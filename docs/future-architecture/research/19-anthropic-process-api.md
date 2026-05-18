<!-- SPDX-License-Identifier: BUSL-1.1 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# 19 — `process_api` pattern catalogue (Anthropic Claude.ai sandbox reference)

> Reference: pattern notes under [`sandboxd/anthropic/`](../../../sandboxd/anthropic/) describing how Anthropic's Claude.ai sandbox is reported to work — specifically its in-VM Rust supervisor `process_api`.
> Distinct from [`13-anthropic-sandbox-runtime.md`](./13-anthropic-sandbox-runtime.md) (the open-source local Claude Code sandbox, bubblewrap/seatbelt) and from [`16-anthropic-production-sandbox-observed.md`](./16-anthropic-production-sandbox-observed.md) (outside view of the same production system). This file covers the **guest-side supervisor itself** — what `process_api` is, what it speaks, and which of its patterns are worth importing.
>
> Status: **pattern catalogue, not yet decision-grade.** Locks no decisions. Each pattern is tagged Adopt / Adapt / Reject for our roadmap; the actual ADRs land at Phase 7 (L1 rewrite) and Phase 10 (snapshot/resume).

## 1. What `process_api` is

A static-PIE Rust binary (≈ 4.3 MB, Tokio 1.52.2) reported to run **either as PID 1 inside a Firecracker microVM** or as a sidecar in gVisor/runc. It owns the WebSocket transport, all child-process lifecycle, OOM monitoring, JWT auth, and the snapstart hand-off. It is **not** an LLM client — it's a process supervisor with a wire protocol.

Build shape (per the pattern notes under [`sandboxd/anthropic/`](../../../sandboxd/anthropic/)):
```
Size:    ~4.3 MB · static-PIE x86-64 · stripped, type names retained
Class:   Rust + Tokio async; static linkage
```

Crate footprint as described in the same notes — what we'd be pulling in if we cloned the design: `tokio`, `hyper`, `tokio-tungstenite`, `tokio-vsock`, `jsonwebtoken`, `ring`, `clap`, `nix`, `serde_json`, plus zstd. No gRPC, no Connect, no Protobuf — **raw WebSocket frames carrying serde-tagged JSON enums.**

## 2. One protocol, three transports

The CLI surface as catalogued in the pattern notes:

| Transport | Flag | Where it runs |
|---|---|---|
| **TCP** | `--addr 0.0.0.0:2024` | Firecracker (current PID 1 invocation), dev, debug |
| **Unix domain socket** | `--listen-uds <path>` | gVisor / runc local sidecar |
| **UDS (dial-out)** | `--dial-uds <path>` | gVisor host-bridge — `bind()` on gofer paths is unreachable from host, so the guest dials out and the Router on the other side issues the HTTP Upgrade |
| **vsock** | `--listen-vsock-port <port>` | Firecracker, future microVM mode |

The same `handle_ws` accept loop drives all four. Transport choice is operational, not architectural — the protocol does not change.

> **Implication for us.** This is the strongest counter-example to ADR-0008's connect-go-over-vsock lean. Anthropic's production agent runs **raw WebSocket frames** over whatever transport the host offers, not gRPC. See §13 for how we should treat this at Phase 7.

## 3. First-byte dispatch (auth)

The accept loop is reported to peek the first byte and branch on it (catalogued under [`sandboxd/anthropic/`](../../../sandboxd/anthropic/)):

- `'{'` → plain JSON `ProcessConnection` (no auth, dev mode or when no public key is loaded).
- `'e'` → base64-url JWT header (`eyJ…`) → Ed25519 verification using `jsonwebtoken` + `ring`.
- Anything else → hard close.

The JWT's `sub` claim is matched against a `container_name` read at boot from a per-VM metadata file. A token issued for container A cannot be replayed against container B — the binding is per-VM, not per-tenant.

## 4. Capabilities negotiation (V1/V2)

The wire-protocol enum is catalogued as:
```
ConnectionCapabilities { supports_traces, supports_zstd }
ProcessCreated   / ProcessCreatedV2
AttachedToProcess / AttachedToProcessV2
TraceEvent (only if supports_traces was negotiated)
```

