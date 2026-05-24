---
status: research-draft
last-reviewed: 2026-05-24
owner: architecture
applies-to: next/v1
---

Evidence brief for the bank-buyer half of `manifesto/01-audience-and-buyer.md`; audience is the architect drafting §01.

## Buyer chain in a tier-1 US/EU bank

Singular "the buyer" does not exist. A purchase of an in-perimeter AI-agent platform at a tier-1 bank requires alignment across four parallel chains, each with veto power:

1. **Business sponsor + budget.** Increasingly a Chief AI Officer with a P&L. HSBC appointed David Rice as inaugural CAIO effective 1 Apr 2026 ([Banking Dive](https://www.bankingdive.com/news/hsbc-david-rice-ai-chief-cto-mario-shamtani-expanded-role-elhedery/815655/)). UBS named Daniele Magazzeni CAIO starting 1 Jan 2026 ([fintechfutures](https://www.fintechfutures.com/job-cuts-new-hires/hsbc-appoints-david-rice-as-its-inaugural-chief-ai-officer)). CBA appointed Ranil Boteju (Dec 2025); NatWest named Dr Maja Pantic Chief AI Research Officer (Jun 2025). JPMorgan has not announced a single CAIO title but routes AI through Mary Erdoes and the firm-wide AI/ML platform org. Assumption (uncited): the CAIO function exists in some form at every tier-1 by end-2026; in banks without the title, the sponsor is the COO of the largest LOB.
2. **Technical owner.** CIO or Head of Engineering Platforms. Buys the runtime, owns SLOs, signs the bill.
3. **Gatekeeper stack.** CISO + Chief Risk Officer + Chief Compliance Officer + Data Protection Officer. Any one of them can kill a deal during InfoSec or third-party-risk review.
4. **Procurement + Legal.** Run TPRM intake, redline the contract, escalate license oddities to outside counsel.

Gartner frames the analyst-side reading: by 2028, AI agents will handle 90% of B2B purchasing decisions, channelling >$15T ([digitalcommerce360](https://www.digitalcommerce360.com/2025/11/28/gartner-ai-agents-15-trillion-in-b2b-purchases-by-2028/)). For now (2026), the human chain above is what closes the deal — and Gartner also forecasts that >40% of agentic AI projects will be cancelled by end-2027 ([Gartner press 2025-06-25](https://www.gartner.com/en/newsroom/press-releases/2025-06-25-gartner-predicts-over-40-percent-of-agentic-ai-projects-will-be-canceled-by-end-of-2027)). Default sales motion is "land with the CAIO, survive the gatekeepers, close through procurement."

## Deal-killers (review boards that veto)

| Board | What kills the deal | Citation |
|---|---|---|
| **Vendor Risk / TPRM** | NYDFS 21 Oct 2025 industry letter on TPSPs — covered entities must add contractual clauses on AI usage, training-data limits, sub-processor disclosure, exit obligations. Missing any = vendor cannot be onboarded. | [NYDFS IL 2025-10-21](https://www.dfs.ny.gov/industry-guidance/industry-letters/il20251021-guidance-managing-risks-third-party); [Inside Privacy](https://www.insideprivacy.com/cybersecurity-2/nydfs-publishes-industry-guidance-on-managing-cyber-risks-related-to-third-party-service-providers/) |
| **InfoSec architecture** | No proof of in-perimeter execution; no demonstrated egress controls against indirect prompt injection / data exfiltration; no signed audit trail under one retention policy. | [Purplesec on data exfiltration via prompt injection](https://purplesec.us/learn/data-exfiltration-ai-prompt-injection/); [dev.to AI governance gap](https://dev.to/ashutoshrana/every-enterprise-ai-framework-has-a-compliance-gap-heres-the-architecture-that-closes-it-20np) |
| **DORA (EU)** | Active enforcement began 2026; fines up to 2% of global turnover (entities) or €5M + 1% daily turnover (critical ICT TPPs); supervisors can suspend service. ~50% of regulated entities entered 2026 with known gaps (Deloitte). | [regulation-dora.eu enforcement](https://www.regulation-dora.eu/blog/dora-2026-enforcement-what-changes); [regulation-dora.eu penalties](https://www.regulation-dora.eu/blog/dora-penalties-fines-enforcement-guide-2025) |
| **Model Risk (was SR 11-7)** | SR 26-2 (17 Apr 2026, jointly Fed/OCC/FDIC) explicitly **excludes** generative and agentic AI from MRM scope as "novel and rapidly evolving" — but bank-wide risk-management and governance expectations still apply. The model-risk path WEAKENS; the broader operational-risk / TPRM / cyber path STRENGTHENS. | [SR 26-2 PDF](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.pdf); [Sullivan & Cromwell memo](https://www.sullcrom.com/insights/memo/2026/April/OCC-Fed-FDIC-Issue-Revised-Guidance-Model-Risk-Management); [cutover.com analysis](https://cutover.com/blog/what-sr-26-2-means-for-banks-deploying-agentic-ai) |
| **Legal / Procurement** | FSL-1.1-Apache-2.0 is not on standard license whitelists. Procurement will escalate to outside counsel; expect questions on the 2-year Apache-2.0 conversion and the anti-SaaS clause. Plan one-pager + redlined MSA before first call. | (assumption, uncited; banks default to OSI-approved list) |
| **DPO / GDPR** | Sub-processor sprawl in public SaaS; data-residency commitments via cloud-provider regional inference are conditional. Claude default routes through US infra ([github issue 40526](https://github.com/anthropics/claude-code/issues/40526)). | [claudereadiness.com](https://claudereadiness.com/blog/claude-security-privacy-enterprise/) |

## Why-now 2026 forcing functions

- **EU AI Act timeline relief (and trap).** Digital Omnibus political agreement 7 May 2026: standalone Annex III high-risk deferred to **2 Dec 2027**; product-embedded high-risk to **2 Aug 2028** ([Consilium press 2026-05-07](https://www.consilium.europa.eu/en/press/press-releases/2026/05/07/artificial-intelligence-council-and-parliament-agree-to-simplify-and-streamline-rules/); [Hogan Lovells](https://www.hoganlovells.com/en/publications/eu-legislators-agree-to-delay-for-highrisk-ai-rules); [White & Case](https://www.whitecase.com/insight-alert/eu-agrees-digital-omnibus-deal-simplify-ai-rules)). Banks read this as "more time to do it right," not "skip it." Agentic systems will almost certainly land in Annex III when scoped against credit decisioning, KYC, employee monitoring.
- **DORA enforcement live.** Regulation in force since 17 Jan 2025; 2026 is the first full year of active supervisory action. First compulsion payments issued; cross-checks against the Register of Information automated ([regulation-dora.eu 2026 changes](https://www.regulation-dora.eu/blog/dora-2026-enforcement-what-changes)).
- **Shadow-AI cost is now a board metric.** IBM Cost of a Data Breach 2025: 20% of breached orgs had a shadow-AI incident; avg total cost $4.63M (vs $4.44M baseline) — $670K premium per breach; 97% of AI-breach victims lacked basic AI access controls ([VentureBeat](https://venturebeat.com/security/ibm-shadow-ai-breaches-cost-670k-more-97-of-firms-lack-controls); [IBM newsroom](https://newsroom.ibm.com/2025-07-30-ibm-report-13-of-organizations-reported-breaches-of-ai-models-or-applications,-97-of-which-reported-lacking-proper-ai-access-controls); [Kiteworks summary](https://www.kiteworks.com/cybersecurity-risk-management/ibm-2025-data-breach-report-ai-risks/)).
- **Public-SaaS Computer Use blockers in banking.** Anthropic's enterprise plan blocks financial-services categories by default in the Claude in Chrome extension ([Harmonic guide](https://www.harmonic.security/resources/securing-claude-cowork-a-security-practitioners-guide)); EU residency requires deployment via Bedrock/Vertex/Foundry rather than native Anthropic API ([github issue 40526](https://github.com/anthropics/claude-code/issues/40526)). Result: every bank that wants Computer Use must either (a) accept a sub-processor stack 3-deep or (b) self-host.

## Top use-cases that close vs theoretical

| Use-case | Close window in 2026 | Evidence |
|---|---|---|
| **KYC / AML investigator assistance** (alert-to-case-closure copilot, transaction-monitoring triage) | Closes now. 58% of banks already use AI for AML/KYC; a Dutch tier-1 reports 90% reduction in onboarding time, 30% staff workload cut. McKinsey writes specifically about agentic AI for client-onboarding and sanctions/fraud investigations. | [McKinsey on agentic AI for KYC/AML](https://www.mckinsey.com/capabilities/risk-and-resilience/our-insights/how-agentic-ai-can-change-the-way-banks-fight-financial-crime); [Deloitte AI adoption in FIs](https://www.deloitte.com/middle-east/en/services/consulting/perspectives/ai-adoption-in-financial-institutions-balancing-growth-and-governance.html) |
| **Internal IT helpdesk automation** | Closes now. Lowest regulatory exposure, internal user, defensible RoI. | (assumption; commonly named in BCG/Deloitte FI surveys) |
| **Developer productivity (sandboxed Computer Use for engineers)** | Closes 2026 if self-hosted; blocked on public SaaS by procurement. | (assumption from sub-processor and residency evidence above) |
| **Compliance evidence collection / control testing** | Closes 2026-2027. On-prem deployments make audit easier — "every artifact lives in one place under one retention policy with one signed audit trail" ([dev.to](https://dev.to/ashutoshrana/every-enterprise-ai-framework-has-a-compliance-gap-heres-the-architecture-that-closes-it-20np)). | |
| **Ops / back-office automation** | Closes 2026 in narrow workflows; broad deployment is year+ away. Only ~10% of FIs apply AI at scale per BCG; 75% still experimenting ([BCG retail banking report 2025](https://web-assets.bcg.com/9e/6f/ee4a643a48f9b4133de389e10386/2025-retail-banking-report-nov-2025-n.pdf); [BCG "AI reckoning"](https://web-assets.bcg.com/1a/b0/007d0359442eb77e5f3aaf07b5c1/for-banks-the-ai-reckoning-is-here-may-2025.pdf)). | |
| **Credit decisioning, customer-facing advisory** | Theoretical for v1. Annex III high-risk; SR 26-2 carve-out plus broad governance still attach; reputational risk too high without a track record. | EU AI Act + cited MRM evidence above. |

## Competitive gap in 2026

| Competitor | Posture | Gap they leave open |
|---|---|---|
| **Anthropic Enterprise** (Code with Claude, London 19 May 2026) | Self-hosted sandboxes in public beta; MCP tunnels in research preview. Tool execution moves customer-side; **orchestration, context, recovery stay Anthropic-side** ([InfoQ](https://www.infoq.com/news/2026/05/claude-mcp-tunnels/); [The New Stack](https://thenewstack.io/anthropic-mcp-tunnels-sandboxes/); [9to5Mac](https://9to5mac.com/2026/05/19/anthropic-enhances-claude-managed-agents-with-two-new-privacy-and-security-features/)). | Agent-loop control plane is a foreign dependency; model-lock-in is structural; not multi-provider. |
| **UiPath Automation Suite — on-prem agentic AI (5 May 2026)** | Self-hosted runtime, supports cloud or self-hosted LLMs. Public-sector launch but explicitly extended to banking. ([UiPath IR](https://ir.uipath.com/news/detail/446/uipath-automation-suite-delivers-on-premises-agentic-ai-for-the-public-sector); [DIGITIMES](https://www.digitimes.com/news/a20260522PD207/security-data.html); [Let's Data Science](https://letsdatascience.com/news/uipath-launches-on-premises-agentic-ai-for-public-sector-9d98d910)) | RPA shape (workflow-orchestrator first, computer-use second); commercial license; lock-in to UiPath skill format. The "agent gives you what you want only inside the UiPath product surface" trap. |
| **OpenAI Enterprise** | Hosted only; no in-perimeter agent loop GA. | Same as Anthropic but worse residency story. |
| **Microsoft Copilot Studio** | Tied to Azure tenant; assumes M365 + Graph + Azure OpenAI. | Not model-agnostic; not deployable outside Azure; not in-perimeter for non-Azure banks. |
| **Skyvern (OSS)** | AGPL-3.0 core; SOC2 Type II + HIPAA in managed cloud. Self-hostable via Docker. ([GitHub](https://github.com/Skyvern-AI/skyvern); [skyvern pricing](https://www.skyvern.com/pricing)) | **AGPL-3.0 is the gap.** Banks running a customised in-perimeter fork would face source-disclosure pressure if they ever exposed it as a "service" — most legal teams reject AGPL by policy. |

Gap that remains for an FSL-1.1-Apache-2.0, model-agnostic, in-perimeter platform with a customer-controlled agent loop: real, but narrower than 12 months ago. Differentiation must rest on (a) full agent loop in-perimeter (not just tool execution), (b) model-agnosticism with no Anthropic/OpenAI tax, (c) bank-acceptable license, (d) audit-evidence pipeline as a first-class component — not a UiPath/Anthropic afterthought.

## Domain-expert failure modes

Concrete patterns that kill enterprise AI deals in 2024-2026 compliance review:

1. **Mock-only on-prem path.** Vendor claims "self-hostable" but the orchestration/agent loop still phones home (Anthropic's first cut of Managed Agents was exactly this until the May 2026 update). Auditor asks for a network diagram, finds an outbound dependency on a public endpoint, deal stalls.
2. **BYOK theater.** Customer brings the KMS, but vendor still decrypts plaintext on vendor-managed servers. Fails any DPO review where the threat model includes the vendor.
3. **Sub-processor sprawl.** Single AI feature ends up with 4-deep sub-processor chain (LLM vendor → hyperscaler → vector-DB SaaS → observability SaaS). NYDFS Oct 2025 letter and DORA's third-party register both make this fatal: each link is a separate due-diligence file.
4. **Missing or non-tamper-evident audit trail.** 97% of orgs that suffered AI-related breaches in 2025 lacked basic AI access controls ([IBM newsroom](https://newsroom.ibm.com/2025-07-30-ibm-report-13-of-organizations-reported-breaches-of-ai-models-or-applications,-97-of-which-reported-lacking-proper-ai-access-controls)). Banks demand WORM-style append-only logs covering prompt, tool call, retrieved context, model output, human override.
5. **AGPL-via-the-back-door.** OSS component (Skyvern, browserless, similar) buried in the product, surfaced only at the OSS-license scan stage of TPRM. Auto-rejection in most banks.
6. **EU residency claimed via "we can deploy on Bedrock."** Conditional residency is not residency; the customer has to own the deployment to claim the control. Procurement reads this in 5 minutes.
7. **Pilot that never scales because risk controls were retrofitted.** 42% of orgs abandoned most AI initiatives in 2025; primary cause cited is compliance and governance, not technical ([dev.to](https://dev.to/ashutoshrana/every-enterprise-ai-framework-has-a-compliance-gap-heres-the-architecture-that-closes-it-20np)). The "we'll add audit later" architecture loses at the InfoSec review.
8. **Shadow-AI bypass.** Sanctioned tool too painful to use → users go back to ChatGPT on a personal phone. IBM: 20% of breaches now involve shadow AI ([VentureBeat](https://venturebeat.com/security/ibm-shadow-ai-breaches-cost-670k-more-97-of-firms-lack-controls)). A platform with friction higher than the public-SaaS alternative loses through this channel even after winning the deal.

## What this means for Manifesto §01

8 recommendations the architect should write into `manifesto/01-audience-and-buyer.md`:

1. **MUST** name the buyer as a chain, not a role. List the four chains (business sponsor / technical owner / gatekeeper stack / procurement-legal) with veto-mapping. One sentence each.
2. **MUST** name the CAIO as the modal sponsor for 2026-2028, with HSBC/UBS/CBA/NatWest as anchor citations. State the assumption that the function exists even when the title does not.
3. **MUST** name the top three deal-killers explicitly: TPRM/NYDFS, InfoSec architecture review, DORA active enforcement. One paragraph each, with the citations from this brief.
4. **MUST NOT** rest the thesis on "only enterprise in-perimeter Computer Use." UiPath shipped 5 May 2026; Anthropic shipped self-hosted sandboxes 19 May 2026. The defensible framing is "full agent loop in-perimeter, multi-provider, FSL-licensed, audit-evidence as first-class component" — pick at least two and stake them.
5. **MUST** state the SR 26-2 carve-out and its consequence: model-risk path weakens, TPRM / operational-risk / cyber path strengthens. v1 architecture must over-invest in the second, not the first.
6. **MUST NOT** cite the McKinsey "$200-340B" headline. Use BCG "~10% at scale, 75% still experimenting" and the IBM shadow-AI cost figures instead.
7. **SHOULD** list the v1 closing use-cases (KYC/AML copilot, internal IT helpdesk, developer productivity, compliance evidence) and explicitly mark credit decisioning + customer-facing advisory as out-of-scope for v1.
8. **SHOULD** include a "failure modes that kill the deal" table mirroring §Domain-expert failure modes above, abbreviated to one line each. Banks recognise their own review processes; this signals we know what theirs look like.
9. **SHOULD** keep §01 to ≤80 lines and stop. Detail belongs in component specs and ADRs; §01 names who buys and what stops them.

## Open questions

- Is "CAIO is the modal sponsor" true at JPMorgan / Goldman / Morgan Stanley, where AI is run from existing CTO/COO structures? Needs sponsor research.
- What is the actual procurement experience of FSL-1.1 in 3+ tier-1 banks? Currently an uncited assumption.
- Does the Anthropic 19 May 2026 release route the agent loop entirely customer-side in self-hosted-sandboxes mode, or only tool execution? Re-read the InfoQ + Anthropic docs before §01 lands.
