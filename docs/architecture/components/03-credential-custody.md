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

The host-side custodian of upstream credentials: it mints a scoped, short-lived lease for the Egress trust-edge at injection time and holds no guest-reachable surface. Audience: engineers and security reviewers implementing or auditing credential custody.

# Component-03: Credential custody

## Purpose

Holds the real upstream credentials host-side and hands the Egress trust-edge a scoped, short-lived lease at injection time, never the guest ([`05-c4-container.md`](../05-c4-container.md) §3). Custody delegates rather than returns the root: it mints a per-session, STS-narrowed lease and retains no code path that returns the master key to any caller.

## Boundaries

Intra-container, three components answer the lease-pull and rotate the root:

| Internal component | Call it answers | Calls it makes |
|---|---|---|
| lease issuer | the lease-pull (north edge of `F8`): validate the requested upstream resource against the session, mint an STS-narrowed lease | reads the secret store; asks the STS delegator to narrow; writes a lease-issue audit event |
| STS delegator | "narrow this root to one resource class for the lease TTL" | calls the upstream STS / token-exchange to derive a scoped credential below the root |
| secret store + rotation | hold the root upstream credential at rest; rotate on cadence | serves the lease issuer; serves no guest-reachable caller |

The edge lease-pull (`F8`), the operator/SOAR rotate-and-revoke path, and the audit fan-in are the boundaries [`05-c4-container.md`](../05-c4-container.md) §4 names (their `F8`/`F11` flow labels are defined in [`06-threat-model.md`](../06-threat-model.md) §1); this spec adds only which internal component terminates each.

Owned state: the root upstream credentials (master keys / service-account material) and the rotation schedule. Custody is the sole custodian of these; no other container holds them. The storage-backend credential is held by the Storage broker, not here ([NFR-SEC-23](../manifesto/02-nfrs.md)).

Does not hold or expose: no guest-facing interface (no socket, mount, or route a sandbox can reach); no kill-switch or denylist route — revocation reaches custody from the operator surface, custody does not own the switch; no second outbound path of its own beyond the STS/token-exchange leg, which traverses the single egress allow-list like any other destination.

