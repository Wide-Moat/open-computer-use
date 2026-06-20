<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: draft
last-reviewed: 2026-06-20
owner: "@Wide-Moat/architects"
applies-to: next/v1
---

Names every boundary that carries a wire contract, the format each uses, and whether OCU defines or conforms to it. Audience: engineers about to author a schema file or a component spec.

## 1. Contract surfaces

A contract at this layer is the typed, versioned shape that crosses a boundary — the methods, payloads, errors, and auth a caller may rely on. This overview owns the inventory, the format choice, and the policy; the per-surface schema files (§5) own the field-level types. Surfaces are the [internal boundaries](05-c4-container.md) (Layer 6 §4) plus the [external actors](03-c4-context.md) (Layer 4 §4); their token classes and zones live in those layers and are not restated here. [`diagrams/08-contracts.mmd`](diagrams/08-contracts.mmd) overlays the format on each crossing of the container diagram; the table below is the full surface list.

OCU does not define every contract it speaks. Five external surfaces are integration contracts the platform consumes — naming a bespoke OCU format for them would contradict the [context map](04-bounded-contexts.md) (Layer 5 §4): MCP authorization (Conformist), OIDC (relying-party), PKCS#11/KMIP (relying-party), chained-proxy, and ICAP. The overview presents these as conform/relying-party, citing the public spec, not an OCU schema.

