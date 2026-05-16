# Requirements & Architecture Plans

This folder collects forward-looking design documents for Open Computer Use.
Unlike the rest of `docs/`, which describes how the project works **today**,
files here describe the architecture we are **planning to ship**.

## Why this folder exists

We want contributors and integrators to know where the project is going
before code lands. A new deployment target (Kubernetes), a new storage
model (object-store backed user data) or a new runtime contract
(`RuntimeBackend` abstraction) is far easier to review when the design is
written down up front, separate from any single PR.

A document in `requirements/` is a **commitment to a direction**, not a
finished spec. We expect each one to be revised as prototypes land. When a
plan is fully delivered the document either moves to the main `docs/` tree
(now describing reality) or is archived with a note pointing at the code.

## What's here

| File | Status | Topic |
|------|--------|-------|
| [`k8s-architecture.md`](k8s-architecture.md) | Draft | Target architecture for Kubernetes deployments — runtime backends, storage tiering, isolation tiers |
| [`roadmap.md`](roadmap.md) | Draft | Phased delivery plan, what each phase changes, what stays compatible |

## What this folder is **not**

- Not a backlog of bugs or feature requests — those go to GitHub Issues.
- Not user-facing documentation — see `docs/INSTALL.md`, `docs/FEATURES.md`,
  `docs/CLOUD.md` for that.
- Not authoritative until the corresponding code ships. If a doc here
  conflicts with the running system, the running system wins.

## How to contribute to a plan

1. Open a GitHub Discussion or Issue referencing the document.
2. PRs that change a plan should explain **what changed and why** in the
   PR description, not just diff the markdown.
3. Prototypes that validate (or invalidate) a plan are welcome — link the
   PR back to the document so the next reader sees the evidence.

The current Docker Compose deployment continues to be supported through
every phase below. No phase forces existing operators to migrate.
