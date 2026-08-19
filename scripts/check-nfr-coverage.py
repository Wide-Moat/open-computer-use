#!/usr/bin/env python3
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""Report how many NFRs are checked by something that runs, not by prose.

An NFR is a claim. A claim nobody executes is a claim the reader has to take on
trust, and this repository's own rule is that a property measured only when
somebody remembers to ask is not enforced. NFR-SEC-89 says that about security
gates; the same sentence applies one level up, to the requirements themselves.

Measured when this was written: of 188 NFR ids in the manifesto, exactly ONE --
NFR-SEC-89 -- is named by any script or workflow. The other 187 exist as table
rows. That is not a defect to fix in one commit; it is the state of the layer,
and the point of this check is that the number appears on every run instead of
being rediscovered by whoever next goes looking.

The check is deliberately narrow. "Armed" means a script or workflow NAMES the
id. It does not claim the named check PROVES the requirement -- no lint can
judge that, and pretending otherwise would make this the same kind of decorative
assertion it exists to count. What it removes is the cheaper failure: believing
the set is measured when almost none of it is.

    check-nfr-coverage.py [--repo-root .] [--min-armed N] [--self-test]

Why the number stops where it does. Twenty rows state a CI-gate verification;
eleven are armed, and each of the remaining nine is blocked by something a
commit cannot supply:

    NFR-SEC-12    component 06-egress-trust-edge is status:draft, contract:null
    NFR-SEC-37    needs observed traffic between running components
    NFR-IC-05     the contract itself says carrier: none (gateway behaviour,
                  not a wire field) -- there is no artifact to check
    NFR-MAINT-07  no ORM, no migrations, no SQL exists in the tree yet
    NFR-MAINT-08  drift detection needs a running deployment
    NFR-MAINT-10  patch coverage needs a threshold decision, and the Python
                  surface here is PoC code rather than next/v1 architecture
    NFR-MAINT-11  needs the parsers and schedulers the components will bring
    NFR-PERF-13   needs a green baseline to regress against
    NFR-FLEX-03   needs an IdP integration to be portable across
    NFR-COST-05   needs session accounting that does not exist
    NFR-COMP-25   marked REVISIT, non-gating
    NFR-SEC-57    the egress tripwire does not exist in the tree -- grep for
                  it across computer-use-server/ and helm/ returns nothing
    NFR-SEC-83    frame-ancestors and X-Frame-Options are on no response;
                  every response.headers assignment in app.py is Cache-Control
                  (#498). A gate before the header exists reds every PR for a
                  condition no PR can fix
    NFR-SEC-86    the artifact-body render substrate does not exist yet

That accounts for every id whose verification names a CI gate THIS repository
could run today. It does not account for the rest, and the earlier claim here
-- that the remainder are "declarations rather than checkable properties" --
was wrong. Grouping the unaccounted rows by their verification column returns
named mechanisms: "per-release" 18 times, "release pipeline" 9, "k6 perf gate"
7, "integration test" 7, "chaos test" 4.

Most are unarmed for one reason rather than individually: the mechanism does
not exist. Grepping .github/workflows/, scripts/ and tests/ for k6, chaos and
replay-test finds them only inside this file -- that is, only in the sentence
describing their absence. They are excused by MECHANISM below, and the excuse
expires the moment the mechanism lands: a k6 job in the tree makes every
k6-verified row a real gap again.

"per-release" was on that list and should not have been. The exemption rested
on a spelling -- mechanism_is_absent() searched for the literal string, which
no workflow contains -- while the release pipeline it names plainly exists:
release.yml, gate3-rehearsal.yml, cosign, syft. Arming NFR-COMP-22 through that
very pipeline is what exposed it; a requirement cannot be excused for want of a
mechanism and armed by that mechanism on the same day. Removing the key raised
the honest count from 31 to 51.

Ten of those twenty came back under reasons that hold: fifteen are regulatory
record-keeping with no artefact here (retention windows, the DORA Register of
Information, the sub-processor list), and five carry the manifesto's own
[REVISIT — non-gating] marker, which is the document declaring they do not
gate. Read from the row rather than listed, so both expire on their own.

That list is the answer to "why not more", and it is here rather than in a
commit message so the next person reads it before re-deriving it.

--min-armed is a RATCHET. It fails when coverage drops below the floor, so an
armed NFR cannot quietly become unarmed -- the number can only go up. It does
not fail for the 187, because failing the build on a state no PR can fix would
make this gate the thing that blocks fixing it.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

# Not `-\d+`: three rows do not end in a bare number -- NFR-FLEX-07a,
# NFR-FLEX-07b (lowercase suffix) and NFR-MAINT-AUDIT-SCHEMA (a word). A
# numeric-only pattern read the
# manifesto as 187 rows when it holds 190, and an arm on any of the three would
# have been invisible to the ratchet: the coverage number would not move and
# nothing would say why.
# The floor, in the file the check lives in. A caller may raise it; a caller
# that passes LESS is refused, because the only legitimate reason for the
# number to fall is that an NFR genuinely stopped being checked -- and that is
# what the coverage comparison already catches, loudly.
COMMITTED_FLOOR = 18

# The unexplained count on the day it was first measured honestly. A ceiling
# rather than a floor: this number must go DOWN, and a commit that raises it is
# adding a requirement nobody accounted for.
UNEXPLAINED_CEILING = 32

NFR_ID = re.compile(r"NFR-[A-Z]+-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*")
MANIFESTO = "docs/architecture/manifesto/02-nfrs.md"
# Where an executable check can live. Docs are excluded on purpose: an id named
# in prose is the thing this script measures the absence of.
#
# `tests` is here because that is where some checks actually are:
# NFR-SEC-15's stated verification is the /home/assistant volume-size assertion
# in tests/test-docker-image.sh, which build.yml runs and which blocks. Naming
# it anywhere else to satisfy this scanner would put the id away from the
# assertion that answers it.
CODE_DIRS = ("scripts", ".github", "tests")


def declared_ids(root: pathlib.Path) -> set[str]:
    """Every NFR id the manifesto defines as a table row.

    Row-anchored rather than a bare sweep: the manifesto also MENTIONS ids in
    prose and in cross-references, and counting those would inflate the
    denominator with things that were never separate requirements.
    """
    path = root / MANIFESTO
    if not path.is_file():
        return set()
    ids: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.split("|")]
        # cells[0] is the empty string before the leading pipe.
        if len(cells) > 1 and NFR_ID.fullmatch(cells[1]):
            ids.add(cells[1])
    return ids


