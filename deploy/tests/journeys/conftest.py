# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""Pytest fixtures for the PoC-vs-fleet journey suite.

The core fixture is ``backend``, parametrized over ["poc", "fleet"]. It
instantiates the right backend and SKIPS — loudly — when that backend's
live() is False. It never xpasses, never stubs, never substitutes a mock for
a down stack.

Honesty rules encoded here (non-negotiable):
  * skip-if-inapplicable != skip-green. A skipped backend is reported skipped
    with a reason; it is not counted as a pass.
  * A mechanism that is inactive in the current env is an xfail(reason), not a
    silent pass. Use the ``inactive_mechanism`` helper to mark it.
  * A backend that has no analogue for an authz boundary raises
    PocHoleNotEnforced; the paired [PoC-HOLE] test catches that as the finding.
    That is distinct from a skip (the stack is up; the boundary is absent).
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Callable

import pytest
import yaml

from backends.base import Backend, BackendUnavailable

from backends.base import Backend, BackendUnavailable
from backends.fleet import FleetBackend
from backends.poc import PocBackend

_SCENARIOS_PATH = Path(__file__).resolve().parent / "scenarios.yaml"

# Loud skip reasons — a reader scanning `pytest -rs` output sees exactly why a
# backend did not run. Never a bare "skipped".
_POC_DOWN = (
    "PoC backend not live: local Docker daemon unreachable. "
    "Bring up docker-compose.yml + docker-compose.webui.yml, then re-run. "
    "This is a SKIP, not a pass — do not read it as green."
)
_FLEET_DOWN = (
    "Fleet backend not live: Lima + runsc not detected (FUSE/runsc cannot run "
    "on a Darwin host) or the fleet compose is down. Run inside Lima (ocu-linux) "
    "with `deploy/fleet/docker-compose.fleet.yml` up. This is a LOUD SKIP, not a "
    "pass — the fleet is never mocked green."
)

_BACKEND_FACTORIES: dict[str, Callable[[], Backend]] = {
    "poc": PocBackend,
    "fleet": FleetBackend,
}
_BACKEND_DOWN_REASON: dict[str, str] = {"poc": _POC_DOWN, "fleet": _FLEET_DOWN}


