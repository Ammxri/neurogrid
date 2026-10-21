"""Signal quality metrics M06–M09 (NG-F07, D-04, A-18, A-19, A-60, A-79).

Per recording one job: a streaming pass over the full length (M07, M08, signal hash) and a deterministic
sample (M06, M09). Jobs run in the calling process or, with ``--jobs N``, in a pool of N processes. Every
worker installs the network guard (A-49) and computes with one BLAS thread, so the results do not depend on
the number of jobs or on the BLAS threads of the environment (A-11, NG-N03). A job never raises: problems
become a reason key that the checks report as not_checkable.
"""

from __future__ import annotations

import math
import sys
from collections.abc import Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from neurogrid.model.dataset import Recording
from neurogrid.quality.positions import Position
from neurogrid.quality.sample import SampleResult, measure_sample
from neurogrid.quality.stream import StreamResult, measure_stream

DEFAULT_LINE_HZ = 50.0  # A-18: line frequency as documented, otherwise 50 Hz
# ProcessPoolExecutor refuses more than 61 workers on Windows (WaitForMultipleObjects); --jobs allows 64
MAX_WORKERS = 61 if sys.platform == "win32" else 64


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


def line_frequency(recording: Recording) -> tuple[float, str]:
    value = recording.line_frequency_hz
    if value is not None and math.isfinite(value) and value > 0:
        return float(value), recording.metadata_sources.get("line_frequency_hz", "header")
    return DEFAULT_LINE_HZ, "default"


def compute(job: QualityJob) -> QualityResult:
    from threadpoolctl import threadpool_limits

    from neurogrid.quality.source import open_signals

    line_hz, source_name = line_frequency(job.recording)
    try:
        source = open_signals(Path(job.path), job.recording)
    except Exception as exc:  # any reader error: the recording is reported, never the run aborted (A-60)
        return QualityResult(line_hz, source_name, reason="read.failed", error_type=type(exc).__name__)
    try:
        if not source.channels:
            return QualityResult(line_hz, source_name, reason="signal.no_eeg_channels")
        settings = job.settings
        with threadpool_limits(limits=1):
            stream = (
                measure_stream(
                    source,
                    line_hz,
                    flat_tolerance_uv=settings.flat_tolerance_uv,
                    plateau_samples=settings.plateau_samples,
                )
                if job.stream
                else None
            )
            sample = (
                measure_sample(
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
                )
                if job.sample
                else None
            )
        return QualityResult(line_hz, source_name, stream=stream, sample=sample)
    except Exception as exc:  # e.g. a damaged block in the middle of a file
        return QualityResult(line_hz, source_name, reason="read.failed", error_type=type(exc).__name__)
    finally:
        source.close()


def _worker_start() -> None:
    from threadpoolctl import threadpool_limits

    from neurogrid.kernel import netguard

    netguard.install()
    threadpool_limits(limits=1)


def _isolated(job: QualityJob) -> QualityResult:
    """One job in a pool of its own; a worker that dies (e.g. out of memory) only fails this recording."""
    try:
        with ProcessPoolExecutor(max_workers=1, initializer=_worker_start) as pool:
            return pool.submit(compute, job).result()
    except BrokenProcessPool:
        line_hz, source_name = line_frequency(job.recording)
        return QualityResult(
            line_hz, source_name, reason="quality.worker_failed", error_type=BrokenProcessPool.__name__
        )


def compute_all(jobs: Sequence[QualityJob], workers: int = 1) -> list[QualityResult]:
    """Results in the order of ``jobs``; ``workers`` > 1 uses a process pool (KONZEPT 1.4). If a worker dies,
    the jobs it took down are run again one at a time, so a crash costs only its own recording."""
    if workers <= 1 or len(jobs) <= 1:
        return [compute(job) for job in jobs]
    results: list[QualityResult | None] = [None] * len(jobs)
    size = min(workers, len(jobs), MAX_WORKERS)
    with ProcessPoolExecutor(max_workers=size, initializer=_worker_start) as pool:
        futures = [pool.submit(compute, job) for job in jobs]
        for index, future in enumerate(futures):
            try:
                results[index] = future.result()
            except BrokenProcessPool:
                continue
    return [
        result if result is not None else _isolated(job) for job, result in zip(jobs, results, strict=True)
    ]


__all__ = [
    "DEFAULT_LINE_HZ",
    "MAX_WORKERS",
    "QualityJob",
    "QualityResult",
    "QualitySettings",
    "compute",
    "compute_all",
    "describe",
    "finite_values",
    "line_frequency",
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
