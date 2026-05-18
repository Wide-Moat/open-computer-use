<!-- SPDX-License-Identifier: BUSL-1.1 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# 16 — Anthropic production sandbox (reverse-engineered, observed)

> Source: empirical observation from inside a live Anthropic Claude sandbox session, 2026-05.
> Distinct from [`13-anthropic-sandbox-runtime.md`](./13-anthropic-sandbox-runtime.md) which covers the open-source local sandbox (`anthropic-experimental/sandbox-runtime`, bubblewrap-based). This file documents the **production hosted environment** — closed, but observable from the inside.
>
> **Companion deep dive:** [`19-anthropic-firecracker-microvm-internals-observed.md`](./19-anthropic-firecracker-microvm-internals-observed.md). This file is the high-level summary; #19 is the layer-by-layer transcript with every supporting datum, locked decisions (incl. "no PVC for sandbox session workspace" — [A37](../antipatterns.md#a37--pvc-for-sandbox-session-workspace)), and a reproduction recipe.
>
> Status: **observation, not yet decision-grade.** Locks in only one downstream choice (rclone baseline for Tier 4 — see [`../architecture/06-storage.md`](../architecture/06-storage.md)). All other implications stay open until Phase 3 / Phase 7 / Phase 8 research. See #19 for additional locked decisions.

## 1. Runtime — Firecracker microVM, NOT k8s

```
Kernel: Linux 6.18.5 (custom Anthropic build)
  cmdline: rdinit=/process_api --firecracker-init
           --addr 0.0.0.0:2024 --block-local-connections
PID 1   : process_api (Anthropic's own agent)
            HTTP/WebSocket on 0.0.0.0:2024 (not vsock)
            exec under cgroup /process_api/<hash>
            reap zombies, stream stdout/stderr/exit
```

- VMM: **Firecracker** (the `--firecracker-init` flag is unambiguous). Not Cloud Hypervisor, not QEMU, not Kata.
- No k8s: no ServiceAccount, no `kubepods` cgroups, no kube env vars.
- Orchestrator is Anthropic's own — Lambda-style scheduling for millions of short sessions.

