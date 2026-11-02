"""The frozen interfaces of the P11 scaffold (NG-F17, NA-01 to NA-05; A-100 to A-106): what areas B (data and
quality), C (decoders and evaluation) and D (notebook, report, figures) build on. The tests of draft section 4
are the areas' own; these pin the shared contract so that the areas can work in parallel."""

from __future__ import annotations

import ast
import importlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from neuroarena import degradation, evaluation, paths, quality, records
from neuroarena.keys import CLEAN, CONDITIONS, KINDS, Condition, RecordingKey, SessionKey

PROJECT = Path(__file__).resolve().parents[1]
MODULES = (
    "neuroarena.compare",
    "neuroarena.datasets",
    "neuroarena.decoders",
    "neuroarena.degradation",
    "neuroarena.determinism",
    "neuroarena.evaluation",
    "neuroarena.export",
    "neuroarena.keys",
    "neuroarena.neurogrid_cli",
    "neuroarena.paths",
    "neuroarena.quality",
    "neuroarena.records",
    "neuroarena.runner",
    "neuroarena.synthetic",
)


def _imports(source: str) -> set[str]:
    found = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call) and getattr(node.func, "attr", getattr(node.func, "id", "")) in (
            "import_module",
            "__import__",
        ):
            found |= {arg.value.split(".")[0] for arg in node.args if isinstance(arg, ast.Constant)}
    return found


def test_the_package_never_imports_neurogrid() -> None:
    """A-100: NeuroGrid runs as the command line of the main project (A-101), never as a library."""
    files = sorted([*(PROJECT / "src").rglob("*.py"), *(PROJECT / "tests").rglob("*.py")])
    assert len(files) >= len(MODULES)
    found = {
        f.relative_to(PROJECT).as_posix() for f in files if "neurogrid" in _imports(f.read_text("utf-8"))
    }
    assert found == set()
    assert _imports(
        "import neurogrid.cli\nfrom neurogrid import x\nimportlib.import_module('neurogrid')\n"
    ) == {"neurogrid"}


def test_every_frozen_module_imports_without_heavy_libraries() -> None:
    """The interfaces import with the standard library only (numpy, mne, moabb, torch inside the functions or
    under TYPE_CHECKING), so a test of one area never pays for the libraries of another."""
    for name in MODULES:
        importlib.import_module(name)
    probe = f"import sys\nfor m in {MODULES!r}: __import__(m)\nprint(sorted(sys.modules))\n"
    loaded = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, encoding="utf-8", check=True
    ).stdout
    for heavy in ("numpy", "mne", "moabb", "torch", "braindecode", "sklearn", "pyriemann"):
        assert f"'{heavy}'" not in loaded, heavy


def test_sixteen_conditions_in_a_fixed_order() -> None:
    """F4a A: one ladder per kind, five levels each, plus the clean data."""
    assert len(CONDITIONS) == 16 and CONDITIONS[0] == CLEAN
    assert [c.id for c in CONDITIONS[1:6]] == [f"line_noise-{level}" for level in range(1, 6)]
    assert KINDS == ("line_noise", "channels", "artifacts")
    assert len({c.id for c in CONDITIONS}) == 16
    assert all(Condition.from_id(c.id) == c for c in CONDITIONS)
    for kind, level in (("clean", 1), ("line_noise", 0), ("line_noise", 6), ("hum", 1)):
        with pytest.raises(ValueError):
            Condition(kind, level)


def test_keys_take_the_loader_names() -> None:
    key = RecordingKey("Zhou2016", 1, "0", "1")
    assert key.session_key == SessionKey("Zhou2016", 1, "0")
    for bad in (("Zhou2016", 0, "0", "0"), ("Zhou2016", 1, "../x", "0"), ("Zhou2016", 1, "0", "")):
        with pytest.raises(ValueError):
            RecordingKey(*bad)


