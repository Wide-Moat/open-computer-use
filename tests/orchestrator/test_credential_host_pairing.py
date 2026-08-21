# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""A caller-named host must not be reached with a deployment credential.

Two places resolve a host and its credential from independent ContextVars,
each with its own env fallback:

    544  anthropic_key  = current_anthropic_auth_token.get() or ANTHROPIC_AUTH_TOKEN
    545  anthropic_base = current_anthropic_base_url.get()   or ANTHROPIC_BASE_URL

    305  mcp_tokens_url     = current_mcp_tokens_url.get()     or MCP_TOKENS_URL
    306  mcp_tokens_api_key = current_mcp_tokens_api_key.get() or MCP_TOKENS_API_KEY

Because the fallbacks are independent, supplying only the host header pairs a
caller-chosen destination with the deployment's own secret (#605, #607).

test_base_url_token_pairing covers the first pair. This covers the SHAPE, and
the second instance, for a reason worth stating: finding the same defect twice
means the next credential+host pair will be written the same way unless
something enumerates them. The sweep test below does that -- it reads the
source, finds every `current_X.get() or ENV` fallback, and fails if a new one
appears without a matching entry here.

The second pair is worse than the first. The deployment's internal API key
goes out in a header, and the response's `token` field comes back as the
GitLab credential injected into the guest -- so a caller-named host both
receives a secret and supplies one.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE = ROOT / "computer-use-server" / "docker_manager.py"

FALLBACK = re.compile(r"(\w+)\s*=\s*(current_\w+)\.get\(\)\s*or\s*([A-Z_]+)")

# Every credential+host pair known to resolve independently, with the issue
# that records it. A new pair must be added here deliberately.
KNOWN_PAIRS = {
    ("current_anthropic_auth_token", "current_anthropic_base_url"): "#605",
    ("current_mcp_tokens_api_key", "current_mcp_tokens_url"): "#607",
}


def _resolve(header_value, env_default):
    """The `or` fallback exactly as written at all four sites."""
    return header_value or env_default


class CredentialHostPairing(unittest.TestCase):
    def test_the_sweep_finds_no_unrecorded_fallback(self):
        """A new credential+host pair must not appear unnoticed.

        This is the point of the file. The same defect was found twice, in
        places written months apart, which means the shape reproduces itself.
        An enumeration that fails on a new instance is the only thing that
        catches the third.
        """
        found = {m.group(2) for m in FALLBACK.finditer(SOURCE.read_text(encoding="utf-8"))}
        recorded = {name for pair in KNOWN_PAIRS for name in pair}
        unrecorded = found - recorded
        self.assertEqual(
            unrecorded,
            set(),
            f"new ContextVar-or-env fallback(s) with no recorded pairing: {sorted(unrecorded)}",
        )

    def test_both_recorded_pairs_are_still_present(self):
        """If a pair is fixed or removed, this file is stale and says so."""
        source = SOURCE.read_text(encoding="utf-8")
        for pair in KNOWN_PAIRS:
            for name in pair:
                with self.subTest(name=name):
                    self.assertIn(f"{name}.get() or ", source)

    def test_a_host_header_alone_takes_the_deployment_secret(self):
        """The defect, stated as the behaviour that currently holds.

        Not expectedFailure: this asserts what the code DOES, so it documents
        the exposure without pretending the fix has landed. The requirement is
        stated as an xfail in test_base_url_token_pairing; duplicating that
        here would give two tests to update for one fix.
        """
        secret = "sk-deployment"
        key = _resolve(None, secret)
        host = _resolve("https://attacker.example", "https://internal")
        self.assertEqual(key, secret)
        self.assertEqual(host, "https://attacker.example")

    def test_supplying_both_headers_uses_neither_deployment_value(self):
        """The supported override, which any fix must preserve."""
        self.assertEqual(_resolve("sk-caller", "sk-deployment"), "sk-caller")
        self.assertEqual(_resolve("https://caller", "https://internal"), "https://caller")


if __name__ == "__main__":
    unittest.main()
