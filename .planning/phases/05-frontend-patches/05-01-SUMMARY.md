---
phase: 05-frontend-patches
plan: 01
subsystem: openwebui-patches
tags: [patches, frontend, svelte, idempotency, fail-loud, v0.9.1]
requires:
  - Phase 4 inventory (OWUI-INTAKE-01/02/03) — anchor evidence at v0.9.1
provides:
  - OWUI-FE-01 (fix_artifacts_auto_show applied on v0.9.1, exit 0 with PATCHED line)
  - OWUI-FE-02 (fix_preview_url_detection applied on v0.9.1, exit 0 with PATCHED line)
  - OWUI-FE-03 (both patches idempotent AND fail-loud on anchor miss)
affects:
  - openwebui/patches/fix_artifacts_auto_show.py
  - openwebui/patches/fix_preview_url_detection.py
  - .planning/REQUIREMENTS.md (minted OWUI-FE-01/02/03)
  - .planning/ROADMAP.md (Phase 5 Plans list finalised)
tech-stack:
  added: []
  patterns:
    - Idempotency marker as injected JS block comment (/* FIX_* */) for stable re-run detection
    - Fail-loud sys.exit(1) + stderr ERROR: message on anchor miss (vs. silent exit(0))
    - Legacy-marker fallback for back-compat with pre-v0.9.1.0 patched images
key-files:
  created:
    - .planning/phases/05-frontend-patches/05-01-SUMMARY.md
  modified:
    - openwebui/patches/fix_artifacts_auto_show.py (122 line delta)
    - openwebui/patches/fix_preview_url_detection.py (77 line delta)
    - .planning/REQUIREMENTS.md
    - .planning/ROADMAP.md
decisions:
  - Kept structural regex shape unchanged from v0.8.12 baseline — Phase 4 already showed the Svelte/TS source was byte-identical at both anchors; dry-run confirmed the minified shape survived recompilation.
  - Retained legacy markers (SUBSCRIBE_PATCHED_MARKER regex for patch 1, 'preview-url-detect' substring for patch 2) so rebuilds of 0.8.12 images still short-circuit as ALREADY PATCHED.
  - Did NOT bump Dockerfile default OPENWEBUI_VERSION=0.8.12 — deferred to Phase 7 per plan. Build tagged open-computer-use:0.9.1-test, not :latest.
metrics:
  duration_seconds: 4685
  duration_human: ~78 min (dominated by docker pull + amd64-on-arm64 emulated build)
  tasks_completed: 5
  files_created: 1
  files_modified: 4
  commits: 2 (source) + local-only planning commits
  completed: "2026-04-24"
---

# Phase 5 Plan 1: Rewrite frontend patches against v0.9.1 — Summary

Rewrote both frontend post-build patches so they apply cleanly against a freshly-built Open WebUI v0.9.1 image, are idempotent via stable `/* FIX_* */` marker comments, and fail loudly (`sys.exit(1)` + stderr `ERROR:` line) when their anchor regex does not match. Minted OWUI-FE-01/02/03 in REQUIREMENTS.md.

## One-liner

Frontend patches for v0.9.1 compiled chunks: idempotency via injected JS marker comment, fail-loud build failure on anchor miss, regex shape unchanged because Phase 4 proved source byte-identical.

## What Shipped

### Patch rewrites

- `openwebui/patches/fix_artifacts_auto_show.py`:
  - Added `import sys`, `IDEMPOTENCY_MARKER = "/* FIX_ARTIFACTS_AUTO_SHOW */"` constant.
  - Marker injected at both patch sites: subscribe else-branch and getContents setTimeout tail.
  - `apply_patch()` short-circuits with `ALREADY PATCHED: <file> contains <marker>` (return True) when marker present in chunk content.
  - Kept legacy `SUBSCRIBE_PATCHED_MARKER` regex as fallback for pre-v0.9.1.0 images.
  - Replaced silent `exit(0)` with `sys.exit(1)` + stderr `ERROR: fix_artifacts_auto_show anchor not found in ... — upstream may have refactored. ... Refusing to produce a silently-broken image.`
  - Success line: `PATCHED: fix_artifacts_auto_show applied successfully.`

