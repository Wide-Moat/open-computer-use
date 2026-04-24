---
phase: 06-backend-patches
plan: 02
subsystem: openwebui/Dockerfile + image rebuild + verdict
tags: [openwebui, dockerfile, v0.9.1, patches, build, pytest, verdict]
dependency_graph:
  requires:
    - OWUI-BE-01..06 (6 backend patches rewritten + pytest-green by 06-01)
  provides:
    - "All 6 backend patches enabled in Dockerfile and applying successfully at build time"
    - "06-VERDICT.md — per-patch rewrite outcome for Phase 6"
    - "Rebuilt image open-computer-use:0.9.1-test with 8 patches (6 BE + 2 FE) applied"
  affects:
    - openwebui/Dockerfile
    - .planning/phases/06-backend-patches/06-VERDICT.md
tech_stack:
  added: []
  patterns:
    - "Docker multi-stage patch application (COPY patches/ → RUN python3 per patch → RUN rm -rf)"
    - "PATCHED:/ERROR: stdout/stderr markers as build-log forensic evidence"
    - "docker-compose.yml + Dockerfile ARG OPENWEBUI_VERSION (plumbing unchanged; default bump deferred to Phase 7)"
key_files:
  created:
    - .planning/phases/06-backend-patches/06-VERDICT.md
  modified:
    - openwebui/Dockerfile
decisions:
  - "Did NOT bump ARG OPENWEBUI_VERSION=0.8.12 default — Phase 7 owns that + docker-compose.webui.yml default + CHANGELOG release entry"
  - "Build used legacy docker builder (buildx not installed) — `--progress=plain` flag dropped; plain build log still captured all PATCHED markers"
  - "Pytest executed in python:3.13-slim container with `-r computer-use-server/requirements.txt` — installs fastapi/pydantic/mcp/docker required for orchestrator + filter + tools test modules"
  - "Planning-file commits use `git add -f` per dual-remote .gitignore convention; push to gitlab only"
metrics:
  duration: "~6 minutes (docker layer cache hot — only the 8 patch RUN steps plus the 5 tail COPY/RUN steps re-executed)"
  completed_date: "2026-04-24"
  tasks_completed: 4
  files_touched: 2
  image_size: "4.75 GB"
  build_log_lines: 143
  pytest_tests: 229
  pytest_duration: "4.39s"
---

# Phase 6 Plan 02: Enable Backend Patches + Rebuild + Verdict — Summary

Uncommented 4 backend patch RUN lines in `openwebui/Dockerfile`, rebuilt `open-computer-use:0.9.1-test` with `--build-arg OPENWEBUI_VERSION=0.9.1`, verified all 8 patches emitted `PATCHED:` markers, ran the full 229-test pytest suite green in a clean python:3.13-slim container, and authored `06-VERDICT.md` documenting each of the 6 backend patches as `rewrite+enabled`.

## What Was Done

### Task 1 — Dockerfile edit

Transformed the "Optional patches below - uncomment if needed:" block into "Enabled backend patches (rewritten for v0.9.1 in Phase 6):" with all 4 `# RUN python3 …` lines stripped of the comment prefix:

| Patch | Dockerfile line | Status before | Status after |
|-------|-----------------|---------------|--------------|
| fix_large_tool_args           | 29 | `# RUN python3 …` | `RUN python3 …` |
| fix_attached_files_position   | 33 | `# RUN python3 …` | `RUN python3 …` |
| fix_skip_embedding_chat_files | 37 | `# RUN python3 …` | `RUN python3 …` |
| fix_skip_rag_files_native_fc  | 41 | `# RUN python3 …` | `RUN python3 …` |

**Untouched:** `ARG OPENWEBUI_VERSION=0.8.12` (line 3) — Phase 7's job.

### Task 2 — Rebuild

Built on host docker context `desktop-linux` (needed explicit `DOCKER_HOST=unix:///Users/nick/.docker/run/docker.sock` because `DOCKER_CONFIG=/tmp/docker-cfg` reset the active context to `default`):

