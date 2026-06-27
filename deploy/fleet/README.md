<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# Fleet assembly

Wires the six next/v1 components into one running deployment. This is the
enterprise-architecture (`next/v1`) assembly — distinct from the
proof-of-concept `docker-compose.yml` at the repository root, which stays in
place and untouched.

## Fleet vs PoC

| | PoC (`/docker-compose.yml`) | Fleet (`deploy/fleet/`) |
|---|---|---|
| Components | MCP server + workspace image | The six `next/v1` components |
| Storage | local workspace volume | object-store service + real S3 (MinIO) |
| Auth | none | embed-token verify + first-party session |
| Egress | none | trust-edge (south mount leg) |
| Audience | local experimentation | the enterprise architecture under assembly |

The PoC keeps working as-is. Migration is a move-over, not a cut-over: run the
fleet stack alongside the PoC, point traffic at it when ready, retire the PoC
compose last.

## What runs live today

| Seam | Status |
|---|---|
| F9 north — web UI → object-store `/v1/files` | live: real HTTP, keystone-404, MinIO backend |
| control → sandbox guest (create → exec → destroy) | live: `octl` raw smoke, runc × scratch |
| south mount — guest → edge → object-store | exchange semantics live-proven on the Go edge; the stock-Envoy container hop is Phase F (see below) |

## South mount leg — Phase E vs Phase F

The weak-session-JWT → real-credential exchange that the south mount leg
depends on has two realizations:

- **Phase E (live-proven).** The exchange chain — real JWKS verification, real
  RFC-8693 token exchange keyed on `filesystem_id`, real strip-and-inject —
  runs on a Go edge (`ocu-rclone-filestore` `test/harness/cmd/edge` +
  `edgeglue`). The mount leg's behavior is proven against it.
- **Phase F (deferred).** Production uses stock Envoy (`envoy.yaml`, the SDS
  secret `filestore_exchanged_credential`). The live `envoyproxy/envoy`
  container hop is not yet run. The missing winch is an SDS source serving the
  exchanged credential keyed on the validated `filesystem_id` (an HTTP→SDS shim
  for a single-`filesystem_id` demo; a multi-`filesystem_id` SDS is the
  real-deployment follow-up).

The fleet south leg runs the Go edge — the same chain, the same semantics —
flagged Phase F for the literal stock-Envoy container. Nothing here claims the
stock Envoy hop runs live, because it does not yet.

## Networks

| Network | Members | Purpose |
|---|---|---|
| `ocu-frontend` | web UI, external client | the embeddable UI surface |
| `ocu-north` | web UI, object-store north | F9 no-credential Files-API leg |
| `ocu-mount-facing` | guest mount, edge | the guest's only route out (south leg) |
| `ocu-edge-backend` | edge, object-store south, control JWKS, exchange, MinIO | the credential-bearing plane; the guest has no membership |

The guest sits on `ocu-mount-facing` only — it has no route to the object-store
south face, control, the exchange peer, or MinIO. The single-hop invariant.

## TLS

One leaf, two listeners: the object-store service's north (`:7080`) and south
(`:8444`) faces share one certificate whose SAN covers `filestore` and
`ocu-filestore`. The `cert-init` one-shot mints it. The web UI trusts that leaf
via `NODE_EXTRA_CA_CERTS` (the CA is mounted, never baked, and certificate
verification is never disabled).

## Bring-up

```
docker compose -f deploy/fleet/docker-compose.fleet.yml up -d --build --wait
```

The sandbox guest is not a long-lived service: control creates it per session
through the Docker socket. The standalone sandbox smoke runs through `octl`
(see `ocu-sandbox`).
