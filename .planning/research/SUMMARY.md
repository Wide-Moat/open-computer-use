# Project Research Summary

**Project:** Multi-CLI Sub-Agent Runtime (open-computer-use v0.9.2.1)
**Domain:** Coding-agent CLI integration into existing Ubuntu sandbox image + FastAPI orchestrator
**Researched:** 2026-04-25
**Confidence:** MEDIUM-HIGH

## Executive Summary

v0.9.2.1 adds Codex CLI (`@openai/codex@0.125.0`) and OpenCode (`opencode-ai@1.14.25`) as drop-in alternatives to Claude Code, behind a single `SUBAGENT_CLI=claude|codex|opencode` env switch read once at orchestrator boot. Both new CLIs install via `npm install -g` into the existing `/usr/local/lib/node_modules_global` prefix — zero new package managers, zero new system packages, ~100–140 MB image-layer growth, volume budget (`/home/assistant` < 1 MB) preserved. The MCP `sub_agent(...)` tool surface stays byte-identical for callers; CLI differences are absorbed by a thin Python adapter layer (`cli_runtime.py` + `cli_adapters/`) that lives below `mcp_tools.sub_agent`.

The recommended approach is a strict adapter pattern: a single dispatch function (`_RESOLVERS` dict) keyed by CLI, three small per-CLI builders that each return `(argv, env_overrides, result_parser)`, and three CLI-scoped env-var allowlists in `docker_manager.py` so that `SUBAGENT_CLI=opencode` does not silently inherit a leftover `OPENAI_API_KEY` from a previous experiment. ttyd UX is delivered by changing only the `.bashrc` autostart line (`exec "${SUBAGENT_CLI:-claude}"`) — `app.py` is untouched. OpenCode config is rendered to `/tmp/opencode.json` (NOT the volume) by the entrypoint heredoc, with `{env:VAR}` substitution so secrets never hit disk.

Key risks: (1) `--max-turns 25` is Claude-only; codex/opencode have no equivalent, so cost guardrail parity must come from `SUB_AGENT_TIMEOUT` + per-CLI native caps + adapter-level docs, not a one-line flag swap. (2) Output schemas diverge — Claude's `{"type":"result"}` JSONL ≠ codex's `turn.completed`/`item.completed` events ≠ opencode's event stream — so `_format_sub_agent_result` must split into per-adapter parsers, returning `cost_usd=None` (rendered "unavailable") rather than `0.0` when the CLI doesn't report. (3) Backwards compat: empty `SUBAGENT_CLI` MUST behave byte-identical to today's claude path — the `claude` adapter is a lift-and-shift of existing code, not a refactor. (4) `openwebui/init.sh` MUST NOT be touched — `SUBAGENT_CLI` is orchestrator-side, not a Valve. Mitigations are concrete and testable; see Phase plan below.

## Key Findings

### Recommended Stack

Two new npm-global CLIs alongside existing `@anthropic-ai/claude-code@2.1.112`. No new apt packages, no new runtimes. Both pinned to exact versions matching the existing `CLAUDE_CODE_VERSION=2.1.112` discipline.

**Core technologies (additions):**
- `@openai/codex@0.125.0`: OpenAI's official coding-agent CLI — only first-party "Codex CLI" with active development; ships native binaries via npm `optionalDependencies` (linux-x64 only on `--platform linux/amd64`), exact `codex exec --ephemeral --json --output-last-message` contract for stateless runs.
- `opencode-ai@1.14.25` (sst/opencode): provider-agnostic coding-agent — 75+ first-class providers (OpenRouter, Bedrock, Anthropic, OpenAI, Ollama, LM Studio); `{env:VAR}` substitution in `opencode.json` matches our "operator brings own keys" rule; canonical fork (do NOT use `opencode-ai/opencode` or `anomalyco/opencode`).
- Existing Node 22.11.0, `curl`, `git`, `ca-certificates`: sufficient — no system-dep additions.

Detailed: see `.planning/research/STACK.md`.

### Expected Features

**Must have (table stakes — verified all three CLIs ship):**
- Non-interactive one-shot: `claude -p` / `codex exec` / `opencode run`
- Env-var auth (no interactive login in headless container)
- Per-invocation `--model` flag
- JSON output mode for parsing
- Permission-bypass flag (`--permission-mode bypassPermissions` / `--full-auto` / `--dangerously-skip-permissions`)
- Tool loop runs inside CLI process (no MCP wiring of Bash/Edit)

