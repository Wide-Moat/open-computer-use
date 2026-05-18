<!-- SPDX-License-Identifier: BUSL-1.1 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# 06 — Storage

> Four-tier model (carried over from the old `docs/requirements/k8s-architecture.md` and elevated to a layer-agnostic spec).
> Applies regardless of L2 runtime or L3 provider.

## The four tiers

| Tier | What | Mode | Lifetime | Backend |
|---|---|---|---|---|
| **1. Image layers** | OS, runtimes, guest agent | RO | per release | OCI registry (cached on host); sealed `squashfs` block disks for the binaries / skills split once Phase 9 lands |
| **2. Skills** | AI capability bundles (`skills/`) | RO | per release, immutable | Object store (S3) as squashfs blobs; **materialized at provisioning, not runtime** ([no hot-reload](../research/19-anthropic-firecracker-microvm-internals-observed.md#layer-5--skills-as-a-provisioning-time-concern-not-a-runtime-one)) |
| **3. Workspace home** | `/home/assistant` per session | RW | per session, ephemeral | **CoW snapshot of golden rootfs** (qcow2 backing / dm-thin / ZFS clone) on Kata/CH; tmpfs / overlayfs on sysbox/runc. **Never PVC** (see [A37](../antipatterns.md#a37--pvc-for-sandbox-session-workspace)) |
| **4. User data** | uploads, outputs, tool results | RW | per tenant | S3-compatible object storage, mounted via FUSE sidecar; **no S3 credentials inside the guest** ([session-token auth](../research/19-anthropic-firecracker-microvm-internals-observed.md#layer-4--credentials-identity-and-the-no-s3-keys-in-the-guest-rule)) |

## Tier 1 — Image

- Standard OCI image. Built once per release. Pulled to nodes via image cache.
- Includes the guest agent binary (today: Python entrypoint; Phase 7+: Go binary).
- **Signed with cosign** ([07-security.md](./07-security.md)); admission controller verifies signature.
- **Immutable reference by digest, never tag** in production templates.

## Tier 2 — Skills

Current state: skills are baked into the image (`/usr/local/share/skills/...`).

Target state (Phase 3):
- Each skill packaged as a `.squashfs` blob at release time, pushed to S3.
- Sandbox manifests reference skills by content-hash (`SkillRef`).
- Mounted RO into the sandbox via squashfuse / kernel squashfs (decision deferred to Phase 3 research — needs `CAP_SYS_ADMIN` for kernel mount, doesn't for squashfuse; sandbox cap surface matters).
- Drops the current ZIP cache; immutability contract guarantees "skill v1.2.3 is bit-identical everywhere".

Benefits:
- Skill updates without rebuilding the sandbox image
- Multi-version coexistence (template A pins skill v1; template B pins v2)
- Smaller image (skills move out)

## Tier 3 — Workspace home

- `/home/assistant` is the AI agent's working directory. **Always ephemeral.** Vanishes when the sandbox dies.
- **Compose / k8s today (sysbox, runc):** tmpfs or overlayfs over the image layer.
- **Phase 9 target (Kata + CH / FC):** **CoW snapshot of a golden rootfs image** at the storage layer — `qcow2` backing files, `dm-thin` snapshots, or ZFS `clone`. This is the pattern observed in Anthropic's production sandbox ([`research/19-anthropic-firecracker-microvm-internals-observed.md` §2.3](../research/19-anthropic-firecracker-microvm-internals-observed.md#23-rootfs-as-cow-snapshot--the-pvc-replacement-pattern-)). Per-session ext4 deltas live on the snapshot; the delta is discarded at session end. The golden image is shared and untouched.
- **No PVC for the session workspace tier in any template.** RWO PVC is rejected — CoW snapshot is cheaper, faster, and gives stronger reset-on-spawn guarantees with no claim controller, no quota controller, no garbage collection. See [A37](../antipatterns.md#a37--pvc-for-sandbox-session-workspace) for the locked-decision rationale. "Continue yesterday's session" is served by Tier 4 (S3) — the workspace re-binds to the same `filesystem_id` prefix on the next VM, no PVC needed.
- **Per-VM soft cap.** Phase 9 templates set ext4 `resuid=65534,resgid=65534` so reserved blocks are claimable by no one, yielding a cheap per-VM ENOSPC ceiling without a quota daemon ([§2.2](../research/19-anthropic-firecracker-microvm-internals-observed.md#22-the-ext4-reserved-blocks-quota-trick)). Phase 3 / 5 can ship with a plain 10 GiB volume.

## Tier 4 — User data

- Three logical buckets per tenant: `uploads/` (user → sandbox), `outputs/` (sandbox → user), `tool-results/` (intermediate artifacts surfaced in UI).
- **Backend:** S3-compatible. Production: AWS S3 / GCS / R2 / Ceph RGW. Local PoC: MinIO in `docker-compose.yml`.
- **Mounted via FUSE sidecar** in the sandbox pod (k8s) or as a service container (Compose). **Baseline backend: `rclone mount` with VFS full cache** — production-validated in Anthropic's sandbox (see [`research/16-anthropic-production-sandbox-observed.md`](../research/16-anthropic-production-sandbox-observed.md)). Final decision locked at Phase 3 research; alternatives kept in scope for that pass:
  - `rclone mount` — **baseline.** Most flexible, supports 70+ backends, VFS cache gives ~POSIX semantics (SQLite, random write, append, fsync all work). Known limits: hardlinks, symlinks, chmod silent-fail.
  - `mountpoint-s3` — AWS-native, fastest, **sequential-write-only** (incompatible with atomic-file write patterns). Rejected as primary for AI-agent workloads.
  - `geesefs` — better random-write than mountpoint-s3 but smaller backend set than rclone.
  - `csi-rclone` / `juicefs-csi` — for k8s production once Phase 5 ships.
- **Credentials:** short-lived STS tokens minted by the L4 secret broker per session ([07-security.md](./07-security.md)). Not static AWS keys.
- **Lifecycle policy** at the S3 layer replaces the current `find /tmp -mtime` cleanup cron.

## Mounts spec on the sandbox

The `SandboxTemplate` declares its mounts; the provider (L3) materializes them. Example shape:

```yaml
mounts:
  - type: image                       # Tier 1 — implicit
  - type: skill
    ref: sha256:abcdef…               # Tier 2 — content-addressed
    path: /usr/local/share/skills/pptx
    mode: ro
  - type: workspace
    persistence: ephemeral            # only "ephemeral"; PVC rejected (A37)
    backend: cow-snapshot             # qcow2 | dm-thin | zfs-clone (Phase 9); overlayfs (sysbox/runc)
    path: /home/assistant
  - type: user-data
    backend: s3
    bucket: tenant-{tenant_id}-data
    prefix: sessions/{session_id}/
    path: /mnt/user-data
    mode: rw
```

## What changes per phase

| Phase | Storage change |
|---|---|
| 1 | None — extract provider interface only |
| 2 | None directly; provider learns mount specs but Docker still binds local fs |
| 3 | MinIO into Compose; `S3_*` config; FUSE sidecar pattern; squashfs skill blobs |
| 4 | Per-session STS tokens replace static S3 creds |
| 5 | K8s provider keeps Tier 3 ephemeral (tmpfs / overlayfs on sysbox); no PVC for sandbox session workspace ([A37](../antipatterns.md#a37--pvc-for-sandbox-session-workspace)); FUSE pattern carried to pods |
| 8 | virtio-fs replaces FUSE on kata-ch (faster, kernel-level) |
| 9 | Tier 3 = CoW snapshot of golden rootfs (qcow2 / dm-thin / ZFS) on Kata templates; ext4 `resuid=nobody` per-VM ceiling; sealed `squashfs` disks for binaries / system skills ([`research/19`](../research/19-anthropic-firecracker-microvm-internals-observed.md)) |

## Explicit non-goals

- **No RWX (ReadWriteMany).** Single-writer patterns only. Avoids EFS/Filestore complexity and consistency surprises.
- **No proprietary CSI drivers.** S3-compatible API only.
- **No custom storage gateway.** Use existing FUSE / virtio-fs / CSI building blocks.
- **No PVC for the sandbox session workspace (Tier 3).** Locked decision — see [A37](../antipatterns.md#a37--pvc-for-sandbox-session-workspace). CoW snapshot at the storage layer replaces it. PVC remains the right primitive for stateful platform services (PostgreSQL, Redis, Prometheus, etcd) — none of which our sandbox runtime hosts.
- **No S3 credentials inside the sandbox guest.** Tier 4 Phase 4 target end-state: guest carries a `filesystem_id` session token, broker / storage proxy holds S3 keys server-side ([`research/19` §4](../research/19-anthropic-firecracker-microvm-internals-observed.md#layer-4--credentials-identity-and-the-no-s3-keys-in-the-guest-rule)).
- **No skill hot-reload.** Skills materialize at provisioning, are immutable for the lifetime of the VM ([`research/19` §5](../research/19-anthropic-firecracker-microvm-internals-observed.md#layer-5--skills-as-a-provisioning-time-concern-not-a-runtime-one)).

## Source

- `docs/requirements/k8s-architecture.md` (pre-rename — original 4-tier spec)
- [`sandboxd/docs/architecture.md`](../../../sandboxd/docs/architecture.md) (storage section)
