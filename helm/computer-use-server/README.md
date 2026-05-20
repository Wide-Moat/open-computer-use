# computer-use-server Helm chart

Deploys the [open-computer-use](https://github.com/Wide-Moat/open-computer-use) orchestrator on Kubernetes. The pod runs the FastAPI MCP server, an inner Docker daemon (DinD), and an optional cleanup sidecar. Disposable workspace containers are spawned by the inner daemon — the same architecture as the Docker Compose stack, lifted onto Kubernetes via **[Kata Containers](https://katacontainers.io/)** (microVM isolation, works on containerd 2.x — see [`docs/kata-runtime.md`](../../docs/kata-runtime.md)).

Open WebUI is **not** packaged here. It has its own [official chart](https://github.com/open-webui/helm-charts) and most users already run it. See [`examples/helm/with-open-webui/`](../../examples/helm/with-open-webui/README.md) for the integration walkthrough.

---

## Prerequisites

1. **Kubernetes ≥ 1.27** with a working CNI and a default StorageClass that supports `ReadWriteOnce`, plus a StorageClass that provisions Block volumes (for `/var/lib/docker`).
2. **[Kata Containers](https://katacontainers.io/)** installed on every node that may schedule the orchestrator pod, with the `kata-qemu` `RuntimeClass`. Install `kata-deploy` and follow [`docs/kata-runtime.md`](../../docs/kata-runtime.md). The target namespace must allow privileged pods (PSA `enforce: privileged`).
3. **`helm` ≥ 3.14** (Helm 4 also works).
4. The orchestrator and workspace images published to a registry the cluster can pull from.

> **Why Kata?** The orchestrator spawns Docker containers inside its own pod (matches the existing app code, no rewrite). Stock `runc` can only do that with `privileged: true`, which gives the inner daemon host-kernel access and trivially breaks isolation — never run that in production. Kata isolates the whole pod in a microVM, so the inner daemon's privileges cannot reach the host kernel, and it works on containerd 2.x (RKE2 / k3s / kubeadm ≥ 1.34). See the [runtime comparison](../../docs/kata-runtime.md#tradeoffs).

---

## Install

### From the public Helm repo (after the first release tag is pushed)

```bash
helm repo add open-computer-use https://wide-moat.github.io/open-computer-use
helm repo update
helm install ocu open-computer-use/computer-use-server \
  --namespace open-computer-use --create-namespace \
  -f my-values.yaml
```

### From the OCI registry (any `v*` tag, including release candidates)

Every `v*` git tag — stable and pre-release — pushes the chart to `oci://ghcr.io/wide-moat/charts/computer-use-server`. Use this path to install an `-rc.N` build for testing without contaminating users on the stable `helm repo`.

The chart and the Docker images use different version strings:

- **`APP_VERSION`** (Docker image tags + chart `appVersion`): full 4-segment app version, e.g. `0.9.2.5-rc.1`. Comes directly from the git tag.
- **`CHART_VERSION`** (Helm chart `version`, what `helm install --version` resolves): strict 3-segment SemVer, e.g. `0.9.2-rc.1`. The 4th segment of the app version is dropped because Helm rejects 4-segment chart versions.

```bash
APP_VERSION=0.9.2.5-rc.1     # Docker image tag
CHART_VERSION=0.9.2-rc.1     # Helm chart version (4th segment dropped)

helm install ocu-rc oci://ghcr.io/wide-moat/charts/computer-use-server \
  --version "$CHART_VERSION" \
  --namespace open-computer-use --create-namespace \
  -f my-values.yaml \
  --set image.tag="$APP_VERSION" \
  --set workspaceImage.tag="$APP_VERSION" \
  --set cleanup.image.tag="$APP_VERSION"
```

The `release-chart.yml` workflow prints both values in the Actions Job Summary on every tag push, so you don't have to derive them yourself.

Stable users running `helm repo add open-computer-use https://wide-moat.github.io/...` are unaffected — Helm excludes SemVer pre-releases from `helm install` resolution unless `--devel` or an explicit `--version X.Y.Z-rc.N` is passed.

### From a git checkout (development / unreleased changes)

```bash
helm install ocu helm/computer-use-server \
  --namespace open-computer-use --create-namespace \
  --set secrets.mcpApiKey=$(openssl rand -hex 32) \
  --set orchestrator.env.PUBLIC_BASE_URL=https://orchestrator.example.com \
  --set ingress.enabled=true \
  --set ingress.hosts[0].host=orchestrator.example.com \
  --set ingress.hosts[0].paths[0].path=/ \
  --set ingress.hosts[0].paths[0].pathType=Prefix
```

See [`examples/helm/standalone/values.yaml`](../../examples/helm/standalone/values.yaml) for a values-file version.

After install:

```bash
helm test ocu -n open-computer-use   # runs a Pod that curls /health
kubectl -n open-computer-use logs deployment/ocu-computer-use-server -c orchestrator
```

---

## Values reference

The full schema lives in [`values.yaml`](values.yaml). The knobs you most often need:

| Key | Default | Notes |
|---|---|---|
| `image.repository` | `ghcr.io/wide-moat/open-computer-use-server` | orchestrator image |
| `image.tag` | `.Chart.AppVersion` | override if pinning |
| `workspaceImage.repository` | `ghcr.io/wide-moat/open-computer-use` | passed as `DOCKER_IMAGE` to the orchestrator; the inner dockerd pulls this on first chat |
| `orchestrator.runtimeClassName` | `kata-qemu` | the Kata `RuntimeClass` (see [kata-runtime.md](../../docs/kata-runtime.md)); `""` drops to stock runc + privileged (functional but INSECURE — testing only) |
| `dind.privileged` | `true` | whether the dind container runs privileged. `true` is required for Kata (caps confined to the microVM). `null` auto-derives from `runtimeClassName`. |
| `dind.storageDriver` | `fuse-overlayfs` | dockerd storage driver. `fuse-overlayfs` is required under Kata (`overlay2` fails on the virtio-fs guest root). |
| `dind.kataInit.enabled` | `true` | runs the chart-managed Kata-guest init wrapper. See [kata-runtime.md](../../docs/kata-runtime.md). Disable only for the runc fallback. |
| `orchestrator.replicas` | `1` | **must stay 1** — single owner of inner dockerd and RWO PVCs |
| `orchestrator.env.PUBLIC_BASE_URL` | `""` | **REQUIRED** — browser-facing URL (no trailing slash). Without it, chat file previews 404. |
| `orchestrator.extraEnv` / `envFrom` | `[]` | inject `ANTHROPIC_*`, `VISION_*`, etc. from existing Secrets / ConfigMaps |
| `secrets.create` | `true` | renders a Secret from `secrets.mcpApiKey` etc. (handy, bad for GitOps) |
| `secrets.existingSecret` | `""` | when set, ignores `secrets.create` and uses your Secret via `envFrom`. Must include `MCP_API_KEY`. |
| `secrets.mcpApiKey` | `""` | **REQUIRED** unless `existingSecret` is set |
| `persistence.userData.size` | `20Gi` | `/tmp/computer-use-data` — uploads + outputs |
| `persistence.data.size` | `5Gi` | `/data` — long-lived orchestrator state |
| `persistence.skillsCache.size` | `2Gi` | `/data/skills-cache` |
| `persistence.varLibDocker.sizeLimit` | `50Gi` | emptyDir size for the inner `/var/lib/docker`, used only under the runc fallback (when `persistentVolume.enabled=false`). |
| `persistence.varLibDocker.persistentVolume.enabled` | `true` | back `/var/lib/docker` with a Block-mode PVC (required under Kata for xattr-dependent workloads). Disable only for the runc fallback. See [kata-runtime.md](../../docs/kata-runtime.md). |
| `cleanup.enabled` | `true` | runs the same crons as `docker-compose.yml` (`cron/cleanup.sh` + `cron/cleanup-quick.sh`) |
| `cleanup.containerMaxAgeHours` | `24` | stop workspace containers older than this |
| `cleanup.dataMaxAgeDays` | `7` | remove stale data dirs older than this |
| `ingress.enabled` | `false` | standard Ingress template — `className`, `annotations`, `hosts`, `tls` |
| `networkPolicy.enabled` | `false` | default-deny + allowed egress to public internet |
| `podDisruptionBudget.enabled` | `false` | irrelevant at `replicas: 1` |

---

## Postgres

The orchestrator itself does not use Postgres — only Open WebUI does. This chart intentionally does **not** bundle Postgres as a subchart, to keep `helm install` paths predictable (Helm 4 has several open bugs around `condition:` dependencies, see [helm/helm#13341](https://github.com/helm/helm/issues/13341)).

If you need Postgres for an adjacent Open WebUI deployment, install it as a separate release. Example:

```bash
helm repo add bitnami https://charts.bitnami.com/bitnami
helm install pg bitnami/postgresql \
  -n open-computer-use \
  --set auth.username=openwebui \
  --set auth.database=openwebui \
  --set auth.existingSecret=ocu-shared
```

See [`examples/helm/with-open-webui/README.md`](../../examples/helm/with-open-webui/README.md) for the full walkthrough.

---

## Bring your own Secret (GitOps mode)

Recommended for anything you check into git:

```bash
kubectl -n open-computer-use create secret generic ocu-server-creds \
  --from-literal=MCP_API_KEY=$(openssl rand -hex 32) \
  --from-literal=ANTHROPIC_AUTH_TOKEN=sk-ant-... \
  --from-literal=VISION_API_KEY=...

helm install ocu helm/computer-use-server \
  --set secrets.create=false \
  --set secrets.existingSecret=ocu-server-creds \
  --set orchestrator.env.PUBLIC_BASE_URL=https://orchestrator.example.com
```

The Secret is mounted via `envFrom` — every key becomes an env var on the orchestrator container.

---

## Runtime

The chart runs the inner Docker daemon under **Kata Containers**. The chart
defaults (`runtimeClassName: kata-qemu`, `dind.privileged: true`,
`dind.kataInit.enabled: true`, `dind.storageDriver: fuse-overlayfs`, Block-mode
PVC for `/var/lib/docker`) are all set for Kata — install `kata-deploy` and the
chart works out of the box. The full runbook — install, configure, verify,
troubleshoot — is in [`docs/kata-runtime.md`](../../docs/kata-runtime.md).

| `orchestrator.runtimeClassName` | `dind.privileged` | `dind` runs as | Use it? |
|---|---|---|---|
| `kata-qemu` (default) | `true` | `privileged: true` (caps confined to the microVM) | ✅ recommended |
| `""` (empty) | `null` (auto) ⇒ `true` | `privileged: true` on stock runc | ⚠️ functional but insecure — testing only |

`dind.privileged: true` is required for Kata — the inner `dockerd` needs
`CAP_NET_ADMIN`/`CAP_NET_RAW` for iptables NAT, and the capabilities stay
confined to the microVM. Setting `runtimeClassName: ""` drops to stock runc with
a privileged dind; this works, but the inner daemon shares the host kernel, so a
container escape is trivial. The chart prints a loud warning in `NOTES.txt`. Use
that path only for local testing — never ship a production cluster that way, and
pair it with `dind.kataInit.enabled=false` and
`persistence.varLibDocker.persistentVolume.enabled=false`.

---

## Troubleshooting

**Chat file preview links 404 from the browser.**
`PUBLIC_BASE_URL` is wrong. It must be the URL the user's browser sees (same host as the Ingress), not the in-cluster service DNS. Update `orchestrator.env.PUBLIC_BASE_URL` and `helm upgrade`.

**`pod has unbound immediate PersistentVolumeClaims`.**
Your StorageClass doesn't support `ReadWriteOnce` or there is no default class. Set `persistence.<vol>.storageClass` explicitly or pre-create PVCs and reference them via `persistence.<vol>.existingClaim`.

**Cleanup sidecar logs `Cannot connect to the Docker daemon`.**
The dind container hasn't finished starting yet, or the shared `dind-socket` volume isn't mounted. Wait 30s — the cron only runs every 2 hours and on schedule, so brief startup gaps are harmless.

**Workspace containers can't pull the workspace image.**
The inner dockerd does the pull, not Kubernetes. The image must be reachable from inside the pod (public registry, or `imagePullSecrets` won't help — they apply only to outer kubelet pulls). For private registries, configure inner-dockerd auth via a custom dind image or `dockerd --insecure-registry` arg.

**`dockerd: iptables: Could not fetch rule set generation id: Permission denied` (Kata).**
The inner dockerd is not privileged. Under Kata, set `dind.privileged: true` — it is safe because the capabilities are confined to the microVM. See [`docs/kata-runtime.md`](../../docs/kata-runtime.md#troubleshooting) for the full Kata troubleshooting table (`overlay2` mount failures, cgroup-v2 errors, xattr loss).

---

## Uninstall

```bash
helm uninstall ocu -n open-computer-use
kubectl -n open-computer-use delete pvc -l app.kubernetes.io/instance=ocu
```

PVCs are not deleted by `helm uninstall` — remove them explicitly to free the storage.

---

## License

BUSL-1.1, Copyright (c) 2025 Open Computer Use Contributors.
