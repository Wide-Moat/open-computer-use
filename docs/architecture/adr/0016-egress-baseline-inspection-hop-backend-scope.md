<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-06-14
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
amends: [0006, 0007, 0011]
compliance-impact: [SOC2-CC6.1, SOC2-CC6.6, NYDFS-500.15, DORA-Art.28, DORA-Art.30, EU-AI-Act-Art.15]
license-impact: none — the hop is the Envoy already bundled by ADR-0006; the reversal removes baseline build surface (the allow-list resolver and structured-deny vocabulary move to optional hardening)
threat-mitigation-link: ../components/06-egress-trust-edge.md
---

Sets the v1 egress baseline to a single TLS-terminating inspection hop with no host allow-list and no egress-side scope, and moves scope enforcement to the backend origin. Audience: anyone wiring or auditing how a sandbox reaches an authenticated upstream or its storage backend.

# ADR-0016: Egress baseline — one inspection hop, backend-enforced scope

## Status

`proposed`

This ADR amends the egress floor set by [ADR-0006](0006-egress-forward-proxy-substrate.md); it lands in the same coordinated package as the storage-custody recut ([ADR-0013](0013-storage-credential-custody.md), [ADR-0014](0014-storage-transport-tier-universal-network-leg.md), [ADR-0015](0015-storage-decomposition-by-trust-plane.md)).

## Context

The v1 baseline reproduces the egress shape the owner ruled to reproduce. That shape is a single TLS-terminating inspection hop: it terminates outbound TLS for every host, presents a per-host leaf from a gateway-side CA, and forwards to origin. It carries no host allow-list — arbitrary hosts and plaintext HTTP pass through, and the storage backend host holds no privilege at the hop. It re-credentials nothing — the client `Authorization: Bearer` passes through after inspection. It emits no structured deny — a blocked non-`:443` port times out, a non-routable host is refused at the TCP layer. Scope is enforced at the backend: a foreign `filesystem_id` (or `memory_store_id`) presented with the same JWT is rejected by the origin (HTTP 401), not by the hop. "One governed outbound path, no bypass" holds by a single default route plus block-local-connections plus the absence of a second socket — not by a deny-by-default allow-list.

Current canon sets the opposite as baseline: [ADR-0006](0006-egress-forward-proxy-substrate.md) fixes a deny-by-default allow-list floor, [NFR-SEC-17](../manifesto/02-nfrs.md) the allow-list-on-connect mechanism with a structured `x-deny-reason`, [ADR-0011](0011-storage-egress-lane.md) a no-TLS-termination storage lane, and [NFR-SEC-16/23/27/29](../manifesto/02-nfrs.md) and [component-06](../components/06-egress-trust-edge.md) the egress-side scope. That is a deviation from the shape ruled to reproduce, and it is named as such below (anti-recurrence rule 5). A second inspection CA exists in the reference for an unrelated, unmodelled purpose; this ADR scopes the baseline to the single egress-gateway-CA chain and does not assume the second chain is intentionally dropped (see Open questions).

## Decision

We will set the v1 egress baseline to a single TLS-terminating inspection hop with no host allow-list and no egress-side scope, enforce scope at the backend origin (it validates the `filesystem_id` / `memory_store_id` JWT claim), and re-classify the prior deny-by-default-allow-list + egress-side-scope + structured-deny model as a named optional hardening on the same hop, because the baseline must reproduce the reference and the stricter posture is a deliberate addition OCU layers on top, not the reference itself.

| Property | Baseline (v1) | Optional hardening |
|---|---|---|
| Destination policy | none — any host reachable through the one hop | deny-by-default allow-list (resolved-IP + SNI) |
| TLS | terminated at the hop, per-host leaf from the gateway-side CA, re-originated to origin | unchanged |
| Credential at the hop | client Bearer passes through unmodified; no re-credentialing | unchanged |
| Scope enforcement | backend origin validates the JWT claim; mismatch → 401 from origin | egress-side per-destination / per-claim scope at the hop |
| Deny signal | none — blocked port times out, non-routable refused at TCP | structured `x-deny-reason` vocabulary on the hop |
| No-bypass guarantee | single default route + block-local-connections + no second socket | unchanged |

