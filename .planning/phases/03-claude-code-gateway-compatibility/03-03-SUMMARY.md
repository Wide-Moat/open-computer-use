---
phase: 03-claude-code-gateway-compatibility
plan: 03
subsystem: config-and-docs
tags:
  - docker-compose
  - env
  - docs
  - operator-guide
  - claude-code
dependency_graph:
  requires:
    - "03-01-SUMMARY.md (the env constants and context_vars fix the config exposes)"
  provides:
    - "docker-compose.yml: 12 new computer-use-server.environment entries (auth + 10 gateway vars)"
    - ".env.example: 13-line 'Claude Code sub-agent gateway overrides' block"
    - "docs/claude-code-gateway.md: operator-facing three-path guide (173 lines)"
    - "README.md and docs/INSTALL.md cross-links to the new doc"
  affects:
    - "Operator UX only — no code behaviour change beyond wiring env vars through compose"
tech_stack:
  added: []
  patterns:
    - "compose '${VAR:-}' default-empty pass-through — unset vars arrive as empty strings and are filtered by the 'if _value:' guard in docker_manager"
    - "HTML-comment SPDX header for Markdown files (first markdown doc to carry one)"
key_files:
  created:
    - "docs/claude-code-gateway.md"
  modified:
    - "docker-compose.yml"
    - ".env.example"
    - "README.md"
    - "docs/INSTALL.md"
requirements:
  covered:
    - GATEWAY-08
    - GATEWAY-09
    - GATEWAY-10
    - GATEWAY-11
    - GATEWAY-MH-08
    - GATEWAY-MH-09
    - GATEWAY-MH-10
  deferred: []
commits:
  - "5995f7c feat(03-03): wire Claude Code gateway env vars into docker-compose"
  - "d4a1b15 docs(03-03): add gateway-overrides block to .env.example"
  - "78a5329 docs(03-03): add Claude Code gateway configuration guide"
  - "01bc9be docs(03-03): cross-link Claude Code gateway guide from README and INSTALL"
status: complete
---

## What was built

### Task 1 - `docker-compose.yml` (commit 5995f7c)

Added 12 new `${VAR:-}` entries to `services.computer-use-server.environment:`
directly after the existing `VISION_MODEL` line. The block covers:

- `ANTHROPIC_AUTH_TOKEN` and `ANTHROPIC_BASE_URL` (previously missing from
  compose, which silently broke Path B end-to-end even with the 03-01
  ContextVar fix).
- The ten official Claude Code gateway vars from the 03-01 passthrough
  tuple (`ANTHROPIC_MODEL`, `ANTHROPIC_DEFAULT_{SONNET,OPUS,HAIKU}_MODEL`,
  `CLAUDE_CODE_SUBAGENT_MODEL`, `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS`,
  `DISABLE_PROMPT_CACHING{,_SONNET,_OPUS,_HAIKU}`).

YAML still parses cleanly; `computer-use-server.environment` now carries
22 entries (was 10). No other service touched.

### Task 2 - `.env.example` (commit d4a1b15)

Inserted a 13-line block immediately after the existing
`# === Optional: Claude Code sub-agent ===` section and before the
`# === Optional: GitLab integration ===` section:

```
# === Optional: Claude Code sub-agent gateway overrides ===
# Pass-through to sandbox when set. Leave commented to use Claude Code defaults.
# ANTHROPIC_MODEL=
... (10 commented var lines) ...
```

All ten new vars are commented out by default so operators discover them
without accidentally injecting empty strings. File length 58 -> 70 lines
(+12 lines, using the pre-existing blank separator as the 13th).

Pre-existing non-ASCII characters on line 40 (em-dashes in the skill
provider block) are out of scope and left untouched. The new block is
pure ASCII.

### Task 3 - `docs/claude-code-gateway.md` (commit 78a5329)

New 173-line operator guide with HTML-comment SPDX header. Sections:

1. Title + intro - explains the sub-agent runs Claude Code CLI inside
   each sandbox and the operator chooses the destination.
2. Three-path summary table.
3. Path A (zero-config) - leave vars unset, see the `/login` OAuth flow
   in ttyd.
4. Path B (public Anthropic) - one-line `.env` snippet with
   `sk-EXAMPLE-...` placeholder.
5. Path C (custom gateway) - worked LiteLLM recipe with all flags set,
   plus the Azure / Bedrock-via-LiteLLM sub-section.
6. Full variable reference - table covering all 12 vars (2 auth + 10
   new) with type / default / purpose / placeholder example.
7. Verification checklist - 6 numbered steps from `grep .env` through
   `docker inspect` to `docker exec` on the sandbox.
8. Troubleshooting - three entries: still prompting for /login (links
   issue #40), LiteLLM 400 on prompt caching, LiteLLM 400 on beta
   headers.
9. Further reading - links to the three canonical Claude Code docs.

All example keys use the `sk-EXAMPLE-*` placeholder pattern (3
occurrences); `grep -cE 'sk-[A-Za-z0-9]{20,}'` returns 0. File is
ASCII-only.

### Task 4 - `README.md` + `docs/INSTALL.md` cross-links (commit 01bc9be)

One new sentence each:

- `README.md`, inside `## Open WebUI Integration`, placed after the
  "Why not a fork?" paragraph and before `The openwebui/ directory
  contains:`:

  > Running Claude Code through a corporate gateway (LiteLLM, Azure,
  > Bedrock)? See [docs/claude-code-gateway.md](docs/claude-code-gateway.md)
  > for the three-path operator recipe.

- `docs/INSTALL.md`, inside `## Configuration`, placed directly after
  ``See `.env.example` for the full list with defaults.``:

  > Routing Claude Code through a custom gateway (LiteLLM / Azure /
  > Bedrock)? See [claude-code-gateway.md](claude-code-gateway.md) for
  > the full recipe.

`git diff --stat` confirms `README.md` +2 lines, `docs/INSTALL.md` +2
lines; no table rows or section headers altered.

## Verification

- `python3 -c "import yaml; yaml.safe_load(open('docker-compose.yml'))"`:
  valid, 22 env entries on `computer-use-server`.
- `grep -cE 'sk-[A-Za-z0-9]{20,}' docs/claude-code-gateway.md .env.example docker-compose.yml`:
  **0** (no real-looking secrets).
- `grep -c 'sk-EXAMPLE' docs/claude-code-gateway.md`: **3** (satisfies
  the >= 3 placeholder requirement).
- `./tests/test-no-corporate.sh`: **14 passed, 0 failed**.
- `./tests/test-project-structure.sh`: **22 passed, 0 failed**.

## Deviations from the plan

None of substance.

- **Minor**: The plan said insert a leading blank line before the new
  `.env.example` block, which would have taken the file to 71 lines. In
  practice the pre-existing blank line between the old Claude Code
  section and the GitLab section served the same purpose visually, so
  the file ended at 70 lines (58 + 12 new non-blank). Operator reading
  experience is unchanged.

## Self-check

- [x] All 4 tasks committed atomically (5995f7c, d4a1b15, 78a5329, 01bc9be).
- [x] All 12 env vars present in `docker-compose.yml` as `${VAR:-}` pass-throughs.
- [x] All 10 optional vars commented out in `.env.example` under the new header.
- [x] `docs/claude-code-gateway.md` >= 80 lines (173), has all 9 sections,
      and contains zero real-looking API keys.
- [x] One cross-link each from `README.md` and `docs/INSTALL.md` to the
      new doc; no other edits to either file.
- [x] Regression gates green: no-corporate + project-structure tests pass.

**Self-check: PASSED**
