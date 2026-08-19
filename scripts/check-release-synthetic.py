#!/usr/bin/env python3
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
#
# NFR-MAINT-05: a release runs a synthetic transaction before it publishes.
#
# The row asks for "presence + success", verified at the release-pipeline. Both
# words matter and they fail differently. Presence is about the mechanism
# existing; success is about a release being unable to proceed when it fails.
#
# The mechanism exists and is not shallow. build.yml stands a server up, waits
# for health, and drives tests/test-mcp-endpoint-live.sh against the running
# process; a second job spawns a real container over the runner's docker.sock.
# That is a synthetic transaction by any reading.
#
# What was missing when this was written is the binding. release.yml triggers on
# `push: tags: ['v*']` and its single job declares no `needs:`, so nothing that
# exercises the artifact runs between the tag and the publish. The synthetic
# transaction happens on pull requests, against a commit -- not against the
# thing being shipped.
#
# So this check does not ask whether a smoke test is spelled anywhere. Grep
# would already pass on today's tree and the requirement would still be unmet.
# It asks whether the publishing job is REACHABLE without one: it walks the
# `needs:` graph backwards from every job that publishes, and refuses when that
# closure contains no job running a synthetic transaction.

import re
import sys
from pathlib import Path

WORKFLOWS = Path(".github/workflows")
RELEASE = "release.yml"

# Steps that put an artifact somewhere the world can pull it.
#
# docker/build-push-action is deliberately NOT here. The action builds and
# publishes, and which one it does is decided by its inputs: `load: true` puts
# the image in the local daemon and `push: true` sends it to a registry. Keying
# on the action name called the release-gate job a publisher because it builds
# an image to smoke-test, so `push: true` is the honest predicate.
PUBLISHES = re.compile(
    r"push:\s*true|softprops/action-gh-release|"
    r"gh\s+release\s+create|helm\s+push|docker\s+push",
    re.I,
)
# Steps that drive a running system rather than inspecting a file.
#
# Each alternative names an INVOCATION. Earlier versions matched `/mcp` and a
# bare script name, which a hand-mutation showed passing on a workflow whose
# steps had been gutted: `/mcp` survived inside a shell comment, and
# `chmod +x tests/test-mcp-endpoint-live.sh` matched the script it only makes
# executable. Both are mentions. A leading `./` or an interpreter, and a `curl`
# that fails the build on a bad status, are the difference.
SYNTHETIC = re.compile(
    r"(?:\./|\bsh\s+|\bbash\s+)\S*test-mcp-endpoint-live|"
    r"\bdocker\s+run\b|\bdocker\s+compose\s+up\b|"
    r"\bcurl\s+[^\n]*\b(?:localhost|127\.0\.0\.1)\b",
    re.I,
)


def jobs(text: str) -> dict[str, dict]:
    """Job name -> {needs, body}. A hand parse: PyYAML is not a CI dependency here."""
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if re.match(r"^jobs:\s*$", line):
            start = index + 1
            break
    if start is None:
        return {}
    found: dict[str, dict] = {}
    current = None
    for line in lines[start:]:
        if line.strip() and not line.startswith(" "):
            break  # a new top-level key ends the jobs block
        header = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if header:
            current = header.group(1)
            found[current] = {"needs": [], "body": []}
            continue
        if current:
            found[current]["body"].append(line)
            needs = re.match(r"^\s{4}needs:\s*(.+)$", line)
            if needs:
                raw = needs.group(1).strip()
                found[current]["needs"] = re.findall(r"[A-Za-z0-9_-]+", raw)
    return found


def executable(body: list[str]) -> str:
    """The lines a runner executes, dropping everything a human only reads.

    Measured need: release.yml embeds `docker compose up` inside the release
    notes as a quick-start instruction. Matching the whole job body read that
    prose as a synthetic transaction and turned this check green on a tree where
    nothing runs before the publish. A step is executable when it is a `run:`
    command or a `uses:` action, so only those count.
    """
    out = []
    depth = None
    for line in body:
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        if not stripped:
            continue
        match = re.match(r"^-?\s*(run|uses):\s*(.*)$", stripped)
        if match:
            depth = indent
            out.append(match.group(2))
            continue
        # Continuation lines of a block scalar belong to the step that opened it
        # -- except shell comments, which a runner reads and does not execute. A
        # mutation proved this matters: gutting every command left `/mcp` in a
        # comment and the check stayed green.
        if depth is not None and indent > depth:
            if not stripped.startswith("#"):
                out.append(stripped)
            continue
        depth = None
    return "\n".join(out)


def closure(name: str, graph: dict[str, dict]) -> set[str]:
    """Every job that must succeed BEFORE `name` runs, excluding itself.

    A job cannot vouch for itself: its own steps run alongside or after the
    publish, so a smoke test sharing a job with `docker push` proves nothing
    about ordering.
    """
    seen: set[str] = set()
    stack = list(graph.get(name, {}).get("needs", []))
    while stack:
        item = stack.pop()
        if item in seen or item not in graph:
            continue
        seen.add(item)
        stack.extend(graph[item]["needs"])
    return seen


