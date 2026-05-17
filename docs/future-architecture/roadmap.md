# Roadmap — Future Architecture Migration

> **Eleven phases**, ordered to strip one blocker at a time.
> Every phase requires **explicit user sign-off** before code starts (see [README.md](./README.md) — research-then-sign-off cadence).
> Every phase carries a **research checklist** linking to repos under `/references/` (git-ignored) and to the matching digest in [`research/`](./research/).

## Non-blocking invariants ⭐ (apply to **every** phase)

These rules are how we keep the migration evolutionary. Any PR that violates them must justify it explicitly in the description or be split.

1. **PoC survival.** Docker Compose PoC keeps working after the phase ships. Acceptance tests run on both Compose AND target backend (k8s where applicable). No exception.
2. **Default off.** Every new behavior gates behind a feature flag (env var or template setting). Default = previous behavior. Operator opts in.
3. **No silent rework dependencies.** Phase N may not require a follow-up phase to "finish" a feature shipped in N. If feature X needs phase N+k to be production-ready, ship it as `X-MVP` in phase N and `X-prod` in N+k — both named.
4. **MCP contract frozen.** `POST /mcp` request/response wire format does not change across any phase. Internal transports may.
5. **Reversible by switch, not by rewrite.** Rollback = flip the flag back / pin the previous image digest. Never "revert N commits across N+1, N+2".
6. **Reads first, writes second.** If a phase introduces a new data store / mount / API, ship the read path before the write path. Write path stays gated until the read path is observed clean.
7. **Latent coupling banned.** If phase N depends on phase M (M < N) for production-readiness — even subtly — the `Depends on` line must say so explicitly. Reviewers reject anything implicit.
8. **Antipattern review mandatory.** Before any phase starts, scan the matching row in [`antipatterns.md`](./antipatterns.md) phase index. Each listed antipattern is a PR-review checkpoint with our locked choice. New antipatterns discovered mid-phase go into doc 16 in the same shape.

## Phase grid

