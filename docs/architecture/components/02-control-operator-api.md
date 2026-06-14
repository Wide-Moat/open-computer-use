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

The operator-facing lifecycle terminator: it owns session lifecycle, quota, the session denylist, and the kill-switch, reachable only on operator/lifecycle ingress and never from the agent-facing MCP surface. Audience: engineers wiring the operator plane or auditing the kill-switch path.

# Component-02: Control / operator API

## Purpose

Owns session lifecycle, quota, the session denylist, and the kill-switch ([`05-c4-container.md`](../05-c4-container.md) §3). It is the operator side of the Control plane split into two runnable units so the kill-switch is unreachable from the agent path by network policy rather than an in-process guard; it is the sole author of the session denylist that the Egress trust-edge reads and that the Control plane checks host-side on every Compute-plane control RPC (`F6`) ([`02-trust-boundaries.md`](../02-trust-boundaries.md) §7).

## Boundaries

Intra-container, this is one process with three internal components behind a single operator/lifecycle ingress that is a distinct deployable from the MCP gateway:

| Internal component | What it does |
|---|---|
| lifecycle controller | terminates session create/status/destroy (gateway service identity) and operator session ops; host-dials the Session sandbox to set up and tear down |
| denylist + kill-switch authority | terminates operator force-kill, denylist edits, and signed SOAR revoke; authors the denylist and signals a host-initiated stop |
| quota accountant | checks per-caller create-rate and per-tenant counters on create; refuses excess |

The operator/lifecycle ingress, the SOAR-revoke ingress, the gateway→Control session set-up edge, the Control→Session sandbox host-dial, and the Control→Audit fan-in are the boundaries `05-c4-container.md` §4 names (their `F2`/`F4`/`F5`/`F6`/`F10` flow labels are defined in [`05-c4-container.md`](../05-c4-container.md) §4); this spec adds only which internal component terminates each.

Owned state: the session registry (live sessions, their `container_name` binding, tenant, quota counters) and the denylist (kill-switch state), of which this container is sole custodian — no other component can mutate either, and the guest holds no handle that reaches them. On the storage path this container is the **provisioning / delivery vehicle for the backend storage credential, not its signer**: it relays a pre-signed, `filesystem_id`-scoped ES256 JWT into the mount config over the host-only control channel before the in-guest mount client starts, and scrubs the on-disk source after handoff ([ADR-0013](../adr/0013-storage-credential-custody.md)). The storage JWT is verified at the backend origin, not in the guest; the verify-key control verb this container sets is the Ed25519 key that authenticates control-WebSocket clients to the executor, a separate layer. The ES256 **signing key sits off-box at the credential issuer service**, never in this container and never in the per-session executor; this container holds no signing path and mints no storage bearer. It provably does not hold an upstream LLM credential (that credential reaches the Egress trust-edge over Envoy SDS, [ADR-0007](../adr/0007-egress-auth-mechanism.md)), holds no backend storage key, and holds no storage-mount bearer of its own after handoff.

Storage-credential custody at this container (one holder per credential, [ADR-0013](../adr/0013-storage-credential-custody.md)):

| Credential | This container | Provably does NOT hold |
|---|---|---|
| ES256 signing key (private) | does not hold — held off-box at the credential issuer | this container, the per-session executor, the guest mount client |
| Pre-signed scoped JWT (bearer) | relays it once into the mount config; retains no copy after handoff | — (the guest mount config holds it, root-readable, for its window; the backend origin verifies the scope claim) |
| Ed25519 control-WS client-auth key (public) | installs it into the guest over the host-only control channel so the executor can authenticate control-WebSocket clients | — (this is the control-channel auth layer, not a storage-JWT verify key; the storage JWT is verified at the backend) |

