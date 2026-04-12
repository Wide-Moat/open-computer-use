---
phase: 03-claude-code-gateway-compatibility
plan: 02
subsystem: tests
tags:
  - tests
  - pytest
  - docker-manager
  - sub-agent
  - env-injection
dependency_graph:
  requires:
    - "03-01-SUMMARY.md (code changes the tests exercise)"
  provides:
    - "tests/orchestrator/test_docker_manager.py — three-path env-injection matrix + regression guards"
    - "tests/orchestrator/test_sub_agent_model_resolution.py — seven alias-resolution cases"
  affects:
    - "CI surface: 13 new tests added to tests/orchestrator/ (6 + 7)"
tech_stack:
  added: []
  patterns:
    - "patch.dict(os.environ) + importlib.reload(docker_manager|mcp_tools) to re-read module-scope env constants"
    - "patch get_docker_client on docker_manager module path; inspect call_args.kwargs['environment']"
    - "IsolatedAsyncioTestCase + patch.object on mcp_tools._execute_bash to capture claude CLI command"
key_files:
  created:
    - "tests/orchestrator/test_docker_manager.py"
    - "tests/orchestrator/test_sub_agent_model_resolution.py"
  modified: []
requirements:
  covered:
    - GATEWAY-05
    - GATEWAY-06
    - GATEWAY-07
    - GATEWAY-12
    - GATEWAY-MH-02
    - GATEWAY-MH-03
    - GATEWAY-MH-04
    - GATEWAY-MH-05
    - GATEWAY-MH-06
    - GATEWAY-MH-07
    - GATEWAY-MH-11
  deferred: []
commits:
  - "6544bdb test(03-02): add docker_manager env-injection matrix tests"
  - "495576f test(03-02): add sub_agent model resolution tests"
status: complete
---

## What was built

Two new pytest files under `tests/orchestrator/` exercising every code change
from plan 03-01 behind executable tests.

### `test_docker_manager.py` (Task 1, commit 6544bdb)

Six tests across two classes:

- `TestDockerManagerEnvInjection` (5 tests)
  - `test_path_a_zero_config_injects_no_gateway_vars` — asserts no
    `ANTHROPIC_*` / `CLAUDE_CODE_*` key appears in the `environment` dict
    when no host env vars are set (GATEWAY-MH-02).
  - `test_path_b_auth_only_injects_token_and_default_base_url` — only
    `ANTHROPIC_AUTH_TOKEN` + default `ANTHROPIC_BASE_URL=https://api.anthropic.com`
    land in `environment`; the ten gateway vars stay absent (GATEWAY-MH-03).
  - `test_path_c_custom_gateway_injects_all_twelve_keys` — all twelve keys
    are injected with their exact host values (GATEWAY-MH-04).
  - `test_empty_string_env_vars_are_not_injected` — the `if _value:` guard
    skips empty-string env vars (prevents accidental empty-string injection).
  - `test_anthropic_custom_headers_injection_regression_guard` — sets
    `current_user_email.set("alice@example.com")` before `_create_container`
    and asserts `environment["ANTHROPIC_CUSTOM_HEADERS"] ==
    "x-openwebui-user-email: alice@example.com"` plus the two git-identity
    env vars (GATEWAY-MH-07).

- `TestContextVarAnthropicBaseUrlDefault` (1 test)
  - `test_current_anthropic_base_url_default_is_none_after_reload` — asserts
    `current_anthropic_base_url.get() is None` after module reload (GATEWAY-01
    unit test — guards against regression of the root-cause ContextVar default).

Each test runs inside a fresh `contextvars.Context` (via
`asyncio.run`-style isolation) to prevent ContextVar leakage into sibling
orchestrator tests. Docker calls are intercepted at
`docker_manager.get_docker_client` and the `environment=` kwarg on
`containers.create` is the assertion target.

### `test_sub_agent_model_resolution.py` (Task 2, commit 495576f)

Seven async tests in `TestSubAgentModelResolution(unittest.IsolatedAsyncioTestCase)`:

1. `test_alias_sonnet_default` — `sub_agent(model="sonnet")` reaches the CLI
   as `--model claude-sonnet-4-6` when no env override is set.
