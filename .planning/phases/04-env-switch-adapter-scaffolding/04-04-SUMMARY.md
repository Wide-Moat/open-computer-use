---
phase: 04-env-switch-adapter-scaffolding
plan: 04
subsystem: orchestrator
tags: [tests, cli-runtime, claude-adapter, byte-compat, init-sh, regression-guard, TEST-02, TEST-05]
requires:
  - tests/orchestrator/test_startup_warnings.py (template — sys.path.insert + module-reload pattern)
  - tests/orchestrator/test_docker_manager.py (template — importlib.reload + env patching)
  - computer-use-server/cli_runtime.py (from plan 04-01)
  - computer-use-server/cli_adapters/claude.py (from plan 04-02)
  - computer-use-server/docker_manager.py SUBAGENT_CLI + warn_subagent_cli (plans 04-01/04-03)
  - openwebui/init.sh v0.9.2.0 baseline (sha256 31ce03b6...c9c27a7)
provides:
  - tests/orchestrator/test_cli_runtime.py — TEST-02 resolver suite (19 cases / 9 functions)
  - tests/orchestrator/test_subagent_claude_compat.py — ADAPT-02 byte-compat (4 cases)
  - tests/fixtures/cli/claude_v0.9.2.0_argv.json — captured v0.9.2.0 argv (NEW SESSION + RESUME)
  - tests/test_init_sh_unchanged.sh — TEST-05 sha256 regression guard (executable, exit 0 on baseline, non-zero on tamper)
affects:
  - CI now blocks regressions of the SUBAGENT_CLI resolver semantics, ClaudeAdapter argv drift, and any modification of openwebui/init.sh
tech-stack:
  added:
    - pytest fixtures (autouse env reset, module-scope fixture loader)
    - capfd file-descriptor stderr capture (per 04-01-SUMMARY decision — print(stderr)+sys.exit(1) shape)
    - sha256 cross-platform detection (sha256sum / shasum -a 256)
  patterns:
    - JSON-fixture golden snapshot test for argv builders
    - importlib.reload-after-monkeypatch for module-load-time env validation
    - Standalone bash test (not integrated into test-project-structure.sh) — matches existing one-test-per-script-file pattern
key-files:
  created:
    - tests/orchestrator/test_cli_runtime.py
    - tests/orchestrator/test_subagent_claude_compat.py
    - tests/fixtures/cli/claude_v0.9.2.0_argv.json
    - tests/test_init_sh_unchanged.sh
  modified: []
decisions:
  - capfd (not capsys) for sys.stderr capture — print(..., file=sys.stderr) writes to fd 2; capsys would return empty
  - Argv length asserts adjusted to 15 (NEW SESSION) and 13 (RESUME) — the 14/12 counts in 04-02-SUMMARY were off by one (shell-string element count, not argv element count); actual ClaudeAdapter output is verified
  - extra_env injection covered by both a functional test (mocked Docker client capturing environment dict) AND a source-grep guard for resilience to downstream wiring failures
  - Standalone bash test for TEST-05 (per CONTEXT D6 + RESEARCH recommendation) — not integrated into test-project-structure.sh
metrics:
  duration_seconds: ~210
  tasks_completed: 3
  commits: 3
  files_created: 4
  files_modified: 0
  completed: "2026-04-25"
---

# Phase 4 Plan 04: Phase 4 test trifecta (TEST-02 + ADAPT-02 + TEST-05) Summary

Shipped the three regression tests that prove Phase 4 done: the TEST-02 cli_runtime resolver suite covering all D1+D2 paths, the ADAPT-02 golden-snapshot byte-compat test for the lifted-but-dormant ClaudeAdapter, and the TEST-05 sha256 byte-equals regression on `openwebui/init.sh`. CI now blocks any future commit that breaks the `SUBAGENT_CLI` resolver semantics, drifts the lifted Claude adapter from the v0.9.2.0 production argv, or modifies `openwebui/init.sh`.

## What Shipped

| File | Tests | Role |
|------|-------|------|
| `tests/orchestrator/test_cli_runtime.py` | 9 functions / 19 parametrize cases | TEST-02 — unset/empty/whitespace/valid/invalid resolver + extra_env injection + warn banner |
| `tests/orchestrator/test_subagent_claude_compat.py` | 4 functions | ADAPT-02 — golden snapshot for both NEW SESSION + RESUME branches + parse_result roundtrip + --disallowedTools unquoted-value guard |
| `tests/fixtures/cli/claude_v0.9.2.0_argv.json` | (data) | Captured v0.9.2.0 argv shapes for both branches with known-fixed inputs |
| `tests/test_init_sh_unchanged.sh` | 1 bash assert | TEST-05 — hardcoded sha256 31ce03b6...c9c27a7 baseline, cross-platform sha256sum/shasum detection, operator-friendly tamper diagnostic |

