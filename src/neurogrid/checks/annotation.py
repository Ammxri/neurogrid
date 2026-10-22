"""M10 Annotation (PRD §12; NG-F08, A-17, A-80): agreement between annotators, codes, gaps and overlaps.

Objects are the signal recordings with the annotations attached to them, and annotation-only files that could
not be attached (CheckContext.annotations(), io/annotations.py). Only the annotators that take part count
(``[annotation] annotators``, compared with annotator IDs); the others are counted in the details. When the
patterns leave out every annotator, the findings say so (``annotation.all_excluded``).

Participants (A-80): an annotator takes part in κ, gaps and overlaps only with at least one annotation of
duration > 0 (a *scored* track). A track of zero-duration markers only counts for the codes and for
``[ai] labels = "annotations"``. An attached annotation-only file without any annotation is an annotator all
the same: it has coverage 0 in the gaps check, takes no part in κ and is listed in the summary.

- **κ** (``annotation.kappa``, CORE-M10-01): pairwise unweighted Cohen's κ on an epoch grid of ``epoch_s``
  (default 30 s continuous, 1 s events) from t = 0 to the end of the recording, complete epochs only (floor),
  each epoch labelled by the codes of the annotations with duration > 0 that cover its midpoint (several codes
  form one combined class, none is the class "no event"). Epochs whose midpoint lies in a record gap of an
  EDF+D file do not count. κ is computed exactly with fractions from integer counts, so it does not depend on
  the platform (A-11). The value is the mean of the pairwise κ (compared with ``min_kappa``, 0.6, PRD); the
  minimum, the number of pairs and the pairs are in the details. A pair whose expected agreement is 1 has no
  κ and is counted as undefined. One annotator: not_applicable. Limits (A-53): at most MAX_EPOCHS epochs and
  MAX_KAPPA_ANNOTATORS scored annotators (4950 pairs) per object, else not_checkable; κ is computed once per
  object and run (measure and summary share it), and only the MAX_PAIRS_LISTED lowest pairs are kept.
- **Codes** (``annotation.codes``, CORE-M10-02): one measurement per object and distinct code: in the
  vocabulary (``[annotation] vocabulary`` > events.json Levels of the code column), compared exactly; and one
  dataset-level measurement per label (events.json Levels description) that must not carry several codes.
  Zero-duration markers count here.
- **Gaps** (``annotation.gaps``, CORE-M10-03), continuous mode only: per object and annotator the parts of the
  scored range (the complete epochs, without EDF+D record gaps) that no annotation with duration > 0 covers;
  coverage is the covered share of the whole recording. A signal recording without any scored annotation
  fails with coverage 0 (A-80), and so does an attached annotation-only file without annotation.
- **Overlaps** (``annotation.overlaps``, CORE-M10-04): per object and annotator the maximal intervals covered
  by two or more annotations with duration > 0; in events mode only annotations with the same code count.
  Touching ends ([0, 30) and [30, 60)) do not overlap.

TIME_TOLERANCE_S (1 ms) is a numerical epsilon for interval ends (gaps and overlaps shorter than it are not
counted, intervals closer than it are joined), not a threshold (A-80, critic G13). Rules without anything to
judge in the whole dataset give one dataset-level measurement instead of one per recording (C11, A-59).
Annotation times are bounded when they are read (io.annotations.valid_times, A-53); the grid and the epoch
classes stay finite for any value all the same.

Display (A-17, A-51, C5): codes and labels appear only if io.identifying.display_text allows it (no name,
long number, absolute path, real date or clock time), otherwise as ``text-<sha8>`` with their length;
annotators always as ``ann-<sha8>`` subkeys, their clear ID only in the details and only in BIDS datasets
(through the same display rule) or with --show-paths. Subkeys do not depend on --show-paths (A-68).
"""

from __future__ import annotations

import bisect
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import PurePosixPath
from typing import Any

import numpy as np

from neurogrid.checks.context import CheckContext
from neurogrid.io.annotations import AnnotatedRecording, Track
from neurogrid.io.discover import _printable
from neurogrid.io.identifying import annotator_pseudonym, display_text
from neurogrid.kernel.findings import Notice, Severity, TimeRange
from neurogrid.kernel.rules import (
    CheckSpec,
    Evaluation,
    Measurement,
    ParamSpec,
    ParamValue,
    at_least,
    is_true,
)
from neurogrid.model.dataset import Annotation

