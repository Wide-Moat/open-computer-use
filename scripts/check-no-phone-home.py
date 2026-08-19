#!/usr/bin/env python3
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
#
# NFR-SEC-16: the shipped artifacts call no vendor-controlled endpoint.
#
# The row asks that the installer and runtime never reach a Wide-Moat-controlled
# endpoint without explicit customer opt-in, and states the verification as CI
# artifact inspection of the installer and runtime images. Zero vendor outbound
# in the default configuration is the target.
#
# The property holds today and this keeps it holding. Measured across the
# Dockerfile, the compose files, the server and the chart: every outbound host
# is either a build-time toolchain source (nodejs.org, bun.sh, github.com,
# gitlab.com), a customer-configured upstream (api.anthropic.com), or a
# local/compose name. No wide-moat.* or ocu-*.io host appears anywhere.
#
# Two distinctions decide what this refuses, and both were measured rather than
# assumed.
#
# A link is not a call. docs.html carries eight github.com hrefs and preview.js
# one -- anchors a human clicks, which fetch nothing on load. A check that
# flagged them would report the repository's own README link as a phone-home.
# What matters in a served asset is a tag the browser resolves automatically:
# script src, link href, img src, iframe src, fetch/XHR to an external origin.
#
# Prose is not code. system_prompt.py names cdnjs.cloudflare.com twice, in text
# instructing the model about artifact authoring. It is a string in a prompt,
# not an outbound path the runtime takes. Scanning every file that contains a
# URL would count it; scanning the artifacts for vendor hosts, and the served
# assets for auto-loading tags, does not.

import re
import sys
from pathlib import Path

# The shipped surface: what a customer installs and runs.
ARTIFACTS = (
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.webui.yml",
    "helm/computer-use-server/values.yaml",
)
SERVER = Path("computer-use-server")
STATIC = SERVER / "static"

# Hosts under the vendor's control. Reaching one in a default install is the
# phone-home this requirement forbids.
VENDOR_HOSTS = (
    "wide-moat.com",
    "wide-moat.io",
    "widemoat.com",
    "widemoat.io",
    "ocu.dev",
    "opencomputeruse.com",
    "telemetry.wide-moat",
)

URL = re.compile(r"https?://([a-zA-Z0-9.-]+)")
# Tags a browser resolves without the user doing anything. An <a href> is
# deliberately absent: it is a link, not a load.
AUTO_LOAD = re.compile(
    r"<(?:script|img|iframe|source|audio|video)[^>]+src\s*=\s*[\"']https?://([^\"'/]+)"
    r"|<link[^>]+href\s*=\s*[\"']https?://([^\"'/]+)"
    r"|\bfetch\s*\(\s*[\"']https?://([^\"'/]+)"
    r"|\.open\s*\(\s*[\"'][A-Z]+[\"']\s*,\s*[\"']https?://([^\"'/]+)",
    re.I,
)


def _is_vendored(path: Path) -> bool:
    """Third-party bundles are not our outbound decisions."""
    return path.name.endswith((".min.js", ".umd.js")) or ".browser.min" in path.name


def vendor_hosts_in(text: str) -> list[str]:
    """Vendor-controlled hosts named anywhere in an artifact."""
    found = []
    for host in URL.findall(text):
        lowered = host.lower()
        for vendor in VENDOR_HOSTS:
            if lowered == vendor or lowered.endswith("." + vendor) or vendor in lowered:
                found.append(host)
    return sorted(set(found))


def auto_loaded_hosts(text: str) -> list[str]:
    """External hosts a served asset fetches without user action."""
    found = []
    for groups in AUTO_LOAD.findall(text):
        host = next((g for g in groups if g), "")
        if host:
            found.append(host.lower())
    return sorted(set(found))


def served_assets(root: Path) -> list[Path]:
    """First-party files the browser loads."""
    base = root / STATIC
    if not base.is_dir():
        return []
    return sorted(
        p
        for p in base.rglob("*")
        if p.is_file() and p.suffix.lower() in (".html", ".js", ".css") and not _is_vendored(p)
    )


def problems(artifacts: dict[str, str], assets: dict[str, str]) -> list[str]:
    """Reasons to refuse. Empty means the default install phones nobody home."""
    out = []
    for name, text in sorted(artifacts.items()):
        for host in vendor_hosts_in(text):
            out.append(f"{name} names the vendor-controlled host {host}")
    for name, text in sorted(assets.items()):
        for host in vendor_hosts_in(text):
            out.append(f"{name} names the vendor-controlled host {host}")
        for host in auto_loaded_hosts(text):
            out.append(
                f"{name} auto-loads from {host} -- a served asset fetching an "
                f"external origin on load is outbound the customer did not configure"
            )
    return out


def self_test() -> int:
    cases = [
        (({"Dockerfile": "RUN curl https://nodejs.org/dist/x.tar.gz"}, {}), 0,
         "a build-time toolchain source passes"),
        (({"Dockerfile": "ENV API=https://api.anthropic.com"}, {}), 0,
         "a customer-configured upstream passes"),
        (({"docker-compose.yml": "TELEMETRY=https://telemetry.wide-moat.io/v1"}, {}), 1,
         "a vendor telemetry endpoint is refused"),
        (({}, {"docs.html": '<a href="https://github.com/x/y">GitHub</a>'}), 0,
         "an anchor a human clicks is not a call"),
        (({}, {"docs.html": '<script src="https://cdnjs.cloudflare.com/x.js"></script>'}), 1,
         "a script the browser auto-loads is refused"),
        (({}, {"p.js": 'fetch("https://example.com/beacon")'}), 1,
         "a fetch to an external origin is refused"),
        (({}, {"p.js": 'fetch("/api/local")'}), 0, "a same-origin fetch passes"),
        (({}, {"d.html": '<link href="https://fonts.example.com/f.css" rel="stylesheet">'}), 1,
         "an external stylesheet is refused"),
    ]
    bad = 0
    for (artifacts, assets), want, label in cases:
        got = 1 if problems(artifacts, assets) else 0
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

    artifacts = {}
    for name in ARTIFACTS:
        path = root / name
        if path.is_file():
            artifacts[name] = path.read_text(encoding="utf-8", errors="ignore")
    if not artifacts:
        sys.stderr.write(
            f"::error::none of the {len(ARTIFACTS)} shipped artifacts were found -- "
            f"the check would pass without inspecting an installer at all\n"
        )
        return 2

    paths = served_assets(root)
    if not paths:
        sys.stderr.write(
            f"::error::no first-party asset under {STATIC} -- the browser surface "
            f"moved and this check would pass without reading it\n"
        )
        return 2
    assets = {str(p.relative_to(root)): p.read_text(encoding="utf-8", errors="ignore") for p in paths}

    issues = problems(artifacts, assets)
    for issue in issues:
        sys.stderr.write(f"::error::NFR-SEC-16: {issue}\n")
    if issues:
        return 1
    print(
        f"NFR-SEC-16: {len(artifacts)} shipped artifact(s) and {len(assets)} served "
        f"asset(s) reach no vendor-controlled endpoint and auto-load nothing external"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
