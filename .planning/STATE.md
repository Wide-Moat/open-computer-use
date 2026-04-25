---
gsd_state_version: 1.0
milestone: v0.9.2.1
milestone_name: — Multi-CLI Sub-Agent Runtime
status: executing
stopped_at: Completed 04-03-PLAN.md (warn_subagent_cli startup banner)
last_updated: "2026-04-25T23:12:00.116Z"
last_activity: 2026-04-25
progress:
  total_phases: 3
  completed_phases: 2
  total_plans: 9
  completed_plans: 8
  percent: 89
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-25)

**Core value:** A single user can pull one image, wire it into Open WebUI, and get real Computer Use working end-to-end without running a corporate stack.
**Current focus:** Phase 4 — env-switch-adapter-scaffolding

## Current Position

Phase: 4 (env-switch-adapter-scaffolding) — EXECUTING
Plan: 5 of 5
Status: Ready to execute
Last activity: 2026-04-25

Progress: [░░░░░░░░░░] 0% (0/5 phases in current milestone)

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
| v0.9.2.1 / Phase 04 Env switch + adapter scaffolding | 0/? | Not started |
| v0.9.2.1 / Phase 05 Adapter layer | 0/? | Not started |
| v0.9.2.1 / Phase 06 Per-CLI auth + config rendering | 0/? | Not started |
| v0.9.2.1 / Phase 07 Cost guardrail + ttyd UX | 0/? | Not started |
| v0.9.2.1 / Phase 08 Operator docs | 0/? | Not started |
| Phase 04 P01 | 1m 15s | 2 tasks | 2 files |
| Phase 04 P02 | 3m | 4 tasks | 5 files |
| Phase 04 P05 | 3m | 3 tasks | 2 files |
| Phase 04 P03 | 1m | 2 tasks | 2 files |

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

### Pending Todos

- After Phase 03 merges: comment on issue #40 with fix version and close; comment on PR #41 with pointer to merged PR, credit @rahxam.
- Issue #1 (security review): separate decision — likely close with "answered, no reporter response for 2+ weeks".
- Add CI smoke tests for sandbox image and browser — `.planning/todos/pending/2026-04-13-add-ci-smoke-tests-for-sandbox-image-and-browser.md`

### Blockers/Concerns

None.

## Session Continuity

Last session: 2026-04-25T23:12:00.114Z
Stopped at: Completed 04-03-PLAN.md (warn_subagent_cli startup banner)
Resume file: None