def test_ladder_values_are_the_draft_table() -> None:
    """F4c: fixed before the first run, never adapted to results."""
    assert degradation.LINE_NOISE_DB == (-15.0, -10.0, -5.0, 0.0, 10.0)
    assert degradation.LINE_NOISE_REFERENCE_BAND_HZ == (1.0, 40.0)
    assert degradation.LINE_NOISE_HARMONIC_AMPLITUDE == 0.5
    assert degradation.CHANNEL_FRACTIONS == (0.05, 0.10, 0.20, 0.35, 0.50)
    assert degradation.CHANNEL_MINIMUMS == (1, 2, 3, 4, 5)
    assert degradation.FLAT_VALUE_V == 0.0
    assert degradation.ARTIFACT_FRACTIONS == (0.05, 0.10, 0.20, 0.35, 0.50)
    assert degradation.ARTIFACT_EPOCH_S == 2.0
    assert degradation.ARTIFACT_TYPES == ("blink", "muscle", "pop")


def test_quality_rules_and_boundaries() -> None:
    """A-102: six core rules (CORE-M07-02 does not count), boundaries 0.5/0.75/1.0/1.5."""
    assert [rule.rule_id for rule in quality.RULES] == [
        "CORE-M06-01",
        "CORE-M07-01",
        "CORE-M08-01",
        "CORE-M08-02",
        "CORE-M09-01",
        "CORE-M09-02",
    ]
    assert quality.BOUNDARIES == (0.5, 0.75, 1.0, 1.5) and quality.LEVELS == (1, 2, 3, 4, 5)
    assert {rule.metric for rule in quality.RULES if rule.per_channel} == {"M07", "M08"}


def test_record_columns_are_frozen() -> None:
    """Area C writes, area D reads these columns."""
    assert records.FOLD_COLUMNS[:7] == (
        "dataset",
        "condition",
        "kind",
        "level",
        "subject",
        "session",
        "decoder",
    )
    assert records.SESSION_COLUMNS[-2:] == ("quality_level", "runs_without_level")
    assert records.CURVE_COLUMNS[:5] == records.CURVE_KEY
    for columns, key in (
        (records.FOLD_COLUMNS, records.FOLD_KEY),
        (records.SESSION_COLUMNS, records.SESSION_KEY),
        (records.CURVE_COLUMNS, records.CURVE_KEY),
    ):
        assert set(key) <= set(columns)
    assert evaluation.N_FOLDS == 5 and evaluation.CONFIDENCE == 0.95


def test_data_stay_under_local_arena_and_area_d_paths_are_reserved() -> None:
    """A-100, F1: data, working files and runs only under .local/arena (git ignores .local/)."""
    assert paths.PROJECT == PROJECT and (paths.REPO / "pyproject.toml").is_file()
    for folder in (paths.MNE_DATA, paths.WORK, paths.RUNS):
        assert folder.is_relative_to(paths.REPO / ".local" / "arena")
    assert ".local/" in (paths.REPO / ".gitignore").read_text(encoding="utf-8").splitlines()
    for folder in (paths.NOTEBOOKS, paths.REPORT_EN, paths.REPORT_ZH, paths.RESULTS):
        assert folder.is_dir() and folder.is_relative_to(PROJECT)
    run = paths.run_dir("r1", Path("runs"))
    assert (
        paths.neurogrid_dir("r1", "Zhou2016", "clean", Path("runs"))
        == run / "neurogrid" / "Zhou2016" / "clean"
    )
    assert paths.folds_file("r1", "Cho2017", "channels-3", "eegnet", Path("runs")) == (
        run / "folds" / "Cho2017" / "channels-3" / "eegnet.csv"
    )
    for bad in ("", "..", "a/b", "a\\b", ".hidden", "x" * 65, "a."):
        with pytest.raises(ValueError):
            paths.run_dir(bad, Path("runs"))


@pytest.mark.smoke
def test_neurogrid_command_line_of_the_main_project_answers() -> None:
    """A-101 precondition: the research environment reaches NeuroGrid only as the main project's command line
    (uv run --project <repo> --locked neurogrid ...). Areas B and C extend the smoke step (F11 B)."""
    uv = shutil.which("uv") or os.environ.get("UV")
    if not uv:
        pytest.skip("uv is neither on PATH nor in UV")
    result = subprocess.run(
        [uv, "run", "--project", str(paths.REPO), "--locked", "neurogrid", "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=600,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert "check" in result.stdout