CANON = "next/v1"


def unreachable_on_canon(root: pathlib.Path, hits: dict[str, list[str]]) -> dict[str, list[str]]:
    """Armed ids whose only naming file cannot run on the canon branch.

    "Named by a check" was the wrong bar on its own. A check that exists in the
    tree but never executes on next/v1 answers for main and nothing else, and
    the ratchet counted it as coverage. Measured when this was written:
    NFR-SEC-15's verification is the /home/assistant volume-size assertion in
    tests/test-docker-image.sh, invoked only by build.yml, whose
    pull_request trigger is `branches: [main]` -- so the id read as armed while
    nothing on canon asserted it.

    Reachability is the same question check-gates-trigger-on-canon.py asks of a
    workflow; here it is asked of the file that carries the assertion.
    """
    import yaml

    workflows = root / ".github" / "workflows"
    fires: dict[str, bool] = {}
    for path in sorted(workflows.glob("*.yml")) + sorted(workflows.glob("*.yaml")):
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            fires[path.name] = False
            continue
        on = doc.get(True) or doc.get("on") or {}
        if not isinstance(on, dict) or "pull_request" not in on:
            fires[path.name] = False
            continue
        pull = on["pull_request"]
        if pull is None:
            fires[path.name] = True
            continue
        branches = pull.get("branches") if isinstance(pull, dict) else None
        fires[path.name] = branches is None or CANON in branches or any(
            "*" in str(b) for b in branches
        )

    bodies = {p.name: p.read_text(encoding="utf-8", errors="ignore")
              for p in list(workflows.glob("*.yml")) + list(workflows.glob("*.yaml"))}

    stranded: dict[str, list[str]] = {}
    for nid, files in sorted(hits.items()):
        reachable = False
        for rel in files:
            if rel.startswith(".github/workflows/"):
                # The workflow must FIRE and must name the id on a line that
                # runs. Firing alone counted a citation buried in a comment:
                # measured, NFR-MAINT-AUDIT-SCHEMA had one comment line in
                # contracts-lint.yml and one source in
                # scripts/apply-layer0-protection.sh, which no workflow invokes
                # -- both dead, and the id read `armed`. NFR-SEC-18 is the same
                # shape in the workflow and survives on check-pin-policy.py,
                # which CI does run.
                name = pathlib.Path(rel).name
                body = bodies.get(name, "")
                # A comment INSIDE a job is the established way to bind an id to
                # a job that carries it -- security.yml says so outright ("Named
                # here so check-nfr-coverage.py counts this requirement as
                # armed"). What does not bind is a citation in the file header,
                # before any job: that is prose about the workflow, not a claim
                # any job makes. Measured: requiring an executable line reported
                # NFR-SEC-07 and NFR-SEC-19 as stranded, and both are carried by
                # blocking jobs whose in-job comments name them.
                in_jobs = body.split("\njobs:", 1)
                scope = in_jobs[1] if len(in_jobs) == 2 else ""
                reachable |= fires.get(name, False) and nid in scope
            else:
                # Everything else -- scripts/ and tests/ alike -- is reachable
                # only if a workflow that FIRES on canon invokes it. This used
                # to shortcut scripts/ to True on the grounds that
                # contracts-lint runs them, which stopped being true when the
                # nfr-gates job moved to its own workflow (#511) and was never
                # true of every file: scripts/apply-layer0-protection.sh is
                # invoked by NO workflow -- it is the manual applier -- yet it
                # is cited as evidence by NFR-SEC-88 and NFR-SEC-89.
                #
                # Not a live fake-green: both also cite a script CI does run,
                # so the verdict is unchanged today. The assumption is what was
                # wrong, and an assumption that happens to hold is the kind
                # this file exists to replace with a measurement.
                # Matched against RUN LINES, not the whole file. A mention in a
                # comment is not an invocation: check-pin-policy.py is named in
                # comments in security.yml and supply-chain.yml, and a
                # substring search over the body counted those as callers --
                # the same text-predicate trap this repository keeps finding.
                reachable |= any(
                    fires.get(w, False)
                    and any(rel in line and not line.lstrip().startswith("#") for line in body.splitlines())
                    for w, body in bodies.items()
                )
        if not reachable:
            stranded[nid] = files
    return stranded


