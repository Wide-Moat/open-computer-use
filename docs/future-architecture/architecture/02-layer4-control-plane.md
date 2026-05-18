<!-- SPDX-License-Identifier: BUSL-1.1 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# 02 — Layer 4: Control Plane

> Status: **design** (locked target). Implementation lands in roadmap Phase 6.
> Language: **Go** ([ADR-0001](../adr/0001-control-plane-language-go.md)).
> Until Phase 6 ships, today's `computer-use-server/` (FastAPI) **is** the de-facto L4 — Phases 1–5 evolve it in place.

## Responsibilities

1. **User-facing MCP gateway.** Accept MCP JSON-RPC over HTTP/WebSocket (the same surface today's `app.py` exposes at `/mcp`). Authenticate, route to a session's L1 agent, stream results back.
2. **Admin REST/GraphQL.** Operator-facing API: list sessions, drain a tenant, rotate keys, push a new `SandboxTemplate`, view audit log. Backs the admin UI.
3. **Tenancy & auth.** OIDC (employee + customer), JWT issuance for sandbox-internal use, RBAC.
4. **Session router.** `session_id → { sandbox_handle, tenant_id, template_id, created_at }`. Backed by a fast KV (Redis / Valkey / etcd). Single source of truth for "which sandbox serves this chat".
5. **Secret broker.** Mint short-lived, scoped credentials (Anthropic, GitLab, S3 STS) on session start; rotate without restarting the sandbox. See [07-security.md](./07-security.md).
6. **Egress JWT signer.** Issue per-session JWTs that encode allowed egress destinations; the egress proxy ([09-templates.md](./09-templates.md) + [08-networking.md](./08-networking.md)) validates them.
7. **Quota / rate-limit.** Per-tenant concurrent sandboxes, per-tenant request rate.
8. **Audit log.** Structured events: session created/destroyed, template assigned, exec called, egress request, secret rotated. Retention ≥ 90 days. See [10-observability.md](./10-observability.md).

## What L4 must NOT do

- **Spawn sandboxes directly.** It calls L3 providers — never `docker.run` or `kubectl apply`.
- **Hold long-lived sandbox credentials in env.** Secret broker mints them per-session.
- **Trust L1 agents.** L1 is reachable only through L3-managed network paths; L4 ↔ L3 is the only authenticated hop.

## API surface (target)

| Endpoint | Purpose | Notes |
|---|---|---|
| `POST /mcp` | MCP JSON-RPC (initialize / tools/list / tools/call) | Bearer auth; existing contract preserved |
| `GET  /mcp/sse` or `WS /mcp` | Streaming for long tool calls | Today: synchronous HTTP; future: streaming |
| `GET  /healthz`, `/readyz` | K8s probes | Same as today |
| `POST /api/uploads` / `GET /api/files/{path}` | Per-tenant user data I/O | Backed by S3 (Phase 3+) |
| `GET  /system-prompt` | Tenant-scoped system prompt rendering | Same as today |
| `POST /admin/tenants/{id}/keys/rotate` | Force-rotate tenant secrets | Admin-only |
| `GET  /admin/sessions` | List + filter | Admin-only |
| `POST /admin/sessions/{id}/terminate` | Force kill | Admin-only |
| `GET  /admin/templates` / `POST /admin/templates` | CRUD sandbox templates | Admin-only; see [09-templates.md](./09-templates.md) |
| `GET  /admin/audit` | Query audit log | Read-only, append-only store |

The `POST /mcp` contract is **frozen** as the user-facing surface — never break it across phases.

## Internal contracts

- **L4 → L3 (provider):** **connect-go** (gRPC + Connect + HTTP/JSON from one `.proto`), mTLS in production. See [ADR-0008](../adr/0008-internal-grpc-external-rest-mcp.md). Operations: `Spawn(template, tenant_ctx)`, `Configure(handle, ctx)`, `Exec(handle, cmd) → stream<Output>`, `Stop(handle)`, `List(filter) → stream<Handle>`, `Health(handle)`, `Events() → stream<Event>`. See [03-layer3-providers.md](./03-layer3-providers.md).
- **L4 → secret stores:** AWS Secrets Manager / Vault / k8s `Secret` — read at startup + on rotation. Never embedded in container images.
- **L4 → KV (session store):** Redis / Valkey / etcd. Failure mode: lose recent session routing → sessions reconnect (sessions are short-lived). Snapshot for multi-AZ.
- **L4 ↔ user UI (CDP / ttyd):** **WebSocket passthrough** — L4 does **not** parse CDP messages; it consistent-hashes by session ID and shovels frames bidirectionally. Same path for ttyd. See [ADR-0008](../adr/0008-internal-grpc-external-rest-mcp.md) for why.

## External surface — protocol map

| Caller | Protocol | Reason |
|---|---|---|
| User agents / Open WebUI | **MCP** (JSON-RPC over HTTP/WebSocket) | Frozen contract ([ADR-0005](../adr/0005-mcp-as-control-plane-gateway.md)) |
| Admin UI | **REST** (OpenAPI-described) | Standard for SPAs, browser-debuggable |
| User UI CDP / ttyd | **WebSocket** passthrough | Long-lived binary streams, opaque to L4 |
| Internal L3 / pool-manager | **connect-go** mTLS | Schema-first, typed, streaming-native |

MCP semantics live **only** in the gateway layer of L4. It translates MCP `tools/call` into typed connect-go calls on the provider. L1 agents do not speak MCP — they speak connect-go.

## Admin UI

- **Scope (MVP, Phase 6):** session list with kill button, template editor, audit log viewer, secret rotation trigger.
- **Stack:** stays unconstrained at the L4 doc level. Likely SPA against the admin REST API. To be designed in a separate `admin-ui.md` once Phase 6 starts (per the per-phase research cadence).
- **Auth:** OIDC, separate role from end-user.

## Deployment shapes

| Shape | When | Notes |
|---|---|---|
| Single binary alongside Compose | PoC, dev (Phase 6 development) | Replaces today's `computer-use-server` container 1:1 |
| `Deployment` in k8s, HPA on RPS | Production single-region (Phase 6 prod) | Stateless; KV holds session state |
| Multi-AZ + multi-region | Phase 10 | KV replicated cross-AZ; sticky routing via consistent hashing in L4 (see anti-pattern note below) |

> **Anti-pattern — never use `Service.spec.sessionAffinity: ClientIP`.** It pins on source IP, which in our deployments is the ingress controller's IP (every client looks the same). The result is a single replica receiving 100% of CDP/ttyd WebSocket traffic. Stickiness for long-lived sessions belongs in L4's session router (consistent-hash by `session_id`), not in the Service. Document this in the Helm chart values; refuse the field in any operator template.

## HA upgrade strategy

L4 is stateless at the request level (KV holds session state), but **CDP / ttyd WebSockets are long-lived** and a rolling rollout that kills the replica owning a session terminates that session's UI. The upgrade procedure:

1. **Scale-to-1, migrate, scale-up** is the safe baseline for single-region:
   - Scale the new revision in.
   - Drain the old revision: stop accepting new sessions; existing sessions remain bound until they end naturally or until the drain timeout (default 30 min, capped at the longest active CDP session).
   - Migrate the session router KV (no-op when KV is external; explicit hand-off when KV is co-located).
   - Scale the old revision to zero.
2. **Blue-green** (preferred for production):
   - Stand up the new revision behind a sibling Service.
   - Switch the L4-fronting ingress route atomically.
   - Old revision keeps existing sessions; new sessions go to the new revision.
   - Old revision drains and is deleted after the drain window.
3. **Never** roll L4 with a vanilla Kubernetes `RollingUpdate` against the same Service while WebSocket sessions are bound. The default kills sessions mid-stream.

Phase 6 ships the scale-to-1 procedure as a Helm `pre-upgrade` hook. Phase 10 adds the blue-green topology once multi-region session affinity is in place.

## Prompt-caching position (Anthropic API gateway role)

L4 sits between LLM clients and the Anthropic API in deployments that route through us. Prompt caching is part of the Anthropic API contract; **L4 must forward the relevant headers and request blocks transparently, not strip or rewrite them**. Specifically:

- The `anthropic-beta: prompt-caching-*` header is set **only** when the client requested it. L4 does not opportunistically add it.
- `cache_control` blocks inside the request body pass through unchanged.
- Response headers reporting cache hit/miss metrics pass back unchanged.
- L4 never inserts or removes `cache_control` markers — that is the client's call. We are a router, not a prompt optimizer.

This matters because Open WebUI and other clients increasingly use caching to amortize long system prompts. A naive proxy that rewrites the body breaks the cache and inflates token bills silently. The L4 implementation has integration tests asserting byte-identical round-trip for cached request shapes.

Phase 6 research locks the exact list of headers and request fields treated as opaque; Phase 6 implementation enforces it.

## Migration from today's FastAPI

- **Phase 1–5:** stay in Python; refactor L3 calls behind a provider interface but `app.py` remains the entrypoint.
- **Phase 6 (cutover):** new Go service stood up alongside; reverse proxy splits traffic by route; Python service decommissioned once parity is reached and admin UI is migrated.
- **Compatibility:** Go service MUST accept the exact existing MCP request shape on day 1 — verified by reusing `tests/integration/test_mcp_auth.py` and `test_mcp_tools.py` against the new endpoint.

## Open questions (deferred to Phase 6 research)

- **Web framework:** stdlib `net/http` vs `chi` vs `gin` vs `connect-go` (for gRPC+HTTP unified). Decide in `phase-6-research.md`.
- **KV choice:** Redis (familiar) vs Valkey (Redis-OSS fork) vs etcd (already in k8s). License sensitivity per [ADR-0006](../adr/0006-no-agpl-no-bsl-dependencies.md).
- **MCP server library:** roll our own JSON-RPC vs adopt an SDK once mature for Go.
- **Streaming transport:** SSE vs WebSocket vs HTTP/2 streaming.

These are not blockers to Phases 1–5.
