<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: draft
last-reviewed: 2026-05-31
owner: "@Wide-Moat/architects"
applies-to: next/v1
compliance: []
threat-model: 06-threat-model.md
contract: null
adr: [0005, 0006, 0007]
---

The sandbox's sole outbound network path: it enforces a deny-by-default destination allow-list, emits a structured deny reason, and on the legs that need it attaches the upstream authorization received over Envoy SDS so the guest carries no long-lived upstream secret on the egress leg. Audience: engineers and security reviewers wiring or auditing egress policy.

# Component-06: Egress trust-edge proxy

## Purpose

The single outbound path for the sandbox: it resolves each destination against a deny-by-default allow-list and, on a bump-rung leg only, originates the upstream connection so it can attach the authorization received over Envoy SDS that the guest never holds ([`05-c4-container.md`](../05-c4-container.md) §3). The destination-to-rung binding is per-destination state held only at the edge, so one egress process serves a transparent-pass-through leg and an egress-wide-bump leg at once.

## Boundaries

The intra-container view. The inbound sandbox leg, the broker backend leg, and the audit fan-in are the boundaries [`05-c4-container.md`](../05-c4-container.md) §4 names; their `F8`/`F9`/`F10` flow labels are defined in [`06-threat-model.md`](../06-threat-model.md) §1. The upstream credential arrives over Envoy SDS, an external input to the edge, not an internal OCU boundary. Token classes are owned by [`02-trust-boundaries.md`](../02-trust-boundaries.md) §8; TTLs are not repeated here.

The edge is the off-the-shelf Envoy proxy with three internal faces and one external input:

| Internal face | What it does |
|---|---|
| sandbox listener | accepts the guest's outbound request on the network-bound default route — the request carries no long-lived upstream secret; a presented scoped credential, if any, gates injection |
| upstream originator | resolves the destination, and on a bump-rung leg terminates and re-originates the TLS with the authorization attached by Envoy's `credential_injector` filter |
| audit emitter | emits an OCSF allow/deny event, denials carrying the `x-deny-reason` vocabulary |

The credential receiver is Envoy's SDS client: it receives the upstream credential over Secret Discovery Service (SDS, gRPC xDS) from the SDS source and binds it for injection on the outbound leg. The source is a static file (solo deployments) or a customer-provided SDS-compatible store (enterprise deployments); its lifecycle is the source's, per [ADR-0005](../adr/0005-egress-credential-delivery-envoy-sds.md).

Owned state: the destination allow-list (resolved-IP + SNI rules) and the per-destination rung binding (transparent pass-through vs egress-wide bump). The edge receives the credential from SDS at injection time, attaches it for the upstream leg, and drops it after the connection terminates; it holds no credential at rest and no rotation or revocation responsibility ([NFR-SEC-29](../manifesto/02-nfrs.md)). It authors no denylist and holds no kill-switch route — the denylist is the Control/operator API's; the edge reads it as a deny signal. It holds no object-store credential — the broker signs its own backend leg ([NFR-SEC-25](../manifesto/02-nfrs.md)), and the broker backend leg (F9) traverses the edge as one allow-list destination with no TLS termination, so the broker-produced signature is forwarded byte-intact.

Token classes ([`02-trust-boundaries.md`](../02-trust-boundaries.md) §8 owns the taxonomy): the edge presents the SDS-delivered authorization upstream; the guest-facing leg carries no long-lived upstream secret — at most a short-lived scoped credential the guest presents to gate injection, never the upstream key. The upstream credential is delivered by Envoy SDS, off-the-shelf and external to OCU, not an OCU-defined wire surface. The outbound leg (F8) is a network property with no wire schema by design ([NFR-SEC-27](../manifesto/02-nfrs.md)); the broker backend leg (F9) is conform ([NFR-SEC-16](../manifesto/02-nfrs.md)). The downloadable axis reaches the edge as a broker-resolved deny signal, not a field the guest's outbound request carries ([NFR-SEC-73](../manifesto/02-nfrs.md)).

## Invariants

Each rule holds independent of the caller and is falsifiable by the named check. Egress *posture* (the §7 rung ladder), in-transit-encryption carve-outs, and zone membership are Layer 3 properties, not invariants here.

