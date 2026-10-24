"""Report fonts (A-27, TECH-07): checked-in static Noto Sans SC cuts, runtime subsets, glyph coverage."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
from datetime import date
from pathlib import Path

import pytest
from fontTools.fontBuilder import FontBuilder
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
