<!-- SPDX-License-Identifier: BUSL-1.1 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# 22 — Anthropic Firecracker microVM internals (deep dive, observed)

> Source: live-VM walk inside an Anthropic Claude production sandbox session, 2026-05-17, all evidence collected from inside the guest with shell tools (`cat /proc/cmdline`, `lsblk`, `mount`, `ps -ef`, `findmnt`, `stat`, `sha256sum`, `uptime -s` vs directory Birth times).
>
> Companion to [`16-anthropic-production-sandbox-observed.md`](./16-anthropic-production-sandbox-observed.md). #16 stays the high-level summary; this file is the **layer-by-layer transcript** with every datum that supports the picture, so we can replicate it later without re-running the experiment.
>
> Status: **decision-grade.** Locks one new decision (no PVC for sandbox session workspace — Tier 3 is CoW snapshot, not RWO PVC; see [`../architecture/06-storage.md`](../architecture/06-storage.md) and antipattern [A37](../antipatterns.md#a37--pvc-for-sandbox-session-workspace)). All other implications carry forward as inputs to Phase 3, Phase 5, Phase 7, Phase 9 research.

## Locked decisions emerging from this observation

| # | Decision | Where locked |
|---|---|---|
| L1 | **No PVC for sandbox session workspace (Tier 3).** Use CoW snapshot of a golden rootfs (qcow2 backing files / dm-thin / ZFS-clone), not RWO PVC. PVC is rejected for the agent session workspace tier in all templates. | [`../architecture/06-storage.md`](../architecture/06-storage.md) Tier 3 + [A37](../antipatterns.md#a37--pvc-for-sandbox-session-workspace) |
| L2 | **Sealed read-only system disks** (binaries, system skills) ship as `squashfs` on dedicated block devices, not as layers inside the rootfs. | [`../architecture/06-storage.md`](../architecture/06-storage.md) Tier 1 / Tier 2 |
| L3 | **No S3 credentials inside the guest.** Storage-side auth: the guest carries only a `filesystem_id` session token; the storage proxy outside the VM maps `filesystem_id → bucket prefix` and holds the S3 creds. | [`../architecture/07-security.md`](../architecture/07-security.md) Tier-4 credential boundary |

All other items in this file are research inputs, not amendments to existing ADRs.

---

## Layer 1 — Hypervisor and init

### 1.1 Firecracker microVM, custom Go init, no systemd

Kernel cmdline (verbatim, line-broken for readability):

```text
rdinit=/process_api --firecracker-init --addr 0.0.0.0:2024
  --max-ws-buffer-size 32768 --block-local-connections
console=ttyS0 reboot=k panic=1 nomodule random.trust_cpu=1
  ipv6.disable=1 swiotlb=noforce init_on_free=1
```

- **VMM = Firecracker.** The `--firecracker-init` flag is unambiguous (confirms [#16 §1](./16-anthropic-production-sandbox-observed.md)).
- **PID 1 = `/process_api`,** a custom Go binary, invoked via kernel `rdinit=` so it runs **directly off the initramfs ramdisk**, bypassing any `init` / `systemd` / `sysvinit` stage entirely.
- `process_api` is the everything-init: mounts the squashfs disks, spawns and supervises `rclone-filestore`, serves a control-plane WebSocket on `0.0.0.0:2024`, reaps zombies, runs the agent's exec loop.
- No containerd, no runc, no Kubernetes, no Docker. Bare Firecracker VM.

Process census inside the live VM: ~56 processes total, **two user-space**:

| PID | Process | Role |
|---|---|---|
| 1 | `process_api` | Init, control-plane WS, supervisor, exec |
| 489 | `rclone-filestore` (custom rclone fork, `multimount` subcommand) | All four FUSE mounts in one process |

The rest are kernel threads.

### 1.2 Kernel hardening flags (each justified)

| Flag | Effect | Why |
|---|---|---|
| `rdinit=/process_api` | Skip `/sbin/init`, run custom binary | Removes systemd attack surface; deterministic boot |
| `--firecracker-init` (binary flag) | `process_api` knows it's PID 1 inside FC | Branches mount/setup behavior |
| `--addr 0.0.0.0:2024` | Control-plane WS bind | TCP, not vsock — see [#16 §2](./16-anthropic-production-sandbox-observed.md) |
| `--max-ws-buffer-size 32768` | Bound WS frame size | DoS mitigation |
| `--block-local-connections` | Drop guest-to-guest local syscalls on control path | Internal lockdown — guest code can't talk to the control plane port |
| `console=ttyS0` | Serial console (Firecracker only exposes ttyS0) | Standard FC |
| `reboot=k panic=1` | Reboot via keyboard reset; panic = exit immediately | FC reboot model — panic = VM dies, host respawns |
| `nomodule` | Disable post-boot kernel module loading | Locks attack surface — even root can't `insmod` |
| `random.trust_cpu=1` | RDRAND counted as seeded entropy | Skip slow entropy gather; fine inside FC where RDRAND is virtualized |
| `ipv6.disable=1` | No IPv6 stack | Smaller surface, single egress path to manage |
| `swiotlb=noforce` | Skip software IOTLB bounce buffer | Perf — FC presents native virtio, no need for swiotlb |
| `init_on_free=1` | Zero pages on `kfree` | Prevents info-leak across freed allocations (CVE class) |

**Takeaway for us.** Every flag is intentional; copying them in our Phase 9 Kata/CH template defaults is cheap and gives meaningful hardening. See [A37](../antipatterns.md) and the cross-link to [`research/05-firecracker.md`](./05-firecracker.md).

---

## Layer 2 — Block devices: four disks, three classes of mutability

```text
NAME  MAJ:MIN  SIZE   RO  TYPE      MOUNTPOINT             ROLE
vda   254:0    256G   rw  ext4      /                      ephemeral rootfs, CoW-snapshot of golden image
vdb   254:16   9.4M   ro  squashfs  /opt/rclone            sealed rclone-filestore binary
vdc   254:32   656K   ro  squashfs  /mnt/skills/public     Anthropic-built system skills
vdd   254:48   5.3M   ro  squashfs  /mnt/skills/examples   example skills
```

### 2.1 Why four disks, not one layered image

One read-write disk for ephemeral session state; three sealed read-only `squashfs` blocks for **everything that must be tamper-evident at boot.** Different classes of data → different disks with different mutability:

- **Binaries and system skills are version-pinned artifacts**, shipped independently of rootfs. Updating rclone or the public skill set does not require rebuilding the golden rootfs. They are also bit-identical across every session that uses the same template version.
- **Even guest root cannot mutate them at runtime** — they're `ro` at the block layer, not just at the mount layer. `mount -o remount,rw` does nothing.
- **An RCE inside the guest cannot swap out `rclone-filestore` or a system skill,** because the underlying block device refuses writes. This is the strongest possible host-side guarantee without crypto.

### 2.2 The ext4 reserved-blocks quota trick

`vda` is a 256 GiB ext4, but `df` inside the guest reports only ~10 GiB free for the agent user. The mount line shows the mechanism:

```text
/dev/vda on / type ext4 (rw,...,resuid=65534,resgid=65534,...)
```

- ext4 `resuid` / `resgid` reserves a fraction of free blocks for **a specific uid/gid only.** Default is `root` (uid 0).
- Anthropic sets `resuid=65534,resgid=65534` (`nobody:nogroup`) — a uid that no real process runs as. The reserved blocks are effectively claimable by **no-one**, so the agent (running as `claude`, uid 999) hits ENOSPC at ~10 GiB despite a 256 GiB volume.
- This gives **per-VM quota at near-zero runtime cost** — no `quota` daemon, no XFS project quotas, no LVM thin volume. Just ext4 tunables baked at provisioning time.

**Takeaway for us.** Cheap per-session-soft-cap pattern for our Phase 9 microVM templates. Useful early Phase 5 as well (k8s ephemeral-storage limits are weaker). Document but ship later (no Phase-3 priority).

### 2.3 Rootfs as CoW snapshot — the PVC-replacement pattern ⭐

`vda` is 256 GiB but it is not 256 GiB of allocated storage. It's an ext4 filesystem **on a CoW snapshot of a golden rootfs image**. Evidence:

- Directory Birth time on `/root`, `/home/claude`, `/tmp` matches the golden-image build date, not VM boot — these directories are inherited from the snapshot, not created fresh.
- `uptime -s` says boot was ~35 min before this observation; many directory Birth times are days older. CoW.
- The 256 GiB is the **maximum** the rootfs can grow to (sparse), not the actual provisioned storage.

The host-side implementation is `qcow2` backing files (Firecracker supports this), or `dm-thin` snapshots, or ZFS clone — observation cannot tell which. What it can tell:

> **The session workspace is a per-VM CoW snapshot of a shared template, not a per-session persistent volume.** Per-session ext4 deltas live on the snapshot; when the session ends, the delta is discarded and the golden image untouched.

This is the technical answer to "do we need PVC for `/home/assistant`?" — **no**. CoW snapshot at the storage layer (qcow2 / dm-thin / ZFS) supplies the same "every session starts from a clean template" guarantee with zero state across sessions, no RWX problems, no garbage collection, no per-tenant claim management.

**Cross-link.** This locks [A37](../antipatterns.md#a37--pvc-for-sandbox-session-workspace) and the Tier 3 wording in [`06-storage.md`](../architecture/06-storage.md).

---

## Layer 3 — FUSE mounts for persistent state (rclone multimount)

```text
fuse.rclone → /mnt/user-data/uploads        ro    vfs-cache-time 1s
fuse.rclone → /mnt/user-data/outputs        rw    vfs-cache-time 3600s
fuse.rclone → /mnt/user-data/tool_results   ro    vfs-cache-time 3s
fuse.rclone → /mnt/transcripts              ro    vfs-cache-time 10s
```

All four mounts are served by **one** process — `rclone-filestore` (PID 489) running a `multimount` subcommand. The `multimount` subcommand does not exist in upstream `rclone` — Anthropic forked rclone and added it.

From the binary's own `--help` (extracted inside the guest):

> Designed for Firecracker containers where a single init script manages all mounts. Uses go-fuse/v2 with DirectMount (no fusermount subprocess) to avoid chroot deadlocks. Once every mount is ready, a ready_file is touched to signal the init script.

Three deliberate engineering choices baked into `multimount`:

1. **`go-fuse/v2` with DirectMount** — bypasses the setuid `fusermount` helper. Smaller TCB; no setuid binary inside the guest at all.
2. **`ready_file` synchronization** — `process_api` blocks on the `ready_file` touch before declaring the VM ready to accept agent traffic. Eliminates the "container started but mounts not ready" race that plagues normal FUSE deployments.
3. **One process, all mounts** — single SIGTERM tears down all four cleanly; memory footprint one rclone process, not four.

### 3.1 Per-mount VFS cache TTL — semantics-driven

The TTLs are chosen per-mount based on writer/reader patterns:

| Mount | TTL | Pattern |
|---|---|---|
| `uploads/` (ro) | 1 s | User writes from outside; agent needs to see new uploads near-immediately |
| `outputs/` (rw) | **3600 s** | Agent is the sole writer — local cache is authoritative for the session |
| `tool_results/` (ro) | 3 s | Control plane writes; agent reads soon after |
| `transcripts/` (ro) | 10 s | Updated occasionally; bounded staleness OK |

Pattern: **read-heavy + multi-writer ⇒ short TTL; write-heavy + single-writer ⇒ long TTL.** This is a portable design rule for any FUSE-over-object-store layout, not Anthropic-specific.

**Takeaway for us.** Folds into the Tier 4 Phase 3 research:
- Multimount in one process — defer. Upstream `rclone mount` × N is fine until we hit boot-time bottlenecks.
- DirectMount — only matters once we go FUSE-in-guest on Kata. Today we mount on the host / sidecar, so the setuid helper isn't in the threat model.
- TTL-per-semantic table — adopt verbatim into the Tier 4 mount spec.
- `ready_file` pattern — adopt at Phase 7 (guest agent boots only after mounts ready).

---

## Layer 4 — Credentials, identity, and the "no S3 keys in the guest" rule

The rclone mount config inside the guest (representative):

```json
{
  "filesystem_id": "claude_chat_01Ss4WPSeLtHEPZ1q3qBrjt7",
  "source": "/uploads",
  "destination": "/mnt/user-data/uploads",
  "readonly": true,
  "vfs_cache_mode": "full",
  "vfs_cache_max_size": "1G",
  "cache_duration_s": 1.0,
  "uid": 999,
  "gid": 1000
}
```

What is **not** in this config — and not anywhere else in the guest:

- No S3 `access_key_id`.
- No S3 `secret_access_key`.
- No STS token.
- No bucket name.
- No S3 endpoint URL.
- No IAM role ARN.

The only thing in the guest is a **session token** (`filesystem_id`). The guest's `rclone-filestore` calls out to a **storage proxy server outside the VM**, which holds the actual S3 credentials and maps `filesystem_id → S3 bucket prefix` server-side.

### 4.1 Security boundary

| Compromise scenario | Blast radius |
|---|---|
| Guest RCE | Attacker has access to their own `filesystem_id` prefix only. No S3 keys to steal. No way to reach another session's data — auth happens server-side by `filesystem_id`. |
| Single `filesystem_id` leak | Attacker can read/write that one session's prefix. Cannot enumerate others; cannot get long-lived S3 creds. |
| S3 credential leak | Impossible from the guest layer — they don't exist in the guest. |

This is the **strongest available** boundary short of E2EE on every object. It's how we want our Tier-4 to behave by Phase 4 (secret broker).

**Cross-link.** Compatible with our Phase 4 plan (STS tokens) but stricter: even STS tokens are absent from the guest in Anthropic's model. Worth folding into Phase 4 research as a target end-state — see [`17-anthropic-claude-code-remote-env-observed.md`](./17-anthropic-claude-code-remote-env-observed.md) §3 (FD-passing) for the same hardening philosophy applied to a different secret class.

---

## Layer 5 — Skills as a provisioning-time concern, not a runtime one

Three classes of skills, three delivery mechanisms:

```text
/mnt/skills/public      → squashfs ro on vdc     Anthropic-built, immutable per template version
/mnt/skills/examples    → squashfs ro on vdd     example skills, immutable per template version
/mnt/skills/user        → ext4 rw on /vda        per-user skills, baked into rootfs at provisioning
```

User skills are **injected into rootfs at provisioning time**, not pulled at runtime. Evidence by comparing the same skill file across two VMs spawned for the same chat user a few minutes apart:

| | VM A (older session) | VM B (fresh session, same user) |
|---|---|---|
| `sha256sum /mnt/skills/user/foo/SKILL.md` | `419bb48f…` | `9534653f…` |
| "v2" marker in file | absent | present at line 8 |

Same source-of-truth (S3 / database), different snapshots inside each VM. The source updated between A and B; B picked up the change at provisioning, A did not, **even though both VMs are still alive at the same time.**

### 5.1 Why this is the right design

- **Determinism.** An agent mid-task cannot get code modified out from under it. Every tool exec in a single VM runs against the same skill snapshot.
- **No runtime invalidation surface.** No `inotify` watch, no version checks per tool call, no hot-reload race.
- **Auditability.** Every session has a fixed skill-snapshot fingerprint — recordable in audit logs.
- **Security.** A skill cannot be modified mid-execution by another tenant or a compromised control plane component; the bytes that run are the bytes the VM was provisioned with.

**Takeaway for us.** When Phase 3 lands squashfs skills, **adopt the bake-at-provisioning model for user skills too,** not just Anthropic's "system" ones. No runtime hot-reload of skills. This is consistent with our Phase 3 acceptance ("Sandbox image no longer carries `/usr/local/share/skills/` baked in") — the skills come from S3 squashfs blobs, but they're materialized **once per VM at boot**, not watched for updates during the session.

---

## Layer 6 — VM lifecycle: pause/resume between messages

VMs are **not kept alive between user messages.** They are paused and resumed via Firecracker snapshot/restore. Evidence:

| Signal | Value | What it means |
|---|---|---|
| `uptime -s` | `2026-05-17 14:39:51` | Kernel boot |
| `stat /home/claude` Birth | `2026-05-17 12:08:21` | rootfs was built earlier — golden image |
| Wall clock at observation | `2026-05-17 15:15:01` | ~35 min into uptime, but most directories older |
| Empty `dmesg` since uptime+5s | no warm-running noise | VM was resumed from snapshot mid-execution; little post-boot activity |

The control plane orchestrates this — VM resume on first user message arrival, pause after agent's reply lands, snapshot the dirty pages, hand the VM back to the warm-pool. Cold sessions ≥ N minutes old are torn down completely; the FUSE mounts re-bind to the same S3 prefix the next time the chat is opened, so the user's workspace returns even if the VM didn't.

### 6.1 Full lifecycle (reconstructed from evidence)

```text
1. User opens a new chat
   └─ control plane clones golden-rootfs.img → my-vm.img (CoW snapshot at storage layer)
   └─ injects /mnt/skills/user/* into rootfs (from S3 / DB source-of-truth at this instant)
   └─ injects container_info.json (session_id, limits)
   └─ Firecracker start --drive my-vm.img --kernel vmlinuz...

2. Boot
   └─ kernel cmdline → rdinit=/process_api → PID 1
   └─ process_api mounts vdb (rclone bin), vdc (skills public), vdd (skills examples)
   └─ process_api starts rclone-filestore multimount → touches ready_file when 4 mounts up
   └─ process_api signals control plane: ready

3. User sends a message
   └─ control plane resumes VM (FC snapshot restore, ~100ms) — or cold-boots if needed
   └─ agent runs: writes to /home/claude (ext4 delta on vda), reads/writes /mnt/user-data/* (FUSE → S3)
   └─ control plane pauses VM after reply (FC snapshot)

4. Chat idle / closed
   └─ Firecracker SIGTERM → process_api → rclone graceful umount → exit
   └─ my-vm.img CoW delta discarded
   └─ S3 prefix remains for restore

5. User returns to chat (even days later)
   └─ control plane provisions a NEW VM with the SAME session_id (filesystem_id)
   └─ FUSE-mount re-binds to the existing S3 prefix
   └─ workspace re-appears — but skills may be updated (provisioned fresh)
```

**Takeaway for us.** This is the right cost model for our Phase 9 templates: VMs are not long-running; they're paused/resumed on the order of message latency. Snapshotting is the architecture, not an optimization. Folds into Phase 10 (snapshot/restore) as the canonical pattern.

---

## Final mental model — storage by data class

| Data class | Examples | Storage | Lifecycle | Delivery |
|---|---|---|---|---|
| **System binaries** | `rclone-filestore`, agent runtime | `squashfs` on a dedicated `ro` disk | versioned artifact | bake into VM image (sealed disk) |
| **System skills** | `/mnt/skills/public`, `/mnt/skills/examples` | `squashfs` on dedicated `ro` disks | per template version, immutable | sealed disks, bit-identical across sessions |
| **User customization** | `/mnt/skills/user`, dotfiles | `ext4` on rootfs | per-user mutable | **inject at provisioning** (not runtime) |
| **Session workspace** | `/home/claude`, `/tmp`, scratch | `ext4` on rootfs (CoW delta) | ephemeral, dies with VM | **CoW snapshot of golden rootfs** |
| **Persistent state** | uploads, outputs, tool_results | S3 via FUSE | per session, survives VM | runtime FUSE mount, server-side auth |
| **Identity** | `session_id` | `container_info.json` | per session | inject at provisioning |

**Where PVC fits in this picture: it does not.** Every row above has a better answer than RWO PVC:

- Ephemeral workspace → CoW snapshot at the storage layer is cheaper, faster, and gives stronger reset-on-spawn guarantees than a wiped-on-claim PVC. No claim controller, no quota controller, no GC.
- Persistent state → S3 with server-side auth is stronger than a PVC reused across sessions (auth boundary, no GC), and trivially multi-region.
- System binaries / skills → sealed `squashfs` is stronger than a PVC (immutable, not just "shouldn't change").

PVC remains the right answer for **classical workloads** that our sandbox runtime does not host: PostgreSQL, Redis, Prometheus, etcd. For agent sandboxes specifically, it's the wrong primitive. See [A37](../antipatterns.md#a37--pvc-for-sandbox-session-workspace).

---

## Implications and where they land in the roadmap

| Layer in this file | Roadmap target | What feeds in |
|---|---|---|
| 1 — Firecracker init, kernel cmdline | [Phase 9](../roadmap.md#phase-9) (Kata + CH) and Phase 7 (guest agent) | Adopt kernel hardening flag set as template default. Agent PID-1 design copies `process_api` shape — single Go binary, supervises children, exposes control-plane WS. |
| 2 — Multi-disk squashfs + CoW rootfs | [Phase 3](../roadmap.md#phase-3) (storage MVP) and Phase 9 | Squashfs for system binaries / skills lands at Phase 3. CoW rootfs (qcow2 backing) lands at Phase 9 as the per-VM disk. Reject PVC for Tier 3 now ([A37](../antipatterns.md#a37--pvc-for-sandbox-session-workspace)). |
| 3 — rclone multimount, VFS TTLs | [Phase 3](../roadmap.md#phase-3) | Adopt TTL-per-semantic table verbatim. Defer multimount fork; ship one `rclone` process per mount until measured boot bottleneck. Adopt `ready_file` synchronization pattern at Phase 7. |
| 4 — No S3 creds in guest | [Phase 4](../roadmap.md#phase-4) (secret broker) | Target end-state: guest carries `filesystem_id` only, broker holds S3 creds server-side. Stronger than the Phase 4 STS-token-in-guest baseline. Folds into Phase 4 research as the stretch goal. |
| 5 — Skills bake-at-provisioning | [Phase 3](../roadmap.md#phase-3) | When squashfs skills land, materialize at provisioning, not runtime. No hot-reload. |
| 6 — VM pause/resume | [Phase 10](../roadmap.md#phase-10) | Snapshot/restore is the lifecycle, not an optimization. Phase 10 acceptance must include pause/resume across messages, not just cold start. |

---

## What to copy verbatim from Anthropic's design

When the corresponding phase ships, take these patterns as-is:

1. **Firecracker microVM + custom Go init via `rdinit=`.** No systemd, no Docker, no containerd inside the guest. — Phase 7 + Phase 9.
2. **Multi-disk layout: ext4 rootfs + sealed `squashfs` for system binaries and system skills.** — Phase 3 (skills disk) + Phase 9 (binaries disk).
3. **CoW snapshot rootfs** via `qcow2` backing files / `dm-thin` / ZFS clone. Storage-level CoW, **NOT** overlayfs inside the guest. — Phase 9.
4. **Two-tier rclone.** Custom multimount inside the VM, `rclone serve` outside the VM. No S3 keys in the guest. — Phase 4 stretch.
5. **`filesystem_id` session-token auth.** Guest carries only the token; storage proxy maps token → bucket prefix. — Phase 4 stretch.
6. **Skills materialized at provisioning, not runtime.** No hot-reload. — Phase 3.
7. **ext4 `resuid=65534,resgid=65534` (`nobody:nogroup`) for cheap per-VM quota.** — Phase 9 (template default).
8. **VM pause/resume via FC snapshots** between user messages; warm-pool of paused VMs, not running ones. — Phase 10.

## What to simplify on day one (not copy)

- **Do not fork rclone yet.** Use `rclone serve webdav` outside + `rclone mount` inside. Add `multimount` only when start-up time hurts. — Phase 3.
- **Do not write a custom Go init yet.** Use `tini` / `dumb-init` + a shell script. Custom Go `process_api` arrives only when the shell glue runs out. — Phase 7.
- **Do not chase ext4 reserved-blocks quota in Phase 3 / 5.** A 10 GiB disk volume gives the same UX. The trick lands in Phase 9 with the Kata templates. — Phase 9.

## What NOT to copy

- **No FUSE-in-guest before Kata / Firecracker.** On `containerd` + `runc`, FUSE-in-guest requires `--privileged`, which voids isolation. Until Phase 9, mount FUSE on the host or in a sidecar (CSI w/ FUSE-on-node). — Phase 5–8.
- **No overlayfs inside the guest as the workspace layer.** Storage-level CoW (qcow2 / ZFS / dm-thin) is strictly better in every dimension except operator simplicity. The operator cost is paid once at the runtime layer; the benefit accrues to every VM. — Phase 9.

---

## How to reproduce these observations

If we ever want to redo the live-VM walk (e.g., to capture new flags after an Anthropic infrastructure update), the commands are:

```bash
cat /proc/cmdline                      # kernel cmdline → Firecracker + flags
ps -ef                                  # find PID 1 = /process_api
lsblk -o NAME,MAJ:MIN,SIZE,RO,TYPE,MOUNTPOINT   # 4-disk layout
findmnt -A                              # mount-by-mount with options (TTLs, resuid)
mount | grep -E '(ext4|squashfs|fuse)'  # cross-check
cat /tmp/rclone-mount-config.json       # rclone session-token config (path observed in one session; may vary)
sha256sum /mnt/skills/user/foo/SKILL.md # skill fingerprint
uptime -s                               # boot time
stat /                                  # Birth time on rootfs → CoW evidence
/opt/rclone/rclone-filestore --help     # discover multimount + flags
```

Run inside any live session within the first minute (some paths get touched later). Save outputs verbatim into a new `research/NN-anthropic-*-observed.md` next time — comparison across snapshots is how we caught the skills-at-provisioning rule (§5.1).
