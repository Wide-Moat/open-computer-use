---
phase: 05-adapter-layer
plan: 02
subsystem: infra
tags: [python, sub-agent, codex, adapter, jsonl-parser]

requires:
  - phase: 04-env-switch-adapter-scaffolding
    provides: "CodexAdapter stub class, SubAgentResult dataclass, CliAdapter Protocol"
provides:
  - "CodexAdapter.build_argv (codex exec --ephemeral --json ... full impl)"
  - "CodexAdapter.parse_result (JSONL turn.completed/item.completed parser)"
  - "SubAgentResult.returncode field (defaulted int = 0, additive)"
affects: [05-04-tests, 05-05-dispatch-and-mcp-rewrite]

tech-stack:
  added: []
  patterns:
    - "Pure-function adapter (no side effects in build_argv; workdir is created by caller)"
    - "Defensive JSONL parsing — JSONDecodeError on a single line is skipped, not raised"
    - "cost_usd=None over $0.00 (Pitfall 4)"
    - "returncode threaded through SubAgentResult so caller can switch on rc=124/137/143"

key-files:
  created: []
  modified:
    - "computer-use-server/cli_adapters/result.py (+6 lines: returncode field + docstring paragraph)"
    - "computer-use-server/cli_adapters/codex.py (+124/-8 net lines: replaced NotImplementedError stubs with full impl)"

key-decisions:
  - "--full-auto chosen over --dangerously-bypass-approvals-and-sandbox per PITFALLS.md security table; container is the sandbox."
  - "system_prompt concatenated as task preamble (Pitfall 2: codex 0.125.0 has no --append-system-prompt)."
  - "resume_session_id ignored with stderr warning (--ephemeral is stateless by design)."
  - "cost_usd=None always — codex JSONL stream does not surface USD cost; per-model price table is a v0.9.x followup."
  - "SubAgentResult.returncode default=0 keeps Phase 4 ClaudeAdapter constructor working (additive change)."

patterns-established:
  - "Adapter remains a pure function: workdir creation is the caller's responsibility (cli_runtime.dispatch in plan 05-05)."
  - "Defensive event-stream parsing: skip JSONDecodeError lines, fall back to raw stdout when no message is captured."

requirements-completed: [ADAPT-03]

duration: ~6min
completed: 2026-04-26
---

# Phase 5 Plan 02: CodexAdapter implementation + SubAgentResult.returncode Summary

**CodexAdapter shipped: build_argv emits `codex exec --ephemeral --json --output-last-message <tmp> --model <m> --full-auto --cd <workdir> --skip-git-repo-check <combined_prompt>`, parse_result consumes JSONL turn.completed/item.completed events with cost_usd=None always (Pitfall 4) and returncode threaded into SubAgentResult.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-04-26T00:50Z
- **Completed:** 2026-04-26T00:56Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- `SubAgentResult` dataclass extended with `returncode: int = 0` (additive — Phase 4 callers unaffected; frozen=True compatible).
- `CodexAdapter.build_argv` returns the exact CONTEXT.md D1 argv shape: `["codex", "exec", "--ephemeral", "--json", "--output-last-message", "<tmp>", "--model", "<m>", "--full-auto", "--cd", "<workdir>", "--skip-git-repo-check", combined_prompt]`.
- System-prompt-as-preamble concatenation (`<sys>\n\n---\n\n<task>`) per Pitfall 2 (codex has no `--append-system-prompt`).
- Per-call workdir via `uuid.uuid4().hex[:12]` (48-bit entropy; collisions negligible). Workdir creation deferred to `cli_runtime.dispatch` (plan 05-05) per "adapter is pure function" rule.
- `resume_session_id` non-empty: prints stderr warning and proceeds with fresh ephemeral session (no raise — caller may have legitimately reused a claude session id).
- `CodexAdapter.parse_result`: walks JSONL stdout, captures last `item.completed`-of-type-`message` text, aggregates `turn.completed.usage.{input,output}_tokens`, sets `is_error = (returncode != 0)`, threads `returncode=returncode` into the result. `cost_usd=None`, `turns=None`, `session_id=None` always.
- Phase 4 regression suite green: 23/23 tests pass in `test_cli_runtime.py` + `test_subagent_claude_compat.py`.

## Task Commits

1. **Task 0: Add returncode field to SubAgentResult dataclass** — `67539dd` (feat)
2. **Task 1: Implement CodexAdapter.build_argv + parse_result** — `7f1f10e` (feat)

## Files Created/Modified

