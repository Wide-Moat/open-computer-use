#!/usr/bin/env python3
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
#
# NFR-SEC-81, the local half: the upload path classifies by CONTENT.
#
# The row asks that every uploaded body be classified by magic-byte sniff plus
# declared media type, with a declared/sniffed mismatch recorded. Measured when
# the defect was filed (#561): uploads.py classified with
# `mimetypes.guess_type(path.name)` alone, so renaming an executable to
# payload.exe.png made it image/png -- exercised, not read, because the module
# needs fastapi and would not import.
#
# The fix sniffs a bounded prefix and lets content win, keeping BOTH values so
# the disagreement is visible. This holds that shape.
#
# The check is deliberately about the classifier's inputs rather than its
# output table. Asserting a specific signature list would freeze a table this
# file has no authority over -- the row puts the full classifier in the parser
# sub-component (ADR-0026). What must not regress is the property: the file is
# opened, the bytes decide, and the mismatch is recorded rather than resolved
# away.

import ast
import sys
from pathlib import Path

UPLOADS = Path("computer-use-server/uploads.py")
# The three things the requirement needs and a name-only classifier lacks.
NEEDS_OPEN = "the classifier never opens the file, so it cannot see content"
NEEDS_SNIFF = "no signature table -- nothing maps bytes to a type"
NEEDS_MISMATCH = "the declared/sniffed disagreement is not recorded"


def _functions(tree: ast.AST) -> dict[str, ast.FunctionDef]:
    return {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}


