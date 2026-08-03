#!/usr/bin/env bash
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
#
# Red-probe the secrets gate: prove it reddens on a planted credential.
#
# A secrets gate that has never been shown to fail is indistinguishable from a
# gate that cannot fail. This runs the exact command `.github/workflows/
# security.yml` runs -- same pinned image, same flags, same base-ref config --
# against two trees, and asserts opposite outcomes:
#
#   clean  = the committed tree at REF, untouched          -> expect exit 0
#   dirty  = that same tree plus planted credentials       -> expect exit 1
#
# Both legs scan a COMMITTED tree, never a working directory. gitleaks is
# invoked without `--no-git`, so it walks commit history: an uncommitted
# planted secret is invisible to it and would produce a green dirty leg that
# says nothing about the gate.
#
# Payloads are generated from /dev/urandom, never copied from documentation.
# Every credential value printed in a vendor's docs is in the scanner's
# allowlist by the time the scanner ships -- otherwise it would redden on the
# vendor's own README -- so a documentation-sourced payload is guaranteed not
# to fire. Three independent detector classes are planted so one allowlisted
# payload cannot make the probe read as vacuous.
#
# Usage:
#   tests/security/redprobe_secrets_gate.sh [--ref REF] [--keep]
#
# Exit 0 when the gate behaved correctly in BOTH directions, 1 otherwise.

set -uo pipefail

REF="origin/next/v1"
KEEP=0
while [ $# -gt 0 ]; do
  case "$1" in
    --ref) REF="$2"; shift 2 ;;
    --keep) KEEP=1; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

# Pinned by digest, matching security.yml. A movable tag would let the probe
# and the gate drift apart silently.
GITLEAKS_IMAGE='zricethezav/gitleaks:v8.30.1@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f'

command -v docker >/dev/null || { echo "docker is required" >&2; exit 2; }
git rev-parse --verify "$REF" >/dev/null 2>&1 || { echo "no such ref: $REF" >&2; exit 2; }

WORK="$(mktemp -d)"
cleanup() { [ "$KEEP" -eq 1 ] && echo "kept: $WORK" || rm -rf "$WORK"; }
trap cleanup EXIT

mkdir -p "$WORK/clean" "$WORK/dirty" "$WORK/config"

# The config comes from the ref under test, mirroring security.yml's
# base-ref-wins rule. Reading it from the working tree would let a local edit
# decide whether the probe passes.
if git cat-file -e "$REF:.gitleaks.toml" 2>/dev/null; then
  git show "$REF:.gitleaks.toml" > "$WORK/config/.gitleaks.toml"
else
  printf '[extend]\nuseDefault = true\n' > "$WORK/config/.gitleaks.toml"
fi

# Clone the REAL history rather than replaying the tree into one synthetic
# commit. gitleaks and trufflehog both scan commit diffs, and the two
# constructions do not agree: on this repository a single-commit replay of
# origin/main reports four findings that a real-history clone of the same
# commit does not report at all. A synthetic history measures the harness,
# not the gate.
SRC="$(git rev-parse --show-toplevel)"
git clone --no-local --quiet --no-checkout "$SRC" "$WORK/clean"
git -C "$WORK/clean" fetch --quiet "$SRC" "+$REF:refs/heads/probe-base"

# Drop every ref except the one under test. A clone carries all of the
# source's branches, and the scanners walk refs rather than the checkout, so
# without this the clean leg answers "clean across whatever branches happened
# to be in the clone" while claiming to answer for REF. It also makes the
# scanned-commit count reproducible between machines, which is what lets the
# count be used as evidence at all.
git -C "$WORK/clean" for-each-ref --format='%(refname)' \
  | grep -v '^refs/heads/probe-base$' \
  | while read -r r; do git -C "$WORK/clean" update-ref -d "$r"; done
git -C "$WORK/clean" checkout --quiet probe-base
git -C "$WORK/clean" reflog expire --expire=now --all
git -C "$WORK/clean" gc --prune=now --quiet

rm -rf "$WORK/dirty"
cp -R "$WORK/clean" "$WORK/dirty"

