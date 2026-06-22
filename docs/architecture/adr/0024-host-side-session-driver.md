<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-06-23
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
amends: ['adr/0017-control-plane-repo-boundary.md']
compliance-impact: [SOC2-CC6.1, SOC2-CC6.6, NYDFS-500.15]
license-impact: none
threat-mitigation-link: ../06-threat-model.md
---

Control (`ocu-control`, container 02) owns the host-side session driver: it creates the session container and runs tools in it over the exec channel.

# ADR-0024: Host-side session driver

## Context

Two host-side drivers exist and neither completes a session end-to-end as the production path needs.

`ocu-control` (container 02) runs the full create pipeline: it creates the per-session internal bridge and the hardened container, binds the Ed25519 public key read-only, mints the Storage-JWT and the exec-JWT (both signed by the single boot-loaded key per ADR-0013), and pushes the mount-config. Its only guest-dialing client is the advisory control-RPC dialer of ADR-0018, whose sole verb is `shutdown`. It has **no exec-channel client**: nothing connects to the guest exec UDS, opens the WebSocket, sends `CreateProcess`, or streams stdio. The exec channel is fully specified in `contracts/exec/exec-channel.schema.json` but unimplemented in `ocu-control` — no WebSocket dependency exists in its `go.mod`. Control can start a guest; it cannot run a tool in it.

`octl` (the `ocu-sandbox` host CLI) closes the loop today, but only as a self-contained dev driver. The host-side session driver is `host/internal/control` (its `Manager`): `Manager.Create` builds the deny-all-egress bridge and the hardened container, `Manager.Exec` runs the drive loop under the mandatory D-03 5-minute total cap, `Manager.Lookup`/`Manager.Destroy` derive teardown from the live mounts. `octl` is already a thin shell over `control.NewManager(cli, priv, sink)`. But that `Manager` mints its **own** session JWT from a host-local Ed25519 seed at `~/.ocu/seed`, generated on first `create`: it builds the signer internally from the private key handed to `NewManager`, with no seam to accept a control-created container or a control-issued token. The two drivers do not interoperate.

The transport and codec — the WebSocket-over-UDS dialer, handshake, and frame types (`host/internal/dial`, `host/internal/wire`, sole external dependency `coder/websocket`) — are leaves, not the driver: `control` imports `dial`/`wire`, never the reverse. So `internal/control` is the unit that closes create→drive→teardown, and it pulls in the docker SDK, `jwtmint`, `runtime`, `audit`, and `control/admission` — the full closure the production driver must import.

Canon files the executor as "the Session sandbox … plus a thin control driver for [component-02]" (ADR-0017:48) and groups the host-side exec supervisor with the Control / operator API as a host-side supervision process (ADR-0012:31,37; `05-session-sandbox.md`:25). It never carries that grouping to the deployable that owns the exec-channel *driver*, so the implementations diverged. Canon gives one verb for what control does over the channel: it "dials in to create and **drive** the session" (`05`:25).

The host-attested caller-identity invariant (`02-trust-boundaries.md`:73, anchored to NFR-SEC-43) requires the channel stay off any network the guest can reach: the host opens it and the guest listens, over vsock or a host-side unix socket; the guest resolves no name for the control plane (`05`:40), and a guest-stack dial or cross-session forge fails at accept (`05`:50, invariant 3). The risk is a function of direction and transport, not of which host deployable holds the driver.

## Decision

We will make **`ocu-control` (container 02) the host-side session driver**. Control owns the full host-side lifecycle of a session: it creates the container and the per-session internal bridge, mints and delivers the JWTs, **and owns the exec-channel driver** that connects to the guest it created and runs tools in it. One deployable closes the loop from container-create to tool-run to teardown.

