#!/usr/bin/env python3
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""Fail when a job reads an output no upstream job will produce.

`${{ needs.build-webui.outputs.digest }}` does not error when `build-webui`
declares no such output, or is missing from this job's `needs`, or is spelled
wrong. It evaluates to the empty string, silently.

That matters here because the release pipeline carries the image digest across
three jobs on exactly this mechanism. The gate3 rehearsal cannot reach it: the
rehearsal is one job, because the throwaway registry it uses is a service
container and does not outlive the job that started it. So the one part of the
pipeline the rehearsal proves nothing about is the part that is only a string.

The failure is not silent corruption -- both guards refuse an empty digest and
say why. It is a release that dies at the signing step, discovered at release
time, which is the situation the rehearsal exists to prevent.

Three ways the reference breaks, all of which produce the same empty string:
the producer is not in `needs`, so its outputs are not in scope; the producer
does not exist; the producer exists and declares different outputs.

Usage:
  check_cross_job_outputs.py [--workflows DIR]
  check_cross_job_outputs.py --self-test

Exit 0 when every cross-job reference resolves, 1 on a broken one, 2 on a
usage or environment error.
"""

import argparse
import glob
import os
import re
import sys

try:
    import yaml
except ImportError:
    print("PyYAML is required: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

REF = re.compile(r"needs\.([A-Za-z0-9_-]+)\.outputs\.([A-Za-z0-9_-]+)")


def needs_of(job):
    n = job.get("needs") or []
    return [n] if isinstance(n, str) else list(n)


def analyse(workflows):
    """workflows: {name: parsed dict}. Returns (violations, references_checked)."""
    violations = []
    checked = 0
    for name, wf in workflows.items():
        jobs = (wf or {}).get("jobs") or {}
        for jid, job in jobs.items():
            if not isinstance(job, dict):
                continue
            needs = needs_of(job)
            # Serialising the job back to text finds the reference wherever it
            # sits -- a step's `run`, a `with:`, an `env:`, a matrix entry --
            # without this file having to know every place an expression is
            # allowed to appear.
            for src, key in set(REF.findall(yaml.safe_dump(job))):
                checked += 1
                if src not in needs:
                    violations.append(
                        f"{name}: job `{jid}` reads needs.{src}.outputs.{key}, but `{src}` "
                        f"is not in its needs {sorted(needs)}. Outputs of a job you do not "
                        f"depend on are not in scope, and the reference is the empty string.")
                elif src not in jobs:
                    violations.append(
                        f"{name}: job `{jid}` reads needs.{src}.outputs.{key}, and no job "
                        f"`{src}` exists in this workflow.")
                else:
                    declared = (jobs[src].get("outputs") or {})
                    if key not in declared:
                        violations.append(
                            f"{name}: job `{jid}` reads needs.{src}.outputs.{key}, but `{src}` "
                            f"declares {sorted(declared) or 'no outputs'}. The reference is the "
                            f"empty string.")
    return violations, checked


SELF_TESTS = [
    ("a reference that resolves", 0, {
        "w.yml": {"jobs": {
            "build": {"outputs": {"digest": "${{ steps.b.outputs.digest }}"}, "steps": []},
            "sign": {"needs": ["build"],
                     "steps": [{"run": "cosign sign ${{ needs.build.outputs.digest }}"}]}}}}),
    ("producer missing from needs", 1, {
        "w.yml": {"jobs": {
            "build": {"outputs": {"digest": "x"}, "steps": []},
            "sign": {"steps": [{"run": "echo ${{ needs.build.outputs.digest }}"}]}}}}),
    ("producer does not exist", 1, {
        "w.yml": {"jobs": {
            "sign": {"needs": ["buidl"],
                     "steps": [{"run": "echo ${{ needs.buidl.outputs.digest }}"}]}}}}),
    ("producer declares a different output", 1, {
        "w.yml": {"jobs": {
            "build": {"outputs": {"sha": "x"}, "steps": []},
            "sign": {"needs": ["build"],
                     "steps": [{"run": "echo ${{ needs.build.outputs.digest }}"}]}}}}),
    ("producer declares no outputs at all", 1, {
        "w.yml": {"jobs": {
            "build": {"steps": []},
            "sign": {"needs": ["build"],
                     "steps": [{"run": "echo ${{ needs.build.outputs.digest }}"}]}}}}),
    # The reference is often not in a `run:`. Serialising the whole job is what
    # makes these reachable without enumerating every place an expression may sit.
    ("a reference inside a matrix entry", 1, {
        "w.yml": {"jobs": {
            "build": {"outputs": {"sha": "x"}, "steps": []},
            "sign": {"needs": ["build"],
                     "strategy": {"matrix": {"include": [
                         {"digest": "${{ needs.build.outputs.digest }}"}]}},
                     "steps": []}}}}),
    ("a reference inside job-level env", 1, {
        "w.yml": {"jobs": {
            "build": {"steps": []},
            "sign": {"needs": ["build"],
                     "env": {"D": "${{ needs.build.outputs.digest }}"},
                     "steps": []}}}}),
]


def self_test():
    failed = 0
    for label, expected, wfs in SELF_TESTS:
        violations, _ = analyse(wfs)
        got = 1 if violations else 0
        if got != expected:
            failed += 1
            print(f"SELF-TEST FAILED: {label} -- expected "
                  f"{'a violation' if expected else 'no violation'}, got {violations or 'none'}")
        else:
            print(f"ok   self-test: {label}")
    if failed:
        print(f"\n{failed} self-test(s) failed; the check cannot be trusted on real workflows")
        return 1
    print("\nself-test: every broken reference is reported, and a resolving one is not")
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
    for path in sorted(glob.glob(os.path.join(args.workflows, "*.yml")) +
                       glob.glob(os.path.join(args.workflows, "*.yaml"))):
        try:
            with open(path) as fh:
                workflows[os.path.basename(path)] = yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            print(f"{path}: not parseable as YAML: {exc}", file=sys.stderr)
            return 2

    violations, checked = analyse(workflows)
    for v in violations:
        print(f"FAIL {v}")
    print(f"\ncross-job output references checked: {checked}, broken: {len(violations)}")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
