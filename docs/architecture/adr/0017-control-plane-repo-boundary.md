<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-06-14
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
compliance-impact: [SOC2-CC6.1, NYDFS-500.15]
license-impact: none
threat-mitigation-link: ../06-threat-model.md
blocks: []
blockedBy: [0015]
---

The one-per-deployment Control plane and the per-session executor are distinct deployables across an interface seam; the Control plane mints and delivers each weak Storage-JWT and holds the Storage-JWT signing key, while the per-session executor holds none. Audience: engineers wiring the build's repository layout and anyone auditing where the storage signing key lives.

# ADR-0017: Control plane and per-session executor are distinct deployables

## Status

`proposed`

## Context

Canon models C4 containers but states no repository or deployable boundary for any of them, and the Control plane and the per-session executor have so far co-housed in one repository (`ocu-sandbox`, [`components/00-overview.md`](../components/00-overview.md) §3). Three forces make the boundary load-bearing.

First, the two units differ on every deployment axis: the Control plane runs one-per-deployment, the executor runs `[1..N]` per session, and they reach each other over a host-dials-guest control channel (the WebSocket process channel and the host-only HTTP/vsock control port), not in-process.

Second, the executor depends on a runtime interface plus a sentinel, not the concrete runtime implementation — only a composition root wires both — so the split already exists at the code seam and the cost is in stating it, not in achieving it.

Third, the storage recut ([ADR-0013](0013-storage-credential-custody.md)) places the Storage-JWT signing key at the Control plane: it mints a `filesystem_id`-scoped weak session JWT, delivers it over the host control channel into the mount config, scrubs the on-disk source after handoff, installs the guest's control-WebSocket verify-key, and publishes a JWKS the egress edge validates against. The executor holds no signing path. A repository layout that leaves the boundary unstated lets the credential-mint path and the per-session executor collapse into one blast radius by default, and lets a fixed container count pre-reject the carve-out the storage recut needs ([ADR-0015](0015-storage-decomposition-by-trust-plane.md) carves the Web UI out of the former single welded storage component).

## Decision

We will state the repository and deployable boundary in canon — the one-per-deployment Control plane (container 02: lifecycle, quota, denylist, kill-switch, and credential MINT and DELIVERY) and the per-session executor (container 05) are distinct deployables across an interface seam, with the Control plane carrying the Storage-JWT mint/delivery/provisioning role: it mints the weak session JWT, delivers it, installs the guest verify-key, and holds the Storage-JWT signing key ([ADR-0013](0013-storage-credential-custody.md)).

The Control plane is its own repository, `ocu-control`, holds the Storage-JWT signing key ([ADR-0013](0013-storage-credential-custody.md)), and `ocu-sandbox` narrows to the per-session executor (container 05). The MCP gateway (01), the Audit pipeline (07), and the egress SDS leaf-minter (06, [ADR-0016](0016-egress-baseline-inspection-hop-backend-scope.md)) are each distinct deployables with their own repository decisions; none folds into `ocu-control`. The credential authority that issues the real filestore credential at the exchange ([ADR-0019](0019-egress-exchanges-filestore-credential.md)) is separately named and may be external/customer-provided.

## Consequences

