<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: stub
last-reviewed: 2026-05-24
owner: "@Wide-Moat/architects"
applies-to: next/v1
---

Architecture Decision Records. One file per decision. ADRs appear on demand following the decision tree in `CLAUDE.md`; no bulk-creation of empty stubs.

## Template

[`0000-template.md`](./0000-template.md) — copy when starting a new ADR.

## Index

| Number | Title | Status | Supersedes | Last-reviewed |
|---|---|---|---|---|
| [0001](0001-layer-0-gate-legacy-exclusion.md) | Layer 0 gate — legacy exclusion | accepted | — | 2026-05-24 |
| [0002](0002-session-view-descriptor.md) | Session view is descriptor-driven | proposed | — | 2026-06-01 |
| [0003](0003-sandbox-runtime-tier-ladder.md) | Sandbox runtime tier ladder | proposed | — | 2026-06-01 |
| [0004](0004-operator-authentication-substrate.md) | Operator authentication substrate | proposed | — | 2026-06-01 |
| [0005](0005-egress-credential-delivery-envoy-sds.md) | Egress credential delivery is off-the-shelf Envoy SDS | proposed | — | 2026-06-01 |
| [0006](0006-egress-forward-proxy-substrate.md) | Egress forward-proxy substrate | proposed | — | 2026-06-01 |
| [0007](0007-egress-auth-mechanism.md) | Egress auth mechanism — edge-inject vs protocol-broker | proposed | — | 2026-06-01 |

## Lifecycle

`proposed` → `accepted` (on PR merge) → `superseded` (when replaced by a later ADR; both files cross-link via front-matter).

`deprecated` is for decisions that no longer apply but were not superseded by a specific replacement.

## ADR threshold

An ADR is for decisions that are:

- **Load-bearing** — other components rely on this being decided one way.
- **Hard to reverse** — undoing it costs more than a typical refactor.
- **Cross-component** — affects at least two components or boundaries.

Decisions that don't meet the bar belong inline in the relevant component spec. See `CLAUDE.md` decision tree §3 for the test.

## Hard cap

Each ADR ≤ 200 lines. If it doesn't fit, the decision is too big — split it.
