#!/usr/bin/env bash
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
#
# architecture-tree-whitelist — fail when an unexpected file appears under
# `docs/architecture/`. Each directory has a known set of allowed files and
# filename patterns. Anything outside the whitelist signals that:
#
#   - someone wrote a verifier snapshot, scratch note, or AI artifact into
#     the architecture set (drift the moment the next pass runs), OR
#   - someone added a new directory without following PROCESS.md, OR
#   - a typo / wrong location for an otherwise legitimate file.
#
# Each new component / ADR / mapping that needs a new file shape must:
#   1. follow PROCESS.md "Adding a <thing>",
#   2. update this whitelist in the same PR.
#
# Run from repo root: scripts/docs-lint/architecture-tree-whitelist.sh

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

if [ ! -d docs/architecture ]; then
  echo "architecture-tree-whitelist: docs/architecture/ does not exist, nothing to check"
  exit 0
fi

# Per-directory allow-list. `*` is a glob, not regex; it matches anything
# except `/` (so `compliance/*-mapping.md` does not match `compliance/sub/x.md`).
ALLOWED=(
  # Top-level architecture-set roots.
  "README.md"
  "MANIFESTO.md"
  "glossary.md"
  "PROCESS.md"
  "primitives-backlog.md"

  # Top-level numbered cross-cutting artifacts (scope cuts across the whole
  # tree, cited by every component spec — e.g. trust boundaries, C4 context,
  # deployment topologies). Per PROCESS.md, these live at the top level rather
  # than under `manifesto/` or `components/`.
  "[0-9][0-9]-*.md"

  # ADRs.
  "adr/README.md"
  "adr/0000-template.md"
  "adr/[0-9][0-9][0-9][0-9]-*.md"

  # Component specs.
  "components/README.md"
  "components/0000-template.md"
  "components/[0-9][0-9]-*.md"

  # Manifesto sections (one numbered file per section).
  "manifesto/README.md"
  "manifesto/[0-9][0-9]-*.md"

  # Compliance — only the cross-framework matrix and per-framework mappings.
  "compliance/README.md"
  "compliance/controls-matrix.md"
  "compliance/*-mapping.md"
  "compliance/sub-processors.md"

  # Diagrams — Mermaid / D2 / PlantUML sources. PNG / JPG forbidden (CLAUDE.md §Diagrams).
  "diagrams/README.md"
  "diagrams/*.mmd"
  "diagrams/*.d2"
  "diagrams/*.puml"
  # Exception (recorded in docs/architecture/README.md, "At a glance"): the
  # component-map overview is a draw.io source — the single source of truth a
  # Mermaid container diagram cannot reproduce — committed with its rendered SVG
  # so the README can embed it. CLAUDE.md §Diagrams otherwise forbids SVG for
  # our own diagrams; this is the one allowed pair, kept pretty-printed so the
  # SVG diffs line-by-line.
  "diagrams/architecture-overview.drawio"
  "diagrams/architecture-overview.svg"

  # Threat models — Threagile / pytm YAML.
  "threat-model/README.md"
  "threat-model/*.yaml"
  "threat-model/*.yml"

  # Contracts — OpenAPI / AsyncAPI / Protobuf / MCP schema.
  "contracts/README.md"
  "contracts/*.yaml"
  "contracts/*.yml"
  "contracts/*.json"
  "contracts/*.proto"

  # gitkeep markers for empty scaffold directories. The `?` is a literal
  # filename character set by the glob translator; here we match exactly
  # ".gitkeep" anywhere one directory deep under docs/architecture/.
  "*/.gitkeep"
)

python3 - "${ALLOWED[@]}" <<'PY'
import fnmatch, pathlib, sys

allowed_globs = sys.argv[1:]
root = pathlib.Path("docs/architecture")

def match_pattern(rel: str, pattern: str) -> bool:
    """Segment-aware glob match. `*` never crosses `/`.

    Plain `fnmatch.fnmatchcase` treats `/` as a normal character, so
    `compliance/*-mapping.md` would silently accept
    `compliance/sub/evil-mapping.md`. We split on `/` and require equal
    depth + per-segment match instead.
    """
    rel_parts = rel.split("/")
    pat_parts = pattern.split("/")
    if len(rel_parts) != len(pat_parts):
        return False
    return all(fnmatch.fnmatchcase(r, p) for r, p in zip(rel_parts, pat_parts))

fail = False
for path in root.rglob("*"):
    if not path.is_file():
        continue
    rel = path.relative_to(root).as_posix()
    if not any(match_pattern(rel, g) for g in allowed_globs):
        print(f"FAIL: docs/architecture/{rel} — file not on the whitelist")
        fail = True

if fail:
    print("""
Hint: every file under docs/architecture/ must match a whitelist entry in
scripts/docs-lint/architecture-tree-whitelist.sh. If the file is legitimate
(new component, new compliance mapping, new diagram), add the matching
pattern to ALLOWED in the same PR. If it is a scratch note, verifier
snapshot, or AI artifact — delete it. Process: docs/architecture/PROCESS.md
and CLAUDE.md "Architecture content routing".
""")
    sys.exit(1)

print("architecture-tree-whitelist: OK")
PY
