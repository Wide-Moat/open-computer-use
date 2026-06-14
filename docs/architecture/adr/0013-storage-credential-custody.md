<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-06-14
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
amends: [0007, 0011]
compliance-impact: [SOC2-CC6.1, SOC2-CC6.6, ISO27001-A.8.10, NYDFS-500.15, DORA-Art.28]
license-impact: none
threat-mitigation-link: ../06-threat-model.md
---

The storage-backend credential is a pre-issued ES256 JWT minted by an off-box host-side credential issuer, scoped to one `filesystem_id`, delivered by the control plane and forwarded unmodified by the guest as a static bearer; the off-box issuer is the sole signing-key holder, the guest verifies only, and the storage engine enforces the scope. Audience: anyone wiring or auditing how a sandbox session reaches its storage backend.

# ADR-0013: Storage credential custody — provisioning-time off-box-issued JWT

## Status

`proposed`

## Context

The storage backend authenticates each request by a bearer credential. Where that credential is minted, who holds the signing key, and who enforces its scope are one coupled decision that crosses the control plane, the in-guest mount client, and the storage engine. A prior model placed the backend key in a host-side component that signs each backend request, on the premise of a per-request signing protocol (SigV4-shaped). The storage backend has no such mechanism: it authenticates by a static JWT bearer, so no per-request signature exists to preserve. The guest is not credential-free; it holds a derived, scoped, short-lived token, and the load-bearing question is which holder owns the signing key and where scope is checked.

Two auth layers run on this path and stay distinct. The storage credential is an ES256 JWT verified by the storage engine. Control-channel client auth is a separate Ed25519 key, set on the executor, that authenticates the control-WebSocket clients ([ADR-0017](0017-control-plane-repo-boundary.md)). They share no key material and serve different counterparties; this ADR governs the ES256 storage layer only.

## Decision

We will custody the storage-backend credential as a pre-issued, asymmetric-signed, scope-bound JWT bearer minted host-side by a separate off-box credential issuer at provisioning time — scoped to one `filesystem_id` plus its workspace and org, with a short fixed window and no refresh — delivered by the control plane into the mount config over the host-only control channel before the mount client starts; the guest forwards it unmodified as a static `Authorization: Bearer` on every request and never signs, the guest verifies only, and the storage engine enforces the `filesystem_id` scope and rejects a foreign-scope token, because the off-box issuer is the one place that holds the signing key, the control plane only relays the pre-signed token, and the guest holds a token useless outside its own scope and window.

The reference token shape illustrates the choice without binding it: an ES256 JWT, `kid` naming the signing key, no `iss`/`aud` claim, fixed ~6 h TTL. The binding decision is the asymmetric-signed, scope-bound, off-box-issued, forward-only bearer; the algorithm and TTL are properties the implementation pins.

### Custody table — storage-backend JWT

| Credential | Holder | Provably does not hold it |
|---|---|---|
| ES256 signing key (private) | **Off-box host-side credential issuer** — sole holder | control plane, executor, guest mount client, object-store service, Web UI, parser-sandbox |
| Pre-signed scoped JWT (the bearer) | Guest mount config (root-readable) and the static bearer header in transit | — |
| Inspection-CA private key | Egress gateway / host side | the guest (holds only the root cert) |
| Ed25519 control-WS client-auth key | Control-channel client identity ([ADR-0017](0017-control-plane-repo-boundary.md)) — a different layer, not a storage-JWT verify key | — |

The control plane is the **delivery / provisioning vehicle**, not a holder of the signing key: it relays the pre-signed token into the mount config, scrubs the on-disk source after handoff, and installs the guest's control-channel verify-key, but it never signs the storage JWT. The guest holds a bearer and verifies it; it holds no signing key. The object-store service, the [Web UI](../components/08-web-ui.md), and the parser-sandbox ([ADR-0015](0015-storage-decomposition-by-trust-plane.md)) hold no signing key either.

## Consequences

