<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# 08 — microsandbox (single-node microVM daemon)

> Source: [`references/microsandbox/`](../../../references/microsandbox/). Rust, libkrun-based, single-node.
> Reference for Phase 2 (HTTP pool-manager sidecar shape) and the optional DirectCHProvider analog (Phase 9+).

## 1. REST/SDK surface — sandbox lifecycle

- **Where.** `crates/microsandbox/lib/sandbox/mod.rs:95-150`.
- **What.** Builder pattern: `builder() → create() / create_detached() → start() → stop() / kill()`. State persisted in SQLite. Status enum: `Running | Draining | Paused | Stopped | Crashed`.
- **Why for us.** Phase 2 — direct template for our pool-manager HTTP API. Status enum especially — we'd add `Idle` (in pool) and `Leased` (assigned to session).

## 2. Guest-agent wire protocol — CBOR over virtio-serial

- **Where.** `crates/protocol/lib/message.rs:46-70`.
- **What.** Binary framing: `[len: u32 BE][id: u32 BE][flags: u8][CBOR(...)]`. Message types: `Ready`, `ExecRequest`/`ExecStdout`/`ExecExited`, `FsRequest`/`FsResponse`, `Shutdown`. u32 correlation IDs.
- **Why for us.** Phase 7 — useful comparison vs our HTTP+WS+vsock path. CBOR's binary efficiency is nice but HTTP+WS already wins us tool ecosystem (curl, devtools, easy debugging). Adopt the **correlation-ID pattern** for our streaming exec; skip the wire format.

## 3. VMM abstraction — pluggable backends

- **Where.** `crates/runtime/lib/vm.rs:1-50`.
- **What.** Trait-based VMM backend. Microsandbox uses **libkrun (macOS-only)**; the trait is portable to Firecracker / QEMU / crosvm.
- **Why for us.** Phase 9 — sets the template for our `Hypervisor` trait if we ever build a DirectCH/DirectFC provider. We **substitute libkrun with CH** as primary.

## 4. CLI ↔ daemon — relay socket + reconnect

- **Where.** `crates/cli/lib/commands/create.rs`.
- **What.** Thin CLI spawns VMs as **detached child processes**; agent relay socket for CLI ↔ sandbox IPC (CBOR). Sandboxes persist in SQLite — CLI can reconnect post-exit.
- **Why for us.** Phase 2 — we want a **persistent HTTP daemon** rather than CLI-spawned subprocesses (matches Docker socket replacement goal). Useful: the reconnect-via-DB pattern for crash recovery.

## 5. Project layout — Rust workspace, mappable to Go modules

- **Where.** Repo `Cargo.toml` workspace.
- **What.** `microsandbox` (SDK) | `cli` | `protocol` (shared host↔guest) | `runtime` (guest) | `network` | `filesystem` | `image` | `db`.
- **Why for us.** Phase 2/6 Go layout. Map directly:
  - `microsandbox` → `pkg/sandboxd` (SDK / library).
  - `cli` → `cmd/sandboxctl`.
  - `protocol` → `pkg/agentproto` (shared).
  - `runtime` → `cmd/agent`.
  - `network` / `filesystem` / `image` / `db` → `internal/*`.
- Compare with [coder's layout](./03-coder.md) §10 — both converge on the same shape, different language.

## 6. Network model — smoltcp + policy

- **Where.** `crates/network/lib/lib.rs`.
- **What.** In-process **smoltcp** networking stack with policy enforcement (advanced). Per-sandbox IPs + per-rule egress.
- **Why for us.** Phase 2 — **simpler approach**: TAP/TUN + iptables. Defer smoltcp until we have a strong reason (full userspace stack isolation in microVM).

## 7. Image / template format

- **Where.** `crates/image/lib/lib.rs`.
- **What.** Standard OCI pulling + EROFS (read-only, compressed) base + ext4 writable overlay. Content-addressed layer cache. Snapshot export/import for fast clones.
- **Why for us.** Phase 3 — EROFS as the read-only base for skill blobs is interesting (vs our planned squashfs). Worth comparing in `phase-3-research.md`.

## 8. Persistence — SQLite (read/write pool split)

- **Where.** `crates/db/lib/pool.rs`.
- **What.** SQLite + WAL mode; **separate read pool (multi-conn) + write pool (single-conn)**. SeaORM ORM. Migrations versioned in code.
- **Tables.** `sandbox`, `run`, `image_ref`, `layer`, `manifest`, `volume`, `sandbox_metric`.
- **Why for us.** Phase 2 pool-manager sidecar — **SQLite is enough** for single-node PoC. The read/write pool split is a smart pattern even at SQLite scale.
- **Phase 6.** Move to Postgres for HA L4 control plane (matches [coder's pattern](./03-coder.md) §7).

## Adoption priorities

| Phase | Take | Skip / substitute |
|---|---|---|
| 2 | Lifecycle state enum; correlation-IDs; SQLite r/w pool split; reconnect-via-DB | smoltcp networking (use TAP+iptables); CBOR wire (use HTTP+WS) |
| 3 | EROFS base for read-only mounts (compare with squashfs) | OCI layer extraction internals — too coupled to libkrun |
| 6 | Crate layout → Go module layout | libkrun integration |
| 8 | VMM trait pattern | libkrun backend (substitute CH/FC) |

## Skip notes

- libkrun is **macOS-first**; for Linux production we go CH / FC.
- Microsandbox is **beta**; don't treat as production reference, treat as design reference.
- No multi-node coordination — we add etcd / Postgres in Phase 6+.
