# Roadmap: Open Computer Use

## Milestones

- ✅ **v0.8.12.7 — System Prompt Extraction** (Phase 1, shipped 2026-04-12)
- ✅ **v0.8.12.8 — Preview Filter UX** (Phase 2, shipped 2026-04-12; v4.1.0 follow-up 2026-04-19)
- ✅ **v0.8.12.9 — Claude Code Gateway Compatibility** (Phase 3, code shipped 2026-04-12; rolled into v0.9.1.0 release)
- 🚧 **v0.9.1.0 — Open WebUI 0.9 Compatibility** (Phases 4–7, planned 2026-04-23)

## Phases

### ✅ v0.8.12.7 — System Prompt Extraction (Shipped)

**Milestone Goal:** Move the ~460-line hard-coded Computer Use system prompt out of the Open WebUI filter and into a server endpoint that does full substitution on the server (URLs from `chat_id`, dynamic `<available_skills>` from optional `user_email`, graceful fallback to default public skills when no external provider is wired). Filter becomes a thin HTTP-fetch + LRU cache + stale-cache fallback layer.

- [x] **Phase 1: System Prompt Extraction** — Port internal v3.7/v3.8 server-side substitution to community. Upgrade `GET /system-prompt`. Rewrite filter as thin HTTP client + LRU cache + stale-cache fallback. Add tests.

### ✅ v0.8.12.8 — Preview Filter UX (Shipped)

**Milestone Goal:** Expose the already-shipped `/preview/{chat_id}` SPA to users of stock Open WebUI (without frontend patches). Filter's `outlet()` learns to emit an inline iframe artifact by default and, opt-in, a markdown preview button. All v3.1.0 `outlet()` correctness invariants preserved. Every Valve (old and new) documented in one authoritative place.

- [x] **Phase 2: Preview Filter UX** — Added three new Valves to `computer_link_filter.py`, extended `outlet()` to emit preview iframe (default) and preview button (opt-in), bumped filter 3.1.0 → 3.2.0 (commit `b08d472`), documented every Valve in a `VALVES:` docstring block + `docs/openwebui-filter.md` (+ troubleshooting section in `d79f730`), proved both the feature and the existing behaviour with pytest in Docker.

### ✅ v0.8.12.9 — Claude Code Gateway Compatibility (Code shipped, no release cut)

**Milestone Goal:** The Claude Code sub-agent running inside each sandbox container routes its API calls to whatever Anthropic-compatible destination the operator configured (public Anthropic, LiteLLM proxy, Azure, Bedrock-via-LiteLLM, etc.), with optional model-ID and prompt-caching/beta overrides — all without ever breaking the zero-config `/login` path. Fixes issue #40; inspired by PR #41 but rewritten with tests and without the deploy-specific churn.

- [x] **Phase 3: Claude Code Gateway Compatibility** — All 3 plans shipped on `main` in 2026-04-12 via commit `38347fd`. Release not cut separately; per 2026-04-23 decision, folded into the v0.9.1.0 CHANGELOG.

### 🚧 v0.9.1.0 — Open WebUI 0.9 Compatibility (Planned 2026-04-23)

**Milestone Goal:** Upgrade the Open WebUI base image from `ghcr.io/open-webui/open-webui:0.8.12` to `:0.9.1` (latest upstream at milestone start). Rewrite every patch in `openwebui/patches/` against the new upstream frontend (freshly minified Svelte chunks) and backend (possibly reshuffled `middleware.py`). Re-enable the 4 currently commented-out patches in the Dockerfile if they still make sense at 0.9.1. Verify Tool + Filter still load, register, and seed Valves without errors. Ship `v0.9.1.0` as the first release of the new `0.9.X.Y` series; CHANGELOG rolls in the previously-unreleased Phase 3 gateway work.

