# Requirements: Open Computer Use

**Defined:** 2026-04-12
**Core Value:** A single user can pull one image, wire it into Open WebUI, and get real Computer Use working end-to-end without running a corporate stack.

## v1 Requirements (current milestone — v0.8.12.9 Claude Code Gateway Compatibility)

Requirements for current milestone. Each maps to roadmap phases.

### Preview Artifact (filter outlet)

- [x] **PREVIEW-01**: Filter's `outlet()` appends an inline HTML iframe artifact pointing at `{FILE_SERVER_URL}/preview/{chat_id}` to assistant messages that contain a file URL for the current `chat_id`, when `ENABLE_PREVIEW_ARTIFACT=True` (new project default). Artifact format: fenced ```html code block wrapping `<iframe src=… style="width:100%;height:100%;border:none" allow="clipboard-write; keyboard-map"></iframe>`.
- [x] **PREVIEW-02**: Filter's `outlet()` appends a markdown link `[{PREVIEW_BUTTON_TEXT}]({FILE_SERVER_URL}/preview/{chat_id})` to the same qualifying messages when `ENABLE_PREVIEW_BUTTON=True` (default `False` — opt-in for stock Open WebUI without artifact rendering).
- [x] **PREVIEW-03**: All v3.1.0 correctness invariants remain intact: (a) only `role=="assistant"` messages are touched; (b) non-string `content` is skipped; (c) `file_url_pattern` is scoped to the current `chat_id` (no cross-chat decoration); (d) `FILE_SERVER_URL.rstrip("/")` is applied so trailing-slash configs do not produce `//preview/`.
- [x] **PREVIEW-04**: Both artifact and button are idempotent — repeated `outlet()` calls on the same message must not duplicate the iframe or the link. Substring match is the accepted strategy (same as the existing archive button).

### Valves surface

- [x] **VALVE-01**: Three new Valves exist on `Filter.Valves` with pydantic `Field(...)` definitions — `ENABLE_PREVIEW_ARTIFACT: bool = True`, `ENABLE_PREVIEW_BUTTON: bool = False`, `PREVIEW_BUTTON_TEXT: str = "🖥️ Open preview"`. Style matches existing Valves (double quotes, trailing commas, descriptions).
- [x] **VALVE-02**: Filter `version:` string in module docstring bumps from `3.1.0` → `3.2.0`; a `CHANGELOG (v3.2.0)` entry is prepended describing the new Valves and default behaviour.

### Documentation

- [x] **DOCS-01**: Module docstring of `computer_link_filter.py` carries a `VALVES:` section documenting every Valve (old and new) with name, type, default, and purpose. Covers `FILE_SERVER_URL`, `SYSTEM_PROMPT_URL`, `INJECT_SYSTEM_PROMPT`, `ENABLE_ARCHIVE_BUTTON`, `ARCHIVE_BUTTON_TEXT`, `ENABLE_PREVIEW_ARTIFACT`, `ENABLE_PREVIEW_BUTTON`, `PREVIEW_BUTTON_TEXT`.
- [x] **DOCS-02**: External reference page `docs/openwebui-filter.md` exists in the repo, written in English, with: purpose, full Valve reference, "which preview mode fits you" decision guide (artifact vs button), troubleshooting (wrong URL / server down / non-http scheme).
- [x] **DOCS-03**: `tests/test_filter.py::test_every_valve_is_documented_in_docstring` asserts every `Field(...)` on `Filter.Valves` has a matching entry in the `VALVES:` docstring block — drift guard.

### Verification

- [x] **VERIFY-01**: `pytest tests/test_filter.py -v` passes 100% (existing 18+ tests plus new `PreviewArtifact` class of 6 tests, `PreviewButton` class of 4 tests, and the DOCS-03 drift test). Tests run in a clean `python:3.13-slim` Docker container.
- [x] **VERIFY-02**: `pytest tests/orchestrator tests/security tests/patches` remains 100% green after the change — regression guard.
- [x] **VERIFY-03**: `./tests/test-docker-image.sh`, `./tests/test-no-corporate.sh`, `./tests/test-project-structure.sh` remain green after `docker build --platform linux/amd64 -t open-computer-use:latest .` — project-level health.

### Claude Code Gateway Compatibility (v0.8.12.9)

