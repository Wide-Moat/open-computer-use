# Stack Research — Multi-CLI Sub-Agent Runtime (v0.9.2.1)

**Domain:** Coding-agent CLI integration into existing Ubuntu 24.04 sandbox image
**Researched:** 2026-04-25
**Confidence:** MEDIUM-HIGH (Codex flags + version verified against developers.openai.com; opencode env-var auto-pickup is MEDIUM — config-driven path recommended over relying on undocumented env-var auto-detection)

**Scope:** Adds two CLIs alongside the existing `@anthropic-ai/claude-code@2.1.112` install. Does NOT re-research the base image, Node.js, Bun, or Python — those are taken as given from the existing Dockerfile.

---

## Recommended Additions

### Core CLIs to Add

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `@openai/codex` | `0.125.0` (latest stable, April 2026) | OpenAI's official coding agent CLI | Only first-party "Codex CLI" with active development; pure npm distribution matches the existing `@anthropic-ai/claude-code` install pattern exactly — no curl-installer, no Homebrew, no extra runtime. Ships as JS + bundled native binaries via npm optionalDependencies for the host arch. |
| `opencode-ai` | `1.14.25` (latest stable, April 2026) | sst/opencode — provider-agnostic coding agent | Canonical npm package for the SST-maintained Go/TypeScript CLI (github.com/sst/opencode). Native OpenRouter / Anthropic / OpenAI / local-model support is what makes it the worked example for "qwen3.6 via OpenRouter without Anthropic." Same npm-global install path = zero new tooling to teach the Dockerfile. |

> **Both CLIs install via `npm install -g` into the same `/usr/local/lib/node_modules_global` prefix that already hosts `claude`. No new package manager, no new runtime.**

### Pinning Recommendation

| Package | Pin Strategy | Rationale |
|---------|--------------|-----------|
| `@openai/codex` | **Pin to exact** (e.g. `0.125.0`) via `ARG CODEX_VERSION=0.125.0` | Matches existing `CLAUDE_CODE_VERSION=2.1.112` discipline. Codex is pre-1.0; minor bumps can break flag surface (`exec` flags moved between 0.10x and 0.12x). Pin gives us controlled bumps with test verification. |
| `opencode-ai` | **Pin to exact** (e.g. `1.14.25`) via `ARG OPENCODE_VERSION=1.14.25` | Post-1.0 but on a fast minor cadence (1.14.22 → 1.14.25 in two days). The published shim package downloads platform-specific binaries from GitHub Releases at install time → reproducibility requires version pinning so the resolved binary URL doesn't drift. |

### CLI Invocation Surface (non-interactive — `claude --print` equivalents)

| CLI | Non-interactive command | Prompt source | Output mode |
|-----|------------------------|---------------|-------------|
| Claude Code (current) | `claude -p "prompt"` or `claude --print "prompt"` | positional arg | `--output-format json` |
| **Codex CLI** | `codex exec "prompt"` (positional) **or** `echo "prompt" \| codex exec -` (stdin) | positional or stdin | `--json` (newline-delimited events) + `--output-last-message <file>` for the final assistant message |
| **OpenCode** | `opencode run "prompt"` (positional) | positional | `--format json` (JSON events; flag name differs from `--output-format`) |

Each adapter must translate the unified MCP `sub_agent(...)` call into the right shape. Three concrete lines the adapter must emit:

```bash
# claude (existing)
claude -p "$task" --model "$model" --max-turns 25 \
  --permission-mode bypassPermissions --output-format json \
  --append-system-prompt "$sys"

# codex (new) — exec subcommand, --skip-git-repo-check needed because /home/assistant
# is not a git repo by default; --full-auto applies workspace-write sandbox
codex exec "$task" --model "$model" --json \
  --output-last-message /tmp/codex-last.txt \
  --skip-git-repo-check --full-auto -C "$working_directory"

# opencode (new) — run subcommand, model must be in provider/model form
opencode run "$task" --model "$provider/$model" --format json
```

### Required Auth & Model Env Vars (per CLI)