rand() { LC_ALL=C tr -dc "$1" < /dev/urandom | head -c "$2"; }
draw_payloads() {
  printf 'aws_access_key_id = AKIA%s\naws_secret_access_key = %s\n' \
    "$(rand 'A-Z0-9' 16)" "$(rand 'A-Za-z0-9/+' 40)" > "$1/planted_aws.txt"
  printf 'GITHUB_TOKEN=ghp_%s\n' "$(rand 'A-Za-z0-9' 36)" > "$1/planted_pat.env"
  openssl genrsa 2048 2>/dev/null > "$1/planted_key.pem"
}

# Preflight: every payload must fire on its own before it is planted.
#
# The AWS rule applies an entropy threshold to the candidate secret, and a
# random 40-character draw misses it in roughly one run in fifteen. Without
# this step the probe of a merge-blocking gate is itself flaky, and a flaky
# probe teaches people to re-run it -- which is how a genuinely dead payload
# eventually passes unnoticed. Re-drawing separates "this class is not
# detected at all", which is a finding, from "this draw was unlucky", which
# is noise. Found by component-06 at 14 detections in 15 isolated runs.
PREFLIGHT="$WORK/preflight"
attempt=0
while :; do
  attempt=$((attempt + 1))
  rm -rf "$PREFLIGHT"; mkdir -p "$PREFLIGHT"
  draw_payloads "$PREFLIGHT"
  git -C "$PREFLIGHT" init -q .
  git -C "$PREFLIGHT" add -A
  git -C "$PREFLIGHT" -c user.email=probe@local -c user.name=probe commit -qm payloads
  # --verbose is what prints the per-finding File: lines. Without it gitleaks
  # reports only a count, and a per-file check silently matches nothing.
  docker run --rm --read-only --user "$(id -u):$(id -g)" \
    -v "$PREFLIGHT:/repo:ro" -v "$WORK/config:/config:ro" \
    "$GITLEAKS_IMAGE" detect --source=/repo --no-banner --redact --verbose --exit-code 1 \
    --config=/config/.gitleaks.toml > "$WORK/preflight.out" 2>&1
  rc=$?
  # 0 = nothing found, 1 = findings. Anything else means the scanner did not
  # run, which must not be re-drawn as if it were an unlucky payload.
  if [ "$rc" -ne 0 ] && [ "$rc" -ne 1 ]; then
    echo "FAIL preflight: the scanner exited $rc, so it did not scan."
    sed -n '1,15p' "$WORK/preflight.out"
    exit 1
  fi
  missing=""
  for p in planted_aws.txt planted_pat.env planted_key.pem; do
    grep -q "$p" "$WORK/preflight.out" || missing="$missing $p"
  done
  [ -z "$missing" ] && break
  if [ "$attempt" -ge 5 ]; then
    echo "FAIL preflight: after $attempt draws these classes are still undetected:$missing"
    echo "     Not a bad draw at this point -- the rule is absent, or the class is allowlisted."
    exit 1
  fi
done
[ "$attempt" -gt 1 ] && echo "note preflight: re-drew payloads $((attempt - 1)) time(s) before all three fired"
echo "ok   preflight: all three payload classes fire in isolation"

cp "$PREFLIGHT"/planted_*.txt "$PREFLIGHT"/planted_*.env "$PREFLIGHT"/planted_*.pem "$WORK/dirty/"
git -C "$WORK/dirty" add -A
git -C "$WORK/dirty" -c user.email=probe@local -c user.name=probe commit -qm "tree at $REF plus planted credentials"

run_gate() {
  docker run --rm --read-only --user "$(id -u):$(id -g)" \
    -v "$WORK/$1:/repo:ro" -v "$WORK/config:/config:ro" \
    "$GITLEAKS_IMAGE" detect --source=/repo --no-banner --redact --verbose --exit-code 1 \
    --config=/config/.gitleaks.toml > "$WORK/$1.out" 2>&1
  echo $?
}

clean_rc="$(run_gate clean)"
dirty_rc="$(run_gate dirty)"

bytes_of() { sed -n 's/.*scanned ~\([0-9]*\) bytes.*/\1/p' "$WORK/$1.out" | head -1; }
commits_of() { sed -n 's/.*[^0-9]\([0-9]*\) commits scanned.*/\1/p' "$WORK/$1.out" | head -1; }
clean_bytes="$(bytes_of clean)"; dirty_bytes="$(bytes_of dirty)"

