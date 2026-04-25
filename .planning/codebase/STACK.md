# Technology Stack

**Analysis Date:** 2026-04-12

## Languages

**Primary:**
- Python 3.12.3 - Core sandbox runtime, skill scripts, document processing, ML/vision
- Node.js 22.11.0 - CLI tools, markdown processing, presentation generation (browser automation via Playwright)
- TypeScript - Future support (tsx runner available)

**Secondary:**
- Bash/Shell - Container entrypoints, wrapper scripts, system utilities
- JavaScript - Browser automation with Playwright, React components

## Runtime

**Environment:**
- Ubuntu 24.04 LTS (Noble Numbat) - Base container image
- Python 3.12.3 with pip package manager
- Node.js 22.11.0 via binary distribution
- Bun runtime - Required for Claude Code CLI execution

**Package Managers:**
- pip (Python 3.12) - Lockfile: `requirements.txt`
- npm 10.9.3+ (Node.js) - Lockfile: `package-lock.json` not checked in (npm packages listed in `package.json`)

**Container Runtime:**
- Docker - Workspace isolation for agent execution

## Frameworks

**Core Infrastructure:**
- FastAPI 0.115.0 - MCP server implementation, REST endpoints
- Uvicorn 0.32.0 - ASGI application server for FastAPI

**Document Processing:**
- python-docx 1.2.0 - Word (.docx) document generation
- python-pptx 1.0.2 - PowerPoint (.pptx) document generation
- openpyxl 3.1.5 - Excel (.xlsx) read/write
- xlsxwriter 3.2.9 - Excel generation alternative
- reportlab 4.4.4 - PDF generation with font support (Cyrillic, emoji via DejaVu, Noto)
- pypdf 5.9.0 - PDF manipulation
- pdfplumber 0.11.9 - PDF data extraction
- pdf2image 1.17.0 - PDF to image conversion
- pikepdf 9.11.0 - PDF processing library

**Image & Vision:**
- pillow 12.1.1 - Image manipulation
- opencv-python 4.11.0.86 - Computer vision (headless variant also available)
- scikit-image 0.25.2 - Scientific image processing
- Wand 0.6.13 - ImageMagick wrapper

**OCR & Text Extraction:**
- pytesseract 0.3.13 - OCR via Tesseract engine (with Cyrillic support)
- tabula-py 2.10.0 - PDF table extraction
- camelot-py 1.0.9 - Advanced PDF table extraction
- markitdown 0.1.3 - Document to markdown conversion

**Browser Automation:**
- playwright 1.57.0 - Headless browser control (Python + Node.js versions pinned together)
- @playwright/cli 0.1.1 - Playwright MCP implementation with patched CDP port 9223

**Data Processing:**
- pandas 2.3.3 - Tabular data manipulation
- numpy 2.3.3 - Numerical arrays
- scipy 1.16.2 - Scientific computing
- scikit-learn 1.7.2 - Machine learning utilities

**ML & Vision Models:**
- openai >= 2.20.0 - Vision API client (used for describe-image skill)
- mediapipe 0.10.14 - Computer vision tasks (pose, hand detection)
- magika 0.6.2 - File type magic detection
- onnxruntime 1.23.1 - ML model inference
- jax 0.7.2 + jaxlib 0.7.2 - Numerical computing (optional)

**Web & HTTP:**
- aiohttp >= 3.9.0 - Async HTTP client for skill communication
- requests 2.32.5 - Synchronous HTTP requests
- beautifulsoup4 4.14.2 - HTML/XML parsing

**CLI Tools:**
- @mermaid-js/mermaid-cli 11.12.0 - Diagram generation (CLI mmdc)
- docx 9.5.1 - Word document generation (Node.js)
- pdf-lib 1.17.1 - PDF manipulation (JavaScript)
- pptxgenjs 4.0.1 - PowerPoint generation (Node.js)
- markdown-pdf 11.0.0 - Markdown to PDF conversion (Node.js)
- markdownlint-cli 0.45.0 - Markdown linting
- remark-cli 12.0.1 - Markdown processor
- sharp 0.34.4 - High-performance image processing
- playwright 1.57.0 - Browser automation (Node.js)
- tsx 4.20.6 - TypeScript execution without compilation

**Development & Scripting:**
- ts-node 10.9.2 - TypeScript REPL and execution
- typescript 5.9.3 - TypeScript compiler
- Flask 3.1.3 - Optional lightweight web framework
- python-dotenv 1.1.1 - Environment variable loading

**Claude Code Integration:**
- @anthropic-ai/claude-code@latest - AI code assistant (npm global install)

**UI Framework:**
- Open WebUI v0.8.12 - Chat interface (from ghcr.io/open-webui/open-webui)
- react 19.2.0 - UI library (dev dependency)
- react-dom 19.2.0 - React DOM rendering

