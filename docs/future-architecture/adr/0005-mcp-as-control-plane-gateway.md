# ADR-0005 — MCP stays the user-facing protocol; admin UI uses a separate API

- **Status:** Accepted
- **Date:** 2026-05-17

## Context

Today users (Open WebUI and direct clients) talk to us via MCP at `/mcp`. We're adding an admin UI for operators. We need to decide whether to unify on MCP or separate the surfaces.

## Decision

- **MCP** is the **only** user-facing protocol. Frozen contract — every phase preserves it.
- **Admin UI** consumes a separate **REST/GraphQL** API on the same control-plane process, behind separate OIDC scope.
- **No MCP-for-admin.** Admin operations don't fit JSON-RPC tool-call semantics well, and conflating roles raises auth blast-radius.

## Rationale

- MCP is the AI-tool protocol; designed for "agent calls tool". Admin operations ("list sessions", "rotate keys") are CRUD, not tool calls.
- Separate APIs let auth scopes be distinct and minimal.
- We don't fork MCP; we don't extend it with non-standard methods.

## Consequences

- L4 exposes two distinct HTTP routes: `/mcp` (MCP gateway) and `/admin/*` (admin API).
- Admin UI is its own deployment / SPA; backend stays in Go control plane.
- Open WebUI integration is unaffected.

## Alternatives

- **MCP-only (admin via custom MCP tools)** — rejected, abuses the protocol, mixes auth scopes.
- **Two separate processes** — rejected for now; can split later if admin scale demands it.