- [x] **GATEWAY-01**: Bug fix — context_vars.py:14 changes current_anthropic_base_url from ContextVar[str] with default="https://api.anthropic.com/" to ContextVar[Optional[str]] with default=None. After the change, current_anthropic_base_url.get() returns None when no per-request header was set, which restores the or ANTHROPIC_BASE_URL fallback at docker_manager.py:359. No other ContextVar in the file changes.
- [x] **GATEWAY-02**: docker_manager.py gains ten module-level constants captured at import time via os.getenv(NAME, ""): ANTHROPIC_MODEL, ANTHROPIC_DEFAULT_SONNET_MODEL, ANTHROPIC_DEFAULT_OPUS_MODEL, ANTHROPIC_DEFAULT_HAIKU_MODEL, CLAUDE_CODE_SUBAGENT_MODEL, CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS, DISABLE_PROMPT_CACHING, DISABLE_PROMPT_CACHING_SONNET, DISABLE_PROMPT_CACHING_OPUS, DISABLE_PROMPT_CACHING_HAIKU. Placement: immediately after the existing ANTHROPIC_BASE_URL line (line 61) and before the VISION_API_KEY block, organised into two sub-groups (model IDs first, compatibility flags second) each preceded by a one-line explanatory comment.
- [x] **GATEWAY-03**: docker_manager.py defines a module-level tuple CLAUDE_CODE_PASSTHROUGH_ENVS listing the ten (NAME, VALUE) pairs in the same order as GATEWAY-02. _create_container iterates the tuple and injects each pair into extra_env only when value is truthy. Injection happens immediately after the existing ANTHROPIC_AUTH_TOKEN/ANTHROPIC_BASE_URL block (line 362) and before the VISION_API_KEY block. No dict-literal inline; no changes to the existing Anthropic block; no changes to the ANTHROPIC_CUSTOM_HEADERS injection at line 378; no change to the if anthropic_key: guard.
- [x] **GATEWAY-04**: mcp_tools.py sub_agent tool resolves the model argument via a new rule set: sonnet maps to ANTHROPIC_DEFAULT_SONNET_MODEL or "claude-sonnet-4-6"; opus maps to ANTHROPIC_DEFAULT_OPUS_MODEL or "claude-opus-4-6"; haiku maps to ANTHROPIC_DEFAULT_HAIKU_MODEL or "claude-haiku-4-5"; any other non-empty string passes through unchanged with model_display equal to the requested string; empty or None falls back to ANTHROPIC_DEFAULT_SONNET_MODEL or "claude-sonnet-4-6" with model_display="sonnet". Alias match is case-insensitive after a strip(). The three new env constants are imported from docker_manager.
- [ ] **GATEWAY-05**: New test file tests/orchestrator/test_docker_manager.py covers the three operator paths (A: no vars then no ANTHROPIC_*/CLAUDE_CODE_* keys in extra_env; B: ANTHROPIC_AUTH_TOKEN only then that key plus ANTHROPIC_BASE_URL="https://api.anthropic.com" and no new gateway vars; C: all twelve vars set then exactly those twelve in extra_env). Tests patch os.environ then importlib.reload(docker_manager), mock get_docker_client, call _create_container directly, and inspect call_args.kwargs["environment"]. Tests run inside python:3.13-slim with no Docker daemon.
- [ ] **GATEWAY-06**: New test class TestSubAgentModelResolution lives in tests/orchestrator/test_sub_agent_model_resolution.py. It covers seven sub_agent cases: alias sonnet default, alias opus default, alias haiku default, direct ID claude-sonnet-4-6, LiteLLM-style anthropic/claude-sonnet-4-6, empty/None fallback, alias sonnet with ANTHROPIC_DEFAULT_SONNET_MODEL="azure/my-deployment" resolving to azure/my-deployment. Uses IsolatedAsyncioTestCase, patches os.environ + importlib.reload(docker_manager), patches _get_or_create_container and _ensure_gitlab_token, and asserts on the resolved model_id captured from the claude CLI invocation.
- [ ] **GATEWAY-07**: Regression test in test_docker_manager.py sets current_user_email ContextVar to alice@example.com, calls _create_container, and asserts extra_env["ANTHROPIC_CUSTOM_HEADERS"] == "x-openwebui-user-email: alice@example.com". Proves the line-378 injection still works and was not accidentally broken by the new pass-through loop.
- [ ] **GATEWAY-08**: docker-compose.yml computer-use-server.environment section declares, under the existing ${VAR:-} pattern and after the existing VISION_* block: ANTHROPIC_AUTH_TOKEN, ANTHROPIC_BASE_URL, and all ten gateway vars. Adding ANTHROPIC_AUTH_TOKEN and ANTHROPIC_BASE_URL is itself a bug fix — they were missing, so the existing Path B flow never worked end-to-end with a vanilla docker compose up.
- [ ] **GATEWAY-09**: .env.example grows a new section header "# === Optional: Claude Code sub-agent gateway overrides ===" followed by "# Pass-through to sandbox when set. Leave commented to use Claude Code defaults." and then ten "# VAR_NAME=" lines in the same order as GATEWAY-02. Placement: immediately after the existing "# === Optional: Claude Code sub-agent ===" block (lines 51-53).
- [ ] **GATEWAY-10**: New file docs/claude-code-gateway.md (SPDX header BUSL-1.1 + copyright line; English-only) with: a three-path purpose table, operator recipe for Path A (zero-config), Path B (ANTHROPIC_AUTH_TOKEN + ANTHROPIC_BASE_URL), Path C (full env matrix with a worked LiteLLM example including CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1 + DISABLE_PROMPT_CACHING=1, and an Azure/Bedrock-via-LiteLLM cross-reference), a verification checklist using docker exec <sandbox> env | grep -E '^(ANTHROPIC|CLAUDE_CODE)', and a troubleshooting entry that points at issue #40 and the context_vars.py fix. Worked examples MUST use placeholder sk-EXAMPLE... strings; no real-looking API keys.
- [ ] **GATEWAY-11**: README.md "## Open WebUI Integration" section AND docs/INSTALL.md .env configuration table both grow a one-sentence cross-link pointing to docs/claude-code-gateway.md for operators who want to route Claude Code through a gateway. No other README / INSTALL edits.
- [ ] **GATEWAY-12**: python -m pytest tests/ -v passes fully green inside python:3.13-slim with zero new warnings. grep -rn "ANTHROPIC_API_KEY" computer-use-server/ reports zero new matches compared to the pre-phase baseline (we standardise on ANTHROPIC_AUTH_TOKEN). ./tests/test-docker-image.sh, ./tests/test-no-corporate.sh, ./tests/test-project-structure.sh remain green after docker build --platform linux/amd64 -t open-computer-use:latest ..