2. `test_alias_opus_default` — same for `opus` → `claude-opus-4-6`.
3. `test_alias_haiku_default` — same for `haiku` → `claude-haiku-4-5`.
4. `test_direct_model_id_passes_through` — `"claude-sonnet-4-6"` reaches the
   CLI unchanged (no silent reset).
5. `test_litellm_style_model_id_passes_through` — `"anthropic/claude-sonnet-4-6"`
   passes through unchanged.
6. `test_empty_model_falls_back_to_sonnet` — empty string falls back via
   `SUB_AGENT_DEFAULT_MODEL` to `claude-sonnet-4-6` with display alias
   `sonnet`.
7. `test_sonnet_alias_honours_env_override` — with
   `ANTHROPIC_DEFAULT_SONNET_MODEL="azure/my-deployment"` set,
   `sub_agent(model="sonnet")` reaches the CLI as
   `--model azure/my-deployment` (and NOT `claude-sonnet-4-6`).

## Chosen patch target

Task 2 patches **`mcp_tools._execute_bash`** rather than
`asyncio.create_subprocess_exec`.

Rationale: after 03-01, `sub_agent()` builds a `claude_command` string that
includes `--model <MODEL_ID>` and executes it via
`asyncio.to_thread(_execute_bash, container, claude_command, ...)`. Patching
`_execute_bash` captures the full command string (and therefore the resolved
model ID) without spawning any real subprocess. The fake returns a
synthetic Claude JSON result line so `_format_sub_agent_result` parses cleanly
and `sub_agent` returns a formatted string — the tests then assert both on
the captured `--model` token and on the `**Model:** <alias>` line in the
result string.

## Test results

All tests run inside `python:3.13-slim` per CLAUDE.md:

```
docker run --rm --platform linux/amd64 -v "$(pwd):/app" -w /app python:3.13-slim \
  bash -c "pip install -q -r computer-use-server/requirements.txt pytest pytest-asyncio && \
           python -m pytest tests/orchestrator/ -v"
```

- `test_docker_manager.py`: **6 passed**
- `test_sub_agent_model_resolution.py`: **7 passed**
- Full `tests/orchestrator/` suite: **61 passed**, 0 failed, 0 new warnings
  attributable to this plan.

The only warnings observed (`datetime.utcnow()` deprecation in
`docker_manager.py:696` and `starlette` `multipart` pending deprecation) are
pre-existing and unrelated to Phase 3.

## Deviations from the plan

None of substance.

- **Clarification**: The plan's `_reload_with_env` helper was implemented
  per-test via a direct `os.environ.pop` loop + `patch.dict(..., clear=False)`
  + `importlib.reload(docker_manager)` inside each test body. Functionally
  identical; kept the helper inline for clarity because each test's
  `env_overrides` dict is short (1-12 entries).
- **Clarification**: `sub_agent` tests use a `_fake_execute_bash_factory`
  that filters for `claude` commands and ignores plan-file writes and
  MCP-config writes. This avoids the fake capturing the wrong command when
  `sub_agent` writes the prompt file before invoking the CLI.

## Follow-ups / notes for 03-03

- `.env.example` and `docker-compose.yml` in plan 03-03 should declare the
  same ten `CLAUDE_CODE_PASSTHROUGH_ENVS` names the tests assert on. Any
  typo in 03-03 will silently break the passthrough — the tests will still
  pass because they patch `os.environ` directly, so 03-03's completion
  criteria must independently grep for every name in the ten-tuple.
- The `ANTHROPIC_BASE_URL` fallback default `https://api.anthropic.com`
  (no trailing slash) is asserted in `test_path_b_*`; 03-03 docs must use
  the same spelling to avoid operator confusion.

## Self-check

- [x] Both new test files exist with SPDX headers.
- [x] Each task committed atomically (6544bdb, 495576f).
- [x] `python -m pytest tests/orchestrator/ -v` in `python:3.13-slim` → 61 passed.
- [x] No real API keys (`grep -cE 'sk-[A-Za-z0-9]{20,}'` returns 0).
- [x] No pre-existing orchestrator test broken.

**Self-check: PASSED**
