# Target Architecture: Kubernetes-friendly Open Computer Use

> **Status:** Draft. No code in this document has shipped yet. The Docker
> Compose deployment (`docker-compose.yml`, `docker-compose.webui.yml`)
> remains the primary supported path until phases below land.

This document describes the target architecture for running Open Computer
Use on Kubernetes alongside the existing Docker Compose stack. It is the
reference for the phased delivery plan in [`roadmap.md`](roadmap.md).

## Goals

1. **Run unchanged on any Kubernetes cluster** — managed (EKS, GKE, AKS),
   self-hosted, or bare-metal. No dependency on a specific cloud provider.
2. **Preserve the Docker Compose path** — single-node operators keep the
   existing experience; nothing they rely on is removed.
3. **Avoid exotic infrastructure** — no `ReadWriteMany` (RWX) storage,
   no proprietary CSI drivers, no cluster-wide privileged daemons.
4. **Stay open-source friendly** — every dependency has a public,
   permissively licensed implementation that contributors can run locally.
5. **Leave a clear path to stronger isolation** — Phase 2 can opt into
   VM-class sandboxing without rewriting the orchestrator.

## Non-goals (for the initial Kubernetes work)

- Building our own object-storage service. Use S3-compatible backends
  (AWS S3, MinIO, Cloudflare R2, Backblaze B2, Ceph RGW, …).
- Building a custom guest agent. The existing entrypoint plus MCP server
  inside the workspace image is sufficient.
- Live migration of running workspaces between nodes.
- L7 egress filtering. `NetworkPolicy` covers L3/L4; richer policy is
  out of scope until an enterprise need shows up.

## Architecture overview

```
                        ┌──────────────────────────────┐
                        │  Open WebUI (or any MCP host)│
                        └──────────────┬───────────────┘
                                       │ MCP / HTTP
                                       ▼
                        ┌──────────────────────────────┐
                        │  computer-use-server         │
                        │  (orchestrator, FastAPI)     │
                        │                              │
                        │  RuntimeBackend interface    │
                        │   ├── DockerBackend          │
                        │   └── K8sBackend             │
                        │                              │
                        │  Warm-pool manager           │
                        │  Skill registry / squashfs   │
                        │  S3 client (boto3)           │
                        └─┬──────────────┬─────────────┘
                          │              │
                K8s API   │              │  S3 API
                          ▼              ▼
              ┌────────────────────┐  ┌──────────────────────┐
              │ Workspace Pod      │  │ Object Store         │
              │  (one per chat)    │  │  - skills/*.squashfs │
              │                    │  │  - chats/<id>/*      │
              │  rootfs (eph/PVC)  │  │  - lifecycle TTL     │
              │  /opt/skills/*    ←┼──┘                      │
              │  /mnt/user-data/* ←│  via FUSE sidecar       │
              │                    │                          │
              │  entrypoint + MCP  │                          │
              └────────────────────┘                          │
                                                              ▼
                                                    cleanup via
                                                    bucket lifecycle
```

## Storage model

The single most important architectural decision is how data is laid out
across four tiers, each with a clear lifetime and access pattern.

| Tier | Purpose | Lifetime | Access | Implementation |
|------|---------|----------|--------|----------------|
| **1. Image** | Base OS, language runtimes, browsers, MCP server | Pinned to image tag | RO, baked in | OCI image, pulled and cached by node kubelet |
| **2. Skills** | Runtime tools: pptx, docx, xlsx, sub-agent, … | Per-version, immutable | RO, mounted | Each skill packaged as a `squashfs` blob, fetched from object store at workspace start |
| **3. Workspace home** | Per-chat working directory (`/home/assistant`) | Per-chat | RW, exclusive | Ephemeral by default (Pod ephemeral storage); optional RWO `PersistentVolumeClaim` for chats that must survive a pod restart |
| **4. User data** | `uploads`, `outputs`, archived results | Per-chat | RO/WO depending on subdir | Object storage with chat-scoped key prefix, mounted via FUSE sidecar (e.g. `rclone mount`, `mountpoint-s3`) |

