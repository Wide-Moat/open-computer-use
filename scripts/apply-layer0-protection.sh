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

# The ten that must be required. The two that must not are named below,
# because "leave them out" is easy to satisfy by accident and easy to undo
# by accident too.
#
# asyncapi joined once it became hermetic (#384 step 3: "make the job required
# once it is hermetic -- a gate nobody is blocked by is a gate nobody notices
# breaking"). It stopped fetching schema.ocsf.io at validation time -- the OCSF
# classes are vendored and $ref'd locally -- and it carries the audit fan-in
# INV-1 check plus the OCSF class-identity gate that NFR-MAINT-AUDIT-SCHEMA and
# half of NFR-SEC-88 rest on.
#
# nfr-gates joined the list after the other eight. It carries the
# deployment-readiness claim, the NFR-coverage ratchet, the pin policy and the
# cross-repo NFR-SEC-89 verdict -- the checks that measure whether this
# architecture holds. Leaving it optional would let a merge past the gate that
# reports the goal, which is the same shape as leaving gitleaks optional: the
# job would still run and still be green, and nothing would depend on it.
REQUIRED=(
  "nfr-gates"
  "asyncapi"
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

# enforce_admins and a required review are part of the posture, not extras.
# Applied as False/None this script produced a branch that NFR-SEC-89 reports as
# violating the moment it is checked — "the gates bind everyone except the people
# most able to bypass them" is the checker's own wording for exactly this state.
# A tool that configures enforcement must not configure it into a finding.
BODY="$(python3 -c '
import json, sys
print(json.dumps({
    "required_status_checks": {"strict": False, "contexts": sys.argv[1:]},
    "enforce_admins": True,
    "required_pull_request_reviews": {
        "dismiss_stale_reviews": True,
        "require_code_owner_reviews": False,
        "required_approving_review_count": 1,
    },
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

# Classic protection alone leaves the NFR-SEC-89 step unable to answer. That
# step judges the sibling repositories too, and GITHUB_TOKEN cannot read
# another repository's protection endpoint — administration:read is not
# grantable to it — so a cross-repo verdict rests on rulesets alone. With
# protection only, the check reports "cannot establish enforcement from here"
# forever: correct protection, permanently unreadable, indistinguishable from
# no protection at all.
#
# So mirror the same set into an active ruleset. Both objects are enforced by
# GitHub independently, which is the other half of the reason: ocu-sandbox
# carried 31 contexts in protection and 19 in its ruleset, and the four CodeQL
# contexts were missing from the ruleset only. One mechanism configured and the
# other left behind is a gap that reads as enforcement.
RULESET_BODY="$(python3 -c '
import json, sys
print(json.dumps({
    "name": "layer0-" + sys.argv[1],
    "target": "branch",
    "enforcement": "active",
    # No bypass actors, for the same reason enforce_admins is true above: an
    # actor who can bypass is an actor for whom the gates do not exist.
    "bypass_actors": [],
    "conditions": {"ref_name": {"include": ["refs/heads/" + sys.argv[1]], "exclude": []}},
    "rules": [
        {"type": "deletion"},
        {"type": "non_fast_forward"},
        {"type": "pull_request", "parameters": {
            "required_approving_review_count": 1,
            "dismiss_stale_reviews_on_push": True,
            "require_code_owner_review": False,
            "require_last_push_approval": False,
            "required_review_thread_resolution": False,
        }},
        {"type": "required_status_checks", "parameters": {
            "strict_required_status_checks_policy": False,
            "required_status_checks": [{"context": c} for c in sys.argv[2:]],
        }},
    ],
}))' "$BRANCH" "${REQUIRED[@]}")"

EXISTING_RULESET="$(gh api "repos/$REPO/rulesets" \
  --jq ".[]|select(.name==\"layer0-${BRANCH}\")|.id" 2>/dev/null | head -1)"

# RS_RC is captured INSIDE each arm. Reading $? after the if/else would read
# the status of the `if` itself, which is the status of its last command --
# measured: an arm exiting 7 leaves $? as 0 once the fi closes, so a failed
# write would pass for success and the die below would never fire.
RS_RC=0
if [ -n "$EXISTING_RULESET" ]; then
  printf '%s' "$RULESET_BODY" | gh api -X PUT "repos/$REPO/rulesets/$EXISTING_RULESET" --input - >/dev/null 2>/tmp/l0rs.err || RS_RC=$?
else
  printf '%s' "$RULESET_BODY" | gh api -X POST "repos/$REPO/rulesets" --input - >/dev/null 2>/tmp/l0rs.err || RS_RC=$?
fi
if [ "$RS_RC" -ne 0 ]; then
  die "the ruleset write failed: $(tr -d '\n' < /tmp/l0rs.err | cut -c1-200)
       Protection IS written and holds; only the ruleset mirror is missing, so
       the cross-repo NFR-SEC-89 verdict stays unreadable until this succeeds."
fi

# Same discipline as above: read the stored ruleset back rather than trusting
# the write. A ruleset that stores a different set is the failure this whole
# script exists to make impossible to miss.
RS_ID="$(gh api "repos/$REPO/rulesets" \
  --jq ".[]|select(.name==\"layer0-${BRANCH}\")|.id" 2>/dev/null | head -1)"
RS_APPLIED="$(gh api "repos/$REPO/rulesets/$RS_ID" \
  --jq '.rules[]|select(.type=="required_status_checks")|.parameters.required_status_checks[].context' 2>/dev/null | sort)"

if [ "$RS_APPLIED" != "$WANTED" ]; then
  echo "MISMATCH between the ruleset sent and the ruleset stored:" >&2
  diff <(printf '%s\n' "$WANTED") <(printf '%s\n' "$RS_APPLIED") >&2
  die "the ruleset was written but does not hold the intended set"
fi

echo "ok ruleset layer0-$BRANCH requires the same ${#REQUIRED[@]} context(s), read back and identical"
