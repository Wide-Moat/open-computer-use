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
import os, re, subprocess, sys

CYR = re.compile(r'[Ѐ-ӿ]')

# Denylist approach: scan EVERY tracked text file. The previous extensions
# allowlist let Cyrillic slip in via unlisted extensions (e.g. `.txt`,
# `.cfg`, `.env.example`). Skip only known-binary extensions, vendored
# trees, and the explicit self-reference below.
SKIP_DIR_PREFIXES = (
    '.git/', '.venv/', '.venv-itest/', '.venv-review/',
    'node_modules/', '__pycache__/', '.claude/', '.planning/',
    'references/', 'sandboxd/', 'dist/', 'build/',
)
SKIP_FILES = {
    'tests/test-no-cyrillic.sh',
}
# Binary / generated extensions. Avoid scanning these for both performance
# and to prevent false positives on encoded payloads.
BINARY_EXTS = {
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.webp', '.svg',
    '.pdf', '.zip', '.tar', '.gz', '.bz2', '.xz', '.7z',
    '.woff', '.woff2', '.ttf', '.otf', '.eot',
    '.mp3', '.mp4', '.mov', '.avi', '.webm', '.ogg', '.wav',
    '.so', '.dylib', '.dll', '.exe', '.bin', '.o', '.a',
    '.pyc', '.pyo', '.class', '.jar',
    '.lock', '.min.js', '.min.css',
}
SKIP_BASENAMES = {'locale.js'}

def listed_files():
    """All files tracked by git, excluding deletions. Falls back to a
    plain os.walk if git is unavailable (e.g. tarball checkout)."""
    try:
        out = subprocess.check_output(
            ['git', 'ls-files', '-z'], stderr=subprocess.DEVNULL,
        )
        return [p for p in out.decode('utf-8', errors='replace').split('\0') if p]
    except (FileNotFoundError, subprocess.CalledProcessError):
        files = []
        for dirpath, dirnames, filenames in os.walk('.'):
            rel = dirpath[2:] + '/' if dirpath.startswith('./') else dirpath + '/'
            dirnames[:] = [
                d for d in dirnames
                if not any((rel + d + '/').startswith(p) for p in SKIP_DIR_PREFIXES)
            ]
            for name in filenames:
                files.append(os.path.normpath(os.path.join(dirpath, name)))
        return files

def included(path):
    if path in SKIP_FILES:
        return False
    if any(path.startswith(p) for p in SKIP_DIR_PREFIXES):
        return False
    name = os.path.basename(path)
    if name in SKIP_BASENAMES:
        return False
    lower = name.lower()
    for ext in BINARY_EXTS:
        if lower.endswith(ext):
            return False
    return True

def is_text(path, sniff_bytes=8192):
    """A file is text if it has no NUL byte and decodes cleanly as UTF-8.
    Cheap heuristic, good enough for source-tree scanning."""
    try:
        with open(path, 'rb') as f:
            chunk = f.read(sniff_bytes)
    except OSError:
        return False
    if b'\x00' in chunk:
        return False
    try:
        chunk.decode('utf-8')
    except UnicodeDecodeError:
        return False
    return True

bad = []
for path in listed_files():
    if not os.path.isfile(path):
        continue
    if not included(path):
        continue
    if not is_text(path):
        continue
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            for lineno, line in enumerate(f, 1):
                if CYR.search(line):
                    bad.append((path, lineno, line.rstrip()))
    except OSError:
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
