---
phase: 07-ttyd-cost-guardrail
plan: 03
subsystem: build-and-test
tags: [docker, image-build, smoke-test, ttyd, autostart, no-autostart, sentinel, pytest, verification]

requires:
  - phase: 07-ttyd-cost-guardrail
    plan: 01
    provides: "Dockerfile .bashrc autostart honours ${SUBAGENT_CLI:-claude} + NO_AUTOSTART/sentinel escape hatches + welcome-banner hint"
  - phase: 07-ttyd-cost-guardrail
    plan: 02
    provides: "tests/orchestrator/test_sub_agent_dispatch.py — TEST-04 end-to-end dispatch suite + cost-rendering 'unavailable' regression guard"
  - phase: 06-per-cli-auth-config
    plan: 05
    provides: "Image build + verification umbrella pattern (mirrored here)"
provides:
  - "open-computer-use:phase7-test image (sha256 127c396cb9f9, 9.05GB, linux/amd64) with Plan 07-01 .bashrc autostart change materialised"
  - "tests/test-docker-image.sh extensions: per-CLI autostart-target verification + NO_AUTOSTART/sentinel smoke + entrypoint escape-hint check (3 new step-blocks, 6 new pass/fail assertions per CLI + 2 dedicated NO_AUTOSTART smokes + 1 entrypoint banner-hint)"
  - "Phase 7 ROADMAP success criteria 1-5 observably satisfied at the image level"
  - "TERM-01, TERM-02, TERM-03, TEST-04 closed"
affects: []

tech-stack:
  added: []
  patterns:
    - "Source-and-test pattern: `PS1=\"t> \" && source /home/assistant/.bashrc 2>&1 && echo BASH_REACHED` — exercises the `[ -n \"$PS1\" ]` guard genuinely (without PS1, the guard short-circuits and would falsely pass any escape-hatch test)"
    - "Loop-piggyback verification: the existing [11/13] per-CLI smoke loop already had a long-running container per CLI; the new autostart-target greps run as `docker exec` against that same container — zero extra container startups, zero extra cost"
    - "Backwards-compat regression guard via negative grep: `! grep CLAUDE_AUTOSTARTED .bashrc` proves the rename is complete, not just additive"

key-files:
  created:
    - ".planning/phases/07-ttyd-cost-guardrail/07-03-SUMMARY.md"
  modified:
    - "tests/test-docker-image.sh (renumber [11/12]/[12/12] -> [11/13]/[13/13]; new [12/13] NO_AUTOSTART step; +6 per-CLI .bashrc autostart-target assertions inside [11/13] loop; +1 entrypoint escape-hint assertion inside [13/13])"

key-decisions:
  - "Image tag named `open-computer-use:phase7-test` (not `:latest`) to mirror Phase 6 plan 06-05's tagging convention. The `:latest` tag stays at v0.9.2.0 baseline until milestone v0.9.2.1 ships in full."
  - "Renumbered the existing decorative `[N/12]` markers to `[N/13]`. The script does not enforce a hard-coded total — purely cosmetic, but kept consistent so failures point at recognisable step labels."
  - "Did NOT add a runtime autostart smoke for codex/opencode (e.g. `docker run -e SUBAGENT_CLI=codex bash -i`). Two reasons: (a) the CLI would crash without real auth — `exec codex` with stub key would exit non-zero, polluting the test signal; (b) the `.bashrc`-content grep already proves the autostart line is identical for every CLI (the `${SUBAGENT_CLI:-claude}` substitution happens at session-start, not at .bashrc-write — so verifying the LITERAL line shape proves all three CLIs route correctly). The runtime smoke would add flakiness without coverage."
  - "Task 2 was pure verification (build + 4 shell test scripts + pytest + auth-leak grep). No files modified, so no commit (mirrored from 07-02 Task 2 convention). The final SUMMARY commit captures the verification artifacts."

decisions: []

metrics:
  duration: "~8 minutes (build was incremental from phase6 cache: 36 layers, only entrypoint/autostart layers changed; build wall-clock <1 minute)"
  tasks: 2
  files_changed: 1
  commits: 1
  completed: "2026-04-26"

threat-flags: []
---

# Phase 7 Plan 03: Image rebuild + verification umbrella Summary

Final verification gate for Phase 7. Mirrors the 06-05 pattern: extend `tests/test-docker-image.sh` with image-level assertions for the new ttyd UX behaviour, rebuild the image so Plan 07-01's Dockerfile change is materialised, and run the full test suite to prove all green.

## What Shipped

### Task 1 — `tests/test-docker-image.sh` extensions (commit `2dc7f53`)

Three structural edits, all using the existing `pass`/`fail` helpers:

**EDIT 1 — inside the existing `[11/13]` per-CLI loop (after marker check, before `docker rm`):**

Per-iteration `docker exec ... cat /home/assistant/.bashrc` + grep, asserting:

1. The autostart line contains the literal `exec "${SUBAGENT_CLI:-claude}"` shape (proves Plan 07-01's `${SUBAGENT_CLI:-claude}` wiring is on disk).
2. The autostart line references both `NO_AUTOSTART` and `/tmp/.no_autostart` (proves the escape hatches landed).
3. The old marker name `CLAUDE_AUTOSTARTED` does NOT appear (backwards-compat regression guard — Plan 07-01 renamed it to `SUBAGENT_AUTOSTARTED`).

3 pass/fail per CLI × 3 CLIs = **9 new assertions** in `[11/13]`.

**EDIT 2 — new `[12/13] NO_AUTOSTART escape hatch` step:**

Two `docker run` smokes, both sourcing `.bashrc` with `PS1` set so the `[ -n "$PS1" ]` autostart guard is genuinely exercised:

- `-e NO_AUTOSTART=1` — autostart must skip; `BASH_REACHED` echoed = pass.
- `touch /tmp/.no_autostart && source ...` — sentinel-file branch; `BASH_REACHED` echoed = pass.

**2 new assertions** in `[12/13]`.

**EDIT 3 — extend `[13/13]` (renumbered from `[12/12]`) entrypoint banner check:**

Adds a `grep -qF "NO_AUTOSTART=1 bash"` against the captured entrypoint stdout, proving the welcome-banner hint from Plan 07-01 EDIT 2 reaches the operator.

**1 new assertion** in `[13/13]`.

Total: **12 new assertions** (54 total, up from 42 pre-Phase-7).

### Task 2 — Image rebuild + full test suite (no commit, pure verification)

| Step | Result |
|------|--------|
| `docker build --platform linux/amd64 -t open-computer-use:phase7-test .` | sha256 `127c396cb9f9f406513d48bb1047fa549711c7e704772206f1c5b654a383683a`, 9.05GB, naming OK, `Claude Code OK` |
| `bash tests/test_init_sh_unchanged.sh` | PASS (sha256 `31ce03b67804ed11c5a5e42be8364c0adfedd356d1e9aed9ce87e8318c9c27a7` — TEST-05 invariant intact) |
| `bash tests/test-no-corporate.sh` | 14/14 PASS — `RESULT: ALL CLEAN` |
| `bash tests/test-project-structure.sh` | 22/22 PASS — `RESULT: STRUCTURE OK` |
| `bash tests/test-docker-image.sh open-computer-use:phase7-test` | **54/54 PASS** — `RESULT: ALL TESTS PASSED` (includes all new Phase 7 assertions) |
| `pytest tests/orchestrator/{test_cli_runtime,test_cli_adapters,test_subagent_claude_compat,test_docker_manager,test_passthrough_isolation,test_startup_warnings,test_sub_agent_dispatch}.py -q` (in `python:3.13-slim`) | **93 passed, 0 failed** in 1.19s |
| Auth-leak grep (`OPENROUTER_API_KEY=or-v1-LEAK-CHECK` + `OPENAI_API_KEY=sk-LEAK-CHECK` + `ANTHROPIC_AUTH_TOKEN=sk-ant-LEAK-CHECK` → `cat /tmp/opencode.json` → grep) | `NO_LEAK` — Pitfall 7 mitigation still in place after Phase 7 changes |

Build was incremental (only the entrypoint heredoc + AUTOSTART_LINE layer changed from the phase6-test cache); wall-clock <1 minute despite 36 layers.

## Phase 7 ROADMAP Success Criteria — observable verification

| # | Criterion | Verified by |
|---|-----------|-------------|
| 1 | `.bashrc` autostart honours `SUBAGENT_CLI` | `[11/13]` per-CLI grep `exec "${SUBAGENT_CLI:-claude}"` — PASS for all 3 CLIs |
| 2 | `NO_AUTOSTART` escape hatch works | `[12/13]` env smoke + sentinel-file smoke — both `BASH_REACHED` |
| 3 | Marker rename backwards-compat preserved | `[11/13]` negative grep `! grep CLAUDE_AUTOSTARTED .bashrc` — PASS for all 3 CLIs |
| 4 | End-to-end dispatch routes correctly | pytest `test_sub_agent_dispatch.py` — 7/7 PASS in 93-test orchestrator suite |
| 5 | Cost-guardrail caveat observable (`cost_usd=None` → `"unavailable"`) | pytest `test_cost_rendering_unavailable_for_none[codex,opencode]` — 2/2 PASS in same suite |

All five satisfied at the IMAGE level (not just at the source level).

## Requirements closed

- **TERM-01** — autostart honours SUBAGENT_CLI: VERIFIED (`[11/13]` per-CLI .bashrc grep)
- **TERM-02** — NO_AUTOSTART escape hatch: VERIFIED (`[12/13]` env + sentinel smokes)
- **TERM-03** — welcome MOTD escape hint: VERIFIED (`[13/13]` banner grep)
- **TEST-04** — end-to-end dispatch test: VERIFIED (pytest `test_sub_agent_dispatch.py` 7/7 + image-level smoke)

## Deviations from Plan

None of substance. Three minor variances, all documented in `key-decisions`:

1. Image tag `:phase7-test` rather than the plan's literal `:latest` — mirrors Phase 6 plan 06-05's convention (the `:latest` tag stays at v0.9.2.0 until milestone ships).
2. No runtime autostart smoke for codex/opencode (would crash without real auth; `.bashrc`-content grep already proves identical line shape for all CLIs).
3. Task 2 was pure verification → no commit (mirrors 07-02 Task 2 convention; the SUMMARY commit captures verification).

## Hand-off

Phase 7 fully complete. Milestone v0.9.2.1 wave 7 closed. The next phase (Phase 8 — operator docs for ttyd UX, per CONTEXT.md "Does NOT deliver") is ready when the milestone roadmap advances.

## Self-Check: PASSED

- File `.planning/phases/07-ttyd-cost-guardrail/07-03-SUMMARY.md` exists — verified by Write tool success.
- Commit `2dc7f53` present in `git log` — verified above.
- `tests/test-docker-image.sh` extensions verified by `bash -n` (syntax) + 4 grep checks (`NO_AUTOSTART=1`, `/tmp/.no_autostart`, `SUBAGENT_AUTOSTARTED`, `orphan CLAUDE_AUTOSTARTED`) — all matched.
- Image `open-computer-use:phase7-test` exists (`docker images` shows sha256 `127c396cb9f9`).
- All 93 pytest tests + 54 docker-image-test assertions + 14 no-corporate + 22 project-structure + init.sh invariant — all green.
- Auth-leak grep returned `NO_LEAK`.
