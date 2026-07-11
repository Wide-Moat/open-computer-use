# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""D5 per-chat scope-resolve keystone (openwebui tool).

The OpenWebUI tool resolves its chat's storage scope from control's caller-scoped
status verb (POST /v1alpha/sessions/status), reading `effective_scope` from the
response. It NEVER derives the scope handle locally; the attested owner form is
control-only (ADR-0030, D5).

These tests drive the REAL _resolve_chat_scope path with a mocked HTTP transport:
- two chats whose status verb returns distinct derived scopes resolve to DISTINCT
  scopes (the load-bearing isolation property);
- a response that omits effective_scope (control ran without -derive-chat-scope)
  degrades to the base OCU_FILESYSTEM_ID (today's behaviour).

Red-probe: if _resolve_chat_scope ignores the response and always returns the
base, the "distinct scope per chat" assertion REDs.
"""

import asyncio
import io
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

_TOOLS_DIR = Path(__file__).resolve().parents[2] / "openwebui" / "tools"
sys.path.insert(0, str(_TOOLS_DIR))

import computer_use_tools as m  # noqa: E402


class _FakeResp:
    """Minimal urlopen context-manager stand-in."""

    def __init__(self, status, payload):
        self.status = status
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._body


@contextmanager
def _status_verb(by_chat):
    """Patch urlopen so each POST /v1alpha/sessions/status returns the response
    keyed by the request's session_hint. Verifies the tool actually POSTs the
    chat id (X-Chat-Id header + session_hint body)."""

    def fake_urlopen(req, timeout=None):
        chat = req.get_header("X-chat-id")  # urllib title-cases header keys
        body = json.loads(req.data.decode("utf-8"))
        assert body["session_hint"] == chat, "session_hint must equal X-Chat-Id"
        status, payload = by_chat[chat]
        return _FakeResp(status, payload)

    with mock.patch.object(m.urllib.request, "urlopen", fake_urlopen):
        yield


def _new_tool(base="fs-fleet"):
    t = m.Tools()
    t.valves.OCU_FILESYSTEM_ID = base
    t.valves.ORCHESTRATOR_URL = "http://mcp-gateway:8080"
    t.valves.MCP_API_KEY = "sk-ocu-test"
    return t


def test_two_chats_resolve_distinct_derived_scopes():
    t = _new_tool()
    responses = {
        "chat-a": (200, {"key": "k1", "state": 2, "effective_scope": "fs-fleet-aaaa000011112222"}),
        "chat-b": (200, {"key": "k2", "state": 2, "effective_scope": "fs-fleet-bbbb333344445555"}),
    }
    with _status_verb(responses):
        scope_a = asyncio.run(t._resolve_chat_scope("chat-a"))
        scope_b = asyncio.run(t._resolve_chat_scope("chat-b"))

    assert scope_a == "fs-fleet-aaaa000011112222"
    assert scope_b == "fs-fleet-bbbb333344445555"
    # The load-bearing property: two chats -> two distinct resolved scopes.
    assert scope_a != scope_b, "per-chat scopes must be distinct"
    # And neither is the bare base (derivation is on).
    assert scope_a != "fs-fleet" and scope_b != "fs-fleet"


def test_absent_effective_scope_degrades_to_base():
    t = _new_tool()
    # control ran WITHOUT -derive-chat-scope: no effective_scope in the body.
    responses = {"chat-x": (200, {"key": "k", "state": 2})}
    with _status_verb(responses):
        scope = asyncio.run(t._resolve_chat_scope("chat-x"))
    assert scope == "fs-fleet", "absent effective_scope must degrade to the base"


def test_transport_error_degrades_to_base():
    t = _new_tool()

    def boom(req, timeout=None):
        raise OSError("connection refused")

    with mock.patch.object(m.urllib.request, "urlopen", boom):
        scope = asyncio.run(t._resolve_chat_scope("chat-err"))
    assert scope == "fs-fleet", "a status-verb miss must not break the upload path"


def test_scope_is_cached_per_chat():
    t = _new_tool()
    calls = {"n": 0}

    def counting(req, timeout=None):
        calls["n"] += 1
        return _FakeResp(200, {"key": "k", "state": 2, "effective_scope": "fs-fleet-deadbeefdeadbeef"})

    with mock.patch.object(m.urllib.request, "urlopen", counting):
        first = asyncio.run(t._resolve_chat_scope("chat-c"))
        second = asyncio.run(t._resolve_chat_scope("chat-c"))
    assert first == second == "fs-fleet-deadbeefdeadbeef"
    assert calls["n"] == 1, "the status verb is hit once per chat, then cached"