| # | Name | Layer | Blocker removed | Reversibility |
|---|---|---|---|---|
| 0 | Document & decide | — | No source of truth for the target | trivially (revert docs) |
| **0.5** | **Architecture-doc polish (gaps from review)** | docs | Known gaps from the antipatterns doc not yet in architecture/* | trivially |
| 1 | `SandboxProvider` interface (Python) | L3 | Docker socket as single SoT | flip flag — additive abstraction |
| 2 | HTTP sandbox pool sidecar | L3 | 1:1 chat:container, no pool | feature-flag (`SANDBOX_PROVIDER`), default `docker_socket` |
| 3 | S3 user-data + squashfs skills (MVP, static creds) | Storage | Local-fs tenancy | per-tenant flag; static creds → prod-ready only after Phase 4 |
| 4 | Secret broker + key rotation | L4-precursor | Static env-injected secrets; finishes Phase 3 prod-readiness | broker flag |
| 5 | Helm hardening + `KubernetesProvider` | L3 | DinD-only k8s deploy | separate chart values; Compose still default |
| 6 | Go control plane (dual-run) | L4 | FastAPI orchestrator monolith | reverse-proxy split per route; revert by re-pointing |
| 7 | Go guest agent + per-template RuntimeClass selection | L1 + L2 | Python in-image MCP server; single global runtime | new image digest; pin previous to roll back |
| **8** | **Egress proxy + audit pipeline (lands BEFORE untrusted tier)** | L4 | No egress control; foundation for untrusted tier | additive; templates without `egress_baseline` keep working |
| **9** | **Kata + Cloud Hypervisor for untrusted tier** | L2 | No hardware isolation (now safe because Phase 8 egress shipped) | opt-in template; sysbox stays default |
| 10 | Snapshot/restore + multi-region | L3 + L4 | No HA, no pause-session | additive per-template + per-deployment |

> **8 ↔ 9 reordering note.** Originally Kata (now Phase 9) shipped before egress proxy. That would have meant "hardware isolation for untrusted users, but they can still freely contact the internet" — unsafe. Egress proxy (Phase 8) is the prerequisite for any "untrusted" claim.

---

## Phase 0 — Document & decide

**Goal.** Lock the target architecture and roadmap; produce ADRs.

**Deliverables.**
- This `docs/future-architecture/` tree merged to `main`.
- 7 ADRs accepted.
- All reference repos cloned under `/references/` (git-ignored).

**Research checklist.** N/A (this phase *is* the research synthesis).

**Acceptance.** PR merged; references list reviewed by owner.

**Sign-off gate.** Already passed — `ExitPlanMode` approval.

---

## Phase 0.5 — Architecture-doc polish (gaps from review)

**Goal.** Patch the architecture docs with the Anthropic / sandboxd practices flagged as missing during the Phase-0 review (gaps tracked across `antipatterns.md` and `research/*`). Pure docs, no code.

**Blocker removed.** Architecture promises something the antipatterns doc says is critical, but `architecture/*` doesn't yet describe how. Phase 1 starts with mismatched contract → rework.

**Research checklist.** None — synthesis of existing pattern docs.

**Deliverables (file-by-file).**
- `architecture/05-layer1-guest-agent.md`: commit to vsock-first / TCP-fallback runtime auto-detect (not build-tag gating); add `PR_SET_DUMPABLE=0`; add `SIGCHLD` reaping + `SIGTERM` propagation explicit; add **dual-port API** (data-plane WS + control-plane HTTP) per Anthropic.
- `architecture/07-security.md`: add `memfd_create` agent binary as defense-in-depth; add **mandatory deny paths** inside workspace home (`.git/hooks`, `.bashrc`, `.mcp.json`, …); add **graceful-shutdown protocol** (page-cache drop → SIGTERM → wait → SIGKILL).
- `architecture/03-layer3-providers.md`: extend warm-pool knobs with `refillRate` + `maxAge`; add **environment-type dispatch** (Baku pattern); add **SandboxClaim CRD** semantics for k8s provider.
- `architecture/02-layer4-control-plane.md`: explicit anti-pattern note "no `sessionAffinity: ClientIP`"; add **HA-replica upgrade strategy** (scale-to-1, migrate, scale-up); add **blue-green deployment** section.
- `architecture/06-storage.md`: add **block-device tooling swap** (Baku/process_api pattern) for microVM templates.
- `architecture/08-networking.md`: add **multi-region workspace-proxies** pattern (Coder) as a Phase-10 substrate.
- `architecture/10-observability.md`: add **RAM-based capacity-sizing formula**; add concrete **SLO targets** (session-create p99 < 500 ms warm, exec p99 < 50 ms, CDP ≥ 10 fps, egress p99 < 100 ms); add **distributed tracing** subsection.
- `architecture/04-layer2-runtimes.md`: add **nydus snapshotter** for lazy-load image layers (relevant Phase 9 with Kata); clarify **virtio-fs vs 9p** decision (CH/FC asymmetry).
- `antipatterns.md`: confirm all referenced entries (A1–A36, C1–C10) align with the new architecture detail; add any new ones surfaced during the polish.
- README index: add `architecture/11-deployment-shapes.md` if any of the above grows too big to fit existing files.

**Acceptance.**
- Each architecture/* doc cross-references the matching `research/NN-*.md`.
- the antipatterns doc table includes all 21 rows with `Action` column.
- No new ADRs needed; if any of the additions requires a decision, file an ADR in the same PR.

**Reversibility.** Pure docs — flip via `git revert`.

**Depends on.** Phase 0.

---

## Phase 1 — `SandboxProvider` interface (Python)

**Goal.** Extract `computer-use-server/docker_manager.py` behind a `SandboxProvider` Protocol. `DockerSocketProvider` is the only implementation. Tests unchanged.

**Blocker removed.** Direct `docker.client` calls scattered across `app.py` / `docker_manager.py` / cleanup cron. Future providers (HTTP pool, k8s) can't exist without this seam.

**Research checklist (mandatory before code).**
- `references/agent-sandbox/api/` — read CRD shapes to inform `SandboxTemplate`, `SandboxHandle` types.
- `references/infra/packages/orchestrator/` — E2B's provider-like layer in Go; port API shape to Python.
- `references/kata-containers/src/agent/` — note OCI-shape we explicitly *don't* want to copy.
- Output: `phase-1-research.md` summarizing the chosen interface + alternatives.

**Acceptance.**
- `tests/integration/test_mcp_*.py` pass unchanged.
- `grep -r 'docker\.' computer-use-server/app.py` returns 0 matches (all behind the provider).
- New `computer-use-server/providers/__init__.py` and `providers/docker_socket.py`.

**Reversibility.** Pure additive abstraction. Roll back by re-inlining provider methods.

**Depends on.** Phase 0.5 (gaps in `architecture/03-layer3-providers.md` patched first).

---

## Phase 2 — HTTP sandbox pool sidecar

**Goal.** Move Docker-socket access out of the orchestrator process into a small `pool-manager` sidecar that speaks HTTP to the orchestrator. Warm-pool skeleton lands (`minSize=0` default = no behavior change).

**Blocker removed.** 1:1 chat:container; no warm pool; orchestrator holds the Docker socket privilege.

**Research checklist.**
- `references/infra/packages/orchestrator/` — E2B's pool semantics.
- `references/agent-sandbox/api/sandbox/v1alpha1/sandboxwarmpool_types.go` — CRD field set.
- `references/microsandbox/` — single-node daemon REST API for inspiration.
- Output: `phase-2-research.md` — HTTP API spec for pool-manager + warm-pool semantics.

**Acceptance.**
- New `pool-manager/` service in `docker-compose.yml`, optional via Compose profile (`COMPOSE_PROFILES=pool` or default-off service).
- `HTTPPoolProvider` is the second `SandboxProvider` impl; feature-flagged via env (`SANDBOX_PROVIDER=docker_socket|http_pool`). **Default = `docker_socket`** so the Compose PoC keeps working unchanged.
- Orchestrator container **may continue mounting `/var/run/docker.sock`** under the default provider; socket binding becomes pool-manager-only once an operator flips `SANDBOX_PROVIDER=http_pool`.
- Integration tests run against **both** providers in CI; PoC test path stays on `docker_socket`.

**Reversibility.** Feature flag. Default stays `docker_socket` until parity is proven over at least one minor release.

**Depends on.** Phase 1.

---

## Phase 3 — S3 user-data + squashfs skills (MVP with static creds)

**Goal.** Replace `/tmp/computer-use-data` filesystem with S3-compatible object storage. Package skills as content-addressed squashfs blobs. **MVP only** — static creds are acceptable here; per-session STS tokens land in Phase 4 and gate production-readiness for the S3 mount.

**Blocker removed.** Local-fs tenancy (single-node ceiling), zip-based skill cache, no immutability contract for skills.

**Prod-readiness boundary.** Phase 3 ships **`S3-MVP`** (works locally / single-tenant, static creds). The **`S3-prod`** label only attaches after Phase 4 (secret broker) is integrated. Don't call S3 storage "production-ready for multi-tenant" until Phase 4 ships.

**Research checklist.**
- `references/infra/packages/template-manager/` — E2B's image+template build pipeline.
- `references/desktop/` and `references/surf/` — see how E2B's Computer Use stack handles user data flow.
- FUSE mount choice: `rclone mount` vs `mountpoint-s3` vs `geesefs` — fetch each project's `README` + write semantics doc.
- Output: `phase-3-research.md` — chosen S3 client, FUSE mount, squashfs build recipe.

**Acceptance.**
- MinIO container in `docker-compose.yml`.
- `S3_*` env vars wired; per-tenant bucket layout documented.
- FUSE sidecar in compose; sandbox mounts `/mnt/user-data` from S3.
- Skill build target produces `.squashfs` artifacts, uploaded to bucket on release.
- Sandbox image no longer carries `/usr/local/share/skills/` baked in.

**Reversibility.** Partial. Data migration script provided (`tmp → s3`). Old skills bake-in path keeps working until removed.

**Depends on.** Phase 2 (provider passes mount spec).

---

## Phase 4 — Secret broker + key rotation

**Goal.** Introduce L4 secret broker pattern. Anthropic / GitLab / S3 creds become short-lived and rotatable without restart.

**Blocker removed.** Static env-injected secrets; restart-on-rotation; full-lifetime credential exposure inside sandbox.

**Research checklist.**
- `references/sandbox-runtime/` — Anthropic's local sandbox: env injection patterns.
- `references/infra/packages/proxy/` — E2B's egress-proxy + token signing.
- AWS STS docs for per-session token scoping (not in `references/`; standard docs).
- Output: `phase-4-research.md` — broker API, rotation schedule, STS bucket policy template.

**Acceptance.**
- New `secret_broker` module in orchestrator; provider's `configure(handle, ctx)` carries per-session creds (not env at create-time).
- Rotation: `POST /admin/rotate?kind=anthropic` triggers re-`configure` of all live sandboxes without restart.
- `tests/integration/test_secret_rotation.py` proves restart-free rotation.

**Reversibility.** Static-env path kept as fallback behind a flag for one release.

**Depends on.** Phase 2 explicitly — **HTTP provider transport is required for per-session credential injection**. The broker mints creds and delivers them via `configure(handle, ctx)` on each session-spawn. In-process `configure` (pre-Phase-2) works for unit tests but cannot deliver per-session creds across the network boundary that production needs.

---

## Phase 5 — Helm hardening + `KubernetesProvider`

**Goal.** Real `KubernetesProvider` (Python `kubernetes-asyncio`). Helm chart switches from DinD-in-pod to per-pod sandboxes orchestrated via the provider. NetworkPolicy default-deny, ResourceQuota, empty-RBAC ServiceAccount.

**Blocker removed.** DinD-only k8s deploy; no real k8s tenancy isolation.

**Research checklist.**
- `references/agent-sandbox/` — controller patterns, CRD lifecycle, warm-pool implementation.
- `references/kata-containers/tools/packaging/kata-deploy/` — DaemonSet pattern (preview for Phase 8).
- `references/sysbox/` — RuntimeClass registration (default L2 for this phase).
- Output: `phase-5-research.md` — whether to vendor `agent-sandbox` CRDs or fork, NetworkPolicy template, RBAC matrix.

**Acceptance.**
- `KubernetesProvider` shipped; passes integration suite against `kind` cluster in CI.
- Helm chart: NetworkPolicy default-deny per tenant namespace, `ResourceQuota` + `LimitRange`, empty-RBAC `ServiceAccount`.
- DinD sidecar removed from chart.
- `tests/integration/test_mcp_*.py` pass on **both** kind/k3d cluster (with `KubernetesProvider`) **and** local Compose (with `DockerComposeProvider`). CI runs both paths and fails the PR if either regresses.

**Reversibility.** Old Helm values preserved as `values-legacy-dind.yaml` for one release.

**Depends on.** Phases 1, 4. (Phase 4 must ship first because the k8s chart's `Secret` template references the broker; without the broker, secrets stay static and the k8s deployment is not production-multi-tenant — only single-tenant PoC.)

---

## Phase 6 — Go control plane (greenfield)

**Goal.** New L4 service in Go. Replaces Python `computer-use-server`. OIDC, session router, MCP gateway, admin UI scaffold, secret broker, audit log emission.

**Blocker removed.** Python FastAPI monolith; weak streaming concurrency; no admin UI.

**🛑 Hard sign-off gate.** This is the **first greenfield rewrite**. User must explicitly approve `phase-6-research.md` before code starts. **The dual-run strategy section (see below) is part of the gate** — without it, "partial reversibility" is fiction.

**Research checklist.**
- `references/coder/coder/` — Go control plane at scale; auth, sessions, audit. Closest production reference. See [`research/03-coder.md`](./research/03-coder.md).
- `references/infra/packages/api/` — E2B's API shape in Go.
- `references/agent-sandbox/cmd/` and `references/agent-sandbox/pkg/` — Go controller patterns.
- `references/chromedp/chromedp/` — CDP handling on the wire (relevant for L4's CDP proxy duties); see [`research/07-chromedp.md`](./research/07-chromedp.md) §9 — L4 should **not** parse CDP, just shovel WS frames.
- Go web framework choice: stdlib `net/http` vs `chi` vs `connect-go` vs `gin` — write a comparison. **Note: [ADR-0008](./adr/0008-internal-grpc-external-rest-mcp.md) makes `connect-go` the lead candidate for internal RPCs; this research item is now about external/admin REST + ingress routing, not the internal transport.**
- MCP-on-Go: roll-our-own JSON-RPC vs SDK (check maturity).
- KV choice: Redis vs Valkey vs etcd.
- **Dual-run strategy section** — mandatory in research doc:
  - (a) KV schema — versioned, shared by Python+Go during cutover.
  - (b) Write ownership — Python keeps creating sessions; Go reads first, creates only after parity proven (Read-path-before-write-path invariant).
  - (c) Reverse-proxy route split — which routes go to Go first (start with `/healthz`, then read-only admin, then `/mcp`).
  - (d) Rollback checklist — flip reverse-proxy weights back; drain Go sessions cleanly.
  - (e) Max dual-run window — propose 2 weeks; longer = stale-session risk.
- **HA-replica upgrade strategy** — at production scale we'll run multiple L4 replicas. Document scale-to-1-for-migration pattern (see [`research/03-coder.md`](./research/03-coder.md) §7-adjacent guidance).
- **Blue-green deployment runbook** — zero-downtime upgrade for stateful L4.
- Output: `phase-6-research.md` — web stack, framework, k8s client, KV, MCP impl, streaming transport, admin UI stack, dual-run plan, HA upgrade strategy.

**Acceptance.**
- New Go service runs alongside Python; reverse proxy splits traffic by route.
- Integration suite (`tests/integration/test_mcp_*.py`) passes against Go endpoint unchanged.
- Admin UI MVP: list sessions, kill, rotate secret, view audit.
- Python service marked deprecated; removal scheduled.

**Reversibility.** Dual-run during cutover; revert by flipping reverse-proxy weights back to Python. **The dual-run strategy section in `phase-6-research.md` is the contract** — without that doc signed off, "reversibility" is not real.

**Depends on.** Phases 1–5 complete (or at least: 1, 4, 5).

---

## Phase 7 — Go guest agent + RuntimeClass selection per template

**Goal.** Replace today's Python entrypoint + in-image MCP server with a Go static binary as PID 1. Templates gain `runtime_class` selection; gVisor lands as experimental for code-exec sandboxes.

**Blocker removed.** Python in-image agent = big attack surface, no vsock readiness, blocks microVM. Single global runtime = no tiering.

**🛑 Hard sign-off gate.** **Owner approves research AND confirms either (a) Go is correct OR (b) ADR-0002 is superseded with a Rust ADR.** The 4 questions from [ADR-0002](./adr/0002-guest-agent-language-go.md) §"Decision gate" must each be answered explicitly in `phase-7-research.md`.

**Research checklist.**
- `references/kata-containers/src/agent/` — PID 1 patterns, signal handling, `PR_SET_DUMPABLE=0`, vsock listener, zombie reaping. See [`research/01-kata-containers.md`](./research/01-kata-containers.md).
- `references/infra/packages/envd/` — Go agent API surface and streaming. See [`research/02-e2b-infra.md`](./research/02-e2b-infra.md) §3.
- `references/microsandbox/` — minimal libkrun integration patterns.
- `references/sandbox-runtime/` — bubblewrap / seccomp BPF (secondary-defense inside VM). See [`research/13-anthropic-sandbox-runtime.md`](./research/13-anthropic-sandbox-runtime.md).
- `references/chromedp/chromedp/` — chromedp vs raw CDP WebSocket for the agent. See [`research/07-chromedp.md`](./research/07-chromedp.md).
- `references/agent-sandbox/` — `RuntimeClass` plumbing.
- **ADR-0002 re-evaluation gate (mandatory section).** Answer:
  1. Concrete RCE attack-surface of Go HTTP/WS server inside sandbox — real exposure or theoretical?
  2. Binary-size delta with optimizers tuned (Go `-s -w -trimpath` vs Rust LTO).
  3. CDP / Chromium driving cost in Rust (no chromedp equivalent — write our own or use less-mature crate?).
  4. Owner's honest assessment of Rust productivity *as of Phase-7 start*.
  Each answer feeds the sign-off. If answers favor Rust → propose ADR-0002 supersession in the same PR; do not start Go code.
- Output: `phase-7-research.md` — chromedp vs raw CDP decision; vsock-first / TCP-fallback auto-detect algorithm (commit to it, not just "vsock-ready"); dual-port (data+control) API spec; ADR-0002 gate answers; **connect-go-over-vsock feasibility check** ([ADR-0008](./adr/0008-internal-grpc-external-rest-mcp.md)).

**Acceptance.**
- New `agent/` Go module produces a static binary.
- Image rebuilt; entrypoint = `/usr/local/bin/sandbox-agent`.
- Provider templates carry `runtime_class`: `runc`, `sysbox`, `gvisor`.
- All existing MCP tools (bash/python/file/sub_agent) work via the new agent.
- **`POST /mcp` wire format unchanged** — same `tests/integration/test_mcp_*.py` pass against the new agent without modification (MCP-contract-frozen invariant).
- Performance: cold-start budget within sandboxd targets (sysbox ≤ 100 ms agent-ready).
- Dual-port API live: data plane (WS) + control plane (HTTP) — config rotation works without dropping streams.

**Reversibility.** New image tag; rollback by pinning prior image digest. (No data migration; agent is stateless.)

**Depends on.** Phase 6. Independent of Phase 8.

---

## Phase 8 — Egress proxy + audit pipeline ⚠️ (was Phase 9 — moved earlier)

**Goal.** JWT-allowlist egress proxy; structured audit pipeline with 90-day retention. **This is the foundation for any "untrusted-tier" claim — Phase 9 (Kata) cannot ship before this.**

**Blocker removed.** No L4/L7 egress control; logs scattered; no compliance-grade audit. Also: prerequisite for safely opening sandboxes to untrusted users.

**Research checklist.**
- `references/agentbox/` — full working JWT-allowlist proxy in Python. See [`research/09-agentbox.md`](./research/09-agentbox.md). Port to Go for production.
- `references/infra/packages/proxy/` — E2B's egress in Go; production scale. See [`research/02-e2b-infra.md`](./research/02-e2b-infra.md) §6 — three-port pattern (HTTP / TLS / other) is complementary to JWT auth.
- `references/docker-socket-proxy/` — see [`research/12-docker-socket-proxy.md`](./research/12-docker-socket-proxy.md) for the "filter before privileged API" pattern.
- DNS strategy: separate kube-dns vs proxy-resolves (decide in research doc).
- **Audit sink** — S3 + object-lock vs Loki vs both. Schema versioning. 90-day immutable retention.
- Output: `phase-8-research.md` — proxy implementation choice (port agentbox vs fork E2B vs compose-with-three-port-firewall), audit sink, DNS strategy, JWT refresh-token endpoint for sessions > 4 h.

**Acceptance.**
- Egress proxy deployed in `egress` namespace; sandbox egress goes through it.
- NetworkPolicy: sandbox can reach only proxy + kube-dns.
- L4 mints per-session JWTs; proxy validates signature + expiry + allowed_hosts on every request.
- Audit pipeline: events from L1/L3/L4 + egress proxy land in immutable sink with ≥ 90 d retention.
- **Templates without `egress_baseline` keep working** — egress allowlist is opt-in per template (matches Phase 5 sysbox internal-tier templates that may not need it).

**Reversibility.** Feature-flagged on the template level (template w/o egress allowlist = no egress controls applied, falls back to existing NetworkPolicy default-deny).

**Depends on.** Phases 5, 6.

---

## Phase 9 — Kata + Cloud Hypervisor for untrusted tier ⚠️ (was Phase 8 — moved later)

**Goal.** Hardware-grade isolation for public/untrusted Computer Use sessions. Multi-tier templates wired end-to-end. **Untrusted-tier templates require Phase 8 egress proxy to be in place** — otherwise an untrusted user inside a hypervisor still has unrestricted internet, which violates the "untrusted" claim.

**Blocker removed.** No hardware isolation; can't safely run untrusted users **(safely = Kata isolation + egress control from Phase 8 both present)**.

**Research checklist.**
- `references/cloud-hypervisor/cloud-hypervisor/` — REST API on unix socket, virtio-fs mount, vsock setup. See [`research/04-cloud-hypervisor.md`](./research/04-cloud-hypervisor.md).
- `references/firecracker/` and `references/firecracker-containerd/` — alternative path; snapshotting for fast cold start. See [`research/05-firecracker.md`](./research/05-firecracker.md) (especially the jailer pattern), [`research/11-firecracker-containerd.md`](./research/11-firecracker-containerd.md) (demux snapshotter).
- `references/kata-containers/` — full kata + CH integration; kata-deploy DaemonSet. See [`research/01-kata-containers.md`](./research/01-kata-containers.md).
- **nydus snapshotter / lazy image loading** — relevant when per-template images differ.
- Bare-metal node pool sizing (sandboxd's capacity formula → already pulled into `architecture/10-observability.md` in Phase 0.5).
- Output: `phase-9-research.md` — `kata-ch` vs `kata-fc` for our workload, bare-metal node sizing, RuntimeClass install steps, snapshotter choice (devmapper / nydus).

**Acceptance.**
- Reference deploy on RKE2 with bare-metal node pool runs `kata-ch` template successfully.
- Computer Use session on `kata-ch` template — CDP frame rate ≥ 10 fps; cold start p99 < 2 s (warm pool refilling).
- Helm chart documents bare-metal pool requirement.
- **Untrusted templates carry `egress_baseline` and are rejected by admission if Phase 8 proxy is not deployed.**

**Reversibility.** Templates are opt-in; sysbox tier remains default. Roll back by removing the `kata-*` templates and the bare-metal node pool.

**Depends on.** Phases 5, 7, **8**. Phase 8 is a hard prerequisite — without it, no template can be labelled "untrusted".

---

## Phase 10 — Snapshot/restore + HA (single-region) + multi-region foundations

**Goal.** Cloud Hypervisor snapshot/restore for pause-resume sessions. Single-region HA for L4 control plane. **Multi-region** is scoped as foundations only — the multi-region production deployment is a follow-up milestone.

**Scope (explicit).**
- ✅ In scope: pause/resume via snapshot/restore; L4 multi-AZ HA in **one region**; KV replicated across AZs; pod-failure mid-session → resume on a different pod via snapshot (not via in-memory affinity).
- ❌ Out of scope (deferred to a follow-up milestone): cross-region active-active routing, cross-region failover, latency-routed workspace proxies (see `architecture/08-networking.md` "Multi-region proxy pattern" — substrate is documented in Phase 0.5 but the implementation is Phase 11+).

**Blocker removed.** No HA, no pause-session, no cross-AZ pod-failure resilience.

**Research checklist.**
- `references/cloud-hypervisor/cloud-hypervisor/` — snapshot/restore API.
- `references/firecracker/` — Firecracker snapshot for comparison.
- `references/firecracker-containerd/` — demux snapshotter for COW rootfs (fast restore) — see [`research/11-firecracker-containerd.md`](./research/11-firecracker-containerd.md) §1.
- Multi-region: KV replication (Redis cluster / etcd multi-DC) — standard docs.
- **Post-restore hardening checklist** — kernel CRNG reseed on VM fork, `init_on_free=1`, `CAP_SYS_RESOURCE` drop. See [`research/15-claude-code-reverse-engineering.md`](./research/15-claude-code-reverse-engineering.md) §10.
- Output: `phase-10-research.md` — snapshot frequency policy; pod-failure mid-session → snapshot-then-restore-elsewhere flow; backup/DR.

**Acceptance.**
- Pause-resume Computer Use session demonstrably faster than cold start (target: ≤ 50 % of cold-start time).
- Multi-AZ L4 deployment; KV replicated across AZs.
- **Pod failure mid-session in multi-AZ setup → session resumes on a different pod via snapshot**, not via "lucky session affinity". Demonstrated end-to-end.
- Post-restore hardening checklist implemented (CRNG reseed, init_on_free, CAP_SYS_RESOURCE drop).
- DR runbook covers single-AZ outage.

**Reversibility.** Snapshot feature opt-in via template; multi-AZ topology opt-in via deployment values.

**Depends on.** Phases 6, 9.

---

## How the loop works (per phase)

1. **Research** — investigate the listed `references/` repos + external docs. Produce `phase-N-research.md` under this directory.
2. **Discuss + sign off** — present `phase-N-research.md` to owner; iterate; lock the decisions.
3. **Plan** — invoke `gsd-plan-phase` to break the phase into atomic tasks.
4. **Execute** — implement on a `dev/future-architecture/phase-N-*` branch.
5. **Verify** — acceptance criteria from this doc.
6. **Merge** — PR into `dev/future-architecture` (default) or `main` (if independently shippable).

See [README.md](./README.md) — Branching strategy. See [`phase-template.md`](./phase-template.md) for the exact `phase-N-research.md` / `phase-N-plan.md` skeletons.

---

## Failure modes & cross-phase retros

What to do when Phase N reveals that Phase M (M < N) was wrong. Tracks the "non-blocking" invariant by making mid-flight corrections cheap.

### Detection signals

A phase has uncovered an upstream flaw when any of these appear:
- Phase N's research doc explicitly cannot fit within the existing interface from Phase M (e.g. Phase 5 finds the `SandboxProvider` signature from Phase 1 forces an awkward k8s impl).
- Phase N's plan needs to modify files outside its declared scope.
- A previously-merged acceptance test starts failing in Phase N.
- The same antipattern gets re-introduced — meaning the lock from Phase M wasn't actually load-bearing.

### Response menu (pick one, document in `phase-N-research.md`)

| Severity | Response | When to pick |
|---|---|---|
| **A. Patch in place** | Add a small fix to the deliverables of Phase N. No new phase. | Flaw is local; fix < 1 day; no contract change. |
| **B. Insert Phase M.5** | New phase ships before Phase N continues. Sized like Phase 0.5: docs + 1–2 small code changes. | Contract change affects ≤ 2 downstream files; you can pause Phase N for a sprint. |
| **C. Supersede ADR** | New ADR records the reversal; old one marked Superseded. Phase N still ships; new ADR drives future work. | Decision was wrong; code already shipped on the old decision; replacing it now is too expensive. |
| **D. Accept as known debt** | Document in `architecture/11-known-debt.md` (create if missing); flag phase that will repay. | Cost of fix > value; future phase will rewrite the area anyway. |

### Forbidden response

- **Silently rework upstream code mid-phase.** If Phase 5 touches Phase-1-shipped files without one of A/B/C/D being chosen → rejected at PR review. The cross-phase decision must be explicit.

### Worked example (hypothetical)

> Phase 5 (k8s provider) research finds that `SandboxProvider.Exec` returns `stream<bytes>` but k8s `connect_get_namespaced_pod_exec` returns paired `stdout` + `stderr`. Patching in place (A) would break the `.proto`. Inserting Phase 4.5 (B) adds an `Exec` v2 returning `stream<ExecChunk{kind, bytes}>` with old and new served simultaneously. Old marked deprecated; Phase 6 drops the old after Go control plane lands.

---

## Rollback runbook (per phase)

One-paragraph "if this phase causes a prod incident, here is the rollback". Each phase's own `phase-N-research.md` carries the detailed version per [`phase-template.md`](./phase-template.md); this is the index.

| Phase | Rollback in ≤ N minutes | Mechanism |
|---|---|---|
| 0.5 | < 5 | `git revert` the docs commit |
| 1 | < 10 | Re-inline provider methods; provider abstraction is additive — old call sites still exist for one release |
| 2 | < 2 | Flip `SANDBOX_PROVIDER=docker_socket` (default already this) |
| 3 | < 30 | Disable S3 mount in template; FUSE sidecar removed; orchestrator falls back to local-FS bind |
| 4 | < 5 | Flip `SECRET_BROKER=static`; fall back to env-at-create-time |
| 5 | < 30 | Helm `--set runtime.legacy=true` reactivates `values-legacy-dind.yaml` |
| 6 | < 5 | Reverse-proxy weights → 100 % Python; Go service idle, sessions drain to Python |
| 7 | < 5 | Pin previous image digest in template `image.ref` |
| 8 | < 2 | Template's `egress_baseline` deleted → NetworkPolicy default-deny still applies but proxy bypassed |
| 9 | < 10 | Untrusted templates marked `disabled: true`; sysbox tier still default |
| 10 | < 30 | Snapshot opt-in flipped off; multi-AZ remains but no snapshot/restore |

If a rollback can't fit its target window → the phase shipped wrong; the next phase's first deliverable is to shrink the window.
