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

NFR_ID = re.compile(r"NFR-[A-Z]+-\d+")
MANIFESTO = "docs/architecture/manifesto/02-nfrs.md"
# Where an executable check can live. Docs are excluded on purpose: an id named
# in prose is the thing this script measures the absence of.
CODE_DIRS = ("scripts", ".github")


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
            "| NFR-SEC-02 | another row, see NFR-SEC-01 |\n",
            encoding="utf-8",
        )
        got = declared_ids(root)
        want = {"NFR-SEC-01", "NFR-SEC-02"}
        ok = got == want
        failures += 0 if ok else 1
        print(f"  {'ok' if ok else 'FAIL'}: only table rows count as declared ({sorted(got)})")

    print()
    if failures:
        print(f"self-test: {failures} case(s) failed")
        return 1
    print("self-test: the check reds on a dropped arm and a stale id, and counts rows only.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--min-armed", type=int, default=1)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()

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
