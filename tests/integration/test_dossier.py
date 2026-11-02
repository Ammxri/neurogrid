"""The evidence dossier (REP-08, V-03; A-35, A-99): ``report --format dossier`` writes dossier.pdf, an index
part and the zh and en report in one PDF, whatever --lang says.

The checks read the PDF with their own pypdf calls, not with the QA gate they test (B2). Tests that print are
marked ``pdf``: skipped without the browser, failing without it when NEUROGRID_REQUIRE_PDF=1.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
from datetime import date
from pathlib import Path
from typing import Any

import pypdf
import pytest
from pypdf.generic import DictionaryObject

from conftest import DOCUMENTED_TOML  # type: ignore[import-not-found]
from neurogrid import __version__, pipeline
from neurogrid.cli import main
from neurogrid.kernel import pdf
from neurogrid.kernel.errors import PdfError
from neurogrid.model.results import Results
from neurogrid.report.identify import IdentifiedReport, dossier_title, identify
from neurogrid.report.output import write_reports
from neurogrid.report.texts import disclaimer, translator

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"
AS_OF = "2026-10-11"
STAMP = "D:20261011000000+00'00'"
SUBJECTS = ("01", "02", "03", "04", "05", "06")  # bids_ai_ok
SOP = b"IT security SOP 12 (synthetic test document)\n"
# Planted identifiers (A-51): a subject that only the consent records know and an ethics approval reference;
# neither may reach the dossier (D-17 option B: consent data never leave results.json and the vault).
PLANTED_SUBJECT = "Planted4711"
PLANTED_REF = "EthicsToken9931"
REPORT_FONT = re.compile(r"^/[A-Z]{6}\+NotoSansSC-(Regular|Bold)$")


def run(args: list[str]) -> int:
    try:
        main(["--lang", "en", *args])
    except SystemExit as exc:
        return int(exc.code or 0)
    return 0


def _squeeze(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _texts(data: bytes) -> list[str]:
    return [page.extract_text() or "" for page in pypdf.PdfReader(io.BytesIO(data)).pages]


def _fonts(resources: Any, found: set[str]) -> None:
    """Own walk over the fonts of a resource dictionary and its forms (test oracle)."""
    resources = resources.get_object() if resources is not None else None
    if not isinstance(resources, DictionaryObject):
        return
    for ref in (resources.get("/Font") or {}).values():
        font = ref.get_object()
        found.add(f"{font.get('/Subtype')} {font.get('/BaseFont')}")
    for ref in (resources.get("/XObject") or {}).values():
        if ref.get_object().get("/Subtype") == "/Form":
            _fonts(ref.get_object().get("/Resources"), found)


@pytest.fixture(scope="module")
def checked(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """bids_ai_ok with a vault (consents of every subject plus a planted one), a manifest and the evidence of
    GXDSL008-ACC-001 with its document, checked with core and gxdsl008."""
    tmp = tmp_path_factory.mktemp("dossier")
    folder = tmp / "data"
    shutil.copytree(FIX / "bids_ai_ok", folder)
    toml = folder / ".neurogrid" / "neurogrid.toml"
    toml.write_text(DOCUMENTED_TOML, encoding="utf-8")
    assert run(["vault", "init", str(folder)]) == 0
    for subject in (*SUBJECTS, PLANTED_SUBJECT):
        fields = ["--date", "2026-03-01", "--uses", "training,validation", "--ethics-ref", PLANTED_REF]
        add = ["vault", "consent", "add", str(folder), "--subject", subject, "--version", "1"]
        assert run([*add, "--role", "data_steward", *fields]) == 0
    assert run(["manifest", str(folder)]) == 0
    (tmp / "docs").mkdir()
    (tmp / "docs" / "it-security-sop.pdf").write_bytes(SOP)
    evidence = tmp / "evidence.yaml"
    evidence.write_text(
        "format_version: 1\nevidence:\n  GXDSL008-ACC-001:\n    status: provided\n"
        f"    document: docs/it-security-sop.pdf\n    sha256: {hashlib.sha256(SOP).hexdigest()}\n"
        "    reviewer: QA lead\n    date: 2026-10-01\n",
        encoding="utf-8",
    )
    results = tmp / "results.json"
    code = run(
        [
            "check",
            str(folder),
            "--rulepack",
            "gxdsl008",
            "--evidence",
            str(evidence),
            "--out",
            str(results),
            "--as-of",
            AS_OF,
        ]
    )
    assert code in (0, 1)
    return {"folder": folder, "toml": toml, "results": results, "tmp": tmp}


@pytest.fixture(scope="module")
def written(checked: dict[str, Path], pdf_shell: object) -> dict[str, bytes]:
    """``report --lang en --format pdf,dossier --config``: report.en.pdf and dossier.pdf (needs the browser:
    skipped or failed like every pdf test)."""
    out = checked["tmp"] / "报告 out"
    code = run(
        [
            "report",
            str(checked["results"]),
            "--lang",
            "en",
            "--format",
            "pdf,dossier",
            "--out",
            str(out),
            "--config",
            str(checked["toml"]),
        ]
    )
    assert code == 0
    assert sorted(path.name for path in out.iterdir()) == ["dossier.pdf", "report.en.pdf"]
    return {path.name: path.read_bytes() for path in out.iterdir()}


def _events(folder: Path) -> list[dict[str, Any]]:
    text = (folder / ".neurogrid" / "vault" / "access.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


@pytest.mark.pdf
def test_dossier_complete(written: dict[str, bytes], checked: dict[str, Path]) -> None:
    """DoD REP-08 (A-35, A-99): index part with the fixed sentence of both languages on every page, the
    dataset, the SHA-256 of results.json, the parts and their page ranges, the evidence list with both
    SHA-256, the manifest and the NeuroVault summary with the access log; then the zh and the en report,
    although --lang en; metadata, fonts and page count of the merged file."""
    dossier, english = written["dossier.pdf"], written["report.en.pdf"]
    reader = pypdf.PdfReader(io.BytesIO(dossier))
    assert dict(reader.metadata or {}) == {
        "/Title": dossier_title(),
        "/Creator": f"NeuroGrid {__version__}",
        "/Producer": f"NeuroGrid {__version__}",
        "/CreationDate": STAMP,
        "/ModDate": STAMP,
    }
    root = reader.trailer["/Root"].get_object()
    assert "/ID" not in reader.trailer and "/Metadata" not in root and "/Outlines" not in root
    fonts: set[str] = set()
    for page in reader.pages:
        _fonts(page.get("/Resources"), fonts)
    assert fonts and all(
        entry.startswith("/Type0 ") and REPORT_FONT.match(entry.split(" ", 1)[1]) for entry in fonts
    ), fonts
    texts = [_squeeze(text) for text in _texts(dossier)]
    zh, en = (_squeeze(disclaimer(lang)) for lang in ("zh", "en"))
    english_pages = [_squeeze(text) for text in _texts(english)]
    assert texts[-len(english_pages) :] == english_pages  # part 3 = the delivered en report
    zh_head = _squeeze(translator("zh").t("report.page.running_head", as_of=AS_OF))
    first_zh = next(number for number, text in enumerate(texts) if zh_head in text)
    index, chinese = texts[:first_zh], texts[first_zh : -len(english_pages)]
    assert index and chinese and len(texts) == len(index) + len(chinese) + len(english_pages)
    assert all(zh in text and en in text for text in index)  # the footer of the index part
    assert all(zh in text and en not in text for text in chinese)
    assert all(en in text for text in english_pages)
    whole = "".join(index)
    results = json.loads(checked["results"].read_bytes())
    sha = hashlib.sha256(SOP).hexdigest()
    for expected in (
        *(translator(lang).t("report.dossier.title") for lang in ("zh", "en")),
        results["dataset"]["name"],
        hashlib.sha256(checked["results"].read_bytes()).hexdigest(),
        "GXDSL008-ACC-001",
        "docs/it-security-sop.pdf",
        results["dataset"]["manifest_hash"],
        "CORE-NV03-01",
        "CORE-M14-01",
        _events(checked["folder"])[-2]["hash"],  # the head before the report's own event (A-30)
        *(translator(lang).t("report.dossier.not_included") for lang in ("zh", "en")),
        *(translator(lang).t("report.value.evidence_provided") for lang in ("zh", "en")),
    ):
        assert _squeeze(expected) in whole, expected
    assert whole.count(sha) == 2  # computed and recorded, one below the other
    first, middle = len(index), len(index) + len(chinese)
    for part, pages in (("index", f"1–{first}"), ("zh", f"{first + 1}–{middle}"), ("en", f"{middle + 1}–")):
        assert _squeeze(translator("en").t(f"report.dossier.part.{part}")) + "".join(pages) in whole, part
    assert f"{middle + 1}–{len(texts)}" in whole


@pytest.mark.pdf
def test_dossier_holds_no_consent_data(written: dict[str, bytes], checked: dict[str, Path]) -> None:
    """A-51, D-17 option B: neither the planted subject of the consent records nor the ethics approval
    reference reaches any page; the consent rule appears with its total only (withheld breakdown, A-81)."""
    whole = "".join(_squeeze(text) for text in _texts(written["dossier.pdf"]))
    for planted in (PLANTED_SUBJECT, f"sub-{PLANTED_SUBJECT}", PLANTED_REF):
        assert planted.lower() not in whole.lower(), planted
    results = json.loads(checked["results"].read_bytes())
    total = sum(1 for f in results["findings"] if f["rule_id"] == "CORE-M14-01")
    total += sum(p["count"] for p in results["passed"] if p["rule_id"] == "CORE-M14-01")
    assert total >= 6
    for lang in ("zh", "en"):
        withheld = translator(lang).t("report.consent.overview_withheld", count=total)
        assert _squeeze(withheld) in whole, lang


@pytest.mark.pdf
def test_dossier_and_reports_are_identified(written: dict[str, bytes]) -> None:
    """A-96: the export takes the dossier and the reports by their title and the QA gate."""
    assert identify(written["dossier.pdf"]) == IdentifiedReport("pdf", None)
    assert identify(written["dossier.pdf"]).name == "dossier.pdf"
    assert identify(written["report.en.pdf"]) == IdentifiedReport("pdf", "en")


@pytest.mark.pdf
def test_two_dossiers_byte_identical(checked: dict[str, Path], tmp_path: Path) -> None:
    """NG-N03, A-99: the same results.json gives the same dossier.pdf, whatever --lang says; written all or
    nothing next to the other formats."""
    data = checked["results"].read_bytes()
    results = Results.model_validate_json(data)
    sha = hashlib.sha256(data).hexdigest()
    first = write_reports(
        results, ["zh"], ["dossier"], tmp_path / "a", environ=os.environ, results_sha256=sha
    )
    second = write_reports(
        results, ["en"], ["html", "dossier"], tmp_path / "b", environ=os.environ, results_sha256=sha
    )
    assert [path.name for path in first] == ["dossier.pdf"]
    assert [path.name for path in second] == ["report.en.html", "dossier.pdf"]
    assert first[0].read_bytes() == second[1].read_bytes()
    assert (
        pdf.qa_gate(
            first[0].read_bytes(),
            pdf.PdfExpect(
                meta=pdf.PdfMeta(title=dossier_title(), as_of=date.fromisoformat(AS_OF)),
                fonts=("NotoSansSC-Regular", "NotoSansSC-Bold"),
                every_page_any=(disclaimer("zh"), disclaimer("en")),
            ),
        )
        == []
    )


def test_dossier_needs_the_browser_and_writes_nothing_without_it(tmp_path: Path) -> None:
    """A-26: the dossier is a PDF; without the browser exit 2 before anything is rendered, nothing written,
    html included."""
    results = pipeline.run_check(FIX / "bids_ok", pipeline.CheckOptions(as_of=date.fromisoformat(AS_OF)))
    environ = {pdf.ENV_BROWSER_DIR: str(tmp_path / "no-browser")}
    folder = tmp_path / "out"
    with pytest.raises(PdfError) as info:
        write_reports(results, ["en"], ["html", "dossier"], folder, environ=environ, results_sha256="0" * 64)
    assert info.value.message_key == "pdf.shell_missing" and not folder.exists()
    with pytest.raises(ValueError):
        write_reports(results, ["en"], ["dossier"], folder, environ=environ)


def test_report_dossier_without_the_browser_is_exit_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    results = pipeline.run_check(FIX / "bids_ok", pipeline.CheckOptions(as_of=date.fromisoformat(AS_OF)))
    source = tmp_path / "results.json"
    source.write_text(results.model_dump_json(), encoding="utf-8")
    monkeypatch.setenv(pdf.ENV_BROWSER_DIR, str(tmp_path / "no-browser"))
    out = tmp_path / "out"
    assert run(["report", str(source), "--format", "html,dossier", "--out", str(out)]) == 2
    assert "PDF browser" in capsys.readouterr().err and not out.exists()
