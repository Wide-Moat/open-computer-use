<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: review
last-reviewed: 2026-05-24
owner: "@Wide-Moat/architects"
applies-to: PR #143 (next/v1)
---

Adversarial review of PR #143 — Manifesto §01 plus 8 research-buffer files. Audience is the PR author and reviewer queue.

## Critical

### CR-01: Unsourced regulator citations (FDIC FIL-44-2025, OCC Bulletin 2025-17)

- **File**: `docs/architecture/manifesto/01-audience-and-buyer.md:36`
- **Text**: "FDIC FIL-44-2025 and OCC Bulletin 2025-17 added US-federal requirements on AI inventory, audit rights, and model-drift control."
- **Problem**: Neither identifier appears in `bank-buyer.md`, `widemoat-thesis-advisor.md`, `proof-*.md`, or `SUMMARY-manifesto-01.md`. The bank-buyer brief cites NYDFS 21 Oct 2025 and SR 26-2 (17 Apr 2026) as the US-federal anchors. Two named regulator artefacts have appeared in §01 with no corresponding verified-source row in the research buffer. Bank Legal will dereference both; if either ID is wrong or misdated, the §01 thesis takes a credibility hit on first read.
- **Fix**: Either (a) add a `proof-fdic-occ-2025.md` buffer with primary-source URLs for FIL-44-2025 and OCC Bulletin 2025-17 before merge, or (b) drop both citations and keep only NYDFS + DORA + SR 26-2 (already verified). Option (b) is the safer pre-merge move; option (a) is a follow-up PR.

### CR-02: Forward reference to a file that does not yet exist

- **File**: `docs/architecture/manifesto/01-audience-and-buyer.md:44`
- **Text**: "a published `LICENSE-ADDITIONAL-PERMISSIONS.md` instrument (see [§05](./05-licensing-posture.md))"
- **Problem**: CLAUDE.md doc-discipline rule: "No forward references. Don't link to docs that don't exist." The §05 file is the one allowed forward ref (acknowledged in the review brief). But `LICENSE-ADDITIONAL-PERMISSIONS.md` does not exist at repo root yet — only a draft in `advisor-fsl-internal-use.md`. §01 names a published instrument that has not been published. Bank Legal reading §01 will grep for the instrument and find nothing.
- **Fix**: Either (a) land `LICENSE-ADDITIONAL-PERMISSIONS.md` at repo root in the same PR (or as a pre-requisite PR), or (b) reword line 44 to "a planned `LICENSE-ADDITIONAL-PERMISSIONS.md` instrument enumerating internal-use scope... — tracked in issue `arch/additional-permissions-instrument`" and reference the same tracking issue as Open Question 5. Option (b) is faster; option (a) is cleaner and matches the advisor's recommendation.

## Warning

### WR-01: Word "four" overloaded across three paragraphs

- **File**: `docs/architecture/manifesto/01-audience-and-buyer.md:29, 40, 44, 46`
- **Problem**: Same paragraph cluster uses "four" with four different referents — four parallel buyer chains (line 29), four forcing functions (line 40), four compliance certifications (SOC 2 / ISO / DORA / Annex III, line 44), four-clause intersection (model-neutral / source-available / in-perimeter / per-release evidence, line 46). A regulated reader who skims will conflate "four-clause thesis" with "four compliance certs" or "four forcing functions". The thesis IS the four clauses on line 46; the certifications are evidence FOR the thesis, not the thesis itself.
- **Fix**: Reword line 46 to "The remaining moat is the intersection of: model-neutral, source-available, fully in-perimeter (loop included), and per-release compliance evidence." Drop the bare "four-clause" phrasing where it competes with adjacent counts.

### WR-02: §01 omits v1 closing use-cases that SUMMARY-manifesto-01 explicitly decided to include

- **File**: `docs/architecture/manifesto/01-audience-and-buyer.md:15` vs `docs/future-architecture/research/SUMMARY-manifesto-01.md:37-39`
- **Problem**: SUMMARY Decision #4 records the recommendation "Name them in §01 under Audience" for KYC/AML, IT helpdesk, dev productivity, compliance-evidence collection, with the cost-of-deferral being "§01 too abstract for a CAIO to recognise their own buying motion." The shipped §01 Audience block (lines 13-17) describes the buyer in capability-ceiling language only ("tier-1 US or EU bank — the most demanding envelope") and omits the use-case list. This is either a deliberate post-synthesis pivot (in which case SUMMARY should be updated to reflect why) or an oversight (in which case §01 should add them).
- **Fix**: Reconcile. If the pivot is intentional, add one line to SUMMARY explaining why the recommendation was overridden. If not, add one sentence to §01 line 15 naming the four 2026 closing use-cases.

