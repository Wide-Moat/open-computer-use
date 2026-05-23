<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# Future Architecture

This directory is the **single source of truth for the target architecture and migration roadmap** of Open Computer Use. It supersedes the previous `docs/requirements/` (renamed to here on 2026-05-17; see [ADR-0007](./adr/0007-superseded-by-future-architecture.md)).

The model is taken from [`sandboxd/`](../../sandboxd/) — a runtime-agnostic, 4-layer design — and adapted to our concrete codebase, constraints, and team preferences.

## TL;DR

- **4 layers:** Control Plane (L4) → Orchestrator/Provider (L3) → Sandbox Runtime (L2) → Guest Agent (L1).
- **11-phase roadmap** (0, 0.5, 1–10). Each phase strips one specific blocker. **No phase breaks the Docker Compose PoC** — that's an [explicit non-blocking invariant](./roadmap.md#non-blocking-invariants).
- **Order reshuffle** (post-review): egress proxy (now Phase 8) ships **before** Kata untrusted tier (now Phase 9) — otherwise "untrusted" is a lie.
- **Locked decisions (ADRs):**
  - **Languages:** Go control plane ([ADR-0001](./adr/0001-control-plane-language-go.md)); **Rust guest agent** ([ADR-0002](./adr/0002-guest-agent-language-go.md), rewritten 2026-05-18 after [`research/19`](./research/19-anthropic-process-api.md) study; matches the `process_api` stack).
  - **Internal transport:** connect-go on L4↔L3; L3↔L1 re-evaluated at Phase 7 (connect-rust vs `process_api`-style WS-frame protocol) per [ADR-0008](./adr/0008-internal-grpc-external-rest-mcp.md).
  - **External protocols:** MCP user-facing ([ADR-0005](./adr/0005-mcp-as-control-plane-gateway.md)); REST for admin; CDP/ttyd is WebSocket passthrough; optional dialect adapters per [ADR-0009](./adr/0009-external-protocol-dialects.md).
  - **Deployment:** Docker-first then k8s ([ADR-0003](./adr/0003-docker-poc-first-then-k8s.md)); pluggable runtime via `RuntimeClass` ([ADR-0004](./adr/0004-pluggable-runtime-via-runtimeclass.md)).
  - **Dependencies:** no AGPL/BSL ([ADR-0006](./adr/0006-no-agpl-no-bsl-dependencies.md)).
  - **AWS Lambda:** inspiration, not runtime ([ADR-0010](./adr/0010-lambda-as-inspiration-not-runtime.md)).

## Reference architectures we draw from

- **Anthropic `process_api`** ([`research/19`](./research/19-anthropic-process-api.md), source under [`sandboxd/anthropic/process_api_re/`](../../sandboxd/anthropic/process_api_re/)) — closest precedent for Phase 7 L1.
- **AWS Lambda** ([`references.md`](./references.md) Lambda framing, [ADR-0010](./adr/0010-lambda-as-inspiration-not-runtime.md)) — pattern source for Firecracker tiering and snapshot-pool cold-start economics. Inspiration only.
- **Snapstart hot-swap** ([`research/20`](./research/20-snapstart-hot-swap.md)) — Phase 10 cold-start design.
- **E2B `envd`** ([`research/02`](./research/02-e2b-infra.md)) — production-shape L1 comparison.
- **Coder** ([`research/03`](./research/03-coder.md)) — multi-region workspace-proxy pattern.
- **Anthropic `environment-runner`** ([`research/21`](./research/21-environment-runner-go.md)) — inspiration-only Go session agent; not on roadmap.
- **Per-phase research-then-sign-off cadence.** Every phase begins with a research pass against the cloned reference repos (under `/references/`, git-ignored) **and** the matching digest in [`research/`](./research/), produces `phase-N-research.md`, and requires owner approval before code starts. **Mandatory pre-read:** the matching phase row in [`antipatterns.md`](./antipatterns.md) — 36 antipatterns mapped to phases, each with our locked decision.

