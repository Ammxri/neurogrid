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


def placeholder(text: str) -> bool:
    return all(token.lower() in PLACEHOLDER_TOKENS for token in text.split())


def real_dates(text: str) -> bool:
    spaced = text.replace("_", " ")  # EDF+ writes spaces inside subfields as underscores
    return any(not DATE_PLACEHOLDER.match(m.group(0)) for m in DATE_IN_TEXT.finditer(spaced))


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
    the A-17 pattern (``DISPLAYABLE``) and does not look identifying (a name, a long number, an absolute
    path). Annotation codes, class labels and annotator IDs from files all use this one rule (A-51)."""
    if value in vocabulary or (DISPLAYABLE.fullmatch(value) and not looks_identifying(value)):
        return DisplayedText(value, value)
    return DisplayedText(None, FREE_TEXT_PREFIX + short_hash(value))


def annotator_pseudonym(annotator: str) -> str:
    """``ann-<sha256[:8]>`` of the raw annotator ID: the subkey of per-annotator findings, the same with and
    without --show-paths (A-68, C5)."""
    return ANNOTATOR_PREFIX + short_hash(annotator)
