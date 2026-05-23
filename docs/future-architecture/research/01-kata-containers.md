<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# 01 — Kata Containers (Rust agent + kata-deploy)

> Source: [`references/kata-containers/`](../../../references/kata-containers/) (Rust PID 1 agent + k8s DaemonSet for installing Kata on nodes).
> Relevant to Phase 7 (Go guest agent — port these patterns) and Phase 9 (Kata + Cloud Hypervisor for untrusted tier).

## 1. PID 1 — Subreaper + async `SIGCHLD` loop

- **What it does.** Register as subreaper via `prctl(PR_SET_SUBREAPER, 1)`, then await `SIGCHLD` in a tokio loop; on each signal call `waitpid(-1, WNOHANG | __WALL)` under a lock to reap orphans while keeping a sandbox-owned process map consistent.
- **Where.** `src/agent/src/signal.rs:9-122` (full file). `set_subreaper(true)` at line 95; `handle_sigchild()` loop at lines 21–86; signal setup at 88–122.
- **Port to Go.**
  1. `unix.Prctl(unix.PR_SET_SUBREAPER, 1, 0, 0, 0)` at startup.
  2. `signal.Notify(ch, syscall.SIGCHLD)`.
  3. Loop with `syscall.Wait4(-1, &wstatus, syscall.WNOHANG|syscall.WALL, nil)`.
  4. Track exits in the agent's process map.
- **Skip.** Kata's `WAIT_PID_LOCKER` is container-runtime specific; our product lifecycle differs.

## 2. vsock listener — `AddressFamily::Vsock` + stream binding

- **What it does.** Bind `AF_VSOCK` on port N, listen, accept. Used for debug console and log streaming without unix sockets.
- **Where.** `src/agent/src/main.rs:161-183` (`create_logger_task`). Socket at line 165; bind+listen at 171–173; `VsockAddr::new(VMADDR_CID_ANY, vsock_port)` at 171.
- **Port to Go.**
  1. `github.com/mdlayher/vsock`: `vsock.Listen(":2048")`.
  2. Accept and demultiplex by service (health, API, logging) on connection.
  3. Graceful fallback if vsock unavailable (matches our [pattern 3 in `00-anthropic-and-sandboxd.md`](./00-anthropic-and-sandboxd.md)).
- **Skip.** Kata's ttrpc protocol is OCI-shaped.

## 3. gRPC service definitions — structure to learn, NOT copy

- **Where.** `src/libs/protocols/protos/agent.proto:20-82`. 40+ RPCs: container lifecycle (`CreateContainer`/`StartContainer`/`RemoveContainer`, 22–32), process control (`ExecProcess`/`SignalProcess`/`WaitProcess`, 33–35), stdio multiplexing (`WriteStdin`/`ReadStdout`/`ReadStderr`, 44–49), networking (51–58), `GetMetrics` (61).
- **Take.** Lifecycle-phase separation; stdio model (request/response for stdin, server-push events for stdout/err); device-hotplug semantics post-VM-start.
- **Skip.** The OCI shape itself — our agent API is **product-aware**, not generic OCI ([`architecture/05-layer1-guest-agent.md`](../architecture/05-layer1-guest-agent.md)).

## 4. Hardening at startup — init-as-PID-1 setup

- **What it does.** When PID 1: mount cgroups v1/v2, set hostname, `setsid()`, set controlling terminal via `ioctl`, configure `PATH`.
- **Where.** `src/agent/src/main.rs:648-680` (`init_agent_as_init`). Cgroup mount: 651. `/dev/ptmx` symlink: 659–660. `setsid()`: 662. Controlling-tty ioctl: 665. Hostname: 670–677.
- **Port to Go.** Detect `getpid() == 1`; conditionally run init routine; mount cgroups only if absent; symlink `/dev/ptmx` if missing.
- **Skip.** Full OCI init (hooks, env setup) — ours is microVM-specific, much smaller.
- **Note.** `PR_SET_DUMPABLE=0` and capability drops live in the **runtime config**, not the agent (agent runs as root inside the guest). We pair this with [pattern 5 in `00-anthropic-and-sandboxd.md`](./00-anthropic-and-sandboxd.md).

