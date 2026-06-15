<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-06-14
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
amends: [0006, 0007, 0008, 0011]
amended-by: [0019]
compliance-impact: [SOC2-CC6.1, SOC2-CC6.6, NYDFS-500.15, DORA-Art.28, DORA-Art.30, EU-AI-Act-Art.15]
license-impact: none — the hop is the Envoy already bundled by ADR-0006; the reversal removes baseline build surface (the allow-list resolver and structured-deny vocabulary move to optional hardening)
threat-mitigation-link: ../components/06-egress-trust-edge.md
---

Sets the v1 egress baseline to a single TLS-terminating inspection hop with no host allow-list and no egress-side scope, and moves scope enforcement to the storage engine. Audience: anyone wiring or auditing how a sandbox reaches an authenticated upstream or its storage backend.

# ADR-0016: Egress baseline — one inspection hop, engine-enforced scope

## Status

`proposed`

This ADR amends the egress floor set by [ADR-0006](0006-egress-forward-proxy-substrate.md); it lands in the same coordinated package as the storage-custody recut ([ADR-0013](0013-storage-credential-custody.md), [ADR-0014](0014-storage-transport-tier-universal-network-leg.md), [ADR-0015](0015-storage-decomposition-by-trust-plane.md)).

## Context

The v1 egress baseline is a single TLS-terminating inspection hop: it terminates outbound TLS for every host, presents a per-host leaf from a gateway-side CA, and forwards to origin. It carries no host allow-list — arbitrary hosts and plaintext HTTP pass through, and the storage backend host holds no privilege at the hop. On the LLM leg it re-credentials nothing — the client `Authorization: Bearer` passes through after inspection. On the storage leg it validates the guest's weak session JWT and exchanges it at the OIDC issuer for the real filestore credential, overwriting the `Authorization` header ([ADR-0019](0019-egress-exchanges-filestore-credential.md)). It emits no structured deny — a blocked non-`:443` port times out, a non-routable host is refused at the TCP layer. Scope is enforced at the storage engine on the edge-injected real credential: a foreign `filesystem_id` (or `memory_store_id`) is rejected (HTTP 403 PermissionDenied — a valid signature but a foreign scope; a missing or expired credential is 401), not by the hop. "One governed outbound path, no bypass" holds by a single default route plus block-local-connections plus the absence of a second socket — not by a deny-by-default allow-list.

Current canon sets the opposite as baseline: [ADR-0006](0006-egress-forward-proxy-substrate.md) fixes a deny-by-default allow-list floor, [NFR-SEC-17](../manifesto/02-nfrs.md) the allow-list-on-connect mechanism with a structured `x-deny-reason`, [ADR-0011](0011-storage-egress-lane.md) a no-TLS-termination storage lane, and [NFR-SEC-16/23/27/29](../manifesto/02-nfrs.md) and [component-06](../components/06-egress-trust-edge.md) the egress-side scope. The owner ruled the permissive hop the v1 baseline and the stricter posture an optional hardening; this ADR records that ruling and names the deviation (anti-recurrence rule 5). A second inspection CA for an unmodelled purpose is out of v1 scope; the baseline is the single egress-gateway-CA chain (see Open questions).

## Decision

We will set the v1 egress baseline to a single TLS-terminating inspection hop with no host allow-list and no egress-side scope, enforce scope at the storage engine (it validates the `filesystem_id` / `memory_store_id` JWT claim), and re-classify the prior deny-by-default-allow-list + egress-side-scope + structured-deny model as a named optional hardening on the same hop, because the permissive hop is the v1 baseline the owner ruled and the stricter posture is a deliberate addition layered on top.

| Property | Baseline (v1) | Optional hardening |
|---|---|---|
| Destination policy | none — any host reachable through the one hop | deny-by-default allow-list (resolved-IP + SNI) |
| TLS | terminated at the hop, per-host leaf from the gateway-side CA, re-originated to origin | unchanged |
| Credential at the hop | LLM leg: client Bearer passes through unmodified. Storage leg: the hop validates the weak session JWT and exchanges it at the issuer for the real filestore credential, overwriting `Authorization` ([ADR-0019](0019-egress-exchanges-filestore-credential.md)) | unchanged |
| Scope enforcement | storage engine validates the `filesystem_id` scope on the edge-injected real credential; foreign scope → 403 PermissionDenied from origin (missing/expired credential → 401) | egress-side per-destination / per-claim scope at the hop |
| Deny signal | none — blocked port times out, non-routable refused at TCP | structured `x-deny-reason` vocabulary on the hop |
| No-bypass guarantee | single default route + block-local-connections + no second socket | unchanged |

