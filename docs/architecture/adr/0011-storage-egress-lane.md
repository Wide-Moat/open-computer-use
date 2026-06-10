<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-06-07
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
compliance-impact: [SOC2-CC6.1, ISO27001-A.8.10, NYDFS-500.15, DORA-Art.28]
license-impact: none
threat-mitigation-link: ../06-threat-model.md
---

The storage-backend leg is reached over a storage-dedicated lane on the Egress trust-edge — out-of-process from the broker, distinct from the guest egress lane — so detaching storage from the guest-egress policy class does not move the enforcement into the credential-holder.

# ADR-0011: Storage backend reached over a storage-dedicated egress lane

## Status

`proposed`

## Context

A network backend engine's leg ([ADR-0010](0010-storage-backend-pluggable-adapter.md)) was routed through the same Egress trust-edge lane that governs the guest's LLM / internet egress ([NFR-SEC-25](../manifesto/02-nfrs.md), [08-contracts.md](../08-contracts.md) F9). Storage and guest-internet are different traffic classes with different authorization — file scope/intent/`downloadable` on one side, the upstream allow-list and credential injection on the other ([05-c4-container.md](../05-c4-container.md) §4) — yet a single shared lane cannot express a storage-specific policy without touching the guest lane. A local-volume engine has no network leg at all, so the shared-lane wording was over-broad for it.

Two constraints bound where the storage leg's network enforcement can live. The broker holds the backend credential, so a control co-located inside the broker process dies with broker compromise (the confused-deputy path P4-E1 is already live) — strictly weaker than the status quo, where the enforcement is a separate container the broker cannot edit. And P4-E2 ([06-threat-model.md](../06-threat-model.md) §3) requires "no outbound path the control cannot see"; detaching from the guest lane must not re-open that hole.

## Decision

The broker-originated backend leg is reached over a storage-dedicated lane on the Egress trust-edge — a distinct policy lane, out-of-process from the broker, on the existing outbound-mediation container — not the guest-egress lane and not a control inside the broker. The broker holds the credential, signs once, and originates the leg; the lane forwards it allow-list-only with no TLS termination and enforces, where the broker cannot suppress it, the destination allow-list, the one proxy-owned resolver and its deny-set, the exfil tripwire, and an edge-authored OCSF event per backend operation ([NFR-SEC-85](../manifesto/02-nfrs.md)).

## Consequences

