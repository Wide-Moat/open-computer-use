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


# Shell-by-construction: these take a COMMAND STRING and hand it to /bin/sh, so
# no safe list-argv form of them exists and any call is a hit.
_ALWAYS_SHELL = {"getoutput", "getstatusoutput", "system", "popen"}

# These take either a list argv (safe) or a command string (a shell).
_RUNNERS = {"run", "call", "check_output", "check_call", "Popen"}


def _shell_hazard_sites(path: Path) -> list[tuple[int, str]]:
    """Return (line_no, what) for each host-side shell hazard in ``path``.

    Decided on the AST, and on the RESOLVED callee rather than its spelling:
    ``from os import system`` and ``sh = subprocess.run`` are the same hazard as
    the dotted form, and a guard matching only the dotted form measures house
    style rather than safety.

    Three shapes:

    * ``shell=`` with anything but a literal ``False``. Not merely literal
      ``True`` — ``shell=sh``, ``shell=1`` and ``shell=bool(os.getenv(...))``
      all reach /bin/sh, and a guard keyed on ``is True`` reads them as clean.
    * a shell-by-construction callee (``os.system``/``os.popen``,
      ``subprocess.getoutput``/``getstatusoutput``).
    * a built command STRING as a runner's first argument — an f-string, ``%``,
      ``.format``, a string ``+``, or a local holding one of those, so hoisting
      the string out of the call does not launder it. Interpolation INSIDE one
      element of a list argv is deliberately not flagged: that is the safe form
      (``f"name={cname}"`` reaches the program as a single argument, with no
      shell to re-parse it), and it is what the per-site waivers describe.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    always_shell_names: set[str] = set()
    runner_names: set[str] = set()
    # ``import os as o`` binds the module under another name; without this the
    # guard matches the spelling ``os.system`` rather than the callee.
    module_aliases: dict[str, str] = {"os": "os", "subprocess": "subprocess"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in ("os", "subprocess"):
            for alias in node.names:
                bound = alias.asname or alias.name
                if alias.name in _ALWAYS_SHELL:
                    always_shell_names.add(bound)
                elif alias.name in _RUNNERS:
                    runner_names.add(bound)
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in ("os", "subprocess") and alias.asname:
                    module_aliases[alias.asname] = alias.name
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Attribute):
            attr = node.value.attr
            for tgt in node.targets:
                if not isinstance(tgt, ast.Name):
                    continue
                if attr in _ALWAYS_SHELL:
                    always_shell_names.add(tgt.id)
                elif attr in _RUNNERS:
                    runner_names.add(tgt.id)

    def _built_string(node: ast.AST) -> str | None:
        if isinstance(node, ast.JoinedStr):
            return "an f-string"
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
            return "a %-formatted string"
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            # ``[...] + args`` builds a list argv, not a command line.
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

    # Scoped per enclosing function, never file-global: a local holding a list
    # argv in one function must not be tainted by a same-named local holding a
    # built string in another. `cmd`, `args` and `argv` are what this harness
    # calls its list argv, so a flat dict would red the safe form.
    string_locals_by_scope: dict[int, dict[str, str]] = {}
    scope_of: dict[int, int] = {}

    def _index_scope(scope: ast.AST) -> None:
        found: dict[str, str] = {}
        for child in ast.walk(scope):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child is not scope:
                continue
            if isinstance(child, ast.Assign):
                built = _built_string(child.value)
                if built is not None:
                    for tgt in child.targets:
                        if isinstance(tgt, ast.Name):
                            found[tgt.id] = built
            if isinstance(child, ast.Call):
                scope_of[id(child)] = id(scope)
        string_locals_by_scope[id(scope)] = found

    _index_scope(tree)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _index_scope(node)

    def _command_string(node: ast.AST, call: ast.Call) -> str | None:
        built = _built_string(node)
        if built is not None:
            return built
        if isinstance(node, ast.Name):
            scope = string_locals_by_scope.get(scope_of.get(id(call), id(tree)), {})
            if node.id in scope:
                return f"{scope[node.id]} (via {node.id})"
        return None

    def _callee(node: ast.Call) -> tuple[str, bool, bool]:
        """(display name, is-always-shell, is-runner) for a call's callee."""
        func = node.func
        if isinstance(func, ast.Attribute):
            raw = func.value.id if isinstance(func.value, ast.Name) else "?"
            base = module_aliases.get(raw, raw)
            if base in ("os", "subprocess") and func.attr in _ALWAYS_SHELL:
                return f"{base}.{func.attr}", True, False
            if base == "subprocess" and func.attr in _RUNNERS:
                return f"subprocess.{func.attr}", False, True
            return f"{base}.{func.attr}", False, False
        if isinstance(func, ast.Name):
            return func.id, func.id in always_shell_names, func.id in runner_names
        return "?", False, False

    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name, always_shell, is_runner = _callee(node)

        for kw in node.keywords:
            if kw.arg is None and isinstance(kw.value, ast.Dict):
                for k, v in zip(kw.value.keys, kw.value.values):
                    if (
                        isinstance(k, ast.Constant)
                        and k.value == "shell"
                        and not (isinstance(v, ast.Constant) and v.value is False)
                    ):
                        hits.append((node.lineno, "shell= via a ** splat"))
                continue
            if kw.arg != "shell":
                continue
            if isinstance(kw.value, ast.Constant) and kw.value.value is False:
                continue
            literal_true = isinstance(kw.value, ast.Constant) and kw.value.value is True
            hits.append((node.lineno, "shell=True" if literal_true else "a non-literal shell="))

        if always_shell:
            hits.append((node.lineno, f"{name} (runs /bin/sh by construction)"))
            continue

        if is_runner and node.args:
            built = _command_string(node.args[0], node)
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

    The planted set deliberately includes the EVASIONS, not only the shapes the
    guard already caught: a command hoisted into a local, ``from``-imported and
    aliased callees, a non-literal ``shell=``, and the shell-by-construction
    ``subprocess.getoutput``/``getstatusoutput`` (which semgrep's python bundle
    does not flag either, so this guard is their only backstop). A negative test
    that plants only what the detector already finds is green by construction.

    The clean half matters as much: an f-string inside ONE argv element and a
    list+list concat are what the harness actually uses, and flagging them would
    force the per-site waivers off rather than keep them honest.
    """
    import tempfile

    hazards = [
        ('subprocess.run("ls -l", shell=True)', "shell=True"),
        ("subprocess.run(a, shell=sh)", "a non-literal shell="),
        ("subprocess.run(a, shell=1)", "a non-literal shell="),
        ('os.system("rm -rf " + x)', "os.system (runs /bin/sh by construction)"),
        ('os.popen("ls " + x)', "os.popen (runs /bin/sh by construction)"),
        ('subprocess.getoutput("docker rm " + x)', "subprocess.getoutput (runs /bin/sh by construction)"),
        ('subprocess.getstatusoutput(f"docker rm {x}")', "subprocess.getstatusoutput (runs /bin/sh by construction)"),
        ('subprocess.run(f"docker rm {x}")', "an f-string as the command"),
        ('subprocess.check_output("cat %s" % x)', "a %-formatted string as the command"),
        ('subprocess.run("docker rm " + x)', "a concatenated string as the command"),
        ('subprocess.run(a, **{"shell": True})', "shell= via a ** splat"),
    ]
    for src, want in hazards:
        planted = f"import os, subprocess\ndef t(a, x, sh):\n    {src}\n"
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "planted.py"
            f.write_text(planted, encoding="utf-8")
            hits = _shell_hazard_sites(f)
        assert [w for _, w in hits] == [want], (
            f"planted hazard {src!r} must be detected as {want!r}; got {hits!r}. "
            "A guard that misses a planted hazard leaves every # nosemgrep "
            "waiver in this tree asserting a property nothing enforces."
        )

    # Callees reached under another name are the same hazard as the dotted form.
    aliased = (
        "import os as o\n"
        "from os import system\n"
        "from subprocess import run\n"
        "import subprocess\n"
        "sh = subprocess.run\n"
        "def t(x):\n"
        '    o.system("rm " + x)\n'
        '    system("rm -rf " + x)\n'
        '    run(f"docker rm {x}")\n'
        '    sh("docker rm " + x)\n'
        '    cmd = f"docker rm {x}"\n'
        "    subprocess.run(cmd)\n"
    )
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "aliased.py"
        f.write_text(aliased, encoding="utf-8")
        whats = sorted(w for _, w in _shell_hazard_sites(f))
    assert whats == sorted(
        [
            "os.system (runs /bin/sh by construction)",
            "system (runs /bin/sh by construction)",
            "an f-string as the command",
            "a concatenated string as the command",
            "an f-string (via cmd) as the command",
        ]
    ), (
        f"a hazardous callee reached via from-import or an alias, and a command "
        f"hoisted into a local, must all be detected; got {whats!r}. Resolving "
        "only the dotted spelling measures house style, not safety."
    )

    # Scope: a local holding a LIST argv must not be tainted by a same-named
    # local holding a built string elsewhere in the file. `cmd`, `args` and
    # `argv` are what this harness names its argv, so a file-global map would
    # red the safe form — the failure this whole test exists to prevent.
    scoped = (
        "import subprocess\n"
        "def list_probe(name):\n"
        '    cmd = ["docker", "ps", "--filter", f"name={name}"]\n'
        "    return subprocess.run(cmd)\n"
        "def other(x):\n"
        '    cmd = f"echo {x}"\n'
        "    return subprocess.getoutput(cmd)\n"
    )
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "scoped.py"
        f.write_text(scoped, encoding="utf-8")
        scoped_hits = _shell_hazard_sites(f)
    assert [ln for ln, _ in scoped_hits] == [7], (
        f"only the getoutput call on line 7 is a hazard; got {scoped_hits!r}. A "
        "file-global map of string locals reds the clean list-argv call on line "
        "4 because another function binds the same name — a false red on the "
        "safe form, which forces the waivers off instead of keeping them honest."
    )

    clean = (
        "import os, subprocess\n"
        "def t(name, sql, docker, args):\n"
        '    subprocess.run(["docker", "rm", "-f", name])\n'
        '    subprocess.check_output(["docker", "ps", "--filter", f"name={name}"])\n'
        '    subprocess.run(_sudo_prefix() + ["test", "-S", SOCK])\n'
        '    subprocess.run(["curl", "-sS"] + args)\n'
        '    subprocess.run([docker, "exec", CONTAINER, "psql", "-c", sql])\n'
        '    subprocess.run(["ls"], shell=False)\n'
    )
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "clean.py"
        f.write_text(clean, encoding="utf-8")
        clean_hits = _shell_hazard_sites(f)
    assert clean_hits == [], (
        f"the clean list-argv forms must NOT be flagged; got {clean_hits!r}. A "
        "guard that reds on interpolation inside one argv element would force "
        "the waivers off rather than keep them honest."
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
