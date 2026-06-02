<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-06-02
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
compliance-impact: [SOC2-CC6.1, NYDFS-500.15, DORA-Art.28]
license-impact: none
threat-mitigation-link: ../06-threat-model.md
---

Fixes how the Egress trust-edge attributes an outbound connection to the session that owns it, and scopes that attribution to deny decisions only. Audience: anyone wiring or auditing how per-session egress policy reaches the edge.

# ADR-0008: Session-to-egress connection attribution

## Status

`proposed`

## Context

[ADR-0007](0007-egress-auth-mechanism.md) fixed that the edge injects the upstream credential gated on a credential the request *presents*, never on its network origin — the forbidden P6-E2 pattern is "inject because traffic came from sandbox X". But per-session deny policy still has to reach the edge: the kill-switch denylist ([component 02](../components/02-control-operator-api.md)), the downloadable-deny ([NFR-SEC-73](../manifesto/02-nfrs.md)), and per-session rate limits all need the edge to know *which session* a connection belongs to. Nothing decided how the edge attributes a raw outbound connection to a session, while [NFR-SEC-43](../manifesto/02-nfrs.md) requires that identity be host-attested (a guest-supplied identity is a hint, never authoritative) and the shared-kernel `runc` tier has no hypervisor context id to lean on. The forcing constraint is the one-click solo install ([NFR-FLEX-15](../manifesto/02-nfrs.md)): the default attribution must hold on `runc` + `docker-compose` with no workload-identity control plane.

## Decision

We will attribute an outbound connection to its owning session by a host-attested identity the guest cannot forge, substituted per runtime tier on the [NFR-SEC-43](../manifesto/02-nfrs.md) ladder — host-created network namespace plus host kernel peer-credentials of the per-session sandbox principal on `runc`/gVisor (the v1 default, no context id), and the hypervisor-assigned vsock context id on the microVM tier (post-v1) — and this attribution scopes deny and rate decisions only; authorization to inject the upstream credential stays gated on the presented scoped credential per [ADR-0007](0007-egress-auth-mechanism.md), never on the attributed origin.

| Runtime tier ([ADR-0003](0003-sandbox-runtime-tier-ladder.md)) | Attribution key (deny-scope only) |
|---|---|
| `runc` — minimal-shelf default, v1 GA | Host-created per-session netns/veth arrival identity, cross-checked against host kernel peer-credentials of the sandbox principal. No context id; multi-tenant agent execution is already forbidden here ([NFR-SEC-38](../manifesto/02-nfrs.md)). |
| gVisor — v1 GA hardened | Host kernel peer-credentials of the sandbox principal at the host-side socket. Still no context id. |
| microVM — post-v1 default | Hypervisor-assigned vsock context id; the guest owns the virtual device, not the id, so it cannot forge it. |

## Consequences

- The attributed session identity drives **deny** at the Egress trust-edge ([component 06](../components/06-egress-trust-edge.md)): the kill-switch denylist refuses a revoked session, downloadable-deny ([NFR-SEC-73](../manifesto/02-nfrs.md)) drops an egress-eligible artifact, and per-session rate limits apply. It is never the injection trigger — that is the line ADR-0007 draws, restated here so the binding is not re-read as "attributed-to-session-X → inject".
- Component 06 records this ADR in its `adr:` front-matter (`[0005, 0006, 0007]` → `[0005, 0006, 0007, 0008]`); the sandbox-listener face and the denylist-at-edge invariant now have a named attribution key.
- Positive: the default holds zero-config on `runc` + `docker-compose` with no SPIFFE issuer and no context id ([NFR-FLEX-15](../manifesto/02-nfrs.md)); the key is host-attested, so a root guest re-IPing itself does not change which host-created interface its packets egress through ([NFR-SEC-43](../manifesto/02-nfrs.md)).
- Negative: on `runc`/gVisor the key is a host-side network fact, not a cryptographic identity, so it carries no standing across a host boundary; it is sound only because the host owns interface creation and the peer-credential view. The microVM context id is stronger and becomes the default when that tier ships — named now so no re-decision is needed.
- Neutral: the binding reuses the existing [NFR-SEC-43](../manifesto/02-nfrs.md)/[NFR-SEC-76](../manifesto/02-nfrs.md) substitution ladder rather than adding a mechanism; the per-tenant boundary it must not let a guest cross is [NFR-SEC-22](../manifesto/02-nfrs.md).

## Alternatives considered

- **Source IP as the attribution key** — rejected: a source address is guest-settable, a root guest re-IPs within its segment, and keying any decision on it re-introduces the P6-E2 network-origin pattern. Source IP is at most a hint cross-checked against the host-attested key ([NFR-SEC-43](../manifesto/02-nfrs.md)).
- **mTLS / SPIFFE SVID as the universal key** — rejected as the default: it requires a trust-domain control plane the one-click solo path cannot carry ([NFR-FLEX-15](../manifesto/02-nfrs.md)) and makes the guest hold a key, against [NFR-SEC-23](../manifesto/02-nfrs.md); it also conflates attribution with the injection trigger ADR-0007 forbids. Recorded as the full-shelf, customer-PKI option where a workload-identity plane already runs.
- **vsock context id for every tier** — rejected as the default: the minimal-shelf default tier (`runc`) has no context id at all — the shared-kernel hole [NFR-SEC-43](../manifesto/02-nfrs.md) names. Adopted as the microVM-tier key only.
- **A single tier-independent mechanism** — rejected: the strongest host-attested key is unavailable precisely on the default tier, so a tiered binding keyed to the [ADR-0003](0003-sandbox-runtime-tier-ladder.md) ladder is the honest answer.

## Compliance impact

- `SOC2-CC6.1`: per-session deny reaches the boundary on a host-attested key, so a revoked or rate-limited session is enforced at the egress point — the access-control story for outbound traffic.
- `NYDFS-500.15` / `DORA-Art.28`: the outbound leg's session attribution is host-derived and audited, recording which session each authenticated outbound flow belongs to.

## License impact

None. The mechanism is host kernel namespaces and peer-credentials on the default tier and hypervisor vsock on microVM; no new bundled dependency.

## Threat mitigation

Tightens the deny side behind P6-E2 in [the threat model](../06-threat-model.md): a compromised guest cannot present another session's host-attested identity, so it cannot borrow a co-tenant's egress policy scope. Per-action authorization on the attributed session — what that session may do to which object — is separate and tracked at [#187](https://github.com/Wide-Moat/open-computer-use/issues/187); whether a multi-tenant gVisor deployment needs a stronger-than-peer-credential key on the shared edge is the residual at [#160](https://github.com/Wide-Moat/open-computer-use/issues/160).
