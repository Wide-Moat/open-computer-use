# Roadmap: Open Computer Use

## Milestones

- ✅ **v0.8.12.7 — System Prompt Extraction** (Phase 1, shipped 2026-04-12)
- ✅ **v0.8.12.8 — Preview Filter UX** (Phase 2, shipped 2026-04-12; v4.1.0 follow-up 2026-04-19)
- ✅ **v0.8.12.9 — Claude Code Gateway Compatibility** (Phase 3, code shipped 2026-04-12; rolled into release)
- 🚧 **v0.9.2.0 — Open WebUI 0.9 Compatibility** (Phases 4–10, repositioned 2026-04-24 after upstream v0.9.2 landed mid-milestone — target bumped from 0.9.1 → 0.9.2 with no release cut at 0.9.1)

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

### 🚧 v0.9.2.0 — Open WebUI 0.9 Compatibility (Repositioned 2026-04-24)

**Milestone Goal:** Upgrade the Open WebUI base image from `ghcr.io/open-webui/open-webui:0.8.12` to `:0.9.2` (latest upstream as of milestone-day pivot). Reuse the 0.9.1-era rewritten patches (all 8 have idempotency markers + `sys.exit(1)` fail-loud + 3-state pytest) as baseline. Re-verify each patch's anchor against v0.9.2 source/chunks; tighten regexes where v0.9.1→v0.9.2 drift changed them. Ship `v0.9.2.0` as the first release of the `0.9.X.Y` series; CHANGELOG rolls in Phase 3 gateway work + the 0.9.x base bump.

**Intermediate milestone pivot (2026-04-24):** Phases 4–6 were executed against v0.9.1. Mid-stream, upstream released v0.9.2 (touches `middleware.py` +87/−24, `retrieval.py` +16, multiple Svelte files). Decision: re-use Phase 4–6 artefacts (INVENTORY.md, rewritten patches, pytest harness) as a baseline; add fresh upstream-intake + re-patch phases (7–9) targeting v0.9.2; release as `v0.9.2.0` (skip v0.9.1.0).

- [x] **Phase 4: Upstream intake and patch inventory (v0.9.1 baseline)** — Done 2026-04-24. Cloned `open-webui@v0.9.1`. Per-patch anchor matrix for all 8 patches; all classified rewrite+enable, 0 drops. Baseline for 0.9.2 delta work.
- [x] **Phase 5: Rewrite frontend patches (v0.9.1)** — Done 2026-04-24. `fix_artifacts_auto_show.py` + `fix_preview_url_detection.py` rewritten with idempotency markers + `sys.exit(1)` fail-loud. Build green; 3-state tests; human LLM UAT pending but code path confirmed live.
- [x] **Phase 6: Rewrite backend patches (v0.9.1)** — Done 2026-04-24. All 6 backend patches rewritten with idempotency + fail-loud; 4 currently-commented patches enabled in Dockerfile. pytest 229/0. Build log shows 8 PATCHED markers.
- [ ] **Phase 7: Upstream re-intake against v0.9.2** — Fetch `open-webui@v0.9.2` (already pulled in upstream clone). Diff `middleware.py`, `retrieval.py`, and the Svelte source anchors between v0.9.1 and v0.9.2. Produce `07-INVENTORY-DELTA.md` mapping each of the 8 patch anchors → still-matches / needs-tweak / broken. Pure read-only investigation; no code changes. Reuses `~/src/open-webui-upstream`.
- [ ] **Phase 8: Re-verify frontend patches against v0.9.2** — For each of 2 frontend patches: pull v0.9.2 image chunks, grep for structural anchor; if still matches → keep regex, re-run 3-state tests against v0.9.2 fixture; if broken → re-derive regex from v0.9.2 compiled chunk, retain idempotency marker + fail-loud. Build `open-computer-use:0.9.2-test` image green; chunks served over HTTP contain patch markers.
- [ ] **Phase 9: Re-verify backend patches against v0.9.2** — For each of 6 backend patches: diff the anchor lines in v0.9.2 `middleware.py`/`retrieval.py`, update regex/SEARCH blocks where v0.9.2 drift (new try/except wraps, async changes, renamed fields) requires it; keep idempotency markers; ensure cascade (patches 3+4) stays atomic. pytest 3-state + cascade tests all green on v0.9.2. Rebuild `open-computer-use:0.9.2-test` — build log has 8 PATCHED markers.
- [x] **Phase 10: Release v0.9.2.0** — Bump `ARG OPENWEBUI_VERSION=0.9.2` in `openwebui/Dockerfile`, `OPENWEBUI_VERSION=0.9.2` in `docker-compose.webui.yml`. Run the three shell tests + full pytest. Prepend `## v0.9.2.0 (YYYY-MM-DD)` in CHANGELOG.md with (a) base bump 0.8.12 → 0.9.2, (b) 8 rewritten patches one-liner each, (c) Phase 3 GATEWAY-01..12 rollup → `docs/claude-code-gateway.md`. Update README compat line. ONE commit `chore: release v0.9.2.0`. NO git tag. NO git push. (completed 2026-04-25)

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
- [x] 05-02-PLAN.md — Live-UI smoke test: launch built v0.9.1 image, capture screenshots of Artifacts panel auto-open and preview iframe render (Wave 2, human UAT required)

