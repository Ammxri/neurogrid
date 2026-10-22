"""M10 end to end (NG-F08, A-80): results.json, determinism, traffic light, exit code, exceptions, report,
privacy of codes, annotators and path-bearing settings (A-51, C4, C5), and a real ``python -m neurogrid``."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any

import jsonschema
import pytest

from gen_fixtures import write_annotation_edf, write_edf  # type: ignore[import-not-found]
from neurogrid import pipeline
from neurogrid.cli import main
from neurogrid.io.discover import pseudonym
from neurogrid.io.identifying import annotator_pseudonym, display_text
from neurogrid.kernel import canonical
from neurogrid.kernel.errors import ConfigError
from neurogrid.kernel.findings import Light, Phase, Status
from neurogrid.model.results import Results
from neurogrid.report.render import render_report

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"
SCHEMAS = Path(__file__).parent.parent.parent / "src" / "neurogrid" / "schemas"
AS_OF = date(2026, 10, 11)
CONTINUOUS = (
    '[annotation]\nmode = "continuous"\nepoch_s = 30\n'
    'vocabulary = ["W", "N1", "N2", "N3", "R", "Lights off"]\n'
)
M10_ONLY = """rulepack: lab
version: "1.0"
source: "M10 rules of core, alone (test)"
source_status: final
rules:
""" + "".join(
    f"""  - id: LAB-ANN-00{n}
    clause: M10
    title_zh: 标注
    title_en: Annotation
    phase: annotation
    check: annotation.{check}
    severity: warning
    verification: automatic