- `computer-use-server/cli_adapters/result.py` — Added `returncode: int = 0` after `raw_events` and a docstring paragraph documenting its purpose (rc=124/137/143 user-message switch in plan 05-05).
- `computer-use-server/cli_adapters/codex.py` — Replaced 9-line `NotImplementedError` stub with 132-line full implementation: SPDX/copyright header preserved, `import json`, `import uuid`, `from .result import SubAgentResult`. `build_argv` constructs argv; `parse_result` walks JSONL stream defensively (`json.JSONDecodeError` skipped per-line). `import sys` is local-scoped inside the resume_session_id warning branch (only loaded when warning fires).

## Decisions Made
- **`--full-auto` not `--dangerously-bypass-approvals-and-sandbox`** — confirmed per PITFALLS.md anti-pattern table. Justification documented inline in the adapter module docstring: container provides the sandbox boundary; codex's own approval layer is redundant and would block non-interactive use.
- **`returncode: int = 0` field default** — keeps Phase 4 `ClaudeAdapter.parse_result` constructor working (it doesn't pass `returncode` kwarg yet). Plan 05-05's claude-fix sub-step will populate it for ClaudeAdapter alongside the `is_error or returncode != 0` patch.
- **Workdir creation off-loaded to dispatch** — adapter stays pure function, no `mkdir` side effect in `build_argv`. Plan 05-05's `cli_runtime.dispatch` will `mkdir -p` inside the sandbox container before invoking the argv.
- **Edge case: malformed JSON line** — `json.JSONDecodeError` on a single line is silently `continue`d (not appended to `events`). Rationale: codex 0.125.0's JSONL stream is intermittent during tool-use; partial flushes are expected. The full stream stays in `raw_events` for any line that DOES parse, supporting downstream debug.
- **Edge case: empty system_prompt** — argv prompt is just `task` (no `\n\n---\n\n` separator). Verified by smoke test (`argv2[-1] == 'hi'`).
- **Edge case: stdout empty** — `last_message_text or stdout` falls back to empty string (not None); `is_error` is set from `returncode != 0` so the caller can branch on the real failure signal.

## Deviations from Plan

None — plan executed exactly as written. CONTEXT.md D1+D2 code copied verbatim. Optional `import sys` inside the `resume_session_id` branch is the only stylistic deviation (plan didn't specify import scope), chosen to keep `sys` out of module load when no resume id is supplied.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required. Codex CLI itself is not yet installed in the image (Phase 6 followup); this plan delivers the adapter code path only.

## Next Phase Readiness

- `CodexAdapter().build_argv(...)` returns concrete argv; no NotImplementedError remains anywhere in `cli_adapters/codex.py`.
- `SubAgentResult.returncode` is available for plan 05-05's `mcp_tools.sub_agent` rewrite to render distinct user-facing messages (rc=124 timeout, rc=137 SIGKILL, rc=143 SIGTERM, default non-zero "failed with exit code N").
- Plan 05-03 (OpenCodeAdapter) has the same structural template now demonstrated by codex.py — same `from .result import SubAgentResult`, same defensive JSONL loop, same `cost_usd`/`is_error`/`returncode` semantics.
- Plan 05-04 (tests) can now parametrize the CodexAdapter against synthetic JSONL fixtures committed under `tests/fixtures/cli/`.
- `cli_runtime.dispatch` (plan 05-05) can call `CodexAdapter()` with confidence: argv is shell-quotable (single-element prompt, no shell metacharacter risk), workdir creation is the caller's responsibility.

## Self-Check: PASSED

- FOUND: `returncode: int = 0` in computer-use-server/cli_adapters/result.py
- FOUND: `"codex", "exec"` in computer-use-server/cli_adapters/codex.py
- FOUND: `"--ephemeral"`, `"--json"`, `"--output-last-message"`, `"--full-auto"`, `"--cd"`, `"--skip-git-repo-check"` in codex.py
- FOUND: `returncode=returncode` propagation in codex.py parse_result constructor
- FOUND: `cost_usd=None` in codex.py parse_result
- NOT FOUND: `NotImplementedError` in codex.py (stub removed)
- NOT FOUND: `dangerously-bypass` in codex.py (security: correct flag chosen)
- FOUND commit: `67539dd` (Task 0)
- FOUND commit: `7f1f10e` (Task 1)
- Smoke (build_argv + parse_result happy path + error returncode propagation): ALL OK
- Phase 4 regression: 23 passed
- cli_adapters/{__init__,claude,opencode}.py UNCHANGED (verified via no edits in this plan)
- mcp_tools.py UNCHANGED (verified via no edits in this plan)
- openwebui/init.sh UNCHANGED (verified via no edits in this plan)

---
*Phase: 05-adapter-layer*
*Completed: 2026-04-26*
