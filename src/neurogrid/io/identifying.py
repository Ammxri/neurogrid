"""Heuristics for identifying header content (A-05, A-51, A-64), shared by all adapters.

Values are only inspected, never kept or returned; adapters report field names only.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Collection

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


# A-17: free text (annotation codes, class labels, annotator IDs) is shown only in this form (C5).
DISPLAYABLE_TEXT = re.compile(r"[A-Za-z0-9_.\-/ ]{1,32}")


def display_text(value: str, vocabulary: Collection[str] = ()) -> tuple[str | None, str]:
    """How a free-text value from the dataset may appear in outputs (A-17, A-51; decision C5).

    Returns ``(shown, subkey)``. A value of the documented vocabulary, or one that matches the A-17 pattern
    and does not look identifying, is shown as it is and is its own subkey. Any other value is not shown
    (``shown`` is None; outputs give "free text (n characters)" instead) and its subkey is the stable
    pseudonym ``text-<sha256[:8]>``. The subkey never depends on --show-paths (A-68).
    """
    if value in vocabulary or (DISPLAYABLE_TEXT.fullmatch(value) and not looks_identifying(value)):
        return value, value
    digest = hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest()[:8]
    return None, f"text-{digest}"
