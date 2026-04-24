# Phase 6: Backend Patches Verdict

**Phase:** 06-backend-patches (v0.9.1.0 milestone)
**Produced:** 2026-04-24
**Rebuilt image:** `open-computer-use:0.9.1-test` (v0.9.1 base + 8 patches)
**Outcome:** All 6 backend patches rewrite+enabled. Zero dropped.

## Summary Verdicts

| # | Patch | v0.8.12 status | v0.9.1 verdict | Dockerfile line | Pytest | Requirement |
|---|-------|----------------|----------------|-----------------|--------|-------------|
| 3 | fix_tool_loop_errors.py           | ACTIVE    | rewrite+enabled | line 13 active | PASS  | OWUI-BE-01 |
| 4 | fix_large_tool_results.py         | ACTIVE    | rewrite+enabled | line 23 active | PASS  | OWUI-BE-02 |
| 5 | fix_large_tool_args.py            | COMMENTED | rewrite+enabled | line 29 uncommented | PASS | OWUI-BE-03 |
| 6 | fix_attached_files_position.py    | COMMENTED | rewrite+enabled | line 33 uncommented | PASS | OWUI-BE-04 |
| 7 | fix_skip_embedding_chat_files.py  | COMMENTED | rewrite+enabled | line 37 uncommented | PASS | OWUI-BE-05 |
| 8 | fix_skip_rag_files_native_fc.py   | COMMENTED | rewrite+enabled | line 41 uncommented | PASS | OWUI-BE-06 |

**Zero patches dropped / classified obsolete.**

## Per-Patch Details

### Patch 3: fix_tool_loop_errors.py — OWUI-BE-01 — rewrite+enabled

**v0.9.1 anchor changes applied:**
- Anchor B (SEARCH_CODE_INTERP): added `await` before `Chats.get_chat_title_by_id(metadata['chat_id'])` in BOTH SEARCH and REPLACE — upstream async-ified `Chats.*` accessors in v0.9.1. [04-INVENTORY.md Patch 3 anchor B]
- Anchor D (SEARCH_DONE_BG): **new lines inserted** — upstream v0.9.1 inserted a fresh `assistant_message` dict + `outlet_filter_handler(ctx)` call between `await background_tasks_handler(ctx)` and the `except asyncio.CancelledError:` terminator. 06-01 Task 3 Step A re-extracted the exact v0.9.1 block from `~/src/open-webui-upstream/backend/open_webui/utils/middleware.py` at tag v0.9.1; REPLACE_DONE_BG now wraps both the `assistant_message` construction and the `outlet_filter_handler(ctx)` call inside the try/except scope. [06-01-SUMMARY.md L51, L97; 06-RESEARCH.md L60]
- Other 3 anchors (TOOL_LOOP, SSE, ITER): unchanged — line drift only.

**Fail-loud conversion:** 5 sub-anchor misses each hard-fail with `sys.exit(1)` + stderr ERROR. Partial-match silent ship eliminated (old `changes >= 1` aggregation removed). Sub-anchor loop unrolled into 5 per-anchor blocks to satisfy the `grep -c "sys.exit(1)" ≥ 5` acceptance criterion.

**Idempotency marker:** `FIX_TOOL_LOOP_ERRORS` added alongside legacy `TOOL_LOOP_ERRORS_UNIFIED`.

**Test coverage:** `tests/patches/test_fix_tool_loop_errors.py` — 3 states pass against real v0.9.1 fixture (fresh / idempotent / broken).

**Build evidence:** `grep "PATCHED: fix_tool_loop_errors applied successfully" /tmp/phase6-build.log` → 1 match (line 38).

### Patch 4: fix_large_tool_results.py — OWUI-BE-02 — rewrite+enabled (cascade)

**v0.9.1 anchor changes applied:** none on SEARCH/REPLACE text (Patch 3's REPLACE_TOOL_LOOP output still contains the `TOOL_LOOP_ERRORS_UNIFIED: save for restore on error` comment tail that Patch 4 anchors on). SEARCH_HISTORY byte-identical.

**Cascade atomicity:** rewritten together with Patch 3 in 06-01 commit `13e5c98`; pytest cascade test `test_cascade_with_patch_3` validates both apply in sequence to same v0.9.1 fixture. Initial cascade attempt failed because Patch 3's REPLACE_TOOL_LOOP originally appended `; FIX_TOOL_LOOP_ERRORS` to the TOOL_LOOP_ERRORS_UNIFIED save-comment line (breaking Patch 4's byte-match); resolution was to keep that specific comment line unchanged and inject the new marker elsewhere in the REPLACE blocks.

**Fail-loud conversion:** Mod 1 (import marker), Mod 2 (SEARCH_TOOL_LOOP), Mod 3 (SEARCH_HISTORY) all hard-fail. Mod 2 miss message directs operator to run patch 3 first.

**Idempotency marker:** `FIX_LARGE_TOOL_RESULTS` added alongside legacy `_truncate_large_results_in_output` function-name marker.

**Build evidence:** `grep "PATCHED: fix_large_tool_results applied successfully" /tmp/phase6-build.log` → 1 match (line 74).

### Patch 5: fix_large_tool_args.py — OWUI-BE-03 — rewrite+enabled (newly enabled)

**v0.9.1 anchor changes applied:** SEARCH literal byte-identical (2 occurrences of `arguments="{html.escape(json.dumps(arguments))}"` at lines 498 and 502 in v0.9.1). Added `content.count(OLD_ARGS) != 2` hard-fail assertion to catch future upstream drift (e.g. a third variant added in v0.9.2).

**Fail-loud + count assertion:** `test_count_assertion_triggers_on_three` validates ERROR + exit 1 when a third occurrence appears in the fixture.

