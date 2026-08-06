<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# next/v1 GA Roadmap

Prioritized wave plan to take the `next/v1` enterprise architecture from PoC-parity to GA. Synthesized from firsthand per-component + per-ADR distance maps against the canon (`MANIFESTO.md`, `manifesto/02-nfrs.md`, `manifesto/04-non-goals.md`). GA-ready = spec invariants enforced in code with tests, cited ADRs implemented, NFRs met, `status: tbd` seams built or cleanly deferred.

---

## 1. Honest overall GA-readiness

**≈ 52% GA-ready** (weighted by GA-criticality, not a flat mean of the eight component percentages).

The flat mean of the reported component scores is ~57% (62/68/62/55/35/30/72). Weighting down-adjusts it because the two lowest-scoring components carry the two GA-defining enterprise promises:

- **Egress trust-edge (06) at 35%** and **Audit pipeline (07) at 30%** are the components a regulated-enterprise auditor and the storage-credential-custody story rest on. Their weight is high and their scores are lowest, so they drag the weighted number below the mean.
- **The entire ADR cluster is `proposed`.** Of ~30 ADRs, only 6 are `accepted` (0022, 0023, 0024, 0025, 0026, 0027, 0028, 0001, 0004 — the accepted set). The egress cluster (0005/0006/0007/0008/0011/0016/0019/0021) and the load-bearing storage-custody ADR-0019 are all `proposed`. GA canon expects decision-bearing specs `accepted`. A GA where the whole egress+audit decision spine is unratified is not GA.

**PoC-parity works; GA canon does not.** The distinction is stark and consistent across the maps:
- The minimal-shelf, single-tenant, docker/runsc, storage-swap-in-a-harness path is **genuinely built, wired, and green** — control lifecycle invariants, gateway sk-key auth, filestore prefix-confinement + subtree join, sandbox host-side teardown/admission, webui security spine. This is real code with property/fuzz tests, not scaffold.
- The GA canon path — **stock-Envoy live enforcement, a shipping RFC-8693 exchange counterparty, the multi-source audit fan-in with a transparency-log anchor, user-namespace mapping in the sandbox, full-shelf OIDC/SCIM/SPIFFE identity** — is where four of the components (05/06/07 and the full-shelf halves of 01/02/08) have security-critical invariants with **no enforcing code**.

The honest read: the platform is a strong, well-tested PoC for the minimal shelf, roughly half-way to the enterprise-GA bar the canon defines.

---

## 2. The gap ledger (de-duplicated, grouped by theme)

### Theme A — Egress-edge live enforcement (the single largest cluster)
| Gap | Component / ADR | What is missing | Effort |
|---|---|---|---|
| A1. **CORRECTED 2026-07-26 — the edge already live-serves on stock Envoy.** | 06, ADR-0019 | The running `ocu-donegate-edge-1` is the upstream `envoyproxy/envoy` image by digest, version 1.31.10, PID 1 `/usr/local/bin/envoy`, serving `/etc/envoy/envoy.yaml` (chain `jwt_authn -> ext_authz -> router`); 7821 upstream requests, `ext_authz` denied 0 / `failure_mode_allowed` 0. What remains harness is the **exchange counterparty** (A2), not the edge. `credential_injector` is absent from the live chain entirely — the seam is `ext_authz`, and Envoy itself prints that the filter is work-in-progress and outside its security team's support, which disqualifies it for credential custody. Remaining A1 work: none as framed; the live-serving claim is closed. | closed |
| A2. RFC-8693 exchange counterparty is a test harness | 06, ADR-0019/0005 | `test/harness/exchange/` stands in for the shipping component. Needs a production exchange binary or bundled-OpenBao integration with per-{filesystem_id,intent} keyed issuance + per-session caching. Owner call: bundled OpenBao vs customer-provided authority contract. | L |
| A3. Generic LLM-leg inspection hop unbuilt | 06, ADR-0006/0016/0005/0007 | Only the storage-leg edge config exists. No arbitrary-host TLS-terminate + per-host leaf from per-deployment CA + client-bearer passthrough + SDS source for the LLM leg. | L |
| A4. Edge policy chain absent | 06, ADR-0008 | Decision names `jwt_authn→ext_authz→rbac→ratelimit→router`; only `jwt_authn` exists. No `ext_authz` denylist consult (kill-switch-at-edge), no per-session ratelimit, no `x-deny-reason`. | M |
| A5. INV-8/9/10 no artifact | 06, ADR-0008/0021 | denylist-drop, monotonic-clock revoke, L3 host-root-netns zero-relay have no code/test in the edge repo. (INV-10 attach seam IS built sandbox-side per ADR-0021.) | M |
| A6. Edge-authored OCSF per connection | 06, ADR-0011, NFR-SEC-03 | No access-log/tap→OCSF wiring in `envoy.yaml`; one-event-per-connection unproven. | S |
| A7. INV-2 TLS re-origination / inspection-CA custody untested | 06 | No test proving guest trust store holds only public root, inspection-CA private key never enters guest, origin-cert validation vs public CA set. | M |

