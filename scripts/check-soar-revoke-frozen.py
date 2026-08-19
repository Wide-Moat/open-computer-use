#!/usr/bin/env python3
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
#
# NFR-COMP-27, the inbound half: the SOAR revoke surface stays frozen.
#
# The row asks for a bidirectional SOAR integration -- signed webhook OUT,
# admin API IN. Only the inbound half exists here, and the outbound half is a
# stated boundary rather than an omission: audit-fanin.asyncapi.yaml:29 says the
# webhook is a separate surface, not modelled in that contract. So this checks
# what the tree actually carries and claims nothing about the four outbound
# event payloads, which exist nowhere (see the finding filed alongside this).
#
# What the inbound contract establishes is unusual enough to be worth guarding.
# soar-revoke.openapi.yaml:80-85 is explicit that the SOAR signature is NOT an
# HTTP security scheme: it is an in-body assertion, `soar_signature`, verified
# at the application layer, and it -- not the transport -- is the authority for
# the revoke. The transport gate (host-attested operator ingress) is a second,
# separate layer.
#
# That design puts the authority in a field, and a field can be made optional
# without breaking anything a schema validator notices. Measured with the
# version CI pins, not a newer one: removing `soar_signature` from the request's
# required list and running `@redocly/cli@1.34.2 lint` against the repository's
# own redocly.yaml exits 0 -- "Your API description is valid". A deployment-wide
# DENY-ALL revoke would then be accepted with no signature at all, and every
# gate stays green.
#
# The 401 is checked for the same reason. The contract's response semantics are
# where "unverifiable signature" is expressed; drop that response and the
# document still validates while the refusal path has no declared shape.

import sys
from pathlib import Path

CONTRACT = Path("contracts/openapi/soar-revoke.openapi.yaml")
OPERATION = "/v1/revoke"
SCHEMA = "SoarRevokeRequest"
# The authority field and the two that scope it. Named here rather than read
# from the contract: deriving the expectation from the document under test is
# the comparison failing open.
FROZEN_REQUIRED = ("scope", "soar_signature", "issued_at")
REFUSAL = "401"


def _load(text: str) -> dict:
    import yaml

    document = yaml.safe_load(text)
    return document if isinstance(document, dict) else {}


def request_required(document: dict) -> list[str] | None:
    """The frozen request body's required list, or None when it is gone."""
    schema = document.get("components", {}).get("schemas", {}).get(SCHEMA)
    if not isinstance(schema, dict):
        return None
    required = schema.get("required")
    return list(required) if isinstance(required, list) else None


def operation_responses(document: dict) -> list[str] | None:
    """Declared response codes for the revoke operation, or None when absent."""
    path = document.get("paths", {}).get(OPERATION)
    if not isinstance(path, dict):
        return None
    post = path.get("post")
    if not isinstance(post, dict):
        return None
    responses = post.get("responses")
    return [str(code) for code in responses] if isinstance(responses, dict) else None


def body_is_required(document: dict) -> bool:
    """Whether the operation demands a body at all."""
    post = document.get("paths", {}).get(OPERATION, {}).get("post", {})
    body = post.get("requestBody", {}) if isinstance(post, dict) else {}
    return bool(body.get("required")) if isinstance(body, dict) else False


def problems(required: list[str] | None, responses: list[str] | None, body: bool) -> list[str]:
    """Reasons to refuse. Empty means the surface is still frozen as designed."""
    out = []
    if required is None:
        out.append(
            f"{SCHEMA} no longer declares a required list -- the revoke authority "
            f"({FROZEN_REQUIRED[1]}) would be optional"
        )
    else:
        missing = [f for f in FROZEN_REQUIRED if f not in required]
        if missing:
            out.append(
                f"{SCHEMA} no longer requires {', '.join(missing)} -- a revoke could "
                f"be accepted without the assertion that authorizes it"
            )
    if not body:
        out.append(f"{OPERATION} no longer requires a request body")
    if responses is None:
        out.append(f"{OPERATION} declares no responses")
    elif REFUSAL not in responses:
        out.append(
            f"{OPERATION} no longer declares {REFUSAL} -- the refusal path for an "
            f"unverifiable signature has no declared shape"
        )
    return out


def self_test() -> int:
    full = list(FROZEN_REQUIRED)
    codes = ["200", "400", "401", "409", "500"]
    cases = [
        ((full, codes, True), 0, "the frozen surface as designed passes"),
        (([f for f in full if f != "soar_signature"], codes, True), 1,
         "dropping soar_signature is refused"),
        ((["scope"], codes, True), 1, "dropping two of three is refused"),
        ((None, codes, True), 1, "a schema with no required list is refused"),
        ((full, ["200", "400", "409"], True), 1, "removing the 401 is refused"),
        ((full, None, True), 1, "an operation with no responses is refused"),
        ((full, codes, False), 1, "an optional request body is refused"),
        ((full + ["extra"], codes, True), 0, "adding a field beyond the frozen set is allowed"),
    ]
    bad = 0
    for (required, responses, body), want, label in cases:
        got = 1 if problems(required, responses, body) else 0
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
    path = root / CONTRACT
    if not path.is_file():
        sys.stderr.write(f"::error::{CONTRACT} is missing -- the check cannot judge\n")
        return 2
    try:
        document = _load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # yaml raises several distinct errors
        sys.stderr.write(f"::error::{CONTRACT} is not readable YAML ({exc}) -- refusing\n")
        return 2
    if not document:
        sys.stderr.write(f"::error::{CONTRACT} parsed empty -- refusing rather than passing\n")
        return 2

    issues = problems(
        request_required(document), operation_responses(document), body_is_required(document)
    )
    for issue in issues:
        sys.stderr.write(f"::error::NFR-COMP-27: {issue}\n")
    if issues:
        return 1
    print(
        f"NFR-COMP-27 (inbound half): {OPERATION} requires a body carrying "
        f"{', '.join(FROZEN_REQUIRED)} and declares {REFUSAL}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