**Should have (differentiators that justify the milestone):**
- OpenCode 75+ providers + native OpenRouter — kills Anthropic lock-in (the headline)
- OpenRouter `qwen/qwen3-coder` worked recipe — proof point per PROJECT.md
- Codex `--ephemeral` — zero disk footprint per sub-agent run (matches our stateless contract)
- OpenCode AGENTS.md picks up existing `CLAUDE.md` automatically (operator migration path)
- Inline `-c key=value` Codex TOML override (per-call provider injection)

**Defer (v0.9.x+):**
- USD cost computation for non-Claude CLIs (model→price table) — surface "unavailable" for now
- Adapter-level max-turns enforcement via JSON event-stream counting + SIGTERM
- Codex `--output-schema` integration for structured returns
- `mode=plan` parameter mapping to OpenCode's plan agent

**Anti-features (do NOT replicate):**
- Per-call CLI override (out of scope per PROJECT.md)
- OpenCode `serve` / `web` / `attach` / `share` modes (redundant infra; `--share` leaks to sst.dev)
- Codex `--dangerously-bypass-approvals-and-sandbox` (use `--full-auto` instead)
- Auto-installing operator API keys

Detailed: see `.planning/research/FEATURES.md`.

### Architecture Approach

Pure-Python adapter layer below `mcp_tools.sub_agent`. `SUBAGENT_CLI` is read once at `docker_manager.py` module load (next to existing `SUB_AGENT_*` constants), propagated into every container's `extra_env`, and re-read at sub_agent invocation time. Three CLI-scoped passthrough tuples (`CLAUDE_CODE_PASSTHROUGH_ENVS`, `CODEX_PASSTHROUGH_ENVS`, `OPENCODE_PASSTHROUGH_ENVS`) union into `ALL_CLI_PASSTHROUGH_ENVS` for the existing iteration site at `_create_container` line 461. ttyd plumbing in `app.py` is untouched; only `.bashrc` autostart (`Dockerfile:395`) changes to `exec "${SUBAGENT_CLI:-claude}"` with the marker renamed `CLAUDE_AUTOSTARTED → SUBAGENT_AUTOSTARTED`. OpenCode's `opencode.json` is rendered by the entrypoint heredoc to `/tmp/opencode.json` (NOT the volume) with `OPENCODE_CONFIG=/tmp/opencode.json` and `{env:VAR}` substitution.

**Major components:**
1. `computer-use-server/cli_runtime.py` (NEW) — `resolve_subagent_model(alias, cli)` + `build_command(cli, ...)` with `_RESOLVERS` dict dispatch; pure Python, no Docker imports.
2. `computer-use-server/cli_adapters/{claude,codex,opencode}.py` (NEW pkg) — per-CLI `build_cmd(...)` and `parse_result(stdout) -> SubAgentResult` (normalised dataclass: `result_text, cost_usd, turns, is_error, session_id, jsonl_log_path`).
3. `computer-use-server/docker_manager.py` (MOD) — `SUBAGENT_CLI` constant, three passthrough tuples + union, `extra_env["SUBAGENT_CLI"]` injection, allowlist gating to prevent auth bleed.
4. `computer-use-server/mcp_tools.py` (MOD) — replace inline alias map (lines 908–925) and inline `claude_command` builder (lines 967–1019) with `cli_runtime` calls; replace `_format_sub_agent_result` with adapter dispatch.
5. `Dockerfile` (MOD) — codex + opencode npm installs after line 218; `--version` smoke checks at line 452; `.bashrc` autostart honours `$SUBAGENT_CLI`; entrypoint renders `/tmp/opencode.json` heredoc when `$SUBAGENT_CLI=opencode`.
6. `skills/public/sub-agent/` — keep shared `SKILL.md` (CLI-agnostic), add `references/runtimes.md` for per-CLI quirks (resume semantics, model alias rules).

Detailed: see `.planning/research/ARCHITECTURE.md`.

### Critical Pitfalls

Top 5 from `.planning/research/PITFALLS.md` (12 documented in total):

