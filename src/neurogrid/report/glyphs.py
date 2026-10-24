"""Glyph safety of the report (REP-00, A-27): no character reaches the HTML or PDF that the embedded report
font cannot draw, so Chromium never falls back to a system font.

A character is replaced by the visible text ``[U+XXXX]`` when it is a C0 or C1 control character (tab, line
feed and carriage return excepted, HTML treats them as white space), a lone surrogate (not encodable as
UTF-8), or - when the report fonts are installed - a code point that one of the fonts does not map to a
glyph (emoji, characters beyond the font's coverage, the CJK radicals that tools/build_fonts.py removes). The
replacement keeps the text readable and adds no data: the code point is the character itself.
"""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path

KEPT_CONTROLS = frozenset({0x09, 0x0A, 0x0D})


def _drawable(codepoint: int, covered: frozenset[int] | None) -> bool:
    if codepoint in KEPT_CONTROLS:
        return True
    if codepoint < 0x20 or 0x7F <= codepoint <= 0x9F or 0xD800 <= codepoint <= 0xDFFF:
        return False
    return covered is None or codepoint in covered


@lru_cache(maxsize=4)
def _coverage(paths: tuple[Path, ...]) -> frozenset[int] | None:
    if not paths or not all(path.is_file() for path in paths):
        return None
    from fontTools.ttLib import TTFont

    covered: frozenset[int] | None = None
    for path in paths:
        with TTFont(path, lazy=True) as font:  # closed again: the file stays deletable and replaceable
            cmap = frozenset(font.getBestCmap() or ())
        covered = cmap if covered is None else covered & cmap
    return covered


def font_coverage(paths: Iterable[Path]) -> frozenset[int] | None:
    """The code points every font in ``paths`` maps to a glyph; None when a font file does not exist (the
    report fonts are package data; without them no font is embedded and only the characters that are never
    drawable are replaced)."""
    return _coverage(tuple(paths))


def glyph_safe(text: str, covered: frozenset[int] | None) -> str:
    """``text`` with every character the report cannot draw written as ``[U+XXXX]``."""
    if all(_drawable(ord(char), covered) for char in text):
        return text
    return "".join(char if _drawable(ord(char), covered) else f"[U+{ord(char):04X}]" for char in text)