- Every outbound connection resolves through this process; the sandbox has no route out other than F8 (network-policy IaC assertion, [NFR-SEC-27](../manifesto/02-nfrs.md)).
- A destination not matched by an allow-list rule is dropped before the TLS handshake at the SNI pre-filter, with no partial connect (integration test, [NFR-SEC-08](../manifesto/02-nfrs.md), [NFR-SEC-17](../manifesto/02-nfrs.md)).
- The proxy-owned resolver is the sole resolution authority: a guest-supplied A/AAAA cannot override it for an egress destination, and the mandatory deny-set is filtered on resolved IP at connect, never on DNS resolution (unit test per rejection class + in-guest rebind negative test, [NFR-SEC-12](../manifesto/02-nfrs.md)).
- Every denied connection is a machine-parseable object carrying the `x-deny-reason` vocabulary, never free text (schema-validation, [NFR-SEC-17](../manifesto/02-nfrs.md)).
- Injection is reachable only on the edge-originated upstream leg of a bump-rung destination; the guest→edge leg and every transparent-pass-through leg carry no upstream credential (integration test asserting no credential in the guest, [NFR-SEC-23](../manifesto/02-nfrs.md), [NFR-SEC-27](../manifesto/02-nfrs.md)).
- Injection is gated on a scoped credential the request presents, never on its network origin alone: a request reaching a bump-rung destination but presenting no scoped credential is forwarded with none attached — "inject because traffic came from sandbox X" is the forbidden anti-pattern ([ADR-0007](../adr/0007-egress-auth-mechanism.md), tightening P6-E2; bare-request negative test, [NFR-SEC-23](../manifesto/02-nfrs.md), [NFR-SEC-29](../manifesto/02-nfrs.md)).
- The injected authorization never reaches a guest-visible response surface; it is stripped before any response crosses back to the guest leg (integration test, [NFR-SEC-23](../manifesto/02-nfrs.md)).
- When the denylist names a session, the edge attaches no credential for it, independent of the credential's own validity window (integration test, [NFR-SEC-04](../manifesto/02-nfrs.md), [NFR-SEC-29](../manifesto/02-nfrs.md)).
- An outbound leg for an object the broker resolved `downloadable=false` is denied with a structured reason at every egress rung (edge integration test, [NFR-SEC-73](../manifesto/02-nfrs.md)).
- A destination tagged allow-list-only is forwarded byte-intact; the edge never terminates or re-signs the broker backend leg (integration test, [NFR-SEC-16](../manifesto/02-nfrs.md), [NFR-SEC-25](../manifesto/02-nfrs.md)).
- Denylist-propagation timing reads a monotonic clock, so a wall-clock setback cannot stall the revoke signal past its window (clock-rollback red-team harness, [NFR-SEC-48](../manifesto/02-nfrs.md), [NFR-SEC-63](../manifesto/02-nfrs.md)).

## Failure modes

Each row traces to one P6/P5 STRIDE row in [`06-threat-model.md`](../06-threat-model.md) §3 and repeats that row's controlling NFR; the actor labels are owned by [`06-threat-model.md`](../06-threat-model.md) §2 (A1 in-sandbox guest, A3 host-side). Fail-closed is the default on every egress, injection, and deny boundary.