KAPPA = "annotation.kappa"
CODES = "annotation.codes"
GAPS = "annotation.gaps"
OVERLAPS = "annotation.overlaps"
CHECKS = frozenset({KAPPA, CODES, GAPS, OVERLAPS})
TIME_TOLERANCE_S = 0.001
DEFAULT_EPOCH_S = {"continuous": 30.0, "events": 1.0}
MAX_TIME_RANGES = 20  # A-10
MAX_PAIRS_LISTED = 100
MAX_CODES_LISTED = 20
MAX_EPOCHS = 5_000_000  # A-53: epochs per object compared for kappa (58 days of 1-s epochs)
MAX_KAPPA_ANNOTATORS = 100  # A-53: scored annotators per object compared for kappa (4950 pairs)
DATASET = "dataset"
LABEL_PREFIX = "label:"
# every reason key the M10 measurements can carry (reason.<key> in the language tables; also built at runtime)
REASONS = (
    "annotation.none",
    "annotation.all_excluded",
    "annotation.markers_only",
    "annotation.too_many_annotators",
    "annotation.single_annotator",
    "annotation.event_mode",
    "annotation.no_vocabulary",
    "annotation.too_short",
    "annotation.kappa_undefined",
    "annotation.unreadable",
    "annotation.too_many",
    "annotation.epoched",
    "annotation.duration_unknown",
    "annotation.too_many_epochs",
    "header.unreadable",
)
NOTICES = (
    "notice.annotations_unassigned",
    "notice.annotations_ambiguous",
    "notice.annotation_files_unmatched",
    "notice.events_rows_invalid",
)
Interval = tuple[float, float]


def _no_gaps(measurement: Measurement, params: Mapping[str, ParamValue]) -> Evaluation:
    return Evaluation(passed=measurement.value["gaps"] == 0)


def _no_overlaps(measurement: Measurement, params: Mapping[str, ParamValue]) -> Evaluation:
    return Evaluation(passed=measurement.value["overlaps"] == 0)


SPECS = (
    CheckSpec(id=KAPPA, evaluate=at_least("min_kappa"), params={"min_kappa": ParamSpec("number", 0.6)}),
    CheckSpec(id=CODES, evaluate=is_true),
    CheckSpec(id=GAPS, evaluate=_no_gaps),
    CheckSpec(id=OVERLAPS, evaluate=_no_overlaps),
)


# --- settings and grid --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Settings:
    continuous: bool
    epoch_s: float
    vocabulary: tuple[str, ...] | None  # from neurogrid.toml; wins over events.json Levels

    @property
    def mode(self) -> str:
        return "continuous" if self.continuous else "events"


def settings(ctx: CheckContext) -> Settings:
    section = ctx.config.annotation
    vocabulary = tuple(sorted({code.strip() for code in section.vocabulary})) if section.vocabulary else None
    epoch = section.epoch_s if section.epoch_s is not None else DEFAULT_EPOCH_S[section.mode]
    return Settings(continuous=section.mode == "continuous", epoch_s=float(epoch), vocabulary=vocabulary)


@dataclass(frozen=True)
class Grid:
    """The epoch grid of one object: ``duration_s`` is the recording's (or the latest annotation end when the
    recording has none), ``data`` the parts with data (EDF+D records, else the whole recording)."""

    duration_s: float
    epoch_s: float
    epochs: int
    data: tuple[Interval, ...]

    @property
    def scored(self) -> tuple[Interval, ...]:
        """The complete epochs, without record gaps."""
        end = self.epochs * self.epoch_s
        return tuple((start, min(stop, end)) for start, stop in self.data if start < end)

    def counted(self, epoch: int) -> bool:
        """True if the midpoint of the epoch lies in data (``data`` is sorted and disjoint)."""
        middle = (epoch + 0.5) * self.epoch_s
        index = bisect.bisect_right([start for start, _stop in self.data], middle) - 1
        return index >= 0 and middle < self.data[index][1]

    def counted_mask(self) -> np.ndarray:
        """``counted`` for every epoch at once."""
        middles = (np.arange(self.epochs) + 0.5) * self.epoch_s
        starts = np.array([start for start, _stop in self.data], dtype=float)
        stops = np.array([stop for _start, stop in self.data], dtype=float)
        index = np.searchsorted(starts, middles, side="right") - 1
        inside = index >= 0
        inside[inside] = middles[inside] < stops[index[inside]]
        return np.asarray(inside, dtype=bool)