| Surface | Boundary (canonical name) | Format | Role | NFR anchor |
|---|---|---|---|---|
| Agent tool-call ingress | Caller → MCP gateway | MCP JSON-Schema | conform | NFR-FLEX-14, NFR-IC-04 |
| Operator REST | Operator → Control / operator API | OpenAPI 3.1 | define | — |
| IdP assertion | Customer IdP → Control / operator API | OIDC | relying-party | NFR-COMP-29 |
| SOAR revoke (inbound) | SOAR → Control / operator API | OpenAPI 3.1 | define | NFR-SEC-01 |
| Session set-up RPC | MCP gateway → Control / operator API | Protobuf/gRPC | define | NFR-IC-04 |
| Exec / PTY+CDP | Control / operator API → Session sandbox | WebSocket, single per session (tagged-JSON control + binary stream frames) | define | NFR-IC-03, NFR-SEC-43 |
| Control → guest control-RPC | Control / operator API → Session sandbox | newline-delimited JSON over a host-owned UDS (closed tagged-union; v1 verb set `shutdown` only) | define | NFR-SEC-43, NFR-SEC-76 |
| Mount provisioning push | Control / operator API → Session sandbox | HTTP+JSON mount config (`filesystem_id`, `service_url`, Control-minted weak session JWT, `ca_cert_pem`, mount set) pushed host-to-guest before the mount client starts | define | NFR-SEC-25 |
| Storage [data leg](glossary.md#data-leg) | Session sandbox → Object-store service (over the Egress trust-edge) | the in-guest mount client (object-store client + transport, one binary) dials `service_url` guest-out, static `Authorization: Bearer` (the weak Storage-JWT); the Egress trust-edge validates and exchanges it for the real filestore credential, which the storage engine verifies and on which it enforces scope | define | NFR-SEC-25, NFR-SEC-46, NFR-SEC-85 |
| File / artifact data plane | Data-plane client → [Web UI](components/08-web-ui.md) | OpenAPI 3.1 (HTTP+JSON: upload/list/download/downloadArchive/getManifest/preview-render/delete + embeddable SPA) | define | NFR-SEC-78, NFR-SEC-82, NFR-SEC-49, NFR-SEC-73 |
| Secret delivery | SDS source → Egress trust-edge | Envoy SDS (gRPC xDS) | wire off-the-shelf; the v1 inspection leaf is pre-minted out of band and served over Envoy-native file SDS (zero OCU minter on the data path), a dynamic per-SNI minter is specified for a non-enumerable destination set but unbuilt at GA ([ADR-0007](adr/0007-egress-auth-mechanism.md)) | NFR-SEC-29 |
| Outbound | Session sandbox → Egress trust-edge | network policy (no wire schema) | network property | NFR-SEC-27, NFR-SEC-85 |
| Audit fan-in / SIEM | five host-side source channels → Audit pipeline → SIEM | AsyncAPI 3.0 / OCSF | publish | NFR-SEC-03 |
| SOAR webhook (outbound) | Audit pipeline → SOAR | AsyncAPI 3.0 | define | NFR-COMP-27 |
| Transparency-log submission | Audit pipeline → log | submission envelope | define (envelope only) | NFR-SEC-03 |
| KMS / proxy / DLP | Egress trust-edge ↔ customer substrate | PKCS#11 · chained-proxy · ICAP | relying-party / conform | NFR-FLEX-04, NFR-COMP-28, NFR-FLEX-15 |

Protobuf/gRPC is the unary session set-up leg only (create, route, destroy a session). The mount config is HTTP+JSON and the exec stream is a WebSocket; the control-RPC differs from the exec WebSocket in shape — verb requests over a UDS, not a bidirectional byte stream. The file-op message-set substrate (REST-JSON over HTTP/2) is a component-spec choice, not part of the contract. Egress secret delivery rides Envoy's native Secret Discovery Service (gRPC xDS); it is off-the-shelf and not an OCU-defined contract.

The storage data leg and the transparency log are mixed-ownership: OCU defines its half and conforms to the storage engine's API or the log operator's Merkle-head signing.

Storage is reached over two surfaces. The mount surface is a host-to-guest provisioning push followed by a guest-out [data leg](glossary.md#data-leg): the Control / operator API mints the weak Storage-JWT (`auth_token`) and pushes the mount config — that token, the inspection-CA anchor (`ca_cert_pem`), `service_url`, and the mount set — over the host-only control channel before the mount client starts; the guest mount client holds the weak session JWT, then dials `service_url` outbound over the egress hop, presenting that JWT as a static `Authorization: Bearer`. The Egress trust-edge validates the weak session JWT against the Control plane's JWKS and exchanges it at the credential authority for the real filestore credential, overwriting the header before the request reaches the Object-store service; the Object-store service forwards that real credential to the storage engine, which enforces the `filesystem_id` scope on it ([ADR-0019](adr/0019-egress-exchanges-filestore-credential.md), [ADR-0013](adr/0013-storage-credential-custody.md), [ADR-0014](adr/0014-storage-transport-tier-universal-network-leg.md)). The Control plane holds the Storage-JWT signing key and publishes the JWKS the edge validates against; the credential authority that issues the real filestore credential over RFC 8693 exchange is a separate counterparty that may be external/customer-provided or bundled minimal. The [Web UI](components/08-web-ui.md) is the second surface: an external [Data-plane client](glossary.md#data-plane-client) reaches it, and it calls the Object-store service over the host leg ([ADR-0015](adr/0015-storage-decomposition-by-trust-plane.md)). Both surfaces reach storage only through the Object-store service; neither reaches the engine directly. Channel direction is per channel: the control/exec channel and the mount provisioning push are host-dialled — the host opens them and a non-host peer is rejected at accept (NFR-SEC-43); the storage data leg and the Web UI fetch run guest-out or client-in, intercepted at the edge under egress policy (NFR-SEC-27).

## 2. Format choice

Five formats cover every surface OCU defines; the choice follows the boundary shape, not preference.

- **MCP JSON-Schema (over JSON-RPC 2.0)** — the agent tool surface. The protocol fixes the format; OCU does not choose it. Tool definitions carry JSON Schema; an embedded schema defaults to JSON Schema 2020-12 and may declare another dialect with `$schema`, so the validator honours the declared dialect and falls back to 2020-12 ([MCP spec 2025-06-18](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)).
- **OpenAPI 3.1** — inbound human/operator and third-party REST (operator API, SOAR revoke) and the Web UI file/artifact data plane (upload/list/download/getManifest/preview-render), an HTTP+JSON surface served on a dedicated ingress. SDK-generatable; its schemas are JSON Schema 2020-12 ([3.1 alignment](https://learn.openapis.org/upgrading/v3.0-to-v3.1.html)), the same dialect MCP defaults to, so inbound validation reads one dialect across both surfaces.
- **Protobuf/gRPC** — unary internal RPC between OCU containers, where both ends version together: session set-up. Field-number rules plus `buf breaking` give machine-checked compatibility with no public-SDK obligation. Internal-only by policy. Egress secret delivery is Envoy SDS (gRPC xDS) between Envoy and the SDS source: the wire is off-the-shelf and not an OCU RPC surface, but the dynamic per-SNI minter that implements the SDS server for a non-enumerable allow-list is self-hosted OCU code ([ADR-0007](adr/0007-egress-auth-mechanism.md)); the file SDS source needs none.
- **WebSocket** — the bidirectional exec/PTY+CDP surface, one socket per session. A PTY carries interleaved stdin/stdout/stderr bytes plus in-band resize and signal control, so the frame is tagged-JSON control alongside raw binary stream frames, not a unary call (NFR-IC-03). gRPC fits request/response, not a live byte stream, which is why this surface is WebSocket and the set-up RPC is not.
- **AsyncAPI 3.0** — one-directional decoupled event fan-in to the Audit pipeline and fan-out to SIEM. Payload is the OCSF Published Language; AsyncAPI names the channel, OCSF types the event ([AsyncAPI 3.0](https://www.asyncapi.com/docs/concepts/asyncapi-document/define-payload)).

## 3. Contract-enforced mitigations

Every OCU-defined contract carries the Layer 7 mitigations as machine-checked constraints. The overview states the property and where it is enforced; the schema states the constraint values. Threats are anchored in [the threat model](06-threat-model.md) (Layer 7) and not restated.

| Mitigation | Property the contract must carry | NFR |
|---|---|---|
| Audience-validated authz | reject any token not naming this surface in its audience ([trust-boundaries §3](02-trust-boundaries.md)); no token passthrough to upstream — the edge injects the SDS-delivered credential (NFR-SEC-23, NFR-SEC-27) | NFR-SEC-09 |
| Bounded error verbosity | caller gets a stable reason code; `error.message`/`error.data` leak no internal topology or stack | NFR-SEC-51 |
| Structured deny | deny is a machine-parseable object using the `x-deny-reason` vocabulary | NFR-SEC-17 |
| Schema validation | every payload validates against the published schema; reject on violation | NFR-SEC-51 |
| Bounded payload | gateway/REST/gRPC bound body size, array length, and object depth at the closed schema; the file-op (REST-JSON over HTTP/2) and exec transport cap max-message/max-object | NFR-SEC-51, NFR-SEC-46 |
| Bounded Web UI inbound body | reject a body above the configured ceiling (default ≤50 MiB) pre-buffer, never partially staged; per-validated-caller op/byte rate limits on a dedicated file/UI ingress | NFR-SEC-78 |
| Archive validation | reject pre-extraction on uncompressed-total / entry-count / traversal / symlink ceilings | NFR-SEC-80 |
| Content classification | resolve content type on ingest (magic-byte + declared media type), record before mount-visibility; pre-stage deny on a policy-denied type | NFR-SEC-81 |
| Embed-token verify | reject any embed token not signature-valid, not naming this surface in audience, or past `exp` (`exp ≤ 120 s`); no OCU upstream secret crosses to the browser | NFR-SEC-82 |
| Frame-ancestors allowlist | every UI/artifact response carries `CSP: frame-ancestors` from the per-deployment allowlist (header-only, default `'none'`) | NFR-SEC-83 |
| First-party session + CSRF | a state-mutating request requires a server-validated CSRF token; a missing/invalid session is 401 with no anonymous fallback | NFR-SEC-84 |
| File-activity audit (Web UI) | every upload/list/download/delete emits an OCSF File System Activity event into the hash-chained pipeline under host-attested identity, fail-closed | NFR-SEC-79 |
| Three-axis authz | scope (`filesystem_id`) + intent (`read`/`write`/`preview`) + `downloadable`, carried in the Storage-JWT and resolved at the storage engine from the host-attested session, never a client-supplied claim; `intent=preview` is read-only and non-downloadable | NFR-SEC-49 |
| Downloadable axis at read | the storage engine resolves `downloadable` at read for both the mount leg and the Web UI; a non-downloadable object yields no egress-eligible artifact (preview ≠ remove-from-sandbox) | NFR-SEC-73 |

The MCP edge carries the same five through a two-tier error model: a protocol error (`JSON-RPC error{code,message}`) never reaches the model and carries a reason code only; a tool-execution error (`result.isError: true` + content) reaches the model with sanitized output. Both are bounded by NFR-SEC-51.

## 4. Versioning & compatibility

Contracts evolve additively. Adding an endpoint, an optional field, a new event type, or a proto field with a fresh field number is non-breaking and ships without a version bump; consumers ignore unknown fields. Removing or renaming a field, tightening a type, changing an error envelope, or repurposing a proto field number is breaking and requires a new **major** version that does not depend on the prior one; the two coexist for the published transition window. Deprecation precedes removal — ship the replacement, migrate clients, then remove. REST deprecation uses the `Deprecation` ([RFC 9745](https://www.rfc-editor.org/rfc/rfc9745.html)) and `Sunset` ([RFC 8594](https://www.rfc-editor.org/rfc/rfc8594.html)) response headers. Breaking-change detection is CI-enforced — `oasdiff` for OpenAPI, `buf breaking` for Protobuf.

The control-plane RPC rule (breaking = major version + deprecation header) is canonical in NFR-IC-04 and governs OCU's own Control/operator API and internal gRPC. The MCP gateway is a Conformist to the MCP wire contract and does not carry semver: its revision is a date string (`protocolVersion: "2025-06-18"`) negotiated on `initialize` and echoed on every HTTP request via `MCP-Protocol-Version`. A revision the peer cannot negotiate is the breaking signal — the server returns an alternate version it supports and a client that cannot accept it disconnects ([MCP lifecycle](https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle)); the spec's example initialization error is `-32602` "Unsupported protocol version". This negotiation path, not an HTTP `Deprecation` header, is the deprecation mechanism NFR-IC-04 describes for that edge. Concurrency is sequential-default per session with opt-in parallelism (NFR-IC-05); PTY and CDP multiplex one WebSocket per session (NFR-IC-03).

## 5. Schema artifacts

This overview is the map; the schema files under `contracts/` own the field-level types. Eight schema files are drafted (the storage surface carries three — mount config, the mount-plane file-op RPC, the Web UI file/artifact API); the rest are not yet built. [`contracts/README.md`](../../contracts/README.md) is the navigator: how to read a schema file and what the `x-ocu-*` annotations mean.

Drafted (not merged):

- `contracts/mcp/2025-06-18/ocu-constraints.schema.json` — the MCP conform profile.
- `contracts/exec/exec-channel.schema.json` — the exec/PTY WebSocket envelope.
- `contracts/control/control-rpc.schema.json` — the in-guest control-RPC envelope (host-owned UDS; v1 verb set `shutdown` only, the deferred and forbidden verbs carried as `x-ocu-tbd-verbs` absent members). STATUS `partial`.
- `contracts/storage/mount-config.schema.json` and `contracts/storage/file-ops.schema.json` — the mount-plane mount config and file-op RPC (the file-op message bodies are tbd).
- `contracts/storage/file-artifact-api.schema.json` — the Web UI file/artifact data plane (upload/list/download/getManifest/preview-render + the embed-token/CSP/CSRF envelope). Per-operation bodies are tbd, like the mount-plane RPC; the embed-token binding claim ([#217](https://github.com/Wide-Moat/open-computer-use/issues/217)) and preview-render parser isolation ([#218](https://github.com/Wide-Moat/open-computer-use/issues/218)) are tracked open items.
- `contracts/audit/audit-fanin.asyncapi.yaml` — the OCSF fan-in (the compute-metering and saturation payloads are tbd, [#150](https://github.com/Wide-Moat/open-computer-use/issues/150)).
- `contracts/admission/runtime-tokens.schema.json` — the admission tier vocabulary: the frozen workload-trust-profile and runtime-tier wire tokens and the 9-cell pairing matrix (NFR-SEC-38, [ADR-0003](adr/0003-sandbox-runtime-tier-ladder.md)). Not a runtime wire message — the tier is resolved independently in the Control / operator API (deploy-time admission) and the Session sandbox (Invariant 8 re-validation), and this schema is the single frozen reference both are checked against. STATUS `frozen`; the microVM tier is pairing-valid but capability-deferred ([#161](https://github.com/Wide-Moat/open-computer-use/issues/161)).

Not built:

- `contracts/openapi/` (operator REST + SOAR revoke) and `contracts/proto/` (session set-up) — [#205](https://github.com/Wide-Moat/open-computer-use/issues/205). Egress secret delivery is off-the-shelf Envoy SDS, not an OCU contract file.
- The transparency-log submission envelope — [#151](https://github.com/Wide-Moat/open-computer-use/issues/151).
- Mock / conformance servers per surface for consumer CI — [#206](https://github.com/Wide-Moat/open-computer-use/issues/206).
- The `SkillProvider` contract is a v1 non-goal; skills load from a customer-provided registry, so no skill-format schema ships in v1.

## 6. Open questions

1. Does NFR-IC-04 bind only the Control/operator API and internal gRPC, leaving the MCP gateway governed solely by date-revision negotiation, or does it need an explicit MCP-edge clause? — [#207](https://github.com/Wide-Moat/open-computer-use/issues/207).
2. Is the inbound gateway contract MCP-only per NFR-FLEX-14, and is `REST fallback` (used in Layer 4 prose, undefined in glossary) dropped or promoted to a defined surface? — [#158](https://github.com/Wide-Moat/open-computer-use/issues/158).
3. The §4 additive-vs-breaking rules, transition window, RFC 9745/8594 headers, and the `oasdiff`/`buf breaking` CI gates extend NFR-IC-04 across two surfaces — should this versioning policy move to a dedicated ADR, leaving §4 a pointer? — [#209](https://github.com/Wide-Moat/open-computer-use/issues/209).
