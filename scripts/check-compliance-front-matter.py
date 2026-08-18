#!/usr/bin/env python3
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""NFR-COMP-17: report which component specs declare the controls they satisfy.

The row asks for a per-component `compliance:` front-matter field, "YAML field
populated", and a generated controls matrix. Measured when this was written:
the field is PRESENT in all seven component specs and EMPTY in all seven --
`compliance: []`, inherited from the template. No controls matrix exists.

The front-matter validator beside this one requires four fields and does not
know about this one, so nothing ever looked. A field that is present and empty
reads as compliance to anyone skimming, which is the failure mode worth
naming: the shape of the answer without the answer.

This does NOT fill the field in. Which SOC 2 / ISO / DORA controls a component
satisfies is a compliance judgement with an owner, and inventing entries to
turn a number green would be worse than the empty list -- it would make the
gap invisible instead of merely unmeasured.

What it does is count, and hold a ratchet:

    check-compliance-front-matter.py [--root .] [--min-declared N] [--self-test]

--min-declared defaults to 0, which never fails on the current state. It fails
when a spec that HAD declarations loses them, and when a spec carries no
`compliance:` key at all -- both are regressions a PR causes and a PR can fix.
The count on every run is what stops the zero from being invisible.

`00-overview.md` is exempt: it is the components index, not a component. The
template is exempt for the same reason -- it is where the empty list belongs.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

COMPONENTS = "docs/architecture/components"
# Not components: the index page and the template a new spec is copied from.
EXEMPT = {"00-overview.md", "0000-template.md"}


def front_matter(text: str) -> dict[str, str]:
    """The top YAML block, read line-wise.

    Deliberately not a YAML parse: these files open with HTML license comments
    before the `---`, which a strict loader rejects, and the validator beside
    this one reads them the same way.
    """
    fields: dict[str, str] = {}
    inside = False
    for line in text.splitlines():
        if line.strip() == "---":
            if inside:
                break
            inside = True
            continue
        if not inside:
            continue
        if ":" not in line or line.startswith((" ", "\t", "-")):
            continue
        key, _, val = line.partition(":")
        fields[key.strip()] = val.strip()
    return fields


def declared_controls(value: str) -> list[str]:
    """Controls named by a `compliance:` value.

    Handles the inline-list form the template uses. A block list continues on
    following lines, which `front_matter` drops -- so a block form reads as
    zero here, which is the safe direction: it under-counts rather than
    crediting a declaration that may not be there.
    """
    inner = value.strip()
    if inner.startswith("[") and inner.endswith("]"):
        inner = inner[1:-1]
    return [c.strip().strip("\"'") for c in inner.split(",") if c.strip()]


def survey(root: pathlib.Path) -> tuple[dict[str, list[str]], list[str]]:
    """(spec -> controls declared, specs with no compliance key at all)."""
    declared: dict[str, list[str]] = {}
    absent: list[str] = []
    base = root / COMPONENTS
    for path in sorted(base.glob("*.md")):
        if path.name in EXEMPT:
            continue
        fields = front_matter(path.read_text(encoding="utf-8"))
        if "compliance" not in fields:
            absent.append(path.name)
            continue
        declared[path.name] = declared_controls(fields["compliance"])
    return declared, absent


def dangling_adr_refs(root) -> list[tuple[str, list[str]]]:
    """Component specs whose `adr:` names an ADR that does not exist.

    The field became load-bearing when #500 derived every `compliance:` entry
    from it. Nothing read it: measured before this check, replacing
    01-mcp-gateway's `adr: [0027]` with `adr: [0099]` left the gate at exit 0
    and the 61 control citations unchanged -- the declarations survived their
    own source going missing.

    A typo here does not fail loudly. It silently narrows what the component is
    governed by, and the compliance field it feeds keeps the stale answer.
    """
    import re

    known = {p.stem.split("-")[0] for p in (root / "docs/architecture/adr").glob("[0-9]*.md")}
    out = []
    for spec in sorted((root / "docs/architecture/components").glob("[0-9]*.md")):
        front = re.match(r"^.*?^---\n(.*?)\n---", spec.read_text(encoding="utf-8"), re.S | re.M)
        if not front:
            continue
        field = re.search(r"^adr:\s*\[([^\]]*)\]", front.group(1), re.M)
        if not field or not field.group(1).strip():
            continue
        missing = [i.strip() for i in field.group(1).split(",") if i.strip().zfill(4) not in known]
        if missing:
            out.append((spec.name, missing))
    return out


