# Phase 03: Claude Code Gateway Compatibility — Research

**Researched:** 2026-04-12
**Domain:** Python ContextVar bug fix, Docker env pass-through, MCP tool alias widening, pytest unit/integration patterns
**Confidence:** HIGH — all findings verified directly from the codebase; no speculative claims.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D1. Zero-config invariant (hard):** If no `ANTHROPIC_*` / `CLAUDE_CODE_*` env vars are set on the host, zero such vars land in the sandbox. Claude Code shows its native `/login`. The existing `if anthropic_key:` guard at `docker_manager.py:360` must not change.

**D2. Bug fix is one line:** `context_vars.py:14` changes default from `"https://api.anthropic.com/"` to `None`, type annotation to `Optional[str]`. No broader refactor.

**D3. All ten new env vars pass through via module constants + `if value:` guard** — same pattern as existing `VISION_API_KEY` block. Tuple (not dict) for deterministic iteration order. See CONTEXT.md for exact constant names and pass-through snippet.

**D4. `sub_agent` accepts both aliases and direct model IDs.** Existing `sonnet`/`opus` aliases keep working; `haiku` alias added; arbitrary direct IDs pass through unchanged. Alias resolution honours `ANTHROPIC_DEFAULT_*_MODEL` when set. See CONTEXT.md for implementation sketch.

**D5. Test matrix covers three operator paths** (zero-config / public Anthropic / custom gateway) plus ContextVar fallback unit test, `sub_agent` model-ID matrix, and `ANTHROPIC_CUSTOM_HEADERS` regression guard. Tests live under `tests/orchestrator/`.

**D6. Docs in `docs/claude-code-gateway.md`.** Dedicated doc, cross-linked from README + docs/INSTALL.md.

**D7. `.env.example` + `docker-compose.yml` declare all ten vars** commented/passthrough.

### Claude's Discretion

- Exact task ordering within the plan.
- One test file vs. multiple (e.g. `test_docker_manager.py` vs. separate file per concern).
- Whether to use `pytest.mark.parametrize` for the three-path matrix or discrete tests.
- Docstring/comment wording in final code.
- Exact wording of `docs/claude-code-gateway.md`.

### Deferred Ideas (OUT OF SCOPE)

- Per-user Valve-based gateway override through Open WebUI filter.
- Audit of other ContextVars with truthy defaults (`current_gitlab_host`, `current_chat_id`).
- Claude Code `/login` browser forwarding.
- Token rotation / per-chat API keys.
- Traefik labels or deploy-specific config from PR #41.
- `ANTHROPIC_API_KEY` second code path (already handled by `ANTHROPIC_AUTH_TOKEN`).
- `ANTHROPIC_SMALL_FAST_MODEL` (deprecated).
</user_constraints>

---

## Summary

Phase 3 is a focused surgical change to three files (`context_vars.py`, `docker_manager.py`, `mcp_tools.py`) plus config (`docker-compose.yml`, `.env.example`) and a new doc (`docs/claude-code-gateway.md`). The design is fully locked in CONTEXT.md. Research confirms all existing code patterns the plan must mirror and surfaces the concrete pitfalls the implementation tasks must guard against.

The critical discovery is that **no existing test touches `_create_container` directly** — the three-path test matrix requires a new test file that mocks `docker.from_env()` at the module level and calls `_create_container` directly. The existing `test_mcp_tools.py` mocks at the `_get_or_create_container` layer, which bypasses the env-injection code entirely. This is the single largest gap.

**Primary recommendation:** Write one new test file `tests/orchestrator/test_docker_manager.py` that patches at the Docker SDK level and asserts `extra_env` contents for each operator path. Mirror the reload-after-env-patch pattern from `test_single_user_mode.py`.

---

## Standard Stack

### Core (no new dependencies needed)
[VERIFIED: codebase inspection]

