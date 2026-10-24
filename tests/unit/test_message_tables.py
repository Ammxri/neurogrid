"""Every message exists in zh and en and is written in its language (NG-N06, A-07).

The key sets, placeholders and used keys are compared in test_language_and_wording.py; here the texts
themselves: none is empty, the Chinese table holds Chinese text, the English and German tables hold no
Chinese, and the texts NeuroGrid keeps outside the tables (validator codes, built-in rule titles) are
translated too."""

from __future__ import annotations

import re
from importlib import resources

import pytest

from neurogrid.kernel.i18n import LANGUAGES
from neurogrid.kernel.rules import load_rulepack
from neurogrid.report.texts import tables, validator_codes

HAN = re.compile("[㐀-䶿一-鿿]")
PLACEHOLDER = re.compile(r"\{[a-z_]+\}")
# Two Latin words in a row: prose. A Chinese text may contain names (neurogrid.toml, EEGChannelCount, N),
# placeholders and punctuation without any Han character, but never an English sentence.
PROSE = re.compile(r"[A-Za-z]{2,}[ \t]+[A-Za-z]{2,}")
BUILTIN_PACKS = ("core", "bids", "gxdsl008")


def untranslated(zh: str) -> bool:
    """True if a Chinese text is English prose: no Han character, but two Latin words in a row."""
    return not HAN.search(zh) and bool(PROSE.search(PLACEHOLDER.sub(" ", zh)))


def test_no_text_is_empty() -> None:
    empty = [(lang, key) for lang in LANGUAGES for key, value in tables()[lang].items() if not value.strip()]
    assert not empty, empty


def test_chinese_texts_are_chinese() -> None:
    hits = sorted(key for key, value in tables()["zh"].items() if untranslated(value))
    assert not hits, hits


def test_language_neutral_chinese_texts_are_names_or_punctuation() -> None:
    """The zh texts without a Han character (measured: 7 of 580 at P5) are names, symbols or placeholders."""
    neutral = {key: value for key, value in tables()["zh"].items() if not HAN.search(value)}
    assert neutral and all(not untranslated(value) for value in neutral.values())
    for key in ("report.value.none", "report.text.origin_config", "cli.help.metavar.number"):
        assert key in neutral, key


@pytest.mark.parametrize("lang", [lang for lang in LANGUAGES if lang != "zh"])
def test_other_tables_hold_no_chinese(lang: str) -> None:
    hits = sorted(key for key, value in tables()[lang].items() if HAN.search(value))
    assert not hits, (lang, hits)


@pytest.mark.parametrize(
    ("text", "flagged"),
    [
        ("Show this message and exit.", True),
        ("the option {name} is required", True),
        ("显示本帮助并退出。", False),
        ("neurogrid.toml", False),
        ("EEGChannelCount", False),
        ("{split}：{names}", False),
        ("{count} / {total}（{unit}）", False),
        ("N", False),
    ],
)
def test_untranslated_detector(text: str, flagged: bool) -> None:
    assert untranslated(text) is flagged


def test_validator_code_texts_are_translated() -> None:
    """A-06: NeuroGrid's own text per validator code exists in every language and is written in it."""
    codes = validator_codes()
    assert codes
    for code, entry in codes.items():
        assert all(entry.get(lang, "").strip() for lang in LANGUAGES), code
        assert HAN.search(entry["zh"]), code
        assert not any(HAN.search(entry[lang]) for lang in LANGUAGES if lang != "zh"), code


@pytest.mark.parametrize("name", BUILTIN_PACKS)
def test_builtin_rule_titles_are_translated(name: str) -> None:
    data = resources.files("neurogrid.rulepacks").joinpath(f"{name}.yaml").read_bytes()
    pack = load_rulepack(data, "builtin").pack
    for rule in pack.rules:
        assert rule.title_zh.strip() and rule.title_en.strip(), rule.id
        assert HAN.search(rule.title_zh), rule.id
        assert not HAN.search(rule.title_en), rule.id
