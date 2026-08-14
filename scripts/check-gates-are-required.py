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
import time
import sys

# The gates CLAUDE.md calls the first three an auditor opens, plus the
# supply-chain leg. A required-context list that misses one of these is the
# finding; the names are matched as substrings because the display name carries
# decoration ("SAST — semgrep").
# Each gate lists the substrings that count as covering it, because a context's
# display name is chosen by whatever publishes it. CodeQL is the case that
# forced this: GitHub's default setup publishes one context per language
# ("Analyze (go)"), and the string "codeql" appears in none of them — so a
# repository with all four required was reported as missing CodeQL entirely.
# A check that reds a correctly configured branch gets ignored, which costs more
# than the miss it was guarding against.
EXPECTED_GATES = {
    "gitleaks": ("gitleaks",),
    "trufflehog": ("trufflehog",),
    "semgrep": ("semgrep",),
    "codeql": ("codeql", "analyze ("),
    "trivy": ("trivy",),
}


def verdict(protection: dict | None, rulesets: list[dict]) -> list[str]:
    """Return the reasons this branch is unprotected. Empty means enforced.

    Split from the API calls so --self-test can drive it with constructed
    shapes: a check whose logic can only run against the live API is a check
    nobody can prove is non-vacuous.
    """
    problems: list[str] = []

    # An active ruleset only counts if it BINDS this branch and CARRIES gates.
    # Checking the word "active" alone failed open one level deeper than the
    # disabled-ruleset trap this script was written for: a tag-targeted ruleset,
    # one scoped to another branch, or one every actor can bypass all read as
    # enforcement while requiring nothing.
    active_rulesets = [
        r
        for r in rulesets
        if str(r.get("enforcement", "")).lower() == "active"
        and str(r.get("target", "branch")).lower() == "branch"
        and not r.get("bypass_actors")
    ]

    if protection is None and not active_rulesets:
        problems.append(
            "no branch protection and no ruleset with enforcement=active: "
            "every gate can be merged past"
        )
        return problems

    if protection is None and active_rulesets:
        # No READABLE branch protection: the rules are the whole claim, so they
        # must carry the required checks themselves. A ruleset that enforces
        # something else (linear history, signed commits) leaves every gate
        # merge-past-able while reading as active.
        #
        # Measured caveat, stated because it bounds what this leg can prove: the
        # branch-scoped rules endpoint LAGS the protection settings. On a branch
        # with 31 required contexts it reported 19 — a strict subset, missing the
        # most recently added ones. So a gate it does not list may still be
        # required, and this leg can produce a false finding on a freshly
        # configured branch. It never produces a false PASS, which is the
        # direction that matters: the set it reports is real, just incomplete.
        covered: list[str] = []
        for r in active_rulesets:
            for rule in r.get("rules") or []:
                if str(rule.get("type", "")).lower() != "required_status_checks":
                    continue
                params = rule.get("parameters") or {}
                for c in params.get("required_status_checks") or []:
                    covered.append(str(c.get("context", "")).lower())
        if not covered:
            problems.append(
                "the active ruleset requires no status checks: "
                "enforcement without gates binds nothing"
            )
        else:
            missing = [
                name
                for name, aliases in EXPECTED_GATES.items()
                if not any(a in c for a in aliases for c in covered)
            ]
            if missing:
                problems.append(
                    "the active ruleset's required checks do not cover: "
                    + ", ".join(missing)
                )

    if rulesets and not active_rulesets:
        names = ", ".join(str(r.get("name")) for r in rulesets)
        problems.append(
            f"ruleset(s) exist but none is enforcing ({names}): "
            "enforcement=disabled is a ruleset that watches, not one that blocks"
        )

    if protection is not None:
        checks = protection.get("required_status_checks") or {}
        # The API returns the same set twice: `contexts` (legacy, plain strings)
        # and `checks` (objects carrying the app id). Reading only one is
        # fragile — GitHub has deprecated `contexts` — so take the union and let
        # either shape answer.
        contexts = [str(c).lower() for c in checks.get("contexts") or []]
        contexts += [
            str(c.get("context", "")).lower() for c in checks.get("checks") or []
        ]
        contexts = [c for c in contexts if c]
        if not contexts:
            problems.append(
                "branch protection exists but requires zero status checks: "
                "the gates run and nothing waits for them"
            )
        else:
            lowered = [c.lower() for c in contexts]
            missing = [
                name
                for name, aliases in EXPECTED_GATES.items()
                if not any(a in c for a in aliases for c in lowered)
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


def _api(path: str, optional: bool = False) -> object | None:
    """Query the GitHub API, returning None on a 404 rather than raising."""
    # Retry the transport, never the verdict. A TLS handshake timeout is not a
    # finding, and letting one decide the gate would make an enforcement check
    # flake — measured: back-to-back runs against the same branch alternated
    # between the real answer and a network error.
    for attempt in range(3):
        proc = subprocess.run(
            ["gh", "api", path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode == 0:
            break
        transient = any(
            m in proc.stderr.lower()
            for m in ("timeout", "connection reset", "temporary failure", "eof")
        )
        if not transient or attempt == 2:
            break
        time.sleep(2 * (attempt + 1))
    if proc.returncode != 0:
        if "Not Found" in proc.stderr or "404" in proc.stderr:
            return None
        if optional and ("403" in proc.stderr or "not accessible" in proc.stderr.lower()):
            # Unreadable is not absent. Say so and let the caller decide; the
            # alternative is a 403 masquerading as "no protection", which turns
            # an access limit into a false finding.
            print(
                f"note: {path} is not readable with this token; "
                "relying on the branch-scoped rules instead",
                file=sys.stderr,
            )
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
        # The same protection expressed only through the modern `checks` array.
        # GitHub has deprecated the flat `contexts` list, so a repo will
        # eventually report this shape alone; reading one field would call a
        # fully protected branch "zero status checks". Measured before the fix.
        (
            "protection using checks[] rather than contexts[]",
            {
                "required_status_checks": {
                    "checks": [
                        {"context": "secrets — gitleaks"},
                        {"context": "secrets — trufflehog"},
                        {"context": "SAST — semgrep"},
                        {"context": "Analyze (go)"},
                        {"context": "SCA — trivy (filesystem)"},
                    ]
                },
                "enforce_admins": {"enabled": True},
            },
            [],
            True,
        ),
        ("nothing at all", None, [], False),
        # The shapes that made the ruleset leg fail open one level deeper than
        # the disabled-ruleset trap. Each reads as enforcement and binds nothing.
        (
            "active ruleset that requires no checks",
            None,
            [{"name": "empty", "enforcement": "active", "target": "branch", "rules": []}],
            False,
        ),
        (
            "active ruleset that enforces something other than checks",
            None,
            [
                {
                    "name": "linear-only",
                    "enforcement": "active",
                    "target": "branch",
                    "rules": [{"type": "non_fast_forward"}],
                }
            ],
            False,
        ),
        (
            "active ruleset whose checks miss a gate",
            None,
            [
                {
                    "name": "partial",
                    "enforcement": "active",
                    "target": "branch",
                    "rules": [
                        {
                            "type": "required_status_checks",
                            "parameters": {
                                "required_status_checks": [
                                    {"context": "gitleaks"},
                                    {"context": "trivy"},
                                ]
                            },
                        }
                    ],
                }
            ],
            False,
        ),
        (
            "active ruleset every actor can bypass",
            None,
            [
                {
                    "name": "bypassable",
                    "enforcement": "active",
                    "target": "branch",
                    "bypass_actors": [{"actor_id": 1}],
                    # Carries the FULL gate set on purpose: only the bypass
                    # filter can reject this, so removing that filter reds
                    # here rather than being masked by the coverage check.
                    "rules": [{"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": "gitleaks"}, {"context": "trufflehog"}, {"context": "sast-semgrep"}, {"context": "Analyze (go)"}, {"context": "trivy"}]}}],
                }
            ],
            False,
        ),
        (
            "active ruleset targeting tags, not branches",
            None,
            # Full gate set again, so only the branch-target filter decides.
            [
                {
                    "name": "tags",
                    "enforcement": "active",
                    "target": "tag",
                    "rules": [{"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": "gitleaks"}, {"context": "trufflehog"}, {"context": "sast-semgrep"}, {"context": "Analyze (go)"}, {"context": "trivy"}]}}],
                }
            ],
            False,
        ),
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

    # The protection endpoint needs `administration: read`, which the Actions
    # token cannot be granted — from CI it answers 403, not 404. Treating that
    # as "unprotected" would report a violation for a branch that is protected,
    # so the classic protection leg is consulted only when it is readable; in
    # CI the branch-scoped rules below carry the verdict alone.
    protection = _api(
        f"repos/{args.repo}/branches/{args.branch}/protection", optional=True
    )
    # Branch-SCOPED effective rules, not the repository's ruleset list. The list
    # says a ruleset exists; it does not say it binds THIS branch, so a ruleset
    # targeting main read as protection for next/v1. This endpoint answers the
    # question actually being asked and needs no admin scope, which the
    # protection endpoint does.
    branch_path = args.branch.replace("/", "%2F")
    effective = _api(f"repos/{args.repo}/rules/branches/{branch_path}") or []
    if not isinstance(effective, list):
        effective = []
    # Present the effective rules in the shape verdict() already reasons about:
    # one synthetic active branch ruleset carrying them, since the endpoint has
    # resolved targeting and returns only what applies here.
    rulesets = (
        [{"enforcement": "active", "target": "branch", "rules": effective}]
        if effective
        else []
    )

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
