#!/usr/bin/env bash
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
#
# Refuse an SBOM that describes nothing.
#
# syft exiting zero does not mean it resolved anything. Without this a
# degenerate SBOM is attested and verification still passes, because
# verification checks that an attestation exists and is signed by the right
# identity -- not that its predicate describes the image.
#
# This lives in a file rather than inline in the workflow so the rehearsal
# exercises the same implementation the release path runs. A copy in the
# rehearsal would prove the copy.
#
# Usage: sbom_guard.sh <sbom.spdx.json>
# Exit 0 when the SBOM describes at least one package, 1 otherwise.
set -uo pipefail

f="${1:?usage: sbom_guard.sh <sbom.spdx.json>}"

if [ ! -s "$f" ]; then
  echo "::error::${f} is absent or empty; syft produced no SBOM" >&2
  exit 1
fi
if ! jq -e . "$f" >/dev/null 2>&1; then
  echo "::error::${f} is not valid JSON" >&2
  exit 1
fi
pkgs="$(jq '(.packages // []) | length' "$f")"
echo "SPDX packages: ${pkgs}"
if [ "$pkgs" -eq 0 ]; then
  echo "::error::an SBOM listing zero packages describes nothing; refusing to attest it" >&2
  exit 1
fi
