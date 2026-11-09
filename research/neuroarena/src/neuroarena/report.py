"""The published results and the technical report of NeuroArena (NG-F17, NA-01, NA-05, DoD 2; A-107, F5f,
F8 A, F9 B; area D "notebook, report en/zh, figures").

``publish`` turns the run folders of the two final runs (the first is the reported run, the second its
repetition, DoD 1) into the committed folder ``results/`` (CC BY 4.0, F8 A); ``render`` writes the report in
English and Chinese from the files in ``results/`` only, so the report can always be rendered again from what
is committed. Every number of the report comes from these files; nothing is typed by hand.

Files of ``results/`` (UTF-8, LF; CSV as ``records``: header, comma, floats by ``repr``, empty = missing)::

    curve.csv                       the reported run's curve.csv (records.CURVE_COLUMNS)
    sessions.csv                    the reported run's sessions.csv (records.SESSION_COLUMNS)
    quality_summary.csv             per dataset and condition: recordings and sessions per level Q1-Q5 and
                                    without a level, the share of recordings at Q4 or worse, how often each
                                    rule was the worst rule and how often it was not measurable, and the
                                    median ratio of each rule (QUALITY_SUMMARY_COLUMNS)
    unmeasured.csv                  per dataset, condition, rule and NeuroGrid's reason: the number of
                                    recordings in which the rule was not measurable (UNMEASURED_COLUMNS)
    method.json                     what the method section states: run ids, mode, configuration, versions,
                                    lock hashes, NeuroGrid's version, call and settings, the thresholds, the
                                    quality level rule, the ladders, the decoders, the evaluation and the
                                    datasets
    run_compare.json                compare.compare_runs of the two runs, with their run ids (DoD 1)
    accuracy_over_quality.svg/.png  main figure (F5f A): accuracy over the session's quality level Q1-Q5
    accuracy_over_degradation.svg/.png  second figure (F5f B): accuracy over the degradation level 0-5 per
                                    kind

Published files hold no absolute path, no user or host name; publishing the same runs twice gives the same
bytes (figures with fixed metadata and ``svg.hashsalt``, Agg). A level without sessions has no point and no
row: it is reported as missing, never invented (DoD 2).

Command line::

    python -m neuroarena.report publish RUN_A RUN_B [--eegnet-tolerance] [--results DIR]
    python -m neuroarena.report render [--results DIR] [--report-en DIR] [--report-zh DIR]

RUN_A and RUN_B are run folders or run ids under .local/arena/runs. ``publish``: exit 0 when the files are
written and the runs are equal within the applied tolerance, 1 when they are written but the runs differ, 2 on
a usage error or an incomplete run. ``render``: exit 0 when both reports are written, 1 when they are written
but run_compare.json records different runs, 2 on a usage error or missing or invalid results.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import io
import json
import math
import statistics
import sys
import tomllib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from neuroarena import compare, degradation, determinism, export, keys, paths, quality, records
from neuroarena.datasets import DATASETS
from neuroarena.keys import CLEAN, KINDS, LEVELS, Condition

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

METHOD_VERSION = 1
QUALITY_SUMMARY_FILE = "quality_summary.csv"
UNMEASURED_FILE = "unmeasured.csv"
METHOD_FILE = "method.json"
QUALITY_FIGURE = "accuracy_over_quality"
DEGRADATION_FIGURE = "accuracy_over_degradation"
FIGURE_FORMATS = ("svg", "png")
REPORT_FILE = "report.md"
# The published files in the order of the module docstring (the figures with both formats).
PUBLISHED = (
    paths.CURVE_FILE,
    paths.SESSIONS_FILE,
    QUALITY_SUMMARY_FILE,
    UNMEASURED_FILE,
    METHOD_FILE,
    paths.RUN_COMPARE_FILE,
    *(f"{stem}.{suffix}" for stem in (QUALITY_FIGURE, DEGRADATION_FIGURE) for suffix in FIGURE_FORMATS),
)

RULE_IDS = tuple(rule.rule_id for rule in quality.RULES)
QUALITY_SUMMARY_COLUMNS = (
    "dataset",
    "condition",
    "kind",
    "level",
    "n_recordings",
    *(f"recordings_q{level}" for level in LEVELS),
    "recordings_without_level",
    "q4_or_worse_share",
    "n_sessions",
    *(f"sessions_q{level}" for level in LEVELS),
    "sessions_without_level",
    *(f"worst_{rule}" for rule in RULE_IDS),
    *(f"unmeasured_{rule}" for rule in RULE_IDS),
    *(f"median_ratio_{rule}" for rule in RULE_IDS),
)
UNMEASURED_COLUMNS = ("dataset", "condition", "rule_id", "reason", "recordings")

# The A-101 call as the method states it (the runner passes absolute paths of the run's own folders).
NEUROGRID_CALL = (
    "uv run --project <repo> --locked neurogrid check <folder> --config <toml> --show-paths --jobs N "
    "--out <file>"
)

# Figures: fixed metadata and hash salt (byte-stable files), the bundled DejaVu Sans (same glyphs everywhere),
# the first two slots of a colour-blind-checked categorical palette for the decoders (markers differ as well)
# and a one-hue ordinal ramp for the levels Q1-Q5.
FIGURE_DPI = 150
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
DECODER_STYLE = {"csp_lda": ("CSP+LDA", "#2a78d6", "o"), "eegnet": ("EEGNet", "#eb6834", "s")}
LEVEL_COLOURS = ("#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281")
NO_LEVEL_COLOUR = "#f0efec"
PARADIGM_LABELS = {"imagery": "motor imagery", "ssvep": "SSVEP"}
KIND_LABELS = {"line_noise": "line noise", "channels": "flat channels", "artifacts": "artefacts"}
# The dataset whose MOABB loader joins one block of trials per class, with the trial onsets a whole number
# of line periods apart and a zero gap between the blocks that is not: the line-noise sinusoid has one
# phase per class at the trial onsets (finding after the full runs, A-111).
PHASE_LOCKED_LINE_NOISE = "Cho2017"
FIGURE_RC = {
    "svg.hashsalt": "neuroarena",
    "svg.fonttype": "path",
    "font.family": "DejaVu Sans",
    "font.size": 8.0,
    "axes.titlesize": 9.0,
    "axes.edgecolor": AXIS,
    "axes.labelcolor": INK_SECONDARY,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "axes.grid.axis": "y",
    "axes.facecolor": SURFACE,
    "figure.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "grid.color": GRID,
    "grid.linewidth": 0.6,
    "hatch.color": INK_MUTED,
    "hatch.linewidth": 0.6,
    "legend.frameon": False,
    "text.color": INK,
    "xtick.color": INK_SECONDARY,
    "ytick.color": INK_SECONDARY,
}
FIGURE_METADATA = {"svg": {"Date": None}, "png": {}}


@dataclass(frozen=True)
class Publication:
    """What ``publish`` wrote: the files (in PUBLISHED order) and the comparison of the two runs."""

    files: tuple[Path, ...]
    comparison: compare.Comparison


# --- publish -----------------------------------------------------------------------------------------------


def publish(
    runs: Sequence[Path],
    results: Path = paths.RESULTS,
    *,
    eegnet_tolerance: compare.EegnetTolerance | None = None,
) -> Publication:
    """Write the files of the module docstring into ``results`` from the run folders ``runs`` (exactly two:
    the reported run, then its repetition); return what was written.

    ValueError when not exactly two runs are given, a run folder is incomplete (run.json, sessions.csv,
    curve.csv, a quality.json, results.json or neurogrid.toml missing; a file missing in one run only), the
    runs have different configurations, or the NeuroGrid settings differ between the conditions of a run.
    The files are written even when the runs differ in value; ``Publication.comparison.ok`` tells."""
    if len(runs) != 2:
        raise ValueError(
            f"publish needs exactly two runs (the reported run and its repetition), not {len(runs)}"
        )
    reported, repetition = (Path(run) for run in runs)
    document, other = _run_document(reported), _run_document(repetition)
    comparison = compare.compare_runs(reported, repetition, eegnet_tolerance)
    missing = [d for d in comparison.differences if d.what == "missing"]
    if missing:
        raise ValueError(
            f"the runs are incomplete: {missing[0].where} ({len(missing)} files or rows missing)"
        )
    comparison = dataclasses.replace(comparison, runs=(str(document["run_id"]), str(other["run_id"])))
    for name in (paths.SESSIONS_FILE, paths.CURVE_FILE):
        if not (reported / name).is_file():
            raise ValueError(f"run {document['run_id']!r} has no {name} (it is not complete)")
    sessions = records.read_sessions(reported / paths.SESSIONS_FILE)
    curve = records.read_curve(reported / paths.CURVE_FILE)
    config = document["config"]
    conditions = [Condition.from_id(c) for c in config["conditions"]]
    checks: dict[tuple[str, str], _Check] = {}
    for dataset in config["datasets"]:
        for condition in conditions:
            checks[dataset, condition.id] = _read_check(reported / "neurogrid" / dataset / condition.id)
    summary = quality_summary(checks, config["datasets"], conditions)
    reasons = unmeasured_reasons(checks)
    method = method_document(document, other, checks)

    results = Path(results)
    records.write_csv(curve, results / paths.CURVE_FILE)
    records.write_csv(sessions, results / paths.SESSIONS_FILE)
    written: dict[str, bytes] = {
        QUALITY_SUMMARY_FILE: _csv_bytes(QUALITY_SUMMARY_COLUMNS, summary),
        UNMEASURED_FILE: _csv_bytes(UNMEASURED_COLUMNS, reasons),
        METHOD_FILE: _json_bytes(method),
    }
    for name, data in written.items():
        records.write_atomic(results / name, data)
    compare.write_comparison(comparison, results / paths.RUN_COMPARE_FILE)
    chance = _mean_chance(sessions)
    datasets = list(config["datasets"])
    decoders = list(config["decoders"])
    paradigms = {name: method["datasets"][name]["paradigm"] for name in datasets}
    without = _sessions_without_level(sessions)
    kinds = [kind for kind in KINDS if any(c.kind == kind for c in conditions)] or list(KINDS)
    figures = {
        QUALITY_FIGURE: lambda: quality_figure(curve, chance, datasets, decoders, paradigms, without),
        DEGRADATION_FIGURE: lambda: degradation_figure(curve, summary, chance, datasets, decoders, kinds),
    }
    for stem, build in figures.items():
        for suffix, data in _figure_bytes(build).items():
            records.write_atomic(results / f"{stem}.{suffix}", data)
    return Publication(files=tuple(results / name for name in PUBLISHED), comparison=comparison)


@dataclass(frozen=True)
class _Check:
    """What publish reads of one NeuroGrid check (one dataset and condition of the reported run)."""

    quality: quality.ConditionQuality
    results: Mapping[str, Any]  # results.json
    index: Mapping[str, Any]  # recordings.json: file -> RecordingKey
    configuration: Mapping[str, Any]  # neurogrid.toml


def _read_check(folder: Path) -> _Check:
    for name in (paths.QUALITY_FILE, paths.RESULTS_FILE, paths.INDEX_FILE, paths.CONFIG_FILE):
        if not (folder / name).is_file():
            raise ValueError(f"{folder.parent.name}/{folder.name}: no {name} (the run is not complete)")
    return _Check(
        quality=quality.read_quality(folder / paths.QUALITY_FILE),
        results=json.loads((folder / paths.RESULTS_FILE).read_bytes().decode("utf-8")),
        index=export.read_index(folder / paths.INDEX_FILE),
        configuration=tomllib.loads((folder / paths.CONFIG_FILE).read_bytes().decode("utf-8")),
    )


def _run_document(folder: Path) -> dict[str, Any]:
    run_file = folder / paths.RUN_FILE
    if not run_file.is_file():
        raise ValueError(f"no {paths.RUN_FILE} in run folder {folder.name!r}")
    return json.loads(run_file.read_bytes().decode("utf-8"))


def quality_summary(
    checks: Mapping[tuple[str, str], _Check], datasets: Sequence[str], conditions: Sequence[Condition]
) -> list[dict[str, Any]]:
    """One row (QUALITY_SUMMARY_COLUMNS) per dataset and condition, sorted by dataset name and then in the
    order of ``conditions``. Shares and medians are empty where nothing is counted."""
    rows = []
    for dataset in sorted(datasets):
        for condition in conditions:
            assessed = checks[dataset, condition.id].quality
            recordings = list(assessed.recordings.values())
            sessions = list(assessed.sessions.values())
            row: dict[str, Any] = {
                "dataset": dataset,
                "condition": condition.id,
                "kind": condition.kind,
                "level": condition.level,
                "n_recordings": len(recordings),
            }
            for level in LEVELS:
                row[f"recordings_q{level}"] = sum(1 for r in recordings if r.level == level)
            row["recordings_without_level"] = sum(1 for r in recordings if r.level is None)
            worse = sum(1 for r in recordings if r.level is not None and r.level >= 4)
            row["q4_or_worse_share"] = worse / len(recordings) if recordings else None
            row["n_sessions"] = len(sessions)
            for level in LEVELS:
                row[f"sessions_q{level}"] = sum(1 for s in sessions if s.level == level)
            row["sessions_without_level"] = sum(1 for s in sessions if s.level is None)
            for rule in RULE_IDS:
                row[f"worst_{rule}"] = sum(1 for r in recordings if r.worst_rule == rule)
            for rule in RULE_IDS:
                row[f"unmeasured_{rule}"] = sum(1 for r in recordings if rule in r.unmeasured)
            for rule in RULE_IDS:
                ratios = [r.ratios[rule] for r in recordings if rule in r.ratios]
                row[f"median_ratio_{rule}"] = statistics.median(ratios) if ratios else None
            rows.append(row)
    return rows


def unmeasured_reasons(checks: Mapping[tuple[str, str], _Check]) -> list[dict[str, Any]]:
    """One row (UNMEASURED_COLUMNS) per dataset, condition, rule and reason: the recordings in which the
    rule was not measurable (``quality.measured_value`` is None), with NeuroGrid's reason key from
    results.json (``reason`` of the metric or of the recording; else its state, ``no_finite_channel`` for a
    per-channel metric without a finite channel, ``no_value`` or ``missing``). Sorted by dataset, condition,
    rule and reason."""
    counts: dict[tuple[str, str, str, str], int] = {}
    for (dataset, condition), check in checks.items():
        for entry in check.results.get("recordings", []):
            metrics = entry.get("metrics")
            for rule in quality.RULES:
                if quality.measured_value(metrics, rule) is None:
                    key = (dataset, condition, rule.rule_id, _reason(metrics, rule))
                    counts[key] = counts.get(key, 0) + 1
    return [
        {"dataset": d, "condition": c, "rule_id": r, "reason": why, "recordings": n}
        for (d, c, r, why), n in sorted(counts.items())
    ]


def _reason(metrics: Any, rule: quality.MetricSource) -> str:
    if not isinstance(metrics, Mapping):
        return "missing"
    if metrics.get("state") == "not_checkable":
        return str(metrics.get("reason") or "not_checkable")
    entry = metrics.get(rule.metric)
    if not isinstance(entry, Mapping):
        return "missing"
    if entry.get("state") in quality.UNMEASURED_STATES:
        return str(entry.get("reason") or entry["state"])
    return "no_finite_channel" if rule.per_channel else "no_value"


def method_document(
    document: Mapping[str, Any], other: Mapping[str, Any], checks: Mapping[tuple[str, str], _Check]
) -> dict[str, Any]:
    """method.json: everything the method section states, from the reported run's run.json (``document``),
    the repetition's run id, the NeuroGrid files of the reported run and NeuroArena's constants. No times, no
    paths, no machine name (the machine's system and architecture only)."""
    config = document["config"]
    tools = {_tool(check.results) for check in checks.values()}
    settings = {_json_text(_neurogrid_settings(check.results)) for check in checks.values()}
    thresholds = {_json_text(quality.thresholds(check.results)) for check in checks.values()}
    for what, values in (("version", tools), ("settings", settings), ("thresholds", thresholds)):
        if len(values) != 1:
            raise ValueError(f"NeuroGrid's {what} differ between the conditions of the run")
    configurations: dict[str, Any] = {}
    for (dataset, _condition), check in sorted(checks.items()):
        text = _json_text(check.configuration)
        if configurations.setdefault(dataset, text) != text:
            raise ValueError(f"the research configuration of {dataset} differs between conditions")
    datasets = {}
    for name in config["datasets"]:
        spec = DATASETS[name]
        entry = {field.name: _plain(getattr(spec, field.name)) for field in dataclasses.fields(spec)}
        entry["flattened_channels"] = [
            degradation.flattened_channel_count(spec.n_eeg_channels, level) for level in LEVELS
        ]
        datasets[name] = entry
    return {
        "version": METHOD_VERSION,
        "runs": [str(document["run_id"]), str(other["run_id"])],
        "mode": config["mode"],
        "config": {key: config[key] for key in ("datasets", "conditions", "decoders", "subjects")},
        "subjects": document["subjects"],
        "base_seed": document["base_seed"],
        "decoders": document["decoders"],
        "evaluation": document["evaluation"],
        "versions": document["versions"],
        "locks": document["locks"],
        "machine": {key: document.get("machine", {}).get(key) for key in ("system", "machine")},
        "pilot": document.get("pilot"),
        "worker_environment": dict(determinism.WORKER_ENVIRONMENT),
        "neurogrid": {
            "version": next(iter(tools)),
            "call": NEUROGRID_CALL,
            "fif_format": export.FIF_FORMAT,
            "settings": json.loads(next(iter(settings))),
            "configuration": {name: json.loads(text) for name, text in sorted(configurations.items())},
            "thresholds": json.loads(next(iter(thresholds))),
        },
        "quality": {
            "rules": [dataclasses.asdict(rule) for rule in quality.RULES],
            "boundaries": list(quality.BOUNDARIES),
            "levels": list(quality.LEVELS),
        },
        "degradation": _constants(degradation),
        "datasets": datasets,
    }


def _tool(results: Mapping[str, Any]) -> str:
    tool = results.get("tool") or {}
    return f"{tool.get('name')} {tool.get('version')}"


def _neurogrid_settings(results: Mapping[str, Any]) -> dict[str, Any]:
    """The settings of a check that are the same for every dataset: seed, sample, quality settings without
    ``min_channels`` (per dataset, see the configuration)."""
    config = results.get("config", {})
    effective = config.get("effective_settings", {})
    common = {k: v for k, v in effective.get("quality", {}).items() if k != "min_channels"}
    return {"seed": config.get("seed"), "sampling": config.get("sampling"), "quality": common}


def _constants(module: Any) -> dict[str, Any]:
    """The upper-case constants defined in ``module`` (lower-case names), tuples as lists; constants it
    imports from ``neuroarena.keys`` or ``decimal`` are left out."""
    import decimal

    return {
        name.lower(): _plain(value)
        for name, value in sorted(vars(module).items())
        if name.isupper()
        and not name.startswith("_")
        and isinstance(value, int | float | str | tuple)
        and not hasattr(keys, name)
        and not hasattr(decimal, name)
    }


def _plain(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


def _json_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _json_bytes(document: Any) -> bytes:
    return (
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
    ).encode()


def _csv_bytes(columns: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> bytes:
    """CSV as ``records`` writes it: header, LF, floats by repr, None as an empty field."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_cell(row[column]) for column in columns])
    return buffer.getvalue().encode("utf-8")


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        raise TypeError("no boolean columns")
    if isinstance(value, float):
        return repr(value)
    return str(value)


def _mean_chance(sessions: Sequence[records.SessionRecord]) -> dict[str, float]:
    """The mean chance level of every dataset over its session rows (every session counts equally often:
    once per condition and decoder)."""
    groups: dict[str, list[float]] = {}
    for row in sessions:
        groups.setdefault(row.dataset, []).append(row.chance)
    return {dataset: math.fsum(values) / len(values) for dataset, values in sorted(groups.items())}


def _sessions_without_level(sessions: Sequence[records.SessionRecord]) -> dict[tuple[str, str], int]:
    """(dataset, decoder) -> (session, condition) pairs without a quality level (the ``n_without_level`` of
    curve.csv, also where curve.csv has no row because no pair of that dataset and decoder has a level)."""
    counts: dict[tuple[str, str], int] = {}
    for row in sessions:
        key = (row.dataset, row.decoder)
        counts[key] = counts.get(key, 0) + (row.quality_level is None)
    return counts


# --- figures -----------------------------------------------------------------------------------------------


def _figure_bytes(build: Callable[[], Figure]) -> dict[str, bytes]:
    """The figure from ``build`` as SVG and PNG with fixed metadata (the rc settings of FIGURE_RC apply while
    it is built and saved)."""
    import matplotlib

    out = {}
    with matplotlib.rc_context(FIGURE_RC):
        figure = build()
        for suffix in FIGURE_FORMATS:
            buffer = io.BytesIO()
            figure.savefig(buffer, format=suffix, dpi=FIGURE_DPI, metadata=FIGURE_METADATA[suffix])
            out[suffix] = buffer.getvalue()
    return out


def quality_figure(
    curve: Sequence[records.CurvePoint],
    chance: Mapping[str, float],
    datasets: Sequence[str],
    decoders: Sequence[str],
    paradigms: Mapping[str, str],
    without: Mapping[tuple[str, str], int],
) -> Figure:
    """Main figure (F5f A): one panel per dataset, accuracy over the session's quality level Q1-Q5 for every
    decoder (mean and bootstrap interval), the dataset's mean chance level as a dashed line, the number of
    (session, condition) pairs per level above the panel and the pairs without a level under it."""
    from matplotlib.figure import Figure
    from matplotlib.ticker import PercentFormatter

    figure = Figure(figsize=(0.4 + 3.3 * len(datasets), 3.6), layout="constrained")
    axes = figure.subplots(1, len(datasets), sharey=True, squeeze=False)[0]
    for ax, dataset in zip(axes, datasets, strict=True):
        points = [p for p in curve if p.dataset == dataset and p.axis == "quality" and p.kind == "all"]
        _accuracy_panel(ax, points, decoders, LEVELS, chance.get(dataset))
        ax.set_xticks(LEVELS, [f"Q{level}" for level in LEVELS])
        ax.set_xlim(LEVELS[0] - 0.5, LEVELS[-1] + 0.5)
        paradigm = paradigms.get(dataset, "")
        ax.set_title(f"{dataset} ({PARADIGM_LABELS.get(paradigm, paradigm)})", color=INK)
        counts = [without.get((dataset, decoder), 0) for decoder in decoders]
        missing = str(counts[0]) if len(set(counts)) == 1 else "/".join(map(str, counts))
        ax.set_xlabel(f"session quality level (NeuroGrid)\npairs without a level: {missing}")
        if not points:
            ax.text(0.5, 0.5, "no session with a level", transform=ax.transAxes, ha="center", color=INK_MUTED)
    axes[0].set_ylabel("accuracy (5-fold, within session)")
    axes[0].yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    figure.legend(*_legend(axes[0], decoders), loc="outside upper center", ncols=len(decoders) + 1)
    return figure


def degradation_figure(
    curve: Sequence[records.CurvePoint],
    summary: Sequence[Mapping[str, Any]],
    chance: Mapping[str, float],
    datasets: Sequence[str],
    decoders: Sequence[str],
    kinds: Sequence[str],
) -> Figure:
    """Second figure (F5f B): per dataset (row) and kind (column), accuracy over the degradation level 0-5
    (clean at 0) for every decoder with the mean chance level, and under it the share of sessions per quality
    level Q1-Q5 and without a level at every degradation level (quality_summary.csv)."""
    from matplotlib.figure import Figure
    from matplotlib.patches import Patch
    from matplotlib.ticker import PercentFormatter

    xs = (0, *LEVELS)
    width = max(0.6 + 3.3 * len(kinds), 6.4)  # room for the legends when the run has a single kind
    figure = Figure(figsize=(width, 0.9 + 3.0 * len(datasets)), layout="constrained")
    grid = figure.add_gridspec(2 * len(datasets), len(kinds), height_ratios=[3, 1] * len(datasets))
    first: Axes | None = None
    for row, dataset in enumerate(datasets):
        for column, kind in enumerate(kinds):
            ax = figure.add_subplot(grid[2 * row, column], sharey=first)
            first = first or ax
            bars = figure.add_subplot(grid[2 * row + 1, column], sharex=ax)
            points = [p for p in curve if p.dataset == dataset and p.axis == "degradation" and p.kind == kind]
            _accuracy_panel(ax, points, decoders, xs, chance.get(dataset))
            ax.set_title(f"{dataset} \N{MIDDLE DOT} {KIND_LABELS.get(kind, kind)}", color=INK)
            ax.tick_params(labelbottom=False)
            ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
            levels = {
                int(r["level"]): r
                for r in summary
                if r["dataset"] == dataset and (r["kind"] == kind or r["condition"] == CLEAN.id)
            }
            _level_bars(bars, levels)
            bars.set_xticks(xs)
            bars.set_xlim(xs[0] - 0.5, xs[-1] + 0.5)
            if column == 0:
                ax.set_ylabel("accuracy")
                bars.set_ylabel("levels")
            if row == len(datasets) - 1:
                bars.set_xlabel("degradation level (0 = clean)")
    assert first is not None
    figure.legend(*_legend(first, decoders), loc="outside upper center", ncols=len(decoders) + 1)
    patches = [
        Patch(facecolor=c, edgecolor=SURFACE, label=f"Q{q}")
        for q, c in zip(LEVELS, LEVEL_COLOURS, strict=True)
    ]
    patches.append(
        Patch(
            facecolor=NO_LEVEL_COLOUR,
            edgecolor=INK_MUTED,
            hatch="////",
            hatchcolor=INK_MUTED,
            label="no level",
        )
    )
    figure.legend(
        handles=patches,
        loc="outside lower center",
        ncols=len(patches) if len(kinds) > 1 else 3,
        title="sessions per quality level",
    )
    return figure


def _accuracy_panel(
    ax: Axes,
    points: Sequence[records.CurvePoint],
    decoders: Sequence[str],
    xs: Sequence[int],
    chance: float | None,
) -> None:
    """Mean accuracy (marker, line between neighbouring levels), its bootstrap interval (vertical bar), the
    number of pairs per level at the top (``n=12``, or ``n=12/11`` when the decoders differ) and the chance
    level. A missing level has no point."""
    nan = float("nan")
    width = 0.14
    by_decoder = {d: {p.x: p for p in points if p.decoder == d} for d in decoders}
    for index, decoder in enumerate(decoders):
        label, colour, marker = DECODER_STYLE.get(decoder, (decoder, INK_SECONDARY, "^"))
        offset = (index - (len(decoders) - 1) / 2) * width
        found = by_decoder[decoder]
        ys = [found[x].mean_accuracy if x in found else nan for x in xs]
        ax.plot(
            [x + offset for x in xs],
            ys,
            color=colour,
            marker=marker,
            markersize=5,
            linewidth=1.5,
            label=label,
        )
        for x, point in sorted(found.items()):
            if math.isfinite(point.ci_low) and math.isfinite(point.ci_high):
                ax.vlines(x + offset, point.ci_low, point.ci_high, colors=colour, linewidth=1.2)
    if chance is not None:
        ax.axhline(chance, color=INK_MUTED, linestyle=(0, (4, 3)), linewidth=1.0, label="chance level (mean)")
    for x in xs:
        counts = [by_decoder[d][x].n_sessions if x in by_decoder[d] else None for d in decoders]
        if all(count is None for count in counts):
            continue
        shown = set(counts)
        text = str(counts[0]) if len(shown) == 1 else "/".join("-" if c is None else str(c) for c in counts)
        ax.text(
            x,
            0.99,
            f"n={text}",
            transform=ax.get_xaxis_transform(),
            ha="center",
            va="top",
            fontsize=6.5,
            color=INK_SECONDARY,
        )
    ax.set_ylim(0.0, 1.15)
    ax.set_yticks([0.0, 0.25, 0.5, 0.75, 1.0])


def _level_bars(ax: Axes, rows: Mapping[int, Mapping[str, Any]]) -> None:
    """Stacked shares of the sessions per quality level (and without a level) at every degradation level."""
    for x, row in sorted(rows.items()):
        total = int(row["n_sessions"])
        if total == 0:
            continue
        bottom = 0.0
        parts = [
            (int(row[f"sessions_q{q}"]), colour, None)
            for q, colour in zip(LEVELS, LEVEL_COLOURS, strict=True)
        ]
        parts.append((int(row["sessions_without_level"]), NO_LEVEL_COLOUR, "////"))
        for count, colour, hatch in parts:
            if count:
                share = count / total
                ax.bar(
                    x,
                    share,
                    bottom=bottom,
                    width=0.6,
                    color=colour,
                    edgecolor=SURFACE,
                    linewidth=0.8,
                    hatch=hatch,
                    hatchcolor=INK_MUTED,
                )
                bottom += share
    ax.set_ylim(0.0, 1.0)
    ax.set_yticks([])
    ax.grid(False)


def _legend(ax: Axes, decoders: Sequence[str]) -> tuple[list[Any], list[str]]:
    handles, labels = ax.get_legend_handles_labels()
    order = [DECODER_STYLE.get(d, (d,))[0] for d in decoders] + ["chance level (mean)"]
    chosen = [(h, label) for name in order for h, label in zip(handles, labels, strict=True) if label == name]
    return [h for h, _ in chosen], [label for _, label in chosen]


# --- render ------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Results:
    """The files of ``results/`` as ``render`` reads them."""

    method: Mapping[str, Any]
    curve: tuple[records.CurvePoint, ...]
    sessions: tuple[records.SessionRecord, ...]
    summary: tuple[Mapping[str, str], ...]  # quality_summary.csv rows (text fields)
    unmeasured: tuple[Mapping[str, str], ...]  # unmeasured.csv rows (text fields)
    comparison: Mapping[str, Any]  # run_compare.json


def load_results(results: Path = paths.RESULTS) -> Results:
    """Read the files of ``results`` (ValueError for a missing file, a wrong header or an unknown version)."""
    results = Path(results)
    for name in PUBLISHED:
        if not (results / name).is_file():
            raise ValueError(f"results: {name} is missing (publish the runs first)")
    method = json.loads((results / METHOD_FILE).read_bytes().decode("utf-8"))
    if method.get("version") != METHOD_VERSION:
        raise ValueError(f"{METHOD_FILE}: unknown version {method.get('version')!r}")
    comparison = json.loads((results / paths.RUN_COMPARE_FILE).read_bytes().decode("utf-8"))
    if comparison.get("version") != compare.COMPARISON_VERSION:
        raise ValueError(f"{paths.RUN_COMPARE_FILE}: unknown version {comparison.get('version')!r}")
    return Results(
        method=method,
        curve=tuple(records.read_curve(results / paths.CURVE_FILE)),
        sessions=tuple(records.read_sessions(results / paths.SESSIONS_FILE)),
        summary=tuple(_read_table(results / QUALITY_SUMMARY_FILE, QUALITY_SUMMARY_COLUMNS)),
        unmeasured=tuple(_read_table(results / UNMEASURED_FILE, UNMEASURED_COLUMNS)),
        comparison=comparison,
    )


def _read_table(path: Path, columns: Sequence[str]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    if not rows or tuple(rows[0]) != tuple(columns):
        raise ValueError(f"{path.name}: the header is not {','.join(columns)}")
    if any(len(row) != len(columns) for row in rows[1:]):
        raise ValueError(f"{path.name}: a row has another number of fields than the header")
    return [dict(zip(columns, row, strict=True)) for row in rows[1:]]


def render(
    results: Path = paths.RESULTS, report_en: Path = paths.REPORT_EN, report_zh: Path = paths.REPORT_ZH
) -> tuple[Path, Path]:
    """Write ``report_en/report.md`` and ``report_zh/report.md`` from the files in ``results`` only (A-107
    sections; the figures are linked relative to each report); return both paths. ValueError when a file of
    ``results`` is missing or invalid."""
    data = load_results(results)
    written = []
    for language, folder in (("en", Path(report_en)), ("zh", Path(report_zh))):
        text = report_text(data, language, figure_links(Path(results), folder))
        written.append(records.write_atomic(folder / REPORT_FILE, text.encode("utf-8")))
    return written[0], written[1]


def figure_links(results: Path, folder: Path) -> dict[str, str]:
    """The figure files of ``results`` relative to the report folder ``folder`` (POSIX, never absolute)."""
    return {
        f"{stem}.{suffix}": _relative(results / f"{stem}.{suffix}", folder)
        for stem in (QUALITY_FIGURE, DEGRADATION_FIGURE)
        for suffix in FIGURE_FORMATS
    }


def _relative(target: Path, start: Path) -> str:
    """``target`` relative to the folder ``start`` as a POSIX path (never absolute)."""
    import os

    try:
        return Path(os.path.relpath(target.resolve(), start.resolve())).as_posix()
    except ValueError:
        raise ValueError(
            "the report and results/ must be on the same drive (relative figure links)"
        ) from None


DASH = "\N{EN DASH}"

TEXTS: dict[str, dict[str, Any]] = {
    "en": {
        "title": "# NeuroArena: decoder accuracy over the NeuroGrid quality level",
        "generated": (
            "<!-- Generated by `python -m neuroarena.report render` from results/; do not edit by hand. -->"
        ),
        "intro": (
            "Technical report of NeuroArena {version} (NG-F17): reported run `{run_a}`, its repetition "
            "`{run_b}`, mode `{mode}`. Every number below comes from the published files in `results/`."
        ),
        "mode_smoke": (
            "> **Mode smoke:** rendered from a short run on synthetic stand-ins of the datasets (no "
            "download, EEGNet with few epochs). Its numbers say nothing about the datasets."
        ),
        "mode_pilot": "> **Mode pilot:** rendered from the pilot run (A-109), not from a full run.",
        "h_goal": "## Goal",
        "goal": (
            "How does the accuracy of two standard decoders change with the NeuroGrid quality level of the "
            "data they are trained and tested on? NeuroArena checks every recording of {n_datasets} public "
            "MOABB datasets with NeuroGrid, gives every session a quality level {first}{dash}{last}, "
            "degrades the data in a controlled way in {n_levels} levels per kind ({kinds}) and evaluates "
            "CSP+LDA and EEGNet in every session under every condition (PRD section 16, NG-F17). The main "
            "result is the curve of the accuracy over the measured quality level (F5f A); the accuracy over "
            "the degradation level is the second view (F5f B)."
        ),
        "h_data": "## Data",
        "data_intro": (
            "The run used {n_datasets} public MOABB datasets as the loaders of moabb {moabb} return them "
            "(the loader's numbers count, not the documentation), with {subjects}. Sessions, recordings and "
            "trials per session of every dataset:"
        ),
        "subjects_all": "all subjects of every dataset (F2 A)",
        "subjects_subset": "a subset of the subjects approved by the owner ({subsets})",
        "data_header": [
            "Dataset",
            "Paradigm",
            "Classes",
            "Subjects",
            "Sessions",
            "Recordings",
            "EEG channels",
            "Sampling rate",
            "Line frequency",
            "Trials per session",
        ],
        "paradigms": {"imagery": "motor imagery", "ssvep": "SSVEP"},
        "h_attribution": "### Attribution",
        "attribution": [
            "- Citation: {citation}",
            "- Paper: [doi:{doi}](https://doi.org/{doi})",
            "- Source of the data: {source}",
            "- Downloaded from: {download}",
            "- Licence at the download source: {licence}. {note}",
        ],
        "attribution_note": (
            "The data were degraded in memory; NeuroGrid read them as temporary FIF files that were deleted "
            "after each condition. NeuroArena does not redistribute the data: this repository holds code, "
            "aggregated results, figures and this report, no recording."
        ),
        "h_method": "## Method",
        "h_neurogrid": "### NeuroGrid and the quality level (A-101, A-102)",
        "neurogrid_call": (
            "{tool} checked the recordings of every dataset and condition once, through the public command "
            "line of the main project (A-101); NeuroArena never imports NeuroGrid. The call, with the run's "
            "own folders in place of the placeholders:"
        ),
        "neurogrid_settings": (
            "The degraded recordings were written as temporary FIF files (MNE format `{fif}`). The core rule "
            "pack ran unchanged with its default thresholds and its sample ({segments} segments of "
            "{segment_s} s, seed {seed}; at least {min_seconds} s of data for M06 and M09); findings of "
            "other rules are not used. The research configuration sets only these values per dataset (F5d):"
        ),
        "config_header": ["Dataset", "`[quality] min_channels`", "`[metadata.defaults] line_frequency_hz`"],
        "level_rule": (
            "For every recording, r = value / effective threshold for each rule below, read from NeuroGrid's "
            "results.json; M07 and M08 per recording are the maximum over the channels with a finite value. "
            "A rule that is not measurable is left out and counted; CORE-M07-02 (plausibility of the line "
            "frequency) does not count. The largest ratio gives the level (A-102): {bounds}. A ratio at a "
            "boundary belongs to the higher level, so {threshold_level} starts at the threshold and {below} "
            "mean below every threshold. A recording without any measurable rule has no level; it is "
            "reported, never dropped. The level of a session is the worst level of its runs that have one."
        ),
        "thresholds_header": ["Rule", "Value per recording", "Effective threshold"],
        "rule_values": {
            "CORE-M06-01": "M06: share of bad EEG channels (pyprep) on NeuroGrid's sample",
            "CORE-M07-01": "M07: line-noise ratio, maximum over the channels",
            "CORE-M08-01": "M08: flat share of the duration, maximum over the channels",
            "CORE-M08-02": "M08: clipped share of the duration, maximum over the channels",
            "CORE-M09-01": "M09a: share of the epochs of the sample that local autoreject rejects",
            "CORE-M09-02": "M09b: share of ICA components whose most likely ICLabel class is not brain",
        },
        "h_degradation": "### Degradation (A-103, F4)",
        "degradation_intro": (
            "{n_conditions} conditions: the clean data and one ladder per kind with the levels "
            "{first}{dash}{last} (F4a A). The degradation acts on the raw signal (MNE Raw, volts) before "
            "filtering and epoching, on the EEG channels only, with a seed per recording, kind and level "
            "(SHA-256 of their names); montage, channel set, annotations and events stay. The level values "
            "were fixed before the first run and never adapted to results (F4c)."
        ),
        "line_noise": (
            "- **Line noise:** a sinusoid at the dataset's line frequency plus its first harmonic at "
            "{harmonic} of its amplitude (below the Nyquist frequency), with a random phase per channel; its "
            "power relative to the channel's power in {band} Hz is {db} dB for the levels "
            "{first}{dash}{last}."
        ),
        "channels": (
            "- **Flat channels:** k EEG channels of a recording are set to {flat} V, k = max(m, round(f "
            "\N{MIDDLE DOT} n)) with n the number of EEG channels, f = {fractions} and m = {minimums}: "
            "{per_dataset}."
        ),
        "artifacts": (
            "- **Artefacts:** {fractions} of the non-overlapping {epoch} s epochs of a recording receive one "
            "additive artefact each, the types in equal parts: eye blinks (Hann pulse of {blink_s} s, "
            "{blink_uv} \N{MICRO SIGN}V at the frontal pole, falling off towards the back of the head), "
            "muscle bursts ({muscle_s} s, {muscle_low} Hz up to {margin} Hz below the Nyquist frequency, RMS "
            "{muscle_uv} \N{MICRO SIGN}V at the most affected channel) and electrode pops (a step of "
            "{pop_uv} \N{MICRO SIGN}V on {pop_channels} channel, decaying with a time constant of {pop_s} s)."
        ),
        "h_decoders": "### Decoders (A-105, F7)",
        "csp": (
            "- **CSP+LDA** as the MOABB pipeline \N{LEFT DOUBLE QUOTATION MARK}CSP + "
            "LDA\N{RIGHT DOUBLE QUOTATION MARK}: covariance estimator `{cov}`, CSP with {filters} filters "
            "(log-variance), LDA (solver `{solver}`). Motor imagery: band-pass {mi_band} Hz. SSVEP: a filter "
            "bank with one band of \N{PLUS-MINUS SIGN}{half} Hz around every stimulus frequency, CSP per "
            "band and LDA on the features of all bands; this is NeuroArena's own construction from the same "
            "blocks and not a typical SSVEP decoder (F7)."
        ),
        "eegnet": (
            "- **EEGNet:** `{cls}` with its default architecture as a skorch classifier, band-pass {band} Hz "
            "and resampling to {rate} Hz; optimiser `{opt}`, learning rate {lr}, batch size {batch}, loss "
            "`{crit}`, at most {max_epochs} epochs ({mode_epochs} in this run), early stopping on "
            "`{monitor}` with patience {patience} on a stratified, seeded validation split of {share} of the "
            "training trials, keeping the weights of the best epoch; device `{device}`. No tuning on test "
            "data."
        ),
        "scale": (
            "- **Deviation from the reference example (input scale):** the training follows the EEGNet "
            "authors' reference example (arl-eegmodels, `examples/ERP.py`), which scales the input from "
            "volts to millivolts. With braindecode's batch normalisation, millivolt input made early "
            "stopping end the training before EEGNet had learned (measured before the full run), so "
            "NeuroArena multiplies the input by {scale} (volts to microvolts). The factor is a constant and "
            "is never fitted to the data."
        ),
        "h_evaluation": "### Evaluation (A-104, F6 A)",
        "evaluation": (
            "Training and test in the same condition: NeuroGrid checks training data, so the question is "
            "which accuracy data of a given quality level allow. {folds}-fold stratified cross-validation "
            "within every session (shuffled, seeded), as MOABB's within-session standard. The accuracy of a "
            "session is the number of correct test predictions over the number of test trials of all folds; "
            "its chance level is the share of its most frequent class. A point of a curve is the mean "
            "accuracy of the (session, condition) pairs in it with a {confidence} percentile bootstrap "
            "interval of the mean ({resamples} resamples, seeded): the main curve groups the pairs of all "
            "conditions by the session's quality level, the second groups them by the degradation level per "
            "kind, with the clean pairs at 0. Paired design: the folds of a session and the initial weights "
            "of EEGNet use the seed `{session_seed}`, the same in every condition and for both decoders, so "
            "a curve shows the change of the data, not of the split."
        ),
        "h_reproducibility": "### Reproducibility (A-106)",
        "reproducibility": (
            "Base seed {base_seed}; worker processes start with spawn and the environment {env}; torch runs "
            "with deterministic algorithms and one thread, on the CPU only. Equality of two runs is promised "
            "only per machine and lock; the two runs of this report ran on {system} {machine} with these "
            "locks (SHA-256): {locks}. Versions: {versions}."
        ),
        "h_results": "## Results",
        "overview_intro": (
            "Per dataset: sessions, conditions, (session, condition) pairs per decoder, pairs without a "
            "quality level and the mean chance level of the sessions:"
        ),
        "overview_header": [
            "Dataset",
            "Sessions",
            "Conditions",
            "Pairs per decoder",
            "Pairs without a level",
            "Mean chance level",
        ],
        "h_quality_curve": "### Accuracy over the quality level (main figure, F5f A)",
        "figure1_alt": "Figure 1: accuracy over the quality level",
        "figure1_caption": (
            "Figure 1. Accuracy over the session's quality level per dataset and decoder: mean of the "
            "(session, condition) pairs at that level with its {confidence} bootstrap interval; dashed line: "
            "mean chance level of the dataset; n: pairs per level (CSP+LDA/EEGNet where they differ); below "
            "each panel the pairs without a level. A level without pairs has no point. Also as [PNG]({png})."
        ),
        "cells_note": (
            "Cells: mean accuracy [bootstrap interval] (pairs); {dash}: no pair at that level, never filled "
            "in."
        ),
        "quality_header": ["Dataset", "Decoder", "Without a level"],
        "h_degradation_curve": "### Accuracy over the degradation level (second figure, F5f B)",
        "figure2_alt": "Figure 2: accuracy over the degradation level",
        "figure2_caption": (
            "Figure 2. Accuracy over the degradation level per dataset (rows) and kind (columns), clean at "
            "0; dashed line: mean chance level; n: pairs per level. Under each panel: the share of sessions "
            "per quality level at each degradation level. Also as [PNG]({png})."
        ),
        "degradation_header": ["Dataset", "Decoder", "Kind", "0 (clean)"],
        "h_levels": "### Quality levels of the recordings",
        "levels_intro": (
            "Recordings per quality level in every condition, and the sessions per level "
            "(quality_summary.csv). {worse}: at or above at least one threshold."
        ),
        "levels_header": ["Dataset", "Condition", "Recordings", "No level", "{worse}", "Sessions {levels}"],
        "q4_or_worse": "Q{level} or worse",
        "no_level_short": "none",
        "rules_intro": (
            "Clean recordings: how often each rule gave the level (worst rule), how often it was not "
            "measurable, and its median ratio over the recordings where it was measured:"
        ),
        "rules_header": ["Dataset", "Rule", "Worst rule", "Not measurable", "Median ratio"],
        "reasons_intro": (
            "Rules that were not measurable, with NeuroGrid's reason key, summed over all conditions "
            "(unmeasured.csv):"
        ),
        "reasons_header": ["Dataset", "Rule", "Reason", "Recordings", "Conditions"],
        "no_reasons": "Every rule was measurable in every recording.",
        "h_compare": "### Comparison of the two runs (DoD 1)",
        "compare": (
            "`compare_runs` on the reported run `{run_a}` and its repetition `{run_b}`: **{verdict}**. "
            "Compared: {quality} quality.json files, the NeuroGrid values of {neurogrid} recordings and "
            "{folds} folds{cells}. EEGNet tolerance: {tolerance}. Differences: {differences}."
        ),
        "compare_cells": ", {cells} EEGNet cells",
        "verdicts": {
            "exact": "exactly equal",
            "tolerance": "equal within the EEGNet tolerance",
            "different": "different",
        },
        "tolerance_none": (
            "none (every EEGNet fold exactly equal, as every CSP+LDA fold and every NeuroGrid value)"
        ),
        "tolerance_relaxed": (
            "at most {trials} test trial per fold and {points} percentage points in the mean of a cell (F3); "
            "CSP+LDA folds and NeuroGrid values exactly equal"
        ),
        "differences_head": "First differences (file and key: run A, run B):",
        "h_limitations": "## Limitations",
        "lim_clean": (
            "- **Clean data at {worse} (pilot finding, A-109).** Clean recordings at {worse}: {shares}. The "
            "rule that gave the level of the clean recordings (worst rule): {worst}. The pilot measured this "
            "before the full run; the owner decided to continue and to report it as a finding, with the "
            "datasets and NeuroGrid unchanged. NeuroGrid's calibrated thresholds (M06, M07, M09) are the "
            "95th percentile of a public test corpus of other recordings and are not adapted to these "
            "datasets; where clean data lie at or above a threshold, the quality axis of that dataset has "
            "little range below {threshold_level}."
        ),
        "lim_m09a": (
            "- **M09a can miss local artefacts.** M09a is the share of epochs that local autoreject "
            "rejects, and autoreject first interpolates a few bad channels of an epoch: an artefact on one "
            "or a few channels (an electrode pop, a frontal blink) is repaired rather than rejected."
        ),
        "lim_m09a_data": "Median M09a ratio, clean and at the highest artefact level of the run: {values}.",
        "lim_m09b": (
            "- **M09b is often not measurable with few EEG channels.** The research configuration sets "
            "`min_channels` to the number of EEG channels of the dataset, and M09b needs that many channels "
            "once the bad channels of M06 are left out, so one bad channel is enough to make it not "
            "measurable."
        ),
        "lim_m09b_data": "Clean recordings without M09b: {values}.",
        "lim_saturation": (
            "- **The worst-ratio rule saturates (A-102, finding on A-45).** One flat channel gives M08 a "
            "flat share of the whole duration against a threshold of {threshold}, a ratio of {ratio}, so "
            "every level of the channel ladder lands at Q{top} and the main curve mixes them there; the "
            "second figure separates them."
        ),
        "lim_saturation_data": "Recordings at Q{top} at the first level of the channel ladder: {values}.",
        "lim_line": (
            "- **Band-pass filters remove most line noise before decoding.** CSP+LDA decodes motor imagery "
            "in {mi_band} Hz and SSVEP in narrow bands around the stimulus frequencies, EEGNet uses "
            "{eegnet_band} Hz, all below the line frequencies of the datasets ({lines} Hz): the line-noise "
            "ladder can therefore move the quality level (M07) without moving the accuracy."
        ),
        "lim_line_data": "Mean accuracy, clean and at the highest line-noise level of the run: {values}.",
        "lim_line_except": "For {name} with EEGNet this does not hold; see the next item.",
        "lim_phase": (
            "- **{name}: the added line noise carries the class (finding after the full runs, A-111).** "
            "MOABB's loader of {name} puts the trials of each class into one block, with the trial onsets a "
            "whole number of periods of the line frequency apart, and joins the two blocks with a gap of "
            "zeros that is not a whole number of periods. The sinusoid of the line-noise ladder runs "
            "through the whole recording, so it has one phase at the onset of every trial of one class and "
            "another phase at the onset of every trial of the other class: the added noise is locked to "
            "the class. EEGNet's temporal convolutions respond to the phase and can learn such a signal "
            "from what the band-pass filter leaves of it; CSP+LDA uses the variance of the signal, which "
            "does not depend on the phase. Along the line-noise ladder of {name} the EEGNet accuracy rises "
            "and the CSP+LDA accuracy does not. The EEGNet accuracies of this ladder, and the EEGNet point "
            "of {name} at Q{top} in the main figure, which contains its pairs, therefore cannot be read as "
            "decoding of EEG under line noise. The degradation was not changed after the results were "
            "seen (F4c)."
        ),
        "lim_phase_data": (
            "Mean accuracy of {name} over the line-noise ladder (clean, levels {levels}): {values}."
        ),
        "lim_phase_top": (
            "EEGNet at Q{top} of {name}: {all} over {n} pairs, {n_line} of them from the line-noise ladder; "
            "without these {rest} over {n_rest} pairs (mean only, no interval)."
        ),
        "lim_equality": (
            "- **Equality only per machine and lock (A-106).** Another machine, another BLAS build or "
            "another lock can give other EEGNet weights and so other accuracies; the comparison of the two "
            "runs holds for one machine and one lock, nothing is claimed across machines."
        ),
        "lim_cho": (
            "- **Cho2017: trials joined by MOABB.** The MOABB loader of Cho2017 joins the trials of a "
            "subject end to end into continuous runs, which leaves discontinuities at the joints. This is an "
            "unverified possible contributor to the M09a ratios of the clean Cho2017 recordings (median "
            "{median})."
        ),
        "lim_kalunga": (
            "- **Few trials per Kalunga2016 session.** {trials} trials per session, about {test} "
            "test trials per fold: one trial moves the accuracy of a session by up to {step} percentage "
            "points, and EEGNet trains on few examples."
        ),
        "lim_design": (
            "- **Design limits.** CSP+LDA on SSVEP is not a typical SSVEP decoder (F7); EEGNet runs with "
            "default hyperparameters without tuning; training and test stay within one session and one "
            "condition (A-104)."
        ),
        "lim_design_channels": (
            "With few EEG channels ({values}) M06 and M09 say less than on dense montages (F5d)."
        ),
        "h_scope": "## Scope statement",
        "scope": (
            "This report applies only to the public datasets and decoders studied; no statement about the "
            "performance or safety of a medical device. NeuroGrid's quality level is used here as a research "
            "measure only (A-45); it is not part of NeuroGrid's own reports."
        ),
        "licence": (
            "Report, figures and aggregated results: CC BY 4.0. The datasets keep their own licences (see "
            "Data)."
        ),
        "kinds": {
            "clean": "clean",
            "line_noise": "line noise",
            "channels": "flat channels",
            "artifacts": "artefacts",
        },
        "rules": {
            "CORE-M06-01": "M06 bad channels",
            "CORE-M07-01": "M07 line noise",
            "CORE-M08-01": "M08 flat",
            "CORE-M08-02": "M08 clipping",
            "CORE-M09-01": "M09a autoreject",
            "CORE-M09-02": "M09b ICLabel",
        },
        "sep": "; ",
        "space": " ",
        "inner": ", ",
        "of": "{name} {n} of {total} ({share})",
        "of_plain": "{name} {n} of {total}",
        "named": "{name}: {items}",
        "item": "{label} {n}",
        "change": "{name} {clean} \N{RIGHTWARDS ARROW} {high} ({condition})",
        "change_decoder": "{name} {decoder} {clean} \N{RIGHTWARDS ARROW} {high} ({condition})",
        "m09b_item": "{name} ({channels} channels) {n} of {total}, reasons: {reasons}",
        "channel_item": "{name}: {counts}",
        "count_channels": "{name} {n}",
        "none": "none",
    },
    "zh": {
        "title": "# NeuroArena：解码器准确率与 NeuroGrid 质量等级",
        "generated": "<!-- 由 `python -m neuroarena.report render` 根据 results/ 生成，请勿手工编辑。 -->",
        "intro": (
            "NeuroArena {version} 技术报告（NG-F17）：报告的运行为 `{run_a}`，其重复运行为 `{run_b}`，模式为 "
            "`{mode}`。下文中的每个数字都来自 `results/` 中已发布的文件。"
        ),
        "mode_smoke": (
            "> **smoke 模式：** 本报告基于一次短时运行生成，该运行使用的是各数据集的合成替代数据（未下载数据"
            "，EEGNet 只训练少数几轮），其中的数字不代表这些数据集。"
        ),
        "mode_pilot": "> **pilot 模式：** 本报告基于试运行（A-109）生成，而非完整运行。",
        "h_goal": "## 目标",
        "goal": (
            "训练和测试所用数据的 NeuroGrid 质量等级如何影响两种标准解码器的准确率？NeuroArena 用 NeuroGrid "
            "检查 {n_datasets} 个公开 MOABB 数据集的每条记录，为每个会话确定 {first}{dash}{last} 的质量等级，"
            "按类型（{kinds}）对数据进行每类 {n_levels} 级的受控劣化，并在每种条件下于每个会话中评估 CSP+LDA "
            "和 EEGNet（PRD 第 16 节，NG-F17）。主要结果是准确率随实测质量等级变化的曲线（F5f A）；准确率随劣"
            "化等级的变化是第二个视角（F5f B）。"
        ),
        "h_data": "## 数据",
        "data_intro": (
            "本次运行使用了 {n_datasets} 个公开 MOABB 数据集，数据以 moabb {moabb} 加载器返回的形式为准（以加"
            "载器的数字为准，而非文档），采用{subjects}。各数据集的会话数、记录数和每个会话的试次数："
        ),
        "subjects_all": "每个数据集的全部受试者（F2 A）",
        "subjects_subset": "经负责人批准的部分受试者（{subsets}）",
        "data_header": [
            "数据集",
            "范式",
            "类别",
            "受试者",
            "会话",
            "记录",
            "EEG 通道",
            "采样率",
            "工频",
            "每会话试次",
        ],
        "paradigms": {"imagery": "运动想象", "ssvep": "SSVEP（稳态视觉诱发电位）"},
        "h_attribution": "### 数据来源与署名",
        "attribution": [
            "- 引用：{citation}",
            "- 论文：[doi:{doi}](https://doi.org/{doi})",
            "- 数据来源：{source}",
            "- 下载地址：{download}",
            "- 下载来源处的许可协议：{licence}。说明（英文原文）：{note}",
        ],
        "attribution_note": (
            "数据在内存中劣化；NeuroGrid 读取的是临时 FIF 文件，每种条件处理完毕后即被删除。NeuroArena 不对这"
            "些数据进行再分发：本代码库只包含代码、汇总结果、图和本报告，不包含任何记录。"
        ),
        "h_method": "## 方法",
        "h_neurogrid": "### NeuroGrid 与质量等级（A-101、A-102）",
        "neurogrid_call": (
            "{tool} 通过主项目的公开命令行，对每个数据集和每种条件的记录各检查一次（A-101）；NeuroArena 从不"
            "以库的方式导入 NeuroGrid。调用方式如下（占位符由本次运行自己的文件夹替代）："
        ),
        "neurogrid_settings": (
            "劣化后的记录被写成临时 FIF 文件（MNE 格式 `{fif}`）。core 规则包保持不变，使用其默认阈值和默认抽"
            "样（{segments} 段，每段 {segment_s} 秒，种子 {seed}；M06 和 M09 至少需要 {min_seconds} 秒数据）"
            "；其他规则的结果不予使用。研究配置只为每个数据集设置以下两个值（F5d）："
        ),
        "config_header": ["数据集", "`[quality] min_channels`", "`[metadata.defaults] line_frequency_hz`"],
        "level_rule": (
            "对每条记录，根据 NeuroGrid 的 results.json，计算下表中每条规则的 r = 测量值 / 有效阈值；M07 和 "
            "M08 在每条记录上取各通道有限值中的最大值。无法测量的规则被略去并计数；CORE-M07-02（工频合理性）"
            "不计入。比值最大的规则决定等级（A-102）：{bounds}。比值恰好落在边界上时归入较高等级，因此 "
            "{threshold_level} 从阈值开始，{below} 表示低于所有阈值。没有任何可测规则的记录没有等级；这类记录"
            "会被列出，绝不丢弃。会话的等级是其各运行（run）中已有等级的最差等级。"
        ),
        "thresholds_header": ["规则", "每条记录的测量值", "有效阈值"],
        "rule_values": {
            "CORE-M06-01": "M06：NeuroGrid 抽样数据中坏 EEG 通道的比例（pyprep）",
            "CORE-M07-01": "M07：工频干扰比，取各通道最大值",
            "CORE-M08-01": "M08：平直段占时长的比例，取各通道最大值",
            "CORE-M08-02": "M08：削波占时长的比例，取各通道最大值",
            "CORE-M09-01": "M09a：抽样数据中被局部 autoreject 拒绝的分段比例",
            "CORE-M09-02": "M09b：最可能的 ICLabel 类别不是 brain 的 ICA 成分比例",
        },
        "h_degradation": "### 受控劣化（A-103、F4）",
        "degradation_intro": (
            "共 {n_conditions} 种条件：干净数据，以及每种类型一条劣化阶梯，等级为 {first}{dash}{last}（F4a "
            "A）。劣化作用于滤波和分段之前的原始信号（MNE Raw，单位伏特），只作用于 EEG 通道，每条记录、每种"
            "类型、每个等级使用各自的种子（由其名称的 SHA-256 得出）；电极布局、通道集合、标注和事件保持不变"
            "。各等级的取值在首次运行前已经确定，从未根据结果调整（F4c）。"
        ),
        "line_noise": (
            "- **工频干扰：** 在数据集的工频处叠加一个正弦波，并在其二次谐波处（低于奈奎斯特频率时）叠加振幅"
            "为基波 {harmonic} 倍的正弦波，每个通道的相位随机；相对于该通道 {band} Hz 频段功率，其功率在等级 "
            "{first}{dash}{last} 依次为 {db} dB。"
        ),
        "channels": (
            "- **平直通道：** 将一条记录中 k 个 EEG 通道置为 {flat} V，k = max(m, round(f \N{MIDDLE DOT} "
            "n))，其中 n 为 EEG 通道数，f = {fractions}，m = {minimums}：{per_dataset}。"
        ),
        "artifacts": (
            "- **伪迹：** 将一条记录划分为互不重叠的 {epoch} 秒分段，其中 {fractions} 的分段各叠加一个伪迹，"
            "三种类型各占一份：眨眼（{blink_s} 秒的 Hann 脉冲，额极处 {blink_uv} \N{MICRO SIGN}V，向头后部衰"
            "减）、肌电爆发（{muscle_s} 秒，{muscle_low} Hz 至奈奎斯特频率以下 {margin} Hz，受影响最大的通道"
            "上均方根值为 {muscle_uv} \N{MICRO SIGN}V）和电极跳变（{pop_channels} 个通道上 {pop_uv} "
            "\N{MICRO SIGN}V 的阶跃，按 {pop_s} 秒的时间常数衰减）。"
        ),
        "h_decoders": "### 解码器（A-105、F7）",
        "csp": (
            "- **CSP+LDA**，与 MOABB 流水线“CSP + LDA”相同：协方差估计 `{cov}`，{filters} 个滤波器的 CSP（对"
            "数方差），LDA（求解器 `{solver}`）。运动想象：{mi_band} Hz 带通滤波。SSVEP：滤波器组，在每个刺激"
            "频率周围取 \N{PLUS-MINUS SIGN}{half} Hz 的频带，每个频带各做 CSP，再用 LDA 处理所有频带的特征；"
            "这是 NeuroArena 用相同组件自行搭建的方案，并非典型的 SSVEP 解码器（F7）。"
        ),
        "eegnet": (
            "- **EEGNet：** 采用默认结构的 `{cls}`，作为 skorch 分类器；{band} Hz 带通滤波并重采样至 {rate} "
            "Hz；优化器 `{opt}`，学习率 {lr}，批大小 {batch}，损失函数 `{crit}`，最多 {max_epochs} 轮（本次运"
            "行的上限为 {mode_epochs} 轮），在训练试次中按分层且固定种子的方式划出 {share} 作为验证集，以 "
            "`{monitor}` 早停，耐心值 {patience}，保留最佳一轮的权重；设备 `{device}`。不在测试数据上调参。"
        ),
        "scale": (
            "- **与参考示例的偏差（输入缩放）：** 训练过程遵循 EEGNet 作者的参考示例（arl-eegmodels，`example"
            "s/ERP.py`），该示例把输入从伏特换算为毫伏。在 braindecode 的批归一化下，毫伏输入使早停在 EEGNet "
            "学到东西之前就结束了训练（完整运行前测得），因此 NeuroArena 将输入乘以 {scale}（伏特换算为微伏）"
            "。该系数是常数，从不根据数据拟合。"
        ),
        "h_evaluation": "### 评估（A-104、F6 A）",
        "evaluation": (
            "训练和测试在同一条件下进行：NeuroGrid 检查的是训练数据，因此问题在于某一质量等级的数据能支持多高"
            "的准确率。在每个会话内进行 {folds} 折分层交叉验证（打乱，固定种子），与 MOABB 的会话内评估标准一"
            "致。会话的准确率为各折中预测正确的测试试次数之和除以测试试次总数；其随机水平为该会话中最常见类别"
            "所占的比例。曲线上的每个点是其中各（会话，条件）组合的平均准确率，并给出均值的 {confidence} 自助"
            "法区间（百分位法，{resamples} 次重抽样，固定种子）：主曲线按会话的质量等级对所有条件下的组合进行"
            "分组，第二张图按每种类型的劣化等级分组，干净数据位于 0。配对设计：一个会话的折划分和 EEGNet 的初"
            "始权重使用种子 `{session_seed}`，在每种条件下、对两种解码器都相同，因此曲线反映的是数据的变化，"
            "而不是划分的变化。"
        ),
        "h_reproducibility": "### 可复现性（A-106）",
        "reproducibility": (
            "基础种子 {base_seed}；工作进程以 spawn 方式启动，环境变量为 {env}；torch 使用确定性算法和单线程"
            "，只在 CPU 上运行。两次运行结果相同的保证只限于同一台机器和同一组锁文件；本报告的两次运行在 "
            "{system} {machine} 上完成，所用锁文件（SHA-256）为：{locks}。版本：{versions}。"
        ),
        "h_results": "## 结果",
        "overview_intro": (
            "各数据集的会话数、条件数、每种解码器的（会话，条件）组合数、没有质量等级的组合数，以及各会话随机"
            "水平的平均值："
        ),
        "overview_header": ["数据集", "会话", "条件", "每种解码器的组合数", "无等级的组合数", "平均随机水平"],
        "h_quality_curve": "### 准确率随质量等级的变化（主图，F5f A）",
        "figure1_alt": "图 1：准确率随质量等级的变化",
        "figure1_caption": (
            "图 1. 各数据集、各解码器的准确率随会话质量等级的变化：该等级下各（会话，条件）组合的平均值及其 "
            "{confidence} 自助法区间；虚线：该数据集的平均随机水平；n：每个等级的组合数（两种解码器的组"
            "合数不同时，写作 CSP+LDA/EEGNet）；每个子图下方注明没有等级的组合数。没有组合的等级不画点。图"
            "中文字为英文。另有 [PNG 版本]({png})。"
        ),
        "cells_note": "单元格：平均准确率 [自助法区间]（组合数）；{dash}：该等级没有组合，不作填补。",
        "quality_header": ["数据集", "解码器", "无等级"],
        "h_degradation_curve": "### 准确率随劣化等级的变化（第二张图，F5f B）",
        "figure2_alt": "图 2：准确率随劣化等级的变化",
        "figure2_caption": (
            "图 2. 各数据集（行）、各劣化类型（列）的准确率随劣化等级的变化，干净数据位于 0；虚线：平均随机水"
            "平；n：每个等级的组合数。每个子图下方：各劣化等级下会话在各质量等级中所占的比例。图中文字为英文"
            "。另有 [PNG 版本]({png})。"
        ),
        "degradation_header": ["数据集", "解码器", "类型", "0（干净）"],
        "h_levels": "### 记录的质量等级",
        "levels_intro": (
            "每种条件下各质量等级的记录数，以及各等级的会话数（quality_summary.csv）。{worse}：至少达到或超过"
            "一个阈值。"
        ),
        "levels_header": ["数据集", "条件", "记录", "无等级", "{worse}", "会话 {levels}"],
        "q4_or_worse": "Q{level} 及更差",
        "no_level_short": "无",
        "rules_intro": (
            "干净记录：每条规则决定等级（比值最大）的次数、无法测量的次数，以及在可测记录上的比值中位数："
        ),
        "rules_header": ["数据集", "规则", "比值最大", "无法测量", "比值中位数"],
        "reasons_intro": "无法测量的规则及 NeuroGrid 给出的原因键，按所有条件汇总（unmeasured.csv）：",
        "reasons_header": ["数据集", "规则", "原因", "记录", "条件"],
        "no_reasons": "每条记录中的每条规则均可测量。",
        "h_compare": "### 两次运行的比较（DoD 1）",
        "compare": (
            "对报告的运行 `{run_a}` 及其重复运行 `{run_b}` 执行 `compare_runs`：**{verdict}**。比较内容："
            "{quality} 个 quality.json 文件、{neurogrid} 条记录的 NeuroGrid 测量值和 {folds} 个折{cells}。"
            "EEGNet 容差：{tolerance}。差异数：{differences}。"
        ),
        "compare_cells": "、{cells} 个 EEGNet 单元",
        "verdicts": {"exact": "完全相同", "tolerance": "在 EEGNet 容差范围内相同", "different": "不同"},
        "tolerance_none": "无（每个 EEGNet 折都完全相同，每个 CSP+LDA 折和每个 NeuroGrid 测量值也是如此）",
        "tolerance_relaxed": (
            "每折正确预测的测试试次数最多相差 {trials} 个，每个单元的平均值最多相差 {points} 个百分点（F3）；"
            "CSP+LDA 折和 NeuroGrid 测量值完全相同"
        ),
        "differences_head": "前几项差异（文件和键：运行 A，运行 B）：",
        "h_limitations": "## 局限性",
        "lim_clean": (
            "- **干净数据已处于 {worse}（试运行发现，A-109）。** 处于 {worse}的干净记录：{shares}。决定干净记"
            "录等级的规则（比值最大）：{worst}。试运行在完整运行之前就测得了这一点；负责人决定继续，并将其作"
            "为一项发现报告，数据集和 NeuroGrid 均保持不变。NeuroGrid 的校准阈值（M06、M07、M09）取自公开测试"
            "语料（由其他记录组成）的第 95 百分位数，并未针对这些数据集调整；当干净数据已达到或超过某个阈值时"
            "，该数据集的质量轴在 {threshold_level} 以下几乎没有跨度。"
        ),
        "lim_m09a": (
            "- **M09a 可能漏掉局部伪迹。** M09a 是局部 autoreject 拒绝的分段所占比例，而 autoreject 会"
            "先对一个分段中少数坏通道进行插值：只影响一个或少数几个通道的伪迹（电极跳变、额部眨眼）会被修复，"
            "而不是被拒绝。"
        ),
        "lim_m09a_data": "干净数据和本次运行中最高伪迹等级下 M09a 比值的中位数：{values}。",
        "lim_m09b": (
            "- **EEG 通道较少时 M09b 往往无法测量。** 研究配置把 `min_channels` 设为数据集的 EEG 通道数，而 "
            "M09b 在去除 M06 判定的坏通道后仍需要这么多通道，因此只要有一个坏通道就会无法测量。"
        ),
        "lim_m09b_data": "没有 M09b 的干净记录：{values}。",
        "lim_saturation": (
            "- **“比值最大”规则会饱和（A-102，关于 A-45 的发现）。** 一个平直通道使 M08 的平直比例为 1（即整"
            "个时长），而阈值为 {threshold}，比值即为 {ratio}，因此通道阶梯的每个等级都落在 Q{top}，主曲线在"
            "该处把它们混在一起；第二张图把它们区分开来。"
        ),
        "lim_saturation_data": "通道阶梯第一级处于 Q{top} 的记录：{values}。",
        "lim_line": (
            "- **带通滤波在解码前去除了大部分工频干扰。** CSP+LDA 对运动想象使用 {mi_band} Hz，对 SSVEP 使用"
            "刺激频率附近的窄频带，EEGNet 使用 {eegnet_band} Hz，均低于各数据集的工频（{lines} Hz）：因此工频"
            "干扰阶梯可能改变质量等级（M07），而准确率不变。"
        ),
        "lim_line_data": "干净数据和本次运行中最高工频干扰等级下的平均准确率：{values}。",
        "lim_line_except": "对 {name} 的 EEGNet 而言并非如此，见下一条。",
        "lim_phase": (
            "- **{name}：添加的工频干扰携带了类别信息（完整运行后的发现，A-111）。** {name} 的 MOABB 加载器把"
            "每个类别的试次放进一个块，试次起点之间相隔工频周期的整数倍，再用一段零值把两个块连接"
            "起来，而这段零值的长度不是周期的整数倍。工频干扰阶梯的正弦波贯穿整条记录，因此它在一个"
            "类别每个试次的起点处相位相同，在另一类别每个试次的起点处是另一个相位：添加的干扰与类别"
            "锁定。EEGNet 的时间卷积对相位敏感，能够从带通滤波后残留的部分中学到这种信号；CSP+LDA "
            "使用信号的方差，而方差与相位无关。沿 {name} 的工频干扰阶梯，EEGNet 的准确率上升，"
            "CSP+LDA 的准确率不变。因此，该阶梯上 EEGNet 的准确率，以及主图中包含这些组合的 {name} "
            "EEGNet 在 Q{top} 的点，都不能解读为在工频干扰下对脑电的解码。看到结果后没有更改劣化方法"
            "（F4c）。"
        ),
        "lim_phase_data": "{name} 在工频干扰阶梯上的平均准确率（干净数据，等级 {levels}）：{values}。",
        "lim_phase_top": (
            "{name} EEGNet 在 Q{top}：{n} 个组合的平均为 {all}，其中 {n_line} 个来自工频干扰阶梯；"
            "去掉这些后，{n_rest} 个组合的平均为 {rest}（只有均值，没有区间）。"
        ),
        "lim_equality": (
            "- **结果相同只限于同一台机器和同一组锁文件（A-106）。** 换一台机器、换一个 BLAS 版本或换一组锁文"
            "件，都可能得到不同的 EEGNet 权重，进而得到不同的准确率；两次运行的比较只对一台机器和一组锁文件成"
            "立，不对跨机器的情况作任何陈述。"
        ),
        "lim_cho": (
            "- **Cho2017：试次由 MOABB 首尾拼接。** Cho2017 的 MOABB 加载器把一个受试者的各试次首尾相接，拼成"
            "连续的运行，拼接处留下信号不连续。这可能是干净 Cho2017 记录 M09a 比值较高的原因之一，但未经验证"
            "（中位数 {median}）。"
        ),
        "lim_kalunga": (
            "- **Kalunga2016 每个会话的试次很少。** 每个会话 {trials} 个试次，每折约 {test} 个测试试"
            "次：一个试次就能使会话准确率最多变化 {step} 个百分点，而且 EEGNet 只能在很少的样本上训练。"
        ),
        "lim_design": (
            "- **设计上的局限。** CSP+LDA 并非典型的 SSVEP 解码器（F7）；EEGNet 使用默认超参数，未经调参；训"
            "练和测试都限于同一会话、同一条件（A-104）。"
        ),
        "lim_design_channels": (
            "EEG 通道较少时（{values}），M06 和 M09 所能反映的信息少于在高密度电极布局下（F5d）。"
        ),
        "h_scope": "## 适用范围声明",
        "scope": (
            "本报告仅适用于所研究的公开数据集和解码器；不对任何医疗器械的性能或安全性作任何陈述。此处的 "
            "NeuroGrid 质量等级仅作为研究指标使用（A-45），不属于 NeuroGrid 自身报告的内容。"
        ),
        "licence": "报告、图和汇总结果：CC BY 4.0。各数据集保留其自身的许可协议（见“数据”一节）。",
        "kinds": {"clean": "干净", "line_noise": "工频干扰", "channels": "平直通道", "artifacts": "伪迹"},
        "rules": {
            "CORE-M06-01": "M06 坏通道",
            "CORE-M07-01": "M07 工频干扰",
            "CORE-M08-01": "M08 平直段",
            "CORE-M08-02": "M08 削波",
            "CORE-M09-01": "M09a autoreject",
            "CORE-M09-02": "M09b ICLabel",
        },
        "sep": "；",
        "space": "",
        "inner": "、",
        "of": "{name}：{total} 条中的 {n} 条（{share}）",
        "of_plain": "{name}：{total} 条中的 {n} 条",
        "named": "{name}：{items}",
        "item": "{label} {n}",
        "change": "{name}：{clean} \N{RIGHTWARDS ARROW} {high}（{condition}）",
        "change_decoder": "{name} {decoder}：{clean} \N{RIGHTWARDS ARROW} {high}（{condition}）",
        "m09b_item": "{name}（{channels} 个通道）：{total} 条中的 {n} 条，原因：{reasons}",
        "channel_item": "{name}：{counts}",
        "count_channels": "{name} {n}",
        "none": "无",
    },
}

# The order of the report's sections (A-107); the test checks the headings of both languages.
SECTIONS = ("h_goal", "h_data", "h_method", "h_results", "h_limitations", "h_scope")


def report_text(data: Results, language: str, links: Mapping[str, str]) -> str:
    """The Markdown report in ``language`` ("en" or "zh") from ``data``; ``links`` maps the figure files to
    their paths relative to the report."""
    t = TEXTS[language]
    view = _View(data, t)
    lines = [t["generated"], "", t["title"], ""]
    method = data.method
    lines += [
        t["intro"].format(
            version=method["versions"].get("neuroarena"),
            run_a=method["runs"][0],
            run_b=method["runs"][1],
            mode=method["mode"],
        ),
        "",
    ]
    if method["mode"] in ("smoke", "pilot"):
        lines += [t[f"mode_{method['mode']}"], ""]
    lines += view.goal() + view.data_section() + view.methods() + view.results(links) + view.limitations()
    lines += [t["h_scope"], "", t["scope"], "", t["licence"], ""]
    return "\n".join(lines).rstrip("\n") + "\n"


class _View:
    """The sections of the report for one language (the texts of TEXTS), all built from one Results."""

    def __init__(self, data: Results, texts: Mapping[str, Any]) -> None:
        self.data = data
        self.t = texts
        method = data.method
        self.method = method
        self.datasets = list(method["config"]["datasets"])
        self.decoders = list(method["config"]["decoders"])
        self.conditions = [Condition.from_id(c) for c in method["config"]["conditions"]]
        self.summary = {(row["dataset"], row["condition"]): row for row in data.summary}
        self.levels = list(method["quality"]["levels"])

    # -- helpers --

    def _kind(self, kind: str) -> str:
        return self.t["kinds"].get(kind, kind)

    def _condition(self, condition: Condition) -> str:
        if condition == CLEAN:
            return self._kind(CLEAN.kind)
        return f"{self._kind(condition.kind)} {condition.level}"

    def _rule(self, rule: str) -> str:
        return self.t["rules"].get(rule, rule)

    def _decoder(self, decoder: str) -> str:
        return DECODER_STYLE.get(decoder, (decoder,))[0]

    def _worse(self) -> str:
        return self.t["q4_or_worse"].format(level=self._threshold_level())

    def _threshold_level(self) -> int:
        """The first level at or above the threshold (the level whose lower bound is 1.0)."""
        bounds = list(self.method["quality"]["boundaries"])
        return self.levels[bounds.index(1.0) + 1] if 1.0 in bounds else self.levels[-2]

    def _first_condition(self) -> Condition:
        return CLEAN if CLEAN in self.conditions else self.conditions[0]

    def _rows(
        self, dataset: str, condition: Condition | None = None, decoder: str | None = None
    ) -> list[Any]:
        return [
            row
            for row in self.data.sessions
            if row.dataset == dataset
            and (condition is None or row.condition == condition.id)
            and (decoder is None or row.decoder == decoder)
        ]

    def _highest(self, kind: str) -> Condition | None:
        found = [c for c in self.conditions if c.kind == kind]
        return max(found, key=lambda c: c.level) if found else None

    # -- sections --

    def goal(self) -> list[str]:
        t = self.t
        text = t["goal"].format(
            n_datasets=len(self.datasets),
            first=f"Q{self.levels[0]}",
            last=f"Q{self.levels[-1]}",
            dash=DASH,
            n_levels=len(LEVELS),
            kinds=t["inner"].join(self._kind(kind) for kind in KINDS),
        )
        return [t["h_goal"], "", text, ""]

    def data_section(self) -> list[str]:
        t, method = self.t, self.method
        subjects = method["config"]["subjects"]
        if subjects is None:
            chosen = t["subjects_all"]
        else:
            listed = t["sep"].join(f"{d}: {', '.join(map(str, s))}" for d, s in sorted(subjects.items()))
            chosen = t["subjects_subset"].format(subsets=listed)
        lines = [
            t["h_data"],
            "",
            t["data_intro"].format(
                n_datasets=len(self.datasets), moabb=method["versions"].get("moabb"), subjects=chosen
            ),
            "",
        ]
        first = self._first_condition()
        rows = []
        for name in self.datasets:
            spec = method["datasets"][name]
            row = self.summary.get((name, first.id), {})
            trials = [r.n_trials for r in self._rows(name, first, self.decoders[0])]
            rows.append(
                [
                    name,
                    t["paradigms"].get(spec["paradigm"], spec["paradigm"]),
                    self.t["inner"].join(spec["events"]),
                    str(len(method["subjects"][name])),
                    row.get("n_sessions", DASH),
                    row.get("n_recordings", DASH),
                    str(spec["n_eeg_channels"]),
                    f"{_num(spec['sampling_rate_hz'])} Hz",
                    f"{_num(spec['line_frequency_hz'])} Hz",
                    _span(trials),
                ]
            )
        lines += _table(t["data_header"], rows) + ["", t["h_attribution"], ""]
        for name in self.datasets:
            spec = method["datasets"][name]
            lines += [f"**{name}**", ""]
            lines += [
                line.format(
                    citation=spec["citation"],
                    doi=spec["paper_doi"],
                    source=spec["source"],
                    download=spec["download"],
                    licence=spec["licence"],
                    note=spec["licence_note"],
                )
                for line in t["attribution"]
            ]
            lines.append("")
        lines += [t["attribution_note"], ""]
        return lines

    def method_neurogrid(self) -> list[str]:
        t, neurogrid = self.t, self.method["neurogrid"]
        settings = neurogrid["settings"]
        sampling = settings.get("sampling") or {}
        lines = [t["h_neurogrid"], "", t["neurogrid_call"].format(tool=neurogrid["version"]), ""]
        lines += ["```", neurogrid["call"], "```", ""]
        lines += [
            t["neurogrid_settings"].format(
                fif=neurogrid["fif_format"],
                segments=_num(sampling.get("segments")),
                segment_s=_num(sampling.get("segment_s")),
                seed=_num(settings.get("seed")),
                min_seconds=_num(settings.get("quality", {}).get("min_seconds")),
            ),
            "",
        ]
        rows = []
        for name in self.datasets:
            configuration = neurogrid["configuration"].get(name, {})
            rows.append(
                [
                    name,
                    _num(configuration.get("quality", {}).get("min_channels")),
                    _num(configuration.get("metadata", {}).get("defaults", {}).get("line_frequency_hz")),
                ]
            )
        lines += _table(t["config_header"], rows) + [""]
        bounds = list(self.method["quality"]["boundaries"])
        parts = []
        for index, level in enumerate(self.levels):
            low = bounds[index - 1] if index > 0 else None
            high = bounds[index] if index < len(bounds) else None
            if low is None:
                parts.append(f"Q{level}: r < {_num(high)}")
            elif high is None:
                parts.append(f"Q{level}: r \N{GREATER-THAN OR EQUAL TO} {_num(low)}")
            else:
                parts.append(f"Q{level}: {_num(low)} \N{LESS-THAN OR EQUAL TO} r < {_num(high)}")
        below = [level for level in self.levels if level < self._threshold_level()]
        lines += [
            t["level_rule"].format(
                bounds=t["sep"].join(parts),
                threshold_level=f"Q{self._threshold_level()}",
                below=f"Q{below[0]}{DASH}Q{below[-1]}" if below else DASH,
            ),
            "",
        ]
        thresholds = neurogrid["thresholds"]
        rows = [[f"`{rule}`", t["rule_values"].get(rule, rule), _num(thresholds[rule])] for rule in RULE_IDS]
        return [*lines, *_table(t["thresholds_header"], rows), ""]

    def method_degradation(self) -> list[str]:
        t, constants = self.t, self.method["degradation"]
        lines = [
            t["h_degradation"],
            "",
            t["degradation_intro"].format(
                n_conditions=len(self.conditions), first=LEVELS[0], last=LEVELS[-1], dash=DASH
            ),
            "",
        ]
        lines.append(
            t["line_noise"].format(
                harmonic=_num(constants["line_noise_harmonic_amplitude"]),
                band=_range(constants["line_noise_reference_band_hz"]),
                db=self.t["inner"].join(_signed(v) for v in constants["line_noise_db"]),
                first=LEVELS[0],
                last=LEVELS[-1],
                dash=DASH,
            )
        )
        per_dataset = t["sep"].join(
            t["channel_item"].format(
                name=name,
                counts=self.t["inner"].join(map(str, self.method["datasets"][name]["flattened_channels"])),
            )
            for name in self.datasets
        )
        lines.append(
            t["channels"].format(
                flat=_num(constants["flat_value_v"]),
                fractions=self.t["inner"].join(_share(v) for v in constants["channel_fractions"]),
                minimums=self.t["inner"].join(map(str, constants["channel_minimums"])),
                per_dataset=per_dataset,
            )
        )
        lines.append(
            t["artifacts"].format(
                fractions=self.t["inner"].join(_share(v) for v in constants["artifact_fractions"]),
                epoch=_num(constants["artifact_epoch_s"]),
                blink_s=_num(constants["blink_duration_s"]),
                blink_uv=_range(constants["blink_amplitude_uv"]),
                muscle_s=_num(constants["muscle_duration_s"]),
                muscle_low=_num(constants["muscle_low_hz"]),
                margin=_num(constants["muscle_nyquist_margin_hz"]),
                muscle_uv=_range(constants["muscle_amplitude_uv"]),
                pop_uv=_range(constants["pop_amplitude_uv"]),
                pop_channels=_num(constants["pop_channels"]),
                pop_s=_num(constants["pop_decay_s"]),
            )
        )
        return [*lines, ""]

    def method_decoders(self) -> list[str]:
        t, d = self.t, self.method["decoders"]
        return [
            t["h_decoders"],
            "",
            t["csp"].format(
                cov=d["covariance_estimator"],
                filters=_num(d["csp_filters"]),
                solver=d["lda_solver"],
                mi_band=_range(d["mi_band_csp_hz"]),
                half=_num(d["ssvep_band_half_width_hz"]),
            ),
            t["eegnet"].format(
                cls=d["eegnet_class"],
                band=_range(d["eegnet_band_hz"]),
                rate=_num(d["eegnet_sampling_rate_hz"]),
                opt=d["eegnet_optimizer"],
                lr=_num(d["eegnet_learning_rate"]),
                batch=_num(d["eegnet_batch_size"]),
                crit=d["eegnet_criterion"],
                max_epochs=_num(d["eegnet_max_epochs"]),
                mode_epochs=_num(d["eegnet_epochs_in_this_mode"]),
                monitor=d["eegnet_early_stopping_monitor"],
                patience=_num(d["eegnet_patience"]),
                share=_share(d["eegnet_validation_share"]),
                device=d["device"],
            ),
            t["scale"].format(scale=_power(d["eegnet_input_scale"])),
            "",
        ]

    def methods(self) -> list[str]:
        t, method = self.t, self.method
        evaluation = method["evaluation"]
        lines = [t["h_method"], ""]
        lines += self.method_neurogrid() + self.method_degradation() + self.method_decoders()
        lines += [
            t["h_evaluation"],
            "",
            t["evaluation"].format(
                folds=_num(evaluation["n_folds"]),
                confidence=_share(evaluation["confidence"]),
                resamples=_num(evaluation["bootstrap_resamples"]),
                session_seed=evaluation["session_seed"],
            ),
            "",
        ]
        env = self.t["inner"].join(f"`{k}={v}`" for k, v in sorted(method["worker_environment"].items()))
        locks = t["inner"].join(f"`{name}` `{value}`" for name, value in sorted(method["locks"].items()))
        versions = t["inner"].join(f"{name} {value}" for name, value in sorted(method["versions"].items()))
        machine = method.get("machine") or {}
        lines += [
            t["h_reproducibility"],
            "",
            t["reproducibility"].format(
                base_seed=method["base_seed"],
                env=env,
                system=machine.get("system"),
                machine=machine.get("machine"),
                locks=locks,
                versions=versions,
            ),
            "",
        ]
        return lines

    def results(self, links: Mapping[str, str]) -> list[str]:
        t = self.t
        lines = [t["h_results"], "", t["overview_intro"], ""]
        chance = _mean_chance(self.data.sessions)
        without = _sessions_without_level(self.data.sessions)
        rows = []
        for name in self.datasets:
            sessions = self.summary.get((name, self._first_condition().id), {}).get("n_sessions", DASH)
            pairs = len(self._rows(name, decoder=self.decoders[0]))
            missing = [without.get((name, decoder), 0) for decoder in self.decoders]
            rows.append(
                [
                    name,
                    sessions,
                    str(len(self.conditions)),
                    str(pairs),
                    str(missing[0]) if len(set(missing)) == 1 else "/".join(map(str, missing)),
                    _percent(chance.get(name)),
                ]
            )
        lines += _table(t["overview_header"], rows) + [""]

        quality_svg = links[f"{QUALITY_FIGURE}.svg"]
        lines += [t["h_quality_curve"], "", f"![{t['figure1_alt']}]({quality_svg})", ""]
        confidence = _share(self.method["evaluation"]["confidence"])
        lines += [t["figure1_caption"].format(confidence=confidence, png=links[f"{QUALITY_FIGURE}.png"]), ""]
        points = {(p.dataset, p.decoder, p.axis, p.kind, p.x): p for p in self.data.curve}
        header = [*t["quality_header"][:2], *(f"Q{level}" for level in self.levels), t["quality_header"][2]]
        rows = []
        for name in self.datasets:
            for decoder in self.decoders:
                cells = [
                    _point(points.get((name, decoder, "quality", "all", level))) for level in self.levels
                ]
                rows.append([name, self._decoder(decoder), *cells, str(without.get((name, decoder), 0))])
        lines += _table(header, rows) + ["", t["cells_note"].format(dash=DASH), ""]

        degradation_svg = links[f"{DEGRADATION_FIGURE}.svg"]
        lines += [t["h_degradation_curve"], "", f"![{t['figure2_alt']}]({degradation_svg})", ""]
        lines += [t["figure2_caption"].format(png=links[f"{DEGRADATION_FIGURE}.png"]), ""]
        kinds = [kind for kind in KINDS if any(c.kind == kind for c in self.conditions)] or list(KINDS)
        header = [*t["degradation_header"], *(str(level) for level in LEVELS)]
        rows = []
        for name in self.datasets:
            for decoder in self.decoders:
                for kind in kinds:
                    cells = [
                        _point(points.get((name, decoder, "degradation", kind, x))) for x in (0, *LEVELS)
                    ]
                    rows.append([name, self._decoder(decoder), self._kind(kind), *cells])
        lines += _table(header, rows) + ["", t["cells_note"].format(dash=DASH), ""]
        return lines + self.results_levels() + self.results_comparison()

    def results_levels(self) -> list[str]:
        t = self.t
        worse = self._worse()
        level_names = "/".join([*(f"Q{level}" for level in self.levels), t["no_level_short"]])
        lines = [t["h_levels"], "", t["levels_intro"].format(worse=worse), ""]
        head = t["levels_header"]
        header = [*head[:3], *(f"Q{level}" for level in self.levels), head[3], head[4].format(worse=worse)]
        header.append(head[5].format(levels=level_names))
        rows = []
        for name in self.datasets:
            for condition in self.conditions:
                row = self.summary.get((name, condition.id))
                if row is None:
                    continue
                counts = [row[f"sessions_q{level}"] for level in self.levels] + [
                    row["sessions_without_level"]
                ]
                share = row["q4_or_worse_share"]
                rows.append(
                    [
                        name,
                        self._condition(condition),
                        row["n_recordings"],
                        *(row[f"recordings_q{level}"] for level in self.levels),
                        row["recordings_without_level"],
                        _percent(float(share)) if share else DASH,
                        "/".join(counts),
                    ]
                )
        lines += _table(header, rows) + [""]
        if CLEAN in self.conditions:
            lines += [t["rules_intro"], ""]
            rows = []
            for name in self.datasets:
                row = self.summary.get((name, CLEAN.id))
                if row is None:
                    continue
                for rule in RULE_IDS:
                    median = row[f"median_ratio_{rule}"]
                    rows.append(
                        [
                            name,
                            self._rule(rule),
                            row[f"worst_{rule}"],
                            row[f"unmeasured_{rule}"],
                            _ratio(float(median)) if median else DASH,
                        ]
                    )
            lines += _table(t["rules_header"], rows) + [""]
        totals: dict[tuple[str, str, str], list[int]] = {}
        for entry in self.data.unmeasured:
            key = (entry["dataset"], entry["rule_id"], entry["reason"])
            totals.setdefault(key, []).append(int(entry["recordings"]))
        lines += [t["reasons_intro"], ""]
        if totals:
            order = {name: index for index, name in enumerate(self.datasets)}
            rules = {rule: index for index, rule in enumerate(RULE_IDS)}
            rows = [
                [name, self._rule(rule), f"`{reason}`", str(sum(counts)), str(len(counts))]
                for (name, rule, reason), counts in sorted(
                    totals.items(),
                    key=lambda item: (order.get(item[0][0], 99), rules.get(item[0][1], 99), item[0][2]),
                )
            ]
            lines += _table(t["reasons_header"], rows) + [""]
        else:
            lines += [t["no_reasons"], ""]
        return lines

    def results_comparison(self) -> list[str]:
        t, comparison = self.t, self.data.comparison
        if comparison["exact"]:
            verdict = t["verdicts"]["exact"]
        elif comparison["ok"]:
            verdict = t["verdicts"]["tolerance"]
        else:
            verdict = t["verdicts"]["different"]
        tolerance = comparison.get("tolerance")
        if tolerance is None:
            tolerance_text = t["tolerance_none"]
        else:
            tolerance_text = t["tolerance_relaxed"].format(
                trials=_num(tolerance["max_trials_per_fold"]),
                points=_num(tolerance["max_mean_points_per_cell"]),
            )
        compared = comparison["compared"]
        runs = list(comparison.get("runs") or self.method["runs"])
        cells = t["compare_cells"].format(cells=compared["cell"]) if "cell" in compared else ""
        lines = [
            t["h_compare"],
            "",
            t["compare"].format(
                run_a=runs[0],
                run_b=runs[1],
                verdict=verdict,
                quality=compared.get("quality", 0),
                neurogrid=compared.get("neurogrid", 0),
                folds=compared.get("fold", 0),
                cells=cells,
                tolerance=tolerance_text,
                differences=len(comparison["differences"]),
            ),
            "",
        ]
        if comparison["differences"]:
            lines += [t["differences_head"], ""]
            lines += [
                f"- `{d['what']}` {d['where']}: `{d['a']}`, `{d['b']}`"
                for d in comparison["differences"][:20]
            ]
            lines.append("")
        return lines

    def limitations(self) -> list[str]:
        t = self.t
        lines = [t["h_limitations"], ""]
        worse = self._worse()
        threshold_level = f"Q{self._threshold_level()}"
        clean = {
            name: self.summary[name, CLEAN.id] for name in self.datasets if (name, CLEAN.id) in self.summary
        }
        worse_levels = [level for level in self.levels if level >= self._threshold_level()]
        shares = t["sep"].join(
            t["of"].format(
                name=name,
                n=sum(int(row[f"recordings_q{level}"]) for level in worse_levels),
                total=row["n_recordings"],
                share=_percent(float(row["q4_or_worse_share"])) if row["q4_or_worse_share"] else DASH,
            )
            for name, row in clean.items()
        )
        worst = t["sep"].join(
            t["named"].format(name=name, items=self._counts(row, "worst_")) for name, row in clean.items()
        )
        if clean:
            lines.append(
                t["lim_clean"].format(
                    worse=worse, shares=shares, worst=worst, threshold_level=threshold_level
                )
            )
        lines.append(self._with_data(t["lim_m09a"], t["lim_m09a_data"], self._change("artifacts", clean)))
        m09b = []
        for name, row in clean.items():
            n = int(row["unmeasured_CORE-M09-02"])
            if n:
                reasons = [
                    e
                    for e in self.data.unmeasured
                    if e["dataset"] == name and e["condition"] == CLEAN.id and e["rule_id"] == "CORE-M09-02"
                ]
                m09b.append(
                    t["m09b_item"].format(
                        name=name,
                        channels=self.method["datasets"][name]["n_eeg_channels"],
                        n=n,
                        total=row["n_recordings"],
                        reasons=t["inner"].join(f"`{e['reason']}` {e['recordings']}" for e in reasons),
                    )
                )
        lines.append(self._with_data(t["lim_m09b"], t["lim_m09b_data"], t["sep"].join(m09b)))
        threshold = float(self.method["neurogrid"]["thresholds"]["CORE-M08-01"])
        top = self.levels[-1]
        first_channels = Condition("channels", LEVELS[0])
        saturated = t["sep"].join(
            t["of_plain"].format(
                name=name,
                n=self.summary[name, first_channels.id][f"recordings_q{top}"],
                total=self.summary[name, first_channels.id]["n_recordings"],
            )
            for name in self.datasets
            if (name, first_channels.id) in self.summary
        )
        lines.append(
            self._with_data(
                t["lim_saturation"].format(threshold=_num(threshold), ratio=_num(1.0 / threshold), top=top),
                t["lim_saturation_data"].replace("{top}", str(top)),
                saturated,
            )
        )
        lines_hz = sorted(
            {float(self.method["datasets"][name]["line_frequency_hz"]) for name in self.datasets}
        )
        decoders = self.method["decoders"]
        line_text = t["lim_line"].format(
            mi_band=_range(decoders["mi_band_csp_hz"]),
            eegnet_band=_range(decoders["eegnet_band_hz"]),
            lines=self.t["inner"].join(_num(v) for v in lines_hz),
        )
        line_item = self._with_data(line_text, t["lim_line_data"], self._accuracy_change("line_noise"))
        phase = PHASE_LOCKED_LINE_NOISE if PHASE_LOCKED_LINE_NOISE in self.datasets else None
        if phase and self._highest("line_noise") is not None:
            lines.append(f"{line_item}{t['space']}{t['lim_line_except'].format(name=phase)}")
            lines.append(self._phase_item(phase))
        else:
            lines.append(line_item)
        lines.append(t["lim_equality"])
        if "Cho2017" in clean:
            median = clean["Cho2017"]["median_ratio_CORE-M09-01"]
            lines.append(t["lim_cho"].format(median=_ratio(float(median)) if median else DASH))
        if "Kalunga2016" in self.datasets:
            trials = sorted(
                r.n_trials for r in self._rows("Kalunga2016", self._first_condition(), self.decoders[0])
            )
            if trials:
                folds = int(self.method["evaluation"]["n_folds"])
                lines.append(
                    t["lim_kalunga"].format(
                        trials=_span(trials),
                        test=f"{statistics.median(trials) / folds:.1f}",
                        step=f"{100.0 / trials[0]:.1f}",
                    )
                )
        counts = {name: int(self.method["datasets"][name]["n_eeg_channels"]) for name in self.datasets}
        channels = t["inner"].join(
            t["count_channels"].format(name=name, n=n)
            for name, n in counts.items()
            if n < max(counts.values())
        )
        lines.append(self._with_data(t["lim_design"], t["lim_design_channels"], channels))
        return [*lines, ""]

    def _counts(self, row: Mapping[str, str], prefix: str) -> str:
        found = [(int(row[f"{prefix}{rule}"]), index, rule) for index, rule in enumerate(RULE_IDS)]
        chosen = sorted((item for item in found if item[0] > 0), key=lambda item: (-item[0], item[1]))
        if not chosen:
            return self.t["none"]
        return self.t["inner"].join(
            self.t["item"].format(label=self._rule(rule), n=n) for n, _, rule in chosen
        )

    def _with_data(self, text: str, template: str, values: str) -> str:
        return f"{text}{self.t['space']}{template.format(values=values)}" if values else text

    def _change(self, kind: str, clean: Mapping[str, Mapping[str, str]]) -> str:
        """Median M09a ratio, clean and at the highest level of ``kind`` in the run, per dataset."""
        highest = self._highest(kind)
        if highest is None:
            return ""
        parts = []
        for name, row in clean.items():
            high = self.summary.get((name, highest.id))
            if high is None:
                continue
            low_value, high_value = row["median_ratio_CORE-M09-01"], high["median_ratio_CORE-M09-01"]
            parts.append(
                self.t["change"].format(
                    name=name,
                    clean=_ratio(float(low_value)) if low_value else DASH,
                    high=_ratio(float(high_value)) if high_value else DASH,
                    condition=self._condition(highest),
                )
            )
        return self.t["sep"].join(parts)

    def _phase_item(self, name: str) -> str:
        """The finding A-111 for ``name``: its mean accuracy per decoder along the line-noise ladder
        (curve.csv, degradation axis) and the EEGNet pairs at the top level of the main curve with and
        without the pairs of that ladder (sessions.csv)."""
        t = self.t
        top = self.levels[-1]
        ladder = sorted(c.level for c in self.conditions if c.kind == "line_noise")
        points = {
            (p.decoder, p.x): p
            for p in self.data.curve
            if p.dataset == name and p.axis == "degradation" and p.kind == "line_noise"
        }
        values = t["sep"].join(
            t["named"].format(
                name=self._decoder(decoder),
                items=" \N{RIGHTWARDS ARROW} ".join(
                    _percent(points[decoder, x].mean_accuracy) if (decoder, x) in points else DASH
                    for x in (0, *ladder)
                ),
            )
            for decoder in self.decoders
        )
        text = self._with_data(
            t["lim_phase"].replace("{name}", name).replace("{top}", str(top)),
            t["lim_phase_data"].replace("{name}", name).replace("{levels}", _span(ladder)),
            values,
        )
        pairs = [row for row in self._rows(name, decoder="eegnet") if row.quality_level == top]
        line_pairs = [row for row in pairs if row.kind == "line_noise"]
        rest = [row for row in pairs if row.kind != "line_noise"]
        if line_pairs and rest:
            text += t["space"] + t["lim_phase_top"].format(
                name=name,
                top=top,
                all=_percent(statistics.fmean(row.accuracy for row in pairs)),
                n=len(pairs),
                n_line=len(line_pairs),
                rest=_percent(statistics.fmean(row.accuracy for row in rest)),
                n_rest=len(rest),
            )
        return text

    def _accuracy_change(self, kind: str) -> str:
        """Mean accuracy, clean (x = 0) and at the highest level of ``kind`` in the run, per dataset and
        decoder (curve.csv, degradation axis)."""
        highest = self._highest(kind)
        if highest is None:
            return ""
        points = {
            (p.dataset, p.decoder, p.x): p
            for p in self.data.curve
            if p.axis == "degradation" and p.kind == kind
        }
        parts = []
        for name in self.datasets:
            for decoder in self.decoders:
                low, high = points.get((name, decoder, 0)), points.get((name, decoder, highest.level))
                if low is None or high is None:
                    continue
                parts.append(
                    self.t["change_decoder"].format(
                        name=name,
                        decoder=self._decoder(decoder),
                        clean=_percent(low.mean_accuracy),
                        high=_percent(high.mean_accuracy),
                        condition=self._condition(highest),
                    )
                )
        return self.t["sep"].join(parts)


def _table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    def line(cells: Sequence[str]) -> str:
        return "| " + " | ".join(str(cell).replace("|", "\\|") for cell in cells) + " |"

    return [line(header), "|" + "|".join("---" for _ in header) + "|", *(line(row) for row in rows)]


def _num(value: Any) -> str:
    """A constant as text: integers without a decimal point, other floats by repr; None as a dash."""
    if value is None:
        return DASH
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e15:
        return str(int(value))
    return str(value) if isinstance(value, int | str) else repr(value)


def _signed(value: float) -> str:
    return f"+{_num(value)}" if value > 0 else _num(value)


def _range(values: Sequence[float]) -> str:
    return f"{_num(values[0])}{DASH}{_num(values[1])}"


def _share(value: float) -> str:
    """A fraction as a percentage without trailing zeros (0.2 -> 20%, 0.95 -> 95%)."""
    return f"{_num(round(value * 100, 6))}%"


def _power(value: float) -> str:
    """Powers of ten from 1000 up as 10^k, other values as ``_num``."""
    if value >= 1000:
        exponent = round(math.log10(value))
        if 10**exponent == value:
            return f"10^{exponent}"
    return _num(value)


def _percent(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return DASH
    return f"{value * 100:.1f}%"


def _ratio(value: float) -> str:
    return f"{value:.2f}" if math.isfinite(value) else DASH


def _span(values: Sequence[int]) -> str:
    if not values:
        return DASH
    low, high = min(values), max(values)
    return str(low) if low == high else f"{low}{DASH}{high}"


def _point(point: records.CurvePoint | None) -> str:
    """``72.3% [68.1–76.4] (12)``; without an interval (one pair) ``72.3% (1)``; a dash for no point."""
    if point is None:
        return DASH
    text = _percent(point.mean_accuracy)
    if math.isfinite(point.ci_low) and math.isfinite(point.ci_high):
        text += f" [{point.ci_low * 100:.1f}{DASH}{point.ci_high * 100:.1f}]"
    return f"{text} ({point.n_sessions})"


# --- command line ------------------------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    """The command line of the module docstring."""
    parser = argparse.ArgumentParser(prog="python -m neuroarena.report", description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    publishing = commands.add_parser("publish", help="write results/ from the two final runs")
    publishing.add_argument("run_a", metavar="RUN_A", help="the reported run (folder or run id)")
    publishing.add_argument("run_b", metavar="RUN_B", help="its repetition (folder or run id)")
    publishing.add_argument(
        "--eegnet-tolerance",
        action="store_true",
        help="compare EEGNet with the relaxed tolerance of F3 (1 trial per fold, 0.5 points per cell)",
    )
    publishing.add_argument("--results", type=Path, default=paths.RESULTS)
    rendering = commands.add_parser("render", help="write report/en and report/zh from results/")
    rendering.add_argument("--results", type=Path, default=paths.RESULTS)
    rendering.add_argument("--report-en", type=Path, default=paths.REPORT_EN)
    rendering.add_argument("--report-zh", type=Path, default=paths.REPORT_ZH)
    try:
        args = parser.parse_args(argv)
    except SystemExit as stop:
        return int(stop.code or 0)
    try:
        if args.command == "publish":
            tolerance = compare.EegnetTolerance() if args.eegnet_tolerance else None
            runs = [_run_folder(args.run_a), _run_folder(args.run_b)]
            publication = publish(runs, args.results, eegnet_tolerance=tolerance)
            ok = publication.comparison.ok
            print(f"published {len(publication.files)} files; the runs are {'equal' if ok else 'different'}")
            return 0 if ok else 1
        written = render(args.results, args.report_en, args.report_zh)
        ok = bool(load_results(args.results).comparison["ok"])
        print(f"rendered {len(written)} reports; run_compare.json: {'equal' if ok else 'different'}")
        return 0 if ok else 1
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


def _run_folder(text: str) -> Path:
    candidate = Path(text)
    return candidate if candidate.is_dir() else paths.run_dir(text)


if __name__ == "__main__":
    raise SystemExit(main())
