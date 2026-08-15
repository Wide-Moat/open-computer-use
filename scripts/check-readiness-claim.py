#!/usr/bin/env python3
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""Answer the deployment-readiness claim by measuring it, not by asserting it.

The claim has four legs — proven isolation, an auditable supply chain, a
canon where every decision is recorded and checkable. Each leg has been built
and each has its own gate. What did not exist until this script is a single
place that asks whether they all hold AT ONCE, against what is actually
shipped.

That distinction is the whole point. A leg living in an unmerged pull request is
not a property of the system; it is a property of a branch. This script reads
the DEFAULT branch of each component, so a leg counts only once it is merged —
so the number moves only when work merges.

    python3 scripts/check-readiness-claim.py            # human summary
    python3 scripts/check-readiness-claim.py --json     # machine-readable

Exit 0 when every leg holds on the shipped branches, 1 when any does not,
2 when a component cannot be read — unreadable is not the same as unmet, and
reporting it as unmet would be the same defect this script exists to catch.

The three-way split is what makes the visibility of the components a
non-question. Reading a sibling works today because those repositories are
public; if one became private, or a token lost access, the affected leg reports
as unreadable and the run exits 2. Verified by pointing a leg at a repository
this token cannot see: the result is "cannot read <leg>", not "<leg> does not
hold". A compliance check that answered "the property is missing" when it merely
could not look would be worse than no check.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time

# WHAT THIS PROVES, AND WHAT IT DOES NOT. Symbol presence establishes that the
# leg's code is on the shipping branch. It does not establish that the code runs,
# that its gate is green, or that a later commit did not neuter it. The error
# directions are not symmetric, which is what makes the proxy usable: a rename
# yields a false NOT-YET (safe — it understates), while dead code or a reverted
# call site would yield a false HOLDS (unsafe — it overstates). The call-site
# evidence below narrows the unsafe direction; it does not close it.
#
# Each leg names the component, the branch that ships it, and TWO pieces of
# evidence: the function that decides the property, and the call that puts it on
# the path a session actually takes. Both, because the first alone overstates.
#
# That is not a hypothetical. E1's first version had the verdict function, the
# tests, and no production caller at all — the property held on the CI runner and
# nowhere else, and a check looking only for `func AdmitUIDMap` would have called
# the leg shipped. A symbol rather than a file for the usual reason: files move,
# and a grep for a path that no longer exists reports a missing property when
# what moved was a file.
# The sequence the delivering PRs must land in. Declared rather than derived:
# the canon gate reds on its own citations without E1's work, so an order that
# lands it first proves nothing -- and no ordering available from the data
# reproduces this one reliably. --compose checks this covers exactly the legs.
MERGE_ORDER = (115, 116, 117, 118)

LEGS = (
    {
        "leg": "proven isolation",
        "delivered_by": 115,
        "repo": "Wide-Moat/ocu-sandbox",
        "branch": "main",
        "evidence": "func AdmitUIDMap",
        "path": "host/exec/runtime/userns.go",
        "wired": "m.admitUserns(ctx",
        "wired_path": "host/exec/manager/manager.go",
        "means": (
            "the control plane refuses a session whose container root is host "
            "root, judged on the mapping the kernel reports"
        ),
    },
    {
        "leg": "auditable supply chain",
        "delivered_by": 118,
        "repo": "Wide-Moat/ocu-sandbox",
        "branch": "main",
        "evidence": "func AdmitImageRef",
        "path": "host/exec/manager/imageref.go",
        "wired": "AdmitImageRef(spec.Image)",
        "wired_path": "host/exec/manager/manager.go",
        "means": (
            "a session cannot start from a re-pointable image tag"
        ),
    },
    {
        "leg": "verified release path",
        "delivered_by": 116,
        "repo": "Wide-Moat/ocu-sandbox",
        "branch": "main",
        "evidence": "certificate-identity-regexp",
        "path": ".github/workflows/ghcr-guest.yml",
        "means": (
            "the release path verifies its own signature against a pinned "
            "identity before applying consumer tags"
        ),
    },
    {
        "leg": "checkable canon",
        "delivered_by": 117,
        "repo": "Wide-Moat/ocu-sandbox",
        "branch": "main",
        "evidence": "func TestEveryDecisionNamesAGuardThatExists",
        "path": "host/internal/doctruth/decision_guards_test.go",
        # A test needs no call site: `go test ./...` is its caller, and the go
        # job runs it as a required context. Naming a second symbol here would
        # be ceremony rather than evidence.
        "wired": None,
        "wired_path": None,
        "means": (
            "every recorded decision names a guard test, and every named guard "
            "is verified to exist"
        ),
    },
)


