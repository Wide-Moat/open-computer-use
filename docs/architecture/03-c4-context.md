<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: draft
last-reviewed: 2026-05-30
owner: "@Wide-Moat/architects"
applies-to: next/v1
---

## 1. Purpose

Names every external boundary OCU speaks across, for architects and security engineers integrating it with the customer's IdP, KMS, SIEM, and outbound proxy. OCU is the in-perimeter tool-execution boundary — a uniform sandbox with a skill library, exposed over MCP; the calling client runs the agent loop and owns the model choice, and OCU executes the tool-calls it receives.

OCU is one component of the Wide-Moat opinionated bundle (other peers in the bundle include n8n and Open WebUI). OCU is also usable standalone — any MCP-speaking peer is a first-class integration. See [`manifesto/01-audience-and-buyer.md`](manifesto/01-audience-and-buyer.md) for the buyer story; this document scopes only what is inside OCU and what it talks to.

## 2. Inside the box

OCU is the tool-execution component: MCP server / Control plane → guest agent → sandbox runtime → Egress trust-edge + Credential broker + Audit pipeline ([`02-trust-boundaries.md`](02-trust-boundaries.md) §1). The guest agent is OCU's in-sandbox executor. Internal decomposition is out of scope at this layer.

## 3. C4 Context diagram

Canonical source: [`diagrams/c4-context.mmd`](diagrams/c4-context.mmd). Convention: solid border = present on the minimal-capability shelf; dashed border = not on the minimal shelf by default. Palette borrows the project red-untrusted / green-trusted convention; semi-trusted (amber) and isolated (blue) zones from the trust-boundary diagram do not apply at the Context level. The solid / dashed split makes the one-click solo-install path visible at a glance — solid-border actors are what a solo install talks to out of the box; dashed-border actors are wired on the full-capability shelf, some optional (SIEM, proxy, ICAP, SOAR, transparency log) and some required there (IdP). Per-actor optionality is stated exactly in the §4 table. Internal containers are not shown here.

## 4. External actors

The boundary-crossing actors are defined canonically in [`02-trust-boundaries.md`](02-trust-boundaries.md) §3. This view groups them by role and marks per-actor optionality; exact required/optional status is in the §4 table below.

| Actor | Role | Required-or-optional | NFR anchor |
|---|---|---|---|
| **MCP-speaking peer** (n8n, Open WebUI, custom MCP client) | Inbound calls into OCU's MCP server | required | — |
| **Admin / Operator** (PAM-JIT human) | Operates OCU; host-rooted local credential on the minimal shelf, short-lived SAML-asserted attribute on the full shelf — no shared service accounts on either | required | [NFR-COMP-29](manifesto/02-nfrs.md) |
| **Customer IdP** (SAML / OIDC) | Authenticates inbound peers and operators on the full shelf; OCU is a relying party | not on the minimal shelf (operators use a host-rooted local credential) — required on the full-capability shelf | — |
| **Customer SIEM** | OCSF v1.x event bridge consumed by the customer's SIEM | optional on minimal shelf (file-system sink); required where SIEM is the system of record | [NFR-MAINT-AUDIT-SCHEMA](manifesto/02-nfrs.md) |
| **Customer KMS / HSM** | Key custody for the broker and audit signing chain on the full-capability shelf | optional — full shelf only; minimal shelf uses host-local keys | [NFR-FLEX-04](manifesto/02-nfrs.md) |
| **Customer outbound proxy** | Chained-proxy hop for egress; OCU's trust-edge proxy speaks the chained contract | optional | — |
| **Customer DLP-ICAP service** | ICAP req-mod / resp-mod hook inside the MITM-inspecting egress mode | optional — engaged only in MITM mode | [NFR-COMP-28](manifesto/02-nfrs.md) |
| **SOAR** (incident automation) | Bidirectional: signed webhook from OCU on alert, admin API back for revoke | optional | — |
| **Transparency log** | Daily Merkle-head submission for tamper-evident audit | optional — choose public or customer-private | [NFR-SEC-03](manifesto/02-nfrs.md) |

Regulator citations and measurable targets for each row land in [`manifesto/02-nfrs.md`](manifesto/02-nfrs.md), not here.

Outbound endpoints behind the egress policy (LLM upstream, customer MCP servers, object stores, internal APIs) are not actors against OCU's contracts — the Egress trust-edge gates them and the Credential broker selects the scoped token ([`02-trust-boundaries.md`](02-trust-boundaries.md) §3 preamble).

Humans drive OCU only through an MCP-speaking peer (e.g. Open WebUI, n8n, or a custom client); direct human-to-OCU UI is a v1 non-goal.

## 5. Scope out

- **Workflow orchestration** — peers like n8n call OCU as an MCP client; they live in their own repos.
- **Chat surface** — peers like Open WebUI call OCU as an MCP client; they live in their own repos.
- **Hosted LLM serving, model selection, and the agent loop** — the calling client owns all three. If a sandbox tool needs an LLM, it reaches it as one allow-listed egress endpoint, not through OCU.
- **Skill registry and skill-pack catalog** — v1 non-goal; `SkillProvider` abstraction reserved.
- **Admin web UI** — v1 non-goal; CLI (`occ`) + GitOps + Grafana cover operations.
- **AI-guardrail / prompt-content policy** — customer's AI gateway, not OCU ([`02-trust-boundaries.md`](02-trust-boundaries.md) §2 zone 4).

## 6. Open questions

1. Bundling status of n8n and Open WebUI on `next/v1` — [#154](https://github.com/Wide-Moat/open-computer-use/issues/154) — Wide-Moat bundle composition is open; Layer 4 names the integration shape but does not lock the packaging.
