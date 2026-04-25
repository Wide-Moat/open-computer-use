# Pitfalls Research

**Domain:** Multi-CLI sub-agent runtime (claude / codex / opencode) behind a single MCP `sub_agent` tool, in the Open Computer Use orchestrator + per-chat sandbox container architecture.
**Researched:** 2026-04-25
**Confidence:** MEDIUM-HIGH for codex (well-documented, pitfalls are concrete), MEDIUM for opencode (config schema is stable but flags are pre-1.0 and the project recently forked — sst/opencode vs opencode-ai/opencode), HIGH for claude regression risk (we own the current contract).
**Categories used (per downstream consumer):** AUTH / CONTRACT / OPS / TEST / UX. Each pitfall is tagged.

> **Architectural anchor:** the surface that must NOT change is `mcp_tools.sub_agent(...)` at `computer-use-server/mcp_tools.py:860–1178`. Today it shells out `claude -p ... --append-system-prompt ... --output-format json` inside the per-chat container. The CLI swap MUST happen below that surface — at an adapter layer — and `SUBAGENT_CLI` MUST be read once at orchestrator boot, not per call (per `PROJECT.md` Key Decisions).

---

## Critical Pitfalls

### Pitfall 1: Auth bleed — env vars from one CLI silently activate another

**Category:** AUTH

**What goes wrong:**
Operator sets `SUBAGENT_CLI=opencode` + `OPENROUTER_API_KEY=...` and expects qwen3.6 via OpenRouter. But the host `.env` still has `OPENAI_API_KEY=sk-...` (left over from a Codex experiment) AND `ANTHROPIC_AUTH_TOKEN=...` (the Phase 3 default). Two failure modes:
1. **OpenCode silently picks the wrong provider** because providers are loaded from any key it sees in env (`opencode.ai/docs/config/`). The model resolves under "anthropic" or "openai" namespace, not openrouter, and bills the wrong account.
2. **Codex falls back to the public OpenAI API** when `OPENAI_BASE_URL` is unset, even though the operator wanted a self-hosted gateway — the missing env is a silent default, not an error.

**Why it happens:**
Each CLI has independent auth-discovery logic. Today `docker_manager._create_container()` (`docker_manager.py:455–463`) injects `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, and the `CLAUDE_CODE_PASSTHROUGH_ENVS` tuple into every container, unconditionally. Adding two more CLIs without scoping means all three see all three sets of env vars.

**How to avoid (actionable):**
- In `docker_manager._build_container_env()`, gate auth env injection on `SUBAGENT_CLI`:
  - `claude` → inject `ANTHROPIC_*` only
  - `codex` → inject `OPENAI_API_KEY`, `OPENAI_BASE_URL` only
  - `opencode` → inject `OPENROUTER_API_KEY` (or whichever provider the operator selected via `OPENCODE_PROVIDER`) only
- Explicitly **strip** the other CLIs' env from the container so a left-over `.env` line never silently re-routes traffic. Use an allowlist not a blocklist.
- Document the matrix in `docs/CLOUD.md` with copy-paste blocks (per `feedback_step_by_step_docs.md`).

**Warning signs:**
LiteLLM/Anthropic dashboard shows traffic when operator believes they cut over to OpenRouter. Sub-agent latency or token cost changes shape unexpectedly. Cost on a "free" model > 0.

**Phase / test that catches it:**
Phase 1 (env-switch resolver) + new orchestrator test `test_subagent_cli_env_isolation.py`: parametrise `SUBAGENT_CLI ∈ {claude, codex, opencode}`, assert the container `environment` dict contains ONLY the auth keys for that CLI and NOT the others, even when all three are set on the host.

---

### Pitfall 2: System-prompt contract divergence — same skill text, three different slots

**Category:** CONTRACT

**What goes wrong:**
Today the sub-agent system prompt (built in `mcp_tools.py:980–1005`, includes `<critical_instruction>`, `<environment>`, `<available_skills>`) is passed via `claude --append-system-prompt`. **Append** means it's added on top of Claude Code's own baseline system prompt.

- **Codex** as of 2026-04 does **not** ship a stable `--append-system-prompt` flag — the feature is open as `openai/codex#11588`. There is `--system-prompt-file` in some builds but its semantics are *replace*, not *append*. If the adapter naively maps our prompt into `--system-prompt-file`, Codex loses its built-in coding-agent baseline (tool use, file editing rules) — sub-agent quality collapses without any error.
- **OpenCode** uses prompt files keyed by mode (see `opencode.ai/docs/modes/`), not a CLI flag. There is no documented runtime "append" — feeding our prompt as a one-shot positional argument means it competes with the user `task` text, not with the system prompt.

**Why it happens:**
The three CLIs disagree on what "system prompt" means. Claude Code: append to baseline. Codex: replace, and the flag may not exist. OpenCode: configured per-mode in JSON, not per-invocation.

**How to avoid (actionable):**
- Treat the skill prompt as a **task preamble**, not a system-prompt-replacement. The adapter must concatenate `system_prompt + "\n\n---\n\n" + task` and feed the combined string as the *task argument* for codex/opencode. Lose the "append vs replace" distinction by never relying on it.
- For Claude, keep `--append-system-prompt` (no regression).
- For OpenCode, generate a per-container `~/.config/opencode/opencode.json` (or `OPENCODE_CONFIG` pointing at a tmp file) with our skill content baked into the `instructions` section — written by `_create_container()` like the existing `~/.mcp.json` write at `mcp_tools.py:932–941`.
- Adapter contract: each CLI adapter returns `(argv, env_overrides, post_run_parser)`. Force all three through the same dispatch so the contract is provable in a unit test.