| Trace | Reaching actor | What goes wrong | Recovery behaviour | Controlling NFR |
|---|---|---|---|---|
| P6-R1 | A1 | A policy-violating egress attempt is later disputed and the decision, destination, and injected-or-not are not durably recorded | Emit OCSF on F10 for every allow and deny; denials carry the structured `x-deny-reason`; SNI pre-filter drops and L7 inspections both record | NFR-SEC-03 |
| P6-I1 | A1 | Content-blind exfil: the guest tunnels data to an allow-listed destination over the transparent pass-through rung (non-inspecting) | Allow-list narrows destinations; the payload-independent byte/cardinality tripwire arms at every rung; deep DLP requires the egress-wide-bump rung | NFR-SEC-57, NFR-SEC-73 |
| P6-I2 | A1 | The injected credential leaks back to the guest via an error, redirect, or reflected header at the egress-wide-bump rung | Strip injected authorization from every response surface before it crosses to the guest leg; injection only on the edge-originated leg; the credential is received from SDS at injection and never persisted at the edge | NFR-SEC-23, NFR-SEC-29 |
| P6-I3 | A3 | The bump-rung decrypt/re-encrypt segment exposes plaintext at the edge in memory or swap | The bump rung is per-destination, a single named inspection segment, TLS 1.3 on both legs; transparent-pass-through and broker legs never terminate | NFR-SEC-05, NFR-SEC-33 |
| P6-E1 | A1 | Allow-list bypass via SNI≠Host domain-fronting, CONNECT abuse, DNS rebinding, or raw-IP / non-HTTP | Deny-by-default; SNI pre-filter drop before TLS; L7 SNI/Host consistency check on the inspected leg; proxy-owned resolver | NFR-SEC-27, NFR-SEC-05, NFR-SEC-16 |
| P6-E2 | A1 | The guest forces injection toward an unintended destination via a cross-scope allow-list entry or open redirect on an allowed upstream | Gate injection on the scoped credential the request presents, never on its network origin alone ([ADR-0007](../adr/0007-egress-auth-mechanism.md)); attach only the SDS-delivered credential matching the validated destination; credential scope is set at the SDS source, so a mis-routed credential stays bounded to the scope the source supplied | NFR-SEC-29, NFR-SEC-23, NFR-SEC-73 |
| P6-E3 | A1 | The upstream needs client-mTLS / cert-pin / DPoP, which header-token injection cannot satisfy | The customer configures the SDS source to supply the client cert / PoP key, re-originated at the bump rung; a source that cannot supply it makes the destination incompatible at config time with a structured deny; a guest-resident-key workaround is refused | NFR-SEC-50 |
| P6-D1 | A1 | The edge is made unreachable by a crash, connection flood, or upstream-timeout storm, losing the sole outbound path | Fail-closed: outbound traffic drops, never bypasses; unallowed destinations dropped cheaply at the SNI pre-filter before TLS to bound handshake-exhaustion cost | NFR-SEC-46, NFR-SEC-53 |
| P6-D3 | A3 | Clock rollback at the edge defeats denylist-propagation timing | Denylist propagation reads a monotonic clock; the denylist is also checked directly on every injection, giving a non-clock revoke path | NFR-SEC-48, NFR-SEC-63 |
| P6-T1 | A3 | At the egress-wide-bump rung the edge holds plaintext between decrypt and re-encrypt; a compromised edge alters bodies undetected | The bump rung is per-destination, customer-CA-rooted, TLS 1.3 on both legs; the carve-out is a single auditable inspection point | NFR-SEC-05, NFR-SEC-33 |
| P5-D2 | A1 | The guest floods the edge with connection/request volume to deny outbound to co-tenant sessions or amplify against an upstream | Single forward proxy bounds reachable destinations; fail-closed drops rather than bypasses; per-session egress rate / connection quota | NFR-SEC-05, NFR-SEC-27 |

