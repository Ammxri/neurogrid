"""The oracle of the G1 acceptance, tools/acceptance_g1.py (NG-F13, NG-F14, NG-N03, NG-N05, REP-00, V-01,
V-06): every check passes on what the product writes and names the defect when that output is broken, so a
green G1 run means each output was really read. The checks run on fixture results here; the end-to-end run
on fixtures is test_g1_fixture_runs.py, the corpus run test_g1_corpus.py. Tests that print PDFs are marked
``pdf`` (skipped without the browser, failing without it when NEUROGRID_REQUIRE_PDF=1)."""

from __future__ import annotations

import html as html_lib
import io
import json
import os
import re
from collections import Counter
from datetime import date
from pathlib import Path

import pypdf
import pytest
from pypdf.generic import ArrayObject, DictionaryObject, NameObject

import acceptance_g1 as g1  # type: ignore[import-not-found]
from gen_fixtures import scale_results, write_edf  # type: ignore[import-not-found]
from neurogrid import pipeline
from neurogrid.kernel import canonical
from neurogrid.model.results import Results
from neurogrid.report.output import write_reports
from neurogrid.report.render import EXPLAINED_EMPTY, FINDING_CELLS, MAX_ROWS_PER_RULE, render_report
from neurogrid.report.texts import disclaimer, translator

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"
AS_OF = date(2026, 10, 11)
LANGS = ("zh", "en")
ROW = re.compile(r'<tr data-key="(?P<key>[0-9a-f]+)">.*?</tr>', re.S)


@pytest.fixture(scope="module")
def results() -> Results:
    """bids_issues with core + bids + gxdsl008: errors, warnings, dataset-level, manual and not-checkable
    findings, parameters with their origin."""
    return pipeline.run_check(
        FIX / "bids_issues", pipeline.CheckOptions(rulepacks=("bids", "gxdsl008"), as_of=AS_OF)
    )


@pytest.fixture(scope="module")
def overflowing() -> Results:
    """More than MAX_ROWS_PER_RULE findings per rule (A-59): the scaling generator's worst case, small."""
    return scale_results(recordings=2, channels=32, worst_case=True)


def _run(name: str, code: int, stdout: bytes = b"", stderr: bytes = b"") -> g1.CommandRun:
    return g1.CommandRun(name, code, stdout, stderr, 0.0)


def _row(document: str, key: str) -> str:
    match = re.search(rf'<tr data-key="{key}">.*?</tr>', document, re.S)
    assert match is not None, key
    return match.group(0)


# --- exit codes and console (NG-F14, A-08) ------------------------------------------------------------------


def test_exit_codes_follow_the_contract(results: Results) -> None:
    code = results.summary.exit_code
    good = {"check": _run("check", code), "report": _run("report", 0), "verify": _run("verify", 0)}
    assert g1.check_exit_codes(good, results) == []
    assert g1.check_exit_codes({**good, "check": _run("check", 2)}, results) == ["check: exit 2 (tool error)"]
    assert g1.check_exit_codes({**good, "check": _run("check", 1 - code)}, results) == [
        f"check: exit {1 - code} != summary.exit_code {code}"
    ]
    assert g1.check_exit_codes({**good, "check": _run("check", 3)}, results) == [
        "check: exit 3 is not 0 or 1"
    ]
    assert g1.check_exit_codes({**good, "report": _run("report", 1)}, results) == [
        "report: exit 1, expected 0"
    ]
    assert g1.check_exit_codes({**good, "scan": _run("scan", 2)}, None) == ["scan: exit 2 (tool error)"]


@pytest.mark.parametrize("lang", LANGS)
def test_console_contract(lang: str) -> None:
    sentence = disclaimer(lang).encode("utf-8")
    warning = translator(lang).t("cli.warning.library", type="RuntimeWarning").encode("utf-8")
    assert g1.check_console(b"done\n" + sentence + b"\n", warning + b"\n", lang, 1) == []
    assert g1.check_console(b"done\n", b"", lang, 0) == [f"stdout lacks the fixed sentence ({lang})"]
    assert g1.check_console(sentence, b"Some library: careful\n", lang, 0) == [
        "stderr holds a line that is no translated NeuroGrid message"
    ]
    assert g1.check_console(b"\xfc\n" + sentence, b"", lang, 0) == ["stdout is not valid UTF-8"]
    trace = b'Traceback (most recent call last):\n  File "x.py", line 1\nError: D:\\data\n'
    assert g1.check_console(b"", trace, lang, 2) == [
        "stderr holds a traceback",
        "stderr holds a source location",
        "stderr holds a drive path",
    ]


