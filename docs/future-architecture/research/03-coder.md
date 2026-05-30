<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# 03 — Coder (production Go control plane)

> Source: [`references/coder/`](../../../references/coder/). Self-hosted workspace platform — auth, sessions, lifecycle, templates, audit, RBAC, telemetry. Closest production analog for our Phase 6 L4 rewrite.
> Analysis covers AGPL OSS edition (May 2026).

## 1. HTTP bootstrap — Chi router with layered middleware

- **Where.** `coderd/coderd.go:511-1050`.
- **What.** `go-chi/chi/v5` router with deliberate middleware ordering: recovery → request ID (`httpmw.AttachRequestID`) → real-IP → Prometheus → route match → rate limit → CORS → API key extraction.
- **Why for us.** Phase 6. We'll hit 150+ endpoints; Chi's `.Route()` groups + middleware composition scale. Ordering matters — observability before route match so metrics include unmatched paths; auth populates context for later handlers.
- **Skip.** Their swaggo integration and cookie-CSRF (specific to their cookie-auth scheme).

## 2. Auth — dual-mode API key, JWT signing keys rotated in DB

- **Where.** `coderd/httpmw/apikey.go:42-100` (validation config) and `:100-500+` (extraction + role loading). OAuth state JWT: `coderd/userauth.go:50-200`.
- **What.** `PrecheckAPIKey` middleware validates early; `ExtractAPIKey` loads session lazily. Tokens in cookie (browser) or `Authorization` header. **No Redis** — sessions are DB rows. Signing keys for OAuth state JWTs are managed in DB by `cryptokeys.StartRotator` (`coderd/coderd.go:588`) — rotation is centralized and zero-touch.
- **Why for us.** Avoids the session-store sync problem in HA L4 deployments. Key rotation pattern directly applicable to our secret broker ([architecture/07-security.md](../architecture/07-security.md)).
- **Skip.** OAuth-provider mode (they act as both consumer and provider), multi-IDP sync. Phase-6 MVP needs only consumer-mode OIDC.

## 3. RBAC — Rego policy + DB role reconciliation + `dbauthz` wrapper

- **Where.**
  - Policy: `coderd/rbac/policy.rego`.
  - Auth check: `coderd/rbac/authz.go:1-100`.
  - Authorizer creation: `coderd/coderd.go:361-365`.
  - Reconciler: `coderd/rbac/rolestore/reconcile.go` (startup-time DB ↔ code sync).
  - DB enforcement: `coderd/database/dbauthz/` wraps every query.
- **Why for us.** Phase 6. Three takeaways:
  1. Policy-as-code in Rego — auditable, testable in isolation.
  2. **Reconcile system roles at startup** — guarantees code/DB consistency.
  3. **`dbauthz` wrapper** — single enforcement point; "you cannot query the DB without auth context". Strong default against accidental data leaks.
- **Skip.** Workspace-sharing ACLs (enterprise), full Rego policy initially (start simple, grow into it). OAuth2 scopes (only if we become a provider).

## 4. Audit log — DB-backed with field-level sensitivity catalog

- **Where.** `coderd/audit.go:1-100`. Field catalog: `enterprise/audit/table.go`. Queries: `coderd/database/queries/auditlogs.sql`.
- **What.** `audit_logs` rows carry structured JSON diffs (before/after) per field. Each field declared `ActionTrack` | `ActionIgnore` | `ActionSecret` — secrets never serialized.
- **Why for us.** Phase 6 + 9. Same DB as system → no sync issues. Field-level sensitivity = mechanical enforcement of our cross-cutting pattern 10 (never log verbatim).
- **Skip.** Real-time export to Splunk/DataDog (Phase 8 may add via separate sink), enterprise retention policies. Start DB-only.

## 5. Workspace lifecycle — provisioner job abstraction

- **Where.** `coderd/workspacebuilds.go:1-100`, `coderd/workspaces.go:897-984`, queries `coderd/database/queries/workspacebuilds.sql`, status: `coderd/provisionerjobs.go`.
- **What.** Workspace create/update/delete = a **provisioner job** row (status: pending/running/succeeded/failed). Watchable over WebSocket; logs + result captured. Actual work delegated to separate provisioner daemons via gRPC.
- **Why for us.** Phase 6. Same shape works for our sandbox spawn/destroy: observable, retryable, decoupled from the L3 provider implementation. Logs persisted = "why did spawn fail?" stays answerable.
- **Skip.** Pre-build caching, Terraform variable interpolation, port-forwarding/SSH (workspace-specific).

## 6. Templates — `Template` + `TemplateVersion` + `ParameterSchema`

- **Where.** `coderd/templateversions.go:1-150`, `coderd/templates.go:1-100`, schemas in `coderd/database/queries/`.
- **What.** `Template` = immutable metadata. `TemplateVersion` = versioned artifact (source + params + timestamp). `ParameterSchema` = validated HCL inputs at creation time.
- **Why for us.** Phase 6, validates our [`09-templates.md`](../architecture/09-templates.md) `SandboxTemplate` versioning approach. Their immutability-per-version pattern is exactly what we propose.
- **Skip.** Dynamic Parameters (runtime-eval), template sharing/RBAC (enterprise), publish workflow.

