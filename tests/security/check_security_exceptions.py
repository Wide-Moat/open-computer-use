#!/usr/bin/env python3
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""Enforce the HIGH-finding exception ledger instead of describing it.

`.github/security-exceptions.yml` carried a schema with a `since`, an
`expires`, an owner and a remediation, and a note saying CI did not enforce any
of it. An exception file nothing reads is not a control. It is a place to write
down that a finding was ignored, with the shape of rigour and none of it, and
its entries outlive their reasons because nothing ever asks whether they are
still needed.

The same standard this repository has been asking of sibling repositories:
a finding closable by the change in flight is fixed; a finding needing separate
work is named with the condition for its own removal; neither is switched off.
An exception must be able to kill itself.

What is refused:

  - an entry past its `expires` date, which is the whole point
  - `expires` more than 14 days after `since`, the window CLAUDE.md sets
  - severity CRITICAL, which is never excepted whatever the file says
  - a missing or malformed field, rather than skipping the entry in silence --
    a lenient reader's quiet is indistinguishable from a working one's

Every admitted exception prints on every run. A silent exception reads exactly
like no exception at all.

An empty ledger is the target state, not a stub.

Usage:
  check_security_exceptions.py [--file PATH] [--today YYYY-MM-DD]
  check_security_exceptions.py --self-test

