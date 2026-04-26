---
phase: 05-adapter-layer
plan: 03
subsystem: infra
tags: [python, sub-agent, opencode, adapter, event-stream-parser]

requires:
  - phase: 04-env-switch-adapter-scaffolding
    provides: "OpenCodeAdapter stub class, CliAdapter Protocol"
  - phase: 05-adapter-layer
    plan: 02
    provides: "SubAgentResult.returncode field"
provides:
  - "OpenCodeAdapter.build_argv (opencode run ... --format json full impl)"
  - "OpenCodeAdapter.parse_result (event-stream JSON parser with defensive text + cost capture)"
affects: [05-04-tests, 05-05-dispatch-and-mcp-rewrite]

tech-stack:
  added: []
  patterns:
    - "Pure-function adapter (no side effects in build_argv)"
    - "Defensive event-stream parsing — JSONDecodeError on a single line is skipped, not raised"
    - "Multi-shape text capture: str / content-blocks list / message.content nested"
    - "cost_usd may be float or None — never $0.00 (Pitfall 4)"
    - "returncode threaded through SubAgentResult"

key-files:
  created: []
  modified:
    - "computer-use-server/cli_adapters/opencode.py (+128/-10 net lines: replaced NotImplementedError stubs with full impl)"

key-decisions:
  - "--dangerously-skip-permissions chosen — correct flag for opencode in isolated container (per opencode.ai/docs/cli for non-interactive use); container provides the sandbox boundary."
  - "system_prompt concatenated as task preamble (Pitfall 2: opencode prompt is per-mode in config, no CLI flag for system prompt)."
  - "resume_session_id ignored with stderr warning (opencode run is stateless; --continue needs Phase 6 mode config)."
  - "Cost aggregation accumulates across step-finish events; falls back to event.usage.total_cost when event.cost absent."
  - "Three final-message event types recognised: assistant-message-completed, step-finish, message-completed (last seen wins)."

patterns-established:
  - "Adapter remains a pure function: no mkdir / no side effects in build_argv."
  - "Defensive event-stream parsing: skip JSONDecodeError lines; fall back to raw stdout when no message captured."
  - "Multi-shape text capture handles provider variance (anthropic/openrouter/openai event shapes differ)."

requirements-completed: [ADAPT-04]

duration: ~3min
completed: 2026-04-25
---

# Phase 5 Plan 03: OpenCodeAdapter implementation Summary

**OpenCodeAdapter shipped: build_argv emits `opencode run <combined_prompt> --model <provider/model> --format json --dangerously-skip-permissions`; parse_result walks the event-stream JSON, captures last text from assistant-message-completed/step-finish/message-completed (str or content-blocks list), sums cost from step-finish events when reported (None otherwise), and threads returncode into SubAgentResult.**

## Performance

- **Duration:** ~3 min
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- `OpenCodeAdapter.build_argv` returns CONTEXT.md D3 argv shape: `["opencode", "run", combined_prompt, "--model", model, "--format", "json", "--dangerously-skip-permissions"]`.
- System-prompt-as-preamble concatenation (`<sys>\n\n---\n\n<task>`) per Pitfall 2 (opencode has no CLI flag for system prompt).
- `resume_session_id` non-empty: prints stderr warning and proceeds statelessly (no raise — Phase 6 will introduce `--continue` once mode config ships).
- `OpenCodeAdapter.parse_result`: walks event-stream stdout line-by-line; recognises three final-message event types and captures text via three field shapes (str / content-blocks list / message.content nested).
- Cost aggregation: `step-finish.cost` (preferred) or `step-finish.usage.total_cost` (fallback); accumulates across multiple step-finish events; stays `None` when neither field arrives.
- `returncode` threaded into `SubAgentResult.returncode`; `is_error` derived from `returncode != 0`.
- Phase 4 + 05-02 regression suite green: **23/23 tests pass** in `test_cli_runtime.py` + `test_subagent_claude_compat.py`.

## Recognised Event Types (parse_result)

| Event type | Source field for text | Cost contribution |
|------------|-----------------------|-------------------|
| `assistant-message-completed` | `text` / `content` / `message.content` | none |
| `step-finish` | `text` / `content` / `message.content` | `cost` or `usage.total_cost` |
| `message-completed` | `text` / `content` / `message.content` | none |

Last seen wins for text. Cost accumulates across all step-finish events.

## Cost-Aggregation Edge Cases