### Open WebUI 0.9 Compatibility — Upstream Intake (v0.9.1.0)

- [x] **OWUI-INTAKE-01**: Upstream `open-webui/open-webui@v0.9.1` source is checked out at `~/src/open-webui-upstream/` (OUTSIDE this repo). `git -C ~/src/open-webui-upstream show v0.9.1:package.json` reports `"version": "0.9.1"`. `git -C ~/src/open-webui-upstream show v0.8.12:package.json` reports `"version": "0.8.12"`. Both tags are reachable in `git tag --list`.
- [x] **OWUI-INTAKE-02**: `.planning/phases/04-owui-intake/04-INVENTORY.md` exists and, for each of the 8 patches in `openwebui/patches/`, carries a section with: (a) upstream file path(s) the patch targets, (b) a `v0.8.12` source excerpt at the anchor, (c) a matching `v0.9.1` source excerpt OR a "NOT FOUND" note with a reproducible grep command as evidence, (d) a 1-sentence rewrite strategy (rewrite regex / rewrite entirely / drop as obsolete).
- [x] **OWUI-INTAKE-03**: For each of the 4 currently-commented-out patches (`fix_large_tool_args`, `fix_attached_files_position`, `fix_skip_embedding_chat_files`, `fix_skip_rag_files_native_fc`), the inventory explicitly classifies the patch as still-valuable-at-0.9.1 (rewrite) or obsolete-at-0.9.1 (drop + document). Classification is based on the research's obsolescence criteria: anchor existence AND whether the underlying pain point still applies at v0.9.1.

### Open WebUI 0.9 Compatibility — Frontend Patches (v0.9.1.0)

