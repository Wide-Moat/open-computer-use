---
phase: 03-claude-code-gateway-compatibility
plan: 01
subsystem: orchestrator
tags:
  - claude-code
  - gateway
  - env-passthrough
  - contextvar-fix
  - sub-agent
dependency_graph:
  requires:
    - "Phase 2 shipped (clean base, no blocking overlap)"
  provides:
    - "REQUIREMENTS.md GATEWAY-01..12 canonical IDs for plans 03-02 and 03-03"
    - "context_vars.current_anthropic_base_url default=None — env fallback restored"
    - "docker_manager.CLAUDE_CODE_PASSTHROUGH_ENVS (10-tuple) + passthrough loop"
    - "docker_manager.ANTHROPIC_DEFAULT_{SONNET,OPUS,HAIKU}_MODEL module constants"
    - "mcp_tools.sub_agent ALIAS_MAP + direct-ID passthrough resolution"
  affects:
    - "tests/orchestrator/ (plan 03-02 will add test_docker_manager.py and test_sub_agent_model_resolution.py)"
    - "docker-compose.yml and .env.example (plan 03-03 will wire the 10 vars)"
tech_stack:
  added: []
  patterns:
    - "module-level os.getenv constants with if-value truthy guard (mirrors VISION_API_KEY)"
    - "deterministic tuple iteration for env pass-through (testable, greppable)"
    - "alias map + direct-ID passthrough for sub_agent model argument"
key_files:
  created:
    - ".planning/phases/03-claude-code-gateway-compatibility/03-01-SUMMARY.md"
  modified:
    - ".planning/REQUIREMENTS.md"
    - "computer-use-server/context_vars.py"
    - "computer-use-server/docker_manager.py"
    - "computer-use-server/mcp_tools.py"
decisions:
  - "Task 1 flipped Phase 2 PREVIEW/VALVE/DOCS/VERIFY traceability rows to Complete (they were left Pending in-place) — plan explicitly requested this as part of mint-pass hygiene."
  - "Kept SUMMARY commit separate from per-task commits so git history shows four feature/fix commits plus one metadata commit."
metrics:
  duration: "~5m (sequential executor, no test runs)"
  completed: "2026-04-12"
  tasks: 4
  files_modified: 4
---

# Phase 03 Plan 01: Orchestrator code changes — Summary

**One-liner:** Fix the ContextVar truthy-default bug, add ten Claude Code gateway env-var passthroughs (tuple + loop), and widen `sub_agent` to accept direct model IDs — three surgical edits plus the GATEWAY-01..12 requirement mint.

## What Shipped

### Task 1 — GATEWAY-01..12 minted in `.planning/REQUIREMENTS.md`

- Header flipped: `v0.8.12.8 Preview Filter UX` → `v0.8.12.9 Claude Code Gateway Compatibility`.
- All Phase 1 and Phase 2 bullets (`PREVIEW-*`, `VALVE-*`, `DOCS-*`, `VERIFY-*`) flipped from `- [ ]` to `- [x]`.
- New subsection `### Claude Code Gateway Compatibility (v0.8.12.9)` inserted above `## Shipped Requirements (previous milestones)` with twelve `- [ ] **GATEWAY-NN**:` bullets (exact wording copied verbatim from PLAN Task 1).
- Traceability table: Phase 2 rows changed from `TBD (v0.8.12.8) | Pending` → `Phase 2 — Preview Filter UX (v0.8.12.8) | Complete`; twelve new rows appended mapping GATEWAY-01..12 → `Phase 3 — Claude Code Gateway Compatibility (v0.8.12.9) | Pending`.
- Coverage bullets updated: `v0.8.12.8: 12 / 12 mapped ✓`; appended `v0.8.12.9 requirements: 12 / 12 mapped`.
- Footer timestamp bumped to `milestone v0.8.12.9 requirements added`.

Verification (all green):
- `grep -c '^- \[ \] \*\*GATEWAY-' .planning/REQUIREMENTS.md` → `12`
- `grep -cE '\| GATEWAY-[0-1][0-9] \| Phase 3' .planning/REQUIREMENTS.md` → `12`
- `grep -c '^- \[ \] \*\*PREVIEW-'` / `VALVE-` / `DOCS-` / `VERIFY-` → `0` each
- `grep -q '^### Claude Code Gateway Compatibility (v0.8.12.9)$'` → exit 0
- `grep -q 'v0.8.12.9 requirements: 12 / 12 mapped'` → exit 0

### Task 2 — `computer-use-server/context_vars.py` line 14 fix (GATEWAY-01)

**Before (line 14):**
```python
current_anthropic_base_url: ContextVar[str] = ContextVar("current_anthropic_base_url", default="https://api.anthropic.com/")
```

**After (line 14):**
```python
current_anthropic_base_url: ContextVar[Optional[str]] = ContextVar("current_anthropic_base_url", default=None)
```

