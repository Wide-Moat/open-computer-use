<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-07-11
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
compliance-impact: [SOC2-CC6.1, SOC2-CC6.6, ISO27001-A.8.3, ISO27001-A.5.15, NYDFS-500.15]
license-impact: none
threat-mitigation-link: ../06-threat-model.md
---

The deployment `filesystem_id` is a scope namespace base; the Control plane derives the effective per-session storage scope from the host-attested caller and the session handle at mint time, so two chats of one deployment do not share one storage tree - for anyone wiring the Control mint path, the object-store north face, or the Web-UI file client.

# ADR-0030: Per-chat storage scope derivation

## Status

`proposed`

## Context

A deployment configures one `filesystem_id` for the session-provisioning mount ([mount-config.schema.json](../../../contracts/storage/mount-config.schema.json)). When that value is a single static string, every session of the deployment binds one storage scope: one chat's uploads and outputs are visible to the next chat over the same mount. The reference deployment ships exactly this shape, so [invariant 2](../components/04-object-store-service.md) ("a caller-supplied scope id is rejected if it does not match the host-attested binding") is vacuous - every caller trivially matches the one scope, and there is no per-chat boundary to enforce.

The canon already models `filesystem_id` as a per-session, host-attested binding the Control plane owns ([component-02](../components/02-control-operator-api.md): "Control keeps only the session-`filesystem_id` binding"; [ADR-0023](0023-files-api-north-contract.md)). What is missing is the derivation: the binding is copied verbatim from static config instead of being derived per session. The session identity that would distinguish two chats already flows - the gateway forwards a per-chat `SessionHint` (the `X-Chat-Id` transport header) and Control joins it with the attested caller to reserve one session per (tenant, chat) (NFR-SEC-43). The scope derivation is the same join, feeding the same mint pipeline.