Total: **23 pytest cases + 1 bash check = 24 regression guards** added.

## Test Counts

```
$ python3 -m pytest tests/orchestrator/test_cli_runtime.py tests/orchestrator/test_subagent_claude_compat.py
======================== 23 passed, 1 warning in 0.50s =========================

$ bash tests/test_init_sh_unchanged.sh
PASS: openwebui/init.sh matches v0.9.2.0 baseline (sha256 31ce03b6...c9c27a7).
```

Tamper detection verified by appending `# tamper` to `openwebui/init.sh`, running the test (exits 1 with descriptive failure), restoring the file, and re-running (exits 0).

## Golden Snapshot — Fixture vs ClaudeAdapter Output

The fixture asserts both `ClaudeAdapter.build_argv` branches produce **byte-identical** argv to v0.9.2.0:

- **NEW SESSION (15 elements):** `["claude", "-p", task, "--model", model, "--append-system-prompt", system_prompt, "--max-turns", "25", "--permission-mode", "bypassPermissions", "--disallowedTools", "AskUserQuestion,ExitPlanMode", "--output-format", "json"]`
- **RESUME (13 elements):** `["claude", "-p", task, "--resume", session_id, "--max-turns", "25", "--permission-mode", "bypassPermissions", "--disallowedTools", "AskUserQuestion,ExitPlanMode", "--output-format", "json"]`

**No fixture drift** — the JSON file matches exactly what `cli_adapters/claude.py:ClaudeAdapter().build_argv(**fixture['*']['inputs'])` produces. The `--disallowedTools` value is the literal string `AskUserQuestion,ExitPlanMode` (no shell quotes — the original `mcp_tools.py:957` single-quotes are shell quoting that vanishes in argv form).

## TEST-05 Baseline

**Hardcoded sha256:** `31ce03b67804ed11c5a5e42be8364c0adfedd356d1e9aed9ce87e8318c9c27a7` (v0.9.2.0).

If `openwebui/init.sh` ever needs to change in a future milestone, **bump `EXPECTED` in `tests/test_init_sh_unchanged.sh` in the same commit**. The failure message points reviewers at PITFALLS Pitfall 10 + the saved-memory rule `feedback_init_sh_marker.md` so the legitimate-bump path is obvious.

## Decisions Made

### `capfd` (not `capsys`) for the SystemExit stderr capture

Per the explicit reminder in 04-01-SUMMARY, `docker_manager.py` uses `print(..., file=sys.stderr) + sys.exit(1)` — the FATAL line is written to file descriptor 2. `capsys` only captures Python-level `sys.stderr` (which is bypassed when `print` writes to fd 2 in some pytest configurations); `capfd` captures the actual fd 2 stream. Using `capfd` produces a reliable `captured.err` regardless of pytest capture mode.

### Argv length assertions adjusted to 15 / 13 (not 14 / 12)

The 04-02-SUMMARY documented argv lengths as 14 (NEW SESSION) and 12 (RESUME), but the actual `ClaudeAdapter.build_argv` output has lengths 15 and 13 respectively (verified by direct invocation). The 14/12 counts in 04-02-SUMMARY appear to count `--max-turns N` as one element instead of two; the test asserts the **actual** output and confirms byte-identical match against the fixture. Functional behaviour is unchanged — this is a cosmetic correction in the assertion message only.

### Two-tier `extra_env` injection coverage

Plan 04-04 specified the test must verify `extra_env["SUBAGENT_CLI"]` is injected. Implemented as two layered guards:

1. **Functional test (`test_extra_env_carries_subagent_cli_via_create_container`)** — patches `get_docker_client` and `USER_DATA_BASE_PATH`, calls `_create_container("test-chat", "test-container")`, captures the `environment` dict passed to `client.containers.create()`, and asserts `SUBAGENT_CLI=opencode` is present.
2. **Source-grep guard (`test_extra_env_injection_line_present_in_source`)** — fallback assertion that `'extra_env["SUBAGENT_CLI"] = SUBAGENT_CLI'` is literally present in `docker_manager.py`. Catches the failure mode where downstream wiring (skill_manager / network) fails before `create()` is reached.

