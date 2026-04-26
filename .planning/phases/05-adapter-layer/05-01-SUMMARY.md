---
phase: 05-adapter-layer
plan: 01
subsystem: infra
tags: [python, sub-agent, cli-runtime, model-resolution, adapter]

requires:
  - phase: 04-env-switch-adapter-scaffolding
    provides: "Cli StrEnum, _ADAPTERS dispatch dict, ANTHROPIC_DEFAULT_*_MODEL constants"
provides:
  - "resolve_subagent_model(alias_or_id, cli) -> (model_id, display_name) public API"
  - "_resolve_claude / _resolve_codex / _resolve_opencode private per-CLI helpers"
  - "_CLAUDE_ALIAS_MAP / _OPENCODE_ALIAS_MAP module-level dicts"
  - "CODEX_SUB_AGENT_DEFAULT_MODEL + OPENCODE_SUB_AGENT_DEFAULT_MODEL env-bound module constants"
  - "Hard-fail (ValueError) when Claude-only alias hits SUBAGENT_CLI=codex (Pitfall 3 mitigation)"
affects: [05-02-codex-adapter, 05-03-opencode-adapter, 05-05-dispatch-and-mcp-rewrite, 05-04-tests]

tech-stack:
  added: []
  patterns:
    - "Per-CLI dispatch via lookup tables + private _resolve_* helpers"
    - "Env vars read at function-call time (not module-load) so tests can monkeypatch.setenv between calls"
    - "Hard-fail on Claude-only aliases to non-Claude CLIs with actionable error message"

key-files:
  created: []
  modified:
    - "computer-use-server/cli_runtime.py (added 99 lines: import os + extended docker_manager import + ADAPT-06 block at lines 65-159)"
    - "computer-use-server/docker_manager.py (added 5 lines: CODEX_/OPENCODE_SUB_AGENT_DEFAULT_MODEL constants at lines 72-76)"

key-decisions:
  - "Read env vars (CODEX_SUB_AGENT_DEFAULT_MODEL etc.) inside _resolve_* via os.getenv at call time — not at module-import time — so tests can flip env vars without importlib.reload."
  - "_CLAUDE_ALIAS_MAP values are zero-arg lambdas (not strings) so the ANTHROPIC_DEFAULT_*_MODEL fallback is evaluated at call time, matching v0.9.2.0 mcp_tools.py:909-924 semantics."
  - "OpenCode missing-prefix is a soft warning (print) not a raise — opencode's own error path will surface the real failure."

patterns-established:
  - "Public dispatch + private _resolve_<cli> helpers — extensible to future CLIs without touching the public function."
  - "Tuple return (model_id, display_name) lets adapters and result formatters use different strings for argv vs UI."

requirements-completed: [ADAPT-06]

duration: ~3min
completed: 2026-04-26
---

# Phase 5 Plan 01: resolve_subagent_model + per-CLI default-model constants Summary

**Per-CLI model resolution primitive (resolve_subagent_model + Claude/Codex/OpenCode alias maps) lifted from inline mcp_tools.py logic into cli_runtime.py with hard-fail on Claude-only aliases hitting codex.**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-04-26T00:46Z
- **Completed:** 2026-04-26T00:48Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- New public `resolve_subagent_model(alias_or_id, cli) -> tuple[str, str]` in `cli_runtime.py` (line 142) covering all three CLIs.
- Three private dispatchers `_resolve_claude` / `_resolve_codex` / `_resolve_opencode` with per-CLI default fallback chains.
- Hard-fail (`ValueError`) when a Claude-only alias (sonnet/opus/haiku) is requested for `SUBAGENT_CLI=codex` — Pitfall 3 mitigated at resolve time, before any subprocess spawn.
- Two new env-bound module constants (`CODEX_SUB_AGENT_DEFAULT_MODEL`, `OPENCODE_SUB_AGENT_DEFAULT_MODEL`) in `docker_manager.py` (lines 75-76).
- Phase 4 test suite (23 tests in `test_cli_runtime.py` + `test_subagent_claude_compat.py`) stays green — zero regression on existing surfaces.

