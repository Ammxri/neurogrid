from __future__ import annotations

import math
from datetime import date
from enum import Enum

import pytest

from neurogrid.kernel import canonical, glob


class Colour(Enum):
    RED = "red"


def test_rounding_and_negative_zero() -> None:
    assert canonical.round_float(0.123456789) == 0.123457
    assert canonical.round_float(-0.0) == 0.0
    assert str(canonical.round_float(-1e-12)) == "-1e-12"


def test_non_finite_rejected() -> None:
    with pytest.raises(ValueError):
        canonical.dumps({"x": math.nan})
    with pytest.raises(ValueError):
        canonical.round_float(math.inf)


def test_dumps_is_sorted_and_stable() -> None:
    data = {"b": [1.0000004, Colour.RED], "a": date(2026, 1, 2), "c": None, "d": (True,)}
    first = canonical.dumps(data)
    assert first == canonical.dumps(dict(reversed(list(data.items()))))
    assert first.decode().index('"a"') < first.decode().index('"b"')
    assert b'"2026-01-02"' in first and b'"red"' in first and first.endswith(b"\n")
    assert canonical.sha256_of(data) == canonical.sha256_of(dict(data))


def test_unknown_type_rejected() -> None:
    with pytest.raises(TypeError):
        canonical.normalize(object())


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        ("sub-07/**", "sub-07/eeg/x.edf", True),
        ("sub-07/**", "sub-07", True),
        ("sub-07/**", "sub-08/eeg/x.edf", False),
        ("**/*.edf", "a/b/c.edf", True),
        ("**/*.edf", "c.edf", True),
        ("*.edf", "a/c.edf", False),
        ("sub-0?/eeg/*", "sub-01/eeg/f.edf", True),
        ("Sub-07/**", "sub-07/x", False),
        ("rec-1234abcd", "rec-1234abcd", True),
        ("a/**/z", "a/z", True),
        ("a/**/z", "a/b/c/z", True),
    ],
)
def test_glob(pattern: str, path: str, expected: bool) -> None:
    assert glob.match(pattern, path) is expected