def _positive(annotations: Iterable[Annotation]) -> list[Annotation]:
    return [a for a in annotations if a.duration_s > 0]


def _is_scored(track: Track) -> bool:
    return any(a.duration_s > 0 for a in track.annotations)


def scored_tracks(obj: AnnotatedRecording) -> tuple[Track, ...]:
    """The annotators that take part in κ and overlaps: at least one annotation with duration > 0 (A-80); a
    track of zero-duration markers only counts for the codes and the [ai] labels alone."""
    return tuple(track for track in obj.tracks if _is_scored(track))


def gap_tracks(obj: AnnotatedRecording) -> tuple[Track, ...]:
    """The annotators the gaps check judges: the scored tracks and the attached annotation-only files without
    any annotation (an annotator who scored nothing has coverage 0, A-80)."""
    return tuple(track for track in obj.tracks if not track.annotations or _is_scored(track))


def _nothing_scored(objects: Sequence[AnnotatedRecording]) -> str:
    """The reason when none of ``objects`` has a scored track: only markers, every annotator left out by the
    ``[annotation] annotators`` patterns, or no annotation at all."""
    if any(obj.annotations for obj in objects):
        return "annotation.markers_only"
    return _nothing_kept(objects)


def _nothing_kept(objects: Sequence[AnnotatedRecording]) -> str:
    """The reason when none of ``objects`` has an annotation of an annotator that takes part."""
    return "annotation.all_excluded" if any(obj.excluded_annotators for obj in objects) else "annotation.none"


def grid(obj: AnnotatedRecording, epoch_s: float) -> Grid | None:
    """None when the length is unknown: no recording duration and no annotation with an end. Times are bounded
    when they are read (A-53); a length or an epoch count that is not finite gives None as well (defence in
    depth: never an overflow)."""
    duration = obj.duration_s
    if duration is None:
        ends = [end for end in (a.onset_s + a.duration_s for a in obj.annotations) if math.isfinite(end)]
        duration = max(ends) if ends and max(ends) > 0 else None
    if duration is None or not math.isfinite(duration):
        return None
    ratio = (duration + TIME_TOLERANCE_S) / epoch_s
    if not math.isfinite(ratio):
        return None
    epochs = max(0, math.floor(ratio))
    data = obj.data_intervals or ((0.0, duration),)
    clipped = tuple((max(0.0, start), min(stop, duration)) for start, stop in data if stop > 0)
    return Grid(duration_s=duration, epoch_s=epoch_s, epochs=epochs, data=clipped)


# --- κ ------------------------------------------------------------------------------------------------------


def _epoch_at(time_s: float, frame: Grid) -> int:
    """The first epoch whose midpoint lies at or after ``time_s``: ceil(time / epoch_s - 0.5), limited to
    -1 … epochs (the same result inside the grid; a time far outside it, or a quotient that overflows for a
    tiny epoch_s, cannot reach math.ceil as an infinity)."""
    position = time_s / frame.epoch_s - 0.5
    return math.ceil(min(max(position, -1.0), float(frame.epochs)))


def epoch_classes(annotations: Iterable[Annotation], frame: Grid) -> list[tuple[str, ...]]:
    """The class of every epoch: the sorted codes of the annotations with duration > 0 that cover its midpoint
    (half-open intervals), () for "no event". A sweep over the epochs keeps the cost linear."""
    starts: dict[int, list[str]] = {}
    stops: dict[int, list[str]] = {}
    for annotation in _positive(annotations):
        end = annotation.onset_s + annotation.duration_s
        if not (math.isfinite(annotation.onset_s) and math.isfinite(end)):
            continue  # never read (A-53); kept out here as well, so math.ceil never sees an infinity
        first = max(0, _epoch_at(annotation.onset_s, frame))
        last = min(frame.epochs - 1, _epoch_at(end, frame) - 1)
        if first <= last:
            starts.setdefault(first, []).append(annotation.code)
            stops.setdefault(last + 1, []).append(annotation.code)
    active: dict[str, int] = {}
    current: tuple[str, ...] = ()
    classes: list[tuple[str, ...]] = []
    for epoch in range(frame.epochs):
        ending, beginning = stops.get(epoch, ()), starts.get(epoch, ())
        for code in ending:
            active[code] -= 1
        for code in beginning:
            active[code] = active.get(code, 0) + 1
        if ending or beginning:  # the class changes only where an annotation starts or ends
            current = tuple(sorted(code for code, count in active.items() if count > 0))
        classes.append(current)
    return classes


