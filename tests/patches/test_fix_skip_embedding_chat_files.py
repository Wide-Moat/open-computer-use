# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""Tests for fix_skip_embedding_chat_files.py against v0.9.1 and v0.9.2 retrieval.py fixtures."""
import ast
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PATCH_DIR = REPO_ROOT / "openwebui" / "patches"
sys.path.insert(0, str(Path(__file__).parent))
from conftest import load_retrieval_v091, load_retrieval_v092  # noqa: E402


def _run_patch(patch_name: str, target_file: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "_PATCH_TARGET_OVERRIDE": str(target_file)}
    return subprocess.run(
        [sys.executable, str(PATCH_DIR / f"{patch_name}.py")],
        env=env, capture_output=True, text=True, timeout=30,
    )


class TestFixSkipEmbeddingChatFiles(unittest.TestCase):
    PATCH_NAME = "fix_skip_embedding_chat_files"
    NEW_MARKER = "FIX_SKIP_EMBEDDING_CHAT_FILES"
    PRIMARY_ANCHOR = "                collection_name = f'file-{file.id}'"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.target = Path(self.tmp) / "retrieval.py"
        self.target.write_text(load_retrieval_v091(), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_fresh_apply(self):
        r = _run_patch(self.PATCH_NAME, self.target)
        self.assertEqual(r.returncode, 0, f"stderr={r.stderr}")
        self.assertIn(f"PATCHED: {self.PATCH_NAME}", r.stdout)
        content = self.target.read_text()
        self.assertIn(self.NEW_MARKER, content)
        ast.parse(content)

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
        self.assertIn(self.PRIMARY_ANCHOR, content)
        self.target.write_text(
            content.replace(self.PRIMARY_ANCHOR, "                # ANCHOR_REMOVED_FOR_TEST")
        )
        r = _run_patch(self.PATCH_NAME, self.target)
        self.assertEqual(r.returncode, 1, f"stdout={r.stdout} stderr={r.stderr}")
        self.assertIn("ERROR:", r.stderr)
        self.assertIn(self.PATCH_NAME, r.stderr)


class TestFixSkipEmbeddingChatFilesV092(unittest.TestCase):
    """3-state coverage against real v0.9.2 retrieval.py fixture."""

    PATCH_NAME = "fix_skip_embedding_chat_files"
    NEW_MARKER = "FIX_SKIP_EMBEDDING_CHAT_FILES"
    PRIMARY_ANCHOR = "                collection_name = f'file-{file.id}'"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.target = Path(self.tmp) / "retrieval.py"
        self.target.write_text(load_retrieval_v092(), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_fresh_apply_v092(self):
        r = _run_patch(self.PATCH_NAME, self.target)
        self.assertEqual(r.returncode, 0, f"stderr={r.stderr}")
        self.assertIn(f"PATCHED: {self.PATCH_NAME}", r.stdout)
        content = self.target.read_text()
        self.assertIn(self.NEW_MARKER, content)
        ast.parse(content)

    def test_idempotent_rerun_v092(self):
        r1 = _run_patch(self.PATCH_NAME, self.target)
        self.assertEqual(r1.returncode, 0)
        after_first = self.target.read_text()
        r2 = _run_patch(self.PATCH_NAME, self.target)
        self.assertEqual(r2.returncode, 0)
        self.assertIn("ALREADY PATCHED", r2.stdout)
        self.assertEqual(after_first, self.target.read_text())

    def test_broken_fixture_fails_loud_v092(self):
        content = self.target.read_text()
        self.assertIn(self.PRIMARY_ANCHOR, content)
        self.target.write_text(
            content.replace(self.PRIMARY_ANCHOR, "                # ANCHOR_REMOVED_FOR_TEST")
        )
        r = _run_patch(self.PATCH_NAME, self.target)
        self.assertEqual(r.returncode, 1, f"stdout={r.stdout} stderr={r.stderr}")
        self.assertIn("ERROR:", r.stderr)
        self.assertIn(self.PATCH_NAME, r.stderr)

    def test_patched_call_uses_await_v092(self):
        # Regression guard for issue #96: Files.update_file_data_by_id was
        # sync in v0.8.x, async since v0.9.x. process_file() is async, so the
        # patched call must be awaited — otherwise the coroutine is dropped,
        # the DB status stays 'pending', and the frontend spinner hangs.
        r = _run_patch(self.PATCH_NAME, self.target)
        self.assertEqual(r.returncode, 0, f"stderr={r.stderr}")
        content = self.target.read_text()
        self.assertIn("await Files.update_file_data_by_id(", content)
        self.assertNotRegex(
            content,
            r"(?<!await )Files\.update_file_data_by_id\(",
            "Found a non-awaited Files.update_file_data_by_id call; "
            "this regresses issue #96.",
        )

    def test_patched_kb_fallback_does_not_block_event_loop_v092(self):
        # Storage.get_file and Loader.load are sync; calling them directly in
        # the async process_file handler would block the OWUI event loop for
        # the entire read/parse (minutes for large PDFs). Upstream OWUI
        # offloads via asyncio.to_thread / Loader.aload; the KB fallback
        # injected by this patch must do the same.
        r = _run_patch(self.PATCH_NAME, self.target)
        self.assertEqual(r.returncode, 0, f"stderr={r.stderr}")
        content = self.target.read_text()
        # Locate the inserted KB fallback block by its marker comment.
        marker = "KB fallback: extracting content from"
        self.assertIn(marker, content)
        block_start = content.index(marker)
        # Bound the block to the next non-indented line to scope assertions.
        block = content[block_start:block_start + 4000]
        self.assertIn("await asyncio.to_thread(Storage.get_file", block)
        self.assertIn("await _fb_loader.aload(", block)
        self.assertNotRegex(
            block,
            r"(?<!to_thread\()Storage\.get_file\(",
            "KB fallback calls Storage.get_file without asyncio.to_thread; "
            "this blocks the OWUI event loop on storage I/O.",
        )
        self.assertNotRegex(
            block,
            r"(?<!await )_fb_loader\.load\(",
            "KB fallback calls _fb_loader.load() synchronously; "
            "use aload() to keep the event loop responsive.",
        )


if __name__ == "__main__":
    unittest.main()
