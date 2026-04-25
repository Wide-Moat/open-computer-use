# Codebase Structure

**Analysis Date:** 2026-04-12

## Directory Layout

```text
project-root/
├── computer-use-server/         # MCP orchestrator (FastAPI, Docker management)
│   ├── app.py                   # FastAPI server, MCP endpoint, file server
│   ├── mcp_tools.py             # MCP tool definitions (bash, file, sub_agent, etc.)
│   ├── docker_manager.py        # Docker container lifecycle, execution, networking
│   ├── skill_manager.py         # Skill caching, manifest, Docker mounts
│   ├── system_prompt.py         # Dynamic system prompt template building
│   ├── context_vars.py          # Request-scoped context variables
│   ├── security.py              # Path validation, sanitization
│   ├── Dockerfile               # Python 3.11, FastAPI, docker.io SDK, aiohttp
│   ├── requirements.txt         # Python dependencies (fastapi, pydantic, docker, aiohttp)
│   ├── static/                  # Generated skill documentation HTML (27 dirs)
│   └── README.md                # Architecture overview
├── openwebui/                   # Open WebUI integration (tools, functions, patches)
│   ├── tools/
│   │   └── computer_use_tools.py  # MCP client proxy tool (thin wrapper)
│   ├── functions/
│   │   └── computer_link_filter.py # System prompt injector + file URL rewriter
│   ├── patches/                 # Build-time fixes (10 patches for artifacts, errors, file handling)
│   ├── init.sh                  # Auto-setup script (creates admin user, installs tool + filter)
│   ├── Dockerfile               # Patches Open WebUI image with tools + functions
│   └── README.md                # Setup and configuration
├── skills/                      # Pluggable skill modules
│   └── public/                  # Built-in public skills (MIT license)
│       ├── pptx/                # PowerPoint creation/editing (ooxml, pptxgenjs)
│       ├── docx/                # Word document creation/editing (python-docx)
│       ├── xlsx/                # Excel spreadsheet creation/editing (openpyxl)
│       ├── pdf/                 # PDF manipulation (pypdf, pdf-lib, reportlab)
│       ├── sub-agent/           # Claude Code delegation (spawn separate session)
│       ├── playwright-cli/       # Web automation (Playwright, CDP)
│       ├── describe-image/       # Vision API image analysis
│       ├── doc-coauthoring/     # Structured document workflow
│       ├── webapp-testing/       # Web app testing with Playwright
│       ├── test-driven-development/ # TDD methodology guidance
│       ├── skill-creator/       # Skill scaffolding + packaging
│       ├── frontend-design/     # UI/UX design patterns
│       └── gitlab-explorer/     # GitLab repo navigation
├── settings-wrapper/            # Optional: Per-user skill access + token management
│   ├── app.py                   # Flask API for token storage/retrieval
│   ├── skills/                  # Custom skill directory (user-uploaded)
│   └── README.md                # Setup and API docs
├── cron/                        # Cleanup job (removes old containers/volumes)
│   └── Dockerfile               # Runs cleanup script periodically
├── tests/                       # Test suite (pytest)
│   ├── orchestrator/            # MCP tools integration tests
│   ├── patches/                 # Open WebUI patch verification
│   ├── security/                # Path traversal, XSS, permission tests
│   └── test_*.sh                # Docker image verification scripts
├── docs/                        # Documentation
│   ├── FEATURES.md              # Feature details and architecture diagrams
│   ├── SKILLS.md                # Skill reference and examples
│   ├── MCP.md                   # MCP integration guide
│   ├── COMPARISON.md            # Feature comparison with alternatives
│   ├── architecture.svg         # System architecture diagram
│   ├── sandbox-contents.svg     # Sandbox tooling diagram
│   └── screenshots/             # Screenshots for README
├── Dockerfile                   # Workspace sandbox image (Ubuntu 24.04, Python, Node.js, tools)
├── docker-compose.yml           # Computer Use Server stack (server, cleanup, workspace)
├── docker-compose.webui.yml     # Open WebUI + PostgreSQL stack (separate)
├── package.json                 # Node.js dependencies (pptxgenjs, pdf-lib, playwright, etc.)
├── requirements.txt             # Python dependencies (FastAPI, docker, aiohttp, PyYAML)
├── README.md                    # Main documentation
├── CHANGELOG.md                 # Release notes
├── CLAUDE.md                    # Project instructions (testing, versioning, structure)
└── server.json                  # MCP server manifest (registry listing)
```

