# Project Instructions

## Branches and scope

This repository has two long-lived branches with different rules:

- **`main`** — the current PoC / production branch. Open WebUI integration, Docker Compose deployment, MCP orchestrator. The rules below apply. Quick fixes welcome.
- **`next/v1`** — the long-lived enterprise architecture branch. Same global rules apply, plus the additional architecture-work rules in the `# Architecture work on next/v1` section below. Designed for US/EU bank deployments; every architectural decision is recorded as an ADR.

When working on a feature branch, the rules of its base branch apply (e.g. `feat/foo` based on `next/v1` inherits the `next/v1` rules).

---

# Global rules (apply to every branch)

## Language

All code, comments, commit messages, PR titles, PR descriptions, documentation, and any text visible in the repository MUST be written in **English only**. No exceptions.

## License Headers

All new source files MUST include an SPDX license header as the first comment:

- Files in `skills/public/describe-image/` or `skills/public/sub-agent/`: `# SPDX-License-Identifier: MIT`
- Files in other `skills/` directories with their own LICENSE.txt: DO NOT add headers
- All other new files: `# SPDX-License-Identifier: FSL-1.1-Apache-2.0`

Always include: `# Copyright (c) 2025 Open Computer Use Contributors`

The FSL-1.1-Apache-2.0 license permits use, modification, forking, internal self-hosting, and redistribution. It prohibits offering the Software as a hosted or embedded service that competes with our paid version(s). Each release automatically converts to Apache-2.0 two years after publication.

## Building the Docker image

Always build with `--platform linux/amd64`:

```bash
docker build --platform linux/amd64 -t open-computer-use:latest .
```

## Testing

After building the image or changing `Dockerfile`, `package.json`, `requirements.txt`, skills, or npm configuration — run:

```bash
./tests/test-docker-image.sh [image-name]
./tests/test-no-corporate.sh
./tests/test-project-structure.sh
```

Default image: `open-computer-use:latest`.

These verify: npm packages (CommonJS `require()`, ESM `import`), CLI tools (mmdc, tsc, tsx, claude), Python packages, Playwright, html2pptx, volume size (`/home/assistant/` < 1MB), file permissions, project structure, no corporate references.

## npm packages layout

Packages are installed outside `/home/assistant` (volume mount point) to avoid duplication per container:

| Path | Contents | Storage |
|------|----------|---------|
| `/home/node_modules/` | Libraries (react, pptxgenjs, pdf-lib...) | Image layer (shared) |
| `/usr/local/lib/node_modules_global/` | CLI tools (mmdc, tsc, tsx, claude) | Image layer (shared) |
| `/home/assistant/node_modules/` | User-installed packages (`npm install`) | Volume (per-container) |

Node.js uses parent-directory resolution: if a package isn't found in `/home/assistant/node_modules`, it looks in `/home/node_modules`.

## Project structure

| Path | Contents |
|---|---|
| `Dockerfile` | Sandbox container image (Ubuntu 24.04, Python, Node.js, CDP, ttyd) |
| `computer-use-server/` | MCP orchestrator (FastAPI, Docker management, CDP/terminal proxy) |
| `openwebui/` | Open WebUI integration (tools, functions, patches) |
| `settings-wrapper/` | Settings sidecar service |
| `skills/` | AI skills (pptx, xlsx, docx, pdf, sub-agent, playwright-cli, ...) |
| `helm/` | Helm chart for Kubernetes deployment |
| `vendor/` | Vendored third-party binaries (e.g. `extract-text`) |
| `tests/` | Test scripts |
| `docs/` | Project documentation |
| `docs/architecture/` | Canonical enterprise architecture (`next/v1` only); read `MANIFESTO.md` first |
| `docs/future-architecture/` | In-progress architecture buffer; superseded by `docs/architecture/` over time |
| `docker-compose.yml` | Computer Use Server |
| `docker-compose.webui.yml` | Open WebUI + PostgreSQL (connects to server via `host.docker.internal`) |

## Versioning (current `main`-line scheme)

Format: `v0.9.X.Y` — the first three segments (`0.9.X`) track the **Open WebUI** base version this project is built on. Never bump them independently.

- **Patch release** (`Y+1`): bug fixes, security patches, dependency bumps, test additions → e.g. `v0.9.5.0` → `v0.9.5.1`
- **Minor release** (`X+1`, reset `Y=0`): new features, new tools, significant changes → only when Open WebUI base version also bumps

To release:

1. Update `CHANGELOG.md` with the new version heading.
2. Commit: `chore: release vX.X.X.X`.
3. Tag: `git tag vX.X.X.X && git push origin main --tags`.

The `next/v1` branch will define its own versioning scheme in an ADR; until then it carries no tagged releases.

---

# Architecture work on `next/v1`

