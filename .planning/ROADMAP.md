# Roadmap: Open Computer Use

## Milestones

- ✅ **v0.8.12.7 — System Prompt Extraction** (Phase 1, shipped 2026-04-12)
- ✅ **v0.8.12.8 — Preview Filter UX** (Phase 2, shipped 2026-04-12)
- ✅ **v0.8.12.9 — Claude Code Gateway Compatibility** (Phase 3, shipped 2026-04-25 in v0.9.2.0)
- 🚧 **v0.9.2.1 — Multi-CLI Sub-Agent Runtime** (Phases 4–8, active since 2026-04-25)

## Phases

### ✅ v0.8.12.7 — System Prompt Extraction (Shipped)

**Milestone Goal:** Move the ~460-line hard-coded Computer Use system prompt out of the Open WebUI filter and into a server endpoint that does full substitution on the server (URLs from `chat_id`, dynamic `<available_skills>` from optional `user_email`, graceful fallback to default public skills when no external provider is wired). Filter becomes a thin HTTP-fetch + LRU cache + stale-cache fallback layer.

- [x] **Phase 1: System Prompt Extraction** — Port internal v3.7/v3.8 server-side substitution to community. Upgrade `GET /system-prompt`. Rewrite filter as thin HTTP client + LRU cache + stale-cache fallback. Add tests.

### ✅ v0.8.12.8 — Preview Filter UX (Shipped)

**Milestone Goal:** Expose the already-shipped `/preview/{chat_id}` SPA to users of stock Open WebUI (without frontend patches). Filter's `outlet()` learns to emit an inline iframe artifact by default and, opt-in, a markdown preview button. All v3.1.0 `outlet()` correctness invariants preserved. Every Valve (old and new) documented in one authoritative place.

- [x] **Phase 2: Preview Filter UX** — Added three new Valves to `computer_link_filter.py`, extended `outlet()` to emit preview iframe (default) and preview button (opt-in), bumped filter 3.1.0 → 3.2.0 (commit `b08d472`), documented every Valve in a `VALVES:` docstring block + `docs/openwebui-filter.md` (+ troubleshooting section in `d79f730`), proved both the feature and the existing behaviour with pytest in Docker.

### ✅ v0.8.12.9 — Claude Code Gateway Compatibility (Shipped 2026-04-25 in v0.9.2.0)

**Milestone Goal:** The Claude Code sub-agent running inside each sandbox container routes its API calls to whatever Anthropic-compatible destination the operator configured (public Anthropic, LiteLLM proxy, Azure, Bedrock-via-LiteLLM, etc.), with optional model-ID and prompt-caching/beta overrides — all without ever breaking the zero-config `/login` path. Fixes issue #40; inspired by PR #41 but rewritten with tests and without the deploy-specific churn.

- [x] **Phase 3: Claude Code Gateway Compatibility** — Fix `context_vars.py:14` default so the `ANTHROPIC_BASE_URL` env fallback actually fires in `_create_container`; pass through the ten official Claude Code env vars only when set; teach `sub_agent` MCP tool to accept direct model IDs; add pytest coverage; document the gateway path.

### 🚧 v0.9.2.1 — Multi-CLI Sub-Agent Runtime (Phases 4–8, active)

**Milestone Goal:** Add Codex CLI (`@openai/codex`) and OpenCode (`opencode-ai`, sst fork) as drop-in alternatives to Claude Code across the entire sub-agent surface. A single `SUBAGENT_CLI=claude|codex|opencode` env switch, read once at orchestrator boot, routes every sub-agent invocation through the chosen CLI with identical operator UX. Default unset = `claude` (byte-identical backwards compat). MCP `sub_agent(...)` tool signature unchanged. Tests are mandatory and ship with the code under test.

