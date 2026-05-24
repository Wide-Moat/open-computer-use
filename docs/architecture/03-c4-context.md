<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: draft
last-reviewed: 2026-05-25
owner: "@Wide-Moat/architects"
applies-to: next/v1
---

## 1. Purpose

Open Computer Use (OCU) is a uniform in-perimeter sandbox with a skill library and an MCP interface — users build automations once, delegate them to agents, and scale them across a team without leaving the safety boundary. The platform is model-neutral by construction (any model with tool-call over MCP) and integrates with the customer's existing IdP, KMS, SIEM, and outbound proxy; this view names every external boundary the system speaks across.

OCU is a part of the Wide-Moat opinionated bundle (which also ships peers like n8n and Open WebUI as one curated stack), and it is usable standalone — any MCP-speaking peer is a first-class integration. See [`manifesto/01-audience-and-buyer.md`](manifesto/01-audience-and-buyer.md) for the buyer story; this document scopes only what is inside OCU and what it talks to.

## 2. Inside the box

OCU is the agent-execution component: MCP server / Control plane → guest agent → sandbox runtime → Egress trust-edge + Credential broker + Audit pipeline ([`02-trust-boundaries.md`](02-trust-boundaries.md) §1). Internals are decomposed in Layer 6 (Container).

## 3. C4 Context diagram

Canonical source: [`diagrams/c4-context.mmd`](diagrams/c4-context.mmd). Convention: solid border = required; dashed border = optional configuration. Palette matches the trust-boundary diagram (red untrusted / amber semi-trusted / green trusted / blue isolated). Internal containers are NOT shown here — see Layer 6.

## 4. External actors

The boundary-crossing actors are defined canonically in [`02-trust-boundaries.md`](02-trust-boundaries.md) §3. This view groups them by role and marks per-actor optionality so the one-click solo install path is visible at a glance.

| Actor | Role | Required-or-optional | Spec link |
|---|---|---|---|
| **MCP-speaking peer** (n8n, Open WebUI, LLM upstream, custom) | Inbound calls into OCU's MCP server; REST is a fallback for non-MCP callers | required | [`02-trust-boundaries.md`](02-trust-boundaries.md) §3 row "MCP client" |
| **Admin / Operator** (PAM-JIT human) | Operates OCU; short-lived SAML-asserted attribute, no shared service accounts | required | [`02-trust-boundaries.md`](02-trust-boundaries.md) §3, [NFR-COMP-29](manifesto/02-nfrs.md) |
| **Customer IdP** (SAML / OIDC) | Authenticates inbound peers and operators; OCU is a relying party | required on full-capability shelf | [`02-trust-boundaries.md`](02-trust-boundaries.md) §3 |
| **Customer SIEM** | OCSF v1.x event bridge from the audit pipeline | optional on minimal shelf (file-system sink); required where SIEM is the system of record | [`02-trust-boundaries.md`](02-trust-boundaries.md) §3, [NFR-MAINT-AUDIT-SCHEMA](manifesto/02-nfrs.md) |
| **Customer KMS / HSM** | Key custody for the broker and audit signing chain on the full-capability shelf | optional — full shelf only; minimal shelf uses host-local keys | [`02-trust-boundaries.md`](02-trust-boundaries.md) §3, [NFR-FLEX-04](manifesto/02-nfrs.md) |
| **Customer outbound proxy** | Chained-proxy hop for egress; OCU's trust-edge proxy speaks the chained contract | optional | [`02-trust-boundaries.md`](02-trust-boundaries.md) §3 |
| **Customer DLP-ICAP service** | ICAP req-mod / resp-mod hook inside the MITM-inspecting egress mode | optional — engaged only in MITM mode | [`02-trust-boundaries.md`](02-trust-boundaries.md) §3, [NFR-COMP-28](manifesto/02-nfrs.md) |
| **SOAR** (incident automation) | Bidirectional: signed webhook from OCU on alert, admin API back for revoke | optional | [`02-trust-boundaries.md`](02-trust-boundaries.md) §3 |
| **Transparency log** | Daily Merkle-head submission for tamper-evident audit | optional — choose public or customer-private | [`02-trust-boundaries.md`](02-trust-boundaries.md) §3, [NFR-SEC-03](manifesto/02-nfrs.md) |

Outbound endpoints behind the egress policy (LLM upstream, customer MCP servers, object stores, internal APIs) are not actors against OCU's contracts — the Egress trust-edge gates them and the Credential broker selects the scoped token ([`02-trust-boundaries.md`](02-trust-boundaries.md) §3 preamble).

## 5. Scope out

- **Workflow orchestration** — peers like n8n call OCU as an MCP client; they live in their own repos.
- **Chat surface** — peers like Open WebUI call OCU as an MCP client; they live in their own repos.
- **Hosted LLM serving** — model-neutral by construction; customer plugs in their model of choice over MCP tool-call.
- **Skill registry and skill-pack catalog** — v1 non-goal; `SkillProvider` abstraction reserved.
- **Admin web UI** — v1 non-goal; CLI (`occ`) + GitOps + Grafana cover operations.
- **AI-guardrail / prompt-content policy** — customer's AI gateway, not OCU ([`02-trust-boundaries.md`](02-trust-boundaries.md) §6).

## 6. Open questions

1. Bundling status of n8n and Open WebUI on `next/v1` — [#154](https://github.com/Wide-Moat/open-computer-use/issues/154) — Wide-Moat bundle composition is open; Layer 4 names the integration shape but does not lock the packaging.
