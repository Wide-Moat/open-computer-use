<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: accepted
last-reviewed: 2026-05-24
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
compliance-impact: []
license-impact: none
threat-mitigation-link: null
---

The Layer 0 CI gates run against every PR on `next/v1`, but `main`-line legacy code on this branch fails them. This ADR records how we keep the gates on without rewriting code that v1 GA does not ship.

# ADR-0001: Layer 0 gate legacy exclusion policy

## Status

`accepted`

## Context

`next/v1` was branched from `main` to carry the existing PoC (sandbox `Dockerfile`, `computer-use-server/` FastAPI, `openwebui/`, `settings-wrapper/`, `cron/`, bundled skills) so the branch stays runnable while the enterprise architecture is designed. The Layer 0 SAST gate (`p/security-audit`, `p/owasp-top-ten`, `p/python`, `p/javascript`, `p/dockerfile`, `p/github-actions`) found 37 blocking issues in that legacy code on its first run: root containers, wildcard CORS, md5 hash use, stdlib XML parsing, dynamic urllib, etc.

None of that code ships in v1 GA. Every legacy area is replaced from scratch by a new component under `docs/architecture/components/` in Layer 6+ (Sandbox Runtime, Control Plane, Audit Pipeline, Egress Proxy, …). Rewriting the legacy now means polishing code we are about to delete.

The gate itself is correct and must remain blocking. The question is which paths it covers.

## Decision

The Layer 0 SAST gate runs against every path in the repository except those listed in `.semgrepignore`. That file enumerates the `main`-line legacy paths slated for replacement, with a header that names the responsible new-architecture component for each entry. Every new-architecture PR that introduces a component covering one of those areas removes the corresponding `.semgrepignore` line in the same commit. CI must pass without the exclusion before the PR can merge.

## Consequences

- Positive: Layer 0 gates stay green on `next/v1` HEAD; the verifier's "CI green" criterion is satisfied without dead-code refactoring.
- Positive: every new component inherits the full SAST gate by default. The exclusion list shrinks monotonically — additions require this ADR's amendment.
- Positive: the legacy debt is auditable in one file rather than scattered across `# nosemgrep` comments.
- Negative: a legacy finding could mask a related issue in new code that imports the legacy path. Mitigated by the rule that new components never import legacy modules (enforced by component-boundary review).
- Negative: `.semgrepignore` is a coarse tool — excluding `computer-use-server/` excludes every rule, not just the failing ones. Acceptable because the directory dies in Layer 6+.

## Alternatives considered

- **Baseline cleanup PR.** Fix the 37 findings in legacy code before continuing. Rejected: the code is scheduled for full rewrite; fixing it now spends review time on artifacts we throw away. The legacy code is not patched on `next/v1`; it is replaced from scratch in Layer 6+ per the architecture plan.
- **Per-rule exception file** (`.semgrep-exceptions.yaml` with finding hashes). Rejected: gives the illusion of per-finding scrutiny while in practice rubber-stamping every legacy hit. The directory-level exclusion is more honest about what we are doing.
- **Lower the gate to `WARN`.** Rejected: removes the gate for new code too. The whole point of Layer 0 is that new components must pass on creation.
- **Delete the legacy code from `next/v1` now.** Rejected: the branch must stay runnable for early-stage demos and contract-shape experiments until Layer 6+ components land.

## Compliance impact

None for now. When the first compliance-mapping ADR lands (Layer 12), this exclusion list is referenced as the scope-boundary statement: SOC 2 / ISO 27001 controls apply to non-excluded paths.

## License impact

None.

## Threat mitigation

None directly. The legacy code's threats (root containers, XXE, SSRF via `urllib`) are addressed by replacement, not by SAST suppression. The new-component-must-remove-its-path rule keeps that promise auditable.

## Amendments

### 2026-05-24 — initial exclusion-list completion

The first version of `.semgrepignore` shipped in commit `709db53` missed three legacy areas that the SAST gate scans:

- `.github/workflows/release-chart.yml` — `main`-line Helm release workflow with a pre-existing `run-shell-injection` finding on the `gh release create` step. Replaced when the supply-chain.yml pattern is extended to chart artifacts in Layer 6+.
- `skills/examples/` — bundled skill examples carrying the same `defusedxml` gaps as `skills/public/`. v1 GA ships zero skills per `manifesto/04-non-goals.md`; both directories die together.
- `tests/` — top-level PoC test tree using stdlib `xml.etree`. New components ship their own tests under each component's directory; this tree dies with the code it tests.

Discovered by the third verifier pass on commit `709db53`. The amendment adds them under the same policy with no change to the decision or alternatives.
