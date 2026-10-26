"""The licence gate (NG-N07, CON-01, D-05): tools/licenses.py stage 1 (exact allowlist with reviewed,
version-pinned exceptions) and stage 2 (copyleft tripwire) run on a throwaway environment with synthetic
distributions, so each stage is shown to stop what it must stop; and no NeuroGrid module imports a copyleft
package (MetaBCI GPL-2.0, OpenViBE AGPL, EEGPrep, D-05). The component check of the locked wheels of both
targets is tested in tests/docs/test_notices.py; the real gate run is part of the P5 acceptance."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

import licenses  # type: ignore[import-not-found]

ROOT = Path(__file__).parent.parent.parent
COPYLEFT_IMPORTS = frozenset({"metabci", "openvibe", "eegprep"})  # D-05, PRD §22


@pytest.fixture(scope="module")
def empty_environment(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """(interpreter, site-packages) of a virtual environment without any distribution."""
    venv = tmp_path_factory.mktemp("gate") / "venv"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(venv)], check=True)
    python = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    site = subprocess.run(
        [str(python), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return python, Path(site)


def _distribution(site: Path, name: str, license_field: str, classifiers: tuple[str, ...] = ()) -> Path:
    """An installed distribution as importlib.metadata sees it: a dist-info folder with METADATA."""
    info = site / f"{name}-1.0.dist-info"
    info.mkdir()
    lines = ["Metadata-Version: 2.1", f"Name: {name}", "Version: 1.0", f"License: {license_field}"]
    lines += [f"Classifier: {classifier}" for classifier in classifiers]
    (info / "METADATA").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (info / "RECORD").write_text(f"{name}-1.0.dist-info/METADATA,,\n", encoding="utf-8")
    return info


@pytest.mark.parametrize(
    ("license_field", "classifiers", "allowlist", "copyleft"),
    [
        ("MIT", (), "ok", "ok"),
        ("GPL-3.0-or-later", (), "FAIL", "FAIL"),
        ("LGPL-2.1-or-later", (), "FAIL", "FAIL"),
        ("MIT OR GPL-2.0-or-later", (), "FAIL", "FAIL"),
        # the classifier wins with --from=mixed: a permissive License field does not hide a GPL classifier
        ("MIT", ("License :: OSI Approved :: GNU General Public License v2 (GPLv2)",), "FAIL", "FAIL"),
        ("AGPL-3.0-only", (), "FAIL", "FAIL"),
        ("Proprietary", (), "FAIL", "ok"),  # not copyleft, but not on the allowlist either
    ],
)
def test_each_stage_stops_what_it_must(
    empty_environment: tuple[Path, Path],
    capsys: pytest.CaptureFixture[str],
    license_field: str,
    classifiers: tuple[str, ...],
    allowlist: str,
    copyleft: str,
) -> None:
    python, site = empty_environment
    info = _distribution(site, "synthetic_dist", license_field, classifiers)
    try:
        passed = licenses.run_stages("synthetic", python)
    finally:
        for child in info.iterdir():
            child.unlink()
        info.rmdir()
    printed = capsys.readouterr().out.splitlines()
    assert f"synthetic / allowlist: {allowlist}" in printed
    assert f"synthetic / copyleft: {copyleft}" in printed
    assert passed is (allowlist == copyleft == "ok")


def test_reviewed_exceptions_are_version_pinned() -> None:
    """A package outside the allowlist passes only as a reviewed name:version exception (A-56)."""
    entries = licenses._lines(licenses.GATE / "exceptions.txt")
    assert entries and all(entry.count(":") == 1 and entry.split(":")[1][0].isdigit() for entry in entries)
    stage1 = dict(licenses.stage_commands(Path(sys.executable)))["allowlist"]
    assert stage1[stage1.index("--ignore-packages") + 1 :] == entries


def _imports(source: str) -> set[str]:
    found = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    return found


def test_the_import_scan_sees_every_import_form() -> None:
    source = "import metabci.x\nfrom openvibe import y\nimport os, eegprep as e\nfrom . import local\n"
    assert _imports(source) & COPYLEFT_IMPORTS == COPYLEFT_IMPORTS


def test_no_copyleft_imports() -> None:
    """CON-01: neither the package nor its tools import MetaBCI, OpenViBE or EEGPrep (D-05)."""
    files = [*(ROOT / "src" / "neurogrid").rglob("*.py"), *(ROOT / "tools").glob("*.py")]
    assert len(files) > 50
    offending = {
        path.relative_to(ROOT).as_posix(): sorted(
            _imports(path.read_text(encoding="utf-8")) & COPYLEFT_IMPORTS
        )
        for path in files
    }
    assert {path: names for path, names in offending.items() if names} == {}
