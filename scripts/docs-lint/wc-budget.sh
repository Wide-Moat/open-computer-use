#!/usr/bin/env bash
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
#
# Line-count budget enforcer for architecture docs.
#
# Per CLAUDE.md "Documentation discipline":
#   - ADR ≤ 200 lines (under docs/architecture/adr/, excluding README/template)
#   - Component spec ≤ 600 lines (under docs/architecture/components/, excluding README/template)
#   - MANIFESTO.md ≤ 400 lines
#
# Exits 1 if any cap is exceeded.

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

fail=0

check_cap() {
  local file="$1" cap="$2" kind="$3"
  if [[ ! -f "$file" ]]; then
    return 0
  fi
  local lines
  lines=$(wc -l < "$file" | tr -d ' ')
  if (( lines > cap )); then
    echo "FAIL: $kind cap exceeded: $file = $lines lines (cap $cap)"
    fail=1
  fi
}

# MANIFESTO.md (single file).
check_cap "docs/architecture/MANIFESTO.md" 400 "MANIFESTO"

# All ADRs except the template and the README.
while IFS= read -r -d '' f; do
  base="$(basename "$f")"
  if [[ "$base" == "README.md" || "$base" == "0000-template.md" ]]; then
    continue
  fi
  check_cap "$f" 200 "ADR"
done < <(find docs/architecture/adr -name '*.md' -print0 2>/dev/null)

# All component specs except the template.
while IFS= read -r -d '' f; do
  base="$(basename "$f")"
  if [[ "$base" == "0000-template.md" ]]; then
    continue
  fi
  check_cap "$f" 600 "component-spec"
done < <(find docs/architecture/components -name '*.md' -print0 2>/dev/null)

if (( fail )); then
  echo
  echo "Hint: split the doc, move detail into a linked ADR, or trim prose."
  exit 1
fi

echo "wc-budget: OK"
