# ADR-0007 — Old `docs/requirements/` superseded by `docs/future-architecture/`

- **Status:** Accepted (historical note)
- **Date:** 2026-05-17

## Context

The directory `docs/requirements/` previously held our k8s architecture and 6-phase roadmap (committed 2026-05-16). On 2026-05-17 we:

1. Renamed the directory to `docs/future-architecture/` via `git mv` (history preserved).
2. Rewrote the contents around the 4-layer model imported from `sandboxd/`.
3. Re-folded the old 6 phases into the new 10-phase roadmap.

## Decision

- `docs/requirements/` no longer exists. All references to it should point at `docs/future-architecture/`.
- The old `roadmap.md` content is **not lost** — its phases live on as new phases 1, 3, 5, 8 (see [`../roadmap.md`](../roadmap.md)).
- The old `k8s-architecture.md` 4-tier storage model lives on as [`../architecture/06-storage.md`](../architecture/06-storage.md).
- The `RuntimeBackend` protocol sketch lives on as [`../architecture/03-layer3-providers.md`](../architecture/03-layer3-providers.md)'s `SandboxProvider`.

## Why we didn't keep the old files as ADRs

- They were *plans*, not decisions. The new docs supersede them entirely.
- `git log --follow` preserves history; nothing is lost.
- Keeping zombie files invites stale advice.

## Verification

```bash
git log --follow docs/future-architecture/roadmap.md
git log --follow docs/future-architecture/architecture/06-storage.md
```

Both should show pre-rename commits on `docs/requirements/roadmap.md` and `docs/requirements/k8s-architecture.md`.