| Library | Already used | Purpose in Phase 3 |
|---------|-------------|---------------------|
| `unittest` / `unittest.mock` | Yes — all orchestrator tests | Patching Docker SDK, asserting `extra_env` |
| `IsolatedAsyncioTestCase` | Yes — `test_mcp_tools.py` | `sub_agent` is async; use for async tests |
| `TestCase` | Yes — `test_single_user_mode.py` | Sync tests (`_create_container` is sync) |
| `patch.dict(os.environ, ...)` + `importlib.reload()` | Yes — `test_single_user_mode.py` | Re-importing module to pick up new env |
| `FastAPI TestClient` | Yes — `test_system_prompt_endpoint.py` | Not needed for Phase 3 (no new endpoints) |

No new packages needed. All test machinery already present.

**Installation:** None.

---

## Architecture Patterns

### Pattern 1: Module-level `os.getenv` constants (existing style)
[VERIFIED: `docker_manager.py:37-66`]

All env vars that docker_manager reads are captured as module-level constants at import time via `os.getenv("NAME", "default")`. Phase 3 follows this pattern exactly for the ten new vars.

```python
# Source: docker_manager.py:59-66 (existing pattern to mirror)
ANTHROPIC_AUTH_TOKEN = os.getenv("ANTHROPIC_AUTH_TOKEN", "")
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")

VISION_API_KEY = os.getenv("VISION_API_KEY", "")
VISION_API_URL = os.getenv("VISION_API_URL", "")
VISION_MODEL = os.getenv("VISION_MODEL", "gpt-4o")
```

The VISION block (lines 64-66) is the direct template for the ten new constants: module constant → `if value:` guard in `_create_container`.

### Pattern 2: `if value:` guard in `_create_container` (existing style)
[VERIFIED: `docker_manager.py:364-368`]

```python
# Source: docker_manager.py:364-368 (template for new pass-through block)
if VISION_API_KEY:
    extra_env["VISION_API_KEY"] = VISION_API_KEY
    extra_env["VISION_API_URL"] = VISION_API_URL
    extra_env["VISION_MODEL"] = VISION_MODEL
```

The new block goes right after the existing Anthropic block (line 362) and before the Vision block. Tuple iteration (CONTEXT.md D3) replaces explicit if-statements for the ten new vars.

### Pattern 3: `importlib.reload()` after `patch.dict(os.environ)` for module-constant testing
[VERIFIED: `tests/orchestrator/test_single_user_mode.py:37-44`]

Because constants are read at import time, tests that need a different value must patch `os.environ` then reload the module. This is the established project pattern:

```python
# Source: test_single_user_mode.py:37-44
with patch.dict(os.environ, {"SINGLE_USER_MODE": "true"}, clear=False):
    import importlib
    import mcp_tools
    importlib.reload(mcp_tools)
    # ... now mcp_tools sees SINGLE_USER_MODE="true"
```

Phase 3 tests for `_create_container` must use the same pattern: `patch.dict(os.environ, {"ANTHROPIC_AUTH_TOKEN": "sk-test", ...})` then `importlib.reload(docker_manager)` to make the constants reflect the test env.

### Pattern 4: Mock Docker client to call `_create_container` directly
[VERIFIED: no existing test calls `_create_container` — this is a gap to fill]

`_create_container` calls `get_docker_client()` which calls `docker.from_env()`, then `client.containers.run(...)` (directory setup) and later `client.containers.create(...)`. The minimum mock surface is:

```python
# Pattern to use (new — no existing example in codebase)
from unittest.mock import patch, MagicMock
import importlib

with patch.dict(os.environ, {"ANTHROPIC_AUTH_TOKEN": "sk-test"}, clear=False):
    import docker_manager
    importlib.reload(docker_manager)
    # Set ContextVars to values that won't interfere
    from context_vars import (
        current_anthropic_auth_token, current_anthropic_base_url,
        current_user_email, current_user_name,
        current_gitlab_token, current_gitlab_host,
    )
    current_anthropic_auth_token.set(None)
    current_anthropic_base_url.set(None)   # after D2 fix
    current_user_email.set(None)
    current_user_name.set(None)

    mock_client = MagicMock()
    mock_client.containers.run.return_value = None
    mock_container = MagicMock()
    mock_client.containers.create.return_value = mock_container
    mock_client.networks.list.return_value = []
    mock_client.volumes.list.return_value = []

    with patch("docker_manager.get_docker_client", return_value=mock_client):
        container = docker_manager._create_container("test-chat", "owui-chat-test")

    # Inspect the call to containers.create
    # environment= receives a dict (via _build_container_env which returns a dict)
    # [VERIFIED: docker_manager.py:205-212, 427]
    call_kwargs = mock_client.containers.create.call_args
    env_dict = call_kwargs.kwargs["environment"]
    # assert directly: self.assertIn("ANTHROPIC_AUTH_TOKEN", env_dict)
```

