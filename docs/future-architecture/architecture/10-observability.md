<!-- SPDX-License-Identifier: BUSL-1.1 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# 10 — Observability

> Metrics, traces, audit log, SLOs.
> Boring on purpose — use the standard stack.

## Signals

| Signal | Tool | Notes |
|---|---|---|
| Metrics | Prometheus | Scrape L3 + L4 + egress proxy + (optionally) L1 |
| Traces | OpenTelemetry → any OTLP backend | Sample at L4 ingress, propagate through L3 → L1 |
| Structured logs | stdout/stderr → fluent-bit → object store / Loki | JSON lines |
| Audit log | dedicated append-only sink | Separate from regular logs; retention ≥ 90d |

## Required metrics

L4:
- `mcp_requests_total{tool,tenant,status}`
- `mcp_request_duration_seconds{tool}`
- `session_create_duration_seconds`
- `session_active{tenant,template}` (gauge)
- `secret_rotation_total{kind,status}`

L3:
- `sandbox_pool_size{template,state}` (state ∈ idle / leased / draining)
- `sandbox_spawn_duration_seconds{template}`
- `sandbox_exec_duration_seconds{template}`
- `sandbox_terminate_total{template,reason}`

L1 (in-sandbox):
- `agent_exec_total{kind}` where kind ∈ bash/python/file/sub_agent
- `agent_exec_duration_seconds{kind}`

Egress proxy:
- `egress_requests_total{decision,destination_class}`
- `egress_request_duration_seconds`

## SLOs (target)

| SLO | Target |
|---|---|
| MCP request success rate | ≥ 99.9% (excluding user-side errors) |
| Session create latency p99 | < 500 ms (warm pool hit) |
| Session create latency p99 cold | < 2 s (cold start, kata-ch) |
| Exec latency p99 | < 50 ms (orchestration overhead, not workload) |
| CDP frame rate | ≥ 10 fps |
| Egress proxy latency p99 | < 100 ms |

These match the sandboxd targets and are validated in Phase 5 (k8s prod) + Phase 9 (kata).

## RAM-based capacity-sizing formula

The first question operators ask is "how many sandboxes does a node hold?" The answer is bounded by **RAM**, not CPU — sandboxes idle most of the time but always reserve their memory request. For `kata-ch` / `kata-fc` specifically, the VMM itself owns a slab of memory that the workload never sees.

```text
concurrent_sandboxes_per_node = floor(
    (node_ram_bytes - system_reserve_bytes - kubelet_reserve_bytes)
    / (template.mem_request_bytes × overcommit_factor + vmm_overhead_bytes)
)
```

| Term | Typical value | Notes |
|---|---|---|
| `node_ram_bytes` | Per node, e.g. `64 GiB` | The bare-metal node spec |
| `system_reserve_bytes` | `1–2 GiB` | Kernel, daemons, monitoring agents |
| `kubelet_reserve_bytes` | `~512 MiB` | k8s overhead per `kube-reserved` + `system-reserved` |
| `template.mem_request_bytes` | `2 GiB` (default `customer-cu-kata-ch-v3`) | What the template guarantees the workload |
| `overcommit_factor` | `1.0` for `customer-cu`, up to `1.5` for `internal` | Operators choose; lower = stricter |
| `vmm_overhead_bytes` | `0` for runc/sysbox, `~20 MiB` for `kata-fc`, `~40 MiB` for `kata-ch` | Per-VM Firecracker / CH process |

Operators size node pools by **solving for `node_ram_bytes`** given a target `concurrent_sandboxes_per_node` and the dominant template. Phase 9 validates the formula on real bare-metal hardware; the dashboard ships node-level "sandbox-density" gauge so the formula can be tuned with field data.

The formula intentionally does **not** include CPU. CPU oversubscription is a separate axis governed by `cpu_request` and HPA; conflating it with RAM here would mislead capacity-planners.

For the Phase 10 frozen-snapshot pool, the analog formula replaces `mem_request × concurrent` with `snapshot_blob_size × pool_size` — RAM cost goes to zero for cold pool entries (they live on disk), only resumed-but-idle sandboxes consume RAM. The formula is updated in the Phase 10 deliverable.

## Distributed tracing

The W3C `traceparent` header crosses every layer boundary; without that, "why was this exec slow?" is unanswerable. Concrete wire requirements:

- **L4 ingress.** Generate a root span per MCP request; attach `traceparent` to every downstream call.
- **L4 → L3.** Carried on the connect-go metadata (`traceparent` is a first-class metadata key); L3 starts a child span on receive.
- **L3 → L1.** Carried as a JSON field in the `Configure` / `ToolCall` / `Exec` data-plane frame (the WS protocol doesn't have HTTP headers; the trace context rides inside the message envelope). L1 starts a child span on receive.
- **Audit-log linkage.** Every audit event carries the `trace_id` of the request that triggered it. This is what lets the "why was this destination egress-blocked?" question reduce to a single trace lookup.

Sampling: ingress samples at a configurable rate (default `1.0` in dev, `0.01` in prod); the rest of the stack honors the upstream sample decision (no resampling). Forced-sample on errors regardless of rate.

OpenTelemetry SDK lands in L4 at Phase 6; L3 at Phase 6+; L1 at Phase 7 (the Rust agent uses `tracing` + `opentelemetry-otlp`). Phase 8 wires the audit-log linkage.

## Audit log

See [07-security.md](./07-security.md) for the mandatory event list and forbidden-content rules.

- Sink: separate from regular logs (e.g., S3 bucket, immutability lock).
- Retention: ≥ 90 days. SOC-2-aligned.
- Schema: stable, versioned. Each event carries `event_id`, `ts`, `tenant_id`, `session_id`, `type`, `payload`.

## Health probes

- `/healthz` (liveness) and `/readyz` (readiness) on L4 (already exists) and L3 (Phase 5).
- L1 agent: `GET /v1/health` is the readiness signal for the warm pool.

## Phase progression

| Phase | Observability change |
|---|---|
| 1–3 | Keep current stdout logging |
| 4 | Audit-event emission added for secret rotation |
| 5 | Prometheus scrape annotations in Helm + dashboards starter pack |
| 6 | OpenTelemetry SDK in Go L4 + audit sink wired |
| 8 | Egress proxy metrics + audit pipeline finalized; 90 d retention enforced |
| 9 | Kata-tier metrics added; capacity-formula validation on bare-metal pool |
| 10 | Multi-AZ traces, error-budget burn alerting; multi-region foundations |

## Source

- [`sandboxd/docs/operations.md`](../../../sandboxd/docs/operations.md)
- [07-security.md](./07-security.md)
