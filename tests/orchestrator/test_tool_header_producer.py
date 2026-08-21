# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""The in-tree header producer is disciplined, and that must not regress.

Six findings concern values arriving as request headers and reaching sinks
unvalidated (#601, #603, #605, #607, #609). Tracing the sender narrows who can
reach them, and the answer is worth locking rather than re-deriving:

  - X-Chat-Id is built from Open WebUI's own metadata (`__metadata__` chat
    UUID), not from user input
  - X-User-Name is URL-encoded before it goes on the wire
  - X-User-Email and the chat id are not encoded, which is why the receiver
    still has to validate them

That last point is why this file does not claim the sender makes the receiver
safe. app.py:163-173 documents calling /mcp directly with curl, so any holder
of the MCP key can send whatever they like. The producer's discipline reduces
the accidental case, not the deliberate one.

What is pinned here is the discipline itself: if X-User-Name stops being
encoded, or the chat id starts coming from somewhere other than metadata, the
accidental case reopens and nothing else would notice.
"""

import ast
import unittest
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE = ROOT / "openwebui" / "tools" / "computer_use_tools.py"


def _build_headers(api_key="", **kwargs):
    """Exec the real build_headers against a stub self."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    cls = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "_MCPClient"
    )
    fn = next(
        n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "build_headers"
    )
    ns = {"urllib": urllib}
    exec(compile(ast.Module([fn], []), "<t>", "exec"), ns)

    class _Stub:
        pass

    stub = _Stub()
    stub.api_key = api_key
    return ns["build_headers"](stub, **kwargs)


class ToolHeaderProducer(unittest.TestCase):
    def test_user_name_is_url_encoded(self):
        """A newline in a display name must not reach the wire raw."""
        headers = _build_headers(chat_id="c", user_name="a\r\nX-Injected: 1")
        self.assertNotIn("\r", headers["X-User-Name"])
        self.assertNotIn("\n", headers["X-User-Name"])
        self.assertIn("%0", headers["X-User-Name"].upper())

    def test_a_plain_user_name_round_trips(self):
        """Encoding that mangled ordinary names would be worse than none."""
        headers = _build_headers(chat_id="c", user_name="First Last")
        self.assertEqual(urllib.parse.unquote(headers["X-User-Name"]), "First Last")

    def test_absent_values_produce_no_header(self):
        """An empty email must not become an empty header."""
        headers = _build_headers(chat_id="c")
        self.assertNotIn("X-User-Email", headers)
        self.assertNotIn("X-User-Name", headers)

    def test_the_api_key_becomes_a_bearer_only_when_set(self):
        self.assertNotIn("Authorization", _build_headers(chat_id="c"))
        self.assertEqual(
            _build_headers(api_key="k", chat_id="c")["Authorization"], "Bearer k"
        )

    def test_the_chat_id_comes_from_metadata_not_user_input(self):
        """Asserted against the source: the value is a chat UUID, not typed text.

        This is the sentence that narrows #601 and #609 from "anyone" to "any
        holder of the MCP key". If the source stops reading __metadata__, that
        reasoning is stale and this fails.
        """
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn('__metadata__.get("chat_id")', source)

    def test_the_email_and_chat_id_are_NOT_encoded(self):
        """Stated so the sender is not mistaken for a validation layer.

        The receiver must still check: /mcp is documented as callable by curl
        (app.py:163-173), so a disciplined producer bounds the accidental case
        and not the deliberate one.
        """
        headers = _build_headers(chat_id="a b", user_email="x y@z")
        self.assertEqual(headers["X-Chat-Id"], "a b")
        self.assertEqual(headers["X-User-Email"], "x y@z")


if __name__ == "__main__":
    unittest.main()
