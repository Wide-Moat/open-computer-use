<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# 14 — e2b/desktop + e2b/surf (full-desktop vs CDP-direct)

> Source: [`references/desktop/`](../../../references/desktop/) and [`references/surf/`](../../../references/surf/).
> Decision point for Phase 7: evolve toward Xfce/VNC or stay CDP-direct?

**Verdict: stay CDP-direct.** Details below.

## 1. Desktop — Xvfb + Xfce4 + resolution

- **Where.** `packages/python-sdk/e2b_desktop/main.py:263-277` (`Sandbox.create`).
- **What.** Xvfb at `1024x768`, DPI 96, display `:0`. `startxfce4` background. Liveness via `xdpyinfo`.
- **Cost for us.** Full WM + panels + desktop icons we never render. Adds ~700 MB image + ~200 MB RAM per sandbox.
- **Skip.** CDP-direct doesn't need any of this.

## 2. Desktop — VNC + noVNC over WebSocket

- **Where.** `e2b_desktop/main.py:84-202` (`_VNCServer`).
- **What.** `x11vnc` on 5900 (RFB), `noVNC` (WebSocket wrapper) on 6080 over HTTPS. Optional password.
- **Trade-off.** VNC is low-latency for humans; **high-bandwidth for rapid AI actions** (full-screen re-encode per frame). noVNC adds 100–200 ms.
- **For us.** Headless agent ≠ human viewer → skip VNC. Chromium CDP screencast (binary frames, 30–60 fps) is cheaper. Surf uses VNC purely for **developer observation**, not the agent control path.

## 3. Desktop — `xdotool` input (X11 events)

- **Where.** `e2b_desktop/main.py:424-488`.
- **What.** `xdotool mousemove`, `xdotool click`, `xdotool key`, `xdotool type --delay`. Pixel coords. Screen size via `xrandr`.
- **Limitation.** Pure visual grounding — no OCR, no DOM. Agent must parse the screenshot.
- **For us.** CDP path unlocks **DOM queries** (`document.evaluate`, element bounding boxes). Far more reliable than visual coord guessing.

## 4. Desktop — screenshot via `scrot` to disk

- **Where.** `e2b_desktop/main.py:406-422`.
- **What.** `scrot --pointer` → PNG to disk → SDK reads → SDK deletes. ~50–100 ms roundtrip.
- **For us.** CDP `Page.captureScreenshot` is async, batched with actions, no disk I/O. CDP wins.

## 5. Surf — action loop pattern

