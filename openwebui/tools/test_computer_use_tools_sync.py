# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""Unit tests for the chat-attachment sync into the guest (D6).

A re-attached file whose bytes changed but whose name and size did not must
still reach the guest. Two independent things have to hold for that, and
neither was asserted anywhere in the repository before this file:

  * the dedup arm compares the content digest, not name+size, so an edit is
    not mistaken for a copy already present;
  * the create request carries ``overwrite_existing`` true, because F9 create
    defaults to refusing an existing path -- with the flag dropped the
    re-upload 409s, the exception lands in the error counter, and the guest
    goes on reading the stale bytes.

Dropping either one leaves the other looking correct. Both are therefore
asserted from the multipart body the client actually posts, not from the
source text.

Run: python3 -m pytest openwebui/tools/test_computer_use_tools_sync.py -v
"""

import hashlib
import importlib.util
import json
import os
import sys
import types

import pytest

_TOOLS_PATH = os.path.join(os.path.dirname(__file__), "computer_use_tools.py")
_FS_ID = "fs-fleet-test"
_URL = "https://filestore:7080"


class _Resp:
    """Stand-in for a requests.Response that still fails on a failure code."""

    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeRequests:
    """Records what the client sends; answers the dedup list with `listing`."""

    def __init__(self, listing):
        self._listing = listing
        self.posts = []

    def get(self, url, **kwargs):
        return _Resp({"data": self._listing})

    def post(self, url, **kwargs):
        self.posts.append(kwargs)
        return _Resp({}, 201)


def _params_of(post):
    """Pull the params JSON out of a recorded multipart body.

    The params part is the one whose filename slot is None; the payload part
    carries a real filename, which is what tells the two apart.
    """
    for _field, part in post["files"]:
        if part[0] is None:
            return json.loads(part[1])
    raise AssertionError(f"no params part in the multipart body: {post!r}")


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _remote(name, content: bytes, digest=True):
    """One F9 list entry. `digest=False` models a pre-D6 server."""
    return {
        "filename": name,
        "size_bytes": len(content),
        "sha256": _sha256(content) if digest else None,
    }


def _attachment(tmp_path, name, content: bytes):
    path = tmp_path / name
    path.write_bytes(content)
    return {"name": name, "path": str(path)}


@pytest.fixture
def sync(monkeypatch):
    """Load the tool module with its two runtime imports neutralised.

    Both are imported inside the function under test, so placing them in
    sys.modules is what reaches it. Storage.get_file is identity here: these
    attachments already sit on disk.
    """
    provider = types.ModuleType("open_webui.storage.provider")

    class _Storage:
        @staticmethod
        def get_file(path):
            return path

    provider.Storage = _Storage
    monkeypatch.setitem(sys.modules, "open_webui", types.ModuleType("open_webui"))
    monkeypatch.setitem(
        sys.modules, "open_webui.storage", types.ModuleType("open_webui.storage")
    )
    monkeypatch.setitem(sys.modules, "open_webui.storage.provider", provider)

    spec = importlib.util.spec_from_file_location("ocu_tools_sync", _TOOLS_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._sync_uploaded_files


def test_edited_bytes_of_the_same_size_are_reuploaded_with_overwrite(
    tmp_path, monkeypatch, sync
):
    """The #181 keystone: same name, same size, different bytes.

    Both halves are asserted here because either one alone still loses the
    edit -- a name+size dedup never posts, and a post without the overwrite
    flag is refused.
    """
    name = "report.txt"
    stored = b"A" * 64
    edited = b"B" * 64
    assert len(stored) == len(edited), (
        "the sizes must be equal or this test proves nothing about the digest "
        "arm -- a size difference would make even name+size dedup re-upload"
    )
    assert _sha256(stored) != _sha256(edited)

    fake = _FakeRequests([_remote(name, stored)])
    monkeypatch.setitem(sys.modules, "requests", fake)

    result = sync(_URL, _FS_ID, [_attachment(tmp_path, name, edited)])

    assert result == {"synced": 1, "skipped": 0, "errors": 0}, (
        f"the edit did not reach the guest: {result} -- a skip here is the "
        "name+size dedup regression, an error is the 409 the missing "
        "overwrite flag produces"
    )
    assert len(fake.posts) == 1
    params = _params_of(fake.posts[0])
    assert params["overwrite_existing"] is True, (
        "create omits overwrite_existing, so F9 refuses the existing path and "
        f"the guest keeps the stale bytes: {params}"
    )
    assert params["path"] == f"/{name}"


def test_a_new_file_is_created_with_overwrite_too(tmp_path, monkeypatch, sync):
    """The flag is unconditional. A first upload takes the same code path, so
    conditioning the flag on 'the object already exists' would leave this green
    while breaking the re-upload above -- assert it on both routes."""
    fake = _FakeRequests([])
    monkeypatch.setitem(sys.modules, "requests", fake)

    result = sync(_URL, _FS_ID, [_attachment(tmp_path, "fresh.txt", b"hello")])

    assert result == {"synced": 1, "skipped": 0, "errors": 0}, result
    assert _params_of(fake.posts[0])["overwrite_existing"] is True


def test_identical_bytes_are_skipped_and_nothing_is_posted(
    tmp_path, monkeypatch, sync
):
    """The negative control. Without it the two assertions above are satisfied
    by a client that posts unconditionally, which would re-upload every
    attachment on every turn."""
    name = "report.txt"
    content = b"A" * 64

    fake = _FakeRequests([_remote(name, content)])
    monkeypatch.setitem(sys.modules, "requests", fake)

    result = sync(_URL, _FS_ID, [_attachment(tmp_path, name, content)])

    assert result == {"synced": 0, "skipped": 1, "errors": 0}, result
    assert fake.posts == [], "an unchanged attachment was re-uploaded"


def test_a_server_without_a_digest_falls_back_to_name_and_size(
    tmp_path, monkeypatch, sync
):
    """The compat window: against a server that exposes no sha256 the client
    keeps the legacy name+size skip. This is the arm that loses a same-size
    edit, which is why the digest arm exists -- pin it so the fallback is a
    stated compromise rather than an accident."""
    name = "report.txt"
    stored = b"A" * 64
    edited = b"B" * 64

    fake = _FakeRequests([_remote(name, stored, digest=False)])
    monkeypatch.setitem(sys.modules, "requests", fake)

    result = sync(_URL, _FS_ID, [_attachment(tmp_path, name, edited)])

    assert result == {"synced": 0, "skipped": 1, "errors": 0}, result
    assert fake.posts == []


def test_a_size_change_is_uploaded_even_without_a_digest(
    tmp_path, monkeypatch, sync
):
    """Keeps the fallback above from reading as 'a digest-less server never
    uploads': the legacy arm still notices a size change."""
    name = "report.txt"

    fake = _FakeRequests([_remote(name, b"A" * 64, digest=False)])
    monkeypatch.setitem(sys.modules, "requests", fake)

    result = sync(_URL, _FS_ID, [_attachment(tmp_path, name, b"B" * 128)])

    assert result == {"synced": 1, "skipped": 0, "errors": 0}, result
    assert _params_of(fake.posts[0])["overwrite_existing"] is True
