# Roadmap: Kubernetes-friendly Open Computer Use

> **Status:** Draft. Phases below are ordered, but each ships
> independently. The Docker Compose stack continues to be supported in
> every phase. Operators are never forced to migrate.

This roadmap delivers the architecture in
[`k8s-architecture.md`](k8s-architecture.md) in small, reviewable steps.
Every phase produces a useful artifact on its own; if work pauses
between phases, the project is still in a coherent state.

## Guiding principles

- **No flag day.** Each phase is additive and gated by configuration.
  Existing users see no behavioural change unless they opt in.
- **Refactor before features.** The `RuntimeBackend` interface lands
  before any new backend, so the diff that adds Kubernetes is small and
  isolated.
- **Prove with prototypes.** Open questions in
  [`k8s-architecture.md`](k8s-architecture.md#open-questions) are
  resolved with measured prototypes, not by debate.
- **Single workspace image.** Both backends pull from the same
  registry. We do not maintain a separate "Kubernetes image".

## Phase 1 — Runtime abstraction (no behaviour change)

**Goal:** Make the orchestrator backend-agnostic without altering
runtime behaviour. Existing Docker Compose users see no difference.

- Extract the `RuntimeBackend` `Protocol` and the `WorkspaceSpec` /
  `Workspace` data classes from the current `docker_manager.py`.
- Move the existing logic into `runtime/docker_backend.py` as the
  default implementation. Same code, new home.
- Plumb a `RUNTIME_BACKEND` environment variable; `docker` is the
  default and only valid value at the end of this phase.
- Update `app.py`, `mcp_tools.py`, `cli_runtime.py` callers to go
  through `runtime.get_backend()` instead of importing
  `docker_manager` directly.
- Tests pass unchanged.

**Exit criteria:** All current functionality works against the new
abstraction. No new dependencies. PR is a pure refactor.

## Phase 2 — Object-store backed user data (Compose first)

**Goal:** Replace per-chat host bind mounts under
`/tmp/computer-use-data/<chat-id>/` with S3-compatible object storage.
Land it on Docker Compose first, where the change is contained, and
keep the `K8sBackend` work decoupled.

- Add a MinIO service to `docker-compose.yml`. Use it as the default
  backend for local development and CI.
- Introduce `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`,
  `S3_BUCKET_DATA` configuration. The orchestrator uses `boto3` against
  the configured endpoint.
- Refactor uploads/outputs handlers in `app.py` to read and write
  through the S3 client; the public HTTP API
  (`/api/uploads/...`, `/files/...`) is unchanged.
- Workspace containers receive `uploads`/`outputs`/`tool-results`
  through a FUSE sidecar (or init-pull, behind a config flag) that
  scopes the mount to `chats/<chat-id>/`.
- `BASE_DATA_DIR` becomes either a local path (legacy) or an S3 prefix
  (new path), selected by configuration.

**Exit criteria:** Compose deployment runs end-to-end against MinIO.
Bucket lifecycle policy replaces filesystem cleanup for user data. The
host-bind code path is still available for one release as a fallback.

## Phase 3 — Skills as squashfs blobs

**Goal:** Replace per-skill ZIPs and host-path bind mounts with
immutable squashfs artifacts in object storage.

- Build skills as `.squashfs` blobs at release time
  (`mksquashfs skills/<name> skills/<name>.squashfs`).
- Push blobs to the same object store, under `skills/<name>/<version>/`.
- Update `skill_manager.py` to fetch the blob list per user / per
  tenant, attach blobs at workspace start (Compose: bind into the
  container; Kubernetes: emerge in Phase 4).
- Drop the ZIP-cache + atomic-replace mechanism in
  `skill_manager.py`. Hot-reload becomes "next workspace start picks
  up the new version".
- Document the immutability contract: a skill version is the same
  bytes everywhere, forever.

**Exit criteria:** All bundled skills ship as squashfs blobs. Compose
users transparently get the new pipeline. Per-user skill selection
(today's `get_user_skills_sync`) continues to work.

## Phase 4 — Kubernetes backend

**Goal:** Ship the `K8sBackend` and a Helm chart that operators can
use to deploy the full stack on any Kubernetes cluster.

- Implement `K8sBackend` against `kubernetes-asyncio`. Pod creation,
  exec, log streaming, removal.
- Mount squashfs skill blobs in workspace Pods (`squashfuse` sidecar
  or init-container, depending on Phase 1's open-question result).
- Mount user-data prefix via FUSE sidecar.
- Expose CDP and ttyd through the existing orchestrator-side
  WebSocket proxies. Pod IP is the routable target; no per-Pod
  Service is created.
- Helm chart `charts/open-computer-use/` covering: orchestrator,
  Open WebUI, MinIO (optional), workspace Pod template (ConfigMap),
  `NetworkPolicy`, RBAC, `ResourceQuota`.
- CI test against `kind` running the same end-to-end test suite that
  Compose uses.

**Exit criteria:** A new operator can `helm install` the chart and
get the same UX as `docker compose up`, on any cluster. Both
backends share more than 90 % of their code path.

## Phase 5 — Warm pool + cleanup migration

**Goal:** Bring cold-start latency on Kubernetes down to parity with
Compose, and replace the standalone cleanup cron.

- Implement the warm-pool manager described in
  [`k8s-architecture.md`](k8s-architecture.md#workspace-lifecycle-and-warm-pool).
- Expose a monotonic `worker_epoch` on the `Workspace` identity
  returned by `RuntimeBackend.ensure_workspace`. Clients reconnecting
  after a pool recycle compare epoch values; a mismatch signals
  "different underlying workspace, re-initialize per-chat state".
  Without this, a tool-call arriving on a recycled Pod can land
  against stale orchestrator-side assumptions.
- Move the reaper loop from `cron/` into the orchestrator as an
  asyncio background task. It calls
  `RuntimeBackend.list_workspaces()` so the same code drives both
  backends.
- Surface metrics (`prometheus_client`): pool size, claim latency
  histogram, workspace lifetime, reap counts, epoch increments.

**Exit criteria:** Pool hit gives sub-second time-to-ready in a real
cluster. Compose users get cleanup-via-orchestrator and can remove
the `cleanup` service from their compose file.

## Phase 6 — Optional: VM-class isolation

**Goal:** Offer hardware-level isolation for deployments that execute
fully untrusted code, without changing the orchestrator API.

- Document supported runtime classes (`kata-fc`, possibly others).
- Add `WorkspaceSpec.runtime_class`; `K8sBackend` plumbs it to
  `PodSpec.runtimeClassName`.
- Provide example values files for clusters with Kata Containers
  preinstalled.
- Validate Chromium / Playwright / ttyd compatibility under
  `kata-fc`. Document any flags or limitations.

This phase is opt-in. Most deployments will keep `runc`. Operators
who need a real VM boundary can flip a single field.

**Exit criteria:** A cluster admin who installs Kata Containers can
set `runtime_class: kata-fc` in chart values and run workloads in
microVMs without further code changes.

## Tracking

- Each phase opens a tracking GitHub Issue with the corresponding
  document section linked.
- Phase status (`planned` / `in progress` / `delivered`) is reflected
  in the table below as PRs land.
- When a phase is fully delivered, its content moves into the main
  `docs/` tree (e.g. `INSTALL.md` gets a Kubernetes section) and the
  draft section here is shortened to a pointer.

| Phase | Topic | Status |
|-------|-------|--------|
| 1 | `RuntimeBackend` refactor | Planned |
| 2 | Object-store user data (Compose) | Planned |
| 3 | Skills as squashfs blobs | Planned |
| 4 | Kubernetes backend + Helm chart | Planned |
| 5 | Warm pool + cleanup migration | Planned |
| 6 | Optional VM-class isolation | Planned |

## What stays compatible across all phases

- `docker compose up` keeps working from Phase 1 through Phase 6.
- The MCP protocol surface is untouched.
- Existing skill packages keep working through Phase 2; Phase 3
  changes the *packaging format* but not the *authoring experience*.
- The Open WebUI integration is unchanged. It only sees the
  orchestrator HTTP API, which does not move.

If a phase ever requires a breaking change for Compose users, it will
be called out explicitly in `CHANGELOG.md` with a migration path.