"""
    for n, check in enumerate(("kappa", "codes", "gaps", "overlaps"), start=1)
)


def _config(tmp_path: Path, text: str, name: str = "neurogrid.toml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _check(target: Path, config: Path | None = None, **options: object) -> Results:
    return pipeline.run_check(
        target,
        pipeline.CheckOptions(config_path=config, as_of=AS_OF, **options),  # type: ignore[arg-type]
    )


def _m10(results: Results) -> list[tuple[str, str, str | None, str | None]]:
    return sorted(
        (f.rule_id, f.status.value, f.subkey, f.reason)
        for f in results.findings
        if f.rule_id.startswith(("CORE-M10", "LAB-ANN"))
    )


def test_results_are_schema_valid_and_carry_the_summary(tmp_path: Path) -> None:
    results = _check(FIX / "annotation_continuous_ok", _config(tmp_path, CONTINUOUS))
    data = json.loads(canonical.dumps(results))
    jsonschema.validate(data, json.loads((SCHEMAS / "results.schema.json").read_text(encoding="utf-8")))
    (night,) = [r for r in data["recordings"] if "annotation" in r["metrics"]]
    assert night["id"] == pseudonym(PurePosixPath("night.edf"))
    summary = night["metrics"]["annotation"]
    assert summary["kappa"] == {
        "mean": 0.666667,
        "min": 0.5,
        "pairs": 3,
        "annotators": 3,
        "undefined_pairs": 0,
    }
    assert summary["mode"] == "continuous" and summary["epoch_s"] == 30.0 and summary["scored_s"] == 300.0
    assert set(summary["coverage"].values()) == {1.0} and len(summary["files"]) == 3
    assert "M07" in night["metrics"]  # the signal metrics stay next to it
    hypnograms = [r for r in data["recordings"] if r["id"] != night["id"]]
    assert len(hypnograms) == 3 and all("annotation" not in r["metrics"] for r in hypnograms)
    passed = {p["rule_id"]: p["count"] for p in data["passed"] if p["rule_id"].startswith("CORE-M10")}
    assert passed == {"CORE-M10-01": 1, "CORE-M10-02": 6, "CORE-M10-03": 3, "CORE-M10-04": 3}
    assert not _m10(results)


def test_two_runs_and_jobs_are_byte_identical(tmp_path: Path) -> None:
    config = _config(tmp_path, CONTINUOUS)
    first = canonical.dumps(_check(FIX / "annotation_continuous_issues", config))
    second = canonical.dumps(_check(FIX / "annotation_continuous_issues", config))
    parallel = canonical.dumps(_check(FIX / "annotation_continuous_issues", config, jobs=4))
    assert first == second == parallel


def test_light_and_exit_code_with_m10_warnings_only(tmp_path: Path) -> None:
    (tmp_path / "m10.yaml").write_text(M10_ONLY, encoding="utf-8")
    config = _config(tmp_path, '[check]\nrulepacks = ["m10.yaml"]\n' + CONTINUOUS)
    ok = _check(FIX / "annotation_continuous_ok", config)
    assert ok.summary.phases[Phase.ANNOTATION].light is Light.GREEN and ok.summary.exit_code == 0
    issues = _check(FIX / "annotation_continuous_issues", config)
    phase = issues.summary.phases[Phase.ANNOTATION]
    assert (phase.light, phase.warnings, phase.errors, issues.summary.exit_code) == (Light.YELLOW, 4, 0, 0)
    assert _m10(issues) == [
        ("LAB-ANN-001", "failed", None, None),
        ("LAB-ANN-002", "failed", "Stage 2", None),
        ("LAB-ANN-003", "failed", annotator_pseudonym("scorer2"), None),
        ("LAB-ANN-004", "failed", annotator_pseudonym("scorer2"), None),
    ]
    by_rule = {f.rule_id: f for f in issues.findings}
    gap = by_rule["LAB-ANN-003"]
    assert gap.measured_value == {"gaps": 1, "gap_s": 30.0, "coverage": 0.9}
    assert [(r.start_s, r.end_s) for r in gap.time_ranges] == [(180.0, 210.0)]
    assert gap.file == pseudonym(PurePosixPath("night_scorer2.edf")) + ".edf"
    overlap = by_rule["LAB-ANN-004"]
    assert [(r.start_s, r.end_s) for r in overlap.time_ranges] == [(80.0, 90.0)]
    kappa = by_rule["LAB-ANN-001"]
    assert kappa.measured_value == pytest.approx(1 / 41) and kappa.threshold == 0.6
    assert kappa.details["pairs"] == 3 and kappa.details["min"] == pytest.approx(-9 / 41)


def test_exceptions_on_code_and_annotator_subkeys(tmp_path: Path) -> None:
    scorer2 = annotator_pseudonym("scorer2")
    config = _config(
        tmp_path,
        CONTINUOUS
        + '[[exceptions]]\nrule = "CORE-M10-02"\nsubkey = "Stage 2"\nreason = "Old label of N2 (SOP-3)."\n'
        + f'[[exceptions]]\nrule = "CORE-M10-03"\nobject = "*.edf"\nsubkey = "{scorer2}"\n'
        + 'reason = "Scorer 2 skipped one epoch on purpose."\n',
    )
    results = _check(FIX / "annotation_continuous_issues", config)
    statuses = {(f.rule_id, f.subkey): f.status for f in results.findings if f.rule_id.startswith("CORE-M10")}
    assert statuses[("CORE-M10-02", "Stage 2")] is Status.EXCEPTED
    assert statuses[("CORE-M10-03", scorer2)] is Status.EXCEPTED
    assert statuses[("CORE-M10-04", scorer2)] is Status.FAILED
    assert [use.used for use in results.exceptions] == [True, True]


def test_report_lists_m10_findings_with_file_and_time_range(tmp_path: Path) -> None:
    results = _check(FIX / "annotation_continuous_issues", _config(tmp_path, CONTINUOUS))
    html = render_report(results, "en")
    assert "CORE-M10-03" in html and "180.000–210.000 s" in html and "80.000–90.000 s" in html
    assert pseudonym(PurePosixPath("night_scorer2.edf")) + ".edf" in html
    assert "No gaps in continuous annotation" in html and "coverage: 0.9" in html
    zh = render_report(results, "zh")
    assert "连续标注无间隙" in zh and "覆盖率" in zh


def test_dataset_without_annotations_gets_one_finding_per_rule() -> None:
    results = _check(FIX / "edf_ok")
    m10 = [f for f in results.findings if f.rule_id.startswith("CORE-M10")]
    assert sorted((f.rule_id, f.object, f.status.value) for f in m10) == [
        (f"CORE-M10-0{n}", "dataset", "not_applicable") for n in (1, 2, 3, 4)
    ]  # C11: not one per recording (A-59)


def test_bids_events_dataset() -> None:
    results = _check(FIX / "bids_events_issues")
    findings = {(f.rule_id, f.subkey): f for f in results.findings if f.rule_id.startswith("CORE-M10")}
    assert findings[("CORE-M10-02", "stimx")].status is Status.FAILED
    overlap = findings[("CORE-M10-04", annotator_pseudonym("A2"))]
    assert overlap.status is Status.FAILED and overlap.details["annotator"] == "A2"  # BIDS: clear, filtered
    assert [(r.start_s, round(r.end_s, 6)) for r in overlap.time_ranges] == [(5.6, 5.8)]
    assert findings[("CORE-M10-03", None)].reason == "annotation.event_mode"
    passed = {(p.rule_id, p.object): p.count for p in results.passed if p.rule_id.startswith("CORE-M10")}
    assert passed[("CORE-M10-02", "dataset")] == 3  # three labels, one code each
    assert passed[("CORE-M10-01", "sub-01/eeg/sub-01_task-oddball_eeg.edf")] == 1
    (summary,) = [r.metrics["annotation"] for r in results.recordings if "annotation" in r.metrics]
    assert summary["kappa"]["mean"] == pytest.approx(0.790576) and summary["sources"] == ["events_tsv"]


def test_unassigned_hypnogram_notice(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    root.mkdir()
    write_edf(root / "night.edf", sfreq=8, seconds=60, labels=("C3",))
    write_annotation_edf(root / "other_s1.edf", ((0.0, 30.0, "W"),))
    results = _check(root)
    notices = {n.message_key: n.params for n in results.notices}
    assert notices["notice.annotations_unassigned"] == {"count": 1}
    summaries = {r.id: r.metrics["annotation"] for r in results.recordings if "annotation" in r.metrics}
    # night.edf has no annotation at all: no summary (its findings say it); the hypnogram is its own object
    other = pseudonym(PurePosixPath("other_s1.edf"))
    assert list(summaries) == [other] and summaries[other]["unassigned"] is True


def test_show_paths_changes_the_display_only(tmp_path: Path) -> None:
    config = _config(tmp_path, CONTINUOUS)
    plain = _check(FIX / "annotation_continuous_issues", config)
    shown = _check(FIX / "annotation_continuous_issues", config, show_paths=True)

    def keys(results: Results) -> list[tuple[str, str, str | None, str]]:
        return sorted((f.key, f.rule_id, f.subkey, f.status.value) for f in results.findings)

    assert keys(plain) == keys(shown)
    gap = next(f for f in shown.findings if f.rule_id == "CORE-M10-03")
    assert gap.details["annotator"] == "scorer2" and gap.file == "night_scorer2.edf"
    assert "annotator" not in next(f for f in plain.findings if f.rule_id == "CORE-M10-03").details


# --- privacy (A-51, C4, C5) ---------------------------------------------------------------------------------


def _planted(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A raw folder whose hypnogram name, annotation text and mapping table carry a name, and a BIDS data set
    whose annotator column does (NeuroGrid's own synthetic values)."""
    raw = tmp_path / "raw"
    (raw / "scoring").mkdir(parents=True)
    write_edf(raw / "night.edf", sfreq=8, seconds=60, labels=("C3",))
    write_annotation_edf(raw / "night_Max_Mustermann.edf", ((0.0, 30.0, "Max Mustermann"), (30.0, 30.0, "W")))
    write_annotation_edf(raw / "scoring" / "Mustermann_hyp.edf", ((0.0, 60.0, "W"),))
    config = _config(
        tmp_path,
        '[annotation]\nmode = "continuous"\nvocabulary = ["W"]\nannotators = ["Max_*", "MM"]\n'
        '[[annotation.files]]\npath = "scoring/Mustermann_hyp.edf"\nrecording = "night.edf"\n'
        "annotator = \"MM\"\n[convert]\npattern = '(?P<subject>Mustermann)_(?P<task>night)\\.edf'\n"
        '[[convert.files]]\npath = "Mustermann/night.edf"\nsubject = "01"\ntask = "sleep"\n',
    )
    bids = tmp_path / "bids"
    eeg = bids / "sub-01" / "eeg"
    eeg.mkdir(parents=True)
    (bids / "dataset_description.json").write_text('{"Name": "t", "BIDSVersion": "1.9.0"}', encoding="utf-8")
    write_edf(eeg / "sub-01_task-x_eeg.edf", sfreq=64, seconds=10, labels=("Fz",), label_prefix="")
    (eeg / "sub-01_task-x_events.tsv").write_text(
        "onset\tduration\ttrial_type\tannotator\n"
        "1\t1\tstim\tZhang Wei\n1\t1\tstim\tA2\n2\t1\tZhang Wei\tA2\n",
        encoding="utf-8",
    )
    return raw, bids, config


