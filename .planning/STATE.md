---
gsd_state_version: 1.0
milestone: v0.9.1.0
milestone_name: — Open WebUI 0.9 Compatibility
status: executing
stopped_at: Completed 05-01-PLAN.md
last_updated: "2026-04-23T23:51:50.827Z"
last_activity: 2026-04-23
progress:
  total_phases: 6
  completed_phases: 3
  total_plans: 7
  completed_plans: 6
  percent: 86
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-23)

**Core value:** A single user can pull one image, wire it into Open WebUI, and get real Computer Use working end-to-end without running a corporate stack.
**Current focus:** Phase 05 — frontend-patches

## Current Position

Phase: 05 (frontend-patches) — EXECUTING
Plan: 2 of 2
Status: Ready to execute
Last activity: 2026-04-23

## Performance Metrics

**Velocity:**

- Total plans completed (all milestones): 4
- Phase 01 (v0.8.12.7) execution: 25m
- Phase 02 (v0.8.12.8) execution: shipped 2026-04-12
- Phase 03 (v0.8.12.9 code only — folded into v0.9.1.0) execution: shipped 2026-04-12

**By Phase:**

| Phase | Plans | Status |
|-------|-------|--------|
| v0.8.12.7 / Phase 01 System Prompt Extraction | 1/1 | ✅ Shipped 2026-04-12 |
| v0.8.12.8 / Phase 02 Preview Filter UX | 1/1 | ✅ Shipped 2026-04-12 |
| v0.8.12.9 / Phase 03 Claude Code Gateway Compatibility | 3/3 | ✅ Code shipped 2026-04-12 (no dedicated release — folded into v0.9.1.0 per 2026-04-23 decision) |
| v0.9.1.0 / Phase 04+ Open WebUI 0.9 Compatibility | 0/0 | 🚧 Defining requirements |
| Phase 04 P01 | 20m | 5 tasks | 2 files |
| Phase 05 P01 | 78m | 5 tasks | 4 files |

## Accumulated Context

### Roadmap Evolution

- 2026-04-12: Phase 2 (Preview Filter UX) marked shipped after filter v3.2.0 merged (b08d472) and docs landed (d79f730).
- 2026-04-12: Phase 3 added — Claude Code Gateway Compatibility. Fixes issue #40; inspired by PR #41 but reimplemented with tests and without the Traefik / deploy-specific churn.
- 2026-04-12: Phase 3 code shipped via commit 38347fd; no release commit cut as `v0.8.12.9`.
- 2026-04-19: v0.8.12.8 released with filter v4.1.0, dropping `"artifact"`/`"both"` preview modes (they broke the `fix_preview_url_detection` frontend patch — closes #43). `PUBLIC_BASE_URL` + server-owned public URL via `X-Public-Base-URL` header shipped. See CHANGELOG.md and PR #64/#65.
- 2026-04-21: Upstream Open WebUI shipped `v0.9.0` and `v0.9.1` on the same day.
- 2026-04-23: Milestone v0.9.1.0 started. Scope: upgrade base `0.8.12` → `0.9.1`, rewrite all 8 patches, roll Phase 3 gateway code into the new release's CHANGELOG (no separate `v0.8.12.9` release).

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- v0.9.1.0 (new): Fold Phase 3 (gateway compatibility) into `v0.9.1.0` CHANGELOG instead of back-releasing `v0.8.12.9`. Rationale: code is on `main` since 2026-04-12; a separate tag now just bifurcates the CHANGELOG. Confirmed by user 2026-04-23.
- v0.9.1.0 (new): Rewrite every patch (all 8, including the 4 currently commented out) against v0.9.1 upstream. Do NOT try to rebase regexes. Minor-version upstream bumps recompile the Svelte frontend (new minified variable names) and typically shuffle `middleware.py` — regex rebase would silently no-op. Confirmed by user 2026-04-23.
- v0.9.1.0 (new): Treat this as a real multi-phase milestone, not a single "bump + rebuild" task. Confirmed by user 2026-04-23.
- v0.9.1.0 (new): Pin to upstream `0.9.1` as the milestone target. If upstream ships `0.9.2` mid-milestone, stay on `0.9.1` — moving targets make the patch-rewrite unverifiable.
- v0.9.1.0 (new): Do not create a git tag or push tags autonomously. User batches releases manually. (Global memory rule.)
- [Phase 04]: Phase 4 verdict: all 8 patches classified rewrite (not obsolete); 6 rewrite-regex, 2 rewrite-entirely
- [Phase 05]: Regex shape unchanged from v0.8.12 — dry-run at v0.9.1 matched exactly once for both patches; no tolerances needed.
- [Phase 05]: Fail-loud sys.exit(1) shipped regardless of regex match — primary guard against silently-broken images on future upstream refactors.

### Pending Todos

- After Phase 03 merges: comment on issue #40 with fix version and close; comment on PR #41 with pointer to merged PR, credit @rahxam, close (or let author close). **Status:** Ready to execute
- Issue #1 (security review): separate decision — likely close with "answered, no reporter response for 2+ weeks".
- Add CI smoke tests for sandbox image and browser — `.planning/todos/pending/2026-04-13-add-ci-smoke-tests-for-sandbox-image-and-browser.md`

### Blockers/Concerns

- **Frontend-patch risk:** `fix_artifacts_auto_show.py` and `fix_preview_url_detection.py` target specific patterns in Open WebUI's compiled Svelte chunks. 0.9.x almost certainly reshuffles minified variable names — both patches will need their regexes fully rewritten.
- **Backend-patch risk:** `fix_tool_loop_errors.py` anchors on the exact body of `middleware.py` try/except for tool-loop streaming. Upstream may have refactored the tool-loop error path between 0.8.12 and 0.9.1.
- **No automated end-to-end test:** docker image tests (`./tests/test-docker-image.sh`) verify image surface, not runtime UI behaviour. Patch correctness will rely on manual smoke tests against a running image.

## Session Continuity

Last session: 2026-04-23T23:51:50.825Z
Stopped at: Completed 05-01-PLAN.md
Resume file: None