### Phase 6: Rewrite backend patches against v0.9.1 (v0.9.1.0)

**Goal:** All middleware/Python patches apply cleanly and preserve their behaviour on v0.9.1. The 4 currently-commented patches each get a verdict: rewrite + enable, or drop + document in REQUIREMENTS.md Out of Scope.
**Depends on:** Phase 4 (inventory).
**Requirements:** OWUI-BE-01..OWUI-BE-06 (one per patch — `tool_loop_errors`, `large_tool_results`, `large_tool_args`, `attached_files_position`, `skip_embedding_chat_files`, `skip_rag_files_native_fc`)
**Success Criteria:** (observable)
  1. Each of the 6 python-target patches has a verdict in `.planning/phases/06-backend-patches/06-VERDICT.md`: rewritten+enabled, rewritten+optional, or dropped-obsolete (with reason).
  2. For each rewritten+enabled patch: pytest coverage (existing or new) passes against a python:3.13-slim + patched `middleware.py`; the patch is uncommented in `openwebui/Dockerfile`.
  3. For each dropped patch: `openwebui/patches/` file deleted, `openwebui/Dockerfile` comment removed, reason logged in `REQUIREMENTS.md` Out of Scope.
  4. `pytest tests/` green on the current repo against the v0.9.1 image (orchestrator suites unchanged, filter suite unchanged, patch suite may change).

**Plans:** 2 plans

Plans:
- [x] 06-01-PLAN.md — Mint OWUI-BE-01..06, extract v0.9.1 fixtures, rewrite all 6 backend patches (cascade 3+4 atomic) with fail-loud + idempotency markers, add 3-state pytest coverage per patch — Wave 1, autonomous
- [x] 06-02-PLAN.md — Uncomment 4 Dockerfile backend patch lines, rebuild open-computer-use:0.9.1-test, run full-repo pytest in python:3.13-slim, write 06-VERDICT.md — Wave 2, autonomous

### Phase 7: Upstream re-intake against v0.9.2 (v0.9.2.0)

**Goal:** Hard-evidence delta inventory mapping every one of the 8 patch anchors from Phase 4's v0.9.1 baseline onto upstream v0.9.2, so Phases 8 and 9 know exactly which regexes need tweaks without blind-rebuild-and-pray.
**Depends on:** Phase 4 (v0.9.1 baseline inventory), Phase 5, Phase 6 (v0.9.1 patch set is the re-verification target).
**Requirements:** OWUI-INTAKE-V092-01 (v0.9.2 tag reachable in shared clone), OWUI-INTAKE-V092-02 (per-patch delta matrix written)
**Success Criteria:** (observable)
  1. `.planning/phases/07-upstream-intake-v0-9-2/07-INVENTORY-DELTA.md` exists with 8 per-patch sections; each carries (a) v0.9.1 anchor excerpt copied verbatim from 04-INVENTORY.md, (b) v0.9.2 content at the same anchor, (c) verdict `still-matches` / `needs-tweak` / `broken`, (d) Phase 8/9 strategy sentence if not still-matches.
  2. Top of the DELTA file carries a Summary Verdicts table: 8 rows × (Patch, verdict, severity) with no placeholder strings.
  3. `/tmp/phase7-refs/` holds reusable v0.9.2 excerpts: 10 full-file snapshots (middleware/retrieval/Artifacts/Chat/index at both tags), 2 unified diffs (middleware, retrieval), 8 per-patch anchor listings — Phase 8/9 do not re-run any `git show`.
  4. Read-only scope honoured: `git status --porcelain openwebui/ tests/ computer-use-server/` prints nothing.
  5. OWUI-INTAKE-V092-01/02 minted in REQUIREMENTS.md with traceability rows.