**Other Utilities:**
- click 8.3.0 - CLI argument parsing
- colorama 0.4.6 - Terminal colored output
- coloredlogs 15.0.1 - Colored logging
- tabulate 0.9.0 - Table formatting
- psutil 7.1.0 - System monitoring
- PyYAML 6.0.3 - YAML parsing
- pyyaml_env_tag 1.1 - YAML environment variable substitution
- PyJWT 2.12.1 - JWT token handling
- cryptography 46.0.6 - Cryptographic operations
- defusedxml 0.7.1 - Safe XML parsing
- lxml 6.0.2 - XML/HTML parsing

**System Tools (apt packages):**
- graphviz - Graph visualization
- tesseract-ocr - OCR engine (English + Russian language packs)
- poppler-utils - PDF tools (pdftotext, pdftoppm)
- ghostscript - PostScript/PDF processing
- pandoc - Document conversion
- ffmpeg - Video/audio processing
- LibreOffice (writer, calc, impress) - Document editing via unoserver
- ImageMagick + libmagickwand-dev - Image processing
- Java (OpenJDK 21) - Required for tabula-py

## Configuration

**Environment Configuration:**
- `.env` file (template: `.env.example`) - Runtime configuration
- Key variables:
  - `OPENAI_API_KEY` - LLM provider API key
  - `OPENAI_API_BASE_URL` - Custom LLM endpoint (OpenRouter, LiteLLM, etc.)
  - `MCP_API_KEY` - Computer Use Server authorization token
  - `ANTHROPIC_AUTH_TOKEN` - Claude Code sub-agent authentication
  - `ANTHROPIC_BASE_URL` - Custom Anthropic endpoint
  - `VISION_API_KEY`, `VISION_API_URL`, `VISION_MODEL` - Vision API for describe-image skill
  - `GITLAB_TOKEN`, `GITLAB_HOST` - GitLab integration
  - `DOCKER_IMAGE` - Sandbox container image name
  - `POSTGRES_PASSWORD` - PostgreSQL credentials
  - `COMMAND_TIMEOUT` - Agent command timeout (seconds, default 120)
  - `SUB_AGENT_TIMEOUT` - Sub-agent timeout (seconds, default 3600)
  - `SINGLE_USER_MODE` - Multi-user vs single-container mode
  - `TOOL_RESULT_MAX_CHARS` - Truncate large MCP tool results (optional, default 50000)

**Build Configuration:**
- `Dockerfile` - Ubuntu 24.04-based sandbox image with Python, Node.js, document tools
- `docker-compose.yml` - Computer Use Server + workspace image builder + cleanup cron
- `docker-compose.webui.yml` - Open WebUI + PostgreSQL 17
- `openwebui/Dockerfile` - Open WebUI customization (patches + Computer Use tool setup)

**Platform Requirements:**
- Docker & Docker Compose - Container orchestration
- Docker socket access - For workspace container spawning
- Linux kernel - AMD64 architecture (builds target `--platform linux/amd64`)

## Key Dependencies

**Critical:**
- fastapi + uvicorn - MCP server runtime (Computer Use Server at `:8081`)
- mcp >= 1.0.0 - Model Context Protocol server SDK
- docker >= 7.0.0 - Docker API client for container lifecycle
- pydantic >= 2.0.0 - Data validation and settings management

**Document Processing Pipeline:**
- python-docx, python-pptx, openpyxl - Core office document generation
- reportlab - PDF generation with custom fonts (DejaVu, Noto)
- PIL + opencv - Image processing
- pytesseract + Tesseract (system) - OCR with Cyrillic support

**Browser Automation:**
- playwright 1.57.0 (Python + Node.js) - Headless Chromium control
- @playwright/cli 0.1.1 - CDP server with patched port 9223 for external access

**Vision & ML:**
- openai SDK - Vision API for image analysis
- mediapipe - Computer vision tasks (pose, objects, hands)
- onnxruntime - Model inference

**Integration Points:**
- aiohttp - Async HTTP for skill-to-skill communication
- requests - HTTP for vision API, external services
- mcp.server.fastmcp - FastMCP framework for tool definition

## Deployment & Environment

**Development:**
- Local Docker with `docker-compose up`
- Computer Use Server: `localhost:8081` (MCP endpoint)
- Open WebUI: `localhost:3000` (Chat interface)

**Production:**
- Docker image registry: `open-computer-use:latest` (built from Dockerfile)
- PostgreSQL 17 (Alpine) - Data persistence for Open WebUI
- Multi-user mode: X-Chat-Id header isolation per container
- Single-user mode: One persistent container per session
- Container lifecycle: 24-hour default TTL (cleanup cron)

---

*Stack analysis: 2026-04-12*
