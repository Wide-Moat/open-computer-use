<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-06-01
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
compliance-impact: [EU-AI-Act-Art.15, DORA-Art.28, NIST-SP-800-190]
license-impact: none
threat-mitigation-link: ../02-trust-boundaries.md#4-per-tenant-isolation-menu
---

Fixes the axis that selects the sandbox runtime tier, and which tiers v1 GA ships. Audience: anyone touching the Session sandbox substrate or its admission rules.

# ADR-0003: Sandbox runtime tier ladder

## Status

`proposed`

## Context

The Session sandbox ([component 05](../components/05-session-sandbox.md)) runs agent-issued actions inside an isolation boundary. The strength of that boundary — bare namespaces, a user-space kernel, or hardware virtualization — sets escape resistance, host footprint, and whether a deployment runs from a single `docker-compose up`.

Two axes compete to drive the choice: data classification (stronger tier for more sensitive data) versus workload trust (the tier follows who supplies the prompts the agent executes). §02 and AP-13 already record the split — data classification governs retention, custody, and residency; workload trust governs the tier. The remaining question is the product-level one this ADR closes: which tiers v1 GA ships and which it defers.

The one-click solo install is an NFR-shaping invariant: the default deployment runs single-operator, no IdP, no KVM, and must not pay for a regulated enterprise's isolation or audit machinery to start.

## Decision

The sandbox runtime tier is selected by the deployment-wide workload-trust profile — `runc` for `trusted_operator`, gVisor/`runsc` for `internal_workforce`, with microVM as the `untrusted` tier deferred post-v1 — and never by data classification (AP-13).

## Consequences

- v1 GA bundles two runtimes and ships three deployable cells; the profile/tier matrix, allowed pairings, and rejected cells live in NFR-SEC-38, enforced at deploy time by the Control / operator API ([component 02](../components/02-control-operator-api.md)). This ADR does not restate them.
- The `trusted_operator` × `runc` cell preserves the one-click solo install — no KVM, no IdP, zero-config. gVisor is the hardened default for `internal_workforce`.
- Enterprise audit machinery stays opt-in for the solo default: the local audit-event emit is mandatory in code for every tier (NFR-SEC-45, fail-closed), but the external sinks and alarms that consume it — SIEM-bridge, SOAR webhook, the NFR-SEC-39 tier-downgrade alarm — are off when no such sink is configured. A solo operator reconfiguring their own tier raises a local event and nothing external fires.
- Per-tier escape resistance and the per-release red-team gate stay governed by NFR-SEC-02; the tier-downgrade alarm by NFR-SEC-39, emitted as `config.trust_profile.downgraded` through the Audit pipeline ([component 07](../components/07-audit-pipeline.md)). This ADR adds no requirement to either.
- The Session sandbox records this ADR in its `adr:` front-matter; its host-side exec-supervisor and runtime-supervisor model is unchanged, so the tier choice forces no Layer-6 container split.
- microVM packaging (Firecracker vs Kata, [#161](https://github.com/Wide-Moat/open-computer-use/issues/161)), per-session trust profile ([#162](https://github.com/Wide-Moat/open-computer-use/issues/162)), and the sandbox sub-split ([#174](https://github.com/Wide-Moat/open-computer-use/issues/174)) are downstream seams this ADR names but does not design.

## Alternatives considered

- **microVM-default (E2B-style)** — hardware virtualization for every deployment. Rejected because it requires KVM on the `trusted_operator` path that needs no hardware boundary, breaking the one-click solo invariant.
- **gVisor-only floor** — drop `runc`, run `runsc` everywhere. Rejected because it removes zero-config `runc` from the `trusted_operator` path and pays user-space-kernel overhead where the workload-trust profile does not call for it.
- **Tier by data classification** — pick the tier from the data the agent touches. Rejected by AP-13: the container-escape surface for adversarial agent-issued code is identical regardless of data class.

## Compliance impact

- `EU-AI-Act-Art.15` (4)/(5): the tier ladder is the agent-execution boundary's cybersecurity measure under the Article's accuracy-and-cybersecurity requirement for high-risk systems; per-tier red-team evidence lands via NFR-SEC-02.
- `DORA-Art.28` (4): the active runtime substrate per deployment is declared at deploy and auditable, so it is recordable in the ITS register of information.
- `NIST-SP-800-190` §3: workload separation is realized through each tier's isolation primitives (`runc` namespaces, gVisor user-space kernel, microVM hardware boundary) — cited for the primitives, not for the selection axis.

## License impact

This is the adopting ADR for `runc` and gVisor, so both enter the Bill of Materials in [`manifesto/05-licensing-posture.md`](../manifesto/05-licensing-posture.md) as bundled (Apache-2.0; gVisor carries per-file MIT/BSD). Both clear the licence gate. Firecracker and Kata clear the same gate but are not bundled in v1; they enter the Bill of Materials when the microVM tier lands ([#161](https://github.com/Wide-Moat/open-computer-use/issues/161)).

## Threat mitigation

The multi-tenant agent-execution invariant in [`02-trust-boundaries.md`](../02-trust-boundaries.md#4-per-tenant-isolation-menu) §4 forbids bare `runc` for multi-tenant execution and requires a user-space kernel or hardware virtualization; the tier ladder is how a deployment satisfies it. Per-tier escape resistance — seccomp BPF, Landlock, cap-drop ALL, read-only rootfs, and the zero-pass red-team gate — is held by NFR-SEC-02.
