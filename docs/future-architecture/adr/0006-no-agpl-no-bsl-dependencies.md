<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# ADR-0006 — No AGPL, no BSL in direct dependencies

- **Status:** Accepted
- **Date:** 2026-05-17

## Context

Our project is BUSL-1.1 (with MIT for select skills, per `CLAUDE.md`). Several adjacent projects in this space carry licenses that would either contaminate our codebase or restrict our ability to ship.

## Decision

**Disallowed in direct dependencies:**
- **GPL v2 / v3** — copyleft, contaminates linked code.
- **AGPL v3** — strongest copyleft, contaminates even SaaS use.
- **BSL (Business Source License)** — not OSI-open-source; HashiCorp Nomad post-acquisition.

**Allowed:** Apache 2.0, MIT, BSD-2/3, MPL 2.0, LGPL 2.1+ (link only).

**Implications:**
- **Daytona** (AGPL v3) — never adopted, even for reference patterns we'd copy code from.
- **Nomad** (BSL) — no Nomad provider, no Nomad client in our stack. E2B's Nomad-specific code is *reference-only*.

## Rationale

- BUSL-1.1 + AGPL = legal headache for downstream users.
- BSL isn't OSI-open-source; building on it limits our distribution flexibility.
- Strict license hygiene now is cheaper than disentangling later.

## Consequences

- Every new direct dependency PR must include a license check.
- CI should enforce a license-allowlist scan (Phase 5+ deliverable).
- Some convenience tools are off the table; alternatives must be found (e.g., for Nomad-style scheduling we'd build on k8s instead).

## Alternatives

- **Allow AGPL via "mere aggregation" loophole** — rejected. Legal risk too high; the loophole is contested.
- **Switch project license to AGPL** — rejected. Out of scope of this ADR.