def _texts(results: Results) -> list[str]:
    return [
        canonical.dumps(results).decode("utf-8"),
        render_report(results, "en"),
        render_report(results, "zh"),
    ]


def test_planted_names_never_appear_without_show_paths(tmp_path: Path) -> None:
    raw, bids, config = _planted(tmp_path)
    raw_results = _check(raw, config)
    bids_results = _check(bids)
    for text in [*_texts(raw_results), *_texts(bids_results)]:
        assert "Mustermann" not in text and "Zhang" not in text
    hidden = display_text("Max Mustermann").subkey
    assert any(f.subkey == hidden and f.details.get("chars") == 14 for f in raw_results.findings)
    assert "free text (14 characters)" in render_report(raw_results, "en")
    settings = raw_results.config.effective_settings
    assert settings["annotation"]["files"][0] == {
        "path": pseudonym(PurePosixPath("scoring/Mustermann_hyp.edf")) + ".edf",
        "recording": pseudonym(PurePosixPath("night.edf")) + ".edf",
        "annotator": annotator_pseudonym("MM"),
    }
    assert settings["convert"]["pattern"].startswith("pattern-")
    assert (
        settings["convert"]["files"][0]["path"] == pseudonym(PurePosixPath("Mustermann/night.edf")) + ".edf"
    )
    assert all(p.startswith("pattern-") for p in settings["annotation"]["annotators"])
    # the configuration hash is taken over the real configuration (A-69)
    assert raw_results.config.canonical_sha256 == _check(raw, config, show_paths=True).config.canonical_sha256


