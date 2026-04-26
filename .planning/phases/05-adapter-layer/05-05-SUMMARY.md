---
phase: 05-adapter-layer
plan: 05
subsystem: orchestrator
tags: [python, sub-agent, dispatch, adapter, mcp-tools, blocker-fix]

requires:
  - phase: 05-adapter-layer
    plan: 01
    provides: "resolve_subagent_model + per-CLI alias maps"
  - phase: 05-adapter-layer
    plan: 02
    provides: "CodexAdapter full impl + SubAgentResult.returncode field"
  - phase: 05-adapter-layer
    plan: 03
    provides: "OpenCodeAdapter full impl"
  - phase: 05-adapter-layer
    plan: 04
    provides: "TEST-03 adapter coverage + BLOCKER 1 xfail-strict regression guard"
provides:
  - "ClaudeAdapter.parse_result returncode-as-error gate (BLOCKER 1 closed)"
  - "ClaudeAdapter.parse_result populates SubAgentResult.returncode"
  - "docker_manager._execute_bash_capture (returns SimpleNamespace stdout/stderr/returncode)"
  - "cli_runtime.dispatch async single entry point"
  - "mcp_tools.sub_agent rewritten to call cli_dispatch — no inline ALIAS_MAP, no inline claude_command, no _format_sub_agent_result"
  - "Per-rc reason-string mapping preserved (124/137/143/other)"
  - "Marker file + JSONL log streaming gated on cli == Cli.CLAUDE"
affects: [05-06-byte-compat-regression-test]

tech-stack:
  added: []
  patterns:
    - "Single-entry-point async dispatch with shlex.quote on every argv element (T-05-05-02)"
    - "SimpleNamespace(stdout, stderr, returncode) wrapper to mirror subprocess.CompletedProcess shape for adapter parsers"
    - "Per-CLI capability gating in MCP tool body (cli == Cli.CLAUDE) so codex/opencode skip claude-only postprocessing without runtime errors"
    - "rc-driven user-facing messages (124→timeout / 137→SIGKILL / 143→SIGTERM / other→exit code N) replacing v0.9.2.0's separate exit_code branches"

key-files:
  created: []
  modified:
    - "computer-use-server/cli_adapters/claude.py (+13 lines: docstring + is_error gate + returncode kwarg)"
    - "tests/orchestrator/test_cli_adapters.py (-12 lines: removed strict-xfail decorator from test_claude_parse_result_nonzero_returncode_is_error)"
    - "computer-use-server/docker_manager.py (+62 lines: SimpleNamespace import + _execute_bash_capture helper)"
    - "computer-use-server/cli_runtime.py (+86 lines: asyncio/shlex imports + _execute_bash_capture import + SubAgentResult import + async dispatch())"
    - "computer-use-server/mcp_tools.py (-160 / +129 net: ALIAS_MAP block, both claude_command builders, _format_sub_agent_result function REMOVED; cli_dispatch wiring + per-rc reason-string switch + Cli.CLAUDE gating ADDED; sub_agent signature byte-identical)"

key-decisions:
  - "BLOCKER 1 + xfail removal in the same commit (Task 0): the strict-xfail decorator in tests/orchestrator/test_cli_adapters.py would have flipped the next CI run to FAILURE under strict=True XPASS semantics; removing it together with the patch keeps CI deterministic across the boundary."
  - "Codex --cd workdir created inside the container by extracting the value following --cd from the adapter-built argv (rather than threading workdir back through a separate adapter hook). Keeps the CliAdapter Protocol minimal — workdir lifecycle is dispatch's concern, not the adapter's."
  - "headers_env is appended verbatim by dispatch (already shlex.quote'd by mcp_tools.sub_agent before being passed in). Preserves v0.9.2.0 contract — quoting happens once, at the call site that owns the value."
  - "_format_sub_agent_result was DELETED rather than kept as a thin wrapper. The new rendering is a few lines inline in sub_agent and is only called once; an extra indirection layer would obscure the rc-switching logic that's central to WARNING 1."
  - "Per-CLI Cli.CLAUDE gate appears in TWO places (the _stream_session_logs body and the _find_session_id helper) rather than introducing a capability-flag abstraction. Two call sites do not justify a new layer; Phase 7 (cost-guardrail-and-ttyd-UX) owns the per-CLI progress/UX redesign and will replace these gates with structured capabilities then."

