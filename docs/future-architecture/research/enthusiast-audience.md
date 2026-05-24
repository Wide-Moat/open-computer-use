<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: draft
last-reviewed: 2026-05-24
owner: nick
applies-to: docs/architecture/manifesto/01-audience-and-buyer.md
---

Research brief for the secondary (solo enthusiast) audience of `next/v1`; input to Manifesto §01.

## Is the OSS to enterprise funnel real for self-hostable infra?

Evidence is genuine but uneven. Three patterns dominate.

**Funnel works when the OSS product is the same engine as the paid product.** Sentry: self-hosted free version drove top-of-funnel; major customers (Instacart, GitHub, Disney, Atlassian, Reddit, Slack) started self-hosted, then bought hosted as scale made DIY uneconomic. Self-serve is ~70% of revenue as of May 2024 (4M developers, 90K orgs).<sup>[1]</sup> Sentry's FSL license is the direct precedent for this repo's license choice.

**Funnel works when bottom-up adoption produces internal champions.** HashiCorp Vault and Terraform — Community Editions onboard practitioners; HCP/Enterprise upsell triggers at the governance / scale / risk boundary. HashiConf 2024 explicitly markets a "Terraform migrate" beta to move CE workflows into HCP.<sup>[2]</sup> dbt followed the same shape: 5+ years of free `dbt Core` adoption, then dbt Cloud crossed $100M ARR by 2024 (Fortune 500 adoption +85% YoY).<sup>[3]</sup> Grafana: 25M users feed 5,000+ paying customers (Bloomberg, Citigroup, Dell, Salesforce); $6B valuation in 2024.<sup>[4]</sup>

**Funnel breaks when you cut off the free engine.** Buoyant stopped publishing stable Linkerd binaries for orgs >50 employees in February 2024. The 2024 CNCF Annual Survey shows service-mesh adoption fell from 50% to 42% YoY despite Kubernetes climbing to 93%.<sup>[5]</sup> Buoyant's own velocity rebounded (IPv6, Gateway API, post-quantum shipped within 18 months), so the company survived — but the *community funnel* did not. This is the cautionary anchor for any decision to gate features behind the paid tier.

For Computer Use specifically: Coder.com (self-hostable workspaces with developer-first DX, then enterprise governance) is the closest live analog and the most relevant funnel shape to copy.<sup>[6]</sup>

## Personas for in-perimeter Computer Use platform

Ranked by v1 relevance.

| Rank | Persona | What they contribute |
|------|---------|----------------------|
| 1 | Indie agent builder | Evals, bug reports, novel skill recipes, public writeups that bank InfoSec then forwards internally |
| 2 | Internal-IT / platform team at non-bank SMB | Real-world deployment friction; same threat model as enterprise just smaller; revenue path via mid-market |
| 3 | OSS maintainer / contributor | Code, integrations (LangChain/Dify/Haystack adapters), MCP server contributions |
| 4 | Privacy-focused self-hoster (Nextcloud/Immich crowd)<sup>[7]</sup> | Hardening reports, default-closed advocacy, attack-surface audits — directly aligned with bank threat model |
| 5 | AI researcher / grad student | Reproducible evals, paper citations, novel agent recipes |
| — | Solo SaaS founder | DROP. The license forbids competing hosted services — this persona is a license violation by definition |

Bank-employed staff engineers exploring at home read as Persona 1 or 4 by behaviour; they sit inside the enterprise funnel by employer.

## Domain-expert DX patterns that make OSS docs delightful

- **Stripe three-column layout**<sup>[8]</sup>: persistent nav | concept | runnable curl/SDK side-by-side. Hover synchronises prose and code. Result: zero context-switch from "what is this" to "paste this". For our docs: every `getting-started/` page exposes a runnable command in the right gutter; reference docs show the YAML and the CLI invocation together.
- **Rust Book pull-model teaching**<sup>[9]</sup>: direct "you" address, explicit "skip ahead if you want", deliberate non-compiling examples with the exact compiler error printed. The book teaches *how to read errors*, not how to avoid them. For our docs: include the failure path for every happy path — what the audit log shows when policy denies, what the CLI returns when SCIM fails.
- **FastAPI auto-generated correctness from types**<sup>[10]</sup>: the OpenAPI spec is generated from Python type hints; docs cannot drift from code because they are the same artifact. For our docs: the Helm `values.yaml` reference, OpenAPI for the broker API, and CLI `--help` are all generated, never hand-edited.
- **Fly.io EffortPost format**<sup>[11]</sup>: bold lede, 2000+ words, runnable code, claims defended with measurements. Fly is moving away from optimising every post for HN — the format still works for one-shot deep dives (e.g. the threat-model walkthrough, the audit-trail design post).
- **Tailwind reference docs**<sup>[12]</sup>: every utility documented with the exact CSS it generates and a copy button. Equivalent for us: every NFR scenario in the manifesto shows the measurable target *and* the test command that verifies it.

