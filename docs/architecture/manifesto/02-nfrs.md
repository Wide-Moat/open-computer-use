<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: draft
last-reviewed: 2026-05-27
owner: "@Wide-Moat/architects"
applies-to: next/v1
---

Names the measurable non-functional requirements every Wide-Moat release must satisfy. Audience is anyone proposing a component spec, ADR, or CI gate that affects buyer-facing surface area.

Categories follow ISO/IEC 25010:2023 plus two inserted sections (Compliance, Cost) that have no native ISO mapping.

## Trust boundaries

Five zones interact: Control plane, Credential broker, Compute plane, Egress trust-edge, Audit pipeline. The trust-zone diagram is canonical in [`../02-trust-boundaries.md`](../02-trust-boundaries.md) §5 (source: [`../diagrams/02-trust-boundaries.mmd`](../diagrams/02-trust-boundaries.mmd)). Every NFR below sits on one of those zones.

Three identity primitives carry the inter-zone calls: a session JWT bound to `container_name` (Control plane → Compute plane, TTL ≤ 4 h), a scoped JWT via the Credential broker bound to the resource (TTL ≤ 15 min), and a network-bound egress identity (Compute plane → Egress trust-edge: the fact that traffic arrived from the sandbox at all is the identity). Component skeletons land under [`../components/`](../components/) when each component spec opens (see [PROCESS.md](../PROCESS.md)).

### Token TTL taxonomy

Three short-lived token classes carry three different lifetimes by design:

| Class | Scope | TTL | Where |
|---|---|---|---|
| Egress JWT | per session (user sees one continuous interaction) | ≤4 h | NFR-SEC-10 |
| Generic internal token | inter-component RPC | ≤60 min | NFR-SEC-23 |
| Broker scoped-JWT | per-resource (one filesystem / one upstream API key class) | ≤15 min | NFR-SEC-29 |

Tighter scope = shorter TTL. The three numbers are independent commitments, not contradictions.

## Scope ownership

Every NFR row sits in one of three ownership classes. Layer 3 (`docs/architecture/02-trust-boundaries.md`) draws the boundary; this section names what we deliver vs. what we make possible.

- **DELIVER** — we ship the code, we are accountable for the measurable target. Failure = our defect. Example: sandbox escape (NFR-SEC-02), egress proxy (NFR-SEC-05), credential broker (NFR-SEC-23/29), audit pipeline (NFR-SEC-03 reframed for tx-log submission), RTO/RPO of our planes (NFR-REL-01/02/03), encryption defaults (NFR-SEC-33).
- **ENABLE** — we publish the contract, the telemetry, or the integration point; the customer is the principal and owns the policy/content. Failure of the surrounding posture = customer's gap, not ours. Example: DORA major-incident timeline (NFR-COMP-04 — we emit telemetry, customer classifies); NYDFS § 500.17 notification (NFR-COMP-05); IdP posture (NFR-FLEX-03 — we are the relying party).
- **REVISIT** — flagged for re-scoping in the next §02 revision. Either claims more than our scope or names a responsibility that belongs to the customer's AI gateway / data-controller / regulator-facing process. Current list (to be re-cut, not re-justified):
  - NFR-FS-03 — "LLM-request byte-identical round-trip for cached request shapes": we do not proxy LLM requests, we route them through the Egress trust-edge; no request cache lives in our platform.
  - NFR-REL-04 — "LLM upstream failover ≤5 min unhealthy → secondary": failover between LLM endpoints is the customer's AI gateway, not ours.
  - NFR-SEC-21 — "EU AI Act Art. 15(5) candidate test suite … data poisoning, model poisoning, adversarial examples, confidentiality attacks": these are model-level threats. We are not the model.
  - NFR-COMP-09 — "Post-market monitoring data flow (EU AI Act Art. 72)": Art. 72 is the deployer's monitoring obligation. We ENABLE (telemetry hooks), we don't OWN.
  - NFR-COMP-10 — "DPIA / FRIA refresh": data controller does the DPIA. We supply sub-processor + data-flow inputs, we don't refresh the assessment.
  - NFR-COMP-14 — "EU AI Act Art. 15 accuracy declaration": accuracy of the AI system. The customer's model, not ours.
  - NFR-COMP-18 — "ISO/IEC 42001:2023 AI Management System conformance": 42001 binds the organisation deploying the AI system. We ENABLE the customer's 42001 evidence; we are not conformance-ed.
  - NFR-COMP-25 — "ZDR contractual-clause checklist per supported managed LLM upstream": the customer contracts ZDR with the upstream. We surface upstream ZDR posture in docs (NFR-FLEX-01) but don't represent it.
  - NFR-COMP-26 — "Configurable prompt-redaction filter": AI-guardrail policy belongs to the customer's AI gateway (commercial AI-gateway product or in-perimeter model with its own guardrails). We route + audit, we don't redact prompts.

REVISIT rows stay in this catalogue at their existing IDs until the next §02 rev; Layer 3 already takes the corrected position. **Enforcement status:** REVISIT rows are **informational / non-gating** in this draft. CI gates, release acceptance, compliance attestations, and verifier passes MUST NOT enforce a REVISIT row's Target column until the row is re-cut. The row's Scenario cell carries an inline `**[REVISIT — non-gating]**` marker so the gate-author cannot miss it.

## Sandbox tier — workload-driven selection

The sandbox runtime ladder is chosen by the trust profile of the workload running inside the sandbox, not by data classification or compliance tier.

