<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: accepted
last-reviewed: 2026-08-06
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
amends: ['0010-storage-backend-pluggable-adapter.md']
compliance-impact: [SOC2-CC6.1, ISO27001-A.8.15]
license-impact: none
threat-mitigation-link: ../06-threat-model.md
---

The four object-addressed south verbs take their request and response bodies from the already-frozen north Files-API, and the lifecycle and ingest verbs stay unpinned — for anyone implementing a south handler or reading the 501 set.

# ADR-0036: South object-verb bodies derive from the north dialect

## Status

`accepted` — amends [ADR-0010](0010-storage-backend-pluggable-adapter.md) (fills the south half of its verb set) and consumes the dialect [ADR-0028](0028-files-api-body-freeze.md) froze. Tracked in [#182](https://github.com/Wide-Moat/open-computer-use/issues/182).

## Context

Seven of the eighteen routable south operations answer `501`: `createFile`, `getFileMetadata`, `listFiles`, `importFiles`, `importZip`, `migrateFilesystem`, `removeFilesystem`. That is not drift. `newHandlerRegistry` binds every frozen op to `unimplemented` and the dispatcher replaces only the nine whose bodies the contract pins, while `fileUpload` and `fileDownload` are REST-routed to their own streaming entrypoints and never read from the registry at all. The 501 set is exactly the set with no frozen body. Three further enum members — `fileDelete`, `readFileMetadata`, `releaseQuarantinedFiles` — are declared as operation names but held out of `knownOps` and are unroutable by construction, for the same reason: no frozen body.

The block is the contract, not the code. [`contracts/storage/file-ops.schema.json`](../../../contracts/storage/file-ops.schema.json) marks these request and response field sets `x-ocu-tbd-bodies` and states the rule that governs them: fill each only when a field-level source pins it. A handler written today would have to invent the body it serves, and `TestOpEnumMatchesContract` exists to catch exactly that.

What changed is that a source now exists for part of the set. [ADR-0028](0028-files-api-body-freeze.md) froze the north Files-API against a running consumer: `FileObject` is the six-field read shape (`id`, `type`, `filename`, `mime_type`, `size_bytes`, `created_at`), and the list envelope is `{data, has_more, first_id, last_id, next_cursor}` with an opaque keyset cursor over a created-at-primary order. Four south TBDs — `createFile`, `getFileMetadata`, `listFiles`, `fileDelete` — name the same objects over the same durable handle store as the north verbs that already carry those bodies.

The remaining five have no such source. `migrateFilesystem`, `removeFilesystem` and `releaseQuarantinedFiles` are session-pseudobucket control primitives with no shipped counterpart on any plane, and `importFiles` / `importZip` describe an ingest path whose substrate is deferred behind [ADR-0026](0026-parser-sandbox-substrate.md).

## Decision

We will bind the four object-addressed south verbs to the north dialect, and leave the lifecycle and ingest verbs unpinned.

- **`getFileMetadata`** returns the ADR-0028 `FileObject` verbatim. Its request is the durable `file_id` alone — the `FileObject.id` the store minted, never the session-scoped transfer uuid the streaming ops mint for their own frames. The op is a by-handle read of the same record the north `getFile` returns, so a second dialect for the same object would be a divergence with no source behind it. An absent or cross-scope id degrades to `NOT_FOUND` (the keystone), never a scope deny.
- **`listFiles`** returns the ADR-0028 list envelope over `FileObject` entries, resuming on the same opaque `next_cursor`. The cursor stays opaque on this plane too: the durable store's keyset cursor carries the `(created_at, file_id)` boundary tuple, and a bare id cannot resume that walk. Ordering is the store's created-at-primary total order, walked in either direction: the dialect carries an optional `order` selector on both faces — `desc` for newest-first, absence or any other value for the ascending default — and the south request carries it as a body field mirroring the north `?order=` query parameter ([ADR-0037](0037-files-api-list-order-selector.md)). The cursor binds its direction: a token minted under one order does not resume under the other, so a paged request repeats the order it started with. (Corrected 2026-08-06: the ratified text stated the dialect carries no order parameter on either face; the north face ships `?order=` and ADR-0037 ratifies it into the dialect.)
- **`createFile`** is the ADR-0028 create whole, not its `params` alone: two ordered parts, `params` then `file`, REST-routed to its own streaming entrypoint the way `fileUpload` and `fileDownload` are — a create's bytes cannot ride the unary JSON envelope under the RPC message ceiling. The `params` field set is the north create's; the response is the minted `FileObject`, and the minted `file_id` exists iff the streamed body equalled `declared_size_bytes` — the no-partial-window rule travels with the body it protects. The scope authority on this face is the engine-verified, exchange-issued credential, never a body field: `params.filesystem_id` stays the cross-check hint whose disagreement is `scope_mismatch`, the same rule ADR-0028 fixed for the north create's attested header.
- **`fileDelete`** enters `knownOps` with a write required-intent row. It is the north `DELETE /v1/files/{file_id}` on the south route shape: the request is the durable `file_id` with the `filesystem_id` cross-check hint and `authorization_metadata`, like the other by-handle requests; the success response is the south's standard empty ack; absent-or-cross-scope degrades to `NOT_FOUND`, so a repeat delete maps to deleted and offers no existence oracle. The hold-out reason was the unfrozen body; this ADR freezes it, so the reason is spent.
- **The lifecycle and ingest verbs stay `x-ocu-tbd`.** `migrateFilesystem`, `removeFilesystem`, `releaseQuarantinedFiles`, `importFiles` and `importZip` keep their TBD bodies and their `501`, and `readFileMetadata` stays out of `knownOps`. Pinning them now would mean inventing the body, which is the failure this ADR exists to avoid.

`downloadable` is absent from every body above. It is a read-time authorization output resolved from the prefix grant ([NFR-SEC-73](../manifesto/02-nfrs.md)), never a stored or transported field.

## Consequences

The routable 501 set drops from seven to four, and `fileDelete` becomes routable. The GA roadmap's Wave-1 tranche assumed five verbs and a "501-count -5" keystone; one of the five (`removeFilesystem`) is in the unpinned half, so the reachable figure is four. The shortfall against that keystone corrects the plan; it is not a miss.

One object dialect now serves both planes. A change to `FileObject` is a change to both faces at once, which is the point — the alternative was two shapes for one record, drifting independently. The coupling is to the contract file, not between the planes' code: the south handlers keep their own authz, audit and ceiling spine, and the engine-verified credential still originates every scope decision.

The unpinned half stays honest. A caller receives `501` with no `x-deny-reason`, which is a different answer from a deny, and `TestOpEnumMatchesContract` keeps the Go enum and the contract enum in agreement whether or not a body is frozen.

## Alternatives

**Freeze all eleven bodies now.** Rejected: seven of them have no field-level source, so the freeze would be invention presented as canon, and a wrong guess is expensive — a frozen body is a compatibility promise the `buf`/`oasdiff` gates then enforce against us.

**Give the south its own object dialect.** Rejected: the two planes read the same durable handle store. Two shapes over one record drift, and the north shape is the one a running consumer already proved.

**Leave the whole set TBD until every verb has a source.** Rejected: it blocks the storage-custody work that depends on `listFiles` and `createFile` at the engine, and the four object verbs have the source the rule asks for. Waiting buys no additional certainty about them.
