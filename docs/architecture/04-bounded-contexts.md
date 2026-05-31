<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: proposed
last-reviewed: 2026-05-31
owner: "@Wide-Moat/architects"
applies-to: next/v1
---

Cuts the domain into bounded contexts and classifies each as core, supporting, or generic — the buy-vs-build call. Audience: anyone deciding what we build and what we integrate.

## 1. Context layer vs trust zones

[`02-trust-boundaries.md`](02-trust-boundaries.md) §2 draws six zones — Control plane, Credential custody, Storage broker, Compute plane, Egress trust-edge, Audit pipeline. Those answer "where does it run and under what protection." This layer answers a different question: "which slices of the domain carry the competitive value, and which are solved problems we integrate." A trust zone is a deploy/protection slice; a bounded context is a domain slice. They do not map one-to-one, and the mismatches are the point.

The classification drives the next layer: a context marked `generic` becomes an integration in [`03-c4-context.md`](03-c4-context.md)'s external-actor set, not a container we build; a `core` context becomes containers we own in the C4 Container layer.

## 2. Subdomain classification

```mermaid
flowchart TB
    subgraph CORE["Core — built in-house"]
        AEX["Agent Execution &amp; Sandbox Lifecycle"]
        CEV["Compliance Evidence &amp; Audit Lineage"]
    end
    subgraph SUP["Supporting — built, not differentiating"]
        TEN["Tenancy &amp; Isolation"]
        OPA["Operator Access"]
    end
    subgraph GEN["Generic — integrated, not built"]
        IDF["Identity federation"]
        SEC["Secrets custody"]
        POL["Policy evaluation"]
    end
    AEX -->|"OCSF event"| CEV
    style CORE fill:#e8f5e9,stroke:#1e7e34,stroke-width:3px
    style SUP fill:#fff8e1,stroke:#b8860b
    style GEN fill:#f5f5f5,stroke:#9e9e9e,stroke-dasharray:5 5
```

The diagram shows only the core-to-core domain edge; the full set of context relationships (inbound, generic integrations) is the context map in §4.

| Subdomain | Class | Value axis | Build-vs-buy |
|---|---|---|---|
| **Agent Execution & Sandbox Lifecycle** | core | domain complexity — safely executing adversarial agent-issued tool-calls and code in-perimeter | build |
| **Compliance Evidence & Audit Lineage** | core | domain complexity — binding every agent action into a replayable, hash-linked lineage that survives an adversarial workload (the lineage, not the OCSF schema or the SIEM sink, is the defensible part) | build |
| **Tenancy & Isolation** | supporting | owns the T0–T3 isolation-tier selection logic | build |
| **Operator Access** | supporting | owns the PAM-JIT human-to-platform contract ([NFR-COMP-29](manifesto/02-nfrs.md)); bespoke to us, sits outside the value axis | build |
| **Identity federation** | generic | relying-party to customer IdP | integrate |
| **Secrets custody** | generic | key custody behind PKCS#11 / KMIP | integrate |
| **Policy evaluation** | generic | externalised authorization decisions | integrate |

Source availability is a go-to-market property, not a classification axis. The security primitives ship in the open artifact ([`01-audience-and-buyer.md`](manifesto/01-audience-and-buyer.md) §"Audience"); that does not demote Agent Execution to generic. Applying an open runtime correctly to adversarial in-perimeter agent-issued code is where the domain complexity sits, so it stays core.

Compliance Evidence is core for the same reason — domain depth, not deal-decisiveness. It clears the TPRM veto (the buyer chain in `01-audience-and-buyer.md`), but that proves it is commercially important, not that it is core. What makes it core is the *lineage*: the OCSF schema, the pluggable SIEM sinks, and the customer-chosen transparency log are generic substrate we integrate; reconstructing a tamper-evident, replayable chain of agent actions across an adversarial workload is the part no competitor hands over and the part we build.

## 3. Trust zones to contexts

The six zones group into two core contexts. The mismatch is deliberate: five zones collapse into one context, one zone is a context of its own.

| Trust zone (Layer 3 §2) | Bounded context | Why this grouping |
|---|---|---|
| Control plane | Agent Execution | session lifecycle is execution machinery |
| Compute plane (sandbox) | Agent Execution | the sandbox is where the tool-calls execute |
| Credential custody | Agent Execution | host-side custody feeds the egress edge that serves the session |
| Storage broker | Agent Execution | host-side broker serves the session's user-data mount |
| Egress trust-edge | Agent Execution | the single outbound path is part of running safely |
| Audit pipeline | Compliance Evidence | different reason to exist: prove, not run |

The Audit pipeline is its own zone in Layer 3 for retention/RPO/tamper-evidence reasons; it is its own context here for a domain reason — its value is regulatory proof, a separate axis from execution.

Merging five zones into one context passes the linguistic test only because they share one ubiquitous language: "execute the tool-calls a client sends, safely, in-perimeter." The Control plane and Compute plane unambiguously speak that one execution language. Credential custody (custody terms: `upstream-credential`, `rotation`, `lease`, `delegated-STS`), the Storage broker (mount terms: `filesystem_id`, `resource-handle`, `backend-credential`; north-face delivery terms: `artifact`, `preview`, `downloadable`, `SPA-render`), and the Egress trust-edge (enforcement and injection terms: `SNI pre-filter`, `MITM mode`, `x-deny-reason`, `auth-injection`) speak narrower sub-languages; they sit *inside* Agent Execution, not as separate contexts, because their invariants exist only to serve the running session and they share its aggregate root (the session). Whether custody earns its own context is tracked in §5.

