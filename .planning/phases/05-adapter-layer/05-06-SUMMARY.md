---
phase: 05-adapter-layer
plan: 06
subsystem: testing
tags: [pytest, monkeypatch, byte-compat, dispatch, claude, regression]

# Dependency graph
requires:
  - phase: 04-runtime-resolver
    provides: build_argv golden snapshot fixture (claude_v0.9.2.0_argv.json) and test_subagent_claude_compat.py harness
  - phase: 05-adapter-layer
    provides: parse_result fixture (claude_v0.9.2.0_stdout.json, plan 05-04) + dispatch flip in mcp_tools.sub_agent (plan 05-05)
provides:
  - End-to-end byte-compat regression net for the SUBAGENT_CLI=claude path through cli_runtime.dispatch
  - Reusable _scrub_dev_env(monkeypatch) helper covering 6 model-override env vars (WARNING 2 fix)
  - Proof that dispatch flip in 05-05 produces shell command + SubAgentResult byte-identical to v0.9.2.0
affects: [phase-06-codex-adapter, phase-07-opencode-adapter, future-cli-additions]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "monkeypatch.delenv loop for dev-env scrubbing in byte-compat tests"
    - "patch('cli_runtime._execute_bash_capture', side_effect=...) to capture shell command without Docker"
    - "asyncio.run(cli_dispatch(...)) for unit-testing async dispatch"

key-files:
  created: []
  modified:
    - tests/orchestrator/test_subagent_claude_compat.py

key-decisions:
  - "Reused existing test_subagent_claude_compat.py file (not a separate dispatch_*.py file) to keep all claude byte-compat tests co-located"
  - "Mocked cli_runtime._execute_bash_capture (the local re-export) rather than docker_manager._execute_bash_capture to avoid module-reload subtleties"
  - "Used patch as a context manager + asyncio.run rather than pytest-asyncio (project has no pytest-asyncio plugin; existing tests use asyncio.run pattern)"

patterns-established:
  - "WARNING-2 dev-env scrubbing: tests sensitive to ANTHROPIC_DEFAULT_*_MODEL / SUB_AGENT_DEFAULT_MODEL / CODEX_*_MODEL / OPENCODE_*_MODEL must call _scrub_dev_env(monkeypatch) first"
  - "End-to-end dispatch byte-compat tests: assert STRICT string equality on captured shell command, with diff-friendly failure messages printing both expected and actual"

requirements-completed: [ADAPT-02]

# Metrics
duration: 8min
completed: 2026-04-26
---

# Phase 5 Plan 06: Dispatch Byte-Compat Regression Net Summary

**Three byte-compat tests around cli_runtime.dispatch prove the 05-05 dispatch flip is non-regressing for the claude path: shell command byte-equal to v0.9.2.0 across new-session, resume, and ANTHROPIC_CUSTOM_HEADERS branches.**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-04-26T04:07:00Z
- **Completed:** 2026-04-26T04:15:35Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments
- Added `test_claude_dispatch_byte_compat` — NEW SESSION path: assembled shell command + parsed SubAgentResult byte-identical to v0.9.2.0 fixture (15-element argv, headers_env="").
- Added `test_claude_dispatch_resume_byte_compat` — RESUME branch: 13-element argv with `--resume <session_id>`, no `--model`, no `--append-system-prompt`.
- Added `test_claude_dispatch_with_headers_env_byte_compat` — `ANTHROPIC_CUSTOM_HEADERS=...` prefix preserved verbatim BEFORE the argv (GATEWAY-07 v0.8.12.9 contract).
- Added `_scrub_dev_env(monkeypatch)` helper + `_DEV_ENV_VARS_TO_SCRUB` tuple covering 6 model-override env vars (WARNING 2 fix). Stress-verified: tests pass even with `ANTHROPIC_DEFAULT_SONNET_MODEL=should-be-scrubbed` exported.

## Task Commits

1. **Task 1: Add test_claude_dispatch_byte_compat to test_subagent_claude_compat.py** — `257ed77` (test)

## Files Created/Modified
- `tests/orchestrator/test_subagent_claude_compat.py` — appended 3 new test functions + `_scrub_dev_env` helper + `_DEV_ENV_VARS_TO_SCRUB` constant (248 insertions); existing 4 Phase-4 tests + SPDX header untouched.

## Decisions Made
- Mocked `cli_runtime._execute_bash_capture` (the local re-export from `from docker_manager import _execute_bash_capture`) rather than the original `docker_manager._execute_bash_capture` symbol, because `cli_runtime.dispatch` calls the locally-bound name; this is the standard Python-mocking idiom (mock the name where it's looked up, not where it's defined).
- Used `asyncio.run(cli_dispatch(...))` to run the async dispatch synchronously inside each test, matching the pattern in `tests/orchestrator/test_tool_descriptions.py` and `test_mcp_resources.py`. The project does not depend on pytest-asyncio.
- The `patch(...)` is a context manager around the `asyncio.run` call; the mock is in scope for the entire dispatch chain (build_argv, shlex.quote, _execute_bash_capture, parse_result).
- Passed `container=object()` (opaque sentinel) since the fake `_execute_bash_capture` ignores it. This avoids any Docker dependency.

