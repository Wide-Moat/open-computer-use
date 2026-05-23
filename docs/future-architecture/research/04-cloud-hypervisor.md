<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# 04 — Cloud Hypervisor (lead untrusted-tier microVM)

> Source: [`references/cloud-hypervisor/`](../../../references/cloud-hypervisor/). Rust microVM hypervisor, Intel-led.
> Primary backend for [Phase 9](../roadmap.md) (`kata-ch`); snapshot/restore feeds Phase 10.

## 1. REST API on Unix socket — VM lifecycle

- **Where.** `docs/api.md:51-59, 61-102` (OpenAPI 3.0). `--api-socket path=/tmp/ch.sock`.
- **What.** Endpoints: `/vmm.ping`, `/vmm.shutdown`, `/vm.create`, `/vm.boot`, `/vm.pause`, `/vm.resume`, `/vm.snapshot`, `/vm.restore`, `/vm.shutdown`. Plus `/vm.resize` (CPU/memory hotplug) and `/vm.add-*` (disk/fs/net/vsock hotplug).
- **Why for us.** Phase 9 control plane → hypervisor. No HTTP/2 / no streaming — keep it synchronous.
- **Skip.** No authn in CH — rely on socket filesystem permissions; orchestrator wraps the socket.

## 2. vsock — CID model + bidirectional setup

- **Where.** `docs/vsock.md:1-19, 51-75`. Kernel: `CONFIG_VHOST_VSOCK` (host), `CONFIG_VIRTIO_VSOCKETS` (guest).
- **What.** CIDs: Hypervisor=0, Loopback=1, Host=2, Guest=3+. Stream only. `--vsock cid=3,socket=/tmp/ch.vsock`.
  - Host→Guest: guest listens on port, host connects via Unix socket with `CONNECT <port>` prefix (socat ≥1.7.4).
  - Guest→Host: host listens on `<socket_path>_<port>`, guest connects to CID=2.
- **Why for us.** Phase 7 vsock listener (`05-layer1-guest-agent.md`). The `CONNECT <port>` protocol detail is non-obvious; document in our agent spec.
- **Skip.** Loopback CID=1 only needed for debug.

## 3. virtio-fs — fast shared mounts (the reason we pick CH)

- **Where.** `docs/fs.md:13-90`. Daemon: `virtiofsd` (separate Rust binary). VM needs `--memory shared=on` (mandatory).
- **What.**
  - Build virtiofsd separately; `setcap cap_sys_admin+epi`.
  - `--fs tag=myfs,socket=/tmp/virtiofs,num_queues=1,queue_size=512`.
  - Guest: `mount -t virtiofs myfs /mnt/shared` (kernel ≥5.10).
  - Cache modes: `cache=never` (default; low RAM, dense) vs `cache=always` (faster, RAM-multiplier — **footgun** at high density).
- **Why for us.** Phase 9 — replaces FUSE for skill / user-data mounts inside the microVM. Updates [`architecture/06-storage.md`](../architecture/06-storage.md) "What changes per phase" row for the kata tier (virtio-fs over FUSE).
- **Skip.** DAX feature not stable; avoid.

## 4. Snapshot / restore — files + ondemand restore

- **Where.** `docs/snapshot_restore.md:11-144`.
- **What.**
  - Snapshot: pause VM → `POST /vm.snapshot {source_url: file:///path}` → produces `config.json`, `memory-ranges`, `state.json`.
  - Restore: `cloud-hypervisor --restore source_url=file:///path,resume=true` OR `POST /vm.restore`. Restored VM is **paused** — must explicitly `/vm.resume`.
  - `memory_restore_mode=ondemand` — userfaultfd-based; skips full-memory copy (faster boot). Fails strict if userfaultfd unavailable.
- **Why for us.** Phase 10. Note: snapshot file size ≈ VM RAM size → 100 VMs × 1 GB = 100 GB fast storage.
- **Skip.** VFIO devices **break** snapshot/restore. If we ever offer GPU passthrough, those templates have no snapshot capability.

