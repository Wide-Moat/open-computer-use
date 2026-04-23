# Architecture

**Analysis Date:** 2026-04-12

## Pattern Overview

**Overall:** Distributed three-tier MCP (Model Context Protocol) architecture with isolated Docker sandboxes per chat session.

**Key Characteristics:**
- Client-server separation: Open WebUI (frontend) ↔ Computer Use Server (backend orchestrator) ↔ Docker sandboxes (execution)
- Per-session isolation: Each chat session (`chat_id`) spawns a dedicated Docker container with file, process, and state isolation
- MCP Streamable HTTP protocol: All tool calls flow through JSON-RPC endpoints, compatible with any MCP client (not just Open WebUI)
- Skills system: Modular SKILL.md documentation files auto-injected into sandboxes; LLM reads skills before executing code
- Pluggable architecture: Optional settings wrapper for token management; extensible skill registry; support for custom MCP servers

## Layers

**Presentation Layer (Open WebUI integration):**
- Purpose: Web UI for chat and file management; bridges to Computer Use Server via MCP protocol
- Location: `openwebui/` directory
- Contains: Tools (thin proxy client), Functions (system prompt injection + filter), Patches (UX improvements), Init script (auto-setup)
- Depends on: Computer Use Server `/mcp` endpoint; File Server endpoints for downloads
- Used by: End users; connects via HTTP to `http://computer-use-server:8081/mcp`

**Orchestration Layer (MCP Server + Docker Manager):**
- Purpose: Central hub for MCP request handling, Docker container lifecycle, command execution, and file management
- Location: `computer-use-server/` directory
- Contains: 
  - `app.py`: FastAPI HTTP server, MCP JSON-RPC endpoint, file upload/download, health checks
  - `mcp_tools.py`: MCP tool definitions (bash_tool, str_replace, file_create, view, sub_agent) — delegates to docker_manager
  - `docker_manager.py`: Container creation, execution, networking, CDP proxy, token injection
  - `skill_manager.py`: Skill caching, manifest management, Docker mounts for skill access
  - `system_prompt.py`: Dynamic system prompt building with skill descriptions and file URLs
  - `context_vars.py`: Request-scoped context (chat_id, user email, API keys, GitLab tokens)
- Depends on: Docker daemon (local socket); optional MCP Tokens Wrapper for token management
- Used by: Open WebUI tool calls, Claude Desktop, n8n, LiteLLM, any MCP client

**Sandbox Layer (Docker containers):**
- Purpose: Isolated Linux (Ubuntu 24.04) environment for code execution
- Location: Dockerfile at repository root
- Contains: Python 3.12, Node.js 22, Java 21, Bun; Libraries: Playwright, LibreOffice, Pandoc, pdf-lib, pptxgenjs, Claude Code CLI, etc.
- Depends on: Computer Use Server for command dispatch; skill files mounted at `/mnt/skills/`
- Used by: All tool calls from orchestrator; sub_agent Claude Code CLI sessions

**Skills Layer (Pluggable documentation + code):**
- Purpose: Best-practice guides and code examples for specific domains (document creation, web automation, etc.)
- Location: `skills/public/` for built-in skills; user-uploaded via Settings Wrapper
- Contains: 13 built-in public skills (pptx, docx, xlsx, pdf, sub-agent, playwright-cli, describe-image, etc.) + examples
- Depends on: Skill manager for caching and mounting; Docker containers access via `/mnt/skills/` paths
- Used by: LLM reads SKILL.md before coding; skills define best practices for output quality

## Data Flow

**MCP Tool Execution Flow (bash_tool example):**

