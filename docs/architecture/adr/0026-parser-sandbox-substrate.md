<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-06-27
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
amends: ['0015-storage-decomposition-by-trust-plane.md']
compliance-impact: [SOC2-CC6.1, SOC2-CC6.6, ISO27001-A.8.26]
license-impact: none
threat-mitigation-link: ../06-threat-model.md
---

The isolation substrate for reading an untrusted artifact body is chosen per render location, not as one mechanism — for anyone wiring preview-render or editing the parser-sandbox boundary (component-08 render, component-04 ingest).

# ADR-0026: Parser-sandbox substrate, keyed on render location

## Status

`proposed` — amends [ADR-0015](0015-storage-decomposition-by-trust-plane.md), resolves its Open Question 1 and [component-08](../components/08-web-ui.md) Open Question 1.

## Context

[ADR-0015](0015-storage-decomposition-by-trust-plane.md) pinned the parser-sandbox as a capability-free plane — no signer, no key, never co-resident with the session-minting authority — fronting untrusted artifact bodies (preview-render, archive ingest), and deferred the *substrate* (process boundary versus in-language capability confinement) to [#218](https://github.com/Wide-Moat/open-computer-use/issues/218). The boundary's existence is canon; only its mechanism is open.

The deciding fact is what the Web UI renders today: nothing untrusted. `previewRender` is a gated-off stub, the SPA preview affordance is hidden, and the runtime dependency closure carries no render, parse, or sanitize library — the content byte path serves `Content-Disposition: inline` by resolved MIME and delegates decode to the browser. The only untrusted-body code that ships is the in-language ingest validator (magic-byte classify over a bounded prefix; archive validation over entry metadata that never inflates), already capability-free under three independent guards (a dependency-graph rule, a lint import-restriction, and an absence test with a recorded red-to-green proof). So the server holds zero full-body-parser attack surface, and a process sandbox built now would isolate a capability that does not exist.

The latent surface is concentrated in two formats a future preview could wire — SVG and OOXML (XLSX/DOCX) — across four vectors: external-entity expansion (XXE), server-side request forgery from body-named URLs (SSRF), entity-expansion denial of service, and active content (script in SVG or HTML). These are the threat rows P4-artifact-I3 and P4-artifact-E3; none is live, each must be closed before its format is ever rendered.

## Decision

We will select the parser-sandbox substrate by **render location**, because the location decides where the untrusted body actually executes — and pin a trigger that re-opens the choice when that location changes.

- **Ingest — in-language capability confinement.** The lexical validator stays server-side and in-process. It holds no signer, no key, no network capability, and reads only bounded metadata; the co-residency ADR-0015 names is already closed in-language and proven by the three-guard harness. A process fork adds an operational substrate for no blast-radius gain, so we do not fork it.
- **Body render — the browser.** Preview render runs in the browser, in a null-origin sandboxed iframe under a strict per-artifact content security policy (`default-src 'none'; script-src 'none'; object-src 'none'`; an iframe `sandbox` attribute carrying neither `allow-scripts` nor `allow-same-origin`). This is a distinct, stricter directive class from the SPA's `frame-ancestors` policy, which governs who frames the SPA, not what an artifact body may do. A null-origin frame cannot reach the embedder's origin, so it also closes the `postMessage` exfil leg without setting COOP.
- **Server-side heavy parser — process boundary, deferred behind a trigger.** Adopting any server-side full-body parser or rasterizer (a Node PDF renderer, a spreadsheet library, a headless office converter) flips the substrate to a separate OS process with a seccomp-bpf syscall filter, no network namespace, a memory and CPU cgroup, a non-root user, and a read-only rootfs. That adoption is itself a load-bearing decision and requires its own ADR; until a heavy parser is introduced, this tier is not built.

The boundary property (no signer, no key, no co-residency with the session-minter) is unchanged. This ADR decides only the substrate per location.

## Consequences

- Preview render, when wired in component-08, is a browser-CSP task, not a server-sandbox build: active content (SVG `<script>`, HTML inline JS) defaults to `attachment` disposition.
- The server keeps zero render-dependency CVE surface for as long as render stays browser-native; the trigger makes that a conscious, ADR-gated step rather than a silent dependency creep.
- Four hardening requirements land as NFR-SEC extensions (XXE-off default; renderer egress-block; entity-expansion limits; active-content disposition), each with a falsifiable CI check, mapped to P4-artifact-I3/E3. They gate the *first* render of a format, not running code.
- A future heavy-parser ADR inherits a clean precondition: the boundary property and the three hardening NFRs already hold, so it adds only the process substrate.

## Alternatives

- **Process boundary now (for ingest and a presumed future render).** Rejected: it isolates a server-side full-body parser that does not exist, so it mocks a need; it adds an operational substrate (process lifecycle, IPC, resource accounting) for zero current blast-radius reduction. The trigger captures the case where it does become load-bearing.
- **In-language confinement for body render too (sanitizer-only, e.g. a DOMPurify pass in the SPA origin).** Rejected as the boundary: a sanitizer is a denylist running in the SPA's own origin, so a bypass executes with SPA privileges. A null-origin sandboxed iframe is an allowlist boundary the sanitizer can complement but not replace.
- **One substrate for all three tiers.** Rejected: ingest, browser render, and a server rasterizer have different execution locations and different blast radii; a single mechanism either over-builds the cheap tiers or under-isolates the heavy one.
