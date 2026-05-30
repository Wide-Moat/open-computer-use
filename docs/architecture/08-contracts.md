<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: draft
last-reviewed: 2026-05-31
owner: "@Wide-Moat/architects"
applies-to: next/v1
---

Names every boundary that carries a wire contract, the format each uses, and whether OCU defines or conforms to it. Audience: engineers about to author a schema file or a component spec.

## 1. Contract surfaces

A contract at this layer is the typed, versioned shape that crosses a boundary — the methods, payloads, errors, and auth a caller may rely on. This overview owns the inventory, the format choice, and the policy; the per-surface schema files (§5) own the field-level types. Surfaces are the [internal boundaries](05-c4-container.md) (Layer 6 §4) plus the [external actors](03-c4-context.md) (Layer 4 §4); their token classes and zones live in those layers and are not restated here. [`diagrams/08-contracts.mmd`](diagrams/08-contracts.mmd) overlays the format on each crossing of the container diagram; the table below is the full surface list.

OCU does not define every contract it speaks. Five external surfaces are integration contracts the platform consumes — naming a bespoke OCU format for them would contradict the [context map](04-bounded-contexts.md) (Layer 5 §4): MCP authorization (Conformist), SAML/OIDC (relying-party), PKCS#11/KMIP (relying-party), chained-proxy, and ICAP. The overview presents these as conform/relying-party, citing the public spec, not an OCU schema.

| Surface | Boundary (canonical name) | Format | Role | NFR anchor |
|---|---|---|---|---|
| Agent tool-call ingress | Caller → MCP gateway | MCP JSON-Schema | conform | NFR-FLEX-14, NFR-IC-04 |
| Operator REST | Operator → Control / operator API | OpenAPI 3.1 | define | — |
| IdP assertion | Customer IdP → Control / operator API | SAML/OIDC | relying-party | NFR-COMP-29 |
| SOAR revoke (inbound) | SOAR → Control / operator API | OpenAPI 3.1 | define | NFR-SEC-01 |
| Session RPC | MCP gateway → Control / operator API | Protobuf/gRPC | define | NFR-IC-04 |
| Exec / PTY+CDP | Control / operator API → Session sandbox | Protobuf/gRPC | define | NFR-IC-03, NFR-SEC-43 |
| File-operation mount | Storage broker → Session sandbox | Protobuf/gRPC | define | NFR-SEC-25 |
| Lease pull | Credential custody → Egress trust-edge | Protobuf/gRPC | define | NFR-SEC-29 |
| Outbound | Session sandbox → Egress trust-edge | network policy (no wire schema) | network property | NFR-SEC-27 |
| Broker backend leg | Storage broker → Egress trust-edge → backend | external backend protocol | conform | NFR-SEC-16 |
| Audit fan-in / SIEM | six containers → Audit pipeline → SIEM | AsyncAPI 3.0 / OCSF | publish | NFR-SEC-03 |
| SOAR webhook (outbound) | Audit pipeline → SOAR | AsyncAPI 3.0 | define | NFR-SEC-45 |
| Transparency-log submission | Audit pipeline → log | submission envelope | define (envelope only) | NFR-SEC-03 |
| KMS / proxy / DLP | Egress trust-edge ↔ customer substrate | PKCS#11 · chained-proxy · ICAP | relying-party / conform | NFR-FLEX-04, NFR-COMP-28, NFR-FLEX-15 |

The broker backend leg and the transparency log are mixed-ownership: OCU defines its half and conforms to the backend's API or the log operator's Merkle-head signing.

## 2. Format choice

Four formats cover every surface OCU defines; the choice follows the boundary shape, not preference.

