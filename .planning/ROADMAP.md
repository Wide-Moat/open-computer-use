# Roadmap: Open Computer Use

## Milestones

- ✅ **v0.8.12.7 — System Prompt Extraction** (Phase 1, shipped 2026-04-12)
- ✅ **v0.8.12.8 — Preview Filter UX** (Phase 2, shipped 2026-04-12)
- 🚧 **v0.8.12.9 — Claude Code Gateway Compatibility** (Phase 3, planned)

## Phases

### ✅ v0.8.12.7 — System Prompt Extraction (Shipped)

**Milestone Goal:** Move the ~460-line hard-coded Computer Use system prompt out of the Open WebUI filter and into a server endpoint that does full substitution on the server (URLs from `chat_id`, dynamic `<available_skills>` from optional `user_email`, graceful fallback to default public skills when no external provider is wired). Filter becomes a thin HTTP-fetch + LRU cache + stale-cache fallback layer.

- [x] **Phase 1: System Prompt Extraction** — Port internal v3.7/v3.8 server-side substitution to community. Upgrade `GET /system-prompt`. Rewrite filter as thin HTTP client + LRU cache + stale-cache fallback. Add tests.

### ✅ v0.8.12.8 — Preview Filter UX (Shipped)

**Milestone Goal:** Expose the already-shipped `/preview/{chat_id}` SPA to users of stock Open WebUI (without frontend patches). Filter's `outlet()` learns to emit an inline iframe artifact by default and, opt-in, a markdown preview button. All v3.1.0 `outlet()` correctness invariants preserved. Every Valve (old and new) documented in one authoritative place.

- [x] **Phase 2: Preview Filter UX** — Added three new Valves to `computer_link_filter.py`, extended `outlet()` to emit preview iframe (default) and preview button (opt-in), bumped filter 3.1.0 → 3.2.0 (commit `b08d472`), documented every Valve in a `VALVES:` docstring block + `docs/openwebui-filter.md` (+ troubleshooting section in `d79f730`), proved both the feature and the existing behaviour with pytest in Docker.

### 🚧 v0.8.12.9 — Claude Code Gateway Compatibility (Planned)

**Milestone Goal:** The Claude Code sub-agent running inside each sandbox container routes its API calls to whatever Anthropic-compatible destination the operator configured (public Anthropic, LiteLLM proxy, Azure, Bedrock-via-LiteLLM, etc.), with optional model-ID and prompt-caching/beta overrides — all without ever breaking the zero-config `/login` path. Fixes issue #40; inspired by PR #41 but rewritten with tests and without the deploy-specific churn.

- [ ] **Phase 3: Claude Code Gateway Compatibility** — Fix `context_vars.py:14` default so the `ANTHROPIC_BASE_URL` env fallback actually fires in `_create_container`; pass through the ten official Claude Code env vars (`ANTHROPIC_MODEL`, `ANTHROPIC_DEFAULT_{SONNET,OPUS,HAIKU}_MODEL`, `CLAUDE_CODE_SUBAGENT_MODEL`, `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS`, `DISABLE_PROMPT_CACHING{,_SONNET,_OPUS,_HAIKU}`) only when set; teach `sub_agent` MCP tool to accept direct model IDs in addition to `sonnet`/`opus` aliases; add pytest coverage for the three operator paths (no vars → stock `/login`; auth-only → public Anthropic; auth + base URL → custom gateway); document the gateway path in `docs/`.

## Phase Details

### Phase 1: System Prompt Extraction (v0.8.12.7)

**Goal:** The system prompt lives on the server; the filter fetches, caches, and falls back gracefully — with full test coverage and no regression.
**Depends on:** Nothing (first phase)
**Requirements:** PROMPT-01, PROMPT-02, PROMPT-03, PROMPT-04, PROMPT-05, PROMPT-06, PROMPT-07
**Success Criteria:** (observable — all met, shipped 2026-04-12)
  1. `GET /system-prompt?chat_id=<id>` returns HTTP 200 `text/plain` with the full Computer Use prompt, `{file_base_url}` / `{archive_url}` / `{chat_id}` substituted. Legacy params still work; no-param call returns the template with placeholders un-substituted.
  2. `GET /system-prompt?chat_id=<id>&user_email=<email>` returns the prompt with a dynamic `<available_skills>` block. In community default config the block contains `DEFAULT_PUBLIC_SKILLS`.
  3. `computer_link_filter.py` no longer contains the multi-line prompt f-string; it fetches the prompt via HTTP. File ≤ 250 lines.
  4. Filter LRU cache keyed by `(chat_id, user_email)`, TTL 5 min, max 100 entries, O(1) eviction; stale-cache fallback on fetch failure.
  5. `pytest tests/` fully green: ≥ 5 new endpoint tests + ≥ 7 new filter cache tests + all 7 pre-existing filter tests.

