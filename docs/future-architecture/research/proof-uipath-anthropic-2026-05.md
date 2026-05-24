---
status: research
last-reviewed: 2026-05-24
owner: nick
applies-to: next/v1 positioning thesis (§01 widemoat)
---

Primary-source verification of two May 2026 launches that the Wide-Moat positioning thesis treats as load-bearing: UiPath's on-prem agentic AI (5 May 2026) and Anthropic's self-hosted sandboxes + MCP tunnels (19 May 2026).

## Claim 1: UiPath on-prem agentic AI (5 May 2026)

Primary sources:
- Press release (IR site): https://ir.uipath.com/news/detail/446/uipath-automation-suite-delivers-on-premises-agentic-ai-for-the-public-sector
- Newsroom mirror: https://www.uipath.com/newsroom/uipath-automation-suite-delivers-agentic-ai-for-public-sector
- BusinessWire syndication: https://www.businesswire.com/news/home/20260505017359/en/
- Platform page (general, not release-specific): https://www.uipath.com/platform/agentic-automation

Product: UiPath Automation Suite, with UiPath Maestro as the agentic control plane plus Agent Builder, GenAI Activities, and context grounding. Positioned at public sector and regulated industries.

Confirmed ship date: 5 May 2026. Conversational Agent and IXP capabilities slated for October 2026.

Deployment model: customer-controlled infrastructure on AWS, Microsoft Azure, OpenShift, or self-hosted data centres. Press release confirms air-gap is supported: "Agencies can run recommended open-source models entirely within their own data centers...without external dependencies."

Agent loop location: orchestration via Maestro runs inside the customer's Automation Suite cluster. LLM calls either egress to OpenAI / Google Gemini / Anthropic or hit a self-hosted open-source model inside the same perimeter. Recommended open-source model list not named in the release.

Licence terms: not disclosed in the release. Automation Suite has historically been commercial closed-source per-user / per-robot under a UiPath EULA; the May 2026 release adds capabilities, it does not change the licensing model. No SBOM, source mirror, or OSS components called out.

Pricing model: not disclosed. Existing Automation Suite contracts are enterprise-license, named-user plus unattended-robot capacity, negotiated. No public price list.

Gap vs Wide-Moat target: UiPath ships RPA-shaped agents (workflow orchestration, document/IXP, GenAI activities inside Studio); it does not ship a generic in-perimeter Computer Use harness (browser + desktop + terminal driven by a vision-LLM loop) with MCP-native skills, model-provider neutrality at the harness layer, and FSL-style source-available licensing. The licence is closed and the unit of work is "automation" not "agent session inside a per-task microVM." Compliance posture (ISO/IEC 42001, FedRAMP, AIUC-1) covers the platform but is not the same as shipping per-deployment compliance evidence templates.

## Claim 2: Anthropic self-hosted sandboxes + MCP tunnels (19 May 2026)

Primary sources:
- Announcement: https://claude.com/blog/claude-managed-agents-updates
- Agent SDK hosting docs: https://code.claude.com/docs/en/agent-sdk/hosting (redirected from docs.claude.com)
- Trade-press confirmation: https://www.infoq.com/news/2026/05/claude-mcp-tunnels/

Product: two features added to Claude Managed Agents on the Claude Platform — self-hosted sandboxes and MCP tunnels. Announced at the Code with Claude London event.

Confirmed ship date and status: 19 May 2026. Self-hosted sandboxes are in public beta. MCP tunnels are in research preview, request-access only.

Customer-hosted vs Anthropic-hosted split:
- Customer-hosted: tool execution sandbox (own infra or via Cloudflare, Daytona, Modal, Vercel), runtime image, network policy, audit logging; for MCP tunnels also a lightweight outbound gateway and the private MCP server.
- Anthropic-hosted: agent loop (orchestration, context management, error recovery), model weights, context store, tunnel termination on the Anthropic side. Verbatim from the announcement: "The agent loop that handles orchestration, context management, and error recovery stays on Anthropic's infrastructure, while tool execution moves to your own configured environment."

