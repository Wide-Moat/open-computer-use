#!/usr/bin/env python3
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
#
# NFR-SEC-82, the half of it that is local: zero OCU upstream credential in
# browser storage or in any browser-visible response.
#
# The row has two halves and only one of them lives here. The embed-token half
# -- the peer backend mints a signed short-TTL token, the UI verifies signature
# and expiry before setting session state -- belongs to the UI component, which
# is not in this tree. Every mention of the embed token here is a COMMENT
# describing what the portal does. Arming the whole row against this repository
# would claim a check on somebody else's code.
#
# What this repository does own is the browser surface it serves: the files
# under computer-use-server/static/. The requirement's storage clause is
# checkable against them directly, and it is a property worth holding rather
# than a formality, because the failure is silent -- a credential written to
# localStorage survives the tab, rides along with every later page load, and is
# readable by any script that lands on the origin.
#
# Measured when this was written: the entire frontend performs ONE browser-
# storage write, `claudeDangerousMode` in preview.js, a UI boolean. The two
# localStorage mentions in system_prompt.py are instructions telling the model
# NOT to use browser storage in artifacts, which is prose in a prompt rather
# than code that runs in a browser -- so the check reads the served assets, not
# every file that contains the word.

import re
import sys
from pathlib import Path

STATIC = Path("computer-use-server/static")
SERVER = Path("computer-use-server")

# The upstream credentials this deployment actually holds. Enumerated from the
# server rather than guessed: a generic *_TOKEN pattern also matches locals like
# `bearer_token` and would report the server's own plumbing as a browser leak.
CREDENTIALS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "MCP_API_KEY",
    "MCP_TOKEN",
    "GITLAB_TOKEN",
)

# Where a value becomes durable in the browser. document.cookie is included even
# though this server sets no cookie: the clause is about what reaches storage,
# and a future cookie write carrying a credential is the same defect.
SINKS = re.compile(
    r"\blocalStorage\s*\.\s*setItem|\bsessionStorage\s*\.\s*setItem|"
    r"\bindexedDB\b|\bdocument\s*\.\s*cookie\s*=",
    re.I,
)


def _is_vendored(path: Path) -> bool:
    """Third-party bundles. They are not ours to hold to this invariant, and
    their minified bodies match anything on substring alone."""
    return path.name.endswith((".min.js", ".umd.js")) or ".browser.min" in path.name


def served_assets(root: Path) -> list[Path]:
    """First-party files the browser loads."""
    base = root / STATIC
    if not base.is_dir():
        return []
    return sorted(
        p
        for p in base.rglob("*")
        if p.is_file() and p.suffix.lower() in (".js", ".html", ".css") and not _is_vendored(p)
    )


def storage_writes(text: str) -> list[tuple[int, str]]:
    """Every line that puts something into browser storage."""
    out = []
    for number, line in enumerate(text.splitlines(), 1):
        if SINKS.search(line):
            out.append((number, line.strip()))
    return out


def credential_on_line(line: str) -> str | None:
    """The upstream credential a line names, if any."""
    for name in CREDENTIALS:
        if name.lower() in line.lower():
            return name
    return None


def leaks(assets: dict[str, str]) -> list[str]:
    """Storage writes that carry an upstream credential. Empty means clean."""
    out = []
    for name, text in sorted(assets.items()):
        for number, line in storage_writes(text):
            found = credential_on_line(line)
            if found:
                out.append(
                    f"{name}:{number} writes {found} into browser storage -- it "
                    f"survives the tab and is readable by any script on the origin"
                )
    return out


def self_test() -> int:
    clean = "function f(){ try { localStorage.setItem('claudeDangerousMode','1'); } catch(e) {} }"
    cases = [
        ({"a.js": clean}, 0, "a UI boolean in localStorage is not a credential"),
        (
            {"a.js": "localStorage.setItem('k', MCP_API_KEY)"},
            1,
            "a credential written to localStorage is refused",
        ),
        (
            {"a.js": "sessionStorage.setItem('t', ANTHROPIC_AUTH_TOKEN)"},
            1,
            "sessionStorage is a sink too",
        ),
        (
            {"a.js": "document.cookie = 'mcp=' + MCP_TOKEN"},
            1,
            "a cookie write carrying a credential is refused",
        ),
        (
            {"a.js": "const k = MCP_API_KEY; send(k)"},
            0,
            "a credential NOT reaching storage is out of this clause's scope",
        ),
        ({"a.js": "// localStorage.setItem('k', MCP_API_KEY)"}, 1, "a commented sink still reports"),
        ({}, 0, "no served assets means nothing to refuse"),
    ]
    bad = 0
    for assets, want, label in cases:
        got = 1 if leaks(assets) else 0
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
    if not (root / SERVER).is_dir():
        sys.stderr.write(f"::error::{SERVER} is missing -- the check cannot judge\n")
        return 2
    paths = served_assets(root)
    if not paths:
        # Not a pass. An empty asset set means the check looked somewhere the
        # frontend no longer is, and reporting "clean" would certify a surface
        # this run never read.
        sys.stderr.write(
            f"::error::no first-party asset found under {STATIC} -- the browser "
            f"surface moved, and this check would pass without reading it\n"
        )
        return 2
    assets = {
        str(p.relative_to(root)): p.read_text(encoding="utf-8", errors="ignore") for p in paths
    }
    found = leaks(assets)
    for item in found:
        sys.stderr.write(f"::error::NFR-SEC-82: {item}\n")
    if found:
        return 1
    writes = sum(len(storage_writes(t)) for t in assets.values())
    print(
        f"NFR-SEC-82 (storage clause): {len(assets)} first-party asset(s), "
        f"{writes} browser-storage write(s), none carrying an upstream credential"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
