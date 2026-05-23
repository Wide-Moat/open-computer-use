<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
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

### DockerSocketProvider (PoC, current path)

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

Five knobs per template:
- `minSize` — sandboxes always idle and ready.
- `targetSize` — provider tries to maintain (refills as sessions consume from pool).
- `maxSize` — hard cap regardless of demand.
- `refillRate` — max sandboxes the refiller may start per second (smooths bursty refill load; without it, a flood of session-ends triggers a thundering-herd spawn).
- `maxAge` — TTL at which an idle pool sandbox is destroyed and replaced regardless of demand. Prevents long-lived "warm" sandboxes from accumulating per-template image drift, leaked file handles, or stale skill blobs.

Lifecycle:
1. Provider pre-starts `minSize` sandboxes per template, runs `Configure` with placeholder context.
2. On `Spawn(template, ctx)` request, pop one from pool, re-`Configure` with real `ctx` (injects session id, env, egress JWT).
3. Background refill task brings pool back to `targetSize` at no more than `refillRate` per second.
4. Idle sandbox older than `maxAge` → destroyed, refiller spawns a replacement.
5. Sessions ending → sandbox is destroyed (not returned to pool — tenancy hygiene; see [07-security.md](./07-security.md)).

Phase 2 ships the skeleton (`minSize=0` default = no behavior change). Phase 5 makes it real. Phase 10 swaps the "warm sandboxes pool" for a **frozen-snapshot pool** with block-device hot-swap on resume — same knobs, different mechanics. See [`research/20-snapstart-hot-swap.md`](../research/20-snapstart-hot-swap.md).

## SandboxClaim CRD semantics (KubernetesProvider)

For the `KubernetesProvider`, the wire between L4 and L3 is **typed Kubernetes objects**, not opaque RPC payloads. The CRD shape comes from [`kubernetes-sigs/agent-sandbox`](https://github.com/kubernetes-sigs/agent-sandbox) — we adopt rather than reinvent.

```yaml
apiVersion: sandbox.kubernetes.io/v1alpha1
kind: SandboxClaim
metadata:
  name: claim-<session-id>
  namespace: tenant-<tenant-id>
spec:
  templateRef:
    name: customer-cu-kata-ch-v3   # SandboxTemplate to allocate from
  envtype: anthropic-hosted         # provider-side dispatch (see below)
  lease:
    ttlSeconds: 7200                # auto-release if the session never returns
    renewDeadlineSeconds: 60        # heartbeat budget
  context:                          # injected via Agent.Configure
    sessionId: <id>
    tenantId:  <id>
    egressJwtSecretRef:
      name: egress-token-<session-id>
status:
  phase:           Bound | Pending | Released | Failed
  sandboxRef:      { name, uid }    # opaque to L4; cluster-internal handle
  boundAt:         <timestamp>
  observedRuntime: kata-ch          # actual L2 runtime that landed
  conditions:     [...]
```

L4's `Spawn` becomes "create a `SandboxClaim`, watch `.status.phase`." `Stop` is `delete claim`. Health is the same watch. The CRD is what gives the provider a place to store **lease state** without L4 caring about Kubernetes specifics.

Two operational properties we get for free:
- **TTL-driven cleanup.** Claims past their lease are released by the controller, not by L4. L4 crashing does not strand sandboxes.
- **kubectl-debuggable.** Operators can `kubectl get sandboxclaims -A` to see pool state without going through L4's admin API.

The `DockerSocketProvider` and `DirectCHProvider` implement the same lifecycle in-process; the CRD shape is the k8s realization of a provider-internal concept.

## Environment-type dispatch (Baku pattern)

Templates carry an `envtype` field consumed by the provider to pick the backend mechanism. The pattern is lifted from Anthropic's Baku/`environment-runner` split ([`research/21`](../research/21-environment-runner-go.md), inspiration-only) and applied narrowly here:

| `envtype` | Provider behaviour | Use case |
|---|---|---|
| `dev` | runc on Docker Compose; no isolation; no egress proxy | Local PoC, integration tests |
| `internal` | sysbox on k8s; egress proxy in monitor mode | Trusted employees |
| `customer-shared` | sysbox or gVisor (per-template) on k8s; egress proxy enforcing | Customer code-only sandboxes |
| `customer-cu` | Kata (CH or FC) on bare-metal node pool; egress proxy enforcing | Customer Computer Use sessions |
| `anthropic-hosted` | Reserved label for our own SaaS deployment; same as `customer-cu` today but pinned to a tier | Anthropic-equivalent deployment shape |
| `byoc` | Customer-supplied cluster; provider holds a lease on a customer namespace | Reserved, not Phase-1 |

`envtype` is **not** the same as `runtimeClass`. `runtimeClass` is the L2 isolation primitive; `envtype` is the L3 dispatch key. One `envtype` can map to multiple `runtimeClass`-es depending on template (e.g. `customer-shared` resolves to sysbox for code, gVisor for browserless code-exec).

## Reaper / cleanup

- Current implementation: per-container Python thread + cron sidecar.
- Target: provider-owned background task, idle-timeout per template, reaped synchronously when stopping. Cron sidecar is removed.

## Tenancy & isolation

- Per `tenant_id`: dedicated k8s namespace (`KubernetesProvider`) or dedicated network (`DockerSocketProvider`).
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
| 1 | Interface extracted; `DockerSocketProvider` is the only impl; still in-process |
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
