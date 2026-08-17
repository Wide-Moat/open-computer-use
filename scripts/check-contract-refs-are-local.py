#!/usr/bin/env python3
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
#
# Every $ref in an AsyncAPI contract resolves on disk, never over the network.
#
# The validator's header says it validates "hermetically", and today that is
# true only because #402 vendored the OCSF schemas and rewrote every $ref to a
# relative path. Nothing holds it true. @asyncapi/parser resolves an http(s)
# $ref by fetching it, and a fetch that SUCCEEDS is indistinguishable from a
# local read in the output: the document validates and the job prints `ok`.
#
# Measured on this tree before writing the check -- one $ref repointed at a
# live host with a valid certificate:
#
#     $ref: https://json.schemastore.org/package.json   ->  exit 0, "ok"
#
# So the gate would go green while depending on a third party's uptime and
# on whatever bytes that party serves that day. A contract gate that reads its
# subject from the internet is not a contract gate.
#
# The neighbouring TLS failure is not a defence. The same probe against a host
# whose certificate does not match reds -- but on the certificate, not on the
# remoteness, so it protects only by the accident of which host was named.
#
# Scheme-relative refs (`//host/x.json`) are remote too: urlsplit gives them an
# empty scheme and a non-empty netloc, so netloc is the discriminator, not the
# scheme.

import sys
from pathlib import Path
from urllib.parse import urlsplit

try:
    import yaml
except ImportError:
    sys.stderr.write("check-contract-refs-are-local: PyYAML is required\n")
    sys.exit(2)


# Documents that legitimately carry no $ref. Declared by name so that a
# document which HAS refs cannot silently drop to zero and still pass: the gate
# would otherwise read "all 0 refs are local" as a clean bill of health.
# ocu-constraints defines its shapes inline under $defs and binds nothing.
REFLESS = {"ocu-constraints.schema.json"}


