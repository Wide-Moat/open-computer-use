# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""One chat cannot read another chat's uploads.

test_mcp_resources covers the LISTING side: a fresh chat inherits no resources
and sees none of another tenant's URIs. That is discovery, and discovery is not
access -- a caller who already knows a path never asks for a listing.

Nothing covered the read side. The property holds today (probed before writing
this: both cross-chat rel_paths are refused 403), and it holds because
read_chat_upload resolves the uploads directory per chat and hands rel_path to
safe_path. Every part of that is one edit away from not being true, and the
failure would be silent: a leak returns bytes rather than raising.

The distinction from test_upload_read_path is the target. That file asserts a
traversal LEAVING the base is refused. This asserts a traversal landing inside
a SIBLING chat is refused too -- same mechanism, different consequence, and the
one an operator would actually be asked about.
"""

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


class CrossChatIsolation(unittest.TestCase):
    """Needs BASE_DATA_DIR set BEFORE uploads is imported."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="ocu-tenancy-test-")
        os.environ["BASE_DATA_DIR"] = cls._tmp
        sys.path.insert(0, str(ROOT / "computer-use-server"))
        import uploads as uploads_mod

        importlib.reload(uploads_mod)
        cls.uploads = uploads_mod

        from fastapi import HTTPException

        cls.HTTPException = HTTPException

        victim = Path(cls._tmp) / "chat-a" / "uploads"
        victim.mkdir(parents=True, exist_ok=True)
        (victim / "secret.txt").write_bytes(b"chat A private data")
        neighbour = Path(cls._tmp) / "chat-b" / "uploads"
        neighbour.mkdir(parents=True, exist_ok=True)
        (neighbour / "own.txt").write_bytes(b"chat B data")

    def test_a_chat_reads_its_own_file(self):
        """The control: isolation that also blocks legitimate reads proves nothing."""
        data, _mime = self.uploads.read_chat_upload("chat-b", "own.txt")
        self.assertEqual(data, b"chat B data")

    def test_climbing_into_a_sibling_chat_is_refused(self):
        """The shape an attacker who knows the layout would try first."""
        for rel in (
            "../../chat-a/uploads/secret.txt",
            "../chat-a/uploads/secret.txt",
            "..%2F..%2Fchat-a%2Fuploads%2Fsecret.txt",
        ):
            with self.subTest(rel=rel):
                with self.assertRaises((self.HTTPException, FileNotFoundError)) as caught:
                    self.uploads.read_chat_upload("chat-b", rel)
                exception = caught.exception
                if isinstance(exception, self.HTTPException):
                    self.assertEqual(exception.status_code, 403)

    def test_a_sibling_chat_id_cannot_be_smuggled_as_a_path(self):
        """chat_id is the other lever, and it is refused earlier with 400."""
        with self.assertRaises(self.HTTPException) as caught:
            self.uploads.read_chat_upload("chat-b/../chat-a", "uploads/secret.txt")
        self.assertEqual(caught.exception.status_code, 400)

    def test_listing_does_not_reveal_the_sibling(self):
        """Discovery stays separated too, so neither half carries the property alone."""
        names = {entry.rel_path for entry in self.uploads.list_chat_uploads("chat-b")}
        self.assertEqual(names, {"own.txt"})

    def test_the_victims_file_is_still_there(self):
        """A refusal that deleted or emptied the target would also pass the above."""
        data, _mime = self.uploads.read_chat_upload("chat-a", "secret.txt")
        self.assertEqual(data, b"chat A private data")


if __name__ == "__main__":
    unittest.main()
