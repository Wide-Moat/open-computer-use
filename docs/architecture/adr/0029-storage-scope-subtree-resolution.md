<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-07-11
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
amends: ['0019-egress-exchanges-filestore-credential.md']
compliance-impact: [SOC2-CC6.1, SOC2-CC6.6, ISO27001-A.8.10, NYDFS-500.15, DORA-Art.28]
license-impact: none
threat-mitigation-link: ../06-threat-model.md
---

The backend source subtree of a storage mount is resolved at the storage engine behind `ocu-filestore`, from the token's minted intent claim joined against a deployment-configured intent→subtree map, with the ADR-0019 credential exchange re-keyed per `{filesystem_id, intent}` so the claim reaches the engine — for anyone wiring the mount plane, the credential exchange, or engine-side scope enforcement.

# ADR-0029: Storage-scope subtree resolution

## Status

`proposed` — amends [ADR-0019](0019-egress-exchanges-filestore-credential.md) (itself `proposed`, so the amendment lands before ratification: the exchange key gains the intent claim) and closes the namespace-split half of [ADR-0023](0023-files-api-north-contract.md) Open Question 5 (ADR-0023:79); the content-hash-manifest tail of that question stays open with the deferred `checksum_md5` ([ADR-0028](0028-files-api-body-freeze.md)). The two backend defects it resolves are stated in the Context below.

## Context

A session is provisioned two storage mounts over one `filesystem_id`: an `uploads` mount, `readonly: true`, and an `outputs` sink, `readonly: false` ([mount-config.schema.json](../../../contracts/storage/mount-config.schema.json)). Two live defects show the split holds only in the guest:

- **`:ro` has no backend truth.** The `readonly` posture is honoured by the in-guest mount client on host-set config; at the backend both mounts ride one flat tree under one credential, and nothing engine-side distinguishes them — so every object behind the read-only view is writable through the read-write mount. The two mounts are read-write-equivalent views of one tree.
- **A prefix-keyed `downloadable` rule matches nothing.** Objects land at the scope root; no `outputs/` subtree exists for a trusted-producer allow rule to key on, so the NFR-SEC-73 allow-leg for sandbox-produced artifacts is inexpressible.

The discriminator already exists and dies at the hop. Each mount carries its own weak session JWT, minted scoped `{filesystem_id + intent + downloadable}` (mount-config.schema.json:84). But [ADR-0019](0019-egress-exchanges-filestore-credential.md) keys the exchange on the validated `filesystem_id` alone and caches one real credential per session (ADR-0019:35), so a session's two mounts share one exchanged credential — and the engine, which receives only the injected credential and never the weak JWT, sees no intent.

The placement is already reserved: the frozen schema states the backend source path "is resolved at the storage engine from filesystem_id + the mount's RW/RO intent and is deliberately off the wire (least-data, NFR-SEC-25)" (mount-config.schema.json:108). That forward-reference is unsatisfiable while the exchange strips the intent.

## Decision

We will resolve the backend source subtree at the storage engine behind `ocu-filestore`, joining the intent claim the Control plane minted against a deployment-configured intent→subtree map, and we will amend ADR-0019 so the exchanged credential carries that claim.

