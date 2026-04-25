# Testing Patterns

**Analysis Date:** 2026-04-12

## Test Framework

**Runner:**
- `pytest` (Python testing framework)
- Config: No `pytest.ini` or `setup.cfg` found (uses defaults)
- Async support: `unittest.IsolatedAsyncioTestCase` for async test methods

**Assertion Library:**
- `unittest.TestCase` assertions (`assertEqual`, `assertIn`, `assertNotIn`, `assertGreater`, `assertIsNotNone`, etc.)
- `pytest` fixtures and assertions (`pytest.raises()` for exception testing)

**Run Commands:**
```bash
# Run all tests
python -m pytest

# Run specific test file
python -m pytest tests/orchestrator/test_mcp_tools.py -v

# Run from computer-use-server directory
cd computer-use-server && python -m pytest ../tests/orchestrator/test_mcp_tools.py -v

# Run Docker integration tests
./tests/test-docker-image.sh [image-name]
./tests/test-no-corporate.sh
./tests/test-project-structure.sh
```

## Test File Organization

**Location:**
Tests are co-located with source but in a separate `tests/` directory (not alongside source):
- `tests/` mirrors aspects of source structure
- Security tests: `tests/security/`
- Orchestrator tests: `tests/orchestrator/`
- Patch tests: `tests/patches/`
- Filter tests: `tests/` (flat)

**Naming:**
- Test files: `test_*.py` (e.g., `test_mcp_tools.py`, `test_safe_path_util.py`)
- Test classes: `Test[ComponentName]` (e.g., `TestBashToolOutputTruncation`, `TestValidateChatId`)
- Test methods: `test_[scenario]_[expected_outcome]` (e.g., `test_large_output_is_truncated`, `test_grep_exit1_returns_no_matches`)

**Structure:**
```text
tests/
├── test_filter.py              # Filter outlet/inlet logic
├── test_requirements.py         # CVE dependency version checks
├── orchestrator/
│   ├── test_mcp_tools.py       # Bash, view, str_replace, sub_agent tools
│   ├── test_single_user_mode.py # Chat ID validation + mode handling
│   └── test_view_image.py       # Image viewing functionality
├── security/
│   ├── test_safe_path_util.py  # Path traversal protection
│   ├── test_path_traversal_*.py # Multi-scenario traversal tests
│   └── test_xss_preview.py      # XSS injection protection
└── patches/
    └── test_fix_large_tool_results.py # Tool output truncation logic
```

## Test Structure

**Suite Organization:**
```python
import unittest
from unittest.mock import patch, MagicMock, AsyncMock

class TestComponentFeature(unittest.TestCase):
    """Docstring: what this test suite covers."""
    
    def setUp(self):
        """Optional: set up test fixtures."""
        self.component = Component()
    
    def test_specific_scenario(self):
        """One scenario, one assertion focus."""
        result = self.component.method()
        self.assertEqual(result, expected)
```

**Async Tests:**
```python
class TestAsyncComponent(unittest.IsolatedAsyncioTestCase):
    """Use IsolatedAsyncioTestCase for async functions."""
    
    async def test_async_operation(self):
        """Methods are declared async."""
        result = await async_function()
        self.assertEqual(result, expected)
```

**Patterns:**
- **setUp/tearDown:** Not consistently used; fixtures often created inline in test methods
- **Test isolation:** Each test should be independent; mocking is used to break dependencies
- **Assertion style:** Single assertion per test or grouped assertions for related checks (e.g., checking multiple error conditions)

**Example from `test_filter.py`:**
```python
class TrailingSlashNormalisation(unittest.TestCase):
    """FILE_SERVER_URL may arrive with a trailing slash; URLs must never end up with `//files/`."""

    def test_inlet_does_not_emit_double_slash(self):
        f = _make_filter("http://localhost:8081/")
        body = f.inlet(_active_body(), __metadata__={"chat_id": "abc"})
        self.assertNotIn("//files/", _system_content(body))
