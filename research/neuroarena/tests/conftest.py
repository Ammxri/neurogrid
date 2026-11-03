"""Test doubles of area C (decoders and evaluation): area B's functions and the worker pool, replaced in this
process with ``monkeypatch`` so that the runner's own logic runs without area B and without spawned workers.
The doubles follow area B's documented contract (freeze_api section 4): ``degraded_dataset`` keeps subjects,
sessions, runs and events; ``assess`` writes quality.json into ``out`` and returns the ConditionQuality."""

from __future__ import annotations

import concurrent.futures
import contextlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from neuroarena import datasets, paths, quality, runner, synthetic
from neuroarena.keys import Condition, SessionKey

CHANNELS = ("Fz", "C3", "Cz", "C4", "Pz", "O1", "Oz", "O2")


class InlineExecutor(concurrent.futures.Executor):
    """Runs every submitted call at once in this process and records the submissions in order."""

    def __init__(self) -> None:
        self.submitted: list[Any] = []

    def submit(self, fn: Any, /, *args: Any, **kwargs: Any) -> concurrent.futures.Future:
        self.submitted.append(args[0] if args else None)
        future: concurrent.futures.Future = concurrent.futures.Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except Exception as error:
            future.set_exception(error)
        return future


def fake_moabb(spec: datasets.DatasetSpec, n_subjects: int = 2, seed: int = 7) -> Any:
    """A small MOABB FakeDataset shaped like ``spec``: 8 channels at 128 Hz, two sessions of one run each, 40
    trials per run (at least 10 per class)."""
    from moabb.datasets.fake import FakeDataset

    return FakeDataset(
        event_list=list(spec.events),
        n_sessions=2,
        n_runs=1,
        n_subjects=n_subjects,
        code=f"Arena{spec.name}",
        paradigm=spec.paradigm,
        channels=CHANNELS,
        seed=seed,
        sfreq=128,
        duration=130,
        n_events=40,
    )


def fake_level(condition: Condition, subject: int, session: str) -> int | None:
    """The quality level the fake quality step gives a session: clean 1, a degraded level l gives
    min(5, l + 1); subject 2, session "1" has no level at line_noise-5."""
    if condition.id == "line_noise-5" and subject == 2 and session == "1":
        return None
    return 1 if condition.level == 0 else min(5, condition.level + 1)


def fake_assess(
    dataset: Any,
    spec: datasets.DatasetSpec,
    condition: Condition,
    subjects: Any,
    work: Path,
    out: Path,
    jobs: int,
) -> quality.ConditionQuality:
    """Area B's quality step as a double: results.json (one recording per session with a metric) and
    quality.json (one level per session). Like area B's step it refuses a non-empty work folder."""
    if work.exists() and any(work.iterdir()):
        raise ValueError(f"work folder {work.name} is not empty")
    work.mkdir(parents=True, exist_ok=True)
    (work / "scratch.fif").write_bytes(b"")
    sessions, recordings = [], []
    for subject in subjects:
        for session in ("0", "1"):
            level = fake_level(condition, subject, session)
            sessions.append({"subject": subject, "session": session, "level": level})
            recordings.append(
                {
                    "id": f"sub-{subject:03d}_ses-{session}_run-0_eeg.fif",
                    "format": "fif",
                    "metrics": {"M06": {"value": 0.1 * (level or 9), "state": "ok"}},
                }
            )
    results = {"environment": {"python": "x"}, "recordings": recordings}
    (out / paths.RESULTS_FILE).write_text(json.dumps(results), encoding="utf-8", newline="\n")
    document = {"version": 1, "dataset": spec.name, "condition": condition.id, "sessions": sessions}
    (out / paths.QUALITY_FILE).write_text(
        json.dumps(document, sort_keys=True), encoding="utf-8", newline="\n"
    )
    (work / "scratch.fif").unlink()
    work.rmdir()
    return fake_read_quality(out / paths.QUALITY_FILE)


def fake_read_quality(path: Path) -> quality.ConditionQuality:
    document = json.loads(path.read_text(encoding="utf-8"))
    sessions = {}
    for item in document["sessions"]:
        key = SessionKey(document["dataset"], item["subject"], item["session"])
        level = item["level"]
        sessions[key] = quality.SessionQuality(key, (), level, 0 if level is not None else 1)
    return quality.ConditionQuality(
        document["dataset"], Condition.from_id(document["condition"]), {}, sessions
    )


@pytest.fixture
def moabb_double() -> Any:
    """``fake_moabb``: a small MOABB FakeDataset shaped like a DatasetSpec."""
    return fake_moabb


@pytest.fixture
def area_b(monkeypatch: pytest.MonkeyPatch) -> None:
    """Area B's functions as documented doubles (freeze_api section 4)."""
    monkeypatch.setattr(datasets, "configure_storage", lambda mne_data=paths.MNE_DATA: None)
    monkeypatch.setattr(datasets, "moabb_dataset", fake_moabb)
    monkeypatch.setattr(synthetic, "fake_dataset", fake_moabb)
    monkeypatch.setattr(datasets, "degraded_dataset", lambda spec, condition, base=None: base)
    monkeypatch.setattr(quality, "assess", fake_assess)
    monkeypatch.setattr(quality, "read_quality", fake_read_quality)


@pytest.fixture
def inline_pool(monkeypatch: pytest.MonkeyPatch) -> list[InlineExecutor]:
    """The runner's worker pool replaced by InlineExecutor (the doubles above exist in this process only);
    returns the list of executors the runner opened."""
    opened: list[InlineExecutor] = []

    @contextlib.contextmanager
    def pool(processes: int) -> Iterator[InlineExecutor]:
        executor = InlineExecutor()
        opened.append(executor)
        yield executor

    monkeypatch.setattr(runner, "_pool", pool)
    return opened
