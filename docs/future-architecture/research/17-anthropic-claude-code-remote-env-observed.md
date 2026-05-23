<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# 17 — Anthropic Claude Code remote environment (reverse-engineered, observed)

> Source: empirical observation of env-var surface inside a live Claude Code remote session, 2026-05.
> Distinct from [`16-anthropic-production-sandbox-observed.md`](./16-anthropic-production-sandbox-observed.md) — that one is the **claude.ai chat sandbox** (ephemeral Firecracker microVM). This one is the **Claude Code remote dev environment**, which is a different product with different trust assumptions: trusted single-user session, not multi-tenant ephemeral.
>
> Status: **observation, not yet decision-grade.** Captures patterns worth folding into our Phase 4 (secret broker), Phase 6 (control plane), and Phase 10 (HA / session migration) research. Locks nothing on its own.

## 1. Observed environment variables

| Variable | Meaning |
|---|---|
| `REMOTE_ENVIRONMENT_TYPE=cloud_default` | Environment is **cloud**, not local. The `default` suffix implies a typed enum: likely `cloud_byo`, `local`, `enterprise`. Type-based routing in the control plane. |
| `CONTAINER_ID` | **Container, not VM.** Big delta vs the chat sandbox (Firecracker). Trust model differs — see §3. |
| `SESSION_ID` + `REMOTE_SESSION_ID` | Two-level session: client-side and remote-side. Decoupled so reconnect / migration can swap the remote worker without losing the client session. |
| `WORKER_EPOCH` | Worker-pool architecture with **reusable** workers. Epoch increments on recycle; client compares to detect "this is a fresh worker, re-initialize". |
| `CLAUDE_CODE_VERSION` + `ENVIRONMENT_RUNNER_VERSION` | **Split deployment:** agent (inside) and runner (outside) versioned independently. Wire protocol stays compatible across mismatched versions. |
| `*_FILE_DESCRIPTOR` (for credentials) | Secrets passed via **FD inheritance** at `fork()/exec()`, not as env vars. The env shows only the FD number, never the secret. |
| `POST_FOR_SESSION_INGRESS_V2` | Outbound URL for events from the env. `V2` = protocol versioning done properly. |
| `WEBSOCKET_AUTH_FILE_DESCRIPTOR` | Bidirectional WebSocket for real-time control. Auth token preloaded into an FD. |

## 2. Architecture deltas vs the chat sandbox

### 2.1 Container, not VM

`CONTAINER_ID` + no Firecracker markers → container runtime (likely runc, possibly gVisor; this is consistent with managed-container hosting platforms). Different from the claude.ai sandbox (Firecracker microVM).

Justified because the trust model is different:
- **Claude Code remote:** single trusted user, authenticated session, user's own workload. Container isolation is adequate.
- **Claude.ai sandbox:** ephemeral, multi-tenant, runs arbitrary code from arbitrary chats. KVM boundary required.

### 2.2 Worker pool, not ephemeral spawn

`WORKER_EPOCH` is a hallmark of warm-pool / long-lived worker patterns (cf. AWS Lambda provisioned concurrency, gRPC long-lived streams). Sessions don't pay cold-start cost on every interaction; the client can detect when its worker has been recycled and reset state.

### 2.3 Bidirectional channel = WebSocket in + POST out

Not one symmetric gRPC stream. Two channels, each optimized for its traffic shape:
- **WebSocket inbound** → tool-call dispatch (low-latency, interactive)
- **POST outbound** → events to control plane (batched, durable, audit/telemetry/session state)

Each channel scales independently.

## 3. The FD-passing pattern — why it matters

The most interesting pattern, worth excerpting in full.

### Problem with env-var secrets

- Any process able to read `/proc/<pid>/environ` sees the token. On shared-kernel multi-tenant hosts this is a real risk even without root.
- Child processes inherit env by default. Run `python` → it sees the token in `os.environ`, can log it, send it to Sentry, dump it in a crash report.

### FD inheritance instead

- FD is passed only to specific children via explicit `fork() + exec()`.
- `/proc/<pid>/environ` shows the FD **number**, not its contents.
- Child reads contents once at startup, then closes the FD; secret lives in memory only.
- Parent can revoke access by closing its end.
- Well-trodden pattern: systemd socket activation (`LISTEN_FDS`), sshd, journald.

### Concrete shape (inferred)

```text
runner opens /run/secrets/oauth-token (mode 0600)
  → fork()
  → child inherits FD (e.g. number 3)
  → exec() with CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR=3 in env
  → child: token = os.read(3, ...); os.close(3)
  → token never appears in env, argv, or filesystem-readable form to other procs
```

## 4. Patterns we should fold into our design (research-grade, NOT locked yet)

Each item below is a candidate addition to a specific upcoming phase research pass. None are amendments to current ADRs.

| # | Pattern | Target phase to evaluate | Currently in our design? |
|---|---|---|---|
| 1 | Independent SemVer for **wire protocol** vs **binaries** (agent and runtime versioned separately) | Phase 6 (Go control plane) and Phase 7 (Go guest agent) | No — implicit assumption is co-versioning |
| 2 | **Worker pool with epoch** as opt-in mode beside ephemeral spawn (`session_mode: ephemeral \| pooled`) | Phase 2 (HTTP sandbox pool) and Phase 10 (HA) | Partially — Phase 2 ships warm pool, but no `WORKER_EPOCH`-style client-side recycle detection |
| 3 | **FD-passing for credentials** (no secrets in env / argv / filesystem readable to other procs) | Phase 4 (secret broker) | No — current sketch passes per-session STS tokens via env. This pattern hardens it. |
| 4 | **Two-level session IDs** (`SESSION_ID` client-side, `REMOTE_SESSION_ID` worker-side) for reconnect / migration / multi-region failover | Phase 6 (control plane) and Phase 10 (multi-region) | No — single session ID assumed |
| 5 | **Asymmetric transport split:** WebSocket inbound (interactive) + POST outbound (durable event stream) | Phase 6 (control plane) and Phase 9 (audit pipeline) | Partial — [ADR-0008](../adr/0008-internal-grpc-external-rest-mcp.md) says WS passthrough for CDP/ttyd; doesn't address event stream direction explicitly |
| 6 | **Typed environment enum** (`REMOTE_ENVIRONMENT_TYPE=cloud_default \| cloud_byo \| local \| enterprise`) so the control plane can route per type | Phase 6 (control plane) | No — current sketch is provider-typed, not environment-typed |

## 5. What this observation does NOT change

- No ADR amendments. Each item above goes into its target phase's research file as a candidate, and gets a yes/no decision there.
- Storage Tier 4 baseline (rclone+VFS, locked in `06-storage.md`) is unrelated — Claude Code remote env has its own storage shape that we did not observe in this session.
- Our trust model. We're closer to claude.ai (multi-tenant ephemeral) than to Claude Code (trusted single-user), so container-only isolation as in §2.1 is **not** transferable; our `untrusted` tier still needs microVM per [ADR-0004](../adr/0004-pluggable-runtime-via-runtimeclass.md).
- 4-layer model. The Claude Code split (runner outside / agent inside) maps cleanly onto our L3 (provider) / L1 (guest agent).

## 6. Why this is worth keeping around

The FD-passing pattern alone is a strong artifact for any future security / compliance review of our design. Pointing at "this is how Anthropic does it in production for Claude Code" carries weight in infosec conversations that an abstract argument doesn't. Capture it now so it's available when Phase 4 (secret broker) research starts.
