<!-- SPDX-License-Identifier: BUSL-1.1 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# ADR-0003 — Deployment ordering: Docker PoC first, then any k8s

- **Status:** Accepted
- **Date:** 2026-05-17

## Context

The roadmap targets multiple deployment shapes: Docker Compose (PoC), RKE2 on-prem, AWS EKS, and other k8s flavors. We need to commit to an order so each phase has a clear target.

User direction: *Docker PoC first, any k8s flavor second.*

## Decision

1. **Docker Compose is the PoC target.** Every phase must leave Compose runnable.
2. **k8s is treated as flavor-agnostic.** Helm chart is the single artifact. RKE2 and AWS EKS are the two reference test targets; nothing in the code privileges one.
3. **No flavor-specific shortcuts.** No EKS-only IAM dance baked into the chart, no RKE2-only manifest, no GKE-only autopilot tricks. Cloud-specific glue lives in Helm values overrides, never in templates.

## Rationale

- Compose is the fastest dev loop and the most reproducible PoC for community contributors. Breaking it imposes setup tax on everyone.
- k8s flavor diversity is real: target deployments span on-prem (RKE2) and cloud-managed (EKS, GKE, AKS). One chart that works on any conformant k8s ≥ 1.28 maximizes reach.
- The user explicitly does not want to prioritize one k8s flavor over another.

## Consequences

- Every PR must include "Compose still works" as part of acceptance.
- Phase 5 (Helm hardening + KubernetesProvider) tests on **both** kind/k3d (local k8s) and a real RKE2 or EKS cluster before merge.
- bare-metal-only L2 runtimes (kata-fc, kata-ch — Phase 9) require explicit bare-metal node pool — documented as a precondition, not assumed.

## Alternatives considered

- **k8s first, Compose deprecated** — rejected. Loses local dev story, community contributors hate it.
- **Pick one k8s flavor** — rejected. User said "any k8s".
- **Docker Compose forever** — rejected. Production tenancy / isolation / scale requires k8s.
