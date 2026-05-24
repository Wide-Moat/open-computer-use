<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# Proof — anthropic-experimental/sandbox-runtime vs open-computer-use

> Companion to [`13-anthropic-sandbox-runtime.md`](./13-anthropic-sandbox-runtime.md) (code-citation deep-dive). This file answers the positioning question: are we redundant with it, a superset, or orthogonal? Verdict at the bottom.
>
> Status: decision-grade for competitive positioning ([`manifesto/01-audience-and-buyer.md`](../manifesto/01-audience-and-buyer.md)) and BoM routing ([`manifesto/05-licensing-posture.md`](../manifesto/05-licensing-posture.md)).
> Evidence base: `/tmp/srt-inspect` snapshot at HEAD `34a39e0` (PR #279, merged 2026-05-22). Anthropic upstream repo: <https://github.com/anthropic-experimental/sandbox-runtime>.

## Anthropic sandbox-runtime — what it actually is

A **single-process security wrapper** for arbitrary commands on a developer laptop. Ships as the `srt` npm CLI plus a TypeScript library (`SandboxManager.wrapWithSandbox()`). Primary user is **Claude Code running locally**; the README leads with "Sandboxing MCP Servers" as the headline use case (`README.md:50-101`). Anthropic positions it as enabling "safer AI agents" but the threat model is local untrusted commands, not multi-tenant or remote agents.

Isolation primitive: **OS-native, no container, no VM**. macOS uses `sandbox-exec` + dynamically generated Seatbelt Lisp profiles (`src/sandbox/macos-sandbox-utils.ts:1-941`). Linux uses `bubblewrap` (`bwrap`) with bind-mounts + network-namespace removal + seccomp BPF filters for AF_UNIX socket blocking (`src/sandbox/linux-sandbox-utils.ts:1-1307`, `vendor/seccomp-src/`). Network filtering is proxy-mediated: built-in HTTP/HTTPS proxy + SOCKS5 proxy that the sandboxed process is forced through (`src/sandbox/http-proxy.ts:1-385`, `src/sandbox/socks-proxy.ts:1-220`). Windows port (Rust crate, WFP-based) landed in PR #278/#279 on 2026-05-22 (`vendor/srt-win/`).

API surface: CLI (`srt <cmd>`) and library (`SandboxManager.initialize(config)` + `wrapWithSandbox(cmd)` returning a shell string — `src/index.ts:1-46`). No REST, no gRPC, no MCP, no daemon. **Lifecycle is one-shot per command**: start proxies, spawn sandboxed child, child exits, `SandboxManager.reset()`. No session, no snapshot, no replay. Language: TypeScript (Node ≥ 18) for the orchestrator, C for seccomp helpers, Rust for the new Windows backend. Maintenance is **active**: 76 commits in the last 90 days, 32 unique contributors across Anthropic + external (`@ryoppippi`, `@SUZUKI Sosuke`, etc.), first commit `2025-10-20`, latest `2026-05-22`. License: **Apache-2.0** (`LICENSE`). Self-described "Beta Research Preview" — APIs may change.

## Open-computer-use — what we actually are

A **managed remote-workspace service**. The orchestrator (`computer-use-server/`, FastAPI, Python) manages full Ubuntu 24.04 containers via the Docker socket; each MCP `X-Chat-Id` gets its own long-lived container (`docker_manager.py`). Inside each container the agent has: Python, Node, Java, Bun, Playwright + CDP browser, ttyd terminal, Claude Code CLI / OpenAI Codex / OpenCode (`Dockerfile:1-50`), 13 built-in skills, the html2pptx / docx / xlsx / pdf stack. The MCP server exposes `bash`, `python`, `playwright-cli`, `sub-agent`, `read_file`, `write_file`, `describe_image`, file upload/download, browser streaming, terminal proxy.

Surface to the LLM is **MCP over Streamable HTTP** (`mcp_tools.py`, `app.py`), not a process-wrap. The LLM never sees the sandbox boundary directly — it sees tools. CDP and the terminal are proxied to the user's browser for live observation. The lifecycle is **long-lived per chat**: container created on first tool call, kept warm for the chat's duration, idle-timed-out. Tested at ~1,000 MAU in production (`README.md:32`).

Isolation today: **plain Docker runc**, no gVisor / Kata / Firecracker on the `main` branch. Helm chart exists with Kata as an option (`README.md:457`). The `next/v1` branch is the enterprise rewrite — Kubernetes-native, Firecracker microVMs for the sandbox tier, audit-event emission, replay bundles, OPA-enforced egress proxy, OpenBao secrets, customer-supplied KMS — designed for bank in-perimeter deployment. License: FSL-1.1-Apache-2.0 (`main`), TBD for `next/v1`.

## Side-by-side feature matrix

| Capability | anthropic-experimental/sandbox-runtime | open-computer-use main (PoC) | Wide-Moat next/v1 target |
|---|---|---|---|
| Isolation primitive | sandbox-exec / bubblewrap (process-level) | Docker runc (container) | Firecracker microVM + Kata option |
| Per-task ephemeral vs session | One-shot per command | Long-lived per chat | Per-chat session, snapshot + resume |
| Browser + desktop (vision-LLM Computer Use) | No | Yes — CDP, Playwright, live stream | Yes |
| Terminal/shell access to the agent | The agent IS a shell command being wrapped | Yes — ttyd + tmux + Claude Code CLI | Yes, audited |
| Filesystem primitives | Allow/deny lists, glob match, mandatory denies | Container FS, host-mounted volume | CoW snapshots, FS diff in replay bundle |
| Network policy / egress control | Built-in HTTP/SOCKS5 proxy, domain allowlist (`http-proxy.ts:74-110`) | Open egress unless ENABLE_NETWORK=false | OPA-policy-driven egress proxy + DNS allowlist |
| Audit-event emission | macOS log-store tap (`macos-sandbox-utils.ts:88-96`); none on Linux | None | Structured audit events to Splunk/SIEM |
| Replay bundle (CDP + DOM + tool trace + LLM prompt + FS diff) | None | None | Designed-in (TBD component) |
| Multi-provider LLM | N/A — does not talk to LLMs | Yes — any OpenAI-compatible + Anthropic | Yes — ModelProvider abstraction |
| MCP-server hosting vs MCP-client only | Wraps MCP servers (their process) | Hosts MCP server | Hosts MCP server |
| Multi-tenant boundary | Single user, single laptop | Per-chat container | Per-tenant + per-session, k8s-namespaced |
| Skill / tool plugin model | None | 13 skills + custom; auto-injected | SkillProvider abstraction (external registry) |
| Deployment shape | npm CLI binary | Docker Compose + Helm | Helm + OCI, GitOps-friendly |
| Licence | Apache-2.0 | FSL-1.1-Apache-2.0 (Apache after 2y) | TBD |
| Maintenance velocity (90d) | 76 commits, 32 contributors, active | This repo, single-maintainer-driven | n/a (not yet released) |

## Where their scope ends and ours begins

- **They stop at "wrap one process on one machine."** No orchestrator, no session, no remote, no multi-tenancy, no LLM, no browser, no skills, no audit log shipping. Their out-of-scope IS our entire product.
- **They have no agent-facing API.** `srt curl ...` is a developer-typed command; an LLM can't "use" `srt` over MCP. We expose tools an LLM calls; the sandbox is below that surface.
- **They isolate at the OS-syscall / seatbelt-policy layer; we isolate at the container/VM layer.** Different threat models — they protect a dev laptop from a rogue MCP server; we protect a bank's prod cluster from a rogue LLM-driven session. Both layers are useful; neither replaces the other.
- **No state model.** No notion of snapshot, resume, replay, idle-timeout, container reuse — all load-bearing for our `next/v1` storage and observability components.

## Primitives in their codebase we should consider adopting

- **HTTP/SOCKS5 proxy with domain allowlist + per-request callback** — `src/sandbox/http-proxy.ts:29-110`, `src/sandbox/request-filter.ts:1-141`. Drop-in match for `next/v1`'s outbound egress proxy ([`09-agentbox.md`](./09-agentbox.md)); reuse the filter-callback shape inside our Go/Rust egress.
- **Mandatory-deny path list** — `src/sandbox/sandbox-utils.ts:11-21` (`.bashrc`, `.git/hooks/`, `.mcp.json`, etc.). Belongs verbatim inside our microVM rootfs build as an always-on read-only overlay; prevents agent self-modification regardless of per-task policy.
- **Seccomp BPF + nested-namespace pattern** — `vendor/seccomp-src/seccomp-unix-block.c:51-80`, `apply-seccomp.c:1-30`. The two-stage isolation (outer bwrap → inner nested user+PID ns + seccomp) is the right shape for Phase 9 inside-microVM defence-in-depth; transfers to our Firecracker guest with minimal change.
- **MitM proxy with ephemeral CA** — `src/sandbox/mitm-ca.ts:1-191`, `src/sandbox/tls-terminate-proxy.ts:1-281`. Recent feature (PR #259, May 2026) — useful pattern for the `next/v1` egress proxy when we need per-request HTTP body filtering, not just domain allowlist.
- **Zod-validated config + file watcher** — `src/sandbox/sandbox-config.ts:1-366`. The schema-validated dual-layer config (global + per-command override) is closer to what we want than our current env-var soup; adopt the shape for our policy CRDs.

## Primitives we already do or plan to do that they don't

- **MCP-over-HTTP orchestrator with per-chat container lifecycle** — `computer-use-server/app.py`, `docker_manager.py`. Out of their scope entirely.
- **Live CDP browser streaming + ttyd terminal proxy** — `mcp_tools.py`, `static/`. Vision-LLM Computer Use core; they don't address it.
- **Skill system** — auto-injected, model-agnostic, custom skills via Settings Wrapper. Their wrapping model has no concept of agent capabilities.
- **Replay bundles (CDP + DOM + tool trace + LLM prompt + FS diff)** — planned for `next/v1`, no equivalent in `srt`.
- **Audit event emission to SIEM, OPA-enforced egress, customer KMS integration** — bank-buyer features; `srt`'s "macOS log-store tap" is interesting prior art but not a replacement.

## Recommendation — adopt / vendor / build / ignore

**Adopt selectively as a bundled dependency for the agent-tool-execution sandbox layer ONLY, not as a replacement for our orchestrator.** Inside each `next/v1` microVM, an MCP-server-running-inside-the-VM (e.g. a customer-supplied filesystem MCP) should be wrapped with `srt` as defence-in-depth — the microVM is the primary boundary, `srt` is the secondary. We do NOT vendor (fork in-tree) because upstream is active (76 commits / 90 days) and the maintenance burden of a fork outweighs the diff. We do NOT build from scratch — re-implementing seccomp + Seatbelt + bubblewrap glue is months of work they've already done under Apache-2.0. We do NOT ignore because two patterns (egress-proxy callback, mandatory-deny list) are directly reusable. The "they cover 80% of our sandbox" framing is wrong: they cover ~5% of our overall scope but ~60% of one specific sub-layer (in-microVM secondary defence). Position them as a BoM dependency under `manifesto/05-licensing-posture.md`, not a competitive overlap in `manifesto/01-audience-and-buyer.md`.

## Open questions for the user

1. Does the in-microVM secondary-defence layer warrant a dedicated ADR in `next/v1`, or fold into the existing Phase 9 (inside-microVM defence) research thread?
2. `srt` is "Beta Research Preview" with explicit "APIs may evolve." Acceptable as bundled dep for v1 GA, or do we pin to a specific commit and accept the fork-cost trade-off?
3. The Anthropic GitHub org owning this is `anthropic-experimental` — same caveat as their other experimental repos. Worth flagging in the BoM rejection-reasons table if they archive it, or treat that as ordinary upstream-risk?
