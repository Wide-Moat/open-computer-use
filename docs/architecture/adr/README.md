<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: stub
last-reviewed: 2026-06-06
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
| [0006](0006-egress-forward-proxy-substrate.md) | Egress forward-proxy substrate | proposed (amended by 0016) | — | 2026-06-14 |
| [0007](0007-egress-auth-mechanism.md) | Egress auth mechanism — edge-inject vs protocol-broker | proposed (amended by 0013, 0016) | — | 2026-06-14 |
| [0008](0008-session-egress-attribution.md) | Session-to-egress attribution by presented token | proposed | — | 2026-06-02 |
| [0009](0009-audit-pipeline-pluggable-by-contract.md) | Audit pipeline is pluggable-by-contract | proposed | — | 2026-06-06 |
| [0010](0010-storage-backend-pluggable-adapter.md) | Storage backend is a pluggable adapter behind the broker | proposed (amended by 0013, 0015, 0016) | — | 2026-06-14 |
| [0011](0011-storage-egress-lane.md) | Storage backend reached over a storage-dedicated egress lane | proposed (amended by 0013, 0016) | — | 2026-06-14 |
| [0012](0012-implementation-language.md) | Implementation language — Go host-side, Rust guest agent | proposed | legacy 0001/0002 | 2026-06-08 |
| [0013](0013-storage-credential-custody.md) | Storage credential custody — provisioning-time host-issued JWT | proposed | — | 2026-06-14 |
| [0014](0014-storage-transport-tier-universal-network-leg.md) | Storage data leg is a tier-universal network endpoint | proposed | — | 2026-06-14 |
| [0015](0015-storage-decomposition-by-trust-plane.md) | Storage decomposition by trust plane | proposed | — | 2026-06-14 |
| [0016](0016-egress-baseline-inspection-hop-backend-scope.md) | Egress baseline — one inspection hop, backend-enforced scope | proposed | — | 2026-06-14 |
| [0017](0017-control-plane-repo-boundary.md) | Control plane and per-session executor are distinct deployables | proposed | — | 2026-06-14 |

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
