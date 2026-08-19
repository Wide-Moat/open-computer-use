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
    "check-security-txt.py": "problems",
    "check-mcp-protocol-version.py": "unsupported",
    "check-release-synthetic.py": "unguarded_publishers",
    "check-browser-storage-clean.py": "leaks",
    "check-file-activity-overlay.py": "problems",
    "check-soar-revoke-frozen.py": "problems",
    "check-operator-bodies-hint-only.py": "problems",
    "check-arms-are-declared.py": "problems",
    "check-session-windows.py": "problems",
    "check-guest-env-allowlist.py": "problems",
    # Added once the registry itself was measured against scripts/: these three
    # carried a --self-test and CI ran it, which proved the self-tests exist.
    # Nothing proved they would notice. Probed before registering -- stubbing
    # scan(), violations() and bindings() reds each one -- so this records a
    # measured property rather than assuming it.
    "check-action-pin-consistency.py": "scan",
    "check-audit-fanin-inv1.py": "violations",
    "check-ocsf-class-identity.py": "bindings",
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


def _registry_covers(root: pathlib.Path) -> list[str]:
    """Checkers in scripts/ that SUBJECTS does not name. Split out so the
    self-test can drive it on a constructed tree rather than only on this
    repository, where it is empty by construction once the registry is right."""
    return sorted(
        p.name
        for p in (root / "scripts").glob("check-*.py")
        if p.name != pathlib.Path(__file__).name and p.name not in SUBJECTS
    )


def _self_tests_ci_never_runs(root: pathlib.Path) -> list[str]:
    """Checkers carrying a --self-test that no workflow invokes.

    This gate proves each self-test would NOTICE a broken checker. It does not
    run them. Measured when this was written: two --self-tests --
    check-audit-fanin-inv1 and check-contract-refs-are-local -- were invoked by
    their live run only, so CI proved they pass on a correct tree and never that
    they fail on a broken one. A red-probe nobody executes is a red-probe on
    paper.
    """
    workflows = root / ".github" / "workflows"
    if not workflows.is_dir():
        return []
    text = " ".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in list(workflows.glob("*.yml")) + list(workflows.glob("*.yaml"))
    )
    # Executable lines only. Matching the whole file counted a COMMENTED-OUT
    # invocation as a live one: measured by prefixing the real
    # `run: python3 scripts/check-pin-policy.py --self-test` with `#`, after
    # which this still exited 0. A gate whose subject is "does CI run this"
    # must not accept the text of a step somebody disabled.
    live = [
        line
        for line in text.splitlines()
        if not line.lstrip().startswith("#")
    ]
    return sorted(
        p.name
        for p in (root / "scripts").glob("check-*.py")
        if "--self-test" in p.read_text(encoding="utf-8", errors="ignore")
        and not any(f"{p.name} --self-test" in line for line in live)
    )


def _self_test() -> int:
    failures = 0

    # _registry_covers() on a constructed tree. Without this the completeness
    # branch is untested: on this repository it returns empty once the registry
    # is correct, so a stub of it would pass unnoticed.
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)
        (base / "scripts").mkdir()
        (base / "scripts" / next(iter(SUBJECTS))).write_text("x", encoding="utf-8")
        if _registry_covers(base):
            failures += 1
            sys.stderr.write("self-test FAIL: a registered checker was reported as uncovered\n")
        else:
            print("  ok: a registered checker is not reported")
        (base / "scripts" / "check-not-in-the-registry.py").write_text("x", encoding="utf-8")
        if not _registry_covers(base):
            failures += 1
            sys.stderr.write("self-test FAIL: an unregistered checker was not reported\n")
        else:
            print("  ok: a checker missing from the registry is reported")

        # _self_tests_ci_never_runs() on the same constructed tree. On this
        # repository it returns empty once every step exists, so a stub of it
        # would pass here unnoticed.
        (base / ".github" / "workflows").mkdir(parents=True)
        (base / "scripts" / "check-probe.py").write_text("--self-test\n", encoding="utf-8")
        (base / ".github" / "workflows" / "w.yml").write_text("run: nothing\n", encoding="utf-8")
        if "check-probe.py" not in _self_tests_ci_never_runs(base):
            failures += 1
            sys.stderr.write("self-test FAIL: a --self-test no workflow runs was not reported\n")
        else:
            print("  ok: a --self-test CI never invokes is reported")
        (base / ".github" / "workflows" / "w.yml").write_text(
            "run: python3 scripts/check-probe.py --self-test\n", encoding="utf-8"
        )
        if "check-probe.py" in _self_tests_ci_never_runs(base):
            failures += 1
            sys.stderr.write("self-test FAIL: an invoked --self-test was still reported\n")
        else:
            print("  ok: a --self-test a workflow invokes is accepted")

        # A commented-out step is not an invocation. Matching the whole file
        # counted one, so disabling a red-probe left this gate green.
        (base / ".github" / "workflows" / "w.yml").write_text(
            "  # run: python3 scripts/check-probe.py --self-test\n", encoding="utf-8"
        )
        if "check-probe.py" not in _self_tests_ci_never_runs(base):
            failures += 1
            sys.stderr.write("self-test FAIL: a commented-out invocation counted as live\n")
        else:
            print("  ok: a commented-out --self-test does not count as invoked")

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

    # The registry must cover scripts/, or this gate answers only for whatever
    # somebody remembered to add. Measured when this was written: 13 checkers
    # present, 9 registered -- three of the four unregistered ones turned out to
    # be bound anyway, which is the point. Nobody knew.
    unregistered = _registry_covers(root)
    if unregistered:
        for name in unregistered:
            print(
                f"::error::{name} is a checker in scripts/ that this gate does not "
                "cover. Register it with the function whose emptiness means "
                "'found nothing', or the claim that every checker is bound is "
                "true only of the ones listed.",
                file=sys.stderr,
            )
        return 1

    unrun = _self_tests_ci_never_runs(root)
    if unrun:
        for name in unrun:
            print(
                f"::error::{name} carries a --self-test that no workflow runs. Its "
                "live invocation proves it passes on a correct tree, never that it "
                "fails on a broken one -- add a step invoking it.",
                file=sys.stderr,
            )
        return 1

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
