---
gsd_state_version: 1.0
milestone: v0.8.12.9
milestone_name: — Claude Code Gateway Compatibility
status: executing
stopped_at: Completed 03-01-PLAN.md
last_updated: "2026-04-12T20:50:45.213Z"
last_activity: 2026-04-12
progress:
  total_phases: 2
  completed_phases: 2
  total_plans: 4
  completed_plans: 4
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-12)

**Core value:** A single user can pull one image, wire it into Open WebUI, and get real Computer Use working end-to-end without running a corporate stack.
**Current focus:** Phase 03 — claude-code-gateway-compatibility

## Current Position

Phase: 03
Plan: Not started
Status: Ready to execute
Last activity: 2026-04-12

## Performance Metrics

**Velocity:**

- Total plans completed (all milestones): 2
- Phase 01 execution: 25m
- Phase 02 execution: (shipped 2026-04-12 — see phases/02-preview-filter-ux/02-VERIFICATION.md)

**By Phase:**

| Phase | Plans | Status |
|-------|-------|--------|
| v0.8.12.7 / Phase 01 System Prompt Extraction | 1/1 | ✅ Shipped 2026-04-12 |
| v0.8.12.8 / Phase 02 Preview Filter UX | 1/1 | ✅ Shipped 2026-04-12 |
| v0.8.12.9 / Phase 03 Claude Code Gateway Compatibility | 0/0 | 🚧 Planned |
| Phase 03 P01 | 5m | 4 tasks | 4 files |

## Accumulated Context

### Roadmap Evolution

- 2026-04-12: Phase 2 (Preview Filter UX) marked shipped after filter v3.2.0 merged (b08d472) and docs landed (d79f730).
- 2026-04-12: Phase 3 added — Claude Code Gateway Compatibility. Fixes issue #40; inspired by PR #41 but reimplemented with tests and without the Traefik / deploy-specific churn.

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- v0.8.12.7: Server owns prompt content; filter owns URL shape. Preserved.
- v0.8.12.7: Filter falls back to no-injection (not stale cache) when cold + server unreachable.
- v0.8.12.8: Project default preview UX is the inline iframe artifact (`ENABLE_PREVIEW_ARTIFACT=True`). The markdown preview button is an opt-in for stock Open WebUI without frontend patches (`ENABLE_PREVIEW_BUTTON=False`).
- v0.8.12.8: Community PR #42 could not be mechanically rebased — reimplemented on v3.1.0 in #45, closed #42 as superseded.
- v0.8.12.9 (new): Hard invariant — zero-config means stock Claude Code `/login`. If the operator sets no `ANTHROPIC_*` / `CLAUDE_CODE_*` env vars on the host, the orchestrator must inject *zero* such env vars into the sandbox; Claude Code then shows its native `/login` screen. This is the default path and must not be broken.
- v0.8.12.9 (new): Do NOT mechanically merge PR #41. Reimplement its idea (env-fallback fix + gateway-vars passthrough + model-ID accept in `sub_agent`) cleanly with tests. PR #41 has a syntax error, extra Traefik labels, ~690 deleted lines from a stale rebase, and no tests — take the signal, not the patch.
- v0.8.12.9 (new): All ten gateway vars added (ANTHROPIC_MODEL, ANTHROPIC_DEFAULT_{SONNET,OPUS,HAIKU}_MODEL, CLAUDE_CODE_SUBAGENT_MODEL, CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS, DISABLE_PROMPT_CACHING{,_SONNET,_OPUS,_HAIKU}) are official Claude Code env vars verified against code.claude.com/docs — not invented.
- v0.8.12.9 (new): Existing `x-anthropic-*` HTTP header path in `mcp_tools.py:1113-1122` stays. It's dead code today but harmless — keeps per-request override available to any future Open WebUI filter that wants to inject per-user keys. Out of scope for Phase 3.
- [Phase 03]: Phase 03 Plan 01: GATEWAY-01..12 minted; context_vars default=None fix (root-cause of #40); 10-var passthrough tuple + loop in docker_manager; sub_agent accepts aliases + direct IDs

### Pending Todos

- After Phase 03 merges: comment on issue #40 with fix version and close; comment on PR #41 with pointer to merged PR, credit @rahxam, close (or let author close).
- Issue #1 (security review): separate decision — likely close with "answered, no reporter response for 2+ weeks".

### Blockers/Concerns

None.

## Session Continuity

Last session: 2026-04-12T20:26:22.946Z
Stopped at: Completed 03-01-PLAN.md
Resume file: None
