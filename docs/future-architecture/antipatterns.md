<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# 16 — Antipatterns by phase (operational decision log)

> Source: [`sandboxd/docs/antipatterns.md`](../../../sandboxd/docs/antipatterns.md) + footgun sections in `research/01-15` + production-gap notes.
>
> **This is a decision log, not a generic survey.** Each entry filtered for our stack (k8s + Kata + Cloud Hypervisor + Rust agent ([ADR-0002](./adr/0002-guest-agent-language-go.md)) + Go control plane ([ADR-0001](./adr/0001-control-plane-language-go.md)) + Computer Use + connect-go L4↔L3 RPC). Antipatterns that don't apply to our chosen stack are dropped explicitly. Each kept antipattern carries **our choice** in addition to "don't do this".
>
> Use this doc when planning a phase: before you write code for Phase N, scan the entries tagged `Phase N` here. Reviewers reject PRs that reintroduce documented antipatterns without an ADR.

## Format

Each entry has:
- **Antipattern** — what NOT to do.
- **Source** — `sandboxd/docs/antipatterns.md:LINE` or `research/NN-*.md` section.
- **Failure mode** — what breaks in production.
- **Our choice** — locked decision for our stack.
- **First-bites phase(s)** — where it would FIRST appear if we slip.
- **Detection** — how a reviewer catches it.

---

## Section A — Excluded as not applicable to our stack

Listed so future contributors don't waste time rediscovering generic warnings that don't apply to us. Each carries the reason it's excluded.

| Antipattern | Source | Why excluded |
|---|---|---|
| Mounting `/var/run/docker.sock` into sandbox | sandboxd:12-34 | We don't ship Docker in prod — only containerd under Kata ([ADR-0003](../adr/0003-docker-poc-first-then-k8s.md)). Compose PoC removes DinD by Phase 5. |
| Mounting host `/var/lib/docker` | sandboxd:79-95 | Same as above. |
| Maintaining both Compose AND Helm | sandboxd:331-347 | Compose stays as PoC only; Helm is the prod artifact ([ADR-0003](../adr/0003-docker-poc-first-then-k8s.md)). |
| Using gVisor for browser-heavy workloads | sandboxd:43-59 | We chose Kata+CH for browser; gVisor only for non-browser code-exec tier (Phase 7, experimental). |
| Single global runtime for all workloads | sandboxd:61-77 | One cluster = one runtime today (kata-ch). Multi-tier templates per-tenant arrive in Phase 9 — record as a Phase-9-research item. |
| Building 7 GiB sandbox images | sandboxd:223-239 | Implementation discipline, not an architectural choice; tracked in image-build CI not here. |
| Using `kubectl exec` to inject session config | sandboxd:349-365 | We have L1 agent with connect-go `Configure` RPC. `kubectl exec` is never used for session injection. |

---

## Section B — Antipatterns we WILL hit if we slip

Ordered by phase where they FIRST become possible.

---

### A1 — `rm`-the-binary is not security by itself

- **Source.** `sandboxd/docs/antipatterns.md:38-70`. Quote: "Linux keeps the inode alive… With root inside the sandbox: `cp /proc/1/exe /tmp/extracted_binary`".
- **Failure.** Compromised root in sandbox copies our agent out of `/proc/1/exe` and reverses it.
- **Our choice — defense in depth, not single layer.**
  - `memfd_create` so the binary never touches a real FS path.
  - `hidepid=2` on `/proc` mount inside sandbox.
  - `PR_SET_DUMPABLE=0` on agent PID 1.
  - Non-root inside sandbox where the runtime allows (Kata is fine).
  - Separate PID namespace (Kata gives this for free).
- **Phase.** 7 (Rust agent) — implement all four together; do not ship the agent rewrite without them.
- **Detection.** PR-review checklist for Phase 7. CI test asserts `cat /proc/1/exe` from inside a built sandbox returns nothing.

### A2 — Service per pod / Service per session

- **Source.** `sandboxd/antipatterns.md:367-383`.
- **Failure.** N services × M sessions → kube-apiserver melts; endpoints controller stalls; iptables/IPVS rules churn.
- **Our choice — one headless Service per pool, app-layer routing in control plane.**
  - One headless Service per warm pool, pod DNS via stable name.
  - L4 reads `session_id → pod_IP` from Valkey (KV) and forwards directly. No per-session k8s Service.
- **Phase.** 5 (`KubernetesProvider`) — wire this in from day one; never go through a per-session Service even for "quick prototype".
- **Detection.** Grep Helm templates and provider code for `kind: Service` inside any session-creation path. Should not exist outside the pool-level Service.

### A3 — Cluster autoscaler without overprovisioning

- **Source.** `sandboxd/antipatterns.md:97-113`.
- **Failure.** Cold start dominated by 2–5 min node provisioning; spike of new sessions → users see "creating sandbox…" for minutes; SLO violation.
- **Our choice — overprovisioning pause-pods with `priorityClassName`.**
  - Pause-pods at lower priority occupy headroom on each node group.
  - Real sandboxes evict pause-pods instantly → no cold-node wait.
  - Cluster autoscaler still scales pause-pod ReplicaSet up so headroom is restored.
