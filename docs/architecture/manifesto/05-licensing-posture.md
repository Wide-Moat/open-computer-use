<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: draft
last-reviewed: 2026-06-14
owner: "@Wide-Moat/architects"
applies-to: next/v1
---

States the licence OCU ships under, the conversion to Apache-2.0, and the gate every dependency passes before it enters the project. Audience: anyone adding a dependency or reasoning about what a fork may do.

## OCU licence: FSL-1.1-Apache-2.0

OCU ships under the [Functional Source License, Version 1.1, Apache 2.0 Future License](../../../LICENSE). The grant lets you use, copy, modify, create derivative works, publish, and redistribute the Software. The one limitation: you may not offer the Software (or a modified version) to third parties on a hosted or embedded basis to compete with a paid version of OCU.

Each release carries its own clock. On the **second anniversary** of the date a given version is made available, that version is additionally licensed under Apache-2.0; from that date the FSL limitation no longer binds it. The conversion is per-release and irrevocable: a release published 2026-06-01 is Apache-2.0 on 2028-06-01 regardless of what later releases do.

The conversion is automatic — no pricing decision and no manual relicensing step. The FSL template carries a license-key anti-tamper clause; OCU ships no license key, so that clause binds nothing here. The change from BUSL-1.1 was a one-time, whole-repo migration ([CHANGELOG](../../../CHANGELOG.md)); releases tagged before it retain BUSL-1.1 terms per the LICENSE published at that tag.

## Dependency licence gate

Every dependency — build, runtime, or dev — passes both gates below before it enters the project. The procedure for proposing one is in [`PROCESS.md`](../PROCESS.md); this section is the allow/reject rule that procedure enforces.

**Licence gate — accept:** Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause, MPL-2.0, LGPL-2.1 (as a separately-running service), PostgreSQL.