class Unreadable(Exception):
    """A component could not be read. Distinct from a leg that does not hold."""


def _run(args: list[str], cwd: str | None = None) -> tuple[int, str, str]:
    for attempt in range(3):
        proc = subprocess.run(
            args, capture_output=True, text=True, timeout=300, cwd=cwd
        )
        if proc.returncode == 0:
            return 0, proc.stdout, proc.stderr
        transient = any(
            m in proc.stderr.lower()
            for m in ("timeout", "connection reset", "temporary failure", "eof")
        )
        if not transient or attempt == 2:
            return proc.returncode, proc.stdout, proc.stderr
        time.sleep(2 * (attempt + 1))
    return proc.returncode, proc.stdout, proc.stderr


def leg_holds(leg: dict) -> bool:
    """Report whether the evidence symbol is present on the shipping branch.

    Reads the remote ref rather than a local checkout: a local branch can carry
    work that was never pushed, and the question is what the component ships.
    """
    code, out, err = _run(
        [
            "gh",
            "api",
            f"repos/{leg['repo']}/contents/{leg['path']}?ref={leg['branch']}",
            "--jq",
            ".content",
        ]
    )
    if code != 0:
        if "404" in err or "Not Found" in err:
            # A 404 covers BOTH "the file is absent on that branch" and "the
            # repository or branch does not exist" — and those are different
            # answers. Confirm the branch itself resolves before calling the leg
            # unmet, or a typo in a repo name reports a security property as
            # missing. Measured: a nonexistent repo returned False before this.
            probe, _, perr = _run(
                ["gh", "api", f"repos/{leg['repo']}/branches/{leg['branch']}"]
            )
            if probe != 0:
                raise Unreadable(
                    f"{leg['repo']}@{leg['branch']} does not resolve: "
                    f"{perr.strip()[:100]}"
                )
            # The branch exists and the file does not: the leg genuinely does
            # not hold there.
            return False
        raise Unreadable(f"{leg['repo']}@{leg['branch']}: {err.strip()[:120]}")

    if leg["evidence"] not in _fetch(leg, leg["path"], out):
        return False

    # The call site, when the leg has one. Declaring these fields and never
    # reading them would repeat the defect this evidence exists to catch: a
    # verdict function present, tested, and called from nowhere.
    if not leg.get("wired"):
        return True
    code2, out2, err2 = _run(
        [
            "gh",
            "api",
            f"repos/{leg['repo']}/contents/{leg['wired_path']}?ref={leg['branch']}",
            "--jq",
            ".content",
        ]
    )
    if code2 != 0:
        if "404" in err2 or "Not Found" in err2:
            return False
        raise Unreadable(f"{leg['repo']}@{leg['branch']}: {err2.strip()[:120]}")
    return leg["wired"] in _fetch(leg, leg["wired_path"], out2)


def _fetch(leg: dict, path: str, encoded: str) -> str:
    import base64

    try:
        return base64.b64decode(encoded).decode("utf-8", "replace")
    except Exception as exc:  # pragma: no cover - defensive
        raise Unreadable(f"{leg['repo']}:{path}: undecodable content: {exc}") from exc


