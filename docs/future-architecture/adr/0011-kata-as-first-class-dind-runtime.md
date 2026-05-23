<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# ADR-0011 — Kata Containers as a first-class DinD runtime

- **Status:** Accepted
- **Date:** 2026-05-20
- **Supersedes:** the runtime phasing in ADR-0004 *Consequences* ("Phase 9 adds `kata-fc` / `kata-ch`")
- **Issue:** [#116](https://github.com/Wide-Moat/open-computer-use/issues/116)

## Context

The `computer-use-server` Helm chart shipped with [Sysbox](https://github.com/nestybox/sysbox)
as its default — and only documented — DinD runtime. Sysbox lets the inner
`dockerd` run unprivileged, which is why the chart couples
`runtimeClassName` to `dind.securityContext.privileged`.

Sysbox no longer works on **containerd 2.x**, which ships with current
Kubernetes distributions (RKE2 / k3s / kubeadm ≥ 1.34). Sysbox fails there with
mount-permission errors. Docker acquired Nestybox; public Sysbox releases are
frozen at containerd 1.x compatibility and there is no upstream fix on the
horizon. Any operator on a modern cluster cannot deploy the chart at all.

ADR-0004 anticipated Kata, but only as a *Phase 9* item for the future native
backend. The Sysbox EOL makes that timeline untenable: Kata is needed **now**,
in the current DinD-based chart, just to keep the chart installable.

## Decision

Make **Kata Containers (`kata-qemu`)** a first-class, fully documented runtime
for the current Helm chart, alongside Sysbox.

Concretely:

1. **`dind.privileged`** — a new explicit override (default `null` = legacy
   auto-derivation). Kata requires `privileged: true` because `dockerd` needs
   `CAP_NET_ADMIN`/`CAP_NET_RAW` for the iptables NAT chain. This is safe under
   Kata — capabilities are confined to the microVM.
2. **`dind.kataInit`** — a chart-templated entrypoint wrapper (shipped in a
   ConfigMap, **not** a custom published image) that prepares the Kata guest:
   installs `fuse-overlayfs`, creates `/dev/fuse`, formats/mounts the Block
   PVC, and runs the cgroup-v2 PID-1 evacuation shim.
3. **`persistence.varLibDocker.persistentVolume`** — optional Block-mode PVC for
   `/var/lib/docker`. Under Kata this is required for workloads needing
   `security.capability` xattrs (the virtio-fs root drops them — CVE-2021-20263).
4. All Kata machinery is gated behind `dind.kataInit.enabled: false` so existing
   Sysbox installs render byte-identically.

## Rationale

- **Chart-templated wrapper over a custom image.** A published
  `docker:dind + fuse-overlayfs` image would burden maintainers with a build
  pipeline, CVE patching, and multi-arch releases. `fuse-overlayfs` is a single
  `apk add` performed idempotently at container start; the wrapper lives in the
  chart, is fully visible in `helm template`, and is testable in CI without a
  cluster. A pre-baked image remains documented as an optional alternative.
- **`fuse-overlayfs`, not `overlay2`.** `overlay2` cannot mount on the Kata
  virtio-fs guest root ([kata-containers#1888](https://github.com/kata-containers/kata-containers/issues/1888)).
  `fuse-overlayfs` is a userspace filesystem with full xattr support.
- **Block PVC for `/var/lib/docker`.** A filesystem PVC reaches the guest over
  virtio-fs and drops xattrs; a Block PVC arrives as virtio-blk, so a real ext4
  filesystem inside the guest preserves them.
- **Backward compatibility is non-negotiable.** Sysbox users must see no
  behavior change — enforced by `null` defaults and a CI render regression check.

## Consequences

- The chart now documents two runtimes; `docs/kata-runtime.md` is the Kata
  runbook (install kata-deploy → configure → deploy → verify → troubleshoot).
- Operators on containerd 2.x have a supported path; Sysbox remains supported
  for containerd 1.x clusters.
- The vendored-chart patches that yambr ran in production are upstreamed, so
  that fork can be retired.
- This is validated in a production deployment but **cannot** be exercised in
  OCU CI (no Kata-capable runners); CI covers chart rendering only.

## Alternatives

- **Document Kata without chart changes** — rejected; operators would still
  hand-patch the `dindPrivileged` helper and hand-roll the guest init.
- **Ship a custom dind image** — rejected as the default (maintenance burden);
  kept as a documented opt-in alternative.
- **Wait for the Phase 9 native-Pod backend** — rejected; leaves every
  containerd 2.x cluster unable to install the chart in the meantime.
