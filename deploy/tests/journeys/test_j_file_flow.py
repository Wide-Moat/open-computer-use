# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""GROUP J — two-way user<->agent file flow across the storage spine, fleet-only.

The finale proved the chat tool cycle; this group pins the FILE cycle between
the chat guest and the user's Files panel, the two legs no other group covers:

  J1  agent-written /mnt/user-data file reaches the user: pane lists it and
      serves its exact bytes (agent -> engine outputs/ -> F9 north -> download)
  J2  user-uploaded file reaches the agent: a pane upload is readable, byte
      exact, from a fresh guest at /mnt/user-data (F9 create -> uploads/ ->
      south mount read)
  J3  the north egress gate survives both legs: an uploads-side object is
      still refused for download (not-downloadable), while the agent's
      outputs-side deliverable serves 200 - the asymmetry IS the control

It drives the REAL wires end to end: the gateway on 127.0.0.1:8080 with the
minted bearer (like groups H/I) for the guest side, and the embed-portal
(127.0.0.1:3003) + File Pane BFF (127.0.0.1:3000) for the user side. Writes
through the guest mount are ASYNC (VFS write-back, seconds); assertions poll
with a bounded deadline instead of sleeping blind. Skips loudly when a wire is
unreachable - never a fabricated green.

No poc counterpart: the PoC shares one docker volume both ways with no
engine/panel spine; the contrast lives in scenarios.yaml (J1..J3).
"""

import json
import subprocess
import time
import uuid

import pytest

GATEWAY_URL = "http://127.0.0.1:8080/"
PORTAL_TOKEN_URL = "http://127.0.0.1:3003/token"
PANE_URL = "http://127.0.0.1:3000"
_PROTO = "2025-06-18"

pytestmark = pytest.mark.fleet

from test_i_mcp_surface import _bash_body, _bearer, _call  # noqa: E402  (same wire)


# --- user-side (pane) wire helpers -----------------------------------------


def _curl_json(args, timeout=15):
    """Run curl, return (status:int, body:str). Transport failure raises."""
    out = subprocess.run(
        ["curl", "-sS", "--max-time", str(timeout), "-o", "-", "-w", "\n%{http_code}"]
        + args,
        capture_output=True,
        text=True,
        timeout=timeout + 10,
    )
    if out.returncode != 0:
        raise RuntimeError(f"curl transport failure rc={out.returncode}: {out.stderr[:200]}")
    text = out.stdout
    nl = text.rfind("\n")
    return int(text[nl + 1 :].strip()), text[:nl]


def _pane_session(tmp_path):
    """Portal token -> pane bootstrap. Returns (cookie_jar_path, csrf_token).

    Skips loudly when the portal or the pane is down: the user leg cannot be
    proven without the real browser-facing wires, and is never mocked green.
    """
    jar = str(tmp_path / "pane-cookies.txt")
    try:
        status, body = _curl_json([PORTAL_TOKEN_URL])
    except RuntimeError:
        pytest.skip("embed-portal (127.0.0.1:3003) unreachable - user leg cannot run. LOUD SKIP, not a pass.")
    if status != 200:
        pytest.skip(f"embed-portal /token returned {status} - user leg cannot run. LOUD SKIP, not a pass.")
    token = json.loads(body)["token"]
    status, body = _curl_json(
        ["-c", jar, "-X", "POST", "-H", f"Authorization: Bearer {token}",
         f"{PANE_URL}/api/auth/embed-token"]
    )
    if status != 200:
        pytest.skip(f"pane bootstrap returned {status} - user leg cannot run. LOUD SKIP, not a pass.")
    csrf = json.loads(body).get("csrfToken", "")
    return jar, csrf


def _pane_list(jar):
    status, body = _curl_json(["-b", jar, f"{PANE_URL}/api/v1/files"])
    assert status == 200, f"pane list status = {status}, want 200"
    return json.loads(body)["data"]


def _pane_find(jar, filename, deadline_s=45):
    """Poll the pane list until filename appears (guest writes are async
    VFS write-back) or the deadline passes; returns the FileObject or None."""
    end = time.monotonic() + deadline_s
    while time.monotonic() < end:
        hit = [f for f in _pane_list(jar) if f.get("filename") == filename]
        if hit:
            return hit[0]
        time.sleep(3)
    return None


def _pane_content(jar, file_id):
    return _curl_json(["-b", jar, f"{PANE_URL}/api/v1/files/{file_id}/content"])


def _pane_upload(jar, csrf, filename, content, mime="text/plain"):
    status, body = _curl_json(
        ["-b", jar, "-X", "POST",
         "-H", f"x-csrf-token: {csrf}",
         "-H", f"x-filename: {filename}",
         "-H", f"Content-Type: {mime}",
         "--data-binary", content,
         f"{PANE_URL}/api/v1/files"]
    )
    assert status == 200, f"pane upload status = {status}, want 200: {body[:200]}"
    return json.loads(body)


# --- guest-side helper -------------------------------------------------------


def _require_gateway():
    if _bearer() is None:
        pytest.skip("boot-set/bearer not rendered - see README re-mint runbook. LOUD SKIP, not a pass.")
    try:
        status, _ = _call(f"j-probe-{uuid.uuid4().hex[:8]}", _bash_body("true"))
    except RuntimeError:
        pytest.skip("gateway (127.0.0.1:8080) unreachable - guest leg cannot run. LOUD SKIP, not a pass.")
    if status == 401:
        pytest.skip("gateway refused the rendered bearer (401) - re-mint per README. LOUD SKIP, not a pass.")


def _guest_bash(chat_id, command, timeout=60):
    status, parsed = _call(chat_id, _bash_body(command), timeout=timeout)
    assert status == 200, f"bash_tool transport status = {status}, want 200"
    result = parsed["result"]
    text = "".join(b.get("text", "") for b in result.get("content", []))
    return result.get("isError", False), text


# --- J1: agent deliverable reaches the user ---------------------------------


def test_j1_agent_write_reaches_pane_download(tmp_path):
    """Agent writes /mnt/user-data/<unique> -> pane lists it -> download 200
    serves the exact bytes. Keystone: a never-written sibling name stays
    absent from the same listing window, so the green cannot come from a
    stale or over-matching list."""
    _require_gateway()
    jar, _csrf = _pane_session(tmp_path)

    name = f"j1-{uuid.uuid4().hex[:10]}.txt"
    ghost = f"j1-ghost-{uuid.uuid4().hex[:10]}.txt"
    payload = f"J1-DELIVERABLE-{uuid.uuid4().hex}"

    is_err, text = _guest_bash(
        f"j1-{uuid.uuid4().hex[:8]}",
        f"printf %s '{payload}' > /mnt/user-data/{name} && echo WROTE",
    )
    assert not is_err and "WROTE" in text, f"guest write failed: {text[:200]}"

    obj = _pane_find(jar, name)
    assert obj is not None, f"pane never listed {name} within the write-back deadline"
    # Keystone: the ghost name must NOT appear - the list is real, not echoed.
    assert not [f for f in _pane_list(jar) if f.get("filename") == ghost]

    status, body = _pane_content(jar, obj["id"])
    assert status == 200, f"download of the agent deliverable = {status}, want 200"
    assert body == payload, "downloaded bytes differ from what the agent wrote"


# --- J2: user upload reaches the agent ---------------------------------------


def test_j2_pane_upload_readable_by_guest(tmp_path):
    """User uploads via the pane -> a FRESH guest reads the exact bytes at
    /mnt/user-data/<name>. Byte equality is the assertion; a stat-visible but
    empty read (the retired #143 failure mode, once pinned here as a strict
    xfail) must FAIL, never pass."""
    _require_gateway()
    jar, csrf = _pane_session(tmp_path)

    name = f"j2-{uuid.uuid4().hex[:10]}.txt"
    payload = f"J2-UPLOAD-{uuid.uuid4().hex}"
    _pane_upload(jar, csrf, name, payload)

    is_err, text = _guest_bash(
        f"j2-{uuid.uuid4().hex[:8]}",
        f"cat /mnt/user-data/{name}",
    )
    assert not is_err, f"guest read errored: {text[:200]}"
    assert text.strip() == payload, (
        f"guest read {len(text.strip())} bytes, want {len(payload)} - "
        "stat-visible-but-empty is the #143 failure mode"
    )


# --- J3: the north egress gate survives both legs ----------------------------


def test_j3_download_gate_asymmetry(tmp_path):
    """The uploads-side object refuses download (not-downloadable) while the
    agent's outputs-side deliverable serves 200. The asymmetry is the
    keystone: if a fix for the south read path ever loosens the NORTH gate,
    the 403 half reddens; if the outputs leg breaks, the 200 half reddens."""
    _require_gateway()
    jar, csrf = _pane_session(tmp_path)

    up_name = f"j3-up-{uuid.uuid4().hex[:10]}.txt"
    up_obj = _pane_upload(jar, csrf, up_name, "J3-UPLOAD-SIDE")
    status, _ = _pane_content(jar, up_obj["id"])
    assert status == 403, (
        f"download of an uploads-side object = {status}, want 403 "
        "(NFR-SEC-73 stored-tag gate on the north content egress)"
    )

    out_name = f"j3-out-{uuid.uuid4().hex[:10]}.txt"
    is_err, text = _guest_bash(
        f"j3-{uuid.uuid4().hex[:8]}",
        f"printf %s J3-OUTPUT-SIDE > /mnt/user-data/{out_name} && echo WROTE",
    )
    assert not is_err and "WROTE" in text
    obj = _pane_find(jar, out_name)
    assert obj is not None, f"pane never listed {out_name} within the write-back deadline"
    status, body = _pane_content(jar, obj["id"])
    assert status == 200 and body == "J3-OUTPUT-SIDE", (
        f"outputs-side deliverable download = {status}, want 200 byte-exact"
    )
