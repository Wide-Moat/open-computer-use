# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""Every scanner invocation names the scanner build it runs.

Pinning `uses:` to a commit pins the action, not the tool the action
downloads. A gate whose scanner floats can reach two different verdicts over
an unchanged tree, and neither verdict is reproducible from the repository --
which is the first property an audit asks a security gate to have.

Run directly (`python3 tests/security/test_scanner_version_pinned.py`) or
under pytest. Exit 0 = every invocation is pinned, 1 = at least one is not.
"""

import os
import sys

import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKFLOW_DIR = os.path.join(REPO_ROOT, ".github", "workflows")

# action name fragment -> the input that names the tool build it fetches
PINNED_INPUT = {
    "aquasecurity/trivy-action": "version",
}


def invocations(workflow_dir=WORKFLOW_DIR):
    """Yield (file, job, step_name, action, pinned_value_or_None) per call."""
    found = []
    if not os.path.isdir(workflow_dir):
        raise SystemExit(f"no workflow directory at {workflow_dir}; nothing was checked")
    names = sorted(
        n for n in os.listdir(workflow_dir) if n.endswith((".yml", ".yaml"))
    )
    if not names:
        raise SystemExit(f"{workflow_dir} holds no workflow files; nothing was checked")
    for name in names:
        path = os.path.join(workflow_dir, name)
        with open(path) as fh:
            doc = yaml.safe_load(fh)
        if not isinstance(doc, dict):
            continue
        for job_name, job in (doc.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            for step in job.get("steps") or []:
                if not isinstance(step, dict):
                    continue
                uses = step.get("uses") or ""
                for action, input_name in PINNED_INPUT.items():
                    if action in uses:
                        with_block = step.get("with") or {}
                        found.append(
                            (
                                name,
                                job_name,
                                step.get("name") or uses,
                                action,
                                with_block.get(input_name),
                            )
                        )
    return found


def check(workflow_dir=WORKFLOW_DIR):
    calls = invocations(workflow_dir)
    if not calls:
        # An empty set would pass every assertion below. Absence of a scanner
        # is a different problem from an unpinned one, and it is not this
        # check's business to be silent about it.
        raise SystemExit(
            "no scanner invocation found in any workflow; this check verified nothing"
        )

    problems = []
    for fname, job, step, action, pinned in calls:
        if not pinned:
            problems.append(
                f"{fname}: job {job!r} step {step!r} runs {action} without naming a "
                f"scanner build; the action fetches whatever its default resolves to"
            )

    # Two passes of the same scanner that run different builds produce an
    # exception ledger describing findings the blocking pass never emitted.
    by_action = {}
    for _, _, _, action, pinned in calls:
        if pinned:
            by_action.setdefault(action, set()).add(pinned)
    for action, versions in by_action.items():
        if len(versions) > 1:
            problems.append(
                f"{action} runs more than one build across the workflows: "
                f"{sorted(versions)}"
            )

    for problem in problems:
        print(f"FAIL {problem}", file=sys.stderr)
    print(
        f"ok {len(calls)} scanner invocation(s) examined; "
        f"{len(calls) - len([p for p in problems if 'without naming' in p])} pinned"
    )
    return 1 if problems else 0


def test_scanner_version_pinned():
    assert check() == 0


if __name__ == "__main__":
    sys.exit(check())