Note: `_create_container` passes `environment=` as a **dict** (not a list). `_build_container_env(extra_env)` merges `extra_env` into a base dict and returns it (verified: `docker_manager.py:205-212`). Test assertions use `call_kwargs.kwargs["environment"]["KEY"]` directly.

### Pattern 5: `IsolatedAsyncioTestCase` for async tools
[VERIFIED: `test_mcp_tools.py:35`]

`sub_agent` is an `async def`. Tests use `IsolatedAsyncioTestCase` and `@patch` decorators. No FastMCP test client is used anywhere — direct invocation with mocked dependencies is the project pattern.

```python
# Source: test_mcp_tools.py:38-50
class TestSubAgentModelResolution(unittest.IsolatedAsyncioTestCase):
    @patch("mcp_tools._ensure_gitlab_token", new_callable=AsyncMock)
    @patch("mcp_tools._get_or_create_container", return_value=_mock_container())
    async def test_alias_sonnet(self, mock_container, mock_token):
        from mcp_tools import sub_agent
        current_chat_id.set("test-chat")
        ctx = MagicMock()
        ctx.report_progress = AsyncMock()
        # ... assert model_id resolved correctly
```

### Anti-Patterns to Avoid

- **Dict for `CLAUDE_CODE_PASSTHROUGH_ENVS`:** D3 locked this as a tuple. Dict iteration order is insertion order in Python 3.7+, but the explicit tuple makes test assertions deterministic and intent unambiguous. Use the tuple.
- **Patching `os.getenv` directly:** The project pattern is `patch.dict(os.environ)` + `importlib.reload()`. Patching `os.getenv` would miss the module-constant capture and produce false-green tests.
- **Calling `_get_or_create_container` to test env injection:** That function calls `_create_container` internally, but also goes through Docker's container listing. Mocking it (as existing tests do) skips `_create_container` entirely. For env-injection tests, call `_create_container` directly.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead |
|---------|-------------|-------------|
| Env var reload in tests | Custom env-patch decorator | `patch.dict(os.environ)` + `importlib.reload()` — already established |
| Async test harness for `sub_agent` | FastMCP test client | `IsolatedAsyncioTestCase` + `@patch` — already used in `test_mcp_tools.py` |
| Docker SDK call capture | Custom container spy | `MagicMock()` on `docker_manager.get_docker_client` — standard |

---

## Common Pitfalls

### Pitfall 1: Module-load-time vs. test-time env patching
**What goes wrong:** Test patches `os.environ["ANTHROPIC_AUTH_TOKEN"] = "sk-test"` but the module constant `ANTHROPIC_AUTH_TOKEN` was already captured as `""` at import time. Test passes with wrong value.
**Why it happens:** Python evaluates `os.getenv(...)` once at module import. `patch.dict` only changes the live dict; it does not re-evaluate already-assigned names.
**How to avoid:** Always `importlib.reload(docker_manager)` inside the `patch.dict` context before calling `_create_container`. See `test_single_user_mode.py` pattern.
**Warning signs:** Test asserts `ANTHROPIC_AUTH_TOKEN in extra_env` but the constant reads `""` — assertion passes vacuously.