def cohen_kappa(first: Sequence[Any], second: Sequence[Any]) -> Fraction | None:
    """Unweighted Cohen's κ of two label sequences, exact; None when the expected agreement is 1 (or no
    labels): then κ is not defined."""
    if len(first) != len(second):
        return None
    labels: dict[Any, int] = {}
    codes = [
        np.array([labels.setdefault(x, len(labels)) for x in seq], dtype=np.int64) for seq in (first, second)
    ]
    classes = len(labels)
    return _kappa(codes[0], codes[1], _class_counts(codes[0], classes), _class_counts(codes[1], classes))


def _class_counts(sequence: np.ndarray, classes: int) -> np.ndarray:
    """How often each class number 0 … classes − 1 occurs, as Python integers (no overflow in products)."""
    return np.bincount(sequence, minlength=classes).astype(object)


def _kappa(
    first: np.ndarray, second: np.ndarray, counts_a: np.ndarray, counts_b: np.ndarray
) -> Fraction | None:
    """κ = (n·agree − Σ nₐ(c)·n_b(c)) / (n² − Σ nₐ(c)·n_b(c)) from integer counts (``_class_counts`` of
    both sequences over the same classes), so the value is exact and the same on every platform (A-11)."""
    n = len(first)
    if n == 0:
        return None
    agree = int(np.count_nonzero(first == second))
    expected = int(sum(counts_a * counts_b))
    denominator = n * n - expected
    if denominator == 0:
        return None
    return Fraction(n * agree - expected, denominator)


@dataclass(frozen=True)
class KappaResult:
    mean: float
    minimum: float
    # (annotator subkey, annotator subkey, κ), lowest first: the MAX_PAIRS_LISTED lowest pairs only
    pairs: tuple[tuple[str, str, float], ...]
    pair_count: int  # pairs with a κ
    annotators: int
    epochs: int
    undefined_pairs: int


def _sequence(classes: list[tuple[str, ...]], numbers: dict[tuple[str, ...], int]) -> np.ndarray:
    """Class numbers of the epochs in the smallest unsigned type that holds them (memory per annotator)."""
    sequence = np.array([numbers.setdefault(c, len(numbers)) for c in classes], dtype=np.int64)
    return sequence.astype(np.min_scalar_type(len(numbers)))


def kappa(obj: AnnotatedRecording, frame: Grid) -> KappaResult | None:
    """Pairwise κ of the scored annotators of ``obj``; None when no pair has a κ. The mean is exact over every
    pair (a running sum of fractions); only the MAX_PAIRS_LISTED lowest pairs are kept, so the memory does not
    grow with the number of pairs (A-53). The class counts of each annotator are taken once, not per pair."""
    counted = frame.counted_mask()
    numbers: dict[tuple[str, ...], int] = {}
    labels: list[tuple[str, np.ndarray]] = []
    for track in scored_tracks(obj):
        sequence = _sequence(epoch_classes(track.annotations, frame), numbers)
        labels.append((annotator_pseudonym(track.annotator), sequence[counted]))
    counts = [_class_counts(sequence, len(numbers)) for _name, sequence in labels]
    total, count, undefined = Fraction(0), 0, 0
    lowest: list[tuple[Fraction, str, str]] = []
    for index, (name_a, seq_a) in enumerate(labels):
        for other, (name_b, seq_b) in enumerate(labels[index + 1 :], start=index + 1):
            value = _kappa(seq_a, seq_b, counts[index], counts[other])
            if value is None:
                undefined += 1
                continue
            total += value
            count += 1
            low, high = sorted((name_a, name_b))
            lowest.append((value, low, high))
            if len(lowest) >= 2 * MAX_PAIRS_LISTED:
                lowest = sorted(lowest)[:MAX_PAIRS_LISTED]
    if not count:
        return None
    lowest = sorted(lowest)[:MAX_PAIRS_LISTED]
    return KappaResult(
        mean=float(total / count),
        minimum=float(lowest[0][0]),
        pairs=tuple((a, b, float(value)) for value, a, b in lowest),
        pair_count=count,
        annotators=len(labels),
        epochs=len(labels[0][1]),
        undefined_pairs=undefined,
    )


# --- intervals ----------------------------------------------------------------------------------------------


