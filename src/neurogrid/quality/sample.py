"""M06 and M09 on a deterministic sample (D-04, A-19, A-60, A-79).

- **Selection:** ``segments`` × ``segment_s`` (default 10 × 60 s), each centred in one of ``segments`` equal
  parts of the recording; a recording up to ``segments × segment_s`` is used whole; ``mode = "full"`` uses the
  whole recording. Start times are given in recording time (EDF+D included).
- **Preparation:** every EEG channel is resampled to 250 Hz (polyphase), the segments are joined with
  boundaries that the filters respect, then a notch filter at the line frequency and its harmonic below
  125 Hz and a 1–100 Hz band-pass. Positions: electrodes.tsv > file > template montage of the standard names
  > none (A-60, details in ``neurogrid.quality.positions``); with positions for only part of the channels (at
  least ``min_channels``), only those channels are analysed and the others are listed.
- **M06:** share of bad EEG channels found by pyprep ``NoisyChannels``. RANSAC runs only with positions and
  when pyprep's own preconditions hold (at least 14 usable channels and enough left after the other criteria);
  otherwise it is skipped and the details say so. If M06 fails, the bad channels are unknown, and M09a/M09b
  (which need the average reference without them) are not_checkable.
- **M09a:** share of rejected 2-s epochs from local autoreject (``cv = 10``, ``n_interpolate = [1, 4, 32]``,
  values not below the number of channels dropped). autoreject needs positions (also without interpolation).
- **M09b:** share of ICA components (picard extended, 20 components or fewer, decim 4) whose most probable
  ICLabel class is not "brain"; also given without "other". Needs positions.
- **Preconditions (A-60, A-79):** at least ``min_seconds`` of data, a rate of at least 200 Hz (the 1–100 Hz
  band) and at least ``min_channels`` EEG channels for all three; M09b also after removing the bad channels.
- All methods run after an average reference without the bad channels, with one BLAS thread and the seed of
  the run (pyprep, autoreject and picard take NumPy seeds below 2^32: they get the seed modulo 2^32); a
  failing method or preparation gives not_checkable with the exception's class name, never exit 2 (A-60).
"""

from __future__ import annotations

import os
import warnings
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from fractions import Fraction
from typing import Any

import numpy as np

from neurogrid.quality.positions import Position, choose, template_positions
from neurogrid.quality.source import SignalSource

TARGET_HZ = 250.0
BAND_HZ = (1.0, 100.0)
EPOCH_S = 2.0
MIN_RATE_HZ = 2 * BAND_HZ[1]  # the 1–100 Hz band of A-19 needs a Nyquist frequency of at least 100 Hz
RANSAC_SAMPLE_PROP = 0.25  # pyprep's default share of channels that predicts each channel
AUTOREJECT_INTERPOLATE = (1, 4, 32)
AUTOREJECT_CV = 10
# below this many channels starting loky workers costs more than the parallel threshold search saves (D-14)
AUTOREJECT_PARALLEL_MIN_CHANNELS = 64
ICA_COMPONENTS = 20
ICA_DECIM = 4


@dataclass(frozen=True)
class MethodResult:
    state: str  # measured | not_checkable
    value: float | None = None
    reason: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SampleResult:
    mode: str
    segments: tuple[tuple[float, float], ...]  # (start in recording time, length) in seconds
    seed: int
    channels: int  # EEG channels analysed
    positions: str  # montage source: sidecar | header | standard_montage | none
    notch_hz: tuple[float, ...]
    m06: MethodResult
    m09a: MethodResult
    m09b: MethodResult
    excluded: tuple[str, ...] = ()  # EEG channels without a position from that source, left out
    positions_unused: Mapping[str, str] = field(default_factory=dict)  # source -> why it was not used

    def describe(self) -> dict[str, Any]:
        """The sample as it is reported (results.json and report, KONZEPT 1.5)."""
        return {
            "mode": self.mode,
            "segments": [{"start_s": start, "duration_s": length} for start, length in self.segments],
            "seed": self.seed,
            "channels": self.channels,
            "excluded_channels": list(self.excluded),
            "positions": self.positions,
            "positions_unused": dict(self.positions_unused),
            "resample_hz": TARGET_HZ,
            "band_hz": list(BAND_HZ),
            "notch_hz": list(self.notch_hz),
            "epoch_s": EPOCH_S,
        }


