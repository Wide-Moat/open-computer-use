<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: draft
last-reviewed: 2026-06-15
owner: "@Wide-Moat/architects"
applies-to: next/v1
compliance: []
threat-model: 06-threat-model.md
contract: null
adr: [0005, 0006, 0007, 0008, 0013, 0016]
---

The sandbox's single outbound hop: it terminates TLS for inspection, forwards the caller's bearer unchanged, and mints no storage credential. Audience: engineers and security reviewers wiring or auditing egress policy.

# Component-06: Egress trust-edge

## Purpose

It presents a per-host leaf from its own inspection CA, re-originates TLS to the genuine origin, and enforces no storage scope.

## Boundaries

The edge is the off-the-shelf Envoy proxy ([ADR-0006](../adr/0006-egress-forward-proxy-substrate.md)). It is the sandbox's only route out: the guest's internet traffic and the in-guest mount client's storage leg both leave on this one hop, and neither reaches its destination directly.

| Direction | What crosses | Note |
|---|---|---|
| Session sandbox → Egress | the sole outbound path (F8), carrying guest-internet traffic and the mount client's storage leg (F7a) alike | the request carries the caller's own credential (`filesystem_id`-scoped storage JWT, upstream bearer, or none); the edge originates none of these |
| Egress → Upstream LLM / API | the re-originated request to the genuine origin | the agent's allowed outbound endpoints |
| Egress → Object-store service | the storage leg's re-originated request | the only door to storage; the edge forwards the storage JWT unchanged |
| Upstream-cred source → Egress | the upstream credential, over Envoy SDS, when an authenticated upstream is configured | external input; lifecycle is the source's ([ADR-0005](../adr/0005-egress-credential-delivery-envoy-sds.md)) |
| Egress → Audit pipeline | one OCSF event per connection (F10) | host-side fan-in |

There is no edge between the egress hop and the credential issuer: the storage JWT is issued off-box and delivered to the sandbox by the control plane, out of the request path ([ADR-0013](../adr/0013-storage-credential-custody.md)). F9 (Web UI → object-store service) does not cross this hop ([`05-c4-container.md`](../05-c4-container.md) §4).

In v1 the destination set is enumerable, so per-host leaves are pre-minted out of band and served over Envoy-native file SDS — no OCU minter on the data path. A dynamic per-SNI minter ([ADR-0007](../adr/0007-egress-auth-mechanism.md)) is specified for a non-enumerable destination set but unbuilt at GA.

Owned state: the edge's own inspection CA, the source of the per-host leaves it presents while terminating TLS. The inspection-CA private key is the edge's own and never enters the guest; the guest trust store carries only the public root cert, pushed at provisioning ([ADR-0013](../adr/0013-storage-credential-custody.md)). When the hardening rung is enabled, the edge also owns the destination allow-list (resolved-IP + SNI rules) and the per-destination injection binding. The edge holds no storage signing key and mints no storage credential. It authors no denylist and holds no kill-switch route; the denylist is the Control / operator API's, and the edge reads it as a deny signal.

The upstream-credential SDS surface is distinct from the inspection-leaf source. The inspection leaf is the per-host certificate the hop presents while terminating TLS. The upstream credential is the bearer the hop attaches on an authenticated leg under edge-injection hardening ([ADR-0016](../adr/0016-egress-baseline-inspection-hop-backend-scope.md)). The baseline path uses no SDS credential source: the caller's own credential passes through and the edge injects nothing.

## Invariants

Each rule holds independent of the caller and is falsifiable by the named check. Egress posture and zone membership are Layer 3 properties. The allow-list, the structured deny vocabulary, and egress-side scope are hardening-rung properties under Operational concerns, not baseline invariants.