def _join(intervals: Iterable[Interval]) -> list[Interval]:
    joined: list[Interval] = []
    for start, stop in sorted(intervals):
        if joined and start <= joined[-1][1] + TIME_TOLERANCE_S:
            joined[-1] = (joined[-1][0], max(joined[-1][1], stop))
        else:
            joined.append((start, stop))
    return joined


def _length(intervals: Iterable[Interval]) -> float:
    return sum(stop - start for start, stop in intervals)


def _intersect(first: Sequence[Interval], second: Sequence[Interval]) -> list[Interval]:
    """The overlap of two sorted lists of disjoint intervals, in one pass over both."""
    out: list[Interval] = []
    i = j = 0
    while i < len(first) and j < len(second):
        begin, end = max(first[i][0], second[j][0]), min(first[i][1], second[j][1])
        if end > begin:
            out.append((begin, end))
        if first[i][1] < second[j][1]:
            i += 1
        else:
            j += 1
    return out


def gaps(annotations: Iterable[Annotation], frame: Grid) -> tuple[list[Interval], float]:
    """Uncovered parts of the scored range (at least TIME_TOLERANCE_S long) and the covered share of the
    recording's data."""
    covered = _join((a.onset_s, a.onset_s + a.duration_s) for a in _positive(annotations))
    missing: list[Interval] = []
    first = 0  # both lists are sorted: one pass over the covered intervals
    for low, high in frame.scored:
        while first < len(covered) and covered[first][1] <= low:
            first += 1
        cursor = low
        index = first
        while index < len(covered) and covered[index][0] < high:
            start, stop = covered[index]
            if start - cursor >= TIME_TOLERANCE_S:
                missing.append((cursor, start))
            cursor = max(cursor, stop)
            index += 1
        if high - cursor >= TIME_TOLERANCE_S:
            missing.append((cursor, high))
    total = _length(frame.data)
    coverage = _length(_intersect(covered, frame.data)) / total if total > 0 else 0.0
    return missing, min(1.0, coverage)


def overlaps(annotations: Iterable[Annotation], *, same_code: bool) -> list[Interval]:
    """Maximal intervals covered by at least two annotations with duration > 0 (at least TIME_TOLERANCE_S
    long); with ``same_code`` only annotations of one code are compared with each other."""
    groups: dict[str, list[Annotation]] = {}
    for annotation in _positive(annotations):
        groups.setdefault(annotation.code if same_code else "", []).append(annotation)
    found: list[Interval] = []
    for members in groups.values():
        points = sorted(
            [(a.onset_s, 1) for a in members] + [(a.onset_s + a.duration_s, -1) for a in members]
        )  # an end sorts before a start at the same time: touching intervals do not overlap
        depth, begin = 0, 0.0
        group: list[Interval] = []
        for time, step in points:
            if step > 0:
                depth += 1
                if depth == 2:
                    begin = time
            else:
                if depth == 2 and time - begin >= TIME_TOLERANCE_S:
                    group.append((begin, time))
                depth -= 1
        found.extend(_join(group))
    return sorted(found)


def _ranges(intervals: Sequence[Interval]) -> dict[str, Any]:
    return {
        "time_ranges": tuple(TimeRange(start_s=s, end_s=e) for s, e in intervals[:MAX_TIME_RANGES]),
        "time_ranges_total": len(intervals),
        "time_ranges_duration_s": _length(intervals),
    }


# --- measurements -------------------------------------------------------------------------------------------


def _base(obj: AnnotatedRecording, check_id: str, **kwargs: Any) -> Measurement:
    return Measurement(
        check_id=check_id,
        object=obj.found.display_id,
        file=obj.found.display_file,
        identity=obj.found.identity,
        **kwargs,
    )


def _dataset(check_id: str, reason: str) -> Measurement:
    return Measurement(check_id=check_id, object=DATASET, state="not_applicable", reason=reason)


def _not_checkable(obj: AnnotatedRecording, check_id: str, reason: str) -> Measurement:
    return _base(obj, check_id, state="not_checkable", reason=reason)


def _annotator_details(ctx: CheckContext, track: Track) -> dict[str, Any]:
    """The clear annotator ID: only with --show-paths, or in BIDS datasets if the display rule allows it."""
    if ctx.show_paths:
        return {"annotator": _printable(track.annotator)}
    if ctx.scan.is_bids:
        shown = display_text(track.annotator).shown
        return {"annotator": shown} if shown is not None else {}
    return {}


