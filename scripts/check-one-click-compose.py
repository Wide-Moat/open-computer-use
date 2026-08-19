#!/usr/bin/env python3
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
#
# NFR-FLEX-07b, the Compose half: `docker compose up` still works with no
# configuration.
#
# The row's target is "one-click solo install preserves Compose path", verified
# by a Compose smoke test. The smoke test exists -- build.yml stands the stack
# up from docker-compose.test.yml and drives it -- so what is unguarded is the
# property that makes the install one-click in the first place: every variable
# the compose file interpolates carries a default.
#
# That is the invariant a well-meaning change breaks quietly. Adding
# `${OCU_LICENSE_KEY}` to a service is a one-line edit that leaves every gate
# green, the file valid, and the smoke test passing -- the test supplies its own
# environment. The person it breaks is the solo installer running `docker
# compose up` on a clean checkout, who gets an empty value substituted and a
# failure somewhere downstream.
#
# Measured when this was written: 25 variables interpolated across the file, 25
# of them with a `:-` default, and no `required: true` anywhere. So the property
# holds and this keeps it holding.
#
# The one-click claim is a standing invariant for the solo audience, not a
# nice-to-have, which is why it is worth a gate rather than a comment.

import re
import sys
from pathlib import Path

COMPOSE = Path("docker-compose.yml")

# ${VAR}, ${VAR:-default}, ${VAR-default}. The middle form is the one that keeps
# the install one-click; the bare form is what this refuses.
INTERPOLATION = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)([:-][^}]*)?\}")


def variables(text: str) -> dict[str, bool]:
    """Every interpolated variable -> whether it carries a default."""
    found: dict[str, bool] = {}
    for name, suffix in INTERPOLATION.findall(text):
        has_default = bool(suffix)
        # A variable used twice counts as defaulted only if EVERY use defaults
        # it: one bare use is enough to break a clean checkout.
        found[name] = found.get(name, True) and has_default
    return found


def services(text: str) -> list[str]:
    """Service names, so an empty parse can be told from an empty file."""
    block = re.search(r"^services:\s*$", text, re.M)
    if not block:
        return []
    return re.findall(r"^  ([a-z][a-z0-9_-]*):\s*$", text[block.end() :], re.M)


def problems(found: dict[str, bool], text: str) -> list[str]:
    """Reasons to refuse. Empty means `docker compose up` needs no config."""
    out = []
    for name in sorted(n for n, defaulted in found.items() if not defaulted):
        out.append(
            f"${{{name}}} is interpolated with no default -- a clean checkout "
            f"running `docker compose up` substitutes an empty value"
        )
    for match in re.finditer(r"required:\s*true", text):
        line = text[: match.start()].count("\n") + 1
        out.append(
            f"line {line} marks a variable required -- the one-click path cannot "
            f"demand configuration"
        )
    return out


def self_test() -> int:
    cases = [
        (({"PORT": True, "IMAGE": True}, ""), 0, "every variable defaulted passes"),
        (({"PORT": True, "LICENSE": False}, ""), 1, "a bare interpolation is refused"),
        (({}, "  environment:\n    - X:\n        required: true\n"), 1,
         "a required variable is refused"),
        (({}, ""), 0, "a file interpolating nothing passes"),
    ]
    bad = 0
    for (found, text), want, label in cases:
        got = 1 if problems(found, text) else 0
        ok = got == want
        bad += 0 if ok else 1
        print(f"  {'ok' if ok else 'FAIL'}: {label}")

    # The extractor, on constructed text. On the shipped file every variable is
    # defaulted, so a stub returning {} would pass unnoticed.
    found = variables("a: ${ONE:-x}\nb: ${TWO}\nc: ${ONE:-y}\n")
    if found != {"ONE": True, "TWO": False}:
        bad += 1
        sys.stderr.write(f"self-test FAIL: extractor returned {found}\n")
    else:
        print("  ok: a bare use is extracted and a defaulted one is not")

    # A variable used both ways is NOT safe: the bare use breaks the install.
    mixed = variables("a: ${DUAL:-x}\nb: ${DUAL}\n")
    if mixed != {"DUAL": False}:
        bad += 1
        sys.stderr.write(f"self-test FAIL: mixed use returned {mixed}\n")
    else:
        print("  ok: one bare use outweighs a defaulted one")

    if bad:
        print(f"self-test: {bad} case(s) failed")
        return 1
    print("self-test ok: 6 cases")
    return 0


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--self-test":
        return self_test()
    root = Path(argv[0]) if argv else Path(".")
    path = root / COMPOSE
    if not path.is_file():
        sys.stderr.write(f"::error::{COMPOSE} is missing -- the one-click path is gone\n")
        return 2
    text = path.read_text(encoding="utf-8")
    found = services(text)
    if not found:
        sys.stderr.write(
            f"::error::no service parsed out of {COMPOSE} -- the file shape changed "
            f"and this check would pass without reading the install path\n"
        )
        return 2

    issues = problems(variables(text), text)
    for issue in issues:
        sys.stderr.write(f"::error::NFR-FLEX-07b: {issue}\n")
    if issues:
        return 1
    print(
        f"NFR-FLEX-07b: {len(found)} compose service(s), "
        f"{len(variables(text))} interpolated variable(s), every one defaulted -- "
        f"`docker compose up` needs no configuration"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
