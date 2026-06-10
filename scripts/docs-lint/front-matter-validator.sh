#!/usr/bin/env bash
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
#
# Front-matter validator — every doc under docs/architecture/ MUST carry the
# four mandatory YAML fields per CLAUDE.md "Documentation discipline":
#   status, last-reviewed (YYYY-MM-DD), owner, applies-to
#
# Also emits a non-blocking WARN if last-reviewed > 180 days old.
#
# Exits 1 if any required field is missing from any architecture doc.

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

fail=0
today_epoch=$(date +%s)
stale_threshold=$((180 * 24 * 3600))

check_file() {
  local file="$1"
  python3 - "$file" "$today_epoch" "$stale_threshold" <<'PY'
import re, sys, datetime as dt, pathlib

path = pathlib.Path(sys.argv[1])
today_epoch = int(sys.argv[2])
stale_threshold = int(sys.argv[3])

text = path.read_text(encoding="utf-8")

# Strip leading HTML license comments (the SPDX header convention).
stripped = re.sub(r'^(?:<!--.*?-->\s*\n)+', '', text, flags=re.DOTALL)

if not stripped.startswith('---'):
    print(f"FAIL: {path}: no YAML front-matter block")
    sys.exit(1)

m = re.match(r'^---\n(.*?)\n---', stripped, flags=re.DOTALL)
if not m:
    print(f"FAIL: {path}: front-matter block not closed with `---`")
    sys.exit(1)

body = m.group(1)
fields = {}
for line in body.splitlines():
    line = line.rstrip()
    if not line or line.startswith('#'):
        continue
    if ':' not in line or line.startswith((' ', '\t', '-')):
        continue
    key, _, val = line.partition(':')
    fields[key.strip()] = val.strip().strip('"').strip("'")

required = ["status", "last-reviewed", "owner", "applies-to"]
missing = [k for k in required if k not in fields or not fields[k]]
if missing:
    print(f"FAIL: {path}: missing front-matter fields: {', '.join(missing)}")
    sys.exit(1)

# Accept the literal placeholder YYYY-MM-DD only in template files.
last_reviewed = fields["last-reviewed"]
if last_reviewed == "YYYY-MM-DD":
    if "template" not in path.name.lower():
        print(f"FAIL: {path}: last-reviewed is placeholder 'YYYY-MM-DD' in a non-template file")
        sys.exit(1)
    sys.exit(0)

try:
    parsed = dt.date.fromisoformat(last_reviewed)
except ValueError:
    print(f"FAIL: {path}: last-reviewed '{last_reviewed}' is not YYYY-MM-DD")
    sys.exit(1)

age = today_epoch - int(dt.datetime.combine(parsed, dt.time()).timestamp())
if age > stale_threshold:
    print(f"WARN: {path}: last-reviewed {last_reviewed} is over 180 days old")
    # Non-blocking — exit 0.

sys.exit(0)
PY
}

while IFS= read -r -d '' f; do
  if ! check_file "$f"; then
    fail=1
  fi
done < <(find docs/architecture -name '*.md' -print0 2>/dev/null)

if (( fail )); then
  echo
  echo "Hint: add YAML front-matter with status, last-reviewed (YYYY-MM-DD), owner, applies-to."
  exit 1
fi

echo "front-matter-validator: OK"
