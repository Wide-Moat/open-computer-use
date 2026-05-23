<!-- SPDX-License-Identifier: BUSL-1.1 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# 23 — Anthropic microVM: execution, egress & secrets (deep dive, observed)

> Source: live-VM walk inside an Anthropic Claude sandbox session, 2026-05-22, same guest-shell methodology as [`22-anthropic-firecracker-microvm-internals-observed.md`](./22-anthropic-firecracker-microvm-internals-observed.md) (`ps -ef`, `cat /proc/cmdline`, `curl -v`, `getent hosts`, reads under `/proc/1/`).
>
> Companion to [`#22`](./22-anthropic-firecracker-microvm-internals-observed.md). #22 is the **storage transcript** — disks, FUSE mounts, CoW rootfs, VM lifecycle. This file covers the **three axes #22 under-weighted**: (1) execution & process supervision, (2) network egress, (3) secrets & identity held in memory — plus the agent-memory gRPC API. Files and the internet are I/O channels; the third axis is *control of code execution inside the VM*, which #22 only touched via "`process_api` runs the exec loop".
>
> Status: **observation.** It carries four **proposed locks** (table below). Unlike #22 — which locked antipattern A37 directly — none of these edit an ADR, `antipatterns.md`, or an `architecture/` file yet. Each needs its owning phase's research pass and owner sign-off first. They are recorded here so that pass starts from a concrete proposal.

## Proposed locks (pending sign-off)

