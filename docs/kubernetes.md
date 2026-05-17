# Kubernetes deployment

The Docker Compose stack in `docker-compose.yml` / `docker-compose.webui.yml` ships as a Helm chart in [`helm/computer-use-server/`](../helm/computer-use-server/). This is the recommended way to run open-computer-use on Kubernetes.

## Quick start

```bash
# 1. Install Sysbox on your nodes once (https://github.com/nestybox/sysbox).
#    Confirm the RuntimeClass exists:
kubectl get runtimeclass sysbox-runc

# 2. Add the chart repo (published from the gh-pages branch on every release tag):
helm repo add open-computer-use https://wide-moat.github.io/open-computer-use
helm repo update

# 3. Install:
helm install ocu open-computer-use/computer-use-server \
  --namespace open-computer-use --create-namespace \
  --values examples/helm/standalone/values.yaml
```

Or, against a git checkout for unreleased changes:

```bash
helm install ocu helm/computer-use-server \
  --namespace open-computer-use --create-namespace \
  --values examples/helm/standalone/values.yaml
```

The chart README at [`helm/computer-use-server/README.md`](../helm/computer-use-server/README.md) is the authoritative reference. This page is the navigation.

## Examples

- **[`examples/helm/standalone/`](../examples/helm/standalone/)** — minimum-viable config (just the orchestrator). Closest to `docker-compose.yml`.
- **[`examples/helm/with-open-webui/`](../examples/helm/with-open-webui/)** — orchestrator + Open WebUI via the upstream Open WebUI Helm chart. Closest to `docker-compose.yml` + `docker-compose.webui.yml` together.

## Architecture

The orchestrator pod has three containers:

```text
┌───────────────────────────────── Pod (runtimeClassName: sysbox-runc) ──────────┐
│                                                                                 │
│  ┌─────────────────┐   ┌─────────────────┐   ┌──────────────────────────────┐  │
│  │  orchestrator   │──►│   inner dockerd │◄──│  cleanup sidecar (cron)      │  │
│  │  FastAPI :8081  │   │  spawns chat-*  │   │  reaps stale chat-* + data   │  │
│  └─────────────────┘   └─────────────────┘   └──────────────────────────────┘  │
│        │ /var/run/docker.sock  ▲       ▲                  ▲                     │
│        └──────── shared emptyDir (dind-socket) ───────────┘                     │
│                                                                                 │
│  Volumes:                                                                       │
│   - emptyDir  dind-socket    → /var/run on all three containers                │
│   - emptyDir  var-lib-docker → /var/lib/docker on dind ONLY (sysbox#406)       │
│   - PVC       user-data      → /tmp/computer-use-data (RWO)                    │
│   - PVC       data           → /data (RWO)                                     │
│   - PVC       skills-cache   → /data/skills-cache (RWO)                        │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**Why DinD-on-Sysbox instead of native k8s Pods?**
The existing orchestrator code talks to a Docker socket. Lifting it onto Kubernetes via Sysbox keeps the app code unchanged. A future `K8sBackend` rewrite (drafted in [`docs/future-architecture/`](future-architecture/)) will spawn native Pods, at which point the inner dockerd disappears — but that's a separate workstream.

**Why is the orchestrator single-replica?**
It owns the inner Docker daemon and three RWO PVCs. There is no shared state between replicas and no leader-election. The chart hard-pins `replicas: 1` in `values.schema.json`.

## Prerequisites checklist

- Kubernetes ≥ 1.27
- StorageClass that supports `ReadWriteOnce` and is the cluster default (or pass `persistence.*.storageClass` explicitly)
- Sysbox installed on candidate nodes + matching `RuntimeClass`
- Ingress controller (nginx-ingress, Traefik, etc.) if you set `ingress.enabled=true`
- DNS + TLS cert for the public hostname referenced by `PUBLIC_BASE_URL`

## See also

- [`helm/computer-use-server/README.md`](../helm/computer-use-server/README.md) — chart reference and troubleshooting
- [`docs/future-architecture/`](future-architecture/) — draft of the future native-Pod backend (not implemented)
- [Sysbox docs](https://github.com/nestybox/sysbox/blob/master/docs/quickstart/install-k8s.md) — install Sysbox on a k8s cluster
