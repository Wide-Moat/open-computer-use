#!/bin/bash
# SPDX-License-Identifier: BUSL-1.1
# Copyright (c) 2025 Open Computer Use Contributors
# Test: No Cyrillic characters in repository source/docs.
#
# Repo policy (CLAUDE.md): all code, comments, commit messages, PR titles,
# PR descriptions, documentation, and any text visible in the repository
# MUST be written in English only. No exceptions.
#
# This script enforces that policy.
#
# Usage: ./tests/test-no-cyrillic.sh [project-root]
# Exit code: 0 = clean, 1 = Cyrillic found

set -euo pipefail

ROOT="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
SCRIPT_NAME="$(basename "$0")"

cd "$ROOT"

# What we scan: text-y source + docs. Skip vendored / minified / binary.
INCLUDE_GLOBS=(
    '--include=*.py'
    '--include=*.js'
    '--include=*.ts'
    '--include=*.tsx'
    '--include=*.jsx'
    '--include=*.go'
    '--include=*.rs'
    '--include=*.sh'
    '--include=*.yml'
    '--include=*.yaml'
    '--include=*.toml'
    '--include=*.md'
    '--include=*.json'
    '--include=*.html'
    '--include=*.css'
    '--include=*.proto'
    '--include=Dockerfile*'
    '--include=Makefile*'
    '--include=*.mk'
)

# What we skip:
#   - VCS / dep / build caches
#   - vendored repos (we shallow-cloned references/ to /references at repo root; git-ignored, but also fence here)
#   - sandboxd/ (external reference design, may contain quotes in original language)
#   - this script itself + corporate-patterns.txt + test-no-corporate.sh (intentional regex patterns)
#   - minified JS bundles (locale tables, xlsx, etc.)
EXCLUDE_DIRS=(
    '--exclude-dir=.git'
    '--exclude-dir=.venv'
    '--exclude-dir=.venv-itest'
    '--exclude-dir=.venv-review'
    '--exclude-dir=node_modules'
    '--exclude-dir=__pycache__'
    '--exclude-dir=.claude'
    '--exclude-dir=.planning'
    '--exclude-dir=references'
    '--exclude-dir=sandboxd'
    '--exclude-dir=dist'
    '--exclude-dir=build'
)

EXCLUDE_FILES=(
    "--exclude=$SCRIPT_NAME"
    '--exclude=test-no-corporate.sh'
    '--exclude=corporate-patterns.txt'
    # Minified i18n bundles in Open WebUI static assets.
    '--exclude=locale.js'
    '--exclude=*.min.js'
)

echo "=== Testing: No Cyrillic characters in $ROOT ==="
echo ""

# Cyrillic range: U+0400-U+04FF covers Russian + most Slavic.
# Use --binary-files=without-match so a stray binary doesn't blow up the run.
HITS=$(grep -rn --binary-files=without-match -P '[\x{0400}-\x{04FF}]' \
    "${INCLUDE_GLOBS[@]}" \
    "${EXCLUDE_DIRS[@]}" \
    "${EXCLUDE_FILES[@]}" \
    . 2>/dev/null || true)

if [ -z "$HITS" ]; then
    echo "  PASS: no Cyrillic found"
    echo ""
    echo "=== Test passed ==="
    exit 0
fi

COUNT=$(echo "$HITS" | wc -l | tr -d ' ')

echo "  FAIL: $COUNT line(s) contain Cyrillic characters"
echo ""
echo "Offending lines (file:line:content):"
echo "$HITS" | sed 's/^/    /'
echo ""
echo "Policy (CLAUDE.md): repo is English-only. Rewrite the affected lines"
echo "before committing. Quotes from external sources must be translated"
echo "or paraphrased; original-language source goes in an external reference,"
echo "not committed."
echo ""
echo "=== Test FAILED ==="
exit 1
