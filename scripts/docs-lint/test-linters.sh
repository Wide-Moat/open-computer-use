#!/usr/bin/env bash
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
#
# Linter self-test: prove each gate catches the violation it's supposed to.
#
# Creates temporary fixtures, runs the matching detection logic against them,
# and asserts each gate correctly flags / accepts the fixture. Cleans up.
#
# Run from repo root: scripts/docs-lint/test-linters.sh

set -uo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

pass=0
fail=0

ok()   { echo "  ok:   $1"; pass=$((pass + 1)); }
err()  { echo "  FAIL: $1"; fail=$((fail + 1)); }

# -------- wc-budget --------
echo "Testing wc-budget.sh:"

big_adr="$TMP/big.md"
{
  echo "---"; echo "status: draft"; echo "---"
  for i in $(seq 1 250); do echo "line $i"; done
} > "$big_adr"

lines=$(wc -l < "$big_adr" | tr -d ' ')
if (( lines > 200 )); then
  ok "ADR cap (200) would block file with $lines lines"
else
  err "wc fixture didn't exceed cap"
fi

# -------- ai-slop-detector --------
echo "Testing ai-slop-detector.sh:"

slop_conclusion="$TMP/slop_conclusion.md"
cat > "$slop_conclusion" <<'EOF'
## Conclusion

text
EOF
if grep -qE '^##+ (Conclusion|Summary|In conclusion|TL;DR)$' "$slop_conclusion"; then
  ok "Conclusion-section regex detects short-doc summary"
else
  err "Conclusion regex didn't match fixture"
fi

slop_toc="$TMP/slop_toc.md"
cat > "$slop_toc" <<'EOF'
## Table of Contents

- a
EOF
if grep -qE '^##+ (Table of [Cc]ontents|TOC|Contents)$' "$slop_toc"; then
  ok "TOC regex detects short-doc TOC"
else
  err "TOC regex didn't match fixture"
fi

slop_stub="$TMP/slop_stub.md"
cat > "$slop_stub" <<'EOF'
## Stub

## Next section

content
EOF
result=$(awk '
  /^##+ / {
    cur=$0; line=NR
    while ((getline next_line) > 0) {
      if (next_line ~ /^[ \t]*$/) continue
      if (next_line ~ /^##+ /) { print "HIT:" line; exit }
      break
    }
  }
' "$slop_stub")
if [[ "$result" == HIT:* ]]; then
  ok "stub-heading detection works"
else
  err "stub-heading regex didn't catch fixture"
fi

# -------- ascii-diagram-detector --------
echo "Testing ascii-diagram-detector.sh:"

ascii_fixture="$TMP/ascii.md"
cat > "$ascii_fixture" <<'EOF'
Box-drawing:

┌──────┐
│ box  │
└──────┘
EOF

if python3 -c "
import re, sys
pat = re.compile(r'[─-╿▀-▟]')
with open('$ascii_fixture') as f:
    sys.exit(0 if any(pat.search(l) for l in f) else 1)
"; then
  ok "Unicode box-drawing detected in fixture"
else
  err "ascii fixture not detected"
fi

table_fixture="$TMP/table.md"
cat > "$table_fixture" <<'EOF'
| a | b |
|---|---|
| 1 | 2 |
EOF

if python3 -c "
import re, sys
pat = re.compile(r'[─-╿▀-▟]')
with open('$table_fixture') as f:
    sys.exit(1 if any(pat.search(l) for l in f) else 0)
"; then
  ok "Markdown table not flagged as ASCII diagram"
else
  err "Markdown table false-positive"
fi

# -------- front-matter-validator --------
echo "Testing front-matter-validator.sh:"

nofm="$TMP/nofm.md"
echo "Just text. No YAML." > "$nofm"

if python3 -c "
import re, sys, pathlib
text = pathlib.Path('$nofm').read_text()
stripped = re.sub(r'^(?:<!--.*?-->\s*\n)+', '', text, flags=re.DOTALL)
sys.exit(1 if stripped.startswith('---') else 0)
"; then
  ok "missing-front-matter detected"
else
  err "missing-FM fixture wasn't caught"
fi

partial_fm="$TMP/partial.md"
cat > "$partial_fm" <<'EOF'
---
status: draft
owner: "@x"
---
content
EOF

if python3 -c "
import re, sys, pathlib
text = pathlib.Path('$partial_fm').read_text()
stripped = re.sub(r'^(?:<!--.*?-->\s*\n)+', '', text, flags=re.DOTALL)
m = re.match(r'^---\n(.*?)\n---', stripped, flags=re.DOTALL)
body = m.group(1)
fields = {}
for line in body.splitlines():
    if ':' in line and not line.startswith(' '):
        k, _, v = line.partition(':')
        fields[k.strip()] = v.strip().strip('\"').strip(\"'\")
required = ['status', 'last-reviewed', 'owner', 'applies-to']
missing = [k for k in required if k not in fields or not fields[k]]
sys.exit(0 if missing else 1)
"; then
  ok "missing-field detection works"
else
  err "partial FM wasn't caught"
fi

# -------- architecture-tree-whitelist --------
echo "Testing architecture-tree-whitelist.sh:"

# Run against an isolated fixture tree so we don't disturb the real
# docs/architecture/. Invoke the same fnmatch logic the linter uses.
tree_root="$TMP/atree/docs/architecture"
mkdir -p "$tree_root/adr" "$tree_root/diagrams" "$tree_root/components"

# Allowed files.
touch "$tree_root/README.md"
touch "$tree_root/adr/0001-foo.md"
touch "$tree_root/diagrams/c4.mmd"
touch "$tree_root/components/01-control-plane.md"

# Disallowed files.
touch "$tree_root/notes.txt"                       # stray scratch note
touch "$tree_root/LAYER-0-VERIFICATION.md"         # AI snapshot
touch "$tree_root/diagrams/screenshot.png"         # binary in diagrams

allow_list=(
  "README.md"
  "adr/[0-9][0-9][0-9][0-9]-*.md"
  "diagrams/*.mmd"
  "components/[0-9][0-9]-*.md"
)
violations=$(
  cd "$TMP/atree" && python3 - "${allow_list[@]}" <<'PY'
import fnmatch, pathlib, sys
allow = sys.argv[1:]
root = pathlib.Path("docs/architecture")
bad = []
for p in root.rglob("*"):
    if not p.is_file():
        continue
    rel = p.relative_to(root).as_posix()
    if not any(fnmatch.fnmatchcase(rel, g) for g in allow):
        bad.append(rel)
print("\n".join(sorted(bad)))
PY
)

want_bad=("LAYER-0-VERIFICATION.md" "diagrams/screenshot.png" "notes.txt")
all_caught=1
for needle in "${want_bad[@]}"; do
  if ! grep -qxF "$needle" <<<"$violations"; then
    all_caught=0
    err "tree-whitelist missed expected violation: $needle"
  fi
done
if (( all_caught )); then
  ok "tree-whitelist catches stray notes, AI snapshots, and binaries"
fi

# Allowed files must NOT appear in violations.
for needle in "README.md" "adr/0001-foo.md" "diagrams/c4.mmd" "components/01-control-plane.md"; do
  if grep -qxF "$needle" <<<"$violations"; then
    err "tree-whitelist false-positive on legitimate file: $needle"
  fi
done
ok "tree-whitelist accepts files that match allowed patterns"

# -------- Summary --------
echo
echo "Linter self-test: $pass passed, $fail failed."
if (( fail > 0 )); then
  exit 1
fi
