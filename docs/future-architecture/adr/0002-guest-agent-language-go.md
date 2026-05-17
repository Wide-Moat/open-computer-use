# ADR-0002 — Guest agent language: Go (with Rust documented)

- **Status:** Accepted (with explicit re-evaluation gate in Phase 7)
- **Date:** 2026-05-17
- **Related:** [ADR-0001](./0001-control-plane-language-go.md)

## Context

Phase 7 of the roadmap replaces today's Python entrypoint + in-image MCP server with a small static binary as PID 1. The candidate languages are **Go** (consistent with ADR-0001) and **Rust** (consistent with sandboxd, kata-agent, msb-agent).

This decision matters more for L1 than for L4 because the in-sandbox agent is the **inner attack target**: untrusted code, prompt-injected agents, or compromised dependencies inside the sandbox all interact with L1 first. RCE in L1's HTTP handling buys the attacker the agent's full powers (which are deliberately small, but still).

## Decision

**Go.** With Rust kept on the table as a Phase 7 *research* topic: the gate before code starts is a written profit/cost analysis that either (a) confirms Go or (b) overturns this ADR.

## Rationale (for Go)

- **Operator preference.** Same owner constraint as [ADR-0001](./0001-control-plane-language-go.md). Owner is productive in Go, not Rust.
- **Single language across L4 + L1.** Shared types, shared HTTP client patterns, shared MCP JSON-RPC handling. One on-call skill set.
- **`chromedp` exists.** Mature direct-CDP client; lets us skip the WebDriver layer for Computer Use. No Rust equivalent of equivalent maturity.
- **Precedent.** E2B's `envd` is Go-and-in-production. Proves the shape works.
- **Static binary, cross-compile.** No worse than Rust for this property in practice.

## What Rust would buy us (documented for future re-evaluation)

- **Smaller binary** (~½ size). Less to ship, less to load.
- **Stronger memory safety.** L1's HTTP handler is a direct RCE target. Rust's safety class eliminates a category of bugs Go does not.
- **Precedent at the runtime layer.** kata-agent (Rust), msb-agent (Rust), Firecracker (Rust), Cloud Hypervisor (Rust). If L1 ever calls into hypervisor APIs directly, Rust integrates more naturally.
- **vsock crates** are mature in Rust; Go's vsock support exists but is less common.
- **Async runtime.** `tokio` is excellent for the L1 workload (long-lived sockets, multiple streams).

## Decision gate (Phase 7 research)

`phase-7-research.md` must answer:
1. Concrete RCE attack surface of a Go HTTP/WS server inside the sandbox. Is it real exposure or theoretical?
2. Binary-size delta on actual artifacts, with each language's optimizer dialed in.
3. CDP / Chromium driving cost in Rust (no chromedp equivalent — write our own or use a less-mature crate).
4. Owner's honest assessment of Rust productivity given exposure since this ADR was written.

If answers favor Rust, supersede this ADR. The interface ([05-layer1-guest-agent.md](../architecture/05-layer1-guest-agent.md)) is language-agnostic — L4 doesn't care.

## Alternatives considered

### Keep Python (status quo)
- **Pro:** zero migration cost.
- **Con:** big attack surface, no static binary, no vsock readiness, no realistic path to microVM Layer-1.
- **Verdict:** rejected as the *target*. Python entrypoint stays as the transitional L1 through Phases 1–6.

### C / C++
- **Verdict:** rejected. Memory-safety properties worse than both Go and Rust; offers nothing they don't.

## Consequences

- Phase 7 ships a Go binary.
- L1 and L4 share language → easier on-call but also single point of language-level CVE risk.
- chromedp dependency added.
- Door for Rust re-evaluation stays open at Phase 7 research gate.