```
DOCKER_CONFIG=/tmp/docker-cfg DOCKER_HOST=unix:///Users/nick/.docker/run/docker.sock \
  docker build --platform linux/amd64 \
    --build-arg OPENWEBUI_VERSION=0.9.1 \
    -f openwebui/Dockerfile \
    -t open-computer-use:0.9.1-test \
    openwebui/ > /tmp/phase6-build.log 2>&1
# EXIT=0
```

**Build log evidence:**

```
Line  26: PATCHED: fix_artifacts_auto_show applied successfully.
Line  38: PATCHED: fix_tool_loop_errors applied successfully.
Line  64: PATCHED: fix_preview_url_detection applied successfully.
Line  74: PATCHED: fix_large_tool_results applied successfully.
Line  86: PATCHED: fix_large_tool_args applied successfully.
Line  93: PATCHED: fix_attached_files_position applied successfully.
Line 103: PATCHED: fix_skip_embedding_chat_files applied successfully.
Line 113: PATCHED: fix_skip_rag_files_native_fc applied successfully.
```

- 8 PATCHED lines, 0 ERROR lines, 19/19 build steps successful.
- Image: `open-computer-use:0.9.1-test` — 4.75 GB.

### Task 3 — Full-repo pytest

```
docker run --rm --platform linux/amd64 \
  -v "$(pwd):/work" -w /work python:3.13-slim \
  bash -c "pip install -q pytest pytest-asyncio -r computer-use-server/requirements.txt \
           && python -m pytest tests/ -v"
# => 229 passed, 6 warnings in 4.39s (EXIT=0)
```

**Per-patch test counts:**

| Patch test file | PASSED count |
|-----------------|--------------|
| test_fix_tool_loop_errors           | 3 |
| test_fix_large_tool_results         | 15 |
| test_fix_large_tool_args            | 4 |
| test_fix_attached_files_position    | 3 |
| test_fix_skip_embedding_chat_files  | 3 |
| test_fix_skip_rag_files_native_fc   | 3 |

All meet or exceed plan thresholds (≥3 / ≥5 / ≥4 / ≥3 / ≥3 / ≥3).

**Deviation:** The plan's verify-command template said "fall back to `pip install -q pytest`". That proved insufficient — tests under `tests/orchestrator/`, `tests/security/`, `tests/test_filter.py`, and `tests/test_tools.py` import `computer-use-server/app.py` / `docker_manager.py` / `mcp_tools.py` / openwebui filter + tool modules which require `fastapi`, `pydantic`, `aiohttp`, `docker`, `mcp`, `python-multipart`, `uvicorn` at collection time. The fix was `pip install -r computer-use-server/requirements.txt` (which already lists these precisely). This is consistent with the plan's explicit guidance: "grep `import` at top of tests/... for third-party deps; add them to the `pip install` line as needed." No source changes required.

### Task 4 — 06-VERDICT.md

Authored `.planning/phases/06-backend-patches/06-VERDICT.md` with:
- Summary verdict table (all 6 = rewrite+enabled; zero dropped).
- Per-patch section for patches 3–8 covering: v0.9.1 anchor changes, fail-loud conversion, idempotency marker, test coverage, build-log evidence line number, and Dockerfile change note.
- Cross-phase evidence block pointing at `/tmp/phase6-build.log`, `/tmp/phase6-pytest.log`, and fixture provenance.
- Phase 7 out-of-scope list (ARG default bump, docker-compose default, CHANGELOG release entry, `:latest` retag).
- Requirement status list (OWUI-BE-01..06 all Complete; flip to `[x]` in REQUIREMENTS.md at 06-SUMMARY rollup).

## Deviations from Plan

**1. [Rule 3 — Blocking] Docker build invocation required `DOCKER_HOST` override.**
- Found during: Task 2.
- Issue: `DOCKER_CONFIG=/tmp/docker-cfg docker build …` (as specified by plan + 05-01) hit `Cannot connect to the Docker daemon at unix:///var/run/docker.sock`. Setting `DOCKER_CONFIG` alone reset the context to `default` (socket at `/var/run/docker.sock`), bypassing Docker Desktop's socket at `/Users/nick/.docker/run/docker.sock`.
- Fix: add `DOCKER_HOST=unix:///Users/nick/.docker/run/docker.sock` to the build invocation.
- Files modified: none (invocation-only workaround).
- Commit: (none).

