# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
"""Meta-guard: the suite must never call a bare shell / interpreter exec argv.

The fleet demo guest (ocu-guest:assembled-demo) is a STATIC BUSYBOX: no
/bin/sh, no coreutils on PATH, no python3. A bare ``backend.exec(["sh", "-c",
...])`` / ``exec(["/bin/sh", ...])`` / ``exec(["python3", ...])`` there is
ENOENT / exit 127, which makes a NEGATIVE assertion ("no leak found", "write
refused", "isolation holds") pass for the WRONG reason — a silent vacuity a
code-read cannot catch, because the ENOENT only surfaces at run time.

The single chokepoint is ``backend.exec_sh(script)``: each backend prefixes the
argv correctly for its substrate (``/bin/sh -c`` on the PoC Ubuntu userland,
``/bin/busybox sh -c`` on the static-busybox fleet guest). Every shell-shaped
exec in the suite MUST route through it. This test greps the suite's OWN
``test_*.py`` files for any ``.exec([...])`` whose argv names a bare shell /
interpreter / the raw ``/bin/busybox`` prefix (which belongs inside exec_sh, not
inline in a test), and FAILS if one is found. It is the mechanical recurrence
gate: a reviewer can miss a re-introduced bare-sh exec; this test cannot.

The backend implementations (backends/base.py, backends/poc.py,
backends/fleet.py) legitimately NAME ``/bin/sh`` / ``/bin/busybox`` / ``python3``
— they are the chokepoint and the place the prefix is applied — so they are NOT
scanned. The chokepoint call ``.exec_sh(...)`` has no ``[`` argv and never
matches. A ``subprocess.run([docker, "run", ..., "sh", "-c", ...])`` is a
docker-run argv, not a ``.exec([`` guest exec, and is likewise not matched.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_SELF = Path(__file__).name

# Hazard tokens: a quoted argv element that names a bare shell / interpreter or
# the raw busybox prefix. If any of these is the FIRST argv element of a
# ``.exec([...])`` guest exec, the call bypasses the exec_sh chokepoint and can
# ENOENT on the static-busybox fleet guest (a vacuous negative assertion).
_HAZARD_TOKENS = ("sh", "/bin/sh", "python3", "python", "/bin/busybox")

# Match a ``.exec([`` opener followed (possibly across lines) by the argv, and
# capture up to the first closing bracket of the list literal. DOTALL so a
# multi-line argv is captured whole; non-greedy so we stop at the first ``]``.
_EXEC_LIST_RE = re.compile(r"\.exec\(\s*\[(.*?)\]", re.DOTALL)

# Within a captured argv, the FIRST quoted element (the program name). We only
# flag when the first element is a hazard token — that is the argv[0] the guest
# would try to exec. A hazard token appearing later (e.g. a filename argument)
# is not an ENOENT-on-argv0 hazard.
_FIRST_QUOTED_RE = re.compile(r"""^\s*["']([^"']*)["']""")


def _test_files() -> list[Path]:
    """Every ``test_*.py`` in the journeys dir except this meta-guard itself."""
    return sorted(p for p in _HERE.glob("test_*.py") if p.name != _SELF)


def _strip_line_comments(src: str) -> str:
    """Blank out ``#`` line-comment tails so a prose reference to a bad argv
    (e.g. a comment reading ``a bare ["sh", "-c", ...]``) is not scanned as
    code. This is a coarse strip (it does not parse ``#`` inside string
    literals), which is safe here: a real ``.exec([...])`` argv is code, and the
    hazard we guard against is a code call, never a ``#``-comment.
    """
    out_lines = []
    for line in src.splitlines():
        hidx = line.find("#")
        out_lines.append(line if hidx == -1 else line[:hidx])
    return "\n".join(out_lines)


def _bad_exec_sites(path: Path) -> list[tuple[int, str]]:
    """Return (line_no, argv0) for each bare-shell/interpreter ``.exec([...])``.

    Empty list means the file routes every shell exec through the chokepoint.
    """
    raw = path.read_text(encoding="utf-8")
    src = _strip_line_comments(raw)
    hits: list[tuple[int, str]] = []
    for m in _EXEC_LIST_RE.finditer(src):
        argv = m.group(1)
        first = _FIRST_QUOTED_RE.match(argv)
        if first is None:
            continue
        argv0 = first.group(1)
        if argv0 in _HAZARD_TOKENS:
            line_no = src.count("\n", 0, m.start()) + 1
            hits.append((line_no, argv0))
    return hits


@pytest.mark.parametrize("path", _test_files(), ids=lambda p: p.name)
def test_no_bare_shell_exec_argv(path: Path) -> None:
    """No ``test_*.py`` calls a bare shell / interpreter ``.exec([...])`` argv.

    Every shell-shaped exec must go through ``backend.exec_sh(script)`` so the
    static-busybox fleet guest gets the ``/bin/busybox sh -c`` prefix and the
    PoC gets ``/bin/sh -c``. A bare ``exec(["sh", "-c", ...])`` /
    ``exec(["python3", ...])`` / an inline ``exec(["/bin/busybox", ...])`` here
    would ENOENT on the fleet guest and pass a negative assertion vacuously.
    """
    hits = _bad_exec_sites(path)
    assert not hits, (
        f"{path.name} calls a bare shell/interpreter exec argv that bypasses "
        f"the exec_sh chokepoint (would ENOENT / exit 127 on the static-busybox "
        f"fleet guest, making a negative assertion vacuously pass). Route each "
        f"through backend.exec_sh(script). Offending sites (line: argv0): "
        + ", ".join(f"{ln}:{a!r}" for ln, a in hits)
    )


def test_meta_guard_reds_on_a_planted_violation() -> None:
    """The guard itself is non-vacuous: a planted bare-sh exec is detected.

    Builds a synthetic source string containing a bare ``exec(["sh", "-c",
    ...])`` and a bare ``exec(["python3", ...])`` and asserts the detector finds
    both — so the guard above cannot silently pass on a real recurrence. Also
    asserts the chokepoint form (``exec_sh("...")``) and a docker-run argv are
    NOT flagged, so the guard does not red on the legitimate patterns.
    """
    import tempfile

    planted = (
        "from x import backend\n"
        "def t():\n"
        '    backend.exec(["sh", "-c", "echo hi"])\n'      # bad
        '    backend.exec(["python3", "-c", "print(1)"])\n'  # bad
        '    backend.exec_sh("echo hi")\n'                  # chokepoint (ok)
        '    backend.exec(["cat", "/some/path"])\n'         # applet, not a shell (ok)
        '    subprocess.run([docker, "run", "img", "sh", "-c", "sleep 1"])\n'  # docker run (ok)
        '    # a comment mentioning a bare ["sh", "-c", ...] must NOT flag\n'
    )
    with tempfile.TemporaryDirectory() as td:
        planted_path = Path(td) / "test_planted.py"
        planted_path.write_text(planted, encoding="utf-8")
        hits = _bad_exec_sites(planted_path)

    argv0s = sorted(a for _, a in hits)
    assert argv0s == ["python3", "sh"], (
        "the meta-guard must detect the two planted bare-shell exec argv "
        f"(sh, python3) and nothing else; got {hits!r}. A guard that does not "
        "red on a planted violation is vacuous."
    )