1. **Auth bleed across CLIs** — host `.env` with leftover `OPENAI_API_KEY` silently re-routes opencode to a wrong provider. **Mitigation:** allowlist (not blocklist) per-CLI env injection in `_build_container_env()`; explicitly strip the other CLIs' env from each container.
2. **System-prompt contract divergence** — `--append-system-prompt` is Claude-only; Codex `--system-prompt-file` is *replace* not *append* (and may not exist); OpenCode uses per-mode prompt files. **Mitigation:** treat skill prompt as a **task preamble**: adapter concatenates `system_prompt + "\n\n---\n\n" + task` for codex/opencode and feeds it as the task argument; for opencode also write the prompt into `instructions[]` of `/tmp/opencode.json`. Never rely on append-vs-replace semantics.
3. **Model-alias mismatch** — `"sonnet"` reaching codex resolves to `claude-sonnet-4-6` and silently 400s. **Mitigation:** move alias map *into* each adapter; hard-fail with a precise message when a Claude alias hits a non-Claude CLI; split `SUB_AGENT_DEFAULT_MODEL` into per-CLI defaults (`CODEX_SUB_AGENT_DEFAULT_MODEL`, `OPENCODE_SUB_AGENT_DEFAULT_MODEL`).
4. **Output-format drift** — `_format_sub_agent_result` parses Claude's `{"type":"result"}` JSONL; codex emits `turn.completed`/`item.completed`; opencode emits a third schema. **Mitigation:** per-adapter `parse_result(stdout) -> SubAgentResult`; return `cost_usd=None` (rendered "unavailable"), never default to `0.0`.
5. **Cost runaway** — `--max-turns 25` is Claude-only. **Mitigation (v0.9.2.1):** `SUB_AGENT_TIMEOUT` is the primary backstop (consider lowering default to 1800s for non-claude CLIs); document the gap; defer adapter-level turn counting to a follow-up phase.

Plus three hard rules from saved memory + PROJECT.md:
- **`openwebui/init.sh` must NOT be touched** (Pitfall 10) — grep gate in `test-project-structure.sh` blocks the PR if it's modified.
- **OpenCode auth.json must NOT persist in the volume** (Pitfall 7) — env-only auth, `OPENCODE_CONFIG=/tmp/opencode.json`, scrub `~/.local/share/opencode/auth.json` on container creation.
- **Backwards compat: `SUBAGENT_CLI=""` ≡ unset ≡ `"claude"`** (Pitfall 12) — golden-snapshot test asserts byte-identical orchestrator output for the claude path pre/post-milestone.

Detailed: see `.planning/research/PITFALLS.md`.

## Implications for Roadmap

Based on cross-cutting findings, the milestone splits cleanly into 5 phases. Phase boundaries are dependency-respecting and each phase is independently testable.

### Phase 1: Env Switch + Adapter Scaffolding
**Rationale:** Pure-Python work with no Docker dependency runs first; everything downstream imports `cli_runtime`. Establishes backwards-compat contract before any CLI is installed in the image.
**Delivers:**
- `SUBAGENT_CLI = os.getenv("SUBAGENT_CLI", "claude").strip().lower() or "claude"` constant in `docker_manager.py` (with allowlist `{"claude","codex","opencode"}`, lenient fallback to `"claude"`)
- `cli_runtime.py` with `resolve_subagent_model(alias, cli)` + `build_command(cli, ...)` + `_RESOLVERS` dict
- `cli_adapters/__init__.py` package skeleton
- Three CLI-scoped passthrough tuples + `ALL_CLI_PASSTHROUGH_ENVS` union
- `extra_env["SUBAGENT_CLI"]` injection in `_create_container`
- `warn_if_subagent_cli_unset` startup banner (informational, mirrors `warn_if_public_base_url_is_default`)
- Unit tests: `test-cli-runtime.py` (resolver), `test_subagent_cli_env_isolation.py` (allowlist), `test_subagent_claude_compat.py` (golden snapshot)
- Dockerfile pinning `ARG CODEX_VERSION=0.125.0` and `ARG OPENCODE_VERSION=1.14.25`

**Avoids:** Pitfalls 1, 3, 10, 12 (auth bleed, alias mismatch, init.sh regression, backwards-compat break).