- [ ] **Phase 4: Env switch + adapter scaffolding** — `SUBAGENT_CLI` constant in `docker_manager.py`, allowlist + hard-fail-on-invalid resolver in `cli_runtime.py`, `cli_adapters/` package skeleton, `extra_env["SUBAGENT_CLI"]` injection, resolver tests + init.sh regression-grep test (CLI-01..03, ADAPT-01, TEST-02, TEST-05).
- [ ] **Phase 5: Adapter layer (per-CLI argv + result parsing)** — Three adapters (`claude.py` lift-and-shift, `codex.py`, `opencode.py`), normalised `SubAgentResult` dataclass, `mcp_tools.sub_agent` rewritten as thin orchestration over `cli_runtime.dispatch(...)`, per-CLI model resolution. Adapter tests + golden Claude snapshot ship with the code (ADAPT-02..06, TEST-03).
- [ ] **Phase 6: Per-CLI auth + config rendering** — Three CLI-scoped passthrough tuples, marker-gated entrypoint heredoc rendering `~/.config/opencode/opencode.json` (env-substituted, in `/tmp`) and `~/.codex/config.toml`, codex + opencode npm-global installs in image, image-level `--version` and per-CLI autostart smoke tests (AUTH-01..04, TEST-01, TEST-06).
- [ ] **Phase 7: Cost guardrail + ttyd UX** — `.bashrc` autostart honours `${SUBAGENT_CLI:-claude}` with renamed `SUBAGENT_AUTOSTARTED` marker, `NO_AUTOSTART=1` escape hatch, `sub_agent` dispatch end-to-end test (TERM-01..03, TEST-04).
- [ ] **Phase 8: Operator docs** — `docs/multi-cli.md` step-by-step copy-paste guide, OpenCode + qwen3-coder + OpenRouter worked recipe, README/INSTALL/.env.example cross-links, CHANGELOG v0.9.2.1 entry (DOCS-MULTICLI-01..04).

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
  1. **Default UX ships** — three new Valves at their defaults; `outlet()` appends exactly one fenced ```html iframe block to assistant messages with a file URL for the current `chat_id`.
  2. **Button opt-in works** — with `ENABLE_PREVIEW_BUTTON=True`, the same message also gets a `[🖥️ Open preview]` markdown link.
  3. **Invariants preserved** — no regression on existing suites; new tests cover role guard, string-content guard, `chat_id` scoping, trailing-slash safety, idempotency.
  4. **Valve docs exist and match code** — `VALVES:` docstring + `docs/openwebui-filter.md` + drift test.
  5. **Docker verification green** — image build + `test-docker-image.sh` / `test-no-corporate.sh` / `test-project-structure.sh` / pytest all pass.

**Plans:** 1 plan — `02-01-PLAN.md` (complete)
**UI hint:** yes

### Phase 3: Claude Code Gateway Compatibility (v0.8.12.9, Shipped 2026-04-25)

**Goal:** The Claude Code sub-agent inside each sandbox container routes its API traffic to the operator-configured destination (public Anthropic, LiteLLM, Azure, Bedrock-via-LiteLLM, etc.), with optional model-ID and prompt-caching/beta overrides, while the zero-config path (no env vars → Claude Code's native `/login`) still works out of the box.
**Depends on:** Nothing blocking (touches `computer-use-server/*` only)
**Requirements:** GATEWAY-01..12
**Related:** Fixes issue #40; inspired by PR #41, reimplemented with tests.
**Success Criteria:** (observable — all met, shipped 2026-04-25)
  1. Zero-config = stock Claude Code `/login` (no `ANTHROPIC_*` vars in sandbox `Env`).
  2. Env fallback works — `ANTHROPIC_AUTH_TOKEN` + `ANTHROPIC_BASE_URL` propagate, root-cause `context_vars.py:14` default fixed.
  3. Ten official Claude Code env vars pass through iff set.
  4. `sub_agent` accepts both aliases (`sonnet`/`opus`/`haiku`) and direct model IDs.
  5. Tests green; `ANTHROPIC_CUSTOM_HEADERS` regression guard passes.
  6. `docs/claude-code-gateway.md` + `.env.example` + `docker-compose.yml` + README/INSTALL cross-links shipped.

**Plans:** 3 plans (all complete)

### Phase 4: Env switch + adapter scaffolding (v0.9.2.1)

**Goal:** Operators can pick a sub-agent CLI runtime via `SUBAGENT_CLI=claude|codex|opencode`, with backwards-compatible defaults, validated input, and a single Python resolver that every downstream call site uses. The MCP `sub_agent(...)` surface is unchanged in this phase — adapters are scaffolded but not yet wired into dispatch.
**Depends on:** Phase 3 (Claude Code path is the byte-identical baseline that the `claude` adapter must lift-and-shift)
**Requirements:** CLI-01, CLI-02, CLI-03, ADAPT-01, TEST-02, TEST-05
**Success Criteria:** (observable — phase complete when ALL hold)
  1. **Env switch read once at boot.** With `SUBAGENT_CLI` unset OR empty string OR `claude` on the host, `docker inspect <sandbox>` shows `SUBAGENT_CLI=claude` in `Env` and the orchestrator startup log emits a single banner `[MCP] Sub-agent runtime: claude`. With `SUBAGENT_CLI=codex` or `opencode` set, the same banner reflects the chosen value and the same env var is propagated into every spawned container.
  2. **Invalid value fails loud.** Setting `SUBAGENT_CLI=cline` (typo) on the host causes the orchestrator to refuse to start with a single-line error naming the offending value and listing the three accepted values. The orchestrator does NOT silently fall back to `claude`.
  3. **Resolver is the single source of truth.** A pure-Python `cli_runtime.resolve_cli()` returns one of `Cli.CLAUDE | Cli.CODEX | Cli.OPENCODE`; `grep -rn 'SUBAGENT_CLI ==' computer-use-server/` returns zero matches outside `cli_runtime.py` (no scattered string comparisons). The `cli_adapters/` package directory exists with `__init__.py` exposing the adapter interface.
  4. **Backwards compat is byte-identical.** `pytest tests/orchestrator/test_cli_runtime.py` is fully green and asserts the unset/empty/`claude` paths produce identical resolver output. The MCP `sub_agent` tool signature and behaviour are unchanged in this phase (adapters are scaffolded only — dispatch flip happens in Phase 7).
  5. **`init.sh` is untouched.** `tests/test_init_sh_unchanged.sh` runs in CI and asserts `openwebui/init.sh` byte-equals the v0.9.2.0 baseline; the test fails if any later phase modifies it.

**Plans:** 5 plans
- [ ] `04-01-PLAN.md` — SUBAGENT_CLI constant + allowlist hard-fail validation in docker_manager.py + extra_env injection + cli_runtime.py with Cli StrEnum and resolve_cli() (CLI-01, CLI-02, CLI-03)
- [ ] `04-02-PLAN.md` — cli_adapters/ package skeleton: CliAdapter Protocol + SubAgentResult dataclass + ClaudeAdapter byte-identical lift-and-shift (DORMANT) + Codex/OpenCode stubs (ADAPT-01, CLI-03)
- [ ] `04-03-PLAN.md` — warn_subagent_cli() banner in docker_manager.py + app.py lifespan wiring (CLI-01)
- [ ] `04-04-PLAN.md` — Tests: TEST-02 resolver suite + golden-snapshot ClaudeAdapter byte-compat + TEST-05 init.sh sha256 regression (TEST-02, TEST-05)
- [ ] `04-05-PLAN.md` — Doc amendments: drop "lenient fallback" wording from research/SUMMARY.md + research/PITFALLS.md Pitfall 12 + ROADMAP Phase 4 line, per CONTEXT.md D1 hard-fail decision (CLI-02)

### Phase 5: Adapter layer (per-CLI argv + result parsing) (v0.9.2.1)

**Goal:** Three CLI adapters live behind a single `cli_runtime.dispatch(...)` entry point. The `claude` adapter is a lift-and-shift (byte-identical output for `SUBAGENT_CLI=claude` vs v0.9.2.0 baseline). Codex and OpenCode adapters build their own argv, parse their own JSON output, and return a normalised `SubAgentResult`. `mcp_tools.sub_agent(...)` becomes a thin orchestration layer over `cli_runtime.dispatch(...)`.
**Depends on:** Phase 4 (resolver + scaffolding must exist before adapters are wired)
**Requirements:** ADAPT-02, ADAPT-03, ADAPT-04, ADAPT-05, ADAPT-06, TEST-03
**Success Criteria:** (observable — phase complete when ALL hold)
  1. **Claude path is byte-identical to v0.9.2.0.** Golden-snapshot test `tests/orchestrator/test_cli_adapters.py::test_claude_argv_byte_compat` passes — argv emitted by `claude_adapter.build_argv(...)` matches the captured v0.9.2.0 invocation exactly. `mcp_tools.sub_agent(model="sonnet")` returns the same shape it did before.
  2. **Codex adapter ships.** `codex_adapter.build_argv(...)` emits `codex exec --ephemeral --json --output-last-message <tmpfile> "<system_prompt + task preamble>"` with `--cd` set to a `/tmp/codex-agents-<uuid>/` dir; `parse_result(...)` consumes captured `turn.completed`/`item.completed` JSONL fixtures and returns `SubAgentResult(text, tokens_in, tokens_out, cost_usd=None, raw_events=[…])`.
  3. **OpenCode adapter ships.** `opencode_adapter.build_argv(...)` emits `opencode run "<prompt>" --model <provider/model> --format json --dangerously-skip-permissions`; `parse_result(...)` consumes captured opencode event-stream fixtures and returns the same `SubAgentResult` dataclass.
  4. **Per-CLI model resolution works.** `resolve_subagent_model("sonnet", Cli.CLAUDE)` returns today's Claude ID; `resolve_subagent_model("sonnet", Cli.OPENCODE)` returns `anthropic/claude-sonnet-4-6`; `resolve_subagent_model("sonnet", Cli.CODEX)` returns the codex default (`gpt-5-codex` unless `CODEX_MODEL` overrides). Direct provider/model strings pass through unchanged.
  5. **MCP signature unchanged.** `sub_agent(task, max_turns=25, model="sonnet")` works for every existing skill caller; no skill file is modified in this phase. `pytest tests/orchestrator/test_cli_adapters.py` is fully green with fixture-based per-CLI tests committed to `tests/fixtures/cli/`.

**Plans:** TBD

### Phase 6: Per-CLI auth + config rendering (v0.9.2.1)

**Goal:** Each CLI sees only its own auth env vars (no auth bleed); OpenCode reads `/tmp/opencode.json` (NOT volume) with `{env:VAR}` substitution; Codex reads `~/.codex/config.toml` rendered conditionally on `OPENAI_BASE_URL`; both new CLIs are installed in the image at pinned versions and resolvable on `$PATH`.
**Depends on:** Phase 5 (adapters expect specific env vars to be present in the container)
**Requirements:** AUTH-01, AUTH-02, AUTH-03, AUTH-04, TEST-01, TEST-06
**Success Criteria:** (observable — phase complete when ALL hold)
  1. **Auth allowlist works.** With all three of `ANTHROPIC_AUTH_TOKEN`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY` set on the host and `SUBAGENT_CLI=opencode`, `docker inspect <sandbox>` shows ONLY the OpenCode passthrough set in `Env` — `OPENAI_API_KEY` and `ANTHROPIC_AUTH_TOKEN` are NOT injected. Verified per CLI by `tests/orchestrator/test_cli_runtime.py::test_passthrough_isolation`.
  2. **OpenCode config is secret-free.** With `SUBAGENT_CLI=opencode`, the file `/tmp/opencode.json` exists in the container, `OPENCODE_CONFIG=/tmp/opencode.json` is set, and `grep -E 'sk-|or-v1-' /tmp/opencode.json` returns zero matches — only `{env:OPENROUTER_API_KEY}` substitution syntax. Volume `/home/assistant/` contains no `auth.json`.
  3. **Codex config conditional.** With `SUBAGENT_CLI=codex` and `OPENAI_BASE_URL` set, `~/.codex/config.toml` contains a `[model_providers.X]` block; with only `OPENAI_API_KEY` set, the same file exists but the block is absent. `codex --version` runs cleanly in both paths.
  4. **Marker-gated bootstrap.** Entrypoint writes the per-CLI config files only when sentinel `/tmp/.cli-runtime-initialised` is absent; on container restart the sentinel is present and the heredoc is skipped. `openwebui/init.sh` itself is NOT modified (verified by Phase 4's regression-grep test still passing).
  5. **All three CLIs installed and verified.** `tests/test-docker-image.sh` runs `claude --version`, `codex --version`, `opencode --version` — all return exit 0. The same script runs end-to-end with `SUBAGENT_CLI` set to each value, with stub auth env vars, and asserts (a) the container starts, (b) the chosen CLI is the autostart target (placeholder pre-Phase 7), (c) `--version` exit-code 0. No real LLM calls.

**Plans:** TBD

### Phase 7: Cost guardrail + ttyd UX (v0.9.2.1)

**Goal:** When the operator opens the in-browser ttyd terminal, it auto-launches the chosen CLI based on `SUBAGENT_CLI`. An escape hatch (`NO_AUTOSTART=1`) drops the operator into plain bash. `mcp_tools.sub_agent(...)` is flipped to dispatch through `cli_runtime` for all three CLIs end-to-end (the actual flip is gated on Phase 5's adapter readiness; Phase 7 lights it up).
**Depends on:** Phase 6 (CLIs must be installed + auth wired before ttyd autostart can succeed)
**Requirements:** TERM-01, TERM-02, TERM-03, TEST-04
**Success Criteria:** (observable — phase complete when ALL hold)
  1. **ttyd autostart honours `SUBAGENT_CLI`.** Opening the in-browser terminal with `SUBAGENT_CLI=codex` lands the operator at the `codex` TUI prompt (not bash, not claude); same for `opencode`; `claude` (or unset) keeps the existing claude-autostart UX. Implemented in `.bashrc` via `exec "${SUBAGENT_CLI:-claude}"`; `app.py` ttyd command is unchanged.
  2. **Escape hatch works.** Opening a terminal with `NO_AUTOSTART=1` in the container env produces a plain bash prompt with a one-line discoverability hint in the terminal welcome text. Verified by `tests/test-docker-image.sh` smoke step.
  3. **Marker rename is backwards-compatible.** Existing volumes that have `CLAUDE_AUTOSTARTED=1` still see autostart fire exactly once on the next session because the new marker `SUBAGENT_AUTOSTARTED` is independently checked; no double-autostart, no regression for existing deployments.
  4. **End-to-end dispatch works for all three CLIs.** `pytest tests/orchestrator/test_sub_agent_dispatch.py` exercises `sub_agent(...)` with each `SUBAGENT_CLI` value (subprocess boundary mocked); the test asserts dispatch routes to the correct adapter and the MCP signature is unchanged. The `mcp_tools.sub_agent` flip from Phase 5's scaffolding to live dispatch through `cli_runtime` is in effect.
  5. **Cost-guardrail caveat is observable.** For non-claude CLIs, `cost_usd=None` is rendered as `cost: unavailable` in the sub-agent result blob (never `$0.00`). `SUB_AGENT_TIMEOUT` is the documented backstop for codex/opencode; the caveat is surfaced in the result string when applicable.

**Plans:** TBD

### Phase 8: Operator docs (v0.9.2.1)

**Goal:** An operator on a clean clone can flip `SUBAGENT_CLI=opencode`, plug in an OpenRouter key, and run sub-agents against qwen3-coder end-to-end by following copy-paste blocks. README, INSTALL, and `.env.example` link to the new doc; CHANGELOG v0.9.2.1 entry credits prior art.
**Depends on:** Phase 7 (docs reference the final shipped flag set + dispatch behaviour)
**Requirements:** DOCS-MULTICLI-01, DOCS-MULTICLI-02, DOCS-MULTICLI-03, DOCS-MULTICLI-04
**Success Criteria:** (observable — phase complete when ALL hold)
  1. **`docs/multi-cli.md` exists and is end-to-end navigable.** English-only, SPDX `BUSL-1.1` header, follows the saved-feedback "do this, then this, verify" template. Sections: (a) what `SUBAGENT_CLI` does and why; (b) install per CLI (already in image); (c) env vars per CLI in copy-paste blocks; (d) verification commands per CLI; (e) what changes when you flip the switch.
  2. **Worked OpenCode + qwen3-coder + OpenRouter recipe is reproducible.** `docs/multi-cli.md` includes an exact `.env` block (`SUBAGENT_CLI=opencode`, `OPENROUTER_API_KEY=…`, `OPENCODE_MODEL=openrouter/qwen/qwen-3-coder`), the exact `docker compose up` command, a sample `sub_agent(...)` invocation, and the expected output shape. A new operator on a clean clone reproduces it without consulting other docs.
  3. **Cross-links land.** `README.md` "Sub-agent" / "Open WebUI Integration" sections and `docs/INSTALL.md` both link to `docs/multi-cli.md`. `.env.example` grows a `# === Optional: Multi-CLI sub-agent runtime ===` block with `SUBAGENT_CLI=` (commented) and the three auth-env templates per CLI.
  4. **CHANGELOG v0.9.2.1 entry is complete.** `CHANGELOG.md` has a v0.9.2.1 heading summarising the milestone, listing every CLI-/ADAPT-/AUTH-/TERM-/TEST-/DOCS- requirement ID, and crediting prior art (Codex docs, sst/opencode docs, OpenRouter qwen3-coder model page).

**Plans:** TBD

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. System Prompt Extraction (v0.8.12.7)         | 1/1 | ✅ Complete | 2026-04-12 |
| 2. Preview Filter UX (v0.8.12.8)                | 1/1 | ✅ Complete | 2026-04-12 |
| 3. Claude Code Gateway Compatibility (v0.8.12.9)| 3/3 | ✅ Shipped  | 2026-04-25 (v0.9.2.0) |
| 4. Env switch + adapter scaffolding (v0.9.2.1)  | 0/5 | Planned     | - |
| 5. Adapter layer (v0.9.2.1)                     | 0/? | Not started | - |
| 6. Per-CLI auth + config rendering (v0.9.2.1)   | 0/? | Not started | - |
| 7. Cost guardrail + ttyd UX (v0.9.2.1)          | 0/? | Not started | - |
| 8. Operator docs (v0.9.2.1)                     | 0/? | Not started | - |

---
*Updated 2026-04-26 — Phase 4 planned: 5 plans (env switch + cli_runtime, cli_adapters package, banner wiring, tests, doc amendments). Phase 4 line amended from "lenient-fallback" to "hard-fail-on-invalid" per CONTEXT.md D1 decision.*