## 5. kata-deploy DaemonSet — install/cleanup, probes, node affinity

- **What it does.** Per-node DaemonSet copies Kata binaries, configures CRI (containerd/CRI-O), creates `RuntimeClass` resources, cleans up on terminate. Node affinity filters on CPU virt features (VMX/SVM).
- **Where.** `tools/packaging/kata-deploy/helm-chart/kata-deploy/templates/kata-deploy.yaml:1-384`.
  - DaemonSet: 21–38.
  - Virt-affinity (x86 VMX/SVM): 77–130.
  - Install action: 140.
  - Probes (startup/liveness/readiness): 317–344.
  - hostPath mounts: 349–379.
  - `terminationGracePeriodSeconds: 600`: line 135.
- **Take for Phase 9 Helm work.**
  - `hostPID: true` for in-container runtime restart visibility.
  - Generous `terminationGracePeriodSeconds` for cleanup.
  - Startup probe with many short retries (60×10 s = 600 s budget).
  - Affinity on hardware capability (KVM-capable nodes only).
  - Env-driven per-node config (shim selection, etc.).
- **RuntimeClass setup.** `tools/packaging/kata-deploy/binary/src/k8s/runtimeclasses.rs:11-87` — list existing `kata-*` classes, patch `overhead.podFixed` from NFD labels (e.g. `tdx.intel.com/keys`, `sev-snp.amd.com/esids`).
- **Skip.** Multi-install suffix (parallel Kata versions), NFD complexity, multi-arch shim selection.

## 6. Configuration — TOML structure per hypervisor backend

- **What it does.** Runtime config split per backend: `[hypervisor.qemu]`, `[hypervisor.firecracker]`, `[hypervisor.clh]`. Host selects active backend by hardware/policy.
- **Where.** `src/runtime/config/configuration-clh.toml.in:14-28`, `configuration-fc.toml.in:14-40`, `configuration-qemu.toml.in:14-80`.
- **Common knobs per backend.** `path` (hypervisor binary), `kernel`, `image` (guest rootfs), `rootfs_type` (ext4/xfs/erofs), `default_vcpus`, `kernel_params`, annotation allowlists.
- **Take for Phase 9 host shim.**
  1. One section per backend in host config.
  2. Defaults per backend (vCPUs, memory overhead, kernel params differ).
  3. Annotation allowlists for which fields pod-author can override.
- **For the Go agent.** Agent doesn't parse this — host passes choices via `/proc/cmdline`. Agent extracts backend identity to decide feature set (e.g., TEE only on CH).

## 7. Backend switching — Cloud Hypervisor vs Firecracker vs QEMU

- **Where.** `src/runtime/config/` (13 backend configs total). FC has `jailer_path`; CH has `firmware` for TEEs.
- **For the agent.** Detect backend at startup via kernel cmdline (`kata.hypervisor=clh`) or DMI/CPUID markers; toggle feature flags (TEE attestation enabled only under CH).

## 8. Small-binary Rust patterns — applicable to Go too

- **Where.** `src/agent/Cargo.toml:1-109`. Workspace deps (105–109), `profile.release` LTO (102–103).
- **Result.** ~3–5 MB unstripped, ~1.5 MB stripped.
- **Port to Go.**
  - Build tags for optional services (policy, confidential data hub).
  - `CGO_ENABLED=0 go build -ldflags="-s -w -X main.version=$VERSION"`.
  - Expected: ~5–10 MB for a production Go agent — acceptable.
  - UPX worth testing but Kata doesn't use it.

## Adoption matrix

| Pattern | Adopt? | Why |
|---|---|---|
| PID 1 subreaper + `SIGCHLD` loop | YES | Mandatory for PID 1 |
| vsock listener on fixed port | YES | Standard microVM transport |
| OCI ttrpc service structure | NO (study) | Our API is product-shaped |
| init-as-PID-1 setup | PARTIAL | Adapt to minimal microVM init |
| DaemonSet + probes + node affinity | YES | Phase-8 Helm pattern |
| TOML config per backend | YES | Host shim, not agent |
| Runtime-backend detection | YES | Feature toggling |
| Feature flags + LTO / `-s -w` | YES | Small Go binary |
