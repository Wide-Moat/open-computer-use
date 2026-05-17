# SPDX-License-Identifier: BUSL-1.1
# Copyright (c) 2025 Open Computer Use Contributors
"""
Integration test fixtures.

These tests run against a *real* computer-use-server container started via
docker-compose.test.yml. The orchestrator binds the host Docker socket and
spawns real workspace containers, exactly like prod.

Two ways to drive the stack:

  1. Test harness owns lifecycle (default):
     pytest brings the stack up at session start and tears it down at the end.
     `make integration-test` or plain `pytest tests/integration/` from a clean
     checkout. Slow on first run (image build), fast afterwards (cache reuse).

  2. CI / external stack:
     export OCU_TEST_BASE_URL=http://localhost:18081
     export OCU_TEST_MCP_API_KEY=test-token-do-not-use-in-prod
     Stack is assumed to be already up; pytest only runs assertions and
     cleanup. Keeps build/test concerns separate in the CI matrix.

In both modes the session finalizer reaps every workspace container whose
name starts with `owui-chat-itest-` (the prefix every chat_id fixture uses)
so a failing test does not leave orphans on the host between runs. No
production-side env knob is needed — the prefix alone uniquely identifies
test containers.
"""
from __future__ import annotations

import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Iterator

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "docker-compose.test.yml"

# Constant matches docker-compose.test.yml — keep these in sync.
DEFAULT_API_KEY = "test-token-do-not-use-in-prod"
DEFAULT_BASE_URL = "http://localhost:18081"
HEALTH_TIMEOUT_S = 60
HEALTH_POLL_INTERVAL_S = 1.0


