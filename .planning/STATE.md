---
gsd_state_version: 1.0
milestone: v0.9.2.1
milestone_name: — Multi-CLI Sub-Agent Runtime
status: executing
stopped_at: Completed 06-04-PLAN.md
last_updated: "2026-04-26T02:00:36.855Z"
last_activity: 2026-04-26
progress:
  total_phases: 5
  completed_phases: 3
  total_plans: 15
  completed_plans: 15
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-25)

**Core value:** A single user can pull one image, wire it into Open WebUI, and get real Computer Use working end-to-end without running a corporate stack.
**Current focus:** Phase 6 — per-cli-auth-config

## Current Position

Phase: 6 (per-cli-auth-config) — EXECUTING
Plan: 5 of 5
Status: Ready to execute
Last activity: 2026-04-26

Progress: [██░░░░░░░░] 20% (1/5 phases in current milestone)

## Performance Metrics

**Velocity:**

- Total plans completed (all milestones): 5
- Phase 01 execution: 25m
- Phase 02 execution: shipped 2026-04-12
- Phase 03 execution: shipped 2026-04-25 (v0.9.2.0)

**By Phase:**

| Phase | Plans | Status |
|-------|-------|--------|
| v0.8.12.7 / Phase 01 System Prompt Extraction | 1/1 | ✅ Shipped 2026-04-12 |
| v0.8.12.8 / Phase 02 Preview Filter UX | 1/1 | ✅ Shipped 2026-04-12 |
| v0.8.12.9 / Phase 03 Claude Code Gateway Compatibility | 3/3 | ✅ Shipped 2026-04-25 (v0.9.2.0) |
| v0.9.2.1 / Phase 04 Env switch + adapter scaffolding | 5/5 | ✅ Complete 2026-04-25 |
| v0.9.2.1 / Phase 05 Adapter layer | 0/? | Not started |
| v0.9.2.1 / Phase 06 Per-CLI auth + config rendering | 0/? | Not started |
| v0.9.2.1 / Phase 07 Cost guardrail + ttyd UX | 0/? | Not started |
| v0.9.2.1 / Phase 08 Operator docs | 0/? | Not started |
| Phase 04 P01 | 1m 15s | 2 tasks | 2 files |
| Phase 04 P02 | 3m | 4 tasks | 5 files |
| Phase 04 P05 | 3m | 3 tasks | 2 files |
| Phase 04 P03 | 1m | 2 tasks | 2 files |
| Phase 04 P04 | 3m 30s | 3 tasks | 4 files |
| Phase 05-adapter-layer P01 | 3min | 2 tasks | 2 files |
| Phase 05 P02 | ~6min | 2 tasks | 2 files |
| Phase 05 P04 | 6m | 3 tasks | 5 files |
| Phase 05 P05 | 25min | 4 tasks | 5 files |
| Phase 05 P06 | 8min | 1 tasks | 1 files |
| Phase 06 P01 | 10min | 2 tasks | 1 files |
| Phase 06 P02 | 5min | 2 tasks | 1 files |
| Phase 06-per-cli-auth-config P03 | 4min | 1 tasks | 1 files |
| Phase 06 P04 | 12m | 2 tasks | 2 files |

## Accumulated Context

### Roadmap Evolution

