"""M03 Abtastrate (PRD §12): value per recording, uniformity across the dataset.

``signal.sampling_rate_consistency`` is the combined check named in the PRD rule-pack example (§11);
core uses the two parts separately so that each has its own finding.
"""

from __future__ import annotations

from collections.abc import Mapping

from neurogrid.checks.context import CheckContext, RecordingState
from neurogrid.kernel.rules import CheckSpec, Evaluation, Measurement, ParamSpec, ParamValue, at_least

RATE_MIN = "signal.sampling_rate_min"
RATE_UNIFORM = "signal.sampling_rate_uniform"
RATE_CONSISTENCY = "signal.sampling_rate_consistency"


def _uniform(measurement: Measurement, params: Mapping[str, ParamValue]) -> Evaluation:
    value = measurement.value
    return Evaluation(passed=len(value["rates_hz"]) <= 1 or bool(value["documented"]))


def _consistency(measurement: Measurement, params: Mapping[str, ParamValue]) -> Evaluation:
    value = measurement.value
    limit = params["min_hz"]
    ok_rate = value["rate_hz"] >= limit
    ok_uniform = value["uniform"] or value["documented"]
    return Evaluation(passed=bool(ok_rate and ok_uniform), threshold=limit)


SPECS = (
    CheckSpec(id=RATE_MIN, evaluate=at_least("min_hz"), params={"min_hz": ParamSpec("number", 500)}),
    CheckSpec(id=RATE_UNIFORM, evaluate=_uniform),
    CheckSpec(id=RATE_CONSISTENCY, evaluate=_consistency, params={"min_hz": ParamSpec("number", 500)}),
)


def _eeg_rates(rec: RecordingState) -> list[float]:
    if rec.recording is None:
        return []
    return sorted({ch.sampling_rate_hz for ch in rec.recording.eeg_channels if ch.sampling_rate_hz})


def _not_checkable(check_id: str, rec: RecordingState) -> Measurement:
    if rec.recording is None:
        reason = "header.unreadable"
    elif rec.recording.eeg_channels:
        reason = "signal.rate_unknown"  # EEG channels exist, but the header gives no valid rate
    else:
        reason = "signal.no_eeg_channels"
    return Measurement(
        check_id=check_id,
        object=rec.object_id,
        file=rec.file,
        state="not_checkable",
        reason=reason,
        identity=rec.identity,
    )


def _dataset_rates(ctx: CheckContext) -> list[float]:
    rates: set[float] = set()
    for rec in ctx.recordings:
        rates.update(_eeg_rates(rec))
    return sorted(rates)


def _documented(ctx: CheckContext) -> bool:
    return bool((ctx.config.metadata.mixed_sampling_rates_reason or "").strip())


def measure_rate_min(ctx: CheckContext) -> list[Measurement]:
    out: list[Measurement] = []
    for rec in ctx.recordings:
        rates = _eeg_rates(rec)
        if not rates:
            out.append(_not_checkable(RATE_MIN, rec))
            continue
        out.append(
            Measurement(
                check_id=RATE_MIN,
                object=rec.object_id,
                file=rec.file,
                value=min(rates),
                identity=rec.identity,
            )
        )
    return out


def measure_rate_uniform(ctx: CheckContext) -> list[Measurement]:
    rates = _dataset_rates(ctx)
    if not rates:
        has_eeg = any(rec.recording is not None and rec.recording.eeg_channels for rec in ctx.recordings)
        return [
            Measurement(
                check_id=RATE_UNIFORM,
                object="dataset",
                state="not_checkable",
                reason="signal.rate_unknown" if has_eeg else "signal.no_eeg_channels",
            )
        ]
    return [
        Measurement(
            check_id=RATE_UNIFORM,
            object="dataset",
            value={"rates_hz": rates, "documented": _documented(ctx)},
        )
    ]


def measure_rate_consistency(ctx: CheckContext) -> list[Measurement]:
    uniform = len(_dataset_rates(ctx)) <= 1
    documented = _documented(ctx)
    out: list[Measurement] = []
    for rec in ctx.recordings:
        rates = _eeg_rates(rec)
        if not rates:
            out.append(_not_checkable(RATE_CONSISTENCY, rec))
            continue
        out.append(
            Measurement(
                check_id=RATE_CONSISTENCY,
                object=rec.object_id,
                file=rec.file,
                value={
                    "rate_hz": min(rates),
                    "uniform": uniform and len(rates) == 1,
                    "documented": documented,
                },
                identity=rec.identity,
            )
        )
    return out


MEASURERS = {
    RATE_MIN: measure_rate_min,
    RATE_UNIFORM: measure_rate_uniform,
    RATE_CONSISTENCY: measure_rate_consistency,
}
