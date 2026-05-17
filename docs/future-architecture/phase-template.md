# Phase-N template

> Copy this file twice per phase: once as `phase-N-research.md` (Step 3 of the cadence), once as `phase-N-plan.md` (Step 5). Leave this template untouched.

## `phase-N-research.md` skeleton

```markdown
# Phase N research — <short title>

**Status:** draft → in-review → signed-off
**Owner:** <name>
**Started:** YYYY-MM-DD
**Signed-off:** YYYY-MM-DD

## Context

What this phase delivers per [roadmap.md](./roadmap.md#phase-N) in one paragraph. Why now.

## Antipatterns scanned

List every entry from [`antipatterns.md`](./antipatterns.md) phase-index row for Phase N. For each: "our choice still holds" OR "this phase needs to amend it because…". Don't skip any.

## Options considered

For each meaningful decision in this phase:

### Decision X — <what>

| Option | Pro | Con | Cost |
|---|---|---|---|
| A | … | … | … |
| B | … | … | … |

**Recommendation:** A. Because …

(One block per meaningful decision. Targets: ≥ 1, typically 2–5.)

## Reference repos read

- `research/NN-foo.md` — what we took from it.
- (additional external sources, if any)

## Success metrics

How will we know the phase shipped correctly? Concrete:
- Latency: p99 < X ms on workload Y.
- Test coverage: integration test Z passes against both PoC and target backend.
- Observability: metric `foo_total` appears in dashboards.
- No regression: existing tests `…/test_mcp_*.py` continue to pass.

## Rollback plan

If this phase causes a production incident:
- Step 1: <flip flag / pin previous digest / re-point reverse-proxy>.
- Step 2: <verify rollback effect via signal X>.
- Estimated rollback time: < N minutes.

## Open questions

Anything that needs sign-off discussion before we proceed to `phase-N-plan.md`.

## Sign-off

- [ ] Owner reviewed.
- [ ] Antipattern scan complete.
- [ ] Rollback plan validated (dry-run if non-trivial).
- [ ] Success metrics agreed.
```

## `phase-N-plan.md` skeleton

```markdown
# Phase N plan — <short title>

**Based on:** `phase-N-research.md` (signed-off YYYY-MM-DD)
**Branch:** `dev/future-architecture/phase-N-<topic>`

## Day-1 checklist

What touches code or config on the first commit. Concrete:
- File X: refactor function Y into module Z (no behavior change).
- File X: introduce flag `SANDBOX_PROVIDER` default `<old behavior>`.
- Tests: add `tests/integration/test_phase-N_*.py`.

## Atomic tasks

(Output of `gsd-plan-phase`. Each task = one commit on the phase branch.)

| # | Task | Files | Test | Reversibility |
|---|---|---|---|---|
| 1 | … | … | … | … |
| 2 | … | … | … | … |

## Acceptance gate

Acceptance criteria from `roadmap.md` Phase N, repeated here verbatim. Tick each as it lands.

- [ ] …
- [ ] …
- [ ] Compose PoC still works (run from clean clone, follow `docs/INSTALL.md`).
- [ ] Antipatterns from Phase-N row of `antipatterns.md` still respected.

## Phase retro

Once merged, answer in 5 lines:
- What was harder than expected?
- What was easier?
- Did this phase reveal a flaw in an earlier phase? (If yes → file follow-up per [roadmap.md § Failure modes](./roadmap.md#failure-modes--cross-phase-retros).)
- Antipatterns to add to `antipatterns.md`?
- One-line lesson for the next phase.
```

## Why a template

- Forces the **antipattern scan** to happen before code (Step 1 of cadence is not skippable).
- Forces explicit **rollback plan** before merge (Phase 6 dual-run lesson).
- Forces **success metrics** before code (Phase 10 "measure first" invariant).
- Forces a **retro** so cross-phase mistakes surface fast.

The skeleton is intentionally short — fill it in 1–2 hours, not 1–2 days.
