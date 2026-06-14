<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-06-01
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
compliance-impact: [SOC2-CC6.1, ISO27001-A.8.24, NYDFS-500.15, PCI-DSS-Req.3]
license-impact: none
threat-mitigation-link: ../02-trust-boundaries.md
---

Egress credential delivery uses off-the-shelf Envoy SDS; OCU stores, mints, and rotates no upstream credential.

# ADR-0005: Egress credential delivery is off-the-shelf Envoy SDS

## Status

`proposed`

## Context

The Egress trust-edge (zone 4, [02-trust-boundaries.md](../02-trust-boundaries.md)) attaches upstream authorization on the outbound leg so the guest never holds the real credential (NFR-SEC-23 invariant). Behind that injection sits a source question: where the credential rests, what API the edge calls to fetch it, and who owns its lifecycle.

Envoy's Secret Discovery Service (SDS, gRPC xDS) is a standard protocol for runtime secret delivery to a proxy, with hot-swap on push. Envoy's native `credential_injector` filter attaches an Authorization header on the outbound leg. Both are off-the-shelf and require no OCU code for credential delivery, minting, or rotation. A solo operator points SDS at a static file; a regulated enterprise points it at a customer-provided SDS-compatible store over the same protocol.

## Decision

The Egress trust-edge receives the upstream credential over Envoy SDS; the SDS source is a static file (solo deployments) or a customer-provided SDS-compatible store (enterprise deployments). Envoy's `credential_injector` filter attaches the Authorization header on the outbound leg. OCU stores, mints, and rotates no upstream credential. Credential minting, rotation, revocation, and per-issuance audit are the SDS source's responsibility: the customer's store on the enterprise shelf, an operator-managed artifact on the solo shelf.

## Consequences

- Zone count is five (was six). Credential custody is no longer a separate zone or container; credential attachment is a capability of the Egress trust-edge. Threat-model rows in [`06-threat-model.md`](../06-threat-model.md) and token-taxonomy rows in [`02-trust-boundaries.md`](../02-trust-boundaries.md) §8 that named Credential custody re-anchor to the Egress trust-edge and the SDS source.
- The solo path stays zero-config. A static file source has no stateful service, no unseal step, and no key infrastructure: the operator places the credential file on the host and points Envoy SDS at it. The minimal-shelf long-lived key is admissible only under NFR-SEC-60; the edge process memory is not a secret store against host-root.
- The enterprise path delegates lifecycle to the customer store. The customer provides an SDS endpoint (a gRPC address) that Envoy queries; that store owns unseal, dynamic-secret issuance, rotation, revocation, and audit. OCU documents the SDS contract — the Secret resource shape, TTL and refresh behavior, error behavior — and the customer operates the store.
- Upstream authorization is attached at the boundary, never in the guest. The guest carries no long-lived upstream secret on the egress leg (it may hold a short-lived session-scoped handle, which is not the upstream credential); Envoy's `credential_injector` attaches the credential on the edge-originated upstream leg before forwarding. The NFR-SEC-23 invariant (the real upstream secret never enters the guest) holds. The mechanism that attaches it — edge-inject here, or a protocol broker for a high-value scoped credential — is selected per upstream in [ADR-0007](0007-egress-auth-mechanism.md).
- The bespoke `F8` lease-pull gRPC protocol (issue [#205](https://github.com/Wide-Moat/open-computer-use/issues/205)), the STS delegator, the per-session lease-issue audit event, and the OCU-enforced TTL and revoke bounds are removed: they governed an OCU minting service that does not exist when Envoy SDS is the delivery path.
- The Egress trust-edge ([component 06](../components/06-egress-trust-edge.md)) records `0005` in its `adr:` front-matter. The SDS source binding (static file or customer endpoint) is a component-spec wiring detail.
- Envoy (Apache-2.0) is the egress edge and a bundled dependency. See the Bill of Materials in [`manifesto/05-licensing-posture.md`](../manifesto/05-licensing-posture.md).

## Alternatives considered

- **Bespoke `F8` lease-pull protocol plus an OCU STS delegator.** Rejected: Envoy SDS is an open, implemented standard. A proprietary lease-pull wire protocol and minting service add code, audit surface, CVE liability, and operational cost for a property SDS already delivers, and grant no security property SDS lacks.
- **An OCU-bundled secret store (OpenBao, or a thin SDS server OCU runs).** Rejected: the store's governance — unseal, rotation policy, audit sink, key custody — is the customer's. Bundling a store breaks the solo one-click path with stateful infrastructure and duplicates machinery the customer already operates. OCU stays a consumer of the SDS API.
- **Inject the credential inside the guest (sandbox mount, env var, or guest-side config).** Rejected: violates NFR-SEC-23. A guest with in-sandbox root extracts the secret from memory, `/proc`, or the filesystem. The edge boundary holds the secret outside the guest, where injection keys on a presented scoped credential, never on network origin ([ADR-0007](0007-egress-auth-mechanism.md), the P6-E2 anti-pattern).

## Compliance impact

- `SOC2-CC6.1` / `ISO27001-A.8.24`: secret confidentiality is realized by the SDS source — a customer store (enterprise) or a static file (solo). No OCU key-management policy is present to audit.
- `NYDFS-500.15`: encryption of nonpublic information in transit (the upstream authorization header) holds on the edge-originated TLS leg and on the customer store's TLS to its SDS endpoint.
- `PCI-DSS-Req.3`: stored-credential protection is the customer store's on the enterprise shelf; the solo shelf rests the credential in a static file under authenticated encryption (the file primitive is a component-spec choice, not this decision).

## License impact

Envoy is Apache-2.0 and is bundled. No stateful secret store is bundled by this decision.

## Threat mitigation

Addresses Information Disclosure and credential-compromise paths at the Egress trust-edge (the credential is attached only on the edge-originated upstream leg, where the request's network identity is known) and on the guest→upstream path (the upstream secret never enters the guest, per NFR-SEC-23). The deferred maturity question on Envoy's `credential_injector` / OAuth2 filter for untrusted upstreams is tracked in [component 06](../components/06-egress-trust-edge.md) Open questions.
