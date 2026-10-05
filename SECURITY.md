<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# Security Policy

This repository is archived. It receives no security fixes, and vulnerability reports against it are not accepted.

## Known issues

Issues reported before archival were not all fixed and will not be. [Known limitations](README.md#known-limitations) lists the main ones, among them passwordless `sudo` in the sandbox, credentials passed as environment variables and HTTP headers, and sandbox containers with network access by default. Do not run this code in production or expose it to untrusted users.

## Successor

[Wide Moat](https://widemoat.ai) replaces this project. Its sandbox uses gVisor on Kubernetes with egress through a MITM proxy. Security reports about Wide Moat go to developer@widemoat.ai.

## Disclosure

Public issues and pull requests are closed. The advisory form is disabled.
