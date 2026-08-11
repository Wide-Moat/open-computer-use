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

import ast
import io
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


def _harness_files() -> list[Path]:
    """Every .py under the journeys tree except this meta-guard itself.

    Wider than :func:`_test_files` on purpose: the subprocess waivers live in
    ``conftest.py`` and ``backends/`` too, and those are exactly the files a new
    helper gets added to.
    """
    return sorted(p for p in _HERE.rglob("*.py") if p.name != _SELF)


def _shell_hazard_sites(path: Path) -> list[tuple[int, str]]:
    """Return (line_no, what) for each host-side shell hazard in ``path``.

    Three shapes, all decided on the AST rather than on how the source is
    written, so a hazard hidden in a differently-formatted call still counts:

    * ``shell=True`` on any call - hands the argv to /bin/sh, which is what the
      per-site ``# nosemgrep`` waivers all assert does NOT happen.
    * ``os.system`` / ``os.popen`` - a shell by construction.
    * an f-string (or a ``%``/``.format`` built string) passed as the COMMAND
      argument of ``subprocess.run``/``call``/``check_output``/``check_call``/
      ``Popen`` - i.e. a command line rather than a list argv. Interpolation
      INSIDE one element of a list argv is deliberately not flagged: that is the
      safe form (``f"name={cname}"`` reaches the program as a single argument,
      with no shell to re-parse it), and it is what the waivers describe.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    runners = {"run", "call", "check_output", "check_call", "Popen"}
    hits: list[tuple[int, str]] = []

    def _built_string(node: ast.AST) -> str | None:
        if isinstance(node, ast.JoinedStr):
            return "an f-string"
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
            return "a %-formatted string"
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            # ``[...] + args`` builds a list argv, not a command line. Only flag
            # a ``+`` whose operands are strings.
            if any(
                isinstance(side, (ast.List, ast.Tuple))
                for side in (node.left, node.right)
            ):
                return None
            if any(
                isinstance(side, ast.Constant) and isinstance(side.value, str)
                for side in (node.left, node.right)
            ):
                return "a concatenated string"
            return None
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "format"
        ):
            return "a .format() string"
        return None

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        for kw in node.keywords:
            if (
                kw.arg == "shell"
                and isinstance(kw.value, ast.Constant)
                and kw.value.value is True
            ):
                hits.append((node.lineno, "shell=True"))

        func = node.func
        if isinstance(func, ast.Attribute):
            if func.attr in ("system", "popen") and isinstance(func.value, ast.Name) and func.value.id == "os":
                hits.append((node.lineno, f"os.{func.attr}"))
            if func.attr in runners and node.args:
                built = _built_string(node.args[0])
                if built is not None:
                    hits.append((node.lineno, f"{built} as the command"))
    return hits


@pytest.mark.parametrize("path", _harness_files(), ids=lambda p: p.name)
def test_no_host_side_shell_in_the_harness(path: Path) -> None:
    """No harness file hands a host command to a shell, or builds one by
    interpolation.

    Every ``subprocess`` call in this tree carries a per-site ``# nosemgrep``
    waiver whose stated reason is the same in each case: list argv, no shell, so
    a metacharacter in stand config is one argv element rather than syntax. That
    reason is an ASSUMPTION about code nobody re-reads. This test makes it a
    property: the first ``shell=True``, ``os.system``, or f-string-built command
    added here reds, and the waiver above it stops being true out loud rather
    than silently.
    """
    hits = _shell_hazard_sites(path)
    assert not hits, (
        f"{path.name} runs a host command through a shell or builds one by "
        f"interpolation, which breaks the 'list argv, never a shell' property "
        f"every # nosemgrep waiver in this tree rests on. Pass a list argv with "
        f"each value as its own element. Offending sites (line: what): "
        + ", ".join(f"{ln}:{w}" for ln, w in hits)
    )


def test_shell_hazard_guard_reds_on_planted_violations() -> None:
    """The shell-hazard guard is non-vacuous, and does not red on the clean form.

    Plants one of each detected shape and asserts all four are found, then
    asserts the shapes the harness legitimately uses - a list argv holding an
    env-derived value, and a literal-joined list - are NOT flagged. Without the
    negative half the guard could flag everything and still look green here.
    """
    import tempfile

    planted = (
        "import os, subprocess\n"
        "def t(name, sql):\n"
        '    subprocess.run("ls -l", shell=True)\n'
        '    os.system("rm -rf /tmp/x")\n'
        '    subprocess.run(f"docker rm {name}")\n'
        '    subprocess.run("docker rm " + name)\n'
        # Clean forms below. The f-string INSIDE one argv element and the
        # list+list concat are the shapes the harness actually uses; flagging
        # them would force the waivers off rather than keep them honest.
        '    subprocess.run(["docker", "rm", "-f", name])\n'
        '    subprocess.check_output(["docker", "ps", "--filter", f"name={name}"])\n'
        '    subprocess.run(_sudo_prefix() + ["test", "-S", SOCK])\n'
        '    subprocess.run([docker, "exec", CONTAINER, "psql", "-c", sql])\n'
    )
    with tempfile.TemporaryDirectory() as td:
        planted_path = Path(td) / "planted_hazards.py"
        planted_path.write_text(planted, encoding="utf-8")
        hits = _shell_hazard_sites(planted_path)

    whats = sorted(w for _, w in hits)
    assert whats == sorted(
        [
            "shell=True",
            "os.system",
            "an f-string as the command",
            "a concatenated string as the command",
        ]
    ), (
        "the shell-hazard guard must detect each planted shape exactly once and "
        f"leave the clean list-argv forms alone; got {hits!r}. A guard that does "
        "not red on a planted violation is vacuous, and one that reds on the "
        "clean form would force the waivers off rather than keep them honest."
    )


def test_no_undefined_names_in_the_suite() -> None:
    """No journey module may reference a name that is never bound.

    An undefined name costs nothing to detect and everything to discover the
    other way: a broad edit that threads an argument through call sites lands
    it in functions that never bind it, those tests raise NameError instead of
    running, and the only thing that surfaces it is a full browser run that
    takes half an hour. That happened twice on the same edit, the second time
    because the first repair was verified on two tests out of fourteen.

    Skips loudly rather than passing when pyflakes is absent: a guard that
    silently does nothing is worse than no guard.
    """
    pyflakes = pytest.importorskip(
        "pyflakes.api",
        reason="pyflakes not installed -- undefined-name guard cannot run. "
        "LOUD SKIP, not a pass.",
    )
    from pyflakes.reporter import Reporter

    class _Collect(io.StringIO):
        pass

    out, err = _Collect(), _Collect()
    reporter = Reporter(out, err)
    for path in sorted(Path(__file__).parent.glob("*.py")):
        pyflakes.checkPath(str(path), reporter)
    undefined = [
        line for line in out.getvalue().splitlines() if "undefined name" in line
    ]
    assert not undefined, "undefined names:\n" + "\n".join(undefined)
