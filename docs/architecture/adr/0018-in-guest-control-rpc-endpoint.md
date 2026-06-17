<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-06-17
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
amends: [0017]
compliance-impact: [SOC2-CC6.1, NYDFS-500.15]
license-impact: none
threat-mitigation-link: ../06-threat-model.md
blocks: []
blockedBy: [0017]
---

The host-dialled in-guest control-RPC endpoint runs HTTP+JSON over a host-owned Unix socket, carries a closed tagged-union of verbs that hold no standalone authority, and ships one verb in v1 — a cooperative `shutdown` the host-driven finalizer outranks. Audience: engineers implementing or auditing the per-session executor's control face.

# ADR-0018: In-guest control-RPC endpoint (FID-03)

## Status

`proposed`

## Context

[ADR-0017](0017-control-plane-repo-boundary.md) names a "host-only HTTP/vsock control port" once, as evidence the Control plane and the per-session executor talk over a host-dialled channel rather than in-process, and files the executor's host-side face as a "thin control driver." It does not specify that port: no transport, no wire format, no verb set, no authority model. The result is a named-but-ungoverned third host-dialled inbound surface alongside the exec WebSocket and the mount-config push. The per-session executor ([`05-session-sandbox.md`](../components/05-session-sandbox.md)) needs this surface to receive a host-initiated cooperative shutdown, and a guest listener has no canon contract to build to.

Three forces make the contract load-bearing.

First, the endpoint is a second inbound listener inside the hostile guest. Whatever it accepts must inherit the same accept-time host-attested-identity floor as the exec channel (NFR-SEC-43 enforced at accept by NFR-SEC-76), or it becomes a guest-reachable authority path the exec channel was hardened to deny.

Second, a control verb that carried its own authority would let a guest that reaches the socket — or a body field a caller forges — name another session, install a key, or claim teardown is done. The session registry's `container_name` binding is the host-attested auth predicate a later host connection is validated against ([`02-control-operator-api.md`](../components/02-control-operator-api.md) sole-custody; [`02-trust-boundaries.md`](../02-trust-boundaries.md) §8, NFR-SEC-10), and the control-WS verify-key decides who counts as host — both are exactly the things a verb must not be allowed to rewrite from inside the guest.

Third, `shutdown` overlaps the host-driven ordered finalizer ([`05-session-sandbox.md`](../components/05-session-sandbox.md) Operational concerns, NFR-SEC-65), which revokes the session credential, drops the egress route, and scrubs writable surfaces independent of guest cooperation. A `shutdown` verb that could substitute for or mark-complete any finalizer step would hand a compromised guest a teardown-evasion path (P2-T2).

Scope is the docker/runc/runsc tiers, whose canon transport is the host kernel with UDS peer-credential checks ([`05-session-sandbox.md`](../components/05-session-sandbox.md) Shelf delta). The microVM tier's vsock control transport and its freeze/thaw/mount_root/snapstart verb set are a separate decision, deferred here.

## Decision

We will specify the FID-03 endpoint [ADR-0017](0017-control-plane-repo-boundary.md) names, as a contract ([`contracts/control/control-rpc.schema.json`](../../../contracts/control/control-rpc.schema.json), [`08-contracts.md`](../08-contracts.md) §1):

