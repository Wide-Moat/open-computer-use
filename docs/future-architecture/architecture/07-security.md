<!-- SPDX-License-Identifier: BUSL-1.1 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# 07 — Security

> Threat model, secret-rotation strategy, egress controls, image signing, audit.
> Derived from [`sandboxd/docs/security.md`](../../../sandboxd/docs/security.md), adapted to our stack.

## Threat model

**We protect against:**
- Curious users probing what's reachable from the sandbox
- "Confused agent" — LLM hallucinating dangerous commands
- Prompt injection coercing the agent into exfil / lateral movement
- Direct adversaries with valid credentials
- Compromised dependencies (npm, pip) inside the sandbox

**We do NOT protect against:**
- Compromised control plane (L4) — if L4 is owned, game over by design
- Host kernel CVEs (assume patches applied)
- Side-channel attacks on shared cores (Spectre / Meltdown — kernel mitigations assumed)
- Hardware attacks (datacenter-level threat)
- Determined DoS by exhausting resources (mitigated by quotas, not prevented)

## Isolation responsibility per layer

| Layer | Trust posture | Primary control |
|---|---|---|
| L1 (agent) | Trusted by L4 (we wrote it); untrusted by host | Small surface, no auth (network-policy-enforced) |
| L2 (runtime) | **Primary security boundary** | Hypervisor / kernel isolation |
| L3 (provider) | Trusted infrastructure | NetworkPolicy, ResourceQuota, PSA, RBAC |
| L4 (control plane) | Most-trusted | Std hardening: mTLS, secrets, RBAC, WAF |

L2 carries the load for untrusted workloads. See the runtime matrix in [04-layer2-runtimes.md](./04-layer2-runtimes.md).

## Secret management

### Today (transitional)
- Anthropic API key, GitLab token, vision API key injected as env vars at container create time.
- Static for container lifetime; rotation requires container restart.
- Stored in k8s `Secret` objects (when on Helm) or `.env` files (Compose).

### Target (Phase 4 ships, Phase 6 expands)

- **Secret broker** lives in L4. Responsibilities:
  1. Read static long-lived secrets from the backing store (AWS Secrets Manager / GCP Secret Manager / Vault / k8s `Secret`) — operator concern.
  2. **Mint short-lived, scoped credentials per session:**
     - Anthropic / vision API keys: same-key issuance (Anthropic doesn't STS) — but rotated on schedule and injected via `/v1/configure` so rotation never requires restart.
     - S3: per-session STS tokens (AWS STS / MinIO STS) scoped to `bucket/sessions/{session_id}/*` only.
     - Egress JWT: signed per-session, encodes allowed destinations + expiry.
  3. **Rotate** static keys on a schedule (≤ 90 days) without downtime.
  4. **Revoke** on session end.

- **In the sandbox:** secrets arrive via `POST /v1/configure`. Never baked into image. Never logged.
- **Rotation pattern:** L4 calls `/v1/configure` again with new short-lived creds; sandbox swaps in place.

### Image signing

- All sandbox images signed with [cosign](https://github.com/sigstore/cosign).
- Admission controller (k8s) verifies signature; rejects unsigned or invalid.
- Templates reference images by **digest** (`sha256:...`), never tag.

## Network egress

- **Default-deny.** No direct internet from any sandbox.
- **Egress proxy** mediates every outbound connection.
  - Sandbox carries a per-session JWT in egress requests.
  - Proxy validates JWT signature, checks destination against the JWT-encoded allowlist, checks expiry.
  - Logs every request (audit).
- **Reference implementation:** [`Michaelliv/agentbox`](https://github.com/Michaelliv/agentbox) — port to Go for production (Phase 8).
- **Allowlist sources:** template-level baseline (e.g., `pypi.org`, `registry.npmjs.org`) + session-level additions (the agent's running task scope).

## Network ingress (to sandbox)

- Sandboxes are **not** publicly addressable.
- Only L3 (provider) reaches L1's port — enforced by k8s `NetworkPolicy` or Docker network isolation.
- The agent itself does **not** authenticate requests — defense is exclusively network-policy-level. Documented loudly to prevent "let's add an extra auth check" cargo-cult that misleads operators.

## Per-runtime residual risks (one-line each)

- **runc/sysbox:** shared host kernel → kernel CVE escapes the sandbox.
- **gVisor:** Sentry bugs (~500K LoC Go); passthrough syscalls.
- **kata-fc / kata-ch:** Firecracker / CH bugs (Rust, ~50-80K LoC); KVM bugs; side-channels on shared CPUs.

See [`sandboxd/docs/security.md`](../../../sandboxd/docs/security.md) for CVE history references.

## Sandbox hygiene

- **No reuse between tenants.** When a session ends, sandbox is destroyed. Never returned to the pool of another tenant.
- **Per-sandbox ServiceAccount** with empty RBAC (k8s) — sandbox can't enumerate the cluster.
- **`securityContext`:** `runAsNonRoot` (where the runtime allows — note: sysbox/kata enable safe root-in-sandbox), `allowPrivilegeEscalation: false`, drop ALL capabilities (re-add only needed ones), `seccompProfile: RuntimeDefault`.
- **`ResourceQuota` + `LimitRange`** per tenant namespace — blast-radius cap.

## Audit log

Mandatory events:
- Session created / configured / terminated
- Exec call (cmd hash, exit code, duration — **not** stdout/stderr verbatim)
- Egress request (destination, decision, JWT id — **not** body)
- Secret rotated
- Admission decision (template assigned)
- Runtime error / health-degraded

Forbidden in logs:
- stdout / stderr verbatim (may contain secrets)
- Env var values
- File contents
- HTTP body through proxy

Retention: **≥ 90 days**. Append-only sink. See [10-observability.md](./10-observability.md).

## Compliance posture (informational, not committed)

| Standard | Posture |
|---|---|
| PCI-DSS 2.4 (isolation) | `kata-ch` satisfies "logical separation" in spirit — get auditor sign-off per deployment |
| HIPAA | Same as above for PHI; encrypt persistent storage with per-session keys; PHI must not appear in audit logs |
| GDPR | Ephemeral by default; explicit DPA needed if persistence enabled |
| SOC 2 | Audit logging here aligns with SOC 2 evidence requirements |

## What ships, when

| Phase | Security change |
|---|---|
| 1–3 | No security change (refactor + storage) |
| 4 | **Secret broker** + per-session STS + key rotation |
| 5 | NetworkPolicy default-deny + ResourceQuota + empty-RBAC SA in Helm chart |
| 6 | mTLS L4 ↔ L3; OIDC for admin UI |
| 7 | Go agent shrinks attack surface; signed image enforcement |
| 8 | Egress proxy + audit-log pipeline + 90 d retention **(prereq for any untrusted tier)** |
| 9 | `kata-ch` / `kata-fc` raise the isolation ceiling — untrusted tier opens, gated on Phase 8 |
| 10 | Snapshot/restore + post-restore hardening (CRNG reseed, `init_on_free=1`, `CAP_SYS_RESOURCE` drop); KMS-backed per-session encryption keys for persistent storage |

## Source

- [`sandboxd/docs/security.md`](../../../sandboxd/docs/security.md)
- [`docs/future-architecture/references.md`](../references.md) (`agentbox`, `cosign`)
- [ADR-0006](../adr/0006-no-agpl-no-bsl-dependencies.md) (license hygiene)
