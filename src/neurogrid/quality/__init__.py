"""Signal quality metrics M06–M09 (NG-F07, D-04, A-18, A-19, A-60, A-79).

Per recording one job: a streaming pass over the full length (M07, M08, signal hash) and a deterministic
sample (M06, M09). A job has four parts: the stream, the preparation of the sample with M06, autoreject (M09a)
and ICA/ICLabel (M09b); the last two need the prepared sample. With ``--jobs 1`` they run one after the other
in this process. With ``--jobs N`` (D-14) they are tasks of a pool of N processes: the stream runs next to
the sample, autoreject next to the ICA, and for a single recording autoreject also spreads its threshold
search over the free processes. Every process installs the network guard (A-49) and computes with one BLAS
thread; the parts are put together by fixed rules, so the results are byte-identical for every N (A-11,
NG-N03). The processes start on the null device (``neurogrid.kernel.processes``): nothing they write
reaches the console (A-51, NG-N05). A job never raises: problems become a reason key that the checks
report as not_checkable.
"""

from __future__ import annotations

import math
import sys
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from neurogrid.kernel.processes import pool_context
from neurogrid.model.dataset import Recording
from neurogrid.quality.positions import Position
from neurogrid.quality.sample import (
    MethodResult,
    SampleResult,
    Stage,
    finish_sample,
    prepare_sample,
    refits,
    run_autoreject,
    run_iclabel,
)
from neurogrid.quality.stream import StreamResult, measure_stream
from neurogrid.quality.workers import worker_start

DEFAULT_LINE_HZ = 50.0  # A-18: line frequency as documented, otherwise 50 Hz
# ProcessPoolExecutor refuses more than 61 workers on Windows (WaitForMultipleObjects); --jobs allows 64
MAX_WORKERS = 61 if sys.platform == "win32" else 64
TASKS_PER_JOB = 3  # at most three parts of one recording run at the same time (stream, autoreject, ICA)
_SENT = "sent to autoreject and ICA"  # stands for the prepared sample once the parent no longer holds it


@dataclass(frozen=True)
class QualitySettings:
    flat_tolerance_uv: float = 0.1
    plateau_samples: int = 10
    min_seconds: float = 60.0
    min_channels: int = 16
    mode: str = "sample"
    segments: int = 10
    segment_s: float = 60.0
    seed: int = 20261011


@dataclass(frozen=True)
class QualityJob:
    path: str
    recording: Recording
    settings: QualitySettings
    channel_map: Mapping[str, str] = field(default_factory=dict)
    stream: bool = True
    sample: bool = True
    sidecar_positions: Mapping[str, Position] = field(default_factory=dict)  # electrodes.tsv (A-60)
    sidecar_reason: str | None = None  # why an existing electrodes.tsv is not used


@dataclass(frozen=True)
class QualityResult:
    line_frequency_hz: float
    line_frequency_source: str  # config | sidecar | header | default
    stream: StreamResult | None = None
    sample: SampleResult | None = None
    reason: str | None = None  # set when nothing could be measured
    error_type: str | None = None


@dataclass(frozen=True)
class Part:
    """What one part of a job gave: a value, or the reason (and exception type) why the recording cannot be
    measured at all."""

    value: Any = None
    reason: str | None = None
    error_type: str | None = None


def line_frequency(recording: Recording) -> tuple[float, str]:
    value = recording.line_frequency_hz
    if value is not None and math.isfinite(value) and value > 0:
        return float(value), recording.metadata_sources.get("line_frequency_hz", "header")
    return DEFAULT_LINE_HZ, "default"


def _with_source(job: QualityJob, work: Callable[[Any, float], Any]) -> Part:
    """``work(source, line_hz)`` on the opened recording; any reader error becomes read.failed: the recording
    is reported, the run is never aborted (A-60)."""
    from threadpoolctl import threadpool_limits

    from neurogrid.quality.source import open_signals

    line_hz, _source_name = line_frequency(job.recording)
    try:
        source = open_signals(Path(job.path), job.recording)
    except Exception as exc:
        return Part(reason="read.failed", error_type=type(exc).__name__)
    try:
        if not source.channels:
            return Part(reason="signal.no_eeg_channels")
        with threadpool_limits(limits=1):
            return Part(value=work(source, line_hz))
    except Exception as exc:  # e.g. a damaged block in the middle of a file
        return Part(reason="read.failed", error_type=type(exc).__name__)
    finally:
        source.close()


def stream_part(job: QualityJob) -> Part:
    settings = job.settings
    return _with_source(
        job,
        lambda source, line_hz: measure_stream(
            source,
            line_hz,
            flat_tolerance_uv=settings.flat_tolerance_uv,
            plateau_samples=settings.plateau_samples,
        ),
    )


def sample_part(job: QualityJob) -> Part:
    """The sample up to M06 (a Stage); autoreject and ICA follow on its good channels."""
    settings = job.settings
    return _with_source(
        job,
        lambda source, line_hz: prepare_sample(
            source,
            line_hz,
            mode=settings.mode,
            segments=settings.segments,
            segment_s=settings.segment_s,
            seed=settings.seed,
            min_seconds=settings.min_seconds,
            min_channels=settings.min_channels,
            channel_map=job.channel_map,
            sidecar=job.sidecar_positions,
            sidecar_reason=job.sidecar_reason,
        ),
    )