- [x] **OWUI-FE-01**: `openwebui/patches/fix_artifacts_auto_show.py` applied to a freshly-built `ghcr.io/open-webui/open-webui:0.9.1` image succeeds (exit 0, `PATCHED!` line in build log, non-zero diff in target chunk), and live UI verification shows the Artifacts panel auto-opens when an assistant message contains an HTML code block.
- [x] **OWUI-FE-02**: `openwebui/patches/fix_preview_url_detection.py` applied to the same image succeeds, and live UI verification shows the preview iframe renders inline when a message contains a `{base}/preview/{chat_id}` or `{base}/files/{chat_id}/...` URL.
- [x] **OWUI-FE-03**: Both patches are idempotent (re-running on an already-patched chunk prints `ALREADY PATCHED` and exits 0) AND fail loudly (`sys.exit(1)` with explicit `ERROR:` message on stderr) if the anchor regex does not match — verified by mutating the target chunk and re-running.

### Open WebUI 0.9 Compatibility — Backend Patches (v0.9.1.0)

- [x] **OWUI-BE-01**: fix_tool_loop_errors.py applied cleanly to a v0.9.1 middleware.py — pytest green for fresh/idempotent/anchor-miss states; exit 1 + stderr ERROR on any sub-anchor miss; Dockerfile line 13 active.
- [x] **OWUI-BE-02**: fix_large_tool_results.py applied after Patch 3 — pytest green; cascade verified against patched Patch 3 fixture; Dockerfile line 23 active.
- [x] **OWUI-BE-03**: fix_large_tool_args.py applied with OLD_ARGS match count == 2 assertion; pytest green; Dockerfile line 29 uncommented.
- [x] **OWUI-BE-04**: fix_attached_files_position.py applied — inner block byte-match at v0.9.1; pytest green; Dockerfile line 33 uncommented.
- [x] **OWUI-BE-05**: fix_skip_embedding_chat_files.py applied — both retrieval.py anchors hard-fail on miss; pytest green; Dockerfile line 37 uncommented.
- [x] **OWUI-BE-06**: fix_skip_rag_files_native_fc.py applied — pytest green; Dockerfile line 41 uncommented; marker name mismatch (file name vs PATCH_MARKER) documented in verdict, not renamed.

## Shipped Requirements (previous milestones)

### v0.8.12.7 System Prompt Extraction (shipped 2026-04-12)

- [x] **PROMPT-01**: Server exposes `GET /system-prompt` returning the Computer Use prompt as `text/plain`. Accepts optional query params `chat_id`, `user_email`, and legacy `file_base_url` / `archive_url`. When `chat_id` is given, the server substitutes `{file_base_url}` = `{FILE_SERVER_URL}/files/{chat_id}`, `{archive_url}` = `{file_base_url}/archive`, and `{chat_id}` directly. Legacy `file_base_url` param takes precedence for deprecated callers. When no `chat_id` / legacy params are supplied, placeholders come back un-substituted (degraded path for diagnostic use). Endpoint reuses `computer-use-server/system_prompt.py::SYSTEM_PROMPT_TEMPLATE` and `build_system_prompt()` — no new prompt text.
- [x] **PROMPT-02**: When `user_email` is supplied, the server asks its skill manager for per-user skills and bakes a dynamic `<available_skills>` XML block into the returned prompt. In community there is no external skill provider by default — server detects absence (e.g. `MCP_TOKENS_URL` / `MCP_TOKENS_API_KEY` env empty or provider unreachable) and returns `DEFAULT_PUBLIC_SKILLS`. Behaviour is indistinguishable from the `user_email`-less path for out-of-the-box community users, but the plumbing is ready for operators who wire their own provider.
- [x] **PROMPT-03**: The Open WebUI filter (`computer_link_filter.py`) no longer hard-codes the prompt — it HTTP-fetches from the server endpoint passing `chat_id` + `user_email`, and injects the response body as-is (no client-side substitution). File size target: ≤ 250 lines (down from ~630).
- [x] **PROMPT-04**: Filter caches responses in an `OrderedDict` LRU keyed by `(chat_id, user_email)` with TTL 5 minutes and max 100 entries, O(1) eviction. Cache hits within TTL skip the HTTP round-trip. Keying by user identity too prevents one user's baked `<available_skills>` from leaking to another user on the same `chat_id`.
- [x] **PROMPT-05**: On fetch failure (connection refused, timeout, non-200, URLError), the filter serves the stale-cache entry for the same `chat_id` if one exists (ignoring TTL) and logs a warning. If the cache is cold for this `chat_id`, the filter skips system-prompt injection — same no-op path as the existing missing-`chat_id` case. No broken URLs ever reach the model.
- [x] **PROMPT-06**: The 7 pre-existing `tests/test_filter.py` cases keep passing after the refactor. The two tests that reach the injection path get a `setUp` that mocks `urllib.request.urlopen` to return a synthetic template; the other five use paths that early-return before the fetch and stay unchanged.
- [x] **PROMPT-07**: New pytest coverage — ≥ 12 tests total across two files:
  - `tests/orchestrator/test_system_prompt_endpoint.py` ≥ 5 tests: `chat_id` substitution (URL + archive + chat_id), `user_email` falls back to defaults when no provider (content-check), legacy `file_base_url` / `archive_url` params substitute correctly, no-params path returns un-substituted placeholders, content-type `text/plain`.
  - `tests/test_filter.py::SystemPromptFetchCache` ≥ 7 tests: fresh fetch populates cache, cache hit within TTL skips HTTP, TTL expiry triggers refetch, LRU eviction at 100 entries, stale-cache fallback on server down, cold-cache skip when server down, `user_email` propagation to server call.