def _track_base(
    ctx: CheckContext, obj: AnnotatedRecording, track: Track, check_id: str, **kwargs: Any
) -> Measurement:
    details = {**_annotator_details(ctx, track), **kwargs.pop("details", {})}
    return Measurement(
        check_id=check_id,
        object=obj.found.display_id,
        file=track.file.display_file,
        identity=obj.found.identity,
        subkey=annotator_pseudonym(track.annotator),
        details=details,
        **kwargs,
    )


def cached_kappa(ctx: CheckContext, obj: AnnotatedRecording, frame: Grid) -> KappaResult | None:
    """κ of ``obj`` on ``frame``, computed once per object and run: the measurement and the summary of
    results.json share it (A-53). The frame is the same for both (one configuration per run)."""
    cache = ctx.annotation_kappa
    if obj.found.relative not in cache:
        cache[obj.found.relative] = kappa(obj, frame)
    result = cache[obj.found.relative]
    return result if isinstance(result, KappaResult) else None


def measure_kappa(ctx: CheckContext) -> list[Measurement]:
    config = settings(ctx)
    objects = ctx.annotations().objects
    out = [_not_checkable(obj, KAPPA, obj.issue) for obj in objects if obj.issue]
    readable = [obj for obj in objects if not obj.issue]
    if not any(len(scored_tracks(obj)) >= 2 for obj in readable):  # nothing to compare anywhere (C11)
        reason = (
            "annotation.single_annotator" if any(map(scored_tracks, readable)) else _nothing_scored(readable)
        )
        return [_dataset(KAPPA, reason), *out]
    for obj in readable:
        details = {"excluded_annotators": obj.excluded_annotators} if obj.excluded_annotators else {}
        frame = grid(obj, config.epoch_s)
        scored = scored_tracks(obj)
        if config.continuous and obj.epoched:
            out.append(_base(obj, KAPPA, state="not_applicable", reason="annotation.epoched"))
        elif not scored:
            reason = _nothing_scored([obj])
            out.append(_base(obj, KAPPA, state="not_applicable", reason=reason, details=details))
        elif len(scored) == 1:
            out.append(
                _base(
                    obj, KAPPA, state="not_applicable", reason="annotation.single_annotator", details=details
                )
            )
        elif len(scored) > MAX_KAPPA_ANNOTATORS:  # A-53: the pairs grow with the square of the annotators
            reason, counted = "annotation.too_many_annotators", {**details, "annotators": len(scored)}
            out.append(_base(obj, KAPPA, state="not_checkable", reason=reason, details=counted))
        elif frame is not None and frame.epochs > MAX_EPOCHS:
            out.append(_not_checkable(obj, KAPPA, "annotation.too_many_epochs"))
        elif frame is None or frame.epochs == 0 or not frame.counted_mask().any():
            out.append(_not_checkable(obj, KAPPA, "annotation.too_short"))
        else:
            result = cached_kappa(ctx, obj, frame)
            if result is None:
                out.append(_not_checkable(obj, KAPPA, "annotation.kappa_undefined"))
                continue
            out.append(_base(obj, KAPPA, value=result.mean, details={**details, **_kappa_details(result)}))
    return out


def _kappa_details(result: KappaResult) -> dict[str, Any]:
    return {
        "min": result.minimum,
        "pairs": result.pair_count,
        "annotators": result.annotators,
        "epochs": result.epochs,
        "undefined_pairs": result.undefined_pairs,
        "lowest_pair": [result.pairs[0][0], result.pairs[0][1]],
        "pair_values": [
            {"annotators": [a, b], "kappa": value} for a, b, value in result.pairs[:MAX_PAIRS_LISTED]
        ],
    }


def measure_codes(ctx: CheckContext) -> list[Measurement]:
    config = settings(ctx)
    objects = ctx.annotations().objects
    out = [_not_checkable(obj, CODES, obj.issue) for obj in objects if obj.issue]
    readable = [obj for obj in objects if not obj.issue]
    judged = [obj for obj in readable if obj.annotations and (config.vocabulary or obj.vocabulary)]
    labels = _label_measurements(readable)
    if not judged and not labels:  # nothing to compare anywhere (C11)
        has_codes = any(obj.annotations for obj in readable)
        reason = "annotation.no_vocabulary" if has_codes else _nothing_kept(readable)
        return [_dataset(CODES, reason), *out]
    for obj in readable:
        vocabulary = config.vocabulary or obj.vocabulary
        if not obj.annotations:  # markers count here (A-80); an empty track has no code
            out.append(_base(obj, CODES, state="not_applicable", reason=_nothing_kept([obj])))
        elif not vocabulary:
            out.append(_base(obj, CODES, state="not_applicable", reason="annotation.no_vocabulary"))
        else:
            out.extend(_code_measurements(obj, vocabulary))
    return out + labels