### WR-03: SUMMARY claims "76 lines of prose" but §01 is 54 lines

- **File**: `docs/future-architecture/research/SUMMARY-manifesto-01.md:155`
- **Text**: "File body counted from front-matter through last open question is 76 lines of prose — within the 80-line cap."
- **Problem**: The shipped §01 file is 54 lines total. SUMMARY's line-count claim refers to the embedded draft (lines 51-152), not the file that landed. Either the draft was tightened post-synthesis without updating SUMMARY, or the count was wrong from the start. Low-risk for ship-decision but invalidates the audit trail.
- **Fix**: Update SUMMARY line 155 to "Draft body is N lines; the shipped §01 came in at 54 lines after tightening — within the 80-line cap" once the final file is locked.

### WR-04: "Wide-Moat is not sold as a single component" paragraph reads as marketing prose

- **File**: `docs/architecture/manifesto/01-audience-and-buyer.md:17`
- **Problem**: The paragraph enumerates eight components ("Computer Use harness, workflow orchestration, presentation surfaces, audit pipeline, identity integration, egress controls, sandbox runtime, key management — assembled, integrated, and supported as one deployable platform"). This is closer to a product-marketing list than a buyer-document statement. Per CLAUDE.md banned-phrase spirit ("State requirements, constraints, trade-offs, and decisions. No adjectives without a measurable referent"), an audience doc names buyers; what they buy is a §06 / commercial-doc concern.
- **Fix**: Trim to one sentence: "Wide-Moat is sold as an in-perimeter ecosystem subscription — a single integrated platform with enablement and certification, not as separable components." Move the component enumeration to a future §06 or component-spec index.

### WR-05: Ambiguous wording in Positioning thesis sentence on FSL scope

- **File**: `docs/architecture/manifesto/01-audience-and-buyer.md:44`
- **Text**: "...enumerating internal-use scope for affiliates, joint ventures, outsourced operators, single-tenant managed deployments, and internal white-labelling; reselling as a competing multi-tenant SaaS remains forbidden, including by Wide-Moat itself."
- **Problem**: "Including by Wide-Moat itself" is a load-bearing claim about the licensor's own constraint. The FSL Future License Grant (Apache 2.0 after 2 years) means Wide-Moat itself can resell post-2-year releases as multi-tenant SaaS — `advisor-fsl-internal-use.md:133-136` and the draft §7 say exactly this. The §01 phrasing reads as an absolute prohibition without the Apache-2.0-conversion qualifier. Bank Legal will ask "for how long?" and find the answer only by reading §05 (forward ref) or the future addendum.
- **Fix**: Reword to "reselling as a competing multi-tenant SaaS remains forbidden during the FSL term (including by Wide-Moat itself), with each release converting to Apache 2.0 two years after publication per the License's Future License Grant."

### WR-06: Personas block mixes architectural and commercial framing without separator

- **File**: `docs/architecture/manifesto/01-audience-and-buyer.md:19-23`
- **Problem**: Persona 2 is "Agents themselves... first-class users from an architectural perspective" — this is an architecture statement, not an audience statement. Personas 1 and 3 are humans inside the customer org. Mixing the two in one numbered list invites a reviewer to ask "are agents a buyer chain?" (answer: no, they are a design constraint). The audience doc names humans; the architectural personhood of agents belongs in a component spec or NFR scenario.
- **Fix**: Either (a) move persona 2 into a separate sentence ("The platform additionally treats agents as a first-class architectural concern — stable contracts MCP, ModelProvider, sandbox runtime API, replay bundle schema") below the human-persona list, or (b) prefix the numbered list with "Three personas, two human and one architectural:" to flag the mix explicitly.

### WR-07: SUMMARY Open Question 4 (FedRAMP) does not match §01 Open Question 4 (embedding/rerank)

- **File**: `docs/future-architecture/research/SUMMARY-manifesto-01.md:148-152` vs `docs/architecture/manifesto/01-audience-and-buyer.md:53`
- **Problem**: SUMMARY's draft Open Question 4 is FedRAMP-v1-or-v2; the shipped §01 Open Question 4 is embedding/rerank scope. §01 Open Question 5 (`additional-permissions-edge-cases`) replaces SUMMARY's missing slot. Either the swap was deliberate (FedRAMP deferred to a later question pool) or accidental. Auditing the diff between SUMMARY's draft and the shipped file should leave a trail.
- **Fix**: Add a one-line annotation to SUMMARY ("§01 Open Question 4 was retargeted from FedRAMP-scope to ModelProvider-scope post-review; FedRAMP-v1-or-v2 deferred to §05 or to a later compliance section.")

