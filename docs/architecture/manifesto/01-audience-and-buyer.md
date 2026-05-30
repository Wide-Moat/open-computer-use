<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: draft
last-reviewed: 2026-05-24
owner: "@Wide-Moat/architects"
applies-to: next/v1
---

Names who Wide-Moat is built for, who can stop a deployment from happening, and why those people are buying in 2026 rather than 2024 or 2028. Audience is anyone proposing a change that affects buyer-facing surface area.

## Audience

Wide-Moat is built for any organisation that needs in-perimeter agentic AI. The capability ceiling targets the requirements of a tier-1 US or EU bank — the most demanding regulatory and operational-scale envelope we design against — so smaller and less-regulated organisations fit beneath it on the same artifact. Primary commercial focus and trust anchor are tier-1 banks; the product is one product, not a tiered SKU. The 2026 use-cases that close at this tier are KYC/AML investigator assistance, internal IT-helpdesk automation, sandboxed developer productivity, and compliance-evidence collection.

Wide-Moat is sold as an in-perimeter ecosystem subscription — a single integrated platform with enablement and certification, not as separable components.

The platform serves two human personas inside the customer organisation:

1. **Business users** consume agents through chat surfaces, workflows, and dashboards. They never see the platform plumbing.
2. **Builder and platform engineers** inside the customer create skills, MCP servers, n8n workflows, observability dashboards, and eval suites. They are the customer's internal multipliers; the training and enablement Wide-Moat sells is for them.

Agents are treated as a first-class architectural concern below the human personas — they call tools, execute browser sessions, and emit audit events through OCU's stable contracts (MCP, the sandbox runtime API, the replay bundle schema). They are a design constraint, not a buyer.

A solo enthusiast audience exists as a downstream consequence of the FSL-1.1-Apache-2.0 licence (full posture lands in §05 — see issue `arch/manifesto-05-licensing-posture`), not as a co-equal persona. Anyone may self-host, fork, and modify the platform. Expected contribution channels are evaluation submissions, hardening reports, MCP server and skill contributions, and public engineering writeups. Security primitives ship in the open artifact; the commercial moat is operational, not capability.

## Buyer chain

A purchase requires alignment across four parallel chains; each chain holds at least one veto, and the gatekeeper chain contains four independent vetoes.

1. **Business sponsor and budget** — Chief AI Officer where the title exists (HSBC, UBS, CBA, NatWest as of 2026); the function is assumed to exist at every tier-1 by end-2026 even where the title does not (uncited assumption — see Open Question 1).
2. **Technical owner** — CIO or Head of Engineering Platforms; owns the runtime, the SLOs, and the bill.
3. **Gatekeeper stack** — CISO, Chief Risk Officer, Chief Compliance Officer, Data Protection Officer; any one of them can stop the deal in InfoSec or third-party-risk review.
4. **Procurement and Legal** — runs the third-party-risk-management intake and the licence redline.

The top deal-killer in 2026 is the third-party-risk-management (TPRM) function, driven by three independent regulator actions. NYDFS Industry Letter of 21 October 2025 binds covered entities to AI-specific contractual requirements on third-party AI use, training-data limits, sub-processor disclosure, and exit obligations. DORA Articles 28–30 (EU) mandate a Register of Information with seven required fields per ICT provider plus explicit concentration-risk management. Supervisory Letter SR 26-2 (17 April 2026) excludes generative and agentic AI from Model Risk Management scope.

The consequence: the veto moves from model-risk reviewers to TPRM, operational-risk, and cyber reviewers. The platform must satisfy that group, not the first.

## Why now

Four forcing functions converge in 2026. DORA enforcement has been active in the EU since 17 January 2025, with 2026 the first full year of supervisory action and fines up to 2% of global turnover. NYDFS Letter of 21 October 2025 binds covered entities to AI-specific TPRM clauses. The EU AI Act Annex III high-risk obligations are deferred to 2 December 2027 (standalone) and 2 August 2028 (product-embedded) under the Digital Omnibus agreement of 7 May 2026 — the procurement window is open and narrow, not closed. IBM Cost of a Data Breach 2025 puts shadow-AI breach cost at $4.63M average ($670K premium over baseline); 97% of AI-breach victims lacked basic AI access controls. BCG's 2025 retail-banking report puts at-scale AI adoption at ~10%, with 75% of banks still experimenting.

## Positioning thesis

Wide-Moat assembles an in-perimeter agentic AI ecosystem and sells it as a deployable subscription with enablement and certification. Every component runs entirely inside the customer's perimeter (including the agent loop, the context store, and the recovery logic — not only the tool-execution sandbox). The platform is model-agnostic by construction (MCP-first, no hosted loop); SOC 2 Type II, ISO 27001, DORA Article 28–30, and EU AI Act Annex III evidence ships as first-class build artifacts on every release. The licence is FSL-1.1-Apache-2.0 with a planned `LICENSE-ADDITIONAL-PERMISSIONS.md` instrument (tracked in issue `arch/additional-permissions-instrument`; drafted in the research buffer; lands at repo root and in §05 once that section is written) enumerating internal-use scope for affiliates, joint ventures, outsourced operators, single-tenant managed deployments, and internal white-labelling; reselling as a competing multi-tenant SaaS remains forbidden during the FSL term (including by Wide-Moat itself), with each release converting to Apache 2.0 two years after publication per the License's Future License Grant.

In-perimeter deployment alone is no longer a moat. UiPath Automation Suite shipped on-prem agentic AI on 5 May 2026 under a commercial closed-source EULA; Anthropic shipped self-hosted sandboxes on 19 May 2026 with the agent loop, context, and model weights kept on Anthropic infrastructure. The remaining moat is the intersection of model-neutrality, source availability, fully in-perimeter execution (loop included), and per-release compliance evidence. These are bundle properties: the loop and model-neutrality come from sibling components (Open WebUI / n8n / LiteLLM); Open Computer Use — the component these architecture docs design — contributes the in-perimeter tool-execution sandbox and the tamper-evident audit lineage, and does not run the loop or proxy a model. Re-evaluates on 2027-05-24.

## Open questions

1. Is "CAIO is the modal sponsor" true at JPMorgan, Goldman Sachs, and Morgan Stanley, where AI strategy currently runs through existing CTO/COO structures? Track in issue `arch/caio-modal-sponsor-validation`.
2. What is the actual procurement experience of FSL-1.1-Apache-2.0 plus the Additional Permissions instrument in three or more tier-1 customers? Track in issue `arch/fsl-procurement-evidence`.
3. Does "first-class build artifact" for compliance evidence mean a signed bundle per release, a continuously-updated portal, or both? Track in issue `arch/thesis-evidence-bundle`.
4. Does "model-agnostic by construction" extend to embedding and rerank models, or only generation models? Track in issue `arch/modelprovider-scope`.
5. Public-sector and academic-consortium deployments need a §8 in the Additional Permissions instrument or bilateral side letters; which? Track in issue `arch/additional-permissions-edge-cases`.