def armed_ids(root: pathlib.Path, ids: set[str]) -> dict[str, list[str]]:
    """Ids named by a file under CODE_DIRS, with the files that name them.

    Reads the working tree rather than a git ref so the check answers for what
    is about to be committed, not for what is already on the branch.
    """
    hits: dict[str, list[str]] = {}
    this_file = pathlib.Path(__file__).resolve()
    for directory in CODE_DIRS:
        base = root / directory
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            # Never count this script. Its self-test fixtures name NFR-SEC-01
            # and NFR-SEC-02, and without this the checker reports them as
            # armed -- by itself. Measured: coverage read 3 of 187 with the two
            # fixtures counted, 1 of 187 without. A gate that satisfies its own
            # assertion is the failure mode this whole file exists to name.
            if path.resolve() == this_file:
                continue
            # Build artifacts are not checks. A .pyc keeps the NFR ids of the
            # source it was compiled from, so a deleted checker stays "armed"
            # as long as its cache survives -- measured on a copy of this tree:
            # delete check-pin-policy.py with __pycache__ present and the
            # ratchet still reads 11. The id is named by a file that no longer
            # runs. A clean checkout has no cache, so this also removes a
            # difference between what CI counts and what a developer counts.
            if "__pycache__" in path.parts or path.suffix in (".pyc", ".pyo"):
                continue
            try:
                body = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for found in set(NFR_ID.findall(body)) & ids:
                hits.setdefault(found, []).append(
                    str(path.relative_to(root))
                )
    return hits


def declared_rows(root: pathlib.Path) -> dict[str, str]:
    """id -> its verification text. declared_ids() returns only the ids, and the
    completeness check needs to know WHAT each row asks for."""
    path = root / MANIFESTO
    if not path.is_file():
        return {}
    rows: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.split("|")]
        if len(cells) > 4 and NFR_ID.fullmatch(cells[1]):
            # The manifesto holds TWO row shapes, and a fixed index reads the
            # wrong column for half of them. Measured: 101 rows are
            # `ID | Scenario | Target | Verification | Source` and 89 insert a
            # threat column -- `ID | Scenario | Threat | Target | Verification |
            # Source`. Taking cells[4:6] for both swept the TARGET into the
            # verification text on the wider rows, and three verdicts turned on
            # it: NFR-SEC-30 counted as CI-checkable because its target says
            # "edge integration test", not its verification.
            #
            # Subject is included deliberately -- the completeness check excuses
            # an id whose SUBJECT is unbuilt, and that word lives in cells[2].
            # Width 8 carries the threat column, width 7 does not. `>= 7` was
            # wrong and measurably so: it matched BOTH shapes, moved 58 rows out
            # of the CI-checkable set in one step, and the first two I read by
            # hand -- NFR-COMP-01, NFR-COMP-11 -- had had their Source column
            # read as their Verification.
            verification = cells[5] if len(cells) >= 8 else cells[4]
            rows[cells[1]] = " ".join([cells[2], verification])
    return rows


EXCUSE_ENTRY = re.compile(r"^\s{4}(NFR-[A-Z]+-[A-Za-z0-9-]+)\s{2,}\S", re.M)
# Verification phrases that name a mechanism CI could carry. The first four
# were the whole list, and they missed most of the manifesto: grouping the
# unaccounted rows by their verification column returned "per-release" 18
# times, "release pipeline" 9, "k6 perf gate" 7, "integration test" 7 and
# "chaos test" 4. Those are named mechanisms, not declarations, and calling
# them declarations let the completeness gate report zero unexplained CI-gated
# ids while 147 rows naming a mechanism sat outside its question.
CI_VERIFICATION = (
    "ci gate",
    "ci lint",
    "lint",
    "script",
    "perf gate",
    "release pipeline",
    "release-pipeline",
    "per-release",
    "integration test",
    "replay test",
    "per-template test",
    "chaos test",
)


