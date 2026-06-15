<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: draft
last-reviewed: 2026-06-02
owner: "@Wide-Moat/architects"
applies-to: next/v1
---

When a feature limitation is an acceptable minimal-shelf trade-off versus a silent security gap that must be gated or labelled. Audience: architects reviewing a component spec or feature proposal for the solo / minimal-shelf tier.

## Shelf split

Both tiers ship the same set of containers ([05-c4-container.md](../05-c4-container.md) §5); only the substrate and credential management differ.

- **Minimal shelf** — single operator, self-signed per-deployment CA, file-system audit, host-rooted operator credential. The one-click `docker-compose up` path: no external IdP, no cloud credential, no pre-staged key.
- **Full shelf** — customer IdP-asserted operator identity, customer-PKI-rooted signers, external SIEM sink, dynamic SDS credential minting.

The runtime tier (`runc` / gVisor / microVM) is selected orthogonally by `workload_trust_profile`, not by the shelf (§"Tier versus shelf").

The feature set is the same on both; every v1 GA feature must be demonstrable on the minimal shelf with defaults in place.

## Acceptable limitation

A limitation is acceptable only if it meets all three:

1. **The minimal-shelf default does not block the primary workflow.** A solo developer or a hardening pilot builds agents, runs sessions, calls tools, and reads results with no configuration beyond `docker-compose up`.
2. **The limitation is discoverable in config and docs.** Enabling an optional feature (external SIEM, credential rotation, DLP, a higher runtime tier) states what the minimal shelf trades away — a config comment or a startup log line, not silence.
3. **No threat-model invariant erodes without explicit operator choice.** The solo path keeps the core locked in code: the guest holds no long-lived upstream secret ([NFR-SEC-23](02-nfrs.md)), audit events are hash-linked ([NFR-SEC-03](02-nfrs.md)), the kill-switch stays operative on the single-instance shelf ([NFR-SEC-01](02-nfrs.md), [NFR-SEC-55](02-nfrs.md)), and session limits hold — idle ≤15 min ([NFR-SEC-40](02-nfrs.md)), absolute ≤12 h ([NFR-SEC-41](02-nfrs.md)).

## Unacceptable limitation

Gate to full shelf, or label it a security gap, if:

- **A core invariant degrades silently** — e.g. audit not hash-linked on solo (breaks NFR-SEC-03), or the guest reaching an upstream secret by default (breaks NFR-SEC-23).
- **The primary workflow is blocked with no working alternative** — e.g. no way to authenticate an operator, or sessions that time out with no adjustable window.
- **It is "not built yet", not an architectural choice** — unfinished work belongs in a backlog, not behind a starter-mode label.

| Verdict | Example |
|---|---|
| Acceptable | The Control plane holds the Storage-JWT signing key and mints the weak Storage-JWT on both shelves (T1, [NFR-SEC-25](02-nfrs.md), [NFR-SEC-60](02-nfrs.md)); on the minimal shelf the RFC 8693 exchange counterparty for the real filestore credential is bundled, and the full shelf brings a customer-provided credential authority (Vault/KMS), the trade is documented, and the sole path to it is the full shelf. |
| Acceptable | The Egress trust-edge on the minimal shelf auto-generates a per-deployment CA instead of integrating a customer KMS ([ADR-0007](../adr/0007-egress-auth-mechanism.md)); a full-shelf deployer brings their PKI. |
| Not acceptable | Audit not written on the minimal shelf because no external SIEM is configured. Audit is not optional; with the sink off, events still write to a local hash-chained store (NFR-SEC-03). |
| Not acceptable | Session idle timeout hard-coded with no adjustable window, breaking the workflow. A knob defaulting conservatively is fine; no knob is not (NFR-SEC-40). |

## Tier versus shelf

The `workload_trust_profile` selects the sandbox runtime tier ([ADR-0003](../adr/0003-sandbox-runtime-tier-ladder.md), [NFR-SEC-38](02-nfrs.md)); the shelf is orthogonal. Both shelves carry every runtime tier where the host supports it, so a solo deployer can pick a hardened tier without leaving the minimal shelf. The shelf split is about how a credential reaches a component and the operational burden (IdP, SIEM), not about the guest isolation boundary.
