<!-- SPDX-License-Identifier: BUSL-1.1 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# 20 — Snapstart hot-swap (frozen snapshot + block-device replacement)

> Reference: the `--firecracker-init` flow catalogued in [`sandboxd/anthropic/`](../../../sandboxd/anthropic/) and the production observations in [`16-anthropic-production-sandbox-observed.md`](./16-anthropic-production-sandbox-observed.md). AWS Lambda's MicroManager pool is the original lineage (see [`references.md`](../references.md) Lambda framing).
>
> Status: **pattern catalogue for Phase 10.** No decisions land here. Phase 10 will pick which pieces we ship.

## 1. The pattern in one sentence

Instead of keeping warm VMs around (RAM-expensive at scale), the Anthropic Claude.ai sandbox is reported to keep **frozen Firecracker snapshots** of a minimal template VM and, at session start, swap the block-device backends and resume. The guest doesn't notice it's a different filesystem.

## 2. Two-phase lifecycle

### Phase A — template (one-time, per release)
```text
1. Firecracker boots minimal kernel + initramfs (~3 MB) holding /process_api.
2. process_api --firecracker-init runs:
     mount /proc /sys /dev; configure networking; signal "ready".
3. Host: PUT /snapshot/create → Firecracker freezes VM state to disk.
4. VM stops; the snapshot sits in the pool.
```

### Phase B — session restore (per user session)
```text
1. Host prepares per-session block devices:
     vda — root filesystem (per-tenant data + ephemeral overlay)
     vdb — squashfs of /opt/<app>             (read-only, per release)
     vdc — squashfs of /opt/<runner>          (read-only, per release)
2. Host: PUT /snapshot/load with the new device backends.
3. VM resumes:
     - Kernel notices block-device sizes changed (virtio_blk: vdc new size …).
     - CRNG reseeds (random: crng reseeded due to virtual machine fork).
4. process_api waits for the host's POST /mount_root on its control server:
     - drop_caches
     - remount devtmpfs
     - mount /dev/vda as ext4
     - pivot_root
     - mount squashfs overlays from /dev/vdb, /dev/vdc
     - clock_settime() to fix the frozen clock
     - drop CAP_SYS_RESOURCE
     - accept WS connections
```

Snapshot pool size, refill rate, and max age are tuned on the host side; the VM does not know it was ever frozen.

## 3. Why this beats warm pools at scale

| Resource | Warm VM pool | Frozen snapshot pool |
|---|---|---|
| RAM | Full per-VM RAM × pool size | Disk only (snapshot blobs) |
| CPU | Idle ticks | None |
| Cold-start | ~0 ms (already running) | tens to low hundreds of ms (restore + remount) |
| Per-tenant attack surface | Reused VMs possible | Fresh snapshot every time |

At Anthropic-scale (millions of short sessions/day) the RAM math forces this design. For our target scale (100–10K concurrent), it's an **economics question for Phase 10** — not a Phase 9 must.

## 4. Post-restore hardening — what the guest does on every resume

These are the actions we'd need on the L1 side. Each is small individually; together they fix the failure modes that naive "VM resume" pretends don't exist.

| Action | Why | Phase relevance |
|---|---|---|
| `drop_caches` | Page cache references files that no longer exist on the new rootfs | Phase 10 mandatory |
| Remount `/dev` (devtmpfs) | Device-node mappings are post-swap | Phase 10 mandatory |
| `pivot_root` to new rootfs | Frozen rootfs is stale by design | Phase 10 mandatory |
| `clock_settime()` | Wall-clock was frozen; restored value is wrong by minutes-to-days | Phase 10 mandatory |
| CRNG reseed (`getrandom`-style force) | Kernel knows it forked; userspace RNGs (OpenSSL, glibc arc4random) do not, so seed them fresh | Phase 10 mandatory |
| `init_on_free=1` kernel cmdline | Cleared freed pages so resume doesn't leak template-VM secrets | Phase 9 (template build) |
| Drop `CAP_SYS_RESOURCE` | Was held only for init; dropping shrinks blast radius | Phase 9 (template build) |
| Env-var scrub before fork (`_TOKEN _SECRET _PASSWORD API_KEY`) | Prevents template-VM env from leaking into session workload | Phase 7 (carries over) |

## 5. Filesystem-freeze coupling

`process_api` is documented to expose `POST /fs_freeze` (FIFREEZE) and `POST /fs_thaw` (FITHAW) on its control server. The host calls freeze before taking the snapshot so the on-disk image is internally consistent. **Without freeze, snapshots silently corrupt on resume** — typical SQLite WAL or atomic-rename caught mid-flight.

For us this is one of two endpoints the L1 agent has to expose at Phase 10. The other is `POST /mount_root`. Neither is needed before snapshots ship.

## 6. Block-device tooling swap — storage implication