- **Where.** `lib/streaming/openai.ts:336-575` (`stream()` async generator).
- **Loop.**
  1. Screenshot → base64.
  2. POST to OpenAI with `tools: [{ type: "computer" }]` (OpenAI's Computer tool).
  3. Response: structured `output[]` with `computer_call` items, each containing batched `actions[]`.
  4. Execute actions sequentially (click/type/scroll/…) via desktop SDK.
  5. Capture screenshot after batch (with configurable fallback delay for async DOM).
  6. Feed screenshot + reasoning into next iteration (context reset per turn).
  7. **Bail** when no more `computer_call` returned.
- **For us.** **Adopt this loop in Phase 7.** Same shape for Claude Computer Use. Not bespoke — OpenAI codified it.

## 6. Surf — coordinates + safety

- **Where.** `lib/streaming/openai.ts:267-334` (`executeAction`); `types/openai.ts`.
- **Actions.** `click(x, y, button)`, `type(text)`, `scroll(x, y, dx, dy)`, `drag(path: [{x,y}, ...])`, `keypress(keys: string[])`, `wait(ms)`.
- **Footguns Surf ignores.**
  - **No coordinate-bounds validation.** Agent picks (10000, 10000) → silent fail or Chromium crash.
  - **Chunked typing** (`chunkSize=50`, `delayMs=25`) **required** for terminal input buffers.
  - **Trailing wait deferred.** If last actions are `wait`, bundle into screenshot capture delay instead of sleeping.
- **For us.** Phase 7 — **add coordinate clipping** (validate within viewport). Adopt chunked typing for our `terminal_type` tool.

## 7. Surf — async settle delay

- **Where.** `lib/streaming/openai.ts:171-189, 232-265` (`shouldApplyFallbackDelay`, `captureBatchScreenshot`).
- **What.** If a batch contains `click`/`scroll`/`drag` or async keypresses (Enter/Tab/Escape) → wait 100 ms before screenshot. DOM may not settle immediately.
- **For us.** CDP has the same issue. `Page.captureScreenshot` right after a click can capture stale layout. **Always insert a small post-batch delay** (configurable per action type). Document the latency trade-off.

## 8. Surf — SSE streaming UI

- **Where.** `app/api/chat/route.ts:12-91`; `lib/streaming/index.ts`.
- **Events.** `SANDBOX_CREATED`, `REASONING`, `ACTION`, `ACTION_COMPLETED`, `SCREENSHOT`, `ERROR`, `DONE`.
- **Lazy sandbox.** Created on first message; reused for conversation.
- **No multi-turn memory** — each OpenAI call independent.
- **For us.** SSE is clean for developer/admin observation surfaces. For Phase 7 headless agent, log locally or stream via our own L4 channel.

## 9. Desktop image — `template/template.py:1-128`

- **Stack.** Ubuntu 22.04 + Xorg + Xvfb + xauth + xdotool + scrot + Xfce4 + x11vnc + noVNC + websockify + Firefox + Chrome + VS Code + LibreOffice + gedit + pcmanfm.
- **Image size.** ~2–3 GiB uncompressed. Startup: 10–20 s.
- **Our path.** Chromium alone: 200–300 MiB. No WM, no panels. Faster spawn, cheaper RAM, lower screenshot latency.

## 10. Comparison table

| Dimension | E2B Desktop + Surf | Our CDP-direct (Phase 7) |
|---|---|---|
| Display backend | Xvfb (X11) + Xfce4 | Chromium `--disable-gpu` / headless |
| Screenshot | scrot → disk; poll ~10 Hz | CDP `Page.captureScreenshot` / screencast; up to 60 Hz |
| Input | xdotool (X11 events, pixel coords) | CDP `Input.dispatchMouseEvent` (CSS pixels) |
| Action→shot latency | ~150–250 ms | ~50–100 ms |
| Coord origin | Screen pixels | Viewport CSS pixels (supports scroll offset) |
| DOM access | None | Full (`document.evaluate`, element boxes) |
| Multi-app | Yes (any X11 app) | Browser-only (terminal via separate MCP tool) |
| Sandbox startup | 10–20 s | 2–5 s |
| Sandbox image | 2–3 GiB | 300–500 MiB |
| Agent reliability | Visual + OCR risk | Semantic (DOM) + visual fallback |

## Verdict for Phase 7

1. **Stay CDP-direct.** VNC/Xfce overhead is not justified for first Computer Use agent. Browser is the primary target; terminal tasks handled by separate MCP tool.
2. **Screenshot strategy.** `Page.startScreencast` for live frames (30–60 fps); `captureScreenshot` for explicit "pause and analyze". Surf only polls — we can do better.
3. **Input primitives.** Adopt Surf's schema (`click`/`type`/`scroll`/`keypress`/`drag`/`wait`). Add coord validation + DOM-query layer (CDP `Runtime.evaluate`).
4. **Async settle.** Insert 100–150 ms delay after action batches containing clicks/scrolls/async keys.
5. **Error recovery.** Not in Surf — we add retry + Chromium restart on CDP connection loss.
6. **Multi-turn memory.** Surf resets per turn. We consider lightweight session state (screenshot/action history) for coherent long-form tasks.

## When to revisit

If we ever need **multi-app Computer Use** (e.g., AI agent that switches between browser + VS Code + terminal in the same display) → revisit Xfce/VNC. For now, single-app + separate tool channels keeps the stack lean.