def _code_measurements(obj: AnnotatedRecording, vocabulary: Sequence[str]) -> list[Measurement]:
    known = set(vocabulary)
    occurrences: dict[str, list[Annotation]] = {}
    for annotation in obj.annotations:
        occurrences.setdefault(annotation.code, []).append(annotation)
    out = []
    for code in sorted(occurrences, key=lambda c: display_text(c, known).subkey):
        found = occurrences[code]
        shown = display_text(code, known)
        details: dict[str, Any] = {"count": len(found)}
        if shown.shown is None:
            details["chars"] = len(code)
        intervals = [(a.onset_s, a.onset_s + a.duration_s) for a in found]
        out.append(
            _base(obj, CODES, subkey=shown.subkey, value=code in known, details=details, **_ranges(intervals))
        )
    return out


def _label_measurements(objects: Sequence[AnnotatedRecording]) -> list[Measurement]:
    """One dataset-level measurement per label (events.json Levels description): it must not carry several
    codes (A-17, A-80); only codes that occur count."""
    codes_of: dict[str, set[str]] = {}
    for obj in objects:
        label_of = dict(obj.labels)
        for annotation in obj.annotations:
            label = label_of.get(annotation.code)
            if label:
                codes_of.setdefault(label, set()).add(annotation.code)
    out = []
    for label in sorted(codes_of, key=lambda text: display_text(text).subkey):
        shown = display_text(label)
        codes = sorted(display_text(code).subkey for code in codes_of[label])
        details: dict[str, Any] = {"n_codes": len(codes), "codes": codes[:MAX_CODES_LISTED]}
        if shown.shown is None:
            details["chars"] = len(label)
        out.append(
            Measurement(
                check_id=CODES,
                object=DATASET,
                subkey=LABEL_PREFIX + shown.subkey,
                value=len(codes) <= 1,
                details=details,
            )
        )
    return out


def _uncovered(obj: AnnotatedRecording, frame: Grid) -> Measurement:
    """A-80: a signal recording without any scored annotation in continuous mode is not covered at all (the
    details count the annotators the ``[annotation] annotators`` patterns left out)."""
    scored = list(frame.scored)
    value = {"gaps": len(scored), "gap_s": _length(scored), "coverage": 0.0}
    details = {"excluded_annotators": obj.excluded_annotators} if obj.excluded_annotators else {}
    return _base(obj, GAPS, value=value, details=details, **_ranges(scored))


def measure_gaps(ctx: CheckContext) -> list[Measurement]:
    config = settings(ctx)
    if not config.continuous:
        return [_dataset(GAPS, "annotation.event_mode")]
    out = []
    for obj in ctx.annotations().objects:
        frame = grid(obj, config.epoch_s)
        if obj.issue:
            out.append(_not_checkable(obj, GAPS, obj.issue))
        elif obj.epoched:
            out.append(_base(obj, GAPS, state="not_applicable", reason="annotation.epoched"))
        elif frame is None:
            out.append(_not_checkable(obj, GAPS, "annotation.duration_unknown"))
        elif frame.epochs == 0 or not frame.scored:
            out.append(_not_checkable(obj, GAPS, "annotation.too_short"))
        elif not gap_tracks(obj):  # no annotation, markers only, or every annotator left out
            out.append(_uncovered(obj, frame))
        else:
            for track in gap_tracks(obj):
                missing, coverage = gaps(track.annotations, frame)
                value = {"gaps": len(missing), "gap_s": _length(missing), "coverage": coverage}
                out.append(_track_base(ctx, obj, track, GAPS, value=value, **_ranges(missing)))
    return out


