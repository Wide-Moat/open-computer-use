<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-08-07
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
amends: []
compliance-impact: [SOC2-CC8.1, ISO27001-A.8.31]
license-impact: none
threat-mitigation-link: ../components/02-control-operator-api.md
---

Fixes what makes a hand-written wire body conform to its frozen contract, and what a component must ship before it may keep one — for anyone adding a transport body or reviewing an interface change.

# ADR-0043: Contract binding without code generation

## Status

`proposed` — closes the open call carried on roadmap G1. Governs the NFR-IC-04 interface surface; adds no new contract.

## Context

Control's contracts are frozen artifacts: `session_setup.proto` for the session-setup surface, `operator-rest.openapi.yaml` for the operator REST surface. Neither has a generated counterpart. The transport is HTTP with JSON bodies, the bodies are hand-written Go structs, and no component in the platform imports gRPC — it appears in `go.mod` as an indirect dependency and nothing else.

That leaves a question the roadmap carried rather than answered: generate the wire from the contract, or keep writing it by hand.

The usual argument for generation is that a struct tag and a contract field drift apart silently. That failure is real and it happened here — the structs' doc comments *claimed* to follow the proto, and a claim in a comment binds nothing. Every transport test drove the wire against the Go structs and never read the contract, so a rename on either side stayed green.

The claim is now a test. Both surfaces have parity tests that parse the frozen contract and require the wire to agree, field-by-field, with each deliberate omission carrying a stated reason. That is the property generation would have bought.

## Decision

We will bind hand-written wire bodies to their frozen contract by test, and will not generate transport code for v1.

- **The binding is a merge-blocking test, not a comment.** Every wire body whose shape a contract freezes has a test that reads the contract at run time and compares field sets in both directions: a contract field with no wire counterpart, and a wire field the contract does not define, both fail. A doc comment asserting conformance satisfies nothing.
- **The covered set is itself checked.** The list of bound bodies is hand-maintained, so a test asserts its extent: every message the contract declares is either bound or carries a reason naming the test that binds it elsewhere. A contract that grows a message must be reckoned with rather than silently uncovered.
- **A deliberate divergence is annotated, never implicit.** A field present on one side and absent on the other is admitted only with a recorded reason. Fields held open pending another decision use the contract's own reservation primitive (`reserved` in proto, an `x-ocu-reserved` annotation in OpenAPI, since OpenAPI has none), so the slot cannot be reused by accident.
- **The parser fails closed.** A contract-reading test that parses zero fields, or finds zero messages, fails rather than passing vacuously. A test whose parser stopped matching reports the same green as a conforming wire, which is the one failure mode this approach has that generation does not.
- **Generation returns with a gRPC consumer.** When a component actually serves or dials the session-setup surface over gRPC, it generates from the contract and the hand-written body for that surface goes away. This decision governs the JSON transports, not the proto's future.

## Consequences

The parity tests are load-bearing infrastructure, not conveniences. Deleting one silently unbinds a wire surface, so they are covered by the same review discipline as the contracts themselves.

The failure mode moves rather than disappearing. Generation cannot drift but can only express what the generator supports; a parser can express anything but can stop matching. The fail-closed rules above are what make that trade acceptable, and they are the part a reviewer checks.

Reviewers gain an obligation: an interface change touches the contract, the struct, and the omission reasons in one pull request. That is the same obligation a generated pipeline imposes through a regenerate-and-diff step, spent at review time instead of build time.

We do not take on a protoc toolchain, a generator plugin pinned per language, vendored generated code in the diff, or a generate-and-check CI step — none of which serve a running consumer today.

## Alternatives

**Generate `.pb.go` now and marshal the generated types as JSON.** Rejected for v1: it introduces the toolchain and the vendored output for a surface no gRPC client dials, and protobuf JSON mapping differs from Go's `encoding/json` in field naming and zero-value handling, so the generated types would not drop into the existing HTTP handlers unchanged.

**Keep the doc-comment convention and rely on review.** Rejected: it is the state that failed. Review did not catch the drift, because nothing in the test suite could show it.

**Generate a schema from the Go structs and diff it against the contract.** Rejected: it derives the contract from the code, inverting the authority. The frozen artifact is the source of truth; a test that regenerates it from the implementation would ratify whatever the implementation does.

**Serve the session-setup surface over gRPC now, so generation has a consumer.** Rejected as out of scope here: the transport choice is a component-02 decision with its own trust-edge and observability consequences, not something to settle as a side effect of how bodies are written.