- [ ] **Phase 4: Upstream intake and patch inventory** — Clone `open-webui/open-webui@v0.9.1` source, diff its frontend chunks and `middleware.py` against `v0.8.12`, produce a per-patch impact matrix documenting where each of the 8 patches' anchor patterns moved / disappeared / were renamed.
- [ ] **Phase 5: Rewrite frontend patches against v0.9.1** — Rewrite `fix_artifacts_auto_show.py` and `fix_preview_url_detection.py` against the v0.9.1 compiled Svelte. Each patch must detect the new minified identifiers (regexes tightened), stay idempotent (already-patched markers), fail loudly if anchor not found. Smoke-test in a running v0.9.1 container.
- [ ] **Phase 6: Rewrite backend patches against v0.9.1** — Rewrite `fix_tool_loop_errors.py` and `fix_large_tool_results.py` against v0.9.1 `middleware.py`. Rewrite the 4 currently-commented patches (`fix_large_tool_args`, `fix_attached_files_position`, `fix_skip_embedding_chat_files`, `fix_skip_rag_files_native_fc`) if their target code still exists at 0.9.1 (drop if obsolete, document in REQUIREMENTS.md Out of Scope). Re-enable verified patches in `openwebui/Dockerfile`.
- [ ] **Phase 7: Release v0.9.1.0** — Bump defaults (`OPENWEBUI_VERSION=0.9.1` in compose + Dockerfile ARG). Run all three test scripts + pytest green. Update CHANGELOG.md with a `v0.9.1.0` entry that (a) announces the base bump and patch rewrites, (b) rolls in Phase 3 Claude Code gateway work, (c) documents the exact upstream tag (`ghcr.io/open-webui/open-webui:0.9.1`) as the supported base. Update README compat line. Commit `chore: release v0.9.1.0`. Do NOT tag (user batches releases).

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
- [x] 03-03-PLAN.md — Config and docs (docker-compose.yml env wiring, .env.example gateway-overrides block, new docs/claude-code-gateway.md, README/INSTALL cross-links) — Wave 2

### Phase 4: Upstream intake and patch inventory (v0.9.1.0)

**Goal:** Produce a hard-evidence inventory of what changed between Open WebUI `v0.8.12` and `v0.9.1` at exactly the anchor points our 8 patches touch, so Phases 5 and 6 have a concrete map (not guesses) for where to rewrite each patch.
**Depends on:** Nothing. Pure read-only investigation.
**Requirements:** OWUI-INTAKE-01 (source cloned), OWUI-INTAKE-02 (per-patch impact matrix written), OWUI-INTAKE-03 (obsolete patches flagged)
**Success Criteria:** (observable)
  1. `open-webui/open-webui@v0.9.1` source checked out at a known path (outside this repo), with its `package.json` confirming the `0.9.1` tag.
  2. `.planning/phases/04-owui-intake/04-INVENTORY.md` exists and, for each of the 8 patches, contains: (a) the exact upstream file(s) each patch modifies, (b) a code excerpt at the `v0.8.12` anchor, (c) the matching excerpt at `v0.9.1` (or a "not found" note with evidence), (d) a 1-sentence rewrite-strategy (rename regex / rewrite entirely / drop as obsolete).
  3. For the 4 currently-commented patches, the inventory also classifies: still-valuable-at-0.9.1 (rewrite), obsolete-at-0.9.1 (drop + document).
  4. No code changes in this phase. No image rebuild.

**Plans:** 1 plan

Plans:
- [x] 04-01-PLAN.md — Mint OWUI-INTAKE-01/02/03, clone upstream open-webui, capture per-patch anchors at v0.8.12 and v0.9.1, and write 04-INVENTORY.md with verdicts (read-only investigation) — Wave 1

### Phase 5: Rewrite frontend patches against v0.9.1 (v0.9.1.0)

**Goal:** `fix_artifacts_auto_show.py` and `fix_preview_url_detection.py` apply cleanly against a v0.9.1 image and produce the same observable user-facing behaviour we ship on `v0.8.12`.
**Depends on:** Phase 4 (needs the inventory to know what to rewrite).
**Requirements:** OWUI-FE-01 (artifacts auto-show patch applied + verified), OWUI-FE-02 (preview URL detection patch applied + verified), OWUI-FE-03 (both patches idempotent + loud-fail on anchor-not-found)
**Success Criteria:** (observable)
  1. `docker build --platform linux/amd64 --build-arg OPENWEBUI_VERSION=0.9.1 …` completes with no patch failing its "already patched" check on a fresh build and with no silent no-op.
  2. Live UI verification: open the built image, open a chat, ask for an HTML artifact — the Artifacts panel auto-opens; ask for a file preview — the preview iframe renders. Screenshots captured to `.planning/phases/05-frontend-patches/` as evidence.
  3. Both patches emit a visible error (non-zero exit) if their anchor regex fails to match — caught by re-running the patch script on an already-patched chunk (must see "ALREADY PATCHED" markers, not "MATCH NOT FOUND").
  4. `./tests/test-docker-image.sh` passes for the `v0.9.1` image.

**Plans:** 2 plans