1. Every outbound connection resolves through this process; the sandbox has no route out other than F8 — one default route, block-local-connections, and no second outbound socket (network-policy IaC assertion, [NFR-SEC-27](../manifesto/02-nfrs.md)).
2. The hop terminates outbound TLS and re-originates it to the genuine origin, validating the origin certificate against the public CA set; the inspection-CA private key never enters the guest and the guest trust store holds only the public root cert (in-guest secret scan + TLS-chain integration test, [NFR-SEC-23](../manifesto/02-nfrs.md), [NFR-SEC-33](../manifesto/02-nfrs.md)).
3. The hop re-credentials nothing at the baseline: the caller's `Authorization` is forwarded unmodified, and the edge holds no storage signing key and mints no storage credential (pass-through integration test asserting the forwarded headers match on the storage and unauthenticated paths, [NFR-SEC-23](../manifesto/02-nfrs.md)).
4. Storage scope is not checked at the edge: a foreign-`filesystem_id` JWT is forwarded without a scope decision and rejected at the storage engine (HTTP 401); the test asserts the 401 originates at the engine ([NFR-SEC-31](../manifesto/02-nfrs.md)).
5. The proxy-owned resolver is the sole resolution authority: a guest-supplied A/AAAA cannot override it, and the mandatory deny-set (RFC1918 / RFC4193 / link-local / metadata IPs) is filtered on resolved IP at connect, never on DNS resolution (unit test per rejection class + in-guest rebind negative test, [NFR-SEC-12](../manifesto/02-nfrs.md)).
6. Where edge-injection hardening is enabled, injection is reachable only on the edge-originated leg of that destination and is gated on a scoped credential the request presents, never on its network origin ([ADR-0008](../adr/0008-session-egress-attribution.md), bare-request negative test, [NFR-SEC-23](../manifesto/02-nfrs.md), [NFR-SEC-29](../manifesto/02-nfrs.md)).
7. Where edge-injection hardening is enabled, the injected authorization never reaches a guest-visible response surface; it is stripped before any response crosses back to the guest leg (integration test, [NFR-SEC-23](../manifesto/02-nfrs.md)).
8. When the denylist names a session, the edge drops its outbound connections independent of any credential's validity window ([ADR-0008](../adr/0008-session-egress-attribution.md), integration test, [NFR-SEC-04](../manifesto/02-nfrs.md), [NFR-SEC-29](../manifesto/02-nfrs.md)).
9. Denylist-propagation timing reads a monotonic clock, so a wall-clock setback cannot stall the revoke signal past its window (clock-rollback red-team harness, [NFR-SEC-48](../manifesto/02-nfrs.md), [NFR-SEC-63](../manifesto/02-nfrs.md)).

## Failure modes

Where a row's ID matches a [`06-threat-model.md`](../06-threat-model.md) §3 STRIDE row, it names that row's primary controlling NFR; the actor labels (A1 in-sandbox guest, A3 host-side) are owned by that model §2. The three rows without a matching STRIDE ID are spec-local elaborations of the edge's residuals — P6-E2 is the network-origin injection anti-pattern ([ADR-0007](../adr/0007-egress-auth-mechanism.md)), P6-I2 and P6-E3 detail the no-response-leak and the guest-resident-key residuals (#197, #176) — and each cites a relevant NFR, not a threat-model row. Fail-closed is the default on every egress and inspection boundary. The deny-by-default destination control and the structured deny reason behind P6-E1 / P6-R1 are hardening-rung behaviour; the baseline rows record what the permissive hop provides.

