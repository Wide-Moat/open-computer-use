<!-- SPDX-License-Identifier: BUSL-1.1 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# Architecture Gap Analysis

> **Pre-mortem inventory** of architecture topics that are either absent or only lightly addressed in [`architecture/`](./architecture/), [`adr/`](./adr/), and [`roadmap.md`](./roadmap.md). Captured **before** code meets reality, so each gap can be resolved (or explicitly deferred) on its own merits.
>
> This is **not** an ADR and **not** a roadmap edit. Phase pointers below are **suggestions**, not commitments. Tier-1 gaps are expected to graduate into their own ADRs / phase-research docs over time.

## How to read this doc

- **Status legend**
  - **MISSING** — topic not addressed anywhere in the live spec.
  - **LIGHT** — touched in one or two places but no architectural weight (no contract, no acceptance criteria, no rollback).
  - **PRESENT** — explicitly named with a contract or acceptance hook in `architecture/` or `adr/`.
- **Lands in phase** — the existing roadmap phase that is the most natural home for the work. Where no phase fits, the entry says so.
- **Cross-cuts** — items that apply to every phase. They belong in invariants or CI policy, not a single phase row.
- **External precedents** — projects worth studying before opening an ADR. These should turn into entries in [`references.md`](./references.md) and digests under [`research/`](./research/) when their gap is taken up.

For phase context see [`roadmap.md`](./roadmap.md). For locked operational choices see [`antipatterns.md`](./antipatterns.md).

---

## A. Multi-tenancy beyond per-session

The current isolation boundary is the **sandbox**. A tenant is an organisation that owns N users and M sessions. The tenant boundary is not defined.

- **Tenant ≠ session.** Define the tenant model (org → users → sessions) as a first-class L4 entity.
- **Fairness between tenants** on a shared cluster — noisy-neighbour case where one tenant drains every warm-pool slot.
- **Per-tenant aggregate quotas** — concurrent sessions, MCP calls/min, storage GB, egress bytes/day. Per-sandbox quotas are insufficient.
- **Per-tenant config overlay** — tenant A gets MCP tool set X with Chrome egress to `*.github.com`; tenant B gets set Y with egress only to `*.internal.bank`.
- **Tenant-scoped audit** — auditor of bank A must not see events from bank B.

**Status:** LIGHT. `architecture/02-layer4-control-plane.md` names `tenant_id` on the session router, per-tenant S3 buckets, and the k8s "namespace per tenant" idea, but org-level fairness, aggregate quotas, per-tenant tool overlays, and per-tenant audit scoping are not contracted.

**Lands in phase:** deeper Phase 5 (`KubernetesProvider` is where tenant = namespace lives) with Phase-6 surface follow-ups (admin API for tenant CRUD, quotas).

**External precedents:** Vault namespaces, Confluent Cloud multi-tenant model, Kubernetes Hierarchical Namespaces (HNC), Snowflake account model.

---

## B. Identity beyond OIDC

OIDC is named in Phase 6. Enterprise-IT integration needs strictly more.

- **SAML 2.0** — required by large enterprises. Distinct protocol, not free from OIDC.
- **LDAP / Active Directory** direct — some legacy enterprises support nothing else.
- **Service accounts** for machine-to-machine (customer CI/CD triggers our platform).
- **RBAC granularity** — concrete roles (`template-admin`, `session-creator`, `audit-reader`, `secret-rotator`) and their permission matrices.
- **Federated identity for self-hosted** — the customer's Keycloak / Okta / Ping is the IdP, we are only the consumer.
- **Token caching & rotation policy** — explicit rotation cadence for access tokens, behaviour on revocation.

**Status:** MISSING (SAML, LDAP/AD, service accounts, federated self-hosted, token-rotation policy) / LIGHT (RBAC granularity — listed as an L4 concern but no permission matrix exists; per-sandbox empty-RBAC ServiceAccount is documented in `architecture/07-security.md` but that is sandbox-scoped, not identity-scoped).

**Lands in phase:** Phase 6 (Go control plane auth surface). RBAC matrix is a docs-only prerequisite that can land in Phase 0.5 follow-on.

