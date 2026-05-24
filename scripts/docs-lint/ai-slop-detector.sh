#!/usr/bin/env bash
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
#
# AI-slop detector — patterns that flag AI-generated bloat.
#
# Complements vale (which checks banned vocab/phrases in prose). This script
# catches structural patterns vale can't see: TOCs in short docs, reflexive
# Conclusion sections, decorative dividers for one-paragraph content,
# stub headings, file openings that restate project scope.
#
# Exits 1 on any hit.

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

fail=0

# Scope: docs/architecture/, CLAUDE.md, README.md, CONTRIBUTING.md.
mapfile -d '' files < <(
  find docs/architecture -name '*.md' -print0 2>/dev/null
  printf '%s\0' CLAUDE.md README.md CONTRIBUTING.md 2>/dev/null
)

check() {
  local file="$1" lines="$2"

  # 1. File begins with "open-computer-use is …" (restating project scope).
  if awk 'NR<=20 && /^[Oo]pen [Cc]omputer [Uu]se is /' "$file" | grep -q .; then
    echo "FAIL: $file restates project scope in first 20 lines"
    fail=1
  fi

  # 2. Conclusion / Summary section in a short doc (< 1000 lines).
  if (( lines < 1000 )) && grep -qE '^##+ (Conclusion|Summary|In conclusion|TL;DR)$' "$file"; then
    echo "FAIL: $file has a Conclusion/Summary section in a doc shorter than 1000 lines"
    fail=1
  fi

  # 3. Table of Contents in a short doc (≤ 500 lines).
  if (( lines <= 500 )) && grep -qE '^##+ (Table of [Cc]ontents|TOC|Contents)$' "$file"; then
    echo "FAIL: $file has a TOC in a doc ≤ 500 lines (headings already navigate)"
    fail=1
  fi

  # 4. Decorative emoji headers.
  if grep -qE '^##+ [^A-Za-z0-9`<\(\[]' "$file"; then
    if grep -nE '^##+ [^A-Za-z0-9`<\(\[]' "$file" | grep -v '^[0-9]*:##* [#]' > /dev/null; then
      echo "WARN: $file may have decorative-character headings (manually verify)"
    fi
  fi

  # 5. Stub headings (heading immediately followed by another heading or EOF).
  awk '
    /^##+ / {
      cur=$0; line=NR
      while ((getline next_line) > 0) {
        if (next_line ~ /^[ \t]*$/) continue
        if (next_line ~ /^##+ /) {
          print FILENAME ":" line ": stub heading (no content before next heading): " cur
          exit 1
        }
        break
      }
    }
  ' "$file" | grep . && fail=1 || true
}

for f in "${files[@]}"; do
  [[ -f "$f" ]] || continue
  lines=$(wc -l < "$f" | tr -d ' ')
  check "$f" "$lines"
done

if (( fail )); then
  echo
  echo "Hint: see CLAUDE.md 'Documentation discipline' for the banned patterns."
  exit 1
fi

echo "ai-slop-detector: OK"