| CLI | Auth env vars | Base URL override | Model selection |
|-----|---------------|-------------------|-----------------|
| **Codex CLI** | `OPENAI_API_KEY` (primary). `CODEX_API_KEY` is also accepted in CI workflows per OpenAI docs. | `OPENAI_BASE_URL` is **not** documented as a top-level CLI env var; the supported path is `~/.codex/config.toml` with a `[model_providers.<name>]` block (or `--config` overrides). For LiteLLM proxy use, write a config block in entrypoint, do not rely on `OPENAI_BASE_URL`. | `--model` / `-m` flag (e.g. `--model gpt-5.4`). No `CODEX_MODEL` env var documented; prefer flag. |
| **OpenCode** | OpenCode reads credentials from `~/.local/share/opencode/auth.json` (written by `opencode auth login`). For headless container use, the **documented** path is config-driven: `apiKey: "{env:OPENROUTER_API_KEY}"` (and same for `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`) inside `~/.config/opencode/opencode.json`. Plain env-var auto-pickup is **not** explicitly guaranteed — do not rely on it. | Provider `baseURL` is set inside the same JSON config under the provider block. | `--model` / `-m` in `provider/model` form (e.g. `--model openrouter/qwen/qwen3-coder`). |

> **Worked OpenCode + qwen3.6 + OpenRouter env block** (entrypoint writes `~/.config/opencode/opencode.json` with):
> ```json
> {
>   "$schema": "https://opencode.ai/config.json",
>   "provider": {
>     "openrouter": { "apiKey": "{env:OPENROUTER_API_KEY}" }
>   },
>   "model": "openrouter/qwen/qwen3-coder"
> }
> ```
> Then `opencode run "..."` picks up `OPENROUTER_API_KEY` from container env. This is the supported substitution per `opencode.ai/docs/config`.

### Env Vars to Add to `extra_env` Passthrough in `docker_manager._create_container`

Augment the existing `CLAUDE_CODE_PASSTHROUGH_ENVS` tuple with new tuples (gated by `SUBAGENT_CLI`):

| New env var | Used by | Notes |
|-------------|---------|-------|
| `SUBAGENT_CLI` | orchestrator + entrypoint | `claude` (default) / `codex` / `opencode` |
| `OPENAI_API_KEY` | codex | Pass through only when `SUBAGENT_CLI=codex` (or always if user opts in) |
| `OPENAI_BASE_URL` | codex (via config.toml render) | Entrypoint reads this and writes the codex config block |
| `CODEX_MODEL` | adapter (NOT codex itself) | Internal name for "default model when sub_agent gets blank model"; wired through `--model` flag |
| `OPENROUTER_API_KEY` | opencode | Substituted into `~/.config/opencode/opencode.json` via `{env:...}` syntax |
| `ANTHROPIC_API_KEY` | opencode (when using anthropic provider) | Note: existing `ANTHROPIC_AUTH_TOKEN` is the Claude-Code-specific name; opencode expects the canonical `ANTHROPIC_API_KEY`. Entrypoint should mirror one to the other. |
| `OPENCODE_MODEL` | adapter | Default `provider/model` for opencode runs (e.g. `openrouter/qwen/qwen3-coder`) |
| `OPENCODE_CONFIG` | opencode | Optional override of config path; default `~/.config/opencode/opencode.json` is fine |

### System Dependencies to Add

**None.**

Verified against the existing Dockerfile system-package list:

| Need | Already present? |
|------|------------------|
| Node.js ≥18 (codex requires `>=20`, opencode-ai loader requires `>=18`) | ✓ Node 22.11.0 |
| `curl`, `tar`, `unzip` (opencode binary download at install time) | ✓ |
| `git` (codex `--skip-git-repo-check` makes git optional, but git is still useful) | ✓ |
| `ca-certificates` + `NODE_EXTRA_CA_CERTS` (HTTPS to platform-binary CDN for opencode) | ✓ |
| ripgrep (sometimes invoked by coding agents) | ✗ — not currently installed, but **not required** by either CLI's documented contract. Skip. |
| `libssl` / fonts | ✓ already present from Playwright/LibreOffice deps |

> Recommendation: do **NOT** add new apt packages for this milestone. Both CLIs ship self-contained.

### Disk-Size Impact

| CLI | Approx. install size in `/usr/local/lib/node_modules_global` | Reasoning |
|-----|-------------------------------------------------------------|-----------|
| Claude Code (existing) | ~25-30 MB | Reference baseline |
| `@openai/codex` 0.125 | **~50-80 MB** (includes Rust-built native binaries for one host arch via npm optionalDependencies) | Codex 0.20+ ships native binaries; the linux-x64 variant is the only one resolved on `--platform linux/amd64`, so worst-case is one binary, not all four. |
| `opencode-ai` 1.14 | **~40-60 MB** (Go binary downloaded at install time, plus shim) | sst/opencode is a Go program; the npm package is a thin loader that fetches the Go binary from GitHub Releases. After install only the linux-x64 binary is on disk. |

