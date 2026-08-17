#!/usr/bin/env python3
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""NFR-FLEX-01: OCU's own code imports no upstream-vendor SDK.

The row asks for endpoints reachable by configuration alone, and states the
check as "zero upstream-vendor SDK imported in CI scan". The reason is in the
row's own tail: provider selection and the agent loop are the CALLING CLIENT's
concern, not OCU's. An SDK compiled into OCU makes a provider a code change.

Measured when this was written: zero vendor imports across the four directories
that hold OCU's own Python. The invariant already holds; nothing was holding it.

What is IN scope, and why the boundary sits there:

  - `computer-use-server`, `openwebui`, `settings-wrapper`, `scripts` -- OCU's
    own code. An import here compiles a provider in.
  - `skills/` is OUT. A skill is an artifact the caller supplies and runs in the
    sandbox; `skills/examples/mcp-builder` imports `anthropic` today, and that
    is a client-side example doing exactly what the NFR says is the client's
    business.
  - `tests/` is OUT for the same reason a test may import what it exercises.
  - requirements files are OUT: `openai` is DECLARED in requirements.txt and
    imported nowhere. A declared-but-unimported dependency is a packaging
    question, not a compiled-in provider -- the NFR says "imported".

An import is matched at statement level (`import X` / `from X import`), not as
a substring: a comment or a string mentioning a vendor is not an import, and a
gate that cannot tell them apart reports defects that are not there.

    check-no-vendor-sdk.py [--root .] [--self-test]
"""

from __future__ import annotations

import argparse
import ast
import pathlib
import sys

# Directories holding OCU's own code. Not a denylist of everything -- see the
# docstring for what is deliberately outside.
OCU_DIRS = ("computer-use-server", "openwebui", "settings-wrapper", "scripts")

# Upstream providers whose SDK would make provider choice a code change.
VENDOR_ROOTS = {
    "openai",
    "anthropic",
    "cohere",
    "mistralai",
    "google.generativeai",
    "vertexai",
    "boto3",
    "botocore",
    "azure",
}


def _root(name: str) -> str:
    """The importable root a dotted module belongs to, longest match first."""
    for vendor in sorted(VENDOR_ROOTS, key=len, reverse=True):
        if name == vendor or name.startswith(vendor + "."):
            return vendor
    return ""


def vendor_imports(source: str) -> list[tuple[int, str]]:
    """(line, vendor) for every vendor SDK imported by this module.

    Parsed, not grepped. `# import openai` and `"from anthropic import"` are
    text, and a check that flags them would fail on its own documentation --
    this file names all nine vendors in a comment above.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                vendor = _root(alias.name)
                if vendor:
                    found.append((node.lineno, vendor))
        elif isinstance(node, ast.ImportFrom):
            # A relative import has no upstream module to be.
            if node.level:
                continue
            vendor = _root(node.module or "")
            if vendor:
                found.append((node.lineno, vendor))
    return found


def scan(root: pathlib.Path) -> tuple[dict[str, list[tuple[int, str]]], int]:
    findings: dict[str, list[tuple[int, str]]] = {}
    scanned = 0
    for directory in OCU_DIRS:
        base = root / directory
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            scanned += 1
            hits = vendor_imports(path.read_text(encoding="utf-8", errors="ignore"))
            if hits:
                findings[str(path.relative_to(root))] = hits
    return findings, scanned


def _self_test() -> int:
    cases = [
        ("a plain import is caught", "import openai\n", 1),
        ("a from-import is caught", "from anthropic import Anthropic\n", 1),
        ("a submodule is caught", "import google.generativeai as genai\n", 1),
        ("an aliased import is caught", "import boto3 as aws\n", 1),
        # The two that make a text-matching gate useless: this file's own
        # docstring names every vendor, and so does the comment above the set.
        ("a comment is not an import", "# import openai\n", 0),
        ("a string is not an import", 'x = "from anthropic import Anthropic"\n', 0),
        ("a relative import is not a vendor", "from .anthropic import thing\n", 0),
        # A local module whose name merely begins with a vendor's.
        ("a same-prefix local module is not a vendor", "import openaiwrapper\n", 0),
        ("unrelated imports pass", "import json\nfrom pathlib import Path\n", 0),
        ("unparseable source yields nothing rather than crashing", "def (\n", 0),
    ]
    failures = 0
    for name, source, want in cases:
        got = len(vendor_imports(source))
        ok = got == want
        failures += 0 if ok else 1
        print(f"  {'ok' if ok else 'FAIL'}: {name} ({got})")
    print()
    if failures:
        print(f"self-test: {failures} case(s) failed")
        return 1
    print("self-test: an import in any shape reds; prose naming a vendor does not.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()

    root = pathlib.Path(args.root).resolve()
    findings, scanned = scan(root)
    if scanned == 0:
        print("::error::no OCU Python found -- the scan covered nothing", file=sys.stderr)
        return 2

    if findings:
        for path, hits in findings.items():
            for line, vendor in hits:
                print(
                    f"::error file={path},line={line}::{vendor} is imported by OCU's "
                    "own code. NFR-FLEX-01: provider selection belongs to the calling "
                    "client; an SDK here makes a provider a code change.",
                    file=sys.stderr,
                )
        return 1

    print(
        f"NFR-FLEX-01 (import half): {scanned} OCU Python file(s) import no "
        "upstream-vendor SDK."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
