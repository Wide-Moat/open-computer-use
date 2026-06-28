<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: accepted
last-reviewed: 2026-06-28
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
amends: []
compliance-impact: [SOC2-CC6.1, ISO27001-A.9.4, NYDFS-500.07]
license-impact: none
threat-mitigation-link: ../06-threat-model.md
---

Names the minimal-shelf MCP-caller credential: a per-caller static `sk-` API key, Control-minted, salted-hash-at-rest, validated in-process by the gateway. The full-shelf customer-IdP relying-party flow is unchanged. Audience: anyone wiring or auditing the MCP gateway's inbound authentication.

# ADR-0027: MCP-caller authentication via a static API key

## Status

`accepted`

## Context

[Component-01](../components/01-mcp-gateway.md) authenticates the inbound MCP caller, but its shelf delta names the minimal-shelf caller credential only by category — "a host-rooted local credential" — and its invariant `:46` reads identity from "the bearer's audience claim", a JWT-shaped assumption. The minimal shelf has no IdP, so the full-shelf relying-party flow (NFR-FLEX-03 — the platform is always the relying party, never an in-house JWT issuer) is unavailable, and a JWT with an audience claim has no issuer to mint it. The shape of the minimal-shelf credential is undecided, while MCP clients on the PoC `main` line already expect a static API key.

This is not a second authentication path. The canon already splits caller authN by shelf at [component-01](../components/01-mcp-gateway.md) `:81`: minimal shelf = a host-rooted local credential, full shelf = the customer-IdP relying-party flow — the same minimal-vs-full pattern that governs operator auth ([ADR-0004](0004-operator-authentication-substrate.md)), the embed token (NFR-SEC-82), and PAM (NFR-COMP-29). What is missing is only the concrete form of the minimal-shelf credential for the MCP plane. NFR-SEC-09 forbids anonymous paths and shared service accounts on both shelves, so that form must be per-caller and managed.

## Decision

We will authenticate the minimal-shelf MCP caller with a per-caller static API key, and keep the full-shelf customer-IdP relying-party flow unchanged.

- **Format.** `sk-ocu-<base62, 32 bytes (256-bit) CSPRNG>`. Per-caller — one key names one principal; never a single shared deployment secret. Shown once at issuance, never persisted in plaintext. The `sk-ocu-` prefix is a secret-scanner signature.
- **Issuance.** The Control plane mints the key via the `occ mcp-key create --tenant <T>` operator verb — the same plane that mints every other platform credential ([ADR-0013](0013-storage-credential-custody.md)), the caller-edge analogue of the operator-edge substrate ([ADR-0004](0004-operator-authentication-substrate.md)). The gateway never issues keys.
- **Storage.** Salted SHA-256 (`sha256(salt‖secret)`, per-key salt). Record: `{key_id, key_hash, salt, tenant, deployment, expires_at, status, created_at}`. The record is held in the Control state store on the full shelf, and in a root-owned hashed-entries file on the minimal shelf. The unsalted hash is rejected (pass-the-hash exposure).
- **Validation.** In-process at the gateway, against a Control-owned hashed-key set loaded at boot over the same config plane that delivers the gateway's signing material — never a per-request Control lookup. The gateway hashes the presented bearer and constant-time-compares. This keeps component-01's "no state that outlives a request" invariant literal (the set is configuration, not request-derived state) and opens no second gateway→Control hot-path edge.
- **Binding.** Tenant and deployment scope are read from the resolved record, not from a claim in the key (an opaque key carries none). A key absent from this deployment's set fails to resolve and is refused with 401. The forward to Control still carries the gateway's own service identity; the caller key is never forwarded ([component-01](../components/01-mcp-gateway.md) invariant `:47`).
- **Revocation.** `occ mcp-key revoke --id` flips `status`; Control re-pushes the boot set and the gateway refreshes within NFR-SEC-04 (≤5 min). Rotation is issue-new + revoke-old with an optional grace window; no in-place mutation. `expires_at` is optional (absent ⇒ non-expiring, so the one-click path is not blocked).

## Consequences

- [Component-01](../components/01-mcp-gateway.md) `:46` is recut: the caller bearer must resolve to a non-expired, non-revoked record in the gateway's boot-loaded key set (minimal shelf) **or** carry an `aud` claim verified against the customer IdP (full shelf); tenant and permitted surface come from that record or claim, never from the request body. `:81` names the minimal-shelf credential as the `sk-` key. `adr:` gains `[0027]`.
- The MCP wire contract ([`ocu-constraints.schema.json`](../../../contracts/mcp/2025-06-18/ocu-constraints.schema.json)) gains an `x-ocu-authz` mode (`static-key` default | `oauth2-rs` full shelf); the Origin-validation and no-passthrough rules stay unconditional, the RFC 8707/9728 relying-party rules become conditional on the OAuth mode.
- [02-trust-boundaries.md](../02-trust-boundaries.md) §8 adds the inbound-caller credential class to the token taxonomy (which today lists only OCU-minted classes); the [glossary](../glossary.md) gains "MCP API key".
- The `occ mcp-key` verb is a new Control operator surface ([component-02](../components/02-control-operator-api.md)); the boot-set delivery is a new Control→gateway config contract.
- NFR-SEC-09 is kept, not amended: a per-caller, hashed-at-rest, revocable key is a managed credential, not an anonymous or shared path. The new floor lands as NFR-SEC-87 (entropy ≥ 256 bits, salted-hash-at-rest, revoke ≤ 5 min). The threat-model P1-S1 mitigation names the `sk-` key as the minimal-shelf form; no new threat row.
- Residual: a leaked key grants the caller's reach until revoked — bounded by per-caller scope, revocation, and the minimal-shelf single-tenant posture.

## Alternatives considered

- **OIDC on the minimal shelf.** Rejected: no IdP is wired there; NFR-FLEX-03 forbids an in-house issuer, so there is nothing to mint or verify a JWT against.
- **A single shared deployment key.** Rejected: NFR-SEC-09 forbids shared service accounts on either shelf; a shared key erases per-caller attribution and makes rotation all-or-nothing.
- **mTLS client certificates.** Rejected: the certificate lifecycle (CA, CSR, renewal) is heavier than a one-click solo deployment carries; the `sk-` key is the lighter managed credential.
- **A host-local-signed short-TTL token.** Rejected: it re-creates the JWT issuer the minimal shelf deliberately omits, for no gain over a hashed static key with revocation.
- **OAuth 2.1 resource server.** Not rejected — it is the full-shelf path, named and kept, not an alternative to the minimal-shelf key.

## Compliance impact

- `SOC2-CC6.1` / `ISO27001-A.9.4`: every MCP caller authenticates with a per-caller, revocable, hashed-at-rest credential; no anonymous or shared path on either shelf, so access to the tool-call surface is attributable and auditable.
- `NYDFS-500.07`: per-caller issuance and revocation give access-privilege management over the agent ingress; the full shelf binds the same surface to the customer IdP.

## License impact

None. The key model is OCU code on the existing Control mint plane and the gateway ingress; no new dependency.

## Threat mitigation

P1-S1 (replayed/forged/wrong-audience bearer) is mitigated on the minimal shelf by the in-process hashed-key resolution: a key not in this deployment's set fails closed with 401, and the key is never forwarded onto F5 or into the sandbox. The salted hash bounds a store disclosure (no pass-the-hash), and revocation bounds a leaked key to ≤ 5 min once flagged.

## Open questions

None.
