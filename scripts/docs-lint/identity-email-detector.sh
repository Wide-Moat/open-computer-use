#!/usr/bin/env bash
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
#
# Identity-email detector — the project commits and authors under the
# Wide-Moat org identity, not a personal address.
#
#   banned:    i@yambr.com
#   canonical: developer@widemoat.ai
#
# This gate scans tracked file content (docs, code, configs) for the banned
# address and tells the author to rewrite it. Commit *metadata* (author /
# committer email) is enforced separately by the pre-push hook; this script
# only covers the file-content surface so the same rule holds in CI.
#
# Exits 1 if the banned address appears in any tracked file.

set -uo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

BANNED="i@yambr.com"
CANONICAL="developer@widemoat.ai"

# Search tracked files only; never descend into references/ (vendored repos)
# or .git. -I skips binary files. Fixed-string match so the dot is literal.
# The two policy scripts (this detector and the pre-push hook) name the banned
# address on purpose, to define the rule — exclude them so the gate does not
# flag its own definition.
hits="$(git grep -InF "$BANNED" -- \
  ':(exclude)references/**' \
  ':(exclude)*.sample' \
  ':(exclude)scripts/docs-lint/identity-email-detector.sh' \
  ':(exclude)scripts/githooks/pre-push' \
  2>/dev/null || true)"

if [ -n "$hits" ]; then
  echo "-----------------------------------------------------------------"
  echo "BLOCKED: the personal address '$BANNED' appears in tracked files."
  echo "Rewrite it to the project identity: $CANONICAL"
  echo ""
  echo "$hits" | sed 's/^/  /'
  echo "-----------------------------------------------------------------"
  exit 1
fi

exit 0
