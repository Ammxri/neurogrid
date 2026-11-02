"""The evidence dossier (REP-08, V-03; A-35, A-99): ``report --format dossier`` writes ``dossier.pdf``, one
PDF of three parts, always in both report languages, whatever --lang says (A-35):

1. the index part (report/templates/dossier.html.j2), bilingual: the title, the fixed sentence in zh and en
   in the footer of every page, the dataset (name, ID, version), the reference date, the tool version, the
   SHA-256 of the results.json bytes, the parts with their page ranges, the evidence list of
   results.evidence (rule, document, status, SHA-256 computed and recorded), the manifest summary of
   results.manifest and the NeuroVault summary: the status counts of every rule of the access phase as
   appendix 6.1 shows them and, with ``report --config``, the access log row of the cover;
2. the zh report and 3. the en report, exactly as ``report --format pdf`` prints them (the same vault view).

Each part is printed and passes the QA gate like a report (report.output prints them with one browser). The
page ranges need the page counts of the reports, which are printed first; the index part is rendered until
its own page count is stable (at most MAX_INDEX_PASSES prints). kernel.pdf.merge_pdfs joins the parts: the
merged file carries exactly Title (dossier_title), Creator and Producer "NeuroGrid <version>" and the
reference date as CreationDate and ModDate, no XMP and no outline, and passes the QA gate again (fonts,
metadata, glyphs, the fixed sentence of at least one language on every page, page count = the sum of the
parts). The same results.json, vault view and NeuroGrid version give byte-identical dossiers.

Privacy (A-51, D-17 option B): the dossier holds what the two reports hold and counts from results.json:
never signals, consent records or subject IDs beyond those the reports show (M11/M12). A rule on a consent
check appears in the NeuroVault summary as in appendix 6.1: a withheld breakdown as its total only (A-81).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from functools import lru_cache
from typing import Any

from markupsafe import Markup

import neurogrid
from neurogrid.kernel.errors import PdfError
from neurogrid.kernel.evidence import EvidenceRecord, EvidenceState
from neurogrid.kernel.findings import Phase, SourceStatus, Status
from neurogrid.kernel.fonts import FONT_FAMILY, font_codepoints, postscript_names, subset_font_css
from neurogrid.kernel.pdf import PdfExpect, PdfMeta, html_title, merge_pdfs, page_count, qa_gate
from neurogrid.kernel.provenance import ManifestStatus
from neurogrid.kernel.report import render_html
from neurogrid.model.results import Results, RuleInfo
from neurogrid.report import tables
from neurogrid.report.glyphs import glyph_safe
from neurogrid.report.identify import dossier_title
from neurogrid.report.output import glyph_safe_document
from neurogrid.report.render import TEMPLATE_DIR, VaultView, css_string, report_coverage
from neurogrid.report.texts import FONT_FILES, REPORT_LANGUAGES, disclaimer, translator

DOSSIER_LANGUAGES = REPORT_LANGUAGES  # zh, then en: the order of the report parts (A-35)
MAX_INDEX_PASSES = 3
INDEX_LOCALE = "zh-CN"  # the browser locale of the bilingual index part (not observable in the PDF, A-85)
TEMPLATE = "dossier.html.j2"
# Prints one HTML document and returns the PDF after the QA gate with ``expect`` (report.output).
PrintPart = Callable[[str, PdfExpect], bytes]


def _finalize(value: Any) -> Any:
    """As report.render: text glyph-safe, Markup as it is."""
    if isinstance(value, Markup) or not isinstance(value, str):
        return value
    return glyph_safe(value, report_coverage())


def both(key: str, **params: Any) -> list[str]:
    """The text ``key`` in every dossier language, zh first."""
    return [translator(lang).t(key, **params) for lang in DOSSIER_LANGUAGES]


def label(key: str, **params: Any) -> str:
    """A bilingual label: 'zh / en'."""
    return " / ".join(both(key, **params))


def running_head(as_of: str) -> str:
    return f"{dossier_title()} · {as_of}"


def page_css(as_of: str) -> str:
    """A4 portrait with the margin boxes of the report (report.render.page_css): the running head, the fixed
    sentence of both languages on two lines (A-08) and the page counter in digits."""
    family = f"font-family: '{FONT_FAMILY}';"
    box = f"{family} font-weight: 400; font-style: normal; font-size: 7.5pt; color: #333;"
    sentences = "\n".join(disclaimer(lang) for lang in DOSSIER_LANGUAGES)
    return (
        "@page { size: A4 portrait; margin: 16mm 13mm 24mm 13mm; "
        f"@top-left {{ content: {css_string(running_head(as_of))}; {box} }} "
        f"@bottom-left {{ content: {css_string(sentences)}; {box} width: 80%; vertical-align: top; "
        "white-space: pre-wrap; } "
        f'@bottom-right {{ content: counter(page) " / " counter(pages); {box} vertical-align: top; }} }}\n'
    )


def page_text(as_of: str) -> str:
    """The texts that appear only in the margin boxes, with every digit, for the font subsets."""
    digits = "0123456789"
    return "\n".join(
        (*(disclaimer(lang) for lang in DOSSIER_LANGUAGES), running_head(digits + "-"), digits + " /", as_of)
    )


@lru_cache(maxsize=1)
def _static_css() -> str:
    return (TEMPLATE_DIR / "report.css").read_text(encoding="utf-8")


# --- the index part -------------------------------------------------------------------------------------


def _cover_rows(results: Results, results_sha256: str) -> list[tuple[str, list[str], bool]]:
    dataset = results.dataset
    return [
        (
            label("report.label.dataset"),
            [dataset.name] if dataset.name else both("report.value.name_missing"),
            False,
        ),
        (label("report.label.dataset_id"), [dataset.id], True),
        (
            label("report.label.version"),
            [dataset.version] if dataset.version else both("report.value.version_missing"),
            False,
        ),
        (label("report.label.date"), [results.config.as_of.isoformat()], False),
        (label("report.label.tool_version"), [f"NeuroGrid {results.tool.version}"], False),
        (label("report.dossier.source_hash"), [results_sha256], True),
    ]


def _part_rows(pages: Sequence[int]) -> list[tuple[str, str]]:
    """(part, 'first–last' in the dossier) for the index part and the two reports."""
    rows = []
    first = 1
    for key, count in zip(
        ("report.dossier.part.index", *(f"report.dossier.part.{lang}" for lang in DOSSIER_LANGUAGES)),
        pages,
        strict=True,
    ):
        rows.append((label(key), f"{first}–{first + count - 1}"))
        first += count
    return rows


def _evidence_status(record: EvidenceRecord, rule: RuleInfo | None) -> list[str]:
    """As section 5 of the report: 'provided' reads as the user's statement, never as passed (A-15)."""
    if rule is not None and rule.source_status is SourceStatus.PLACEHOLDER:
        return both("report.value.placeholder_status")
    if record.status is EvidenceState.PROVIDED and record.outcome is Status.PASSED:
        return both("report.value.evidence_provided")
    return both(f"status.{record.outcome.value}")


