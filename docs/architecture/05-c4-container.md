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

The six trust zones map to seven containers. Five of the six zones are one container each. The Control plane is the exception: it splits into two containers along its interface seam — an agent-facing MCP gateway and an operator/lifecycle API — because the kill-switch must be unreachable from the agent path by network policy, not by an in-process route guard (§3). Layer 5 grouped five of the zones into one bounded context (Agent Execution); that grouping is about domain ownership, not deployment, so it does not merge the boxes — Agent Execution is realized as six cooperating containers, and the seventh (Audit pipeline) is the Compliance Evidence context.

## 2. Container diagram

The diagram is [`diagrams/c4-container.mmd`](diagrams/c4-container.mmd) (seven containers in the OCU box; five external actors for orientation). Edge labels name the protocol or token class that crosses; `1..N` marks the per-session container; all six source containers fan into the Audit pipeline over one Published Language (OCSF). External-actor contracts are in [`03-c4-context.md`](03-c4-context.md) §4, not restated here.

## 3. The seven containers

Each sits in a Layer 3 zone and a Layer 5 context. Responsibility is one line; technology is a component-spec decision (under [`components/`](./components/), opened per [PROCESS.md](PROCESS.md)) and is named here only by role. NFR anchors are the measurable targets each container must meet.

| Container | Zone | Context | Responsibility | NFR anchor |
|---|---|---|---|---|
| **MCP gateway** (agent-facing) | Control plane | Agent Execution | Terminates inbound MCP tool-calls and authenticates the caller; metadata-only, runs no agent loop and proxies no model. Holds no upstream credential, no lifecycle mutation, and no kill-switch. | [NFR-IC-04](manifesto/02-nfrs.md), [NFR-FLEX-14](manifesto/02-nfrs.md) |
| **Control / operator API** | Control plane | Agent Execution | Session lifecycle, quota, the session denylist, and the kill-switch. Operator-only ingress; no path reachable from the MCP surface. | [NFR-SEC-01](manifesto/02-nfrs.md), [NFR-COMP-29](manifesto/02-nfrs.md) |
| **Credential custody** | Credential custody | Agent Execution | Host-side store of the real upstream credentials with rotation and delegated STS. Hands a scoped lease to the Egress trust-edge at injection time; no guest-facing interface. | [NFR-SEC-23](manifesto/02-nfrs.md), [NFR-SEC-29](manifesto/02-nfrs.md) |
| **Storage broker** | Storage broker | Agent Execution | Host-side object-store client holding the backend credential; signs its own backend requests. Two faces of one client: the guest mount (south — `filesystem_id`-scoped file-operation interface) and the data-plane client face (north — the file/artifact API plus OCU's authenticated SPA and preview-render, served as components inside this container, not a separate one). Both faces share the one backend credential and the one egress backend leg; no other component speaks the object-store protocol ([NFR-SEC-25](manifesto/02-nfrs.md)), so one consistency view covers both faces. Resolves the `downloadable` axis at read for both faces ([NFR-SEC-73](manifesto/02-nfrs.md)); neither guest nor data-plane client holds a backend credential. The north face verifies the embed token and sets a first-party session ([NFR-SEC-82](manifesto/02-nfrs.md), [NFR-SEC-83](manifesto/02-nfrs.md)). Replica count is a deployment concern (§5). | [NFR-SEC-25](manifesto/02-nfrs.md), [NFR-SEC-15](manifesto/02-nfrs.md), [NFR-SEC-73](manifesto/02-nfrs.md), [NFR-SEC-79](manifesto/02-nfrs.md), [NFR-SEC-82](manifesto/02-nfrs.md), [NFR-SEC-83](manifesto/02-nfrs.md) |
| **Session sandbox** `[1..N]` | Compute plane | Agent Execution | Executes one session's tool-calls in an isolated runtime that holds no standing secret and reaches the network only through the egress edge. Guest agent is PID 1; runtime tier by `workload_trust_profile`. | [NFR-SEC-02](manifesto/02-nfrs.md), [NFR-SEC-43](manifesto/02-nfrs.md) |
| **Egress trust-edge proxy** | Egress trust-edge | Agent Execution | The single outbound path. Deny-by-default allow-list; emits a structured deny reason. On legs that require it, injects the upstream authorization fetched from custody — possible only in MITM-inspecting mode; the minimal-shelf transparent pass-through cannot inject (see [`02-trust-boundaries.md`](02-trust-boundaries.md) §7). The broker's pre-signed backend leg traverses allow-list-only (no TLS termination); mode is per-destination, not global. | [NFR-SEC-05](manifesto/02-nfrs.md), [NFR-SEC-27](manifesto/02-nfrs.md) |
| **Audit pipeline** | Audit pipeline | Compliance Evidence | Captures session, tool, credential, storage, and egress events into a hash-linked durable store and forwards to a customer-owned sink. | [NFR-SEC-03](manifesto/02-nfrs.md), [NFR-COMP-01](manifesto/02-nfrs.md) |

The MCP gateway and the Control / operator API are the same trust zone (Control plane, §2) split into two runnable units so the §1 reachability property holds at deploy time — separate process, operator-only ingress, distinct privilege set. The guest agent is the process that constitutes the sandbox container, not an eighth container: it has no lifecycle independent of the sandbox and dies with it.

## 4. Internal boundaries

Token classes and their TTLs are canonical in [`02-trust-boundaries.md`](02-trust-boundaries.md) §8; this layer names which boundary each crosses.

| Boundary | What crosses | Direction |
|---|---|---|
| Caller → MCP gateway | MCP authorization spec, audience-validated | inbound |
| Operator → Control / operator API | PAM-JIT credential, operator-only ingress | inbound |
| Customer IdP → Control / operator API | relying-party assertion (full shelf); contract in [`03-c4-context.md`](03-c4-context.md) §4 | inbound |
| SOAR → Control / operator API | signed admin API for revoke (the inbound half of the SOAR contract); contract in [`03-c4-context.md`](03-c4-context.md) §4 | inbound |
| MCP gateway → Control / operator API | session create / status, service identity | internal request |
| Control / operator API → Session sandbox | Session JWT bound to `container_name` | host dials guest |
| Storage broker → Session sandbox | file-operation mount, session resource handle | host dials guest |
| Data-plane client → Storage broker (north face) | SPA + file/artifact API (upload/list/download), embed token verified → first-party session; scope + intent checked at accept, `downloadable` resolved at read ([NFR-SEC-73](manifesto/02-nfrs.md)) | inbound |
| Credential custody → Egress trust-edge | scoped credential lease, fetched at injection | edge pulls |
| Session sandbox → Egress trust-edge | the only outbound network path | one-way |
| Storage broker → Egress trust-edge → backend | broker-signed request, allow-list-only | outbound |
| {all six source containers} → Audit pipeline | OCSF event (Published Language) | fan-in |

Two properties are load-bearing at this layer. First, no guest path reaches a standing secret — both credential boundaries in the table above sit host-side of the guest. Second, the control / exec channel is opened by the host into the guest (host dials, guest listens) with the caller identity host-derived, so a compromised guest cannot reach the kill-switch or impersonate another session ([NFR-SEC-43](manifesto/02-nfrs.md)).

User-data and guest-internet traffic take different routes with different authorization. User-data is exchanged with the Storage broker over its two faces (south mount, north file/artifact API), where file authorization lives — scope, intent, `downloadable`. Guest-internet traffic takes the Egress trust-edge, where network authorization lives — allow-list, MITM inspection, upstream-auth injection — and the guest names no storage backend. The guest has no single path that does both. The two routes converge at one boundary already in the table above — `Storage broker → Egress trust-edge → backend` — where the broker's own backend leg leaves allow-list-only (the edge forwards a broker-signed request, it does not authorize the content). That north-face traffic is host-side caller↔broker, not a host↔guest channel, so NFR-SEC-43 is unaffected.

## 5. Deployment shelves

All seven containers exist on both shelves; only the substrate differs. The diagram is shelf-agnostic. Scaling topology — node placement, sandbox scheduling, replica counts — is a deployment-view concern, not drawn here. The egress-mode and identity-floor substitutions below are summarized from [`02-trust-boundaries.md`](02-trust-boundaries.md) §7–§8, which owns them.

| Container | Minimal shelf (one-click solo) | Full shelf |
|---|---|---|
| MCP gateway | single process, co-located | scheduled, single instance per deployment |
| Control / operator API | co-located, host-rooted local operator credential | scheduled; customer-IdP-asserted operator identity |
| Credential custody | host-local signing key | customer-PKI workload identity, HSM-rooted |
| Storage broker | host-local backend credential | customer-PKI workload identity; STS-scoped per session |
| Session sandbox | local runtime, `runc` default | hardened or hardware-virt tier per workload |
| Egress trust-edge proxy | transparent pass-through | MITM-inspecting opt-in, customer CA |
| Audit pipeline | file-system sink | OCSF bridge to customer SIEM |

## 6. Industry comparison

The agent-facing / operator split (containers 1 and 2) is the dominant shape across orchestrated sandbox platforms: caller-facing surfaces and lifecycle surfaces are separate deployables. OCU adopts that split and additionally motivates it with the kill-switch reachability invariant rather than protocol convenience alone.

Two seams diverge from the field by design, for an in-perimeter regulated buyer whose threat model is an adversarial workload rather than inbound multi-tenant routing:

- **Storage broker as its own container.** Storage is the least-separated concern elsewhere — usually backed by external object storage or host-local volumes managed inside the control plane. OCU keeps the backend credential and the plaintext content-inspection point out of the agent-reachable surface, which the blast-radius requirement demands ([NFR-SEC-25](manifesto/02-nfrs.md)).
- **Egress as a credential-injecting enforcement chokepoint.** Dedicated proxies are near-universal but almost all are ingress/routing proxies. OCU's egress edge is the sole outbound path, deny-by-default, and the upstream-authorization injection point — so the guest never holds the credential.

## 7. Open questions

1. Does the Session sandbox warrant a sub-container split once the workload-trust tier and guest-agent protocol are specified, or stay one container with internal components? — [#174](https://github.com/Wide-Moat/open-computer-use/issues/174).
2. Is Credential custody (and the Storage broker) one container per deployment or one per sandbox host, and does the answer change the diagram? — [#175](https://github.com/Wide-Moat/open-computer-use/issues/175).
