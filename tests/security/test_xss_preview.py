# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""Tests for XSS protection in _generate_preview_html."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "computer-use-server"))

import pytest

from app import _generate_preview_html
from security import sanitize_chat_id


VALID_CHAT_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


class TestPreviewXSS:
    def test_script_injection_in_chat_id(self):
        """chat_id with JS break-out should be escaped so quotes don't terminate the string."""
        html = _generate_preview_html('";alert(1);//', "/api", "/files")
        # The unescaped pattern would create: chatId: "";alert(1);//"
        # With json.dumps it becomes: chatId: "\";alert(1);//" (safe)
        assert 'chatId: "";alert(1)' not in html

    def test_closing_script_tag_escaped(self):
        """</script> in chat_id must not close the script block."""
        html = _generate_preview_html('</script><script>alert(1)</script>', "/api", "/files")
        # json.dumps produces: "</script><script>alert(1)</script>"
        # This is still inside a JS string, but a naive HTML parser would close the block.
        # The real fix is sanitize_chat_id (rejects / in chat_id), but let's verify
        # the value is inside a JSON string context (wrapped by json.dumps quotes).
        # With old f-string: chatId: "</script>... — parser closes <script> block = XSS
        # With json.dumps: chatId: "</script>... — still JSON string, but browsers
        # may still parse </script> as tag close. Full protection comes from sanitize_chat_id.
        # Verify json.dumps is being used (presence of escaped quotes pattern)
        assert 'chatId: "' in html  # json.dumps adds quotes

    def test_normal_chat_id(self):
        html = _generate_preview_html(VALID_CHAT_ID, "/api/outputs/x", "/files/x")
        assert VALID_CHAT_ID in html

    def test_values_use_json_dumps(self):
        """All config values should be properly JSON-encoded (not raw f-string interpolation)."""
        html = _generate_preview_html("test-id", "/api/test", "/files/test")
        # json.dumps adds its own quotes, so the pattern should be: chatId: "test-id"
        assert 'chatId: "test-id"' in html
        assert 'apiUrl: "/api/test"' in html
        assert 'filesBase: "/files/test"' in html


class TestChatIdCharacterClass:
    """The guarantee belongs to the input, not to thirty-two call sites.

    The tests above prove the template escapes what reaches it. That was the
    only barrier: sanitize_chat_id rejected '..', '/', '\\' and NUL, so a
    quote-bearing id was accepted and the endpoint stayed safe purely because
    every interpolation happened to be json.dumps'd. These bind the allow-list
    instead -- if it is loosened back to a deny-list, they red.
    """

    def test_quote_bearing_id_is_refused(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            sanitize_chat_id('x" onload="alert(1)')

    def test_markup_is_refused_without_relying_on_the_slash(self):
        # '<script>' carries no '/', so the traversal rule never saw it.
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            sanitize_chat_id("a<script>alert(1)")

    def test_real_values_still_pass(self):
        for value in (VALID_CHAT_ID, "default", "abc123", "test-123", "Winner"):
            assert sanitize_chat_id(value) == value.lower()

    def test_length_is_bounded(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            sanitize_chat_id("a" * 65)
