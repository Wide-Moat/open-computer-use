#!/usr/bin/env bash
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
#
# Build the image reference the signing job will sign, refusing an absent
# digest.
#
# A build job that pushed nothing leaves its output empty, and an empty digest
# composes the reference `ghcr.io/x@` -- which cosign rejects with a parse
# error rather than a statement about signing. Failing here keeps the reason
# legible.
#
# Lowercasing is not cosmetic: registries reject uppercase in a repository
# name, and `github.repository` carries the organisation's capitalisation that
# metadata-action used to fold away while the name came from `tags:`.
#
# Reads DIGEST, SUFFIX, REPO from the environment. Writes `ref=` to
# GITHUB_OUTPUT when set, and prints it either way.
# Exit 0 when a reference was built, 1 when the digest is absent.
set -uo pipefail

: "${DIGEST?}" ; : "${SUFFIX?}" ; : "${REPO?}"

if [ -z "$DIGEST" ]; then
  echo "::error::no digest from the build job; there is nothing to sign" >&2
  exit 1
fi

repo_lower="$(printf '%s' "$REPO" | tr '[:upper:]' '[:lower:]')"
ref="ghcr.io/${repo_lower}${SUFFIX}@${DIGEST}"
echo "$ref"
[ -n "${GITHUB_OUTPUT:-}" ] && printf 'ref=%s\n' "$ref" >> "$GITHUB_OUTPUT"
exit 0
