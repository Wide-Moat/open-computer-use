<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# 05 — Firecracker (kata-fc backend, fastest-cold-start tier)

> Source: [firecracker-microvm/firecracker](https://github.com/firecracker-microvm/firecracker). AWS Lambda/Fargate microVM.
> Backend for [Phase 9](../roadmap.md) `kata-fc` (free-trial / fastest-cold-start tier). Cloud Hypervisor remains primary; FC fills the "smallest attack surface" niche.

## 1. REST API on unix socket — synchronous-only

- **Where.** `src/vmm/src/rpc_interface.rs:50-150` (`VmmAction` enum), `src/firecracker/swagger/firecracker.yaml`.
- **What.** HTTP/1.1 only (no HTTP/2). All actions are `VmmAction` variants. States: `NotStarted` → `Running` → `Paused` → snapshot/resume. Pause is mandatory before snapshot.
- **Why for us.** Phase 9 alternative backend. No streaming → cleaner than CH for "give me a sandbox now" path.
- **Skip.** No WebSocket / no async jobs.

## 2. Jailer — privilege-drop wrapper

- **Where.** `src/jailer/src/main.rs:1-250`, `src/jailer/src/chroot.rs:19-100`, `src/jailer/src/cgroup.rs`, `src/jailer/src/env.rs`.
- **What.** Stateless wrapper binary that, before exec'ing firecracker, does:
  - **Mount namespace isolation:** `unshare(CLONE_NEWNS)` → `pivot_root()` → umount old_root.
  - **Chroot via bind-mount + pivot_root** (not naive `chroot()`).
  - **uid/gid drop** (`--uid`, `--gid`).
  - **Cgroup placement** (v1 & v2 — moves FC pid into a child cgroup).
  - **Optional `--netns`** (network-ns inheritance).
  - **Seccomp filters** loaded by firecracker itself after jailer execs it.
- **Why for us.** This is the standard hypervisor-hardening pattern. Our Phase 9 Helm/CRD work for `kata-fc` templates should use jailer-equivalent containment, even if the orchestrator wraps CH instead.
- **Skip.** Assumes host enforces file perms; no AppArmor/SELinux integration. `resource_limits` moved to cgroups in the 2024 release.

## 3. MMDS — guest metadata service (EC2-compatible)

- **Where.** `src/vmm/src/mmds/data_store.rs:1-230` (JSON store, 51.2 KB default limit), `src/vmm/src/mmds/ns.rs` (TCP), `src/vmm/src/mmds/token.rs` (V2 session tokens), `docs/device-api.md:26`.
- **What.**
  - In-process metadata server at `169.254.169.254` (EC2-compatible).
  - **V1**: no auth, deprecated.
  - **V2**: session token (HMAC), required for cross-tenant safety on shared hosts.
  - JSON tree set via `PUT /mmds`, patched via `PATCH`.
  - **Requires** a virtio-net device to enable.
  - **Not persisted across snapshots** — config saved, data store cleared. Reconfigure on restore.
- **Why for us.** Phase 9 — cheap, no-network bootstrap of guest config (env vars, JWT for L4 callback). Replaces a chunk of what we'd otherwise do through `/v1/configure` for VM-class templates.
- **Skip.** No nested auth; V2 tokens are simple HMAC.

## 4. Snapshot / restore — files + memory mmap + versioning

- **Where.** `src/vmm/src/persist.rs:1-100` (`MicrovmState`), `docs/snapshotting/snapshot-support.md:32-172`, `src/vmm/src/rpc_interface.rs:67, 98`.
- **What.**
  - Files: (1) memory file (guest RAM), (2) vmstate (JSON + bincode + 64-bit CRC32), (3) disk files (user-managed).
  - Restored via `MAP_PRIVATE` mmap → on-demand paging + COW.
  - Versioning `MAJOR.MINOR.PATCH` — incompat versions rejected.
  - Boot from snapshot < 125 ms.
  - **vsock connections closed on snapshot** (listening sockets survive).
  - **Network connection state not guaranteed.**
  - No built-in encryption — user-managed at the storage layer.
- **Why for us.** Phase 10. Snapshot file lifetime ≥ resumed VM lifetime.
- **Caveat.** GIC version (aarch64) must match between snapshot and restore hosts.

## 5. Memory & resource limits

- **Where.** `src/vmm/src/vstate/memory.rs`, `src/vmm/src/resources.rs:1-100`, jailer cgroup integration.
- **What.**
  - Guest RAM as anonymous mmap (or hugepages if configured). 1 MiB → 32 TiB theoretical.
  - **Oversubscription enabled by default** — host OOM killer can evict.
  - 1–32 vCPUs per microVM.
  - virtio-mem hotplug **advertised but not optimized** — don't rely on dynamic memory in practice.
- **Why for us.** Phase 9 — predictable per-VM cost (~5 MiB VMM overhead). Densely pack idle microVMs.

## 6. Seccomp filters

- **Where.** `src/vmm/src/seccomp.rs:1-137`, `docs/seccomp.md:1-87`, `resources/seccomp/` (JSON rules).
- **What.**
  - **Compiled at build time** (`seccompiler-bin` → bitcode embedded in binary).
  - Per-thread filters: vmm, api, vcpu (separate allowlists).
  - Max 4096 BPF instructions/filter.
  - Override at runtime: `--seccomp-filter <path>`.
  - **Never disable in prod** (`--no-seccomp`).
- **Why for us.** Phase 9 — direct lesson: per-thread allowlists. Don't write one big filter; segment by thread role.

## 7. Logging & metrics — named-pipe drain, best-effort

- **Where.** `src/vmm/src/logger/`, `docs/metrics.md`, `src/vmm/src/rpc_interface.rs:60-62`.
- **What.** Plain-text logs to named pipe. Metrics every 60 s + on events (start, panic). Counters for per-device I/O, vCPU halts, `lost-logs`, `lost-metrics` (when pipe full).
- **Why for us.** Phase 9 — must drain the pipe in real time or signals are lost. Our metrics shipper must keep up.
- **Skip.** No structured logging (no syslog/JSON). Customer owns aggregation.

## 8. What Firecracker explicitly does NOT support

This list is the reason **Cloud Hypervisor is our primary** and FC is the secondary backend:

- **✗ virtio-fs** — block devices + vsock only. → Use CH for skill / user-data mounts.
- **✗ GPU / VFIO** — no IOMMU, no GPU paravirt. → CH or kata-qemu for GPU.
- **✗ Arbitrary PCI hotplug** — only virtio-block/net/pmem hotplug as developer-preview.
- **✗ Guest graceful reboot (x86_64)** — only ARM64 via PSCI.
- **✗ Nested virt.**
- **✗ 32-bit guest.**
- **✗ ACPI PM / thermal throttling (x86).**
- **Devices total**: virtio-net, virtio-block, virtio-balloon, virtio-vsock, serial, minimal i8042.

## 9. Multi-arch (x86_64 ↔ aarch64)

- **Where.** `src/arch/x86_64/`, `src/arch/aarch64/`.
- **What.** Both first-class. Tested on AWS Intel/AMD/Graviton metals. GICv2/GICv3 supported on aarch64 but **snapshot/restore requires same GIC version** on both hosts.

## Summary table

| Pattern | File | Phase | Constraint |
|---|---|---|---|
| REST on unix socket | `rpc_interface.rs` | 8 | Synchronous only |
| **Jailer** (chroot + ns + cgroup + uid) | `jailer/src/main.rs` + `chroot.rs` | 8 | Standard hardening pattern — adopt principle |
| MMDS V2 (token-auth) | `mmds/data_store.rs` | 8 | Cleared on snapshot restore |
| Snapshot files + CRC + ondemand | `persist.rs` | 10 | Memory file must persist |
| Memory oversubscription | `vstate/memory.rs` | 8 | OOM killer can evict |
| Per-thread seccomp BPF | `seccomp.rs` | 8 | Compiled in; segmented by role |
| Named-pipe logs/metrics | `logger/` | 8,10 | Must drain in real-time |
| Constraint: no virtio-fs/GPU | `docs/design.md` | 8 | Use CH for those workloads |
| Multi-arch | `arch/` | 8,10 | Snapshot needs matching GIC on aarch64 |
