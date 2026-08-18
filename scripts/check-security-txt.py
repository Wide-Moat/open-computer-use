#!/usr/bin/env python3
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
#
# NFR-COMP-19: the vulnerability-disclosure record is machine-readable and not
# expired.
#
# SECURITY.md already carried the contact, in prose. A scanner looking for
# /.well-known/security.txt found nothing, so the requirement was answered for
# a human reader and not for the tool the RFC exists to serve.
#
# The interesting field is Expires. RFC 9116 makes it mandatory precisely
# because a stale record is worse than none -- it publishes a channel nobody
# watches. A file with a date in the past satisfies "the file exists" and fails
# the requirement, which is why this checks the value rather than the presence.

import datetime
import re
import sys
from pathlib import Path

RECORD = Path(".well-known/security.txt")
REQUIRED_FIELDS = ("Contact", "Expires", "Canonical", "Policy")
FIELD = re.compile(r"^([A-Za-z-]+):\s*(\S.*)$")


def fields(text: str) -> dict[str, str]:
    """Parse the record. Comment lines are not fields -- the RFC uses `#`."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        match = FIELD.match(line.strip())
        if match:
            out.setdefault(match.group(1), match.group(2).strip())
    return out


def problems(text: str, today: datetime.date) -> list[str]:
    """Reasons to refuse. Empty means the record answers NFR-COMP-19."""
    found = fields(text)
    out = [f"missing required field {name}" for name in REQUIRED_FIELDS if name not in found]
    raw = found.get("Expires")
    if raw:
        try:
            expires = datetime.datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except ValueError:
            out.append(f"Expires is not an ISO 8601 timestamp: {raw!r}")
        else:
            if expires <= today:
                out.append(
                    f"Expires {expires} is in the past -- the record publishes a "
                    f"channel nobody has promised to watch"
                )
    return out


def self_test() -> int:
    today = datetime.date(2026, 1, 1)
    live = (
        "Contact: https://x/report\nExpires: 2027-01-01T00:00:00.000Z\n"
        "Canonical: https://x/security.txt\nPolicy: https://x/SECURITY.md\n"
    )
    cases = [
        (live, 0, "a complete, unexpired record passes"),
        (live.replace("2027", "2025"), 1, "an expired record is refused"),
        (live.replace("Contact: https://x/report\n", ""), 1, "a missing Contact is refused"),
        (live.replace("Expires: 2027-01-01T00:00:00.000Z", "Expires: soon"), 1,
         "an unparseable Expires is refused"),
        ("# Contact: https://x/report\n" + live.replace("Contact: https://x/report\n", ""), 1,
         "a field commented out does not count"),
    ]
    bad = 0
    for text, want, label in cases:
        got = 1 if problems(text, today) else 0
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
    root = Path(argv[0]) if argv else Path(".")
    path = root / RECORD
    if not path.is_file():
        sys.stderr.write(
            f"::error::{RECORD} is missing. NFR-COMP-19 asks for a machine-readable "
            "disclosure record; SECURITY.md answers a human reader only.\n"
        )
        return 1
    found = problems(path.read_text(encoding="utf-8"), datetime.date.today())
    for problem in found:
        sys.stderr.write(f"::error::{RECORD}: {problem}\n")
    if found:
        return 1
    print(f"NFR-COMP-19: {RECORD} carries all {len(REQUIRED_FIELDS)} required fields and has not expired")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
