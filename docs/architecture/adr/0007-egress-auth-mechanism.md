<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-06-01
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
compliance-impact: [SOC2-CC6.1, SOC2-CC6.6, NYDFS-500.15, DORA-Art.28, EU-AI-Act-Art.15]
license-impact: TLS-termination substrate is the same Envoy already bundled by ADR-0006; a per-SNI cert-minting sidecar is the added build surface
threat-mitigation-link: ../components/06-egress-trust-edge.md
---

Selects how the Egress trust-edge attaches upstream authorization — by edge injection or by a protocol broker — and scopes v1 to edge injection only. Audience: anyone wiring or auditing how the sandbox reaches an authenticated upstream.

# ADR-0007: Egress auth mechanism — edge-inject vs protocol-broker

## Status

`proposed`

## Context

The guest holds no long-lived upstream secret ([NFR-SEC-23](../manifesto/02-nfrs.md)); the credential is attached outside the guest. Two mechanisms can do that, and they suit different upstreams. The Egress trust-edge can originate the connection and inject an `Authorization` header (edge-inject), or a host-side broker can hold the credential, speak the upstream protocol itself, and expose only a local handle to the guest (protocol-broker). [ADR-0005](0005-egress-credential-delivery-envoy-sds.md) fixed where the credential comes from (Envoy SDS); [ADR-0006](0006-egress-forward-proxy-substrate.md) fixed the forward-proxy substrate (Envoy, deny-by-default floor). Neither decided which mechanism attaches the credential, nor how the edge terminates TLS to do it — left open as component-06 open question #2. The forcing constraint is the one-click solo install ([NFR-FLEX-15](../manifesto/02-nfrs.md)): the default path must run from one `docker-compose up` with no certificate authority an operator has to manage.

## Decision

We will select the egress auth mechanism by the upstream's properties — edge-inject for a fixed-client, low-granularity bearer credential; protocol-broker for a high-value credential scoped by per-operation rights — and ship only edge-inject in v1, because the v1 upstream is an LLM API and a broker is unneeded surface until a scoped-credential upstream exists.

The selection axis:

| Upstream property | Mechanism |
|---|---|
| Client is a fixed binary that hardcodes the endpoint; credential is one bearer token; protocol is HTTP + `Authorization`; no per-operation authorization needed | **edge-inject (egress-wide bump)** |
| Credential is high-value and scoped by rights (repo / object / tenant); protocol is multi-operation (git-smart-http, S3/SigV4, REST with per-object authz); the credential holder must authorize each operation | **protocol-broker** |

v1 implements edge-inject. Protocol-broker is named, abstraction-ready, and deferred: the pattern is already canonical as the Storage broker zone ([02-trust-boundaries.md](../02-trust-boundaries.md) §2), which holds the object-store backend credential and exposes a session-scoped handle. A future scoped-credential upstream reuses that zone; v1 builds no new broker.

**edge-inject mechanism (v1).** The edge runs egress-wide bump: it terminates every outbound TLS connection by presenting a leaf certificate minted on demand for the requested SNI, signed by a per-deployment CA whose public certificate is in the sandbox trust store and whose private key never enters the guest. It injects the upstream credential on the re-originated leg and re-establishes TLS to the genuine upstream, validating the upstream's real certificate against the public CA set. Injection is gated on a presented, scoped credential carried by the request — never on the request's network origin (a guest process that presents no credential receives none, which is why a bare `curl` from the sandbox reaches an allowed host but is unauthenticated). The substrate is the Envoy already bundled by ADR-0006 as the data plane, plus a self-hosted SDS minting service (a gRPC `SecretDiscoveryService` that stamps a leaf for the requested SNI from the CA key); Envoy alone does not mint leaves on the fly.

## Consequences

