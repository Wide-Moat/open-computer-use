<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# 08 — Networking

> Network policy, egress proxy, CDP/ttyd routing, ingress.
> Cross-cuts L3 + L4.

## Principles

1. **Default-deny everywhere.** Every namespace, every sandbox, every direction.
2. **Single mediated egress path** — the JWT-allowlist proxy (see [07-security.md](./07-security.md)).
3. **Sandbox is not publicly addressable.** Ever.
4. **L4 ↔ L3 is mTLS.** L3 ↔ L1 is network-policy-isolated, no app-level auth.

## Topology (k8s target, Phase 5+)

```text
                  Internet
                     │
            ┌────────▼────────┐
            │   Ingress + WAF │   (public; serves L4 only)
            └────────┬────────┘
                     │
            ┌────────▼────────┐
            │  L4 Control Plane│
            └────┬───────┬────┘
                 │       │
        mTLS gRPC│       │ HTTPS to S3 / Secrets / KV
                 │       │
            ┌────▼────┐  │
            │   L3    │  │
            │ Provider│  │
            └────┬────┘  │
                 │ k8s API
            ┌────▼─────────────────────────────────────┐
            │  Tenant namespace (per tenant_id)        │
            │  NetworkPolicy: deny all, allow:          │
            │    - L3 → sandbox pod port (exec API)     │
            │    - sandbox → egress-proxy svc           │
            │  No pod-to-pod within namespace either.   │
            │                                            │
            │  ┌─────────────┐   ┌─────────────────┐    │
            │  │  Sandbox A  │   │  Egress proxy   │────┼──► Internet
            │  │  (L1 agent) │──►│  (JWT validate) │    │   (allowlisted)
            │  └─────────────┘   └─────────────────┘    │
            └────────────────────────────────────────────┘
```

## NetworkPolicy (default per tenant namespace)

- `default-deny-ingress` and `default-deny-egress` on every pod.
- Allow ingress: from `namespace=control-plane` pods (label-selected) on the sandbox port only.
- Allow egress: to `namespace=egress` egress-proxy svc on its port only; plus DNS to kube-dns.
- **No pod-to-pod within the tenant namespace** — workspaces never see each other.

## Egress proxy

- One deployment per cluster (HA-replicated). Service in a dedicated `egress` namespace.
- Validates per-session JWT issued by L4's secret broker.
- JWT carries: `session_id`, `allowed_hosts` (or regex), `expiry`.
- Logs: destination host, decision, JWT id, latency. Sent to audit sink.
- Reference: [`Michaelliv/agentbox`](https://github.com/Michaelliv/agentbox). Port to Go in Phase 8.

DNS:
- Allowlist DNS too (egress to kube-dns; kube-dns has its own egress allowlist for resolution).
- Or: proxy resolves DNS itself, sandbox uses HTTP proxy directly.
- Decision deferred to Phase 8 research.

## CDP / ttyd routing

Today:
- Open WebUI / user UI calls L4 (`computer-use-server`) on a public route.
- L4 proxies CDP WebSocket frames to/from the sandbox's exposed Chromium.
- Same path for ttyd.

Target (Phase 6+):
- Same shape: L4 is the only public surface for CDP/ttyd too.
- L4 ↔ sandbox: mTLS internal. Sandbox's CDP endpoint reachable only from L4 pods (NetworkPolicy).
- Long-lived WebSocket — L4 must be HA-friendly (sticky sessions via consistent hashing, or session-router lookup on each new connection).

## Ingress (public)

- TLS terminated at ingress (cert-manager + Let's Encrypt for self-hosted; ACM for AWS).
- WAF in front for public deployments (mod_security, AWS WAF, Cloudflare).
- Only L4 routes exposed publicly. L3 / L1 / sandbox pods have no public ingress.

## Docker Compose (PoC)

- Phases 0–4: existing compose network; no NetworkPolicy equivalent.
- Phase 8: optional egress proxy container can be enabled in Compose for local testing of the allowlist pattern.

## What ships, when

| Phase | Network change |
|---|---|
| 1–4 | No network topology change (Compose stays as today) |
| 5 | Helm chart adds NetworkPolicy default-deny + tenant namespace template |
| 6 | mTLS L4 ↔ L3; ingress/WAF guidance documented |
| 8 | Egress proxy + JWT signing in L4 + audit sink (prereq for untrusted tier in Phase 9) |
| 10 | Multi-AZ session routing — snapshot-based recovery on pod failure (not in-memory affinity); multi-region foundations only |

## Multi-region workspace proxies (Phase 10 substrate)

Long-lived CDP / ttyd WebSockets penalize latency hard — a 200 ms RTT makes a Chromium screencast feel underwater. Once the deployment spans more than one region, L4 cannot terminate every user's WebSocket centrally without paying the cross-region tax on every keystroke.

The pattern, lifted from Coder ([`research/03`](../research/03-coder.md)):

```text
                User UI
                   │
                   ▼
        ┌──────────────────────┐
        │ Region-local         │
        │ Workspace Proxy      │   one per region; terminates user-side TLS
        │ (CDP/ttyd terminator)│   consistent-hashes by session_id
        └──────────┬───────────┘
                   │ mTLS, region-local
                   ▼
        ┌──────────────────────┐
        │ L4 (global, multi-AZ)│
        │ + KV session router  │
        └──────────┬───────────┘
                   │
                   ▼
        ┌──────────────────────┐
        │ L3 + sandboxes        │
        │ in the user's region  │
        └──────────────────────┘
```

Properties:
- **User-perceived latency is region-local.** RTT to the sandbox stays under the regional ceiling.
- **L4 stays single-pane-of-glass.** Auth, session router, secret broker remain global; the proxies are dumb shovels.
- **Failure isolation.** A region's proxy can lose its L4 link without dropping in-flight CDP frames (proxy buffers; reconnects when L4 returns).
- **Consistent-hash by `session_id`.** Within a region, the same session always lands on the same proxy replica. Avoids the `sessionAffinity: ClientIP` anti-pattern called out in [`02-layer4-control-plane.md`](./02-layer4-control-plane.md).

What this implies for earlier phases:
- The CDP/ttyd transport must already be transparent passthrough (L4 does not parse frames — [ADR-0008](../adr/0008-internal-grpc-external-rest-mcp.md)). Anything that requires L4 to understand the wire breaks here.
- Session router state must be **externally addressable** (KV, not in-process) so a region-local proxy can resolve `session_id → region`.
- mTLS between proxy and L4 must be operational — Phase 6 deliverable.

Phase 10 ships one proxy per region; before that, the proxy is just L4 itself (one region). The architecture is forward-compatible: a Phase 6 deployment with no proxies looks like the Phase 10 deployment minus the geographic shard.

## Source

- Internal security notes
- [07-security.md](./07-security.md)
- [`docs/future-architecture/references.md`](../references.md) (`agentbox`)
