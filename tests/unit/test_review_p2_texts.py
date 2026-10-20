"""Review P2, texts pass (NG-N06, A-06, A-07, A-74, A-77, R14).

- Language keys that the P2 fixes use exist in zh/en/de with the agreed texts.
- Validator findings name their sub-codes in the report ('Affected: a, b (2), c'), because one finding now
  covers one object and validator code (A-06, A-77).
- Wording that read the opposite of the result: the CORE-M04-05 title, TOO_FEW_AUTHORS, HED_* and
  CHECK_ERROR at dataset level, 'raw folder without mapping', the header size limit.
- scan keeps orphan .eeg/.fdt files out of 'unsupported data files' and lists them with their reason.
- The report marks recordings that cannot be read in blocks (KONZEPT: EEGLAB with embedded data, R14).
- DATA_SOURCES.md states only what the BIDS fixtures say, and CI traces check/convert for connect calls.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any

import jsonschema
import pytest
from markupsafe import escape

from conftest import DOCUMENTED_TOML  # type: ignore[import-not-found,unused-ignore]
from neurogrid import pipeline
from neurogrid.cli import main
from neurogrid.io import ORPHAN_SUFFIXES
from neurogrid.io.discover import pseudonym
from neurogrid.kernel import canonical
from neurogrid.kernel.findings import Status
from neurogrid.kernel.i18n import LANGUAGES
from neurogrid.kernel.safety import load_yaml
from neurogrid.model.results import Results
from neurogrid.report.render import MAX_SUB_CODES_SHOWN, render_report
from neurogrid.report.texts import tables, translator, validator_codes

ROOT = Path(__file__).parent.parent.parent
FIX = ROOT / "tests" / "fixtures" / "synthetic"
SCHEMAS = ROOT / "src" / "neurogrid" / "schemas"
AS_OF = date(2026, 10, 11)

# Texts agreed with the fixer groups; their tests assert the English text exactly (placeholders as in en).
AGREED = {
    "errors.config.unsafe_pattern": {
        "en": "Configuration: the regular expression in field '{field}' can take extremely long on some file "
        "names (a repeated part contains another repetition or alternatives, or it uses a back-reference). "
        "Please simplify it.",
        "zh": "配置：字段 '{field}' 中的正则表达式在某些文件名上可能运行极长时间"
        "（重复部分内含另一重复或分支，或使用了反向引用）。请简化该表达式。",
        "de": "Konfiguration: Der reguläre Ausdruck in Feld '{field}' kann bei manchen Dateinamen sehr lange "
        "laufen (ein wiederholter Teil enthält eine weitere Wiederholung oder Alternativen, oder er nutzt "
        "einen Rückverweis). Bitte vereinfachen.",
    },
    "cli.convert.missing_field_na_valid": {
        "en": "Not documented, written as n/a: {field} ({count} recording(s)); BIDS accepts n/a for this "
        "field, so 'check' does not report it.",
        "zh": "未记录，已写为 n/a：{field}（{count} 条记录）；"
        "BIDS 允许该字段为 n/a，因此 'check' 不会报告此项。",
        "de": "Nicht dokumentiert, als n/a geschrieben: {field} ({count} Aufnahme(n)); BIDS lässt hier n/a "
        "zu, daher meldet 'check' das Feld nicht.",
    },
    "reason.convert.failed": {
        "en": "The recording could not be written; nothing of it remains in the output.",
        "zh": "无法写入该记录；输出中不保留其任何部分。",
        "de": "Die Aufnahme konnte nicht geschrieben werden; nichts davon bleibt in der Ausgabe.",
    },
    "reason.convert.no_eeg_channels": {
        "en": "No EEG channel to write (EEG-BIDS needs at least one); not converted.",
        "zh": "没有可写入的 EEG 通道（EEG-BIDS 至少需要一个）；未转换。",
        "de": "Kein EEG-Kanal zum Schreiben (EEG-BIDS braucht mindestens einen); nicht umgewandelt.",
    },
    "errors.convert.mapping_missing_unwritable": {
        "en": "{count} data file(s) have no subject/task mapping; the template .neurogrid/{template} could "
        "not be written (folder not writable, or a link that is not followed).",
        "zh": "{count} 个数据文件缺少受试者/任务映射；无法写入模板 .neurogrid/{template}（文件夹不可写，"
        "或为不跟随的链接）。",
        "de": "{count} Datendatei(en) ohne Zuordnung zu Proband/Aufgabe; die Vorlage .neurogrid/{template} "
        "konnte nicht geschrieben werden (Ordner nicht beschreibbar oder ein Link, dem nicht gefolgt wird).",
    },
    "errors.convert.label_case": {
        "en": "The labels {first} and {second} differ only in case; they would share one folder on Windows "
        "and macOS. Please make them distinct.",
        "zh": "标签 {first} 与 {second} 仅大小写不同；在 Windows 和 macOS 上二者会位于同一文件夹。"
        "请使用可区分的标签。",
        "de": "Die Labels {first} und {second} unterscheiden sich nur in der Groß-/Kleinschreibung; unter "
        "Windows und macOS lägen sie im selben Ordner. Bitte eindeutig benennen.",
    },
    "issue.header.external_reference": {
        "en": "The HDF5 container refers to other files (external link, external storage or virtual "
        "dataset); they are not opened (A-52).",
        "zh": "HDF5 容器引用了其他文件（外部链接、外部存储或虚拟数据集）；这些文件不会被打开（A-52）。",
        "de": "Der HDF5-Container verweist auf andere Dateien (externer Link, externe Speicherung oder "
        "virtueller Datensatz); sie werden nicht geöffnet (A-52).",
    },
    "report.validator.sub_codes": {
        "en": "Affected: {names}",
        "zh": "涉及：{names}",
        "de": "Betrifft: {names}",
    },
    "report.value.not_streamable": {
        "en": "not readable in blocks",
        "zh": "无法分块读取",
        "de": "nicht blockweise lesbar",
    },
    "cli.scan.subjects_unknown": {
        "en": "unknown (not every recording is mapped to a subject)",
        "zh": "未知（并非每条记录都已映射到受试者）",
        "de": "unbekannt (nicht jede Aufnahme ist einem Probanden zugeordnet)",
    },
}
# Phrases that claim a single file; wrong for codes the validator also reports for the whole dataset.
FILE_CLAIMS = ("this file", "of this file", "该文件", "此文件", "diese Datei", "dieser Datei")


def run(args: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    with pytest.raises(SystemExit) as info:
        main(args)
    out, err = capsys.readouterr()
    return int(info.value.code or 0), out, err


# --- language keys ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("key", sorted(AGREED))
def test_keys_of_the_p2_fixes_have_the_agreed_texts(key: str) -> None:
    loaded = tables()
    for lang in LANGUAGES:
        assert loaded[lang][key] == AGREED[key][lang], f"{lang}:{key}"


def test_keys_raised_by_convert_and_eeglab_are_translated_on_the_console() -> None:
    """These keys reach the console through exceptions (_NotConverted, _Refused), not as reason=..."""
    for lang in LANGUAGES:
        tr = translator(lang, strict=True).t
        for key in (
            "reason.convert.failed",
            "reason.convert.no_eeg_channels",
            "issue.header.external_reference",
        ):
            assert tr(key) and tr(key) != key


# --- validator sub-codes in the report (A-06, A-77) ---------------------------------------------------------


@pytest.fixture(scope="module")
def base_results() -> Results:
    return pipeline.run_check(FIX / "edf_mixed", pipeline.CheckOptions(as_of=AS_OF))


def _with_details(results: Results, details: dict[str, Any]) -> Results:
    finding = results.findings[0].model_copy(update={"details": details, "reason": None})
    return results.model_copy(update={"findings": [finding]})


def _findings_html(html: str) -> str:
    return html[html.index('id="findings"') : html.index('id="metrics"')]


@pytest.mark.parametrize(
    ("lang", "affected", "count"),
    [
        ("en", "Affected: CapManufacturer, EEGGround (2), Manufacturer", "(4 occurrences)"),
        ("zh", "涉及：CapManufacturer, EEGGround (2), Manufacturer", "（共 4 处）"),
    ],
)
def test_validator_sub_codes_follow_the_validator_text(
    base_results: Results, lang: str, affected: str, count: str
) -> None:
    details = {
        "validator_code": "SIDECAR_KEY_RECOMMENDED",
        "count": 4,
        "sub_codes": {"Manufacturer": 1, "CapManufacturer": 1, "EEGGround": 2},
    }
    html = _findings_html(render_report(_with_details(base_results, details), lang))
    own = str(escape(validator_codes()["SIDECAR_KEY_RECOMMENDED"][lang]))
    assert own in html and count in html and affected in html
    assert html.index(own) < html.index(count) < html.index(affected)


def test_validator_finding_without_sub_codes_names_none(base_results: Results) -> None:
    html = render_report(
        _with_details(base_results, {"validator_code": "README_FILE_MISSING", "count": 1}), "en"
    )
    assert "Affected:" not in html and validator_codes()["README_FILE_MISSING"]["en"] in html


def test_sub_codes_are_plain_text_and_bounded(base_results: Results) -> None:
    """A sub-code can be a column name from the dataset (TSV_ADDITIONAL_COLUMNS_*): escaped, never markup."""
    names = {f"col{index:03d}": 1 for index in range(MAX_SUB_CODES_SHOWN + 5)}
    names["<b>x</b>"] = 3
    details = {"validator_code": "TSV_ADDITIONAL_COLUMNS_UNDEFINED", "count": 108, "sub_codes": names}
    html = _findings_html(render_report(_with_details(base_results, details), "en"))
    assert "<b>x</b>" not in html and "&lt;b&gt;x&lt;/b&gt; (3)" in html
    assert "col000" in html and f"col{MAX_SUB_CODES_SHOWN - 2:03d}" in html  # '<b>' sorts first
    assert f"col{MAX_SUB_CODES_SHOWN + 4:03d}" not in html and "(+6)" in html


@pytest.fixture(scope="module")
def bids_issues(tmp_path_factory: pytest.TempPathFactory) -> Results:
    """The real validator on bids_issues (README missing, Authors missing, HED schema not offline)."""
    base = tmp_path_factory.mktemp("work-base")
    options = pipeline.CheckOptions(rulepacks=("bids",), as_of=AS_OF, work_base=base)
    return pipeline.run_check(FIX / "bids_issues", options)


def _row(html: str, rule_id: str, *contains: str) -> str:
    """The one finding row of ``rule_id`` that contains every text in ``contains``."""
    rows = re.findall(rf'<tr>\s*<td class="mono">{rule_id}</td>(.*?)</tr>', _findings_html(html), flags=re.S)
    matching = [row for row in rows if all(text in row for text in contains)]
    assert len(matching) == 1, (rule_id, contains, rows)
    return matching[0]


def test_real_validator_findings_name_the_missing_fields(bids_issues: Results) -> None:
    html = render_report(bids_issues, "en")
    assert "Affected: EEGReference" in _row(html, "BIDS-STO-001", "SIDECAR_KEY_REQUIRED")
    assert "Affected: GeneratedBy, License, SourceDatasets" in _row(
        html, "BIDS-STO-002", "JSON_KEY_RECOMMENDED"
    )
    recommended = _row(html, "BIDS-STO-002", "SIDECAR_KEY_RECOMMENDED", "sub-01_task-rest_eeg.edf</td>")
    assert "CapManufacturer, CapManufacturersModelName" in recommended and "EEGGround" in recommended
    zh = render_report(bids_issues, "zh")
    assert "涉及：EEGReference" in _row(zh, "BIDS-STO-001", "SIDECAR_KEY_REQUIRED")


# --- wording that read the opposite of the result -----------------------------------------------------------


def test_only_1005_title_states_the_checked_property(bids_issues: Results) -> None:
    """A 10-05-only name fails CORE-M04-05 with measured 'no': the title must be the checked property."""
    rule = next(r for r in bids_issues.rules if r.id == "CORE-M04-05")
    assert (rule.title_en, rule.title_zh) == (
        "Channel name is within 10-20/10-10",
        "通道名在 10-20/10-10 范围内",
    )
    texts = {lang: tables()[lang]["check.channels.only_1005"] for lang in LANGUAGES}
    assert texts == {
        "en": "Channel name within 10-20/10-10",
        "zh": "通道名在 10-20/10-10 范围内",
        "de": "Kanalname innerhalb 10-20/10-10",
    }
    (finding,) = [f for f in bids_issues.findings if f.rule_id == "CORE-M04-05"]
    assert (finding.subkey, finding.status, finding.measured_value) == ("AFF1h", Status.FAILED, False)
    row = _row(render_report(bids_issues, "en"), "CORE-M04-05", "AFF1h")
    assert (
        "Channel name is within 10-20/10-10 – AFF1h" in row and "not passed" in row and "<td>no</td>" in row
    )


def test_too_few_authors_covers_a_missing_field(bids_issues: Results) -> None:
    """The bundled rule is length(Authors) > 1, so it also fires when Authors is missing (convert output)."""
    text = validator_codes()["TOO_FEW_AUTHORS"]
    assert text["en"] == (
        "The Authors field of dataset_description.json has fewer than two entries or is missing; each author "
        "is expected as a separate entry."
    )
    assert "或缺失" in text["zh"] and "oder fehlt" in text["de"]
    assert {"NO_AUTHORS", "TOO_FEW_AUTHORS"} <= {f.subkey for f in bids_issues.findings}  # Authors missing


def test_codes_reported_for_the_whole_dataset_claim_no_file(bids_issues: Results) -> None:
    """HED_* also come without a location (HED schema not loadable); CHECK_ERROR also at folders."""
    (hed,) = [f for f in bids_issues.findings if f.subkey == "HED_ERROR"]
    assert hed.file is None  # reported for the dataset
    table = validator_codes()
    for code in ("HED_ERROR", "HED_WARNING", "CHECK_ERROR", "MISSING_DATASET_DESCRIPTION", "UNUSED_STIMULUS"):
        for lang in LANGUAGES:
            assert not any(claim in table[code][lang] for claim in FILE_CLAIMS), (code, lang)
    html = render_report(bids_issues, "en")
    assert table["HED_ERROR"]["en"] in _row(html, "BIDS-STO-003", "HED_ERROR")


def test_header_size_issue_names_what_exceeds_which_limit() -> None:
    """issue.header.too_large also covers declared HDF5 sizes and expanded MAT variables (EEGLAB, 4 GB)
    and BrainVision headers above 2 MB."""
    for lang in LANGUAGES:
        text = tables()[lang]["issue.header.too_large"]
        assert "4 GB" in text and "2 MB" in text and "4096" in text, lang
    assert tables()["en"]["issue.header.too_large"].startswith(
        "The header or the content it declares exceeds"
    )


def test_scan_says_why_the_subject_count_is_unknown(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Review P2: a mapping that covers only rec_a.edf printed 'raw folder without mapping'."""
    raw = tmp_path / "raw"
    shutil.copytree(FIX / "edf_ok", raw)
    (raw / ".neurogrid").mkdir()
    (raw / ".neurogrid" / "neurogrid.toml").write_text(
        '[[convert.files]]\npath = "rec_a.edf"\nsubject = "01"\ntask = "rest"\n', encoding="utf-8"
    )
    assert pipeline.run_scan(raw).subjects is None
    code, out, _ = run(["scan", str(raw)], capsys)
    assert code == 0 and "  Subjects: unknown (not every recording is mapped to a subject)\n" in out
    code, out, _ = run(["--lang", "zh", "scan", str(raw)], capsys)
    assert code == 0 and "未知（并非每条记录都已映射到受试者）" in out