### Theme B — Storage credential custody (ADR-0013/0019 vs shipped)
| Gap | Component / ADR | What is missing | Effort |
|---|---|---|---|
| B1. **RESCOPED 2026-07-26 — the mechanism runs on the stand; the shipped artifacts do not enable it.** | 04, ADR-0013/0019 | `docker inspect ocu-donegate-filestore-1` shows the real engine image running with `-verify-storage-jwt -storage-jwks-path .../credential-jwks.json -storage-jwt-issuer https://exchange.test -storage-jwt-audience filestore -claims-bind`, and a forged bearer at its south face answers 401 against 6800 legitimate 200s. So "engine does not verify the injected credential" is refuted on the stand. Two things stay open: the flags appear in NO shipped `deploy/*.yml` in the filestore repo (the stand was built from staged sources, so a clean rebuild from repo artifacts ships dark), and the **correctness** of that verification is unproven — alg pinning, absence of a fallback branch, `kid` handling. Remaining work: wire the shipped manifests plus a config-drift guard, and red-probe the three correctness axes. | M |
| B2. **REWRITTEN 2026-07-26 — there is no mismatch and no path to choose.** | 04, ADR-0029 | The keyed store is not in the Envoy config at all: it lives in the `ext_authz` sidecar, and its key is literally the pair — `type key struct { filesystemID string; intent string }` (`ocu-rclone-filestore/internal/edgeauthz/edgeauthz.go:73-76`, written at :166, read at :211, same key on the single-flight). Both roadmap "paths" hold simultaneously: the exchange is pair-keyed AND `intent` never travels the RFC-8693 wire (the request body carries `grant_type`, `subject_token`, `subject_token_type` only), riding inside the subject token and read after re-verification. The issuing side keeps no cache, so exactly one keyed store exists in the chain and the two sides cannot disagree. Remaining work: reword the decision text; the code needs nothing. | S (doc) |
| B3. 11 of 21 frozen south verbs return 501 | 04 | Unbuilt: createFile, getFileMetadata, readFileMetadata, fileDelete, listFiles, importFiles, importZip, migrateFilesystem, removeFilesystem, releaseQuarantinedFiles. A GA "only door to storage" must serve listFiles/createFile/getFileMetadata + filesystem lifecycle. | L |

### Theme C — Audit emit contract & tamper-evidence (07 / ADR-0009)
| Gap | Component / ADR | What is missing | Effort |
|---|---|---|---|
| C1. No pipeline component; only one source's emitter | 07, ADR-0009 | Audit code is an in-process library inside ocu-control. No multi-source mTLS fan-in, no per-source channel binding, INV-2 (source publishes only to own channel) untestable. | L |
| C2. Durable bus absent | 07, ADR-0009, NFR-REL-12 | Fsyncs straight to local file (local-commit floor met); no durable-bus seam, no decoupled fan-out, no replay-on-recovery, no bus-on-path chaos test. | L |
| C3. Merkle head + transparency-log + envelope signer unbuilt | 07, ADR-0009, NFR-SEC-03 | Code itself admits "not yet wired". No Merkle batching, no daily head, no tx-log publish, no submission-envelope signer. Tamper-evidence is detective-only. | L |
| C4. Per-source fairness / saturation self-emit absent | 07, NFR-SEC-56/PERF-10 | No rate-shaping keyed to host-attested source, no saturation OCSF event, no flood chaos test. | M |
| C5. WORM cold-tier + retention floor (7y/10y) | 07, NFR-COMP-01 | No retention-policy code, no hot→cold rotation (WORM substrate stays a customer seam). | M |
| C6. Filestore audit fan-out is local-only | 04, INV-7 | Local fsync'd chain exists; no fan-in publisher seam + dropped-fan-out reconcile counter. | M |

### Theme D — Full-shelf enterprise identity (01 / 02 / 08 / ADR-0004)
| Gap | Component / ADR | What is missing | Effort |
|---|---|---|---|
| D1. **RECLASSIFIED 2026-07-26 — an unselected shelf, not a gap.** | 01, ADR-0027 | The vendored constraint contract makes the RFC 8707 audience rule and the RFC 9728 resource-metadata pointer CONDITIONAL on an `oauth2-rs` auth mode, with `static-key` as the declared default; the unconditional rule is only that a 401 carries a `WWW-Authenticate: Bearer` challenge, which the shipped gateway does send. So the missing OAuth-RS validator is the unbuilt half of a ratified two-shelf design (ADR-0027, accepted), not debt — and selecting the shelf is an architect decision, deferred to Phase 7. Two REAL items surfaced underneath it: no test anywhere pins the unconditional challenge (zero `WWW-Authenticate` hits across all `*_test.go`), and the validator embeds a second, pre-ADR-0027 copy of the constraint schema that contradicts the canon copy on exactly this point. | S (the two real items) |
| D2. Control full-shelf operator auth | 02, ADR-0004 | No OIDC/SCIM relying-party, PAM-JIT, or SPIFFE-SVID SOAR identity. Only minimal-shelf peer-cred + signed-webhook seam. | L |
| D3. Concrete SOARVerifier unwired | 02, ADR-0004 | Structural verify-then-mint fence is fail-closed and tested, but no concrete signed-webhook signature verifier is wired (interface only). | S |
| D4. WebUI full-shelf OIDC embed | 08 | Only minimal-shelf HS256 pre-issued token verified. No RS256/OIDC discovery/JWKS-per-issuer. INV1 holds minimal-shelf only. | L |
| D5. Gateway per-action authz | 01, NFR-SEC-49, #187 | Deny-by-default per-action authz (caller+tool+params) absent. Named GA security control; spec declares it a residual (clean boundary) but a regulated authz review will require it. | M |

