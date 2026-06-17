<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-06-16
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
compliance-impact: [DORA-Art.28, EU-AI-Act-Art.15, NIST-SP-800-190]
license-impact: bundled-images
threat-mitigation-link: null
---

Fixes which image a sandbox runs and how a customer supplies their own — the axis canon names nowhere. Audience: anyone touching the Session sandbox rootfs, the control-plane admission path, or the Bill of Materials.

# ADR-0020: Sandbox image provisioning

## Status

`proposed` — **stub**. Context and the axis are fixed; the Decision is held open behind the owner rulings and open questions below. This ADR does not leave draft until those close.

## Context

[Component 05](../components/05-session-sandbox.md) and [ADR-0003](0003-sandbox-runtime-tier-ladder.md) specify the sandbox's runtime *security* and *isolation* exhaustively, but nothing specifies what **image** runs inside it or how a customer brings their own. The gap already leaks: NFR-FS-01/02 say "per-template", yet [`glossary.md`](../glossary.md) defines no `template` or `image` term (a one-source-of-truth break). A regulated buyer cannot adopt a fixed Ubuntu blob — their InfoSec mandates a hardened base, their workloads need different toolchains, and air-gap forbids any phone-home pull. "Bring your own image" is therefore a deal-requirement, not a convenience, and — unlike the agent loop ([04-non-goals](../manifesto/04-non-goals.md)) — a sandbox without an image cannot be a non-goal.

Two axes are in play and must not collapse into one: **image-fatness** (what is *in* the box) and the **runtime tier** (what *isolates* the box, fixed by [ADR-0003](0003-sandbox-runtime-tier-ladder.md) — runc/gVisor/microVM). ADR-0003 scopes itself to the runtime-tier ladder only; the image-fatness axis is this ADR's to fix. The [ADR-0012](0012-implementation-language.md) Rust static-PIE guest agent is not part of any image — it is part of the runtime, injected into every image at start, so an image carries only its userland. A bundled image is a release artifact carrying full CVE/SBOM/SLSA/RoI responsibility ([05-licensing-posture](../manifesto/05-licensing-posture.md)).

## Decision

**TBD.** The shape below is the owner's locked input; the load-bearing choices stay open (see Open questions). The ADR records the direction, not yet the decision.

Owner rulings (authoritative, not relitigated):

1. **One materialize path for every image.** There is no "OCU image" versus "BYO image" as two modes. An image (an OCU-prebuilt rung or a customer base) is given → OCU appends its runtime layers → OCU starts it. The agent is part of the runtime, never baked into an image; the prebuilt rungs are a shelf of convenient agent-less userlands that flow through the same pipe as a customer image. `FROM-min-base` as a second path is rejected — it reintroduced the duality.
2. **Injection is an appended OCI layer, not a bake or a synthetic file.** OCU appends the runtime as standard OCI layers over the base (`mutate.AppendLayers`-style), leaving the base image byte-unmutated — the common-tooling path, not a microVM/FUSE-specific synthetic-file scheme. Two static (no-libc) binaries ride these layers: the control agent (PID 1) and the `ocu-rclone-filestore` mount binary the agent starts; the mount binary needs `/dev/fuse` + `SYS_ADMIN` from the runtime.
3. **Image-fatness is a named axis orthogonal to the [ADR-0003](0003-sandbox-runtime-tier-ladder.md) runtime tier**, exposing a four-rung shelf — `min`, `medium` (+ userland, no browser), `high` (+ Chromium + CDP), `xhigh` (+ Claude Code CLI as an on-rootfs binary) — plus customer **BYO** through the identical path.
4. **All four rungs are bundled.** OCU builds, signs, and owns the CVE/SBOM/SLSA/RoI of every rung, including Chromium and the Claude Code CLI. There is no customer-overlay tier.
5. **Provenance is two-signature and uniform.** The image (OCU's or the customer's) carries its own signature OCU verifies; the agent carries OCU's signature, the same known binary every time. Admission verifies the two separately; the per-session provenance record, not a merged-rootfs signature, is the system of record.
6. **Injection is covered by a merge-blocking test matrix.** A CI gate proves agent-as-PID-1, mount-comes-up, base-image-byte-unmutated, two-signature verification, and the NFR-SEC-14 posture across substrate × image-rung × BYO; negative cells (unsigned base, missing `/dev/fuse`/`SYS_ADMIN`) must fail closed. Carried as an NFR row, not restated here.

Provisioning is a **role on the existing control plane** ([component 02](../components/02-control-operator-api.md)) — selection, admission validation, materialization — not a new component or deployable; it is the session-create step *before* the mount-config push. The runtime tier stays the deployment-wide knob, never a field on the image request.

## Consequences

