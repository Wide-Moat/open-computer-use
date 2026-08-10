#!/usr/bin/env python3
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
#
# Actions used through SEVERAL SUBPATHS of one repository must share a SHA.
#
# github/codeql-action ships init, autobuild, and analyze as three paths in ONE
# repository, and CodeQL refuses to run when they disagree: "Loaded a
# configuration file for version '4.36.2', but running version '4.37.5'". The
# same holds for any multi-path action.
#
# Dependabot opens one PR per PATH, so a package with three used paths arrives
# as three PRs that each break the trio in isolation. Merging any one of them
# reds CodeQL on every subsequent PR, and the failure names a version mismatch
# rather than the split bump that produced it.
#
# The rule is scoped to multi-subpath packages on purpose. A single-path action
# like actions/checkout is a fresh, independent invocation each time, so two
# workflows may sit on different versions without interacting; demanding one SHA
# there would be a house-style opinion, not a correctness gate. What breaks is
# subpaths of one package that share runtime state.
#
# zizmor's unpinned-uses rule checks that each ref IS a SHA. It does not check
# that sibling subpaths share one, which is the failure this catches.
#
# --self-test plants a divergent pin and asserts the check goes RED, then
# asserts the shipped tree passes.
import os
import re
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOWS = os.path.join(ROOT, ".github", "workflows")

# owner/repo[/subpath]@sha — the SHA is what must agree across subpaths.
USES_RE = re.compile(r"uses:\s*([A-Za-z0-9._-]+/[A-Za-z0-9._-]+)(/[A-Za-z0-9._/-]+)?@([0-9a-f]{40})")


def scan(workflows=WORKFLOWS):
    """Return {package: {sha: [locations]}} for SHA-pinned actions, and the set
    of subpaths seen per package."""
    seen = defaultdict(lambda: defaultdict(list))
    subpaths = defaultdict(set)
    if not os.path.isdir(workflows):
        return seen
    for name in sorted(os.listdir(workflows)):
        if not name.endswith((".yml", ".yaml")):
            continue
        path = os.path.join(workflows, name)
        with open(path, encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                m = USES_RE.search(line)
                if m:
                    pkg, sub, sha = m.group(1), m.group(2) or "", m.group(3)
                    seen[pkg][sha].append(f"{name}:{lineno}{sub}")
                    subpaths[pkg].add(sub)
    return seen, subpaths


def check(workflows=WORKFLOWS, quiet=False):
    """Return a list of failure strings; empty means every package agrees."""
    seen, subpaths = scan(workflows)
    if not seen:
        return ["no SHA-pinned actions found; this gate would be vacuous"]
    multi = {p for p, subs in subpaths.items() if len(subs) > 1}
    if not multi:
        return ["no action is used through more than one subpath; this gate would be vacuous"]
    problems = []
    for pkg, by_sha in sorted(seen.items()):
        if pkg in multi and len(by_sha) > 1:
            detail = "; ".join(f"{sha[:8]} at {', '.join(locs)}" for sha, locs in sorted(by_sha.items()))
            problems.append(
                f"{pkg} is pinned to {len(by_sha)} different SHAs — {detail}. "
                f"Paths of one action repository must share a SHA (a split dependabot bump does this)."
            )
    if not quiet:
        print(f"action-pin-consistency: {len(multi)} multi-subpath package(s) checked, each pinned to one SHA")
    return problems


def self_test():
    import shutil
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        work = os.path.join(tmp, "workflows")
        shutil.copytree(WORKFLOWS, work)
        if check(work, quiet=True):
            print("::error::action-pin-consistency: the shipped tree already fails; the mutation below would prove nothing", file=sys.stderr)
            sys.exit(1)

        # Find a package used at two or more locations and split it.
        target = None
        seen_w, subs_w = scan(work)
        for pkg, by_sha in seen_w.items():
            if len(subs_w[pkg]) < 2:
                continue
            locs = next(iter(by_sha.values()))
            if len(locs) >= 2:
                target = (pkg, next(iter(by_sha)), locs[0].split(":")[0])
                break
        if target is None:
            print("::error::action-pin-consistency: no multi-subpath action to mutate; the self-test cannot prove anything", file=sys.stderr)
            sys.exit(1)

        pkg, sha, fname = target
        path = os.path.join(work, fname)
        with open(path, encoding="utf-8") as f:
            body = f.read()
        # Diverge exactly one occurrence.
        body = body.replace("@" + sha, "@" + "0" * 40, 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)

        if not check(work, quiet=True):
            print(f"::error::action-pin-consistency: a divergent pin on {pkg} was NOT caught", file=sys.stderr)
            sys.exit(1)

    print("action-pin-consistency self-test: a divergent pin reds the gate; the shipped tree passes")


def main(argv):
    if "--self-test" in argv:
        self_test()
        return 0
    problems = check()
    for p in problems:
        print(f"::error::action-pin-consistency: {p}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
