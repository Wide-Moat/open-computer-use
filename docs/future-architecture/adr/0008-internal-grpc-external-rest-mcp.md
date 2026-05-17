<!-- SPDX-License-Identifier: BUSL-1.1 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# ADR-0008 — Internal transport: connect-go (gRPC). External: MCP + REST. CDP/ttyd: WebSocket passthrough.

- **Status:** Accepted
- **Date:** 2026-05-17
- **Related:** [ADR-0001](./0001-control-plane-language-go.md), [ADR-0002](./0002-guest-agent-language-go.md), [ADR-0005](./0005-mcp-as-control-plane-gateway.md)

## Context

The architecture has three transport boundaries that are too easy to conflate:

1. **External, user-facing** — user agents and Open WebUI call us.
2. **External, operator-facing** — admin UI calls us.
3. **Internal** — L4 ↔ L3 ↔ L1.
4. **External, opaque passthrough** — CDP frames and ttyd between user UI and the sandbox's Chromium.

Until now docs said "HTTP/gRPC" everywhere — ambiguous. The Anthropic pattern in `sandboxd` #2 ("HTTP+WS API") was written about their *user-facing* `process_api`; we copied it without noting that for us L1 is internal, not user-facing. Different decomposition → different transport choice.

## Decision

| Boundary | Protocol | Rationale |
|---|---|---|
| User → L4 (agents, Open WebUI) | **MCP** (JSON-RPC over HTTP/WebSocket) | Frozen contract per [ADR-0005](./0005-mcp-as-control-plane-gateway.md) |
| Admin UI → L4 | **REST** (OpenAPI-described) | Standard for SPAs, generates browser clients trivially, debuggable via curl/Postman |
| L4 ↔ L3 (provider) | **connect-go** (mTLS) | Schema-first; gRPC streaming + Connect/HTTP-JSON from one `.proto` |
| L3 ↔ L1 (agent) | **connect-go** (vsock on microVM, TCP on runc/sysbox) | Same `.proto` shape; transport-agnostic |
| User UI ↔ sandbox CDP/ttyd | **WebSocket passthrough** via L4 | L4 does **not** parse; shovels frames opaquely |

**connect-go** specifically (not pure grpc-go):
- Single server speaks **gRPC**, **Connect** (HTTP/2 framed), and **gRPC-Web** from one `.proto`.
- HTTP/JSON variant lets us `curl` any internal RPC for debug, no `grpcurl` required.
- Bidi streaming preserved.
- Used by E2B's `envd` and by Connect's own production users.

## What MCP looks like inside

MCP wire format stays **opaque to L1**. L4 receives MCP JSON-RPC → translates to typed `connect-go` calls on L3 → L3 calls L1's `Exec(cmd, env, stdin) → stream<Output>` etc.

Consequence: MCP semantics live **only** in L4 gateway. We can:
- Change internal RPCs without touching the MCP contract.
- Add a second user-facing protocol (e.g., direct gRPC API for power users) without rewriting internals.
- Swap L1 implementations without MCP-side test changes.

## CDP and ttyd are the exception

Long-lived WebSocket from user UI → L4 → sandbox Chromium. L4 must **not** decode CDP messages — It consistent-hashes the session ID to a sandbox pod and shovels frames in both directions. Reasons:

- CDP messages are large (screencast binary frames) — parsing adds latency and zero value.
- Schema is upstream-owned (Chrome team) — keeping us out of it = no version-lock.
- Same shape applies to ttyd.

## Alternatives considered

### Pure grpc-go (no Connect)
- **Pro:** Most "standard" gRPC stack.
- **Con:** No HTTP/JSON debug path; needs `grpcurl`. Browser clients require gRPC-Web sidecar (Envoy/Connect anyway).
- **Verdict:** Rejected. connect-go is a superset.

### HTTP+WS everywhere (status quo, Anthropic-style for L1)
- **Pro:** Simpler tooling; works with stdlib.
- **Con:** No schema enforcement; breaking changes hit at runtime. Bidi streaming via WebSocket is hand-rolled framing. Type safety lost across L4↔L3↔L1.
- **Verdict:** Rejected for internal boundaries.

### REST everywhere
- **Pro:** Maximum debuggability.
- **Con:** Streaming exec / events / metrics over REST is awkward (SSE works but is one-direction). Schemas via OpenAPI possible but weaker than `.proto` in our experience.
- **Verdict:** Rejected for L4↔L3↔L1. Kept for admin UI.

### gRPC + gRPC-Web (no Connect)
- **Pro:** Standard.
- **Con:** Needs Envoy or grpc-web translator. connect-go does this in-process.
- **Verdict:** Rejected.

## Consequences

**Positive:**
- One `.proto` per boundary; CI compiles it for both sides; breaking changes caught at build time.
- Same Go server serves gRPC, Connect, and `curl` calls — no separate debug stack.
- L1's agent contract becomes typed → cross-tier consistency (sysbox / gVisor / kata all serve same `.proto`).
- MCP contract isolation → internal refactors don't risk the user-facing wire.

**Negative:**
- One more tool in the toolbox (`buf` for `.proto` linting, `connect-go` codegen). Worth it.
- L1 agent must include connect-go runtime → slightly larger binary than raw HTTP server (~1–2 MB). Acceptable per [ADR-0002](./0002-guest-agent-language-go.md) targets (~5–10 MB total).
- Phase 7 research must include "vsock + connect-go" feasibility — vsock transport for connect/gRPC is well-trodden but not zero-config.

**Neutral:**
- Phase 6 research now picks connect-go as primary candidate; the framework choice section in `roadmap.md` narrows.
- Existing Python `computer-use-server` keeps speaking HTTP/MCP unchanged — transition is at Phase 6 cutover.

## Migration notes

- **Phases 1–5 (Python orchestrator):** stay on Python HTTP; provider interface is in-process Protocol; HTTP transport between orchestrator and pool-manager sidecar.
- **Phase 6 (Go control plane):** introduces `.proto` files for L4↔L3 boundary. Python orchestrator keeps working in parallel; new Go service serves both MCP gateway (external) and connect RPCs (internal).
- **Phase 7 (Go agent):** L1 serves connect-go on vsock/TCP; L3 client compiled from same `.proto`.
- **Phase 8 (egress proxy):** connect for L4↔proxy stats/control; egress traffic itself stays HTTP CONNECT (proxy is a TCP proxy, not RPC).
- **Phase 9 (Kata):** vsock + connect-go validated.
- **Phase 10 (HA / multi-region):** mTLS on all internal RPCs; cert rotation via cert-manager or equivalent.

## Verification

- Each phase's PR must include the `.proto` schema diff if any internal RPC changed.
- `tests/integration/test_mcp_*.py` continue to call MCP and **do not** speak connect — proving the user-facing surface is unchanged.
- Phase 6 acceptance: `curl -H "Content-Type: application/json" -X POST http://l4/api.v1.SandboxProvider/Spawn -d '{...}'` returns the same result as the typed gRPC call.
