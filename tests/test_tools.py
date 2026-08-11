# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""Tests for computer_use_tools (Open WebUI Tool).

Run: python -m pytest tests/test_tools.py -v
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "openwebui" / "tools"))

import computer_use_tools  # noqa: E402


class ValveSchema(unittest.TestCase):
    """v4.0.0: Tool Valve renamed FILE_SERVER_URL → ORCHESTRATOR_URL for
    consistency with the filter. Semantics unchanged — still the internal URL
    of the Computer Use server for MCP forwarding.
    """

    def test_orchestrator_url_valve_exists(self):
        valve_fields = set(computer_use_tools.Tools.Valves.model_fields.keys())
        self.assertIn("ORCHESTRATOR_URL", valve_fields)

    def test_file_server_url_valve_removed(self):
        valve_fields = set(computer_use_tools.Tools.Valves.model_fields.keys())
        self.assertNotIn("FILE_SERVER_URL", valve_fields)


class OrchestratorURLScheme(unittest.TestCase):
    """The orchestrator URL must be http(s).

    urllib honours ``file://``, ``ftp://`` and ``data://``, so a Valve holding
    one of those makes the health probe and the preflight read a local file and
    report the result as if it had come from the orchestrator. The check lives
    where the URL enters, so a scheme cannot reach any of the three call sites.
    """

    def _client(self, url):
        return computer_use_tools._MCPClient(url)

    def test_http_and_https_are_accepted(self):
        for url in ("http://orchestrator:8000", "https://orchestrator:8000"):
            with self.subTest(url=url):
                self._client(url)

    def test_file_scheme_is_refused(self):
        # The one that turns a network read into a local-file read.
        with self.assertRaises(ValueError) as caught:
            self._client("file:///etc/passwd")
        self.assertIn("file", str(caught.exception))

    def test_other_urllib_schemes_are_refused(self):
        for url in ("ftp://host/x", "data:text/plain,hi", "gopher://host/"):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    self._client(url)

    def test_a_bare_host_without_a_scheme_is_refused(self):
        # urlparse gives this an empty scheme, which urlopen then rejects far
        # from here with a message that names neither the Valve nor the URL.
        with self.assertRaises(ValueError):
            self._client("orchestrator:8000/mcp")


if __name__ == "__main__":
    unittest.main()