**External precedents:** Coder enterprise auth, GitLab self-hosted Omnibus, Authentik, Keycloak federation patterns.

---

## C. Compliance and audit immutability

Audit append-only sink with ≥ 90 d retention is named in `architecture/07-security.md` and `architecture/10-observability.md`. Compliance posture is mentioned. Several pieces are still missing.

- **Frameworks promised.** SOC 2 Type II, ISO 27001, HIPAA, PCI DSS — each carries distinct controls. Without an explicit choice this does not sell.
- **Audit log immutability.** Write-once, no retroactive edit. S3 Object Lock / WORM storage. Phase 8 names the pipeline; immutability needs to be named with the same weight.
- **Retention policy.** Financial sector ≥ 7 years; HIPAA ≥ 6 years; GDPR "no longer than necessary". The conflict has to be resolved explicitly.
- **Data residency** as a hard guarantee. Tenant X data lives only in region Y. Architecturally this is **deployment topology**, not a template setting — a single control plane cannot serve tenants with different residency without full physical separation.
- **Right to be forgotten (GDPR Art. 17)** — selective deletion of a user's data from every system **including the audit log** (conflicts with immutability — needs tombstoning).
- **Session recording / lawful intercept** — a regulator may demand "show everything the agent did over period X" including screenshots, MCP calls, user input. A computed artefact.

**Status:** PRESENT (SOC 2 / HIPAA / PCI named in `architecture/07-security.md`, append-only sink named in `07-security.md` + `10-observability.md`) / LIGHT (GDPR — ephemeral-by-default posture only, no Art. 17 deletion flow; ISO 27001 implied not mapped) / MISSING (data residency, retention-policy conflict resolution, lawful-intercept session recording).

**Lands in phase:** first iteration in Phase 4 (secret broker — foundation for tenant-scoped secrets) and Phase 8 (audit immutability + retention). Data residency belongs in the future multi-region milestone (post Phase 10).

**External precedents:** AWS GovCloud / FedRAMP boundary doc, Sentry Single Tenant compliance, Atlassian Trust Center as a public-facing template.

---

## D. Determinism and session replay

- Can an agent session be **replayed 100 % accurately** for debugging? If the agent did something strange — full replay, or at least deterministic audit.
- Persist every MCP call + screenshot in a format that **plays back** → 80 % of replay capability at a low cost.
- **Time inside the sandbox** — does the agent see real wallclock or a frozen one? Anthropic `process_api` almost certainly manipulates the clock for consistent caching and reproducibility.
- **Random-seed control** — for skills that use randomness, fix the seed per session for replay.
- **Audit-event ID** — UUIDv7 (timestamp-prefixed) is much easier for time-range queries than UUIDv4.

**Status:** LIGHT. `architecture/07-security.md` covers CRNG reseed and wall-clock hardening on snapstart restore (anti-divergence), but session-replay debugging, deterministic time inside the sandbox, per-session random-seed control, and UUIDv7 audit IDs are not specified.

**Lands in phase:** Phase 7 (Rust agent — capabilities + dual-port API are the natural home for replay primitives) + Phase 8 (audit pipeline — replay reads from this).

**External precedents:** Mozilla rr (record/replay debugger), Replay.io, Antithesis (deterministic simulator), DVC for ML experiment determinism.

---

## E. Cost attribution and metering

- **Per-session billing primitives** — CPU-min, RAM-GB-min, storage-GB-day, egress bytes, MCP-call count. Without these no internal showback and no external chargeback.
- **Per-tenant aggregation** — realtime and period rollups.
- **Cost annotation on every sandbox event** — for post-hoc analysis ("what burned Q3 budget").
- **Threshold alerts** — tenant approaching quota → notification.

**Status:** MISSING. `architecture/10-observability.md` only carries a RAM capacity-sizing formula. No billing primitives, no metering SDK, no cost tagging.

**Lands in phase:** suggestion for a new **Phase 6.5** between Go control plane (Phase 6) and Rust agent (Phase 7). Not edited into `roadmap.md` in this PR.