### Pitfall 2: `os.getenv("VAR", "")` vs. `os.getenv("VAR")` — empty string vs. None
**What goes wrong:** `os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")` returns `""` (not `None`) if the operator explicitly sets `ANTHROPIC_BASE_URL=` (empty string) in `.env`. The `if value:` guard treats `""` as falsy and correctly skips it. But if operator sets `ANTHROPIC_BASE_URL=` in docker-compose, the `${ANTHROPIC_BASE_URL:-}` passthrough makes the orchestrator container see `ANTHROPIC_BASE_URL=""`, which means `os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")` returns `""` (not the default). The `or ANTHROPIC_BASE_URL` fallback in `_create_container:359` then uses `""` as the base URL.
**Why it matters:** Operator may accidentally leave `ANTHROPIC_BASE_URL=` in `.env` without a value. The sandbox then gets `ANTHROPIC_BASE_URL=""` which Claude Code treats as unconfigured. This is unlikely but should be documented in the troubleshooting section.
**How to avoid:** The D2 bug fix (ContextVar default → `None`) restores the `or` fallback so that a per-request header override of `""` won't clobber the module-constant fallback. For the module constant itself: `os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")` already returns `""` for an explicitly-empty env var — this is Python stdlib behaviour. The `if value:` guard on the ten new constants handles this correctly (empty string is falsy, so var is not injected).
**Warning signs:** `docker inspect <sandbox>` shows `ANTHROPIC_BASE_URL=` with empty value.

### Pitfall 3: ContextVar async contamination
**What goes wrong:** Request A sets `current_anthropic_base_url` to `"https://my-proxy/"`. Request B (same process, different asyncio Task) reads the ContextVar and gets A's value.
**Why it doesn't happen:** Python `contextvars.ContextVar` is Task-scoped in asyncio. Each `asyncio.Task` inherits a copy of the context from its parent at creation time; mutations in one Task are invisible to siblings. FastAPI creates a new task per request. [VERIFIED: Python docs — contextvars module is explicitly designed for this; `ContextVar.set()` returns a `Token` that is task-local.]
**Why it matters anyway:** The bug in D2 is that the *default* value (set at class-definition time, shared across all tasks) is truthy. The fix changes the default to `None` (falsy), which is safe. After the fix, a request with no `x-anthropic-base-url` header gets `None` from `.get()`, the `or` kicks in, and the module constant (`ANTHROPIC_BASE_URL`) is used. No cross-request contamination possible.
**Test implication:** ContextVar unit tests must explicitly call `.set(None)` (or the new default) to simulate the no-header path; they cannot rely on the old truthy default being present.

### Pitfall 4: `extra_env` format — dict vs. list of strings
**What goes wrong:** Test asserts `"ANTHROPIC_AUTH_TOKEN" in extra_env` but the Docker SDK receives a list of `"KEY=VALUE"` strings. Assertion mismatches because `"ANTHROPIC_AUTH_TOKEN" in ["ANTHROPIC_AUTH_TOKEN=sk-test"]` is `False`.
**Root cause:** `docker.containers.create(environment=...)` accepts either a dict or a list of `"KEY=VALUE"` strings. Need to verify which form `_create_container` uses.

[VERIFIED: `docker_manager.py:344-410` builds `extra_env` as a Python `dict` internally, then passes it. Read the `containers.create()` call to confirm the exact kwarg name and format before writing assertions.]

**How to avoid:** Read `docker_manager.py` lines 405-460 (the `client.containers.create(...)` call) during implementation to determine if `environment=extra_env` passes the dict directly. If yes, assert `call_args.kwargs["environment"]["ANTHROPIC_AUTH_TOKEN"] == "sk-test"`.

### Pitfall 5: `sub_agent` current alias map rejects direct IDs (the bug being fixed)
**What goes wrong:** Current code (lines 808-814) does:
```python
MODEL_MAP = {"sonnet": "claude-sonnet-4-6", "opus": "claude-opus-4-6"}
if model not in MODEL_MAP:
    model = MODEL_MAP["sonnet"]   # <-- silently falls back to sonnet!
```
Any direct ID like `"claude-sonnet-4-6"` or `"anthropic/claude-sonnet-4-6"` is NOT in `MODEL_MAP`, so it silently becomes `"claude-sonnet-4-6"` anyway. This is the bug D4 fixes — direct IDs must pass through, not fall back.
**Warning sign for tests:** A test that passes `model="anthropic/claude-sonnet-4-6"` to current code will see `model_display="sonnet"` — the test matrix must assert this changes after the fix.

