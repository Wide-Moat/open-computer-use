<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# 05 — Layer 1: Guest Agent

> The PID 1 process inside every sandbox. Today: Python entrypoint + in-image MCP server. Future: small **Rust** static binary (Phase 7).
> Language decision: **Rust** ([ADR-0002](../adr/0002-guest-agent-language-go.md)). Closest precedent: Anthropic `process_api` — see [`research/19`](../research/19-anthropic-process-api.md).

## Contract (target)

The agent exposes **two ports**, on the model `process_api` validates:

1. **Data plane — WebSocket.** Bidirectional, JSON frames (serde-tagged enums), zstd compression optional via capabilities negotiation. Carries every per-session interaction: exec, streaming I/O, signal forwarding, CDP/ttyd passthrough. Transport is **auto-detected**, not build-tag-gated:
   - `vsock` if `/dev/vsock` is present (microVM tiers `kata-ch`, `kata-fc`).
   - `TCP` otherwise (runc, sysbox, gVisor, dev).
   - Same `handle_ws` accept loop drives both ([`research/19`](../research/19-anthropic-process-api.md) §2). Transport is operational, not architectural.
2. **Control plane — HTTP.** Stateless POSTs for actions that should not flow through the user-facing data plane. Separate listener, same binary:
   - `GET /healthz`, `GET /readyz` — liveness / readiness probes for L3.
   - `POST /shutdown` — graceful shutdown signal.
   - `POST /mount_root` — snapstart restore handshake. **Phase 10 only**, feature-gated until then.
   - `POST /fs_freeze`, `POST /fs_thaw` — `FIFREEZE` / `FITHAW` ioctl bridge for snapshot consistency. **Phase 10 only.**
   - `POST /auth_public_key` — hot-reload of the Ed25519 verification key. Optional, Phase 7+.

The L1 agent is **never** publicly reachable — only L3 (provider) talks to it. See [ADR-0008](../adr/0008-internal-grpc-external-rest-mcp.md) for transport positioning across tiers (and the Phase 7 gate on connect-rust vs. WS-frame protocol).

## RPC surface (data plane)

The methods below map to message variants on the WebSocket. The shape is sketched as a `.proto` for clarity, but the wire is **JSON frames + capabilities-negotiated V1/V2 variants**, not gRPC ([`research/19`](../research/19-anthropic-process-api.md) §4, §12).

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

**WebSocket passthroughs** are routed through a **sibling port by default** (one passthrough socket per stream), so the data-plane WS does not have to multiplex CDP / ttyd binary frames alongside `Agent.*` RPC frames. The same-port variant ("one socket per sandbox") stays available as an option if a future deployment needs to minimize listener count, but Phase 7 ships the sibling-port shape.

- `WS /v1/cdp` — bidirectional CDP proxy to local Chromium; L4 shovels frames opaquely.
- `WS /v1/tty` — ttyd-equivalent terminal stream.

The agent **does not** speak MCP. MCP semantics live in L4's gateway. L4 receives `tools/call` from the user, decides which sandbox owns the session, and calls `Agent.ToolCall`. This keeps the user-facing wire (MCP) decoupled from internal RPC evolution.

## Capabilities negotiation (V1/V2)

The server's first frame on each connection advertises capabilities, modelled on `process_api`'s `ConnectionCapabilities` ([`research/19`](../research/19-anthropic-process-api.md) §4):

```json
{
  "type": "ConnectionCapabilities",
  "supports_traces": true,
  "supports_zstd":   true,
  "protocol_version": 2
}
```

Old clients ignore unknown fields and stay on V1 message variants. New clients opt into V2, zstd compression on server-to-client frames, and trace events. This lets the agent protocol evolve without breaking older sandboxes still in flight.

## PID 1 hygiene (Phase 7 mandatory)

The agent is the init process inside the sandbox. These primitives are mandatory together — none of them works alone:

- **`SIGCHLD` reaping.** Wait on the signalfd or libc `signal()` and reap zombies. Without this, fork-heavy workloads (sub-agent CLIs, shell scripts) leak PIDs until cgroup limits trip.
- **`SIGTERM` propagation.** L3's `/shutdown` POST or a connect-side `Shutdown` RPC drains via: page-cache drop → SIGTERM to the workload process group → grace-period wait → SIGKILL escalation. The two-phase shape mirrors `process_api`'s OOM killer ([`research/19`](../research/19-anthropic-process-api.md) §7).
- **`PR_SET_DUMPABLE=0` post-init.** Disables core dumps and blocks `/proc/<pid>/mem` reads from other processes — even from inside the same UID. Cheap, prevents an entire class of "ptrace the agent to steal session JWT" attacks ([`research/13`](../research/13-anthropic-sandbox-runtime.md) §4 two-stage nested-namespace pattern).
- **`killed_by_process_api`-style audit flag.** A per-child boolean that distinguishes "agent killed this" (timeout, OOM, signal RPC) from "kernel killed this" (cgroup OOM, external SIGKILL). Removes ambiguity from the audit log without parsing exit codes ([`research/19`](../research/19-anthropic-process-api.md) §6).
- **Env-var scrub before fork.** Strip names matching `_TOKEN`, `_SECRET`, `_PASSWORD`, `API_KEY` from the child env unless the configure-time policy explicitly passes them through. Cross-link to [antipattern A1].

## What L1 does NOT do

- **Authenticate users.** L4 does. L1 trusts whoever can reach its port — network policy ensures only L3 can.
- **Authenticate L3 — for now.** Phase 7+ may add **Ed25519 JWT bound to `container_name`** read from `/container_info.json`, modelled on `process_api` ([`research/19`](../research/19-anthropic-process-api.md) §3). Pre-Phase-7+ the network boundary alone is the trust boundary. **Document this loudly; do NOT add a fake bearer token that lulls operators.**
- **Persist state across sessions.** L3 owns the sandbox lifecycle and any volume binding.
- **Manage its own lifecycle.** It runs until killed; L3 decides when.
- **Hold long-lived secrets.** Secrets arrive via `Configure` (per-session, short-lived). Rotated by L4's secret broker. See [07-security.md](./07-security.md).

## Today's transitional L1 (Python entrypoint + MCP server in image)

The current image's entrypoint:
- Reads env vars.
- Dynamically generates an MCP config.
- Starts the MCP server (FastMCP) that the orchestrator talks to via `docker exec` and Docker streams.

This works for the PoC and stays through Phases 1–6. It blocks two things:
- **microVM runtimes** — no vsock transport in the current setup.
- **Smaller, harder-to-RCE surface** — Python + Playwright + skills is a big attack surface inside the sandbox.

Phase 7 replaces this with the Rust agent.

## Future Rust agent — design notes