## Directory Purposes

**computer-use-server/:**
- Purpose: Central orchestrator — receives MCP requests, manages Docker containers, executes tools
- Contains: FastAPI app, tool definitions, Docker lifecycle management, skill injection, system prompt building
- Key files: `app.py` (HTTP server), `mcp_tools.py` (tool handlers), `docker_manager.py` (container ops), `skill_manager.py` (skill caching)

**openwebui/:**
- Purpose: Bridge between Open WebUI and Computer Use Server; integrations, patches, auto-setup
- Contains: MCP client proxy tool, system prompt filter, UX patches, initialization script
- Key files: `computer_use_tools.py` (MCP client), `computer_link_filter.py` (prompt injection), `patches/*.py` (optional enhancements)

**skills/public/:**
- Purpose: Reusable knowledge modules for specific domains; auto-mounted in containers
- Contains: 13 built-in skills + 14 examples; each skill has SKILL.md (documentation) + supporting code
- Key files: `*/SKILL.md` (read by LLM before coding), `*/scripts/` (utility functions), `*/references/` (examples)

**settings-wrapper/:**
- Purpose: Optional centralized management for per-user skills, custom skills, encrypted tokens
- Contains: Flask API, PostgreSQL integration, skill registry
- Key files: `app.py` (API server), `skills/` (user-uploaded custom skills)

**tests/:**
- Purpose: Validation suite for Docker image, MCP tools, security, Open WebUI patches
- Contains: pytest tests, bash test scripts, integration tests, security checks
- Key files: `orchestrator/test_*.py` (MCP integration), `security/test_*.py` (path traversal, XSS), `test-*.sh` (shell tests)

**docs/:**
- Purpose: User and developer documentation; architecture diagrams, guides, feature lists
- Contains: Markdown guides, SVG architecture diagrams, screenshots
- Key files: `FEATURES.md`, `SKILLS.md`, `MCP.md`, `COMPARISON.md`

## Key File Locations

**Entry Points:**

- `computer-use-server/app.py`: FastAPI server entry point; starts on `http://0.0.0.0:8081`
- `openwebui/tools/computer_use_tools.py`: Open WebUI tool proxy; bridges UI to orchestrator
- `openwebui/init.sh`: Auto-setup on container start; creates admin user, installs tool + filter
- `Dockerfile`: Sandbox image build; Ubuntu 24.04 base, installs all runtimes and tools

**Configuration:**

- `.env` (or `.env.example`): Environment variables (API keys, Docker settings, timeouts, etc.)
- `docker-compose.yml`: Orchestrator stack definition (server, cleanup, workspace image)
- `docker-compose.webui.yml`: Open WebUI + PostgreSQL stack
- `CLAUDE.md`: Project conventions (license headers, versioning, testing requirements)
- `server.json`: MCP server manifest for registry

**Core Logic:**

- `computer-use-server/mcp_tools.py`: MCP tool implementations (bash_tool, str_replace, file_create, view, sub_agent)
- `computer-use-server/docker_manager.py`: Container creation, command execution, networking, token injection
- `computer-use-server/skill_manager.py`: Skill caching, manifest generation, Docker mounts
- `computer-use-server/system_prompt.py`: System prompt template with skill injection
- `openwebui/functions/computer_link_filter.py`: System prompt injection + file URL generation

**Testing:**

- `tests/orchestrator/test_mcp_tools.py`: MCP tool integration tests (bash execution, file operations)
- `tests/security/test_path_traversal_*.py`: Path validation, XSS prevention, file access checks
- `tests/test_*.sh`: Docker image verification (npm packages, CLI tools, volume size, structure)

## Naming Conventions

**Files:**

- Python modules: `snake_case.py` (e.g., `docker_manager.py`, `skill_manager.py`)
- Test files: `test_*.py` or `*_test.py` (pytest discovery pattern)
- Skills: `SKILL.md` (uppercase; indicates primary documentation file)
- Docker files: `Dockerfile` (no extension; convention), `docker-compose*.yml`
- Config files: `.env`, `.env.example`, `server.json` (JSON), `requirements.txt`, `package.json`