### Phase 2: Adapter Layer (per-CLI argv + result parsing)
**Rationale:** Adapter contract must exist before `mcp_tools.sub_agent` can dispatch through it; pure-Python so unit tests are fast (no Docker).
**Delivers:**
- `cli_adapters/claude.py` — lift-and-shift from `mcp_tools.py:967-1019` (zero diff except imports — preserves backwards compat)
- `cli_adapters/codex.py` — `codex exec "$task" --model "$model" --json --output-last-message /tmp/codex-last.txt --skip-git-repo-check --full-auto -C "$workdir"` + JSONL `turn.completed`/`item.completed` parser
- `cli_adapters/opencode.py` — `opencode run "$task" --model "$provider/$model" --format json --dangerously-skip-permissions` + event-stream parser
- Normalised `SubAgentResult` dataclass: `result_text, cost_usd (Optional[float]), turns, is_error, session_id, jsonl_log_path`
- System-prompt strategy: claude uses `--append-system-prompt`; codex/opencode receive `system_prompt + "\n\n---\n\n" + task` as task preamble (Pitfall 2)
- `_format_sub_agent_result` split into adapter dispatch (Pitfall 4)
- Tests: `test-cli-adapters.py` (golden-string argv per CLI), `test_subagent_prompt_assembly.py`, `test_subagent_result_parsing.py` with fixture stdout dumps per CLI

**Avoids:** Pitfalls 2, 4 (prompt contract, output drift).

### Phase 3: Per-CLI Auth + OpenCode Config Rendering
**Rationale:** Auth wiring is the security-sensitive surface; lands in its own phase with dedicated review and leak tests. Image work happens here because the entrypoint heredoc is the single source of truth for `opencode.json`.
**Delivers:**
- Dockerfile additions after line 218: `npm install -g @openai/codex@${CODEX_VERSION}`, `npm install -g opencode-ai@${OPENCODE_VERSION}`, smoke-test `claude --version && codex --version && opencode --version`
- Entrypoint heredoc (after `Dockerfile:352`): `if [ "${SUBAGENT_CLI:-claude}" = "opencode" ]; then` write `/tmp/opencode.json` with `{env:OPENROUTER_API_KEY}` substitution; set `OPENCODE_CONFIG=/tmp/opencode.json`
- Defensive scrub of `~/.local/share/opencode/auth.json` in `_create_container()` (Pitfall 7)
- Codex auth via `~/.codex/config.toml` `[model_providers.X]` block (NOT `OPENAI_BASE_URL` env — undocumented)
- `mcp_tools.py` MCP-config writer extended to emit codex's `[mcp_servers]` TOML and opencode's `mcp` block (port of existing `build_mcp_config` for `~/.mcp.json`)
- Tests: `test_opencode_no_persistent_auth.py` (security), volume-leak grep for `auth.json`

**Avoids:** Pitfalls 1 (auth bleed via gating), 7 (opencode auth leak).

### Phase 4: Cost Guardrail + ttyd UX Parity
**Rationale:** UX-facing surface lands together; both items are small but visible. Decoupled from auth/adapter work because they don't touch the same files.
**Delivers:**
- `.bashrc` autostart change at `Dockerfile:395`: `[ -z "$SUBAGENT_AUTOSTARTED" ] && [ -n "$PS1" ] && export SUBAGENT_AUTOSTARTED=1 && exec "${SUBAGENT_CLI:-claude}"` (marker renamed from `CLAUDE_AUTOSTARTED`)
- `NO_AUTOSTART=1` env + `/tmp/.no_autostart` sentinel escape hatch (Pitfall 9)
- Default `SUB_AGENT_TIMEOUT=1800` for non-claude CLIs (lowered from 3600 — Pitfall 5)
- `cost_usd=None` rendered as "cost: unavailable" in `_format_sub_agent_result` (Pitfall 4 follow-through)
- Documentation of cost-guardrail caveat in `skills/public/sub-agent/references/runtimes.md`
- `mcp_tools.sub_agent` flipped to dispatch through `cli_runtime` (replaces `mcp_tools.py:908-1019`)

**Avoids:** Pitfalls 5, 9 (cost runaway, ttyd no-escape).