def problems(source: str) -> list[str]:
    """Reasons to refuse. Empty means content decides and mismatch is kept."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f"uploads.py does not parse ({exc})"]

    functions = _functions(tree)
    out = []

    classifier = functions.get("classify")
    if classifier is None:
        return ["no classify() -- the content-sniffing entry point is gone"]

    # It must read bytes. A classifier that only inspects the name is the
    # defect this replaced.
    opens = any(
        isinstance(node, ast.Attribute) and node.attr in ("open", "read_bytes")
        for node in ast.walk(classifier)
    )
    if not opens:
        out.append(NEEDS_OPEN)

    if "sniff_mime" not in functions:
        out.append("no sniff_mime() -- byte inspection has no entry point")
    elif not any(
        isinstance(node, ast.Constant) and isinstance(node.value, bytes)
        for node in ast.walk(tree)
    ):
        out.append(NEEDS_SNIFF)

    # The mismatch must be computed, not just the winner returned.
    compares = any(
        isinstance(node, ast.Compare)
        and any(isinstance(op, ast.NotEq) for op in node.ops)
        for node in ast.walk(classifier)
    )
    if not compares:
        out.append(NEEDS_MISMATCH)

    # And it must survive into the listing, or nothing downstream can see it.
    entry = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "UploadEntry"),
        None,
    )
    if entry is None:
        out.append("UploadEntry is gone -- the listing carries no type at all")
    else:
        fields = {
            node.target.id
            for node in entry.body
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
        }
        for needed in ("declared_mime", "sniffed_mime", "type_mismatch"):
            if needed not in fields:
                out.append(f"UploadEntry has no {needed} -- the mismatch cannot be reported")
    return out


def self_test() -> int:
    good = (
        "import mimetypes\n"
        "from dataclasses import dataclass\n"
        "@dataclass\n"
        "class UploadEntry:\n"
        "    mime_type: str\n    declared_mime: str = ''\n"
        "    sniffed_mime: str = ''\n    type_mismatch: bool = False\n"
        "def sniff_mime(prefix):\n    return 'image/png' if prefix.startswith(b'\\x89PNG') else ''\n"
        "def classify(path):\n"
        "    declared = mimetypes.guess_type(path.name)[0]\n"
        "    with path.open('rb') as h:\n        prefix = h.read(16)\n"
        "    sniffed = sniff_mime(prefix)\n"
        "    return sniffed or declared, declared, sniffed, sniffed != declared\n"
    )
    name_only = (
        "import mimetypes\n"
        "from dataclasses import dataclass\n"
        "@dataclass\n"
        "class UploadEntry:\n    mime_type: str\n    declared_mime: str = ''\n"
        "    sniffed_mime: str = ''\n    type_mismatch: bool = False\n"
        "def sniff_mime(prefix):\n    return ''\n"
        "def classify(path):\n"
        "    declared = mimetypes.guess_type(path.name)[0]\n"
        "    return declared, declared, '', False\n"
    )
    cases = [
        (good, 0, "content-sniffing with a recorded mismatch passes"),
        (name_only, 1, "a name-only classifier is refused"),
        (good.replace("    type_mismatch: bool = False\n", ""), 1,
         "dropping type_mismatch from the entry is refused"),
        (good.replace("def classify(path):", "def other(path):"), 1,
         "a removed classify() is refused"),
        (good.replace("sniffed != declared", "False"), 1,
         "returning a winner without comparing is refused"),
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


def behaves(root: Path) -> list[str]:
    """Run the real classifier on a planted disguised file.

    The AST half above proves the SHAPE is present. It is not enough, and a
    mutation showed why: replacing the sniff result with an empty string left
    open(), the signature table and the comparison all in place, so the static
    check stayed green while the classifier went back to trusting the
    extension. Only executing it catches that.

    uploads.py imports `security`, which imports fastapi -- absent in the lint
    environment -- so the module is loaded with a stub in place. That is the
    same technique used to demonstrate the original defect (#561).
    """
    import importlib.util
    import tempfile
    import types

    path = root / UPLOADS
    stub = types.ModuleType("security")
    stub.safe_path = lambda *parts: Path(*[str(p) for p in parts])
    stub.sanitize_chat_id = lambda value: value
    saved = sys.modules.get("security")
    sys.modules["security"] = stub
    try:
        spec = importlib.util.spec_from_file_location("_uploads_probe", path)
        if spec is None or spec.loader is None:
            return ["uploads.py could not be loaded for the behavioural probe"]
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        out = []
        with tempfile.TemporaryDirectory() as tmp:
            disguised = Path(tmp) / "payload.exe.png"
            disguised.write_bytes(b"MZ\x90\x00\x03")
            resolved, declared, sniffed, mismatch = module.classify(disguised)
            if declared != "image/png":
                out.append(f"the declared type of payload.exe.png read as {declared!r}")
            if resolved == "image/png" or not sniffed:
                out.append(
                    "payload.exe.png still classifies as image/png -- content is not "
                    "deciding, so a renamed executable passes as an image"
                )
            if not mismatch:
                out.append("the declared/sniffed disagreement was not flagged")
            honest = Path(tmp) / "real.png"
            honest.write_bytes(b"\x89PNG\r\n\x1a\n\x00")
            if module.classify(honest)[3]:
                out.append("a genuine PNG was reported as a type mismatch")
        return out
    except Exception as exc:  # noqa: BLE001 -- any failure here is a refusal
        return [f"the behavioural probe could not run ({exc.__class__.__name__}: {exc})"]
    finally:
        if saved is not None:
            sys.modules["security"] = saved
        else:
            sys.modules.pop("security", None)


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--self-test":
        return self_test()
    root = Path(argv[0]) if argv else Path(".")
    path = root / UPLOADS
    if not path.is_file():
        sys.stderr.write(f"::error::{UPLOADS} is missing -- the check cannot judge\n")
        return 2
    issues = problems(path.read_text(encoding="utf-8")) + behaves(root)
    for issue in issues:
        sys.stderr.write(f"::error::NFR-SEC-81: {issue}\n")
    if issues:
        return 1
    print(
        "NFR-SEC-81 (local half): the upload classifier reads bytes, lets content "
        "win, and records the declared/sniffed mismatch"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
