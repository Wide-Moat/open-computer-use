# 09 — Michaelliv/agentbox (egress proxy reference)

> Source: [`references/agentbox/`](../../../references/agentbox/). Python asyncio reference for JWT-allowlist egress proxy. Companion blog: https://michaellivs.com/blog/sandboxed-execution-environment/.
> Direct input for [Phase 8](../roadmap.md).

## 1. JWT — HS256, allow-list as comma-delimited claim

- **Where.** `agentbox/sandbox_manager.py:133-165`.
- **Shape.**
  ```
  Header:  {"typ":"JWT","alg":"HS256"}
  Payload: {
    "iss":"sandbox-egress-control",
    "session_id":"uuid",
    "tenant_id":"optional",
    "allowed_hosts":"pypi.org,github.com,*.example.com",
    "exp": now + 4h
  }
  Signature: HMAC-SHA256(header.payload, signing_key)
  ```
- **Why for us (Phase 8 MVP).** Stateless; proxy verifies signature + expiry, no DB round-trip. 4-hour `exp` matches our session-lifetime cap ([pattern 16 in `00-anthropic-and-sandboxd.md`](./00-anthropic-and-sandboxd.md)).
- **Production note.** HS256 = shared symmetric key — works when proxy + L4 are colocated. For untrusted-host scenarios switch to **RS256** with public-key distribution (proxy only needs the public key).

## 2. Allowlist matching — wildcard suffix + port stripping

- **Where.** `agentbox/egress_proxy.py:130-151`.
- **Semantics.**
  - Exact match: `"github.com" == "github.com"`.
  - Wildcard suffix: `"*.github.io"` matches `"user.github.io"` AND `"github.io"` itself.
  - Port stripped: `"pypi.org:443"` → `"pypi.org"`.
- **Footguns.**
  - No IP-literal blocking (allowlist is hostname-only).
  - `*.com` matches **any** `.com` — relies on admin discipline.
  - No double-wildcard (`**.example.com` not supported).
- **Port to Go.** `strings.HasSuffix`. Add RFC-1123 validation to reject malformed entries.

## 3. CONNECT proxy (HTTPS) — bidirectional pipe

- **Where.** `agentbox/egress_proxy.py:153-222`.
- **Flow.** Client `CONNECT host:port HTTP/1.1` → proxy verifies host + token → `200 Connection Established` → two asyncio tasks pipe 8KB chunks both ways until EOF.
- **Why for us.** Phase 8 — HTTPS is opaque to L7 inspection; CONNECT is the only practical path.
- **Production gaps.** No timeout on pipe (slow upload hangs forever). No bytes-transferred audit. No rate-limit. Exceptions silently close (no detail to client).

## 4. HTTP proxy (non-HTTPS) — Host-header filter + header sanitization

- **Where.** `agentbox/egress_proxy.py:224-292`.
- **What.** Parses request URL (HTTP/1.1 absolute-form), validates host, strips `Host`, `Proxy-Authorization`, `Proxy-Connection`, forwards request body verbatim. Returns full response (no streaming — loaded in memory).
- **Why for us.** Phase 8 fallback for plaintext HTTP (rare but possible). Skip the in-memory load for production — use streaming.

## 5. Proxy auth wire format — `Basic base64(sandbox:jwt_<token>)`

- **Where.** `agentbox/egress_proxy.py:91-113`.
- **Container wire-up.**
  ```
  HTTP_PROXY=http://sandbox:jwt_<token>@proxy_host:15004
  HTTPS_PROXY=http://sandbox:jwt_<token>@proxy_host:15004
  ```
- **Why for us.** Phase 8 — sandbox just sets env vars; any HTTP client (curl, requests, urllib, npm, pip) picks it up automatically. The `jwt_` prefix distinguishes from password auth.
- **Production note.** Proxy URL over cleartext is a vulnerability across untrusted networks. Phase 8 MVP runs proxy on loopback; production puts proxy behind mTLS or a Unix socket if cross-network.

## 6. Session lifecycle — JWT on session create, no refresh

- **Where.** `agentbox/sandbox_manager.py:167-178` + `:254-320`.
- **Flow.** `CreateSession(allowed_hosts=[...])` → `_generate_proxy_jwt()` → `_generate_proxy_url()` → injected into container's `HTTP_PROXY`.
- **Why for us.** Phase 8 — token expires with session; no refresh needed at <1 K concurrent sessions.
- **Limitation.** Container outliving 4-hour token → silent network fails. For long sessions, add a `/refresh` endpoint that mints a new JWT from existing session_id.

## 7. Audit logging — stderr only, unstructured

