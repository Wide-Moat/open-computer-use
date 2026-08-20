# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""load_container_meta reads a per-chat file, and nothing tested it.

Three properties, all already true, all one edit from not being.

chat_id is sanitized before it becomes a path. _get_meta_path calls
sanitize_chat_id, so a traversal is refused 400 rather than reading
BASE_DATA_DIR/../etc/.meta.json. That guard is a separate import inside the
function, which is exactly the kind of line a refactor drops.

A corrupt file degrades to None rather than raising. The except is broad, which
is right here -- a container whose metadata will not parse should be
recreatable rather than un-restartable -- but a broad except is also how a
guard stops discriminating, so the DEGRADE is asserted rather than assumed.

And an absent file is None too, which is the ordinary case for a fresh chat and
must not be confused with the corrupt one.
"""

import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "computer-use-server"))

import docker_manager  # noqa: E402
from fastapi import HTTPException  # noqa: E402

importlib.reload(docker_manager)


class ContainerMeta(unittest.TestCase):
    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp(prefix="ocu-meta-test-"))
        self._saved = docker_manager.BASE_DATA_DIR
        docker_manager.BASE_DATA_DIR = self._tmp

    def tearDown(self):
        docker_manager.BASE_DATA_DIR = self._saved

    def _seed(self, chat_id: str, text: str) -> None:
        target = self._tmp / chat_id
        target.mkdir(parents=True, exist_ok=True)
        (target / ".meta.json").write_text(text, encoding="utf-8")

    def test_loads_saved_metadata(self):
        self._seed("metachat", json.dumps({"user_email": "a@b.c", "mcp_servers": "x"}))
        loaded = docker_manager.load_container_meta("metachat")
        self.assertEqual(loaded["user_email"], "a@b.c")

    def test_absent_metadata_is_none(self):
        """The ordinary case for a fresh chat, not an error."""
        self.assertIsNone(docker_manager.load_container_meta("never-existed"))

    def test_corrupt_metadata_degrades_to_none(self):
        """Asserted rather than assumed: a broad except is how a guard stops
        discriminating, and the caller's recovery path depends on None."""
        self._seed("corruptchat", "{not json at all")
        self.assertIsNone(docker_manager.load_container_meta("corruptchat"))

    def test_traversal_in_chat_id_is_refused(self):
        """_get_meta_path sanitizes before joining. A refactor dropping that
        import would read BASE_DATA_DIR/../etc/.meta.json instead."""
        with self.assertRaises(HTTPException) as caught:
            docker_manager.load_container_meta("../etc")
        self.assertEqual(caught.exception.status_code, 400)

    def test_meta_path_stays_under_the_data_dir(self):
        resolved = docker_manager._get_meta_path("metachat")
        self.assertTrue(str(resolved).startswith(str(self._tmp)))
        self.assertTrue(str(resolved).endswith(".meta.json"))


if __name__ == "__main__":
    unittest.main()