The sections below apply to all architectural work on the `next/v1` branch (the long-lived enterprise architecture branch). They do not constrain quick fixes or PoC work on `main`.

## Architecture decisions (next/v1)

Before proposing, designing, or implementing anything architectural on `next/v1` — read [`docs/architecture/MANIFESTO.md`](./docs/architecture/MANIFESTO.md). The Manifesto sets the non-negotiables (enterprise compliance posture, build-vs-buy rules, starter-mode limitations, licensing). Any deviation requires a new ADR under [`docs/architecture/adr/`](./docs/architecture/adr/) that explicitly cites the principle being overridden and why.

Component-level work: read the relevant ADRs under [`docs/architecture/adr/`](./docs/architecture/adr/) before editing the component's spec or code. Use [`docs/architecture/PROCESS.md`](./docs/architecture/PROCESS.md) when adding new components, ADRs, NFRs, dependencies, or TBD-stubs.

## Architecture content routing

Before writing any new architectural content, walk this tree. If you cannot place a paragraph in 30 seconds using these steps, the paragraph is not yet a decision — leave it as an Open Question (step 6), not as prose.

1. **Is it a non-negotiable rule that every future decision must respect?** → `MANIFESTO.md` §03 (Principles). Add anti-example. One line for rationale. No implementation detail. STOP.
2. **Else, is it a measurable cross-cutting requirement (latency, RTO, isolation, audit retention)?** → `manifesto/02-nfrs.md` as a scenario with a measurable target. STOP.
3. **Else, is it a load-bearing decision that (a) is hard to reverse, OR (b) crosses ≥ 2 components, OR (c) closes a debated option?** → New ADR in `adr/NNNN-slug.md` with Status / Context / Decision / Consequences / Alternatives. Link from every affected component spec. STOP.
4. **Else, is it an internal design detail of exactly one existing component?** → That component's spec under `components/<NN>-<name>.md`. Inside the fixed section order. STOP.
5. **Else, is it a term used in ≥ 2 documents (or one ambiguous term)?** → `glossary.md`. Inline use links to the glossary entry. STOP.
6. **Else, is it a question we cannot yet answer?** → `## Open questions` section of the nearest owning doc, capped at 5 entries; each entry MUST link a GitHub issue. If the cap is exceeded, escalate the oldest to an ADR or close it. STOP.
7. **Else, is it content lifted from `docs/future-architecture/` that is still valid?** → Re-evaluate, then rewrite in the target location (steps 1-5) with `supersedes: docs/future-architecture/<file>` in front-matter. Leave a redirect stub in the original. STOP.
8. **Else, is it speculation about something we may build later?** → DO NOT WRITE prose. Create a `tbd` stub: a single line + tracking issue. STOP.
9. **Else, is it a how-to / runbook?** → `docs/operating/` only; never inside architecture docs. STOP.
10. **Else** → it does not belong in the architecture set. Reject or route to README / CHANGELOG.

## Diagrams

- **Mermaid first.** All diagrams under `docs/architecture/` are Mermaid source files (`.mmd`) committed alongside the doc that references them. Inline mermaid blocks allowed only for diagrams ≤ 15 lines.
- **D2 or PlantUML** only when Mermaid lacks the primitive (e.g. complex sequence with timing constraints).
- **ASCII diagrams are forbidden** in `docs/architecture/`. They don't render in browsers, can't be linted for broken references, and signal AI-style ad-hoc artwork. Existing ASCII art in `docs/future-architecture/` is converted to Mermaid during migration, not lifted.
- **PNG / JPG / SVG** only for: external-UI screenshots, customer-supplied branding, scanned analog artifacts. Never for our own diagrams (we lose versionability and diff-ability).
- **C4 model levels:** Context → Container → Component. Code-level diagrams (level 4) only when needed, normally inside the relevant component spec or ADR.
- **Trust-zone diagrams** live in a single canonical place; other docs link to it.

## Dependency policy

For every dependency added to the project (build, runtime, or dev):

1. **License gate.** Must be: Apache-2.0, MIT, BSD-2/3, MPL-2.0, LGPL-2.1 (as separate service), PostgreSQL. Reject: AGPL (any), BSL, BUSL (other than past-version of our own), SSPL, CC-NC, commercial-only-source.
2. **Supply-chain gate.** Must have: SBOM published OR reproducible build OR signed releases OR cosign-attested artifacts. Reject: sole-maintainer npm/PyPI packages with no provenance.
3. **Bundled vs not-bundled.** Recorded in the Bill of Materials in `manifesto/05-licensing-posture.md`:
   - **Bundled** = we ship the binary/image/lib as part of our release. Carries full responsibility: vuln-scanning, version pinning, CVE response.
   - **Not bundled** = customer provides via standard API (Keycloak, OpenBao, Splunk, customer KMS). We document the integration contract; customer owns the lifecycle.
