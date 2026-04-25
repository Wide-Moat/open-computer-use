---
phase: 10-release-v0-9-2-0
reviewed: 2026-04-25T00:00:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - openwebui/Dockerfile
  - docker-compose.webui.yml
  - README.md
  - CHANGELOG.md
findings:
  critical: 0
  warning: 1
  info: 3
  total: 4
status: issues_found
---

# Phase 10: Code Review Report

**Reviewed:** 2026-04-25
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Release commit cutting `v0.9.2.0` — bumps Open WebUI base from `0.8.12` to `0.9.2` in `openwebui/Dockerfile` and `docker-compose.webui.yml`, prepends a `v0.9.2.0` entry to `CHANGELOG.md`, and refreshes the compatibility wording in `README.md`. The two version-defining knobs (`Dockerfile:3` `ARG OPENWEBUI_VERSION=0.9.2` and `docker-compose.webui.yml:18` `OPENWEBUI_VERSION:-0.9.2`) agree, the compose YAML is syntactically correct, and the CHANGELOG entry accurately mirrors the file changes it claims.

One real consistency bug remains: the README's "embedding into your own stack" cookbook still shows `OPENWEBUI_VERSION: "0.8.12"` in its copy-paste example (`README.md:263`). Copy-paste users following Step 1 will silently downgrade to the previous base — exactly the wrong default for the release this commit is cutting. Three lower-priority doc-staleness items also flagged below.

Project versioning policy in `CLAUDE.md` says the first three segments of `v0.8.X.Y` track the Open WebUI base — bumping `0.8.12` → `0.9.2` therefore correctly resets the patch counter to `Y=0`, giving `v0.9.2.0`. CHANGELOG heading matches.

## Warnings

### WR-01: README "embedding" example pins the OLD Open WebUI base

**File:** `README.md:263`
**Issue:** Inside the Step 1 copy-paste yaml block under "Required setup when embedding Open WebUI into your own stack", the example `build.args.OPENWEBUI_VERSION` is still `"0.8.12"`:

```yaml
        OPENWEBUI_VERSION: "0.8.12"
        COMPUTER_USE_SERVER_URL: "cu.your-domain.com"   # see Step 2 — NOT an internal hostname
```

This is the documented downstream-integration recipe — operators following this guide on a fresh `v0.9.2.0` clone will paste a build-arg that pins the previous base, silently undoing the headline change of this release. It also disagrees with the new defaults in `openwebui/Dockerfile:3` and `docker-compose.webui.yml:18` (both `0.9.2`), and with the README's own line 193 ("Tested with Open WebUI v0.9.2 (current default)"). This isn't a syntax problem — it's a real footgun for the most security-sensitive copy-paste path in the doc.

**Fix:**
```yaml
        OPENWEBUI_VERSION: "0.9.2"
        COMPUTER_USE_SERVER_URL: "cu.your-domain.com"   # see Step 2 — NOT an internal hostname
```

If keeping a 0.8.12 example is intentional (showing how to pin the old base), make that explicit in the surrounding prose ("If you need to stay on the previous base, set ...") and update the default-path example to `0.9.2`. Right now nothing in the surrounding paragraph signals that `0.8.12` is the legacy value.

## Info

### IN-01: Dockerfile comment claims patches were "rewritten for v0.9.1" — actually v0.9.2

**File:** `openwebui/Dockerfile:25`
**Issue:** The block comment reads `# Enabled backend patches (rewritten for v0.9.1 in Phase 6):`. Per `CHANGELOG.md:7` ("the 0.9.1-era patches were rewritten as the v0.9.2 baseline (Phases 4–6), and only the v0.9.2 re-verification (Phases 7–9) was carried into this release") and `CHANGELOG.md:16` (`fix_tool_loop_errors` — rewrite-enabled at v0.9.2), the rewrite that actually shipped landed against v0.9.2. The Dockerfile comment is from the abandoned v0.9.1 cut and was not updated when the base bumped. Misleading future readers about which version forced the SEARCH/REPLACE rewrite.

**Fix:**
```dockerfile
# Enabled backend patches (rewritten for v0.9.2 in Phases 4–6):
```

### IN-02: README compatibility line omits 0.9.1 even though CHANGELOG claims it works

**File:** `README.md:193`, `README.md:195`
**Issue:** README says "Prior base v0.8.11–0.8.12 still works" and "you can use stock Open WebUI versions v0.8.11–0.9.2". `CHANGELOG.md:8` says "All 8 patches still apply to 0.8.12 and 0.9.1 via the backward-compat shim". Either the README range should explicitly include 0.9.1 ("v0.8.11–0.8.12 and v0.9.1 still works", or "v0.8.11–0.9.2") or the CHANGELOG should de-emphasise 0.9.1 since no v0.9.1 release was cut. Currently the two docs disagree on whether 0.9.1 is a supported pin target.

**Fix:** Pick one story. Suggested README line:
```
**Compatibility:** Tested with Open WebUI v0.9.2 (current default). Prior bases v0.8.11–0.8.12 and v0.9.1 still work via `OPENWEBUI_VERSION=<version>` in `.env` (the v0.9.1 path uses the in-memory shim in `fix_tool_loop_errors`).
```

### IN-03: CHANGELOG verification claim is unverifiable from this commit

**File:** `CHANGELOG.md:23`, `CHANGELOG.md:41`
**Issue:** The CHANGELOG asserts "248 passed, 0 failed (+19 v0.9.2 cases on top of the 229-test v0.9.1 baseline)" and that the build emits "8 `PATCHED: fix_* applied successfully.` lines and 0 `ERROR:` lines". These are good claims to make, but nothing in the four files under review can substantiate them — they're statements about test runs and image builds done in earlier phases. The Known Limitations entry on `CHANGELOG.md:41` explicitly defers live UI UAT to the user, which is honest. No action required if Phase 7–9 verification artifacts back these numbers; flagging only because release CHANGELOGs that overstate verification become reputational debt later. Skim the phase 9 `*-VERIFICATION.md` to confirm the "248 passed" figure is the actual pytest output, not a copy from a draft.

**Fix:** No code change. If a phase 9 verification artifact exists with the literal `248 passed, 0 failed` line, this is fine as-is.

---

_Reviewed: 2026-04-25_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
