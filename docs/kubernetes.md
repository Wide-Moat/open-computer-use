# Kubernetes deployment

The Docker Compose stack in `docker-compose.yml` / `docker-compose.webui.yml` ships as a Helm chart in [`helm/computer-use-server/`](../helm/computer-use-server/). This is the recommended way to run open-computer-use on Kubernetes.

## Runtime

The orchestrator runs an inner Docker daemon, which needs a DinD-capable runtime
on the node. The chart uses **[Kata Containers](https://katacontainers.io/)** —
it works on modern containerd 2.x clusters (RKE2 / k3s / kubeadm ≥ 1.34) and
isolates the pod in a microVM. Install `kata-deploy` and follow the
[Kata runtime guide](kata-runtime.md) before installing the chart.

## Quick start

```bash
# 1. Install Kata Containers (kata-deploy) on the nodes once — see
#    docs/kata-runtime.md. Confirm the RuntimeClass exists:
kubectl get runtimeclass kata-qemu

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
┌──────────────────────────── Pod (runtimeClassName: kata-qemu) ──────────────────┐
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
│   - Block PVC var-lib-docker → /var/lib/docker on dind ONLY (xattr-safe)       │
│   - PVC       user-data      → /tmp/computer-use-data (RWO)                    │
│   - PVC       data           → /data (RWO)                                     │
│   - PVC       skills-cache   → /data/skills-cache (RWO)                        │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**Why DinD instead of native k8s Pods?**
The existing orchestrator code talks to a Docker socket. Lifting it onto Kubernetes via Kata Containers keeps the app code unchanged. A future `K8sBackend` rewrite (drafted in [`docs/future-architecture/`](future-architecture/)) will spawn native Pods, at which point the inner dockerd disappears — but that's a separate workstream.

**Why is the orchestrator single-replica?**
It owns the inner Docker daemon and three RWO PVCs. There is no shared state between replicas and no leader-election. The chart hard-pins `replicas: 1` in `values.schema.json`.

## Prerequisites checklist

- Kubernetes ≥ 1.27
- StorageClass that supports `ReadWriteOnce` and is the cluster default (or pass `persistence.*.storageClass` explicitly), plus one that provisions Block volumes for `/var/lib/docker`
- Kata Containers installed on candidate nodes + the `kata-qemu` `RuntimeClass` — see [`kata-runtime.md`](kata-runtime.md)
- Ingress controller (nginx-ingress, Traefik, etc.) if you set `ingress.enabled=true`
- DNS + TLS cert for the public hostname referenced by `PUBLIC_BASE_URL`

## See also

- [`helm/computer-use-server/README.md`](../helm/computer-use-server/README.md) — chart reference and troubleshooting
- [`docs/kata-runtime.md`](kata-runtime.md) — Kata Containers runtime guide (install, configure, verify, troubleshoot)
- [`docs/future-architecture/`](future-architecture/) — draft of the future native-Pod backend (not implemented)