| Trace | Reaching actor | What goes wrong | Recovery behaviour | Controlling NFR |
|---|---|---|---|---|
| P6-R1 | A1 | A policy-violating egress attempt is later disputed and the decision, destination, and credential disposition are not durably recorded | Emit OCSF on F10 for every connection; a baseline block surfaces as a connect failure recorded as such; the hardening rung adds a structured `x-deny-reason` where a deployment needs a machine-parseable denial | NFR-SEC-03 |
| P6-I1 | A1 | Content-blind exfil: the guest tunnels data to a reachable destination, which at the baseline is any host | The payload-independent byte/cardinality tripwire arms on the inspected hop; destination restriction requires the allow-list hardening; deep DLP is an ICAP configuration of the hop | NFR-SEC-57, NFR-SEC-73 |
| P6-I2 | A1 | An injected upstream credential leaks back to the guest via an error, redirect, or reflected header where edge-injection hardening is enabled | Strip injected authorization from every response surface before it crosses to the guest leg; injection only on the edge-originated leg; the baseline injects nothing, so it has no injected credential to leak | NFR-SEC-23, NFR-SEC-29 |
| P6-I3 | A3 | The TLS-termination segment exposes plaintext at the hop in memory or swap | The hop is the single named inspection point, TLS 1.3 on both legs; plaintext lives only between decrypt and re-encrypt; the inspection-CA private key never enters the guest | NFR-SEC-05, NFR-SEC-33 |
| P6-E1 | A1 | At the baseline the hop reaches arbitrary hosts and plaintext HTTP, so a guest reaches an unintended destination | The baseline bounds reach to one inspected hop with no second socket and the proxy-owned resolver mandatory deny-set (NFR-SEC-12); destination restriction (deny-by-default allow-list, SNI pre-filter, SNI/Host consistency) is the hardening rung | NFR-SEC-27, NFR-SEC-05, NFR-SEC-16 |
| P6-E2 | A1 | A leaked storage JWT is replayed to reach another filesystem, or a guest forces an unintended cross-scope reach | Scope is enforced at the storage engine: a foreign `filesystem_id` claim is rejected with a 401, so a leaked token confines to its own scope for its TTL; egress-side scope binding is the optional hardening | NFR-SEC-31, NFR-SEC-29, NFR-SEC-73 |
| P6-E3 | A1 | An authenticated upstream needs client-mTLS / cert-pin / DPoP, which header-token injection cannot satisfy | At the edge-injection hardening rung the customer configures the SDS source to supply the client cert / PoP key, re-originated at the hop; a source that cannot supply it makes the destination incompatible at config time; a guest-resident-key workaround is refused | NFR-SEC-50 |
| P6-D1 | A1 | The edge is made unreachable by a crash, connection flood, or upstream-timeout storm, losing the sole outbound path | Fail-closed: outbound traffic drops, never bypasses; per-session egress rate / connection quota bounds the flood | NFR-SEC-46, NFR-SEC-53 |
| P6-D3 | A3 | Clock rollback at the edge defeats denylist-propagation timing | Denylist propagation reads a monotonic clock; the denylist is also checked directly on every connection, giving a non-clock revoke path | NFR-SEC-48, NFR-SEC-63 |
| P6-T1 | A3 | At the TLS-termination segment the edge holds plaintext between decrypt and re-encrypt; a compromised edge alters bodies undetected | The hop is the single inspection point, rooted in the edge's own CA, TLS 1.3 on both legs; the carve-out is one auditable point, not a per-destination scatter | NFR-SEC-05, NFR-SEC-33 |
| P5-D2 | A1 | The guest floods the edge with connection/request volume to deny outbound to co-tenant sessions or amplify against an origin | Single forward proxy with one outbound socket bounds the surface; fail-closed drops rather than bypasses; per-session egress rate / connection quota | NFR-SEC-05, NFR-SEC-27 |

Residuals track to [`06-threat-model.md`](../06-threat-model.md) §5; the MITIGATED P6 STRIDE rows live in §4.