The pattern requires Tier-1 (OCI image) and Tier-2 (skills squashfs) content to be **shippable as block devices** that can be swapped at resume. Concretely:
- `/opt/<runner>` and `/opt/<skills>` become **squashfs blobs**, not container layers.
- The root filesystem on `vda` is a **per-tenant overlay** on a shared template base, prepared by the host before resume.

This is the "block-device tooling swap" item flagged in `roadmap.md` Phase 0.5 line 74. The architecture-level write-up belongs in `architecture/06-storage.md`.

## 7. What stays the same as today

- The MCP tool catalogue inside the sandbox.
- The user's view of `/home/assistant` (workspace).
- The agent's RPC surface above the control-server endpoints.

Snapstart is a **deployment optimization**, not a contract change. Existing L4 / MCP clients should see no difference except cold-start latency.

## 8. What we'd be giving up

- **Persistent in-VM state across sessions.** Each session resumes from the same frozen snapshot. Anything the agent wrote to root from a prior session is gone unless it landed on `vda` (per-tenant overlay) or in Tier-4 mounts.
- **Cross-session warm caches.** No JIT warmup, no resolved DNS, no preloaded model weights survive the swap. Tier-4 mounts (rclone+VFS) carry persistent state.
- **Casual debugging.** "Just exec into the box" is harder when the box is a frozen snapshot pool you can't SSH into.

## 9. Adopt / Adapt / Reject

| Element | Decision | Phase | Notes |
|---|---|---|---|
| Frozen-snapshot pool (vs. warm VM pool) | **Adopt** | Phase 10 | Only at the scale point where warm-pool RAM becomes the bottleneck |
| Two-phase template / restore lifecycle | **Adopt** | Phase 10 | Template build is part of release pipeline |
| Block-device hot-swap (`vda`/`vdb`/`vdc` semantics) | **Adopt** | Phase 10 | Drives storage architecture (see `architecture/06-storage.md` Phase 0.5 update) |
| `POST /mount_root` on agent's control server | **Adopt** | Phase 10 | Optional control endpoint, gated by feature flag until snapshot tier lands |
| `POST /fs_freeze` / `/fs_thaw` | **Adopt** | Phase 10 | Required for snapshot consistency |
| Mandatory post-restore guest actions (drop_caches, devtmpfs remount, clock_settime, CRNG reseed) | **Adopt** | Phase 10 | All four together, as a single hardening protocol |
| `init_on_free=1` kernel cmdline | **Adopt** | Phase 9 | Template-build hardening |
| Drop `CAP_SYS_RESOURCE` post-init | **Adopt** | Phase 9 | Template-build hardening |
| Snapshot pool tuning (min/target/max/refillRate/maxAge) | **Adopt** | Phase 10 | Already planned at Phase 6 for warm pools (`architecture/03-layer3-providers.md`); applied to snapshot pool at Phase 10 |
| Snapshot pool placement (multi-region) | **Adapt** | Phase 10 | Coupled to the workspace-proxy pattern in `architecture/08-networking.md` |
| Per-tenant root overlay preparation on host | **Adapt** | Phase 10 | The host-side tooling here is novel work, not lifted from process_api |

## 10. Open questions for Phase 10 research

1. **Which VMM?** Firecracker is the proven option (Anthropic prod), Cloud Hypervisor adds virtio-fs + GPU but its snapshot story is younger. Cross-link to `research/04-cloud-hypervisor.md` and `research/05-firecracker.md`.
2. **Snapshot blob storage.** S3-class blobs vs. local SSD per node — latency vs. failure-domain trade-off.
3. **Per-tenant root preparation.** Mount-time copy-on-write (overlayfs on host) vs. dm-snapshot vs. block-level CoW. Influences cold-start latency target.
4. **Snapshot retention and rotation.** When the template image changes, all existing snapshots become stale — drain or kill?
5. **DoS surface.** Pool exhaustion under burst load needs explicit policy: queue, reject, or fall back to cold boot.

## Related

- ADR: [`0008-internal-grpc-external-rest-mcp.md`](../adr/0008-internal-grpc-external-rest-mcp.md), [`0010-lambda-as-inspiration-not-runtime.md`](../adr/0010-lambda-as-inspiration-not-runtime.md)
- Sibling digests: [`05-firecracker.md`](./05-firecracker.md), [`16-anthropic-production-sandbox-observed.md`](./16-anthropic-production-sandbox-observed.md), [`19-anthropic-process-api.md`](./19-anthropic-process-api.md)
- Architecture: [`06-storage.md`](../architecture/06-storage.md), [`07-security.md`](../architecture/07-security.md), [`04-layer2-runtimes.md`](../architecture/04-layer2-runtimes.md)
- Antipatterns: A22 (no GPU on snapshottable templates), A27 (image-digest pinning per template)
