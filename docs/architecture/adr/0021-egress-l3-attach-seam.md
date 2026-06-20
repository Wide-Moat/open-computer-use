<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-06-20
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
amends: []
compliance-impact: [SOC2-CC6.1, SOC2-CC6.6, NYDFS-500.15, DORA-Art.28]
license-impact: none
threat-mitigation-link: ../06-threat-model.md
---

Fixes how a sandbox session's outbound bytes physically reach the egress edge's L3 hop, and bounds that hop to a host-driven attach with no added privilege. Audience: anyone wiring or auditing the L3 path between a guest and the egress edge.

# ADR-0021: Host-side L3 egress attach seam

## Status

`proposed`

Companion to [ADR-0008](0008-session-egress-attribution.md): 0008 fixes *who* an outbound request is attributed to (the presented L7 token, never a network fact); this ADR fixes *how* the bytes physically transit to the hop that reads that token. The two are orthogonal — 0008 keys policy on the token; this keys nothing on the L3 fact, it only carries the bytes.

## Context

[ADR-0008](0008-session-egress-attribution.md) assumes the edge already holds the guest's plaintext request after TLS termination, but does not say how a guest's bytes physically reach the edge's L3 hop. The per-session bridge ships deny-all: `denyAllEgressNetworkOptions` creates each bridge `Internal: true` (no off-bridge route), and `DropEgress` is a host-side SDK `NetworkDisconnect` of the container from that bridge at teardown — the L3 teardown half (NFR-SEC-27). The attach half — the standing L3 path the edge listens on — had no decision. An `Internal: true` bridge's only on-bridge peer is a dead-end host gateway; bytes addressed to it land nowhere. Making the edge the real L3 exit needs a mechanism, and the mechanism must not regress the control plane's privilege: the control plane runs non-root (no `CAP_NET_ADMIN`), and `DropEgress` is SDK-only. The component-06 edge — the L7 demux, the credential exchange, the forwarding element — does not exist yet, so the decision is scoped to the L3 attach proven in component-05 against an off-bridge stand-in.

## Decision

A guest's bytes reach the edge over a **host-root-netns listener bound on the session's per-session bridge gateway IP** — the host-owned L3 address the bridge device already carries in the host root network namespace after `NetworkCreate`. The host-side attach seam (`EgressAttach`: `Attach` on Create, `Detach` on teardown) stands an ordinary `net.Listen` on that address: no `ip link`, no netns entry, no `CAP_NET_ADMIN`. A guest packet to its gateway IP leaves the container netns through the veth pair and is delivered in the host root netns — a real netns-boundary crossing, not a loopback to an on-bridge sibling.

The per-session bridge stays `Internal: true`; the attach adds no cross-session L3 hole. The stand-in **terminates** the bytes (accept, decide, close) and is the chokepoint that owns the allow/deny decision; the deny-all default forwards nothing. The L7 session-JWT demux, the real upstream egress, and the forwarding element are the component-06 edge, deferred — the component-05 seam carries this boundary as a pinned doc-comment so the deferral cannot silently turn into an overclaimed edge.

## Consequences

- The mechanism is tier-identical, preserving [ADR-0008](0008-session-egress-attribution.md)'s cross-tier property: the gateway lives in the host root netns, outside the gVisor network stack, so the transit and the deny decision hold the same under `runc` and `runsc`. The proof runs against both tiers.
- A host-root-netns listener holds L3 routes to every bridge, so locally-originated traffic bypasses the `FORWARD` chain — the cross-session-relay risk the gateway-bind introduces. The deny path must therefore prove a real **packet drop on a reachable path**, not absence of forwarding: the proof reaches a sibling session's guest from the host root netns under a positive control (the route is live, the test fails if it is not), then asserts the deny path forwarded zero. Co-tenant isolation (NFR-SEC-22) is shown by a packet that does not pass, not by an unconfigured route.
- `denyAllEgressNetworkOptions` stays `Internal: true`; the `.Internal == true` posture check survives unchanged. Surviving that check is **not** read as "there is no off-bridge byte sink" — the gateway-bound listener is exactly such a sink, by a different path; the two posture facts are distinct.
- `Detach` reaps the listener at teardown, advisory and ahead of `DropEgress`; teardown leaves zero orphaned listeners. A recycled gateway address re-binds cleanly.
- Component-06 records this ADR in its `adr:` front-matter (`[…, 0016]` → `[…, 0016, 0021]`); the forwarding element, the L7 demux, and the credential exchange that turn this terminating stand-in into the real edge are its decision, not restated here.

## Alternatives considered

- **Per-session veth into an edge netns** — rejected: it requires `ip link add veth` and entry into the container netns, both of which the non-root control plane (no `CAP_NET_ADMIN`) cannot do; it would regress the SDK-only `DropEgress` to a privileged data path. The gateway-bind needs no privilege the SDK does not already hold.
- **`NetworkConnect` the edge into the `Internal` bridge as a peer** — rejected: an `Internal: true` bridge has no off-bridge route and the edge-as-peer has no default gateway, so the bytes never leave the bridge — the same dead-end the on-bridge host gateway already is. It proves a loopback, not transit through a mechanism.
- **Drop `Internal: true` and enforce deny-all only at the edge** — rejected for v1: it moves the deny-all guarantee off a kernel-enforced bridge posture onto edge configuration, widening the blast radius of an edge misconfiguration to cross-session reachability. The `Internal` bridge keeps the kernel as the first deny; the attach is additive to it, not a replacement.

## Compliance impact

- `SOC2-CC6.1` / `SOC2-CC6.6`: the outbound L3 path is a single host-controlled chokepoint per session with a deny-all default; cross-session reachability is denied at the kernel bridge and re-proven at the host hop.
- `NYDFS-500.15` / `DORA-Art.28`: the session's outbound leg has one host-attested L3 exit, so each outbound flow is bound to its owning session's bridge before the edge attributes it by token.

## License impact

None. The seam is `net.Listen` on a Docker-SDK-created address; no new dependency.

## Threat mitigation

Closes the L3 half of per-session egress isolation behind P5-D2 / P6-D1 in [the threat model](../06-threat-model.md): a guest reaches only the host hop on its own bridge gateway, and the host hop's deny-all default relays nothing to a sibling even though the host root netns can route to one — the cross-session-relay path is proven dropped, not merely unconfigured. The L7 demux and the forwarding element that complete the edge are component-06, tracked with the one-per-host-vs-one-per-deployment instantiation question at [#175](https://github.com/Wide-Moat/open-computer-use/issues/175).