def excused_ids(source: str) -> set[str]:
    """Ids the docstring lists as unarmed-and-why.

    Matched on the list's SHAPE -- four spaces, an id, two or more spaces, a
    reason -- not on the id appearing somewhere in the header. A first version
    of this measurement searched the whole docstring and reported NFR-SEC-15 and
    NFR-SEC-89 as stale excuses; both are armed, and both appear in prose
    explaining what the check does. A substring match answers a question nobody
    asked.
    """
    return set(EXCUSE_ENTRY.findall(source))


# Verification mechanisms that do not exist in this repository. An id excused
# by one of these is excused for a reason that is checkable rather than
# asserted: ABSENT_MECHANISM is only honoured while the mechanism is genuinely
# missing, which mechanism_is_absent() re-measures on every run.
# "per-release" is NOT here. It was, and the exemption rested on a spelling:
# mechanism_is_absent() searched for the literal string "per-release", which no
# workflow contains, so 25 ids were excused while the release pipeline they
# refer to plainly exists -- release.yml, gate3-rehearsal.yml, cosign and syft
# all present. Arming NFR-COMP-22 through that very pipeline (#527) is what
# exposed it: a requirement cannot be both excused for want of a mechanism and
# armed by that mechanism on the same day.
ABSENT_MECHANISM = (
    "k6",
    "chaos test",
    "replay test",
    "per-template test",
    # Adversarial evaluation. NFR-SEC-34 asks for a red-team subset per PR and
    # a full suite nightly; NFR-MAINT-12 for a threat-model re-run on
    # DFD-bearing PRs. Measured across .github/, scripts/ and tests/: no
    # promptfoo, garak, pyrit or threagile, and docs/architecture/threat-model/
    # does not exist -- the only hits were path patterns in a docs-lint
    # whitelist, which is a list of files that MAY exist, not a mechanism.
    "per-pr + nightly",
    "threat-model pass",
)

# The second reason an id cannot be armed: the SUBJECT does not exist. A
# requirement about per-tenant isolation cannot have a check while nothing in
# the tree is tenant-aware, and that is a different fact from "the test
# framework is missing". Measured across computer-use-server/ and helm/ when
# this was written -- tenant, trust-edge, broker, spiffe, scim and attestation
# return nothing; egress, idp and sandbox do exist, so requirements about
# those are NOT excused here.
#
# Keyed on a word that appears in the requirement's own subject cell, and
# honoured only while subject_is_absent() still finds nothing. The exemption
# expires when the component lands, which is when the requirement becomes a
# real gap rather than a description of unbuilt work.
ABSENT_SUBJECT = (
    "tenant",
    "trust-edge",
    "broker",
    "spiffe",
    "scim",
    "attestation",
    # Regulatory record-keeping with no artefact in this tree: audit-log
    # retention windows, the DORA Register of Information, the sub-processor
    # list. Dropping the false "per-release" mechanism exemption surfaced 20
    # ids, and 15 of them are these -- obligations discharged by a document
    # somebody publishes, not by code CI can read. Measured: retention,
    # sub-processor, register-of-information and audit-log return nothing
    # across computer-use-server/, helm/ and docs/compliance/.
    "retention",
    "sub-processor",
    "register of information",
    # NFR-REL-08 asks that stateful sandbox hibernation, resume, snapshot and
    # fork be demonstrated end-to-end by an integration test. The test framework
    # is not what is missing -- integration tests exist and run -- so the
    # mechanism probe would not excuse this, correctly. The SUBJECT is missing:
    # no code hibernates, snapshots or forks a sandbox. Keyed on `hibernation`
    # rather than the other three words on purpose. `snapshot` and `fork` both
    # return present, and both hits are COMMENTS about something else: an argv
    # snapshot in a CLI adapter, and routing codex through a gateway "without
    # forking". Keying on either would rest the exemption on a word in a
    # sentence, which is the shape that has produced a false green here before.
    # Hibernation carries the whole row -- without it there is nothing to resume
    # or to fork -- and it returns nothing across every subject directory.
    "hibernation",
    # NFR-SEC-31 puts per-session filesystem-prefix isolation at the storage
    # engine behind `ocu-filestore`: a foreign filesystem_id presented with the
    # same injected credential is rejected 403, a missing or expired token 401.
    # That refusal is the requirement, and it lives in a component that is not
    # in this tree -- ocu-filestore, filestore and storage-jwt all return
    # nothing here.
    #
    # `filesystem_id` DOES return present, which is why this is keyed on the
    # component and not on the field. The hits are real code rather than
    # comments -- init.sh seeds OCU_FILESYSTEM_ID and the link filter carries it
    # into a download scope -- but every one of them is the SENDING side, the
    # value that goes out on a request. Nothing in computer-use-server checks a
    # presented scope against a session's claim; grep for the rejection in
    # security.py and app.py returns nothing. Excusing on `filesystem_id` would
    # therefore rest on code that populates the field the requirement is about
    # somebody else refusing.
    #
    # Deliberately not extended to NFR-SEC-05, which also names ocu-filestore.
    # There the storage leg is one leg of a single forward-proxy egress, and its
    # subject -- proxy, egress -- is present in this tree. It stays unexcused.
    "ocu-filestore",
    # NFR-SEC-84 asks for a CSRF token on state-mutating requests, after an
    # embed-token-verified browser session (NFR-SEC-82). No browser credential
    # exists here: probed for set_cookie / request.cookies / Set-Cookie in
    # server code excluding comments, and found nothing. The word `cookie` does
    # appear twice -- both in COMMENTS, in openwebui/, describing Open WebUI's
    # behaviour rather than this server's -- which is why the probe reads code
    # and the key is `csrf`, the one term genuinely absent.
    "csrf",
)
SUBJECT_DIRS = ("computer-use-server", "helm", "settings-wrapper", "openwebui")

