<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# Journey-suite findings

Defects the user-journey e2e suite surfaced by running FIRSTHAND against the
live fleet (Lima, runsc + runsc-fuse). Each was reproduced with a raw
create/exec against control, not inferred from code. The suite records each as
a strict `real_finding` xfail with the reproduction below, so the finding is
tracked, not hidden, and the run stays green on the invariants that DO hold.

Live-run baseline: 20 passed / 6 failed / 50 skipped / 24 xfailed. The six
non-xfail failures all trace to finding 1 (the storage-write plane) or the two
separate download/audit surfaces (E8, G3) noted at the end.

## 1. Storage-write plane does not round-trip (B1–B5, D5, G1)

A FUSE write to `/mnt/user-data/outputs/` reports success in-guest but the
object does not read back.

Two distinct causes, both reproduced firsthand:

- The in-guest mount client streams the object `Put` without the
  contract-required `declared_size_bytes`; the broker answers
  `400 INVALID_ARGUMENT {"reason_code":"INVALID_ARGUMENT","message":"declared_size_bytes required"}`.
  The contract makes the field required, so the gap is in the mount wrapper,
  not the broker.
- The fleet's filestore is a stand-in whose read/resolve plane is unimplemented:
  a read-back logs `ocufs: resolve "/x": brokerrpc: status 501 UNIMPLEMENTED
  "operation not implemented in this build"`.

Effect: a docx written by the agent cannot be downloaded — the outputs journey
does not complete on the fleet stand-in.

Reproduce:

```bash
# create a storage session (returns 201), then in-guest:
/bin/busybox sh -c 'echo HELLO > /mnt/user-data/outputs/x.txt; /bin/busybox cat /mnt/user-data/outputs/x.txt'
# read-back is empty; the guest rclone-mount log carries the 400 / 501 above.
```

The pure-Python OOXML validity keystone (`_assert_valid_docx`) stays a hard
pass; only the mount round-trip is xfail.

## 2. Concurrency-counter leak wedges the deployment (E7)

The `DimConcurrentSessions` counter is a write-only ratchet under the operator
kill-switch path: `RevokeAll` / `forceKillRow` call `ForceReleaseRow` (row →
Released) but never `ReleaseConcurrency`, so the counter is not decremented.
Separately, boot reconcile lists containers with `ListOptions{All: true}`, so an
Exited-but-present container matches its still-ACTIVE row and its slot is never
reclaimed. The counter climbs to the tier cap and every subsequent create is
refused `409`, even with zero live sessions.

Observed on the live stack: counter stuck at 64 against 3 live rows → all
creates 409. Same family as the boot-reconcile row-leak already fixed, one layer
deeper (the derived counter, not the row).

## 3. Egress is open to the public internet (G4)

The `ocu-fleet_ocu-mount-facing` network is `internal: false` — a NAT bridge
with a default route out — so a guest reaches arbitrary external hosts. The
single-hop invariant (guest reaches only its allow-listed edge) holds only for
in-cluster names via DNS scoping, not at L3.

Reproduce (repeatable, rc 0):

```bash
/bin/busybox nc -w5 1.1.1.1 443   # rc 0 — reached the public internet
```

The network must be `internal: true`. Ties the shared-mount-facing network-model
convergence issue.

## Control observability gaps the incidents exposed

These made the findings above hard to diagnose from outside; worth fixing
regardless:

- The create pipeline's host-side stages (handoff / mint / render / materialize)
  emit no audit event on failure and the failing stage name is logged nowhere,
  so a create refusal surfaces only as an opaque `409 "request refused"`. The
  audit-first invariant stops before these stages.
- `readCACertPEM` silently yields an empty string when `-ca-cert` is set but the
  file is unreadable, latching an empty CA at boot (every storage-scoped create
  then dies at the render stage). It should fail-closed at boot the way the
  signing key does — this is what a clean `down -v` + `up` raced into until the
  `harness-init` `depends_on` was added.
- A mountless (compute) create fails at a host-side stage with no audit event
  and no docker activity, so it too is an opaque 409.

## Deploy fixes applied (deploy/fleet)

Two real deployment fixes landed while unblocking the suite:

- `control` `depends_on` now waits on `harness-init` (it writes the CA the
  control plane latches at boot), so a clean `down -v` + `up` self-heals instead
  of racing into an empty-CA boot.
- `control` command gains `-guest-image-allow ocu-guest:assembled-demo` (the
  demo image carries the busybox an in-guest exec needs; the default assembled
  image is distroless). Without it, deny-by-default refused the demo image `400`.
