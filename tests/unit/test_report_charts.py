"""Distribution charts of section 4 (REP-04, A-84) and the glyph safety of the report (REP-00, A-27): own
deterministic SVG instead of matplotlib, standard library only."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

from neurogrid.report import charts
from neurogrid.report.charts import (
    CHART_BINS,
    HEIGHT,
    PLOT_BOTTOM,
    PLOT_LEFT,
    PLOT_RIGHT,
    PLOT_TOP,
    WIDTH,
    bin_counts,
    bin_index,
    histogram_svg,
    nice_ceiling,
    threshold_x,
)
from neurogrid.report.glyphs import font_coverage, glyph_safe

SRC = Path(__file__).parent.parent.parent / "src" / "neurogrid"


def test_histogram_is_byte_identical() -> None:
    values = [0.05 * i for i in range(21)]
    first = histogram_svg(values, lo=0.0, hi=1.0, label="M06", thresholds=[0.30625])
    assert first == histogram_svg(list(values), lo=0.0, hi=1.0, label="M06", thresholds=[0.30625])
    assert "id=" not in first and "http" not in first and "xmlns" not in first


def test_bin_edges_and_clamping() -> None:
    assert (
        bin_index(0.0, 0.0, 1.0) == 0 and bin_index(0.049, 0.0, 1.0) == 0 and bin_index(0.05, 0.0, 1.0) == 1
    )
    assert bin_index(1.0, 0.0, 1.0) == CHART_BINS - 1  # the upper edge belongs to the last bin
    assert bin_index(-3.0, 0.0, 1.0) == 0 and bin_index(7.0, 0.0, 1.0) == CHART_BINS - 1  # clamped
    assert bin_index(-1.0, -1.0, 1.0) == 0 and bin_index(0.0, -1.0, 1.0) == 10
    counts = bin_counts([0.0, 0.01, 0.5, 1.0, 2.0], 0.0, 1.0)
    assert len(counts) == CHART_BINS and sum(counts) == 5 and counts[0] == 2 and counts[-1] == 2
    with pytest.raises(ValueError):
        bin_counts([0.5], 1.0, 1.0)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.815338, 1.0),
        (1.0, 1.0),
        (1.2, 2.0),
        (2.2, 2.5),
        (3.0, 5.0),
        (5.13642, 10.0),
        (0.3, 0.5),
        (0.2, 0.2),
        (0.0, 1.0),
        (-2.0, 1.0),
        (float("nan"), 1.0),
        (120.0, 200.0),
    ],
)
def test_nice_ceiling(value: float, expected: float) -> None:
    assert nice_ceiling(value) == expected


def test_threshold_line_position() -> None:
    svg = histogram_svg([0.1], lo=0.0, hi=1.0, label="x", thresholds=[0.5, 0.5, 2.0])
    lines = re.findall(r'<line class="thr" x1="([\d.]+)" y1="(\d+)" x2="([\d.]+)" y2="(\d+)"/>', svg)
    plot = WIDTH - PLOT_LEFT - PLOT_RIGHT
    assert lines == [
        (
            f"{PLOT_LEFT + plot / 2:.2f}",
            str(PLOT_TOP),
            f"{PLOT_LEFT + plot / 2:.2f}",
            str(HEIGHT - PLOT_BOTTOM),
        )
    ]  # one line per distinct value; 2.0 lies outside [0, 1]
    assert threshold_x(-1.0, -1.0, 1.0) == PLOT_LEFT and threshold_x(1.0, -1.0, 1.0) == WIDTH - PLOT_RIGHT


def test_bar_heights_follow_the_counts() -> None:
    svg = histogram_svg([0.01, 0.02, 0.03, 0.97], lo=0.0, hi=1.0, label="x")
    bars = re.findall(
        r'<rect class="bar" x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"/>', svg
    )
    plot_h = HEIGHT - PLOT_TOP - PLOT_BOTTOM
    assert [float(b[3]) for b in bars] == [plot_h, round(plot_h / 3, 2)]
    assert '<text class="tk" x="31" y="17" text-anchor="end">3</text>' in svg  # the largest count
    assert ">0</text>" in svg and ">0.5</text>" in svg and ">1</text>" in svg


def test_svg_has_only_rect_line_text() -> None:
    """NG-N05: aggregates only, never a waveform: no path, polyline, image or script."""
    svg = histogram_svg([i / 1000 for i in range(1000)], lo=0.0, hi=1.0, label="<b>x</b>", thresholds=[0.2])
    inner = svg[svg.index(">") + 1 : svg.rindex("</svg>")]
    assert set(re.findall(r"<(\w+)", inner)) == {"rect", "line", "text"}
    assert len(re.findall(r"<rect ", svg)) == CHART_BINS
    assert 'aria-label="&lt;b&gt;x&lt;/b&gt;"' in svg  # the label is escaped


def test_no_bars_without_values() -> None:
    svg = histogram_svg([], lo=0.0, hi=1.0, label="x")
    assert "<rect" not in svg and '<line class="ax"' in svg


def test_charts_use_the_standard_library_only() -> None:
    """A-84: the report draws its charts itself; matplotlib stays an MNE dependency only."""
    tree = ast.parse((SRC / "report" / "charts.py").read_text(encoding="utf-8"))
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported |= {
        (node.module or "").split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }
    assert imported - {"__future__"} <= set(sys.stdlib_module_names)
    for path in (SRC / "report").rglob("*.py"):
        assert "matplotlib" not in path.read_text(encoding="utf-8"), path.name
    assert charts.CHART_BINS == 20


# --- glyph safety -------------------------------------------------------------------------------------------


def test_glyph_safe_replaces_controls_and_uncovered_characters() -> None:
    assert glyph_safe("plain text\tand\nlines\r", None) == "plain text\tand\nlines\r"
    assert glyph_safe("a\x07b\x1bc\x7f\x9f", None) == "a[U+0007]b[U+001B]c[U+007F][U+009F]"
    assert glyph_safe("lone \ud800", None) == "lone [U+D800]"  # not encodable as UTF-8
    covered = frozenset(ord(c) for c in "abc ")
    assert glyph_safe("abc 😀 𠀀 d", covered) == "abc [U+1F600] [U+20000] [U+0064]"
    assert glyph_safe("a\x07", covered | {7}) == "a[U+0007]"  # a control character is never drawn


def _font(path: Path, chars: str) -> Path:
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    names = [".notdef", *(f"g{ord(c):05X}" for c in sorted(set(chars)))]
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(names)
    builder.setupCharacterMap({ord(c): f"g{ord(c):05X}" for c in set(chars)})
    glyphs = {}
    for name in names:
        pen = TTGlyphPen(None)
        pen.moveTo((0, 0))
        pen.lineTo((0, 500))
        pen.lineTo((500, 500))
        pen.closePath()
        glyphs[name] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (600, 0) for name in names})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable({"familyName": "Test", "styleName": "Regular"})
    builder.setupOS2()
    builder.setupPost()
    builder.save(str(path))
    return path


def test_font_coverage_is_the_intersection_of_the_cmaps(tmp_path: Path) -> None:
    regular = _font(tmp_path / "r.ttf", "abcd")
    bold = _font(tmp_path / "b.ttf", "bcde")
    assert font_coverage([regular, bold]) == frozenset(map(ord, "bcd"))
    assert font_coverage([regular, tmp_path / "missing.ttf"]) is None  # fonts not installed
    assert font_coverage([]) is None


def test_report_i18n_texts_covered_by_font() -> None:
    """A-27/REP-00: every character of NeuroGrid's own report texts (language tables, rule titles, validator
    texts, template text, CSS-only strings) has a glyph in both report fonts, so glyph_safe never touches
    them. The fonts are package data of the PDF pipeline (tools/build_fonts.py)."""
    from neurogrid.kernel.i18n import LANGUAGES
    from neurogrid.report.render import page_text, report_coverage
    from neurogrid.report.texts import tables, validator_codes

    covered = report_coverage()
    if covered is None:
        pytest.skip(
            "the report fonts are not installed (src/neurogrid/report/fonts, built by tools/build_fonts.py)"
        )
    texts = [value for lang in LANGUAGES for value in tables()[lang].values()]
    texts += [entry[lang] for entry in validator_codes().values() for lang in LANGUAGES]
    texts += [page_text(lang) for lang in ("zh", "en")]
    texts += [p.read_text(encoding="utf-8") for p in (SRC / "report" / "templates").glob("*.j2")]
    texts += [p.read_text(encoding="utf-8") for p in (SRC / "rulepacks").glob("*.yaml")]
    missing = sorted({c for text in texts for c in text if ord(c) >= 0x20 and ord(c) not in covered})
    assert not missing, [f"U+{ord(c):04X}" for c in missing]
