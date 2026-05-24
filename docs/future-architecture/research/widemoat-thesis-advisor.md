---
status: research-buffer
last-reviewed: 2026-05-24
owner: positioning
applies-to: docs/architecture/manifesto/01-audience-and-buyer.md
---

# Wide-Moat positioning thesis — advisor

Advises the wording of `docs/architecture/manifesto/01-audience-and-buyer.md` after the
2026-05 market shifts (UiPath Automation Suite on-prem agentic AI on 5 May 2026; Anthropic
self-hosted sandboxes + MCP tunnels on 19 May 2026) invalidated the prior "doesn't exist"
framing.

## 1. Decision-summary table

| Frame | Defensibility (mo) | True May 2026? | Filters design? | Banned-vocab clean? | Buyer reaction | Enthusiast reaction | Obsolescence risk |
|---|---|---|---|---|---|---|---|
| 1. Current "doesn't exist" | 0 | No — UiPath + Anthropic both shipped | Weak (negative claim) | Yes | "Two press releases refute you" | "Outdated on day one" | Already obsolete |
| 2. Four-quadrant + named fifth | 9-12 | Yes | Medium (taxonomy guides, not constrains) | Yes (if "named fifth" not "best-in-class") | "Where is your category?" — needs analyst pickup | "Fair framing, see the gap" | High if a competitor adopts FSL |
| 3. Compliance-first (SOC 2 + ISO + DORA + EU AI Act) | 12-18 | Yes — no competitor maps all four with evidence on day 1 | Strong (every NFR traces to a control) | Yes | Direct InfoSec/procurement match | "Why I care: provable, not asserted" | Medium — UiPath catches up on docs |
| 4. License-first (FSL anti-SaaS) | 18-24 | Yes — unique stance | Weak (license rarely shapes code) | Yes | "Legal will read it. Engineering shrugs." | Strong (community trust) | Low (license is a moat by definition) |
| 5. Model-neutrality (MCP + DORA art. 28-30) | 12-15 | Yes — UiPath ties governance to its Maestro, Anthropic ties loop to its API | Strong (forces provider abstractions) | Yes | "Concentration-risk language we already use" | "Lock-in escape, technical" | Medium — Bedrock/Vertex shore up MCP support |
| 6. Combination: model-neutral + compliance-evidence (anchor) + in-perimeter + FSL (secondary) | 12-18 | Yes — each clause is independently verifiable | Strong (3 anchors → 3 NFR families) | Yes | Procurement/InfoSec/Legal all find their clause | Strong (technical + ethical anchors) | Medium — each clause ages differently |

## 2. Recommended frame and draft thesis

Recommended: **Frame 6 (combination)**, anchored on compliance evidence, with
model-neutrality and license as the supporting clauses. Reason: it survives both
near-term shocks already observed (UiPath shipping on-prem, Anthropic shipping
managed self-host) because neither competitor ships SOC 2 Type II + ISO 27001 + DORA
RoI fields + EU AI Act Annex III evidence in the artifact itself on day 1, and
neither one is fair-source.

Draft thesis (paste into §01 below the audience block):

> Wide-Moat ships an AI-agent platform for tier-1 EU and US banks that runs entirely
> inside the customer's perimeter, is model-agnostic by construction (MCP-first,
> no hosted loop), and emits SOC 2 Type II, ISO 27001, DORA Article 28-30, and EU AI
> Act Annex III evidence as first-class build artifacts. The license is
> FSL-1.1-Apache-2.0: customers may self-host, fork, and embed, but cannot resell
> the platform as a SaaS that competes with the vendor — a clause regulated buyers
> read as protection against their tooling becoming someone else's hosted product.

Three independently verifiable clauses. Zero banned words. No "comprehensive",
"robust", "seamless", "powerful", "best-in-class", "industry-leading", "modern",
"elegant", "battle-tested".

## 3. Cost of the discarded frames

- Frame 1: false on day of publication; one journalist kills the thesis.
- Frame 2: depends on analyst category creation we do not control.
- Frame 3 alone: a competitor that publishes a compliance pack overtakes us with a
  PDF, not a code change.
- Frame 4 alone: license is a legal moat, not a product moat; engineers do not buy
  a license, they buy a contract surface.
