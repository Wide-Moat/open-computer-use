<!-- SPDX-License-Identifier: BUSL-1.1 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# External References

> Catalog of open-source projects we either build on, learn from, or explicitly reject.
> Source: `sandboxd/docs/references.md` (verbatim URLs preserved) plus our own additions.
>
> Each entry carries: **License**, **Language**, **Role in our stack**, optional **To research** tag.
> Entries tagged `to-research` are unresolved and must be evaluated during the relevant phase's research pass (see [`roadmap.md`](./roadmap.md) — per-phase research-then-sign-off cadence).

---

## Layer 1 — Guest agents (sandbox PID 1)

### e2b-dev/infra — `envd`
- **URL:** https://github.com/e2b-dev/infra/tree/main/packages/envd
- **License:** Apache 2.0
- **Language:** Go
- **Role:** Reference for our future Go guest agent (Phase 7). API surface, gRPC streaming, image-build pipeline.
- **Notes:** Production at E2B Cloud. Coupled to Firecracker networking and Nomad — port API ideas, not glue.
- **To research:** Phase 7.

### kata-containers / src / agent
- **URL:** https://github.com/kata-containers/kata-containers/tree/main/src/agent
- **License:** Apache 2.0
- **Language:** Rust
- **Role:** Canonical kata-agent. PID 1 patterns, vsock transport, signal handling, `PR_SET_DUMPABLE=0` hardening.
- **Notes:** OCI-shaped API — we want a product-aware API. Don't bolt Computer Use onto kata-agent itself.
- **To research:** Phase 7 (compare Rust vs Go alternatives; feeds ADR-0002).

### microsandbox / msb-agent
- **URL:** https://github.com/microsandbox/microsandbox
- **License:** Apache 2.0
- **Language:** Rust
- **Role:** Small, readable libkrun-based agent — good for learning the pattern.
- **Notes:** Beta as of early 2026. Not production-ready.
- **To research:** Phase 7 (skim for API ideas).

---

## Layer 2 — Sandbox runtimes

### firecracker-microvm/firecracker
- **URL:** https://github.com/firecracker-microvm/firecracker
- **License:** Apache 2.0
- **Language:** Rust
- **Role:** Smallest attack surface, fastest cold start. AWS Lambda/Fargate foundation.
- **Constraints:** Requires KVM + bare-metal (or nested virt). No virtio-fs, no GPU.
- **To research:** Phase 9 (kata-fc alternative tier).

### cloud-hypervisor/cloud-hypervisor
- **URL:** https://github.com/cloud-hypervisor/cloud-hypervisor
- **License:** Apache 2.0
- **Language:** Rust
- **Role:** Preferred microVM for Computer Use — supports virtio-fs, GPU passthrough, hot-plug. Used by AWS, Microsoft.
- **Constraints:** Requires KVM + bare-metal. Larger codebase (~80K LOC) than Firecracker (~50K).
- **To research:** Phase 9 (lead candidate for `kata-ch` tier).

### kata-containers/kata-containers
- **URL:** https://github.com/kata-containers/kata-containers
- **License:** Apache 2.0
- **Language:** Go + Rust
- **Role:** k8s-native microVM runtime. RuntimeClass-driven, installed via `kata-deploy` DaemonSet. Backends: QEMU / Firecracker / Cloud Hypervisor.
- **Status:** CNCF graduated.
- **To research:** Phase 9.

### google/gvisor
- **URL:** https://github.com/google/gvisor
- **License:** Apache 2.0
- **Language:** Go
- **Role:** Userspace kernel. Good for short-lived CPU-only scripts.
- **Caveat:** **Not suitable for Chromium / Computer Use** — `docs/future-architecture/architecture/04-layer2-runtimes.md` explicitly rejects gVisor for our browser workloads (compat envelope too narrow). Use for non-browser tiers only.
- **To research:** Phase 7 (validate as experimental tier for code-execution sandboxes).

### nestybox/sysbox
- **URL:** https://github.com/nestybox/sysbox
- **License:** Apache 2.0 (CE) / commercial (EE)
- **Language:** Go
- **Role:** User-namespace + procfs/sysfs emulation. Allows root-in-container, Docker-in-Docker without `--privileged`. Default for the current Helm chart.
- **Caveat:** Shares host kernel — vulnerable to kernel CVEs. Internal/trusted only.
- **To research:** Phase 5 (already in use — formalize as the default L2 for the k8s provider).

### opencontainers/runc
- **URL:** https://github.com/opencontainers/runc
- **License:** Apache 2.0
- **Language:** Go
- **Role:** Default dev/CI runtime. No isolation guarantees for untrusted code.

---

## Layer 3 — Orchestration

### kubernetes-sigs/agent-sandbox
- **URL:** https://github.com/kubernetes-sigs/agent-sandbox
- **License:** Apache 2.0
- **Language:** Go
- **Role:** Basis for our future `KubernetesProvider` (Phase 5+). Provides `Sandbox`, `SandboxTemplate`, `SandboxClaim`, `SandboxWarmPool` CRDs.
- **Status:** v0.1.1 (early but active, backed by Google + SIG Apps). Supports gVisor (default) and Kata.
- **To research:** Phase 5 (mandatory deep-dive before writing K8sProvider; check CRD stability).

### e2b-dev/infra
- **URL:** https://github.com/e2b-dev/infra
- **License:** Apache 2.0
- **Language:** Go
- **Role:** Reference for egress proxy (`packages/proxy`) and template builder (`packages/template-manager`).
- **Caveat:** Nomad-coupled. Port ideas, don't fork wholesale.
- **To research:** Phases 2, 9.

