"""Report fonts (A-27): the code points of the static Noto Sans SC cuts and runtime subsets, embedded as
``@font-face`` rules with ``data:`` URIs.

The static cuts (weights 400 and 700) are produced once by tools/build_fonts.py and carry no radical or
compatibility code points, so the text of a printed report never contains e.g. U+2F63 instead of 生.
Subsetting is deterministic: the same font file, the same code points and the same fontTools version give
the same bytes (no timestamp recalculation, sorted input). In every subset each code point has its own
glyph (separate_shared_glyphs), so the text of the PDF is the text of the HTML; a copy keeps the kerning,
mark positions and localized forms of the glyph it was copied from (GlyphCopies). Font paths are passed in
by the product (A-23).
"""

from __future__ import annotations

import base64
import html
import io
from collections.abc import Iterable, Iterator, Mapping, Sequence
from copy import deepcopy
from functools import lru_cache
from itertools import product
from pathlib import Path
from typing import Any, cast

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


@lru_cache(maxsize=8)
def _postscript_name(key: tuple[str, int, int]) -> str:
    font = TTFont(key[0], recalcTimestamp=False, lazy=True)
    try:
        name = font["name"].getDebugName(6)
    finally:
        font.close()
    if not name:
        raise ValueError("font without a PostScript name (name ID 6)")
    return str(name)


def postscript_names(font_paths: Mapping[int, Path]) -> tuple[str, ...]:
    """The PostScript names (name ID 6) of the faces, by weight. Chromium embeds a subset of a face as
    ``ABCDEF+<PostScript name>``; the PDF QA gate accepts no other font (kernel/pdf.py)."""
    return tuple(_postscript_name(_stat_key(path)) for _weight, path in sorted(font_paths.items()))


def used_codepoints(text: str) -> frozenset[int]:
    """The code points of ``text`` as written and HTML-unescaped, plus the page-counter characters.

    Control characters are left out; the browser draws no glyph for them."""
    chars = set(text) | set(html.unescape(text)) | set(ALWAYS_INCLUDED)
    return frozenset(ord(ch) for ch in chars if ord(ch) >= 0x20 and not 0x7F <= ord(ch) <= 0x9F)


def shared_glyphs(font: TTFont) -> dict[str, list[int]]:
    """Glyphs that several code points of the best cmap share (glyph name -> ascending code points), e.g.
    U+2012/U+2013 or U+002D/U+00AD/U+2011 in Noto Sans SC."""
    by_glyph: dict[str, list[int]] = {}
    for codepoint, name in sorted(cast("dict[int, str]", font.getBestCmap() or {}).items()):
        by_glyph.setdefault(name, []).append(codepoint)
    return {name: codepoints for name, codepoints in by_glyph.items() if len(codepoints) > 1}


def separate_shared_glyphs(font: TTFont, *, layout: bool = True) -> dict[int, str]:
    """Give every code point of ``font`` its own glyph; returns code point -> new glyph name.

    Chromium's PDF writer (Skia) writes one ToUnicode entry per glyph: the lowest code point of the
    embedded font that maps to it (measured). Were a glyph shared, a dataset name with a figure dash
    (U+2012) would make every en dash (U+2013) of the report extract as U+2012, and a required phrase of
    the QA gate could go missing (dataset data never ends with exit 2). The lowest code point keeps the
    glyph; each other one gets a copy with the same outline and metrics, so the PDF text is exactly the
    HTML text. Deterministic: copies are named and ordered by code point.

    With ``layout`` (always, except as a test's negative control) a copy takes part in every GSUB, GPOS
    and GDEF entry of its original (GlyphCopies), so kerning, mark positioning and localized forms are
    the same as with the shared glyph."""
    shared = shared_glyphs(font)
    if not shared:
        return {}
    unsupported = sorted(tag for tag in GLYPH_TABLES_NOT_COPIED if tag in font)
    if unsupported:
        raise ValueError(f"glyph copies would be missing from table(s) {', '.join(unsupported)}")
    copies = {
        codepoint: (name, f"{name}.u{codepoint:04X}")
        for name, codepoints in shared.items()
        for codepoint in codepoints[1:]
    }
    glyphs = GlyphCopies(font)
    for codepoint in sorted(copies):
        glyphs.want(copies[codepoint][0], f".u{codepoint:04X}")
    if layout:
        glyphs.close_substitutions()
    glyphs.create()
    for table in font["cmap"].tables:
        mapping = getattr(table, "cmap", None)
        if mapping:
            for codepoint, (_name, copy) in copies.items():
                if codepoint in mapping:
                    mapping[codepoint] = copy
    if layout:
        glyphs.extend_layout()
    return {codepoint: copy for codepoint, (_name, copy) in copies.items()}


