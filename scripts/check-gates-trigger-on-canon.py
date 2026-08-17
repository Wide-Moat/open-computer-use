#!/usr/bin/env python3
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
#
# A required gate must FIRE on the canon branch, not merely exist.
#
# check-gates-are-required.py asks whether a context is required. That question
# assumes the context arrives. A workflow filtered to `branches: [main]`
# publishes no context on a next/v1 pull request at all, so requiring it would
# block every PR forever on a check that never runs -- and NOT requiring it
# leaves the branch unanalysed while the workflow file sits in the tree looking
# like coverage.
#
# Measured before this was written: codeql.yml carried `pull_request:
# branches: [main]`, and the platform agreed -- code-scanning/analyses for
# refs/heads/next/v1 held 10 Trivy uploads and zero from CodeQL. The workflow
# existed, was correct, was pinned, and analysed nothing on canon.
#
# The check reads triggers only. Whether a gate is REQUIRED is the other
# script's question; whether it can possibly report is this one's.

import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.stderr.write("check-gates-trigger-on-canon: PyYAML is required\n")
    sys.exit(2)

CANON = "next/v1"
WORKFLOWS = Path(".github/workflows")

# Workflows that must be able to report on a canon pull request. Named, not
# inferred: a release workflow legitimately has no pull_request trigger, and a
# check that flagged those would be ignored within a week.
MUST_COVER_CANON = {
    "codeql.yml",
    "security.yml",
    "contracts-lint.yml",
    "docs-lint.yml",
    "gate3-rehearsal.yml",
}


def triggers(doc):
    """The `on:` mapping. PyYAML parses a bare `on:` key as the boolean True."""
    if not isinstance(doc, dict):
        return {}
    on = doc.get(True)
    if on is None:
        on = doc.get("on")
    return on if isinstance(on, dict) else {}


def covers_canon(on):
    """Does this workflow publish a context on a canon pull request?

    `pull_request:` with no value means EVERY branch -- the trap that made a
    first sweep of this repository report five false gaps, security.yml among
    them, when its gates plainly do report on canon PRs.
    """
    if "pull_request" not in on:
        return False, "no pull_request trigger"
    pr = on["pull_request"]
    if pr is None:
        return True, "every branch"
    if not isinstance(pr, dict):
        return False, f"unreadable pull_request node ({type(pr).__name__})"
    branches = pr.get("branches")
    if branches is None:
        return True, "every branch"
    if CANON in branches:
        return True, f"branches={branches}"
    if any("*" in str(b) for b in branches):
        return True, f"branches={branches} (glob)"
    return False, f"branches={branches}"


def findings(root=Path(".")):
    """Return (workflow, reason) for every named gate blind to the canon branch."""
    out = []
    for name in sorted(MUST_COVER_CANON):
        path = root / WORKFLOWS / name
        if not path.is_file():
            out.append((name, "workflow file is missing"))
            continue
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            out.append((name, f"does not parse ({type(exc).__name__})"))
            continue
        ok, why = covers_canon(triggers(doc))
        if not ok:
            out.append((name, why))
    return out


def self_test():
    cases = [
        ({"pull_request": None}, True, "a bare pull_request key covers every branch"),
        ({"pull_request": {"branches": ["main", CANON]}}, True, "canon listed explicitly"),
        ({"pull_request": {"branches": ["main"]}}, False, "filtered to main only"),
        ({"pull_request": {"branches": ["releases/**"]}}, True, "a glob is treated as covering"),
        ({"push": {"branches": [CANON]}}, False, "push-only does not report on a PR"),
        ({}, False, "no triggers at all"),
    ]
    bad = 0
    for on, want, label in cases:
        got, why = covers_canon(on)
        if got != want:
            bad += 1
            sys.stderr.write(f"self-test FAIL: {label} -> {got} ({why}), want {want}\n")
        else:
            print(f"self-test ok: {label} -> {'covers' if got else 'blind'}")

    # The named set must be non-empty, or findings() is vacuous by construction.
    if not MUST_COVER_CANON:
        bad += 1
        sys.stderr.write("self-test FAIL: MUST_COVER_CANON is empty\n")
    else:
        print(f"self-test ok: {len(MUST_COVER_CANON)} workflows are named as gates")

    # findings() itself, on a constructed tree -- not just covers_canon(). The
    # meta-gate stubs THIS function to `return []`, and a self-test that never
    # calls it stays green under that stub, certifying a checker that asserts
    # nothing. Measured: before this block, the stub left --self-test at exit 0.
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / WORKFLOWS).mkdir(parents=True)
        for name in MUST_COVER_CANON:
            (root / WORKFLOWS / name).write_text(
                f"name: {name}\non:\n  pull_request:\n    branches: [main, {CANON}]\n",
                encoding="utf-8",
            )
        if findings(root):
            bad += 1
            sys.stderr.write("self-test FAIL: a fully covering tree reported a finding\n")
        else:
            print("self-test ok: findings() accepts a tree where every gate covers canon")

        blind = root / WORKFLOWS / sorted(MUST_COVER_CANON)[0]
        blind.write_text("name: x\non:\n  pull_request:\n    branches: [main]\n", encoding="utf-8")
        if not findings(root):
            bad += 1
            sys.stderr.write("self-test FAIL: a main-only gate was not reported\n")
        else:
            print("self-test ok: findings() reports a gate filtered to main")

    if bad:
        return 1
    print(f"self-test ok: {len(cases)} cases")
    return 0


def main(argv):
    if argv and argv[0] == "--self-test":
        return self_test()
    root = Path(argv[0]) if argv else Path(".")
    blind = findings(root)
    for name, why in blind:
        sys.stderr.write(
            f"::error::{name} does not report on a {CANON} pull request ({why}) — "
            f"a gate that cannot fire is not coverage\n"
        )
    if blind:
        return 1
    print(f"every one of {len(MUST_COVER_CANON)} named gates reports on a {CANON} pull request")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
