<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: accepted
last-reviewed: 2026-06-22
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: ['contracts/storage/file-artifact-api.schema.json (PoC north op-shape: OperationName enum + {filesystem_id,path}-only handle model)']
superseded-by: null
amends: []
compliance-impact: [SOC2-CC6.1, SOC2-CC7.2, ISO27001-A.8.15]
license-impact: none
threat-mitigation-link: ../06-threat-model.md
---

The canonical public north contract of filestore is the de-facto Files-API shape (`/v1/files`), superseding the PoC custom op-shape while preserving the embed-token, cookie/CSRF/CSP, and three-axis-authz wrapper — for anyone wiring an external file client into the Web UI or editing the north-face contract or its handle model.

# ADR-0023: Files-API as the north contract of filestore

## Status

`accepted`

## Context

External clients hit the file API directly — `/v1/files` is the public data-plane surface, fronting the external data-plane client E5 ([`components/08-web-ui.md`](../components/08-web-ui.md)). The south `/v1/filestore/fs/<op>` surface is a different consumer: the in-guest rclone mount client speaks it as a POSIX/FUSE filesystem RPC ([`contracts/storage/file-ops.schema.json`](../../../contracts/storage/file-ops.schema.json)), authenticating with the egress-injected backend credential — a credential a browser cannot obtain. The two surfaces share one authorization spine (`filesystem_id` + `intent` + `downloadable`) but have different clients, auth, addressing, transport, and verbs.

The PoC north op-shape ([`file-artifact-api.schema.json`](../../../contracts/storage/file-artifact-api.schema.json)) was a placeholder: seven custom ops over a `{filesystem_id, path}`-pair handle that carried no opaque object id. The shipped PoC file API (`/api/uploads`, `/api/outputs`, `/files/{chat_id}/...`, `/preview`) already serves humans the upload/list/download/preview quartet over browser auth — so the public surface is already file-management-shaped, and its model echoes the de-facto Files API supported by Anthropic and OpenAI. The recut keeps the cross-cutting auth/transport/audit wrapper intact ([invariants 1-4, 6, 8](../components/08-web-ui.md)) and honours the ephemeral-no-retention rule ([ADR-0010](0010-storage-backend-pluggable-adapter.md)).

## Decision

We will make the Files-API shape the canonical north contract of filestore — the public surface speaks Files-API natively rather than fronting a custom op-shape — because external clients hit the public surface directly and one open wire shape removes the adapter layer.

- **Endpoints.** `POST /v1/files` (upload, `Create`), `GET /v1/files` (list, `Read`), `GET /v1/files/{file_id}` (metadata, `Read`), `GET /v1/files/{file_id}/content` (bytes, `Read`), `DELETE /v1/files/{file_id}` (`Delete`). These five replace the seven PoC ops. `getManifest` folds into a per-object `checksum_md5`; `downloadArchive` stays as a sibling OCU-extension route under the same cookie/CSP envelope, off `/v1/files`; `previewRender` stays an internal Web-UI SPA route.
- **File object.** Anthropic-leaning dialect: `{id, type:"file", filename, mime_type, size_bytes, created_at (RFC-3339), downloadable, scope{id,type:"session"}, checksum_md5?}`. `id` is opaque and server-minted. No `expires_at`. List envelope is `{data, has_more, first_id, last_id}` with opaque-id cursors.
- **Handle.** `file_id` resolves through a durable scope-bound mapping `file_id → {scope, object_ref, filename, mime, size, created_at, downloadable_policy_ref}`. The mapping holds metadata and a reference into the customer store, never customer bytes. It lives in the object-store service's own durable handle-store ([component-04](../components/04-object-store-service.md), a new on-disk fsync'd store beside the audit `FileSink`, `--handle-store` path flag; Postgres/engine-side impl deferred), not in the ephemeral within-session objectid store that backs the south mount RPC, and not in the control plane.
- **Keystone invariant.** `file_id` is never a capability. The resolver always takes scope from the host-attested channel (embed-token + cookie), asserts `record.scope == attested_scope`, and on mismatch or no record returns `not_found`, never `forbidden` — so a `file_id` is durable but resolves only under its own attested scope. The `scope_mismatch` reason is reserved for the `authorization_metadata.filesystem_id` caller-hint axis; the `file_id`-resolve path emits only `not_found` (a cross-scope or unknown id is indistinguishable from non-existence — anti-enumeration).
- **`downloadable`** is the read-time NFR-SEC-73 policy value surfaced through the Files-API field with a documented re-interpretation (read-time egress decision, not a create-time provenance bit); `intent=preview` stays non-downloadable regardless. `DELETE` unlinks the handle so the id stops resolving; the service owns no bytes, so it makes no byte-erasure guarantee. Symmetrically, a resolving `file_id` asserts the handle persists, not that the customer-store bytes still exist — `GET /v1/files/{file_id}/content` may resolve the handle and then fail re-fetch if the customer store dropped the bytes ([ADR-0010](0010-storage-backend-pluggable-adapter.md) makes no byte-durability promise).

