<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: accepted
last-reviewed: 2026-08-06
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
amends: ['0028-files-api-body-freeze.md', '0036-south-object-verb-bodies.md']
compliance-impact: []
license-impact: none
threat-mitigation-link: ../06-threat-model.md
---

The list verb takes an optional direction selector on both faces, and the frozen dialect gains the parameter it has been serving since July — for anyone reading a list page or implementing the south list handler.

# ADR-0037: Files-API list carries an order selector

## Status

`accepted` — amends [ADR-0028](0028-files-api-body-freeze.md) (adds a parameter to the frozen list surface) and corrects [ADR-0036](0036-south-object-verb-bodies.md) (whose listFiles bullet denied the parameter exists). Tracked in [#182](https://github.com/Wide-Moat/open-computer-use/issues/182).

## Context

The store's list order is created-at-primary ascending. A page-1-only reader therefore sees the oldest objects, so in a scope holding a full page the file a user just created is absent from the pane that should show it. That is [#182](https://github.com/Wide-Moat/open-computer-use/issues/182).

The fix shipped on 2026-07-19: a descending walk in the durable store with a direction-aware cursor, and a `?order=` query parameter on the north listener threading it through. It works, it is tested at both layers, and the cursor carries a version byte so a token minted under one direction is refused under the other.

It reached the wire without reaching the contract. The commit that added the parameter touched no file under `contracts/`, so the frozen [Files-API surface](../../../contracts/openapi/files-api.openapi.yaml) declares five parameters and the implementation honours six. Eighteen days later [ADR-0036](0036-south-object-verb-bodies.md) read the contract, found no order parameter, and ratified the sentence "the dialect carries no order parameter on either face" — entombing the drift as canon under the same issue number that had already shipped the parameter.

`oasdiff` cannot catch this class. A handler that reads a new query parameter never edits the schema, so a schema diff sees nothing; the drift is invisible to the gate that exists to prevent drift.

## Decision

We will make the order selector part of the dialect on both faces, and give the north face the contract row it has been serving without.

- **The selector is optional and tolerant.** `desc` selects the descending walk; absence, or any other value, is the ascending default. A caller cannot fail a request by sending a value we do not recognise — the direction is a rendering preference, not an authorization input, so a strict enum would turn a typo into a refused list.
- **The cursor binds its direction.** A continuation token minted under one order does not resume under the other; the token carries the direction and the store refuses the mismatch. A paged reader repeats the order it started with.
- **Both faces carry it.** North takes it as the `?order=` query parameter it already serves; south takes it as an optional `order` field in the listFiles request body, since that face is JSON rather than query-shaped. The semantics are identical — one dialect, two carriers.
- **The parameter is declared.** `contracts/openapi/files-api.openapi.yaml` gains the query parameter, and the south `listFiles` body in `contracts/storage/file-ops.schema.json` gains the field.

The shipped behaviour does not change. This ADR ratifies what runs and closes the gap between it and the frozen text.

## Consequences

ADR-0036's listFiles bullet is corrected in place with a dated note, the convention [ADR-0028](0028-files-api-body-freeze.md) already uses for its own cursor correction. The false clause stays visible rather than being silently rewritten: a reader who acted on it deserves to see that it was wrong and when.

A wire-parity test now binds the query parameters the list handler reads to the parameters the contract declares, in the mould of the existing `createparams` and `fileobject` parity tests. Without it the next undeclared knob repeats this exactly — and repeats it invisibly, because the schema gate is structurally blind to a handler-side read.

Ascending stays the default, so every existing caller and every stored cursor is unaffected. A full-walk consumer should keep using it: under ascending, a concurrent create lands strictly after any prior cursor and is picked up, while under descending it lands before the walk's start and is missed.

## Alternatives

**Remove the parameter and hold the frozen text.** Rejected: it re-breaks #182, discarding a correct fix with a sound direction-versioned cursor to protect a sentence that was wrong when written. The contract is meant to describe the wire, not to veto it after the fact.

**Patch ADR-0036's bullet and add no ADR.** Rejected: the repair adds a parameter to the ADR-0028 frozen surface, which is a decision, not a typo. The clause being corrected set the bar itself — "ratified as an ADR-0028 amendment" — and following it is cheaper than arguing the exception.

**Declare the parameter north-only.** Rejected: a knob on one face and not the other is the two-dialects-for-one-record drift ADR-0036 exists to prevent, and the south list reads the same store through the same cursor.