- **Static-PIE binary**, `musl` target, x86-64 + arm64. Target size ~4–6 MB (precedent: `process_api` 4.3 MB, [`research/19`](../research/19-anthropic-process-api.md) §1).
- **Crate footprint** ([ADR-0002](../adr/0002-guest-agent-language-go.md)): `tokio`, `hyper`, `tokio-tungstenite`, `tokio-vsock`, `ring`, `jsonwebtoken`, `clap`, `nix`, `serde_json`. Optional `zstd` if capabilities negotiation enables it. No `chromedp` equivalent — see CDP note below.
- **PID 1 hygiene** as above (`SIGCHLD`, `SIGTERM`/`SIGKILL` chain, `PR_SET_DUMPABLE=0`, env-scrub).
- **Process model:** spawn workloads as child process groups; stream stdout/stderr as `ExpectStdOut`/`ExpectStdErr` frames; track exit code; emit `ProcessExited` / `ProcessTimedOut` / `ProcessOutOfMemory` terminal states (mutually exclusive, modelled on [`research/19`](../research/19-anthropic-process-api.md) §6).
- **Cgroup-aware OOM monitor.** Per-container OOM watchdog polls cgroup memory at 100 ms; adopts orphans before scanning; two-phase kill (signal → wait → escalate). Replaces our current reliance on Docker's default OOM policy.
- **CDP proxy.** Two options for Phase 7 research:
  - Use [`chromiumoxide`](https://github.com/mattsse/chromiumoxide) (Rust-native CDP client) and let L1 drive Chromium.
  - **Raw WebSocket pass-through** to Chromium's `/devtools/browser` endpoint — L4 (and L1) never parse CDP frames. Simpler, smaller agent. Aligns with ADR-0008's "L4 shovels frames opaquely" stance.
- **MCP tool execution.** A small dispatch layer above the data-plane WS — see "MCP tool execution inside L1" below.
- **No HTTP bearer auth on the data plane** until Phase 7+ Ed25519 JWT lands. Network policy is the trust boundary in the meantime.

## MCP tool execution inside L1

Today's tools (`mcp_tools.py`):
- `bash_tool` — exec in a shell.
- `python_tool` — exec under python3.
- `create_file` / `str_replace` / `view` — file ops.
- `view_image` — return base64.
- `sub_agent` — dispatch to claude / codex / opencode CLI.

Phase 7 maps each to a Rust handler reachable via `Agent.ToolCall`. Sub-agent dispatch (`cli_runtime.dispatch()`) is the heaviest port — its current Python adapter layer per CLI must be re-implemented. Acceptable cost: this is where most "sandbox business logic" lives, and the new home is auditable.

The agent itself does not need to know what's in `skills/`. Skills are mounted as a Tier-2 squashfs and discovered at runtime by the workload, not by L1 ([06-storage.md](./06-storage.md)).

## Open questions (Phase 7 research must answer)

- `chromiumoxide` vs raw CDP WebSocket passthrough — pick one, justify, document.
- ttyd replacement (Rust-native) vs wrap-in-place (run ttyd as a subprocess and proxy its WS).
- Transport auto-detect details: presence of `/dev/vsock` plus configure-time hint, or a CLI flag with a sensible default — Phase 7 picks the rule.
- Connect-rust vs `process_api`-style WS-frame protocol on vsock ([ADR-0008](../adr/0008-internal-grpc-external-rest-mcp.md) Phase 7 gate). Driven by tooling maturity and binary-size measurement on real artefacts.
- Whether Phase 7 ships JWT auth on day one, or starts network-only and adds JWT in Phase 7.1. Default leans toward the latter — small surfaces first.

## Related

- ADR: [ADR-0002](../adr/0002-guest-agent-language-go.md) (Rust for L1), [ADR-0008](../adr/0008-internal-grpc-external-rest-mcp.md) (transport choice + Phase 7 gate), [ADR-0010](../adr/0010-lambda-as-inspiration-not-runtime.md) (Lambda framing).
- Research: [`research/19-anthropic-process-api.md`](../research/19-anthropic-process-api.md) (primary precedent), [`research/13-anthropic-sandbox-runtime.md`](../research/13-anthropic-sandbox-runtime.md) (PID 1 + nested-ns hardening), [`research/02-e2b-infra.md`](../research/02-e2b-infra.md) (`envd` comparison).
- Antipatterns: A1 (secret leakage in env), and the deny-paths list (`.git/hooks/*`, `.bashrc`, `.mcp.json`, `.claude/`) enforced via [`07-security.md`](./07-security.md).

## Source

- [`sandboxd/docs/architecture.md`](../../../sandboxd/docs/architecture.md) (Layer 1).
- [`sandboxd/docs/agent-protocol.md`](../../../sandboxd/docs/agent-protocol.md).
- [`sandboxd/anthropic/`](../../../sandboxd/anthropic/) — `process_api` pattern catalogue (closest documented precedent).