### Why these choices

- **No RWX storage anywhere.** Every mount is either RO (skills, uploads,
  tool-results) or single-writer (workspace home, outputs). Single-writer
  patterns work on `ReadWriteOnce` block storage that every cloud and
  every CSI driver supports out of the box.
- **Skills are immutable artifacts.** A skill at version *v* is the same
  bytes everywhere. Promoting a new version is a registry push, not a
  filesystem mutation. This makes hot-reload semantics simple ("attach
  the new blob to the next workspace that starts") and makes per-tenant
  skill sets trivial (different blob list in `WorkspaceSpec`).
- **User data is namespaced by path, not by volume.** A single bucket
  holds all chats; per-chat isolation is the bucket prefix
  `chats/<chat-id>/`. Cleanup is a lifecycle policy on the bucket; we
  never have to enumerate K8s `PersistentVolumeClaim` objects for it.
- **Workspace home is the only thing that may need real persistence.**
  Most chats are short-lived enough that ephemeral storage is correct.
  Long-lived "saved" chats can opt into a RWO PVC; the orchestrator
  controls this via `WorkspaceSpec.home_persistence`.

### Object store compatibility

Every storage interaction is over the S3 protocol with a configurable
endpoint:

```
S3_ENDPOINT_URL=http://minio:9000          # local docker-compose
S3_ENDPOINT_URL=https://s3.amazonaws.com    # AWS
S3_ENDPOINT_URL=https://<acct>.r2.cloudflarestorage.com   # R2
S3_ENDPOINT_URL=https://storage.googleapis.com            # GCS interop
```

The Docker Compose stack ships a MinIO service so single-node operators
get the same code paths as cloud deployments without registering for an
external account.

## Runtime backends

The orchestrator talks to its workspace runtime through a `RuntimeBackend`
interface. Two implementations ship:

- **`DockerBackend`** — the existing Docker-socket-based code path,
  refactored behind the interface. Default on Compose.
- **`K8sBackend`** — Kubernetes Python client; creates `Pod`s (or
  optionally `Deployment`s with `replicas=0/1`) and uses
  `connect_get_namespaced_pod_exec` for the same `exec` channel the
  Docker backend uses today.

```python
class RuntimeBackend(Protocol):
    async def ensure_workspace(chat_id: str, spec: WorkspaceSpec) -> Workspace
    async def get_workspace(chat_id: str) -> Workspace | None
    async def get_address(chat_id: str) -> str | None    # routable IP for CDP/ttyd proxy
    async def exec(chat_id: str, cmd: list[str], **opts) -> ExecResult
    async def exec_stream(chat_id: str, cmd: list[str]) -> AsyncIterator[bytes]
    async def remove(chat_id: str) -> None
    async def list_workspaces() -> list[Workspace]
```

`WorkspaceSpec` is a backend-agnostic description:

```python
@dataclass
class WorkspaceSpec:
    image: str
    env: dict[str, str]
    cpu: float                       # vCPU
    memory: str                      # "2Gi"
    skills: list[SkillRef]           # squashfs blobs to attach
    user_data_namespace: str         # chat_id; becomes object-store prefix
    home_persistence: Literal["ephemeral", "persistent"]
    runtime_class: str | None        # e.g. "kata-fc" in Phase 2
```

The browser CDP and terminal proxies in `app.py` already work against a
routable IP. They keep working unchanged: the Docker backend returns the
container's network address, the Kubernetes backend returns
`pod.status.podIP`. No proxy logic moves.

## Workspace lifecycle and warm pool

Cold-creating a Kubernetes Pod typically takes several seconds even after
image pull is cached, dominated by scheduling, CSI volume attach, and
container start. To match the responsiveness of `docker run`, the
`K8sBackend` maintains a small **warm pool** of pre-started, idle Pods.

- The pool runs *N* (default 2–5) workspace Pods with a generic identity
  and no chat assigned.
- When a new chat arrives, the orchestrator atomically claims one Pod
  from the pool by relabelling it (`chat-id=<id>`), injects per-chat
  environment, and returns it as ready. Time-to-ready is dominated by
  the relabel + env injection round-trip, typically a few hundred
  milliseconds.
- A background task replenishes the pool to size *N*.
- On image change (new workspace tag), the pool is drained and rebuilt.

This is independent of the storage tier and works with both the
ephemeral and persistent home choices.

## Isolation tiers

Two runtime classes are supported, selected per workspace via
`WorkspaceSpec.runtime_class`:

| Tier | When to use | Trade-offs |
|------|-------------|------------|
| `runc` (default) | Trusted code, internal teams, dev/test | Shared kernel, fastest cold start, broadest compatibility |
| `kata-fc` (Kata Containers on Firecracker) | Untrusted code, public multi-tenant deployments | Real VM boundary per workspace, requires Kata installed on nodes; slightly slower start, occasional driver/feature gaps |

`gVisor` is intentionally not in the matrix: its compatibility envelope
is too narrow for the workloads Open Computer Use runs (Chromium with
sandbox flags, Playwright, browser downloads). If a deployment needs
hardware-level isolation, `kata-fc` is the right tool.

Selecting a runtime class is a `PodSpec.runtimeClassName` field — no
code changes are required beyond plumbing the value through
`WorkspaceSpec`. Cluster admins install the runtime once via DaemonSet
or pick a managed offering that includes it.

## Network and security

- **Per-namespace `NetworkPolicy`** denies workspace-to-workspace
  traffic and workspace-to-Kubernetes-API traffic by default. Egress
  to the public internet plus the orchestrator's port is allowed.
- **`ResourceQuota` and `LimitRange`** cap blast radius per namespace.
- **ServiceAccount per workspace** (or one shared, RBAC-empty SA) so the
  workspace cannot enumerate or modify cluster state.
- **`securityContext`**: `runAsNonRoot`, `allowPrivilegeEscalation: false`,
  drop all capabilities, `seccompProfile: RuntimeDefault`. The Docker
  setup's `security_opt: no-new-privileges` translates directly.
- **Secrets** for API keys (Anthropic, vision, GitLab, …) come from
  `Secret` objects via `envFrom`, created per chat or shared per
  namespace depending on tenancy model.

## Cleanup

The current `cron/` reaper container moves into the orchestrator process
as a background asyncio task. It uses
`RuntimeBackend.list_workspaces()` to enumerate and
`RuntimeBackend.remove(chat_id)` to terminate, so the same code drives
both backends.

Object-store cleanup is handled out-of-band by the bucket's lifecycle
policy (default: expire `chats/*` after 7 days). The orchestrator never
walks the bucket itself.

## What does **not** change

- The MCP tool surface and JSON-RPC protocol.
- The system-prompt rendering pipeline.
- The browser CDP and terminal WebSocket proxies in `app.py`.
- `cli_runtime.py` and the multi-CLI sub-agent code path.
- The workspace `Dockerfile`. The same image is used by both backends;
  the registry it is pulled from is a deployment concern.
- The Open WebUI integration (`openwebui/` directory).

## Open questions

These decisions are deferred until prototypes provide evidence:

- **Squashfs mount mechanism on `runc`**: kernel `mount -t squashfs`
  needs `CAP_SYS_ADMIN`, while `squashfuse` works in user space at the
  cost of needing FUSE in the Pod. Validate which is preferred for
  Phase 1 once we have a measurement.
- **FUSE sidecar choice for user data**: `rclone mount`, `mountpoint-s3`,
  and `geesefs` have different write semantics. `mountpoint-s3` only
  supports sequential writes which suits `outputs/` but may break some
  tools that write atomic temp files. To be measured before commitment.
- **Warm pool sizing heuristics**: static *N* is fine to start; whether
  to scale with cluster load is a Phase 2 question.
- **PVC pool vs. per-chat dynamic provisioning** for the persistent
  home option. Pool reduces volume-attach latency at the cost of
  pre-allocated capacity.

Each open question becomes a small prototype PR with measurements
attached. None blocks the Phase 1 refactor that exposes
`RuntimeBackend`.