# Tables with per-glyph data that separate_shared_glyphs does not copy (outlines other than glyf, bitmaps,
# colour layers, variations, AAT and legacy kerning, MATH, JSTF): a font with one of them is refused instead
# of getting copies that silently lack it. The static cuts have none of them (tools/build_fonts.py).
GLYPH_TABLES_NOT_COPIED = (
    "CFF ",
    "CFF2",
    "COLR",
    "SVG ",
    "CBDT",
    "CBLC",
    "EBDT",
    "EBLC",
    "sbix",
    "gvar",
    "HVAR",
    "VVAR",
    "VORG",
    "kern",
    "morx",
    "mort",
    "MATH",
    "JSTF",
)
MAX_GLYPHS = 0xFFFF  # glyph IDs are 16 bits
# Glyph sequences of the rules of format-1 (glyph based) contextual lookups.
_RULE_SEQUENCES = ("Backtrack", "Input", "LookAhead")
# (table, lookup type) -> (rule set, rule) attribute names of format 1 of the contextual lookup types
_RULE_SETS = {
    ("GSUB", 5): ("SubRuleSet", "SubRule"),
    ("GSUB", 6): ("ChainSubRuleSet", "ChainSubRule"),
    ("GPOS", 7): ("PosRuleSet", "PosRule"),
    ("GPOS", 8): ("ChainPosRuleSet", "ChainPosRule"),
}
_EXTENSION = {"GSUB": 7, "GPOS": 9}


