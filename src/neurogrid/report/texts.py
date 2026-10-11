"""Access to NeuroGrid's language tables (zh/en/de)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from neurogrid.kernel.i18n import Translator, load_tables

I18N_DIR = Path(__file__).parent / "i18n"
REPORT_LANGUAGES = ("zh", "en")  # NG-F13; de exists as kernel table only (A-07, D-10 i)


@lru_cache(maxsize=1)
def tables() -> dict[str, dict[str, str]]:
    return load_tables(I18N_DIR)


def translator(lang: str, *, strict: bool = False) -> Translator:
    return Translator(tables(), lang, strict=strict)


def disclaimer(lang: str) -> str:
    return tables()[lang]["disclaimer"]