- **Phase.** 5 (k8s deployment shape) — ship pause-pods in the Helm chart as opt-in `overprovisioning.enabled`, default off; flip on in Phase 9 when kata bare-metal pool lands and cold-start cost matters.
- **Detection.** Look for `priorityClassName: system-cluster-critical` or `overprovisioning` in Helm values; alert on `cluster_autoscaler_unschedulable_pods_count` spikes.

### A4 — Session affinity via k8s `sessionAffinity: ClientIP`

- **Source.** `sandboxd/antipatterns.md:209-226`.
- **Failure.** Under corporate NAT / mobile carriers all traffic shares one IP → all sessions pin to one pod → that pod overloaded, others idle. Capacity adds don't help latency.
- **Our choice — application-layer routing only.**
  - L4 looks up `session_id → pod_IP` in Valkey on every request.
  - Forward HTTP directly to pod IP.
  - **Never** `Service.spec.sessionAffinity: ClientIP` in any chart.
- **Phase.** 6 (Go control plane) — implement at the gateway layer.
- **Detection.** Grep all Helm templates and k8s manifests for `sessionAffinity`; default value is `None`, we never set anything else.

### A5 — Pod IP caching without TTL or invalidation

- **Source.** `sandboxd/antipatterns.md:133-149`.
- **Failure.** Pod dies → IP reassigned to another tenant → traffic for session X lands in tenant Y's pod → tenant data crosses tenants.
- **Our choice — TTL + watch-driven invalidation.**
  - Valkey entries TTL 60 s.
  - L4 runs a k8s Informer `watch` on sandbox pods.
  - On `Pod Deleted` / `Pod Failed` event → invalidate entry by name.
  - Routing fetches fresh IP from Informer cache, not stale Valkey.
- **Phase.** 5 (KubernetesProvider event subscription) + Phase 6 (KV semantics in L4).
- **Detection.** Code review: any cache write of `pod_IP` must be followed by a delete-on-event path. Integration test: kill a pod mid-session, confirm next request 404s with "session lost" (not "wrong pod served it").

### A6 — `kubectl exec` to inject env into running Chromium (or any tool)

- **Source.** `sandboxd/antipatterns.md:349-365`.
- **Failure.** Env mutation after process start does not affect already-spawned process; you set `HTTP_PROXY=...` and Chromium still bypasses the egress proxy because it cached env at start.
- **Our choice — Chromium starts AFTER `Configure`.**
  - Pool member = warm with pre-loaded Chrome dependencies, **but Chrome not running**.
  - On session assign: L4 calls `Agent.Configure(ctx)` → agent receives env/secrets/JWT → agent starts Chrome with the right env in one step.
  - We never mutate env on a running process.
- **Phase.** 7 (Rust agent) — `Configure` must complete before any tool RPC accepted.
- **Detection.** Agent state machine has `unconfigured | configured | running`. RPCs other than `Configure` return `FailedPrecondition` in `unconfigured`. Test asserts.

### A7 — Trust agent for authentication

- **Source.** `sandboxd/antipatterns.md:269-283`.
- **Failure.** If L1 is owned, in-process auth check is bypassable anyway. False sense of security. Key rotation forces sandbox restart.
- **Our choice — auth in L4 only.**
  - L1 trusts whoever can reach its connect-go port.
  - Network policy + Kata isolation ensures only L4 can.
  - Agent does NOT validate JWTs.
  - **Counter-pattern note from [`research/15-claude-code-reverse-engineering.md`](./research/15-claude-code-reverse-engineering.md) §6:** Anthropic adds public-key JWT verification at L1 as defense-in-depth. We revisit if we ever expose L1 over TCP at scale; for vsock/localhost it stays "trust the network".
- **Phase.** 7 (Rust agent design).
- **Detection.** Grep `jwt.Parse`, `jwt.Verify` in agent code — should not exist.

### A8 — Long-lived egress tokens (e.g. 30 days)

- **Source.** `sandboxd/antipatterns.md:286-299`.
- **Failure.** Mid-session compromise → attacker has 30-day exfil window. Rotating signing key invalidates all live tokens at once.
- **Our choice — per-session JWT, lifetime = session-max (4 h).**
  - L4 mints on `CreateSession`.
  - Egress proxy validates signature + `exp` + `allowed_hosts` on every request.
  - Key rotation ≤ 90 d with overlap window (`kid` header).
  - Refresh endpoint for sessions > 4 h ([`research/09-agentbox.md`](./09-agentbox.md) §6).
- **Phase.** 4 (broker) + Phase 8 (egress proxy).
- **Detection.** Audit log lists JWT `exp` per session; alert on `exp > now + 4h`. Code review: signing function clamps `exp` to session-max.

### A9 — Persistent sandbox state by default

