---
phase: 06-per-cli-auth-config
plan: 03
subsystem: infra
tags: [dockerfile, entrypoint, heredoc, opencode, codex, auth, cli-runtime]

# Dependency graph
requires:
  - phase: 06-per-cli-auth-config
    provides: "Plan 06-02 added codex/opencode npm-global installs and CODEX_VERSION/OPENCODE_VERSION ARGs to the same Dockerfile entrypoint region this plan extends."
  - phase: 04-cli-runtime-resolver
    provides: "SUBAGENT_CLI env var contract — entrypoint dispatches on ${SUBAGENT_CLI:-claude}."
  - phase: 05-mcp-dispatch
    provides: "OPENCODE_PASSTHROUGH_ENVS / CODEX_PASSTHROUGH_ENVS allowlists — runtime env vars referenced by {env:VAR} substitution and ${OPENAI_BASE_URL} interpolation."
provides:
  - "Marker-gated per-CLI config render block inside /home/assistant/.entrypoint.sh"
  - "/tmp/opencode.json with OpenCode {env:VAR} substitution syntax (no plaintext secrets)"
  - "OPENCODE_CONFIG=/tmp/opencode.json export for interactive shells"
  - "~/.codex/config.toml with conditional [model_providers.custom] gateway block"
  - "/tmp/.cli-runtime-initialised sentinel (per-container ephemeral)"
affects: [06-04-verify, 06-05-image-rebuild, 07-ttyd-autostart]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Marker-gated bootstrap inside printf-emitted entrypoint script"
    - "Single-quoted heredoc (<<'OCEOF') to preserve OpenCode {env:VAR} verbatim"
    - "Unquoted heredoc (<<CXEOF) to interpolate ${OPENAI_BASE_URL} at script execution"
    - "Shell-escape pattern '\"'\"' for embedding single quotes inside printf format string"

key-files:
  created: []
  modified:
    - Dockerfile

key-decisions:
  - "Hardcode OpenCode model default to 'anthropic/claude-sonnet-4-6' inside JSON since single-quoted heredoc cannot expand ${OPENCODE_MODEL:-...} (OpenCode CLI itself reads OPENCODE_MODEL env at runtime to override)"
  - "Marker file at /tmp/.cli-runtime-initialised (NOT volume) — env-var change + container restart re-renders from scratch, distinct from openwebui/init.sh persistent marker"
  - "chown -R assistant:assistant /home/assistant/.codex needed because entrypoint runs as root"

patterns-established:
  - "Per-CLI dispatch via case ${SUBAGENT_CLI:-claude} in entrypoint — Phase 7 will mirror for autostart"
  - "Quoting policy: secret-bearing heredocs are single-quoted; URL/scalar-only heredocs are unquoted"

requirements-completed: [AUTH-02, AUTH-03, AUTH-04]

# Metrics
duration: 4min
completed: 2026-04-26
---

# Phase 06 Plan 03: Per-CLI auth config render Summary

**Marker-gated entrypoint heredoc renders /tmp/opencode.json with {env:VAR} substitution syntax and ~/.codex/config.toml with conditional gateway block — no plaintext secrets baked into image or runtime files.**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-04-26T01:49Z
- **Completed:** 2026-04-26T01:53:26Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments
- Per-CLI config block inserted inside the existing `RUN printf '#!/bin/bash...'` entrypoint script in Dockerfile, between the CLAUDE.md/settings.json copy lines and the autostart block.
- OpenCode case writes `/tmp/opencode.json` via single-quoted heredoc `<<'OCEOF'` (escaped as `'"'"'OCEOF'"'"'` inside the printf format string) so bash never expands `{env:OPENROUTER_API_KEY}` / `{env:OPENAI_API_KEY}` / `{env:ANTHROPIC_API_KEY}` — the file holds OpenCode substitution tokens verbatim, no secrets at rest.
- OpenCode case exports `OPENCODE_CONFIG=/tmp/opencode.json` for interactive shells (06-01 already injects the same var via container Env for `docker exec`-spawned subprocesses).
- Codex case conditionally writes `~/.codex/config.toml` via unquoted heredoc `<<CXEOF` so `${OPENAI_BASE_URL}` is interpolated at script execution time. When `OPENAI_BASE_URL` is unset, the file is truncated to empty (Codex falls back to public OpenAI defaults).
- `chown -R assistant:assistant /home/assistant/.codex` after the heredoc write so the assistant user can read the config when invoking `codex`.
- Whole block gated on `[ ! -f /tmp/.cli-runtime-initialised ]` — runs once per container lifetime; marker on `/tmp` ensures container restart re-renders.

