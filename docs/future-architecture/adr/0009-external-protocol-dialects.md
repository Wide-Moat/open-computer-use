<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# ADR-0009 — L4 external surface: MCP primary, optional adapter dialects

- **Status:** Proposed
- **Date:** 2026-05-18
- **Related:** [ADR-0005](./0005-mcp-as-control-plane-gateway.md), [ADR-0008](./0008-internal-grpc-external-rest-mcp.md), [research/18](../research/18-open-webui-terminals-observed.md)

## Context

We have one external protocol today (MCP at `/mcp`) and a confirmed requirement that **multiple clients reach an identical capability surface**: Open WebUI, n8n, Claude Desktop, LiteLLM, OpenAI Agents SDK. Skills must be portable across all of them — a tool that works in one client and not another splits the surface and is rejected by definition (see [`COMPARISON.md`](../../COMPARISON.md), [`MCP.md`](../../MCP.md)).

Two distinct external-protocol pressures have emerged:

1. **Open WebUI native UX.** Open WebUI ships a native "terminal connection" mechanism with embedded file browser (`FileNav`), embedded xterm.js (`XTerminal`), and OpenAPI-driven tool injection. To use it, a server must speak either the single-terminal wire contract (`open-webui/open-terminal`) or the orchestrator wire contract (`open-webui/terminals`). See [research/18](../research/18-open-webui-terminals-observed.md) §3 for the contract.
2. **OpenAI-compatible API.** A non-trivial fraction of integration requests assume `/v1/chat/completions`. Not blocking today, but recurring.

The question is whether L4 should expose only `/mcp` or accept additional external dialects as adapters.

## Decision

- **MCP remains the only frozen, primary user-facing contract** ([ADR-0005](./0005-mcp-as-control-plane-gateway.md) stands).
- **Additional external dialects may be added as L4 adapters** over the same internal connect-go RPC ([ADR-0008](./0008-internal-grpc-external-rest-mcp.md)), under three conditions enforced per dialect:
  1. **Skill parity.** Every skill we ship MUST behave identically through the dialect and through MCP. If a skill cannot be expressed losslessly in the dialect, the dialect is not added.
  2. **No coupling to dialect-specific clients.** Removing the adapter must not affect any other client.
  3. **Wire contract must be stable.** If the dialect's wire format belongs to an upstream we don't control, the upstream's compatibility guarantees must be acceptable; otherwise pin and document supported version ranges.
- **No adapter is committed by this ADR.** Each dialect is gated on its own validation gate (see Verification below).

```text
                  ┌─── /mcp                        Primary, frozen        (n8n, Claude Desktop, LiteLLM, OpenAI Agents SDK)
L4 (Go) ──────────┼─── /api/v1/policies, /p/...    Proposed adapter       Open WebUI orchestrator dialect, status Hypothesis
                  ├─── /v1/chat/completions        Proposed adapter       OpenAI-compatible, status Hypothesis
                  └─── /admin/*                    Operator UI            REST, ADR-0008
```

## Rationale

- **One internal contract, many external surfaces** is the same shape as ADR-0008's internal/external split — just extended to external. The cost of adding a dialect is bounded by the adapter; the cost of NOT being able to add one is permanent client lock-in.
- **MCP as the parity floor.** Because MCP is the lowest-common-denominator protocol across all current target clients, locking MCP as the source of truth guarantees portability automatically. Any adapter that cannot match MCP's capability is by construction worse than the floor and is rejected.
- **Adapter, not branch.** Dialects do not fork the tool set, do not add MCP-incompatible methods, and do not reshape the sandbox lifecycle. An adapter that needs internal RPC changes is no longer an adapter — it's a fork — and falls outside this ADR.

## What this ADR does NOT do

- It does **not** approve adding the Open WebUI dialect. That hypothesis lives in [research/18](../research/18-open-webui-terminals-observed.md) §5 with five explicit open questions; until they are answered the dialect is not built.
- It does **not** approve adding an OpenAI-compatible dialect. Same status.
- It does **not** change the MCP contract.
- It does **not** authorise dropping the existing Open WebUI tool + filter integration. That decision is downstream of skill-parity validation per condition 1.

## Consequences

**Positive:**
- Adapters become an explicit, bounded extension mechanism — not ad-hoc patches scattered across the codebase.
- Conditions 1–3 make "should we add dialect X?" answerable with a checklist instead of a debate.
- Skill portability is structurally enforced: anything that breaks MCP parity is out by definition.

**Negative:**
- Each adapter adopted is permanent surface area to maintain. The decision to add must include the decision to maintain.
- Some upstream wire contracts (notably the Open WebUI orchestrator dialect) are at early version numbers and may break between releases. Adapters against them need a supported-version-range policy.

**Neutral:**
- Phase 6 L4 framework choice (HTTP router, middleware) must support multiple route trees mounted on the same connect-go core. Not a constraint on connect-go itself — every candidate router meets this.

## Alternatives considered

### MCP-only forever
- **Pro:** Smallest surface; zero adapter maintenance.
- **Con:** Locks us out of native UX in clients that don't speak MCP first-class. Open WebUI patches and our `computer_link_filter` then have to evolve in lockstep with upstream — the patch-maintenance burden grows with every Open WebUI release.
- **Verdict:** Acceptable today; this ADR keeps it as the default by requiring per-dialect justification.

### One adapter per client, deeply coupled
- **Pro:** Each client gets its perfect UX.
- **Con:** N adapters × M clients explosion; condition 1 (skill parity) becomes impossible to enforce; internal surface starts to bend toward dialects.
- **Verdict:** Rejected.

### Fork MCP with our own extensions
- **Pro:** Single protocol, richer capability.
- **Con:** Breaks every off-the-shelf MCP client. Loses the parity floor.
- **Verdict:** Rejected by ADR-0005.

## Verification

For each proposed adapter, before it is built:

1. **Skill-parity matrix.** Every skill in `skills/` must have a documented mapping that produces equivalent model behaviour via the dialect as via MCP. Discrepancies → adapter not built.
2. **Removal test.** Acceptance includes a CI configuration that builds and runs L4 with the adapter disabled; all other clients must still pass their integration tests unchanged.
3. **Version-range policy.** If the adapter speaks an upstream-owned wire format, the supported upstream version range is documented in the adapter's README and pinned in CI.
4. **Phase placement.** Adapters land no earlier than Phase 6 (L4 rewrite). Adding adapters to the current Python `computer-use-server` is not authorised by this ADR — that would create migration debt against ADR-0001.

## Migration notes

- Phases 1–5: unchanged. Single MCP endpoint stays on Python.
- Phase 6: L4 framework selection must explicitly preserve the option to mount additional route trees. No adapter built yet.
- Phase 6+: adapters added one at a time, each gated by the conditions above.
