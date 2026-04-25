---
created: 2026-04-13T11:44:00.000Z
title: Add examples and verify Cherry Studio integration
area: docs
files:
  - docs/
  - README.md
---

## Problem

The repo is primarily documented and tested against Open WebUI as the MCP client. Users reaching for Cherry Studio (another MCP-capable chat client) have to piece together the connection details on their own, and we have no confirmation that the server actually works with it end-to-end. First impression for those users is brittle.

Two gaps:
1. No worked examples directory (or examples section in README) showing realistic setups — at minimum: a minimal MCP client config, a sample prompt that exercises browser + terminal + a skill, and expected output.
2. No verification that Cherry Studio can connect to `computer-use-server` and drive a sandbox through the full loop (browser session, terminal, file transfer, skill invocation).

## Solution

Two-part task:

1. **Examples**
   - Create `docs/examples/` (or similar) with at least 2 setups: Open WebUI (already supported, document what's already there), Cherry Studio.
   - Each example: client config snippet, minimum env vars, a walkthrough prompt, screenshot or recorded output.

2. **Cherry Studio integration check**
   - Install Cherry Studio locally, configure it to talk to `computer-use-server` (MCP over HTTP or stdio, whichever Cherry Studio speaks).
   - Run through the standard acceptance flow: spawn sandbox → open browser → run a terminal command → invoke a skill → verify artifact appears in outputs.
   - If something doesn't work: file issue(s) with minimal repro; fix in a separate PR.
   - If it works: add a one-line support statement to README and link the example doc.

Non-goals for this task: add *every* client. Focus on Cherry Studio as the proving ground for the "bring-your-own-client" story.
