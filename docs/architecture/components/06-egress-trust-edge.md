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
adr: []
---

The sandbox's sole outbound network path: it enforces a deny-by-default destination allow-list, emits a structured deny reason, and on the legs that need it attaches the upstream authorization fetched from custody so the guest sends an unauthenticated request. Audience: engineers and security reviewers wiring or auditing egress policy.

# Component-06: Egress trust-edge proxy

## Purpose

The single outbound path for the sandbox: it resolves each destination against a deny-by-default allow-list and, on a MITM-mode leg only, originates the upstream connection so it can attach the custody-fetched authorization the guest never holds ([`05-c4-container.md`](../05-c4-container.md) §3). The destination-to-mode binding is per-destination state held only at the edge, so one egress process serves a transparent leg and a MITM leg at once.

## Boundaries

The intra-container view. The inbound sandbox leg, the custody lease-pull leg, the broker backend leg, and the audit fan-in are the boundaries [`05-c4-container.md`](../05-c4-container.md) §4 names; their `F9`/`F8`/`F10`/`F11` flow labels are defined in [`06-threat-model.md`](../06-threat-model.md) §1. Token classes are owned by [`02-trust-boundaries.md`](../02-trust-boundaries.md) §8; TTLs are not repeated here.

The edge is one process with four internal faces:

| Internal face | What it does |
|---|---|
| sandbox listener | accepts the guest's unauthenticated outbound request on the network-bound default route |
| lease puller | pulls a Custody credential lease from custody at injection time, per connection |
| upstream originator | resolves the destination, and on a MITM-mode leg terminates and re-originates the TLS with the injected authorization attached |
| audit emitter | emits an OCSF allow/deny event, denials carrying the `x-deny-reason` vocabulary |

Owned state: the destination allow-list (resolved-IP + SNI rules), the per-destination mode binding (transparent vs MITM), and a lease held only for the life of one upstream connection. The edge holds no standing upstream credential at rest — the lease is pulled at injection and dropped after use ([NFR-SEC-29](../manifesto/02-nfrs.md)). It authors no denylist and holds no kill-switch route — the denylist is the Control/operator API's; the edge reads it as a deny signal. It holds no object-store credential — the broker signs its own backend leg ([NFR-SEC-25](../manifesto/02-nfrs.md)), and the broker backend leg (F10) traverses the edge as one allow-list destination with no TLS termination, so the broker-produced signature is forwarded byte-intact.

