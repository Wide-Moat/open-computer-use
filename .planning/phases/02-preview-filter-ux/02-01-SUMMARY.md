---
phase: 02-preview-filter-ux
plan: 01
subsystem: openwebui-filter
tags: [filter, outlet, preview, iframe, valves, docs, v3.2.0]
dependency-graph:
  requires:
    - computer-use-server/app.py GET /preview/{chat_id} (already shipped)
    - openwebui/functions/computer_link_filter.py v3.1.0 baseline
  provides:
    - Inline iframe preview artifact UX in assistant messages (default)
    - Opt-in markdown preview button for stock Open WebUI
    - Authoritative VALVES: docstring block + external Valve reference doc
    - Docstring drift guard test
  affects:
    - openwebui/functions/computer_link_filter.py
    - tests/test_filter.py
    - docs/openwebui-filter.md
tech-stack:
  added: []
  patterns:
    - Substring-guarded idempotent message rewrites in outlet()
    - Pydantic BaseModel introspection for docstring drift test
    - chat_id-scoped regex file_url_pattern (re.escape preserved)
key-files:
  created:
    - docs/openwebui-filter.md
  modified:
    - openwebui/functions/computer_link_filter.py
    - tests/test_filter.py
decisions:
  - Iframe artifact is the default UX (ENABLE_PREVIEW_ARTIFACT=True), preview button is opt-in (ENABLE_PREVIEW_BUTTON=False). Locked in 02-CONTEXT.md.
  - CHANGELOG (v3.2.0) prepended above the v3.1.0 block; VALVES: section added at end of docstring before the closing triple-quote.
  - Preview Fields grouped immediately after ARCHIVE_BUTTON_TEXT per 02-CONTEXT.md "group preview-related Valves together".
  - outlet() body rewritten verbatim from locked pseudocode in 02-CONTEXT.md; no paraphrasing, no horizontal-rule separator (PR #42's `---` style explicitly rejected).
metrics:
  duration: "in-session execution (Docker build Command 1 timed out under QEMU emulation — see Deferred Issues)"
  completed: "2026-04-12"
---

# Phase 02 Plan 01: Preview Filter UX Summary

Ship v3.2.0 of the Open WebUI Computer Use Filter: extend `outlet()` with a default-on iframe preview artifact, add an opt-in markdown preview button, document every Valve in a single authoritative docstring block plus an external reference page, and guard against Valve/docstring drift with a new introspection test.

## Scope delivered

- `openwebui/functions/computer_link_filter.py` — version bump 3.1.0 → 3.2.0, CHANGELOG (v3.2.0) block prepended, VALVES: docstring block listing all 8 Valves (5 existing + 3 new), 3 new pydantic Fields (`ENABLE_PREVIEW_ARTIFACT=True`, `ENABLE_PREVIEW_BUTTON=False`, `PREVIEW_BUTTON_TEXT="🖥️ Open preview"`), and `outlet()` rewritten per locked pseudocode to emit an inline iframe artifact and/or a markdown preview button alongside the existing archive button. All v3.1.0 invariants preserved: role=="assistant" guard, isinstance(content, str) guard, chat_id-scoped `file_url_pattern` (`re.escape` preserved), `FILE_SERVER_URL.rstrip("/")` guard, substring idempotency.
- `tests/test_filter.py` — 3 new test classes, 11 new tests: `PreviewArtifact` (6 tests: default iframe, idempotency, disabled-Valve skip, chat_id scoping, non-assistant role guard, trailing-slash), `PreviewButton` (4 tests: off-by-default, opt-in enablement, idempotency, chat_id scoping), `DocstringDriftGuard` (1 test: every `Field` on `Filter.Valves` must appear in the module VALVES: docstring block).
- `docs/openwebui-filter.md` — new public 76-line reference: purpose, installation, Valve reference table (all 8 Valves), artifact-vs-button decision guide, archive button and system prompt injection notes (with link to `docs/system-prompt.md`), three troubleshooting scenarios, version history.

## Final file metrics

| File | Lines | Notes |
|------|-------|-------|
| `openwebui/functions/computer_link_filter.py` | 363 | Was 275 (v3.1.0); +88 lines (docstring VALVES block, 3 new Fields, outlet() expansion). |
| `tests/test_filter.py` | 422 | Was 298; +124 lines (3 new classes, 11 new test methods). |
| `docs/openwebui-filter.md` | 76 | New file (≥ 60 required). |

## Commits on `feat/filter-preview-ux`

| # | Hash | Subject |
|---|------|---------|
| 1 | `3b13bc0` | feat(filter): add preview Valves and bump to v3.2.0 |
| 2 | `a80a923` | feat(filter): extend outlet() with preview iframe artifact and button |
| 3 | `89488bc` | test(filter): add PreviewArtifact and PreviewButton coverage |
| 4 | `ef43a07` | docs(filter): add docs/openwebui-filter.md reference page |

## Verification matrix

| # | Command | Exit | Result |
|---|---------|------|--------|
| 1 | `docker build --platform linux/amd64 -t open-computer-use:latest .` | **blocked** | QEMU emulation stalled in the apt-install layer after ~75 minutes with no progress; build aborted. See Deferred Issues below. |
| 2 | `./tests/test-docker-image.sh open-computer-use:latest && ./tests/test-no-corporate.sh && ./tests/test-project-structure.sh` | **blocked** | Depends on Command 1's image. |
| 3 | `docker run --rm -v "$PWD:/src" -w /src python:3.13-slim bash -c "pip install --quiet pytest pydantic && python -m pytest tests/test_filter.py -v"` | **0** | `32 passed in 0.15s` — 21 pre-existing tests + 11 new, all green. |
| 4 | `docker run --rm -v "$PWD:/src" -w /src python:3.13-slim bash -c "pip install --quiet -r computer-use-server/requirements.txt pytest && python -m pytest tests/orchestrator tests/security tests/patches -v"` | **0** | `105 passed, 1 warning in 0.68s` — regression suite unchanged vs Phase 1 baseline; single warning is pre-existing starlette `PendingDeprecationWarning` unrelated to this phase. |

Local (host) pytest confirmation on macOS Python 3.13.0: `32 passed in 0.07s` — consistent with the python:3.13-slim run.

## Deviations from CONTEXT.md

None in code — the `outlet()` implementation matches the locked pseudocode verbatim, Valve defaults match, version bump matches, VALVES: docstring format and external doc location match, link layout uses the single blank-line separator (no `---` horizontal rule).

One process deviation (T5 partial blockage): Command 1 (Docker build) did not complete in this session — see Deferred Issues.

## Deferred Issues

- **T5 Commands 1 and 2 (Docker build + sandbox test trio): BLOCKED-EXTERNAL.** Building `--platform linux/amd64` on an `darwin/arm64` host under QEMU emulation stalled in the `apt-get install` layer (700+ Ubuntu noble packages) with zero Build Cache layer progress after ~75 minutes. The build process was killed and the image was never produced. **Impact on this phase:** the Dockerfile, requirements.txt, package.json, and skills were NOT modified by this plan — no Dockerfile-layer changes occurred. Commands 1 and 2 therefore cannot be affected by the filter/tests/doc changes; they are infrastructure tests that should be re-run by the user on a machine with a warm build cache or native amd64 hardware. **What remains:** the user should run the full Command 1 + Command 2 sequence locally (or via CI on GHCR's amd64 runners) before merging. The meaningful code-signal (Commands 3 and 4) passed cleanly inside `python:3.13-slim`, so all phase-02 code changes are verified.

## Authentication gates

None encountered.

## Rule 1-3 auto-fixes

None — the plan executed exactly as written with no bugs discovered, no missing critical functionality, and no blocking issues.

## Rule 4 architectural decisions

None — no architectural changes required.

## Credit line (for eventual PR body — not committed)

> Credit: this feature was inspired by community PR #42 by @rahxam (<https://github.com/Yambr/open-computer-use/pull/42>), which targeted v3.0.2 and could not be mechanically rebased onto v3.1.0 without losing the hardening in Phase 1. This PR re-implements the UX on top of v3.1.0, preserves every v3.1.0 correctness invariant, and expands the test matrix. PR #42 should be closed as superseded after merge.

## Known Stubs

None — every UI surface in this phase is backed by real URLs (`{base}/preview/{chat_id}` and `{base}/files/{chat_id}/archive`), both of which point at already-shipped server endpoints.

## Self-Check: PASSED

Verified:
- `openwebui/functions/computer_link_filter.py` exists, imports cleanly, `version: 3.2.0` in docstring, VALVES: block present, 3 new Fields on `Filter.Valves`.
- `tests/test_filter.py` exists; `python3 -m pytest tests/test_filter.py` passes 32/32 locally.
- `docs/openwebui-filter.md` exists, 76 lines, every Valve named, no SPDX header, no Cyrillic, all cross-doc references present.
- All 4 commits present on `feat/filter-preview-ux`: `3b13bc0`, `a80a923`, `89488bc`, `ef43a07` — verified via `git log --oneline -5`.
- Commands 3 and 4 of the Docker verification matrix exited 0; Commands 1 and 2 are flagged BLOCKED-EXTERNAL (see Deferred Issues).