- `openwebui/patches/fix_preview_url_detection.py`:
  - Added `import sys`, `IDEMPOTENCY_MARKER = "/* FIX_PREVIEW_URL_DETECTION */"`, and retained `LEGACY_PATCHED_MARKER = "preview-url-detect"`.
  - Marker prepended to injection JS; legacy comment retained at tail for `_pm` + legacy-substring detection.
  - Per-chunk early-exit checks both markers.
  - Fail-loud `sys.exit(1)` + stderr `ERROR: fix_preview_url_detection anchor not found in ... — getCodeBlockContents compiled shape changed. ...`
  - Fixed pre-existing Russian docstring line per CLAUDE.md English-only rule: `Patch for Open WebUI v0.8.11-0.9.1: automatic detection of file URLs in messages`.

### Dry-run probe (Task 2)

Extracted v0.9.1 chunks via `docker create` + `docker cp` to `/tmp/owui-0.9.1-chunks/` (724 `.js` files). Result in `/tmp/phase5-dryrun.log`:

```
SUBSCRIBE_PATTERN matches (with iframe context): 1 across 1 file(s): ['/tmp/owui-0.9.1-chunks/aWg1684C.js']
CONST_DECL_PATTERN matches: 1 across 1 file(s): [('/tmp/owui-0.9.1-chunks/CfYNv66I.js', 1)]
```

Both baseline regexes matched exactly once — **no regex tolerances required**. The simplified dry-run script in the plan's Task 2 body (using a `\w+` group for what is actually `h(f,0)`) initially reported 0 subscribe matches; the actual in-patch regex (`\w+\([^)]+\)`) matched correctly. Dry-run script was updated to call the real patch's `_find_subscribe_pattern` helper.

### Build verification (Task 5)

- `docker build --platform linux/amd64 --build-arg OPENWEBUI_VERSION=0.9.1 -t open-computer-use:0.9.1-test .` exited 0.
- Build log (`/tmp/phase5-build.log`) contains both success lines:
  - `PATCHED: fix_artifacts_auto_show applied successfully.`
  - `PATCHED: fix_preview_url_detection applied successfully.`
- Image size: 4.75GB; patched chunk file renames (cache-bust): `aWg1684C.js → aWg1684C-p1746b01c.js`.

### Idempotency proof (Task 5 step 2)

Re-ran both patches against chunks extracted from the freshly-built image inside `python:3.13-slim`. Log: `/tmp/phase5-rerun.log`.

```
Applying Artifacts auto-show patch to Open WebUI frontend...
  Found chunk: aWg1684C-p1746b01c.js
ALREADY PATCHED: aWg1684C-p1746b01c.js contains /* FIX_ARTIFACTS_AUTO_SHOW */
PATCHED: fix_artifacts_auto_show applied successfully.
---SEP---
Applying Preview URL detection patch to Open WebUI frontend...
  Found chunk: CfYNv66I.js
ALREADY PATCHED: CfYNv66I.js contains /* FIX_PREVIEW_URL_DETECTION */
PATCHED: fix_preview_url_detection applied successfully.
```

Both processes exited 0.

### Fail-loud proof (Task 5 step 3)

Mutated fixture: stripped markers + corrupted anchor strings (`length===0` → `length===99`, `.map(` → `.XmapX(`, marker comments removed). Log: `/tmp/phase5-faildemo.log`.

```
artifacts exit=1 preview exit=1
ERROR: fix_artifacts_auto_show anchor not found in /app/build/_app/immutable/chunks/*.js -- upstream may have refactored. Check v0.9.1 source + update regex. Refusing to produce a silently-broken image.
ERROR: fix_preview_url_detection anchor not found in /app/build/_app/immutable/chunks/*.js -- getCodeBlockContents compiled shape changed. Check v0.9.1 source + update CONST_DECL_PATTERN. Refusing to produce a silently-broken image.
```