"Governed" means one TLS-inspected hop with no second outbound socket, not a deny-by-default allow-list. The optional hardening is configuration on the same hop, switched on per deployment; the baseline path runs with it off.

**Two distinct SDS surfaces — do not conflate.** The inspection leaf is the per-host TLS certificate the hop presents while terminating outbound TLS, signed from the gateway-side inspection CA. The **upstream-credential SDS source** ([ADR-0005](0005-egress-credential-delivery-envoy-sds.md)) is unrelated: there Envoy fetches the upstream authorization from a static file or a customer store and OCU mints nothing. The leaf is the inspection certificate; the credential source delivers the upstream bearer.

The inspection leaf's source is mode-dependent, and v1 needs no OCU code for it. Stock Envoy distributes and rotates an existing secret over SDS but never generates a keypair or signs a CSR on the fly, so a non-enumerable destination set (CDN shards, per-tenant subdomains) would need an OCU per-SNI minter — a gRPC `SecretDiscoveryService` that stamps a leaf for the requested SNI from the CA key ([ADR-0007](0007-egress-auth-mechanism.md)). The v1 destination set is enumerable (the single LLM apex at the baseline, an explicit allow-list under the hardening), so the leaves are **pre-minted out of band from the inspection CA and served over Envoy-native file SDS — zero OCU minter code on the data path**. The dynamic per-SNI minter is specified for the non-enumerable case but **not instantiated at v1 GA**. The baseline hop terminates TLS with a pre-minted leaf and forwards the client bearer untouched; it engages no upstream-credential injection unless a deployment configures one.

## Consequences