The engine constrains the scope id shape: it validates `filesystem_id` as a single path segment and rejects `/`, `\`, `.`, and `..` (traversal defence, [invariant 1](../components/04-object-store-service.md), [NFR-SEC-25](../manifesto/02-nfrs.md)). A slash-namespaced id (`fs-base/tenant/chat`) is refused at the engine and would collide with the ADR-0029 subtree segment, so the derived id must be one opaque segment.

## Decision

We will treat the deployment `filesystem_id` as a scope namespace base and have the Control plane derive the effective per-session scope id from the host-attested caller identity and the session handle at Storage-JWT mint time.

- **Namespace base, not the scope.** The provisioning `filesystem_id` is the base of a namespace. Control derives `effective_scope = base + "-" + scopeHandle(attested_owner, session_handle)`, a SINGLE opaque path segment (`fs-base-<hex>`) the engine accepts as-is. The gateway is unchanged: it forwards the provisioning fields verbatim from deployment config, and the derivation happens at the mint authority, not the caller-adjacent hop ([F5 ruling A](../components/02-control-operator-api.md), NFR-SEC-43).
- **Derivation is host-attested.** `scopeHandle` mixes the attested owner identity (the same identity Control derives the session key from) with the session handle. A caller cannot widen its scope: the chat handle is a hint, and it can only ever reach the scope Control derives inside the caller's own attested namespace. Cross-tenant reach is closed by the attested owner half; within a tenant, chat separation is client-cooperative hygiene, matching the reference behaviour of a per-chat directory.
- **The claim carries the derived scope.** Control mints the effective scope into the weak Storage-JWT's `filesystem_id` claim ([ADR-0013](0013-storage-credential-custody.md)). The ADR-0019 exchange and the ADR-0029 subtree join are untouched: the edge still keys the exchange on the validated claim, and the engine still joins the subtree on the credential's claim - the value in that claim is now per-session. "The Control-minted claim is the grant" (ADR-0029) is unchanged; only the granularity of the scope id widens from per-deployment to per-session.
- **Control persists the binding.** Control persists the session-`effective_scope` binding in the session registry (the binding it is already the sole custodian of) so the Web-UI file client can resolve a chat's scope through Control's read surface. A per-chat scope's north-face authorization (below) reads this binding.
- **North F9 attests the namespace, not the whole scope.** The Web-UI file client presents an embed token that attests the tenant namespace base; the pane requests a chat scope within it, and the object-store north face authorizes the request against the Control-held binding rather than treating the token as a whole-namespace grant. The host-attested scope of the F9 leg ([ADR-0025](0025-f9-internal-transport.md)) narrows from the base to the per-chat scope.
- **Format is pinned; no wire change.** The scope id is `<base>-<hex(scopeHandle)>`, one segment, engine-legal. `mount-config.schema.json` is unchanged: `filesystem_id` stays an opaque string, and nothing new rides the wire. A deployment that sets a static base and one chat degrades to today's single-scope behaviour with no code path difference.

## Consequences

- Component [02](../components/02-control-operator-api.md): the mint path derives the effective scope from the attested owner and session handle, mints it into the claim, and persists the session-scope binding in the registry; the read surface exposes it. Positive: the per-session storage boundary becomes real; invariant 2 is non-vacuous. Negative: the registry gains a persisted per-session scope field and the mint path gains a derivation step.
- Component [04](../components/04-object-store-service.md): the north face authorizes a per-chat scope against the Control-held binding instead of accepting the embed token as a whole-namespace grant; the scope-id format is pinned to one engine-legal segment. The south engine is unchanged - the scope is opaque and already enforced (invariant 4). Negative: north-face authorization is new logic on the F9 leg.
- Component [08](../components/08-web-ui.md): the file pane resolves a chat's scope through Control's read surface rather than binding a static `filesystem_id` from the embed token.
- Edge and issuer ([ADR-0019](0019-egress-exchanges-filestore-credential.md)): unchanged - they key on the validated claim, which now carries the per-session value.
- Negative: a per-chat scope multiplies filesystem lifecycles; scope garbage-collection is deferred (Open questions, item 2).

## Alternatives considered

- **A per-chat subtree within one static scope** (`uploads/<chat>/`, `outputs/<chat>/`). Rejected: isolation by path convention shares one credential and one scope across all chats, so a mis-scoped list or a traversal leaks across chats; it also collides with the ADR-0029 intent subtree and forces a migration of objects to a deeper path once the real per-scope fix lands.
- **Derive the scope at the gateway from `X-Chat-Id`.** Rejected: the gateway is the caller-adjacent hop F5 ruling A distrusts, and it never holds the attested registry owner - only the pre-attestation principal. Scope authority belongs at the mint authority (Control), which holds the attested identity and the signing key.
- **Slash-namespaced scope id** (`fs-base/tenant/chat`). Rejected: the engine rejects `/` in a scope id (invariant 1) and the segment would collide with the ADR-0029 subtree join. The derived id is one opaque segment.
- **A `filesystem_id` field on the caller's create body.** Rejected: a caller-supplied provisioning field is exactly what F5 ruling A forbids (a caller must not widen its own scope). The scope is host-derived, never body-supplied.

## Compliance impact

`SOC2-CC6.1` and `SOC2-CC6.6` (logical access segregation), `ISO27001-A.8.3` and `ISO27001-A.5.15` (information access restriction), `NYDFS-500.15` (access privilege limitation): a per-session storage scope enforces access segregation between chats of one deployment.

## License impact

None.

## Threat mitigation

Closes the cross-chat file-visibility path in the reference single-scope deployment: two chats of one deployment resolve to distinct derived scopes, so one chat's uploads and outputs are unreachable from another (cross-chat negative test on the derived scope).

## Open questions

1. Within-tenant hard boundary - the chat id arrives as a hint today; a cryptographic within-tenant boundary needs the chat id on an attested channel (an embed-token claim) rather than a transport header ([#348](https://github.com/Wide-Moat/open-computer-use/issues/348)).
2. Per-chat scope lifecycle - garbage-collection and reap policy for the multiplied per-session filesystems ([#349](https://github.com/Wide-Moat/open-computer-use/issues/349)).

---

Hard cap: 200 lines.
