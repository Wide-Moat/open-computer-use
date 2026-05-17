# 10 — sysbox (default L2 for internal/trusted tier)

> Source: [`references/sysbox/`](../../../references/sysbox/). User-namespace + procfs/sysfs emulation.
> Already used by our current Helm chart (`RuntimeClass: sysbox-runc`). [Phase 5](../roadmap.md#phase-5--helm-hardening--kubernetesprovider) formalizes it as the default L2.

## 1. Installation — `sysbox-deploy-k8s` DaemonSet

- **Where.** `sysbox-k8s-manifests/sysbox-install.yaml:42-181`. Image `registry.nestybox.com/nestybox/sysbox-deploy-k8s:v0.7.0`.
- **What.** Auto-installs binaries (`sysbox-runc`, `sysbox-fs`, `sysbox-mgr`) on labeled nodes; configures containerd/CRI-O; registers RuntimeClass. Tolerates `sysbox-runtime: not-running` during install; relabels `sysbox-runtime: running` post-success. Rolling update.
- **Why for us.** Phase 5 — direct analog to [kata-deploy](./01-kata-containers.md#5-kata-deploy-daemonset--installcleanup-probes-node-affinity). Bundle into Helm dependencies.
- **Footgun.** Requires privileged init container (unavoidable — patches systemd units and kernel modules). Pre-2.0.5 containerd → falls back to CRI-O; mandate **containerd v2.0.5+** to skip that path.

## 2. RuntimeClass — `sysbox-runc`

- **Where.** `sysbox-install.yaml:173-180`.
- **What.** `node.k8s.io/v1` RuntimeClass; handler = `sysbox-runc`. `nodeSelector: sysbox-runtime: running` pins pods to installed nodes.
- **K8s ≥ v1.30 + containerd ≥ v2.0.5.** Supports formal user-namespace via `pod.spec.hostUsers: false` (cleaner than CRI-O's annotation `io.kubernetes.cri-o.userns-mode: "auto:size=65536"`).
- **Why for us.** Phase 5 default template runtime.
- **Footgun.** Pre-1.30 clusters → fall back to CRI-O annotation; document separately.

## 3. What sysbox adds vs runc

- **Where.** `README.md:19-62`, `design.md:1-45`, `dind.md:23-129`.
- **Key gains.**
  - **User-namespace isolation** — root inside container = `nobody:nogroup` on host.
  - **procfs / sysfs virtualization** — FUSE-mounted by `sysbox-fs`; hides host resources; container-local sysctl.
  - **Immutable rootfs mounts** — prevents mount-escape tricks.
  - **DinD without `--privileged`** — inner Docker daemon runs unprivileged.
- **For us.** Phase 5 internal tier — VM-class isolation without VM cost, ~50 ms cold start, ~5 MB RAM overhead.
- **NOT enough alone for untrusted.** Kernel CVEs still apply → pair with kata-ch (Phase 9).

## 4. Component triad — `sysbox-runc`, `sysbox-fs`, `sysbox-mgr`

- **Where.** `design.md:13-46`.
- **What.**
  - **`sysbox-runc`** — OCI runtime fork; per create/start/delete; gRPC client to sysbox-mgr.
  - **`sysbox-fs`** — FUSE daemon; emulates `/proc`, `/sys`; resident for container lifetime.
  - **`sysbox-mgr`** — stateful daemon; allocates per-container UID ranges from `/etc/subuid`, `/etc/subgid`; coordinates cgroup limits.
- **For us.** Monitoring must track all three. gRPC failures between them are the failure mode. DaemonSet handles restart in k8s; on bare metal use `Restart=always` + throttling.

## 5. systemd-in-container — works out of the box

- **Where.** `design.md:198-225`, `dind.md:103-129`.
- **What.** sysbox detects PID 1 = systemd and: allows `/proc/sys` writes (normally user-ns-blocked), auto-mounts cgroup v2, whitelists mount/umount. `command: ["/sbin/init"]` just works.
- **For us.** Phase 5 — relevant if a template ever bundles multiple services. Use Nestybox-provided Ubuntu Jammy/Focal systemd-docker images as base.

## 6. License — Apache 2.0 (CE only)

- **Where.** `README.md:198-211`, `install-k8s.md:154-297` (EE marked DEPRECATED).
- **What.** **Sysbox CE** = Apache 2.0. **Sysbox-EE** deprecated since May 2022 (Docker acquired Nestybox). EE distribution stopped.
- **For us.** Compatible with our license policy ([ADR-0006](../adr/0006-no-agpl-no-bsl-dependencies.md)). Support is community / GitHub issues / Slack.

## 7. Known CVEs (kernel-shared caveats)

- **Where.** `security-cve.md:1-169`.
- **Critical four.**
  | CVE | Affects | Fix |
  |---|---|---|
  | CVE-2022-0185 (user-ns escape) | Kernel < 5.16 | Kernel ≥ 5.16 |
  | CVE-2022-0847 (Dirty Pipe) | Kernel < 5.16.11 / 5.15.25 / 5.10.102 | Patched kernel |
  | CVE-2022-0811 (CRI-O sysctl) | `sysbox-deploy-k8s` < v0.5.1 | DaemonSet ≥ v0.5.1 |
  | CVE-2024-21626 (runc fd leak) | **NOT affected** — sysbox has user-ns fallback | — |
- **For us.** Phase 5 — gate sysbox templates on `kernel-version: >=5.16` node label. Annual CVE audit.
- **Why this is acceptable.** sysbox is OS-virtualization, not VM-isolation. We accept the trade-off for **internal trusted** tier; eliminate it via kata-ch for **untrusted** (Phase 9).

## 8. Containerd vs CRI-O integration

- **Where.** `install-k8s.md:90-108`.
- **What.** K8s ≥ 1.30 + containerd ≥ 2.0.5 → OCI runtime spec, drops `sysbox-runc` into `/usr/bin/`, updates `config.toml`. Older → falls back to **customized CRI-O** (heavier, requires kubelet restart).
- **For us.** **Mandate K8s ≥ 1.30 + containerd ≥ 2.0.5** in Helm pre-install hook. Hard requirement, not soft recommendation.

## 9. Performance

- **Where.** `README.md:324-340`, `dind.md:199-204`.
- **What.** Cold start ~50 ms (vs runc 30 ms). RAM overhead ~5 MB / pod (vs runc 2 MB, gVisor 15–25 MB). CPU overhead negligible. Inner-container network has slight overhead due to extra bridge.
- **For us.** Phase 5 SLO budgets — 50 ms pod-spawn is fine. 5 MB × 1000 pods = 5 GB host RAM (acceptable).

## 10. Operator footguns

| Don't | Why | Do |
|---|---|---|
| Mount host `/var/lib/docker` into container | Breaks isolation; concurrent cache violations | Let inner Docker manage its own |
| Configure inner Docker with userns-remap | Not supported; redundant with sysbox user-ns | Leave default |
| Share inner Docker data-root across containers | Lock contention → failures | sysbox-mgr errors out anyway |
| Skip `hostUsers: false` (or CRI-O annotation) | Pod runs root w/o user-ns — half the security gone | Always set it |
| Run on kernel < 5.4 | Sysbox unsupported | Kernel ≥ 5.16 (for CVEs above) |

## Adoption checklist for Phase 5

1. Add `sysbox-deploy-k8s` DaemonSet to Helm chart (or document as prereq).
2. Helm pre-install hook: validate `kubectl version ≥ 1.30` + containerd ≥ 2.0.5 + kernel ≥ 5.16 on a sample of nodes.
3. Default template: `runtimeClassName: sysbox-runc`, `hostUsers: false`.
4. Document footguns in `values.yaml` comments.
5. Plan kernel ≥ 5.16 enforcement via node label + scheduler taint (Phase 5 acceptance).
6. Phase 9: layer kata-ch beside sysbox for untrusted tier.
