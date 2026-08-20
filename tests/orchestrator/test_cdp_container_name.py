# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""The CDP lookup sanitises chat_id differently, and that is deliberate.

get_container_cdp_address does not call security.sanitize_chat_id. It applies
its own rule -- `re.sub(r'[^a-zA-Z0-9_.-]', '-', chat_id.lower())` -- and the
two disagree. Measured:

    '../etc'  ->  local '..-etc'     strict REFUSED
    'a.b'     ->  local 'a.b'        strict REFUSED
    "x'y"     ->  local 'x-y'        strict REFUSED

A second sanitiser next to a strict one usually means somebody forgot. Here it
does not, and the reason is what this file records: the output becomes a DOCKER
CONTAINER NAME, never a filesystem path. `sanitized_id` has four uses and every
one feeds `owui-chat-{...}` into `containers.get`. Dots are legal in a container
name and dangerous in a path, which is exactly why the strict rule rejects them
and this one need not.

So the property to hold is not "both rules agree" -- they must not. It is that
the local rule maps every separator to a dash, so no input can produce a name
that addresses a different container than intended, and that the result is
never used as a path.
"""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "computer-use-server"))

SANITISE = re.compile(r"[^a-zA-Z0-9_.-]")


def _local_rule(chat_id: str) -> str:
    """The rule as docker_manager applies it, restated so a drift is visible."""
    return SANITISE.sub("-", chat_id.lower())


class CdpContainerName(unittest.TestCase):
    def test_the_source_still_applies_this_rule(self):
        """If docker_manager's regex changes, this file's premise is stale."""
        source = (ROOT / "computer-use-server" / "docker_manager.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(r"re.sub(r'[^a-zA-Z0-9_.-]', '-', chat_id)", source)

    def test_separators_cannot_survive_into_the_name(self):
        """A slash or backslash reaching containers.get would address elsewhere."""
        for value in ("a/b", "a\\b", "../etc", "a b", "x'y", 'x"y', "a;b"):
            with self.subTest(value=value):
                self.assertNotRegex(_local_rule(value), r"[/\\ ;'\"]")

    def test_ordinary_ids_are_unchanged(self):
        for value in ("default", "abc123", "test-123", "a.b", "a_b"):
            with self.subTest(value=value):
                self.assertEqual(_local_rule(value), value)

    def test_case_is_folded(self):
        self.assertEqual(_local_rule("MixedCase"), "mixedcase")

    def test_it_diverges_from_the_strict_rule_on_dots(self):
        """Stated as a test so the divergence is a decision, not an accident.

        A dot is legal in a container name and dangerous in a path. The strict
        rule guards paths and rejects it; this one guards a name and need not.
        """
        from fastapi import HTTPException
        from security import sanitize_chat_id

        self.assertEqual(_local_rule("a.b"), "a.b")
        with self.assertRaises(HTTPException):
            sanitize_chat_id("a.b")

    def test_the_sanitised_value_never_becomes_a_path(self):
        """The premise of the whole divergence, asserted against the source."""
        source = (ROOT / "computer-use-server" / "docker_manager.py").read_text(
            encoding="utf-8"
        )
        for line in source.splitlines():
            if "sanitized_id" not in line or line.strip().startswith("#"):
                continue
            if "sanitized_id =" in line:
                continue
            self.assertIn(
                "owui-chat-",
                line,
                "sanitized_id reached something other than a container name",
            )


if __name__ == "__main__":
    unittest.main()