**Plans:** 1 plan — `01-01-PLAN.md` (complete)

### Phase 2: Preview Filter UX (v0.8.12.8, Shipped 2026-04-12)

**Goal:** Stock Open WebUI users can see file previews directly in assistant messages, without frontend patches, while every v3.1.0 correctness invariant in the filter's `outlet()` remains intact and every Valve is discoverable without reading source.
**Depends on:** Phase 1 (needs v3.1.0 `outlet()` + Valves as baseline)
**Requirements:** PREVIEW-01, PREVIEW-02, PREVIEW-03, PREVIEW-04, VALVE-01, VALVE-02, DOCS-01, DOCS-02, DOCS-03, VERIFY-01, VERIFY-02, VERIFY-03
**Success Criteria:** (observable — all met, shipped 2026-04-12)
  1. **Default UX ships** — with the three new Valves at their defaults (`ENABLE_PREVIEW_ARTIFACT=True`, `ENABLE_PREVIEW_BUTTON=False`, `PREVIEW_BUTTON_TEXT="🖥️ Open preview"`), `outlet()` applied to an assistant message containing a file URL for the current `chat_id` appends exactly one fenced ```html block with an `<iframe src="{base}/preview/{chat_id}" …>` snippet and no markdown preview-button link. Verified in `tests/test_filter.py::PreviewArtifact`.
  2. **Button opt-in works** — with `ENABLE_PREVIEW_BUTTON=True`, the same qualifying message also gets `[🖥️ Open preview]({base}/preview/{chat_id})` appended as a markdown link. Verified in `tests/test_filter.py::PreviewButton`.
  3. **Invariants preserved** — no regression on existing `BaselineBehaviour` / `TrailingSlashNormalisation` / `EmptyChatIdHandling` / `SystemPromptFetchCache` suites. New tests cover: role guard (iframe not added to user/system/tool), string-content guard (non-string content untouched), `chat_id` scoping (other-chat file URL not decorated), no `//preview/` on trailing slash, idempotency (second `outlet()` call does not duplicate iframe or button).
  4. **Valve docs exist and match code** — `computer_link_filter.py` docstring has a `VALVES:` section listing every `Field(...)`; `docs/openwebui-filter.md` carries the same reference plus a decision guide and troubleshooting; `test_every_valve_is_documented_in_docstring` enforces no drift between the two.
  5. **Docker verification green** — `docker build --platform linux/amd64 -t open-computer-use:latest .` succeeds; `./tests/test-docker-image.sh`, `./tests/test-no-corporate.sh`, `./tests/test-project-structure.sh` pass; `python -m pytest tests/test_filter.py tests/orchestrator tests/security tests/patches -v` run inside `python:3.13-slim` all green with zero new warnings.

**Plans:** 1 plan — `02-01-PLAN.md` (complete)

### Phase 3: Claude Code Gateway Compatibility (v0.8.12.9)

