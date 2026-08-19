#!/usr/bin/env python3
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
#
# NFR-SEC-79, the contract half: a file-activity audit event carries the OCU
# mandatory set, and both contracts that state it agree.
#
# The row asks that every file operation on either storage surface commit a
# chain-linked OCSF File System Activity event. The chain-linkage half is not
# checkable here and deliberately not claimed: audit-fanin.asyncapi.yaml:230
# says prev_hash/chain_hash are authored by the pipeline at ingest and are NOT
# part of the publish payload. What a source must supply is the ordering input
# and the mandatory fields, and that IS on the wire.
#
# Two documents state the same requirement and nothing compared them:
#
#   - audit-fanin.asyncapi.yaml carries an allOf overlay on the vendored OCSF
#     class, named for NFR-SEC-79, making filesystem_id / intent / downloadable
#     required on top of the base class.
#   - file-artifact-api.schema.json defines FileActivityEvent with the same
#     three in its own required list, and pins class_uid to const 1001.
#
# Either can be relaxed alone without breaking anything else. Drop `required`
# from the overlay and the AsyncAPI still validates, the OCSF class file is
# untouched, and the schema validator beside this one still passes -- while a
# producer may now omit the disposition fields that decide whether a file left
# the boundary. That is a silent loss of an audit property, which is the failure
# this check exists to make loud.
#
# The existing ocsf-class-identity gate covers a different statement: that the
# message title's class uid matches the vendored class file. It says nothing
# about which fields are mandatory, so this does not duplicate it.

import json
import re
import sys
from pathlib import Path

ASYNCAPI = Path("contracts/audit/audit-fanin.asyncapi.yaml")
STORAGE = Path("contracts/storage/file-artifact-api.schema.json")
DEFINITION = "FileActivityEvent"
CLASS_UID = 1001

# The disposition fields NFR-SEC-79 makes non-optional. Named rather than
# derived from either document: deriving them from one would make this check
# agree with whichever it read, which is the comparison failing open.
MANDATORY = ("filesystem_id", "intent", "downloadable")


def overlay_required(text: str) -> list[str] | None:
    """The required list of the NFR-SEC-79 overlay, or None when it is gone.

    Anchored on the overlay's own description rather than on a line number: the
    file has several `required:` lines and the neighbouring messages carry their
    own overlays.
    """
    marker = re.search(r"NFR-SEC-79 required-field overlay", text)
    if not marker:
        return None
    tail = text[marker.end() :]
    found = re.search(r"^\s*required:\s*\[([^\]]*)\]", tail, re.M)
    if not found:
        return None
    return [item.strip() for item in found.group(1).split(",") if item.strip()]


def storage_required(document: dict) -> list[str] | None:
    """FileActivityEvent's required list from the storage schema."""
    definition = document.get("$defs", {}).get(DEFINITION)
    if not isinstance(definition, dict):
        return None
    required = definition.get("required")
    return list(required) if isinstance(required, list) else None


def storage_class_uid(document: dict) -> int | None:
    """The class the storage schema pins FileActivityEvent to."""
    definition = document.get("$defs", {}).get(DEFINITION, {})
    if not isinstance(definition, dict):
        return None
    spec = definition.get("properties", {}).get("class_uid", {})
    value = spec.get("const") if isinstance(spec, dict) else None
    return value if isinstance(value, int) else None


def problems(overlay: list[str] | None, storage: list[str] | None, uid: int | None) -> list[str]:
    """Reasons to refuse. Empty means both contracts still carry the property."""
    out = []
    if overlay is None:
        out.append(
            f"the NFR-SEC-79 overlay is gone from {ASYNCAPI.name} -- a producer may "
            f"omit the disposition fields and the contract still validates"
        )
    else:
        missing = [f for f in MANDATORY if f not in overlay]
        if missing:
            out.append(f"{ASYNCAPI.name} overlay no longer requires {', '.join(missing)}")
    if storage is None:
        out.append(f"{STORAGE.name} no longer defines {DEFINITION} with a required list")
    else:
        missing = [f for f in MANDATORY if f not in storage]
        if missing:
            out.append(f"{STORAGE.name} {DEFINITION} no longer requires {', '.join(missing)}")
    if uid is None:
        out.append(f"{STORAGE.name} no longer pins {DEFINITION}.class_uid")
    elif uid != CLASS_UID:
        out.append(
            f"{STORAGE.name} pins {DEFINITION}.class_uid to {uid}, not the OCSF "
            f"File System Activity class {CLASS_UID}"
        )
    return out


def self_test() -> int:
    full = list(MANDATORY) + ["outcome"]
    cases = [
        ((full, full, CLASS_UID), 0, "both contracts carrying the set agree"),
        ((None, full, CLASS_UID), 1, "a deleted overlay is refused"),
        ((["filesystem_id"], full, CLASS_UID), 1, "an overlay missing two fields is refused"),
        ((full, ["filesystem_id", "intent"], CLASS_UID), 1, "storage dropping downloadable is refused"),
        ((full, None, CLASS_UID), 1, "a removed FileActivityEvent is refused"),
        ((full, full, 1007), 1, "a class_uid repointed at another OCSF class is refused"),
        ((full, full, None), 1, "an unpinned class_uid is refused"),
    ]
    bad = 0
    for (overlay, storage, uid), want, label in cases:
        got = 1 if problems(overlay, storage, uid) else 0
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
    for path in (ASYNCAPI, STORAGE):
        if not (root / path).is_file():
            sys.stderr.write(f"::error::{path} is missing -- the check cannot judge\n")
            return 2
    try:
        document = json.loads((root / STORAGE).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"::error::{STORAGE} is not readable JSON ({exc}) -- refusing\n")
        return 2

    overlay = overlay_required((root / ASYNCAPI).read_text(encoding="utf-8"))
    storage = storage_required(document)
    uid = storage_class_uid(document)

    issues = problems(overlay, storage, uid)
    for issue in issues:
        sys.stderr.write(f"::error::NFR-SEC-79: {issue}\n")
    if issues:
        return 1
    print(
        f"NFR-SEC-79 (contract half): both contracts require "
        f"{', '.join(MANDATORY)} on a File System Activity ({CLASS_UID}) event"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
