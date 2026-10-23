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
    cover_text,
    font_codepoints,
    is_radical_or_compat,
    subset_font_css,
    subset_ttf,
    used_codepoints,
)
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


def test_cover_text_replaces_what_the_fonts_cannot_draw() -> None:
    covered = font_codepoints(FONT_FILES)
    text = "数据 ok\t\n\r😀 ✗ ⽣ \x01 \x85 ﻿"
    assert cover_text(text, covered) == "数据 ok\t\n\r[U+1F600] [U+2717] [U+2F63] [U+0001] [U+0085] [U+FEFF]"
    plain = "NeuroGrid 预检报告 – · （）"
    assert cover_text(plain, covered) is plain
    assert (
        cover_text("a]b[c\\d^", frozenset())
        == "[U+0061][U+005D][U+0062][U+005B][U+0063][U+005C][U+0064][U+005E]"
    )


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