**Plans:** 1 plan

Plans:
- [x] 07-01-PLAN.md — Mint OWUI-INTAKE-V092-01/02, extract v0.9.2 anchor excerpts to /tmp/phase7-refs/ (reusing ~/src/open-webui-upstream clone), write 07-INVENTORY-DELTA.md with 8 per-patch verdicts + summary table, confirm zero code changes — Wave 1, autonomous

### Phase 8: Re-verify frontend patches against v0.9.2 (v0.9.2.0)

**Goal:** Prove the two v0.9.1-era rewritten frontend patches (`fix_artifacts_auto_show.py`, `fix_preview_url_detection.py`) still apply cleanly against Open WebUI v0.9.2 compiled SvelteKit chunks, without logic rewrite. Ship `open-computer-use:0.9.2-test` with both idempotency markers baked in.
**Depends on:** Phase 5 (v0.9.1 baseline patches with markers), Phase 7 (07-INVENTORY-DELTA.md — still-matches verdict for both patches).
**Requirements:** OWUI-FE-V092-01 (artifacts patch applied on v0.9.2 + marker baked), OWUI-FE-V092-02 (preview patch applied on v0.9.2 + marker baked)
**Success Criteria:** (observable)
  1. `docker build --platform linux/amd64 --build-arg OPENWEBUI_VERSION=0.9.2 -f openwebui/Dockerfile -t open-computer-use:0.9.2-test openwebui/` exits 0.
  2. Build log contains exactly one `PATCHED: fix_artifacts_auto_show applied successfully.` line AND one `PATCHED: fix_preview_url_detection applied successfully.` line, with zero `ERROR: fix_*` lines.
  3. `docker run --rm --entrypoint grep open-computer-use:0.9.2-test -rl '<MARKER>' /app/build/_app/immutable/chunks` lists at least one chunk path for each of `FIX_ARTIFACTS_AUTO_SHOW` and `FIX_PREVIEW_URL_DETECTION`.
  4. If regex tightening was required: diff is under 20 lines and scoped to literal/character-class changes only (no logic / marker / exit-path changes). If not required (expected per Phase 7 still-matches verdict): `git diff openwebui/patches/` is empty.
  5. OWUI-FE-V092-01/02 minted in REQUIREMENTS.md with `Complete` traceability rows. The Phase 5 image `open-computer-use:0.9.1-test` is still present (new tag `:0.9.2-test` does not overwrite it).

**Plans:** 1 plan

Plans:
- [x] 08-01-PLAN.md — Mint OWUI-FE-V092-01/02, extract v0.9.2 chunks to /tmp/phase8-chunks/, dry-run both frontend patches against extracted chunks, tighten regex only if drifted, build open-computer-use:0.9.2-test with --build-arg OPENWEBUI_VERSION=0.9.2, verify both idempotency markers baked in built-image chunks — Wave 1, autonomous


### Phase 9: Re-verify backend patches against v0.9.2 (v0.9.2.0)