# Deployable files that live at the repository root rather than inside a
# component directory. Without these the probe has a blind spot exactly where
# the sandbox image is defined: measured on NFR-FLEX-08, where every spelling of
# the CA-bundle subject returned ABSENT while Dockerfile:43-45 sets
# NODE_EXTRA_CA_CERTS, REQUESTS_CA_BUNDLE and SSL_CERT_FILE and line 159 keeps
# them across sudo. An exemption taken on that reading would have claimed the
# subject does not exist when the image ships it.
SUBJECT_FILES = (
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.webui.yml",
    "docker-compose.test.yml",
)


# Assets that cannot implement anything, and whose bytes produce false matches.
# Measured: "pam" appears in six files under these directories and every one is
# a KaTeX font or a minified bundle -- the word is three random bytes inside a
# .woff2. `grep -l` skips those as binary; reading with errors="ignore" does
# not, so the probe claimed a subject was present that exists nowhere in source.
BINARY_SUFFIXES = (
    ".woff", ".woff2", ".ttf", ".otf", ".eot", ".png", ".jpg", ".jpeg", ".gif",
    ".ico", ".pdf", ".wasm", ".zip", ".gz", ".whl", ".so", ".dylib",
)


def _is_asset(path: pathlib.Path) -> bool:
    """Binary blobs and vendored minified bundles are not implementation."""
    if path.suffix.lower() in BINARY_SUFFIXES:
        return True
    return path.name.endswith((".min.js", ".min.css"))


def _subject_paths(root: pathlib.Path):
    """Every file that could implement a requirement's subject."""
    for directory in SUBJECT_DIRS:
        base = root / directory
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts or _is_asset(path):
                continue
            yield path
    for name in SUBJECT_FILES:
        path = root / name
        if path.is_file():
            yield path


def subject_is_absent(root: pathlib.Path, word: str) -> bool:
    """True while no implementation file mentions the subject."""
    for path in _subject_paths(root):
        try:
            if word in path.read_text(encoding="utf-8", errors="ignore").lower():
                return False
        except OSError:
            continue
    return True
MECHANISM_PROBE = {
    "k6": "k6",
    "chaos test": "chaos",
    "replay test": "replay",
    "per-template test": "per-template",
    "per-pr + nightly": "promptfoo",
    "threat-model pass": "threagile",
}


def mechanism_is_absent(root: pathlib.Path, mechanism: str) -> bool:
    """True while nothing under .github/, scripts/ or tests/ implements it.

    This file is excluded: it names every mechanism in the paragraph explaining
    that they are missing, so a search including it always finds them and the
    excuse would never expire.
    """
    needle = MECHANISM_PROBE.get(mechanism, mechanism)
    this = pathlib.Path(__file__).resolve()
    for directory in (".github", "scripts", "tests"):
        base = root / directory
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.resolve() == this:
                continue
            if "__pycache__" in path.parts:
                continue
            try:
                if needle in path.read_text(encoding="utf-8", errors="ignore"):
                    return False
            except OSError:
                continue
    return True


