<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: draft
last-reviewed: 2026-06-02
owner: "@Wide-Moat/architects"
applies-to: next/v1
---

The Architecture Manifesto for open-computer-use `next/v1`. This file is the read-first artifact for every architectural decision in this repository.

## Status

Draft. Sections appear one at a time via PRs on `next/v1`. Each section is reviewed before the next is opened. No bulk-generation.

## Sections

The expanded sections live under [`manifesto/`](./manifesto/); this file stays the ≤ 400-line read-first map.

| # | Section | File | Status |
|---|---|---|---|
| 1–2 | Purpose, audience & buyer's checklist | [`01-audience-and-buyer.md`](./manifesto/01-audience-and-buyer.md) | draft |
| — | NFRs / quality goals | [`02-nfrs.md`](./manifesto/02-nfrs.md) | draft |
| 3 | Non-negotiables (with anti-examples) | [`03-non-negotiables.md`](./manifesto/03-non-negotiables.md) | draft |
| 4 | Non-goals (v1) | [`04-non-goals.md`](./manifesto/04-non-goals.md) | draft |
| 5 | Licensing posture (FSL-1.1-Apache-2.0 + dependency policy) | [`05-licensing-posture.md`](./manifesto/05-licensing-posture.md) | draft |
| 6 | Starter-mode policy | [`06-starter-mode-policy.md`](./manifesto/06-starter-mode-policy.md) | draft |
| 7 | Governance & decision-recording protocol | [`07-governance.md`](./manifesto/07-governance.md) | draft |

The NFR catalogue carries no MANIFESTO section number — it is the measurable-quality layer the numbered sections reference, kept in `02-nfrs.md`.

## Hard rules already locked

- License is **FSL-1.1-Apache-2.0** with 2-year automatic Apache-2.0 conversion. See `LICENSE` and `NOTICE`.
- Documentation discipline, decision tree, diagram rules, dependency policy, and testing/QA discipline are codified in the project's `CLAUDE.md` (loaded by the AI assistant on every session). They apply to this directory.

See [`README.md`](./README.md) for the directory layout and [`PROCESS.md`](./PROCESS.md) for how to add a section.
