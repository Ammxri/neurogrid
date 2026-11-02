"""M14 in the check pipeline and the report (NV-F02, M14, DM-08; A-30, A-51, A-81, A-91; D-17 option B): the
effective consent at the reference date, exit codes and the light without consent data, the control-file
rule, config.consents_sha256, the notices, the privacy of the consent records and the aggregated report
block. The two-runs byte-identity with a vault is the vault area's and the integration step's test."""

from __future__ import annotations

import datetime as dt
import html as html_lib
import io
import json
import os
import re
import shutil
from pathlib import Path

import pypdf
import pytest

from conftest import dir_link  # type: ignore[import-not-found]
from neurogrid import pipeline
from neurogrid.checks import consent as consent_checks
from neurogrid.checks.ai_dataset import SMALL_CELL
from neurogrid.checks.context import CheckContext
from neurogrid.cli import main
from neurogrid.kernel import canonical
from neurogrid.kernel.errors import ConfigError, UnsafePathError
from neurogrid.kernel.findings import Light, Status
from neurogrid.model.consent import ConsentFile, ConsentScope, dump_consents
from neurogrid.model.results import Results
from neurogrid.report import tables
from neurogrid.report.output import write_reports
from neurogrid.report.render import render_report
from neurogrid.report.texts import translator
from neurogrid.vault import store
from neurogrid.vault.consents import add_consents
from report_html import section, visible_text  # type: ignore[import-not-found]

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"
AS_OF = dt.date(2026, 11, 20)


def record(
    subject: str, uses: tuple[str, ...] = ("training", "validation"), **fields: object
) -> ConsentScope:
    values: dict[str, object] = {"subject": subject, "version": 1, "date": dt.date(2026, 1, 1)}
    values.update(fields)
    return ConsentScope(permitted_uses=uses, **values)  # type: ignore[arg-type]


def write_vault(folder: Path, records: list[ConsentScope]) -> store.VaultLocation:
    """A vault at the default location of ``folder`` (what ``vault init`` creates) with these records."""
    location = store.locate(folder, store.DEFAULT_VAULT_PATH)
    store.init_vault(location)
    location.consents.write_bytes(dump_consents(ConsentFile(consents=records)))
    return location


ALL = [record(f"sub-0{n}") for n in range(1, 7)]
# a pack with the consent check only: the exit code and the lights then depend on M14 alone
LAB_PACK = """rulepack: lab
version: "1"
source: "Lab consent rule"
source_status: final
rules:
  - id: LAB-ACC-001
    clause: "LAB-9"
    title_zh: 用途在知情同意范围内
    title_en: Use covered by consent
    phase: access
    check: consent.covered
    severity: error
    verification: automatic
"""


def _copy(tmp_path: Path, name: str = "bids_ai_ok", folder: str = "ds") -> Path:
    target = tmp_path / folder
    shutil.copytree(FIX / name, target)
    return target


def _check(folder: Path, tmp_path: Path, **options: object) -> Results:
    values: dict[str, object] = {"as_of": AS_OF, "work_base": tmp_path / "work"}
    values.update(options)
    return pipeline.run_check(folder, pipeline.CheckOptions(**values))  # type: ignore[arg-type]


def _m14(results: Results, rule: str = "CORE-M14-01") -> list[tuple[str, str | None, str, str | None]]:
    return sorted(
        (f.object, f.subkey, f.status.value, f.reason) for f in results.findings if f.rule_id == rule
    )


def _lab_only(folder: Path) -> None:
    """The dataset checked with the consent rule only (LAB_PACK, from .neurogrid/neurogrid.toml)."""
    (folder / "lab.yaml").write_text(LAB_PACK, encoding="utf-8")
    (folder / ".neurogrid").mkdir(exist_ok=True)
    (folder / ".neurogrid" / "neurogrid.toml").write_text('[check]\nrulepacks = ["lab.yaml"]\n', "utf-8")


# --- the effective consent and the exit codes -------------------------------------------------------------


def test_effective_version_by_as_of(tmp_path: Path) -> None:
    folder = _copy(tmp_path)
    write_vault(folder, [*ALL, record("sub-03", (), version=2, date=dt.date(2026, 6, 1), withdrawn=True)])
    before = _check(folder, tmp_path, as_of=dt.date(2026, 5, 31))
    assert _m14(before) == []  # every subject covered: passed results are only counted
    assert sum(p.count for p in before.passed if p.rule_id == "CORE-M14-01") == 6
    after = _check(folder, tmp_path, as_of=dt.date(2026, 6, 1))  # the withdrawal is dated on the date
    assert _m14(after) == [("sub-03", "training", "failed", "consent.withdrawn")]
    (finding,) = [f for f in after.findings if f.rule_id == "CORE-M14-01"]
    assert finding.details == {
        "use": "training",
        "splits": ["train"],
        "dataset_uses": False,
        "consent_version": 2,
        "recordings": ["sub-03/eeg/sub-03_task-rest_run-1_eeg.edf"],
        "recordings_total": 1,
    }
    assert finding.severity.value == "error" and finding.phase.value == "access"


def _exit_code(folder: Path, out: Path, *options: str) -> tuple[int, Results]:
    with pytest.raises(SystemExit) as info:
        main(["check", str(folder), "--as-of", AS_OF.isoformat(), "--out", str(out), *options])
    return int(info.value.code or 0), Results.model_validate_json(out.read_bytes())