| # | Proposed lock | Would land in | Gated on |
|---|---|---|---|
| P1 | Egress allowlist enforced at **connection time** (resolved IP + TLS SNI), never at DNS-resolution time. DNS resolution itself stays unrestricted. | [`08-networking.md`](../architecture/08-networking.md) egress proxy; a new antipattern beside [A24](../antipatterns.md#a24--hostname-allowlist-without-dns-rebinding-defense) / [A31](../antipatterns.md#a31--wildcard-allowed-hosts-com) | Phase 8 research |
| P2 | A fixed **SSRF deny-set** is mandatory in every egress substrate: RFC1918, link-local `169.254.0.0/16`, cloud metadata `169.254.169.254`, and the IPv6 equivalents (`fc00::/7`, `fe80::/10`). | [`08-networking.md`](../architecture/08-networking.md) + [`07-security.md`](../architecture/07-security.md) | Phase 8 research |
| P3 | The guest holds **no long-lived API key** — not on disk, not in env, not in any config file. Even scoped/short-lived tokens are delivered over the control channel into agent memory and handed to workloads scoped + short-lived. | [`07-security.md`](../architecture/07-security.md) secret broker; extends #22 Layer-4 (`filesystem_id`) to the model-API-key class | Phase 4 research |
| P4 | The agent's control-plane port is unreachable from guest workload code (an `--block-local-connections` equivalent). | [`05-layer1-guest-agent.md`](../architecture/05-layer1-guest-agent.md) + [`07-security.md`](../architecture/07-security.md) ingress section | Phase 7 research |

---

## Axis 1 — Execution & process supervision

### 1.1 `process_api` is the execution supervisor, not just init

#22 §1 established `process_api` as PID 1 (custom Go binary, `rdinit=`). This walk shows it is also the **execution supervisor** — the everything-process for running code inside the VM:

- It **spawns and supervises child processes** — workloads and their PTYs — and reaps them.
- It **owns the control channel:** a WebSocket bound on `:2024` (`--addr 0.0.0.0:2024`, #22 §1.2). The **host is the client** — reached at `192.0.2.2` over the Firecracker tap device. The guest serves; the host drives.
- It runs the **agent exec loop** — the dispatch path for "run this command", "open this PTY".
- `--block-local-connections` (#22 §1.2) means **guest workload code cannot open the control port.** The `:2024` channel is host ↔ PID-1 only; nothing the agent spawns can reach it.

This is the third axis. #22 documented the *file* I/O channel (FUSE → S3) thoroughly; the network channel is its own axis (below). The under-documented one is **execution control** — who starts processes, who owns PTYs, who multiplexes the control channel. For our design it collapses into **Layer 1**: the Rust guest agent is simultaneously PID 1, the child-process supervisor, and the control-channel server. This is exactly the `process_api` shape studied in [`#19`](./19-anthropic-process-api.md) and the basis for [ADR-0002](../adr/0002-guest-agent-language-go.md) (Rust L1) — see also P4.

### 1.2 The in-VM memory boundary is weak — by acceptance, not by accident

Inside the VM the agent runs with root; `/proc/1/mem` is readable. **Secrets sitting in `process_api`'s memory are not protected from in-VM code execution as root.** Anthropic does not pretend otherwise — the real boundary is *external* (Firecracker/KVM) plus scope plus ephemerality. This matters because it sets the rule for Axis 3: do not design as if "the secret is in memory, therefore safe". It is not. See Axis 3.

### 1.3 Control-channel framing / multiplexing — open

WS frames are bounded (`--max-ws-buffer-size 32768`, #22 §1.2). How exec streams, PTY streams, and any file-sync traffic are **framed and multiplexed over the single `:2024` WebSocket** was not fully reverse-engineered in this walk. This is a direct input to the L3↔L1 protocol decision deferred to Phase 7 by [ADR-0008](../adr/0008-internal-grpc-external-rest-mcp.md) (connect-rust vs a `process_api`-style WS-frame protocol). Flagged as an open question below.

---

## Axis 2 — Network egress

### 2.1 What was observed

| Property | Observation | What it means |
|---|---|---|
| Transparency | No `Via:` header; TLS not intercepted / not re-signed; the guest CA bundle is the clean upstream bundle | **No MITM proxy** in the guest's TLS path. Egress is transparent at the TLS layer. |
| DNS | Resolution is **unrestricted** — the guest resolves arbitrary names freely (`8.8.8.8` reachable) | Filtering is **not** done by lying in DNS. |
| Enforcement point | Filtering happens **at connection time**, not at resolution time | You can resolve anything; you cannot *connect* to disallowed destinations. |
| Failure mode A | `403` on link-local / cloud-metadata (`169.254.169.254`) | An application/policy-layer SSRF rejection. |
| Failure mode B | `connection reset` on the control-plane port | A coarse L3/L4 block. |

Two distinct failure modes ⇒ **layered enforcement**: a coarse host-side L3/L4 filter underneath a finer policy layer on the agent/runner side.

### 2.2 What could not be determined

- **Which component terminates egress** (host vs agent) and what software implements it — no usable fingerprint.
- **IPv6 discrepancy.** This session showed IPv6 egress traffic, but #22's kernel cmdline carries `ipv6.disable=1`. Either this is a different environment/template, or IPv6 is selectively enabled here. **Do not assume #22 and #23 describe a bit-identical template** — reconcile before either is treated as canonical.

### 2.3 Takeaway for us

This confirms the [`08-networking.md`](../architecture/08-networking.md) default-deny + allowlist posture and sharpens it into two precise rules — **P1** (filter on the resolved IP + SNI at connect time, never on the DNS name) and **P2** (a fixed SSRF deny-set). Both are already implied by [A24](../antipatterns.md#a24--hostname-allowlist-without-dns-rebinding-defense) (DNS-rebinding defense) and [A31](../antipatterns.md#a31--wildcard-allowed-hosts-com) (no wildcard hosts): the allowlist must be checked against the *connection*, not the *name*. The forward-looking "how we would build this across substrates" lives in [`../design-notes.md`](../design-notes.md) DN-1.

---

## Axis 3 — Secrets & identity (held in memory, not on disk)

### 3.1 What was observed

There is **no model API key anywhere in the guest** — not on disk, not in any environment variable, not in any config file. #22 Layer-4 established the same for S3 credentials (the guest carries only a `filesystem_id` session token). This walk extends the finding to the **model-API-key class**.

Inference: the key — or, more likely, a scoped token derived from it — arrives **over the control channel** into `process_api`'s memory, and is handed to workloads **scoped and short-lived**. The exact handoff (where the runtime obtains the token, how the agent forwards a scoped token to a workload) was not fully traced — see open questions.

### 3.2 Why the defense holds without "memory is unreadable"

Axis 1.2 showed `/proc/1/mem` is readable by in-VM root, so the secret is **not** protected by being in memory. The defense rests on three *external* properties:

1. **External isolation** — the Firecracker/KVM boundary. The host, not the guest, is the trust boundary.
2. **Narrow scope** — the token a workload receives is scoped to that session/workload; leaking it leaks little.
3. **Ephemerality** — short TTL plus VM pause/teardown (#22 Layer-6). A leaked token expires fast.

This is the same philosophy as [`#17`](./17-anthropic-claude-code-remote-env-observed.md) §3 (FD-passing) and #22 Layer-4 (`filesystem_id`): **never put a long-lived high-value secret where compromised guest code can read it; if a secret must be in the guest, make it scoped + short-lived so the blast radius is small.** It is the target end-state for our Phase 4 secret broker — stricter than the current [`07-security.md`](../architecture/07-security.md) baseline, which still injects keys via `/v1/configure` (in-guest, even if rotated). → **P3**.

---

## The agent-memory gRPC API — a separate channel, not a file

Distinct from the file axis: agent "memory" is **not** a filesystem path. It is a dedicated **gRPC API**:

- **push** — inject content into the model context.
- **edit** — mutate memory via a tool call.
- **event-sourced** — proto messages named by event.

This is a clean separation worth copying: durable *user* files go through the FUSE/S3 path (#22 Layer-3); agent *working memory* is an API surface — versioned proto, event-sourced — owned by the control plane. For our 4-layer model this is a **Layer 4 (control plane)** concern, not Layer 1 storage. It has no current roadmap consumer and deserves a dedicated Phase 6 research item — worth a `gaps.md` entry when this doc is reviewed.

---

## Open questions / what to research next

| # | Question | Owner phase |
|---|---|---|
| Q1 | Exact point where the runtime obtains the model token, and how the agent forwards a *scoped* token to a workload (the remaining gap in Axis 3). | Phase 4 |
| Q2 | Which component terminates egress (host vs agent) and what software implements it — no fingerprint obtained. | Phase 8 |
| Q3 | Control-channel framing / multiplexing over the single `:2024` WebSocket (exec vs PTY vs file-sync). | Phase 7 ([ADR-0008](../adr/0008-internal-grpc-external-rest-mcp.md)) |
| Q4 | IPv6 egress observed here vs `ipv6.disable=1` in #22 — same template or not? | — (reconcile #22/#23) |
| Q5 | Display + input layer (Xvfb + CDP) — the most Computer-Use-specific piece, not covered by any Anthropic-internals doc yet. | Phase 7 |
| Q6 | Firecracker snapshot/restore for fast ephemeral workspaces — cross-ref [`#20`](./20-snapstart-hot-swap.md); already a Phase 10 input. | Phase 10 |

---

## Implications and where they land in the roadmap

| Axis in this file | Roadmap target | What feeds in |
|---|---|---|
| 1 — execution & process supervision | [Phase 7](../roadmap.md#phase-7), [ADR-0008](../adr/0008-internal-grpc-external-rest-mcp.md) | L1 agent is PID 1 + child-process supervisor + control-channel server in one binary. Control-channel framing/multiplexing (Q3) is an open Phase 7 protocol question. P4: control port unreachable from workloads. |
| 2 — network egress | [Phase 8](../roadmap.md#phase-8) | P1 (filter on connect, not DNS) + P2 (SSRF deny-set). Reconcile IPv6 vs #22 (Q4). Build approach in [`design-notes.md`](../design-notes.md) DN-1. |
| 3 — secrets in memory | [Phase 4](../roadmap.md#phase-4) | P3: no long-lived key in the guest; scoped + short-lived tokens only. Stricter than the current `07-security.md` `/v1/configure` baseline. |
| Agent-memory gRPC API | [Phase 6](../roadmap.md#phase-6) | Agent memory is an API surface (event-sourced proto), not Layer-1 storage. New research item — propose a `gaps.md` entry. |

## What to copy verbatim from Anthropic's design

1. **One PID-1 binary = init + supervisor + control-channel server.** No split. — Phase 7.
2. **Control port unreachable from workload code** (`--block-local-connections` equivalent). — Phase 7 (P4).
3. **Egress filtered on connect (resolved IP + SNI), DNS left open.** — Phase 8 (P1).
4. **Fixed SSRF deny-set**, IPv6 included. — Phase 8 (P2).
5. **No long-lived key in the guest;** scoped + short-lived tokens delivered over the control channel. — Phase 4 (P3).
6. **Agent memory as an event-sourced gRPC API,** separate from the user-file storage path. — Phase 6.

## How to reproduce these observations

```bash
ps -ef                                   # PID 1 = /process_api, supervisor + children
cat /proc/cmdline                         # control-port + --block-local-connections flags
curl -v https://example.com 2>&1 | grep -iE 'via:|issuer|subject'   # transparency: no Via, clean TLS chain
curl -s -o /dev/null -w '%{http_code}' http://169.254.169.254/      # SSRF guard → 403
cat /etc/resolv.conf && getent hosts example.com                    # DNS resolution unrestricted
env | grep -iE 'key|token|secret'         # API key absent from env
grep -rIl -iE 'sk-ant|api[_-]?key' ~ /etc 2>/dev/null               # API key absent from disk/config
head -c0 /proc/1/mem 2>&1                 # in-VM memory boundary smoke test (root can read)
```

Run inside a live session early (some paths get touched later). Save outputs verbatim into a new `research/NN-anthropic-*-observed.md` — cross-snapshot comparison is how the #22/#23 IPv6 discrepancy (Q4) surfaced.