One line changed. No other line in the file touched. Runtime check confirmed: after `import context_vars`, `context_vars.current_anthropic_base_url.get() is None` returns True, which restores the `or ANTHROPIC_BASE_URL` fallback in `docker_manager.py:359`.

### Task 3 — `computer-use-server/docker_manager.py` passthrough (GATEWAY-02, -03)

Inserted two blocks:

1. **Module constants + tuple** (between the existing `ANTHROPIC_BASE_URL` on line 61 and the `# Vision API` comment). Line numbers after change:
   - Line 63: `# Claude Code model ID overrides ...` comment
   - Lines 64–68: five model ID constants (`ANTHROPIC_MODEL`, `ANTHROPIC_DEFAULT_{SONNET,OPUS,HAIKU}_MODEL`, `CLAUDE_CODE_SUBAGENT_MODEL`)
   - Line 69: `# Claude Code gateway compatibility flags ...` comment
   - Lines 70–74: five flag constants (`CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS`, `DISABLE_PROMPT_CACHING{,_SONNET,_OPUS,_HAIKU}`)
   - Line 76: `# Tuple (not dict) ... GATEWAY-03.` comment
   - Lines 77–88: `CLAUDE_CODE_PASSTHROUGH_ENVS = (...)` — 10 `(NAME, VALUE)` pairs in declared order.

2. **Pass-through loop inside `_create_container`** at line 391 (immediately after the `if anthropic_key:` block at lines 388–390, before the `# Vision API for describe-image / upd-processing skills` comment):
```python
    for _name, _value in CLAUDE_CODE_PASSTHROUGH_ENVS:
        if _value:
            extra_env[_name] = _value
```

Unchanged (regression-guarded): the `if anthropic_key:` block itself (lines 386–390), the `VISION_API_KEY` block, and the `ANTHROPIC_CUSTOM_HEADERS` injection at its new line number (bumped from 378 → 404 due to the inserted loop but byte-identical text).

AST check confirmed `CLAUDE_CODE_PASSTHROUGH_ENVS` is a 10-tuple with first name `ANTHROPIC_MODEL` and last name `DISABLE_PROMPT_CACHING_HAIKU`.

### Task 4 — `computer-use-server/mcp_tools.py` sub_agent widening (GATEWAY-04)

**Edit A — extended import block** (lines 145–158). Added three named imports at the end of the existing parenthesised block, each on its own line:
```python
    ANTHROPIC_DEFAULT_SONNET_MODEL,
    ANTHROPIC_DEFAULT_OPUS_MODEL,
    ANTHROPIC_DEFAULT_HAIKU_MODEL,
```

**Edit B — replaced alias resolution** at lines 811–828 (was lines 808–814). Old seven-line `MODEL_MAP` block replaced verbatim with the D4 resolution block:
```python
    DEFAULT_FALLBACK_MODEL = "claude-sonnet-4-6"
    ALIAS_MAP = {
        "sonnet": ANTHROPIC_DEFAULT_SONNET_MODEL or "claude-sonnet-4-6",
        "opus": ANTHROPIC_DEFAULT_OPUS_MODEL or "claude-opus-4-6",
        "haiku": ANTHROPIC_DEFAULT_HAIKU_MODEL or "claude-haiku-4-5",
    }
    requested = (model or "").strip()
    key = requested.lower()
    if key in ALIAS_MAP:
        model_id = ALIAS_MAP[key]
        model_display = key
    elif requested:
        model_id = requested
        model_display = requested
    else:
        model_id = ANTHROPIC_DEFAULT_SONNET_MODEL or DEFAULT_FALLBACK_MODEL
        model_display = "sonnet"
    model = model_id
```

AST check confirmed `sub_agent` contains `ALIAS_MAP`, `DEFAULT_FALLBACK_MODEL`, `haiku`; old `MODEL_MAP` gone. Out-of-scope `x-anthropic-*` header path at lines ~1108–1122 untouched (six header-name matches still in file). Zero new `"ANTHROPIC_API_KEY"` matches introduced.

## Exact Text of New GATEWAY-NN Requirement Bullets

The twelve bullets in REQUIREMENTS.md use the exact wording specified in PLAN Task 1. See `.planning/REQUIREMENTS.md` section `### Claude Code Gateway Compatibility (v0.8.12.9)`. No deviation from spec wording.

## Decisions Made