1. User asks: "Execute `npm install`"
2. Open WebUI client → `POST /mcp` with MCP JSON-RPC (tool_name: `bash_tool`, arguments: `{command: "npm install"}`)
3. `app.py` receives request → validates MCP auth → extracts chat_id from `X-Chat-Id` header
4. Sets context variables: `current_chat_id = chat_id`, `current_user_email`, etc.
5. Routes to `mcp_tools.py` → `bash_tool` handler
6. Handler calls `docker_manager.py:_execute_bash()` → gets or creates container `owui-chat-{chat_id}`
7. Docker container executes command via `docker exec` → stdout/stderr streamed back
8. Response: MCP JSON-RPC with `{status: "success", output: "..."}` → sent back to client
9. Client renders output; files written to container's `/mnt/user-data/outputs/` are accessible via HTTP file server

**File Download Flow:**

1. LLM generates file in container at `/mnt/user-data/outputs/report.docx`
2. LLM returns response with file URL: `http://computer-use-server:8081/files/{chat_id}/report.docx`
3. User clicks link → browser requests `/files/{chat_id}/report.docx`
4. `app.py:GET /files/{chat_id}/{path}` → sanitizes path → reads from container volume at `/tmp/computer-use-data/{chat_id}/outputs/`
5. Returns file with correct MIME type → browser downloads

**Skill Injection Flow (dynamic system prompt):**

1. Skill manager queries Settings Wrapper (optional) or uses hardcoded native skills
2. For each enabled skill: reads `SKILL.md` description and generates `<available_skills>` XML block
3. `system_prompt.py:build_system_prompt()` → injects skill list into system prompt template
4. `openwebui/functions/computer_link_filter.py:inlet()` → adds file URLs placeholders
5. Final prompt sent to LLM with:
   - Skill descriptions (what each skill is for, when to use it)
   - File base URL (`http://computer-use-server:8081/files/{chat_id}/`)
   - Archive URL for batch download
6. LLM reads SKILL.md files directly via `view /mnt/skills/public/pptx/SKILL.md` when needed

**State Management:**

- **Chat-scoped state**: Container persists for duration of chat session; idle timeout after 10 minutes with no commands
- **File state**: `/mnt/user-data/uploads/` (read-only, user-uploaded files); `/mnt/user-data/outputs/` (LLM-created files, exposed via HTTP)
- **Process state**: Container stops when idle timeout expires; next command spawns fresh container with same chat_id
- **No session state persisted**: Container is ephemeral; file server is source of truth for outputs

## Key Abstractions

**MCP Tool:**
- Purpose: Single discrete capability exposed to LLM (execute bash, edit file, create file, view directory, spawn sub_agent)
- Examples: `bash_tool` (`mcp_tools.py`), `str_replace` (`mcp_tools.py`), `sub_agent` (`mcp_tools.py`)
- Pattern: Each tool is a FastMCP-decorated function that validates inputs, delegates to docker_manager, streams output

**Skill:**
- Purpose: Reusable knowledge base for specific domain (e.g., "how to create a professional PowerPoint")
- Examples: `skills/public/pptx/SKILL.md`, `skills/public/docx/SKILL.md`, `skills/public/pdf/SKILL.md`
- Pattern: Folder with `SKILL.md` (documentation), supporting code files (scripts/, ooxml/, etc.), examples; mounted into container at `/mnt/skills/`

**Chat Session Container:**
- Purpose: Isolated sandbox per chat; manages lifecycle, resource limits, file I/O
- Examples: Container named `owui-chat-{chat_id}` created on first tool call, torn down after idle timeout
- Pattern: Standard Docker container (2GB RAM, 1 CPU limits) with volume mounts: user data, skills, code execution

**System Prompt Template:**
- Purpose: Core instruction set for LLM behavior; customizable with placeholders for dynamic content
- Examples: `SYSTEM_PROMPT_TEMPLATE` in `system_prompt.py`; placeholders: `{file_base_url}`, `{archive_url}`, skill list block
- Pattern: Multi-part template (before skills, skill XML block, after skills) substituted at runtime

## Entry Points

