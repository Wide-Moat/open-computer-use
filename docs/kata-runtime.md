<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# Kata Containers runtime (containerd 2.x)

This guide is the runbook for deploying `computer-use-server` on Kubernetes with
**[Kata Containers](https://katacontainers.io/)** as the inner Docker-in-Docker
(DinD) runtime. It covers why Kata, how to install it, how to configure the Helm
chart, and how to verify and troubleshoot the result.

For the chart reference in general, see [`kubernetes.md`](kubernetes.md) and the
[chart README](../helm/computer-use-server/README.md).

---

## Why Kata

Kata Containers is the supported DinD runtime for the Helm chart. It runs each
pod inside a lightweight VM (a *microVM*) with its own guest kernel, works on
**containerd 2.x** — the runtime that ships with current Kubernetes
distributions (RKE2 / k3s / kubeadm ≥ 1.34) — and gives **hypervisor-grade
isolation**. The cost is a slower cold start and a fixed per-pod memory overhead
(see [Tradeoffs](#tradeoffs)).

---

## Prerequisites

- A Kubernetes cluster on **containerd 2.x**.
- Nodes that can run a hypervisor: **nested virtualization or bare metal** with
  `/dev/kvm` available. Check with `ls -l /dev/kvm` on a node.
- `helm` ≥ 3.14.
- The target namespace must allow privileged pods (Kata DinD runs privileged —
  see [why](#step-2--configure-the-helm-chart)). Pod Security Admission `enforce`
  baseline must be `privileged` for that namespace.

---

## Step 1 — Install kata-deploy

[`kata-deploy`](https://github.com/kata-containers/kata-containers/tree/main/tools/packaging/kata-deploy)
is the official installer. It runs a DaemonSet that drops the Kata binaries and
containerd shim onto each node and registers the `RuntimeClass` objects.

```bash
helm install kata-deploy \
  oci://ghcr.io/kata-containers/kata-deploy-charts/kata-deploy \
  --version 3.30.0 \
  --namespace kube-system \
  --set env.shims=qemu \
  --set env.defaultShim=qemu \
  --set env.createDefaultRuntimeClass=false
```

- `env.shims=qemu` installs only the QEMU shim — the one this guide uses. Add
  others (`fc`, `clh`) only if you need them.
- `createDefaultRuntimeClass=false` keeps `runc` as the cluster default — Kata
  is opt-in per workload, not cluster-wide.

Verify the RuntimeClass landed:

```bash
kubectl get runtimeclass kata-qemu
# NAME        HANDLER
# kata-qemu   kata-qemu
```

### Optional — a "heavy" RuntimeClass for large guests

The Computer Use workspace can need a multi-GiB guest. RuntimeClass `overhead`
is fixed per class, so for large guests create a dedicated class:

```yaml
apiVersion: node.k8s.io/v1
kind: RuntimeClass
metadata:
  name: kata-qemu-heavy
handler: kata-qemu
overhead:
  podFixed:
    memory: "350Mi"
    cpu: "250m"
scheduling:
  nodeSelector:
    katacontainers.io/kata-runtime: "true"
```

The **guest memory** itself is set per-pod via annotations, not the RuntimeClass.
Add them under `orchestrator.podAnnotations` (or `podAnnotations`) in the chart:

```yaml
podAnnotations:
  io.katacontainers.config.hypervisor.default_memory: "8192"     # MiB
  io.katacontainers.config.hypervisor.default_maxmemory: "16384"
  io.katacontainers.config.hypervisor.default_vcpus: "4"
```

For these annotations to be honored, kata-deploy must allow them — pass
`--set 'env.allowedHypervisorAnnotations=default_memory default_maxmemory default_vcpus'`
at install time.

---

## Step 2 — Configure the Helm chart

The chart defaults already target Kata — the keys below are the chart defaults,
shown here so you understand what each one does. A ready-to-edit values file is
at [`examples/helm/standalone/values.yaml`](../examples/helm/standalone/values.yaml).

```yaml
orchestrator:
  runtimeClassName: kata-qemu          # or kata-qemu-heavy

dind:
  privileged: true                     # REQUIRED — see below
  storageDriver: fuse-overlayfs        # overlay2 fails on the Kata guest root
  kataInit:
    enabled: true                      # runs the chart-managed guest init wrapper

persistence:
  varLibDocker:
    persistentVolume:
      enabled: true                    # Block PVC — preserves xattrs
      size: 50Gi
      storageClass: longhorn           # must provision Block volumes
```

Why each setting:

- **`dind.privileged: true`** — `dockerd` needs `CAP_NET_ADMIN`/`CAP_NET_RAW` to
  build its iptables NAT chain. Without it dockerd fails with
  `iptables: Could not fetch rule set generation id: Permission denied`.
  **This is safe under Kata** — the capabilities are confined to the microVM and
  cannot reach the host kernel.
- **`dind.storageDriver: fuse-overlayfs`** — `overlay2` cannot mount on the Kata
  virtio-fs guest root
  ([kata-containers#1888](https://github.com/kata-containers/kata-containers/issues/1888)).
  `fuse-overlayfs` is a userspace overlay filesystem with full xattr support.
- **`dind.kataInit.enabled: true`** — runs the chart-managed entrypoint wrapper
  ([see below](#what-the-katainit-wrapper-does)).
- **Block PVC for `/var/lib/docker`** — the Kata virtio-fs root drops
  `security.capability` xattrs (CVE-2021-20263), which breaks binaries that rely
  on file capabilities (e.g. GStreamer in the workspace image). A **Block-mode**
  PVC arrives in the guest as a raw `virtio-blk` device; the init wrapper formats
  it `ext4` and mounts it, and ext4 preserves xattrs.

Install:

```bash
kubectl create namespace open-computer-use
kubectl label namespace open-computer-use \
  pod-security.kubernetes.io/enforce=privileged --overwrite

helm install ocu helm/computer-use-server \
  -n open-computer-use \
  -f examples/helm/standalone/values.yaml
```

---

## What the `kataInit` wrapper does

When `dind.kataInit.enabled: true`, the dind container's entrypoint is a
chart-managed script (rendered into a ConfigMap, see
`templates/configmap-dind-init.yaml`). Before `exec`-ing `dockerd` it runs four
idempotent, self-detecting steps:

1. **Install `fuse-overlayfs`** — `apk add --no-cache fuse-overlayfs` if it is
   not already present. Add more packages via `dind.kataInit.extraPackages`.
2. **Create `/dev/fuse`** — the Kata guest kernel has `fuse` compiled in but no
   device node; `mknod /dev/fuse c 10 229`.
3. **Format + mount the Block PVC** — if `persistence.varLibDocker.persistentVolume`
   is enabled, `mkfs.ext4` the raw device once (skipped if already formatted),
   then mount it at `/var/lib/docker`.
4. **cgroup-v2 PID-1 evacuation** — the Kata guest's systemd leaves PID 1 in a
   domain-threaded root cgroup, which blocks nested `runc`
   (`cannot enter cgroupv2 ... with domain controllers`). The wrapper moves
   processes into a child cgroup and republishes controllers at the root
   ([docker-library/docker#308](https://github.com/docker-library/docker/issues/308)).

Every step no-ops cleanly on an environment that does not need it.

### Alternative — a pre-baked custom image

If you prefer not to `apk add` at container start (faster cold start, air-gapped
clusters), build a custom dind image and point `dind.image` at it:

```dockerfile
FROM docker:27-dind
RUN apk add --no-cache fuse-overlayfs
```

You can still keep `dind.kataInit.enabled: true` — step 1 becomes a no-op while
steps 2–4 still run. Or disable `kataInit` entirely and bake the init logic into
your image's own entrypoint.

---

## Step 3 — Verify

```bash
# RuntimeClass is registered
kubectl get runtimeclass kata-qemu

# The pod is scheduled with the Kata RuntimeClass
kubectl -n open-computer-use get pod -l app.kubernetes.io/name=computer-use-server \
  -o jsonpath='{.items[0].spec.runtimeClassName}'   # => kata-qemu

# dockerd is healthy and using fuse-overlayfs
POD=$(kubectl -n open-computer-use get pod -l app.kubernetes.io/name=computer-use-server -o name)
kubectl -n open-computer-use exec "$POD" -c dind -- docker info | grep "Storage Driver"
#   Storage Driver: fuse-overlayfs

# /dev/fuse exists and /var/lib/docker is the ext4 Block volume
kubectl -n open-computer-use exec "$POD" -c dind -- sh -c 'ls -l /dev/fuse; mount | grep /var/lib/docker'

# Orchestrator health
helm test ocu -n open-computer-use
```

Finally, open a chat and confirm a workspace container spawns and tool calls
succeed end to end.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `dockerd: iptables: Could not fetch rule set generation id: Permission denied` | dind not privileged | set `dind.privileged: true` |
| `failed to mount overlay: operation not permitted` | `overlay2` on the Kata virtio-fs root ([kata#1888](https://github.com/kata-containers/kata-containers/issues/1888)) | set `dind.storageDriver: fuse-overlayfs` + `dind.kataInit.enabled: true` |
| `runc ... cannot enter cgroupv2 ... with domain controllers` | Kata guest PID-1 domain-threaded cgroup | `dind.kataInit.enabled: true` runs the cgroup shim |
| Workspace binaries fail / missing file capabilities (e.g. GStreamer) | virtio-fs drops `security.capability` xattrs (CVE-2021-20263) | enable `persistence.varLibDocker.persistentVolume` (Block PVC) |
| Pod stuck `Pending`, `runtimeclass not found` | kata-deploy not installed / DaemonSet not ready on the node | check `kubectl -n kube-system get ds kata-deploy` and `kubectl get runtimeclass` |
| Pod rejected by Pod Security Admission | namespace `enforce` is not `privileged` | `kubectl label ns <ns> pod-security.kubernetes.io/enforce=privileged --overwrite` |
| `mknod`/`mkfs` errors in dind logs | wrapper running but device absent | confirm the PVC is `volumeMode: Block` and bound; check `kubectl get pvc` |

---

## Tradeoffs

Kata is the runtime the chart uses. The table puts it next to the
`runc + privileged` fallback for context — that fallback is functional but
insecure, fit for local testing only.

| Dimension | Kata-qemu (chart default) | runc + privileged (testing only) |
|---|---|---|
| Isolation | hardware VM, **separate** guest kernel | none — host kernel, escape is trivial |
| containerd 2.x | ✅ works | ✅ works |
| Cold start | slower (microVM boot, ~1–3 s) | fast |
| Storage driver | `fuse-overlayfs` (`overlay2` fails) | `overlay2` / `vfs` |
| Memory overhead | ~150–350 MiB/pod (guest kernel + hypervisor) | none |
| `privileged` needed | yes — but caps confined to the VM | yes — caps on the **host** |
| Setup complexity | medium (kata-deploy, init wrapper, Block PVC) | low |
| Production-safe | yes | **no** |

**Bottom line:** Kata is the recommended runtime — strong isolation and it works
on modern containerd 2.x. `runc + privileged` works too, but the inner daemon
shares the host kernel, so it is a local-testing escape hatch only, never
production.

## See also

- [`kubernetes.md`](kubernetes.md) — Kubernetes deployment overview
- [chart README](../helm/computer-use-server/README.md) — full values reference
- [ADR-0011](future-architecture/adr/0011-kata-as-first-class-dind-runtime.md) — the decision record
- [`examples/helm/standalone/values.yaml`](../examples/helm/standalone/values.yaml) — copy-paste config