patterns-established:
  - "Adapter dispatch surface (cli_runtime.dispatch) is the ONLY consumer of _execute_bash_capture today — _execute_bash retains the v0.9.2.0 concatenated-output contract for all other call sites."
  - "Per-rc user-facing reason strings (124/137/143/other) live in mcp_tools.sub_agent. Adapters expose returncode in SubAgentResult; the human-readable mapping is a presentation concern."
  - "Marker-file + tail -f JSONL streaming is a claude-only optimisation. Codex/opencode get heartbeat-only progress. This boundary is documented in source comments at both gating sites."

decisions: []

metrics:
  duration: "~25 minutes"
  tasks: 4
  files_changed: 5
  commits: 4
  completed: "2026-04-25"

threat-flags: []
---

# Phase 5 Plan 5: Dispatch FLIP + BLOCKER 1 Fix Summary

The riskiest single change in milestone v0.9.2.1 — flipping `mcp_tools.sub_agent`
from inline alias map + claude_command shell builder + `_format_sub_agent_result`
parser onto `cli_runtime.dispatch(...)`, while patching `ClaudeAdapter.parse_result`
to gate `is_error` on `returncode != 0` (BLOCKER 1).

## What Shipped

### Task 0 — BLOCKER 1 (cli_adapters/claude.py + test_cli_adapters.py)
- `parse_result` now sets `is_error = is_error or (returncode != 0)` immediately
  before constructing `SubAgentResult`, aligning ClaudeAdapter with
  CodexAdapter and OpenCodeAdapter. Without this, killed/timed-out claude
  runs (rc=137/143/124 with no JSON `result` line in stdout) would silently
  return `is_error=False` and an empty `text`, bypassing the
  Sub-Agent-Terminated branch entirely.
- `SubAgentResult.returncode` (added in plan 05-02 Task 0) is now populated
  by ClaudeAdapter — previously the dataclass default of `0` always applied
  on the claude path.
- `tests/orchestrator/test_cli_adapters.py`: removed the
  `pytest.mark.xfail(strict=True)` decorator from
  `test_claude_parse_result_nonzero_returncode_is_error`. With the patch in
  place, the test now passes; under `strict=True`, the unexpected pass
  would otherwise hard-fail CI.

### Task 1 — _execute_bash_capture (docker_manager.py)
- New helper `_execute_bash_capture(container, command, timeout=None)` returns a
  `SimpleNamespace(stdout, stderr, returncode)`. Mirrors `_execute_bash`'s
  docker exec semantics (timeout, shutdown-timer reset, demux=True) but
  preserves stdout/stderr separation that the adapter parsers' signature
  `parse_result(stdout, stderr, returncode)` requires.
- `from types import SimpleNamespace` added to top-of-file imports (PEP 8;
  WARNING 3 fix). Single import — no inline duplicates.
- Existing `_execute_bash` is untouched; all current call sites keep their
  concatenated `output` string contract.

### Task 2 — cli_runtime.dispatch (cli_runtime.py)
- `async def dispatch(*, container, task, system_prompt, model, max_turns,
  timeout_s, working_directory, resume_session_id="", plan_file="",
  headers_env="") -> tuple[SubAgentResult, str, str]` is the single entry
  point per CONTEXT.md D6.
- Resolves CLI via `resolve_cli` → picks adapter via `get_adapter` → resolves
  model via `resolve_subagent_model` → builds argv via `adapter.build_argv` →
  pre-creates `--cd` workdir for codex via `mkdir -p` inside the container →
  joins `shlex.quote`'d argv → executes via `_execute_bash_capture` wrapped
  in `asyncio.to_thread` → parses via `adapter.parse_result`.