Residual, by [`06-threat-model.md`](../06-threat-model.md) §5 register: the transparent (non-inspected) leg stays content-blind, so P6-I1 records only metadata and P6-R1 can dispute only metadata — content-blind transparent egress, accepted-with-tier ([#182](https://github.com/Wide-Moat/open-computer-use/issues/182)). The no-credential-in-response stripping behind P6-I2, the edge-binary/config attestation behind P6-T1, and the plaintext-zeroization behind P6-I3 lack an explicit NFR ([#197](https://github.com/Wide-Moat/open-computer-use/issues/197)). SNI/Host consistency on the transparent leg behind P6-E1 is unenforced ([#198](https://github.com/Wide-Moat/open-computer-use/issues/198)). The destination-to-lease binding and per-action authz behind P6-E2 are tracked at [#187](https://github.com/Wide-Moat/open-computer-use/issues/187); the guest-resident-key schemes behind P6-E3 are declared unsupported ([#176](https://github.com/Wide-Moat/open-computer-use/issues/176)). The per-sandbox egress conn-rate / fd containment behind P6-D1 / P5-D2 is the resource-exhaustion theme — NFR-SEC-46 is the edge control and NFR-SEC-53 the sibling MCP-gateway-listener ceiling ([#188](https://github.com/Wide-Moat/open-computer-use/issues/188)). Clock-rollback behind P6-D3 is the trusted-time theme ([#185](https://github.com/Wide-Moat/open-computer-use/issues/185)). The MITIGATED P6 rows (the listener spoof, the bump-rung upstream spoof, the broker-leg tamper) live in [`06-threat-model.md`](../06-threat-model.md) §4.

## Operational concerns

**Config surface.** The allow-list (resolved-IP + SNI rules per destination), the per-destination egress rung ([`02-trust-boundaries.md`](../02-trust-boundaries.md) §7), the proxy-owned resolver and its deny-set (the canonical list is in [NFR-SEC-12](../manifesto/02-nfrs.md), enforced by the resolver invariant above), and the per-session egress rate / connection ceilings. DLP-ICAP is a configuration of the egress-wide-bump rung, not a separate rung ([NFR-FLEX-15](../manifesto/02-nfrs.md), [NFR-COMP-28](../manifesto/02-nfrs.md)).

**Observability.** The edge emits an OCSF event for every allow and deny on fan-in flow F10, denials carrying the `x-deny-reason`, against the audit contract ([`08-contracts.md`](../08-contracts.md) §1) and [NFR-SEC-03](../manifesto/02-nfrs.md). The payload-independent exfil tripwire ([NFR-SEC-57](../manifesto/02-nfrs.md)) raises a structured OCSF anomaly event in both postures.

**Scaling axis.** A per-host shared edge serves many co-located sessions, which makes it a shared DoS surface (P5-D2 / P6-D1); the per-session rate / fd ceiling under [NFR-SEC-46](../manifesto/02-nfrs.md) is the containment, with [NFR-SEC-53](../manifesto/02-nfrs.md) bounding the sibling MCP-gateway listener, not the edge. Whether the edge is one-per-host or one-per-deployment tracks the same instantiation question as the broker ([#175](https://github.com/Wide-Moat/open-computer-use/issues/175)).

**Rotation / lifecycle.** The edge receives the credential from SDS per-connection and drops it after use; rotation belongs to the SDS source, not the edge ([NFR-SEC-04](../manifesto/02-nfrs.md)). On sandbox teardown the host-driven finalizer drops the network-bound egress route host-side even if the guest is unresponsive ([NFR-SEC-65](../manifesto/02-nfrs.md)).

**Shelf delta** ([`05-c4-container.md`](../05-c4-container.md) §5): egress posture is a ladder by need ([`02-trust-boundaries.md`](../02-trust-boundaries.md) §7, [ADR-0007](../adr/0007-egress-auth-mechanism.md)). A deployment with no outbound need runs deny-all; one needing only unauthenticated internet runs transparent pass-through (no CA) and cannot inject; one with an upstream credential configured runs egress-wide bump — a per-deployment CA auto-generated and its public cert auto-injected into the sandbox trust store at start, attaching the credential on the edge-originated leg. The enterprise shelf points the credential at a customer-provided SDS source. The boundary properties in the Invariants section hold at every rung; the CA and the TLS-termination capability appear at the bump rung. Envoy is the forward-proxy substrate ([ADR-0006](../adr/0006-egress-forward-proxy-substrate.md)); the bump rung terminates with a leaf minted per SNI from that CA — pre-minted over a file SDS source for a config-time-enumerable allow-list, or a self-hosted SDS minting service for a non-enumerable one ([ADR-0007](../adr/0007-egress-auth-mechanism.md)).

## Open questions

1. Envoy's `credential_injector` filter and its OAuth2 extension carry an upstream maturity caveat — not substantial production burn-in, an unknown security posture, intended for trusted-on-both-ends paths — while a third-party LLM API is an untrusted upstream. The regulated-tier posture for this filter is deferred pending a security review — needs issue.
2. ~~MITM-termination technology undecided.~~ Resolved by [ADR-0007](../adr/0007-egress-auth-mechanism.md): the bump rung terminates with a leaf minted per SNI from a per-deployment CA, served by the Envoy data plane plus a self-hosted SDS minting service; a config-time-enumerable allow-list uses pre-minted leaves over a file SDS source instead. Selection between edge-inject and a protocol broker is per upstream; v1 ships edge-inject only.
3. SNI/Host consistency on the transparent (non-inspected) leg, where the SNI pre-filter alone misses domain-fronting — [#198](https://github.com/Wide-Moat/open-computer-use/issues/198).
4. No-credential-in-response stripping, edge-binary/config attestation, and plaintext-zeroization for the bump rung lack an explicit NFR — [#197](https://github.com/Wide-Moat/open-computer-use/issues/197).
5. mTLS / cert-pin / DPoP upstreams the edge cannot serve by injection, and the guest-resident-key schemes declared unsupported — [#176](https://github.com/Wide-Moat/open-computer-use/issues/176).