### firecracker-microvm/firecracker-containerd
- **URL:** https://github.com/firecracker-microvm/firecracker-containerd
- **License:** Apache 2.0
- **Language:** Go
- **Role:** Firecracker via containerd CLI/API — intermediate option between raw FC and Kata.
- **To research:** Phase 9 (snapshotter pattern feeds Phase 10).

---

## Layer 4 — Egress proxies

### Michaelliv/agentbox
- **URL:** https://github.com/Michaelliv/agentbox
- **License:** MIT
- **Language:** Python (asyncio aiohttp)
- **Role:** Reference JWT-allowlist egress proxy (Phase 8). Working implementation — port to Go for production.
- **Companion blog:** https://michaellivs.com/blog/sandboxed-execution-environment/
- **To research:** Phase 8.

### Tecnativa/docker-socket-proxy
- **URL:** https://github.com/Tecnativa/docker-socket-proxy
- **License:** Apache 2.0
- **Role:** Pattern for filtering API access (HAProxy-based). Not directly useful unless legacy Docker-API consumer needs read-only access.

---

## Local sandboxing (research only)

### anthropic-experimental/sandbox-runtime
- **URL:** https://github.com/anthropic-experimental/sandbox-runtime
- **License:** Apache 2.0 (research preview)
- **Language:** Rust + bubblewrap (Linux) / seatbelt (macOS)
- **Role:** **Not** `process_api`. This is local Claude Code sandboxing. Useful patterns: FS allowlist, network restriction via seccomp BPF, macOS seatbelt profiles.

---

## Computer Use specific

### e2b-dev/desktop
- **URL:** https://github.com/e2b-dev/desktop
- **License:** Apache 2.0
- **Role:** GUI desktop env (Xfce) inside sandbox, VNC/RDP patterns. Comparable to our current CDP+ttyd setup.
- **To research:** Phase 7 (compare Xfce/VNC vs our current CDP-only approach).

### e2b-dev/surf
- **URL:** https://github.com/e2b-dev/surf
- **License:** Apache 2.0
- **Role:** Computer Use agent reference — action loop, screenshot streaming.

### Browser automation
- **Playwright** (Microsoft, Apache 2.0) — already in our image
- **Puppeteer** (Google, Apache 2.0)
- **chromedp** (Go, MIT) — direct CDP; candidate if guest agent goes Go
- **fantoccini** (Rust, MIT/Apache 2.0)

For Computer Use we want direct CDP (not WebDriver) — fine-grained event injection + screencast. **To research (Phase 7):** chromedp vs raw CDP WebSocket in the Go agent.

---

## Reverse-engineering / research notes

### AprilNEA/reverse-engineering-claude-code-antspace
- **URL:** https://github.com/AprilNEA/reverse-engineering-claude-code-antspace
- **License:** MIT (analysis); binaries are Anthropic's
- **Role:** Reference for wire protocol, snapshot architecture, inferred Go monorepo structure of Claude Code Web. Compare with our MCP gateway design.

### Michael Livshits blog — "Reverse-engineering Claude's sandbox"
- **URL:** https://michaellivs.com/blog/sandboxed-execution-environment/
- **Role:** Clearest published explanation of the architectural pattern. Pair with sandboxd's `architecture.md`. Required reading before Phase 6 (Go control plane).

---

## Explicitly rejected

### Daytona (daytonaio/daytona)
- **URL:** https://github.com/daytonaio/daytona
- **License:** AGPL v3
- **Reason:** AGPL contaminates downstream (incl. SaaS). Toxic for enterprise. See [ADR-0006](./adr/0006-no-agpl-no-bsl-dependencies.md).

### HashiCorp Nomad
- **License:** BSL — not OSI-open-source as of the HashiCorp re-license.
- **Reason:** License-incompatible with our intended Apache-2.0 posture. Don't take a Nomad dependency. E2B's Nomad-specific code is reference-only.

### Beam.cloud
- **License:** Mixed (some Apache, control plane closed).
- **Reason:** No isolation by default (containers, not microVM); control plane closed.

### Modal
- **License:** Closed, managed-only.

---

## Compatibility matrix (target combinations)

| Agent | Hypervisor / Runtime | Orchestrator | Tier / Use case |
|---|---|---|---|
| current Python entrypoint + MCP server | runc / sysbox | Docker Compose | Today's PoC (Phase 0–5) |
| current Python entrypoint + MCP server | sysbox | k8s (any) via our Helm chart | Phase 5 target |
| **future Go agent** | sysbox | k8s | Internal/trusted tier (Phase 7) |
| future Go agent | gVisor | k8s | Code-execution (non-browser) tier (Phase 7) |
| future Go agent | Kata + Cloud Hypervisor | k8s | Untrusted tier — Computer Use, public (Phase 9 — requires Phase 8 egress proxy) |
| future Go agent | Kata + Firecracker | k8s | Untrusted tier — fastest cold start (Phase 9 — requires Phase 8 egress proxy) |

---

## License compatibility (our project)

Project license: BUSL-1.1 (per `CLAUDE.md`) with MIT for select skills.

Direct dependencies must be compatible — **safe:**
- Apache 2.0, MIT, BSD-2/3, MPL 2.0, LGPL 2.1+ (link only)

**Avoid:**
- GPL v2 / v3 (copyleft)
- AGPL v3 (Daytona)
- BSL (Nomad post-HashiCorp)

See [ADR-0006](./adr/0006-no-agpl-no-bsl-dependencies.md).
