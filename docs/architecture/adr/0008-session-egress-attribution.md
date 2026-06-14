<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-06-02
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
amended-by: [0016]
compliance-impact: [SOC2-CC6.1, NYDFS-500.15, DORA-Art.28]
license-impact: none
threat-mitigation-link: ../06-threat-model.md
---

Fixes how the Egress trust-edge attributes an outbound request to the session that owns it, and scopes that attribution to deny decisions only. Audience: anyone wiring or auditing how per-session egress policy reaches the edge.

# ADR-0008: Session-to-egress attribution by presented token

## Status

`proposed`

Amended by [ADR-0016](0016-egress-baseline-inspection-hop-backend-scope.md): the hop terminates TLS at the baseline, not only on a hardening rung, so attribution by the presented L7 token applies at the baseline too. Read "egress-wide-bump rung" below as the baseline inspection hop. The `credential_injector` filter runs only where edge-injection hardening is configured; the attribution chain (`jwt_authn → ext_authz → rbac → ratelimit`) stands at the baseline without it.

## Context

[ADR-0007](0007-egress-auth-mechanism.md) gates credential injection on a credential the request *presents*, never on its network origin — the forbidden P6-E2 pattern is "inject because traffic came from sandbox X". Per-session deny policy still has to reach the edge: the kill-switch denylist ([component 02](../components/02-control-operator-api.md)), downloadable-deny ([NFR-SEC-73](../manifesto/02-nfrs.md)), and per-session rate limits all need the edge to know *which session* a request belongs to. Nothing decided how the edge derives that session identity. The edge terminates TLS at the baseline inspection hop ([ADR-0016](0016-egress-baseline-inspection-hop-backend-scope.md), [02-trust-boundaries.md](../02-trust-boundaries.md) §7, [ADR-0006](0006-egress-forward-proxy-substrate.md), [ADR-0007](0007-egress-auth-mechanism.md)): the guest trusts the per-deployment CA whose public certificate is in its trust store, so the edge can read the plaintext request and the session token the guest carries. The open question is whether attribution reads that L7 token or instead needs a network-layer fact (source IP, mTLS peer, the host↔guest connection identity).

## Decision

An outbound request is attributed to its owning session by the **session-scoped token the request presents at L7**, read after TLS termination at the inspection hop. Every per-session deny and rate decision keys on the verified token's claims, not on any network-layer fact. The edge runs the off-the-shelf Envoy filter chain `jwt_authn → ext_authz → rbac → ratelimit → router`. `jwt_authn` reads and verifies the token and writes its session claim to dynamic metadata; `ext_authz` consults the denylist; `ratelimit` applies the per-session limit on that claim. Where edge-injection hardening is configured ([ADR-0007](0007-egress-auth-mechanism.md)), a `credential_injector` filter sits before `router` and attaches the SDS-delivered upstream credential; the baseline runs no injector.

Injection stays gated on the presented token by filter order. The auth and denylist filters terminate a disallowed request before it reaches the injector, which carries no per-request predicate of its own. A request presenting no valid session token is rejected and never injected, satisfying the [ADR-0007](0007-egress-auth-mechanism.md) gate. One L7 read of the same token serves both the deny/rate decision here and the injection gate there.

Network-layer identity is **not** the egress attribution key. The host-attested network fact (per-session netns, host kernel peer-credentials, or the hypervisor vsock context id by runtime tier) attributes a connection to a *guest* on the host↔guest channel and isolates one sandbox from another — guest isolation, owned by [02-trust-boundaries.md](../02-trust-boundaries.md) §4 and [NFR-SEC-43](../manifesto/02-nfrs.md). It is a different boundary from egress session attribution and is not restated as one here.

## Consequences

- The session claim drives **deny** at the Egress trust-edge ([component 06](../components/06-egress-trust-edge.md)): `ext_authz` refuses a revoked session against the denylist, downloadable-deny ([NFR-SEC-73](../manifesto/02-nfrs.md)) drops an egress-eligible artifact, and `ratelimit` bounds the session. It is never the injection trigger on its own — that is the [ADR-0007](0007-egress-auth-mechanism.md) line; here it is enforced by filter order, not a flag.
- Component 06 records this ADR in its `adr:` front-matter (`[0005, 0006, 0007]` → `[0005, 0006, 0007, 0008]`); the sandbox-listener face now has a named session key — the L7 token — and the denylist-at-edge invariant reads it through `ext_authz`.
- Positive: attribution needs no per-session network plumbing, so it holds identically across every runtime tier ([ADR-0003](0003-sandbox-runtime-tier-ladder.md)) — `runc` shared-kernel with no context id, gVisor, and microVM all present the same L7 token. The chain is native Envoy ([ADR-0006](0006-egress-forward-proxy-substrate.md)); no custom data-plane code.
- Negative: the token must be a verifiable JWT for `jwt_authn` to validate it standalone; an opaque token moves validation to an `ext_authz` introspection call-out to the session authority (still native Envoy, one more dependency on the call path). `credential_injector` is the youngest filter in the chain — pin its version and smoke-test the SDS-rotation path.
- Neutral: a downstream filter trusts the token only after `jwt_authn` records a verified status, never a copied claim header alone, so a forged claim header cannot pass; claims reach `ext_authz` as metadata, not a trusted header.

## Alternatives considered

- **Host-attested network fact (netns / peer-credentials / vsock context id) as the egress key** — rejected: that fact attributes a connection to a guest and isolates sandboxes (the host↔guest concern, [NFR-SEC-43](../manifesto/02-nfrs.md)); it is absent or weak exactly where the edge terminates TLS (shared-kernel `runc` has no context id), and the edge already holds the session token in plaintext after termination, so a network fact adds nothing the L7 read does not give. Carrying it onto the egress edge conflates isolation with attribution.
- **Source IP as the session key** — rejected: a guest-settable network fact; keying any decision on it re-introduces the P6-E2 network-origin pattern.
- **A custom Envoy filter or `ext_proc` for the read/validate/inject path** — rejected: the native `jwt_authn` / `ext_authz` / `ratelimit` / `credential_injector` chain covers it; custom data-plane code is only needed for value-varying per-session credential selection, which v1's single upstream does not require.

## Compliance impact

- `SOC2-CC6.1`: per-session deny reaches the boundary on a verified token claim, so a revoked or rate-limited session is enforced at the egress point — the access-control story for outbound traffic.
- `NYDFS-500.15` / `DORA-Art.28`: the outbound leg's session identity is the verified token, audited per request, recording which session each authenticated outbound flow belongs to.

## License impact

None. The chain is native Envoy filters already bundled by [ADR-0006](0006-egress-forward-proxy-substrate.md); no new dependency.

## Threat mitigation

Tightens the deny side behind P6-E2 in [the threat model](../06-threat-model.md): a request presenting no valid session token is rejected before the injector, and a forged claim is caught by the verified-status check, so a compromised guest cannot borrow a co-tenant's egress policy by forging a header. Per-action authorization on the attributed session — what that session may do to which object — is separate and tracked at [#187](https://github.com/Wide-Moat/open-computer-use/issues/187); whether the session token is a JWT or an opaque token validated by introspection is the open sub-question at [#160](https://github.com/Wide-Moat/open-computer-use/issues/160).
