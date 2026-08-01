#!/usr/bin/env bash
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
#
# Require the Layer-0 gates on a branch, and refuse to do it wrongly.
#
# Branch protection matches a check by its name, byte for byte. Two ways to
# get that wrong both end in a branch nobody can merge into:
#
#   - require a name nothing reports, and the context sits pending forever;
#   - require a name that used to report and has since been renamed, which
#     is the same thing arriving later. This repository has already renamed
#     one: `release - signing precedes publish` became `release - pipeline
#     integrity (signing order, cross-job wiring)` between two runs.
#
# So the names are not typed here from memory. Each one is checked against
# what the branch head actually reported before anything is written, and the
# stored set is read back and compared afterwards. A run that cannot verify
# refuses rather than reporting success.
#
# Needs admin on the repository. `push` is not enough: both the protection
# API and the rulesets API answer 404 without it, which reads as a missing
# branch rather than a missing permission.
#
# Usage: scripts/apply-layer0-protection.sh [--dry-run] [owner/repo] [branch]

set -uo pipefail

DRY_RUN=0
if [ "${1:-}" = "--dry-run" ]; then DRY_RUN=1; shift; fi

REPO="${1:-Wide-Moat/open-computer-use}"
BRANCH="${2:-next/v1}"

# The eight that must be required. The two that must not are named below,
# because "leave them out" is easy to satisfy by accident and easy to undo
# by accident too.
REQUIRED=(
  "secrets — gitleaks"
  "secrets — trufflehog"
  "SAST — semgrep"
  "SCA — trivy (filesystem)"
  "IaC — checkov"
  "release — gate 3 rehearsal (nothing published)"
  "commits — conventional-commits"
  "release — pipeline integrity (signing order, cross-job wiring)"
)

# Requiring either of these blocks the branch permanently.
#
#   Trivy       a second check run from the SARIF upload, green whether or
#               not the scan found anything -- it reports upload success.
#   CodeRabbit  arrives on the commit-status surface, not as a check run,
#               and does not report on every push.
#
# Both are green today, which is exactly why requiring them looks harmless.
FORBIDDEN=("Trivy" "CodeRabbit")

die() { echo "REFUSED: $*" >&2; exit 2; }

# A call that never completed and a call that was refused read the same way
# at the call site: empty output, non-zero status. They are not the same
# fact, and this script exists to not confuse two causes of one reading.
# Retry the transport, then report which of the two happened.
api() {
  local out rc i
  for i in 1 2 3 4 5; do
    out="$(gh api "$@" 2>/tmp/l0.api.err)"; rc=$?
    if [ "$rc" -eq 0 ]; then printf '%s' "$out"; return 0; fi
    grep -qiE "TLS handshake|timeout|connection reset|no such host|EOF" /tmp/l0.api.err || break
    sleep $((i * 2))
  done
  printf '%s' "$out"
  return "$rc"
}

transport_failed() {
  grep -qiE "TLS handshake|timeout|connection reset|no such host|EOF" /tmp/l0.api.err
}


command -v gh >/dev/null 2>&1 || die "gh is not on PATH"
command -v python3 >/dev/null 2>&1 || die "python3 is not on PATH"

echo "repo=$REPO branch=$BRANCH dry_run=$DRY_RUN"

# Before any network call. This is a claim about the two lists above,
# not about the branch -- gating it on a reachable API would leave it
# unreached whenever an earlier check refuses first, which is how a
# guard comes to pass for the wrong reason.
for name in "${FORBIDDEN[@]}"; do
  for want in "${REQUIRED[@]}"; do
    [ "$name" = "$want" ] && die "$name must never be required: see the note above.
     It is green today, which is what makes requiring it look harmless."
  done
done


HEAD_SHA="$(api "repos/$REPO/branches/$BRANCH" --jq .commit.sha)"
if [ -z "$HEAD_SHA" ]; then
  if transport_failed; then
    die "the call to read $BRANCH never completed after five tries
     ($(tr -d "\n" < /tmp/l0.api.err | cut -c1-120)).
     This says nothing about the branch. Nothing was checked, nothing written."
  fi
  die "$REPO has no branch $BRANCH, or it is not readable with this token.
     Nothing was checked and nothing was written."
fi
echo "head=${HEAD_SHA:0:8}"

# What the head actually reported, across both surfaces protection matches.
REPORTED="$(
  {
    api "repos/$REPO/commits/$HEAD_SHA/check-runs?per_page=100" \
      --jq '.check_runs[].name'
    api "repos/$REPO/commits/$HEAD_SHA/status" \
      --jq '.statuses[].context'
  } | sort -u
)"
if [ -z "$REPORTED" ]; then
  transport_failed && die "the call to list the head's checks never completed;
     nothing was checked and nothing was written."
  die "${HEAD_SHA:0:8} reported no check at all. On a merge commit this is
     usual -- the gates run on pull-request heads. Point this at a commit
     that ran them, or at the branch after a push-triggered run:
       scripts/apply-layer0-protection.sh --dry-run $REPO <branch>"
fi

echo "reported contexts: $(printf '%s\n' "$REPORTED" | wc -l | tr -d ' ')"

missing=0
for name in "${REQUIRED[@]}"; do
  if printf '%s\n' "$REPORTED" | grep -qxF "$name"; then
    echo "  present  $name"
  else
    echo "  ABSENT   $name" >&2
    missing=$((missing + 1))
  fi
done

if [ "$missing" -gt 0 ]; then
  die "$missing name(s) above do not match anything the head reported.
     A required context nothing reports never turns green. Compare against
     the live list before editing this script:
       gh api repos/$REPO/commits/$HEAD_SHA/check-runs --jq '.check_runs[].name'"
fi

BODY="$(python3 -c '
import json, sys
print(json.dumps({
    "required_status_checks": {"strict": False, "contexts": sys.argv[1:]},
    "enforce_admins": False,
    "required_pull_request_reviews": None,
    "restrictions": None,
}))' "${REQUIRED[@]}")"

if [ "$DRY_RUN" -eq 1 ]; then
  echo "dry run: every name matches a reported context; nothing written"
  exit 0
fi

printf '%s' "$BODY" | gh api -X PUT "repos/$REPO/branches/$BRANCH/protection" --input - >/dev/null 2>/tmp/l0.err
PUT_RC=$?
if [ "$PUT_RC" -ne 0 ]; then
  if grep -qi "not found" /tmp/l0.err; then
    die "the write was refused (404). Without admin, both the protection API
     and the rulesets API answer 404, which reads as a missing branch rather
     than a missing permission. Nothing was changed."
  fi
  die "the write failed: $(tr -d '\n' < /tmp/l0.err | cut -c1-200)"
fi

# Written is not applied. Read the stored set back and compare it, so a
# silently-dropped or silently-mangled name cannot pass for success.
APPLIED="$(gh api "repos/$REPO/branches/$BRANCH/protection/required_status_checks" \
  --jq '.contexts[]' 2>/dev/null | sort)"
WANTED="$(printf '%s\n' "${REQUIRED[@]}" | sort)"

if [ "$APPLIED" != "$WANTED" ]; then
  echo "MISMATCH between what was sent and what is stored:" >&2
  diff <(printf '%s\n' "$WANTED") <(printf '%s\n' "$APPLIED") >&2
  die "protection was written but does not hold the intended set"
fi

echo "ok protection on $BRANCH requires ${#REQUIRED[@]} context(s), read back and identical"