- Frame 5 alone: one MCP-ecosystem shift (e.g. Bedrock MCP gateway) collapses the
  differentiation.

## 4. Open questions (cap 3)

1. Does "first-class build artifact" mean a signed evidence bundle per release, or
   a continuously-updated portal? — track in issue `arch/thesis-evidence-bundle`.
2. Do we include FedRAMP Moderate in the compliance clause for v1 or defer to v2? —
   track in issue `arch/fedramp-v1-or-v2`.
3. Does "model-agnostic by construction" extend to embedding/rerank models, or
   only generation models? — track in issue `arch/modelprovider-scope`.

## 5. Adjacent moats — moat vs table stakes

| Asset | Classification | Why |
|---|---|---|
| FSL-1.1-Apache-2.0 anti-SaaS clause | Moat | Unique in this space; UiPath is commercial-closed, Skyvern is AGPL-3.0 |
| SOC 2 + ISO 27001 + DORA + EU AI Act evidence bundle | Moat (12-18 mo) | None of UiPath/Anthropic/Skyvern publish all four as artifacts |
| MCP-first model-agnostic abstractions | Moat (12-15 mo) | Anthropic's managed loop is API-locked; UiPath Maestro is Maestro-locked |
| Sandbox isolation (Firecracker / Kata path) | Table stakes | Anthropic uses Firecracker too; isolation is necessary, not sufficient |
| Skill registry (TBD-component) | Neither yet | Locked as v1 non-goal; becomes a moat only if a registry standard emerges |
| In-perimeter deployment | Was a moat in 2025 | Now table stakes after UiPath 2026-05-05 + Anthropic 2026-05-19 |
| Admin web UI absence | Neutral | Reduces attack surface; does not differentiate |

## 6. Moat clock — 12-18 months, then what?

Estimate: the recommended frame holds **12-18 months** before the compliance-evidence
clause becomes table stakes. Triggers that would shorten the clock:

- Anthropic publishes a SOC 2 + ISO 27001 + DORA evidence bundle for the Claude
  Managed Agents self-hosted-sandbox tier (plausible in 6-9 months).
- UiPath publishes a DORA RoI-aligned third-party-concentration-risk pack for
  Automation Suite (plausible in 9-12 months, already partial).
- Microsoft bundles Magentic-One into Azure Local with EU AI Act conformity
  assessment templates (12-18 months estimate, depends on Azure Local sovereign
  cloud rollout pace).

Architectural decisions to make **now** so the moat survives the clock:

1. **Evidence-as-code.** Compliance artifacts are generated from the same
   repository as the binaries: SBOM (Syft/SPDX, cosign-signed), SLSA L3 provenance,
   audit-event schema in `audit/` with one-to-one mapping to DORA Article 28-30
   register fields. ADR mandates this in Layer 0.
2. **`ModelProvider` abstraction enforced in CI.** No code path may import a
   provider SDK directly; all generation goes through the abstraction. Lint
   rule + integration test fails the build otherwise. Locks in
   model-neutrality before any one provider's roadmap warps the codebase.
3. **DORA RoI field-level traceability.** Every dependency added to the BoM
   carries the seven fields required for a DORA RoI row (provider name, country,
   subcontracting depth, function criticality, exit strategy, audit rights,
   data-residency). Reject-list captures dependencies that cannot supply these
   fields. Locked in `manifesto/05-licensing-posture.md`.
4. **EU AI Act Annex III conformity checklist in release pipeline.** Each GA
   release tags the Annex III risk categories the platform is configured for and
   blocks release if the corresponding controls (logging, human oversight,
   accuracy metrics, post-market monitoring hooks) are missing. Tracks to the
   2027-12-02 deadline with margin.
5. **MCP server allow-list as a first-class config.** Customer InfoSec controls
   which MCP servers the platform may reach; gateway enforces. Defends against
   the "Anthropic ships MCP tunnels, we lose differentiation" risk by making the
   policy boundary our artifact, not the transport.

Re-evaluate this thesis on 2027-05-24 (12-month checkpoint) and 2027-11-24
(18-month checkpoint). If two of the three clauses have become table stakes by
the first checkpoint, open a new ADR for thesis rotation.
