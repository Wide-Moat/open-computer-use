<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: draft
last-reviewed: 2026-06-14
owner: "@Wide-Moat/architects"
applies-to: next/v1
compliance: []
threat-model: 06-threat-model.md
contract: contracts/exec/exec-channel.schema.json
adr: [0003, 0005, 0007, 0013, 0014, 0015, 0016, 0017]
---

Internal design of the per-session execution container, for engineers implementing and auditing the guest agent and its host-side edges.

# Component-05: Session sandbox

## Purpose

The per-session untrusted guest executor: it runs one session's tool-calls as PID 1 in an isolated runtime, holds only session-scoped tokens (a control-channel Session JWT and a `filesystem_id`-scoped storage JWT — no signing key), and reaches the network only through the Egress trust-edge.

## Boundaries

The container is one process tree rooted at the guest agent (PID 1). The Control / operator API dials in to create and drive the session; the only outbound is the egress hop. Three host-side machineries sit outside the guest's network. The per-session exec supervisor terminates the exec WebSocket, spawns and reaps guest processes, and bounds stdio. The runtime supervisor is the isolation backer: the user-space-kernel sentry on the gVisor tier, the VMM on the microVM tier, the host kernel on runc. The runtime-monitor authors the guest's tool-call audit records out of band; the guest cannot disable it.

| Direction | What crosses | Internal terminator | Note |
|---|---|---|---|
| Control → guest | exec/PTY+CDP control union + stdin frames | exec supervisor (host-dialled; non-host peer dropped at accept) | one WebSocket per session; envelope frozen in [`exec/exec-channel`](../../../contracts/exec/exec-channel.schema.json) |
| Control → guest | Session JWT (selects session identity) | guest agent | TTL per [`02-trust-boundaries.md`](../02-trust-boundaries.md) §8 |
| Control → guest | mount config: `filesystem_id`, `service_url`, the off-box-issued scoped JWT, CA cert, mount paths (F7) | guest agent (mount client) | written before the in-guest mount client starts; the scoped JWT is the only storage credential the guest holds |
| guest → Control | stdout/stderr binary frames + result/EOF | exec supervisor | length-prefixed, bounded per call (Invariants) |
| guest → Egress | the sole outbound network leg (F8) | guest agent | carries the in-guest mount client's storage leg (F7a) and guest-internet alike; the guest holds no long-lived upstream secret on this leg; the edge attaches upstream authorization ([ADR-0005](../adr/0005-egress-credential-delivery-envoy-sds.md), [ADR-0007](../adr/0007-egress-auth-mechanism.md)); this is the container's only egress (invariant 4) |

The exec/PTY+CDP edge and the egress leg are the boundaries [`05-c4-container.md`](../05-c4-container.md) §4 names; the `F6`/`F7`/`F7a`/`F8` flow labels are defined there. The guest has no route to the audit pipeline; its sole outbound is the egress hop (invariant 5).

Owned state: the live process tree and its scratch/tmpfs, the per-process resource counters the exec supervisor keeps, and the guest's in-memory Session JWT and scoped storage JWT for the life of the session. The guest holds no signing key, no other-credential, no session denylist, and no kill-switch route; those sit host-side or off-box at the credential issuer. The guest resolves no name for the Control plane — that channel is host-opened off the guest network, so no guest-side lookup exists to retarget. The `service_url` it does resolve is an egress destination, not a control endpoint.

The contract carries the tagged-JSON control union and out-of-band binary stdio frames; field types and the bounded-reason error envelope live in the schema and are not restated. The exec supervisor, not the guest, terminates the socket. The runtime tier is selected by `workload_trust_profile`, not by the contract. The schema records the spawn-time environment fields; the host supervisor enforces the strip (Invariants).

## Invariants

Each is falsifiable by the named check; cross-cutting zone, egress-mode, retention, and isolation-tier-menu properties stay in Layer 3.

