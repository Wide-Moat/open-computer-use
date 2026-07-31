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
publish? Ordering means a `needs:` edge, so the signer has to live in the
same workflow as the publish it precedes.

Ordering across two workflows is not accepted, and not because it is hard to
read. A signature is over a digest, and the digest exists only once the build
has run: a signing workflow scheduled ahead of the building one has nothing to
sign, and one scheduled after it signs what is already public. Neither order
satisfies the invariant, so there is no arrangement of `workflow_run` to
accept. The way out is push-by-digest, which publishes no tag, followed by
`needs:`-ordered sign and promote jobs in that same workflow.

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


def shell_code(run):
    """The lines of a `run:` block that the shell would execute.

    Whole-line comments are dropped. Both directions of this matter and the
    second is the dangerous one: a commented-out `docker push` is noise, but a
    commented-out `cosign sign` makes a job read as a signer, and a publish
    that depends on that job then reports zero violations for a pipeline whose
    signing is switched off.

    Only lines whose first non-blank character is `#` are removed. A trailing
    comment on a real command is left in place: cutting at the first `#`
    anywhere would also cut a `#` inside a quoted string, and the failure there
    is to stop seeing a publish that is really happening.
    """
    return "\n".join(
        line for line in str(run or "").splitlines()
        if not line.lstrip().startswith("#")
    )


def is_local_registry(ref):
    """True when the reference names a registry only the runner can reach.

    A rehearsal that pushes to a registry started as a job service proves the
    mechanism without creating anything anyone can pull: the host dies with the
    job. Treating that as a publish would force the check to reject the only
    way to exercise the pipeline it is guarding.

    Matched on the registry host, which is the first path segment when it
    carries a port or is a bare localhost form -- not on a substring, so an
    image called `localhost-tools` on a real registry is unaffected.
    """
    head = ref.strip().split("/", 1)[0]
    host = head.rsplit(":", 1)[0] if ":" in head else head
    return host in ("localhost", "127.0.0.1", "::1", "[::1]")


def steps_of(job):
    return job.get("steps") or [] if isinstance(job, dict) else []


def tag_inside_outputs(outputs):
    """A tag can hide in `outputs: type=image,name=<ref>,...` with no `tags:` key.

    A colon in the LAST path segment is a tag. A colon before it is a registry
    port -- `localhost:5000/org/repo` carries no tag -- and reading that as one
    trades a false negative for a false positive, which is not an improvement.
    """
    for part in outputs.split(","):
        part = part.strip()
        if not part.startswith("name="):
            continue
        ref = part[len("name="):]
        if ":" in ref.rsplit("/", 1)[-1]:
            return ref
    return None


def job_publishes(job):
    """Return a reason string when the job creates a CONSUMER-REACHABLE reference.

    What matters is the tag, not the push. Cosign signs a digest, so the image
    must reach the registry before it can be signed at all -- a digest-only
    push is the sole way to have something to sign and is not a violation. The
    violation is attaching a tag a consumer would pull, before a signature
    exists for it.

    `push: true` and `outputs: type=image,...,push=true` are the same act
    spelled two ways, and the second is the ordinary spelling for digest-based
    publishing. Reading only the first passes a tagged publish silently.
    """
    for step in steps_of(job):
        if not isinstance(step, dict):
            continue
        uses = str(step.get("uses") or "")
        run = shell_code(step.get("run"))
        with_ = step.get("with") or {}

        if any(a in uses for a in PUBLISH_ACTIONS):
            push = with_.get("push")
            outputs = str(with_.get("outputs") or "")
            pushes_via_outputs = "push=true" in outputs.replace(" ", "")
            digest_only = "push-by-digest=true" in outputs.replace(" ", "")
            push_absent = push is None or push is False or str(push).lower() == "false"
            if push_absent and not pushes_via_outputs and not digest_only:
                continue

            # push-by-digest short-circuits before any tag reasoning. It is the
            # corrected form, and without this the check can flag the very
            # shape it exists to recommend.
            if digest_only:
                continue

            if is_local_registry(str(with_.get("tags") or "")) or \
               any(is_local_registry(part[len("name="):])
                   for part in outputs.split(",") if part.strip().startswith("name=")):
                continue

            tags = str(with_.get("tags") or "").strip()
            hidden = tag_inside_outputs(outputs) if not tags else None
            if not tags and not hidden:
                # No tag anywhere: the reference is a digest nobody was handed.
                continue
            label = tags.splitlines()[0][:60] if tags else hidden
            if STAGING_MARKER in (tags or hidden or ""):
                continue

            how = f"outputs: {outputs[:60]}" if pushes_via_outputs else f"push: {push}"
            if hidden:
                how = f"the tag is inside outputs, with no `tags:` key: {outputs[:60]}"
            if "${{" in str(push):
                how = f"push is the expression {push!r}, which may be true"
            return f"step `{uses.split('@')[0]}` attaches tag(s) {label!r} with {how}"

        for marker in PUBLISH_SHELL:
            if marker in run:
                line = next((l.strip() for l in run.splitlines() if marker in l), marker)
                if STAGING_MARKER in line:
                    continue
                if any(is_local_registry(tok) for tok in line.split()):
                    continue
                # A bare digest reference in a shell push is not consumer-reachable.
                if marker == "docker push" and "@sha256:" in line and "--tag" not in line:
                    continue
                return f"run step contains `{marker}`: {line[:80]}"
    return None


