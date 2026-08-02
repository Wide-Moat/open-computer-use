# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""Tests for fix_tool_loop_errors.py against the v0.11.0 middleware.py fixture.

3-state coverage: fresh apply / idempotent re-run / broken fixture fails loud.
The patch anchors target one upstream shape (openwebui/Dockerfile
ARG OPENWEBUI_VERSION), so the fixture is pinned to that base.
"""
import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PATCH_DIR = REPO_ROOT / "openwebui" / "patches"
sys.path.insert(0, str(Path(__file__).parent))
from conftest import load_middleware_v0110  # noqa: E402


def _error_block(content: str, marker: str) -> str:
    """Slice one injected error-handling block, from `marker` to its `break`.

    Every block this patch injects bails out of the tool loop, so the first
    `break` line after the marker terminates it. Bounding on that rather than
    a character count keeps the window tied to the block even if the patch
    grows or shrinks the code it injects.
    """
    start = content.index(marker)
    end = re.search(r"\n[ \t]+break\n", content[start:])
    assert end is not None, f"no terminating break after {marker!r}"
    return content[start:start + end.end()]


def _run_patch(patch_name: str, target_file: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "_PATCH_TARGET_OVERRIDE": str(target_file)}
    return subprocess.run(
        [sys.executable, str(PATCH_DIR / f"{patch_name}.py")],
        env=env, capture_output=True, text=True, timeout=30,
    )


class TestFixToolLoopErrorsV0110(unittest.TestCase):
    """3-state coverage against the real v0.11.0 middleware.py fixture."""

    PATCH_NAME = "fix_tool_loop_errors"
    NEW_MARKER = "FIX_TOOL_LOOP_ERRORS"
    # Distinctive single line from the SEARCH_ITER anchor
    PRIMARY_ANCHOR = (
        "                    max_tool_call_iterations is None"
        " or tool_call_iterations < max_tool_call_iterations"
    )

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.target = Path(self.tmp) / "middleware.py"
        self.target.write_text(load_middleware_v0110(), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_fresh_apply(self):
        r = _run_patch(self.PATCH_NAME, self.target)
        self.assertEqual(r.returncode, 0, f"stderr={r.stderr}\nstdout={r.stdout}")
        self.assertIn(f"PATCHED: {self.PATCH_NAME}", r.stdout)
        content = self.target.read_text()
        self.assertIn(self.NEW_MARKER, content)
        self.assertIn("TOOL_LOOP_ERRORS_UNIFIED", content)
        ast.parse(content)

    def test_injected_code_calls_no_removed_helpers(self):
        # Open WebUI 0.10.0 deleted serialize_output(); the error paths this
        # patch injects sit inside broad `except` blocks, so a NameError there
        # would be swallowed and the user-facing error banner lost.
        r = _run_patch(self.PATCH_NAME, self.target)
        self.assertEqual(r.returncode, 0, f"stderr={r.stderr}")
        content = self.target.read_text()
        self.assertNotIn(
            "serialize_output",
            content,
            "patched middleware calls serialize_output(), removed upstream in 0.10.0",
        )

    def test_each_error_path_emits_exactly_one_banner(self):
        # 0.11.0 added emit_message_error(), which upstream calls from the
        # tool-loop and code-interpreter `except` blocks. The patch replaces
        # those blocks and delegates the banner to that helper. Emitting
        # chat:message:error directly as well would show the user two banners
        # for one failure; emitting neither would lose the error entirely.
        # Both are silent in production — the emits sit inside `except` blocks
        # nothing exercises until a model call fails mid-tool-loop.
        r = _run_patch(self.PATCH_NAME, self.target)
        self.assertEqual(r.returncode, 0, f"stderr={r.stderr}")
        content = self.target.read_text()

        for marker, label in (
            ("TOOL_LOOP_ERRORS_UNIFIED: restore clean output + classify", "tool-loop except"),
            ("TOOL_LOOP_ERRORS_UNIFIED: handle non-streaming error", "non-streaming branch"),
        ):
            self.assertIn(marker, content, f"{label} block missing from patched output")
            block = _error_block(content, marker)
            self.assertEqual(
                block.count("await emit_message_error("), 1,
                f"{label} must emit exactly one error banner",
            )
            self.assertNotIn(
                "'type': 'chat:message:error'", block,
                f"{label} emits chat:message:error directly as well as via the "
                "helper — the user would see two banners for one failure",
            )

        # The code-interpreter except is a separate injection site.
        self.assertIn(
            "CODE_INTERP_ERROR", content,
            "code-interpreter except block missing from patched output",
        )
        ci = _error_block(content, "CODE_INTERP_ERROR")
        self.assertEqual(ci.count("await emit_message_error("), 1)
        self.assertNotIn("'type': 'chat:message:error'", ci)

    def test_idempotent_rerun(self):
        r1 = _run_patch(self.PATCH_NAME, self.target)
        self.assertEqual(r1.returncode, 0)
        after_first = self.target.read_text()
        r2 = _run_patch(self.PATCH_NAME, self.target)
        self.assertEqual(r2.returncode, 0)
        self.assertIn("ALREADY PATCHED", r2.stdout)
        self.assertEqual(after_first, self.target.read_text())

    def test_broken_fixture_fails_loud(self):
        content = self.target.read_text()
        self.assertIn(self.PRIMARY_ANCHOR, content, "test fixture assumption wrong")
        self.target.write_text(
            content.replace(self.PRIMARY_ANCHOR, "                    or False")
        )
        r = _run_patch(self.PATCH_NAME, self.target)
        self.assertEqual(r.returncode, 1, f"expected exit 1; stdout={r.stdout} stderr={r.stderr}")
        self.assertIn("ERROR:", r.stderr)
        self.assertIn(self.PATCH_NAME, r.stderr)


if __name__ == "__main__":
    unittest.main()
