"""Review of P4, evidence area (R13): GX-03 for formats NeuroGrid cannot read (EVI30), open evidence of info
rules (EVI33), the traffic-light legend (EVI34, C6), P3 results with a free rule ID in an exception (INT41,
C1), the time range of findings on files that are no recordings (INT46, A-10), and the effective
configuration: extensions that carry a name (AI17, A-51) and annotator values in BIDS (INT42, C5)."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import date
from pathlib import Path, PurePosixPath

import h5py
import jsonschema
import pytest
from markupsafe import escape

from conftest import DOCUMENTED_TOML, documented_config  # type: ignore[import-not-found]
from neurogrid import pipeline
from neurogrid.cli import main
from neurogrid.io.discover import pseudonym
from neurogrid.io.identifying import annotator_pseudonym
from neurogrid.io.provenance import shown_suffix
from neurogrid.kernel import canonical
from neurogrid.kernel.findings import Light, Phase, Severity, Status
from neurogrid.model.results import Results
from neurogrid.report.render import build_context, render_report
from neurogrid.report.texts import translator

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"
SCHEMAS = Path(__file__).parents[2] / "src" / "neurogrid" / "schemas"
AS_OF = date(2026, 10, 11)
GX_ONLY = '[check]\nrulepacks = ["gxdsl008"]\n'  # core deselected (A-02): gxdsl008 is evaluated on its own
LANGUAGES = ("zh", "en", "de")


def _config(folder: Path, text: str, name: str = "neurogrid.toml") -> Path:
    path = folder / name
    path.write_text(text, encoding="utf-8")
    return path


def _check(target: Path, config: Path | None = None, **options: object) -> Results:
    return pipeline.run_check(
        target,
        pipeline.CheckOptions(config_path=config, as_of=AS_OF, **options),  # type: ignore[arg-type]
    )


def _texts(results: Results) -> list[str]:
    return [
        canonical.dumps(results).decode("utf-8"),
        *(render_report(results, lang) for lang in ("en", "zh")),
    ]


def _rows(html: str, rule: str) -> list[list[str]]:
    """The cells of the findings rows of ``rule``: rule, clause, title, status, file, channel, measured value,
    threshold, time range, reason (P5: rows carry data-key and cell classes, a channel column was added)."""
    rows = re.findall(
        rf'<tr data-key="[0-9a-f]+"><td class="c-rule mono">{re.escape(rule)}</td>(.*?)</tr>',
        html,
        flags=re.S,
    )
    return [[rule, *re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S)] for row in rows]


# --- EVI30: GX-03 measures recordings in formats NeuroGrid cannot read and orphan companions ---------------


def test_gx03_names_unsupported_formats_by_their_extension_without_core(tmp_path: Path) -> None:
    """A-40/A-83: GX-03 'EDF or HDF5' also for a Neuroscan .cnt, an EGI .mff folder, an orphan .eeg and NWB
    files, with core deselected (A-02). The value is the format from the extension, never the file name
    (A-51); an NWB file that is HDF5 passes."""
    folder = tmp_path / "raw"
    shutil.copytree(FIX / "unsupported", folder)  # legacy.cnt, notes.txt, rec_ok.edf
    (folder / "王伟.cnt").write_bytes(b"\x00" * 64)
    (folder / "sess.mff").mkdir()
    (folder / "sess.mff" / "info.xml").write_text("<fileInfo/>\n", encoding="utf-8")
    (folder / "lonely.eeg").write_bytes(b"\x00" * 32)  # no BrainVision header names it
    (folder / "plain.nwb").write_bytes(b"not an HDF5 container\n")
    with h5py.File(folder / "session.nwb", "w") as handle:
        handle.attrs["nwb_version"] = "2.7.0"
    results = _check(folder, _config(tmp_path, GX_ONLY))
    assert [p.name for p in results.rulepacks] == ["gxdsl008"]
    gx03 = sorted(
        (f.file, f.measured_value, f.status, f.severity)
        for f in results.findings
        if f.rule_id == "GXDSL008-STO-001"
    )
    expected = [
        (pseudonym(PurePosixPath(name)) + suffix, value, Status.FAILED, Severity.WARNING)
        for name, suffix, value in (
            ("legacy.cnt", ".cnt", "CNT"),
            ("王伟.cnt", ".cnt", "CNT"),
            ("sess.mff", ".mff", "MFF"),
            ("lonely.eeg", ".eeg", "EEG"),
            ("plain.nwb", ".nwb", "NWB"),
        )
    ]
    assert gx03 == sorted(expected)
    passed = {p.object for p in results.passed if p.rule_id == "GXDSL008-STO-001"}
    assert passed == {pseudonym(PurePosixPath("rec_ok.edf")), pseudonym(PurePosixPath("session.nwb"))}
    assert results.summary.phases[Phase.STORAGE].light is Light.YELLOW and results.summary.exit_code == 0
    assert all("王伟" not in text for text in _texts(results))


# --- EVI33: open evidence counts only for error and warning rules (A-16) ------------------------------------

INFO_PACK = """rulepack: infopack
version: "1.0"
source: "Site guideline (synthetic)"
source_status: final
rules:
  - id: INFO-ANN-001
    clause: "4.2"
    title_zh: 标注说明（证明材料）
    title_en: Annotation guideline (evidence)
    phase: annotation
    check: evidence.document
    severity: info
    verification: manual
