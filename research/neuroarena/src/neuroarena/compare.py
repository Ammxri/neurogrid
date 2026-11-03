"""Comparison of two runs with the documented tolerance (DoD P11 "the notebook runs twice with equal numbers",
F3, A-106; area C "decoders and evaluation").

Exactly equal: the quality levels (quality.json), NeuroGrid's values (``recordings[].metrics`` of every
results.json, without the run-specific blocks such as ``environment`` and ``config.as_of``) and every CSP+LDA
fold. EEGNet: every fold exactly equal on the same machine; only if the pilot shows deviations does the
relaxed tolerance apply, at most 1 test trial per fold and at most 0.5 percentage points in the mean of a cell
(dataset x condition x decoder) - the report states which one was used (F3). No equality across machines is
claimed. ``fit_seconds`` and the times in run.json are never compared.

Command line (DoD 1; its output is committed as results/run_compare.json by area D)::

    python -m neuroarena.compare RUN_A RUN_B [--eegnet-tolerance] [--out FILE]

Exit 0: equal within the tolerance; 1: not; 2: usage error or a run folder that is incomplete.

What is compared, per dataset, condition and decoder of the (equal) configuration: quality.json as a whole,
the ``metrics`` of every recording of results.json (matched by ``recordings[].id``) and every row of
folds/<dataset>/<condition>/<decoder>.csv (matched by ``records.FOLD_KEY``; every column but
``fit_seconds``). Values compare by type and value, NaN equal to NaN. Under the tolerance an EEGNet fold may
differ in ``n_correct`` (and so ``accuracy``) by at most ``max_trials_per_fold``; such differences are listed
with "(within tolerance)" in ``where`` and keep ``ok``. The mean of a cell is the mean of its session
accuracies (sum of n_correct / sum of n_test per session), computed exactly. A file or row present in one
run only is a difference of type "missing".
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from neuroarena import paths, records, runner

COMPARISON_VERSION = 1


@dataclass(frozen=True)
class EegnetTolerance:
    """The relaxed tolerance of F3 for EEGNet."""

    max_trials_per_fold: int = 1
    max_mean_points_per_cell: float = 0.5  # percentage points


@dataclass(frozen=True)
class Difference:
    what: str  # "quality" | "neurogrid" | "fold" | "cell" | "missing"
    where: str  # file and key, e.g. "folds/Zhou2016/clean/eegnet.csv subject=1 session=0 fold=3"
    a: str
    b: str


@dataclass(frozen=True)
class Comparison:
    ok: bool  # equal within the applied tolerance
    exact: bool  # everything exactly equal
    tolerance: EegnetTolerance | None  # None: exact for EEGNet as well
    compared: Mapping[str, int]  # what -> number of items compared
    differences: tuple[Difference, ...]  # sorted by (what, where)
    # The run ids (run A, run B) as area D publishes the comparison (report.publish); compare_runs and the
    # command line leave it empty.
    runs: tuple[str, str] | tuple[()] = ()


def compare_runs(a: Path, b: Path, eegnet_tolerance: EegnetTolerance | None = None) -> Comparison:
    """Compare the run folders ``a`` and ``b`` (same configuration in run.json, else ValueError).

    ``compared`` counts the quality.json files ("quality"), the recordings whose metrics were compared
    ("neurogrid"), the fold rows ("fold") and, under the tolerance, the EEGNet cells ("cell")."""
    document_a, document_b = _run_document(a), _run_document(b)
    if runner.configuration(document_a) != runner.configuration(document_b):
        raise ValueError("the runs have different configurations (run.json); they cannot be compared")
    config = document_a["config"]
    found: list[tuple[Difference, bool]] = []  # (difference, fatal)
    compared = {"quality": 0, "neurogrid": 0, "fold": 0}
    if eegnet_tolerance is not None:
        compared["cell"] = 0
    for dataset in config["datasets"]:
        for condition in config["conditions"]:
            neurogrid = Path("neurogrid") / dataset / condition
            name = (neurogrid / paths.QUALITY_FILE).as_posix()
            pair = _pair(a, b, name, _read_json, found)
            if pair is not None:
                compared["quality"] += 1
                found.extend((d, True) for d in _json_differences("quality", name, *pair))
            name = (neurogrid / paths.RESULTS_FILE).as_posix()
            pair = _pair(a, b, name, _read_json, found)
            if pair is not None:
                compared["neurogrid"] += _compare_metrics(name, *pair, found)
            for decoder in config["decoders"]:
                name = f"folds/{dataset}/{condition}/{decoder}.csv"
                pair = _pair(a, b, name, records.read_folds, found)
                if pair is not None:
                    tolerance = eegnet_tolerance if decoder == "eegnet" else None
                    compared["fold"] += _compare_folds(name, *pair, tolerance, found)
                    if tolerance is not None:
                        compared["cell"] += 1
                        mean_a, mean_b = _cell_mean(pair[0]), _cell_mean(pair[1])
                        if abs(mean_a - mean_b) * 100 > Fraction(tolerance.max_mean_points_per_cell):
                            found.append(
                                (Difference("cell", name, repr(float(mean_a)), repr(float(mean_b))), True)
                            )
    differences = tuple(sorted((d for d, _ in found), key=lambda d: (d.what, d.where)))
    return Comparison(
        ok=not any(fatal for _, fatal in found),
        exact=not found,
        tolerance=eegnet_tolerance,
        compared=compared,
        differences=differences,
    )


def write_comparison(comparison: Comparison, path: Path) -> Path:
    """JSON (UTF-8, LF, sort_keys, two-space indent) without absolute paths or machine names (the run ids
    only); return ``path``.

    The Comparison holds no paths (``where`` is relative to the run folder) and run ids only in ``runs``
    (empty unless area D set them): the file is ``{"version", "ok", "exact", "tolerance", "compared",
    "differences", "runs"}``."""
    document = {
        "version": COMPARISON_VERSION,
        "ok": comparison.ok,
        "exact": comparison.exact,
        "tolerance": None if comparison.tolerance is None else asdict(comparison.tolerance),
        "compared": dict(comparison.compared),
        "differences": [asdict(difference) for difference in comparison.differences],
        "runs": list(comparison.runs),
    }
    text = json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    return records.write_atomic(path, text.encode("utf-8"))


def main(argv: Sequence[str] | None = None) -> int:
    """The command line above. RUN_A and RUN_B are run folders or run ids under .local/arena/runs."""
    parser = argparse.ArgumentParser(prog="python -m neuroarena.compare", description=__doc__.split("\n")[0])
    parser.add_argument("run_a", metavar="RUN_A")
    parser.add_argument("run_b", metavar="RUN_B")
    parser.add_argument(
        "--eegnet-tolerance",
        action="store_true",
        help="the relaxed EEGNet tolerance of F3 (1 trial per fold, 0.5 points per cell)",
    )
    parser.add_argument("--out", type=Path, default=None, help="write the comparison as JSON")
    try:
        args = parser.parse_args(argv)
    except SystemExit as stop:
        return int(stop.code or 0)
    tolerance = EegnetTolerance() if args.eegnet_tolerance else None
    try:
        comparison = compare_runs(_folder(args.run_a), _folder(args.run_b), tolerance)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.out is not None:
        write_comparison(comparison, args.out)
    counts = ", ".join(f"{count} {what}" for what, count in sorted(comparison.compared.items()))
    if comparison.exact:
        verdict = "exactly equal"
    elif comparison.ok:
        verdict = "equal within the EEGNet tolerance"
    else:
        verdict = f"different ({len(comparison.differences)} differences)"
    print(f"{verdict}; compared {counts}")
    for difference in comparison.differences[:20]:
        print(f"  {difference.what}: {difference.where}: {difference.a} != {difference.b}")
    if any(difference.what == "missing" for difference in comparison.differences):
        return 2
    return 0 if comparison.ok else 1


def _folder(text: str) -> Path:
    candidate = Path(text)
    return candidate if candidate.is_dir() else paths.run_dir(text)


def _run_document(folder: Path) -> dict[str, Any]:
    run_file = folder / paths.RUN_FILE
    if not run_file.is_file():
        raise ValueError(f"no {paths.RUN_FILE} in run folder {folder.name!r}")
    return json.loads(run_file.read_text(encoding="utf-8"))


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _pair(
    a: Path, b: Path, name: str, read: Any, found: list[tuple[Difference, bool]]
) -> tuple[Any, Any] | None:
    present_a, present_b = (a / name).is_file(), (b / name).is_file()
    if not (present_a and present_b):
        state = {True: "present", False: "missing"}
        found.append((Difference("missing", name, state[present_a], state[present_b]), True))
        return None
    return read(a / name), read(b / name)


def _same(a: Any, b: Any) -> bool:
    if type(a) is not type(b):
        return False
    if isinstance(a, float) and math.isnan(a) and math.isnan(b):
        return True
    return a == b


def _json_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _json_differences(what: str, where: str, a: Any, b: Any, path: str = "$") -> list[Difference]:
    if isinstance(a, dict) and isinstance(b, dict):
        result = []
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                result.append(
                    Difference(
                        what,
                        f"{where} {path}.{key}",
                        _json_text(a[key]) if key in a else "missing",
                        _json_text(b[key]) if key in b else "missing",
                    )
                )
            else:
                result.extend(_json_differences(what, where, a[key], b[key], f"{path}.{key}"))
        return result
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [Difference(what, f"{where} {path}", f"{len(a)} items", f"{len(b)} items")]
        result = []
        for index, (item_a, item_b) in enumerate(zip(a, b, strict=True)):
            result.extend(_json_differences(what, where, item_a, item_b, f"{path}[{index}]"))
        return result
    if _same(a, b):
        return []
    return [Difference(what, f"{where} {path}", _json_text(a), _json_text(b))]


def _compare_metrics(name: str, a: Mapping[str, Any], b: Mapping[str, Any], found: list) -> int:
    """The metrics of every recording (by id); returns the number of recordings compared."""
    metrics_a = {item["id"]: item.get("metrics") for item in a.get("recordings", [])}
    metrics_b = {item["id"]: item.get("metrics") for item in b.get("recordings", [])}
    count = 0
    for identifier in sorted(set(metrics_a) | set(metrics_b)):
        where = f"{name} recording={identifier}"
        if identifier not in metrics_a or identifier not in metrics_b:
            state = ("present", "missing") if identifier in metrics_a else ("missing", "present")
            found.append((Difference("missing", where, *state), True))
            continue
        count += 1
        differences = _json_differences("neurogrid", where, metrics_a[identifier], metrics_b[identifier])
        found.extend((d, True) for d in differences)
    return count


def _fold_key(row: records.FoldRecord) -> tuple[Any, ...]:
    return tuple(getattr(row, column) for column in records.FOLD_KEY)


def _compare_folds(
    name: str,
    a: Sequence[records.FoldRecord],
    b: Sequence[records.FoldRecord],
    tolerance: EegnetTolerance | None,
    found: list,
) -> int:
    """Every fold row (by key, every column but fit_seconds); returns the number of rows compared."""
    rows_a = {_fold_key(row): row for row in a}
    rows_b = {_fold_key(row): row for row in b}
    columns = [column for column in records.FOLD_COLUMNS if column != "fit_seconds"]
    count = 0
    for key in sorted(set(rows_a) | set(rows_b)):
        where = f"{name} subject={key[2]} session={key[3]} fold={key[5]}"
        if key not in rows_a or key not in rows_b:
            state = ("present", "missing") if key in rows_a else ("missing", "present")
            found.append((Difference("missing", where, *state), True))
            continue
        count += 1
        row_a, row_b = rows_a[key], rows_b[key]
        changed = [c for c in columns if not _same(getattr(row_a, c), getattr(row_b, c))]
        if not changed:
            continue
        tolerated = (
            tolerance is not None
            and set(changed) <= {"n_correct", "accuracy"}
            and abs(row_a.n_correct - row_b.n_correct) <= tolerance.max_trials_per_fold
        )
        suffix = " (within tolerance)" if tolerated else ""
        for column in changed:
            difference = Difference(
                "fold",
                f"{where} field={column}{suffix}",
                repr(getattr(row_a, column)),
                repr(getattr(row_b, column)),
            )
            found.append((difference, not tolerated))
    return count


def _cell_mean(rows: Sequence[records.FoldRecord]) -> Fraction:
    """The exact mean of the session accuracies of a cell (sum of n_correct / sum of n_test per session)."""
    sessions: dict[tuple[int, str], list[int]] = {}
    for row in rows:
        totals = sessions.setdefault((row.subject, row.session), [0, 0])
        totals[0] += row.n_correct
        totals[1] += row.n_test
    if not sessions:
        return Fraction(0)
    return sum((Fraction(correct, test) for correct, test in sessions.values()), Fraction(0)) / len(sessions)


if __name__ == "__main__":
    raise SystemExit(main())
