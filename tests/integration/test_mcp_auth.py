# SPDX-License-Identifier: BUSL-1.1
# Copyright (c) 2025 Open Computer Use Contributors
"""
Auth contract: POST /mcp requires Bearer MCP_API_KEY when configured.

Regression target: a refactor that drops the verify_mcp_auth dependency would
make /mcp open to the world. Unit tests don't catch this because the dependency
is wired at app construction time. This suite hits the real container.
"""
from __future__ import annotations

import httpx
import pytest

from conftest import mcp_request


def _init_payload() -> dict:
    return mcp_request(
        "initialize",
        {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "integration-test", "version": "0.0.0"},
        },
    )


@pytest.mark.integration
def test_valid_token_returns_200(orchestrator, chat_id):
    """Sanity: the well-known good token from compose env is accepted."""
    with httpx.Client(base_url=orchestrator["url"], timeout=10.0) as c:
        r = c.post(
            "/mcp",
            json=_init_payload(),
            headers={
                "Authorization": f"Bearer {orchestrator['api_key']}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "X-Chat-Id": chat_id,
            },
        )
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:300]}"


@pytest.mark.integration
def test_missing_authorization_returns_401(orchestrator, chat_id):
    """No Authorization header → 401 with WWW-Authenticate: Bearer."""
    with httpx.Client(base_url=orchestrator["url"], timeout=10.0) as c:
        r = c.post(
            "/mcp",
            json=_init_payload(),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "X-Chat-Id": chat_id,
            },
        )
    # FastAPI/HTTPBearer returns 403 by default when auto_error=True and the
    # header is missing; the codepath in app.py overrides to 401 explicitly.
    # Either status proves auth is enforced; pin to 401 because that's what
    # the code documents.
    assert r.status_code == 401, (
        f"expected 401 for missing auth header, got {r.status_code}: {r.text[:300]}"
    )
    assert "bearer" in r.headers.get("www-authenticate", "").lower()


@pytest.mark.integration
def test_invalid_token_returns_401(orchestrator, chat_id):
    """Wrong token → 401, never 200."""
    with httpx.Client(base_url=orchestrator["url"], timeout=10.0) as c:
        r = c.post(
            "/mcp",
            json=_init_payload(),
            headers={
                "Authorization": "Bearer obviously-wrong-token",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "X-Chat-Id": chat_id,
            },
        )
    assert r.status_code == 401, (
        f"expected 401 for bad token, got {r.status_code}: {r.text[:300]}"
    )