**2. [Rule 3 — Blocking] Build command required `--progress=plain` removal.**
- Found during: Task 2.
- Issue: host has only the legacy docker builder (`buildx` not installed); `--progress=plain` is a buildx flag and caused `unknown flag`.
- Fix: dropped `--progress=plain`. Legacy-builder output includes every Step and every PATCHED line — sufficient for forensic evidence.
- Files modified: none.
- Commit: (none).

**3. [Rule 3 — Blocking] Pytest container needed `computer-use-server/requirements.txt` install.**
- Found during: Task 3.
- Issue: bare `pip install -q pytest` left 12 test files un-collectable due to 3rd-party module imports in project code.
- Fix: added `-r computer-use-server/requirements.txt` to the install step (already the project's orchestrator requirements file — 8 deps including fastapi, pydantic, mcp, docker). No project-source changes; this is purely the test environment bootstrap.
- Files modified: none.
- Commit: (none).

None of these 3 are source-code deviations — they are command-line invocation adjustments documented here for future reproducibility.

## Files & Commits

| Commit | What |
|--------|------|
| `3818182` | Task 1 — Dockerfile: 4 backend patch RUN lines uncommented + header comment updated (also swept pre-staged .planning/REQUIREMENTS.md + .planning/ROADMAP.md + .planning/STATE.md updates into the same commit from the prior session's index) |
| `f69f9db` | Task 4 — 06-VERDICT.md added (force-added due to dual-remote .gitignore convention) |

## Boundary Verification

- `ARG OPENWEBUI_VERSION=0.8.12` unchanged (Phase 7 bumps).
- `docker-compose.webui.yml` unchanged (Phase 7).
- `CHANGELOG.md` unchanged (Phase 7 adds v0.9.1.0 entry).
- `REQUIREMENTS.md` unchanged in this plan (06-01 already set all 6 OWUI-BE-0X statuses).
- No new Cyrillic: `grep -rP '[\x{0400}-\x{04FF}]' openwebui/Dockerfile .planning/phases/06-backend-patches/06-VERDICT.md` empty.
- English-only: pass.

## Phase 6 End-to-End Verification

1. ✅ `grep -c '^RUN python3 /tmp/patches/fix_' openwebui/Dockerfile` → 8 (all 6 backend + 2 frontend active).
2. ✅ `grep -c '^# RUN python3 /tmp/patches/fix_' openwebui/Dockerfile` → 0.
3. ✅ `grep -c '^ARG OPENWEBUI_VERSION=0.8.12' openwebui/Dockerfile` → 1.
4. ✅ `grep -c 'PATCHED: fix_.* applied successfully' /tmp/phase6-build.log` → 8.
5. ✅ `grep -c 'ERROR:' /tmp/phase6-build.log` → 0.
6. ✅ `docker images open-computer-use:0.9.1-test` present (4.75 GB).
7. ✅ `grep -c ' FAILED' /tmp/phase6-pytest.log` → 0; `grep -c ' ERROR' /tmp/phase6-pytest.log` → 0; 229 passed.
8. ✅ `test -f .planning/phases/06-backend-patches/06-VERDICT.md` exit 0.
9. ✅ All 6 patches classified `rewrite+enabled` (13 occurrences in VERDICT.md).
10. ✅ Zero patches dropped / obsoleted.

**ROADMAP Phase 6 SC1 (all 6 patches verdicted), SC2 (rewritten+enabled active), SC4 (pytest green) met. SC3 (verified-dropped drops clearly labelled) vacuously satisfied — no drops.**

## Self-Check: PASSED

- `openwebui/Dockerfile` modified — verified via `git log --stat` on 3818182.
- `.planning/phases/06-backend-patches/06-VERDICT.md` exists (127 lines, 127 insertions in f69f9db).
- Commit `3818182` present in `git log --oneline --all`.
- Commit `f69f9db` present in `git log --oneline --all`.
- Image `open-computer-use:0.9.1-test` present.
- Build log `/tmp/phase6-build.log` retained (143 lines, 8 PATCHED, 0 ERROR).
- Pytest log `/tmp/phase6-pytest.log` retained (229 passed, 0 failed, 0 error).
