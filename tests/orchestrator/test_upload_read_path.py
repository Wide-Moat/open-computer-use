# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""read_chat_upload is the byte path, and nothing exercised it.

list_chat_uploads had coverage through test_mcp_resources; its sibling did not.
That matters more than the symmetry suggests: read_chat_upload takes a
`rel_path` straight from an MCP resource URI (mcp_resources.py:88), so the
segment reaching safe_path is attacker-formable by whatever drives the model.

test_security_boundaries pins safe_path itself. This pins that read_chat_upload
still ROUTES through it -- a future edit that joins the path directly would
leave every safe_path test green while the traversal guard stopped applying to
the one caller that needs it most.

Also pins the tuple contract: the function returns (bytes, mime), and the mime
half now comes from the content classifier rather than the filename.
"""

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


class ReadChatUpload(unittest.TestCase):
    """Needs BASE_DATA_DIR set BEFORE uploads is imported."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="ocu-read-test-")
        os.environ["BASE_DATA_DIR"] = cls._tmp
        sys.path.insert(0, str(ROOT / "computer-use-server"))
        import uploads as uploads_mod

        importlib.reload(uploads_mod)
        cls.uploads = uploads_mod

        from fastapi import HTTPException

        cls.HTTPException = HTTPException

    def _seed(self, chat_id: str, rel_path: str, data: bytes) -> None:
        target = Path(self._tmp) / chat_id / "uploads" / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def test_reads_a_flat_file(self):
        self._seed("readerchat", "hello.txt", b"contents")
        data, mime = self.uploads.read_chat_upload("readerchat", "hello.txt")
        self.assertEqual(data, b"contents")
        self.assertEqual(mime, "text/plain")

    def test_reads_a_nested_file(self):
        self._seed("readerchat", "sub/nested.json", b"{}")
        data, _mime = self.uploads.read_chat_upload("readerchat", "sub/nested.json")
        self.assertEqual(data, b"{}")

    def test_mime_comes_from_content_not_the_name(self):
        """The read path must not reintroduce filename-trust behind the listing."""
        self._seed("readerchat", "payload.exe.png", b"MZ\x90\x00\x03")
        _data, mime = self.uploads.read_chat_upload("readerchat", "payload.exe.png")
        self.assertNotEqual(mime, "image/png")

    def test_missing_file_raises_filenotfound(self):
        with self.assertRaises(FileNotFoundError):
            self.uploads.read_chat_upload("readerchat", "does-not-exist.txt")

    def test_traversal_in_rel_path_is_refused(self):
        """rel_path arrives from an MCP resource URI, so it is attacker-formable.

        Refused by safe_path with 403 rather than reported as missing -- the
        distinction matters, because FileNotFoundError would tell a caller the
        path was merely absent and invite them to try another.
        """
        outside = Path(self._tmp) / "outside.txt"
        outside.write_text("secret", encoding="utf-8")
        with self.assertRaises(self.HTTPException) as caught:
            self.uploads.read_chat_upload("readerchat", "../../outside.txt")
        self.assertEqual(caught.exception.status_code, 403)

    def test_traversal_in_chat_id_is_refused(self):
        """The other untrusted segment, refused earlier and with a different code."""
        with self.assertRaises(self.HTTPException) as caught:
            self.uploads.read_chat_upload("../etc", "hello.txt")
        self.assertEqual(caught.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
