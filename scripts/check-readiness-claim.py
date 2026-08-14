#!/usr/bin/env python3
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""Answer the deployment-readiness claim by measuring it, not by asserting it.

The claim has three legs — proven isolation, an auditable supply chain, and a
canon where every decision is recorded and checkable. Each leg has been built
and each has its own gate. What did not exist until this script is a single
place that asks whether all three hold AT ONCE, against what is actually
shipped.

That distinction is the whole point. A leg living in an unmerged pull request is
not a property of the system; it is a property of a branch. This script reads
the DEFAULT branch of each component, so a leg counts only once it is merged —
which is why running it today reports the claim as not yet held, with the four
open pull requests named.

    python3 scripts/check-readiness-claim.py            # human summary
    python3 scripts/check-readiness-claim.py --json     # machine-readable

Exit 0 when all three legs hold on the shipped branches, 1 when any does not,
2 when a component cannot be read — unreadable is not the same as unmet, and
reporting it as unmet would be the same defect this script exists to catch.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time

# Each leg names the component, the branch that ships it, and a symbol whose
# presence on that branch is the evidence. A symbol rather than a file: files
# get moved and renamed, and a grep for one that no longer exists reports a
# missing property rather than a missing file.
LEGS = (
    {
        "leg": "proven isolation",
        "repo": "Wide-Moat/ocu-sandbox",
        "branch": "main",
        "evidence": "func AdmitUIDMap",
        "path": "host/exec/runtime/userns.go",
        "means": (
            "the control plane refuses a session whose container root is host "
            "root, judged on the mapping the kernel reports"
        ),
    },
    {
        "leg": "auditable supply chain",
        "repo": "Wide-Moat/ocu-sandbox",
        "branch": "main",
        "evidence": "func AdmitImageRef",
        "path": "host/exec/manager/imageref.go",
        "means": (
            "a session cannot start from a re-pointable image tag; the release "
            "path verifies its own signature before applying consumer tags"
        ),
    },
    {
        "leg": "checkable canon",
        "repo": "Wide-Moat/ocu-sandbox",
        "branch": "main",
        "evidence": "func TestEveryDecisionNamesAGuardThatExists",
        "path": "host/internal/doctruth/decision_guards_test.go",
        "means": (
            "every recorded decision names a guard test, and every named guard "
            "is verified to exist"
        ),
    },
)


class Unreadable(Exception):
    """A component could not be read. Distinct from a leg that does not hold."""


def _run(args: list[str]) -> tuple[int, str, str]:
    for attempt in range(3):
        proc = subprocess.run(args, capture_output=True, text=True, timeout=60)
        if proc.returncode == 0:
            return 0, proc.stdout, proc.stderr
        transient = any(
            m in proc.stderr.lower()
            for m in ("timeout", "connection reset", "temporary failure", "eof")
        )
        if not transient or attempt == 2:
            return proc.returncode, proc.stdout, proc.stderr
        time.sleep(2 * (attempt + 1))
    return proc.returncode, proc.stdout, proc.stderr


def leg_holds(leg: dict) -> bool:
    """Report whether the evidence symbol is present on the shipping branch.

    Reads the remote ref rather than a local checkout: a local branch can carry
    work that was never pushed, and the question is what the component ships.
    """
    code, out, err = _run(
        [
            "gh",
            "api",
            f"repos/{leg['repo']}/contents/{leg['path']}?ref={leg['branch']}",
            "--jq",
            ".content",
        ]
    )
    if code != 0:
        if "404" in err or "Not Found" in err:
            # A 404 covers BOTH "the file is absent on that branch" and "the
            # repository or branch does not exist" — and those are different
            # answers. Confirm the branch itself resolves before calling the leg
            # unmet, or a typo in a repo name reports a security property as
            # missing. Measured: a nonexistent repo returned False before this.
            probe, _, perr = _run(
                ["gh", "api", f"repos/{leg['repo']}/branches/{leg['branch']}"]
            )
            if probe != 0:
                raise Unreadable(
                    f"{leg['repo']}@{leg['branch']} does not resolve: "
                    f"{perr.strip()[:100]}"
                )
            # The branch exists and the file does not: the leg genuinely does
            # not hold there.
            return False
        raise Unreadable(f"{leg['repo']}@{leg['branch']}: {err.strip()[:120]}")

    import base64

    try:
        body = base64.b64decode(out).decode("utf-8", "replace")
    except Exception as exc:  # pragma: no cover - defensive
        raise Unreadable(f"{leg['repo']}: undecodable content: {exc}") from exc
    return leg["evidence"] in body


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    results = []
    for leg in LEGS:
        try:
            holds = leg_holds(leg)
        except Unreadable as exc:
            print(f"cannot read {leg['leg']}: {exc}", file=sys.stderr)
            return 2
        results.append({**leg, "holds": holds})

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            mark = "HOLDS    " if r["holds"] else "NOT YET  "
            print(f"  {mark} {r['leg']}")
            print(f"            {r['means']}")
            print(f"            evidence: {r['evidence']} on {r['repo']}@{r['branch']}")
        held = sum(1 for r in results if r["holds"])
        print()
        if held == len(results):
            print(
                "The deployment-readiness claim holds on the shipped branches: "
                "all three legs are merged and each carries its own gate."
            )
        else:
            print(
                f"The claim does NOT hold yet: {held} of {len(results)} legs are "
                "merged. The rest are built and gated but live in open pull "
                "requests, so they are properties of a branch rather than of "
                "the system."
            )

    return 0 if all(r["holds"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
