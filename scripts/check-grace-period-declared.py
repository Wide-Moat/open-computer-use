#!/usr/bin/env python3
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
#
# NFR-REL-11, the declared-value half: the chart states its shutdown grace
# period rather than inheriting one.
#
# The row's target is `terminationGracePeriodSeconds=30`, SIGTERM->5s->SIGKILL,
# tmpdir clean <= 10 s. Only the first clause is a chart property; the other two
# are server behaviour and are NOT claimed here (see #530 for the measurement of
# all three).
#
# Kubernetes defaults this field to 30, which is the same number, and that
# coincidence is exactly why the check exists. A default is not a decision: it
# can be changed by a cluster policy or a mutating admission webhook without the
# chart noticing, and a rendered manifest that does not carry the number gives
# an auditor nothing to read. Measured when this was written: the field appeared
# nowhere in helm/, so the deployment matched the requirement only by accident.
#
# The check reads the TEMPLATE and the VALUE rather than a rendered manifest,
# because rendering needs required values supplied on the command line
# (PUBLIC_BASE_URL and an mcpApiKey, per the chart's own schema) and a lint that
# has to be handed secrets to run is a lint people skip.

import re
import sys
from pathlib import Path

DEPLOYMENT = Path("helm/computer-use-server/templates/deployment.yaml")
VALUES = Path("helm/computer-use-server/values.yaml")
FIELD = "terminationGracePeriodSeconds"
# The row fixes 30 s. A deployment may not silently drift off it.
REQUIRED = 30


def template_declares(text: str) -> bool:
    """True when the pod spec sets the field from values."""
    return re.search(rf"^\s*{FIELD}:\s*\{{\{{", text, re.M) is not None


def declared_value(text: str) -> int | None:
    """The number values.yaml ships, or None when it is absent."""
    found = re.search(rf"^\s*{FIELD}:\s*(\d+)\s*$", text, re.M)
    return int(found.group(1)) if found else None


def problems(template: str, values: str) -> list[str]:
    """Reasons to refuse. Empty means the number is stated, not inherited."""
    out = []
    if not template_declares(template):
        out.append(
            f"the pod spec does not set {FIELD} -- the deployment would inherit "
            f"the Kubernetes default, which is a coincidence rather than a decision"
        )
    value = declared_value(values)
    if value is None:
        out.append(f"values.yaml ships no {FIELD}, so the template has nothing to render")
    elif value != REQUIRED:
        out.append(
            f"values.yaml ships {FIELD}={value}, and NFR-REL-11 fixes {REQUIRED}"
        )
    return out


def self_test() -> int:
    good_t = "spec:\n      " + FIELD + ": {{ .Values.orchestrator." + FIELD + " }}\n"
    good_v = "orchestrator:\n  " + FIELD + ": 30\n"
    cases = [
        ((good_t, good_v), 0, "template plus a 30 s value passes"),
        (("spec:\n      containers: []\n", good_v), 1, "a template that omits the field is refused"),
        ((good_t, "orchestrator:\n  other: 1\n"), 1, "a missing value is refused"),
        ((good_t, "orchestrator:\n  " + FIELD + ": 5\n"), 1, "a value off the fixed 30 is refused"),
        ((good_t, "orchestrator:\n  " + FIELD + ": 300\n"), 1, "a longer window is refused too"),
        (("spec:\n      " + FIELD + ": 30\n", good_v), 1,
         "a hardcoded template value is refused -- it cannot be tuned per deployment"),
    ]
    bad = 0
    for (template, values), want, label in cases:
        got = 1 if problems(template, values) else 0
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
    for path in (DEPLOYMENT, VALUES):
        if not (root / path).is_file():
            sys.stderr.write(f"::error::{path} is missing -- the check cannot judge\n")
            return 2
    issues = problems(
        (root / DEPLOYMENT).read_text(encoding="utf-8"),
        (root / VALUES).read_text(encoding="utf-8"),
    )
    for issue in issues:
        sys.stderr.write(f"::error::NFR-REL-11: {issue}\n")
    if issues:
        return 1
    print(
        f"NFR-REL-11 (declared-value half): the chart states {FIELD}={REQUIRED} "
        f"rather than inheriting it"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
