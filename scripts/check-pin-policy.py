#!/usr/bin/env python3
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""NFR-SEC-18: every action and container image is pinned to an immutable ref.

security.yml states the policy in a header comment and names zizmor as what
enforces it — `unpinned-uses` "would block merge on its own". Measured: zizmor
appears in five comments across two workflows and in NO executed step, no
requirements file, and no script. The policy rested on a tool that does not
run here, which is worse than an unstated policy: the comment tells the next
reader the question is already settled.

Two rules, both of which zizmor would have covered:

  1. Every third-party `uses:` names a 40-hex commit SHA, never a tag. A tag is
     a movable pointer; the account that publishes it can repoint it after
     review. `actions/*` and `github/*` are NOT exempt — a first-party org is
     still an upstream.
  2. Every container `image:` carries `@sha256:<64-hex>`. A `name:tag` image is
     the same movable pointer wearing different syntax, and the workflows here
     run third-party containers as job hosts.
  3. Every `actions/checkout` sets `persist-credentials: false` (zizmor calls
     this `artipacked`). Without it the job token stays in `.git/config` for
     every later step in the job -- including any third-party action that reads
     the working tree. No workflow here pushes back, so nothing needs it.

Local `./` and `docker://`-less reusable-workflow refs are out of scope: a
relative path resolves inside this repository, so there is no upstream to move.

    check-pin-policy.py [--root .] [--self-test]
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

# `uses: owner/repo@ref` or `uses: owner/repo/sub/path@ref`. The ref is captured
# whole rather than matched as hex, so an unpinned one is REPORTED rather than
# skipped -- a regex demanding 40 hex digits matches nothing on a tag, which
# would make the check silently pass exactly what it exists to catch.
USES_RE = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)")
IMAGE_RE = re.compile(r"^\s*image:\s*([^\s#]+)")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")


def unpinned_uses(text: str) -> list[str]:
    """`uses:` refs that name something movable."""
    bad = []
    for line in text.splitlines():
        m = USES_RE.match(line)
        if not m:
            continue
        ref = m.group(1)
        # A local composite action or a relative reusable workflow: no upstream.
        if ref.startswith("./") or ref.startswith(".github/"):
            continue
        if "@" not in ref:
            bad.append(f"{ref} (no ref at all)")
            continue
        _, _, pin = ref.rpartition("@")
        if not SHA40.match(pin):
            bad.append(ref)
    return bad


def unpinned_images(text: str) -> list[str]:
    """Container `image:` refs without a digest.

    A matrix entry is a bare name with no registry path and no tag, which is a
    VALUE being iterated rather than an image being run -- `- open-computer-use`
    under `matrix.image:`. Those are matched by the list-item form, not by
    `image:`, so this walks only the key form and still guards against the bare
    name reaching the digest test.
    """
    bad = []
    for line in text.splitlines():
        m = IMAGE_RE.match(line)
        if not m:
            continue
        ref = m.group(1)
        if "${{" in ref:
            # An expression: the pin lives wherever the expression is defined,
            # and this check cannot follow it. Reported so it is a decision.
            bad.append(f"{ref} (expression -- pin at its definition)")
            continue
        if not DIGEST.search(ref):
            bad.append(ref)
    return bad


def persisting_checkouts(text: str) -> list[str]:
    """`actions/checkout` steps that leave the job token in `.git/config`.

    Reads the step BLOCK, not the file: a `persist-credentials: false` anywhere
    in the file would otherwise vouch for every checkout in it, which is exactly
    the shape build.yml has today -- nine checkouts, one flag.

    A step ends at the next line indented no deeper than its own `- `, so the
    scan is bounded by structure rather than by a fixed line count.
    """
    lines = text.splitlines()
    bad = []
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*)-\s+uses:\s*actions/checkout@", line)
        if not m:
            continue
        indent = len(m.group(1))
        block = []
        for follow in lines[i + 1:]:
            if not follow.strip():
                continue
            lead = len(follow) - len(follow.lstrip())
            if lead <= indent:
                break
            block.append(follow)
        if not any("persist-credentials: false" in b for b in block):
            bad.append(f"line {i + 1}")
    return bad


    # A downloaded executable is a supply-chain input exactly like a `uses:` ref,
    # and this checker did not look at one. The proto gate curled a 34 MB `buf`
    # and ran it: the URL pinned v1.34.0, which is a version tag, not an
    # identity -- a release asset is mutable, so the tag buys nothing against a
    # substituted artifact. Nothing in CI verified a checksum anywhere.
    #
    # The rule is deliberately narrow: a download is only a finding when the
    # same `run:` block later makes it executable. Fetching a config file or a
    # checksum list is not this problem, and flagging those would get the check
    # ignored.


DOWNLOAD = re.compile(r"\b(?:curl|wget)\b[^\n|]*?(?:-o|-O|--output)\s+(\S+)")
VERIFIES = re.compile(r"\b(?:sha256sum|shasum|sha512sum|cosign\s+verify|gpg\s+--verify)\b")


def unverified_downloads(text: str) -> list[str]:
    """Downloads that are made executable without any integrity check.

    Scoped per `run:` block, not per file: a workflow that verifies one binary
    and blindly executes another must still fail, and a file-wide search for
    `sha256sum` would call that clean.
    """
    bad = []
    for block in re.split(r"\n(?=\s*-\s+name:|\s*-\s+uses:)", text):
        if not DOWNLOAD.search(block):
            continue
        if VERIFIES.search(block):
            continue
        for m in DOWNLOAD.finditer(block):
            target = m.group(1)
            # Only executables. `chmod +x` or a direct invocation of the path.
            made_executable = re.search(rf"chmod\s+\+x\s+{re.escape(target)}", block) or re.search(
                rf"^\s*{re.escape(target)}\s", block, re.M
            )
            if made_executable:
                bad.append(target)
    return bad


