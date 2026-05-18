<!-- SPDX-License-Identifier: BUSL-1.1 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# 21 — `environment-runner` pattern (inspiration-only)

> Reference: pattern notes under [`sandboxd/anthropic/`](../../../sandboxd/anthropic/) describing the Go-language session agent that runs **above** `process_api` in Anthropic's Claude Code Web product.
>
> **Status: inspiration-only, not on our roadmap.** Open Computer Use's sub-agent layer is a thin CLI dispatcher (Claude Code / Codex / OpenCode invoked as one-shot tools from inside the sandbox), not a long-lived session agent that polls a control plane. This digest exists to keep the pattern catalogue complete, and as a reference if we ever decide to grow our sub-agent orchestration into something durable. **No phase currently consumes this material.**

## 1. What `environment-runner` is

A ~27 MB Go binary running inside the sandbox **as a child of `process_api`**. The pattern notes describe its module path as `github.com/anthropics/anthropic/api-go/environment-manager`.

Where `process_api` is a transport + lifecycle supervisor with no knowledge of LLMs, MCP, or agents, `environment-runner` is the **session-aware Go agent** that knows about Claude Code, MCP servers, git, deploy, and BYOC. It is the layer that would map to "our L1 agent" if we were doing what Anthropic is reported to do. We are not.

## 2. Internal package layout (as catalogued)

```
api/               Anthropic API client — session ingress, work polling
auth/              GitHub app token provider
claude/            Claude Code install, upgrade, execution
config/            Session modes (new / resume / resume-cached / setup-only)
envtype/
  ├─ anthropic/    Anthropic-hosted environment
  └─ byoc/         Bring Your Own Cloud
gitproxy/          Git credential proxy server
input/             Stdin parser + secret handling
manager/           Session manager, MCP config, skill extraction
mcp/
  └─ servers/
     ├─ codesign/  Code signing MCP server
     └─ supabase/  Supabase integration MCP server
orchestrator/      Poll loop, hooks, whoami
podmonitor/        Kubernetes lease manager (BYOC mode)
process/           Process exec + script runner
sandbox/           Sandbox runtime config
session/           Activity recorder
sources/           Git clone + source classification
tunnel/            WebSocket tunnel + action handlers
  └─ actions/
     ├─ deploy/    Antspace + Vercel deploy clients
     ├─ snapshot/  File snapshots
     └─ status/    Status reporting
util/              Git helpers, retry, stream tailer
```

## 3. What it does (single-paragraph summary per area)

- **Polling loop.** Long-poll Anthropic's API for session assignments; when one arrives, install/upgrade Claude Code, clone the requested git source, start MCP servers, and stream activity back.
- **MCP server hosting.** Owns two internal MCP servers (`codesign`, `supabase`) and discovers project-specific ones via skill extraction.
- **Git workflow.** Clones, branches, manages credentials via a local proxy so Claude Code never sees raw tokens.
- **Deploy.** Two pluggable clients — Antspace (internal Anthropic PaaS, NDJSON status stream) and Vercel (SHA-deduped uploads, polled status).
- **BYOC.** When the customer brings their own k8s cluster, holds a pod lease and reports back; in Anthropic-hosted mode this code is dead.
- **Tunnel.** A WebSocket tunnel back to the control plane carrying snapshot, deploy, and status actions.

## 4. Why this is **not** our model

Open Computer Use is **MCP-server-first**, sub-agent-second. The control flow is:

```
LLM (host) ──MCP──> L4 (computer-use-server) ──Docker──> Sandbox
                                                              ├── MCP tools (bash, view, …)
                                                              └── (optional) sub-agent CLI on demand
```

The Anthropic flow is the reverse: a **session-owning agent inside the sandbox** polls the control plane for work, then drives Claude Code locally. The two designs disagree on which side initiates.

If we ever ship a "long-running coding session" product, **then** this digest matters. Today it does not.

## 5. Pieces that might be useful later (and only later)

If we ever build durable sub-agent sessions, these would be the parts to study, in roughly this order of relevance:

| Piece | What it solves | When it might matter for us |
|---|---|---|
| `gitproxy/` | Sub-agent CLIs never see raw git tokens | If we add multi-tenant git workflows to sub-agents |
| `manager/` MCP config + skill extraction | Standard way to wire skills + MCP servers per session | If our skill system grows beyond the current static set |
| `input/` secret handling | Stdin-fed secrets that never hit disk or logs | Cross-cuts with antipattern A1 |
| `orchestrator/` poll loop with hooks | Pre/post-session lifecycle hooks | If we move from one-shot to durable sessions |
| `tunnel/actions/snapshot/` | File snapshots as a first-class action | If we ship session-resume in Phase 10+ |
| `mcp/servers/codesign/` shape | In-sandbox MCP server hosting pattern | We already do this; the Anthropic shape is a useful comparison |

Pieces we'd **never** import: `api/` (Anthropic-specific control plane), `claude/` (Claude Code install logic), `envtype/anthropic/` (their PaaS), `tunnel/actions/deploy/` (Antspace + Vercel — product-specific).

## 6. Why Go for the L1-equivalent at Anthropic

Worth noting since our ADR-0002 just landed on **Rust** for our L1. The Anthropic split, as catalogued, is:
- `process_api` = Rust. PID 1 needs a tiny static binary, kernel-adjacent code, predictable allocations.
- `environment-runner` = Go. Ecosystem fit — MCP libraries, git tooling, cobra CLI, OpenTelemetry, gRPC. The agent is large (~27 MB) and not on the hot path.

The split mirrors a working precedent: small Rust supervisor at the floor, larger Go agent on top. If our sub-agent orchestration ever grows that complex, this is a credible reference pattern. Today our sub-agent layer is a thin CLI dispatcher in `computer-use-server/cli_runtime.py`, which is the right size for what it does.

## 7. Adopt / Adapt / Reject

| Element | Decision | Notes |
|---|---|---|
| Long-poll session agent inside the sandbox | **Reject** | Inverts our MCP-server-first control flow |
| In-sandbox MCP server hosting | **Already-have** | We do this in `mcp_tools.py`; not new |
| Git credential proxy | **Defer** | Not on roadmap; revisit if multi-tenant sub-agent git flows ship |
| Skill extraction at session start | **Defer** | Our skill system already does this statically; revisit only if sessions become durable |
| Antspace / Vercel deploy clients | **Reject** | Product-specific to the reference design |
| BYOC pod lease manager | **Reject** | Out of scope; we are one-tenant-per-deployment today |
| File-snapshot action | **Defer to Phase 10+** | Relevant only if we ship session-resume |
| Go-on-top-of-Rust two-language split | **Reference pattern** | Validates that our Rust L1 + (possibly Go) L4 mix is a working shape |

## 8. What this digest does **not** trigger

- No ADR changes (existing ADR-0001 L4=Go gate at Phase 6 is untouched).
- No `architecture/*` changes (this material has no current Phase).
- No new antipatterns.

It is a **bookmark for future-us**, kept in the same directory as the rest of the catalogue so it doesn't get lost. If a future phase needs durable session agents, start here, then re-read `process_api_re/`.

## Related

- Sibling digests: [`13-anthropic-sandbox-runtime.md`](./13-anthropic-sandbox-runtime.md), [`16-anthropic-production-sandbox-observed.md`](./16-anthropic-production-sandbox-observed.md), [`17-anthropic-claude-code-remote-env-observed.md`](./17-anthropic-claude-code-remote-env-observed.md), [`19-anthropic-process-api.md`](./19-anthropic-process-api.md)
- Architecture: none (this material has no Phase consumer today)
