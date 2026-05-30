<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# 09 — Sandbox Templates

> The configurable, version-pinned recipe that produces a sandbox.
> Tenant tier → template → image + runtime + resources + mounts + network + egress allowlist.

## Why templates are first-class

User requirement: *the container itself must be configurable via templates.* The template object decouples *what tenants get* from *how providers implement it*.

## Schema (target)

Conceptually CRD-shaped (k8s) but the same object lives in Compose (YAML file) and DirectCH (TOML). Provider materializes it.

```yaml
apiVersion: sandbox.openchatcomputeruse.io/v1
kind: SandboxTemplate
metadata:
  name: computer-use-untrusted-v3
  labels:
    tier: untrusted
    purpose: computer-use
spec:
  image:
    ref: ghcr.io/wide-moat/open-computer-use@sha256:abcdef…
    signature: required           # cosign verified by admission

  runtime_class: kata-ch          # see 04-layer2-runtimes.md
  envtype: customer-cu            # L3 dispatch key — see 03-layer3-providers.md
  snapstart_compatible: false     # Phase 10 only; set true when template ships paired squashfs blobs (see 06-storage.md)

  resources:
    cpu:   "2"
    mem:   "2Gi"
    disk:  "10Gi"

  pool:
    minSize: 2
    targetSize: 5
    maxSize: 20
    idleTimeoutSeconds: 600

  mounts:                         # see 06-storage.md
    - type: skill
      refs:
        - { name: pptx,   sha256: … }
        - { name: docx,   sha256: … }
    - type: workspace
      persistence: ephemeral
    - type: user-data
      backend: s3
      bucket: tenant-{tenant_id}-data

  env_template:                   # rendered at /v1/configure with session ctx
    PUBLIC_BASE_URL: "{public_base_url}"
    SUBAGENT_CLI:   "claude"
    # NO SECRETS HERE — secret broker injects them

  egress_baseline:                # added to per-session JWT allowlist
    - "*.anthropic.com"
    - "pypi.org"
    - "files.pythonhosted.org"
    - "registry.npmjs.org"
    - "github.com"
    - "objects.githubusercontent.com"

  security:
    runAsNonRoot: false           # sysbox/kata allow safe root
    seccompProfile: RuntimeDefault
    dropCapabilities: ["ALL"]
    addCapabilities: []           # template can request specific caps with justification
```

## Tenant → template mapping

L4 resolves at session creation:

```python
template = TemplateResolver.resolve(
    tenant_tier,          # e.g. "internal-employee", "paid-customer", "trial"
    workload_kind,        # e.g. "computer-use", "code-exec"
    region,
)
```

Examples:
- Internal employee + code-exec → `internal-code-sysbox-v2`
- Paid customer + Computer Use → `customer-cu-kata-ch-v3`
- Free trial + Computer Use → `trial-cu-kata-fc-v1`

The mapping is policy held in L4 config (DB-backed in Phase 6+). Admin UI edits it.

## Template lifecycle

- **Created** by ops via admin API (Phase 6+) or YAML in Helm values pre-Phase-6.
- **Validated** at admission: image signature, mount sanity, resource within cluster quotas.
- **Versioned**: name carries `vN`. Old version stays until its referenced sessions drain. No mutation in place.
- **Deprecated** via label; new sessions get the latest non-deprecated.

## Two new fields, briefly

- **`envtype`** — the L3 dispatch key. Picks the backend mechanism (Docker Compose vs k8s vs DirectCH, plus the egress-proxy enforcement mode). Values: `dev`, `internal`, `customer-shared`, `customer-cu`, `anthropic-hosted`, `byoc`. Full matrix in [`03-layer3-providers.md`](./03-layer3-providers.md) "Environment-type dispatch (Baku pattern)". Distinct from `runtime_class` — `envtype` says *where it runs*, `runtime_class` says *what isolates it*.
- **`snapstart_compatible`** — Phase-10-only flag. When `true`, the template's release pipeline produced paired Tier-2 squashfs blobs (`vdb`, `vdc`) alongside the OCI image, and the template is wired for block-device hot-swap on resume ([`06-storage.md`](./06-storage.md) block-device tooling swap). Phase 9 templates are always `false`. Templates without paired blobs are rejected by admission when this flag is `true`.

## Per-phase progression

| Phase | Templates state |
|---|---|
| 1 | None — single hardcoded config inherited from today's compose |
| 2 | One template per provider, declared in code |
| 3 | Mounts spec real (skills + S3) |
| 4 | Egress baseline + env_template separated from secrets |
| 5 | Templates become CRD-shaped in k8s (via `agent-sandbox` `SandboxTemplate`) |
| 6 | Admin UI CRUD + tenant→template resolver in L4 |
| 8 | Multi-tier templates (sysbox / gVisor / kata-* fully wired) |

## Source

- Internal design notes (template patterns)
- [`kubernetes-sigs/agent-sandbox`](https://github.com/kubernetes-sigs/agent-sandbox) — `SandboxTemplate` CRD basis
