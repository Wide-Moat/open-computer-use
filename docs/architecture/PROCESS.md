<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: draft
last-reviewed: 2026-05-30
owner: "@Wide-Moat/architects"
applies-to: next/v1
---

How to add new architectural content. Pacing rule: discuss → stub → draft → revise → commit. One artifact per PR. No bulk-generation.

## Adding a component (4 steps)

1. Open an issue titled `Component proposal: <name>`. State the component's purpose, its boundaries (inputs/outputs/owned state), and why it exists now (not later).
2. On a feature branch, create `components/<NN>-<name>.md` from the component-spec template (front-matter + `## Purpose` line, nothing more).
3. Open a PR against `next/v1`. Discuss. Don't add content beyond the stub until the boundaries are agreed.
4. **Inherit Layer 0 gates.** Remove this component's path from `.semgrepignore` (and any other gate-exclusion file) in the same PR that introduces source code for the component. CI must pass without the legacy exclusion. New code is never excluded — the exclusion list shrinks monotonically. Policy: [ADR-0001](adr/0001-layer-0-gate-legacy-exclusion.md).

## Adding an ADR (3 steps)

1. Open an issue titled `Decision: <title>`. State the question, constraints, and at least two candidate options.
2. On a feature branch, create `adr/<NNNN>-<slug>.md` from `adr/0000-template.md` with `status: proposed`.
3. Open a PR against `next/v1`. The ADR moves to `status: accepted` only after the PR merges.

ADRs are reserved for decisions that are load-bearing, hard to reverse, or cross at least two components. If a decision doesn't meet that bar, write it inline in the component spec.

## Adding an NFR / non-negotiable

1. Open an issue titled `Principle proposal: <title>`.
2. Add a single line to `MANIFESTO.md` §03 (non-negotiables) or a sub-section in `manifesto/02-nfrs.md` with a measurable target.
3. State the anti-example explicitly. If you can't name the anti-example, the rule is not yet ready.

## Adding a dependency (Bill of Materials)

1. Open an issue titled `Dependency proposal: <component> = <pick>`.
2. Add a row to the BoM table in `manifesto/05-licensing-posture.md`: name, license, bundled/not-bundled, version pin policy, supply-chain attestation (SBOM / signed / reproducible).
3. Reject if any of the following holds: AGPL (any flavour, except as a separate process with stable API and explicit note), BSL, BUSL (other than past versions of our own code), SSPL, CC-NC, commercial-only-source, sole-maintainer npm/PyPI package with no provenance.

Heavier and vendor-backed beats lighter and unknown. The platform targets regulated enterprises; "lightweight but undocumented" loses every InfoSec review.

## Marking content as TBD

- If the answer isn't known yet, write `status: tbd` in the front-matter, a one-line context, and a link to the tracking issue. Don't invent.
- TBD is a first-class state. Reviewers must not push to remove TBDs prematurely.
- Skill registry is the canonical example: v1 ships zero default skills bundled; the `SkillProvider` abstraction stays TBD until the contract proves itself.

## Capturing primitives discovered during research

When a research, advisor, or verifier cycle surfaces an architectural primitive that OCU will need (e.g. evidence-as-code bundle, egress allow-list, DORA RoI field-level traceability, kill-switch SLA, replay-bundle schema), append it to `primitives-backlog.md` immediately. Do not stash primitives in research-buffer files only — they get lost on the next research cycle.

Each entry is one line: `- **<primitive name>** — <one-line purpose> — lands in <target-section-or-component>`. State the primitive and where it lands; do not record where the fact came from. Target may be `§02` (NFRs), `§03` (non-negotiables), a component spec, or `TBD` if not yet placed.

The backlog drains in two directions: each entry either resolves into a concrete NFR / principle / spec section (delete from backlog when it lands), or becomes a tracked GitHub issue when scope grows beyond a single line.

## Adding a new file kind to the tree

Every file under `docs/architecture/` must match an entry in the whitelist at `scripts/docs-lint/architecture-tree-whitelist.sh`. The whitelist exists so that scratch notes, verifier snapshots, screenshots, and AI artifacts cannot drift into the architecture set. CI blocks merge if an unexpected file lands.

When a PR legitimately needs a new file kind (e.g. introducing the `contracts/` directory or a new compliance template), update `ALLOWED` in `architecture-tree-whitelist.sh` in the same PR. Reviewers check that the added pattern is as tight as possible: `compliance/*-mapping.md`, not `compliance/*`.

## Scope boundary

This file is the how-to for adding artifacts. Adjacent concerns live elsewhere: roadmaps are out of scope; the inventory of which artifacts exist is `README.md`; the rules for writing the content are in `CLAUDE.md` under `## Documentation discipline` and `## Architecture content routing`.
