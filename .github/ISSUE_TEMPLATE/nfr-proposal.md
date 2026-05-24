---
name: Principle / NFR proposal
about: Propose a non-negotiable principle or measurable cross-cutting requirement
title: "Principle proposal: <title>"
labels: ["architecture", "manifesto", "next/v1"]
assignees: []
---

<!--
Per docs/architecture/PROCESS.md "Adding a NFR / non-negotiable":
  1. Open this issue.
  2. Add a single line under MANIFESTO.md §03 OR a sub-section in
     manifesto/02-nfrs.md.
  3. Discuss in PR review.

A "non-negotiable" goes in MANIFESTO.md §03 with an anti-example.
A "measurable cross-cutting requirement" goes in manifesto/02-nfrs.md
with a specific target (latency, RTO, isolation, retention, etc.).
-->

## Kind

- [ ] Non-negotiable principle (goes in MANIFESTO §03)
- [ ] Measurable NFR (goes in manifesto/02-nfrs.md)

## The rule, in one sentence

State the principle or requirement. No marketing tone.

## Rationale (one line)

Why this is non-negotiable — what's the failure mode if we ignore it?

## Anti-example (mandatory)

The concrete thing this rule forbids. If you can't name an anti-example, the rule isn't ready.

## Measurable target (NFRs only)

Latency p99? Retention duration? Isolation strength? Be specific.

## Affected components / ADRs

Where will this principle bind future decisions?
