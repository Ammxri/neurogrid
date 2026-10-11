"""Deterministic JSON serialization (NG-N03, A-61).

Floats are rounded to 6 significant digits, -0.0 becomes 0.0, non-finite numbers are rejected,
keys are sorted. Lists keep the order chosen by the producer, which must be deterministic.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from datetime import date
from enum import Enum
from typing import Any

from pydantic import BaseModel

SIGNIFICANT_DIGITS = 6


def round_float(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("non-finite float in canonical output")
    rounded = float(format(value, f".{SIGNIFICANT_DIGITS}g"))
    return 0.0 if rounded == 0 else rounded


def normalize(obj: Any) -> Any:
    """Convert models, enums, dates and nested containers into canonical JSON values."""
    if isinstance(obj, BaseModel):
        return normalize(obj.model_dump(mode="json"))
    if isinstance(obj, bool) or obj is None or isinstance(obj, str):
        return obj
    if isinstance(obj, Enum):
        return normalize(obj.value)
    if isinstance(obj, int):
        return obj
    if isinstance(obj, float):
        return round_float(obj)
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, Mapping):
        return {str(key): normalize(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [normalize(item) for item in obj]
    raise TypeError(f"type {type(obj).__name__} is not allowed in canonical output")


def dumps(obj: Any) -> bytes:
    """Canonical, human-readable JSON as UTF-8 bytes with a trailing newline."""
    text = json.dumps(normalize(obj), ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
    return (text + "\n").encode("utf-8")


def compact(obj: Any) -> bytes:
    """Canonical JSON without whitespace, used as hash input."""
    text = json.dumps(
        normalize(obj), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return text.encode("utf-8")


def sha256_of(obj: Any) -> str:
    return hashlib.sha256(compact(obj)).hexdigest()
