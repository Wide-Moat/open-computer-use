<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# 04b — Credential Broker

> The host-side process that holds **real** cloud credentials so the sandbox guest never sees them. Follows the industry-observed FUSE-filestore-over-loopback broker pattern.
>
> **Phase placement.** Foundations in Phase 4 (secret broker section of [07-security.md](./07-security.md)); deployment-topology decisions referenced here. Final shape locked when Phase 4 ships.

## Why a broker (not credential injection)

The guest must reach S3, GCS, and the Anthropic API. The naive choices both fail:

- **Inject real keys into the guest env.** Any RCE in the guest exfils them. Violates the "no secrets in the sandbox" invariant.
- **Egress proxy that re-signs the request.** Works for HTTP headers (`x-api-key`); breaks for SigV4 because the signature covers the body the proxy cannot legally rewrite. AND it conflates the **network** plane with the **authorization** plane (see [§ Two planes, two mechanisms](#two-planes-two-mechanisms)).

The broker pattern: a trusted daemon outside the guest holds the real keys, accepts a **scoped JWT** from the guest over a host-controlled channel (vsock or loopback), and signs the outbound request itself.

```text
[ guest (untrusted) ]                            [ trust boundary ]
  FUSE filestore   ── HTTP/localhost:9112 ───►  broker (host-side)
   client                                          (real GCS/S3/API creds,
   (scoped JWT,                                    SigV4 / x-api-key signing,
    filesystem_id,                                 TLS origination outbound)
    NO secrets)
                                                       │
                                                       ▼
                                                GCS / S3 / model API
```

## Two planes, two mechanisms

**Network identity** (egress to the public internet): grounded in the **path itself** — the guest has no route out other than via the egress proxy. The HTTPS request carries no token. The proxy and broker know it's a sandbox because nothing else can reach them.

**Resource authorization** (per-session data access): grounded in a **scoped JWT** that encodes `session_id`, `filesystem_id`, scope (which bucket/prefix), and TTL. The broker validates the JWT and enforces scope.

These two planes are **orthogonal**. JWT does not authenticate egress; the network path does. JWT does not authenticate the network; it authorizes a specific resource operation. Conflating them produces either "secrets in the guest" (network-bound only) or a fake security perimeter (JWT for egress that the guest could leak anyway). Phase 4 + Phase 8 design must keep them separate.

## Broker contract

### Authentication / authorization
- Accept a per-session **Ed25519 JWT** from the guest. Validate signature, expiry, scope claims.
- Claims minimum set: `session_id`, `filesystem_id`, `tenant_id`, `ops` (e.g. `read`, `write`), `exp`.
- Reject anything outside the JWT's stated scope (no cross-session reads, no cross-tenant access).
- Support short TTLs (≤ 15 min target) and explicit revocation (broker-side blocklist by `session_id`).

### Upstream signing
- Hold the real GCS service-account key / S3 access keys / `x-api-key`, on disk via the host secret store (Vault, AWS Secrets Manager, k8s Secret with appropriate KMS) — never inside the guest.
- Sign each outbound call:
  - **S3 / S3-compatible** → SigV4 with broker's keys after scope check (guest never signs).
  - **Anthropic API** → inject `x-api-key` + `anthropic-version` after scope check.
  - **GCS** → service-account token exchange.
- **Terminate TLS outbound** (TLS origination): guest speaks plaintext to broker over a host-controlled channel; broker speaks valid HTTPS to upstream with strict cert validation (fail-closed).

### Filestore semantics
- CRUD: `list`, `stat`, `get`, `put`, `delete`, `move`.
- Logical paths (`/inputs`, `/outputs`, `/tool-results`) map to the physical backend (`bucket/prefix`) keyed on `filesystem_id`.
- Streaming for large objects — never buffer a whole file in broker memory.
- ro vs rw enforcement per mount point, derived from JWT `ops` claim.

### Operational
- Listen on loopback / vsock only — **never** on a public host interface.
- Audit log of every operation with `session_id`, `filesystem_id`, operation, decision, `trace_id` ([10-observability.md](./10-observability.md)).
- Per-token rate limiting; per-tenant aggregate quotas (cross-link [gaps.md § A](../gaps.md#a-multi-tenancy-beyond-per-session)).
- Domain allowlist (broker refuses to call upstreams outside the configured set).
- Health endpoint, Prometheus metrics (requests, auth errors, upstream latency).

## Deployment topology by runtime tier

The broker's home depends on the L2 runtime. The choice is **not** a single design but a per-tier matrix.

### Docker / runc / sysbox (shared kernel)

The broker is a sidecar process. Three options, in increasing isolation:

| Variant | Channel | Isolation | Verdict |
|---|---|---|---|
| Shared network namespace (`--network container:broker`) | `localhost:9112` | Weakest — shared network stack with the guest | **Anti-pattern for untrusted guests.** Use only for trusted-dev tiers. |
| Per-network user-defined Docker net | `broker:9112` via DNS | Separate netns; routing controlled by Docker | Acceptable for sysbox-class tenants. |
| Unix domain socket bind-mounted in | `/run/broker.sock` (ro mount in guest) | No shared netns at all | Strongest in this tier. |

### Firecracker / Cloud Hypervisor (microVM, own kernel)

Sidecar patterns do not apply — the guest has its own kernel, the boundary is the hypervisor (KVM). The broker **must** live host-side and the guest reaches it through an explicit host↔guest channel:

| Channel | Notes |
|---|---|
| **virtio-vsock** | Preferred. Native Firecracker/CH primitive, no TCP/IP needed in the guest. Guest can run with no network at all, just vsock → broker. |
| TAP + IP | Use only when the guest needs a routed network for other reasons. Broker listens on a host address; host-side firewall blocks anything else from the guest. |

The microVM tiers **strengthen** the broker pattern: guest kernel escape (the most common shared-kernel failure mode) does not reach the broker — KVM is in the way.

### Localhost ergonomics over a non-local channel: the vsock shim

Application code (FUSE filestore client, custom backends) assumes `localhost:9112`. To preserve that ergonomics on a microVM tier without baking vsock awareness into every caller:

```text
GUEST (Firecracker):
  FUSE filestore client  →  127.0.0.1:9112    ← caller thinks it's local
        └── vsock-shim: listens on 127.0.0.1:9112,
            forwards to vsock(host CID, port 9112)    ← dumb bridge, NO secrets

══════════════════ KVM hypervisor ══════════════════

HOST:
  vsock-listener :9112
        └── broker (real creds) → S3 / model API / GCS
```

The shim is a **dumb forwarder** — it holds no keys, runs no policy, knows no JWTs. Implementations: `socat VSOCK-CONNECT ... TCP-LISTEN:9112` for prototyping, or a tiny static Rust/Go binary in the L1 image for production. The illusion of "localhost broker" is independent of whether the host runs one shared broker or broker-per-VM — pick the multi-tenancy posture separately.

## Multi-tenancy: shared broker vs broker-per-VM

A single process serving every guest's traffic = **shared fate** (one broker bug or RCE leaks credentials across tenants). The anchor for safe multi-tenancy is the **vsock CID** assigned by the hypervisor: it is set on the host side, the guest cannot spoof it, and the broker sees it on every connection.

| Posture | Mechanic | Blast radius | Recommendation |
|---|---|---|---|
| **Single multiplexing broker** | One process, partitions state by CID + JWT scope | All tenants share one process — compromise = total exposure | Only for trusted-tier deployments |
| **Broker-per-VM** | One lightweight broker process per VM, started at VM boot, holds only that VM's short-lived creds | Per-tenant — broker dies with the VM | **Recommended** for untrusted tiers |
| **Per-VM + delegated STS** | Per-VM broker, but the broker itself does not hold a master key — pulls scoped temp credentials from L4 at boot | Per-session — even broker compromise leaks only that session's scoped STS | **Target** for compliance-bearing tiers (cross-link [gaps.md § C](../gaps.md#c-compliance-and-audit-immutability)) |

Localhost ergonomics (the vsock shim) and strong isolation (broker-per-VM + per-VM STS) are **not** mutually exclusive. Phase 4 ships the per-VM model; Phase 6 adds delegated STS.

## Filesystem-scope as a first-class secret-scope dimension

The `filesystem_id` JWT claim is what makes one session's filestore invisible to another, **architecturally** rather than via file permissions:

- The broker maps `(tenant_id, filesystem_id) → bucket/prefix` server-side.
- The JWT names the `filesystem_id` it's authorized for; the broker refuses any path outside that prefix.
- Cross-session reads are not "guarded" — they're impossible to express because the JWT cannot name another session's `filesystem_id`.

This is the design lever that lets per-session FUSE mounts (`filestore:session_<SESSION_ID>:/path` style) work without per-session credentials in the guest.

## Open questions (resolve before Phase 4 ships)

- **Issuer of the scoped JWT.** L4? Per-session minting? Where the signing key lives and rotates. **This is the gating decision** — the JWT is the only barrier between "the guest asked" and "the broker spent a real key." Resolve first.
- **JWT binding to vsock CID.** Either embed CID in claims (broker verifies channel CID == claim CID — defense in depth) or rely purely on the unforgeable CID (simpler).
- **FUSE mount vs HTTP API only.** The FUSE client path uses a mount; some workloads only need the HTTP CRUD. Phase 4 ships HTTP first; FUSE-in-guest behind a feature flag.
- **Upstream set on day one.** S3 only? Plus Anthropic Files API? Plus GCS? Start minimal — each upstream is a new attack surface.
- **Physical backend.** MinIO (PoC), AWS S3, OVH Object Storage. Path-style vs virtual-hosted for S3-compatible — broker normalizes.

## Related

- [04-layer2-runtimes.md](./04-layer2-runtimes.md) — runtime tiers and per-tier isolation mechanics.
- [05-layer1-guest-agent.md](./05-layer1-guest-agent.md) — L1's `Configure` RPC delivers the scoped JWT into the guest.
- [06-storage.md](./06-storage.md) — Tier 4 (user data) mounts that the broker serves.
- [07-security.md](./07-security.md) — secret broker phase placement, image signing, audit log.
- [08-networking.md](./08-networking.md) — egress proxy (the other half of "no secrets in the guest").
- [10-observability.md](./10-observability.md) — audit-event schema, secret-scrubbing rules.

## Source

- Internal design notes — credential-broker spec, the two-planes-of-identity argument, and the no-S3-keys-in-the-guest rule.
