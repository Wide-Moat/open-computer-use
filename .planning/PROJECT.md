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
- ✓ System prompt extraction: `GET /system-prompt` returns fully-baked prompt (URLs + `<available_skills>` per user with default-skills fallback); `computer_link_filter.py` is a thin HTTP client with per-(chat, user) LRU cache and stale-cache fallback. Filter body shrank from ~636 to ≤ 250 lines. (Phase 1, v0.8.12.7)
- ✓ Preview filter UX: `outlet()` emits inline preview iframe artifact by default plus opt-in markdown button; every Valve documented in-file and in `docs/openwebui-filter.md` with a drift-check test. Browser-only sessions also get previews via `<details type="tool_calls">` detection. (Phase 2, v0.8.12.8; later hardened in v0.8.12.8 "filter v4.1.0" release that dropped `"artifact"`/`"both"` preview modes after they were shown to break the `fix_preview_url_detection` frontend patch.)
- ✓ Claude Code gateway compatibility: sandbox containers route Claude Code traffic to the operator-configured Anthropic-compatible destination (public Anthropic / LiteLLM / Azure / Bedrock) via 10 optional env vars, with zero-config falling back to stock `/login`; `sub_agent` MCP tool accepts direct model IDs in addition to `sonnet`/`opus`/`haiku` aliases. Code shipped on `main` in commit `38347fd` (2026-04-12) but was never cut as a dedicated `v0.8.12.9` release — folded into `v0.9.1.0`. (Phase 3, see `docs/claude-code-gateway.md`)
- ✓ Maximum MCP-native system-prompt surface (6 tiers): commit `8cd426d`.
- ✓ Single public URL on server: `FILE_SERVER_URL` → `PUBLIC_BASE_URL`, delivered to the filter via the `X-Public-Base-URL` response header on `/system-prompt`; filter no longer carries a public-URL Valve. Commit `fb079a4`.

### Active

<!-- In this milestone. -->

## Current Milestone: v0.9.1.0 Open WebUI 0.9 Compatibility

**Goal:** Upgrade the Open WebUI base from `0.8.12` to the latest upstream (`0.9.1`, released 2026-04-21), rewrite every patch in `openwebui/patches/` against the new upstream frontend/backend shape, verify all Tool/Filter behaviour still holds end-to-end, bump our version to `v0.9.1.0` (first of the new `0.9.X.Y` series), and document which Open WebUI version this release is pinned to.

**Target features:**

- Base image bump: `ghcr.io/open-webui/open-webui:0.9.1` in `openwebui/Dockerfile` and `docker-compose.webui.yml` defaults
- All 8 patches in `openwebui/patches/` rewritten against 0.9.1 upstream — 4 currently active (`fix_artifacts_auto_show`, `fix_tool_loop_errors`, `fix_preview_url_detection`, `fix_large_tool_results`) and 4 currently commented out (`fix_large_tool_args`, `fix_attached_files_position`, `fix_skip_embedding_chat_files`, `fix_skip_rag_files_native_fc`) — per explicit decision "rewrite every patch" (2026-04-23)
- End-to-end verification: image builds `--platform linux/amd64`, `init.sh` seeds Valves on fresh DB, filter + tool register without errors, preview/iframe/artifact flows still work against 0.9.x frontend
- Release `v0.9.1.0` — first release on the new `0.9.X.Y` series; CHANGELOG documents upstream compat pinning (`ghcr.io/open-webui/open-webui:0.9.1`) and rolls in the Phase 3 Claude Code gateway work that landed post-v0.8.12.8 but was never cut as `v0.8.12.9`

**Why now:** upstream shipped `0.9.0` + `0.9.1` on 2026-04-21 (minor-version bump — first since `0.8.0` in 2026-03). Users on stock `0.9.x` installs currently can't use our filter/patches because the Dockerfile default still pins `0.8.12`. Not upgrading means diverging further every week.

**Context:**
- `0.8.12` → `0.9.1` is a minor bump — upstream frontend chunks are freshly compiled (new minified variable names; every Svelte-chunk patch regex will miss on first run) and `middleware.py` internals may have shifted. Treat as "rewrite every patch", not "rebase".
- Phase 3 (Claude Code Gateway Compatibility, `v0.8.12.9`) never got its own release commit / CHANGELOG entry — the code shipped on `main` in commit `38347fd` but no `chore: release v0.8.12.9` follow-up was made. Decision (explicit, 2026-04-23): fold Phase 3 into the `v0.9.1.0` CHANGELOG instead of back-releasing `v0.8.12.9`.
- Versioning rule from `CLAUDE.md`: `v0.8.X.Y` → the first three segments track Open WebUI base. Upstream minor bump (`0.8` → `0.9`) ⇒ our version becomes `v0.9.1.0` (reset `Y=0`, `X` = upstream minor, first three track `0.9.1`).

### Out of Scope

<!-- For this milestone. Each with a reason. -->

- **Back-releasing `v0.8.12.9`** — Phase 3 gateway code is already on `main` since commit `38347fd`; cutting a retro patch release now just bifurcates the CHANGELOG. Fold into `v0.9.1.0` instead.
- **Forking Open WebUI as a git submodule / maintaining a true patch-set** — tempting for a minor bump, but a separate architectural decision. Sticks with the runtime-patch strategy for now; revisit if `0.10.x` bumps get painful again.
- **Upgrading past `0.9.1`** — `0.9.1` is the latest tag at milestone start (2026-04-23). If upstream ships `0.9.2` mid-milestone we stay on `0.9.1` to avoid a moving target. Chase the new tag in the next milestone.
- **Porting v0.9.x new-upstream features** (whatever Open WebUI added in `0.9.0`/`0.9.1`) into our Tool/Filter — separate work; this milestone is pure compatibility, not feature intake.
- Russian-language skill triggers and i18n — repo is English-only per `CLAUDE.md`.
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
| Fold v0.8.12.9 (Phase 3 gateway) into v0.9.1.0 instead of cutting a back-release | Gateway code has been on `main` since 2026-04-12; a separate `v0.8.12.9` tag now just bifurcates the CHANGELOG and adds a release-notes page nobody will read. User explicitly confirmed on 2026-04-23. | 🚧 v0.9.1.0 in progress |
| Rewrite every patch (all 8, including the 4 commented-out) against v0.9.1 upstream rather than try to rebase regexes | Minor-version upstream bumps recompile the Svelte frontend (new minified variable names) and typically shuffle `middleware.py`. Rebase-by-regex would produce silent no-ops that only show as runtime bugs. Treat as clean-slate rewrite, test each patch in isolation against a fresh v0.9.1 image. User explicitly confirmed on 2026-04-23. | 🚧 v0.9.1.0 in progress |
| Versioning bump `v0.8.12.8` → `v0.9.1.0` (not `v0.8.13.0` or `v0.9.0.0`) | `CLAUDE.md` rule: first three segments track upstream Open WebUI. Latest upstream is `0.9.1`, so `0.9.1.Y` is the series; `Y=0` because this is the first release of the series. Skipping `0.9.0.x` entirely is fine — upstream released `0.9.0` + `0.9.1` on the same day (2026-04-21). | 🚧 v0.9.1.0 in progress |

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
*Last updated: 2026-04-23 — milestone v0.9.1.0 (Open WebUI 0.9 Compatibility) started*
