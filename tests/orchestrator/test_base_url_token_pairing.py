# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""A caller-set base URL must not receive the deployment's credential.

docker_manager.py:544-547 reads the token and the base URL from two
independent ContextVars, each falling back to its own env default:

    anthropic_key  = current_anthropic_auth_token.get() or ANTHROPIC_AUTH_TOKEN
    anthropic_base = current_anthropic_base_url.get()   or ANTHROPIC_BASE_URL

Both are set straight from request headers with no validation, and because the
fallbacks are independent, supplying only the URL header pairs a caller-chosen
host with the deployment's own token (#605).

The same value also templates every MCP server URL (build_mcp_config, line
339), and those calls carry the token too -- so one header redirects both the
model calls and the tool calls.

The pairing test is expectedFailure: the fix changes what the server accepts
for anyone relying on URL-only override, which is a compatibility decision.
The other three combinations are asserted as passing, because a fix that broke
them would be worse than the defect -- an operator overriding both values is
the ordinary supported case.
"""

import unittest

# The two lines under test, restated. The real ones live inside a 200-line
# container-creation function that needs a Docker client to reach; restating
# them keeps the test honest about what it covers -- the PAIRING rule, not the
# surrounding function -- and a guard below asserts the source still matches.
DEPLOYMENT_TOKEN = "sk-deployment-secret"
DEPLOYMENT_BASE = "https://api.anthropic.com"


def _resolve(header_token, header_base):
    token = header_token or DEPLOYMENT_TOKEN
    base = header_base or DEPLOYMENT_BASE
    return token, base


class BaseUrlTokenPairing(unittest.TestCase):
    def test_the_source_still_resolves_them_independently(self):
        """If the fallbacks change, this file's premise is stale."""
        from pathlib import Path

        source = (
            Path(__file__).resolve().parent.parent.parent
            / "computer-use-server"
            / "docker_manager.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "current_anthropic_base_url.get() or ANTHROPIC_BASE_URL", source
        )
        self.assertIn(
            "current_anthropic_auth_token.get() or ANTHROPIC_AUTH_TOKEN", source
        )

    def test_no_headers_uses_the_deployment_pair(self):
        token, base = _resolve(None, None)
        self.assertEqual((token, base), (DEPLOYMENT_TOKEN, DEPLOYMENT_BASE))

    def test_both_headers_use_the_caller_pair(self):
        """The ordinary supported override, which the fix must not break."""
        token, base = _resolve("sk-caller", "https://caller.example")
        self.assertEqual((token, base), ("sk-caller", "https://caller.example"))

    def test_a_token_header_alone_keeps_the_deployment_host(self):
        """Harmless direction: the caller's own token to the default host."""
        token, base = _resolve("sk-caller", None)
        self.assertEqual((token, base), ("sk-caller", DEPLOYMENT_BASE))

    @unittest.expectedFailure
    def test_a_url_header_alone_must_not_carry_the_deployment_token(self):
        """#605: fails today. The interesting row of the four."""
        token, base = _resolve(None, "https://attacker.example")
        self.assertNotEqual(
            token,
            DEPLOYMENT_TOKEN,
            f"the deployment credential would be sent to {base}",
        )


if __name__ == "__main__":
    unittest.main()
