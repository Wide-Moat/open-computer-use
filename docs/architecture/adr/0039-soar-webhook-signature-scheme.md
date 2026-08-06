<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: accepted
last-reviewed: 2026-08-07
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
amends: ['0004-operator-authentication-substrate.md']
compliance-impact: [SOC2-CC6.1, ISO27001-A.8.2, DORA-Art.9, NYDFS-500.7]
license-impact: none
threat-mitigation-link: ../components/02-control-operator-api.md
---

Pins the bytes a SOAR platform signs and the key Control verifies them against — for anyone implementing a SOAR playbook that revokes, or the Control-side verifier.

# ADR-0039: SOAR webhook signature scheme

## Status

`accepted` — amends [ADR-0004](0004-operator-authentication-substrate.md), which fixes the minimal-shelf SOAR identity as a "signed webhook" without naming an algorithm or the signed bytes. Closes the open question carried in [`contracts/openapi/soar-revoke.openapi.yaml`](../../../contracts/openapi/soar-revoke.openapi.yaml).

## Context

[P2-R2](../components/02-control-operator-api.md) requires that a SOAR-driven revoke be verified against the SOAR principal before any kill-switch state changes, and that the verified principal — not the socket peer that delivered the webhook — is the audit actor.

The fence that enforces this is built: `SOARVerifier` is the seam, and the operator adapter cannot form an Engine call without a scope that only a successful verify mints. A nil verifier refuses fail-closed. What has no implementation is the verifier itself, so the minimal shelf ships with the fence closed against everything.

The frozen contract pins the wire — `soar_signature` base64, `issued_at` as the anti-replay anchor, 401 on an unverifiable signature, 409 on a stale or replayed issuance — and states outright that the canonicalization of the signed bytes is not pinned and is not to be invented at the contract layer.

That canonicalization is an interop commitment, not an internal detail. The signer is the customer's SOAR platform, an implementation we do not write, which must reproduce the byte string independently. Once a deployed playbook signs one shape, changing it breaks every integration in the field.

## Decision

The minimal-shelf SOARVerifier verifies an Ed25519 ([RFC 8032](https://www.rfc-editor.org/rfc/rfc8032)) signature over a length-prefixed canonical payload, against a host-owned static keyring in Control's configuration.

The canonical signed payload is:

```text
canonical = "ocu.soar.revoke.v1" || LP(scope) || LP(target) || LP(issued_at)
LP(s)     = uint32 big-endian byte-length of s, then the UTF-8 bytes of s
```

where `scope`, `target`, and `issued_at` are the decoded JSON string values of the `SoarRevokeRequest` fields; `target` is the empty string when `scope` is `all` (the schema forbids the field in that case); and `issued_at` is covered as its verbatim RFC 3339 text — no epoch conversion, no normalization. `soar_signature` carries the base64 of the Ed25519 signature over these bytes.

Length prefixes make the encoding injective for any field content: `target_session_id` is an arbitrary string, so any separator-joined scheme admits two distinct field triples that serialize to one byte string. The version-bearing domain tag prevents a signature made for another purpose from verifying here, and seams a future revision.

Exactly one algorithm is wired. The wire carries no algorithm or key-id selector: the frozen body has no field for one, and a caller-influenced selector is the algorithm-confusion surface. The verifier trial-verifies against the configured keyring and returns the `Identity` — principal name and tenant — of the entry whose key verified. The principal is derived from the verifying key, never from the body.

Keys are provisioned as host-owned configuration at deploy time. There is no network fetch on the kill path: a revoke must not acquire an availability dependency on a key endpoint, nor an outbound-fetch trust surface. An entry may list two keys so a rotation overlaps.

Replay suppression stays outside the `SOARVerifier`. The operator adapter verifies the signature first, then enforces the `issued_at` acceptance window and a seen-signature cache bounded by that window, and only then mints the scope. Only verified issuances enter the cache — admitting an unverified one lets anyone who reaches the socket pre-poison it with a forged future timestamp and block the legitimate revoke, a denial of service on the kill path. `Verify` stays `(payload, sig) -> (Identity, error)`, stateless.

## Consequences

The `SOARVerifier` interface does not change, so the full shelf swaps the keyring for SPIFFE SVID trust-bundle resolution behind the same seam. Both shelves are then "Control trusts a public key", and the upgrade changes key distribution rather than the shape of the trust.

A deployment that swaps verifiers cannot lose replay protection, because the adapter enforces the window and the cache unconditionally, whichever verifier is wired.

Ed25519 is the algorithm already carried in component 02's asset table for the control-WebSocket client-auth key, so this adds no dependency and no second signature algorithm to audit.

The contract's open-question note is now answered by this ADR. That is a comment-only edit; no wire field changes, so the freeze holds.

Rotation without an overlap window fails closed: a SOAR platform that rotates its key before the new public key is provisioned has its revokes refused 401 until the config catches up. This is the intended direction of failure for a kill path.

## Alternatives

**HMAC-SHA256 with a shared secret.** Rejected. P2-R2's threat is a *disputed* revoke, and a shared secret means Control can produce any signature the SOAR platform could. The audit claim that the actor is the SOAR principal is then unprovable to a third party, which defeats the attribution the row exists to guarantee.

**ECDSA P-256.** Rejected. Signing is nonce-sensitive, with a catastrophic key-recovery failure mode on nonce reuse, and it has no precedent in this codebase. Ed25519 is deterministic and needs no parameter choices.

**JSON canonicalization ([RFC 8785](https://www.rfc-editor.org/rfc/rfc8785)) over the request body.** Rejected. It is a larger interop surface than four length-prefixed fields, and it makes correctness depend on two independent JSON serializers agreeing on number and escape handling that the signed fields do not need.

**Signing the raw request body bytes.** Rejected. It forces byte-identical serialization on both sides — any whitespace or key-order difference breaks a signature that is otherwise valid.

**Fetching the SOAR public key from a JWKS endpoint.** Rejected. It puts an availability dependency and an outbound fetch on the path that stops a running session.

**Covering `issued_at` as epoch seconds.** Rejected. RFC 3339 admits several spellings of one instant, so an epoch conversion requires both sides to normalize identically and lets distinct wire bytes verify as equal. Verbatim text binds what is sent; the window check parses the timestamp separately.
