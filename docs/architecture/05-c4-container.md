<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: draft
last-reviewed: 2026-06-14
owner: "@Wide-Moat/architects"
applies-to: next/v1
---

Names the runnable units inside the OCU box that Layer 4 drew as one block, and what crosses between them. Audience: architects and security engineers reading this before a component spec.

## 1. Container vs zone vs context

A C4 container is a separately runnable unit — a process or data store that must be running for OCU to work ([c4model.com](https://c4model.com/abstractions/container)). That is a different axis from the two already cut:

- A **trust zone** ([`02-trust-boundaries.md`](02-trust-boundaries.md) §2) is a deploy/protection slice — where it runs and under what protection.
- A **bounded context** ([`04-bounded-contexts.md`](04-bounded-contexts.md) §1) is a domain slice — which part carries the competitive value.

The trust zones map to a set of containers, one runnable unit per row of §3. The mapping is not 1:1: the Control plane splits into two containers along its interface seam — an agent-facing MCP gateway and an operator/lifecycle API — because the kill-switch must be unreachable from the agent path by network policy, not by an in-process route guard (§3); and the Web UI is a container distinct from the Object-store service because they front different counterparties with different custody and aggregate roots ([ADR-0015](adr/0015-storage-decomposition-by-trust-plane.md)). Layer 5 grouped the compute-side zones into one bounded context (Agent Execution); that grouping is about domain ownership, not deployment, so it does not merge the boxes — Agent Execution is realized as several cooperating containers, and the Audit pipeline is the Compliance Evidence context. The current count is a then-true observation of this layer, not a binding invariant: an ADR may not reject a new deployable on the ground that it would raise the count ([ADR-0015](adr/0015-storage-decomposition-by-trust-plane.md) restates the carve-out on counterparty, not on count).

## 2. Container diagram

The diagram is [`diagrams/c4-container.mmd`](diagrams/c4-container.mmd) (the containers in the OCU box; external actors for orientation). Edge labels name the protocol or token class that crosses; `1..N` marks the per-session container; the host-side containers fan into the Audit pipeline over one Published Language (OCSF). External-actor contracts are in [`03-c4-context.md`](03-c4-context.md) §4, not restated here.

## 3. The containers

Each sits in a Layer 3 zone and a Layer 5 context. Responsibility is one line; technology is a component-spec decision (under [`components/`](./components/), opened per [PROCESS.md](PROCESS.md)) and is named here only by role. NFR anchors are the measurable targets each container must meet.

| Container | Zone | Context | Responsibility | NFR anchor |
|---|---|---|---|---|
| **MCP gateway** (agent-facing) | Control plane | Agent Execution | Terminates inbound MCP tool-calls and authenticates the caller; metadata-only, runs no agent loop and proxies no model. Holds no upstream credential, no lifecycle mutation, and no kill-switch. | [NFR-IC-04](manifesto/02-nfrs.md), [NFR-FLEX-14](manifesto/02-nfrs.md) |
| **Control / operator API** | Control plane | Agent Execution | Session lifecycle, quota, the session denylist, and the kill-switch. Operator-only ingress; no path reachable from the MCP surface. Carries the storage-credential **delivery** role: it relays the pre-issued, `filesystem_id`-scoped JWT into the mount config over the provisioning push and installs the guest's control-channel verify-key ([ADR-0013](adr/0013-storage-credential-custody.md)); the signing key stays off-box at a separate issuer (below) — the control plane delivers, it does not sign. | [NFR-SEC-01](manifesto/02-nfrs.md), [NFR-COMP-29](manifesto/02-nfrs.md), [NFR-SEC-25](manifesto/02-nfrs.md) |
| **Object-store service** | Storage | Agent Execution | The only door to storage: the capability-free service that speaks the engine protocol no other component speaks ([ADR-0010](adr/0010-storage-backend-pluggable-adapter.md) generalizes the engine to local-volume + S3): engine + `filesystem_id`→prefix + multipart. It holds no signing key — the credential is the off-box-issued scoped JWT, forwarded unmodified, and the storage engine enforces the `filesystem_id` scope ([ADR-0013](adr/0013-storage-credential-custody.md)). Both callers reach it: the in-guest mount client (guest leg, over the egress hop) and the Web UI (host leg) ([ADR-0014](adr/0014-storage-transport-tier-universal-network-leg.md)). One door, two callers, one engine leg. The `memory_store_id` mount is a sibling type ([ADR-0015](adr/0015-storage-decomposition-by-trust-plane.md)). Replica count is a deployment concern (§5). | [NFR-SEC-25](manifesto/02-nfrs.md), [NFR-SEC-15](manifesto/02-nfrs.md), [NFR-SEC-73](manifesto/02-nfrs.md) |
| **Web UI** | Storage | Agent Execution | File upload, preview, download, and the embeddable SPA, reached by an external data-plane client (E5) over an embed-token→first-party-session flow ([NFR-SEC-82](manifesto/02-nfrs.md), [NFR-SEC-83](manifesto/02-nfrs.md)). An OCU design addition, not a reproduction of the reference. Aggregate root is the artifact plus the embed-asserted principal, not the running sandbox session. Holds no signing key; reaches storage only by calling the Object-store service (host leg). Untrusted file bodies render inside the capability-free parser-sandbox sub-boundary ([components/08-web-ui.md](components/08-web-ui.md), [#218](https://github.com/Wide-Moat/open-computer-use/issues/218)). Resolves `downloadable` at read ([NFR-SEC-73](manifesto/02-nfrs.md)). | [NFR-SEC-79](manifesto/02-nfrs.md), [NFR-SEC-82](manifesto/02-nfrs.md), [NFR-SEC-83](manifesto/02-nfrs.md) |
| **Session sandbox** `[1..N]` | Compute plane | Agent Execution | Executes one session's tool-calls in an isolated runtime that reaches the network only through the egress edge. Holds the off-box-issued, `filesystem_id`-scoped JWT in its mount config (root-readable, useless outside its scope and ~6 h window) but never a signing key ([ADR-0013](adr/0013-storage-credential-custody.md)). Guest agent is PID 1; runtime tier by `workload_trust_profile`. | [NFR-SEC-02](manifesto/02-nfrs.md), [NFR-SEC-43](manifesto/02-nfrs.md) |
| **Egress trust-edge proxy** | Egress trust-edge | Agent Execution | The single governed outbound hop: one default route, no second socket, guest loopback dials blocked ([NFR-SEC-16](manifesto/02-nfrs.md)). Terminates TLS for inspection and forwards the request on; it does not re-credential — a client bearer passes through unmodified ([ADR-0016](adr/0016-egress-baseline-inspection-hop-backend-scope.md)). Scope is not enforced here: a foreign-`filesystem_id` token is rejected by the storage engine, not the proxy ([ADR-0013](adr/0013-storage-credential-custody.md)). A deny-by-default allow-list with structured deny is a named optional hardening on top of this hop, not the v1 baseline (see [`02-trust-boundaries.md`](02-trust-boundaries.md) §7). | [NFR-SEC-05](manifesto/02-nfrs.md), [NFR-SEC-16](manifesto/02-nfrs.md) |
| **Audit pipeline** | Audit pipeline | Compliance Evidence | Captures session, tool, storage, and egress events into a hash-linked durable store and forwards to a customer-owned sink. Fan-in is host-side only; the Session sandbox does not emit. | [NFR-SEC-03](manifesto/02-nfrs.md), [NFR-COMP-01](manifesto/02-nfrs.md) |

The MCP gateway and the Control / operator API are the same trust zone (Control plane, §2) split into two runnable units so the §1 reachability property holds at deploy time — separate process, operator-only ingress, distinct privilege set. The Object-store service and the Web UI share the Storage zone but are distinct deployables: the Object-store service is the door both legs reach, the Web UI fronts the external E5 client with its own aggregate root ([ADR-0015](adr/0015-storage-decomposition-by-trust-plane.md)). The guest agent is the process that constitutes the sandbox container, not a separate container; it dies with the sandbox.

The storage signing key sits at a separate off-box issuer that this layer does not model as a container: it is not in the deployment's request path, the control plane reaches it out of band to obtain a pre-signed token, and no modelled container holds its key ([ADR-0013](adr/0013-storage-credential-custody.md)). Its deployable and repository boundary is [ADR-0017](adr/0017-control-plane-repo-boundary.md), not this layer.

## 4. Internal boundaries

Token classes and their TTLs are canonical in [`02-trust-boundaries.md`](02-trust-boundaries.md) §8; this layer names which boundary each crosses. The `F#` column is the canonical flow label every component spec and [`06-threat-model.md`](06-threat-model.md) §3 reference; this table is its sole definition.

| F# | Boundary | What crosses | Direction |
|---|---|---|---|
| F1 | Caller → MCP gateway | MCP authorization spec, audience-validated | inbound |
| F2 | Operator → Control / operator API | PAM-JIT credential, operator-only ingress | inbound |
| F3 | Customer IdP → Control / operator API | relying-party assertion (full shelf); contract in [`03-c4-context.md`](03-c4-context.md) §4 | inbound |
| F4 | SOAR → Control / operator API | signed admin API for revoke (the inbound half of the SOAR contract); contract in [`03-c4-context.md`](03-c4-context.md) §4 | inbound |
| F5 | MCP gateway → Control / operator API | session create / status, service identity | internal request |
| F6 | Control / operator API → Session sandbox | Session JWT bound to `container_name`, host-attested caller | host dials guest |
| F7 | Control / operator API → Session sandbox | mount provisioning push: the `ProvisionMountConfig` (`filesystem_id`, `service_url`, off-box-issued scoped JWT (control-plane-relayed), `ca_cert_pem`, mount paths) written before the mount client starts; distinct from the data leg F7a ([ADR-0013](adr/0013-storage-credential-custody.md)) | host dials guest |
| F7a | Session sandbox → Egress trust-edge → Object-store service → Storage engine | the in-guest mount client dials the `service_url` data leg outbound over the single egress hop to the Object-store service, static `Authorization: Bearer` (the off-box-issued scoped JWT, forwarded unmodified); the Object-store service forwards it to the storage engine, which validates the `filesystem_id` scope ([ADR-0014](adr/0014-storage-transport-tier-universal-network-leg.md), [ADR-0013](adr/0013-storage-credential-custody.md)) | guest-out |
| F8 | Session sandbox → Egress trust-edge | the only outbound network path; carries F7a and guest-internet traffic alike | one-way |
| F9 | Web UI → Object-store service | intra-deployment file-operation intent (host leg), after three-axis authorization, to the one door that speaks the engine protocol; does not cross the egress hop ([ADR-0015](adr/0015-storage-decomposition-by-trust-plane.md)) | internal request |
| F10 | {host-side containers: MCP gateway, Control / operator API, Object-store service, Web UI, Egress trust-edge} → Audit pipeline | OCSF event (Published Language); the Session sandbox does not emit — its actions are recorded host-side | fan-in |
| F11 | Data-plane client → Web UI | SPA + file API (upload/list/download), embed token verified → first-party session; scope + intent checked at accept, `downloadable` resolved at read ([NFR-SEC-73](manifesto/02-nfrs.md)) | inbound |

Two properties are load-bearing at this layer. First, no in-deployment path holds a signing key. The storage-credential signing key is held off-box by a separate issuer; the Control / operator API only delivers the pre-signed bearer ([ADR-0013](adr/0013-storage-credential-custody.md)). The guest receives a `filesystem_id`-scoped, ~6 h bearer over the F7 provisioning push and forwards it unmodified on the F7a data leg, so a fully-compromised guest yields at most one session's own filesystem for the remaining window, and the storage engine rejects that token presented for any other `filesystem_id`. The mechanism that attaches an upstream credential is selected per upstream by [ADR-0007](adr/0007-egress-auth-mechanism.md): edge-inject for the fixed-client LLM bearer in v1; the protocol-broker mechanism stays named and deferred for a future scoped-credential upstream. No in-deployment component holds the storage credential — it is the off-box-issued, guest-forwarded scoped bearer the engine verifies. Second, the control / exec channel is opened by the host into the guest (host dials, guest listens) with the caller identity host-derived, so a compromised guest cannot reach the kill-switch or impersonate another session ([NFR-SEC-43](manifesto/02-nfrs.md)).

The provisioning push (F7) and the data leg (F7a) are distinct. F7 is host-originated and carries the mount config — the scope handle, the `service_url`, the scoped bearer, and the inspection-CA trust anchor — over the host-dials-guest control channel before the mount client starts. F7a is guest-originated: the in-guest mount client dials the `service_url` out through the single egress hop on every tier ([ADR-0014](adr/0014-storage-transport-tier-universal-network-leg.md)), never a host-dialled socket.

Storage has one door. The Object-store service is the single component that speaks the engine protocol; both callers reach it — the guest mount client over the egress hop (F7a/F8) and the Web UI over the intra-deployment leg F9. Neither caller reaches the storage engine directly, and there is one engine leg, from the Object-store service. The off-box-issued scoped bearer travels on F7a, and the storage engine validates its `filesystem_id` claim ([ADR-0013](adr/0013-storage-credential-custody.md)).

User-data and guest-internet traffic take different boundaries with different authorization. User-data reaches the Object-store service over two legs — the guest mount leg F7a and the Web UI host leg F9 (fronting the E5 client API F11) — where file authorization lives: scope, intent, `downloadable`. On a network-engine shelf, guest-internet and the storage data leg both leave on the Egress trust-edge (F8): the proxy inspects one governed hop and forwards, the storage engine enforces scope, and a retarget to a foreign `filesystem_id` is refused at the engine. The egress hop is a shelf property of the storage leg, not an invariant: on the minimal/dev shelf a local-volume engine ([ADR-0010](adr/0010-storage-backend-pluggable-adapter.md)) opens no network leg. The F11 traffic is host-side caller↔Web UI, not a host↔guest channel, so NFR-SEC-43 is unaffected.

## 5. Deployment shelves

Every container in §3 exists on both shelves; only the substrate differs. The diagram is shelf-agnostic. Scaling topology — node placement, sandbox scheduling, replica counts — is a deployment-view concern, not drawn here. The egress-substrate and identity-floor substitutions below are summarized from [`02-trust-boundaries.md`](02-trust-boundaries.md) §7–§8, which owns them. Egress posture is chosen by need (the §7 ladder, [ADR-0007](adr/0007-egress-auth-mechanism.md)), not by shelf; the row below shows only the substrate each shelf supplies under that ladder.

| Container | Minimal shelf (one-click solo) | Full shelf |
|---|---|---|
| MCP gateway | single process, co-located | scheduled, single instance per deployment |
| Control / operator API | co-located, host-rooted local operator credential; delivers a bearer from a co-located off-box issuer (issuer signing key local to the host) | scheduled; customer-IdP-asserted operator identity; off-box issuer signing key in customer KMS/HSM |
| Object-store service | host-local storage engine | customer-PKI workload identity; engine-enforced `filesystem_id` scope |
| Web UI | co-located, file API + SPA on the host | scheduled; parser-sandbox on a hardened substrate |
| Session sandbox | local runtime, `runc` default | hardened or hardware-virt tier per workload |
| Egress trust-edge proxy | auto-generated per-deployment inspection CA, single TLS-inspected hop | external/customer SDS source; optional deny-by-default allow-list hardening |
| Audit pipeline | file-system sink | OCSF bridge to customer SIEM |

## 6. Industry comparison

The agent-facing / operator split (the MCP gateway and the Control / operator API) is common across orchestrated sandbox platforms: caller-facing surfaces and lifecycle surfaces are separate deployables. OCU motivates it with the kill-switch reachability invariant, not protocol convenience.

Three seams diverge by design, for an in-perimeter buyer whose threat model is an adversarial workload, not inbound multi-tenant routing:

- **Storage-credential custody at an off-box issuer.** The signing key for the storage credential is held only by a separate off-box issuer; the control plane delivers a pre-signed token, the guest forwards a `filesystem_id`-scoped, time-bounded JWT it cannot mint or widen, and the storage engine enforces the scope ([ADR-0013](adr/0013-storage-credential-custody.md)). A leaked guest token confines to one session's own filesystem for its window ([NFR-SEC-25](manifesto/02-nfrs.md)).
- **One door to storage, with the Web UI as its own component.** Storage is the least-separated concern elsewhere — usually folded into the control plane over external object storage or host-local volumes. OCU keeps the Object-store service capability-free as the only door and isolates the untrusted-body preview-render in a capability-free parser-sandbox under the Web UI, so the session-minting authority and the untrusted content never co-reside with a key-adjacent path ([ADR-0015](adr/0015-storage-decomposition-by-trust-plane.md), [#218](https://github.com/Wide-Moat/open-computer-use/issues/218)).
- **Egress as a single governed TLS-inspected hop.** Dedicated proxies are near-universal but almost all are ingress/routing proxies. OCU's egress edge is the sole outbound path and a TLS-terminating inspection point; it forwards rather than re-credentials, and storage scope is enforced at the storage engine, not by an egress allow-list ([ADR-0016](adr/0016-egress-baseline-inspection-hop-backend-scope.md)). A deny-by-default allow-list with structured deny is a hardening on top of this hop, not the v1 baseline ([ADR-0016](adr/0016-egress-baseline-inspection-hop-backend-scope.md)).

## 7. Open questions

1. Does the Session sandbox warrant a sub-container split once the workload-trust tier and guest-agent protocol are specified, or stay one container with internal components? — [#174](https://github.com/Wide-Moat/open-computer-use/issues/174).
2. Is the Object-store service one deployable per deployment or one per sandbox host, and does the answer change the diagram? — [#175](https://github.com/Wide-Moat/open-computer-use/issues/175).