def unexplained_ci_ids(rows: dict[str, str], armed: set[str], excused: set[str], root: pathlib.Path = pathlib.Path(".")) -> list[str]:
    """Ids whose verification column names a CI gate, yet are neither armed nor
    listed with a reason.

    This is the completeness question for the excuse list. Without it the list
    answers for whatever somebody happened to add: measured before it existed,
    190 declared, 11 armed, 11 excused, and three ids naming a CI gate that
    nobody had accounted for.

    Deliberately narrow. An id whose verification asks for a running deployment
    is not coverage debt, and counting it would misread the manifesto.
    """
    absent = {m for m in ABSENT_MECHANISM if mechanism_is_absent(root, m)}
    unbuilt = {w for w in ABSENT_SUBJECT if subject_is_absent(root, w)}
    # The manifesto's own opt-out. A row headed [REVISIT — non-gating] has been
    # declared not to gate anything, so counting it as coverage debt argues with
    # the document this check exists to measure. Read from the row rather than
    # listed here, so the exemption disappears when the marker does.
    return sorted(
        nfr
        for nfr, verification in rows.items()
        if nfr not in armed
        and nfr not in excused
        and any(term in verification.lower() for term in CI_VERIFICATION)
        # Excused by mechanism, and only while that mechanism is still missing.
        and not any(m in verification.lower() for m in absent)
        # Excused by subject, on the same terms: the component is not built.
        and not any(w in verification.lower() for w in unbuilt)
        # Excused by the manifesto itself.
        and "revisit" not in verification.lower()
        and "non-gating" not in verification.lower()
    )


def verdict(declared: set[str], armed: dict[str, list[str]], floor: int) -> list[str]:
    """Reasons to refuse. Empty means the ratchet holds.

    Split from the filesystem walk so --self-test can drive it with constructed
    sets: a check whose logic only runs against the real tree is a check nobody
    can prove still discriminates.
    """
    problems: list[str] = []
    unknown = set(armed) - declared
    if unknown:
        problems.append(
            "named by a check but absent from the manifesto: "
            + ", ".join(sorted(unknown))
            + " -- a check pinned to an id that no longer exists proves nothing"
        )
    if len(armed) < floor:
        problems.append(
            f"armed NFRs dropped to {len(armed)}, below the floor of {floor}: "
            + ", ".join(sorted(declared - set(armed) if floor else []))[:200]
        )
    return problems


def _completeness_self_test() -> int:
    """Drive unexplained_ci_ids() and excused_ids() on constructed inputs."""
    failures = 0
    rows = {
        "NFR-A-1": "CI gate",
        "NFR-A-2": "running deployment probe",
        "NFR-A-3": "CI lint",
    }
    cases = [
        ({"NFR-A-1"}, {"NFR-A-3"}, [], "armed or excused leaves nothing unexplained"),
        ({"NFR-A-1"}, set(), ["NFR-A-3"], "a CI-gated id with no excuse is reported"),
        (set(), set(), ["NFR-A-1", "NFR-A-3"], "both CI-gated ids reported, the deployment one is not"),
    ]
    for armed, excused, want, label in cases:
        got = unexplained_ci_ids(rows, armed, excused)
        ok = got == want
        failures += 0 if ok else 1
        print(f"  {'ok' if ok else 'FAIL'}: {label} -> {got or 'none'}")

    # The excuse parser matches the list's shape, not any mention. This case is
    # the false alarm that shaped it: an id named in prose is not an excuse.
    source = "docstring mentions NFR-SEC-89 in a sentence\n    NFR-B-2   a real reason\n"
    got = excused_ids(source)
    ok = got == {"NFR-B-2"}
    failures += 0 if ok else 1
    print(f"  {'ok' if ok else 'FAIL'}: an id in prose is not an excuse -> {sorted(got)}")
    return failures


def _subject_probe_self_test() -> int:
    """subject_is_absent() must ignore binary assets.

    Without this the probe reads a word out of a font file: "pam" matched six
    files under the implementation directories and every one was a KaTeX
    .woff2 or a minified bundle, so a requirement about privileged-access
    management looked implemented by three random bytes.
    """
    import tempfile

    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        (root / "computer-use-server").mkdir(parents=True)
        (root / "computer-use-server" / "font.woff2").write_bytes(b"\x00widgetword\x01")
        if not subject_is_absent(root, "widgetword"):
            failures += 1
            sys.stderr.write("self-test FAIL: a word inside a .woff2 counted as implementation\n")
        else:
            print("  ok: a word present only in a binary asset is still absent")
        (root / "computer-use-server" / "real.py").write_text("WIDGETWORD = 1\n", encoding="utf-8")
        if subject_is_absent(root, "widgetword"):
            failures += 1
            sys.stderr.write("self-test FAIL: a word in real source read as absent\n")
        else:
            print("  ok: the same word in source counts as present")

    # A subject defined at the repository root rather than inside a component
    # directory. The scan covered SUBJECT_DIRS only, so the sandbox image was
    # invisible to it: every spelling of NFR-FLEX-08's CA-bundle subject read
    # ABSENT while Dockerfile:43-45 sets NODE_EXTRA_CA_CERTS, REQUESTS_CA_BUNDLE
    # and SSL_CERT_FILE. An exemption on that reading would have claimed a
    # subject the image ships does not exist.
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        (root / "computer-use-server").mkdir(parents=True)
        if not subject_is_absent(root, "rootword"):
            failures += 1
            sys.stderr.write("self-test FAIL: a word in no file read as present\n")
        else:
            print("  ok: a word in no file is absent")
        (root / "Dockerfile").write_text("ENV ROOTWORD=/etc/ssl\n", encoding="utf-8")
        if subject_is_absent(root, "rootword"):
            failures += 1
            sys.stderr.write("self-test FAIL: a subject defined in the Dockerfile read as absent\n")
        else:
            print("  ok: a subject defined at the repository root counts as present")
    return failures