def _have_docker() -> bool:
    try:
        return subprocess.run(
            ["docker", "version"], capture_output=True, timeout=5
        ).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _wait_for_health(url: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{url}/health", timeout=2.0)
            if r.status_code == 200 and r.json().get("status") == "healthy":
                return
        except Exception as e:
            last_err = e
        time.sleep(HEALTH_POLL_INTERVAL_S)
    raise RuntimeError(
        f"orchestrator at {url}/health never became healthy in {timeout}s "
        f"(last error: {last_err})"
    )


def _compose(cmd: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    full = ["docker", "compose", "-f", str(COMPOSE_FILE), *cmd]
    return subprocess.run(full, capture_output=True, text=True, env={**os.environ, **(env or {})})


# Every integration test uses a chat_id that starts with this prefix (see the
# `chat_id` fixture). The orchestrator's container naming convention is
# `owui-chat-<chat_id>`, so prefixing the chat_id lets us reap orphans by
# container-name filter — no production-side code change needed.
TEST_CHAT_ID_PREFIX = "itest-"
TEST_CONTAINER_NAME_PREFIX = f"owui-chat-{TEST_CHAT_ID_PREFIX}"


def _reap_test_workspace_containers() -> int:
    """Force-remove workspace containers spawned by this test session.

    Identified by container-name prefix (`owui-chat-itest-`), which only ever
    appears when tests run — no prod chat-id starts with `itest-`. This avoids
    a production-side env knob just for test cleanup.

    Belt-and-braces: tests usually end their own chat sessions, but a crashed
    test or a SIGINT mid-suite would otherwise leak containers on the runner.
    Returns count of containers actually removed.
    """
    import sys

    listing = subprocess.run(
        ["docker", "ps", "-aq",
         "--filter", f"name={TEST_CONTAINER_NAME_PREFIX}",
         "--filter", "label=managed-by=mcp-computer-use-orchestrator"],
        capture_output=True, text=True,
    )
    ids = [i for i in listing.stdout.strip().splitlines() if i]
    if not ids:
        return 0
    rm = subprocess.run(["docker", "rm", "-f", *ids], capture_output=True, text=True)
    if rm.returncode != 0:
        # Don't raise — finalizer must not mask the underlying test failure.
        print(
            f"[conftest] WARN: docker rm -f failed (rc={rm.returncode}): "
            f"{rm.stderr.strip()[:300]}",
            file=sys.stderr,
        )
        recheck = subprocess.run(
            ["docker", "ps", "-aq",
             "--filter", f"name={TEST_CONTAINER_NAME_PREFIX}",
             "--filter", "label=managed-by=mcp-computer-use-orchestrator"],
            capture_output=True, text=True,
        )
        remaining = len([i for i in recheck.stdout.strip().splitlines() if i])
        return len(ids) - remaining
    return len(ids)


@pytest.fixture(scope="session")
def orchestrator() -> Iterator[dict]:
    """Yield {url, api_key} after ensuring the stack is healthy.

    Skips the entire suite if Docker is unavailable — these tests are real
    integration, not unit tests, and pretending otherwise hides regressions.
    """
    if not _have_docker():
        pytest.skip("Docker daemon not reachable; integration tests require Docker")

    external = os.environ.get("OCU_TEST_BASE_URL")
    api_key = os.environ.get("OCU_TEST_MCP_API_KEY", DEFAULT_API_KEY)

    if external:
        # CI / dev opted to manage the stack themselves. Just wait + yield.
        _wait_for_health(external, HEALTH_TIMEOUT_S)
        try:
            yield {"url": external, "api_key": api_key}
        finally:
            reaped = _reap_test_workspace_containers()
            if reaped:
                print(f"[conftest] reaped {reaped} orphan workspace containers")
        return

    # Owned-stack mode. Build + up + wait. Always teardown.
    up = _compose(["up", "-d", "--build"])
    if up.returncode != 0:
        pytest.fail(f"docker compose up failed:\nSTDOUT:\n{up.stdout}\nSTDERR:\n{up.stderr}")

    try:
        _wait_for_health(DEFAULT_BASE_URL, HEALTH_TIMEOUT_S)
        yield {"url": DEFAULT_BASE_URL, "api_key": api_key}
    finally:
        import sys
        reaped = _reap_test_workspace_containers()
        if reaped:
            print(f"[conftest] reaped {reaped} orphan workspace containers")
        down = _compose(["down", "-v", "--remove-orphans"])
        if down.returncode != 0:
            # Don't raise — we're in a finalizer and an exception here would
            # mask the actual test failure. But do surface the daemon error so
            # leftover networks/volumes on the runner are diagnosable.
            print(
                f"[conftest] WARN: docker compose down failed (rc={down.returncode}): "
                f"{down.stderr.strip()[:300]}",
                file=sys.stderr,
            )


@pytest.fixture()
def client(orchestrator) -> Iterator[httpx.Client]:
    """HTTP client preconfigured with auth + sensible timeout for tool calls."""
    headers = {
        "Authorization": f"Bearer {orchestrator['api_key']}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    with httpx.Client(base_url=orchestrator["url"], headers=headers, timeout=120.0) as c:
        yield c


@pytest.fixture()
def chat_id() -> str:
    """A fresh chat-id per test — each gets its own workspace container.

    The `itest-` prefix is load-bearing: the session finalizer uses it (via
    `owui-chat-itest-*` container-name match) to find and reap orphans
    without touching prod containers a developer may have running locally.
    """
    return f"{TEST_CHAT_ID_PREFIX}{uuid.uuid4().hex[:12]}"


def mcp_request(method: str, params: dict | None = None, req_id: int = 1) -> dict:
    """Build a JSON-RPC 2.0 request envelope matching the MCP spec."""
    payload: dict = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        payload["params"] = params
    return payload


def parse_mcp_response(resp: httpx.Response) -> dict:
    """Return the decoded JSON-RPC envelope from either an SSE or JSON body.

    FastMCP's streamable_http_app picks the response format based on the
    request's Accept header — we send both, and the server tends to reply
    with text/event-stream. The single data: line carries the actual envelope.
    """
    import json

    ctype = resp.headers.get("content-type", "")
    body = resp.text
    # Detect SSE only by Content-Type or by an `event:`/`data:` line at the
    # *start* of a line. The original substring-anywhere check was too loose:
    # a perfectly valid JSON-RPC payload like {"result":{"data":"x"}} contains
    # the literal `"data:` and would be misrouted to the SSE branch.
    is_sse = (
        "text/event-stream" in ctype
        or body.lstrip().startswith("event:")
        or any(line.startswith("data:") for line in body.splitlines())
    )
    if is_sse and "text/event-stream" in ctype:
        # Trust Content-Type when present — only then walk SSE frames.
        for line in body.splitlines():
            if line.startswith("data:"):
                return json.loads(line[len("data:"):].strip())
        raise AssertionError(f"SSE body had no data: line. Raw:\n{body[:500]}")
    return json.loads(body)


def call_mcp(client: httpx.Client, chat_id: str, method: str,
             params: dict | None = None, req_id: int = 1) -> dict:
    """POST /mcp with the X-Chat-Id header the orchestrator requires."""
    resp = client.post(
        "/mcp",
        json=mcp_request(method, params, req_id),
        headers={"X-Chat-Id": chat_id},
    )
    return {"status": resp.status_code, "headers": dict(resp.headers),
            "envelope": parse_mcp_response(resp) if resp.status_code == 200 else None,
            "body": resp.text}
