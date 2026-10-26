""".env.example lists every environment variable of NeuroGrid, its tools and its workflows, with empty values
only; .env stays out of git (secrets only via environment variables).

The scan covers the package and the tools (every name read, set or cleared, also through constants, loops and
the environment handed to a child process), the names the tests read without setting them, the workflows
(env blocks, vars/secrets/env expressions, the variables of their scripts) and the packaging scripts (bash,
PowerShell, cmd). Every name found is either in .env.example or in one of the reviewed sets below, and every
reviewed name is still in use."""

from __future__ import annotations

import ast
import re
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / ".env.example"
# Set by the operating system, the shell, Python or GitHub Actions: read (or passed on), never set for
# NeuroGrid. PRETTY_NAME comes from /etc/os-release, read by the Linux clean room.
PROVIDED = {
    "ACTIONS_ID_TOKEN_REQUEST_URL",
    "BASH_SOURCE",
    "COMPUTERNAME",
    "ERRORLEVEL",
    "GITHUB_ACTIONS",
    "GITHUB_REF",
    "GITHUB_REF_NAME",
    "GITHUB_REPOSITORY",
    "HOME",
    "LOCALAPPDATA",
    "PATH",
    "PRETTY_NAME",
    "RUNNER_TEMP",
    "SYSTEMROOT",
    "SystemRoot",
    "TEMP",
    "TMP",
    "TMPDIR",
    "USERNAME",
    "USERPROFILE",
    "WINDIR",
    "XDG_DATA_HOME",
}
# Variables of other programs that NeuroGrid, its scripts or its workflows set, clear or pass on for them:
# dead proxies of the clean rooms; the Node.js and Playwright debug switches removed from the PDF driver's
# environment; the environment of the validator (Deno) and of the PDF browser; gh, git, MNE, Python and uv.
THIRD_PARTY = {
    "ALL_PROXY",
    "DEBUG",
    "DEBUGP",
    "DEBUG_FILE",
    "DENO_DIR",
    "DENO_NO_PROMPT",
    "DENO_NO_UPDATE_CHECK",
    "GH_TOKEN",
    "GIT_SSH_COMMAND",
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "LANG",
    "LC_ALL",
    "MNE_TQDM",
    "NODE_OPTIONS",
    "NODE_PATH",
    "NO_COLOR",
    "NO_PROXY",
    "PWDEBUG",
    "PYTHONIOENCODING",
    "PYTHONWARNDEFAULTENCODING",
    "UV_CACHE_DIR",
    "UV_NO_CONFIG",
    "UV_NO_PROGRESS",
    "UV_OFFLINE",
    "UV_PYTHON_DOWNLOADS",
    "XDG_CACHE_HOME",
    "XDG_CONFIG_HOME",
}
# Defined inside one workflow for its own steps, or by one of the project's scripts for another
# (cleanroom_linux.sh -> cleanroom_inside.sh, the docker build argument of pdf_debian12.sh); never set from
# outside.
INTERNAL = {"BUNDLES", "NG_EXPECT_REFUSAL", "NG_PDF_SHA", "NG_PDF_ZIP", "NG_TRACE", "PACKAGES", "UV_VERSION"}
# Listed for the owner although nothing uses it yet: only if Trusted Publishing is declined (D-07).
RESERVED = {"PYPI_API_TOKEN"}
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _example() -> dict[str, str]:
    values = {}
    for line in EXAMPLE.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            name, sep, value = line.partition("=")
            assert sep == "=" and re.fullmatch(r"[A-Z][A-Z0-9_]*", name), line
            values[name] = value
    return values


# --- Python: names in the environment's accessors, resolved through constants, assignments and loops

Binding = tuple[ast.expr, int | None]  # the bound expression; None: the value itself, -1: each element,
# n >= 0: element n of each element (a loop over pairs)


def _is_environment(node: ast.AST) -> bool:
    """os.environ, environ, or a mapping named env (the environment handed to a child process)."""
    if isinstance(node, ast.Attribute):
        return node.attr == "environ"
    return isinstance(node, ast.Name) and node.id in ("environ", "env")


