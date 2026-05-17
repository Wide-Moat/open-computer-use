<!-- SPDX-License-Identifier: BUSL-1.1 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# 02 — E2B Infrastructure (e2b-dev/infra)

> Source: [`references/infra/`](../../../references/infra/). Production E2B infra in Go.
> Most relevant for Phase 2 (HTTP pool sidecar), Phase 3 (storage), Phase 6 (control plane), Phase 7 (guest agent), Phase 8 (egress proxy).

## 1. Network slot pool — dual-channel recycle with drain delay

- **What.** Pool of network-namespace slots with **two** channels — "new" (pre-allocated at startup) and "reused" (returned post-drain). `Get()` tries reused first, falls back to new. `Return()` waits `ReturnDelay` (3 s) before pushing back to allow inflight requests to drain.
- **Where.** `packages/orchestrator/pkg/sandbox/network/pool.go` (357 lines).
  - `NewPool()` builds dual channels.
  - `Get()` tries reused, falls back to new.
  - `Return()` schedules recycle with `ReturnDelay`.
  - Metrics: `newSlotsAvailableCounter`, `reusableSlotsAvailableCounter`.
- **Why for us.** Phase 2 pool semantics. The drain delay prevents dropped connections when sandboxes cycle fast.
- **Skip.** Linux iptables/netlink specifics; keep the slot/return semantics as an abstraction.

## 2. Adjustable semaphore — separates fresh-create vs snapshot-resume

- **What.** Feature-flag-driven semaphore limits concurrent **sandbox starts**. Snapshot resumes use `waitForAcquire` (15 s timeout — higher parallelism). Fresh creates use `TryAcquire` (immediate or reject).
- **Where.** `packages/orchestrator/pkg/server/main.go:87-91, 162-182` (`NewAdjustableSemaphore`, `refreshStartingSandboxesLimit` every 30 s). Usage: `packages/orchestrator/pkg/server/sandboxes.go:116-130`.
- **Why for us.** Phases 2 + 6. Prevents thundering herd on template loads / NBD allocation / memory.
- **Skip.** LaunchDarkly — use simple env / config.

## 3. envd — PID 1 Go agent with Connect-RPC streaming exec

- **What.** PID 1 in each sandbox; `os/exec` + signal forwarding; Connect-RPC over HTTP/2 in a single binary; `Process.Start()` streams stdout/stderr/pty as a oneof event; supports `SendSignal` (SIGTERM/SIGKILL), stdin/pty write, KeepAlive events for idle-TCP survival.
- **Where.**
  - Main: `packages/envd/main.go:132-221` (HTTP/2 server, chi router, Connect auth).
  - Service: `packages/envd/internal/services/process/service.go:19-84`.
  - Handler: `packages/envd/internal/services/process/handler/handler.go:44-487`.
  - Proto: `packages/envd/spec/process/process.proto:1-172`.
- **Why for us.** **Direct template for Phase 7 Go agent.** Pattern set:
  - Signal forwarding via SDK call.
  - Streaming output via oneof event (stdout / stderr / pty / keepalive / exit).
  - Multiplex multiple concurrent execs per VM.
  - KeepAlive frames against TCP idle timeout.
- **Skip.** Firecracker MMDS polling, vsock specifics, cgroup v2 (port the *shape*, not Linux glue).

## 4. Sandbox creation flow — multi-resource assembly with rollback

- **What.** `SandboxCreateRequest` acquires in sequence: network slot, template, NBD block device, memory+rootfs snapshots. Feature flags gate Firecracker version, max sandboxes/node, internet access, disk size. Returns `client_id` for session routing.
- **Where.** `packages/orchestrator/pkg/server/sandboxes.go:60-235`.
  - 107–129: semaphore + node capacity.
  - 132–141: template fetch.
  - 143–161: network/egress config.
  - 163–214: assemble + `ResumeSandbox()`.
  - 215–235: rollback on failure.
  - 237–249: lifecycle hooks + event publish.
- **Why for us.** Phase 6 orchestration. The **rollback pattern** (release acquired resources on partial failure) is the key takeaway.
- **Skip.** Nomad job scheduling, GCS template bucket. Keep the multi-resource orchestration shape.

## 5. Cgroup v2 isolation — weighted process classes via `clone3(CLONE_INTO_CGROUP)`

- **What.** Three cgroup hierarchies per sandbox:
  - **PTYs (interactive):** `cpu.weight=200`, `memory.high=80%`.
  - **Socats (proxies):** `cpu.weight=150`, `memory.min/low=8MB`.
  - **User processes:** `cpu.weight=50`, `memory.high=80%`.
  Uses `clone3(CLONE_INTO_CGROUP)` with a passed file descriptor for **race-free** classification at process birth.
- **Where.** Manager `packages/orchestrator/pkg/sandbox/nbd/cgroup/cgroup2.go:1-120`. envd integration: `packages/envd/main.go:223-272`.
- **Why for us.** Phase 7 — prevents user processes from starving orchestrator infrastructure inside the sandbox. The Firecracker memory limit is whole-VM; this gives per-process guarantees.

## 6. Egress proxy — protocol-specific inspection ports

- **What.** Single `tcpproxy.Proxy` listening on three ports:
  - **HTTP (5016):** inspects `Host` header against allowlist.
  - **TLS (5017):** inspects SNI against allowlist.
  - **Other (5018):** CIDR-only check (no protocol sniffing — prevents blocking SSH).
  Host iptables redirects by original dst port.
- **Where.** `packages/orchestrator/pkg/tcpfirewall/proxy.go:1-100+`.
- **Why for us.** Phase 8 — domain blocklist without false positives from protocol mis-detection.
- **Skip.** iptables/netlink Linux specifics; abstract as "traffic shaper with protocol inspection". Compare with our planned [agentbox-style](./09-agentbox.md) JWT pattern — these are complementary (this filters; JWT authorizes).