**Idempotency marker:** `FIX_LARGE_TOOL_ARGS` added alongside existing `_truncate_for_attr` function-name marker.

**Build evidence:** `grep "PATCHED: fix_large_tool_args applied successfully" /tmp/phase6-build.log` → 1 match (line 86).

**Dockerfile change:** line 29 uncommented in Task 1 of 06-02.

### Patch 6: fix_attached_files_position.py — OWUI-BE-04 — rewrite+enabled (classification downgraded)

**v0.9.1 anchor changes applied:** SEARCH literal byte-identical. Docstring version range updated `v0.8.11–0.8.12` → `v0.8.11–0.9.1`.

**Classification downgrade:** 04-INVENTORY.md labelled this patch "rewrite entirely" (defensive over-classification because the enclosing function `add_file_context` became `async def`). 06-RESEARCH.md § Patch 6 downgraded to "rewrite regex": the inner 5-line SEARCH block is byte-identical and does NOT reference the `async def` header or the awaited `Chats.get_chat_by_id_and_user_id` call. **Confirmed:** 06-01 Task 4 applied regex-level rewrite; pytest fresh+idempotent+broken states all green.

**Idempotency marker:** `FIX_ATTACHED_FILES_POSITION` added alongside existing `attached_files_append`.

**English-only audit:** no Cyrillic in file (CLAUDE.md rule).

**Build evidence:** `grep "PATCHED: fix_attached_files_position applied successfully" /tmp/phase6-build.log` → 1 match (line 93).

**Dockerfile change:** line 33 uncommented in Task 1 of 06-02.

### Patch 7: fix_skip_embedding_chat_files.py — OWUI-BE-05 — rewrite+enabled (newly enabled)

**v0.9.1 anchor changes applied:** both SEARCH literals byte-identical at v0.9.1 (retrieval.py, line drift +12 and +14 only). Docstring version range updated.

**Fail-loud upgrade:** previously had asymmetric failure — Patch 1 anchor hard-failed, Patch 2 anchor soft-warned and continued. Both now hard-fail per Phase 5 SC3 rule. Data-corruption-risk rationale: a silently-skipped Patch 2 means Patch-1-uploaded files cannot be added to KBs.

**Idempotency marker:** `FIX_SKIP_EMBEDDING_CHAT_FILES` added alongside existing `skip_processing_chat_files`.

**Build evidence:** `grep "PATCHED: fix_skip_embedding_chat_files applied successfully" /tmp/phase6-build.log` → 1 match (line 103).

**Dockerfile change:** line 37 uncommented in Task 1 of 06-02.

### Patch 8: fix_skip_rag_files_native_fc.py — OWUI-BE-06 — rewrite+enabled (newly enabled)

**v0.9.1 anchor changes applied:** SEARCH literal byte-identical (line drift +86). No regex change needed.

**Fail-loud conversion:** rerouted stdout `ERROR:` to stderr; explicit `sys.exit(1)` added.

**Filename vs marker mismatch (documented, not renamed):** filename says `native_fc` but `PATCH_MARKER = "skip_rag_files_ai_computer_use"` inside the patch. **Decision:** keep as-is. Rationale: renaming the file churns Dockerfile line, git history, and test references for zero functional gain. Future cleanup opportunity in a docs-only phase.

**Idempotency marker:** `FIX_SKIP_RAG_FILES_NATIVE_FC` added alongside existing `skip_rag_files_ai_computer_use`.

**Build evidence:** `grep "PATCHED: fix_skip_rag_files_native_fc applied successfully" /tmp/phase6-build.log` → 1 match (line 113).

**Dockerfile change:** line 41 uncommented in Task 1 of 06-02.

## Cross-Phase Evidence

- **Fixtures:** `tests/patches/fixtures/middleware_v0.9.1.py` + `retrieval_v0.9.1.py`, extracted byte-identical from `~/src/open-webui-upstream` at tag v0.9.1 (rev 0a8a620fb6fd4c914494f56ac06475bd5f95a985).
- **Build log:** `/tmp/phase6-build.log` (retained, not committed) — 8 `PATCHED:` lines, 0 `ERROR:` lines. Build command: `DOCKER_CONFIG=/tmp/docker-cfg DOCKER_HOST=unix:///Users/nick/.docker/run/docker.sock docker build --platform linux/amd64 --build-arg OPENWEBUI_VERSION=0.9.1 -f openwebui/Dockerfile -t open-computer-use:0.9.1-test openwebui/`.
- **Pytest log:** `/tmp/phase6-pytest.log` — 229 passed, 0 failed, 0 errors. Run inside `python:3.13-slim` container with `pip install -q pytest pytest-asyncio -r computer-use-server/requirements.txt`.
- **Image:** `open-computer-use:0.9.1-test` rebuilt with `--build-arg OPENWEBUI_VERSION=0.9.1` — 4.75 GB.

## Out of Scope (for Phase 7)

- `ARG OPENWEBUI_VERSION=0.8.12` default bump → 0.9.1 in `openwebui/Dockerfile`.
- `OPENWEBUI_VERSION=0.9.1` default in `docker-compose.webui.yml`.
- `CHANGELOG.md` release entry v0.9.1.0.
- Image retagging to `open-computer-use:latest`.

## Requirement Status (to be flipped by 06-01 Task 1 write-back in 06-SUMMARY)

- OWUI-BE-01: Complete
- OWUI-BE-02: Complete
- OWUI-BE-03: Complete
- OWUI-BE-04: Complete
- OWUI-BE-05: Complete
- OWUI-BE-06: Complete

Flip the `- [ ]` to `- [x]` in REQUIREMENTS.md at phase close.

## VERDICT COMPLETE