def _bindings(scope: ast.AST, *, top: bool) -> dict[str, list[Binding]]:
    """The names bound in a module (its top level) or a function (anywhere inside, loops and comprehensions
    included), flow-insensitive."""
    found: dict[str, list[Binding]] = defaultdict(list)
    nodes = scope.body if isinstance(scope, ast.Module) and top else ast.walk(scope)
    for node in nodes:
        if isinstance(node, ast.Assign | ast.AnnAssign) and node.value is not None:
            for target in node.targets if isinstance(node, ast.Assign) else [node.target]:
                if isinstance(target, ast.Name):
                    found[target.id].append((node.value, None))
        elif not top and isinstance(node, ast.For | ast.comprehension):
            if isinstance(node.target, ast.Name):
                found[node.target.id].append((node.iter, -1))
            elif isinstance(node.target, ast.Tuple):
                for index, part in enumerate(node.target.elts):
                    if isinstance(part, ast.Name):
                        found[part.id].append((node.iter, index))
    return found


class _Resolver:
    """The string values an expression can have: constants, tuples and lists of them, names bound in the
    function or the module, and the module constants of the other scanned files (imported or module.NAME)."""

    def __init__(self, tree: ast.Module, constants: dict[str, list[ast.expr]]) -> None:
        self.constants = constants
        self.module = _bindings(tree, top=True)
        self.functions: dict[ast.AST, dict[str, list[Binding]]] = {}

    def _bound(self, name: str, function: ast.AST | None) -> list[Binding]:
        if function is not None:
            if function not in self.functions:
                self.functions[function] = _bindings(function, top=False)
            if name in self.functions[function]:
                return self.functions[function][name]
        if name in self.module:
            return self.module[name]
        return [(value, None) for value in self.constants.get(name, [])]

    def values(self, node: ast.expr, function: ast.AST | None, index: int | None = None) -> set[str]:
        return self._values(node, function, index, frozenset())

    def _values(
        self, node: ast.expr, function: ast.AST | None, index: int | None, seen: frozenset[str]
    ) -> set[str]:
        if isinstance(node, ast.Name | ast.Attribute):
            name = node.id if isinstance(node, ast.Name) else node.attr
            if name in seen:
                return set()
            bindings = (
                self._bound(name, function)
                if isinstance(node, ast.Name)
                else [(value, None) for value in self.constants.get(name, [])]
            )
            scope = function if isinstance(node, ast.Name) else None
            found: set[str] = set()
            for source, inner in bindings:
                if inner is None:
                    found |= self._values(source, scope, index, seen | {name})
                elif index is None:
                    found |= self._values(source, scope, inner, seen | {name})
            return found
        if index is None:
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                return {node.value}
            return set()
        if isinstance(node, ast.Tuple | ast.List | ast.Set):
            found = set()
            for element in node.elts:
                if isinstance(element, ast.Starred):
                    found |= self._values(element.value, function, index, seen)
                elif index == -1:
                    found |= self._values(element, function, None, seen)
                elif isinstance(element, ast.Tuple) and index < len(element.elts):
                    found |= self._values(element.elts[index], function, None, seen)
            return found
        return set()

    def strings(self, node: ast.expr, function: ast.AST | None) -> set[str]:
        """Values of a name argument: a string, or a tuple of them (an element list)."""
        if isinstance(node, ast.Tuple | ast.List | ast.Set):
            return self.values(node, function, -1)
        return self.values(node, function)


def _owners(tree: ast.AST) -> dict[ast.AST, ast.AST | None]:
    """The innermost function of every node (None at module level)."""
    owner: dict[ast.AST, ast.AST | None] = {}
    stack: list[tuple[ast.AST, ast.AST | None]] = [(tree, None)]
    while stack:
        node, function = stack.pop()
        owner[node] = function
        inner = node if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda) else function
        stack.extend((child, inner) for child in ast.iter_child_nodes(node))
    return owner


