---
created: 2026-04-13T07:28:52.264Z
title: Add CI smoke tests for sandbox image and browser
area: testing
files:
  - .github/workflows/build.yml:131-142
  - tests/test-docker-image.sh
---

## Problem

CI `Test` job only runs `test-no-corporate.sh` and `test-project-structure.sh` — both lightweight repo-level checks. The main smoke test `tests/test-docker-image.sh` (which verifies npm/pip packages, CLI tools, Playwright install in the built image) is **not** wired into CI; it runs only manually on local builds.

This gap let PR #37 (Dependabot bump of npm `playwright` 1.57.0 → 1.59.1) land green even though the matching PyPI release did not exist yet (max on PyPI: 1.58.0). The mismatch was discovered only when a human rebuilt locally and `pip install playwright==1.59.1` failed. Same class of bug could hit any future Dependabot PR that touches runtime-shared pins.

There is also no runtime check that Chromium actually launches inside the built image. A smoke test (launch browser → goto example.com → assert title) would catch wire-protocol mismatches and missing browser binaries — things a pure `docker build` cannot detect.

## Solution

Two new CI jobs in `.github/workflows/build.yml`, both gating merge:

1. **`test-sandbox-image`** — depends on `build-sandbox`. Load the already-built image (either via registry pull or GHA cache/artifact), run `./tests/test-docker-image.sh` against it. Reuses existing asserts (packages, CLI tools, Playwright).

2. **`test-browser-smoke`** — depends on `build-sandbox`. Runs a minimal python-in-container script: `playwright.chromium.launch(headless=True) → page.goto("https://example.com") → assert "Example Domain" in page.title()`. Keeps the matrix small (Python-side only; trust npm-side via `test-sandbox-image`).

Open as a separate branch + dedicated PR (do not pile onto the sync-pin PR #47).

Optional stretch: add the same two jobs for the server image and the patched Open WebUI image, but start with sandbox only.
