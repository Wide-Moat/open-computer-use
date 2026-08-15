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
import glob
import os
import json
import pathlib
import subprocess
import yaml
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


def verdict(
    protection: dict | None,
    rulesets: list[dict],
    protection_readable: bool = True,
) -> list[str]:
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
        if protection_readable:
            problems.append(
                "no branch protection and no ruleset with enforcement=active: "
                "every gate can be merged past"
            )
        else:
            # Unreadable is not absent, and saying "no branch protection" when
            # the endpoint answered 403 is a factually wrong finding. The
            # branch-scoped rules endpoint reports ruleset-derived rules ONLY,
            # so a classically protected branch is invisible to it — from CI
            # that reads as nothing at all. Say what is known instead.
            problems.append(
                "cannot establish enforcement from here: the protection endpoint "
                "is unreadable with this token and no branch-scoped ruleset rules "
                "apply. Enforce via a ruleset, which CI can observe, or run this "
                "with a token carrying administration:read"
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


def synthesise_ruleset(
    effective: list[dict], bypass_actors: list[dict]
) -> list[dict]:
    """Wrap branch-scoped effective rules in the shape verdict() reasons about.

    Separate from main() so the self-test can drive it. It has to be: the bypass
    filter in verdict() was real and mutation-proven, and still dead on the live
    path, because this wrapper was built without the field it filters on. A
    filter is only as good as the record handed to it.
    """
    if not effective:
        return []
    return [
        {
            "enforcement": "active",
            "target": "branch",
            "rules": effective,
            "bypass_actors": bypass_actors,
        }
    ]


def required_contexts(
    protection: dict | None, rulesets: list[dict]
) -> set[str]:
    """Every context this branch requires, from BOTH sources, lowercased.

    Either can be the one enforcing. A branch protected by a ruleset rather than
    classic protection has an empty protection payload, and reading protection
    alone reports no unenforceable job on exactly the configuration the flip
    instructions recommend — rulesets, because CI can observe them and cannot
    read the protection endpoint.
    """
    names: set[str] = set()
    if isinstance(protection, dict):
        rsc = protection.get("required_status_checks") or {}
        names |= {str(c).lower() for c in rsc.get("contexts") or []}
        names |= {str(c.get("context", "")).lower() for c in rsc.get("checks") or []}
    for rs in rulesets or []:
        for rule in rs.get("rules") or []:
            if str(rule.get("type", "")).lower() != "required_status_checks":
                continue
            params = rule.get("parameters") or {}
            names |= {
                str(c.get("context", "")).lower()
                for c in params.get("required_status_checks") or []
            }
    return {n for n in names if n}


def unenforceable_required_jobs(
    jobs: list[tuple[str, set[str]]], required: set[str]
) -> list[str]:
    """Name jobs that are required AND cannot fail.

    Separate from main() so the self-test can drive it. It has to be: the
    bypass_actors incident in this same file was a filter that was real in the
    tested function and dead on the live path, and a filter living only inside
    main() repeats it — three mutations to this logic survived a green self-test
    before it was extracted.

    A job matches on EITHER identity it can publish, since GitHub uses the job's
    `name:` when set and its key otherwise.
    """
    out: list[str] = []
    for label, identities in jobs:
        if identities & required:
            out.append(label)
    return out


def _local_repo_slug() -> str:
    """Return owner/name of the checkout this script is running in, lowercased.

    Empty when it cannot be determined, which disables the workflow-file check
    rather than letting it read the wrong repository's files.
    """
    proc = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if proc.returncode != 0:
        return ""
    url = proc.stdout.strip()
    for prefix in ("git@github.com:", "https://github.com/"):
        if url.startswith(prefix):
            return url[len(prefix):].removesuffix(".git").lower()
    return ""


def non_blocking_jobs(
    workflow_dir: str = ".github/workflows",
) -> list[tuple[str, set[str]]]:
    """Name jobs that carry continue-on-error, so they cannot fail a merge.

    A required context whose job is continue-on-error is green whatever the tool
    finds — the NFR's own sentence ("a merge cannot reach a protected branch
    while a gate is failing") is unsatisfiable for it, because it is never
    failing. Branch protection cannot see this: the API reports the context as
    required and the run reports success.

    Read from the workflow files rather than the API for the same reason the
    verdict reads rules rather than settings — this is a property of what runs,
    not of what is configured.

    Scope, stated because every gap here fails OPEN: it reads JOB-level literal
    `continue-on-error: true` only, and matches a context by exact identity, so a
    MATRIX job is missed — codeql's job is keyed `analyze` and publishes
    `Analyze (go)`, which neither identity equals. A step-level flag on the sole gating step, an
    expression-valued flag, the string "true", and a reusable workflow called via
    `uses:` all go unreported. Widening to those means evaluating expressions and
    following workflow references, which is a different tool; what this catches
    is the shape both of this repository's disabled gates take.
    """
    found: list[tuple[str, set[str]]] = []
    paths = sorted(
        glob.glob(os.path.join(workflow_dir, "*.yml"))
        + glob.glob(os.path.join(workflow_dir, "*.yaml"))
    )
    for path in paths:
        try:
            doc = yaml.safe_load(open(path, encoding="utf-8"))
        except Exception:
            continue
        for name, job in (doc.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            if job.get("continue-on-error") is True:
                # Carry BOTH identities. The context GitHub publishes is the
                # job's `name:` when it has one and the job KEY otherwise, and a
                # required-set comparison against only one of them matches
                # nothing: this repo's lax jobs are keyed `sast-semgrep` while
                # their contexts read "SAST — semgrep".
                found.append(
                    (
                        f"{os.path.basename(path)}:{name}",
                        {name.lower(), str(job.get("name") or name).lower()},
                    )
                )
    return found


def _probe_readable(path: str) -> bool:
    """Report whether a 404 (absent) rather than a 403 (unreadable) came back.

    _api collapses both to None, and the difference decides whether the verdict
    may say "no branch protection" — a claim that is simply false when the
    endpoint refused to answer.
    """
    proc = subprocess.run(
        ["gh", "api", path], capture_output=True, text=True, timeout=30
    )
    if proc.returncode == 0:
        return True
    return "Not Found" in proc.stderr or "404" in proc.stderr


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
    # The live path SYNTHESISES a ruleset from the effective-rules response, and
    # a filter verdict() enforces is only real if that synthesis carries the
    # field it filters on. Bypass was invisible exactly this way: verdict()
    # rejected bypass-laden rulesets, main() built one without the field, and
    # every unit assertion stayed green while the deployed pipeline admitted it.
    # Assert the wrapper here, since no shape driven through verdict() alone can
    # see it.
    # Every field verdict() filters on must be one synthesise_ruleset supplies,
    # or the filter is dead on the live path — which is how bypass_actors was
    # missed. Derived from the source rather than listed by hand: a hand-kept
    # list is one more thing to forget when a filter is added.
    import re

    src = pathlib.Path(__file__).read_text(encoding="utf-8")
    fn = src[src.index("def synthesise_ruleset") :]
    fn = fn[: fn.index("\ndef ", 10)]
    provided = set(re.findall(r'"([a-z_]+)":', fn))
    filtered = set(re.findall(r'r\.get\("([a-z_]+)"', src))
    # `name` feeds a message only; `ruleset_id` is read off the rules, not the
    # ruleset, so neither is the wrapper's to supply.
    unfed = filtered - provided - {"name", "ruleset_id"}
    if unfed:
        print(
            "SELF-TEST FAIL: verdict() filters on "
            f"{sorted(unfed)} which the live wrapper never supplies"
        )
        failures += 1
    else:
        print("  ok: every filtered field is one the live wrapper supplies")

    # The continue-on-error scan reads workflow files, so drive it against a
    # temporary directory rather than the repo's own: asserting on this checkout
    # would make the test's verdict depend on which repository it runs in.
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        io_open = open
        with io_open(os.path.join(td, "a.yml"), "w", encoding="utf-8") as fh:
            # The lax job carries a display name unlike its key, because the
            # required-set comparison must match EITHER — a job keyed `foo` can
            # publish its context as "Foo Bar", and matching only one finds
            # nothing on real workflows.
            fh.write(
                "jobs:\n"
                "  gating:\n    runs-on: x\n"
                "  lax:\n    name: Lax Display\n"
                "    continue-on-error: true\n    runs-on: x\n"
            )
        # A .yaml sibling, because the glob covering only .yml was a real gap and
        # a scratch probe of it left nothing behind to keep it closed.
        with io_open(os.path.join(td, "b.yaml"), "w", encoding="utf-8") as fh:
            fh.write("jobs:\n  yamllax:\n    continue-on-error: true\n    runs-on: x\n")
        found = non_blocking_jobs(td)
    labels = sorted(f for f, _ in found)
    identities = dict(found).get("a.yml:lax", set())
    if labels != ["a.yml:lax", "b.yaml:yamllax"] or identities != {
        "lax",
        "lax display",
    }:
        print(
            "SELF-TEST FAIL: the continue-on-error scan should report exactly "
            f"the lax job, got {found!r}"
        )
        failures += 1
    else:
        print("  ok: a job that cannot fail is reported, one that can is not")

    # The required-set filter, driven directly. Living only inside main() it
    # survived three mutations against a green self-test — the same shape as the
    # bypass filter this file already records.
    #
    # The first case is the one the key-only comparison failed: the workflow
    # knows the job as `sast-semgrep`, protection requires it as "SAST — semgrep".
    # The ASSEMBLY, composed. Every defect this file has shipped lived here
    # rather than in a piece: a filter handed the wrong argument, a wrapper built
    # without the field it is filtered on, a scan run unconditionally. Driving
    # the pieces alone left all three re-mergeable.
    #
    # The shape is CI's: protection unreadable (403), enforcement carried by an
    # active ruleset, the workflow scan finding one job that cannot fail.
    gate_ctx = [
        {"context": c}
        for c in ("gitleaks", "trufflehog", "SAST — semgrep", "Analyze (go)", "trivy")
    ]
    ci_rules = [
        {
            "type": "required_status_checks",
            "ruleset_id": 1,
            "parameters": {"required_status_checks": gate_ctx},
        }
    ]
    lax_job = [("security.yml:sast-semgrep", {"sast-semgrep", "sast — semgrep"})]

    def compose(jobs, bypass=None, slug="owner/repo"):
        return assemble_problems(
            None, False, ci_rules, bypass or [], [], slug, "owner/repo", jobs
        )

    only_lax = compose(lax_job)
    if len(only_lax) != 1 or "continue-on-error" not in only_lax[0]:
        print(
            "SELF-TEST FAIL: a required job that cannot fail must be the sole "
            f"finding in the CI shape, got {only_lax!r}"
        )
        failures += 1
    elif compose([("x.yml:other", {"other"})]) != []:
        print("SELF-TEST FAIL: a job that is not required must leave the CI shape clean")
        failures += 1
    elif compose(lax_job, bypass=[{"actor_id": 1}]) == only_lax:
        # A bypassable ruleset is discarded by verdict()'s filter, so the shape
        # degrades to "cannot establish enforcement" rather than naming bypass —
        # correct, since a ruleset anyone can step around establishes nothing.
        # What must not happen is the two shapes reporting identically, which is
        # what a wrapper dropping bypass_actors would produce.
        print(
            "SELF-TEST FAIL: a bypassable ruleset must not read the same as an "
            "enforcing one"
        )
        failures += 1
    elif compose(lax_job, slug="someone/else") != []:
        print(
            "SELF-TEST FAIL: a mismatched checkout must skip the scan, so no "
            "finding can come from another repository's workflows"
        )
        failures += 1
    else:
        print("  ok: the composed assembly reports exactly the finding each shape earns")

    # The required set can come from a RULESET instead of classic protection —
    # the configuration the flip instructions recommend, since CI can observe
    # rulesets and cannot read the protection endpoint. Taking it from
    # protection alone reported nothing there; assert the extraction here so
    # that stays fixed.
    ruleset_only = [
        {
            "enforcement": "active",
            "target": "branch",
            "rules": [
                {
                    "type": "required_status_checks",
                    "parameters": {
                        "required_status_checks": [{"context": "SAST — semgrep"}]
                    },
                }
            ],
        }
    ]
    from_ruleset = required_contexts(None, ruleset_only)
    if from_ruleset != {"sast — semgrep"}:
        print(
            "SELF-TEST FAIL: a ruleset's required contexts must count as required, "
            f"got {from_ruleset!r}"
        )
        failures += 1
    else:
        print("  ok: required contexts are read from rulesets as well as protection")

    lax = [("security.yml:sast-semgrep", {"sast-semgrep", "sast — semgrep"})]
    if unenforceable_required_jobs(lax, {"sast — semgrep"}) != ["security.yml:sast-semgrep"]:
        print("SELF-TEST FAIL: a required job named by its display name went unreported")
        failures += 1
    elif unenforceable_required_jobs(lax, {"sast-semgrep"}) != ["security.yml:sast-semgrep"]:
        print("SELF-TEST FAIL: a required job named by its key went unreported")
        failures += 1
    elif unenforceable_required_jobs(lax, {"something-else"}) != []:
        print("SELF-TEST FAIL: a job that is NOT required must not be accused")
        failures += 1
    elif unenforceable_required_jobs(lax, set()) != []:
        # An empty required set means nothing is required — on an unprotected
        # branch that is the normal state, and accusing every lax job there would
        # fill the report-only step with findings that are not violations.
        print("SELF-TEST FAIL: an empty required set must accuse nobody")
        failures += 1
    else:
        print("  ok: a required non-blocking job is named by either identity, and only when required")

    gates = [
        {"context": c}
        for c in ("gitleaks", "trufflehog", "sast-semgrep", "Analyze (go)", "trivy")
    ]
    live_rules = [
        {
            "type": "required_status_checks",
            "ruleset_id": 1,
            "parameters": {"required_status_checks": gates},
        }
    ]
    live = verdict(None, synthesise_ruleset(live_rules, [{"actor_id": 1}]))
    if not live:
        print(
            "SELF-TEST FAIL: a bypass-laden ruleset reads clean through the live "
            "wrapper, so the bypass filter never fires where it matters"
        )
        failures += 1
    else:
        print("  ok: the live wrapper carries bypass through to the filter")

    # The unreadable-protection branch is not one of the shapes above: it turns
    # on HOW the answer was obtained, not on what it said. Assert its wording,
    # because the whole point is that it must NOT claim protection is absent.
    unreadable = verdict(None, [], protection_readable=False)
    if not unreadable or "cannot establish enforcement" not in unreadable[0]:
        print(
            "SELF-TEST FAIL: an unreadable protection endpoint must say so, "
            f"got {unreadable!r}"
        )
        failures += 1
    elif "no branch protection" in unreadable[0]:
        print("SELF-TEST FAIL: unreadable was reported as absent")
        failures += 1
    else:
        print("  ok: unreadable protection -> reported as unreadable, not absent")

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


def assemble_problems(
    protection: dict | None,
    protection_readable: bool,
    effective: list[dict],
    bypass: list[dict],
    unreadable_rulesets: list[str],
    local_repo_slug: str,
    target_repo: str,
    workflow_jobs: list[tuple[str, set[str]]],
) -> list[str]:
    """Assemble the full verdict from already-fetched inputs.

    Pure, and separate from main() for the reason this file has now recorded
    three times: every defect it has shipped lived in the ASSEMBLY — a filter
    passed the wrong argument, a wrapper built without the field it is filtered
    on, a scan run unconditionally. Each instance was fixed and the class stayed
    open, because self_test() drove the pieces and never their composition.
    Mutating any wiring decision below now reds a committed case.
    """
    rulesets = synthesise_ruleset(effective, bypass)

    problems = verdict(
        protection if isinstance(protection, dict) else None,
        rulesets,
        protection_readable=protection_readable,
    )
    # A job that cannot fail cannot gate, whatever protection says about it.
    # Only REQUIRED contexts are judged: a reporting-only job carrying
    # continue-on-error is doing what it was built to do, and calling that a
    # violation would red every repository that has one.
    #
    # Consequence worth naming: on a branch with no protection this finds
    # nothing, because there are no required contexts to compare against. That
    # is not a miss — such a branch already reports the larger violation above.
    # It does mean the check first bites at flip time, which is exactly when a
    # continue-on-error gate would otherwise be marked required and enforce
    # nothing.
    # Both sources, because either can be the one enforcing. A branch protected
    # by a RULESET rather than by classic protection has an empty protection
    # payload, and taking the required set from protection alone would report no
    # unenforceable job on exactly the configuration the flip instructions
    # recommend — rulesets, because CI can observe them.
    required_names = required_contexts(protection, rulesets)
    # Only meaningful when the checkout IS the repository being judged. Reading
    # the local .github/workflows while --repo names a different repository
    # would report that repository's gates using this one's files — measured, and
    # it produced two findings that belonged to the wrong repo.
    local_repo = local_repo_slug
    jobs = workflow_jobs if local_repo == target_repo.lower() else []
    if not local_repo:
        print(
            "note: skipping the continue-on-error check — the checkout's own "
            "repository could not be determined from the git remote",
            file=sys.stderr,
        )
    elif local_repo != target_repo.lower():
        print(
            f"note: skipping the continue-on-error check — this checkout is "
            f"{local_repo}, not {target_repo}",
            file=sys.stderr,
        )
    for job in unenforceable_required_jobs(jobs, required_names):
        problems.append(
            f"{job} carries continue-on-error, so it reports success whatever it "
            "finds — a required context that cannot fail is presence, not "
            "enforcement"
        )

    for rid in unreadable_rulesets:
        problems.append(
            f"cannot establish the bypass posture for ruleset {rid}: it is "
            "unreadable with this token, and a ruleset whose bypass actors "
            "cannot be read must not be assumed to have none"
        )

    return problems


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
    # _api returns None for BOTH "404, no protection" and "403, cannot read it".
    # The verdict has to tell them apart, so ask again without the optional
    # escape: a genuine 404 still yields None, while a 403 exits non-zero — so
    # reaching here with None twice means absent, not unreadable.
    protection_readable = protection is not None or _probe_readable(
        f"repos/{args.repo}/branches/{args.branch}/protection"
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
    # Resolve bypass actors, which the effective-rules response does not carry:
    # bypass is a property of the RULESET, not of a rule. Without this the
    # bypass filter in verdict() is dead on the live path — the synthetic
    # ruleset was built without the field, so it always passed. The tested
    # function was stricter than the deployed pipeline, which is the shape a
    # unit test cannot catch on its own.
    bypass: list[dict] = []
    unreadable_rulesets: list[str] = []
    for rid in sorted({r.get("ruleset_id") for r in effective if r.get("ruleset_id")}):
        rs = _api(f"repos/{args.repo}/rulesets/{rid}", optional=True)
        if isinstance(rs, dict):
            bypass += rs.get("bypass_actors") or []
        else:
            # Defaulting to bypass-free here would be the same defect the
            # protection leg was just fixed for, on the leg that carries the
            # verdict in CI — and it errs the unsafe way: a token that cannot
            # read the ruleset would report a bypassable branch as enforced.
            unreadable_rulesets.append(str(rid))

    problems = assemble_problems(
        protection if isinstance(protection, dict) else None,
        protection_readable,
        effective,
        bypass,
        unreadable_rulesets,
        _local_repo_slug(),
        args.repo,
        non_blocking_jobs(),
    )

    if problems:
        print(f"NFR-SEC-89 VIOLATION on {args.repo}@{args.branch}:")
        for p in problems:
            print(f"  - {p}")
        # Annotate, so the finding survives the log. The CI step is report-only
        # by design -- enabling protection is an owner action, and blocking here
        # would red every PR for a condition no PR can fix -- but report-only
        # printed into a log nobody opens is the theatre this NFR names. A
        # warning annotation appears on the PR without failing the run.
        if os.environ.get("GITHUB_ACTIONS") == "true":
            # A newline in either field ENDS the annotation and lets whatever
            # follows be read as its own workflow command, so a branch name on
            # a fork PR could forge one. Strip the separators rather than trust
            # the source: %0A is the encoding a real multi-line annotation uses.
            def _one_line(text: str) -> str:
                return (
                    str(text)
                    .replace("\r", " ")
                    .replace("\n", " ")
                    .replace("::", ": ")
                )

            summary = _one_line("; ".join(problems))
            print(
                f"::warning title=NFR-SEC-89: gates are not enforced on "
                f"{_one_line(args.branch)}::{summary}"
            )
        print(
            "\nEvery gate can be green and every one of them merged past. "
            "Presence is not enforcement."
        )
        return 1

    print(f"NFR-SEC-89 holds on {args.repo}@{args.branch}: the gates block.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