- Returns `(result, model_id, model_display)` so mcp_tools can render the
  user-facing display name unchanged from v0.9.2.0.

### Task 3 — sub_agent FLIP (mcp_tools.py)
- **Removed:** `_format_sub_agent_result` function (45 lines), inline
  `ALIAS_MAP` block (16 lines), both inline `claude_command` shell-string
  builders (~50 lines), the v0.9.2.0 separate `exit_code in (137, 143, -9, -15)`
  / `exit_code == 124` branches (~30 lines).
- **Added:** `from cli_runtime import dispatch as cli_dispatch, Cli, resolve_cli`
  import; `cli = resolve_cli()` at function entry; `cli_dispatch(...)` call
  in place of the `_execute_bash` claude-command call site; per-rc
  user-facing reason mapping; `Cli.CLAUDE` gate on `_stream_session_logs`
  (heartbeat-only fallback for non-claude CLIs) and on `_find_session_id`
  (returns `""` for non-claude CLIs).
- **Unchanged:** the `@mcp.tool()`-decorated `sub_agent(task, description, ctx,
  model="", max_turns=0, working_directory="/home/assistant",
  resume_session_id="")` signature is byte-identical. MCP-call-arg defaulting
  for `model` and `max_turns` from env constants stays in mcp_tools (model
  resolution happens inside dispatch via `resolve_subagent_model`).

## Per-rc Reason-String Mapping (WARNING 1 preserved)

| returncode      | User-facing reason                |
|-----------------|------------------------------------|
| 124             | "timed out after Ns"              |
| 137 / -9        | "killed by SIGKILL"               |
| 143 / -15       | "terminated by SIGTERM"           |
| other non-zero  | "failed with exit code N"         |
| 0 with is_error | "crashed before producing results" |

The reason string is rendered only when `sub_result.is_error and not
sub_result.text.strip()` (matches the v0.9.2.0 condition for the
Sub-Agent-Terminated branch).

## Verification

All four `success_criteria` grep gates pass:
- `is_error or (returncode != 0)` present in claude.py
- `returncode=returncode` present in claude.py
- `from types import SimpleNamespace` present (single import) in docker_manager.py
- `def _execute_bash_capture` present in docker_manager.py
- `async def dispatch` present in cli_runtime.py
- `shlex.quote` present in cli_runtime.py
- `cli_dispatch` present in mcp_tools.py
- ALIAS_MAP / claude_command / `_format_sub_agent_result` all GONE from mcp_tools.py
- sub_agent signature byte-identical

Tests:
- `pytest tests/orchestrator/test_cli_runtime.py tests/orchestrator/test_cli_adapters.py tests/orchestrator/test_subagent_claude_compat.py` → **64 passed, 0 failed, 0 xfail**.
- `bash tests/test_init_sh_unchanged.sh` → **PASS** (init.sh sha256 31ce03b... matches v0.9.2.0 baseline).
- `python3 -c "import sys; sys.path.insert(0,'computer-use-server'); from cli_runtime import dispatch"` → success. Full mcp_tools import not attempted on host (requires `mcp` package; runs in Docker per CLAUDE.md).

## Deviations from Plan

None. The implementation follows CONTEXT.md D6 (dispatch shape) and D7
(mcp_tools rewrite shape) verbatim. The plan's "thin wrapper" alternative
for `_format_sub_agent_result` was NOT taken — the function is fully
deleted and its replacement rendering is inlined in sub_agent — because
the rendering is now ~15 lines and is only called once, and an extra
indirection layer would obscure the rc-switching logic central to WARNING 1.
This is a smaller-blast-radius variant of the plan-allowed approach.

## Hand-off to Plan 05-06

Plan 05-06 will add the byte-compat regression test that mocks
`_execute_bash_capture` and asserts the shell command + parsed result for
the claude path match v0.9.2.0 exactly. The dispatch wiring landed by
this plan is what the regression test will exercise.

## Self-Check: PASSED

All 5 modified files exist on disk; all 4 task commits (54f3761, 457f43c,
49bd0be, 1393b53) present in `git log`.