Licence terms for customer-installed components: the announcement does not state a licence for the sandbox runtime, gateway agent, or SDK. The Agent SDK is distributed via PyPI / npm and bundles a native Claude Code binary. Source-availability and licence of that binary are not declared on the hosting docs page. No SBOM linked from the release.

Closed-weights confirmation: yes, weights stay on Anthropic. The customer-side runtime only egresses to api.anthropic.com per the SDK docs ("Outbound HTTPS to api.anthropic.com"). Weights are never shipped into the customer perimeter.

Gap vs Wide-Moat target: this is a Claude-only path. The agent loop, weights, context, and recovery logic remain on Anthropic SaaS; banks that need full-perimeter operation (no outbound LLM API call, no Anthropic-side context retention) cannot use it. There is no multi-provider story (OpenAI / Bedrock / Vertex / vLLM cannot drive these sandboxes), no source-available harness, no shipped compliance-evidence templates for the customer to hand to InfoSec.

## Side-by-side comparison

| Dimension | UiPath Automation Suite (5 May 2026) | Anthropic Claude Managed Agents (19 May 2026) | Wide-Moat target (next/v1) |
|---|---|---|---|
| Deployment model | On-prem / private-cloud / air-gap on AWS, Azure, OpenShift | SaaS agent loop + customer-side sandbox (beta) + outbound MCP tunnel (research preview) | Fully in-perimeter incl. agent loop |
| Agent loop location | Customer infra (Maestro) | Anthropic infra | Customer infra |
| Model location | Customer choice: cloud API or self-hosted OSS | Anthropic only, closed weights | Customer choice, model-provider neutral |
| Licence | Commercial closed-source EULA | Closed SaaS; SDK licence undeclared in release | FSL-1.1-Apache-2.0, source-available |
| Compliance evidence | ISO/IEC 42001, FedRAMP, AIUC-1 (platform-level) | Anthropic SOC 2 / ISO; customer-side scope only | Per-deployment evidence templates (planned) |
| Multi-provider LLM | Yes (OpenAI, Gemini, Anthropic, self-hosted) | No (Claude only) | Yes |
| MCP-native | Not advertised | Yes, but via tunnel to Anthropic SaaS | Yes, fully in-perimeter |

## Verdict on the load-bearing claim

The original §01 wording — that the "in-perimeter Computer Use sole moat" is broken — is over-read. UiPath's release is real on-prem agentic AI but it targets RPA workflows under a closed commercial licence; it does not deliver a generic Computer Use harness or a source-available stack. Anthropic's release moves only the sandbox and MCP transport inside the customer perimeter; the agent loop, context, and weights remain Anthropic SaaS, which is exactly what bank InfoSec rejects. Corrected wording for §01: "By May 2026 the major vendors had partial in-perimeter answers — UiPath shipped closed-source on-prem RPA agents, Anthropic shipped a customer-side sandbox while keeping the agent loop on its SaaS — but neither shipped a model-neutral, source-available, fully in-perimeter Computer Use harness with per-deployment compliance evidence. That is the remaining moat."

## Open questions / things I could not verify

1. UiPath Automation Suite 2026 licence text and SBOM availability — searched the press release, newsroom, and product page; pricing and licence terms are gated behind sales contact, no public EULA URL found.
2. Licence of the customer-installed Anthropic sandbox runtime and MCP tunnel gateway — checked the announcement and the Agent SDK hosting docs; neither states an OSI licence for the gateway binary or the bundled Claude Code binary. Could not confirm whether the gateway is reproducible or signed.
3. Whether MCP tunnels' research-preview customers can disable Anthropic-side context retention end-to-end — checked the announcement and InfoQ; the split is described at the tool-execution boundary, retention/audit posture of the Anthropic-side context store under tunnel mode is not documented publicly.
