<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-08-07
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
amends: ['0027-mcp-caller-static-api-key-auth.md']
compliance-impact: [SOC2-CC6.3, ISO27001-A.8.3, NYDFS-500.7, DORA-Art.28]
license-impact: none
threat-mitigation-link: ../components/01-mcp-gateway.md
---

Fixes where the gateway's per-action authorization policy lives, what a rule may say, and which arguments carry predicates — for anyone writing a deployment policy or the gate that reads it.

# ADR-0041: Gateway per-action authorization policy

## Status

`proposed` — amends [ADR-0027](0027-mcp-caller-static-api-key-auth.md), whose boot-loaded caller material this policy rides alongside. Closes roadmap gap D5 and the P1-E2 residual in [component 01](../components/01-mcp-gateway.md).

## Context

[NFR-SEC-49](../manifesto/02-nfrs.md) requires a deny-by-default decision keyed on the authenticated caller, the tool name, and the action parameters, taken before dispatch. Component 01 records per-action authorization as the accepted residual for P1-E2.

Two authorization layers ship today. A tool-name allowlist derived from the advertised tool list refuses a name the gateway does not serve, and a per-caller confinement binds one credential to `resolve_scope` alone. Neither reads an argument, and the second is one caller class hard-coded into the request path.

A threat-table residual records what is unmitigated; it does not waive an NFR carrying a measurable bar and live compliance mappings. The two artifacts read as a conflict only if the residual is taken for a decision.

The case for leaving it to the sandbox fails on one axis. A session is tenant-scoped, so two credentials of one tenant — an executing agent key and a view-only portal key — land in the same sandbox with identical authority. A distinction keyed on the caller is decidable only where the caller identity is resolved, which is the gateway. The shipped resolve-only confinement is already the first member of that class.

## Decision

We will enforce the gateway half of NFR-SEC-49 as a deny-by-default policy gate in the ingress boundary order, between the tool-name allowlist and the resolve step, so a denied call reaches neither the serializer nor Control and creates no session.

The policy is deployment-supplied, boot-loaded configuration on the same config plane as the boot credential set: a JSON document, strict-decoded against a closed schema under `contracts/`, rejecting unknown fields. It is never fetched from the Control plane at request time; the gateway-to-Control read edge stays forbidden.

The document defines named profiles, binds resolved caller ids to profiles, and names a default profile for unbound callers. A profile grants tool names from the advertised set only — a profile naming an unserved tool fails boot, the same no-drift rule the embedded tool list already carries. A tool absent from the bound profile is denied with a fixed reason class, and the refusal is durably recorded before the response, symmetric with the existing post-authentication refusals.

Argument predicates exist for exactly one key: the `path` of the file verbs. The predicate is an allowed absolute-prefix list compared after lexical normalization; a relative path or a `..` escape is denied before comparison, and a prefix matches only at a separator boundary. Globs and regular expressions are not policy syntax — a pattern language on agent-supplied input adds an evaluation surface at the one boundary that is meant to have none. The predicate is lexical: symlink and mount semantics are enforced by the sandbox mount plan, not here, and both halves are required.

`bash_tool.command` carries no content predicate. A command-pattern deny rule cannot meet this NFR's zero-red-team-pass criterion — quoting, encoding, and in-guest interpreters defeat any pattern set — so the per-action decision for that tool is the tool-class grant itself, and command effects are confined by the sandbox boundary. NFR-SEC-49 gains a clause stating the exclusion, so the row cannot be read as demanding a control that fails its own bar.

The shipped baseline policy is a committed file granting the advertised tools under the documented workspace prefixes. A deployment that supplies nothing runs today's surface under an auditable rule set rather than under an absence. A configured policy path that is missing or invalid fails boot; there is no silent fallback.

This mechanism supersedes the resolve-only caller list: the confinement becomes a `resolve_scope`-only profile, the existing environment syntax compiles to a caller binding, and the resolve-only tests migrate to the gate.

## Consequences

Deny-by-default is a property of the evaluator, not of the shipped rule set. The baseline is permissive and explicit, which is what keeps the one-click install alive; a deny-all default would ship a dead gateway, and an allow-all default would be the present hole wearing a policy file.

The gateway gains a boot-time failure mode it did not have. A deployment that mounts a malformed policy does not start, which is the intended direction for a component whose job is refusing calls.

Two enforcement points now bound a file verb, and neither is sufficient alone. The gateway decides on the requested path before dispatch; the mount plan decides what that path can reach. A review that credits only one of them will misjudge the boundary, so the split is stated here rather than left to be inferred.

The policy schema becomes a deployment contract. Changing a rule's shape is a breaking change for every deployment carrying a policy file, and takes the versioning path of [`08-contracts.md`](../08-contracts.md) §4.

## Alternatives

**An embedded OPA/Rego engine.** Rejected, and recorded in the rejection table of [`05-licensing-posture.md`](../manifesto/05-licensing-posture.md). It passes the licence and supply-chain gates; it fails on fit. The predicate vocabulary here is closed and small, and a general policy interpreter evaluating agent-influenced input adds parser surface at the agent-facing boundary, which is where [NFR-SEC-51](../manifesto/02-nfrs.md) asks for closed grammars. Reconsidered only if a customer-supplied policy plane becomes a requirement.

**Control-plane-delivered policy.** Rejected: it either adds the forbidden request-time read edge from the gateway to Control, or reduces to configuration delivered at boot, which is the decision above with a delivery mechanism the gateway need not know about.

**A static embedded policy.** Rejected: which caller may do what is deployment-specific, and embedding fixes it at build time for every operator.

**Command-content predicates for `bash_tool`.** Rejected as stated above. A control that produces audit evidence while not controlling is worse than its absence, because a review that red-teams it and breaks it discounts the neighbouring controls too.
