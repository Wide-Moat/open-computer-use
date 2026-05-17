<!-- SPDX-License-Identifier: BUSL-1.1 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# 06 — Storage

> Four-tier model (carried over from the old `docs/requirements/k8s-architecture.md` and elevated to a layer-agnostic spec).
> Applies regardless of L2 runtime or L3 provider.

## The four tiers

| Tier | What | Mode | Lifetime | Backend |
|---|---|---|---|---|
| **1. Image layers** | OS, runtimes, guest agent | RO | per release | OCI registry (cached on host) |
| **2. Skills** | AI capability bundles (`skills/`) | RO | per release, immutable | Object store (S3) as squashfs blobs |
| **3. Workspace home** | `/home/assistant` per session | RW | per session (ephemeral default; opt-in PVC) | tmpfs / overlayfs / RWO PVC |
| **4. User data** | uploads, outputs, tool results | RW | per tenant | S3-compatible object storage, mounted via FUSE sidecar |

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

- `/home/assistant` is the AI agent's working directory.
- **Default ephemeral:** tmpfs or overlayfs over image layer. Vanishes when sandbox dies.
- **Opt-in persistent:** RWO PVC (k8s) or named volume (Compose), keyed by `session_id` or `tenant_id+project_id`. Single-writer always — no RWX. Explicit cleanup policy required.

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
    persistence: ephemeral            # or "pvc:claim-name"
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
| 5 | K8s provider uses PVCs (RWO) for Tier 3 opt-in persistence; FUSE pattern carried to pods |
| 8 | virtio-fs replaces FUSE on kata-ch (faster, kernel-level) |

## Explicit non-goals

- **No RWX (ReadWriteMany).** Single-writer patterns only. Avoids EFS/Filestore complexity and consistency surprises.
- **No proprietary CSI drivers.** S3-compatible API only.
- **No custom storage gateway.** Use existing FUSE / virtio-fs / CSI building blocks.

## Source

- `docs/requirements/k8s-architecture.md` (pre-rename — original 4-tier spec)
- [`sandboxd/docs/architecture.md`](../../../sandboxd/docs/architecture.md) (storage section)
