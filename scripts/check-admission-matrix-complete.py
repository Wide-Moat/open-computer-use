#!/usr/bin/env python3
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
#
# NFR-SEC-38, the contract half: the admission pairing matrix stays complete.
#
# The row asks for admission-time validation of a declared workload-trust
# profile against the configured runtime tier, using a 9-cell pairing matrix.
# contracts/admission/runtime-tokens.schema.json carries that matrix as nine
# `allOf` branches, one per (profile, tier) pair, over a closed profile enum.
#
# Nothing guarded it. Deleting a branch leaves the schema valid JSON Schema, the
# contracts-lint json-schema gate green, and the declaration file still
# conforming -- while the pair that branch covered is no longer required to
# appear. A deployment could then declare a matrix that says nothing about, say,
# (untrusted, runc), and admission would have no rule to apply for the most
# dangerous cell in the table.
#
# The completeness property is what makes a pairing matrix a matrix rather than
# a list of examples, so it is checked as a cartesian product: every profile in
# the closed enum, crossed with every tier the matrix mentions, must have a
# branch. Enumerating the expected pairs in this file instead would restate the
# contract and drift from it; deriving the axes FROM the schema and requiring
# the product keeps one source of truth while still refusing a missing cell.
#
# The subject probe does not see this file -- contracts/ is outside SUBJECT_DIRS
# -- so `workload_trust_profile` reads as absent to the coverage scanner. It is
# not: the profile enum and the matrix both live here. Excusing the row would
# have been wrong, which is why this arms it instead.

import json
import sys
from itertools import product
from pathlib import Path

SCHEMA = Path("contracts/admission/runtime-tokens.schema.json")
PROFILE_DEF = "WorkloadTrustProfile"


def _cells(document: dict) -> list[tuple[str, str]]:
    """(profile, tier) for every branch the matrix requires."""
    matrix = document.get("properties", {}).get("matrix", {})
    out = []
    for branch in matrix.get("allOf", []):
        properties = branch.get("contains", {}).get("properties", {})
        profile = properties.get("profile", {}).get("const")
        tier = properties.get("tier", {}).get("const")
        if profile and tier:
            out.append((profile, tier))
    return out


def _profiles(document: dict) -> list[str]:
    """The closed profile enum, from its definition."""
    definition = document.get("$defs", {}).get(PROFILE_DEF, {})
    values = definition.get("enum")
    return sorted(values) if isinstance(values, list) else []


def missing_cells(profiles: list[str], cells: list[tuple[str, str]]) -> list[str]:
    """Pairs the matrix does not require. Empty means the product is covered."""
    if not profiles or not cells:
        return []
    tiers = sorted({tier for _, tier in cells})
    have = set(cells)
    return [f"({p}, {t})" for p, t in product(sorted(profiles), tiers) if (p, t) not in have]


def problems(document: dict) -> list[str]:
    """Reasons to refuse. Empty means the matrix is a complete product."""
    profiles = _profiles(document)
    cells = _cells(document)
    out = []
    if not profiles:
        out.append(f"$defs.{PROFILE_DEF} no longer declares a closed enum of profiles")
    if not cells:
        out.append(
            "the matrix declares no (profile, tier) branch -- admission has no "
            "pairing rule to validate against"
        )
    if profiles and cells:
        tiers = sorted({tier for _, tier in cells})
        expected = len(profiles) * len(tiers)
        for pair in missing_cells(profiles, cells):
            out.append(
                f"the matrix requires no branch for {pair} -- that pairing would be "
                f"unvalidated at admission"
            )
        if len(cells) != len(set(cells)):
            out.append("the matrix declares a duplicate (profile, tier) branch")
        if not out and len(cells) != expected:
            out.append(f"the matrix has {len(cells)} branches, expected {expected}")
    return out


def self_test() -> int:
    def doc(profiles, cells):
        return {
            "$defs": {PROFILE_DEF: {"enum": profiles}},
            "properties": {
                "matrix": {
                    "allOf": [
                        {"contains": {"properties": {"profile": {"const": p}, "tier": {"const": t}}}}
                        for p, t in cells
                    ]
                }
            },
        }

    full = [(p, t) for p in ("a", "b") for t in ("x", "y")]
    cases = [
        (doc(["a", "b"], full), 0, "a complete product passes"),
        (doc(["a", "b"], full[:-1]), 1, "one deleted cell is refused"),
        (doc(["a", "b", "c"], full), 1, "a profile with no cells is refused"),
        (doc([], full), 1, "a removed profile enum is refused"),
        (doc(["a", "b"], []), 1, "an empty matrix is refused"),
        (doc(["a", "b"], full + [("a", "x")]), 1, "a duplicate branch is refused"),
    ]
    bad = 0
    for document, want, label in cases:
        got = 1 if problems(document) else 0
        ok = got == want
        bad += 0 if ok else 1
        print(f"  {'ok' if ok else 'FAIL'}: {label}")
    if bad:
        print(f"self-test: {bad} case(s) failed")
        return 1
    print(f"self-test ok: {len(cases)} cases")
    return 0


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--self-test":
        return self_test()
    root = Path(argv[0]) if argv else Path(".")
    path = root / SCHEMA
    if not path.is_file():
        sys.stderr.write(f"::error::{SCHEMA} is missing -- the check cannot judge\n")
        return 2
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"::error::{SCHEMA} is not readable JSON ({exc}) -- refusing\n")
        return 2

    issues = problems(document)
    for issue in issues:
        sys.stderr.write(f"::error::NFR-SEC-38: {issue}\n")
    if issues:
        return 1
    profiles = _profiles(document)
    cells = _cells(document)
    tiers = sorted({tier for _, tier in cells})
    print(
        f"NFR-SEC-38: the admission matrix requires all {len(cells)} cells of "
        f"{len(profiles)} profile(s) x {len(tiers)} tier(s)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