- 2026-04-25: Milestone v0.9.2.1 (Multi-CLI Sub-Agent Runtime) roadmap created. Five phases (4–8) derived from 22 requirements (CLI-01..03, ADAPT-01..06, AUTH-01..04, TERM-01..03, TEST-01..06, DOCS-MULTICLI-01..04). Tests are NOT deferred — they ship in the same phase as the code under test (TEST-02+TEST-05 in P4, TEST-03 in P5, TEST-01+TEST-06 in P6, TEST-04 in P7).
- 2026-04-25: Phase 3 shipped in v0.9.2.0 release. Milestone v0.8.12.9 closed.

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- v0.9.2.1: `SUBAGENT_CLI` is boot-time, not per-call (per-call would multiply test surface).
- v0.9.2.1: Adapter layer hides CLI differences behind unchanged MCP `sub_agent` surface; skills don't change.
- v0.9.2.1: `claude` remains default (unset = byte-identical backwards compat).
- v0.9.2.1: OpenCode + qwen3-coder + OpenRouter is the worked headline recipe.
- v0.9.2.1: Tests are mandatory, ship with the code under test, not deferred to a final phase.
- v0.9.2.1: `openwebui/init.sh` MUST NOT be touched (saved-memory hard rule); regression-grep test (TEST-05) lives in Phase 4 onward.
- [Phase 04]: Used print(stderr)+sys.exit(1) shape for SUBAGENT_CLI hard-fail (NOT sys.exit(message)) — guarantees stderr visibility under pytest/lifespan; resolver tests must use capfd not capsys.
- [Phase 04]: Picked D5 shape (a) — explicit single-line extra_env["SUBAGENT_CLI"]=SUBAGENT_CLI assignment over module-level tuple — Phase 6 per-CLI passthroughs use the existing if-guarded tuple pattern, no need for runtime-level tuple yet.
- [Phase 04]: Standalone bash test for TEST-05 (init.sh sha256) instead of integration into test-project-structure.sh — matches existing one-test-per-script-file pattern; CI runs alongside other standalone scripts.
- [Phase 04]: capfd (not capsys) for stderr capture in resolver tests — print(..., file=sys.stderr)+sys.exit(1) shape requires file-descriptor capture.
- [Phase 05-adapter-layer]: Env vars read at call-time inside _resolve_* (not module-load) so tests monkeypatch.setenv without importlib.reload.
- [Phase 05-adapter-layer]: _CLAUDE_ALIAS_MAP values are zero-arg lambdas to preserve v0.9.2.0 mcp_tools.py:909-924 fallback semantics.
- [Phase 05]: Plan 05-04: Used pytest.mark.xfail(strict=True) as a cross-plan handover marker for the BLOCKER 1 ClaudeAdapter returncode patch — XPASS-under-strict forces the marker removal in lockstep with the 05-05 fix.
- [Phase 05]: BLOCKER 1 fix + xfail removal in same commit (Task 0) — strict-xfail XPASS would otherwise hard-fail CI
- [Phase 05]: Codex --cd workdir created by dispatch (extracted from argv) rather than via separate adapter hook — keeps CliAdapter Protocol minimal
- [Phase 05]: _format_sub_agent_result fully deleted (rendering inlined in sub_agent) rather than kept as thin wrapper — reduces indirection around rc-switch logic
- [Phase 06]: Gate legacy Anthropic standalone block and ANTHROPIC_CUSTOM_HEADERS on SUBAGENT_CLI=='claude' to fully close Pitfall 1 across all auth injection paths
- [Phase 06]: Pin OPENCODE_CONFIG=/tmp/opencode.json into container Env (not just entrypoint export) so docker exec subprocesses inherit it (Pitfall 7)
- [Phase 06-per-cli-auth-config]: 06-03: Hardcoded OpenCode model default in JSON since single-quoted heredoc cannot expand bash vars; OPENCODE_MODEL env override happens at OpenCode CLI runtime
- [Phase 06]: test_passthrough_isolation captures containers.create kwargs (not .run — that is the ephemeral mkdir shim)
- [Phase 06]: Docker smoke step uses long-running container + docker exec entrypoint twice + GATED-SENTINEL overwrite to verify marker gating

### Pending Todos

- After Phase 03 merges: comment on issue #40 with fix version and close; comment on PR #41 with pointer to merged PR, credit @rahxam.
- Issue #1 (security review): separate decision — likely close with "answered, no reporter response for 2+ weeks".
- Add CI smoke tests for sandbox image and browser — `.planning/todos/pending/2026-04-13-add-ci-smoke-tests-for-sandbox-image-and-browser.md`

### Blockers/Concerns

None.

## Session Continuity

Last session: 2026-04-26T02:00:36.852Z
Stopped at: Completed 06-04-PLAN.md
Resume file: None
