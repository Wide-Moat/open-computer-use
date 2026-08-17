#!/usr/bin/env python3
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""Refuse a self-test that passes while the thing it tests is broken.

Every checker in scripts/ carries a --self-test, and CI runs each one as its own
blocking step. That arrangement proves the self-tests EXIST. It does not prove
any of them would notice if the checker stopped working -- a self-test whose
fixtures agree with a broken predicate is the same fake-green it was written to
prevent, one level up.

So: break each checker, run its own self-test, and require a failure.

The mutation is deliberately crude -- force the function that returns findings
to return none, which is what every one of these checkers looks like when it
has silently stopped discriminating. A self-test that still passes under that
is not bound to its subject.

Measured when this was written: seven checkers, seven caught. That is the
result worth keeping green, because the failure it guards against is invisible
by construction -- everything stays green while nothing is checked.

    check-self-tests-are-bound.py [--root .] [--self-test]
"""

from __future__ import annotations

import argparse
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

# The function whose emptiness means "found nothing" in each checker. Named
# rather than guessed: a regex over `def ...` would hit helpers and report a
# checker as unbound because the wrong function was stubbed.
SUBJECTS: dict[str, str] = {
    "check-pin-policy.py": "unpinned_uses",
    "check-no-vendor-sdk.py": "vendor_imports",
    "check-compliance-front-matter.py": "verdict",
    "check-schemas-are-closed.py": "open_nodes",
    "check-nfr-coverage.py": "verdict",
    "check-gates-are-required.py": "verdict",
    "check-readiness-claim.py": "leg_holds",
    "check-contract-refs-are-local.py": "check_file",
    "check-gates-trigger-on-canon.py": "findings",
}

# What "found nothing" looks like for each: a list of findings, or a bool that
# means the leg holds.
EMPTY_RETURN = {"leg_holds": "True", "_default": "[]"}


def stub(source: str, function: str) -> str | None:
    """Return `source` with `function` short-circuited, or None if not found."""
    match = re.search(rf"^def {re.escape(function)}\(.*?\).*?:\n", source, re.S | re.M)
    if not match:
        return None
    value = EMPTY_RETURN.get(function, EMPTY_RETURN["_default"])
    at = match.end()
    return source[:at] + f"    return {value}  # STUB\n" + source[at:]


def self_test_notices(root: pathlib.Path, name: str, function: str) -> tuple[bool, str]:
    """True when the checker's own --self-test fails once it is stubbed."""
    target = root / "scripts" / name
    if not target.is_file():
        return False, "checker not present"
    original = target.read_text(encoding="utf-8")
    mutated = stub(original, function)
    if mutated is None:
        return False, f"could not stub {function}() -- signature changed?"
    # A copy of the tree, so a probe cannot leave the checkout mutated if this
    # process dies between write and restore.
    with tempfile.TemporaryDirectory() as tmp:
        work = pathlib.Path(tmp) / "scripts"
        shutil.copytree(root / "scripts", work)
        (work / name).write_text(mutated, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(work / name), "--self-test"],
            capture_output=True,
            text=True,
            cwd=root,
        )
    return proc.returncode != 0, f"exit {proc.returncode}"


def _self_test() -> int:
    failures = 0
    cases = [
        ("a list-returning function is stubbed to []", "def f(x) -> list[str]:\n    return [1]\n", "f", "return []"),
        ("leg_holds is stubbed to True", "def leg_holds(leg) -> bool:\n    return False\n", "leg_holds", "return True"),
        ("a multi-line signature is still matched", "def f(\n    a,\n    b,\n) -> list:\n    return [1]\n", "f", "return []"),
    ]
    for name, src, fn, expected in cases:
        out = stub(src, fn)
        ok = out is not None and expected in out
        failures += 0 if ok else 1
        print(f"  {'ok' if ok else 'FAIL'}: {name}")

    missing = stub("def other(): pass\n", "absent")
    ok = missing is None
    failures += 0 if ok else 1
    print(f"  {'ok' if ok else 'FAIL'}: an absent function reports rather than silently passing")

    print()
    if failures:
        print(f"self-test: {failures} case(s) failed")
        return 1
    print("self-test: the stubber rewrites the named function and reports when it cannot.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()

    root = pathlib.Path(args.root).resolve()
    unbound: list[str] = []
    for name, function in sorted(SUBJECTS.items()):
        noticed, detail = self_test_notices(root, name, function)
        print(f"  {'bound' if noticed else 'UNBOUND'}  {name} ({function}: {detail})")
        if not noticed:
            unbound.append(f"{name} ({detail})")

    if unbound:
        for item in unbound:
            print(
                f"::error::{item} -- its --self-test passes while the checker is "
                "stubbed, so the self-test proves the checker exists and not that "
                "it works",
                file=sys.stderr,
            )
        return 1

    print(
        f"every one of {len(SUBJECTS)} checkers fails its own self-test when stubbed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