The supporting and generic contexts are not Layer 3 zones we own. Of the three generic contexts, two are Layer 3 §3 external actors — Identity federation (Customer IdP) and Secrets custody (Customer KMS / HSM). Policy evaluation is not yet drawn in Layer 3; it is consumed at two sub-zones of Agent Execution — the Egress trust-edge (egress allow-list) and Credential custody (credential-scope selection) — and Layer 6 splits the anti-corruption layer accordingly. The remaining Layer 3 §3 actors are not new contexts: Customer SIEM, SOAR, and the transparency log are downstream consumers of the Compliance Evidence context (§4); the customer outbound proxy and DLP-ICAP are configurations of the Egress trust-edge already inside Agent Execution. An LLM, if a sandbox tool reaches one, is just another allow-listed egress endpoint behind that edge — not a context we model.

## 4. Context map

```mermaid
flowchart LR
    IDF["Identity federation<br/>(generic)"]
    SEC["Secrets custody<br/>(generic)"]
    POL["Policy evaluation<br/>(generic)"]
    MCP["MCP caller<br/>(upstream; runs the loop)"]
    OPER["Operator<br/>(PAM-JIT human)"]
    AEX["Agent Execution<br/>(core)"]
    CEV["Compliance Evidence<br/>(core)"]
    SINK["SIEM · SOAR · transparency log<br/>(downstream consumers)"]
    MCP -->|"Conformist:<br/>MCP authz spec"| AEX
    OPER -->|"Customer/Supplier:<br/>PAM-JIT (NFR-COMP-29)"| AEX
    IDF -->|"Anti-corruption layer"| AEX
    SEC -->|"Anti-corruption layer"| AEX
    POL -->|"Anti-corruption layer"| AEX
    AEX -->|"Open Host Service +<br/>Published Language: OCSF"| CEV
    CEV -->|"OCSF bridges"| SINK
    style AEX fill:#e8f5e9,stroke:#1e7e34,stroke-width:2px
    style CEV fill:#e8f5e9,stroke:#1e7e34,stroke-width:2px
    style IDF fill:#f5f5f5,stroke:#9e9e9e,stroke-dasharray:5 5
    style SEC fill:#f5f5f5,stroke:#9e9e9e,stroke-dasharray:5 5
    style POL fill:#f5f5f5,stroke:#9e9e9e,stroke-dasharray:5 5
    style SINK fill:#f5f5f5,stroke:#9e9e9e,stroke-dasharray:5 5
    style MCP fill:#fdecea,stroke:#c0392b
    style OPER fill:#fdecea,stroke:#c0392b
```

| Relationship | From → To | Pattern | What it commits to |
|---|---|---|---|
| Execution emits evidence | Agent Execution → Compliance Evidence | Open Host Service + Published Language | OCSF v1.x is the published schema; Compliance Evidence is the host with fan-in from five Layer 3 zones and fan-out to multiple SIEMs. The emitter conforms to the schema, not to the consumer's internals ([glossary: OCSF](glossary.md#ocsf)) |
| Inbound tool calls | MCP caller → Agent Execution | Conformist | we conform to the MCP authorization spec; we do not define it |
| Operator access | Operator → Agent Execution | Customer/Supplier | PAM-JIT human-to-platform contract ([NFR-COMP-29](manifesto/02-nfrs.md)); host-rooted credential on the minimal shelf, SAML-asserted attribute on the full shelf |
| Generic integrations | {Identity, Secrets, Policy} → Agent Execution | Anti-corruption layer | each vendor's interface is translated at the boundary so a vendor swap does not reach the core |
| Evidence to sinks | Compliance Evidence → SIEM / SOAR / transparency log | Open Host Service | OCSF bridges and the submission envelope; the consumer adapts, not us |

The anti-corruption layer is what lets Identity, Secrets, and Policy stay `integrate`: the vendor (Keycloak, OpenBao, OPA) can change without the core's domain changing. An LLM is not among them — it is reached, if at all, as one allow-listed egress endpoint, and the agent loop that would call it runs in the MCP caller. The two core contexts share the OCSF event and nothing else — no shared identifier type, no shared library — so the Published Language does not degrade into a shared kernel that would bind their release cadences.

## 5. Open questions

1. Does Tenancy & Isolation stay supporting, or split a `core` sub-slice once multi-tenant agent-execution grading lands? — [#165](https://github.com/Wide-Moat/open-computer-use/issues/165).
2. Does the PAM-JIT contract keep Operator Access as its own supporting context, or fold it into Agent Execution? — [#166](https://github.com/Wide-Moat/open-computer-use/issues/166).
3. Is workload-trust sandbox-tier grading (`workload_trust_profile`, AP-13) a sub-context of its own, distinct from the session-lifecycle language inside Agent Execution? — [#168](https://github.com/Wide-Moat/open-computer-use/issues/168).
4. Does Credential custody collapse into the generic Secrets custody context now that injection lives at the egress edge, or stay a distinct concern inside Agent Execution? — [#169](https://github.com/Wide-Moat/open-computer-use/issues/169).
