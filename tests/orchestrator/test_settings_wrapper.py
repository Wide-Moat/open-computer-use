# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""settings-wrapper had no tests, and it holds two internal routes.

It serves /api/internal/user-config/{email} and
/api/internal/skills/{name}/download behind a single check that is a no-op
when API_KEY is empty (#612). Both routes are the far side of paths this
repository already has findings about: the skill name that reaches a mount
path (#595) and the internal key that a header can redirect (#607).

The module is loaded by ast-extraction rather than import: it constructs a
FastAPI app at module scope and the lint environment has no fastapi. The
functions under test are pure, so extracting them tests the real source
without standing the service up.

What this pins:

  - the auth matrix, including the empty-key row that is the finding
  - the traversal refusal, which is BETTER here than in its neighbours and
    worth locking before somebody simplifies it
  - the new startup warning, so the silent-misconfiguration gap stays closed
"""

import ast
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE = ROOT / "settings-wrapper" / "app.py"


class _HTTPException(Exception):
    def __init__(self, status_code=None, detail=None):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _load(names, **namespace):
    """Exec the named top-level functions against a controlled namespace."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    ns = {"HTTPException": _HTTPException, "os": os, "Path": Path, **namespace}
    for name in names:
        fn = next(
            n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name
        )
        exec(compile(ast.Module([fn], []), "<sw>", "exec"), ns)
    return ns


class CheckAuth(unittest.TestCase):
    def test_a_configured_key_refuses_a_wrong_one(self):
        ns = _load(["_check_auth"], API_KEY="sk-real", Header=lambda *a, **k: None)
        for supplied in (None, "", "wrong"):
            with self.subTest(supplied=supplied):
                with self.assertRaises(_HTTPException) as caught:
                    ns["_check_auth"](supplied)
                self.assertEqual(caught.exception.status_code, 401)

    def test_a_configured_key_accepts_the_right_one(self):
        """The control: a check that refuses everything would pass the above."""
        ns = _load(["_check_auth"], API_KEY="sk-real", Header=lambda *a, **k: None)
        self.assertIsNone(ns["_check_auth"]("sk-real"))

    def test_an_empty_key_allows_everyone(self):
        """#612, asserted as the behaviour that currently holds.

        Not an xfail: whether an empty key should REFUSE is a deployment
        decision shared with #552, and stating the requirement here would
        pre-empt it. What is fixed instead is the silence -- see below.
        """
        ns = _load(["_check_auth"], API_KEY="", Header=lambda *a, **k: None)
        for supplied in (None, "wrong", "sk-anything"):
            with self.subTest(supplied=supplied):
                self.assertIsNone(ns["_check_auth"](supplied))


class WarnIfApiKeyMissing(unittest.TestCase):
    def test_it_warns_when_the_key_is_empty(self):
        ns = _load(["warn_if_api_key_missing"], API_KEY="")
        self.assertTrue(ns["warn_if_api_key_missing"]())

    def test_it_stays_quiet_when_the_key_is_set(self):
        """A warning that always fires is a warning nobody reads."""
        ns = _load(["warn_if_api_key_missing"], API_KEY="sk-real")
        self.assertFalse(ns["warn_if_api_key_missing"]())

    def test_it_is_called_at_import(self):
        """A warning nothing invokes is not a warning."""
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("\nwarn_if_api_key_missing()\n", source)


class ValidateSkillName(unittest.TestCase):
    def test_ordinary_names_pass(self):
        ns = _load(["_validate_skill_name"], _SKILL_NAME_RE=__import__("re").compile(r"^[a-zA-Z0-9_-]+$"))
        for name in ("pptx", "my-skill", "skill_2"):
            with self.subTest(name=name):
                self.assertEqual(ns["_validate_skill_name"](name), name)

    def test_traversal_and_separators_are_refused(self):
        """Two independent guards here -- the regex AND an explicit '..' check.

        Worth locking: this is stronger than the mount-path construction in
        docker_manager (#601), and a simplification that dropped one of the
        two would still look correct.
        """
        ns = _load(["_validate_skill_name"], _SKILL_NAME_RE=__import__("re").compile(r"^[a-zA-Z0-9_-]+$"))
        for name in ("..", "../etc", "a/b", "a\\b", "a.b", ""):
            with self.subTest(name=name):
                with self.assertRaises(_HTTPException) as caught:
                    ns["_validate_skill_name"](name)
                self.assertEqual(caught.exception.status_code, 400)

    def test_the_source_still_has_both_guards(self):
        """If either is removed the other still passes these tests."""
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("_SKILL_NAME_RE.match(name)", source)
        self.assertIn("'..' in name", source)

    def test_the_download_route_also_contains_the_path(self):
        """realpath + os.sep suffix, independent of the name check."""
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("os.path.realpath", source)
        self.assertIn("base_resolved + os.sep", source)


if __name__ == "__main__":
    unittest.main()
