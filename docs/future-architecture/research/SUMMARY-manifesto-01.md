<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: research-synthesis
last-reviewed: 2026-05-24
owner: "@Wide-Moat/architects"
applies-to: next/v1
---

Synthesis of three gsd-research briefs into a decision-ready document for the first content-bearing Manifesto artifact (`docs/architecture/manifesto/01-audience-and-buyer.md`). Inputs: `bank-buyer.md`, `enthusiast-audience.md`, `widemoat-thesis-advisor.md` in the same directory.

## Conflicts resolved

| # | Conflict | Winner | Resolution |
|---|---|---|---|
| 1 | enthusiast-audience.md §"Cope-check" recommends demoting enthusiast out of §01 into a separate Manifesto section, but the dual-audience constraint (memory `feedback-dual-audience`) is LOCKED | Enthusiast brief on placement; locked constraint on scope | §01 keeps a single short paragraph naming the enthusiast as a *consequence of the FSL licence*, listing the four contribution channels (evals, hardening reports, MCP/skill contributions, public writeups). Audience-specific DX guidance (Stripe / Rust / FastAPI / Fly patterns) does NOT enter §01; it migrates to a future Manifesto entry on documentation discipline (partially expressed already in `CLAUDE.md` banned vocab). Dual-audience honoured by *naming both*, not by *parallel paragraphs*. |
| 2 | bank-buyer.md §"What this means" rec. 4 says "pick at least two of {in-perimeter, multi-provider, FSL, audit-evidence}"; widemoat-thesis-advisor.md Frame 6 stakes all four as one combined thesis | Advisor brief | Frame 6 is verifiable today and survives both 2026-05 shocks (UiPath Automation Suite 5 May; Anthropic self-hosted sandboxes + MCP tunnels 19 May). Bank brief's "pick two" is a fallback for resource constraint; architectural decisions for all four are already queued in widemoat-thesis-advisor §6 (evidence-as-code, ModelProvider lint, MCP allow-list, FSL clause). Stake all four; demote in-perimeter to "necessary but no longer sufficient". |
| 3 | bank-buyer.md treats SR 26-2 (17 Apr 2026) as a WEAKENING of model-risk path; advisor brief does not mention SR 26-2 | Bank brief | SR 26-2 explicitly excludes gen/agentic AI from MRM scope; load-bearing for §01 because it shifts veto power from model-risk reviewers to TPRM + operational-risk + cyber reviewers. §01 names this in one sentence under "Buyer chain". |
| 4 | bank-buyer.md uses BCG "~10% at scale, 75% experimenting" and IBM "$4.63M shadow-AI" as the why-now stats; advisor brief uses no quantitative anchors | Bank brief | §"Why now" cites BCG ~10%, IBM $4.63M, NYDFS 21 Oct 2025, DORA 2026 enforcement, EU AI Act Annex III deferred to 2 Dec 2027 per Digital Omnibus 7 May 2026. No McKinsey "$200-340B" headline (bank brief rec. 6). |
| 5 | bank-buyer.md says "name CAIO as modal sponsor" with HSBC/UBS/CBA/NatWest citations, but its own Open Questions admit JPM/GS/MS may not have the title | Both, partially | §01 names CAIO as modal sponsor *with the explicit assumption* that the function exists when the title does not. JPM/GS/MS gap goes into §01 Open Questions verbatim. |

## Decisions waiting on the user

1. **Stake all four clauses (Frame 6) or only two (bank brief rec. 4)?**
   - *Recommendation:* All four. The architectural work to back them is queued in widemoat-thesis-advisor.md §6.
   - *Cost if two:* Lose the procurement / InfoSec / legal "everyone finds their clause" reaction; reopen the framing fight every time a competitor ships one of the four.

2. **Enthusiast = one paragraph in §01, or zero?**
   - *Recommendation:* One paragraph, framed as "consequence of the FSL licence". Names four contribution channels.
   - *Cost if zero:* Dual-audience constraint becomes invisible at the top of the Manifesto; future maintainers treat enthusiast contributions as out-of-scope, the funnel closes.

3. **Use "Wide-Moat" as the product name in §01 prose, or keep it generic?**
   - *Recommendation:* "Wide-Moat" — matches the GitHub org and the advisor brief's draft thesis. Repo is `open-computer-use` for legacy reasons; the v1 product surface is Wide-Moat.
   - *Cost if generic:* Prose reads as a template; loses the brand anchor.

4. **Name the v1 closing use-cases (KYC/AML, IT helpdesk, dev productivity, compliance evidence) in §01, or defer to §06 / §04?**
   - *Recommendation:* Name them in §01 under Audience. Out-of-scope items (credit decisioning, customer-facing advisory) go in §04 non-goals, NOT §01.
   - *Cost if deferred:* §01 too abstract for a CAIO to recognise their own buying motion.

