#!/usr/bin/env python3
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
#
# NFR-SEC-75: the guest environment is built from an allowlist, and no secret
# reaches argv.
#
# The requirement has two halves and they pull in opposite directions, which is
# why a naive check gets it backwards. It FORBIDS inheriting the host
# environment ("inherit-none default", strip anything matching *_TOKEN /
# *_SECRET / *_PASSWORD / API_KEY at fork). It EXPLICITLY PERMITS handing a
# secret to a tool through the environment: "a secret that must reach a tool is
# passed via the environment or a file descriptor, never on argv".
#
# So ANTHROPIC_AUTH_TOKEN appearing in the guest env dict is compliant, and a
# check that flagged it would report a violation the canon licenses. What is
# not compliant is `os.environ` or `os.environ.copy()` flowing into that dict,
# because that is inheritance -- the shape the requirement names -- and a
# secret name appearing in a command string, because argv is world-readable
# through /proc/<pid>/cmdline to any same-namespace process.
#
# Measured when this was written: _build_container_env starts from a literal
# dict of one key and updates it from an explicit extra_env; nothing reads
# os.environ into it, and no command string carries a secret name.

import ast
import re
import sys
from pathlib import Path

RUNTIME = Path("computer-use-server/docker_manager.py")
BUILDER = "_build_container_env"
# Names the requirement's deny-pattern set describes.
SECRET_NAME = re.compile(r"\b[A-Z][A-Z0-9_]*(?:_TOKEN|_SECRET|_PASSWORD|_KEY)\b|\bAPI_KEY\b")


def inherits_environment(source: str) -> list[str]:
    """Reads of os.environ inside the guest-env builder.

    Parsed rather than grepped: `os.environ` appears elsewhere in this module
    for host-side configuration, which is not what the requirement forbids.
    Only inheritance INTO the guest environment counts.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ["<unparseable: the builder could not be read>"]
    findings: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef) and node.name == BUILDER):
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Attribute) and inner.attr == "environ":
                findings.append(f"{BUILDER} reads os.environ at line {inner.lineno}")
            if isinstance(inner, ast.Name) and inner.id == "environ":
                findings.append(f"{BUILDER} reads environ at line {inner.lineno}")
    return findings


def secrets_on_argv(source: str) -> list[str]:
    """Command strings that name a secret-bearing variable.

    A command is assembled as a string and handed to `bash -c`, so anything
    interpolated there lands in argv. The requirement singles this out because
    /proc/<pid>/cmdline is readable by any process in the same namespace.
    """
    findings = []
    for number, line in enumerate(source.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if not re.search(r"command\s*=|cmd\s*=|bash -c", stripped):
            continue
        match = SECRET_NAME.search(stripped)
        if match:
            # The NAME, not the value -- but a checker that prints
            # ANTHROPIC_AUTH_TOKEN into a log is indistinguishable from one
            # leaking a secret, both to CodeQL (py/clear-text-logging-sensitive-
            # data, raised on this very line) and to a reader scanning CI
            # output. The file and line locate it exactly; the operator opens
            # the file. Reporting the position keeps the finding actionable
            # without putting a secret-shaped string in a log at all.
            findings.append(
                f"line {number}: a secret-bearing variable name appears in a "
                f"command string (see {RUNTIME}:{number})"
            )
    return findings


def problems(source: str) -> list[str]:
    """Both halves. Empty means the guest env is allowlist-built and argv clean."""
    return inherits_environment(source) + secrets_on_argv(source)


def self_test() -> int:
    allowlist = (
        "import os\n"
        "def _build_container_env(extra_env=None):\n"
        "    env = {'NPM_CONFIG_PREFIX': '/x'}\n"
        "    if extra_env:\n        env.update(extra_env)\n"
        "    return env\n"
    )
    cases = [
        (allowlist, 0, "a literal dict plus explicit extra_env passes"),
        (
            allowlist.replace("env = {'NPM_CONFIG_PREFIX': '/x'}", "env = dict(os.environ)"),
            1,
            "inheriting os.environ into the builder is refused",
        ),
        (
            allowlist + "\ndef spawn():\n    command = f\"bash -c 'echo {ANTHROPIC_AUTH_TOKEN}'\"\n",
            1,
            "a secret name in a command string is refused",
        ),
        (
            allowlist + "\nHOST = os.environ.get('PUBLIC_BASE_URL')\n",
            0,
            "os.environ outside the builder is host config, not inheritance",
        ),
        (
            allowlist + "\ndef spawn():\n    command = \"bash -c 'ls /home'\"\n",
            0,
            "a command with no secret name passes",
        ),
    ]
    bad = 0
    for source, want, label in cases:
        got = 1 if problems(source) else 0
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
    path = root / RUNTIME
    if not path.is_file():
        sys.stderr.write(f"::error::{RUNTIME} is missing -- the check cannot judge\n")
        return 2
    source = path.read_text(encoding="utf-8")
    if f"def {BUILDER}(" not in source:
        sys.stderr.write(
            f"::error::{RUNTIME} no longer defines {BUILDER} -- the guest environment "
            "is built somewhere this check does not look\n"
        )
        return 1
    found = problems(source)
    for item in found:
        sys.stderr.write(f"::error::NFR-SEC-75: {item}\n")
    if found:
        return 1
    print(
        f"NFR-SEC-75: {BUILDER} inherits nothing from os.environ, and no command "
        f"string in {RUNTIME.name} names a secret-bearing variable"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
