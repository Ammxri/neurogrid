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

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

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
        raise NotImplementedError("area B")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ConditionQuality:
        raise NotImplementedError("area B")


def level_for_ratio(ratio: float) -> int:
    """The level 1-5 of a finite ratio >= 0 (BOUNDARIES); ValueError for a negative or non-finite ratio."""
    raise NotImplementedError("area B")


def recording_quality(
    results: Mapping[str, Any], index: Mapping[str, RecordingKey]
) -> dict[RecordingKey, RecordingQuality]:
    """Quality of every recording of a results.json document (parsed JSON) of a ``--show-paths`` check,
    mapped through the export index (``recordings[].id`` is the file path relative to the checked folder).
    Thresholds from ``config.effective_params``. Every recording of the index must be in the results, and
    every recording of the results in the index (ValueError otherwise)."""
    raise NotImplementedError("area B")


def session_quality(recordings: Mapping[RecordingKey, RecordingQuality]) -> dict[SessionKey, SessionQuality]:
    """The level of every session: the worst level of its runs (F5e)."""
    raise NotImplementedError("area B")


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
    ``out`` is ``paths.neurogrid_dir(run_id, spec.name, condition.id)``. Returns the ConditionQuality."""
    raise NotImplementedError("area B")


def read_quality(path: Path) -> ConditionQuality:
    """quality.json as ``assess`` wrote it."""
    raise NotImplementedError("area B")