def iter_refs(node, path=()):
    """Yield (json_pointer, ref_value) for every $ref in the document."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                yield "/".join(str(p) for p in path), value
            else:
                yield from iter_refs(value, path + (key,))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from iter_refs(value, path + (index,))


def is_remote(ref):
    """True when resolving this $ref requires the network.

    A bare fragment (`#/components/x`) is in-document. A relative path is on
    disk. Anything carrying a netloc leaves the machine -- including the
    scheme-relative form, whose scheme is empty.
    """
    split = urlsplit(ref)
    return bool(split.netloc) or split.scheme in ("http", "https")


def unresolvable(ref, doc_path):
    """A relative $ref whose target is not on disk, or None when it resolves."""
    target = ref.split("#", 1)[0]
    if not target:
        return None  # in-document fragment
    resolved = (doc_path.parent / target).resolve()
    return None if resolved.exists() else str(resolved)


def check_file(path):
    """Return a list of (pointer, ref, reason) for every non-local $ref.

    Returns a plain list, not a (findings, count) pair. The meta-gate
    (`check-self-tests-are-bound.py`) proves a checker is bound to its subject
    by stubbing this function to `return []` and requiring --self-test to red.
    A tuple return turns that stub into `ValueError: not enough values to
    unpack` -- red, but on a crash rather than on the finding being gone, which
    would pass the meta-gate for a checker that asserts nothing. The ref count
    is available separately via count_refs().

    The walk is TRANSITIVE. Checking only the named documents leaves the hole
    one level down: a remote $ref injected into a vendored OCSF schema -- which
    the fan-in document $refs by relative path -- passes both this check and the
    parser, because the parser fetches it successfully and neither one looks
    inside a file it did not open. Measured before this was written: both exit 0
    on exactly that tree.
    """
    findings = []
    seen = set()
    queue = [(Path(path), "")]
    while queue:
        doc_path, prefix = queue.pop()
        resolved = doc_path.resolve()
        if resolved in seen:
            # Contracts $ref each other; without this a cycle spins forever.
            continue
        seen.add(resolved)
        try:
            doc = yaml.safe_load(doc_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            findings.append((prefix or str(doc_path), str(doc_path), f"is unreadable ({type(exc).__name__})"))
            continue
        for pointer, ref in iter_refs(doc):
            where = f"{prefix}{pointer}" if not prefix else f"{prefix} -> {doc_path.name}:{pointer}"
            if is_remote(ref):
                findings.append((where, ref, "resolves over the network"))
                continue
            missing = unresolvable(ref, doc_path)
            if missing:
                findings.append((where, ref, f"does not exist on disk ({missing})"))
                continue
            target = ref.split("#", 1)[0]
            if target:
                queue.append(((doc_path.parent / target).resolve(), f"{doc_path.name}:{pointer}"))
    return findings


def count_refs(path):
    """How many $refs the document carries — reported so a pass states its scope."""
    doc = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return len(list(iter_refs(doc)))


def self_test():
    """Exercise both arms on fixtures written to a temp dir.

    The fixtures name a schema this checker never reads, so a pass here cannot
    come from the repository's own contracts being well-formed.
    """
    import tempfile

    doc = (
        "asyncapi: 3.0.0\n"
        "info: {title: t, version: '1'}\n"
        "components:\n"
        "  schemas:\n"
        "    a: {$ref: '%s'}\n"
        "    b: {$ref: '#/components/schemas/a'}\n"
    )
    cases = [
        ("./vendored.json", 0, "a relative ref whose target exists"),
        ("https://example.invalid/x.json", 1, "an https ref"),
        ("//example.invalid/x.json", 1, "a scheme-relative ref"),
        ("./absent.json", 1, "a relative ref with no file"),
    ]
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "vendored.json").write_text('{"type":"object"}', encoding="utf-8")
        for ref, want, label in cases:
            path = root / "d.asyncapi.yaml"
            path.write_text(doc % ref, encoding="utf-8")
            findings = check_file(path)
            count = count_refs(path)
            got = 1 if findings else 0
            if got != want or count != 2:
                bad += 1
                sys.stderr.write(
                    f"self-test FAIL: {label} -> findings={got} want={want}, refs={count} want=2\n"
                )
            else:
                print(f"self-test ok: {label} -> {'flagged' if got else 'accepted'}")

        # Transitivity: the remote ref sits one level down, in a file the entry
        # document only reaches by a relative ref. The un-transitive version of
        # this checker returned clean here, as did the AsyncAPI parser.
        (root / "mid.json").write_text(
            '{"properties":{"deep":{"$ref":"https://example.invalid/x.json"}}}', encoding="utf-8"
        )
        entry = root / "entry.asyncapi.yaml"
        entry.write_text(doc % "./mid.json", encoding="utf-8")
        if not check_file(entry):
            bad += 1
            sys.stderr.write("self-test FAIL: a remote ref one level down was not reported\n")
        else:
            print("self-test ok: a remote ref one level down -> flagged")

        # And the cycle guard, or the walk above never terminates.
        (root / "p.json").write_text('{"a":{"$ref":"./q.json"}}', encoding="utf-8")
        (root / "q.json").write_text('{"b":{"$ref":"./p.json"}}', encoding="utf-8")
        if check_file(root / "p.json"):
            bad += 1
            sys.stderr.write("self-test FAIL: mutually referencing local files reported a finding\n")
        else:
            print("self-test ok: a ref cycle terminates and reports nothing")
    if bad:
        return 1
    print(f"self-test ok: {len(cases) + 2} cases")
    return 0


def main(argv):
    if argv and argv[0] == "--self-test":
        return self_test()
    if not argv:
        sys.stderr.write("usage: check-contract-refs-are-local.py <doc.asyncapi.yaml>...\n")
        return 2
    failed = 0
    for arg in argv:
        findings = check_file(arg)
        ref_count = count_refs(arg)
        if findings:
            failed += 1
            for pointer, ref, reason in findings:
                sys.stderr.write(
                    f"::error::{arg}: $ref {ref!r} at /{pointer} {reason} — "
                    f"contract schemas are vendored and resolved on disk\n"
                )
        elif ref_count == 0 and Path(arg).name not in REFLESS:
            # Zero refs is a pass only for a document listed as self-contained.
            # "All 0 refs are local" is also true of a document that LOST its
            # payload bindings, which is the shape this gate exists to notice --
            # so the empty case must be declared, not inferred.
            failed += 1
            sys.stderr.write(
                f"::error::{arg}: no $ref found — either the payload bindings are "
                f"gone, or the document is self-contained and belongs in REFLESS\n"
            )
        else:
            print(f"refs local: {arg} ({ref_count} refs)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
