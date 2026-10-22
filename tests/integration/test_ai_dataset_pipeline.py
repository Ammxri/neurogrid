"""M11/M12 end to end (NG-F09, M11, M12; A-04, A-21, A-51, A-81; KONZEPT DoD P4): a subject in train and test
is an error, duplicates are found via the signal hash, splits.tsv is a control file (exit 2), demography
and labels leave the process only aggregated, and hashes and raw ages never leave it at all. Class labels
also come from the M10 annotations (A-80), hypnograms counting in the split of their signal recording (C10).

Most runs use a rule pack with only the four M11/M12 checks (``aionly``), so that the exit code shows their
verdict alone; the core rules are covered by tests/rules.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path, PurePosixPath

import jsonschema
import pytest

from gen_fixtures import write_annotation_edf, write_edf  # type: ignore[import-not-found]
from neurogrid import pipeline
from neurogrid.checks.context import CheckContext
from neurogrid.cli import main
from neurogrid.config import Config
from neurogrid.io.discover import pseudonym, scan
from neurogrid.io.identifying import display_text
from neurogrid.kernel import canonical
from neurogrid.kernel.errors import ConfigError, InputError
from neurogrid.kernel.findings import Light, Severity, Status
from neurogrid.model.results import Results
from neurogrid.report.render import render_report

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"
SCHEMA = json.loads(
    (Path(__file__).parents[2] / "src" / "neurogrid" / "schemas" / "results.schema.json").read_text(
        encoding="utf-8"
    )
)
AS_OF = date(2026, 10, 11)
LABELS = '[ai]\nlabels = "events:trial_type"\n'
AI_PACK = """rulepack: aionly
version: "1.0"
source: "M11/M12 checks of the core pack (test)"
source_status: final
rules:
  - id: AI-PROC-001
    clause: M11
    title_zh: 类别占比
    title_en: Class share
    phase: processing
    check: ai.class_balance
    severity: warning
    verification: automatic
  - id: AI-PROC-002
    clause: M11
    title_zh: 年龄和性别已记录
    title_en: Age and sex documented
    phase: processing
    check: ai.demographics_complete
    severity: warning
    verification: automatic
  - id: AI-PROC-003
    clause: M12
    title_zh: 受试者只属于一个数据划分
    title_en: Subject in one split only
    phase: processing
    check: ai.split_integrity
    severity: error
    verification: automatic
  - id: AI-PROC-004
    clause: M12
    title_zh: 无重复记录
    title_en: No duplicate recordings
    phase: processing
    check: ai.duplicate_recordings
    severity: error
    verification: automatic
