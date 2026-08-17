#!/usr/bin/env python3
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
#
# Binds each audit-fan-in message to the OCSF class it claims.
#
# NFR-SEC-88 (class half): the control-plane authentication trail must be an
# OCSF Authentication (3002) event. This holds the CLASS -- `title: Authentication
# (OCSF 3002)` is checked against the vendored class file, so re-pointing that
# message at another class fails here. The emission half (every authentication
# act produces one, failures counted, fail-open with counted loss) is runtime
# and is not claimed by this check.
#
# The AsyncAPI validator beside this one checks that every payload $ref resolves
# to a well-formed JSON Schema. It does not check WHICH schema: replacing a
# vendored OCSF class with `{"type": "integer", "minimum": 5}` passes it (probed
# directly). So a class swapped for the wrong one — or a vendored file silently
# re-pointed at a different OCSF version — validates clean while the wire the
# contract describes has changed.
#
# Two independent statements of the same fact already exist and were never
# compared: the message title names the class uid ("API Activity (OCSF 6003)"),
# and the vendored file carries `uid` and `name`. This gate compares them, so a
# swap has to defeat both to go unnoticed.
#
# --self-test mutates each binding and asserts the check goes RED, then asserts
# the shipped tree passes. A gate that cannot fail is not a gate.
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTRACT = os.path.join(ROOT, "contracts", "audit", "audit-fanin.asyncapi.yaml")

# A message block declares its class in the title and references the vendored
# file a few lines below. The uid in the title is the assertion; the $ref is what
# it must agree with. "OCSF class TBD" marks a message whose class is not frozen
# yet (x-ocu-tbd) and carries no vendored file to bind to.
TITLE_RE = re.compile(r"^\s*title:\s*(?P<caption>.+?)\s*\(OCSF\s+(?P<uid>\d+)\)\s*$")
REF_RE = re.compile(r"""\$ref:\s*["'](?P<path>\./ocsf/(?P<version>[^/]+)/(?P<file>[^"']+\.json))["']""")


def fail(msg):
    print(f"::error::ocsf-class-identity: {msg}", file=sys.stderr)
    sys.exit(1)


def bindings(text):
    """Yield (uid, caption, ref_path) for every message that names an OCSF uid.

    The $ref is taken from the lines following the title, up to the next title:
    a message's payload always follows its own title in this document, so the
    first $ref after a title belongs to it. A title with no $ref before the next
    title yields nothing and is reported by the caller as an unbound claim.
    """
    lines = text.splitlines()
    out = []
    pending = None
    for i, line in enumerate(lines):
        t = TITLE_RE.match(line)
        if t:
            if pending is not None:
                out.append((pending[0], pending[1], None, pending[2]))
            pending = (t.group("uid"), t.group("caption"), i + 1)
            continue
        r = REF_RE.search(line)
        if r and pending is not None:
            out.append((pending[0], pending[1], r.group("path"), pending[2]))
            pending = None
    if pending is not None:
        out.append((pending[0], pending[1], None, pending[2]))
    return out


def check(contract_path=CONTRACT, quiet=False):
    """Return a list of failure strings; empty means the bindings agree."""
    with open(contract_path, encoding="utf-8") as f:
        text = f.read()

    found = bindings(text)
    if not found:
        return ["the contract declares no OCSF-classed messages; this gate would be vacuous"]

    problems = []
    checked = 0
    for uid, caption, ref, lineno in found:
        if ref is None:
            problems.append(
                f"{contract_path}:{lineno}: message titled {caption!r} claims OCSF {uid} but references no vendored class"
            )
            continue
        target = os.path.normpath(os.path.join(os.path.dirname(contract_path), ref))
        if not os.path.exists(target):
            problems.append(f"{contract_path}:{lineno}: {caption!r} references {ref}, which does not exist")
            continue
        try:
            with open(target, encoding="utf-8") as f:
                cls = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"{contract_path}:{lineno}: {ref} is not readable JSON: {exc}")
            continue

        actual = cls.get("uid")
        if actual is None:
            problems.append(
                f"{ref}: carries no uid, so it cannot be confirmed to be an OCSF class descriptor "
                f"(the message titled {caption!r} claims OCSF {uid})"
            )
            continue
        if str(actual) != uid:
            problems.append(
                f"{contract_path}:{lineno}: {caption!r} claims OCSF {uid} but {ref} is uid {actual} "
                f"({cls.get('caption', '?')}) — the payload validates as a schema either way"
            )
            continue
        checked += 1

    if not quiet:
        print(f"ocsf-class-identity: {checked} message/class bindings agree")
    return problems


def self_test():
    """Two-sided: each mutation must be caught, and the shipped tree must pass."""
    import shutil
    import tempfile

    src = os.path.join(ROOT, "contracts", "audit")
    with tempfile.TemporaryDirectory() as tmp:
        work = os.path.join(tmp, "audit")
        shutil.copytree(src, work)
        contract = os.path.join(work, "audit-fanin.asyncapi.yaml")

        # The shipped tree must pass, or every mutation below is trivially "caught".
        if check(contract, quiet=True):
            fail("self-test: the shipped contract does not pass; the mutations below would prove nothing")

        original = open(contract, encoding="utf-8").read()

        # Mutation 1: point a message at a DIFFERENT vendored class. This is the
        # case the AsyncAPI validator cannot see — both files are valid schemas.
        swapped = original.replace(
            '$ref: "./ocsf/1.5.0/api_activity.json"',
            '$ref: "./ocsf/1.5.0/authentication.json"',
            1,
        )
        if swapped == original:
            fail("self-test: could not build the class-swap mutation")
        open(contract, "w", encoding="utf-8").write(swapped)
        if not check(contract, quiet=True):
            fail("self-test: a message pointed at the wrong OCSF class was NOT caught")

        # Mutation 2: strip the uid from a vendored class, so its identity is
        # unconfirmable rather than wrong.
        open(contract, "w", encoding="utf-8").write(original)
        cls_path = os.path.join(work, "ocsf", "1.5.0", "api_activity.json")
        cls = json.load(open(cls_path, encoding="utf-8"))
        del cls["uid"]
        json.dump(cls, open(cls_path, "w", encoding="utf-8"))
        if not check(contract, quiet=True):
            fail("self-test: a vendored class with no uid was NOT caught")

    print("ocsf-class-identity self-test: a swapped class and a uid-less class both red; the shipped tree passes")


def main(argv):
    if "--self-test" in argv:
        self_test()
        return 0
    problems = check()
    for p in problems:
        print(f"::error::ocsf-class-identity: {p}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