**External precedents:** Kubecost (k8s-native cost), AWS Cost Explorer API model, OpenCost (CNCF), Stripe metered-billing primitives.

---

## F. Disaster recovery — RTO/RPO explicit

Phase 10 ships HA in a single region and multi-region foundations. The DR contract is not explicit.

- **RTO (Recovery Time Objective)** — how long to come back up after a catastrophe? 5 minutes? An hour? A day?
- **RPO (Recovery Point Objective)** — how much data can be lost on failover? Seconds? Minutes?
- **Backup strategy for control-plane state** — KV snapshots, PostgreSQL backups, S3 versioning.
- **Restore drills.** When was the last one. Without regular drills DR is fiction.
- **Chaos engineering** — regular component kill, verify the system degrades rather than collapses.

**Status:** LIGHT. Phase 10 snapshot/restore covers pause-resume and cross-AZ recovery; the DR runbook is mentioned but RTO/RPO targets, backup-strategy spec, drill cadence, and chaos engineering are not.

**Lands in phase:** suggestion to rename Phase 10 to **"HA + DR"** with explicit RTO/RPO in the acceptance criteria. Not edited into `roadmap.md` in this PR.

**External precedents:** Stripe DR game days (public write-ups), Netflix Chaos Monkey, AWS Well-Architected DR Pillar, Velero for k8s backups.

---

## G. Supply chain security

- **SBOM (Software Bill of Materials)** for every image. Without an SBOM, US-government deployments under Executive Order 14028 are unreachable.
- **Cosign / Sigstore signing** for every artefact — images, Helm charts, binary releases. Verify chain in kubectl admission.
- **Continuous CVE scanning** — Trivy / Grype in CI per PR + daily against existing images.
- **Reproducible builds** for the L1 agent — musl static-PIE, fixed timestamps, bit-by-bit identical builds. Rust fits well.
- **Base-image hardening** — Chainguard / Wolfi distroless instead of Ubuntu. Order-of-magnitude fewer CVEs by default.

**Status:** PRESENT (Cosign signing + admission verifier in `architecture/07-security.md`; templates reference by digest) / LIGHT (CVE risks per runtime listed but no automated scanning or IR flow; reproducible-build hints exist in `antipatterns.md` A22 — pinned versions + `SOURCE_DATE_EPOCH`, but not validated end-to-end) / MISSING (SBOM generation/distribution, base-image hardening).

**Lands in phase:** cross-cut. Add to a Phase-0.5 follow-on as CI policy (SBOM emit, Trivy scan, reproducibility CI check). Base-image hardening fits Phase 7 (new image is rebuilt anyway).

**External precedents:** SLSA framework, in-toto attestations, GUAC, CNCF TAG-Security guide.

---

## H. Air-gap and corporate networking

- **Air-gapped deployment** — offline installer with a tarball of every image and chart. Must install with **no internet at all**.
- **Corporate egress proxy** — `$HTTP_PROXY`, `$HTTPS_PROXY`, `$NO_PROXY` honoured everywhere. Custom CA bundle injection.
- **Internal certificate authority** — customer supplies their own CA, our services accept it for mTLS.
- **DNS via corp resolver** — cannot use `8.8.8.8`; must work with split-horizon DNS.
- **Update channel in air-gap** — how patches are delivered. USB stick? Internal mirror registry?

**Status:** MISSING.

**Lands in phase:** suggestion for a dedicated future phase, gated on the first regulated-deployment customer. Not edited into `roadmap.md` in this PR.

**External precedents:** Replicated KOTS (purpose-built for self-hosted), Anthos on-prem, GitLab Omnibus offline install, Anchore Enterprise.

---

## I. Operator UX (Day-2 ops)

- **Synthetic transactions** — every deploy auto-runs a canary sandbox session with a known tool and checks the result. Fails the deploy if it does not work.
- **Diagnostic bundle** — one command collects logs / configs / metrics / topology into a zip for support. Without it every support ticket is 3 hours of artefact gathering.
- **SLO templates** — Prometheus rules + Grafana dashboards out of the box.
- **Runbook catalogue** — "control plane unresponsive" → steps. "Sandbox stuck in Creating" → steps. Markdown in the repo.
- **Upgrade tooling** — `helm upgrade` with pre/post hooks for migrations. One-command rollback.