"""
CLASSES, DEMOGRAPHY, SPLITS, DUPLICATES = "AI-PROC-001", "AI-PROC-002", "AI-PROC-003", "AI-PROC-004"


def ai_config(folder: Path, extra: str = "", rules: tuple[str, ...] = ()) -> Path:
    """A neurogrid.toml in ``folder`` that loads only the M11/M12 checks (all four, or the ``rules`` IDs)."""
    pack = AI_PACK
    if rules:
        head, *entries = AI_PACK.split("  - id: ")
        pack = head + "".join(f"  - id: {entry}" for entry in entries if entry.split("\n")[0] in rules)
    (folder / "aionly.yaml").write_text(pack, encoding="utf-8")
    config = folder / "neurogrid.toml"
    config.write_text('[check]\nrulepacks = ["aionly.yaml"]\n' + extra, encoding="utf-8")
    return config


def run(target: Path, config: Path, **options: object) -> Results:
    return pipeline.run_check(target, pipeline.CheckOptions(config_path=config, as_of=AS_OF, **options))  # type: ignore[arg-type]


def findings(results: Results, rule: str) -> list[tuple[str, str | None, Status, str | None]]:
    return sorted((f.object, f.subkey, f.status, f.reason) for f in results.findings if f.rule_id == rule)


def copy_fixture(name: str, tmp_path: Path) -> Path:
    folder = tmp_path / name
    shutil.copytree(FIX / name, folder)
    return folder


def write_splits(folder: Path, rows: list[tuple[str, str]]) -> None:
    lines = ["recording\tsplit", *(f"{recording}\t{split}" for recording, split in rows)]
    (folder / ".neurogrid").mkdir(exist_ok=True)
    (folder / ".neurogrid" / "splits.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_path(sub: str, run: int = 1) -> str:
    return f"sub-{sub}/eeg/sub-{sub}_task-rest_run-{run}_eeg.edf"


DISJOINT = [
    (run_path("01", 1), "train"),
    (run_path("01", 2), "train"),
    (run_path("02"), "train"),
    (run_path("03"), "train"),
    (run_path("04"), "train"),
    (run_path("05"), "val"),
    (run_path("06"), "test"),
]


# --- CORE-M12-01: a subject in more than one split (NG-F09 acceptance, A-21) -------------------------------


@pytest.mark.parametrize(
    "splits", [("train", "test"), ("train", "val"), ("val", "test"), ("train", "val", "test")]
)
def test_subject_in_more_than_one_split_is_an_error(tmp_path: Path, splits: tuple[str, ...]) -> None:
    folder = copy_fixture("bids_ai_ok", tmp_path)
    rows = [row for row in DISJOINT if not row[0].startswith("sub-01/")]
    rows += [(run_path("01", 1), splits[0]), (run_path("01", 2), splits[1])]
    rows += [(run_path("01", 2), split) for split in splits[2:]]  # a recording may be listed twice
    write_splits(folder, rows)
    results = run(folder, ai_config(tmp_path))
    failed = [f for f in results.findings if f.rule_id == SPLITS]
    assert [(f.object, f.status, f.measured_value) for f in failed] == [
        ("sub-01", Status.FAILED, list(splits))
    ]
    assert set(failed[0].details["split_recordings"]) == set(splits)
    assert results.summary.exit_code == 1


def test_subject_disjoint_splits_pass(tmp_path: Path) -> None:
    results = run(FIX / "bids_ai_ok", ai_config(tmp_path, LABELS))
    assert not results.findings and results.summary.exit_code == 0
    assert {p.object for p in results.passed if p.rule_id == SPLITS} == {f"sub-0{n}" for n in range(1, 7)}
    assert results.ai is not None and results.ai.splits is not None
    assert results.ai.splits.source == "splits.tsv"
    assert results.ai.splits.recordings == {"train": 5, "val": 1, "test": 1}
    assert (
        results.ai.splits.subjects == {"train": 4, "val": 1, "test": 1} and results.ai.splits.unassigned == 0
    )
    assert results.summary.phases["processing"].light.value == "green"


def test_splits_from_the_participants_split_column(tmp_path: Path) -> None:
    folder = copy_fixture("bids_ai_ok", tmp_path)
    (folder / ".neurogrid" / "splits.tsv").unlink()
    table = folder / "participants.tsv"
    rows = ["participant_id\tage\tsex\tsplit"] + [f"sub-0{n}\t30\tF\ttrain" for n in range(1, 5)]
    table.write_text("\n".join([*rows, "sub-05\t30\tF\tval", "sub-06\t30\tF\ttest"]) + "\n", encoding="utf-8")
    config = ai_config(tmp_path)
    clean = run(folder, config)
    assert not findings(clean, SPLITS) and clean.ai is not None and clean.ai.splits is not None
    assert clean.ai.splits.source == "participants.tsv" and clean.ai.splits.subjects["train"] == 4
    with table.open("a", encoding="utf-8") as handle:  # sub-03 a second time, in test; sub-06 invalid
        handle.write("sub-03\t30\tF\ttest\nsub-06\t30\tF\tvalidation\n")
    leaked = run(folder, config)
    assert findings(leaked, SPLITS) == [("sub-03", None, Status.FAILED, None)]
    invalid = [n for n in leaked.notices if n.message_key == "notice.participants_split_invalid"]
    assert [n.params for n in invalid] == [{"count": 1}] and leaked.summary.exit_code == 1
    write_splits(folder, DISJOINT)  # both sources: splits.tsv wins, with a notice (A-81)
    both = run(folder, config)
    assert not findings(both, SPLITS)
    assert any(n.message_key == "notice.splits_both_sources" for n in both.notices)


def _raw_folder(tmp_path: Path, names: dict[str, int]) -> Path:
    folder = tmp_path / "raw"
    for name, seed in names.items():
        write_edf(folder / name, sfreq=128, seconds=2, labels=("Fp1", "Fp2", "C3", "C4"), seed=seed)
    return folder


def test_raw_folder_splits_with_mapping_and_pseudonymous_ids(tmp_path: Path) -> None:
    folder = _raw_folder(tmp_path, {"s01_r1.edf": 1, "s01_r2.edf": 2, "s02_r1.edf": 3, "s03_r1.edf": 4})
    write_splits(
        folder,
        [
            (pseudonym(Path("s01_r1.edf")), "train"),  # rec-ID without the extension
            (f"{pseudonym(Path('s01_r2.edf'))}.edf", "test"),  # rec-ID with it (A-70)
            ("s02_r1.edf", "val"),  # dataset-relative path
            ("Zhang_San_notes.edf", "train"),  # matches nothing: counted, never shown
        ],
    )
    mapping = "[convert]\npattern = '(?P<subject>s[0-9]+)_(?P<task>r[0-9]+)\\.edf'\n"
    results = run(folder, ai_config(tmp_path, mapping))
    assert findings(results, SPLITS) == [("sub-s01", None, Status.FAILED, None)]
    notices = {n.message_key: n.params for n in results.notices}
    assert notices["notice.splits_unknown_rows"] == {"count": 1}
    assert notices["notice.splits_unassigned"] == {"count": 1}  # s03_r1.edf
    text = canonical.dumps(results).decode("utf-8")
    assert "Zhang" not in text and "s01_r1" not in text  # pseudonymous IDs in raw folders (A-51)
    failed = next(f for f in results.findings if f.rule_id == SPLITS)
    assert failed.details["split_recordings"] == {
        "train": [pseudonym(Path("s01_r1.edf"))],
        "test": [pseudonym(Path("s01_r2.edf"))],
    }
    # without a mapping the subjects are unknown: a recording in two splits still fails, the others cannot
    # be judged (A-21)
    write_splits(folder, [("s01_r1.edf", "train"), ("s01_r1.edf", "test"), ("s02_r1.edf", "val")])
    unmapped = run(folder, ai_config(tmp_path))
    assert set(findings(unmapped, SPLITS)) == {
        (pseudonym(Path("s01_r1.edf")), None, Status.FAILED, None),
        (pseudonym(Path("s02_r1.edf")), None, Status.NOT_CHECKABLE, "ai.subject_unknown"),
    }
    assert findings(unmapped, DEMOGRAPHY) == [("dataset", None, Status.NOT_CHECKABLE, "ai.subjects_unknown")]


def test_hypnograms_are_no_recordings_for_m11_m12(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """C10, critic G1: an unmapped annotation-only file neither makes the subjects unknown nor counts as an
    unassigned recording; its duplicate check is not applicable."""
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "unit"))
    from test_io import _annotation_only_edf  # type: ignore[import-not-found]

    folder = _raw_folder(tmp_path, {"s01_night.edf": 5, "s02_night.edf": 6})
    _annotation_only_edf(folder / "hypnogram_scorer1.edf")
    (folder / "participants.tsv").write_text(
        "participant_id\tage\tsex\ns01\t33\tF\nsub-s02\t47\tM\n", encoding="utf-8"
    )
    write_splits(folder, [("s01_night.edf", "train"), ("s02_night.edf", "test")])
    mapping = "[convert]\npattern = '(?P<subject>s[0-9]+)_(?P<task>night)\\.edf'\n"
    results = run(folder, ai_config(tmp_path, mapping))
    assert findings(results, DEMOGRAPHY) == []  # both subjects documented ("sub-" prefix optional)
    assert not [n for n in results.notices if n.message_key == "notice.splits_unassigned"]
    hypnogram = pseudonym(Path("hypnogram_scorer1.edf"))
    assert findings(results, DUPLICATES) == [
        (hypnogram, None, Status.NOT_APPLICABLE, "recording.annotations_only")
    ]
    (folder / "participants.tsv").unlink()
    missing = run(folder, ai_config(tmp_path, mapping))
    assert {reason for *_rest, reason in findings(missing, DEMOGRAPHY)} == {"ai.no_participants_table"}


# --- splits.tsv is a control file: exit 2, line named, cell text never echoed (C2) --------------------------


def _cli(args: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    with pytest.raises(SystemExit) as info:
        main(args)
    out, err = capsys.readouterr()
    return int(info.value.code or 0), out, err


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("recording\tname\nZhang_San.edf\ttrain\n", "needs exactly one column 'recording'"),
        ("recording\tsplit\nZhang_San.edf\ttesting\n", "line 2: the split must be train, val or test"),
        ("recording\tsplit\n\n../Zhang_San.edf\ttrain\n", "line 3: the recording must be a relative path"),
        ("recording\tsplit\nZhang_San.edf\n", "line 2: the row has no value"),
    ],
)
def test_invalid_splits_file_ends_with_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], content: str, expected: str
) -> None:
    folder = copy_fixture("bids_ai_ok", tmp_path)
    (folder / ".neurogrid" / "splits.tsv").write_text(content, encoding="utf-8")
    code, out, err = _cli(["check", str(folder), "--out", str(tmp_path / "r.json")], capsys)
    assert code == 2 and expected in err
    assert "Zhang" not in out + err and not (tmp_path / "r.json").exists()


def test_configured_splits_file_must_exist(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = ai_config(tmp_path, '[ai]\nsplits = "missing/splits.tsv"\n')
    with pytest.raises(ConfigError) as info:
        run(FIX / "bids_ai_ok", config)
    assert info.value.message_key == "config.splits_not_found"
    args = ["check", str(FIX / "bids_ai_ok"), "--config", str(config), "--out", str(tmp_path / "r.json")]
    code, _out, err = _cli(args, capsys)
    assert code == 2 and "field 'ai.splits' does not exist" in err


def test_configured_splits_file_outside_the_dataset(tmp_path: Path) -> None:
    folder = copy_fixture("bids_ai_ok", tmp_path)
    shutil.move(folder / ".neurogrid" / "splits.tsv", tmp_path / "splits.tsv")
    config = ai_config(tmp_path, '[ai]\nlabels = "events:trial_type"\nsplits = "splits.tsv"\n')
    results = run(folder, config)
    assert not results.findings and results.ai is not None and results.ai.splits is not None
    assert any(n.message_key == "notice.splits_outside_dataset" for n in results.notices)


def test_invalid_splits_in_a_real_process(tmp_path: Path) -> None:
    folder = copy_fixture("bids_ai_ok", tmp_path)
    (folder / ".neurogrid" / "splits.tsv").write_text(
        "recording\tsplit\nsub-01/eeg/Wang_Wu.edf\tholdout\n", encoding="utf-8"
    )
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "neurogrid",
            "--lang",
            "zh",
            "check",
            str(folder),
            "--out",
            str(tmp_path / "r.json"),
        ],
        capture_output=True,
        env=env,
        check=False,
    )
    err = process.stderr.decode("utf-8")
    assert process.returncode == 2 and "第 2 行" in err and "Wang_Wu" not in err and "holdout" not in err


def test_participants_table_problems_are_findings_not_exit_2(tmp_path: Path) -> None:
    folder = copy_fixture("bids_ai_ok", tmp_path)
    (folder / "participants.tsv").write_bytes(b"participant_id\tage\tsex\nsub-01\t\xff\tF\n")
    results = run(folder, ai_config(tmp_path))
    assert {reason for *_rest, reason in findings(results, DEMOGRAPHY)} == {"ai.participants_unusable"}
    assert results.summary.exit_code == 0  # warnings only


# --- CORE-M12-02: duplicates via the signal hash (A-21, A-79) ----------------------------------------------


def _duplicates_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "raw"
    labels = ("Fp1", "Fp2", "C3", "C4")
    write_edf(folder / "session_a.edf", sfreq=128, seconds=2, labels=labels, seed=5)
    # the same samples under another name and with other header fields: the hash sees only the signal
    write_edf(
        folder / "copy_of_a.edf",
        sfreq=128,
        seconds=2,
        labels=labels,
        seed=5,
        recording="Startdate X X X copy",
        label_prefix="",
    )
    write_edf(folder / "other.edf", sfreq=128, seconds=2, labels=labels, seed=6)
    return folder


def test_duplicates_are_found_with_pseudonymous_ids(tmp_path: Path) -> None:
    folder = _duplicates_folder(tmp_path)
    config = ai_config(tmp_path)
    results = run(folder, config)
    copy, original = pseudonym(Path("copy_of_a.edf")), pseudonym(Path("session_a.edf"))
    assert results.duplicates == [[copy, original]]  # ordered by relative path, never the hash
    assert findings(results, DUPLICATES) == sorted(
        [(copy, "1", Status.FAILED, None), (original, "1", Status.FAILED, None)]
    )
    failed = next(f for f in results.findings if f.object == copy)
    assert failed.measured_value == 1 and failed.details["duplicate_of"] == [original]
    assert results.summary.exit_code == 1
    shown = run(folder, config, show_paths=True)
    assert shown.duplicates == [["copy_of_a.edf", "session_a.edf"]]
    assert sorted(f.key for f in shown.findings) == sorted(f.key for f in results.findings)  # A-68
    assert [f.status for f in shown.findings] == [f.status for f in results.findings]


def test_duplicate_check_alone_runs_the_stream_but_not_the_sample(tmp_path: Path) -> None:
    folder = _duplicates_folder(tmp_path)
    results = run(folder, ai_config(tmp_path, rules=(DUPLICATES,)))
    assert len(findings(results, DUPLICATES)) == 2 and results.duplicates is not None
    assert all(rec.sample is None and "M08" in rec.metrics for rec in results.recordings)
    assert results.ai is None  # only the duplicate check ran


def test_signal_hashes_never_leave_the_process(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _duplicates_folder(tmp_path)
    ctx = CheckContext.build(scan(folder), Config())
    ctx.compute_quality(stream=True, sample=False)
    hashes = {rec.quality.stream.signal_hash for rec in ctx.recordings if rec.quality and rec.quality.stream}
    assert len(hashes) == 2 and all(isinstance(h, str) and len(h) == 64 for h in hashes)
    out_file = tmp_path / "results.json"
    code, out, err = _cli(["--debug", "check", str(folder), "--out", str(out_file)], capsys)
    assert code == 1
    report_dir = tmp_path / "report"
    report_code, report_out, report_err = _cli(
        ["report", str(out_file), "--lang", "zh,en", "--out", str(report_dir)], capsys
    )
    assert report_code == 0
    texts = [out, err, report_out, report_err, out_file.read_text(encoding="utf-8")]
    texts += [path.read_text(encoding="utf-8") for path in report_dir.glob("*.html")]
    assert len(texts) == 7
    for digest in hashes:
        assert all(digest not in text and digest[:16] not in text for text in texts)


def test_duplicate_check_states(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "unit"))
    from test_io import _annotation_only_edf  # type: ignore[import-not-found]

    folder = _raw_folder(tmp_path, {"good.edf": 9})
    write_edf(folder / "ecg.edf", sfreq=128, seconds=2, labels=("ECG", "EMG"), label_prefix="", seed=8)
    (folder / "broken.edf").write_bytes(b"0" * 300)
    _annotation_only_edf(folder / "hypnogram.edf")
    results = run(folder, ai_config(tmp_path, rules=(DUPLICATES,)))
    reasons = {obj: (status, reason) for obj, _s, status, reason in findings(results, DUPLICATES)}
    assert reasons == {
        pseudonym(Path("broken.edf")): (Status.NOT_CHECKABLE, "header.unreadable"),
        pseudonym(Path("ecg.edf")): (Status.NOT_CHECKABLE, "signal.no_eeg_channels"),
        pseudonym(Path("hypnogram.edf")): (Status.NOT_APPLICABLE, "recording.annotations_only"),
    }
    assert [p.object for p in results.passed if p.rule_id == DUPLICATES] == [pseudonym(Path("good.edf"))]
    assert results.duplicates == []


# --- CORE-M11-01/02: classes and demography; privacy of the aggregates (A-51) ------------------------------


def test_without_a_label_source_class_balance_is_not_applicable() -> None:
    results = pipeline.run_check(FIX / "bids_ai_issues", pipeline.CheckOptions(as_of=AS_OF))
    assert findings(results, "CORE-M11-01") == [
        ("dataset", None, Status.NOT_APPLICABLE, "ai.labels_not_configured")
    ]
    assert results.ai is not None and results.ai.labels is None and results.ai.splits is not None


def test_event_labels_are_counted_per_scope(tmp_path: Path) -> None:
    results = run(FIX / "bids_ai_issues", ai_config(tmp_path, LABELS))
    failed = {f.subkey: f.measured_value for f in results.findings if f.rule_id == CLASSES}
    assert failed == {
        "all:rare": 0.025,
        "train:rare": pytest.approx(1 / 23),
        "val:rare": 0.0,
        "test:rare": 0.0,
        "test:C": 0.0,  # a class missing from a split has share 0 (A-21)
    }
    rare = next(f for f in results.findings if f.subkey == "all:rare")
    assert rare.details == {"scope": "all", "label": "rare", "unit": "events", "count": 1, "total": 40}
    labels = results.ai.labels if results.ai else None
    assert (
        labels is not None
        and labels.unit == "events"
        and list(labels.scopes) == ["all", "train", "val", "test"]
    )
    assert labels.scopes["all"].classes == {"A": 19, "B": 13, "C": 7, "rare": 1}  # events: not suppressed


@pytest.mark.parametrize(("rare", "failed"), [(4, []), (3, ["all:rare"])])
def test_share_at_the_threshold(tmp_path: Path, rare: int, failed: list[str]) -> None:
    """4 of 80 events = 0.05 passes (at least the minimum share), 3 of 80 does not."""
    folder = copy_fixture("bids_ai_ok", tmp_path)
    (folder / ".neurogrid" / "splits.tsv").unlink()  # the scope "all" only
    events = folder / "sub-01" / "eeg" / "sub-01_task-rest_run-1_events.tsv"
    rows = "".join(f"{i}\t0.1\t{'rare' if i < rare else 'A'}\n" for i in range(20))  # 20 + 6 x 10 events
    events.write_text("onset\tduration\ttrial_type\n" + rows, encoding="utf-8")
    results = run(folder, ai_config(tmp_path, LABELS, rules=(CLASSES,)))
    assert [f.subkey for f in results.findings] == failed


def test_free_text_labels_are_not_shown(tmp_path: Path) -> None:
    folder = copy_fixture("bids_ai_ok", tmp_path)
    events = folder / "sub-02" / "eeg" / "sub-02_task-rest_run-1_events.tsv"
    events.write_text("onset\tduration\ttrial_type\n0\t0.1\tJohn Smith\n", encoding="utf-8")
    results = run(folder, ai_config(tmp_path, LABELS, rules=(CLASSES,)))
    free = [f for f in results.findings if f.subkey and "text-" in f.subkey]
    assert free and all(f.details["label"] is None and f.details["label_chars"] == 10 for f in free)
    assert "John" not in canonical.dumps(results).decode("utf-8")


def test_empty_scope_and_missing_column(tmp_path: Path) -> None:
    folder = copy_fixture("bids_ai_ok", tmp_path)
    events = folder / "sub-06" / "eeg" / "sub-06_task-rest_run-1_events.tsv"
    events.write_text("onset\tduration\ttrial_type\n0\t0.1\tn/a\n", encoding="utf-8")
    results = run(folder, ai_config(tmp_path, LABELS, rules=(CLASSES,)))
    assert findings(results, CLASSES) == [("dataset", "test", Status.NOT_CHECKABLE, "ai.no_label_values")]
    missing = run(folder, ai_config(tmp_path, '[ai]\nlabels = "events:condition"\n', rules=(CLASSES,)))
    assert findings(missing, CLASSES) == [("dataset", None, Status.NOT_CHECKABLE, "ai.label_column_missing")]
    no_column = run(folder, ai_config(tmp_path, '[ai]\nlabels = "participants:group"\n', rules=(CLASSES,)))
    assert findings(no_column, CLASSES) == [
        ("dataset", None, Status.NOT_CHECKABLE, "ai.label_column_missing")
    ]


def test_subject_level_counts_are_suppressed(tmp_path: Path) -> None:
    """A-51/A-81: participants labels count subjects; counts of 1-4 never reach results.json, not even as
    the measured share of a finding."""
    config = ai_config(
        tmp_path, '[ai]\nlabels = "participants:sex"\n[rules."AI-PROC-001".params]\nmin_share = 0.9\n'
    )
    results = run(FIX / "bids_ai_ok", config)
    shares = [f for f in results.findings if f.rule_id == CLASSES]
    assert shares and all(f.status is Status.FAILED for f in shares)  # every share is below 0.9
    for finding in shares:
        assert finding.details["unit"] == "subjects"
        count = finding.details.get("count")
        assert count is None or count == 0 or count >= 5
        if finding.details.get("small_cell"):
            assert finding.measured_value is None and finding.reason == "ai.small_cell"
    assert any(f.details.get("small_cell") for f in shares)
    labels = results.ai.labels if results.ai else None
    assert labels is not None and labels.scopes["all"].classes == {"F": None, "M": None}
    demography = results.ai.demographics if results.ai else None
    assert demography is not None and demography.subjects == 6
    assert set(demography.sex.values()) == {None} and set(demography.age_groups.values()) == {None}


def test_raw_ages_never_leave_the_process(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """bids_ai_ok plants the ages 37.25 and 61.75 (A-21: the raw age is never serialised)."""
    config = tmp_path / "neurogrid.toml"
    config.write_text(LABELS, encoding="utf-8")
    out_file = tmp_path / "results.json"
    code, out, err = _cli(
        ["check", str(FIX / "bids_ai_ok"), "--config", str(config), "--out", str(out_file)], capsys
    )
    assert code in (0, 1)
    report_dir = tmp_path / "report"
    _cli(["report", str(out_file), "--lang", "zh,en", "--out", str(report_dir)], capsys)
    texts = [out, err, out_file.read_text(encoding="utf-8")]
    texts += [path.read_text(encoding="utf-8") for path in report_dir.glob("*.html")]
    assert len(texts) == 5
    for age in ("37.25", "61.75", "37,25"):
        assert all(age not in text for text in texts)
    data = json.loads(texts[2])
    assert data["ai"]["demographics"]["subjects"] == 6


# --- CORE-M11-01 with [ai] labels = "annotations": the M10 reader as label source (A-80, A-81, C10) --------

# [annotation] of the annotation fixtures (tools/gen_fixtures.py): three scorers stage ten 30-s epochs each
SLEEP = (
    '[annotation]\nmode = "continuous"\nepoch_s = 30\n'
    'vocabulary = ["W", "N1", "N2", "N3", "R", "Lights off"]\n'
)
ANNOTATION_LABELS = '[ai]\nlabels = "annotations"\n'


def test_annotation_labels_take_the_split_of_their_signal_recording(tmp_path: Path) -> None:
    """C10: the hypnograms attached to night.edf count as its events and in its split; the splits.tsv row of
    a hypnogram itself is ignored. Every annotation of every scorer is one event, the zero-duration marker
    "Lights off" included: 1 of 31 events, below min_share."""
    folder = copy_fixture("annotation_continuous_ok", tmp_path)
    write_splits(folder, [("night.edf", "train"), ("night_scorer1.edf", "test")])
    results = run(folder, ai_config(tmp_path, SLEEP + ANNOTATION_LABELS, rules=(CLASSES,)))
    labels = results.ai.labels if results.ai else None
    assert labels is not None and (labels.source, labels.column, labels.unit) == (
        "annotations",
        None,
        "events",
    )
    classes = {"Lights off": 1, "N1": 4, "N2": 9, "N3": 6, "R": 4, "W": 7}
    assert {scope: value.classes for scope, value in labels.scopes.items()} == {
        "all": classes,
        "train": classes,
    }
    assert labels.scopes["all"].total == labels.scopes["train"].total == 31
    assert findings(results, CLASSES) == [
        ("dataset", "all:Lights off", Status.FAILED, None),
        ("dataset", "train:Lights off", Status.FAILED, None),
    ]
    marker = next(f for f in results.findings if f.subkey == "all:Lights off")
    assert marker.details == {
        "scope": "all",
        "label": "Lights off",
        "unit": "events",
        "count": 1,
        "total": 31,
    }
    assert [(p.rule_id, p.object, p.count) for p in results.passed] == [(CLASSES, "dataset", 10)]
    keys = {n.message_key for n in results.notices}
    assert not keys & {"notice.splits_unassigned", "notice.splits_unknown_rows"}  # hypnograms: no recordings
    assert "notice.annotation_labels_unreadable" not in keys
    # the annotations were read once for the labels: the recording carries the M10 summary (A-80, X10)
    assert [
        r.metrics["annotation"]["annotations"] for r in results.recordings if "annotation" in r.metrics
    ] == [31]
    jsonschema.validate(json.loads(canonical.dumps(results)), SCHEMA)
    assert "1 of 31 (events)" in render_report(results, "en")


def test_annotation_labels_follow_the_annotators_filter(tmp_path: Path) -> None:
    """Only the annotators that take part count ([annotation] annotators, A-80): without scorer1 there is no
    "Lights off" and every class has at least 3 of 20 events. A recording whose header cannot be read gives
    no annotations: it is left out and counted in a warning notice."""
    folder = copy_fixture("annotation_continuous_ok", tmp_path)
    (folder / "broken.edf").write_bytes(b"0" * 300)
    config = SLEEP + 'annotators = ["scorer2", "scorer3"]\n' + ANNOTATION_LABELS
    results = run(folder, ai_config(tmp_path, config, rules=(CLASSES,)))
    labels = results.ai.labels if results.ai else None
    assert labels is not None and list(labels.scopes) == ["all"]  # no splits: the scope "all" only
    assert labels.scopes["all"].classes == {"N1": 3, "N2": 6, "N3": 4, "R": 3, "W": 4}
    assert not results.findings and results.summary.exit_code == 0
    notices = {n.message_key: (n.level, n.params) for n in results.notices}
    assert notices["notice.annotation_labels_unreadable"] == (Severity.WARNING, {"count": 1})
    assert "The annotations of 1 recording(s) could not be read" in render_report(results, "en")


def test_annotation_labels_in_bids_come_from_events_tsv(tmp_path: Path) -> None:
    """In BIDS the M10 reader takes events.tsv (code = trial_type, A-80): the same classes as
    events:trial_type. An events.tsv that cannot be read leaves its recording out as a whole, so the test
    split (sub-06 alone) has no labelled event."""
    events = run(FIX / "bids_ai_ok", ai_config(tmp_path, LABELS, rules=(CLASSES,)))
    annotations = run(FIX / "bids_ai_ok", ai_config(tmp_path, ANNOTATION_LABELS, rules=(CLASSES,)))
    assert events.ai is not None and events.ai.labels is not None
    assert annotations.ai is not None and annotations.ai.labels is not None
    assert annotations.ai.labels.source == "annotations" and annotations.ai.labels.column is None
    assert annotations.ai.labels.scopes == events.ai.labels.scopes
    assert annotations.ai.labels.scopes["all"].classes == {"A": 28, "B": 21, "C": 21}
    assert not annotations.findings
    folder = copy_fixture("bids_ai_ok", tmp_path)
    damaged = folder / "sub-06" / "eeg" / "sub-06_task-rest_run-1_events.tsv"
    damaged.write_bytes(b"onset\tduration\ttrial_type\n0\t0.1\t\xff\n")
    results = run(folder, ai_config(tmp_path, ANNOTATION_LABELS, rules=(CLASSES,)))
    assert findings(results, CLASSES) == [("dataset", "test", Status.NOT_CHECKABLE, "ai.no_label_values")]
    unreadable = [n for n in results.notices if n.message_key == "notice.annotation_labels_unreadable"]
    assert [(n.level, n.params) for n in unreadable] == [(Severity.WARNING, {"count": 1})]


def test_free_text_annotation_codes_are_not_shown(tmp_path: Path) -> None:
    """C5, A-51: a code that looks like a name is a class of its own, keyed text-<sha8> and shown only with
    its length."""
    folder = tmp_path / "raw"
    write_edf(folder / "night.edf", sfreq=8, seconds=60, labels=("C3",))
    write_annotation_edf(folder / "night_scorer1.edf", ((0.0, 30.0, "Max Mustermann"), (30.0, 30.0, "W")))
    extra = ANNOTATION_LABELS + '[rules."AI-PROC-001".params]\nmin_share = 0.9\n'
    results = run(folder, ai_config(tmp_path, extra, rules=(CLASSES,)))
    hidden = display_text("Max Mustermann").subkey
    labels = results.ai.labels if results.ai else None
    assert labels is not None and labels.scopes["all"].classes == {hidden: 1, "W": 1}
    free = next(f for f in results.findings if f.subkey == f"all:{hidden}")
    assert free.details["label"] is None and free.details["label_chars"] == 14
    texts = [
        canonical.dumps(results).decode("utf-8"),
        render_report(results, "en"),
        render_report(results, "zh"),
    ]
    assert all("Mustermann" not in text for text in texts)


def test_annotations_are_read_for_labels_only_with_the_class_balance(tmp_path: Path) -> None:
    """The labels belong to CORE-M11-01: a pack without ai.class_balance neither counts them nor reads the
    annotations for them (no M10 summary, no labels block)."""
    config = ai_config(tmp_path, SLEEP + ANNOTATION_LABELS, rules=(DEMOGRAPHY,))
    results = run(FIX / "annotation_continuous_ok", config)
    assert results.ai is not None and results.ai.labels is None
    assert all("annotation" not in r.metrics for r in results.recordings)


# --- datasets without labels and splits (C11) and the processing light (C6) ---------------------------------


def test_without_labels_and_splits_each_rule_gives_one_dataset_level_finding(tmp_path: Path) -> None:
    """C11: without [ai] labels and without splits CORE-M11-01 and CORE-M12-01 give exactly one dataset-level
    not_applicable each, not one per recording. C6: the processing light is grey when no M11/M12 rule passed
    or failed, and green when the duplicate check passed."""
    results = run(FIX / "edf_ok", ai_config(tmp_path))
    assert findings(results, CLASSES) == [
        ("dataset", None, Status.NOT_APPLICABLE, "ai.labels_not_configured")
    ]
    assert findings(results, SPLITS) == [("dataset", None, Status.NOT_APPLICABLE, "ai.no_splits")]
    assert findings(results, DEMOGRAPHY) == [("dataset", None, Status.NOT_CHECKABLE, "ai.subjects_unknown")]
    assert findings(results, DUPLICATES) == []
    assert {p.object for p in results.passed if p.rule_id == DUPLICATES} == {
        pseudonym(Path("rec_a.edf")),
        pseudonym(Path("rec_b.edf")),
    }
    assert results.summary.phases["processing"].light is Light.GREEN and results.summary.exit_code == 0
    alone = run(FIX / "edf_ok", ai_config(tmp_path, rules=(CLASSES, SPLITS)))
    assert sorted((f.rule_id, f.object, f.subkey, f.status) for f in alone.findings) == [
        (CLASSES, "dataset", None, Status.NOT_APPLICABLE),
        (SPLITS, "dataset", None, Status.NOT_APPLICABLE),
    ]
    assert not alone.passed and alone.summary.exit_code == 0
    assert alone.summary.phases["processing"].light is Light.GREY
    core = pipeline.run_check(FIX / "edf_ok", pipeline.CheckOptions(as_of=AS_OF))
    for rule in ("CORE-M11-01", "CORE-M12-01"):
        assert [(f.object, f.status) for f in core.findings if f.rule_id == rule] == [
            ("dataset", Status.NOT_APPLICABLE)
        ]
    # labels from the annotations of a dataset that has none: one dataset-level not_checkable
    empty = run(FIX / "edf_ok", ai_config(tmp_path, ANNOTATION_LABELS, rules=(CLASSES,)))
    assert findings(empty, CLASSES) == [("dataset", None, Status.NOT_CHECKABLE, "ai.no_label_values")]
    assert empty.summary.phases["processing"].light is Light.GREY


# --- privacy of the configured splits file (C4, A-51) ------------------------------------------------------


def test_configured_splits_path_is_hidden_in_raw_folders(tmp_path: Path) -> None:
    """A configured [ai] splits outside .neurogrid/ can carry a name. Raw folders without --show-paths show
    it as its pseudonymous file name, in results.json and in the report appendix; NeuroGrid's own name in
    .neurogrid/, --show-paths and BIDS datasets show it as configured."""
    folder = _raw_folder(tmp_path, {"s01.edf": 1, "s02.edf": 2})
    planted = tmp_path / "Zhang_San" / "splits.tsv"
    planted.parent.mkdir()
    planted.write_text("recording\tsplit\ns01.edf\ttrain\ns02.edf\ttest\n", encoding="utf-8")
    config = ai_config(tmp_path, '[ai]\nsplits = "Zhang_San/splits.tsv"\n')
    results = run(folder, config)
    assert results.ai is not None and results.ai.splits is not None  # the planted file was used
    assert results.ai.splits.recordings == {"train": 1, "val": 0, "test": 1}
    shown = pseudonym(PurePosixPath("Zhang_San/splits.tsv")) + ".tsv"
    assert results.config.effective_settings["ai"]["splits"] == shown
    english = render_report(results, "en")
    texts = [canonical.dumps(results).decode("utf-8"), english, render_report(results, "zh")]
    assert all("Zhang" not in text for text in texts) and shown in english
    clear = run(folder, config, show_paths=True)
    assert clear.config.effective_settings["ai"]["splits"] == "Zhang_San/splits.tsv"
    assert clear.config.canonical_sha256 == results.config.canonical_sha256  # over the real configuration
    bids = run(FIX / "bids_ai_ok", config)
    assert bids.config.effective_settings["ai"]["splits"] == "Zhang_San/splits.tsv"
    write_splits(tmp_path, [("s01.edf", "train")])  # .neurogrid/splits.tsv next to neurogrid.toml
    own = run(folder, ai_config(tmp_path, '[ai]\nsplits = ".neurogrid/splits.tsv"\n'))
    assert own.config.effective_settings["ai"]["splits"] == ".neurogrid/splits.tsv"


# --- exceptions, determinism, schema and report ------------------------------------------------------------


def test_exceptions_apply_per_object_and_subkey(tmp_path: Path) -> None:
    extra = (
        LABELS
        + '[[exceptions]]\nrule = "AI-PROC-004"\nobject = "sub-01/eeg/sub-01_task-rest_run-1_eeg.edf"\n'
        'reason = "Intended copy for a test-retest study (synthetic)."\n'
        '[[exceptions]]\nrule = "AI-PROC-001"\nsubkey = "test:C"\n'
        'reason = "C is not scored in the test set."\n'
        '[[exceptions]]\nrule = "AI-PROC-003"\nobject = "sub-02"\nreason = "Documented re-recording."\n'
    )
    results = run(FIX / "bids_ai_issues", ai_config(tmp_path, extra))
    statuses = {(f.rule_id, f.object, f.subkey): f.status for f in results.findings}
    assert statuses[(DUPLICATES, run_path("01"), "1")] is Status.EXCEPTED
    assert statuses[(DUPLICATES, run_path("05"), "1")] is Status.FAILED
    assert statuses[(CLASSES, "dataset", "test:C")] is Status.EXCEPTED
    assert statuses[(SPLITS, "sub-02", None)] is Status.EXCEPTED
    assert results.summary.exit_code == 1  # the second member of the group still fails
    both = extra + '[[exceptions]]\nrule = "AI-PROC-004"\nobject = "sub-05/**"\nreason = "Second copy."\n'
    assert run(FIX / "bids_ai_issues", ai_config(tmp_path, both)).summary.exit_code == 0


def test_results_do_not_depend_on_jobs(tmp_path: Path) -> None:
    """NG-N03, A-11: splits, duplicates and labels give byte-identical results for --jobs 1 and 4."""
    config = tmp_path / "neurogrid.toml"
    config.write_text(LABELS, encoding="utf-8")
    runs = [
        canonical.dumps(run(FIX / "bids_ai_issues", config, jobs=jobs, work_base=tmp_path / f"w{index}"))
        for index, jobs in enumerate((1, 4, 1))
    ]
    assert runs[0] == runs[1] == runs[2]
    assert json.loads(runs[0])["duplicates"] == [[run_path("01"), run_path("05")]]


def test_results_schema_and_report(tmp_path: Path) -> None:
    results = run(FIX / "bids_ai_issues", ai_config(tmp_path, LABELS))
    data = json.loads(canonical.dumps(results))
    jsonschema.validate(data, SCHEMA)
    english = render_report(results, "en")
    assert f"Same signal as: {run_path('05')}" in english
    assert f"train: {run_path('02', 1)}" in english and "1 of 40 (events)" in english
    chinese = render_report(results, "zh")
    assert "与以下记录信号相同" in chinese and "1 / 40（事件）" in chinese
    old = Results.model_validate({k: v for k, v in data.items() if k not in ("duplicates", "ai")})
    assert old.duplicates is None and old.ai is None  # results.json of P1-P3 still loads (C1)
    render_report(old, "en")


def test_labels_grammar_is_checked_when_the_configuration_is_read(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as info:
        run(FIX / "bids_ai_ok", ai_config(tmp_path, '[ai]\nlabels = "annotations:trial_type"\n'))
    assert info.value.params["field"] == "ai.labels"
    folder = copy_fixture("bids_ai_ok", tmp_path)
    (folder / ".neurogrid" / "splits.tsv").write_bytes(b"recording\tsplit\n\xff\ttrain\n")
    with pytest.raises(InputError) as error:
        run(folder, ai_config(tmp_path))
    assert error.value.message_key == "splits.encoding"