```

## Mocking

**Framework:** `unittest.mock` (`MagicMock`, `AsyncMock`, `patch`)

**Patterns:**

1. **Basic Mock:**
```python
from unittest.mock import MagicMock

def _mock_container():
    """Create a mock Docker container."""
    c = MagicMock()
    c.id = "mock-container-id"
    c.name = "owui-chat-test"
    c.status = "running"
    return c
```

2. **Async Mock:**
```python
from unittest.mock import AsyncMock

@patch("mcp_tools._ensure_gitlab_token", new_callable=AsyncMock)
async def test_something(self, mock_token):
    mock_token.return_value = "token"
    result = await bash_tool("echo hello", "test", ctx)
```

3. **Return Value Patching:**
```python
with patch("mcp_tools.execute_bash_streaming",
           return_value={"output": "success", "exit_code": 0, "success": True}):
    result = await bash_tool("echo", "test", ctx)
```

4. **Context-Manager Patching (for multiple scenarios):**
```python
with patch.dict(os.environ, {"SINGLE_USER_MODE": "false"}, clear=False):
    import importlib
    import mcp_tools
    importlib.reload(mcp_tools)  # Re-import to pick up new env
    chat_id, error = mcp_tools._validate_chat_id()
```

**What to Mock:**
- External I/O (file system, Docker socket, HTTP requests)
- Environment variables (use `patch.dict(os.environ, ...)`)
- Async operations (use `AsyncMock()`)
- Long-running operations (timeouts, retries)

**What NOT to Mock:**
- Core business logic (test the actual function, not mocks of it)
- Pure functions with no side effects
- Type checking — let pytest/mypy catch type errors
- Internal helper functions (test through public API)

## Fixtures and Factories

**Test Data:**
Helper functions to create test data (not pytest fixtures):

```python
def _make_filter(file_server_url: str = "http://localhost:8081") -> "computer_link_filter.Filter":
    """Factory for Filter instances."""
    f = computer_link_filter.Filter()
    f.valves.FILE_SERVER_URL = file_server_url
    return f

def _active_body() -> dict:
    """Factory for active body (tool_ids + messages)."""
    return {
        "tool_ids": ["ai_computer_use"],
        "messages": [{"role": "user", "content": "hi"}],
    }
```

**Location:**
- Helper functions: Top of test file or `setUp()` method
- No conftest.py or shared fixtures observed
- Each test file is self-contained with inline factory functions

## Coverage

**Requirements:** No coverage enforced (no pytest-cov config, no CI check)

**View Coverage:**
Not configured in this codebase. To add:
```bash
pytest --cov=computer-use-server --cov-report=html
```

## Test Types

**Unit Tests:**
- Scope: Single function/method in isolation
- Mocking: Heavy use of mocks to break dependencies
- Examples: `test_safe_path_util.py` (path validation), `test_filter.py` (filter logic)

**Integration Tests:**
- Scope: Multiple components interacting (e.g., bash tool + Docker + path sanitization)
- Mocking: Partial (mock Docker, test actual logic)
- Examples: `test_mcp_tools.py` (bash_tool with mocked containers), `test_single_user_mode.py` (validation + tool behavior)

**E2E Tests:**
- Framework: Bash scripts (not pytest)
- Examples: `./tests/test-docker-image.sh`, `./tests/test-no-corporate.sh`
- Scope: Docker image package availability, CLI tool presence, project structure

## Common Patterns

**Async Testing:**
```python
class TestAsyncBashTool(unittest.IsolatedAsyncioTestCase):
    """Use IsolatedAsyncioTestCase to run async tests."""

    @patch("mcp_tools._ensure_gitlab_token", new_callable=AsyncMock)
    @patch("mcp_tools._get_or_create_container", return_value=_mock_container())
    async def test_large_output_is_truncated(self, mock_container, mock_token):
        """Async test with multiple mocked dependencies."""
        from mcp_tools import bash_tool
        current_chat_id.set("test-chat")
        ctx = MagicMock()
        ctx.report_progress = AsyncMock()

        big_output = "x" * 60_000
        with patch("mcp_tools.execute_bash_streaming",
                   return_value={"output": big_output, "exit_code": 0, "success": True}):
            result = await bash_tool("cat big_file", "read", ctx)

        self.assertIn("truncated", result.lower())
        self.assertLessEqual(len(result), 32_000)
