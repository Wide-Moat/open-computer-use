# SPDX-License-Identifier: BUSL-1.1
# Copyright (c) 2025 Open Computer Use Contributors
"""
Workspace container lifecycle: the orchestrator spawns a real per-chat
container on the first tools/call, labels it correctly, and binds the
expected mount paths.

Regression target: docker_manager.py refactors that drop a label or change a
mount path. Unit tests cover env injection but never actually start a
container, so a mount typo would land in prod.
"""
from __future__ import annotations

import subprocess

import pytest

from conftest import call_mcp


def _list_containers_for_chat(chat_id: str) -> list[dict]:
    import json
    r = subprocess.run(
        ["docker", "ps", "-a",
         "--filter", f"label=chat-id={chat_id}",
         "--format", "{{json .}}"],
        capture_output=True, text=True, check=True,
    )
    return [json.loads(line) for line in r.stdout.splitlines() if line.strip()]


def _inspect(container_id: str) -> dict:
    import json
    r = subprocess.run(
        ["docker", "inspect", container_id],
        capture_output=True, text=True, check=True,
    )
    return json.loads(r.stdout)[0]


@pytest.mark.integration
@pytest.mark.timeout(180)
def test_first_tool_call_spawns_labeled_workspace(client, chat_id, orchestrator):
    """After one tools/call, the chat must own exactly one workspace container
    with the prod label set and the test-run-id we asked compose to inject."""
    call_mcp(client, chat_id, "initialize", {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "integration-test", "version": "0.0.0"},
    })
    r = call_mcp(client, chat_id, "tools/call", {
        "name": "bash_tool",
        "arguments": {"command": "true", "description": "spawn"},
    }, req_id=2)
    assert r["status"] == 200, f"tools/call failed: {r['body'][:300]}"

    containers = _list_containers_for_chat(chat_id)
    assert len(containers) == 1, (
        f"expected exactly 1 workspace for chat-id={chat_id}, got {len(containers)}"
    )

    info = _inspect(containers[0]["ID"])
    labels = info["Config"]["Labels"] or {}

    assert labels.get("managed-by") == "mcp-computer-use-orchestrator", (
        f"prod label missing: {labels}"
    )
    assert labels.get("chat-id") == chat_id
    assert labels.get("tool") == "computer-use-mcp"
    # The test-run-id label proves the WORKSPACE_EXTRA_LABELS pipeline works
    # — without it, the session finalizer can't reap orphans.
    assert labels.get("test-run-id") == orchestrator["test_run_id"], (
        f"WORKSPACE_EXTRA_LABELS did not propagate. Labels: {labels}"
    )


@pytest.mark.integration
@pytest.mark.timeout(180)
def test_workspace_has_user_data_mounts(client, chat_id):
    """Bind mounts under /mnt/user-data must exist on the spawned container.
    Docker-compose's USER_DATA_BASE_PATH must round-trip into the workspace.
    """
    call_mcp(client, chat_id, "initialize", {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "integration-test", "version": "0.0.0"},
    })
    call_mcp(client, chat_id, "tools/call", {
        "name": "bash_tool",
        "arguments": {"command": "true", "description": "spawn"},
    }, req_id=2)

    containers = _list_containers_for_chat(chat_id)
    assert containers, "no workspace container was spawned"

    mounts = _inspect(containers[0]["ID"])["Mounts"]
    dests = {m["Destination"]: m for m in mounts}

    assert "/mnt/user-data/uploads" in dests, f"missing uploads mount: {dests.keys()}"
    assert "/mnt/user-data/outputs" in dests, f"missing outputs mount: {dests.keys()}"

    uploads = dests["/mnt/user-data/uploads"]
    outputs = dests["/mnt/user-data/outputs"]
    assert uploads["Mode"] in ("ro", "rorw"), f"uploads must be read-only, got {uploads['Mode']}"
    # Outputs may be 'rw' or absent Mode field depending on docker version;
    # check RW is true rather than parsing Mode string.
    assert outputs.get("RW") is True, f"outputs must be RW: {outputs}"
