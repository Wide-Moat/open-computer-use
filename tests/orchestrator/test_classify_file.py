# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""classify_file decides how the preview renders a file, and nothing tested it.

The verdict is not cosmetic. preview.js:520 branches on it, and `html` selects
renderHtmlPreview -- so this function decides which agent-written files get
rendered as markup. #594 records that the resulting iframe carries no sandbox
attribute; that is a separate defect, and this file pins the classifier itself
so the branch selection cannot drift while the question is open.

The classifier reads the EXTENSION only, which is correct for its job -- it
picks a viewer, and a viewer is a display choice rather than a trust decision.
uploads.classify() is the one that must not trust the name, because its verdict
travels to consumers as the file's type. The two are deliberately different and
the test says so, since a future reader finding two classifiers will otherwise
assume one is a mistake.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "computer-use-server"))

import app  # noqa: E402


class ClassifyFile(unittest.TestCase):
    def test_html_is_its_own_category(self):
        """The consequential branch: this is what reaches renderHtmlPreview."""
        for name in ("report.html", "page.htm", "NESTED/Deep.HTML"):
            with self.subTest(name=name):
                self.assertEqual(app.classify_file(name)[0], "html")

    def test_each_family_lands_in_its_category(self):
        cases = {
            "chart.png": "image",
            "clip.mp3": "audio",
            "demo.mp4": "video",
            "paper.pdf": "pdf",
            "notes.md": "markdown",
            "data.csv": "spreadsheet",
            "report.docx": "docx",
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(app.classify_file(name)[0], expected)

    def test_pdf_and_docx_pin_their_mime(self):
        """Both hardcode a mime rather than trusting mimetypes' local table."""
        self.assertEqual(app.classify_file("x.pdf")[1], "application/pdf")
        self.assertEqual(
            app.classify_file("x.docx")[1],
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    def test_unknown_extension_gets_a_neutral_mime(self):
        """No extension must not become a renderable category by accident."""
        category, mime = app.classify_file("mystery.zzz")
        self.assertNotIn(category, ("html", "image", "pdf"))
        self.assertEqual(mime, "application/octet-stream")

    def test_no_extension_at_all(self):
        category, mime = app.classify_file("README")
        self.assertNotEqual(category, "html")
        self.assertEqual(mime, "application/octet-stream")

    def test_a_disguised_name_is_classified_by_its_last_extension(self):
        """Recorded because it looks like a defect and is not.

        payload.exe.html classifies as html on the name alone. That is correct
        HERE: the category picks a viewer. The trust decision lives in
        uploads.classify(), which sniffs content and refuses to let the name
        decide -- covered by test_upload_classifier. Two classifiers, two jobs.
        """
        self.assertEqual(app.classify_file("payload.exe.html")[0], "html")

    def test_case_is_folded_before_matching(self):
        self.assertEqual(app.classify_file("IMAGE.PNG")[0], "image")


if __name__ == "__main__":
    unittest.main()
