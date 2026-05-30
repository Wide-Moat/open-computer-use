<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# 06 — Storage

> Four-tier model (carried over from the old `docs/requirements/k8s-architecture.md` and elevated to a layer-agnostic spec).
> Applies regardless of L2 runtime or L3 provider.

## The four tiers

| Tier | What | Mode | Lifetime | Backend |
|---|---|---|---|---|
| **1. Image layers** | OS, runtimes, guest agent | RO | per release | OCI registry (cached on host); sealed `squashfs` block disks for the binaries / skills split once Phase 9 lands |
| **2. Skills** | AI capability bundles (`skills/`) | RO | per release, immutable | Object store (S3) as squashfs blobs; **materialized at provisioning, not runtime** ([no hot-reload](../research/22-anthropic-firecracker-microvm-internals-observed.md#layer-5--skills-as-a-provisioning-time-concern-not-a-runtime-one)) |
| **3. Workspace home** | `/home/assistant` per session | RW | per session, ephemeral | **CoW snapshot of golden rootfs** (qcow2 backing / dm-thin / ZFS clone) on Kata/CH; tmpfs / overlayfs on sysbox/runc. **Never PVC** (see [A37](../antipatterns.md#a37--pvc-for-sandbox-session-workspace)) |
| **4. User data** | uploads, outputs, tool results | RW | per tenant | S3-compatible object storage, reached via a FUSE client speaking file-ops to a host-side storage broker; **no S3 credentials inside the guest** ([session-token auth](../research/22-anthropic-firecracker-microvm-internals-observed.md#layer-4--credentials-identity-and-the-no-s3-keys-in-the-guest-rule)) |

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
- **Phase 9 target (Kata + CH / FC):** **CoW snapshot of a golden rootfs image** at the storage layer — `qcow2` backing files, `dm-thin` snapshots, or ZFS `clone`. This is the pattern observed in Anthropic's production sandbox ([`research/22-anthropic-firecracker-microvm-internals-observed.md` §2.3](../research/22-anthropic-firecracker-microvm-internals-observed.md#23-rootfs-as-cow-snapshot--the-pvc-replacement-pattern-)). Per-session ext4 deltas live on the snapshot; the delta is discarded at session end. The golden image is shared and untouched.
- **No PVC for the session workspace tier in any template.** RWO PVC is rejected — CoW snapshot is cheaper, faster, and gives stronger reset-on-spawn guarantees with no claim controller, no quota controller, no garbage collection. See [A37](../antipatterns.md#a37--pvc-for-sandbox-session-workspace) for the locked-decision rationale. "Continue yesterday's session" is served by Tier 4 (S3) — the workspace re-binds to the same `filesystem_id` prefix on the next VM, no PVC needed.
- **Per-VM soft cap.** Phase 9 templates set ext4 `resuid=65534,resgid=65534` so reserved blocks are claimable by no one, yielding a cheap per-VM ENOSPC ceiling without a quota daemon ([§2.2](../research/22-anthropic-firecracker-microvm-internals-observed.md#22-the-ext4-reserved-blocks-quota-trick)). Phase 3 / 5 can ship with a plain 10 GiB volume.

## Tier 4 — User data

- Three logical buckets per tenant: `uploads/` (user → sandbox), `outputs/` (sandbox → user), `tool-results/` (intermediate artifacts surfaced in UI).
- **Backend:** S3-compatible. Production: AWS S3 / GCS / R2 / Ceph RGW. Local PoC: MinIO in `docker-compose.yml`.
- **Broker model (the object-store credential is never in the guest).** The guest mounts a FUSE filesystem that speaks a file-operation interface to a host-side storage broker; the broker is the object-store client and signs its own backend requests. The guest never speaks the object-store protocol and never holds an STS token. This is the canonical model in [`02-trust-boundaries.md`](../../architecture/02-trust-boundaries.md) §2 zone 3 / §7.1 and [NFR-SEC-25](../../architecture/manifesto/02-nfrs.md), matched by Anthropic's `rclone-filestore` (a custom `anthropic.filestore.v1alpha` Connect-RPC fork, not stock S3-mount) and by Daytona's runner-as-S3-client volume model.
- **Guest-side FUSE client.** A FUSE backend that speaks the broker's file-RPC — Anthropic forks rclone for this; a thin custom backend is the alternative. Stock `rclone mount` straight to S3 (70+ backends, VFS cache) is the *interim PoC shortcut* only, and only where the guest is trusted; it is not the target, because it puts the object-store credential and protocol in the guest.
  - `mountpoint-s3` — AWS-native, fastest, **sequential-write-only**; usable behind the broker, rejected as a guest-facing primary.
  - `geesefs` — better random-write than mountpoint-s3, smaller backend set.
- **Backend credential:** held by the broker, never the guest. Short-lived **STS scoped-session** credentials minted per session, locked by inline session policy to the bucket-prefix the `filesystem_id` names ([07-security.md](./07-security.md)). Not static keys. The broker's backend leg traverses the Egress trust-edge allow-list-only (no TLS termination), so the request signature stays intact.
- **Lifecycle policy** at the S3 layer replaces the current `find /tmp -mtime` cleanup cron.

## Mounts spec on the sandbox

The (planned) `SandboxTemplate` will declare its mounts; the provider (L3) materializes them. Target shape (prospective schema — not implemented today):

```yaml
mounts:
  - type: image                       # Tier 1 — implicit
  - type: skill
    ref: sha256:abcdef…               # Tier 2 — content-addressed
    path: /usr/local/share/skills/pptx
    mode: ro
  - type: workspace
    persistence: ephemeral            # only "ephemeral"; PVC rejected (A37)
    backend: cow-snapshot             # prospective Phase 9 field, not in schema today: qcow2 | dm-thin | zfs-clone; overlayfs (sysbox/runc)
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
| 4 | Storage broker holds the backend credential (per-session STS, not static keys); guest speaks file-RPC to the broker and holds only a `filesystem_id` handle |
| 5 | K8s provider keeps Tier 3 ephemeral (tmpfs / overlayfs on sysbox); no PVC for sandbox session workspace ([A37](../antipatterns.md#a37--pvc-for-sandbox-session-workspace)); FUSE pattern carried to pods |
| 8 | virtio-fs replaces FUSE on kata-ch (faster, kernel-level) |
| 9 | Tier 3 = CoW snapshot of golden rootfs (qcow2 / dm-thin / ZFS) on Kata templates; ext4 `resuid=65534` per-VM ceiling; sealed `squashfs` disks for binaries / system skills ([`research/22`](../research/22-anthropic-firecracker-microvm-internals-observed.md)) |

## Block-device tooling swap (microVM templates, Phase 10)

Once the snapstart pattern lands ([`research/20-snapstart-hot-swap.md`](../research/20-snapstart-hot-swap.md)), Tier-1 and Tier-2 content stops being "OCI layers pulled at spawn" and becomes **block devices the host swaps at resume**. The L1 agent's job is to remount them when the host signals readiness via `POST /mount_root` on its control server.

Layout per session (Firecracker / Cloud Hypervisor microVM):

| Device | Content | Mode | Lifetime |
|---|---|---|---|
| `vda` | per-tenant root overlay on a shared template base (ext4) | RW | per session |
| `vdb` | Tier 2 skills (squashfs of `/opt/skills`) | RO | per release |
| `vdc` | Tier 1 runtime/payload (squashfs of `/opt/<runner>`) | RO | per release |
| Tier-4 mounts | rclone-FUSE-in-VM as today | RW (where applicable) | per tenant |

Per-resume sequence on the L1 side (the host does the device swap first, then calls `/mount_root`):

1. `drop_caches` — page cache references files from the frozen rootfs that no longer exist.
2. Remount devtmpfs.
3. Mount `/dev/vda` as ext4, `pivot_root` into it.
4. Mount `/dev/vdb`, `/dev/vdc` squashfs overlays.
5. `clock_settime()` (the wall-clock was frozen).
6. Trigger CRNG reseed (see [07-security.md](./07-security.md) snapstart-restore hardening).
7. Drop `CAP_SYS_RESOURCE`.
8. Start accepting WS connections.

The pattern lifts directly from `process_api` / Baku ([`research/19`](../research/19-anthropic-process-api.md) §5, §9; [`research/20`](../research/20-snapstart-hot-swap.md) §2). Tier-2 stays as squashfs in both the OCI-layer world and the block-device world — the format is the same, only the delivery channel changes. **Skills built before Phase 10 are forward-compatible.**

Implication for the release pipeline (Phase 10): tooling produces both an OCI image *and* a paired set of `vdb` / `vdc` squashfs blobs from the same source. Both are signed; both are referenced by content hash from templates. Phase 9 templates use only OCI; Phase 10 templates may use either, gated on `snapstart_compatible` ([09-templates.md](./09-templates.md)).

## Explicit non-goals

- **No RWX (ReadWriteMany).** Single-writer patterns only. Avoids EFS/Filestore complexity and consistency surprises.
- **No proprietary CSI drivers.** S3-compatible API only.
- **No custom storage *transport*.** The mount substrate uses existing FUSE / virtio-fs / CSI building blocks — we do not write a block protocol. The storage *broker* (credential custody + object-store client + per-session scope) is a deliberate component, not a transport; it is the canonical model, not a workaround ([`02-trust-boundaries.md`](../../architecture/02-trust-boundaries.md) §2 zone 3).
- **No PVC for the sandbox session workspace (Tier 3).** Locked decision — see [A37](../antipatterns.md#a37--pvc-for-sandbox-session-workspace). CoW snapshot at the storage layer replaces it. PVC remains the right primitive for stateful platform services (PostgreSQL, Redis, Prometheus, etcd) — none of which our sandbox runtime hosts.
- **No S3 credentials inside the sandbox guest.** Tier 4 Phase 4 target end-state: guest carries a `filesystem_id` session token, broker / storage proxy holds S3 keys server-side ([`research/22` §4](../research/22-anthropic-firecracker-microvm-internals-observed.md#layer-4--credentials-identity-and-the-no-s3-keys-in-the-guest-rule)).
- **No skill hot-reload.** Skills materialize at provisioning, are immutable for the lifetime of the VM ([`research/22` §5](../research/22-anthropic-firecracker-microvm-internals-observed.md#layer-5--skills-as-a-provisioning-time-concern-not-a-runtime-one)).

## Source

- `docs/requirements/k8s-architecture.md` (pre-rename — original 4-tier spec)
- [`sandboxd/docs/architecture.md`](../../../sandboxd/docs/architecture.md) (storage section)
