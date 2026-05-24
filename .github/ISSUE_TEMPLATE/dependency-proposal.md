---
name: Dependency proposal
about: Propose a new third-party dependency (Bill of Materials)
title: "Dependency proposal: <component> = <pick>"
labels: ["architecture", "dependency", "next/v1"]
assignees: []
---

<!--
Per docs/architecture/PROCESS.md "Adding a dependency (Bill of Materials)":
  1. Open this issue.
  2. Add a row to manifesto/05-licensing-posture.md BoM.
  3. Reject if any of: AGPL (any), BSL, BUSL (other than our own past
     versions), SSPL, CC-NC, commercial-only-source, sole-maintainer
     npm/PyPI without provenance.

"Heavier and vendor-backed beats lighter and unknown."
-->

## What component this satisfies

E.g. "identity provider", "secrets store", "egress proxy".

## Proposed dependency

- Name + repo URL:
- Version pin (initial):
- License:
- Bundled or not-bundled (per CLAUDE.md "Dependency policy"):
- Supply-chain attestation:
  - [ ] SBOM published upstream
  - [ ] Reproducible build documented
  - [ ] Signed releases (Cosign / Sigstore / equivalent)
  - [ ] Cosign-attested artifacts

## License gate

- [ ] Apache-2.0, MIT, BSD-2/3, MPL-2.0, LGPL-2.1 (separate service), PostgreSQL ✓
- [ ] AGPL (any), BSL, BUSL (not ours), SSPL, CC-NC, commercial-only — REJECT

## Enterprise-grade check

- [ ] Vendor-backed or named foundation (CNCF, ASF, OpenInfra, ...)?
- [ ] Bank-audit-ready upstream maintenance posture?
- [ ] Alternatives considered (≥ 1):

## Anti-pattern alternatives we explicitly reject

E.g. "we will not pin Vault (BUSL) directly — OpenBao instead."