- **Both `cost` and `usage.total_cost` absent on step-finish:** event contributes nothing; cost_usd stays None.
- **Only `usage.total_cost` present:** picked up via fallback path.
- **Multiple step-finish events:** cost values summed (verified by smoke test: 0.01 + 0.02 = 0.03).
- **Non-numeric cost field (e.g. dict):** ignored via `isinstance(step_cost, (int, float))` type-guard (T-05-03-04 mitigation).

## Returncode Propagation Confirmation

- `parse_result(stdout='', stderr='boom', returncode=143)` → `SubAgentResult(is_error=True, returncode=143, ...)` — verified.
- `parse_result(stdout=<happy>, returncode=0)` → `SubAgentResult(is_error=False, returncode=0, ...)` — verified.
- Plan 05-05's `mcp_tools.sub_agent` rewrite can now switch on `result.returncode` for distinct rc=124/137/143 user messages.

## Task Commits

1. **Task 1: Implement OpenCodeAdapter.build_argv + parse_result** — `d0642a0` (feat)

## Files Created/Modified

- `computer-use-server/cli_adapters/opencode.py` — Replaced 9-line `NotImplementedError` stub with 128-line full implementation: SPDX/copyright header preserved, `import json`, `from .result import SubAgentResult`. `build_argv` constructs argv with combined prompt; `parse_result` walks event-stream defensively. `import sys` is local-scoped inside the resume_session_id warning branch.

## Decisions Made

- **`--dangerously-skip-permissions` is correct here** — different rationale than codex's `--full-auto` (different flag spelling per opencode 1.14.25 CLI), same security posture: container is the boundary; the CLI's permission layer is redundant inside it (T-05-03-02 accepted).
- **Three text-field shapes supported** — `event.text` (anthropic-style), `event.content` (openrouter-style flat), `event.message.content` (nested). All three covered by the same `or`-chain.
- **Content-blocks list shape** — when `text_field` is a list of `{type, text}` blocks, last block of `type:text` wins. Mirrors codex's content-blocks handling.
- **Edge case: malformed JSON line** — silently `continue`d (T-05-03-05 mitigation). Partial flushes during streaming are expected.
- **Edge case: stdout empty** — `last_message_text or stdout` falls back to empty string; `is_error` set from `returncode != 0`.
- **Edge case: empty system_prompt** — argv prompt is just `task` (no `\n\n---\n\n` separator). Verified by smoke test.

## Deviations from Plan

None — plan executed exactly as written. CONTEXT.md D3+D4 code copied verbatim. Optional `import sys` inside the `resume_session_id` branch is the only stylistic choice (mirrors codex.py).

## Issues Encountered

None.

## User Setup Required

None — opencode CLI itself is not yet installed in the image (Phase 6 followup); this plan delivers the adapter code path only.

## Next Phase Readiness

- `OpenCodeAdapter().build_argv(...)` returns concrete argv; no NotImplementedError remains anywhere in `cli_adapters/opencode.py`.
- All three adapters (claude/codex/opencode) now have full implementations — plan 05-04 can parametrize tests against synthetic event-stream fixtures committed under `tests/fixtures/cli/`.
- `cli_runtime.dispatch` (plan 05-05) can call `OpenCodeAdapter()` with confidence: argv is shell-quotable (single-element prompt, no shell metacharacter risk), no workdir setup required (unlike codex).
- `SubAgentResult.returncode` populated for the rc=124/137/143 UX branch.

## Self-Check: PASSED

- FOUND: `"opencode", "run"` in computer-use-server/cli_adapters/opencode.py
- FOUND: `"--dangerously-skip-permissions"` in opencode.py
- FOUND: `"--format", "json"` in opencode.py
- FOUND: `assistant-message-completed`, `step-finish`, `message-completed` in opencode.py
- FOUND: `returncode=returncode` in opencode.py parse_result constructor
- NOT FOUND: `NotImplementedError` in opencode.py (stub removed)
- FOUND commit: `d0642a0` (Task 1)
- Smoke (build_argv shape + prompt concat + str-text + content-blocks + cost from cost field + cost from usage.total_cost + multi-step cost sum + no-cost path + error returncode + returncode field propagation): ALL OK
- Phase 4 + 05-02 regression: 23 passed
- cli_adapters/{__init__,result,claude,codex}.py UNCHANGED (verified — no edits in this plan)
- mcp_tools.py UNCHANGED (verified — no edits in this plan)
- openwebui/init.sh UNCHANGED (verified — no edits in this plan)

---
*Phase: 05-adapter-layer*
*Completed: 2026-04-25*
