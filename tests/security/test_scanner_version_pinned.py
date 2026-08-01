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
import re
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


# Scanner binaries a script can call directly. An action's `version:` input
# has no equivalent here: a bare `trivy ...` runs whatever build is on PATH,
# and the repository does not say which.
SCANNER_BINARIES = ("trivy", "syft", "grype")

SCRIPT_SUFFIXES = (".sh", ".bash")


def bare_invocations(root=REPO_ROOT):
    """Yield (file, line, binary) for scanner calls made outside a workflow.

    Walking only `.github/workflows` answers a narrower question than the one
    a reader takes from a green result. A scan driven from a shell script or
    a Dockerfile is a scan, and its build is no more pinned for living
    somewhere the workflow walk does not reach.
    """
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames if d not in (".git", "node_modules", ".venv")
        ]
        # Workflow files are the other arm's business.
        if os.path.relpath(dirpath, root).startswith(os.path.join(".github", "workflows")):
            continue
        for name in filenames:
            if not (name.endswith(SCRIPT_SUFFIXES) or name.startswith("Dockerfile")):
                continue
            path = os.path.join(dirpath, name)
            try:
                with open(path, errors="replace") as fh:
                    lines = fh.readlines()
            except OSError:
                continue
            for lineno, line in enumerate(lines, 1):
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                for binary in SCANNER_BINARIES:
                    # A command position: start of line, or after a pipe,
                    # `&&`, `;` or `$(`. Not a substring of another word.
                    if re.search(rf"(^|[|;&]|\$\()\s*{re.escape(binary)}\s", stripped):
                        found.append(
                            (os.path.relpath(path, root), lineno, binary)
                        )
                        break
    return sorted(found)


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

    # A scanner called from a script runs whatever build is on PATH. The
    # repository cannot say which, so the pin above describes a subset while
    # reading as the whole.
    bare = bare_invocations()
    for path, lineno, binary in bare:
        problems.append(
            f"{path}:{lineno} calls {binary} directly; the build it runs comes "
            f"from PATH and is not stated anywhere in the repository"
        )

    for problem in problems:
        print(f"FAIL {problem}", file=sys.stderr)
    unpinned = len([p for p in problems if "without naming" in p])
    print(
        f"ok {len(calls)} action invocation(s) examined, {len(calls) - unpinned} "
        f"pinned; {len(bare)} direct call(s) outside a workflow"
    )
    return 1 if problems else 0


def test_scanner_version_pinned():
    assert check() == 0


if __name__ == "__main__":
    sys.exit(check())
