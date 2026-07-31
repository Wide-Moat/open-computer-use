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

git archive "$REF" | tar -x -C "$WORK/clean"
git -C "$WORK/clean" init -q .
git -C "$WORK/clean" add -A
git -C "$WORK/clean" -c user.email=probe@local -c user.name=probe commit -qm "tree at $REF"

cp -R "$WORK/clean/." "$WORK/dirty/"
rm -rf "$WORK/dirty/.git"
git -C "$WORK/dirty" init -q .

rand() { LC_ALL=C tr -dc "$1" < /dev/urandom | head -c "$2"; }
printf 'aws_access_key_id = AKIA%s\naws_secret_access_key = %s\n' \
  "$(rand 'A-Z0-9' 16)" "$(rand 'A-Za-z0-9/+' 40)" > "$WORK/dirty/planted_aws.txt"
printf 'GITHUB_TOKEN=ghp_%s\n' "$(rand 'A-Za-z0-9' 36)" > "$WORK/dirty/planted_pat.env"
openssl genrsa 2048 2>/dev/null > "$WORK/dirty/planted_key.pem"

git -C "$WORK/dirty" add -A
git -C "$WORK/dirty" -c user.email=probe@local -c user.name=probe commit -qm "tree at $REF plus planted credentials"

run_gate() {
  docker run --rm --read-only --user "$(id -u):$(id -g)" \
    -v "$WORK/$1:/repo:ro" -v "$WORK/config:/config:ro" \
    "$GITLEAKS_IMAGE" detect --source=/repo --no-banner --redact --exit-code 1 \
    --config=/config/.gitleaks.toml > "$WORK/$1.out" 2>&1
  echo $?
}

clean_rc="$(run_gate clean)"
dirty_rc="$(run_gate dirty)"

bytes_of() { sed -n 's/.*scanned ~\([0-9]*\) bytes.*/\1/p' "$WORK/$1.out" | head -1; }
clean_bytes="$(bytes_of clean)"; dirty_bytes="$(bytes_of dirty)"

fail=0
note() { echo "$1"; }

# Delivery check first. A dirty leg that scanned no more bytes than the clean
# leg never received the payload, and its result -- green or red -- is about
# the harness, not the gate.
if [ -z "$clean_bytes" ] || [ -z "$dirty_bytes" ]; then
  note "FAIL delivery: could not read scanned-byte counts; the gate did not run as expected"
  fail=1
elif [ "$dirty_bytes" -le "$clean_bytes" ]; then
  note "FAIL delivery: dirty leg scanned $dirty_bytes bytes, clean scanned $clean_bytes -- the payload never reached the scanned tree"
  fail=1
else
  note "ok   delivery: payload reached the scanned tree (+$((dirty_bytes - clean_bytes)) bytes)"
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
  elif [ "$found" -lt 3 ]; then
    note "FAIL dirty leg: only $found of 3 planted classes detected -- at least one detector is allowlisted or absent"
    fail=1
  else
    note "ok   dirty leg: gate reddened on all planted classes (exit 1, leaks found: $found)"
  fi
fi

if [ "$fail" -ne 0 ]; then
  echo
  echo "SECRETS GATE RED-PROBE FAILED"
  exit 1
fi
echo
echo "secrets gate proven two-sided against $REF"