def library_seed(seed: int) -> int:
    """The seed for pyprep, autoreject and picard, whose RandomState takes 0 … 2^32 − 1 (A-75 allows more)."""
    return seed % 2**32


def _not_checkable(reason: str, **details: Any) -> MethodResult:
    return MethodResult(state="not_checkable", reason=reason, details=details)


def select_segments(
    data_seconds: float, mode: str, segments: int, segment_s: float
) -> list[tuple[float, float]]:
    """(start, length) in data time; see the module docstring."""
    if mode == "full" or data_seconds <= segments * segment_s:
        return [(0.0, data_seconds)]
    part = data_seconds / segments
    return [((index + 0.5) * part - segment_s / 2, segment_s) for index in range(segments)]


def _resampled(values: np.ndarray, rate: float) -> np.ndarray:
    from scipy.signal import resample_poly

    ratio = Fraction(TARGET_HZ / rate).limit_denominator(1000)
    if ratio == 1:
        return values
    return np.asarray(resample_poly(values, ratio.numerator, ratio.denominator, axis=-1))


def _quiet() -> None:
    import mne

    os.environ["MNE_TQDM"] = "off"  # pyprep's RANSAC progress bar must not reach the console
    mne.set_log_level("ERROR")
    warnings.simplefilter("ignore")


@dataclass(frozen=True)
class Stage:
    """The sample after its preparation and M06. Either it ended early (``good`` is None: ``head`` is the
    whole result), or ``good`` holds the good channels with the average reference, ready for autoreject and
    ICA. Picklable, so that the two methods can run in other processes (``--jobs``)."""

    head: SampleResult  # m09a/m09b are placeholders while ``good`` is set
    good: Any = None
    positions: bool = False
    rng_seed: int = 0
    min_channels: int = 16


_PENDING = MethodResult(state="pending")


def measure_sample(
    source: SignalSource,
    line_hz: float,
    *,
    mode: str,
    segments: int,
    segment_s: float,
    seed: int,
    min_seconds: float,
    min_channels: int,
    channel_map: Mapping[str, str],
    sidecar: Mapping[str, Position] | None = None,
    sidecar_reason: str | None = None,
) -> SampleResult:
    """The whole sample in this process (``--jobs 1``); the same steps as prepare_sample, run_autoreject,
    run_iclabel and finish_sample, which ``--jobs N`` spreads over processes."""
    stage = prepare_sample(
        source,
        line_hz,
        mode=mode,
        segments=segments,
        segment_s=segment_s,
        seed=seed,
        min_seconds=min_seconds,
        min_channels=min_channels,
        channel_map=channel_map,
        sidecar=sidecar,
        sidecar_reason=sidecar_reason,
    )
    if stage.good is None:
        return stage.head
    return finish_sample(stage, run_autoreject(stage), run_iclabel(stage))


def finish_sample(stage: Stage, m09a: MethodResult, m09b: MethodResult) -> SampleResult:
    return replace(stage.head, m09a=m09a, m09b=m09b)


def run_autoreject(stage: Stage, n_jobs: int = 1) -> MethodResult:
    """M09a on a prepared sample; never raises (A-60). ``n_jobs`` > 1 spreads autoreject's threshold search
    over processes when the sample has enough channels for that to pay off; the result does not depend on
    it."""
    from threadpoolctl import threadpool_limits

    try:
        _quiet()
        jobs = n_jobs if len(stage.good.ch_names) >= AUTOREJECT_PARALLEL_MIN_CHANNELS else 1
        with threadpool_limits(limits=1):
            return _autoreject(stage.good, stage.positions, stage.rng_seed, jobs)
    except Exception as exc:  # e.g. MemoryError outside autoreject's own steps: the stream values remain
        return _failed(exc)