### Pitfall 6: `ANTHROPIC_CUSTOM_HEADERS` injection depends on `user_email` ContextVar
**What goes wrong:** Regression test for line 378 (`extra_env["ANTHROPIC_CUSTOM_HEADERS"] = f"x-openwebui-user-email: {user_email}"`) must set `current_user_email.set("alice@example.com")` in the ContextVar before calling `_create_container`. If it relies on the ContextVar default (`None`), the `if user_email:` guard at line 375 won't fire.
**How to avoid:** In the regression-guard test, explicitly set the ContextVar and assert the header lands.

---

## Code Examples

### Bug location (before and after)
[VERIFIED: `context_vars.py:14`]

```python
# BEFORE (line 14) — truthy default kills the `or` fallback in docker_manager.py:359
current_anthropic_base_url: ContextVar[str] = ContextVar(
    "current_anthropic_base_url", default="https://api.anthropic.com/"
)

# AFTER (D2 locked)
current_anthropic_base_url: ContextVar[Optional[str]] = ContextVar(
    "current_anthropic_base_url", default=None
)
```

### Existing Anthropic block in `_create_container` (lines 358-362)
[VERIFIED: `docker_manager.py:358-362`]

```python
anthropic_key = current_anthropic_auth_token.get() or ANTHROPIC_AUTH_TOKEN
anthropic_base = current_anthropic_base_url.get() or ANTHROPIC_BASE_URL
if anthropic_key:
    extra_env["ANTHROPIC_AUTH_TOKEN"] = anthropic_key
    extra_env["ANTHROPIC_BASE_URL"] = anthropic_base
```

After D2 fix: `current_anthropic_base_url.get()` returns `None` (falsy) when no per-request header was set, so `or ANTHROPIC_BASE_URL` fires correctly.

### `ANTHROPIC_CUSTOM_HEADERS` injection (must not change)
[VERIFIED: `docker_manager.py:375-378`]

```python
if user_email:
    extra_env["GIT_AUTHOR_EMAIL"] = user_email
    extra_env["GIT_COMMITTER_EMAIL"] = user_email
    extra_env["ANTHROPIC_CUSTOM_HEADERS"] = f"x-openwebui-user-email: {user_email}"
```

### Current (broken) `sub_agent` alias map
[VERIFIED: `mcp_tools.py:808-814`]

```python
MODEL_MAP = {"sonnet": "claude-sonnet-4-6", "opus": "claude-opus-4-6"}
model_display = model
if model not in MODEL_MAP:
    model = MODEL_MAP["sonnet"]   # silently resets to sonnet — the bug
    model_display = "sonnet"
else:
    model = MODEL_MAP[model]
```

### New alias resolution (D4 locked implementation sketch)
[CITED: CONTEXT.md D4]

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
```

### docker-compose.yml pattern (existing `${VAR:-}` style)
[VERIFIED: `docker-compose.yml:37-46`]

```yaml
environment:
  - VISION_API_KEY=${VISION_API_KEY:-}
  - VISION_API_URL=${VISION_API_URL:-}
  - VISION_MODEL=${VISION_MODEL:-}