1. The guest agent is PID 1 and the container holds no process or token that outlives the session; teardown kills the process tree and destroys the cgroup (integration-test, NFR-REL-11).
2. The exec/PTY+CDP channel is a single host-dialled socket per session; a connection from any non-host peer is dropped at accept before any frame is parsed (accept-time negative-test, NFR-SEC-76 — the accept-time enforcement of NFR-SEC-43, scoped here to the Control listener).
3. Guest-originated code cannot reach the control/exec channel through the guest's own network stack, and a guest with in-sandbox root cannot present another session's identity (integration negative-test: guest-stack dial fails, forge-another-session fails — NFR-SEC-43).
4. The container has exactly one outbound network route and it is the Egress trust-edge; there is no second NIC or route (IaC-policy assertion, NFR-SEC-27).
5. The guest emits nothing to the audit pipeline and has no route to it; its tool-call events are authored host-side by the exec supervisor and the runtime-monitor, so a compromised guest can neither reach nor silence the record (no-egress-to-audit network assertion + host-authored-source test, NFR-SEC-47).
6. Inter-sandbox reachability is disabled by default; tenant A's sandbox cannot reach tenant B's without an explicit policy (NetworkPolicy + integration-test, NFR-SEC-22).
7. Every container carries `no-new-privileges`, cap-drop ALL with minimal add-back, seccomp BPF, read-only rootfs, user-namespace mapping (host UID 0 ≠ guest UID 0), and pids/cpu/mem cgroup limits; `docker.sock` is never mounted (admission-gate, NFR-SEC-14).
8. The configured runtime tier matches the deployment's declared `workload_trust_profile` per the pairing matrix; a mismatch is an admission-time hard error (admission test fixture, NFR-SEC-38).
9. A guest-spawned process inherits no host secret: the host supervisor strips the deny-pattern env set (`*_TOKEN`/`*_SECRET`/`*_PASSWORD`/`API_KEY`) at fork and injects only declared vars; no secret rides on argv (spawn-time fixture + property-test, NFR-SEC-75).
10. Per-stream stdout/stderr over the exec channel is framed, length-prefixed, and bounded per call; on reaching the ceiling the supervisor stops forwarding, emits a truncation marker with a dropped-byte count, and never buffers unbounded guest output into host memory (red-team output-flood suite, NFR-SEC-74).
11. Per-sandbox resource use is contained beyond the cgroup ceiling — scratch disk quota and deterministic OOM scoping (the breaching sandbox is the victim) — so one sandbox's flood holds co-resident sandboxes within the noisy-neighbour latency budget (red-team noisy-neighbour suite, NFR-SEC-46).
12. No session-scoped secret is present in guest RAM or disk at snapshot-create time, and on resume the guest re-derives a fresh host-attested identity and reseeds entropy and unique IDs so no two guests restored from one image share a token, nonce, RNG stream, or `boot_id` (offline image-extraction scan + N-fork uniqueness test, NFR-SEC-44 + NFR-SEC-71).
13. Every TTL/expiry decision the guest is subject to reads a monotonic clock immune to wall-clock setback, and on resume the wall clock is corrected before any time-bound check runs (red-team clock-rollback harness, NFR-SEC-48 + NFR-SEC-63 — trusted-time theme [#185](https://github.com/Wide-Moat/open-computer-use/issues/185), [`06-threat-model.md`](../06-threat-model.md) §5).
14. A recycled mount substrate carries no readable session-1 content into session-2: the page cache is dropped and the local mount/scratch region is zeroized (or its per-session DEK destroyed) before the region is re-granted, so erase completes-before re-grant (property test: write a session-1 marker, recycle, assert session-2 cannot read it, NFR-SEC-54 + NFR-SEC-64 + NFR-SEC-66). The resume-time CSPRNG/identity reseed that prevents a shared RNG stream is invariant 12, not restated here.

## Failure modes

Each row traces to one P5 STRIDE row in [`06-threat-model.md`](../06-threat-model.md) §3.1 and names that row's primary controlling NFR; the threat narrative, rating, and regulator cell stay there. A1 (the in-sandbox guest holding root) is the reaching actor for the §3.1 rows; A3 (post-escape or host foothold) for the at-rest snapshot row.

| Trace | Reaching actor | Container-internal recovery behaviour | Controlling NFR |
|---|---|---|---|
| P2-T2 | A1 | Guest stalls or drops the host-dialled control RPC to outlive a revoke/kill. Recovery is owned by the Control/operator API ([`02-control-operator-api.md`](02-control-operator-api.md)): the F6 denylist/kill-switch check is host-side, so an unreachable channel grants the guest no new authority. | NFR-SEC-01 |
| P5-D1 | A1 | Guest exhausts node resources (fork-bomb, disk fill, memory pressure). Fail-closed via the cgroup PID/CPU/mem ceiling plus scratch quota and deterministic OOM scoping — the offender is the OOM/quota victim, co-residents hold SLO. Residual: per-session quota precision — resource-exhaustion theme [#188](https://github.com/Wide-Moat/open-computer-use/issues/188). | NFR-SEC-14 + NFR-SEC-46 + NFR-SEC-74 |
| P5-D2 | A1 | Guest floods the edge to deny outbound for itself and co-tenants. Single forward route, deny-by-default; fail-closed drops outbound if the proxy is unreachable rather than bypassing. Residual: per-session egress rate-limit unstated — resource-exhaustion theme [#188](https://github.com/Wide-Moat/open-computer-use/issues/188). | NFR-SEC-05 + NFR-SEC-27 |
| P5-I1 | A1 | Guest mounts a microarchitectural side-channel against a co-resident tenant. Per-tier posture: the shared-kernel residual is declared-not-eliminated; the reduced tier pins SMT-off, current microcode, and single-tenant scheduling for flagged sessions. Residual: a measurable cross-tenant target — side-channel theme [#183](https://github.com/Wide-Moat/open-computer-use/issues/183), [#148](https://github.com/Wide-Moat/open-computer-use/issues/148). | NFR-SEC-58 |
| P5-I3 | A1 | Guest tunnels tenant data outbound on its one egress leg. The container's only recovery is that single route; detection and content inspection are owned by the Egress trust-edge, host-side ([`06-egress-trust-edge.md`](06-egress-trust-edge.md), F8), not by the guest. Residual: content-blind egress on the baseline hop — theme [#182](https://github.com/Wide-Moat/open-computer-use/issues/182). | NFR-SEC-57 |
| P5-I4 | A1 | A guest-spawned process inherits a host-env secret, or a secret on argv leaks via `/proc/<pid>/cmdline`. Allowlist-only env injection with the deny-pattern strip at fork; secrets pass via env or fd, never argv. | NFR-SEC-75 + NFR-SEC-43 |
| P5-T1 | A1 | With root the guest suppresses, fabricates, or reorders the OCSF events it would author for its own in-sandbox actions. The guest is never the authoritative source: a host-side mediation layer and a not-guest-disableable runtime-monitor session author the record out of band. Residual: purely in-sandbox actions with no host-side side-effect — guest-self-audit theme [#181](https://github.com/Wide-Moat/open-computer-use/issues/181). | NFR-SEC-47 |
| P5-R1 | A1 | An in-sandbox action cannot be non-repudiably attributed because its only candidate record originates inside the guest. Out-of-band host-authored evidence supplies the record and the monotonic-clock envelope orders accepted events. Residual: the in-sandbox-evidence gap (theme [#181](https://github.com/Wide-Moat/open-computer-use/issues/181)) plus the clock-trust dependency (theme [#185](https://github.com/Wide-Moat/open-computer-use/issues/185)). | NFR-SEC-47 + NFR-SEC-48 |
| P5-I2 | A3 | A snapshot/hibernation image freezes a live Session JWT and mount handle at rest; an image read recovers a usable token before TTL. The image is taken at minimal-init before session material is layered, and live token buffers are zeroized before a retained hibernate. Residual: a live secret in an off-cycle image — snapshot theme [#184](https://github.com/Wide-Moat/open-computer-use/issues/184). | NFR-SEC-44 + NFR-SEC-66 |
| P4-mount-I2 | A1 | A reused mount substrate leaks session-1 user-data into session-2 via page-cache or device-backend residue. Erase-before-reuse (invariant 14): the page cache is dropped and the local mount/scratch region zeroized — or its per-session DEK destroyed — before the region is re-granted, so erase completes-before re-grant; mount and handle are session-scoped, list/read stay confined to the `filesystem_id` prefix. Residual: deterministic per-session erasure ordering not yet pinned to an NFR scenario — re-homed from [`06-threat-model.md`](../06-threat-model.md) P4-mount-I2. | NFR-SEC-15 + NFR-SEC-54 + NFR-SEC-13 + NFR-SEC-64 + NFR-SEC-25 |

The host-facing default is fail-closed on every boundary the guest can pressure: an unreachable exec channel, a dropped egress route, and a failed teardown each deny authority rather than degrade open. Sandbox escape to the host kernel and the exec/PTY+CDP channel-spoof variants are MITIGATED in [`06-threat-model.md`](../06-threat-model.md) §4 (NFR-SEC-02/14, NFR-SEC-43) and are not live rows here.

## Operational concerns

Scaling axis is per session — one container per session `[1..N]`, lifecycle bound to the session ([`05-c4-container.md`](../05-c4-container.md) §3). Capacity is governed by the host substrate and the per-sandbox cgroup ceiling (NFR-SEC-14). Session-create targets ≤500 ms p99 warm-pool-hit (NFR-PERF-02), ≤2 s p99 cold-start (NFR-PERF-03), and ≤400 ms p99 on the user-space-kernel substrate (NFR-PERF-08). Compute-plane RTO for new sessions is ≤30 min with in-flight state non-durable (NFR-REL-02); stateful hibernate/resume/snapshot/fork is demonstrated end-to-end (NFR-REL-08).

Cooperative shutdown is `terminationGracePeriodSeconds=30`, SIGTERM→5 s→SIGKILL, tmpdir clean ≤10 s (NFR-REL-11). Teardown then runs a host-driven ordered finalizer that revokes the session credential, drops the outbound route, and scrubs writable surfaces before kill, independent of guest cooperation (NFR-SEC-65). A guest that ran a session is destroyed, never re-pooled (NFR-SEC-68); a warm-pool claim re-derives a fresh host-attested identity and discards the pre-warm placeholder (NFR-SEC-69).

Config surface: the runtime tier (set by `workload_trust_profile`, validated at admission — NFR-SEC-38), the cgroup/quota ceilings (NFR-SEC-14, NFR-SEC-46), the per-stream stdio ceiling (default ≤8 MiB/stream, retunable per tier — NFR-SEC-74), the spawn-time env allowlist (NFR-SEC-75), and the exec-channel capability flags negotiated in the handshake (trace, compression — see the contract). Concurrency on the exec channel is sequential-default with opt-in parallelism (NFR-IC-05); PTY and CDP multiplex one socket per session (NFR-IC-03).

Observability: the guest emits no audit events (invariant 5). The exec supervisor and the runtime-monitor author the guest's tool-call records host-side and emit them on the F10 fan-in (NFR-SEC-47 + NFR-SEC-03). A tier-downgrade of a running deployment fires `config.trust_profile.downgraded` within ≤30 s (NFR-SEC-39).

Shelf delta ([`05-c4-container.md`](../05-c4-container.md) §5, [`02-trust-boundaries.md`](../02-trust-boundaries.md) §8): the boundary invariants above hold on both shelves and only the substrate changes. The runtime supervisor that backs invariants 2–3, 10, and 12 is the host kernel with UDS peer-credential checks on the container tiers and the VMM with vsock on the microVM tier; the predicates (host-dialled channel, bounded stdio, no live secret in the image) do not change. The runtime-tier substrate and packaging pick is a future ADR; the FLEX-02 runtime ladder fixes the tier set, not the implementation.

## Open questions

1. Does the Session sandbox stay one container with internal components, or split into sub-containers once the workload-trust tier and guest-agent protocol are specified? — [#174](https://github.com/Wide-Moat/open-computer-use/issues/174).
2. Is workload-trust tier grading (`workload_trust_profile`, AP-13) a sub-context of its own, distinct from the session-lifecycle language inside Agent Execution? — [#168](https://github.com/Wide-Moat/open-computer-use/issues/168).
3. A measurable cross-tenant side-channel target on the shared-kernel tier ("tenant A cannot observe tenant B") is not yet an NFR scenario. — [#183](https://github.com/Wide-Moat/open-computer-use/issues/183), [#148](https://github.com/Wide-Moat/open-computer-use/issues/148).
4. Out-of-band evidence for purely in-sandbox actions with no host-side side-effect, and host-attested binding of the OCSF source at ingestion. — [#181](https://github.com/Wide-Moat/open-computer-use/issues/181).
5. Deterministic per-session erasure ordering and the live-secret-in-off-cycle-image residual on teardown/snapshot. — [#184](https://github.com/Wide-Moat/open-computer-use/issues/184).