Stripe/Rust/FastAPI/Fly all share one trait that distinguishes them from corporate ISMS docs: prose paragraphs are short, every claim is verifiable, no marketing voice.

## Tensions between bank and enthusiast requirements

| Tension | Resolution mechanism in v1 |
|---------|----------------------------|
| Image tags (mutable `latest` for hacking; pinned + cosign for procurement) | Publish both. `:edge` for enthusiasts, `:vX.Y.Z` + signed digest for banks. Documented in release notes. |
| IdP (Keycloak/Entra mandatory vs none-at-all) | `auth.mode: local` env flag ships local-only with single admin token; `auth.mode: oidc` enforces SCIM/SAML. Default in Helm chart: `oidc`; default in Compose quickstart: `local`. |
| Audit sinks (Splunk/QRadar vs filesystem) | `audit.sink` interface with `filesystem`, `syslog`, `splunk-hec`, `qradar` implementations. Filesystem ships with the repo; the rest are integration docs. |
| Threat-model placement (visible vs hidden) | Diátaxis split absorbs: `docs/architecture/security/threat-model.md` for bank InfoSec; `docs/getting-started/security-defaults.md` for enthusiast (one screen, "these are the defaults that protect you"). |
| Support model | Bank-only contract. No tension — enthusiasts get GitHub issues + community Discord, banks pay for SLA. State this once in the manifesto, not on every doc page. |
| Doc voice | Diátaxis quadrant decides voice, not audience. `architecture/` and `compliance/` are reference + explanation (formal, NFR-style). `getting-started/`, `operating/`, `contributing/` are tutorial + how-to (direct "you", runnable). |
| Default-closed network posture | Default-closed everywhere. The enthusiast tradeoff is a one-line env override (`network.egress.mode: allow-localhost`) documented in `getting-started/local-development.md`. No special build, no soft default. |

The mechanism that does *not* work: a single doc that tries to address both audiences in alternating paragraphs.

## Cope-check: did anyone die from dual-audience?

The Authentik 2024 incident is the live cautionary tale.<sup>[13]</sup> A community PR to add an SSO source was rejected because SAML connections were in the paid tier. The community read this as "SSO is security tablestakes in 2024, you cannot gate it behind enterprise." Authentik responded with a blog post conceding the framing, then shipped SCIM/OAuth/SAML/Plex *source* mappings in 2024.8 to the open-source product. The lesson: *security primitives cannot be the paid moat for an OSS security product*. For Computer Use this means SCIM/SAML, audit-trail integrity, signed releases, and threat-model docs must all live in the OSS product; the moat is operational (managed deployment, paid SLA, certification packs), not capability.

Honest read on "dual audience": the constraint is load-bearing for licensing (FSL-1.1-Apache-2.0 only makes sense if enthusiasts can use it) and load-bearing for credibility (banks distrust OSS products with no real community), but it is *not* load-bearing for §01 of the Manifesto. §01 should name the primary buyer cleanly and treat the enthusiast as a downstream consequence of the licensing decision, not a co-equal persona in the buyer document. Treating it as co-equal is the procrastination risk.

## Domain-expert failure modes

Patterns where projects pretend to serve both audiences and serve neither:

1. **Marketing-tone README the bank rejects, dense ADRs the enthusiast skips.** A README opening with "industry-leading, battle-tested, enterprise-grade AI agents" signals to bank InfoSec that the project has no audit posture; signals to enthusiasts that it is vapourware. Banned vocab list in this repo's CLAUDE.md exists for this reason.
2. **Half-OSS / half-paid security primitives.** Authentik 2024 above. Any project where SSO, audit, or RBAC sits behind paywall loses the OSS community immediately and gains zero bank trust (banks read the same news).
3. **Quickstart that needs Kafka + Vault + Keycloak.** If the "5-minute getting started" requires the enterprise stack, no enthusiast tries it; the funnel never opens. Counter-pattern: Dify and n8n ship `docker compose up` with sane local defaults.<sup>[14]</sup>
4. **Threat model written as marketing.** "Defense in depth", "zero trust", "secure by design" with no DFD, no STRIDE table, no measured posture. Bank InfoSec discards on first read; enthusiast cannot tell what the defaults actually do.
5. **ADRs that mix decision with rationale with implementation.** Nygard format exists for a reason; bank reviewers grep for `Decision:` and bail when they cannot find it.

## What this means for Manifesto §01

