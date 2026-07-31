#!/usr/bin/env bash
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
#
# Assert that the release pipeline's certificate-identity pattern rejects the
# identities it claims to reject.
#
# supply-chain.yml builds a `--certificate-identity-regexp` for `cosign
# verify` and its comments state two properties: the pattern is anchored, so
# a typosquat repository or a signature from another workflow in the same
# repository cannot satisfy it; and regex metacharacters in the tag are
# escaped, so `v0.9.5.1` cannot be matched by a same-shape tag such as
# `v0a9b5c1`. Both are load-bearing -- a signature that verifies against the
# wrong identity is worth nothing -- and neither had a test.
#
# The pattern construction below is copied byte-for-byte from the workflow.
# It is duplicated rather than sourced because the workflow embeds it in a
# `run:` block; the drift-guard is that this file names the source and any
# edit there must be mirrored here.
#
# Boundary, stated rather than assumed: cosign matches with Go's RE2 and this
# harness matches with `grep -E` (POSIX ERE). The two agree on anchoring,
# alternation, and literal-vs-metacharacter dots, which is the whole of what
# is asserted here. A property depending on RE2-specific semantics would need
# cosign itself.
#
# Usage: check_cosign_identity_anchor.sh
# Exit 0 when every identity is classified as intended, 1 otherwise.

set -uo pipefail

WORKFLOW_SOURCE=".github/workflows/supply-chain.yml"

# --- copied verbatim from ${WORKFLOW_SOURCE} ---------------------------------
build_cert_id() {
  REF_NAME="$1"; REPO_FOR_VERIFY="$2"; EVENT_NAME="$3"
  ref_re="$(printf '%s' "$REF_NAME" | sed -E 's/[][\\.*^$()+?{|]/\\&/g')"
  repo_re="$(printf '%s' "$REPO_FOR_VERIFY" | sed -E 's/[][\\.*^$()+?{|]/\\&/g')"
  if [ "$EVENT_NAME" = "push" ]; then
    cert_id="^https://github\\.com/${repo_re}/\\.github/workflows/supply-chain\\.yml@refs/tags/${ref_re}$"
  else
    cert_id="^https://github\\.com/${repo_re}/\\.github/workflows/supply-chain\\.yml@(refs/tags/v[0-9.]+|refs/heads/(main|next/v1))$"
  fi
  printf '%s' "$cert_id"
}
# --- end copied block --------------------------------------------------------

REPO="Wide-Moat/open-computer-use"
TAG="v0.9.5.1"
WF="https://github.com/${REPO}/.github/workflows/supply-chain.yml"

fail=0
check() { # verdict-expected, identity, label, cert_id
  local want="$1" identity="$2" label="$3" pattern="$4" got
  if printf '%s' "$identity" | grep -Eq "$pattern"; then got=match; else got=reject; fi
  if [ "$got" = "$want" ]; then
    printf 'ok   %-6s %s\n' "$got" "$label"
  else
    printf 'FAIL wanted %s, got %s: %s\n     identity: %s\n' "$want" "$got" "$label" "$identity"
    fail=1
  fi
}

echo "=== push event, tag ${TAG} ==="
PUSH_ID="$(build_cert_id "$TAG" "$REPO" push)"
check match  "${WF}@refs/tags/${TAG}"                    "the genuine release identity"        "$PUSH_ID"
check reject "https://github.com/${REPO}-EVIL/.github/workflows/supply-chain.yml@refs/tags/${TAG}" \
                                                          "typosquat repository suffix"         "$PUSH_ID"
check reject "https://github.com/${REPO}/.github/workflows/build.yml@refs/tags/${TAG}" \
                                                          "another workflow in the same repo"   "$PUSH_ID"
check reject "${WF}@refs/tags/v0a9b5c1"                  "same-shape tag (dot as wildcard)"    "$PUSH_ID"
check reject "${WF}@refs/heads/main"                     "branch ref on a tag-push identity"   "$PUSH_ID"
check reject "${WF}@refs/tags/${TAG}-EVIL"               "suffix appended past the anchor"     "$PUSH_ID"
check reject "https://evil.example/${WF}@refs/tags/${TAG}" "prefix prepended past the anchor"  "$PUSH_ID"

echo
echo "=== workflow_dispatch event ==="
WD_ID="$(build_cert_id "$TAG" "$REPO" workflow_dispatch)"
check match  "${WF}@refs/heads/main"                     "release branch main"                 "$WD_ID"
check match  "${WF}@refs/heads/next/v1"                  "release branch next/v1"              "$WD_ID"
check match  "${WF}@refs/tags/v1.2.3"                    "any release-shaped tag"              "$WD_ID"
check reject "${WF}@refs/heads/throwaway"                "arbitrary throwaway branch"          "$WD_ID"
check reject "${WF}@refs/heads/main-EVIL"                "branch name with a suffix"           "$WD_ID"

echo
if [ "$fail" -ne 0 ]; then
  echo "CERTIFICATE-IDENTITY ANCHOR CHECK FAILED"
  echo "The pattern in ${WORKFLOW_SOURCE} does not reject what its comments claim it rejects."
  exit 1
fi
echo "certificate-identity pattern rejects every impostor identity and accepts only the genuine one"
