<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-06-01
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
compliance-impact: [SOC2-CC6.6, SOC2-CC6.7, NYDFS-500.15, DORA-Art.9, EU-AI-Act-Art.12]
license-impact: Envoy Apache-2.0; clears the allow-list, bundled by this ADR
threat-mitigation-link: ../components/06-egress-trust-edge.md
---

Picks the forward-proxy substrate for the Egress trust-edge and scopes it to the v1 deny-by-default floor. Audience: anyone wiring or auditing the sandbox's outbound path.

# ADR-0006: Egress forward-proxy substrate

## Status

`proposed`

## Context

The Egress trust-edge ([component 06](../components/06-egress-trust-edge.md)) is the sandbox's sole outbound network path. v1 ships one capability there: a deny-by-default destination allow-list applied at connect time on resolved-IP and SNI, with a machine-parseable reason on every block. That floor must run from a single `docker-compose up` with no certificate authority, no IdP, and no policy engine — the one-click solo install is an NFR-shaping invariant.

The component spec carries no substrate decision (`adr: []`) and an open question on which proxy provides it (open-Q#2). A purpose-built forward proxy supplies connect-time allow-listing, a controllable resolver, and an external-authorization seam. The risk is over-buying: pulling in TLS termination, dynamic config distribution, or an inline content-inspection path that the v1 floor does not need and that would tax the solo default.

MITM termination — per-SNI on-the-fly leaf certificates — is a separate, deferred decision (component 06 open question #2, the MITM-termination half) and is not in scope here.

## Decision

The Egress trust-edge runs an Apache-2.0/MIT/BSD forward proxy — Envoy is the lead candidate (Apache-2.0, native connect-time SNI/resolved-IP filtering and an `ext_authz`/`ext_proc` seam), with the final binary left to the component spec — configured to the v1 floor only: a deny-by-default allow-list at connect time on resolved-IP + SNI, a proxy-owned resolver carrying the mandatory deny-set, a machine-parseable `x-deny-reason` on block, one external-authorization seam whose default backend is a static allow-list, and a per-upstream-leg credential-origination hook.

## Consequences

- Component 06 records this ADR in its `adr:` front-matter (`[]` → `[0006]`). The allow-list at connect time satisfies NFR-SEC-08 and NFR-SEC-17; the proxy-owned resolver enforces NFR-SEC-12's mandatory deny-set; the structured block carries the `x-deny-reason` vocabulary the spec already defines. This ADR does not restate those NFRs.
- The `ext_authz`/`ext_proc` seam ships with a static allow-list as its default backend — the solo path configures no policy engine. OPA as a full-shelf backend behind the same seam is deferred, not v1.
- The credential-origination hook is the seam where the edge attaches the upstream authorization received over Envoy SDS ([ADR-0005](0005-egress-credential-delivery-envoy-sds.md)); it fires only on a leg that needs it, never on the transparent default route. No CA, cert-issuer, ICAP, or credential wiring lands on the transparent path.
- The broker backend leg ([component 04](../components/04-storage-broker.md), F10) traverses the proxy as one allow-list destination with no TLS termination, so the broker-signed request is forwarded byte-intact per NFR-SEC-25.
- Every allow and every deny is emitted as an OCSF event through the Audit pipeline ([component 07](../components/07-audit-pipeline.md)); the payload-independent exfil tripwire (NFR-SEC-57) runs on this path with no CA. This ADR adds no requirement to either.
- The egress posture stays mode-selectable per NFR-FLEX-15: this ADR fixes the transparent default; MITM-mode origination (NFR-SEC-30, NFR-SEC-37, NFR-SEC-50) and DLP/ICAP as a MITM config (NFR-COMP-28) ride the same substrate but are decided in the deferred MITM-termination ADR (component 06 open question #2).
- xDS dynamic config and per-node sharding ([#175](https://github.com/Wide-Moat/open-computer-use/issues/175)) are deferred seams this ADR names but does not design.

## Alternatives considered

- **Squid (GPL-2.0+)** — mature forward proxy with SslBump for the later MITM leg; clears the allow-list, but a bundled GPL binary triggers the distribution review noted in [`manifesto/05-licensing-posture.md`](../manifesto/05-licensing-posture.md), and its config model fits the deny-by-default floor less directly than Envoy's filter chain.
- **HAProxy (GPL-2.0+ / LGPL)** — passes the allow-list and handles SNI routing, but bundling carries the same GPL distribution review and it lacks a first-class external-authorization seam equivalent to `ext_authz`.
- **Hand-rolled CONNECT proxy** — a minimal Go/Rust proxy owned end to end. Rejected: re-implementing resolver pinning, filter chains, and an `ext_authz` seam is net-new attack surface a bank InfoSec review would not credit against a vendor-backed proxy.

## Compliance impact

- `SOC2-CC6.6` / `SOC2-CC6.7`: the deny-by-default allow-list and structured deny reason are the boundary-protection and transmission controls for outbound flows.
- `NYDFS-500.15`: outbound destinations are gated and logged, supporting the access-and-monitoring controls.
- `DORA-Art.9`: the edge is the network-segmentation and traffic-control measure for the sandbox's outbound leg, recordable per deployment.
- `EU-AI-Act-Art.12`: allow/deny events emitted to the Audit pipeline contribute to the automatic record-keeping required of high-risk systems.

## License impact

This is the adopting ADR for the forward proxy: Envoy enters the Bill of Materials in [`manifesto/05-licensing-posture.md`](../manifesto/05-licensing-posture.md) as bundled (Apache-2.0), clearing the licence gate. The Squid and HAProxy alternatives clear the same gate, but a bundled GPL binary triggers the distribution review that file records; neither is bundled by this ADR.

## Threat mitigation

The deny-by-default floor is the v1 realization of the egress controls in [`06-egress-trust-edge.md`](../components/06-egress-trust-edge.md) (P6 rows): connect-time allow-listing on resolved-IP + SNI, the proxy-owned resolver's mandatory deny-set, and the payload-independent exfil tripwire (NFR-SEC-57) that runs in both postures without a CA. The credential-origination hook keeps the upstream authorization off the guest, attached over Envoy SDS ([ADR-0005](0005-egress-credential-delivery-envoy-sds.md)) only on the leg that needs it.