def delivery_intact(leg: dict) -> bool | None:
    """Does the PR named in `delivered_by` still carry this leg's evidence?

    A leg that does not hold on the shipping branch is expected while its PR is
    open. What is NOT expected is the delivery path silently emptying: a rebase
    that drops the call site, a branch renamed out from under the claim, a PR
    closed without merging. All of those leave the readiness line reading
    "NOT YET" — identical to healthy work in progress — so the regression hides
    behind the expected state.

    Returns True when the PR still carries both markers, False when it does not,
    and None when the answer cannot be read (no token, network, PR gone). None is
    not False: an unreadable delivery path is reported as unreadable, because
    treating "could not look" as "broken" would cry wolf on every offline run.
    """
    pr = leg.get("delivered_by")
    if not pr:
        return None
    try:
        return _delivery_intact(leg, pr)
    except (subprocess.SubprocessError, Unreadable, OSError, ValueError):
        # Containment, not laziness. This function is a REPORT decoration on a
        # verdict main() has already reached. Letting it raise would delete the
        # whole readiness report -- including the HOLDS/NOT YET lines that are
        # the reason the step runs at all -- and the caller in CI appends
        # `|| true`, so the deletion would be silent. Degrade to unreadable.
        return None


def _delivery_intact(leg: dict, pr: int) -> bool | None:
    code, out, _ = _run(
        ["gh", "pr", "view", str(pr), "--repo", leg["repo"],
         "--json", "headRefName,state", "--jq", ".headRefName + \" \" + .state"]
    )
    if code != 0 or not out.strip():
        return None
    parts = out.strip().split()
    if len(parts) != 2:
        return None
    ref, state = parts
    if state != "OPEN":
        return False
    for symbol, path in ((leg["evidence"], leg["path"]),
                         (leg.get("wired"), leg.get("wired_path"))):
        if not symbol:
            continue
        code2, out2, _err2 = _run(
            ["gh", "api", f"repos/{leg['repo']}/contents/{path}?ref={ref}",
             "--jq", ".content"]
        )
        if code2 != 0:
            # A 404 means the path is genuinely gone from that branch. Anything
            # else (transport, auth, rate limit) is a failure to look, and the
            # docstring promises None for those -- reporting BROKEN on a network
            # blip is the cry-wolf direction.
            if "404" in _err2 or "Not Found" in _err2:
                return False
            return None
        if symbol not in _fetch(leg, path, out2):
            return False
    return True


