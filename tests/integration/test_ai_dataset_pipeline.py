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


@pytest.mark.parametrize("source", ["header_only", "participants_na", "rows_unmatched"])
def test_a_split_source_that_assigns_nothing_is_not_applicable(tmp_path: Path, source: str) -> None:
    """AI14 (C11): a split source that assigns no recording gives one dataset-level not_applicable with
    ai.splits_unassigned, never no outcome at all; results.ai.splits still names the source. Negative case,
    a source that assigns some recordings: test_raw_folder_splits_with_mapping_and_pseudonymous_ids."""
    folder = copy_fixture("bids_ai_ok", tmp_path)
    if source == "header_only":
        write_splits(folder, [])
    elif source == "participants_na":
        (folder / ".neurogrid" / "splits.tsv").unlink()
        rows = ["participant_id\tage\tsex\tsplit"] + [f"sub-0{n}\t30\tF\tn/a" for n in range(1, 7)]
        (folder / "participants.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    else:  # paths typed with another case: they match no recording (A-14 matcher)
        write_splits(folder, [(row.upper(), split) for row, split in DISJOINT])
    results = run(folder, ai_config(tmp_path, rules=(SPLITS,)))
    assert findings(results, SPLITS) == [("dataset", None, Status.NOT_APPLICABLE, "ai.splits_unassigned")]
    assert not results.passed and results.summary.phases["processing"].light is Light.GREY
    splits = results.ai.splits if results.ai else None
    expected = "participants.tsv" if source == "participants_na" else "splits.tsv"
    assert splits is not None and splits.source == expected and splits.unassigned == 7
    assert {n.message_key: n.params for n in results.notices}["notice.splits_unassigned"] == {"count": 7}


def test_placeholder_sex_values_are_not_documented(tmp_path: Path) -> None:
    """AI15 (A-81): "unknown" and "nan" say the sex is not known; CORE-M11-02 fails for them like for n/a and
    they do not count as documented."""
    folder = copy_fixture("bids_ai_ok", tmp_path)
    table = folder / "participants.tsv"
    text = table.read_text(encoding="utf-8").replace("sub-03\t45\tF", "sub-03\t45\tunknown")
    table.write_text(text.replace("sub-04\t61.75\tM", "sub-04\t61.75\tnan"), encoding="utf-8")
    results = run(folder, ai_config(tmp_path, rules=(DEMOGRAPHY,)))
    assert findings(results, DEMOGRAPHY) == [
        ("sub-03", "sex", Status.FAILED, "ai.value_missing"),
        ("sub-04", "sex", Status.FAILED, "ai.value_missing"),
    ]
    demography = results.ai.demographics if results.ai else None
    assert demography is not None and (demography.sex_documented, demography.age_documented) == (4, 6)
    clean = run(FIX / "bids_ai_ok", ai_config(tmp_path, rules=(DEMOGRAPHY,)))
    assert not clean.findings and clean.ai is not None and clean.ai.demographics is not None
    assert clean.ai.demographics.sex_documented == 6


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


def test_subject_level_tables_are_withheld_as_a_whole(tmp_path: Path) -> None:
    """A-51 table rule (A-81): participants labels count subjects (sub-01's two recordings count once, CON50).
    Every scope of bids_ai_ok has a cell of 1-4 subjects, so no scope shows a class key or count, only its
    total; CORE-M11-01 has one finding per scope, judged from the total and min_share alone: all (6 subjects)
    fails because even 4 of 6 is below 0.9, train (4) is not checkable, val and test (1 each) pass."""
    config = ai_config(
        tmp_path, '[ai]\nlabels = "participants:sex"\n[rules."AI-PROC-001".params]\nmin_share = 0.9\n'
    )
    results = run(FIX / "bids_ai_ok", config)
    labels = results.ai.labels if results.ai else None
    assert labels is not None and (labels.source, labels.column, labels.unit) == (
        "participants",
        "sex",
        "subjects",
    )
    assert {scope: (value.total, value.classes) for scope, value in labels.scopes.items()} == {
        "all": (6, None),
        "train": (4, None),
        "val": (1, None),
        "test": (1, None),
    }
    assert findings(results, CLASSES) == [
        ("dataset", "all", Status.FAILED, "ai.small_cell"),
        ("dataset", "train", Status.NOT_CHECKABLE, "ai.small_cell"),
    ]
    assert [(p.object, p.count) for p in results.passed if p.rule_id == CLASSES] == [("dataset", 2)]
    for finding in (f for f in results.findings if f.rule_id == CLASSES):
        assert finding.measured_value is None and finding.threshold == 0.9
        assert finding.details == {
            "scope": finding.subkey,
            "unit": "subjects",
            "total": labels.scopes[str(finding.subkey)].total,
            "small_cell": True,
        }
    demography = results.ai.demographics if results.ai else None
    assert demography is not None and (demography.subjects, demography.age_documented) == (6, 6)
    assert demography.sex_documented == 6 and demography.sex is None and demography.age_groups is None
    data = json.loads(canonical.dumps(results))
    assert data["ai"]["labels"]["scopes"]["val"] == {"classes": None, "total": 1}
    jsonschema.validate(data, SCHEMA)
    assert "withheld: categories with fewer than 5 subjects (6 subjects in this scope)" in render_report(
        results, "en"
    )
    assert "已隐去：存在少于 5 名受试者的类别（该范围共 6 名受试者）" in render_report(results, "zh")


def _subjects_dataset(
    folder: Path,
    rows: list[tuple[str, str, str, str]],
    splits: dict[str, str] | None = None,
    runs: dict[str, int] | None = None,
) -> Path:
    """A BIDS dataset with one 2-s EDF per subject (``runs``: more) and a participants.tsv with the columns
    age, sex and group (rows: label, age, sex, group); ``splits`` puts subjects into splits (splits.tsv)."""
    folder.mkdir(parents=True)
    shutil.copyfile(FIX / "bids_ai_ok" / "dataset_description.json", folder / "dataset_description.json")
    lines = ["participant_id\tage\tsex\tgroup"]
    assigned: list[tuple[str, str]] = []
    for index, (label, age, sex, group) in enumerate(rows):
        lines.append(f"sub-{label}\t{age}\t{sex}\t{group}")
        for number in range(1, (runs or {}).get(label, 1) + 1):
            path = run_path(label, number)
            write_edf(
                folder / path,
                sfreq=128,
                seconds=2,
                labels=("Fp1", "Fp2", "C3", "C4"),
                seed=10 * index + number,
            )
            if splits and label in splits:
                assigned.append((path, splits[label]))
    (folder / "participants.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if assigned:
        write_splits(folder, assigned)
    return folder


def _published(results: Results) -> dict[str, object]:
    """Everything a reader of results.json learns about M11/M12: findings with values, thresholds, reasons
    and details, the passed counts, the ai block, the notices and the exit code."""
    data = json.loads(canonical.dumps(results))
    return {
        "findings": data["findings"],
        "passed": data["passed"],
        "ai": data["ai"],
        "notices": data["notices"],
        "exit_code": data["summary"]["exit_code"],
    }


Changes = dict[str, dict[str, str]]  # subject label -> column -> value


def _thirty(changes: Changes) -> list[tuple[str, str, str, str]]:
    """30 subjects (ages 20-49, odd labels female) in the group "control", with ``changes`` applied."""
    rows = []
    for n in range(1, 31):
        row = {
            "age": str(19 + n),
            "sex": "F" if n % 2 else "M",
            "group": "control",
            **changes.get(f"{n:02d}", {}),
        }
        rows.append((f"{n:02d}", row["age"], row["sex"], row["group"]))
    return rows


def _patients(*numbers: int) -> Changes:
    return {f"{n:02d}": {"group": "patient"} for n in numbers}


THIRTY_SPLITS = {f"{n:02d}": "train" if n <= 20 else "val" if n <= 27 else "test" for n in range(1, 31)}
LONE_TEST = {f"{n:02d}": "train" if n < 30 else "test" for n in range(1, 31)}  # sub-30 alone in test


@pytest.mark.parametrize(
    ("labels", "first", "second", "splits"),
    [
        # AI09: status, threshold and total of the scope "all" told whether 1 or 2 subjects are patients
        ("participants:group", _patients(25), _patients(25, 26), None),
        # AI10: one patient more in val; the subjects per split and the other scopes are the same
        ("participants:group", _patients(1, 2, 3, 4, 5, 21), _patients(1, 2, 3, 4, 5, 21, 22), THIRTY_SPLITS),
        # INT38: zero cells and the split subject count told the label of a split's only subject
        ("participants:group", _patients(*range(1, 11), 30), _patients(*range(1, 11)), LONE_TEST),
        # CON48: the same with participants:sex; the demographic sex table (15/15) stays the same
        ("participants:sex", {}, {"29": {"sex": "M"}, "30": {"sex": "F"}}, LONE_TEST),
    ],
)
def test_no_withheld_cell_can_be_derived(
    tmp_path: Path, labels: str, first: Changes, second: Changes, splits: dict[str, str] | None
) -> None:
    """A-51/A-81: two datasets that differ only in a cell of 1-4 subjects give the same results.json for
    every M11/M12 output, so no cell can be recovered from status and total, scope differences, the split
    counts, zero cells or the category keys."""
    config = ai_config(tmp_path, f'[ai]\nlabels = "{labels}"\n', rules=(CLASSES, DEMOGRAPHY, SPLITS))
    one = run(_subjects_dataset(tmp_path / "one", _thirty(first), splits), config)
    two = run(_subjects_dataset(tmp_path / "two", _thirty(second), splits), config)
    assert _published(one) == _published(two)
    assert one.ai is not None and one.ai.labels is not None
    assert all(scope.classes is None for scope in one.ai.labels.scopes.values())
    assert one.ai.labels.scopes["all"].total == 30


@pytest.mark.parametrize(
    ("first", "second"),
    [
        # CON49: every subject in one category (3 subjects, all female and 20-29) vs. two categories
        (
            [("01", "23", "F", "x"), ("02", "25", "F", "x"), ("03", "27", "F", "x")],
            [("01", "23", "F", "x"), ("02", "25", "M", "x"), ("03", "37", "F", "x")],
        ),
        # AI11: only 3 of 12 subjects have an age (all 70-79 vs. two groups); the CORE-M11-02 failures and
        # the subjects give the documented total
        (
            [("01", "75", "F", "x"), ("02", "75", "M", "x"), ("03", "75", "F", "x")]
            + [(f"{n:02d}", "n/a", "M", "x") for n in range(4, 13)],
            [("01", "75", "F", "x"), ("02", "75", "M", "x"), ("03", "25", "F", "x")]
            + [(f"{n:02d}", "n/a", "M", "x") for n in range(4, 13)],
        ),
    ],
)
def test_no_withheld_demographic_cell_can_be_derived(
    tmp_path: Path, first: list[tuple[str, str, str, str]], second: list[tuple[str, str, str, str]]
) -> None:
    """A-51: age groups and sex are withheld as tables (no key with null that would say "at least 1"); the
    documented totals are shown, as CORE-M11-02 publishes them per subject anyway."""
    config = ai_config(tmp_path, rules=(DEMOGRAPHY,))
    one = run(_subjects_dataset(tmp_path / "one", first), config)
    two = run(_subjects_dataset(tmp_path / "two", second), config)
    assert _published(one) == _published(two)
    demography = one.ai.demographics if one.ai else None
    assert demography is not None and demography.age_groups is None and demography.sex is None
    assert demography.age_documented == 3 and demography.sex_documented == len(first)


def test_participant_labels_count_subjects_with_exact_values(tmp_path: Path) -> None:
    """CON50: at least 5 subjects per class, so the table is published with exact values. Subjects are
    counted, not recordings: sub-01 has two recordings and counts once (F 6 subjects in 7 recordings)."""
    rows = [
        (f"{n:02d}", f"2{n % 10}" if n <= 5 else "37.25", "F" if n % 2 else "M", "x") for n in range(1, 12)
    ]
    folder = _subjects_dataset(tmp_path / "eleven", rows, runs={"01": 2})
    sex = run(folder, ai_config(tmp_path, '[ai]\nlabels = "participants:sex"\n', rules=(CLASSES,)))
    labels = sex.ai.labels if sex.ai else None
    assert labels is not None and labels.unit == "subjects" and list(labels.scopes) == ["all"]
    assert (labels.scopes["all"].classes, labels.scopes["all"].total) == ({"F": 6, "M": 5}, 11)
    assert not sex.findings and [(p.object, p.count) for p in sex.passed] == [("dataset", 2)]
    demography = sex.ai.demographics if sex.ai else None
    assert demography is not None and demography.sex == {"female": 6, "male": 5}
    assert demography.age_groups == {"20-29": 5, "30-39": 6}
    strict = run(
        folder,
        ai_config(
            tmp_path,
            '[ai]\nlabels = "participants:sex"\n[rules."AI-PROC-001".params]\nmin_share = 0.5\n',
            rules=(CLASSES,),
        ),
    )
    assert findings(strict, CLASSES) == [("dataset", "all:M", Status.FAILED, None)]
    failed = strict.findings[0]
    assert failed.measured_value == pytest.approx(5 / 11) and failed.threshold == 0.5
    assert failed.details == {"scope": "all", "label": "M", "unit": "subjects", "count": 5, "total": 11}
    assert "5 of 11 (subjects)" in render_report(strict, "en")
    # participants:age counts the 10-year groups (A-21): the raw age 37.25 is no class
    ages = run(folder, ai_config(tmp_path, '[ai]\nlabels = "participants:age"\n', rules=(CLASSES,)))
    assert ages.ai is not None and ages.ai.labels is not None
    assert ages.ai.labels.scopes["all"].classes == {"20-29": 5, "30-39": 6} and not ages.findings
    assert "37.25" not in canonical.dumps(ages).decode("utf-8")


@pytest.mark.parametrize("labels", [LABELS, '[ai]\nlabels = "participants:age"\n'])
def test_raw_ages_never_leave_the_process(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], labels: str
) -> None:
    """bids_ai_ok plants the ages 37.25 and 61.75 (A-21: the raw age is never serialised), also when the age
    column is the label source (AI12, INT39: it counts in 10-year groups, here withheld by the table rule)."""
    config = tmp_path / "neurogrid.toml"
    config.write_text(labels, encoding="utf-8")
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
    if "participants:age" in labels:
        assert data["ai"]["labels"]["scopes"]["all"] == {"classes": None, "total": 6}
        balance = [f for f in data["findings"] if f["rule_id"] == "CORE-M11-01"]
        assert all(f["subkey"] in ("all", "train", "val", "test") for f in balance)


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
    assert "notice.labels_unreadable" not in keys
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
    assert notices["notice.labels_unreadable"] == (Severity.WARNING, {"count": 1})
    assert "The labels of 1 recording(s) could not be read" in render_report(results, "en")


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
    unreadable = [n for n in results.notices if n.message_key == "notice.labels_unreadable"]
    assert [(n.level, n.params) for n in unreadable] == [(Severity.WARNING, {"count": 1})]


def test_unreadable_events_tsv_with_the_events_label_source(tmp_path: Path) -> None:
    """AI13, INT43 (critic G10, A-81): events:<column> reads events.tsv like M10. A recording whose events.tsv
    is not UTF-8 is left out as a whole and counted in the warning notice, as with the source annotations:
    the same classes and scopes from both sources. All tables unreadable: not checkable with
    ai.labels_unreadable, not "column missing"."""
    folder = copy_fixture("bids_ai_ok", tmp_path)
    tables = sorted(folder.glob("sub-*/eeg/*_events.tsv"))
    tables[-1].write_bytes("onset\tduration\ttrial_type\n0\t0.1\t睁眼\n".encode("gbk"))  # sub-06, test
    events = run(folder, ai_config(tmp_path, LABELS, rules=(CLASSES,)))
    annotations = run(folder, ai_config(tmp_path, ANNOTATION_LABELS, rules=(CLASSES,)))
    assert events.ai is not None and events.ai.labels is not None
    assert annotations.ai is not None and annotations.ai.labels is not None
    assert events.ai.labels.scopes == annotations.ai.labels.scopes
    assert events.ai.labels.scopes["all"].total == 60 and events.ai.labels.scopes["test"].total == 0
    for results in (events, annotations):
        assert findings(results, CLASSES) == [("dataset", "test", Status.NOT_CHECKABLE, "ai.no_label_values")]
        notices = [
            (n.level, n.params) for n in results.notices if n.message_key == "notice.labels_unreadable"
        ]
        assert notices == [(Severity.WARNING, {"count": 1})]
    for table in tables:
        table.write_bytes("onset\tduration\ttrial_type\n0\t0.1\t睁眼\n".encode("gbk"))
    for config in (LABELS, ANNOTATION_LABELS):
        unread = run(folder, ai_config(tmp_path, config, rules=(CLASSES,)))
        assert findings(unread, CLASSES) == [("dataset", None, Status.NOT_CHECKABLE, "ai.labels_unreadable")]
        assert unread.ai is not None and unread.ai.labels is None
        notices = [(n.level, n.params) for n in unread.notices if n.message_key == "notice.labels_unreadable"]
        assert notices == [(Severity.WARNING, {"count": 7})]
    readable = run(FIX / "bids_ai_ok", ai_config(tmp_path, LABELS, rules=(CLASSES,)))
    assert not [n for n in readable.notices if n.message_key == "notice.labels_unreadable"]


def test_duplicate_label_columns_count_as_in_m10(tmp_path: Path) -> None:
    """INT43: a second trial_type column is ignored by both sources (the first column counts)."""
    folder = copy_fixture("bids_ai_ok", tmp_path)
    for table in folder.glob("sub-*/eeg/*_events.tsv"):
        lines = table.read_text(encoding="utf-8").splitlines()
        rows = [f"{lines[0]}\ttrial_type"] + [f"{line}\tB" for line in lines[1:]]
        table.write_text("\n".join(rows) + "\n", encoding="utf-8")
    events = run(folder, ai_config(tmp_path, LABELS, rules=(CLASSES,)))
    annotations = run(folder, ai_config(tmp_path, ANNOTATION_LABELS, rules=(CLASSES,)))
    assert events.ai is not None and events.ai.labels is not None
    assert annotations.ai is not None and annotations.ai.labels is not None
    assert events.ai.labels.scopes["all"].classes == {"A": 28, "B": 21, "C": 21}
    assert events.ai.labels.scopes == annotations.ai.labels.scopes


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
