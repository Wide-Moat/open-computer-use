<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-06-14
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
amends: [0010]
blocks: [0017]
blockedBy: [0013]
compliance-impact: [SOC2-CC6.1, ISO27001-A.8.10, NYDFS-500.15, DORA-Art.28]
license-impact: none
threat-mitigation-link: ../06-threat-model.md
---

Cuts storage into planes named by the trust boundary each one fronts — mount-plane, Web UI, parser-sandbox, and the object-store service — and retires the compass-direction identity. Audience: anyone editing the storage component specs, the container set, or the threat model.

# ADR-0015: Storage decomposition by trust plane

## Status

`proposed`

## Context

The storage component carried four distinct counterparties under one identity, named by a picture's compass direction — a "south face" (the guest mount) and a "north face" (the file-artifact data plane), "two faces on one object-store client". A direction is not a trust statement: the two faces front different counterparties, with different custody, different reachability, and different blast radius, yet shared one component identity and one set of invariants. That weld put the session-minting authority and the preview-render of untrusted artifact bodies in the same boundary as the backend-key-adjacent path, and left [#218](https://github.com/Wide-Moat/open-computer-use/issues/218) — parser isolation for untrusted preview bodies — without a boundary to sit behind.

The custody ADR ([storage-credential-custody](0013-storage-credential-custody.md)) fixes who holds the storage signing key: the Control plane mints and signs a scoped, time-bounded weak Storage-JWT, holds its signing key, and publishes the JWKS the Egress trust-edge validates against; the guest holds that weak session JWT, which the Egress trust-edge validates and exchanges at the #3 counterparty for the real filestore credential ([ADR-0019](0019-egress-exchanges-filestore-credential.md)); no in-guest part holds a signing key. With the storage signing key pinned at the Control plane and out of the guest, the single-credential argument that justified the weld no longer holds — the planes can be cut by their counterparty without moving any key.

Three facts bound the cut. The in-guest mount client and the in-guest transport are one binary, one config, one process — the guest dials its mount endpoint directly. A memory store is selected per mount entry by `memory_store_id` instead of `filesystem_id`, mutually exclusive, with its own scoped bearer, quota dimensions, and verb set. The control verbs (import / migrate / remove) act on a whole filesystem, not a file.

## Decision

We will decompose storage into four parts named by the trust boundary each fronts, and retire "south face / north face / two faces of one object-store client" as component identity:

| Part | Counterparty | Holds a backend key | Aggregate root |
|---|---|---|---|
| **Mount-plane** | the untrusted guest | no (holds a `filesystem_id`-scoped weak session JWT the edge exchanges) | the running session |
| **Web UI** | an external data-plane client (E5), OUR design | no | artifact + embed-asserted principal |
| **Parser-sandbox** | untrusted artifact bodies (preview-render, archive ingest) | no signer, no key | — |
| **Object-store service** | the storage engine (engine adapter + `filesystem_id`→prefix + multipart) | no (capability-free; the Control plane mints + holds the storage signing key; the guest holds a weak session JWT the edge exchanges) | — |

The mount-plane is the `filesystem_id`-scoped file-operation interface (open / read / write / list / preview) plus the whole-filesystem control verbs (import / migrate / remove) the guest reaches. The Web UI is the client file/artifact HTTP API, the embeddable SPA, and preview-render, reached over an embed-token→first-party-session flow; it is an OCU design addition. The parser-sandbox is a capability-free boundary for content validation, carrying the preview-render isolation #218. The object-store service is the part that earns the "storage" name: it speaks a first-party filestore HTTP/RPC surface ([ADR-0010](0010-storage-backend-pluggable-adapter.md) generalizes the engine to local-volume + S3) and holds no signing key.

**In-guest fusion.** The in-guest mount client and the in-guest transport stay one binary. The cut separates the host-side Web UI, the parser-sandbox, and the issuer; it does not split the in-guest client from its transport. A split there adds a process boundary with no custody or counterparty gain.

**Memory store is a sibling mount-type.** A `memory_store_id` mount is a sibling of a `filesystem_id` mount behind a `MemoryProvider`-style seam — one selected per mount entry, mutually exclusive, sharing the one governed egress with no bypass, with its own scoped bearer and quota dimensions. It is not folded into the filestore and not a second parallel credential.

