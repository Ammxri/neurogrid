"""NeuroGrid as the command line of the main project (A-101): the research configuration, the argument list
and the handling of exit codes, without running NeuroGrid (the smoke tests run it)."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from neuroarena import datasets, neurogrid_cli, paths


def test_write_config_is_exactly_the_research_configuration(tmp_path) -> None:
    """F5d and A-101: min_channels = number of EEG channels, the dataset's line frequency, nothing else."""
    path = neurogrid_cli.write_config(datasets.DATASETS["Cho2017"], tmp_path / "x" / "neurogrid.toml")
    assert (
        path.read_bytes()
        == b"[quality]\nmin_channels = 64\n\n[metadata.defaults]\nline_frequency_hz = 60.0\n"
    )
    zhou = neurogrid_cli.write_config(datasets.DATASETS["Zhou2016"], tmp_path / "zhou.toml").read_text(
        "utf-8"
    )
    assert "min_channels = 14\n" in zhou and "line_frequency_hz = 50.0\n" in zhou


def test_check_command_is_the_a101_call(tmp_path) -> None:
    command = neurogrid_cli.check_command(Path("work"), Path("c.toml"), Path("r.json"), 3, repo=tmp_path)
    assert command == [
        neurogrid_cli.UV,
        "run",
        "--project",
        str(tmp_path.absolute()),
        "--locked",
        "neurogrid",
        "check",
        str(Path("work").absolute()),
        "--config",
        str(Path("c.toml").absolute()),
        "--show-paths",
        "--jobs",
        "3",
        "--out",
        str(Path("r.json").absolute()),
    ]
    assert neurogrid_cli.check_command(Path("w"), Path("c"), Path("o"), 1)[3] == str(paths.REPO.absolute())
    for jobs in (0, 65, True):
        with pytest.raises(ValueError):
            neurogrid_cli.check_command(Path("w"), Path("c"), Path("o"), jobs)


def _fake_check(monkeypatch: pytest.MonkeyPatch, script: str) -> None:
    """Replace the NeuroGrid call by ``python -c script`` with the results path as its argument."""

    def command(folder: Path, config: Path, out: Path, jobs: int, repo: Path = paths.REPO) -> list[str]:
        return [sys.executable, "-c", script, str(out)]

    monkeypatch.setattr(neurogrid_cli, "check_command", command)


def test_run_check_accepts_exit_0_and_1_with_a_results_file(tmp_path, monkeypatch) -> None:
    out = tmp_path / "run" / "results.json"
    for code in (0, 1):
        _fake_check(
            monkeypatch,
            f"import sys, pathlib; pathlib.Path(sys.argv[1]).write_text('{{}}'); sys.exit({code})",
        )
        assert neurogrid_cli.run_check(tmp_path, tmp_path / "c.toml", out, 1) == out


def test_run_check_refuses_other_exit_codes_and_a_missing_file(tmp_path, monkeypatch) -> None:
    out = tmp_path / "results.json"
    out.write_text("stale")  # a file of an earlier call never counts
    _fake_check(monkeypatch, "import sys; sys.exit(0)")
    with pytest.raises(neurogrid_cli.NeuroGridError, match="no results file"):
        neurogrid_cli.run_check(tmp_path, tmp_path / "c.toml", out, 1)
    home = str(Path.home())
    script = f"import sys; sys.stderr.write('line 1\\nfailed in ' + {home!r} + '\\\\x\\n'); sys.exit(2)"
    _fake_check(monkeypatch, script)
    with pytest.raises(neurogrid_cli.NeuroGridError) as error:
        neurogrid_cli.run_check(tmp_path, tmp_path / "c.toml", out, 1)
    message = str(error.value)
    assert "exit code 2" in message and "failed in ~" in message and home not in message


def test_run_check_ends_the_process_tree_on_timeout(tmp_path, monkeypatch) -> None:
    _fake_check(monkeypatch, "import time; time.sleep(60)")
    started = time.monotonic()
    with pytest.raises(neurogrid_cli.NeuroGridError, match="did not end"):
        neurogrid_cli.run_check(tmp_path, tmp_path / "c.toml", tmp_path / "r.json", 1, timeout_s=1.0)
    assert time.monotonic() - started < 30