def unguarded_publishers(text: str) -> list[str]:
    """Publishing jobs whose prerequisite closure runs no synthetic transaction."""
    graph = jobs(text)
    out = []
    for name, job in sorted(graph.items()):
        if not PUBLISHES.search(executable(job["body"])):
            continue
        reachable = closure(name, graph)
        covered = any(SYNTHETIC.search(executable(graph[dep]["body"])) for dep in reachable)
        if not covered:
            where = ", ".join(sorted(reachable)) if reachable else "nothing — it declares no needs"
            out.append(
                f"{name}: publishes, but nothing it depends on ({where}) "
                f"exercises a running system"
            )
    return out


def self_test() -> int:
    publish_step = "      - uses: docker/build-push-action@v6\n        with:\n          push: true\n"
    bare = "on:\n  push:\n    tags: ['v*']\njobs:\n  release:\n    steps:\n" + publish_step
    smoked = (
        "on:\n  push:\n    tags: ['v*']\njobs:\n"
        "  smoke:\n    steps:\n      - run: ./tests/test-mcp-endpoint-live.sh http://localhost:8081\n"
        "  release:\n    needs: [smoke]\n    steps:\n" + publish_step
    )
    # The shape that made version two refuse a correct tree: a gate job builds
    # an image to smoke-test it. Building is not publishing.
    builds_locally = (
        "jobs:\n  smoke:\n    steps:\n"
        "      - uses: docker/build-push-action@v6\n        with:\n          load: true\n"
        "      - run: docker run --rm x healthz\n"
    )
    detached = smoked.replace("    needs: [smoke]\n", "")
    indirect = (
        "jobs:\n"
        "  smoke:\n    steps:\n      - run: docker run --rm x healthz\n"
        "  gate:\n    needs: [smoke]\n    steps:\n      - run: echo ok\n"
        "  release:\n    needs: [gate]\n    steps:\n      - run: gh release create v1\n"
    )
    nothing = "jobs:\n  lint:\n    steps:\n      - run: echo hi\n"
    # The shape that made version one of this check pass on a tree where the
    # requirement is unmet: the words appear in release-note prose, not in a step.
    prose = (
        "jobs:\n  release:\n    steps:\n"
        "      - uses: softprops/action-gh-release@v2\n        with:\n          body: |\n"
        "            ## Quick Start\n            ```bash\n            docker compose up\n            ```\n"
    )
    # A smoke test in the SAME job as the publish orders nothing.
    same_job = (
        "jobs:\n  release:\n    steps:\n"
        "      - run: docker run --rm x healthz\n" + publish_step
    )
    # Every command gutted, but the words survive in a comment and a chmod.
    # This is the mutation that caught version three.
    mentioned = (
        "jobs:\n  smoke:\n    steps:\n      - run: |\n"
        "          # register MCP, and answer /health + /mcp\n"
        "          chmod +x tests/test-mcp-endpoint-live.sh\n"
        "          echo skipped\n"
        "  release:\n    needs: [smoke]\n    steps:\n" + publish_step
    )
    cases = [
        (bare, 1, "publishing with no synthetic transaction is refused"),
        (prose, 1, "a smoke command quoted in release notes does not count"),
        (same_job, 1, "a smoke step inside the publishing job does not count"),
        (builds_locally, 0, "building an image with load: true is not publishing"),
        (mentioned, 1, "a smoke script named in a comment or chmod is not a run"),
        (smoked, 0, "a publisher that needs the smoke job passes"),
        (detached, 1, "a smoke job present but not needed is refused"),
        (indirect, 0, "coverage through a transitive need passes"),
        (nothing, 0, "a workflow that publishes nothing has nothing to guard"),
    ]
    bad = 0
    for text, want, label in cases:
        got = 1 if unguarded_publishers(text) else 0
        ok = got == want
        bad += 0 if ok else 1
        print(f"  {'ok' if ok else 'FAIL'}: {label}")
    if bad:
        print(f"self-test: {bad} case(s) failed")
        return 1
    print(f"self-test ok: {len(cases)} cases")
    return 0


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--self-test":
        return self_test()
    root = Path(argv[0]) if argv else Path(".")
    path = root / WORKFLOWS / RELEASE
    if not path.is_file():
        sys.stderr.write(f"::error::{WORKFLOWS / RELEASE} is missing -- the check cannot judge\n")
        return 2
    text = path.read_text(encoding="utf-8")
    if not jobs(text):
        sys.stderr.write(
            f"::error::no jobs parsed out of {RELEASE} -- the check would pass "
            f"vacuously, so it refuses instead\n"
        )
        return 2
    issues = unguarded_publishers(text)
    for issue in issues:
        sys.stderr.write(
            f"::error::NFR-MAINT-05: {issue}. A tag would publish an artifact no "
            f"synthetic transaction ever ran against.\n"
        )
    if issues:
        return 1
    print(
        f"NFR-MAINT-05: every publishing job in {RELEASE} depends on a job that "
        f"drives a running system"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
