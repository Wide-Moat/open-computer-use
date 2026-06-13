<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: draft
last-reviewed: 2026-06-13
owner: "@Wide-Moat/architects"
applies-to: next/v1
---

Index of the `components/` directory: one spec slot per Layer 6 container, its spec status, and the decisions and contracts already bound to it. Audience: an engineer about to open or write a component spec.

## 1. Index scope

Layer 6 ([`05-c4-container.md`](../05-c4-container.md) §3) is the source of truth for what each container does; this index does not restate it — it records where each is specified and what already binds it.

A spec is added per [PROCESS.md](../PROCESS.md): open an issue, create `components/NN-<name>.md` from [`0000-template.md`](0000-template.md) at `status: stub`, discuss in the PR. The number `NN` is the container's row order below; it is assigned here and does not change once given.

## 2. Container specs

Each row links the container's responsibility (Layer 6) and lists the spec file, its current status, and the ADRs and contracts that already bind it. `—` in the Bound ADRs column means no ADR binds the container yet; opening one is its own PR. `NN` is the container row identifier — there is no `03`, the set is the six containers of [`05-c4-container.md`](../05-c4-container.md) §3, and the number does not track a trust zone (the Session sandbox is container 05, trust zone 3).

| NN | Container | Spec | Status | Bound ADRs | Bound contracts |
|---|---|---|---|---|---|
| 01 | MCP gateway (agent-facing) | [`01-mcp-gateway.md`](01-mcp-gateway.md) | draft | — | [`mcp/ocu-constraints`](../../../contracts/mcp/2025-06-18/ocu-constraints.schema.json) |
| 02 | Control / operator API | [`02-control-operator-api.md`](02-control-operator-api.md) | draft | [0004](../adr/0004-operator-authentication-substrate.md) | — |
| 04 | Storage broker | [`04-storage-broker.md`](04-storage-broker.md) | draft | [0002](../adr/0002-session-view-descriptor.md), [0010](../adr/0010-storage-backend-pluggable-adapter.md), [0011](../adr/0011-storage-egress-lane.md) | [`storage/mount-config`](../../../contracts/storage/mount-config.schema.json), [`storage/file-ops`](../../../contracts/storage/file-ops.schema.json), [`storage/file-artifact-api`](../../../contracts/storage/file-artifact-api.schema.json) |
| 05 | Session sandbox `[1..N]` | [`05-session-sandbox.md`](05-session-sandbox.md) | draft | [0003](../adr/0003-sandbox-runtime-tier-ladder.md) | [`exec/exec-channel`](../../../contracts/exec/exec-channel.schema.json) |
| 06 | Egress trust-edge proxy | [`06-egress-trust-edge.md`](06-egress-trust-edge.md) | draft | [0005](../adr/0005-egress-credential-delivery-envoy-sds.md), [0006](../adr/0006-egress-forward-proxy-substrate.md), [0007](../adr/0007-egress-auth-mechanism.md), [0008](../adr/0008-session-egress-attribution.md) | — |
| 07 | Audit pipeline | [`07-audit-pipeline.md`](07-audit-pipeline.md) | draft | [0009](../adr/0009-audit-pipeline-pluggable-by-contract.md) | [`audit/audit-fanin`](../../../contracts/audit/audit-fanin.asyncapi.yaml) |

The guest agent is the process that constitutes the Session sandbox container ([`05-c4-container.md`](../05-c4-container.md) §3), not a separate row; its protocol is specified inside `05-session-sandbox.md`.

## 3. Implementation repositories

The specs above are the source of truth; the code lives in separate public repositories under the `Wide-Moat` org. Each implements the containers named here against the contracts and ADRs the table binds.

| Repository | Implements | Side |
|---|---|---|
| [`ocu-sandbox`](https://github.com/Wide-Moat/ocu-sandbox) | Control / operator API (02), Session sandbox (05) | Host control plane + sandbox executor |
| [`ocu-filestore`](https://github.com/Wide-Moat/ocu-filestore) | Storage broker (04) | Host-side broker daemon |
| [`ocu-rclone-filestore`](https://github.com/Wide-Moat/ocu-rclone-filestore) | Storage broker (04), south face | Guest-side mount binary |

Containers 01 (MCP gateway), 06 (Egress trust-edge), and 07 (Audit pipeline) have no implementation repository yet.

## 4. Maturation order

All six are at `draft`. The ones a contract or a pending decision already pins harden to `proposed`/`accepted` first, because their spec has the least free design left and the most to verify against:

1. **Storage broker** — three contracts and seven NFR anchors already fix its surface; the spec records the two-face component split and the per-tenant instantiation question ([#175](https://github.com/Wide-Moat/open-computer-use/issues/175)).
2. **Session sandbox** — the exec-channel contract fixes its machine edge; the runtime-tier-by-`workload_trust_profile` decision is fixed by [ADR-0003](../adr/0003-sandbox-runtime-tier-ladder.md) and the sub-container split is open ([#174](https://github.com/Wide-Moat/open-computer-use/issues/174)).
3. **Egress trust-edge** — no built contract yet, but the deny-reason and egress-wide-bump behaviour are NFR-anchored and cross the broker boundary; the auth mechanism is fixed by [ADR-0007](../adr/0007-egress-auth-mechanism.md) (edge-inject in v1), the substrate is Envoy plus a self-hosted SDS minting service, and the upstream credential arrives over Envoy SDS.

The other three reach `accepted` once these three settle their shared invariants and the ADRs their `adr:` keys cite ([ADR-0003](../adr/0003-sandbox-runtime-tier-ladder.md) runtime tier, [ADR-0004](../adr/0004-operator-authentication-substrate.md) operator-auth, [ADR-0010](../adr/0010-storage-backend-pluggable-adapter.md) object-store engine) move from `proposed` to `accepted`.