def _uses(node: ast.AST) -> Iterable[tuple[ast.expr, bool]]:
    """(name expression, written) of one node that reads, sets or clears an environment variable."""
    if isinstance(node, ast.Call):
        func = node.func
        attr = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""
        if node.args and isinstance(func, ast.Attribute) and _is_environment(func.value):
            if attr == "get":
                yield node.args[0], False
            elif attr in ("pop", "setdefault"):
                yield node.args[0], True
        elif node.args and attr == "getenv":
            yield node.args[0], False
        elif node.args and attr in ("putenv", "unsetenv", "setenv", "delenv"):  # also pytest's monkeypatch
            yield node.args[0], True
        for keyword in node.keywords:
            if keyword.arg == "env" and isinstance(keyword.value, ast.Dict):
                yield from ((key, True) for key in keyword.value.keys if key is not None)
    elif isinstance(node, ast.Subscript) and _is_environment(node.value):
        yield node.slice, not isinstance(node.ctx, ast.Load)
    elif isinstance(node, ast.Compare) and any(isinstance(op, ast.In | ast.NotIn) for op in node.ops):
        if any(_is_environment(c) for c in node.comparators):
            yield node.left, False
    elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
        named = any(_is_environment(target) for target in node.targets)
        spread = any(
            k is None and _is_environment(v) for k, v in zip(node.value.keys, node.value.values, strict=True)
        )
        if named or spread:
            yield from ((key, True) for key in node.value.keys if key is not None)


def _python_names(sources: dict[str, str]) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Names read and names set or cleared, each with the files, of Python sources {where: text}."""
    trees = {where: ast.parse(text) for where, text in sources.items()}
    constants: dict[str, list[ast.expr]] = defaultdict(list)
    for tree in trees.values():
        for name, bindings in _bindings(tree, top=True).items():
            constants[name] += [value for value, index in bindings if index is None]
    read: dict[str, set[str]] = defaultdict(set)
    written: dict[str, set[str]] = defaultdict(set)
    for where, tree in trees.items():
        resolver, owner = _Resolver(tree, constants), _owners(tree)
        for node in ast.walk(tree):
            for expression, write in _uses(node):
                for name in resolver.strings(expression, owner[node]):
                    if NAME.fullmatch(name):
                        (written if write else read)[name].add(where)
    return read, written


def _sources(paths: Iterable[Path]) -> dict[str, str]:
    return {path.relative_to(ROOT).as_posix(): path.read_text(encoding="utf-8") for path in paths}


def _code_names() -> dict[str, set[str]]:
    """Every name the package and the tools read, set or clear, and every name the tests read without setting
    it themselves (a name a test sets is its own stimulus)."""
    code = [*(ROOT / "src").rglob("*.py"), *(ROOT / "tools").rglob("*.py")]
    read, written = _python_names(_sources(code))
    found: dict[str, set[str]] = defaultdict(set)
    for table in (read, written):
        for name, wheres in table.items():
            found[name] |= wheres
    test_read, test_written = _python_names(_sources((ROOT / "tests").rglob("*.py")))
    for name, wheres in test_read.items():
        if name not in test_written:
            found[name] |= wheres
    return found


# --- shell scripts and workflows -----------------------------------------------------------------------

SH_REFERENCE = re.compile(r"\$\{?([A-Z_][A-Z0-9_]*)")
SH_EXPORT = re.compile(r"^\s*export\s+(.*)$", re.M)
SH_ASSIGNMENT = re.compile(r"^\s*(?:local\s+|readonly\s+)?([A-Z_][A-Z0-9_]*)=", re.M)
DOCKER_ENV = re.compile(r"""\s-e\s+["']?([A-Z_][A-Z0-9_]*)=""")
POWERSHELL_ENV = re.compile(r"\$env:([A-Za-z_][A-Za-z0-9_]*)", re.I)
CMD_VARIABLE = re.compile(r"%([A-Za-z_][A-Za-z0-9_]*)%")
EXPRESSION = re.compile(r"\b(?:vars|secrets|env)\.([A-Za-z_][A-Za-z0-9_]*)")


def _bash_names(text: str) -> set[str]:
    """Upper-case variables a bash script reads, exports or passes into a container; a variable the script
    assigns without exporting is its own shell variable."""
    words = (word.partition("=")[0] for line in SH_EXPORT.findall(text) for word in line.split())
    exported = {word for word in words if re.fullmatch(r"[A-Z_][A-Z0-9_]*", word)}
    shell_only = set(SH_ASSIGNMENT.findall(text)) - exported
    return (set(SH_REFERENCE.findall(text)) - shell_only) | exported | set(DOCKER_ENV.findall(text))