## Confirmation: byte-equality with v0.9.2.0

The captured shell command in each test is asserted with strict `==` (not substring) against a freshly reconstructed expected string built by:

```python
expected_quoted = " ".join(shlex.quote(a) for a in expected_argv)
expected_shell_cmd = f"cd {shlex.quote(working_directory)} && {headers_env}{expected_quoted}"
```

This mirrors the exact construction in `cli_runtime.dispatch` (lines 231-235):

```python
quoted_argv = " ".join(shlex.quote(a) for a in argv)
shell_cmd = (
    f"cd {shlex.quote(working_directory)} && "
    f"{headers_env}{quoted_argv}"
)
```

…which in turn matches the v0.9.2.0 inline `mcp_tools.sub_agent` `claude_command` shape. No subtle quoting differences were discovered during implementation — the dispatch impl matches v0.9.2.0 exactly.

## WARNING-2 fix: env-var scrub list and rationale

A developer with one of these vars exported in their local shell would see byte-compat assertions fail (because the resolver would substitute their override into the argv where the fixture expects `claude-sonnet-4-6`):

| Env var                              | Why scrubbed                                                            |
|--------------------------------------|-------------------------------------------------------------------------|
| `ANTHROPIC_DEFAULT_SONNET_MODEL`     | Overrides `_CLAUDE_ALIAS_MAP["sonnet"]` resolution in cli_runtime.py    |
| `ANTHROPIC_DEFAULT_OPUS_MODEL`       | Overrides `_CLAUDE_ALIAS_MAP["opus"]` resolution                        |
| `ANTHROPIC_DEFAULT_HAIKU_MODEL`      | Overrides `_CLAUDE_ALIAS_MAP["haiku"]` resolution                       |
| `SUB_AGENT_DEFAULT_MODEL`            | mcp_tools.sub_agent fallback when `model` arg is empty                  |
| `CODEX_SUB_AGENT_DEFAULT_MODEL`      | Codex resolver default (defensive — even though tests target claude path) |
| `OPENCODE_SUB_AGENT_DEFAULT_MODEL`   | OpenCode resolver default (defensive)                                   |

CI is clean; this scrub gives local dev the same guarantees. Stress-tested: `ANTHROPIC_DEFAULT_SONNET_MODEL=should-be-scrubbed pytest tests/orchestrator/test_subagent_claude_compat.py -v` exits 0 with all 7 tests green.

## Deviations from Plan

None — plan executed exactly as written. Code block from plan inserted verbatim before the `if __name__ == "__main__":` guard.

## Issues Encountered

None. Tests passed on first run.

## Verification Results

- `ANTHROPIC_DEFAULT_SONNET_MODEL=should-be-scrubbed pytest tests/orchestrator/test_subagent_claude_compat.py -v` → **7 passed** (4 Phase-4 existing + 3 new)
- `pytest tests/orchestrator/test_cli_runtime.py tests/orchestrator/test_cli_adapters.py -q` → **60 passed, 1 warning** (pre-existing datetime.utcnow deprecation, unrelated)
- `bash tests/test_init_sh_unchanged.sh` → **PASS** (sha256 matches v0.9.2.0 baseline)
- `git diff HEAD~1 -- computer-use-server/` → 0 lines (zero code changes; tests-only plan as required)

## User Setup Required

None — pure-test plan; no external service configuration.

## Next Phase Readiness

Plan 05-06 is the final regression net for the Phase 5 adapter layer. Combined coverage:
- **Phase 4** golden argv snapshot — `build_argv` byte-compat
- **Plan 05-04** parse_result fixture tests — `parse_result` byte-compat
- **Plan 05-06** (this plan) — end-to-end dispatch shell-command + SubAgentResult byte-compat

ROADMAP success criterion #1 (Claude path byte-identical to v0.9.2.0) is satisfied at all three layers. Phase 6 (codex adapter) and Phase 7 (opencode adapter + ttyd autostart) can proceed with confidence that the claude regression net will catch any drift introduced by future runtime changes.

---
*Phase: 05-adapter-layer*
*Completed: 2026-04-26*

## Self-Check: PASSED

- FOUND: tests/orchestrator/test_subagent_claude_compat.py
- FOUND: .planning/phases/05-adapter-layer/05-06-SUMMARY.md
- FOUND: commit 257ed77 (test(05-06): add dispatch byte-compat regression tests for claude path)