def _combined(
    job: QualityJob,
    stream: Part | None,
    sample: Part | None,
    m09a: MethodResult | None = None,
    m09b: MethodResult | None = None,
) -> QualityResult:
    """The fixed rules that put the parts of a job together, the same for every number of processes: the
    first part (stream before sample) that could not read the recording decides; otherwise both values."""
    line_hz, source_name = line_frequency(job.recording)
    for part in (stream, sample):
        if part is not None and part.reason:
            return QualityResult(line_hz, source_name, reason=part.reason, error_type=part.error_type)
    sample_result: SampleResult | None = None
    if sample is not None:
        stage: Stage = sample.value
        if stage.good is None:
            sample_result = stage.head
        else:
            assert m09a is not None and m09b is not None
            sample_result = finish_sample(stage, m09a, m09b)
    return QualityResult(
        line_hz, source_name, stream=stream.value if stream is not None else None, sample=sample_result
    )


def compute(job: QualityJob) -> QualityResult:
    """All parts of one job in this process (``--jobs 1``)."""
    stream = stream_part(job) if job.stream else None
    if stream is not None and stream.reason:
        return _combined(job, stream, None)
    sample = sample_part(job) if job.sample else None
    if sample is not None and not sample.reason and sample.value.good is not None:
        stage = sample.value
        return _combined(job, stream, sample, run_autoreject(stage), run_iclabel(stage))
    return _combined(job, stream, sample)


def autoreject_part(stage: Stage, n_jobs: int) -> tuple[MethodResult, bool]:
    """M09a as a task of the pool, and whether a loky process died during it (the fit ran again in the
    pool process: the same value, A-89)."""
    before = refits()
    value = run_autoreject(stage, n_jobs)
    return value, refits() != before


def _worker_start() -> None:
    worker_start()


def _pool(size: int) -> ProcessPoolExecutor:
    """A pool of ``size`` processes that start on the null device and run ``_worker_start`` first."""
    return ProcessPoolExecutor(max_workers=size, initializer=_worker_start, mp_context=pool_context())


def _isolated(job: QualityJob) -> QualityResult:
    """One job in a pool of its own; a worker that dies (e.g. out of memory) only fails this recording."""
    try:
        with _pool(1) as pool:
            return pool.submit(compute, job).result()
    except BrokenProcessPool:
        line_hz, source_name = line_frequency(job.recording)
        return QualityResult(
            line_hz, source_name, reason="quality.worker_failed", error_type=BrokenProcessPool.__name__
        )


@dataclass
class _Progress:
    """The parts of one job that have arrived."""

    stream: Part | None = None
    sample: Part | None = None
    m09a: MethodResult | None = None
    m09b: MethodResult | None = None
    broken: bool = False

    def complete(self, job: QualityJob) -> bool:
        if job.stream and self.stream is None:
            return False
        if self.stream is not None and self.stream.reason:
            return True  # the stream decides (_combined), whatever the sample gives
        if not job.sample:
            return True
        if self.sample is None:
            return False
        if self.sample.reason or self.sample.value.good is None:
            return True
        return self.m09a is not None and self.m09b is not None