```

**Error/Exception Testing:**
```python
def test_traversal_dot_dot(self, tmp_path):
    """Use pytest.raises to test exception paths."""
    base = tmp_path / "data"
    base.mkdir()
    with pytest.raises(HTTPException) as exc_info:
        safe_path(base, "..", "..", "etc", "passwd")
    assert exc_info.value.status_code == 403
```

**Environment Variable Testing:**
```python
def test_multi_user_mode_no_chat_id_returns_error(self):
    """Use patch.dict to mock os.environ for mode testing."""
    with patch.dict(os.environ, {"SINGLE_USER_MODE": "false"}, clear=False):
        import importlib
        import mcp_tools
        importlib.reload(mcp_tools)  # Re-import to pick up new env
        current_chat_id.set("default")
        chat_id, error = mcp_tools._validate_chat_id()
        self.assertIsNotNone(error)
        self.assertIn("required", error.lower())
```

**Parametric/Multiple Scenarios:**
Test classes organize related scenarios (not pytest parametrize):
```python
class TestSafePath(unittest.TestCase):
    """Group all safe_path() tests."""

    def test_normal_path(self, tmp_path):
        """Normal case."""
        result = safe_path(tmp_path / "data", "file.txt")
        self.assertEqual(result, (tmp_path / "data" / "file.txt").resolve())

    def test_traversal_dot_dot(self, tmp_path):
        """Traversal attempt."""
        with pytest.raises(HTTPException):
            safe_path(tmp_path / "data", "..", "etc", "passwd")

    def test_symlink_escape(self, tmp_path):
        """Symlink escape."""
        with pytest.raises(HTTPException):
            safe_path(tmp_path / "data", "link", "key.txt")
```

## Test Execution

**Before running tests:**
1. Add computer-use-server to path (if testing orchestrator):
   ```python
   sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'computer-use-server'))
   ```

2. Import the module under test after path setup:
   ```python
   import computer_link_filter
   from mcp_tools import bash_tool
   ```

**Full test suite:**
```bash
# All pytest tests
python -m pytest tests/ -v

# All tests with coverage
python -m pytest tests/ --cov=computer-use-server --cov=openwebui

# Specific test file
python -m pytest tests/orchestrator/test_mcp_tools.py -v

# Specific test class
python -m pytest tests/orchestrator/test_mcp_tools.py::TestBashToolOutputTruncation -v

# Specific test method
python -m pytest tests/orchestrator/test_mcp_tools.py::TestBashToolOutputTruncation::test_large_output_is_truncated -v
```

## Security-Focused Tests

Special emphasis on security testing (path traversal, XSS, CVE versions):

**Path Traversal (`test_safe_path_util.py`):**
- `test_traversal_dot_dot`: `../../etc/passwd`
- `test_traversal_in_segment`: `../../etc/passwd` in single segment
- `test_absolute_path_injection`: `/etc/passwd`
- `test_string_prefix_false_positive`: `/data` should NOT match `/data-evil`
- `test_symlink_escape`: Symlinks pointing outside base directory

**Dependency Version Guards (`test_requirements.py`):**
- `test_pillow_at_least_12_1_1`: PSD out-of-bounds write CVE
- `test_urllib3_at_least_2_6_3`: Decompression bomb + redirect bypass
- `test_cryptography_at_least_46_0_6`: SECT curves subgroup attack
- `test_pyjwt_at_least_2_12_1`: Critical header extensions bypass

---

*Testing analysis: 2026-04-12*