def derivable_controls(root) -> dict[str, set[str]]:
    """Controls each component spec should carry, taken from the ADRs.

    NFR-COMP-17 asks for the field POPULATED, and it is empty in all seven
    specs. Filling it by hand would mean inventing control citations, which is
    the opposite of an audit trail. It does not have to be invented: 43 of 45
    ADRs already carry a populated `compliance-impact`, and an ADR names the
    components it governs with a markdown link. So the mapping is a
    consequence of decisions already accepted -- 8 of 9 components resolve.

    Matching is on the LINK, not on the file stem appearing in the prose: a
    stem search returned 0 of 9 here, because ADRs reference components as
    `[Egress trust-edge](components/06-egress-trust-edge.md)` rather than by
    bare name.
    """
    import re

    comps = {p.stem for p in (root / "docs/architecture/components").glob("[0-9]*.md")}
    out: dict[str, set[str]] = {}
    for adr in sorted((root / "docs/architecture/adr").glob("[0-9]*.md")):
        text = adr.read_text(encoding="utf-8")
        front = re.match(r"^.*?^---\n(.*?)\n---", text, re.S | re.M)
        found = re.search(r"compliance-impact:\s*\[([^\]]*)\]", front.group(1) if front else "")
        controls = [c.strip() for c in found.group(1).split(",")] if found and found.group(1).strip() else []
        if not controls:
            continue
        for ref in re.findall(r"components/([0-9][^)#\s]*?)\.md", text):
            if ref in comps:
                out.setdefault(ref, set()).update(controls)
    return out


def verdict(
    declared: dict[str, list[str]], absent: list[str], floor: int
) -> list[str]:
    """Reasons to refuse. Empty means the ratchet holds."""
    problems: list[str] = []
    if absent:
        problems.append(
            "component spec(s) carry no `compliance:` key at all: "
            + ", ".join(sorted(absent))
            + " -- the field is how NFR-COMP-17 is answered, so its absence is "
            "not the same as an empty answer"
        )
    total = sum(len(v) for v in declared.values())
    if total < floor:
        problems.append(
            f"declared controls dropped to {total}, below the floor of {floor}"
        )
    return problems


def undeclared_but_derivable(declared: dict[str, list[str]], derivable: dict[str, set[str]]) -> dict[str, list[str]]:
    """Controls an ADR assigns to a component that its spec does not declare.

    Reported, never blocking. Populating seven specs is canon work with an
    owner; a gate that red every PR until someone does it would be turned off
    long before it was satisfied -- the same trap as requiring a context that
    never arrives. What this does buy: the gap is a number on every run instead
    of a claim nobody has measured.
    """
    gaps: dict[str, list[str]] = {}
    for comp, controls in sorted(derivable.items()):
        have = {c.strip() for c in declared.get(f"{comp}.md", [])}
        missing = sorted(controls - have)
        if missing:
            gaps[comp] = missing
    return gaps