"Governed" means one TLS-inspected hop with no second outbound socket, not a deny-by-default allow-list. The optional hardening is configuration on the same hop, switched on per deployment; the baseline path runs with it off.

**Two distinct SDS surfaces — do not conflate.** The inspection leaf is the per-host TLS certificate the hop presents while terminating outbound TLS, signed from the gateway-side inspection CA. The **upstream-credential SDS source** ([ADR-0005](0005-egress-credential-delivery-envoy-sds.md)) is unrelated: there Envoy fetches the upstream authorization from a static file or a customer store and OCU mints nothing. The leaf is the inspection certificate; the credential source delivers the upstream bearer.

The inspection leaf's source is mode-dependent, and v1 needs no OCU code for it. Stock Envoy distributes and rotates an existing secret over SDS but never generates a keypair or signs a CSR on the fly, so a non-enumerable destination set (CDN shards, per-tenant subdomains) would need an OCU per-SNI minter — a gRPC `SecretDiscoveryService` that stamps a leaf for the requested SNI from the CA key ([ADR-0007](0007-egress-auth-mechanism.md)). The v1 destination set is enumerable (the single LLM apex at the baseline, an explicit allow-list under the hardening), so the leaves are **pre-minted out of band from the inspection CA and served over Envoy-native file SDS — zero OCU minter code on the data path**. The dynamic per-SNI minter is specified for the non-enumerable case but **not instantiated at v1 GA**. The baseline hop terminates TLS with a pre-minted leaf and forwards the client bearer untouched; it engages no upstream-credential injection unless a deployment configures one.

## Consequences