**Goal:** All 6 backend patches apply cleanly on Open WebUI v0.9.2 `middleware.py` / `retrieval.py`. Patches 3 & 4 tweaked (the Phase 7 `needs-tweak` verdicts: new `'metadata': metadata,` key inserted into both `new_form_data = {` blocks); patches 5/6/7/8 confirmed byte-identical. Full `openwebui/Dockerfile` builds green with `--build-arg OPENWEBUI_VERSION=0.9.2`, build log has 8 PATCHED markers, cascade (3+4) stays atomic, full-repo pytest green.
**Depends on:** Phase 6 (v0.9.1 baseline patch set + pytest harness), Phase 7 (07-INVENTORY-DELTA.md — needs-tweak verdicts for patches 3 & 4), Phase 8 (establishes the full-Dockerfile build gap to close).
**Requirements:** OWUI-BE-V092-01, OWUI-BE-V092-02, OWUI-BE-V092-03, OWUI-BE-V092-04, OWUI-BE-V092-05, OWUI-BE-V092-06
**Success Criteria:** (observable)
  1. `.planning/REQUIREMENTS.md` contains OWUI-BE-V092-01..06 flipped to `[x]` / Complete after phase close.
  2. `openwebui/patches/fix_tool_loop_errors.py` + `openwebui/patches/fix_large_tool_results.py` SEARCH blocks include the new v0.9.2 `'metadata': metadata,` line; `sys.exit(1)` fail-loud preserved; idempotency markers (`FIX_TOOL_LOOP_ERRORS`, `FIX_LARGE_TOOL_RESULTS`) unchanged; patches 5/6/7/8 untouched.
  3. `tests/patches/fixtures/middleware_v0.9.2.py` + `tests/patches/fixtures/retrieval_v0.9.2.py` exist, byte-identical to `git -C ~/src/open-webui-upstream show v0.9.2:backend/...`.
  4. `python3 -m pytest tests/patches/ -v` passes with >= 49 tests (31 Phase-6 baseline + 18 new v0.9.2 3-state/cascade).
  5. `docker build --platform linux/amd64 --build-arg OPENWEBUI_VERSION=0.9.2 -f openwebui/Dockerfile -t open-computer-use:0.9.2-test openwebui/` exits 0; build log has exactly 8 `PATCHED: fix_* applied successfully.` lines and 0 `ERROR: fix_*` lines; `open-computer-use:0.9.1-test` image preserved (not overwritten).
  6. `python -m pytest tests/ -v` green inside python:3.13-slim (0 failed, 0 errored).
  7. `.planning/phases/09-backend-patches-v0-9-2/09-VERDICT.md` documents per-patch v0.9.2 outcome (all 6 BE rewrite-enabled or still-matches, zero dropped).
  8. `openwebui/Dockerfile` ARG `OPENWEBUI_VERSION=0.8.12` default UNCHANGED (Phase 10 bumps it).

**Plans:** 2 plans

Plans:
- [x] 09-01-PLAN.md — Mint OWUI-BE-V092-01..06, add v0.9.2 middleware/retrieval fixtures, cascade-update patches 3 & 4 SEARCH blocks for the new `'metadata': metadata,` key (atomic), dry-verify patches 5/6/7/8 still-match v0.9.2, extend pytest 3-state + cascade coverage to the v0.9.2 fixture — Wave 1, autonomous
- [x] 09-02-PLAN.md — Full production-Dockerfile rebuild at `--build-arg OPENWEBUI_VERSION=0.9.2`, verify 8 PATCHED markers + 0 ERROR lines, full-repo pytest green in python:3.13-slim, author 09-VERDICT.md, flip REQUIREMENTS.md OWUI-BE-V092-01..06 to Complete — Wave 2, autonomous

### Phase 10: Release v0.9.2.0 (v0.9.2.0)

