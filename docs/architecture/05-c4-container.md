<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: draft
last-reviewed: 2026-05-31
owner: "@Wide-Moat/architects"
applies-to: next/v1
---

Names the runnable units inside the OCU box that Layer 4 drew as one block, and what crosses between them. Audience: architects and security engineers reading this before a component spec.

## 1. Container vs zone vs context

A C4 container is a separately runnable unit — a process or data store that must be running for OCU to work ([c4model.com](https://c4model.com/abstractions/container)). That is a different axis from the two already cut:

- A **trust zone** ([`02-trust-boundaries.md`](02-trust-boundaries.md) §2) is a deploy/protection slice — where it runs and under what protection.
- A **bounded context** ([`04-bounded-contexts.md`](04-bounded-contexts.md) §1) is a domain slice — which part carries the competitive value.

The five trust zones map to six containers. Four of the five zones are one container each. The Control plane is the exception: it splits into two containers along its interface seam — an agent-facing MCP gateway and an operator/lifecycle API — because the kill-switch must be unreachable from the agent path by network policy, not by an in-process route guard (§3). Layer 5 grouped four of the zones into one bounded context (Agent Execution); that grouping is about domain ownership, not deployment, so it does not merge the boxes — Agent Execution is realized as five cooperating containers, and the sixth (Audit pipeline) is the Compliance Evidence context.

## 2. Container diagram

The diagram is [`diagrams/c4-container.mmd`](diagrams/c4-container.mmd) (six containers in the OCU box; five external actors for orientation). Edge labels name the protocol or token class that crosses; `1..N` marks the per-session container; all five source containers fan into the Audit pipeline over one Published Language (OCSF). External-actor contracts are in [`03-c4-context.md`](03-c4-context.md) §4, not restated here.

## 3. The six containers

Each sits in a Layer 3 zone and a Layer 5 context. Responsibility is one line; technology is a component-spec decision (under [`components/`](./components/), opened per [PROCESS.md](PROCESS.md)) and is named here only by role. NFR anchors are the measurable targets each container must meet.

| Container | Zone | Context | Responsibility | NFR anchor |
|---|---|---|---|---|
| **MCP gateway** (agent-facing) | Control plane | Agent Execution | Terminates inbound MCP tool-calls and authenticates the caller; metadata-only, runs no agent loop and proxies no model. Holds no upstream credential, no lifecycle mutation, and no kill-switch. | [NFR-IC-04](manifesto/02-nfrs.md), [NFR-FLEX-14](manifesto/02-nfrs.md) |
| **Control / operator API** | Control plane | Agent Execution | Session lifecycle, quota, the session denylist, and the kill-switch. Operator-only ingress; no path reachable from the MCP surface. | [NFR-SEC-01](manifesto/02-nfrs.md), [NFR-COMP-29](manifesto/02-nfrs.md) |
| **Storage broker** | Storage broker | Agent Execution | Host-side object-store client holding the backend credential; signs its own backend requests. Two faces of one client: the guest mount (south — `filesystem_id`-scoped file-operation interface) and the data-plane client face (north — the file/artifact API plus OCU's authenticated SPA and preview-render, served as components inside this container, not a separate one). Both faces share the one backend credential and the one storage-lane backend leg ([NFR-SEC-85](manifesto/02-nfrs.md)); no other component speaks the object-store protocol ([NFR-SEC-25](manifesto/02-nfrs.md)), so one consistency view covers both faces. Resolves the `downloadable` axis at read for both faces ([NFR-SEC-73](manifesto/02-nfrs.md)); neither guest nor data-plane client holds a backend credential. The north face verifies the embed token and sets a first-party session ([NFR-SEC-82](manifesto/02-nfrs.md), [NFR-SEC-83](manifesto/02-nfrs.md)). Replica count is a deployment concern (§5). | [NFR-SEC-25](manifesto/02-nfrs.md), [NFR-SEC-15](manifesto/02-nfrs.md), [NFR-SEC-73](manifesto/02-nfrs.md), [NFR-SEC-79](manifesto/02-nfrs.md), [NFR-SEC-82](manifesto/02-nfrs.md), [NFR-SEC-83](manifesto/02-nfrs.md) |
| **Session sandbox** `[1..N]` | Compute plane | Agent Execution | Executes one session's tool-calls in an isolated runtime that holds no standing secret and reaches the network only through the egress edge. Guest agent is PID 1; runtime tier by `workload_trust_profile`. | [NFR-SEC-02](manifesto/02-nfrs.md), [NFR-SEC-43](manifesto/02-nfrs.md) |
| **Egress trust-edge proxy** | Egress trust-edge | Agent Execution | The single outbound path. Deny-by-default allow-list; emits a structured deny reason. On legs that require it, injects the upstream authorization received over Envoy SDS at the egress-wide-bump rung (the default once an upstream credential is configured); the transparent pass-through and deny-all rungs do not inject (see [`02-trust-boundaries.md`](02-trust-boundaries.md) §7, [ADR-0007](adr/0007-egress-auth-mechanism.md)). The broker's pre-signed backend leg traverses a storage-dedicated lane allow-list-only (no TLS termination), distinct from the guest egress lane ([NFR-SEC-85](manifesto/02-nfrs.md)); the rung is per-destination, not global. | [NFR-SEC-05](manifesto/02-nfrs.md), [NFR-SEC-23](manifesto/02-nfrs.md), [NFR-SEC-27](manifesto/02-nfrs.md), [NFR-SEC-29](manifesto/02-nfrs.md) |
| **Audit pipeline** | Audit pipeline | Compliance Evidence | Captures session, tool, storage, and egress events into a hash-linked durable store and forwards to a customer-owned sink. | [NFR-SEC-03](manifesto/02-nfrs.md), [NFR-COMP-01](manifesto/02-nfrs.md) |

The MCP gateway and the Control / operator API are the same trust zone (Control plane, §2) split into two runnable units so the §1 reachability property holds at deploy time — separate process, operator-only ingress, distinct privilege set. The guest agent is the process that constitutes the sandbox container, not an eighth container: it has no lifecycle independent of the sandbox and dies with it.

## 4. Internal boundaries

Token classes and their TTLs are canonical in [`02-trust-boundaries.md`](02-trust-boundaries.md) §8; this layer names which boundary each crosses. The `F#` column is the canonical flow label every component spec and [`06-threat-model.md`](06-threat-model.md) §3 reference; this table is its sole definition.

| F# | Boundary | What crosses | Direction |
|---|---|---|---|
| F1 | Caller → MCP gateway | MCP authorization spec, audience-validated | inbound |
| F2 | Operator → Control / operator API | PAM-JIT credential, operator-only ingress | inbound |
| F3 | Customer IdP → Control / operator API | relying-party assertion (full shelf); contract in [`03-c4-context.md`](03-c4-context.md) §4 | inbound |
| F4 | SOAR → Control / operator API | signed admin API for revoke (the inbound half of the SOAR contract); contract in [`03-c4-context.md`](03-c4-context.md) §4 | inbound |
| F5 | MCP gateway → Control / operator API | session create / status, service identity | internal request |
| F6 | Control / operator API → Session sandbox | Session JWT bound to `container_name` | host dials guest |
| F7 | Storage broker → Session sandbox | file-operation mount, session resource handle | host dials guest |
| F8 | Session sandbox → Egress trust-edge | the only outbound network path | one-way |
| F9 | Storage broker → Egress trust-edge → backend | broker-signed request, allow-list-only | outbound |
| F10 | {all five source containers} → Audit pipeline | OCSF event (Published Language) | fan-in |
| F11 | Data-plane client → Storage broker (north face) | SPA + file/artifact API (upload/list/download), embed token verified → first-party session; scope + intent checked at accept, `downloadable` resolved at read ([NFR-SEC-73](manifesto/02-nfrs.md)) | inbound |

Two properties are load-bearing at this layer. First, no guest path reaches a long-lived upstream secret — the Storage broker holds its backend credential host-side, and the upstream credential reaches the Egress trust-edge over SDS on the edge-originated leg, never the guest; the guest may hold a short-lived session-scoped handle to a host-side mediator, which is not the upstream secret. The mechanism that attaches the credential is selected per upstream ([ADR-0007](adr/0007-egress-auth-mechanism.md)): edge-inject in v1; the protocol-broker mechanism is the Storage-broker zone, deferred for other upstreams. Second, the control / exec channel is opened by the host into the guest (host dials, guest listens) with the caller identity host-derived, so a compromised guest cannot reach the kill-switch or impersonate another session ([NFR-SEC-43](manifesto/02-nfrs.md)).

User-data and guest-internet traffic take different routes with different authorization. User-data is exchanged with the Storage broker over its two faces (south mount, north file/artifact API), where file authorization lives — scope, intent, `downloadable`. Guest-internet traffic takes the Egress trust-edge, where network authorization lives — allow-list, bump-rung inspection, upstream-auth injection — and the guest names no storage backend. The guest has no single path that does both. The two routes converge at one boundary already in the table above — `Storage broker → Egress trust-edge → backend` — where the broker's own backend leg leaves on the storage-dedicated lane allow-list-only ([NFR-SEC-85](manifesto/02-nfrs.md)) (the edge forwards a broker-signed request, it does not authorize the content). That north-face traffic is host-side caller↔broker, not a host↔guest channel, so NFR-SEC-43 is unaffected.

## 5. Deployment shelves

All six containers exist on both shelves; only the substrate differs. The diagram is shelf-agnostic. Scaling topology — node placement, sandbox scheduling, replica counts — is a deployment-view concern, not drawn here. The egress-substrate and identity-floor substitutions below are summarized from [`02-trust-boundaries.md`](02-trust-boundaries.md) §7–§8, which owns them. Egress posture is chosen by need (the §7 ladder, [ADR-0007](adr/0007-egress-auth-mechanism.md)), not by shelf; the row below shows only the substrate each shelf supplies under that ladder.

| Container | Minimal shelf (one-click solo) | Full shelf |
|---|---|---|
| MCP gateway | single process, co-located | scheduled, single instance per deployment |
| Control / operator API | co-located, host-rooted local operator credential | scheduled; customer-IdP-asserted operator identity |
| Storage broker | host-local backend credential | customer-PKI workload identity; STS-scoped per session |
| Session sandbox | local runtime, `runc` default | hardened or hardware-virt tier per workload |
| Egress trust-edge proxy | auto-generated per-deployment CA + file SDS source (pre-minted leaves for an enumerable allow-list) | external/customer SDS source; dynamic per-SNI minter for a non-enumerable allow-list |
| Audit pipeline | file-system sink | OCSF bridge to customer SIEM |

## 6. Industry comparison

The agent-facing / operator split (containers 1 and 2) is the dominant shape across orchestrated sandbox platforms: caller-facing surfaces and lifecycle surfaces are separate deployables. OCU adopts that split and additionally motivates it with the kill-switch reachability invariant rather than protocol convenience alone.

Two seams diverge from the field by design, for an in-perimeter regulated buyer whose threat model is an adversarial workload rather than inbound multi-tenant routing:

- **Storage broker as its own container.** Storage is the least-separated concern elsewhere — usually backed by external object storage or host-local volumes managed inside the control plane. OCU keeps the backend credential and the plaintext content-inspection point out of the agent-reachable surface, which the blast-radius requirement demands ([NFR-SEC-25](manifesto/02-nfrs.md)).
- **Egress as a credential-injecting enforcement chokepoint.** Dedicated proxies are near-universal but almost all are ingress/routing proxies. OCU's egress edge is the sole outbound path, deny-by-default, and the upstream-authorization injection point — the credential reaches it over Envoy SDS, is attached on the re-originated leg ([ADR-0007](adr/0007-egress-auth-mechanism.md)), and the guest never holds the long-lived upstream secret.

## 7. Open questions

1. Does the Session sandbox warrant a sub-container split once the workload-trust tier and guest-agent protocol are specified, or stay one container with internal components? — [#174](https://github.com/Wide-Moat/open-computer-use/issues/174).
2. Is the Storage broker one container per deployment or one per sandbox host, and does the answer change the diagram? — [#175](https://github.com/Wide-Moat/open-computer-use/issues/175).
