"""Report fonts (A-27): the code points of the static Noto Sans SC cuts and runtime subsets, embedded as
``@font-face`` rules with ``data:`` URIs.

The static cuts (weights 400 and 700) are produced once by tools/build_fonts.py and carry no radical or
compatibility code points, so the text of a printed report never contains e.g. U+2F63 instead of 生.
Subsetting is deterministic: the same font file, the same code points and the same fontTools version give
the same bytes (no timestamp recalculation, sorted input). Font paths are passed in by the product (A-23).
"""

from __future__ import annotations

import base64
import html
import io
import re
from collections.abc import Iterable, Mapping
from functools import lru_cache
from pathlib import Path
from typing import cast

from fontTools import subset
from fontTools.ttLib import TTFont

FONT_FAMILY = "NG Sans"
# CJK Radicals Supplement, Kangxi Radicals, CJK Compatibility Ideographs (+ Supplement): removed from the
# static cuts by tools/build_fonts.py (A-27) and refused by the PDF QA gate (kernel/pdf.py).
RADICAL_AND_COMPAT: tuple[tuple[int, int], ...] = (
    (0x2E80, 0x2EFF),
    (0x2F00, 0x2FDF),
    (0xF900, 0xFAFF),
    (0x2F800, 0x2FA1F),
)
# The browser draws the page counters ("3 / 12") itself; their characters are always in the subset.
ALWAYS_INCLUDED = "0123456789 /"
KEPT_CONTROLS = frozenset("\t\n\r")
# name IDs kept in every subset: family, style, version and PostScript names plus copyright (0, with the
# Reserved Font Name), licence description (13) and licence URL (14) as the OFL requires (A-27)
NAME_IDS = (0, 1, 2, 3, 4, 5, 6, 13, 14)


def is_radical_or_compat(codepoint: int) -> bool:
    return any(low <= codepoint <= high for low, high in RADICAL_AND_COMPAT)


def _stat_key(path: Path) -> tuple[str, int, int]:
    stat = path.stat()
    return str(path.resolve()), stat.st_size, stat.st_mtime_ns


@lru_cache(maxsize=8)
def _cmap(key: tuple[str, int, int]) -> frozenset[int]:
    font = TTFont(key[0], recalcTimestamp=False, lazy=True)
    try:
        best = cast("dict[int, str] | None", font.getBestCmap())
        return frozenset(best or ())
    finally:
        font.close()


def font_codepoints(font_paths: Mapping[int, Path]) -> frozenset[int]:
    """The code points every face can draw (intersection of their best cmaps)."""
    sets = [_cmap(_stat_key(path)) for _weight, path in sorted(font_paths.items())]
    if not sets:
        return frozenset()
    common = sets[0]
    for other in sets[1:]:
        common &= other
    return common


def used_codepoints(text: str) -> frozenset[int]:
    """The code points of ``text`` as written and HTML-unescaped, plus the page-counter characters.

    Control characters are left out; the browser draws no glyph for them."""
    chars = set(text) | set(html.unescape(text)) | set(ALWAYS_INCLUDED)
    return frozenset(ord(ch) for ch in chars if ord(ch) >= 0x20 and not 0x7F <= ord(ch) <= 0x9F)


def _drawable(ch: str, codepoints: frozenset[int]) -> bool:
    code = ord(ch)
    return ch in KEPT_CONTROLS or (code >= 0x20 and not 0x7F <= code <= 0x9F and code in codepoints)


def cover_text(text: str, codepoints: frozenset[int]) -> str:
    """Replace every character the report fonts cannot draw, and control characters other than tab,
    newline and carriage return, by ``[U+XXXX]``.

    Applied to the whole HTML document (markup and CSS are ASCII), so a dataset name with an emoji or a
    radical never makes the browser fall back to a system font and the PDF check never fails on dataset
    text (dataset data never ends with exit 2)."""
    missing = sorted(ch for ch in set(text) if not _drawable(ch, codepoints))
    if not missing:
        return text
    pattern = re.compile("[" + "".join(re.escape(ch) for ch in missing) + "]")
    return pattern.sub(lambda match: f"[U+{ord(match.group(0)):04X}]", text)


@lru_cache(maxsize=32)
def _subset(key: tuple[str, int, int], codepoints: frozenset[int]) -> bytes:
    options = subset.Options()
    options.name_IDs = list(NAME_IDS)
    options.name_languages = [0x409]
    options.recalc_timestamp = False
    options.notdef_outline = True
    options.hinting = False
    font = TTFont(key[0], recalcTimestamp=False, lazy=True)
    try:
        subsetter = subset.Subsetter(options=options)
        subsetter.populate(unicodes=sorted(codepoints))
        subsetter.subset(font)
        buffer = io.BytesIO()
        font.save(buffer)
        return buffer.getvalue()
    finally:
        font.close()


def subset_ttf(path: Path, codepoints: Iterable[int]) -> bytes:
    """A TrueType subset of ``path`` with the glyphs of ``codepoints`` (deterministic bytes)."""
    return _subset(_stat_key(path), frozenset(codepoints))


def subset_font_css(font_paths: Mapping[int, Path], text: str, *, family: str = FONT_FAMILY) -> str:
    """One ``@font-face`` rule per weight with a subset that covers ``text`` (A-27).

    ``family`` must be a plain name (letters, digits, spaces, hyphens); it is written between double
    quotes."""
    if not family or any(not (ch.isalnum() or ch in " -") for ch in family):
        raise ValueError("font family must be a plain name")
    codepoints = used_codepoints(text) & font_codepoints(font_paths)
    rules = []
    for weight, path in sorted(font_paths.items()):
        data = base64.b64encode(subset_ttf(path, codepoints)).decode("ascii")
        rules.append(
            f'@font-face {{ font-family: "{family}"; font-weight: {weight}; font-style: normal; '
            f'src: url(data:font/ttf;base64,{data}) format("truetype"); }}'
        )
    return "\n".join(rules) + "\n"
