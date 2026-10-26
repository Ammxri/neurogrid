"""Report fonts (A-27, TECH-07): checked-in static Noto Sans SC cuts, runtime subsets, glyph coverage."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import io
import itertools
import json
import re
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from fontTools.fontBuilder import FontBuilder
from fontTools.otlLib import builder as otl_builder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

from neurogrid import pipeline
from neurogrid.kernel import fonts
from neurogrid.kernel.fonts import (
    FONT_FAMILY,
    NAME_IDS,
    RADICAL_AND_COMPAT,
    font_codepoints,
    is_radical_or_compat,
    postscript_names,
    subset_font_css,
    subset_ttf,
    used_codepoints,
)
from neurogrid.report.glyphs import font_coverage
from neurogrid.report.output import glyph_safe_document
from neurogrid.report.render import page_text, render_report
from neurogrid.report.texts import FONT_DIR, FONT_FILES

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"
RECORD = json.loads((FONT_DIR / "fonts.json").read_text(encoding="utf-8"))
FACES = {400: ("Regular", 0x40, 0), 700: ("Bold", 0x20, 1)}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_static_cuts_match_fonts_json_sha256() -> None:
    import build_fonts  # tools/build_fonts.py

    assert RECORD["license"] == "OFL-1.1" and RECORD["family"] == "Noto Sans SC"
    assert RECORD["source"]["sha256"] == build_fonts.SOURCE_FONT["sha256"]
    assert RECORD["source"]["commit"] == build_fonts.COMMIT and RECORD["tool"]["fonttools"] == "4.66.1"
    assert set(RECORD["files"]) == {path.name for path in FONT_FILES.values()}
    for weight, path in FONT_FILES.items():
        entry = RECORD["files"][path.name]
        assert entry["weight"] == weight
        assert entry["bytes"] == path.stat().st_size and entry["sha256"] == _sha256(path)
        assert entry["removed_codepoints"] == 453  # 115 + 214 + 122 + 2 radical/compatibility code points
    assert (
        _sha256(FONT_DIR / "OFL.txt")
        == RECORD["license_file"]["sha256"]
        == build_fonts.SOURCE_LICENSE["sha256"]
    )
    assert "SIL OPEN FONT LICENSE Version 1.1" in (FONT_DIR / "OFL.txt").read_text(encoding="utf-8")


def test_static_cuts_have_no_radical_or_compat_codepoints() -> None:
    covered = font_codepoints(FONT_FILES)
    assert len(covered) == 30437
    assert not [cp for cp in covered if is_radical_or_compat(cp)]
    assert {ord(ch) for ch in "生数据集预检报告ABCxyz0123–·（）"} <= covered
    assert RECORD["removed_ranges"] == [[f"U+{a:04X}", f"U+{b:04X}"] for a, b in RADICAL_AND_COMPAT]


@pytest.mark.parametrize("weight", [400, 700])
def test_static_cuts_are_static_truetype_400_700(weight: int) -> None:
    style, fs_selection, mac_style = FACES[weight]
    font = TTFont(FONT_FILES[weight], lazy=True)
    try:
        assert "glyf" in font and not {"fvar", "gvar", "avar", "HVAR", "MVAR", "CFF ", "CFF2"} & set(
            font.keys()
        )
        assert font["OS/2"].usWeightClass == weight
        assert font["OS/2"].fsSelection & 0x61 == fs_selection and font["head"].macStyle == mac_style
        assert font["name"].getDebugName(6) == f"NotoSansSC-{style}"
        assert font["name"].getDebugName(1) == "Noto Sans SC" and font["name"].getDebugName(2) == style
        ids = {record.nameID for record in font["name"].names}
        assert {0, 13, 14} <= ids
        assert "Reserved Font Name" in font["name"].getDebugName(0)
    finally:
        font.close()


def test_subset_keeps_name_ids_0_13_14_and_is_byte_identical_twice() -> None:
    wanted = used_codepoints("NeuroGrid 预检报告 Pre-check")
    first = subset_ttf(FONT_FILES[400], wanted)
    fonts._subset.cache_clear()
    second = subset_ttf(FONT_FILES[400], wanted)
    assert first == second
    subset = TTFont(io.BytesIO(first))
    ids = {record.nameID for record in subset["name"].names}
    # the kept IDs plus font-specific IDs (>= 256) that the STAT table refers to; nothing else
    assert set(NAME_IDS) <= ids and all(i in NAME_IDS or i >= 256 for i in ids)
    assert set(subset.getBestCmap()) == set(wanted) & font_codepoints(FONT_FILES)
    original = TTFont(FONT_FILES[400], lazy=True)
    assert subset["head"].modified == original["head"].modified  # no recalculated timestamp
    original.close()


def test_subset_covers_every_used_codepoint() -> None:
    results = pipeline.run_check(FIX / "edf_mixed", pipeline.CheckOptions(as_of=date(2026, 10, 11)))
    document = render_report(results, "zh") + page_text("zh")
    css = subset_font_css(FONT_FILES, document)
    covered = font_codepoints(FONT_FILES)
    needed = used_codepoints(document) & covered
    for data in re.findall(r"base64,([A-Za-z0-9+/=]+)", css):
        subset = TTFont(io.BytesIO(base64.b64decode(data)))
        assert needed <= set(subset.getBestCmap())
    assert {ord(ch) for ch in "0123456789 /"} <= used_codepoints("")


def test_font_css_is_data_uri_truetype_two_weights() -> None:
    css = subset_font_css(FONT_FILES, "NeuroGrid 报告")
    rules = re.findall(
        r'@font-face \{ font-family: "NG Sans"; font-weight: (\d+); font-style: normal; '
        r'src: url\(data:font/ttf;base64,([A-Za-z0-9+/=]+)\) format\("truetype"\); \}',
        css,
    )
    assert [weight for weight, _ in rules] == ["400", "700"] and FONT_FAMILY == "NG Sans"
    for weight, data in rules:
        font = TTFont(io.BytesIO(base64.b64decode(data)))
        assert font["OS/2"].usWeightClass == int(weight) and "glyf" in font
    assert css == subset_font_css(FONT_FILES, "NeuroGrid 报告")
    assert "Other" in subset_font_css(FONT_FILES, "x", family="Other Family")
    with pytest.raises(ValueError):
        subset_font_css(FONT_FILES, "x", family='a"; } body { color: red')


def test_glyph_safe_document_replaces_what_the_fonts_cannot_draw() -> None:
    """The whole delivered document goes through report.glyphs.glyph_safe (the one place that writes
    [U+XXXX], B1/B6); a document without such characters comes back as the same object."""
    covered = font_codepoints(FONT_FILES)
    text = "数据 ok\t\n\r😀 ✗ ⽣ \x01 \x85 ﻿ \ud800"
    assert (
        glyph_safe_document(text, covered)
        == "数据 ok\t\n\r[U+1F600] [U+2717] [U+2F63] [U+0001] [U+0085] [U+FEFF] [U+D800]"
    )
    plain = "NeuroGrid 预检报告 – · （）"
    assert glyph_safe_document(plain, covered) is plain
    assert (
        glyph_safe_document("a]b[c\\d^", frozenset())
        == "[U+0061][U+005D][U+0062][U+005B][U+0063][U+005C][U+0064][U+005E]"
    )
    # the report area's coverage (report/glyphs.py) and the subsetting's agree on the code points
    assert font_coverage(FONT_FILES[w] for w in sorted(FONT_FILES)) == covered
    assert font_coverage([FONT_DIR / "missing.ttf"]) is None


def test_postscript_names_of_the_faces_by_weight(tmp_path: Path) -> None:
    """What the QA gate accepts as embedded font (BaseFont 'ABCDEF+<name>'), read from the font files."""
    assert postscript_names(FONT_FILES) == ("NotoSansSC-Regular", "NotoSansSC-Bold")
    assert postscript_names({700: FONT_FILES[700], 400: FONT_FILES[400]}) == postscript_names(FONT_FILES)
    nameless = _tiny_font([0x41])
    nameless["name"].removeNames(nameID=6)
    nameless.save(tmp_path / "nameless.ttf")
    with pytest.raises(ValueError):
        postscript_names({400: tmp_path / "nameless.ttf"})


def test_used_codepoints_include_unescaped_entities_and_drop_controls() -> None:
    found = used_codepoints("&amp;&#x751F;\x00\x7f\x9f")
    assert {ord("&"), ord("a"), ord("m"), 0x751F} <= found
    assert not {0x00, 0x7F, 0x9F} & found
    assert font_codepoints({}) == frozenset()


def _tiny_font(codepoints: list[int]) -> TTFont:
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder([".notdef", "a"])
    builder.setupCharacterMap({cp: "a" for cp in codepoints})
    pen = TTGlyphPen(None)
    pen.moveTo((0, 0))
    pen.lineTo((0, 500))
    pen.lineTo((500, 0))
    pen.closePath()
    glyph = pen.glyph()
    builder.setupGlyf({".notdef": glyph, "a": glyph})
    builder.setupHorizontalMetrics({".notdef": (500, 0), "a": (500, 0)})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable({"familyName": "Tiny", "styleName": "Regular"})
    builder.setupOS2()
    builder.setupPost()
    return builder.font


def _twin_font(extra_glyph: str | None = None) -> TTFont:
    """Glyphs 'a' (U+0061, U+0062, U+0063) and 'dash' (U+2012, U+2013) shared, 'b' (U+0042) alone; with
    vertical metrics and GDEF glyph classes like the static cuts."""
    names = [".notdef", "a", "b", "dash"] + ([extra_glyph] if extra_glyph else [])
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(names)
    builder.setupCharacterMap({0x61: "a", 0x62: "a", 0x63: "a", 0x42: "b", 0x2012: "dash", 0x2013: "dash"})
    glyphs = {}
    for index, name in enumerate(names):
        pen = TTGlyphPen(None)
        pen.moveTo((0, 0))
        pen.lineTo((0, 100 + 50 * index))
        pen.lineTo((300 + 10 * index, 0))
        pen.closePath()
        glyphs[name] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (500 + i, 7 + i) for i, name in enumerate(names)})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupVerticalMetrics({name: (1000, 30 + i) for i, name in enumerate(names)})
    builder.setupVerticalHeader(ascent=500, descent=-500)
    builder.setupNameTable({"familyName": "Twins", "styleName": "Regular"})
    builder.setupOS2()
    builder.setupPost()
    builder.addOpenTypeFeatures("table GDEF { GlyphClassDef [a b dash], , , ; } GDEF;")
    return builder.font


def test_separate_shared_glyphs_gives_every_codepoint_its_own_glyph() -> None:
    """Skia writes one ToUnicode entry per glyph (the lowest code point of the font that maps to it): the
    copies make the PDF text the HTML text (A-27, B2). Outline, advance, vertical metrics and GDEF class of
    a copy are those of the original; the lowest code point keeps the original glyph."""
    font = _twin_font()
    assert fonts.shared_glyphs(font) == {"a": [0x61, 0x62, 0x63], "dash": [0x2012, 0x2013]}
    copies = fonts.separate_shared_glyphs(font)
    assert copies == {0x62: "a.u0062", 0x63: "a.u0063", 0x2013: "dash.u2013"}
    buffer = io.BytesIO()
    font.save(buffer)
    saved = TTFont(io.BytesIO(buffer.getvalue()))
    cmap = saved.getBestCmap()
    assert fonts.shared_glyphs(saved) == {} and len(set(cmap.values())) == len(cmap) == 6
    assert (cmap[0x61], cmap[0x42], cmap[0x2012]) == ("a", "b", "dash")
    assert saved.getGlyphOrder() == [".notdef", "a", "b", "dash", "a.u0062", "a.u0063", "dash.u2013"]
    glyf = saved["glyf"]
    classes = saved["GDEF"].table.GlyphClassDef.classDefs
    for codepoint, copy in copies.items():
        original = {0x62: "a", 0x63: "a", 0x2013: "dash"}[codepoint]
        assert cmap[codepoint] == copy
        assert glyf[copy].getCoordinates(glyf)[0] == glyf[original].getCoordinates(glyf)[0]
        assert saved["hmtx"][copy] == saved["hmtx"][original]
        assert saved["vmtx"][copy] == saved["vmtx"][original]
        assert classes[copy] == classes[original] == 1
    for table in saved["cmap"].tables:  # every subtable, not only the best one
        assert {cp: table.cmap[cp] for cp in copies if cp in table.cmap} == copies
    assert fonts.separate_shared_glyphs(saved) == {}  # nothing left to separate
    plain = _tiny_font([0x41])
    assert fonts.shared_glyphs(plain) == {} and fonts.separate_shared_glyphs(plain) == {}


def test_separate_shared_glyphs_refuses_a_name_clash() -> None:
    font = _twin_font(extra_glyph="a.u0062")
    with pytest.raises(ValueError):
        fonts.separate_shared_glyphs(font)
    assert font.getBestCmap()[0x62] == "a"  # unchanged


# --- glyph copies in the layout tables (GSUB, GPOS, GDEF) ------------------------------------------------

LAYOUT_GLYPHS = [
    ".notdef",
    "a",
    "b",
    "dash",
    "x",
    "acute",
    "a.sc",
    "b.alt",
    "dash.alt",
    "a_b",
    "b_dash",
    "a_dash",
]
# 'a' (U+0061/U+0062), 'dash' (U+2012/U+2013) and the mark 'acute' (U+0301/U+0341) are shared
LAYOUT_CMAP = {
    0x61: "a",
    0x62: "a",
    0x42: "b",
    0x2012: "dash",
    0x2013: "dash",
    0x78: "x",
    0x301: "acute",
    0x341: "acute",
}
# One lookup of every GSUB type (1-8, 7 = extension) and GPOS type (1-8, single and pair positioning in both
# formats, lookup flags with a mark filtering set and a mark attachment class), GDEF with every glyph list.
LAYOUT_FEATURES = """
languagesystem DFLT dflt;
languagesystem latn dflt;
markClass acute <anchor 0 500> @TOP;
@MARKS = [acute];
@LEFT = [a b];
@RIGHT = [dash x];
lookup SINGLE { sub dash by dash.alt; } SINGLE;
lookup SINGLE_A { sub a by a.sc; } SINGLE_A;
lookup MULTIPLE { sub a by a.sc b; } MULTIPLE;
lookup ALTERNATE { sub a from [a.sc b.alt]; } ALTERNATE;
lookup LIGATURE { sub a b by a_b; sub b dash by b_dash; sub a dash by a_dash; } LIGATURE;
lookup REVERSE { rsub [b x] a' dash by a.sc; } REVERSE;
lookup EXTENSION useExtension { sub dash by b.alt; } EXTENSION;
lookup CONTEXT { sub a' lookup SINGLE_A dash' lookup SINGLE; } CONTEXT;
lookup CHAIN { sub dash a' lookup SINGLE_A dash; } CHAIN;
lookup SINGLEPOS1 { pos [a dash] <0 0 30 0>; } SINGLEPOS1;
lookup SINGLEPOS2 { pos a <0 0 10 0>; pos dash <0 0 20 0>; pos x <0 0 30 0>; } SINGLEPOS2;
lookup PAIR1 { pos a dash -30; pos dash a -20; pos b dash -10; } PAIR1;
lookup PAIR2 { pos @LEFT @RIGHT -40; } PAIR2;
lookup CURSIVE {
  pos cursive a <anchor 0 0> <anchor 500 0>; pos cursive dash <anchor 10 0> <anchor 400 0>;
} CURSIVE;
lookup MARKBASE { pos base [a dash] <anchor 250 450> mark @TOP; } MARKBASE;
lookup MARKLIG {
  pos ligature a_b <anchor 100 500> mark @TOP ligComponent <anchor 400 500> mark @TOP;
} MARKLIG;
lookup MARKMARK { pos mark acute <anchor 0 600> mark @TOP; } MARKMARK;
lookup POSCONTEXT { pos a' lookup SINGLEPOS1 dash'; } POSCONTEXT;
lookup POSCHAIN { pos dash a' lookup SINGLEPOS1 dash; } POSCHAIN;
lookup FILTERED { lookupflag UseMarkFilteringSet [acute]; pos a dash -5; } FILTERED;
lookup ATTACHTYPE { lookupflag MarkAttachmentType @MARKS; pos b dash -6; } ATTACHTYPE;
feature locl { lookup SINGLE; } locl;
feature ccmp { lookup MULTIPLE; } ccmp;
feature salt { lookup ALTERNATE; } salt;
feature liga { lookup LIGATURE; } liga;
feature calt { lookup REVERSE; lookup EXTENSION; lookup CONTEXT; lookup CHAIN; } calt;
feature kern { lookup SINGLEPOS1; lookup SINGLEPOS2; lookup PAIR1; lookup PAIR2; lookup POSCONTEXT;
  lookup POSCHAIN; lookup FILTERED; lookup ATTACHTYPE; } kern;
feature curs { lookup CURSIVE; } curs;
feature mark { lookup MARKBASE; lookup MARKLIG; } mark;
feature mkmk { lookup MARKMARK; } mkmk;
table GDEF {
  GlyphClassDef [a b dash x a.sc b.alt dash.alt], [a_b b_dash a_dash], [acute], ;
  Attach a 1;
  LigatureCaretByPos a_b 300;
} GDEF;
"""
GSUB_INDEX = {"single": 0, "single_a": 1, "multiple": 2, "alternate": 3, "ligature": 4, "reverse": 5}
GSUB_INDEX |= {"extension": 6, "context": 7, "chain": 8}
GPOS_INDEX = {"single1": 0, "single2": 1, "pair1": 2, "pair2": 3, "cursive": 4, "markbase": 5, "marklig": 6}
GPOS_INDEX |= {"markmark": 7, "context": 8, "chain": 9, "filtered": 10, "attachtype": 11}


@contextlib.contextmanager
def _contextual_format(form: int) -> Iterator[None]:
    """feaLib writes the smallest of the contextual formats 1-3; this makes ``form`` the smallest."""
    real = otl_builder.ChainContextualBuilder.getCompiledSize_

    def size(builder: Any, subtables: list[Any]) -> int:
        real(builder, subtables)
        return 0 if subtables[0].Format == form else 1 << 20

    with mock.patch.object(otl_builder.ChainContextualBuilder, "getCompiledSize_", size):
        yield


def _saved(font: TTFont) -> TTFont:
    buffer = io.BytesIO()
    font.save(buffer)
    return TTFont(io.BytesIO(buffer.getvalue()))


def _layout_font(form: int) -> TTFont:
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(LAYOUT_GLYPHS)
    builder.setupCharacterMap(LAYOUT_CMAP)
    glyphs = {}
    for index, name in enumerate(LAYOUT_GLYPHS):
        pen = TTGlyphPen(None)
        pen.moveTo((0, 0))
        pen.lineTo((0, 100 + 50 * index))
        pen.lineTo((300 + 10 * index, 0))
        pen.closePath()
        glyphs[name] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (500 + i, 7 + i) for i, name in enumerate(LAYOUT_GLYPHS)})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable({"familyName": "Layout", "styleName": "Regular"})
    builder.setupOS2()
    builder.setupPost()
    builder.font.cfg["fontTools.otlLib.builder:WRITE_GPOS7"] = True  # GPOS 7 next to GPOS 8
    with _contextual_format(form):
        builder.addOpenTypeFeatures(LAYOUT_FEATURES)
    return _saved(builder.font)


def _subtables(font: TTFont, tag: str, index: int) -> list[Any]:
    lookup = font[tag].table.LookupList.Lookup[index]
    extension = {"GSUB": 7, "GPOS": 9}[tag]
    return [st.ExtSubTable if lookup.LookupType == extension else st for st in lookup.SubTable]


def _mapping(font: TTFont, index: int) -> dict[str, Any]:
    found: dict[str, Any] = {}
    for subtable in _subtables(font, "GSUB", index):
        found |= getattr(subtable, "alternates", None) or subtable.mapping
    return found


def _ligatures(font: TTFont, index: int) -> dict[tuple[str, ...], str]:
    return {
        (first, *ligature.Component): ligature.LigGlyph
        for subtable in _subtables(font, "GSUB", index)
        for first, ligatures in subtable.ligatures.items()
        for ligature in ligatures
    }


def _covered(coverage: Any, glyph: str) -> int | None:
    return coverage.glyphs.index(glyph) if glyph in coverage.glyphs else None


def _value(record: Any) -> tuple[Any, ...] | None:
    if record is None:
        return None
    return tuple(getattr(record, name, 0) for name in ("XPlacement", "YPlacement", "XAdvance", "YAdvance"))


def _single_value(font: TTFont, index: int, glyph: str) -> tuple[Any, ...] | None:
    for subtable in _subtables(font, "GPOS", index):
        at = _covered(subtable.Coverage, glyph)
        if at is not None:
            return _value(subtable.Value if subtable.Format == 1 else subtable.Value[at])
    return None


def _pair_value(font: TTFont, index: int, first: str, second: str) -> tuple[Any, ...] | None:
    """The first pair adjustment that applies to (first, second): as a shaper looks it up."""
    for subtable in _subtables(font, "GPOS", index):
        at = _covered(subtable.Coverage, first)
        if at is None:
            continue
        if subtable.Format == 1:
            records = subtable.PairSet[at].PairValueRecord
            assert [font.getGlyphID(r.SecondGlyph) for r in records] == sorted(
                font.getGlyphID(r.SecondGlyph) for r in records
            )  # shapers search the pair set by glyph ID
            for record in records:
                if record.SecondGlyph == second:
                    return _value(record.Value1)
        else:
            row = subtable.Class1Record[subtable.ClassDef1.classDefs.get(first, 0)]
            return _value(row.Class2Record[subtable.ClassDef2.classDefs.get(second, 0)].Value1)
    return None


def _anchor(anchor: Any) -> tuple[int, int] | None:
    return None if anchor is None else (anchor.XCoordinate, anchor.YCoordinate)


def _context(subtable: Any, backtrack: list[str], glyphs: list[str], lookahead: list[str]) -> Any:
    """The lookup records of the first rule of a contextual subtable that matches exactly ``backtrack``
    (in text order), ``glyphs`` and ``lookahead``, or None (formats 1-3, chained or not)."""
    chained = type(subtable).__name__.startswith("Chain")
    kind = "Subst" if "Subst" in type(subtable).__name__ else "Pos"

    def records(owner: Any) -> list[tuple[int, int]]:
        return [(r.SequenceIndex, r.LookupListIndex) for r in getattr(owner, f"{kind}LookupRecord")]

    if subtable.Format == 3:
        if chained:
            parts = (
                (list(reversed(backtrack)), subtable.BacktrackCoverage),
                (glyphs, subtable.InputCoverage),
                (lookahead, subtable.LookAheadCoverage),
            )
        else:
            parts = ((glyphs, subtable.Coverage),)
            if backtrack or lookahead:
                return None
        for sequence, coverages in parts:
            if len(sequence) != len(coverages) or any(
                g not in c.glyphs for g, c in zip(sequence, coverages, strict=True)
            ):
                return None
        return records(subtable)
    at = _covered(subtable.Coverage, glyphs[0])
    if at is None:
        return None
    if subtable.Format == 1:
        sets = getattr(subtable, f"Chain{kind[:3]}RuleSet" if chained else f"{kind[:3]}RuleSet")
        rules = getattr(sets[at], f"Chain{kind[:3]}Rule" if chained else f"{kind[:3]}Rule")
        wanted = (list(reversed(backtrack)), glyphs[1:], lookahead)
    else:
        if chained:
            defs = (subtable.BacktrackClassDef, subtable.InputClassDef, subtable.LookAheadClassDef)
        else:
            defs = (None, subtable.ClassDef, None)

        def classes(class_def: Any, sequence: list[str]) -> list[int]:
            return [class_def.classDefs.get(g, 0) if class_def else 0 for g in sequence]

        first = classes(defs[1], glyphs[:1])[0]
        sets = getattr(subtable, f"Chain{kind[:3]}ClassSet" if chained else f"{kind[:3]}ClassSet")
        if sets[first] is None:
            return None
        rules = getattr(sets[first], f"Chain{kind[:3]}ClassRule" if chained else f"{kind[:3]}ClassRule")
        wanted = (
            classes(defs[0], list(reversed(backtrack))),
            classes(defs[1], glyphs[1:]),
            classes(defs[2], lookahead),
        )
    for rule in rules:
        if chained:
            found = (list(rule.Backtrack), list(rule.Input), list(rule.LookAhead))
        else:
            found = ([], list(rule.Input if subtable.Format == 1 else rule.Class), [])
        if found == wanted:
            return records(rule)
    return None


# the copies of the layout font: cmap copies, then the copies of the substitutes they get (same suffix)
LAYOUT_COPIES = {
    "a": ["a.u0062"],
    "acute": ["acute.u0341"],
    "dash": ["dash.u2013"],
    "dash.alt": ["dash.alt.u2013"],
    "a.sc": ["a.sc.u0062"],
    "b": ["b.u0062"],  # second glyph of the multiple substitution of 'a'
    "b.alt": ["b.alt.u0062", "b.alt.u2013"],
    # ligatures: per component '.L<length of its suffix><suffix>' ('.L0' for an original)
    "a_b": ["a_b.L0.L6.u0062", "a_b.L6.u0062.L0", "a_b.L6.u0062.L6.u0062"],
    "a_dash": ["a_dash.L0.L6.u2013", "a_dash.L6.u0062.L0", "a_dash.L6.u0062.L6.u2013"],
    "b_dash": ["b_dash.L0.L6.u2013", "b_dash.L6.u0062.L0", "b_dash.L6.u0062.L6.u2013"],
}


def _variants(*glyphs: str) -> list[tuple[str, ...]]:
    return list(itertools.product(*([glyph, *LAYOUT_COPIES.get(glyph, [])] for glyph in glyphs)))


def _ligature_suffix(*glyphs: str) -> str:
    suffixes = [glyph[glyph.index(".u") :] if ".u" in glyph else "" for glyph in glyphs]
    return "".join(f".L{len(suffix)}{suffix}" for suffix in suffixes) if any(suffixes) else ""


@pytest.mark.parametrize("form", [1, 2, 3])
def test_glyph_copies_take_part_in_every_lookup_of_their_original(form: int) -> None:
    """P3, A-27: a copy is wherever its original is (coverage, class definitions, pair sets as first and as
    second glyph, substitution inputs, ligature components, contextual rules in formats 1-3), so a shaper
    gives a text with twins exactly the kerning, mark positions and substitutions of the shared glyph. A
    substitute of a copy is a copy of the substitute with the copy's suffix (its own glyph, so the PDF
    text keeps the code point); copies get outline, metrics and every GDEF entry of their original."""
    font = _layout_font(form)
    assert fonts.separate_shared_glyphs(font) == {0x62: "a.u0062", 0x341: "acute.u0341", 0x2013: "dash.u2013"}
    font = _saved(font)
    copies = font.getGlyphOrder()[len(LAYOUT_GLYPHS) :]
    assert sorted(copies) == sorted(c for group in LAYOUT_COPIES.values() for c in group)
    glyf, gdef = font["glyf"], font["GDEF"].table
    for original, group in LAYOUT_COPIES.items():
        for copy in group:
            assert glyf[copy].getCoordinates(glyf)[0] == glyf[original].getCoordinates(glyf)[0]
            assert font["hmtx"][copy] == font["hmtx"][original]
            assert gdef.GlyphClassDef.classDefs[copy] == gdef.GlyphClassDef.classDefs[original]
    # GSUB 1, 2, 3, 7 (extension around 1), 4 and 8
    assert _mapping(font, GSUB_INDEX["single"])["dash.u2013"] == "dash.alt.u2013"
    assert _mapping(font, GSUB_INDEX["single_a"])["a.u0062"] == "a.sc.u0062"
    assert _mapping(font, GSUB_INDEX["multiple"])["a.u0062"] == ["a.sc.u0062", "b.u0062"]
    assert _mapping(font, GSUB_INDEX["alternate"])["a.u0062"] == ["a.sc.u0062", "b.alt.u0062"]
    assert _mapping(font, GSUB_INDEX["extension"])["dash.u2013"] == "b.alt.u2013"
    ligatures = _ligatures(font, GSUB_INDEX["ligature"])
    for sequence, ligature in (("a", "b"), "a_b"), (("b", "dash"), "b_dash"), (("a", "dash"), "a_dash"):
        for variant in _variants(*sequence):
            assert ligatures[variant] == ligature + _ligature_suffix(*variant), variant
    assert len(ligatures) == sum(len(_variants(*s)) for s in (("a", "b"), ("b", "dash"), ("a", "dash")))
    (reverse,) = _subtables(font, "GSUB", GSUB_INDEX["reverse"])
    assert dict(zip(reverse.Coverage.glyphs, reverse.Substitute, strict=True)) == {
        "a": "a.sc",
        "a.u0062": "a.sc.u0062",
    }
    assert [c.glyphs for c in reverse.BacktrackCoverage] == [["b", "x", "b.u0062"]]
    assert [c.glyphs for c in reverse.LookAheadCoverage] == [["dash", "dash.u2013"]]
    # contextual lookups (GSUB 5/6, GPOS 7/8) in the forced format: every variant matches like the original
    for tag, index, backtrack, glyphs, lookahead in (
        ("GSUB", GSUB_INDEX["context"], [], ["a", "dash"], []),
        ("GSUB", GSUB_INDEX["chain"], ["dash"], ["a"], ["dash"]),
        ("GPOS", GPOS_INDEX["context"], [], ["a", "dash"], []),
        ("GPOS", GPOS_INDEX["chain"], ["dash"], ["a"], ["dash"]),
    ):
        (subtable,) = _subtables(font, tag, index)
        assert subtable.Format == form
        expected = _context(subtable, backtrack, glyphs, lookahead)
        assert expected
        sequence = [*backtrack, *glyphs, *lookahead]
        for variant in _variants(*sequence):
            parts = list(variant)
            found = _context(
                subtable,
                parts[: len(backtrack)],
                parts[len(backtrack) : len(backtrack) + len(glyphs)],
                parts[len(backtrack) + len(glyphs) :],
            )
            assert found == expected, (tag, variant)
        other = (backtrack, ["a", "x"], lookahead) if len(glyphs) == 2 else (backtrack, glyphs, ["x"])
        assert _context(subtable, *other) is None
    # GPOS 1 (both formats), 2 (glyph pairs and class pairs, also with lookup flags), 3, 4, 5, 6
    for key in ("single1", "single2"):
        for original in ("a", "dash"):
            for copy in LAYOUT_COPIES[original]:
                value = _single_value(font, GPOS_INDEX[key], original)
                assert value is not None and _single_value(font, GPOS_INDEX[key], copy) == value
    for key, pairs in (
        ("pair1", (("a", "dash"), ("dash", "a"), ("b", "dash"))),
        ("pair2", (("a", "dash"), ("b", "x"), ("a", "x"))),
        ("filtered", (("a", "dash"),)),
        ("attachtype", (("b", "dash"),)),
    ):
        for first, second in pairs:
            value = _pair_value(font, GPOS_INDEX[key], first, second)
            assert value is not None and value[2] < 0
            for variant in _variants(first, second):
                assert _pair_value(font, GPOS_INDEX[key], *variant) == value, (key, variant)
    (cursive,) = _subtables(font, "GPOS", GPOS_INDEX["cursive"])
    exits = {
        glyph: (_anchor(record.EntryAnchor), _anchor(record.ExitAnchor))
        for glyph, record in zip(cursive.Coverage.glyphs, cursive.EntryExitRecord, strict=True)
    }
    assert exits["a.u0062"] == exits["a"] and exits["dash.u2013"] == exits["dash"]
    (markbase,) = _subtables(font, "GPOS", GPOS_INDEX["markbase"])
    marks = {
        g: (r.Class, _anchor(r.MarkAnchor))
        for g, r in zip(markbase.MarkCoverage.glyphs, markbase.MarkArray.MarkRecord, strict=True)
    }
    bases = {
        g: [_anchor(a) for a in r.BaseAnchor]
        for g, r in zip(markbase.BaseCoverage.glyphs, markbase.BaseArray.BaseRecord, strict=True)
    }
    assert marks["acute.u0341"] == marks["acute"] and bases["a.u0062"] == bases["a"]
    assert bases["dash.u2013"] == bases["dash"]
    (marklig,) = _subtables(font, "GPOS", GPOS_INDEX["marklig"])
    attach = {
        g: [[_anchor(a) for a in c.LigatureAnchor] for c in r.ComponentRecord]
        for g, r in zip(marklig.LigatureCoverage.glyphs, marklig.LigatureArray.LigatureAttach, strict=True)
    }
    assert all(attach[copy] == attach["a_b"] for copy in LAYOUT_COPIES["a_b"])
    assert "acute.u0341" in marklig.MarkCoverage.glyphs
    (markmark,) = _subtables(font, "GPOS", GPOS_INDEX["markmark"])
    assert markmark.Mark1Coverage.glyphs == markmark.Mark2Coverage.glyphs == ["acute", "acute.u0341"]
    assert _anchor(markmark.Mark2Array.Mark2Record[1].Mark2Anchor[0]) == (0, 600)
    # GDEF lists
    assert [c.glyphs for c in gdef.MarkGlyphSetsDef.Coverage] == [["acute", "acute.u0341"]]
    assert gdef.MarkAttachClassDef.classDefs["acute.u0341"] == gdef.MarkAttachClassDef.classDefs["acute"]
    points = dict(
        zip(gdef.AttachList.Coverage.glyphs, [p.PointIndex for p in gdef.AttachList.AttachPoint], strict=True)
    )
    assert points["a.u0062"] == points["a"] == [1]
    carets = dict(zip(gdef.LigCaretList.Coverage.glyphs, gdef.LigCaretList.LigGlyph, strict=True))
    assert [c.Coordinate for c in carets["a_b.L6.u0062.L0"].CaretValue] == [
        c.Coordinate for c in carets["a_b"].CaretValue
    ]


def test_glyph_copies_without_layout_are_in_no_lookup() -> None:
    """Negative control (the state before P3): copies made with ``layout=False`` are in no lookup, so a
    twin lost kerning, mark positions and localized forms."""
    font = _layout_font(1)
    fonts.separate_shared_glyphs(font, layout=False)
    font = _saved(font)
    assert font.getGlyphOrder()[len(LAYOUT_GLYPHS) :] == ["a.u0062", "acute.u0341", "dash.u2013"]
    assert "dash.u2013" not in _mapping(font, GSUB_INDEX["single"])
    assert _pair_value(font, GPOS_INDEX["pair1"], "a", "dash.u2013") is None
    assert _pair_value(font, GPOS_INDEX["pair2"], "a.u0062", "dash") is None
    (subtable,) = _subtables(font, "GSUB", GSUB_INDEX["chain"])
    assert _context(subtable, ["dash"], ["a.u0062"], ["dash"]) is None


def test_glyph_copies_of_the_static_cuts_keep_kerning_and_localized_forms() -> None:
    """P3 on the shipped fonts: with U+2012 (figure dash) and U+22EF in the text, U+2013 and U+22EF are
    copies; kerning of T/L with the en dash (class kerning, both directions) is that of the shared glyph,
    and the localized form of the ellipsis (locl, Latin) maps the copy to its own copy of the substitute."""
    text = "T–T L–L ‒ a…b⋯c"
    for weight, path in FONT_FILES.items():
        subset = TTFont(io.BytesIO(subset_ttf(path, fonts.used_codepoints(text))))
        cmap = subset.getBestCmap()
        figure, en, ellipsis, midline = (cmap[cp] for cp in (0x2012, 0x2013, 0x2026, 0x22EF))
        assert len({figure, en}) == len({ellipsis, midline}) == 2
        gpos = subset["GPOS"].table
        kerned = 0
        for index, lookup in enumerate(gpos.LookupList.Lookup):
            if lookup.LookupType != 2:
                continue
            for first, second in (("T", figure), (figure, "T"), ("L", figure)):
                value = _pair_value(subset, index, first, second)
                twin = [en if glyph == figure else glyph for glyph in (first, second)]
                assert _pair_value(subset, index, *twin) == value, (weight, first, second)
                kerned += value is not None and value[2] != 0
        assert kerned == 3, weight
        glyf, substituted = subset["glyf"], 0
        for index, lookup in enumerate(subset["GSUB"].table.LookupList.Lookup):
            if lookup.LookupType == 1:
                mapping = _mapping(subset, index)
                if ellipsis in mapping:
                    form, copy = mapping[ellipsis], mapping[midline]
                    assert form != copy and form not in cmap.values() and copy not in cmap.values()
                    assert glyf[copy].getCoordinates(glyf)[0] == glyf[form].getCoordinates(glyf)[0]
                    assert subset["hmtx"][copy] == subset["hmtx"][form]
                    substituted += 1
        assert substituted >= 1, weight


def test_glyph_copies_refuse_fonts_with_tables_they_would_miss() -> None:
    """A font with per-glyph data outside glyf/hmtx/vmtx/GSUB/GPOS/GDEF (here a legacy 'kern' table) is
    refused before anything changes; copies would silently lack it."""
    from fontTools.ttLib import newTable

    font = _twin_font()
    kern = newTable("kern")
    kern.version, kern.kernTables = 0, []
    font["kern"] = kern
    with pytest.raises(ValueError, match="kern"):
        fonts.separate_shared_glyphs(font)
    assert font.getBestCmap()[0x62] == "a" and "a.u0062" not in font.getGlyphOrder()
    assert "kern" in fonts.GLYPH_TABLES_NOT_COPIED and "CFF " in fonts.GLYPH_TABLES_NOT_COPIED


def test_glyph_copies_refuse_an_unknown_lookup_type_and_too_many_glyphs() -> None:
    font = _layout_font(1)
    font["GPOS"].table.LookupList.Lookup[GPOS_INDEX["pair1"]].LookupType = 10
    with pytest.raises(ValueError, match="GPOS lookup type 10"):
        fonts.separate_shared_glyphs(font)
    full = _twin_font()
    full.setGlyphOrder(full.getGlyphOrder() + [f"g{i}" for i in range(fonts.MAX_GLYPHS - 4)])
    copies = fonts.GlyphCopies(full)
    with pytest.raises(ValueError, match="too many glyphs"):
        copies.want("a", ".u0062")
    assert copies.original == {}


def test_static_cuts_share_95_glyphs_and_subsets_share_none() -> None:
    """The measured state of the static cuts: 95 glyphs shared by two to four code points (e.g. U+2012/
    U+2013, U+002D/U+00AD/U+2011, U+00B7/U+2022/U+2027/U+30FB, U+3B35/U+80F6). Every subset that holds all
    of them gives each code point its own glyph with the original outline and metrics."""
    groups: dict[int, list[list[int]]] = {}
    for weight, path in FONT_FILES.items():
        original = TTFont(path, lazy=True)
        try:
            shared = fonts.shared_glyphs(original)
            groups[weight] = sorted(shared.values())
            twins = sorted(cp for cps in shared.values() for cp in cps)
            subset = TTFont(io.BytesIO(subset_ttf(path, [*twins, ord("A")])))
            cmap = subset.getBestCmap()
            assert fonts.shared_glyphs(subset) == {} and set(cmap) == {*twins, ord("A")}
            source_cmap, source_glyf, glyf = original.getBestCmap(), original["glyf"], subset["glyf"]
            for codepoint in twins:
                name, source = cmap[codepoint], source_cmap[codepoint]
                assert (
                    glyf[name].getCoordinates(glyf)[0] == source_glyf[source].getCoordinates(source_glyf)[0]
                )
                assert subset["hmtx"][name] == original["hmtx"][source]
                assert subset["vmtx"][name] == original["vmtx"][source]
        finally:
            original.close()
    assert groups[400] == groups[700] and len(groups[400]) == 95
    assert [0x2012, 0x2013] in groups[400] and [0x2D, 0xAD, 0x2011] in groups[400]
    assert [0xB7, 0x2022, 0x2027, 0x30FB] in groups[400] and [0x3B35, 0x80F6] in groups[400]


def test_required_phrases_keep_their_codepoints_next_to_every_glyph_twin() -> None:
    """The verifier's case (B2): characters of the QA gate's phrases (title, headings, fixed sentence,
    placeholder banner; zh and en, and the title 'NeuroGrid – 预检报告' quoted in B2) share glyphs with
    lower code points (e.g. '–' with U+2012). With all those twins in the dataset text, the embedded subsets
    of the delivered HTML still give each phrase character its own glyph, so the PDF text keeps it."""
    from neurogrid.report.output import REQUIRED_ONCE, html_document
    from neurogrid.report.texts import translator

    shared = fonts.shared_glyphs(TTFont(FONT_FILES[400], lazy=True))
    twin_of = {cp: cps for cps in shared.values() for cp in cps}
    phrases = ["NeuroGrid – 预检报告"]
    for lang in ("zh", "en"):
        tr = translator(lang).t
        phrases += [tr(key) for key in (*REQUIRED_ONCE, "disclaimer", "report.placeholder_banner")]
    chars = {ord(ch) for phrase in phrases for ch in phrase}
    lower = sorted({low for cp in chars for low in twin_of.get(cp, []) if low < cp})
    assert 0x2012 in lower  # '–' of the B2 title
    results = pipeline.run_check(FIX / "edf_mixed", pipeline.CheckOptions(as_of=date(2026, 10, 11)))
    results.dataset.name = "".join(chr(cp) for cp in lower)
    for lang in ("zh", "en"):
        document = html_document(results, lang)
        for data in re.findall(r"base64,([A-Za-z0-9+/=]+)", document):
            subset = TTFont(io.BytesIO(base64.b64decode(data)))
            cmap = subset.getBestCmap()
            assert set(lower) <= set(cmap) and fonts.shared_glyphs(subset) == {}


def test_build_fonts_removes_radical_and_compat_codepoints() -> None:
    import build_fonts

    font = _tiny_font([0x41, 0x751F, 0x2E80, 0x2F63, 0xF900, 0x2F800])
    assert build_fonts.remove_codepoints(font) == 4
    assert set(font.getBestCmap()) == {0x41, 0x751F}


def test_build_fonts_refuses_sources_with_another_checksum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import build_fonts

    (tmp_path / "OFL.txt").write_bytes(b"not the pinned licence")
    with pytest.raises(build_fonts.BuildError):
        build_fonts.source_file(build_fonts.SOURCE_LICENSE, tmp_path)
    assert build_fonts.main(["--source", str(tmp_path)]) == 2

    class Response(io.BytesIO):
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *args: object) -> None:
            self.close()

    requested: list[str] = []

    def fake_urlopen(request: object, timeout: float) -> Response:
        requested.append(getattr(request, "full_url", ""))
        return Response(b"tampered")

    monkeypatch.setattr(build_fonts.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(build_fonts.BuildError):
        build_fonts.fetch(build_fonts.SOURCE_LICENSE, tmp_path / "cache")
    assert requested == [build_fonts.SOURCE_LICENSE["url"]]
    assert not list((tmp_path / "cache").iterdir())  # the partial download is removed
