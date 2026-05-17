<!-- SPDX-License-Identifier: BUSL-1.1 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# 03 — Layer 3: Orchestrator / Providers

> Pluggable layer between the control plane (L4) and the sandbox runtime (L2).
> The interface is **the** key abstraction in this whole roadmap — Phase 1 introduces it.

## The interface

Published as a `.proto` schema from Phase 6 onward (see [ADR-0008](../adr/0008-internal-grpc-external-rest-mcp.md) — connect-go on the wire). Before Phase 6 it lives as a Python `Protocol`, in-process; the shape is identical so the migration is mechanical.

```proto
service SandboxProvider {
  rpc Spawn     (SpawnRequest)        returns (SpawnResponse);
  rpc Configure (ConfigureRequest)    returns (ConfigureResponse);
  rpc Exec      (ExecRequest)         returns (stream ExecChunk);
  rpc Upload    (stream UploadChunk)  returns (UploadResponse);
  rpc Download  (DownloadRequest)     returns (stream DownloadChunk);
  rpc Stop      (StopRequest)         returns (StopResponse);
  rpc List      (ListRequest)         returns (stream SandboxHandle);
  rpc Health    (HealthRequest)       returns (HealthResponse);
  rpc Events    (EventsRequest)       returns (stream LifecycleEvent);  // provider → control plane
}
```

- `SandboxHandle` is opaque to L4; internally it carries provider-specific identifiers (Docker container id, k8s pod ref, VM uuid).
- `SandboxTemplate` is provider-agnostic — see [09-templates.md](./09-templates.md).
- `TenantContext` carries `tenant_id`, `session_id`, headers (`X-Chat-Id`, `X-User-Email`), short-lived secrets.

**Transport per phase:**
- Phase 1 — in-process Python `Protocol`.
- Phase 2 — HTTP/JSON over the pool-manager sidecar (still Python).
- Phase 6+ — **connect-go** (gRPC + Connect + HTTP/JSON from one `.proto`). mTLS in production.

The same `.proto` is consumed by L4 (client) and L3 (server). Phase 7 the L1 agent serves a sibling `Agent` service from the same compile, so L3 calls L1 as a typed client.

## Concrete providers

### DockerComposeProvider (PoC, current path)

- **Phase:** in-process today (via `docker_manager.py`); extracted behind the interface in Phase 1; talks HTTP to a pool-manager sidecar from Phase 2.
- **Backend:** Docker socket — but only this provider knows that. L4 never sees it.
- **Use:** local dev, single-host PoC, integration tests.
- **Warm pool:** added in Phase 2 (minSize defaults 0 to preserve current behavior).

### KubernetesProvider

- **Phase:** 5.
- **Backend:** `kubernetes-asyncio` (Python) or `client-go` (after Phase 6 Go cutover). Talks to k8s API.
- **CRD basis:** [`kubernetes-sigs/agent-sandbox`](https://github.com/kubernetes-sigs/agent-sandbox) — `Sandbox`, `SandboxTemplate`, `SandboxClaim`, `SandboxWarmPool`. We adopt them rather than inventing our own; we contribute upstream if gaps appear.
- **Runtime selection:** per-template `runtimeClassName` (runc / sysbox / kata-fc / kata-ch / gvisor).
- **Network:** default-deny `NetworkPolicy`, egress only via proxy. See [08-networking.md](./08-networking.md).
- **Replaces today's:** DinD-in-pod pattern. The current Helm chart's inner `docker:dind` sidecar is **transitional only** — Phase 5 replaces it with real per-pod sandboxes.

### DirectCHProvider (optional, Phase 9+)

- **Backend:** drives Cloud Hypervisor directly on a bare-metal host without k8s.
- **Use:** edge deployments, single-tenant compliance setups, very low-latency requirements.
- **Trade-off:** no k8s orchestration goodies (HPA, NetworkPolicy, RBAC) — provider implements them itself.

### What we will NOT implement

- **Nomad provider** — Nomad is BSL ([ADR-0006](../adr/0006-no-agpl-no-bsl-dependencies.md)).
- **Generic OCI provider** — too vague; pick the orchestrator.

## Warm pool semantics

Three knobs per template:
- `minSize` — sandboxes always idle and ready.
- `targetSize` — provider tries to maintain (refills as sessions consume from pool).
- `maxSize` — hard cap regardless of demand.

Lifecycle:
1. Provider pre-starts `minSize` sandboxes per template, runs `/v1/configure` with placeholder context.
2. On `spawn(template, ctx)` request, pop one from pool, re-configure with real `ctx` (injects session id, env, egress JWT).
3. Background refill task brings pool back to `targetSize`.
4. Sessions ending → sandbox is destroyed (not returned to pool — tenancy hygiene; see [07-security.md](./07-security.md)).

Phase 2 ships the skeleton (`minSize=0` default = no behavior change). Phase 5 makes it real. Phase 10 adds snapshot/restore so the "warm" state can persist sessions.

## Reaper / cleanup

- Current implementation: per-container Python thread + cron sidecar.
- Target: provider-owned background task, idle-timeout per template, reaped synchronously when stopping. Cron sidecar is removed.

## Tenancy & isolation

- Per `tenant_id`: dedicated k8s namespace (`KubernetesProvider`) or dedicated network (`DockerComposeProvider`).
- `NetworkPolicy`: deny workspace→workspace, deny workspace→control-plane (except via the egress proxy and the L4-managed exec path).
- `ResourceQuota` + `LimitRange` per namespace (k8s only) — blast-radius containment.
- Per-sandbox `ServiceAccount` with **empty** RBAC (no cluster enumeration possible).

## Events

Provider emits structured events the control plane consumes for audit + UI:
- `sandbox.spawned`, `sandbox.configured`, `sandbox.exec.started/completed`, `sandbox.stopped`, `sandbox.health.degraded`, `sandbox.evicted`.

Transport: same channel as L4 ↔ L3 (HTTP stream or gRPC server-side stream).

## Phase-by-phase progression for L3

| Phase | What changes |
|---|---|
| 1 | Interface extracted; `DockerComposeProvider` is the only impl; still in-process |
| 2 | HTTP transport; pool-manager sidecar owns Docker socket; warm pool skeleton |
| 3 | Storage (S3) plumbed via provider (mount specs in template) |
| 4 | Secret broker integration — provider receives short-lived creds in `configure` |
| 5 | `KubernetesProvider` ships; Helm chart real per-pod sandboxes |
| 7 | Provider learns to pass new Go-agent endpoints (vsock-ready spec) |
| 9 | `DirectCHProvider` ships; templates gain `runtimeClass` selection |
| 10 | Snapshot / restore + multi-region session routing |

## Source

- [`sandboxd/docs/architecture.md`](../../../sandboxd/docs/architecture.md) (Layer 3 sections)
- [`docs/future-architecture/architecture/01-layers.md`](./01-layers.md)
- [`docs/future-architecture/references.md`](../references.md) (`kubernetes-sigs/agent-sandbox`, `e2b-dev/infra`)
