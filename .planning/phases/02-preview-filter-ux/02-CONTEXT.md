# Phase 02: Preview Filter UX — Context

**Gathered:** 2026-04-12
**Status:** Ready for planning
**Source:** Pre-approved plan (`/Users/nick/.claude/plans/wild-wobbling-kahan.md`) — decisions locked during plan-mode dialogue with the user.

<domain>
## Phase Boundary

Expose the orchestrator's existing file-preview SPA (`GET /preview/{chat_id}` at `computer-use-server/app.py:1102`) to users of stock Open WebUI (without frontend patches) through the filter's `outlet()`. Every v3.1.0 correctness invariant in the filter stays intact; every Valve (existing and new) is documented in one authoritative place.

**Scope includes:** edits to `openwebui/functions/computer_link_filter.py` (Valves, `outlet()`, docstring, version bump), new unit tests in `tests/test_filter.py`, a new public doc page `docs/openwebui-filter.md`, and Docker-based verification.

**Scope excludes:** server changes (`/preview/{chat_id}` already exists), frontend patches to Open WebUI, release tagging, community PR #41 (Claude Code compat — deferred to a later milestone).

</domain>

<decisions>
## Implementation Decisions (locked during plan-mode)

### Defaults for new Valves

- `ENABLE_PREVIEW_ARTIFACT: bool = True` — **project default**. Inline `<iframe>` preview artifact is the intended UX when the deployment renders fenced ```html blocks as artifacts.
- `ENABLE_PREVIEW_BUTTON: bool = False` — **opt-in** escape hatch for stock Open WebUI installations where artifact rendering is unavailable or the operator wants a click-through link instead.
- `PREVIEW_BUTTON_TEXT: str = "🖥️ Open preview"` — matches community PR #42.

Do not flip these defaults to "safer" opt-in values. The user explicitly confirmed on 2026-04-12 that the iframe artifact is his canonical UX and the button is the workaround.

### Invariants from v3.1.0 `outlet()` that MUST be preserved

1. `role == "assistant"` guard — no other roles (user/system/tool) are ever modified.
2. `isinstance(content, str)` guard — non-string (multimodal list) content is skipped, never coerced.
3. `file_url_pattern` is built with `re.escape(chat_id)` — no cross-chat decoration when a quoted transcript contains a file URL from a different chat.
4. `base = self.valves.FILE_SERVER_URL.rstrip("/")` — trailing-slash configs never produce `//preview/` or `//files/`.
5. Idempotency by substring check — the existing archive button uses `archive_url not in content`; the same strategy extends to preview URL and the iframe snippet.

### `outlet()` extension — locked pseudocode

```python
if not (self.valves.ENABLE_ARCHIVE_BUTTON
        or self.valves.ENABLE_PREVIEW_BUTTON
        or self.valves.ENABLE_PREVIEW_ARTIFACT):
    return body

chat_id = __metadata__.get("chat_id") if __metadata__ else None
if not chat_id:
    return body

base = self.valves.FILE_SERVER_URL.rstrip("/")
file_url_pattern = re.escape(base) + r"/files/" + re.escape(chat_id) + r"/[^\s\)]+"
preview_url = f"{base}/preview/{chat_id}"
archive_url = f"{base}/files/{chat_id}/archive"

for message in body.get("messages", []):
    if message.get("role") != "assistant":
        continue
    content = message.get("content")
    if not content or not isinstance(content, str):
        continue
    if not re.search(file_url_pattern, content):
        continue

    links: list[str] = []
    if self.valves.ENABLE_PREVIEW_BUTTON and preview_url not in content:
        links.append(f"[{self.valves.PREVIEW_BUTTON_TEXT}]({preview_url})")
    if self.valves.ENABLE_ARCHIVE_BUTTON and archive_url not in content:
        links.append(f"[{self.valves.ARCHIVE_BUTTON_TEXT}]({archive_url})")
    if links:
        content += "\n\n" + "\n".join(links)

    if self.valves.ENABLE_PREVIEW_ARTIFACT:
        iframe = (
            f'<iframe src="{preview_url}" '
            f'style="width:100%;height:100%;border:none" '
            f'allow="clipboard-write; keyboard-map"></iframe>'
        )
        if iframe not in content:
            content += "\n\n```html\n" + iframe + "\n```"

    message["content"] = content

return body
```

### Filter version string

Bump `version: 3.1.0` → `version: 3.2.0` in the module docstring header. Semver minor: new feature, no breaking change (old Valves keep defaults). Prepend `CHANGELOG (v3.2.0)` block.

This is the *filter-internal* version string (Open WebUI function metadata). It is **not** the repository release version `v0.8.X.Y` — the repo release is controlled by the user via CHANGELOG.md + tags and is out of scope here.

### Link layout (resolved gray area)

`outlet()` appends links using `"\n\n" + "\n".join(links)` — that is, a single blank-line separator (the v3.1.0 style), not the `---` horizontal rule PR #42 introduced. Rationale: preserves the regression test `test_outlet_appends_archive_button_once` idempotency expectation and reads cleanly in rendered markdown.

### External docs page location (resolved gray area)

`docs/openwebui-filter.md` (new file). Discoverable path under the existing `docs/` tree; co-location with `openwebui/functions/` was considered but rejected because `docs/` is where all other user-facing references live.

### Valve docstring format

