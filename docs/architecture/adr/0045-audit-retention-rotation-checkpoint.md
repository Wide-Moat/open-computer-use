<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-08-08
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
amends: ['0009-audit-pipeline-pluggable-by-contract.md']
compliance-impact: [SOC2-CC7.2, ISO27001-A.8.15, NYDFS-500.06, DORA-Art.12, FCA-SYSC-9]
license-impact: none
threat-mitigation-link: ../components/07-audit-pipeline.md
---

Fixes how the audit store rotates hot records to the cold tier without moving boot behind the customer's WORM mount or breaking genesis verification — for anyone implementing NFR-COMP-01 retention or reviewing the pipeline's verify paths.

# ADR-0045: Audit retention rotates through a signed checkpoint; boot never crosses the cold seam

## Status

`proposed` — amends [ADR-0009](0009-audit-pipeline-pluggable-by-contract.md), which fixes the WORM cold-tier substrate as a customer seam behind the OCU-owned local commit but leaves open how rotation and verification interact.

## Context

NFR-COMP-01 requires two tiers — hot ≤ 90 d, then cold to a 7 y floor — machine-enforced by the pipeline on both shelves. The store today is one append-only WAL, and every verify path is cumulative from genesis: boot recovery, the daily Merkle head, and the offline verifier all read the full record set. Rotation under that model forces a choice between two failures: truncating the hot file breaks genesis verification, and verifying the union at boot makes every daemon restart read 7–10 years of segments through the customer's cold mount — a mount outage becomes an audit outage, which NFR-SEC-45's fail-closed rule turns into a platform-wide denial of privileged actions. ADR-0009 places the no-loss commit point upstream of every seam precisely so OCU availability never depends on the customer substrate. A further trap is physical: a crash mid-copy leaves a partial object, and under S3 Object Lock Compliance a partial written at its final name is undeletable for the full retention term, burning that segment name permanently.

## Decision

The audit store becomes an ordered segment set: one active append file plus sealed segments, named in commit order. Sealing fsyncs, closes, and atomically renames the active file in the hot directory, then reopens a fresh active file. Per-source chain linkage remains the ordering authority; segment names are a hint that verification cross-checks.

Rotation moves a sealed segment hot → cold as copy-verify-rename: copy to an attempt-unique temporary name in the cold directory, fsync, re-read the cold bytes and compare digest and frame checksums, atomically rename to the final segment name, fsync, and only then remove the hot copy. A torn temporary is discarded on resume — it is never "divergent". A complete cold segment that differs from a surviving hot copy refuses boot. Under a WORM mount, orphaned temporaries may persist object-locked; they carry attempt-unique names, appear in no inventory, and are inert.

The verification perimeter splits:

- **Boot** verifies the hot tier only, anchored on the signed retention checkpoint: per-source chain tips, Merkle tree size, and the accumulator frontier recorded at the last rotation. Recovery verifies hot chains from those anchors, rebuilds the current Merkle state from frontier plus hot leaves, and cross-checks the freshest signed head by consistency proof. Boot never reads the cold directory, so a cold-mount outage cannot take the audit plane down and boot cost is bounded by the hot tier.
- **The offline verifier** owns the whole horizon: cold + hot union in segment order, per-source chains from genesis, recomputed head against the signed head, inclusion proofs at original global indexes, and checkpoint/inventory audit against directory contents.

The retention checkpoint is a signed artifact: retention policy plus per-segment inventory (name, digest, record count, IngestTime bounds, global index bounds) plus the boot anchors. It is signed by the existing host-local key under a distinct domain tag; NFR-SEC-03's key duty widens from "submission envelope" to "submission envelope and retention checkpoint". Checkpoint updates are ordered inside the rotation sequence so a crash between rename and checkpoint rewrite resumes as an in-progress rotation, not a tamper alarm.

Failure posture: rotation failure never blocks `Admit` — the fsync-then-ack commit stays upstream of the seam. A rotation that cannot complete, a record aging past the hot ceiling, and any accepted retention-policy change each self-emit a chain-linked record on the pipeline's own channel (the NFR-SEC-45 evidence path; the emission mechanism already serves saturation events). A policy shrink below the pinned floor refuses boot. No code path deletes a committed record; disposal at floor expiry is out of scope and would require its own ADR.

## Consequences

Boot-time tamper evidence for the cold tier is deliberately detective, not preventive: a cold tamper is caught by the offline verifier and the daily head, not by the daemon's own boot — the same shelf semantics ADR-0009 already assigns the minimal shelf. The checkpoint becomes a second signed artifact class the offline verifier must audit; its anchors are exactly what a future hot-tier-pruning decision would consume, so that decision needs no artifact migration. Segment inventories make retention externally auditable (FCA SYSC 9 / DORA evidence: policy, per-segment ages, rotation timestamps, breach events on the chain).

## Alternatives considered

- **Union verification at boot** — rejected: couples daemon availability to the customer cold mount and makes restart cost grow with the retention horizon; contradicts ADR-0009's upstream-of-seam commit point.
- **Truncate hot after rotation without a signed anchor** — rejected: the next boot re-anchors chains on genesis over a partial record set, and the daily head's cumulative tree size becomes unverifiable — silent loss of tamper evidence.
- **A dedicated retention signing key** — rejected: doubles solo-shelf key custody with no threat-model gain over domain-tagged messages under one key; the full shelf already upgrades custody wholesale via the HSM seam.
- **Direct write to the final cold name** — rejected: a crash mid-copy under S3 Object Lock Compliance locks a partial object at the final name for the retention term, permanently burning the segment name.