### Theme E — Sandbox hardening & lifecycle invariants (05)
| Gap | Component / ADR | What is missing | Effort |
|---|---|---|---|
| E1. **REFRAMED 2026-07-26 — the fix is daemon config plus an admission gate, never a per-container field.** | 05, NFR-SEC-14 | `UsernsMode` is absent from all of `host/` (grep: zero hits) and guest UID0 == host UID0 under `runc`. But writing `UsernsMode` in `buildHostConfig` is the wrong fix and the repo already decided so: DD-7 (`ocu-sandbox/docs/design-decisions.md:197-205`) records that no per-container enable exists — remap is daemon-global and the only per-container control (`--userns=host`) *disables* it — so "the create path writes no per-container userns field: a no-op field would falsely imply an isolation property the container does not have". Correct form: daemon remap at deployment plus a per-create fail-closed admission gate that refuses when the daemon reports no remap, with the keystone observed as the actual in-container `uid_map`. Landlock stays absent and is a separate item; a shipped doc claims it as delivered, which is its own defect. | M |
| E2. Snapshot/hibernate/resume/fork | 05, INV12, NFR-REL-08 | Not built — no secret-zeroization at snapshot, no resume-time re-identity + entropy/boot_id reseed, no N-fork uniqueness test. | XL |
| E3. Monotonic-clock rollback defence | 05, INV13, NFR-SEC-48 | Guest TTLs read wall clock; no resume-time wall-clock correction; no rollback red-team. | M |
| E4. Erase-before-reuse / per-session DEK | 05, INV14, NFR-SEC-54 | Page-cache-drop + region-zeroize / per-session-DEK-destroy on recycled mount is a stub; session-1→session-2 no-read property test absent (cross-repo with filestore). | L |
| E5. Runtime-monitor host-authored audit half | 05, INV5, #181 | Not-guest-disableable runtime-monitor authoring in-sandbox tool-call events out-of-band unbuilt (spec residual). | M |
| E6. Guest mount-config ingestion (F7) | 05, ADR-0013/0019 | In-guest mount-config consumption + scrub-after-load (NFR-SEC-25 guest half) not in ocu-sandbox. | M |
| E7. Cross-tier egress e2e (runc AND runsc) not a GA gate | 05, INV16 | Docker-gated, skips on darwin; not a required CI gate. Canon demands zero-relay proven under positive control on both tiers. | M |

### Theme F — WebUI preview substrate & audit actor (08)
| Gap | Component / ADR | What is missing | Effort |
|---|---|---|---|
| F1. Preview-render substrate | 08, INV7, ADR-0026 | Null-origin sandboxed-iframe render under body content-CSP is a gated stub (`PREVIEW_RENDER_ENABLED` OFF; `handlePreview` no-op). INV7 preview half unbuilt. | M |
| F2. OCSF actor bound to scope not embed principal | 08, INV8, #181 | Audit actor set to `{session_uid: filesystemId}`, not `session.sub`. Non-repudiation cannot attribute to the asserting user. | S |

### Theme G — Frozen contracts + ratification
| Gap | Component / ADR | What is missing | Effort |
|---|---|---|---|
| G1. Control frozen OpenAPI/gRPC + buf/oasdiff CI | 02, #205, NFR-IC-04 | Wire is HTTP/newline-JSON-over-UDS handlers, not the frozen operator-REST/SOAR OpenAPI 3.1 + session_setup.proto; no buf breaking / oasdiff gate. | M |
| G2. ADR ratification (proposed→accepted) | all ADRs | Egress cluster (0005/6/7/8/11/16/19/21) + storage (0010/0013/0015/0029/0030) + sandbox (0003/0017/0018) + 0002/0009/0012 all `proposed`. Owner batch sign-off + write-down reconciliations. | S–M (per cluster) |

### Theme H — Image provisioning (ADR-0020, the one genuine open decision)
| Gap | Component / ADR | What is missing | Effort |
|---|---|---|---|
| H1. Appended-OCI-layer agent injection | ADR-0020 | `mutate.AppendLayers` materialize step (agent as appended layer, not baked). BYO allow-set + control-owned Entrypoint already built. | L |
| H2. Four-rung shelf (min/medium/high/xhigh) + sign pipeline | ADR-0020 | high=Chromium+CDP, xhigh=Claude Code CLI on patch SLA. | L |
| H3. Two-signature cosign admission | ADR-0020 | Verify image + injected-agent signatures separately at session-create admission. | M |
| H4. Injection test matrix + NFR row + BoM/licence rows | ADR-0020, manifesto/02+05 | Merge-blocking matrix across substrate × rung × BYO; land BoM/licence rows (blocking dependency for ratification). | M |

