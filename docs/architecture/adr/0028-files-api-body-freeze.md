<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: accepted
last-reviewed: 2026-07-01
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
amends: ['0023-files-api-north-contract.md']
compliance-impact: [SOC2-CC6.1, SOC2-CC7.2, ISO27001-A.8.15]
license-impact: none
threat-mitigation-link: ../06-threat-model.md
---

The per-operation request and response bodies of the north Files-API are frozen to one OpenAPI file, and the ADR-0023 FileObject dialect is corrected to what the wire carries — for anyone wiring the component-08 BFF, the component-04 north listener, or the public SPA file client.

# ADR-0028: Files-API body freeze and dialect correction

## Status

`accepted` — amends [ADR-0023](0023-files-api-north-contract.md) (corrects its FileObject and cursor dialect) and resolves the two [ADR-0025](0025-f9-internal-transport.md) Open Questions (the per-operation F9 bodies and the `downloadArchive` placement), both tracked in [#304](https://github.com/Wide-Moat/open-computer-use/issues/304).

## Context

[ADR-0023](0023-files-api-north-contract.md) pins the five Files-API verbs, the durable `file_id` handle-store, and the scope-binding keystone. [ADR-0025](0025-f9-internal-transport.md) pins the F9 transport — a dedicated north listener on the object-store service, scope from the host-attested `X-OCU-Filesystem-Id` header, no credential on the leg — and leaves the per-operation bodies and the archive route open.

The consumers already assume a shape. The component-08 BFF sends a two-part `multipart/form-data` create (`params` then `file`), the object-store service reads `params` first and mirrors the proven south `uploadParamsFrame` field-set, and both require `declared_size_bytes`. Three gaps stay unpinned, and each is a live divergence:

- The read FileObject the object-store service emits is six fields; the public SPA type over-declares `downloadable` and `scope` as required, which the F9 client already ignores in favour of the attested channel. `downloadable` is a read-time authorization output (NFR-SEC-73), never a stored field, and a body `scope` is exactly what the keystone forbids a client to trust.
- The list envelope the object-store service emits carries an opaque `next_cursor` the public type drops, while the client paginates on `?after=<last_id>` — two cursor models on one wire. The durable store's list order is created-at-primary; its keyset cursor deliberately carries the (created_at, file_id) boundary tuple, so a bare `last_id` cannot resume the walk (a deleted boundary record repeats or strands a record).
- The create response is fenced pending this freeze; an empty response cannot carry the minted `file_id` the BFF must project to the SPA, so the public upload contract cannot close until the create returns the minted object.

## Decision

We will freeze the north Files-API bodies to [`contracts/openapi/files-api.openapi.yaml`](../../../contracts/openapi/files-api.openapi.yaml) and correct the ADR-0023 dialect to match the wire.

- **Create request.** `POST /v1/files` is `multipart/form-data` with two ordered parts: `params` (a JSON form field, strict-decoded, unknown fields rejected) then `file` (the raw bytes, part filename `upload`). The `params` field-set is the south `uploadParamsFrame`: `filesystem_id` (cross-check hint), `path`, `declared_size_bytes`, `authorization_metadata`, `media_type`, `overwrite_existing`, `filename`, and the tolerated `metadata`/`tags`/`ttl_seconds`. The scope authority is the `X-OCU-Filesystem-Id` header on every verb; a `params.filesystem_id` disagreement is `scope_mismatch`. The MIME field name on the request is strictly `media_type` (the south name); the request does not also accept `mime_type`.
- **Create response.** `201 Created` with the minted FileObject — the same object metadata returns, built from the minted handle record. This closes the public upload contract: the BFF projects a real FileObject to the SPA.
- **Zero-byte out of v1.** `declared_size_bytes` is required and greater than zero. The create response and its minted `file_id` exist iff the streamed body equalled `declared_size_bytes`; there is no length-unspecified form and no observable zero-or-partial-length window. A deliberate empty artifact is out of scope for v1.
- **Read FileObject.** The wire is exactly six fields: `{id, type, filename, mime_type, size_bytes, created_at}`. `downloadable` (a read-time authorization output, NFR-SEC-73) and `scope` (attestation-only) are off the wire; `checksum_md5` is deferred for v1.
- **List envelope.** `{data, has_more, first_id, last_id, next_cursor}`; the forward cursor is `?after=<next_cursor>` (the opaque keyset token). `first_id`/`last_id` are informational boundary ids, not resume keys. (Corrected 2026-07-02: the first freeze put the forward cursor on a bare `last_id`, which cannot resume a created-at-primary keyset walk.)
- **Delete.** `DELETE /v1/files/{file_id}` takes no body, scope in the header; `204 No Content` on success, keystone `404` for absent-or-cross-scope, `503` on an audit-write failure. A client maps both `204` and `404` to deleted, so a repeat delete is idempotent and offers no existence oracle.
- **Archive.** `GET /v1/files/archive` is an additive OCU-extension route, a sibling off `/v1/files` and not one of the five frozen verbs: scope in the header, a repeated `file_id` query parameter, an `application/zip` attachment response, keystone `404` when no named id resolves in scope.
- **Error posture.** Every id-addressed verb returns keystone `404`, never `403`, for absent-or-cross-scope; `503` for an audit-down or latched write.

This amends ADR-0023: the FileObject dialect drops `downloadable`, `scope`, and `checksum_md5` from the wire, and the "opaque-id cursors" wording is fixed to the opaque `next_cursor` forward token with `first_id`/`last_id` as informational boundary ids. The keystone, the durable handle home, and the five verbs are unchanged.

## Consequences

- Component [04](../components/04-object-store-service.md): the north handler serves the frozen bodies; the create response reuses the metadata FileObject builder, so one object serves create, metadata, and each list item. The list handler surfaces the store's opaque keyset token as `next_cursor`.
- Component [08](../components/08-web-ui.md): the public `FileObject` type drops `downloadable` and `scope`, removing the divergence where a `downloadable=false` metadata read misrepresented a re-derived read-time value. The `DELETE` client gate opens against the frozen 204/404 shape, and the archive client gate opens against the additive route.
- The upload contract closes end to end: the create returns the minted `file_id`, so the BFF projects a real FileObject to the SPA without a second resolve round-trip.
- [ADR-0025](0025-f9-internal-transport.md) Open Questions close: the F9 bodies are frozen here, and `downloadArchive` lands as the additive route.
- `checksum_md5` stays deferred; a manifest or dedup consumer re-opens it under ADR-0023 Open Question 5.

## Alternatives

- **Expand the server FileObject with `downloadable` and `scope`.** Rejected: stamping `downloadable` into a stored metadata view is the create-time provenance bit NFR-SEC-73 forbids, and emitting a body `scope` invites a client to trust it, which the keystone rules out. Trimming the public type is the honest direction.
- **Keep the south empty-200 create and resolve the `file_id` in a second call.** Rejected: the empty response carries no `file_id`, so the BFF cannot learn the minted id; the upload contract cannot close without a returned object, and a second resolve is an added round-trip.
- **A bare `last_id` as the forward cursor (no `next_cursor`).** Rejected (2026-07-02 correction; briefly the ruling): the durable store's created-at-primary keyset walk cannot resume from a bare id — a deleted boundary record repeats or strands a record. Re-ordering the store by file id alone would trade away chronological listing; a per-page id-to-tuple lookup breaks on the same deleted boundary. The opaque token survives it because it carries the boundary tuple itself.
- **Permit `declared_size_bytes: 0` for a deliberate empty upload.** Rejected: it re-opens a zero-length window on the upload path for a case the SPA never needs; a zero-byte artifact stays out of v1.
- **Keep `downloadArchive` gated and out of the freeze.** Rejected: the consumer is built and ADR-0023 already names the sibling route; adding it additively keeps the five-verb freeze intact.
