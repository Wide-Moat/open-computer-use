<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-06-01
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
compliance-impact: [SOC2-CC6.1, ISO27001-A.8.24, DORA-Art.9, DORA-Art.28, NYDFS-500.15, PCI-DSS-Req.3]
license-impact: none
threat-mitigation-link: ../02-trust-boundaries.md#4-per-tenant-isolation-menu
---

Fixes the secret-store substrate behind Credential custody and the abstraction that lets a customer's audited store own the unseal, rotation, lease, and key-escrow lifecycle. Audience: anyone touching Credential custody or wiring an external secret store.

# ADR-0005: SecretsProvider substrate behind credential custody

## Status

`proposed`

## Context

Credential custody ([component 03](../components/03-credential-custody.md)) holds the upstream secrets an agent session needs and injects them at the Egress trust-edge so the guest never sees them. Behind custody sits a store question: where do those secrets rest, and who owns the unseal, rotation, lease, and key-escrow lifecycle of that store.

A bank already runs an audited secret store (OpenBao, a customer KMS, a Vault drop-in) with BYOK, seal-wrap, and dynamic-secret issuance under its own InfoSec review. A solo operator runs none of that and must not be made to: the one-click solo install is an NFR-shaping invariant — single-operator, no IdP, no stateful key infrastructure, `docker-compose up` stays trivial. Bundling a stateful secret store as a GA requirement would force OCU to own a CVE and seal-unseal lifecycle for software the bank already operates, and tax the solo path with infrastructure it does not need.

## Decision

Credential custody resolves secrets through a `SecretsProvider` abstraction with two backends. The bundled default is a host-local AEAD-encrypted file, read and injected at the Egress edge, with no stateful service, no lease lifecycle, and no HSM concept. The not-bundled adapter is a contract through which a customer's audited store owns BYOK, seal-wrap, and dynamic-secret issuance. OCU mints nothing and bundles no stateful secret store in v1; the provider return type carries an optional lease-TTL field so a lease-returning backend plugs in post-v1.

## Consequences

- Credential custody ([component 03](../components/03-credential-custody.md)) records `0005` in its `adr:` front-matter and owns the `SecretsProvider` boundary; custody stays domain-specific to agent-session upstream creds and does not collapse into a generic secrets manager, since the external store is that generic manager underneath. This closes custody open-Q#2 ([#169](https://github.com/Wide-Moat/open-computer-use/issues/169)).
- The bundled host-local AEAD default keeps the solo path zero-config: no stateful store, no unseal step, no key infrastructure. The minimal-shelf long-lived broker credential it holds is admissible only under the conditions held by NFR-SEC-60; the custody process memory is not a secret store against host-root, per NFR-SEC-59.
- The external-store path carries the lifecycle the bank already runs: the full-shelf root stays HSM-resident under NFR-FLEX-04, dynamic-secret STS issuance and seal-wrap belong to the customer store, and the adapter consumes them. This ADR adds no requirement to NFR-SEC-23, NFR-SEC-25, NFR-SEC-29, or NFR-SEC-30.
- The Storage broker ([component 04](../components/04-storage-broker.md)) reuses the same backend-credential discipline (NFR-SEC-23); the Egress trust-edge ([component 06](../components/06-egress-trust-edge.md)) consumes the provider as the F8 lease-pull consumer and stays backend-agnostic, so a file default and a lease-returning store present the same edge contract.
- Provider lifecycle transitions are audited through the Audit pipeline ([component 07](../components/07-audit-pipeline.md)) split by initiator: a system-initiated per-session lease issue under NFR-SEC-72, an operator-forced mint, rotate, or revoke under NFR-SEC-45. For the solo file default the events write locally and no external sink fires.
- External-store adapter dialects (OpenBao/KMS), lease-TTL minting, and FIPS-140-3 seal validation are deferred seams this ADR names but does not design; the product choice for a chosen store opens under [#169](https://github.com/Wide-Moat/open-computer-use/issues/169). Custody cardinality is decided separately ([#175](https://github.com/Wide-Moat/open-computer-use/issues/175)) and is out of scope here.

## Alternatives considered

- **Bundle OpenBao plus an OCU-built STS minter and seal-wrap** — rejected on the dependency-policy bundling rule ([`manifesto/05-licensing-posture.md`](../manifesto/05-licensing-posture.md)): OCU would own a CVE and seal-unseal lifecycle for a store the customer already runs.
- **HashiCorp Vault bundled** — rejected as bundled (BUSL fails the licence gate, per the reject-table); admissible only as a customer-provided drop-in behind the external-store adapter.
- **Collapse custody into a generic secrets manager** — rejected because the external store is already the generic manager, and a generic surface drops the agent-session scoping that custody enforces.

## Compliance impact

- `SOC2-CC6.1` / `ISO27001-A.8.24`: secret confidentiality and key use are realized by the AEAD default or delegated to the customer store; the adapter records which path is active.
- `DORA-Art.9` (4): the encryption-at-rest and key-management posture of the active provider is declared and auditable.
- `DORA-Art.28` (4): the secret-store substrate per deployment is recordable in the register of information.
- `NYDFS-500.15`: encryption of nonpublic information at rest is satisfied by the AEAD default or the customer store.
- `PCI-DSS-Req.3`: stored-credential protection is met by the active provider; dynamic-secret issuance, where present, belongs to the external store.

## License impact

The bundled default is a host-local AEAD-encrypted file built on an allow-list-clean primitive library; the specific library pick is a [component 03](../components/03-credential-custody.md) detail, not this decision. No stateful secret store is bundled, so no store row enters the Bill of Materials in [`manifesto/05-licensing-posture.md`](../manifesto/05-licensing-posture.md).

## Threat mitigation

The egress-injection custody model in [`02-trust-boundaries.md`](../02-trust-boundaries.md#4-per-tenant-isolation-menu) §4 keeps the upstream secret out of the guest; the `SecretsProvider` boundary preserves that whether the secret rests in the AEAD file default or in a customer store, since both inject only at the Egress edge. The custody-memory-versus-host-root boundary is held by NFR-SEC-59; the minimal-shelf credential conditions by NFR-SEC-60.
