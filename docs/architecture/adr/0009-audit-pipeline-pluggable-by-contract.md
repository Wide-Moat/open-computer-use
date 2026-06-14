<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-06-06
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
compliance-impact: [SOC2-CC7.2, ISO27001-A.8.15, NYDFS-500.06, DORA-Art.10, EU-AI-Act-Art.12]
license-impact: none
threat-mitigation-link: ../06-threat-model.md
---

The audit pipeline's durable bus, WORM store, SIEM, and transparency log are integration contracts the customer fills; OCU delivers only the chain of custody and a local durable commit.

# ADR-0009: Audit pipeline is pluggable-by-contract

## Status

`proposed`

## Context

The Audit pipeline ([component 07](../components/07-audit-pipeline.md), trust-zone 5 of [02-trust-boundaries.md](../02-trust-boundaries.md) §2) turns each source's OCSF event into a durable, ordered, tamper-evident record and forwards it to a customer sink. Two substrates were left undecided: the durable-bus product and the WORM cold-tier store , named in the [component 07](../components/07-audit-pipeline.md) Shelf delta as pluggable seams behind the OCU-owned local commit, not decided in that spec. [02-trust-boundaries.md](../02-trust-boundaries.md) §10 held "mandatory in code, pluggable in sinks" unanchored by an ADR.

The build-scope principle ([03-non-negotiables.md](../manifesto/03-non-negotiables.md)) sets the rule: OCU builds the control plane and the sandbox; every neighbouring capability is integrated off-the-shelf, bundled only as a one-click-solo reference. A bus, an object store, a SIEM, and a transparency log are neighbouring systems that run when OCU is stopped. The open question is where, inside the audit pipeline, the build/buy line falls — what OCU must author versus what the customer plugs in.

## Decision

We draw the build/buy line once for the whole audit tract: OCU delivers the chain of custody and a local durable commit; everything downstream — bus, store, SIEM, transparency log, signing-key custody — is a published contract the customer fills, with a one-click-solo reference default, carrying no OCU CVE responsibility.

## Consequences

OCU's mandatory core (the DELIVER side of [02-nfrs.md](../manifesto/02-nfrs.md) §Scope ownership), present on both shelves and chaos-testable:

- **Host-attested ingest** — binds the OCSF `source` to the verified channel identity, never the payload ([NFR-SEC-09](../manifesto/02-nfrs.md)).
- **A local durable commit** — fsync-then-ack on the always-present file-system sink, before the source's publish is acknowledged. This is what [NFR-REL-03](../manifesto/02-nfrs.md) (RPO = 0) forces: an arbitrary customer bus whose ack semantics OCU does not control cannot hold RPO = 0, so the no-loss commit point is OCU's, upstream of any seam. It does not force OCU to own the bus. Write-before-ack and "no synchronous DB on the critical path" are [NFR-REL-12](../manifesto/02-nfrs.md).
- **Chain writer + Merkle-head accumulator + envelope signer** — per-source hash linkage, the daily head, and the submission-envelope signature ([NFR-SEC-03](../manifesto/02-nfrs.md)). OCU signs only the envelope; the transparency-log operator signs the head.
- **OCSF envelope and retention-policy enforcement** — the mandatory fields out-of-band of the payload ([NFR-MAINT-AUDIT-SCHEMA](../manifesto/02-nfrs.md)) and the 7 y / 10 y floor on both shelves ([NFR-COMP-01](../manifesto/02-nfrs.md)).

The pluggable seams (the ENABLE side), each a contract plus a solo-reference default:

| Seam | Solo reference | Full-shelf | Open question |
|---|---|---|---|
| Durable-bus product | embedded append-only file / WAL | customer NATS or Kafka | [#150](https://github.com/Wide-Moat/open-computer-use/issues/150) |
| WORM cold-tier store | none — FS + hash-chain is the floor | customer S3 Object Lock Compliance / Ceph RGW | — |
| SIEM sink | file-system sink only | OCSF bridge (Splunk HEC, syslog-TLS, ECS, UDM) | [#150](https://github.com/Wide-Moat/open-computer-use/issues/150) |
| Transparency-log endpoint | local Merkle head | customer-pointed (public or private) | [#151](https://github.com/Wide-Moat/open-computer-use/issues/151) |
| Envelope-key custody | host-local key | HSM-rooted PKCS#11 / KMIP | — |

- Positive: the minimal shelf runs from one `docker-compose up` with no bus, no object store, and no SIEM; the FS sink plus hash-chain and signed Merkle head is the complete tamper-evidence story. The enterprise shelf points each seam at infrastructure the customer already operates and audits.
- Positive: OCU carries no CVE, SBOM, or version lifecycle for a bus, store, SIEM, or log it does not write. The reference defaults exist for the solo path, not as a bundled product line.
- Negative: the minimal-shelf tamper-evidence is detective (the chain detects deletion or truncation after the fact), not the preventive WORM-immutability of the full shelf ([NFR-COMP-01](../manifesto/02-nfrs.md)). A deployment whose threat model needs immutability against a privileged actor wires the WORM seam.
- Neutral: this resolves the two [component 07](../components/07-audit-pipeline.md) Shelf-delta picks in one boundary rule and anchors [02-trust-boundaries.md](../02-trust-boundaries.md) §10 to an ADR. Per-seam transport and backpressure detail stays open ([#150](https://github.com/Wide-Moat/open-computer-use/issues/150), [#151](https://github.com/Wide-Moat/open-computer-use/issues/151)).

## Alternatives considered

- **Bundle a durable bus (ship NATS or Kafka, own its CVE/SBOM/version lifecycle).** Rejected: a bus is a neighbouring system that runs without OCU, so bundling it violates the build-scope principle ([03-non-negotiables.md](../manifesto/03-non-negotiables.md)) and makes OCU accountable for a CVE surface the customer's own platform team already operates. The reference default for the solo path is an embedded WAL, not a bundled bus product.
- **Make the durable commit pluggable too (write straight to the customer's bus, no OCU-local commit).** Rejected: [NFR-REL-03](../manifesto/02-nfrs.md) RPO = 0 cannot hold against an arbitrary bus whose ack semantics OCU does not control — acking before the bus confirms durability opens a loss window, blocking on a slow bus violates the spill-not-block behaviour of [NFR-REL-12](../manifesto/02-nfrs.md). The thin local commit is the one part that cannot be a pure plug.
- **Two ADRs, one per substrate (bus / WORM).** Rejected: under the build-scope principle both are pluggable seams on the same side of one boundary, so the build/buy line is a single decision; splitting it duplicates the rationale and fragments a Nygard one-decision-per-file record. The [ADR-0005](0005-egress-credential-delivery-envoy-sds.md) precedent records one role for one container.

## Compliance impact

- `SOC2-CC7.2` / `ISO27001-A.8.15`: the chain of custody (hash linkage, Merkle head, envelope signature) is OCU-authored and present on both shelves; logging integrity does not depend on the customer's choice of sink.
- `NYDFS-500.06` / `DORA-Art.10`: the audit trail and its retention floor are machine-enforced on both shelves ([NFR-COMP-01](../manifesto/02-nfrs.md)); the WORM substrate satisfies the immutability expectation when the full-shelf seam is wired.
- `EU-AI-Act-Art.12`: the record-keeping obligation is met by the mandatory core; the transparency-log endpoint is the customer's choice of public or private operator.

## License impact

None. No bus, store, SIEM, or transparency-log dependency is bundled by this decision; the reference defaults (embedded WAL, file-system sink, local Merkle head) are OCU code. Customer-provided substrates are integrated over their standard APIs.

## Threat mitigation

Addresses Tampering and Repudiation on the audit path: the chain of custody is authored before any record leaves the pipeline, so a record's integrity is independent of the pluggable sink, and the local durable commit holds RPO = 0 against a stalled or hostile downstream. Per-seam residuals — SIEM-bridge backpressure ([#150](https://github.com/Wide-Moat/open-computer-use/issues/150)) and the transparency-log publishing path ([#151](https://github.com/Wide-Moat/open-computer-use/issues/151)) — stay open.
