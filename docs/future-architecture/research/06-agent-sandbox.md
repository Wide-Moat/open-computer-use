<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# 06 — kubernetes-sigs/agent-sandbox (CRD base for `KubernetesProvider`)

> Source: [kubernetes-sigs/agent-sandbox](https://github.com/kubernetes-sigs/agent-sandbox). Google-backed, SIG Apps, v1alpha1.
> Direct base for [Phase 5](../roadmap.md#phase-5--helm-hardening--kubernetesprovider) `KubernetesProvider`.

## 1. CRD shapes & field semantics

### `Sandbox` — core singleton workload

- **Where.** `api/v1alpha1/sandbox_types.go:129-244`.
- **Fields.**
  - `podTemplate` (required) — embeds `corev1.PodSpec` + optional labels/annotations.
  - `volumeClaimTemplates[]` — dynamically provisioned PVCs; merged into `Pod.Spec.Volumes`.
  - `replicas` — binary (0/1) for suspend/resume.
  - `service` — bool; auto-creates headless Service.
  - `lifecycle.shutdownTime` — absolute expiry; `lifecycle.shutdownPolicy` ∈ {Delete, Retain}.
- **Status.** Conditions: `Ready`, `Suspended`, `Finished`. `serviceFQDN`, `podIPs[]`.

### `SandboxTemplate` — reusable blueprint

- **Where.** `extensions/api/v1alpha1/sandboxtemplate_types.go:73-154`.
- **Fields.** Inherits Sandbox fields, plus:
  - `networkPolicyManagement` ∈ {Managed, Unmanaged}.
  - `networkPolicy` — custom Ingress/Egress; **if omitted → "Secure by Default"** (Sandbox Router ingress only, no internal egress).
  - `envVarsInjectionPolicy` ∈ {Allowed, Overrides, Disallowed} — gates whether a Claim can inject env vars.
- **No status subresource** — read-only template.

### `SandboxClaim` — user-facing claim

- **Where.** `extensions/api/v1alpha1/sandboxclaim_types.go:124-194`.
- **Fields.**
  - `sandboxTemplateRef.name` (required, same namespace).
  - `lifecycle` (mirrors Sandbox + `ttlSecondsAfterFinished`).
  - `warmpool` ∈ {none, default, named-pool} — default attempts adoption from warm pool.
  - `additionalPodMetadata` — labels/annotations propagated; restricted domains (`kubernetes.io`, `k8s.io`, `agents.x-k8s.io` forbidden).
  - `env[]` — gated by template's `envVarsInjectionPolicy`.
- **Status.** Mirrors Sandbox + claim-specific (`Ready`, `Expired`, `Finished`).

### `SandboxWarmPool` — pre-warmed reservoir

- **Where.** `extensions/api/v1alpha1/sandboxwarmpool_types.go:31-107`.
- **Fields.** `replicas` (HPA-compatible), `sandboxTemplateRef`, `updateStrategy.type` ∈ {Recreate, OnReplenish}.
- **Status.** `replicas`, `readyReplicas`, `selector` (label for pool member discovery).

## 2. Controller reconciliation patterns

### Sandbox controller

- **Where.** `controllers/sandbox_controller.go:82-100`.
- **Behaviors.**
  - Tracks pod via controllerRef + `agents.x-k8s.io/pod-name` annotation when adopted from pool.
  - Volume merging — PVC-backed volumes from `volumeClaimTemplates` override by name (StatefulSet-like).
  - Lifecycle: polls `shutdownTime` expiry, deletes Pod+Service per `shutdownPolicy`.
  - Service provisioning — headless Service with same name.
  - Finalizers cascade Pod/PVC deletion.

### SandboxClaim controller

- **Where.** `extensions/controllers/sandboxclaim_controller.go:140-282`.
- **Critical patterns.**
  - **Fast-path warm-pool adoption before template lookup** — minimizes cold-start latency.
  - Lazy template validation — requeue without error if missing (no log spam).
  - Synchronous metadata validation (reject if bad labels).
  - **Namespace isolation enforced** — no cross-namespace adoption.
  - Tracks `observedTime` per claim UID — measures cold-start.
  - Dual timers: `shutdownTime` (absolute) and `ttlSecondsAfterFinished` (relative to Finished condition).
  - NetworkPolicy reconciliation is **non-blocking** — continues if fetch fails.

### SandboxWarmPool controller

- **Where.** `extensions/controllers/sandboxwarmpool_controller.go:63-120`.
- **Behaviors.** Lists by hash label; creates/deletes to match `replicas`. `Recreate` deletes stale immediately; `OnReplenish` waits for adoption.

### SandboxTemplate controller

- **Where.** `extensions/controllers/sandboxtemplate_controller.go:52-100`.
- **Behaviors.** Creates/updates **single shared NetworkPolicy** per template (not per pod). NP name = `<template.Name>-network-policy`. Secure Default = ingress only from Sandbox Router, egress to public internet excluding RFC1918 + metadata server.

## 3. RuntimeClass integration

- **Mechanism.** **No explicit CRD field** — `podTemplate.spec.runtimeClassName` is passed through to Pod for kubelet resolution.
- **Examples.** `examples/kata-gke-sandbox/README.md:42-60` uses `runtimeClassName: kata-qemu`. `examples/quickstart/gvisor.md:45-55` uses `runtimeClassName: gvisor`.
- **Per-tenant tiering.** Different templates → different runtimes. **No dynamic per-claim override** in the core API.
- **For us.** Aligns with [ADR-0004](../adr/0004-pluggable-runtime-via-runtimeclass.md). We propagate `SandboxTemplate.runtime_class` into the embedded `podTemplate.spec.runtimeClassName`. If we need per-claim override (e.g. session tier), we add a custom mutation (admission webhook or template selection in L4).

## 4. NetworkPolicy assumptions ⚠️

- **Single shared NP per template** — pod selector via hash label `agents.x-k8s.io/sandbox-template-ref-hash`.
- **Secure Default details (when `networkPolicy` omitted):**
  - Ingress: only from Sandbox Router.
  - Egress: public internet, **excluding RFC1918 + metadata server** (no cluster DNS by default).
  - ⚠ **Sidecars (Istio, monitoring) on separate ports must be explicitly allowed** in custom rules.
- **Operators must add cluster-DNS allowance** — easy to miss.
- **For us.** Phase 5 must add custom NetworkPolicy that allows kube-dns + our egress-proxy svc + Sandbox Router ingress. Document the sidecar caveat loudly in our Helm `values.yaml`.

## 5. RBAC model

- **Where.** `k8s/rbac.generated.yaml:1-60` (core) + `k8s/extensions-rbac.generated.yaml:1-88` (extensions).
- **Core controller.** ClusterRole `agent-sandbox-controller` — sandboxes (+ status, finalizers), pods, PVCs, services, events, leases (leader-elect).
- **Extensions controller.** Adds CRDs (sandboxclaims, templates, warmpools + status/finalizers), Pod patching (adoption), NetworkPolicy CRUD.
- **Verbs.** Standard CRUD set.
- **For us.** Reuse as-is via Helm.

## 6. Status subresource design

- **Conditions** — `metav1.Condition` (type, status, reason, message, observedGeneration).
- **Sandbox.** `Ready` (DependenciesReady/NotReady/SandboxSuspended) | `Suspended` (PodTerminated/PodNotTerminated) | `Finished` (PodSucceeded/PodFailed).
- **`serviceFQDN`** — controller-flag `--cluster-domain` configurable.
- **`podIPs[]`** — direct from Pod status, mirrored for fast L4 routing (matches our cross-cutting pattern 9: app-layer routing, not ClientIP).

## 7. Webhooks

- **None.** All validation is synchronous in controllers + OpenAPI schema (kubebuilder markers).
- **For us.** Defer admission webhooks; add later only if cross-resource validation is needed.

## 8. Project maturity signals

- **Version.** v1alpha1 (pre-beta). Roadmap mentions Beta/GA as future.
- **Governance.** kubernetes-sigs project; SIG Apps; CLA; OWNERS file. Auto-stale 30 d, auto-close 15 d. AI-assisted first-pass review (Copilot).
- **Adoption.** No explicit prod-user list. Kata + gVisor examples lean GKE. Backed by Google + community.
- **Release cadence.** Manual via `RELEASE.md`; no release tags in shallow clone.
- **For us.** Vendor the CRDs **with our own copy under version control** (Phase 5 research). Don't blindly track upstream main during alpha.

## 9. Skip notes

- **No per-claim RuntimeClass override** — different templates needed.
- **No webhook validation** — sync in controllers.
- **Sidecars need explicit NP rules.**
- **No dynamic cluster-domain discovery** — operator sets controller flag.

## Phase-5 implementation checklist

1. Vendor `Sandbox`/`SandboxTemplate`/`SandboxClaim`/`SandboxWarmPool` types under our own CRD group (or upstream `agents.x-k8s.io` directly — decide in `phase-5-research.md`).
2. Map our `SandboxProvider.spawn(template, ctx)` → create `SandboxClaim`; watch `Ready` condition.
3. Use Secure-Default NetworkPolicy + override to allow our egress-proxy svc + kube-dns.
4. Per-tenant template = per-tenant RuntimeClass (sysbox / gVisor / kata-ch).
5. Warm pool: `SandboxWarmPool` with `replicas` driven by L4 demand prediction.
6. Fast-path adoption is a controller-internal optimization — our L4 just sees fast `Ready`.
7. App-layer session routing — L4 reads `Status.sandbox.podIPs[0]` from Claim, forwards HTTP directly.