- **Resolution point.** The engine — the same point that enforces `filesystem_id` scope (NFR-SEC-31) — resolves `subtree = map[intent]` and confines every backend path of the request under `<filesystem_id prefix>/<subtree>/`. No guest, host, or hop component resolves the subtree; the hop keys the exchange on the validated claims and enforces no storage scope (NFR-SEC-31; [ADR-0016](0016-egress-baseline-inspection-hop-backend-scope.md):66). The join input is the credential's claim, never per-request caller metadata — the caller-hint pattern of component-04 invariant 2.
- **The map, with a pinned default.** `write → outputs/` (the RW sink), `read → uploads/` (RO), `preview → uploads/` (RO, and the object is non-downloadable regardless of its stored tag — the three-value intent axis of NFR-SEC-49 and the read-time resolution of NFR-SEC-73, component-04 invariant 5). `read` and `preview` carry no write lease (NFR-SEC-49), so the RO posture becomes engine-enforced rather than a guest mount option. The default map ships pinned, so the minimal shelf runs zero-config; a deployment may override the map, never bypass it.
- **Intent-keyed exchange — the ADR-0019 amendment.** The edge exchanges per mount, not per session: the real filestore credential is keyed and cached per `{filesystem_id, intent}`. ADR-0019's "keyed on the validated `filesystem_id`" and once-per-session cache (ADR-0019:31/35) re-anchor to the pair key and the per-mount cadence; the matching wording in NFR-SEC-85, NFR-SEC-25, and mount-config.schema.json:84 re-anchors with it. Everything else in ADR-0019 stands: the edge validates against the Control plane's JWKS, strips the weak JWT (`forward=false`), holds no signing key, and mints nothing — custody ([ADR-0013](0013-storage-credential-custody.md)) is untouched.
- **The engine verifies the claim, not an edge-stripped hint (path b).** The intent that steers `map[intent]`, and the `filesystem_id` the engine confines under, are read from the weak Storage-JWT the engine JWKS-verifies itself against the Control plane's published set — signature, `kid`-pinned alg (EdDSA/ES256, never `none`), `iss`/`aud`, and a required `exp`. The engine does not trust a claim an upstream stripped and re-asserted; it binds scope only from a claim whose signature it checked. This is the enforceable form of ADR-0013 custody at the engine: an unsigned or forged bearer binds no scope (401), a claim outside the engine's provisioned `filesystem_id` is refused at the engine (403), so the intent-rides-the-JWT decision holds even where the edge exchange is not yet in place. The JWKS reaches the engine as a pinned file mounted from the same artifact ADR-0019 §35 publishes; a fetch/rotation path is a later refinement, not a claim-trust change.
- **Wave split.** The engine-side verification and scope/subtree enforcement (this ADR's load-bearing half) land first; the ADR-0019 `{filesystem_id, intent}` edge exchange that mints the per-mount real credential is the counterparty step. They are separable because the engine's authority is the claim's verified signature, not the exchanged credential's provenance — the edge remains stock Envoy and is untouched by the engine-side half.
- **No wire `root_path`.** The frozen mount config gains no backend-path field: mount-config.schema.json:108 already rules the backend path off the wire (least-data, NFR-SEC-25). The placement there is unchanged.
- **`-granted-intents` is a ceiling.** The static deployment flag names the intents the deployment serves; the effective intent is the intersection of the minted claim and that ceiling. The flag never grants — a claim outside the ceiling is refused, and no flag value substitutes for a missing claim. The Control-minted claim is the grant.
- **Canonical stored path.** The path the engine stores, joins, and evaluates the per-object `downloadable` stored tag against (the `StoredTagFunc` input) is engine-relative with no leading slash — `outputs/report.pdf`, never `/outputs/report.pdf`. One convention across the north and south planes settles the cross-plane mismatch in which the planes disagreed on the leading slash and the stored-tag lookup missed.
- **North F9 stays asymmetric.** No credential crosses F9 ([ADR-0025](0025-f9-internal-transport.md):43), so the north leg carries no intent claim: host-attested list and read stay whole-scope — the scope's owner sees the whole tree — and a north create lands under the `uploads/` subtree, the human→sandbox direction.

## Consequences

- Component [02](../components/02-control-operator-api.md): mints the per-mount intent claim from the mount's host-set posture — the RW sink gets `write`, RO input mounts `read`, a preview-purposed surface `preview`. The claim is the grant; the deployment flag is only the ceiling.
- Component [04](../components/04-object-store-service.md): the engine gains the intent→subtree map, the join, and the stored-path convention. It also gains the JWKS verification of the weak Storage-JWT (signature, `kid`-pinned alg, `iss`/`aud`, `exp`) that binds the scope and intent it enforces — the engine reads the published set as a pinned file, holds no signing key, and mints nothing (ADR-0013). Join mechanics — normalization order against invariant 1's traversal rejection, map-override syntax, the `-granted-intents` intersection — land in the component-04 spec, not here.
- With [ADR-0030](0030-per-chat-storage-scope-derivation.md) the per-chat derived `filesystem_id` keeps the mounts of distinct chats on distinct engine prefixes; the engine confines each verified claim under its own derived scope, so the verification half and the per-chat derivation compose without a shared prefix.
- Component [06](../components/06-egress-trust-edge.md): the exchange cache key widens to `{filesystem_id, intent}`; a two-mount session holds two cached real credentials for the window — the ADR-0019 edge-cache trade multiplied by the mount count, bounded by the three-value intent axis.
- Disjoint subtrees close the `:ro`-mirage defect by construction: every path presented with the write-intent credential joins under `outputs/`, so a crafted write to `uploads/x` becomes the distinct object `outputs/uploads/x` and the uploads subtree is unreachable for writing; the read-intent credential carries no write lease.
- A prefix-keyed `downloadable` allow rule on `outputs/` now matches sandbox-produced artifacts, closing the inexpressible-allow-leg defect.
- ADR-0023 Open Question 5's namespace split is decided: uploads-vs-outputs is a backend subtree split, resolved engine-side, invisible on both the mount wire and the single `/v1/files` surface.

## Alternatives

- **A `root_path` field on the mount config.** Rejected: mount-config.schema.json:108 keeps the backend path off the wire (least-data, NFR-SEC-25), and reopening the frozen shape forces a lockstep change across the control plane, the provisioning push, and the guest client. It also cannot close the `:ro`-mirage defect — the engine sees only the exchanged credential, never the mount config, so a wire field is advisory at the one point that could enforce it.
- **Enforce the subtree at the egress hop.** Rejected: scope enforcement lives at the storage engine, not the hop (NFR-SEC-31); ADR-0016:66 already rejects egress-side scope as the baseline. A hop-side subtree check duplicates the engine's authority at a middlebox and disappears wherever the optional hardening is off.
- **A whole-scope `*` downloadable posture instead of subtrees.** Rejected: one scope tree holds both directions, so whole-scope downloadable makes every human upload egress-eligible — reopening the exfiltration split NFR-SEC-73 exists to hold ("agent may read this object" vs "agent may remove it from the sandbox").