- Component 06 records this ADR in its `adr:` front-matter (`[0005, 0006]` → `[0005, 0006, 0007]`); open question #2 (the MITM-termination half) is resolved here.
- Egress posture follows need, not a fixed default ([02-trust-boundaries.md](../02-trust-boundaries.md) §7): a deployment that needs no egress runs deny-all; one that needs only unauthenticated internet runs transparent pass-through; one that needs an authenticated upstream runs egress-wide bump. Bump is the default *only when an upstream credential is configured* — it is not imposed on a deployment that needs no outbound credential, so the one-click solo path stays intact. [NFR-FLEX-15](../manifesto/02-nfrs.md) is reframed from a two-mode switch to this ladder.
- The bump CA is generated per deployment and its public certificate is injected into the sandbox trust store automatically at start; "one-click" is preserved by automating the CA, not by omitting it. The private key sits only on the minting service.
- Egress-wide bump holds plaintext for every inspected destination at the edge, a larger blast radius than the broker pattern. The credential-holding minter and the plaintext-inspection path are distinct trust surfaces: the rule the substrate must not blur is that the injected credential does not share a blast radius with the plaintext of all egress. A single Envoy-plus-minter process is admissible on the solo shelf only because the injected credential there is itself scoped and short-lived; a high-value long-lived credential separates the minter from the inspection plane.
- The leaf source is static or dynamic by the allow-list's shape, not its size: a config-time-enumerable allow-list that changes slower than the deploy cadence is served by pre-minted leaves over a file SDS source (Envoy holds thousands of certificates without issue — the limit is enumerability, sub-domain depth, and churn, not a certificate count). A non-enumerable allow-list (CDN shards, per-tenant sub-domains, deep multi-label hosts a wildcard cannot compress, or third-party-controlled naming) requires the dynamic per-SNI minter. v1's single LLM apex is the trivial static case; the minter is specified so the dynamic case needs no re-decision.
- mTLS / cert-pin / proof-of-possession upstreams cannot be served by header injection and stay tracked at [#176](https://github.com/Wide-Moat/open-computer-use/issues/176); they are a protocol-broker or out-of-scope case, not an edge-inject one.
- This ADR adds no requirement to the Audit pipeline, the resolver, or the allow-list that ADR-0006 already fixed; it sits above them.

## Alternatives considered

- **Protocol-broker for v1's LLM upstream** — rejected: the LLM credential is a single low-granularity bearer to a fixed endpoint, so a broker that speaks the protocol and authorizes per operation buys nothing the edge does not, and adds a stateful service to the solo path.
- **mitmproxy / Squid ssl-bump as the bump substrate** — both mint per-SNI leaves natively with less code than a custom SDS minter. Rejected as the default: adopting either as the bump engine drops the Envoy data plane (the allow-list, OCSF audit emit, and `ext_authz` seam ADR-0006 already placed there) or runs two proxies in series. The Envoy-plus-minter path keeps one data plane; mitmproxy (BSD, clears the licence gate) is recorded as the fallback for a deployment that does not need the Envoy data plane.
- **GCP Secure Web Proxy (managed Envoy + minter)** — supplies exactly this shape as a managed service. Rejected: not self-hostable inside a customer perimeter, which is the deployment target; it informs the architecture but cannot be the substrate.
- **Inject user personal access tokens through the egress edge** — proposed as a way to let the agent reach a user's third-party account by storing each user's PAT outside the guest and injecting it like the LLM key. Rejected: a PAT is a high-value credential scoped by rights, so by this ADR's own axis it is a protocol-broker case, not edge-inject. Edge injection cannot authorize per operation (it staples the token to every request to that host) and would make OCU a store of users' personal third-party access — the broad blast radius an InfoSec review rejects. The correct path is the broker pattern with short-lived, per-resource tokens (e.g. a GitHub App installation token), deferred with the rest of the broker mechanism.

## Compliance impact

- `SOC2-CC6.1` / `SOC2-CC6.6`: the credential is attached outside the guest on the edge-originated leg, and the bump segment is a single named inspection point — the access-control and boundary-protection story for authenticated egress.
- `NYDFS-500.15`: the upstream authorization is encrypted in transit on both legs; the re-originated leg validates the genuine upstream certificate.
- `DORA-Art.28` / `EU-AI-Act-Art.15`: the selection axis records, per upstream, where a credential is held and how each authenticated outbound flow is mediated — the third-party-arrangement and robustness evidence for the outbound path.

## License impact

The TLS-termination substrate is the Envoy already bundled by [ADR-0006](0006-egress-forward-proxy-substrate.md); no new bundled proxy. The added build surface is a self-hosted SDS minting service (OCU code). mitmproxy, if later adopted as the fallback engine, is BSD and clears the licence gate; it is recorded in [`manifesto/05-licensing-posture.md`](../manifesto/05-licensing-posture.md) as rejected-as-default for dropping the Envoy data plane.

## Threat mitigation

Resolves the MITM-termination half of [component 06](../components/06-egress-trust-edge.md) open question #2 and tightens P6-E2: injection keyed on a presented scoped credential, never on network origin, bounds a cross-scope or compromised-in-guest process to the credentials it can present rather than to whatever the sandbox can reach. The anti-pattern this forbids — "inject because traffic came from sandbox X" — is named so it is not re-introduced.
