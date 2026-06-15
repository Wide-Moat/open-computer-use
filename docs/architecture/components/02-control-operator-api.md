<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: draft
last-reviewed: 2026-06-14
owner: "@Wide-Moat/architects"
applies-to: next/v1
compliance: []
threat-model: 06-threat-model.md
contract: null
adr: [0004, 0013, 0017]
---

The only door to create or manage a session. Audience: engineers wiring the operator plane or auditing the kill-switch path.

# Component-02: Control / operator API

## Purpose

Every request to create or manage a session enters through the Control / operator API. It owns session lifecycle, quota, the session denylist, and the kill-switch ([`05-c4-container.md`](../05-c4-container.md) §3). It mints the weak session JWT and delivers it to the guest; it holds the Storage-JWT signing key and publishes a JWKS the Egress trust-edge validates against. It dials into the guest; the guest never dials it.

## Boundaries

Inbound edges:

- **MCP gateway → Control** (session set-up). The gateway carries a service identity, not operator scope.
- **Operator console / CLI → Control.** A human never calls the API directly; the console or CLI is the door.

Control mints the weak Storage-JWT itself and holds its signing key, so there is no inbound storage-credential edge here; the real filestore credential the Egress trust-edge exchanges for lives at the #3 counterparty, off Control's request path.

Outbound edges:

- **Control → Session sandbox.** The host dials the guest to create, drive, and tear down a session, and to deliver the storage JWT. The guest never dials Control.
- **Control → Audit pipeline** (host-side fan-in).

There is no edge from the MCP gateway to the sandbox; every request to create or manage a session enters through Control. Control has no edge to the storage path.

Two listeners back this container: an operator/lifecycle ingress and a gateway service-identity ingress, on distinct network endpoints. The kill-switch and force-kill routes exist only on the operator ingress. There is no storage-issuer listener: Control mints the weak Storage-JWT itself and holds its signing key as a config/secret mount, so no storage credential arrives on a network endpoint.

Owned state: the session registry (live sessions, their `container_name` binding, tenant, quota counters) and the denylist (kill-switch state). This container is the sole custodian of both. No other component mutates either, and the guest holds no handle that reaches them.

Control mints and delivers the weak session JWT; relay and scope custody are in the table below ([ADR-0013](../adr/0013-storage-credential-custody.md)). Scrub-on-load is a requirement of the in-guest mount client ([`05-session-sandbox.md`](05-session-sandbox.md)), not Control behaviour. The upstream LLM credential never reaches Control; it reaches the Egress trust-edge over Envoy SDS ([ADR-0007](../adr/0007-egress-auth-mechanism.md)).

Custody of each credential ([ADR-0013](../adr/0013-storage-credential-custody.md)):

| Credential | Control holds | Held elsewhere |
|---|---|---|
| Storage-JWT signing key (private) | yes — the Control plane holds it, mints the weak session JWT at provisioning, and publishes a JWKS the Egress trust-edge validates against | no guest, edge, or object-store component holds it |
| Weak session JWT (bearer) | relays once into the mount config; keeps no copy | the guest mount config, for its window; presented to the Egress trust-edge, which validates and exchanges it — it does not reach the storage engine ([ADR-0019](../adr/0019-egress-exchanges-filestore-credential.md)) |
| Ed25519 control-WS client-auth key (public) | installs into the guest over the control channel | the guest executor uses it to authenticate the host-dialled control-WebSocket client (host dials in; guest verifies the caller) |