"""


def test_open_evidence_of_an_info_rule_is_not_counted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A-16 'open_evidence ist nur eine Aufschlüsselung' of errors and warnings: the open evidence of an info
    rule stays a finding but is counted nowhere, and the console does not claim it is in the counts."""
    (tmp_path / "info.yaml").write_text(INFO_PACK, encoding="utf-8")
    config = _config(tmp_path, '[check]\nrulepacks = ["info.yaml"]\n')
    out_file = tmp_path / "results.json"
    with pytest.raises(SystemExit) as info:
        main(["check", str(FIX / "edf_ok"), "--config", str(config), "--out", str(out_file)])
    out, _ = capsys.readouterr()
    assert info.value.code == 0 and "open evidence item" not in out
    results = Results.model_validate_json(out_file.read_bytes())
    (finding,) = results.findings
    assert (finding.rule_id, finding.status, finding.severity) == (
        "INFO-ANN-001",
        Status.EVIDENCE_OPEN,
        Severity.INFO,
    )
    annotation = results.summary.phases[Phase.ANNOTATION]
    assert (annotation.light, annotation.errors, annotation.warnings, annotation.open_evidence) == (
        Light.GREEN,
        0,
        0,
        0,
    )
    assert results.summary.open_evidence == 0
    for phase in results.summary.phases.values():
        assert phase.open_evidence <= phase.errors + phase.warnings


# --- EVI34: the legend follows C6 --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def not_applicable_access(tmp_path_factory: pytest.TempPathFactory) -> Results:
    """gxdsl008 alone with GX-04 not applicable (justified): the access phase holds only that result."""
    tmp = tmp_path_factory.mktemp("legend")
    evidence = tmp / "evidence.yaml"
    evidence.write_text(
        "format_version: 1\nevidence:\n  GXDSL008-ACC-001:\n    status: not_applicable\n"
        "    justification: no data at rest on this system\n",
        encoding="utf-8",
    )
    return _check(FIX / "edf_ok", _config(tmp, GX_ONLY + DOCUMENTED_TOML), evidence_path=evidence)


@pytest.mark.parametrize("lang", LANGUAGES)
def test_legend_counts_a_justified_not_applicable_evidence_as_evaluated(
    not_applicable_access: Results, lang: str
) -> None:
    """C6 / ENTSCHEIDUNGEN 'Ampel': every result of an evidence rule counts as evaluated, also a justified
    not_applicable; the green access row and the legend agree."""
    access = [f for f in not_applicable_access.findings if f.phase is Phase.ACCESS]
    assert [(f.rule_id, f.status) for f in access] == [("GXDSL008-ACC-001", Status.NOT_APPLICABLE)]
    assert not_applicable_access.summary.phases[Phase.ACCESS].light is Light.GREEN
    legend = translator(lang).t("light.legend")
    assert str(escape(legend)) in render_report(not_applicable_access, lang)
    assert "evidence.yaml" in legend  # the sentence on evidence rules
    # the outcomes that make a phase evaluated are named in the grey sentence
    for status in ("passed", "failed", "excepted", "evidence_open"):
        assert translator(lang).t(f"status.{status}").split("（")[0].split(" (")[0] in legend


def test_english_legend_wording() -> None:
    legend = translator("en").t("light.legend")
    assert "no open evidence for an error or warning rule" in legend  # A-16 counting (EVI33)
    assert "also a justified 'not applicable'" in legend
    assert "or only results that are not applicable" not in legend  # the old grey sentence