The south mount RPC (`file-ops.schema.json`) stays internal and untouched, including its weak-session-JWT-to-egress credential exchange ([ADR-0013](0013-storage-credential-custody.md), [ADR-0019](0019-egress-exchanges-filestore-credential.md)). The shared `AuthorizationMetadata` (`filesystem_id` + `intent` + `downloadable`) stays one referenced shape across both schemas — forking it into two near-copies is duplication and is rejected.

## Consequences

- Component [08](../components/08-web-ui.md): the seven-op `OperationName` enum and the `{filesystem_id, path}` `FileEntry` handle are superseded by the five Files-API endpoints and the opaque-`id` `FileObject`. Invariant 5 is recut from "the handle is the `{filesystem_id, path}` pair" to the scope-bound `file_id`-resolution rule; invariants 1-4, 6-8 hold unchanged. The embed-token verify, cookie/CSRF/CSP envelope, three-axis authz, ingest ceilings, and `DenyReason` survive frozen — `DenyReason` becomes the internal/audit reason, projected to the public Files-API error type with HTTP status authoritative.
- Component [04](../components/04-object-store-service.md): gains the durable `file_id`→handle-record index (metadata + customer-store reference, never bytes) beside the audit `FileSink`. The OCSF `FileActivityEvent` `object_handle` field is recut for the north face: it logs the resolved `object_ref` / `{filesystem_id, path}`, not the public `file_id`; its "no opaque object id exists" note is dropped for the north surface. The ephemeral objectid store keeps its within-session lifecycle for the south mount RPC.
- Component [02](../components/02-control-operator-api.md): unchanged. It keeps only the session↔`filesystem_id` binding it already owns; no file-handle table.
- ADR-0010-clean: an `id ↔ handle` mapping is metadata-and-reference index-keeping, not customer-byte retention, WORM, versioning, or erasure duty — byte durability and erasure stay the customer store's duty. The service already owns durable fsync'd state (the audit hash-chain), so a durable handle index is the same persistence class, not a new capability.
- Positive: external Anthropic/OpenAI-dialect file SDK clients point at the north face natively; persistence is honoured by the durable handle, not an ephemeral store. The opaque id the PoC schema warned against is made safe by the scope-binding rule.
- Negative: the north face reintroduces an opaque object id and cursor pagination the PoC schema forbade; both are deliberate and gated on the now-durable, scope-bound handle home.

## Alternatives considered

- **Thin Files-API adapter over the custom north op-shape** — rejected: an adapter is a second layer over the same surface external clients hit directly.
- **Files-API verb names on the south mount RPC** — rejected: a browser cannot present the egress-injected backend credential the mount requires, and the rclone client needs POSIX/FUSE verbs the five Files-API endpoints cannot express; a global-bearer surface on the guest leg re-creates the confused-deputy the no-cred-in-guest invariant kills.
- **The durable handle registry in the control plane** — rejected: `file_id` is a storage concern; the object-store service already owns durable state and the scope-binding resolver, so the handle index belongs there, and a control-plane round-trip on every read is avoided.
- **A separate `files-api-gateway` deployable** — deferred to v2; the minimal shelf serves the contract on the existing component-08 ingress.

## Compliance impact

- `SOC2-CC6.1` / `ISO27001-A.8.15`: the scope-binding rule re-derives authority from the host-attested channel per request; a `file_id` is never a capability and cross-scope resolution degrades to `not_found`, so the durable id adds no enumeration or confused-deputy path.
- `SOC2-CC7.2`: every endpoint emits the unchanged gateway-authored, fail-closed OCSF `FileActivityEvent`; `Create`/`Read`/`Delete` map to the five endpoints, audit-write-failure still denies.

## License impact

None. The Files-API shape is the public, both-vendor de-facto standard adopted as the native north contract; the recut adds no bundled dependency.

## Threat mitigation

The opaque, durable `file_id` is the new surface this ADR introduces, and the scope-binding keystone is its mitigation: scope always comes from the host-attested channel, the id is asserted equal to its stored scope, and any mismatch resolves to `not_found` — so the traversal/enumeration risk the PoC schema guarded against by refusing an opaque id is held by binding instead. The auth/envelope/ingest/audit wrapper ([`06-threat-model.md`](../06-threat-model.md) §3) is unchanged.

## Open questions

1. OpenAI field-dialect alias view (`object`/`bytes`/epoch `created_at`/after-only cursor) as an edge serialization adapter over the same endpoints (tracking issue TBD).
2. Engine-adapter delete semantics for customer-owned stores — handle-unlink vs requested byte-delete where the adapter exposes it (tracking issue TBD).
3. Chat-message-embeddable session-scoped artifact URLs (the PoC `computer_link_filter` injects preview/archive links into chat) — how the Files-API surface emits a clickable URL alongside the raw `file_id` (tracking issue TBD).
4. Preview rendering — the PoC `/preview/{chat_id}` SPA and inline-artifact URL promotion as an internal Web-UI route relating to a `file_id` (tracking issue TBD).
5. Uploads-vs-outputs namespace split (human→sandbox vs sandbox→human, with the content-hash manifest for dedup sync) under the single `/v1/files` surface (tracking issue TBD).
6. MCP-resource mirror — the same files surfaced as `file://uploads/{scope}/...` MCP resources reconciled with the Files-API `file_id` (tracking issue TBD).
