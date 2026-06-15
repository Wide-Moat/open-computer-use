<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-06-15
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: ['0013 (storage-leg custody half only)']
superseded-by: null
amends: [0007, 0011, 0016]
compliance-impact: [SOC2-CC6.1, SOC2-CC6.6, ISO27001-A.8.10, NYDFS-500.15, DORA-Art.28]
license-impact: none
threat-mitigation-link: ../06-threat-model.md
---

The egress edge validates a weak session JWT the guest holds, exchanges it at the OIDC issuer for the real filestore credential keyed on `filesystem_id`, and overwrites the `Authorization` header with that credential; the issuer keeps the sole signing key and the storage engine enforces scope on the injected credential. Audience: anyone wiring or auditing how a sandbox session's storage requests reach the object-store service.

# ADR-0019: Egress exchanges the filestore credential from the session JWT

## Status

`proposed`

## Context

The storage leg runs guest mount client → egress trust-edge → `ocu-filestore` → storage engine. [ADR-0013](0013-storage-credential-custody.md) gave the guest the engine-accepted credential — a scoped JWT the guest forwarded unmodified — and rejected injecting or re-credentialing the bearer at the egress middlebox as an anti-pattern, on the premise that doing so places a signing key on the inspection plane. The owner now requires the guest to hold only a WEAK session JWT that the storage engine does not accept on its own, and the edge to EXCHANGE that weak JWT for the real filestore credential. The signing key stays at the issuer, so the old anti-pattern — a signing key on the inspection plane — does not apply to an exchange.

## Decision

We will make the egress edge validate the guest's weak session JWT, strip it, exchange it at the OIDC issuer for the real filestore credential keyed on the validated `filesystem_id`, and overwrite the `Authorization` header with that credential, because the issuer stays the sole signing-key holder and the edge mints nothing.

The OIDC issuer (Keycloak reference target; any OIDC provider meeting the mint-plus-exchange contract; minimal shelf = bundled OpenBao) is the sole signing-key holder. It issues two things: (a) a weak session JWT to the guest before or at provisioning, via the control plane — ES256, scoped `{filesystem_id, intent, downloadable}`, short-lived, an edge-only assertion `ocu-filestore` does not accept; and (b) the real filestore credential, via RFC 8693 token-exchange, when the edge presents the weak session JWT as the `subject_token`.

The edge validates the weak session JWT with stock `envoy.filters.http.jwt_authn` against a local verifying key — missing or invalid yields 401; strips it (`forward=false`); exchanges it at the issuer for the real credential keyed on `filesystem_id`; and overwrites `Authorization` with the real credential via stock `credential_injector`, or `ext_proc` for the claim-keyed mapping. The keyed mapping is OCU code; Envoy stays stock. The edge holds no signing key and mints nothing — it exchanges. The exchange runs per-session, cached: the edge exchanges once per session or per TTL and caches the real credential for that session window, not per file-op request. `ocu-filestore` receives only the real injected credential; the storage engine enforces `filesystem_id` scope on it.

## Consequences

- Component [04](../components/04-object-store-service.md): `ocu-filestore` receives only the real edge-injected credential, never the guest's weak JWT; the storage engine behind it enforces `filesystem_id` scope on the injected credential.
- Component [05](../components/05-session-sandbox.md): the guest holds only the weak session JWT; a fully-compromised guest yields an assertion `ocu-filestore` does not accept on its own.
- Component [06](../components/06-egress-trust-edge.md): the edge gains validate-and-exchange; the prior pass-through test becomes a swap test asserting the forwarded `Authorization` differs from the inbound one.
- Positive: the one-door property holds — the edge sits before `ocu-filestore`, and both legs reach the storage engine only through it.
- Positive: the guest's blast radius shrinks to a weak edge-only assertion; the real credential never enters the guest.
- Negative: the cached real credential lives on the edge for the session window — the accepted trade for a per-session exchange cadence.
- Failure modes: a missing or invalid weak session JWT is rejected 401 at the edge; a foreign-scope or missing-or-expired injected credential is rejected 403 or 401 at the backend on the injected credential.
- Supersedes the storage-leg custody half of [ADR-0013](0013-storage-credential-custody.md) (the guest no longer forwards the engine-accepted credential), and amends [ADR-0007](0007-egress-auth-mechanism.md), [ADR-0011](0011-storage-egress-lane.md), and [ADR-0016](0016-egress-baseline-inspection-hop-backend-scope.md).

## Alternatives considered

- **Keep [ADR-0013](0013-storage-credential-custody.md) — guest forwards the engine-accepted credential, edge swaps nothing.** Rejected by the owner: the guest holds a credential the engine accepts directly.
- **A single deployment-wide static credential injected by the stock generic injector.** Rejected: it is not keyed per `filesystem_id`, so every session would inject the same credential.
- **S3/SigV4 re-sign at the edge.** Rejected: the storage engine sits behind `ocu-filestore` and is unreachable from the edge, so there is no backend signature for the edge to produce.

## Compliance impact

- `SOC2-CC6.1` / `SOC2-CC6.6` / `ISO27001-A.8.10`: the signing key stays at one OIDC issuer; the guest holds a weak short-lived assertion; the edge exchanges it; the storage engine enforces scope on the real credential — the access-control and least-privilege story for storage authentication.
- `NYDFS-500.15` / `DORA-Art.28`: the exchange is keyed per `filesystem_id` at a single auditable issuer, and the injected credential is scope-enforced at the storage engine — the third-party-access governance evidence.

## License impact

None. Envoy is already bundled ([ADR-0006](0006-egress-forward-proxy-substrate.md)); the keyed exchange is OCU code; the real credential comes from the customer's store.

## Threat mitigation

Re-anchors P6-E2 ([06-threat-model.md](../06-threat-model.md)): the exchange is the baseline on the storage leg, so the forwarded `Authorization` differs from the inbound assertion; the signing key never reaches the edge or the guest; a foreign-scope injected credential is rejected at the storage engine.

## Open questions

1. `ext_proc` versus claim-keyed SDS for the keyed exchange — tracking issue.
2. Rotation of the cached real credential against the weak session JWT window — tracking issue.
