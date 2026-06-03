<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: draft
last-reviewed: 2026-06-03
owner: "@Wide-Moat/architects"
applies-to: next/v1
compliance: []
threat-model: 06-threat-model.md
contract: contracts/mcp/2025-06-18/ocu-constraints.schema.json
adr: []
---

The agent-facing inbound terminator: it authenticates the MCP caller, validates the tool-call, and hands a session request to the Control/operator API. Audience: engineers and security reviewers implementing or auditing the inbound MCP edge.

# Component-01: MCP gateway

## Purpose

Terminates inbound MCP tool-calls and authenticates the caller, then forwards a metadata-only session request to the Control/operator API ([`05-c4-container.md`](../05-c4-container.md) §3). It is a Conformist to the public MCP revision and runs no agent loop, so the calling client owns the loop and the model; the gateway holds no caller token past the request, no upstream credential, and no lifecycle or kill-switch route.

## Boundaries

Intra-container, the gateway is one process with three internal stages on each request:

| Internal stage | What it does |
|---|---|
| transport listener | terminates the MCP connection and validates the bearer audience |
| schema validation | applies the MCP base schema, then the OCU constraint profile |
| forwarding | issues a service-identity request to the Control/operator API |

The inbound caller edge, the gateway→Control/operator API edge, and the gateway→Audit pipeline fan-in are the boundaries `05-c4-container.md` §4 names (their `F1`/`F5`/`F11` flow labels are defined in [`06-threat-model.md`](../06-threat-model.md) §1); this spec adds only which internal stage terminates each.

Owned state: none that outlives a request. The gateway holds the in-flight request, the negotiated protocol revision for the connection, and its own service-identity signing material; it persists no session registry (that is the Control/operator API), no caller token after the response, and no customer payload. It provably does NOT hold an upstream credential, a Custody credential lease, a Storage-mount handle, the session denylist, or any route that resolves to a lifecycle or kill-switch operation — the operator surface sits in a separate container reachable only on operator-only ingress ([`02-trust-boundaries.md`](../02-trust-boundaries.md) §8).

Token classes ([`02-trust-boundaries.md`](../02-trust-boundaries.md) §8 owns the taxonomy): the gateway validates the inbound external bearer as a relying party, presents a Generic internal token on the forward to the Control/operator API, and mints or holds neither a Session JWT nor a Custody credential lease. The wire contract is the OCU constraint profile over MCP revision 2025-06-18 ([`ocu-constraints.schema.json`](../../../contracts/mcp/2025-06-18/ocu-constraints.schema.json)); it is a conform-not-define overlay, so field types, the error envelope, and the numeric caps live in the schema. The schema does not encode three facts: the gateway terminates the MCP socket and applies the base schema before the profile; the bearer is carried on the transport, never in the JSON-RPC body or URI query; and the caller token is never forwarded onto the Control/operator API leg or into the sandbox.

## Invariants

Each holds independent of the caller and is falsifiable by the named check.

- Every inbound tool-call is validated against the MCP base schema then the OCU profile before any forward, and an unknown field or out-of-bound payload is rejected pre-buffer with a structured deny, never partially acted on (schema-validation + property-test, NFR-SEC-51, NFR-SEC-46).
- The bearer must name this MCP server in its audience claim or the request is refused with the relying-party challenge; identity is never read from the request body (schema-validation + unit-test, NFR-SEC-09).
- The caller bearer never appears on the forward leg, in a forwarded argument, or in any path reaching the sandbox; the forward carries only the gateway's own service identity (code-path audit + integration-test, NFR-SEC-09, NFR-SEC-26).
- No gateway code path resolves to a lifecycle, denylist, or kill-switch route, and no rendered deploy manifest grants the gateway a network route to the operator ingress on either shelf (IaC-policy assertion, NFR-SEC-52).
- Outbound errors and discovery responses are size-bounded and carry a stable reason class plus a correlation id only — never a session id, `container_name`, internal host/route, or stack detail (schema-validation + property-test, NFR-SEC-51).
- The negotiated protocol revision is pinned per connection; a request whose `MCP-Protocol-Version` is missing or unnegotiable is rejected rather than silently downgraded (schema-validation + unit-test, NFR-IC-04).
- Tool execution is serialized per session by default; parallelism is opt-in per skill (integration-test, NFR-IC-05).
- The gateway holds at most a configured number of open connections per audience-validated caller; excess is refused, not queued, and a single caller cannot consume more than its configured share of the listener fd table (chaos-test, NFR-SEC-53).

## Failure modes

Each row traces to one P1 STRIDE row in [`06-threat-model.md`](../06-threat-model.md) §3.2 and repeats that row's controlling NFR; fail-closed is the default on every authentication and forward boundary. A1 is the in-sandbox guest; A2 is the external caller (the reaching actor on the gateway's P1 element).