```

All ten new vars follow this exact pattern under `computer-use-server.environment`.

---

## Validation Architecture

Nyquist validation is disabled for this project. This section is a checklist of observable invariants the plan must verify — not a VALIDATION.md spec.

### Observable invariants

| # | Invariant | How to assert |
|---|-----------|---------------|
| V1 | `context_vars.current_anthropic_base_url.get()` returns `None` when no `.set()` call made | `self.assertIsNone(current_anthropic_base_url.get())` after reload |
| V2 | Path A (zero-config): `extra_env` contains no `ANTHROPIC_*` / `CLAUDE_CODE_*` keys | `self.assertNotIn("ANTHROPIC_AUTH_TOKEN", extra_env)` etc. |
| V3 | Path B (auth-only): `extra_env` contains exactly `ANTHROPIC_AUTH_TOKEN` + `ANTHROPIC_BASE_URL="https://api.anthropic.com"`, none of the ten new vars | assert both present + assert each of 10 absent |
| V4 | Path C (custom gateway): only the vars the operator actually set appear; unset vars absent | set 3 of 10, assert exactly those 3 present and other 7 absent |
| V5 | `ANTHROPIC_CUSTOM_HEADERS` injects for non-null `user_email` ContextVar | set email, call `_create_container`, assert key present with correct value |
| V6 | `sub_agent(model="sonnet")` → `model_id="claude-sonnet-4-6"`, `model_display="sonnet"` | unit test on alias resolution logic |
| V7 | `sub_agent(model="opus")` → `model_id="claude-opus-4-6"`, `model_display="opus"` | same |
| V8 | `sub_agent(model="claude-sonnet-4-6")` → passes through unchanged, `model_display="claude-sonnet-4-6"` | unit test |
| V9 | `sub_agent(model="anthropic/claude-sonnet-4-6")` → passes through unchanged | unit test |
| V10 | `sub_agent(model=None)` or `sub_agent(model="")` → falls back to `ANTHROPIC_DEFAULT_SONNET_MODEL or "claude-sonnet-4-6"` | unit test |
| V11 | When `ANTHROPIC_DEFAULT_SONNET_MODEL="azure/my-deployment"` is set, alias `"sonnet"` resolves to `"azure/my-deployment"` | set env constant, test alias resolution |

### Natural failure modes to guard against

- **Empty-string injection:** A var set to `""` on the host must NOT appear in `extra_env`. The `if value:` guard handles this, but a test should verify it explicitly (set `ANTHROPIC_MODEL=""` and assert absent from `extra_env`).
- **ContextVar truthy default regression:** After D2 fix, if someone accidentally reverts the default, the Path B test (V3) will catch it — `anthropic_base` will be `"https://api.anthropic.com/"` (with trailing slash) instead of `"https://api.anthropic.com"` (from the module constant), producing a subtle URL mismatch.
- **`sub_agent` silent fallback regression:** Before D4 fix, V8/V9 would see `model_display="sonnet"` — tests guard the fix.

---

## Test Infrastructure — Verified State

### What exists in `tests/orchestrator/`

| File | Tests | Pattern |
|------|-------|---------|
| `test_mcp_tools.py` | `bash_tool`, `view`, `str_replace`, helper functions | `IsolatedAsyncioTestCase` + `@patch` decorators; mocks at `_get_or_create_container` level |
| `test_single_user_mode.py` | `_validate_chat_id`, `_get_default_chat_warning`, `bash_tool` single-user modes | `TestCase` + `patch.dict(os.environ)` + `importlib.reload()` |
| `test_system_prompt_endpoint.py` | FastAPI endpoint contract | `FastAPI TestClient` |
| `test_view_image.py` | Pillow 12 API | `IsolatedAsyncioTestCase` |

### What does NOT exist (gaps for Phase 3)

- No test calls `_create_container` directly. **Phase 3 must add this.** Recommended: new file `tests/orchestrator/test_docker_manager.py`.
- No test for `sub_agent` model resolution. **Phase 3 must add this.** Can go in `test_mcp_tools.py` (adds a new class) or a new file — planner decides.
- No `conftest.py` in `tests/orchestrator/` — no shared fixtures. Each test file sets up its own mocks inline (the established pattern).

### No Docker daemon required
[VERIFIED: all existing tests mock `docker.from_env()` / `_get_or_create_container` — zero real Docker calls]

Tests for `_create_container` must follow the same pattern: patch `get_docker_client` or `docker.from_env` before `_create_container` can run.

### Test run command
[VERIFIED: `CLAUDE.md` + existing test docstrings]

```bash
# From repo root (python:3.13-slim environment)
python -m pytest tests/ -v

