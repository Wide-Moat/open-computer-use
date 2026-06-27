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

The web UI BFF refuses to start without a real embed-verify and session secret
(no default — a default-keyed deployment would accept forged embed tokens), so
provide an env file first:

```
cp deploy/fleet/.env.example deploy/fleet/.env
# set OCU_EMBED_VERIFY_SECRET and OCU_SESSION_SECRET (openssl rand -hex 32 each)
docker compose -f deploy/fleet/docker-compose.fleet.yml --env-file deploy/fleet/.env \
  up -d --build --wait
```

The object-store engine reaches MinIO over a dedicated `ocu-storage-backend`
network, kept off the credential-bearing south plane. Without it the daemon's
S3 versioning probe cannot dial `minio` and the process fail-closes at boot.

The sandbox guest is not a long-lived service: control creates it per session
through the Docker socket. The standalone sandbox smoke runs through `octl`
(see `ocu-sandbox`).

## Durable state

The control plane's session state — the reservation registry, the deny posture,
and the quota counters — is durable in Postgres (`control-db`), not in-memory.
Control opens it via `-state-dsn` and applies its embedded schema idempotently
on boot, so a fresh deployment provisions the three lock-domain tables and an
existing one is a no-op. Session reservations survive a control restart.

Verify the schema provisioned + state survives a restart:

```
docker compose -f deploy/fleet/docker-compose.fleet.yml exec control-db \
  psql -U ocu -d ocu_control -c '\dt'
# -> sessions, denylist, quota_counters

docker compose -f deploy/fleet/docker-compose.fleet.yml exec control-db \
  psql -U ocu -d ocu_control -c \
  "INSERT INTO denylist (scope,key,reason,since) VALUES (0,'probe','x',now());"
docker compose -f deploy/fleet/docker-compose.fleet.yml restart control
docker compose -f deploy/fleet/docker-compose.fleet.yml exec control-db \
  psql -U ocu -d ocu_control -c "SELECT key FROM denylist WHERE key='probe';"
# -> the row survives the daemon restart
```

## Seam smokes

Each data seam has a smoke that reds on a real break — run them after bring-up.

North F9 (web UI → object-store north), from the `ocu-north` network:

```
# keystone: an unknown or cross-scope file_id is 404 not_found, never 403
docker run --rm --network ocu-fleet_ocu-north curlimages/curl -sk \
  -H 'X-OCU-Filesystem-Id: fs-fleet' \
  -o /dev/null -w '%{http_code}\n' https://filestore:7080/v1/files/unknown
# -> 404 (a 403 here would be an enumeration leak)

# the BFF trusts the object-store leaf via NODE_EXTRA_CA_CERTS, not by disabling
# verification — proven from inside the web UI container
docker compose -f deploy/fleet/docker-compose.fleet.yml exec webui \
  node -e 'const https=require("https"),fs=require("fs");
  https.get({host:"filestore",port:7080,path:"/v1/files?limit=1",
  headers:{"X-OCU-Filesystem-Id":"fs-fleet"},ca:fs.readFileSync(process.env.NODE_EXTRA_CA_CERTS)},
  r=>console.log(r.statusCode))'
# -> 200
```

South mount (guest → edge → exchange → south object-store), from
`ocu-mount-facing`, using the weak JWT the harness renders into the shared
volume:

```
# valid weak JWT completes the validate->strip->exchange->inject->route chain
curl -sk --cacert <ca.pem from south-shared> \
  -H "Authorization: Bearer <weak JWT from guest-config.json>" \
  -X POST -d '{"filesystem_id":"fsrw","path":"/"}' \
  https://edge:8450/v1/filestore/fs/listDirectory
# -> 200 ; the same request with no token -> 401
```

Sandbox leg: `octl create --runtime runc --image process_api:prod` →
`octl exec` → `octl destroy` (zero-leak), run in Lima (`ocu-sandbox`,
`make e2e-vm`). The createFile write verb on the north leg is `501` until #304
freezes the upload body; the live read-plane (list, metadata, content, the
keystone) is fully exercised.

## Smoke-wave verdict

Each component carries its own critical-aspect smokes, run firsthand against
the real component (not the fleet stand-ins where those differ — see the live
stack caveats below). Every smoke was proven non-vacuous by a planted mutation
that drove it red before revert.

| Component | Aspects proven (PASS) | Non-vacuity |
|---|---|---|
| filestore (04) | north/south router split (#10: north 404 / south 405); F9 503 fail-closed without scope header, 501 create-fenced (#304), 404 keystone byte-identical for foreign vs unknown fsid; handle-store durability across kill+restart | 2 planted mutations red the keystone + the create-fence tests |
| rclone mount (04) | validate→strip→RFC8693→inject→route swap; weak-JWT matrix on the **live edge** (fsrw=200, no-token=401, forged=401, foreign-scope=403); single-hop proven by L3 route block (backend IPs unreachable from mount-facing); FUSE cap hardening | 3 planted mutations red the swap, the sig check, the cap posture |
| control (02) | killswitch isolation, required-flag boot gate, ADR-0017 no-scope mint refusal, audit-error propagation on destroy-deny; live `ocu-controld` 0.0.0.0 bind fail-closes 401 on unattested caller; distroless image (no shell) | 4 planted mutations each red their aspect |
| webui (08) | proxy runs on the Node runtime (no node:crypto-in-edge); F9 TLS trust via NODE_EXTRA_CA_CERTS; embed-verify boot gate refuses a short key (HTTP 500); live F9 round-trip list=200, keystone=404 | 2 planted mutations + a defanged short-key boot |
| admin | every Constitution "never" (BFF→authority import, `.sock` leak, gate fail-open, JWT alg-pin drop, cookie `Secure`/`SameSite` drop, config fallback); build, typecheck, 40/40 vitest, Stryker 92.45% | 6 planted defects each red their guard |

### Live stack caveats (honest)

- **filestore** — the live fleet container now runs the F9 north plane (`:7080`)
  and stays healthy; the S3 dial it crashed on at first bring-up is fixed (the
  `ocu-storage-backend` network). The live F9 round-trip above (list=200,
  keystone=404) is proven from inside the web UI container.
- **control** — the live fleet `control-plane` container is the south-credential
  harness stand-in (mint + JWKS only), not this repo's `ocu-controld`. The
  control invariants are smoked against the real daemon directly; smoking the
  stand-in would be a fake-green.
- **admin** — not in the fleet compose and has no Dockerfile; its operator
  read-surface (ADR-0022) is unbuilt, so it is correctly absent from the live
  data path. Its guards are smoked in-repo.
- **sandbox** — the live FUSE/runtime e2e needs `/dev/fuse` + runsc, which live
  on Lima `ocu-linux`, not the Darwin Docker host the fleet runs on. The leg is
  proven through `octl` in Lima (above), not the Darwin stack.