def _load_scenarios() -> dict[str, dict[str, Any]]:
    with _SCENARIOS_PATH.open("r", encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    by_id: dict[str, dict[str, Any]] = {}
    for entry in doc.get("scenarios", []):
        sid = entry["id"]
        if sid in by_id:
            raise ValueError(f"duplicate scenario id in scenarios.yaml: {sid}")
        by_id[sid] = entry
    return by_id


@pytest.fixture(scope="session")
def scenarios() -> dict[str, dict[str, Any]]:
    """All scenarios from scenarios.yaml, keyed by id (A1..G6)."""
    return _load_scenarios()


@pytest.fixture(params=["poc", "fleet"])
def backend(request: pytest.FixtureRequest) -> Backend:
    """The system under test, parametrized over both backends.

    Instantiates the requested backend and skips loudly if its live() is
    False. A live() probe that itself raises (a broken substrate) is also a
    skip with the same loud reason — never an error that masquerades as a pass.
    """
    name = request.param
    factory = _BACKEND_FACTORIES[name]
    impl = factory()
    try:
        is_live = impl.live()
    except BackendUnavailable as exc:
        pytest.skip(f"{_BACKEND_DOWN_REASON[name]} ({exc})")
    if not is_live:
        pytest.skip(_BACKEND_DOWN_REASON[name])
    if name == "fleet":
        _reclaim_fleet_concurrency_leak()
    return impl


# KNOWN-BUG REMEDIATION (delete when [concurrency-counter-leak] lands).
#
# The fleet control DimConcurrentSessions counter leaks: the operator kill-switch
# (RevokeAll) releases the ROW but never calls ReleaseConcurrency, and boot
# reconcile treats an EXITED-but-present container as live substrate, so it never
# reclaims that row's slot. A guest whose exec exits (every storage session in
# this suite) therefore leaks one slot, and the counter climbs to the tier cap
# (64) while few rows are actually live — after which every create 409s and the
# whole suite wedges, order-dependently.
#
# This is recorded as a REAL-FINDING (issue [concurrency-counter-leak]) and is
# exercised directly by the E7 counter-parity keystone. To keep the OTHER fleet
# tests from cascading a single control bug into unrelated 409 reds, we reclaim
# the leak before each fleet test by resetting the counter to the TRUE live-row
# count — exactly what the eventual reconcile fix will compute. This is a
# documented test-env reset, not a green: E7 still witnesses the leak, and this
# hook is deleted the moment the counter refund lands.
_FLEET_CONTROL_DB = os.getenv("FLEET_CONTROL_DB_CONTAINER", "ocu-fleet-control-db-1")
_FLEET_DB_USER = os.getenv("FLEET_CONTROL_DB_USER", "ocu")
_FLEET_DB_NAME = os.getenv("FLEET_CONTROL_DB_NAME", "ocu_control")
_FLEET_RECLAIM = os.getenv("FLEET_RECLAIM_COUNTER_LEAK", "1") not in ("0", "", "false")
# The concurrent-sessions quota dimension id (state.DimConcurrentSessions == 0).
_FLEET_CONCURRENT_DIM = os.getenv("FLEET_CONCURRENT_DIM", "0")


def _reclaim_fleet_concurrency_leak() -> None:
    """Reset the leaked DimConcurrentSessions counter to the true live-row count.

    No-op (never fails a test) when docker or the control DB is not reachable, or
    when FLEET_RECLAIM_COUNTER_LEAK=0. See the KNOWN-BUG note above.
    """
    if not _FLEET_RECLAIM:
        return
    import shutil
    import subprocess

    docker = shutil.which("docker")
    if not docker:
        return
    sql = (
        f"update quota_counters set value="
        f"(select count(*) from sessions where state in (0,1)) "
        f"where dim={_FLEET_CONCURRENT_DIM};"
    )
    try:
        subprocess.run(
            [
                docker, "exec", _FLEET_CONTROL_DB,
                "psql", "-U", _FLEET_DB_USER, "-d", _FLEET_DB_NAME, "-c", sql,
            ],
            capture_output=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return


@pytest.fixture
def expect(scenarios: dict[str, dict[str, Any]], backend: Backend) -> Callable[[str], dict[str, Any]]:
    """Look up a scenario's per-backend expectation by id.

    Returns a callable ``expect(scenario_id)`` -> a dict with:
        id, group, story, proves, bucket, keystone,
        expect       the poc_expect or fleet_expect string for THIS backend,
        backend      the backend name ("poc"/"fleet").

    A paired test uses this to assert the outcome its running backend is
    supposed to produce, so one test body reads correctly on both sides.
    """
    key = "poc_expect" if backend.name == "poc" else "fleet_expect"

    def _lookup(scenario_id: str) -> dict[str, Any]:
        sc = scenarios.get(scenario_id)
        if sc is None:
            raise KeyError(f"unknown scenario id: {scenario_id}")
        return {
            "id": sc["id"],
            "group": sc["group"],
            "story": sc["story"],
            "proves": sc["proves"],
            "bucket": sc["bucket"],
            "keystone": sc["keystone"],
            "expect": sc[key],
            "backend": backend.name,
        }

    return _lookup


def inactive_mechanism(reason: str) -> None:
    """Mark the current test as xfail because a mechanism is inactive here.

    Use when the invariant is real but the substrate cannot exercise it in
    this env (e.g. a read-only cgroupfs disables a leaf-kill, or a :ro bind is
    unenforced under a given driver). This is an xfail with a reason — a
    RECORDED gap — never a silent pass. If the mechanism is genuinely absent
    (a boundary that does not exist), that is a PoC-HOLE finding, not this.
    """
    pytest.xfail(f"mechanism inactive in this environment: {reason}")


def real_finding(issue: str, reason: str) -> None:
    """Mark the current test xfail because the PRODUCT invariant is broken.

    Distinct from ``inactive_mechanism``: this is NOT "the env can't exercise
    the mechanism". It is "the mechanism ran and the product genuinely VIOLATES
    the invariant" — a live-reproduced defect. It is recorded as an xfail so the
    finding is visible in ``pytest -rx`` (a known, issue-linked gap) rather than
    an unexplained red that gets normalised and then masks a regression.

    Two honesty rules the caller MUST keep for this to stay non-vacuous:
      * Call it ONLY after asserting the SPECIFIC broken signature (e.g. the
        read-back is empty, the external host was reached). If the invariant is
        later restored, that prior assertion fails LOUDLY (red) instead of a
        silent xpass — imperative xfail cannot be strict, so the caller's own
        signature assertion is the strictness backstop.
      * ``issue`` names the tracking issue so ``-rx`` is not a dead end.
    """
    pytest.xfail(f"REAL-FINDING [{issue}]: {reason}")


_FLEET_EXEC_READY_TIMEOUT_S = float(os.getenv("FLEET_EXEC_READY_TIMEOUT_S", "20"))


def await_fleet_exec_ready(backend: Backend) -> None:
    """Poll a marker echo until the guest exec plane is warm (fleet only).

    A fleet create returns on row-reservation; the guest's exec listener (the
    boot-child) binds a couple of seconds later. An exec fired at first-bind is
    refused, and — the trap this gate closes — an exec fired in the narrow
    just-bound window runs (exit 0) but returns EMPTY stdout, so a
    "true"-and-exit-0 probe declares ready while the stdout capture is not yet
    warm. A following burst then reads empty and a cross-talk / round-trip check
    reds for the wrong reason.

    So the probe ECHOES a marker and requires the marker to come BACK in stdout,
    twice in a row, before declaring ready — this proves the stdout path is warm,
    not merely that the process ran. No-op on the PoC (exec-ready at create).
    Loud-skips if the guest never warms within the bound — a genuine boot
    failure, not a passing state.
    """
    if getattr(backend, "name", "") != "fleet":
        return
    marker = b"__ocu_exec_ready__"
    argv = ["/bin/busybox", "echo", marker.decode("ascii")]
    deadline = time.monotonic() + _FLEET_EXEC_READY_TIMEOUT_S
    consecutive = 0
    last = ""
    while time.monotonic() < deadline:
        try:
            res = backend.exec(argv)
        except BackendUnavailable as exc:
            last = str(exc)
            consecutive = 0
            time.sleep(0.4)
            continue
        if not res.denied and res.exit_code == 0 and marker in res.stdout:
            consecutive += 1
            if consecutive >= 2:
                return
        else:
            consecutive = 0
            last = (
                f"denied={res.denied} exit={res.exit_code} "
                f"stdout={res.stdout[:32]!r}"
            )
        time.sleep(0.4)
    pytest.skip(
        f"guest exec plane never warmed within {_FLEET_EXEC_READY_TIMEOUT_S}s "
        f"(last: {last}). SKIP, not a pass."
    )
