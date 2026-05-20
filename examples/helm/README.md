# Helm examples

Two ready-to-tweak deployment recipes for [`helm/computer-use-server/`](../../helm/computer-use-server/).

| Recipe | Equivalent Compose stack | When to use |
|---|---|---|
| [`standalone/`](standalone/) | `docker-compose.yml` | You already run Open WebUI (or some other MCP client) and just want the orchestrator. |
| [`with-open-webui/`](with-open-webui/) | `docker-compose.yml` + `docker-compose.webui.yml` | You want the whole stack — orchestrator, Open WebUI, Postgres — in one cluster. |

Open WebUI itself is **not** packaged by our chart. Use the upstream chart at <https://github.com/open-webui/helm-charts> instead — `with-open-webui/` shows how to wire the two together.

## Prerequisites

- Kubernetes ≥ 1.27
- [Kata Containers](https://katacontainers.io/) installed on candidate nodes (the chart runs the inner Docker daemon under Kata) — see [`docs/kata-runtime.md`](../../docs/kata-runtime.md)
- A StorageClass that supports `ReadWriteOnce`, and one that provisions Block volumes for `/var/lib/docker`
- An Ingress controller (nginx-ingress, Traefik, etc.)
- DNS + TLS for the public hostnames

See [`docs/kubernetes.md`](../../docs/kubernetes.md) for the full architecture overview.