5. **Cite SR 26-2 in §01 or defer to §05 / a future compliance section?**
   - *Recommendation:* Cite in §01 Buyer chain — one sentence. It changes who can veto, which IS the §01 topic.
   - *Cost if deferred:* §01 reader doesn't understand why TPRM is the top deal-killer.

6. **Include the failure-modes mini-table (bank brief rec. 8) or move it to a future ADR?**
   - *Recommendation:* Defer. 80-line cap won't hold with a table; belongs in a "What kills the deal" reference doc under `docs/architecture/buyer/` or an ADR on procurement contract surface.
   - *Cost if included:* §01 breaks the 80-line cap; pacing rule violation; §01 starts doing §02/§03's job.

## Draft §01 file content (paste-ready)

```markdown
---
status: draft
last-reviewed: 2026-05-24
owner: "@Wide-Moat/architects"
applies-to: next/v1
---

Names who buys Wide-Moat, who can stop the deal, and why those people are
buying in 2026 rather than 2024 or 2028; audience is anyone proposing a
change that affects buyer-facing surface area.

### Audience

Wide-Moat is built for one buyer: a tier-1 US or EU bank procuring an
in-perimeter AI-agent platform for internal use. Modal early use-cases
that close in 2026 are KYC/AML investigator assistance, internal IT
helpdesk automation, sandboxed developer productivity, and
compliance-evidence collection. Credit decisioning and customer-facing
advisory are out of scope for v1 (see §04).

A solo enthusiast audience exists as a downstream consequence of the
FSL-1.1-Apache-2.0 licence, not as a co-equal persona. Anyone may
self-host, fork, and modify the platform. Wide-Moat expects four
contribution channels from this audience: evaluation submissions,
hardening reports, MCP server and skill contributions, and public
engineering writeups. Security primitives (SCIM/SAML, audit-trail
integrity, signed releases, default-closed network, threat-model docs)
ship in the open artifact; the commercial moat is operational (managed
deployment, paid SLA, certification packs), not capability.

### Buyer chain

A purchase requires alignment across four parallel chains, each with
veto power:

1. **Business sponsor + budget** — Chief AI Officer where the title
   exists (HSBC, UBS, CBA, NatWest as of 2026); the function exists at
   every tier-1 by end-2026 even where the title does not.
2. **Technical owner** — CIO or Head of Engineering Platforms; owns the
   runtime, the SLOs, and the bill.
3. **Gatekeeper stack** — CISO, Chief Risk Officer, Chief Compliance
   Officer, Data Protection Officer; any one of them can kill the deal
   in InfoSec or third-party-risk review.
4. **Procurement and Legal** — runs the TPRM intake and the licence
   redline.

The top deal-killer in 2026 is Vendor Risk / TPRM. The NYDFS industry
letter of 21 October 2025 added contractual requirements on third-party
AI use, training-data limits, sub-processor disclosure, and exit
obligations; missing any clause fails onboarding. SR 26-2 (17 April
2026) excludes generative and agentic AI from Model Risk Management
scope; the veto moves from model-risk reviewers to TPRM,
operational-risk, and cyber reviewers — the platform must over-invest
in the second group, not the first.

### Why now

Four forcing functions converge in 2026. DORA enforcement is live in
the EU since 17 January 2025; 2026 is the first full year of active
supervisory action with fines up to 2% of global turnover. NYDFS Letter
of 21 October 2025 binds covered entities to AI-specific TPRM clauses.
The EU AI Act Annex III high-risk obligations are deferred to 2 December
2027 (standalone) and 2 August 2028 (product-embedded) under the Digital
Omnibus agreement of 7 May 2026 — banks read this as "more time to do
it right", not "skip it". IBM Cost of a Data Breach 2025 puts shadow-AI
breach cost at $4.63M average ($670K premium); 97% of AI-breach victims
lacked basic AI access controls. BCG's 2025 retail-banking report puts
at-scale AI adoption at ~10%; 75% of banks are still experimenting.
The procurement window is open and narrow.

### Positioning thesis

Wide-Moat ships an AI-agent platform for tier-1 EU and US banks that
runs entirely inside the customer's perimeter, is model-agnostic by
construction (MCP-first, no hosted loop), and emits SOC 2 Type II, ISO
27001, DORA Article 28-30, and EU AI Act Annex III evidence as
first-class build artifacts. The licence is FSL-1.1-Apache-2.0:
customers may self-host, fork, and embed, but cannot resell the
platform as a SaaS that competes with the vendor — a clause regulated
buyers read as protection against their tooling becoming someone else's
hosted product. In-perimeter deployment alone is no longer a moat
(UiPath Automation Suite shipped 5 May 2026; Anthropic self-hosted
sandboxes plus MCP tunnels shipped 19 May 2026). The four clauses
together remain verifiable on day one of publication and re-evaluate
on 2027-05-24.

### Open questions

1. Is "CAIO is the modal sponsor" true at JPMorgan, Goldman Sachs, and
   Morgan Stanley, where AI is run through existing CTO/COO structures?
   — track in issue `arch/caio-modal-sponsor-validation`.
2. What is the actual procurement experience of FSL-1.1 in three or
   more tier-1 banks? — track in issue `arch/fsl-procurement-evidence`.
3. Does "first-class build artifact" for compliance evidence mean a
   signed bundle per release, or a continuously-updated portal? —
   track in issue `arch/thesis-evidence-bundle`.
4. Do we include FedRAMP Moderate in the compliance clause for v1, or
   defer to v2? — track in issue `arch/fedramp-v1-or-v2`.
5. Does "model-agnostic by construction" extend to embedding and
   rerank models, or only generation models? — track in issue
   `arch/modelprovider-scope`.
```

