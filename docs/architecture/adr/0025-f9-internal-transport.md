<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: accepted
last-reviewed: 2026-07-01
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
amends: []
compliance-impact: [SOC2-CC6.1, SOC2-CC7.2, ISO27001-A.8.15]
license-impact: none
threat-mitigation-link: ../06-threat-model.md
---

The F9 hop — how the component-08 BFF reaches component-04 to resolve a durable `file_id` — is a dedicated north host-leg listener on the object-store service, not the south mount RPC; for engineers wiring the BFF to the object-store service or implementing its north face.

# ADR-0025: F9 internal transport — the BFF→object-store durable-resolve host leg

## Status

`accepted`

## Context

[ADR-0023](0023-files-api-north-contract.md) pins three things: the public Files-API endpoints (`/v1/files`, served on the component-08 ingress), the durable `file_id` home (component-04's handle-store, not the ephemeral within-session objectid store that backs the south mount RPC), and that the south `/v1/filestore/fs/<op>` mount RPC "stays internal and untouched." It does not pin the wire between the two: when the component-08 BFF terminates a public `/v1/files` call and turns around to resolve the durable `file_id`, it never said over what route, transport, or auth the BFF reaches component-04.

That gap was filled by an informal note that routed the BFF resolve over the south verb `/v1/filestore/fs/getFileMetadata`. Two facts make that wrong:

- The south route resolves the **ephemeral** session-scoped objectid store — the one ADR-0023 explicitly excludes as the durable home. A `file_id` minted in one session resolves to `not_found` in the next. The south `getFileMetadata` verb is itself an unimplemented deferral.
- The south route is where the egress-injected backend credential is exchanged. Co-locating the no-credential, host-attested durable-resolve on that credential-bearing surface is the confused-deputy ADR-0023 rejects, re-created one layer in.

The object-store service already carries the right resolver — a durable, scope-bound, keystone-tested handle-store — and a dormant north seam built to front it. What is missing is the decision to stand that seam up as the F9 transport and the frozen route+auth shape both repos wire to.

## Decision

We will stand up a **dedicated north host-leg listener on the object-store service** as the F9 internal transport, separate from the south mount listener, exposing the Files-API verbs and resolving the durable handle-store.

- **Listener.** A north listener on its own bind (the object-store service's `--north-listen`), a different listener and process surface from the south `/v1/filestore/fs/<op>` mount RPC. The two never share a listener, router, or resolver. This is a physical trust boundary between the credential-bearing south plane and the no-credential north plane, not only a logical one.
- **Verbs.** The five Files-API endpoints of [ADR-0023](0023-files-api-north-contract.md): `POST /v1/files`, `GET /v1/files`, `GET /v1/files/{file_id}`, `GET /v1/files/{file_id}/content`, `DELETE /v1/files/{file_id}`. The BFF's server-side client emits these directly; the south `OperationName` verb-dispatch is not used on this leg.
- **Resolver.** Every `file_id`-bearing verb resolves the durable handle-store ([component-04](../components/04-object-store-service.md), ADR-0023's pinned home), never the ephemeral objectid store. The handle-store stays the single `file_id` authority — no second component resolves a `file_id`.
- **Auth — scope source.** No credential crosses F9. The host-attested `filesystem_id` rides as a scope field on the F9 request, forwarded from the BFF over the trusted intra-deployment channel. The BFF has already run embed-token verify, first-party session, and three-axis authorization ([component-08](../components/08-web-ui.md), NFR-SEC-82) before the F9 call, so the scope reaching the object-store service is attested upstream; the service reads it from the request scope field and trusts it as an intra-deployment peer. This leg does not cross the egress trust-edge and carries no backend credential, so there is no edge-injected credential to read — the object-store service's south-plane credential-scope reader is not reused here. The BFF mints no token for this leg: it forwards an already-attested scope, not a fresh JWT. The egress-injected credential and its exchange stay entirely on the south plane.
- **Keystone.** The handle-store resolves only a byte-equal-scope record; a cross-scope or unknown `file_id` returns the same `not_found`, never `forbidden` — the anti-enumeration keystone of ADR-0023:38, enforced in the handle-store (its one home) and surfaced as HTTP 404 on the wire. The BFF maps 404 to a null resolve and projects `not_found` without distinguishing cross-scope from absent.

The south mount RPC and its weak-session-JWT-to-egress credential exchange are left byte-untouched ([ADR-0013](0013-storage-credential-custody.md), [ADR-0019](0019-egress-exchanges-filestore-credential.md)) — satisfied by construction, since the north plane shares no code path with it.

## Consequences

- Component [08](../components/08-web-ui.md): the BFF's object-store client targets the five north Files-API routes instead of the south verb-dispatch. The no-credential invariant, the keystone null-on-404, and the client-facing `/v1/files` App-Router handlers are unchanged — only the route and method the internal client emits move. The public surface the SPA sees does not change.
- Component [04](../components/04-object-store-service.md): the dormant north seam becomes a live listener on `--north-listen`, fronting the durable handle-store with the five-route handler. The south face is unchanged. The handle-store, already built and keystone-tested, is wired to a request path rather than held only for lifecycle teardown.
- Positive: the durable-handle invariant (ADR-0023:37) is honoured in fact — a `file_id` survives a session/daemon restart because the resolve lands on the durable store. The credential and no-credential planes are physically separated, so a routing or scope-derivation bug cannot let a no-credential north request reach the credential-bearing south path.
- Negative: a second listener and bind on the object-store service, and one new inter-component contract to maintain. Both are the cost of the trust boundary; the cheaper path-prefix variant was rejected (see Alternatives).

## Alternatives

- **South route with Files-API verbs (the informal status quo)** — rejected: the south route resolves the ephemeral objectid store, not the durable handle-store ADR-0023:37 mandates, so a `file_id` would not survive a session; and it drags Files-API resolve onto the credential-bearing mount RPC ADR-0023:41/55 keeps internal and untouched, putting two resolvers on one `file_id`.
- **Path-prefix `/v1/files` on the existing south server** — rejected: it reaches the right resolver and is cheaper, but co-locating the no-credential durable-resolve plane and the credential-bearing mount plane on one listener+router keeps them one router-bug apart — the confused-deputy surface ADR-0023:55 exists to close. A separate bind buys a physical trust boundary that a regulated-enterprise InfoSec review treats as load-bearing, not optional.
- **A separate `files-api-gateway` deployable for the BFF→object-store hop** — deferred to v2 with the north public gateway ([ADR-0023](0023-files-api-north-contract.md)); the minimal shelf serves the north leg on the object-store service's own bind.

## Open questions

- The per-operation request/response bodies on the north leg: resolved by [ADR-0028](0028-files-api-body-freeze.md) ([#304](https://github.com/Wide-Moat/open-computer-use/issues/304)) — bodies frozen in `contracts/openapi/files-api.openapi.yaml`, the `DELETE` gate opens against the frozen shape.
- `downloadArchive` placement: resolved by [ADR-0028](0028-files-api-body-freeze.md) ([#304](https://github.com/Wide-Moat/open-computer-use/issues/304)) — `GET /v1/files/archive` is an additive OCU-extension north route beside the five frozen verbs.