def _self_test() -> int:
    """Drive main() over a stubbed _run for every delivery outcome.

    Through main(), not delivery_intact alone. The verdict function being right
    is not the property that matters -- the property is that the REPORT a reader
    sees says the right thing, and that a failure inside the decoration cannot
    take the report with it. A self-test that drove only the function would have
    passed while the live script died on a slow API call and printed nothing.
    """
    import base64
    import io as _io
    import contextlib

    global _run
    real_run = _run
    failures = []

    def stub(script):
        def _stub(args):
            return script(args)
        return _stub

    _ALL_SYMBOLS = (
        "func AdmitUIDMap\nm.admitUserns(ctx\nfunc AdmitImageRef\n"
        "AdmitImageRef(spec.Image)\nfunc TestEveryDecisionNamesAGuardThatExists\n"
    )

    def encoded(text):
        return 0, base64.b64encode(text.encode()).decode(), ""

    # Every case pins main()'s printed report AND its exit code.
    cases = []

    def carries(args):
        # main branch never has the symbol -> every leg NOT YET; the PR does.
        if args[:2] == ["gh", "pr"]:
            return 0, "some-branch OPEN", ""
        ref = next((a for a in args if "ref=" in a), "")
        if "ref=main" in ref:
            return encoded("package x\n")
        return encoded(_ALL_SYMBOLS)
    cases.append(("intact", carries, "is open and still carries", 1))

    def closed(args):
        if args[:2] == ["gh", "pr"]:
            return 0, "some-branch MERGED", ""
        return encoded("package x\n")
    cases.append(("closed PR", closed, "DELIVERY BROKEN", 1))

    def rebased_away(args):
        if args[:2] == ["gh", "pr"]:
            return 0, "some-branch OPEN", ""
        return encoded("package x\n")  # PR open but symbol gone
    cases.append(("rebased away", rebased_away, "DELIVERY BROKEN", 1))

    def unreadable(args):
        if args[:2] == ["gh", "pr"]:
            return 1, "", "could not connect"
        return encoded("package x\n")
    cases.append(("unreadable PR", unreadable, "could not be read", 1))

    def hangs(args):
        # THE REGRESSION: a slow API call must not delete the report.
        if args[:2] == ["gh", "pr"]:
            raise subprocess.TimeoutExpired(cmd=args, timeout=60)
        return encoded("package x\n")
    cases.append(("timeout mid-report", hangs, "could not be read", 1))

    def net_fail_contents(args):
        # Transport failure fetching the PR's file: unreadable, never BROKEN.
        if args[:2] == ["gh", "pr"]:
            return 0, "some-branch OPEN", ""
        ref = next((a for a in args if "ref=" in a), "")
        if "ref=main" in ref:
            return encoded("package x\n")
        return 1, "", "server error: 502 bad gateway"
    cases.append(("contents transport failure", net_fail_contents, "could not be read", 1))

    # The three cases below each isolate ONE check. Earlier stubs withheld BOTH
    # symbols at once, so a BROKEN verdict could arrive by either path and the
    # individual gates were decoration: dropping the state check, the wired
    # check, or the 404 branch each left every case green.
    def merged_but_carries(args):
        # State gate alone: the branch still has both symbols, only the PR died.
        if args[:2] == ["gh", "pr"]:
            return 0, "some-branch MERGED", ""
        ref = next((a for a in args if "ref=" in a), "")
        if "ref=main" in ref:
            return encoded("package x\n")
        return encoded(_ALL_SYMBOLS)
    cases.append(("merged PR whose branch still carries", merged_but_carries,
                  "DELIVERY BROKEN", 1))

    def wired_dropped(args):
        # Wired-symbol check alone: the verdict function is there, the call is not.
        if args[:2] == ["gh", "pr"]:
            return 0, "some-branch OPEN", ""
        ref = next((a for a in args if "ref=" in a), "")
        if "ref=main" in ref:
            return encoded("package x\n")
        path = next((a for a in args if "contents/" in a), "")
        if "manager.go" in path:
            return encoded("package x\n")  # call site rebased away
        return encoded(_ALL_SYMBOLS)
    cases.append(("call site dropped, verdict kept", wired_dropped,
                  "DELIVERY BROKEN", 1))

    def contents_gone(args):
        # 404 branch alone: the PR is open, the FILE is gone from the branch.
        if args[:2] == ["gh", "pr"]:
            return 0, "some-branch OPEN", ""
        ref = next((a for a in args if "ref=" in a), "")
        if "ref=main" in ref:
            return encoded("package x\n")
        return 1, "", "gh: Not Found (HTTP 404)"
    cases.append(("contents 404 on the PR branch", contents_gone,
                  "DELIVERY BROKEN", 1))

    for label, script, expect, want_exit in cases:
        _run = stub(script)
        buf = _io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                code = main([])
        except BaseException as exc:  # noqa: BLE001 - a crash IS the finding
            failures.append(f"{label}: main() raised {type(exc).__name__}: {exc}")
            continue
        finally:
            _run = real_run
        out = buf.getvalue()
        if not out.strip():
            failures.append(f"{label}: main() printed NOTHING (report deleted)")
            continue
        if expect not in out:
            failures.append(f"{label}: report missing {expect!r}")
        if code != want_exit:
            failures.append(f"{label}: exit {code}, want {want_exit}")

    # A BROKEN delivery must never be reported as intact.
    _run = stub(closed)
    buf = _io.StringIO()
    with contextlib.redirect_stdout(buf):
        main([])
    _run = real_run
    if "is open and still carries" in buf.getvalue():
        failures.append("closed PR reported as intact")

    # composed_verdict, which otherwise nothing in CI exercises. Real git, no
    # network: a throwaway repo whose branches carry or omit the leg symbols.
    import subprocess as _sp
    import tempfile as _tf

    with _tf.TemporaryDirectory() as d:
        def git(*a):
            _sp.run(["git", "-C", d, *a], capture_output=True, text=True, check=False)

        leg = LEGS[0]
        git("init", "-q", "-b", "main")
        git("config", "user.email", "t@example.invalid")
        git("config", "user.name", "t")
        _io.open(f"{d}/seed", "w", encoding="utf-8").write("seed\n")
        git("add", "-A")
        git("commit", "-qm", "seed")
        # A doctruth-shaped module, so the compose cases actually RUN the gate.
        # Without it every case takes the "gate is not present" path and the
        # gate-running behaviour is bound by nothing -- measured: deleting the
        # whole block left this suite green.
        import os as _os
        _os.makedirs(f"{d}/host/internal/doctruth", exist_ok=True)
        _io.open(f"{d}/host/go.mod", "w", encoding="utf-8").write("module x\n\ngo 1.21\n")
        # A buildable package: the build check runs before the gate, and a module
        # with nothing to compile is not a useful stand-in for the real tree.
        _io.open(f"{d}/host/internal/doctruth/doctruth.go", "w", encoding="utf-8").write(
            "package doctruth\n"
        )
        _io.open(f"{d}/host/internal/doctruth/guard_test.go", "w", encoding="utf-8").write(
            "package doctruth\n\n"
            "import (\n\t\"os\"\n\t\"testing\"\n)\n\n"
            "func TestEveryDecisionNamesAGuardThatExists(t *testing.T) {\n"
            "\tif _, err := os.Stat(\"../../../poison\"); err == nil {\n"
            "\t\tt.Fatal(\"a decision names a guard that does not exist\")\n"
            "\t}\n}\n"
        )
        git("add", "-A")
        git("commit", "-qm", "the gate")
        # The gate lives on main: composed_verdict starts its scratch worktree at
        # origin/main, so anything the build or gate needs must be on the base,
        # not only on the branches being merged.
        git("checkout", "-q", "-b", "carries")
        for path, symbol in ((leg["path"], leg["evidence"]),
                             (leg["wired_path"], leg["wired"])):
            import os as _os
            _os.makedirs(_os.path.dirname(f"{d}/{path}"), exist_ok=True)
            # Valid Go, not a bare symbol: the build check runs on this tree, and
            # a file containing only an identifier is not a package. The fixture
            # has to be buildable for the gate case to mean anything.
            pkg = _os.path.basename(_os.path.dirname(path))
            _io.open(f"{d}/{path}", "w", encoding="utf-8").write(
                f"package {pkg}\n\n// {symbol}\n"
            )
        git("add", "-A")
        git("commit", "-qm", "carries the leg")
        git("checkout", "-q", "-b", "poisoned")
        _io.open(f"{d}/poison", "w", encoding="utf-8").write("x\n")
        git("add", "-A")
        git("commit", "-qm", "carries the leg and reds the gate")
        git("checkout", "-q", "main")

        compose_cases = [
            ("a branch carrying the leg makes it hold", ["carries"], 1),
            ("a branch without it does not", ["main"], 0),
            # -2 is "rejected", distinct from 0 legs holding: the legs were
            # present, the gate refused the tree.
            ("a branch that reds the gate is rejected", ["poisoned"], -2),
            ("a directory that is not a worktree refuses", None, -1),
            # Bound on the DIAGNOSIS, not the verdict: without the guard a merge
            # into a missing directory fails anyway, so the refusal alone is
            # non-discriminating. What the guard buys is not blaming a conflict.
        ]
        for label, branches, want in compose_cases:
            if branches is None:
                held, notes = composed_verdict("/nonexistent-xyz", ["carries"])
                if "not a git worktree" not in " ".join(notes):
                    failures.append(
                        "a missing directory is blamed on a merge conflict: "
                        + " ".join(notes)[:60]
                    )
            else:
                # A fresh clone per case: composed_verdict MERGES, so reusing one
                # tree lets an earlier case's merge satisfy a later one -- the
                # "does not" case passed only because a previous merge left the
                # symbols behind.
                # A fresh clone per case: composed_verdict merges, so reusing
                # one tree lets an earlier case satisfy a later one. Keep the
                # clone alive for the whole call -- composed_verdict adds its
                # own scratch worktree inside it and needs the parent to exist.
                w = _tf.mkdtemp(prefix="ocu-case-")
                _sp.run(["git", "clone", "-q", d, w], capture_output=True, check=False)
                _sp.run(["git", "-C", w, "checkout", "-q", "main"],
                        capture_output=True, check=False)
                held, _ = composed_verdict(w, [f"origin/{b}" for b in branches])

            got = held if held < 0 else (1 if held >= 1 else 0)
            if got != want:
                failures.append(f"{label}: held={held}, want {want}")
            else:
                print(f"  ok: {label}")

    # MERGE_ORDER must cover exactly the legs. A leg missing from the sequence
    # composes without its PR and the verdict is confidently wrong.
    declared = set(MERGE_ORDER)
    from_legs = {leg["delivered_by"] for leg in LEGS if leg.get("delivered_by")}
    if declared != from_legs:
        failures.append(
            f"MERGE_ORDER {sorted(declared)} does not cover the legs "
            f"{sorted(from_legs)}"
        )
    else:
        print("  ok: MERGE_ORDER covers exactly the delivering PRs")

    for f in failures:
        print(f"FAIL {f}")
    if failures:
        print(f"\n{len(failures)} self-test failure(s)")
        return 1
    print(f"delivery reporting: {len(cases)} cases through main(), all as specified")
    return 0


