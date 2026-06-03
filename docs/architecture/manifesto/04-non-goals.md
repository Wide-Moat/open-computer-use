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

**Hosting models and orchestrating the agent loop.** OCU does not host, proxy, or select an LLM, and orchestrates no loop of its own (multi-turn reasoning, reflection, tool-use selection). The loop belongs to its owner: the calling client — a sibling component such as Open WebUI, n8n, or LiteLLM, or any MCP caller — or a workload the customer runs inside the sandbox, such as their own coding agent. OCU is an MCP server plus a sandbox executor: it terminates tool-call requests and executes them in isolation. Either way, a workload or tool that needs an LLM reaches it as one allow-listed egress endpoint under the Egress trust-edge, broker, and audit path ([03-non-negotiables.md](03-non-negotiables.md)), never through an OCU model abstraction. The sandbox is a leaf in the runtime tree: a workload inside it runs its own loop but cannot spawn a container or a nested sandbox.

**Admin web UI.** v1 ships no operator console. Operator functions — session lifecycle, quota, denylist, audit review — run over the CLI (`occ`) and GitOps config. Every UI is new attack surface (CSRF, XSS, broken auth), accessibility burden, and localization cost. The end-user data-plane surface (file upload/download, preview, artifact render, transcript display) is in scope and serves end-user visibility, not operator control ([NFR-SEC-82](02-nfrs.md)). v2 may add a read-only operator console once the CLI is feature-complete and customers ask.

**SaaS offered by us.** FSL-1.1-Apache-2.0 forbids offering OCU (or a modified version) on a hosted or embedded basis that competes with a paid version ([05-licensing-posture.md](05-licensing-posture.md)). We ship self-hostable software only; the limitation lifts per-release on the two-year Apache-2.0 conversion.
