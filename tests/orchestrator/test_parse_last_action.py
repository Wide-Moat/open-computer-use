# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""parse_last_action reads an agent-written log, and nothing tested it.

It parses the Claude session JSONL to show what the agent is doing now. The
input is written by the agent, so every line is untrusted in the ordinary
sense: malformed JSON, missing keys, wrong types and enormous strings all
arrive as a matter of course rather than as an attack.

Four properties hold and none was covered.

The LAST action wins, whether it is text or a tool call. The docstring says
this is to avoid showing stale text while a long tool runs, so a test that
only fed text in order would pass while the ordering broke.

Malformed input degrades to None. The except swallows JSONDecodeError,
KeyError and TypeError, which is correct for a status display -- a broken log
line should not take down the endpoint -- but a broad except is also how a
parser stops parsing, so the degrade is asserted.

Text is bounded to 80 characters and newlines are flattened. Both matter for
a single-line status field, and both are one slice away from not happening.
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "computer-use-server"))

import mcp_tools  # noqa: E402


def _assistant(*items) -> str:
    return json.dumps({"type": "assistant", "message": {"content": list(items)}})


def _text(value: str) -> dict:
    return {"type": "text", "text": value}


def _tool(name: str, **inp) -> dict:
    return {"type": "tool_use", "name": name, "input": inp}


class ParseLastAction(unittest.TestCase):
    def test_a_tool_after_text_wins(self):
        """The ordering the docstring exists for: no stale text mid-tool."""
        result = mcp_tools.parse_last_action(
            [_assistant(_text("thinking")), _assistant(_tool("bash_tool", description="ls"))]
        )
        self.assertIn("ls", result)
        self.assertNotIn("thinking", result)

    def test_text_after_a_tool_wins(self):
        """The same rule in the other direction, so it is ordering not priority."""
        result = mcp_tools.parse_last_action(
            [_assistant(_tool("bash_tool")), _assistant(_text("done"))]
        )
        self.assertEqual(result, "done")

    def test_malformed_lines_degrade_to_none(self):
        """Asserted, not assumed: a broad except is how a parser stops parsing."""
        self.assertIsNone(mcp_tools.parse_last_action(["{not json", "", "   "]))

    def test_no_lines_is_none(self):
        self.assertIsNone(mcp_tools.parse_last_action([]))

    def test_a_malformed_line_does_not_hide_a_later_good_one(self):
        """The degrade must not become a swallow -- the loop has to continue."""
        result = mcp_tools.parse_last_action(["{broken", _assistant(_text("recovered"))])
        self.assertEqual(result, "recovered")

    def test_newlines_are_flattened(self):
        """The status field is one line; an embedded newline would break it."""
        result = mcp_tools.parse_last_action([_assistant(_text("a\nb\nc"))])
        self.assertEqual(result, "a b c")

    def test_text_is_bounded(self):
        """80 chars. A log line is agent-written and has no natural bound."""
        result = mcp_tools.parse_last_action([_assistant(_text("x" * 500))])
        self.assertLessEqual(len(result), 80)

    def test_a_tool_detail_is_bounded_too(self):
        """The text branch truncated and the tool branch did not.

        Measured before the fix: the same 5000-character payload produced 80
        characters as text and 5009 as a tool description. The string reaches
        send_progress as an MCP notification, so an unbounded field is a
        protocol message sized by whatever the agent wrote.
        """
        result = mcp_tools.parse_last_action(
            [_assistant(_tool("Bash", description="y" * 5000))]
        )
        self.assertLessEqual(len(result), 120, "tool detail is not bounded")

    def test_a_short_tool_detail_is_not_truncated(self):
        """The bound must not eat ordinary values."""
        result = mcp_tools.parse_last_action([_assistant(_tool("Bash", description="ls -la"))])
        self.assertIn("ls -la", result)

    def test_a_wrong_typed_content_field_does_not_raise(self):
        """content as a string rather than a list -- TypeError is caught."""
        line = json.dumps({"type": "assistant", "message": {"content": "not-a-list"}})
        self.assertIsNone(mcp_tools.parse_last_action([line]))


if __name__ == "__main__":
    unittest.main()
