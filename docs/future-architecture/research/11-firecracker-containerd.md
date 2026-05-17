# 11 — firecracker-containerd (FC via containerd + COW snapshotter)

> Source: [`references/firecracker-containerd/`](../../../references/firecracker-containerd/). AWS's containerd integration for Firecracker.
> Relevant for [Phase 9](../roadmap.md) (kata-fc alternative path) and [Phase 10](../roadmap.md#phase-10--snapshotrestore--multi-region) (COW snapshotting for fast cold-start / warm pool).

## 1. Demux snapshotter — out-of-VM proxy ⭐

- **Where.** `snapshotter/README.md`; `snapshotter/demux/snapshotter.go` (Prepare:109, Commit:145, Remove:159, Usage:77); `snapshotter/app/service.go`; cache: `snapshotter/demux/cache/cache.go`.
- **What.** containerd snapshotter plugin that proxies snapshot ops (Prepare/Commit/Remove/Mounts) **over vsock** to remote snapshotters running **inside** the microVM. In-VM snapshotter resolves via `GET /address?namespace={vmid}` → vsock socket path + metrics port.
- **Why for Phase 10.** **The** enabler for COW rootfs and warm-pool cold-start. Workflow:
  1. Prepare snapshot from parent (immutable base image) → CoW view.
  2. Commit on container exit → releases snapshot resources.
  3. All I/O through in-VM snapshotter for block-level dedup.
- **For us.** Reference for our snapshot strategy in Phase 10 — even if we go with Cloud Hypervisor primary, this is the **architectural pattern** for "snapshotter inside the VM, control plane outside".

## 2. vsock + TTRPC agent ↔ shim handshake

- **Where.** Shim: `runtime/service.go` (vmReady channel, `agentClient taskAPI.TaskService` at line 138, vsock port allocation 74–76). Agent: `agent/service.go` (TaskService wrapping runc 46–72). Proto: `proto/firecracker.proto` (CreateVM, PauseVM, ResumeVM, StopVM, GetVMInfo, SetMetadata). Dial pattern: `runtime/service.go:~607` (`vsock.DialContext`).
- **What.**
  1. **VM bootstrap** — `CreateVM` spins up FC, waits for agent on vsock (vmReady channel).
  2. **Task routing** — Create/Exec/Delete/Kill from shim → agent over ttrpc-vsock.
  3. **Port allocation** — per-container unique vsock I/O port (min 11000, allocated at runtime/service.go 432–443).
  4. Agent **wraps `runc.New()`** (agent/service.go:99) — forwards containerd task API directly. Containers-in-VMs transparent to the containerd control plane.
- **Why for us.** Phase 9 — exact model for how a host-side shim talks to an in-VM agent. We adopt the **bootstrap timing + vsock port lifecycle** pattern; we **skip TTRPC** in favor of HTTP+WS (per ADR direction).

## 3. Control API — VM lifecycle ≠ task lifecycle

- **Where.** `proto/firecracker.proto` (CreateVMRequest, CreateVMResponse), `firecracker-control/service.go`, `runtime/service.go`.
- **What.** Two-layer API:
  - **VM lifecycle** (control plugin) — long-lived, multi-container.
  - **Task lifecycle** (V2 runtime shim) — per-container, short-lived.
  - **Reuse pattern**: orchestrator calls `CreateVM` once per workload group → VMID reused for N task creates → mounts different drives per task → **`ExitAfterAllTasksDeleted: true`** auto-cleans the VM when last task exits.
- **vs Kata.** Kata creates 1 VM per pod (1:1). firecracker-containerd reuses 1 VM across M tasks (1:M) → much higher density for short-lived workloads.
- **For us.** Phase 9 — **interesting alternative** to the per-session VM model. Trade-off: 1:M reuse → less per-session isolation. Use only for tightly-related batches inside same tenant; never across tenants.

## 4. Drive mounting — pre-allocated stubs + dynamic updates

- **Where.** `proto/firecracker.proto` (RootDrive, DriveMounts, ContainerCount); `runtime/service.go:CreateContainerStubs()`; `agent/drive_handler.go` (in-VM mount handler, MountDrive TTRPC).
- **What.** Firecracker has **no hot-plug**. Workaround:
  1. Runtime pre-allocates N stub drive files on VM creation (`ContainerCount`).
  2. At task-creation, runtime updates `FirecrackerConfig.Drives[i].Path` to actual container image **while VM runs**.
  3. CoW via the demux snapshotter (§1) — each container's rootfs is a unique snapshot.
- **For us.** Phase 10 warm-pool insight: even Firecracker's no-hot-plug limit can be worked around with **pre-allocation**. One VM with 32 stub drives = 32 sequential containers without reboot.

## 5. Network setup — TC redirect + CNI chain

- **Where.** `docs/networking.md` (rationale 62–110), `runtime/service.go:1031-1046` (NetworkInterfaces).
- **What.** Linux Traffic Control U32 filter redirects packets between VM's TAP device ↔ veth in a CNI-configured netns. CNI chain: `[ptp (veth) → tc-redirect-tap (redirect veth ↔ tap)]`.
- **Why.**
  - **TC redirect** = ~10–20 % CPU savings vs bridge.
  - **Chained CNI** = composable policy (DNS via host-local IPAM, internet via `ipMasq=true`).
  - **Per-VM netns isolation** = multi-tenant ready.
  - **No VM IP needed** — TC redirect lets guest see same MAC/IP as veth → DHCP-free boot.
- **For us.** Phase 9 — reference network pattern when wiring kata-fc templates; documents how CNI chains compose under Firecracker.

## 6. Metrics & logging — FIFOs + HTTP discovery for snapshotter

- **Where.** `proto/firecracker.proto:40-41` (LogFifoPath, MetricsFifoPath); `docs/logging.md` (per-library log levels); `snapshotter/README.md` (Prometheus `GET /metrics/{port}`).
- **What.** FC metrics + logs → named pipes (FIFOs). Snapshotter metrics discovered via HTTP resolver. Per-library log levels (`firecracker:debug`, `firecracker-containerd:error`, etc.).
- **For us.** Phase 10 warm-pool health — drain FIFOs periodically; alert on stall. Use snapshotter metrics for CoW efficiency (snapshot count, dedup ratio).

## 7. Task lifecycle — cleanup-stack pattern

- **Where.** `agent/service.go` (`execCleanups` map 50–51, `addCleanup`/`doCleanup` 132–150); `runtime/service.go`.
- **What.** Each Create registers rollback handlers; on failure or Delete, run in **reverse order**. Multi-container per VM works because `ExitAfterAllTasksDeleted` is checked before VM shutdown.
- **For us.** Phase 9 — clean pattern for "any step of sandbox-create fails → unwind cleanly". Same shape as E2B's multi-resource rollback ([`02-e2b-infra.md`](./02-e2b-infra.md) §4).

## 8. When to pick this over kata-fc?

| Dimension | firecracker-containerd | kata-fc |
|---|---|---|
| VM : task | 1 : M | 1 : 1 |
| Cold start | CoW via demux snapshotter | devmapper snapshots |
| Network setup | Manual CNI + TC redirect | Kata handles CNI |
| Warm pool fit | **Excellent** | Good |
| Boot latency | ~100 ms | 200–400 ms |
| K8s native | Indirect (containerd) | Direct (RuntimeClass) |

**Use firecracker-containerd when** workload is many-short-tasks-per-VM (serverless-shaped); snapshotter-driven cold-start matters; want containerd API without k8s overhead; need <100 ms cold start via VM reuse.

**Use kata-fc when** target is Kubernetes (CRI-standard, RuntimeClass); 1 VM : 1 pod is acceptable; want mature ecosystem.

**Our default = kata-fc** (Phase 9). firecracker-containerd is on the table for a future high-density tier where a single trusted-tenant batch can share one VM (rare; doesn't match Computer Use's per-session model).

## Phase-10 takeaways

1. **Demux snapshotter** is the architectural pattern for fast cold start — *snapshotter lives inside the VM, control plane outside*. Adapt to Cloud Hypervisor + virtio-fs in our snapshot pipeline.
2. **Pre-allocated stub drives** work around hypervisor hot-plug limits — useful template-design knowledge.
3. **Cleanup-stack pattern** standardizes rollback across our spawn pipelines.
4. **FIFOs drain in real time** — observability pipeline must keep up.
