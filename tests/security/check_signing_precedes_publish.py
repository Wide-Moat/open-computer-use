#!/usr/bin/env python3
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""Fail when a workflow publishes a consumer-reachable image before it is signed.

A release gate that produces a signature after the artifact is already public
does not gate anything. It reports, loudly, on something that has already
happened, and its failure retracts nothing -- the tag still resolves and the
image still pulls.

The check reads the workflow graph rather than the shell inside a step. It
answers one question: for every trigger on which some job publishes a
consumer-reachable image reference, is a signing job ordered before that
publish? Ordering means a `needs:` edge inside one workflow, or a
`workflow_run` dependency between two.

Two deliberate refusals, both because a silent "ok" here would be the
comforting nothing this check exists to prevent:

  - A job that both publishes and signs is REJECTED, not accepted. Deciding
    that `docker push` above `cosign sign` in one script actually runs first
    means parsing shell with conditionals and functions.
  - A publish whose reference cannot be resolved statically is REPORTED, not
    skipped. An unreadable reference is an unchecked one.

A staging publish is exempt only when the reference names itself as such --
the marker `unsigned` in the tag. The weakening then lives in the workflow
where a reviewer sees it, rather than in this file's assumptions.

Usage:
  check_signing_precedes_publish.py [--workflows DIR]
  check_signing_precedes_publish.py --self-test