1. State the primary buyer in one sentence: tier-1 US/EU bank InfoSec procuring an in-perimeter Computer Use platform.
2. State the licensing consequence next: FSL-1.1-Apache-2.0 means anyone can self-host, fork, and modify — therefore an OSS community exists and is a permanent part of the project's surface.
3. Frame the enthusiast as a *consequence of the license*, not a *co-primary persona*. One paragraph, not a parallel section.
4. List the four enthusiast contributions §01 expects: evals, hardening reports, MCP/skill contributions, public writeups. Tie each to a measurable feedback channel (GitHub issue label, eval submission, Discord channel).
5. Hard rule: security primitives (SCIM/SAML, audit integrity, signed releases, default-closed network, threat-model docs) are in the OSS product. The moat is operational, not capability. Cite Authentik 2024 as the anti-pattern. Cite Linkerd 2024 as the funnel-break anti-pattern.
6. Move audience-specific DX guidance out of §01 into a separate Manifesto entry on documentation discipline (already drafted as banned-vocab list in CLAUDE.md). §01 is "who and why", not "how we write".
7. Demote the solo SaaS founder persona explicitly — the license forbids that customer. Stating this in §01 prevents a recurring product-design argument.
8. End §01 with one anti-example: "We will not write a README that opens with marketing adjectives, because both audiences read the same first paragraph and both lose trust differently." This is the single sentence that operationalises dual-audience without giving it a co-equal section.

## Sources

[1] [Sentry self-serve funnel](https://research.contrary.com/company/sentry); [Sentry FSL licensing](https://open.sentry.io/licensing/)
[2] [HashiConf 2024 — Terraform migrate, CE to Enterprise](https://www.globenewswire.com/news-release/2024/10/15/2963222/0/en/HashiConf-2024-brings-community-and-customers-together-to-do-cloud-right-with-best-practices-for-cloud-infrastructure-automation.html); [HashiCorp CE→Enterprise strategy](https://medium.com/continuous-insights/from-oss-to-enterprise-when-hashicorp-terraform-and-vault-need-to-grow-with-you-f97d1048b8ef)
[3] [dbt Labs Snowflake / $100M ARR / source-available](https://www.runtime.news/dbt-labs-source-available-bet-pays-off-at-snowflake/); [dbt Core vs dbt Cloud framing](https://www.getdbt.com/blog/how-we-think-about-dbt-core-and-dbt-cloud)
[4] [Grafana Labs $6B valuation, 25M users, 5,000+ customers](https://research.contrary.com/company/grafana); [Grafana 2024 year in review](https://grafana.com/blog/open-source-at-grafana-labs-2024-year-in-review/)
[5] [Linkerd stable-binary policy change Feb 2024](https://www.buoyant.io/linkerd-vs-istio); [Service Mesh at a Crossroads — CNCF survey 50%→42%](https://cloudnativenow.com/features/service-mesh-at-a-crossroads-istios-graduation-and-the-road-ahead/)
[6] [Coder enterprise AI development infrastructure](https://coder.com/blog/coder-enterprise-grade-platform-for-self-hosted-ai-development); [Coder + Linkerd partner-of-year](https://coder.com/blog/coder-named-hashicorp-integration-partner-of-the-year-for-2024)
[7] [Immich + Nextcloud self-hoster persona](https://cloudbasedbackup.com/en/blog/nextcloud-vs-immich-choosing-the-right-self-hosted-photo-and-cloud-solution); [self-hoster trade-offs](https://bhaveshmishra.dev/blog/self-host-curse/)
[8] [Stripe docs teardown — three-column](https://www.moesif.com/blog/best-practices/api-product-management/the-stripe-developer-experience-and-docs-teardown/); [Stripe docs case study](https://ninadpathak.com/marketing-research/stripe-documentation-case-study/)
[9] [The Rust Programming Language — Introduction](https://doc.rust-lang.org/book/ch00-00-introduction.html); [Why Rust Docs Are the Gold Standard](https://medium.com/@syntaxSavage/why-rust-docs-are-the-gold-standard-and-every-language-should-copy-them-4ec8f1edc14b)
[10] [FastAPI OpenAPI auto-generation](https://fastapi.tiangolo.com/reference/openapi/docs/); [type-safe SDK generation from FastAPI](https://www.speakeasy.com/openapi/frameworks/fastapi)
[11] [Fly.io — A Blog, If You Can Keep It (EffortPost retrospective)](https://fly.io/blog/a-blog-if-kept/)
[12] [Tailwind CSS docs and IntelliSense](https://floatui.com/blog/tailwind-css-documentation-the-essential-guide)
[13] [Authentik response — Nov 2024](https://goauthentik.io/blog/2024-11-21-if-your-open-source-project-competes-with-your-paid-project/); [Authentik 2024.8 release shipping SCIM/SAML sources to OSS](https://docs.goauthentik.io/releases/2024.8/)
[14] [Self-hostable AI agent platforms 2025/2026 — n8n, Dify, Haystack](https://www.knowlee.ai/blog/self-hosted-ai-agent-platforms-2026); [Microsoft Agent Governance Toolkit](https://opensource.microsoft.com/blog/2026/04/02/introducing-the-agent-governance-toolkit-open-source-runtime-security-for-ai-agents/)