- The enforcement stays out-of-broker, so it survives broker compromise: a fully-compromised broker holds the credential but can neither relax the storage allow-list, nor silence the connect-time deny, nor suppress or backfill the edge-authored OCSF event — the property the shared-lane transit gave today, kept ([NFR-SEC-85](../manifesto/02-nfrs.md), closing the in-broker-control weakening).
- P4-E2 holds equal-or-stronger. The leg is now a distinguishable policy class rather than an indistinguishable guest-egress lookalike, so the lane can express a storage-specific deny it could not before, while the count of outbound paths the control can see is unchanged — still one outbound-mediation container, with the direct broker-to-backend dial still forbidden ([NFR-SEC-16](../manifesto/02-nfrs.md)).
- The one proxy-owned resolver is the sole resolution authority for both lanes ([NFR-SEC-12](../manifesto/02-nfrs.md)) — the storage lane shares it, it does not bring its own, so detaching the lane creates no second resolver and no second SSRF/rebind surface.
- No new container. The storage lane is a second listener on the existing Egress trust-edge container, so the five-zone / six-container model ([05-c4-container.md](../05-c4-container.md) §1) is unchanged.
- Positive: single-egress is single-egress-per-purpose ([NFR-SEC-05](../manifesto/02-nfrs.md), [NFR-SEC-16](../manifesto/02-nfrs.md)) — guest-internet / upstream-API on the forward-proxy lane, customer object storage on the storage lane, both deny-by-default and audited. The storage lane does no credential injection, no customer-CA bump, no edge ICAP — those are upstream-API-shaped and never applied to storage.
- Positive: a local-volume engine ([ADR-0010](0010-storage-backend-pluggable-adapter.md)) opens no network leg, so the lane is vacuous for it; the minimal shelf holds the one-click-solo property unchanged.
- Neutral: storage user-data content inspection runs at the broker on plaintext before signing ([NFR-SEC-81](../manifesto/02-nfrs.md)), since the lane is pass-through and sees only the broker-signed ciphertext — this is where the content-blind-storage residual ([#182](https://github.com/Wide-Moat/open-computer-use/issues/182)) is closed for storage.
- Negative: in-transit confidentiality on the leg rests on the broker's own TLS to the backend ([NFR-SEC-25](../manifesto/02-nfrs.md) — the broker signs and originates the request), not on a shared-edge property; the broker must validate the backend certificate strictly and fail closed. P4-T2 in-transit confidentiality now rests on [NFR-SEC-25](../manifesto/02-nfrs.md) + [NFR-SEC-85](../manifesto/02-nfrs.md) (broker-originated TLS); [NFR-SEC-05](../manifesto/02-nfrs.md) stays guest-egress-scoped.

## Alternatives considered

- **Keep the storage leg on the shared guest-egress lane (the status quo before this ADR).** Rejected: storage and guest-internet are different traffic classes, so one lane cannot carry a storage-specific policy without touching the guest lane; the leg is also indistinguishable from guest egress for audit and deny purposes. Fails the separation the storage contour requires.
- **Move the allow-list, resolver, tripwire, and OCSF emit into the broker (broker enforces its own exit).** Rejected: the broker holds the backend credential, so a control in the same process is defeated by broker compromise (P4-E1 confused-deputy is live) — strictly weaker than today's separate-container enforcement, and it re-opens the P4-E2 uncontrolled-exit hole. It would also stand up a second resolver, contradicting [NFR-SEC-12](../manifesto/02-nfrs.md).
- **A dedicated storage-egress sidecar (own process, own resolver) in the Egress zone.** Rejected: a standalone process reads as a seventh container against the five-zone / six-container model ([05-c4-container.md](../05-c4-container.md) §1), and its own resolver violates the single-resolution-authority clause of [NFR-SEC-12](../manifesto/02-nfrs.md). A second listener on the existing edge delivers the same separation without either cost.

## Compliance impact

- `SOC2-CC6.1` / `ISO27001-A.8.10`: backend-credential confidentiality holds — the broker is the sole credential holder and the lane terminates no TLS, so no credential reaches the lane or the guest.
- `NYDFS-500.15` / `DORA-Art.28`: the storage leg is a controlled, audited outbound path with an edge-authored event a compromised broker cannot suppress; third-party-storage access is governed and recorded.

## License impact

None. The storage lane is a listener configuration on the already-bundled outbound-mediation edge ([ADR-0006](0006-egress-forward-proxy-substrate.md)); no new dependency is introduced.

## Threat mitigation

Re-homes P4-D2 and P4-E2 ([06-threat-model.md](../06-threat-model.md) §3) off the shared single-egress wording onto the storage lane: the broker-signed leg traverses an out-of-broker enforcement point under a deny-by-default allow-list, the deny-set, the exfil tripwire, and an edge-authored OCSF event, so no outbound path the control cannot see exists by policy even under broker compromise. P4-T2 in-transit confidentiality re-anchors onto the broker-originated TLS ([NFR-SEC-25](../manifesto/02-nfrs.md) + [NFR-SEC-85](../manifesto/02-nfrs.md)), off the now guest-egress-scoped [NFR-SEC-05](../manifesto/02-nfrs.md).

## Open questions

1. Per-session backend byte / rate ceiling on the storage lane — resource-exhaustion theme, [#188](https://github.com/Wide-Moat/open-computer-use/issues/188).
2. Whether broker-side plaintext DLP on user-data is mandatory or per-deployment on the storage path — content-blind theme, [#182](https://github.com/Wide-Moat/open-computer-use/issues/182).