### Theme I — Session-view forward-compat (ADR-0002)
| Gap | Component / ADR | What is missing | Effort |
|---|---|---|---|
| I1. Descriptor-driven session view | 08, ADR-0002 | WebUI ships a hardcoded FilePane. No descriptor type, no discovery endpoint, no ignore-unknown-kind render path. Length-1 `[files]` seam only (browser/terminal descriptors stay deferred to #210). | M |

### Theme J — Layer-0 CI gate debt
See Section 4 — treated as its own phase.

**Fully implemented / clean-deferral, NOT gaps (do not re-flag):** ADR-0010 (both engines), ADR-0014 (transport triplet), ADR-0021 (attach stand-in), ADR-0023/0025/0028 (north Files-API), ADR-0026 ingest tier, ADR-0027 sk-key, ADR-0022 admin read-surface, ADR-0024 shared module, ADR-0012 language split, ADR-0030 south per-chat scope. Firecracker/k8s/microVM stubs are canon-sanctioned deferrals (untrusted profile is a locked v1 non-goal).

---

## 3. Dependency-ordered phases

Each phase is a shippable increment; no phase depends on a later one. **Canon-change-first** steps (ADR ratification) precede the code they gate.

### Phase 0 — Ratification & reconciliation (canon-change-first, mostly docs)
Unblocks everything downstream; no code depends on a later decision.
- **Ratify the cheap, code-conforming ADRs:** 0012 (language, code already conforms), 0003 (runtime ladder, fully implemented), 0018 (control-RPC, fully implemented), 0017 (after resolving #270/#271 repo-home calls), 0010 (both engines built). Owner batch sign-off → `accepted`.
- **Write the storage-custody reconciliation** (gap B2): decide ADR-0029 path (a) edge re-key vs (b) doc reconciliation that intent rides the JWT claim + ADR-0030 derived-scope makes each mount distinct. Write it down before ratifying 0029.
- **Rule the egress cluster:** owner sign-off that ADR-0016 permissive-baseline recut is final; batch-flip 0006/0007/0008/0011/0016. Rule whether ext_authz/ratelimit (0008) are v1-GA or hardening.
- **Rule ADR-0019 exchange counterparty:** bundled OpenBao vs customer-provided authority contract (gates B1, A2, 0005, 0011).
- Keystone: `docs/architecture` front-matter shows target ADRs `accepted`; content-routing tree walked on each reconciliation edit; doc-slop-reviewer clean.

### Phase 1 — Storage credential custody made real (B1, B2, B3, C6)
The custody model is the spine the whole egress+storage story hangs on; it precedes egress live-serving because the engine must verify the injected credential before the edge injects it live.
- ADRs: ratify 0013/0015/0029 after Phase 0 reconciliation; 0019 stays proposed until Phase 2 lands its counterparty.
- Build: real credential extractor binding {fsid, intent} from the injected credential, JWKS-verified (iss/aud/alg); move scope enforcement to engine-verifies-injected-credential (B1). Implement the 11 missing frozen south verbs against the engine adapter with the same authz/audit/ceiling spine (B3). Add filestore audit fan-in publisher seam + drop counter (C6).
- Keystones: foreign-fsid 403 originates AT the engine on the injected credential (not the route layer); listFiles/createFile/getFileMetadata green; south verb 501-count → 0.

### Phase 2 — Egress trust-edge live (A1, A2, A6, A7)
Depends on Phase 1 (engine must verify the injected credential) and Phase 0 (0019 counterparty ruling).
- ADRs: ratify 0019 once the exchange counterparty is a shipping contract; ratify 0005/0011.
- Build: graduate RFC-8693 exchange from harness to a shipping service (or bundled-OpenBao) with per-{fsid,intent} keyed issuance + per-session cache (A2). Stand up real Envoy 1.31+ serving `envoy.yaml` against live JWKS + exchange + filestore; resolve the credential_injector WIP posture (#240) (A1). Edge access-log→OCSF one-event-per-connection (A6). TLS re-origination + inspection-CA custody test (A7).
- Keystones: forwarded Authorization ≠ inbound JWT proven on the stock binary (not harness); unauthenticated leg unchanged; 403-at-engine end-to-end; in-guest scan finds no signing key.

### Phase 3 — Sandbox hardening core (E1, E3, E6, E7)
Independent of egress; the security-critical invariants with no code. Sequenced before snapshot (E2) because userns/clock are simpler and higher-severity.
- ADRs: 0018/0024 already accepted; no new decision.
- Build: daemon userns-remap at deployment + a per-create fail-closed admission gate that refuses when the daemon reports no remap, keystone observed as the in-container `uid_map`, RED-on-removal test; NOT a per-container `UsernsMode` field, which DD-7 forbids as a no-op that falsely implies isolation. Landlock ruleset in guest supervisor, plus the correction of a shipped doc that already claims Landlock as delivered (E1). Route guest TTL through monotonic source + resume-time wall-clock correction + rollback red-team (E3). Guest mount-config ingestion + scrub-after-load (E6). Promote cross-tier egress e2e (runc AND runsc) to a required Linux CI gate (E7).
- Keystones: admission rejects a container with host UID0==guest UID0; clock-rollback cannot extend a TTL; zero-relay proven on both tiers as a required gate.

### Phase 4 — Audit pipeline as a component (C1, C2, C3, C4, C5)
The heaviest single component. Depends on Phase 0 (ADR-0009 ratification) and reuses the filestore fan-in seam (C6) from Phase 1.
- ADRs: ratify 0009 after owner confirms shipping the mandatory core (Merkle head + envelope signer) in v1 vs downgrading them in the ADR text.
- Build: fan-in ingress service terminating five mTLS source channels + self-emit, binding OCSF source to verified peer, rejecting cross-channel publishes (C1). Durable-bus seam (embedded WAL solo default) + decoupled fan-out + replay-on-recovery + NFR-REL-12 chaos test (C2). Merkle-head accumulator + daily submission envelope + host-local signer + tx-log endpoint as customer seam (C3). Per-source token-bucket + saturation OCSF + flood chaos test (C4). Retention-floor + hot/cold tier boundary (C5).
- Keystones: one source's credential rejected on every other channel; bus-on-path for every event; daily transparency-log probe green; flood shapes not drops with zero chain breaks.

### Phase 5 — Control kill-switch SLA + frozen contracts (Control GA-blockers)
- ADRs: 0004 minimal-shelf ratification; 0018 accepted.
- Build: bounded worker pool with reserved admission priority on the operator listener + k6 load harness proving ≤30s p99 revoke SLA under create+operator flood (NFR-SEC-55, the control GA-blocker). Implement frozen operator-REST/SOAR OpenAPI 3.1 + session_setup.proto gRPC; wire buf breaking + oasdiff CI (G1). Concrete SOARVerifier signed-webhook impl (D3). Gateway per-action authz (D5).
- Keystones: revoke ≤30s p99 while flooded (non-vacuous load, sized to saturate); buf/oasdiff reds on a breaking change; SOAR revoke with a bad signature refused.

### Phase 6 — WebUI GA half (F1, F2, I1)
- ADRs: 0002 ratification (build the length-1 descriptor seam so implementation stops contradicting the decision); 0026 already accepted.
- Build: null-origin sandboxed-iframe preview render under body content-CSP + iframe-isolation test, then flip the gate (F1). Thread `session.sub` into audit actor (F2). Descriptor type + length-1 discovery endpoint + ignore-unknown-kind shell (I1).
- Keystones: preview cannot download/write and stays non-downloadable regardless of stored tag; audit actor carries the embed principal; unknown descriptor kind renders nothing and does not crash.

### Phase 7 — Full-shelf enterprise identity (D1, D2, D4)
The bank-facing shipping path; large and sequenced late because minimal shelf ships GA-usable and the full shelf is additive behind existing seams.
- ADRs: 0004 full-shelf; 0027 full-shelf path (already reserved).
- Build: OAuth 2.1 RS validator (aud/8707/9728, JWKS refresh) behind CallerAuthenticator + shelf switch (D1). OIDC/SCIM RP + SPIFFE-SVID SOAR identity behind OperatorSeam (D2). WebUI OIDC/JWKS-per-issuer + per-deployment allowlist (D4). Integration tests against Dex/Keycloak stand-in.
- Keystones: revoked full-shelf identity denied; per-deployment frame-ancestors allowlist enforced; both shelves pass their invariant suites.

### Phase 8 — Image provisioning (ADR-0020, the last open decision)
Sequenced last: ADR-0020 is a STUB with 6 open questions and cannot start until the Decision leaves TBD.
- ADRs: close ADR-0020's 6 open questions (owner + contracts-owner calls + BoM/licence rows); move off STUB.
- Build: appended-OCI-layer injection (H1); four-rung shelf + sign pipeline (H2); two-signature cosign admission (H3); injection test matrix + NFR row (H4).
- Keystones: unsigned base fails closed; agent-layer signature mismatch refused; FUSE-under-gVisor + /dev/fuse cells proven.

### Phase 9 — Snapshot/hibernate/resume/fork + erase-before-reuse (E2, E4, E5)
Largest sandbox work; NFR-REL-08 is a named GA reliability promise but touches the most surface, so it lands after the higher-severity hardening (Phase 3).
- Build: snapshot secret-zeroization + resume host-attested re-identity + entropy/boot_id reseed + N-fork uniqueness test (E2). Per-session DEK destroy + page-cache drop on mount recycle, cross-repo with filestore + session-1→session-2 no-read property test (E4). Runtime-monitor host-authored audit path (E5).
- Keystones: N forks yield N distinct identities; session-2 cannot read session-1 marker; hibernate→resume e2e green.

---

## 4. Layer-0 CI-gate debt (its own phase)

Canon (`CLAUDE.md` testing section + NFR-SEC-07/19/20, PERF-13) requires these as Layer-0 gates that ship *before* architectural content.

**RE-MEASURED 2026-08-06 against the eight repos and the live branch-protection API.** The table below was written from the distance maps, which understated the fleet: three rows called "Missing fleet-wide" are stale, and the two real gaps are ones the table never names. Every cell now cites a workflow file, and every "required" claim was read from `gh api repos/<repo>/branches/main/protection`, not inferred from a file's presence.

**The two real gaps.**

1. **`ocu-audit` has no remote.** The Wide-Moat org hosts seven fleet repos; `ocu-audit` is local-only on `feat/ga-supply-chain-release`, whose HEAD is `ci(release): add signed-SBOM + SLSA release pipeline` — a release pipeline that has never executed anywhere. No Actions, no protection, no required checks. One of canon's four mutation-gated package classes is entirely unverified: not a weak gate, an absent one. This is the wave's largest finding.
2. **~~`ocu-sandbox` ships an unsigned, unattested image.~~ WITHDRAWN 2026-08-06, same day.** The first census read the local worktrees, and `ocu-sandbox` had `chore/unblock-sast-sca` checked out — eight commits behind its own `origin/main`, which carries cosign keyless signing, an SPDX SBOM attestation and SLSA build provenance. Re-measured against `origin/main` rather than whatever branch a worktree sits on, **every one of the seven remote repos carries SBOM tooling**. `ocu-admin`'s main is the lone exception and it is being fixed in flight: `feat/ga-image-scan-gate` holds fourteen unpushed commits adding exactly that gate.

**The method error is the finding.** A fleet census that greps working copies measures which branch each worktree happens to sit on, not what the fleet ships. Every claim in this table is now read from `origin/main` with `git grep <ref>`; a claim about a repo's shipped CI that was taken from a checked-out branch is not evidence.

**The red-probe shape the fleet already settled.** `ocu-control` carries eleven probe scripts wired INLINE into jobs that are themselves required contexts (`secrets-gitleaks`, `secrets-trufflehog`, `sast-semgrep`, `sca-trivy-fs`, `mutation`, `deadcode`, `docs`), and `ocu-mcp-gateway` carries two the same way. Inline is the right shape: the probe rides an existing required context, so "is the probe required?" dissolves by construction and a red probe is a blocked merge. `ocu-filestore`'s separate `gate-redprobe.yml` is the deeper two-tree variant on a path filter plus a daily cron — a backstop, deliberately not per-PR, and correctly absent from its required set.

| Gate | Canon requirement | Status from the maps | Action |
|---|---|---|---|
| gitleaks + trufflehog blocking | NFR-SEC-19, top-3 | **Required in all 7 remote repos** (read from the live protection API). Red-probed per-PR in control (inline) and on a cron in filestore | Port the inline two-sided probe to webui, admin, sandbox. Do NOT touch rclone: a peer's `ci/layer0-red-probes` branch is in flight there |
| Semgrep + CodeQL HIGH/CRITICAL block | NFR-SEC-20, top-3 | Gateway IaC self-test exists; general SAST/SCA per-repo state unverified fleet-wide | Verify Semgrep+CodeQL on changed files across all 8 repos + Trivy/Grype CRITICAL on deps/images |
| Signed SBOM + SLSA L3 provenance | NFR-SEC-07/18, top-3 | **STALE — shipped on `origin/main` in every remote repo**, sandbox included (`ghcr-guest.yml` signs by digest, attests SPDX, records SLSA provenance). Measured with `git grep origin/main`, not the worktrees | No fill. `ocu-admin` is the only main without it and carries fourteen unpushed commits adding it (`feat/ga-image-scan-gate`) — leave it to that branch |
| Mutation ≥60% on auth/sandbox/audit/broker | CLAUDE.md CI | Present historically (gateway G2b mutation gate in memory); audit/broker/sandbox coverage unverified | Confirm mutation gate on all four package classes; the audit + exchange packages are new and need it |
| Property-based tests on parsers/scheduler/policy | CLAUDE.md CI | Strong in filestore (fuzz/property) + control; verify gateway profile validator + audit chain | Confirm property tests on every parser/scheduler/policy engine |
| k6 perf regression <10% | PERF-13 | **STALE for the gateway.** `ocu-mcp-gateway/.github/workflows/perf.yml` is a pinned-checksum k6 ABAB gate (`head_p95 > base_p95*1.10 AND delta > 2ms`), deliberately `continue-on-error` with its ratchet-to-required marked owner-gated in the file | Ratchet the gateway gate to required (owner call), then extend to PERF-02/03/06/08 + the SEC-55 revoke SLA (Phase 5) |
| Playwright golden-path E2E | CLAUDE.md CI | WebUI live-browser proof exists (memory); not a required per-merge fleet gate | Promote to required golden-path on every merge |
| Promptfoo red-team subset per PR | CLAUDE.md CI | **CONFIRMED MISSING** — zero promptfoo/garak/pyrit hits across all eight repos | Add Garak/PyRIT nightly + Promptfoo subset per PR |
| IaC scan (Checkov+tfsec), Conftest no-operator-route | NFR-SEC-52 | Gateway `iac_policy_check.py` with self-test; fleet-wide Conftest/OPA gateway→operator unproven | Confirm the fleet CI carries the rendered-manifest OPA assertion (gap map calls this out for 01 + 02) |
| License scan against allow-list | Dependency policy | Per-repo lexicon gates; license allow-list scan unverified | Confirm license scan vs `manifesto/05-licensing-posture.md` allow-list (blocks ADR-0020 BoM rows) |

**This is a standalone phase, run early and in parallel** (it does not depend on component code): a "Layer-0 CI-gate fleet audit + fill" that red-probes each gate (plant a secret, a CRITICAL dep, a breaking API change, a >10% perf regression) and proves each reddens before declaring green — per the memory lessons on vacuous gates (`required + continue-on-error`, whitelisted example secrets, required-ABSENT).

---

## 5. Non-goals guardrail (must stay UNBUILT with clean boundaries)

Per `manifesto/04-non-goals.md`. A builder must NOT implement any of these:

1. **Skill registry** — v1 ships zero default skills. `SkillProvider` stays `status: tbd`; skills load from a customer-supplied registry over a stable contract. Do not invent the skill metadata schema, versioning, or discovery protocol. (NFR-SEC-24 carries the invariant only when it lands post-v1.)
2. **Hosted models & the agent loop** — OCU hosts/proxies/selects no LLM and runs no loop. The loop lives in the calling client (Open WebUI / n8n / LiteLLM / any MCP caller). A sandbox tool needing an LLM reaches it as **one allow-listed egress endpoint** under the Egress trust-edge + audit path — never an OCU model abstraction. Gateway routes only; do not add a model/loop abstraction to 01 or 02. (The REVISIT NFRs — FS-03, REL-04, SEC-21, COMP-09/10/14/25/26 — are non-gating; do not enforce them.)
3. **Mutating admin web UI** — no read-write operator console. Every mutation (lifecycle, quota, denylist) runs over `occ` CLI + GitOps. **Clarification for builders:** the *read-only* `ocu-admin` console IS in scope and already built (ADR-0022, accepted) — a live view with no write path. The end-user data-plane UI (upload/download/preview/render) is ALSO in scope (that is component-08, NFR-SEC-82). Do not add a mutation route to ocu-admin.
4. **Durable customer-data store** — OCU is an ephemeral workspace; session files live on the mounted scope only while the session runs, scrubbed at teardown (NFR-SEC-65/54). The only long-term artifact is the audit record (who/what/when, not bytes) on the NFR-COMP-01 floor. The object store is a customer-provided capability reached via `ocu-filestore`; do not make OCU a system of record.
5. **SaaS offered by us** — FSL-1.1-Apache-2.0 forbids competing hosted/embedded offerings. Self-hostable software only.

Also keep deferred (canon-sanctioned, not gaps): microVM/Firecracker + k8s runtime tiers (untrusted profile is not deployable in v1 GA; admission rejects it), server-side heavy parser substrate (ADR-0026, behind a future trigger ADR), mid-session Storage-JWT refresh (ADR-0013 #267), within-tenant north hard boundary (ADR-0030 #348), per-object authz (#187), embed-token replay-binding (#217).

---

## 6. The first 3 concrete waves to run next

Each is a Workflow-sized unit (one coherent PR-cluster with keystone verification), ordered so none depends on a later one. Wave 1 is deliberately the CI-gate fleet audit (no code dependency, unblocks trustworthy green everywhere) run in parallel with the storage-custody spine.

### Wave 1 — Layer-0 CI-gate fleet audit + fill (parallelizable, no code dependency)
- **Canon:** NFR-SEC-07/18/19/20, PERF-13, CLAUDE.md testing section.
- **Components:** all 8 repos + `deploy/fleet`.
- **Build:** confirm gitleaks/trufflehog/Semgrep/CodeQL/Trivy required-and-red-probing per repo; **build the two missing gates** — Syft→SPDX + Cosign + SLSA L3 provenance, and k6 perf gates for PERF-02/03/06; add the fleet Conftest/OPA gateway→operator-route assertion.
- **Keystones:** plant a secret → gitleaks reds; plant a CRITICAL dep → Trivy reds; remove SBOM → release fails; a rendered manifest granting gateway→operator route → OPA reds. Each proven `required-ABSENT`, not just not-green (per the required-ABSENT memory lesson).

### Wave 2 — Storage credential custody made real (Phase 1 core)
- **Canon-change-first:** write the ADR-0029 reconciliation (path a vs b) and the ADR-0019 counterparty ruling in Phase 0; ratify 0013/0015/0029.
- **ADRs:** 0013, 0015, 0029 (0019 stays proposed pending Wave-3 counterparty).
- **Components:** 04 (ocu-filestore), 02 (ocu-control, intent mint already built).
- **Build:** real credential extractor binding {fsid, intent} from the injected credential with JWKS/iss/aud/alg verification (gap B1); move scope enforcement to engine-verifies-injected-credential; implement the highest-value missing south verbs first — listFiles, createFile, getFileMetadata, fileDelete, removeFilesystem (gap B3, first tranche); filestore audit fan-in publisher seam + drop counter (C6).
- **Keystones:** foreign filesystem_id → 403 originating **at the engine** on the injected credential (not the route layer — this is the inv-4 that option-c currently violates); listFiles/createFile green against the engine; missing/expired credential → 401; south 501-count drops by 5.

### Wave 3 — Egress trust-edge live on stock Envoy (Phase 2 core)
- **Canon-change-first:** ratify 0019 once the exchange counterparty is a shipping contract (owner ruling from Phase 0: bundled OpenBao vs customer authority); ratify 0005/0011.
- **ADRs:** 0019, 0005, 0011.
- **Components:** 06 (ocu-rclone-filestore edge + exchange), depends on Wave-2 engine.
- **Build:** graduate RFC-8693 exchange from `test/harness/exchange/` to a shipping service (or bundled-OpenBao) with per-{fsid,intent} keyed issuance + per-session cache (A2); stand up real Envoy 1.31+ serving `envoy.yaml` against live control-plane JWKS + exchange + Wave-2 filestore; resolve the credential_injector WIP-filter posture (#240); add edge access-log→OCSF per connection (A6).
- **Keystones:** on the **stock Envoy binary** (not the Go harness), forwarded `Authorization` ≠ inbound weak JWT AND the unauthenticated leg is unchanged; end-to-end swap → engine enforces scope → foreign fsid denied; one OCSF event per connection emitted; in-guest secret scan finds no signing key. This closes the 06 GA-blocker that today is proven only by a harness reimplementation.

---

*Sources: firsthand per-component distance maps (01–08) and per-ADR maps (egress 0005/6/7/8/11/16/19/21, storage 0010/13/15/23/25/28/29/30, sandbox 0003/17/18/20/24/26/27, cross 0001/2/4/9/12/22); canon `MANIFESTO.md`, `manifesto/02-nfrs.md`, `manifesto/04-non-goals.md`.*
---

## 7. Wave sequencing ruling (Fable advisor, 2026-07-12)

The owner delegated the wave-order decision to Fable. Ruling: start with storage
credential custody, NOT Layer-0 CI and NOT pure ratification.

**WAVE 1 (FIRST) - Storage credential custody made real (theme B core + canon head).**
PREMISE CORRECTED 2026-07-26, and the correction shrinks the wave. The original
rationale claimed the shipped `ocu-filestore` trusts a forged bearer's
`filesystem_id`/`intent` claims in the RUNNING path. On the stand that is refuted:
the running engine verifies an exchange-issued credential and answers 401 to a
forged bearer. What survives is narrower and still worth the wave: the verifying
flags live only in staged sources, so a clean rebuild from repo artifacts ships
dark; the verification's correctness (alg pinning, fallback branch, `kid`
handling) has no red-probe; and the two token pairs were unpinned until this week.
The wave keeps its place at the head because the engine is the hard dependency for
egress work, not because isolation is currently a lie. It is
also the critical-path head: Wave 3 (egress-live) hard-depends on the engine
verifying the injected credential first; Layer-0 CI depends on nothing and blocks
nothing, so doing the parallelizable item first wastes the longest lead time. The
XL fear belongs to the egress half (stock Envoy + exchange counterparty = Wave 3);
the custody CORE (JWKS-verified extractor + engine-enforced scope) is effort L.
- Canon head (folded in): draft ADR-0029 reconciliation as PATH (b) - intent rides
  the JWT claim, ADR-0030 derived scope keeps mounts distinct (matches what is
  built; path (a) touches the edge = Wave-3 territory). Queue 0013/0015/0029
  ratification drafts for OWNER sign-off; 0019 stays proposed pending the
  counterparty ruling (OpenBao vs customer authority).
- Repos: ocu-filestore (primary); ocu-control (JWKS artifact already renders - pin
  iss/aud off "PIN-PENDING").
- Build: B1 - real credential extractor binding {fsid,intent} with JWKS/iss/aud/alg
  verification; scope enforcement moved to engine-verifies-injected-credential.
  B3 first tranche - listFiles, createFile, getFileMetadata, fileDelete,
  removeFilesystem. C6 - audit fan-in publisher seam + drop counter.
- KEYSTONE (non-vacuous, red-probe FIRST): today's shipped binary must ACCEPT a
  forged unsigned bearer (proving the hole is live), then the fix reds it -
  forged/unsigned -> denied; foreign fsid -> 403 ORIGINATING AT THE ENGINE;
  missing/expired -> 401; south 501-count -5.
- Effort: L (~5-7 builder agents, one PR-cluster). Merges OWNER-GATED.
- Unblocks: Wave 3 egress-live (hard dep), ADR-0019/0025 "impossible by
  construction" becoming true, 0013/0015/0029 ratification, Phase-4 audit fan-in.

**WAVE 2 - Layer-0 CI-gate fleet audit + fill** (theme J): SBOM/SLSA + k6 built,
every existing gate red-probed required-ABSENT, landing BEFORE egress goes live so
Wave-3 keystones sit on a trustworthy substrate.

**WAVE 3 - Egress trust-edge live on stock Envoy** (A1/A2/A6/A7), with the owner's
ADR-0019 counterparty ruling (OpenBao vs customer authority) obtained during Waves 1-2.
