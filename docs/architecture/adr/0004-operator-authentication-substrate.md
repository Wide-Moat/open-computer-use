<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-06-01
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
compliance-impact: [SOC2-CC6.1, ISO27001-A.8.2, DORA-Art.9, NYDFS-500.7, EU-AI-Act-Art.14]
license-impact: none
threat-mitigation-link: ../components/02-control-operator-api.md
---

Fixes how a human operator and an automated SOAR caller authenticate to the Control / operator API, and what that costs on the solo path. Audience: anyone touching operator auth, the kill switch, or SOAR integration.

# ADR-0004: Operator authentication substrate

## Status

`proposed`

## Context

The Control / operator API ([component 02](../components/02-control-operator-api.md)) is the privileged plane: it reaches the kill switch, the denylist authority, and tier admission. Two principals call it — a human operator and an automated SOAR responder — and the component marks operator-auth as `needs ADR` in its Boundaries, Operational concerns, and Open question #5 (tracked [#225](https://github.com/Wide-Moat/open-computer-use/issues/225)). This ADR closes that question.

The one-click solo install is an NFR-shaping invariant: the default deployment runs single-operator, no IdP, no KVM, and must not pay for a regulated enterprise's identity machinery to start. The substrate has to scale from that floor up to a customer with a federated identity provider and a PAM tool, without forking the contract.

Dual-control and break-glass stay out of scope. The kill switch is itself the single-operator emergency path, and accountability is already carried by the chain-linked audit emit before acknowledgement. The solo shelf has one operator, so two-person control cannot be a baseline.

## Decision

The Control / operator API authenticates a human operator and an automated SOAR caller against a two-shelf substrate — minimal shelf is a host-rooted local operator credential plus a signature-verified signed-webhook, full shelf makes OCU a relying-party to the customer IdP (OIDC + SCIM, PAM-JIT via SAML-asserted attributes) and a SPIFFE SVID workload identity for SOAR — with multi-party approval left as a post-v1 policy seam over the same audit set, and no break-glass or dual-control fixture added.

## Consequences

- Human identity, minimal shelf: a single host-rooted local operator credential, no IdP. Satisfies NFR-SEC-09 and NFR-COMP-29; preserves the zero-config solo path.
- Human identity, full shelf: OCU is a relying-party to the customer IdP — Keycloak/OIDC reference RP plus SCIM provisioning — with PAM just-in-time access driven by SAML-asserted attributes that integrate the customer PAM tool. The IdP and PAM tool are customer-provided, never bundled (NFR-COMP-29).
- SOAR machine identity, minimal shelf: signed-webhook plus admin API, the signature verified before any action per [component 02](../components/02-control-operator-api.md) (P2-R2), satisfying NFR-COMP-27.
- SOAR machine identity, full shelf: a SPIFFE SVID over mTLS, reusing the NFR-SEC-09 workload-identity floor. The per-boundary signer assignment and PKI tool pick are decided upstream by the PKI ADR tracked at [#152](https://github.com/Wide-Moat/open-computer-use/issues/152) ([`02-trust-boundaries.md`](../02-trust-boundaries.md) §8.1 names signer identity per boundary; the per-boundary signer table lands with that ADR); this ADR depends on it for the full-shelf signer and does not pick the PKI tool.
- A privileged call touches the Egress trust-edge ([component 06](../components/06-egress-trust-edge.md)) as denylist authority and emits to the Audit pipeline ([component 07](../components/07-audit-pipeline.md)); the emit-before-acknowledge ordering and fail-closed posture are governed by NFR-SEC-45, the kill-switch latency by NFR-SEC-01 and its under-saturation bound NFR-SEC-55.
- Multi-party approval is a named post-v1 policy seam layered over the NFR-SEC-45 audit set; a customer whose NIST SP 800-53 AC-3(2) baseline requires it selects it then. Nothing is built for it now.
- [Component 02](../components/02-control-operator-api.md) moves its `adr` reference from `[]` to `[0004]`.

## Alternatives considered

- Bundle Teleport as the access plane — rejected: AGPLv3 plus commercial-only binaries fail the license gate (05-licensing-posture.md reject-table).
- Bundle HashiCorp Boundary as the access plane — rejected: BUSL fails the license gate (05-licensing-posture.md reject-table).
- Add a break-glass credential alongside the operator credential — rejected: the kill switch is already the single-operator emergency path and the audit emit already carries accountability, so a third fixture is ceremony.
- Assert two-person dual-control as the v1 baseline — rejected: the solo shelf has one operator, so it cannot be a baseline; it lands as the post-v1 multi-party seam instead.

## Compliance impact

SOC2-CC6.1 and ISO 27001 A.8.2 (privileged-access control), DORA Art. 9 (protection and prevention), NYDFS 500.7 (access privileges), EU AI Act Art. 14 (human oversight — the kill switch is the oversight control).

## License impact

None. OCU stays a relying-party; Keycloak/OIDC and SPIRE on the full shelf are integrated, not bundled by this ADR; the customer PAM tool is never bundled.

## Threat mitigation

Mitigates the P2 attack-path rows in [component 02](../components/02-control-operator-api.md): unauthenticated or spoofed access to the privileged plane, and an unverified SOAR caller acting on the denylist or kill switch.
