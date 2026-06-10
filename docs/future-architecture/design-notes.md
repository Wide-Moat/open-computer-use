<!-- SPDX-License-Identifier: BUSL-1.1 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# Design Notes

Solution-shaped proposals that are **not yet locked**. This file is the sibling of [`gaps.md`](./gaps.md): `gaps.md` records *problems and risks*, this file records *candidate solutions* to them.

Rules:

- A design note is a **candidate**, not spec. Each one names its owning roadmap phase and must clear that phase's research pass and owner sign-off before any of it lands in `architecture/` or an ADR.
- If a note conflicts with a file under `architecture/`, **`architecture/` wins** until the owning phase ships (same rule as the [README](./README.md#what-this-document-tree-does-not-do)).
- Any third-party component named in a note must pass [ADR-0006](./adr/0006-no-agpl-no-bsl-dependencies.md) license vetting (no AGPL, no BSL in direct deps) at phase-research time, not here.

---

## DN-1 — Substrate-independent egress, identity & secret-broker design

> Owning phases: Phase 4 (secret broker), Phase 6 (control plane), Phase 8 (egress proxy).
> Derived from internal microVM design notes.
> Status: **candidate.** Pending Phase 4/6/8 research + owner sign-off.

**Goal.** One design for egress control, connectivity/identity, and secret handling that holds across all three deployment substrates — Docker Compose PoC, Kubernetes, microVM — as *one invariant with thin per-substrate enforcement*, not three separate designs.

### 1. One egress invariant, three thin wrappers

Invariant: **default-deny + allowlist-on-connect** — enforce against the resolved IP + TLS SNI, never the DNS name.

| Substrate | Enforcement binding |
|---|---|
| Docker Compose | `DOCKER-USER` iptables chain |
| Kubernetes | `NetworkPolicy` (egress) |
| microVM | `nftables` |

SNI-based allowlisting implementations to evaluate at Phase 8: HAProxy `req.ssl_sni`, smokescreen, Cilium `toFQDNs`, Envoy `tls_inspector`.

### 2. "Internet, not intranet"

The egress filter must deny RFC1918 + link-local + cloud metadata (`169.254.169.254`), and **must not forget IPv6** (`fc00::/7`, `fe80::/10`). A sandbox that can reach the internet must still not reach the deployment's internal network or the host's metadata endpoint.

### 3. Connectivity + identity

For the cases where a sandbox legitimately needs an *internal* service, do not widen the egress allowlist to the intranet. Instead use a mesh: **Tailscale / Headscale (self-hosted)** — connectivity over a single outbound connection, identity by mesh membership, least-privilege via mesh ACLs. The sandbox reaches exactly the internal services its ACL grants and nothing else.

### 4. Don't expose keys — a broker-gateway

A **broker-gateway lives outside the sandbox.** The workload receives a per-session token; the real `ANTHROPIC_API_KEY` exists only on the gateway. Claude Code (and any model client) is pointed at the gateway via `ANTHROPIC_BASE_URL`. **LiteLLM** sits *behind* the gateway as a token-accounting / usage-metering layer — **not** as the auth or RBAC layer.

It aligns with the [`07-security.md`](./architecture/07-security.md) secret broker (Phase 4) and with an FD-passing hardening philosophy: a compromised sandbox can leak at most a scoped, short-lived session token, never the long-lived provider key.

### 5. Real RBAC

Authorization is a pipeline, and **LiteLLM is not it**:

```text
IdP (Keycloak)
  → policy engine (OPA / Casbin)
    → enforcement points (broker-gateway, egress filter, mesh ACLs)
      → LiteLLM  (narrow role: token accounting only)
```

Explicitly: **LiteLLM ≠ RBAC.** It meters; it does not decide who may do what.

### Mapping to the roadmap

| Section | Owning phase | Refines |
|---|---|---|
| §1–§2 egress invariant + SSRF deny-set | [Phase 8](./roadmap.md#phase-8) | [`08-networking.md`](./architecture/08-networking.md) |
| §3 mesh connectivity / identity | none yet — flag for Phase 6/8 scoping | new surface |
| §4 broker-gateway | [Phase 4](./roadmap.md#phase-4) | [`07-security.md`](./architecture/07-security.md) |
| §5 RBAC pipeline | [Phase 6](./roadmap.md#phase-6) + Phase 4 | [`02-layer4-control-plane.md`](./architecture/02-layer4-control-plane.md) |

**License note (ADR-0006).** First-pass read: Headscale (BSD-3), Keycloak / OPA / Casbin / Cilium / Envoy (Apache-2), smokescreen (MIT), LiteLLM (MIT) are clear of AGPL/BSL. HAProxy is GPLv2 — acceptable as a standalone deployed service (not linked into our binaries). Confirm every dependency at the owning phase's research pass; this note does not authorize adoption.