def run_iclabel(stage: Stage) -> MethodResult:
    """M09b on a prepared sample; never raises (A-60)."""
    from threadpoolctl import threadpool_limits

    try:
        _quiet()
        with threadpool_limits(limits=1):
            return _iclabel(stage.good, stage.positions, stage.rng_seed, stage.min_channels)
    except Exception as exc:
        return _failed(exc)


def prepare_sample(
    source: SignalSource,
    line_hz: float,
    *,
    mode: str,
    segments: int,
    segment_s: float,
    seed: int,
    min_seconds: float,
    min_channels: int,
    channel_map: Mapping[str, str],
    sidecar: Mapping[str, Position] | None = None,
    sidecar_reason: str | None = None,
) -> Stage:
    from threadpoolctl import threadpool_limits

    channels = source.channels
    data_seconds = min((c.n_samples / c.rate_hz for c in channels), default=0.0)
    chosen = select_segments(data_seconds, mode, segments, segment_s) if channels else []
    notch = tuple(f for f in (line_hz, 2 * line_hz) if f < TARGET_HZ / 2)
    shown = (
        tuple(
            (round(float(source.time_s(0, round(start * channels[0].rate_hz))), 6), round(float(length), 6))
            for start, length in chosen
        )
        if channels
        else ()
    )

    sidecar_unused = {"sidecar": sidecar_reason} if sidecar_reason else {}

    def result(
        m06: MethodResult,
        m09a: MethodResult,
        m09b: MethodResult,
        positions: str = "none",
        analysed: int | None = None,
        excluded: tuple[str, ...] = (),
        unused: Mapping[str, str] | None = None,
    ) -> Stage:
        return Stage(
            head=SampleResult(
                mode=mode,
                segments=shown,
                seed=seed,
                channels=len(channels) if analysed is None else analysed,
                positions=positions,
                notch_hz=notch,
                m06=m06,
                m09a=m09a,
                m09b=m09b,
                excluded=excluded,
                positions_unused=dict(sidecar_unused if unused is None else unused),
            )
        )

    if not channels:
        missing = _not_checkable("signal.no_eeg_channels")
        return result(missing, missing, missing)
    if data_seconds < min_seconds:
        short = _not_checkable("quality.too_short", seconds=round(data_seconds, 3), min_seconds=min_seconds)
        return result(short, short, short)
    slow = min(c.rate_hz for c in channels)
    if slow < MIN_RATE_HZ:
        low = _not_checkable("quality.rate_too_low", rate_hz=slow, min_rate_hz=MIN_RATE_HZ)
        return result(low, low, low)
    if len(channels) < min_channels:
        few = _not_checkable("quality.too_few_channels", channels=len(channels), min_channels=min_channels)
        return result(few, few, few)
    _quiet()
    names = [c.name for c in channels]
    # e.g. external electrodes (BioSemi EXG) next to a 10-20 cap: only the channels with positions (A-79)
    choice = choose(
        names,
        [
            ("sidecar", sidecar or {}),
            ("header", source.positions()),
            ("standard_montage", template_positions(names, channel_map)),
        ],
        min_channels,
    )
    analysed = set(choice.analysed)
    indices = [index for index, name in enumerate(names) if name in analysed]
    positions = choice.source != "none"
    report = (choice.source, len(indices), choice.excluded, sidecar_unused)
    rng_seed = library_seed(seed)
    with threadpool_limits(limits=1):
        try:
            raw = _prepared(source, chosen, indices, choice.positions if positions else None, notch)
        except Exception as exc:  # e.g. a damaged block in a sampled segment; the stream values remain
            failed = _failed(exc)
            return result(failed, failed, failed, *report)
        m06, bads = _bad_channels(raw, positions, rng_seed)
        if bads is None:  # the average reference without the bad channels is not possible (A-19)
            unknown = _not_checkable("quality.bad_channels_unknown")
            return result(m06, unknown, unknown, *report)
        good_names = [n for n in raw.ch_names if n not in bads]
        if len(good_names) < 2:
            few = _not_checkable("quality.too_few_channels", channels=len(good_names), min_channels=2)
            return result(m06, few, few, *report)
        try:
            raw.info["bads"] = list(bads)
            raw.set_eeg_reference("average", verbose="error")
            good = raw.copy().pick(good_names)
        except Exception as exc:
            failed = _failed(exc)
            return result(m06, failed, failed, *report)
    head = result(m06, _PENDING, _PENDING, *report).head
    return Stage(head=head, good=good, positions=positions, rng_seed=rng_seed, min_channels=min_channels)


