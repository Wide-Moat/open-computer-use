<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-06-14
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
blocks: []
blockedBy: [0013]
compliance-impact: [SOC2-CC6.1, NIST-SP-800-190, DORA-Art.28]
license-impact: none
threat-mitigation-link: ../06-threat-model.md
---

Pins the guest storage data leg as a tier-universal outbound network endpoint and separates it from the exec/control channel. Audience: anyone touching the storage transport, the Session sandbox substrate, or the mount contract.

# ADR-0014: Storage data leg is a tier-universal network endpoint

## Status

`proposed`

## Context

The guest reaches its storage backend over a leg whose direction and reachability were left to the component spec ("transport is a component-spec choice"), while [05-c4-container.md](../05-c4-container.md) §4 drew the storage flow (F7) as "host dials guest" — the same arrow as the exec/control channel (F6). A guest-facing leg whose endpoint and direction are unpinned admits a host-dialled in-guest unix socket, which cannot cross a microVM kernel boundary ([ADR-0003](0003-sandbox-runtime-tier-ladder.md) defers that tier); the drawn-as-F7 storage leg then conflicts with the frozen mount contract, whose `service_url` is constrained `^https://` ([08-contracts.md](../08-contracts.md) §1).

The mount client holds four reused outbound TCP/443 connections to an HTTPS `service_url` (HTTP/2, Connect-RPC) and no AF_UNIX or vsock on the data path. The leg is guest-dialled-out on every tier; each tier has a guest network stack, so the same endpoint shape holds for `runc`, gVisor, and the deferred microVM tier. A distinct host→guest push delivers the mount configuration (filesystem_id, service_url, JWT, CA certificate, paths) before the mount client starts — the only host-originated storage step, separate from the data leg it configures.

## Decision

The guest storage data leg is one tier-universal network endpoint — the in-guest mount client dials an HTTPS `service_url` (HTTP/2, Connect-RPC) outbound on every tier — pinned as a tier-keyed transport seam that resolves to a network endpoint on each tier ([ADR-0003](0003-sandbox-runtime-tier-ladder.md)): `runc` → network, gVisor → network, microVM → network (deferred with the tier). The host-dials-guest unix-socket/vsock ladder ([NFR-SEC-43](../manifesto/02-nfrs.md)) carries the exec/control channel only, never storage; the host→guest mount-provisioning push that delivers the mount configuration is a third, separate channel from the data leg.

## Consequences

- Positive: the leg is tier-portable by construction. Because every tier ([ADR-0003](0003-sandbox-runtime-tier-ladder.md)) gives the guest a network stack, the same outbound `service_url` dial works under `runc`, gVisor, and the deferred microVM tier — no host-dialled in-guest socket is baked, so nothing in the storage path breaks when the microVM tier lands. The Session sandbox ([component 05](../components/05-session-sandbox.md)) reaches storage by dialling one network name outbound, retargeted-denied at the storage engine by the filesystem_id binding ([ADR-0013](0013-storage-credential-custody.md)).
- Positive: on a network-engine shelf, storage shares the single governed outbound hop. The data leg traverses the Egress trust-edge ([component 06](../components/06-egress-trust-edge.md)) like every other guest-originated dial — one default route, no second socket — so it is not a privileged second exit. "Single governed hop" here means one TLS-inspecting hop with no second socket (the permissive baseline of [ADR-0016](0016-egress-baseline-inspection-hop-backend-scope.md)), not a deny-by-default allow-list ([NFR-SEC-16](../manifesto/02-nfrs.md)). The egress hop is a shelf property of the leg, not an invariant: on the minimal/dev shelf a local-volume engine ([ADR-0010](0010-storage-backend-pluggable-adapter.md)) opens no network leg and the leg does not traverse the gateway at all.
- Neutral: [05-c4-container.md](../05-c4-container.md) §4 splits the single F7 arrow into a host→guest provisioning push and a guest-out data leg; the two-leg model lands in [08-contracts.md](../08-contracts.md) §1 (ProvisionMountConfig host→guest, the mount-config guest-out data leg). The container count is a then-true observation, not an invariant, and this split adds no container.
- Negative: the data leg runs over the same guest network stack a compromised guest controls, so confidentiality and scope cannot rest on the transport. They rest off the leg — TLS on the egress hop plus the storage engine's validation of the filesystem_id claim — not on a host-private socket. The exec/control channel's host-attested-caller invariant ([NFR-SEC-43](../manifesto/02-nfrs.md), [NFR-SEC-76](../manifesto/02-nfrs.md)) is scoped to that channel and does not transfer to the storage leg.
- Neutral: the seam is a network endpoint on every tier, so the only baked variation across tiers is the in-guest VFS substrate, not the leg's direction or reachability. A host-private storage socket is not a tier rung of this seam; an exec/control-style host-dialled channel ([NFR-SEC-43](../manifesto/02-nfrs.md)) carries control, never the data leg, so nothing reintroduces a baked unix socket on the storage path.

## Alternatives considered

- **Leave the transport a component-spec choice.** Rejected: an unpinned guest-facing leg let a host-dialled in-guest unix socket get baked, which cannot cross a microVM kernel boundary and contradicts the `^https://` `service_url` in the frozen mount contract ([08-contracts.md](../08-contracts.md) §1). A guest-facing leg's direction, reachability, and endpoint are trust-tier properties, not spec discretion; only the in-guest VFS substrate (FUSE/virtio-fs/9p) stays a spec choice.
- **Model storage as a host-pushed mount on the F7 "host dials guest" channel.** Rejected: it contradicts the frozen mount contract's guest-out `service_url` and folds the data leg into the exec/control channel, so a single host-dialled arrow would carry two traffic classes with different counterparties — the host control plane on one side, the storage backend on the other — and the data path would inherit the exec channel's host-attested-caller invariant it cannot satisfy. The host originates only the provisioning push; the data leg is guest-dialled-out.

## Compliance impact

- `NIST-SP-800-190` §4: the storage data path is an explicit, single-route outbound leg, not an ad-hoc host-guest socket; isolation between the exec/control channel and the data leg is declared, not incidental.
- `SOC2-CC6.1`: scope and confidentiality on the leg rest on the storage engine's filesystem_id-claim validation and TLS, recorded where the credential custody is recorded ([ADR-0013](0013-storage-credential-custody.md)), not on transport reachability.
- `DORA-Art.28`: the storage leg is a declared outbound dependency reachable over one governed hop, recordable in the register of information.

## License impact

None. The leg reuses the bundled Egress trust-edge ([ADR-0006](0006-egress-forward-proxy-substrate.md)); no dependency is introduced.

## Threat mitigation

Re-anchors the storage-leg direction in [06-threat-model.md](../06-threat-model.md) §3 (P4-T1/I2/S1) onto a guest-out network dial, off the prior host-dialled drawing. The exec/control channel's no-guest-reachable-network invariant ([NFR-SEC-43](../manifesto/02-nfrs.md)) and host-peer accept ([NFR-SEC-76](../manifesto/02-nfrs.md)) stay scoped to F6; the storage leg's deny rests at the Egress trust-edge hop and at the storage engine's `filesystem_id` binding, not on the exec channel's attribution. This ADR's leg deny cites the storage-engine `filesystem_id`-claim scope ([ADR-0013](0013-storage-credential-custody.md)) and the single-governed-hop reading of NFR-SEC-16 ([ADR-0016](0016-egress-baseline-inspection-hop-backend-scope.md)).

## Open questions

1. Tier-keyed host-private storage seam if a deployment forbids the guest-out leg — deferred with the microVM tier, [#161](https://github.com/Wide-Moat/open-computer-use/issues/161).