4. **Enterprise-grade requirement.** When in doubt between a heavier, vendor-backed, audited tool and a lighter, sole-maintainer one — pick the heavier. The platform targets regulated enterprises; lightweight-but-undocumented loses every InfoSec review.
5. **Reject reasons are first-class.** If we reject something, record it in the rejection table in `manifesto/05-licensing-posture.md` so future contributors don't re-propose it.

## Testing & QA discipline (next/v1)

Foundation rule: every gate ships in the Layer 0 commits of `next/v1`, before any architectural content. "We'll add tests later" never happens at this stage.

Top three CI gates a regulated-enterprise auditor opens first — without these the repo is not auditable at all:

1. **Secrets scan blocks merge.** gitleaks + trufflehog on every commit + pre-receive hook. Any hit = red.
2. **SAST/SCA CRITICAL blocks merge.** Semgrep + CodeQL HIGH/CRITICAL on changed files; Trivy/Grype CRITICAL on deps and container images. HIGH allowed for 14 days with a tracked exception file.
3. **Signed SBOM + SLSA L3 provenance** required for every release artifact. Syft → SPDX, Cosign-signed; CI fails if missing.

Full CI rule set (lands in the CI-gates PR of Layer 0): IaC scan (Checkov + tfsec), Cosign signature verification on dep pulls, license scan against the allow-list in `manifesto/05-licensing-posture.md`, unit-test patch coverage ≥ 80%, mutation testing ≥ 60% on auth/sandbox/audit/broker packages, property-based tests on every parser/scheduler/policy engine, k6 perf regression < 10%, Playwright golden-path E2E on every merge, Promptfoo red-team subset per PR (Garak + PyRIT nightly), Threagile threat-model re-runs on DFD-bearing PRs, conventional commits, signed commits, CODEOWNERS approval, branch-protection bypass = block.

Documentation linter (same CI): markdownlint, vale (banned vocab + phrases), lychee (broken links), wc-line-budget (ADR ≤ 200, component spec ≤ 600, MANIFESTO ≤ 400, README sections ≤ one screen), ai-slop-detector (banned phrases and AI tells), front-matter validator (`status`, `last-reviewed`, `owner`, `applies-to` mandatory), staleness warning (`last-reviewed` > 180 days), ASCII-diagram detector in `docs/architecture/`.

Code-review discipline: CODEOWNERS routes every PR; "done definition" per PR includes tests added/updated, docs updated in the same PR, CHANGELOG entry, status front-matter updated, ADR linked if decision-bearing. Reviewers run the content-routing tree above on every architecture doc.

## v1 non-goals (locked early)

The following are explicit non-goals for `next/v1` GA. Each gets a clean abstraction boundary so the contract is ready when we add them later, but the implementation is out of scope:

- **Skill registry.** v1 ships zero default skills bundled. Components include a `SkillProvider` abstraction at `status: tbd`. Skills load from an external registry the customer provides. Anti-pattern: invent a half-baked skill format now and lock customers into it.
- **Hosted models and the agent loop.** OCU does not host, select, or proxy an LLM, and does not run the agent loop. OCU is an MCP server plus a sandbox executor; the loop and the model choice live in the calling client (a Wide-Moat sibling component such as LiteLLM / Open WebUI / n8n, or any MCP caller). If a sandbox tool needs an LLM, it reaches it as one allow-listed egress endpoint, governed by the same Egress trust-edge, broker, and audit path as any other endpoint — not through an OCU model abstraction.
- **Admin web UI.** v1 ships zero admin UI. CLI (`occ`) + GitOps + Grafana for ops. Every UI is new attack surface, auth burden, and accessibility cost. v2 may add a read-only operator console after CLI is feature-complete and customers request it.
- **SaaS offered by us.** Our license (FSL-1.1-Apache-2.0) forbids competing hosted services without permission. We ship self-hostable software only.

## Documentation discipline (applies to all docs)

Applies to every file under `docs/`, every `README.md`, every ADR.

