<!-- SPDX-License-Identifier: BUSL-1.1 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# 01 — The 4-Layer Model

> Target architecture, adapted from [sandboxd](../../../sandboxd/docs/architecture.md).
> Same model. Same separation of concerns. Our concrete component names.

## Diagram

```text
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 4 — Control Plane                          (Go service)      │
│  • User-facing API: MCP gateway + REST/GraphQL for admin UI         │
│  • Auth: OIDC / JWT, tenancy, RBAC                                  │
│  • Session router: session_id → sandbox handle (KV store)           │
│  • Secret broker: short-lived creds, key rotation                   │
│  • Quota / rate-limit / audit log                                   │
│  • Egress proxy management (JWT-allowlist signing)                  │
└────────────────────────┬────────────────────────────────────────────┘
                         │   HTTP / gRPC (internal, mTLS)
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 3 — Orchestrator / Provider             (pluggable)          │
│  SandboxProvider interface:                                         │
│    spawn(template) → handle    exec(handle, cmd) → stream           │
│    configure(handle, ctx)      stop(handle)                         │
│    list() / health(handle)                                          │
│                                                                     │
│  Implementations:                                                   │
│    • DockerComposeProvider  ← PoC, current path (Phases 1–4)        │
│    • KubernetesProvider     ← prod, on agent-sandbox CRDs (Phase 5) │
│    • DirectCHProvider       ← bare-metal microVM (Phase 9+, opt)    │
│                                                                     │
│  Owns: scheduling, warm pool, networking, storage binding           │
└────────────────────────┬────────────────────────────────────────────┘
                         │   creates / drives
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 2 — Sandbox Runtime                     (pluggable)          │
│  Selected per template via RuntimeClass / direct hypervisor:        │
│    • runc       — dev/CI, no isolation                              │
│    • sysbox     — internal/trusted, fast, kernel-shared             │
│    • gVisor     — code-exec only (NOT browser)                      │
│    • kata-ch    — Cloud Hypervisor microVM, untrusted Computer Use  │
│    • kata-fc    — Firecracker microVM, fastest cold start           │
└────────────────────────┬────────────────────────────────────────────┘
                         │   provides PID 1 process namespace
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 1 — Guest Agent                                              │
│  Today:  Python entrypoint + MCP server inside image  (transition)  │
│  Future: small Go static binary as PID 1            (Phase 7)       │
│  Surface: HTTP + WebSocket (+ vsock when on microVM)                │
│  Duties: exec, file ops, port-forward, CDP proxy, ttyd, MCP tools   │
│  Does NOT: authenticate (L4 does), persist state (L3 does)          │
└─────────────────────────────────────────────────────────────────────┘
```

## Why this split

- **Independent evolution.** Replace the runtime (L2) without touching the agent (L1) or the orchestrator (L3). Add a new orchestrator (L3) without changing the user-facing protocol (L4).
- **Threat-model-driven runtime choice.** Same agent, same control plane, different L2 for different tenants. Trusted internal → sysbox. Public Computer Use → Kata + Cloud Hypervisor.
- **One protocol for users.** L4 exposes **MCP** (already in production with us) plus a thin admin REST/GraphQL. L1–L3 internal contracts stay internal.

## Mapping today's code to this model

| Today | Where it lives | Future layer | Migration phase |
|---|---|---|---|
| `computer-use-server/app.py` (FastAPI, MCP, uploads, auth) | repo root | **L4** Control Plane (will be Go) | Phase 6 cutover |
| `computer-use-server/docker_manager.py` (Docker socket, lifecycle, cleanup) | repo root | **L3** Provider (`DockerComposeProvider`) | Phase 1 extract behind interface |
| `computer-use-server/mcp_tools.py` (bash/python/file tools) | repo root | **L4** (gateway) + **L1** (exec target) | Phase 7 split |
| `Dockerfile` entrypoint, in-image MCP server | sandbox image | **L1** Guest Agent (Python → Go) | Phase 7 |
| Docker (`runc`) as runtime | host | **L2** Runtime (`runc` tier) | Phase 9 adds Kata tiers |
| `helm/computer-use-server/` (single Deployment + DinD sidecar) | repo | **L3** + **L4** k8s manifests, split | Phases 5, 6 |
| `/tmp/computer-use-data` + Docker volumes | host fs | **Storage** ([06-storage.md](./06-storage.md)) — moves to S3 | Phase 3 |
| Static env-var secrets (Anthropic, GitLab, vision) | container env | **L4** secret broker | Phase 4 |

## What changes for users — nothing (intentionally)

- The MCP contract (tools, headers, auth) stays stable across every phase.
- Docker Compose PoC keeps working through Phase 10.
- Open WebUI integration is L4-facing — unchanged.

## What does NOT belong to any of these layers

- **Skills** (the AI capability bundles under `skills/`) — packaging, not architecture. They mount into L1 sandboxes. See [06-storage.md](./06-storage.md).
- **Open WebUI** — a downstream consumer of L4's MCP gateway. Not part of this stack.
- **Sub-agent CLIs** (claude, codex, opencode) — executed *inside* L1. Tooling, not architecture.

## Source

- [`sandboxd/docs/architecture.md`](../../../sandboxd/docs/architecture.md) — the layered model is taken from there.
- [`sandboxd/docs/glossary.md`](../../../sandboxd/docs/glossary.md) — shared vocabulary.

## See also

- [02 — Layer 4: Control Plane](./02-layer4-control-plane.md)
- [03 — Layer 3: Providers](./03-layer3-providers.md)
- [04 — Layer 2: Runtimes](./04-layer2-runtimes.md)
- [05 — Layer 1: Guest Agent](./05-layer1-guest-agent.md)
- [Roadmap](../roadmap.md)