- Positive: one materialize path means identical sandbox behaviour for a prebuilt rung and a customer base — no "worked on ours, broke on theirs" class; a hardened-base BYO path becomes expressible; the `min`/`medium` floor preserves the one-click solo shelf (a Chromium critical rebuilds `high`/`xhigh` only).
- Negative: bundling all four rungs puts OCU on the Chromium release cadence under the NFR-MAINT-01 patch SLA (≤7d for CVSS ≥9.0) — `xhigh` (CLI + Chromium) sets the release cadence and is the most expensive artifact to keep in SLA.
- Neutral: image provisioning consumes a pre-built OCI artifact read-only; OCU runs no session-time registry-push build (unlike the E2B template-manager model).
- Affects [component 02](../components/02-control-operator-api.md) (admission role), [component 05](../components/05-session-sandbox.md) (agent injected as PID 1, not image-borne), [05-licensing-posture](../manifesto/05-licensing-posture.md) (bundled BoM rows), [glossary.md](../glossary.md) (two new terms).
- Per-substrate boot/materialize mechanics (runc, gVisor, Firecracker, Docker-compose, Kubernetes) are an internal design detail of components 02/05, not ADR Decision text.

## Alternatives considered

- **Customer-overlay for high/xhigh** (OCU ships only the recipe) — rejected by owner ruling 4; OCU owns all CVE/RoI instead.
- **Two paths — agent baked in OCU images, injected only for BYO** — rejected: two behaviours is two bug surfaces ("worked on ours, broke on theirs"); the agent is part of the runtime and injected uniformly, so `FROM-min-base` as a second path is dropped.
- **Synthetic FUSE file for the agent** (microsandbox `init.krun`-style) — rejected as the primary mechanism: microVM/FUSE-centric, not common OCI tooling; the appended-OCI-layer path works on every substrate. May resurface as a microVM-tier option only.
- **Fold image-fatness into ADR-0003** — rejected: ADR-0003 selects the isolation boundary; conflating it with what-is-in-the-box collapses two independent axes.
- **Build-from-image at session time** (E2B template-manager) — rejected: OCU consumes a pre-built signed OCI artifact read-only; no session-time build surface.

## Compliance impact

- `DORA-Art.28`: each bundled rung carries a Register-of-Information row (the Chromium and Claude Code CLI fourth-party entries are OCU's once bundled).
- `EU-AI-Act-Art.15`: the image is part of the agent-execution boundary; SBOM/provenance per rung is the cybersecurity evidence.
- `NIST-SP-800-190` §3: image provenance, digest-pinning, and signature verification at admission.

## License impact

`min` and `medium` enter the Bill of Materials in [`05-licensing-posture.md`](../manifesto/05-licensing-posture.md) as bundled images; `high` (Chromium) and `xhigh` (Claude Code CLI) add bundled rows whose CVE/RoI OCU owns. The Claude Code CLI must clear the dependency licence gate before its row lands — not yet verified.

## Threat mitigation

Not threat-driven. The admission floor (image digest-pin, cosign-verify image and the injected agent against offline-bundle keys, agent-version-match on the injected runtime binary, arch match, runtime-tier match) attaches to NFR-SEC-16/18/38 once the Decision lands. The agent's presence is not checked on the image — OCU injects its own known binary every time.

## Open questions

1. Ship `medium` bundled, or bundle `min` only and treat `medium` as the first heavier rung? Bundling `medium` is an ongoing CVE commitment (CPython/OpenSSL/glibc churn under NFR-MAINT-01). — owner ruling needed, track issue.
2. BoM rows for `high`/`xhigh`/Chromium/Claude-Code-CLI do not exist in [`05-licensing-posture.md`](../manifesto/05-licensing-posture.md); the CLI's licence-gate result is unverified. — must land before this ADR cites them, track issue.
3. Agent injection on Firecracker writes into a freshly-built ext4 with no content-addressed layer identity; OCU signs the final template. Confirm the two-signature record (image + agent) covers the converted artifact. — track issue.
4. Does `image_tier`/`image_ref` ride the existing gateway→Control session-setup RPC as additive fields, or warrant a typed surface in [08-contracts](../08-contracts.md) §1? — confirm with contracts owner.
5. FIPS-140-3 variant per bundled rung (NFR-SEC-28) doubles the bundled evidence set (min/medium × default+FIPS). — release-pipeline scope decision, track issue.
6. The merge-blocking injection test-matrix gate (ruling 6) is not yet an NFR row in [`02-nfrs.md`](../manifesto/02-nfrs.md); the FUSE-under-gVisor and `/dev/fuse`-in-Firecracker mount cells need proving, not assuming. — land the NFR row + CI gate, track issue.
