---
name: ADR proposal
about: Propose an architecture decision
title: "Decision: <title>"
labels: ["architecture", "adr-proposal", "next/v1"]
assignees: []
---

<!--
Per docs/architecture/PROCESS.md "Adding an ADR (3 steps)":
  1. Open this issue.
  2. Create adr/NNNN-<slug>.md from 0000-template.md (status: proposed).
  3. Open PR. ADR moves to status: accepted only after PR merges.

ADRs are reserved for decisions that are (a) load-bearing, (b) hard to
reverse, or (c) cross ≥ 2 components. If your decision doesn't meet that
bar, write it inline in the relevant component spec instead.
-->

## Question

What's the decision being made? One sentence, no preamble.

## Why is this an ADR (not an inline note)

- [ ] Load-bearing — other components depend on it being decided.
- [ ] Hard to reverse — undoing costs more than a typical refactor.
- [ ] Cross-component — affects ≥ 2 components or boundaries.

## Constraints

NFRs, threat-model entries, prior ADRs, regulatory requirements that bound the decision.

## Options (at least 2)

1. **Option A** — sketch
2. **Option B** — sketch

## Compliance / license / threat-model impact (early read)

Which framework controls might this affect? Any FSL dependency-policy interaction? Any threat-model entry it would mitigate?