**Combined image-layer growth: ~100-140 MB.** Stays in the image layer (`/usr/local/lib/node_modules_global`), not the volume. **Volume budget under `/home/assistant` is unaffected** — the <1 MB rule is preserved because no per-user state is created until the user runs a CLI.

---

## Installation (Dockerfile snippet matching existing pattern)

```dockerfile
# Pin both CLIs alongside the existing CLAUDE_CODE_VERSION
ARG CODEX_VERSION=0.125.0
ARG OPENCODE_VERSION=1.14.25

# Install Codex CLI (drop-in alternative to claude)
RUN sudo -u assistant bash -c "npm install -g @openai/codex@${CODEX_VERSION}"

# Install OpenCode CLI (sst/opencode — npm shim downloads platform binary)
RUN sudo -u assistant bash -c "npm install -g opencode-ai@${OPENCODE_VERSION}"

# Smoke-test both CLIs in the same RUN as the existing claude --version line
RUN sudo -u assistant bash -c "export PATH=/usr/local/lib/node_modules_global/bin:\$PATH && \
    claude --version && codex --version && opencode --version" && \
    echo "All three sub-agent CLIs OK"
```

Place these `RUN` lines **immediately after** the existing `Install Claude Code CLI` block (Dockerfile line 218). Cache invalidation chain: changing `CODEX_VERSION` or `OPENCODE_VERSION` invalidates only the new layers, not Claude Code's.

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| `@openai/codex` (npm) | `brew install --cask codex` | Only on a developer Mac. Not viable in a Linux container — Linuxbrew adds 2 GB. |
| `@openai/codex` (npm) | Direct `curl` from GitHub Releases tarball | Only if npm install ever proves too slow / breaks; npm's built-in pin is simpler today. |
| `opencode-ai` (npm) | `curl -fsSL https://opencode.ai/install \| bash` | YOLO installer is fine for a workstation but writes to `~/.opencode` and skips reproducibility. npm pin is auditable. |
| `opencode-ai` (npm) | `brew install sst/tap/opencode` | macOS-only. |
| sst/opencode | `opencode-ai/opencode` (a *different* repo at github.com/opencode-ai/opencode) | Do NOT use — that's a separate fork with a different feature set and `-p` flag still has the open issue #277 ("Unable to specify model in non-interactive mode"). The SST repo at github.com/sst/opencode is the canonical project for this milestone. |
| sst/opencode | `anomalyco/opencode` | Newer fork mentioned in some search results; not the canonical project. Stick with sst. |

---