fail=0
note() { echo "$1"; }

# Scope check. The expectation comes from `git rev-list`, a different source
# than the scanner's own counter -- comparing a run against a previous run of
# the same tool catches drift but not systematic error, and both defects this
# harness has had were systematic: a replayed one-commit history, and a clone
# carrying every branch. Two independent sources agreeing is what makes the
# count evidence rather than decoration.
expected_commits="$(git -C "$WORK/clean" rev-list --count HEAD)"
scanned_commits="$(commits_of clean)"
if [ -z "$scanned_commits" ]; then
  note "FAIL scope: the scanner reported no commit count; it did not walk a history"
  fail=1
elif [ "$scanned_commits" != "$expected_commits" ]; then
  note "FAIL scope: scanner walked $scanned_commits commits, git says $REF reaches $expected_commits."
  note "     The scan surface is not the ref under test, so neither leg answers for $REF."
  fail=1
else
  note "ok   scope: $scanned_commits commits, matching git rev-list for $REF"
fi

# Delivery check first. A dirty leg that scanned no more bytes than the clean
# leg never received the payload, and its result -- green or red -- is about
# the harness, not the gate.
undelivered=""
for p in planted_aws.txt planted_pat.env planted_key.pem; do
  git -C "$WORK/dirty" cat-file -e "HEAD:$p" 2>/dev/null || undelivered="$undelivered $p"
done
if [ -n "$undelivered" ]; then
  note "FAIL delivery: these payloads are not in the dirty leg's committed history:$undelivered"
  note "     Both scanners read commits, so an unstaged payload is invisible and the"
  note "     dirty leg's result says nothing about the gate."
  fail=1
else
  note "ok   delivery: all three payloads present in the dirty leg's HEAD (scanned bytes ${clean_bytes:-?} -> ${dirty_bytes:-?}, informational)"
fi

if [ "$clean_rc" -ne 0 ]; then
  note "FAIL clean leg: the committed tree at $REF reports a leak (exit $clean_rc). Either a real secret is committed, or the config is broken."
  sed -n '1,20p' "$WORK/clean.out"
  fail=1
else
  note "ok   clean leg: committed tree at $REF is clean (exit 0)"
fi

if [ "$dirty_rc" -ne 1 ]; then
  note "FAIL dirty leg: three planted credential classes did NOT redden the gate (exit $dirty_rc)."
  note "     This is the fake-green case: the gate runs, reports success, and would pass a real leak."
  sed -n '1,20p' "$WORK/dirty.out"
  fail=1
else
  # Exit 1 alone is not proof of detection. gitleaks also exits non-zero when
  # it cannot load its config at all, and a probe that accepts that as "the
  # gate reddened" would certify a scanner that never scanned. Require a
  # parsed finding count.
  found="$(sed -n 's/.*leaks found: \([0-9]*\).*/\1/p' "$WORK/dirty.out" | head -1)"
  if [ -z "$found" ]; then
    note "FAIL dirty leg: exit 1 but no finding count reported -- the scanner failed rather than detected."
    sed -n '1,20p' "$WORK/dirty.out"
    fail=1
  else
    # Attribute rather than count. A finding total of three proves the gate
    # reddened; it does not prove it reddened on the planted payload, and a
    # pre-existing secret elsewhere would satisfy a count check while leaving
    # the planted classes undetected.
    unattributed=""
    for p in planted_aws.txt planted_pat.env planted_key.pem; do
      grep -q "$p" "$WORK/dirty.out" || unattributed="$unattributed $p"
    done
    if [ -n "$unattributed" ]; then
      note "FAIL dirty leg: the gate reddened, but not on these planted files:$unattributed"
      note "     Something else in the tree produced the findings, so the probe proves nothing."
      fail=1
    else
      note "ok   dirty leg: gate reddened, all three planted files named (exit 1, leaks found: $found)"
    fi
  fi
fi

if [ "$fail" -ne 0 ]; then
  echo
  echo "SECRETS GATE RED-PROBE FAILED"
  exit 1
fi
echo
echo "secrets gate proven two-sided against $REF"
