# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""g7-visualizer network-isolation guard.

The visualiser serves `/api/create`, `/api/exec`, `/api/tool` and
`/api/destroy` over plain HTTP with NO inbound authentication, and it holds the
gateway mTLS client credential, so every one of those routes drives a real
create/exec/destroy in a live guest using the proxy's cert. Anything that can
open a TCP connection to it is a confused deputy.

Two properties keep that contained, and neither is self-evident from reading
the service:

- the published port keeps its `127.0.0.1:` prefix, so the host does not offer
  it off-box;
- the service shares a bridge with control ALONE. A `ports:` publish says
  nothing about in-network callers, so putting it back on the frontend bridge
  would hand `/api/exec` to the web tier, which processes untrusted input.

These are asserted here because a compose edit is exactly how they get lost.
"""

from pathlib import Path

import yaml

_COMPOSE = (
    Path(__file__).resolve().parents[1] / "fleet" / "docker-compose.fleet.yml"
)

# Services that handle untrusted input and must never share a bridge with the
# unauthenticated exec surface.
_WEB_TIER = {"open-webui", "webui", "embed-portal", "admin", "mcp-gateway"}


def _doc() -> dict:
    return yaml.safe_load(_COMPOSE.read_text(encoding="utf-8"))


def test_the_visualiser_publishes_on_loopback_only() -> None:
    ports = _doc()["services"]["g7-visualizer"].get("ports", [])
    assert ports, "g7-visualizer publishes no port; this guard would be vacuous"
    for entry in ports:
        assert str(entry).startswith("127.0.0.1:"), (
            f"g7-visualizer publishes {entry!r} without a 127.0.0.1 prefix, so "
            "an unauthenticated /api/exec that runs arbitrary argv in a live "
            "guest is offered on every host interface"
        )


def test_the_visualiser_shares_no_bridge_with_the_web_tier() -> None:
    doc = _doc()
    g7 = set(doc["services"]["g7-visualizer"].get("networks") or [])
    assert g7, "g7-visualizer declares no network; this guard would be vacuous"

    for name in sorted(_WEB_TIER):
        svc = doc["services"].get(name)
        if svc is None:
            continue
        shared = g7 & set(svc.get("networks") or [])
        assert not shared, (
            f"g7-visualizer and {name} share {sorted(shared)}. The loopback "
            "publish does not restrict in-network callers, so {name} could "
            "POST /api/exec in cleartext and execute in a live guest using the "
            "proxy's mTLS cert, with no credential of its own."
        )


def test_the_visualiser_still_reaches_control() -> None:
    # The isolation is only correct if it does not also break the one hop the
    # service needs; otherwise a green suite would hide a dead visualiser.
    doc = _doc()
    g7 = set(doc["services"]["g7-visualizer"].get("networks") or [])
    control = set(doc["services"]["control"].get("networks") or [])
    assert g7 & control, (
        "g7-visualizer shares no network with control, so it cannot reach the "
        f"gateway it proxies to (g7={sorted(g7)}, control={sorted(control)})"
    )