## Document map

**Live spec (read every phase):**

```text
docs/future-architecture/
├── README.md                       ← you are here
├── roadmap.md                      11 phases (0, 0.5, 1–10), invariants, failure modes, rollback
├── antipatterns.md                 ⭐ operational decision log, per-phase index
├── gaps.md                         Pre-mortem gap inventory (A–M); suggestions, not commitments
├── phase-template.md               Skeleton for phase-N-research.md and phase-N-plan.md
├── references.md                   External repos + projects, annotated
├── architecture/                   Target design — 4-layer spec
│   ├── 01-layers.md                4-layer overview + ASCII diagram + mapping to today's code
│   ├── 02-layer4-control-plane.md  Go service: MCP gateway, OIDC, admin UI, secret broker
│   ├── 03-layer3-providers.md      SandboxProvider interface + Docker/K8s/Direct impls
│   ├── 04-layer2-runtimes.md       runc / sysbox / gVisor / kata-fc / kata-ch matrix
│   ├── 05-layer1-guest-agent.md    Rust agent contract, PID-1 duties, MCP tool exec
│   ├── 06-storage.md               4-tier: image / squashfs skills / workspace / S3 user-data
│   ├── 07-security.md              Threat model, secret rotation, egress, image signing, audit
│   ├── 08-networking.md            NetworkPolicy default-deny, egress proxy, CDP routing
│   ├── 09-templates.md             SandboxTemplate spec, tenant→template resolver
│   └── 10-observability.md         Metrics, traces, audit log, SLOs
└── adr/                            Locked decisions
    ├── 0001-control-plane-language-go.md       (Phase 6 re-eval gate added 2026-05-18)
    ├── 0002-guest-agent-language-go.md         (rewritten 2026-05-18: Rust, not Go)
    ├── 0003-docker-poc-first-then-k8s.md
    ├── 0004-pluggable-runtime-via-runtimeclass.md
    ├── 0005-mcp-as-control-plane-gateway.md
    ├── 0006-no-agpl-no-bsl-dependencies.md
    ├── 0007-superseded-by-future-architecture.md
    ├── 0008-internal-grpc-external-rest-mcp.md (Phase 7 gate tightened 2026-05-18)
    ├── 0009-external-protocol-dialects.md
    └── 0010-lambda-as-inspiration-not-runtime.md   (added 2026-05-18)
```

**Research archive (read at start of relevant phase only):**

```text
└── research/                       Per-repo digests; reference-only, decay OK
    ├── 01-kata-containers.md          (Phase 7, 9)
    ├── 02-e2b-infra.md                (Phase 2, 3, 6, 7, 8)
    ├── 03-coder.md                    (Phase 6)
    ├── 04-cloud-hypervisor.md         (Phase 9, 10)
    ├── 05-firecracker.md              (Phase 9, 10)
    ├── 06-agent-sandbox.md            (Phase 5)
    ├── 07-chromedp.md                 (Phase 7)
    ├── 08-microsandbox.md             (Phase 2, 9)
    ├── 09-agentbox.md                 (Phase 8)
    ├── 10-sysbox.md                   (Phase 5)
    ├── 11-firecracker-containerd.md   (Phase 9, 10)
    ├── 12-docker-socket-proxy.md      (Phase 2, 8)
    ├── 13-anthropic-sandbox-runtime.md (Phase 7, 9)
    ├── 14-e2b-desktop-and-surf.md     (Phase 7)
    ├── 15-claude-code-reverse-engineering.md (Phase 6, 7, 10)
    ├── 16-anthropic-production-sandbox-observed.md (Phase 3, 7, 8)
    ├── 17-anthropic-claude-code-remote-env-observed.md (Phase 6, 7, 10)
    ├── 18-open-webui-terminals-observed.md (Phase 6, 8)
    ├── 19-anthropic-process-api.md    (Phase 7, 10 — primary L1 precedent)
    ├── 20-snapstart-hot-swap.md       (Phase 10)
    ├── 21-environment-runner-go.md    (inspiration-only; no Phase consumer)
    └── 22-anthropic-firecracker-microvm-internals-observed.md ⭐ (Phase 3, 7, 9, 10) — locks A37 "no PVC for sandbox session workspace"
```