## What NOT to Use / NOT to Add

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Adding `ripgrep` apt package | Neither CLI requires it; both do their own file search via internal tools. Adds image weight without payoff. | Existing `grep` / `find` are enough for the sub-agent contract. |
| Relying on `OPENAI_BASE_URL` env var for codex | Not documented as a first-class env var on developers.openai.com/codex/cli/reference. Behavior may regress between versions. | Render `~/.codex/config.toml` in entrypoint with a `[model_providers.litellm] base_url=...` block, then `codex exec --config model_provider=litellm`. |
| Relying on plain `OPENROUTER_API_KEY` auto-pickup by opencode | Documented config substitution is `apiKey: "{env:OPENROUTER_API_KEY}"`, not implicit env-var auto-detection. Implicit pickup may work, but depends on provider plugin and is not contractually guaranteed. | Write `~/.config/opencode/opencode.json` in entrypoint with explicit `{env:...}` substitution and let opencode resolve at runtime. |
| `opencode-ai/opencode` package on github.com/opencode-ai/opencode | Different fork, separate issue tracker (#277 specifically affects non-interactive `-p` mode), different command surface. | `opencode-ai` package on npm pointing at `github.com/sst/opencode`. |
| `codex` package from PyPI / older 2021 OpenAI Codex artifact | Refers to the deprecated 2021 OpenAI Codex completion model SDK, not the 2025+ CLI. Names collide. | `@openai/codex` on npm — distinct namespace. |
| Per-call CLI override (`sub_agent(cli="codex", ...)`) | Already ruled Out of Scope in PROJECT.md — multiplies test surface, confuses skill prompts. | `SUBAGENT_CLI` env var, set once at orchestrator boot, propagated to every sandbox. |
| Bundling provider API keys in the image | Explicit Out of Scope per PROJECT.md — operator brings their own keys. | Always pull keys from per-container env at runtime. |

---

## Stack Patterns by SUBAGENT_CLI Value

**If `SUBAGENT_CLI=claude` (default):**
- No change. Existing `claude -p ... --output-format json` path stays as-is.
- Existing `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_BASE_URL` / `ANTHROPIC_DEFAULT_*_MODEL` passthrough unchanged.

**If `SUBAGENT_CLI=codex`:**
- Adapter emits `codex exec "$task" --model "$model" --json --output-last-message /tmp/codex-last.txt --skip-git-repo-check --full-auto -C "$workdir"`.
- Entrypoint renders `~/.codex/config.toml` from `OPENAI_API_KEY` + `OPENAI_BASE_URL` (latter only if set) under a `[model_providers.litellm]` block.
- `--output-format json` from claude has no direct codex equivalent — use `--json` for streaming events and `--output-last-message` to capture the final result text.

**If `SUBAGENT_CLI=opencode`:**
- Adapter emits `opencode run "$task" --model "$provider/$model" --format json`.
- Entrypoint renders `~/.config/opencode/opencode.json` with `{env:...}` substitutions for whichever of `OPENROUTER_API_KEY` / `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` are set in container env.
- Default model = `${OPENCODE_MODEL:-openrouter/qwen/qwen3-coder}` — wires the milestone's worked example.

---

## Version Compatibility

| Combination | Compatible? | Notes |
|-------------|-------------|-------|
| `@openai/codex@0.125.0` + Node 22.11.0 (current image) | ✓ | Codex requires Node ≥20; image has 22. |
| `opencode-ai@1.14.25` + Node 22.11.0 | ✓ | Loader requires Node ≥18. Go binary itself has no Node dep at runtime; Node is only used during `npm install`. |
| `@openai/codex@0.125.0` running under Bun | ⚠ Untested | The existing `claude` wrapper rewrites the shebang to `bun`. Codex ships native binaries — do **not** apply the bun wrapper to codex. Keep codex on its own npm shim. |
| `opencode-ai` running under Bun | n/a | opencode is a Go binary; Bun is irrelevant. |
| Both new CLIs + existing `@anthropic-ai/claude-code@2.1.112` | ✓ | Three independent npm packages, three independent bin entries (`claude`, `codex`, `opencode`). No shared modules. |
| `@openai/codex` + LiteLLM proxy | ✓ via config.toml `model_providers` block, ✗ via `OPENAI_BASE_URL` env | Codex CLI's gateway compatibility goes through config.toml, not env. Mirrors the GATEWAY-02 pattern from Phase 3 for Claude Code. |

---

## Sources

- [OpenAI Codex CLI Reference — developers.openai.com/codex/cli/reference](https://developers.openai.com/codex/cli/reference) — `codex exec` flags, `--model`, `--json`, `--output-last-message`, `--skip-git-repo-check`, `--full-auto`, `--cd` verified. **HIGH confidence.**
- [OpenAI Codex CLI Non-interactive — developers.openai.com/codex/noninteractive](https://developers.openai.com/codex/noninteractive) — non-interactive mode contract (positional prompt or stdin, stderr=progress, stdout=final). **HIGH confidence.**
- [github.com/openai/codex](https://github.com/openai/codex) — version 0.125.0 confirmed (April 24, 2026); npm/brew/binary install methods. **HIGH confidence.**
- [github.com/sst/opencode releases](https://github.com/sst/opencode/releases) — version 1.14.25 (April 25, 2026); npm distribution strategy with platform-specific optional deps. **HIGH confidence.**
- [opencode.ai/docs/cli](https://opencode.ai/docs/cli/) — `opencode run`, `--model provider/model`, `--format json`, `OPENCODE_CONFIG` / `OPENCODE_CONFIG_DIR`. **HIGH confidence.**
- [opencode.ai/docs/config](https://opencode.ai/docs/config/) — JSON/JSONC config format, `{env:VAR}` substitution syntax. **HIGH confidence.**
- [opencode.ai/docs/models](https://opencode.ai/docs/models/) — provider list via Models.dev, `provider/model_id` form. **MEDIUM confidence** (page accessed via search summary, not direct fetch).
- WebSearch on OpenRouter / opencode env-var auto-pickup — env-var auto-detection is **not** documented; recommendation is config-driven `{env:...}`. **MEDIUM confidence — flag for verification when implementing the entrypoint render.**
- Existing `/Users/nick/open-computer-use/Dockerfile` lines 122-218 — install-pattern parallel for `npm install -g` of CLIs. **HIGH confidence (read directly).**
- Existing `/Users/nick/open-computer-use/computer-use-server/docker_manager.py` lines 81-105 — `CLAUDE_CODE_PASSTHROUGH_ENVS` tuple pattern to extend. **HIGH confidence (read directly).**

---

*Stack research for: multi-CLI sub-agent runtime (claude / codex / opencode)*
*Researched: 2026-04-25*
