<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-06-14
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
amended-by: [0013, 0016]
compliance-impact: [SOC2-CC6.1, ISO27001-A.8.10, NYDFS-500.15, DORA-Art.28]
license-impact: none
threat-mitigation-link: ../06-threat-model.md
---

The guest storage leg rides the single egress hop like every other guest dial: the hop terminates TLS, forwards the static Bearer unchanged, and enforces no storage scope; scope is the storage engine's. Audience: anyone wiring or auditing how the guest reaches its storage backend.

# ADR-0011: Storage backend rides the single egress hop

## Status

`proposed` — amended by [ADR-0013](0013-storage-credential-custody.md) and [ADR-0016](0016-egress-baseline-inspection-hop-backend-scope.md).

## Context

A network storage engine ([ADR-0010](0010-storage-backend-pluggable-adapter.md)) is reached over a network leg from the guest. The guest dials out, and that dial leaves the sandbox on the Egress trust-edge, the single outbound hop every guest connection uses ([NFR-SEC-16](../manifesto/02-nfrs.md), [08-contracts.md](../08-contracts.md)). The storage credential is a guest-held, off-box-issued static JWT bearer ([ADR-0013](0013-storage-credential-custody.md)); no in-deployment component holds a storage signing key, and the bearer is forwarded unmodified.

The egress hop terminates TLS, inspects, and forwards the connection. It mints no credential, attaches none, and re-signs nothing — the bearer it forwards is byte-unchanged, and the hop enforces no storage scope ([ADR-0016](0016-egress-baseline-inspection-hop-backend-scope.md)). Scope is enforced by the storage engine, which verifies the JWT and rejects a foreign `filesystem_id`. A local-volume engine has no network leg, so the hop is vacuous for it.

## Decision

The guest storage leg uses the single egress hop, not a storage-dedicated lane and not a control inside the object-store service. The guest forwards the static Bearer; the hop terminates TLS and forwards it unchanged; the storage engine verifies and enforces scope. At the baseline the hop is permissive — one default route, no second socket, guest loopback dials blocked — and emits an edge-authored OCSF event per backend operation ([NFR-SEC-85](../manifesto/02-nfrs.md)); the destination allow-list, the proxy-owned resolver deny-set, and the connect-time structured deny are optional hardening on the same hop, not the baseline ([ADR-0016](0016-egress-baseline-inspection-hop-backend-scope.md)). Every one of these controls is out-of-process from the object-store service and the guest.

## Consequences

- Enforcement stays out of the guest and out of the object-store service, so it survives a compromise of either: a compromised guest holds the scoped bearer but cannot reach a second socket and cannot suppress the edge-authored OCSF event ([NFR-SEC-85](../manifesto/02-nfrs.md)). Where the optional hardening is enabled, it also cannot relax the allow-list or silence the connect-time deny.
- P4-mount-E2 holds: the storage leg adds no outbound path the control cannot see. It is one more guest dial on the one outbound-mediation container, and the direct guest-to-engine dial bypassing the hop is forbidden ([NFR-SEC-16](../manifesto/02-nfrs.md)).
- The one proxy-owned resolver is the sole resolution authority for the hop ([NFR-SEC-12](../manifesto/02-nfrs.md)); the storage leg shares it and brings no second resolver, so no second SSRF/rebind surface.
- No new container. The storage leg reuses the existing Egress trust-edge container, so the container set ([05-c4-container.md](../05-c4-container.md) §1) is unchanged.
- The hop terminates TLS, so where the optional content-inspection hardening is enabled it runs on the storage leg's plaintext ([NFR-SEC-81](../manifesto/02-nfrs.md)); the content-blind-storage residual ([#182](https://github.com/Wide-Moat/open-computer-use/issues/182)) is a per-deployment hardening choice, not a baseline guarantee.
- A local-volume engine ([ADR-0010](0010-storage-backend-pluggable-adapter.md)) opens no network leg, so the hop is vacuous for it; the minimal shelf holds the one-click-solo property unchanged.
- In-transit confidentiality rests on TLS at the hop, not on a separate object-store-service property. P4-mount-T2 in-transit confidentiality re-anchors onto the hop's TLS ([NFR-SEC-85](../manifesto/02-nfrs.md)); [NFR-SEC-05](../manifesto/02-nfrs.md) stays guest-egress-scoped.

## Alternatives considered

- **A storage-dedicated egress lane that forwards the leg with no TLS termination so a per-request signature stays byte-intact.** Rejected: the storage credential is a static bearer, not a per-request signature, so there is nothing to keep byte-intact ([ADR-0013](0013-storage-credential-custody.md)). A no-termination lane gives up the plaintext inspection the hop needs for the exfil tripwire and content classification, and a storage-specific lane is a second policy surface for no gain — the leg is one more guest dial.
- **Move the allow-list, resolver, tripwire, and OCSF emit into the object-store service.** Rejected: a control co-located with the component that touches file content is defeated by that component's compromise, and it would stand up a second resolver, contradicting [NFR-SEC-12](../manifesto/02-nfrs.md). The hop is out-of-process from both the guest and the object-store service.
- **A dedicated storage-egress sidecar (own process, own resolver) in the Egress zone.** Rejected: a standalone process adds a container to the set ([05-c4-container.md](../05-c4-container.md) §1) for no gain, and its own resolver violates the single-resolution-authority clause of [NFR-SEC-12](../manifesto/02-nfrs.md).

## Compliance impact

- `SOC2-CC6.1` / `ISO27001-A.8.10`: no in-deployment component holds the storage signing key, and the egress hop holds no credential — the guest forwards a scoped, time-bounded bearer the storage engine verifies.
- `NYDFS-500.15` / `DORA-Art.28`: the storage leg is a controlled, audited outbound path with an edge-authored event a compromised guest cannot suppress; third-party-storage access is governed and recorded.

## License impact

None. The storage leg reuses the already-bundled outbound-mediation edge ([ADR-0006](0006-egress-forward-proxy-substrate.md)); no new dependency is introduced.

## Threat mitigation

Re-homes P4-mount-D2 and P4-mount-E2 ([06-threat-model.md](../06-threat-model.md) §3.1) onto the single egress hop: the storage leg traverses an out-of-guest enforcement point — the single-hop no-bypass guarantee (one default route, no second socket, loopback blocked), the payload-independent exfil tripwire, and an edge-authored OCSF event — so no outbound path the control cannot see exists under guest compromise. The destination allow-list and connect-time deny are optional hardening on the same hop ([ADR-0016](0016-egress-baseline-inspection-hop-backend-scope.md)). P4-mount-T2 in-transit confidentiality ([06-threat-model.md](../06-threat-model.md) §4) re-anchors onto the hop's TLS ([NFR-SEC-85](../manifesto/02-nfrs.md)), off the now guest-egress-scoped [NFR-SEC-05](../manifesto/02-nfrs.md).

## Open questions

1. Per-session backend byte / rate ceiling on the storage leg — resource-exhaustion theme, [#188](https://github.com/Wide-Moat/open-computer-use/issues/188).
2. Whether plaintext DLP on user-data is mandatory or per-deployment on the storage path — content-blind theme, [#182](https://github.com/Wide-Moat/open-computer-use/issues/182).
