# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""Harness self-integrity: the create-rate window retry, and who must NOT get it.

Control caps session creates per caller per minute. This whole suite runs under
one caller identity, so a fast stretch of tests exhausts the window; control
refuses with 409 and the gateway turns every refusal into the same leak-free
502. Eight tests died that way in one run -- five j, one k, two m -- all with
symptoms that read like storage, admin and browser defects.

Two halves have to hold, and they pull in opposite directions:

  * a test that needs a working session waits out the window and re-issues;
  * a test that REQUIRES a denial must not, because A6 sends an off-allow-list
    image and E's overflow seeds the concurrency counter to the tier cap. A
    minute of waiting cannot turn either into a success on purpose, but it is
    long enough for the idle reaper to release the seeded row, which turns a
    required denial into a live session and breaks the assertion.

Neither half is visible from the other's code, so both are pinned here.

Run: python3 -m pytest test_z_rate_window_retry.py -v
"""

import time

import test_i_mcp_surface as I
from backends.fleet import FleetBackend


def _no_sleep(monkeypatch, log):
    monkeypatch.setattr(time, "sleep", lambda s: log.append(s))


def test_a_502_is_retried_across_the_window(monkeypatch):
    calls, slept = [], []

    def fake_once(chat_id, body, timeout=40):
        calls.append(chat_id)
        return (502, None) if len(calls) == 1 else (200, {"result": {}})

    monkeypatch.setattr(I, "_call_once", fake_once)
    _no_sleep(monkeypatch, slept)

    status, parsed = I._call("chat-1", "{}")

    assert status == 200, f"a 502 that clears on retry must surface as 200, got {status}"
    assert len(calls) == 2, f"expected one retry, the call was made {len(calls)}x"
    assert len(slept) == 1 and 0 < slept[0] <= 61, (
        f"the wait must cross a minute boundary and no more: {slept}"
    )


def test_a_clean_call_never_waits(monkeypatch):
    """Without this the retry could be an unconditional double-call that happens
    to end in a 200 -- and every green run would cost an extra minute."""
    calls, slept = [], []

    def fake_once(chat_id, body, timeout=40):
        calls.append(chat_id)
        return 200, {"result": {}}

    monkeypatch.setattr(I, "_call_once", fake_once)
    _no_sleep(monkeypatch, slept)

    assert I._call("chat-2", "{}")[0] == 200
    assert len(calls) == 1, "a successful call must not be re-issued"
    assert slept == [], "a successful call must not sleep"


def test_a_persistent_502_still_surfaces(monkeypatch):
    """The retry bounds itself. A 502 whose cause outlives the window has to
    reach the assertion, or the harness would hide a real forward failure."""
    calls, slept = [], []

    def fake_once(chat_id, body, timeout=40):
        calls.append(chat_id)
        return 502, None

    monkeypatch.setattr(I, "_call_once", fake_once)
    _no_sleep(monkeypatch, slept)

    status, _ = I._call("chat-3", "{}")

    assert status == 502, "a refusal that outlives the window must not be swallowed"
    assert len(calls) == 1 + I._RATE_RETRIES, (
        f"expected {1 + I._RATE_RETRIES} attempts, got {len(calls)}"
    )
    assert len(slept) == I._RATE_RETRIES


def test_the_wait_is_bounded_to_one_minute():
    assert 0 < I._seconds_to_next_minute() <= 61


def test_a_session_the_test_needs_is_retried(monkeypatch):
    backend = FleetBackend()
    calls, slept = [], []

    def fake_curl(*args, **kwargs):
        calls.append(1)
        return (409, {}) if len(calls) == 1 else (201, {"key": "session-key-1"})

    monkeypatch.setattr(backend, "_curl", fake_curl)
    _no_sleep(monkeypatch, slept)

    ref = backend.create_storage_session()

    assert ref.status == "active" and ref.key == "session-key-1", (
        f"a create refused only by the rate window must succeed on retry: {ref}"
    )
    assert len(calls) == 2


def test_a_denial_the_test_requires_is_not_waited_out(monkeypatch):
    """The sibling guard. Flipping the admission-probe verb to retry would leave
    every other test here green while silently breaking A6 and E's overflow."""
    backend = FleetBackend()
    calls, slept = [], []

    def fake_curl(*args, **kwargs):
        calls.append(1)
        return 409, {}

    monkeypatch.setattr(backend, "_curl", fake_curl)
    _no_sleep(monkeypatch, slept)

    ref = backend.create_session(image="ghcr.io/attacker/not-on-allowlist:latest")

    assert ref.status == "denied:409", f"the denial must reach the caller: {ref}"
    assert len(calls) == 1, (
        "the admission-probe verb re-issued a create it was told to leave "
        "refused -- A6 and the E overflow depend on the FIRST answer"
    )
    assert slept == [], "the admission-probe verb must not wait out a window"