- **Transport is a host-owned Unix domain socket; the guest authenticates the caller by kernel peer-credentials / per-session socket path, and a non-host peer is dropped at accept before any frame is parsed** (NFR-SEC-43, NFR-SEC-76). Not loopback TCP: the guest shares the loopback stack, so a TCP control port is a guest-reachable surface by default.
- **Wire is HTTP+JSON over that socket**, a closed externally-tagged union. An unknown tag is a hard protocol error on both sides, never silent-accept; a future verb is an additive schema change (NFR-IC-04), not an open extension point. Errors reuse the exec channel's bounded-reason envelope (NFR-SEC-51).
- **No verb carries standalone authority.** The sole authority is the host-attested caller identity re-checked at accept; every body field is a hint, never the authority (mirrors component-02's hint-never-authority invariant). An under-specified verb fails closed.
- **The v1 verb set is a single `shutdown`** (wire tag `Shutdown`), a cooperative fast-path. It can at most advance the cooperative SIGTERM phase the guest already runs; it can never reorder, substitute for, or mark-complete the host-driven finalizer (NFR-SEC-65), which executes regardless of any guest reply. It is idempotent and host-caller-only, and carries no body — there is no session or `container_name` field to forge.

Control verbs stay out of the exec/PTY+CDP union ([`contracts/exec/exec-channel.schema.json`](../../../contracts/exec/exec-channel.schema.json)); `ShuttingDown` there is a server→client notification, not a host verb.

## Consequences

- **The endpoint is a second host-dialled listener, governed by [`05-session-sandbox.md`](../components/05-session-sandbox.md) invariant 15.** Invariant 2 stays scoped to the exec listener; the new invariant inherits the NFR-SEC-43/76 accept-drop for the control-RPC listener, holds invariant 4 (no new outbound route), and extends invariant 3's guest-stack-dial and forge-another-session predicates to it.
- **`shutdown` is a fast-path, not a teardown owner.** [`05-session-sandbox.md`](../components/05-session-sandbox.md) Operational concerns records that a guest which drops the verb, replies wrongly, or skips the cooperative phase and claims clean is overridden by the host-executed finalizer and gains no new authority — the P2-T2 row's fail-closed property, now also exercised on this verb.
- **`container_name` update is forbidden on this endpoint, in every version.** A guest-supplied or guest-mutated name can never become the `expected_container_name` a later host connection is validated against (rename-poison; the host-attested binding is NFR-SEC-43). The Control plane is the sole custodian ([`02-control-operator-api.md`](../components/02-control-operator-api.md) Owned state); the guest holds no handle. An informational, non-authoritative push, if ever wanted, is a new decision plus an accept-time invariant that it can never feed the auth predicate — tracked at [#286](https://github.com/Wide-Moat/open-computer-use/issues/286).
- **Runtime (re)delivery of the control-WS verify-key is deferred for v1, with its threat stated.** The key is the public Ed25519 control-WS client-auth verify-key the guest uses to authenticate the host-dialled caller ([`02-control-operator-api.md`](../components/02-control-operator-api.md)), distinct from the Session-JWT signing key. This ADR rules that v1 installs it once at session bring-up over the host-only provisioning push and does not re-deliver it over this endpoint; the bring-up install carries no prior key to authorise against, so its sole authority is the NFR-SEC-76 host-accept on the provisioning channel. Delivering it over this endpoint at runtime risks substitution (a caller installs a key it controls, then authenticates as host) and downgrade/rollback (replaying an older key). If added later, the write authorises against the current key plus NFR-SEC-76, carries a monotonic epoch checked anti-rollback, and may never widen who counts as host. Deferral is bounded by guest ephemerality — the executor is per-session ([`05-session-sandbox.md`](../components/05-session-sandbox.md)), so the key need not rotate within a session and a key change applies at the next session's bring-up. No current NFR anchors this key's rotation cadence (NFR-SEC-11 is Session-JWT signing, NFR-SEC-04 is the tenant DEK/KEK, NFR-SEC-26 sets none) — a flagged gap, tracked at [#287](https://github.com/Wide-Moat/open-computer-use/issues/287).
- **Clock-sync is deferred for v1.** A host-pushed wall-clock correction couples the endpoint to the trusted-time invariants ([`05-session-sandbox.md`](../components/05-session-sandbox.md) invariants 12/13, NFR-SEC-48/63). If added, it is host-push only, pinned to invariant 13 (resume-time correction before any time-bound check), and rejects any guest-influenced backward set — tracked at [#288](https://github.com/Wide-Moat/open-computer-use/issues/288).
- **Deferred and forbidden verbs are absent schema members, not open bodies.** The schema carries them as `x-ocu-tbd` entries with their disposition, threat, and tracking issue, so adding one is a coordinated additive bump and a silently-accepted unknown verb is impossible.
- Negative: a second listener is a second accept path to keep host-only, and a second negative-test family (guest-stack dial, forge-another-session, non-host-peer-at-accept) the executor must carry. The cost buys a host-initiated cooperative shutdown without granting the guest any authority the exec channel denies.

## Alternatives considered

- **Leave the port unspecified (status quo).** Rejected: the executor will not build an ungoverned guest listener, and an unspecified inbound surface inside the hostile guest is the exact gap the exec-channel hardening exists to close. ADR-0017 names the port but governs the deployable boundary, not the contract.
- **Loopback TCP control port.** Rejected: the guest shares the loopback network stack, so a TCP port is reachable from guest-originated code by default, contradicting invariant 3. The UDS with kernel peer-creds is the canon transport for the container tiers ([`05-session-sandbox.md`](../components/05-session-sandbox.md) Shelf delta) and gives a falsifiable accept-time identity check.
- **Fold the control verbs into the exec WebSocket union.** Rejected: the exec union is process-lifecycle, request/response-free streaming with binary stdio; a host-initiated lifecycle verb is a different shape, and merging them couples two independently-versioned contracts. The peer's exec parser already enforces a closed union — a control verb in it would be a forward-compat hole.
- **Carry the rulings as an amendment to ADR-0017.** Rejected: ADR-0017's subject is the repository/deployable boundary; the FID-03 rulings decide a wire contract and an authority model across components 02 and 05. Folding them in violates one-decision-per-file and mislabels ADR-0017's boundary claim as changed when it is not. This ADR amends ADR-0017 only to point at the contract for the port it named.

## Compliance impact

- `SOC2-CC6.1` / `NYDFS-500.15`: logical-access segregation. The endpoint adds no authority path a guest can use to escalate — the host-attested accept check is the sole authority, and the forbidden `container_name` update keeps the auth predicate in the Control plane's sole custody, auditable against the deployment's accept-time negative tests.

## License impact

None. The decision specifies an internal wire contract; it adds no dependency and changes no distribution term.

## Threat mitigation

Anchors the FID-03 endpoint to the P2-T2 control-plane row in [`06-threat-model.md`](../06-threat-model.md): the `shutdown`-evasion path fails closed on the host-driven finalizer (NFR-SEC-65) and the accept-time host-attested check (NFR-SEC-43/76). The forbidden `container_name` update closes the rename-poison path against the host-attested binding (NFR-SEC-43); the deferred verify-key delivery keeps the substitution/downgrade threat out of v1 code rather than leaving it silently open.

## Open questions

1. Whether the cooperative `shutdown` reply needs a bounded deadline before the host stops waiting and runs the finalizer, or whether the existing `terminationGracePeriodSeconds` window already bounds it — [#290](https://github.com/Wide-Moat/open-computer-use/issues/290).
