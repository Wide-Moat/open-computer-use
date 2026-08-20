#!/usr/bin/env python3
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
#
# An arm must be declared, not acquired by mentioning an id.
#
# check-nfr-coverage.py attributes an arm to any file under scripts/, .github/
# or tests/ that NAMES an NFR id. That is the right rule for finding assertions
# -- a check has to name what it checks -- but it is silent about the inverse:
# writing an id into a comment arms it, with no assertion behind the name.
#
# It happened. A checker header cited a second requirement alongside the one it
# holds, purely as context, and coverage jumped by two. The number was noticed
# only because the expected rise was one; a wider gap, or a less attentive
# reading, and the ledger would have carried a requirement nothing checks.
#
# So this gate holds a ledger. Every armed id is listed here with the checker
# that answers for it, and the gate refuses three ways:
#
#   - an id counted as armed but absent from the ledger (a mention acquired it)
#   - an id in the ledger no longer counted (its assertion left the tree)
#   - a ledger entry naming a checker that does not exist
#
# The ledger is written by hand on purpose. Deriving it from the scan would make
# it agree with whatever the scan found, which is exactly the failure it exists
# to catch. Adding a row here is the step where somebody states, deliberately,
# that a check now answers for a requirement.

import importlib.util
import pathlib
import sys

COVERAGE = pathlib.Path("scripts/check-nfr-coverage.py")

# id -> the file carrying the assertion. Where an id is named by several files
# (a workflow step plus its script), the SCRIPT is named: it is the thing that
# would have to change for the assertion to stop holding.
LEDGER: dict[str, str] = {
    "NFR-COMP-17": "scripts/check-compliance-front-matter.py",
    "NFR-COMP-19": "scripts/check-compliance-front-matter.py",
    "NFR-COMP-22": ".github/workflows/gate3-rehearsal.yml",
    "NFR-COMP-27": "scripts/check-soar-revoke-frozen.py",
    "NFR-FLEX-01": "scripts/check-no-vendor-sdk.py",
    "NFR-FLEX-07b": "scripts/check-one-click-compose.py",
    "NFR-FLEX-13": "scripts/check-contract-refs-are-local.py",
    "NFR-FLEX-14": "scripts/check-mcp-protocol-version.py",
    "NFR-IC-02": "scripts/check-no-mutating-console.py",
    "NFR-MAINT-05": "scripts/check-release-synthetic.py",
    "NFR-MAINT-AUDIT-SCHEMA": "scripts/check-audit-fanin-inv1.py",
    "NFR-SEC-07": "scripts/check-schemas-are-closed.py",
    "NFR-SEC-15": "tests/test-docker-image.sh",
    "NFR-SEC-16": "scripts/check-no-phone-home.py",
    "NFR-SEC-18": "scripts/check-pin-policy.py",
    "NFR-SEC-19": "scripts/check-pin-policy.py",
    "NFR-SEC-26": "scripts/check-operator-bodies-hint-only.py",
    "NFR-SEC-38": "scripts/check-admission-matrix-complete.py",
    "NFR-SEC-40": "scripts/check-session-windows.py",
    "NFR-SEC-51": "scripts/check-schemas-are-closed.py",
    "NFR-SEC-75": "scripts/check-guest-env-allowlist.py",
    "NFR-SEC-79": "scripts/check-file-activity-overlay.py",
    "NFR-SEC-81": "scripts/check-upload-content-sniffing.py",
    "NFR-SEC-82": "scripts/check-browser-storage-clean.py",
    "NFR-SEC-87": "scripts/check-schemas-are-closed.py",
    "NFR-SEC-88": "scripts/check-ocsf-class-identity.py",
    "NFR-SEC-89": "scripts/check-gates-are-required.py",
}


def _coverage_module(root: pathlib.Path):
    """Import the coverage checker so both read one definition of 'armed'."""
    path = root / COVERAGE
    spec = importlib.util.spec_from_file_location("coverage_check", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def counted_arms(root: pathlib.Path) -> set[str] | None:
    """Ids the coverage scanner counts as armed, or None when it cannot run."""
    module = _coverage_module(root)
    if module is None:
        return None
    return set(module.armed_ids(root, module.declared_ids(root)))


def problems(counted: set[str], ledger: dict[str, str], root: pathlib.Path) -> list[str]:
    """Reasons to refuse. Empty means the ledger and the scan agree."""
    out = []
    for identifier in sorted(counted - set(ledger)):
        out.append(
            f"{identifier} counts as armed but is not in the ledger -- if a comment "
            f"acquired it, remove the mention; if a check now answers for it, add "
            f"the row deliberately"
        )
    for identifier in sorted(set(ledger) - counted):
        out.append(
            f"{identifier} is in the ledger but no longer counts as armed -- its "
            f"assertion left the tree"
        )
    for identifier, holder in sorted(ledger.items()):
        if not (root / holder).is_file():
            out.append(f"{identifier} names {holder}, which does not exist")
    return out


def self_test() -> int:
    here = pathlib.Path(".")
    ledger = {"NFR-A-1": "scripts/check-nfr-coverage.py"}
    cases = [
        (({"NFR-A-1"}, ledger), 0, "ledger and scan agreeing pass"),
        (({"NFR-A-1", "NFR-B-2"}, ledger), 1, "an id armed by a mention is refused"),
        ((set(), ledger), 1, "a ledger entry that stopped being armed is refused"),
        (({"NFR-A-1"}, {"NFR-A-1": "scripts/does-not-exist.py"}), 1, "a missing holder is refused"),
    ]
    bad = 0
    for (counted, entries), want, label in cases:
        got = 1 if problems(counted, entries, here) else 0
        ok = got == want
        bad += 0 if ok else 1
        print(f"  {'ok' if ok else 'FAIL'}: {label}")
    if bad:
        print(f"self-test: {bad} case(s) failed")
        return 1
    print(f"self-test ok: {len(cases)} cases")
    return 0


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--self-test":
        return self_test()
    root = pathlib.Path(argv[0]) if argv else pathlib.Path(".")
    if not (root / COVERAGE).is_file():
        sys.stderr.write(f"::error::{COVERAGE} is missing -- the ledger cannot be compared\n")
        return 2
    counted = counted_arms(root)
    if counted is None:
        sys.stderr.write(
            f"::error::{COVERAGE} could not be imported -- refusing rather than "
            f"reporting agreement this run never established\n"
        )
        return 2
    if not counted:
        sys.stderr.write(
            f"::error::the coverage scan counted zero arms -- the ledger would "
            f"look wrong for a reason that is not the ledger's\n"
        )
        return 2

    issues = problems(counted, LEDGER, root)
    for issue in issues:
        sys.stderr.write(f"::error::arms-ledger: {issue}\n")
    if issues:
        return 1
    print(f"arms-ledger: {len(LEDGER)} declared arm(s), each counted and each with a holder")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
