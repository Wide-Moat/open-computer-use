<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# 12 — Tecnativa/docker-socket-proxy (privileged-API filter pattern)

> Source: [Tecnativa/docker-socket-proxy](https://github.com/Tecnativa/docker-socket-proxy). HAProxy-based filter for the Docker API.
> Pattern reference for Phase 2 (HTTP pool-manager sidecar — the *only* component that holds the Docker socket) and Phase 8 (egress filtering); general template for "filter access to a privileged API".

## 1. Endpoint allowlist via regex + env-gated rules

- **Where.** `haproxy.cfg:46-79` (frontend rules). Example `:60`:
  ```haproxy
  http-request allow if { path,url_dec -m reg -i ^(/v[\d\.]+)?/containers } { env(CONTAINERS) -m bool }
  ```
- **What.** Each API category (CONTAINERS, NETWORKS, VOLUMES, …) has a regex path matcher + an env-var boolean gate. `0 = deny`, `1 = allow`.
- **Why for us.** Phase 2 pool-manager: same shape filters Docker socket access. Phase 8: same shape filters egress URLs.
- **Skip.** Docker version prefix `(/v[\d\.]+)?` is Docker-specific.

## 2. Method/path split — read-only by default

- **Where.** `haproxy.cfg:48` (global filter), `:51-55` (per-op gates).
- **What.** `http-request deny unless METH_GET || { env(POST) -m bool }`. GET/HEAD allowed; POST/PUT/DELETE require `POST=1`. Destructive ops (ALLOW_STOP, ALLOW_RESTARTS, …) have independent gates **even when** POST is on.
- **Why for us.** Phase 2 — observability (list, get) ≠ mutation (delete). Phase 8 — block all egress POST/DELETE by default.
- **Protocol-agnostic.** Works for REST, gRPC-JSON bridges.

## 3. Env-var-driven config — operator UX

- **Where.** `Dockerfile:4-33` (25+ env vars); `docker-entrypoint.sh:23` (template substitution).
- **What.** Operators set `CONTAINERS=1 ALLOW_START=1` to grant only specific capabilities. Defaults conservative (most=0; only `EVENTS`, `PING`, `VERSION` = 1).
- **Why for us.** Helm `values.yaml` exposes the same boolean knobs. No code recompile to change policy.
- **Skip for k8s API.** Use native RBAC for k8s; env gates are best as a *secondary defense layer*.

## 4. Health, observability, streaming-safe backends

- **Where.** `haproxy.cfg:42-44` (special `events` backend with `timeout server 0`), `:2, 13-14` (logging), README `:198-202` (`LOG_LEVEL`).
- **What.** Streaming endpoints (e.g. Docker `/events`, k8s watch) need **no server timeout** or they get killed mid-stream. Full request logs (httplog) feed audit.
- **Why for us.** Phase 2 — k8s watch streams and L1 streaming exec calls require the same treatment.

## 5. Least-privilege secure-by-default posture

- **Where.** README `:109-147` (access matrix); Dockerfile defaults.
- **What.** All dangerous operations default to deny (`AUTH=0`, `SECRETS=0`, `POST=0`, `CONTAINERS=0`). Only read-only basics allowed. **No catch-all "allow everything" gate.**
- **Why for us.** Foundational; matches cross-cutting pattern 13 (NetworkPolicy default-deny). Operator must opt-in to each capability.

## 6. Trust boundary at network edge — no TLS inside

- **Where.** README `:26-34`.
- **What.** No TLS inside the container network. Security relies on container/k8s networking isolation. External exposure forbidden.
- **Why for us.** Phase 2 — pool-manager runs in sandbox pod's netns or via Unix socket / private service. No mTLS within the trust boundary. mTLS only for cross-network egress (Phase 8).

## Adoption checklist

1. **Config as code** — template + env vars locked at deploy time (Helm/kustomize).
2. **Deny by default** — explicit allowlist, never blocklist.
3. **Granular gates** — separate controls per operation class.
4. **Audit logging** — full request log, configurable level.
5. **Streaming-safe backends** — no server timeout on watch / events / exec.
6. **Network-edge trust** — proxy is network-isolated; no TLS inside.
7. **Matrix tests** — see `tests/test_service.py:10-40` for permission-matrix testing.