def _reachability_self_test() -> int:
    """Drive unreachable_on_canon() over constructed trees.

    Without this the reachability branch is live and untested: every case below
    exercises verdict() only, and the meta-gate would certify a stubbed
    reachability check as bound.
    """
    import tempfile

    failures = 0
    scenarios = [
        ("[main]", ["NFR-X-1"], "a tests/ file reached only by a main-only workflow"),
        (f"[main, {CANON}]", [], "the same file once the workflow reaches canon"),
        ("", [], "a workflow with an unfiltered pull_request trigger"),
    ]
    for branches, want, label in scenarios:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / "tests").mkdir()
            trigger = f"    branches: {branches}\n" if branches else ""
            (root / ".github" / "workflows" / "w.yml").write_text(
                f"name: w\non:\n  pull_request:\n{trigger}jobs:\n  j:\n    steps:\n"
                "      - run: ./tests/t.sh\n",
                encoding="utf-8",
            )
            (root / "tests" / "t.sh").write_text("# NFR-X-1\n", encoding="utf-8")
            got = sorted(unreachable_on_canon(root, {"NFR-X-1": ["tests/t.sh"]}))
            ok = got == want
            failures += 0 if ok else 1
            print(f"  {'ok' if ok else 'FAIL'}: {label} -> {got or 'reachable'}")
    return failures