Token classes ([`02-trust-boundaries.md`](../02-trust-boundaries.md) §8 owns the taxonomy and TTLs): this container mints the Session JWT (per-session, bound to `container_name`) toward the Session sandbox on the host-dialled control channel, accepts a Generic internal token authenticating the inbound gateway service identity on session set-up, and accepts an operator credential on ingress (the operator-auth substrate is fixed by [ADR-0004](../adr/0004-operator-authentication-substrate.md)). The wire surface is unfrozen: the operator REST and SOAR-revoke surfaces (OpenAPI 3.1) and the gateway→Control session set-up RPC (Protobuf/gRPC) are OCU-`define` in [`08-contracts.md`](../08-contracts.md) §1, but their schema files are not yet built ([#205](https://github.com/Wide-Moat/open-computer-use/issues/205)), so `contract: null`. Two listeners back this container — operator/lifecycle ingress and gateway service-identity ingress; the kill-switch route exists only on the former. The customer-IdP assertion on ingress is relying-party, not an OCU-defined surface.

## Invariants

Each holds independent of the caller and is falsifiable by the named check. Cross-cutting properties (zone membership, in-transit encryption, retention floor, isolation tier) are Layer 3 and not restated.

- No MCP-surface route resolves to a lifecycle, denylist, or kill-switch route, and no rendered deploy manifest grants the gateway a network route to the operator ingress on either shelf (IaC-policy assertion, NFR-SEC-52).
- The kill-switch and revoke path holds its SLA while the control plane is saturated, including a flood on the operator/SOAR ingress itself; the lifecycle/revoke route carries reserved capacity or admission priority distinct from the create path (chaos test with an adversarial concurrent-load dimension, NFR-SEC-55, with the ≤30 s p99 value owned by NFR-SEC-01).
- A body-supplied session/tenant/`container_name` id is a hint, never the authority; the binding the host acts on (the host-dial, the registry write) is host-derived, so a gateway or guest naming another session's id cannot bind or address it (integration-test: forge-another-session attempt fails, NFR-SEC-43).
- The gateway service identity reaching this container carries no operator scope; force-kill, denylist edit, and quota override are unreachable with that audience (unit + integration-test on the audience-to-route map, NFR-SEC-26).
- Every privileged operator/SOAR action in the NFR-SEC-45 enumerated set emits a chain-linked OCSF event before acknowledgement, and the action is denied if the audit write fails (fail-closed); the enumerated set is the versioned fixture owned by NFR-SEC-45, with system-initiated lifecycle transitions owned by NFR-SEC-72 (per-release integration-test driving every action + a negative test asserting deny on audit-sink failure, NFR-SEC-45).
- Per-caller create-rate and per-tenant quota are enforced before a session is created; excess is refused, not queued, and agent-side create flooding cannot starve the operator/revoke route because the two ingresses are distinct (quota integration + connection-flood chaos test, NFR-COST-06, NFR-SEC-53).
- All TTL and revocation windows (Session JWT, denylist propagation) are computed against a monotonic clock immune to wall-clock setback; a setback ≥ a window neither extends a token nor defers a revoke (red-team clock-rollback harness, NFR-SEC-48).

## Failure modes

Each row traces to one P2 STRIDE row in [`06-threat-model.md`](../06-threat-model.md) §3 and repeats that row's controlling NFR; fail-closed is the default on the denylist, revoke, and audit-write boundaries. A1 is the in-sandbox guest; A2 is the external caller / gateway service identity; A3 is the operator/SOAR principal.

| Trace | Reaching actor | What goes wrong | Recovery behaviour | Controlling NFR |
|---|---|---|---|---|
| P2-E1 | A2, A1 | Agent-path principal probes for an operator or kill-switch route | No lifecycle/kill-switch route resolves; gateway→operator-ingress reachability is denied at deploy time and a missed route fails CI, not runtime | NFR-SEC-52 |
| P2-T2 | A1 | Guest stalls or drops the host-dialled control RPC to defeat the stop | The denylist is read host-side and the kill-switch is a host-initiated stop, not a cooperative guest action; an unreachable channel grants no new authority (fail-closed) | NFR-SEC-01 |
| P2-D1 | A2, A1 | Concurrent flood of session-create and operator/SOAR calls aims to starve revoke | The create path sheds at the per-caller/per-tenant quota and fails-closed; the revoke route holds reserved capacity so the kill-switch stays within SLA, with RTO/RPO the post-failure backstop | NFR-SEC-55, NFR-REL-01 |
| P2-R1 | A3, A2 | Operator force-kill / denylist edit / quota override leaves no independent record | The action is denied if its audit event fails to write; it does not take effect un-recorded | NFR-SEC-45 |
| P2-R2 | A2 | SOAR revoke disputed or replayed | The call is verified by signature against the SOAR principal before acting and emits an OCSF event bound to that principal; an unverifiable call is rejected | NFR-COMP-27, NFR-SEC-45 |
| P2-I1 | A2, A3 | Registry/quota enumeration across tenants | Audience-scoping returns only the caller's own sessions and host-attested binding blocks cross-session reads; the control plane carries no customer payload | NFR-IC-04 |

Residual, by [`06-threat-model.md`](../06-threat-model.md) §5 register: the stop-SLA accounting behind P2-T2 assumes a trustworthy host clock — trusted-time theme, [#185](https://github.com/Wide-Moat/open-computer-use/issues/185). Saturation/spill behaviour and a measurable containment target for P2-D1 fold into the resource-exhaustion theme, [#188](https://github.com/Wide-Moat/open-computer-use/issues/188). The mandatorily-audited action set behind P2-R1/P2-R2 is the privileged-operator-audit theme tracked at [#186](https://github.com/Wide-Moat/open-computer-use/issues/186). The no-customer-payload gate behind P2-I1 is not yet a measurable target, [#149](https://github.com/Wide-Moat/open-computer-use/issues/149).

The denylist this container authors also gates the Egress trust-edge: a revoked session is refused lease injection at the edge (the deny-signal half of [`02-trust-boundaries.md`](../02-trust-boundaries.md) §7). That enforcement behaviour lives in the Egress trust-edge spec; here the invariant is only sole authorship of the denylist the edge reads.

## Operational concerns

Config surface: the operator/lifecycle ingress listener and the gateway service-identity listener are distinct network endpoints (the NFR-SEC-52 separation); per-caller create-rate, per-tenant concurrent-session and calls/min ceilings (NFR-COST-06), and the reserved lifecycle/revoke capacity (NFR-SEC-55) are the principal knobs. Observability: this container emits OCSF on the audit fan-in for session create/destroy, every enumerated privileged action (NFR-SEC-45), and quota rejections, into the hash-chained pipeline ([`audit/audit-fanin`](../../../contracts/audit/audit-fanin.asyncapi.yaml), NFR-SEC-03); the audit-write is on the critical path of a privileged action (fail-closed), not a side-channel. Scaling axis and deployable boundary: this is a **one-per-deployment** deployable, distinct from the **per-session `[1..N]` executor** it drives; the two are separate runnable units reached over a host-dials-guest control channel (the WebSocket process channel and the host-only HTTP/vsock control port), not one in-process unit ([`05-c4-container.md`](../05-c4-container.md) §4, [ADR-0017](../adr/0017-control-plane-repo-boundary.md)). The split already exists at the code seam — the executor depends on a runtime interface plus a sentinel, not the concrete runtime, and only a composition root wires both — so canon records the boundary; it does not create it. This container is its own repository, `ocu-control`, while the executor narrows to `ocu-sandbox` (container 05); the off-box credential issuer is a separate deployable again and folds into neither ([ADR-0017](../adr/0017-control-plane-repo-boundary.md)). A co-housed single binary stays a valid operator packaging of the same two deployables, so the boundary is a source-and-blast-radius statement, not a forced runtime topology. The single-instance minimal shelf is in scope for the kill-switch-under-saturation target (NFR-SEC-55), so the capacity model reserves admission priority for the revoke route rather than scaling out, and RTO/RPO of this plane is NFR-REL-01. Upgrade/rotation: the RPC surface (session create/destroy/exec/fs) is versioned — a breaking change requires a major version plus deprecation header, CI-enforced by `buf breaking` / `oasdiff` (NFR-IC-04, [`08-contracts.md`](../08-contracts.md) §4); Session JWT rotation is mint-fresh-before-expiry, not extension, on the JWT TTL window in [`02-trust-boundaries.md`](../02-trust-boundaries.md) §8.

Shelf delta ([`05-c4-container.md`](../05-c4-container.md) §5): the minimal shelf co-locates this container with a host-rooted local operator credential and a host-local Session-JWT signing key; the full shelf schedules it with a customer-IdP-asserted operator identity (NFR-COMP-29) and a customer-PKI-rooted signer. The invariants above are boundary properties and hold on both shelves; only the operator-auth substrate and the JWT signer change, never the gateway↛operator separation, the host-attested binding, or the fail-closed audit-write. Retention of the audit events this container emits is the platform floor owned by the Audit pipeline (NFR-COMP-01). The operator-auth substrate is fixed by [ADR-0004](../adr/0004-operator-authentication-substrate.md).

## Open questions

1. Minimum scope of the gateway's internal token on the session set-up edge, and per-tool/per-action authorization on operator actions — [#187](https://github.com/Wide-Moat/open-computer-use/issues/187).
2. Measurable no-customer-payload gate on the control plane — [#149](https://github.com/Wide-Moat/open-computer-use/issues/149).
3. Saturation/spill behaviour and a measurable containment target for the create and operator/SOAR ingress under sustained adversarial load — [#188](https://github.com/Wide-Moat/open-computer-use/issues/188).
4. Trusted-time floor for Session-JWT TTL and denylist-propagation windows — [#185](https://github.com/Wide-Moat/open-computer-use/issues/185).
5. Operator-auth substrate (PAM-JIT integration, full vs minimal shelf) is fixed by [ADR-0004](../adr/0004-operator-authentication-substrate.md); the multi-party-approval residual is tracked at [#225](https://github.com/Wide-Moat/open-computer-use/issues/225).