**Directories:**

- Feature modules: `snake_case/` (e.g., `computer-use-server/`, `settings-wrapper/`)
- Skills: `kebab-case/` (e.g., `playwright-cli/`, `doc-coauthoring/`, `skill-creator/`)
- Tests: `tests/` with subfolders by type (`orchestrator/`, `security/`, `patches/`)
- Build artifacts: `.pytest_cache/`, `__pycache__/`, `dist/`, `*.egg-info/` (git-ignored)

**Functions/Classes:**

- Python functions: `snake_case()` (e.g., `get_docker_client()`, `_execute_bash()`)
- Classes: `PascalCase` (e.g., `Filter`, `Valves`, `MCPClient`)
- Private helpers: `_snake_case()` prefix (e.g., `_validate_chat_id()`)
- Context variables: `current_snake_case` (e.g., `current_chat_id`, `current_user_email`)

**MCP Tools:**

- Exact names: `bash_tool`, `str_replace`, `file_create`, `view`, `sub_agent` (referenced by name in LLM calls)
- Defined in: `computer-use-server/mcp_tools.py` as FastMCP-decorated functions

## Where to Add New Code

**New MCP Tool (e.g., web_fetch):**
- Primary code: `computer-use-server/mcp_tools.py` — add `@mcp.tool()` decorated async function
- Docker manager delegation: If requires execution, call `docker_manager._execute_bash()` or `_execute_python_with_stdin()`
- Context variables: Use `current_chat_id.get()`, `current_user_email.get()` for request scope
- Tests: Add to `tests/orchestrator/test_mcp_tools.py`

**New Skill (e.g., video_editor):**
- Location: `skills/public/video-editor/` (kebab-case)
- Structure: `SKILL.md` (documentation), `scripts/` (helper functions), `references/` (examples)
- License: Add `LICENSE.txt` if third-party code; otherwise MIT or BUSL-1.1
- Registration: Add to `system_prompt.py` → `NATIVE_PROMPT_DESCRIPTIONS` dictionary
- Mounting: Skill manager auto-discovers and mounts at `/mnt/skills/public/video-editor/SKILL.md`

**New Open WebUI Patch (e.g., improve_artifacts_ui):**
- Location: `openwebui/patches/fix_improve_artifacts_ui.py`
- Pattern: Python file that monkey-patches Open WebUI modules at startup
- Registration: Add import to `openwebui/Dockerfile` build step
- Testing: Add to `tests/patches/test_*.py` to verify patch applies correctly

**New Utility/Helper:**
- Shared helpers (used by multiple tools): `computer-use-server/helpers/` (new directory)
- Security utilities: `computer-use-server/security.py` (existing)
- Skill utilities: `computer-use-server/skill_manager.py` (existing, extend if needed)

**New Test:**
- MCP tool integration: `tests/orchestrator/test_*.py`
- Security validations: `tests/security/test_*.py`
- Open WebUI patches: `tests/patches/test_*.py`
- Docker image verification: `tests/test-*.sh` (bash)

## Special Directories

**`.playwright-mcp/`:**
- Purpose: Playwright MCP server directory (generated by Playwright CLI)
- Generated: Yes (auto-created on first Playwright MCP setup)
- Committed: No (git-ignored via `.gitignore`)

**`computer-use-server/static/`:**
- Purpose: Generated HTML documentation for skills (parsed from SKILL.md files)
- Generated: Yes (built at startup by `skill_manager.py`)
- Committed: Yes (checked in for serving via `/docs/skills/` endpoint)

**`data/` and `/tmp/computer-use-data/`:**
- Purpose: Runtime container data, uploads, outputs; volumes in docker-compose
- Generated: Yes (created on first container start)
- Committed: No (git-ignored, ephemeral data)

**`.pytest_cache/`, `__pycache__/`:**
- Purpose: Test and Python bytecode caches
- Generated: Yes (pytest and Python interpreter)
- Committed: No (git-ignored)

**`.env` and `.env.*` (except `.env.example`):**
- Purpose: Environment variable configuration (secrets, API keys, settings)
- Generated: No (user-created from `.env.example`)
- Committed: No (git-ignored for security)

---

*Structure analysis: 2026-04-12*