- **The boundary is canon, not an artifact of how the code happens to be packaged.** [`components/00-overview.md`](../components/00-overview.md) §3 stops asserting a present-tense "implements 02" for `ocu-sandbox` and gains a repository column and a maturity/state column (the overview edit is follow-on work routed through PROCESS, gated on this ADR), so an entry never reads as a present-tense completion claim.
- **`ocu-control` owns container 02; `ocu-sandbox` narrows to container 05.** The credential-mint role gets a deployable home: [`components/02-control-operator-api.md`](../components/02-control-operator-api.md) records `ocu-control` as the Storage-JWT mint and delivery path — it mints the `filesystem_id`-scoped weak session JWT, delivers it into the mount config before the mount client starts, installs the guest's verify-key, and holds the Storage-JWT signing key ([ADR-0013](0013-storage-credential-custody.md)). Filing the executor as the Session sandbox ([`components/05-session-sandbox.md`](../components/05-session-sandbox.md)) plus a thin control driver for [`components/02-control-operator-api.md`](../components/02-control-operator-api.md) — rather than a storage face — is fixed by [ADR-0015](0015-storage-decomposition-by-trust-plane.md).
- **The MCP gateway (01), the Audit pipeline (07), and the egress SDS leaf-minter (06) are recorded as planned with their repositories TBD, not folded into `ocu-control`.** The overview marks them maturity `none`; each is a separate deployable that earns its own repository decision when its spec hardens, so the delivery plane does not accrete the agent-path gateway, the audit chain-of-custody, or the egress leaf-minting key.
- The deployable boundary keeps the Storage-JWT signing key and the per-session executor in separate blast radii: the key lives at the Control plane (`ocu-control`, which also mints and delivers the token), and the per-session executor (`ocu-sandbox`) holds none. One executor compromise reaches no signing key — the key is at the Control plane, never in the executor — and the Control plane that mints the token is a separately deployed unit reached only over the host-dialled control channel ([`02-trust-boundaries.md`](../02-trust-boundaries.md) §4 direction). The own-repository layout gives `ocu-control` its own CI, CODEOWNERS, and release cadence.
- The count of containers stays an observation, not an invariant — the later Web UI carve-out ([ADR-0015](0015-storage-decomposition-by-trust-plane.md)) and any future deployable add a repository row without an ADR rejecting them on "it would be the Nth container".
- Negative: two repositories cost a cross-repository interface contract that one repository hides in a shared build. The seam is the runtime interface plus sentinel already present; the contract is stated once and versioned. A co-housed single binary remains a valid operator packaging of the same two deployables, so the boundary is a source-and-blast-radius statement, not a forced runtime topology.

## Alternatives considered

- **Leave the repository and deployable boundary unstated (status quo).** Rejected: the code defaulted to co-housing the Control plane and the executor, so the storage delivery path and the per-session executor share one blast radius by omission, and the repository map silently contradicts the build's own layout and roadmap. An unstated boundary also lets a fixed container count pre-reject the storage recut's carve-out. The deployable-boundary anti-recurrence rule requires every container spec to state its boundary; silence fails that rule.
- **Declare one permanent repository for both the Control plane and the executor (02 + 05).** Rejected: the two units differ on lifecycle (one-per-deployment vs per-session `[1..N]`), scaling, and blast radius, and the executor already depends on a runtime interface and sentinel rather than the concrete runtime — only a composition root wires them, so the packages are already interface-decoupled. A permanent single repository freezes a coupling the code does not have and welds the credential-delivery path to the per-session unit it must outlive and out-scope.

## Compliance impact

- `SOC2-CC6.1` / `NYDFS-500.15`: backend-storage-credential confidentiality and key-custody segregation. The Storage-JWT signing key lives at the Control plane (`ocu-control`), which mints and delivers the token; the per-session executor and the guest hold no signing path. Stating the deployable boundary makes the segregation auditable against the deployment topology, not merely against the source layout.

## License impact

None. The decision concerns repository layout and the deployable boundary; it adds no dependency and changes no distribution term.

## Threat mitigation

Anchors the mint and delivery path of the Storage-JWT to a named deployable (`ocu-control`, container 02, which holds the Storage-JWT signing key) distinct from the per-session executor (`ocu-sandbox`, container 05), supporting the P4 storage and P6 control-plane custody anchors in [`06-threat-model.md`](../06-threat-model.md). A compromise of one per-session executor reaches no signing key — the key is at the Control plane — and the Control plane that mints the token is a separately deployed unit reached only over the host-dialled control channel. A compromised Control plane can mint Storage-JWTs for any `filesystem_id` for the window — the accepted T1 trade, a stated consequence on the Control-plane threat-model rows, not a defect.

## Open questions

1. Repository home for the MCP gateway (01) and the Audit pipeline (07) — assigned now or left planned until each spec hardens; the Audit pipeline needs a repository to carry its bundled bill-of-materials row and SLSA L3 provenance — [#270](https://github.com/Wide-Moat/open-computer-use/issues/270).
2. Repository home for the egress SDS leaf-minter — its own repository versus co-housing with the Envoy edge, settled by a later ADR; it is not `ocu-control` — [#271](https://github.com/Wide-Moat/open-computer-use/issues/271).

---

Hard cap: 200 lines.
