# Open WebUI Patches

Source surgery applied to the Open WebUI base image at Docker build time. Each patch is a standalone Python script performing literal SEARCH/REPLACE against upstream files; `openwebui/Dockerfile` runs all of them, in order, unconditionally.

Target base: Open WebUI 0.11.0 (`ARG OPENWEBUI_VERSION` in `openwebui/Dockerfile`).

## Patches

| Patch | Target file | Effect |
|---|---|---|
| `fix_artifacts_auto_show.py` | `/app/build/_app/immutable/chunks/*.js` | Auto-opens the Artifacts panel when an assistant message contains HTML code blocks. Without it, previews need a manual click. |
| `fix_tool_loop_errors.py` | `utils/middleware.py` | Surfaces tool-loop, transport, non-streaming, code-interpreter and SSE errors instead of swallowing them, and stops a failed background task from hanging the UI. |
| `fix_preview_url_detection.py` | `/app/build/_app/immutable/chunks/*.js` | Detects file preview URLs in messages and renders them in the Artifacts panel, host-agnostically. |
| `fix_large_tool_results.py` | `utils/middleware.py` | Truncates tool results over `TOOL_RESULT_MAX_CHARS`, in the live loop and in history loaded from the database. Runs after `fix_tool_loop_errors.py`, whose marker it anchors on. |
| `fix_attached_files_position.py` | `utils/middleware.py` | Appends `<attached_files>` to the end of a message rather than prepending, so a large attachment does not invalidate the prompt cache prefix. |
| `fix_skip_embedding_chat_files.py` | `routers/retrieval.py` | Skips extraction and embedding for chat uploads over 1 MB, falling back to a knowledge-base upload instead of blocking the chat. |
| `fix_skip_rag_files_native_fc.py` | `utils/middleware.py` | Skips the RAG pipeline for chat files when the `ai_computer_use` tool is enabled — the tool reads files directly through the MCP server. Files marked `context: full` still go through RAG. |

`fix_large_tool_results.py` reads three environment variables at runtime:

- `TOOL_RESULT_MAX_CHARS` (default 50000) — truncation threshold; `0` disables truncation.
- `TOOL_RESULT_PREVIEW_CHARS` (default 2000) — preview size kept for the model.
- `ORCHESTRATOR_URL` (optional) — base URL for uploading the full result, same value as the Tool/Filter Valve.

## How patches work

Each script locates its anchors in the installed upstream source, applies its modifications, and writes the file back. A `PATCH_MARKER` makes re-runs a no-op, so a rebuilt layer prints `ALREADY PATCHED` rather than double-applying.

Anchor misses are fatal: the script writes `ERROR:` to stderr and exits `1`, failing the `RUN` layer. A base-version bump that moves an anchor breaks the build rather than shipping a partially patched image.

Anchors match exactly one upstream shape, so bumping `ARG OPENWEBUI_VERSION` means re-auditing every patch against the new tree. `tests/patches/` runs each script against byte-identical upstream fixtures for the pinned version, covering fresh apply, idempotent re-run, and fail-loud on a removed anchor.
