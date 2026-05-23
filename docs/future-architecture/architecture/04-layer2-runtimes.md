<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# 04 — Layer 2: Sandbox Runtimes

> The actual isolation primitive that wraps Layer 1 (the agent + workload).
> Selected **per template**, not globally. Same agent, same orchestrator, different runtime → different threat-model fit.

## Runtime matrix

| Runtime | Cold start | RAM overhead | Isolation | Use case | Status in our stack |
|---|---|---|---|---|---|
| **runc** | ~30 ms | ~2 MB | Namespaces only — none for untrusted code | Dev / CI | Today via Docker Compose |
| **sysbox** | ~50 ms | ~5 MB | + user-ns remap, procfs emulation; shares host kernel | Internal trusted users; DinD; systemd | Today via Helm (current default) |
| **gVisor** | ~50 ms | ~15-25 MB | Userspace kernel intercepts syscalls | Code-execution sandboxes (no browser) | Experimental, Phase 7+ |
| **Kata + Firecracker** (`kata-fc`) | ~125 ms | ~5-10 MB | KVM hypervisor, minimal device model | Public untrusted, fastest cold start | Phase 9 |
| **Kata + Cloud Hypervisor** (`kata-ch`) | ~150 ms | ~10-20 MB | KVM hypervisor + virtio-fs + GPU passthrough | **Computer Use (browser)** untrusted | Phase 9 (primary target) |
| **Kata + QEMU** | ~500 ms | ~50 MB | KVM hypervisor, full device model | Compatibility fallback | Not planned |

Numbers from [`sandboxd/docs/architecture.md`](../../../sandboxd/docs/architecture.md). Validate during Phase 9 research on actual hardware.

## Why Cloud Hypervisor is the lead untrusted runtime (not Firecracker)

- **virtio-fs** — fast shared mounts; Firecracker omits this. Important for skill blobs and user-data overlays (see [06-storage.md](./06-storage.md)).
- **GPU passthrough** — relevant if Computer Use workloads ever need accelerated rendering.
- **Hot-plug** — easier resource adjustments.
- Trade-off: ~80K LoC vs Firecracker's ~50K (larger attack surface, still small).

Firecracker stays available via `kata-fc` for the fastest-cold-start tier (e.g., free-tier anonymous trials). Note that Firecracker is the microVM that AWS Lambda and Fargate are built on — its scale-pattern lineage informs the Phase 10 snapshot-pool design ([`research/20`](../research/20-snapstart-hot-swap.md)) without making us a Lambda deployment. See the Lambda framing in [`references.md`](../references.md) and [ADR-0010](../adr/0010-lambda-as-inspiration-not-runtime.md).

## virtio-fs vs 9p — the CH/FC asymmetry

CH and FC do not agree on shared-filesystem story, and the difference is load-bearing for Tier-2 (skills) and Tier-4 (user data) mounts:

| | virtio-fs | 9p |
|---|---|---|
| Cloud Hypervisor | First-class (default) | Possible but not the natural path |
| Firecracker upstream | **Not supported** in stock Firecracker | The historical option; out-of-tree patches and Kata wrappers exist |
| Performance | Native-ish (FUSE protocol, shared page cache) | Slower; protocol overhead dominates |
| Posix coverage | High | Lower (the legacy choice) |

Implication: `kata-ch` is the only tier where Tier-2 / Tier-4 mounts are "free." On `kata-fc` we either accept 9p's performance/POSIX trade-offs, lean on rclone-FUSE-inside-VM (per [`research/16`](../research/16-anthropic-production-sandbox-observed.md) §3), or block-device-mount squashfs (per [`research/20`](../research/20-snapstart-hot-swap.md) §6). Phase 9 research locks the choice per tier.

## nydus snapshotter for lazy image-layer load