| Trace | Reaching actor | What goes wrong | Recovery behaviour | Controlling NFR |
|---|---|---|---|---|
| P1-S1 | A2 | Replayed, forged, or wrong-audience bearer presented to open or address sessions | Validate as relying party; refuse with the resource-metadata challenge | NFR-SEC-09 |
| P1-S2 | A2 | Gateway service identity escalated on the forward so the Control/operator API treats the request as more privileged | The forward carries the gateway service principal only, which holds no operator scopes | NFR-SEC-26 |
| P1-T1 | A2 | On-path rewrite of tool-call parameters in flight | Validate audience and schema before acting; downstream authority is the host-derived identity, not the body | NFR-SEC-33 |
| P1-T2 | A2 | Forwarded body claims another tenant's `session_id`/`container_name` to bind or read a session it does not own | The body id is a hint cross-checked host-side; the Control/operator API derives the binding, so a forged id grants no reach | NFR-SEC-43 |
| P1-R1 | A2 | Caller denies issuing a tool-call/session-create; no independent record attributes the action | Emit an OCSF event on fan-in per terminated request with the validated caller identity | NFR-SEC-03 |
| P1-I1 | A2 | Verbose MCP errors or discovery leak session ids, `container_name`, tenant ids, or the operator surface | Emit a stable reason class + correlation id only, size-bounded; discovery exposes only the declared tool surface | NFR-SEC-51 |
| P1-D1 | A2 | Flood of the MCP surface exhausts gateway connections/CPU and pressures the lifecycle plane via the forward | Per-caller connection/fd ceiling refuses excess; the separate runnable unit means saturation cannot reach operator ingress or the kill-switch | NFR-COST-06, NFR-SEC-01, NFR-SEC-53 |
| P1-E2 | A2 | Caller invokes a tool or action beyond its authorization; the gateway authenticates but does not yet decide per-action authz | Audience-validated authN bounds who reaches the surface; host-attested identity blocks cross-session addressing downstream; per-action authz is the residual | NFR-SEC-49 |

Residual, by [`06-threat-model.md`](../06-threat-model.md) §5 register: per-action authorization (P1-E2) is specified by NFR-SEC-49 but not yet enforced at the gateway — tracked at [#187](https://github.com/Wide-Moat/open-computer-use/issues/187). The identifier-minimization measurement behind P1-I1/P1-R1 is tracked at [#149](https://github.com/Wide-Moat/open-computer-use/issues/149). The gateway↛operator network separation that bounds P1-S2 and P1-D1 is verified by the NFR-SEC-52 IaC-policy assertion; the gateway is the agent-path side of the two-container split whose escalation row (P2-E1) is owned with the Control/operator API.

## Operational concerns

Config surface: the inbound listener bind and transport, the bearer relying-party metadata (issuer, audience, resource-metadata URL), the pinned MCP revision, the per-caller connection/fd ceiling and per-tenant calls-min quota (NFR-COST-06, NFR-SEC-53), and the gateway's own caps on error/result/argument size — each an enforced default the operator may retune within the NFR-SEC-46/51 floor. Observability: the gateway emits OCSF on the fan-in flow for every terminated request with the validated caller identity, and an OCSF rejection event on a connection-ceiling refusal ([`audit/audit-fanin`](../../../contracts/audit/audit-fanin.asyncapi.yaml), NFR-SEC-03). Scaling axis: single instance per deployment (not per session); capacity is bounded by the per-caller ceiling and the MCP request success-rate target (NFR-PERF-01). Upgrade/rotation: the gateway carries no semver — its revision is the date string negotiated on `initialize`, and a peer that cannot negotiate the revision is the breaking signal rather than an HTTP deprecation header (NFR-IC-04); the service-identity signing key rotates on the inter-component identity cadence ([`02-trust-boundaries.md`](../02-trust-boundaries.md) §8).

Shelf delta ([`05-c4-container.md`](../05-c4-container.md) §5): the minimal shelf runs the gateway as a single co-located process whose service identity is a host-local signing key and whose caller authN is a host-rooted local credential; the full shelf schedules a single instance whose service identity is a customer-PKI workload identity and whose caller authN is the customer-IdP-asserted relying-party flow (NFR-COMP-29). The invariants above are boundary properties and hold on both shelves; only the identity substrate and listener scheduling change.

## Open questions

1. Does NFR-IC-04 bind only the Control/operator API and internal RPC, leaving the MCP edge governed solely by date-revision negotiation, or does it need an explicit MCP-edge clause? — [#207](https://github.com/Wide-Moat/open-computer-use/issues/207).
2. Per-action / per-tool authorization at the gateway (deny-by-default keyed on caller, tool name, action parameters) — [#187](https://github.com/Wide-Moat/open-computer-use/issues/187).
3. Outbound error/discovery identifier-minimization and size-bound enforcement at the gateway decoder — [#149](https://github.com/Wide-Moat/open-computer-use/issues/149).
4. Whether the per-session sequential-execution serializer (the NFR-IC-05 carrier, today a gateway behaviour with no wire field) needs its own versioned conformance fixture so opt-in parallelism is testable independently of the MCP profile ([#239](https://github.com/Wide-Moat/open-computer-use/issues/239)).
