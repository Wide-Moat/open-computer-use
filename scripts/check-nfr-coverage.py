#!/usr/bin/env python3
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""Report how many NFRs are checked by something that runs, not by prose.

An NFR is a claim. A claim nobody executes is a claim the reader has to take on
trust, and this repository's own rule is that a property measured only when
somebody remembers to ask is not enforced. NFR-SEC-89 says that about security
gates; the same sentence applies one level up, to the requirements themselves.

Measured when this was written: of 188 NFR ids in the manifesto, exactly ONE --
NFR-SEC-89 -- is named by any script or workflow. The other 187 exist as table
rows. That is not a defect to fix in one commit; it is the state of the layer,
and the point of this check is that the number appears on every run instead of
being rediscovered by whoever next goes looking.

The check is deliberately narrow. "Armed" means a script or workflow NAMES the
id. It does not claim the named check PROVES the requirement -- no lint can
judge that, and pretending otherwise would make this the same kind of decorative
assertion it exists to count. What it removes is the cheaper failure: believing
the set is measured when almost none of it is.

    check-nfr-coverage.py [--repo-root .] [--min-armed N] [--self-test]

Why the number stops where it does. Twenty rows state a CI-gate verification;
eleven are armed, and each of the remaining nine is blocked by something a
commit cannot supply:

    NFR-SEC-12    component 06-egress-trust-edge is status:draft, contract:null
    NFR-SEC-37    needs observed traffic between running components
    NFR-IC-05     the contract itself says carrier: none (gateway behaviour,
                  not a wire field) -- there is no artifact to check
    NFR-MAINT-07  no ORM, no migrations, no SQL exists in the tree yet
    NFR-MAINT-08  drift detection needs a running deployment
    NFR-MAINT-10  patch coverage needs a threshold decision, and the Python
                  surface here is PoC code rather than next/v1 architecture
    NFR-MAINT-11  needs the parsers and schedulers the components will bring
    NFR-PERF-13   needs a green baseline to regress against
    NFR-FLEX-03   needs an IdP integration to be portable across
    NFR-COST-05   needs session accounting that does not exist
    NFR-COMP-25   marked REVISIT, non-gating

That list is the answer to "why not more", and it is here rather than in a
commit message so the next person reads it before re-deriving it.

--min-armed is a RATCHET. It fails when coverage drops below the floor, so an
armed NFR cannot quietly become unarmed -- the number can only go up. It does
not fail for the 187, because failing the build on a state no PR can fix would
make this gate the thing that blocks fixing it.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

# Not `-\d+`: three rows do not end in a bare number -- NFR-FLEX-07a,
# NFR-FLEX-07b (lowercase suffix) and NFR-MAINT-AUDIT-SCHEMA (a word). A
# numeric-only pattern read the
# manifesto as 187 rows when it holds 190, and an arm on any of the three would
# have been invisible to the ratchet: the coverage number would not move and
# nothing would say why.
# The floor, in the file the check lives in. A caller may raise it; a caller
# that passes LESS is refused, because the only legitimate reason for the
# number to fall is that an NFR genuinely stopped being checked -- and that is
# what the coverage comparison already catches, loudly.
COMMITTED_FLOOR = 11

NFR_ID = re.compile(r"NFR-[A-Z]+-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*")
MANIFESTO = "docs/architecture/manifesto/02-nfrs.md"
# Where an executable check can live. Docs are excluded on purpose: an id named
# in prose is the thing this script measures the absence of.
#
# `tests` is here because that is where some checks actually are:
# NFR-SEC-15's stated verification is the /home/assistant volume-size assertion
# in tests/test-docker-image.sh, which build.yml runs and which blocks. Naming
# it anywhere else to satisfy this scanner would put the id away from the
# assertion that answers it.
CODE_DIRS = ("scripts", ".github", "tests")


