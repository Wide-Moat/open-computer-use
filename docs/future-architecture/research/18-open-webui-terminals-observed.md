<!-- SPDX-License-Identifier: BUSL-1.1 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# 18 — Open WebUI `open-terminal` + `terminals` (observed)

> Source: [`open-webui/open-terminal`](https://github.com/open-webui/open-terminal) (sandbox shell server) and [`open-webui/terminals`](https://github.com/open-webui/terminals) (per-user orchestrator). Reviewed 2026-05.
>
> Status: **observation, hypothesis only.** Their target audience is single-user / SMB self-host. Our target is multi-tenant enterprise (financial-sector infosec, multi-cluster, BYOK, compliance-grade audit). This document records what they do at the wire-protocol level, and frames one open hypothesis about reusing that wire protocol as an external dialect — nothing here locks any architectural decision.

## 1. What the two projects are

- **`open-terminal`**: a FastAPI service that runs inside a single container and exposes a REST API + WebSocket terminal. Tools: bash exec, file CRUD, document extraction, port reverse-proxy, Jupyter kernels, optional in-process MCP via `FastMCP.from_fastapi(app)`.
- **`terminals`**: a separate FastAPI control-plane that provisions one `open-terminal` container *per `(user_id, policy_id)`* and reverse-proxies requests to it. Three backends: Docker socket, Kubernetes direct, Kubernetes via Kopf operator + `Terminal` CRD (`openwebui.com/v1alpha1`).

Open WebUI integrates both natively. The backend (`backend/open_webui/routers/configs.py:277-323`) auto-detects which one the user pointed at:

```text
GET {url}/api/v1/policies → 200 → server_type = "orchestrator"  (terminals)
GET {url}/api/config      → 200 → server_type = "terminal"      (open-terminal)
```

For an orchestrator, requests are routed as `/p/{policy_id}/{path}`. For a single terminal, paths pass through as-is.

## 2. Audience and scope difference

This is **not a critique** — these are different products solving different problems.

| Dimension | Open WebUI stack | Our target |
|---|---|---|
| Primary user | Self-hoster, single-team install | Multi-tenant enterprise, paid SaaS |
| Tenancy boundary | Linux UID inside one container (multi-user mode) or one container per user (orchestrator) | One sandbox per session, microVM-isolated for untrusted tier |
| Runtime isolation | `runc` only | runc / sysbox / gVisor / kata-fc / kata-ch per template ([04-layer2-runtimes.md](../architecture/04-layer2-runtimes.md)) |
| Cluster model | Single cluster, single namespace | Multi-cluster, multi-AZ, federated |
| Identity | Static API key or Open WebUI JWT | OIDC + per-session JWT + secret broker ([07-security.md](../architecture/07-security.md)) |
| Secrets | env vars / K8s `Secret` | Per-session STS, key rotation ≤90d without restart |
| Egress | iptables + dnsmasq inside each container | Centralized JWT-allowlist egress proxy with audit pipeline ([08-networking.md](../architecture/08-networking.md), Phase 8) |
| Storage | `/home/user` bind-mount or PVC | 4-tier (image / squashfs skills / ephemeral workspace / S3 user-data) ([06-storage.md](../architecture/06-storage.md)) |
| Audit | SQL `audit_log` table | Append-only S3 with object-lock, ≥90d retention |
| HA control plane | Single process, in-memory `_instances` dict | 3+ replicas, leader election via `coordination.k8s.io/Lease`, external KV |
| Compliance posture | None specifically targeted | SOC2 / PCI / FedRAMP-class workloads in scope |

Their stack would be a regression for our targets. Ours would be over-engineering for theirs. Both can be correct.

## 3. Wire contract (what Open WebUI expects)

Useful to record verbatim because the protocol is what unlocks native integration in Open WebUI's UI.

### 3.1 Auto-detection probes

```text
GET /api/v1/policies          → orchestrator dialect
GET /api/config               → single-terminal dialect, returns { features: { terminal: bool } }
```

### 3.2 Orchestrator dialect (used by `terminals`)

- `GET /api/v1/policies` — list policies (`PolicyData`: image, env, cpu_limit, memory_limit, storage, storage_mode, idle_timeout_minutes)
- `POST/PUT/DELETE /api/v1/policies/{id}` — CRUD from admin UI
- `ALL /p/{policy_id}/{path:path}` — reverse-proxy to the provisioned sandbox; `X-User-Id` header required; orchestrator resolves `(user_id, policy_id) → sandbox`, replaces auth with the sandbox's internal API key, streams body bidirectionally
- `WS /p/{policy_id}/api/terminals/{session_id}` — WebSocket proxy with first-message `{"type":"auth","token":"..."}` handshake

### 3.3 Single-terminal dialect (used by `open-terminal`)

The endpoints under `/p/{policy_id}/` in orchestrator mode are exactly the endpoints `open-terminal` exposes at root. Open WebUI clients used by the UI:

- `GET /openapi.json` — OpenAPI 3.0 spec; tools from this spec are surfaced to the model as function-calling tools
- `GET /files/cwd`, `POST /files/cwd` — session-scoped CWD (keyed on `X-Session-Id`)
- `GET /files/list?directory=`, `GET /files/read?path=`, `GET /files/view?path=`
- `POST /files/upload?directory=` (multipart), `POST /files/mkdir`, `DELETE /files/delete`, `POST /files/move`, `POST /files/archive`
- `POST /api/terminals` → `{ id }`; then `WS /api/terminals/{id}` with first-message auth, binary frames for PTY I/O, JSON `{type:"resize",cols,rows}` / `{type:"ping"}` for control

All HTTP requests authenticated by `Authorization: Bearer <key>`; `X-Session-Id` keys per-chat state; `X-User-Id` keys per-user provisioning in orchestrator mode.

### 3.4 What Open WebUI gives back if a server implements this

- **`FileNav.svelte`** — full file browser in the chat sidebar (list, read, upload via drag-drop, download, mkdir, delete, move, archive)
- **`XTerminal.svelte`** — embedded xterm.js with the WebSocket protocol above
- **Tool calling** — OpenAPI tools auto-injected into the inference loop when the model has `capabilities.terminal = true`
- **`AddTerminalServerModal.svelte`** — admin / per-user UI to add a server, with orchestrator-mode policy editor
- **Per-chat `X-Session-Id`** — Open WebUI passes the chat id automatically, sandboxes can scope CWD and state to a session

## 4. Hard constraint: client parity

Current explicit requirement: **Open WebUI and n8n must reach an identical capability surface** so that skills are portable between clients. The MCP protocol is the only common denominator across the target clients today (Open WebUI MCP support, n8n MCP nodes, OpenAI Agents SDK, LiteLLM, Claude Desktop). See [`../../MCP.md`](../../MCP.md), [`../../COMPARISON.md`](../../COMPARISON.md).

This constraint **takes precedence** over any UX gain from native Open WebUI integration. Anything that splits the skill surface — i.e. tools that work in Open WebUI but not in n8n, or vice versa — is rejected by definition. ADR-0005 (MCP as user-facing control-plane gateway, frozen contract) stands.

## 5. Hypothesis (open, not decided)

Add an **external protocol dialect** to L4 that speaks the orchestrator wire contract from §3.2 alongside the primary MCP endpoint, while internal tool execution stays MCP-shaped end-to-end.

```text
                  ┌─── /mcp                        primary, frozen          (n8n, Claude Desktop, LiteLLM, OpenAI Agents)
L4 (Go) ──────────┼─── /api/v1/policies, /p/...    Open WebUI native UX     (FileNav, XTerminal, OpenAPI tools)
                  ├─── /v1/chat/completions        OpenAI-compat            (future, for OpenAI-API consumers)
                  └─── /admin/*                    operator UI
```

All four are adapters over the same internal connect-go RPC ([ADR-0008](../adr/0008-internal-grpc-external-rest-mcp.md)).

### What this would unlock

- Open WebUI users get the native file browser + embedded terminal + OpenAPI-tool injection out of the box, without our `computer_link_filter` and Open WebUI source patches.
- No regression for n8n / Claude Desktop / LiteLLM — they keep using `/mcp` unchanged.

### What still has to be proven before this becomes decision-grade

1. **Skill parity check.** The Open WebUI dialect would deliver tools via OpenAPI 3.0, not MCP `tools/call`. We have to confirm that for every skill we ship, the OpenAPI representation and the MCP representation produce identical model behaviour. If not, the dialect splits the skill surface and §4 forces rejection.
2. **CDP and live browser viewer.** Open WebUI's terminal dialect has no concept of a Chrome DevTools Protocol stream. Either we extend the dialect with our own WebSocket endpoint under `/p/{policy_id}/devtools/...` (and patch Open WebUI to recognise it — back to the patch-maintenance problem), or we accept that Computer Use's primary fronted-killer feature is unavailable through this path.
3. **`computer_link_filter` value.** Today the filter injects skill descriptions into the system prompt and rewrites output URLs into iframe previews. Open WebUI's native flow injects OpenAPI tool descriptions automatically but does **not** rewrite output URLs. We have to decide whether the URL-rewriting UX is essential — if yes, we still need the filter even when using the native dialect, and the simplification budget shrinks.
4. **State of the contract.** `open-webui/terminals` is at `v0.0.3` with an Enterprise License. Backwards-compat guarantees on the orchestrator wire format are unclear; pinning to a specific Open WebUI version range may be necessary.
5. **`X-Session-Id` semantics.** Open WebUI assumes sessions outlive single requests (CWD persists). Our session model is sandbox-per-chat with a TTL. Confirm the mapping doesn't surprise anyone — e.g. what happens to file ops sent during sandbox cold-start.

### Phase to evaluate

If pursued, this is a Phase 6 concern (L4 rewrite) at the earliest — the adapter lives in L4 and benefits from connect-go's HTTP+JSON pluralism. Not earlier: doing it on top of the current FastAPI server would create migration debt.

## 6. Patterns observed, not borrowed

For completeness, things their code does competently that we should make sure are covered in our own design (these are CNCF / k8s-api-convention basics, not their inventions — listing only to confirm we don't drop them):

- Status `phase` + `conditions[]` array on the CRD (k8s API conventions). Their flat `cpuLimit: "2"` vs nested `resources.limits.cpu` is the opposite — non-standard, breaks generic k8s tooling. **Antipattern note added below.**
- Finalizer-driven teardown (`settings.persistence.finalizer = "..."`) — standard. Required for our S3-cleanup / secret-revocation / egress-JWT-invalidation flows.
- PVC lifecycle separated from CR lifecycle (PVC outlives the controller object). Useful pattern for stateful workloads; **not directly applicable to us** since our default workspace home is ephemeral and persistence is S3-mediated.
- Reverse-proxy with retry on cold-start (5 attempts, 1s backoff) — required behaviour for warm-pool misses; should be explicit in [`03-layer3-providers.md`](../architecture/03-layer3-providers.md) and [`02-layer4-control-plane.md`](../architecture/02-layer4-control-plane.md).

## 7. Antipattern note candidate

For [`../antipatterns.md`](../antipatterns.md):

> **Flat resource fields on a CRD spec.** Using `spec.cpuLimit: "2"` and `spec.memoryLimit: "4Gi"` instead of the canonical `spec.resources.limits.{cpu,memory}` breaks `kubectl explain`, generic policy admission controllers (Kyverno, Gatekeeper templates that target `resources.limits`), and Helm-chart introspection tooling. Save the typing, lose the ecosystem. Always nest under `resources`.

## 8. Summary

`open-terminal` and `terminals` are well-scoped products for a different audience. Their wire protocol is the one piece worth recording for possible reuse as an external dialect of our L4 — strictly as a **hypothesis** subordinated to the MCP-first / client-parity constraint. No architecture commitment is made by this file.