- Positive: the v1 egress reproduces the reference, so a session that behaves there behaves here — the reproduction target is met without a divergence to explain on the first InfoSec read.
- Positive: the baseline drops build surface. The allow-list resolver, the SNI pre-filter as a mandatory drop, and the `x-deny-reason` vocabulary become optional-hardening config rather than baseline code, and the one-click solo path ([NFR-FLEX-15](../manifesto/02-nfrs.md)) runs with one default route and a pre-minted inspection leaf served over Envoy-native file SDS — no OCU minter code on the v1 data path.
- Positive: backend-enforced scope means a leaked guest JWT cannot reach another `filesystem_id` even if the hop is permissive — the blast radius is one session's own scope for the token TTL, set by the origin, independent of the hop. Custody of that JWT (signing key off-box at a host-side issuer, control plane delivers, guest forwards a scoped pre-signed bearer) is set by [ADR-0013](0013-storage-credential-custody.md); this ADR governs the path that JWT travels, not its issuance.
- Negative: with no baseline allow-list, the permissive hop reaches arbitrary hosts and plaintext HTTP. Content-blind exfil to an unconfigured destination is not denied at the baseline; it is bounded only by the single-hop inspection and the payload-independent tripwire. A deployment that needs destination restriction enables the allow-list hardening — named, not silent.
- Negative: with no structured deny at the hop, a baseline block surfaces as a timeout or TCP refusal, not a machine-parseable reason. Audit of a baseline denial records the connect failure, not an `x-deny-reason`. The hardening restores the structured deny where a deployment needs it.
- Neutral: scope denials are origin-authored JSON bodies, observable in the audit stream as upstream responses, not as hop-authored deny events — the audit contract ([08-contracts.md](../08-contracts.md) §1) records the hop's allow/observe events and the origin's response, not a hop scope-deny.
- This ADR amends [component-06](../components/06-egress-trust-edge.md) (baseline = permissive inspection hop; allow-list / structured-deny invariants move under the hardening), [ADR-0006](0006-egress-forward-proxy-substrate.md) (the deny-by-default allow-list floor it fixes is no longer the baseline, only the hardening rung), [ADR-0007](0007-egress-auth-mechanism.md) (edge-inject and the leaf-minter ride the hardening rung, not a baseline injection floor), and [ADR-0011](0011-storage-egress-lane.md) (the storage lane's "no TLS termination, allow-list-only" clause is false to the reference — the hop terminates TLS and there is no per-request signature to preserve). It re-anchors NFR-SEC-16/17/23/27/29 (see Compliance impact); the NFR re-anchor lands in the same package.

## Alternatives considered

- **Keep the deny-by-default allow-list as the baseline (current canon).** Rejected: it diverges from the reference shape the owner ruled to reproduce — the reference hop carries no host allow-list and lets arbitrary hosts and plaintext through. Holding the stricter posture as the baseline silently differs from the reproduction target, which anti-recurrence rule 5 forbids; the deviation is the hardening, not the base. The allow-list survives as the named optional hardening, so the capability is not lost — only its place in the ladder changes.
- **Enforce scope at the egress hop (egress-side `filesystem_id` / `memory_store_id` binding).** Rejected: the reference enforces scope at the backend origin — the hop is claim-blind and the origin returns the 401 on a foreign scope. Egress-side scope is the hardening, not the base; making it the baseline both diverges from the reference and duplicates the origin's authority at the hop, widening the hop's responsibility for no baseline gain. A deployment that wants defence-in-depth enables egress-side scope as the named hardening.

## Compliance impact

- `SOC2-CC6.1` / `SOC2-CC6.6`: boundary protection rests on the single governed hop and the no-second-socket guarantee; access control to a storage scope is the backend origin's claim check, recorded as the evidence path for scope enforcement.
- `NYDFS-500.15`: traffic is TLS-terminated and re-originated at the one hop; in-transit confidentiality holds on both legs at the baseline.
- `DORA-Art.28` / `DORA-Art.30` / `EU-AI-Act-Art.15`: the outbound path is a single named mediation point, and per-scope authorization is the backend origin's documented control — the third-party-arrangement and accuracy/cybersecurity evidence names where each check lives (hop vs origin) rather than asserting one place does both.

## License impact

None. The hop is the Envoy substrate already bundled by [ADR-0006](0006-egress-forward-proxy-substrate.md); the v1 inspection leaf is pre-minted out of band and served over Envoy-native file SDS, so v1 ships no OCU minter on the data path. The dynamic per-SNI minter named by [ADR-0007](0007-egress-auth-mechanism.md) stays specified for the non-enumerable case but unbuilt at GA. The reversal removes baseline build surface (the allow-list resolver and structured-deny vocabulary move to optional hardening); it adds no dependency.

## Threat mitigation

Re-anchors the P6 egress rows in [06-threat-model.md](../06-threat-model.md) §3 onto the baseline hop. The deny-by-default allow-list (P6-E1) and the structured `x-deny-reason` (P6-R1) move from baseline invariants to the optional-hardening rung; the baseline keeps the single-hop no-bypass guarantee (single route + block-local-connections + no second socket) and the payload-independent tripwire (P6-I1). For cross-scope reach (P6-E2): the baseline forwards the caller's bearer unmodified and injects nothing, so P6-E2's credential-injection premise is absent at the baseline — the residual cross-scope vector is a foreign `filesystem_id` presented with the held JWT, which the backend origin rejects (401); the threat-model edit to P6-E2 is a premise rewrite (injection absent), not merely a mitigation re-home. The deviation between baseline and hardening is named here so a later contributor does not re-introduce the deny-by-default allow-list as the baseline by default.

## Open questions

1. The reference carries a second inspection CA for an unobserved purpose; v1 models only the single egress-gateway-CA inspection chain. Whether a second chain is ever needed is deferred ([#269](https://github.com/Wide-Moat/open-computer-use/issues/269)).
2. The accepted-with-tier residual: a permissive baseline reaches arbitrary hosts and plaintext HTTP, and a block surfaces as a connect failure rather than a structured deny ([#272](https://github.com/Wide-Moat/open-computer-use/issues/272)).
