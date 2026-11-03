"""Complete run folders without any computation for the tests of area D (report): run.json, every NeuroGrid
file of every dataset and condition, the folds, sessions.csv and curve.csv, all with the frozen formats and
area B's and C's own writers (``quality.recording_quality``, ``records.write_csv``, ``runner.curve_points``).
The values are chosen so that the report has something to say about every limitation: clean Zhou2016 at Q4
(M06), clean Cho2017 at Q5 (M09a), M09b not measurable on Zhou2016, a flat channel at Q5, one Kalunga2016
session without a level."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from neuroarena import export, neurogrid_cli, paths, quality, records, runner
from neuroarena.datasets import DATASETS
from neuroarena.keys import Condition, RecordingKey, SessionKey

DATASET_NAMES = ("Zhou2016", "Cho2017", "Kalunga2016")
CONDITION_IDS = ("clean", "line_noise-5", "channels-1", "artifacts-5")
SUBJECTS = (1, 2)
# dataset -> (sessions, runs per session, test trials per fold)
LAYOUT = {
    "Zhou2016": (("0", "1"), ("0",), 9),
    "Cho2017": (("0",), ("0",), 20),
    "Kalunga2016": (("0",), ("0", "1"), 4),
}
CHANNELS = ("C3", "Cz", "C4")
NEUROGRID_VERSION = "9.9.9"
THRESHOLDS = {
    "CORE-M06-01": ("max_fraction", 0.30625),
    "CORE-M07-01": ("max_ratio", 0.407669),
    "CORE-M08-01": ("max_fraction", 0.05),
    "CORE-M08-02": ("max_fraction", 0.05),
    "CORE-M09-01": ("max_fraction", 0.305083),
    "CORE-M09-02": ("max_fraction", 0.6),
}


def metrics(dataset: str, condition: Condition, key: RecordingKey) -> dict[str, Any]:
    """NeuroGrid's metrics of one fake recording (results.json form)."""
    if dataset == "Kalunga2016" and condition.id == "artifacts-5" and key.subject == 2:
        return {"state": "not_checkable", "reason": "quality.too_short"}  # no level for this session
    m06 = {"Zhou2016": 0.35, "Cho2017": 0.05, "Kalunga2016": 0.1}[dataset]
    m09a = {"Zhou2016": 0.05, "Cho2017": 0.5, "Kalunga2016": 0.02}[dataset]
    ratio, flat = 0.01, 0.0
    if condition.kind == "line_noise":
        ratio = 0.9
    elif condition.kind == "channels":
        flat = 1.0
    elif condition.kind == "artifacts":
        m09a += 0.3
    channels = {
        name: {"ratio": ratio, "flat_fraction": flat if index == 0 else 0.0, "clipped_fraction": 0.0}
        for index, name in enumerate(CHANNELS)
    }
    result: dict[str, Any] = {
        "M06": {"state": "measured", "value": m06},
        "M07": {"channels": {name: {"ratio": values["ratio"]} for name, values in channels.items()}},
        "M08": {
            "channels": {
                name: {"flat_fraction": v["flat_fraction"], "clipped_fraction": v["clipped_fraction"]}
                for name, v in channels.items()
            }
        },
        "M09a": {"state": "measured", "value": m09a},
    }
    if dataset == "Zhou2016":
        result["M09b"] = {"state": "not_checkable", "reason": "quality.too_few_channels"}
    else:
        result["M09b"] = {"state": "measured", "value": 0.3}
    return result