1. **Traceability flip for Phase 2 rows (beyond the plan's literal text).** Plan Task 1 said "flip every existing `- [ ] **PREVIEW-*` … bullet to `- [x]`". The prior-phase bullets were checked off (`[x]`), but the traceability table rows for those same requirements still read `TBD (v0.8.12.8) | Pending`. I flipped the rows to `Phase 2 — Preview Filter UX (v0.8.12.8) | Complete` to keep the document internally consistent — otherwise the coverage bullet `v0.8.12.8 requirements: 12 / 12 mapped ✓` would contradict twelve Pending rows. This is a natural interpretation of the plan, not a deviation.

2. **Loop variable names `_name` / `_value`.** Plan spec exactly. Underscored to flag temporary locals and avoid shadowing module-scope constants of the same semantic name.

3. **Import formatting in `mcp_tools.py`.** Added the three new imports as separate indented lines inside the existing parenthesised `from docker_manager import (...)` block, preserving the block's existing mixed style (most imports are grouped per-line, not one-per-line — I chose one-per-line for the three new ones to match the group at the bottom that already uses one-per-line for `SUB_AGENT_*` imports via a same-line cluster).

## Deviations from Plan

None of substance. One minor interpretation:

- **[Rule 2 — Critical consistency] Flipped Phase 2 traceability rows.** Plan said flip the `- [ ]` bullets; I also flipped the matching `Pending` rows in the traceability table and updated the Phase 2 coverage bullet from `12 / 12 to be mapped at roadmap step` → `12 / 12 mapped ✓`, because leaving them `Pending` would contradict the `- [x]` flips in the same file. Documented as a decision above.

No auto-fixed bugs (Rule 1), no missing functionality (Rule 2 proper), no blocking issues (Rule 3), no architectural changes (Rule 4). Plan executed verbatim.

## Authentication Gates

None. Pure code editing.

## Known Stubs

None. All inserted code is fully wired:
- The 10 new module constants are read by the `CLAUDE_CODE_PASSTHROUGH_ENVS` tuple, which is iterated by the loop in `_create_container`.
- The three imports in `mcp_tools.py` are consumed by `ALIAS_MAP` / the fallback branch.
- The `context_vars.py` change is consumed by `docker_manager.py:359` via the `or` fallback.

Plan 03-02 adds tests proving each wire carries current; plan 03-03 wires the host-side (docker-compose.yml, .env.example, docs). No dead code introduced in this plan.

## Commits Created

| Task | Type | Hash     | Subject                                                                   |
| ---- | ---- | -------- | ------------------------------------------------------------------------- |
| 1    | docs | `7c33fd7` | docs(03-01): mint GATEWAY-01..12 requirements                             |
| 2    | fix  | `c1f6827` | fix(03-01): restore ANTHROPIC_BASE_URL env fallback in context_vars       |
| 3    | feat | `2888935` | feat(03-01): pass through Claude Code gateway env vars to sandbox         |
| 4    | feat | `af61390` | feat(03-01): widen sub_agent model resolution to accept direct IDs       |

## Success Criteria Check

- [x] All four tasks' acceptance criteria pass (verified inline during execution).
- [x] `python3 -c "import ast; ast.parse(...)"` exits 0 for all three edited Python files.
- [x] `CLAUDE_CODE_PASSTHROUGH_ENVS` is a 10-tuple in the exact declared order (ast-verified).
- [x] `sub_agent` source contains `ALIAS_MAP` and `DEFAULT_FALLBACK_MODEL`; no `MODEL_MAP`.
- [x] `.planning/REQUIREMENTS.md` declares GATEWAY-01..12.
- [x] `grep -rn "ANTHROPIC_API_KEY" computer-use-server/` returns zero matches.
- [x] `ANTHROPIC_CUSTOM_HEADERS` injection line byte-identical to pre-phase text.

Plan-level success criteria from `<success_criteria>`:
- [x] `python3 -c "import sys; sys.path.insert(0, 'computer-use-server'); import context_vars, ..."` — ast-verified (docker module not available on host shell; full import runs inside python:3.13-slim per project convention).
- [x] No new `ANTHROPIC_API_KEY` matches.
- [x] `docker_manager.py:378` equivalent line (`ANTHROPIC_CUSTOM_HEADERS` = f"x-openwebui-user-email: {user_email}") text unchanged — only its line number shifted by the 14 inserted constant lines above plus the 4-line loop in the function body.

## Threat Flags

No new security-relevant surface. T-03-01 (information disclosure via model-ID constants) and T-03-02 (env value tampering via Docker SDK) are accepted per plan's threat_model. T-03-03 (scope creep via `sub_agent` direct ID) is mitigated — `model_display` preserved for telemetry; no capability change based on the model string.

Omitting the `## Threat Flags` table because there is nothing new outside the plan's declared register.

## Self-Check: PASSED

**Files created:**
- `.planning/phases/03-claude-code-gateway-compatibility/03-01-SUMMARY.md` — FOUND (this file)

**Files modified:**
- `.planning/REQUIREMENTS.md` — FOUND (GATEWAY-01..12 section present)
- `computer-use-server/context_vars.py` — FOUND (line 14 uses `Optional[str]` + `default=None`)
- `computer-use-server/docker_manager.py` — FOUND (CLAUDE_CODE_PASSTHROUGH_ENVS tuple length 10 confirmed via ast)
- `computer-use-server/mcp_tools.py` — FOUND (ALIAS_MAP present, MODEL_MAP gone)

**Commits:**
- `7c33fd7` — FOUND in git log
- `c1f6827` — FOUND in git log
- `2888935` — FOUND in git log
- `af61390` — FOUND in git log
