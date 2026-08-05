<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
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

The three object-addressed south verbs take their request and response bodies from the already-frozen north Files-API, and the three filesystem-lifecycle verbs stay unpinned — for anyone implementing a south handler or reading the 501 set.

# ADR-0036: South object-verb bodies derive from the north dialect

## Status

`proposed` — amends [ADR-0010](0010-storage-backend-pluggable-adapter.md) (fills the south half of its verb set) and consumes the dialect [ADR-0028](0028-files-api-body-freeze.md) froze. Tracked in [#182](https://github.com/Wide-Moat/open-computer-use/issues/182).

## Context

Seven of the eighteen routable south operations answer `501`: `createFile`, `getFileMetadata`, `listFiles`, `importFiles`, `importZip`, `migrateFilesystem`, `removeFilesystem`. That is not drift. `newHandlerRegistry` binds every frozen op to `unimplemented` and the dispatcher replaces only the nine whose bodies the contract pins, while `fileUpload` and `fileDownload` are REST-routed to their own streaming entrypoints and never read from the registry at all. The 501 set is exactly the set with no frozen body. Three further enum members — `fileDelete`, `readFileMetadata`, `releaseQuarantinedFiles` — are declared as operation names but held out of `knownOps` and are unroutable by construction.

The block is the contract, not the code. [`contracts/storage/file-ops.schema.json`](../../../contracts/storage/file-ops.schema.json) marks these request and response field sets `x-ocu-tbd-bodies` and states the rule that governs them: fill each only when a field-level source pins it. A handler written today would have to invent the body it serves, and `TestOpEnumMatchesContract` exists to catch exactly that.

What changed is that a source now exists for part of the set. [ADR-0028](0028-files-api-body-freeze.md) froze the north Files-API against a running consumer: `FileObject` is the six-field read shape (`id`, `type`, `filename`, `mime_type`, `size_bytes`, `created_at`), and the list envelope is `{data, has_more, first_id, last_id, next_cursor}` with an opaque keyset cursor over a created-at-primary order. Three south TBDs — `createFile`, `getFileMetadata`, `listFiles` — name the same objects over the same durable handle store as the north verbs that already carry those bodies.

The remaining four have no such source. `migrateFilesystem`, `removeFilesystem` and `releaseQuarantinedFiles` are session-pseudobucket control primitives with no shipped counterpart on any plane, and `importFiles` / `importZip` describe an ingest path whose substrate is deferred behind [ADR-0026](0026-parser-sandbox-substrate.md).

## Decision

We will bind the three object-addressed south verbs to the north dialect, and leave the filesystem-lifecycle verbs unpinned.

- **`getFileMetadata`** returns the ADR-0028 `FileObject` verbatim. Its request is the object handle alone. The op is a by-handle read of the same record the north `getFile` returns, so a second dialect for the same object would be a divergence with no source behind it.
- **`listFiles`** returns the ADR-0028 list envelope over `FileObject` entries, resuming on the same opaque `next_cursor`. The cursor stays opaque on this plane too: the durable store's keyset cursor carries the `(created_at, file_id)` boundary tuple, and a bare id cannot resume that walk. Ordering is the store's created-at-primary total order; a caller that needs newest-first asks for it rather than reversing a page it holds.
- **`createFile`** takes the north create's `params` field set and returns the minted `FileObject`. The scope authority is the attested channel, never a body field: a `filesystem_id` in the body is a cross-check hint whose disagreement is `scope_mismatch`, which is the rule ADR-0028 already fixed for the north create.
- **The lifecycle verbs stay `x-ocu-tbd`.** `migrateFilesystem`, `removeFilesystem`, `releaseQuarantinedFiles`, `importFiles` and `importZip` keep their TBD bodies and their `501`, and `fileDelete` / `readFileMetadata` stay out of `knownOps`. Pinning them now would mean inventing the body, which is the failure this ADR exists to avoid.

`downloadable` is absent from every body above. It is a read-time authorization output resolved from the prefix grant ([NFR-SEC-73](../manifesto/02-nfrs.md)), never a stored or transported field.

## Consequences

The routable 501 set drops from seven to four. The GA roadmap's Wave-1 tranche assumed five verbs and a "501-count -5" keystone; two of the five it names are in the unpinned half (`removeFilesystem`) or unroutable entirely (`fileDelete`), so the reachable figure is three. The shortfall against that keystone corrects the plan; it is not a miss.

One object dialect now serves both planes. A change to `FileObject` is a change to both faces at once, which is the point — the alternative was two shapes for one record, drifting independently. The coupling is to the contract file, not between the planes' code: the south handlers keep their own authz, audit and ceiling spine, and the engine-verified credential still originates every scope decision.

The unpinned half stays honest. A caller receives `501` with no `x-deny-reason`, which is a different answer from a deny, and `TestOpEnumMatchesContract` keeps the Go enum and the contract enum in agreement whether or not a body is frozen.

## Alternatives

**Freeze all eleven bodies now.** Rejected: eight of them have no field-level source, so the freeze would be invention presented as canon, and a wrong guess is expensive — a frozen body is a compatibility promise the `buf`/`oasdiff` gates then enforce against us.

**Give the south its own object dialect.** Rejected: the two planes read the same durable handle store. Two shapes over one record drift, and the north shape is the one a running consumer already proved.

**Leave the whole set TBD until every verb has a source.** Rejected: it blocks the storage-custody work that depends on `listFiles` and `createFile` at the engine, and the three object verbs have the source the rule asks for. Waiting buys no additional certainty about them.
