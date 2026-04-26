---
phase: 06-per-cli-auth-config
plan: 01
subsystem: orchestrator/docker_manager
tags: [auth, security, multi-cli, pitfall-1, pitfall-7, AUTH-01]
requires:
  - SUBAGENT_CLI selector (Phase 4)
  - CLAUDE_CODE_PASSTHROUGH_ENVS (Phase 3)
provides:
  - CODEX_PASSTHROUGH_ENVS
  - OPENCODE_PASSTHROUGH_ENVS
  - _PASSTHROUGH_BY_CLI dispatch
  - per-CLI auth gating in _create_container
  - OPENCODE_CONFIG=/tmp/opencode.json env pin
  - defensive ~/.local/share/opencode/auth.json scrub
affects:
  - mcp_tools.sub_agent (inherits OPENCODE_CONFIG via docker exec)
tech-stack:
  added: []
  patterns:
    - module-level passthrough tuples with SUBAGENT_CLI dispatch
    - container.exec_run defensive cleanup as best-effort
key-files:
  created: []
  modified:
    - computer-use-server/docker_manager.py
decisions:
  - Gate legacy ANTHROPIC_AUTH_TOKEN/BASE_URL block on SUBAGENT_CLI=='claude' (closes T-06-01-02)
  - Gate ANTHROPIC_CUSTOM_HEADERS user-email injection on claude only (T-06-01-03)
  - Pin OPENCODE_CONFIG into extra_env (not just entrypoint export) so docker exec subprocesses inherit it (T-06-01-05)
metrics:
  completed: 2026-04-26
  duration: ~10min
  tasks: 2
  files: 1
requirements:
  - AUTH-01
---

# Phase 6 Plan 01: Per-CLI auth allowlist + scrub Summary

Per-CLI auth env var dispatch in `_create_container`: only the active SUBAGENT_CLI's allowlist is injected into the sandbox container, with defensive OpenCode auth.json scrub and an `OPENCODE_CONFIG=/tmp/opencode.json` env pin so `docker exec` subprocesses cannot fall back to volume-persisted credentials.

## What Was Built

### Module-level passthrough constants (Task 1, commit `323445a`)

Added to `computer-use-server/docker_manager.py` next to existing `CLAUDE_CODE_PASSTHROUGH_ENVS`:

- `CODEX_PASSTHROUGH_ENVS` — `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `CODEX_MODEL`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_VERSION`
- `OPENCODE_PASSTHROUGH_ENVS` — `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENCODE_MODEL`
- `_PASSTHROUGH_BY_CLI = {claude, codex, opencode}` dispatch mapping

`CLAUDE_CODE_PASSTHROUGH_ENVS` is byte-identical to before (Phase 3 GATEWAY-03 invariant preserved).

### `_create_container` per-CLI gating (Task 2, commit `a87f498`)

Four edits inside `_create_container`:

1. **Edit 1 — replaced unconditional loop:** `for _name, _value in CLAUDE_CODE_PASSTHROUGH_ENVS` → `for _name, _value in _PASSTHROUGH_BY_CLI[SUBAGENT_CLI]`. Closes Pitfall 1 (auth bleed).
2. **Edit 1b — gated standalone Anthropic block:** the `if anthropic_key:` block (ANTHROPIC_AUTH_TOKEN + ANTHROPIC_BASE_URL) wrapped with `if SUBAGENT_CLI == "claude":`. Without this, codex/opencode containers would still receive Anthropic gateway vars from the legacy Phase 3 path.
3. **Edit 1b cont — gated ANTHROPIC_CUSTOM_HEADERS:** the `x-openwebui-user-email` custom-header injection wrapped on `claude` only. Codex/opencode no longer receive a spurious anthropic-flavoured env var.
4. **Edit 1c — OPENCODE_CONFIG pin:** when `SUBAGENT_CLI == "opencode"`, sets `extra_env["OPENCODE_CONFIG"] = "/tmp/opencode.json"` so `docker inspect` shows it in `Config.Env` and every `docker exec opencode ...` subprocess inherits it (entrypoint shell exports do NOT propagate to docker exec).
5. **Edit 2 — defensive scrub:** added `container.exec_run("rm -f /home/assistant/.local/share/opencode/auth.json", user="assistant")` wrapped in try/except as the last action before `return container`. Handles resurrected containers that may carry leftover OpenCode auth from earlier `opencode auth login` experiments.