- **Where.** `agentbox/egress_proxy.py:173, 256`.
- **Today.**
  ```
  logger.info(f"Proxying CONNECT to {host}:{port}")
  logger.info(f"Proxying {request.method} to {url}")
  logger.warning(f"Blocked CONNECT to {host}:{port}")
  ```
- **Gaps for our Phase 8.**
  - No request ID / correlation across proxy + container.
  - No bytes transferred / latency.
  - `tenant_id` in JWT but **not logged** — we must add it for multi-tenant audit.
  - Blocked = log host but not reason (typo vs. missing entry).
- **Target.** Structured JSON: `{ts, session_id, tenant_id, target, port, verdict, reason, bytes_out, latency_ms, jwt_id}` → ship to immutable audit sink (matches `00-anthropic-and-sandboxd.md` pattern 10).

## 8. Signing-key management — `secrets.token_hex(32)`, in-process

- **Where.** `agentbox/sandbox_manager.py:76-86`.
- **Today.** Auto-generated 256-bit hex if not provided via `SIGNING_KEY` env. Both manager + proxy must share it (loopback).
- **Gaps.** No rotation; no versioning (rotation invalidates all live tokens); symmetric key compromise = total proxy compromise.
- **Phase 4 + 9.** Source from our secret broker; rotate ≤ 90 d; consider RS256 + `kid` header for graceful rotation (old + new public keys overlap).

## 9. DNS — client-driven (proxy trusts container's resolution)

- **Where.** `agentbox/egress_proxy.py:176-177` — `asyncio.open_connection(host, port)` uses OS resolver.
- **Implication.** Allowlist is hostname-based. **DNS rebinding** theoretically possible but mitigated because the client is *inside our sandbox* (we control its resolv.conf).
- **For Phase 8 research.** Decide: trust container DNS (simpler) vs proxy-resolves-itself (defends against rebinding). E2B's three-port pattern ([`02-e2b-infra.md`](./02-e2b-infra.md) §6) is an orthogonal axis.

## 10. Streaming perf

- **Where.** `agentbox/egress_proxy.py:191-205`. 8 KB chunks, `await writer.drain()` for backpressure.
- **Scale.** Single Python process handles ~1 K concurrent CONNECT tunnels. Per-tunnel saturates network bandwidth. CPU mostly idle.
- **Go port wins.** Goroutines lighter than asyncio tasks → 10× concurrency. `io.Copy` (or `io.CopyBuffer` for chunk control). Add `TCP_NODELAY` for latency-sensitive paths.

## Porting checklist (Python → Go for production)

| Pattern | Today | Go equivalent | Production-ready? |
|---|---|---|---|
| JWT HS256 sign/verify | `hmac.new(..., sha256)` | `crypto/hmac` + `crypto/sha256` | ✓ (also add RS256) |
| JWT lib | manual b64 + check | `github.com/golang-jwt/jwt/v5` | ✓ |
| Wildcard match | `endswith` | `strings.HasSuffix` | ✓ |
| CONNECT tunnel | asyncio bidi | goroutine pair + `io.Copy` | ✓ (add timeout) |
| HTTP proxy | aiohttp | `httputil.ReverseProxy` | ✓ |
| Basic-auth parse | `base64.b64decode` | `encoding/base64` | ✓ |
| Session lifecycle | 4h, no refresh | Same + add `/refresh` | ✓ |
| Logging | stderr | `zap` / `slog` JSON | ⚠ add structured |
| Signing key | `secrets.token_hex` | `crypto/rand` | ✓ (rotate via KMS) |
| DNS | OS resolver | OS resolver (or `net.Resolver`) | ✓ |

## Production gaps to close in Phase 8

1. **Token refresh endpoint** for sessions > 4 h.
2. **Structured audit logging** → immutable sink with 90 d retention.
3. **Per-tenant rate limiting** (token bucket).
4. **RS256** alongside HS256.
5. **Timeouts** on CONNECT pipes.
6. **Graceful shutdown** that drains in-flight tunnels.
7. **mTLS or Unix socket** for proxy access — never cleartext across networks.

## Phase-9 strategy (locked)

- **MVP**: keep agentbox in place — Python, HS256, 4 h JWT, simple allowlist.
- **Port to Go** *after* MVP proves the JWT/allowlist semantics. Target: same wire format; bug-for-bug compatible token format so sandboxes don't have to change.
- **Compose with E2B's three-port firewall** (see [`02-e2b-infra.md`](./02-e2b-infra.md) §6) — they're complementary: agentbox authorizes (who can egress where); E2B-style firewall filters protocols (no protocol confusion on non-HTTP ports).