def scan(root: pathlib.Path) -> dict[str, list[str]]:
    findings: dict[str, list[str]] = {}
    wf = root / ".github" / "workflows"
    paths = sorted(wf.glob("*.yml")) + sorted(wf.glob("*.yaml"))
    actions = root / ".github" / "actions"
    if actions.is_dir():
        paths += sorted(actions.rglob("action.yml"))
    for path in paths:
        text = path.read_text(encoding="utf-8")
        problems = [f"uses: {u}" for u in unpinned_uses(text)]
        problems += [f"image: {i}" for i in unpinned_images(text)]
        problems += [
            f"actions/checkout at {w} does not set persist-credentials: false"
            for w in persisting_checkouts(text)
        ]
        problems += [
            f"downloads {d} and executes it with no checksum or signature check"
            for d in unverified_downloads(text)
        ]
        if problems:
            findings[str(path.relative_to(root))] = problems
    return findings, len(paths)


def _self_test() -> int:
    cases = [
        # Downloads. The negative cases matter as much as the positive one: a
        # rule that also flagged a fetched config file or the checksum list
        # itself would be turned off within a week.
        (
            "an executable downloaded with no check is caught",
            "      - name: b\n        run: |\n          curl -sSL -o /tmp/b https://x/b\n          chmod +x /tmp/b\n          /tmp/b run\n",
            unverified_downloads,
            True,
        ),
        (
            "the same download with sha256sum passes",
            "      - name: b\n        run: |\n          curl -sSL -o /tmp/b https://x/b\n          sha256sum /tmp/b\n          chmod +x /tmp/b\n",
            unverified_downloads,
            False,
        ),
        (
            "a config file that is never executed passes",
            "      - name: c\n        run: |\n          curl -sSL -o /tmp/c.yaml https://x/c.yaml\n          cat /tmp/c.yaml\n",
            unverified_downloads,
            False,
        ),
        (
            "fetching the checksum list itself passes",
            "      - name: s\n        run: |\n          curl -sSL -o /tmp/sha256.txt https://x/sha256.txt\n",
            unverified_downloads,
            False,
        ),
        ("a tag-pinned action is caught", "      - uses: actions/checkout@v4\n", unpinned_uses, True),
        ("a sha-pinned action passes", "      - uses: actions/checkout@" + "a" * 40 + "\n", unpinned_uses, False),
        ("a short sha is caught", "      - uses: o/r@" + "a" * 7 + "\n", unpinned_uses, True),
        ("a ref-less use is caught", "      - uses: owner/repo\n", unpinned_uses, True),
        ("a local action is exempt", "      - uses: ./.github/actions/thing\n", unpinned_uses, False),
        ("a subpath sha passes", "      - uses: github/codeql-action/init@" + "b" * 40 + "\n", unpinned_uses, False),
        ("a digest image passes", "      image: registry:2@sha256:" + "c" * 64 + "\n", unpinned_images, False),
        ("a tag-only image is caught", "      image: registry:2\n", unpinned_images, True),
        ("a bare image name is caught", "      image: postgres\n", unpinned_images, True),
        ("an expression image is reported", "      image: ${{ matrix.image }}\n", unpinned_images, True),
        # The matrix VALUE form must not be read as an image ref, or every
        # workflow iterating image names reds and the check gets switched off.
        ("a matrix list item is not an image ref", "          - open-computer-use\n", unpinned_images, False),
        # The block-scoped read is the whole point of rule 3: build.yml has nine
        # checkouts and one flag, so a file-scoped search would have vouched for
        # all nine on the strength of the ninth.
        (
            "a guarded checkout passes",
            "      - uses: actions/checkout@x\n        with:\n          persist-credentials: false\n",
            persisting_checkouts,
            False,
        ),
        (
            "an unguarded checkout is caught",
            "      - uses: actions/checkout@x\n        with:\n          fetch-depth: 0\n",
            persisting_checkouts,
            True,
        ),
        (
            "a checkout with no `with:` at all is caught",
            "      - uses: actions/checkout@x\n      - run: echo\n",
            persisting_checkouts,
            True,
        ),
        (
            "a flag on a LATER step does not vouch for an earlier checkout",
            "      - uses: actions/checkout@x\n      - uses: actions/checkout@y\n"
            "        with:\n          persist-credentials: false\n",
            persisting_checkouts,
            True,
        ),
    ]
    failures = 0
    for name, text, fn, want_bad in cases:
        got_bad = bool(fn(text))
        ok = got_bad == want_bad
        failures += 0 if ok else 1
        print(f"  {'ok' if ok else 'FAIL'}: {name}")
    print()
    if failures:
        print(f"self-test: {failures} case(s) failed")
        return 1
    print("self-test: the check catches a movable ref in each shape and passes an immutable one.")
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
        print("::error::no workflow files found -- the check scanned nothing", file=sys.stderr)
        return 2

    if findings:
        for path, problems in findings.items():
            for problem in problems:
                print(f"::error file={path}::unpinned: {problem}", file=sys.stderr)
        print(
            f"::error::NFR-SEC-18: {sum(len(v) for v in findings.values())} unpinned "
            f"ref(s) across {len(findings)} file(s). A tag is a pointer its publisher "
            "can move after review; a digest is the artifact.",
            file=sys.stderr,
        )
        return 1

    print(f"NFR-SEC-18 holds: every uses: and image: across {scanned} workflow file(s) names an immutable ref.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