| Residual | Rows | Tracking |
|---|---|---|
| Content-blind exfil at the baseline hop | P6-I1 | [#182](https://github.com/Wide-Moat/open-computer-use/issues/182) |
| Permissive baseline reach; a block surfaces as a connect failure, not a structured deny | P6-R1 | [#272](https://github.com/Wide-Moat/open-computer-use/issues/272) |
| SNI/Host consistency under the allow-list hardening | P6-E1 | [#198](https://github.com/Wide-Moat/open-computer-use/issues/198) |
| No-credential-in-response stripping; edge-binary/config attestation; plaintext-zeroization lack an explicit NFR | P6-I2, P6-T1, P6-I3 | [#197](https://github.com/Wide-Moat/open-computer-use/issues/197) |
| Egress-side scope as defence-in-depth over the storage engine's claim check | P6-E2 | [#187](https://github.com/Wide-Moat/open-computer-use/issues/187) |
| Guest-resident-key upstream schemes unsupported | P6-E3 | [#176](https://github.com/Wide-Moat/open-computer-use/issues/176) |
| Per-sandbox egress conn-rate / fd containment | P6-D1, P5-D2 | [#188](https://github.com/Wide-Moat/open-computer-use/issues/188) |
| Clock-rollback | P6-D3 | [#185](https://github.com/Wide-Moat/open-computer-use/issues/185) |

## Operational concerns

**Config surface (baseline).** The edge's own inspection CA (its public root cert pushed into the guest trust store at provisioning), the proxy-owned resolver and its mandatory deny-set ([NFR-SEC-12](../manifesto/02-nfrs.md)), and the per-session egress rate / connection ceilings. The baseline carries no destination allow-list and no structured-deny vocabulary.

**Config surface (optional hardening).** Three additions on the same hop, each enabled per deployment, none baseline:

| Hardening | What it adds |
|---|---|
| Destination allow-list | deny-by-default resolved-IP + SNI rules, SNI pre-filter drop before TLS, SNI/Host consistency on the inspected leg ([NFR-SEC-16](../manifesto/02-nfrs.md), [NFR-SEC-27](../manifesto/02-nfrs.md)) |
| Structured deny | the `x-deny-reason` vocabulary on a hop-side block, so a denial is machine-parseable rather than a connect failure ([NFR-SEC-17](../manifesto/02-nfrs.md)) |
| Egress-side scope | per-destination / per-claim scope binding at the hop as defence-in-depth over the storage engine's check ([#187](https://github.com/Wide-Moat/open-computer-use/issues/187)) |

Edge-injection of an authenticated-upstream credential ([ADR-0007](../adr/0007-egress-auth-mechanism.md)) is a separate hardening that pairs with the allow-list rung; the baseline forwards the caller's own credential and injects nothing. DLP-ICAP is a configuration of the inspecting hop, not a separate rung ([NFR-FLEX-15](../manifesto/02-nfrs.md), [NFR-COMP-28](../manifesto/02-nfrs.md)).

**Observability.** The edge emits an OCSF event per connection on F10, against the audit contract ([`08-contracts.md`](../08-contracts.md) §1) and [NFR-SEC-03](../manifesto/02-nfrs.md). A baseline block records the connect failure; the structured `x-deny-reason` appears only under the structured-deny hardening. A storage scope denial is the storage engine's JSON response observed in the audit stream, not a hop-authored deny event. The payload-independent exfil tripwire ([NFR-SEC-57](../manifesto/02-nfrs.md)) raises a structured OCSF anomaly event on the inspected hop.

**Scaling axis.** A per-host shared edge serves many co-located sessions, which makes it a shared DoS surface (P5-D2 / P6-D1); the per-session rate / fd ceiling under [NFR-SEC-46](../manifesto/02-nfrs.md) is the containment, with [NFR-SEC-53](../manifesto/02-nfrs.md) bounding the sibling MCP-gateway listener. Whether the edge is one-per-host or one-per-deployment tracks the same instantiation question as the object-store service ([#175](https://github.com/Wide-Moat/open-computer-use/issues/175)).

**Rotation / lifecycle.** At the baseline the edge holds no credential to rotate — the storage JWT is off-box-issued and passes through, and refresh is the issuer's, deferred per [ADR-0013](../adr/0013-storage-credential-custody.md). Under edge-injection hardening the edge receives the upstream credential from SDS per-connection and drops it after use; rotation belongs to the SDS source ([NFR-SEC-04](../manifesto/02-nfrs.md)). On sandbox teardown the host-driven finalizer drops the network-bound egress route host-side even if the guest is unresponsive ([NFR-SEC-65](../manifesto/02-nfrs.md)).

**Shelf delta** ([`05-c4-container.md`](../05-c4-container.md) §5): the baseline is one TLS-terminating inspection hop with the inspection CA's public cert auto-injected into the sandbox trust store at start — the one-click solo path runs here with no allow-list to curate ([NFR-FLEX-15](../manifesto/02-nfrs.md)). A deployment that needs destination restriction enables the allow-list hardening; one that needs an authenticated upstream enables edge-injection ([ADR-0007](../adr/0007-egress-auth-mechanism.md)), pointing the credential at a file SDS source (solo) or a customer-provided SDS source (enterprise).

## Open questions

1. The baseline-block residual — a permissive hop reaches arbitrary hosts and plaintext HTTP, and a block surfaces as a connect failure rather than a structured deny ([#272](https://github.com/Wide-Moat/open-computer-use/issues/272)); content-blind exfil over that hop is the content-blind theme ([#182](https://github.com/Wide-Moat/open-computer-use/issues/182)).
2. Envoy's `credential_injector` filter and its OAuth2 extension carry an upstream maturity caveat for the edge-injection hardening — intended for trusted-on-both-ends paths, while a third-party LLM API is an untrusted upstream. The regulated-tier posture for this filter is deferred pending a security review ([#240](https://github.com/Wide-Moat/open-computer-use/issues/240)).
3. SNI/Host consistency under the allow-list hardening, where the SNI pre-filter alone misses domain-fronting ([#198](https://github.com/Wide-Moat/open-computer-use/issues/198)).
4. No-credential-in-response stripping, edge-binary/config attestation, and plaintext-zeroization for the TLS-termination segment lack an explicit NFR ([#197](https://github.com/Wide-Moat/open-computer-use/issues/197)).
5. Egress-side scope binding as defence-in-depth over the storage engine's claim check, and the mTLS / cert-pin / DPoP upstreams the edge cannot serve by injection ([#187](https://github.com/Wide-Moat/open-computer-use/issues/187), [#176](https://github.com/Wide-Moat/open-computer-use/issues/176)).
