<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# ADR-0002 — Guest agent language: Rust

- **Status:** Accepted (rewritten 2026-05-18; supersedes the prior Go decision recorded under the same number)
- **Date:** 2026-05-18 (original 2026-05-17 version was Go-with-Rust-as-option; rewritten in place after `sandboxd/anthropic/process_api_re/` study made Rust the better starting point)
- **Related:** [ADR-0001](./0001-control-plane-language-go.md), [ADR-0008](./0008-internal-grpc-external-rest-mcp.md), [research/19](../research/19-anthropic-process-api.md)
- **Filename note:** kept as `0002-guest-agent-language-go.md` for git-history continuity; the title and content are now Rust.

## Context

Phase 7 of the roadmap replaces today's Python entrypoint + in-image MCP server with a small static binary as PID 1. The candidate languages are **Rust** (Anthropic's `process_api`, kata-agent, msb-agent, Firecracker, Cloud Hypervisor) and **Go** (consistent with ADR-0001's L4 choice, E2B's `envd`).

This decision matters more for L1 than for L4 because the in-sandbox agent is the **inner attack target**: untrusted code, prompt-injected agents, or compromised dependencies inside the sandbox all interact with L1 first. RCE in L1's HTTP / WS handling buys the attacker the agent's full powers (which are deliberately small, but still).

The earlier (2026-05-17) version of this ADR picked Go for operator-preference reasons. That was written before [`research/19-anthropic-process-api.md`](../research/19-anthropic-process-api.md) extracted concrete Rust patterns from `sandboxd/anthropic/process_api_re/`. With that material now in hand, Rust is the better starting point — it matches the precedent at every microVM-runtime project we depend on, and the L1 contract turns out to be a near-1:1 match for what `process_api` already does.

## Decision

**Rust.** Phase 7 ships a Rust binary as the L1 guest agent. The crate footprint mirrors `process_api`'s: `tokio`, `hyper`, `tokio-tungstenite`, `tokio-vsock`, `ring`, `jsonwebtoken`, `clap`, `nix`, `serde_json`.

Go stays on the table only as a **fallback** if the Phase 7 research gate (below) surfaces a concrete blocker we cannot route around.

## Rationale (for Rust)

- **Precedent at the runtime layer.** Every adjacent agent-in-microVM project is Rust: `process_api` ([research/19](../research/19-anthropic-process-api.md)), kata-agent, msb-agent, Firecracker, Cloud Hypervisor. We are not the first ones doing this; the language choice has been litigated.
- **Memory safety on the RCE target.** L1's WS handler is a direct RCE target. Rust's safety class eliminates a category of bugs Go does not, and the small static-PIE binary surface is easier to audit.
- **Smaller binary.** `process_api` is 4.3 MB static-PIE. A Go equivalent would be 10–15 MB. For a binary that ships inside every sandbox image, the delta matters at scale.
- **Async runtime fit.** `tokio` is excellent for L1's workload (long-lived WS, multiple streams, vsock).
- **vsock crates are mature in Rust** (`tokio-vsock`). Go's vsock support exists but is less common.
- **Same primitives as `process_api`.** First-byte JSON-vs-JWT dispatch, Ed25519 verification with `ring`, capabilities negotiation — these are easier to clone when the dependency list matches.
- **Owner reconsideration.** The original ADR rejected Rust on owner-productivity grounds. After studying `process_api_re/`, the owner has flipped that call: the L1 surface is small and protocol-shaped, which is where Rust's friction is lowest.

## What Go would have bought us (kept for the record)

- **Single language across L4 + L1** with ADR-0001. Lost — but L4 ↔ L1 talks over a wire protocol, not shared code, so the loss is shallow.
- **`chromedp` exists.** Mature direct-CDP client. Mitigation: Phase 7 research evaluates a Rust CDP client (`chromiumoxide`) or treats CDP as a pure WebSocket passthrough (see ADR-0008) and does not parse it on the L1 side.
- **Operator familiarity.** Owner accepts the productivity hit on the L1 side; L4 stays Go ([ADR-0001](./0001-control-plane-language-go.md)) so the day-to-day operator surface is unchanged.

## Decision gate (Phase 7 research)

`phase-7-research.md` must confirm before code starts:

1. **CDP driving from Rust.** `chromiumoxide` vs raw WebSocket passthrough — pick one and justify. No chromedp parity required if the L1 doesn't drive CDP itself.
2. **Build & toolchain.** musl static-PIE target, cross-compile for `linux/amd64` and `linux/arm64`, reproducible builds.
3. **vsock transport feasibility.** `tokio-vsock` on the runtimes we target (runc, sysbox, kata-fc, kata-ch). This also feeds the ADR-0008 Phase 7 gate.
4. **MCP server hosting.** Rust MCP server libraries are younger than Go's; if the only mature one is unfit, decide whether to (a) hand-roll JSON-RPC dispatch (the path `process_api` would take), (b) accept the youngest mature crate, or (c) keep MCP termination in L4 and have L1 expose only the typed RPC.
5. **Owner productivity check.** Honest assessment after spiking the agent skeleton.

If answers favor Go, supersede this ADR with a new one (not by editing this file again). The interface ([05-layer1-guest-agent.md](../architecture/05-layer1-guest-agent.md)) is language-agnostic — L4 doesn't care.

## Alternatives considered

### Go (the prior decision under this number)
- **Pro:** single language with L4, `chromedp`, E2B precedent, owner-familiar.
- **Con:** Larger binary; weaker memory-safety story on the RCE target; out of line with every adjacent microVM-agent project; loses the direct ability to clone `process_api` patterns.
- **Verdict:** rejected as the *target* with a Phase 7 escape hatch. The original Go-leaning ADR text is preserved in git history (`git log` on this file).

### Keep Python (status quo)
- **Pro:** zero migration cost.
- **Con:** big attack surface, no static binary, no vsock readiness, no realistic path to microVM Layer-1.
- **Verdict:** rejected as the *target*. Python entrypoint stays as the transitional L1 through Phases 1–6.

### C / C++
- **Verdict:** rejected. Memory-safety properties worse than both Go and Rust; offers nothing they don't.

## Consequences

**Positive:**
- L1 binary is smaller (target ~4–6 MB) and audit-able.
- L1 lines up with `process_api`, kata-agent, msb-agent — known idioms, known crates.
- Capabilities negotiation, Ed25519 JWT, first-byte dispatch (from [research/19](../research/19-anthropic-process-api.md) §3–§4) become drop-in patterns rather than ports.

**Negative:**
- Two-language stack (Rust L1 + Go L4). On-call needs to read both. The wire boundary between them is the firewall: contracts in `.proto` / JSON, no shared code.
- Slower L1 iteration vs. Go in the early Phase 7 weeks. Mitigated by the small surface area of the agent.
- We give up `chromedp` — Phase 7 research must close that gap.

**Neutral:**
- ADR-0008's "connect-go on L3↔L1" line now reads "connect-rust" in effect. ADR-0008 has a Phase 7 gate ([its §"Negative"](./0008-internal-grpc-external-rest-mcp.md)) that already calls this out; the gate is tightened in the 2026-05-18 edit of that ADR.
- ADR-0001 (L4=Go) stays unchanged. Its Phase 6 gate now also re-confirms Go-vs-Rust on the L4 side given that L1 went Rust.