- **Source.** `sandboxd/antipatterns.md:302-316`.
- **Failure.** Disk bloat; compliance liability (GDPR/HIPAA — old PII on disk); compromised sandbox reads prior tenant's data.
- **Our choice — ephemeral by default, no persistent sandbox-workspace tier.**
  - Computer Use sessions are hours, not days.
  - "Continue yesterday's session" is served by **Tier 4 (S3 with `filesystem_id` token auth)**, not by a persistent Tier 3 workspace. The next VM re-binds to the same `filesystem_id` prefix — the user's files reappear without any persistent workspace volume.
  - **No PVC for the session workspace tier in any template.** Locked — see [A37](#a37--pvc-for-sandbox-session-workspace).
  - **Encryption still applies to the persistent user-data tier (Tier 4).** Moving continuity to Tier 4 does not retire the encryption requirement — the `filesystem_id`-keyed S3 prefix carries the same obligation. See [A34](#a34--no-per-session-encryption-for-persistent-data).
- **Phase.** 3 (storage MVP) + ongoing.
- **Detection.** Helm chart's default `SandboxTemplate.persistence: ephemeral`. Validate at admission.

### A10 — Embedding secrets in sandbox images

- **Source.** `sandboxd/antipatterns.md:259-275` nearby.
- **Failure.** Image registry compromise → all secrets ever shipped leaked. Rotation requires rebuild.
- **Our choice — secrets only via `Agent.Configure` RPC.**
  - Image is stateless.
  - L4 broker mints scoped tokens per session, delivered via `Configure(ctx)`.
  - Image-build CI rejects PRs that add `ENV ANTHROPIC_API_KEY=…` etc.
- **Phase.** 4 (broker) — but the discipline starts at Phase 1 image hygiene.
- **Detection.** `grep -E '(API_KEY|TOKEN|SECRET)=.+' Dockerfile`. CI gate.

### A11 — Builds without reproducibility

- **Source.** `sandboxd/antipatterns.md:241-257`.
- **Failure.** Two builds of the same source produce different images → can't verify supply-chain → cosign signature on wrong artifact passes admission.
- **Our choice — pinned versions + `SOURCE_DATE_EPOCH` + cosign + verify at admission.**
  - Phase 1: pin every `apt`/`pip`/`npm` version in `Dockerfile`.
  - Phase 5: cosign-sign images in release CI; deploy by `@sha256:`.
  - Phase 5: admission controller verifies signature (`sigstore-policy-controller` or `connaisseur`).
- **Phase.** 1 (pin), 5 (sign + verify).
- **Detection.** Build twice in CI, assert image digests match. Admission rejects unsigned images in test cluster.

### A12 — Warm pool without bounds

- **Source.** `sandboxd/antipatterns.md` (warm-pool patterns).
- **Failure.** Unbounded pool → cluster OOM. No `maxAge` → stale members carry leaked state.
- **Our choice — `min/target/max + refillRate + maxAge`.**
  - Defaults: `minSize=5, targetSize=20, maxSize=50, refillRate=3/s, maxAge=30m`.
  - All four are knobs in `SandboxTemplate`.
  - Pool controller smooths target against recent demand (EWMA over 5 min).
- **Phase.** 2 (skeleton, `minSize=0`) → Phase 5 (real defaults).
- **Detection.** Template admission rejects `maxSize` unset or `maxAge > 1h`.

### A13 — No idle timeout

- **Source.** `sandboxd/antipatterns.md:475-491`.
- **Failure.** Sandbox runs forever after user closes browser → wasted RAM/CPU at scale.
- **Our choice — multi-tier cascade.**
  - User session idle (no `/mcp` calls): 10 min → L4 sends `Agent.Shutdown`.
  - Sandbox no-agent-requests: 30 min → L3 force-stops.
  - Max session lifetime: 4 h → L4 terminates.
  - Agent self-shutdown safety net: 2 h since last `Configure` → agent exits.
  - Pool member age: 30 min unleased → recycled.
- **Phase.** 2 (skeleton in pool-manager), Phase 6 (full cascade in L4).
- **Detection.** Metrics: histogram of session-lifetime; alert if p99 > 4 h.

### A14 — Logging user output verbatim

- **Source.** `sandboxd/antipatterns.md:406-420`.
- **Failure.** Stdout from agent contains user secrets (printed API keys, file contents) → logs become a credential-harvest target → SOC2/PCI audit fails.
- **Our choice — structured metadata only.**
  - Log: `{session_id, tool, exit_code, duration_ms, stdout_bytes, stderr_bytes}`.
  - Never: stdout/stderr verbatim, env values, file contents, HTTP bodies through egress proxy.
  - Optional "verbose" pipeline (off by default) for debugging, behind stricter RBAC, separate retention.
- **Phase.** 6 (L4 emission) + Phase 8 (audit pipeline).
- **Detection.** Schema validation on audit-log writes; forbidden fields rejected. Code review for `logger.info(f"stdout: {output}")` patterns.

### A15 — `SIGKILL` without grace period

- **Source.** `sandboxd/antipatterns.md:425-438`.
- **Failure.** Chrome / Python killed mid-write → temp files, sockets, pipes left over → next session inherits stale state.
- **Our choice — `terminationGracePeriodSeconds: 30` + cooperative shutdown.**
  - L4 sends `Agent.Shutdown` RPC → agent drops page caches → `SIGTERM` to children → waits 5 s → `SIGKILL` survivors → exits.
  - k8s grace period 30 s gives agent time.
  - WS clients receive shutdown frame to flush.
- **Phase.** 7 (agent shutdown RPC) + Phase 5 (Helm `terminationGracePeriodSeconds`).
- **Detection.** Test: send `Shutdown` to an agent running `sleep 60`; verify exit within 10 s with clean tmp dir.

### A16 — `restartPolicy: Always` for sandbox

- **Source.** `sandboxd/antipatterns.md:187-203`.
- **Failure.** Sandbox is a session, not a service. Auto-restart on crash → session resurrects with stale state, mid-tool-call → user sees inexplicable behavior.
- **Our choice — `restartPolicy: Never`.**
  - On crash → L3 emits event → L4 invalidates session → user notified.
  - Pool members never auto-restart; the controller spawns fresh members instead.
- **Phase.** 5 (Helm template) — default and not overridable.
- **Detection.** Admission webhook rejects `restartPolicy != Never` in any sandbox-labeled pod.

### A17 — Treat sandboxes as cattle indiscriminately

- **Source.** `sandboxd/antipatterns.md:205-221`.
- **Failure.** Replacing an in-use sandbox mid-session = losing the user's work.
- **Our choice — pool members = cattle; assigned sandboxes = pets.**
  - Pre-assignment: replaceable, recycled freely.
  - Post-assignment (leased to session): immutable identity, never auto-replaced.
  - This is exactly the agent-sandbox CRD model — adopt as-is ([`research/06-agent-sandbox.md`](./research/06-agent-sandbox.md)).
- **Phase.** 5 (k8s provider semantics).
- **Detection.** Pool controller code paths: `evictable` filter must check lease state.

### A18 — "Build yet another platform"

- **Source.** `sandboxd/antipatterns.md` meta + our own scope discipline.
- **Failure.** We end up maintaining an inferior k8s operator + inferior egress proxy + inferior hypervisor instead of building Computer Use product.
- **Our choice — adopt + integrate, don't reinvent.**
  - **Orchestration:** `agent-sandbox` CRDs ([`research/06-agent-sandbox.md`](./research/06-agent-sandbox.md)).
  - **Runtime:** Kata + Cloud Hypervisor as-is.
  - **Egress proxy:** start with agentbox Python ([`research/09-agentbox.md`](./research/09-agentbox.md)), fork-and-port to Go in Phase 8 only when scale demands.
  - **Agent:** ours (Go per [ADR-0002](../adr/0002-guest-agent-language-go.md)).
  - **Control plane:** ours (Go per [ADR-0001](../adr/0001-control-plane-language-go.md)) — this is the differentiator.
- **Phase.** All — referenced in each phase's "Depends on" sections.
- **Detection.** Any PR adding `internal/operator/` or `internal/hypervisor/` triggers ADR-required gate.

### A19 — Premature cold-start optimization

- **Source.** `sandboxd/operations.md` meta.
- **Failure.** Spending months on CH snapshot/restore before knowing if warm pool alone solves cold start → engineering capacity wasted.
- **Our choice — measure first.**
  - Phase 5: warm pool with `minSize=5`. Measure p99 session-create.
  - Phase 10: snapshot/restore only if measured p99 still misses SLO.
  - Do not implement snapshotting in Phases 6–9.
- **Phase.** 10 gated on Phase-5-onwards measurements.
- **Detection.** Phase 10 spec must cite p99 numbers from production showing warm pool insufficient.

### A20 — `cache=always` in virtio-fs at density

- **Source.** [`research/04-cloud-hypervisor.md`](./04-cloud-hypervisor.md) §3, §9.
- **Failure.** Host page cache multiplies per VM → 100 VMs × shared dir = 100× the RAM. Thrashing, OOM.
- **Our choice — `cache=never` for untrusted-tier templates.** `cache=always` only for low-density single-tenant trusted templates with explicit memory budget.
- **Phase.** 9 (Kata templates) — virtiofsd args baked into template defaults.
- **Detection.** Admission webhook rejects `kata-*` template if `cache=always` is set without `template.tier=trusted`.

### A21 — Skipping seccomp in production

- **Source.** [`research/04-cloud-hypervisor.md`](./04-cloud-hypervisor.md) §9, [`research/05-firecracker.md`](./05-firecracker.md) §6.
- **Failure.** Hypervisor escapes that seccomp would have blocked become host compromises.
- **Our choice — seccomp ON by default, `--seccomp log` only for debug, never `--seccomp false` in prod.**
- **Phase.** 9 (Kata templates).
- **Detection.** Helm values reject `--seccomp false`. Runtime audit: alert on syscall denials from VMM threads.

### A22 — GPU passthrough on snapshottable templates

- **Source.** [`research/04-cloud-hypervisor.md`](./04-cloud-hypervisor.md) §6.
- **Failure.** VFIO devices break CH snapshot. Template silently fails to snapshot; pause/resume loses state.
- **Our choice — no GPU on any snapshottable template.** If a future template needs GPU, mark it `snapshot: disabled` explicitly.
- **Phase.** 10 (snapshot/restore).
- **Detection.** Admission webhook rejects `snapshot.enabled && devices[*].vfio`.

### A23 — Landlock hotplug paths not pre-declared

- **Source.** [`research/04-cloud-hypervisor.md`](./04-cloud-hypervisor.md) §9.
- **Failure.** Hot-add disk denied by Landlock at runtime → silent failure.
- **Our choice — pre-declare all possible mount paths in `--landlock-rules`** at VM creation. Phase-9 templates carry a `hotplug_paths` field.
- **Phase.** 9.
- **Detection.** Template validation: `hotplug_paths` must include any path referenced by `mounts[*]`.

### A24 — Hostname allowlist without DNS-rebinding defense

- **Source.** [`research/09-agentbox.md`](./09-agentbox.md) §9 + sandboxd egress patterns.
- **Failure.** Allowlist `api.example.com`; attacker controls DNS; resolves to internal IP → SSRF.
- **Our choice — proxy resolves DNS itself, pins to public IP ranges only.**
  - Egress proxy uses a known recursive resolver, not the sandbox's resolv.conf.
  - Resolved IP checked against RFC1918 blocklist before connect.
  - Per-session JWT also carries `allowed_hosts`, but DNS resolution is proxy-owned.
- **Phase.** 8 (egress proxy implementation).
- **Detection.** Proxy unit tests for DNS rebinding cases (low-TTL host that flips IP between resolutions).

### A25 — HTTP body / response logging through egress proxy

- **Source.** `sandboxd/security.md` "Do not log".
- **Failure.** Bodies contain secrets (API responses with tokens, downloaded files). Audit pipeline = secrets store.
- **Our choice — egress proxy logs metadata only.** `{ts, session_id, target_host, port, verdict, bytes_out, bytes_in, latency_ms, jwt_id}`. Never bodies, never headers beyond Host/User-Agent.
- **Phase.** 8.
- **Detection.** Proxy code review: response handler must not pass body to logger. Audit schema validates field set.

### A26 — Logging environment variable values

- **Source.** `sandboxd/security.md` "Do not log".
- **Failure.** Diagnostic log dumps `os.environ` → secrets leak.
- **Our choice — log env keys only, never values.** If a debug log needs a value, it goes through the sensitive-log pipeline with RBAC.
- **Phase.** 6, 7.
- **Detection.** Code review for `repr(env)` / `f"{os.environ}"`.

### A27 — Single global agent binary (no versioning)

- **Source.** Inferred from `research/02-e2b-infra.md` §12 (version-gated metrics) + sandboxd operations.
- **Failure.** Updating the agent binary forces all sandboxes to upgrade simultaneously. Rollback impossible without rebuilding the world.
- **Our choice — agent version baked in image tag; per-template image digest.** L4 metrics + control queries the agent's version on `Configure`; can keep multiple agent versions in production simultaneously (one per template).
- **Phase.** 7.
- **Detection.** `Agent.Health` response includes `agent_version`. L4 logs agent_version alongside session_id.

### A28 — `RuntimeClass` baked globally (no per-template override)

- **Source.** [`research/06-agent-sandbox.md`](./06-agent-sandbox.md) §3, §9.
- **Failure.** Want to add gVisor as experimental tier or kata-fc for free trial — requires changing default; affects everyone.
- **Our choice — `runtime_class` is a `SandboxTemplate` field, not a deployment default.** Default = kata-ch; templates can override.
- **Phase.** 9 (multi-template) — already aligned in [`architecture/09-templates.md`](../architecture/09-templates.md).
- **Detection.** Helm chart has no `runtimeClassName` outside template specs. Provider passes `template.runtime_class`.

### A29 — No template smoke test in deployment

- **Source.** sandboxd ops + general.
- **Failure.** New template version ships, all sessions assigned to it fail because of a typo.
- **Our choice — every template ships with a smoke test job that spawns it once, runs a tiny exec (`echo ok`), tears down.** Helm post-install hook runs it; rollout blocked on failure.
- **Phase.** 5 (Helm) + every template change.
- **Detection.** Template PR-required: matching `smoke_test:` block.

### A30 — Implicit assumptions about kernel version

- **Source.** [`research/10-sysbox.md`](./10-sysbox.md) §7 (CVE table requires kernel ≥ 5.16).
- **Failure.** Helm chart deploys on RHEL 8 (kernel 4.18) → sysbox vulnerable to CVE-2022-0185 → escape.
- **Our choice — Helm pre-install hook validates node kernels.**
  - Required: kernel ≥ 5.16 on all sysbox nodes; ≥ 5.5 for vsock; KVM available on Kata nodes.
  - Mismatch → install fails with explanatory error.
- **Phase.** 5.
- **Detection.** Hook script in chart; CI matrix on multiple kernel versions.

### A31 — Wildcard allowed-hosts (`*.com`)

- **Source.** [`research/13-anthropic-sandbox-runtime.md`](./13-anthropic-sandbox-runtime.md) §8.
- **Failure.** Operator sets `*.com` "for convenience" → effectively allows any host → egress proxy useless.
- **Our choice — JWT validator rejects patterns that match more than two label-segments wildcards (`*.*.com` etc) and rejects suffix-only TLD matches (`*.com`, `*.org`, `*.io`).**
- **Phase.** 8.
- **Detection.** Proxy unit test for each rejection class; admission rejects templates with overly broad `egress_baseline`.

### A32 — No timeout on CONNECT tunnels

- **Source.** [`research/09-agentbox.md`](./09-agentbox.md) §3, §10.
- **Failure.** Slow upstream → tunnel goroutine pinned forever → resource exhaustion at egress proxy.
- **Our choice — read/write timeouts on every tunnel; default 5 min idle, 1 h total.**
- **Phase.** 8.
- **Detection.** Proxy config required: `tunnel_idle_timeout` + `tunnel_max_lifetime`. Reject if unset.

### A33 — No key rotation for egress JWT signing key

- **Source.** [`research/09-agentbox.md`](./09-agentbox.md) §8.
- **Failure.** Key compromise = forge any session's egress JWT until manual rotation.
- **Our choice — RS256/ES256 with `kid` header; rotate ≤ 90 d via secret broker; overlap window 24 h.**
  - Old + new public keys both accepted during overlap; signer uses new.
  - Egress proxy fetches public-key set on startup + every 1 h.
- **Phase.** 4 (broker) + Phase 8 (egress proxy).
- **Detection.** Broker metric: time-since-last-rotation; alert at 80 d.

### A34 — No per-session encryption for persistent data

- **Source.** sandboxd security + sandboxd §11 implications.
- **Failure.** Persistent PVC reused across tenants without scrubbing → data crosses.
- **Our choice — if persistence enabled, KMS-backed per-session key; data encrypted at rest; key destroyed on session end.**
- **Phase.** 10 (HA + persistence).
- **Detection.** Template admission: `persistence != ephemeral` requires `encryption.kms_key_id` field.

### A35 — Seccomp filter too permissive (e.g. allows `ptrace`)

- **Source.** [`research/05-firecracker.md`](./05-firecracker.md) §6.
- **Failure.** Compromised agent ptraces host processes if seccomp lets it.
- **Our choice — per-thread allowlists, segmented by role; ptrace, `process_vm_readv/writev`, `kcmp` all denied unless explicitly justified.** Test fixture asserts denial.
- **Phase.** 7 (agent seccomp profile) + Phase 9 (CH seccomp).
- **Detection.** Profile diff requires ADR for any new syscall added to allowlist.

### A36 — Session affinity cache not invalidated on pod restart

- **Source.** Same as A5 but generalized — pods can restart even without delete (OOM-kill, liveness fail).
- **Failure.** Pod restarts with new IP, Valkey holds old IP, session calls timeout for `TTL` window.
- **Our choice — Informer watches pod **status**, not just lifecycle events.** Any phase change → invalidate. Validate via integration test that asserts restarted-pod scenario.
- **Phase.** 6 (L4 KV management).
- **Detection.** Integration test from A5.

### A37 — PVC for sandbox session workspace

- **Source.** [`research/22-anthropic-firecracker-microvm-internals-observed.md` §2.3](./research/22-anthropic-firecracker-microvm-internals-observed.md#23-rootfs-as-cow-snapshot--the-pvc-replacement-pattern-). Observation: Anthropic's production Firecracker microVM serves `/home/claude` from a per-VM CoW snapshot (qcow2 backing / dm-thin / ZFS clone) of a golden rootfs — **not** from a per-session PVC.
- **Failure.**
  - **Cross-tenant leak (security).** A reused PVC that isn't scrubbed exactly right between sessions = previous tenant's data to the next one. The scrub step is operationally fragile; CoW snapshots eliminate the failure mode by design (delta is discarded, golden image is the only shared state and it is read-only).
  - **Reset isn't free.** Wiping a 10 GiB PVC before a session lease takes seconds-to-minutes; discarding a qcow2 delta is constant-time.
  - **Claim controller drag.** Per-session PVC create/delete melts the apiserver at high session churn ([A2](#a2--service-per-pod--service-per-session)-class failure). CoW snapshots are a storage-layer concern, no k8s object on the create path.
  - **No multi-region story.** PVCs are AZ-pinned (RWO). The CoW-rootfs + S3-FUSE pattern is location-agnostic: the next VM can spawn in a different region and re-bind to the same `filesystem_id` prefix.
  - **Wrong primitive shape.** "Continue yesterday's session" is a **Tier 4** concern (the user's *data*), not a Tier 3 concern (the agent's *runtime fs*). The PVC tries to solve the wrong problem.
- **Our choice — Tier 3 is always ephemeral; CoW snapshot is the implementation.**
  - **No PVC for the session workspace tier in any template.** Helm admission rejects `persistence != ephemeral` on Tier 3.
  - **Phase 9 (Kata / FC):** Tier 3 = CoW snapshot of golden rootfs via `qcow2` backing files / `dm-thin` snapshots / ZFS `clone`.
  - **Phase 5 (sysbox / runc):** Tier 3 = tmpfs or overlayfs over the image layer.
  - **Persistence for the user, when needed,** is served by Tier 4 (S3 + FUSE) with `filesystem_id` session-token auth — the next VM re-binds to the same prefix.
  - PVC remains the right primitive for **classical platform workloads** (PostgreSQL, Redis, Prometheus, etcd) — none of which our sandbox runtime hosts. This antipattern is scoped to the sandbox session workspace tier specifically.
- **Phase.** 3 (storage MVP) — admission rule lands here. 9 (Kata templates) — CoW backend wires in.
- **Detection.**
  - Grep every Helm template / `SandboxTemplate` for `kind: PersistentVolumeClaim` inside a sandbox spec — should not exist outside platform-services charts.
  - Admission webhook: `SandboxTemplate.mounts[type=workspace].persistence` must be `ephemeral`; any other value rejected with a link to this entry.
  - Integration test: spawn → write file → terminate → spawn fresh → assert file absent (clean reset). No scrub step in the provisioning path.

---

## Section C — Antipatterns specific to OUR stack (not in sandboxd)

These came up while filtering and don't appear in the canonical sandboxd list because they're consequences of our connect-go / Kata / multi-replica choices.

### C1 — Not using vsock when available

- **Failure.** TCP-only L1 transport works on runc/sysbox but loses the IP-exhaustion + zero-network-stack-overhead benefits of vsock on Kata. Also blocks "single binary across all runtimes" claim.
- **Our choice — vsock primary, TCP fallback. Runtime auto-detect.**
  - Agent boot: `if /dev/vsock exists → bind AF_VSOCK; else TCP 0.0.0.0:port`.
  - Same binary across all runtimes (sandboxd §3).
- **Phase.** 7.
- **Detection.** Agent integration test on both transports.

### C2 — Kata pods scheduled to control-plane node pool

- **Failure.** Kata needs bare-metal + KVM. Putting Kata pods on cloud-managed VM nodes either fails (no KVM) or silently falls back to runc (no isolation).
- **Our choice — dedicated bare-metal node pool with taints + `nodeSelector`.**
  - Pool taint: `runtime=kata:NoSchedule`.
  - Kata templates carry matching toleration + `nodeSelector: runtime=kata`.
  - Control plane / Valkey / egress proxy stay on regular nodes.
- **Phase.** 9.
- **Detection.** Helm chart pre-install validates that a node pool with the right label/taint exists. Admission rejects kata templates if no matching node found.

### C3 — Bidi gRPC streaming for everything

- **Failure.** Bidi streaming is the most complex shape; using it where unary or server-stream would do bloats client code, complicates retries, and obscures observability.
- **Our choice — 4 RPC shapes by semantic.**
  - **Unary** — `Configure`, `Health`, `Stop`.
  - **Server-stream** — `Exec` (output), `Events` (lifecycle).
  - **Client-stream** — `Upload`.
  - **Bidi** — only `CDP` and `Screencast` (genuinely bidirectional).
- **Phase.** 6 (.proto authoring) + Phase 7 (agent service).
- **Detection.** `.proto` review: bidi without justification = blocked.

### C4 — Long-lived subscribe stream agent → orchestrator

- **Failure.** Agent holds a long-lived stream from L3 → L3 reconnects on every L3 pod restart → cascading reconnect storms when L3 rolls.
- **Our choice — push model: L3 → agent.**
  - L3 calls `Agent.Exec` / `Agent.Configure` per request.
  - Lifecycle events flow agent → L3 only on demand (`Events` stream pulled by L3 watcher).
  - No agent-initiated persistent connection to L3.
- **Phase.** 7.
- **Detection.** Agent code review: no `connect.NewClient(...).LifecycleEvents(ctx)` loop running at boot.

### C5 — Single-replica L4 control plane

- **Failure.** L4 dies → entire fleet undeployable; rolling deploy needs downtime; HA impossible.
- **Our choice — min 3 replicas + k8s `Lease`-based leader election.**
  - Leader handles lifecycle reconcile (pool refill, GC).
  - Followers serve user-facing MCP / REST / WS.
  - Leader election via `coordination.k8s.io/Lease`.
- **Phase.** 6 (Go control plane HA from day one) — non-negotiable.
- **Detection.** Helm chart default `replicas: 3`; lower triggers warning. Integration test kills leader, verifies failover < 10 s.

### C6 — Lifecycle reconcile decisions made by every replica

- **Failure.** Every L4 replica tries to spawn pool members → races, duplicate pods, quota exhaustion.
- **Our choice — leader-only reconcile.**
  - Pool refill, GC, secret rotation, audit-log compaction = leader-only.
  - User request handling = any replica.
- **Phase.** 6.
- **Detection.** Code review: any controller-loop code path must guard on `if !leader { return }`.

### C7 — One runtime baked into config

- **Failure.** Wedged to kata-clh forever; can't add kata-fc for fast cold start or sysbox for internal trusted tier without re-arch.
- **Our choice — `RuntimeClass` is template-level config, never baked.**
  - Already covered by [A28](#a28--runtimeclass-baked-globally-no-per-template-override) but worth restating: this is the "default" we lock in Phase 9, not the only option.
- **Phase.** 9 onwards.
- **Detection.** Same as A28.

### C8 — Connect-go service without buf-lint in CI

- **Failure.** `.proto` files drift unchecked, breaking changes ship to production, clients break in mysterious ways.
- **Our choice — `buf lint` + `buf breaking` in CI from Phase 6 onward.**
  - `buf lint` blocks malformed `.proto`.
  - `buf breaking` blocks wire-incompatible changes against the previously-released branch.
- **Phase.** 6.
- **Detection.** CI job presence; PR check status.

### C9 — Translating MCP into multiple internal RPC shapes

- **Failure.** L4 has 3 different ways to translate `tools/call` → fan-out to L3 → debugging nightmare, MCP semantics partially leak into L3.
- **Our choice — single `ToolCall` RPC in `Agent` service; L4 gateway is a thin translator.**
  - MCP `tools/call` → exactly one `Agent.ToolCall(name, args)` server-stream.
  - L3 just forwards; no MCP awareness in L3 or L1.
- **Phase.** 6 + 7.
- **Detection.** Grep L1/L3 code for `mcp`, `tools/call`, `jsonrpc`: should not appear.

### C10 — Treating connect-go HTTP/JSON fallback as production transport

- **Failure.** Operators (or us) use the `curl` debug path against the production endpoint at scale → slow, unbatched, no streaming → look like real production traffic patterns and skew metrics.
- **Our choice — HTTP/JSON is debug-only.** Production clients use gRPC or Connect framing.
- **Phase.** 6.
- **Detection.** Metrics segment by transport; alert if HTTP/JSON volume > 5% of gRPC volume.

---

## Phase index

Quick lookup: when planning Phase N, scan these entries.

| Phase | Antipatterns to guard against |
|---|---|
| 0.5 (docs polish) | A18 (don't build yet another platform — record decisions, don't reimplement) |
| 1 (provider interface) | A10, A11 (start image hygiene + reproducibility) |
| 2 (HTTP pool sidecar) | A12 (warm pool bounds), A13 (idle timeout skeleton) |
| 3 (S3 + squashfs) | A9 (ephemeral by default), A10 (no secrets in image), A34 (encryption if persistence), **A37 (no PVC for sandbox session workspace)** |
| 4 (secret broker) | A8 (per-session JWT), A33 (signing key rotation) |
| 5 (Helm + K8sProvider) | A2 (no per-session Service), A3 (overprovisioning), A5/A36 (pod IP cache + watch), A11 (cosign verify), A12 (warm pool real), A15 (graceful shutdown), A16 (`restartPolicy: Never`), A17 (cattle/pets), A29 (smoke tests), A30 (kernel version validation), **A37 (no PVC for sandbox session workspace — admission rule)** |
| 6 (Go control plane) | A4 (no ClientIP affinity), A5/A36 (informer-driven cache), A8 (mint JWT), A14 (audit metadata only), A26 (no env values in logs), C5 (3 replicas), C6 (leader-only reconcile), C8 (buf-lint), C9 (single ToolCall), C10 (HTTP/JSON debug-only) |
| 7 (Rust guest agent) | A1 (defense in depth, all 4 layers), A6 (Configure-before-Chrome), A7 (no auth in agent), A15 (cooperative Shutdown RPC), A27 (versioned agent), A35 (tight seccomp), C1 (vsock auto-detect), C3 (4 RPC shapes), C4 (push model) |
| 8 (egress proxy + audit) | A8 (token lifetime), A14/A25/A26 (log discipline), A24 (DNS rebinding), A31 (wildcard rejection), A32 (CONNECT timeouts), A33 (key rotation overlap) |
| 9 (Kata + CH) | A20 (`cache=never`), A21 (seccomp ON), A23 (Landlock pre-declare), A28 (template-level RuntimeClass), **A37 (CoW snapshot backend for Tier 3, not PVC)**, C2 (dedicated node pool), C7 (don't bake runtime) |
| 10 (snapshot/HA) | A19 (measure first), A22 (no GPU on snapshottable), A34 (KMS per session), and the sandboxd post-restore hardening triad (CRNG reseed, `init_on_free=1`, `CAP_SYS_RESOURCE` drop) |

---

## How to use this doc

1. **At start of every phase.** Read the phase row in the index above. Each entry is a PR-review checkpoint.
2. **At PR review.** If your PR could trip any listed antipattern → reference it in the PR description with how you avoided it.
3. **When you find a NEW one.** Add an entry here in the same shape (source, failure, our choice, phase, detection). Don't squirrel away in `research/NN-*.md` skip-notes — those exist for context; this doc is the operational truth.
4. **When excluding one.** Add to Section A with a one-line reason. Future contributors deserve to see why generic advice doesn't apply.