## Consequences

- The Web UI gets its own component spec ([08-web-ui.md](../components/08-web-ui.md)); the moved invariants and the P4-artifact STRIDE rows land there, not on the object-store service. Its deployable and repository boundary is stated in the repo-boundary ADR ([control-plane-repo-boundary](0017-control-plane-repo-boundary.md)), which this decomposition blocks — that ADR cannot record the Web UI deployable until the plane it names exists.
- [#218](https://github.com/Wide-Moat/open-computer-use/issues/218) now has a home: preview-render runs in the parser-sandbox, a capability-free boundary, so an untrusted artifact body cannot reach the session-minting authority or any key-adjacent path. The session-minter (Web UI) and the untrusted-body parser stop being co-resident.
- [06-threat-model.md](../06-threat-model.md) P4 splits into P4-mount (the guest counterparty) and P4-artifact (the E5 counterparty), cut by counterparty.
- The glossary retires "South face / north face" and "two faces" and defines Mount-plane, Web UI (OUR design), Parser-sandbox, and the object-store service once.
- [05-c4-container.md](../05-c4-container.md) §3 carries the object-store service and the Web UI; the container count is restated as a then-true observation, not an invariant, so the Web UI carve-out is not pre-rejected on count.
- Memory and filestore are separate quota and verb surfaces sharing one egress; the `MemoryProvider` seam exists so adding a memory store later changes no plane boundary.
- The whole-filesystem control verbs (import / migrate / remove) sit on the mount-plane, not the file-level read path, so their authorization is a filesystem-scope decision distinct from a per-file one.

## Alternatives considered

- **Keep the welded "two faces, one object-store client" (KEEP_FUSED).** Rejected: the single-backend-credential argument does not require fusing the guest transport, the client API, and the object-store service into one identity. With the storage signing key pinned at the Control plane by the custody ADR, the planes have different counterparties (untrusted guest vs external E5 client) and different aggregate roots (session vs artifact-plus-principal); one identity cannot carry both sets of invariants without re-creating the co-residency this ADR removes.
- **Split the in-guest client from its transport.** Rejected: the direction question this addresses is already settled by the transport ADR ([storage-transport-tier-universal-network-leg](0014-storage-transport-tier-universal-network-leg.md)), which pins the data leg as one guest-dialled network endpoint; the in-guest mount client and its transport are one binary, and prying them apart adds a process boundary with no custody or counterparty gain. The cut that matters is by counterparty (host-side Web UI, parser-sandbox, off-box issuer), not by transport.

## Compliance impact

- `SOC2-CC6.1` / `ISO27001-A.8.10`: each plane states the credentials it holds; no plane that serves untrusted content or mints a session holds a key, so the access-control boundary is auditable per plane rather than per the welded component.
- `NYDFS-500.15` / `DORA-Art.28`: the Web UI and the object-store service are distinct deployables with distinct counterparties, so third-party data-plane access and backend access are governed and recorded on separate boundaries.

## License impact

None. The decomposition renames and re-homes existing surfaces; no new dependency is introduced. The parser-sandbox substrate selection is deferred to its component spec.

## Threat mitigation

Re-anchors P4 by counterparty: P4-mount fronts the untrusted guest, P4-artifact fronts the external E5 client, and the parser-sandbox isolates untrusted artifact bodies from the session-minter and any key-adjacent path, closing the #218 co-residency. No plane holds a signing key, so a compromise of any plane is bounded to that plane's counterparty rather than the storage engine.

## Open questions

1. ~~Parser-sandbox substrate (process boundary vs in-language capability confinement) — [#218](https://github.com/Wide-Moat/open-computer-use/issues/218).~~ Resolved by [ADR-0026](0026-parser-sandbox-substrate.md): substrate is chosen per render location — ingest in-language, body render browser null-origin iframe, server heavy-parser process-boundary deferred behind a trigger.
2. Whether `memory_store_id` is a recognized v1 mount-plane scope class or scoped out with a tracking issue — [#188](https://github.com/Wide-Moat/open-computer-use/issues/188).