def test_console_names_the_chosen_output_folder_only() -> None:
    """A-82: the console names the --out folder (with the home folder written '~'); any other path under the
    home folder is a defect."""
    out = Path.home() / "ng-acceptance" / "out"
    sentence = disclaimer("en").encode("utf-8")
    shown = (
        f"Report written to {out / 'report.en.html'}\nResults written to ~{os.sep}ng-acceptance{os.sep}out\n"
    )
    stdout = shown.encode("utf-8") + sentence
    assert g1.check_console(stdout, b"", "en", 0, allowed_paths=(out,)) == []
    problems = g1.check_console(stdout, b"", "en", 0, allowed_paths=(out.parent / "other",))
    assert "stdout holds the home folder" in problems


def test_files_are_exactly_the_products_files(tmp_path: Path) -> None:
    for name in g1.PRODUCT_FILES:
        (tmp_path / name).write_bytes(b"")
    assert g1.check_files(tmp_path) == []
    (tmp_path / "report.zh.pdf").unlink()
    (tmp_path / ".results.json.x1.tmp").write_bytes(b"")  # a staged file left behind (A-54)
    (tmp_path / "run-1a2b").mkdir()  # a work folder left behind
    assert g1.check_files(tmp_path) == [
        "missing report.zh.pdf",
        "unexpected file .results.json.x1.tmp",
        "unexpected folder run-1a2b",
    ]


# --- results.json (NG-F14) ----------------------------------------------------------------------------------


def test_results_file_valid_and_canonical(results: Results, tmp_path: Path) -> None:
    path = tmp_path / "results.json"
    path.write_bytes(canonical.dumps(results))
    checked = g1.validate_results_file(path)
    assert checked.problems == [] and checked.results == results
    data = json.loads(canonical.dumps(results))
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    assert g1.validate_results_file(path).problems == ["results.json is not canonical"]
    data["summary"]["exit_code"] = "1"
    path.write_text(json.dumps(data), encoding="utf-8")
    problems = g1.validate_results_file(path).problems
    assert "results.json: schema error at /summary/exit_code" in problems
    path.write_bytes(b"\xff not json")
    assert g1.validate_results_file(path).problems == [
        "results.json: not readable as UTF-8 JSON (UnicodeDecodeError)",
        "results.json does not load (ValidationError)",
    ]


def test_scan_and_manifest_files_against_their_schemas(tmp_path: Path) -> None:
    scan = tmp_path / "scan.json"
    scan.write_bytes(canonical.dumps(pipeline.run_scan(FIX / "edf_mixed")))
    assert g1.validate_schema_file(scan, "scan") == []
    data = json.loads(scan.read_text(encoding="utf-8"))
    data["recordings"] = "none"
    scan.write_text(json.dumps(data), encoding="utf-8")
    assert g1.validate_schema_file(scan, "scan") == ["scan.json: schema error at /recordings"]


# --- finding rows (NG-F13, A-09, A-13, A-59) ----------------------------------------------------------------


@pytest.mark.parametrize("lang", LANGS)
def test_finding_rows_accept_the_report(results: Results, overflowing: Results, lang: str) -> None:
    for checked_results in (results, overflowing):
        checked = g1.check_finding_rows(render_report(checked_results, lang), checked_results, lang)
        totals = Counter(finding.rule_id for finding in checked_results.findings)
        assert checked.problems == []
        assert checked.rows == sum(min(total, MAX_ROWS_PER_RULE) for total in totals.values())
    assert max(Counter(f.rule_id for f in overflowing.findings).values()) > MAX_ROWS_PER_RULE


def test_finding_rows_name_each_defect(results: Results) -> None:
    lang = "en"
    document = render_report(results, lang)
    key = ROW.search(document)["key"]  # type: ignore[index]
    row = _row(document, key)

    def problems(changed_row: str, source: str = document) -> list[str]:
        return g1.check_finding_rows(source.replace(row, changed_row), results, lang).problems

    time_cell = re.search(r'<td class="c-time">.*?</td>', row)
    assert time_cell is not None
    assert f"row {key}: cells missing: time" in problems(row.replace(time_cell.group(0), ""))
    reason = re.search(r'<td class="c-reason">.*?</td>', row)
    assert reason is not None
    bare = row.replace(reason.group(0), '<td class="c-reason">–</td>')
    assert problems(bare) == [f"row {key}: cell reason is a dash without an explained reason"]
    empty = row.replace(reason.group(0), '<td class="c-reason"> </td>')
    assert problems(empty) == [f"row {key}: cell reason is empty"]
    rule = re.search(r'<td class="c-rule mono">.*?</td>', row)
    assert rule is not None
    other = row.replace(rule.group(0), '<td class="c-rule mono">CORE-M99-99</td>')
    assert f"row {key}: rule cell differs from the finding's rule" in problems(other)
    unknown = "0" * len(key)
    changed = problems(row.replace(f'data-key="{key}"', f'data-key="{unknown}"'))
    finding = next(f for f in results.findings if f.key == key)
    total = sum(f.rule_id == finding.rule_id for f in results.findings)
    shown = min(total, MAX_ROWS_PER_RULE)
    assert changed == [
        f"row {unknown}: no finding with this key in results.json",
        f"{finding.rule_id}: {shown - 1} rows shown, expected {shown} of {total}",
    ]
    assert f"row {key}: shown 2 times" in problems(row + row)
    doubled = row.replace(rule.group(0), rule.group(0) + rule.group(0))
    assert f"row {key}: a cell class appears twice" in problems(doubled)


