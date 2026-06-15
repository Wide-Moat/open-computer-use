<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: draft
last-reviewed: 2026-06-14
owner: "@Wide-Moat/architects"
applies-to: next/v1
---

Canonical definitions for terms used across this architecture. Define a term here once; link to it from anywhere else. A term lands here when it appears in ≥ 2 documents.

## Control plane

The orchestration zone: session lifecycle, with an agent-facing MCP interface (tool calls) and an operator/lifecycle interface (lifecycle, quota, kill-switch). The kill-switch is reachable only on the operator interface, never over MCP. Holds metadata only, no customer payload. Outbound to the LLM and other upstream goes through the Egress trust-edge — the Control plane is not a model proxy. The agent-facing / operator split becomes two containers at Layer 6.

Used in: [`02-trust-boundaries.md`](./02-trust-boundaries.md) §2, [`manifesto/02-nfrs.md`](./manifesto/02-nfrs.md).

## Control / operator API

The only door to create or manage a session, repo `ocu-control`. It exposes the operator/lifecycle interface (lifecycle, quota, kill-switch) reached through the [Operator console](#operator-console) or CLI, never over MCP. It dials into the guest (host dials guest); there is no agent-path edge that reaches the kill-switch, denylist, or lifecycle. It delivers the pre-signed [Storage-JWT](#storage-jwt) in the provisioning push and never signs ([ADR-0013](./adr/0013-storage-credential-custody.md)). One instance per deployment.

Used in: [`05-c4-container.md`](./05-c4-container.md) §3, [`08-contracts.md`](./08-contracts.md) §1, [`adr/0017-control-plane-repo-boundary.md`](./adr/0017-control-plane-repo-boundary.md), [`components/02-control-operator-api.md`](./components/02-control-operator-api.md).

## Operator console

The read-only live view, repo `ocu-admin`, opt-in. A human reaches the [Control / operator API](#control--operator-api) through it (or the CLI), never by calling the API directly. It observes sessions; it cannot create or mutate them.

Used in: [`02-trust-boundaries.md`](./02-trust-boundaries.md) §2, [`components/00-overview.md`](./components/00-overview.md), [`adr/0017-control-plane-repo-boundary.md`](./adr/0017-control-plane-repo-boundary.md).

## Compute plane

The session sandbox zone — one sandbox per session, lifecycle bound to the session, guest agent as PID 1. Substrate is set by the [Sandbox tier](#sandbox-tier) — `runc`, gVisor, or microVM — selected by `workload_trust_profile`, orthogonal to the [shelf](#capability-shelf): both shelves carry every tier the host supports. Cross-session network reachability disabled.

Used in: [`02-trust-boundaries.md`](./02-trust-boundaries.md) §2, [`manifesto/02-nfrs.md`](./manifesto/02-nfrs.md).

## Filestore

The storage concern as a whole: a session's mutable user-data, the engine that holds it, and the components that reach it. The [Object-store service](#object-store-service) (`ocu-filestore`) is the one door to storage; it fronts a pluggable [storage engine](#storage-engine) (local-volume or S3) per [ADR-0010](./adr/0010-storage-backend-pluggable-adapter.md). Two callers reach the service: the [in-guest mount client](#in-guest-mount-client) (`ocu-rclone-filestore`) on the guest leg and the [Web UI](#web-ui) (`ocu-webui`) on the host leg. None of these holds a signing key ([ADR-0013](./adr/0013-storage-credential-custody.md), [ADR-0015](./adr/0015-storage-decomposition-by-trust-plane.md)). Drawn as the **Storage** zone in [`02-trust-boundaries.md`](./02-trust-boundaries.md) §2.

Used in: [`02-trust-boundaries.md`](./02-trust-boundaries.md) §2, [`04-bounded-contexts.md`](./04-bounded-contexts.md) §2-§4, [`05-c4-container.md`](./05-c4-container.md) §3, [`08-contracts.md`](./08-contracts.md) §1.

## Object-store service

The one door to storage, repo `ocu-filestore`. A first-party file-operation service (`listDirectory` / `upload` / `download` over an HTTP/RPC surface) that fronts a pluggable [storage engine](#storage-engine) ([ADR-0010](./adr/0010-storage-backend-pluggable-adapter.md)). Both callers reach the engine only through it — the [in-guest mount client](#in-guest-mount-client) on the guest leg, the [Web UI](#web-ui) on the host leg. It receives only the real filestore credential the [Egress trust-edge](#egress-trust-edge) injected — never the guest's weak [Storage-JWT](#storage-jwt), which the edge strips and exchanges before the request reaches it — and holds no signing key. One backend leg, two callers — never one leg per caller.

Used in: [`02-trust-boundaries.md`](./02-trust-boundaries.md) §2, [`04-bounded-contexts.md`](./04-bounded-contexts.md) §2-§4, [`05-c4-container.md`](./05-c4-container.md) §3, [`08-contracts.md`](./08-contracts.md) §1.

## Storage engine

The store that holds the bytes, behind the [Object-store service](#object-store-service): S3 or a local volume, a pluggable adapter ([ADR-0010](./adr/0010-storage-backend-pluggable-adapter.md)), off-box. It receives the real filestore credential the [Egress trust-edge](#egress-trust-edge) injected (never the guest's weak [Storage-JWT](#storage-jwt)) and enforces scope on it: a foreign `filesystem_id` returns 403 PermissionDenied — a valid credential but a foreign scope; a missing or expired credential is 401 ([ADR-0016](./adr/0016-egress-baseline-inspection-hop-backend-scope.md)). Reached only through `ocu-filestore`; neither the guest nor the Web UI reaches it directly. A local-volume engine opens no network leg.

Used in: [`02-trust-boundaries.md`](./02-trust-boundaries.md) §2, [`05-c4-container.md`](./05-c4-container.md) §3, [`08-contracts.md`](./08-contracts.md) §1, [`manifesto/02-nfrs.md`](./manifesto/02-nfrs.md) NFR-SEC-31.

## In-guest mount client

The guest-side storage caller, repo `ocu-rclone-filestore`. It presents the backend files as a filesystem in the guest and offers the `filesystem_id`-scoped file operations the running session reaches: `readFile` / `readFileMetadata` / `fileDelete` / `fileUpload` / `fileDownload` / `listDirectory` plus the whole-filesystem control verbs `importFiles` / `importZip` / `migrateFilesystem` / `removeFilesystem` / `releaseQuarantinedFiles`. It dials out to the [Object-store service](#object-store-service) over the [Data-leg](#data-leg) and authorizes with a [Storage-JWT](#storage-jwt) — the guest holds that scoped bearer in memory, never a signing key and never a raw backend key ([ADR-0013](./adr/0013-storage-credential-custody.md)). Authorization carries three axes: scope (`filesystem_id`), intent (`read` / `write` / `preview`), and [downloadable](#downloadable); scope is enforced at the [storage engine](#storage-engine) ([ADR-0016](./adr/0016-egress-baseline-inspection-hop-backend-scope.md)). Mount substrate (FUSE / virtio-fs / 9p) is a component-spec choice.

Used in: [`02-trust-boundaries.md`](./02-trust-boundaries.md) §2, [`04-bounded-contexts.md`](./04-bounded-contexts.md) §2-§4, [`05-c4-container.md`](./05-c4-container.md) §3, [`08-contracts.md`](./08-contracts.md) §1, [`manifesto/02-nfrs.md`](./manifesto/02-nfrs.md) NFR-SEC-25.

## Web UI

The file upload / preview / download component, repo `ocu-webui`: OCU's own client file/artifact API plus an embeddable SPA. It fronts an external [Data-plane client](#data-plane-client) over the [embed token](#embed-token) flow; its aggregate root is the artifact plus the embed-asserted principal, distinct from the session, so it is a core sub-context and its own component ([`04-bounded-contexts.md`](./04-bounded-contexts.md) §3, [ADR-0015](./adr/0015-storage-decomposition-by-trust-plane.md)). It reaches storage only through the [Object-store service](#object-store-service); it holds no signing key. Untrusted bodies render through a capability-free parser sub-component that holds no key and reaches no backend ([#218](https://github.com/Wide-Moat/open-computer-use/issues/218)). Served on a file/UI ingress distinct from the MCP listener.

Used in: [`04-bounded-contexts.md`](./04-bounded-contexts.md) §2-§4, [`05-c4-container.md`](./05-c4-container.md) §3-§4, [`06-threat-model.md`](./06-threat-model.md) §3, [`08-contracts.md`](./08-contracts.md) §1 / §3, [`manifesto/02-nfrs.md`](./manifesto/02-nfrs.md) NFR-SEC-82.

## Credential issuer

The off-box OIDC service that holds the sole signing key (ES256). It issues two things. First, a scoped weak [Storage-JWT](#storage-jwt) before sandbox boot; the [Control / operator API](#control--operator-api) delivers that pre-signed token in the provisioning push and never signs ([ADR-0013](./adr/0013-storage-credential-custody.md)). Second, the real filestore credential via RFC 8693 token-exchange, when the [Egress trust-edge](#egress-trust-edge) presents the weak JWT as the `subject_token` ([ADR-0019](./adr/0019-egress-exchanges-filestore-credential.md)). On the minimal shelf it is a bundled OpenBao; on the full shelf the customer provides it (OpenBao / Keycloak / KMS) over a documented mint-and-exchange contract. No component below it holds the signing key — not the guest, the [in-guest mount client](#in-guest-mount-client), the [Egress trust-edge](#egress-trust-edge), the [Object-store service](#object-store-service), or the [Web UI](#web-ui).

Used in: [`04-bounded-contexts.md`](./04-bounded-contexts.md) §3, [`05-c4-container.md`](./05-c4-container.md) §3, [`manifesto/02-nfrs.md`](./manifesto/02-nfrs.md) NFR-SEC-60, [`manifesto/05-licensing-posture.md`](./manifesto/05-licensing-posture.md) §"Bundled vs not-bundled".

## Storage-JWT

The weak, edge-only ES256 session assertion the [in-guest mount client](#in-guest-mount-client) carries toward the [Egress trust-edge](#egress-trust-edge); it is NOT the credential the [storage engine](#storage-engine) accepts. Minted by the [Credential issuer](#credential-issuer), scoped `{filesystem_id, intent, downloadable}`, short-lived, no in-session refresh, no re-sign. Delivered into the guest mount config at provisioning and forwarded as an opaque static `Authorization: Bearer`. The edge validates it (missing or invalid → 401) and exchanges it at the issuer for the real filestore credential ([ADR-0019](./adr/0019-egress-exchanges-filestore-credential.md)); the storage engine then enforces scope on that real credential — a foreign `filesystem_id` returns 403 PermissionDenied, a missing or expired credential is 401 ([ADR-0016](./adr/0016-egress-baseline-inspection-hop-backend-scope.md)). A leaked weak JWT reaches at most this filesystem for its short window and only by re-traversing the edge; it is not a whole-backend key.

Used in: [`05-c4-container.md`](./05-c4-container.md) §3, [`06-threat-model.md`](./06-threat-model.md) §3, [`08-contracts.md`](./08-contracts.md) §1, [`manifesto/02-nfrs.md`](./manifesto/02-nfrs.md) NFR-SEC-60.

## Data-leg

The session's storage data path: the [in-guest mount client](#in-guest-mount-client) dials out to the [Object-store service](#object-store-service) at a network `service_url` (REST-JSON over HTTP/2) over the single [Egress trust-edge](#egress-trust-edge) hop, which terminates TLS, validates the [Storage-JWT](#storage-jwt), and exchanges it at the [Credential issuer](#credential-issuer) for the real filestore credential it injects toward the [Object-store service](#object-store-service). Guest-out, not host-dialled, and tier-universal — every runtime (runc / gVisor / microVM) has a guest network stack. Distinct from the host→guest provisioning push that delivers the mount config and the Storage-JWT before boot ([ADR-0014](./adr/0014-storage-transport-tier-universal-network-leg.md)). A local-volume [storage engine](#storage-engine) ([ADR-0010](./adr/0010-storage-backend-pluggable-adapter.md)) opens no network leg; the leg, when present, always transits the inspection hop.

Used in: [`02-trust-boundaries.md`](./02-trust-boundaries.md) §2, [`05-c4-container.md`](./05-c4-container.md) §4, [`08-contracts.md`](./08-contracts.md) §1.

## Data-plane client

An external caller that reaches the [Web UI](#web-ui) to upload, list, download, or preview-render files. It is either OCU's own authenticated SPA (embeddable cross-origin via an [embed token](#embed-token)) or a headless caller of the file/artifact API. The Web UI reaches storage only through the [Object-store service](#object-store-service); the client never speaks to the [storage engine](#storage-engine) directly. Distinct from the MCP caller (which drives the Control plane) and the Operator (CLI / PAM-JIT). Absent in headless deployments.

Used in: [`03-c4-context.md`](./03-c4-context.md) §4, [`05-c4-container.md`](./05-c4-container.md) §3-§4, [`06-threat-model.md`](./06-threat-model.md) §2, [`08-contracts.md`](./08-contracts.md) §1.

## Embed token

A signed short-TTL token (OIDC-asserted, `exp ≤ 120 s`) the calling peer's backend mints so its already-authenticated user opens OCU's embeddable SPA cross-origin without re-entering credentials. The [Web UI](#web-ui) verifies the token signature and expiry, then sets a first-party session; OCU mints nothing and no OCU upstream secret enters the browser.

Used in: [`05-c4-container.md`](./05-c4-container.md) §3, [`06-threat-model.md`](./06-threat-model.md) §3, [`08-contracts.md`](./08-contracts.md) §3, [`manifesto/02-nfrs.md`](./manifesto/02-nfrs.md) NFR-SEC-82.

## Downloadable

The third storage-authorization axis (beyond scope and intent): a per-object disposition resolved at read by the [storage engine](#storage-engine) behind the [Object-store service](#object-store-service), separating "may read" from "may remove from the sandbox." A non-downloadable object is readable or previewable in-session but the engine mints no egress-eligible artifact for it — the primary control sits at the engine, not at the edge. The [Egress trust-edge](#egress-trust-edge) enforces no storage scope; a `downloadable` deny signal carried to the edge is optional hardening, not the baseline ([ADR-0016](./adr/0016-egress-baseline-inspection-hop-backend-scope.md)).

Used in: [`02-trust-boundaries.md`](./02-trust-boundaries.md) §2, [`06-threat-model.md`](./06-threat-model.md) §3, [`08-contracts.md`](./08-contracts.md) §3, [`manifesto/02-nfrs.md`](./manifesto/02-nfrs.md) NFR-SEC-73.

## Egress trust-edge

The single outbound zone. Every outbound request from the Compute plane goes through here. The guest holds no long-lived upstream secret; the edge attaches the upstream-API authorization, received over Envoy SDS from a static file (solo) or a customer store (enterprise), on the re-originated leg at the egress-wide-bump rung ([Egress posture](#egress-posture)). Injection is gated on a scoped credential the request presents, never on network origin — a request presenting none receives none ([ADR-0007](./adr/0007-egress-auth-mechanism.md), the network-origin injection anti-pattern, P6-E2). On the storage leg the edge validates the guest's weak [Storage-JWT](#storage-jwt) (missing or invalid → 401), strips it, exchanges it (RFC 8693) at the [Credential issuer](#credential-issuer) for the real filestore credential keyed on `filesystem_id`, and overwrites the `Authorization` header with that credential; it holds no signing key and mints nothing — it exchanges. Fail-closed: proxy unreachable → outbound traffic dropped.

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

A ladder of rungs the Egress trust-edge runs at, chosen by what the deployment needs ([ADR-0007](./adr/0007-egress-auth-mechanism.md)):

- **deny-all** — no outbound need; egress off.
- **transparent pass-through** — proxy in path, does not terminate TLS, no CA; reaches unauthenticated endpoints only.
- **egress-wide bump** — proxy terminates TLS at a per-deployment CA (auto-generated, public cert auto-injected into the sandbox trust store at start) and attaches the upstream credential on the re-originated leg; enables in-path content inspection (DLP-ICAP). The default rung once an upstream credential is configured.
- **external SDS source** — enterprise: the credential lifecycle is owned by a customer store off-box.

Bump is the default only when an upstream credential is configured, never imposed on a deployment that needs none, so the one-click solo path holds at every rung. DLP-ICAP is a configuration of the bump rung, not a separate rung.

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
