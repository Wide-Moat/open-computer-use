#!/usr/bin/env python3
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
#
# NFR-IC-02: no mutating operator-console surface ships.
#
# The row says every state-mutating operator / control-plane action goes through
# the CLI and declarative config, with no mutating operator-console UI in v1.
# CLAUDE.md states the same thing as a locked non-goal: v1 ships zero admin UI,
# because every UI is new attack surface, auth burden and accessibility cost.
#
# The distinction that makes this checkable is SCOPE, not the HTTP verb. This
# server does serve mutating routes and a page that calls them -- restart the
# container, kill a process, stop ttyd. Reading them shows every one is keyed on
# `chat_id` and the page supplies exactly one, from window.__CONFIG__, so the UI
# acts on the session it belongs to and cannot address another. That is a
# data-plane surface, which the row explicitly routes to NFR-SEC-82 instead.
#
# An operator console is the other shape: a mutating route with no session in
# its path, reachable by whoever loads the page, acting on somebody else's
# session or on the deployment. That is what this refuses.
#
# So the check is: every mutating route the server declares carries a session
# parameter in its path. A route that mutates without one is either an operator
# action -- which belongs in the CLI -- or a data-plane action that has lost its
# scope, and both are worth stopping.

import re
import sys
from pathlib import Path

APP = Path("computer-use-server/app.py")
STATIC = Path("computer-use-server/static")

# Mutating HTTP verbs as FastAPI decorators.
ROUTE = re.compile(r"^@app\.(post|put|patch|delete)\(\s*[\"']([^\"']+)[\"']", re.M)
# The path parameter that scopes an action to one session.
SESSION_PARAM = re.compile(r"\{chat_id[^}]*\}")

# Names that would make a page an operator console rather than a session panel.
CONSOLE_MARKERS = ("ocu-admin", "admin-console", "operator-console", "admin_ui")


def mutating_routes(source: str) -> list[tuple[str, str]]:
    """(verb, path) for every mutating route the app declares."""
    return [(verb.upper(), path) for verb, path in ROUTE.findall(source)]


def unscoped(routes: list[tuple[str, str]]) -> list[str]:
    """Mutating routes with no session in their path."""
    return [f"{verb} {path}" for verb, path in routes if not SESSION_PARAM.search(path)]


def console_assets(assets: dict[str, str]) -> list[str]:
    """Served files that identify themselves as an operator console."""
    out = []
    for name, text in sorted(assets.items()):
        lowered = text.lower()
        for marker in CONSOLE_MARKERS:
            if marker in lowered:
                out.append(f"{name} names {marker}")
    return out


def problems(routes: list[tuple[str, str]], assets: dict[str, str]) -> list[str]:
    """Reasons to refuse. Empty means no mutating operator surface ships."""
    out = []
    for route in unscoped(routes):
        out.append(
            f"{route} mutates without a session in its path -- an operator action "
            f"belongs in the CLI, and a data-plane action without a scope can "
            f"address somebody else's session"
        )
    out.extend(console_assets(assets))
    return out


def self_test() -> int:
    session = [("POST", "/terminal/{chat_id}/restart-container")]
    cases = [
        ((session, {}), 0, "a mutating route scoped to a session passes"),
        ((session + [("POST", "/admin/kill-all")], {}), 1, "an unscoped mutating route is refused"),
        (([("DELETE", "/sessions/{id}")], {}), 1, "a session param by another name is not the scope"),
        ((session, {"p.js": "fetch('/api/x')"}), 0, "a session panel is not a console"),
        ((session, {"a.js": "mount('#ocu-admin-root')"}), 1, "an asset naming ocu-admin is refused"),
        (([], {}), 0, "no mutating route at all passes"),
    ]
    bad = 0
    for (routes, assets), want, label in cases:
        got = 1 if problems(routes, assets) else 0
        ok = got == want
        bad += 0 if ok else 1
        print(f"  {'ok' if ok else 'FAIL'}: {label}")

    # The extractor, on constructed source. Without this the parse is untested:
    # on the shipped tree every route is scoped, so a stub returning [] passes.
    found = mutating_routes(
        '@app.post("/terminal/{chat_id}/x")\n@app.get("/read")\n@app.delete("/admin/y")\n'
    )
    if found != [("POST", "/terminal/{chat_id}/x"), ("DELETE", "/admin/y")]:
        bad += 1
        sys.stderr.write(f"self-test FAIL: extractor returned {found}\n")
    else:
        print("  ok: mutating verbs are extracted and GET is not one")

    if bad:
        print(f"self-test: {bad} case(s) failed")
        return 1
    print("self-test ok: 7 cases")
    return 0


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--self-test":
        return self_test()
    root = Path(argv[0]) if argv else Path(".")
    path = root / APP
    if not path.is_file():
        sys.stderr.write(f"::error::{APP} is missing -- the check cannot judge\n")
        return 2
    source = path.read_text(encoding="utf-8")
    routes = mutating_routes(source)
    if not routes:
        # Not a pass. This server declares mutating routes; finding none means
        # the decorator shape changed and the check stopped reading the surface.
        sys.stderr.write(
            f"::error::no mutating route parsed out of {APP} -- the route shape "
            f"changed and this check would pass without inspecting one\n"
        )
        return 2

    assets = {}
    base = root / STATIC
    if base.is_dir():
        for asset in sorted(base.rglob("*")):
            if asset.is_file() and asset.suffix.lower() in (".js", ".html") and not asset.name.endswith(".min.js"):
                assets[str(asset.relative_to(root))] = asset.read_text(encoding="utf-8", errors="ignore")

    issues = problems(routes, assets)
    for issue in issues:
        sys.stderr.write(f"::error::NFR-IC-02: {issue}\n")
    if issues:
        return 1
    print(
        f"NFR-IC-02: all {len(routes)} mutating route(s) are session-scoped and "
        f"none of {len(assets)} served asset(s) is an operator console"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
