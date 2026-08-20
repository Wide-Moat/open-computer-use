# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""security.py is a boundary, and nothing exercised it.

sanitize_chat_id and safe_path are the traversal and injection guards every
per-chat path goes through. Measured before writing this: zero test files
imported the module, while docker_manager had six and mcp_tools seven. A guard
with no test is a guard whose next edit is unreviewed by anything that runs.

The payloads below are not invented. The module's own docstring records the
strings the allow-list was written against -- a quote-bearing id the previous
deny-list accepted, and the prefix collision os.sep was added to prevent. Those
are the cases most worth pinning, because they are the ones somebody already
had to think about.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "computer-use-server"))

from fastapi import HTTPException  # noqa: E402

from security import safe_path, sanitize_chat_id  # noqa: E402


class SanitizeChatId(unittest.TestCase):
    def test_accepts_the_shapes_real_deployments_use(self):
        """The allow-list must not reject ids the product actually issues."""
        for value in ("default", "abc123", "test-123", "a" * 64,
                      "550e8400-e29b-41d4-a716-446655440000"):
            with self.subTest(value=value):
                self.assertEqual(sanitize_chat_id(value), value)

    def test_normalises_case_and_surrounding_space(self):
        self.assertEqual(sanitize_chat_id("  ABC-123  "), "abc-123")

    def test_rejects_the_quote_payload_the_old_rule_accepted(self):
        """From the module's own docstring: the deny-list let this through.

        chat_id reaches an HTML template. It is json.dumps'd at every
        interpolation today, so this was not exploitable -- but that was a
        property of thirty-two call sites rather than of the input. The
        allow-list moves the guarantee to the data, and this pins it there.
        """
        with self.assertRaises(HTTPException) as caught:
            sanitize_chat_id('x" onload="alert(1)')
        self.assertEqual(caught.exception.status_code, 400)

    def test_rejects_traversal_and_separators(self):
        for value in ("..", "../etc", "a/b", "a\\b", "a\x00b"):
            with self.subTest(value=value):
                with self.assertRaises(HTTPException):
                    sanitize_chat_id(value)

    def test_rejects_empty_and_overlong(self):
        for value in ("", "   ", "a" * 65):
            with self.subTest(value=value):
                with self.assertRaises(HTTPException):
                    sanitize_chat_id(value)


class SafePath(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="ocu-safepath-"))

    def test_joins_segments_inside_the_base(self):
        result = safe_path(self.base, "chat", "uploads", "file.txt")
        self.assertTrue(str(result).startswith(str(self.base.resolve())))

    def test_refuses_traversal_out_of_the_base(self):
        with self.assertRaises(HTTPException) as caught:
            safe_path(self.base, "..", "..", "etc", "passwd")
        self.assertEqual(caught.exception.status_code, 403)

    def test_refuses_an_absolute_segment(self):
        """os.path.join discards everything before an absolute segment."""
        with self.assertRaises(HTTPException):
            safe_path(self.base, "/etc/passwd")

    def test_refuses_a_symlink_escaping_the_base(self):
        """realpath is what makes this catchable; a lexical check would not."""
        outside = Path(tempfile.mkdtemp(prefix="ocu-outside-"))
        (outside / "secret.txt").write_text("x", encoding="utf-8")
        link = self.base / "escape"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable on this platform")
        with self.assertRaises(HTTPException):
            safe_path(self.base, "escape", "secret.txt")

    def test_refuses_a_sibling_sharing_the_base_prefix(self):
        """The os.sep suffix exists for this: /data must not match /data-evil.

        Without it a base of /data would accept /data-evil/... on a plain
        startswith. Named in the module comment, unexercised until now.
        """
        sibling = Path(str(self.base) + "-evil")
        sibling.mkdir(exist_ok=True)
        with self.assertRaises(HTTPException):
            safe_path(self.base, "..", sibling.name, "loot.txt")

    def test_the_base_itself_is_allowed(self):
        """Equality is the one non-prefix case the containment check permits."""
        self.assertEqual(safe_path(self.base), Path(os.path.realpath(self.base)))


if __name__ == "__main__":
    unittest.main()