For the microVM tiers (`kata-fc`, `kata-ch`), pulling the full container image at sandbox spawn is the single biggest cold-start cost. **nydus** ([nydus-snapshotter](https://github.com/containerd/nydus-snapshotter), Apache 2.0) reformats OCI images into a chunk-addressable layout that the VM can lazy-load on demand — pages are fetched as files are touched, not upfront.

- **Relevance.** Phase 9 cold-start budget for `kata-ch` is in the 100–200 ms range with full image pull. Lazy-load with nydus gets that closer to template-snapshot territory ([`research/20`](../research/20-snapstart-hot-swap.md)) without the snapshot-pool engineering bill.
- **Trade-off.** Adds a new component to the runtime path; failure modes (registry hiccups mid-execution) need their own playbook.
- **Decision.** Phase 9 research evaluates whether nydus or a snapshot pool (or both, layered) hits the cold-start target.

## VMM Lambda lineage (one paragraph, by reference)

Firecracker exists because AWS needed a VMM small enough to scale Lambda/Fargate. Anthropic's `process_api` and our Phase-9 `kata-fc` tier both inherit from that lineage. The architectural takeaway is the **VMM design** (minimal device model, small attack surface, fast init) — not the deployment substrate. See [`references.md`](../references.md) Lambda framing, [`research/05`](../research/05-firecracker.md), and [ADR-0010](../adr/0010-lambda-as-inspiration-not-runtime.md) for the closed answer to "are we going to run on Lambda?" (no).

## Why NOT gVisor for browsers

Already a locked decision from the pre-existing `docs/requirements/k8s-architecture.md`:

> compatibility envelope too narrow for Chromium with sandbox flags, Playwright, browser downloads

gVisor remains viable for non-browser code-execution sandboxes (e.g., a "run this Python snippet" tier). Phase 7 validates this as an optional experimental tier.

## Selection mechanism

- **In k8s:** `Pod.spec.runtimeClassName` — installed via `kata-deploy` DaemonSet (for kata-*) and `gvisor` runtimeclass.
- **Direct (DirectCHProvider):** hypervisor invocation, no k8s.
- **In Docker Compose:** runc only (the PoC); sysbox optional if the host has it. Compose is not the prod runtime story.

`SandboxTemplate.runtime_class` carries the choice; the provider plumbs it. See [09-templates.md](./09-templates.md).

## Threat-model matrix (target tiering)

| Tenant tier | Workload | Runtime |
|---|---|---|
| Internal employees + trusted scripts | Code only | sysbox (or runc in dev) |
| Internal employees + Computer Use | Browser, file ops | sysbox |
| External customer + code only | Code only | gVisor or `kata-ch` |
| External customer + Computer Use | Browser | `kata-ch` |
| Anonymous trial | Anything | `kata-fc` |

The control plane (L4) picks the template (and thereby the runtime) based on tenant tier at session-spawn time.

## Hardware / cluster requirements

- **runc, sysbox, gVisor:** any Linux kernel ≥ 5.x. Run on any cloud VM, including managed k8s (EKS, GKE on standard nodes).
- **kata-fc, kata-ch:** require **bare-metal** k8s nodes — KVM is needed and nested-virt won't reliably work in most cloud VMs.
  - On AWS: `m6i.metal` / `c6i.metal` etc.
  - On-prem RKE2: any host with `/dev/kvm`.
  - Use a **dedicated node pool with taints** to keep regular workloads off the bare-metal nodes (they're expensive).

## What ships, when

- **Phase 1–4:** runc only (via Docker Compose) and sysbox (via existing Helm chart). No L2 change.
- **Phase 5:** real `KubernetesProvider` ships with sysbox as default; the Helm chart switches from DinD-in-pod to real per-pod sandboxes on sysbox.
- **Phase 7:** gVisor added as experimental tier for non-browser sandboxes; runtime selection becomes per-template.
- **Phase 9:** `kata-ch` and `kata-fc` added; bare-metal node pool required; multi-tier templates land.

## Security boundary per runtime (one-liner)

| Runtime | Primary boundary | Boundary fails if… |
|---|---|---|
| runc | Linux namespaces | …kernel CVE (Dirty Pipe, nf_tables) — assume escapable |
| sysbox | Above + user-ns + emulation | …kernel CVE; sysbox bugs |
| gVisor | Sentry userspace kernel (Go) | …Sentry bug; passthrough syscall path |
| kata-fc | KVM + Firecracker VMM | …Firecracker CVE; KVM CVE; side-channel |
| kata-ch | KVM + Cloud Hypervisor VMM | …CH CVE; KVM CVE; side-channel |

See [07-security.md](./07-security.md) for the full threat model.

## Source

- [`sandboxd/docs/security.md`](../../../sandboxd/docs/security.md)
- [`sandboxd/docs/architecture.md`](../../../sandboxd/docs/architecture.md)
- [`docs/future-architecture/references.md`](../references.md) (every runtime URL listed there)
