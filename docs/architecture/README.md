---
status: stub
last-reviewed: 2026-05-24
owner: "@Wide-Moat/architects"
applies-to: next/v1
---

This directory will hold the canonical enterprise solution architecture for `next/v1`. Read [`MANIFESTO.md`](./MANIFESTO.md) before anything else.

## What's here

| File | Status | Purpose |
|---|---|---|
| [`MANIFESTO.md`](./MANIFESTO.md) | stub | Non-negotiables, NFRs by reference, governance. Read first. |
| [`glossary.md`](./glossary.md) | stub | Canonical terms (tenant, sandbox, session, agent, runtime, …). |
| [`PROCESS.md`](./PROCESS.md) | draft | 3-step playbooks for adding a component, ADR, NFR, dependency, or TBD. |
| `manifesto/` | empty | Expanded Manifesto sections — appear one at a time via PRs. |
| `components/` | empty | Per-component design contracts — appear one at a time. |
| `adr/` | partial | Contains `README.md` (index) and `0000-template.md`. ADRs appear on demand. |
| `diagrams/` | empty | Mermaid / D2 source files. |
| `compliance/` | empty | Per-framework mappings (SOC 2, ISO 27001, DORA, EU AI Act, GDPR, SR 11-7, HIPAA, PCI-DSS). |

## What's NOT here yet

Everything else. The tree grows one artifact per PR, after discussion. See [`PROCESS.md`](./PROCESS.md).

The in-progress materials at [`docs/future-architecture/`](../future-architecture/) remain a working buffer until coverage here reaches 100%; at that point a `SUPERSEDED.md` marker points back here and that directory becomes legacy.

## Reading order

1. [`MANIFESTO.md`](./MANIFESTO.md) — what the project is and what's non-negotiable.
2. [`glossary.md`](./glossary.md) — vocabulary.
3. [`PROCESS.md`](./PROCESS.md) — how to add new content.
4. The component diagram in `components/00-overview.md` (when it lands).
5. Specific ADRs and component specs as needed.
