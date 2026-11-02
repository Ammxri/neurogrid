"""The NeuroGrid quality level of a recording and a session (NA-02; A-45 made precise by A-102, F5b, F5c (i),
F5e; area B "data and quality").

For every recording, r = value / effective threshold for each of the six core rules below, read from
results.json (``recordings[].metrics`` and ``config.effective_params``). M07 and M08 are measured per channel;
their value per recording is the maximum over the channels with a finite value (as the report chart, A-84).
A rule that is not measurable for a recording (state ``not_checkable`` or ``not_applicable``, a missing or
null value, no channel with a finite value, or ``metrics`` of the recording itself ``not_checkable``) is
left out and counted. The worst (largest) ratio wins and gives the level:

    Q1: r < 0.5    Q2: 0.5 <= r < 0.75    Q3: 0.75 <= r < 1.0    Q4: 1.0 <= r < 1.5    Q5: r >= 1.5

Q4 starts at the threshold, so Q1-Q3 mean "below every threshold" (F5c (i)). Without any measurable rule a
recording has no level; it is reported, never dropped. CORE-M07-02 (plausibility of the line frequency) does
not count (F5b). The level of a session is the worst level of its runs that have one (F5e); a session none of
whose runs has a level has none. Only research/ uses this level (A-45).
"""

from __future__ import annotations

import json
import math
import shutil
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from neuroarena import export, neurogrid_cli, paths
from neuroarena.datasets import DatasetSpec
from neuroarena.keys import Condition, RecordingKey, SessionKey

if TYPE_CHECKING:
    from moabb.datasets.base import BaseDataset


@dataclass(frozen=True)
class MetricSource:
    """Where results.json holds the value and the threshold of one core rule."""

    rule_id: str
    metric: str  # key in recordings[].metrics
    field: str  # "value" (per recording) or the field of each channel in metrics[metric]["channels"]
    per_channel: bool
    parameter: str  # config.effective_params[rule_id][parameter]["value"] is the threshold


RULES = (
    MetricSource("CORE-M06-01", "M06", "value", False, "max_fraction"),
    MetricSource("CORE-M07-01", "M07", "ratio", True, "max_ratio"),
    MetricSource("CORE-M08-01", "M08", "flat_fraction", True, "max_fraction"),
    MetricSource("CORE-M08-02", "M08", "clipped_fraction", True, "max_fraction"),
    MetricSource("CORE-M09-01", "M09a", "value", False, "max_fraction"),
    MetricSource("CORE-M09-02", "M09b", "value", False, "max_fraction"),
)
# Lower bounds of Q2-Q5 (F5c (i)); a ratio equal to a bound belongs to the higher level.
BOUNDARIES = (0.5, 0.75, 1.0, 1.5)
LEVELS = (1, 2, 3, 4, 5)
QUALITY_VERSION = 1
# States of a metric (or of one channel of M07/M08) that make it not measurable.
UNMEASURED_STATES = ("not_checkable", "not_applicable")


@dataclass(frozen=True)
class RecordingQuality:
    key: RecordingKey
    ratios: Mapping[str, float]  # rule id -> r, measurable rules only
    unmeasured: tuple[str, ...]  # rule ids left out, in the order of RULES
    worst_rule: str | None  # rule id of the largest ratio (first in RULES order on a tie); None without one
    worst_ratio: float | None
    level: int | None  # 1-5; None without a measurable rule


@dataclass(frozen=True)
class SessionQuality:
    key: SessionKey
    runs: tuple[RecordingKey, ...]  # every run of the session, sorted
    level: int | None  # worst level of the runs that have one; None if none has
    runs_without_level: int