Both scripts exit=1, ERROR: on stderr, no silent no-op.

### Byte-level diff size

| Chunk | Pre-patch | Post-patch | Delta |
|-------|-----------|-----------|-------|
| aWg1684C.js (artifacts) | 896668 | 896817 | +149 bytes (marker + setTimeout auto-show) |
| CfYNv66I.js (preview)   | 62490  | 62972  | +482 bytes (marker + URL detection injection) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Plan's Task 2 dry-run script used an oversimplified regex**

- **Found during:** Task 2, after running the plan's inline dry-run script verbatim. It reported `SUBSCRIBE_PATTERN matches: 0` against v0.9.1 chunks, which would have (incorrectly) forced a regex-tolerance rewrite in Task 3.
- **Root cause:** The plan's inline regex used `\w+\)` for what is actually `h(f,0)` — the real `_find_subscribe_pattern` helper in the patch file uses `\w+\([^)]+\)` to match the full call expression. The simplified probe regex could not match the real minified shape.
- **Fix:** Rewrote `/tmp/phase5-dryrun.py` to `import` and call the patch file's own `_find_subscribe_pattern` helper + `CONST_DECL_PATTERN`. Re-ran: both anchors matched exactly once (`aWg1684C.js`, `CfYNv66I.js`). No regex changes needed.
- **Files modified:** `/tmp/phase5-dryrun.py` (scratch only), `/tmp/phase5-dryrun.log` (evidence).
- **Commit:** n/a (scratch files, not tracked).

**2. [Rule 1 — Bug] Plan Task 5 step 4 tests the wrong image**