def _evidence_rows(results: Results) -> list[dict[str, Any]]:
    rules = {rule.id: rule for rule in results.rules}
    none = translator(DOSSIER_LANGUAGES[0]).t("report.value.none")
    return [
        {
            "rule": record.rule_id,
            "rulepack": record.rulepack,
            "document": record.document or none,
            "status": _evidence_status(record, rules.get(record.rule_id)),
            "sha256": record.sha256 or none,
            "sha256_recorded": record.sha256_recorded or none,
        }
        for record in results.evidence
    ]


COMPARED = (ManifestStatus.MATCHES, ManifestStatus.DIFFERS)  # a check compared the files: the counts hold


def _manifest_hash_missing(status: list[str]) -> list[str]:
    """report.value.manifest_hash_missing in each language with the status in that language."""
    return [
        translator(lang).t("report.value.manifest_hash_missing", status=text)
        for lang, text in zip(DOSSIER_LANGUAGES, status, strict=True)
    ]


def _manifest_rows(results: Results) -> list[tuple[str, list[str], bool]]:
    """The manifest block of results.json (A-82): hash, status, files and, after a comparison, the counts of
    deviating paths (never paths)."""
    info = results.manifest
    if info is None:
        return [(label("report.label.manifest_status"), both("report.value.manifest_block_missing"), False)]
    status = both(f"report.manifest_status.{info.status.value}")
    rows = [
        (
            label("report.label.manifest_hash"),
            [info.sha256] if info.sha256 else _manifest_hash_missing(status),
            info.sha256 is not None,
        ),
        (label("report.label.manifest_status"), status, False),
    ]
    if info.files is not None:
        values = (
            both(
                "report.dossier.manifest_counts",
                files=info.files,
                changed=info.changed,
                new=info.new,
                missing=info.missing,
                skipped_changed=info.skipped_changed,
                unreadable=info.unreadable,
            )
            if info.status in COMPARED
            else both("report.dossier.manifest_listed", files=info.files)
        )
        rows.append((label("report.dossier.manifest_files"), values, False))
    return rows


def _vault_rows(results: Results) -> list[dict[str, Any]]:
    """Every rule of the access phase with its counts per status as appendix 6.1 counts them; a rule on a
    consent check with a withheld breakdown only with its total (A-81, A-91), a placeholder rule as not
    evaluated (A-41)."""
    counts = tables.rule_counts(results)
    withheld = tables.withheld_consent_rules(results)
    rows = []
    for rule in results.rules:
        if rule.phase is not Phase.ACCESS:
            continue
        row: dict[str, Any] = {
            "id": rule.id,
            "title": [rule.title_zh, rule.title_en],
            "counts": [str(counts[rule.id][status]) for status in tables.COUNTED],
            "note": [],
        }
        if rule.source_status is SourceStatus.PLACEHOLDER:
            row["note"] = both("report.value.placeholder_status")
        elif rule.id in withheld:
            row["note"] = both("report.consent.overview_withheld", count=sum(counts[rule.id].values()))
        rows.append(row)
    return rows


