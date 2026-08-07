<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-08-07
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
amends: ['0018-in-guest-control-rpc-endpoint.md']
compliance-impact: [SOC2-CC8.1, ISO27001-A.8.25]
license-impact: none
threat-mitigation-link: ../components/02-control-operator-api.md
---

Fixes how a frozen contract reaches the wire — generated for the proto surface, bound by a document-driven suite for the REST ones — for anyone serving or consuming a Control-plane surface.

# ADR-0040: The contract is the wire

## Status

`proposed` — amends [ADR-0018](0018-in-guest-control-rpc-endpoint.md), which fixes the in-guest control-RPC transport and says nothing about the operator or session-setup surfaces. Closes the open half of roadmap gap G1.

## Context

[`08-contracts.md`](../08-contracts.md) pins the format of each surface: session set-up is Protobuf/gRPC, the operator REST and SOAR revoke surfaces are OpenAPI 3.1 over the host-owned socket. Component 02 lists all three documents in its front-matter.

The served wire is none of them. Session set-up is hand-written JSON whose Go structs transcribe the proto's field names; the operator surface is hand-written HTTP whose handlers were never checked against the document that describes them.

Transcription is where the compatibility guarantee is lost. On a JSON wire keyed by field names, the proto's machinery binds nothing: field numbers, `reserved 6`, and append-only enum numbering describe a wire nobody serves. [NFR-IC-04](../manifesto/02-nfrs.md) requires additive-only evolution with a major bump and a deprecation header for a break — a rule `buf breaking` can only enforce over a file the runtime imports.

Three divergences are live today, and a field-name parity test is green across all of them. The operator create response returns `{key, state}` with a numeric state where `SessionHandle` requires `session_key` and the string enum `reserved|active|released`. Every refusal is written as `text/plain` where the `Denied` response declares the `BoundedReason` JSON envelope ([NFR-SEC-51](../manifesto/02-nfrs.md)). The create body accepts `image`, which the OpenAPI `CreateRequest` withholds and the proto carries as `reserved 6`.

The `image` case is a documentation divergence rather than an escalation: the resolved image is gated against a deny-by-default allow-set before admission ([ADR-0020](0020-sandbox-image-provisioning.md)), so a caller cannot name an arbitrary image. What it does mean is that a reader auditing the contract sees a surface the deployment does not serve.

## Decision

We will make each frozen contract the wire it describes, by surface.

- **Session set-up is generated gRPC.** The served wire is the `SessionSetup` service generated from `session_setup.proto` via `buf generate`, on the existing gateway mTLS listener; accept-time SAN attestation stays at the transport ([NFR-SEC-43](../manifesto/02-nfrs.md)). Generated code is committed under the `go_package` path and CI fails when regeneration produces a diff. A hand-written transcription of this surface is forbidden — it is what moves the compatibility guarantee off the wire and onto a file no runtime code imports.
- **Operator REST and SOAR revoke stay hand-written HTTP over the host-owned socket.** Their format already matches their contract, so binding rather than generation is what canon asks for. gRPC never runs on the operator plane: its authority is the transport peer credential, and the OpenAPI documents are the audited description.
- **A hand-written surface is admissible only under a document-driven binding, enforced in CI.** The binding parses the frozen documents — never constants transcribed from them — and holds four properties: the registered method-and-path set equals the document's operation set in both directions; every response body validates against the schema declared for its status code; every request-body constraint is enforced by the decoder, proven by fixtures derived from the document; every emitted status code is declared on its operation. Field-name parity is subsumed. A wire field the contract withholds, or a contract field the wire drops, is a failure resolved by changing one side in the same commit, with a deliberate omission carried as an annotated exception naming its reason and tracking issue.
- **Server generation from OpenAPI 3.1 is rejected for v1**, recorded in the rejection table of [`05-licensing-posture.md`](../manifesto/05-licensing-posture.md): the available Go generators require down-converting the frozen 3.1 documents to 3.0, which forks the source of truth, or carry a dependency that fails the supply-chain gate. Re-evaluated when a generator passes both.
- **The breaking-change gate stays `buf breaking` plus `oasdiff` against the merge base.** A breaking delta takes the major-version and deprecation-header path of [`08-contracts.md`](../08-contracts.md) §4.

## Consequences

The binding reds immediately on the three live divergences. Fixing them is the first tranche of work under this decision, not a follow-up: a suite that lands green against a diverged wire would have been written to fit the code rather than the contract.

Two reconciliations close before the generated surface serves. The `image` field is either restored to the contract or removed from the wire, which is the [ADR-0020](0020-sandbox-image-provisioning.md) BYO-rung question tracked at [#205](https://github.com/Wide-Moat/open-computer-use/issues/205); and the gateway's `status` verb is reconciled with the proto's `Route`.

Consumers gain a compile-time surface. A gateway calling a generated client cannot send a field the contract does not declare, so the class of drift this ADR removes cannot reappear on that leg.

The operator plane keeps two transports and two idioms. That is the cost of pinning formats per surface rather than unifying on one, and it is accepted because the operator plane's authority is its socket rather than its wire.

## Alternatives

**Generate both surfaces.** Rejected for v1 on the dependency gate, not on principle: OpenAPI 3.1 server generation in Go currently requires forking the frozen documents down to 3.0 or taking a generator that fails the supply-chain review. Forking the source of truth to satisfy a tool inverts which artifact is authoritative.

**Keep both hand-written and rely on `buf breaking` plus `oasdiff`.** Rejected: both tools diff a contract against its own history. Neither reads the served code, so a wire that never matched the contract passes every run — which is the state this ADR ends.

**Treat field-name parity as sufficient.** Rejected by evidence: the parity test is green while the response shape, the state enum, the deny envelope, and the accepted field set all diverge. Names are the one property transcription tends to preserve.

**Unify the operator plane onto gRPC.** Rejected: it breaks the OpenAPI 3.1 format pin for those surfaces and buys nothing, since the peer credential rather than the wire format carries the authority there.