def declared_ids(root: pathlib.Path) -> set[str]:
    """Every NFR id the manifesto defines as a table row.

    Row-anchored rather than a bare sweep: the manifesto also MENTIONS ids in
    prose and in cross-references, and counting those would inflate the
    denominator with things that were never separate requirements.
    """
    path = root / MANIFESTO
    if not path.is_file():
        return set()
    ids: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.split("|")]
        # cells[0] is the empty string before the leading pipe.
        if len(cells) > 1 and NFR_ID.fullmatch(cells[1]):
            ids.add(cells[1])
    return ids


def armed_ids(root: pathlib.Path, ids: set[str]) -> dict[str, list[str]]:
    """Ids named by a file under CODE_DIRS, with the files that name them.

    Reads the working tree rather than a git ref so the check answers for what
    is about to be committed, not for what is already on the branch.
    """
    hits: dict[str, list[str]] = {}
    this_file = pathlib.Path(__file__).resolve()
    for directory in CODE_DIRS:
        base = root / directory
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            # Never count this script. Its self-test fixtures name NFR-SEC-01
            # and NFR-SEC-02, and without this the checker reports them as
            # armed -- by itself. Measured: coverage read 3 of 187 with the two
            # fixtures counted, 1 of 187 without. A gate that satisfies its own
            # assertion is the failure mode this whole file exists to name.
            if path.resolve() == this_file:
                continue
            # Build artifacts are not checks. A .pyc keeps the NFR ids of the
            # source it was compiled from, so a deleted checker stays "armed"
            # as long as its cache survives -- measured on a copy of this tree:
            # delete check-pin-policy.py with __pycache__ present and the
            # ratchet still reads 11. The id is named by a file that no longer
            # runs. A clean checkout has no cache, so this also removes a
            # difference between what CI counts and what a developer counts.
            if "__pycache__" in path.parts or path.suffix in (".pyc", ".pyo"):
                continue
            try:
                body = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for found in set(NFR_ID.findall(body)) & ids:
                hits.setdefault(found, []).append(
                    str(path.relative_to(root))
                )
    return hits


def verdict(declared: set[str], armed: dict[str, list[str]], floor: int) -> list[str]:
    """Reasons to refuse. Empty means the ratchet holds.

    Split from the filesystem walk so --self-test can drive it with constructed
    sets: a check whose logic only runs against the real tree is a check nobody
    can prove still discriminates.
    """
    problems: list[str] = []
    unknown = set(armed) - declared
    if unknown:
        problems.append(
            "named by a check but absent from the manifesto: "
            + ", ".join(sorted(unknown))
            + " -- a check pinned to an id that no longer exists proves nothing"
        )
    if len(armed) < floor:
        problems.append(
            f"armed NFRs dropped to {len(armed)}, below the floor of {floor}: "
            + ", ".join(sorted(declared - set(armed) if floor else []))[:200]
        )
    return problems


