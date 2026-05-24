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

  # 6. Self-referential CI / doc-rules meta-noise. Reader does not need to be
  #    told about our line caps, vale lint, banned-vocab list, "diagrams budget"
  #    inside the doc itself. CLAUDE.md is the rule source; the doc carries
  #    content, not rules about itself.
  if grep -nEi '(kept within the [^.]*budget|≤[0-9]+-line (form|cap|budget)|CLAUDE\.md (rules|conventions|line cap|inline-mermaid|Diagrams (budget|rules|inline))|preserve[sd]? .{0,40}(banned-vocab|vale lint)|the surrounding backticks preserve|against (our|the) (project )?banned-vocab)' "$file" > /dev/null; then
    grep -nEi '(kept within the [^.]*budget|≤[0-9]+-line (form|cap|budget)|CLAUDE\.md (rules|conventions|line cap|inline-mermaid|Diagrams (budget|rules|inline))|preserve[sd]? .{0,40}(banned-vocab|vale lint)|the surrounding backticks preserve|against (our|the) (project )?banned-vocab)' "$file"
    echo "FAIL: $file contains self-referential CI / doc-rules meta-noise"
    fail=1
  fi

  # 7. "Holds in spirit" / "honest about" / "as a binding artifact for" —
  #    hedge phrasing that adds no factual content.
  if grep -nEi '(hold[s]? in spirit|honest about (not )?being|the binding artifact for|is what the contract binds)' "$file" > /dev/null; then
    grep -nEi '(hold[s]? in spirit|honest about (not )?being|the binding artifact for|is what the contract binds)' "$file"
    echo "FAIL: $file contains hedge / pompous phrasing"
    fail=1
  fi

  # 8. "the only X" / "is the only" boastful framing — superlative without a
  #    measurable referent. CLAUDE.md "no adjectives without measurable
  #    referent".
  #    Allowed: "is the only zone" / "is the only path" in legitimate context.
  #    Banned: "is the only plaintext segments and …" boastful style.
  if grep -nEi '\b(is|are) the only [a-z]+ (and|listed|that)\b' "$file" > /dev/null; then
    grep -nEi '\b(is|are) the only [a-z]+ (and|listed|that)\b' "$file"
    echo "FAIL: $file contains boastful 'the only X' framing"
    fail=1
  fi

  # 9. Triple parallel construction "X stay in Y; X' stay in Y'; X'' stay in Y''"
  #    pattern. AI loves three-clause parallelism. Looks for repeated verb
  #    three times in one line with semicolons.
  if grep -nE '([A-Za-z]+) [a-z]+ in [^;]+; [A-Za-z]+ \1 [a-z]+ in [^;]+; [A-Za-z]+ \1 [a-z]+ in' "$file" > /dev/null; then
    grep -nE '([A-Za-z]+) [a-z]+ in [^;]+; [A-Za-z]+ \1 [a-z]+ in [^;]+; [A-Za-z]+ \1 [a-z]+ in' "$file"
    echo "FAIL: $file has triple-parallel 'X verbs in Y; X' verbs in Y'; …' construction"
    fail=1
  fi

  # 10. Triple negation "It does NOT X, it does NOT Y, it does NOT Z" pattern.
  if grep -nEi 'does \*?\*?not\*?\*? [^.]+\. (it|It) does \*?\*?not\*?\*? [^.]+\. (it|It) does \*?\*?not\*?\*?' "$file" > /dev/null; then
    grep -nEi 'does \*?\*?not\*?\*? [^.]+\. (it|It) does \*?\*?not\*?\*? [^.]+\. (it|It) does \*?\*?not\*?\*?' "$file"
    echo "FAIL: $file has triple-negation 'It does not X. It does not Y. It does not Z' construction"
    fail=1
  fi

  # 11. List-of-three "no X, no Y, no Z" inside parentheses.
  if grep -nE '\(no [a-z-]+, no [a-z-]+, no [a-z-]+\)' "$file" > /dev/null; then
    grep -nE '\(no [a-z-]+, no [a-z-]+, no [a-z-]+\)' "$file"
    echo "FAIL: $file has list-of-three '(no X, no Y, no Z)' construction"
    fail=1
  fi
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
