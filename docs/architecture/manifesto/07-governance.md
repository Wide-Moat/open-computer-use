<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: draft
last-reviewed: 2026-06-02
owner: "@Wide-Moat/architects"
applies-to: next/v1
---

How architectural decisions are recorded, approved, and superseded. Audience: reviewers deciding what merits a decision record, and auditors verifying decision lineage.

## Decision routing

Not every choice is an ADR. The decision tree in [`CLAUDE.md`](../../../CLAUDE.md) §"Architecture content routing" is the canonical router; the threshold for an ADR is step 3 — a load-bearing decision that is hard to reverse, crosses ≥2 components, or closes a debated option. Below that threshold, content lands in its NFR scenario, its component spec, the glossary, or an `## Open questions` entry with a tracking issue. A disagreement about the threshold itself is settled by an ADR that cites the routing rule it changes, not by editing this section.

## ADR lifecycle

An ADR moves through four states, recorded in its `status` front-matter.

| State | Criteria | Next |
|---|---|---|
| **proposed** | PR open; options and rationale under review; front-matter complete, compliance- and license-impact populated | merge on consensus or owner decision → accepted |
| **accepted** | PR merged; the decision is locked and every artifact citing it via `adr:` is production-ready | superseded, deprecated, or stays accepted |
| **superseded** | a later ADR closes a question this one opened; the two cross-link (`superseded-by:` here, `supersedes:` there); the decision still holds for releases made under it | final |
| **deprecated** | the decision no longer applies and has no direct successor (rare — a constraint changed and nothing replaces it) | final |

No other states. There is no pre-PR "draft" for ADRs — the tracking issue (PROCESS.md step 1) is where discussion happens before the file exists. There is no "withdrawn": close the PR (the issue stays open for later), or merge with `status: deprecated` to record that the idea was evaluated and set aside.

## Approval

An ADR is approved by consensus or by named decision-maker, not by vote.

- **Consensus** — the `owner` and all CODEOWNERS reviewers approve the PR; options are fairly evaluated and the consequences are acceptable.
- **Decision-maker** — if good-faith discussion does not converge, the `owner` field names who decides; that approval is recorded in the PR description and the merge commit for the audit trail.

The `owner` front-matter always names the decision-maker. The default for architecture ADRs is `@Wide-Moat/architects`; a specific handle is named when subject-matter authority is required.

## Compliance lineage

Two front-matter fields carry the regulatory audit trail when a decision touches compliance:

- **`compliance-impact`** — the controls the decision touches, in the citation form the canon uses (`DORA-Art.28`, `NYDFS-500.15`, `SOC2-CC6.1`, `EU-AI-Act-Art.15`). Empty when not applicable; an empty field is not a non-compliance mark.
- **`threat-mitigation-link`** — a pointer to the threat-model section or component spec showing how the decision mitigates a named threat.

These let a compliance owner query the decision log by control and verify coverage. The decision audit trail they reconstruct is what DORA Art. 9 and NYDFS §500.15 require of the change-management record.

## Re-evaluation

An accepted ADR is not edited after merge. It is reconsidered when a constraint changes (a dependency is sunset, a regulatory requirement shifts), or a previously-unavailable alternative emerges, or a stakeholder raises a concern later — in each case a follow-up ADR with `supersedes: NNNN` revisits it and either confirms or overrides. No time-based auto-review; the release-readiness gate ([PROCESS.md](../PROCESS.md)) checks that the decision log is complete and no compliance- or buyer-facing ADR has drifted a major release without a re-evaluation note.

## Citation discipline

Every artifact that depends on an ADR records the link, and a supersession cascades through those links:

- **Component specs** carry an `adr:` front-matter list (e.g. the Egress trust-edge spec cites `[0005, 0006, 0007]`).
- **NFR rows** in [`02-nfrs.md`](02-nfrs.md) carry a `Source` column pointing to the deciding ADR or MANIFESTO section.
- **Diagrams** record the driving ADR in the commit that changes them, not in the diagram body.

When a new ADR supersedes an old one, the same PR updates every `adr:` field that cited the old number to cite the new — a cleanup commit, not a fresh decision.
