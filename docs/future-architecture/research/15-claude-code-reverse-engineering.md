<!-- SPDX-License-Identifier: BUSL-1.1 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# 15 — Claude Code Web reverse-engineering (Anthropic-specific extras)

> Source: [`references/reverse-engineering-claude-code-antspace/`](../../../references/reverse-engineering-claude-code-antspace/). AprilNEA's binary analysis; companion to [`sandboxd/docs/comparison.md`](../../../sandboxd/docs/comparison.md).
> **This doc covers Anthropic-specific details NOT already in [`00-anthropic-and-sandboxd.md`](./00-anthropic-and-sandboxd.md)** — cross-reference, don't duplicate.
> Relevant to Phases 6 (Go control plane) and 7 (Go guest agent).

## 1. Wire protocol — WebSocket with hybrid text+binary framing

- **Where.** `process_api_wire_protocol.md:100-157`.
- **What.** `process_api` mixes text JSON for control + binary frames for stdio:
  - Server → client: `{"ExpectStdOut": null}` (text) → `[binary bytes]` (WS binary frame)
  - Client → server: `{"ExpectStdIn": null}` (text) → `[binary bytes]` (binary frame)
  - End: `{"StdOutEOF": null}` (text)
- **Why for us.** Phase 7 — **adopt** this exact framing in our L1 agent. Cleaner than gRPC bidi for CDP + screencast + streaming exec; better error recovery; easier to proxy and debug.

## 2. Dual-port API — process (2024) + control (2025/vsock)

- **Where.** `process_api_wire_protocol.md:169-186`.
- **What.** `process_api` exposes **two** endpoints:
  - **Port 2024 (TCP):** WebSocket process lifecycle (exec, reattach, streaming).
  - **Port 2025 (TCP) or vsock:** HTTP control API: `/mount_root`, `/auth_public_key`, `/fs_sync`, `/shutdown`.
- **Why.** Control API can reconfigure the guest (rotate JWT key, mount new FS) **without disrupting active process streams**.
- **For us.** Phase 6+7. Our L1 agent should expose the same split: data-plane WS port + control-plane HTTP port. Already implicit in [`05-layer1-guest-agent.md`](../architecture/05-layer1-guest-agent.md) — make it explicit.

## 3. Snapstart — minimal template + deferred mount + multi-mode boot

- **Where.** `snapshot_architecture.md:6-183` (dmesg evidence `:12-32`, mount hierarchy `:130-142`).
- **Three boot modes observed.**
  1. **Snapstart (deferred mount):** Initramfs empty of config; `POST /mount_root` over vsock supplies config post-restore.
  2. **Fresh boot (full init):** Initramfs ships with `/mount_config.json`.
  3. **Snapstart with vsock control:** Most flexible — config delivered after restore.
- **Evidence.** ext4 image mount count = 11 (multi-session reuse); kernel timestamp shows 48.5-hour gap (snapshot/restore cycle).
- **Why.** Snapstart hides 50–200 ms re-init per session (cache drop, remount, clock fixup) while keeping template at ~30 s boot. Trade: cold-template cost once every ~2 days for fast restore per connect.
- **For us.** Phase 10+ snapshot strategy. The **`POST /mount_root` over vsock** pattern informs our L1 mount contract today (Phase 7).

## 4. Baku — environment-type dispatch + auto-Supabase

- **Where.** `baku-analysis.md:6-408`. Symbols: `internal/envtype/anthropic/*.go`.
- **What.** `environment_type = "baku"` boots a specialized environment with:
  - Vite project template copied to `/home/claude/project`.
  - Auto-provisioned Supabase DB (creds in `.env.local`); Supabase MCP server with 6 tools.
  - Vite dev server auto-started via supervisord.
  - Antspace as default deploy target.
  - Stop hook validates Vite errors + TS types + uncommitted changes.
- **Why for us.** Phase 6+ — the **environment-type dispatch** pattern. Not monolithic "Claude Code" but pluggable environment types. Our control plane should support similar specialization (e.g. `computer-use`, `code-exec`, `data-analysis` tiers map to different templates + bootstrap hooks).

## 5. Antspace — 3-phase NDJSON streaming deploy

- **Where.** `antspace-analysis.md:52-170`.
- **Protocol.**
  1. POST → create deployment → get id.
  2. multipart POST → upload `dist.tar.gz`.
  3. GET (streaming) → NDJSON status: `{"status":"packaging|uploading|building|deploying|deployed","url":...,"error":""}`.
- **Auth.** Bearer + dynamic control-plane URL, both injected via session startup JSON (`antspace_deploy` auth type).
- **vs Vercel.** Antspace builds **locally in the env**, uploads artifact, deploys. Streams progress (better UX than polling).
- **For us.** Phase 6+ deployment-target integration model. Use as design reference; we'd substitute Vercel / Netlify / generic S3 artifact store. Antspace itself is closed-source — don't try to integrate.

## 6. JWT auth — public-key set at runtime, optional handshake

- **Where.** `process_api_wire_protocol.md:17-20, 182-183`.
- **What.** WS handshake accepts optional JWT (text frame). Server validates against an asymmetric public key set via `POST /auth_public_key`. Claims: `{sub, iat, exp}` minimal or 5-field full.
- **If no key loaded:** JWT accepted without verification — useful during bootstrap.
- **For us.** Phase 6-7. Interesting **counter-pattern to our "no auth at L1"** rule ([pattern 18 in `00`](./00-anthropic-and-sandboxd.md)). Anthropic does add agent-level JWT auth as **defense-in-depth on top of network isolation**. We should reconsider for TCP-exposed agents; vsock/localhost-only agents can keep "trust the network".

