# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""The same chat_id is sanitised for the container name and not for the path.

docker_manager sanitises chat_id into a container name at line 501 and then
joins the RAW value into a host mount path at line 605. Both results are used
together: the name at containers.get, the paths as bind mounts (#601).

Measured:

    chat_id='../../../etc'   name owui-chat-..-..-..-etc
                             path /data/users/../../../etc/uploads
    chat_id='/etc/shadow'    name owui-chat--etc-shadow
                             path /etc/shadow/uploads

The absolute case is the sharper one -- os.path.join discards everything
before an absolute segment, so the configured base is not escaped, it is
ignored.

Two of these tests fail today. They are expectedFailure rather than skipped,
for the reason #598 states: a skip says "not checked", an xfail says "checked,
and known wrong", and an xfail that starts passing is reported rather than
silent. The fix is a compatibility decision about the header contract, so the
test states the requirement and waits for it.

The passing tests are not filler. They establish that the container NAME is
already safe, which is what makes the path's exposure a divergence rather than
a general absence of sanitisation -- and that security.sanitize_chat_id, which
already exists, would reject every payload here.
"""

import os
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "computer-use-server"))

from fastapi import HTTPException  # noqa: E402

from security import sanitize_chat_id  # noqa: E402

# The two rules as docker_manager applies them, restated so a drift is visible.
NAME_RULE = re.compile(r"[^a-zA-Z0-9_.-]")
BASE = "/data/users"

TRAVERSAL = "../../../etc"
ABSOLUTE = "/etc/shadow"


def _container_name(chat_id: str) -> str:
    return f"owui-chat-{NAME_RULE.sub('-', chat_id.lower())}"


def _mount_path(chat_id: str) -> str:
    """Line 605 as written: os.path.join on the raw value."""
    return os.path.join(BASE, chat_id.lower())


class ChatIdMountPath(unittest.TestCase):
    def test_the_source_still_builds_the_path_this_way(self):
        """If line 605 changes, this file's premise is stale and must be re-read."""
        source = (ROOT / "computer-use-server" / "docker_manager.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("os.path.join(USER_DATA_BASE_PATH, chat_id)", source)

    def test_the_container_name_is_safe(self):
        """The half that already works -- which is what makes this a divergence."""
        for value in (TRAVERSAL, ABSOLUTE, "a/b"):
            with self.subTest(value=value):
                self.assertNotRegex(_container_name(value), r"[/\\]")

    def test_the_existing_sanitiser_would_reject_these(self):
        """The fix needs no new rule: security.sanitize_chat_id already refuses."""
        for value in (TRAVERSAL, ABSOLUTE, "a/b"):
            with self.subTest(value=value):
                with self.assertRaises(HTTPException):
                    sanitize_chat_id(value)

    @unittest.expectedFailure
    def test_a_traversal_chat_id_does_not_escape_the_base(self):
        """#601: fails today. The path climbs out of USER_DATA_BASE_PATH."""
        resolved = os.path.realpath(_mount_path(TRAVERSAL))
        self.assertTrue(
            resolved == BASE or resolved.startswith(BASE + os.sep),
            f"mount path escaped the base: {resolved}",
        )

    @unittest.expectedFailure
    def test_an_absolute_chat_id_does_not_replace_the_base(self):
        """#601: fails today. os.path.join discards the base entirely."""
        self.assertTrue(
            _mount_path(ABSOLUTE).startswith(BASE),
            f"the configured base was ignored: {_mount_path(ABSOLUTE)}",
        )

    def test_an_ordinary_chat_id_stays_under_the_base(self):
        """The control: the assertions above must not pass by rejecting everything."""
        self.assertTrue(_mount_path("normal-chat").startswith(BASE + os.sep))


if __name__ == "__main__":
    unittest.main()