## Verification

- `grep -q "^CODEX_PASSTHROUGH_ENVS = (" computer-use-server/docker_manager.py` → 0
- `grep -q "^OPENCODE_PASSTHROUGH_ENVS = (" computer-use-server/docker_manager.py` → 0
- `grep -q "^_PASSTHROUGH_BY_CLI = {" computer-use-server/docker_manager.py` → 0
- `grep -q "_PASSTHROUGH_BY_CLI\[SUBAGENT_CLI\]" computer-use-server/docker_manager.py` → 0
- `grep -q 'if SUBAGENT_CLI == "claude":' computer-use-server/docker_manager.py` → 0
- `grep -q 'if SUBAGENT_CLI == "opencode":' computer-use-server/docker_manager.py` → 0
- `grep -q 'extra_env\["OPENCODE_CONFIG"\] = "/tmp/opencode.json"' computer-use-server/docker_manager.py` → 0
- `grep -q "rm -f /home/assistant/.local/share/opencode/auth.json" computer-use-server/docker_manager.py` → 0
- `! grep -q "for _name, _value in CLAUDE_CODE_PASSTHROUGH_ENVS:" computer-use-server/docker_manager.py` → 0 (legacy loop removed)
- `python3 -m pytest tests/orchestrator/test_cli_runtime.py tests/orchestrator/test_cli_adapters.py tests/orchestrator/test_subagent_claude_compat.py tests/orchestrator/test_docker_manager.py -q` → **77 passed, 6 warnings**
- `bash tests/test_init_sh_unchanged.sh` → PASS (sha256 baseline match)
- Module load: `import docker_manager; assert set(docker_manager._PASSTHROUGH_BY_CLI) == {'claude','codex','opencode'}` → OK
- Files unchanged in this plan: `Dockerfile`, `cli_runtime.py`, `cli_adapters/*`, `mcp_tools.py`, `openwebui/init.sh` (verified by `git diff --name-only HEAD~2 HEAD` showing only `computer-use-server/docker_manager.py`)

## Deviations from Plan

None — plan executed exactly as written, including the in-plan recommendations to gate the standalone Anthropic block and ANTHROPIC_CUSTOM_HEADERS on `SUBAGENT_CLI == "claude"`.

## Threat Mitigations Applied

| Threat ID | Mitigation |
|-----------|------------|
| T-06-01-01 | `_PASSTHROUGH_BY_CLI[SUBAGENT_CLI]` dispatch isolates auth env per CLI |
| T-06-01-02 | Standalone Anthropic block gated on `SUBAGENT_CLI == "claude"` |
| T-06-01-03 | `ANTHROPIC_CUSTOM_HEADERS` gated on `SUBAGENT_CLI == "claude"` |
| T-06-01-04 | `container.exec_run("rm -f .../opencode/auth.json", user="assistant")` defensive scrub |
| T-06-01-05 | `extra_env["OPENCODE_CONFIG"] = "/tmp/opencode.json"` lands in `Config.Env`, inherited by `docker exec` subprocesses |
| T-06-01-08 | Scrub runs as `user="assistant"`, cannot escape `/home/assistant` |

## Commits

- `323445a` feat(06-01): add CODEX/OPENCODE passthrough tuples + _PASSTHROUGH_BY_CLI dispatch
- `a87f498` feat(06-01): per-CLI auth dispatch + OPENCODE_CONFIG pin + auth.json scrub

## Follow-ups (handled in later plans)

- Plan 06-02: Dockerfile codex + opencode npm installs at pinned versions
- Plan 06-03: Marker-gated entrypoint heredoc renders `/tmp/opencode.json` and `~/.codex/config.toml`
- Plan 06-04: New `tests/orchestrator/test_passthrough_isolation.py` regression guard for the cross-CLI isolation contract this plan establishes
- Plan 06-05: Image build + TEST-01 / TEST-06 smoke

## Self-Check: PASSED

- `computer-use-server/docker_manager.py` modified — FOUND
- Commit `323445a` — FOUND
- Commit `a87f498` — FOUND
- All listed verification commands exit 0
- Phase 4+5 test suite (77 tests) green
- TEST-05 invariant (init.sh unchanged) green