**MCP JSON-RPC Endpoint:**
- Location: `computer-use-server/app.py:POST /mcp`
- Triggers: Any MCP client sends `{"method": "tools/call", "params": {...}}`
- Responsibilities: Validate auth → parse MCP request → delegate to tool handler → return JSON-RPC response

**HTTP File Server:**
- Location: `computer-use-server/app.py:GET /files/{chat_id}/{path}`
- Triggers: User clicks file download link or LLM references file URL
- Responsibilities: Sanitize path → verify chat access → return file from container volume

**Web UI Tool Proxy:**
- Location: `openwebui/tools/computer_use_tools.py`
- Triggers: User interacts with Open WebUI, LLM calls Computer Use tool
- Responsibilities: Build HTTP headers from context → call orchestrator `/mcp` → stream response to UI

**System Prompt Filter:**
- Location: `openwebui/functions/computer_link_filter.py`
- Triggers: Before LLM processes request
- Responsibilities: Thin HTTP client — fetches the fully-baked Computer Use system prompt from the orchestrator's `GET /system-prompt` endpoint (server substitutes `{file_base_url}` / `{archive_url}` / `{chat_id}` and assembles the `<available_skills>` XML block per user), caches per `(chat_id, user_email)` with 5-minute TTL + stale-cache fallback, and injects the response as-is into the system message. No client-side substitution.

## Error Handling

**Strategy:** Fault isolation per container; graceful degradation; detailed error messages to LLM.

**Patterns:**

- **Command execution errors**: Bash returns exit code + stderr → wrapped in MCP response as `{status: "error", output: "stderr text"}`
- **Container errors** (unavailable, timeout): Caught in `docker_manager.py` → wrapped with helpful context ("container timeout, retrying...") → returned to LLM
- **File path traversal attacks**: `security.py:safe_path()` validates all file paths; blocks `../` sequences; rejects absolute paths outside user data
- **Invalid chat_id**: Strict multi-user mode (`SINGLE_USER_MODE=false`) requires `X-Chat-Id` header; missing header → 400 Bad Request with explanation
- **MCP auth failure**: Missing/invalid Bearer token → 401 Unauthorized
- **Skills not found**: Skill manager returns empty list; system prompt falls back to hardcoded native skills

## Cross-Cutting Concerns

**Logging:** 
- Python logging module in orchestrator (`logger.info()`, `logger.error()`)
- Container stdout/stderr captured and returned to client
- Debug mode: `DEBUG_LOGGING=true` in docker-compose for verbose output

**Validation:**
- HTTP headers: `X-Chat-Id` (required), `X-User-Email`, `X-User-Name`, `X-Gitlab-Token`, `X-Anthropic-Api-Key` (all optional)
- File paths: `security.py:safe_path()` — no traversal, no absolute paths outside `/mnt/user-data/`
- MCP payloads: Pydantic models in `app.py` validate JSON-RPC structure before processing
- Command timeout: Environment variable `COMMAND_TIMEOUT` (default 120s) — enforced at container level

**Authentication:**
- MCP bearer token: `MCP_API_KEY` environment variable; validated in `app.py:verify_mcp_auth()`
- User identity: Passed via headers (`X-User-Email`, `X-OpenWebUI-User-Email`); NOT verified server-side (trusts client)
- GitLab tokens: Priority order: header → MCP Tokens Wrapper (fetch by email) → none
- Anthropic API keys: Priority order: header → environment variable (`ANTHROPIC_AUTH_TOKEN`)

**Performance Considerations:**

- **Container reuse**: Same container (`owui-chat-{chat_id}`) used for all commands in a chat; no spin-up overhead after first call
- **Skill caching**: `skill_manager.py` caches ZIP files on disk + in-memory manifest; TTL 60s for user skill lists
- **File streaming**: Large command output (>30K chars) truncated; `view` tool uses streaming reads to avoid loading entire files
- **Cleanup job**: Cron service (`cron/`) periodically removes stopped containers + orphaned volumes (configurable age limits)

---

*Architecture analysis: 2026-04-12*