def test_threshold_cells_need_every_parameter_with_its_origin(results: Results) -> None:
    lang = "zh"
    tr = translator(lang).t
    document = render_report(results, lang)
    finding = next(f for f in results.findings if f.params)
    name = sorted(finding.params)[0]
    origin = tr(f"report.text.origin_{finding.params[name].origin}")
    row = _row(document, finding.key)
    cell = re.search(r'<td class="c-threshold">(.*?)</td>', row)
    assert cell is not None and f"({html_lib.escape(origin, quote=False)})" in cell.group(1)
    stripped = row.replace(cell.group(0), '<td class="c-threshold">5</td>')
    problems = g1.check_finding_rows(document.replace(row, stripped), results, lang).problems
    assert f"row {finding.key}: threshold cell lacks parameter {name} with its origin" in problems
    without = next(f for f in results.findings if not f.params and f.threshold is None)
    row = _row(document, without.key)
    cell = re.search(r'<td class="c-threshold">(.*?)</td>', row)
    assert cell is not None
    hidden = row.replace(cell.group(0), '<td class="c-threshold">x</td>')
    problems = g1.check_finding_rows(document.replace(row, hidden), results, lang).problems
    assert f"row {without.key}: threshold cell does not say that the rule has no threshold" in problems


def test_dataset_level_cells_say_so(results: Results) -> None:
    lang = "en"
    tr = translator(lang).t
    document = render_report(results, lang)
    finding = next(f for f in results.findings if f.file is None and not f.time_ranges)
    row = _row(document, finding.key)
    moved = row.replace(
        f'<td class="c-time">{html_lib.escape(tr("report.value.time_dataset"))}</td>',
        f'<td class="c-time">{tr("report.value.whole_file")}</td>',
    )
    assert moved != row
    problems = g1.check_finding_rows(document.replace(row, moved), results, lang).problems
    assert problems == [f"row {finding.key}: time cell does not say dataset level"]


def test_remainder_sentence_is_required(overflowing: Results) -> None:
    lang = "zh"
    tr = translator(lang).t
    document = render_report(overflowing, lang)
    rule, total = Counter(f.rule_id for f in overflowing.findings).most_common(1)[0]
    remainder = total - MAX_ROWS_PER_RULE
    sentence = tr("report.text.rule_more", count=remainder, rule=rule)
    group = re.search(rf'<div class="rule-group" data-rule="{rule}">.*?</div>', document, re.S)
    assert group is not None and sentence in html_lib.unescape(group.group(0))
    more = re.search(r'<p class="more">.*?</p>', group.group(0), re.S)
    assert more is not None
    cut = document.replace(group.group(0), group.group(0).replace(more.group(0), ""))
    assert g1.check_finding_rows(cut, overflowing, lang).problems == [
        f"{rule}: the sentence naming the remaining {remainder} findings is missing"
    ]
    last = ROW.findall(group.group(0))[-1]
    dropped = document.replace(_row(document, last), "")
    assert g1.check_finding_rows(dropped, overflowing, lang).problems == [
        f"{rule}: {MAX_ROWS_PER_RULE - 1} rows shown, expected {MAX_ROWS_PER_RULE} of {total}"
    ]


def test_oracle_uses_the_render_contract() -> None:
    """B1: the cell classes and the explained empty texts come from report/render.py, not from a copy."""
    assert g1.FINDING_CELLS is FINDING_CELLS and len(FINDING_CELLS) == 10
    assert g1.EXPLAINED_EMPTY is EXPLAINED_EMPTY
    assert all(translator(lang).has(key) for lang in LANGS for key in EXPLAINED_EMPTY)


# --- PDF: the independent reading (REP-00, A-08, A-27) ------------------------------------------------------


def _type0(
    base: str = "/ABCDEF+NotoSansSC-Regular",
    cid: str = "/CIDFontType2",
    files: tuple[str, ...] = ("/FontFile2",),
    tounicode: bool = True,
) -> DictionaryObject:
    descriptor = DictionaryObject({NameObject(name): NameObject("/x") for name in files})
    descendant = DictionaryObject(
        {NameObject("/Subtype"): NameObject(cid), NameObject("/FontDescriptor"): descriptor}
    )
    font = DictionaryObject(
        {
            NameObject("/Subtype"): NameObject("/Type0"),
            NameObject("/BaseFont"): NameObject(base),
            NameObject("/DescendantFonts"): ArrayObject([descendant]),
        }
    )
    if tounicode:
        font[NameObject("/ToUnicode")] = NameObject("/x")
    return font


def _simple(subtype: str, base: str = "/Helvetica") -> DictionaryObject:
    return DictionaryObject(
        {NameObject("/Subtype"): NameObject(subtype), NameObject("/BaseFont"): NameObject(base)}
    )