**Goal:** Bump `ARG OPENWEBUI_VERSION=0.8.12` → `0.9.2` in `openwebui/Dockerfile` and `docker-compose.webui.yml`; prepend a `## v0.9.2.0 (YYYY-MM-DD)` entry to `CHANGELOG.md` that documents the base bump, the 8 rewritten patches (Phases 4–9) with their markers and behaviours, and the Phase 3 Claude Code Gateway rollup (GATEWAY-01..12) linking to `docs/claude-code-gateway.md`; refresh README + INSTALL compatibility references. Run the three project shell tests + full pytest green, create ONE commit `chore: release v0.9.2.0`. NO git tag. NO git push.
**Depends on:** Phase 8 (frontend patches re-verified at v0.9.2), Phase 9 (backend patches re-verified at v0.9.2, pytest green).
**Requirements:** OWUI-REL-V092-01, OWUI-REL-V092-02, OWUI-REL-V092-03, OWUI-REL-V092-04
**Success Criteria:** (observable)
  1. `openwebui/Dockerfile` line 3 reads `ARG OPENWEBUI_VERSION=0.9.2` (no occurrences of `0.8.12` remain in the file).
  2. `docker-compose.webui.yml` line 18 reads `OPENWEBUI_VERSION: ${OPENWEBUI_VERSION:-0.9.2}`.
  3. `CHANGELOG.md` top entry is `## v0.9.2.0 (<release date>)` and contains: (a) base bump statement 0.8.12 → 0.9.2 with "no 0.9.1 release cut" note, (b) 8 patches one-liner each with marker names, (c) Phase 3 GATEWAY-01..12 rollup with link to `docs/claude-code-gateway.md`, (d) Known Limitations paragraph flagging that v0.9.2 live UI UAT is deferred to the user's post-release run.
  4. `README.md` compatibility copy references Open WebUI 0.9.2 in both the "Compatibility:" line and the "Why not a fork?" paragraph. `docs/INSTALL.md` has any base-version callouts updated to 0.9.2.
  5. `./tests/test-docker-image.sh` (skipped cleanly if no `:latest` image present), `./tests/test-no-corporate.sh`, `./tests/test-project-structure.sh` return exit 0; `python -m pytest tests/` inside `python:3.13-slim` returns exit 0 with 0 failed / 0 errored.
  6. Exactly ONE new commit lands with subject `chore: release v0.9.2.0`, touching exactly 6 files (REQUIREMENTS.md, Dockerfile, docker-compose.webui.yml, README.md, docs/INSTALL.md, CHANGELOG.md).
  7. `git tag --list | grep -Fx v0.9.2.0` returns zero results (user tags manually).
  8. No `git push` was invoked by the phase (user pushes manually).
  9. `git config user.email` is `i@yambr.com` at commit time.

**Plans:** 1/1 plans complete

Plans:
- [x] 10-01-PLAN.md — Mint OWUI-REL-V092-01..04, bump Dockerfile + docker-compose.webui.yml defaults 0.8.12 → 0.9.2, refresh README + INSTALL compat references, prepend CHANGELOG v0.9.2.0 entry (8 patches + GATEWAY-01..12 rollup), run three shell tests + full pytest (BLOCKS commit on red), create ONE `chore: release v0.9.2.0` commit with 4-layer protection (identity gate, idempotency gate, allowlist staging, post-commit tag/push/file-count verification) — Wave 1, autonomous


## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. System Prompt Extraction (v0.8.12.7)      | 1/1 | ✅ Complete     | 2026-04-12 |
| 2. Preview Filter UX (v0.8.12.8)             | 1/1 | ✅ Complete     | 2026-04-12 |
| 3. Claude Code Gateway Compatibility (v0.8.12.9) | 3/3 | ✅ Code shipped (no release) | 2026-04-12 |
| 4. Upstream intake and patch inventory (v0.9.1 baseline) | 1/1 | ✅ Complete | 2026-04-24 |
| 5. Rewrite frontend patches (v0.9.1)         | 2/2 | ✅ Complete | 2026-04-24 |
| 6. Rewrite backend patches (v0.9.1)          | 2/2 | ✅ Complete | 2026-04-24 |
| 7. Upstream re-intake against v0.9.2 (v0.9.2.0) | 0/1 | 🚧 Planned | — |
| 8. Re-verify frontend patches against v0.9.2 | 0/1 | 🚧 Planned | — |
| 9. Re-verify backend patches against v0.9.2  | 0/2 | 🚧 Planned | — |
| 10. Release v0.9.2.0                         | 1/1 | Complete   | 2026-04-25 |

---
*Updated 2026-04-24 — Phase 10 planned (1 plan, Wave 1, autonomous, held pending user UAT). Release commit only — no tag, no push.*
