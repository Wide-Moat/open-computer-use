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

Firecracker stays available via `kata-fc` for the fastest-cold-start tier (e.g., free-tier anonymous trials).

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
