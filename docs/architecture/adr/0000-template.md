<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: YYYY-MM-DD
owner: "@github-handle"
applies-to: next/v1
supersedes: []
superseded-by: null
compliance-impact: []
license-impact: none
threat-mitigation-link: null
---

Template for an Architecture Decision Record, used by `next/v1` engineers to capture decisions that are load-bearing, hard to reverse, or cross at least two components.

# ADR-NNNN: <title>

## Status

`proposed` | `accepted` | `superseded` | `deprecated`

Mirror the value in front-matter. On lifecycle change, update both this section and the front-matter `status` / `superseded-by` fields.

## Context

What forces drive this decision? What constraints are in play (NFRs, threat-model entries, prior ADRs, regulatory requirements)? One short paragraph. State the *problem*, not the solution.

## Decision

We will <verb> <object>, because <one-line rationale>.

Present tense. One sentence ideal, one paragraph max.

## Consequences

What changes as a result? Positive and negative. Cite the components affected by name.

- Positive: …
- Negative: …
- Neutral but worth noting: …

## Alternatives considered

At least two. For each: what it is, why we rejected it. Single-sentence per alternative is fine; this is not an essay.

- **<alternative A>** — rejected because …
- **<alternative B>** — rejected because …

## Compliance impact

Which framework controls does this decision satisfy or affect? Reference by control ID (e.g. `SOC2-CC6.1`, `ISO27001-A.8.2`, `EU-AI-Act-Art.12`). Empty if none.

## License impact

Does this introduce a dependency or pattern that affects our FSL-1.1-Apache-2.0 distribution? Empty if none.

## Threat mitigation

Link to the threat-model entry this decision mitigates, if any. Empty if not threat-driven.

---

Hard cap: 200 lines. If the decision doesn't fit, split it.
