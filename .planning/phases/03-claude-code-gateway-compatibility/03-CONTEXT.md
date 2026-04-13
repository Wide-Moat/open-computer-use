# Phase 03: Claude Code Gateway Compatibility — Context

**Gathered:** 2026-04-12
**Status:** Ready for planning
**Source:** Interactive discussion (not `/gsd-discuss-phase`; captured directly from chat before `/gsd-plan-phase 3`)

<domain>
## Phase Boundary

**What this phase delivers:**

1. **Root-cause bug fix** in `computer-use-server/context_vars.py:14` — the `current_anthropic_base_url` ContextVar default is a truthy string `"https://api.anthropic.com/"`, which makes `current_anthropic_base_url.get() or ANTHROPIC_BASE_URL` in `docker_manager.py:359` always short-circuit on the first operand, so the env-var fallback never fires. Change default to `""` (or `None`) so the `or` falls through as designed.

2. **Optional pass-through** of the ten official Claude Code env vars from the orchestrator host environment into every sandbox container, **only when set** on the host:
   - Model selection: `ANTHROPIC_MODEL`, `ANTHROPIC_DEFAULT_SONNET_MODEL`, `ANTHROPIC_DEFAULT_OPUS_MODEL`, `ANTHROPIC_DEFAULT_HAIKU_MODEL`, `CLAUDE_CODE_SUBAGENT_MODEL`
   - Gateway compatibility flags: `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS`, `DISABLE_PROMPT_CACHING`, `DISABLE_PROMPT_CACHING_SONNET`, `DISABLE_PROMPT_CACHING_OPUS`, `DISABLE_PROMPT_CACHING_HAIKU`