def _windows_names(text: str) -> set[str]:
    """$env:NAME of PowerShell and %NAME% of cmd (also inside messages that name the folder)."""
    return set(POWERSHELL_ENV.findall(text)) | set(CMD_VARIABLE.findall(text))


def _step_shell(step: dict[str, Any], job: dict[str, Any], workflow: dict[str, Any]) -> str:
    """The shell of a run step, GitHub's defaults included: pwsh on Windows runners, bash elsewhere; a runner
    from the matrix may be either."""
    for source in (step, job.get("defaults", {}).get("run", {}), workflow.get("defaults", {}).get("run", {})):
        if source.get("shell"):
            return str(source["shell"])
    runs_on = str(job.get("runs-on", ""))
    return "either" if "${{" in runs_on else "pwsh" if "windows" in runs_on else "bash"


def _workflow_names(text: str) -> set[str]:
    data = yaml.safe_load(text)
    names = set(EXPRESSION.findall(text)) | set(data.get("env", {}))
    for job in data["jobs"].values():
        names |= set(job.get("env", {}))
        for step in job.get("steps", []):
            names |= set(step.get("env", {}))
            run, shell = str(step.get("run", "")), _step_shell(step, job, data)
            if shell in ("pwsh", "powershell", "either"):
                names |= _windows_names(run)
            if shell not in ("pwsh", "powershell"):
                names |= _bash_names(run)
    return names


def _script_names() -> dict[str, set[str]]:
    found: dict[str, set[str]] = defaultdict(set)
    for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        for name in _workflow_names(path.read_text(encoding="utf-8")):
            found[name].add(path.relative_to(ROOT).as_posix())
    for path in sorted((ROOT / "packaging").rglob("*")):
        if path.suffix == ".sh":
            names = _bash_names(path.read_text(encoding="utf-8"))
        elif path.suffix in (".ps1", ".cmd"):
            names = _windows_names(path.read_text(encoding="utf-8-sig"))
        else:
            continue
        for name in names:
            found[name].add(path.relative_to(ROOT).as_posix())
    return found


def _used() -> dict[str, set[str]]:
    found = _code_names()
    for name, wheres in _script_names().items():
        found[name] = found.get(name, set()) | wheres
    return dict(found)


# --- tests -------------------------------------------------------------------------------------------


def test_example_exists_with_empty_values_only() -> None:
    values = _example()
    assert values and all(value == "" for value in values.values()), values
    assert len(values) == len(set(values))


def test_example_lists_every_variable_of_code_and_workflows() -> None:
    listed = set(_example())
    used = _used()
    unreviewed = {name: sorted(wheres) for name, wheres in used.items()}
    for name in listed | PROVIDED | THIRD_PARTY | INTERNAL:
        unreviewed.pop(name, None)
    assert unreviewed == {}, "list these in .env.example or review them into PROVIDED/THIRD_PARTY/INTERNAL"
    assert {
        "NEUROGRID_PDF_BROWSER_DIR",
        "NEUROGRID_REQUIRE_PDF",
        "SOURCE_DATE_EPOCH",
        "GITEE_SSH_KEY",
    } <= listed
    assert listed - set(used) == RESERVED  # every other listed name is used somewhere


def test_reviewed_names_are_in_use_and_in_one_set_only() -> None:
    used = set(_used())
    sets = {
        "PROVIDED": PROVIDED,
        "THIRD_PARTY": THIRD_PARTY,
        "INTERNAL": INTERNAL,
        "example": set(_example()),
    }
    for (a, left), (b, right) in ((x, y) for x in sets.items() for y in sets.items() if x[0] < y[0]):
        assert not left & right, (a, b, sorted(left & right))
    for label in ("PROVIDED", "THIRD_PARTY", "INTERNAL"):
        assert sets[label] <= used, (label, sorted(sets[label] - used))  # no stale entry