### Phase 5: Test Coverage + Operator Docs
**Rationale:** Test work assumes phases 1–4 are stable; operator docs are last because they reference the final shipped surface. Mandatory per CLAUDE.md.
**Delivers:**
- `tests/test-docker-image.sh` extended: `which $tool && $tool --version` per new CLI; new step `[12/14] CLI flag compatibility` greps `codex exec --help` and `opencode run --help` for adapter-required flags (Pitfall 6); new step `[13/14] Sub-agent CLI dispatch` runs a trivial prompt per CLI against a stub provider; volume-size test runs entrypoint twice before measuring (Pitfall 11)
- Grep gate in `tests/test-project-structure.sh`: assert `openwebui/init.sh` unchanged in this milestone diff (Pitfall 10)
- `tests/security/test_opencode_no_persistent_auth.py` — start container, write fake auth.json, restart, assert it's gone
- `docs/multi-cli.md` — step-by-step copy-paste docs (per `feedback_step_by_step_docs.md`):
  - "Switch to Codex" (env vars, restart command, verification)
  - "Switch to OpenCode + qwen3-coder via OpenRouter" (the worked headline recipe)
  - Verification commands per CLI ("how do I know it took effect")
  - Per-CLI gotcha matrix (model alias rules, cost reporting availability, max-turns caveat)
- `skills/public/sub-agent/references/runtimes.md` — per-CLI table for resume semantics, session log paths, model alias rules
- README + CHANGELOG entry for v0.9.2.1

**Avoids:** Pitfalls 6, 8, 11 (version drift, test combinatorics, test-docker-image.sh blind spots).

### Phase Ordering Rationale

- **Pure-Python before Docker** (Phase 1, 2 before 3): adapter unit tests run in seconds without image rebuilds; reviewers see the contract before they see the wiring.
- **Auth/image as one phase** (Phase 3): the entrypoint heredoc is the single source of truth for `opencode.json` — splitting across phases creates two write paths that drift. Security review happens once on this phase.
- **UX after wiring** (Phase 4): ttyd autostart and cost-guardrail surfaces are small and visible; landing them together gives a clean "operator-facing changes" checkpoint. `mcp_tools.sub_agent` flip happens here so claude path stays unmodified through phases 1–3.
- **Tests + docs last** (Phase 5): docs reference the final shipped flag set; tests need all three CLIs installed (Phase 3) AND dispatched (Phase 4) before they can assert end-to-end.
- **Backwards compat is structural** (Pitfall 12): the `claude` adapter is a lift-and-shift, no refactor — diff vs old code is import-only. This rule applies across phases 1–4.

### Research Flags

Phases needing deeper research during planning (`/gsd-research-phase`):
- **Phase 2 (adapter layer):** opencode JSON event schema is verified at the doc level but exact field names per event type are sparsely documented; consider one round of `/gsd-research-phase` to capture real fixture stdout from each CLI before writing parsers. Codex `--max-output-tokens` flag availability also needs version-specific verification (Pitfall 6 risk).
- **Phase 3 (auth wiring):** Codex `requires_openai_auth = true` for custom providers comes from a single doc source (MEDIUM confidence); verify in CI test before relying on it.

Phases with standard patterns (skip research-phase):
- **Phase 1 (env switch + scaffolding):** mirrors existing `SUB_AGENT_*` constants pattern at `docker_manager.py:70-91`; no new ground.
- **Phase 4 (UX):** trivial bash + dataclass changes; no research needed.
- **Phase 5 (tests + docs):** test-docker-image.sh extension is mechanical; docs follow `feedback_step_by_step_docs.md` template.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM-HIGH | Codex flags + version verified on developers.openai.com; opencode env-var auto-pickup is MEDIUM (config-driven `{env:...}` is the safe path); both pinned to exact versions to neutralise drift risk |
| Features | HIGH | Cross-checked against developers.openai.com/codex, opencode.ai docs, sst/opencode `run.ts` source, opencode.ai/docs/providers; rows 1-9 of capability matrix all verified |
| Architecture | HIGH | All file:line references verified by direct read of `mcp_tools.py`, `docker_manager.py`, `Dockerfile`, `app.py`; integration points concrete |
| Pitfalls | MEDIUM-HIGH | HIGH for claude-regression (we own the contract), MEDIUM-HIGH for codex (concrete docs + open issues found), MEDIUM for opencode (pre-1.0 flags + recent fork between sst/opencode-ai/anomalyco — we pin to sst) |

**Overall confidence:** MEDIUM-HIGH — sufficient to start Phase 1; one targeted research round before Phase 2 will close the remaining gaps on opencode JSON event schema.

### Gaps to Address