- Component [04](../components/04-object-store-service.md) and [05](../components/05-session-sandbox.md): the in-guest mount client forwards an off-box-issued token unmodified. It runs no signer and reaches no signing key, so a fully-compromised guest yields at most this token, valid only for its own `filesystem_id` for the remaining window.
- The signing-key holder is a distinct off-box credential issuer service, not folded into any modelled container ([ADR-0017](0017-control-plane-repo-boundary.md) sets its delivery boundary). Component [02-control-operator-api.md](../components/02-control-operator-api.md) gains a DELIVERY / provisioning role: it relays the pre-signed token into the mount config, scrubs the on-disk source after handoff, and installs the guest's control-channel verify-key; it does not mint the storage JWT and holds no signing key. The custody disclaimer re-points to the off-box issuer, not to the control plane.
- Positive: low blast radius on token leak. A root read of the mount config yields one session's own filesystem for the remaining TTL — not a backend key. The storage engine rejects the same token presented for a foreign `filesystem_id` (HTTP 401), so it cannot be replayed across filesystems. This adds a storage-engine claim check as a new property and re-anchors [NFR-SEC-31](../manifesto/02-nfrs.md): the host-attested prefix isolation at the storage component stays, and the engine's foreign-scope rejection layers on top — the two checks are layered, not substituted.
- Positive: scope enforcement is at the storage engine, not a middlebox. The egress hop inspects but does not re-credential; the credential's authority is the signed claim the engine validates ([ADR-0016](0016-egress-baseline-inspection-hop-backend-scope.md)). This removes the per-request-signing coupling and the requirement that no middlebox rewrite a signature; [NFR-SEC-25](../manifesto/02-nfrs.md) re-anchors off the self-signs / STS-per-session premise.
- Amends [ADR-0007](0007-egress-auth-mechanism.md): its §Decision names the storage zone as the canonical protocol-broker pattern "which holds the object-store backend credential and exposes a session-scoped handle." That key-holder premise is retired — no in-deployment component holds the storage signing key. The §Decision sentence is re-anchored onto this model (the storage credential is the off-box-issued, guest-forwarded scoped bearer); the abstract edge-inject-vs-protocol-broker selection axis for a future scoped-credential upstream is untouched.
- Negative: no mid-session refresh. The mount client reads the token once; a session outliving the fixed window receives 401. v1 ships no refresh machinery; a refresh design is deferred ([#267](https://github.com/Wide-Moat/open-computer-use/issues/267)).
- Negative: the credential lives in the guest (root-readable mount config), so the guest is not credential-free. The mitigation is the scope and TTL bound above, not absence; in-guest secret scans assert the token is scoped and short-lived, not that no token exists.
- Reconciliation of [NFR-SEC-60](../manifesto/02-nfrs.md): the prior NFR let the minimal-shelf component hold a long-lived host-local backend credential. Under this model no in-deployment component holds the signing key; the minimal-shelf credential becomes the guest-held scoped bearer minted by the off-box issuer, and the long-lived host-local credential survives only as the [ADR-0010](0010-storage-backend-pluggable-adapter.md) local-volume / S3-adapter engine credential admitted under `workload_trust_profile = trusted_operator` and single-tenant — a backend-engine credential, not a JWT signing key.
- Neutral: the [memory-store](../components/04-object-store-service.md) mount type carries its own scoped JWT under the same mechanism (a `memory_store_id` claim in place of `filesystem_id`), so this ADR governs both; the type itself is scoped out of v1 and named, not modelled ([ADR-0015](0015-storage-decomposition-by-trust-plane.md)). The `workspace_cmek_enabled` envelope branch sits at the storage engine, not in the token custody, and is unaffected.

## Alternatives considered

- **A host-side component holds the backend key and self-signs each request.** Rejected: it fuses the signing key into the same process that touches untrusted file content and mints session scope, violating the custody rule that a component serving untrusted content holds no key; and there is no per-request signing protocol to host — the backend authenticates by a static bearer the issuer mints once, so self-signing invents a mechanism the backend does not use. This is the prior [NFR-SEC-25](../manifesto/02-nfrs.md) / [ADR-0011](0011-storage-egress-lane.md) premise, now corrected.
- **Inject or re-credential the bearer at the egress middlebox.** Rejected: the inspecting hop terminates TLS but does not mint or attach the storage credential — the token originates host-side and passes through unmodified ([ADR-0016](0016-egress-baseline-inspection-hop-backend-scope.md)). The bearer is static, so there is no per-request signature for a middlebox to re-sign, and routing the high-value signing key to the inspection plane would join the credential's blast radius to the plaintext of all egress. [ADR-0005](0005-egress-credential-delivery-envoy-sds.md) already removed the bespoke credential-delegator path, and [ADR-0007](0007-egress-auth-mechanism.md) names the inject-at-edge mechanism for the fixed upstream LLM bearer, not for a scope-bound storage credential the storage engine must verify. The egress edge holds no storage signing key.

## Compliance impact

- `SOC2-CC6.1` / `SOC2-CC6.6` / `ISO27001-A.8.10`: the signing key is held by one off-box issuer service; the control plane only delivers; the guest holds a derived, scoped, time-bounded bearer and verifies it; the storage engine enforces the scope claim — the access-control and least-privilege story for storage authentication.
- `NYDFS-500.15` / `DORA-Art.28`: the credential is scoped per filesystem and bounded to a fixed window, the issuer is a single auditable mint point, and cross-scope replay is rejected at the storage engine — the third-party-access governance evidence.

## License impact

None. The off-box issuer signs with a standard asymmetric primitive (ECDSA P-256); no dependency is introduced by this ADR. The issuer product and its bundled-vs-not-bundled posture are decided by the issuer ADR this one precedes.

## Threat mitigation

Re-anchors P4 custody ([06-threat-model.md](../06-threat-model.md) §3): the signing key never enters the guest, the control plane, or the per-session executor — it stays at the off-box issuer — so a compromised guest cannot mint or widen a token; the storage engine rejects a foreign-`filesystem_id` claim, so a leaked token confines to its own filesystem for its window; the guest holds no signing path and cannot forge a token. The anti-pattern forbidden here — placing the storage signing key in the guest, the object-store service, the control plane, or the egress middlebox — is named so it is not re-introduced.

## Open questions

1. Mid-session token refresh / rotation posture beyond the fixed window — refresh theme, [#267](https://github.com/Wide-Moat/open-computer-use/issues/267).
2. Whether the issuer emits a mint/lifecycle audit event or the lifecycle stays the storage engine's record — audit-fan-in count theme, [#268](https://github.com/Wide-Moat/open-computer-use/issues/268).
