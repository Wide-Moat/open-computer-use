---
status: proposed
last-reviewed: 2026-08-09
owner: architecture
applies-to: contracts/mcp/mcp-key-set.schema.json, component-01, component-02
---

Gives the config plane a way to say "authenticate nobody", so revoking the last
active key reaches a live gateway. Audience: anyone touching the key-set wire or
the gateway's refresh path.

## Context

Revoking the **last** active mcp-key leaves that key valid on a running gateway
until it restarts. NFR-SEC-04 requires revocation to land within five minutes.

Both halves are individually correct:

- The frozen key-set schema pins `records.minItems: 1`. Control refuses to
  render an empty active set, because an empty set was only ever reachable as a
  mis-render, and one would make the gateway reject every key while looking
  healthy.
- The gateway's `Refresh()` keeps the last-good set on a loader error or a
  missing file, so a transient filesystem hiccup does not blank all auth. Its
  own doc says revocation "converges on the next **successful** refresh".

Together they deadlock. Control writes nothing for the empty case, so no
successful refresh ever happens; deleting the artifact does not help, because a
missing file also keeps last-good. **Empty and unreadable are the same state on
this wire, and neither means deny.**

## Decision

We add an explicit deny-all state to the key set, and the gateway treats it as
authenticate-nothing rather than as an error.

- `records.minItems` relaxes to 0.
- A new required top-level `state` carries `"active"` or `"deny-all"`.
- `state: "deny-all"` requires `records: []`; `state: "active"` keeps
  `minItems: 1`.
- `Refresh()` swaps in the empty set when it loads a deny-all document. It keeps
  last-good only for a load FAILURE, which is unchanged.

Deny-all is a value on the existing artifact, not a second file. A separate
marker would make authentication state depend on the read order of two files,
and that ordering becomes an invariant nobody declared.

The distinction the schema must carry is intent, not emptiness. `records: []`
alone would still be ambiguous with a truncated write; pairing it with an
explicit `state` makes the deny deliberate and a torn document invalid.

## Consequences

- Revoking the last key produces a document Control can render and the gateway
  can load, so revocation converges within the NFR-SEC-04 window without a
  restart.
- A truncated or corrupt artifact still fails to load and still keeps last-good.
  Deny-all is expressible; it is not the failure mode.
- The frozen schema changes, so every vendored copy must move in lockstep and
  the parity gate must pass on the same commit.
- The gateway's loader gains one branch. An old gateway reading a deny-all
  document rejects it as schema-invalid and keeps last-good — so the gateway
  must ship before Control emits the state.

## Alternatives

**A separate deny-all marker file.** Rejected: two files, one answer. The
gateway would have to read them in a fixed order, and that order is an
undeclared invariant that a future refactor can silently invert.

**A tombstone record with `status: "deny-all"`.** Rejected: it puts a non-key in
the key list, so every consumer that iterates records must learn to skip it, and
one that forgets treats deny-all as a credential.

**Leave it to operators (delete the artifact, restart the gateway).** Rejected:
a restart is not a five-minute guarantee, and it makes revocation depend on an
operator noticing.