# --- INT41: a P3 results.json with a free rule ID in an exception still loads and renders (C1) --------------


def test_p3_results_with_a_lower_case_exception_rule_still_render(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """P3 accepted any rule text in [[exceptions]] and reported notice.exception_unused; its results.json
    must still pass the results model and schema and render. neurogrid.toml itself must name a rule ID."""
    config = documented_config(tmp_path, '[[exceptions]]\nrule = "CORE-M04-01"\nreason = "old amplifier"\n')
    data = json.loads(canonical.dumps(_check(FIX / "edf_ok", config)))
    data["exceptions"][0]["entry"]["rule"] = "core-m04-01"  # as a P3 run wrote it
    old = tmp_path / "p3_results.json"
    old.write_text(json.dumps(data), encoding="utf-8")
    loaded = Results.model_validate_json(old.read_bytes())
    assert loaded.exceptions[0].entry.rule == "core-m04-01"
    jsonschema.validate(data, json.loads((SCHEMAS / "results.schema.json").read_text(encoding="utf-8")))
    assert render_report(loaded, "en")
    with pytest.raises(SystemExit) as info:
        main(["report", str(old), "--lang", "zh,en", "--out", str(tmp_path / "report")])
    assert info.value.code == 0 and (tmp_path / "report" / "report.en.html").is_file()
    capsys.readouterr()
    lower = documented_config(
        tmp_path, '[[exceptions]]\nrule = "core-m04-01"\nreason = "old amplifier"\n', name="lower.toml"
    )
    with pytest.raises(SystemExit) as info:
        main(["check", str(FIX / "edf_ok"), "--config", str(lower), "--out", str(tmp_path / "r.json")])
    _, err = capsys.readouterr()
    assert info.value.code == 2 and "exceptions.0.rule" in err
    config_schema = json.loads((SCHEMAS / "config.schema.json").read_text(encoding="utf-8"))
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"exceptions": [{"rule": "core-m04-01", "reason": "x"}]}, config_schema)


# --- INT46: files that are no recordings show 'whole file', not 'whole recording' (A-10) -------------------


@pytest.fixture(scope="module")
def deviations(tmp_path_factory: pytest.TempPathFactory) -> Results:
    """A raw folder with its neurogrid.toml in .neurogrid/ and a manifest; afterwards the toml changes and a
    text file is added (CORE-M13-02 changed and new)."""
    tmp = tmp_path_factory.mktemp("deviations")
    folder = tmp / "raw"
    shutil.copytree(FIX / "edf_ok", folder)
    (folder / ".neurogrid").mkdir()
    toml = folder / ".neurogrid" / "neurogrid.toml"
    toml.write_text(DOCUMENTED_TOML, encoding="utf-8")
    run = pipeline.run_manifest(folder)
    assert run.data is not None
    run.target.write_bytes(run.data)
    toml.write_text(DOCUMENTED_TOML + "# reviewed\n", encoding="utf-8")
    (folder / "notes.txt").write_text("session notes\n", encoding="utf-8")
    return _check(folder)


@pytest.mark.parametrize("lang", LANGUAGES)
def test_findings_on_files_that_are_no_recordings_cover_the_whole_file(
    deviations: Results, lang: str
) -> None:
    tr = translator(lang).t
    rows = {row[4]: row for row in _rows(render_report(deviations, lang), "CORE-M13-02")}
    notes = pseudonym(PurePosixPath("notes.txt")) + ".txt"
    assert set(rows) == {".neurogrid/neurogrid.toml", notes}
    for row in rows.values():
        assert row[8] == str(escape(tr("report.value.whole_file")))
    # a finding on a recording without a time range still covers the whole recording
    fmt = build_context(deviations, lang)["fmt"]
    recordings = {rec.id for rec in deviations.recordings}
    on_recordings = [
        f for f in deviations.findings if f.object in recordings and f.file and not f.time_ranges
    ]
    assert on_recordings
    assert {fmt.time_range(f) for f in on_recordings} == {tr("report.value.whole_recording")}


def test_orphan_companion_covers_the_whole_file(tmp_path: Path) -> None:
    """The same for P1-P3 findings on files that are no recordings (CORE-M01-04 orphan companion)."""
    results = _check(FIX / "orphan", documented_config(tmp_path))
    rows = _rows(render_report(results, "en"), "CORE-M01-04")
    assert [row[4] for row in rows] == [pseudonym(PurePosixPath("lonely.fdt")) + ".fdt"]
    assert rows[0][8] == "whole file"