Exit 0 when every publish is preceded by a signature, 1 on a violation,
2 on a usage or environment error.
"""

import argparse
import os
import sys

try:
    import yaml
except ImportError:
    print("PyYAML is required: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

PUBLISH_ACTIONS = ("docker/build-push-action", "redhat-actions/push-to-registry")
PUBLISH_SHELL = ("docker push", "buildx imagetools create", "podman push", "skopeo copy")
SIGN_SHELL = ("cosign sign", "cosign attest")
SIGN_ACTIONS = ("actions/attest-build-provenance", "sigstore/gh-action-sigstore-python")
STAGING_MARKER = "unsigned"


def steps_of(job):
    return job.get("steps") or [] if isinstance(job, dict) else []


def job_publishes(job):
    """Return a reason string when the job publishes a consumer-reachable ref."""
    for step in steps_of(job):
        if not isinstance(step, dict):
            continue
        uses = str(step.get("uses") or "")
        run = str(step.get("run") or "")
        with_ = step.get("with") or {}
        if any(a in uses for a in PUBLISH_ACTIONS):
            push = with_.get("push")
            # `push:` absent defaults to false for build-push-action; an
            # expression is unresolvable here and is reported rather than
            # assumed either way.
            if push is None or push is False or str(push).lower() == "false":
                continue
            tags = str(with_.get("tags") or "")
            if STAGING_MARKER in tags:
                continue
            if "${{" in str(push):
                return f"step `{uses.split('@')[0]}` push is the expression {push!r}, which may be true"
            return f"step `{uses.split('@')[0]}` with push: {push}"
        for marker in PUBLISH_SHELL:
            if marker in run:
                line = next((l.strip() for l in run.splitlines() if marker in l), marker)
                if STAGING_MARKER in line:
                    continue
                return f"run step contains `{marker}`: {line[:80]}"
    return None


def job_signs(job):
    for step in steps_of(job):
        if not isinstance(step, dict):
            continue
        run = str(step.get("run") or "")
        uses = str(step.get("uses") or "")
        if any(m in run for m in SIGN_SHELL) or any(a in uses for a in SIGN_ACTIONS):
            return True
    return False


def needs_of(job):
    n = job.get("needs") if isinstance(job, dict) else None
    if n is None:
        return []
    return [n] if isinstance(n, str) else list(n)


def triggers_of(wf):
    """Normalise `on:` into comparable trigger keys.

    `on` is the YAML boolean True after parsing, which is why this reads
    both spellings rather than the obvious one.
    """
    on = wf.get("on", wf.get(True))
    if on is None:
        return set()
    if isinstance(on, str):
        return {on}
    if isinstance(on, list):
        return set(on)
    keys = set()
    for event, spec in on.items():
        if event == "push" and isinstance(spec, dict):
            for tag in spec.get("tags") or []:
                keys.add(f"push:tags:{tag}")
            for br in spec.get("branches") or []:
                keys.add(f"push:branches:{br}")
            if not spec.get("tags") and not spec.get("branches"):
                keys.add("push")
        else:
            keys.add(str(event))
    return keys


def reachable_predecessors(jobs, start):
    """Every job that must complete before `start` runs."""
    seen, stack = set(), list(needs_of(jobs.get(start, {})))
    while stack:
        j = stack.pop()
        if j in seen:
            continue
        seen.add(j)
        stack.extend(needs_of(jobs.get(j, {})))
    return seen


def analyse(workflows):
    """workflows: {name: parsed dict}. Returns (violations, examined_count)."""
    violations = []
    examined = 0

    # A workflow that waits on another via workflow_run runs strictly after it.
    runs_after = {}
    for name, wf in workflows.items():
        on = wf.get("on", wf.get(True)) or {}
        if isinstance(on, dict) and isinstance(on.get("workflow_run"), dict):
            runs_after[name] = set(on["workflow_run"].get("workflows") or [])

    signing_workflows = {}
    for name, wf in workflows.items():
        jobs = wf.get("jobs") or {}
        signers = {jid for jid, j in jobs.items() if job_signs(j)}
        if signers:
            signing_workflows[name] = (signers, triggers_of(wf), wf)

    for name, wf in workflows.items():
        jobs = wf.get("jobs") or {}
        if not jobs:
            continue
        examined += 1
        wf_triggers = triggers_of(wf)
        for jid, job in jobs.items():
            reason = job_publishes(job)
            if not reason:
                continue

            if job_signs(job):
                violations.append(
                    f"{name}: job `{jid}` both publishes and signs. Step order inside one "
                    f"job cannot be established from the workflow graph, so this is not a "
                    f"proven ordering. Split the signature into its own job. ({reason})")
                continue

            preds = reachable_predecessors(jobs, jid)
            if any(job_signs(jobs.get(p, {})) for p in preds):
                continue

            same_wf_signers = {j for j in jobs if job_signs(jobs[j])}
            if same_wf_signers:
                violations.append(
                    f"{name}: job `{jid}` publishes without depending on the signing job(s) "
                    f"{sorted(same_wf_signers)}. The pullable reference exists before the "
                    f"signature. ({reason})")
                continue

            # No signer in this workflow. Look for one elsewhere on a shared
            # trigger -- and say plainly that sharing a trigger is a race,
            # not an ordering.
            elsewhere = [
                other for other, (_, other_trig, _) in signing_workflows.items()
                if other != name and (wf_triggers & other_trig)
                and name not in runs_after.get(other, set())
            ]
            if elsewhere:
                violations.append(
                    f"{name}: job `{jid}` publishes on {sorted(wf_triggers)} and the signing "
                    f"job lives in {elsewhere} on the same trigger with no workflow_run "
                    f"dependency. Two workflows on one trigger race; they are not ordered. "
                    f"({reason})")
            else:
                violations.append(
                    f"{name}: job `{jid}` publishes a consumer-reachable reference and nothing "
                    f"in this repository signs it. ({reason})")
    return violations, examined


SELF_TESTS = [
    ("publish with no signer anywhere", 1, {
        "build.yml": {"on": {"push": {"tags": ["v*"]}}, "jobs": {
            "image": {"steps": [{"uses": "docker/build-push-action@v7", "with": {"push": True}}]}}}}),
    ("publish and sign in separate workflows on the same tag", 1, {
        "build.yml": {"on": {"push": {"tags": ["v*"]}}, "jobs": {
            "image": {"steps": [{"uses": "docker/build-push-action@v7", "with": {"push": True}}]}}},
        "supply-chain.yml": {"on": {"push": {"tags": ["v*"]}}, "jobs": {
            "sign": {"steps": [{"run": "cosign sign --yes $REF"}]}}}}),
    ("publish without needs on the signer in the same workflow", 1, {
        "w.yml": {"on": {"push": {"tags": ["v*"]}}, "jobs": {
            "image": {"steps": [{"run": "docker push ghcr.io/o/i:1"}]},
            "sign": {"steps": [{"run": "cosign sign --yes ghcr.io/o/i:1"}]}}}}),
    ("one job that both publishes and signs is refused", 1, {
        "w.yml": {"on": {"push": {"tags": ["v*"]}}, "jobs": {
            "both": {"steps": [{"run": "docker push ghcr.io/o/i:1\ncosign sign --yes ghcr.io/o/i:1"}]}}}}),
    ("publish ordered after the signer via needs", 0, {
        "w.yml": {"on": {"push": {"tags": ["v*"]}}, "jobs": {
            "sign": {"steps": [{"run": "cosign sign --yes ghcr.io/o/i@$DIGEST"}]},
            "promote": {"needs": "sign",
                        "steps": [{"run": "docker buildx imagetools create --tag ghcr.io/o/i:1 ghcr.io/o/i@$DIGEST"}]}}}}),
    ("staging publish naming itself unsigned is exempt", 0, {
        "w.yml": {"on": {"push": {"tags": ["v*"]}}, "jobs": {
            "stage": {"steps": [{"run": "docker push ghcr.io/o/i:unsigned-staging"}]}}}}),
    ("pull-request build that does not push", 0, {
        "w.yml": {"on": {"pull_request": None}, "jobs": {
            "image": {"steps": [{"uses": "docker/build-push-action@v7", "with": {"push": False}}]}}}}),
]


def self_test():
    failed = 0
    for label, expected, wfs in SELF_TESTS:
        violations, _ = analyse(wfs)
        got = 1 if violations else 0
        if got != expected:
            failed += 1
            print(f"SELF-TEST FAILED: {label} -- expected {'a violation' if expected else 'no violation'}, "
                  f"got {violations or 'none'}")
        else:
            print(f"ok   self-test: {label}")
    if failed:
        print(f"\n{failed} self-test(s) failed; the check cannot be trusted on real workflows")
        return 1
    print("\nself-test: the check reports a violation in every case that has one, and none where there is not")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workflows", default=".github/workflows")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    if not os.path.isdir(args.workflows):
        print(f"no such directory: {args.workflows}", file=sys.stderr)
        return 2

    workflows = {}
    for fn in sorted(os.listdir(args.workflows)):
        if not fn.endswith((".yml", ".yaml")):
            continue
        path = os.path.join(args.workflows, fn)
        try:
            with open(path) as fh:
                doc = yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            print(f"FAIL {fn}: unparseable, so its publishes are unchecked -- {exc}")
            return 1
        if isinstance(doc, dict):
            workflows[fn] = doc

    violations, examined = analyse(workflows)

    if examined == 0:
        print(f"NOTHING WAS EXAMINED in {args.workflows}. Treat this as a failure: a check "
              f"that inspects no workflow is indistinguishable from one that passes.")
        return 1

    for v in violations:
        print(f"FAIL {v}")
    print(f"\nworkflows with jobs examined: {examined}, violations: {len(violations)}")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