def _self_test() -> int:
    cases = [
        ("a missing key reds", {}, ["05-x.md"], 0, True),
        ("an empty list at floor 0 passes", {"05-x.md": []}, [], 0, False),
        ("losing a declaration reds", {"05-x.md": []}, [], 1, True),
        ("holding the floor passes", {"05-x.md": ["SOC2-CC6.1"]}, [], 1, False),
        ("gaining passes", {"05-x.md": ["a", "b"]}, [], 1, False),
    ]
    # dangling_adr_refs() on a constructed tree. Without this the branch is
    # live and untested, and the meta-gate would certify it stubbed.
    import tempfile

    dangling_failures = 0
    for adr_id, want, label in (
        ("0001", False, "an adr: id with a matching file is accepted"),
        ("0099", True, "an adr: id with no matching file is reported"),
    ):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            (base / "docs/architecture/adr").mkdir(parents=True)
            (base / "docs/architecture/components").mkdir(parents=True)
            (base / "docs/architecture/adr/0001-a.md").write_text("x", encoding="utf-8")
            (base / "docs/architecture/components/01-c.md").write_text(
                f"---\nstatus: draft\nadr: [{adr_id}]\n---\n", encoding="utf-8"
            )
            got = bool(dangling_adr_refs(base))
            ok = got == want
            dangling_failures += 0 if ok else 1
            print(f"  {'ok' if ok else 'FAIL'}: {label}")

    # The derivation, on constructed inputs. Without this the gap report is
    # live and untested: the cases above only drive verdict().
    derive_cases = [
        ("an ADR control absent from the spec is reported",
         {"05-x.md": []}, {"05-x": {"SOC2-CC6.1"}}, True),
        ("a control the spec already declares is not reported",
         {"05-x.md": ["SOC2-CC6.1"]}, {"05-x": {"SOC2-CC6.1"}}, False),
        ("a component no ADR governs is not reported",
         {"05-x.md": []}, {}, False),
    ]
    derive_failures = 0
    for name, declared_c, derivable_c, want in derive_cases:
        ok = bool(undeclared_but_derivable(declared_c, derivable_c)) == want
        derive_failures += 0 if ok else 1
        print(f"  {'ok' if ok else 'FAIL'}: {name}")
    failures = 0
    for name, declared, absent, floor, want_red in cases:
        got_red = bool(verdict(declared, absent, floor))
        ok = got_red == want_red
        failures += 0 if ok else 1
        print(f"  {'ok' if ok else 'FAIL'}: {name}")

    parses = [
        ("an empty inline list declares nothing", "[]", 0),
        ("an inline list is counted", '["SOC2-CC6.1", "ISO-A.9.4"]', 2),
        ("an unquoted inline list is counted", "[DORA-Art28, SOC2-CC7.2]", 2),
        ("whitespace alone declares nothing", "   ", 0),
    ]
    for name, value, want in parses:
        got = len(declared_controls(value))
        ok = got == want
        failures += 0 if ok else 1
        print(f"  {'ok' if ok else 'FAIL'}: {name} ({got})")

    # The reader must find the block that follows HTML comments, or every spec
    # reads as key-absent and the gate reports a defect that is not there.
    text = "<!-- SPDX -->\n---\nstatus: draft\ncompliance: [X]\n---\nbody\n"
    got = front_matter(text).get("compliance")
    ok = got == "[X]"
    failures += 0 if ok else 1
    print(f"  {'ok' if ok else 'FAIL'}: front-matter is found past a leading comment ({got!r})")

    failures += derive_failures + dangling_failures

    print()
    if failures:
        print(f"self-test: {failures} case(s) failed")
        return 1
    print("self-test: the check reds on an absent key and on a lost declaration.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--min-declared", type=int, default=0)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()

    root = pathlib.Path(args.root).resolve()
    declared, absent = survey(root)
    if not declared and not absent:
        print(f"::error::no component specs found under {COMPONENTS}", file=sys.stderr)
        return 2

    total = sum(len(v) for v in declared.values())
    empty = [n for n, v in declared.items() if not v]
    print(
        f"NFR-COMP-17: {total} control(s) declared across "
        f"{len(declared)} component spec(s); {len(empty)} declare none"
    )
    for name in sorted(declared):
        shown = ", ".join(declared[name]) if declared[name] else "(none)"
        print(f"  {name}: {shown}")

    problems = verdict(declared, absent, args.min_declared)
    if problems:
        for problem in problems:
            print(f"::error::{problem}", file=sys.stderr)
        return 1

    dangling = dangling_adr_refs(root)
    if dangling:
        for spec, missing in dangling:
            print(
                f"::error::{spec}: adr: names {', '.join(missing)}, and no such ADR "
                "exists. The compliance: field is derived from this list, so a "
                "dangling id silently keeps a stale answer instead of failing.",
                file=sys.stderr,
            )
        return 1

    derivable = derivable_controls(root)
    gaps = undeclared_but_derivable(declared, derivable)
    if gaps:
        missing_total = sum(len(v) for v in gaps.values())
        print(
            f"::notice::{missing_total} control citation(s) across {len(gaps)} "
            f"component spec(s) are already assigned by an ADR's "
            f"compliance-impact and not declared on the component. These are not "
            f"a judgement call -- each is a consequence of a decision already "
            f"accepted, and the ADR names the component by link."
        )
        for comp in sorted(gaps):
            print(f"  {comp}: {', '.join(gaps[comp][:6])}{' ...' if len(gaps[comp]) > 6 else ''}")

    if empty:
        print(
            "::notice::the field is present and empty everywhere it is empty -- "
            "NFR-COMP-17 asks for it POPULATED. Reported, not failed: applying "
            "the mapping above is canon work with an owner, and a gate that red "
            "every PR until it lands would be switched off before it was met."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
