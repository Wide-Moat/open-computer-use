# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""Centralized security utilities for path validation and input sanitization."""
import os
import re
from pathlib import Path

from fastapi import HTTPException


CHAT_ID = re.compile(r"^[a-z0-9_-]{1,64}$")

# Characters that terminate or split a header value. A header value cannot
# legitimately contain any of them, so stripping is safe regardless of how the
# downstream consumer parses -- which matters here because the consumer is
# Claude Code inside the guest, and its splitting rule is not defined in this
# repository (#603).
_HEADER_UNSAFE = re.compile(r"[\r\n\x00]")


def header_safe(value: str) -> str:
    """Strip characters that could add or truncate a header.

    Applied where a request-supplied value is interpolated into a header the
    guest sends upstream. It is deliberately a STRIP rather than a rejection:
    the caller is building a diagnostic tagging header, and failing a whole
    session because a display name contained a newline would be a worse
    outcome than tagging it with the newline removed.
    """
    return _HEADER_UNSAFE.sub("", value)


def sanitize_chat_id(chat_id: str) -> str:
    """Validate chat_id against a character class, not a list of bad characters.

    The previous rule rejected '..', '/', '\\' and NUL -- path traversal only.
    Everything else passed, and chat_id reaches an HTML template: `/preview/{id}`
    interpolates it four times. Those four go through json.dumps, so the value
    cannot escape its JS string today, and CodeQL's py/reflective-xss on
    app.py:1147 is not exploitable as written (#495).

    What made it safe was every interpolation staying json.dumps'd -- a property
    of thirty-two call sites rather than of the input. A quote-bearing id was
    accepted:

        'x" onload="alert(1)'   accepted by the old rule
        'a<script>alert(1)'     rejected, but only because of the closing tag's
                                slash, not because anything looked for markup

    An allow-list moves the guarantee to the data. Measured against every
    chat_id literal in the repository -- UUIDs, "default", "abc123",
    "test-123" -- the class accepts all of them and rejects the traversal and
    markup cases the old rule was reaching for.
    """
    normalized = chat_id.strip().lower()
    if not CHAT_ID.fullmatch(normalized):
        raise HTTPException(status_code=400, detail="Invalid chat_id")
    return normalized


def safe_path(base_dir: Path, *segments: str) -> Path:
    """Construct a path from untrusted segments and verify it stays within base_dir.

    Uses os.path.realpath + startswith — pattern natively recognized by CodeQL
    as a containment check barrier for py/path-injection (pathlib Path.resolve
    is not modeled as a sanitizer by CodeQL).
    Resolves symlinks via realpath to prevent symlink escape attacks.
    Raises HTTPException(403) on traversal attempt.
    Returns the resolved absolute path.
    """
    constructed = str(base_dir)
    for seg in segments:
        constructed = os.path.join(constructed, seg)

    resolved_str = os.path.realpath(constructed)
    base_str = os.path.realpath(str(base_dir))

    # os.sep suffix prevents prefix collision: /data should NOT match /data-evil
    if resolved_str != base_str and not resolved_str.startswith(base_str + os.sep):
        raise HTTPException(
            status_code=403, detail="Access denied: path traversal detected"
        )
    return Path(resolved_str)