Plans:
- [x] 05-01-PLAN.md — Mint OWUI-FE-01/02/03, rewrite both frontend patches with idempotency markers + fail-loud exits, verify docker build + test-docker-image.sh on v0.9.1 (Wave 1, autonomous)
- [ ] 05-02-PLAN.md — Live-UI smoke test: launch built v0.9.1 image, capture screenshots of Artifacts panel auto-open and preview iframe render (Wave 2, human UAT required)

### Phase 6: Rewrite backend patches against v0.9.1 (v0.9.1.0)

**Goal:** All middleware/Python patches apply cleanly and preserve their behaviour on v0.9.1. The 4 currently-commented patches each get a verdict: rewrite + enable, or drop + document in REQUIREMENTS.md Out of Scope.
**Depends on:** Phase 4 (inventory).
**Requirements:** OWUI-BE-01..OWUI-BE-06 (one per patch — `tool_loop_errors`, `large_tool_results`, `large_tool_args`, `attached_files_position`, `skip_embedding_chat_files`, `skip_rag_files_native_fc`)
**Success Criteria:** (observable)
  1. Each of the 6 python-target patches has a verdict in `.planning/phases/06-backend-patches/06-VERDICT.md`: rewritten+enabled, rewritten+optional, or dropped-obsolete (with reason).
  2. For each rewritten+enabled patch: pytest coverage (existing or new) passes against a python:3.13-slim + patched `middleware.py`; the patch is uncommented in `openwebui/Dockerfile`.
  3. For each dropped patch: `openwebui/patches/` file deleted, `openwebui/Dockerfile` comment removed, reason logged in `REQUIREMENTS.md` Out of Scope.
  4. `pytest tests/` green on the current repo against the v0.9.1 image (orchestrator suites unchanged, filter suite unchanged, patch suite may change).

**Plans:** 2–3 plans expected — TBD by `/gsd-plan-phase 6`.

### Phase 7: Release v0.9.1.0 (v0.9.1.0)

**Goal:** Ship a clean `v0.9.1.0` release commit. Users cloning `main` and running `docker compose -f docker-compose.webui.yml up --build` get Computer Use working end-to-end against Open WebUI `0.9.1` with no extra configuration.
**Depends on:** Phase 5 AND Phase 6 (both patch sets must be green).
**Requirements:** OWUI-REL-01 (defaults bumped), OWUI-REL-02 (CHANGELOG written with Phase 3 gateway rollup), OWUI-REL-03 (README compat line updated), OWUI-REL-04 (full test suite green on the built image)
**Success Criteria:** (observable)
  1. `docker-compose.webui.yml` default `OPENWEBUI_VERSION=0.9.1`; `openwebui/Dockerfile` `ARG OPENWEBUI_VERSION=0.9.1`.
  2. `CHANGELOG.md` has a `## v0.9.1.0 (YYYY-MM-DD)` entry that: (a) states supported upstream = `ghcr.io/open-webui/open-webui:0.9.1`, (b) lists every rewritten patch with a one-line behaviour description, (c) rolls in Phase 3 Claude Code gateway work (GATEWAY-01..12) as "Features" with a pointer to `docs/claude-code-gateway.md`, (d) lists any dropped patches under "Breaking changes" if applicable.
  3. `README.md` quick-start section states compatibility with Open WebUI `0.9.1`.
  4. `./tests/test-docker-image.sh`, `./tests/test-no-corporate.sh`, `./tests/test-project-structure.sh` all pass against the rebuilt image. `pytest tests/` green inside `python:3.13-slim`.
  5. One commit `chore: release v0.9.1.0` merged to `main`. **No git tag created** (user tags manually per memory rule).

**Plans:** 1 plan expected — TBD by `/gsd-plan-phase 7`.

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. System Prompt Extraction (v0.8.12.7)      | 1/1 | ✅ Complete     | 2026-04-12 |
| 2. Preview Filter UX (v0.8.12.8)             | 1/1 | ✅ Complete     | 2026-04-12 |
| 3. Claude Code Gateway Compatibility (v0.8.12.9) | 3/3 | ✅ Code shipped (no release) | 2026-04-12 |
| 4. Upstream intake and patch inventory (v0.9.1.0) | 0/? | 🚧 Planned | — |
| 5. Rewrite frontend patches (v0.9.1.0)       | 0/? | 🚧 Planned | — |
| 6. Rewrite backend patches (v0.9.1.0)        | 0/? | 🚧 Planned | — |
| 7. Release v0.9.1.0                          | 0/? | 🚧 Planned | — |

---
*Updated 2026-04-23 — v0.9.1.0 milestone added with 4 phases (Phases 4–7). Phase 3 reclassified as shipped-no-release; its CHANGELOG entry rolls into v0.9.1.0.*
