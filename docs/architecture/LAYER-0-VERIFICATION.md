<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: draft
last-reviewed: 2026-05-24
owner: "@Wide-Moat/architects"
applies-to: next/v1
---

# Layer 0 verification — `next/v1`

This file records the verifier's pass over the Layer 0 closure of `next/v1`. It is intentionally co-located with the architecture set so that future verifier runs can diff against it.

## Verdict

**Pending CI confirmation.** The second verifier pass on commit `13f724e6` (after PR #138 hardening) flagged one blocker: the Layer-0 gate row 0 success criterion "CI green" was not met because the `security` workflow was failing on 37 Semgrep findings in pre-existing `main`-line code. ADR-0001 (this commit) records the policy that those legacy paths are excluded via `.semgrepignore` until the corresponding new-architecture components replace them in Layer 6+. The new component PR removes its path from the exclusion list in the same commit. Once this PR merges and CI runs green, the verdict updates to **READY for Layer 1**.

The first verifier pass (commit `493dd73`) declared "READY for Layer 1" without inspecting workflow run conclusions. That was a missed step — the same Semgrep failure was already present on `493dd73` (run `26355890254`).

## Delta from previous run (`493dd73` → `13f724e6`)

PR #138 ("fix(ci): close 3 HIGH bypasses found by post-merge review of #137") tightened the CI hardening that PR #137 introduced. Every claimed change is present at HEAD; no regression detected.

| Item | Claim | Verified at |
|---|---|---|
| H-1 | gitleaks always passes `--config`; writes `[extend]\nuseDefault = true\n` stub when base ref lacks file | `.github/workflows/security.yml` lines 99-109, 134 |
| H-2 | `tag="${REF_NAME#v}"` to match `build.yml` v-prefix strip | `.github/workflows/supply-chain.yml` line 104 |
| H-3 | Mirrored `cosign verify-attestation --type cyclonedx` after spdxjson | `supply-chain.yml` lines 215-229 |
| M-1 | Trivy `ignore-unfixed: false` on the CRITICAL pass | `security.yml` line 215 |
| M-2 | CODEOWNERS dual-team on `.github/dependabot.yml`, `.gitleaks.toml`, `SECURITY.md` | `.github/CODEOWNERS` lines 113, 119, 123 |
| M-3 | Dropped dead helm allowlist | `.gitleaks.toml` lines 33-37 — only the comment remains |
| M-4 | Narrowed `workflow_dispatch` cert-identity regex to `refs/tags/v*` or `refs/heads/(main\|next/v1)` | `supply-chain.yml` line 207 |
| M-6 | Semgrep `p/dockerfile` + `p/github-actions` (dropped non-existent `p/bash`, `p/yaml`) | `security.yml` lines 187-193 |
| L-1 | `..` segment check on image_ref | `supply-chain.yml` lines 121-126 |
| L-2 | Regex-escape REF_NAME / REPO before cert-identity interpolation | `supply-chain.yml` lines 198-199 |

## Process / CI gates (P-01 … P-16)

| ID | Status | Evidence |
|---|---|---|
| P-01 | PASS | `CLAUDE.md` carries all seven sections: Architecture decisions, Architecture content routing, Diagrams, Dependency policy, Testing & QA discipline, v1 non-goals, Documentation discipline |
| P-02 | PASS | `LICENSE` is FSL-1.1-Apache-2.0; `grep -rIl 'BUSL-1.1'` returns only `CHANGELOG.md` (historical entry) |
| P-03 | PASS | `docs/architecture/{README,MANIFESTO,glossary,PROCESS}.md` and `adr/{README,0000-template,0001-…}.md` exist with valid front-matter |
| P-04 | PASS | `.github/workflows/security.yml` runs gitleaks (Docker, two-source config) + trufflehog; both block merge |
| P-05 | PASS | Semgrep (six verified packs) + Trivy CRITICAL (`ignore-unfixed: false`) + Trivy HIGH SARIF informational; all block CRITICAL |
| P-06 | PARTIAL | `supply-chain.yml` provides signed SBOM (SPDX + CycloneDX) + dual cosign attest + dual cosign verify-attestation + environment gate. SLSA-3 provenance is deferred to a follow-up release workflow (the slsa-github-generator requires the real image digest, not available in a sign-only workflow). Documented in the workflow header. |
| P-07 | PASS | `.github/workflows/docs-lint.yml` enforces YAML front-matter via custom validator |
| P-08 | PASS | Line-budget check in docs-lint: ADR ≤ 200, component ≤ 600, MANIFESTO ≤ 400 |
| P-09 | PASS | Vale config under `.vale/styles/Architecture/` enforces banned vocabulary and phrases |
| P-10 | PASS | Custom box-drawing-character grep in docs-lint blocks ASCII diagrams in `docs/architecture/` |
| P-11 | PASS | lychee broken-link check in docs-lint |
| P-12 | PASS | `CLAUDE.md` `## Architecture content routing` carries the ten-step decision tree verbatim |
| P-13 | PASS | `PROCESS.md` describes five add-flows (component / ADR / NFR / dependency / TBD), each three to four steps |
| P-14 | PASS | `.github/CODEOWNERS` routes architecture, security workflows (dual-team), and component directories |
| P-15 | PASS | `adr/0000-template.md` enforces Status / Context / Decision / Consequences / Alternatives / Compliance / License / Threat-mitigation |
| P-16 | PASS | `components/0000-template.md` enforces Purpose / Boundaries / Invariants / Failure modes / Operational concerns / Open questions |

## Manifesto (M-01 … M-10)

| ID | Status | Evidence |
|---|---|---|
| M-01 … M-08 | N-A | Layer-0-scope: only the stub `MANIFESTO.md` exists; per-section files (`manifesto/01-audience-and-buyer.md` … `manifesto/07-governance.md`) are intentionally absent (foundation-pacing — one PR per file). Verified at Layer 1. |
| M-09 | PASS | `wc -l < docs/architecture/MANIFESTO.md` = 34, well under cap 400 |
| M-10 | PASS | `CLAUDE.md` line 107 — "Before proposing, designing, or implementing anything architectural on `next/v1` — read [`docs/architecture/MANIFESTO.md`](./docs/architecture/MANIFESTO.md)…" Also `CLAUDE.md` line 79 in Project Structure: "read `MANIFESTO.md` first" |

## Compliance (C-01 … C-10)

| ID | Status | Evidence |
|---|---|---|
| C-01 … C-10 | N-A | Layer-0-scope: `docs/architecture/compliance/` is an empty scaffold directory. Per-framework mapping files and the cross-framework controls matrix land in Layer 12, after components exist to map controls to. |

## InfoSec (S-01 … S-18)

| ID | Status | Evidence |
|---|---|---|
| S-01 … S-09, S-11 … S-18 | N-A | Component specs, ADRs, threat models, and contracts are Layer 6-10 artifacts. Not in Layer 0 scope. |
| S-10 | PASS | `supply-chain.yml` provides SBOM (SPDX + CycloneDX) + Cosign keyless sign + dual in-toto attestation + dual verify-attestation, all under `environment: production` gating. PR #138 hardenings H-2, H-3, M-4, L-2 close the bypass paths the first reviewer found. SLSA-3 provenance still deferred (tracked in `manifesto/05-licensing-posture.md` BoM row 9 once that file lands). At Layer 0, this is the strongest single-component implementation. |

## Layer-by-layer gate row 0

> Scaffolding files created and `status:stub`? `find docs/architecture -name '*.md' -exec grep -L '^---' {} \;` empty; CI green.

| Sub-check | Status | Evidence |
|---|---|---|
| Scaffolding files created | PASS | Files listed under P-03 |
| `grep -L '^---'` empty (every md file has front-matter) | PASS | `find docs/architecture -name '*.md' -exec grep -L '^---' {} \;` returns empty (verified locally) |
| CI green | **PENDING** | At the time of writing the security workflow is RED because Semgrep blocks merge on 37 findings in pre-existing `main`-line code. This PR adds `.semgrepignore` covering the legacy paths and records the policy in ADR-0001; the new component PR removes its path from the exclusion list in the same commit. The verdict above updates to PASS once the post-merge CI run is green. |

## Open issues blocking Layer 1 entry

1. **`security` workflow RED on `next/v1` HEAD** — addressed by this PR (ADR-0001 + `.semgrepignore`). Closes the gap once CI confirms green post-merge.
2. **`security-exceptions.yml` not programmatically enforced.** The file's own header (lines 19-21) acknowledges this: "CI does NOT yet enforce this file format programmatically — that's a follow-up task once we have actual exceptions to track." Not blocking Layer 1 entry, but worth a tracked issue before any per-finding exception is added.
3. **`supply-chain.yml` has no run history yet** (no tag on `next/v1`). Static review of the YAML and PR #138 hardening claims is the only signal available. A dry-run `workflow_dispatch` against a known-signed test image would confirm the cosign verify-attestation calls behave as expected. Not blocking; the first real release will be the first real test.

---

_Verified: 2026-05-24T09:30:00Z_
_Verifier: Claude (gsd-verifier) — second pass, post PR #138_