def _prepared(
    source: SignalSource,
    chosen: list[tuple[float, float]],
    indices: list[int],
    positions: Mapping[str, Position] | None,
    notch: tuple[float, ...],
) -> Any:
    import mne

    names = [source.channels[i].name for i in indices]
    groups: dict[float, list[int]] = {}  # rate -> positions in ``indices``; one read per group and segment
    for position, index in enumerate(indices):
        groups.setdefault(source.channels[index].rate_hz, []).append(position)
    parts = []
    for start, length in chosen:
        rows: list[np.ndarray] = [np.zeros(0)] * len(indices)
        for rate, members in sorted(groups.items()):
            first = round(start * rate)
            available = min(source.channels[indices[m]].n_samples for m in members)
            last = min(available, first + round(length * rate))
            block = _resampled(source.read_many([indices[m] for m in members], first, last), rate)
            for member, row in zip(members, block, strict=True):
                rows[member] = row
        size = min(len(row) for row in rows)
        data = np.vstack([row[:size] for row in rows]) * 1e-6  # MNE works in volts
        parts.append(mne.io.RawArray(data, mne.create_info(names, TARGET_HZ, "eeg"), verbose="error"))
    raw = mne.concatenate_raws(parts, verbose="error") if len(parts) > 1 else parts[0]
    if positions is not None:
        ch_pos = {name: np.asarray(value, dtype=np.float64) for name, value in positions.items()}
        montage = mne.channels.make_dig_montage(ch_pos=ch_pos, coord_frame="head")
        raw.set_montage(montage, verbose="error")
    if notch:
        raw.notch_filter(list(notch), verbose="error")
    raw.filter(BAND_HZ[0], BAND_HZ[1], verbose="error")
    return raw


def _failed(exc: BaseException) -> MethodResult:
    return _not_checkable("quality.method_failed", error_type=type(exc).__name__)


def _ransac_possible(noisy: Any) -> bool:
    """pyprep's preconditions of RANSAC (``pyprep.ransac.find_bad_by_ransac``): a 25 % sample of the usable
    channels must hold more than 3 channels, and more than that must be left after the other criteria."""
    usable = [str(name) for name in noisy.ch_names_new]
    predictors = int(np.around(RANSAC_SAMPLE_PROP * len(usable)))
    excluded = {
        str(name) for name in noisy.bad_by_correlation + noisy.bad_by_deviation + noisy.bad_by_dropout
    }
    good = sum(1 for name in usable if name not in excluded)
    return predictors > 3 and good >= predictors + 1


def _bad_channels(raw: Any, positions: bool, seed: int) -> tuple[MethodResult, list[str] | None]:
    """M06 and the bad channels; None when they could not be determined. The criteria run in the order of
    pyprep's ``find_all_bads``, RANSAC last."""
    from pyprep.find_noisy_channels import NoisyChannels

    try:
        noisy = NoisyChannels(raw.copy(), do_detrend=False, random_state=seed, ransac=False)
        noisy.find_all_bads(ransac=False)
        ransac = positions and _ransac_possible(noisy)
        if ransac:
            noisy.find_bad_by_ransac()
        bads = sorted(str(name) for name in noisy.get_bads())
    except Exception as exc:  # pyprep raises many types on degenerate data; the outcome counts
        return _failed(exc), None
    details: dict[str, Any] = {"bad_channels": bads, "channels": len(raw.ch_names), "ransac": ransac}
    if positions and not ransac:
        details["ransac_skipped"] = "too_few_channels"
    return MethodResult(state="measured", value=len(bads) / len(raw.ch_names), details=details), bads


