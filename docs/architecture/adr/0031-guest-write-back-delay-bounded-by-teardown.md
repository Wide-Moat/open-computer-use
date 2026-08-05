<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-08-05
owner: "@Wide-Moat/architects"
applies-to: next/v1
supersedes: []
superseded-by: null
amends: []
compliance-impact: []
license-impact: none
threat-mitigation-link: ../06-threat-model.md
---

# ADR-0031: Guest write-back delay bounded by the teardown window

## Status

Proposed.

## Context

A storage-scoped session mounts its filesystems inside the guest through a mount
process the guest agent starts as a boot-child. The mount holds a written file in
its local cache for a delay before writing it back to the broker. The delay is a
throughput choice: longer batches more, shorter uploads sooner.

Session teardown bounds that delay from above. The guest agent forwards SIGTERM to
its boot-child and then stops waiting for it after a fixed window, roughly two
seconds, which no host-side stop grace extends — the cap belongs to the agent. A
boot-child that drains inside the window exits cleanly; one that needs longer is
killed part-way through, and whatever the queue still held is gone. The agent
reports success either way, so the truncation raises nothing by itself.

The two values are therefore coupled, and nothing expressed the coupling. The
mount-config contract carried no write-back field at all, while the guest mount
implementation accepted one — so the delay every deployment ran on was the mount
implementation's own default, which exceeds the teardown window. The result is that
the most recently written file of a session does not reach storage when that session
is released.

The `Mount` object is `additionalProperties: false`, so the absent field was not an
omission a producer could route around: no component could send the value, and the
CI identity gate that pins each vendored copy to this contract kept it that way.

## Decision

The mount-config contract carries `vfs_write_back` as an OPTIONAL per-mount string.

A producer that sets it MUST choose a value below the guest teardown window, so a
file closed immediately before a release still has room to upload. A producer that
omits the key leaves the guest on its own default and accepts that a write made
close to release may not survive it.

The key stays outside `required`. A config that omits it is valid and renders
exactly as it did before the field existed, which is what lets each component adopt
the field independently of the others.

Zero is not a legal value. An object store is asynchronous by construction, and the
guest mount refuses a non-positive delay outright — emitting one stops the mount
coming up rather than merely flushing late, so producers validate positivity before
the value leaves the host.

## Consequences

Storage-scoped sessions lose less on release, bounded by how long an upload takes
rather than by how long the queue waits before starting one.

Write-back runs more often per session. The trade is deliberate: a sandbox session
writes few files, and losing the last one is worse than uploading it twice as
eagerly.

The bound is a cross-component invariant with no compile-time enforcement. The guest
teardown window lives outside this repository, so a producer's value can only be
justified against a measured window, and a change to either side has to re-measure
the other.

Read-after-write across contexts becomes visible sooner, since the same delay
governs when a written file appears to a reader that does not share the writer's
cache.

## Alternatives

Drain and wait at teardown, host-side: the session driver would signal the mount and
block until it finished before stopping the container. This is a guarantee rather
than a shrunken race, and it is rejected here only because the driver's substrate
surface is deliberately narrow and reaching into a running guest widens it. It
remains the stronger option if the narrow surface is ever revisited.

Widen the teardown window: not available. The window belongs to the guest agent and
is not configurable through any interface it exposes.

Leave the delay at the guest default and treat the loss as accepted behaviour: this
is the status quo, and it is rejected because the loss is silent — no error, no
non-zero exit, nothing an operator can alert on.