- **MCP JSON-Schema (over JSON-RPC 2.0)** — the agent tool surface. The protocol fixes the format; OCU does not choose it. Tool definitions carry JSON Schema; the 2025-06-18 revision does not pin a dialect version, so the validator reads `$schema` per tool ([MCP spec 2025-06-18](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)).
- **OpenAPI 3.1** — inbound human/operator and third-party REST (operator API, SOAR revoke). SDK-generatable; its schemas are JSON Schema 2020-12 ([3.1 alignment](https://learn.openapis.org/upgrading/v3.0-to-v3.1.html)). OCU normalizes inbound validation to one dialect rather than relying on the MCP revision to fix it.
- **Protobuf/gRPC** — internal RPC between OCU containers, where both ends version together. Field-number rules plus `buf breaking` give machine-checked compatibility with no public-SDK obligation. Internal-only by policy.
- **AsyncAPI 3.0** — one-directional decoupled event fan-in to the Audit pipeline and fan-out to SIEM. Payload is the OCSF Published Language; AsyncAPI names the channel, OCSF types the event ([AsyncAPI 3.0](https://www.asyncapi.com/docs/concepts/asyncapi-document/define-payload)).

## 3. Contract-enforced mitigations

Every OCU-defined contract carries the Layer 7 mitigations as machine-checked constraints. The overview states the property and where it is enforced; the schema states the constraint values. Threats are anchored in [the threat model](06-threat-model.md) (Layer 7) and not restated.

| Mitigation | Property the contract must carry | NFR |
|---|---|---|
| Audience-validated authz | reject any token not naming this surface in its audience ([trust-boundaries §3](02-trust-boundaries.md)); no token passthrough to upstream — the edge injects custody credentials (NFR-SEC-23, NFR-SEC-27) | NFR-SEC-09 |
| Bounded error verbosity | caller gets a stable reason code; `error.message`/`error.data` leak no internal topology or stack | NFR-SEC-51 |
| Structured deny | deny is a machine-parseable object using the `x-deny-reason` vocabulary | NFR-SEC-17 |
| Schema validation | every payload validates against the published schema; reject on violation | NFR-SEC-51 |
| Bounded payload | gateway/REST/gRPC bound body size, array length, and object depth at the closed schema; the broker and exec transport cap max-message/max-object | NFR-SEC-51, NFR-SEC-46 |

The MCP edge carries the same five through a two-tier error model: a protocol error (`JSON-RPC error{code,message}`) never reaches the model and carries a reason code only; a tool-execution error (`result.isError: true` + content) reaches the model with sanitized output. Both are bounded by NFR-SEC-51.

## 4. Versioning & compatibility

Contracts evolve additively. Adding an endpoint, an optional field, a new event type, or a proto field with a fresh field number is non-breaking and ships without a version bump; consumers ignore unknown fields. Removing or renaming a field, tightening a type, changing an error envelope, or repurposing a proto field number is breaking and requires a new **major** version that does not depend on the prior one; the two coexist for the published transition window. Deprecation precedes removal — ship the replacement, migrate clients, then remove. REST deprecation uses the `Deprecation` ([RFC 9745](https://www.rfc-editor.org/rfc/rfc9745.html)) and `Sunset` ([RFC 8594](https://www.rfc-editor.org/rfc/rfc8594.html)) response headers. Breaking-change detection is CI-enforced — `oasdiff` for OpenAPI, `buf breaking` for Protobuf.

The control-plane RPC rule (breaking = major version + deprecation header) is canonical in NFR-IC-04 and governs OCU's own Control/operator API and internal gRPC. The MCP gateway is a Conformist to the MCP wire contract and does not carry semver: its revision is a date string (`protocolVersion: "2025-06-18"`) negotiated on `initialize` and echoed on every HTTP request via `MCP-Protocol-Version`. A revision the peer cannot negotiate is the breaking signal: the server returns an alternate version it supports and a client that cannot accept it disconnects ([MCP lifecycle](https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle)); the spec's example initialization error is `-32602` "Unsupported protocol version". This negotiation path is the deprecation mechanism NFR-IC-04 describes for that edge, not an HTTP `Deprecation` header. Concurrency is sequential-default per session with opt-in parallelism (NFR-IC-05); PTY and CDP multiplex one WebSocket per session (NFR-IC-03).

## 5. Deferred artifacts

This overview is the map. Executable artifacts are one schema file per OCU-defined surface; each is a tbd stub here.

- One schema file per OCU-defined surface (`contracts/mcp/2025-06-18/`, `contracts/openapi/`, `contracts/proto/`, `contracts/asyncapi/`) — status: not built. Field-level types for Tool, CallToolResult, and content blocks follow MCP revision `2025-06-18` and are defined in the MCP schema file, not restated here. [#TBD]
- Mock / conformance servers per surface for consumer CI — status: not built. [#TBD]
- The `SkillProvider` contract is a v1 non-goal; skills load from a customer-provided registry, so no skill-format schema ships in v1. [#TBD]

## 6. Open questions

1. Does NFR-IC-04 bind only the Control/operator API and internal gRPC, leaving the MCP gateway governed solely by date-revision negotiation, or does it need an explicit MCP-edge clause? — [#TBD].
2. Is the inbound gateway contract MCP-only per NFR-FLEX-14, and is `REST fallback` (used in Layer 4 prose, undefined in glossary) dropped or promoted to a defined surface? — [#TBD].
3. Does the broker file-operation contract (open/read/write/list) stay distinct from any object-store API at every shelf, and where is that boundary asserted? — [#TBD].
4. The §4 additive-vs-breaking rules, transition window, RFC 9745/8594 headers, and the `oasdiff`/`buf breaking` CI gates extend NFR-IC-04 across two surfaces — should this versioning policy move to a dedicated ADR, leaving §4 a pointer? — [#TBD].
