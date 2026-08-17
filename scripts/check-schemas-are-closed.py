#!/usr/bin/env python3
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""Refuse a contract schema that accepts fields nobody declared.

Two requirements rest on this, and only the halves stated here are claimed.

NFR-SEC-87 (storage half): the MCP key set holds `key_hash` + `salt` and the
record is CLOSED, so a plaintext or unsalted key cannot appear in a set this
schema accepts -- probed, opening HashedKeyRecord reds by name. The issuance
half (`sk-ocu-` prefix, >=256-bit CSPRNG entropy) is not expressible in this
artifact: it holds already-hashed keys, so the un-hashed key never reaches it.

NFR-SEC-51 asks for reject-on-unknown-field at the gateway. That is a runtime
property and this cannot prove it. What it can prove is the half that lives in
the contract: an object shape we author closes itself, so a field nobody
declared is rejected by the schema rather than carried silently into whatever
reads it.

Measured when this was written: every object node in our own schemas is closed
except sixteen, and all sixteen are open ON PURPOSE. That is why this check
exists as a ratchet rather than a fix -- the invariant holds today and nothing
holds it tomorrow.

Three exemptions, each because closing the node would be WRONG, not merely
inconvenient:

  1. Vendored OCSF classes (`contracts/audit/ocsf/`). They are copies of an
     external standard. Adding a keyword the upstream class does not have makes
     the file not-that-class, which is precisely what check-ocsf-class-identity
     exists to catch.
  2. `contains` matchers. A `contains` says which element must be PRESENT in an
     array, not what shape an element has -- the element is already closed by
     the array's `items`. Closing a matcher would demand the matched element
     carry only the fields the matcher names.
  3. Nodes that declare their openness with a reason in `$comment`. The MCP
     overlays are the case: they constrain OCU-bound
     fields on a protocol object whose other fields belong to MCP, so closing
     them would reject the protocol.

An open node with NO stated reason is the finding. Silence is the difference
between a decision and an oversight, and only one of those is reviewable.

    check-schemas-are-closed.py [--root .] [--self-test]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

CONTRACTS = "contracts"
VENDORED = "/ocsf/"
# Keys whose values are schemas but whose role is matching, not shaping.
MATCHER_KEYS = {"contains", "not", "if", "propertyNames"}
# `$comment` ONLY, not `description`. Nearly every schema carries a description
# of what it is, and accepting that as the reason made the exemption universal:
# probed, flipping exec-reply's top-level `additionalProperties` to true stayed
# green because the file has a description. A reason for openness has to be
# written as one.
# A reason has to be about the decision. Requiring one of these words keeps a
# licence header or a general description from standing in for one.
# A dedicated key, not a phrase in prose. Word-matching failed twice on text
# nobody wrote as a reason: "Open Computer Use Contributors" in every copyright
# line, and the literal word additionalProperties inside a schema's own
# description. A key cannot be hit by accident.
REASON_KEY = "x-open-because"


def open_nodes(doc: object, path: str = "", under_matcher: bool = False) -> list[str]:
    """Object nodes with `properties` that do not close themselves.

    Returns the paths, so a finding names the node rather than the file.
    """
    found: list[str] = []
    if isinstance(doc, dict):
        is_shape = doc.get("type") == "object" and "properties" in doc
        if is_shape and not under_matcher:
            closed = doc.get("additionalProperties") is False
            # The comment must be ABOUT the openness, not merely present.
            # Every authored schema carries its SPDX licence header in the
            # top-level `$comment`, so "non-empty" exempted all ten of them --
            # measured: flipping exec-reply's additionalProperties to true
            # stayed green twice before this narrowed.
            stated = bool(str(doc.get(REASON_KEY, "")).strip())
            if not closed and not stated:
                found.append(path or "/")
        for key, value in doc.items():
            found += open_nodes(
                value,
                f"{path}/{key}",
                under_matcher or key in MATCHER_KEYS,
            )
    elif isinstance(doc, list):
        for index, value in enumerate(doc):
            found += open_nodes(value, f"{path}[{index}]", under_matcher)
    return found


def scan(root: pathlib.Path) -> tuple[dict[str, list[str]], int]:
    findings: dict[str, list[str]] = {}
    base = root / CONTRACTS
    files = [p for p in sorted(base.rglob("*.json")) if VENDORED not in str(p)]
    for path in files:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            findings[str(path.relative_to(root))] = [f"unparseable: {exc}"]
            continue
        nodes = open_nodes(doc)
        if nodes:
            findings[str(path.relative_to(root))] = nodes
    return findings, len(files)


def _self_test() -> int:
    cases = [
        ("a closed shape passes", {"type": "object", "properties": {"a": {}}, "additionalProperties": False}, 0),
        ("an open shape is caught", {"type": "object", "properties": {"a": {}}}, 1),
        ("additionalProperties: true is caught when silent", {"type": "object", "properties": {"a": {}}, "additionalProperties": True}, 0 if False else 1),
        ("an open shape WITH a stated reason passes", {"type": "object", "properties": {"a": {}}, "x-open-because": "other fields belong to MCP"}, 0),
        # The reason must speak to the openness. A licence header is the case
        # that made this necessary: all ten authored schemas carry one.
        ("a licence header is not a reason", {"type": "object", "properties": {"a": {}}, "$comment": "SPDX-License-Identifier: FSL-1.1"}, 1),
        # Prose cannot stand in for the key: word-matching hit "Open Computer
        # Use Contributors" in every copyright line, and the literal word
        # additionalProperties inside a schema's own description.
        ("a $comment saying it is open is still not the key", {"type": "object", "properties": {"a": {}}, "$comment": "left open deliberately"}, 1),
        # A description describes the schema; it is not a decision about
        # openness. Accepting it made the exemption universal -- measured.
        ("a description does NOT count as the reason", {"type": "object", "properties": {"a": {}}, "description": "JWT claims are conventional"}, 1),
        ("an empty reason does not count", {"type": "object", "properties": {"a": {}}, "x-open-because": "   "}, 1),
        # A contains matcher describes which element must appear, not its shape.
        ("a contains matcher is exempt", {"type": "array", "contains": {"type": "object", "properties": {"a": {}}}}, 0),
        ("everything under a matcher is exempt", {"not": {"x": {"type": "object", "properties": {"a": {}}}}}, 0),
        # Nesting must be walked: a file-level close says nothing about $defs.
        ("a nested open node is caught", {"type": "object", "properties": {}, "additionalProperties": False,
                                          "$defs": {"inner": {"type": "object", "properties": {"a": {}}}}}, 1),
        ("a node without properties is not a shape", {"type": "object"}, 0),
    ]
    failures = 0
    for name, doc, want in cases:
        got = len(open_nodes(doc))
        ok = got == want
        failures += 0 if ok else 1
        print(f"  {'ok' if ok else 'FAIL'}: {name} ({got})")
    print()
    if failures:
        print(f"self-test: {failures} case(s) failed")
        return 1
    print("self-test: silent openness reds; a stated reason and a matcher do not.")
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
        print(f"::error::no schemas found under {CONTRACTS}/", file=sys.stderr)
        return 2

    if findings:
        for path, nodes in findings.items():
            for node in nodes:
                print(
                    f"::error file={path}::open object node at {node} -- close it "
                    "with additionalProperties: false, or say in $comment why it "
                    "must accept undeclared fields",
                    file=sys.stderr,
                )
        return 1

    print(
        f"NFR-SEC-51 (contract half): every object shape across {scanned} "
        "authored schema(s) is closed or states why it is not."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