**Status:** PRESENT (SLO targets in `architecture/10-observability.md`; per-phase rollback windows in `roadmap.md`) / LIGHT (health probes named but no synthetic-transaction framework) / MISSING (diagnostic bundle, runbook catalogue, upgrade tooling beyond per-phase rollback).

**Lands in phase:** cross-cut. Each phase should grow operator-UX artefacts in parallel rather than wait for a standalone phase.

**External precedents:** Replicated Troubleshoot, Bitnami ops playbooks, GitLab "Database Lab" pattern, Sentry self-hosted ops.

---

## J. Versioning policy

- **Backward compatibility** — does L1 v3 control plane work with an L4 v1 control plane? How many versions back are supported. Capabilities negotiation is already in the architecture, which is good.
- **API deprecation policy** — announce N versions before removal, `Deprecated:` header on responses (Stripe-style).
- **Database migrations** — forward-only without data loss. Rollback is a separate DR procedure. Atlas / Sqitch / golang-migrate.
- **Live migration of sessions on upgrade** — if the control plane restarts, do live sandboxes keep running (because L1 is autonomous), or must the client reconnect? The contract must be written down.

**Status:** LIGHT (capabilities negotiation in `architecture/05-layer1-guest-agent.md`; Phase 6 has a dual-run strategy section) / MISSING (formal API-deprecation policy, schema-migration tooling spec, session-survives-upgrade contract).

**Lands in phase:** suggestion to add a new file `architecture/11-versioning.md` as the canonical versioning contract. Not created in this PR.

**External precedents:** Stripe API versioning manifesto, Kubernetes Deprecation Policy, Tailscale upgrade-compatibility blog posts.

---

## K. Agentic-workload edge cases

These are the core, and they tend to surface in production:

- **Cancellation latency.** User clicks Stop. How many seconds before a `pip install` in flight is actually stopped? Graceful chain (`SIGTERM` → wait → `SIGKILL`) timeout has to be explicit.
- **Long-running tools without HTTP timeout** — 30-minute web scrape, model training. WebSocket keepalive, progress events.
- **Disconnection mid-tool** — tool still running, client dropped. What should L1 do? Wait + save result? Kill?
- **Concurrent tool calls in one session** — legal or not? Two tools writing into the same directory?
- **Tool output larger than the MCP message limit** — `dmesg` stdout or a giant JSON. Streaming, pagination, pre-signed URL — which one is chosen.
- **Large files agent → user** — agent generated a 5 GB Parquet. S3 pre-signed URL or your transport? Cost implications.

**Status:** LIGHT (`architecture/05-layer1-guest-agent.md` covers `SIGTERM`→`SIGKILL`, zombie reaping, dual-port API; `process_api` precedent in `research/19` handles zombies and long-running processes) / MISSING (explicit cancellation-latency SLO, long-running-tool heartbeat protocol, disconnection-mid-tool semantics, concurrent-tool-call contract, output-size flow control, large-artefact transport policy).

**Lands in phase:** Phase 7 acceptance should be strengthened to cover the above. No new phase.

**External precedents:** JupyterHub kernel restart semantics, gRPC streaming patterns, S3 multipart upload, Anthropic Computer Use public docs (cancellation behaviour is described there).

---

## L. MCP ecosystem (zone of uncertainty)

- **MCP server discovery** — how the agent finds what is available. Static config vs runtime registry.
- **Per-tenant MCP server set** — tenant A gets Jira/Confluence, tenant B gets Salesforce. Provisioning flow.
- **Sandboxing MCP servers** — a third party wrote an MCP server. Do you trust it? Isolate it from agent state?
- **Capability advertisement** — server X says "I can tool A with args B". Schema validation.

**Status:** LIGHT (`architecture/02-layer4-control-plane.md` mentions tenant-scoped system prompt rendering and templates drive the tool set, but per-tenant MCP capability scoping is not contracted) / MISSING (MCP server discovery flow, sandboxing of MCP servers, capability schema validation).

