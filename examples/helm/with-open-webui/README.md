# Open WebUI + computer-use-server on Kubernetes

This is the Kubernetes analog of running `docker-compose.yml` + `docker-compose.webui.yml` together. You install two Helm charts side-by-side in the same namespace and wire them through a shared Secret.

```text
┌──────────────────────── namespace: open-computer-use ──────────────────────────┐
│                                                                                 │
│  Users ── Ingress ──► Service: open-webui :3000                                │
│                              │                                                  │
│                              │ HTTP (ORCHESTRATOR_URL, MCP_API_KEY)            │
│                              ▼                                                  │
│                  Service: ocu-computer-use-server :8081                         │
│                  (Kata DinD pod, see helm/computer-use-server/README.md)         │
│                              │                                                  │
│                              ▼                                                  │
│                  StatefulSet: postgres  (Bitnami subchart, or BYO)              │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Prerequisites

The same prereqs as `standalone/`: Kata Containers on nodes (see [`docs/kata-runtime.md`](../../../docs/kata-runtime.md)), RWO + Block StorageClass, Ingress controller, DNS + TLS. Plus:

- The upstream Open WebUI Helm repo configured:
  ```bash
  helm repo add open-webui https://helm.openwebui.com/
  helm repo update
  ```

## Install steps

```bash
# 0. Create namespace
kubectl create namespace open-computer-use

# 1. Shared Secret used by both charts. MCP_API_KEY must match in both places.
kubectl -n open-computer-use create secret generic ocu-shared \
  --from-literal=MCP_API_KEY=$(openssl rand -hex 32) \
  --from-literal=POSTGRES_PASSWORD=$(openssl rand -hex 24) \
  --from-literal=WEBUI_SECRET_KEY=$(openssl rand -hex 32) \
  --from-literal=ANTHROPIC_AUTH_TOKEN=sk-ant-...  # if using Anthropic

# 2. Install Postgres as a separate release (this chart does NOT bundle it).
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update
helm install pg bitnami/postgresql \
  -n open-computer-use \
  --set auth.username=openwebui \
  --set auth.database=openwebui \
  --set auth.existingSecret=ocu-shared \
  --set auth.secretKeys.userPasswordKey=POSTGRES_PASSWORD

# 3. Install computer-use-server. Edit values-computer-use.yaml first.
helm install ocu ../../../helm/computer-use-server \
  -n open-computer-use \
  -f values-computer-use.yaml

# 4. Install Open WebUI. Edit values-open-webui.yaml first.
helm install webui open-webui/open-webui \
  -n open-computer-use \
  -f values-open-webui.yaml

# 5. Smoke-test
helm test ocu -n open-computer-use
kubectl -n open-computer-use get pods
```

## How the wiring works

- **`MCP_API_KEY`** lives in the shared `ocu-shared` Secret.
  - `computer-use-server` reads it via `secrets.existingSecret=ocu-shared` (mounted via `envFrom` onto the orchestrator container).
  - Open WebUI reads it the same way, then `openwebui/init.sh` (or your manual setup) seeds it into the Tool and Filter Valves on first boot. **The values must match** — that's the whole reason for sharing one Secret.

- **`ORCHESTRATOR_URL`** is the **in-cluster** URL Open WebUI uses to call the MCP endpoint:
  ```text
  http://ocu-computer-use-server.open-computer-use.svc.cluster.local:8081
  ```
  Set as a plain env var on the Open WebUI container — `values-open-webui.yaml` shows the line. Browsers never see this URL.

- **`PUBLIC_BASE_URL`** is the **browser-facing** URL of the orchestrator. The orchestrator returns it in the `X-Public-Base-URL` header, and the Open WebUI filter uses it to rewrite preview links in chat. It must match the public hostname users actually hit. Set in `values-computer-use.yaml`.

> Note: the `openwebui/init.sh` script from this repo expects to run as the Open WebUI container's entrypoint wrapper. The upstream Open WebUI chart does **not** invoke it. Either build your own image (using `openwebui/Dockerfile` from this repo) and point the upstream chart at it via `image.repository`, or seed the Valves manually through the Admin UI on first boot. Both paths work — the init.sh path is more reproducible.

## Files in this directory

| File | Purpose |
|---|---|
| `values-computer-use.yaml` | values for our chart (orchestrator + DinD + cleanup) |
| `values-open-webui.yaml` | values for upstream Open WebUI chart, pointed at our Service |

## Uninstall

```bash
helm uninstall webui -n open-computer-use
helm uninstall ocu   -n open-computer-use
kubectl -n open-computer-use delete pvc -l app.kubernetes.io/instance=ocu
kubectl -n open-computer-use delete pvc -l app.kubernetes.io/instance=webui
kubectl -n open-computer-use delete secret ocu-shared
```
