<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# 07 — chromedp (Go direct-CDP client)

> Source: [`references/chromedp/`](../../../references/chromedp/).
> Candidate for Phase 7 (Go guest agent — drives Chromium in-sandbox) and Phase 6 (L4 — tunnels CDP frames from user UI to sandbox).

## 1. CDP transport — single WebSocket, session-multiplexed

- **Where.** `conn.go:42-142`.
- **What.** One WebSocket per browser (`gobwas/ws`), JSON marshalling with reused encoder/decoder buffers. Session ID multiplexing handles multi-tab.
- **Constraint.** Chrome doesn't support frame fragmentation; single frame max 100 MiB.
- **Why for us.** Phase 7 — efficient single-conn model exactly matches our agent's "one Chromium, many targets".

## 2. Action / task model — minimal `Action` interface

- **Where.** `chromedp.go:718-743`.
- **What.** `type Action interface { Do(context.Context) error }`. Executor bound via context value. `Tasks` is `[]Action` — trivially composable for sequential workflows.
- **Why for us.** Phase 7 — sub-agent flows (login → navigate → click → screenshot) are sequential `Tasks`. No DSL invention needed.

## 3. Event subscriptions — synchronous, context-scoped

- **Where.** `chromedp.go:786-836`.
- **What.** `ListenTarget`, `ListenBrowser` — callbacks invoked synchronously per event. Cancellation tied to ctx.
- **Footgun.** Blocking I/O inside a listener **deadlocks the CDP loop**. Listeners must be fast-and-async (channel-send only).
- **Why for us.** Phase 7. Document the non-blocking rule in our agent codebase loudly.

## 4. Screenshot — pull-based; live screencast = raw CDP

- **Where.** `screenshot.go:106-162`.
- **What.** `CaptureScreenshot` is on-demand. For ≥10 fps live streaming, **chromedp doesn't help directly** — call `Page.startScreencast` via raw CDP commands and subscribe to `Page.screencastFrame`.
- **Why for us.** Phase 7. For Computer Use we need the screencast path — chromedp gives us the wire (CDP target, message routing) but the screencast loop is custom.

## 5. Input synthesis — clicks, keys, scroll

- **Where.** `input.go:28-94, 166-192`.
- **What.** Mouse clicks at coords or DOM nodes; keyboard via key encoding; viewport scroll honors device pixel ratio and modifiers.
- **Why for us.** Phase 7. Direct fit for Computer Use action-injection — saves us writing our own CDP `Input.dispatchMouseEvent` wrappers.

## 6. Browser lifecycle — pluggable Allocator

- **Where.** `allocate.go`, `chromedp.go:122-220`.
- **What.** `Allocator` interface abstracts launching. `ExecAllocator` runs a local Chromium process. **Context ownership rule:** cancel parent → close browser; cancel child → close tab only. Multi-tab via context inheritance.
- **Why for us.** Phase 7 — we own Chromium launch flags (sandbox off inside microVM, screencast on). Allocator pattern keeps that clean.

## 7. Pooling & routing — single conn, session-mux

- **Where.** `browser.go:38-90, 269-337`.
- **What.** One conn per browser; messages routed by session-ID. Sufficient for "one browser per sandbox" — our case.
- **Why for us.** Phase 7 = direct fit. Phase 6 = **NOT directly usable** because L4 multiplexes many users' CDP across many sandboxes — that's a gateway, not a chromedp use case.

## 8. Errors & cancellation — context-driven

- **Where.** `errors.go`, `browser.go:182-240`.
- **What.** Small set of domain-specific errors. Cancellation via standard ctx. **No built-in retry, no transparent reconnect.**
- **Why for us.** Phase 7 — wrap with our own retry + reconnect for crashed-Chromium recovery.

## 9. Trade-off vs raw CDP

- **chromedp wins.** Action composition, input synthesis, multi-tab management, browser lifecycle.
- **Raw CDP wins.** Screencast streaming, custom Target subscription, lowest-latency frame paths, smaller dependency footprint.
- **Verdict for Phase 7.** Use **chromedp for control** (clicks, navigate, screenshots, DOM); use **raw CDP for screencast** (`Page.startScreencast` directly on the WS). chromedp exposes the conn for this hybrid use.
- **Verdict for Phase 6.** Don't use chromedp in L4. L4 is a CDP **proxy** — it shouldn't parse CDP messages, just shovel WebSocket frames.

## Phase-7 implementation checklist

1. `chromedp.NewContext(parent)` — one per sandbox session.
2. Launch flags: `--no-sandbox` (we are inside microVM), `--remote-debugging-port=...` (or use chromedp's own allocator).
3. Action composition for `bash`/`python`/`view`/`click`/`type` MCP tools.
4. **Custom screencast loop** — bypass chromedp Action API; subscribe to `Page.screencastFrame` events; forward binary to caller over WS at `/v1/cdp` or `/v1/screencast`.
5. Listener discipline — channel-send only, no blocking I/O.
6. Restart logic — chromedp gives none; we add reconnect + Chromium relaunch on crash.

## Verdict

- **Phase 7 agent:** adopt for control plane (clicks/navigate/etc); raw CDP for screencast.
- **Phase 6 L4:** skip — use opaque WS proxy.
