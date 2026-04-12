# Open Computer Use

## What This Is

An MCP-first, self-hostable Computer Use stack: a Python orchestrator (FastAPI) that spawns per-user Ubuntu sandbox containers with Claude Code CLI, Playwright-controlled Chromium, a web terminal (ttyd), and a curated set of skills (pptx/xlsx/docx/pdf/sub-agent/playwright-cli etc.). Open WebUI integrates via a Tool (`computer_use_tools.py`) and a Filter (`computer_link_filter.py`). This repository is the community fork of an internal Computer Use platform, stripped to a generic, corporate-free baseline.

## Core Value

A single user can pull one image, wire it into Open WebUI, and get real Computer Use (browser + terminal + file generation) working end-to-end, without running a corporate stack.

## Requirements

### Validated

<!-- Capabilities already shipped and working in the codebase. -->

- ✓ MCP orchestrator exposing `bash_tool`, `view`, `str_replace`, `file_create`, `sub_agent` over Streamable HTTP — `computer-use-server/mcp_tools.py`
- ✓ Per-chat Docker sandbox with Playwright/Chromium, ttyd terminal, file server — `computer-use-server/docker_manager.py`, `Dockerfile`
- ✓ Open WebUI bridge: Tool + Filter injecting Computer Use system prompt and file/archive links — `openwebui/tools/`, `openwebui/functions/`
- ✓ Curated public skills bundled in the image — `skills/public/*`
- ✓ SINGLE_USER_MODE onboarding path — no X-Chat-Id required
- ✓ MCP Registry manifest + Docker image release workflow
- ✓ SPDX headers + BUSL-1.1 license model
- ✓ CodeQL + Dependabot security baseline, Pillow 12 + CVE bumps
- ✓ Test suites: Docker image verification, project structure, no-corporate guard, pytest deps guard, filter fixes (v3.0.3)
- ✓ Sub-agent cost guardrails: COSTLY markings, `max_turns=25`, scope limited to code-only tasks
- ✓ System prompt extraction: `GET /system-prompt` returns fully-baked prompt (URLs + `<available_skills>` per user with default-skills fallback); `computer_link_filter.py` is a thin HTTP client with per-(chat, user) LRU cache and stale-cache fallback. Filter body shrank from ~636 to ≤ 250 lines.

### Active

<!-- In this milestone. -->

## Current Milestone: v0.8.12.8 Preview Filter UX

**Goal:** Expose the already-shipped `/preview/{chat_id}` SPA to stock Open WebUI users by teaching the filter's `outlet()` to emit an inline iframe artifact (default) and an opt-in markdown preview button, while preserving every v3.1.0 correctness invariant and documenting all Valves in one authoritative place.

**Target features:**

- Inline iframe preview artifact in assistant messages (`ENABLE_PREVIEW_ARTIFACT=True` default — project's opinionated UX)
- Opt-in markdown preview button for stock Open WebUI without artifact rendering (`ENABLE_PREVIEW_BUTTON=False` default)
- Authoritative Valve reference: in-file `VALVES:` docstring block + external docs page + drift-check test

**Why now:** community PR #42 by `rahxam` surfaced real demand for this UX; that PR targets v3.0.2 and cannot be mechanically rebased onto v3.1.0 without losing the hardening done in Phase 1 (`role == "assistant"` guard, `isinstance(content, str)` guard, `chat_id`-scoped `file_url_pattern`, `rstrip("/")` base). We re-implement the idea on top of v3.1.0 and credit the author.

**Context:** server endpoint `/preview/{chat_id}` already exists (`computer-use-server/app.py:1102`) — this milestone is pure filter + docs work, no server changes.

### Out of Scope

<!-- For this milestone. Each with a reason. -->

- Preview SPA + `<details>` migration logic from the internal filter chain v3.3–v3.5 — not applicable to current community UI surface.
- Browser-keyword heuristic for preview injection (internal v3.8 bug-fix) — community has no preview injection to protect.
- Shipping a default external skill provider (e.g. running a settings-wrapper service in the image) — out of scope; community ships with provider URL empty, and the server falls back to default public skills. Operators who want per-user skills wire their own provider via env.
- Russian-language skill triggers and i18n for preview UI — community is English-only per `CLAUDE.md`.
- Corporate CA cert bundle, corporate peer-matching skill, NTLM/Kerberos overlay — corporate specifics.
- Retroactive bump of bundled `claude-code` CLI — image pulls `@latest`, no pinning needed.

## Context

- **Forked from:** internal Computer Use fork at `computer_link_filter` v3.0.2. Since the fork, the internal version advanced to v3.8.0 by moving the system prompt to the server, adding per-user skills and a preview SPA. Community never received those forward ports.
- **Recent deltas ported from internal fork:** sub-agent scope restriction to code-only tasks, two silent bugs in filter (trailing slash, missing `chat_id`).
- **Users:** self-hosters wiring Computer Use into their own Open WebUI; evaluators looking at the architecture; contributors. No corporate dependency.
- **Distribution:** GHCR image + MCP Registry entry. Runs behind a reverse proxy (nginx etc.), not directly exposed.

## Constraints

- **License:** BUSL-1.1 for project source; MIT for `describe-image` and `sub-agent` skills (separate LICENSE.txt). All new files carry SPDX headers.
- **Language policy:** repository is English-only — code, comments, commits, PRs, docs. No Russian or other non-English strings in tracked files.
- **Versioning:** `v0.8.X.Y` — `0.8.X` tracks the Open WebUI base; `Y` is patch-only, bumped per release.
- **Platform:** Docker images built `--platform linux/amd64`. Tests require Docker running.
- **Sandbox disk budget:** `/home/assistant` (volume mount point) must stay under 1 MB in the image. npm libraries live in `/home/node_modules/`, CLI tools in `/usr/local/lib/node_modules_global/`.
- **MCP contract:** `computer-use-server/mcp_tools.py` exposes tools over Streamable HTTP; any new endpoint on the server must not break this contract.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Fork at internal v3.0.2 instead of later | v3.2+ introduced server-side prompt and per-user skills, tightly coupled to internal services | ✅ Closed by current milestone — v3.2/v3.6/v3.7 gaps ported in Phase 1 |
| Port the full server-side substitution pipeline from the internal v3.7 endpoint | Endpoint accepts `chat_id` + `user_email` and returns a fully-baked prompt (URLs + `<available_skills>`). Client does a single fetch and injects the body as-is. Single source of truth for prompt assembly; per-user skills become possible without client rewrites. | ✅ Shipped (Phase 1) |
| Per-user skills via optional external provider, graceful fallback built-in | Community ships without `MCP_TOKENS_URL`; server returns default public skills in that case. Operators who self-host a provider get per-user `<available_skills>` for free. Same call path either way. | ✅ Shipped (Phase 1) |
| Filter caches `(chat_id, user_email) → prompt` in an LRU (5-min TTL, 100 entries) with stale-cache fallback on fetch failure | Serving a slightly-stale prompt is better UX than silently disabling Computer Use. Skip-injection remains the fallback only when cache is cold. Matches the internal v3.8.0 behaviour. Cache key includes `user_email` to prevent one user's baked `<available_skills>` from leaking to another user on the same `chat_id`. | ✅ Shipped (Phase 1) |
| Keep `file_base_url` / `archive_url` legacy query params on the endpoint | Copied verbatim from the internal implementation for forward/backward compatibility with existing deployments; cheap to carry. | ✅ Shipped (Phase 1) |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-12 — milestone v0.8.12.8 (Preview Filter UX) started*
