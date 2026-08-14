#!/usr/bin/env python3
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""NFR-SEC-89: every security gate is REQUIRED, not merely present.

A repository can run gitleaks, trufflehog, semgrep, CodeQL, Trivy, syft and
cosign on every pull request and still merge past all of them. Presence is not
enforcement, and the difference is invisible from the workflow files — which is
why this asks the branch-protection and rulesets APIs instead of reading YAML.
That distinction is the whole point: a workflow that runs proves the gate
exists and proves nothing about whether it blocks.

Measured on next/v1 when this was written: the protection endpoint returned 404
for both release branches, and the single ruleset carried
`enforcement: disabled`. Every gate was green and none of them could stop a
merge.

    check-gates-are-required.py --repo owner/name --branch next/v1
    check-gates-are-required.py --self-test

--self-test runs the verdict function against constructed API shapes, including
the ones that must FAIL, so the check cannot quietly stop discriminating.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

# The gates CLAUDE.md calls the first three an auditor opens, plus the
# supply-chain leg. A required-context list that misses one of these is the
# finding; the names are matched as substrings because the display name carries
# decoration ("SAST — semgrep").
EXPECTED_GATES = (
    "gitleaks",
    "trufflehog",
    "semgrep",
    "codeql",
    "trivy",
)


def verdict(protection: dict | None, rulesets: list[dict]) -> list[str]:
    """Return the reasons this branch is unprotected. Empty means enforced.

    Split from the API calls so --self-test can drive it with constructed
    shapes: a check whose logic can only run against the live API is a check
    nobody can prove is non-vacuous.
    """
    problems: list[str] = []

    active_rulesets = [
        r for r in rulesets if str(r.get("enforcement", "")).lower() == "active"
    ]

    if protection is None and not active_rulesets:
        problems.append(
            "no branch protection and no ruleset with enforcement=active: "
            "every gate can be merged past"
        )
        return problems

    if rulesets and not active_rulesets:
        names = ", ".join(str(r.get("name")) for r in rulesets)
        problems.append(
            f"ruleset(s) exist but none is enforcing ({names}): "
            "enforcement=disabled is a ruleset that watches, not one that blocks"
        )

    if protection is not None:
        checks = protection.get("required_status_checks") or {}
        contexts = [str(c).lower() for c in checks.get("contexts", [])]
        if not contexts:
            problems.append(
                "branch protection exists but requires zero status checks: "
                "the gates run and nothing waits for them"
            )
        else:
            missing = [
                g for g in EXPECTED_GATES if not any(g in c for c in contexts)
            ]
            if missing:
                problems.append(
                    f"required contexts do not cover: {', '.join(missing)}"
                )

        admins = protection.get("enforce_admins") or {}
        if not admins.get("enabled", False):
            problems.append(
                "enforce_admins is off: the gates bind everyone except the "
                "people most able to bypass them"
            )

    return problems


def _api(path: str) -> object | None:
    """Query the GitHub API, returning None on a 404 rather than raising."""
    proc = subprocess.run(
        ["gh", "api", path],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode != 0:
        if "Not Found" in proc.stderr or "404" in proc.stderr:
            return None
        print(f"api {path} failed: {proc.stderr.strip()[:200]}", file=sys.stderr)
        sys.exit(2)
    return json.loads(proc.stdout)


def self_test() -> int:
    """Drive the verdict with shapes that must pass and shapes that must fail."""
    good_protection = {
        "required_status_checks": {
            "contexts": [
                "secrets — gitleaks",
                "secrets — trufflehog",
                "SAST — semgrep",
                "CodeQL",
                "SCA — trivy (filesystem)",
            ]
        },
        "enforce_admins": {"enabled": True},
    }

    cases: list[tuple[str, dict | None, list[dict], bool]] = [
        # (label, protection, rulesets, expect_clean)
        ("fully enforced", good_protection, [], True),
        ("nothing at all", None, [], False),
        (
            "ruleset present but disabled",
            None,
            [{"name": "x", "enforcement": "disabled"}],
            False,
        ),
        (
            "protection with zero required contexts",
            {"required_status_checks": {"contexts": []}, "enforce_admins": {"enabled": True}},
            [],
            False,
        ),
        (
            "a gate missing from the required set",
            {
                "required_status_checks": {
                    "contexts": ["secrets — gitleaks", "SAST — semgrep"]
                },
                "enforce_admins": {"enabled": True},
            },
            [],
            False,
        ),
        (
            "admins exempt",
            {**good_protection, "enforce_admins": {"enabled": False}},
            [],
            False,
        ),
    ]

    failures = 0
    for label, prot, rules, expect_clean in cases:
        problems = verdict(prot, rules)
        clean = not problems
        if clean != expect_clean:
            want = "clean" if expect_clean else "problems"
            print(f"SELF-TEST FAIL: {label!r} should report {want}, got {problems!r}")
            failures += 1
        else:
            print(f"  ok: {label} -> {'clean' if clean else problems[0][:60]}")

    if failures:
        print(f"\n{failures} self-test case(s) failed: the check does not discriminate.")
        return 1
    print("\nself-test: the check reds on every unenforced shape and passes the enforced one.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo")
    ap.add_argument("--branch", default="next/v1")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    if not args.repo:
        ap.error("--repo is required unless --self-test is given")

    protection = _api(f"repos/{args.repo}/branches/{args.branch}/protection")
    rulesets = _api(f"repos/{args.repo}/rulesets") or []
    if not isinstance(rulesets, list):
        rulesets = []

    problems = verdict(protection if isinstance(protection, dict) else None, rulesets)
    if problems:
        print(f"NFR-SEC-89 VIOLATION on {args.repo}@{args.branch}:")
        for p in problems:
            print(f"  - {p}")
        print(
            "\nEvery gate can be green and every one of them merged past. "
            "Presence is not enforcement."
        )
        return 1

    print(f"NFR-SEC-89 holds on {args.repo}@{args.branch}: the gates block.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
