---
gsd_state_version: 1.0
milestone: v0.9.2.1
milestone_name: Multi-CLI Sub-Agent Runtime
status: roadmap_defined
stopped_at: Roadmap for v0.9.2.1 created (Phases 4-8); ready to plan Phase 4
last_updated: "2026-04-25T00:00:00.000Z"
last_activity: 2026-04-25
progress:
  total_phases: 5
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-25)

**Core value:** A single user can pull one image, wire it into Open WebUI, and get real Computer Use working end-to-end without running a corporate stack.
**Current focus:** Milestone v0.9.2.1 — Multi-CLI Sub-Agent Runtime (Codex + OpenCode as drop-in alternatives to Claude Code).

## Current Position

Phase: 4 of 8 (Env switch + adapter scaffolding) — next up
Plan: — (run `/gsd-plan-phase 4`)
Status: Ready to plan Phase 4
Last activity: 2026-04-25 — Milestone v0.9.2.1 roadmap created (5 phases: 4–8)

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

### Pending Todos

- After Phase 03 merges: comment on issue #40 with fix version and close; comment on PR #41 with pointer to merged PR, credit @rahxam.
- Issue #1 (security review): separate decision — likely close with "answered, no reporter response for 2+ weeks".
- Add CI smoke tests for sandbox image and browser — `.planning/todos/pending/2026-04-13-add-ci-smoke-tests-for-sandbox-image-and-browser.md`

### Blockers/Concerns

None.

## Session Continuity

Last session: 2026-04-25
Stopped at: Roadmap for milestone v0.9.2.1 created (Phases 4–8). Next: `/gsd-plan-phase 4`.
Resume file: None