def test_no_data_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """KONZEPT DoD 'M14 ohne Daten not_checkable': grey and not counted (exit 0), an error with --strict;
    with consent data a missing consent is red and exit 1; everything covered is green."""
    folder = _copy(tmp_path)
    _lab_only(folder)
    out = tmp_path / "r.json"
    code, plain = _exit_code(folder, out)
    assert _m14(plain, "LAB-ACC-001") == [("dataset", None, "not_checkable", "consent.no_vault")]
    assert (code, plain.summary.phases["access"].light) == (0, Light.GREY)
    assert plain.config.consents_sha256 is None
    code, strict = _exit_code(folder, out, "--strict")
    assert _m14(strict, "LAB-ACC-001") == [("dataset", None, "failed", "consent.no_vault")]
    assert (code, strict.summary.phases["access"].light) == (1, Light.RED)
    write_vault(folder, ALL)
    code, covered = _exit_code(folder, out)
    assert (code, covered.summary.phases["access"].light) == (0, Light.GREEN)
    write_vault(folder, [r for r in ALL if r.subject != "sub-04"])
    code, missing = _exit_code(folder, out)
    assert _m14(missing, "LAB-ACC-001") == [("sub-04", "training", "failed", "consent.missing")]
    assert (code, missing.summary.phases["access"].light) == (1, Light.RED)
    capsys.readouterr()


def test_needed_uses_per_split_and_for_the_dataset(tmp_path: Path) -> None:
    folder = _copy(tmp_path)
    (folder / ".neurogrid").mkdir(exist_ok=True)
    write_vault(folder, ALL)
    toml = '[consent]\nsplit_use = { test = ["validation", "publication"] }\ndataset_uses = ["sharing"]\n'
    (folder / ".neurogrid" / "neurogrid.toml").write_text(toml, encoding="utf-8")
    results = _check(folder, tmp_path)
    found = _m14(results)
    assert ("sub-06", "publication", "failed", "consent.use_not_permitted") in found  # test needs publication
    assert {(obj, use) for obj, use, _status, _reason in found if use == "sharing"} == {
        (f"sub-0{n}", "sharing") for n in range(1, 7)
    }  # dataset_uses: every subject
    sharing = next(f for f in results.findings if f.object == "sub-06" and f.subkey == "sharing")
    assert sharing.details["dataset_uses"] is True and sharing.details["splits"] == []
    assert results.config.effective_settings["consent"] == {
        "dataset_uses": ["sharing"],
        "split_use": {"test": ["validation", "publication"]},
    }


def test_annotation_only_files_need_no_consent(tmp_path: Path) -> None:
    """C10: a hypnogram in a split is no signal recording, so it needs no use."""
    folder = _copy(tmp_path, "annotation_continuous_ok")
    write_vault(folder, [record("sub-01")])
    (folder / ".neurogrid" / "splits.tsv").write_text(
        "recording\tsplit\nnight_scorer1.edf\ttrain\n", encoding="utf-8"
    )
    assert _m14(_check(folder, tmp_path)) == [("dataset", None, "not_applicable", "consent.no_uses")]


# --- the consent records are a control file (C2) ----------------------------------------------------------


