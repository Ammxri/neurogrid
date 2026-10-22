"""Heuristics for identifying header content (A-05, A-51, A-64), shared by all adapters, and the display
rule for free text from data files (A-17, A-51, C5).

Values are only inspected, never kept or returned; adapters report field names only.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Collection
from typing import NamedTuple

PLACEHOLDER_TOKENS = frozenset({"x", "-", "_", "0", "anonymous", "anon", "unknown", "n/a", "na", "none"})
DATE_IN_TEXT = re.compile(
    r"\b(?:\d{1,2}[-./](?:\d{1,2}|[A-Za-z]{3})[-./]\d{2,4}|\d{4}[-./]\d{1,2}[-./]\d{1,2})\b"
)
DATE_PLACEHOLDER = re.compile(
    r"^(?:01-JAN-\d{4}|01[-./]01[-./]\d{2,4}|\d{4}[-./]0?1[-./]0?1)$", re.IGNORECASE
)
# Bounded parts (real name parts are short): the unbounded form backtracked quadratically on text such as
# "A-A-A-..." in a 2 MB BrainVision comment (A-53); with bounds each start costs a constant number of steps.
NAME_LIKE = re.compile(r"\b[A-Z][A-Za-z'-]{1,40}[ ,_]{1,8}[A-Z][A-Za-z'-]{1,40}\b")
LONG_NUMBER = re.compile(r"\d{6,}")
NON_ASCII = "�"  # replacement character from decoding non-ASCII bytes
# An absolute path (drive, UNC or POSIX root) in free text reveals folder names of the original system.
ABSOLUTE_PATH = re.compile(r"(?:\b[A-Za-z]:[\\/]|\\\\[^\\\s]|(?:^|\s)/[A-Za-z0-9_.-]+/)")


# Further forms of dates and clock times that the display rule hides (C5, A-51) besides real_dates, which the
# A-05 header heuristics keep narrow: a month name next to a day or a year ("12 Mar 1961", "March 1961"), a
# year 1900-2099 not glued to letters or digits ("born 1961", also the year of a blanked date such as
# 01.01.1985: a birth year is an age), and clock times hh.mm(.ss) with a two-digit hour ("22.31"), hhHmm
# ("22h31") or with am/pm ("10.30 pm", "8pm"). Not counted, so that codes stay readable: decimals with a
# one-digit whole part ("0.25", "8.30"), a year glued to letters ("S1999") and four digits that are no year
# ("2231").
_MONTH = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
    r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)
NAMED_DATE = re.compile(
    rf"(?<![A-Za-z0-9])(?:\d{{1,2}}(?:st|nd|rd|th)?[ _.,/-]{{0,3}}{_MONTH}(?![A-Za-z])"
    rf"|{_MONTH}\.?[ _.,/-]{{0,3}}\d{{1,4}}(?!\d))",
    re.IGNORECASE,
)
YEAR_IN_TEXT = re.compile(r"(?<![A-Za-z0-9])(?:19|20)\d{2}(?!\d)")
CLOCK_TIME = re.compile(
    r"(?<![A-Za-z0-9.])(?:(?:[01]\d|2[0-3])\.[0-5]\d(?:\.[0-5]\d)?(?![\d.])"
    r"|(?:[01]?\d|2[0-3])h[0-5]\d(?!\d)"
    r"|(?:0?[1-9]|1[0-2])(?:[.h][0-5]\d)?[ _]?[ap]\.?m\.?(?![A-Za-z]))",
    re.IGNORECASE,
)


def placeholder(text: str) -> bool:
    return all(token.lower() in PLACEHOLDER_TOKENS for token in text.split())


def _numeric_dates(text: str) -> bool:
    return any(not DATE_PLACEHOLDER.match(m.group(0)) for m in DATE_IN_TEXT.finditer(text))


def real_dates(text: str) -> bool:
    return _numeric_dates(text.replace("_", " "))  # EDF+ writes spaces inside subfields as underscores


def dates_or_times(text: str) -> bool:
    """The display rule's wider view (C5, A-51): a real date (``real_dates``, also with underscores as date
    separators: "born_12_03_1961"), a date with a month name, a year standing alone, or a clock time."""
    return bool(
        real_dates(text)
        or _numeric_dates(text.replace("_", "-"))
        or NAMED_DATE.search(text)
        or YEAR_IN_TEXT.search(text)
        or CLOCK_TIME.search(text)
    )


def looks_identifying(text: str) -> bool:
    """A name, a long number, non-ASCII characters or an absolute path."""
    spaced = text.replace("_", " ")
    return bool(
        NAME_LIKE.search(spaced)
        or LONG_NUMBER.search(text)
        or NON_ASCII in text
        or any(ord(ch) > 127 for ch in text)
        or ABSOLUTE_PATH.search(text)
    )


# A-17: a code or label from a data file is shown only if it is short and made of these characters.
DISPLAYABLE = re.compile(r"[A-Za-z0-9_.\-/ ]{1,32}")
FREE_TEXT_PREFIX = "text-"  # subkey of a value that is not shown (A-17, like pattern-<sha8> in A-69)
ANNOTATOR_PREFIX = "ann-"  # pseudonym of an annotator ID (A-51, A-68)


def short_hash(value: str) -> str:
    """The first 8 hex digits of SHA-256 over the UTF-8 bytes (surrogates kept, so any text has one)."""
    return hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest()[:8]


class DisplayedText(NamedTuple):
    """How a value from a data file appears in outputs.

    ``shown`` is the value itself, or None for free text, which outputs show as "free text (n characters)"
    (report.value.free_text, with n = len(value)); ``subkey`` is the value itself or the stable
    ``text-<sha256[:8]>``. Neither depends on --show-paths, so finding keys and exceptions do not either
    (A-68).
    """

    shown: str | None
    subkey: str


def display_text(value: str, vocabulary: Collection[str] = ()) -> DisplayedText:
    """A-17 with the refinement of C5: a value is shown if it is in the vocabulary, or if it fully matches
    the A-17 pattern (``DISPLAYABLE``) and does not look like personal data: no name, long number or
    absolute path (``looks_identifying``) and no date, year or clock time such as "born 12.03.1961",
    "recorded 2019-03-12", "born 12 Mar 1961", "born 1961", "Lights off 22.31" or "22h31"
    (``dates_or_times``, A-05; the placeholder date 01.01.85 stays visible). Annotation codes, class labels
    and annotator IDs from files all use this one rule (A-51)."""
    if value in vocabulary or (
        DISPLAYABLE.fullmatch(value) and not looks_identifying(value) and not dates_or_times(value)
    ):
        return DisplayedText(value, value)
    return DisplayedText(None, FREE_TEXT_PREFIX + short_hash(value))


def annotator_pseudonym(annotator: str) -> str:
    """``ann-<sha256[:8]>`` of the raw annotator ID: the subkey of per-annotator findings, the same with and
    without --show-paths (A-68, C5)."""
    return ANNOTATOR_PREFIX + short_hash(annotator)
