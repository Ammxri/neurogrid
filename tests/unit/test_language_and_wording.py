"""Language tables complete in zh/en/de (NG-N06, A-07) and no conformity claims anywhere (POS-01, A-57)."""

from __future__ import annotations

import re
from importlib import resources
from pathlib import Path

import pytest

from neurogrid.kernel.errors import ConfigError
from neurogrid.kernel.i18n import LANGUAGES, Translator, detect_language, flatten
from neurogrid.kernel.safety import load_yaml
from neurogrid.report.texts import tables

ROOT = Path(__file__).parent.parent.parent
SRC = ROOT / "src" / "neurogrid"


def test_all_languages_have_the_same_keys() -> None:
    loaded = tables()
    keys = {lang: set(loaded[lang]) for lang in LANGUAGES}
    for lang in LANGUAGES:
        assert keys[lang] == keys["en"], f"{lang}: {sorted(keys[lang] ^ keys['en'])[:20]}"


def test_placeholders_match_across_languages() -> None:
    loaded = tables()
    for key, text in loaded["en"].items():
        expected = set(re.findall(r"\{(\w+)\}", text))
        for lang in LANGUAGES:
            assert set(re.findall(r"\{(\w+)\}", loaded[lang][key])) == expected, f"{lang}:{key}"


def test_keys_used_in_code_exist() -> None:
    loaded = tables()["en"]
    used: set[str] = set()
    for path in [*SRC.rglob("*.py"), *SRC.rglob("*.j2")]:
        text = path.read_text(encoding="utf-8")
        used.update(re.findall(r"""(?:t|_say|tr)\(\s*['"]([a-z_]+(?:\.[a-z_0-9]+)+)['"]""", text))
        used.update(f"errors.{k}" for k in re.findall(r"""Error\(\s*['"]([a-z_]+\.[a-z_]+)['"]""", text))
    for path in SRC.rglob("*.py"):
        for key in re.findall(
            r"""reason\s*=\s*['"]([a-z_]+\.[a-z_]+)['"]""", path.read_text(encoding="utf-8")
        ):
            used.add(f"reason.{key}")
        text = path.read_text(encoding="utf-8")
        # reasons and header issues that are raised, not passed as reason=... (Review P2: convert.failed,
        # header.external_reference were missing and printed as bare keys)
        used.update(
            f"reason.{k}" for k in re.findall(r"""_NotConverted\(\s*['"]([a-z_]+\.[a-z_]+)['"]""", text)
        )
        used.update(f"issue.{k}" for k in re.findall(r"""['"]((?:header|companion)\.[a-z_]+)['"]""", text))
    used = {k for k in used if not k.startswith("errors.errors.")}
    prefixes = {k for k in used if k.endswith(("_", "."))}
    missing = sorted(k for k in used - prefixes if k not in loaded)
    missing += sorted(p for p in prefixes if not any(key.startswith(p) for key in loaded))
    assert not missing, missing


def test_translator_behaviour() -> None:
    tr = Translator({"en": {"a": "A {x}"}, "zh": {}}, "zh")
    assert tr.t("a", x=1) == "A 1" and tr.t("missing") == "missing" and not tr.has("a")
    assert Translator({"en": {"a": "{y}"}}, "en").t("a") == "{y}"
    with pytest.raises(KeyError):
        Translator({"zh": {}}, "zh", strict=True).t("x")
    with pytest.raises(ConfigError):
        Translator({"en": {}}, "fr")
    assert flatten({"a": {"b": 1}}) == {"a.b": "1"}


def test_detect_language(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEUROGRID_LANG", "zh")
    assert detect_language(None) == "zh" and detect_language("EN") == "en"
    monkeypatch.delenv("NEUROGRID_LANG")
    assert detect_language(None) in LANGUAGES


def _wording() -> dict[str, list[str]]:
    data = load_yaml((SRC / "report" / "wording" / "forbidden.yaml").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _forbidden() -> dict[str, list[re.Pattern[str]]]:
    return {
        lang: [re.compile(p) for p in patterns] for lang, patterns in _wording().items() if lang != "allowed"
    }


def _texts_to_scan() -> list[tuple[str, str]]:
    disclaimers = [tables()[lang]["disclaimer"] for lang in LANGUAGES]
    sources = [*SRC.rglob("*.yaml"), *SRC.rglob("*.j2"), ROOT / "README.md", ROOT / "pyproject.toml"]
    texts = []
    for path in sources:
        if path.name == "forbidden.yaml":
            continue
        text = path.read_text(encoding="utf-8")
        for sentence in [*disclaimers, *_wording()["allowed"]]:
            text = re.sub(re.escape(sentence), "", text, flags=re.IGNORECASE)
        texts.append((str(path.relative_to(ROOT)), text))
    for entry in resources.files("neurogrid.rulepacks").iterdir():
        if entry.name.endswith(".yaml"):
            texts.append((entry.name, entry.read_text(encoding="utf-8")))
    return texts


def test_no_conformity_claims() -> None:
    patterns = [p for group in _forbidden().values() for p in group]
    hits = [(name, p.pattern) for name, text in _texts_to_scan() for p in patterns if p.search(text)]
    assert not hits, hits


def test_forbidden_list_catches_examples() -> None:
    patterns = [p for group in _forbidden().values() for p in group]
    for example in (
        "数据符合标准要求",
        "Your data is compliant",
        "Daten sind konform",
        "通过 YY/T 2029",
        "合格",
    ):
        assert any(p.search(example) for p in patterns), example
