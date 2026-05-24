#!/usr/bin/env bash
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
#
# ASCII-diagram detector — blocks box-drawing characters in docs/architecture/.
#
# Per CLAUDE.md "Diagrams": Mermaid first; D2/PlantUML when needed; ASCII
# diagrams are forbidden in docs/architecture/ (they don't render in browsers,
# can't be linted for broken references, and signal AI-style ad-hoc artwork).
#
# Box-drawing Unicode ranges: U+2500–U+257F, plus heavy "═║╔╗╚╝╠╣╦╩╬" style.
# Common ASCII fallbacks like `+--+` and `|  |` in tables are NOT flagged —
# they're legitimate Markdown tables.
#
# Exits 1 if any box-drawing characters are found in docs/architecture/.

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# Unicode box-drawing block: ─ │ ┌ ┐ └ ┘ ├ ┤ ┬ ┴ ┼ ═ ║ ╔ ╗ ╚ ╝ ╠ ╣ ╦ ╩ ╬ etc.
pattern=$'[─-╿]'

# Gather .md files under docs/architecture/.
mapfile -t files < <(find docs/architecture -name '*.md' 2>/dev/null)

if (( ${#files[@]} == 0 )); then
  echo "ascii-diagram-detector: OK (no files to scan)"
  exit 0
fi

# Use Python for reliable Unicode-range grep (macOS grep -P is limited).
python3 - "${files[@]}" <<'PY'
import re, sys
pat = re.compile(r"[─-╿▀-▟]")
fail = False
for path in sys.argv[1:]:
    try:
        with open(path, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                if pat.search(line):
                    print(f"FAIL: {path}:{i}: Unicode box-drawing diagram detected")
                    fail = True
    except (OSError, UnicodeDecodeError):
        continue
sys.exit(1 if fail else 0)
PY

status=$?

if (( status != 0 )); then
  echo
  echo "Hint: convert to Mermaid (committed alongside the doc as .mmd, or inline if ≤ 15 lines)."
  exit 1
fi

echo "ascii-diagram-detector: OK"