**Implication for us.** Firecracker is production-proven for this workload shape at scale; Cloud Hypervisor stays as opt-in for GUI / virtio-fs / virtio-gpu cases. Earlier sketches that defaulted CH should be re-evaluated in [Phase 9 research](../roadmap.md#phase-9). **Not yet locked.**

## 2. Guest agent protocol — HTTP/WebSocket, NOT vsock

- `0.0.0.0:2024` HTTP+WS, `--block-local-connections` for guest-internal lockdown.
- Anthropic emphatically picked TCP HTTP over the Kata-style vsock+gRPC pattern.
- Benefits observed: dev-mode works without a VM, any HTTP tool debugs the agent, simpler upgrade story.

**Implication for us.** Phase 7 (guest agent rewrite) should consider HTTP+WS as the **default** with vsock as opt-in transport, not the other way around. This contradicts the earlier ADR-0008 lean toward connect-go-over-vsock for L3↔L1. **Re-evaluate at Phase 7 research, do not patch ADR-0008 yet.**

## 3. Storage — two-tier observed split

| Mount | Backend | Semantics | Speed |
|---|---|---|---|
| `/home/claude` | local ext4 on `/dev/vda` (virtio-block) | ephemeral, POSIX 100% | ~0.05 ms / file |
| `/mnt/user-data/uploads` (ro) | rclone FUSE → object storage | persistent, POSIX ~95% | ~1.34 ms / file |
| `/mnt/user-data/outputs` (rw) | rclone FUSE → object storage | persistent, POSIX ~95% | ~1.34 ms / file |
| `/mnt/user-data/tool_results` (ro) | rclone FUSE → object storage | persistent, POSIX ~95% | ~1.34 ms / file |
| `/mnt/transcripts` (ro) | rclone FUSE → object storage | persistent, POSIX ~95% | ~1.34 ms / file |

**Tooling: `rclone` with VFS cache.** Not Mountpoint S3 CSI. Sample command shape (inferred):

```bash
rclone mount s3:user-{id}-outputs /mnt/user-data/outputs \
  --vfs-cache-mode full \
  --vfs-cache-max-age 24h \
  --vfs-cache-max-size 10G \
  --vfs-write-back 10s \
  --dir-cache-time 5m \
  --allow-other
```

POSIX coverage (works via VFS cache): SQLite, openpyxl re-save, random write, mmap, fsync.
Known gaps: hardlinks → `EOPNOTSUPP`, symlinks → `ENOSYS`, chmod/chown → silent no-op.

**Implication for us — locked.** [`../architecture/06-storage.md`](../architecture/06-storage.md) Tier 4 now lists **rclone+VFS as the baseline backend** with mountpoint-s3 / geesefs / csi-rclone / juicefs-csi as deferred alternatives for the Phase 3 research pass.

## 4. Three-zone user-data layout

| Mount | Writer | Reader | Lifecycle |
|---|---|---|---|
| `uploads/` | user | agent (ro) | session |
| `outputs/` | agent | user | persistent |
| `tool_results/` | runtime / control plane | agent (ro) | session |

`tool_results/` is an architectural slot we don't currently have: a place for the control plane to inject results (large tool outputs that exceed inline message limits, cross-tool shared blobs). Empty in observed session, but the mount is provisioned.

**Implication for us.** Worth folding into the storage spec when we revisit Tier 4 in Phase 3 — but **not now**, this is an open question, not a locked decision.

## 5. `present_files` is a control-plane operation, not an FS write

Materializing a file as a user-facing attachment is **not** the same as writing it to `outputs/`. The observed Anthropic API exposes a separate `present_files` tool that does MIME detection, audit logging, and emits a UI attachment card.

**Implication for us.** When we design the Tier 4 contract in Phase 3, "write to outputs" and "surface to user" should be two separate operations, not one.

## 6. Other observations

- **`old_root` in `/`** — pivot_root artifact at boot, microVM signature.
- **`container_info.json` in `/`** — metadata laid down by the runtime at start.
- **Coder presence** — kernel build string mentions `argocd@coder-xiangbin-xb-home-2-0`, suggesting Anthropic engineers use Coder for AI-infra development. Not architectural, but useful as a political reference for Coder adoption in CDEs.
- **Hardware: Intel Xeon Sapphire/Emerald Rapids fleet.** Standard cloud silicon.

## 7. What this changes for our design — summary

| Area | Status after this observation |
|---|---|
| Storage Tier 4 backend | **Locked: rclone+VFS baseline** ([`06-storage.md`](../architecture/06-storage.md)) |
| 3-zone user-data layout (`uploads`/`outputs`/`tool_results`) | Open — revisit in Phase 3 research |
| Storage as first-class layer / adapter | Open — proposal exists but not committed; revisit in Phase 0.5 or Phase 3 |
| Default VMM (Firecracker vs CH) | Open — revisit in Phase 9 research |
| Guest agent transport (HTTP+WS vs vsock+gRPC) | Open — revisit in Phase 7 research; do not amend [`ADR-0008`](../adr/0008-internal-grpc-external-rest-mcp.md) yet |
| `present_files` style materialization | Open — revisit in Phase 3 |

## 8. What this observation does NOT change

- Our k8s direction. Anthropic's no-k8s choice is driven by Lambda-style scale. At our target scale (100–10K concurrent sandboxes), k8s + RuntimeClass remains the right fit.
- Our 4-layer model. Anthropic's stack maps 1:1 to L1–L4; storage adapter as a cross-cutting concern is a possible 5th element but stays a proposal until reviewed.
- Earlier ADRs. None are amended by this file. ADR amendments require their own research pass and supersedes block.
