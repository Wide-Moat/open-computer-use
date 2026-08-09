<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-08-09
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
amends: ['0019-egress-exchanges-filestore-credential.md']
compliance-impact: [SOC2-CC6.1, SOC2-CC6.6, ISO27001-A.8.10, NYDFS-500.15, DORA-Art.28]
license-impact: none
threat-mitigation-link: ../components/06-egress-trust-edge.md
---

Fixes who runs the RFC 8693 exchange and where its root key material rests on each shelf — for anyone building the exchange, sizing the Bill of Materials, or auditing storage-credential custody.

# ADR-0046: The exchange counterparty is ours, rooted in static config

## Status

`proposed` — amends [ADR-0019](0019-egress-exchanges-filestore-credential.md), which fixes that the edge exchanges the weak session JWT for a real filestore credential but leaves the counterparty itself unnamed. Closes the owner call recorded in roadmap gap A2.

## Context

The storage leg carries two credentials. The Control plane mints the weak, edge-only session JWT ([NFR-SEC-60](../manifesto/02-nfrs.md)) from a Control-plane-local signing key and publishes a JWKS. The Egress trust-edge exchanges that assertion, over RFC 8693, for the real filestore credential it injects; [ADR-0042](0042-engine-credential-verification-anchor.md) anchors the engine's verification on that issuer's JWKS.

The issuing side has no shipping component. `test/harness/exchange/` stands in for it on the stand, so a clean deployment from repository artifacts has no counterparty at all.

Two candidates were carried: bundle OpenBao as the issuer, or ship no issuer and document an integration contract a customer's own authority satisfies. The choice was read as a vendor selection. It is not one, because the shelf split for root key material is already ratified: [NFR-SEC-59](../manifesto/02-nfrs.md) puts the root in the SDS source — "a customer store HSM-resident on the full shelf, FIPS 140-3 L3; **a static file on the solo shelf**" — and NFR-SEC-60 already makes the Control-plane-local signing key the baseline on every shelf.

A bundled secret manager on the solo shelf would therefore guard material canon permits in a file, while adding a heavyweight bundled dependency: vulnerability scanning, version pinning, CVE response, and a Bill-of-Materials row, all against the one-click solo install this platform holds as an NFR invariant.

## Decision

We will build the exchange counterparty ourselves and bundle no secret manager.

- **The counterparty is an OCU component, not a vendored product.** It implements the RFC 8693 token exchange with per-`{filesystem_id, intent}` keyed issuance and per-session caching, and publishes the JWKS ADR-0042's engine verifies against. It replaces `test/harness/exchange/` as the shipping artifact.
- **Its root key material follows the ratified shelf split.** On the solo shelf the issuing key is a static file the deployment mounts read-only, the same shape NFR-SEC-59 already permits for the SDS source. On the full shelf the counterparty holds no root: it delegates issuance to a customer-provided credential authority over a documented contract, so the root stays HSM-resident on the customer's side (NFR-FLEX-04).
- **The shelf is a configuration choice, not a build.** One binary serves both; the deployment selects static-file or delegated mode. A delegated deployment that names no authority fails closed at boot rather than silently falling back to the static key.
- **We bundle no secret manager.** OpenBao, Vault, and equivalents stay out of the Bill of Materials. A customer already running one reaches it through the full-shelf delegation contract, not through a copy we ship.

## Consequences

The Bill of Materials gains no secret-manager row, and the solo shelf keeps a one-click install with no additional service to run. We own the exchange binary: its correctness, its key handling, and its CVE surface are ours, where a bundled product would have carried an upstream's.

The static-file root on the solo shelf is a declared residual, not a hidden one. It is the same posture NFR-SEC-59 already states for the SDS source, and it is the reason the solo shelf makes no in-process-memory secrecy claim against a host-root adversary.

Roadmap A2 stops being an owner call and becomes ordinary build work. ADR-0019 and ADR-0005 can ratify once the counterparty ships, and gap B1's remaining half — the shipped manifests enabling verification — gains a real issuer to point at.

## Alternatives

**Bundle OpenBao as the issuer.** Rejected. It guards on the solo shelf what NFR-SEC-59 already permits in a file, and buys that with a bundled dependency carrying full vuln-scanning, pinning, and CVE-response duty plus a BoM row — against an NFR invariant that the solo install stays one click. Its MPL-2.0 licence passes our allow-list, so this is a scope and ownership call, not a licensing one.

**Ship no issuer; require a customer authority on every shelf.** Rejected. It leaves the solo shelf with no working storage leg out of the box, breaking the dual-audience requirement that a solo builder can run the platform without an enterprise secret manager.

**Keep the harness and defer.** Rejected. The harness is not deployable, so every downstream row — A2, the ADR-0019/0005 ratifications, and B1's manifest half — stays blocked on a component nobody is building.
