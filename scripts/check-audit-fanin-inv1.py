#!/usr/bin/env python3
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
#
# INV-1 lint for the audit fan-in contract (component-07, ADR-0009).
#
# INV-1: a source publishes only to its own channel, and the pipeline only ever
# RECEIVES. The contract encodes this as every operation being action: receive —
# there is no source-authored send surface. A send operation entering the
# contract would advertise a publish path the fan-in never grants, which is the
# cross-channel leak INV-2 exists to close, arriving one level up in the wire
# description itself.
#
# This is the code-side half of INV-1 that lands before the ingress service
# exists: the ingress enforces it at runtime by binding source to verified peer,
# and this keeps the CONTRACT from ever describing a surface that contradicts it.
#
# The check is deliberately structural and does not import an AsyncAPI library:
# it reads the operations map and asserts the action of every entry. Run with
# --self-test to exercise the pass and fail arms without touching the tree.

import sys

try:
    import yaml
except ImportError:
    sys.stderr.write("check-audit-fanin-inv1: PyYAML is required\n")
    sys.exit(2)

CONTRACT = "contracts/audit/audit-fanin.asyncapi.yaml"


def violations(doc):
    """Return a list of (operation_name, action) for every non-receive operation.

    An empty list means the contract is receive-only. A document with no
    operations at all is itself a violation: a fan-in contract that receives
    nothing describes no ingest, and an empty result must not read as a pass.
    """
    ops = doc.get("operations")
    if not isinstance(ops, dict) or not ops:
        return [("<no operations declared>", "none")]
    bad = []
    for name, op in ops.items():
        action = op.get("action") if isinstance(op, dict) else None
        if action != "receive":
            bad.append((name, action))
    return bad


def check_file(path):
    with open(path, encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    bad = violations(doc)
    if bad:
        for name, action in bad:
            sys.stderr.write(
                f"::error::audit-fanin INV-1: operation {name!r} has action "
                f"{action!r}, want 'receive' — the fan-in never grants a source a "
                f"publish surface\n"
            )
        return 1
    print(f"audit-fanin INV-1 ok: every operation in {path} is receive-only")
    return 0


def self_test():
    receive_only = {"operations": {"a": {"action": "receive"}, "b": {"action": "receive"}}}
    has_send = {"operations": {"a": {"action": "receive"}, "leak": {"action": "send"}}}
    empty = {"operations": {}}
    missing = {}

    assert violations(receive_only) == [], "receive-only must pass"
    assert violations(has_send) == [("leak", "send")], "a send must be flagged"
    assert violations(empty), "no operations must fail closed"
    assert violations(missing), "a missing operations map must fail closed"
    print("self-test ok")
    return 0


def main(argv):
    if "--self-test" in argv:
        return self_test()
    return check_file(CONTRACT)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