- Positive: the v1 egress is one permissive TLS-inspecting hop with no host allow-list, so there is no baseline destination policy to explain or justify on the first InfoSec read.
- Positive: the baseline drops build surface. The allow-list resolver, the SNI pre-filter as a mandatory drop, and the `x-deny-reason` vocabulary become optional-hardening config rather than baseline code, and the one-click solo path ([NFR-FLEX-15](../manifesto/02-nfrs.md)) runs with one default route and a pre-minted inspection leaf served over Envoy-native file SDS — no OCU minter code on the v1 data path.
- Positive: engine-enforced scope means a leaked guest JWT cannot reach another `filesystem_id` even if the hop is permissive — the blast radius is one session's own scope for the token TTL, set by the origin, independent of the hop. Custody of that JWT (signing key off-box at a host-side issuer, control plane delivers, guest holds a weak session JWT the edge exchanges) is set by [ADR-0013](0013-storage-credential-custody.md); this ADR governs the path that JWT travels, not its issuance.
- Negative: with no baseline allow-list, the permissive hop reaches arbitrary hosts and plaintext HTTP. Content-blind exfil to an unconfigured destination is not denied at the baseline; it is bounded only by the single-hop inspection and the payload-independent tripwire. A deployment that needs destination restriction enables the allow-list hardening — named, not silent.
- Negative: with no structured deny at the hop, a baseline block surfaces as a timeout or TCP refusal, not a machine-parseable reason. Audit of a baseline denial records the connect failure, not an `x-deny-reason`. The hardening restores the structured deny where a deployment needs it.
- Neutral: scope denials are origin-authored JSON bodies, observable in the audit stream as upstream responses, not as hop-authored deny events — the audit contract ([08-contracts.md](../08-contracts.md) §1) records the hop's allow/observe events and the origin's response, not a hop scope-deny.
- This ADR amends [component-06](../components/06-egress-trust-edge.md) (baseline = permissive inspection hop; allow-list / structured-deny invariants move under the hardening), [ADR-0006](0006-egress-forward-proxy-substrate.md) (the deny-by-default allow-list floor it fixes is no longer the baseline, only the hardening rung), [ADR-0007](0007-egress-auth-mechanism.md) (edge-inject and the leaf-minter ride the hardening rung, not a baseline injection floor), [ADR-0008](0008-session-egress-attribution.md) (attribution by the presented L7 token applies at the baseline hop, not only the bump rung), and [ADR-0011](0011-storage-egress-lane.md) (the storage lane's "no TLS termination, allow-list-only" clause is dropped — the hop terminates TLS and there is no per-request signature to preserve). It re-anchors NFR-SEC-16/17/23/27/29 (see Compliance impact).

## Alternatives considered

- **Keep the deny-by-default allow-list as the baseline (current canon).** Rejected: the owner ruled the baseline a permissive hop with no host allow-list, passing arbitrary hosts and plaintext through. Holding the stricter posture as the baseline contradicts that ruling (anti-recurrence rule 5); the deviation is the hardening, not the base. The allow-list survives as the named optional hardening, so the capability is not lost — only its place in the ladder changes.
- **Enforce scope at the egress hop (egress-side `filesystem_id` / `memory_store_id` binding).** Rejected: scope is enforced at the storage engine — the hop is claim-blind and the engine returns 403 PermissionDenied on a foreign scope (a missing or expired token is 401). Egress-side scope is the hardening, not the base; making it the baseline duplicates the engine's authority at the hop, widening the hop's responsibility for no baseline gain. A deployment that wants defence-in-depth enables egress-side scope as the named hardening.

## Compliance impact

- `SOC2-CC6.1` / `SOC2-CC6.6`: boundary protection rests on the single governed hop and the no-second-socket guarantee; access control to a storage scope is the storage engine's claim check, recorded as the evidence path for scope enforcement.
- `NYDFS-500.15`: traffic is TLS-terminated and re-originated at the one hop; in-transit confidentiality holds on both legs at the baseline.
- `DORA-Art.28` / `DORA-Art.30` / `EU-AI-Act-Art.15`: the outbound path is a single named mediation point, and per-scope authorization is the storage engine's documented control — the third-party-arrangement and accuracy/cybersecurity evidence names where each check lives (hop vs origin) rather than asserting one place does both.

## License impact

None. The hop is the Envoy substrate already bundled by [ADR-0006](0006-egress-forward-proxy-substrate.md); the v1 inspection leaf is pre-minted out of band and served over Envoy-native file SDS, so v1 ships no OCU minter on the data path. The dynamic per-SNI minter named by [ADR-0007](0007-egress-auth-mechanism.md) stays specified for the non-enumerable case but unbuilt at GA. The reversal removes baseline build surface (the allow-list resolver and structured-deny vocabulary move to optional hardening); it adds no dependency.

## Threat mitigation

Re-anchors the P6 egress rows in [06-threat-model.md](../06-threat-model.md) §3 onto the baseline hop. The deny-by-default allow-list (P6-E1) and the structured `x-deny-reason` (P6-R1) move from baseline invariants to the optional-hardening rung; the baseline keeps the single-hop no-bypass guarantee (single route + block-local-connections + no second socket) and the payload-independent tripwire (P6-I1). For cross-scope reach (P6-E2): on the storage leg the exchange is the baseline — the edge validates the guest's weak session JWT and exchanges it at the issuer for the real filestore credential keyed on `filesystem_id` ([ADR-0019](0019-egress-exchanges-filestore-credential.md)), so the forwarded `Authorization` differs from the inbound assertion; the residual cross-scope vector is a foreign `filesystem_id` on the injected credential, which the storage engine rejects (403 PermissionDenied — a valid signature but a foreign scope; a missing or expired credential is 401). The deviation between baseline and hardening is named here so a later contributor does not re-introduce the deny-by-default allow-list as the baseline by default.

## Open questions

1. The reference carries a second inspection CA for an unobserved purpose; v1 models only the single egress-gateway-CA inspection chain. Whether a second chain is ever needed is deferred ([#269](https://github.com/Wide-Moat/open-computer-use/issues/269)).
2. The accepted-with-tier residual: a permissive baseline reaches arbitrary hosts and plaintext HTTP, and a block surfaces as a connect failure rather than a structured deny ([#272](https://github.com/Wide-Moat/open-computer-use/issues/272)).
