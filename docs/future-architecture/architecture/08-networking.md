# 08 — Networking

> Network policy, egress proxy, CDP/ttyd routing, ingress.
> Cross-cuts L3 + L4.

## Principles

1. **Default-deny everywhere.** Every namespace, every sandbox, every direction.
2. **Single mediated egress path** — the JWT-allowlist proxy (see [07-security.md](./07-security.md)).
3. **Sandbox is not publicly addressable.** Ever.
4. **L4 ↔ L3 is mTLS.** L3 ↔ L1 is network-policy-isolated, no app-level auth.

## Topology (k8s target, Phase 5+)

```
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
| 10 | Multi-AZ session routing — snapshot-based recovery on pod failure (not in-memory affinity); multi-region foundations only — see `sandboxd` §"Other catalog additions" |

## Source

- [`sandboxd/docs/security.md`](../../../sandboxd/docs/security.md)
- [07-security.md](./07-security.md)
- [`docs/future-architecture/references.md`](../references.md) (`agentbox`)
