<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# ADR-0001 — Control plane language: Go

- **Status:** Accepted
- **Date:** 2026-05-17
- **Deciders:** project owner
- **Supersedes:** —
- **Superseded by:** —

## Context

The current control plane (`computer-use-server/`) is Python FastAPI. The roadmap (`../roadmap.md`) cuts over to a greenfield control plane in Phase 6. We must commit to a language for that rewrite now, because every prior phase (Phases 1–5 inside Python) must avoid Python-only design choices that don't translate.

Constraints:
- Target deployment includes AWS and GCP managed k8s, on-prem RKE2, and Docker Compose for PoC.
- Heavy k8s API interaction (`KubernetesProvider`, `agent-sandbox` CRDs).
- MCP gateway must support long-lived streaming connections (CDP, ttyd, MCP responses).
- Operator skill set on the project (owner explicitly stated preference and unfamiliarity with Rust).

## Decision

**The new control plane (Phase 6+) will be written in Go.**

## Rationale

- **k8s ecosystem fit.** `client-go` is the canonical k8s API client; every CRD controller, every k8s tool, every operator pattern is Go-first. `kubernetes-sigs/agent-sandbox` (our L3 CRD basis) is Go.
- **Single SDK story across clouds.** AWS SDK v2 and GCP SDK are both mature in Go.
- **Operator preference.** Project owner is comfortable with Go, not Rust. Code we can't maintain confidently is a liability.
- **Static binary.** Trivial container packaging, easy ops.
- **Streaming concurrency model.** Goroutines + channels map well to long-lived MCP/CDP WebSocket gateways.
- **Boring choice.** Operations community knows Go-on-k8s; hiring is easier.

## Alternatives considered

### Stay with Python (FastAPI)
- **Pro:** zero migration cost, current team velocity, MCP SDK ecosystem strong.
- **Con:** k8s controller story is weak; long-running connections under GIL get hairy at scale; no static binary; type safety weaker for a long-lived production service.
- **Verdict:** continue using Python through Phases 1–5 (refactor in place); rewrite in Go at Phase 6.

### Rust
- **Pro:** memory safety, smallest binary, fastest runtime, aligns with kata-agent's Layer-1 language preference. Would also let us share code between L1 (agent) and L4 (control plane).
- **Con:** project owner is not productive in Rust; k8s ecosystem in Rust is immature (`kube-rs` exists but is a fraction of `client-go`'s coverage); slower iteration on a control-plane-heavy codebase.
- **Verdict:** rejected for L4. L1 may revisit ([ADR-0002](./0002-guest-agent-language-go.md)).

### TypeScript / Node
- **Pro:** good for admin UI sharing types.
- **Con:** worse k8s story than Go, weaker for long-lived streams, worse SDK story for AWS/GCP at the same depth as Go.
- **Verdict:** rejected. Admin UI is a separate concern and can ship in TS independently.

## Consequences

**Positive:**
- Phase 6 produces a long-lived, easy-to-operate binary.
- Future hires and contributors have a familiar stack.
- Direct path to writing a custom k8s controller if `agent-sandbox` CRDs need extension.

**Negative:**
- Phase 6 is a non-trivial rewrite (not just a port — design improves at the same time).
- Bilingual maintenance period: Phase 6 runs Python and Go side-by-side until parity is reached.
- L1 (Go) and L4 (Go) share a language; we lose the option to share *code* with a Rust L1 if that direction is later reconsidered.

**Neutral:**
- Interfaces (L4 ↔ L3, L3 ↔ L1) stay language-agnostic (HTTP/gRPC), so the L1 language decision ([ADR-0002](./0002-guest-agent-language-go.md)) is independent.

## Verification

- Phase 6 research doc (`phase-6-research.md`) must confirm web framework + k8s client + MCP-on-Go strategy before code starts.
- Parity acceptance: integration tests (`tests/integration/test_mcp_*.py`) pass against the new Go endpoint unchanged.

## Phase 6 re-evaluation gate (added 2026-05-18)

[ADR-0002](./0002-guest-agent-language-go.md) flipped L1 to Rust after this ADR was accepted. That changes the two-language calculus referenced under "Negative consequences" above — we no longer have a single-language stack. Phase 6 research must therefore answer one extra question before Go code starts:

> Given that L1 is Rust, does L4 still want to be Go? The default answer remains **yes** (k8s ecosystem fit, owner familiarity, streaming concurrency, hiring) and this ADR is **not pre-superseded**. The gate exists so the Phase 6 author cannot ship Go code without having considered the alternative explicitly.

If Phase 6 research instead concludes that L4 should also be Rust, supersede this ADR rather than amending it.
