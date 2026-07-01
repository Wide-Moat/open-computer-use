<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: draft
last-reviewed: 2026-06-20
owner: "@Wide-Moat/architects"
applies-to: next/v1
---

The wire contracts OCU defines or conforms to, one file per boundary. Read [`docs/architecture/08-contracts.md`](../docs/architecture/08-contracts.md) first — it is the surface map and the format/versioning policy; this README is the navigator for the files here.

## Layout

| File | Surface | Format | Validated by |
|---|---|---|---|
| `mcp/2025-06-18/ocu-constraints.schema.json` | Agent tool-call ingress (caller → MCP gateway) | JSON Schema 2020-12 (MCP conform profile) | `json-schema` CI job |
| `mcp/mcp-key-set.schema.json` | MCP hashed-key-set (control plane → MCP gateway boot-set, ADR-0027) | JSON Schema 2020-12 | `json-schema` CI job |
| `exec/exec-channel.schema.json` | Exec / PTY+CDP (control API → sandbox, machine-to-machine) | JSON Schema 2020-12 | `json-schema` CI job |
| `control/control-rpc.schema.json` | Control → guest control-RPC (control plane → sandbox, over a host-owned UDS) | JSON Schema 2020-12 | `json-schema` CI job |
| `storage/mount-config.schema.json` | Mount-plane mount config (control plane → in-guest mount client) | JSON Schema 2020-12 | `json-schema` CI job |
| `storage/file-ops.schema.json` | Object-store client RPC (in-guest mount client → object-store service) | JSON Schema 2020-12 | `json-schema` CI job |
| `storage/file-artifact-api.schema.json` | Web UI file/artifact data plane (data-plane client → Web UI) | JSON Schema 2020-12 | `json-schema` CI job |
| `audit/audit-fanin.asyncapi.yaml` | Audit event fan-in (five source channels → audit → SIEM) | AsyncAPI 3.0 / OCSF | `asyncapi` CI job |
| `admission/runtime-tokens.schema.json` | Admission tier vocabulary (shared profile/tier-token + pairing matrix, resolved independently in control plane and sandbox) | JSON Schema 2020-12 | `json-schema` CI job |
| `openapi/operator-rest.openapi.yaml` | Operator REST (operator console/CLI + SOAR caller → Control / operator API) | OpenAPI 3.1 | `openapi` CI job |
| `openapi/soar-revoke.openapi.yaml` | SOAR revoke inbound (SOAR → Control / operator API) | OpenAPI 3.1 | `openapi` CI job |
| `proto/ocu/control/session/v1/session_setup.proto` | Session set-up RPC (MCP gateway → Control / operator API) | Protobuf 3 / gRPC | `proto` CI job |

The storage surface is three files: the guest mount config (`mount-config`), the mount-plane RPC (`file-ops`), and the Web UI HTTP API (`file-artifact-api`). The two callers stay distinct — `file-ops` is the in-guest mount client's RPC to the object-store service (the narrow object-store client speaks the storage protocol guest-out, holds no signing key, and forwards the weak session JWT it was provisioned; the egress edge validates that JWT and exchanges it at the issuer for the real filestore credential, which the object-store service translates each verb into a storage-engine request against, and the engine enforces the scope), `file-artifact-api` is the data-plane client's HTTP surface to the Web UI.

The control-plane surface is three files: the operator REST API (`openapi/operator-rest`), the inbound SOAR-revoke API (`openapi/soar-revoke`), and the gateway session-setup RPC (`proto/.../session_setup`). The operator and SOAR surfaces carry operator authority; the session-setup surface carries the gateway service identity only, with no operator scope, so force-kill, denylist-edit, and quota-override are not reachable on it. A deny on any of the three carries the shared `BoundedReason` envelope. Not-yet-built surfaces (transparency-log envelope, mock servers) are tracked in `08-contracts.md` §5.

## How to read a schema file

1. `$comment` carries the SPDX header, a one-line scope, and the NFR anchors the file satisfies.
2. `$defs` holds the reusable shapes; the root `type`/`properties` is the message envelope.
3. A `STATUS` of `partial` in `$comment` means the named shapes are fixed but some bodies or union members stay unspecified — see the `x-ocu-tbd-bodies` block (unspecified bodies) or the `x-ocu-tbd-verbs` block (deferred/forbidden union members) for which.
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
| `x-ocu-tbd-verbs` | A union schema's deferred or forbidden members, named but absent from the v1 tag set. Each entry carries a disposition, its threat where it bears one, and a tracking issue. Adding a verb is an additive bump, not an open extension point. |
| `x-ocu-open-questions` | A list of unresolved shape decisions for this file. |

The rule the files hold to: never invent a wire field. If a body is not sourced and not NFR-derived, it stays `x-ocu-tbd` with an issue, not a guess.

## Changing a contract

Additive (a new optional field, a new event type, a new proto field number) ships without a version bump. Removing, renaming, or tightening is breaking and needs a new major version — see `08-contracts.md` §4 for the policy and the CI breaking-change gates.
