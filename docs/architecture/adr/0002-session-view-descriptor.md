<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-06-01
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
compliance-impact: [EU-AI-Act-Art.12, SOC2-CC6.1]
license-impact: none
threat-mitigation-link: 06-threat-model.md
---

Fixes how OCU's data-plane UI discovers its views, so adding the deferred live-session views (browser, terminal) is additive, not a breaking change.

# ADR-0002: Session view is descriptor-driven

## Status

`proposed`

## Context

The PoC ships a working preview panel with three tabs — files, a live browser (CDP screencast), and a live terminal (ttyd). v1 ships only the files tab; the two live-session tabs are deferred to [#210](https://github.com/Wide-Moat/open-computer-use/issues/210) pending a security pass on the human channel into the guest. The two later tabs read from a different source than files (ephemeral CDP/PTY streams off the Session sandbox host edge, not the durable object store served by the artifact-plane in the Storage zone), authenticate separately, and have their own lifecycle. The risk: if the UI hardcodes its tab set or folds all three behind one file API and one credential, adding the live-session tabs later breaks the embedding contract and collapses two trust domains into one.

## Decision

We will have the data-plane UI discover its available surfaces at runtime from a session-scoped descriptor list, rendering one tab per descriptor and ignoring kinds it does not recognize, because this makes the file tab and the later live-session tabs additive entries in one list rather than a hardcoded set. The discovery endpoint lands as an addition to the artifact-plane contract inventory ([`08-contracts.md`](../08-contracts.md) §1) in the same change set that ships it.

## Consequences

- Positive: v1 returns one descriptor (`files`); the endpoint returns three once [#210](https://github.com/Wide-Moat/open-computer-use/issues/210) lands. Adding the browser and terminal tabs is appending two descriptors; an old shell renders the subset it recognizes and never errors on a new kind.
- Positive: the files surface is served by the **artifact-plane** ([component 08](../components/08-artifact-plane.md)), its own deployable inside the Storage zone ([`05-c4-container.md`](../05-c4-container.md) §3, decomposition per [ADR-0015](0015-storage-decomposition-by-trust-plane.md)); the shell that renders the descriptor list is a thin data-plane-UI component over per-surface sources, not owned by any one container — the deferred live-view tabs read off the **Session sandbox** host edge, a different container.
- Positive: each surface authenticates to its own source with its own token — the files tab uses the embed-token → first-party-session path ([NFR-SEC-82](../manifesto/02-nfrs.md), [NFR-SEC-84](../manifesto/02-nfrs.md)); a future live-view tab gets a separate session-scoped token. The shell carries and forwards no credential, closing the PoC's single-`chat_id`-gates-everything weakness.
- Positive: the descriptor's `entry.url` is host-side only — a structural invariant (schema + property test) that forbids a guest container IP/port, enforcing host-dials-guest ([NFR-SEC-43](../manifesto/02-nfrs.md)) before any live-view kind exists.
- Negative: a capability-discovery endpoint plus a versioned descriptor schema is more than a single hardcoded tab needs today; mitigated by shipping the minimum (a length-1 list, open `kind` enum, `transport` discriminator, `contract_ref`) and deferring the host↔surface message protocol until a sandboxed surface needs it.
- Neutral: the descriptor is one cross-surface contract; each surface keeps its own per-surface contract (the file-artifact data plane stays `file-artifact-api.schema.json`), not absorbed into a mega-API.

## Alternatives considered

- **Hardcoded tab set in the UI** — rejected because adding the browser/terminal tabs would change the shell and break any embedder pinned to the v1 tab set; offers no forward-compatibility seam.
- **One mega data-plane API with capability flags** (`/dataplane` toggling files/browser/terminal under one credential) — rejected because it folds the durable file-artifact data plane and the ephemeral live-view plane behind one credential and one lifecycle, collapsing two trust domains (NFR-SEC-25) and re-creating the PoC exfil surface.
- **Customer builds its own UI over our APIs, OCU ships no SPA** — rejected for v1 because OCU's authenticated file-preview SPA is in-scope per `03-c4-context.md` §4; kept available as a path (the descriptor + per-surface contracts are public), but not the default.

## Compliance impact

`EU-AI-Act-Art.12` (per-surface audit of file activity, NFR-SEC-79), `SOC2-CC6.1` (per-surface authentication, no panel-wide credential).

## License impact

None.

## Threat mitigation

Structurally bars a guest-reachable `entry.url` ([NFR-SEC-43](../manifesto/02-nfrs.md)) and keeps per-surface authentication, closing the PoC's single-`chat_id` and direct-guest-reachability weaknesses; the artifact-plane F11 rows P4-S3/T3/I3 in [`06-threat-model.md`](../06-threat-model.md) §3.2 cover the embed-token and single-credential vectors. Live-view STRIDE rows land with [#210](https://github.com/Wide-Moat/open-computer-use/issues/210).