**Warning signs:**
Sub-agent for codex/opencode skips the `<critical_instruction>` block (doesn't re-read `task_plan.md` after compaction); sub-agent doesn't know about `<available_skills>` and re-implements PowerPoint from scratch instead of using the pptx skill.

**Phase / test that catches it:**
Phase 2 (adapter layer) + new test `test_subagent_prompt_assembly.py`: parametrise per CLI, assert the **rendered argv string** contains the `task_plan.md` reference and the skills text. Smoke test (Phase 5) verifies the sub-agent actually used the plan file by checking `/home/assistant/task_plan.md` was read.

---

### Pitfall 3: Model alias semantics — `"sonnet"` reaches codex/opencode and silently 400s

**Category:** CONTRACT

**What goes wrong:**
`mcp_tools.sub_agent.ALIAS_MAP` (`mcp_tools.py:909–913`) maps `sonnet/opus/haiku` → real Anthropic model IDs from `ANTHROPIC_DEFAULT_*` envs. If `SUBAGENT_CLI=codex` and a skill calls `sub_agent(model="sonnet", ...)`:
- The alias resolver still resolves to `claude-sonnet-4-6` (Anthropic ID).
- That string is passed to `codex exec --model claude-sonnet-4-6` → OpenAI rejects with 400 / "model not found".
- The `_format_sub_agent_result` parser (`mcp_tools.py:812–857`) looks for Claude's specific `{"type":"result"}` JSONL line, doesn't find it, falls back to the raw error string. Operator sees a confusing 400 message wrapped in `**Sub-Agent Completed** (success)`.

Symmetric trap: `CLAUDE_CODE_SUBAGENT_MODEL=claude-sonnet-4-6` env left set from an old config; operator flips `SUBAGENT_CLI=opencode`; the alias resolver still picks the Anthropic ID up. OpenCode's resolver fails differently (provider not found, not model not found), still no error surface.

**Why it happens:**
The alias map is currently global and Anthropic-only. The CLI switch is below the alias resolver in the call stack.

**How to avoid (actionable):**
- Move the alias map **into** each CLI adapter. `claude` adapter keeps the Anthropic map; `codex` adapter has its own (`gpt-5`, `gpt-5-mini`, `o3` → real OpenAI IDs) or rejects unknown aliases with a clear error; `opencode` adapter requires `provider/model` form (per `opencode.ai/docs/cli/`) and rejects single-word aliases unless mapped.
- Make alias resolution **hard-fail** when a Claude-flavored alias hits a non-Claude CLI: log `"Model alias 'sonnet' is Claude-only; SUBAGENT_CLI=codex requires a GPT model id. Set SUB_AGENT_DEFAULT_MODEL=gpt-5 or similar."` Don't silently substitute.
- Default model envs split per CLI: keep `SUB_AGENT_DEFAULT_MODEL` (claude default), add `CODEX_SUB_AGENT_DEFAULT_MODEL` and `OPENCODE_SUB_AGENT_DEFAULT_MODEL`. Resolver picks based on `SUBAGENT_CLI`.

**Warning signs:**
Sub-agent immediately returns "model not found" or "provider not found" without burning any tokens. `--print` exit code non-zero on first call after CLI switch.

**Phase / test that catches it:**
Phase 1 (resolver) + `test_subagent_model_alias_per_cli.py`: assert that `("codex", "sonnet")` raises a clear adapter error and does NOT silently produce `claude-sonnet-4-6`.

---

### Pitfall 4: Output-format drift — `_format_sub_agent_result` is hardcoded to Claude's JSONL schema

**Category:** CONTRACT

**What goes wrong:**
`_format_sub_agent_result()` (`mcp_tools.py:812–857`) parses Claude Code's `--output-format json` schema: `{"type":"result", "result", "total_cost_usd", "num_turns", "is_error", "session_id"}`. Codex's `exec --json` emits **different** event types — `turn.started`, `turn.completed`, `item.completed`, etc. (verified at `developers.openai.com/codex/noninteractive`). OpenCode's `run` emits *yet a third* schema. Three concrete failures:
1. `response_text` ends up empty → fallback `response_text = output` returns the full JSONL stream. The skill caller sees thousands of lines of raw JSONL instead of the assistant's final message.
2. `cost`, `turns`, `session_id` all default to 0/empty. The cost-guardrail story (COSTLY markings) becomes a lie.
3. The JSONL-tail streaming logic (`_stream_session_logs`, `mcp_tools.py:1029–1098`) reads `/home/assistant/.claude/projects/-home-assistant/*.jsonl` — that directory only exists for Claude. For codex/opencode the heartbeat falls into the "no jsonl" fallback branch and just sends elapsed-time pings — operator loses the live progress UX.

**Why it happens:**
Output parsing was built when the contract was "claude or nothing." It's tightly coupled to Claude Code's JSONL.

**How to avoid (actionable):**
- Each adapter returns a `parse_output(stdout: str) -> SubAgentResult` callable with a normalised dataclass: `result_text, cost_usd, turns, is_error, session_id, jsonl_log_path`. Move `_format_sub_agent_result` into `claude_adapter.parse_output`.
- For codex: parse `--json` JSONL events; sum `turn.completed.usage` for cost; final `result_text` = last `item.completed` of type message.
- For opencode: use whatever `opencode run` emits on stdout; document what's available (cost may be unrecoverable on some providers — set `cost_usd=None`, NOT `0.0`, so the UI can render "cost: unavailable" instead of "$0.00").
- For the live-log heartbeat: each adapter exposes its log path (or returns `None`, falling through to elapsed-time-only progress).

**Warning signs:**
After flipping the switch, sub-agent return strings get 10× longer (raw JSONL). Cost in result line always reads `$0.0000`. No live progress notifications.

**Phase / test that catches it:**
Phase 2 (adapter) + `test_subagent_result_parsing.py` per CLI with **fixture** stdout dumps from each CLI. Phase 5 smoke test asserts result string < 4 KB and contains the expected final-message marker.

---

### Pitfall 5: Cost runaway — `max_turns` is Claude-only; codex/opencode have no equivalent

**Category:** OPS

**What goes wrong:**
Today `--max-turns 25` (`mcp_tools.py:956`) is the cost guardrail. Codex `exec` does **not** have `--max-turns`; it has approval-mode and sandbox-mode flags but turn count is internally managed. OpenCode similarly doesn't expose a hard turn cap from the CLI in non-interactive mode (`anomalyco/opencode#13851` notes non-interactive UX gaps). Concrete failure: a buggy skill prompt sends the codex sub-agent into a 200-turn loop. `SUB_AGENT_TIMEOUT=3600` is the only backstop — that's $50+ on a frontier model before the wall-clock kicks in. The COSTLY warning in the docstring becomes a lie because the structural cap doesn't exist.

**Why it happens:**
Open assumption that all CLIs respect the same operational primitives.

**How to avoid (actionable):**
- Treat `SUB_AGENT_TIMEOUT` (env, currently 3600s) as the **primary** guardrail for codex/opencode and document this in the adapter README. Lower the default to `1800` for non-claude CLIs unless explicitly raised.
- Codex: pass `--max-output-tokens` if available + use `OPENAI_MAX_TURNS` style env if Codex supports it (verify per release).
- OpenCode: configure `mode.<mode>.maxIterations` in the generated `opencode.json` (per `opencode.ai/docs/modes/`), default to `max_turns` value from the MCP call.
- Adapter MUST translate the MCP-level `max_turns` into whatever each CLI exposes — even if that's just "set timeout = max_turns × 60s estimate." Never silently drop the constraint.
- Add a per-CLI **sentinel turn cap** test: feed an infinite-loop prompt (e.g., "list all positive integers"), assert sub-agent terminates within `max_turns × per_turn_budget` regardless of CLI.

**Warning signs:**
Single sub-agent invocation costs > $5. Container's `pgrep -f 'codex|opencode'` still alive at `SUB_AGENT_TIMEOUT - 30s`.

**Phase / test that catches it:**
Phase 4 (cost guardrails parity) + `test_subagent_cost_caps.py` — invoke each CLI with a runaway prompt against a mocked provider that always returns "continue", verify sub-agent terminates by `max_turns` (or by timeout for CLIs that don't honour turns).

---

### Pitfall 6: CLI version drift breaks the adapter, but tests still pass

**Category:** TEST

**What goes wrong:**
Both codex and opencode are pre-1.0 and ship breaking flag changes between minor versions (codex `--json` JSON output schema docs go stale — `openai/codex#4776`; opencode is mid-fork between `sst/opencode` and `opencode-ai/opencode`). Without pinning, tomorrow's `npm install -g` rebuild can:
- Rename `--max-output-tokens` → `--output-budget` → adapter generates wrong argv, codex prints "unknown flag" to stderr, exit code 2, _format_sub_agent_result returns empty text. The test suite as it stands (which only verifies `which codex` returns OK) never catches this.
- Change `exec --json` event names → output parser silently returns empty `result_text`.

**Why it happens:**
`tests/test-docker-image.sh` line 84 only checks `which $tool` — it proves binaries exist on PATH, nothing about flag compatibility.

**How to avoid (actionable):**
- **Pin** in Dockerfile: `npm install -g @openai/codex@${CODEX_VERSION}` and `npm install -g opencode-ai@${OPENCODE_VERSION}` (mirror the existing `CLAUDE_CODE_VERSION` pattern at `Dockerfile:218`). NEVER `@latest` for the new CLIs.
- Add a `tests/test-docker-image.sh` step **per CLI** that runs `codex exec --json -m <fake-model> "echo"` (against a stub provider) and parses stdout, asserting our output-parser still works. NOT just `--version`.
- Track upstream releases — add a Dependabot/Renovate config for the npm packages so version bumps land in a PR with the test-suite run, not as a silent `@latest` drift.
- Test contract: each adapter exposes `verify_cli_compat() -> bool` that the smoke step calls; fails CI if the CLI's flag schema drifted.

**Warning signs:**
`test-docker-image.sh` passes; production sub-agent returns empty result text. Operators report "sub-agent returns nothing" on their first try after image bump.

**Phase / test that catches it:**
Phase 5 (test coverage) + new test step `[12/14] CLI flag compatibility` in `test-docker-image.sh` — runs a real `codex exec --help` and `opencode run --help`, greps for the exact flags the adapter emits.

---

### Pitfall 7: OpenCode config persists in the volume → one user's API key leaks to the next

**Category:** AUTH (security)

**What goes wrong:**
Per `opencode.ai/docs/config/`, OpenCode reads from `OPENCODE_CONFIG` / `OPENCODE_CONFIG_DIR` and stores credentials at `~/.local/share/opencode/auth.json` after `opencode auth login`. The container's per-chat workspace volume binds to `/home/assistant` (`docker_manager.py:530`). If a user runs `opencode auth login` in the ttyd terminal once, the credentials land in the volume. Next time *the same `chat_id`* is reused — possibly by a different operator on a shared deployment with `SINGLE_USER_MODE=""` (lenient default — see `CONCERNS.md` Single-User Mode Shared Container State Leak) — the API key is reused. **Worse**: the Dockerfile entrypoint already mirrors `/home/assistant` config to `/root` for some dotfiles (see `Dockerfile:391–392`), repeat-pattern would magnify the leak.

**Why it happens:**
Auth-via-config-file is OpenCode's default; the project's volume mount makes that file persistent; the project's lenient single-user-mode default makes containers shareable.

**How to avoid (actionable):**
- **Do not** use `opencode auth login` for credential management. Source keys exclusively from env (`OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, etc.) injected per container by `_create_container()` (Pitfall 1's allowlist).
- The generated `opencode.json` written by the adapter MUST use `"apiKey": "{env:OPENROUTER_API_KEY}"` — never bake the key into the file (per `opencode.ai/docs/config/` env-substitution syntax).
- Write the generated `opencode.json` to `/tmp/opencode.json` (NOT in the volume), set `OPENCODE_CONFIG=/tmp/opencode.json` in the container env. `/tmp` is wiped on container removal.
- In docs (`docs/CLOUD.md`): explicit warning that `opencode auth login` is unsupported in this image; key flow is env-only.
- Audit on container creation: `_create_container()` deletes `~/.local/share/opencode/auth.json` if present (defensive scrub for resurrected containers).

**Warning signs:**
`auth.json` appears in `chat-${chat_id}-workspace` volume after a session. OpenRouter usage shows traffic from a chat where the operator set no `OPENROUTER_API_KEY`.

**Phase / test that catches it:**
Phase 3 (opencode adapter) + `tests/security/test_opencode_no_persistent_auth.py` — start a container, write a fake `auth.json`, restart, assert it's gone. Volume-leak test in `test-docker-image.sh` already greps for `auth.json` in the volume.

---

### Pitfall 8: Test combinatorics — 3× CLIs × N skills = unmaintainable runtime

**Category:** TEST

**What goes wrong:**
Naively parametrising every existing sub-agent test by `SUBAGENT_CLI` triples test runtime and CI cost. Worse, smoke-testing the full dispatch (real container, real CLI binary) per CLI per test triples Docker image pulls and external API calls. Test budget explodes; team starts skipping tests; coverage decays.

**Why it happens:**
Default reaction to multi-implementation features is "test all combinations equally."

**How to avoid (actionable):**
- **Resolver-level tests** (env switch, model alias, prompt assembly, output parsing): parametrise by CLI — these are pure-function unit tests, fast.
- **Adapter-level tests**: per-CLI fixture-based tests using **recorded stdout** (no real CLI invocation). One fixture file per CLI per scenario.
- **Smoke / e2e in `test-docker-image.sh`**: ONE dispatch per CLI (3 total), with a *trivial prompt* against either a stub provider or a free model. Not the full skill suite.
- **Skills tests** stay CLI-agnostic: skills consume the normalised `sub_agent` return contract, so they're tested once against a mocked sub-agent that returns a fixture-shaped response.
- Document the matrix in `tests/README.md` so the next contributor doesn't reflexively "add coverage" by parametrising everything.

**Warning signs:**
CI runtime > 2× current. Test author starts gating tests with `pytest.mark.skip(reason="slow per-CLI")`.

**Phase / test that catches it:**
Phase 5 (test coverage) — review checklist before merge: "Is this a contract test (parametrise) or a smoke test (one per CLI)?"

---

### Pitfall 9: ttyd auto-execs the chosen CLI — operator can't get a plain bash

**Category:** UX

**What goes wrong:**
The Dockerfile entrypoint installs an autostart hook: `[ -z "$CLAUDE_AUTOSTARTED" ] && [ -n "$PS1" ] && export CLAUDE_AUTOSTARTED=1 && claude` (`Dockerfile:394–395`). The milestone says ttyd should launch the chosen CLI — naive port: change `claude` → `${SUBAGENT_CLI}`. Result: every interactive shell in the ttyd preview drops the operator straight into codex/opencode's TUI. If the operator wants `ls`, `cat /home/assistant/task_plan.md`, or to abort and start over, they must know each TUI's exit incantation (different per CLI: `Ctrl-D` for some, `:q` for others, `exit` keyword).

**Why it happens:**
"Replace claude with $SUBAGENT_CLI" is a one-line search-and-replace that works for the happy path and breaks the escape hatch.

**How to avoid (actionable):**
- Keep the autostart hook but make it skippable: respect `CLAUDE_AUTOSTARTED` (existing) AND a new `NO_AUTOSTART=1` env, AND check for a sentinel file `/tmp/.no_autostart` so a power user can `touch /tmp/.no_autostart` from one terminal and get plain bash on the next.
- Document in `docs/CLOUD.md`: "To get a plain bash shell, run `NO_AUTOSTART=1 bash` or open a second terminal tab and `touch /tmp/.no_autostart`."
- Smoke test: `test-docker-image.sh` step that runs the entrypoint with `NO_AUTOSTART=1` and asserts the shell prompt is bash, not the CLI banner.

**Warning signs:**
First user complaint after release: "I can't get to the regular terminal."

**Phase / test that catches it:**
Phase 4 (ttyd UX) + smoke test in `test-docker-image.sh`.

---

### Pitfall 10: `init.sh` regression — adding `SUBAGENT_CLI` to bootstrap turns it into "always-sync"

**Category:** OPS (explicit user-memory constraint)

**What goes wrong:**
Per saved feedback `feedback_init_sh_marker.md`: `init.sh` is one-shot — it seeds Valves from env on first boot, then a marker file `/app/backend/data/.computer-use-initialized` blocks re-runs. The temptation when adding `SUBAGENT_CLI` is to "make it visible in Open WebUI Valves so users can flip it from the admin UI" — and to "re-sync env to Valve on every restart so a `.env` change actually propagates." That breaks the marker-gated contract: any operator edit to the Valve in the admin UI gets clobbered on the next container restart.

Specifically: this milestone's `SUBAGENT_CLI` lives on the **computer-use-server** container (Python orchestrator), NOT on the **open-webui** container where init.sh runs. There is **no** Valve to seed. Adding one is the wrong shape.

**Why it happens:**
Pattern-matching: "every config knob should be a Valve so the admin UI shows it." Untrue for orchestrator-side env; init.sh is an Open WebUI bootstrapper, not an orchestrator config sync.

**How to avoid (actionable):**
- **Do not touch `openwebui/init.sh`.** `SUBAGENT_CLI` is a `docker-compose.yml` env on the computer-use-server service — set it once, restart the server, done.
- Add a one-time startup **warning** in `docker_manager.py` (mirror `warn_if_public_base_url_is_default` at `docker_manager.py:113–136`): `warn_if_subagent_cli_unset` prints a banner if `SUBAGENT_CLI` is empty, encouraging explicit choice rather than silent claude default. (Default behaviour stays claude per Pitfall 12; the warning is informational, not gating.)
- If a future milestone genuinely needs the choice exposed in the WebUI, that goes in a separate filter Valve update — not in `init.sh`'s seeding flow.
- Add a CI/grep check: `git diff` of this milestone MUST NOT touch `openwebui/init.sh`. Block the PR if it does.

**Warning signs:**
PR diff touches `init.sh`. User reports "my admin-UI Valve changes get reset when I restart open-webui."

**Phase / test that catches it:**
Phase 1 (env switch) + grep gate in `test-project-structure.sh`: assert `init.sh` was not modified by this milestone (compare to a known-good hash, or just exclude with a "milestone scope" comment).

---

### Pitfall 11: `test-docker-image.sh` passes for all the wrong reasons

**Category:** TEST

**What goes wrong:**
Current test (line 84): `for tool in mmdc tsc tsx claude; do which $tool ...`. Adding `codex opencode` to the loop is the obvious move. Three traps:
1. **Volume size budget breaks**: `/home/assistant` must stay < 1 MB (line 133). Both new CLIs are large npm packages. If they install user-scoped via `~/.config/opencode/` or `~/.codex/` on first use (codex creates `~/.codex/`), the volume bloats past 1 MB on first run and test 9 fails — but only after a real invocation, not on a fresh image.
2. **Entrypoint banner regex** (line 173): `grep -qE "(GITLAB_TOKEN|ANTHROPIC_AUTH_TOKEN|Claude Code configured)"`. If the entrypoint is updated to print a CLI-specific status banner ("Codex configured", "OpenCode configured"), the existing regex misses it; entrypoint test 11 fails silently as "ran but produced no recognisable banner."
3. **`which codex` passes for an empty wrapper**: if the npm install fails partway and leaves a shell stub, `which` succeeds but the binary 1-exits on every call. No assertion catches this.

**How to avoid (actionable):**
- Test 5 (CLI tools): for each new CLI add `which $tool && $tool --version` — verify binary actually runs.
- Test 9 (volume size): run the entrypoint **twice** before measuring `/home/assistant` size, so any first-run config-file creation is captured. If size grows past 1 MB, force the install to use system paths (`/usr/local/lib/...`) per the existing npm layout convention — config files writable at `/tmp/`.
- Test 11 (entrypoint banner): extend the regex to include all three CLIs' configured banners, gated on `SUBAGENT_CLI`.
- New test step (e.g. `[12/14] Sub-agent CLI dispatch`): run `claude --print "say OK"` (or codex/opencode equivalent) against a stub provider, assert the orchestrator's adapter parses non-empty result text.

**Warning signs:**
Test passes after image rebuild; first real sub-agent invocation in production fails with an error the test never exercised.

**Phase / test that catches it:**
Phase 5. Each new test step explicitly listed above; all three categories.

---

### Pitfall 12: Backwards compat — silently adding any new env mutates existing deployments

**Category:** CONTRACT

**What goes wrong:**
Existing deployments have no `SUBAGENT_CLI` set. If the orchestrator reads it with `os.getenv("SUBAGENT_CLI", "")` and adapter dispatch keys off the empty string, behaviour diverges silently from today's claude path: env-passthrough may shrink, model-alias resolver may stop honouring `ANTHROPIC_DEFAULT_SONNET_MODEL`, output parser may not recognise Claude's JSONL — even though no operator opted in.

**Why it happens:**
"Default = empty string" is the easy code path; "default behaviour byte-identical to today" requires an explicit `SUBAGENT_CLI=claude` fallback **before** any branching.

**How to avoid (actionable):**
- Read once at boot: `SUBAGENT_CLI = os.getenv("SUBAGENT_CLI", "claude").strip().lower() or "claude"`. Empty string and unset both → `"claude"`.
- Validate against a fixed allowlist `{"claude", "codex", "opencode"}`. Anything else → log error + fall back to `"claude"` (same lenient pattern as `SINGLE_USER_MODE`).
- For the `claude` branch, the adapter must be a **byte-identical wrapper** around today's code path: same argv, same env, same parser. Concretely: the existing `claude_command` construction at `mcp_tools.py:967–1019` should be lifted into `adapters/claude.py` unchanged — diff between old and new claude path is zero except for import.
- Regression test: snapshot today's `sub_agent` end-to-end output for a fixed prompt with a fixed mocked Claude response. New test asserts `SUBAGENT_CLI=""` and `SUBAGENT_CLI="claude"` produce identical orchestrator-side output.

**Warning signs:**
Existing test `test_mcp_tools.py` start failing on the milestone branch when no claude-related code "should" have changed.

**Phase / test that catches it:**
Phase 1 (env switch) + golden-snapshot test `test_subagent_claude_compat.py`.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| `if cli == "claude": ... elif "codex": ... elif "opencode": ...` chains scattered through `mcp_tools.py` | Fast first cut, no new modules | Every new feature touches three branches; the contract drifts; pitfalls 2/4/5 reappear at every change | NEVER — collapse into adapter classes from day one |
| Reuse `_format_sub_agent_result` for all three CLIs by adding `try/except json.JSONDecodeError` fallback | Looks like graceful degradation | Silent data loss (cost=0, turns=0) the operator never sees; Pitfall 4 in disguise | NEVER — return `None` for unavailable fields and surface "unavailable" in the UI |
| Pin codex/opencode versions to `@latest` in Dockerfile to "stay current" | Always get bug fixes | Pitfall 6 — flag drift breaks adapter without test signal | NEVER — pin and bump deliberately, like CLAUDE_CODE_VERSION |
| Add `SUBAGENT_CLI` Valve to `init.sh` so admins can switch in the WebUI | One-click switching | Breaks the marker-gated contract (Pitfall 10), violates `feedback_init_sh_marker.md` | NEVER — orchestrator env only, this milestone |
| Allow per-call `sub_agent(cli="codex", ...)` override "for flexibility" | Skills can pick CLI per task | Test surface = 3 × all skills; prompt-contract drift across calls; explicitly out-of-scope per `PROJECT.md` | Future milestone, only with an explicit per-call test matrix |
| Source codex/opencode auth from `~/.codex/auth.json` and `~/.local/share/opencode/auth.json` (their defaults) | "Just works" with `*-auth login` | Pitfall 7 — credentials persist across users in shared volume | NEVER — env-only auth, scrub config dirs on container creation |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Codex `exec --json` | Parse as `{"type":"result", ...}` (Claude schema) | Parse JSONL events `turn.completed`/`item.completed` per `developers.openai.com/codex/noninteractive` |
| Codex auth | Assume `OPENAI_API_KEY` = "use default OpenAI"; rely on Codex auto-discovery | Always set `OPENAI_API_KEY` AND `OPENAI_BASE_URL` together; document the LiteLLM gateway pattern (mirror Phase 3 `ANTHROPIC_BASE_URL`) |
| Codex sandboxing | Run `codex exec` without `--dangerously-bypass-approvals-and-sandbox` and wonder why it stalls on approval prompts | We are already in an isolated container — pass `--dangerously-bypass-approvals-and-sandbox` (`--yolo`) explicitly. Document why this is safe in this context |
| OpenCode config | Bake `apiKey` literal into `opencode.json` | Use env-substitution: `"apiKey": "{env:OPENROUTER_API_KEY}"` per `opencode.ai/docs/config/` |
| OpenCode model selection | Pass single-word model name (`qwen3.6`) | Always `provider/model` (e.g. `openrouter/qwen/qwen3.6-coder`) per CLI doc |
| OpenCode fork choice | `npm install -g opencode-cli` and hope it's the right one | Two competing forks exist (sst/opencode, opencode-ai/opencode) — pin to ONE explicitly in Dockerfile, document choice in `docs/CLOUD.md`. Open issue `anomalyco/opencode#13851` is on a third fork — be aware |
| Claude Code (regression) | Refactor `claude_command` construction during the move to adapter | Lift unchanged; defer refactor; the diff for the `claude` adapter must be import-only |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Per-call container `exec` to write `opencode.json` | Sub-agent first-token latency +1–2s | Write config once in `_create_container()` (mirror existing `~/.mcp.json` write at `mcp_tools.py:932–941`), not per `sub_agent` call | Visible immediately on warm container |
| Full JSONL read at end of run for parsing | Memory spike + slow result on 100-turn runs | Stream-parse during `_stream_session_logs` and accumulate the structured result; don't double-parse | At ~50 turns / 1 MB JSONL |
| `which codex` test only — no `--version` | Smoke-test passes with broken binary | Add `$tool --version` per Pitfall 11 | First production invocation post-image-bump |
| Three CLIs all installed even when only one is used | Image size +200–400 MB | Document but accept (single image, switchable runtime is the value prop). Possibly future: build-arg `CLI_FLAVORS=claude,codex` to slim variants | Image push/pull time, not runtime |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Inject all auth env vars unconditionally into every container regardless of `SUBAGENT_CLI` | Cross-CLI billing leak (Pitfall 1); operator's leftover `OPENAI_API_KEY` charges to the wrong account | Per-CLI allowlist in `_build_container_env()` |
| Persist OpenCode `auth.json` in workspace volume | Credential leak across operators in shared / `SINGLE_USER_MODE=""` deployments (Pitfall 7) | Env-only auth; `OPENCODE_CONFIG=/tmp/opencode.json`; scrub `auth.json` on container creation |
| Pass user prompts through to `codex exec --dangerously-bypass-approvals-and-sandbox` without explicit acknowledgement | YOLO flag bypasses Codex's own sandbox; if container escape is ever found, no second line of defence | Document the layered safety model: `--yolo` is acceptable ONLY because of the Docker container + `no-new-privileges` + non-root user. Never enable on the host. |
| Log full sub-agent output (incl. JSONL) to stdout | API keys / model IDs / file contents land in container logs harvested by external aggregators | Sanitise log lines (strip `Authorization`, `api_key=` patterns) — already a partial gap noted in `CONCERNS.md`; this milestone makes it worse if not addressed |
| Bake codex/opencode CLIs but leave their telemetry endpoints live | Project metadata phones home to OpenAI/sst even on air-gapped deployments | Set `OPENAI_TELEMETRY_DISABLED=1` and OpenCode equivalent in container env (verify per CLI release notes); document explicitly |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Switching `SUBAGENT_CLI` in `.env` requires `docker compose restart computer-use-server` AND the user has no signal that the switch took effect | Operators flip env, see no change, file bug | Print `[MCP] Sub-agent runtime: codex (gpt-5)` banner on orchestrator startup; surface in `/health` endpoint |
| Cost field reads `$0.0000` for opencode (provider doesn't report) | Operator thinks they got a free run; later sees the OpenRouter bill | Render "cost: unavailable" when adapter returns `None`; never default to 0.0 (Pitfall 4) |
| Skill prompts assume claude-isms ("read CLAUDE.md", "use Task tool") that codex/opencode don't have | Sub-agent for codex/opencode fails on tasks that work fine on claude | Audit `skills/public/sub-agent/SKILL.md` for claude-specific verbs; make instructions CLI-agnostic OR have the adapter prepend a CLI-specific preamble |
| ttyd auto-execs the chosen CLI with no escape hatch (Pitfall 9) | Operators feel trapped in the TUI | `NO_AUTOSTART=1` env + sentinel file + documented in CLOUD.md |
| Operator sets `SUBAGENT_CLI=codex` but model alias `sonnet` (Pitfall 3) — silent 400 | Confusing first-run failure | Hard-fail with a precise error: "model alias 'sonnet' is Claude-only; codex requires `gpt-5` or similar" |

## "Looks Done But Isn't" Checklist

- [ ] **CLI install:** `which codex && which opencode` passes — verify ALSO `codex --version` and `opencode --version` succeed (Pitfall 6/11)
- [ ] **Env switch:** `SUBAGENT_CLI=codex` produces a codex argv — verify ALSO `SUBAGENT_CLI=""` and `SUBAGENT_CLI` unset both behave byte-identical to claude default (Pitfall 12)
- [ ] **Auth isolation:** codex run uses `OPENAI_API_KEY` — verify ALSO `ANTHROPIC_AUTH_TOKEN` and `OPENROUTER_API_KEY` are NOT in the container env (Pitfall 1)
- [ ] **Prompt assembly:** sub-agent receives the skill text — verify ALSO `<critical_instruction>` block reaches codex/opencode AND `task_plan.md` was actually read (Pitfall 2)
- [ ] **Output parsing:** sub-agent returns structured result — verify ALSO `cost_usd` is non-None for cost-reporting CLIs and `None` (rendered "unavailable") for non-reporting; result text is the FINAL message, not raw JSONL (Pitfall 4)
- [ ] **Cost guardrail:** `max_turns=25` works for claude — verify ALSO an infinite-loop prompt terminates within timeout for codex AND opencode (Pitfall 5)
- [ ] **OpenCode auth:** `OPENROUTER_API_KEY` works — verify ALSO `~/.local/share/opencode/auth.json` does NOT exist after a session (Pitfall 7)
- [ ] **ttyd UX:** new terminal launches the chosen CLI — verify ALSO `NO_AUTOSTART=1 bash` gives plain bash (Pitfall 9)
- [ ] **init.sh:** OpenWebUI bootstrap still works — verify the milestone diff did NOT touch `openwebui/init.sh` (Pitfall 10, hard rule per saved memory)
- [ ] **Backwards compat:** existing claude deployment still works — verify a snapshot test of the claude-default path is byte-identical pre/post-milestone (Pitfall 12)
- [ ] **`test-docker-image.sh`:** all 11 existing steps pass — verify ALSO new steps for per-CLI dispatch + flag-compat exist (Pitfall 11)
- [ ] **Image volume budget:** `/home/assistant` < 1 MB at build — verify ALSO it stays < 1 MB after one full sub-agent dispatch per CLI (Pitfall 11 sub-trap 1)
- [ ] **English-only:** all new files in English (CLAUDE.md hard rule)
- [ ] **License headers:** new orchestrator files have `BUSL-1.1` SPDX header; any sub-agent skill changes have `MIT` (CLAUDE.md)

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Auth bleed (1) shipped | MEDIUM | 1. Audit billing dashboards for the leak window. 2. Hotfix `_build_container_env()` to allowlist. 3. Rotate the leaked-into provider's keys. 4. Patch release `v0.9.2.2` |
| Prompt contract divergence (2) shipped | LOW | Adapter-level fix: change `task = system_prompt + "\n\n" + task` for codex/opencode adapters. Patch release |
| Model-alias mismatch (3) shipped | LOW | Add hard-fail validation in adapter; no data corruption to undo |
| Output parser broken (4) shipped | LOW-MEDIUM | Update parser; previous results were ugly but not corrupt; no rollback of data needed |
| Cost runaway (5) shipped | HIGH | Operator absorbs the bill. Mitigation: emergency env knob `SUB_AGENT_TIMEOUT=300` recommended in incident docs while the proper turn-cap fix lands |
| Version drift (6) breaks production | LOW | Pin to last-known-good version in Dockerfile, rebuild image, push patch release. Detection lag is the actual cost |
| OpenCode auth leak (7) shipped | HIGH | Same as Pitfall 1 + enumerate all `chat-*-workspace` volumes for `auth.json`, scrub, rotate every key found. Public disclosure depending on severity |
| ttyd no-escape (9) shipped | LOW | Doc patch + `NO_AUTOSTART` env hot-add; no image rebuild needed for users who can pass env to compose |
| `init.sh` regression (10) shipped | MEDIUM | Revert `init.sh` change; users whose Valves were clobbered must re-edit. No silent corruption but irritation guaranteed |
| Backwards-compat break (12) shipped | HIGH | Existing deployments break on upgrade — emergency revert of the milestone, point release without the env switch, redo with proper compat layer |

## Pitfall-to-Phase Mapping

Phase numbering aligns with `PROJECT.md` Active milestone target features.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1 — Auth bleed | Phase 1 (env-switch resolver) + Phase 3 (per-CLI auth wiring) | `test_subagent_cli_env_isolation.py` parametrised by CLI; assert allowlist behaviour |
| 2 — Prompt contract | Phase 2 (adapter layer) | `test_subagent_prompt_assembly.py` per CLI; smoke test asserts plan-file read |
| 3 — Model alias | Phase 1 (resolver) | `test_subagent_model_alias_per_cli.py`; assert hard-fail on cross-CLI alias |
| 4 — Output drift | Phase 2 (adapter) | `test_subagent_result_parsing.py` with per-CLI fixture stdout dumps |
| 5 — Cost runaway | Phase 4 (cost parity) | `test_subagent_cost_caps.py` with infinite-loop prompt against mocked provider |
| 6 — Version drift | Phase 5 (test coverage) + Dockerfile pinning in Phase 1 | `test-docker-image.sh` step `[12/14]` running `--help` and grepping for adapter-required flags |
| 7 — OpenCode auth leak | Phase 3 (opencode adapter) | `tests/security/test_opencode_no_persistent_auth.py` |
| 8 — Test combinatorics | Phase 5 (test coverage) | Reviewer checklist in `tests/README.md` |
| 9 — ttyd no escape | Phase 4 (UX parity) | `test-docker-image.sh` smoke for `NO_AUTOSTART=1` |
| 10 — init.sh regression | Phase 1 (and every phase) | Grep gate in `test-project-structure.sh`: `init.sh` unchanged |
| 11 — `test-docker-image.sh` blind spots | Phase 5 (test coverage) | New test steps `[12/14]` and `[13/14]` per Pitfall 11 |
| 12 — Backwards compat | Phase 1 (env-switch defaults) | Golden-snapshot test `test_subagent_claude_compat.py` |

## Sources

- [OpenAI Codex CLI — Command line options](https://developers.openai.com/codex/cli/reference) — verified flags `exec --json`, `--model`, `--output-last-message`, `--dangerously-bypass-approvals-and-sandbox`
- [OpenAI Codex CLI — Non-interactive mode](https://developers.openai.com/codex/noninteractive) — `codex exec` JSONL event schema (`turn.started/completed`, `item.*`)
- [openai/codex#11588 — Add system prompt customization flags](https://github.com/openai/codex/issues/11588) — `--system-prompt-file` / `--append-system-prompt` are open feature requests, NOT shipped (Pitfall 2)
- [openai/codex#4776 — JSON output mode docs are out of date](https://github.com/openai/codex/issues/4776) — output schema drift evidence (Pitfall 6)
- [openai/codex#2288 — CLI flag to save trajectory/output as JSON](https://github.com/openai/codex/issues/2288) — confirms output format is still in flux
- [OpenCode docs — Config](https://opencode.ai/docs/config/) — `OPENCODE_CONFIG`, `OPENCODE_CONFIG_DIR`, env-substitution `{env:VAR}` syntax
- [OpenCode docs — CLI](https://opencode.ai/docs/cli/) — `opencode run` non-interactive mode, `provider/model` form
- [OpenCode docs — Providers](https://opencode.ai/docs/providers/) — auth-from-env discovery (Pitfall 1)
- [OpenCode docs — Modes](https://opencode.ai/docs/modes/) — per-mode prompt files and `maxIterations` (Pitfall 5)
- [anomalyco/opencode#13851 — Unable to use opencode cli in a non-interactive pipeline](https://github.com/anomalyco/opencode/issues/13851) — known non-interactive UX gaps; fork-state caveat
- Project files (verified by direct read 2026-04-25):
  - `computer-use-server/mcp_tools.py:860–1178` — current `sub_agent` contract
  - `computer-use-server/docker_manager.py:69–105, 441–550` — env-passthrough + container env build
  - `tests/test-docker-image.sh:84` — current CLI-presence test
  - `Dockerfile:218, 253–255, 314–395` — claude install, bun-wrapper, autostart hook
  - `openwebui/init.sh` — full body, marker-gated bootstrap (Pitfall 10)
- Saved memory (binding constraints):
  - `feedback_init_sh_marker.md` — init.sh must stay marker-gated (Pitfall 10)
  - `feedback_step_by_step_docs.md` — copy-paste docs over scattered KNOWN-BUGS entries
  - `project_filter_preview_defaults.md` — relevant for ttyd UX framing

---
*Pitfalls research for: Multi-CLI Sub-Agent Runtime (claude / codex / opencode) milestone v0.9.2.1*
*Researched: 2026-04-25*