**Lands in phase:** parallel watching. The MCP spec itself is moving — do not lock the design under the current MCP API; expect movement.

**External precedents:** Anthropic MCP spec (primary source). Few mature precedents — this is an open shape in the industry.

---

## M. Open-source community ops

Before publishing:

- **Security disclosure policy** — `SECURITY.md`, `security@your-domain`, GPG key, response SLA. Without it researchers file CVEs in public.
- **Code of Conduct** — Contributor Covenant template.
- **Maintainer access policy** — who can merge. Bus factor.
- **Phone-home telemetry for OSS** — yes / no / opt-in. Default-on is a red flag for customers.
- **Release cadence and LTS** — each minor supported for how long. Enterprise expectation is "N−2 versions receive security patches".
- **Third-party builds** — do downstream distributions get to redistribute? Nuances with BUSL / FSL.

**Status:** MISSING (no `SECURITY.md`, CoC, telemetry policy, release-cadence/LTS spec, redistribution policy in the architecture).

**Lands in phase:** non-blocker. Pre-OSS-publish checklist; resolve before the first public marketing of the OSS edition.

**External precedents:** CNCF security policy template, Kubernetes contributor ladder, Linux Foundation OSS Manager.

---

## Roadmap integration summary

| Category | Tier | Suggested phase placement | New doc artefact (future) |
|---|---|---|---|
| A. Multi-tenancy beyond per-session | 1 | Deeper Phase 5 (tenant = namespace) + Phase 6 tenant CRUD | ADR on tenant model |
| B. Identity beyond OIDC | 1 | Phase 6 (control plane auth) | ADR on auth surface; RBAC matrix in `architecture/02-*` |
| C. Compliance & audit immutability | 1 | Phase 4 + Phase 8 (immutability), residency = post Phase 10 | `architecture/07-security.md` expansion; ADR per framework |
| D. Determinism & session replay | 2 | Phase 7 + Phase 8 | Section in `architecture/05-*` and `architecture/10-*` |
| E. Cost attribution & metering | 1 | Proposed **Phase 6.5** | `architecture/10-observability.md` billing-primitives section |
| F. DR — RTO/RPO/backup/chaos | 1 | Rename Phase 10 → "HA + DR"; explicit RTO/RPO in acceptance | DR-runbook index |
| G. Supply chain security | 1 | Cross-cut; add CI policy in a Phase-0.5 follow-on | SBOM/SLSA section in `architecture/07-security.md` |
| H. Air-gap & corp networking | 2 | Dedicated future phase (customer-triggered) | Air-gap install guide |
| I. Operator UX day-2 | 2 | Cross-cut; grows per phase | Runbook catalogue; diagnostic-bundle spec |
| J. Versioning policy | 1 | New `architecture/11-versioning.md` | The file itself |
| K. Agentic-workload edge cases | 1 | Strengthen Phase 7 acceptance | Acceptance-criteria update only |
| L. MCP ecosystem | 2 | Parallel watching; revisit when MCP spec stabilises | None yet |
| M. Open-source community ops | 3 | Pre-OSS-publish checklist | `SECURITY.md`, `CODE_OF_CONDUCT.md`, release-policy doc |

**Tier 1** = critical for compliance / operations or for agentic-workload maturity at production scale.
**Tier 2** = enterprise-adoption blockers that depend on a specific customer trigger.
**Tier 3** = pre-public-launch hygiene.

---

## Out of scope (this document)

- No phase reordering or scope edit in `roadmap.md`.
- No new ADRs created — each Tier-1 gap is expected to graduate into its own ADR / phase-research doc when it is taken up.
- No code, no config, no CI changes.

## See also

- [`roadmap.md`](./roadmap.md) — 12 phases, invariants, failure-modes menu, rollback runbook
- [`antipatterns.md`](./antipatterns.md) — locked operational choices indexed by phase
- [`architecture/`](./architecture/) — layer specs (L4 → L1)
- [`adr/`](./adr/) — locked decisions
- [`research/`](./research/) — reference-architecture digests