def _self_test() -> int:
    cases = [
        ("a dropped arm reds", {"NFR-A-1", "NFR-A-2"}, {"NFR-A-1": ["s"]}, 2, True),
        ("holding the floor passes", {"NFR-A-1", "NFR-A-2"}, {"NFR-A-1": ["s"], "NFR-A-2": ["s"]}, 2, False),
        ("gaining an arm passes", {"NFR-A-1", "NFR-A-2"}, {"NFR-A-1": ["s"], "NFR-A-2": ["s"]}, 1, False),
        ("a floor of zero never reds on count", {"NFR-A-1"}, {}, 0, False),
        ("an id no manifesto row declares reds", {"NFR-A-1"}, {"NFR-A-1": ["s"], "NFR-GONE-9": ["s"]}, 1, True),
    ]
    failures = 0
    for name, declared, armed, floor, want_red in cases:
        got_red = bool(verdict(declared, armed, floor))
        ok = got_red == want_red
        failures += 0 if ok else 1
        print(f"  {'ok' if ok else 'FAIL'}: {name}")

    # The parser is the other half: a row-anchored read must not count ids that
    # only appear in prose, or the denominator inflates and coverage looks worse
    # than it is -- an alarm that cries wolf gets switched off.
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        (root / MANIFESTO).parent.mkdir(parents=True)
        (root / MANIFESTO).write_text(
            "Prose mentioning NFR-SEC-99 which is not a row.\n"
            "| NFR-SEC-01 | a real row |\n"
            "| NFR-SEC-02 | another row, see NFR-SEC-01 |\n"
            # Neither of these ends in a bare number. The first pattern here
            # read only `-\\d+` and silently undercounted the manifesto by
            # three rows, which also made an arm on any of them invisible.
            "| NFR-FLEX-07a | a lowercase-suffixed row |\n"
            "| NFR-MAINT-AUDIT-SCHEMA | a word-suffixed row |\n",
            encoding="utf-8",
        )
        got = declared_ids(root)
        want = {"NFR-SEC-01", "NFR-SEC-02", "NFR-FLEX-07a", "NFR-MAINT-AUDIT-SCHEMA"}
        ok = got == want
        failures += 0 if ok else 1
        print(f"  {'ok' if ok else 'FAIL'}: only table rows count as declared ({sorted(got)})")

    # The floor itself has to be un-lowerable, and the constant has to match
    # what the workflow passes -- a floor the caller can undercut is decoration.
    import subprocess

    wf = pathlib.Path(__file__).resolve().parents[1] / ".github/workflows/contracts-lint.yml"
    if wf.is_file():
        text = wf.read_text(encoding="utf-8")
        passed = [
            int(part.split()[0])
            for part in text.split("--min-armed ")[1:]
            if part.split() and part.split()[0].isdigit()
        ]
        ok = bool(passed) and all(v >= COMMITTED_FLOOR for v in passed)
        failures += 0 if ok else 1
        print(
            f"  {'ok' if ok else 'FAIL'}: the workflow never passes less than "
            f"COMMITTED_FLOOR ({passed} vs {COMMITTED_FLOOR})"
        )

    rc = main(["--min-armed", str(COMMITTED_FLOOR - 1)])
    ok = rc == 2
    failures += 0 if ok else 1
    print(f"  {'ok' if ok else 'FAIL'}: a caller below the floor is refused (exit {rc})")

    print()
    if failures:
        print(f"self-test: {failures} case(s) failed")
        return 1
    print("self-test: the check reds on a dropped arm and a stale id, counts rows only, and refuses a lowered floor.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    # Default to the committed floor, not to 1. The floor lived only in the
    # workflow's --min-armed argument, so lowering it was a one-character edit
    # that nothing noticed: measured, changing 11 to 1 left the check green and
    # silent. A ratchet that can be wound backwards without a sound is not one.
    ap.add_argument("--min-armed", type=int, default=COMMITTED_FLOOR)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()

    if args.min_armed < COMMITTED_FLOOR:
        print(
            f"::error::--min-armed {args.min_armed} is below the committed floor "
            f"of {COMMITTED_FLOOR}. Raising the floor is a normal commit; lowering "
            "it means an NFR stopped being checked, which this refuses to do "
            "quietly. Change COMMITTED_FLOOR in this file, in the same commit "
            "that removes the arm, and say why.",
            file=sys.stderr,
        )
        return 2

    root = pathlib.Path(args.repo_root).resolve()
    declared = declared_ids(root)
    if not declared:
        print(f"::error::no NFR rows found in {MANIFESTO} -- the check cannot judge", file=sys.stderr)
        return 2

    armed = armed_ids(root, declared)
    print(f"NFR coverage: {len(armed)} of {len(declared)} ids are named by a check that runs")
    for nfr in sorted(armed):
        print(f"  armed  {nfr}  <- {', '.join(sorted(set(armed[nfr])))}")

    problems = verdict(declared, armed, args.min_armed)
    if problems:
        for problem in problems:
            print(f"::error::{problem}", file=sys.stderr)
        return 1

    print(
        f"the ratchet holds at {args.min_armed}. The remaining "
        f"{len(declared) - len(armed)} are prose: true as written, unproven by anything "
        "that runs."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