# --- scan: orphan companions (A-74, A-77) -------------------------------------------------------------------


def _orphans_and_cnt(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    shutil.copytree(FIX / "orphan", data)
    shutil.copyfile(FIX / "unsupported" / "legacy.cnt", data / "legacy.cnt")
    (data / "lonely.eeg").write_bytes(b"\x00" * 32)
    return data


def test_scan_lists_orphan_companions_apart_from_unsupported_formats(tmp_path: Path) -> None:
    data = _orphans_and_cnt(tmp_path)
    scanned = pipeline.run_scan(data)
    assert [(f.id, f.format) for f in scanned.unsupported] == [
        (pseudonym(PurePosixPath("legacy.cnt")), "CNT")
    ]
    assert sorted((f.id, f.format) for f in scanned.orphans) == sorted(
        [(pseudonym(PurePosixPath("lonely.eeg")), "EEG"), (pseudonym(PurePosixPath("lonely.fdt")), "FDT")]
    )
    assert {f.format.lower() for f in scanned.orphans if f.format} == {s.lstrip(".") for s in ORPHAN_SUFFIXES}
    document = json.loads(canonical.dumps(scanned))
    jsonschema.validate(document, json.loads((SCHEMAS / "scan.schema.json").read_text(encoding="utf-8")))
    assert [item["format"] for item in document["unsupported"]] == ["CNT"]
    assert sorted(item["format"] for item in document["orphans"]) == ["EEG", "FDT"]
    # check still reports them, with their own reason (CORE-M01-04)
    toml = tmp_path / "documented.toml"
    toml.write_text(DOCUMENTED_TOML, encoding="utf-8")
    results = pipeline.run_check(
        data, pipeline.CheckOptions(config_path=toml, as_of=AS_OF, work_base=tmp_path)
    )
    reasons = sorted(f.reason or "" for f in results.findings if f.rule_id == "CORE-M01-04" and f.file)
    assert reasons == ["format.orphan_companion", "format.orphan_companion", "format.unsupported"]


def test_scan_prints_orphans_with_their_reason(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = _orphans_and_cnt(tmp_path)
    code, out, _ = run(["scan", str(data)], capsys)
    reason = translator("en").t("reason.format.orphan_companion")
    cnt, eeg, fdt = (pseudonym(PurePosixPath(n)) for n in ("legacy.cnt", "lonely.eeg", "lonely.fdt"))
    assert code == 0
    assert f"  Unsupported data files: 1\n    - {cnt} (CNT)\n" in out
    assert "  Data files that cannot be assigned: 2\n" in out
    assert f"    - {eeg} (EEG) – {reason}\n" in out and f"    - {fdt} (FDT) – {reason}\n" in out
    code, out, _ = run(["scan", str(FIX / "orphan")], capsys)
    assert (
        code == 0
        and "  Unsupported data files: 0\n" in out
        and "  Data files that cannot be assigned: 1\n" in out
    )
    code, out, _ = run(["scan", str(FIX / "edf_ok")], capsys)
    assert code == 0 and "cannot be assigned" not in out  # listed only when there are any


# --- report: recordings that cannot be read in blocks (R14) -------------------------------------------------


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_report_marks_recordings_not_readable_in_blocks(tmp_path: Path, lang: str) -> None:
    toml = tmp_path / "documented.toml"
    toml.write_text(DOCUMENTED_TOML, encoding="utf-8")
    options = pipeline.CheckOptions(config_path=toml, as_of=AS_OF, work_base=tmp_path)
    embedded = pipeline.run_check(FIX / "eeglab_embedded", options)
    assert [(r.format, r.streamable) for r in embedded.recordings] == [("EEGLAB", False)]
    marker = translator(lang).t("report.value.not_streamable")
    html = render_report(embedded, lang)
    metrics = html[html.index('id="metrics"') : html.index('id="evidence"')]
    assert f"<td>EEGLAB – {marker}</td>" in metrics
    separate = pipeline.run_check(FIX / "eeglab_ok", options)
    assert all(r.streamable for r in separate.recordings)
    assert marker not in render_report(separate, lang)


# --- DATA_SOURCES.md and CI ---------------------------------------------------------------------------------


def test_data_sources_says_only_what_the_fixtures_say() -> None:
    text = " ".join((ROOT / "DATA_SOURCES.md").read_text(encoding="utf-8").split())
    assert "synthetic" in (FIX / "bids_ok" / "README").read_text(encoding="utf-8")
    assert not any(p.name.upper().startswith("README") for p in (FIX / "bids_issues").iterdir())
    assert "each of these data sets says so in its README" not in text
    assert "`bids_ok` says so in its README" in text and "`bids_issues` has no README on purpose" in text
    assert "README_FILE_MISSING" in text and "tools/gen_fixtures.py" in text


def test_ci_traces_check_and_convert_for_network_connections() -> None:
    """KONZEPT: Linux job under strace -f -e trace=connect; any AF_INET/AF_INET6 connect fails it (D-09:
    runs on push)."""
    workflow = load_yaml((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    job = workflow["jobs"]["offline-strace"]
    assert job["runs-on"] == "ubuntu-24.04"
    script = "\n".join(str(step.get("run", "")) for step in job["steps"])
    assert "uv sync --locked --no-build --python 3.12" in script and "apt-get install -y strace" in script
    assert (
        "strace -f -e trace=connect -o trace.txt uv run --no-sync neurogrid check "
        "tests/fixtures/synthetic/bids_ok --rulepack bids --out r.json"
    ) in script
    assert "strace -A -f -e trace=connect -o trace.txt uv run --no-sync neurogrid convert" in script
    assert "cp -r tests/fixtures/synthetic/edf_ok" in script and "[[convert.files]]" in script
    assert 'path = "rec_a.edf"' in script and 'path = "rec_b.edf"' in script
    assert "grep -E 'AF_INET6?' trace.txt" in script and "exit 1" in script
