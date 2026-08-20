# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""
Shared helpers for listing + reading files under a chat's uploads directory.

Used by:
  - GET /api/uploads/{chat_id}/list (existing HTTP endpoint).
  - sync_chat_resources / the @mcp.resource handler in mcp_resources.py
    (Tier 6 native MCP surface).

Traversal protection reuses security.safe_path / security.sanitize_chat_id —
no new security logic.
"""

import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from security import safe_path, sanitize_chat_id


# Module-level so tests can patch / so app.py re-uses the same value.
BASE_DATA_DIR = Path(os.getenv("BASE_DATA_DIR", "/data"))


@dataclass(frozen=True)
class UploadEntry:
    name: str          # basename — display label
    rel_path: str      # relative to the uploads dir; may contain "/"
    size: int
    modified: float    # st_mtime
    mime_type: str     # resolved: content wins over extension
    declared_mime: str = ""   # what the filename claimed
    sniffed_mime: str = ""    # what the bytes say, "" when unrecognised
    type_mismatch: bool = False


# Magic-byte signatures, longest first so a prefix cannot shadow a longer
# match. Deliberately small: these are the types whose confusion actually
# matters here -- an executable or archive wearing an image extension. A
# fuller table belongs in the parser sub-component (ADR-0026), not in a
# listing helper.
_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"%PDF-", "application/pdf"),
    (b"PK\x03\x04", "application/zip"),
    (b"\x7fELF", "application/x-executable"),
    (b"MZ", "application/x-msdownload"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x1f\x8b", "application/gzip"),
)
_SNIFF_BYTES = 16


def _declared_mime(path: Path) -> str:
    """What the FILENAME claims. Never authoritative on its own."""
    mime, _ = mimetypes.guess_type(path.name)
    return mime or "application/octet-stream"


def sniff_mime(prefix: bytes) -> str:
    """What the BYTES say, or "" when no signature matches.

    Empty is not a failure: most text has no magic number. The caller keeps
    the declared type in that case rather than inventing one.
    """
    for signature, mime in _SIGNATURES:
        if prefix.startswith(signature):
            return mime
    return ""


def classify(path: Path) -> tuple[str, str, str, bool]:
    """(resolved, declared, sniffed, mismatch) for one file.

    Content wins when it is recognised, because the extension is attacker-
    chosen and the bytes are not. The mismatch is REPORTED rather than
    silently resolved -- NFR-SEC-81 asks for the disagreement to be recorded,
    and a caller that only sees the winner cannot tell a renamed executable
    from an ordinary image.
    """
    declared = _declared_mime(path)
    try:
        with path.open("rb") as handle:
            prefix = handle.read(_SNIFF_BYTES)
    except OSError:
        return declared, declared, "", False
    sniffed = sniff_mime(prefix)
    if not sniffed:
        return declared, declared, "", False
    return sniffed, declared, sniffed, sniffed != declared


def _guess_mime(path: Path) -> str:
    """Resolved type for callers that want one value. Kept for compatibility."""
    return classify(path)[0]


def list_chat_uploads(chat_id: str) -> list[UploadEntry]:
    """List files under BASE_DATA_DIR/{chat_id}/uploads/ recursively.

    Returns [] if the directory doesn't exist (newly-created chat).
    Sorted by modification time, newest first — matches the HTTP endpoint's
    existing behavior (app.py:404).
    """
    chat_id = sanitize_chat_id(chat_id)
    uploads_dir = safe_path(BASE_DATA_DIR, chat_id, "uploads")
    if not uploads_dir.exists():
        return []
    entries: list[UploadEntry] = []
    for fp in uploads_dir.rglob("*"):
        if not fp.is_file():
            continue
        rel = fp.relative_to(uploads_dir)
        st = fp.stat()
        resolved, declared, sniffed, mismatch = classify(fp)
        entries.append(UploadEntry(
            name=fp.name,
            rel_path=str(rel),
            size=st.st_size,
            modified=st.st_mtime,
            mime_type=resolved,
            declared_mime=declared,
            sniffed_mime=sniffed,
            type_mismatch=mismatch,
        ))
    entries.sort(key=lambda e: e.modified, reverse=True)
    return entries


def read_chat_upload(chat_id: str, rel_path: str) -> tuple[bytes, str]:
    """Read a single uploaded file. Returns (bytes, mime_type).

    rel_path is whatever list_chat_uploads reported (may contain "/").
    safe_path enforces traversal protection — no `..`, no absolute paths.
    """
    chat_id = sanitize_chat_id(chat_id)
    uploads_dir = safe_path(BASE_DATA_DIR, chat_id, "uploads")
    # safe_path handles multi-segment join with traversal protection.
    file_path = safe_path(uploads_dir, rel_path)
    if not file_path.is_file():
        raise FileNotFoundError(f"No such upload: {chat_id}/{rel_path}")
    return file_path.read_bytes(), _guess_mime(file_path)
