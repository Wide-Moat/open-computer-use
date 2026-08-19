#!/usr/bin/env python3
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
#
# NFR-SEC-26, the contract half: no operator request body names the acting
# caller.
#
# The session-binding requirement is deliberately NOT named here. This file
# originally cited it alongside SEC-26, and the coverage scanner counted it as
# armed on the strength of the mention -- an id named in a comment is not an
# assertion, and that row asks for far more than a contract shape. Naming it
# would have claimed a check that does not exist.
#
# The operator REST surface establishes identity out of band. Its only security
# scheme is operatorPeerCred -- the caller is derived from the peer credential
# of the host-owned 0700 operator socket -- and the file states the consequence
# directly (operator-rest.openapi.yaml:13-20): a request body carries only
# HINTS, and no body field names a caller, tenant, session-authority or
# container_name id, because a body-supplied id is a hint and never the
# authority that binds or addresses a session.
#
# That is a property a schema validator cannot see. Adding `caller_id` to a
# request body is a well-formed OpenAPI change; the document still lints, and
# the surface now offers a field that looks authoritative to any implementer
# reading the contract. The failure is that somebody downstream binds to it.
#
# Two things are checked, because the rule depends on both:
#
#   1. The transport scheme still exists and is the only one. If a second scheme
#      appears -- a bearer token, an API key header -- identity has moved into
#      the request, and the hint-only rule loses the thing that justifies it.
#   2. No request-body schema carries a caller-identity field name.
#
# `tenant` is deliberately NOT forbidden outright, and that distinction was
# measured rather than assumed. MCPKeyCreateRequest carries a `tenant` property
# whose description says it is the scope the new key is bound to and "never the
# acting caller's identity". Forbidding the word would report a violation the
# contract explicitly reasons about; what is forbidden is a field that names WHO
# IS CALLING.

import sys
from pathlib import Path

CONTRACT = Path("contracts/openapi/operator-rest.openapi.yaml")
TRANSPORT_SCHEME = "operatorPeerCred"

# Field names that would assert the acting caller. Chosen as names an
# implementer would bind to, not as substrings: `tenant` alone is a scope and is
# permitted (see above), while `acting_tenant` names the caller.
CALLER_FIELDS = (
    "caller",
    "caller_id",
    "acting_caller",
    "acting_tenant",
    "principal",
    "principal_id",
    "actor_id",
    "container_name",
    "session_authority",
    "on_behalf_of",
)


def _load(text: str) -> dict:
    import yaml

    document = yaml.safe_load(text)
    return document if isinstance(document, dict) else {}


def security_schemes(document: dict) -> list[str]:
    """Declared security schemes, in name order."""
    schemes = document.get("components", {}).get("securitySchemes")
    return sorted(schemes) if isinstance(schemes, dict) else []


def body_schema_names(document: dict) -> set[str]:
    """Component schemas reachable as a request body on any operation."""
    names: set[str] = set()
    for path in (document.get("paths") or {}).values():
        if not isinstance(path, dict):
            continue
        for operation in path.values():
            if not isinstance(operation, dict):
                continue
            content = (operation.get("requestBody") or {}).get("content") or {}
            for media in content.values():
                ref = (media or {}).get("schema", {}).get("$ref", "")
                if ref.startswith("#/components/schemas/"):
                    names.add(ref.rsplit("/", 1)[-1])
    return names


def caller_fields_in_bodies(document: dict) -> list[str]:
    """Caller-identity field names found on request-body schemas."""
    schemas = document.get("components", {}).get("schemas") or {}
    reachable = body_schema_names(document)
    found = []
    seen: set[str] = set()

    def visit(name: str) -> None:
        if name in seen or name not in schemas:
            return
        seen.add(name)
        schema = schemas[name]
        if not isinstance(schema, dict):
            return
        for field, spec in (schema.get("properties") or {}).items():
            if field.lower() in CALLER_FIELDS:
                found.append(f"{name}.{field}")
            # Nested intents are bodies too -- CreateRequest reaches MountIntent
            # and EgressPolicy by $ref, and a caller field there is as binding.
            ref = spec.get("$ref", "") if isinstance(spec, dict) else ""
            if ref.startswith("#/components/schemas/"):
                visit(ref.rsplit("/", 1)[-1])

    for name in sorted(reachable):
        visit(name)
    return sorted(found)