def test_show_paths_reveals_file_names_but_never_free_text(tmp_path: Path) -> None:
    raw, _bids, config = _planted(tmp_path)
    results = _check(raw, config, show_paths=True)
    text = canonical.dumps(results).decode("utf-8")
    assert "night_Max_Mustermann.edf" in text and "scoring/Mustermann_hyp.edf" in text
    assert "Max Mustermann" not in text  # the annotation text stays free text
    assert results.config.effective_settings["annotation"]["annotators"] == ["Max_*", "MM"]


def test_bids_settings_are_shown_in_clear(tmp_path: Path) -> None:
    root = tmp_path / "bids"
    shutil.copytree(FIX / "bids_events_issues", root)
    config = _config(tmp_path, "[convert]\npattern = '(?P<subject>x)_(?P<task>y)\\.edf'\n")
    settings = _check(root, config).config.effective_settings
    assert settings["convert"]["pattern"] == "(?P<subject>x)_(?P<task>y)\\.edf"


def test_real_subprocess_check(tmp_path: Path) -> None:
    """``python -m neurogrid check`` with the M10 rules alone: warnings only, exit 0; the console names no
    planted text (A-51)."""
    (tmp_path / "m10.yaml").write_text(M10_ONLY, encoding="utf-8")
    config = _config(tmp_path, '[check]\nrulepacks = ["m10.yaml"]\n' + CONTINUOUS)
    out = tmp_path / "results.json"
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "neurogrid",
            "check",
            str(FIX / "annotation_continuous_issues"),
            "--config",
            str(config),
            "--out",
            str(out),
            "--as-of",
            "2026-10-11",
        ],
        capture_output=True,
        env=env,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert sorted(f["rule_id"] for f in data["findings"]) == [f"LAB-ANN-00{n}" for n in (1, 2, 3, 4)]
    assert data["summary"]["phases"]["annotation"]["light"] == "yellow"
    raw, _bids, planted = _planted(tmp_path / "planted")
    console = subprocess.run(
        [sys.executable, "-m", "neurogrid", "check", str(raw), "--config", str(planted), "--out", str(out)],
        capture_output=True,
        env=env,
        check=False,
    )
    assert console.returncode in (0, 1)
    for stream in (console.stdout, console.stderr):
        assert b"Mustermann" not in stream
    assert b"Mustermann" not in out.read_bytes()