# --- AI17: an extension that carries a name is left out of the effective configuration (A-51) --------------

SPLITS_PACK = """rulepack: splitsonly
version: "1.0"
source: "M12 split check of the core pack (test)"
source_status: final
rules:
  - id: AI-PROC-003
    clause: M12
    title_zh: 受试者只属于一个数据划分
    title_en: Subject in one split only
    phase: processing
    check: ai.split_integrity
    severity: error
    verification: automatic
"""


def test_settings_never_show_a_name_written_as_an_extension(tmp_path: Path) -> None:
    """C4: path values of the effective configuration appear in raw folders as pseudonymous file names; an
    extension made of other than ASCII letters and digits is left out like in manifest findings (show())."""
    folder = tmp_path / "raw"
    shutil.copytree(FIX / "edf_ok", folder)
    (tmp_path / "lists").mkdir()
    (tmp_path / "lists" / "splits.王伟").write_text(
        "recording\tsplit\nrec_a.edf\ttrain\nrec_b.edf\ttest\n", encoding="utf-8"
    )
    (tmp_path / "splits.yaml").write_text(SPLITS_PACK, encoding="utf-8")
    config = _config(
        tmp_path,
        '[check]\nrulepacks = ["splits.yaml"]\n[ai]\nsplits = "lists/splits.王伟"\n'
        '[[annotation.files]]\npath = "hyp/scorer.张三"\nrecording = "rec_a.edf"\n',
    )
    results = _check(folder, config)
    assert results.ai is not None and results.ai.splits is not None  # the planted file was read
    settings = results.config.effective_settings
    assert settings["ai"]["splits"] == pseudonym(PurePosixPath("lists/splits.王伟"))
    assert settings["annotation"]["files"][0]["path"] == pseudonym(PurePosixPath("hyp/scorer.张三"))
    assert settings["annotation"]["files"][0]["recording"] == pseudonym(PurePosixPath("rec_a.edf")) + ".edf"
    for text in _texts(results):
        assert "王伟" not in text and "张三" not in text
    # the shared rule (io.provenance.shown_suffix): short ASCII extensions only, two-part ones as one
    assert [shown_suffix(name) for name in ("splits.TSV", "a.fif.gz", "a.王伟", "a.extensionlong", "x")] == [
        ".tsv",
        ".fif.gz",
        "",
        "",
        "",
    ]


# --- INT42: annotator values in BIDS follow the display rule of C5 ------------------------------------------


def _bids_with_named_annotators(tmp_path: Path) -> Path:
    root = tmp_path / "bids"
    shutil.copytree(FIX / "bids_events_issues", root)
    events = root / "sub-01" / "eeg" / "sub-01_task-oddball_events.tsv"
    events.write_text(events.read_text(encoding="utf-8").replace("\tA1\n", "\tZhang Wei\n"), encoding="utf-8")
    return root


OVERLAPS_PACK = """rulepack: overlapsonly
version: "1.0"
source: "M10 overlap check of the core pack (test)"
source_status: final
rules:
  - id: LAB-ANN-004
    clause: M10
    title_zh: 标注无重叠
    title_en: No overlapping annotations
    phase: annotation
    check: annotation.overlaps
    severity: warning
    verification: automatic
"""
ANNOTATOR_CONFIG = (
    '[check]\nrulepacks = ["overlaps.yaml"]\n'
    '[annotation]\nannotators = ["Zhang Wei", "A2", "张*", "scorer*"]\n'
    '[[annotation.files]]\npath = "sub-01/eeg/hyp.edf"\n'
    'recording = "sub-01/eeg/sub-01_task-oddball_eeg.edf"\nannotator = "Zhang_Wei"\n'
)


def _pattern_pseudonym(pattern: str) -> str:
    return "pattern-" + hashlib.sha256(pattern.encode("utf-8")).hexdigest()[:8]


