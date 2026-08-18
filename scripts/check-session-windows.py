#!/usr/bin/env python3
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
#
# NFR-SEC-40: the shipped idle window is inside the bound the requirement sets.
#
# The row asks for an idle window <= 15 min and says the operator may tune it
# "customer-tunable-DOWN" -- so the number that must satisfy the bound is the
# DEFAULT this repository ships, not whatever an environment supplies at run
# time. That distinction is the whole check: measured before writing it,
# CONTAINER_IDLE_TIMEOUT=3600 yields a 60-minute window, and nothing refuses
# it. Bounding the env var would argue with canon; bounding the default is what
# canon actually fixes.
#
# Two defaults ship and they must agree. computer-use-server/docker_manager.py
# carries the code default and helm/computer-use-server/values.yaml the chart
# one; a drift between them means the container and the chart disagree about a
# security window, which no schema check would notice.

import re
import sys
from pathlib import Path

CODE = Path("computer-use-server/docker_manager.py")
CHART = Path("helm/computer-use-server/values.yaml")
IDLE_MAX_SECONDS = 15 * 60

CODE_DEFAULT = re.compile(
    r'^CONTAINER_IDLE_TIMEOUT\s*=\s*int\(\s*os\.getenv\(\s*"CONTAINER_IDLE_TIMEOUT"\s*,\s*"(\d+)"',
    re.M,
)
CHART_DEFAULT = re.compile(r'^\s*CONTAINER_IDLE_TIMEOUT:\s*"?(\d+)"?\s*$', re.M)


def defaults(code_text: str, chart_text: str) -> dict[str, int | None]:
    """The idle window each shipped default declares, or None when absent."""
    code = CODE_DEFAULT.search(code_text)
    chart = CHART_DEFAULT.search(chart_text)
    return {
        "code": int(code.group(1)) if code else None,
        "chart": int(chart.group(1)) if chart else None,
    }


def problems(found: dict[str, int | None], bound: int = IDLE_MAX_SECONDS) -> list[str]:
    """Reasons to refuse. Empty means both defaults sit inside the bound."""
    out = []
    for where, value in sorted(found.items()):
        if value is None:
            out.append(f"{where}: no CONTAINER_IDLE_TIMEOUT default found")
        elif value > bound:
            out.append(
                f"{where}: default {value}s exceeds the NFR-SEC-40 bound of {bound}s"
            )
    values = {v for v in found.values() if v is not None}
    if len(values) > 1:
        out.append(
            f"the shipped defaults disagree: {sorted(values)} -- the container and "
            f"the chart would apply different security windows"
        )
    return out


def self_test() -> int:
    cases = [
        ({"code": 600, "chart": 600}, 0, "matching defaults inside the bound pass"),
        ({"code": 900, "chart": 900}, 0, "exactly at the bound passes"),
        ({"code": 901, "chart": 901}, 1, "one second over is refused"),
        ({"code": 600, "chart": 300}, 1, "defaults that disagree are refused"),
        ({"code": None, "chart": 600}, 1, "a missing code default is refused"),
        ({"code": 600, "chart": None}, 1, "a missing chart default is refused"),
    ]
    bad = 0
    for found, want, label in cases:
        got = 1 if problems(found) else 0
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
    for path in (CODE, CHART):
        if not (root / path).is_file():
            sys.stderr.write(f"::error::{path} is missing -- the check cannot judge\n")
            return 2
    found = defaults(
        (root / CODE).read_text(encoding="utf-8"),
        (root / CHART).read_text(encoding="utf-8"),
    )
    issues = problems(found)
    for issue in issues:
        sys.stderr.write(f"::error::NFR-SEC-40: {issue}\n")
    if issues:
        return 1
    print(
        f"NFR-SEC-40: the shipped idle window is {found['code']}s in code and "
        f"{found['chart']}s in the chart, both within {IDLE_MAX_SECONDS}s"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