def test_invalid_consents_end_the_run_before_the_signal_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _copy(tmp_path)
    location = write_vault(folder, ALL)
    location.consents.write_bytes(b"format_version: 1\nconsents:\n  - subject: Zhang San\n")

    def never(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the signal pass ran")

    monkeypatch.setattr(CheckContext, "compute_quality", never)
    with pytest.raises(ConfigError) as info:
        _check(folder, tmp_path)
    assert info.value.message_key == "consents.invalid" and "Zhang" not in str(info.value.params)


@pytest.mark.parametrize("part", ["vault", "consents.yaml"])
def test_a_linked_vault_or_consents_file_ends_the_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], part: str
) -> None:
    folder = _copy(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    write_vault(elsewhere, ALL)
    if part == "vault":
        (folder / ".neurogrid").mkdir(exist_ok=True)
        dir_link(folder / ".neurogrid" / "vault", elsewhere / ".neurogrid" / "vault")
    else:
        location = write_vault(folder, [])
        location.consents.unlink()
        dir_link(location.consents, elsewhere)
    with pytest.raises(UnsafePathError) as info:
        _check(folder, tmp_path)
    assert info.value.message_key == "vault.link" and info.value.params == {"part": part}
    with pytest.raises(SystemExit) as exit_info:
        main(["--lang", "en", "check", str(folder), "--out", str(tmp_path / "r.json")])
    assert exit_info.value.code == 2 and not (tmp_path / "r.json").exists()
    assert translator("en").t("errors.vault.link", part=part) in capsys.readouterr().err


# --- determinism: config.consents_sha256 --------------------------------------------------------------------


def test_consents_sha256_formatting_independent(tmp_path: Path) -> None:
    folder = _copy(tmp_path)
    location = write_vault(folder, ALL)
    canonical_run = _check(folder, tmp_path)
    reformatted = "".join(
        f"  - {{withdrawn: false, permitted_uses: [validation, training], date: '2026-01-01', version: 1,"
        f" subject: '0{n}'}}\r\n"
        for n in reversed(range(1, 7))
    )
    location.consents.write_bytes(
        b"# hand-written\r\nformat_version: 1\r\nconsents:\r\n" + reformatted.encode()
    )
    hand_run = _check(folder, tmp_path)
    assert hand_run.config.consents_sha256 == canonical_run.config.consents_sha256 is not None
    assert canonical.dumps(hand_run) == canonical.dumps(canonical_run)  # results.json byte-identical
    location.consents.write_bytes(dump_consents(ConsentFile(consents=ALL[:-1])))
    assert _check(folder, tmp_path).config.consents_sha256 != canonical_run.config.consents_sha256
    location.consents.unlink()
    assert _check(folder, tmp_path).config.consents_sha256 is None  # no file


def test_without_m14_the_records_are_not_read(tmp_path: Path) -> None:
    folder = _copy(tmp_path)
    location = write_vault(folder, ALL)
    location.consents.write_bytes(b"not: [valid")  # would end a run that loads M14
    (folder / ".neurogrid" / "neurogrid.toml").write_text('[check]\nrulepacks = ["bids"]\n', encoding="utf-8")
    results = _check(folder, tmp_path)
    assert results.config.consents_sha256 is None and _m14(results) == []


# --- notices (counts only) ---------------------------------------------------------------------------------


def test_notices(tmp_path: Path) -> None:
    folder = _copy(tmp_path)
    write_vault(
        folder,
        [
            *ALL,
            record("sub-05", version=2, date=dt.date(2027, 1, 1)),  # after the reference date
            record("sub-99"),  # no recording
            record("sub-98", ethics_approval_ref="Zhang San approval"),
        ],
    )
    notices = {n.message_key: n.params for n in _check(folder, tmp_path).notices}
    assert notices["notice.consent_future_versions"] == {"count": 1, "as_of": AS_OF.isoformat()}
    assert notices["notice.consents_without_recording"] == {"count": 2}
    assert notices["notice.consent_refs_look_identifying"] == {"count": 1}
    assert "notice.consents_outside_dataset" not in notices
    assert "Zhang" not in json.dumps(notices)


def test_a_vault_outside_the_dataset_gets_a_notice(tmp_path: Path) -> None:
    folder = _copy(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    toml = project / "neurogrid.toml"
    toml.write_text('[vault]\npath = "vault"\n', encoding="utf-8")
    location = store.locate(project, "vault")
    store.init_vault(location)
    location.consents.write_bytes(dump_consents(ConsentFile(consents=ALL)))
    results = _check(folder, tmp_path, config_path=toml)
    assert "notice.consents_outside_dataset" in {n.message_key for n in results.notices}
    assert results.summary.phases["access"].light is Light.GREEN


# --- consent add and the manifest (A-22, CLI-09) ------------------------------------------------------------


def test_verify_reports_changed_consents_after_add(tmp_path: Path) -> None:
    folder = _copy(tmp_path)
    location = write_vault(folder, ALL)
    run = pipeline.run_manifest(folder)
    assert run.data is not None
    run.target.write_bytes(run.data)
    assert pipeline.run_verify(folder, run.target).exit_code == 0
    add_consents(location, [record("sub-07")], role="QA", purpose=None, approval_ref=None)
    verify = pipeline.run_verify(folder, run.target)
    assert verify.exit_code == 1
    assert verify.deviations["changed"] == [
        ".neurogrid/vault/consents.yaml"
    ]  # in clear (KNOWN_CONTROL_FILES)
    assert not any(verify.deviations[kind] for kind in verify.deviations if kind != "changed")  # log excluded


# --- privacy (NG-N05, A-51) and the report (D-17 option B) ------------------------------------------------

ETHICS_REF = "EC-ZhangSan-1234567"
VERSION = 7777
DATE = dt.date(2019, 3, 12)


def _raw_with_consents(tmp_path: Path) -> tuple[Path, Path]:
    """A raw folder whose recordings map to sub-07 (train) and sub-08 (val), checked with a pack that has only
    the consent rule: subject IDs can then reach outputs only through the consent findings."""
    folder = _copy(tmp_path, "edf_ok", "raw")
    write_vault(
        folder,
        [
            record("sub-07", ("validation",), version=VERSION, date=DATE, ethics_approval_ref=ETHICS_REF),
            record("sub-08", (), version=VERSION, date=DATE, withdrawn=True, ethics_approval_ref=ETHICS_REF),
        ],
    )
    (folder / ".neurogrid" / "splits.tsv").write_text(
        "recording\tsplit\nrec_a.edf\ttrain\nrec_b.edf\tval\n", encoding="utf-8"
    )
    (folder / "lab.yaml").write_text(LAB_PACK, encoding="utf-8")
    (folder / ".neurogrid" / "neurogrid.toml").write_text(
        '[check]\nrulepacks = ["lab.yaml"]\n'
        '[[convert.files]]\npath = "rec_a.edf"\nsubject = "07"\ntask = "rest"\n'
        '[[convert.files]]\npath = "rec_b.edf"\nsubject = "08"\ntask = "rest"\n',
        encoding="utf-8",
    )
    return folder, tmp_path / "out"


def _texts(data: bytes) -> str:
    return "".join(page.extract_text() or "" for page in pypdf.PdfReader(io.BytesIO(data)).pages)


def _check_privacy(
    folder: Path, out: Path, capsys: pytest.CaptureFixture[str], formats: str
) -> dict[str, str]:
    out.mkdir(exist_ok=True)
    results_file = out / "results.json"
    texts: dict[str, str] = {}
    for args in (
        ["--lang", "en", "check", str(folder), "--as-of", AS_OF.isoformat(), "--out", str(results_file)],
        [
            "--lang",
            "en",
            "report",
            str(results_file),
            "--lang",
            "zh,en",
            "--format",
            formats,
            "--out",
            str(out),
        ],
    ):
        with pytest.raises(SystemExit) as info:
            main(args)
        captured = capsys.readouterr()
        assert info.value.code in (0, 1), captured.err
        texts[f"console {args[2]}"] = captured.out + captured.err
    texts["results.json"] = results_file.read_text(encoding="utf-8")
    for lang in ("zh", "en"):
        texts[f"html {lang}"] = visible_text((out / f"report.{lang}.html").read_text(encoding="utf-8"))
        if "pdf" in formats:
            texts[f"pdf {lang}"] = _texts((out / f"report.{lang}.pdf").read_bytes())
    return texts


def _assert_private(texts: dict[str, str]) -> None:
    for name, text in texts.items():
        assert ETHICS_REF not in text and "ZhangSan" not in text, name
        assert DATE.isoformat() not in text and "2019" not in text, name  # no consent date anywhere
    findings = json.loads(texts["results.json"])["findings"]
    m14 = [f for f in findings if f["rule_id"] == "LAB-ACC-001"]
    # results.json keeps the per-subject findings with the consent version (D-17 option B) ...
    assert {(f["object"], f["subkey"], f["reason"]) for f in m14} == {
        ("sub-07", "training", "consent.use_not_permitted"),
        ("sub-08", "validation", "consent.withdrawn"),
    }
    assert {f["details"]["consent_version"] for f in m14} == {VERSION}
    assert not any("permitted_uses" in f["details"] or "date" in f["details"] for f in m14)
    # ... the report and the console show neither the subjects nor the version
    for name, text in texts.items():
        if name != "results.json":
            assert "sub-07" not in text and "sub-08" not in text and str(VERSION) not in text, name


def test_planted_identifiers_never_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder, out = _raw_with_consents(tmp_path)
    _assert_private(_check_privacy(folder, out, capsys, "html"))


@pytest.mark.pdf
def test_planted_identifiers_never_reach_the_pdf_text(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder, out = _raw_with_consents(tmp_path)
    texts = _check_privacy(folder, out, capsys, "html,pdf")
    assert {"pdf zh", "pdf en"} <= set(texts)
    _assert_private(texts)


def _bids_results(tmp_path: Path, records: list[ConsentScope], toml: str | None = None) -> Results:
    folder = _copy(tmp_path)
    write_vault(folder, records)
    if toml is not None:
        (folder / ".neurogrid" / "neurogrid.toml").write_text(toml, encoding="utf-8")
    return _check(folder, tmp_path)


def test_the_report_shows_m14_aggregated(tmp_path: Path) -> None:
    """D-17 option B: one block per use, status and reason, no finding row, no subject ID, no version; an
    exception of M14 shows neither its object nor its reason (6.3, 6.5); results.json keeps everything."""
    exception = (
        '[[exceptions]]\nrule = "CORE-M14-01"\nobject = "sub-02"\nsubkey = "training"\n'
        'reason = "re-consent requested for sub-02"\n'
    )
    records = [r if r.subject != "sub-02" else record("sub-02", ("validation",), version=4321) for r in ALL]
    results = _bids_results(tmp_path, records, exception)
    assert _m14(results) == [("sub-02", "training", "excepted", "consent.use_not_permitted")]
    m14_keys = {f.key for f in results.findings if f.rule_id == "CORE-M14-01"}
    for lang in ("zh", "en"):
        tr = translator(lang).t
        document = render_report(results, lang)
        block = re.search(r'<div class="rule-group" data-rule="CORE-M14-01">.*?</div>', document, re.S)
        assert block is not None and '<table class="consent">' in block.group(0)
        shown = visible_text(block.group(0))
        assert "sub-0" not in shown and "4321" not in shown
        assert tr("terms.consent_use.training") in shown and tr("report.consent.withheld") in shown  # 1 < 5
        assert tr("report.consent.note") in shown
        assert not any(f'data-key="{key}"' in document for key in m14_keys)  # no finding row
        appendix = document[document.index('<section id="appendix">') :]
        assert "re-consent requested" not in appendix and '"sub-02"' not in appendix
        assert tr("report.consent.exception_withheld") in visible_text(appendix)
    assert results.exceptions[0].entry.object == "sub-02"  # results.json keeps the exception
    assert results.config.effective_settings["exceptions"][0]["reason"] == "re-consent requested for sub-02"


def _finding(results: Results, **update: object) -> object:
    template = next(f for f in results.findings if f.rule_id == "CORE-M14-01")
    return template.model_copy(update=update)


def test_the_small_cell_rule_of_the_m14_block(tmp_path: Path) -> None:
    """A-81 as accepted in D-15: per use the subjects form a table over (status, reason); it is shown only if
    every filled cell has at least 5 subjects, and one withheld use withholds every use (a withdrawal concerns
    all uses of a subject). Dataset-level findings and recordings without a known subject are counted."""
    results = _bids_results(tmp_path, [])
    assert SMALL_CELL == tables.SMALL_CELL == 5 and tables.CONSENT_CHECK == consent_checks.COVERED

    def subjects(use: str, reason: str, count: int) -> list[object]:
        return [
            _finding(
                results,
                object=f"sub-{use}{n}",
                subkey=use,
                status=Status.FAILED,
                reason=reason,
                details={"use": use, "consent_version": 3},
            )
            for n in range(count)
        ]

    big = subjects("training", "consent.withdrawn", 6) + subjects("training", "consent.missing", 5)
    rows, withheld = tables.consent_rows(big)  # type: ignore[arg-type]
    assert not withheld
    assert [(r.use, r.reason, r.count, r.unit) for r in rows] == [
        ("training", "consent.missing", 5, "subjects"),
        ("training", "consent.withdrawn", 6, "subjects"),
    ]
    small = big + subjects("sharing", "consent.use_not_permitted", 2)
    recording = _finding(
        results,
        object="rec-1234abcd",
        status=Status.NOT_CHECKABLE,
        reason="consent.subject_unknown",
        details={"required": False, "uses": ["training", "sharing"]},
    )
    rows, withheld = tables.consent_rows([*small, recording])  # type: ignore[list-item]
    assert withheld
    assert [(r.use, r.status, r.count, r.unit) for r in rows] == [
        ("training", None, 11, "subjects"),  # withheld: only the total of the use
        ("training", Status.NOT_CHECKABLE, 1, "recordings"),
        ("sharing", None, 2, "subjects"),
        ("sharing", Status.NOT_CHECKABLE, 1, "recordings"),
    ]
    dataset = _finding(
        results, status=Status.NOT_CHECKABLE, reason="consent.no_consents", details={"required": False}
    )
    rows, withheld = tables.consent_rows([dataset])  # type: ignore[list-item]
    assert not withheld and [(r.use, r.reason, r.unit) for r in rows] == [
        (None, "consent.no_consents", "dataset")
    ]


@pytest.mark.pdf
def test_the_m14_block_prints(tmp_path: Path) -> None:
    records = [r for r in ALL if r.subject != "sub-04"]
    results = _bids_results(tmp_path, records)
    out = tmp_path / "reports"
    paths = write_reports(results, ["zh", "en"], ["html", "pdf"], out, environ=os.environ)
    for path in paths:
        if path.suffix == ".pdf":
            text = _texts(path.read_bytes())
            lang = path.name.split(".")[1]
            assert re.sub(r"\s+", "", translator(lang).t("report.consent.withheld")) in re.sub(
                r"\s+", "", text
            )
            assert "sub-04" not in re.sub(r"\s+", "", text.split("CORE-M14-01", 1)[1].split("CORE-", 1)[0])


# --- the small-cell rule across the whole report (A-81, A-91; P6 review) ------------------------------------

WITHDRAWN = [*ALL, record("sub-03", (), version=2, date=dt.date(2026, 6, 1), withdrawn=True)]
NOT_PERMITTED = [r if r.subject != "sub-02" else record("sub-02", ("validation",)) for r in ALL]
EXCEPTION = (
    '[[exceptions]]\nrule = "CORE-M14-01"\nobject = "{object}"\nsubkey = "{use}"\nreason = "{reason}"\n'
)


def _consent_views(results: Results, lang: str) -> dict[str, str]:
    """The visible text of every part of the report that counts M14 results: the block with the line under
    its heading, the rule's row in appendix 6.1, the passed checks of section 2 and the error heading of
    section 3."""
    html = render_report(results, lang)
    block = re.search(r'<div class="rule-group" data-rule="CORE-M14-01">.*?</div>', html, re.S)
    overview = re.search(r'<tr data-rule="CORE-M14-01">.*?</tr>', section(html, "appendix"), re.S)
    passed = re.search(
        r'<p class="passed">.*?</p>\s*(?:<p class="passed-note">.*?</p>)?', section(html, "summary"), re.S
    )
    heading = re.search(
        r'<h3 class="sev-error">.*?</h3>\s*(<p class="consent-severity-note">.*?</p>)?', html, re.S
    )
    assert block and overview and passed and heading
    return {
        "block": visible_text(block.group(0)),
        "overview": visible_text(overview.group(0)),
        "overview_cells": overview.group(0),
        "passed": visible_text(passed.group(0)),
        "heading": visible_text(heading.group(0)),
    }


def test_no_m14_cell_of_one_to_four_subjects_can_be_read_from_the_report(tmp_path: Path) -> None:
    """P6 review (A-81 as accepted in D-15, D-17 option B): the M14 tables count every subject that needs a
    use, the passed ones included (results.consent gives the sums per use, results.passed the passed
    subjects), and a withheld table shows only its sums. Nothing else in the report counts what it hides: the
    line under the rule heading names the subjects only, appendix 6.1 the total, the passed checks of
    section 2 leave the rule out and the severity heading counts no excepted result. So the report reads the
    same whether all six subjects consented, one withdrew or one is excepted; only the error counts (summary,
    light, exit code, severity heading) count the failed result, as for every rule."""
    exception = EXCEPTION.format(object="sub-02", use="training", reason="re-consent requested")
    for name in ("covered", "withdrawn", "excepted"):
        (tmp_path / name).mkdir()
    runs = {
        "covered": _bids_results(tmp_path / "covered", ALL),
        "withdrawn": _bids_results(tmp_path / "withdrawn", WITHDRAWN),
        "excepted": _bids_results(tmp_path / "excepted", NOT_PERMITTED, exception),
    }
    assert _m14(runs["covered"]) == []
    assert _m14(runs["withdrawn"]) == [("sub-03", "training", "failed", "consent.withdrawn")]
    assert _m14(runs["excepted"]) == [("sub-02", "training", "excepted", "consent.use_not_permitted")]
    for lang in ("zh", "en"):
        tr = translator(lang).t
        views = {name: _consent_views(results, lang) for name, results in runs.items()}
        for name in ("block", "overview", "passed"):
            assert views["covered"][name] == views["withdrawn"][name] == views["excepted"][name], name
        assert views["covered"]["heading"] == views["excepted"]["heading"]  # the excepted one is not counted
        shown = views["covered"]
        assert tr("report.consent.aggregate", subjects=6) in shown["block"]
        assert tr("report.consent.subjects", count=4) in shown["block"]  # training: sub-01 ... sub-04
        assert tr("report.consent.subjects", count=2) in shown["block"]  # validation: sub-05, sub-06
        assert shown["block"].count(tr("report.consent.withheld")) == 2
        assert tr("report.consent.subjects", count=1) not in shown["block"]
        assert tr("report.text.rule_aggregate", findings=1, objects=1) not in shown["block"]
        assert tr("report.consent.overview_withheld", count=6) in shown["overview"]
        assert '<td class="num">' not in shown["overview_cells"]  # no count per status
        assert tr("report.consent.passed_note") in shown["passed"]
        assert tr("report.consent.severity_note") in shown["heading"]
    for name, results in runs.items():  # section 2: the passed checks of the other rules only
        assert results.consent is not None and results.consent.subjects == {"training": 4, "validation": 2}
        others = sum(p.count for p in results.passed if p.rule_id != "CORE-M14-01")
        assert (
            f"{translator('en').t('report.label.passed_checks')}: {others}"
            in _consent_views(results, "en")["passed"]
        ), name


def test_results_consent_only_when_m14_measured_per_subject(tmp_path: Path) -> None:
    """results.consent (A-91) exists only with results per subject: not without consent data, nor when no
    loaded pack has the consent check; a pack of its own on the check gets the same sums."""
    assert _check(_copy(tmp_path), tmp_path).consent is None  # no vault
    folder = _copy(tmp_path, folder="bids_only")
    write_vault(folder, ALL)
    (folder / ".neurogrid" / "neurogrid.toml").write_text('[check]\nrulepacks = ["bids"]\n', "utf-8")
    assert _check(folder, tmp_path).consent is None
    _lab_only(folder)
    lab = _check(folder, tmp_path)
    assert lab.consent is not None and lab.consent.subjects == {"training": 4, "validation": 2}


def _subject_finding(results: Results, subject: str, use: str, reason: str) -> object:
    return _finding(
        results,
        object=subject,
        subkey=use,
        status=Status.FAILED,
        reason=reason,
        details={"use": use, "consent_version": 2},
    )


def test_a_published_m14_table_shows_the_passed_subjects_of_each_use(tmp_path: Path) -> None:
    """A-81: a table is published when every filled cell, the passed subjects of a use included, has at least
    5 subjects; then 6.1 and section 2 count the rule as any other. A passed cell of 1-4 subjects withholds
    every table, and without the sums per use (results.json written before results.consent existed) only the
    number of subjects that need a use is shown."""
    from neurogrid.kernel.findings import PassedCount
    from neurogrid.model.results import ConsentSummary

    base = _bids_results(tmp_path, WITHDRAWN)
    withdrawn = [_subject_finding(base, f"sub-w{n}", "training", "consent.withdrawn") for n in range(5)]
    passed = [PassedCount(rule_id="CORE-M14-01", object=f"sub-p{n}", count=1) for n in range(55)]
    sums = {"training": 40, "validation": 20}
    table = tables.consent_table(withdrawn, passed, sums)  # type: ignore[arg-type]
    assert not table.withheld and table.subjects == 60
    assert [(r.use, r.status, r.reason, r.count) for r in table.rows] == [
        ("training", Status.FAILED, "consent.withdrawn", 5),
        ("training", Status.PASSED, None, 35),
        ("validation", Status.PASSED, None, 20),
    ]
    small = tables.consent_table(withdrawn, passed[:23], {"training": 8, "validation": 20})  # type: ignore[arg-type]
    assert small.withheld  # 3 subjects passed training
    assert [(r.use, r.status, r.count) for r in small.rows] == [
        ("training", None, 8),
        ("validation", None, 20),
    ]
    for sums_given in (None, {"training": 40, "validation": 21}):  # unknown, or not matching results.passed
        unknown = tables.consent_table(withdrawn, passed, sums_given)  # type: ignore[arg-type]
        assert unknown.withheld and [(r.use, r.status, r.count) for r in unknown.rows] == [(None, None, 60)]
    m14 = [f for f in base.findings if f.rule_id != "CORE-M14-01"]
    results = base.model_copy(
        update={
            "findings": [*m14, *withdrawn],
            "passed": [*(p for p in base.passed if p.rule_id != "CORE-M14-01"), *passed],
            "consent": ConsentSummary(subjects=sums),
        }
    )
    for lang in ("zh", "en"):
        tr = translator(lang).t
        views = _consent_views(results, lang)
        assert tr("report.consent.withheld") not in views["block"]
        assert (
            tr("status.passed") in views["block"]
            and tr("report.consent.subjects", count=35) in views["block"]
        )
        assert tr("report.consent.overview_withheld", count=60) not in views["overview"]
        assert views["overview_cells"].count('<td class="num">') == len(tables.COUNTED)
        assert tr("report.consent.passed_note") not in views["passed"]
        assert tr("report.consent.severity_note") not in views["heading"]
    old = results.model_copy(update={"consent": None})
    views = _consent_views(old, "en")
    assert translator("en").t("report.consent.all_uses") in views["block"]
    assert translator("en").t("report.consent.withheld") in views["block"]


def test_exceptions_of_m14_rules_are_counted_only(tmp_path: Path) -> None:
    """6.3 shows the exceptions of an M14 rule as their number (subject, use, reason and the 'used' marks
    would count the excepted subjects), 6.4 notes no unused one of them, and the settings in 6.5 withhold
    object, use and reason; results.json keeps everything (D-17 option B, A-81)."""
    exceptions = EXCEPTION.format(
        object="sub-02", use="training", reason="re-consent requested"
    ) + EXCEPTION.format(object="sub-05", use="validation", reason="asked again")
    results = _bids_results(tmp_path, NOT_PERMITTED, exceptions)
    assert [(u.entry.object, u.entry.subkey, u.used) for u in results.exceptions] == [
        ("sub-02", "training", True),
        ("sub-05", "validation", False),
    ]
    assert any(n.message_key == "notice.exception_unused" for n in results.notices)
    for lang in ("zh", "en"):
        tr = translator(lang).t
        html = render_report(results, lang)
        appendix = section(html, "appendix")
        listed = appendix[appendix.index("<h3>6.3 ") : appendix.index("<h3>6.4 ")]
        rows = re.findall(r'<tr><td class="mono">.*?</tr>', listed, re.S)
        assert len(rows) == 1 and tr("report.consent.exceptions_total", count=2) in visible_text(rows[0])
        assert "training" not in visible_text(listed) and "validation" not in visible_text(listed)
        text = visible_text(appendix)
        assert "re-consent" not in text and "asked again" not in text and "sub-05" not in text
        unused = tr("notice.exception_unused", rule="CORE-M14-01")
        assert re.sub(r"\s+", "", unused) not in re.sub(r"\s+", "", text)
        assert '"subkey": "training"' not in html_lib.unescape(appendix)
        assert '"subkey": "validation"' not in html_lib.unescape(appendix)


def _exception_without_m14(tmp_path: Path) -> Results:
    """bids_ai_ok checked with the BIDS pack only and an exception for CORE-M14-01 that names a subject and
    gives a reason with a personal name (the rule is not loaded, so the exception has no effect)."""
    folder = _copy(tmp_path)
    (folder / ".neurogrid").mkdir(exist_ok=True)
    (folder / ".neurogrid" / "neurogrid.toml").write_text(
        '[check]\nrulepacks = ["bids"]\n'
        + EXCEPTION.format(object="sub-02", use="training", reason="re-consent asked for sub-02 ZhangSan"),
        encoding="utf-8",
    )
    results = _check(folder, tmp_path)
    assert "CORE-M14-01" not in {rule.id for rule in results.rules}
    assert results.exceptions[0].entry.object == "sub-02"  # results.json keeps the exception
    return results


def test_exceptions_of_an_unloaded_m14_rule_are_withheld(tmp_path: Path) -> None:
    """P6 review (D-17 option B): an exception for a built-in M14 rule is withheld in 6.3 and 6.5 also when
    no loaded pack has the rule; the rules on consent.covered of a loaded pack count as well
    (tables.consent_exception_rules)."""
    results = _exception_without_m14(tmp_path)
    assert tables.BUILTIN_CONSENT_RULES == {"CORE-M14-01"}
    for lang in ("zh", "en"):
        tr = translator(lang).t
        appendix = section(render_report(results, lang), "appendix")
        text = visible_text(appendix)
        assert "ZhangSan" not in text and "re-consent" not in text and "sub-02" not in text
        listed = appendix[appendix.index("<h3>6.3 ") : appendix.index("<h3>6.4 ")]
        assert tr("report.consent.exceptions_total", count=1) in visible_text(listed)
        assert "training" not in visible_text(listed)
        assert tr("report.consent.exception_withheld") in text  # 6.5: object, use and reason
    lab = results.model_copy(
        update={"rules": [*results.rules, results.rules[0].model_copy(update={"id": "LAB-ACC-001"})]}
    )
    assert "LAB-ACC-001" not in tables.consent_exception_rules(lab)  # not on the consent check
    on_check = results.rules[0].model_copy(update={"id": "LAB-ACC-001", "check": "consent.covered"})
    assert "LAB-ACC-001" in tables.consent_exception_rules(results.model_copy(update={"rules": [on_check]}))


@pytest.mark.pdf
def test_exceptions_of_an_unloaded_m14_rule_never_reach_the_pdf(tmp_path: Path) -> None:
    results = _exception_without_m14(tmp_path)
    for path in write_reports(results, ["zh", "en"], ["pdf"], tmp_path / "reports", environ=os.environ):
        tr = translator(path.name.split(".")[1]).t
        text = re.sub(r"\s+", "", _texts(path.read_bytes()))
        assert "ZhangSan" not in text and "re-consent" not in text
        appendix = text.split("6.3" + re.sub(r"\s+", "", tr("report.label.exceptions")), 1)[1]
        assert "sub-02" not in appendix  # BIDS findings name the subject, the exception does not
        assert re.sub(r"\s+", "", tr("report.consent.exceptions_total", count=1)) in appendix


def test_the_built_in_consent_rules_are_known() -> None:
    """tables.BUILTIN_CONSENT_RULES names every rule on consent.covered of the built-in packs."""
    from importlib import resources

    names = sorted(
        entry.name.removesuffix(".yaml")
        for entry in resources.files("neurogrid.rulepacks").iterdir()
        if entry.name.endswith(".yaml")
    )
    assert "core" in names
    found = {
        rule.id
        for name in names
        for rule in pipeline.load_rulepack_ref(name).pack.rules
        if rule.check == tables.CONSENT_CHECK
    }
    assert found == tables.BUILTIN_CONSENT_RULES


@pytest.mark.pdf
def test_the_withheld_m14_counts_in_the_pdf(tmp_path: Path) -> None:
    """The same in the printed report: the sums per use and the total, never the one withdrawn subject."""
    results = _bids_results(tmp_path, WITHDRAWN)
    paths = write_reports(results, ["zh", "en"], ["pdf"], tmp_path / "reports", environ=os.environ)
    for path in paths:
        tr = translator(path.name.split(".")[1]).t
        text = re.sub(r"\s+", "", _texts(path.read_bytes()))
        for shown in (
            tr("report.consent.aggregate", subjects=6),
            tr("report.consent.subjects", count=4),
            tr("report.consent.overview_withheld", count=6),
            tr("report.consent.passed_note"),
        ):
            assert re.sub(r"\s+", "", shown) in text, shown
        block = text.split("CORE-M14-01", 1)[1].split("CORE-", 1)[0]
        assert re.sub(r"\s+", "", tr("report.consent.subjects", count=1)) not in block
        assert re.sub(r"\s+", "", tr("report.text.rule_aggregate", findings=1, objects=1)) not in block


# --- the evaluator and the language keys of the area ---------------------------------------------------


def test_the_evaluator_decides_the_status_of_a_measurement_without_a_value() -> None:
    """ARC-02: the measurer records the run's 'required' fact, the evaluator decides (no kernel change)."""
    from neurogrid.kernel.rules import Measurement

    evaluate = consent_checks.SPECS[0].evaluate
    plain = Measurement(check_id="consent.covered", object="dataset", reason="consent.no_vault")
    assert evaluate(plain, {}).not_checkable == "consent.no_vault"
    required = Measurement(
        check_id="consent.covered", object="dataset", reason="consent.no_vault", details={"required": True}
    )
    verdict = evaluate(required, {})
    assert verdict.not_checkable is None and verdict.passed is False
    covered = Measurement(check_id="consent.covered", object="sub-01", value=True, subkey="training")
    assert evaluate(covered, {}).passed is True
    not_covered = Measurement(
        check_id="consent.covered", object="sub-01", value=False, reason="consent.missing"
    )
    assert evaluate(not_covered, {}).passed is False and evaluate(not_covered, {}).not_checkable is None


def test_language_keys_of_the_area() -> None:
    """Keys built at run time (reasons passed through variables, notices, error and report keys): zh, en, de
    (NG-N06, C7)."""
    from neurogrid.model.consent import CONSENT_USES
    from neurogrid.report.texts import tables as language_tables

    keys = [f"reason.{key}" for key in consent_checks.REASONS] + list(consent_checks.NOTICES)
    keys += [f"check.{spec.id}" for spec in consent_checks.SPECS]
    keys += [f"terms.consent_use.{use}" for use in CONSENT_USES]
    keys += [
        f"errors.consents.{name}" for name in ("invalid", "too_large", "encoding", "not_a_file", "unreadable")
    ]
    keys += [f"errors.consent.{name}" for name in ("duplicate_version", "date_order", "write_failed")]
    keys += [
        f"errors.consent_tsv.{name}"
        for name in ("columns", "invalid_row", "duplicate", "too_large", "too_many_rows", "encoding")
    ]
    keys += [f"report.consent.{unit}" for unit in ("subjects", "recordings", "dataset")]
    for lang in ("zh", "en", "de"):
        missing = [key for key in keys if key not in language_tables()[lang]]
        assert not missing, (lang, missing)


def test_reason_keys_of_the_module_are_listed() -> None:
    source = Path(consent_checks.__file__).read_text(encoding="utf-8")
    used = set(re.findall(r'"(consent\.[a-z_]+)"', source)) - set(consent_checks.CHECKS)
    assert used == set(consent_checks.REASONS)
    assert Path(consent_checks.__file__).name == "consent.py"  # TECH-01 module name
