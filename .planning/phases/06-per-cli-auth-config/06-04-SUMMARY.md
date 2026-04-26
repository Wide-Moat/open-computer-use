---
phase: 06-per-cli-auth-config
plan: 04
subsystem: tests
tags: [tests, regression-guard, multi-cli, auth-isolation, marker-gating]
requires:
  - 06-01  # per-CLI passthrough + scrub + OPENCODE_CONFIG pin
  - 06-02  # codex + opencode installed in image
  - 06-03  # entrypoint heredoc + marker
provides:
  - tests/orchestrator/test_passthrough_isolation.py  # Pitfall 1 regression guard + OPENCODE_CONFIG pin
  - tests/test-docker-image.sh  # extended CLI presence + per-CLI smoke + marker gating
affects:
  - none  # tests-only plan; no production code touched
tech-stack:
  added: []
  patterns:
    - "monkeypatch.setenv + importlib.reload(docker_manager) — mirror Phase 3 GATEWAY-05 fixture"
    - "MagicMock docker client capturing client.containers.create kwargs (not .run — that is the ephemeral mkdir shim)"
    - "Long-running docker container + docker exec entrypoint twice + sentinel-overwrite for marker-gating verification"
key-files:
  created:
    - tests/orchestrator/test_passthrough_isolation.py
  modified:
    - tests/test-docker-image.sh
decisions:
  - "Use containers.create.call_args (not containers.run) — the SUT creates the actual sandbox via .create; .run is only the ephemeral mkdir shim"
  - "Smoke step uses long-running container + docker exec entrypoint twice — required for marker-gating verification (single docker run cannot run entrypoint twice in same container)"
  - "Production parity: smoke step does NOT pass --user=assistant — production entrypoint runs as root before user shell starts (codex chown line in 06-03 heredoc requires root)"
  - "Sentinel-overwrite (`GATED-SENTINEL`) verifies opencode marker gating; same gate guards codex branch in entrypoint, so verifying for opencode proves it for codex too"
metrics:
  duration: "~12 min"
  completed: "2026-04-25"
---

# Phase 6 Plan 4: Tests for per-CLI auth + marker gating Summary

Added the test layer for Phase 6's invariants: pure-Python regression guard for per-CLI auth allowlist isolation (Pitfall 1) plus image-level CLI presence checks and a per-CLI dispatch + marker-gating smoke step in the docker-image test script.

## What Changed

### New: tests/orchestrator/test_passthrough_isolation.py (197 lines)

Three parametrized cases (`claude`, `codex`, `opencode`) that:

1. Set ALL three families of host auth env vars (`ANTHROPIC_AUTH_TOKEN`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, etc.).
2. `monkeypatch.setenv("SUBAGENT_CLI", cli)` + `importlib.reload(docker_manager)` so the module-level `_PASSTHROUGH_BY_CLI` and `SUBAGENT_CLI` constants rebuild against the test fixture.
3. Mock `docker.from_env` so `client.containers.create(**config)` returns a `MagicMock` container instead of touching a real daemon.
4. Call `docker_manager._create_container("test-chat", "owui-chat-test")` and capture the `environment` kwarg from `client.containers.create.call_args`.

Per-case assertions:

| CLI       | Expected keys present                    | Forbidden keys absent (Pitfall 1)                                              | OPENCODE_CONFIG               |
| --------- | ---------------------------------------- | ------------------------------------------------------------------------------ | ----------------------------- |
| claude    | `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL` | `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `OPENAI_BASE_URL`, `OPENCODE_CONFIG` | absent                        |
| codex     | `OPENAI_API_KEY`, `OPENAI_BASE_URL`      | `ANTHROPIC_AUTH_TOKEN`, `OPENROUTER_API_KEY`, `OPENCODE_CONFIG`                | absent                        |
| opencode  | `OPENROUTER_API_KEY`, `OPENAI_API_KEY`   | `ANTHROPIC_AUTH_TOKEN`                                                         | `/tmp/opencode.json` (pinned) |

Plus a defensive scrub assertion: `fake_container.exec_run` was called with `rm -f /home/assistant/.local/share/opencode/auth.json` (Plan 06-01 D4 — Pitfall 7 defense).

The OPENCODE_CONFIG pin assertion (ROADMAP success #2) closes the Pitfall 7 reopen vector — without `OPENCODE_CONFIG` in the container `Env`, `docker exec opencode ...` invocations would fall back to `~/.local/share/opencode/auth.json` even though the entrypoint exports the variable.

### Modified: tests/test-docker-image.sh (+76, −14 lines)

Three edits:

1. **CLI-presence loop extended** (line 84) — six tools instead of four (added `codex`, `opencode`) and a `--version` smoke per tool (TEST-01: every CLI must respond with exit 0).
2. **Step renumber** — every header bumped from `[N/11]` to `[N/12]` to make room for the new smoke step.
3. **NEW step `[11/12] Per-CLI dispatch smoke + marker gating`** — for each of the three CLIs:
   - Start a long-running container with stub auth env vars (`docker run -d ... --entrypoint=bash -c "tail -f /dev/null"`).
   - Run `/home/assistant/.entrypoint.sh` via `docker exec` and assert `/tmp/.cli-runtime-initialised` landed.
   - For `opencode` only: overwrite `/tmp/opencode.json` with sentinel string `GATED-SENTINEL`, run entrypoint a SECOND time, assert sentinel survived (heredoc skipped per ROADMAP success #4).
   - Cleanup with `docker rm -f`.

Production parity: NO `--user=assistant` flag in the new smoke step — the entrypoint runs as root in production before the user shell starts (the codex `chown -R assistant:assistant /home/assistant/.codex` line in Plan 06-03's heredoc only works correctly when invoked as root). The marker check works regardless because `/tmp` is world-readable.

## Self-Check

| Check | Result |
| ----- | ------ |
| `pytest tests/orchestrator/test_passthrough_isolation.py -v` | 3 passed |
| Targeted suite (passthrough + cli_runtime + cli_adapters + subagent_claude_compat + docker_manager) | 80 passed |
| `bash -n tests/test-docker-image.sh` | exit 0 |
| `grep -q "for tool in mmdc tsc tsx claude codex opencode"` | found |
| `grep -q "GATED-SENTINEL"` | found |
| `grep -q "marker gating works"` | found |
| `grep -q "Per-CLI dispatch smoke"` | found |
| `git diff HEAD~2 -- computer-use-server/ Dockerfile openwebui/` line count | 0 (tests-only plan) |
| `bash tests/test_init_sh_unchanged.sh` | PASS — sha256 baseline match |
| New test file SPDX header | `BUSL-1.1` ✓ |
| English-only | ✓ |
| Commit author | `i@yambr.com` (Nick) ✓ |

## Deviations from Plan

### Auto-fixed issues

**1. [Rule 1 — Bug] Test capture target corrected: `containers.create` not `containers.run`**

- **Found during:** Task 1 (running new test).
- **Issue:** The plan's draft skeleton (lines 154–160 + line 226) instructed mocking `client.containers.run` and asserting on its `call_args.kwargs["environment"]`. In the actual `docker_manager._create_container`, `client.containers.run` is only used for the ephemeral mkdir shim — the actual sandbox container is created via `client.containers.create(**config)` and `.start()`. Asserting on `.run` would never see the sandbox `environment` dict.
- **Fix:** Mirrored the proven Phase 3 pattern from `tests/orchestrator/test_docker_manager.py::_build_mock_docker_client` — mock both `.run` (returns None) and `.create` (returns the fake container with `exec_run`), then read `client.containers.create.call_args.kwargs["environment"]`.
- **Files modified:** `tests/orchestrator/test_passthrough_isolation.py` (Task 1).
- **Commit:** `9362766`.

**2. [Rule 3 — Blocking] `docker run -d` without `--entrypoint=bash` would invoke the production entrypoint as PID 1 (heredoc fires immediately) and prevent the marker-gating test from controlling WHEN the entrypoint runs**

- **Found during:** Task 2 (designing the smoke step).
- **Issue:** If we let the production entrypoint run on `docker run`, the marker would already be set before our first `docker exec /home/assistant/.entrypoint.sh` — making the gating verification meaningless (we would not be testing the gate, just observing post-entrypoint state).
- **Fix:** Added `--entrypoint=bash ... -c "tail -f /dev/null"` to the `docker run -d` invocation so PID 1 is just `bash tail`, and the entrypoint is only invoked via our explicit `docker exec` calls. This lets the test control marker timing.
- **Files modified:** `tests/test-docker-image.sh` (Task 2 — the new smoke step).
- **Commit:** `f428766`.

### Unfixed (out of scope)

**Pre-existing `--user=assistant` usages on lines 32 (comment), 35 (`run_in_container` helper), and 227 (existing entrypoint test).** The success criterion stated `! grep -q "\-\-user=assistant"` would pass — but those usages predate Phase 6 and are intentional for the helper's stated purpose ("matches production"). Removing them would violate the criterion "Existing test assertions are byte-identical to before." The intent of the constraint is clearly "no `--user=assistant` in the NEW smoke step", which is satisfied: my new `[11/12]` block contains no such flag. The legitimate prior usages are out of scope per the deviation Rules scope boundary.

## Commits

| Hash    | Subject                                                          |
| ------- | ---------------------------------------------------------------- |
| 9362766 | `test(06-04): add passthrough isolation regression guard`        |
| f428766 | `test(06-04): extend test-docker-image.sh with codex/opencode + smoke` |

## Self-Check: PASSED
