# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""A request-supplied value cannot add a header to an upstream call.

x-user-email arrives from the request unvalidated (mcp_tools:1322) and is
interpolated into ANTHROPIC_CUSTOM_HEADERS, a header LIST that Claude Code
parses inside the guest (#603).

Shell injection was already closed on both paths and this does not change
that: the sub-agent path shlex.quote's the assignment, and the entrypoint
exports the variable quoted. Both were checked rather than assumed. What was
open is one layer up -- a separator inside the VALUE.

header_safe strips rather than rejects, deliberately. The header is diagnostic
tagging; failing a whole session because a display name carried a newline
would be a worse outcome than tagging it with the newline gone. The tests
below say so, so the choice is visible rather than looking like a half
measure.

The consumer's splitting rule is not defined in this repository, so the fix
does not depend on knowing it: CR, LF and NUL cannot legitimately appear in a
header value under any parser.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "computer-use-server"))

from security import header_safe  # noqa: E402


class HeaderSafe(unittest.TestCase):
    def test_an_ordinary_email_is_untouched(self):
        """The bound must not damage the values it exists to carry."""
        for value in ("user@example.com", "First Last", "ünïcode@example.com"):
            with self.subTest(value=value):
                self.assertEqual(header_safe(value), value)

    def test_crlf_cannot_survive(self):
        """The injection shape: a second header appended to the value."""
        result = header_safe("a@b.c\r\nx-api-key: stolen")
        self.assertNotIn("\r", result)
        self.assertNotIn("\n", result)

    def test_a_bare_newline_cannot_survive(self):
        self.assertNotIn("\n", header_safe("a@b.c\nx-forwarded-for: 1.2.3.4"))

    def test_nul_cannot_survive(self):
        """A NUL truncates the value for a C-string consumer."""
        self.assertNotIn("\x00", header_safe("a@b.c\x00ignored"))

    def test_it_strips_rather_than_rejects(self):
        """Stated as a test so the choice is a decision, not an oversight.

        The remaining text is kept: a diagnostic tagging header should degrade
        to a slightly wrong tag rather than fail the session.
        """
        self.assertEqual(header_safe("a@b.c\r\nx: y"), "a@b.cx: y")

    def test_an_empty_value_stays_empty(self):
        self.assertEqual(header_safe(""), "")

    def test_both_interpolation_sites_use_it(self):
        """The function is worthless if a caller forgets it.

        Asserted against the source: both places that build
        ANTHROPIC_CUSTOM_HEADERS must pass the value through header_safe.
        """
        for name in ("docker_manager.py", "mcp_tools.py"):
            source = (ROOT / "computer-use-server" / name).read_text(encoding="utf-8")
            for line in source.splitlines():
                if "x-openwebui-user-email:" in line and "f\"" in line or "x-openwebui-user-email:" in line and "f'" in line:
                    self.assertIn(
                        "header_safe",
                        line,
                        f"{name} interpolates the email without header_safe",
                    )


if __name__ == "__main__":
    unittest.main()
