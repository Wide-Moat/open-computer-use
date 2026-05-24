<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: research
last-reviewed: 2026-05-24
owner: nick
applies-to: next/v1 positioning thesis (§01 widemoat); supersedes open question #2 in proof-uipath-anthropic-2026-05.md
---

Primary-source check of what Anthropic publishes (licence, source URL, signed artefacts) for the customer-installed components that ship with the 19 May 2026 self-hosted-sandbox + MCP-tunnel launch.

### What is public (with URLs)

| Artifact | Source URL | Licence | SBOM | Signed binary? |
|---|---|---|---|---|
| `@anthropic-ai/claude-code` (npm 2.1.150, 126k stars on issue tracker) | https://github.com/anthropics/claude-code (issue tracker only, no `src/`) | Proprietary; `LICENSE.md`: "© Anthropic PBC. All rights reserved. Use is subject to Anthropic's Commercial Terms of Service" | Not published | Not declared |
| `@anthropic-ai/claude-agent-sdk` (npm 0.3.150) + `claude-agent-sdk-linux-x64`, `…-musl`, `…-darwin-arm64` native binary subpackages | https://github.com/anthropics/claude-agent-sdk-typescript (issue tracker only, no `src/`) | Proprietary; same `LICENSE.md` text as claude-code | Not published | Not declared |
| `claude-agent-sdk` (PyPI 0.2.87) | https://github.com/anthropics/claude-agent-sdk-python | MIT (pure-Python wrapper; spawns the bundled npm CLI binary as a subprocess) | Not published | Not declared |
| `@anthropic-ai/sdk` (npm 0.98.0), `anthropic` (PyPI 0.104.1) | https://github.com/anthropics/anthropic-sdk-typescript and `…-python` | MIT (REST client only, no agent loop) | Not published | Not declared |
| `@anthropic-ai/sandbox-runtime` (`srt`, npm 0.0.52) | https://github.com/anthropic-experimental/sandbox-runtime (4,104 stars) | Apache-2.0 | Not published | Not declared |
| MCP tunnel proxy (Anthropic-authored container) | OCI: `us-docker.pkg.dev/anthropic-public-registry/charts/mcp-tunnel`, version 1.0.0; no GitHub repo found | Not declared on the docs page or the registry; "as-is" research preview, request-access | Not published | Not declared |
| MCP tunnel agent | upstream `cloudflared` (https://github.com/cloudflare/cloudflared) — pulled as-is, not re-distributed by Anthropic | Apache-2.0 (Cloudflare's licence) | Cloudflare's | Cloudflare's |
| `anthropics/skills` | https://github.com/anthropics/skills | No licence file (139k stars) | n/a | n/a |

### What is not public (with explicit "we searched X, did not find Y")

- We searched `gh search repos org:anthropics` and `org:anthropic-experimental` for `sandbox-runtime`, `mcp-tunnel`, `tunnel-proxy`, `gateway`, `managed-agent` — only `anthropic-experimental/sandbox-runtime` came back. There is no public `anthropics/mcp-tunnel-proxy` or equivalent.
- `anthropics/computer-use-demo` (Apache-2.0 in 2024) returns HTTP 404 as of 2026-05-24; it has been deleted or made private.
- We searched https://code.claude.com/docs/en/agent-sdk/hosting, `…/secure-deployment`, https://platform.claude.com/docs/en/agents-and-tools/mcp-tunnels/overview, and `…/deploy-helm`, and the 19 May 2026 announcement: none state a licence, SBOM, cosign signature, reproducible-build recipe, or source URL for the Helm chart, the proxy image, or the bundled Claude Code binary inside `@anthropic-ai/claude-agent-sdk`.
- We searched the npm `@anthropic-ai/*` scope for any tunnel-gateway package: no such package exists.
- We checked the `LICENSE.md` text on both `anthropics/claude-code` and `anthropics/claude-agent-sdk-typescript`: identical, both proprietary. GitHub's licence detector reports `license: null` for both because the file is not a recognised OSI text.

### Plain-English answer

Anthropic's customer-installed stack is a mix. The thin parts are open. The Python wrapper, the REST clients, and the standalone host-level `srt` tool are MIT or Apache-2.0 with full source on GitHub. The load-bearing parts are not. The TypeScript SDK and the Claude Code CLI ship as prebuilt native binaries on npm under "© Anthropic PBC. All rights reserved. Use is subject to Anthropic's Commercial Terms of Service" — their GitHub repos hold only the changelog and the issue tracker, not the source. The MCP tunnel proxy is distributed as an opaque OCI artefact from `us-docker.pkg.dev/anthropic-public-registry`, with no GitHub repo, no declared licence, no SBOM, no cosign signature, and a research-preview "as-is, request-access" status. The only fully open component on the tunnel data path is Cloudflare's `cloudflared`, which Anthropic pulls as-is. A bank InfoSec architect must treat the proxy image and the Claude Code binary as closed third-party software under Anthropic's commercial terms, with no provenance attestation available today.

### Impact on §01 wording

Previous open question #2 framed the licence as "undeclared." That framing was too soft. The correction:

- The sandbox runtime exists in two senses. (a) Host-level `srt` is Apache-2.0 open source — that part is not part of the gap. (b) The runtime image pulled by Cloudflare / Modal / Daytona / Vercel into the sandbox is not an Anthropic artefact at all; customers compose their own container with the SDK installed via npm/pip.
- The MCP tunnel gateway is two components. (a) `cloudflared` is upstream Apache-2.0. (b) The Anthropic proxy is closed: no source, no SBOM, no signature, commercial terms, research preview.
- The Claude Code binary bundled by the agent SDK is closed under Anthropic Commercial ToS.

Proposed §01 sentence: "Anthropic ships the sandbox-host tool (`srt`) as Apache-2.0 open source and the tunnel transport as upstream Cloudflare `cloudflared`, but the agent loop, the Claude Code binary, and the MCP-tunnel proxy image are closed binaries distributed under its Commercial Terms of Service with no SBOM or signed-provenance attestation as of 2026-05-24." This keeps the moat claim accurate without overstating the closed surface.