The server's first frame advertises capabilities; old clients ignore unknown fields and stay on V1 variants, new clients opt into V2 + zstd + traces. This is how the protocol evolves without breakage — a pattern we don't currently have anywhere in `architecture/05-layer1-guest-agent.md`.

## 5. Control-server endpoints (dual-port API)

The data-plane WebSocket is one socket. A **separate control server** (`--control-server-addr` or `--control-vsock-port`) handles HTTP POSTs that the data plane should not see. As catalogued:

| Endpoint | Purpose | Phase relevance for us |
|---|---|---|
| `POST /mount_root` | Snapstart restore: remount rootfs after host swaps block devices | Phase 10 only |
| `POST /shutdown` | Graceful shutdown signal | Phase 7 (always-on) |
| `POST /auth_public_key` | Hot-reload Ed25519 public key | Phase 7+ (optional) |
| `POST /fs_freeze`, `POST /fs_thaw` | `FIFREEZE` / `FITHAW` ioctls for snapshot consistency | Phase 10 only |
| `POST /write_etc_files` | Inject `/etc/hosts`, CA certs at restore time | Phase 10 only |

> **Implication for us.** Today our Python L1 agent has a single HTTP port. Phase 7 should split into **data-plane (WS) + control-plane (HTTP)** so health, shutdown, and (later) snapshot operations stay out of the user-facing path. See `architecture/05-layer1-guest-agent.md` after the Phase 0.5 polish.

## 6. Process supervision model

Per connection the supervisor owns:
- `WsStreamHandle` — the WebSocket peer, zstd compression, frame buffering.
- `ProcController` — wall-clock + CPU timeouts, signal proxying, state machine.
- `ProcHandle` — the OS child: PID, stdin/stdout/stderr FDs, and the boolean `killed_by_process_api` flag.

Terminal states are mutually exclusive:
```
ProcessExited { code }      // normal exit            (killed_by_process_api = false)
ProcessTimedOut             // wall-clock budget hit  (killed_by_process_api = true)
ProcessCpuTimedOut          // CPU budget hit         (killed_by_process_api = true)
ProcessOutOfMemory          // per-process cgroup OOM (killed_by_process_api = false)
ContainerOutOfMemory        // container-wide OOM     (killed_by_process_api = true)
ShuttingDown                // graceful shutdown
```

The `killed_by_process_api` flag is the audit-correctness primitive: it lets the control plane distinguish "we killed it" from "the kernel killed it" without parsing exit codes.

## 7. Container-wide OOM monitor

A dedicated task polls cgroup memory every `--oom-polling-period-ms` (default 100 ms). The cataloged behaviour:

