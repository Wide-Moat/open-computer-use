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

The agent tool-call ingress: it authenticates the MCP caller, validates the tool-call, and routes a session request to the control plane. Audience: engineers and security reviewers implementing or auditing the inbound MCP edge.

# Component-01: MCP gateway

## Purpose

The MCP gateway is the agent tool-call ingress for MCP callers; it authenticates the caller, validates the tool-call against the OCU profile, and routes a session request to the Control/operator API ([`05-c4-container.md`](../05-c4-container.md) §3). It runs no agent loop — the calling client owns the loop and the model. It holds no session lifecycle, no kill-switch route, and never reaches the sandbox directly.

## Boundaries

The gateway has three edges:

| Edge | Direction | Defined in |
|---|---|---|
| MCP caller → gateway | inbound tool-call | [`05-c4-container.md`](../05-c4-container.md) §4 (`F1`) |
| gateway → Control/operator API | session request forward | [`05-c4-container.md`](../05-c4-container.md) §4 (`F5`) |
| gateway → Audit pipeline | OCSF fan-in | [`05-c4-container.md`](../05-c4-container.md) §4 (`F10`) |

There is no gateway→sandbox edge and no gateway→operator-ingress edge. Every request to create or manage a session enters through the control plane; the gateway routes the request there and goes no further.

Intra-container, the gateway is one process.

Owned state: none that outlives a request. The gateway holds the in-flight request, the connection's negotiated protocol revision, and its own service-identity signing material. It persists no session registry (the Control/operator API owns that), no caller token after the response, and no customer payload. It holds no upstream credential, no storage credential, no session denylist, and no route that resolves to a lifecycle or kill-switch operation — the operator surface sits in a separate container on operator-only ingress ([`02-trust-boundaries.md`](../02-trust-boundaries.md) §8).

Token classes ([`02-trust-boundaries.md`](../02-trust-boundaries.md) §8 owns the taxonomy): the gateway validates the inbound external bearer as a relying party and presents a Generic internal token on the forward to the Control/operator API. It mints and holds no Session JWT and no storage credential. The wire contract is the OCU constraint profile over MCP revision 2025-06-18 ([`ocu-constraints.schema.json`](../../../contracts/mcp/2025-06-18/ocu-constraints.schema.json)); it overlays rather than redefines, so field types, the error envelope, and the numeric caps live in the schema. The caller token rides the transport, never the JSON-RPC body or URI query, and is never forwarded onto the Control/operator API leg or into the sandbox.

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

Each row traces to one P1 STRIDE row in [`06-threat-model.md`](../06-threat-model.md) §3.2 and names that row's controlling NFR set; fail-closed is the default on every authentication and forward boundary. Every row in the table below is reached by A2, the external caller on the gateway's P1 element.

| Trace | Reaching actor | What goes wrong | Recovery behaviour | Controlling NFR |
|---|---|---|---|---|
| P1-S1 | A2 | Replayed, forged, or wrong-audience bearer presented to open or address sessions | Validate as relying party; refuse with the resource-metadata challenge | NFR-SEC-09 |
| P1-S2 | A2 | Gateway service identity escalated on the forward so the Control/operator API treats the request as more privileged | The forward carries the gateway service principal only, which holds no operator scopes | NFR-SEC-26 |
| P1-T1 | A2 | On-path rewrite of tool-call parameters in flight | Validate audience and schema before acting; downstream authority is the host-derived identity, not the body | NFR-SEC-33 |
| P1-T2 | A2 | Forwarded body claims another tenant's `session_id`/`container_name` to bind or read a session it does not own | The body id is a hint cross-checked host-side; the Control/operator API derives the binding, so a forged id grants no reach | NFR-SEC-43 |
| P1-R1 (E1 caller via F1) | A2 | Caller denies issuing a tool-call/session-create; no independent record attributes the action | Emit an OCSF event on fan-in per terminated request with the validated caller identity | NFR-SEC-03 |
| P1-I1 | A2 | Verbose MCP errors or discovery leak session ids, `container_name`, tenant ids, or the operator surface | Emit a stable reason class + correlation id only, size-bounded; discovery exposes only the declared tool surface | NFR-SEC-33, NFR-SEC-51 |
| P1-D1 | A2 | Flood of the MCP surface exhausts gateway connections/CPU and pressures the lifecycle plane via the forward | Per-caller connection/fd ceiling refuses excess; the separate runnable unit means saturation cannot reach operator ingress or the kill-switch | NFR-COST-06, NFR-SEC-01, NFR-SEC-53 |
| P1-E2 | A2 | Caller invokes a tool or action beyond its authorization; the gateway authenticates but does not yet decide per-action authz | Audience-validated authN bounds who reaches the surface; host-attested identity blocks cross-session addressing downstream; per-action authz is the residual | NFR-SEC-49 |

Residual: per-action authorization (P1-E2) is specified by NFR-SEC-49 but not yet enforced at the gateway — the gateway authenticates the caller without deciding per-action authz. P2-E1 is specified in the Control/operator API spec; this spec carries only the gateway-side property (no MCP-surface route to a lifecycle/kill-switch op).

## Operational concerns

Config surface: the inbound listener bind and transport, the bearer relying-party metadata (issuer, audience, resource-metadata URL), the pinned MCP revision, the per-caller connection/fd ceiling and per-tenant calls-min quota (NFR-COST-06, NFR-SEC-53), and the gateway's caps on error/result/argument size. Each is an enforced default the operator may retune within the NFR-SEC-46/51 floor.

Observability: the gateway emits OCSF on the fan-in flow for every terminated request with the validated caller identity, plus an OCSF rejection event on a connection-ceiling refusal ([`audit/audit-fanin`](../../../contracts/audit/audit-fanin.asyncapi.yaml), NFR-SEC-03).

Scaling axis: a single instance per deployment, not per session; capacity is bounded by the per-caller ceiling and the MCP request success-rate target (NFR-PERF-01).

Upgrade/rotation: the gateway carries no semver. Its revision is the date string negotiated on `initialize`, and a peer that cannot negotiate the revision is the breaking signal, not an HTTP deprecation header (NFR-IC-04). The service-identity signing key rotates on the inter-component identity cadence ([`02-trust-boundaries.md`](../02-trust-boundaries.md) §8).

Shelf delta ([`05-c4-container.md`](../05-c4-container.md) §5): the minimal shelf runs the gateway as a single co-located process whose service identity is a host-local signing key and whose caller authN is a host-rooted local credential; the full shelf schedules a single instance whose service identity is a customer-PKI workload identity and whose caller authN is the customer-IdP-asserted relying-party flow (NFR-COMP-29). The invariants above are boundary properties and hold on both shelves; only the identity substrate and listener scheduling change.

## Open questions

1. Does NFR-IC-04 bind only the Control/operator API and internal RPC, leaving the MCP edge governed solely by date-revision negotiation, or does it need an explicit MCP-edge clause? — [#207](https://github.com/Wide-Moat/open-computer-use/issues/207).
2. Per-action / per-tool authorization at the gateway (deny-by-default keyed on caller, tool name, action parameters) — [#187](https://github.com/Wide-Moat/open-computer-use/issues/187).
3. Outbound error/discovery identifier-minimization and size-bound enforcement at the gateway decoder — [#149](https://github.com/Wide-Moat/open-computer-use/issues/149).
4. Whether the per-session sequential-execution serializer (the NFR-IC-05 carrier, today a gateway behaviour with no wire field) needs its own versioned conformance fixture so opt-in parallelism is testable independently of the MCP profile ([#239](https://github.com/Wide-Moat/open-computer-use/issues/239)).