def _access_log(view: VaultView) -> list[str]:
    """The access log row of the cover (``report --config``, A-30): entries, head hash, state."""
    lines = []
    for lang in DOSSIER_LANGUAGES:
        tr = translator(lang).t
        state = tr(f"report.value.access_log_state.{view.state}", deviations=view.deviations)
        if view.state not in ("intact", "broken"):
            lines.append(state)
        elif view.head is None:
            lines.append(tr("report.value.access_log_empty", state=state))
        else:
            lines.append(tr("report.value.access_log", events=view.events, head=view.head, state=state))
    return lines


def build_context(
    results: Results,
    *,
    results_sha256: str,
    vault: VaultView | None,
    pages: Sequence[int],
    font_css: str = "",
) -> dict[str, Any]:
    """``pages``: the page counts of the index part (as assumed) and of the zh and en report."""
    as_of = results.config.as_of.isoformat()
    css = Markup(font_css) + Markup(_static_css()) + Markup(page_css(as_of))
    return {
        "css": css,
        "title": dossier_title(),
        "title_lines": both("report.dossier.title"),
        "disclaimers": [disclaimer(lang) for lang in DOSSIER_LANGUAGES],
        "version": results.tool.version,
        "label": label,
        "both": both,
        "cover_rows": _cover_rows(results, results_sha256),
        "parts": _part_rows(pages),
        "evidence_rows": _evidence_rows(results),
        "manifest_rows": _manifest_rows(results),
        "vault_rows": _vault_rows(results),
        "statuses": [label(f"status.{status.value}") for status in tables.COUNTED],
        "access_log": _access_log(vault) if vault is not None else None,
    }


def index_document(
    results: Results, *, results_sha256: str, vault: VaultView | None, pages: Sequence[int]
) -> str:
    """The index part as one self-contained HTML document, rendered twice like a report (report.output): the
    first time for its characters, the second with the font subsets that cover them."""
    covered = font_codepoints(FONT_FILES)

    def render(font_css: str) -> str:
        context = build_context(
            results, results_sha256=results_sha256, vault=vault, pages=pages, font_css=font_css
        )
        return glyph_safe_document(render_html(TEMPLATE_DIR, TEMPLATE, context, finalize=_finalize), covered)

    draft = render("")
    css = subset_font_css(FONT_FILES, draft + page_text(results.config.as_of.isoformat()), family=FONT_FAMILY)
    return render(css)


def index_expectation(results: Results, document: str) -> PdfExpect:
    """The QA gate of the index part: the fixed sentence of both languages on every page, the title of both
    languages once."""
    return PdfExpect(
        meta=PdfMeta(title=html_title(document), as_of=results.config.as_of),
        fonts=postscript_names(FONT_FILES),
        every_page=tuple(disclaimer(lang) for lang in DOSSIER_LANGUAGES),
        once=tuple(both("report.dossier.title")),
    )


def build_dossier(
    results: Results,
    reports: Mapping[str, bytes],
    print_part: PrintPart,
    *,
    results_sha256: str,
    vault: VaultView | None,
) -> bytes:
    """dossier.pdf from the printed zh and en report (``reports``, QA-gated already) and the index part that
    ``print_part`` prints; PdfError pdf.qa_failed (exit 2) when the index part's page count does not settle
    (page_ranges) or the merged file fails the QA gate."""
    counts = [page_count(reports[lang]) for lang in DOSSIER_LANGUAGES]
    assumed = 1
    for _attempt in range(MAX_INDEX_PASSES):
        document = index_document(
            results, results_sha256=results_sha256, vault=vault, pages=(assumed, *counts)
        )
        index = print_part(document, index_expectation(results, document))
        printed = page_count(index)
        if printed == assumed:
            break
        assumed = printed
    else:
        raise PdfError("pdf.qa_failed", checks="page_ranges")
    meta = PdfMeta(title=dossier_title(), as_of=results.config.as_of)
    merged = merge_pdfs(
        [index, *(reports[lang] for lang in DOSSIER_LANGUAGES)],
        meta,
        producer=f"NeuroGrid {neurogrid.__version__}",
    )
    expect = PdfExpect(
        meta=meta,
        fonts=postscript_names(FONT_FILES),
        every_page_any=tuple(disclaimer(lang) for lang in DOSSIER_LANGUAGES),
    )
    violations = set(qa_gate(merged, expect))
    if page_count(merged) != assumed + sum(counts):
        violations.add("page_count")
    if violations:
        raise PdfError("pdf.qa_failed", checks=",".join(sorted(violations)))
    return merged