- Adopts orphans before each memory scan (so reparented zombies don't survive the search).
- Reads fresh memory usage for all processes to find the largest.
- Issues a two-phase kill (signal → wait → escalate) with an explicit timeout.
- Logs both "memory reclaimed" and "timed out after killing" outcomes.

More disciplined than what we have today (Docker's default OOM killer policy).

## 8. Security primitives — what we already match and what we don't

| Primitive | `process_api` does | Our state today |
|---|---|---|
| `--block-local-connections` (refuse 127.0.0.1 + own iface IPs on TCP) | Yes | No — covered by `architecture/08-networking.md` after Phase 8 |
| Vsock CID pin (only host CID may dial) | Yes | N/A until Phase 9 |
| Env-var scrub (`_TOKEN _SECRET _PASSWORD API_KEY`) before fork | Yes (substring filter) | Partial — covered by [antipatterns A1, C8] but not enforced in the agent |
| Drop `CAP_SYS_RESOURCE` post-init | Yes (firecracker-init only) | N/A until Phase 9 |
| `init_on_free=1` kernel cmdline | Yes (per [`16-anthropic-production-sandbox-observed.md`](./16-anthropic-production-sandbox-observed.md) §1) | N/A until Phase 9 |
| CRNG reseed on snapshot restore | Yes (mentioned in production observation) | Deferred — Phase 10 |

## 9. Init sequence (firecracker-init mode)

As catalogued, in order:
1. Parse args.
2. Mount `/proc`, `/sys`, `/dev`, `/dev/pts`; configure networking.
3. Pick rootfs path:
   - Boot-time config file present → fresh boot, mount and pivot.
   - Absent → snapstart wait, accept the host's `POST /mount_root`.
4. `pivot_root` + spawn FUSE daemon for Tier 4 mounts.
5. Load the per-VM `container_name` from a metadata file.
6. Load the auth public key (32 raw bytes, Ed25519).
7. Bind WS listener (TCP / UDS / vsock), bind control server, spawn OOM monitor.
8. Drop `CAP_SYS_RESOURCE`.
9. Install signal handlers; accept loop.

> **Implication for us.** Steps 5–9 are template for our Phase 7 agent boot. Steps 2–4 are template only for Phase 10 (when we ship a microVM tier).

## 10. What's intentionally **not** there

- **No tool definitions.** `process_api` does not know what `bash`, `view_image`, or `sub_agent` are. It exec's whatever the client says. Tools live one layer up.
- **No LLM client.** No `anthropic-sdk`, no model APIs.
- **No persistent state.** No DB, no on-disk session log. The state machine is per-connection in memory; trace events flow out, the agent forgets when the client disconnects.
- **No gRPC, no Protobuf.** Pure WebSocket + serde-tagged JSON enums.
- **No prompt caching, no Anthropic-API awareness at all.** This is a transport, not an agent.

Our Phase 7 L1 agent has more responsibilities than `process_api` (it terminates the MCP server and dispatches MCP tools). The takeaway is **not** "rewrite L1 to be identical to process_api" — it is "borrow these primitives, keep our MCP layer above them."

## 11. Lambda lineage

Two patterns here are direct heirs of AWS Lambda's MicroManager design:
- **Two-tier control:** a host-side Router (analog of Lambda's Worker Manager) issues JWTs, picks placement, talks to the snapshot pool; an in-VM supervisor (analog of Lambda's shim) handles in-VM lifecycle.
- **Snapshot pool of frozen VMs** rather than warm VMs (cheaper at scale — frozen snapshots don't consume RAM).

We are not building Lambda, but the cold-start economics and the two-tier split are the parts to study. See [`references.md`](../references.md) Lambda framing and [`05-firecracker.md`](./05-firecracker.md).

## 12. Diff vs ADR-0008's current direction

ADR-0008 picked **connect-go (gRPC + Connect + HTTP/JSON) on vsock or TCP** for L3↔L1. `process_api` chose **raw WebSocket frames + serde-tagged JSON**. With ADR-0002 now landed on **Rust for L1** (matching process_api's stack: `tokio` + `hyper` + `tokio-tungstenite` + `tokio-vsock` + `ring` + `jsonwebtoken`), the WS-frames pattern becomes the natural fit and connect-go on the L1 side becomes the awkward choice:

| Aspect | connect-go (ADR-0008 as written, Go-era) | process_api WS-frames (our Rust L1 target) |
|---|---|---|
| Schema-first | Yes (`.proto`) | No (Rust enums + `serde`, manual contract) |
| Streaming | Server-streaming, bidi | Native (every connection is bidi) |
| Debuggability | curl-able via HTTP/JSON fallback | Any browser dev-tools |
| Transport over vsock | Works but "well-trodden but not zero-config" (per [`02-layer4-control-plane.md`](../architecture/02-layer4-control-plane.md)) | Trivially — `tokio-tungstenite` over `tokio-vsock` |
| Capabilities evolution | Protobuf field numbers | First-frame negotiation (V1/V2) |
| Binary size | Larger (Connect runtime + Protobuf) | Smaller (just `hyper` + `tungstenite`) |
| Crate ecosystem fit (Rust) | Connect-rust is younger than connect-go; smaller blast radius | First-class: `tokio-tungstenite-0.24.0` is what process_api itself uses |

> **Implication for us.** ADR-0008 is **Go-era**: it picked connect-go partly because the L1 was assumed to be Go. With L1 going Rust, the L3↔L1 leg needs a Phase 7 re-evaluation against the WS-frame option. This file does not amend ADR-0008; the Phase 7 gate language inside ADR-0008 will be tightened to call this out explicitly.

## 13. Adopt / Adapt / Reject

| Pattern | Decision | Phase | Notes |
|---|---|---|---|
| Three-transport-one-protocol WS server | **Adapt** | Phase 7 | We may keep connect-go; the lesson is "transport must not leak into the contract" |
| First-byte JSON-vs-JWT dispatch | **Adapt** | Phase 7+ | Once we add agent-side auth, this is the lightest implementation; before that, accept JSON only |
| Ed25519 JWT bound to `container_name` | **Adopt** | Phase 7+ | Per-VM binding is the right granularity for our threat model |
| Capabilities negotiation (V1/V2) | **Adopt** | Phase 7 | Lets our agent protocol evolve without breaking older sandboxes |
| Dual-port API (data-WS + control-HTTP) | **Adopt** | Phase 7 | Already in the roadmap line 70 deliverable; this is the template |
| Control-server endpoints (`/shutdown`, `/healthz`) | **Adopt** | Phase 7 | Always |
| Control-server endpoints (`/mount_root`, `/fs_freeze`, `/write_etc_files`) | **Adopt** | Phase 10 | Only when snapshot tier lands |
| `killed_by_process_api` flag for audit correctness | **Adopt** | Phase 7 | Cheap to add, removes ambiguity in audit log |
| Two-phase OOM monitor with orphan adoption | **Adopt** | Phase 7 | Replaces our reliance on Docker's default policy |
| Env-var scrub on substring match (`_TOKEN _SECRET _PASSWORD API_KEY`) | **Adopt** | Phase 7 | Cross-link [antipattern A1] |
| `drop_cap_sys_resource()` post-init | **Adopt** | Phase 9 | Only relevant inside microVMs |
| `--block-local-connections` | **Adapt** | Phase 8 | Egress proxy already covers most of this; consider as belt-and-braces |
| Vsock CID pin | **Adopt** | Phase 9 | Free hardening once vsock is in play |
| Snapshot hand-off via `POST /mount_root` + block-device hot-swap | **Adopt** | Phase 10 | See [`20-snapstart-hot-swap.md`](./20-snapstart-hot-swap.md) |
| Rust as the L1 implementation language | **Adopt** | Phase 7 | ADR-0002 rewritten on this premise; same crate footprint as process_api (`tokio` + `hyper` + `tokio-tungstenite` + `tokio-vsock` + `ring` + `jsonwebtoken`) |
| `tokio-vsock`-style raw WS frames over vsock | **Open** | Phase 7 | With L1=Rust this is the natural choice; ADR-0008 to be re-evaluated at Phase 7 research against connect-rust-over-vsock |
| `process_api`'s "no tools, just exec" purity | **Reject** | — | We keep MCP tool dispatch in L1; pure exec doesn't fit the MCP shape |
| Antspace / Baku / Vercel deploy clients | **Reject** | — | Product-specific to Anthropic; not in our scope |

## 14. What this digest does **not** change

- ADR-0001, -0003, -0004, -0005, -0006, -0007, -0009 — unaffected.
- The 4-layer model — `process_api` validates it; nothing to revise.
- Roadmap phase ordering — all "Adopt" items land in their existing phases.

## Related

- ADR: [`0002-guest-agent-language-go.md`](../adr/0002-guest-agent-language-go.md), [`0008-internal-grpc-external-rest-mcp.md`](../adr/0008-internal-grpc-external-rest-mcp.md), [`0010-lambda-as-inspiration-not-runtime.md`](../adr/0010-lambda-as-inspiration-not-runtime.md)
- Sibling digests: [`13-anthropic-sandbox-runtime.md`](./13-anthropic-sandbox-runtime.md), [`16-anthropic-production-sandbox-observed.md`](./16-anthropic-production-sandbox-observed.md), [`20-snapstart-hot-swap.md`](./20-snapstart-hot-swap.md), [`21-environment-runner-go.md`](./21-environment-runner-go.md)
- Architecture: [`05-layer1-guest-agent.md`](../architecture/05-layer1-guest-agent.md), [`07-security.md`](../architecture/07-security.md)
- Antipatterns: A1 (secret leakage in env), C8 (cgroup OOM handling)
- Source notes: pattern catalogue under [`sandboxd/anthropic/`](../../../sandboxd/anthropic/)