Both pass cleanly in the current build. Phase 6's TEST-06 image-level `docker inspect` test is the third defence-in-depth layer.

### Standalone bash test for TEST-05 (not integrated into `test-project-structure.sh`)

Per CONTEXT D6 + RESEARCH recommendation. The init.sh check is logically distinct from project-structure (existence/layout) checks, and matches the existing one-test-per-script-file pattern (`test-no-corporate.sh`, `test-mcp-endpoint-live.sh`, etc.). CI / pre-push hooks invoke it alongside the others.

## Verification

```
$ python3 -m pytest tests/orchestrator/test_cli_runtime.py tests/orchestrator/test_subagent_claude_compat.py -v
... 23 passed in 0.50s

$ bash tests/test_init_sh_unchanged.sh
PASS: openwebui/init.sh matches v0.9.2.0 baseline (sha256 31ce03b6...c9c27a7).

$ git diff HEAD~3 -- computer-use-server/ openwebui/init.sh | wc -l
0

$ ls tests/fixtures/cli/
claude_v0.9.2.0_argv.json

$ ls -l tests/test_init_sh_unchanged.sh
-rwxr-xr-x ... tests/test_init_sh_unchanged.sh

$ head -2 tests/orchestrator/test_cli_runtime.py tests/orchestrator/test_subagent_claude_compat.py tests/test_init_sh_unchanged.sh
==> tests/orchestrator/test_cli_runtime.py <==
# SPDX-License-Identifier: BUSL-1.1
# Copyright (c) 2025 Open Computer Use Contributors
==> tests/orchestrator/test_subagent_claude_compat.py <==
# SPDX-License-Identifier: BUSL-1.1
# Copyright (c) 2025 Open Computer Use Contributors
==> tests/test_init_sh_unchanged.sh <==
#!/bin/bash
# SPDX-License-Identifier: BUSL-1.1
```

All success criteria met:
- TEST-02 fully green (resolver, banner, extra_env injection)
- ADAPT-02 byte-compat proven for both ClaudeAdapter branches + parse_result roundtrip
- TEST-05 baseline matches; tamper detection verified
- Code files (`computer-use-server/`, `openwebui/init.sh`) UNCHANGED across all three plan commits
- All new files have BUSL-1.1 SPDX header (Python: line 1; Bash: line 2 after shebang)
- All commits attributed to `i@yambr.com`, English-only

## Deviations from Plan

**Argv length asserts (15/13 instead of 14/12):** Cosmetic correction. The plan's 14/12 numbers were copied from 04-02-SUMMARY which appears to have miscounted (treating `--max-turns N` as one element). The fixture content is unchanged from the plan; only the length assertion numerics were adjusted to match the actual `len(adapter.build_argv(...))`. This is **not** a Rule 1/2/3 deviation — the tests still verify byte-identical equality; the length asserts are belt-and-braces second checks.

Otherwise: plan executed exactly as written. No Rule 1/2/3 auto-fixes applied. No checkpoints, no auth gates, no architectural questions.

## Self-Check: PASSED

- FOUND: tests/orchestrator/test_cli_runtime.py (BUSL-1.1, 19 test cases, all green)
- FOUND: tests/orchestrator/test_subagent_claude_compat.py (BUSL-1.1, 4 test cases, all green)
- FOUND: tests/fixtures/cli/claude_v0.9.2.0_argv.json (valid JSON, both new_session + resume keys)
- FOUND: tests/test_init_sh_unchanged.sh (BUSL-1.1, executable, baseline sha256 present)
- FOUND commit: 356f027 (`test(04-04): add cli_runtime resolver test suite (TEST-02)`)
- FOUND commit: a7269ad (`test(04-04): add ClaudeAdapter golden-snapshot byte-compat (ADAPT-02)`)
- FOUND commit: 9174576 (`test(04-04): add init.sh sha256 byte-equals regression (TEST-05)`)
- VERIFIED: `git diff HEAD~3 -- computer-use-server/ openwebui/init.sh | wc -l` returns 0
- VERIFIED: `bash tests/test_init_sh_unchanged.sh` exits 0 and tamper detection works
- VERIFIED: `pytest tests/orchestrator/test_cli_runtime.py tests/orchestrator/test_subagent_claude_compat.py` -> 23 passed
