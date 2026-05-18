<!-- SPDX-License-Identifier: BUSL-1.1 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# ADR-0010 — AWS Lambda: inspiration, not runtime

- **Status:** Accepted
- **Date:** 2026-05-18
- **Deciders:** project owner
- **Supersedes:** —
- **Superseded by:** —
- **Related:** [ADR-0003](./0003-docker-poc-first-then-k8s.md), [ADR-0004](./0004-pluggable-runtime-via-runtimeclass.md), [references.md](../references.md), [research/05](../research/05-firecracker.md), [research/16](../research/16-anthropic-production-sandbox-observed.md), [research/19](../research/19-anthropic-process-api.md), [research/20](../research/20-snapstart-hot-swap.md)

## Context

AWS Lambda recurs across the reference catalogue. It is the original consumer of Firecracker; its MicroManager pool is the design lineage behind Anthropic's `process_api` placement plane ([research/19](../research/19-anthropic-process-api.md) §11); its cold-start economics underwrite the snapstart pattern we evaluate at Phase 10 ([research/20](../research/20-snapstart-hot-swap.md)).

This recurrence has begun to confuse the architecture conversation. "Lambda" appears in [`references.md`](../references.md) as a Firecracker provenance note, in [`research/05`](../research/05-firecracker.md) as a foundation, and in [`research/16`](../research/16-anthropic-production-sandbox-observed.md) as a contrast to our k8s direction. None of these documents make the explicit claim that we will or won't run on Lambda.

This ADR makes the claim and closes the question.

## Decision

**Open Computer Use will not run on AWS Lambda or AWS Fargate.** Lambda is treated as a **design reference**, not a deployment target. The patterns we borrow are explicit, named, and bounded; nothing beyond them transfers.

### What "inspiration" means concretely

We adopt **patterns** from the Lambda design lineage:

| Pattern | How it lands for us | Where |
|---|---|---|
| Firecracker as a microVM tier with the smallest attack surface | `kata-fc` runtime tier | [`research/05`](../research/05-firecracker.md), [`architecture/04-layer2-runtimes.md`](../architecture/04-layer2-runtimes.md), Phase 9 |
| Two-tier control split (host-side router + in-guest supervisor) | L4 (Go) + L1 (Rust, [ADR-0002](./0002-guest-agent-language-go.md)) with WS over vsock | [`research/19`](../research/19-anthropic-process-api.md), Phase 7 |
| Frozen-snapshot pool with block-device hot-swap on resume | Snapstart-style cold-start optimization | [`research/20`](../research/20-snapstart-hot-swap.md), Phase 10 |
| Per-session VM isolation (no reuse across tenants) | RuntimeClass-driven, per-tenant namespace | [ADR-0004](./0004-pluggable-runtime-via-runtimeclass.md), `architecture/07-security.md` |

### What we are explicitly **not** adopting

- **The deployment substrate.** We do not deploy on `aws-lambda` (function-as-a-service) or `aws-fargate` (managed-task). The runtime substrate is Kubernetes ([ADR-0003](./0003-docker-poc-first-then-k8s.md)) plus a RuntimeClass-pluggable microVM tier ([ADR-0004](./0004-pluggable-runtime-via-runtimeclass.md)).
- **Per-invocation billing model.** Our sandboxes are session-shaped, not request-shaped. The cost model is per-session, per-RuntimeClass — not per-100ms-CPU-burst.
- **15-minute hard wall.** Lambda's 15-minute invocation cap is a non-starter for Computer Use sessions. We need sessions that survive multi-hour LLM-driven work.
- **Lambda's specific orchestrator.** Anthropic's Router shares Lambda's lineage but is a custom system. We are not cloning either; k8s + a custom L4 control plane do the same job at our scale.
- **Lambda Extensions / Layers / SnapStart-the-AWS-product.** These are AWS-product names. We use the *technique* SnapStart describes (see [`research/20`](../research/20-snapstart-hot-swap.md)) without using AWS's implementation.

## Rationale

- **Scale mismatch.** Lambda's design optimizes for millions of short serverless invocations. We target 100–10K concurrent long-lived sandboxes (see [`research/16`](../research/16-anthropic-production-sandbox-observed.md) §7). k8s + RuntimeClass remains the right fit; serverless infra is over-engineered for the bottom and under-fit for the top.
- **Workload shape mismatch.** Computer-Use sessions are stateful, long-running, and need predictable resource ceilings (memory for screencast frame buffers, CPU for browser rendering). Lambda's stateless-by-default, scale-on-bursts model fights every assumption.
- **Self-hosting requirement.** A serious chunk of the addressable user base self-hosts. Lambda is not portable; k8s is.
- **Vendor lock.** Lambda ties us to AWS as the deployment substrate. The architecture explicitly aims for AWS, GCP, on-prem RKE2, and Docker Compose ([ADR-0001](./0001-control-plane-language-go.md) Context).
- **Open-source posture.** The project is open-source ([ADR-0006](./0006-no-agpl-no-bsl-dependencies.md) on license hygiene). Optimizing for a single-cloud managed runtime is at odds with that posture.

## Consequences

**Positive:**
- The Lambda question is closed. Future debate about "should we go serverless?" can be answered by linking to this ADR.
- Phase 9 / Phase 10 design discussions can use Lambda as a reference point without confusion about commitment.
- `references.md` gets one explicit Lambda paragraph; everything else cross-links to it.

**Negative:**
- We carry the operational cost of running k8s ourselves. Acceptable per [ADR-0001](./0001-control-plane-language-go.md), [ADR-0003](./0003-docker-poc-first-then-k8s.md).
- Snapshot-pool engineering at Phase 10 is non-trivial without Lambda's MicroManager doing it for us. Acceptable; it's also what makes the system buildable outside AWS.

**Neutral:**
- A future small-scale deployment optimization could in theory wrap sandboxes in Fargate Tasks. This ADR does not preempt that; it forbids it as the *default*.

## Alternatives considered

### Run on AWS Lambda
- **Verdict:** rejected. 15-minute cap, stateless-by-default, no Kubernetes affinity, vendor lock. Doesn't fit the workload.

### Run on AWS Fargate
- **Pro:** managed task substrate, no node ops.
- **Con:** opaque scheduler, no RuntimeClass control, no microVM tiering (Firecracker is there but you can't pick), still AWS-only.
- **Verdict:** rejected as the *default*. Possibly viable as a future "managed tier" for AWS-only users; that would land in its own ADR.

### Adopt Lambda's MicroManager pattern wholesale
- **Pro:** proven at scale.
- **Con:** rebuilds Lambda's orchestrator on our side — a huge engineering bill for problems we don't have yet at our scale.
- **Verdict:** rejected. We adopt the **patterns** ("two-tier control", "snapshot pool", "per-session isolation") without rebuilding the orchestrator. k8s + a custom L4 are enough.

## Verification

- `references.md` contains a single "Lambda framing" subsection that cross-links to this ADR.
- `architecture/04-layer2-runtimes.md` mentions Firecracker's Lambda lineage exactly once, with a back-link here.
- Search the docs tree for "Lambda" — every hit either points to this ADR, the references paragraph, or a research digest. No standalone claims.
- Phase 9 / Phase 10 PRs that touch microVM choice or snapshot pooling include "ADR-0010 reviewed" in the PR description checklist.