We will **promote `host/internal/control` to a separate Go module at `host/exec/` inside `ocu-sandbox`** — its own `go.mod` — that both repos consume, with `dial`, `wire`, and `jwtmint` moved out of `internal/` alongside it (Go's internal rule forbids cross-module import). The module is the `Manager` driver plus its transport and codec; its `go.mod` pins the minimal closure (the docker SDK, the runtime-tier selector, the WebSocket client, the runtime and audit interfaces) so a consumer resolves that closure, not the executor module's full dependency universe. `ocu-control` imports it for the production driver; `octl` imports it for development. This is **not a mechanical move of the transport packages**: `Manager.Exec` builds its signer internally at create (`jwtmint.NewSigner(m.priv, …)`), so the module is refactored to accept an injected issuer through a `Minter` seam at `NewManager`, replacing the key-derived in-line signer. The seam moves from a private key to an issuer the caller supplies.

We will make **`octl` the dev-only CLI** for component-05 (`ocu-sandbox`) development — exercising the guest, the exec contract, and the runtime tiers without a control plane. It is not the production driver. Its own-JWT-mint-from-local-seed path is wired through the same `Minter` seam as a dev convenience and stays out of every production path.

In production there is **one issuer**: `ocu-control` holds the signing key (ADR-0013), mints the exec-JWT bound to the host-attested `container_name` as `Subject`, and supplies it to the driver through the `Minter` seam. The guest verifies against the public key control bound at create. There is no second issuer and no local-seed mint in the production driver. The shared module carries the wire types, transport, handshake, drive loop, and lifecycle orchestration only; it holds **no signer and no key material**. The `Minter` interface is its sole signing seam — `ocu-control` wires its boot-loaded key (ADR-0013), `octl` wires the local-seed signer, and neither signer enters the module. Extracting the driver therefore moves no signing path into the executor.

We will keep the **guest UDS-only and host-dialled**, and bind trust at create. Control opens the exec UDS in the host-owned 0700 sock dir; the guest listens; the guest resolves no control-plane name (`05`:40), and a guest-stack dial fails at accept (`05`:50, invariant 3). A guest accepts exactly the verify-key bound into it at container-create by its creator; in production the creator is `ocu-control`, and the exec driver presents only control-minted JWTs verifiable against that key. `octl`'s local-seed key pair is never installed into, nor accepted by, a control-created guest — the `Minter` seam carries the signer, never the authority to choose which verify-key a guest trusts, which is fixed at create, not at dial. The exec WebSocket and the advisory control-RPC endpoint of ADR-0018 stay separate channels; this ADR does not fold control verbs into the exec union or alter the control-RPC surface.

This carries ADR-0017's "thin control driver for [component-02]" (0017:48) to the deployable that owns the exec driver: that driver is `ocu-control`. ADR-0017's framing — that "a co-housed single binary remains a valid operator packaging … the boundary is a source-and-blast-radius statement, not a forced runtime topology" (0017:52) — is amended only at the source level: the production exec driver lives in `ocu-control`, with the shared module the seam between the two repos. The blast-radius property ADR-0017:50 protects (the executor holds no signing key) is preserved verbatim.

## Consequences

- **Extraction work and package split.** Promote `host/internal/control` to the `host/exec/` module, split so the docker dependency does not leak to the exec-only consumer: `host/exec/wire` and `host/exec/dial` carry the WebSocket transport, handshake, drive loop, and frame types and import **no docker SDK** (the drive loop already reaches docker only through a `dialFunc` seam); `host/exec/manager` carries the docker-bound `Create`/`Lookup`/`Destroy` orchestration. `ocu-control` has its own Docker provider, so it imports `host/exec/dial` + `host/exec/wire` for the exec drive and never pulls `host/exec/manager`'s docker closure into its `go.sum`; `octl` imports `host/exec/manager` for its self-contained dev create-and-drive. Refactor `NewManager` to take an injected `Minter` issuer instead of constructing `jwtmint.NewSigner` from a private key.
- **Module home and ownership.** The shared driver is a **separate Go module inside `ocu-sandbox` at `host/exec/`** — its own `go.mod`, not a package in the executor module and not a third repository. It keeps the `Manager`, its mutation-tested suite, and the D-03/idle-window hardening next to the only working tests that guard them. Its `go.mod` pins the minimal closure (`dial`, `wire`, `jwtmint`-minus-signer, the runtime and audit interfaces, the WebSocket client, the docker SDK), so `ocu-control` imports `host/exec` and resolves that closure — not the whole executor module's dependency universe. It is tagged independently (`host/exec/vX.Y.Z`); `ocu-control` consumes a pinned tag. A separate package in the executor module would weld the two repos' upgrade blast radii through MVS; a third repository would bootstrap a full gate set from zero and detach the channel from its tests. The separate-module boundary is the condition that holds both off.
- **Cross-team ownership.** CODEOWNERS on `host/exec/**` requires **both** the executor team and the control-plane team, because the production driver path runs through it. The mutation and hardening gate runs on the `host/exec` module's own PRs (`go-mutesting` with a score floor, green-baseline-first — not `go-gremlins`, which mis-parses the comment-led `go.mod`), blocking merges to it.
- **One production issuer.** `octl`'s local-seed mint is dev-only. The production driver consumes control's minted exec-JWT and the verify-key control already binds at create. No second issuer, no foreign verify-key seam on the host side. Supports the host-attested accept posture (NFR-SEC-43, NFR-SEC-76).
- **Minimal Compose slice unblocks.** With the exec driver in `ocu-control`, the tracer path — control creates the container, drives one tool, tears it down — runs in one deployable instead of two non-interoperating ones. The slice no longer waits on a cross-repo driver handoff.
- **Trust boundary and executor blast radius unchanged.** The guest stays UDS-only and host-dialled; control opens the socket, the guest listens and resolves no control name. The decision changes which host deployable holds the driver, not the direction or transport, so the invariant at `02-trust-boundaries.md`:73 holds. The executor's no-signing-key blast radius (ADR-0017:50) is unchanged — the shared module is signer-agnostic, so the extraction adds no key to either repo's closure.
- **Storage and egress untouched.** This ADR governs the exec/session-driver path only. The Storage-JWT flow (ADR-0019) and the host-side L3 egress attach seam (ADR-0021) are unchanged; control still mints and delivers the Storage-JWT and the mount-config as before.
- **ADR-0018 untouched.** The control-RPC endpoint stays the separate advisory-`shutdown` channel; this decision does not add a verb to it or fold the exec driver into it.
- **`occ` is the operator CLI.** `octl` is internal to `ocu-sandbox` development and is not the operator-facing CLI. The canon operator CLI remains `occ`; `octl` does not introduce a second operator CLI.

## Alternatives

**1b — `octl` stays the driver; control shells out to it.** Give `octl` an external-issuer seam and an attach-mode (drive a container created by another process), then have `ocu-control` invoke `octl` as a subprocess for production sessions. Rejected: it keeps two processes on the host critical path, with the lifecycle split across a CLI boundary and the JWT crossing a process exec for every session — strictly worse for the host-attested posture (NFR-SEC-43/76). Control is already the Docker driver and the JWT minter (ADR-0013), so importing the shared `Manager` closes container-create, mint, drive, and teardown in one process. The ownership concern 1b raises — keep the hardened channel under the executor team — is satisfied better by the shared module living in `ocu-sandbox` and `ocu-control` importing it, which is this decision done correctly.

**1c — Two permanent drivers, no extraction.** Keep `ocu-control` and `octl` as separate implementations of the host driver. Rejected: it is the current state. The exec contract would have two independent driver implementations to keep in sync against one frozen schema, and `ocu-control` still completes no session — the divergence this ADR closes.

## Status

Proposed (2026-06-23). Amends ADR-0017. Separate from ADR-0018 (control-RPC), ADR-0019 (storage JWT), and ADR-0021 (egress attach).