## Task Commits

1. **Task 1: Add CODEX_/OPENCODE_SUB_AGENT_DEFAULT_MODEL constants to docker_manager.py** — `1cf6032` (feat)
2. **Task 2: Add resolve_subagent_model + per-CLI _resolve_* helpers to cli_runtime.py** — `652ea1d` (feat)

**Plan metadata commit:** added separately via final_commit step.

## Files Created/Modified

- `computer-use-server/docker_manager.py` — Added `CODEX_SUB_AGENT_DEFAULT_MODEL` and `OPENCODE_SUB_AGENT_DEFAULT_MODEL` at lines 75-76, between `SUB_AGENT_DEFAULT_MODEL` (line 71) and `SUB_AGENT_MAX_TURNS` (line 77). Both default to empty string.
- `computer-use-server/cli_runtime.py` — Added `import os` + extended `from docker_manager import (...)` to pull in `ANTHROPIC_DEFAULT_SONNET_MODEL`/`OPUS`/`HAIKU`. Appended ADAPT-06 block at lines 65-159 containing: `_CLAUDE_ALIAS_MAP` (line 82), `_OPENCODE_ALIAS_MAP` (line 88), `_resolve_claude` (line 95), `_resolve_codex` (line 103), `_resolve_opencode` (line 121), public `resolve_subagent_model` (line 142). Existing `Cli`, `_ADAPTERS`, `resolve_cli`, `get_adapter` untouched.

## Decisions Made
- Env vars are read at call time inside the `_resolve_*` helpers via `os.getenv` (not imported as module constants from `docker_manager`). This lets tests use `monkeypatch.setenv(...)` between calls without `importlib.reload(docker_manager)`. Plan 05-04 will rely on this.
- `_CLAUDE_ALIAS_MAP` values are zero-arg lambdas so the fallback (`ANTHROPIC_DEFAULT_SONNET_MODEL or "claude-sonnet-4-6"`) is evaluated at call time — matches v0.9.2.0 `mcp_tools.py:909-924` byte-for-byte semantics.
- OpenCode pass-through with missing provider prefix triggers a soft warning (`print`) rather than `raise` — opencode's own error path will produce the actionable failure at runtime, and we don't want to over-restrict pluggable model strings.

## Deviations from Plan

None — plan executed exactly as written. CONTEXT.md D5 code copied verbatim.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- `resolve_subagent_model` is callable and verified for all eight resolution branches (claude alias, claude direct, claude empty, codex empty, codex direct, codex Claude-alias-raises, opencode alias, opencode direct, opencode empty).
- Plan 05-02 (codex adapter) and 05-03 (opencode adapter) can build argv with confidence that the model string they receive is already CLI-appropriate.
- Plan 05-05 (`cli_runtime.dispatch` + `mcp_tools.sub_agent` rewrite) will consume `resolve_subagent_model` directly — no further model-resolution code should be added in any subsequent plan.
- Plan 05-04 (tests) will parametrize all branches of `resolve_subagent_model` plus add monkeypatched env-var cases.

## Self-Check: PASSED

- FOUND: computer-use-server/cli_runtime.py contains `def resolve_subagent_model`
- FOUND: computer-use-server/cli_runtime.py contains `_CLAUDE_ALIAS_MAP`, `_OPENCODE_ALIAS_MAP`, `Claude-only`
- FOUND: computer-use-server/docker_manager.py contains `CODEX_SUB_AGENT_DEFAULT_MODEL`, `OPENCODE_SUB_AGENT_DEFAULT_MODEL`
- FOUND: commit `1cf6032` (Task 1)
- FOUND: commit `652ea1d` (Task 2)
- Smoke (eight resolution branches): ALL OK
- Phase 4 regression: 23 passed
- mcp_tools.py UNCHANGED in this plan (verified — no edits)
- openwebui/init.sh UNCHANGED (verified — no edits)

---
*Phase: 05-adapter-layer*
*Completed: 2026-04-26*
