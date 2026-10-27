"""Reading the rendered report in tests: finding rows by data-key and cell class (B1 contract), sections and
the visible text. Standard library HTML parser, so the tests do not depend on the exact markup layout."""

from __future__ import annotations

import html as html_lib
import re
from html.parser import HTMLParser

from neurogrid.report.render import FINDING_CELLS


class _Rows(HTMLParser):
    """Collects every <tr data-key=...> with the text of its <td class="c-...">, unescaped."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict[str, str]] = []
        self._row: dict[str, str] | None = None
        self._cell: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "tr" and values.get("data-key"):
            self._row = {"key": values["data-key"] or ""}
        elif tag == "td" and self._row is not None:
            classes = (values.get("class") or "").split()
            self._cell = next((c[2:] for c in classes if c.startswith("c-")), None)
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._row is not None and self._cell is not None:
            self._row[self._cell] = "".join(self._text)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None


def finding_rows(html: str) -> list[dict[str, str]]:
    """The finding rows of a report: {'key': Finding.key, 'rule': ..., 'clause': ..., ...} per row."""
    parser = _Rows()
    parser.feed(html)
    return parser.rows


def section(html: str, name: str) -> str:
    """The markup of section ``name`` (cover, summary, findings, metrics, evidence, appendix)."""
    start = html.index(f'<section id="{name}">')
    return html[start : html.index("</section>", start)]


def visible_text(markup: str) -> str:
    """The text a reader sees: tags, the style element and attribute values removed, entities resolved,
    white space collapsed."""
    without_style = re.sub(r"<style>.*?</style>", " ", markup, flags=re.S)
    without_tags = re.sub(r"<[^>]+>", " ", without_style)
    return re.sub(r"\s+", " ", html_lib.unescape(without_tags)).strip()


def inline_text(markup: str) -> str:
    """The text of ``markup`` (no style element in it) with its tags removed and nothing put in their place,
    entities resolved: inline markup such as the span that keeps a rule ID on one line joins its
    neighbours, as on the page."""
    return html_lib.unescape(re.sub(r"<[^>]*>", "", markup))


__all__ = ["FINDING_CELLS", "finding_rows", "inline_text", "section", "visible_text"]
