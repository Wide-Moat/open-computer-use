#!/bin/bash
# SPDX-License-Identifier: BUSL-1.1
# Copyright (c) 2025 Open Computer Use Contributors
# Test: No Cyrillic characters in repository source/docs.
#
# Repo policy (CLAUDE.md): English-only. No exceptions.
#
# Usage: ./tests/test-no-cyrillic.sh [project-root]
# Exit code: 0 = clean, 1 = Cyrillic found

set -euo pipefail

ROOT="${1:-$(cd "$(dirname "$0")/.." && pwd)}"

cd "$ROOT"

echo "=== Testing: No Cyrillic characters in $ROOT ==="
echo ""

# Use Python for portable Unicode regex (BSD grep on macOS has no PCRE,
# and CI runs on Ubuntu — keep one impl).
python3 - <<'PY'
import os, re, sys

CYR = re.compile(r'[Ѐ-ӿ]')

EXTS = {'.py', '.js', '.ts', '.tsx', '.jsx', '.go', '.rs', '.sh',
        '.yml', '.yaml', '.toml', '.md', '.json', '.html', '.css',
        '.proto', '.mk'}
SPECIAL_NAMES = {'Dockerfile', 'Makefile'}

SKIP_DIR_PREFIXES = (
    './.git/', './.venv/', './.venv-itest/', './.venv-review/',
    './node_modules/', './__pycache__/', './.claude/', './.planning/',
    './references/', './sandboxd/', './dist/', './build/',
)
SKIP_FILES = {
    './tests/test-no-cyrillic.sh',
}

def included(path):
    if path in SKIP_FILES:
        return False
    if any(path.startswith(p) for p in SKIP_DIR_PREFIXES):
        return False
    name = os.path.basename(path)
    if name == 'locale.js' or name.endswith('.min.js'):
        return False
    if any(name.startswith(p) for p in SPECIAL_NAMES):
        return True
    _, ext = os.path.splitext(name)
    return ext in EXTS

bad = []
for dirpath, dirnames, filenames in os.walk('.'):
    dirnames[:] = [d for d in dirnames if not any(
        (dirpath + '/' + d + '/').startswith(p) for p in SKIP_DIR_PREFIXES
    )]
    for name in filenames:
        path = os.path.join(dirpath, name)
        if not included(path):
            continue
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                for lineno, line in enumerate(f, 1):
                    if CYR.search(line):
                        bad.append((path, lineno, line.rstrip()))
        except (OSError, UnicodeDecodeError):
            continue

if not bad:
    print("  PASS: no Cyrillic found")
    print("")
    print("=== Test passed ===")
    sys.exit(0)

print(f"  FAIL: {len(bad)} line(s) contain Cyrillic characters\n")
print("Offending lines (path:line:content):")
for path, lineno, line in bad[:50]:
    print(f"    {path}:{lineno}:{line}")
if len(bad) > 50:
    print(f"    ... and {len(bad) - 50} more")
print("")
print("Policy (CLAUDE.md): repo is English-only. Rewrite affected lines.")
print("")
print("=== Test FAILED ===")
sys.exit(1)
PY