# --- P4 review: inputs that ended the run with exit 2 or were judged wrongly (R7-R11) -----------------------

STAGES = ("W", "W", "N1", "N2", "N2", "N3", "N3", "N2", "R", "W")
EVENTS_TSV = Path("sub-01") / "eeg" / "sub-01_task-oddball_events.tsv"


def _cli(args: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    with pytest.raises(SystemExit) as info:
        main(args)
    out, err = capsys.readouterr()
    return int(info.value.code or 0), out, err


def _events_copy(tmp_path: Path, name: str, rows: str, *, keep: str | None = None) -> Path:
    """A copy of bids_events_issues whose events.tsv keeps its header and its rows of annotator ``keep``
    (every row when None), followed by ``rows``."""
    root = tmp_path / name
    shutil.copytree(FIX / "bids_events_issues", root)
    lines = (root / EVENTS_TSV).read_text(encoding="utf-8").splitlines()
    kept = [lines[0], *(line for line in lines[1:] if keep is None or line.endswith("\t" + keep))]
    (root / EVENTS_TSV).write_text("\n".join(kept) + "\n" + rows, encoding="utf-8", newline="\n")
    return root


def test_values_that_overflowed_never_end_the_run_with_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """C2, A-12: events rows whose onset and duration are finite but whose end overflows (ANN00, CON47, INT40:
    math.ceil(inf) with two annotators, an infinite overlap and time range with one) and a hypnogram whose
    header size field reads -1 (ANN01: numpy's memory map raised OverflowError) gave 'Internal error', exit 2
    and no results.json."""
    two = _events_copy(tmp_path, "two", "1e308\t1e308\tstandard\tA1\n9e307\t9e307\tstandard\tA2\n")
    one = _events_copy(tmp_path, "one", "1e308\t1e308\tstimx\tA1\n1e308\t1e308\tstimx\tA1\n", keep="A1")
    header = tmp_path / "header"
    shutil.copytree(FIX / "annotation_continuous_ok", header)
    raw = bytearray((header / "night_scorer1.edf").read_bytes())
    raw[184:192] = b"-1      "
    (header / "night_scorer1.edf").write_bytes(bytes(raw))
    config = _config(tmp_path, CONTINUOUS)
    outputs = {}
    for root, extra in ((two, []), (one, []), (header, ["--config", str(config)])):
        out = tmp_path / f"{root.name}.json"
        code, _out, err = _cli(
            ["check", str(root), "--out", str(out), "--as-of", "2026-10-11", *extra], capsys
        )
        assert code in (0, 1) and "Internal error" not in err, (root.name, err)
        outputs[root.name] = json.loads(out.read_text(encoding="utf-8"))
    for name, kept in (("two", 14), ("one", 7)):
        data = outputs[name]
        notices = {n["message_key"]: n["params"] for n in data["notices"]}
        assert notices["notice.events_rows_invalid"] == {"count": 2}
        (summary,) = [r["metrics"]["annotation"] for r in data["recordings"] if "annotation" in r["metrics"]]
        assert (summary["annotations"], summary["invalid_rows"]) == (kept, 2)
    assert "CORE-M10-01" in {p["rule_id"] for p in outputs["two"]["passed"]}  # kappa of the valid rows
    assert not [f for f in outputs["one"]["findings"] if f["subkey"] == "stimx"]  # the rows are no annotation
    night = pseudonym(PurePosixPath("night.edf"))
    findings = outputs["header"]["findings"]
    unreadable = {
        f["rule_id"]: f["reason"]
        for f in findings
        if f["object"] == night and f["rule_id"].startswith("CORE-M10") and f["status"] == "not_checkable"
    }
    assert unreadable == {f"CORE-M10-0{n}": "annotation.unreadable" for n in (1, 2, 3, 4)}
    scorer1 = pseudonym(PurePosixPath("night_scorer1.edf"))
    (size,) = [f for f in findings if f["object"] == scorer1 and f["rule_id"] == "CORE-M01-02"]
    assert "header.size_field" in size["details"]["issues"]  # M01 reports the damaged header


def test_dates_in_annotation_texts_are_free_text(tmp_path: Path) -> None:
    """ANN02 (A-51, C5): a clock time, a recording date and a birth date in the annotation texts of a raw
    folder appear neither in results.json nor in the reports, with or without --show-paths: only as
    text-<sha8> with their length."""
    raw = tmp_path / "raw"
    raw.mkdir()
    texts = ("Lights off 22.31.07", "recorded 2019-03-12", "born 12.03.1961")
    write_edf(
        raw / "night.edf",
        sfreq=8,
        seconds=60,
        labels=("C3",),
        plus="C",
        annotations=tuple((10.0 * n, 0.0, text) for n, text in enumerate((*texts, "W"))),
    )
    config = _config(tmp_path, '[annotation]\nvocabulary = ["W"]\n')
    for show_paths in (False, True):
        results = _check(raw, config, show_paths=show_paths)
        for text in [*_texts(results), render_report(results, "de")]:
            assert not [p for p in ("22.31.07", "2019-03-12", "12.03.1961") if p in text]
        hidden = {f.subkey: f.details["chars"] for f in results.findings if f.rule_id == "CORE-M10-02"}
        assert hidden == {display_text(text).subkey: len(text) for text in texts}
        assert "free text (19 characters)" in render_report(results, "en")


def test_markers_and_an_empty_scorer_file(tmp_path: Path) -> None:
    """A-80: the technician's zero-duration markers in the signal file are no rater (ANN03: kappa 1.0 of two
    identical scorers, not 0.33, and no gap for them); a scorer file without any annotation is an annotator
    with coverage 0 that takes no part in kappa (ANN04: it was dropped without a trace)."""
    raw = tmp_path / "raw"
    raw.mkdir()
    markers = ((12.0, 0.0, "Lights off"), (290.0, 0.0, "Lights on"))
    write_edf(raw / "night.edf", sfreq=16, seconds=300, labels=("C3",), plus="C", annotations=markers)
    staged = tuple((30.0 * n, 30.0, stage) for n, stage in enumerate(STAGES))
    for name in ("night_scorer1.edf", "night_scorer2.edf"):
        write_annotation_edf(raw / name, staged)
    config = _config(tmp_path, CONTINUOUS.replace('"Lights off"]', '"Lights off", "Lights on"]'))

    def summary(results: Results) -> dict[str, Any]:
        (found,) = [r.metrics["annotation"] for r in results.recordings if "annotation" in r.metrics]
        return dict(found)

    results = _check(raw, config)
    assert _m10(results) == []
    passed = {p.rule_id: p.count for p in results.passed if p.rule_id.startswith("CORE-M10")}
    assert passed == {"CORE-M10-01": 1, "CORE-M10-02": 7, "CORE-M10-03": 2, "CORE-M10-04": 2}
    first = summary(results)
    assert first["kappa"] == {"mean": 1.0, "min": 1.0, "pairs": 1, "annotators": 2, "undefined_pairs": 0}
    names = [annotator_pseudonym(n) for n in ("default", "scorer1", "scorer2")]
    assert first["annotators"] == names and sorted(first["coverage"]) == sorted(names[1:])
    write_annotation_edf(raw / "night_scorer3.edf", ())
    results = _check(raw, config)
    scorer3 = annotator_pseudonym("scorer3")
    assert _m10(results) == [("CORE-M10-03", "failed", scorer3, None)]
    (gap,) = [f for f in results.findings if f.rule_id == "CORE-M10-03"]
    assert gap.measured_value == {"gaps": 1, "gap_s": 300.0, "coverage": 0.0}
    assert gap.file == pseudonym(PurePosixPath("night_scorer3.edf")) + ".edf"
    second = summary(results)
    assert second["annotators"] == [*names, scorer3] and second["coverage"][scorer3] == 0.0
    assert second["kappa"] == first["kappa"] and len(second["files"]) == 3


def test_kappa_annotator_limit(tmp_path: Path) -> None:
    """ANN05 (A-53): many annotators in a small events.tsv made the run quadratic (hours, then MemoryError);
    above MAX_KAPPA_ANNOTATORS kappa is not_checkable and is never computed."""
    rows = "".join(f"{1.2 + 2 * (n % 7)}\t0.6\tstandard\tR{n}\n" for n in range(101))
    results = _check(_events_copy(tmp_path, "many", rows, keep="nobody"))
    (kappa,) = [f for f in results.findings if f.rule_id == "CORE-M10-01"]
    assert (kappa.status, kappa.reason, kappa.details) == (
        Status.NOT_CHECKABLE,
        "annotation.too_many_annotators",
        {"annotators": 101},
    )
    (summary,) = [r.metrics["annotation"] for r in results.recordings if "annotation" in r.metrics]
    assert summary["kappa"] is None and len(summary["annotators"]) == 101
    assert "More annotators than the limit for Cohen" in render_report(results, "en")


def test_annotation_configuration_errors_and_patterns(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """ANN06 (C2): a second [[annotation.files]] row for the same file is exit 2 naming the field (it was
    ignored without a trace); ANN08: patterns are compared with annotator IDs, and a file-name pattern that
    leaves out every annotator is reported as such, not as 'no annotations'."""
    rows = "".join(
        f'[[annotation.files]]\npath = "{path}"\nrecording = "night.edf"\nannotator = "{who}"\n'
        for path, who in (("night_scorer1.edf", "s1"), ("./night_scorer1.edf", "s9"))
    )
    duplicate = _config(tmp_path, CONTINUOUS + rows, "duplicate.toml")
    out = tmp_path / "dup.json"
    code, _out, err = _cli(
        ["check", str(FIX / "annotation_continuous_ok"), "--config", str(duplicate), "--out", str(out)],
        capsys,
    )
    assert code == 2 and "annotation.files.1.path" in err and not out.exists()
    with pytest.raises(ConfigError):
        _check(FIX / "annotation_continuous_ok", duplicate)
    by_file = _config(tmp_path, CONTINUOUS + 'annotators = ["night_scorer*.edf"]\n', "files.toml")
    results = _check(FIX / "annotation_continuous_ok", by_file)
    reasons = {f.rule_id: f.reason for f in results.findings if f.object == "dataset"}
    assert {reasons[f"CORE-M10-0{n}"] for n in (1, 2, 4)} == {"annotation.all_excluded"}
    (gap,) = [f for f in results.findings if f.rule_id == "CORE-M10-03"]
    assert gap.measured_value["coverage"] == 0.0 and gap.details == {"excluded_annotators": 3}
    for lang, text in (("en", "leaves out every annotator"), ("de", "schließt jeden Annotator aus")):
        assert text in render_report(results, lang)
    by_id = _config(tmp_path, CONTINUOUS + 'annotators = ["scorer*"]\n', "ids.toml")
    assert "CORE-M10-01" in {p.rule_id for p in _check(FIX / "annotation_continuous_ok", by_id).passed}
