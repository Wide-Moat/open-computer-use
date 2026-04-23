# External Integrations

**Analysis Date:** 2025-04-12

## APIs & External Services

**LLM Provider (Required):**
- OpenAI-compatible API - Any provider (OpenAI, OpenRouter, LiteLLM, custom)
  - SDK/Client: `openai` Python package
  - Auth: `OPENAI_API_KEY` environment variable
  - Config: `OPENAI_API_BASE_URL` (optional, for custom endpoints)
  - Implementation: Passed from client (Open WebUI) to sandbox containers

**Vision API (Optional):**
- Image analysis for describe-image skill
  - Service: OpenAI GPT-4 Vision (or compatible)
  - SDK/Client: `openai` Python package
  - Auth: `VISION_API_KEY` environment variable
  - Endpoint: `VISION_API_URL` (default: `https://api.openai.com/v1`)
  - Model: `VISION_MODEL` (default: `gpt-4o`)
  - Location: `skills/public/describe-image/scripts/describe.py`

**Claude Code Sub-Agent (Optional):**
- AI coding assistant for autonomous skill execution
  - Service: Anthropic Claude API
  - SDK/Client: `@anthropic-ai/claude-code` (npm global)
  - Auth: `ANTHROPIC_AUTH_TOKEN` environment variable
  - Endpoint: `ANTHROPIC_BASE_URL` (default: `https://api.anthropic.com`)
  - Configuration: Injected into sandbox containers at runtime
  - Location: `computer-use-server/docker_manager.py` - container env setup

**GitLab Integration (Optional):**
- Version control and token management
  - Service: GitLab (gitlab.com or self-hosted)
  - SDK/Client: `glab` CLI (1.52.0) installed in container
  - Auth: `GITLAB_TOKEN` environment variable
  - Host: `GITLAB_HOST` (default: `gitlab.com`)
  - Implementation:
    - Git auth via URL rewriting: `git config url.<https://oauth2:TOKEN@HOST/>.insteadOf`
    - Dynamic token fetch: `settings-wrapper` service can provide per-user tokens
  - Location: `computer-use-server/docker_manager.py` - env injection

## Data Storage

**Databases:**

**PostgreSQL 17 (Open WebUI metadata):**
- Connection string: `postgresql://openwebui:${POSTGRES_PASSWORD}@postgres:5432/openwebui`
- Client: SQLAlchemy (built into Open WebUI)
- Startup dependency: `docker-compose.webui.yml` postgres service
- Volumes: `postgres-data` Docker volume (persistent)
- Healthcheck: `pg_isready -U openwebui`
- Configuration:
  - User: `openwebui`
  - Password: `POSTGRES_PASSWORD` env var
  - Database: `openwebui`

**File Storage:**

**Local filesystem:**
- Input uploads: `/mnt/user-data/uploads/` (read-only for agent)
- Output files: `/mnt/user-data/outputs/` (agent writes results here)
- Workspace: `/home/assistant/` (ephemeral, not synced)
- Intermediate: `/tmp/computer-use-data/` (host-mounted for container access)
- Skills cache: `skills-cache` Docker volume (shared)

**Docker volumes:**
- `open-webui-data` - Open WebUI application state
- `postgres-data` - PostgreSQL databases
- `computer-use-data` - Agent execution data (host mount: `/tmp/computer-use-data`)
- `skills-cache` - Cached skill metadata and resources

**Caching:**
- File caching: Redis not used (Open WebUI bypasses embedding/retrieval)
- Docker layer caching: Node.js/Python packages cached in image layers
- Skill metadata caching: `skills-cache` volume

## Authentication & Identity

**Auth Provider:**
- Custom (Open WebUI built-in authentication)
- Implementation:
  - Admin email/password: `ADMIN_EMAIL`, `ADMIN_PASSWORD` (auto-init on first run)
  - Session tokens: Stored in PostgreSQL
  - Multi-user mode: `X-Chat-Id` header isolation (required if `SINGLE_USER_MODE=false`)
  - Single-user mode: One container per session, optional chat ID

**External Auth:**
- GitLab token management: Optional `MCP_TOKENS_API_KEY` via `settings-wrapper` service
- Token refresh: `computer-use-server/docker_manager.py` - fetches tokens before container creation

## Monitoring & Observability

**Error Tracking:**
- None configured by default
- Log output: Container stdout/stderr captured by Docker

