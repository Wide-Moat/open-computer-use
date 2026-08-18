#!/usr/bin/env python3
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
#
# NFR-FLEX-14: MCP is OCU's inbound wire protocol, and the version the contract
# freezes is one the pinned library can actually speak.
#
# The contract directory is named for a protocol version --
# contracts/mcp/2025-06-18/ -- and nothing tied that name to the runtime. The
# version is not written in OCU's code at all: it comes from the `mcp` pin in
# computer-use-server/requirements.txt, whose SUPPORTED_PROTOCOL_VERSIONS list
# decides what the server will negotiate.
#
# So the failure this catches is a silent one. Bump the pin to a release that
# drops 2025-06-18 and the contract still parses, every schema gate stays green,
# and the frozen surface describes a protocol the server can no longer speak.
# Nothing else in the repository compares the two.
#
# Measured when this was written: mcp==1.27.0 supports
# ['2024-11-05', '2025-03-26', '2025-06-18', '2025-11-25'], so the contract is
# satisfiable today. The `2024-11-05` string in app.py is a documentation
# EXAMPLE of an initialize request, not the version the server declares -- a
# grep for the version would report a contradiction that does not exist.

import re
import sys
from pathlib import Path

CONTRACTS = Path("contracts/mcp")
REQUIREMENTS = Path("computer-use-server/requirements.txt")
VERSION_DIR = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def contract_versions(root: Path) -> list[str]:
    """Protocol versions the contract tree freezes, from its directory names."""
    base = root / CONTRACTS
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir() and VERSION_DIR.match(p.name))


def pinned_mcp(root: Path) -> str | None:
    """The mcp version requirements.txt pins, or None when it is not pinned."""
    path = root / REQUIREMENTS
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        match = re.match(r"^mcp==([0-9][^\s#]*)", stripped)
        if match:
            return match.group(1)
    return None


def unsupported(contract: list[str], supported: list[str]) -> list[str]:
    """Contract versions the library cannot speak. Empty means agreement."""
    return sorted(v for v in contract if v not in supported)


def self_test() -> int:
    cases = [
        (["2025-06-18"], ["2024-11-05", "2025-06-18"], [], "a contract version the library supports"),
        (["2025-06-18"], ["2024-11-05", "2025-11-25"], ["2025-06-18"], "a version dropped by a bump"),
        ([], ["2025-06-18"], [], "no contract directory is not a violation"),
        (["2025-06-18", "2099-01-01"], ["2025-06-18"], ["2099-01-01"], "one of two is reported"),
    ]
    bad = 0
    for contract, supported, want, label in cases:
        got = unsupported(contract, supported)
        ok = got == want
        bad += 0 if ok else 1
        print(f"  {'ok' if ok else 'FAIL'}: {label} -> {got or 'none'}")
    if bad:
        print(f"self-test: {bad} case(s) failed")
        return 1
    print(f"self-test ok: {len(cases)} cases")
    return 0


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--self-test":
        return self_test()
    root = Path(argv[0]) if argv else Path(".")

    versions = contract_versions(root)
    if not versions:
        print(f"::notice::no versioned directory under {CONTRACTS} -- nothing to compare")
        return 0

    pin = pinned_mcp(root)
    if pin is None:
        sys.stderr.write(
            f"::error::{REQUIREMENTS} does not pin mcp==, so the protocol version the "
            "server negotiates is whatever resolves that day\n"
        )
        return 1

    try:
        from mcp.shared.version import SUPPORTED_PROTOCOL_VERSIONS as supported
    except ImportError:
        # Not a pass. Unreadable is a third outcome: reporting "supported" here
        # would certify agreement this run never established.
        print(
            f"::notice::the mcp package is not importable here, so the {len(versions)} "
            f"contract version(s) could not be checked against the pin ({pin}). "
            f"UNVERIFIED on this run rather than confirmed."
        )
        return 0

    missing = unsupported(versions, list(supported))
    for version in missing:
        sys.stderr.write(
            f"::error::contracts/mcp/{version}/ freezes a protocol version that "
            f"mcp=={pin} cannot speak (supports {', '.join(supported)}). The frozen "
            f"surface describes a protocol the server will not negotiate.\n"
        )
    if missing:
        return 1
    print(
        f"NFR-FLEX-14: every contract version ({', '.join(versions)}) is spoken by "
        f"the pinned mcp=={pin}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