def job_signs(job):
    for step in steps_of(job):
        if not isinstance(step, dict):
            continue
        run = shell_code(step.get("run"))
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

            # No signer in this workflow. Name the one that exists elsewhere,
            # so the report does not read as "nothing signs this" when
            # something does -- the remedy differs between the two.
            elsewhere = [
                other for other, (_, other_trig, _) in signing_workflows.items()
                if other != name and (wf_triggers & other_trig)
            ]
            # A signer that does not share this trigger is still a signer. Say
            # so: "nothing signs it" and "the signer is in another workflow"
            # have different remedies, and only the second is true here.
            if not elsewhere:
                elsewhere = [other for other in signing_workflows if other != name]
            if elsewhere:
                violations.append(
                    f"{name}: job `{jid}` publishes on {sorted(wf_triggers)} and the only "
                    f"signing job is in {elsewhere}, a separate workflow. No trigger order "
                    f"between two workflows fixes this: scheduled first the signer has no "
                    f"digest to sign, scheduled second it signs what is already public. Move "
                    f"the signature into this workflow behind `needs:`. ({reason})")
            else:
                violations.append(
                    f"{name}: job `{jid}` publishes a consumer-reachable reference and nothing "
                    f"in this repository signs it. ({reason})")
    return violations, examined


SELF_TESTS = [
    # These two carry `tags:` because a real publishing job does. Written
    # without it they were shorthand for "a job that publishes", and the
    # shorthand stopped being true once the check learned that the tag, not
    # the push, is what makes a reference reachable.
    ("a publish that exists only inside a shell comment is not a publish", 0, {
        "w.yml": {"on": {"push": {"tags": ["v*"]}}, "jobs": {
            "image": {"steps": [{"run": "# the old pipeline ran:\n#   docker push ghcr.io/o/i:v1\necho building\n"}]}}}}),
    # The dangerous direction. Before comment lines were skipped this returned
    # no violation: the commented-out cosign made `sign` read as a signer, and
    # the publish depending on it looked ordered behind a signature that is
    # switched off.
    ("a publish behind a signer whose cosign is commented out", 1, {
        "w.yml": {"on": {"push": {"tags": ["v*"]}}, "jobs": {
            "sign": {"steps": [{"run": "# cosign sign --yes ghcr.io/o/i:v1\necho disabled\n"}]},
            "publish": {"needs": "sign", "steps": [{"run": "docker push ghcr.io/o/i:v1"}]}}}},
     "nothing in this repository signs it"),
    ("a push to a registry only the runner can reach is not a publish", 0, {
        "w.yml": {"on": {"pull_request": None}, "jobs": {
            "rehearse": {"steps": [
                {"run": "docker buildx imagetools create --tag localhost:5000/probe:v1 localhost:5000/probe@$D"}]}}}}),
    ("the same push to a real registry is a publish", 1, {
        "w.yml": {"on": {"pull_request": None}, "jobs": {
            "rehearse": {"steps": [
                {"run": "docker buildx imagetools create --tag ghcr.io/o/probe:v1 ghcr.io/o/probe@$D"}]}}}}),
    ("a repository merely named localhost-something is still a publish", 1, {
        "w.yml": {"on": {"push": {"tags": ["v*"]}}, "jobs": {
            "p": {"steps": [{"run": "docker push ghcr.io/o/localhost-tools:v1"}]}}}}),
    ("publish with no signer anywhere", 1, {
        "build.yml": {"on": {"push": {"tags": ["v*"]}}, "jobs": {
            "image": {"steps": [{"uses": "docker/build-push-action@v7",
                                 "with": {"push": True, "tags": "ghcr.io/o/i:v1"}}]}}}}),
    ("publish and sign in separate workflows on the same tag", 1, {
        "build.yml": {"on": {"push": {"tags": ["v*"]}}, "jobs": {
            "image": {"steps": [{"uses": "docker/build-push-action@v7",
                                 "with": {"push": True, "tags": "ghcr.io/o/i:v1"}}]}}},
        "supply-chain.yml": {"on": {"push": {"tags": ["v*"]}}, "jobs": {
            "sign": {"steps": [{"run": "cosign sign --yes $REF"}]}}}},
     "a separate workflow", "nothing in this repository signs it"),
    # `workflow_run` used to be documented as an accepted ordering. No
    # arrangement of it can be correct, so both directions stay violations and
    # both must name the separate workflow rather than deny it exists.
    ("publisher scheduled after the signer via workflow_run, by display name", 1, {
        "build.yml": {"name": "Build", "on": {"workflow_run": {
            "workflows": ["supply-chain"], "types": ["completed"]}}, "jobs": {
            "image": {"steps": [{"uses": "docker/build-push-action@v7",
                                 "with": {"push": True, "tags": "ghcr.io/o/i:v1"}}]}}},
        "supply-chain.yml": {"name": "supply-chain", "on": {"push": {"tags": ["v*"]}}, "jobs": {
            "sign": {"steps": [{"run": "cosign sign --yes $REF"}]}}}},
     None, "nothing in this repository signs it"),
    ("signer scheduled after the publisher via workflow_run", 1, {
        "build.yml": {"name": "Build", "on": {"push": {"tags": ["v*"]}}, "jobs": {
            "image": {"steps": [{"uses": "docker/build-push-action@v7",
                                 "with": {"push": True, "tags": "ghcr.io/o/i:v1"}}]}}},
        "supply-chain.yml": {"name": "supply-chain", "on": {"push": {"tags": ["v*"]},
            "workflow_run": {"workflows": ["Build"], "types": ["completed"]}}, "jobs": {
            "sign": {"steps": [{"run": "cosign sign --yes $REF"}]}}}},
     "a separate workflow", "nothing in this repository signs it"),
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
    # The same publish spelled through `outputs:`. Reading only `with.push`
    # passed this silently, which is how it was found -- against a peer's
    # corrected pipeline, where the tagless form of it is the correct answer.
    ("tagged publish spelled through outputs: is a violation", 1, {
        "w.yml": {"on": {"push": {"tags": ["v*"]}}, "jobs": {
            "publish": {"steps": [{"uses": "docker/build-push-action@v7", "with": {
                "outputs": "type=image,name=ghcr.io/o/i,push=true", "tags": "ghcr.io/o/i:v1.2.3"}}]},
            "sign": {"steps": [{"run": "cosign sign --yes ghcr.io/o/i:v1.2.3"}]}}}}),
    ("push-by-digest with no tag is not a consumer reference", 0, {
        "w.yml": {"on": {"push": {"tags": ["v*"]}}, "jobs": {
            "image": {"steps": [{"uses": "docker/build-push-action@v7", "with": {
                "outputs": "type=image,name=ghcr.io/o/i,push-by-digest=true"}}]},
            "sign": {"needs": "image", "steps": [{"run": "cosign sign --yes ghcr.io/o/i@$DIGEST"}]},
            "promote": {"needs": "sign", "steps": [
                {"run": "docker buildx imagetools create --tag ghcr.io/o/i:v1 ghcr.io/o/i@$DIGEST"}]}}}}),
    ("push: true with no tag is likewise not a consumer reference", 0, {
        "w.yml": {"on": {"push": {"tags": ["v*"]}}, "jobs": {
            "image": {"steps": [{"uses": "docker/build-push-action@v7", "with": {"push": True}}]}}}}),
    # The mirror of the outputs hole, found by component-02 in its own checker
    # and present here too: a tag with neither a `tags:` key nor a `push:` key.
    ("a tag hidden inside outputs, with no tags: key", 1, {
        "w.yml": {"on": {"push": {"tags": ["v*"]}}, "jobs": {
            "publish": {"steps": [{"uses": "docker/build-push-action@v7", "with": {
                "outputs": "type=image,name=ghcr.io/org/repo:v1.2.3,push=true"}}]},
            "sign": {"steps": [{"run": "cosign sign --yes ghcr.io/org/repo:v1.2.3"}]}}}}),
    ("a registry port is not a tag", 0, {
        "w.yml": {"on": {"push": {"tags": ["v*"]}}, "jobs": {
            "publish": {"steps": [{"uses": "docker/build-push-action@v7", "with": {
                "outputs": "type=image,name=localhost:5000/org/repo,push=true"}}]},
            "sign": {"needs": "publish", "steps": [{"run": "cosign sign --yes localhost:5000/org/repo@$D"}]}}}}),
]


def self_test():
    failed = 0
    for entry in SELF_TESTS:
        label, expected, wfs = entry[0], entry[1], entry[2]
        # A case may pin a fragment of the reason. Asserting only the count let
        # a violation be reported for the wrong reason, which is how the
        # cross-workflow cases came to say "nothing signs it" about a
        # repository that does sign it.
        want, unwanted = (entry[3] if len(entry) > 3 else None), (entry[4] if len(entry) > 4 else None)
        violations, _ = analyse(wfs)
        got = 1 if violations else 0
        if got != expected:
            failed += 1
            print(f"SELF-TEST FAILED: {label} -- expected {'a violation' if expected else 'no violation'}, "
                  f"got {violations or 'none'}")
        elif want and not any(want in v for v in violations):
            failed += 1
            print(f"SELF-TEST FAILED: {label} -- reported, but no reason contains {want!r}: {violations}")
        elif unwanted and any(unwanted in v for v in violations):
            failed += 1
            print(f"SELF-TEST FAILED: {label} -- reason wrongly claims {unwanted!r}: {violations}")
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
