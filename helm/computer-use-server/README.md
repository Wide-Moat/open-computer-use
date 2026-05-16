# computer-use-server Helm chart

Deploys the [open-computer-use](https://github.com/Wide-Moat/open-computer-use) orchestrator on Kubernetes. The pod runs the FastAPI MCP server, an inner Docker daemon (DinD), and an optional cleanup sidecar. Disposable workspace containers are spawned by the inner daemon — the same architecture as the Docker Compose stack, lifted onto Kubernetes via [Sysbox](https://github.com/nestybox/sysbox).

Open WebUI is **not** packaged here. It has its own [official chart](https://github.com/open-webui/helm-charts) and most users already run it. See [`examples/helm/with-open-webui/`](../../examples/helm/with-open-webui/README.md) for the integration walkthrough.

---

## Prerequisites

1. **Kubernetes ≥ 1.27** with a working CNI and a default StorageClass that supports `ReadWriteOnce`.
2. **[Sysbox](https://github.com/nestybox/sysbox)** installed on every node that may schedule the orchestrator pod, with a matching `RuntimeClass` (default name: `sysbox-runc`). Sysbox lets the inner Docker daemon run **without** `privileged: true`. The chart still supports stock runc, but only as an explicit, documented downgrade.
3. **`helm` ≥ 3.14** (Helm 4 also works).
4. The orchestrator and workspace images published to a registry the cluster can pull from.

> **Why Sysbox?** The orchestrator needs to spawn Docker containers inside its own pod (matches the existing app code, no rewrite). Sysbox is the only mainstream runtime that supports `dockerd` inside an unprivileged container. Without it, you fall back to `privileged: true`, which gives the inner daemon host-kernel access and trivially breaks pod isolation. Don't run that in production.

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
| `orchestrator.runtimeClassName` | `sysbox-runc` | set to `""` to drop to stock runc + privileged (UNSUPPORTED) |
| `orchestrator.replicas` | `1` | **must stay 1** — single owner of inner dockerd and RWO PVCs |
| `orchestrator.env.PUBLIC_BASE_URL` | `""` | **REQUIRED** — browser-facing URL (no trailing slash). Without it, chat file previews 404. |
| `orchestrator.extraEnv` / `envFrom` | `[]` | inject `ANTHROPIC_*`, `VISION_*`, etc. from existing Secrets / ConfigMaps |
| `secrets.create` | `true` | renders a Secret from `secrets.mcpApiKey` etc. (handy, bad for GitOps) |
| `secrets.existingSecret` | `""` | when set, ignores `secrets.create` and uses your Secret via `envFrom`. Must include `MCP_API_KEY`. |
| `secrets.mcpApiKey` | `""` | **REQUIRED** unless `existingSecret` is set |
| `persistence.userData.size` | `20Gi` | `/tmp/computer-use-data` — uploads + outputs |
| `persistence.data.size` | `5Gi` | `/data` — long-lived orchestrator state |
| `persistence.skillsCache.size` | `2Gi` | `/data/skills-cache` |
| `persistence.varLibDocker.sizeLimit` | `50Gi` | emptyDir for the inner `/var/lib/docker`. **Never** make this a PVC — see [nestybox/sysbox#406](https://github.com/nestybox/sysbox/issues/406). |
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

## Sysbox handling

The chart couples `runtimeClassName` and `dind.securityContext.privileged`:

| `orchestrator.runtimeClassName` | `dind` runs as | Supported? |
|---|---|---|
| `sysbox-runc` (default) | `privileged: false` | ✅ recommended |
| (other RuntimeClass) | `privileged: false` | ⚠️ only if that runtime supports unprivileged DinD |
| `""` (empty) | `privileged: true` on stock runc | ❌ unsupported, container-escape risk |

When `runtimeClassName` is empty the chart prints a loud warning in `NOTES.txt` after install. The `privileged: true` flip is purely a "make it functional for testing" escape hatch — don't ship a production cluster that way.

---

## Troubleshooting

**`unlinkat /etc/ld.so.cache: operation not permitted` in the dind container.**
Sysbox issue #406 — you're sharing `/var/lib/docker` somewhere you shouldn't. Confirm `var-lib-docker` is its own `emptyDir`, mounted **only** into the `dind` container. Don't replace it with a PVC and don't bind it into the orchestrator.

**Chat file preview links 404 from the browser.**
`PUBLIC_BASE_URL` is wrong. It must be the URL the user's browser sees (same host as the Ingress), not the in-cluster service DNS. Update `orchestrator.env.PUBLIC_BASE_URL` and `helm upgrade`.

**`pod has unbound immediate PersistentVolumeClaims`.**
Your StorageClass doesn't support `ReadWriteOnce` or there is no default class. Set `persistence.<vol>.storageClass` explicitly or pre-create PVCs and reference them via `persistence.<vol>.existingClaim`.

**Cleanup sidecar logs `Cannot connect to the Docker daemon`.**
The dind container hasn't finished starting yet, or the shared `dind-socket` volume isn't mounted. Wait 30s — the cron only runs every 2 hours and on schedule, so brief startup gaps are harmless.

**Workspace containers can't pull the workspace image.**
The inner dockerd does the pull, not Kubernetes. The image must be reachable from inside the pod (public registry, or `imagePullSecrets` won't help — they apply only to outer kubelet pulls). For private registries, configure inner-dockerd auth via a custom dind image or `dockerd --insecure-registry` arg.

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