def test_every_listed_name_is_documented_by_a_comment() -> None:
    lines = EXAMPLE.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line and not line.startswith("#"):
            assert any(lines[i].startswith("#") for i in range(max(0, index - 3), index)), line


def test_dot_env_is_ignored_by_git() -> None:
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in ignored


def test_scanner_finds_planted_names() -> None:
    source = 'os.environ.get("A_B")\nos.environ["C_D"]\nos.getenv("E_F")\nenviron.get( "G_H", "x")\n'
    read, written = _python_names({"planted.py": source})
    assert set(read) == {"A_B", "C_D", "E_F", "G_H"} and not written
    module = """
import os
from other import IMPORTED
DIRECT = "K_DIRECT"
LISTED = ("K_LIST_1", "K_LIST_2")


def run(work):
    env = {"K_CHILD": "1", "TMP": str(work)}
    if "K_IN" in os.environ:
        env["K_SET"] = os.environ["K_IN"]
    for name in LISTED:
        os.environ.pop(name, None)
    for key, sub in (("K_PAIR", "a"), ("K_PAIR_2", "b")):
        env[key] = sub
    names = ("K_LOCAL", *LISTED)
    saved = {n: os.environ.get(n) for n in names}
    subprocess.run(["x"], env={**os.environ, "K_KEYWORD": "1"})
    child = {**os.environ, "K_SPREAD": "1"}
    return os.environ.get(DIRECT), os.environ.get(IMPORTED), os.environ.get(other.IMPORTED), saved, child
"""
    # Names are resolved per function without control flow: a loop variable stands for every value it takes.
    read, written = _python_names({"m.py": module, "other.py": 'IMPORTED = "K_IMPORTED"\n'})
    assert set(read) == {"K_IN", "K_LOCAL", "K_LIST_1", "K_LIST_2", "K_DIRECT", "K_IMPORTED"}
    assert set(written) == {"K_CHILD", "TMP", "K_SET", "K_LIST_1", "K_LIST_2", "K_PAIR", "K_PAIR_2",
                            "K_KEYWORD", "K_SPREAD"}  # fmt: skip
    test = (
        'monkeypatch.setenv("T_STIMULUS", "1")\nassert os.environ.get("T_STIMULUS")\nos.environ.get("T_IN")\n'
    )
    read, written = _python_names({"test_x.py": test})
    assert set(read) == {"T_STIMULUS", "T_IN"} and set(written) == {"T_STIMULUS"}  # _code_names keeps T_IN


def test_script_scanners_find_planted_names() -> None:
    bash = (
        'export A_ONE=1 A_TWO="$x"\nLOCAL_ONLY=3\necho "$LOCAL_ONLY ${A_READ:-} $A_PLAIN"\n'
        'docker run -e A_DOCKER=1 -e "A_QUOTED=$y" image\nlower=1; echo "$lower"\n'
    )
    assert _bash_names(bash) == {"A_ONE", "A_TWO", "A_READ", "A_PLAIN", "A_DOCKER", "A_QUOTED"}
    assert _windows_names("$env:B_One = 1; $ENV:B_TWO; $LASTEXITCODE; echo %B_CMD% %~dp0 %*") == {
        "B_One",
        "B_TWO",
        "B_CMD",
    }
    workflow = """
on: push
env: {C_TOP: "1"}
jobs:
  linux:
    runs-on: ubuntu-24.04
    env: {C_JOB: "1"}
    steps:
      - env: {C_STEP: "${{ secrets.C_SECRET }}"}
        run: echo "$C_BASH ${{ vars.C_VAR }} ${{ env.C_TOP }}"
  windows:
    runs-on: windows-latest
    steps:
      - run: echo $env:C_PWSH $LASTEXITCODE
  both:
    runs-on: ${{ matrix.os }}
    steps:
      - run: echo "$C_EITHER"
      - shell: bash
        run: echo "$C_SHELL"
"""
    assert _workflow_names(workflow) == {
        "C_TOP", "C_JOB", "C_STEP", "C_SECRET", "C_BASH", "C_VAR", "C_PWSH", "C_EITHER", "C_SHELL"
    }  # fmt: skip