## 7. Template streaming cache — lazy block-device loading

- **What.** Snapshots (memfile, rootfs, metadata) keyed by `buildID`. First access streams from GCS/S3 into local tmpfs; cached for 1 h. Supports layered builds.
- **Where.** Interface `packages/orchestrator/pkg/sandbox/template/template.go:16-24`. Proto `packages/orchestrator/template-manager.proto:1-179` (layer upload at 9–18, config at 61–89, metadata at 127–135).
- **Why for us.** Phase 3 — templates as **streaming block devices**, not OCI images. Layer-reuse via `cacheScope`.

## 8. Slot recycling — graceful return with locking discipline

- **What.** On sandbox end, slot recycle waits `ReturnDelay` for drain → resets internet config (iptables) → returns to pool. RWMutex on the reused-slots channel; lock released **before** slow `RemoveNetwork` syscalls (lines 254–286 of `pool.go`).
- **Where.** `packages/orchestrator/pkg/sandbox/network/pool.go:204-298`. Metrics: `returnedSlotCounter`, `releasedSlotCounter`.
- **Why for us.** Phase 2. Same drain + lock discipline ensures fast recycle without dropping inflight requests or stalling new acquisitions.

## 9. Per-sandbox metrics — delta-temporality observable gauges

- **What.** Callback-driven observable gauges (CPU %, mem bytes, disk bytes) measured in parallel (5× concurrency cap). Uses OTel **delta temporality** so gauges don't repeat indefinitely after sandbox death. Tagged by `sandbox_id`, `team_id`, `build_id`. Warns at >80 % mem or CPU.
- **Where.** `packages/orchestrator/pkg/metrics/sandboxes.go:46-319`. Export every 5 s (line 41).
- **Why for us.** Phase 6 / 10. Especially the **delta temporality** detail — common foot-gun with OTel gauges in ephemeral-pod environments.

## 10. API gateway auth — multi-tenant team-context extraction

- **What.** Request validated by either API token (Bearer → team lookup) or Supabase JWT (user → teams → default team). All downstream calls receive `teamID` context.
- **Where.** `packages/api/internal/handlers/auth.go:1-80`.
- **Why for us.** Phase 6. Foundational multi-tenant pattern; same shape regardless of identity backend.
- **Skip.** Supabase specifics; substitute our OIDC provider.

## 11. Snapshot/pause/resume lifecycle

- **What.** On pause: save VM memory + disk to GCS/S3. On resume: reconstruct from snapshot files; `Server.Create()` branches on `req.Sandbox.Snapshot` (line 69, 117) — resume uses `resumeVM()` with `waitForAcquire(15s)` vs. fresh `TryAcquire`.
- **Where.** Create flow: `packages/orchestrator/pkg/server/sandboxes.go:69, 117-129`. FC client: `packages/orchestrator/pkg/sandbox/fc/client.go` (`resumeVM`, `pauseVM`).
- **Why for us.** Phase 10. Stateful handoff, cost optimization, multi-session continuity.

## 12. Version-gated metric collection

- **What.** Observe metrics only if `envd.Version >= minEnvdVersionForMetrics` (line 165). Feature-specific minima: memory precision ≥ 0.2.4, disk ≥ 0.2.4, cache ≥ 0.5.9. Prevents crashes on older sandboxes.
- **Where.** `packages/orchestrator/pkg/metrics/sandboxes.go:165-173, 225-257`.
- **Why for us.** Phase 6 — safe gradual rollout of new metrics without coordinating sandbox upgrades. General Go pattern, adopt broadly.

## 13. Zombie reaping via Go stdlib `os/exec.Wait()`

- **What.** Per spawned process: goroutines stream stdout/stderr/pty; `Process.Wait()` blocks on `cmd.Wait()`; SIGTERM/SIGKILL cancels output context (`p.outCancel()` line 360).
- **Where.** `packages/envd/internal/services/process/handler/handler.go:335-486`. Start: 429–447. Wait: 449–486 (cmd.Wait at 453, exit at 464–469). Signal: 354–364.
- **Why for us.** Phase 7. Go stdlib handles `SIGCHLD` automatically for *its own* children — but for PID 1 reaping of inherited orphans we still need [pattern 1 from kata](./01-kata-containers.md#1-pid-1--subreaper--async-sigchld-loop). Use both.

## Summary

| Pattern | File | Phase | Take? |
|---|---|---|---|
| Dual-channel network pool + drain delay | `orchestrator/pkg/sandbox/network/pool.go` | 2 | YES |
| Adjustable semaphore (fresh vs resume) | `orchestrator/pkg/server/main.go` | 2,6 | YES |
| envd Connect-RPC streaming agent | `envd/main.go`, `envd/internal/services/process/` | 7 | YES — template |
| Multi-resource create with rollback | `orchestrator/pkg/server/sandboxes.go` | 6 | YES |
| Cgroup v2 weighted classes | `orchestrator/pkg/sandbox/nbd/cgroup/cgroup2.go` | 7 | YES |
| Three-port egress firewall | `orchestrator/pkg/tcpfirewall/proxy.go` | 9 | YES |
| Streaming template cache | `orchestrator/pkg/sandbox/template/` | 3 | YES |
| Delta-temporality observable gauges | `orchestrator/pkg/metrics/sandboxes.go` | 6,10 | YES |
| Multi-tenant team-context auth | `api/internal/handlers/auth.go` | 6 | YES |
| Snapshot pause/resume | `orchestrator/pkg/server/sandboxes.go` | 10 | YES |
| Version-gated metric features | `orchestrator/pkg/metrics/sandboxes.go` | 6 | YES |