**Logs:**
- Application logs: FastAPI (Computer Use Server) + Uvicorn
- Debug logging: Controlled by Uvicorn/FastAPI log level (`--log-level debug`) and Python `logging` config
- Skill logs: Written to `/mnt/user-data/outputs/` (agent's working directory)
- Container logs: `docker logs <container-name>`
- Health checks: Uvicorn health endpoint at `/health` (Computer Use Server)

**Tracing:**
- Not implemented (no OpenTelemetry or similar)

## CI/CD & Deployment

**Hosting:**
- Docker containers - Self-hosted via Docker Compose
- Image registry: Local build (`open-computer-use:latest`)
- Kubernetes: Not integrated (Docker Compose only)

**CI Pipeline:**
- None configured in this repository
- Test scripts: `./tests/test-docker-image.sh`, `./tests/test-no-corporate.sh`, `./tests/test-project-structure.sh`
- Manual build: `docker build --platform linux/amd64 -t open-computer-use:latest .`

**Container Lifecycle:**
- Workspace container: Built once per `docker-compose up`, exits after verification
- Computer Use Server: Long-running (always-active MCP endpoint)
- Agent containers: Spawned per task, auto-removed after completion
- Cleanup cron: Removes stopped containers (default 24h TTL)

## Environment Configuration

**Required env vars:**
- `OPENAI_API_KEY` - LLM provider authentication
- `MCP_API_KEY` - Computer Use Server API authorization (leave empty for dev)
- `POSTGRES_PASSWORD` - PostgreSQL user password
- `OPENWEBUI_VERSION` - Open WebUI base version (default: 0.8.12)

**Optional env vars:**
- `OPENAI_API_BASE_URL` - Custom LLM endpoint (OpenRouter, LiteLLM)
- `ANTHROPIC_AUTH_TOKEN` - Claude Code integration
- `ANTHROPIC_BASE_URL` - Custom Anthropic endpoint
- `VISION_API_KEY`, `VISION_API_URL`, `VISION_MODEL` - Vision API configuration
- `GITLAB_TOKEN`, `GITLAB_HOST` - GitLab integration
- `COMMAND_TIMEOUT` - Agent command timeout (seconds)
- `SUB_AGENT_TIMEOUT` - Sub-agent execution timeout (seconds)
- `SINGLE_USER_MODE` - Multi-user vs single-container mode
- `TOOL_RESULT_MAX_CHARS`, `TOOL_RESULT_PREVIEW_CHARS` - Tool result truncation
- `DOCKER_IMAGE` - Custom sandbox image name
- `CONTAINER_MAX_AGE_HOURS` - Cleanup cron TTL for stopped containers
- `DATA_MAX_AGE_DAYS` - Cleanup cron TTL for orphaned data
- `ENABLE_OPENAI_API_SSL_VERIFY` - SSL verification for custom LLM endpoints
- `ADMIN_EMAIL`, `ADMIN_PASSWORD` - Open WebUI admin (auto-init only)
- `MCP_TOKENS_URL`, `MCP_TOKENS_API_KEY` - Optional external skill/tokens provider for per-user `<available_skills>`; when unset, the server falls back to `DEFAULT_PUBLIC_SKILLS`
- `SKILLS_CACHE_DIR`, `SKILLS_CACHE_HOST_PATH` - Disk cache for user-uploaded skill ZIPs (container-visible and Docker-host paths respectively)

**Secrets location:**
- `.env` file (must be created from `.env.example`)
- Secrets MUST NOT be committed to git (`.env` in `.gitignore`)

## Webhooks & Callbacks

**Incoming:**
- None implemented

**Outgoing:**
- None implemented

**Container Communication:**
- Computer Use Server health check: `/health` endpoint (internal)
- MCP tools endpoint: `POST /mcp` with Authorization header
- Sub-agent communication: Chat completion requests via `ANTHROPIC_AUTH_TOKEN`
- Vision API calls: OpenAI-compatible endpoint

## Integration Flow

**Chat Message Processing:**

1. User sends message in Open WebUI (port 3000)
2. Open WebUI calls Computer Use Tool (`ai_computer_use`) with chat context
3. Tool makes request to Computer Use Server (port 8081, localhost or host.docker.internal)
4. Server spawns new sandbox container with task context
5. Container executes skills (document generation, Playwright automation, OCR, vision)
6. Results uploaded to `/mnt/user-data/outputs/` (mounted on server)
7. Server returns file paths + previews to Open WebUI
8. UI displays artifacts (code blocks, documents, browser screenshots)

**Skill Execution:**
- Skills are read from `/mnt/skills/public/`, `/mnt/skills/private/`, `/mnt/skills/user/`
- Each skill has a `SKILL.md` describing interface and requirements
- Skills are symlinked into container's `/home/assistant/.claude/skills/`
- Claude Code can invoke skills directly or agent can call skill MCP tools

## Cross-Codebase References

**Open WebUI Patches:**
- `openwebui/patches/fix_tool_loop_errors.py` - Tool execution error handling
- `openwebui/patches/fix_artifacts_auto_show.py` - Auto-open artifacts panel
- `openwebui/patches/fix_preview_url_detection.py` - File preview URL detection (uses `COMPUTER_USE_SERVER_URL`)
- `openwebui/patches/fix_large_tool_results.py` - Tool result truncation
- `openwebui/tools/computer_use_tools.py` - MCP client proxy

**Server-Side Integration:**
- `computer-use-server/mcp_tools.py` - MCP tool definitions + skill execution
- `computer-use-server/docker_manager.py` - Container lifecycle + env injection (ANTHROPIC, VISION, GITLAB tokens)
- `computer-use-server/skill_manager.py` - Skill discovery and loading
- `computer-use-server/app.py` - FastAPI entry point + health checks

---

*Integration audit: 2025-04-12*
