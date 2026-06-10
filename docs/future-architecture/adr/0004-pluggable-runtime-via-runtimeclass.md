<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# ADR-0004 — Pluggable runtime via Kubernetes RuntimeClass (and per-template selection)

- **Status:** Accepted
- **Date:** 2026-05-17

## Context

We need to swap L2 runtimes (runc / sysbox / gVisor / kata-fc / kata-ch) per template, not per cluster. Internal sandboxes go to sysbox; public Computer Use goes to kata-ch; dev goes to runc. All in the same cluster.

## Decision

- **In k8s:** runtime selection is `Pod.spec.runtimeClassName`, carried from `SandboxTemplate.runtime_class`.
- **Outside k8s:** the provider (`DirectCHProvider`, `DockerComposeProvider`) honors the same field, mapping it to its native mechanism.
- **No runtime detection.** Templates declare; cluster operators install the matching RuntimeClasses.

## Rationale

- `runtimeClassName` is the standard k8s primitive. No reinvention.
- Per-template choice is what tenant tiering requires.
- Separation of concerns: operators install runtimes (kata-deploy DaemonSet etc.); template authors choose them.

## Consequences

- Helm chart documents required RuntimeClasses per template.
- Bare-metal node pool with taints required when any template uses `kata-*`.
- Phase 5 ships with `sysbox` only; Phase 7 adds `gVisor`; Phase 9 adds `kata-fc` / `kata-ch`.

## Alternatives

- **Single cluster-wide runtime** — rejected, no tenant tiering possible.
- **Custom CRD with runtime-detection** — rejected, reinvents RuntimeClass.
