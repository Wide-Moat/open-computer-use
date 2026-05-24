<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: draft
last-reviewed: 2026-05-24
owner: "@Wide-Moat/architects"
applies-to: next/v1
---

Canonical definitions for terms used across this architecture. Define a term here once; link to it from anywhere else. A term lands here when it appears in ≥ 2 documents.

## Control plane

Orchestrator, RPC surface, session lifecycle, MCP server. Single instance per deployment. Holds no customer payload; metadata-only by design. Outbound to LLM and other upstream goes through the Egress trust-edge — the Control plane is not a model proxy.

Used in: [`02-trust-boundaries.md`](./02-trust-boundaries.md) §2, [`manifesto/02-nfrs.md`](./manifesto/02-nfrs.md).

## Compute plane

The session sandbox zone — one sandbox per session, lifecycle bound to the session, guest agent as PID 1. Substrate is container on the minimal-capability shelf, microVM on the full-capability shelf. Cross-session network reachability disabled.

Used in: [`02-trust-boundaries.md`](./02-trust-boundaries.md) §2, [`manifesto/02-nfrs.md`](./manifesto/02-nfrs.md) (formerly named `data-plane` in some §02 rows; converging on "Compute plane").

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

- **Minimal-capability shelf** — single-tenant, host-local Ed25519 signing keys, auto-generated self-signed CA, file-system audit sink. The one-click solo install path.
- **Full-capability shelf** — customer HSM rooted, per-tenant SPIFFE trust domain, customer-CA-rooted egress, OCSF bridges to customer SIEM.

Both shelves run the same binary; the difference is configuration plus presence of customer-supplied facilities (HSM, CA, SIEM bridge). Not a SKU split.

Used in: [`02-trust-boundaries.md`](./02-trust-boundaries.md) §2 / §8 / §10, [`manifesto/02-nfrs.md`](./manifesto/02-nfrs.md).

## Isolation tier (T0…T3)

Per-tenant deployment shape menu. Picks the substrate, not the invariants — boundary properties hold for every tier.

- T0 logical — row-level filter, shared kernel.
- T1 namespace — Kubernetes namespace + NetworkPolicy + RBAC + ResourceQuota.
- T2 VPC / VNet — per-tenant VPC, no peering.
- T3 dedicated cluster — dedicated control plane per tenant.

Higher isolation tiers (dedicated hardware, customer-owned cage) are tracked as candidates in open question `arch/cross-tenant-isolation-grading`; promote when a named workload requires them.

Used in: [`02-trust-boundaries.md`](./02-trust-boundaries.md) §4.

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

External append-only log that the customer chooses (public Sigstore Rekor, a customer-private Rekor, or a CT-log instance). The Audit pipeline submits the daily Merkle head of the hash-chained audit store; the log operator signs the Merkle head, we sign only the submission envelope. Provides tamper-evidence the customer can verify against an operator they trust.

Used in: [`02-trust-boundaries.md`](./02-trust-boundaries.md) §3 / §8.1 / §10 / §12, [`manifesto/02-nfrs.md`](./manifesto/02-nfrs.md) NFR-SEC-03.

## Compute-time metering

Per-session billing primitives emitted as audit events: CPU-min, RAM-GB-min, storage-GB-day, egress bytes, MCP-call count. Live on the Audit pipeline because they are part of the same hash-chained record stream.

Used in: [`02-trust-boundaries.md`](./02-trust-boundaries.md) §2, [`manifesto/02-nfrs.md`](./manifesto/02-nfrs.md) NFR-COST-05.