## 7. Database access — sqlc + `dbauthz` + paired migrations

- **Where.** Queries: `coderd/database/queries/*.sql`. Wrapper: `coderd/database/dbauthz/dbauthz.go`. Wiring: `coderd/coderd.go:374-380`. Migrations: `coderd/database/migrations/` (paired up/down).
- **What.** `.sql` files → `make gen` runs sqlc → typed Go. All access through `Store` interface, wrapped by `dbauthz.New()` enforcing authorization per query. Unauthorized = "not authorized" (no reason leak). Migrations paired = clean rollback.
- **Why for us.** Phase 6. sqlc eliminates a class of runtime SQL bugs. The wrapper pattern is the cleanest implementation of "no DB query without auth context" we've seen.
- **Skip.** `regosql` per-query auth (complex). Start with handler-side authz, then wrap.

## 8. Streaming endpoints — `coder/websocket` lib + custom JSON encoder

- **Where.** `coderd/workspaceagents.go:481-510, 855-870, 1227-1240`.
- **What.** `github.com/coder/websocket` (not gorilla — newer/lighter); accept + wrap with JSON encoder; auto compression + ping/pong negotiation.
- **Why for us.** Phase 6. Direct fit for our CDP / ttyd / MCP-streaming proxying.
- **Skip.** Their DERP mesh (Tailscale-specific), workspace-agent multiplexing.

## 9. CLI ↔ server — REST over HTTP with bearer tokens

- **Where.** `cli/root.go`, `cli/login.go`, SDK: `codersdk/`, server auth: `coderd/httpmw/apikey.go`.
- **What.** CLI is a standalone Go binary calling the **same** REST API as the frontend. Bearer token in `Authorization` header. No custom CLI protocol. SDK in `codersdk/` is importable by third parties.
- **Why for us.** Phase 6. Sane default for future admin CLI — no separate gRPC just for the CLI. Public SDK is a real adoption multiplier.
- **Skip.** `config-ssh` helper, agent connection pooling (workspace-SSH-specific).

## 10. Project layout — flat `cli/`, `coderd/`, `codersdk/`

- **Where.** Repo root.
- **What.**
  - `cli/` — commands.
  - `coderd/` — control plane logic.
  - `codersdk/` — shared request/response types + Go client (importable).
  - Nested under `coderd/` by domain: `rbac/`, `audit/`, `database/`, `httpmw/`, `provisionerjobs/` etc.
- **Why for us.** Phase 6. Directly adoptable layout. Public SDK at `codersdk/` matches our intent to keep the MCP contract first-class.
- **Skip.** `enterprise/` directory (defer the commercial split).

## 11. Testing — `coderdtest.New(t, nil)` harness with real Postgres

- **Where.** `coderd/coderdtest/coderdtest.go:1-150` + helpers.
- **What.** Spawns real Postgres + coderd instance + bootstraps templates/users → returns test client. Table-driven, `t.Parallel()`. Test patterns: create user → workspace → wait for build → assert.
- **Why for us.** Phase 6. Real-DB integration tests catch race/lock/constraint bugs that mocks miss. Matches our existing integration-test posture (commit `7a55968`).
- **Skip.** OIDC mocking, load harness, enterprise-only utilities.

## 12. Secrets — encrypted in DB with key rotation

- **Where.** `coderd/usersecrets.go:1-100`, `coderd/cryptokeys/`, rotator start at `coderd/coderd.go:588`, schema `coderd/database/queries/crypto_keys.sql`.
- **What.** User secrets (API keys, OAuth tokens, env vars) stored encrypted with rotation-aware key. Old keys readable for decryption; new encryptions use latest key. Never logged/exported.
- **Why for us.** Phase 4 (secret broker) + Phase 6. Pattern is directly applicable — single-DB storage, in-process key management, rotation as a background task.
- **Skip.** Azure Key Vault (substitute our chosen secret backend), enterprise export.

## Adoption priority for Phase 6 MVP

1. Chi router + layered middleware (`coderd/coderd.go:500-1050`)
2. API-key middleware with context population (`coderd/httpmw/apikey.go`)
3. sqlc + `dbauthz` wrapper (`coderd/database/dbauthz/`)
4. Simple RBAC (`coderd/rbac/authz.go`) — Rego later
5. DB-backed audit log (`coderd/audit.go`)
6. Provisioner-job abstraction for sandbox lifecycle
7. `coderdtest`-style real-DB integration harness
8. WebSocket streaming via `coder/websocket` (`coderd/workspaceagents.go`)

**Defer to Phase 6.5+.** Multi-IDP sync, OAuth-provider mode, full Rego policies, template-version Dynamic Parameters, multi-key rotation.