## Reference repositories

Cloned shallowly into `/references/` (added to `.gitignore`):

```text
agent-sandbox  agentbox    chromedp        cloud-hypervisor
coder          desktop     docker-socket-proxy
firecracker    firecracker-containerd      infra (e2b-dev)
kata-containers  microsandbox  reverse-engineering-claude-code-antspace
sandbox-runtime  surf       sysbox
```

Each phase in [roadmap.md](./roadmap.md) carries a checklist of which of these to study before that phase's research doc is written. Don't read the repos cold — start from [`research/`](./research/) which has per-repo "what to take" digests with file:line citations.

## Per-phase research-then-sign-off cadence

Mandatory for **every** phase (not just the greenfield ones):

1. **Pre-read.** Open [`antipatterns.md`](./antipatterns.md) — find your phase row — read every linked entry. These are PR-review checkpoints with our locked choice already filled in. Don't reintroduce them.
2. **Research.** Investigate the listed `references/` repos via their `research/` digest. External docs as needed.
3. **Write `phase-N-research.md`** from [`phase-template.md`](./phase-template.md). Options, recommendation, trade-offs, success metrics.
4. **Discuss + sign off with owner.** No code begins until approval.
5. **Plan.** Invoke `gsd-plan-phase` to break the phase into atomic tasks. Result: `phase-N-plan.md`.
6. **Execute** on a `dev/future-architecture/phase-N-*` branch.
7. **Verify** against acceptance criteria.
8. **Merge** into `dev/future-architecture` (default) or `main` (if independently shippable).
9. **Retro.** If the phase revealed that an earlier phase was wrong, follow [roadmap.md § Failure modes](./roadmap.md#failure-modes--cross-phase-retros).

## Branching strategy

1. **This directory** (the docs + ADRs) lands on a docs branch and is **merged to `main`** as the locked source of truth. Pure docs, no code risk.
2. **After merge**, all roadmap execution moves to a long-lived branch — proposed name `dev/future-architecture` — cut from `main`. `main` stays shippable.
3. Each phase ships as a PR from `dev/future-architecture/phase-N-*` → `dev/future-architecture` (default), or → `main` directly if the phase is independently shippable and reversible (Phase 1 is the example: pure additive abstraction).
4. `dev/future-architecture` is rebased on `main` regularly so production hotfixes never diverge.

## What this document tree does NOT do

- It is not user-facing docs — see `docs/INSTALL.md`, `docs/FEATURES.md`, `docs/CLOUD.md` for runtime-relevant content.
- It is not a backlog — GitHub Issues for that.
- It does not authorize any code change. Each phase has its own sign-off gate.
- If a doc here conflicts with the running system, **the running system wins until that phase ships**.

## Constraints inherited from the project

- All text **English only** (project-wide rule).
- License hygiene: no AGPL, no BSL in direct deps ([ADR-0006](./adr/0006-no-agpl-no-bsl-dependencies.md)).
- Docker Compose PoC must keep working through every phase ([ADR-0003](./adr/0003-docker-poc-first-then-k8s.md)).
- The MCP user-facing contract is frozen ([ADR-0005](./adr/0005-mcp-as-control-plane-gateway.md)).

## Next steps

1. Owner reviews + merges this directory.
2. Cut `dev/future-architecture` from `main`.
3. Invoke `gsd-new-milestone` for "future-architecture migration v1" anchored to [roadmap.md](./roadmap.md).
4. Begin Phase 1: read antipatterns row → write `phase-1-research.md` from `phase-template.md`.