def composed_verdict(repo_dir: str, branches: list[str]) -> tuple[int, list[str]]:
    """Merge the delivering branches in order and re-run every leg on the result.

    The legs live in PRs that fork from a common base rather than nesting, so
    "each PR is green" does not establish that the three properties hold
    TOGETHER. Nothing else answers that: the shipped checker reads the shipping
    branch, and the shipping branch has none of them yet.

    A conflict or a missing symbol is a real answer -- it means the sequence
    does not deliver what it claims.
    """
    notes = []
    # Compose in a THROWAWAY worktree, never the caller's tree. Pointed at a
    # working repo the merges land on whatever branch is checked out, and a
    # conflict leaves it mid-merge with MERGE_HEAD set -- a check that damages
    # the repo it inspects is worse than no check.
    # Refuse a directory that is not a git worktree BEFORE attempting a merge.
    # Otherwise every failure -- missing directory, wrong path, not a repo --
    # reports "does not merge cleanly", sending the reader to hunt a conflict
    # that does not exist.
    code, out, _ = _run(["git", "-C", repo_dir, "rev-parse", "--is-inside-work-tree"])
    if code != 0 or out.strip() != "true":
        return -1, [f"{repo_dir} is not a git worktree"]

    import tempfile

    scratch = tempfile.mkdtemp(prefix="ocu-compose-")
    work = f"{scratch}/tree"
    # Fetch BEFORE composing: worktree add --detach starts at the caller's HEAD,
    # and nothing here refreshes the remote. Measured -- composing from a base 40
    # commits stale reported 4 of 4, describing a merge that will never happen.
    code, _, err = _run(["git", "-C", repo_dir, "fetch", "-q", "origin"])
    if code != 0:
        return -1, [f"cannot fetch origin in {repo_dir}: {err.strip()[:80]}"]
    code, _, err = _run(
        ["git", "-C", repo_dir, "worktree", "add", "-q", "--detach", work, "origin/main"]
    )
    if code != 0:
        return -1, [f"cannot create a scratch worktree in {repo_dir}: {err.strip()[:80]}"]
    base_code, base, _ = _run(["git", "-C", work, "rev-parse", "--short", "HEAD"])
    notes.append(f"composed from origin/main at {base.strip() if base_code == 0 else '?'}")
    try:
        return _compose_in(repo_dir, work, branches, notes)
    finally:
        _run(["git", "-C", repo_dir, "worktree", "remove", "--force", work])