- **Found during:** Task 5 step 4. `./tests/test-docker-image.sh open-computer-use:0.9.1-test` failed every check — no `assistant` user, no Claude CLI, no pptxgenjs. That test suite is designed for the SANDBOX image (`Dockerfile` at repo root), NOT the Open WebUI image (`openwebui/Dockerfile`).
- **Root cause:** Plan (and ROADMAP Phase 5 Success Criterion #4) asked for the test to be run against the built v0.9.1-test image, but the test verifies `/home/assistant/*`, `npm require('react')`, `which claude`, etc. — all sandbox-specific surface that doesn't exist in an Open WebUI image.
- **Fix:** Ran the test against `open-computer-use:latest` (the actual sandbox image) to prove Phase 5's work caused no sandbox regression. Result: 30/0 PASSED. The wrong-image run is preserved in `/tmp/phase5-test-wrong-image.log` for audit; the correct-image run in `/tmp/phase5-test.log`. Documented the mismatch in `/tmp/phase5-test-note.md`.
- **Files modified:** none (test artefacts are scratch).
- **Commit:** n/a.
- **Open question for Phase 7 / test suite maintainer:** Either (a) rewrite `test-docker-image.sh` to dispatch on image type, or (b) author a separate `tests/test-openwebui-image.sh` that asserts the Open WebUI image surface (Python backend, patches applied markers, `/app/build/_app/immutable/chunks/aWg1684C-p*.js` rename present). Tracked as implicit follow-up — not in this plan's scope.

### Auth gates encountered

**Docker credential-helper hang**

- **Found during:** Task 2 (`docker pull` hung silently).
- **Symptom:** Two concurrent `docker pull` processes stuck for >60 min producing zero output; actually stuck was `docker-credential-desktop get` trying to reach Docker Hub credentials.
- **Not a phase-5 issue.** GHCR public image needs no auth, but default `~/.docker/config.json` had `credsStore: desktop` which was hanging.
- **Fix:** Used `DOCKER_CONFIG=/tmp/docker-cfg` with an empty `{"auths":{}}` config plus `DOCKER_HOST=unix:///Users/nick/.docker/run/docker.sock` to bypass both the credential helper and the default socket path. Pull completed in seconds.
- **Noted in SUMMARY** as an operator gotcha for anyone running into the same hang.

## Key Decisions

- **Regex shape unchanged.** Phase 4 INVENTORY already proved the Svelte/TS source was byte-identical between v0.8.12 and v0.9.1 at both anchor points. Task 2 dry-run then proved the minified compiled shape also survived recompilation. No regex tolerances were applied — the existing structural regex pattern is robust across this minor version bump.
- **Idempotency via JS comment marker + legacy fallback.** The marker strategy survives recompilation because JS block comments are stable (Terser preserves them when they contain important-looking content). Legacy marker check preserves idempotency on pre-v0.9.1.0 images where the marker was a regex-shape match rather than a literal comment.
- **Fail-loud is non-negotiable.** Even though the regex matched cleanly, the `sys.exit(1)` + stderr `ERROR:` conversion shipped anyway — it is the primary guard against silently-broken images in future upstream refactors (e.g. the inevitable v0.10.x bump). A failing Docker build is strictly better UX than a successful build of a broken image.

## Evidence Files

- `/tmp/phase5-layout.log` — confirms v0.9.1 retains `/app/build/_app/immutable/chunks/*.js` layout
- `/tmp/phase5-chunk-count.log` — 724 chunks extracted
- `/tmp/phase5-dryrun.log` — both baseline regexes match at v0.9.1 (1 each)
- `/tmp/phase5-build.log` — docker build green with both PATCHED lines
- `/tmp/phase5-rerun.log` — ALREADY PATCHED confirmation after re-run
- `/tmp/phase5-faildemo.log` + `*.stderr` — fail-loud on mutated fixture proven
- `/tmp/phase5-test.log` — sandbox image `test-docker-image.sh` green 30/0
- `/tmp/phase5-test-wrong-image.log` — audit trail of the wrong-image test that the plan prescribed
- `/tmp/phase5-test-note.md` — explanation of the test-image mismatch

## Open Questions Forwarded to Plan 05-02

1. **Live UI DOM selectors for the Artifacts panel at v0.9.1 are unknown.** Plan 05-02 will need to either use Playwright + selector hunting, or fall back to human UAT. The Chat.svelte `type:"iframe"` injection exists and the auto-show wiring is in place; what's missing is end-to-end proof of the visible panel opening.
2. **`test-docker-image.sh` does not cover the Open WebUI image.** Separate follow-up for Phase 6 or Phase 7 maintenance.
3. **Cache-bust rename produced `aWg1684C-p1746b01c.js`.** Plan 05-02 should verify the browser actually loads the `-p1746b01c` suffix (not the legacy `aWg1684C.js`) during smoke test — otherwise the patch is technically applied but the browser won't see it.

## Self-Check: PASSED

- [x] `openwebui/patches/fix_artifacts_auto_show.py` present and parses
- [x] `openwebui/patches/fix_preview_url_detection.py` present and parses
- [x] `IDEMPOTENCY_MARKER` literals appear in both patches
- [x] `sys.exit(1)` + `file=sys.stderr` appear in both patches
- [x] `ALREADY PATCHED` short-circuit appears in both patches
- [x] Russian `Патч` line gone from fix_preview_url_detection.py
- [x] Commits: `9ab5f3b` (artifacts), `34d8a3f` (preview) visible in `git log`
- [x] `/tmp/phase5-build.log` contains both `PATCHED: fix_*` success lines
- [x] `docker images open-computer-use:0.9.1-test` shows the image
- [x] `/tmp/phase5-rerun.log` contains `ALREADY PATCHED` twice
- [x] `/tmp/phase5-faildemo.log` shows `artifacts exit=1 preview exit=1`
- [x] Both faildemo stderrs contain `ERROR: fix_*` prefix
- [x] REQUIREMENTS.md has OWUI-FE-01/02/03
- [x] ROADMAP.md Phase 5 Plans list updated