- **Real codex/opencode JSON output fixtures.** Documented schemas are correct in shape but exact event field names need a one-shot capture before writing the parsers. Plan: spawn the new image manually in Phase 2, run `codex exec --json "echo OK"` and `opencode run --format json "echo OK"` against a stub provider, save outputs as `tests/fixtures/codex_run.jsonl` and `tests/fixtures/opencode_run.jsonl`, write `parse_result` against fixtures.
- **Codex `requires_openai_auth = true` for custom providers.** Single doc source; verify with a CI test that a custom `[model_providers.X]` block with `env_key` actually picks up the env var.
- **OpenCode npm package vs Go-binary download URL drift.** `opencode-ai` shim downloads the platform binary from GitHub Releases at install time — if the URL pattern changes between releases, our pinned version may stop installing. Plan: cache-bust the install in CI on every Renovate bump.
- **Adapter-level max-turns enforcement** is deferred (Pitfall 5 mitigation); operators on codex/opencode rely on `SUB_AGENT_TIMEOUT` until v0.9.x. Document explicitly in Phase 5 docs.
- **Cost-USD computation for non-Claude CLIs** is deferred. `cost_usd=None` rendered as "unavailable" is the v0.9.2.1 contract; model→price table comes when operators ask.

## Sources

### Primary (HIGH confidence)
- developers.openai.com/codex/cli/reference — `codex exec` flags (`--json`, `-o`, `--output-schema`, `-c`, `--full-auto`, `--ephemeral`)
- developers.openai.com/codex/noninteractive — `ThreadEvent` JSONL schema, prompt-via-stdin, approval-fail behaviour
- developers.openai.com/codex/auth + developers.openai.com/codex/cli/config — auth modes, `requires_openai_auth`, `env_key`, `[model_providers.X]` TOML
- github.com/openai/codex (releases + docs/agents_md.md) — version 0.125.0 (April 24, 2026), AGENTS.md mechanism
- github.com/sst/opencode/releases — version 1.14.25 (April 25, 2026), npm distribution strategy
- opencode.ai/docs/cli + /docs/config + /docs/providers + /docs/rules + /docs/modes — `opencode run`, `--format json`, `provider/model`, `{env:VAR}` substitution, AGENTS.md/CLAUDE.md fallback, `instructions[]`
- github.com/sst/opencode/blob/dev/packages/opencode/src/cli/cmd/run.ts — exact flag definitions for `opencode run`
- openrouter.ai/qwen/qwen3-coder/api — model id `qwen/qwen3-coder`, OpenAI-compatible endpoint
- Existing repo files (verified by direct read 2026-04-25): `Dockerfile:218,395,452`, `computer-use-server/mcp_tools.py:812-857,860-1178,908-925,932-941,967-1019`, `computer-use-server/docker_manager.py:70-105,455-463,461,530`, `computer-use-server/app.py:825-854`, `tests/test-docker-image.sh:84,133,173`, `openwebui/init.sh` (full body), `skills/public/sub-agent/SKILL.md:124,137-140`

### Secondary (MEDIUM confidence)
- learn.microsoft.com/en-us/azure/foundry/openai/how-to/codex — Azure `[model_providers.azure]` `wire_api = "responses"`
- codex.danielvaughan.com/2026/04/08/codex-cli-configuration-reference — full TOML key reference
- deepwiki.com/openai/codex/4.2-headless-execution-mode — `--ephemeral` flag, `ThreadEvent` schema
- opencode.ai/docs/models — provider list via Models.dev, `provider/model_id` form
- WebSearch on opencode env-var auto-pickup — implicit env-var pickup undocumented; config-driven `{env:...}` recommended

### Tertiary (LOW confidence — flagged for verification)
- github.com/openai/codex#11588 — `--system-prompt-file` / `--append-system-prompt` are open feature requests, NOT shipped (drives Pitfall 2 mitigation: task-preamble strategy)
- github.com/openai/codex#4776 — JSON output mode docs are out of date (drives Pitfall 6 mitigation: pin + flag-compat test)
- github.com/anomalyco/opencode#13851 — non-interactive UX gaps (third-fork issue; we pin to sst, not anomalyco)
- Codex `requires_openai_auth = true` for custom providers — single doc source; verify in Phase 3 CI test

---
*Research completed: 2026-04-25*
*Ready for roadmap: yes*
