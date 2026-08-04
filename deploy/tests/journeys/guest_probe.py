# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""A TCP-connect probe that resolves its primitive from the guest image.

Isolation checks need to attempt a connect from inside the guest and assert it
FAILED with a no-route signature. The primitive for that is not the same across
guest images: ocu-guest:assembled-demo is a static busybox whose only netcat is
the `/bin/busybox nc` applet, while ocu-guest:poc-fat carries a full userland
with python3 and no netcat at all.

Committing to one primitive turns "this image lacks that tool" into a probe that
never runs, and a probe that never runs makes a negative assertion ("the guest
could not reach control") pass for the wrong reason. The call sites already
refuse to accept that -- they fail on exit 127 rather than treating it as
isolation -- so on an image without the chosen tool they simply go red. Resolve
the primitive instead, and keep the same observable contract either way.

Contract: every script prints `__rc=<n>` as its last line, where 0 means the
connect SUCCEEDED (isolation is broken) and non-zero means it failed. Callers
assert on that token, not on any tool's own wording.
"""

from __future__ import annotations

_PROBE_CACHE: dict[int, str] = {}


def _busybox_nc(host: str, port: int, timeout: int) -> str:
    return f"/bin/busybox nc -w{timeout} {host} {port} </dev/null; echo __rc=$?"


def _python3_socket(host: str, port: int, timeout: int) -> str:
    # Report the errno class as well: a refused connect and a name that does not
    # resolve are both isolation, but a caller reading the output should be able
    # to tell which one it got.
    return (
        "python3 -c \""
        "import socket,sys\n"
        "try:\n"
        f"    socket.create_connection(('{host}', {port}), {timeout}).close()\n"
        "    print('__rc=0')\n"
        "except OSError as exc:\n"
        "    print('__err=%s' % type(exc).__name__)\n"
        "    print('__rc=1')\n"
        '"'
    )


def tcp_connect_script(backend, host: str, port: int, timeout: int = 4) -> str:
    """Return a shell script that attempts a TCP connect and prints ``__rc=``.

    The primitive is probed once per backend instance and cached: busybox nc
    when the image carries it, python3 sockets otherwise. Raises when the image
    carries neither, because a probe that cannot run must not be mistaken for a
    connect that failed.
    """
    key = id(backend)
    kind = _PROBE_CACHE.get(key)
    if kind is None:
        if not backend.exec(["/bin/busybox", "true"]).denied:
            kind = "busybox"
        elif not backend.exec(["/usr/bin/python3", "-c", "pass"]).denied:
            kind = "python3"
        else:
            raise RuntimeError(
                "the guest image carries neither /bin/busybox nor "
                "/usr/bin/python3, so no TCP-connect probe can run; an "
                "isolation assertion here would be vacuous"
            )
        _PROBE_CACHE[key] = kind
    if kind == "busybox":
        return _busybox_nc(host, port, timeout)
    return _python3_socket(host, port, timeout)