Token classes ([`02-trust-boundaries.md`](../02-trust-boundaries.md) §8 owns the taxonomy and TTLs): Control mints the Session JWT toward the Session sandbox on the host-dialled control channel; the JWT proves session identity and is checked against a separately-supplied expected container name on the same channel, not as a JWT claim (NFR-SEC-43); accepts a Generic internal token from the gateway service identity on session set-up; and accepts an operator credential on the operator ingress ([ADR-0004](../adr/0004-operator-authentication-substrate.md) fixes the substrate). The operator REST and SOAR-revoke surfaces (OpenAPI 3.1) and the gateway→Control session set-up RPC (Protobuf/gRPC) are OCU-`define` in [`08-contracts.md`](../08-contracts.md) §1; their schema files are not yet built ([#205](https://github.com/Wide-Moat/open-computer-use/issues/205)), so `contract: null`. The customer-IdP assertion on ingress is relying-party, not an OCU-defined surface.

## Invariants

Cross-cutting properties (zone membership, in-transit encryption, retention floor, isolation tier) are Layer 3 and not restated.

- Every route to create or manage a session enters through Control. No MCP-surface route resolves to a lifecycle, denylist, or kill-switch route, and no rendered deploy manifest grants the gateway a network route to the operator ingress (IaC-policy assertion, NFR-SEC-52).
- The host dials the guest. The kill-switch is a host-initiated stop, not a cooperative guest action; an unreachable control channel grants the guest no new authority (NFR-SEC-01).
- Control verifies no storage scope; the Egress trust-edge validates the guest's weak session JWT and exchanges it for the real filestore credential, and the storage engine enforces scope on that injected credential ([ADR-0019](../adr/0019-egress-exchanges-filestore-credential.md), [ADR-0013](../adr/0013-storage-credential-custody.md)).
- A body-supplied session/tenant/`container_name` id is a hint, never the authority. The binding the host acts on is host-derived from the runtime-attested caller identity (hypervisor context id / kernel peer creds / per-session socket path; [`02-trust-boundaries.md`](../02-trust-boundaries.md) host-attested invariant), not from request fields, so a gateway or guest naming another session's id cannot bind or address it (forge-another-session test, NFR-SEC-43).
- The gateway service identity carries no operator scope. Force-kill, denylist edit, and quota override are unreachable with that audience (audience-to-route map test, NFR-SEC-26).
- Every privileged operator/SOAR action in the NFR-SEC-45 set emits a chain-linked OCSF event before acknowledgement, and the action is denied if the audit write fails (NFR-SEC-45; system-initiated lifecycle transitions owned by NFR-SEC-72).
- Per-caller create-rate and per-tenant quota are enforced before a session is created; excess is refused, not queued. The create flood cannot starve the operator/revoke route, which sits on a distinct ingress (NFR-COST-06, NFR-SEC-53).
- The kill-switch and revoke path holds its ≤30 s p99 SLA while the control plane is saturated, including a flood on the operator ingress; the route carries reserved capacity distinct from the create path (NFR-SEC-55, SLA owned by NFR-SEC-01).
- TTL and revocation windows (Session JWT, denylist propagation) run against a monotonic clock; a wall-clock setback neither extends a token nor defers a revoke (clock-rollback harness, NFR-SEC-48).

## Failure modes

Each row traces to one P2 STRIDE row in [`06-threat-model.md`](../06-threat-model.md) §3 and names that row's controlling NFR set. A1 is the in-sandbox guest; A2 is the external caller / gateway service identity; A3 is the operator/SOAR principal.

| Trace | Reaching actor | What goes wrong | Recovery behaviour | Controlling NFR |
|---|---|---|---|---|
| P2-E1 | A2, A1 | Agent-path principal probes for an operator or kill-switch route | No lifecycle/kill-switch route resolves; gateway→operator-ingress reachability is denied at deploy time and a missed route fails CI, not runtime | NFR-SEC-52, NFR-SEC-01 |
| P2-T2 | A1 | Guest stalls or drops the host-dialled control RPC to defeat the stop | The denylist is read host-side and the kill-switch is a host-initiated stop, not a cooperative guest action; an unreachable channel grants no new authority (fail-closed) | NFR-SEC-01 |
| P2-D1 | A2, A1 | Concurrent flood of session-create and operator/SOAR calls aims to starve revoke | The create path sheds at the per-caller/per-tenant quota and fails-closed; the revoke route holds reserved capacity so the kill-switch stays within SLA, with RTO/RPO the post-failure backstop | NFR-SEC-55, NFR-REL-01 |
| P2-R1 | A3, A2 | Operator force-kill / denylist edit / quota override leaves no independent record | The action is denied if its audit event fails to write; it does not take effect un-recorded | NFR-SEC-45 |
| P2-R2 | A2 | SOAR revoke disputed or replayed | The call is verified by signature against the SOAR principal before acting and emits an OCSF event bound to that principal; an unverifiable call is rejected | NFR-SEC-01 |
| P2-I1 | A2, A3 | Registry/quota enumeration across tenants | Audience-scoping returns only the caller's own sessions and host-attested binding blocks cross-session reads; the control plane carries no customer payload | NFR-IC-04 |

Residual, by [`06-threat-model.md`](../06-threat-model.md) §5 register: the stop-SLA accounting behind P2-T2 assumes a trustworthy host clock — trusted-time theme, [#185](https://github.com/Wide-Moat/open-computer-use/issues/185). Saturation/spill behaviour and a measurable containment target for P2-D1 fold into the resource-exhaustion theme, [#188](https://github.com/Wide-Moat/open-computer-use/issues/188). The mandatorily-audited action set behind P2-R1/P2-R2 is the privileged-operator-audit theme tracked at [#186](https://github.com/Wide-Moat/open-computer-use/issues/186). The no-customer-payload gate behind P2-I1 is not yet a measurable target, [#149](https://github.com/Wide-Moat/open-computer-use/issues/149).

Control authors the denylist; the Egress trust-edge reads it and refuses a revoked session. That enforcement lives in the [Egress trust-edge spec](06-egress-trust-edge.md).

## Operational concerns

Config surface: the operator/lifecycle ingress listener and the gateway service-identity listener are distinct network endpoints (the NFR-SEC-52 separation). Per-caller create-rate, per-tenant concurrent-session and calls/min ceilings (NFR-COST-06), and the reserved lifecycle/revoke capacity (NFR-SEC-55) are the principal knobs.

Observability: this container emits OCSF on the audit fan-in for session create/destroy, every enumerated privileged action (NFR-SEC-45), and quota rejections, into the hash-chained pipeline ([`audit/audit-fanin`](../../../contracts/audit/audit-fanin.asyncapi.yaml), NFR-SEC-03). The audit-write is on the critical path of a privileged action (fail-closed), not a side-channel.

Scaling axis: this is a one-per-deployment deployable, distinct from the per-session `[1..N]` executor it drives over the host-dials-guest control channel; the two are separate repositories, `ocu-control` and `ocu-sandbox` ([ADR-0017](../adr/0017-control-plane-repo-boundary.md)). The single-instance minimal shelf is in scope for the kill-switch-under-saturation target (NFR-SEC-55), so the capacity model reserves admission priority for the revoke route rather than scaling out. RTO/RPO of this plane is NFR-REL-01.

Upgrade/rotation: the RPC surface (session create/destroy/exec/fs) is versioned — a breaking change requires a major version plus deprecation header, CI-enforced by `buf breaking` / `oasdiff` (NFR-IC-04, [`08-contracts.md`](../08-contracts.md) §4). Session JWT rotation is mint-fresh-before-expiry, not extension, on the JWT TTL window in [`02-trust-boundaries.md`](../02-trust-boundaries.md) §8.

Shelf delta ([`05-c4-container.md`](../05-c4-container.md) §5): the minimal shelf co-locates this container with a host-rooted local operator credential and a host-local Session-JWT signing key; the full shelf schedules it with a customer-IdP-asserted operator identity (NFR-COMP-29) and a customer-PKI-rooted signer. The operator-auth substrate and the JWT signer change between shelves; the invariants above hold on both. Retention of the audit events this container emits is the platform floor owned by the Audit pipeline (NFR-COMP-01).

## Open questions

1. Minimum scope of the gateway's internal token on the session set-up edge, and per-tool/per-action authorization on operator actions — [#187](https://github.com/Wide-Moat/open-computer-use/issues/187).
2. Measurable no-customer-payload gate on the control plane — [#149](https://github.com/Wide-Moat/open-computer-use/issues/149).
3. Saturation/spill behaviour and a measurable containment target for the create and operator/SOAR ingress under sustained adversarial load — [#188](https://github.com/Wide-Moat/open-computer-use/issues/188).
4. Trusted-time floor for Session-JWT TTL and denylist-propagation windows — [#185](https://github.com/Wide-Moat/open-computer-use/issues/185).
5. Operator-auth substrate (PAM-JIT integration, full vs minimal shelf) is fixed by [ADR-0004](../adr/0004-operator-authentication-substrate.md); the multi-party-approval residual is tracked at [#225](https://github.com/Wide-Moat/open-computer-use/issues/225).