def test_only_embedded_subsets_of_the_report_fonts_pass() -> None:
    assert g1._font_problem(_type0()) is None
    assert g1._font_problem(_type0(base="/QWERTY+NotoSansSC-Bold")) is None
    for subtype in ("/Type1", "/TrueType", "/Type3", "/MMType1"):
        assert g1._font_problem(_simple(subtype)) == (
            f"font of subtype {subtype} (only embedded Type0 subsets are allowed)"
        )
    for base in (
        "/ABCDEF+Consolas",
        "/NotoSansSC-Regular",
        "/ABCDEF+NotoSansSC-Thin",
        "/abcdef+NotoSansSC-Bold",
    ):
        assert g1._font_problem(_type0(base=base)) == "a font that is no subset of the report fonts"
    assert g1._font_problem(_type0(tounicode=False)) == "a font without ToUnicode"
    assert g1._font_problem(_type0(cid="/CIDFontType0")) == "a Type0 font without a CIDFontType2 descendant"
    for files in ((), ("/FontFile3",), ("/FontFile2", "/FontFile3")):
        assert g1._font_problem(_type0(files=files)) == "a font that is not embedded as FontFile2"


def test_font_walk_enters_form_xobjects() -> None:
    inner = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F2"): _simple("/Type1")})})
    form = DictionaryObject({NameObject("/Subtype"): NameObject("/Form"), NameObject("/Resources"): inner})
    resources = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): _type0()}),
            NameObject("/XObject"): DictionaryObject({NameObject("/X1"): form}),
        }
    )
    found = list(g1._fonts(resources, set()))
    assert [str(font["/Subtype"]) for font in found] == ["/Type0", "/Type1"]


def test_page_counter_pattern() -> None:
    counter = g1._page_counter(3, 12)
    assert counter.search("x第3页/共12页y") and counter.search("3/12")
    assert not counter.search("3/120") and not counter.search("3/112") and not counter.search("13/12")
    assert not g1._page_counter(13, 12).search("3/12")


