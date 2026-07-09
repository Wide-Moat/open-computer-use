# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""GROUP I — MCP tool-surface properties BELOW the exec contract, fleet-only.

The @L4 half of mcp_tool_surface.feature (projection, script semantics, result
shaping) is proven in the gateway forward e2e, where a control-mock executes the
real committed scripts. This group proves the @L5 half — the properties only a
LIVE guest can settle:

  I1  a real failing command's non-zero exit is really transported to isError
  I2  oversized guest output is bounded by control, not relayed whole
  I3  a command past the timeout is killed below the contract
  I4  create_file EACCES is a function of the live guest identity (a contrast)
  I5  one chat maps to one PERSISTENT workspace across tool calls
  I6  the four tools compose over one workspace (needs a python3 guest, #122)

It drives the REAL gateway on 127.0.0.1:8080 with the minted bearer, exactly like
group H. Every scenario carries its keystone (the negative that makes the green
non-vacuous) inline. It skips loudly when the gateway is unreachable or the boot
set is not rendered — it never fabricates a green.

No poc counterpart: these are gateway/control-transported properties; the PoC has
no gateway. The PoC-vs-fleet contrast for each lives in scenarios.yaml (I1..I6).
"""

import json
import subprocess
import time
import uuid
from pathlib import Path

import pytest

# The gateway's north listener, host-mapped in the fleet compose (same as H).
GATEWAY_URL = "http://127.0.0.1:8080/"
_PROTO = "2025-06-18"
_SECRETS = Path(__file__).resolve().parents[2] / "fleet" / "secrets" / "gateway"
_BOOT_SET = _SECRETS / "boot-set.json"
_BEARER_FILE = _SECRETS / "bearer.txt"

pytestmark = pytest.mark.fleet


def _bearer():
    if _BEARER_FILE.exists():
        b = _BEARER_FILE.read_text().strip()
        return b or None
    return None


def _bash_body(command):
    """A tools/call bash_tool JSON-RPC body — the exact shape the browser sends."""
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "bash_tool", "arguments": {"command": command}},
        }
    )


def _file_tool_body(name, arguments):
    """A tools/call body for a file tool (create_file / view / str_replace)."""
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )


def _call(chat_id, body, timeout=40):
    """POST a tools/call to the gateway; return (http_status:int, parsed:dict|None).

    Uses curl to match the exact wire and to stay dependency-free like the demo
    scripts. Raises on a transport failure so an unreachable gateway becomes a
    loud skip via _require_gateway, never a silent pass.
    """
    bearer = _bearer()
    args = [
        "curl", "-sS", "--max-time", str(timeout), "-o", "-", "-w", "\n%{http_code}",
        GATEWAY_URL,
        "-H", f"Authorization: Bearer {bearer}",
        "-H", f"MCP-Protocol-Version: {_PROTO}",
        "-H", f"X-Chat-Id: {chat_id}",
        "-H", "content-type: application/json",
        "-d", body,
    ]
    out = subprocess.run(args, capture_output=True, text=True, timeout=timeout + 10)
    if out.returncode != 0:
        raise RuntimeError(f"curl transport failure rc={out.returncode}: {out.stderr[:200]}")
    text = out.stdout
    nl = text.rfind("\n")
    status = int(text[nl + 1 :].strip())
    try:
        parsed = json.loads(text[:nl])
    except (ValueError, TypeError):
        parsed = None
    return status, parsed


def _result(parsed):
    """(text, is_error) from a CallToolResult, or (None, None) on a JSON-RPC error."""
    if not isinstance(parsed, dict) or "error" in parsed:
        return None, None
    res = parsed.get("result") or {}
    is_error = bool(res.get("isError"))
    text = None
    for item in res.get("content") or []:
        if item.get("type") == "text":
            text = item.get("text")
            break
    return text, is_error


def _gateway_live():
    try:
        _call("i-probe", _bash_body("true"), timeout=8)
        return True
    except Exception:
        return False


def _guest_has_python3(chat_id):
    """True iff the live guest has a runnable python3 (gates the file-tool journey)."""
    _, parsed = _call(chat_id, _bash_body("command -v python3 >/dev/null 2>&1 && echo yes || echo no"))
    text, _ = _result(parsed)
    return bool(text and "yes" in text)


@pytest.fixture(autouse=True)
def _require_gateway():
    if not _BOOT_SET.exists():
        pytest.skip(
            f"gateway boot-set not rendered at {_BOOT_SET} "
            "(run scripts/mint_boot_set.py) — SKIP, not a pass."
        )
    if _bearer() is None:
        pytest.skip(f"gateway bearer not rendered at {_BEARER_FILE} — SKIP, not a pass.")
    if not _gateway_live():
        pytest.skip(
            f"MCP gateway not reachable at {GATEWAY_URL} "
            "(bring up the mcp-gateway service inside Lima) — SKIP, not a pass."
        )


def _cid(tag):
    return f"i-{tag}-{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# I1 — a real non-zero exit is transported to isError (not fabricated)
# ---------------------------------------------------------------------------

def test_i1_nonzero_exit_transports_to_iserror():
    """A real failing command over the live gateway → isError:true; a zero-exit
    command over the SAME path → isError:false. Proves the flag tracks the guest's
    real exit code (control transports it), not a constant. Empty-output non-zero
    also carries the synthesized "[Exit code: N]" (the L4 shaping, proven live)."""
    status, parsed = _call(_cid("i1-fail"), _bash_body("exit 7"))
    assert status == 200, f"a tool error is Tier-2 (HTTP 200 + isError), got {status}"
    text, is_error = _result(parsed)
    assert is_error is True, f"a real non-zero exit must transport isError:true, got {parsed}"
    assert text == "[Exit code: 7]", (
        f"empty-output non-zero must synthesize the exit-code marker live, got {text!r}"
    )

    # keystone: a zero exit over the SAME path is NOT an error (flag is not constant).
    status, parsed = _call(_cid("i1-ok"), _bash_body("true"))
    text, is_error = _result(parsed)
    assert status == 200 and is_error is False, (
        f"a zero-exit command must be isError:false (keystone), got status={status} {parsed}"
    )


# ---------------------------------------------------------------------------
# I2 — oversized output is bounded by control, not relayed whole
# ---------------------------------------------------------------------------

# The step-2 caller-facing content ceiling (#128): once control bounds each reply
# stream at 64 KiB at the source, this is the size a caller ever sees. I2c pins it.
_CONTENT_CEILING_BYTES = 64 << 10  # 65536

_I2_BIG = 120000  # raw stdout for the oversized probe — well past the old ~48KiB 502 boundary


def test_i2_oversized_output_is_not_dropped():
    """The #127 step-1 contract (gateway PR #43): oversized output is a BOUNDED TOOL
    RESULT, not a 502 forward-refusal that loses the whole result. A 120k output that
    used to 502 now returns HTTP 200 with the output intact.

    This asserts nothing-lost STRICTLY (len >= the emitted size). That is a designed
    paired-flip with I2c: when step 2 (#128, control 64KiB reply ceiling) lands, a
    120k output comes back bounded at 64KiB, so THIS test reds at the SAME moment
    I2c strict-xpasses — the step-2 PR must reconcile them into one bounded-contract
    test. The transitional assert cannot rot silently: the event that retires it is
    the event that reds it.

    Residual: step 1 moved the 502 boundary, it did not kill the class — an output
    whose base64-in-JSON exceeds the 24MiB read-cap (~18MiB raw) still truncates
    mid-JSON and 502s. Step 2 removes the class by bounding at the source."""
    status, parsed = _call(_cid("i2-big"), _bash_body(f"yes X | head -c {_I2_BIG}"))
    text, is_error = _result(parsed)
    assert status == 200, (
        f"oversized output must be a bounded tool result (HTTP 200), not a 502 "
        f"forward-refusal that loses the whole result — got {status} (#127 step 1)"
    )
    assert is_error is False, f"a large stdout output is not an error, got isError on {parsed}"
    assert text is not None and len(text) >= _I2_BIG, (
        f"the whole output must survive (nothing lost, nothing silently cut), got "
        f"{len(text or '')} bytes for a {_I2_BIG}-byte emit"
    )

    # keystone: a small marker over the SAME path comes back whole.
    marker = "I2_SMALL_" + uuid.uuid4().hex[:8]
    _, parsed = _call(_cid("i2-small"), _bash_body(f"printf %s {marker}"))
    text, _ = _result(parsed)
    assert text is not None and marker in text, (
        f"a small output must return whole (keystone), got {text!r}"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "#128 (step 2): the CALLER-facing content ceiling is not yet 64KiB. Step 1 "
        "(#127, merged) raised the gateway boundContent to 8MiB, so output up to 8MiB "
        "comes back whole with no marker. Step 2 bounds each control reply stream at "
        "64KiB at the source, making 64KiB the caller ceiling + surfacing the "
        "truncation marker. xfail(strict) XPASSes -> reds the suite when step 2 lands, "
        "forcing this and I2 to merge into one bounded-contract test."
    ),
)
def test_i2c_oversized_output_bounded_at_caller_ceiling():
    """The step-2 (#128) contract: oversized output is bounded at the 64KiB
    caller-facing ceiling with a truncation marker. Fails until control bounds the
    reply stream at the source (today boundContent is 8MiB, so a 120k output is
    returned whole and this reds)."""
    status, parsed = _call(_cid("i2c-big"), _bash_body(f"yes X | head -c {_I2_BIG}"))
    text, is_error = _result(parsed)
    assert status == 200 and is_error is False, (
        f"oversized output must be a bounded tool result, got {status} {parsed}"
    )
    assert text is not None and len(text) <= _CONTENT_CEILING_BYTES, (
        f"oversized output must be bounded at the 64KiB caller ceiling, got "
        f"{len(text or '')} bytes"
    )
    assert "truncat" in text.lower(), (
        f"a bounded large output must carry a truncation marker, got {text[-120:]!r}"
    )


def test_i2b_moderate_output_returns_whole():
    """A moderate output returns whole and un-truncated over the live gateway. This
    is the long-lived whole-return-under-ceiling keystone: n=30000 sits below the
    FINAL 64KiB caller ceiling (#128), so it returns whole both now (step 1: 8MiB
    boundContent) and after step 2 lands (64KiB ceiling) — it survives the step-2
    flip untouched. Kept deliberately below the ceiling; do not raise toward 64KiB."""
    n = 30000
    status, parsed = _call(_cid("i2b"), _bash_body(f"yes X | head -c {n}"))
    text, is_error = _result(parsed)
    assert status == 200 and is_error is False, (
        f"a moderate {n}-byte output must return a clean tool result, got {status} {parsed}"
    )
    assert text is not None and len(text) >= n, (
        f"a moderate output must come back whole ({n} bytes), got {len(text or '')}"
    )


# ---------------------------------------------------------------------------
# I3 — a command past the timeout is killed below the contract
# ---------------------------------------------------------------------------

def test_i3_timeout_is_enforced():
    """A command that would sleep far past the exec-timeout is KILLED (does not run
    to completion), while a fast command over the SAME path returns promptly. This
    proves timeout ENFORCEMENT — the load-bearing property — holds on the live
    stand. It does NOT assert the result shape (that is I3b): today control's
    exec-timeout (execTimeoutDefaultSeconds=30) kills the command and the leg
    surfaces as a 502; enforcement is proven by the wall-clock, not the status."""
    # sleep 600 would hang for 10 minutes if unbounded; the exec-timeout kills it
    # far sooner. We assert it did NOT run to completion, whatever the result shape.
    start = time.monotonic()
    try:
        _call(_cid("i3-hang"), _bash_body("sleep 600"), timeout=120)
    except RuntimeError:
        # A curl-level abort still means the call did not hang the full 600s; the
        # wall-clock assertion below is the real check.
        pass
    elapsed = time.monotonic() - start
    assert elapsed < 115, (
        f"a sleep 600 must be KILLED by the exec-timeout, not run to completion; "
        f"took {elapsed:.0f}s (timeout enforcement is the load-bearing property)"
    )

    # keystone: a fast command returns promptly (the kill is the timeout, not a cap).
    start = time.monotonic()
    marker = "I3_FAST_" + uuid.uuid4().hex[:8]
    _, parsed = _call(_cid("i3-fast"), _bash_body(f"printf %s {marker}"))
    fast_elapsed = time.monotonic() - start
    text, _ = _result(parsed)
    assert text is not None and marker in text and fast_elapsed < 30, (
        f"a fast command must return promptly (keystone), took {fast_elapsed:.0f}s text={text!r}"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "DEFECT #129 (timeout-shaping, NOT the #127 size class): a timed-out command "
        "surfaces as a 502 forward-refusal, not a Tier-2 tool result. The PoC returns "
        "the run with a '[Command timed out after N seconds]' notice (isError), a "
        "USABLE result. sleep 600 emits zero stdout, so #127's maxReplyBytes raise "
        "could not have touched this path — it's control's exec-timeout shaped into "
        "ErrForwardFailed. xfail(strict) reds the suite when the timeout-shaping fix "
        "lands. Enforcement itself (the kill) is proven green in I3."
    ),
)
def test_i3b_timeout_surfaces_as_tool_result_not_502():
    """A timed-out command should be a bounded Tier-2 tool result (isError:true with
    a timeout notice), the way the PoC returns it — not a 502 that loses the result.
    Companion to I3: I3 proves the KILL happens; I3b pins the RESULT-SHAPE contract
    the fleet does not yet meet."""
    status, parsed = _call(_cid("i3b"), _bash_body("sleep 600"), timeout=120)
    text, is_error = _result(parsed)
    assert status == 200, (
        f"a timed-out command must be a tool result (HTTP 200 + isError), not a 502 "
        f"forward-refusal — got {status} (DEFECT #127)"
    )
    assert is_error, f"a timed-out command must be a tool error, got {parsed}"


# ---------------------------------------------------------------------------
# I4 — create_file EACCES is a function of the live guest identity (a contrast)
# ---------------------------------------------------------------------------

def test_i4_write_permission_is_guest_identity_contrast():
    """The PoC's create_file into /home/assistant returns [Errno 13] because the
    guest user is not the owner. The fleet guest identity may differ (root vs a
    named user), so this records the LIVE outcome as a contrast rather than
    asserting the PoC's exact errno. The keystone: a writable path over the SAME
    session succeeds — the write plane is not broken, only the protected path is
    (whatever the guest identity makes protected)."""
    if not _guest_has_python3(_cid("i4-probe")):
        pytest.skip(
            "create_file needs a python3-bearing guest (#122); the default guest is "
            "stripped — SKIP, not a pass. I4 is a file-tool identity contrast."
        )
    cid = _cid("i4")
    # A path a non-root user typically cannot write; the LIVE outcome is recorded.
    status, parsed = _call(
        cid, _file_tool_body("create_file", {"path": "/root/i4_probe.txt", "file_text": "x"})
    )
    text, is_error = _result(parsed)
    assert status == 200, f"create_file is a tool call (HTTP 200), got {status}"
    # Contrast, not a fixed assertion: if the guest runs as root the write may
    # SUCCEED where the PoC's assistant-user would EACCES. Either way it must be a
    # legible result, and we record which for CONTRAST.md.
    outcome = "ERROR(" + (text or "").strip()[:60] + ")" if is_error else "WROTE"
    print(f"[I4 CONTRAST] fleet create_file /root -> {outcome}")

    # keystone: a writable path over the SAME session must succeed (write plane OK).
    marker = "I4_OK_" + uuid.uuid4().hex[:8]
    _, parsed = _call(
        cid, _file_tool_body("create_file", {"path": f"/tmp/{marker}.txt", "file_text": marker})
    )
    text, is_error = _result(parsed)
    assert is_error is False and text and "Successfully created" in text, (
        f"a writable /tmp path must succeed (keystone — write plane not broken), got {text!r}"
    )


# ---------------------------------------------------------------------------
# I5 — one chat maps to one PERSISTENT workspace across tool calls
# ---------------------------------------------------------------------------

def test_i5_workspace_persists_across_calls_in_one_session():
    """Call 1 writes a marker file; call 2 in the SAME chat reads it back. Proves
    the session maps to ONE persistent container, not a fresh one per exec. The
    keystone: a DIFFERENT chat id does NOT see the marker — persistence is
    per-session, not a shared global filesystem. This is sh-only (no python3),
    provable on the default guest — the highest-value single property here."""
    cid = _cid("i5")
    marker = "I5_PERSIST_" + uuid.uuid4().hex[:12]

    # call 1 — write the marker.
    _, parsed = _call(cid, _bash_body(f"echo {marker} > /tmp/i5_probe.txt && echo wrote"))
    text, is_error = _result(parsed)
    assert is_error is False and text and "wrote" in text, (
        f"call 1 must write the marker file, got {text!r}"
    )

    # call 2 — same chat reads it back.
    _, parsed = _call(cid, _bash_body("cat /tmp/i5_probe.txt"))
    text, is_error = _result(parsed)
    assert is_error is False and text and marker in text, (
        f"call 2 in the SAME session must see the marker call 1 wrote (workspace persisted), "
        f"got {text!r}"
    )

    # keystone: a DIFFERENT chat must NOT see the marker (per-session isolation).
    other = _cid("i5-other")
    _, parsed = _call(other, _bash_body("cat /tmp/i5_probe.txt 2>&1 || true"))
    text, _ = _result(parsed)
    assert text is None or marker not in text, (
        f"a DIFFERENT chat must NOT see another session's file (keystone — per-session, "
        f"not shared global fs), got {text!r}"
    )


# ---------------------------------------------------------------------------
# I6 — the four tools compose over one workspace (the owner-shown journey)
# ---------------------------------------------------------------------------

def test_i6_four_tools_compose_over_one_workspace():
    """create_file writes a file, view shows it, str_replace edits it, bash_tool
    cats it — all over ONE session. The full owner-shown journey. Requires a
    python3-bearing guest (#122); skips loudly on a stripped guest rather than
    passing vacuously. No tool may fall back to bash for a file operation."""
    probe_cid = _cid("i6-probe")
    if not _guest_has_python3(probe_cid):
        pytest.skip(
            "the four-tool journey needs a python3-bearing guest (#122); the default "
            "guest is stripped — SKIP, not a pass."
        )
    cid = _cid("i6")
    path = "/tmp/i6_journey.txt"

    # 1) create_file — ALPHA original
    _, parsed = _call(cid, _file_tool_body("create_file", {"path": path, "file_text": "ALPHA original\n"}))
    text, is_error = _result(parsed)
    assert is_error is False and text and "Successfully created" in text, (
        f"create_file must write the file, got {text!r}"
    )

    # 2) view — shows the file with line numbers
    _, parsed = _call(cid, _file_tool_body("view", {"path": path}))
    text, is_error = _result(parsed)
    assert is_error is False and text and "ALPHA original" in text, (
        f"view must show the created file, got {text!r}"
    )

    # 3) str_replace — original -> EDITED
    _, parsed = _call(
        cid, _file_tool_body("str_replace", {"path": path, "old_str": "original", "new_str": "EDITED"})
    )
    text, is_error = _result(parsed)
    assert is_error is False and text and "Successfully replaced" in text, (
        f"str_replace must edit the file, got {text!r}"
    )

    # 4) bash_tool — cat confirms the edited content over the SAME workspace
    _, parsed = _call(cid, _bash_body(f"cat {path}"))
    text, is_error = _result(parsed)
    assert is_error is False and text and "ALPHA EDITED" in text, (
        f"bash cat must confirm the edit persisted across all four tools, got {text!r}"
    )