def _compose_in(
    origin_dir: str, repo_dir: str, branches: list[str], notes: list[str]
) -> tuple[int, list[str]]:
    for branch in branches:
        # Resolve first: an unfetched or deleted ref is an UNREADABLE input, not
        # a broken composition, and reporting it as "does not merge cleanly"
        # blames the branches for the caller's stale remote.
        code, _, _ = _run(["git", "-C", repo_dir, "rev-parse", "--verify", f"{branch}^{{commit}}"])
        if code != 0:
            notes.append(f"{branch} does not resolve -- fetch, or it was deleted")
            return -1, notes
        code, out, err = _run(["git", "-C", repo_dir, "merge", "-q", "--no-edit", branch])
        if code != 0:
            notes.append(f"{branch} does not merge cleanly: {(out + err).strip()[:80]}")
            return 0, notes
        notes.append(f"merged {branch}")

    held = 0
    for leg in LEGS:
        pairs = [(leg["evidence"], leg["path"])]
        if leg.get("wired"):
            pairs.append((leg["wired"], leg["wired_path"]))
        ok = True
        for symbol, path in pairs:
            code, out, _ = _run(["git", "-C", repo_dir, "show", f"HEAD:{path}"])
            if code != 0 or symbol not in out:
                ok = False
                break
        held += ok
        notes.append(f"{'PRESENT' if ok else 'ABSENT '} {leg['leg']}")

    # Symbol presence is not the property. A decision citing a guard that does
    # not exist leaves every symbol in place and reds the canon gate, so a tree
    # can report every leg present while the gate that proves one of them
    # fails. Run it.
    import os

    # Build both modules first. host/ and host/exec/ are separate modules, so
    # the canon gate never compiles manager.go -- the file BOTH #115 and #118
    # edit, where both wired symbols live. A textually clean but semantically
    # broken merge would otherwise pass with every symbol PRESENT.
    for module in ("host", "host/exec"):
        mod_dir = f"{repo_dir}/{module}"
        if not os.path.isfile(f"{mod_dir}/go.mod"):
            continue
        code, out, err = _run(["go", "build", "./..."], cwd=mod_dir)
        if code != 0:
            notes.append(f"{module} does not build on the composed tree: {(out + err).strip()[:120]}")
            return -2, notes
        notes.append(f"{module} builds on the composed tree")

    gate_dir = f"{repo_dir}/host"
    if not os.path.isdir(f"{gate_dir}/internal/doctruth"):
        # The composed tree does not carry the gate. Say so rather than
        # reporting a pass for a test that never ran -- and rather than
        # crashing on a cwd that does not exist.
        notes.append("canon gate is not present on the composed tree")
        return held, notes
    code, out, err = _run(
        ["go", "test", "./internal/doctruth/...",
         "-run", "TestEveryDecisionNamesAGuardThatExists"],
        cwd=gate_dir,
    )
    if code != 0:
        notes.append(f"canon gate FAILS on the composed tree: {(out + err).strip()[:120]}")
        # -2: rejected, not "0 legs hold". Four PRESENT lines above a 0 count
        # contradict each other; the composition is refused, not measured.
        return -2, notes
    notes.append("canon gate passes on the composed tree")
    return held, notes