- Front-matter required: `status`, `last-reviewed` (YYYY-MM-DD), `owner`, `applies-to`. CI fails without all four.
- First line after front-matter: one sentence stating purpose and audience. No preamble.
- Diátaxis (tutorial / how-to / reference / explanation) governs `docs/getting-started/`, `docs/operating/`, `docs/contributing/`. It does NOT govern `docs/architecture/`, `docs/adr/`, `docs/compliance/` — those are engineering artifacts with their own templates.
- ADR: Nygard format (Context / Decision / Consequences / Alternatives / Status). One decision per file. Present tense ("We will…"). Hard cap 200 lines.
- Component spec: fixed sections in order — Purpose, Boundaries, Invariants, Failure modes, Operational concerns, Open questions. Hard cap 600 lines.
- MANIFESTO: principles only. Each principle gets one rationale line and one anti-example. Hard cap 400 lines. No implementation details — they live in component specs.
- Compliance mapping: table only (control → component → evidence link). No narrative.
- Show before tell: every concept doc has a runnable example, command, or diagram above the first prose explanation. ADRs exempt.
- Why over what: prose explains rationale and trade-offs. The code shows the what. If a paragraph paraphrases the code, delete it.
- One source of truth: each fact lives in one file; others link. Glossary terms defined only in `docs/architecture/glossary.md`.
- Diagrams as source (Mermaid / PlantUML). No `.png` in `docs/architecture/` except external-UI screenshots.
- No forward references. Don't link to docs that don't exist. Don't write "covered later." If it belongs here, write it; otherwise drop it.
- No TOC in docs ≤ 500 lines. No Conclusion / Summary section in docs < 1000 lines. Headings already navigate.
- One outbound link cap: ≤ 3 cross-doc links per H2 section. More links = the doc is fragmented; consolidate.
- Tables when ≥ 3 parallel items have ≥ 2 attributes. Lists for sequences only. Prose for argument.
- Banned vocabulary: "comprehensive", "robust", "seamless", "powerful", "best-in-class", "industry-leading", "modern", "elegant", "battle-tested". State the specific property instead (e.g. "supports transactional DDL", not "robust").
- Banned phrases: "It's worth noting that…", "It is important to…", "In this section…", "This document will…", "Going forward…", "Please note…", "Happy coding", "delve".
- No restating project scope. Reader arrived via README; assume context. No file begins with "open-computer-use is…".
- No stub headings. Write the content or remove the heading.
- No marketing tone. State requirements, constraints, trade-offs, and decisions. No adjectives without a measurable referent.
- Examples beat lists of features. If a feature list is necessary, every item must link to where it's specified or demonstrated.
- Docs and code change in the same PR. CODEOWNERS routes doc review by `applies-to`. Drifted docs (last-reviewed > 180 days) flagged in CI.
- Step-by-step copy-paste for user-facing procedures: "do this, then this, verify". No scattered KNOWN-BUGS-style fragments.
- English only. No emoji unless the user explicitly requests it.
- When in doubt, delete. Shorter is better if no fact is lost.

### Slop patterns (structural, not just vocabulary)

The banned-vocabulary list catches words. These catch the structure that reads as AI-generated even when every word is clean. Reviewers and the doc-slop agent (`.claude/agents/doc-slop-reviewer.md`) check these on every new architecture doc.

- **Headings name content, never frame it.** A heading states what the section *is*, as a noun phrase. Never "Why this is not X", "Understanding Y", "A note on Z", "How we think about W". These are conversational tells.
  - Bad: `## Why this layer is not the trust-zone layer` → Good: `## Context vs trust zone`
  - Bad: `## Understanding the broker` → Good: `## Credential broker`
- **The purpose line states purpose once.** The mandated first sentence says what the doc is and for whom — once. Do not follow it with a second sentence that restates the audience in other words.
  - Bad: "Cuts the domain into contexts … the call made before any component exists. Audience is anyone deciding what we build vs integrate." (the tail restates the opening)
  - Good: "Cuts the domain into bounded contexts and classifies each — the buy-vs-build call. Audience: anyone choosing what to build and what to integrate."
- **No throat-clearing tails.** Drop "… before any component exists", "… in the modern landscape", "… as we move forward" — grand-sounding clauses that add no fact.
- **No hedge-restatement.** Don't say a thing, then say it again softer: "X. That is to say, X." Cut the second clause.
- **No rule-of-three padding.** "secure, scalable, and resilient" — adjective triples without a measurable referent are the loudest tell. Name one specific property or none.
- **No "it's important to note / worth mentioning" even reworded.** If it's important, state it as a plain claim. If it isn't, cut it.
- **Symmetry for its own sake is a smell.** Every section the same length, every list exactly three items, every paragraph the same shape — real docs are lumpy because content is lumpy. Don't pad a thin section to match a thick one.
- **No process-narration.** The doc, the commit message, and the PR description record what is true, never how you arrived at it. Banned: "Reconstructed X, then fixed Y", "We researched / dug into / verified from the binary and found …", "After analysing …, we decided …", "established this session". The reader does not care that an agent read a binary — state the resulting fact. Bad: "Reconstructed Anthropic's channel design from the binary, then fixed our Layer 3." Good: "The control channel stays off the guest network; the host dials in."
- **No view-restatement.** A fact that already lives in a table, a diagram label, or another section is stated once. Prose next to a table adds only what the table can't carry — never "as the table shows" followed by the table's content. A diagram labels; it does not explain — push the "why" to the section, not the node.
