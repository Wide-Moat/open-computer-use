# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""The upload classifier decides by content, not by filename.

NFR-SEC-81 asks that every uploaded body be classified by magic-byte sniff plus
declared media type, with the mismatch recorded. Before the classifier landed,
`mimetypes.guess_type(path.name)` was the whole implementation, so renaming an
executable to payload.exe.png made it image/png.

check-upload-content-sniffing.py holds the shape of that code in CI. This holds
the BEHAVIOUR, in the suite that runs against a real Python: the two answer
different questions, and the lint half was measurably insufficient on its own --
blanking the sniff result left every structural marker in place while the
classifier went back to trusting the extension.

Also asserts the listing carries the verdict through. A classifier that resolves
correctly and reports nothing downstream leaves every consumer as blind as
before.
"""

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


class UploadClassifier(unittest.TestCase):
    """Needs BASE_DATA_DIR set BEFORE uploads is imported."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="ocu-classify-test-")
        os.environ["BASE_DATA_DIR"] = cls._tmp
        sys.path.insert(0, str(ROOT / "computer-use-server"))
        import uploads as uploads_mod

        importlib.reload(uploads_mod)
        cls.uploads = uploads_mod

    def _write(self, name: str, data: bytes) -> Path:
        path = Path(self._tmp) / name
        path.write_bytes(data)
        return path

    def test_disguised_executable_is_not_an_image(self):
        """The defect this replaced: payload.exe.png resolving to image/png."""
        path = self._write("payload.exe.png", b"MZ\x90\x00\x03")
        resolved, declared, sniffed, mismatch = self.uploads.classify(path)
        self.assertEqual(declared, "image/png", "the filename still claims an image")
        self.assertNotEqual(resolved, "image/png", "content must win over the extension")
        self.assertEqual(sniffed, "application/x-msdownload")
        self.assertTrue(mismatch, "the disagreement must be recorded, not resolved away")

    def test_genuine_png_is_not_flagged(self):
        """A correct file must not raise a mismatch, or the flag means nothing."""
        path = self._write("real.png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0d")
        resolved, declared, sniffed, mismatch = self.uploads.classify(path)
        self.assertEqual(resolved, "image/png")
        self.assertEqual(declared, sniffed)
        self.assertFalse(mismatch)

    def test_unrecognised_content_keeps_the_declared_type(self):
        """Most text has no magic number. Guessing there would break plain files."""
        path = self._write("notes.txt", b"hello world, no signature here")
        resolved, _declared, sniffed, mismatch = self.uploads.classify(path)
        self.assertEqual(resolved, "text/plain")
        self.assertEqual(sniffed, "", "no signature matched, so nothing was invented")
        self.assertFalse(mismatch)

    def test_zip_wearing_an_image_extension(self):
        """A second disguise shape, so the executable case is not the only one."""
        path = self._write("archive.png", b"PK\x03\x04\x14\x00\x00\x00")
        resolved, _declared, _sniffed, mismatch = self.uploads.classify(path)
        self.assertEqual(resolved, "application/zip")
        self.assertTrue(mismatch)

    def test_empty_file_does_not_crash(self):
        """Zero bytes match no signature and must not raise."""
        path = self._write("empty.png", b"")
        resolved, declared, sniffed, mismatch = self.uploads.classify(path)
        self.assertEqual(resolved, declared)
        self.assertEqual(sniffed, "")
        self.assertFalse(mismatch)

    def test_listing_carries_the_verdict(self):
        """A classifier nothing reports is as blind as no classifier."""
        chat = "classify-demo"
        uploads_dir = Path(self._tmp) / chat / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        (uploads_dir / "payload.exe.png").write_bytes(b"MZ\x90\x00\x03")

        entries = self.uploads.list_chat_uploads(chat)
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry.declared_mime, "image/png")
        self.assertEqual(entry.sniffed_mime, "application/x-msdownload")
        self.assertTrue(entry.type_mismatch)
        self.assertNotEqual(entry.mime_type, "image/png")


if __name__ == "__main__":
    unittest.main()
