"""The MOABB dataset classes behind ``datasets.degraded_dataset`` and ``synthetic.fake_dataset`` (area B).

Private: this module imports MOABB when it is imported, so the frozen modules import it only inside their
functions. The classes live at module level so that their objects can be pickled (worker processes, area C).
"""

from __future__ import annotations

from typing import Any

from moabb.datasets.base import BaseDataset, CacheConfig
from moabb.datasets.preprocessing import FixedPipeline

from neuroarena import degradation, synthetic
from neuroarena.datasets import DatasetSpec
from neuroarena.keys import Condition, RecordingKey


def _code_part(text: str) -> str:
    """``text`` as a part of a MOABB code (Camel-KebabCase, lower case after the class name)."""
    return "".join(char for char in text.lower() if char.isalnum() or char == "-")


class Synthetic(BaseDataset):
    """``synthetic.fake_dataset``: SESSIONS x RUNS_PER_SESSION synthetic runs per subject."""

    def __init__(self, spec: DatasetSpec, n_subjects: int, seed: int) -> None:
        eeg, other, interval = synthetic.loader_layout(spec)
        self.spec = spec
        self.seed = seed
        self.eeg_names = eeg
        self.other_names = other
        super().__init__(
            subjects=list(range(1, n_subjects + 1)),
            sessions_per_subject=synthetic.SESSIONS,
            events={event: index + 1 for index, event in enumerate(spec.events)},
            code=f"Synthetic-{_code_part(spec.name)}-{n_subjects}-{seed}",
            interval=list(interval),
            paradigm=spec.paradigm,
        )

    def _get_single_subject_data(self, subject: int) -> dict[str, dict[str, Any]]:
        data: dict[str, dict[str, Any]] = {}
        for session_index in range(synthetic.SESSIONS):
            session = str(session_index)
            data[session] = {
                str(run): synthetic.synthetic_raw(
                    self.spec,
                    self.eeg_names,
                    self.other_names,
                    self.interval,
                    synthetic.raw_seed(self.spec, self.seed, subject, session, str(run)),
                )
                for run in range(synthetic.RUNS_PER_SESSION)
            }
        return data

    def data_path(
        self,
        subject: int,
        path: Any = None,
        force_update: bool = False,
        update_path: Any = None,
        verbose: Any = None,
    ) -> list[str]:
        return []


class Degraded(BaseDataset):
    """``datasets.degraded_dataset``: the raws of ``base`` after ``degradation.degrade`` for one condition."""

    def __init__(self, spec: DatasetSpec, condition: Condition, base: BaseDataset) -> None:
        self.spec = spec
        self.condition = condition
        self.base = base
        super().__init__(
            subjects=list(base.all_subjects),
            sessions_per_subject=base.n_sessions,
            events=dict(base.event_id),
            code=f"Degraded-{_code_part(base.code)}-{_code_part(condition.id)}",
            interval=list(base.interval),
            paradigm=base.paradigm,
            doi=base.doi,
            unit_factor=base.unit_factor,
            selected_subjects=list(base.subject_list),
            selected_sessions=base._selected_sessions,
            return_all_modalities=base.return_all_modalities,
        )

    def _get_single_subject_data(self, subject: int) -> dict[str, dict[str, Any]]:
        # the raw stage of ``base`` exactly as its own get_data loads it (sourcedata store, metadata), without
        # any processing step and without the disk cache
        sessions = self.base._get_single_subject_data_using_cache(subject, CacheConfig(), FixedPipeline([]))
        out: dict[str, dict[str, Any]] = {}
        for session, runs in sessions.items():
            out[session] = {}
            for run in list(runs):
                key = RecordingKey(self.spec.name, subject, session, run)
                out[session][run] = degradation.degrade(
                    runs.pop(run), key, self.condition, self.spec.line_frequency_hz
                )
        return out

    def data_path(
        self,
        subject: int,
        path: Any = None,
        force_update: bool = False,
        update_path: Any = None,
        verbose: Any = None,
    ) -> Any:
        return self.base.data_path(subject, path, force_update, update_path, verbose)

    def get_additional_metadata(self, subject: str, session: str, run: str) -> Any:
        return self.base.get_additional_metadata(subject, session, run)

    def _block_rep(self, block: int, repetition: int) -> Any:
        return self.base._block_rep(block, repetition)