@pytest.fixture(scope="module")
def printed(results: Results, pdf_shell: object, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The four reports of ``results`` written by the product (needs the browser)."""
    folder = tmp_path_factory.mktemp("acceptance_pdf")
    write_reports(results, list(LANGS), ["html", "pdf"], folder, environ=os.environ)
    return folder


@pytest.mark.pdf
@pytest.mark.parametrize("lang", LANGS)
def test_check_pdf_accepts_the_printed_report(results: Results, printed: Path, lang: str) -> None:
    document = (printed / f"report.{lang}.html").read_text(encoding="utf-8")
    checked = g1.check_pdf((printed / f"report.{lang}.pdf").read_bytes(), lang, results, document)
    assert checked.problems == []
    assert checked.pages >= 3
    assert sorted(checked.info) == ["/CreationDate", "/Creator", "/ModDate", "/Producer", "/Title"]
    assert checked.info["/Title"] == translator(lang).t("report.title")


@pytest.mark.pdf
def test_check_pdf_names_metadata_and_page_defects(results: Results, printed: Path) -> None:
    document = (printed / "report.en.html").read_text(encoding="utf-8")
    data = (printed / "report.en.pdf").read_bytes()
    stamp = g1.pdf_date(AS_OF).encode("ascii")
    assert data.count(stamp) == 2
    moved = data.replace(stamp, g1.pdf_date(date(2026, 10, 12)).encode("ascii"))  # same length (A-85)
    assert (
        "/CreationDate or /ModDate is not the reference date"
        in g1.check_pdf(moved, "en", results, document).problems
    )
    writer = pypdf.PdfWriter(clone_from=io.BytesIO(data))
    writer.add_metadata({"/Subject": "a dataset name"})
    buffer = io.BytesIO()
    writer.write(buffer)
    problems = g1.check_pdf(buffer.getvalue(), "en", results, document).problems
    assert "/Info keys are not exactly Title Creator Producer CreationDate ModDate" in problems
    wrong = g1.check_pdf(data, "zh", results, document).problems  # the other language's texts
    assert "page 1: the fixed sentence is missing" in wrong and "page 1: the running head is missing" in wrong
    assert g1.check_pdf(b"%PDF-1.7 broken", "en", results, document).problems[-1].startswith("not readable")


# --- privacy (NG-N05, A-51) ---------------------------------------------------------------------------------


def test_header_values_of_an_identifying_edf() -> None:
    found = {
        (item.label, item.value, item.kind)
        for item in g1.header_values(FIX / "edf_identifying" / "rec_named.edf")
    }
    assert found == {
        ("EDF/BDF header value", "Zhang San 01-JAN-1980", "literal"),
        ("EDF/BDF header subfield", "Zhang", "word"),
        ("EDF/BDF header subfield", "San", "word"),
        ("EDF/BDF header subfield", "01-JAN-1980", "word"),
        ("recording date", "24.08.21", "literal"),
        ("recording date", "2021-08-24", "literal"),
        ("recording date", "24-AUG-2021", "literal"),
    }


def test_header_values_skip_placeholders_and_the_reference_date(tmp_path: Path) -> None:
    edf = tmp_path / "rec.edf"
    write_edf(edf, startdate="11.10.26", recording="Startdate 11-OCT-2026 X Tech_Li EEG-1200")
    found = {(item.label, item.value) for item in g1.header_values(edf, AS_OF)}
    assert ("recording date", "2026-10-11") not in found  # the report shows the reference date
    assert ("EDF/BDF header subfield", "Tech_Li") in found and ("EDF/BDF header subfield", "X") not in found
    write_edf(edf)  # 'X X X X', 'Startdate X X X X', 01.01.85
    assert {label for label, _value in {(i.label, i.value) for i in g1.header_values(edf)}} == {
        "recording date"
    }


def test_privacy_finds_every_spelling_and_never_shows_the_value(results: Results, tmp_path: Path) -> None:
    dataset = tmp_path / "Daten" / "ds"
    forbidden = [g1.Forbidden("data set path", form, "path") for form in g1._path_forms(dataset)]
    forbidden += [
        g1.Forbidden("user name", "zhangsan", "word"),
        g1.Forbidden("EDF/BDF header value", "Zhang San 01-JAN-1980", "literal"),
    ]
    clean = [g1.Output("report.en.html", "nothing here; zhangsanfeng is another word")]
    assert g1.check_privacy(clean, forbidden, results) == []
    leaks = [
        g1.Output("a", f"file {str(dataset).replace(os.sep, '/').upper()}/x.edf"),
        g1.Output("b", json.dumps({"path": str(dataset)})),
        g1.Output("c", "reviewed by ZhangSan."),
        g1.Output("d.pdf", "", raw=b"BT " + "Zhang San 01-JAN-1980".encode("utf-16-be") + b" ET"),
        g1.Output("e.pdf", "", info={"/Title": "Zhang San 01-JAN-1980"}),
        g1.Output("manifest.json", "Zhang San 01-JAN-1980 " + str(dataset), manifest=True),
    ]
    problems = g1.check_privacy(leaks, forbidden, results)
    assert problems == [
        "a: contains a data set path",
        "b: contains a data set path",
        "c: contains a user name",
        "d.pdf: contains a EDF/BDF header value",
        "e.pdf: contains a EDF/BDF header value",
        "manifest.json: contains a data set path",  # the manifest names files by design, never paths (A-82)
    ]
    assert not any("Zhang" in problem or "Daten" in problem for problem in problems)


def test_hex_runs_other_than_the_declared_digests(results: Results) -> None:
    keys = {finding.key for finding in results.findings}
    digests = g1.declared_digests(results)
    declared = f"{sorted(keys)[0]} {results.config.canonical_sha256} {results.rulepacks[0].sha256[:24]}"
    assert g1.unexpected_digests(declared, keys, digests) == 0
    assert g1.unexpected_digests("signal hash 0123456789abcdef0123", keys, digests) == 1
    font = "src: url(data:font/ttf;base64,AAAA0123456789abcdef0123456789abcdefAAAA)"
    assert g1.unexpected_digests(font, keys, digests) == 0
    output = g1.Output("results.json", "x 00ff00ff00ff00ff00ff y")
    assert g1.check_privacy([output], [], results) == [
        "results.json: 1 hex digest(s) results.json does not declare"
    ]
    assert g1.check_privacy([output], [], results, extra={"aa00ff00ff00ff00ff00ffbb"}) == []


def test_ages_only_as_counts_or_groups(tmp_path: Path) -> None:
    assert g1.age_problems({"ages": {"30-39": 2, "90+": 1}, "age": None, "n_age": 3, "stage": "N2"}) == []
    assert g1.age_problems({"demographics": {"age": "34"}}) == [
        "/demographics/age holds a value that is no count"
    ]
    assert g1.age_problems([{"age": 34.5}]) == ["/0/age holds a value that is no count"]
    assert g1.age_problems({"age_groups": {"34": 1}}) == [
        "/age_groups holds more than 10-year groups with counts"
    ]
    (tmp_path / "participants.tsv").write_text(
        "participant_id\tage\tsex\nsub-01\t34\tF\nsub-02\tn/a\tM\nsub-03\t34.5\tF\n", encoding="utf-8"
    )
    assert g1.raw_ages(tmp_path) == ["34", "34.5"]
    forbidden = g1.forbidden_values(tmp_path, tmp_path / "out")
    assert [item.value for item in forbidden if item.label == "raw age"] == ["34.5"]
    assert g1._matches("mean 34.5 years", forbidden[[i.label for i in forbidden].index("raw age")])
    assert not g1._matches("version 134.56", g1.Forbidden("raw age", "34.5", "number"))


# --- determinism, V-01 and the summary (NG-N03, V-01, V-06) ------------------------------------------------


def test_compare_runs_per_file(tmp_path: Path) -> None:
    first, second = tmp_path / "1", tmp_path / "2"
    for folder in (first, second):
        folder.mkdir()
        (folder / "results.json").write_bytes(b"{}\n")
        (folder / "report.en.pdf").write_bytes(b"%PDF")
    (second / "report.en.pdf").write_bytes(b"%PDF ")
    names = ("results.json", "report.en.pdf", "report.zh.pdf")
    assert g1.compare_runs(first, second, names) == {
        "results.json": True,
        "report.en.pdf": False,
        "report.zh.pdf": False,
    }


MATRIX = """\
| ID | Anforderung | Status | Nachweis |
|----|-------------|--------|----------|
| NG-F01 | Formate | erfüllt | x |
| NG-F13 | Bericht | in Arbeit | y |

Text between the tables.

| ID | Kurz | Status |
|---|---|---|
| M01 | Lesbarkeit | erfüllt |
"""


def test_matrix_status_reads_every_table() -> None:
    assert g1.matrix_status(MATRIX) == {"NG-F01": "erfüllt", "NG-F13": "in Arbeit", "M01": "erfüllt"}


def _entry(**changes: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "check_exit": 1,
        "read_errors": 0,
        "formats": list(g1.FORMATS),
        "is_bids": True,
        "validator_evaluated": True,
        "v06": [],
        "report_problems": [],
        "json_problems": [],
    }
    entry.update(changes)
    return entry


def test_v01_checklist_needs_matrix_and_run() -> None:
    rows = ["NG-F01", "NG-F02", "NG-F05", *g1.METRIC_ROWS, "RP-09", *g1.GX_ROWS, "NG-F13", "NG-F14"]
    statuses = dict.fromkeys(rows, "erfüllt")
    items = g1.v01_checklist(statuses, [_entry()], True)
    assert [item["status"] for item in items] == ["fulfilled"] * 7
    assert all(item["evidence"] for item in items)
    items = g1.v01_checklist({**statuses, "M07": "in Arbeit"}, [_entry()], True)
    assert [item["item"] for item in items if item["status"] != "fulfilled"] == ["metrics"]
    items = g1.v01_checklist(statuses, [_entry(report_problems=["en: row x"], formats=["EDF"])], True)
    assert [item["item"] for item in items if item["status"] != "fulfilled"] == ["five_formats", "report"]
    items = g1.v01_checklist(statuses, [_entry(validator_evaluated=False, json_problems=["x"])], True)
    assert [item["item"] for item in items if item["status"] != "fulfilled"] == ["structure_check", "json"]
    items = g1.v01_checklist(statuses, [_entry(v06=[f"a {g1.NORM} rule is loaded"])], False)
    assert [item["item"] for item in items if item["status"] != "fulfilled"] == ["rulepacks", "report"]


def test_v01_items_without_a_run_criterion_say_so() -> None:
    """The G1 run never converts (item 2) and has no criterion of its own for the metrics (item 4): those two
    rest on the matrix rows and their tests, and the run column says that no run criterion applies instead of
    a "ja" the run never checked. Every other item has one, and its evidence names it ("G1-Lauf")."""
    rows = ["NG-F01", "NG-F02", "NG-F05", *g1.METRIC_ROWS, "RP-09", *g1.GX_ROWS, "NG-F13", "NG-F14"]
    statuses = dict.fromkeys(rows, "erfüllt")
    without = {"bids_conversion", "metrics"}
    for entries in ([_entry()], [_entry(formats=["EDF"], validator_evaluated=False, v06=["x"])], []):
        items = {item["item"]: item for item in g1.v01_checklist(statuses, entries, True)}
        assert {name for name, item in items.items() if item["run_ok"] is None} == without
        for item in items.values():
            assert (item["run_ok"] is not None) == ("G1-Lauf" in item["evidence"]), item["item"]
    items = {item["item"]: item for item in g1.v01_checklist(statuses, [], False)}
    assert items["bids_conversion"]["status"] == items["metrics"]["status"] == "fulfilled"  # matrix rows
    assert items["five_formats"]["status"] == "not_fulfilled"  # no data set ran: the run criterion fails
    open_f02 = {**statuses, "NG-F02": "offen"}
    items = {item["item"]: item for item in g1.v01_checklist(open_f02, [_entry()], True)}
    assert items["bids_conversion"]["status"] == "not_fulfilled"
    markdown = g1.summary_markdown(_summary())
    table = [line for line in markdown.splitlines() if re.match(r"^\| [1-7] \| ", line)]
    cells = {row[0]: row for row in ([c.strip() for c in line.strip("|").split("|")] for line in table)}
    assert sorted(cells) == [str(n) for n in range(1, 8)]
    for number, row in cells.items():  # Nr. | Punkt | Status | Matrix | Lauf | Nachweis
        assert row[4] in ((g1.NO_RUN_CRITERION,) if number in ("2", "4") else ("ja", "nein")), row


def test_v06_problems(results: Results) -> None:
    assert g1.v06_problems(results, ["Pre-check with NeuroGrid."]) == []
    # a made-up clause number after the norm's name (the norm text was never available, D-02)
    assert g1.v06_problems(results, [f"see {g1.NORM}-2026 clause 5.3.2"]) == [
        f"an output cites a {g1.NORM} clause"
    ]
    fewer = results.model_copy(update={"rulepacks": results.rulepacks[:1]})
    assert g1.v06_problems(fewer, []) == [
        f"loaded packs are {results.rulepacks[0].name}, not core, bids, gxdsl008"
    ]


def _summary() -> dict[str, object]:
    entry = {
        **_entry(),
        "name": "ds-x",
        "recordings": 2,
        "report_exit": 0,
        "errors": 1,
        "warnings": 2,
        "findings": 3,
        "rows_checked": {"zh": 3, "en": 3},
        "pdf_pages": {"zh": 9, "en": 10},
        "seconds": {"run1": {"check": 1.5, "report": 2.5}, "run2": {"check": 1.4, "report": 2.4}},
        "bytes": {
            "report.zh.html": 2000,
            "report.en.html": 1000,
            "report.zh.pdf": 5000,
            "report.en.pdf": 4000,
        },
        "identical": True,
        "problems": [],
        "ok": True,
    }
    jobs1 = {
        "dataset": g1.JOBS1_DATASET,
        "exit": 1,
        "identical": True,
        "check_s": 3.0,
        "problems": [],
        "ok": True,
    }
    return g1._summary([entry], jobs1, True, runs=2, jobs=4, as_of=AS_OF)


def test_summary_files_hold_no_paths(tmp_path: Path) -> None:
    summary = _summary()
    assert summary["g1"]["minimum_met"] is False and summary["g1"]["criteria_met"] is False  # 1 data set
    g1.write_summary(tmp_path, summary)
    text = (tmp_path / "summary.json").read_text(encoding="utf-8")
    assert json.loads(text)["schema"] == g1.SUMMARY_SCHEMA
    markdown = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert (
        "| ds-x | EDF, BDF, BrainVision, EEGLAB, FIF | 2 | 1 / 0 | 1 / 2 | 3 | 3 / 3 | 9 / 10 |" in markdown
    )
    for written in (text, markdown):
        assert str(tmp_path) not in written and str(Path.home()) not in written
        assert not g1.DRIVE_PATH.search(written)
    g1.write_summary(tmp_path / ".", summary)
    assert (tmp_path / "summary.json").read_text(encoding="utf-8") == text  # deterministic


def test_output_folder_must_be_empty_or_an_earlier_run(tmp_path: Path) -> None:
    out = tmp_path / "g1"
    g1._prepare_out(out, 2, replace=False)  # created
    (out / "run1").mkdir()
    (out / "summary.json").write_text("{}", encoding="utf-8")
    with pytest.raises(g1.ToolError, match="not empty"):
        g1._prepare_out(out, 2, replace=False)
    g1._prepare_out(out, 2, replace=True)
    assert list(out.iterdir()) == []
    (out / "notes.txt").write_text("mine", encoding="utf-8")
    with pytest.raises(g1.ToolError, match="something else"):
        g1._prepare_out(out, 2, replace=True)
    assert (out / "notes.txt").is_file()  # never removed


def test_tool_error_is_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert g1.main(["--corpus", str(tmp_path / "missing"), "--out", str(tmp_path / "out")]) == 2
    assert "the corpus folder does not exist" in capsys.readouterr().err
    (tmp_path / "corpus").mkdir()
    assert (
        g1.main(["--corpus", str(tmp_path / "corpus"), "--out", str(tmp_path / "o"), "--datasets", "x"]) == 2
    )
    assert "unknown data set(s): x" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        g1.main(["--corpus", str(tmp_path / "corpus"), "--out", str(tmp_path / "o"), "--runs", "1"])


def test_v01_evidence_names_existing_tests() -> None:
    """Every test the V-01 checklist cites as evidence exists (no invented evidence)."""
    root = Path(__file__).parent.parent.parent
    cited = [part.strip() for *_rest, evidence in g1.V01_ITEMS for part in evidence.split(";")]
    named = [part for part in cited if part.startswith("tests/")]
    assert len(named) >= 7
    for reference in named:
        path, _sep, name = reference.partition("::")
        source = (root / path).read_text(encoding="utf-8")
        assert not name or re.search(rf"^def {re.escape(name)}\(", source, re.M), reference


def test_summary_names_what_the_run_covers_and_what_it_does_not(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """KONZEPT §6 G1: the run checks only part of the G1 criterion. summary.md says 'criteria of this run'
    and names the parts with evidence of their own (scaling test, Linux offline + strace, clean room,
    coverage), so 'ja' never reads as the whole G1 criterion being met; summary.json lists them as well."""
    summary = _summary()
    markdown = g1.summary_markdown(summary)
    assert "- Alle Kriterien erfüllt:" not in markdown
    assert "- Alle Kriterien dieses Laufs erfüllt: nein" in markdown
    outside = [line for line in markdown.splitlines() if line.startswith("- Nicht Teil dieses Laufs")]
    assert len(outside) == 1
    for part in ("1000 × 64", "strace", "debian:12-slim --network none", "Kern ≥ 90 %", "Prüfer ≥ 80 %"):
        assert part in outside[0], part
    assert summary["g1"]["outside_this_run"] == list(g1.OUTSIDE_THIS_RUN)
    monkeypatch.setattr(g1, "run_acceptance", lambda *args, **kwargs: summary)
    assert g1.main(["--corpus", str(tmp_path), "--out", str(tmp_path / "out")]) == 1
    printed = capsys.readouterr().out
    assert "all criteria of this run NOT met" in printed and "outside this run:" in printed


def test_unreadable_recordings_do_not_count_towards_the_minimum(tmp_path: Path) -> None:
    """KONZEPT §6 G1 / NG-F01: a data set whose recordings fail CORE-M01 has not been checked, so neither it
    nor its formats count towards '≥ 3 data sets in ≥ 2 formats', and the entry names the reason."""
    readable = {**_summary()["datasets"][0], "problems": [], "ok": True}  # type: ignore[index]
    names = ("ds-a", "ds-b", "ds-c")
    formats = ("EDF", "BDF", "EDF")
    good = [{**readable, "name": n, "formats": [f]} for n, f in zip(names, formats, strict=True)]
    summary = g1._summary(good, None, True, runs=2, jobs=4, as_of=AS_OF)
    assert summary["g1"]["minimum_met"] and summary["g1"]["formats_ok"] == ["BDF", "EDF"]
    unreadable = [{**entry, "read_errors": entry["recordings"]} for entry in good]
    summary = g1._summary(unreadable, None, True, runs=2, jobs=4, as_of=AS_OF)
    assert summary["g1"]["datasets_ok"] == 0 and summary["g1"]["formats_ok"] == []
    assert summary["g1"]["minimum_met"] is False and summary["g1"]["criteria_met"] is False
    one = [good[0], {**good[1], "read_errors": 1}, good[2]]  # the only BDF data set is not readable
    summary = g1._summary(one, None, True, runs=2, jobs=4, as_of=AS_OF)
    assert summary["g1"]["formats_ok"] == ["EDF"] and summary["g1"]["minimum_met"] is False
    (tmp_path / "run1" / "ds-x").mkdir(parents=True)
    evaluation = g1.DatasetEval(stats={"read_errors": 2, "formats": ["BDF"], "recordings": 2})
    same = dict.fromkeys(g1.PRODUCT_FILES, True)
    entry = g1._entry("ds-x", tmp_path, [evaluation], {}, {"check": 1}, same)
    assert entry["ok"] is False
    assert "read: 2 failed readability findings (CORE-M01-01..04)" in entry["problems"]


# --- the fixed sentence in the HTML reports (REP-07, A-08) --------------------------------------------------


@pytest.mark.parametrize("lang", LANGS)
def test_html_reports_carry_the_fixed_sentence(results: Results, lang: str) -> None:
    """REP-07/A-08: the fixed sentence is visible on the cover and in the appendix and is the meta
    description; a copy in the print CSS (@page) alone does not count."""
    document = render_report(results, lang)
    assert g1.check_html(document, lang) == []
    sentence = html_lib.escape(disclaimer(lang), quote=False)
    paragraph = f'<p class="disclaimer">{sentence}</p>'
    assert document.count(paragraph) == 2
    cover, appendix = (document.index(paragraph), document.rindex(paragraph))
    no_cover = document[:cover] + document[cover:].replace(paragraph, "<p></p>", 1)
    assert g1.check_html(no_cover, lang) == ["the fixed sentence is missing on the cover"]
    no_appendix = document[:appendix] + document[appendix:].replace(paragraph, "<p></p>", 1)
    assert g1.check_html(no_appendix, lang) == ["the fixed sentence is missing in the appendix"]
    meta = f'<meta name="description" content="{html_lib.escape(disclaimer(lang))}">'
    assert meta in document
    no_meta = document.replace(meta, '<meta name="description" content="">')
    assert g1.check_html(no_meta, lang) == ["the meta description is not the fixed sentence"]
    css_only = document.replace(paragraph, "<p></p>").replace(meta, "")
    assert disclaimer(lang) in css_only  # still in @page content of the print CSS
    assert g1.check_html(css_only, lang) == [
        "the fixed sentence is missing on the cover",
        "the fixed sentence is missing in the appendix",
        "the meta description is not the fixed sentence",
    ]
    other = "zh" if lang == "en" else "en"
    assert "the fixed sentence is missing on the cover" in g1.check_html(document, other)
