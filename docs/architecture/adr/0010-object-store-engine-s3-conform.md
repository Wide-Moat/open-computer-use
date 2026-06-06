<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-06-07
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
compliance-impact: [SOC2-CC6.1, ISO27001-A.8.10]
license-impact: none
threat-mitigation-link: ../06-threat-model.md
---

The Storage broker's object-store client speaks the S3 data-access API to a customer-provided engine; the guest's file-operation contract stays distinct from it, and the solo shelf bundles one Apache-2.0 local-filesystem S3 server as the reference.

# ADR-0010: Object-store engine is an S3-conform seam

## Status

`proposed`

## Context

The Storage broker ([component 04](../components/04-storage-broker.md)) is the sole component that speaks the backend object-store protocol ([NFR-SEC-25](../manifesto/02-nfrs.md)); the guest holds only a `filesystem_id` handle. Two things were left undecided: which engine the broker's object-store client speaks to, and which protocol it speaks ([component 04](../components/04-storage-broker.md) Shelf delta — "needs ADR: object-store engine selection; picks no engine"). [08-contracts.md](../08-contracts.md) frames the broker backend leg generically as "external backend protocol / conform", and the broker open question on whether the guest file-operation contract stays distinct from the backend API is unanswered ([#208](https://github.com/Wide-Moat/open-computer-use/issues/208)).

OCU is an ephemeral workspace ([04-non-goals.md](../manifesto/04-non-goals.md)): it retains no customer file bytes past the session, so the engine carries no retention, WORM, versioning, or erasure duty — those are the customer store's. What remains is a build/buy choice for a neighbouring system ([03-non-negotiables.md](../manifesto/03-non-negotiables.md)).

## Decision

The broker's object-store client speaks the S3 HTTP data-access API to a customer-provided engine, the guest↔broker file-operation contract stays distinct from that S3 API inside the object-store client, and the solo shelf bundles one Apache-2.0/MIT/BSD local-filesystem S3 server as the reference engine — no engine is bundled for production, and the ephemeral model attaches no retention, WORM, versioning, or erasure duty to the engine.

## Consequences

- The backend conform-contract is the S3 data-access subset — `PutObject` / `GetObject` / `ListObjectsV2` / `DeleteObject` over AWS Signature v4 — not the full AWS surface. [08-contracts.md](../08-contracts.md) narrows from "external backend protocol" to "S3 HTTP data-access API"; the broker conforms, it does not define ([NFR-SEC-16](../manifesto/02-nfrs.md)). Every store a regulated enterprise runs already exposes this subset (AWS S3, Ceph RGW, NetApp StorageGRID / ONTAP S3, Dell ECS / ObjectScale, Pure, VAST, Scality), so the broker targets one protocol and engine choice collapses to deployment config behind the `filesystem_id`→prefix map.
- **The two contracts stay distinct, and this closes [#208](https://github.com/Wide-Moat/open-computer-use/issues/208).** The south-face guest↔broker contract is the OCU-defined file-operation interface (open/read/write/list over FUSE/virtio-fs/9p, [08-contracts.md](../08-contracts.md)), deliberately POSIX-shaped, never S3. The broker's object-store client translates a file-operation verb into a broker-signed S3 request ([component 04](../components/04-storage-broker.md) invariant 2); the S3 API is never visible guest-ward. The boundary lives inside the object-store client — file-operation in, broker-signed S3 out.
- Positive: the broker's S3 client is identical on both shelves; only the endpoint and the credential substrate change ([component 04](../components/04-storage-broker.md) Shelf delta — host-local credential on the minimal shelf per [NFR-SEC-60](../manifesto/02-nfrs.md), STS-scoped per session on the full shelf per [NFR-SEC-25](../manifesto/02-nfrs.md)).
- Positive: production engines are customer-provided and not bundled — AWS S3, Ceph RGW (the reference object store in [05-licensing-posture.md](../manifesto/05-licensing-posture.md)), or any S3-compatible appliance. OCU owns no engine CVE, SBOM, or version lifecycle.
- The solo shelf bundles one Apache-2.0 local-filesystem S3 server so the one-click path has an object store with no customer infrastructure — lead candidate `versitygw` (Apache-2.0, single Go binary, S3-over-local-filesystem), with the final binary fixed in the component spec per the [ADR-0006](0006-egress-forward-proxy-substrate.md) pattern. Unlike the audit WORM seam ([ADR-0009](0009-audit-pipeline-pluggable-by-contract.md)) whose solo default can be "none — the file system is the floor", the broker needs a real S3 endpoint on every shelf, so a reference engine is required.
- Negative: "S3-compatible" is not "S3-identical" — Ceph RGW implements a subset and appliances vary. The four-operation data-access subset (`PutObject` / `GetObject` / `ListObjectsV2` / `DeleteObject`) is the contract ceiling; no feature outside it is assumed.
- Neutral: this resolves the engine half of the [component 04](../components/04-storage-broker.md) Shelf-delta picks; the broker runtime tier stays a separate decision (its own ADR). Per-tenant instantiation ([NFR-SEC-76](../manifesto/02-nfrs.md)) is unchanged.

## Alternatives considered

- **Bundle a production engine (ship Ceph or MinIO, own its lifecycle).** Rejected: an object store is a neighbouring system that runs without OCU, so bundling it for production violates the build-scope principle and takes on a CVE surface the customer's platform team already operates. MinIO is also AGPL ([05-licensing-posture.md](../manifesto/05-licensing-posture.md) rejection table) and has moved to a maintenance posture; Garage is AGPL — both fail the licence gate, recorded so neither is re-proposed.
- **Leave the backend protocol generic ("any object store the broker is configured for").** Rejected: a generic protocol forces the broker to carry per-engine SDKs and leaves #208 open. Fixing the S3 data-access subset gives one client and one signing path.
- **Make the guest speak S3 directly to the store (skip the broker translation).** Rejected: violates [NFR-SEC-25](../manifesto/02-nfrs.md) — the guest would hold a backend credential and the broker would no longer be the sole object-store speaker; the per-session prefix isolation ([NFR-SEC-31](../manifesto/02-nfrs.md)) could not be host-enforced.

## Compliance impact

- `SOC2-CC6.1` / `ISO27001-A.8.10`: backend-credential confidentiality holds because the broker is the sole S3 speaker and the guest never receives a backend key; the engine choice does not change this property on either shelf.

## License impact

No production engine is bundled. The solo reference engine is Apache-2.0/MIT/BSD (lead candidate `versitygw`, Apache-2.0); its Bill-of-Materials row in [05-licensing-posture.md](../manifesto/05-licensing-posture.md) lands when the component spec fixes the final binary, per the [ADR-0006](0006-egress-forward-proxy-substrate.md) pattern. Customer-provided engines are integrated over the S3 API and carry no OCU lifecycle.

## Threat mitigation

Addresses Information Disclosure on the backend leg: the S3 API terminates inside the broker's object-store client, the request is broker-signed, and the egress edge forwards it allow-list-only without TLS termination ([ADR-0006](0006-egress-forward-proxy-substrate.md)), so the broker-signed request is byte-intact ([NFR-SEC-16](../manifesto/02-nfrs.md)) and no S3 credential or endpoint reaches the guest.
