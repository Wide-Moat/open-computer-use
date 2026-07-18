# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""GROUP M journeys: the eyes-in-browser PoC-parity cycle (Fable ruling ae7daf88).

The owner's parity bar is the FULL browser cycle, not wire probes: a file the
model creates RENDERS in the OpenWebUI pane preview, a chat upload reaches the
guest, and skills fire and produce an artifact. Groups A-L drive the wire with
curl; this group drives a REAL browser (Playwright) against the embed-portal
(127.0.0.1:3003) which frames the File Pane BFF (127.0.0.1:3000). A browser is
required because the pane's authed calls need both a Secure session cookie and
the x-ocu-chat-scope header, which the pane's own client sends and curl cannot
replay.

Anti-vacuity (this suite lied by skipping before): these tests are GATED on
OCU_BROWSER_E2E=1. When the gate is SET, a missing Playwright / chromium is a
FAIL, not a skip -- skip == NOT-RUN is exactly the hole. When the gate is
unset, they skip loudly (the browser rig is opt-in, run in the VM jvenv).

  M1 (P-A): exec writes a PNG of known dimensions to /mnt/user-data/outputs ->
            pane preview renders an <img> whose naturalWidth/Height match.
            Red-probe: NEXT_PUBLIC_PREVIEW_RENDER_ENABLED OFF -> no <img>.
  M2 (P-B): Playwright drives the real chat file input (set_input_files, not the
            upload API) -> the guest reads the exact bytes at uploads/<name>.
            Red-probe: upload under a different chat scope -> guest must NOT see.
  M3 (P-C): guest runs a /mnt/skills toolchain -> artifact in outputs -> pane
            lists + previews it. Red-probe: skill dir absent -> RED.
  M4 (KEYSTONE): live model -> prompt -> tool call -> file -> preview, eyes-in-
            browser. Parity is NOT done until M4 runs firsthand once.
"""

import os
import subprocess
import time
import uuid

import pytest

PORTAL_URL = "http://127.0.0.1:3003"
PANE_FRAME_URL = "127.0.0.1:3000"

pytestmark = pytest.mark.fleet

_BROWSER_GATE = os.getenv("OCU_BROWSER_E2E", "") in ("1", "true", "yes", "on")


def _require_browser():
    """Gate + anti-vacuity: gate-set-but-no-chromium is a FAIL, not a skip."""
    if not _BROWSER_GATE:
        pytest.skip(
            "OCU_BROWSER_E2E not set: the eyes-in-browser M-group is opt-in "
            "(run in the VM jvenv with playwright+chromium). LOUD SKIP."
        )
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError as exc:
        pytest.fail(
            "OCU_BROWSER_E2E is SET but playwright is not importable: "
            f"{exc}. A missing browser under the gate is a FAILURE, not a "
            "skip (skip == NOT-RUN is how this suite lied before). "
            "Install: /tmp/jvenv/bin/pip install playwright && "
            "/tmp/jvenv/bin/python -m playwright install chromium."
        )


def _guest_exec(chat_id, command, timeout=90):
    """Run a bash command in the guest via the gateway wire (from test_i)."""
    from test_i_mcp_surface import _bash_body, _call  # same wire

    status, parsed = _call(chat_id, _bash_body(command), timeout=timeout)
    from test_i_mcp_surface import _result

    text, is_error = _result(parsed)
    return status, text, is_error


def _portal_reachable():
    try:
        out = subprocess.run(
            ["curl", "-sS", "--max-time", "8", "-o", "/dev/null",
             "-w", "%{http_code}", PORTAL_URL + "/"],
            capture_output=True, text=True, timeout=12,
        )
        return out.stdout.strip() == "200"
    except (OSError, subprocess.SubprocessError):
        return False


# ---------------------------------------------------------------------------
# M1 -- a model-written image renders in the pane preview (P-A)
# ---------------------------------------------------------------------------

def test_m1_agent_image_renders_in_pane_preview():
    """P-A: an image written to outputs renders as an <img> in the pane preview
    with the file's real pixel dimensions -- not just a 200 on the content URL
    (that is a download, not a preview). Requires the #218 slice built with
    NEXT_PUBLIC_PREVIEW_RENDER_ENABLED=true.
    """
    _require_browser()
    if not _portal_reachable():
        pytest.fail(
            "OCU_BROWSER_E2E set but embed-portal :3003 is unreachable -- the "
            "user leg cannot run; a down portal under the gate is a FAILURE."
        )
    from playwright.sync_api import sync_playwright

    # 1. The guest writes a PNG of KNOWN dimensions (poc-fat has PIL).
    chat_id = f"m1-{uuid.uuid4().hex[:8]}"
    name = f"m1-{uuid.uuid4().hex[:8]}.png"
    W, H = 123, 45
    status, text, is_error = _guest_exec(
        chat_id,
        f"python3 -c \"from PIL import Image; "
        f"Image.new('RGB',({W},{H}),(10,20,30)).save('/mnt/user-data/outputs/{name}')\" "
        f"&& echo WROTE",
        timeout=120,
    )
    assert status == 200 and not is_error and text and "WROTE" in text, (
        f"guest PNG write failed: status={status} err={is_error} text={text!r}"
    )

    # 2. Drive a real browser: portal frames the pane; open the file's preview.
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(PORTAL_URL, wait_until="networkidle", timeout=30000)
            frame = next(
                (f for f in page.frames if PANE_FRAME_URL in (f.url or "")), None
            )
            assert frame is not None, "pane iframe (127.0.0.1:3000) not found in portal"
            # Wait for the file row, then activate its preview affordance.
            frame.wait_for_selector(f"text={name}", timeout=45000)
            preview_btn = frame.locator(f"[aria-label='Preview {name}']")
            assert preview_btn.count() > 0, (
                "no Preview affordance for the file -- the #218 slice flag is "
                "likely OFF in this webui image (build with "
                "NEXT_PUBLIC_PREVIEW_RENDER_ENABLED=true)"
            )
            preview_btn.first.click()
            img = frame.locator("[data-testid='file-preview-image']")
            img.wait_for(state="visible", timeout=20000)
            nat_w = img.evaluate("el => el.naturalWidth")
            nat_h = img.evaluate("el => el.naturalHeight")
            assert (nat_w, nat_h) == (W, H), (
                f"preview <img> rendered {nat_w}x{nat_h}, expected {W}x{H} -- "
                "the image did not truly paint (P-A parity)"
            )
        finally:
            browser.close()


# ---------------------------------------------------------------------------
# M2/M3/M4 -- authored next, once M1 is green against the built image.
# ---------------------------------------------------------------------------

@pytest.mark.skip(reason="M2 (chat-upload UI leg) authored after M1 is green against the built webui image")
def test_m2_chat_upload_reaches_guest():
    ...


@pytest.mark.skip(reason="M3 (skills fire + artifact) authored after M1/M2")
def test_m3_skill_fires_and_artifact_previews():
    ...


@pytest.mark.skip(reason="M4 keystone (live model -> file -> preview) needs a model endpoint; authored last")
def test_m4_live_model_file_preview_keystone():
    ...