def test_bids_annotator_settings_follow_the_display_rule(tmp_path: Path) -> None:
    """ENTSCHEIDUNGEN 'Freitext in Ausgaben' (C5): the annotators the findings show as ann-<sha8> do not
    appear in clear through the effective configuration either; displayable IDs, wildcard patterns and the
    path values stay readable in BIDS."""
    root = _bids_with_named_annotators(tmp_path)
    (tmp_path / "overlaps.yaml").write_text(OVERLAPS_PACK, encoding="utf-8")
    config = _config(tmp_path, ANNOTATOR_CONFIG)
    results = _check(root, config)
    annotation = results.config.effective_settings["annotation"]
    assert annotation["annotators"] == [
        _pattern_pseudonym("Zhang Wei"),
        "A2",
        _pattern_pseudonym("张*"),
        "scorer*",
    ]
    assert annotation["files"][0] == {
        "path": "sub-01/eeg/hyp.edf",
        "recording": "sub-01/eeg/sub-01_task-oddball_eeg.edf",
        "annotator": annotator_pseudonym("Zhang_Wei"),
    }
    metrics = [r.metrics["annotation"] for r in results.recordings if "annotation" in r.metrics]
    # the configured annotator is used, under its pseudonym
    assert metrics and annotator_pseudonym("Zhang Wei") in metrics[0]["annotators"]
    for text in _texts(results):
        assert "Zhang" not in text and "张" not in text
    shown = _check(root, config, show_paths=True)
    clear = shown.config.effective_settings["annotation"]
    assert clear["annotators"] == ["Zhang Wei", "A2", "张*", "scorer*"]
    assert clear["files"][0]["annotator"] == "Zhang_Wei"
    assert shown.config.canonical_sha256 == results.config.canonical_sha256  # over the real configuration


# A wildcard inside a name does not make it displayable (INT42 follow-up, A-51, C5): each value the fixed text
# spells with a wildcard filled in (nothing, a separator, a letter, a digit) must pass display_text.
HIDDEN_PATTERNS = (
    "Zh?ng San",  # a letter: Zhang San
    "Zh*ng San",
    "Wang W?i",  # a letter: Wang Wei
    "Zhang S*",  # a letter: Zhang Sa...
    "Zhang?San",  # a separator: Zhang San
    "Zh?ng?San",  # a letter and a separator together
    "?ei ?hang",  # capitals: Wei Zhang
    "ID12345?",  # a digit: a long number
    "Zh[a]ng San",  # glob syntax outside A-17
    "a?b?c?d?",  # more wildcards than MAX_SHOWN_PATTERN_WILDCARDS
    "night 22?31",  # a clock-time separator: night 22.31, 22h31 (X-evidence-0)
    "10?30pm",  # 10.30pm
    "born 12?03?1961",  # a date: born 12.03.1961
)
SHOWN_PATTERNS = ("scorer*", "*scorer*", "rater-??", "site?-rater-??", "A?", "*")


def test_bids_annotator_patterns_with_wildcards_in_a_name_are_hidden(tmp_path: Path) -> None:
    """ENTSCHEIDUNGEN 'Freitext in Ausgaben' (C5): 'Zh?ng San' is not shown in clear because its wildcard is
    no word separator; in BIDS without --show-paths such patterns appear as pattern-<sha8> in
    effective_settings and in the report appendix, wildcard patterns over codes stay readable, and
    --show-paths shows every pattern as configured."""
    assert pipeline.MAX_SHOWN_PATTERN_WILDCARDS == 3
    root = _bids_with_named_annotators(tmp_path)
    (tmp_path / "overlaps.yaml").write_text(OVERLAPS_PACK, encoding="utf-8")
    patterns = [*HIDDEN_PATTERNS, *SHOWN_PATTERNS]
    config = _config(
        tmp_path,
        '[check]\nrulepacks = ["overlaps.yaml"]\n[annotation]\nannotators = ' + json.dumps(patterns) + "\n",
    )
    results = _check(root, config)
    annotators = results.config.effective_settings["annotation"]["annotators"]
    assert annotators == [*(_pattern_pseudonym(p) for p in HIDDEN_PATTERNS), *SHOWN_PATTERNS]
    texts = [*_texts(results), render_report(results, "de")]
    for text in texts:
        for pattern in HIDDEN_PATTERNS:
            assert pattern not in text
    for lang in LANGUAGES:  # the report appendix lists the readable patterns and the pseudonyms
        html = render_report(results, lang)
        assert str(escape(json.dumps("site?-rater-??"))) in html and _pattern_pseudonym("Zh?ng San") in html
    shown = _check(root, config, show_paths=True)
    assert shown.config.effective_settings["annotation"]["annotators"] == patterns
    assert str(escape(json.dumps("Zh?ng San"))) in render_report(shown, "en")
    assert shown.config.canonical_sha256 == results.config.canonical_sha256
