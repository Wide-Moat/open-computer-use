<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: draft
last-reviewed: 2026-05-31
owner: "@Wide-Moat/architects"
applies-to: next/v1
---

The wire contracts OCU defines or conforms to, one file per boundary. Read [`docs/architecture/08-contracts.md`](../docs/architecture/08-contracts.md) first — it is the surface map and the format/versioning policy; this README is the navigator for the files here.

## Layout

| File | Surface | Format | Validated by |
|---|---|---|---|
| `mcp/2025-06-18/ocu-constraints.schema.json` | Agent tool-call ingress (caller → MCP gateway) | JSON Schema 2020-12 (MCP conform profile) | `json-schema` CI job |
| `exec/exec-channel.schema.json` | Exec / PTY+CDP (control API → sandbox, machine-to-machine) | JSON Schema 2020-12 | `json-schema` CI job |
| `storage/mount-config.schema.json` | South-face mount config (broker → sandbox) | JSON Schema 2020-12 | `json-schema` CI job |
| `storage/file-ops.schema.json` | South-face file-op RPC (sandbox → broker) | JSON Schema 2020-12 | `json-schema` CI job |
| `storage/file-artifact-api.schema.json` | North-face file/artifact data plane (data-plane client → broker) | JSON Schema 2020-12 | `json-schema` CI job |
| `audit/audit-fanin.asyncapi.yaml` | Audit event fan-in (six containers → audit → SIEM) | AsyncAPI 3.0 / OCSF | `asyncapi` CI job |

The storage surface is three files: the guest mount config, the south-face broker RPC, and the north-face HTTP API. South (`file-ops`) and north (`file-artifact-api`) stay distinct — the south is the sandbox-to-broker RPC, the north is the data-plane client's HTTP surface. Not-yet-built surfaces (operator REST, session-setup gRPC, transparency-log envelope, mock servers) are tracked in `08-contracts.md` §5.

## How to read a schema file

1. `$comment` carries the SPDX header, a one-line scope, and the NFR anchors the file satisfies.
2. `$defs` holds the reusable shapes; the root `type`/`properties` is the message envelope.
3. A `STATUS` of `partial` in `$comment` means the named shapes are fixed but some bodies stay unspecified — see the `x-ocu-tbd-bodies` block for which.
4. Run the same check CI runs:

```sh
npx ajv-cli@5 compile -s contracts/storage/file-ops.schema.json --spec=draft2020 --strict=false
```

## Annotation conventions

A field lands in a schema only when it is sourced, NFR-derived, or explicitly deferred. The annotation says which:

| Annotation | Meaning |
|---|---|
| (none) | Sourced — a real field/message shape; the contract fixes it. |
| `x-ocu-design` | A design-level decision (e.g. an envelope carrier name) referencing a sourced shape; named here, not externally fixed. |
| `x-ocu-default` | An NFR-derived default value (a ceiling, a TTL). Configurable, not frozen — the number tracks the NFR, deployments tune it. |
| `x-ocu-tbd` / `x-ocu-tbd-bodies` | Deliberately unspecified — no field-level source pins it yet. Carries the tracking issue. Do not invent a body to fill it. |
| `x-ocu-open-questions` | A list of unresolved shape decisions for this file. |

The rule the files hold to: never invent a wire field. If a body is not sourced and not NFR-derived, it stays `x-ocu-tbd` with an issue, not a guess.

## Changing a contract

Additive (a new optional field, a new event type, a new proto field number) ships without a version bump. Removing, renaming, or tightening is breaking and needs a new major version — see `08-contracts.md` §4 for the policy and the CI breaking-change gates.