Exit 0 when every entry is well-formed and live, 1 on a violation, 2 on a
usage or environment error.
"""

import argparse
import datetime as dt
import os
import sys

try:
    import yaml
except ImportError:
    print("PyYAML is required: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

MAX_WINDOW_DAYS = 14
REQUIRED = ("id", "severity", "tool", "since", "expires", "owner", "reason", "remediation")
TOOLS = ("trivy", "semgrep", "checkov", "trufflehog", "gitleaks")


def _date(value, field, where, problems):
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        problems.append(f"{where}: `{field}` is {value!r}, not a YYYY-MM-DD date")
        return None


def analyse(doc, today):
    """doc: parsed ledger. Returns (violations, admitted) -- admitted is printed."""
    violations, admitted = [], []

    if doc is None:
        return ["the ledger is empty as a file; it must contain `exceptions: []`"], []
    if not isinstance(doc, dict) or "exceptions" not in doc:
        return ["the ledger has no `exceptions:` key"], []

    entries = doc["exceptions"]
    if entries is None:
        entries = []
    if not isinstance(entries, list):
        return [f"`exceptions:` is {type(entries).__name__}, not a list"], []

    for i, e in enumerate(entries):
        where = f"entry {i + 1}"
        if not isinstance(e, dict):
            violations.append(
                f"{where} is {type(e).__name__}, not a mapping, so nothing about it can be "
                f"checked. Refusing to pass over an entry that was never examined.")
            continue

        missing = [f for f in REQUIRED if f not in e or e[f] in (None, "")]
        if missing:
            violations.append(f"{where} ({e.get('id', 'no id')}) is missing {missing}")
            continue

        where = f"entry {i + 1} ({e['id']})"

        if str(e["severity"]).upper() == "CRITICAL":
            violations.append(
                f"{where}: CRITICAL is never excepted. CI fails regardless of this file.")
            continue
        if str(e["severity"]).upper() != "HIGH":
            violations.append(f"{where}: severity is {e['severity']!r}, only HIGH may be excepted")
            continue
        if str(e["tool"]) not in TOOLS:
            violations.append(f"{where}: tool {e['tool']!r} is not one of {list(TOOLS)}")
            continue

        since = _date(e["since"], "since", where, violations)
        expires = _date(e["expires"], "expires", where, violations)
        if since is None or expires is None:
            continue

        if expires < since:
            violations.append(f"{where}: expires {expires} is before since {since}")
            continue
        if (expires - since).days > MAX_WINDOW_DAYS:
            violations.append(
                f"{where}: the window is {(expires - since).days} days, "
                f"more than the {MAX_WINDOW_DAYS} allowed")
            continue
        if today > expires:
            violations.append(
                f"{where}: expired on {expires}, {(today - expires).days} day(s) ago. "
                f"Fix the finding or renew the entry with a fresh justification -- an "
                f"exception that outlives its date is a silent suppression.")
            continue

        admitted.append(
            f"ADMITTED {e['id']} ({e['tool']}, HIGH) until {expires}, owner {e['owner']}: "
            f"{e['reason']} / remediation: {e['remediation']}")

    return violations, admitted


SELF_TESTS = [
    ("an empty ledger is the target state", 0, {"exceptions": []}, "2026-07-31"),
    ("a live entry inside the window is admitted", 0, {"exceptions": [{
        "id": "CVE-2026-1", "severity": "HIGH", "tool": "trivy",
        "since": "2026-07-28", "expires": "2026-08-04", "owner": "@x",
        "reason": "r", "remediation": "m"}]}, "2026-07-31"),
    ("an expired entry is refused", 1, {"exceptions": [{
        "id": "CVE-2026-2", "severity": "HIGH", "tool": "trivy",
        "since": "2026-07-01", "expires": "2026-07-15", "owner": "@x",
        "reason": "r", "remediation": "m"}]}, "2026-07-31"),
    ("a window longer than 14 days is refused", 1, {"exceptions": [{
        "id": "CVE-2026-3", "severity": "HIGH", "tool": "trivy",
        "since": "2026-07-01", "expires": "2026-08-30", "owner": "@x",
        "reason": "r", "remediation": "m"}]}, "2026-07-31"),
    ("CRITICAL is never excepted", 1, {"exceptions": [{
        "id": "CVE-2026-4", "severity": "CRITICAL", "tool": "trivy",
        "since": "2026-07-30", "expires": "2026-08-02", "owner": "@x",
        "reason": "r", "remediation": "m"}]}, "2026-07-31"),
    ("a missing field is refused, not skipped", 1, {"exceptions": [{
        "id": "CVE-2026-5", "severity": "HIGH", "tool": "trivy",
        "since": "2026-07-30", "expires": "2026-08-02"}]}, "2026-07-31"),
    ("an entry that is not a mapping is refused, not skipped", 1,
     {"exceptions": ["CVE-2026-6"]}, "2026-07-31"),
    ("an unparseable date is refused", 1, {"exceptions": [{
        "id": "CVE-2026-7", "severity": "HIGH", "tool": "trivy",
        "since": "yesterday", "expires": "2026-08-02", "owner": "@x",
        "reason": "r", "remediation": "m"}]}, "2026-07-31"),
    ("a tool nobody runs is refused", 1, {"exceptions": [{
        "id": "CVE-2026-8", "severity": "HIGH", "tool": "astrology",
        "since": "2026-07-30", "expires": "2026-08-02", "owner": "@x",
        "reason": "r", "remediation": "m"}]}, "2026-07-31"),
    ("a ledger with no exceptions key is refused", 1, {"entries": []}, "2026-07-31"),
]


def self_test():
    failed = 0
    for label, expected, doc, today in SELF_TESTS:
        violations, _ = analyse(doc, dt.date.fromisoformat(today))
        got = 1 if violations else 0
        if got != expected:
            failed += 1
            print(f"SELF-TEST FAILED: {label} -- expected "
                  f"{'a violation' if expected else 'none'}, got {violations or 'none'}")
        else:
            print(f"ok   self-test: {label}")
    if failed:
        print(f"\n{failed} self-test(s) failed; the check cannot be trusted on the real ledger")
        return 1
    print("\nself-test: every malformed, expired and over-window entry is refused, "
          "and a live one is admitted")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=".github/security-exceptions.yml")
    ap.add_argument("--today", default=None, help="override today, for testing")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    if not os.path.isfile(args.file):
        print(f"no such file: {args.file}", file=sys.stderr)
        return 2
    try:
        with open(args.file) as fh:
            doc = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        print(f"{args.file}: not parseable as YAML: {exc}", file=sys.stderr)
        return 2

    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    violations, admitted = analyse(doc, today)

    for a in admitted:
        print(a)
    for v in violations:
        print(f"FAIL {args.file}: {v}")

    total = len(admitted) + len(violations)
    print(f"\nexception ledger: {total} entr(ies), {len(admitted)} admitted, "
          f"{len(violations)} refused, as of {today}")
    if not total:
        print("the ledger is empty, which is its target state")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