def main(argv: list[str] | None = None) -> int:
    # Explicit argv, because _self_test drives main() while sys.argv still says
    # --self-test. Re-parsing the process argv there sent main() straight back
    # into the self-test: infinite recursion that appeared only as a subprocess,
    # since an in-process caller has a clean sys.argv.
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument(
        "--compose",
        metavar="DIR",
        help="a checkout to merge the delivering branches into, then re-run "
        "every leg against the result: symbol presence plus the canon gate",
    )
    ap.add_argument(
        "--self-test",
        action="store_true",
        help="drive the report over constructed delivery outcomes and exit",
    )
    args = ap.parse_args(argv)
    if getattr(args, "self_test", False):
        return _self_test()

    if args.compose:
        # Derive the sequence from the legs rather than duplicating it: a leg
        # whose PR is missing from a hand-kept tuple composes silently without
        # it, which is how the release-path property went untracked.
        # MERGE_ORDER, declared. Neither available ordering is trustworthy:
        # LEGS order gives 115,118,116,117 -- the legs are listed by property,
        # not by dependency -- and PR number only happens to match today because
        # these were opened in dependency order. Deriving the SET from the legs
        # keeps a leg from composing silently without its PR; the ORDER has to
        # be stated, and is checked against that set below.
        declared = list(MERGE_ORDER)
        from_legs = {leg["delivered_by"] for leg in LEGS if leg.get("delivered_by")}
        if set(declared) != from_legs:
            missing = from_legs - set(declared)
            extra = set(declared) - from_legs
            print(
                f"  MERGE_ORDER does not cover the legs: missing {sorted(missing)}, "
                f"unknown {sorted(extra)}"
            )
            return 2
        branches = []
        for pr in declared:
            code, out, _ = _run(
                ["gh", "pr", "view", str(pr), "--repo", LEGS[0]["repo"],
                 "--json", "headRefName", "--jq", ".headRefName"]
            )
            if code != 0 or not out.strip():
                print(f"  cannot resolve the head branch of #{pr}")
                return 2
            branches.append(f"origin/{out.strip()}")
        held, notes = composed_verdict(args.compose, branches)
        for n in notes:
            print(f"  {n}")
        if held == -2:
            print("\ncomposition rejected: the canon gate is red on the composed tree")
            return 1
        if held < 0:
            # Unreadable, not unmet. The distinction is the one this script's
            # header calls the defect it exists to catch.
            print("\ncannot judge the composition: a delivering branch is unreadable")
            return 2
        print(f"\n{held} of {len(LEGS)} legs hold on the composed tree")
        return 0 if held == len(LEGS) else 1

    results = []
    for leg in LEGS:
        try:
            holds = leg_holds(leg)
        except Unreadable as exc:
            print(f"cannot read {leg['leg']}: {exc}", file=sys.stderr)
            return 2
        intact = None if holds else delivery_intact(leg)
        results.append({**leg, "holds": holds, "delivery_intact": intact})

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            mark = "HOLDS    " if r["holds"] else "NOT YET  "
            print(f"  {mark} {r['leg']}")
            print(f"            {r['means']}")
            print(f"            evidence: {r['evidence']} on {r['repo']}@{r['branch']}")
            if not r["holds"] and r.get("delivered_by"):
                intact = r.get("delivery_intact")
                if intact is True:
                    print(
                        f"            delivery: #{r['delivered_by']} is open and "
                        "still carries this leg"
                    )
                elif intact is False:
                    print(
                        f"            DELIVERY BROKEN: #{r['delivered_by']} no "
                        "longer carries this leg (closed, renamed, or rebased "
                        "away) -- the path to shipping it is gone, not pending"
                    )
                else:
                    print(
                        f"            delivery: #{r['delivered_by']} could not "
                        "be read from here"
                    )
        held = sum(1 for r in results if r["holds"])
        print()
        if held == len(results):
            print(
                "The deployment-readiness claim holds on the shipped branches: "
                "every leg is merged. Whether each gate is GREEN is a separate question this script does not ask."
            )
        else:
            print(
                f"The claim does NOT hold yet: {held} of {len(results)} legs are "
                "merged. The rest are built and gated but live in open pull "
                "requests, so they are properties of a branch rather than of "
                "the system."
            )

    return 0 if all(r["holds"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