class GlyphCopies:
    """Copies of glyphs that take part in everything their original takes part in (A-27).

    A copy stands for one code point (or, made by a ligature, for the code points of its components) and
    is named ``<original><suffix>``, the suffix naming them: ``.u2013``, or for a ligature one
    ``.L<length><suffix>`` per component (``.L0`` for an original), so different component sequences never
    give the same copy. It gets the original's outline,
    metrics and GDEF entries, and is added wherever the original is in GSUB and GPOS: coverage tables
    with the records that belong to them, class definitions, pair sets (also as second glyph), substitution
    inputs, ligature components and the glyph sequences of contextual rules (every combination of original
    and copies). A substitution of a copy gives a copy of the substitute with the same suffix
    (close_substitutions): Skia names a glyph that no code point maps to by the text it was shaped from
    (measured: the locl form of U+2026 in English text extracts as U+2026), so a substitute shared by two
    code points would again extract as one of them. Glyph order: copies after every glyph of the font, in
    the order they were wanted."""

    def __init__(self, font: TTFont) -> None:
        self.font = font
        self.order = list(font.getGlyphOrder())
        self.taken = set(self.order)
        self.original: dict[str, str] = {}  # copy -> original
        self.suffix: dict[str, str] = {}  # copy -> suffix
        self.copies: dict[str, list[str]] = {}  # original -> copies, in glyph order

    def want(self, original: str, suffix: str) -> bool:
        """Register the copy ``<original><suffix>`` of a glyph of the font; False if it is known already."""
        copy = original + suffix
        if copy in self.original:
            return False
        if copy in self.taken or original in self.original:
            raise ValueError("glyph name of a copy already in the font")
        if len(self.order) >= MAX_GLYPHS:
            raise ValueError("too many glyphs for copies")
        self.original[copy] = original
        self.suffix[copy] = suffix
        self.copies.setdefault(original, []).append(copy)
        self.order.append(copy)
        self.taken.add(copy)
        return True

    def close_substitutions(self) -> None:
        """Want a copy of every substitute that a copy can be substituted by, until there is no new one."""
        changed = True
        while changed:
            changed = False
            for _tag, kind, subtable in self._subtables("GSUB"):
                for inputs, outputs in self._substitutions(kind, subtable):
                    for variant in self._sequences(inputs)[1:]:
                        suffix = self._ligature_suffix(variant) if kind == 4 else self.suffix[variant[0]]
                        for output in outputs:
                            changed |= self.want(output, suffix)

    def create(self) -> None:
        """Glyph order, outlines and metrics of every wanted copy."""
        if not self.original:
            return
        self.font.setGlyphOrder(list(self.order))
        glyf = self.font["glyf"]
        metrics = [self.font[tag].metrics for tag in ("hmtx", "vmtx") if tag in self.font]
        for copy, original in self.original.items():
            glyf[copy] = deepcopy(glyf[original])
            for table in metrics:
                table[copy] = table[original]

    def extend_layout(self) -> None:
        if not self.original:
            return
        for tag in ("GSUB", "GPOS"):
            for _tag, kind, subtable in self._subtables(tag):
                self._subtable(tag, kind, subtable)
        if "GDEF" in self.font:
            self._gdef(self.font["GDEF"].table)

    # --- building blocks -----------------------------------------------------------------------------

    def _subtables(self, tag: str) -> Iterator[tuple[str, int, Any]]:
        if tag not in self.font or self.font[tag].table.LookupList is None:
            return
        for lookup in self.font[tag].table.LookupList.Lookup:
            for subtable in lookup.SubTable:
                kind = lookup.LookupType
                if kind == _EXTENSION[tag]:
                    kind, subtable = subtable.ExtensionLookupType, subtable.ExtSubTable
                yield tag, kind, subtable

    @staticmethod
    def _substitutions(kind: int, subtable: Any) -> Iterator[tuple[list[str], list[str]]]:
        """(input sequence, substitutes) of a substitution subtable (types 1, 2, 3, 4 and 8)."""
        if kind in (1, 2):
            for name, value in subtable.mapping.items():
                yield [name], [value] if kind == 1 else list(value)
        elif kind == 3:
            for name, value in subtable.alternates.items():
                yield [name], list(value)
        elif kind == 4:
            for first, ligatures in subtable.ligatures.items():
                for ligature in ligatures:
                    yield [first, *ligature.Component], [ligature.LigGlyph]
        elif kind == 8:
            for name, value in zip(subtable.Coverage.glyphs, subtable.Substitute, strict=True):
                yield [name], [value]

    def _id(self, name: str) -> int:
        return int(self.font.getGlyphID(name))

    @staticmethod
    def _substitute(name: str, suffix: str) -> str:
        """The copy of substitute ``name`` for a copy with ``suffix`` (wanted by close_substitutions)."""
        return name + suffix

    def _ligature_suffix(self, components: Sequence[str]) -> str:
        """Each component's suffix ('' for an original) after its length: a suffix starts with '.', so the
        length ends where it starts, and the sequence can be read back (no two sequences share a name)."""
        return "".join(f".L{len(suffix)}{suffix}" for suffix in (self.suffix.get(n, "") for n in components))

    def _variants(self, name: str) -> list[str]:
        return [name, *self.copies.get(name, ())]

    def _coverage(self, coverage: Any, *aligned: list[Any]) -> None:
        """Copies into ``coverage`` with a copy of each record of the lists that follow its order; the
        coverage stays sorted by glyph ID."""
        if coverage is None:
            return
        rows = [list(row) for row in zip(coverage.glyphs, *aligned, strict=True)]
        added = [
            [copy, *(deepcopy(item) for item in row[1:])]
            for row in rows
            for copy in self.copies.get(row[0], ())
        ]
        if not added:
            return
        rows = sorted(rows + added, key=lambda row: self._id(row[0]))
        coverage.glyphs = [row[0] for row in rows]
        for index, items in enumerate(aligned, start=1):
            items[:] = [row[index] for row in rows]

    def _classes(self, class_def: Any) -> None:
        if class_def is None:
            return
        classes = class_def.classDefs
        for name, value in list(classes.items()):
            for copy in self.copies.get(name, ()):
                classes[copy] = value

    def _sequences(self, glyphs: Sequence[str]) -> list[list[str]]:
        """Every variant of ``glyphs`` with originals replaced by their copies; the given one first."""
        return [list(variant) for variant in product(*(self._variants(name) for name in glyphs))]

    def _rules(self, rules: list[Any]) -> list[Any]:
        """Each rule followed by its variants (in a rule set the first matching rule applies)."""
        result = []
        for rule in rules:
            result.append(rule)
            sequences = [list(getattr(rule, name, None) or []) for name in _RULE_SEQUENCES]
            for variant in list(product(*(self._sequences(sequence) for sequence in sequences)))[1:]:
                extra = deepcopy(rule)
                for name, sequence in zip(_RULE_SEQUENCES, variant, strict=True):
                    if sequence:
                        setattr(extra, name, sequence)
                result.append(extra)
        return result

    # --- lookups --------------------------------------------------------------------------------------

    def _subtable(self, tag: str, kind: int, subtable: Any) -> None:
        if tag == "GSUB" and kind in (1, 2, 3):
            mapping = subtable.alternates if kind == 3 else subtable.mapping
            for name, value in list(mapping.items()):
                for copy in self.copies.get(name, ()):
                    suffix = self.suffix[copy]
                    if kind == 1:
                        mapping[copy] = self._substitute(value, suffix)
                    else:
                        mapping[copy] = [self._substitute(item, suffix) for item in value]
        elif tag == "GSUB" and kind == 4:
            self._ligatures(subtable)
        elif (tag, kind) in _RULE_SETS:
            self._context(_RULE_SETS[(tag, kind)], subtable)
        elif tag == "GSUB" and kind == 8:
            substitutes = dict(zip(subtable.Coverage.glyphs, subtable.Substitute, strict=True))
            self._coverage(subtable.Coverage)
            subtable.Substitute = [
                substitutes[name]
                if name in substitutes
                else self._substitute(substitutes[self.original[name]], self.suffix[name])
                for name in subtable.Coverage.glyphs
            ]
            for coverage in (*subtable.BacktrackCoverage, *subtable.LookAheadCoverage):
                self._coverage(coverage)
        elif tag == "GPOS" and kind == 1:
            if subtable.Format == 1:
                self._coverage(subtable.Coverage)
            else:
                self._coverage(subtable.Coverage, subtable.Value)
        elif tag == "GPOS" and kind == 2:
            self._pairs(subtable)
        elif tag == "GPOS" and kind == 3:
            self._coverage(subtable.Coverage, subtable.EntryExitRecord)
        elif tag == "GPOS" and kind in (4, 5, 6):
            self._marks(kind, subtable)
        else:
            raise ValueError(f"{tag} lookup type {kind} is not supported")

    def _ligatures(self, subtable: Any) -> None:
        ligatures: dict[str, list[Any]] = {}
        for first, entries in subtable.ligatures.items():
            for ligature in entries:
                variants = self._sequences([first, *ligature.Component])
                ligatures.setdefault(first, []).append(ligature)
                for variant in variants[1:]:
                    extra = deepcopy(ligature)
                    extra.Component = variant[1:]
                    extra.LigGlyph = self._substitute(ligature.LigGlyph, self._ligature_suffix(variant))
                    ligatures.setdefault(variant[0], []).append(extra)
        subtable.ligatures = ligatures

    def _context(self, names: tuple[str, str], subtable: Any) -> None:
        if subtable.Format == 1:
            rule_set, rule = names
            sets = getattr(subtable, rule_set)
            for entry in sets:
                if entry is not None:
                    setattr(entry, rule, self._rules(getattr(entry, rule)))
            self._coverage(subtable.Coverage, sets)
        elif subtable.Format == 2:
            self._coverage(subtable.Coverage)
            for name in ("ClassDef", "BacktrackClassDef", "InputClassDef", "LookAheadClassDef"):
                self._classes(getattr(subtable, name, None))
        else:
            for name in ("Coverage", "BacktrackCoverage", "InputCoverage", "LookAheadCoverage"):
                for coverage in getattr(subtable, name, None) or []:
                    self._coverage(coverage)

    def _pairs(self, subtable: Any) -> None:
        if subtable.Format == 1:
            for pair_set in subtable.PairSet:
                records = list(pair_set.PairValueRecord)
                for record in pair_set.PairValueRecord:
                    for copy in self.copies.get(record.SecondGlyph, ()):
                        extra = deepcopy(record)
                        extra.SecondGlyph = copy
                        records.append(extra)
                pair_set.PairValueRecord = sorted(records, key=lambda record: self._id(record.SecondGlyph))
            self._coverage(subtable.Coverage, subtable.PairSet)
        else:
            self._coverage(subtable.Coverage)
            self._classes(subtable.ClassDef1)
            self._classes(subtable.ClassDef2)

    def _marks(self, kind: int, subtable: Any) -> None:
        if kind == 4:
            self._coverage(subtable.MarkCoverage, subtable.MarkArray.MarkRecord)
            self._coverage(subtable.BaseCoverage, subtable.BaseArray.BaseRecord)
        elif kind == 5:
            self._coverage(subtable.MarkCoverage, subtable.MarkArray.MarkRecord)
            self._coverage(subtable.LigatureCoverage, subtable.LigatureArray.LigatureAttach)
        else:
            self._coverage(subtable.Mark1Coverage, subtable.Mark1Array.MarkRecord)
            self._coverage(subtable.Mark2Coverage, subtable.Mark2Array.Mark2Record)

    def _gdef(self, table: Any) -> None:
        self._classes(getattr(table, "GlyphClassDef", None))
        self._classes(getattr(table, "MarkAttachClassDef", None))
        attach = getattr(table, "AttachList", None)
        if attach is not None:
            self._coverage(attach.Coverage, attach.AttachPoint)
        carets = getattr(table, "LigCaretList", None)
        if carets is not None:
            self._coverage(carets.Coverage, carets.LigGlyph)
        sets = getattr(table, "MarkGlyphSetsDef", None)
        if sets is not None:
            for coverage in sets.Coverage:
                self._coverage(coverage)


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
        separate_shared_glyphs(font)
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
