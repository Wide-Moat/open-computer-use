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

In both modes the session finalizer reaps every workspace container labeled
with this run's TEST_RUN_ID so a failing test does not leave orphans on the
host between runs.
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


def _reap_workspace_containers(test_run_id: str) -> int:
    """Force-remove every workspace container tagged with this run.

    Belt-and-braces cleanup: tests usually end their own chat sessions, but a
    crashed test or a SIGINT mid-suite would otherwise leak containers on the
    runner. Returns count of containers actually removed (not just matched) so
    the caller's log message doesn't lie about the result.
    """
    import sys

    label = f"test-run-id={test_run_id}"
    listing = subprocess.run(
        ["docker", "ps", "-aq", "--filter", f"label={label}"],
        capture_output=True, text=True,
    )
    ids = [i for i in listing.stdout.strip().splitlines() if i]
    if not ids:
        return 0
    rm = subprocess.run(["docker", "rm", "-f", *ids], capture_output=True, text=True)
    if rm.returncode != 0:
        # Surface the failure but don't raise — this runs in a finalizer and
        # an exception here would mask the actual test failure that led to
        # the leak. Operator can still see the count mismatch + reason.
        print(
            f"[conftest] WARN: docker rm -f failed (rc={rm.returncode}): "
            f"{rm.stderr.strip()[:300]}",
            file=sys.stderr,
        )
        # Count what actually disappeared by re-querying.
        recheck = subprocess.run(
            ["docker", "ps", "-aq", "--filter", f"label={label}"],
            capture_output=True, text=True,
        )
        remaining = len([i for i in recheck.stdout.strip().splitlines() if i])
        return len(ids) - remaining
    return len(ids)


# Matches docker-compose.test.yml's ${TEST_RUN_ID:-default} fallback. When the
# external-stack path is taken without TEST_RUN_ID set, both sides agree on
# "default" so the finalizer can still find and reap the right containers.
_COMPOSE_DEFAULT_RUN_ID = "default"


@pytest.fixture(scope="session")
def test_run_id() -> str:
    explicit = os.environ.get("TEST_RUN_ID")
    if explicit:
        return explicit
    # External-stack mode without TEST_RUN_ID → align with compose default
    # so the cleanup label query still matches what the orchestrator stamped.
    if os.environ.get("OCU_TEST_BASE_URL"):
        return _COMPOSE_DEFAULT_RUN_ID
    # Owned-stack mode: random id is safe because we set it in compose's env.
    return f"pytest-{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="session")
def orchestrator(test_run_id: str) -> Iterator[dict]:
    """Yield {url, api_key, test_run_id} after ensuring the stack is healthy.

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
        yield {"url": external, "api_key": api_key, "test_run_id": test_run_id}
        # No teardown — caller owns the stack.
        reaped = _reap_workspace_containers(test_run_id)
        if reaped:
            print(f"[conftest] reaped {reaped} orphan workspace containers")
        return

    # Owned-stack mode. Build + up + wait. Always teardown.
    env = {"TEST_RUN_ID": test_run_id}
    up = _compose(["up", "-d", "--build"], env=env)
    if up.returncode != 0:
        pytest.fail(f"docker compose up failed:\nSTDOUT:\n{up.stdout}\nSTDERR:\n{up.stderr}")

    try:
        _wait_for_health(DEFAULT_BASE_URL, HEALTH_TIMEOUT_S)
        yield {"url": DEFAULT_BASE_URL, "api_key": api_key, "test_run_id": test_run_id}
    finally:
        import sys
        reaped = _reap_workspace_containers(test_run_id)
        if reaped:
            print(f"[conftest] reaped {reaped} orphan workspace containers")
        down = _compose(["down", "-v", "--remove-orphans"], env=env)
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
    """A fresh chat-id per test — each gets its own workspace container."""
    return f"itest-{uuid.uuid4().hex[:12]}"


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