## 7. Go monorepo by **domain**, not by layer

- **Where.** Inferred symbols: `internal/tunnel/actions/deploy/antspace.go`, `internal/envtype/anthropic/*.go`, `internal/mcp/servers/supabase/*.go`.
- **Pattern.** Flat `internal/` with subdirs by **functional domain** (tunnel, envtype, mcp, …), not by layer (api/, agent/, orchestrator/).
- **For us.** Phase 6 layout. Adapt to `internal/session/`, `internal/auth/`, `internal/broker/`, `internal/provider/`, `internal/mcp/` etc. Avoids the "api/ layer has everything" god-package antipattern. Compare with [coder's layout](./03-coder.md) §10 — both converge on domain split.

## 8. Session-scoped env vars + mount bindings

- **Where.** `baku-analysis.md:99-106`; `snapshot_architecture.md:130-142`.
- **What.**
  - **Auth context** supplies tokens/URLs at session start.
  - **Env vars** written to `.env.local` (e.g., `SUPABASE_URL`, `SUPABASE_ANON_KEY`).
  - **Block-device mount bindings**: `/dev/vdb` → `/opt/claude-code` (squashfs, ro), `/dev/vdc` → `/opt/env-runner` (squashfs, ro). Swapped at restore time to inject session-specific tooling.
- **For us.** Already aligned with our [`06-storage.md`](../architecture/06-storage.md) per-session mount spec — but the **block-device swap pattern** for tooling is something we hadn't named. Adopt for microVM templates in Phase 9.

## 9. Graceful shutdown — `POST /shutdown` + cgroup cascade

- **Where.** `process_api_wire_protocol.md:226-234` (shutdown flow); `:98` (`ShuttingDown` message).
- **Sequence.**
  1. Control plane → `POST /shutdown` on agent control API.
  2. Agent drops page caches (`/proc/sys/vm/drop_caches`).
  3. SIGTERM to all process group leaders → wait 5 s.
  4. SIGKILL remaining children.
  5. Return `"Shutdown initiated"`.
- WS clients receive `{"ShuttingDown": null}` and can flush buffers.
- **For us.** Phase 7 — formalize this on our L1 control endpoint. Already implicit in PID-1 signal handling ([pattern 17 in `00`](./00-anthropic-and-sandboxd.md)); make it a named API surface so L4 can trigger it cleanly.

## 10. Post-restore security hardening

- **Where.** `snapshot_architecture.md:168-192`.
- **What.** Immediately after snapstart restore:
  - **Kernel CRNG reseed** on VM fork (`random: crng reseeded due to virtual machine fork` in dmesg).
  - `init_on_free=1` kernel param — freed pages zeroed (prevents data leak between sessions reusing same snapshot).
  - `process_api` drops `CAP_SYS_RESOURCE` (prevents OOM-killer manipulation).
- **Why.** Snapshots share template across many sessions. Without these:
  - CRNG without fork-detection → crypto is predictable across sessions.
  - `init_on_free=0` → template pages leak.
  - `CAP_SYS_RESOURCE` held → compromised session manipulates OOM-killer.
- **For us.** Phase 10. **Document as boot-hardening checklist** for snapshot-based templates from day one — easy to miss until it's a CVE.

## Summary: what's new beyond `00-anthropic-and-sandboxd.md`

| # | Pattern | Anthropic-specific | Our phase |
|---|---|---|---|
| 1 | Hybrid text+binary WS framing | `process_api` | 7 |
| 2 | Dual-port API (data/control split) | `process_api` | 6+7 |
| 3 | Snapstart deferred mount via `/mount_root` over vsock | `process_api` | 10, informs 7 contract |
| 4 | Environment-type dispatch (Baku as example) | Baku | 6 |
| 5 | Antspace NDJSON deploy protocol | Antspace | 6 (informational) |
| 6 | JWT at L1 as defense-in-depth | `process_api` | 6+7 reconsider |
| 7 | Go monorepo by **domain** | env-runner | 6 |
| 8 | Block-device swap for session tooling | `process_api` + Baku | 9 |
| 9 | Graceful shutdown `POST /shutdown` | `process_api` | 7 |
| 10 | Post-restore hardening (CRNG, init_on_free, cap drop) | Firecracker + kernel | 10 |

## What we should NOT copy

- **Antspace** is Anthropic-internal, closed source. Use only as design reference; integrate with public deploy targets (Vercel / Netlify / S3 + signed URLs).
- **Baku-specific bootstrap (Vite + Supabase auto-provision)** is product-shaped for Claude Code Web. The **dispatch pattern** is transferable; the specific bootstrap is not.
- **Implied claims from binary analysis are not authoritative** — treat as hints, verify against `sandboxd/docs/` (which is intentional documentation).

## Quotes preserved

- "Antspace is Anthropic's internal application hosting/deployment platform" — no public docs.
- "The ext4 rootfs has been used across 11 sessions, always mounted at `/mnt` before `pivot_root`" — evidence of multi-session template reuse.
- "Baku powers the public Claude Code on the web's project builder" — "zero public documentation under that name".
- "`process_api` does not authenticate. Network layer ensures isolation." — same posture sandboxd documents.
- Snapstart trade-off: "Trade CPU/disk for RAM" — idle sessions suspended to disk, restored on reconnect.
