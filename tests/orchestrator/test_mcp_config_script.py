# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""build_mcp_config_write_script builds a shell command, and nothing tested it.

Two properties are worth pinning, and both are already true.

The config is base64'd rather than interpolated. A server name or URL carrying
a quote would otherwise break out of the python3 -c string -- the script is
assembled by f-string, so escaping is the only thing standing between a config
value and shell syntax, and base64 removes the question rather than answering
it carefully.

The token is not in the script. ANTHROPIC_AUTH_TOKEN is read from the
container's own environment at runtime, so the command -- which is visible in
`docker inspect`, in any exec log, and to anything that can read the process
table -- carries no credential. NFR-SEC-75 requires exactly this shape, and the
test states it as a property of the OUTPUT rather than of how the output is
built.
"""

import base64
import importlib
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "computer-use-server"))

import docker_manager  # noqa: E402

importlib.reload(docker_manager)


class McpConfigWriteScript(unittest.TestCase):
    def _script(self, config: dict) -> str:
        return docker_manager.build_mcp_config_write_script(config)

    def test_config_survives_the_round_trip(self):
        """The payload must arrive intact, or the encoding is just obfuscation."""
        config = {"mcpServers": {"ocu": {"url": "http://host:8081/mcp", "headers": {}}}}
        script = self._script(config)
        blob = re.search(r'b64decode\("([^"]+)"\)', script)
        self.assertIsNotNone(blob, "the script no longer carries a base64 payload")
        self.assertEqual(json.loads(base64.b64decode(blob.group(1))), config)

    def test_a_quote_in_a_config_value_cannot_reach_the_shell(self):
        """The reason base64 is there. An f-string offers no other protection."""
        hostile = {
            "mcpServers": {
                "evil'; touch /tmp/pwned; #": {
                    "url": 'http://x/"; rm -rf /; "',
                    "headers": {},
                }
            }
        }
        script = self._script(hostile)
        self.assertNotIn("touch /tmp/pwned", script)
        self.assertNotIn("rm -rf /", script)
        # And it still round-trips, so the defence is encoding rather than dropping.
        blob = re.search(r'b64decode\("([^"]+)"\)', script)
        self.assertEqual(json.loads(base64.b64decode(blob.group(1))), hostile)

    def test_the_script_carries_no_token(self):
        """NFR-SEC-75: the command is world-readable; the credential must not be in it."""
        script = self._script({"mcpServers": {"ocu": {"headers": {}}}})
        self.assertIn("os.environ.get(\"ANTHROPIC_AUTH_TOKEN\"", script)
        self.assertNotIn("Bearer sk-", script)
        for line in script.splitlines():
            self.assertNotRegex(
                line,
                r"ANTHROPIC_AUTH_TOKEN\s*=\s*\S",
                "the token is assigned a literal value in the script",
            )

    def test_a_token_shaped_value_in_the_config_is_still_encoded(self):
        """If a caller puts a secret in the config, it must not appear in clear."""
        config = {"mcpServers": {"ocu": {"headers": {"X-Key": "sk-ant-secret-value"}}}}
        script = self._script(config)
        self.assertNotIn("sk-ant-secret-value", script)

    def test_enables_exactly_the_servers_it_was_given(self):
        """The auto-approve list is derived, so a stale hardcoded name would show."""
        script = self._script({"mcpServers": {"alpha": {}, "beta": {}}})
        self.assertIn("enabledMcpjsonServers", script)
        self.assertIn('c["mcpServers"].keys()', script)


if __name__ == "__main__":
    unittest.main()
