"""Structural rules: kernel import boundary (A-23), schemas and fixtures up to date, banned APIs (A-49)."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
SRC = ROOT / "src" / "neurogrid"
# fontTools, playwright and pypdf: report fonts and PDF printing with its QA gate in kernel/fonts.py and
# kernel/pdf.py (KONZEPT 1.2, P5 decision B2)
KERNEL_ALLOWED_THIRD_PARTY = {"pydantic", "jinja2", "yaml", "fontTools", "playwright", "pypdf"}
EEG_LIBRARIES = {"mne", "mne_bids", "edfio", "numpy", "scipy", "pyprep", "autoreject", "mne_icalabel"}
# Modules that can talk to the network. Only the network guard itself may import socket (A-49).
NETWORK_MODULES = {
    "aiohttp",
    "asyncio",
    "ftplib",
    "http",
    "httpx",
    "imaplib",
    "logging.handlers",
    "multiprocessing.connection",
    "nntplib",
    "poplib",
    "pooch",
    "requests",
    "smtplib",
    "socket",
    "socketserver",
    "ssl",
    "telnetlib",
    "urllib.request",
    "webbrowser",
    "websocket",
    "websockets",
    "xmlrpc",
}
NETWORK_ATTRIBUTES = {"mne.datasets", "mne_icalabel.datasets", "mne.Report", "mne.report"}
DYNAMIC_IMPORTS = {"importlib.import_module", "importlib.__import__", "builtins.__import__", "__import__"}


def _module_name(path: Path) -> tuple[str, bool]:
    parts = list(path.relative_to(SRC.parent).with_suffix("").parts)
    if parts[-1] == "__init__":
        return ".".join(parts[:-1]), True
    return ".".join(parts), False


def _imports_from_source(source: str, module: str, is_package: bool) -> set[str]:
    """Absolute names of everything imported: modules and, for ``from x import y``, also ``x.y``.

    Relative imports are resolved against ``module``; constant arguments of importlib.import_module and
    __import__ count as imports too.
    """
    package = module if is_package else module.rpartition(".")[0]
    names: set[str] = set()
    tree = ast.parse(source)
    aliases = _aliases(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base_parts = package.split(".")
                base = ".".join(base_parts[: len(base_parts) - (node.level - 1)])
                origin = f"{base}.{node.module}" if node.module else base
            else:
                origin = node.module or ""
            if node.module:
                names.add(origin)
            names.update(f"{origin}.{alias.name}" for alias in node.names if alias.name != "*")
        elif isinstance(node, ast.Call) and _dotted(node.func, aliases) in DYNAMIC_IMPORTS:
            candidates = [*node.args[:1], *(kw.value for kw in node.keywords if kw.arg == "name")]
            for argument in candidates:
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    names.add(argument.value)
    return names


def _imports(path: Path) -> set[str]:
    module, is_package = _module_name(path)
    return _imports_from_source(path.read_text(encoding="utf-8"), module, is_package)


def _kernel_violations(names: set[str]) -> list[str]:
    stdlib = set(sys.stdlib_module_names)
    bad = []
    for name in sorted(names):
        top = name.split(".")[0]
        if top == "neurogrid":
            if not (name == "neurogrid.kernel" or name.startswith("neurogrid.kernel.")):
                bad.append(name)
        elif top not in stdlib and top not in KERNEL_ALLOWED_THIRD_PARTY or top in EEG_LIBRARIES:
            bad.append(name)
    return bad


def test_kernel_imports_only_kernel_stdlib_and_allowed_libraries() -> None:
    files = sorted((SRC / "kernel").rglob("*.py"))
    assert files
    for path in files:
        assert not _kernel_violations(_imports(path)), f"{path.name}: {_kernel_violations(_imports(path))}"


def test_kernel_boundary_check_sees_relative_imports() -> None:
    source = (
        "from ..model.dataset import Recording\nfrom .. import pipeline\nfrom . import glob\nimport mne\n"
    )
    names = _imports_from_source(source, "neurogrid.kernel.example", is_package=False)
    assert {"neurogrid.model.dataset", "neurogrid.pipeline", "neurogrid.kernel.glob", "mne"} <= names
    assert _kernel_violations(names) == [
        "mne",
        "neurogrid.model.dataset",
        "neurogrid.model.dataset.Recording",
        "neurogrid.pipeline",
    ]
    package_names = _imports_from_source("from .sub import x\n", "neurogrid.kernel", is_package=True)
    assert package_names == {"neurogrid.kernel.sub", "neurogrid.kernel.sub.x"}


def _aliases(tree: ast.AST) -> dict[str, str]:
    """Local name -> imported dotted name, for ``import x as y`` and ``from x import y [as z]``."""
    found: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found[alias.asname or alias.name.split(".")[0]] = (
                    alias.name if alias.asname else alias.name.split(".")[0]
                )
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for alias in node.names:
                if alias.name != "*":
                    found[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return found


def _dotted(node: ast.AST, aliases: dict[str, str]) -> str | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(aliases.get(node.id, node.id))
    return ".".join(reversed(parts))


def _attribute_chains(tree: ast.AST) -> set[str]:
    """Every prefix of every attribute chain, import aliases resolved (``m.datasets`` -> mne.datasets)."""
    aliases = _aliases(tree)
    chains: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Attribute, ast.Name)):
            dotted = _dotted(node, aliases)
            if dotted:
                parts = dotted.split(".")
                chains.update(".".join(parts[:n]) for n in range(1, len(parts) + 1))
    return chains


def _network_hits(names: set[str], allowed: set[str]) -> set[str]:
    banned = NETWORK_MODULES | NETWORK_ATTRIBUTES
    return {name for name in names if any(name == b or name.startswith(b + ".") for b in banned - allowed)}


def _violations(source: str, module: str, allowed: set[str] = frozenset()) -> set[str]:  # type: ignore[assignment]
    tree = ast.parse(source)
    return _network_hits(_imports_from_source(source, module, False) | _attribute_chains(tree), set(allowed))


def test_banned_network_capable_apis_are_not_used() -> None:
    for path in sorted(SRC.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        module, _is_package = _module_name(path)
        allowed = {"socket"} if path == SRC / "kernel" / "netguard.py" else set()
        assert not _violations(text, module, allowed), f"{path.name}: {_violations(text, module, allowed)}"
        assert "sys_info(" not in text or "check_version=False" in text


@pytest.mark.parametrize(
    "source",
    [
        "import mne\npath = mne.datasets.sample.data_path()\n",
        "from mne import Report\n",
        "from mne import datasets\n",
        "from mne_icalabel import datasets\n",
        "from urllib import request\n",
        "import urllib\nurllib.request.urlopen('x')\n",
        "import mne as m\nm.datasets.sample\n",
        "from mne.datasets import sample\n",
        "import importlib\nimportlib.import_module('socket')\n",
        "__import__('ssl')\n",
        "import pooch\n",
        "from logging import handlers\n",
        "from asyncio import open_connection\n",
        "from mne.report import Report\n",
        "from mne import report\n",
        "import mne.report\n",
        "import builtins\nbuiltins.__import__('ssl')\n",
        "import importlib\nimportlib.__import__('socket')\n",
        "import importlib\nimportlib.import_module(name='socket')\n",
    ],
)
def test_banned_api_check_catches_every_form(source: str) -> None:
    assert _violations(source, "neurogrid.example")


def test_banned_api_check_allows_harmless_code() -> None:
    assert not _violations(
        "import logging\nimport json\nfrom pathlib import Path\nlogging.getLogger()\n", "x.y"
    )


def _tool(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False
    )


def test_schemas_are_up_to_date() -> None:
    result = _tool("tools/gen_schemas.py", "--check")
    assert result.returncode == 0, result.stdout


def test_fixtures_are_reproducible() -> None:
    result = _tool("tools/gen_fixtures.py", "--check")
    assert result.returncode == 0, result.stdout


def test_matrix_coverage() -> None:
    result = _tool("tools/check_matrix_coverage.py")
    assert result.returncode == 0, result.stdout
