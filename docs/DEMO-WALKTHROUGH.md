<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: draft
last-reviewed: 2026-06-28
owner: "@Wide-Moat/architects"
applies-to: next/v1
---

# OCU next/v1 — step-by-step demo

A runnable walkthrough of each architectural security and data-flow guarantee — one step at a time, with the command and the expected observable.

## 0. Prerequisites

```bash
# Lima VM with runc + runsc registered (the e2e substrate; not Docker Desktop)
limactl start ocu-linux        # the working reference runtime
# Build the sandbox guest image (the guest agent is the ENTRYPOINT)
cd ocu-sandbox && docker build -f host/guestimage/Dockerfile -t ocu-guest:demo host/guestimage
```

The fleet wires together via `deploy/fleet/` (certs, edge, secrets) and the
`feat/fleet-assembly` branch (compose that stands up all six components with the
three live cross-component seams).

---

## Aspect 1 — MCP gateway: caller auth + the F5 forward (component-01)

**Proves:** a caller authenticates with a static `sk-ocu-` key; the gateway forwards
to Control under its OWN service identity; the caller key never crosses F5.

```bash
# 1a. mint a key (Control is the only mint point)
occ mcp-key create --tenant acme            # prints sk-ocu-<32B> ONCE
KEY=$(cat ~/.ocu/mcp-key)                    # the minted key, from your secret store
# 1b. call the gateway with the key
curl -H "Authorization: Bearer $KEY" -H "MCP-Protocol-Version: 2025-06-18" \
     localhost:8080/mcp -d '{"jsonrpc":"2.0","method":"tools/call",...}'
# 1c. call with a wrong key
curl -H "Authorization: Bearer $WRONG_KEY" ...
```

**Expect:** (1b) authenticates → forwards to Control (502 today: forward is the
fail-closed stub until P1 wires the live F5). (1c) → **401**, key not in the
boot-loaded set. Observe in the gateway's OCSF audit (F10): `actor_id` is the
*resolved* KeyID, never a body-claimed identity (NFR-SEC-09).

**The guarantee to point at:** the caller key appears in NO forwarded request — the
forward carries only the gateway service identity (proven by the type fact: the F5
forward shapes have no credential field).

---

## Aspect 2 — Strict tool-call validation + IaC fail-closed

**Proves:** the gateway rejects malformed input pre-buffer, and the policy gate
fails closed on an empty/malformed deploy manifest.

```bash
# 2a. ingress strict-validate + invariants (Go)
go test ./internal/ingress/ -run 'Valid|Strict|Reject|Origin|Auth|Invariant'
# 2b. the IaC policy gate's built-in two-sided self-test
python3 scripts/iac_policy_check.py --self-test
```

**Expect:** (2a) malformed input rejected before any forward, stable reason class only
(no session id, no internal route). (2b) every neutered check reds; shipped manifests
pass — a self-contained RED-when-neutered / GREEN-as-shipped gate.

**Output** (gateway main `@49e5e91`):

```
# 2a
$ go test ./internal/ingress/ -run 'Valid|Strict|Reject|Origin|Auth|Invariant'
   ok  github.com/Wide-Moat/ocu-mcp-gateway/internal/ingress

# 2b — the gate neuters each rule and proves it reds
$ python3 scripts/iac_policy_check.py --self-test
   ::error:: k8s manifest is empty ... no proof of deny-by-default (fail-closed)
   ::error:: k8s manifest is not a NetworkPolicy ... egress posture unproven (fail-closed)
   ::error:: k8s NetworkPolicy declares no Egress policyType ... (fail-closed)
   ::error:: Compose manifest has no ocu-mcp-gateway service ... (fail-closed)
   iac-policy self-test: selector forms + empty-manifest fail-open all
     RED-when-neutered, GREEN-as-shipped
```

The self-test covers every selector form (matchLabels + matchExpressions
In/Exists/namespaceSelector) and empty/malformed manifests.

---

## Aspect 3 — Cross-tenant isolation: the keystone (component-04 + component-08)

**Proves:** a caller scoped to tenant A cannot read tenant B's files — cross-tenant
reads return 404, not 200.

```bash
# two sessions, two tenants, one shared store
# tenant A uploads a file under scope A, gets file_id
# tenant B (different cookie) requests that file_id
curl -b cookieB localhost:3000/api/v1/files/<A's file_id>
```

**Expect:** **404 not_found** (never 403 — anti-enumeration). The webui route export
resolves scope from the *verified session* (attestedAuth), never a stub.

**Output** (webui F9 stack @d7337ba, the regression test imports the
SHIPPED `POST/GET/METADATA_GET` exports — not a factory):

```
# 1. baseline — the guard holds
$ npx vitest run src/app/api/v1/files/__tests__/cross-tenant.test.ts
   Tests  3 passed (3)

# 2. red-probe — collapse the metadata-GET export scope to a fixed "tenant-a"
#    (reproduces the stubAuth hole), keep tenant A's own read intact
   × tenant B cannot read tenant A's file metadata — cross-scope → 404, never 403
   AssertionError: cross-tenant access must be not_found: expected 200 to be 404
   Tests  1 failed | 2 passed (3)      # B now reads A — the CRITICAL is back

# 3. restore → 3 passed (3)
```

The red-probe reds the *exact* cross-tenant case (B reads A) while tenant A's own
read stays green — two-sided proof the guard reds on the real hole against the
shipped path.