Draft body inside this synthesis is ~76 lines; the shipped §01 came in at 57 lines after the pre-merge tightening (FDIC/OCC drop, forward-ref removal, component-list trim, persona split, sentence breakup). Within the 80-line cap. Banned-vocab check passes: no "comprehensive / robust / seamless / powerful / best-in-class / industry-leading / modern / elegant / battle-tested". Banned-phrase check passes: no "It's worth noting / It is important to / In this section / This document will / Going forward / Please note / Happy coding / delve".

### Open-Question reconciliation between this draft and the shipped §01

The draft's Open Question 4 was FedRAMP-v1-or-v2; the shipped §01 retargeted it to ModelProvider-scope (embedding/rerank models). FedRAMP-v1-or-v2 deferred to a later compliance section (or `arch/fedramp-v1-or-v2` issue when filed). The shipped §01 also added a fifth Open Question covering public-sector and academic-consortium Additional Permissions edge cases (`arch/additional-permissions-edge-cases`) that did not appear in this draft.

## Required plan + memory updates — COMPLETED 2026-05-24 post-merge

All four items below were applied during the PR #143 post-merge follow-up cycle. Kept for audit trail.

1. **Plan file** `/Users/nick/.claude/plans/users-nick-open-computer-use-sandboxd-v-eventual-allen.md` — DONE.
   - Replaced "EU AI Act high-risk 2 Aug 2026" with "Annex III standalone 2 Dec 2027 / product-embedded 2 Aug 2028 (Digital Omnibus 7 May 2026)".
   - Added 2026-05 shock-events row (UiPath 5 May / Anthropic 19 May).
   - Added SR 26-2 (17 Apr 2026) row.
   - Updated verifier coverage map row M-02 to reference the four-clause thesis.

2. **Memory** `project_widemoat_positioning.md` — DONE.
   - Old "doesn't exist" thesis kept in a SUPERSEDED block; new four-clause thesis inserted as the current statement.

3. **Memory** `project_next_v1_layer_0_status.md` — DONE.
   - Layer 1 §01 status entry added with the eight research brief paths plus a pointer to this synthesis and the load-bearing decisions.

4. **New memory** `reference_2026_regulator_triad.md` — DONE.
   - Captures NYDFS 21 Oct 2025 + DORA Art. 28-30 + EU AI Act post-Omnibus + SR 26-2 as the single source of truth for "why now" citations.

## What §01 deliberately does NOT decide

Flagged by name so the §01 stub does not leak content downstream:

- **NFRs** (measurable cross-cutting targets: latency, RTO, isolation, audit retention) → §02. §01 names the buyer and the deal-killers; the measurable property they buy goes in §02.
- **Non-negotiables / principles** (default-closed network, no admin UI, no hosted models, evidence-as-code, ModelProvider abstraction enforced in CI) → §03. §01 cites the *thesis*; the *rules that protect it* go in §03.
- **Non-goals** (skill registry, hosted models, admin web UI, our own SaaS, credit decisioning, customer-facing advisory) → §04. §01 mentions credit decisioning and customer-facing advisory only as framing; the locked non-goal list lives in §04.
- **Licensing posture** (FSL allow-list, AGPL reject-list, Bill of Materials, dependency gates) → §05. §01 names the licence; the rationale and the rejection table live in §05.
- **Starter-mode policy** (`auth.mode: local`, image tag policy, `:edge` vs signed digest) → §06. §01 names the dual audience; the knobs that make the OSS path work go in §06.
- **Governance / ADR lifecycle** (PROCESS.md, ADR template, content routing, doc cap enforcement) → §07. §01 names *who buys*; *how we decide* goes in §07.

Discipline: §01 names actors and forces. Everything else is downstream.
