<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# Security Policy

## Reporting a vulnerability

Use the GitHub **private vulnerability reporting** form:
[Wide-Moat/open-computer-use → Security → Advisories → New advisory](https://github.com/Wide-Moat/open-computer-use/security/advisories/new)

Do not open a public issue or pull request for a security problem. Public disclosure happens after the fix lands and (where applicable) a CVE is published.

## What's in scope

- Code in this repository on the `main` and `next/v1` branches.
- Container images we publish to GHCR.
- Helm chart we publish.

## What's not in scope

- Third-party dependencies — report upstream (we will track and patch).
- Vulnerabilities in customer deployments unless the root cause is in our code.

## Response timeline

We aim for:

- Acknowledgement of receipt: ≤ 3 business days.
- Initial severity assessment: ≤ 5 business days.
- Patch + advisory for a confirmed Critical/High: ≤ 30 days from confirmation, faster when feasible.

## Supported versions

Each release of the Software is licensed under FSL-1.1-Apache-2.0 and automatically converts to Apache-2.0 two years after publication.

We patch security issues on `main` and `next/v1`. We do not back-port fixes to tagged releases older than the most recent minor.

## Coordinated disclosure

We follow [coordinated vulnerability disclosure](https://en.wikipedia.org/wiki/Coordinated_vulnerability_disclosure). Once a fix is available and customers have had a reasonable window to upgrade, the advisory is made public with credit to the reporter (if requested).