## v2 Requirements

Deferred. Not in current roadmap.

### Filter Parity

- **FILTER-01**: Browser-keyword detection restricted to `tool_calls` and `role=tool` messages (an internal-fork v3.8 bug-fix for preview injection — guarded against future preview-injection work).
- **FILTER-02**: Preview-link injection for last assistant message when browser/sub-agent tools were used (additive on top of v0.8.12.8 iframe artifact).

### Skill Pipeline

- **SKILL-01**: Default external skill provider shipped with the image (container running `mcp-settings-wrapper` or similar) so per-user skills work out of the box without operator config. v1 ships the hooks only.

### Claude Code compatibility (deferred from community PR #41)

- **CLAUDE-CODE-01**: Claude Code compatibility env pass-through (`ANTHROPIC_MODEL`, `ANTHROPIC_DEFAULT_SONNET_MODEL`, `ANTHROPIC_DEFAULT_OPUS_MODEL`, `ANTHROPIC_DEFAULT_HAIKU_MODEL`, `CLAUDE_CODE_SUBAGENT_MODEL`, `DISABLE_PROMPT_CACHING`, `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS`) in `docker_manager.py` + `.env.example` + `docker-compose.yml`, with the syntax error flagged by CodeRabbit on the upstream PR fixed, and `context_vars.current_anthropic_base_url` default change audited for breakage.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Frontend patches to Open WebUI core | We do not fork upstream; the filter is the only integration surface |
| New server endpoints (second preview endpoint, etc.) | `/preview/{chat_id}` already exists and is sufficient |
| Git tag / release automation | User controls release cadence manually (memory: no-tag-without-ask) |
| Forward-port of internal filter chain 3.3–3.7 in full | Tied to internal architecture with no community value |
| Russian-language skill triggers / i18n | Community is English-only per `CLAUDE.md` |
| Corporate CA certificates | Not distributed in open-source image |
| NTLM/Kerberos browser auth overlay | Corporate-specific |
| Shipping a default external skill provider in the community image | Per-user skills require an API that community doesn't provide; server falls back to `DEFAULT_PUBLIC_SKILLS` gracefully when provider URL is empty |

## Traceability

Filled by the roadmap step — see ROADMAP.md once phases are defined.

