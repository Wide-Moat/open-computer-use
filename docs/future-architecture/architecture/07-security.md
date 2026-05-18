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

## Mandatory deny paths inside the workspace

Even with full L2 isolation, the agent itself must refuse to write a small set of paths that are vectors for persistent shell takeover or self-exfiltration. The list is **always-on, regardless of template configuration** — modelled on Anthropic's local sandbox-runtime ([`research/13`](../research/13-anthropic-sandbox-runtime.md) §2):

| Path / glob | Why blocked |
|---|---|
| `.bashrc`, `.bash_profile`, `.zshrc`, `.zprofile`, `.profile` | Persistent shell hijack — survives session, exfils on next user shell |
| `.gitconfig`, `.gitmodules` | Persistent git hooks via `[core] hooksPath`; submodule URL injection |
| `.git/hooks/*` | Hook execution on every git operation |
| `.mcp.json` | Sub-agent MCP server hijack |
| `.claude/`, `.claude-code/`, `.codex/`, `.opencode/` | Sub-agent CLI config / credential hijack |
| `.vscode/`, `.idea/` | IDE-driven code execution on user re-open |
| `.ssh/`, `.aws/`, `.gcp/`, `.kube/` | Credential exfil targets |
| `$PATH` directories owned by the user (`~/.local/bin/*`, `bin/*`) | Shadow-binary injection |

Enforcement: a Rust-side path-canonicalization check on every write in the L1 agent's file-ops handlers. Symlink targets are resolved before the check (see symlink-attack defenses in [`research/13`](../research/13-anthropic-sandbox-runtime.md) §6). Phase 7 implements; the antipattern reference is A1 / C-series.

## Graceful-shutdown protocol

When L3 needs to stop a sandbox — drain for upgrade, end-of-session, idle TTL — the protocol is **four steps, in order**. Skipping steps causes data loss (atomic-rename caught mid-flight) or audit-log gaps:

1. **Drop the page cache** inside the sandbox (echo 3 → drop_caches via the L1 control endpoint). Forces dirty data to disk; pending writebacks complete or fail visibly.
2. **`SIGTERM` to the workload process group.** Give it a grace period (default 10 s, template-tunable).
3. **Wait** for child reaper to confirm exit, or timeout.
4. **`SIGKILL`** to anything still running. Container teardown follows.

The L1 agent exposes this as `POST /shutdown` on the control plane ([05-layer1-guest-agent.md](./05-layer1-guest-agent.md)) and as a connect-side `Shutdown` RPC on the data plane. The two paths share the same state machine; whichever fires first wins.

## Defense-in-depth: `memfd_create` for the agent binary (Phase 9+)

Optional hardening for the microVM tiers: the L1 agent binary is loaded into a `memfd` at boot and the on-disk copy is unlinked. An attacker who lands code execution inside the sandbox cannot read the agent binary from disk to study it — `/proc/self/exe` resolves to a memory-only file descriptor.

This is purely defense-in-depth (the binary's source-equivalent is public). Cheap to implement once the agent is a static Rust binary; **Phase 9 nice-to-have, not Phase 7 must.**

## Snapstart-restore hardening (Phase 10)

When a sandbox resumes from a frozen Firecracker snapshot, the guest is **stale by design** — the kernel knows it forked but userspace does not. Without explicit re-initialization, userspace RNGs reseed from snapshotted state (worst-case identical seeds across restores), wall-clock is wrong by minutes-to-days, and any cached page references point into a rootfs that was just swapped underneath.

Mandatory on every restore (lifted from [`research/20`](../research/20-snapstart-hot-swap.md) §4):

| Action | Why |
|---|---|
| `drop_caches` after device hot-swap | Page cache references the frozen rootfs |
| Devtmpfs remount | Device-node mapping changed |
| `pivot_root` onto fresh rootfs | The frozen rootfs is stale |
| `clock_settime()` to current host time | Wall-clock was frozen |
| **CRNG reseed** (`getrandom`-style force) | Userspace RNGs (OpenSSL, glibc arc4random) don't notice the fork — without reseed, two sandboxes restored from the same snapshot can generate identical "random" values |
| Drop `CAP_SYS_RESOURCE` | Held only for init |
| Re-run env-var scrub | Template env may have changed since the template was frozen |

Template-build-time hardening:
- `init_on_free=1` kernel cmdline — zeroes freed pages before reuse so a fresh resume can't read template-VM secrets out of recycled memory.
- Template image built with **no `CAP_SYS_RESOURCE` retention** logic — the cap is held only during init.

Until Phase 10 ships, the L1 agent's `/mount_root` endpoint is **not exposed**. Adding it pre-Phase-10 is a footgun (untested resume path on a sandbox that was never frozen).

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
| 7 | Rust agent shrinks attack surface; signed image enforcement |
| 8 | Egress proxy + audit-log pipeline + 90 d retention **(prereq for any untrusted tier)** |
| 9 | `kata-ch` / `kata-fc` raise the isolation ceiling — untrusted tier opens, gated on Phase 8 |
| 10 | Snapshot/restore + post-restore hardening (CRNG reseed, `init_on_free=1`, `CAP_SYS_RESOURCE` drop); KMS-backed per-session encryption keys for persistent storage |

## Source

- [`sandboxd/docs/security.md`](../../../sandboxd/docs/security.md)
- [`docs/future-architecture/references.md`](../references.md) (`agentbox`, `cosign`)
- [ADR-0006](../adr/0006-no-agpl-no-bsl-dependencies.md) (license hygiene)
