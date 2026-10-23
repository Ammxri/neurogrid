"""Access to NeuroGrid's language tables (zh/en/de) and its texts for BIDS validator codes (A-06)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from neurogrid.kernel.i18n import Translator, load_tables
from neurogrid.kernel.safety import load_yaml

I18N_DIR = Path(__file__).parent / "i18n"
VALIDATOR_CODES = Path(__file__).parent / "validator_codes.yaml"
REPORT_LANGUAGES = ("zh", "en")  # NG-F13; de exists as kernel table only (A-07, D-10 i)
# static Noto Sans SC cuts made by tools/build_fonts.py (A-27), weight -> file; subset at run time
FONT_DIR = Path(__file__).parent / "fonts"
FONT_FILES = {400: FONT_DIR / "NotoSansSC-Regular.ttf", 700: FONT_DIR / "NotoSansSC-Bold.ttf"}


@lru_cache(maxsize=1)
def tables() -> dict[str, dict[str, str]]:
    return load_tables(I18N_DIR)


def translator(lang: str, *, strict: bool = False) -> Translator:
    return Translator(tables(), lang, strict=strict)


def disclaimer(lang: str) -> str:
    return tables()[lang]["disclaimer"]


@lru_cache(maxsize=1)
def validator_codes() -> dict[str, dict[str, str]]:
    """Code -> {category, en, zh, de}: NeuroGrid's own one-sentence text per validator code (A-06)."""
    data = load_yaml(VALIDATOR_CODES.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError("validator_codes.yaml must be a mapping")
    return {str(code): {str(k): str(v) for k, v in entry.items()} for code, entry in data.items()}


def validator_text(code: str, lang: str) -> str | None:
    """The text for a validator code, or None for a code NeuroGrid has no text for."""
    entry = validator_codes().get(code)
    return entry.get(lang) if entry else None