| Requirement | Phase | Status |
|-------------|-------|--------|
| PROMPT-01 | Phase 1 — System Prompt Extraction (v0.8.12.7) | Complete |
| PROMPT-02 | Phase 1 — System Prompt Extraction (v0.8.12.7) | Complete |
| PROMPT-03 | Phase 1 — System Prompt Extraction (v0.8.12.7) | Complete |
| PROMPT-04 | Phase 1 — System Prompt Extraction (v0.8.12.7) | Complete |
| PROMPT-05 | Phase 1 — System Prompt Extraction (v0.8.12.7) | Complete |
| PROMPT-06 | Phase 1 — System Prompt Extraction (v0.8.12.7) | Complete |
| PROMPT-07 | Phase 1 — System Prompt Extraction (v0.8.12.7) | Complete |
| PREVIEW-01 | Phase 2 — Preview Filter UX (v0.8.12.8) | Complete |
| PREVIEW-02 | Phase 2 — Preview Filter UX (v0.8.12.8) | Complete |
| PREVIEW-03 | Phase 2 — Preview Filter UX (v0.8.12.8) | Complete |
| PREVIEW-04 | Phase 2 — Preview Filter UX (v0.8.12.8) | Complete |
| VALVE-01 | Phase 2 — Preview Filter UX (v0.8.12.8) | Complete |
| VALVE-02 | Phase 2 — Preview Filter UX (v0.8.12.8) | Complete |
| DOCS-01 | Phase 2 — Preview Filter UX (v0.8.12.8) | Complete |
| DOCS-02 | Phase 2 — Preview Filter UX (v0.8.12.8) | Complete |
| DOCS-03 | Phase 2 — Preview Filter UX (v0.8.12.8) | Complete |
| VERIFY-01 | Phase 2 — Preview Filter UX (v0.8.12.8) | Complete |
| VERIFY-02 | Phase 2 — Preview Filter UX (v0.8.12.8) | Complete |
| VERIFY-03 | Phase 2 — Preview Filter UX (v0.8.12.8) | Complete |
| GATEWAY-01 | Phase 3 — Claude Code Gateway Compatibility (v0.8.12.9) | Complete |
| GATEWAY-02 | Phase 3 — Claude Code Gateway Compatibility (v0.8.12.9) | Complete |
| GATEWAY-03 | Phase 3 — Claude Code Gateway Compatibility (v0.8.12.9) | Complete |
| GATEWAY-04 | Phase 3 — Claude Code Gateway Compatibility (v0.8.12.9) | Complete |
| GATEWAY-05 | Phase 3 — Claude Code Gateway Compatibility (v0.8.12.9) | Pending |
| GATEWAY-06 | Phase 3 — Claude Code Gateway Compatibility (v0.8.12.9) | Pending |
| GATEWAY-07 | Phase 3 — Claude Code Gateway Compatibility (v0.8.12.9) | Pending |
| GATEWAY-08 | Phase 3 — Claude Code Gateway Compatibility (v0.8.12.9) | Pending |
| GATEWAY-09 | Phase 3 — Claude Code Gateway Compatibility (v0.8.12.9) | Pending |
| GATEWAY-10 | Phase 3 — Claude Code Gateway Compatibility (v0.8.12.9) | Pending |
| GATEWAY-11 | Phase 3 — Claude Code Gateway Compatibility (v0.8.12.9) | Pending |
| GATEWAY-12 | Phase 3 — Claude Code Gateway Compatibility (v0.8.12.9) | Pending |
| OWUI-INTAKE-01 | Phase 4 — Upstream intake and patch inventory (v0.9.1.0) | Complete |
| OWUI-INTAKE-02 | Phase 4 — Upstream intake and patch inventory (v0.9.1.0) | Complete |
| OWUI-INTAKE-03 | Phase 4 — Upstream intake and patch inventory (v0.9.1.0) | Complete |
| OWUI-FE-01 | Phase 5 — Rewrite frontend patches against v0.9.1 (v0.9.1.0) | In progress |
| OWUI-FE-02 | Phase 5 — Rewrite frontend patches against v0.9.1 (v0.9.1.0) | In progress |
| OWUI-FE-03 | Phase 5 — Rewrite frontend patches against v0.9.1 (v0.9.1.0) | In progress |
| OWUI-BE-01 | Phase 6 — Rewrite backend patches against v0.9.1 (v0.9.1.0) | Complete |
| OWUI-BE-02 | Phase 6 — Rewrite backend patches against v0.9.1 (v0.9.1.0) | Complete |
| OWUI-BE-03 | Phase 6 — Rewrite backend patches against v0.9.1 (v0.9.1.0) | Complete |
| OWUI-BE-04 | Phase 6 — Rewrite backend patches against v0.9.1 (v0.9.1.0) | Complete |
| OWUI-BE-05 | Phase 6 — Rewrite backend patches against v0.9.1 (v0.9.1.0) | Complete |
| OWUI-BE-06 | Phase 6 — Rewrite backend patches against v0.9.1 (v0.9.1.0) | Complete |

**Coverage:**
- v0.8.12.7 requirements: 7 / 7 mapped ✓
- v0.8.12.8 requirements: 12 / 12 mapped ✓
- v0.8.12.9 requirements: 12 / 12 mapped
- v0.9.1.0 Phase 4 requirements: 3 / 3 mapped ✓
- v0.9.1.0 Phase 5 requirements: 3 / 3 mapped ✓
- v0.9.1.0 Phase 6 requirements: 6 / 6 mapped ✓

---
*Requirements defined: 2026-04-12*
*Last updated: 2026-04-24 — OWUI-BE-01..06 minted for Phase 6 (milestone v0.9.1.0)*