Token classes ([`02-trust-boundaries.md`](../02-trust-boundaries.md) §8 owns the taxonomy): the edge pulls a Custody credential lease and presents the injected authorization upstream; the guest-facing leg carries no token at all. The lease-pull (F8) is a frozen Protobuf/gRPC define surface ([`08-contracts.md`](../08-contracts.md) §1, [NFR-SEC-29](../manifesto/02-nfrs.md)) whose schema file is not yet built ([#205](https://github.com/Wide-Moat/open-computer-use/issues/205)); the outbound leg (F9) is a network property with no wire schema by design ([NFR-SEC-27](../manifesto/02-nfrs.md)); the broker backend leg (F10) is conform ([NFR-SEC-16](../manifesto/02-nfrs.md)). The downloadable axis reaches the edge as a broker-resolved deny signal, not a field the guest's outbound request carries ([NFR-SEC-73](../manifesto/02-nfrs.md)).

## Invariants

Each rule holds independent of the caller and is falsifiable by the named check. Egress *posture* (transparent vs MITM), in-transit-encryption carve-outs, and zone membership are Layer 3 properties, not invariants here.

- Every outbound connection resolves through this process; the sandbox has no route out other than F9 (network-policy IaC assertion, [NFR-SEC-27](../manifesto/02-nfrs.md)).
- A destination not matched by an allow-list rule is dropped before the TLS handshake at the SNI pre-filter, with no partial connect (integration test, [NFR-SEC-08](../manifesto/02-nfrs.md), [NFR-SEC-17](../manifesto/02-nfrs.md)).
- The proxy-owned resolver is the sole resolution authority: a guest-supplied A/AAAA cannot override it for an egress destination, and the mandatory deny-set is filtered on resolved IP at connect, never on DNS resolution (unit test per rejection class + in-guest rebind negative test, [NFR-SEC-12](../manifesto/02-nfrs.md)).
- Every denied connection is a machine-parseable object carrying the `x-deny-reason` vocabulary, never free text (schema-validation, [NFR-SEC-17](../manifesto/02-nfrs.md)).
- Injection is reachable only on the edge-originated upstream leg of a MITM-mode destination; the guest→edge leg and every transparent-mode leg carry no upstream credential (integration test asserting no credential in the guest, [NFR-SEC-23](../manifesto/02-nfrs.md), [NFR-SEC-27](../manifesto/02-nfrs.md)).
- The injected authorization never reaches a guest-visible response surface; it is stripped before any response crosses back to the guest leg (integration test, [NFR-SEC-23](../manifesto/02-nfrs.md)).
- When the denylist names a session, the edge pulls and attaches no lease for it, independent of the lease TTL ceiling (integration test, [NFR-SEC-04](../manifesto/02-nfrs.md), [NFR-SEC-29](../manifesto/02-nfrs.md)).
- An outbound leg for an object the broker resolved `downloadable=false` is denied with a structured reason in both transparent and MITM modes (edge integration test, [NFR-SEC-73](../manifesto/02-nfrs.md)).
- A destination tagged allow-list-only is forwarded byte-intact; the edge never terminates or re-signs the broker backend leg (integration test, [NFR-SEC-16](../manifesto/02-nfrs.md), [NFR-SEC-25](../manifesto/02-nfrs.md)).
- TTL and revocation decisions read a monotonic clock, so a wall-clock setback cannot extend a lease past its window (clock-rollback red-team harness, [NFR-SEC-48](../manifesto/02-nfrs.md), [NFR-SEC-63](../manifesto/02-nfrs.md)).

## Failure modes

Each row traces to one P6/P5 STRIDE row in [`06-threat-model.md`](../06-threat-model.md) §3 and repeats that row's controlling NFR; the actor labels are owned by [`06-threat-model.md`](../06-threat-model.md) §2 (A1 in-sandbox guest, A3 host-side). Fail-closed is the default on every egress, lease, and deny boundary.

| Trace | Reaching actor | What goes wrong | Recovery behaviour | Controlling NFR |
|---|---|---|---|---|
| P6-R1 | A1 | A policy-violating egress attempt is later disputed and the decision, destination, and injected-or-not are not durably recorded | Emit OCSF on F11 for every allow and deny; denials carry the structured `x-deny-reason`; SNI pre-filter drops and L7 inspections both record | NFR-SEC-03 |
| P6-I1 | A1 | Content-blind exfil: the guest tunnels data to an allow-listed destination over the transparent (non-inspecting) leg | Allow-list narrows destinations; the payload-independent byte/cardinality tripwire arms in both modes; deep DLP requires opt-in MITM | NFR-SEC-57, NFR-SEC-73 |
| P6-I2 | A1 | The injected credential leaks back to the guest via an error, redirect, or reflected header in MITM mode | Strip injected authorization from every response surface before it crosses to the guest leg; injection only on the edge-originated leg; lease short-TTL and per-resource scoped | NFR-SEC-23, NFR-SEC-29 |
| P6-I3 | A3 | The MITM decrypt/re-encrypt segment exposes plaintext at the edge in memory or swap | MITM is opt-in per-destination, a single named inspection segment, TLS 1.3 on both legs; transparent and broker legs never terminate | NFR-SEC-05, NFR-SEC-33 |
| P6-E1 | A1 | Allow-list bypass via SNI≠Host domain-fronting, CONNECT abuse, DNS rebinding, or raw-IP / non-HTTP | Deny-by-default; SNI pre-filter drop before TLS; L7 SNI/Host consistency check on the inspected leg; proxy-owned resolver | NFR-SEC-27, NFR-SEC-05, NFR-SEC-16 |
| P6-E2 | A1 | The guest forces injection toward an unintended destination via a cross-scope allow-list entry or open redirect on an allowed upstream | Pull only the lease matching the validated destination, so a mis-routed credential stays bounded to its resource scope | NFR-SEC-29, NFR-SEC-23, NFR-SEC-73 |
| P6-E3 | A1 | The upstream needs client-mTLS / cert-pin / DPoP, which edge token-injection cannot satisfy | Re-originate the upstream TLS in MITM mode with a custody-held client cert / PoP key; a guest-resident-key workaround is refused at config time with a structured deny | NFR-SEC-50 |
| P6-D1 | A1 | The edge is made unreachable by a crash, connection flood, or upstream-timeout storm, losing the sole outbound path | Fail-closed: outbound traffic drops, never bypasses; unallowed destinations dropped cheaply at the SNI pre-filter before TLS to bound handshake-exhaustion cost | NFR-SEC-46, NFR-SEC-53 |
| P6-D3 | A3 | Clock rollback at the edge extends an expired lease or defeats denylist-propagation timing | TTL/revoke read a monotonic clock; the denylist is also checked directly, giving a non-clock revoke path | NFR-SEC-48, NFR-SEC-63 |
| P6-T1 | A3 | In MITM mode the edge holds plaintext between decrypt and re-encrypt; a compromised edge alters bodies undetected | MITM is opt-in per-destination, customer-CA-rooted, TLS 1.3 on both legs; the carve-out is a single auditable inspection point | NFR-SEC-05, NFR-SEC-33 |
| P5-D2 | A1 | The guest floods the edge with connection/request volume to deny outbound to co-tenant sessions or amplify against an upstream | Single forward proxy bounds reachable destinations; fail-closed drops rather than bypasses; per-session egress rate / connection quota | NFR-SEC-05, NFR-SEC-27 |

Residual, by [`06-threat-model.md`](../06-threat-model.md) §5 register: the transparent (non-inspected) leg stays content-blind, so P6-I1 records only metadata and P6-R1 can dispute only metadata — content-blind transparent egress, accepted-with-tier ([#182](https://github.com/Wide-Moat/open-computer-use/issues/182)). The no-credential-in-response stripping behind P6-I2, the edge-binary/config attestation behind P6-T1, and the plaintext-zeroization behind P6-I3 lack an explicit NFR ([#197](https://github.com/Wide-Moat/open-computer-use/issues/197)). SNI/Host consistency on the transparent leg behind P6-E1 is unenforced ([#198](https://github.com/Wide-Moat/open-computer-use/issues/198)). The destination-to-lease binding and per-action authz behind P6-E2 are tracked at [#187](https://github.com/Wide-Moat/open-computer-use/issues/187); the guest-resident-key schemes behind P6-E3 are declared unsupported ([#176](https://github.com/Wide-Moat/open-computer-use/issues/176)). The per-sandbox egress conn-rate / fd containment behind P6-D1 / P5-D2 is the resource-exhaustion theme — NFR-SEC-46 is the edge control and NFR-SEC-53 the sibling MCP-gateway-listener ceiling ([#188](https://github.com/Wide-Moat/open-computer-use/issues/188)). Clock-rollback behind P6-D3 is the trusted-time theme ([#185](https://github.com/Wide-Moat/open-computer-use/issues/185)). The MITIGATED P6 rows (the listener spoof, the MITM upstream spoof, the broker-leg tamper, the lease-fetch DoS) live in [`06-threat-model.md`](../06-threat-model.md) §4.

## Operational concerns

**Config surface.** The allow-list (resolved-IP + SNI rules per destination), the per-destination egress mode ([`02-trust-boundaries.md`](../02-trust-boundaries.md) §7), the proxy-owned resolver and its deny-set (the canonical list is in [NFR-SEC-12](../manifesto/02-nfrs.md), enforced by the resolver invariant above), and the per-session egress rate / connection ceilings. DLP-ICAP is a configuration of the MITM mode, not a third mode ([NFR-FLEX-15](../manifesto/02-nfrs.md), [NFR-COMP-28](../manifesto/02-nfrs.md)).

**Observability.** The edge emits an OCSF event for every allow and deny on fan-in flow F11, denials carrying the `x-deny-reason`, against the audit contract ([`08-contracts.md`](../08-contracts.md) §1) and [NFR-SEC-03](../manifesto/02-nfrs.md). The payload-independent exfil tripwire ([NFR-SEC-57](../manifesto/02-nfrs.md)) raises a structured OCSF anomaly event in both postures.

**Scaling axis.** A per-host shared edge serves many co-located sessions, which makes it a shared DoS surface (P5-D2 / P6-D1); the per-session rate / fd ceiling under [NFR-SEC-46](../manifesto/02-nfrs.md) is the containment, with [NFR-SEC-53](../manifesto/02-nfrs.md) bounding the sibling MCP-gateway listener, not the edge. Whether the edge is one-per-host or one-per-deployment tracks the same instantiation question as custody and the broker ([#175](https://github.com/Wide-Moat/open-computer-use/issues/175)).

**Rotation / lifecycle.** Leases are pulled per-connection and dropped after use; rotation is custody's, not the edge's ([NFR-SEC-04](../manifesto/02-nfrs.md)). On sandbox teardown the host-driven finalizer drops the network-bound egress route host-side even if the guest is unresponsive ([NFR-SEC-65](../manifesto/02-nfrs.md)).

**Shelf delta** ([`05-c4-container.md`](../05-c4-container.md) §5): the minimal shelf runs transparent pass-through (no customer CA, one-click solo path) and cannot inject; the full shelf adds opt-in MITM-inspecting mode with a customer CA in the sandbox trust store, the only mode that attaches an upstream credential. The boundary properties in the Invariants section hold on both shelves; only TLS termination and injection capability change with the mode. The forward-proxy substrate and the MITM-termination substrate are future ADRs — `needs ADR:` (see Open questions); no technology is decided here.

## Open questions

1. The lease-pull (F8) define surface and the broker downloadable-axis deny signal have no built schema file yet — tracked with the other unbuilt proto/REST surfaces at [#205](https://github.com/Wide-Moat/open-computer-use/issues/205); the `contract:` key stays `null` until the file lands.
2. Forward-proxy substrate and MITM-termination technology are undecided — needs ADR: record the edge runtime / substrate pick (role named here only, never decided in prose), coupled to [NFR-FLEX-15](../manifesto/02-nfrs.md) / [NFR-COMP-28](../manifesto/02-nfrs.md).
3. SNI/Host consistency on the transparent (non-inspected) leg, where the SNI pre-filter alone misses domain-fronting — [#198](https://github.com/Wide-Moat/open-computer-use/issues/198).
4. No-credential-in-response stripping, edge-binary/config attestation, and plaintext-zeroization for the MITM mode lack an explicit NFR — [#197](https://github.com/Wide-Moat/open-computer-use/issues/197).
5. mTLS / cert-pin / DPoP upstreams the edge cannot serve by injection, and the guest-resident-key schemes declared unsupported — [#176](https://github.com/Wide-Moat/open-computer-use/issues/176).