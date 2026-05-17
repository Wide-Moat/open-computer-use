<!-- SPDX-License-Identifier: BUSL-1.1 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# 05 — Layer 1: Guest Agent

> The PID 1 process inside every sandbox. Today: Python entrypoint + in-image MCP server. Future: small Go static binary (Phase 7).
> Language decision: **Go** ([ADR-0002](../adr/0002-guest-agent-language-go.md)).

## Contract (target)

The agent serves **connect-go** (gRPC + Connect + HTTP/JSON from one `.proto`) on vsock (microVM) or TCP (runc/sysbox/gVisor). It is **never** publicly reachable — only L3 (provider) talks to it. See [ADR-0008](../adr/0008-internal-grpc-external-rest-mcp.md) for the transport decision.

```proto
service Agent {
  rpc Health    (HealthRequest)       returns (HealthResponse);
  rpc Configure (ConfigureRequest)    returns (ConfigureResponse);  // inject session ctx, env, egress JWT
  rpc Exec      (ExecRequest)         returns (stream ExecChunk);   // streaming stdout/stderr/exit
  rpc Upload    (stream UploadChunk)  returns (UploadResponse);
  rpc Download  (DownloadRequest)     returns (stream DownloadChunk);
  rpc Signal    (SignalRequest)       returns (SignalResponse);     // SIGINT / SIGTERM / SIGKILL
  rpc Shutdown  (ShutdownRequest)     returns (ShutdownResponse);   // drop caches → SIGTERM → wait → SIGKILL
  rpc ToolCall  (ToolCallRequest)     returns (stream ToolChunk);   // MCP-tool semantics translated by L4
}
```

**WebSocket passthroughs** sit alongside the connect-go service (not RPCs):
- `WS /v1/cdp` — bidirectional CDP proxy to local Chromium; L4 shovels frames opaquely.
- `WS /v1/tty` — ttyd-equivalent terminal stream.

The agent **does not** speak MCP. MCP semantics live in L4's gateway. L4 receives `tools/call` from the user, decides which sandbox owns the session, and calls `Agent.ToolCall` over connect-go. This keeps the user-facing wire (MCP) decoupled from internal RPC evolution.

## What L1 does NOT do

- **Authenticate users.** L4 does. L1 trusts whoever can reach its port (network policy ensures only L3 can).
- **Persist state across sessions.** L3 owns the sandbox lifecycle and any volume binding.
- **Manage its own lifecycle.** It runs until killed; L3 decides when.
- **Hold long-lived secrets.** Secrets arrive via `/v1/configure` (per-session, short-lived). Rotated by L4's secret broker. See [07-security.md](./07-security.md).

## Today's transitional L1 (Python entrypoint + MCP server in image)

The current image's entrypoint:
- Reads env vars
- Dynamically generates an MCP config
- Starts the MCP server (FastMCP) that the orchestrator talks to via `docker exec` and Docker streams

This works for the PoC and stays through Phases 1–6. It blocks two things:
- **microVM runtimes** — there's no vsock transport in the current setup.
- **Smaller, harder-to-RCE surface** — Python + Playwright + skills is a big attack surface inside the sandbox.

Phase 7 replaces this with the Go agent.

## Future Go agent — design notes

- **Static binary** built with `CGO_ENABLED=0`, multi-arch (`amd64` mandatory, `arm64` later).
- **PID 1 hygiene:** reap zombies, propagate signals, exit cleanly. Reference patterns: kata-agent (Rust) signal handling adapted to Go.
- **Transports:**
  - HTTP+WS on a fixed port (today's path)
  - vsock listener gated by build tag or runtime detection (kata/microVM only — Phase 9 unlocks this)
- **Process model:** spawn user commands as a child process group; stream stdout/stderr; track exit code. For long-running CDP/ttyd, keep persistent goroutines.
- **CDP proxy:** the agent runs Chromium locally and proxies CDP. Two options to evaluate in Phase 7 research:
  - Use [`chromedp`](https://github.com/chromedp/chromedp) (Go-native CDP client)
  - Raw WebSocket pass-through to Chromium's `/devtools/browser` endpoint
- **No HTTP auth.** Token-on-the-wire is meaningless in-sandbox — defense is network-policy-level (L3 owns it). Document this loudly; do NOT add a fake auth that lulls operators.

## Why Go (and why we keep Rust documented)

See [ADR-0002](../adr/0002-guest-agent-language-go.md). One-paragraph summary here:

- **For Go:** user preference; single language across L1+L4 simplifies on-call; chromedp gives mature CDP support; ecosystem already proven by `envd` and gVisor. Static binary cross-compiles cleanly.
- **What Rust would buy us:** ~half the binary size; stronger memory-safety guarantees against HTTP-parsing RCE (matters because L1 is the in-sandbox attack target); precedent from kata-agent and msb-agent. Door stays open — interfaces are language-agnostic.

## MCP tool execution inside L1

Today's tools (`mcp_tools.py`):
- `bash_tool` — exec in a shell
- `python_tool` — exec under python3
- `create_file` / `str_replace` / `view` — file ops
- `view_image` — return base64
- `sub_agent` — dispatch to claude / codex / opencode CLI

Phase 7 maps each to a Go handler. Sub-agent dispatch (`cli_runtime.dispatch()`) is the heaviest port — its current Python adapter layer for each CLI must be re-implemented. Acceptable cost: this is the place where most "sandbox business logic" lives, and Go keeps it auditable.

## Open questions (deferred to Phase 7 research)

- chromedp vs raw CDP WebSocket
- ttyd replacement vs wrap-in-place
- vsock listener strategy (build-tag, env-detection, or always-on with fallback)
- Whether to keep Python skills available via `python_tool` in the new image (yes — skills are an L1 capability bundle, not an L1 implementation language)

## Source

- [`sandboxd/docs/architecture.md`](../../../sandboxd/docs/architecture.md) (Layer 1)
- [`sandboxd/docs/agent-protocol.md`](../../../sandboxd/docs/agent-protocol.md)
- [`docs/future-architecture/references.md`](../references.md) (`envd`, `kata-agent`, `msb-agent`)
