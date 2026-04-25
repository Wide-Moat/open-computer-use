# Coding Conventions

**Analysis Date:** 2026-04-12

## Naming Patterns

**Files:**
- Python modules: `snake_case.py` (e.g., `docker_manager.py`, `mcp_tools.py`, `computer_link_filter.py`)
- Test files: `test_*.py` (e.g., `test_mcp_tools.py`, `test_safe_path_util.py`)
- Bash scripts: lowercase with hyphens (e.g., `test-docker-image.sh`, `test-no-corporate.sh`)

**Functions:**
- Python: `snake_case` for all functions (e.g., `safe_path()`, `sanitize_chat_id()`, `_validate_chat_id()`)
- Private/internal functions: `_leading_underscore()` prefix (e.g., `_fetch_gitlab_token()`, `_get_or_create_container()`)
- Async functions: same naming as sync (e.g., `async def bash_tool()`, `async def view()`)

**Variables:**
- Python: `snake_case` (e.g., `DOCKER_SOCKET`, `current_chat_id`, `form_data`)
- Constants: `UPPER_CASE` (e.g., `COMMAND_TIMEOUT`, `FILE_SERVER_URL`, `SINGLE_USER_MODE`)
- Private module variables: `_leading_underscore` prefix (e.g., `_TOOL_RESULT_MAX_CHARS`)

**Types:**
- Python: Type hints on function signatures using `from typing import` (e.g., `Optional[str]`, `Dict[str, Any]`, `List[Path]`, `tuple[str, str | None]`)
- Pydantic models: `PascalCase` for classes (e.g., `Filter`, `Valves`, `MCPRequest`)
- Type unions: `|` notation for newer Python (e.g., `str | None` instead of `Optional[str]`)

## Code Style

**Formatting:**
- No explicit linter configuration found (`.eslintrc`, `.prettierrc`, `black` config absent)
- Follows PEP 8 conventions by convention (4-space indentation, line length not strictly enforced)
- Import ordering: stdlib first, then third-party, then local imports

**Linting:**
- No automated linting enforced in CI (no `.eslintrc`, `black`, `flake8`, or `ruff` config)
- SPDX license headers enforced by manual review

**File Headers:**
All source files MUST start with SPDX and copyright comments:
```python
# SPDX-License-Identifier: BUSL-1.1
# Copyright (c) 2025 Open Computer Use Contributors
```

Exception: MIT files in `skills/public/describe-image/` or `skills/public/sub-agent/`:
```python
# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Open Computer Use Contributors
```

## Import Organization

**Order:**
1. Standard library imports (`os`, `sys`, `asyncio`, `pathlib`, `typing`, etc.)
2. Third-party imports (`fastapi`, `pydantic`, `docker`, `aiohttp`, etc.)
3. Relative local imports (`from . import`, `from ..module import`)
4. Explicit path manipulation if needed (`sys.path.insert(0, ...)` for test discovery)

**Path Aliases:**
Test files use explicit path insertion for discovery:
```python
sys.path.insert(0, str(ROOT / "computer-use-server"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "computer-use-server"))
```

No barrel files or path aliases observed in main code.

## Error Handling

**Patterns:**
- Explicit exception catching: `except SpecificException as e:` (not bare `except:`)
- FastAPI integration: Raise `HTTPException(status_code=code, detail="message")` for API errors
- Print to stdout for logging: `print("[TAG] message")` (e.g., `print("[WARN]")`, `print("[GITLAB]")`, `print("[SUB-AGENT]")`)
- Async cancellation: Explicitly catch `asyncio.CancelledError` and `asyncio.TimeoutError`

**Example from `security.py`:**
```python
if resolved_str != base_str and not resolved_str.startswith(base_str + os.sep):
    raise HTTPException(
        status_code=403, detail="Access denied: path traversal detected"
    )
```

**Example from `mcp_tools.py`:**
```python
try:
    result = await asyncio.wait_for(execute_bash_streaming(...), timeout=COMMAND_TIMEOUT)
except asyncio.TimeoutError:
    return f"Command timed out after {COMMAND_TIMEOUT}s"
except asyncio.CancelledError:
    # Handle cancellation
    pass
```

## Logging

**Framework:** `print()` to stdout with prefixed tags

**Patterns:**
- Info: `print("[TAG] message")` where TAG identifies the subsystem
- Debug: `print(f"[DEBUG] {detail}")` when DEBUG_LOGGING=true
- Warnings: `print("[WARN] message")`
- Subsystem tags observed: `[GITLAB]`, `[SUB-AGENT]`, `[WARN]`, `[SUB-AGENT-PROGRESS]`, `[DEBUG]`

**Example from `docker_manager.py`:**
```python
if not mcp_tokens_api_key:
    print("[GITLAB] MCP_TOKENS_API_KEY not configured, skipping token fetch")
    return None
```

## Comments

**When to Comment:**
- Docstrings: Required for all module-level and function definitions
- Inline comments: Used sparingly for non-obvious logic or architectural notes
- Section markers: Used to separate logical blocks (e.g., `# =============================================================================`)

**DocString Format:**
Module-level docstring template:
```python
"""
[One-line summary]

[Detailed description of what the module does]

Sections:
- [What it does]
- [How it works]
"""
```

Function docstring template:
```python
def function_name(arg: Type) -> ReturnType:
    """
    [One-line summary — action verb form]

    [Detailed explanation if needed]

    Args:
        arg: [What this argument represents]

    Returns:
        [What is returned]
    """
```

**Examples:**
- `docker_manager.py`: Full module docstring describing Docker lifecycle management
- `mcp_tools.py`: Detailed docstring explaining HTTP headers, environment variables, and LiteLLM integration
- `security.py`: Docstrings explaining CodeQL-recognized sanitization patterns

## Function Design

**Size:** Typically 10-50 lines. Longer functions (100+ lines) are common for complex async operations like sub-agent execution.

**Parameters:**
- Type hints required for all parameters
- Optional parameters use `Optional[Type]` or `Type | None`
- Default arguments use constants or None (e.g., `timeout=COMMAND_TIMEOUT`)

**Return Values:**
- Type hints required for all return values
- Async functions return unwrapped types (async keyword makes return type implicit)
- Error returns: Either raise exceptions or return error strings (inconsistent between modules)

**Example from `mcp_tools.py`:**
```python
async def bash_tool(command: str, description: str, ctx: Context) -> str:
    """Execute bash command in container with output truncation."""
    # Function body
    return result  # String (success or error message)
```

## Module Design

**Exports:**
- No explicit `__all__` declarations observed
- Public functions: Not prefixed (e.g., `bash_tool`, `view`, `str_replace`)
- Private functions: `_leading_underscore` prefix (e.g., `_validate_chat_id`, `_get_or_create_container`)

**Barrel Files:**
Not used in this codebase. Each module imports its dependencies explicitly.

## Environment Configuration

**Pattern:**
- `os.getenv("VAR_NAME", "default_value")` for optional variables
- `os.getenv("VAR_NAME")` for required variables (may return None, validated at function entry)
- No `.env` file validation enforced (depends on deployment)

**Examples from `docker_manager.py`:**
```python
DOCKER_SOCKET = os.getenv("DOCKER_SOCKET", "unix:///var/run/docker.sock")
COMMAND_TIMEOUT = int(os.getenv("COMMAND_TIMEOUT", "120"))
FILE_SERVER_URL = os.getenv("FILE_SERVER_URL", "http://computer-use-server:8081")
```

## Language

**Requirement:** All code, comments, commit messages, documentation, and visible text MUST be in **English only**. No exceptions.

---

*Convention analysis: 2026-04-12*
