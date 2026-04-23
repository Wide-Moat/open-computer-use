---
phase: 02-preview-filter-ux
reviewed: 2026-04-12T00:00:00Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - openwebui/functions/computer_link_filter.py
  - tests/test_filter.py
  - docs/openwebui-filter.md
findings:
  critical: 0
  warning: 0
  info: 3
  total: 3
status: issues_found
---

# Phase 02 Code Review

**Date:** 2026-04-12
**Reviewer:** gsd-code-reviewer
**Scope:** 3 files, 4 commits, +302/-13 lines

## Summary

The v3.2.0 preview UX extension to `outlet()` faithfully implements the locked pseudocode in `02-CONTEXT.md`. All five v3.1.0 invariants are preserved verbatim: `role=="assistant"` guard (filter.py:336), `isinstance(content, str)` guard (filter.py:339), `re.escape(chat_id)` in `file_url_pattern` (filter.py:331, plus `re.escape(base)` — stronger than required), `FILE_SERVER_URL.rstrip("/")` (filter.py:330), and substring-based idempotency for all three decorations (filter.py:345, 347, 358). The iframe snippet is a stable f-string whose only interpolated value is `preview_url`, which is itself deterministic given `FILE_SERVER_URL` + `chat_id` — so the `iframe not in content` check is sound.

The 11 new tests cover the six PREVIEW-requirement boundary conditions (default-on, idempotency, disabled-valve, cross-chat guard, non-assistant roles, trailing slash) plus a drift guard for DOCS-03. The `VALVES:` docstring block and `docs/openwebui-filter.md` table are consistent and list all eight Valves. Everything is English. The filter-internal version bump (`3.1.0` → `3.2.0`) is in the right place (module docstring header, not the repo `v0.8.X.Y` axis).

No blockers, no warnings. Three INFO items below — all are discretionary hardening suggestions, not defects against the locked spec.

## Findings

### BLOCKER

_None._

### WARNING

_None._

### INFO

#### IN-01: iframe `src` attribute is not HTML-escaped — defensive-only, no current risk

**File:** `openwebui/functions/computer_link_filter.py:354`
**Problem:** `preview_url` is interpolated directly into `<iframe src="{preview_url}" …>` without HTML-attribute escaping. In the current data flow `chat_id` is produced by Open WebUI (UUID-shaped) and `FILE_SERVER_URL` is an operator-trusted Valve, so there is no realistic injection vector today — both the `02-CONTEXT.md` threat model and the scope brief confirm this. Still, if a future code path ever routes a less-trusted value into `chat_id` (e.g. a session ID string containing `"` or `>`), the iframe attribute would break out of the `src`. The markdown-link case (`[text]({preview_url})`) is lower risk because Open WebUI's markdown renderer would escape it, but the raw `html` fenced block is rendered verbatim.
**Note:** Not a fix-now item — flagging so that a future reviewer who sees `chat_id` start flowing from user-controlled input knows this line needs `html.escape(preview_url, quote=True)`. Given the locked pseudocode is the canonical reference, no change is required here.

#### IN-02: Re-enabling `ENABLE_PREVIEW_BUTTON` after artifact has been emitted silently skips the button

**File:** `openwebui/functions/computer_link_filter.py:345`
**Problem:** The button guard is `preview_url not in content`. Because the iframe snippet also contains `preview_url`, a message that was decorated while `ENABLE_PREVIEW_BUTTON=False` and `ENABLE_PREVIEW_ARTIFACT=True` will never get a button added on a subsequent `outlet()` call even after the operator flips the button Valve on. This is a deliberate consequence of substring idempotency and of the locked decision that "Valves don't change mid-conversation," so it is not a defect — but it is a non-obvious operator gotcha.
**Note:** Either (a) accept as-is and mention in the "both on" paragraph of `docs/openwebui-filter.md` that toggling Valves requires a new assistant message for the change to take effect, or (b) use a stricter substring marker like the full `[{PREVIEW_BUTTON_TEXT}](` literal. Option (a) is cheaper and matches the documented idempotency contract.

#### IN-03: Docstring-drift guard only checks that the Valve name appears somewhere — not that it is described

**File:** `tests/test_filter.py:405-418`
**Problem:** `test_every_valve_is_documented_in_docstring` calls `self.assertIn(field_name, after_marker, …)`. If a future contributor adds a Valve and only writes its name into the `VALVES:` block with no description (or mentions the name incidentally in a CHANGELOG sub-bullet that also lands after the `VALVES:` marker), the guard still passes. `02-CONTEXT.md` explicitly scopes this as a "cheap drift guard; no external doc sync," so the looseness is intentional — noting here so reviewers are not surprised.
**Note:** If a tighter guard is wanted later, match on `        {field_name} ` (eight-space indent + trailing space) to anchor on the documented format of the `VALVES:` block.

## Verdict

**APPROVE**

## One-line summary

Locked pseudocode implemented verbatim, all v3.1.0 invariants preserved, tests cover the six PREVIEW boundary conditions and DOCS-03; three INFO items are discretionary hardening notes with no change required for merge.
