<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: draft
last-reviewed: 2026-05-28
owner: "@Wide-Moat/architects"
applies-to: next/v1
---

Canonical definitions for terms used across this architecture. Define a term here once; link to it from anywhere else. A term lands here when it appears in ≥ 2 documents.

## Control plane

Orchestrator, RPC surface, session lifecycle, MCP server. Single instance per deployment. Holds no customer payload; metadata-only by design. Outbound to LLM and other upstream goes through the Egress trust-edge — the Control plane is not a model proxy.

Used in: [`02-trust-boundaries.md`](./02-trust-boundaries.md) §2, [`manifesto/02-nfrs.md`](./manifesto/02-nfrs.md).

## Compute plane

The session sandbox zone — one sandbox per session, lifecycle bound to the session, guest agent as PID 1. Substrate is set by the [Sandbox tier](#sandbox-tier): `runc` on the minimal-capability shelf, `gVisor` on the full-capability shelf in v1 (microVM post-v1). Cross-session network reachability disabled.

Used in: [`02-trust-boundaries.md`](./02-trust-boundaries.md) §2, [`manifesto/02-nfrs.md`](./manifesto/02-nfrs.md).

## Credential broker

Per-VM secrets-injection service. Host-side. Bound to loopback / vsock / UDS only. Holds the real upstream credentials; the guest never does. Issues scoped, short-lived tokens to the guest. Distinct from a customer PAM tool — when §02 NFR-COMP-29 says "PAM brokers", it means the customer's privileged-access-management tool, not this component.

Used in: [`02-trust-boundaries.md`](./02-trust-boundaries.md) §2, [`manifesto/02-nfrs.md`](./manifesto/02-nfrs.md).

## Egress trust-edge

The single outbound zone. Every outbound request from the Compute plane goes through here. Network-bound identity (NFR-SEC-27): the fact that traffic arrived from the sandbox at all is the identity. Fail-closed: proxy unreachable → outbound traffic dropped, never bypassed. Configurable posture per [Egress posture](#egress-posture) entry.

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

## Egress JWT

Per-session bearer token issued by the Control plane to the guest agent, bound to `container_name`, TTL ≤ 4 h. Distinct from the broker scoped-JWT (TTL ≤ 15 min, per-resource) and the generic internal RPC token (TTL ≤ 60 min, inter-component). The three TTL classes are independent commitments.

Used in: [`02-trust-boundaries.md`](./02-trust-boundaries.md) §5 / §8 / §8.1, [`manifesto/02-nfrs.md`](./manifesto/02-nfrs.md) NFR-SEC-10/23/29.

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

A shared, documented schema two contexts agree on at their boundary; the emitter conforms to the schema, not to the consumer's internals. The OCSF event between Agent Execution and Compliance Evidence is the canonical instance ([OCSF](#ocsf)). Distinct from Conformist, where one context accepts an upstream's model without negotiation (the MCP authorization spec, provider APIs).

Used in: [`04-bounded-contexts.md`](./04-bounded-contexts.md).

## Compute-time metering

Per-session billing primitives emitted as audit events: CPU-min, RAM-GB-min, storage-GB-day, egress bytes, MCP-call count. Live on the Audit pipeline because they are part of the same hash-chained record stream.

Used in: [`02-trust-boundaries.md`](./02-trust-boundaries.md) §2, [`manifesto/02-nfrs.md`](./manifesto/02-nfrs.md) NFR-COST-05.