def correct(
    dataset: str, condition: Condition, decoder: str, subject: int, session: str, fold: int, n: int
) -> int:
    """Deterministic correct test trials of one fold (lower for degraded data, EEGNet a little lower)."""
    base = n - 1 - (condition.level // 2) - (1 if decoder == "eegnet" else 0)
    return max(0, min(n, base - (subject + fold + len(session)) % 3))


def make_run(
    base: Path,
    run_id: str,
    mode: str = "full",
    eegnet_offset: int = 0,
    conditions: tuple[str, ...] = CONDITION_IDS,
    subjects: dict[str, tuple[int, ...]] | None = None,
) -> Path:
    """A complete run folder ``base/<run_id>`` of DATASET_NAMES x ``conditions`` x both decoders with
    ``subjects`` per dataset (default SUBJECTS for each). ``eegnet_offset`` changes n_correct of the first
    EEGNet fold (another run in value)."""
    config = runner.RunConfig(run_id=run_id, mode=mode, datasets=DATASET_NAMES, conditions=conditions)
    subjects = subjects or {name: SUBJECTS for name in DATASET_NAMES}
    folder = paths.run_dir(run_id, base)
    document = runner._document(config, subjects)
    document["attempts"] = [{"started": run_id, "finished": run_id}]
    runner._write_json(folder / paths.RUN_FILE, document)
    session_rows = []
    for dataset in DATASET_NAMES:
        spec = DATASETS[dataset]
        sessions, runs, n_test = LAYOUT[dataset]
        for condition_id in conditions:
            condition = Condition.from_id(condition_id)
            out = paths.neurogrid_dir(run_id, dataset, condition_id, base)
            out.mkdir(parents=True)
            neurogrid_cli.write_config(spec, out / paths.CONFIG_FILE)
            index = {
                export.recording_filename(key): key
                for subject in subjects[dataset]
                for session in sessions
                for run in runs
                for key in (RecordingKey(dataset, subject, session, run),)
            }
            export.write_index(index, out)
            results = {
                "tool": {"name": "neurogrid", "version": NEUROGRID_VERSION},
                "config": {
                    "as_of": run_id,
                    "seed": 20261011,
                    "sampling": {"mode": "sample", "segment_s": 60.0, "segments": 10},
                    "effective_settings": {
                        "quality": {
                            "min_channels": spec.n_eeg_channels,
                            "min_seconds": 60.0,
                            "plateau_samples": 10,
                        }
                    },
                    "effective_params": {
                        rule: {parameter: {"origin": "rulepack", "value": value}}
                        for rule, (parameter, value) in THRESHOLDS.items()
                    },
                },
                "environment": {"host": run_id},
                "recordings": [
                    {"id": name, "format": "FIF", "metrics": metrics(dataset, condition, key)}
                    for name, key in sorted(index.items())
                ],
            }
            runner._write_json(out / paths.RESULTS_FILE, results)
            levels = quality.recording_quality(results, index)
            assessed = quality.ConditionQuality(dataset, condition, levels, quality.session_quality(levels))
            quality.write_quality(assessed, out / paths.QUALITY_FILE)
            for decoder in config.decoders:
                folds = []
                for subject in subjects[dataset]:
                    for session in sessions:
                        for fold in range(5):
                            n = correct(dataset, condition, decoder, subject, session, fold, n_test)
                            if decoder == "eegnet" and subject == 1 and fold == 0 and session == sessions[0]:
                                n = max(0, n - eegnet_offset)
                            folds.append(
                                records.FoldRecord(
                                    dataset=dataset,
                                    condition=condition_id,
                                    kind=condition.kind,
                                    level=condition.level,
                                    subject=subject,
                                    session=session,
                                    decoder=decoder,
                                    fold=fold,
                                    seed=1000 + fold,
                                    n_train=4 * n_test,
                                    n_test=n_test,
                                    n_correct=n,
                                    accuracy=n / n_test,
                                    fit_seconds=0.5,
                                )
                            )
                records.write_csv(folds, paths.folds_file(run_id, dataset, condition_id, decoder, base))
                for subject in subjects[dataset]:
                    for session in sessions:
                        own = [f for f in folds if f.subject == subject and f.session == session]
                        level = assessed.sessions[SessionKey(dataset, subject, session)]
                        session_rows.append(
                            records.SessionRecord(
                                dataset=dataset,
                                paradigm=spec.paradigm,
                                condition=condition_id,
                                kind=condition.kind,
                                level=condition.level,
                                subject=subject,
                                session=session,
                                decoder=decoder,
                                n_trials=sum(f.n_test for f in own),
                                accuracy=sum(f.n_correct for f in own) / sum(f.n_test for f in own),
                                chance=1.0 / len(spec.events),
                                quality_level=level.level,
                                runs_without_level=level.runs_without_level,
                            )
                        )
    records.write_csv(session_rows, folder / paths.SESSIONS_FILE)
    records.write_csv(runner.curve_points(session_rows), folder / paths.CURVE_FILE)
    return folder
