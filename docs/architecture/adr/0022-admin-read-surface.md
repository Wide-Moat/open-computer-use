<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-06-27
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
amends: []
compliance-impact: [SOC2-CC6.1, SOC2-CC7.2, ISO27001-A.8.15, NYDFS-500.06]
license-impact: none
threat-mitigation-link: ../06-threat-model.md
---

The read-only operator console reaches the Control plane through a server-side BFF over an all-GET read-API on the operator plane; the read-API holds operator-plane peer-cred identity, adds no control-plane state, projects the session registry plus a new metrics exporter, and has zero mutating reach. Audience: anyone wiring or auditing the `ocu-admin` console and its read path into `ocu-control`.

# ADR-0022: Admin read-surface — all-GET operator-plane read-API behind a BFF

## Status

`proposed`

## Context

The original v1 non-goal in `CLAUDE.md` reads "v1 ships zero admin UI". The owner reverses that for the read direction: a read-only operator console (`ocu-admin`) is in scope and opt-in, while a mutating admin console stays a non-goal. The Manifesto requires an ADR that cites the overridden principle ([`manifesto/04-non-goals.md`](../manifesto/04-non-goals.md), which already names the read-only console in scope). This ADR freezes the contract that reversal needs.

Three forces shape the contract. First, the operator plane is a host-owned 0700 Unix socket whose identity is `SO_PEERCRED` ([ADR-0004](0004-operator-authentication-substrate.md), [`components/02-control-operator-api.md`](../components/02-control-operator-api.md)); a browser cannot dial it. Second, the existing operator REST surface is POST/DELETE only — session lifecycle, kill-switch, denylist, quota — and the console must not gain any of that reach. Third, the data the console needs is not all on the frozen reservation row: the reservation instant, the activation instant, and the resource caps are durable enrichment recorded out of band of the frozen mutators (the `EnrichedLister` read seam), and average start time is a timing distribution, not a row field.

## Decision

We will add an all-GET read-API on the operator plane and reach it from the console through a server-side BFF. The browser never touches `ocu-control`; the BFF holds the UDS dial and the user-auth gate.

- **BFF as the sole browser-to-control hop.** The browser authenticates to the BFF with plain bcrypt + a first-party cookie ([NFR-SEC-84](../manifesto/02-nfrs.md)); the BFF dials the operator socket. The read-identity into the Control plane is the operator-plane peer-cred the operator plane already attests ([ADR-0004](0004-operator-authentication-substrate.md)) — the BFF runs as the operator-scoped peer. Not OIDC; canon auth is unchanged.
- **All-GET, zero mutating reach.** The read handlers are GET only and add no control-plane state — they project the existing reservation registry (through the optional `EnrichedLister` read seam) plus a new metrics exporter. An import-boundary test forbids a read handler from referencing destroy, revoke, denylist, or quota (mirrors the NFR-SEC-26 audience-to-route map test).
- **Endpoints.** `GET /v1alpha/sessions` (enriched list, `?include_released` adds RELEASED tombstones), `GET /v1alpha/sessions/{key}` (single or 404), `GET /v1alpha/deployment` (`{runtime_tier, runtime_provider}` — deployment-wide singletons, not per-row), `GET /metrics` (Prometheus: counts-by-state, create/destroy counters, a reserved→active start-duration histogram), and a future additive `GET /v1alpha/events` (`text/event-stream`) for live lifecycle deltas.
- **Read row.** `{key, owner{tenant, caller}, state, container_name?, caps?{cpu_cores, memory_bytes, pids_limit?}, reserved_at, active_at?}`. `state` is `reserved` (creating) / `active` (live) / `released` (destroyed). `reserved_at` is the instant the row was reserved and is always present; `active_at` and `caps` are the activation enrichment, absent until the row reaches `active`; `container_name` is bound after activation and absent until then. Average start time is derived from the `/metrics` reserved→active histogram (`active_at − reserved_at`), never from a single row. `runtime_tier` is the deployment-wide singleton, one value, never per-session.

This reverses the `CLAUDE.md` "zero admin UI" non-goal to: a read-only operator console is allowed in v1; a mutating admin console stays a non-goal — kill, scale, and denylist remain CLI (`occ`) + GitOps.

## Consequences

- Component [02](../components/02-control-operator-api.md): the operator/lifecycle ingress gains an all-GET read-surface alongside the POST/DELETE lifecycle and kill-switch routes; the operator-rest OpenAPI contract carries both. The read-surface adds no owned state — the reservation registry and denylist are still the sole mutable state, and no read handler mutates either.
- The console (`ocu-admin`) reaches Control only through the BFF; the import-boundary test makes "console cannot mutate" a compile-time property, not a runtime check.
- `/metrics` is Prometheus exposition (text), not an OpenAPI operation — it is documented as a sibling read path, scraped by the customer's Prometheus and viewed in Grafana. SSE `/v1alpha/events` is `text/event-stream`, noted as a future additive path, not frozen here.
- Accepted limitations of the read-only console: a **shared console password** (one bcrypt credential, not per-operator accounts); **no per-operator attribution** of a console read (the BFF dials as one operator peer, so a console view is not an audited per-human action — only the mutating CLI/SOAR path carries the NFR-SEC-45 per-actor audit); and **operator-sees-all** — the console projects every session in the deployment, with no per-operator scoping of the read.
- Negative: the BFF is a new server-side deployable with a session cookie and a UDS dial — new surface, but off the control plane and with no mutating reach.

## Alternatives considered

- **CLI-only, no console.** Rejected: polling the CLI per session reconstructs the same data the registry already holds, with no cross-session view. The console provides that view without adding new state.
- **Read-only console behind an all-GET BFF read-API (chosen).** A console with a live read view and zero mutating reach; the read row and `/metrics` cover the operator's view without exposing a write path.
- **Full mutating admin console.** Rejected: attack surface. A write path on the kill/denylist/quota routes is the surface the non-goal guards; mutation stays CLI + GitOps.

## Compliance impact

- `SOC2-CC6.1` / `NYDFS-500.06`: the console read-identity is the operator-plane peer-cred the operator plane already attests; the read-API adds no new privileged path and no mutating reach, so access control over the kill path is unchanged.
- `SOC2-CC7.2` / `ISO27001-A.8.15`: `/metrics` and the enriched session list are the operator-facing monitoring read; the per-actor audit obligation (NFR-SEC-45) is unchanged because the read path carries no mutation.

## License impact

None. The read-API is OCU code on the existing operator plane; Prometheus exposition and SSE are stock formats. The BFF and console (`ocu-admin`) are a separate opt-in deployable adding no bundled dependency to the Control plane.

## Threat mitigation

The read-surface adds no mutating reach to the operator plane — the import-boundary test (mirroring NFR-SEC-26) makes a read handler that reaches destroy/revoke/denylist/quota a build failure, so the P2 control-plane anchors in [`06-threat-model.md`](../06-threat-model.md) hold unchanged. The browser never touches `ocu-control`: the BFF is the single hop between them, holds the UDS dial, and dials as the operator-scoped peer the plane attests (NFR-SEC-76). The shared-password and operator-sees-all limitations are accepted trades of the read-only console, recorded here, not defects.

## Open questions

1. Per-operator console accounts and per-read attribution, lifting the shared-password and operator-sees-all limitations ([#308](https://github.com/Wide-Moat/open-computer-use/issues/308)).
2. Freezing the SSE `/v1alpha/events` delta schema when the live-view path hardens ([#309](https://github.com/Wide-Moat/open-computer-use/issues/309)).
