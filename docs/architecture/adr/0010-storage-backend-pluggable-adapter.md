<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-06-14
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
amended-by: [0013, 0015, 0016]
compliance-impact: [SOC2-CC6.1, ISO27001-A.8.10]
license-impact: none
threat-mitigation-link: ../06-threat-model.md
---

The object-store service owns the guest file-operation contract and drives the storage engine through a pluggable engine adapter — a local volume and an S3 store from day one — so the guest never sees the backend protocol and no engine is bundled for production.

# ADR-0010: Storage engine is a pluggable adapter behind the object-store service

## Status

`proposed` — amended by [ADR-0015](0015-storage-decomposition-by-trust-plane.md), [ADR-0013](0013-storage-credential-custody.md), and [ADR-0016](0016-egress-baseline-inspection-hop-backend-scope.md).

## Context

The object-store service ([component 04](../components/04-object-store-service.md)) is the sole component that speaks the backend protocol ([NFR-SEC-25](../manifesto/02-nfrs.md)); the guest holds only a `filesystem_id` handle and issues file-operation verbs that name no backend object (invariant 2). Which engine sits behind that service was deferred — [component 04](../components/04-object-store-service.md) Shelf delta carried `needs ADR: object-store engine selection`, and the same question is phrased identically as an open item in [08-contracts.md](../08-contracts.md) §6 ([#208](https://github.com/Wide-Moat/open-computer-use/issues/208)): does the file-operation contract stay distinct from any object-store API at every shelf, and where is that boundary asserted.

OCU is an ephemeral workspace ([04-non-goals.md](../manifesto/04-non-goals.md)): it retains the audit record of file activity, never the customer file bytes, so the engine carries no retention, WORM, versioning, or erasure duty — those belong to the customer's store. Under the build-scope principle ([03-non-negotiables.md](../manifesto/03-non-negotiables.md)) an object store is a neighbouring system that runs when OCU is stopped.

## Decision

The object-store service drives the storage engine through a pluggable engine adapter: the guest↔service file-operation contract is OCU-defined and stays distinct from the backend protocol at every shelf, a local-volume engine and an S3 engine are both present from day one, and no engine is bundled for production.

## Consequences

- **The two contracts stay distinct, and this closes [#208](https://github.com/Wide-Moat/open-computer-use/issues/208).** The guest↔service contract is the OCU-defined file-operation interface (open/read/write/list over FUSE, a component-spec choice, [08-contracts.md](../08-contracts.md)), deliberately POSIX-shaped, never the backend protocol. The boundary is asserted inside the object-store service: invariant 2 ([component 04](../components/04-object-store-service.md)) — no caller request names a backend object directly — is the falsifiable statement of the split. The engine choice is the role `conform` backend leg ([08-contracts.md](../08-contracts.md)); the file-op mount is the role `define` surface.
- Positive: swapping the engine changes neither the file-operation contract nor any of the object-store service's invariants ([component 04](../components/04-object-store-service.md)) — substrate and transport are component-spec choices, not contract. A later engine (e.g. a cloud object store) is a third adapter behind the unchanged contract, with the guest mount and the schema untouched.
- Positive: the local-volume engine has no network leg, so the minimal shelf runs from one `docker-compose up` with no external object store and no cloud credential, holding the one-click-solo invariant ([03-non-negotiables.md](../manifesto/03-non-negotiables.md)). The egress-transit invariant ([NFR-SEC-25](../manifesto/02-nfrs.md)) applies to a network engine's leg, not to the local-volume engine, which has nothing to transit.
- Positive: production engines are customer-provided and not bundled — AWS S3, Ceph RGW (the reference object store in [05-licensing-posture.md](../manifesto/05-licensing-posture.md)), or any S3-compatible store. OCU owns no engine CVE, SBOM, or version lifecycle, mirroring [ADR-0009](0009-audit-pipeline-pluggable-by-contract.md)'s no-CVE posture.
- Neutral: resolves the engine half of the [component 04](../components/04-object-store-service.md) Shelf-delta picks; the object-store service runtime tier is a separate concern, resolved in [component 04](../components/04-object-store-service.md) §Operational concerns at the [NFR-SEC-02](../manifesto/02-nfrs.md) hardened-`runc` floor (profile-independent, no tier ladder). Per-tenant instantiation ([NFR-SEC-76](../manifesto/02-nfrs.md)) and the credential substrate ([NFR-SEC-60](../manifesto/02-nfrs.md) / [NFR-SEC-25](../manifesto/02-nfrs.md)) are unchanged — both engines serve both shelves, differing only in whether the engine credential is a host filesystem permission (local volume) or a backend key (network engine).
- Negative: the local-volume engine is durability/HA-naive (single host, no erasure coding) and is a solo-reference only; a production deployment wires the S3 engine to its own store. OCU makes no durability promise for the local-volume path.
- Negative: the file-operation contract must carry chunked upload and Range read as first-class verbs so a large object never crosses as one message; this puts the size ceiling in the object-store service's chunk policy, not the engine, and obliges every adapter to translate chunking to the backend's transfer model.

## Alternatives considered

- **Make S3 the conformance target — the service's contract is the S3 API, solo bundles an S3 server (the prior closed draft).** Rejected: inverts the canon topology — [component 04](../components/04-object-store-service.md) invariant 2 makes the guest speak a file-operation interface that names no backend object, and [08-contracts.md](../08-contracts.md) already separates the `define` mount leg from the `conform` backend leg. Collapsing them re-exposes the backend protocol guest-ward, contradicts [NFR-SEC-25](../manifesto/02-nfrs.md), and fails [#208](https://github.com/Wide-Moat/open-computer-use/issues/208) by denying the distinction it asks us to assert.
- **Bundle a production engine (ship Ceph or MinIO and own its lifecycle).** Rejected: an object store is a neighbouring system that runs without OCU, so bundling it for production violates the build-scope principle ([03-non-negotiables.md](../manifesto/03-non-negotiables.md)) and the durable-store non-goal ([04-non-goals.md](../manifesto/04-non-goals.md)), and takes on a CVE surface the customer's platform team already operates. MinIO's community edition is AGPL ([05-licensing-posture.md](../manifesto/05-licensing-posture.md) rejection table).
- **Ship one engine (S3 only), add local-volume later.** Rejected: breaks the one-click-solo invariant ([03-non-negotiables.md](../manifesto/03-non-negotiables.md)) — the minimal shelf would require an external object store and a credential before the first session. The local-volume engine is what lets the solo path run with no external service, so both exist from day one.

## Compliance impact

- `SOC2-CC6.1` / `ISO27001-A.8.10`: backend-credential confidentiality holds because the object-store service is the sole backend-protocol speaker and the guest never receives a backend key; the engine choice does not change this property on either shelf.

## License impact

No production engine is bundled. The local-volume reference engine is OCU code over the host filesystem and pulls in no third-party dependency. Customer-provided engines are integrated over the backend protocol and carry no OCU lifecycle.

## Threat mitigation

Addresses Information Disclosure on the backend leg: the object-store service is the sole speaker of the backend protocol to the storage engine. The guest mount client presents its weak session JWT as a static bearer over the single TLS-terminating egress hop; the Egress trust-edge validates that JWT and exchanges it at the issuer for the real filestore credential it injects toward the service, and the storage engine enforces scope on that injected credential ([ADR-0013](0013-storage-credential-custody.md), [ADR-0016](0016-egress-baseline-inspection-hop-backend-scope.md), [ADR-0019](0019-egress-exchanges-filestore-credential.md)). The exchange is a header overwrite at the TLS-terminating hop, not a per-request re-signature; there is no per-request signature to preserve. A local-volume engine opens no network leg, so the in-transit obligation is vacuous for it.