## Info

### IN-01: Reduce ambiguity on "the function exists at every tier-1 by end-2026"

- **File**: `docs/architecture/manifesto/01-audience-and-buyer.md:31`
- **Suggested**: This is an unverified assumption acknowledged in `bank-buyer.md:14` ("assumption (uncited)"). §01 carries the claim forward without the hedge marker. Either add "(assumption pending validation — Open Question 1)" inline, or accept the claim as part of the thesis.

### IN-02: "Veto power" used twice, second use is weaker

- **File**: `docs/architecture/manifesto/01-audience-and-buyer.md:29, 33`
- **Suggested**: Line 29 says "four parallel chains, each with veto power"; line 33 then says of the Gatekeeper stack "any one of them can stop the deal". The Gatekeeper stack is one of the four chains but contains four roles, each individually able to veto. Rephrase line 29 to "four parallel chains; each chain holds at least one veto, and the gatekeeper chain contains four independent vetoes."

### IN-03: One sentence covers seven dependency clauses; consider breaking up

- **File**: `docs/architecture/manifesto/01-audience-and-buyer.md:36`
- **Suggested**: The third sentence ("NYDFS... DORA... SR 26-2... TPRM...") runs 65+ words and packs three regulator citations plus a consequence claim into one sentence. Splitting into two sentences (regulator triad / consequence) improves grep-ability for compliance auditors.

### IN-04: Open Questions placeholder format inconsistent with existing repo conventions

- **File**: `docs/architecture/manifesto/01-audience-and-buyer.md:50-54`
- **Suggested**: Each question uses ``issue `arch/<slug>`'' format. CLAUDE.md doc rule says "each entry MUST link a GitHub issue" — the issue placeholders are slugs, not links. Pre-merge this is fine because the issues have not been filed yet; post-merge, convert each slug to a clickable issue link in a follow-up PR.

### IN-05: SUMMARY "Required plan + memory updates" block is stale

- **File**: `docs/future-architecture/research/SUMMARY-manifesto-01.md:157-177`
- **Suggested**: The post-merge updates list (plan file, memory files) was generated before §01 landed. Verify each pointer (plan path, memory filenames) is still accurate before the queued post-merge work runs. The plan file path `/Users/nick/.claude/plans/users-nick-open-computer-use-sandboxd-v-eventual-allen.md` looks machine-generated; confirm it still exists.

### IN-06: Six research-buffer files lack the SPDX license header

- **File**: `docs/future-architecture/research/bank-buyer.md`, `docs/future-architecture/research/enthusiast-audience.md`, `docs/future-architecture/research/widemoat-thesis-advisor.md`, `docs/future-architecture/research/proof-uipath-anthropic-2026-05.md`, `docs/future-architecture/research/proof-anthropic-sdk-license.md`, `docs/future-architecture/research/advisor-fsl-internal-use.md`
- **Suggested**: CLAUDE.md "License Headers" rule says all new source files MUST include an SPDX header. `SUMMARY-manifesto-01.md` and `01-audience-and-buyer.md` carry the header; the six research briefs above do not. Research-buffer discipline is lower, but the rule is "all new source files" without a buffer exclusion. Add the two-line header to each on next touch; do not block merge.

## Verdict

**Ship with notes.** Two Critical findings — both fixable in a single follow-up commit on the same PR before merge:

1. CR-01 (FDIC FIL-44-2025 / OCC Bulletin 2025-17): either drop both citations or land a `proof-fdic-occ-2025.md` source brief.
2. CR-02 (LICENSE-ADDITIONAL-PERMISSIONS.md forward ref): either land the instrument now or reword line 44 to flag it as planned-with-tracking-issue.

Seven Warnings are reconciliation issues between §01 and the research buffer (the buffer is internally consistent; the shipped §01 diverged from SUMMARY's recommendations on use-case naming and component enumeration without leaving a paper trail). Six Info items are stylistic refinements and license-header housekeeping in the research buffer. None of the Warnings or Info items block ship; all can land as a queued follow-up PR with comments on PR #143.

Counts: 2 Critical / 7 Warning / 6 Info.

---

_Reviewed: 2026-05-24_
_Reviewer: Claude (gsd-code-reviewer, opus-4.7-1m)_
_Depth: standard with cross-file consistency checks_