def _self_test() -> int:
    cases = [
        ("a dropped arm reds", {"NFR-A-1", "NFR-A-2"}, {"NFR-A-1": ["s"]}, 2, True),
        ("holding the floor passes", {"NFR-A-1", "NFR-A-2"}, {"NFR-A-1": ["s"], "NFR-A-2": ["s"]}, 2, False),
        ("gaining an arm passes", {"NFR-A-1", "NFR-A-2"}, {"NFR-A-1": ["s"], "NFR-A-2": ["s"]}, 1, False),
        ("a floor of zero never reds on count", {"NFR-A-1"}, {}, 0, False),
        ("an id no manifesto row declares reds", {"NFR-A-1"}, {"NFR-A-1": ["s"], "NFR-GONE-9": ["s"]}, 1, True),
    ]
    failures = 0
    for name, declared, armed, floor, want_red in cases:
        got_red = bool(verdict(declared, armed, floor))
        ok = got_red == want_red
        failures += 0 if ok else 1
        print(f"  {'ok' if ok else 'FAIL'}: {name}")

    # The parser is the other half: a row-anchored read must not count ids that
    # only appear in prose, or the denominator inflates and coverage looks worse
    # than it is -- an alarm that cries wolf gets switched off.
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        (root / MANIFESTO).parent.mkdir(parents=True)
        (root / MANIFESTO).write_text(
            "Prose mentioning NFR-SEC-99 which is not a row.\n"
            "| NFR-SEC-01 | a real row |\n"
            "| NFR-SEC-02 | another row, see NFR-SEC-01 |\n"
            # Neither of these ends in a bare number. The first pattern here
            # read only `-\\d+` and silently undercounted the manifesto by
            # three rows, which also made an arm on any of them invisible.
            "| NFR-FLEX-07a | a lowercase-suffixed row |\n"
            "| NFR-MAINT-AUDIT-SCHEMA | a word-suffixed row |\n",
            encoding="utf-8",
        )
        got = declared_ids(root)
        want = {"NFR-SEC-01", "NFR-SEC-02", "NFR-FLEX-07a", "NFR-MAINT-AUDIT-SCHEMA"}
        ok = got == want
        failures += 0 if ok else 1
        print(f"  {'ok' if ok else 'FAIL'}: only table rows count as declared ({sorted(got)})")

    # The floor itself has to be un-lowerable, and the constant has to match
    # what the workflow passes -- a floor the caller can undercut is decoration.
    import subprocess

    # Every workflow, not one named file. This read contracts-lint.yml by name,
    # and the nfr-gates job moved to its own workflow (#510) -- the assertion
    # then found no caller at all and reported `[] vs 11`, failing on the
    # absence of what it was looking for rather than on a lowered floor. A check
    # that names one blessed location disables itself the moment the subject
    # moves.
    workflows = pathlib.Path(__file__).resolve().parents[1] / ".github/workflows"
    passed: list[int] = []
    for wf in sorted(workflows.glob("*.yml")) + sorted(workflows.glob("*.yaml")):
        # Executable lines only. A commented-out caller carries the same text,
        # and counting it means this assertion answers for a step nobody runs
        # -- measured by prefixing the real `--min-armed 11` step with `#`,
        # after which the self-test still exited 0.
        text = "\n".join(
            line
            for line in wf.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("#")
        )
        passed += [
            int(part.split()[0])
            for part in text.split("--min-armed ")[1:]
            if part.split() and part.split()[0].isdigit()
        ]
    ok = bool(passed) and all(v >= COMMITTED_FLOOR for v in passed)
    failures += 0 if ok else 1
    print(
        f"  {'ok' if ok else 'FAIL'}: no workflow passes less than "
        f"COMMITTED_FLOOR ({passed} vs {COMMITTED_FLOOR})"
    )

    rc = main(["--min-armed", str(COMMITTED_FLOOR - 1)])
    ok = rc == 2
    failures += 0 if ok else 1
    print(f"  {'ok' if ok else 'FAIL'}: a caller below the floor is refused (exit {rc})")

    failures += _reachability_self_test()
    failures += _subject_probe_self_test()
    failures += _completeness_self_test()

    print()
    if failures:
        print(f"self-test: {failures} case(s) failed")
        return 1
    print("self-test: the check reds on a dropped arm and a stale id, counts rows only, and refuses a lowered floor.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    # Default to the committed floor, not to 1. The floor lived only in the
    # workflow's --min-armed argument, so lowering it was a one-character edit
    # that nothing noticed: measured, changing 11 to 1 left the check green and
    # silent. A ratchet that can be wound backwards without a sound is not one.
    ap.add_argument("--min-armed", type=int, default=COMMITTED_FLOOR)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()

    if args.min_armed < COMMITTED_FLOOR:
        print(
            f"::error::--min-armed {args.min_armed} is below the committed floor "
            f"of {COMMITTED_FLOOR}. Raising the floor is a normal commit; lowering "
            "it means an NFR stopped being checked, which this refuses to do "
            "quietly. Change COMMITTED_FLOOR in this file, in the same commit "
            "that removes the arm, and say why.",
            file=sys.stderr,
        )
        return 2

    root = pathlib.Path(args.repo_root).resolve()
    declared = declared_ids(root)
    if not declared:
        print(f"::error::no NFR rows found in {MANIFESTO} -- the check cannot judge", file=sys.stderr)
        return 2

    armed = armed_ids(root, declared)
    unexplained = unexplained_ci_ids(
        declared_rows(root),
        set(armed),
        excused_ids(pathlib.Path(__file__).read_text(encoding="utf-8")),
        root,
    )
    # A ratchet, not a wall. Widening CI_VERIFICATION to the mechanisms the
    # manifesto actually names took this from 0 to 43: those rows name
    # `release pipeline` and `integration test`, both of which EXIST here, so
    # they are real coverage debt rather than a missing tool. Blocking on them
    # would red every PR for a condition no PR can fix -- the trap already
    # recorded against requiring a context that never arrives. The count is
    # reported and floored instead, so the debt cannot grow unremarked.
    if len(unexplained) > UNEXPLAINED_CEILING:
        print(
            f"::error::{len(unexplained)} ids name a CI gate, are not armed, and carry "
            f"no reason -- above the ceiling of {UNEXPLAINED_CEILING}. Arm one, or "
            f"record why it cannot be armed.",
            file=sys.stderr,
        )
        return 1
    if unexplained:
        print(
            f"::notice::{len(unexplained)} id(s) name a CI gate this repository can run, "
            f"are not armed, and carry no reason: {', '.join(unexplained[:6])}"
            f"{' ...' if len(unexplained) > 6 else ''}. Ceiling {UNEXPLAINED_CEILING}; "
            f"it only goes down."
        )

    print(f"NFR coverage: {len(armed)} of {len(declared)} ids are named by a check that runs")
    stranded = unreachable_on_canon(root, armed)
    for nfr in sorted(armed):
        mark = "STRANDED" if nfr in stranded else "armed   "
        print(f"  {mark} {nfr}  <- {', '.join(sorted(set(armed[nfr])))}")

    if stranded:
        print(
            f"::notice::{len(stranded)} armed id(s) are named only by a check that "
            f"cannot run on {CANON}: {', '.join(sorted(stranded))}. The assertion "
            f"exists and answers for main. Reported, not failed -- the workflow that "
            f"would carry it to canon also builds and pushes images, which is a "
            f"release-posture decision rather than a coverage fix."
        )

    problems = verdict(declared, armed, args.min_armed)
    if problems:
        for problem in problems:
            print(f"::error::{problem}", file=sys.stderr)
        return 1

    print(
        f"the ratchet holds at {args.min_armed}. The remaining "
        f"{len(declared) - len(armed)} are prose: true as written, unproven by anything "
        "that runs."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
