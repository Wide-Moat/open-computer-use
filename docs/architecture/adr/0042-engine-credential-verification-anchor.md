<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-08-07
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
amends: ['0019-egress-exchanges-filestore-credential.md']
compliance-impact: [SOC2-CC6.1, SOC2-CC6.6, ISO27001-A.8.10, NYDFS-500.15, DORA-Art.28]
license-impact: none
threat-mitigation-link: ../components/04-object-store-service.md
---

Fixes which key the storage engine verifies an injected credential against, how that key reaches it, and what a deployment must do to run unverified — for anyone wiring the storage leg or auditing its custody.

# ADR-0042: The engine's credential verification anchor

## Status

`proposed` — amends [ADR-0019](0019-egress-exchanges-filestore-credential.md), which fixes the exchange but leaves the engine side at "enforces scope on the injected credential" without pinning the verification anchor, the JWKS delivery, or the default posture. Closes the open half of roadmap gap B1.

## Context

Two issuers sit on the storage leg. The Control plane mints the weak session JWT the guest holds and the egress edge validates. A separately-named credential authority issues the real filestore credential the edge injects after the RFC 8693 exchange. [ADR-0013](0013-storage-credential-custody.md) calls the weak JWT an edge-only assertion `ocu-filestore` does not accept, and [NFR-SEC-31](../manifesto/02-nfrs.md) says the engine verifies the signature against the Credential-issuer's public key.

The shipped engine could not tell an operator which one it meant. Its flag help named Control's JWKS artifact and told the operator the issuer must equal Control's, across five sites. Following that text anchors the engine on the wrong key, and the failure is bidirectional: the engine begins accepting a guest's own weak JWT presented straight at the south face — the edge bypass ADR-0013 exists to close — while rejecting every legitimately injected credential.

The verification itself also does not run by default. `-verify-storage-jwt` defaults false, and neither shipped manifest passes it, so a clean deploy from repo artifacts enforces nothing. Nothing inside the binary can detect that: the binary is doing what it was told.

Beside it sits `-claims-bind`, which reads `filesystem_id` and `intent` from an unverified bearer. It exists because the per-mount intent had to reach the engine before verification did.

## Decision

We will anchor the engine's verification on the credential authority, never on the Control plane.

- **Trust anchor.** The engine verifies the injected credential against the credential authority's published JWKS: kid match, per-kid algorithm pin, signature, `iss`/`aud`, and a required `exp`. The bound `{filesystem_id, intent}` scope comes from verified claims alone; a forged, unsigned, or foreign-issuer bearer binds no scope. The engine never accepts, verifies, or falls back to the Control-minted weak session JWT or its JWKS.
- **JWKS delivery.** The authority renders and persists its JWKS as a file artifact; the deployment mounts it read-only into the engine container, and the engine reads it once at boot, failing closed on an empty, unreadable, or key-less document. The engine performs no network fetch for it — [component 04](../components/04-object-store-service.md) admits no second outbound path, and a read-only mount is not a network leg. Rotation is restart-scoped for v1.
- **Audience and issuer.** The credential's `aud` is the engine's service identity. Its `iss` is the authority's announced identity, which is a deployment parameter rather than a canon constant, because the authority itself is an open ruling. One deployment-level variable feeds both the authority's mint and the engine's check, so the two cannot disagree, and a shipped manifest carries no placeholder-TLD value.
- **Default posture.** Verification is on by default. The only unverified posture is a static operator-configured scope bind, selected by a flag whose name says it is insecure, and admitted only in engine-only rigs that have no authority to verify against. Every such manifest is recorded in the config-drift gate's audited exemption set.
- **The unverified claims-parse seam is removed.** Binding scope from an unverified bearer's claims lets the bearer choose its own scope. The verified path reads the same claims after the signature check, so the seam's only job is done strictly better by the thing that replaced it.

## Consequences

The default flip is what turns this from a capability into a control. A verifier behind a default-off flag is a fail-open system wearing fail-closed code, which is the shape that produced B1.

Naming the opt-out for its danger puts the posture in the process argv, where the drift gate, an InfoSec reviewer, and a container inspection all read it. A boolean set to false says nothing when read back.

The engine-only rigs — conformance and component-IT — stand up a bare engine with no authority and no JWKS. They take the insecure flag and stay in the exemption set with their reason recorded, so their posture is a documented exception rather than an accident.

A deployment that mounts the wrong JWKS now fails closed at boot rather than serving. That is a louder failure than the alternative, and the alternative is the bidirectional hole above.

The flags governing this credential are renamed away from "storage-jwt": in canon vocabulary that name belongs to the weak session JWT, and the collision is what made the wrong anchor readable as correct. The rename costs nothing because no shipped manifest passes the flags yet.

## Alternatives

**Anchor on Control's JWKS.** Rejected: it is the documented bypass. The engine would accept an assertion canon says it does not accept, and reject the credential canon says it must.

**Fetch the JWKS over the network.** Rejected for v1: it opens a second outbound path from the broker, which component 04's boundary does not admit, and it makes boot depend on the authority being reachable. A refresh path is a later decision against that boundary, not a convenience.

**Keep verification opt-in and rely on the drift gate.** Rejected: the gate reads shipped manifests, so it cannot see a hand-rolled deployment or a fork. A default that must be opted into is a control the operator can lose by omission.

**Keep the claims-parse seam for deployments without an authority.** Rejected: it binds attacker-controlled scope. Where no authority exists, the static operator-configured bind gives the same capability while the scope stays something the operator chose.