def measure_overlaps(ctx: CheckContext) -> list[Measurement]:
    config = settings(ctx)
    objects = ctx.annotations().objects
    out = [_not_checkable(obj, OVERLAPS, obj.issue) for obj in objects if obj.issue]
    readable = [obj for obj in objects if not obj.issue]
    if not any(map(scored_tracks, readable)):  # nothing to compare anywhere (C11)
        return [_dataset(OVERLAPS, _nothing_scored(readable)), *out]
    for obj in readable:
        if config.continuous and obj.epoched:
            out.append(_base(obj, OVERLAPS, state="not_applicable", reason="annotation.epoched"))
        elif not scored_tracks(obj):
            out.append(_base(obj, OVERLAPS, state="not_applicable", reason=_nothing_scored([obj])))
        else:
            for track in scored_tracks(obj):
                found = overlaps(track.annotations, same_code=not config.continuous)
                value = {"overlaps": len(found), "overlap_s": _length(found)}
                out.append(_track_base(ctx, obj, track, OVERLAPS, value=value, **_ranges(found)))
    return out


MEASURERS = {KAPPA: measure_kappa, CODES: measure_codes, GAPS: measure_gaps, OVERLAPS: measure_overlaps}


# --- results.json and notices -------------------------------------------------------------------------------


def summaries(ctx: CheckContext) -> dict[PurePosixPath, dict[str, Any]]:
    """The M10 summary per object for recordings[].metrics["annotation"] (critic X10): passed κ values are
    otherwise only counted (A-59). Empty when the annotations were not read (no M10 check ran, and no M11
    class balance with ``[ai] labels = "annotations"``, A-81); objects without any annotation source (no
    annotation, no attached or excluded file, nothing unreadable) get none, their findings say it (A-59).
    ``annotators`` lists every annotator that takes part (marker-only and empty tracks included); κ covers
    the scored ones, ``coverage`` the ones the gaps check judges."""
    if not ctx.annotations_read:
        return {}
    config = settings(ctx)
    out: dict[PurePosixPath, dict[str, Any]] = {}
    for obj in ctx.annotations().objects:
        if not (obj.tracks or obj.attached or obj.excluded_annotators or obj.invalid_rows) and (
            obj.issue is None or obj.issue == "header.unreadable"
        ):
            continue
        frame = grid(obj, config.epoch_s)
        entry: dict[str, Any] = {
            "mode": config.mode,
            "epoch_s": config.epoch_s,
            "annotations": len(obj.annotations),
            "annotators": [annotator_pseudonym(t.annotator) for t in obj.tracks],
            "excluded_annotators": obj.excluded_annotators,
            "sources": sorted({t.source for t in obj.tracks}),
            "files": [found.display_file for found in obj.attached],
            "epochs": (frame.epochs if frame.epochs <= MAX_EPOCHS else None) if frame else 0,
            "scored_s": _length(frame.scored) if frame else 0.0,
            "kappa": None,
        }
        if obj.issue:
            entry["issue"] = obj.issue
        if obj.unassigned:
            entry["unassigned"] = True
        if obj.invalid_rows:
            entry["invalid_rows"] = obj.invalid_rows
        usable = not obj.issue and frame is not None and frame.epochs > 0 and not obj.epoched
        comparable = 2 <= len(scored_tracks(obj)) <= MAX_KAPPA_ANNOTATORS
        if usable and frame is not None and comparable and frame.epochs <= MAX_EPOCHS:
            result = cached_kappa(ctx, obj, frame)
            if result is not None:
                entry["kappa"] = {
                    "mean": result.mean,
                    "min": result.minimum,
                    "pairs": result.pair_count,
                    "annotators": result.annotators,
                    "undefined_pairs": result.undefined_pairs,
                }
        if config.continuous and usable and frame is not None:
            entry["coverage"] = {
                annotator_pseudonym(t.annotator): gaps(t.annotations, frame)[1] for t in gap_tracks(obj)
            }
        out[obj.found.relative] = entry
    return out


def notices(ctx: CheckContext) -> list[Notice]:
    """Annotation-only files that could not be attached, [[annotation.files]] rows that matched nothing and
    events.tsv rows without a valid onset or duration (counts only, A-51)."""
    if not ctx.annotations_read:
        return []
    index = ctx.annotations()
    found = [
        (index.unassigned, Severity.INFO, "notice.annotations_unassigned"),
        (index.ambiguous, Severity.WARNING, "notice.annotations_ambiguous"),
        (index.unmatched_rows, Severity.WARNING, "notice.annotation_files_unmatched"),
        (index.invalid_rows, Severity.INFO, "notice.events_rows_invalid"),
    ]
    return [
        Notice(level=level, message_key=key, params={"count": count}) for count, level, key in found if count
    ]