Token classes ([`02-trust-boundaries.md`](../02-trust-boundaries.md) §8 owns the taxonomy): custody mints the Custody credential lease consumed only by the edge and authenticates the edge on `F8` with a Generic internal token; it never sees the Session JWT or the Storage-mount handle, both guest-held. The `F8` wire shape is the `contracts/proto/` lease-pull surface (`Credential custody → Egress trust-edge`, Protobuf/gRPC, define) listed in [`08-contracts.md`](../08-contracts.md) §1; that file is unbuilt ([#205](https://github.com/Wide-Moat/open-computer-use/issues/205)), so this spec binds `contract: null` and states only what a schema cannot encode: the lease issuer terminates `F8`, and the edge — not custody — originates the upstream TLS the lease authorizes ([NFR-SEC-30](../manifesto/02-nfrs.md)).

## Invariants

Each holds independent of the caller and is falsifiable by the named check.

- No listener, socket, or route resolvable from a sandbox network or namespace binds to custody; the only inbound caller is the edge over `F8` under a Generic internal token (IaC-policy assertion that no custody bind address is on a guest-reachable network, NFR-SEC-23).
- Every credential leaving custody is an STS-narrowed lease, never the master key; no code path returns the root over `F8` or any RPC (unit-test that the lease-issue path returns only a delegated credential + property-test that no response body equals the stored root, NFR-SEC-29).
- A minted lease names exactly one bucket prefix or one API-key class, never wider than the request resolves to (property-test over requested-vs-minted scope, reject on widen, NFR-SEC-29).
- The session identity custody binds against is the host-attested identity the edge presents, never a claim in a guest-supplied body (unit-test that a body-supplied session id is ignored when it disagrees with the host-attested caller, NFR-SEC-29).
- Lease expiry and the high-value revoke window (the TTLs are canonical in [`02-trust-boundaries.md`](../02-trust-boundaries.md) §8 / NFR-SEC-29) compute against a monotonic source immune to wall-clock setback; the platform trusted-time floor is owned by §8 and this is its custody-side consequence (clock-rollback harness asserts a wall-clock setback ≥ a TTL window does not extend a lease, NFR-SEC-48).
- The secret store holds the root under authenticated encryption with key custody host-local (minimal shelf) or HSM-rooted (full shelf); custody-process memory is not claimed secret against a host-root adversary on either shelf (deployment audit asserts no plaintext root on disk and the configured key-custody root matches the shelf, NFR-SEC-33, NFR-SEC-59).
- A system-initiated per-session lease issue or scope-change emits a chain-linked OCSF event before the issue is acknowledged; an operator-forced mint, rotate, or scope-change is the operator-initiated audit set; an audit-write failure fails the operation closed (integration-test that a mint with the audit write failing returns no lease, NFR-SEC-72, NFR-SEC-45).

## Failure modes

Each row traces to one P3 or F8 STRIDE row in [`06-threat-model.md`](../06-threat-model.md) §3 and repeats that row's controlling NFR; threat narrative, rating, and regulator cells stay there. Recovery is fail-closed at every credential boundary. A1 is the in-sandbox guest reaching custody only through the edge; A3 is a host-foothold adversary.

| Trace | Reaching actor | What goes wrong | Recovery behaviour | Controlling NFR |
|---|---|---|---|---|
| P3-E1 | A1 (via the edge) | Over-broad lease requested to widen blast radius beyond the session's resource | Lease issuer mints at most one resource-class scope and rejects a widen; an over-broad ask fails closed, no lease issued | NFR-SEC-29 |
| P3-T1 | A3 | Tampered issuance request carrying a caller-supplied policy to mint a wider scope | STS delegator derives scope from the validated request, not a caller policy; a tampered request fails validation and mints nothing | NFR-SEC-29 |
| P3-T2 | A3 | Wall-clock setback used to extend a live lease past its TTL | TTL and revoke read the monotonic clock, so a setback does not extend a lease; revoke reaches custody by the denylist independent of self-expiry | NFR-SEC-48 |
| P3-R1 | A3 | Operator-forced mint / rotate / scope-change disputed for lack of a record | The forced action emits a mandatory chain-linked event before acknowledgement; on audit-write failure the action is denied | NFR-SEC-45 |
| P3-I1 | A3 | At-rest store or live process scraped for the root | Root held under authenticated encryption; delegated STS hands out leases, not the root, so a session-path compromise cannot reach the master key. Live in-process secrecy is disclaimed against host-root (see P3-I2) | NFR-SEC-33 |
| P3-I2 | A3 | Live lease or root frozen into a snapshot / hibernation image | Clean-before-stop zeroizes live root/lease material before an image is taken; the image's artifacts are encrypted at rest; the lease TTL bounds a captured lease | NFR-SEC-44, NFR-SEC-61 |
| P3-D1 | A3 | Custody made unavailable host-side so the edge cannot fetch a lease | Unreachable custody fails closed: the upstream-authenticated leg drops, never bypasses; in-flight sessions run under existing leases until TTL. A guest has no path to drive custody load | NFR-SEC-23 |
| F8-I1 | A3 | Lease intercepted or captured in flight / at the edge | Fetched at injection, never persisted to the guest, host-side encrypted in transit; scope + lease TTL + high-value revoke bound a captured lease, and a revoked session blocks injection at the edge | NFR-SEC-29 |

PARTIAL-row residuals (by [`06-threat-model.md`](../06-threat-model.md) §5 register theme + tracking issue):

- P3-E1, P3-T1 — minimum lease scope per tool/action below resource-class is unstated (per-action authorization theme, [#187](https://github.com/Wide-Moat/open-computer-use/issues/187)).
- P3-T2 — monotonic-clock TTL enforcement specified, implementation tracked (trusted-time theme, [#185](https://github.com/Wide-Moat/open-computer-use/issues/185)).
- P3-R1 — mandatory privileged-action audit beyond tier-downgrade (privileged-operator-audit theme, [#186](https://github.com/Wide-Moat/open-computer-use/issues/186)).
- P3-I1, P3-I2, F8-I1 — a live lease captured in a host memory image escapes the at-rest envelope (snapshot-secret theme, [#184](https://github.com/Wide-Moat/open-computer-use/issues/184)); PoP / client-mTLS upstreams shift where the credential lives ([#176](https://github.com/Wide-Moat/open-computer-use/issues/176)).
- P3-D1 — no NFR scenario pins a custody RTO/RPO target; host-side resource-exhaustion containment is tracked under the resource-exhaustion theme ([#188](https://github.com/Wide-Moat/open-computer-use/issues/188)). The pure custody-availability target gap is unfiled (see Open questions).

Spoofing of the custody process and STS-delegation elevation are MITIGATED in [`06-threat-model.md`](../06-threat-model.md) §4 and are not live rows here.

## Operational concerns

Config surface: the upstream-resource catalogue (which bucket prefixes / API-key classes a lease may name), the rotation cadence per credential class, the secret-store backend and its key-custody root, and the STS / token-exchange endpoint per upstream. The high-value class (LLM upstream API key) carries the tighter TTL and revoke window per [NFR-SEC-23](../manifesto/02-nfrs.md) and [NFR-SEC-29](../manifesto/02-nfrs.md) (the §8 table holds the base lease class).

Observability and audit: custody emits OCSF on the fan-in flow `F11` for every lease mint, rotate, scope-change, and revoke — system-initiated issues under [NFR-SEC-72](../manifesto/02-nfrs.md), operator-forced actions under [NFR-SEC-45](../manifesto/02-nfrs.md) — written via the durable bus on the critical path ([NFR-REL-12](../manifesto/02-nfrs.md)) into the hash-chained store under the retention floor ([NFR-COMP-01](../manifesto/02-nfrs.md)). The lease-issue event is a host-authored record; it is not the NFR-SEC-47 out-of-band evidence set for in-sandbox actions, which is the audit pipeline's concern.

Scaling axis: per-deployment or per-sandbox-host, open at [#175](https://github.com/Wide-Moat/open-computer-use/issues/175), which also decides whether the container diagram changes. Capacity is bounded by lease-issuance rate; the lease issuer never buffers a root in a returnable response. No REL NFR pins a custody RTO/RPO; the accepted gap is recorded in Open questions rather than invented here.

Rotation discipline: rotating the root is custody-internal and does not invalidate in-flight leases — those self-expire and revoke per the TTL and audit invariants above; the one new fact is that root rotation is independent of live-lease validity.

Shelf delta from [`05-c4-container.md`](../05-c4-container.md) §5: minimal shelf uses a host-local signing key and host-local root credential; full shelf uses a customer-PKI workload identity with the root HSM-rooted (FIPS 140-3 L3) and STS-scoped per session ([NFR-FLEX-04](../manifesto/02-nfrs.md)). Boundary invariants hold on both shelves; only the key-custody substrate and STS narrowness change. Edge re-origination for mTLS / cert-pin / DPoP upstreams pulls a client-cert/key or PoP key from custody as a credential class under the same lease discipline ([NFR-SEC-50](../manifesto/02-nfrs.md)). The concrete custody / KMS product and PKCS#11 / KMIP wiring are a future ADR, not decided here.

## Open questions

1. One custody per deployment or one per sandbox host, and does the answer change the container diagram? — [#175](https://github.com/Wide-Moat/open-computer-use/issues/175).
2. Does Credential custody collapse into a generic Secrets-custody context, and the build-vs-buy call for the secret store / delegated-STS issuer? — [#169](https://github.com/Wide-Moat/open-computer-use/issues/169).
3. Minimum lease scope per tool/action below resource-class (least-privilege) — [#187](https://github.com/Wide-Moat/open-computer-use/issues/187).
4. Custody-side credential class and lease discipline for mTLS / cert-pin / DPoP upstreams the edge re-originates — [#176](https://github.com/Wide-Moat/open-computer-use/issues/176).
5. needs issue: define a custody availability target (RTO/RPO) for the lease-issuance path, given that an unreachable custody fails closed and drops upstream-authenticated traffic for in-flight sessions at lease TTL (P3-D1 names no RTO/RPO at this element; resource-exhaustion containment is #188).