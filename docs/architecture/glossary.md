<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: draft
last-reviewed: 2026-05-30
owner: "@Wide-Moat/architects"
applies-to: next/v1
---

Canonical definitions for terms used across this architecture. Define a term here once; link to it from anywhere else. A term lands here when it appears in ≥ 2 documents.

## Control plane

Orchestrator and session lifecycle, exposing two interfaces of one zone: an agent-facing MCP interface (tool calls) and an operator/lifecycle interface (lifecycle, quota, kill-switch). The kill-switch is reachable only on the operator interface, never over MCP. Single instance per deployment. Holds no customer payload; metadata-only by design. Outbound to LLM and other upstream goes through the Egress trust-edge — the Control plane is not a model proxy. The agent-facing / operator split becomes two containers at Layer 6.

Used in: [`02-trust-boundaries.md`](./02-trust-boundaries.md) §2, [`manifesto/02-nfrs.md`](./manifesto/02-nfrs.md).

## Compute plane

The session sandbox zone — one sandbox per session, lifecycle bound to the session, guest agent as PID 1. Substrate is set by the [Sandbox tier](#sandbox-tier): `runc` on the minimal-capability shelf, `gVisor` on the full-capability shelf in v1 (microVM post-v1). Cross-session network reachability disabled.

Used in: [`02-trust-boundaries.md`](./02-trust-boundaries.md) §2, [`manifesto/02-nfrs.md`](./manifesto/02-nfrs.md).

## Storage broker

Host-side broker for the guest's mutable user-data mount. The guest speaks a file-operation interface (open / read / write / list) to the broker, not the object-store protocol; the broker is the object-store client and signs its own backend requests, so no middlebox rewrites a request signature. Holds the backend credential; the guest holds only a session-scoped resource handle (a `filesystem_id`), never the backend key. The broker's backend traffic traverses the Egress trust-edge as one allow-list destination, in allow-list-only mode (no TLS termination) so the signature stays intact; content inspection, when required, runs at the broker on plaintext, before signing. It has a guest-facing interface (the mount) and governs an inbound data path, where the Egress trust-edge governs only outbound. Mount substrate (FUSE / virtio-fs / 9p) is a component-spec choice. The broker has two faces on one object-store client: a [south face](#south-face--north-face) (the guest mount) and a [north face](#south-face--north-face) (the file-artifact data plane for a [Data-plane client](#data-plane-client)).

Used in: [`02-trust-boundaries.md`](./02-trust-boundaries.md) §2 / §7.1, [`manifesto/02-nfrs.md`](./manifesto/02-nfrs.md) NFR-SEC-25.

## Data-plane client

An external caller that reaches OCU's file-artifact data plane — the [Storage broker](#storage-broker) [north face](#south-face--north-face) — to upload, list, download, or preview-render files. It is either OCU's own authenticated SPA (embeddable cross-origin) or a headless caller of the file-artifact API; bytes flow client↔OCU directly, never through a calling peer and never to the object store. Distinct from the MCP caller (which drives the control plane) and the Operator (CLI / PAM-JIT). Absent in headless deployments.

Used in: [`03-c4-context.md`](./03-c4-context.md) §4, [`05-c4-container.md`](./05-c4-container.md) §3-§4, [`06-threat-model.md`](./06-threat-model.md) §2, [`08-contracts.md`](./08-contracts.md) §1.

## South face / north face

The two faces of the one [Storage broker](#storage-broker) object-store client. The **south face** is the guest mount — a file-operation interface (open / read / write / list) the sandbox speaks, scoped by `filesystem_id`. The **north face** is the file-artifact data plane — OCU's HTTP file/artifact API and embeddable SPA, served on a dedicated file/UI ingress for a [Data-plane client](#data-plane-client), not the MCP listener. Both faces share the one backend credential and the one egress backend leg; neither the guest nor the data-plane client holds a backend credential.

Used in: [`02-trust-boundaries.md`](./02-trust-boundaries.md) §2, [`04-bounded-contexts.md`](./04-bounded-contexts.md) §3, [`05-c4-container.md`](./05-c4-container.md) §3-§4, [`08-contracts.md`](./08-contracts.md) §1.

## Downloadable

The third storage-authorization axis (beyond scope and intent): a per-object disposition the broker resolves at read, separating "may read" from "may remove from the sandbox." A non-downloadable object is readable or previewable in-session but yields no egress-eligible artifact; the disposition reaches the Egress trust-edge as a deny signal. The preview-not-download exfiltration control.

Used in: [`02-trust-boundaries.md`](./02-trust-boundaries.md) §2, [`06-threat-model.md`](./06-threat-model.md) §3, [`08-contracts.md`](./08-contracts.md) §3, [`manifesto/02-nfrs.md`](./manifesto/02-nfrs.md) NFR-SEC-73.

## Embed token

A signed short-TTL token (OIDC-asserted, `exp ≤ 120 s`) the calling peer's backend mints so its already-authenticated user opens OCU's embeddable SPA cross-origin without re-entering credentials. The [north face](#south-face--north-face) verifies the token signature and expiry, then sets a first-party session; OCU mints nothing and no OCU upstream secret enters the browser.

Used in: [`05-c4-container.md`](./05-c4-container.md) §3, [`06-threat-model.md`](./06-threat-model.md) §3, [`08-contracts.md`](./08-contracts.md) §3, [`manifesto/02-nfrs.md`](./manifesto/02-nfrs.md) NFR-SEC-82.

## Egress trust-edge

The single outbound zone. Every outbound request from the Compute plane goes through here. The guest sends an unauthenticated request; the edge attaches the upstream authorization, received over Envoy SDS from a static file (solo) or a customer store (enterprise), on the outbound leg (injection needs the MITM-inspecting mode — see [Egress posture](#egress-posture)). Network-bound identity (NFR-SEC-27): the fact that traffic arrived from the sandbox at all is the identity. Fail-closed: proxy unreachable → outbound traffic dropped.

Used in: [`02-trust-boundaries.md`](./02-trust-boundaries.md) §2, [`manifesto/02-nfrs.md`](./manifesto/02-nfrs.md). Spelled `egress proxy` when referring to the component implementation; `Egress trust-edge` when referring to the zone.

## Audit pipeline

Durable bus + hash-chained store + bridges to customer sinks. Mandatory in code; sinks are pluggable. Distinct retention floor, RPO, and tamper-evidence properties from the Control plane, which is why it is drawn as its own zone.

Used in: [`02-trust-boundaries.md`](./02-trust-boundaries.md) §2, [`manifesto/02-nfrs.md`](./manifesto/02-nfrs.md).

## Capability shelf

A configuration profile of one product. Two shelves:

- **Minimal-capability shelf** — single-tenant, host-local Ed25519 signing keys, auto-generated self-signed CA, file-system audit sink, host-rooted local operator credential. The one-click solo install path. Spelled **solo / dev tier** in some Layer 3 prose and NFR rows; the two names denote the same shelf.
- **Full-capability shelf** — customer HSM rooted, per-tenant SPIFFE trust domain, customer-CA-rooted egress, OCSF bridges to customer SIEM, customer-IdP-asserted operator identity. Spelled **hardened tier and above** in some Layer 3 prose and NFR rows; same shelf.

Both shelves run the same binary; the difference is configuration plus presence of customer-supplied facilities (HSM, CA, SIEM bridge, IdP). Not a SKU split. The shelf is one axis; the [Sandbox tier](#sandbox-tier) (runtime) and the [Isolation tier](#isolation-tier-t0t3) (tenancy shape) are orthogonal axes — selecting a shelf does not pick the runtime.

Used in: [`02-trust-boundaries.md`](./02-trust-boundaries.md) §2 / §8 / §10, [`manifesto/02-nfrs.md`](./manifesto/02-nfrs.md).

## Isolation tier (T0…T3)

Per-tenant deployment shape menu. Picks the substrate, not the invariants — boundary properties hold for every tier.

- T0 logical — row-level filter, shared kernel.
- T1 namespace — Kubernetes namespace + NetworkPolicy + RBAC + ResourceQuota.
- T2 VPC / VNet — per-tenant VPC, no peering.
- T3 dedicated cluster — dedicated control plane per tenant.

Higher isolation tiers (dedicated hardware, customer-owned cage) are tracked as candidates in open question `arch/cross-tenant-isolation-grading`; promote when a named workload requires them.

Used in: [`02-trust-boundaries.md`](./02-trust-boundaries.md) §4.

## Sandbox tier

The sandbox runtime ladder, picked by the workload's `workload_trust_profile`, never by data classification (AP-13). Distinct from the [Isolation tier](#isolation-tier-t0t3) (tenancy shape) and the [Capability shelf](#capability-shelf) (key custody / CA / sink).

- `runc` — shared-kernel container; v1 default for the `trusted_operator` profile (one-click solo install).
- `gVisor` (`runsc`) — user-space-kernel isolation; v1 hardened default for the `internal_workforce` profile.
- microVM (hardware-virt; named example Firecracker) — post-v1, for the `untrusted` profile; tracked at [#161](https://github.com/Wide-Moat/open-computer-use/issues/161).

Used in: [`manifesto/02-nfrs.md`](./manifesto/02-nfrs.md) §"Sandbox tier — workload-driven selection", [`02-trust-boundaries.md`](./02-trust-boundaries.md) §2.

## Egress posture

The mode the Egress trust-edge runs in. Two modes:

- **Transparent pass-through** — proxy in path, does not terminate TLS, no customer CA needed. Default.
- **MITM-inspecting** — proxy terminates TLS at the customer-CA root; required for any in-path content inspection (DLP-ICAP, prompt-content classification). Opt-in.

DLP-ICAP is a configuration of the MITM mode, not a third mode.

Used in: [`02-trust-boundaries.md`](./02-trust-boundaries.md) §7, [`manifesto/02-nfrs.md`](./manifesto/02-nfrs.md) NFR-FLEX-15.

## Session JWT

Per-session session-identity token issued by the Control plane to the guest agent, bound to `container_name`, TTL ≤ 60 min and rotated while the session is active. It proves session identity to the Control plane; it is not an upstream credential and never leaves toward an upstream. The only token the guest holds. The TTL is an anti-replay window, not a session length — session idle (≤15 min, NFR-SEC-40) and absolute (≤12 h, NFR-SEC-41) limits are separate. Distinct from the SDS-delivered upstream credential (attached by the Egress trust-edge, never the guest) and the generic internal RPC token (TTL ≤ 60 min, inter-component, host-side).

Used in: [`02-trust-boundaries.md`](./02-trust-boundaries.md) §5 / §8 / §8.1, [`manifesto/02-nfrs.md`](./manifesto/02-nfrs.md) NFR-SEC-10/23/29.

## Generic internal token

Host-side service-to-service RPC token authenticating one internal component to another (Control plane ↔ Audit pipeline), TTL ≤ 60 min. It never reaches the guest and carries no operator scope or upstream credential. Distinct from the [Session JWT](#session-jwt) (guest-held, per session) and the SDS-delivered upstream credential (attached by the Egress trust-edge).

Used in: [`02-trust-boundaries.md`](./02-trust-boundaries.md) §8, [`manifesto/02-nfrs.md`](./manifesto/02-nfrs.md) NFR-SEC-23.

## OCSF

Open Cybersecurity Schema Framework, v1.x JSON. The canonical audit-event schema we emit on the Audit pipeline. Bridges to SIEM transforms emit CEF / Elastic ECS / Chronicle UDM downstream.

Used in: [`02-trust-boundaries.md`](./02-trust-boundaries.md) §5 / §10, [`manifesto/02-nfrs.md`](./manifesto/02-nfrs.md) NFR-MAINT-AUDIT-SCHEMA.

## Transparency log

External append-only log that the customer chooses (public, customer-private, or a Certificate-Transparency-style instance). The Audit pipeline submits the daily Merkle head of the hash-chained audit store; the log operator signs the Merkle head, we sign only the submission envelope. Provides tamper-evidence the customer can verify against an operator they trust.

Used in: [`02-trust-boundaries.md`](./02-trust-boundaries.md) §3 / §8.1 / §10 / §12, [`manifesto/02-nfrs.md`](./manifesto/02-nfrs.md) NFR-SEC-03.

## Bounded context

A slice of the domain with its own consistent model and language. Distinct from a trust zone ([`02-trust-boundaries.md`](./02-trust-boundaries.md) §2 — a deploy / protection slice): a bounded context answers "which domain model is consistent here," a trust zone answers "where does it run and under what protection." The two do not map one-to-one. Classified core (built in-house, carries competitive value), supporting (built, not differentiating), or generic (integrated, not built).

Used in: [`04-bounded-contexts.md`](./04-bounded-contexts.md).

## Anti-corruption layer

A translation boundary that keeps an external model from leaking into a context's own model. Lets a generic integration (customer IdP, secrets store, policy engine) be swapped without changing the core domain model. Spelled out in full; not abbreviated to "ACL" in diagrams, which collides with Access Control List.

Used in: [`04-bounded-contexts.md`](./04-bounded-contexts.md).

## Published Language

A shared, documented schema two contexts agree on at their boundary; the emitter conforms to the schema, not to the consumer's internals. The OCSF event between Agent Execution and Compliance Evidence is the canonical instance ([OCSF](#ocsf)). Distinct from Conformist, where one context accepts an upstream's model without negotiation (the MCP authorization spec).

Used in: [`04-bounded-contexts.md`](./04-bounded-contexts.md).

## Customer/Supplier

An upstream/downstream relationship where the downstream's needs shape the upstream's contract through negotiation — distinct from Conformist (no negotiation) and Anti-corruption layer (defensive translation). The Operator → Agent Execution PAM-JIT path is the instance: the operator's access needs are met by a negotiated contract, not by adopting an external model wholesale.

Used in: [`04-bounded-contexts.md`](./04-bounded-contexts.md).

## Open Host Service

A context that publishes a protocol or endpoint through which many producers and consumers integrate, typically carrying a [Published Language](#published-language). Compliance Evidence is the canonical instance — fan-in of OCSF events from five trust zones, fan-out to multiple customer SIEMs. The Open Host Service is the door; the Published Language is the vocabulary.

Used in: [`04-bounded-contexts.md`](./04-bounded-contexts.md).

## Compute-time metering

Per-session billing primitives emitted as audit events: CPU-min, RAM-GB-min, storage-GB-day, egress bytes, MCP-call count. Live on the Audit pipeline because they are part of the same hash-chained record stream.

Used in: [`02-trust-boundaries.md`](./02-trust-boundaries.md) §2, [`manifesto/02-nfrs.md`](./manifesto/02-nfrs.md) NFR-COST-05.