---

## Aspect 4 — F9 storage: offset reads + the Files-API north contract (component-04)

**Proves:** a content read with an offset but no length reads `[offset, EOF)` — never
an empty 200.

```bash
# write "hello", read from offset 2 with no length param
curl 'localhost:9000/v1/files/<id>/content?offset=2'
```

**Expect:** body = `llo` (bytes from offset to EOF). Before the fix this returned an
empty 200. The F9 listener is a dedicated north Files-API leg (ADR-0025), distinct
from the south mount route; scope rides as a host-attested `filesystem_id` field, no
edge-injected credential.

**Output** (filestore main @104dac8 — F9 listener landed via #21):

```
# 1. baseline — the offset-to-EOF guard holds
$ go test ./internal/filesapi/ -run TestContentOffsetOnlyReadsToEOF
   ok  github.com/Wide-Moat/ocu-filestore/internal/filesapi

# 2. red-probe — neutralize the fix (force length=0 on the absent-length path,
#    reproducing the pre-fix empty-200 bug)
   content_test.go:181: offset-only body = "", want "llo" (bytes [offset, EOF))
   --- FAIL: TestContentOffsetOnlyReadsToEOF

# 3. restore → ok
```

`TestContentOffsetOnlyReadsToEOF` also pins `Stat called 1 time` — the handler
resolves `length = info.Size - offset` via a single Stat before the ALLOW mandate,
so a vanished object still records a deny.

---

## Aspect 5 — Sandbox exec: UDS-only, fail-closed boot (component-05)

**Proves:** the guest binds its exec socket UDS-only; a guest with no/invalid key
fails closed at boot; the host dials in (the guest never dials out).

```bash
# materialize a session container with the real handoff (Stage: sock 0777, files 0644, real ed25519 key)
octl create --image ocu-guest:demo --tier runc
octl exec <session> -- /bin/sh -c 'echo hi'     # runs over the exec channel under CapDrop ALL
```

**Expect:** exec runs over the UDS; a guest-stack dial fails at accept (the channel is
off any guest-reachable network, NFR-SEC-43); a container booted without
`--auth-public-key` fails closed (the guest agent exits). The control→guest argv is pinned
in INTEGRATION.md (binary first, flags as arguments to the ENTRYPOINT).

---

## Aspect 6 — Operator read console: BFF + read-must-not-mutate (ocu-admin)

**Proves:** the operator console reaches Control through a server-side BFF over an
all-GET read-API; the console cannot mutate (a compile-time property).

```bash
# log in to the BFF (bcrypt + first-party cookie), view the session list
curl -b adminCookie localhost:4000/v1alpha/sessions
```

**Expect:** the enriched session list (reserved/active/released rows). The BFF dials
the operator socket as the operator-scoped peer (ADR-0004); a read handler that
references destroy/revoke/denylist/quota is a **build failure** (the import-boundary
test — plant a forbidden import and depcruise reds).

---

## Aspect 7 — Audit: OCSF emit, fail-closed durable-first (component-07)

**Proves:** every terminated request is recorded durably before acknowledgement.

```bash
# perform an authorized op, then read the durable OCSF line
tail -1 /var/ocu/audit/*.ocsf.json
```

**Expect:** an OCSF ApiActivity (class 6003 at the gateway / 1001 at filestore) with a
monotonic per-source sequence; the hash-chain is authored by the pipeline at ingest.
If the durable write fails, the request is refused (500), never ack'd — emit-before-ack.

---

## Aspect–canon index

| Aspect | Component | Key ADR/NFR | Guarantee | Live proof |
|---|---|---|---|---|
| 1 caller auth + F5 | 01 MCP gateway | ADR-0027, NFR-SEC-09/87 | key never forwarded | repo suite |
| 2 strict-validate + IaC | 01 | NFR-SEC-46/51/52 | fail-closed gates | **firsthand self-test ✓** |
| 3 cross-tenant | 04 + 08 | NFR-SEC-26 | scope from attested session | **firsthand red-probe ✓** |
| 4 F9 offset reads | 04 | ADR-0025 | nil-length = to-EOF | **firsthand red-probe ✓** |
| 5 sandbox exec | 05 | ADR-0024, NFR-SEC-43 | UDS-only, host-dialled | e2e on Lima |
| 6 read console | admin | ADR-0022, ADR-0004 | read-must-not-mutate | repo suite |
| 7 audit | 07 | ADR-0009 | durable-first emit-before-ack | fleet journal |

Commit anchors for the firsthand runs above: gateway `@49e5e91`, webui `@d7337ba`,
filestore `@104dac8`.

## Open: live-wire fleet-assembly

The end-to-end live demo (all seven aspects against one running fleet) is
`deploy/fleet/docker-compose.fleet.yml` (13 services: real MinIO object-store, real
Postgres-17 control state, the six built components, and the south mount plane). It
wires the three proven cross-component seams (F9 webui↔filestore, south mount
filestore↔rclone, control↔guest argv) so the steps above run against real
neighbours, not stubs. The Lima VM `ocu-linux` is the substrate.

The compose lives on `feat/fleet-assembly`, which still carries a pre-ratification
doc snapshot (it predates the ADR-0022/0024/0025/0026/0027 merges on `next/v1`); the
compose file itself is current, but rebase the branch onto the ratified canon before
standing the full fleet up so the doc tree does not regress.