| Workload profile (`workload_trust_profile`) | Recommended tier | Rationale |
|---|---|---|
| `trusted_operator` — solo developer, single operator; you are the only one driving the agent | `runc` (default; one-click solo install preserved) | Shared kernel; trade isolation for speed. Acceptable when you are the workload. |
| `internal_workforce` — vetted employees and partners driving the agent; you know who they are, you trust their intent | `gVisor` (`runsc`) — v1 hardened default | User-space-kernel isolation; two-bug escape requirement per gVisor's published threat model. |
| `untrusted` — unknown actors (external customers, public endpoints, untrusted skill execution) | **microVM (hardware-virt)** — post-v1, tracked at [`arch/microvm-tier-v1.1`](https://github.com/Wide-Moat/open-computer-use/issues/161) | Hardware-virtualisation is the defensible isolation primitive against unknown-actor adversarial code. Named example: Firecracker. Kata Containers is one packaging option, not a requirement. |

The `untrusted` profile is not deployable in v1 GA; admission rejects it because the microVM tier has not shipped. KVM presence is a microVM precondition. Per-session trust profiles are tracked for v1.1+ at [`arch/per-session-trust-profile`](https://github.com/Wide-Moat/open-computer-use/issues/162); v1 GA carries a single deployment-wide profile.

## 1. Functional Suitability

Scope: determinism, replay, and reproducibility properties of the agent loop. Functional behaviour of individual components lives in the respective component specs.

| ID | Scenario | Target | Verification | Source |
|---|---|---|---|---|
| NFR-FS-01 | Per-template agent wall-clock policy — real / frozen / replayable; CRNG reseed on snapstart restore | declared per template | template field + replay test | [`gaps.md`](../../future-architecture/gaps.md) D.2 |
| NFR-FS-02 | Skill randomness honours session-fixed seed when `determinism.fixed_seed: true` | `tbd` (`arch/deterministic-skill-seed`) | per-template test | [`gaps.md`](../../future-architecture/gaps.md) D.3 |
| NFR-FS-03 | **[REVISIT — non-gating]** LLM-request byte-identical round-trip for cached request shapes (proxy semantics, not provider semantics) | CI integration test asserts | release pipeline | [`02-layer4-control-plane.md`](../../future-architecture/architecture/02-layer4-control-plane.md) §LLM proxy |

## 2. Performance Efficiency

| ID | Scenario | Target | Verification | Source |
|---|---|---|---|---|
| NFR-PERF-01 | MCP request success rate | ≥99.9% | Prometheus blackbox | [`10-observability.md`](../../future-architecture/architecture/10-observability.md) §SLO |
| NFR-PERF-02 | Session-create p99, warm-pool hit | ≤500 ms | k6 perf gate | [`10-observability.md`](../../future-architecture/architecture/10-observability.md) §SLO |
| NFR-PERF-03 | Session-create p99, cold-start on the hardened tier (gVisor v1; microVM post-v1) | ≤2 s | k6 perf gate | per-tier baselines in NFR-PERF-07/08/09 |
| NFR-PERF-04 | Exec orchestration overhead p99 | ≤50 ms | k6 perf gate | [`10-observability.md`](../../future-architecture/architecture/10-observability.md) §SLO |
| NFR-PERF-05 | CDP frame rate | ≥10 fps | Playwright golden-path | [`10-observability.md`](../../future-architecture/architecture/10-observability.md) §SLO |
| NFR-PERF-06 | Egress-proxy latency p99 | ≤100 ms | k6 perf gate | [`10-observability.md`](../../future-architecture/architecture/10-observability.md) §SLO |
| NFR-PERF-07 | Cold-start container-substrate p99 (dev / PoC only — not GA acceptance path) | ≤200 ms | k6 perf gate | dev-tier baseline |
| NFR-PERF-08 | Cold-start user-space-kernel substrate p99 | ≤400 ms | k6 perf gate | published user-space-kernel benchmarks |
| NFR-PERF-09 | Cold-start microVM substrate p99 | ≤1500 ms baseline; pilot data may tighten to ≤800 ms. Gated on microVM tier shipping ([`arch/microvm-tier-v1.1`](https://github.com/Wide-Moat/open-computer-use/issues/161)); not enforced in v1 | k6 perf gate | Firecracker-Lambda public baseline |
| NFR-PERF-10 | Audit-pipeline backpressure | ≥10× peak; zero chain breaks; no silent drop | chaos test | RFC-9162 + EU AI Act Art. 12 |
| NFR-PERF-11 | Egress trust-edge throughput ceiling | `tbd` (`arch/egress-throughput-ceiling`) | — | open |
| NFR-PERF-12 | Concurrent sandbox count per node per tier | `tbd` (`arch/sandbox-density-per-node`) | — | open |
| NFR-PERF-13 | Perf regression vs last-green baseline | >10% fails CI | k6 smoke per PR | `CLAUDE.md` CI gates |

## 3. Interaction Capability

| ID | Scenario | Target | Verification | Source |
|---|---|---|---|---|
| NFR-IC-01 | Human-oversight notification latency | p99 ≤1 s | synthetic test | EU AI Act Art. 14 |
| NFR-IC-02 | Every operator action via CLI + declarative config — no admin UI in v1 | feature parity per release | CI golden-path | `CLAUDE.md` v1 non-goals |
| NFR-IC-03 | PTY + CDP streaming through single WebSocket per session | stable versioned API; one socket per session | integration test | [`02-layer4-control-plane.md`](../../future-architecture/architecture/02-layer4-control-plane.md) §streaming |
| NFR-IC-04 | Control-plane RPC surface (session create/destroy/exec/fs) versioned | breaking change requires major version + deprecation header | API-version audit | [`02-layer4-control-plane.md`](../../future-architecture/architecture/02-layer4-control-plane.md) §RPC |
| NFR-IC-05 | Concurrent tool-call contract — sequential default; explicit parallelism opt-in per skill | contract published per release | API contract test | [`gaps.md`](../../future-architecture/gaps.md) K.4 |

## 4. Reliability

| ID | Scenario | Target | Verification | Source |
|---|---|---|---|---|
| NFR-REL-01 | Control-plane RTO / RPO | ≤60 min / ≤5 min | quarterly DR exercise | DORA Art. 11/12 + tier-1 baseline |
| NFR-REL-02 | Data-plane RTO | ≤30 min new sessions (in-flight non-durable) | quarterly DR exercise | DORA Art. 12 |
| NFR-REL-03 | Audit-pipeline RTO / RPO | ≤15 min / 0 (no event loss) | chaos test | RFC-9162 + DORA Art. 19 |
| NFR-REL-04 | **[REVISIT — non-gating]** LLM upstream failover | ≤5 min unhealthy → secondary | chaos test | DORA Art. 29 |
| NFR-REL-05 | Single-AZ failure | continuity across remaining AZs, no operator action | quarterly chaos | DORA Art. 12 |
| NFR-REL-06 | Regional failure | RTO ≤4 h secondary region (CIF tier) | annual DR exercise | DORA Art. 12 + CPMI-IOSCO baseline |
| NFR-REL-07 | Routine upgrade — zero customer-visible downtime | per release | release notes | FFIEC BCM |
| NFR-REL-08 | Stateful sandbox hibernation + resume + snapshot + fork | demonstrated end-to-end | integration test | [`gaps.md`](../../future-architecture/gaps.md) J |
| NFR-REL-09 | Idle reaper + graceful cleanup reconcile loop | zero orphan processes per release | release acceptance | [`antipatterns.md`](../../future-architecture/antipatterns.md) A15 |
| NFR-REL-10 | Backup-isolation | physically AND logically segregated from source | architectural review | DORA Art. 12(3) verbatim |
| NFR-REL-11 | Cooperative shutdown | `terminationGracePeriodSeconds=30`; SIGTERM→5s→SIGKILL; tmpdir clean ≤10 s | integration test | [`antipatterns.md`](../../future-architecture/antipatterns.md) A15 |
| NFR-REL-12 | Audit producers write only via durable bus; no synchronous DB writes on critical path | bus on path for every event | chaos test | [`10-observability.md`](../../future-architecture/architecture/10-observability.md) §pipeline |

## 5. Security

| ID | Scenario | Threats | Target | Verification | Source |
|---|---|---|---|---|---|
| NFR-SEC-01 | Kill switch — one session or all globally | DoS, runaway-agent | ≤30 s p99 wall-clock; SOAR webhook + admin API + CLI | chaos test | primitives-backlog |
| NFR-SEC-02 | Sandbox escape | EoP, Tampering | Tier-appropriate sandbox-escape resistance: gVisor user-space kernel as v1 hardened default; microVM hardware-virt post-v1 ([`arch/microvm-tier-v1.1`](https://github.com/Wide-Moat/open-computer-use/issues/161)). Every tier carries seccomp BPF + Landlock + cap-drop ALL with minimum add-back + read-only rootfs. Zero red-team pass per release per tier shipped | red-team suite | EU AI Act Art. 15(5) |
| NFR-SEC-03 | Audit-log tamper | Tampering, Repudiation | hash-chained append-only audit log; daily Merkle head over the chain submitted to a transparency log within 24 h. Submission envelope signed with a host-local key on the solo / dev tier; the same envelope signed with an HSM-rooted key (PKCS#11 / KMIP) when customer KMS is wired per NFR-FLEX-04. The transparency-log operator signs the Merkle head — we sign only the envelope | daily transparency-log probe; HSM-signature check when customer KMS is wired | RFC-9162 + EU AI Act Art. 12 |
| NFR-SEC-04 | Credential / key rotation | Information Disclosure | tenant DEK ≤90 d; KEK ≤365 d; revocation ≤5 min platform-wide | rotation audit | PCI-DSS 4.0 Req 3.7 |
| NFR-SEC-05 | MITM-friendly egress | Information Disclosure, exfil | single forward proxy; customer-CA injected into sandbox trust store; WebSocket support; ext_authz hook; strict upstream TLS validation + fail-closed | integration test | primitives-backlog |
| NFR-SEC-06 | Replay-bundle completeness | Repudiation, forensics | ≥99% session events reconstructable; 100% sessions bundled | replay-eval suite | EU AI Act Art. 12 |
| NFR-SEC-07 | Supply-chain | Tampering, supply-chain | CycloneDX SBOM + SPDX + SLSA L3 + cosign per release; VEX per known CVE | CI gate | NIST 800-218A |
| NFR-SEC-08 | MCP allow-list enforcement | Information Disclosure, lateral | Egress trust-edge enforces customer allow-list; deny-by-default; auditable denials | SIEM-side check | primitives-backlog |
| NFR-SEC-09 | Identity binding to every action | Spoofing, Repudiation | SPIFFE SVID on every inter-component call; human action requires SAML/OIDC + SCIM; no anonymous paths in production | code-path audit + SOC 2 CC6.x | NYDFS Part 500 |
| NFR-SEC-10 | Per-session egress JWT | Replay, token-theft | `exp ≤ session-max (4 h)`; refresh issues new token, never extends | token-lifetime test | [`antipatterns.md`](../../future-architecture/antipatterns.md) A8 |
| NFR-SEC-11 | Egress JWT signing-key rotation | Tampering | Ed25519, ≤90 d, `kid` header, 24 h overlap | rotation log | [`antipatterns.md`](../../future-architecture/antipatterns.md) A33 |
| NFR-SEC-12 | DNS-rebinding defence at proxy | SSRF | proxy-owned resolver; fixed mandatory deny-set RFC1918 + RFC4193 (fc00::/7) + RFC4291 link-local (fe80::/10) + `169.254.169.254` + `[fd00:ec2::254]`; filter at connect time on resolved IP + SNI, never DNS resolution | unit test per rejection class | [`antipatterns.md`](../../future-architecture/antipatterns.md) A24 |
| NFR-SEC-13 | Per-session KMS-backed key destroyed on session end | PVC-reuse cross-tenant | KMS key per session; destroyed on session end | audit destroy-events | [`antipatterns.md`](../../future-architecture/antipatterns.md) A34 |
| NFR-SEC-14 | Sandbox hardening — `no-new-privileges:true` + cap-drop ALL with minimal add-back + seccomp BPF + read-only rootfs + tmpfs + user-namespace mapping (host UID 0 ≠ container UID 0) + pids/cpu/mem cgroup limits + `docker.sock` not mounted | EoP | invariant per container | admission gate | [`07-security.md`](../../future-architecture/architecture/07-security.md) §container hardening |
| NFR-SEC-15 | User-data volume-only; image carries no PII | Information Disclosure | `/home/assistant/` volume <1 MB enforced in CI | CI gate | `tests/test-docker-image.sh` |
| NFR-SEC-16 | Installer and runtime never call Wide-Moat-controlled endpoints without explicit customer opt-in; outbound traffic permitted only to endpoints the customer configured (LLM upstream API, customer SIEM, customer S3, customer DNS, customer registry — up to 5 named categories per deployment, documented in release notes); telemetry / error reporting / update checks default off | Information Disclosure | zero Wide-Moat-controlled outbound in default config; opt-in feature flags surface telemetry; release notes enumerate customer-configured endpoint categories | CI artifact inspection (installer + runtime images) | primitives-backlog |
| NFR-SEC-17 | Egress posture (sandbox trust tier) | Information Disclosure, exfil | default-deny + allowlist-on-connect (resolved IP + SNI) + `x-deny-reason` block reason | NetworkPolicy diff | [`design-notes.md`](../../future-architecture/design-notes.md) DN-1 |
| NFR-SEC-18 | Static-tagged image refs; admission rejects unsigned; reproducible-build CI gate | Supply-chain, Tampering | every image ref `@sha256:`; cosign verify at admission; "build twice → digests match" | admission + CI gate | [`antipatterns.md`](../../future-architecture/antipatterns.md) A11 |
| NFR-SEC-19 | Zero secrets in source | Information Disclosure | gitleaks + trufflehog exit 1 on any finding | `.github/workflows/security.yml` | `CLAUDE.md` top-3 CI gate |
| NFR-SEC-20 | SAST/SCA CRITICAL blocks merge; HIGH tracked ≤14 d | Tampering, Information Disclosure | CRITICAL = exit 1; HIGH exception ledger | `.github/workflows/security.yml` | `CLAUDE.md` top-3 CI gate |
| NFR-SEC-21 | **[REVISIT — non-gating]** EU AI Act Art. 15(5) candidate test suite | Tampering, Information Disclosure | pass/fail per release; four named attack classes (data poisoning, model poisoning, adversarial examples, confidentiality attacks); mitigation thresholds tracked against forthcoming EU Commission implementing act | red-team suite | EU AI Act Art. 15(5) verbatim |
| NFR-SEC-22 | Per-tenant network isolation; inter-sandbox communication disabled by default | Information Disclosure, lateral | tenant-A cannot reach tenant-B sandbox without explicit policy | NetworkPolicy + integration test | [`08-networking.md`](../../future-architecture/architecture/08-networking.md) §isolation |
| NFR-SEC-23 | Secrets externalised; runtime injection through broker (short-lived, revocable); high-value classes (LLM upstream API key, cloud-storage SigV4 origination) carry tighter TTL | Information Disclosure | zero secrets in container manifest; ≤60 min generic token lifetime; ≤15 min for high-value class; revocable ≤5 min generic, ≤1 min high-value | image scan + integration | [`04b-credential-broker.md`](../../future-architecture/architecture/04b-credential-broker.md) §TTL |
| NFR-SEC-24 | When `SkillProvider` lands (post-v1), skills execute inside the same VM boundary as guest workload; no privileged path outside the sandbox | Tampering, supply-chain | invariant carried by component spec when skill registry is in scope; not GA in v1 (see NFR-FLEX-05) | architectural review on `SkillProvider` ADR | primitives-backlog (SkillProvider TBD) |
| NFR-SEC-25 | In-guest mount initiation; no host bind-mount of secrets into guest; covers filesystem AND upstream-API-key classes | Information Disclosure | zero host-side secret bind-mounts; mount backend initiated from inside guest. Mount substrate (FUSE / virtio-fs / 9p) is a component-spec choice | runtime audit | [`06-storage.md`](../../future-architecture/architecture/06-storage.md) §mounts + [`04b-credential-broker.md`](../../future-architecture/architecture/04b-credential-broker.md) |
| NFR-SEC-26 | Internal service-to-service identity = Ed25519 JWT on WebSocket bound to `container_name` | Spoofing | works identically across all supported runtimes; transport choice (TCP / UDS / vsock) is a deployment-overlay detail, not a platform-level NFR; intra-platform TLS is enforced at the deployment overlay (k8s service-mesh, Compose internal network, microVM vsock) — see Open Question | integration test per runtime | [`02-layer4-control-plane.md`](../../future-architecture/architecture/02-layer4-control-plane.md) §auth + [`05-layer1-guest-agent.md`](../../future-architecture/architecture/05-layer1-guest-agent.md) |
| NFR-SEC-27 | Egress identity = **network-bound** — sandbox has no route out other than the MITM-proxy; no JWT on outbound HTTPS request | Spoofing | `curl` from sandbox returns 200 without client cert or token; outbound default-route = proxy | network-policy audit + integration test | [`08-networking.md`](../../future-architecture/architecture/08-networking.md) §egress |
| NFR-SEC-28 | Wide-Moat ships a default image and a FIPS-validated image variant. Default uses Apache-2.0 crypto providers and supports TLS 1.3 with ChaCha20 + Ed25519. FIPS variant uses FIPS 140-3 validated crypto modules and may carry a narrower cipher floor (e.g. TLS 1.2). Security envelope is equivalent — FIPS variant adds regulator-acceptable certification, not stronger crypto. Two-image stance rationale tracked in `arch/adr-fips-binary-tier` | (compliance) | per-release default + FIPS variants emitted; FIPS-conformance test green on FIPS variant | release-pipeline | separate-binary precedent across enterprise OSS |
| NFR-SEC-29 | Credential broker — per-VM; broker holds no master key for compliance-bearing tiers (delegated STS). Binding substrate matches the tier: loopback / UDS on the runc and gVisor tiers (inherits the user-space-kernel process boundary on the gVisor tier); vsock CID + JWT scope on the microVM tier (post-v1, [`arch/microvm-tier-v1.1`](https://github.com/Wide-Moat/open-computer-use/issues/161)) — CID is hypervisor-assigned, unforgeable by guest code | Information Disclosure, broker compromise | scoped-JWT TTL ≤15 min; revocation propagation ≤1 min; public-interface bind admission-rejected | per-tier deployment audit + broker integration test | [`04b-credential-broker.md`](../../future-architecture/architecture/04b-credential-broker.md) §topology |
| NFR-SEC-30 | Broker terminates outbound TLS with strict cert validation, fail-closed | Tampering | broker integration test on bad upstream cert | fail-closed test | [`04b-credential-broker.md`](../../future-architecture/architecture/04b-credential-broker.md) §TLS |
| NFR-SEC-31 | Per-session filesystem-prefix isolation enforced by JWT-claim scope check at broker | Information Disclosure | cross-session reads architecturally impossible, not policy-guarded | broker integration test | [`04b-credential-broker.md`](../../future-architecture/architecture/04b-credential-broker.md) §scope |
| NFR-SEC-32 | In-VM memory is NOT a secret store — `/proc/N/mem` readable by in-VM root; defence rests on scope + TTL + external boundary | Information Disclosure | no row of §02 implies in-memory secrecy without external boundary | architectural review | [`07-security.md`](../../future-architecture/architecture/07-security.md) §memory boundary |
| NFR-SEC-33 | Encryption defaults | (compliance) | TLS 1.3 in transit (TLS 1.2 disable-able); AES-256-GCM at rest; cryptographic erasure (tenant-DEK destruction) = data deletion primitive | per-release crypto conformance | [`07-security.md`](../../future-architecture/architecture/07-security.md) §encryption |
| NFR-SEC-34 | Continuous eval / red-team in CI | Tampering, Information Disclosure | 10-min red-team subset per PR; full red-team suite nightly; signed attestation per release | per-PR + nightly + per-release | `CLAUDE.md` CI ruleset |
| NFR-SEC-35 | Host kernel floor + microVM kernel cmdline hardening | EoP, kernel CVEs | Host kernel ≥5.10. KVM presence is a precondition for the microVM tier only (post-v1, [`arch/microvm-tier-v1.1`](https://github.com/Wide-Moat/open-computer-use/issues/161)); when present, microVM-tier templates boot with `init_on_free=1`, `nomodule`, `random.trust_cpu=1`, `panic=1`. KVM absence is not a deployment block; the deployment selects the highest tier the host substrate supports | Helm pre-install probe runs in ≤2 s and emits a clear error naming the missing capability when `runtime: microVM` is configured on a host without `/dev/kvm`; CI test on a KVM-absent runner asserts the probe error path; image-spec audit covers the microVM-tier kernel cmdline | [`04-layer2-runtimes.md`](../../future-architecture/architecture/04-layer2-runtimes.md) §kernel |
| NFR-SEC-36 | Guest control-plane port unreachable from guest workload code (block-local-connections equivalent on the L1 agent) | EoP, lateral | enforced at L1 listener config + iptables/nftables guest-egress rule | integration test | [`05-layer1-guest-agent.md`](../../future-architecture/architecture/05-layer1-guest-agent.md) §listener |
| NFR-SEC-37 | Inter-component traffic between Wide-Moat components is encrypted in transit | Information Disclosure, lateral | zero plaintext between named components per release. Documented exceptions (decrypted traffic exists by design and is re-encrypted on the upstream leg): (a) the Egress trust-edge inspection point when MITM-inspecting mode is active (NFR-FLEX-15) — disabled in transparent-pass-through mode; (b) the DLP-ICAP hook (NFR-COMP-28). Substrate-specific enforcement is a component-spec choice | tcpdump probe on every named inter-component pair captures zero plaintext payload bytes outside (a)/(b); CI gate fails on any plaintext byte outside the carve-out | [`07-security.md`](../../future-architecture/architecture/07-security.md) §intra-platform TLS |
| NFR-SEC-38 | Workload-trust profile declared at deployment time; admission validates the configured runtime tier against the profile. Allowed pairings: `trusted_operator` → runc / gVisor / microVM; `internal_workforce` → gVisor / microVM; `untrusted` → microVM only. Mismatch is a hard error. Picking the tier by data classification is forbidden separately by AP-13 | Spoofing, Tampering | admission-time validation against a 9-cell pairing matrix. 6 cells valid by pairing rules (3 require the post-v1 microVM tier per [#161](https://github.com/Wide-Moat/open-computer-use/issues/161)); 3 cells rejected by pairing rules. v1 GA deployable: 3 cells (`trusted_operator`×runc, `trusted_operator`×gVisor, `internal_workforce`×gVisor); v1 GA rejected: 6 cells (3 pairing-rejected + 3 microVM-not-shipped). Commitment; implementation lands with control-plane code | per-release admission test fixture | this PR |
| NFR-SEC-39 | Tier-downgrade alarm — a deployment reconfigured from gVisor or microVM to a weaker tier, OR `workload_trust_profile` downgraded with active sessions present | Tampering, Repudiation | audit event `config.trust_profile.downgraded` within ≤30 s; SIEM-bridge HIGH; SOAR webhook per NFR-COMP-27. Commitment; implementation lands with audit pipeline + SOAR integration | integration test against the audit pipeline | this PR |

## 6. Maintainability

| ID | Scenario | Target | Verification | Source |
|---|---|---|---|---|
| NFR-MAINT-01 | Security-patch SLA | ≤7 d (CVSS ≥9.0); ≤30 d (7.0-8.9); ≤90 d (4.0-6.9) | release-pipeline audit | PCI-DSS 4.0 Req 6.3.3 + banking convention |
| NFR-MAINT-02 | Upgrade rollback to N-1 | ≤30 min Control plane; ≤5 min Compute plane node | DR exercise | DORA Art. 12 |
| NFR-MAINT-03 | Configuration drift detection | declarative; ≤5 min divergence | continuous monitoring | NYDFS Part 500 § 500.5 + SOC 2 CC7.x |
| NFR-MAINT-04 | API deprecation policy | announce N versions before removal; `Deprecated:` header | code review | [`gaps.md`](../../future-architecture/gaps.md) J |
| NFR-MAINT-05 | Synthetic transactions per deploy | presence + success | release-pipeline | [`gaps.md`](../../future-architecture/gaps.md) I |
| NFR-MAINT-06 | Backward-compat L4↔L1 | N-2 floor; cross-version capability negotiation tested | matrix test | [`gaps.md`](../../future-architecture/gaps.md) J.1 |
| NFR-MAINT-07 | Schema migrations forward-only, reversible per release, executed by separate Job; no runtime-ORM schema-gen | migration plan committed | release-pipeline | [`02-layer4-control-plane.md`](../../future-architecture/architecture/02-layer4-control-plane.md) §schema |
| NFR-MAINT-08 | Reproducible GitOps deployment | declarative SOT; drift-detection ≤5 min | GitOps lint + drift probe | [`gaps.md`](../../future-architecture/gaps.md) I |
| NFR-MAINT-09 | Mutation-testing score on auth / sandbox / audit / broker packages | ≥60% per release | mutation-testing report attached to release | `CLAUDE.md` CI ruleset |
| NFR-MAINT-10 | Patch coverage on changed files | ≥80% per PR | CI gate | `CLAUDE.md` CI ruleset |
| NFR-MAINT-11 | Property-based tests on every parser / scheduler / policy engine | green per release | per-release CI gate | `CLAUDE.md` CI ruleset |
| NFR-MAINT-12 | Threat-model re-runs on DFD-bearing PRs | new HIGH without ADR mitigation = block | per-PR threat-model pass | `CLAUDE.md` CI ruleset |
| NFR-MAINT-13 | External pen-test cadence | annually (baseline); "after major release" `tbd` (`arch/pentest-cadence-major-release`) | summary in TPRM-pack | industry-baseline (banking-vendor convention) |
| NFR-MAINT-AUDIT-SCHEMA | Audit-event schema = OCSF v1.x JSON primary; transformer outputs ship as CEF + Elastic ECS + Chronicle UDM; SIEM bridges (Splunk HEC, ArcSight CEF, syslog-TLS baseline; Elastic ECS, Chronicle UDM, Kafka, S3 PutObject opt-in) green per release; mandatory fields `trace_id`, `session_id`, `actor_id`, `resource`, `action`, `outcome`; OCSF schema upgrade ≤90 d after major OCSF release; N-1 backward-compat | per-release schema-conformance | OCSF JSON CI gate + bridge integration | OCSF v1.x spec (open) |

## 7. Flexibility (Portability)

| ID | Scenario | Target | Verification | Source |
|---|---|---|---|---|
| NFR-FLEX-01 | LLM upstream-provider switch — zero application-code changes; ≥4 upstreams green per release (Anthropic API, AWS Bedrock, Azure OpenAI ZDR, GCP Vertex); zero direct-provider imports in CI scan; we surface each upstream's ZDR posture in docs, we do not represent it | matrix green | CI lint + integration test | DORA Art. 29 |
| NFR-FLEX-02 | Sandbox runtime ladder — `runc` and `gVisor` in v1, buildable from the same artefact; microVM tier (hardware-virt; named example: Firecracker; packaging via Kata Containers or direct is a component-spec ADR) post-v1 at [`arch/microvm-tier-v1.1`](https://github.com/Wide-Moat/open-computer-use/issues/161). Deployment selects the highest tier the host substrate supports | per-release artifact inventory; tier-portability test | release pipeline | [`04-layer2-runtimes.md`](../../future-architecture/architecture/04-layer2-runtimes.md) §tiers |
| NFR-FLEX-03 | Identity provider portability — SAML 2.0 + OIDC + SCIM 2.0 + SPIFFE + LDAP/AD bind-mode; ≥3 commercial IdP vendors green per release; platform always the relying-party — no in-house JWT issuer / SCIM endpoint / user table with passwords. The specific vendor test matrix lands in the IdP-integration component spec | per-release integration test | CI lint + integration | NYDFS Part 500 + [`gaps.md`](../../future-architecture/gaps.md) B |
| NFR-FLEX-04 | KMS / HSM portability — PKCS#11 + KMIP; ≥2 vendors green per release; tested against AWS KMS/CloudHSM + Azure Key Vault HSM + GCP Cloud KMS/HSM + Thales Luna + Entrust nShield; absent HSM, runtime falls back to a local KMS abstraction with documented downgrade (solo / one-click path) | HSM-conformance per release; local-fallback integration test | release pipeline | NIST 800-57 + one-click invariant |
| NFR-FLEX-05 | `SkillProvider` abstraction stable; v1 ships zero default skills bundled | abstraction stable; zero bundled skills | release artifact inventory | `CLAUDE.md` v1 non-goals |
| NFR-FLEX-06 | Same egress invariant across Docker Compose + k8s + microVM (when the microVM tier ships) | one invariant, three thin wrappers | cross-substrate test | [`design-notes.md`](../../future-architecture/design-notes.md) DN-1 |
| NFR-FLEX-07a | Air-gap installer artefact — zero outbound internet during install when air-gap mode selected | offline-install test against air-gap installer image | release pipeline | primitives-backlog (air-gap) |
| NFR-FLEX-07b | Standard installer — internet egress permitted at install time; ≤5 documented run-time egress endpoints per deployment | documented endpoint list per release; one-click solo install preserves Compose path | release pipeline + Compose smoke test | one-click invariant + [`gaps.md`](../../future-architecture/gaps.md) H |
| NFR-FLEX-08 | `HTTP_PROXY` / `HTTPS_PROXY` / `NO_PROXY` + custom CA bundle injection per component | integration test | release pipeline | [`gaps.md`](../../future-architecture/gaps.md) H |
| NFR-FLEX-09 | Substrate independence — identical sandbox image runs on ≥3 substrates; CI matrix passes on Docker Compose AND target k8s per release | matrix green | cross-substrate CI matrix | [`01-layers.md`](../../future-architecture/architecture/01-layers.md) §substrate independence |
| NFR-FLEX-10 | Decoupled Control plane vs Compute plane — orchestrator does not depend on runtime details; guest builds itself given network + credentials | architecture audit | release review | [`01-layers.md`](../../future-architecture/architecture/01-layers.md) §control vs compute |
| NFR-FLEX-11 | Image tier portability (slim → max; arbitrary OCI; flexible limits; optional GPU passthrough) | tiers buildable from same Dockerfile pipeline | release inventory | [`09-templates.md`](../../future-architecture/architecture/09-templates.md) §tiers |
| NFR-FLEX-12 | Customer-tenant Compute plane as first-class deployment shape — Control plane carries metadata only; Compute plane (compute + storage + logs) runs in customer tenant | customer-hosted Compute plane option green per release | per-release integration | primitives-backlog (customer-tenant Compute plane) |
| NFR-FLEX-13 | k8s-distro portability — Helm chart on any conformant k8s ≥1.28 without flavor glue; CI matrix tests kind + EKS + RKE2 per release | CI matrix | release pipeline | future ADR (`arch/adr-k8s-distros`) |
| NFR-FLEX-14 | MCP is the agent-side wire protocol — control-plane is MCP server to upstream LLM and MCP client to skill packs; no upstream-vendor SDK hard-coded | protocol-compliance test green | release pipeline | [`02-layer4-control-plane.md`](../../future-architecture/architecture/02-layer4-control-plane.md) §MCP gateway |
| NFR-FLEX-15 | Egress posture mode-selectable — default: transparent pass-through (no customer CA needed; one-click solo install path). Opt-in: MITM-inspecting (requires customer CA in sandbox trust store). DLP-ICAP (NFR-COMP-28) is a configuration of the MITM mode, not a third mode. Single CA-trust-store invariant applies only when MITM is active | per-mode integration test | release pipeline | [`../02-trust-boundaries.md`](../02-trust-boundaries.md) §7 + one-click invariant |

## 8. Compliance

| ID | Scenario | Target | Verification | Source |
|---|---|---|---|---|
| NFR-COMP-01 | Audit-log retention — 7 y default / 10 y configurable; WORM (S3 Object Lock Compliance or equivalent); two-tier hot (≤90 d) → cold | retention-policy audit | per-release | FCA SYSC 9 / FINRA / MAS overlay + EU AI Act Art. 19(1) floor |
| NFR-COMP-02 | DORA Register of Information — 7 fields per third-party ICT provider populated for every BoM row | BoM linter | per-release | DORA Art. 28 + RTS-2025/532 |
| NFR-COMP-03 | EU AI Act Annex III conformity checklist per release; release blocks if controls absent; Art. 12/13/14/15/17/19/49 each mapped | pass/fail | release-pipeline | EU AI Act Art. 12 + 15 + 72 + Annex III §5(b) |
| NFR-COMP-04 | DORA major-incident classification candidate emission — platform telemetry enables customer to meet timeline (classification is customer-side) | telemetry available ≤1 h post-event; bundle supports initial ≤4 h after classification (≤24 h after detection), intermediate ≤72 h, final ≤1 month | incident-drill | DORA-RTS-2025/301 Art. 5 verbatim |
| NFR-COMP-05 | NYDFS § 500.17 cybersecurity-event notification telemetry | ≤72 h notification supported; ransomware-payment ≤24 h | incident-drill | NYDFS § 500.17(a) + (c) |
| NFR-COMP-06 | NYDFS contractual-clause completeness — 8 clauses populated incl. AI-acceptable-use + training-data | template review per release | per-release | NYDFS Industry Letter 21 Oct 2025 |
| NFR-COMP-07 | Evidence-as-code bundle per release — immutable + attached; ≤7 d to TPRM intake; includes the latest available SOC 2 attestation (Type I from GA, Type II from GA+12 months), SIG Lite + Core, CAIQ v4, CSA STAR L2, ISO 27001 cert, pen-test exec summary, DORA RoI template row, CycloneDX SBOM, SLSA L3 provenance, VEX. SOC 2 and ISO 27001 evidence claims require HSM-rooted key custody (NFR-FLEX-04) and audit-pipeline mandatory delivery (NFR-MAINT-AUDIT-SCHEMA); deployments without HSM-rooted custody carry the bundle but do not carry the attestation claim | bundle present per release; field-level completeness gate | release-pipeline | primitives-backlog (evidence-as-code) |
| NFR-COMP-08 | Sub-processor disclosure — public list + 30-day change notification + machine-readable Atom/JSON changelog + DPA addendum mechanism; chain depth ≥3 | BoM audit + feed-consumption test | per-release | NYDFS Industry Letter + DORA-RTS-2025/532 |
| NFR-COMP-09 | **[REVISIT — non-gating]** Post-market monitoring data flow (EU AI Act Art. 72) — per-release plan + telemetry collectable | release notes | per-release | EU AI Act Art. 72 |
| NFR-COMP-10 | **[REVISIT — non-gating]** DPIA / FRIA refresh per major release + on substantial change | template review | per-release | GDPR Art. 35 + EU AI Act Art. 26 |
| NFR-COMP-11 | Tenant-scoped audit isolation | per-tenant query returns 0 rows for other tenants | integration test | [`gaps.md`](../../future-architecture/gaps.md) A |
| NFR-COMP-12 | GDPR Art. 17 right-to-be-forgotten — audit-log tombstoning mechanism present; completion SLA `tbd` (`arch/gdpr-rtb-sla`) | end-to-end RTB test | per-release | GDPR Art. 17 + [`gaps.md`](../../future-architecture/gaps.md) C |
| NFR-COMP-13 | Data residency — zero cross-region traffic for tagged tenant; per-region pinning explicit for compute + storage + logs | network-policy audit | per-release | [`gaps.md`](../../future-architecture/gaps.md) C |
| NFR-COMP-14 | **[REVISIT — non-gating]** EU AI Act Art. 15 accuracy declaration (qualitative) — every model deployment publishes accuracy metric + methodology | release notes | per-release | EU AI Act Art. 15(1) + 15(3) verbatim |
| NFR-COMP-15 | SR 26-2 carve-out — platform governance hooks provide customer's parallel-framework evidence for agentic AI. The SR 26-2 evidence pack is available when HSM-rooted key custody (NFR-FLEX-04) is wired and the Merkle-head submission envelope is hardware-signed per NFR-SEC-03; deployments without that custody carry the underlying telemetry but not the attestation claim | per-release evidence bundle includes logging + accountability + escalation | TPRM-pack audit | SR 26-2 verbatim |
| NFR-COMP-16 | Incorporated code permissive-licensed only (Apache / MIT / BSD / MPL); AGPL/SSPL/BUSL not in bundled artefacts; AGPL components (Loki/Tempo/Grafana) only as separate services, never linked | dep-graph audit | license scanner | future ADR (`arch/adr-licence-allowlist`) |
| NFR-COMP-17 | Per-component `compliance:` front-matter — declares SOC 2 / ISO / DORA controls satisfied; `controls-matrix.md` auto-generated | YAML field populated; CI fails on stale matrix | CI gate | `CLAUDE.md` doc-discipline |
| NFR-COMP-18 | **[REVISIT — non-gating]** ISO/IEC 42001:2023 AI Management System conformance | scope statement + cert in evidence bundle | per-release | ISO/IEC 42001:2023 |
| NFR-COMP-19 | Public Vulnerability Disclosure Program landing page (`security.txt` + PGP-signed contact) AND bug bounty | VDP page live + bounty live before GA | per-release | industry-baseline (TPRM checklist) |
| NFR-COMP-20 | Per-component status page — minimum 4 named components (Control plane, Compute plane runtime, Egress trust-edge, Audit pipeline) with independent uptime ≥90 d + Atom/RSS subscription + email/webhook channels minimum | live per component | per-release | industry-baseline (Atlassian Statuspage convention) |
| NFR-COMP-21 | DORA Art. 30 right-to-audit — audit-rights template clause + 12-month exit-assistance runbook | per release | template + runbook present | DORA Art. 30 |
| NFR-COMP-22 | EU Cyber Resilience Act 2024/2847 baseline — SBOM mandate + 24 h vulnerability disclosure workflow; obligations active from 11 Dec 2027; pilot evidence collected per release from 2026-12 onward | signed SBOM + workflow integration-tested | per-release | EU CRA Reg 2024/2847 |
| NFR-COMP-23 | TLPT participation supported for TIBER-scope customers (artefacts + access mode); cadence customer-led, not platform-mandated | TLPT-access mode documented | per-release | DORA Art. 26-27 |
| NFR-COMP-24 | NIS2 Art. 23 incident-reporting cascade — 24 h early-warning + 72 h notification telemetry hook | incident-drill | per-release | NIS2 Directive Art. 23 |
| NFR-COMP-25 | **[REVISIT — non-gating]** ZDR contractual-clause checklist per supported managed LLM upstream | presence-gate per release | CI gate | per-upstream ZDR docs (cited at release) |
| NFR-COMP-26 | **[REVISIT — non-gating]** Configurable prompt-redaction filter before any external LLM call; per-tenant policy; redaction events audited | release pipeline | integration test | NYDFS Industry Letter (training-data clause) |
| NFR-COMP-27 | SOAR bidirectional — signed webhook OUT (event payloads `session.flagged`, `policy.violation`, `dlp.hit`, `auth.anomaly`); admin API IN (quarantine session / revoke token) | versioned + integration-tested per release | release pipeline | NIST 800-61 + industry SOAR convention |
| NFR-COMP-28 | DLP at egress — ICAP hook + outbound classifier (rule-based or LLM-based) + block-or-redact policy per tenant; HTTP-classifier for outbound prompt-leak detection | per-release pass/fail | integration test | primitives-backlog (egress DLP) |
| NFR-COMP-29 | PAM — just-in-time admin elevation via SAML-asserted attributes; integration with the customer's PAM tool; no shared service accounts in production | per-release audit | integration test | NIST 800-53 AC-2(7) |
| NFR-COMP-30 | FSL-1.1 procurement-redline pack ships per release — DPA template + SCCs + FSL-1.1 commentary explaining 2-year Apache-2.0 conversion mechanic + competing-SaaS clause | pack in evidence bundle | per-release | tracked: `arch/fsl-redline-pack` |

## 9. Cost

| ID | Scenario | Target | Verification | Source |
|---|---|---|---|---|
| NFR-COST-01 | Cost per concurrent session at p50 load | `tbd` (`arch/cost-per-session-baseline`) | pilot telemetry | open (no peer baseline) |
| NFR-COST-02 | LLM-upstream overhead cap | ≤10% over raw upstream call (`tbd` finalisation `arch/llm-upstream-overhead-cap`) | internal economics | industry shape |
| NFR-COST-03 | Audit-pipeline cost at scale | `tbd` (`arch/audit-cost-per-tb-year`) | internal economics | open (no peer baseline) |
| NFR-COST-04 | Control-plane fixed cost (no traffic) | `tbd` (`arch/control-plane-idle-cost`) | pilot telemetry | open (no peer baseline) |
| NFR-COST-05 | Per-session billing primitives emitted | CPU-min, RAM-GB-min, storage-GB-day, egress bytes, MCP-call count | metric-schema audit | [`gaps.md`](../../future-architecture/gaps.md) E |
| NFR-COST-06 | Per-tenant aggregate quotas — concurrent sessions, MCP calls/min, storage GB, egress bytes/day | quota integration test | release pipeline | [`gaps.md`](../../future-architecture/gaps.md) A |
| NFR-COST-07 | Cleanup retention defaults (Tier 3, not audit) — container-max-age 24 h; volume-max-age 7 d; data-max-age 7 d | configuration audit | per-release | `cron/cleanup.sh` |
| NFR-COST-08 | Real-time tenant-aggregate cost emission + period rollup at hour / day / month | metric-schema audit | per-release | [`gaps.md`](../../future-architecture/gaps.md) E.2 |

## Anti-pattern rows (forbidden by named NFRs above)

Each anti-pattern is forbidden by ≥1 row above.

- AP-1 — trusting in-VM memory as a secret store (`/proc/N/mem` readable by in-VM root). Forbidden by NFR-SEC-23, NFR-SEC-29, NFR-SEC-32.
- AP-2 — exposing `docker.sock` to guests. Forbidden by NFR-SEC-14.
- AP-3 — allow-list by hostname only, not by resolved IP + SNI at connect time. Forbidden by NFR-SEC-12, NFR-SEC-17.
- AP-4 — symmetric HS256 signing key without rotation, no `kid`. Forbidden by NFR-SEC-11.
- AP-5 — JWT accepted without verification in production. Forbidden by NFR-SEC-09.
- AP-6 — PVC for sandbox session workspace. Forbidden by NFR-SEC-31 (filesystem-prefix isolation makes cross-session reuse architecturally impossible) + NFR-SEC-13 (per-session KMS key destroyed on session end); cleanup defaults in NFR-COST-07 supporting.
- AP-7 — `--seccomp false` / `--seccomp log` in production. Forbidden by NFR-SEC-02, NFR-SEC-14.
- AP-8 — VNC for AI-action loops. Forbidden by NFR-IC-03 + NFR-PERF-05 (CDP screencast).
- AP-9 — weakened-isolation flags in production. Forbidden by NFR-SEC-02, NFR-SEC-05.
- AP-10 — service-per-session in k8s. Forbidden by NFR-PERF-12.
- AP-11 — single global agent binary without per-template version pinning. Forbidden by NFR-MAINT-06.
- AP-12 — kernel below the supported floor. Forbidden by NFR-SEC-35 + NFR-MAINT-01 (CVE-patch SLA).
- AP-13 — picking the sandbox tier by data classification (e.g. "NPI → microVM" or "PUBLIC → runc"). The container-escape attack surface for adversarial LLM-issued code is identical regardless of data class. Data class governs retention (NFR-COMP-01), key custody (NFR-SEC-33), and residency (NFR-COMP-13); the workload-trust profile picks the tier. Forbidden by NFR-SEC-02 + NFR-SEC-38.

## Long-form scenarios

Eight scenarios are candidates for full Source / Stimulus / Response / Response-Measure treatment in a follow-up PR: NFR-SEC-01 (kill switch), NFR-SEC-06 (replay bundle), NFR-REL-01..03 (RTO/RPO trio), NFR-SEC-04 (BYOK rotation), NFR-SEC-08 (MCP allow-list), NFR-MAINT-AUDIT-SCHEMA (OCSF), NFR-SEC-26 (internal service-to-service auth), NFR-FLEX-12 (customer-tenant Compute plane). Tracked: `arch/long-form-nfr-scenarios`.

## Open questions

1. NFR ID versioning policy on breaking changes — major-version-bump vs supersede. Track: `arch/nfr-versioning-policy`.
2. NFR-violation surface — release notes + dashboard + both? Track: `arch/nfr-violation-reporting`.
3. SLO vs hard-threshold framing — error-budget rows vs binary pass/fail. Track: `arch/nfr-slo-vs-threshold`.
4. Pause-pod overprovisioning ratio per node pool. Track: `arch/pause-pod-overprovisioning-ratio`.
5. Substrate-specific TLS enforcement choice (k8s service-mesh vs Compose-network vs microVM-vsock — microVM tier post-v1, [`arch/microvm-tier-v1.1`](https://github.com/Wide-Moat/open-computer-use/issues/161)) — component-spec level decision. Track: `arch/intra-platform-tls-substrate-choice`.
