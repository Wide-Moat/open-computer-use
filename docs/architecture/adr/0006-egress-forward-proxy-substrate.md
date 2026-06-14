<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-06-14
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
amended-by: [0016]
compliance-impact: [SOC2-CC6.6, SOC2-CC6.7, NYDFS-500.15, DORA-Art.9, EU-AI-Act-Art.12]
license-impact: Envoy Apache-2.0; clears the allow-list, bundled by this ADR
threat-mitigation-link: ../components/06-egress-trust-edge.md
---

Picks Envoy as the forward-proxy substrate for the Egress trust-edge. Audience: anyone wiring or auditing the sandbox's outbound path.

# ADR-0006: Egress forward-proxy substrate

## Status

`proposed`

Amended by [ADR-0016](0016-egress-baseline-inspection-hop-backend-scope.md): the deny-by-default destination allow-list this ADR fixed as the v1 floor is now optional hardening, not the baseline. The v1 baseline is a single TLS-terminating inspection hop with no host allow-list. The substrate choice below (Envoy) stands; read every "deny-by-default floor" claim as the optional-hardening rung.

## Context

The Egress trust-edge ([component 06](../components/06-egress-trust-edge.md)) is the sandbox's sole outbound network path. It needs a forward proxy that supplies connect-time destination control on resolved-IP and SNI, a controllable resolver, and an external-authorization seam. The proxy must run from a single `docker-compose up` with no IdP and no policy engine — the one-click solo install is an NFR-shaping invariant.

The component spec carried no substrate decision (`adr: []`) and an open question on which proxy provides it (open-Q#2). At the time of this ADR a deny-by-default destination allow-list was taken as the v1 floor; [ADR-0016](0016-egress-baseline-inspection-hop-backend-scope.md) later re-scoped that allow-list to optional hardening and made a single TLS-terminating inspection hop the baseline. The substrate must serve both: connect-time allow-listing when the hardening is on, and TLS termination at the baseline.

MITM termination — the per-host leaf certificates the baseline hop presents — is decided in [ADR-0007](0007-egress-auth-mechanism.md) on the same Envoy substrate. This ADR fixes only the forward-proxy substrate.

## Decision

The Egress trust-edge runs Envoy (Apache-2.0): native TLS termination, connect-time SNI/resolved-IP filtering, an `ext_authz`/`ext_proc` seam, and a per-upstream-leg credential-origination hook. The baseline configuration terminates outbound TLS at one hop with a proxy-owned resolver carrying the mandatory deny-set. The deny-by-default allow-list at connect time on resolved-IP + SNI, the machine-parseable `x-deny-reason` on block, and the external-authorization seam with a static-allow-list backend are the optional-hardening configuration on the same substrate ([ADR-0016](0016-egress-baseline-inspection-hop-backend-scope.md)).

## Consequences

- Component 06 records this ADR in its `adr:` front-matter (`[]` → `[0006]`). The proxy-owned resolver enforces NFR-SEC-12's mandatory deny-set at the baseline. The connect-time allow-list (NFR-SEC-08, NFR-SEC-17) and its `x-deny-reason` vocabulary are the optional-hardening rung; this ADR does not restate those NFRs.
- The `ext_authz`/`ext_proc` seam ships with a static allow-list as its default backend under the hardening rung — the solo baseline configures no policy engine. OPA as a full-shelf backend behind the same seam is deferred, not v1.
- The credential-origination hook is the seam where the edge attaches the upstream authorization received over Envoy SDS ([ADR-0005](0005-egress-credential-delivery-envoy-sds.md)); it fires only on a leg that needs it, never on the transparent default route. No CA, cert-issuer, ICAP, or credential wiring lands on the transparent path.
- The storage data leg is the in-guest mount client dialling the object-store service's `service_url` guest-out (F7a, riding the single egress path F8) over this same hop; the hop terminates TLS and forwards the static `Authorization: Bearer` Storage-JWT unmodified, with scope enforced at the storage engine, not here. There is no storage-dedicated lane and no signed byte-intact backend leg on the edge — that retired model is amended by [ADR-0016](0016-egress-baseline-inspection-hop-backend-scope.md). F9 is the intra-deployment Web UI → object-store service seam ([component 08](../components/08-web-ui.md)), not an edge leg.
- Every allow and every deny is emitted as an OCSF event through the Audit pipeline ([component 07](../components/07-audit-pipeline.md)); the payload-independent exfil tripwire (NFR-SEC-57) runs on this path with no CA. This ADR adds no requirement to either.
- The egress posture is the NFR-FLEX-15 ladder: this ADR fixes the forward-proxy substrate every rung shares; the baseline TLS-terminating hop, the allow-list hardening, credential origination (NFR-SEC-30, NFR-SEC-37, NFR-SEC-50), and DLP/ICAP config (NFR-COMP-28) all ride the same substrate and are decided in [ADR-0007](0007-egress-auth-mechanism.md) and [ADR-0016](0016-egress-baseline-inspection-hop-backend-scope.md) (which resolve component 06 open question #2).
- xDS dynamic config and per-node sharding ([#175](https://github.com/Wide-Moat/open-computer-use/issues/175)) are deferred seams this ADR names but does not design.

## Alternatives considered

- **Squid (GPL-2.0+)** — mature forward proxy with SslBump for the later egress-wide-bump leg; clears the allow-list, but a bundled GPL binary triggers the distribution review noted in [`manifesto/05-licensing-posture.md`](../manifesto/05-licensing-posture.md), and its config model fits the deny-by-default floor less directly than Envoy's filter chain.
- **HAProxy (GPL-2.0+ / LGPL)** — passes the allow-list and handles SNI routing, but bundling carries the same GPL distribution review and it lacks a first-class external-authorization seam equivalent to `ext_authz`.
- **Hand-rolled CONNECT proxy** — a minimal Go/Rust proxy owned end to end. Rejected: re-implementing resolver pinning, filter chains, and an `ext_authz` seam is net-new attack surface a regulated-enterprise InfoSec review would not credit against a vendor-backed proxy.

## Compliance impact

- `SOC2-CC6.6` / `SOC2-CC6.7`: the single TLS-terminating hop is the boundary-protection and transmission control for outbound flows; the deny-by-default allow-list and structured deny reason add destination restriction under the hardening rung.
- `NYDFS-500.15`: outbound destinations are gated and logged, supporting the access-and-monitoring controls.
- `DORA-Art.9`: the edge is the network-segmentation and traffic-control measure for the sandbox's outbound leg, recordable per deployment.
- `EU-AI-Act-Art.12`: allow/deny events emitted to the Audit pipeline contribute to the automatic record-keeping required of high-risk systems.

## License impact

This is the adopting ADR for the forward proxy: Envoy enters the Bill of Materials in [`manifesto/05-licensing-posture.md`](../manifesto/05-licensing-posture.md) as bundled (Apache-2.0), clearing the licence gate. The Squid and HAProxy alternatives clear the same gate, but a bundled GPL binary triggers the distribution review that file records; neither is bundled by this ADR.

## Threat mitigation

The substrate realizes the egress controls in [`06-egress-trust-edge.md`](../components/06-egress-trust-edge.md) (P6 rows): the baseline single TLS-terminating hop, the proxy-owned resolver's mandatory deny-set, and the payload-independent exfil tripwire (NFR-SEC-57); connect-time allow-listing on resolved-IP + SNI rides the hardening rung. The credential-origination hook keeps the upstream authorization off the guest, attached over Envoy SDS ([ADR-0005](0005-egress-credential-delivery-envoy-sds.md)) only on the leg that needs it.
