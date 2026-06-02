<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: draft
last-reviewed: 2026-06-02
owner: "@Wide-Moat/architects"
applies-to: next/v1
---

Features v1 defers, each with a clean abstraction boundary so a later milestone adds it without redesign. Audience: anyone proposing a feature for v1; the ADR path to reconsider is in [PROCESS.md](../PROCESS.md).

## Non-goals

**Skill registry.** v1 ships zero default skills. The `SkillProvider` abstraction stays `status: tbd` in the component set; skills load from a registry the customer supplies over a stable contract. v1 does not fix the skill metadata schema, the versioning rules, or the discovery protocol — inventing them now locks customers into a shape we have not proved.

**Hosted models and the agent loop.** OCU does not host, proxy, or select an LLM, and does not run the loop (multi-turn reasoning, reflection, tool-use selection); that lives in the calling client — a sibling component such as Open WebUI, n8n, or LiteLLM, or any MCP caller. OCU is an MCP server plus a sandbox executor: it terminates tool-call requests and executes them in isolation. A sandbox tool that needs an LLM reaches it as one allow-listed egress endpoint under the Egress trust-edge, broker, and audit path ([03-non-negotiables.md](03-non-negotiables.md)), never through an OCU model abstraction.

**Admin web UI.** v1 ships no operator console. Operator functions — session lifecycle, quota, denylist, audit review — run over the CLI (`occ`) and GitOps config. Every UI is new attack surface (CSRF, XSS, broken auth), accessibility burden, and localization cost. A read-only data-plane surface (file preview, artifact render, transcript display) is in scope and serves end-user visibility, not operator control ([NFR-SEC-82](02-nfrs.md)). v2 may add a read-only operator console once the CLI is feature-complete and customers ask.

**SaaS offered by us.** FSL-1.1-Apache-2.0 forbids offering OCU (or a modified version) on a hosted or embedded basis that competes with a paid version ([05-licensing-posture.md](05-licensing-posture.md)). We ship self-hostable software only; the limitation lifts per-release on the two-year Apache-2.0 conversion.