## 5. Memory — balloon, free-page reporting, ACPI hotplug

- **Where.** `docs/balloon.md:8-76`, `docs/memory.md:64-86`, `docs/hotplug.md:64-75`.
- **What.**
  - **Balloon** (`--balloon size=...,deflate_on_oom=on,free_page_reporting=on`) — host reclaims guest pages.
  - **Free Page Reporting** alone (even with balloon size 0) cuts host footprint without shrinking guest visible RAM. Best for high-density untrusted tier.
  - **ACPI hotplug**: `/vm.resize` to grow; **shrink takes effect only on guest reboot** (footgun).
  - Reserve headroom: `--memory size=1G,hotplug_size=2G`.
- **Why for us.** Phase 5+ capacity policy. Free Page Reporting is the easy density win.
- **Skip.** Hugepages — only if a workload is latency-critical; otherwise hurts packing.

## 6. GPU passthrough — VFIO (future)

- **Where.** `docs/vfio.md:1-150`.
- **What.** Unbind from native driver → bind to `vfio-pci` → pass `--device path=/sys/bus/pci/devices/...`. NVIDIA P2P: `x_nv_gpudirect_clique=0`.
  - IOMMU group: all devices in same group must be passed (or none).
  - Snapshot incompatible with VFIO.
- **Why for us.** Out of scope until Phase 10+, but documented now so we don't promise it for templates that need snapshotting.

## 7. Privilege model — capability-based, no jailer

- **Where.** `docs/seccomp.md:1-68`, `docs/landlock.md:1-106`.
- **What.** **No** Firecracker-style jailer. Single process; only `cap_net_admin+ep` for TAP networking. Hardening = seccomp (per-thread allowlists, on by default, kill-on-violation) + **Landlock** sandboxing (Linux ≥5.13) for FS access. Hotplug paths must be pre-declared in `--landlock-rules`.
- **Why for us.** Phase 9 — orchestrator wraps CH in a container/cgroup boundary; CH itself relies on seccomp + Landlock. Compare with [Firecracker's jailer](./05-firecracker.md) — different security model.
- **Footguns.** Never `--seccomp false` in production; never run as root; Landlock + hotplug requires upfront path declaration.

## 8. TDX / SEV-SNP attestation (compliance tier)

- **Where.** `docs/intel_tdx.md:26-97`, `docs/amd_sev_snp.md:16-40`.
- **What.** Build with `--features tdx` (Intel) or `--features sev_snp` (AMD, MSHV-only). Encrypted guest, hypervisor-blind. No balloon, no VFIO under TDX. 10–30 % perf penalty.
- **Why for us.** Phase 10+ if a compliance tier (HIPAA/Confidential Computing) is added. ADR-worthy when it lands.

## 9. Footguns — explicit

| What NOT to do | Why | Fix |
|---|---|---|
| Snapshot + VFIO | Snapshot fails on VFIO devices | No GPU passthrough on snapshottable templates |
| `cache=always` at density | Host page cache multiplies | Always `cache=never` for untrusted tier |
| Landlock hotplug without pre-declaration | Add-disk denied | Pre-declare all possible hotplug paths |
| `deflate_on_oom=on` w/o testing guest | Older Linux/Windows may not handle | Default off; test per-image |
| Trust TDX report w/o attestation chain | Rogue hypervisor fakes it | Validate against Intel/AMD roots |
| Run as root | Larger attack surface | `setcap cap_net_admin+ep` + seccomp |
| `--seccomp false` in prod | Removes syscall allowlist | Keep on; use `--seccomp log` for debug |

## Summary for Phase 9 (`kata-ch`)

1. REST on unix socket — orchestrator control.
2. vsock CID=3 for agent comms.
3. virtio-fs with `cache=never` for skill / user-data mounts.
4. Landlock + seccomp enabled by default.
5. Headroom: `--memory size=1G,hotplug_size=2G` per template.
6. Free Page Reporting on by default for density.
7. **No** VFIO on snapshottable templates.
8. Snapshot files sized = guest RAM — provision fast block storage.