Add a `VALVES:` section to the module docstring of `computer_link_filter.py` that enumerates every Valve with name, type, default, and a 1–3 line description. Covers old Valves (`FILE_SERVER_URL`, `SYSTEM_PROMPT_URL`, `INJECT_SYSTEM_PROMPT`, `ENABLE_ARCHIVE_BUTTON`, `ARCHIVE_BUTTON_TEXT`) and new (`ENABLE_PREVIEW_ARTIFACT`, `ENABLE_PREVIEW_BUTTON`, `PREVIEW_BUTTON_TEXT`).

### Drift guard

A new test `test_every_valve_is_documented_in_docstring` asserts that every `Field(...)` on `Filter.Valves` has a matching entry in the `VALVES:` docstring block. Cheap drift guard; no external doc sync (external doc is a manually-maintained superset).

### Claude's Discretion

- Exact phrasing of the `VALVES:` docstring entries and the external doc sections — match existing tone.
- Ordering of test methods within the new `PreviewArtifact` / `PreviewButton` classes.
- Location of the new Valves within `Filter.Valves` body — group preview-related Valves together near `ENABLE_ARCHIVE_BUTTON`.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Core filter + server integration points
- `openwebui/functions/computer_link_filter.py` — current v3.1.0 filter; contains the `outlet()` to extend and the `Filter.Valves` model.
- `computer-use-server/app.py` (lines 208, 1102) — existing `/preview/{chat_id}` SPA endpoint + CORS-for-iframe block confirming iframe embedding is a supported use case.

### Regression baseline
- `tests/test_filter.py` — full existing test file; new test classes must follow the `unittest.TestCase` + `_make_filter` / `_urlopen_mock` helper pattern.

### Project-level constraints
- `CLAUDE.md` — English-only policy, Docker build command, npm layout, license headers, versioning rules (`v0.8.X.Y`).
- `.planning/PROJECT.md` — Core Value + Constraints.
- `.planning/REQUIREMENTS.md` — PREVIEW-01..04, VALVE-01..02, DOCS-01..03, VERIFY-01..03.

### Upstream community PR (credit)
- `https://github.com/Yambr/open-computer-use/pull/42` — source of the idea; cannot be merged mechanically because it targets v3.0.2.

</canonical_refs>

<specifics>
## Specific Ideas

### Test coverage layout

New test classes in `tests/test_filter.py`:

- **`PreviewArtifact`** (6 tests) — covers PREVIEW-01, PREVIEW-03 (invariants for iframe), PREVIEW-04 (iframe idempotency):
  1. `test_outlet_appends_iframe_artifact_by_default`
  2. `test_outlet_iframe_artifact_is_idempotent`
  3. `test_outlet_iframe_artifact_disabled_when_valve_false`
  4. `test_outlet_iframe_artifact_respects_other_chat_ids`
  5. `test_outlet_iframe_not_added_to_non_assistant_roles`
  6. `test_outlet_iframe_url_has_no_double_slash_when_trailing_slash`

- **`PreviewButton`** (4 tests) — covers PREVIEW-02, PREVIEW-04 (button idempotency):
  7. `test_outlet_preview_button_off_by_default`
  8. `test_outlet_preview_button_appended_when_enabled`
  9. `test_outlet_preview_button_is_idempotent`
  10. `test_outlet_preview_button_respects_other_chat_ids`

- **Docs drift** (1 test) — covers DOCS-03:
  11. `test_every_valve_is_documented_in_docstring` — extracts `Field` names from `Filter.Valves` via introspection, asserts each appears as a heading/line in the `VALVES:` block of `computer_link_filter.__doc__`.

### Verification command matrix (VERIFY-01..03)

1. `docker build --platform linux/amd64 -t open-computer-use:latest .`
2. `./tests/test-docker-image.sh open-computer-use:latest && ./tests/test-no-corporate.sh && ./tests/test-project-structure.sh`
3. `docker run --rm -v "$PWD:/src" -w /src python:3.13-slim bash -c "pip install --quiet pytest pydantic && python -m pytest tests/test_filter.py -v"`
4. `docker run --rm -v "$PWD:/src" -w /src python:3.13-slim bash -c "pip install --quiet -r computer-use-server/requirements.txt pytest && python -m pytest tests/orchestrator tests/security tests/patches -v"`

All four must be green.

### Ship flow

Branch `feat/filter-preview-ux` off `main` → `/gsd-pr-branch` to strip `.planning/` from commits bound for public `origin` → `gh pr create` against `main` with PR body crediting `rahxam` + PR #42 → after merge, `gh pr comment 42` with credit + superseded note. **No `git tag`** per `CLAUDE.md` and user memory.

</specifics>

<deferred>
## Deferred Ideas

- **Community PR #41** (Claude Code compatibility env flags) — captured as requirement `CLAUDE-CODE-01` in v2 Requirements; next milestone after v0.8.12.8 ships. Explicitly not in Phase 2 scope.
- **Frontend patches to Open WebUI core** that would remove the need for the button fallback entirely — captured as `FILTER-02` in v2 Requirements; not this milestone.
- **Integration smoke test** (`@pytest.mark.integration`) that spins up orchestrator via `docker-compose up -d` and curls `/preview/{chat_id}` — optional, gated by env var; planner may add or skip at its discretion.

</deferred>

---

*Phase: 02-preview-filter-ux*
*Context gathered: 2026-04-12 — transcribed from approved plan file `/Users/nick/.claude/plans/wild-wobbling-kahan.md` after plan-mode dialogue*
