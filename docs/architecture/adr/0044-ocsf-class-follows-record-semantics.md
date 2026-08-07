<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-08-07
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
amends: ['0009-audit-pipeline-pluggable-by-contract.md']
compliance-impact: [SOC2-CC7.2, ISO27001-A.8.15, NYDFS-500.06, DORA-Art.12]
license-impact: none
threat-mitigation-link: ../components/07-audit-pipeline.md
---

Fixes how an emitter picks the OCSF class for an audit record, and what the channel does and does not decide — for anyone adding an audited action or reviewing a fan-in contract change.

# ADR-0044: The OCSF class follows the record, the channel names the source

## Status

`proposed` — amends [ADR-0009](0009-audit-pipeline-pluggable-by-contract.md), which fixes the fan-in seam and host-attested ingest but leaves class selection to the contract without saying what governs when an emitter and the contract disagree.

## Context

The audit fan-in contract gives each source container one channel, and the channel address *is* the source identity. Each channel declares the message set it carries. The control-plane channel declares Authentication (OCSF 3002) and Entity Management (3004); the MCP gateway channel declares API Activity (6003).

The control plane emits 6003 for every privileged action it records, with the verb carried in `metadata.unmapped`.

Three things are wrong with that, and only the first is about the contract:

The class is not the one its channel declares. A source is publishing a message shape its own channel does not carry, which is the invariant the per-channel message set exists to hold.

The events are not conformant 6003 either. OCSF's API Activity class carries the operation in an `api` object; the emitted event has no such field, so the verb has nowhere to go but `unmapped` — the bucket OCSF reserves for fields that could not be mapped. A detection keyed on the primary discriminator would find it in the one place a schema promises nothing.

The single class also cannot carry the taxonomy. Several actions have no CRUD slot and collapse to activity Other(99), so records with unrelated meaning arrive under one `type_uid`.

The reason this has not broken anything is that the control plane commits to its own durable sink and no per-channel conformance gate runs yet. It becomes a hard ingest rejection the day that gate lands.

## Decision

We will choose the OCSF class from what the record *is*, and let the channel carry source identity alone.

- **The class follows record semantics.** An emitter maps each record family to the OCSF class whose schema fits it, and populates that class's own required objects. A class is not selected for uniformity, for convenience, or because one class is already wired.
- **The channel is the source discriminator, and the only one.** Source identity is the verified channel the event arrived on, never a payload field ([NFR-SEC-09](../manifesto/02-nfrs.md), [NFR-SEC-56](../manifesto/02-nfrs.md)). It follows that one class may legitimately appear on several channels: the same record shape observed at two points is two sources, disambiguated by channel, not by class.
- **`metadata.unmapped` never carries a primary discriminator.** It holds fields with no first-class slot in the chosen class. If the verb, the subject, or the outcome of a record lands there, the class is the wrong one.
- **A class a channel does not declare is a contract change, not an emitter decision.** Where a record family genuinely fits a class the channel omits, the contract gains that message additively and the emitter follows. An emitter never resolves the disagreement by emitting anyway.
- **A declared message with no emitter is a coverage gap.** The contract declaring a class the source never sends is a defect on the emitter's side, tracked as such rather than resolved by deleting the declaration.

## Consequences

Emitters carry per-class field sets rather than one event struct. That is the cost of conformance: a class's required objects are part of the class, and an event missing them is not that class regardless of its `class_uid`.

Detections become class-native. A reviewer filtering on entity type or API operation reads fields the schema defines, instead of parsing an `unmapped` blob whose shape no contract fixes.

Adding an audited action now asks which class it belongs to. That question has a wrong answer, which is the point — the alternative let every action inherit a class by default and never surfaced the mismatch.

Contract and emitter move in the same direction but not the same commit. The contract change is additive and ships first; an emitter that switched first would send a class the fan-in does not yet accept.

## Alternatives

**One class per source, discriminated by `activity_id`.** Rejected: it is the state that failed. The enum is CRUD-shaped and cannot express the control plane's verbs, so the surplus collapses to Other and the real discriminator migrates to `unmapped`.

**Let the channel's declared set decide the class, mapping each record to whatever the channel already carries.** Rejected: it inverts the reasoning. The channel says who is speaking, not what may be said, and forcing an ill-fitting record into a declared class reproduces the `unmapped` problem one level down.

**Emit the honest class regardless of what the channel declares, and reconcile the contract later.** Rejected: the per-channel message set is what makes fan-in validation possible at all. An emitter that publishes outside it makes every conformance check advisory.

**Define OCU-private classes for records that fit no OCSF class.** Rejected for v1: the value of OCSF is that a customer's SIEM already understands it. A record with no honest class is carried as an explicit open item rather than given a private one.