# Orchestrator tests only (faster iteration)
cd computer-use-server && python -m pytest ../tests/orchestrator/ -v
```

The `sys.path.insert` at the top of each orchestrator test file makes `computer-use-server/` importable. New tests must include the same:

```python
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'computer-use-server'))
```

---

## Doc Conventions

### Template to mirror: `docs/openwebui-filter.md`
[VERIFIED: read file]

Structure used: Purpose / Installation / Feature explanation with options / Valves reference table / Troubleshooting.

### Recommended structure for `docs/claude-code-gateway.md`
[CITED: CONTEXT.md D6 + Specifics section]

1. **Purpose** — one paragraph: three-path table (zero-config / public Anthropic / custom gateway).
2. **Path A** — stock Claude Code `/login` (set nothing; confirm what user sees).
3. **Path B** — own Anthropic API key (`ANTHROPIC_AUTH_TOKEN` only).
4. **Path C** — custom gateway (full env matrix; LiteLLM/Azure/Bedrock recipe from Claude Code docs).
5. **Verification checklist** — `docker exec <sandbox> env | grep -E '^(ANTHROPIC|CLAUDE_CODE)'`; trigger `sub_agent`; inspect.
6. **Troubleshooting** — "sub-agent asks me to /login even though I set my token" (points to bug fix + #40).

This is operator-facing, not contributor-facing. Simpler than `openwebui-filter.md` — no screenshot, no installation steps (just env vars). Cross-link from: `README.md` (Open WebUI Integration section) and `docs/INSTALL.md` (`.env` section).

SPDX header required on new file:
```
# SPDX-License-Identifier: BUSL-1.1
# Copyright (c) 2025 Open Computer Use Contributors
```

---

## `.env.example` and `docker-compose.yml` Changes

### `.env.example` (current state)
[VERIFIED: read file — lines 51-53]

Current block ends with:
```
# === Optional: Claude Code sub-agent ===
# ANTHROPIC_AUTH_TOKEN=
# ANTHROPIC_BASE_URL=https://api.anthropic.com
```

New block appended immediately after (D7 locked):
```
# === Optional: Claude Code sub-agent gateway overrides ===
# Pass-through to sandbox when set. Leave commented to use Claude Code defaults.
# ANTHROPIC_MODEL=
# ANTHROPIC_DEFAULT_SONNET_MODEL=
# ANTHROPIC_DEFAULT_OPUS_MODEL=
# ANTHROPIC_DEFAULT_HAIKU_MODEL=
# CLAUDE_CODE_SUBAGENT_MODEL=
# CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=
# DISABLE_PROMPT_CACHING=
# DISABLE_PROMPT_CACHING_SONNET=
# DISABLE_PROMPT_CACHING_OPUS=
# DISABLE_PROMPT_CACHING_HAIKU=
```

### `docker-compose.yml` (current state)
[VERIFIED: read file — `computer-use-server.environment` section ends at line 46]

Currently the `computer-use-server` environment does NOT include `ANTHROPIC_AUTH_TOKEN` or `ANTHROPIC_BASE_URL`. Both must be added along with the ten new vars (D7). All follow the `${VAR:-}` pattern:

```yaml
- ANTHROPIC_AUTH_TOKEN=${ANTHROPIC_AUTH_TOKEN:-}
- ANTHROPIC_BASE_URL=${ANTHROPIC_BASE_URL:-}
- ANTHROPIC_MODEL=${ANTHROPIC_MODEL:-}
- ANTHROPIC_DEFAULT_SONNET_MODEL=${ANTHROPIC_DEFAULT_SONNET_MODEL:-}
- ANTHROPIC_DEFAULT_OPUS_MODEL=${ANTHROPIC_DEFAULT_OPUS_MODEL:-}
- ANTHROPIC_DEFAULT_HAIKU_MODEL=${ANTHROPIC_DEFAULT_HAIKU_MODEL:-}
- CLAUDE_CODE_SUBAGENT_MODEL=${CLAUDE_CODE_SUBAGENT_MODEL:-}
- CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=${CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS:-}
- DISABLE_PROMPT_CACHING=${DISABLE_PROMPT_CACHING:-}
- DISABLE_PROMPT_CACHING_SONNET=${DISABLE_PROMPT_CACHING_SONNET:-}
- DISABLE_PROMPT_CACHING_OPUS=${DISABLE_PROMPT_CACHING_OPUS:-}
- DISABLE_PROMPT_CACHING_HAIKU=${DISABLE_PROMPT_CACHING_HAIKU:-}
```

Note: `ANTHROPIC_AUTH_TOKEN` and `ANTHROPIC_BASE_URL` are currently missing from `docker-compose.yml` despite being in `.env.example`. Adding them is required for the existing env-fallback path to work (without them, the orchestrator container never sees those vars even if the operator sets them in `.env`).

---

## Environment Availability

Step 2.6: SKIPPED. Phase 3 is code/config changes only. No new external runtime dependencies. Test suite runs in `python:3.13-slim` as per existing CI pattern; all required packages (`docker`, `fastapi`, `aiohttp`) are already in `computer-use-server/requirements.txt`.

---

## Runtime State Inventory

Step 2.5: SKIPPED. Phase 3 is not a rename/refactor/migration. No runtime state (stored data, service config, OS registration, secrets, build artifacts) is affected.

---

## Open Questions

1. **`_create_container` `environment=` kwarg format** — RESOLVED [VERIFIED: docker_manager.py:205-212, 427]
   - `_build_container_env(extra_env)` returns a dict; `containers.create(environment=<dict>)` receives it directly.
   - Test assertions: `call_args.kwargs["environment"]["ANTHROPIC_AUTH_TOKEN"] == "sk-test"`.

2. **`ANTHROPIC_AUTH_TOKEN` + `ANTHROPIC_BASE_URL` absence from `docker-compose.yml`**
   - What we know: Both are in `.env.example` but absent from `docker-compose.yml:37-46` (verified). This means the existing env-fallback path (Path B) doesn't actually work with a default `docker-compose up` — the orchestrator container never receives those env vars.
   - Recommendation: D7 adds them to `docker-compose.yml`. The plan should note this as a bug fix alongside the ContextVar fix, since both are required for Path B to work end-to-end.

---

## Assumptions Log

**None.** All claims in this research are VERIFIED from direct codebase reads. A1 (environment= kwarg format) was resolved during research — see Open Questions #1.

---

## Sources

### Primary (HIGH confidence — direct codebase reads)
- `computer-use-server/context_vars.py` — line 14, the bug location
- `computer-use-server/docker_manager.py` — lines 1-68 (module constants), 205-212 (`_build_container_env`), 344-430 (`_create_container` body + containers.create call)
- `computer-use-server/mcp_tools.py` — lines 795-820 (sub_agent), 1108-1122 (header path)
- `tests/orchestrator/test_mcp_tools.py` — IsolatedAsyncioTestCase + @patch pattern
- `tests/orchestrator/test_single_user_mode.py` — importlib.reload + patch.dict pattern
- `tests/orchestrator/test_system_prompt_endpoint.py` — FastAPI TestClient pattern
- `docker-compose.yml` — environment section, confirmed missing ANTHROPIC vars
- `.env.example` — current optional sections
- `docs/openwebui-filter.md` — doc template structure

### Secondary (MEDIUM confidence)
- `CONTEXT.md` — locked design decisions (canonical for this phase)
- `STATE.md` — binding decisions for v0.8.12.9

---

## Metadata

**Confidence breakdown:**
- Bug fix (D2): HIGH — line is right there, fix is one character change
- Env pass-through (D3): HIGH — pattern verified from VISION_API_KEY block
- sub_agent fix (D4): HIGH — current code verified, fix pattern clear
- Test infrastructure: HIGH — all four existing test files read and documented
- `docker-compose.yml` gap: HIGH — verified by reading the file
- `environment=` kwarg format: LOW (A1) — requires reading lines 405-460

**Research date:** 2026-04-12
**Valid until:** 60 days (stable domain; no external deps)