def problems(schemes: list[str], caller_fields: list[str]) -> list[str]:
    """Reasons to refuse. Empty means identity is still out of band."""
    out = []
    if TRANSPORT_SCHEME not in schemes:
        out.append(
            f"the {TRANSPORT_SCHEME} transport scheme is gone -- host-attested "
            f"identity is what makes hint-only bodies safe"
        )
    extra = [s for s in schemes if s != TRANSPORT_SCHEME]
    if extra:
        out.append(
            f"a second security scheme appeared ({', '.join(extra)}) -- identity "
            f"has moved into the request, which the hint-only rule forbids"
        )
    for field in caller_fields:
        out.append(
            f"{field} names the acting caller in a request body -- a body-supplied "
            f"id is a hint, never the authority that binds a session"
        )
    return out


def self_test() -> int:
    cases = [
        (([TRANSPORT_SCHEME], []), 0, "one transport scheme and hint-only bodies pass"),
        (([TRANSPORT_SCHEME], ["CreateRequest.caller_id"]), 1, "a caller_id in a body is refused"),
        (([TRANSPORT_SCHEME, "bearerAuth"], []), 1, "a second security scheme is refused"),
        (([], []), 1, "a removed transport scheme is refused"),
        (([TRANSPORT_SCHEME], ["MountIntent.container_name"]), 1, "a nested intent is checked too"),
    ]
    bad = 0
    for (schemes, fields), want, label in cases:
        got = 1 if problems(schemes, fields) else 0
        ok = got == want
        bad += 0 if ok else 1
        print(f"  {'ok' if ok else 'FAIL'}: {label}")

    # The extractor, on a constructed document. Without this the traversal is
    # untested: on the shipped contract it returns empty by construction, so a
    # stub of it would pass unnoticed.
    doc = {
        "paths": {
            "/x": {
                "post": {
                    "requestBody": {
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/A"}}}
                    }
                }
            }
        },
        "components": {
            "schemas": {
                "A": {"properties": {"hint": {"type": "string"}, "nested": {"$ref": "#/components/schemas/B"}}},
                "B": {"properties": {"caller_id": {"type": "string"}}},
                "Unreachable": {"properties": {"principal": {"type": "string"}}},
            }
        },
    }
    found = caller_fields_in_bodies(doc)
    if found != ["B.caller_id"]:
        bad += 1
        sys.stderr.write(f"self-test FAIL: traversal returned {found}, expected ['B.caller_id']\n")
    else:
        print("  ok: a nested body field is found and an unreachable schema is not")

    if bad:
        print(f"self-test: {bad} case(s) failed")
        return 1
    print("self-test ok: 6 cases")
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
    except Exception as exc:
        sys.stderr.write(f"::error::{CONTRACT} is not readable YAML ({exc}) -- refusing\n")
        return 2
    if not document.get("paths"):
        sys.stderr.write(
            f"::error::{CONTRACT} declares no paths -- the check would pass without "
            f"reading a single body\n"
        )
        return 2

    schemes = security_schemes(document)
    fields = caller_fields_in_bodies(document)
    issues = problems(schemes, fields)
    for issue in issues:
        sys.stderr.write(f"::error::NFR-SEC-26: {issue}\n")
    if issues:
        return 1
    print(
        f"NFR-SEC-26: identity is {TRANSPORT_SCHEME} only, and "
        f"{len(body_schema_names(document))} request-body schema(s) name no acting caller"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