3. **`sub_agent` MCP tool** (currently in `computer-use-server/mcp_tools.py:799-815`) learns to accept arbitrary model IDs in addition to the two existing aliases `sonnet`/`opus`. Alias resolution honours `ANTHROPIC_DEFAULT_*_MODEL` when the operator set them (so `sub_agent(model="sonnet")` routes to operator's LiteLLM-scoped Sonnet ID, e.g. `azure/claude-sonnet-4-6`, not the hardcoded `claude-sonnet-4-6`).

4. **Tests, docs, and `.env.example` / `docker-compose.yml` wiring** for all of the above.

**What this phase does NOT deliver (explicit out-of-scope):**

- Changes to the `x-anthropic-*` HTTP header path in `computer-use-server/mcp_tools.py:1113-1122`. It is dead code today (no Open WebUI-side caller sets those headers), but harmless. Keeping it leaves a per-request override path available to any future consumer and minimises blast radius.
- Traefik labels or other deploy-specific config from PR #41.
- Per-user Valve-based override through the Open WebUI filter (`computer_link_filter.py`). If desired later, that is a follow-up phase.
- `ANTHROPIC_API_KEY` handling — we standardise on `ANTHROPIC_AUTH_TOKEN` per existing code; Claude Code treats them as interchangeable, so adding a second code path is pure bloat.
- `ANTHROPIC_SMALL_FAST_MODEL` — deprecated per Claude Code docs in favour of `ANTHROPIC_DEFAULT_HAIKU_MODEL`. We skip the deprecated name.
- Milestone bump / version tag. Shipping version (`v0.8.12.9`) is applied at release time by the user.

</domain>

<decisions>
## Implementation Decisions (locked before planning)

### D1. The zero-config invariant (hard)

**Locked:** If the operator sets **no** `ANTHROPIC_*` or `CLAUDE_CODE_*` env vars on the host, the orchestrator injects **zero** such env vars into the sandbox container. Claude Code inside the sandbox starts with no `ANTHROPIC_BASE_URL` and no `ANTHROPIC_AUTH_TOKEN`, and triggers its native `/login` OAuth flow. No change to the existing `if anthropic_key:` guard at `docker_manager.py:360`.

**Why locked:** Internal production setup at this project uses a LiteLLM proxy with two env vars on the host (`ANTHROPIC_AUTH_TOKEN` + `ANTHROPIC_BASE_URL`). Community users want the vanilla `/login` flow when they don't set anything. Both paths shipped before this phase; this phase must not regress either. Any "inject defaults for convenience" suggestion is rejected.

### D2. The bug fix is one line

**Locked:** `computer-use-server/context_vars.py:14` changes from

```python
current_anthropic_base_url: ContextVar[str] = ContextVar(
    "current_anthropic_base_url", default="https://api.anthropic.com/"
)
```

to

```python
current_anthropic_base_url: ContextVar[Optional[str]] = ContextVar(
    "current_anthropic_base_url", default=None
)
```

…matching the type of `current_anthropic_auth_token` on line 13 (which is already `Optional[str], default=None` and works correctly). Type annotation updated to `Optional[str]`.

**Why locked:** This single symmetry restores the intended fallback logic at `docker_manager.py:359`. No broader refactor is justified. Audit of the other ContextVars (`current_gitlab_host`, default `"gitlab.com"`; `current_chat_id`, default `"default"`; etc.) shows they are either *intended* to have a default or fall into the same consumer-side `or` pattern — but no reports exist and they are out of scope for this phase.

### D3. All ten new env vars pass through via the same pattern

**Locked:** In `docker_manager.py`, after the existing `ANTHROPIC_AUTH_TOKEN` block (around line 360), iterate over a fixed list of ten env vars; for each, read `os.getenv(NAME, "")` at module load time into a module constant, and in `_create_container` inject into `extra_env` only when the constant is truthy. Mirror pattern of existing `VISION_API_KEY` block at line 365-368.

Module constants at the top of `docker_manager.py` (one block below the existing Anthropic block):

```python
# Claude Code model ID overrides (pass through only when set on host)
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "")
ANTHROPIC_DEFAULT_SONNET_MODEL = os.getenv("ANTHROPIC_DEFAULT_SONNET_MODEL", "")
ANTHROPIC_DEFAULT_OPUS_MODEL = os.getenv("ANTHROPIC_DEFAULT_OPUS_MODEL", "")
ANTHROPIC_DEFAULT_HAIKU_MODEL = os.getenv("ANTHROPIC_DEFAULT_HAIKU_MODEL", "")
CLAUDE_CODE_SUBAGENT_MODEL = os.getenv("CLAUDE_CODE_SUBAGENT_MODEL", "")
# Claude Code gateway compatibility flags (set to "1" to disable)
CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS = os.getenv("CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS", "")
DISABLE_PROMPT_CACHING = os.getenv("DISABLE_PROMPT_CACHING", "")
DISABLE_PROMPT_CACHING_SONNET = os.getenv("DISABLE_PROMPT_CACHING_SONNET", "")
DISABLE_PROMPT_CACHING_OPUS = os.getenv("DISABLE_PROMPT_CACHING_OPUS", "")
DISABLE_PROMPT_CACHING_HAIKU = os.getenv("DISABLE_PROMPT_CACHING_HAIKU", "")
```

Pass-through in `_create_container`:

```python
CLAUDE_CODE_PASSTHROUGH_ENVS = (
    ("ANTHROPIC_MODEL", ANTHROPIC_MODEL),
    ("ANTHROPIC_DEFAULT_SONNET_MODEL", ANTHROPIC_DEFAULT_SONNET_MODEL),
    ("ANTHROPIC_DEFAULT_OPUS_MODEL", ANTHROPIC_DEFAULT_OPUS_MODEL),
    ("ANTHROPIC_DEFAULT_HAIKU_MODEL", ANTHROPIC_DEFAULT_HAIKU_MODEL),
    ("CLAUDE_CODE_SUBAGENT_MODEL", CLAUDE_CODE_SUBAGENT_MODEL),
    ("CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS", CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS),
    ("DISABLE_PROMPT_CACHING", DISABLE_PROMPT_CACHING),
    ("DISABLE_PROMPT_CACHING_SONNET", DISABLE_PROMPT_CACHING_SONNET),
    ("DISABLE_PROMPT_CACHING_OPUS", DISABLE_PROMPT_CACHING_OPUS),
    ("DISABLE_PROMPT_CACHING_HAIKU", DISABLE_PROMPT_CACHING_HAIKU),
)
for name, value in CLAUDE_CODE_PASSTHROUGH_ENVS:
    if value:
        extra_env[name] = value
```

Tuple (not dict) to fix iteration order in tests.

**Why locked:** Matches existing style (module constants + `if value:` guard), trivially testable, every injection line is greppable, no magic. PR #41 used a dict-literal inline in the function body; we prefer named module constants for observability and deterministic test ordering.

### D4. `sub_agent` accepts both aliases and direct model IDs

**Locked:** `sub_agent` in `mcp_tools.py:799-815` keeps the existing alias map (`sonnet` → `claude-sonnet-4-6`, `opus` → `claude-opus-4-6`) as the **fallback** for empty input. When operator has set `ANTHROPIC_DEFAULT_*_MODEL` env vars, aliases route to those values instead. A direct model ID (anything not matching the alias set) is passed through unchanged so LiteLLM-style IDs like `anthropic/claude-sonnet-4-6` or `azure/my-deployment` work.

Implementation sketch (final wording decided during planning):

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

**Why locked:** Backwards compatible (existing `sub_agent(model="sonnet")` keeps working); adds `haiku` alias because the passthrough env covers it; direct IDs work for gateway users; single fallback when nothing is supplied.

### D5. Test matrix covers three operator paths

**Locked:** New pytest coverage verifies:

| Path | Operator sets | `_create_container` → `extra_env` |
|------|----------------|-----------------------------------|
| A (zero-config) | nothing | no `ANTHROPIC_*` / `CLAUDE_CODE_*` keys |
| B (public Anthropic) | `ANTHROPIC_AUTH_TOKEN` only | `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL=https://api.anthropic.com` — nothing else |
| C (custom gateway) | `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, plus any subset of the ten new vars | exactly what was set, nothing more |

Plus:
- Unit test on the ContextVar fallback (mirrors issue #40 repro path).
- Unit test on `sub_agent` alias + direct-ID resolution (4 cases: `sonnet`, `opus`, raw `claude-...`, LiteLLM-style `anthropic/claude-...`).
- Confirmation test that `ANTHROPIC_CUSTOM_HEADERS` injection at `docker_manager.py:378` still fires for the per-user email header (regression guard).

Tests live under `tests/orchestrator/` (existing directory, per `.planning/phases/02-preview-filter-ux/02-VERIFICATION.md`). Use `pytest` markers consistent with existing tests.

**Why locked:** Covers every operator-facing path; ensures no regression on the two paths that already work; the one new code path (custom gateway) gets first-class coverage.

### D6. Docs live in a dedicated doc

**Locked:** New file `docs/claude-code-gateway.md` with the three-operator-path table, a worked LiteLLM example (`ANTHROPIC_AUTH_TOKEN` + `ANTHROPIC_BASE_URL` + `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1` + `DISABLE_PROMPT_CACHING=1`), a worked Azure/Bedrock-via-LiteLLM example, and a "verify it works" checklist. Cross-link from `README.md` Open-WebUI-Integration section and from `docs/INSTALL.md` `.env` section.

**Why locked:** This is a gateway/ops concern, not an install concern — deserves its own page. `docs/INSTALL.md` becomes a cross-link hub; we avoid bloating it. Same pattern as `docs/openwebui-filter.md`.

### D7. `.env.example` + `docker-compose.yml` list all ten vars, all commented/passthrough

**Locked:** `.env.example` adds a commented block after the existing `# === Optional: Claude Code sub-agent ===` section with one `# VAR_NAME=` line per variable plus a one-line comment above the group explaining "pass-through to sandbox when set." `docker-compose.yml` adds `${VAR:-}` declarations for all ten under the `computer-use-server` `environment:` section, so the orchestrator actually sees what the operator set on the host.

**Why locked:** Discoverable; operators can grep `.env.example` for `CLAUDE_CODE_` and find everything; default-unset means zero surprise for the stock-path user.

### Claude's Discretion (planner decides)

- Exact ordering of tasks within the plan (bug fix first vs. feature first).
- Test file layout (one file per concern vs. consolidated `test_docker_manager.py`).
- Docstring/comment wording in the final code — should be minimal per project CLAUDE.md.
- Whether to use `pytest.mark.parametrize` for the three-path matrix or write three discrete tests.
- Exact wording of `docs/claude-code-gateway.md` (can defer to documentation-writing agent if one runs).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Code under modification

- `computer-use-server/context_vars.py` — module with the one-line bug (line 14).
- `computer-use-server/docker_manager.py` — sandbox container creation; specifically lines 56-68 (env-var module constants), line 358-362 (existing Anthropic pass-through with the env fallback), line 378 (`ANTHROPIC_CUSTOM_HEADERS` injection — must not be touched).
- `computer-use-server/mcp_tools.py` — specifically lines 799-820 (`sub_agent` tool body with alias map) and lines 1113-1122 (`x-anthropic-*` header path, **out of scope**).

### Existing tests to mirror

- `tests/orchestrator/` — all new tests live here; follow existing fixtures and patterns.
- `tests/test_filter.py` — reference for pytest style used in this project.

### External references (verified 2026-04-12)

- Claude Code environment variables — https://code.claude.com/docs/en/env-vars — canonical list of all ten target vars, confirms they are all first-party.
- Claude Code LLM gateway guide — https://code.claude.com/docs/en/llm-gateway — documents the recommended LiteLLM/Bedrock/Vertex recipe (`ANTHROPIC_BASE_URL` + `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1` + `DISABLE_PROMPT_CACHING=1`).
- Claude Code model config — https://code.claude.com/docs/en/model-config — documents `ANTHROPIC_MODEL`, `ANTHROPIC_DEFAULT_*_MODEL`, `CLAUDE_CODE_SUBAGENT_MODEL`, and `ANTHROPIC_CUSTOM_HEADERS` format (`Name: Value`, colon-separated, comma-separated for multi-header).
- Managing API key env vars in Claude Code — https://support.claude.com/en/articles/12304248-managing-api-key-environment-variables-in-claude-code — confirms `ANTHROPIC_AUTH_TOKEN` vs `ANTHROPIC_API_KEY` interchangeability.

### Signals the planning must respect

- **Issue #40** — https://github.com/Yambr/open-computer-use/issues/40 — the reproduction of the root-cause bug. Author is `rahxam`. Phase closes this issue.
- **PR #41** — https://github.com/Yambr/open-computer-use/pull/41 — community attempt by the same author. Signal is correct, patch is not merge-ready (syntax error in `DISABLE_PROMPT_CACHING_SONNET`, Traefik deploy labels mixed in, ~690 lines deleted from a stale rebase, no tests). Use as **inspiration and cross-check**, not as the patch to merge. Credit the author in the final PR body; close #41 with a pointer to the new PR.
- **`.planning/STATE.md`** — Accumulated Context → Decisions section has two v0.8.12.9 entries that must be respected: "hard zero-config invariant" and "do NOT mechanically merge PR #41."
- **`CLAUDE.md`** (project root) — English-only policy, SPDX headers, Docker build flags, versioning rules. All new code and docs in this phase follow these.

</canonical_refs>

<specifics>
## Specific Ideas

- The `.env.example` changes should live in a block titled like:
  ```
  # === Optional: Claude Code sub-agent gateway overrides ===
  # Pass-through to sandbox when set. Leave commented to use Claude Code defaults.
  ```
- The `docker-compose.yml` additions go under `services.computer-use-server.environment:` and should preserve the existing `${VAR:-}` pattern.
- A plausible shape for `docs/claude-code-gateway.md` (planner can rework):
  1. Intro paragraph — three paths table.
  2. Path A: "I want the stock Claude Code `/login` experience" (set nothing).
  3. Path B: "I have my own Anthropic API key" (set `ANTHROPIC_AUTH_TOKEN`).
  4. Path C: "I want to route through a LiteLLM / Azure / Bedrock gateway" (full env matrix, Claude Code LLM-gateway docs cross-link).
  5. Verification checklist (`docker exec <sandbox> env | grep -E '^(ANTHROPIC|CLAUDE_CODE)' `; trigger a `sub_agent` call; inspect endpoint headers).
  6. Troubleshooting: "sub-agent asks me to /login even though I set my token" → check step 2 in the bug fix, mention #40.

</specifics>

<deferred>
## Deferred Ideas

- **Per-user gateway override via Open WebUI Valves.** Could let each operator's user pick their own `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_BASE_URL` through the filter Valves UI. Interesting, but requires cross-cutting work in the filter + tool + orchestrator and breaks the "server owns the API key" model. Defer to a follow-up phase only if the community asks.
- **Audit other ContextVars with truthy defaults.** `current_gitlab_host="gitlab.com"` and `current_chat_id="default"` follow the same pattern but no bug reports. Defer until someone reports.
- **Claude Code `/login` via orchestrator.** If a community user wants the OAuth `/login` flow but lacks a browser inside the container, we might eventually auto-forward `claude login` output. Too speculative for now; defer.
- **Token rotation / per-chat API keys.** A secure multi-tenant deployment would want per-chat short-lived tokens. Orthogonal to gateway routing. Defer.

</deferred>

---

*Phase: 03-claude-code-gateway-compatibility*
*Context gathered: 2026-04-12 via direct in-chat discussion before `/gsd-plan-phase 3`*
