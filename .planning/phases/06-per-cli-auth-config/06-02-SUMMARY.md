---
phase: 06-per-cli-auth-config
plan: 02
subsystem: sandbox-image
tags: [dockerfile, npm-global, codex, opencode, version-pin]
requires: [phase-05-sub-agent-claude-compat]
provides: [codex-cli-in-image, opencode-cli-in-image, version-pinned-cli-tier]
affects: [Dockerfile]
tech_added:
  - "@openai/codex@0.125.0 (npm global)"
  - "opencode-ai@1.14.25 (sst fork, npm global)"
patterns:
  - "ARG <NAME>_VERSION=<pin> (mirrors CLAUDE_CODE_VERSION)"
  - "RUN sudo -u assistant bash -c \"npm install -g <pkg>@${ARG}\""
key_files:
  modified:
    - Dockerfile
decisions:
  - "Pin to specific versions (0.125.0, 1.14.25) per RESEARCH STACK.md / Pitfall 6 (CLI version drift)"
  - "Skip bun-wrapper for codex/opencode: they ship working native entry points; only claude-code 2.1.112 needs the wrapper because of its packaging"
  - "Keep all three CLI installs co-located after the claude-code line so the sub-agent runtime tier is visually grouped"
metrics:
  duration_minutes: 5
  tasks_completed: 2
  files_modified: 1
  completed: 2026-04-26
requirements_completed: [TEST-01]
---

# Phase 06 Plan 02: Dockerfile codex + opencode npm-global installs Summary

Pinned `@openai/codex@0.125.0` and `opencode-ai@1.14.25` (sst fork) into the sandbox image via `npm install -g`, mirroring the existing `@anthropic-ai/claude-code` install pattern; both land on `PATH` via the pre-existing `/usr/local/lib/node_modules_global/bin` prefix.

## What Was Built

Two surgical Dockerfile edits implementing TEST-01 (image-level CLI presence):

1. **ARG version pins** (Dockerfile:23, 28): `CODEX_VERSION=0.125.0` and `OPENCODE_VERSION=1.14.25` placed immediately after `ARG CLAUDE_CODE_VERSION=2.1.112`. Pin rationale per RESEARCH STACK.md and Pitfall 6 — version drift can break the adapter contract while tests stay green.
2. **RUN install steps** (Dockerfile:233, 237): two `RUN sudo -u assistant bash -c "npm install -g ..."` lines added immediately after the existing claude-code install (Dockerfile:228) and before the playwright-cli block (Dockerfile:241). Both reuse the npm-global prefix already configured at Dockerfile:178.

No bun-wrapper was added for the new CLIs. Only claude-code 2.1.112 needs the wrapper (pkg's cli.js + Bun runtime quirk, see Dockerfile:14-17 comment); codex and opencode ship native CLI entry points that work directly.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Add CODEX_VERSION and OPENCODE_VERSION ARGs | 2a03702 | Dockerfile (+10 lines) |
| 2 | Add npm install RUN steps for codex and opencode | 966b1ee | Dockerfile (+11/-1 lines) |

## Verification

All success criteria satisfied:

```
OK CODEX_VERSION   (grep ^ARG CODEX_VERSION=0.125.0$)
OK OPENCODE_VERSION (grep ^ARG OPENCODE_VERSION=1.14.25$)
OK codex install    (grep "npm install -g @openai/codex")
OK opencode-ai install (grep "npm install -g opencode-ai")
OK no anomalyco     (negative grep — wrong fork not used)
OK no opencode-cli  (negative grep — wrong package name not used)
CLAUDE_CODE_VERSION count: 1 (existing line preserved, not duplicated)
```

TEST-05 invariant (openwebui/init.sh byte-identical to v0.9.2.0 baseline):
```
PASS: openwebui/init.sh matches v0.9.2.0 baseline (sha256 31ce03b6...).
```

Phase 4 + 5 regression tests:
```
77 passed, 6 warnings in 0.38s
(test_cli_runtime.py + test_cli_adapters.py + test_subagent_claude_compat.py + test_docker_manager.py)
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Removed literal "opencode-cli" string from comment**
- **Found during:** Task 2 verification
- **Issue:** Plan asked for negative grep `! grep -q "opencode-cli" Dockerfile`, but the CONTEXT D1 ARG block comment contained "NOT opencode-cli" as a warning, which tripped the check.
- **Fix:** Reworded comment to "NOT the unrelated similarly-named package. See RESEARCH STACK.md for fork rationale." — keeps the warning intent while letting the negative grep guard pass.
- **Files modified:** Dockerfile (line 25)
- **Commit:** Folded into 2a03702 via amend would lose the per-task atomicity; instead the reword landed alongside Task 2's edits in 966b1ee.

Auth gates: none.

## Threat Flags

None — this plan changes only the build-time CLI inventory. The npm registry / GitHub Releases trust boundary was already in scope per the plan's `<threat_model>` (T-06-02-01 through T-06-02-05, all `accept` except T-06-02-05 which is mitigated by the pre-existing `sudo -u assistant` install pattern).

## Known Stubs

None. Both CLIs are real installs from upstream npm; image rebuild (Plan 06-05) will surface any registry/network problems.

## Out of Scope (deferred to later plans)

- Image rebuild + `--version` smoke test → Plan 06-05 (Wave 4) — gated to run once after entrypoint heredoc (06-03) and tests (06-04) are also in.
- Entrypoint config rendering for the new CLIs → Plan 06-03.
- Per-CLI auth tests → Plan 06-04.

## Self-Check: PASSED

- Files exist:
  - FOUND: Dockerfile (modified, contains all four required strings)
- Commits exist:
  - FOUND: 2a03702 (feat(06-02): pin codex and opencode CLI versions via ARG)
  - FOUND: 966b1ee (feat(06-02): install codex and opencode CLIs in sandbox image)
