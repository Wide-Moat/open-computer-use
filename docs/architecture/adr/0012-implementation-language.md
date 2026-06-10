<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-06-08
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: [future-architecture/adr/0001-control-plane-language-go, future-architecture/adr/0002-guest-agent-language-go]
superseded-by: null
compliance-impact: [SOC2-CC8.1]
license-impact: none
threat-mitigation-link: ../02-trust-boundaries.md#4-per-tenant-isolation-menu
---

Fixes the implementation language for each build target: Go for the host-side control and supervision processes, Rust for the in-sandbox guest agent. Audience: anyone writing or reviewing component code.

# ADR-0012: Implementation language

## Status

`proposed`

## Context

No prior ADR in this set fixes an implementation language; the choice crosses every component (the guest agent, the host exec-supervisor, the Control / operator API) and is expensive to reverse once code lands.

Two build targets sit in different trust zones with different constraints:

- **Host-side control and supervision** — the Control / operator API ([component 02](../components/02-control-operator-api.md)) and the host exec-supervisor that the Session sandbox spec ([component 05](../components/05-session-sandbox.md)) places outside the guest. This grows into session lifecycle, quota, denylist, kill-switch, and (on the full shelf) k8s orchestration and cloud-provider integration. It is operated daily.
- **The in-sandbox guest agent** — PID 1 inside the sandbox ([component 05](../components/05-session-sandbox.md)). It is the inner attack target: untrusted agent-issued code, prompt-injected agents, and compromised in-sandbox dependencies all reach it first. Its control-channel handler is a direct RCE target, and it ships inside every sandbox image.

The two talk over a wire contract ([`exec/exec-channel.schema.json`](../../../contracts/exec/exec-channel.schema.json)), not shared memory, so they need not share a language.

## Decision

Host-side control and supervision processes are written in **Go**: the Control / operator API and the host exec-supervisor — the process that terminates the exec WebSocket, spawns and reaps guest processes, and strips the deny-pattern env set at fork ([component 05](../components/05-session-sandbox.md)). The in-sandbox PID-1 guest agent is written in **Rust**. The fork/exec boundary is the Go/Rust seam: the Go supervisor writes the spawn frame onto the exec channel; the Rust agent runs on the other side. The two share no runtime and no in-process state.

## Consequences

- The Go side gets the canonical k8s client (`client-go`), mature AWS and GCP SDKs, and goroutine-per-connection concurrency that fits the long-lived control and exec channels — the full-shelf orchestration path stays on the ecosystem built for it. Go is the language the project currently operates in; the maintenance surface carries no additional toolchain cost.
- The Rust guest agent is a static-PIE binary on the RCE target: memory safety removes a bug class from the control-channel handler, the binary that ships in every image stays a few megabytes rather than ten-plus, and `tokio` fits the long-lived channel with bounded per-stream stdio (NFR-SEC-74). The cost is a second toolchain and a language the project is less fluent in — accepted because the guest surface is protocol-shaped (bounded schema, no ambient library surface), which is where that toolchain cost is lowest.
- The exec-channel union ([`exec/exec-channel.schema.json`](../../../contracts/exec/exec-channel.schema.json)) is the single source for the wire types both sides build against; the Go host side and the Rust guest side each conform to it (generated or validated in CI, the carrier owned by [`08-contracts.md`](../08-contracts.md) §4), not by hand-maintained parallel definitions.
- A Cargo workspace MAY share a wire-types crate across Rust binaries, but the guest agent and any host-side Rust helper compile to separate binaries; the guest binary ships inside the hostile rootfs and the host binaries never do.
- Component specs record no language in their prose; this ADR is the single source. New source files carry the SPDX header in the comment syntax of their language.
- This decision binds implementation only. It forces no Layer-6 container split and changes no contract, NFR, or trust boundary.

## Alternatives considered

- **Go everywhere (including the guest agent).** One toolchain, one hiring story, `chromedp` available for later CDP work. Rejected for the guest agent: a garbage-collected ten-plus-megabyte binary on the per-image RCE target trades away the memory-safety class and the small-surface audit benefit for a code-sharing win that does not exist (the two sides talk over a wire contract, not shared code).
- **Rust everywhere (including the control plane).** Smallest binaries, one memory-safety story. Rejected for the host side: the k8s client and cloud-provider SDKs are a fraction as mature in Rust as in Go, the control plane is the daily-operated surface where the project is most fluent in Go, and a control-plane-heavy codebase is where Rust's iteration friction is highest. Code the team cannot maintain confidently is a liability.
- **Python (continue the PoC stack).** Zero migration from the current `main`-line server. Rejected: no static binary, a weaker k8s-controller story, and weaker type safety for a long-lived production service — the wrong base for a regulated-enterprise control plane.

## Compliance impact

| Control | Component | Evidence |
|---|---|---|
| SOC2-CC8.1 | all build targets | one recorded language per target → deterministic toolchain, SBOM surface, and supply-chain scan per artifact (this ADR) |

## License impact

None. Both toolchains and their standard libraries clear the licence gate ([`manifesto/05-licensing-posture.md`](../manifesto/05-licensing-posture.md)): Go is BSD-3, Rust is MIT/Apache-2.0. Per-dependency gating is unchanged; this ADR adopts no library.

## Threat mitigation

The Rust guest agent narrows the in-sandbox RCE target's bug class on the boundary the threat model marks as the inner attack surface ([component 05](../components/05-session-sandbox.md) failure modes, reaching actor A1). Per-tier escape resistance and the per-release red-team gate stay governed by NFR-SEC-02; this ADR adds no requirement to either and substitutes for no isolation control — a memory-safe agent is not a substitute for the sandbox boundary.
