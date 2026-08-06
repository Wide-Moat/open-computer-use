<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: accepted
last-reviewed: 2026-08-06
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
amends: ['0017-control-plane-repo-boundary.md']
compliance-impact: [SOC2-CC6.6, ISO27001-A.8.22]
license-impact: none
threat-mitigation-link: ../06-threat-model.md
---

Deployment manifests identify a component by one label pair, and the gateway-to-operator isolation is asserted by a purpose-built structural gate rather than a generic IaC scanner — for anyone writing a manifest or wiring the NFR-SEC-52 check.

# ADR-0038: Deploy identity, and the instrument that enforces NFR-SEC-52

## Status

`accepted` — amends [ADR-0017](0017-control-plane-repo-boundary.md) (fixes the deploy-identity label its deployable name implies) and corrects the verification column of [NFR-SEC-52](../manifesto/02-nfrs.md). Tracked in [ocu-control#1](https://github.com/Wide-Moat/ocu-control/issues/1).

## Context

[NFR-SEC-52](../manifesto/02-nfrs.md) requires a CI assertion that the agent-facing MCP gateway has no network route to Control's operator ingress. The gateway half is built: a structural check parses its shipped NetworkPolicy and Compose manifests, fails closed on an absent or malformed one, and self-tests by planting an operator route in four selector forms before the gate runs. It is a required context.

That check binds against nothing. Its egress allowlist selects a pod labelled `app.kubernetes.io/name: ocu-control` carrying `ocu.dev/ingress: session`; Control's manifests label their pods `ocu-controld` and stamp no ingress label at all. The selector therefore matches no pod, which makes the shipped policy stricter than intended and the invariant unfalsifiable from the Control side. Two components disagree about what one of them is called, and neither is wrong by any written rule, because no rule exists.

The label scheme is in the same position. The gateway invented `ocu.dev/ingress: session|operator` and shipped it; no contract or decision ratifies it. It is a cross-component wire contract with a consumer and no producer.

The invariant's own shape was also misread. Control's operator ingress is not a network endpoint on either shelf: both manifests pass `-operator-listen unix:///run/ocu-control/operator.sock`. There is no port to reach, so "no network route" holds by topology, and a network-membership assertion on the Control side would be checking a property that has no counterpart there.

## Decision

We will fix the deploy identity, ratify the label scheme, and name the instrument that enforces the invariant.

- **`ocu-control` is the deploy identity.** `app.kubernetes.io/name` is `ocu-control` on every Control pod. ADR-0017 fixes the deployable and the published image under that name, and the label names the application, not the binary. `ocu-controld` remains correct for the binary and the container; it is wrong as a pod identity, and Control's manifests are the ones that change.
- **`ocu.dev/ingress` is the audience label**, values `session` and `operator`. A pod serving Control's session API carries `session`. **No pod carries `operator` while the operator ingress is a unix socket** — that is the rule, not an omission, and a manifest that stamps it is asserting a network exposure that does not exist.
- **The session port is 8443**, the value the gateway already dials. Control's `9466` is a loopback development bind and is rebound when the two are wired together.
- **The NFR-SEC-52 instrument is a per-repo structural gate**, run as a required CI context with a self-test that plants the violation it claims to catch. Checkov and tfsec are removed from the verification column: a rule-library scanner has no vocabulary for "this endpoint pair is unreachable", so pointing one at the property yields a green that measures nothing. Generic IaC scanning, if wanted, is a separate NFR.
- **On the UDS shelf the assertion is custody, not membership.** Where the operator ingress is a unix socket, the Control-side gate asserts that the listener flag is `unix://`, that no Service, Ingress, NodePort or published port exposes either listener, that nothing else mounts the socket's volume, and that no NetworkPolicy admits the gateway's identity. A network-membership check there would assert against networks that do not exist.

## Consequences

The gateway's manifest is left alone. Its selector was right and its allowlist was written against the identity canon implies; Control's label was the divergence, so exactly one repo changes and the fix is a label, not a redesign.

Control's session listener stays on loopback. Rebinding it to a pod IP would trade a topology guarantee that holds today for a policy guarantee that needs the gate to be built first, and it is only meaningful in the change that actually wires the two together.

P2-E1 in [`06-threat-model.md`](../06-threat-model.md) leaves PARTIAL once the Control-side gate lands, because both ends of the pair become falsifiable: the gateway's plants prove it cannot route out, and Control's prove it does not expose.

## Alternatives

**Change the gateway's selector to `ocu-controld`.** Rejected: it ratifies the label the rest of canon never uses, and it buys no falsifiability — the allowlist would then match a pod that still carries no audience label, so the invariant stays unprovable from the far side.

**Add Checkov and tfsec, as the NFR's column says.** Rejected: neither can express the property. Adding them would produce a passing scan that says nothing about gateway-to-operator reachability, which is worse than no scan, because the green is mistaken for coverage.

**Network-bind Control's operator listener so the NetworkPolicy has something to deny.** Rejected: it manufactures the exposure the invariant exists to prevent, so a policy can be seen denying it. The UDS holds the property more strongly than any policy can.