def _autoreject(raw: Any, positions: bool, seed: int, n_jobs: int = 1) -> MethodResult:
    if not positions:
        return _not_checkable("quality.no_positions")
    import mne

    try:
        epochs = mne.make_fixed_length_epochs(raw, duration=EPOCH_S, preload=True, verbose="error")
        interpolate = [n for n in AUTOREJECT_INTERPOLATE if n < len(raw.ch_names)] or [1]
        folds = min(AUTOREJECT_CV, len(epochs))
        if folds < 2:
            return _not_checkable("quality.too_short", epochs=len(epochs))
        model = _fitted_autoreject(epochs, interpolate, folds, seed, n_jobs)
        bad = np.asarray(model.get_reject_log(epochs).bad_epochs, dtype=bool)
    except Exception as exc:  # autoreject raises many types on degenerate data; the outcome counts
        return _failed(exc)
    return MethodResult(
        state="measured",
        value=float(bad.mean()) if len(bad) else 0.0,
        details={
            "epochs": int(len(bad)),
            "rejected": int(bad.sum()),
            "n_interpolate": interpolate,
            "cv": folds,
        },
    )


def _fitted_autoreject(epochs: Any, interpolate: list[int], folds: int, seed: int, n_jobs: int) -> Any:
    """autoreject fitted with ``n_jobs`` loky processes; if one of them dies (e.g. out of memory), the same
    fit runs again in this process, which gives the same model (D-14: --jobs never changes a value)."""
    from autoreject import AutoReject

    def model(jobs: int) -> Any:
        return AutoReject(n_interpolate=interpolate, cv=folds, random_state=seed, n_jobs=jobs, verbose=False)

    if n_jobs > 1:
        from concurrent.futures.process import BrokenProcessPool

        from neurogrid.quality.workers import loky_processes

        try:
            with loky_processes():
                return model(n_jobs).fit(epochs)
        except BrokenProcessPool:  # loky's TerminatedWorkerError is one
            pass
    return model(1).fit(epochs)


def _iclabel(raw: Any, positions: bool, seed: int, min_channels: int) -> MethodResult:
    if not positions:
        return _not_checkable("quality.no_positions")
    if len(raw.ch_names) < min_channels:
        return _not_checkable(
            "quality.too_few_channels", channels=len(raw.ch_names), min_channels=min_channels
        )
    import mne
    import onnxruntime
    from mne_icalabel import label_components

    onnxruntime.disable_telemetry_events()  # ICLabel runs through onnxruntime; no telemetry (NG-N01, CON-04)
    try:
        components = min(ICA_COMPONENTS, len(raw.ch_names) - 1)
        ica = mne.preprocessing.ICA(
            n_components=components,
            method="picard",
            fit_params={"ortho": False, "extended": True},
            random_state=seed,
            max_iter="auto",
        )
        ica.fit(raw, decim=ICA_DECIM, verbose="error")
        labels = list(label_components(raw, ica, method="iclabel")["labels"])
    except Exception as exc:  # picard/ICLabel raise many types on degenerate data; the outcome counts
        return _failed(exc)
    count = len(labels)
    non_brain = sum(1 for label in labels if label != "brain")
    without_other = sum(1 for label in labels if label not in ("brain", "other"))
    return MethodResult(
        state="measured",
        value=non_brain / count if count else 0.0,
        details={
            "components": count,
            "non_brain": non_brain,
            "non_brain_without_other": without_other,
            "share_without_other": without_other / count if count else 0.0,
            "labels": {label: labels.count(label) for label in sorted(set(labels))},
        },
    )