**Licence gate — reject:** AGPL (any version), BSL, BUSL (any version that is not a past version of OCU's own licence), SSPL, CC-NC, and any commercial-only or source-unavailable licence.

**Supply-chain gate.** A dependency must have at least one of: a published SBOM, a reproducible build, signed releases, or cosign-attested artifacts. A sole-maintainer npm/PyPI package with no provenance is rejected on this gate alone, regardless of licence.

When the choice is between a heavier, vendor- or foundation-backed, audited tool and a lighter sole-maintainer one, take the heavier one. OCU targets regulated enterprises; a lightweight-but-undocumented dependency loses the InfoSec review that gates the sale.

## Bundled vs not-bundled

Each accepted dependency is recorded as bundled or not-bundled when an ADR or component spec adopts it.

- **Bundled** — OCU ships the binary, image, or library as part of a release. OCU owns its CVE response, version pinning, vulnerability scanning, and SBOM entry.
- **Not bundled** — the customer provides it over a standard API (for example an IdP, a secret store, a SIEM, or a customer KMS). OCU documents the integration contract; the customer owns the lifecycle.

The Bill of Materials is the table of accepted dependencies with this flag. It is not pre-populated: a row is added when the ADR or component spec that adopts a dependency lands, so the bundled/not-bundled call is made with the rationale that needs it, not in advance.

| Dependency | Licence | Bundled | Adopted by |
|---|---|---|---|
| runc | Apache-2.0 | bundled | [ADR-0003](../adr/0003-sandbox-runtime-tier-ladder.md) |
| gVisor (`runsc`) | Apache-2.0 (per-file MIT/BSD) | bundled | [ADR-0003](../adr/0003-sandbox-runtime-tier-ladder.md) |
| Envoy | Apache-2.0 | bundled | [ADR-0005](../adr/0005-egress-credential-delivery-envoy-sds.md), [ADR-0006](../adr/0006-egress-forward-proxy-substrate.md) |
| `rclone` (in-guest mount client, `ocu-rclone-filestore`) | base MIT; binding chain go-fuse (BSD-3-Clause) / cgofuse (MIT) | bundled | [ADR-0015](../adr/0015-storage-decomposition-by-trust-plane.md) |
| OpenBao Transit (storage-credential ES256 signer: `ecdsa-p256`, `marshaling_algorithm=jws`) | MPL-2.0 (signer engine); the ~100-line OCU JWS assembler is FSL-1.1-Apache-2.0 library code | bundled (signer engine); not-bundled (issuer) | [ADR-0013](../adr/0013-storage-credential-custody.md) |

## Rejected dependencies

A rejection is first-class: recorded so it is not re-proposed. Each row names the reject reason and the path OCU takes instead. The adopting ADR re-verifies a row's licence fact against the dependency's own LICENSE before it cites the row.

| Dependency | Reason | Instead |
|---|---|---|
| HashiCorp Vault | BUSL — reject as a bundled dependency | OpenBao (MPL-2.0) bundled; Vault permitted only as a customer-provided drop-in |
| HashiCorp Boundary | BUSL (Community edition) | Customer-provided PAM/access plane; OCU stays a relying party |
| Teleport | AGPLv3 source + commercial-only Community binaries | Customer-provided access plane; OCU stays a relying party |
| Infisical (enterprise) | Core is MIT, but SSO/audit features are under a commercial licence | Treat as integrate-only; the audit/SSO features a regulated enterprise requires are behind the commercial gate |
| MinIO | AGPL community edition | Customer S3-compatible store; Ceph RGW as the reference object store |
| Zitadel (as primary IdP) | AGPL-3.0 | Keycloak (Apache-2.0) as the reference IdP relying-party target |
| Redpanda | BSL | NATS JetStream (Apache-2.0) for the event bus |
| mitmproxy / Squid ssl-bump (as the bump engine) | BSD / GPL-2.0+ — licence is not the blocker; adopting either as the egress bump engine drops the Envoy data plane (allow-list, OCSF audit, `ext_authz`) ADR-0006 placed there | Envoy data plane + a self-hosted SDS minting service for per-SNI leaves ([ADR-0007](../adr/0007-egress-auth-mechanism.md)); mitmproxy (BSD) recorded only as the fallback engine where the Envoy data plane is not needed |
| SPIRE (as the Storage-JWT issuer) | Cannot reproduce the scoped ES256 envelope OCU mints — SVID shape, not a `{filesystem_id + workspace + org}` claim set with the 3-axis `AuthorizationMetadata` and fixed no-refresh TTL ([ADR-0013](../adr/0013-storage-credential-custody.md)) | OpenBao Transit signer + OCU JWS assembler; customer OpenBao / Keycloak / KMS over the documented mint contract |
| GCP `signJwt` (IAM Credentials) | RS256-only and forces a Google `iss` + JWKS the backend origin must trust — wrong key type and trust anchor for the off-box issuer envelope | OpenBao Transit (`ecdsa-p256` / `jws`) as the reference signer; customer KMS as a drop-in over the mint contract |
| AWS STS as the storage-credential issuer | The killed SigV4 / `F8` lease-pull shape ([#205](https://github.com/Wide-Moat/open-computer-use/issues/205), [ADR-0005](../adr/0005-egress-credential-delivery-envoy-sds.md)) — a per-operation request signer, not a pre-issued scoped bearer; reintroduces an OCU minting/STS-delegator surface ADR-0013 removes | Pre-issued ES256 `Authorization: Bearer`, scope enforced at the backend origin; no OCU STS leg on the data path |
| cert-manager (as the JWT issuer) | An X.509 certificate authority, not a JWT signer — emits no `{filesystem_id + workspace + org}` bearer; mismatched primitive | OpenBao Transit signer; customer IdP / KMS over the mint contract |
| Third-party Vault / OpenBao JWT plugins (community auth-method and signing plugins) | Sole-maintainer, no provenance — fails the supply-chain gate regardless of licence | First-party OpenBao Transit `jws` marshaling on the bundled engine; no out-of-tree plugin on the signing path |
