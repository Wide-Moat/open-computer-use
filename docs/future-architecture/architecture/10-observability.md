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

## Audit log

See [07-security.md](./07-security.md) for the mandatory event list and forbidden-content rules.

- Sink: separate from regular logs (e.g., S3 bucket, immutability lock).
- Retention: ≥ 90 days. SOC-2-aligned.
- Schema: stable, versioned. Each event carries `event_id`, `ts`, `tenant_id`, `session_id`, `type`, `payload`.

## Tracing patterns

- L4 starts a span per MCP request.
- L4 → L3 calls carry W3C `traceparent`.
- L3 → L1 carries it forward (HTTP header).
- Skill / sub-agent execution wraps a child span.

This makes "why was that exec slow" answerable across the whole stack in one trace.

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
