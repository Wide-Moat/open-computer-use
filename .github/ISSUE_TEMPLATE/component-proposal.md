---
name: Component proposal
about: Propose a new component for the next/v1 architecture
title: "Component proposal: <name>"
labels: ["architecture", "component-proposal", "next/v1"]
assignees: []
---

<!--
Per docs/architecture/PROCESS.md "Adding a component (3 steps)":
  1. Open this issue.
  2. Create components/<NN>-<name>.md stub from the template.
  3. Open PR. Discuss in PR review.
-->

## Purpose

One sentence: what role does this component play, and for whom?

## Boundaries (sketch)

What crosses in, what crosses out, what state does it own? Bullet points OK at this stage.

## Why now (not later)

What forces the decision now? If the answer is "in case", file this as a TBD instead.

## NFRs / trust zones it interacts with

Cite manifesto/02-nfrs.md entries or architecture/02-trust-boundaries.md zones it touches.

## Dependencies (BoM impact)

Does this introduce new third-party deps? List candidates and license — see CLAUDE.md "Dependency policy".

## Anti-pattern alternatives

What we explicitly will NOT do for this component.
