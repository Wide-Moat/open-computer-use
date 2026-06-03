<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: draft
last-reviewed: 2026-06-02
owner: "@Wide-Moat/architects"
applies-to: next/v1
---

Principles every architectural decision must respect. Audience: reviewers and architects deciding whether a proposal fits the platform.

## Non-negotiable principles

**Agent loop stays outside OCU.** The loop — model query, response handling, reflection — runs in the calling client, never in OCU. Anti-example: OCU as an LLM proxy that selects the model and runs the tool-execution loop internally.

**Model agnostic by construction.** OCU does not host, select, or provision LLMs; the model choice is the caller's. A sandbox tool that needs an LLM reaches it as one allow-listed egress endpoint, governed by the Egress trust-edge like any other upstream. Anti-example: a default bundled model or a model-selection API.

**Guest holds no long-lived upstream secret.** The sandbox never holds a credential that reaches a backend outside OCU (storage, SDS, KMS, LLM); a session-scoped handle is acceptable, the upstream key stays host-side and injects at the trust-edge only ([NFR-SEC-23](02-nfrs.md), [ADR-0007](../adr/0007-egress-auth-mechanism.md)). Anti-example: the guest receiving an object-store access key or a hardcoded API token.

**Kill-switch and lifecycle mutation are unreachable from the agent path.** Session revoke, quota kill, and denylist mutation have no network route from the path that carries tool-call execution; the non-reachability is a network-policy invariant ([NFR-SEC-52](02-nfrs.md)), not an in-process route guard. The revoke itself enforces as an in-process denylist check on every Compute-plane RPC ([02-trust-boundaries.md](../02-trust-boundaries.md) §7), propagated platform-wide within ≤5 min ([NFR-SEC-04](02-nfrs.md)). Anti-example: an agent-callable RPC that revokes its own session.

**One-click solo install holds at every rung.** The minimal shelf — single operator, self-signed CA, file-system audit, `runc` — runs from one `docker-compose up` with no external service, no cloud credential, and no pre-staged key ([NFR-FLEX-15](02-nfrs.md)). Opt-in compliance machinery layers on top; it never becomes a prerequisite for the first session. Anti-example: requiring IdP enrollment or external-vault integration before a session can run.

**Audit events are immutable and hash-linked.** The OCSF event stream is written once, never modified, and hash-chained so tampering is detectable ([NFR-SEC-03](02-nfrs.md)); the audit-write is on the critical path of a privileged action, fail-closed. Anti-example: audit in a mutable store with no hash chain.

**Compliance evidence ships with every release.** Each release carries its attestations as build artifacts — signed SBOM, SLSA provenance, threat-model traces, control mappings — not a sales document assembled on demand. Anti-example: evidence generated retroactively under audit pressure.

**Skill registry is deferred, not invented now.** v1 ships zero bundled default skills; the `SkillProvider` abstraction stays `status: tbd` and skills load from a customer-provided registry over a stable contract ([04-non-goals.md](04-non-goals.md)). Anti-example: shipping a half-baked built-in skill format in v1 that locks customers in.

**No hosted SaaS from us.** FSL-1.1-Apache-2.0 forbids offering OCU on a hosted or embedded basis that competes with a paid version, until the per-release Apache-2.0 conversion ([05-licensing-posture.md](05-licensing-posture.md)). We ship self-hostable software. Anti-example: a managed OCU cloud service.

**The wire surface is versioned and changes additively.** The Control-plane RPC and the OCSF Published Language are versioned; a breaking change needs a major version and a deprecation window, CI-enforced ([NFR-IC-04](02-nfrs.md), [08-contracts.md](../08-contracts.md) §4). The MCP edge is a Conformist to the MCP spec and versions by date-revision negotiation, not semver. Anti-example: silently changing the operator REST response shape between releases.
