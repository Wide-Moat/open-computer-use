# Feature Research

**Domain:** Multi-CLI sub-agent runtime (Claude Code / Codex CLI / OpenCode) inside Open Computer Use sandbox
**Researched:** 2026-04-25
**Confidence:** HIGH (verified against upstream docs and source for both CLIs; OpenAI dev portal + sst/opencode source)

---

## Scope reminder

Two surfaces consume the chosen CLI inside the sandbox:

1. **Headless** — `mcp_tools.sub_agent` shells out to `claude --print …` today. The MCP tool returns one stdout blob per call. Stateless per invocation by design (resume is opt-in via `resume_session_id`). This is the contract every alternative CLI must match.
2. **Interactive** — ttyd terminal in the sandbox: operator types into `claude` (or `codex` / `opencode`) directly, full TUI. No structured contract — whatever the CLI ships as default TUI is fine.

Categorisation below is **for our use case**, not for the CLIs in general.

---

## Per-CLI Capability Matrix

The 10 questions from the brief, answered against upstream docs.

| # | Capability | Claude Code (baseline) | Codex CLI (`@openai/codex`) | OpenCode (`sst/opencode`) |
|---|---|---|---|---|
| 1 | Non-interactive batch mode | `claude -p/--print TASK` | `codex exec TASK` (or `codex exec -` to read prompt from stdin) | `opencode run MESSAGE…` (positional args + stdin both joined into the message) |
| 2 | System prompt injection | `--append-system-prompt "…"` flag (string) | **No equivalent CLI flag.** Project instructions live in `AGENTS.md` (project root, walks up; falls back to `~/.codex/AGENTS.md`). Inline override possible via `-c key=value` (TOML override). | **No `--system` flag.** `instructions` array in `opencode.json` (file paths, globs, or remote URLs). Plus `AGENTS.md` (project + `~/.config/opencode/AGENTS.md`, with optional `~/.claude/CLAUDE.md` fallback). Per-agent `prompt:` field via `opencode agent create`. |
| 3 | Tool use / tool loop | Built-in agentic loop: Bash, Read, Write, Edit, Grep, Glob, WebSearch, WebFetch, TodoWrite. CLI runs the loop; model only sees tool results. | Built-in agentic loop with sandboxed bash, file edits, image input, web search, MCP servers. CLI runs the loop. `codex exec` runs to completion non-interactively; **approval requests cause immediate failure** unless sandbox/auto-approve set. | Built-in agentic loop (Bash, Edit, Write, Read, Grep, Glob, WebFetch, Task). CLI runs loop. Two built-in agents: `build` (full access) and `plan` (read-only). `--dangerously-skip-permissions` for headless. |
| 4 | Model selection at runtime | `--model sonnet|opus|haiku` flag, or full ID; `ANTHROPIC_MODEL` env | `--model, -m gpt-5-codex` flag (overrides config); `model = "…"` in `~/.codex/config.toml`; `-c model=…` inline override | `--model, -m provider/model` flag (e.g. `openrouter/qwen/qwen3-coder`); `"model"` key in `opencode.json`; interactive `/models` |
| 5a | Provider routing — Codex | n/a | OpenAI direct (default), ChatGPT subscription auth, **Azure OpenAI** (first-class via `[model_providers.azure]` TOML, `wire_api = "responses"`), **any OpenAI-compatible base URL** via custom `[model_providers.NAME]` block with `base_url` + `env_key` + `wire_api = "chat"|"responses"`. So OpenRouter etc. work via custom block, but **not as a built-in named provider**. | n/a |
| 5b | Provider routing — OpenCode | n/a | n/a | **Native first-class providers:** Anthropic, OpenAI, Google, OpenRouter, Azure OpenAI, Amazon Bedrock, GitHub Copilot, Groq, Mistral, Cohere, DeepSeek, xAI, plus 75+ via Models.dev. **Local:** Ollama, LM Studio (configured as openai-compatible). **Custom:** any OpenAI-compatible endpoint via `npm: "@ai-sdk/openai-compatible"` + `baseURL`. |
| 6 | Auth modes | API key (`ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN`) **or** OAuth (`/login` flow). Both work. | **Both supported in CLI:** `OPENAI_API_KEY` env var **or** "Sign in with ChatGPT" OAuth (`codex login`). Custom providers use either `requires_openai_auth = true` (reuses ChatGPT login) **or** `env_key` (env var per provider, e.g. `AZURE_OPENAI_API_KEY`). Cannot pass key inline; `env_key` must point to a real env var. | Per-provider env vars (`OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, etc.) **or** `opencode auth login` (interactive `/connect`, stores creds in keychain). API keys can also be inlined via `{env:VAR_NAME}` substitution in `opencode.json`. Note: **Anthropic explicitly prohibits using Claude Pro subscriptions with third-party tools** — Anthropic provider in OpenCode requires a real API key. |
| 7 | Streaming output | `--output-format text|stream-json|json` — `stream-json` is JSONL safe to pipe | `--json` emits JSONL `ThreadEvent` objects (`TurnStarted`, `ItemStarted`, `ItemCompleted`, `TurnCompleted`) line-by-line on stdout; `--output-last-message, -o PATH` writes only the final assistant message to a file (still also printed to stdout) | `--format default|json`; `json` emits raw event stream on stdout; positional message also accepts stdin |
| 8 | Cost / token reporting | In `--output-format json`: `total_cost_usd`, `num_turns`, token counts in result line | Token usage on `TurnCompleted` events when `--json`; **no `total_cost_usd` field** — Codex doesn't compute USD (provider-agnostic for custom providers) | Token usage in JSON event stream on assistant message events; **no first-class USD cost field** (provider-agnostic) |
| 9 | Multi-turn / session state | Stateless per invocation by default; `--resume <session-id>` opt-in. JSONL session log at `~/.claude/projects/<dir>/<session>.jsonl` | Sessions persisted by default to `~/.codex/` (SQLite + transcripts); `codex resume --last` or `codex resume <id>`; **`--ephemeral` flag for stateless runs without disk persistence** — perfect match for our sub_agent | Sessions persisted; `--continue, -c` resumes last; `--session, -s ID` resumes specific; `--fork` branches; **no documented `--ephemeral` flag** — every `opencode run` creates a session row (manageable, but a footprint) |
| 10 | Worked OpenCode + qwen3-coder + OpenRouter | n/a | n/a | See "Worked Recipe" below |

**Confidence per row:** 1–9 HIGH (cross-checked against developers.openai.com/codex/cli/reference, deepwiki openai/codex headless mode, opencode.ai/docs, and `sst/opencode` `run.ts` source). Row 6 Codex `requires_openai_auth` MEDIUM (single doc source).

---

## Feature Landscape

### Table Stakes — operators expect these from a coding CLI sub-agent

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Non-interactive one-shot mode that returns final answer on stdout | Without it, no MCP integration is possible | LOW | All three CLIs ship this: `claude -p`, `codex exec`, `opencode run` |
| API key via env var (no interactive login required) | Sandbox containers are headless; OAuth flows can't open browsers | LOW | All three support env-var auth. Codex `env_key` must be a real env var (not literal). OpenCode supports `{env:VAR}` substitution in JSON config |
| Per-invocation model override | Operator wants to flip sonnet↔opus, or qwen↔gpt-5-codex, without editing config | LOW | All three: `--model` flag |
| JSONL/JSON output mode for parsing | Orchestrator extracts final text + token counts from stdout | LOW | All three: `--output-format json` (Claude), `--json` (Codex), `--format json` (OpenCode) |
| Tool-use loop runs inside the CLI process | We do NOT want to wire bash/edit tools through MCP for the sub-agent — too slow, too fragile | LOW (already true) | All three run the loop themselves |
| Bypass interactive permission prompts | Headless runs can't answer y/N | LOW | Claude: `--permission-mode bypassPermissions`. Codex: `--full-auto` or `--sandbox danger-full-access` (with sandbox VM warning). OpenCode: `--dangerously-skip-permissions` |
| Configurable max turns / iteration cap | Cost ceiling — sub_agent already pins this at 25 | LOW | Claude: `--max-turns N`. **Codex: no documented direct `--max-turns` flag** — caps come from sandbox/approval policy. OpenCode: agent-level prompt convention (no flag). **GAP for Codex/OpenCode parity.** |
| OpenAI-compatible base URL or LiteLLM passthrough | Operators behind corporate gateways need this | LOW–MEDIUM | Claude: `ANTHROPIC_BASE_URL`. Codex: `[model_providers.X] base_url + wire_api`. OpenCode: native OpenAI-compatible provider type |
| Session resume by ID | Long refactors hit max_turns; resume saves context | LOW | Claude: `--resume`. Codex: `codex resume`. OpenCode: `--continue` / `--session` / `--fork` |

### Differentiators — features that would attract operators to switch CLI

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **75+ providers out of the box (OpenCode)** | One CLI talks to OpenRouter, Bedrock, Ollama, LM Studio, Anthropic, OpenAI without provider-specific glue | LOW (already there) | This is OpenCode's killer feature for our community. The Anthropic-lock-in is the #1 complaint about Claude Code |
| **OpenRouter native + qwen3-coder access (OpenCode)** | Cheap, OSS-friendly model that's competitive with Sonnet on coding benchmarks. No Anthropic dependency. | LOW | Worked recipe below — this is the proof point for v0.9.2.1 |
| **`--ephemeral` headless mode (Codex)** | Zero disk footprint per sub-agent run — matches our stateless-by-default contract exactly | LOW | Use this flag in Codex adapter to avoid `~/.codex/` accreting state per chat |
| **`--output-schema` (Codex)** | Validate sub-agent's final message against a JSON Schema — guarantees machine-readable output for downstream tools | MEDIUM | Not used in current `sub_agent` MCP tool, but a future hook for skills that need structured returns |
| **ChatGPT subscription login (Codex)** | Operators with ChatGPT Plus/Pro can use it without a separate API key | LOW (CLI supports it) | **Not useful inside the sandbox** (no browser), but useful for the ttyd interactive surface where the operator can `codex login` once |
| **Built-in `plan` agent (OpenCode)** | Read-only safety mode for "what would you do?" runs | LOW (already there) | Useful future hook for a `mode=plan` parameter on `sub_agent` |
| **AGENTS.md inheritance with CLAUDE.md fallback (OpenCode)** | If a project already has `CLAUDE.md`, OpenCode picks it up automatically | LOW | Operators already in the Claude ecosystem migrate without rewriting prompts |
| **`{env:VAR}` substitution in opencode.json (OpenCode)** | Config can carry env-var references, not literal secrets — matches our "operator brings their own keys" rule | LOW | Use this pattern in the OpenCode adapter |
| **Inline `-c key=value` config override (Codex)** | Override any TOML key per-invocation without rewriting `config.toml` | LOW | We can use this to inject per-call models or providers from the orchestrator |

### Anti-Features — capabilities we should explicitly NOT replicate

| Feature | Why Requested | Why Problematic For Us | Alternative |
|---------|---------------|------------------------|-------------|
| **Per-call CLI override** (`sub_agent(cli="codex", …)`) | "Let each task pick the best CLI" | Triples test surface (3 CLIs × every skill); sub-agent prompts assume one tool vocabulary; PROJECT.md already excludes this | Boot-time `SUBAGENT_CLI` env switch only |
| **Codex Cloud / `codex cloud` subcommand** | Submits tasks to OpenAI's hosted Codex Cloud | We already ship a sandbox; layering another remote sandbox is double-isolation and breaks the "self-hosted" promise | Sub-agent stays in our Docker sandbox |
| **OpenCode `serve` / `web` / `attach` modes** | Headless API server with web UI; remote TUI | Open Computer Use already provides ttyd + file server + MCP — adding OpenCode's server is redundant infrastructure | Ignore these subcommands; only use `opencode run` for headless and `opencode` (TUI) for ttyd |
| **`opencode share`** | One-click public URL for a session | Leaks session contents to sst.dev infrastructure; violates self-hosted promise; potential PII leak in corp deployments | Document explicitly: do NOT pass `--share` |
| **Codex `--dangerously-bypass-approvals-and-sandbox`** | Headless convenience | Codex's own docs warn against this outside isolated VMs. We ARE in a Docker sandbox, but Claude Code's `--permission-mode bypassPermissions` is more conservative and well-tested | Use `--full-auto` (Codex) and `--dangerously-skip-permissions` (OpenCode); avoid the more aggressive flag |
| **OpenCode's interactive `/connect` for auth** | Easy onboarding | Sandbox containers are ephemeral — interactive login on each spawn is wrong UX; secrets must come from env | Set provider env vars at container start (already the pattern for `ANTHROPIC_AUTH_TOKEN`) |
| **Codex notification hooks / desktop notifications** | "Tell me when the agent finishes" | Sub-agent runs inside a Docker container; host desktop notifications are out of band, and the orchestrator already streams progress over MCP | Skip; orchestrator's existing `send_progress` covers this |
| **Codex `--output-schema` for v1** | Structured returns | Useful, but adding it requires rewriting `_format_sub_agent_result` to honour a schema. Out of scope for v0.9.2.1 — record as v0.9.x.x candidate | Plain-text final message via `--output-last-message` or `--json` parsing |
| **Codex / OpenCode native MCP server config** | "Just point at MCP servers" | Both have their own MCP integration paths (`[mcp_servers]` TOML in Codex, `mcp` block in opencode.json). Our orchestrator already builds `~/.mcp.json` for Claude Code in `build_mcp_config`. We must adapt the same logic for the other two — not a new feature, just a port | Build per-CLI MCP config files in the adapter (extend `build_mcp_config_write_script`) |
| **Codex Plan Mode (`plan_mode_reasoning_effort`)** | Reasoning-effort control | Provider-specific (gpt-5-codex). Skipping in MVP — sub_agent already passes `model` at runtime. Add later if operators ask | Keep `model` as the only knob in v0.9.2.1 |

### Out-of-Scope features (relevant but excluded by PROJECT.md)

These appeared in research but are explicitly excluded by the milestone:

- Auto-installing API tokens for the operator — operator brings own keys
- Adding a 4th CLI (Aider, Continue, qwen-code) — three is the supported set
- Per-call CLI override — boot-time only
- Migrating ttyd default off Claude Code — Claude stays the recommended runtime; Codex/OpenCode are alternatives

---

## Feature Dependencies

```
SUBAGENT_CLI=codex
    ├─requires─> codex CLI installed in image
    ├─requires─> OPENAI_API_KEY env (or AZURE_OPENAI_API_KEY + [model_providers.azure])
    ├─requires─> ~/.codex/config.toml written at container start with model + model_provider + sandbox config
    └─enables──> --ephemeral flag (no SQLite state per chat)

SUBAGENT_CLI=opencode
    ├─requires─> opencode CLI installed in image
    ├─requires─> opencode.json written at container start with provider + model
    ├─requires─> per-provider env var (OPENROUTER_API_KEY | ANTHROPIC_API_KEY | OPENAI_API_KEY | …)
    └─enables──> qwen3-coder via OpenRouter (the worked recipe)

System prompt parity
    Claude --append-system-prompt "<SYS>"
        └─maps to (Codex)──> write SYS to ~/.codex/AGENTS.md before exec
        └─maps to (OpenCode)─> write SYS to AGENTS.md or instructions[] file before run

MCP server passthrough (current build_mcp_config writes ~/.mcp.json for Claude)
    └─requires port──> Codex equivalent: [mcp_servers] block in config.toml
    └─requires port──> OpenCode equivalent: mcp block in opencode.json

Boot-time SUBAGENT_CLI switch
    ├─enables──> CLI adapter dispatch in mcp_tools.sub_agent
    ├─enables──> ttyd default-shell selection
    └─required-by─> install of all three CLIs in the image (test verifies all three exist)
```

### Dependency Notes

- **Codex AGENTS.md as system-prompt mechanism is fragile**: the file is read from the working directory walking upward. Our `working_directory` is `/home/assistant`. We must write `AGENTS.md` there per call (and clear it after) — or use `~/.codex/AGENTS.md` as a global. Per-call write is safer; global would leak between concurrent sub-agents in the same container (but our containers are per-chat, so global is fine in practice).
- **OpenCode's `instructions` array in opencode.json is the cleanest match** for our existing `--append-system-prompt` contract — it lists files that get appended to the system prompt. Write the prompt to a file once, reference it in opencode.json, done.
- **Max-turns parity is not free**: Claude Code has `--max-turns`, Codex and OpenCode do not. Closest analog: count turns in `--json` event stream and SIGTERM the process when exceeded. **This is a real adapter-level engineering task**, not a flag. Document as a known caveat for v0.9.2.1.
- **Cost reporting parity is not free**: Claude returns `total_cost_usd`. Codex and OpenCode return only token counts. Adapter must compute USD from a model→price table or omit the cost field for non-Claude runs. Recommend: omit when CLI doesn't provide it.

---

## Worked Recipe — OpenCode + qwen3-coder via OpenRouter

This is the headline proof-point per PROJECT.md: "you can run sub-agents without Anthropic." Verified against opencode.ai/docs/providers and the run.ts source.

### Setup at container start (orchestrator-side)

```bash
# 1. Install once in Dockerfile
RUN curl -fsSL https://opencode.ai/install | bash
# (Or: npm install -g opencode-ai per opencode.ai/docs/install)

# 2. Per-container env (set by orchestrator from operator-provided values)
export OPENROUTER_API_KEY="sk-or-v1-…"

# 3. Write config to /home/assistant/opencode.json (per-chat)
cat > /home/assistant/opencode.json <<'JSON'
{
  "$schema": "https://opencode.ai/config.json",
  "model": "openrouter/qwen/qwen3-coder",
  "instructions": ["/home/assistant/.subagent_system_prompt.md"]
}
JSON

# 4. Write the sub-agent system prompt (the same prompt
#    Claude gets via --append-system-prompt today)
cat > /home/assistant/.subagent_system_prompt.md <<'SYS'
<critical_instruction>
Your task plan is saved at /home/assistant/task_plan.md
…
</critical_instruction>
…
SYS

# 5. Write the task plan (existing pattern — unchanged from Claude path)
cat > /home/assistant/task_plan.md <<'PLAN'
## ROLE
…
PLAN
```

### Per-invocation (replaces `claude -p …` in `mcp_tools.sub_agent`)

```bash
cd /home/assistant && \
  opencode run \
    --model openrouter/qwen/qwen3-coder \
    --format json \
    --dangerously-skip-permissions \
    "Read and execute your task plan from /home/assistant/task_plan.md"
```

### Expected stdout (truncated, illustrative)

`--format json` emits one JSON event per line. Real schema is whatever sst/opencode's event types emit; the orchestrator only needs the assistant text and final usage:

```jsonl
{"type":"session.created","sessionID":"ses_01H…","title":"Read and execute your task plan…"}
{"type":"message.started","role":"assistant"}
{"type":"tool.invoked","name":"Read","input":{"filePath":"/home/assistant/task_plan.md"}}
{"type":"tool.completed","name":"Read","output":"## ROLE\n…"}
{"type":"tool.invoked","name":"Bash","input":{"command":"pytest tests/orchestrator/"}}
{"type":"tool.completed","name":"Bash","output":"…"}
{"type":"message.delta","content":"I've fixed all failing tests. Summary:\n…"}
{"type":"message.completed","usage":{"input_tokens":12450,"output_tokens":3210}}
{"type":"session.completed"}
```

The adapter:

1. Reads stdout line-by-line.
2. Streams `tool.invoked` events as MCP progress notifications (via existing `send_progress`).
3. On `message.completed`, captures `usage` for the result blob.
4. On `session.completed`, builds the final response string, formats it through `_format_sub_agent_result` (the cost field is empty/N-A — see "cost parity" caveat above).

### Cost note

OpenRouter's `qwen/qwen3-coder` is currently $0.20/M input / $0.80/M output (verified at openrouter.ai/qwen/qwen3-coder/api). A `qwen/qwen3-coder:free` tier exists for evaluation. Operator picks the model id; the adapter doesn't compute USD.

### Failure modes to test

- Missing `OPENROUTER_API_KEY` → `opencode run` returns auth error on stderr; adapter must surface this
- Invalid model id (`openrouter/qwen3-coder` without provider prefix) → opencode resolution failure
- OpenRouter 429 / 5xx → tool-loop continues with retry-or-fail per opencode's internal retry policy

---

## Worked Recipe — Codex CLI + Azure OpenAI

Second-most-likely operator path: a corp deployment with an existing Azure OpenAI subscription.

### Setup at container start

```bash
# 1. Install
RUN npm install -g @openai/codex
# (Verify: codex --version)

# 2. Per-container env
export AZURE_OPENAI_API_KEY="…"

# 3. Write ~/.codex/config.toml
mkdir -p /home/assistant/.codex
cat > /home/assistant/.codex/config.toml <<'TOML'
model = "gpt-5-codex"
model_provider = "azure"

[model_providers.azure]
name = "Azure OpenAI"
base_url = "https://YOUR_RESOURCE.openai.azure.com/openai/v1"
env_key = "AZURE_OPENAI_API_KEY"
wire_api = "responses"
TOML

# 4. Write AGENTS.md (this is Codex's system-prompt mechanism)
cat > /home/assistant/AGENTS.md <<'SYS'
<critical_instruction>
Your task plan is saved at /home/assistant/task_plan.md
…
</critical_instruction>
SYS
```

### Per-invocation

```bash
cd /home/assistant && \
  codex exec \
    --ephemeral \
    --json \
    --full-auto \
    --output-last-message /tmp/sub_agent_final.txt \
    "Read and execute your task plan from /home/assistant/task_plan.md"
```

`--ephemeral` skips disk persistence; `--json` streams `ThreadEvent`s; `--output-last-message` writes the final assistant message to a file the adapter reads after exit.

For a non-Azure custom provider (e.g. OpenRouter via Codex), substitute:

```toml
[model_providers.openrouter]
name = "OpenRouter"
base_url = "https://openrouter.ai/api/v1"
env_key = "OPENROUTER_API_KEY"
wire_api = "chat"
```

OpenRouter via Codex works but is **second-class** — Codex's first-class providers are OpenAI direct + Azure. OpenCode is the recommended path for OpenRouter.

---

## MVP Definition (what v0.9.2.1 must ship)

### Launch With (v0.9.2.1)

- [x] `SUBAGENT_CLI` env var read at orchestrator boot — chooses `claude` (default) | `codex` | `opencode`
- [ ] `claude` adapter — current code path, unchanged contract
- [ ] `codex` adapter — `codex exec --ephemeral --json --full-auto --output-last-message` invocation; writes `~/.codex/config.toml` + `AGENTS.md` per-call from existing system_prompt
- [ ] `opencode` adapter — `opencode run --format json --dangerously-skip-permissions` invocation; writes `opencode.json` + system-prompt instructions file per-call
- [ ] All three CLIs installed in the Docker image (Dockerfile)
- [ ] `tests/test-docker-image.sh` verifies `claude --version`, `codex --version`, `opencode --version` all resolve
- [ ] ttyd `command:` honours `SUBAGENT_CLI` and launches the chosen CLI on terminal open
- [ ] Worked OpenRouter+qwen3-coder recipe in docs (env vars, config, sample command, expected output)
- [ ] Step-by-step copy-paste docs per CLAUDE.md preference

### Add After Validation (v0.9.x)

- [ ] Cost-USD computation for non-Claude CLIs from a model→price table (defer until operators ask)
- [ ] Adapter-level max-turns enforcement for Codex / OpenCode (count turns in event stream, SIGTERM on cap) — defer; rely on per-CLI native caps for now
- [ ] `--output-schema` Codex hook for skills that want structured JSON results
- [ ] `mode=plan` parameter on `sub_agent` mapping to OpenCode's plan agent

### Future Consideration (v2+)

- [ ] Per-call CLI override (sub_agent(cli=…)) — only if multi-CLI proves valuable in real use
- [ ] 4th CLI (qwen-code, aider) — only on demand
- [ ] Auto-detect CLI from operator env (e.g. infer codex if only OPENAI_API_KEY set) — risky magic, defer

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| `SUBAGENT_CLI` env switch resolver | HIGH | LOW | P1 |
| Codex adapter (`codex exec`) | HIGH | MEDIUM | P1 |
| OpenCode adapter (`opencode run`) | HIGH | MEDIUM | P1 |
| Image install of both new CLIs | HIGH (gates everything) | LOW | P1 |
| OpenRouter + qwen3-coder worked recipe | HIGH (proof point) | LOW | P1 |
| ttyd default-CLI per `SUBAGENT_CLI` | MEDIUM | LOW | P1 |
| MCP server config translation per CLI | MEDIUM | MEDIUM | P1 (skills break otherwise) |
| Per-CLI test coverage in test-docker-image.sh | HIGH (CI gate) | LOW | P1 |
| Adapter-level max-turns enforcement (Codex/OpenCode) | MEDIUM | MEDIUM-HIGH | P2 |
| USD cost computation for non-Claude | LOW | MEDIUM | P3 |
| Codex `--output-schema` integration | LOW | MEDIUM | P3 |
| Per-call CLI override | LOW | HIGH (test surface explosion) | OUT OF SCOPE |
| OpenCode `serve`/`web`/`attach` modes | LOW | HIGH | OUT OF SCOPE (anti-feature) |
| OpenCode `--share` | NEGATIVE | LOW | EXCLUDED (privacy) |

---

## Competitor Feature Analysis (CLI-against-CLI for our use case)

| Feature | Claude Code | Codex CLI | OpenCode | Our Approach |
|---------|-------------|-----------|----------|--------------|
| Headless one-shot | `--print` flag | `codex exec` subcommand | `opencode run` subcommand | Adapter chooses based on `SUBAGENT_CLI` |
| Pass system prompt | `--append-system-prompt STRING` | Write `AGENTS.md` file | Write file referenced in `instructions[]` | Adapter writes a file pre-call (Codex/OpenCode) |
| Pick model per call | `--model` flag | `--model` flag | `--model provider/model` flag | All three: surface as `model=` param on `sub_agent` |
| Bypass permissions | `--permission-mode bypassPermissions` | `--full-auto` | `--dangerously-skip-permissions` | Adapter sets the right flag per CLI |
| Stateless / no disk state | Default (we don't write state outside JSONL log) | `--ephemeral` flag | (no flag — sessions persist) | Codex: use `--ephemeral`. OpenCode: accept persistence; document cleanup |
| Provider scope | Anthropic + ANTHROPIC_BASE_URL gateway (LiteLLM/Bedrock-via-LiteLLM/Vertex-via-LiteLLM) | OpenAI + Azure first-class; others via custom `[model_providers]` blocks | 75+ first-class incl. OpenRouter + Bedrock + Ollama + LM Studio | Each CLI plays to its strength; documentation steers operators per provider |
| Cost reporting | `total_cost_usd` in JSON | Token counts only | Token counts only | Surface USD only when CLI provides it |
| MCP server config | `~/.mcp.json` | `[mcp_servers]` in `config.toml` | `mcp` block in `opencode.json` | Adapter writes the right file at container init |
| Auth | API key OR OAuth | API key OR ChatGPT OAuth (per-provider via `requires_openai_auth` or `env_key`) | Per-provider env var OR `auth login` keychain | Env-var only inside sandbox (operator brings keys); ttyd terminal can use OAuth interactively |

---

## Key risks / quality gate flags

1. **Max-turns parity is the biggest hidden gap.** Claude's `--max-turns 25` is the only enforcement keeping `sub_agent` cost-bounded today. Codex and OpenCode don't ship it. Without adapter-level enforcement, a runaway Codex or OpenCode session can blow through tokens. **Mitigation in v0.9.2.1:** rely on `SUB_AGENT_TIMEOUT` (3600s) as the hard ceiling; document the gap; consider a follow-up phase to add turn-counting in the JSON event stream.
2. **Codex AGENTS.md scope.** Globally writing `~/.codex/AGENTS.md` works because containers are per-chat, but if SINGLE_USER_MODE=true reuses one container across sessions, the AGENTS.md from one sub-agent leaks into the next. **Mitigation:** write to `<working_directory>/AGENTS.md` per call and remove on exit, OR rely on the per-chat container isolation.
3. **OpenCode session persistence.** No `--ephemeral`; every `opencode run` creates a session row in opencode's local DB. Over hundreds of sub-agent calls per chat, this accumulates. **Mitigation:** `opencode session list | opencode session delete` cleanup hook on container shutdown, or document acceptable footprint.
4. **Codex `requires_openai_auth = true`** for custom providers — single doc source. Verify in CI test before relying on it for OpenAI-compatible providers.
5. **OpenCode's `share` flag** is opt-in but easy to enable accidentally. Anti-feature: never pass `--share` from the adapter; document it in docs/CLOUD.md as an operator gotcha.

---

## Sources

- [Codex CLI command reference (developers.openai.com)](https://developers.openai.com/codex/cli/reference) — flags for `codex exec` (`--json`, `-o`, `--output-schema`, `-c`), `--full-auto`, sandbox modes
- [Codex CLI features (developers.openai.com)](https://developers.openai.com/codex/cli/features) — `exec` subcommand description, `resume`, slash commands
- [Codex headless execution mode (DeepWiki)](https://deepwiki.com/openai/codex/4.2-headless-execution-mode-(codex-exec)) — `ThreadEvent` JSONL schema, `--ephemeral`, prompt-via-stdin pattern, approval-fail behaviour
- [Codex CLI authentication (developers.openai.com)](https://developers.openai.com/codex/auth) — ChatGPT OAuth + API key, `requires_openai_auth`, `env_key`, `forced_login_method`
- [Codex CLI configuration (developers.openai.com)](https://developers.openai.com/codex/cli/config) — `~/.codex/config.toml`, MCP servers block, plan-mode reasoning
- [Codex Azure OpenAI integration (Microsoft Foundry docs)](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/codex) — `[model_providers.azure]` TOML, `wire_api = "responses"`
- [Codex CLI configuration reference blog](https://codex.danielvaughan.com/2026/04/08/codex-cli-configuration-reference/) — full TOML key reference
- [openai/codex docs/agents_md.md](https://github.com/openai/codex/blob/main/docs/agents_md.md) — AGENTS.md as instructions mechanism, `child_agents_md` feature flag
- [OpenCode CLI command list (opencode.ai)](https://opencode.ai/docs/cli/) — `run`, `auth login`, `session list`, `models`, `agent create`, all flags
- [OpenCode providers (opencode.ai)](https://opencode.ai/docs/providers/) — 75+ providers, OpenRouter native config, Bedrock auth chain, Ollama/LM Studio openai-compatible setup
- [OpenCode AGENTS.md / rules (opencode.ai)](https://opencode.ai/docs/rules/) — AGENTS.md precedence (project → global → CLAUDE.md fallback), `instructions[]` config field
- [OpenCode config reference (opencode.ai)](https://opencode.ai/docs/config/) — `opencode.json` schema, `{env:VAR}` substitution, model + provider config, MCP block
- [sst/opencode run.ts source](https://github.com/sst/opencode/blob/dev/packages/opencode/src/cli/cmd/run.ts) — exact flag definitions for `opencode run`: `--model`, `--format`, `--continue`, `--session`, `--fork`, `--dangerously-skip-permissions`, message-from-args+stdin assembly
- [OpenRouter qwen3-coder API docs](https://openrouter.ai/qwen/qwen3-coder/api) — model id `qwen/qwen3-coder`, OpenAI-compatible endpoint
- [Qwen Code CLI configuration](https://qwenlm.github.io/qwen-code-docs/en/users/configuration/model-providers/) — corroborates `OPENROUTER_API_KEY` + `https://openrouter.ai/api/v1` pattern (cross-CLI)

---
*Feature research for: Multi-CLI sub-agent runtime (Claude / Codex / OpenCode) inside Open Computer Use sandbox*
*Researched: 2026-04-25*
