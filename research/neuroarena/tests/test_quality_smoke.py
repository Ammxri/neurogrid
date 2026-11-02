"""NA-02 and NA-03 through the real command line of the main project (A-101; marker ``smoke``, F11 B): a
synthetic recording goes as FIF through ``neurogrid check`` to a quality level, twice with the same result,
and NeuroGrid's metrics respond to each degradation ladder (lowest and highest level)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from neuroarena import datasets, degradation, export, neurogrid_cli, paths, quality, synthetic
from neuroarena.keys import CLEAN, Condition, RecordingKey

pytestmark = pytest.mark.smoke

SPEC = datasets.DATASETS["Zhou2016"]  # 14 EEG channels at 250 Hz: M06 and M09 measurable (F5d)
JOBS = 2


@pytest.fixture(autouse=True)
def _needs_uv() -> None:
    if shutil.which(neurogrid_cli.UV) is None and not Path(neurogrid_cli.UV).is_file():
        pytest.skip("uv is neither on PATH nor in UV")


def _metrics(results: dict) -> list:
    return [(entry["id"], entry["metrics"]) for entry in results["recordings"]]


def test_assess_twice_gives_the_same_quality(tmp_path) -> None:
    """NA-02 integration: synthetic raw -> FIF -> neurogrid check -> Q, twice equal (A-11 of NeuroGrid and
    A-103 of the degradation), with the files of the run folder and without the working folder."""
    view = datasets.degraded_dataset(SPEC, CLEAN, synthetic.fake_dataset(SPEC, n_subjects=1))
    outcomes = []
    for attempt in ("a", "b"):
        out = paths.neurogrid_dir(f"smoke-{attempt}", SPEC.name, CLEAN.id, runs=tmp_path / "runs")
        work = paths.work_dir(f"smoke-{attempt}", SPEC.name, CLEAN.id, work=tmp_path / "work")
        result = quality.assess(view, SPEC, CLEAN, [1], work, out, JOBS)
        assert not work.exists()
        names = {paths.CONFIG_FILE, paths.INDEX_FILE, paths.RESULTS_FILE, paths.QUALITY_FILE}
        assert names <= {path.name for path in out.iterdir()}
        assert quality.read_quality(out / paths.QUALITY_FILE) == result
        results = json.loads((out / paths.RESULTS_FILE).read_bytes())
        outcomes.append((result, (out / paths.QUALITY_FILE).read_bytes(), _metrics(results)))
    (first, first_bytes, first_metrics), (second, second_bytes, second_metrics) = outcomes
    assert first == second and first_bytes == second_bytes and first_metrics == second_metrics
    assert len(first.recordings) == synthetic.RUNS_PER_SESSION and len(first.sessions) == 1
    for item in first.recordings.values():
        assert item.level is not None
        # the research configuration makes M06 and M09a measurable with 14 channels (F5d)
        assert {"CORE-M06-01", "CORE-M07-01", "CORE-M08-01", "CORE-M09-01"} <= set(item.ratios)
    session = next(iter(first.sessions.values()))
    assert session.level == max(item.level for item in first.recordings.values())


LADDER = (
    CLEAN,
    Condition("line_noise", 1),
    Condition("line_noise", 5),
    Condition("channels", 1),
    Condition("channels", 5),
    Condition("artifacts", 1),
    Condition("artifacts", 5),
)


def test_neurogrid_detects_each_degradation(tmp_path) -> None:
    """NA-03 detection over the command line: M07 rises with the line noise, M08 (flat channels) and M06 with
    the flat channels, M09a with the share of artefact epochs (lowest and highest level of each ladder)."""
    base = synthetic.fake_dataset(SPEC, n_subjects=1)
    folder = tmp_path / "work"
    folder.mkdir()
    index: dict[str, RecordingKey] = {}
    for subject, condition in enumerate(LADDER, start=1):
        raw = datasets.degraded_dataset(SPEC, condition, base).get_data([1])[1]["0"]["0"]
        key = RecordingKey(SPEC.name, subject, "0", "0")  # one recording per condition, told apart by subject
        raw.save(folder / export.recording_filename(key), fmt=export.FIF_FORMAT, verbose="error")
        index[export.recording_filename(key)] = key
    config = neurogrid_cli.write_config(SPEC, tmp_path / "neurogrid.toml")
    results = json.loads(
        neurogrid_cli.run_check(folder, config, tmp_path / "results.json", JOBS).read_bytes()
    )
    levels = quality.recording_quality(results, index)
    metrics = dict(_metrics(results))
    by_condition = {
        condition.id: (metrics[name], levels[key])
        for (name, key), condition in zip(index.items(), LADDER, strict=True)
    }

    def m07(condition: str) -> float:
        return max(channel["ratio"] for channel in by_condition[condition][0]["M07"]["channels"].values())

    def flat_channels(condition: str) -> int:
        channels = by_condition[condition][0]["M08"]["channels"].values()
        return sum(channel["flat_fraction"] == 1.0 for channel in channels)

    def value(condition: str, metric: str) -> float:
        return by_condition[condition][0][metric]["value"]

    # line noise: M07 rises with the level; +10 dB lies far beyond the threshold (Q5)
    threshold = results["config"]["effective_params"]["CORE-M07-01"]["max_ratio"]["value"]
    assert m07("clean") < m07("line_noise-1") < threshold < m07("line_noise-5")
    assert by_condition["line_noise-5"][1].level == 5
    # channels: M08 counts exactly the flattened channels; M06 rises with them; one flat channel is Q5 (F4b)
    assert flat_channels("clean") == 0
    assert flat_channels("channels-1") == degradation.flattened_channel_count(SPEC.n_eeg_channels, 1)
    assert flat_channels("channels-5") == degradation.flattened_channel_count(SPEC.n_eeg_channels, 5)
    assert value("channels-1", "M06") < value("channels-5", "M06")
    assert by_condition["channels-1"][1].level == by_condition["channels-5"][1].level == 5
    # artefacts: M09a rises with the share of artefact epochs
    assert value("artifacts-1", "M09a") < value("artifacts-5", "M09a")
