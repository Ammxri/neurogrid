"""M06–M09 signal quality checks (PRD §12; D-04, A-18, A-19, A-20, A-44, A-47, A-60, A-79).

The values come from one job per recording (``neurogrid.quality``): a streaming pass over the full length
for M07 and M08, a deterministic sample for M06 and M09. M07 and M08 are measured per EEG channel (subkey =
channel), M06 and M09 per recording. Thresholds of M06, M07 and M09 are calibrated (A-20, MET-01); M08 keeps
the PRD start value of 5 % of the duration.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from neurogrid.checks.context import CheckContext, RecordingState
from neurogrid.kernel.findings import TimeRange
from neurogrid.kernel.rules import CheckSpec, Evaluation, Measurement, ParamSpec, ParamValue, at_most
from neurogrid.quality.sample import MethodResult
from neurogrid.quality.stream import Ranges

BAD_CHANNELS = "quality.bad_channels"
LINE_NOISE = "quality.line_noise"
LINE_FREQUENCY = "quality.line_frequency"
FLATLINE = "quality.flatline"
CLIPPING = "quality.clipping"
AUTOREJECT = "quality.autoreject"
NON_BRAIN = "quality.non_brain_components"

STREAM_CHECKS = frozenset({LINE_NOISE, LINE_FREQUENCY, FLATLINE, CLIPPING})
SAMPLE_CHECKS = frozenset({BAD_CHANNELS, AUTOREJECT, NON_BRAIN})

# Start values of the calibrated thresholds: 95th percentile over the public corpus (A-20, MET-01). The rule
# pack carries the same values with their origin; tools/calibrate.py writes the protocol.
CALIBRATED = {
    "bad_channels": 0.30625,
    "line_noise": 0.407669,
    "autoreject": 0.305083,
    "non_brain": 0.6,
}


def _line_frequency_plausible(measurement: Measurement, params: Mapping[str, ParamValue]) -> Evaluation:
    """A-47: the other line frequency fits better if its median ratio is ``min_factor`` times higher."""
    value = measurement.value
    factor = params["min_factor"]
    return Evaluation(
        passed=not value["other_median"] > factor * value["documented_median"], threshold=factor
    )


SPECS = (
    CheckSpec(
        id=BAD_CHANNELS,
        evaluate=at_most("max_fraction"),
        params={"max_fraction": ParamSpec("number", CALIBRATED["bad_channels"])},
    ),
    CheckSpec(
        id=LINE_NOISE,
        evaluate=at_most("max_ratio"),
        params={"max_ratio": ParamSpec("number", CALIBRATED["line_noise"])},
    ),
    CheckSpec(
        id=LINE_FREQUENCY,
        evaluate=_line_frequency_plausible,
        params={"min_factor": ParamSpec("number", 2.0)},
    ),
    CheckSpec(
        id=FLATLINE, evaluate=at_most("max_fraction"), params={"max_fraction": ParamSpec("number", 0.05)}
    ),
    CheckSpec(
        id=CLIPPING, evaluate=at_most("max_fraction"), params={"max_fraction": ParamSpec("number", 0.05)}
    ),
    CheckSpec(
        id=AUTOREJECT,
        evaluate=at_most("max_fraction"),
        params={"max_fraction": ParamSpec("number", CALIBRATED["autoreject"])},
    ),
    CheckSpec(
        id=NON_BRAIN,
        evaluate=at_most("max_fraction"),
        params={"max_fraction": ParamSpec("number", CALIBRATED["non_brain"])},
    ),
)


def _base(rec: RecordingState, check_id: str, **kwargs: Any) -> Measurement:
    return Measurement(
        check_id=check_id, object=rec.object_id, file=rec.file, identity=rec.identity, **kwargs
    )


def _unavailable(rec: RecordingState, check_id: str) -> Measurement | None:
    """The recording-level reason why nothing can be measured, if any."""
    if rec.annotations_only:
        return _base(rec, check_id, state="not_applicable", reason="recording.annotations_only")
    if rec.recording is None:
        return _base(rec, check_id, state="not_checkable", reason="header.unreadable")
    result = rec.quality
    if result is None:
        return _base(rec, check_id, state="not_checkable", reason="quality.not_computed")
    if result.reason:
        details = {"error_type": result.error_type} if result.error_type else {}
        return _base(rec, check_id, state="not_checkable", reason=result.reason, details=details)
    return None


def _method(rec: RecordingState, check_id: str, method: MethodResult) -> Measurement:
    if method.state != "measured" or method.value is None:
        return _base(
            rec,
            check_id,
            state="not_checkable",
            reason=method.reason or "quality.method_failed",
            details=dict(method.details),
        )
    return _base(rec, check_id, value=method.value, details=dict(method.details))


def _sample_measurer(check_id: str, attribute: str) -> Any:
    def measure(ctx: CheckContext) -> list[Measurement]:
        out: list[Measurement] = []
        for rec in ctx.recordings:
            unavailable = _unavailable(rec, check_id)
            if unavailable is not None:
                out.append(unavailable)
                continue
            assert rec.quality is not None
            sample = rec.quality.sample
            if sample is None:
                out.append(_base(rec, check_id, state="not_checkable", reason="quality.not_computed"))
                continue
            out.append(_method(rec, check_id, getattr(sample, attribute)))
        return out

    return measure


def measure_line_noise(ctx: CheckContext) -> list[Measurement]:
    out: list[Measurement] = []
    for rec in ctx.recordings:
        unavailable = _unavailable(rec, LINE_NOISE)
        if unavailable is not None:
            out.append(unavailable)
            continue
        assert rec.quality is not None and rec.quality.stream is not None
        result = rec.quality
        stream = result.stream
        assert stream is not None
        details = {
            "line_frequency_hz": result.line_frequency_hz,
            "line_frequency_source": result.line_frequency_source,
        }
        for channel in stream.channels:
            if channel.line_state != "measured":
                out.append(
                    _base(
                        rec,
                        LINE_NOISE,
                        subkey=channel.name,
                        channel=channel.name,
                        state=channel.line_state,
                        reason=channel.line_reason,
                        details=details,
                    )
                )
            else:
                out.append(
                    _base(
                        rec,
                        LINE_NOISE,
                        subkey=channel.name,
                        channel=channel.name,
                        value=channel.line_ratio,
                        details=details,
                    )
                )
    return out


def measure_line_frequency(ctx: CheckContext) -> list[Measurement]:
    import statistics

    out: list[Measurement] = []
    for rec in ctx.recordings:
        unavailable = _unavailable(rec, LINE_FREQUENCY)
        if unavailable is not None:
            out.append(unavailable)
            continue
        assert rec.quality is not None and rec.quality.stream is not None
        stream = rec.quality.stream
        measured = [ch for ch in stream.channels if ch.line_state == "measured"]
        if not measured:  # the channels' common reason, e.g. too short for one Welch segment
            reasons = {ch.line_reason for ch in stream.channels}
            reason = reasons.pop() if len(reasons) == 1 else None
            state = "not_applicable" if reason == "quality.rate_below_line_band" else "not_checkable"
            out.append(_base(rec, LINE_FREQUENCY, state=state, reason=reason or "quality.no_signal_power"))
            continue
        if any(ch.other_ratio is None for ch in measured):  # the other line band is above Nyquist
            out.append(
                _base(rec, LINE_FREQUENCY, state="not_checkable", reason="quality.rate_below_other_band")
            )
            continue
        out.append(
            _base(
                rec,
                LINE_FREQUENCY,
                value={
                    "documented_hz": rec.quality.line_frequency_hz,
                    "documented_median": statistics.median(ch.line_ratio or 0.0 for ch in measured),
                    "other_hz": stream.other_frequency_hz,
                    "other_median": statistics.median(ch.other_ratio or 0.0 for ch in measured),
                },
                details={"line_frequency_source": rec.quality.line_frequency_source},
            )
        )
    return out


def _windows_measurer(check_id: str, attribute: str) -> Any:
    def measure(ctx: CheckContext) -> list[Measurement]:
        out: list[Measurement] = []
        for rec in ctx.recordings:
            unavailable = _unavailable(rec, check_id)
            if unavailable is not None:
                out.append(unavailable)
                continue
            assert rec.quality is not None and rec.quality.stream is not None
            stream = rec.quality.stream
            for channel in stream.channels:
                if not channel.windows:
                    out.append(
                        _base(
                            rec,
                            check_id,
                            subkey=channel.name,
                            channel=channel.name,
                            state="not_checkable",
                            reason=channel.windows_reason or "quality.too_short",
                        )
                    )
                    continue
                flagged: Ranges = getattr(channel, attribute)
                out.append(
                    _base(
                        rec,
                        check_id,
                        subkey=channel.name,
                        channel=channel.name,
                        value=flagged.windows / channel.windows,
                        time_ranges=tuple(TimeRange(start_s=a, end_s=b) for a, b in flagged.ranges),
                        time_ranges_total=flagged.total,
                        time_ranges_duration_s=round(flagged.seconds, 6) if flagged.windows else None,
                        details={
                            "windows": channel.windows,
                            "flagged_windows": flagged.windows,
                            "unusable_windows": channel.unusable_windows,
                            "method": stream.clipping_method if attribute == "clipped" else "peak_to_peak",
                        },
                    )
                )
        return out

    return measure


MEASURERS = {
    BAD_CHANNELS: _sample_measurer(BAD_CHANNELS, "m06"),
    LINE_NOISE: measure_line_noise,
    LINE_FREQUENCY: measure_line_frequency,
    FLATLINE: _windows_measurer(FLATLINE, "flat"),
    CLIPPING: _windows_measurer(CLIPPING, "clipped"),
    AUTOREJECT: _sample_measurer(AUTOREJECT, "m09a"),
    NON_BRAIN: _sample_measurer(NON_BRAIN, "m09b"),
}
