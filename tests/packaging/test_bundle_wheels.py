"""The real wheelhouse of the bundle, offline from uv.lock (NG-N04, A-48, A-58): every runtime package has a
cp312 wheel for win_amd64 and for manylinux <= 2_28 x86_64, the runtime export holds no dev or docs package,
and nothing of the runtime set needs the _dbm module that the Linux bundle leaves out.

`uv export` needs uv: from the environment variable UV (set by `uv run`) or from PATH; without it these tests
skip with that reason (CI always has uv).
"""

from __future__ import annotations

import ast
import os
import re
import shutil
import subprocess
import sys
import tomllib
from importlib import metadata
from pathlib import Path

import pytest
from packaging.utils import canonicalize_name

import bundle

ROOT = Path(__file__).resolve().parents[2]
UV = os.environ.get("UV") or shutil.which("uv")
needs_uv = pytest.mark.skipif(UV is None, reason="uv not found: run the tests through `uv run` or set UV")


def _export(*options: str) -> set[str]:
    assert UV is not None
    command = [
        UV,
        "export",
        "--frozen",
        "--no-emit-project",
        "--format",
        "requirements-txt",
        "--no-header",
        *options,
    ]
    text = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True
    ).stdout
    return {pin.name for pin in bundle.parse_requirements(text)}


@needs_uv
@pytest.mark.parametrize("platform", bundle.PLATFORMS)
def test_every_runtime_package_has_a_fitting_wheel(platform: str) -> None:
    pins = bundle.parse_requirements(bundle.export_requirements())
    uv_lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    python = bundle.load_bundle_lock()["python"]["version"]
    wheels = bundle.select_wheels(uv_lock, pins, platform, python)  # raises for a package without a wheel
    assert len(wheels) >= 50
    names = {w.name for w in wheels}
    assert {"mne", "numpy", "scipy", "pydantic", "typer", "deno", "bids-validator-deno"} <= names
    if platform == "linux_x86_64":
        glibc = bundle.highest_manylinux([w.filename for w in wheels])
        assert glibc is not None and glibc <= (2, 28)
        assert "colorama" not in names
    else:
        assert all(w.filename.endswith(("-win_amd64.whl", "-none-any.whl")) for w in wheels)


@needs_uv
def test_runtime_export_holds_no_dev_or_docs_only_package() -> None:
    """The bundle's export (--no-default-groups) holds no package that only a dependency group asks for:
    with `default-groups = ["dev", "docs"]` the older --no-dev lets the docs group into the wheelhouse."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    runtime_direct = {
        canonicalize_name(r.split("==")[0].split("[")[0]) for r in project["project"]["dependencies"]
    }
    runtime = _export("--no-default-groups")
    assert runtime_direct <= runtime
    groups = project.get("dependency-groups", {})
    assert "dev" in groups
    for group, requirements in groups.items():
        direct = {canonicalize_name(re.split(r"[=<>~!\[; ]", r, maxsplit=1)[0]) for r in requirements}
        leaked = (direct - runtime_direct) & runtime
        assert not leaked, (group, leaked)
        assert direct <= _export("--only-group", group)
    assert not {"pytest", "ruff", "mypy", "mkdocs", "mkdocs-material"} & runtime


def _runtime_distributions() -> list[metadata.Distribution]:
    pins = bundle.parse_requirements(bundle.export_requirements())
    names = {pin.name for pin in pins}
    found = {}
    for dist in metadata.distributions():
        name = canonicalize_name(dist.metadata["Name"] or "")
        if name in names:
            found.setdefault(name, dist)
    return list(found.values())


@needs_uv
def test_no_runtime_package_uses_dbm_or_shelve() -> None:
    hits = []
    for dist in _runtime_distributions():
        for file in dist.files or []:
            if file.suffix != ".py":
                continue
            try:
                tree = ast.parse(
                    Path(str(dist.locate_file(file))).read_text(encoding="utf-8", errors="replace")
                )
            except (SyntaxError, OSError):
                continue
            for node in ast.walk(tree):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else []
                if isinstance(node, ast.ImportFrom) and node.module and not node.level:
                    names = [node.module]
                if any(n.split(".")[0] in ("dbm", "_dbm", "shelve") for n in names):
                    hits.append(f"{dist.metadata['Name']}: {file}")
    assert not hits, hits


TRIMMED_IMPORTS = r"""
import importlib, sys
sys.modules["_dbm"] = None  # the trimmed Linux interpreter has no _dbm (Berkeley DB, bundle_lock.json)
failed = []
for name in sys.argv[1:]:
    try:
        importlib.import_module(name)
    except Exception as exc:
        failed.append(f"{name}: {type(exc).__name__}: {exc}")
print("\n".join(failed))
"""


@needs_uv
def test_every_runtime_package_imports_without_the_berkeley_db_module() -> None:
    modules = set()
    for dist in _runtime_distributions():
        top = dist.read_text("top_level.txt")
        candidates = top.split() if top else []
        if not candidates:
            for file in dist.files or []:
                parts = file.parts
                if len(parts) == 2 and parts[1] == "__init__.py" or len(parts) == 1 and file.suffix == ".py":
                    candidates.append(parts[0].removesuffix(".py"))
        modules.update(c for c in candidates if c.isidentifier() and not c.startswith("_"))
    assert {"mne", "numpy", "scipy", "onnxruntime", "typer"} <= modules
    env = {
        **os.environ,
        "MPLBACKEND": "Agg",
    }  # pylab (matplotlib) starts pyplot, which needs no display with Agg
    result = subprocess.run(
        [sys.executable, "-c", TRIMMED_IMPORTS, "neurogrid.cli", *sorted(modules)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=600,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.strip() == "", result.stdout