def compute_all(
    jobs: Sequence[QualityJob], workers: int = 1, on_recompute: Callable[[int], None] | None = None
) -> list[QualityResult]:
    """Results in the order of ``jobs``, equal to ``[compute(job) for job in jobs]``. ``workers`` > 1 runs the
    parts of the jobs as tasks of a process pool (KONZEPT 1.4, D-14); at most ``workers`` recordings are in
    work at a time, which bounds the memory for prepared samples. If a worker dies, the jobs it took down are
    run again one at a time, so a crash costs only its own recording. Nothing of a dead process reaches the
    console (A-89); instead ``on_recompute`` is called once, before those runs, with the number of
    recordings whose work goes on without it: a process of the pool or one of autoreject's loky processes
    died (or a part could not be delivered). Their values do not change, unless a recording's own process
    dies too (quality.worker_failed)."""
    if workers <= 1:
        return [compute(job) for job in jobs]
    size = min(workers, MAX_WORKERS, TASKS_PER_JOB * max(1, len(jobs)))
    # a single recording: autoreject's threshold search may use all processes but its own (the stream ends
    # early, the ICA is short); with several recordings the pool is busy with them
    ar_jobs = max(1, min(workers, MAX_WORKERS) - 1) if len(jobs) == 1 else 1
    results: list[QualityResult | None] = [None] * len(jobs)
    progress: dict[int, _Progress] = {}
    futures: dict[Future[Any], tuple[int, str, int]] = {}
    order = 0
    waiting = list(range(len(jobs)))[::-1]  # next job at the end
    pool_broken = False  # after a dead worker the pool takes no more work: the rest runs one job at a time
    refitted: set[int] = set()  # recordings whose autoreject fit ran again after a loky process died
    with _pool(size) as pool:

        def submit(index: int, kind: str, fn: Callable[..., Any], *args: Any) -> None:
            nonlocal order, pool_broken
            try:
                futures[pool.submit(fn, *args)] = (index, kind, order)
            except BrokenProcessPool:
                progress[index].broken = pool_broken = True
            except Exception:  # the job runs again on its own
                progress[index].broken = True
            order += 1

        def start(index: int) -> None:
            job = jobs[index]
            progress[index] = _Progress()
            if job.stream:
                submit(index, "stream", stream_part, job)
            if job.sample:
                submit(index, "sample", sample_part, job)

        def finish(index: int) -> None:
            state = progress.pop(index)
            if not state.broken:
                results[index] = _combined(jobs[index], state.stream, state.sample, state.m09a, state.m09b)

        def refill() -> None:
            while waiting and len(progress) < size and not pool_broken:
                index = waiting.pop()
                start(index)
                if not jobs[index].stream and not jobs[index].sample:
                    finish(index)

        refill()
        while futures:
            done, _pending = wait(list(futures), return_when=FIRST_COMPLETED)
            for future in sorted(done, key=lambda f: futures[f][2]):  # submission order: a fixed sequence
                index, kind, _order = futures.pop(future)
                state = progress[index]
                try:
                    value = future.result()
                except BrokenProcessPool:
                    state.broken = pool_broken = True
                    continue
                except Exception:  # e.g. the prepared sample could not be pickled (MemoryError): run it alone
                    state.broken = True
                    continue
                if kind == "stream":
                    state.stream = value
                elif kind == "sample":
                    state.sample = value
                    stage = value.value
                    stream_failed = state.stream is not None and state.stream.reason is not None
                    if not value.reason and stage.good is not None and not state.broken and not stream_failed:
                        submit(index, "m09a", autoreject_part, stage, ar_jobs)
                        submit(index, "m09b", run_iclabel, stage)
                        # only the head is needed here; the pool still holds the prepared sample with its two
                        # tasks until they end, so at most ``size`` prepared samples are in memory
                        state.sample = Part(value=replace(stage, good=_SENT))
                elif kind == "m09a":
                    state.m09a, refitted_here = value
                    if refitted_here:
                        refitted.add(index)
                else:
                    state.m09b = value
            busy = {entry[0] for entry in futures.values()}
            for index in sorted(progress):
                state = progress[index]
                if index not in busy and (state.broken or state.complete(jobs[index])):
                    finish(index)
            refill()
    again = refitted | {index for index, result in enumerate(results) if result is None}
    if again and on_recompute is not None:
        on_recompute(len(again))
    return [
        result if result is not None else _isolated(job) for job, result in zip(jobs, results, strict=True)
    ]


__all__ = [
    "DEFAULT_LINE_HZ",
    "MAX_WORKERS",
    "Part",
    "QualityJob",
    "QualityResult",
    "QualitySettings",
    "autoreject_part",
    "compute",
    "compute_all",
    "describe",
    "finite_values",
    "line_frequency",
    "sample_part",
    "stream_part",
]


def finite_values(value: Any) -> Any:
    """``value`` with every non-finite float replaced by None (A-61, A-75): metric values reach results.json
    without the rule engine, which handles non-finite measurements itself."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: finite_values(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [finite_values(item) for item in value]
    return value


def describe(result: QualityResult) -> dict[str, Any]:
    """Metric values of one recording for results.json (NG-F07: every value per recording)."""
    out: dict[str, Any] = {}
    if result.reason:
        out["state"] = "not_checkable"
        out["reason"] = result.reason
        return out
    if result.stream is not None:
        stream = result.stream
        out["M07"] = {
            "line_frequency_hz": result.line_frequency_hz,
            "line_frequency_source": result.line_frequency_source,
            "other_frequency_hz": stream.other_frequency_hz,
            "channels": {
                ch.name: (
                    {"ratio": ch.line_ratio, "other_ratio": ch.other_ratio}
                    if ch.line_state == "measured"
                    else {"state": ch.line_state, "reason": ch.line_reason}
                )
                for ch in stream.channels
            },
        }
        out["M08"] = {
            "window_s": 1.0,
            "clipping_method": stream.clipping_method,
            "channels": {
                ch.name: {
                    "windows": ch.windows,
                    "flat_fraction": ch.flat.windows / ch.windows if ch.windows else None,
                    "clipped_fraction": ch.clipped.windows / ch.windows if ch.windows else None,
                }
                for ch in stream.channels
            },
        }
        out["data_seconds"] = round(stream.data_seconds, 6)
    if result.sample is not None:
        sample = result.sample
        for key, method in (("M06", sample.m06), ("M09a", sample.m09a), ("M09b", sample.m09b)):
            entry: dict[str, Any] = {"state": method.state}
            if method.value is not None:
                entry["value"] = method.value
            if method.reason:
                entry["reason"] = method.reason
            entry.update(method.details)
            out[key] = entry
    return out