**Goal:** The Claude Code sub-agent inside each sandbox container routes its API traffic to the operator-configured destination (public Anthropic, LiteLLM proxy, Azure, Bedrock-via-LiteLLM, etc.), with optional model-ID and prompt-caching/beta overrides, while the zero-config path (no env vars → Claude Code's native `/login`) still works out of the box.
**Depends on:** Nothing blocking (touches `computer-use-server/*` only; independent of Phase 2)
**Requirements:** GATEWAY-01, GATEWAY-02, GATEWAY-03, GATEWAY-04, GATEWAY-05, GATEWAY-06, GATEWAY-07, GATEWAY-08, GATEWAY-09, GATEWAY-10, GATEWAY-11, GATEWAY-12 (minted by `/gsd-plan-phase 3` — see `.planning/REQUIREMENTS.md`)
**Related:** Fixes issue #40 (https://github.com/Yambr/open-computer-use/issues/40); inspired by PR #41 (https://github.com/Yambr/open-computer-use/pull/41), reimplemented with tests and without deploy-specific churn.
**Success Criteria:** (observable — phase complete when ALL hold)
  1. **Zero-config = stock Claude Code.** Operator sets no `ANTHROPIC_*` / `CLAUDE_CODE_*` env vars on the host → `docker inspect <sandbox>` shows no such vars in `Env` → Claude Code inside shows its native `/login` prompt. No regression on existing `SINGLE_USER_MODE` / `ANTHROPIC_CUSTOM_HEADERS` behaviour.
  2. **Env fallback works.** Operator sets only `ANTHROPIC_AUTH_TOKEN=<k>` and `ANTHROPIC_BASE_URL=<url>` on the host → both land in the sandbox → Claude Code connects to `<url>` with `<k>`. Root-cause bug at `context_vars.py:14` (default `"https://api.anthropic.com/"`) is fixed so the `or ANTHROPIC_BASE_URL` fallback in `docker_manager.py:359` actually fires.
  3. **Optional gateway vars pass through when set, stay out when not.** Any subset of the ten official Claude Code env vars (`ANTHROPIC_MODEL`, `ANTHROPIC_DEFAULT_{SONNET,OPUS,HAIKU}_MODEL`, `CLAUDE_CODE_SUBAGENT_MODEL`, `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS`, `DISABLE_PROMPT_CACHING{,_SONNET,_OPUS,_HAIKU}`) lands in the sandbox iff the operator set it on the host. Empty / unset vars are never injected.
  4. **`sub_agent` accepts direct model IDs.** `sub_agent(model="sonnet")` and `sub_agent(model="opus")` keep working; `sub_agent(model="claude-sonnet-4-6")` and `sub_agent(model="anthropic/claude-sonnet-4-6")` also work. Alias resolution honours `ANTHROPIC_DEFAULT_*_MODEL` when set.
  5. **Tests green.** `pytest tests/` passes with new coverage for the three operator paths (no vars / auth-only / custom gateway), the ContextVar fallback fix, the `sub_agent` model-ID acceptance, and confirmation that `ANTHROPIC_CUSTOM_HEADERS` injection at `docker_manager.py:378` is unchanged.
  6. **Docs ship.** New `docs/claude-code-gateway.md` with the three-operator-path table, including the LiteLLM/Azure/Bedrock recipe (`ANTHROPIC_AUTH_TOKEN` + `ANTHROPIC_BASE_URL` + `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1` + `DISABLE_PROMPT_CACHING=1` per Claude Code LLM-gateway docs). `.env.example` + `docker-compose.yml` declare the new optional vars (all `${VAR:-}` style, unset → unset). `README.md` and `docs/INSTALL.md` cross-link the new doc.

**Plans:** 3 plans

Plans:
- [x] 03-01-PLAN.md — Orchestrator code changes (context_vars fix, docker_manager env constants + pass-through tuple, sub_agent alias widening, REQUIREMENTS.md GATEWAY-* minting) — Wave 1
- [x] 03-02-PLAN.md — Tests (three-path env-injection matrix, sub_agent model resolution, ANTHROPIC_CUSTOM_HEADERS regression guard) — Wave 2
- [ ] 03-03-PLAN.md — Config and docs (docker-compose.yml env wiring, .env.example gateway-overrides block, new docs/claude-code-gateway.md, README/INSTALL cross-links) — Wave 2

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. System Prompt Extraction (v0.8.12.7)      | 1/1 | ✅ Complete     | 2026-04-12 |
| 2. Preview Filter UX (v0.8.12.8)             | 1/1 | ✅ Complete     | 2026-04-12 |
| 3. Claude Code Gateway Compatibility (v0.8.12.9) | 0/3 | 🚧 Planned | — |

---
*Updated 2026-04-12 — Phase 3 broken down into 3 plans by `/gsd-plan-phase 3`.*
