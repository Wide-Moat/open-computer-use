# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""Every request header that becomes a ContextVar, enumerated.

set_context_from_headers takes ten values from request headers and sets them
as ContextVars. None is validated at that boundary -- .lower() on chat_id and
urllib.unquote on user_name are normalisation, not checks.

Four of the ten have a recorded consequence:

    current_chat_id               -> host mount path (#601), system prompt (#609)
    current_user_email            -> upstream header value (#603, fixed #604)
    current_anthropic_base_url    -> upstream host with deployment token (#605)
    current_mcp_tokens_url        -> internal key out, credential back in (#607)

The other six reach container environment variables, which NFR-SEC-75 permits
explicitly -- a secret may be handed to a tool through the environment. They
are listed anyway, because "checked and found harmless" and "never looked at"
are different states and only one of them survives a new consumer.

That is what this file is for. Eight findings came from the same root, found
one at a time by tracing a value to its sink. An inventory that fails when an
ELEVENTH variable appears turns the next one into a build failure instead of
an investigation.
"""

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE = ROOT / "computer-use-server" / "mcp_tools.py"

ASSIGNMENT = re.compile(r"(current_\w+)\.set\(")

# Every ContextVar set from a request header, with where its value goes.
# A new entry here is a deliberate act; an unlisted one fails the test.
KNOWN = {
    "current_chat_id": "mount path (#601) + system prompt (#609)",
    "current_user_email": "upstream header value (#603, fixed #604)",
    "current_user_name": "container env: GIT_AUTHOR_NAME",
    "current_gitlab_token": "container env: GITLAB_TOKEN",
    "current_gitlab_host": "container env: GITLAB_HOST",
    "current_anthropic_auth_token": "container env + paired with base URL (#605)",
    "current_anthropic_base_url": "upstream host, MCP server URLs (#605)",
    "current_mcp_tokens_url": "tokens-wrapper host (#607)",
    "current_mcp_tokens_api_key": "tokens-wrapper key (#607)",
    "current_mcp_servers": "MCP server name list",
}


def _header_set_vars() -> set[str]:
    source = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "set_context_from_headers"
    )
    lines = source.splitlines()
    found = set()
    for i in range(fn.lineno, (fn.end_lineno or fn.lineno) + 1):
        match = ASSIGNMENT.search(lines[i - 1])
        if match:
            found.add(match.group(1))
    return found


class HeaderBoundaryInventory(unittest.TestCase):
    def test_no_unlisted_header_variable(self):
        """An eleventh variable must be a build failure, not an investigation.

        This is the point of the file. Eight findings came from one root,
        located one at a time by tracing a value to its sink; the enumeration
        is what makes the next one arrive as a red test instead.
        """
        unlisted = _header_set_vars() - set(KNOWN)
        self.assertEqual(
            unlisted,
            set(),
            f"header-set ContextVar(s) with no recorded destination: {sorted(unlisted)}",
        )

    def test_every_listed_variable_is_still_set_from_a_header(self):
        """The inventory must not accumulate entries for code that is gone."""
        stale = set(KNOWN) - _header_set_vars()
        self.assertEqual(stale, set(), f"listed but no longer header-set: {sorted(stale)}")

    def test_the_boundary_still_validates_nothing(self):
        """States the gap as a fact rather than leaving it implied.

        When a boundary check lands, this test fails and the file is updated
        deliberately -- which is the right amount of friction for a change
        that alters what the server accepts (#601).
        """
        source = SOURCE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        fn = next(
            n
            for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name == "set_context_from_headers"
        )
        body = ast.unparse(fn)
        self.assertNotIn("sanitize_chat_id", body)
        self.assertNotIn("header_safe", body)

    def test_the_count_is_ten(self):
        """A blunt guard: a silent removal is as much a change as an addition."""
        self.assertEqual(len(_header_set_vars()), 10)


if __name__ == "__main__":
    unittest.main()
