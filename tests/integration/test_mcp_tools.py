# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""
MCP protocol: tools/list shape + tools/call bash_tool end-to-end.

Regression target: a typo in @mcp.tool() registration (bash_tool → bash_too1)
or a refactor that breaks the streamable_http_app's response wrapping. Both
land in prod silently today.
"""
from __future__ import annotations

import pytest

from conftest import call_mcp

# Snapshot of tools registered in mcp_tools.py. Update intentionally when the
# tool surface changes; a drift here means somebody renamed/added/removed a tool
# and the team should agree before shipping.
EXPECTED_TOOL_NAMES = {"bash_tool", "str_replace", "create_file", "view", "sub_agent"}


def _initialize(client, chat_id) -> None:
    """MCP requires initialize before any other method."""
    r = call_mcp(client, chat_id, "initialize", {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "integration-test", "version": "0.0.0"},
    })
    assert r["status"] == 200, f"initialize failed: {r['body'][:300]}"


@pytest.mark.integration
def test_tools_list_matches_expected_set(client, chat_id):
    _initialize(client, chat_id)
    r = call_mcp(client, chat_id, "tools/list", req_id=2)
    assert r["status"] == 200, f"tools/list HTTP {r['status']}"

    env = r["envelope"]
    assert env["jsonrpc"] == "2.0"
    assert env["id"] == 2
    assert "result" in env, f"missing result: {env}"
    tools = env["result"]["tools"]
    names = {t["name"] for t in tools}

    assert names == EXPECTED_TOOL_NAMES, (
        f"tool set drifted.\n  expected: {sorted(EXPECTED_TOOL_NAMES)}\n  got:      {sorted(names)}"
    )
    # Each tool must declare a non-empty inputSchema. A registration that
    # forgets the schema is technically valid for FastMCP but breaks clients.
    for t in tools:
        assert isinstance(t.get("inputSchema"), dict) and t["inputSchema"], (
            f"tool {t['name']!r} has empty inputSchema"
        )


@pytest.mark.integration
@pytest.mark.timeout(180)  # first call cold-starts a workspace container
def test_bash_tool_echo_roundtrip(client, chat_id):
    """The smallest possible real tool call. Catches:
    - workspace image missing / unpullable
    - Docker socket misconfigured
    - container spawn racing /health
    - response wrapping (content[0].text) regressions
    """
    _initialize(client, chat_id)

    r = call_mcp(client, chat_id, "tools/call", {
        "name": "bash_tool",
        "arguments": {
            "command": "echo hello-from-integration",
            "description": "integration smoke: echo",
        },
    }, req_id=2)
    assert r["status"] == 200, f"tools/call HTTP {r['status']}: {r['body'][:400]}"

    env = r["envelope"]
    assert env["jsonrpc"] == "2.0"
    assert "result" in env, f"got JSON-RPC error instead of result: {env}"
    result = env["result"]

    # MCP tool-level error path: result.isError=True is a successful protocol
    # response carrying a domain-level failure. Treat as fail for this smoke.
    assert not result.get("isError"), f"bash_tool reported isError=True: {result}"

    content = result.get("content", [])
    assert content and content[0]["type"] == "text", (
        f"expected text content[], got: {content}"
    )
    text_blob = "".join(part["text"] for part in content if part.get("type") == "text")
    assert "hello-from-integration" in text_blob, (
        f"expected echo output in tool result, got:\n{text_blob[:500]}"
    )


@pytest.mark.integration
def test_health_unauthenticated(orchestrator):
    """/health stays open — used by k8s probes and uptime monitors."""
    import httpx
    r = httpx.get(f"{orchestrator['url']}/health", timeout=5.0)
    assert r.status_code == 200
    assert r.json() == {"status": "healthy"}