@dataclass(frozen=True)
class ConditionQuality:
    """The quality of one dataset under one condition, as ``assess`` stores it in quality.json."""

    dataset: str
    condition: Condition
    recordings: Mapping[RecordingKey, RecordingQuality]
    sessions: Mapping[SessionKey, SessionQuality]

    def to_dict(self) -> dict[str, Any]:
        """The JSON form: ``{"version": 1, "dataset", "condition": <id>, "recordings": [{"dataset",
        "subject", "session", "run", "ratios", "unmeasured", "worst_rule", "worst_ratio", "level"}],
        "sessions": [{"dataset", "subject", "session", "runs": [<run>], "level", "runs_without_level"}]}``,
        lists sorted by key; floats as Python writes them (repr), so equal runs give equal files."""
        recordings = [
            {
                "dataset": key.dataset,
                "subject": key.subject,
                "session": key.session,
                "run": key.run,
                "ratios": {
                    rule.rule_id: item.ratios[rule.rule_id] for rule in RULES if rule.rule_id in item.ratios
                },
                "unmeasured": list(item.unmeasured),
                "worst_rule": item.worst_rule,
                "worst_ratio": item.worst_ratio,
                "level": item.level,
            }
            for key, item in sorted(self.recordings.items())
        ]
        sessions = [
            {
                "dataset": key.dataset,
                "subject": key.subject,
                "session": key.session,
                "runs": [run.run for run in item.runs],
                "level": item.level,
                "runs_without_level": item.runs_without_level,
            }
            for key, item in sorted(self.sessions.items())
        ]
        return {
            "version": QUALITY_VERSION,
            "dataset": self.dataset,
            "condition": self.condition.id,
            "recordings": recordings,
            "sessions": sessions,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ConditionQuality:
        if data.get("version") != QUALITY_VERSION:
            raise ValueError(f"{paths.QUALITY_FILE}: unknown version {data.get('version')!r}")
        order = [rule.rule_id for rule in RULES]
        recordings: dict[RecordingKey, RecordingQuality] = {}
        for entry in data["recordings"]:
            key = RecordingKey(entry["dataset"], int(entry["subject"]), entry["session"], entry["run"])
            ratios = {rule: float(entry["ratios"][rule]) for rule in order if rule in entry["ratios"]}
            if set(entry["ratios"]) - set(order) or set(entry["unmeasured"]) - set(order):
                raise ValueError(f"{paths.QUALITY_FILE}: unknown rule in {key}")
            worst = entry["worst_ratio"]
            recordings[key] = RecordingQuality(
                key=key,
                ratios=ratios,
                unmeasured=tuple(rule for rule in order if rule in entry["unmeasured"]),
                worst_rule=entry["worst_rule"],
                worst_ratio=None if worst is None else float(worst),
                level=entry["level"],
            )
        sessions: dict[SessionKey, SessionQuality] = {}
        for entry in data["sessions"]:
            key = SessionKey(entry["dataset"], int(entry["subject"]), entry["session"])
            sessions[key] = SessionQuality(
                key=key,
                runs=tuple(
                    sorted(RecordingKey(key.dataset, key.subject, key.session, run) for run in entry["runs"])
                ),
                level=entry["level"],
                runs_without_level=int(entry["runs_without_level"]),
            )
        return cls(
            dataset=data["dataset"],
            condition=Condition.from_id(data["condition"]),
            recordings=dict(sorted(recordings.items())),
            sessions=dict(sorted(sessions.items())),
        )


def level_for_ratio(ratio: float) -> int:
    """The level 1-5 of a finite ratio >= 0 (BOUNDARIES); ValueError for a negative or non-finite ratio."""
    if isinstance(ratio, bool) or not isinstance(ratio, int | float) or not math.isfinite(ratio) or ratio < 0:
        raise ValueError(f"not a finite ratio >= 0: {ratio!r}")
    return LEVELS[sum(ratio >= bound for bound in BOUNDARIES)]


def _finite(value: Any) -> float | None:
    """``value`` as a float when it is a finite number (never a bool), else None."""
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        return None
    return float(value)


def thresholds(results: Mapping[str, Any]) -> dict[str, float]:
    """The effective threshold of every rule of RULES (``config.effective_params``); ValueError if one is
    missing or not a finite number > 0."""
    params = results["config"]["effective_params"]
    out: dict[str, float] = {}
    for rule in RULES:
        try:
            value = _finite(params[rule.rule_id][rule.parameter]["value"])
        except (KeyError, TypeError):
            value = None
        if value is None or value <= 0:
            raise ValueError(f"results.json: no usable threshold {rule.parameter} of {rule.rule_id}")
        out[rule.rule_id] = value
    return out


def measured_value(metrics: Any, rule: MetricSource) -> float | None:
    """The value of ``rule`` in the metrics of one recording (maximum over the channels with a finite value
    for M07/M08), or None when it is not measurable (module docstring)."""
    if not isinstance(metrics, Mapping) or metrics.get("state") == "not_checkable":
        return None
    entry = metrics.get(rule.metric)
    if not isinstance(entry, Mapping) or entry.get("state") in UNMEASURED_STATES:
        return None
    if not rule.per_channel:
        return _finite(entry.get(rule.field))
    channels = entry.get("channels")
    if not isinstance(channels, Mapping):
        return None
    values = [
        value
        for channel in channels.values()
        if isinstance(channel, Mapping) and channel.get("state") not in UNMEASURED_STATES
        for value in (_finite(channel.get(rule.field)),)
        if value is not None
    ]
    return max(values) if values else None


def recording_quality(
    results: Mapping[str, Any], index: Mapping[str, RecordingKey]
) -> dict[RecordingKey, RecordingQuality]:
    """Quality of every recording of a results.json document (parsed JSON) of a ``--show-paths`` check,
    mapped through the export index (``recordings[].id`` is the file path relative to the checked folder).
    Thresholds from ``config.effective_params``. Every recording of the index must be in the results, and
    every recording of the results in the index (ValueError otherwise)."""
    limits = thresholds(results)
    entries = {entry["id"]: entry for entry in results["recordings"]}
    if len(entries) != len(results["recordings"]):
        raise ValueError("results.json: a recording id appears twice")
    missing, unknown = sorted(set(index) - set(entries)), sorted(set(entries) - set(index))
    if missing or unknown:
        raise ValueError(f"results.json and the index differ: missing {missing}, not in the index {unknown}")
    out: dict[RecordingKey, RecordingQuality] = {}
    for name, key in sorted(index.items(), key=lambda item: item[1]):
        metrics = entries[name].get("metrics")
        ratios: dict[str, float] = {}
        unmeasured: list[str] = []
        for rule in RULES:
            value = measured_value(metrics, rule)
            if value is None:
                unmeasured.append(rule.rule_id)
            else:
                ratios[rule.rule_id] = value / limits[rule.rule_id]
        worst_rule = max(ratios, key=lambda rule_id: ratios[rule_id]) if ratios else None  # first on a tie
        worst_ratio = ratios[worst_rule] if worst_rule is not None else None
        out[key] = RecordingQuality(
            key=key,
            ratios=ratios,
            unmeasured=tuple(unmeasured),
            worst_rule=worst_rule,
            worst_ratio=worst_ratio,
            level=None if worst_ratio is None else level_for_ratio(worst_ratio),
        )
    return out


def session_quality(recordings: Mapping[RecordingKey, RecordingQuality]) -> dict[SessionKey, SessionQuality]:
    """The level of every session: the worst level of its runs (F5e)."""
    groups: dict[SessionKey, list[RecordingKey]] = {}
    for key in sorted(recordings):
        groups.setdefault(key.session_key, []).append(key)
    out: dict[SessionKey, SessionQuality] = {}
    for session, runs in sorted(groups.items()):
        levels = [recordings[run].level for run in runs]
        known = [level for level in levels if level is not None]
        out[session] = SessionQuality(
            key=session,
            runs=tuple(runs),
            level=max(known) if known else None,
            runs_without_level=len(levels) - len(known),
        )
    return out


def assess(
    dataset: BaseDataset,
    spec: DatasetSpec,
    condition: Condition,
    subjects: Sequence[int],
    work: Path,
    out: Path,
    jobs: int,
) -> ConditionQuality:
    """The quality step of one dataset and condition (one NeuroGrid call, A-101):
    1. ``export.write_fifs(dataset, spec, subjects, work)`` (``dataset`` is ``datasets.degraded_dataset``).
    2. ``neurogrid_cli.write_config(spec, out / paths.CONFIG_FILE)``.
    3. ``neurogrid_cli.run_check(work, <config>, out / paths.RESULTS_FILE, jobs)``.
    4. Copy the index to ``out / paths.INDEX_FILE``; ``recording_quality`` and ``session_quality``; write
       ``out / paths.QUALITY_FILE`` (``to_dict``, UTF-8, LF, sort_keys, two-space indent).
    5. Delete ``work`` (F1: working files are removed after each condition), also when a step fails.
    ``out`` is ``paths.neurogrid_dir(run_id, spec.name, condition.id)``. Returns the ConditionQuality.

    ValueError before anything is written when ``work`` exists and is not empty (it is not deleted then).
    quality.json is written last and atomically: its presence marks a finished step."""
    if not export.folder_is_free(work):
        raise ValueError(f"the working folder must be new or empty: {Path(work).name}")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / paths.QUALITY_FILE).unlink(missing_ok=True)
    try:
        index = export.write_fifs(dataset, spec, subjects, work)
        config = neurogrid_cli.write_config(spec, out / paths.CONFIG_FILE)
        results_path = neurogrid_cli.run_check(work, config, out / paths.RESULTS_FILE, jobs)
        shutil.copyfile(Path(work) / paths.INDEX_FILE, out / paths.INDEX_FILE)
        results = json.loads(results_path.read_bytes().decode("utf-8"))
        recordings = recording_quality(results, index)
        result = ConditionQuality(spec.name, condition, recordings, session_quality(recordings))
        write_quality(result, out / paths.QUALITY_FILE)
        return result
    finally:
        _remove_tree(Path(work))


def write_quality(quality: ConditionQuality, path: Path) -> Path:
    """``quality.to_dict()`` as JSON (UTF-8, LF, sort_keys, two-space indent), written atomically."""
    path = Path(path)
    text = json.dumps(quality.to_dict(), indent=2, sort_keys=True, allow_nan=False) + "\n"
    partial = path.with_name(path.name + ".partial")
    partial.write_bytes(text.encode("utf-8"))
    partial.replace(path)
    return path


def _remove_tree(folder: Path) -> None:
    """Delete ``folder`` (F1); read-only files are made writable first (Windows)."""

    def retry(function: Any, name: str, _exc: BaseException) -> None:
        Path(name).chmod(stat.S_IWRITE)
        function(name)

    if folder.exists():
        shutil.rmtree(folder, onexc=retry)


def read_quality(path: Path) -> ConditionQuality:
    """quality.json as ``assess`` wrote it (the file, or the folder that holds it)."""
    path = Path(path)
    if path.is_dir():
        path = path / paths.QUALITY_FILE
    return ConditionQuality.from_dict(json.loads(path.read_bytes().decode("utf-8")))
