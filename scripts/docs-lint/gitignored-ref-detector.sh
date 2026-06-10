#!/usr/bin/env bash
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
#
# gitignored-ref-detector — fail when a doc references a path that the
# reader cannot open from a clean git clone.
#
# The rule: docs under `docs/architecture/` and `docs/future-architecture/`
# are reference material that someone who cloned the repo must be able to
# follow. If a doc cites a path that is gitignored, the reader sees a dead
# link and the architecture becomes self-referential to a private working
# directory.
#
# The set of local-only directory prefixes to treat as private is supplied
# out-of-band via the LOCAL_REF_DIRS environment variable (colon-separated).
# It defaults to empty, in which case only `git check-ignore` drives the
# finding. No literal local directory name is embedded in this script.
#
# This linter walks every markdown file under the doc roots, extracts file
# paths (anything that looks like `path/to/file.ext`), and fails if any of
# those paths is gitignored.
#
# Allowed exceptions (implemented below):
#   - paths that resolve to URLs (http:// https://)
#   - absolute non-repo paths (starting with `/`)
#   - command-fragment heuristic for /dev/null, /proc/*, /tmp/*, /etc/*,
#     /var/*, /home/*, /usr/* — these are filesystem paths in commands,
#     not repo references
#
# Currently not separately filtered (rely on `git check-ignore` instead):
#   - paths under `docs/` (docs-tree paths are checked like any other —
#     if a doc path is gitignored, that is itself a finding)
#   - paths under `.planning/` (gitignored by repo policy; would correctly
#     fire here, but `.planning/` is not in the doc roots scanned, so
#     references to it from inside `docs/` would correctly fail)
#
# Run from repo root:  scripts/docs-lint/gitignored-ref-detector.sh

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

DOC_ROOTS=(
  docs/architecture
  docs/future-architecture
)

# Local-only directory prefixes (colon-separated), supplied out-of-band.
# Defaults to empty: with no value set, only `git check-ignore` drives the
# finding and this extra prefix match is a no-op.
LOCAL_REF_DIRS="${LOCAL_REF_DIRS:-}"
IFS=':' read -r -a LOCAL_PREFIXES <<< "$LOCAL_REF_DIRS"

fail=0
total_refs=0

for root in "${DOC_ROOTS[@]}"; do
  [ -d "$root" ] || continue

  while IFS= read -r -d '' doc; do
    # Extract candidate filesystem paths:
    #   - inside backticks
    #   - markdown links [text](path)
    #   - bare path/with/slashes.ext occurrences
    # Filter to things that look like a real path (contain `/` and end in
    # a known extension OR look like a directory path).
    candidates=$(grep -ohE '(\[[^]]*\]\(([^)]+)\))|(`[^`]+`)|([A-Za-z0-9_./-]+\.(md|mmd|yaml|yml|json|sh|py|go|rs|ts|tsx|js|jsx|toml|conf|txt|zip|html|svg|png|jpg))' "$doc" \
      | sed -E 's/^\[[^]]*\]\(([^)]+)\)$/\1/' \
      | sed -E 's/^`(.+)`$/\1/' \
      | grep -vE '^https?://' \
      | grep -vE '^#' \
      | grep -E '/' \
      | sort -u || true)

    while IFS= read -r path; do
      [ -z "$path" ] && continue
      # strip line-number suffix like file.md:42 or file.md#anchor
      clean=$(echo "$path" | sed -E 's/[:#].*$//')
      # strip leading ./ or ../
      clean=$(echo "$clean" | sed -E 's|^\./||; s|^(\.\./)+||')
      # skip URLs and absolute non-repo paths
      case "$clean" in
        http*|/*) continue ;;
      esac
      # skip well-known non-path matches (heuristic: command-like fragments)
      case "$clean" in
        */dev/null|*/proc/*|*/tmp/*|*/etc/*|*/var/*|*/home/*|*/usr/*) continue ;;
      esac

      total_refs=$((total_refs + 1))

      # Local-only prefix match (only when LOCAL_REF_DIRS is set).
      for prefix in "${LOCAL_PREFIXES[@]}"; do
        [ -z "$prefix" ] && continue
        case "$clean" in
          "$prefix"|"$prefix"/*)
            echo "FAIL: $doc references local-only path: $clean"
            fail=1
            ;;
        esac
      done

      # `git check-ignore` exits 0 if path is gitignored
      if git check-ignore -q "$clean" 2>/dev/null; then
        echo "FAIL: $doc references gitignored path: $clean"
        fail=1
      fi
    done <<< "$candidates"
  done < <(find "$root" -type f -name '*.md' -print0)
done

if [ "$fail" -eq 1 ]; then
  echo ""
  echo "gitignored-ref-detector: at least one doc references a path the reader"
  echo "cannot open. Either remove the reference, replace it with a public"
  echo "citation (e.g. a regulator URL, a public Anthropic doc URL, an in-repo"
  echo "file under docs/), or move the cited content into the repo."
  exit 1
fi

echo "gitignored-ref-detector: scanned $total_refs refs, all reachable."