## Task Commits

1. **Task 1: Insert marker-gated per-CLI config render** — `654c770` (feat)

## Files Created/Modified
- `Dockerfile` — Added 49-line block inside the entrypoint printf string (between line ~412 `cp .../settings.json` and line ~414 `# Auto-start claude on first interactive bash login`).

## Decisions Made
- **Hardcoded OpenCode model default in JSON** — CONTEXT D3 noted a self-contradiction: single-quoted heredoc cannot expand `${OPENCODE_MODEL:-anthropic/claude-sonnet-4-6}`, but unquoted heredoc would also expand `$OPENROUTER_API_KEY` (defeating the no-plaintext-secrets goal). Resolution: keep `'OCEOF'` quoting and bake `"anthropic/claude-sonnet-4-6"` as the literal default. OpenCode CLI itself reads `OPENCODE_MODEL` env at runtime to override.
- **No chown on `/tmp/opencode.json`** — `/tmp` is world-readable; root-owned file is fine for assistant-user reads.

## Deviations from Plan

None — plan executed exactly as written. The verbatim heredoc block from plan §"EXACT BLOCK TO INSERT" was inserted byte-for-byte at the prescribed insertion point.

## Issues Encountered
None.

## Verification Results

All automated checks passed:
- `grep -q "/tmp/.cli-runtime-initialised" Dockerfile` — OK
- `grep -q "/tmp/opencode.json" Dockerfile` — OK
- `grep -q "{env:OPENROUTER_API_KEY}" Dockerfile` / `{env:OPENAI_API_KEY}` / `{env:ANTHROPIC_API_KEY}` — OK (literal substitution syntax preserved by single-quoted heredoc)
- `grep -q "model_providers.custom" Dockerfile` — OK
- `grep -q "wire_api" Dockerfile` — OK
- `grep -q "OPENCODE_CONFIG=/tmp/opencode.json" Dockerfile` — OK
- `grep -q "chown -R assistant:assistant /home/assistant/.codex" Dockerfile` — OK
- `grep -q "<<CXEOF" Dockerfile` — OK
- Negative test `! grep -E 'sk-[a-zA-Z0-9]{10}|or-v1-' Dockerfile` — OK (no secret literals)
- `bash tests/test_init_sh_unchanged.sh` — PASS (TEST-05 invariant: openwebui/init.sh sha256 matches v0.9.2.0 baseline)
- `pytest tests/orchestrator/test_cli_runtime.py test_cli_adapters.py test_subagent_claude_compat.py test_docker_manager.py -q` — 77 passed (Phase 4-5 regression suite green)

## Heredoc-Escaping Note for Plan 06-05 Reviewers

The single-quoted heredoc terminator `'OCEOF'` is embedded inside a shell-printf format string via the `'"'"'OCEOF'"'"'` pattern (close-single, open-double, single, close-double, open-single). This is the same trick used at the existing `CLAUDE_JSON='"'"'...'"'"'` assignment (Dockerfile line 396). The CLOSING `OCEOF` line stays unquoted in the printf because the heredoc only requires the opening token to be quoted — the closer is just a line that begins with the terminator word. When Plan 06-05 rebuilds the image and Plan 06-04 inspects the rendered `/tmp/opencode.json` inside a running container, the file should contain literal `{env:OPENROUTER_API_KEY}` strings (not the resolved env values).

## Self-Check: PASSED

- Dockerfile modification — FOUND (commit 654c770 in `git log --oneline`)
- All 11 grep verification checks — passed
- Phase 4-5 regression tests — 77/77 passed
- TEST-05 (init.sh unchanged) — passed

## Next Phase Readiness
- Plan 06-04 (verify rendered files inside running container) can proceed once Plan 06-05 rebuilds the image.
- Plan 06-05 (image rebuild + smoke tests) is the next plan in the phase queue.
- Phase 7 will rename `CLAUDE_AUTOSTARTED → SUBAGENT_AUTOSTARTED` and add per-CLI dispatch in the autostart line at Dockerfile:415 — this plan intentionally did not touch that line.

---
*Phase: 06-per-cli-auth-config*
*Completed: 2026-04-26*
