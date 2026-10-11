"""Language tables zh/en/de (PRD §1, NG-N06, A-07).

Own messages are only produced through keys. Tables are nested YAML mappings, addressed with dotted keys.
"""

from __future__ import annotations

import locale
import os
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from neurogrid.kernel.errors import ConfigError
from neurogrid.kernel.safety import load_yaml

LANGUAGES: tuple[str, ...] = ("zh", "en", "de")
DEFAULT_LANGUAGE = "en"


def flatten(data: Mapping[str, Any], prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, value in data.items():
        dotted = f"{prefix}{key}"
        if isinstance(value, Mapping):
            flat.update(flatten(value, dotted + "."))
        else:
            flat[dotted] = str(value)
    return flat


def load_tables(directory: Path, languages: Sequence[str] = LANGUAGES) -> dict[str, dict[str, str]]:
    tables: dict[str, dict[str, str]] = {}
    for lang in languages:
        data = load_yaml((directory / f"{lang}.yaml").read_text(encoding="utf-8"))
        if not isinstance(data, Mapping):
            raise ConfigError("i18n.invalid_table", language=lang)
        tables[lang] = flatten(data)
    return tables


class _Missing(dict[str, object]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


class Translator:
    def __init__(self, tables: Mapping[str, Mapping[str, str]], lang: str, *, strict: bool = False) -> None:
        if lang not in tables:
            raise ConfigError("i18n.unknown_language", language=lang)
        self.lang = lang
        self._tables = tables
        self._strict = strict

    def has(self, key: str, /) -> bool:
        return key in self._tables[self.lang]

    def t(self, key: str, /, **params: object) -> str:
        table = self._tables[self.lang]
        if key in table:
            text = table[key]
        elif self._strict:
            raise KeyError(f"missing translation {self.lang}:{key}")
        else:
            fallback = self._tables.get(DEFAULT_LANGUAGE, {}).get(key)
            if fallback is None:
                return key  # unknown keys (e.g. from a foreign results.json) are never used as a template
            text = fallback
        return text.format_map(_Missing(params))


def normalize_language(value: str) -> str:
    """'zh_CN.UTF-8', 'zh-CN' and 'ZH' all name the language 'zh'."""
    return re.split(r"[-_.@\s]", value.strip().lower(), maxsplit=1)[0]


def detect_language(explicit: str | None = None, supported: Sequence[str] = LANGUAGES) -> str:
    """--lang > NEUROGRID_LANG > system locale > en.

    An explicit or NEUROGRID_LANG value that names no supported language is an error, not a silent fallback.
    """
    for candidate in (explicit, os.environ.get("NEUROGRID_LANG")):
        if candidate is None:
            continue
        if not candidate.strip():
            raise ConfigError("i18n.empty")  # set but empty is no silent fallback either
        if candidate:
            lang = normalize_language(candidate)
            if lang not in supported:
                raise ConfigError("i18n.unknown_language", language=candidate.strip()[:20])
            return lang
    system = (locale.getlocale()[0] or "").lower()
    for lang in supported:
        if (
            system.startswith(lang)
            or (lang == "zh" and "chinese" in system)
            or (lang == "de" and "german" in system)
        ):
            return lang
    return DEFAULT_LANGUAGE
