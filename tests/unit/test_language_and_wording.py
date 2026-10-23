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


def test_notice_keys_used_in_code_exist() -> None:
    """C7 (critic G3): Notice(message_key=...) keys, literal or built from a prefix, exist in every
    language."""
    loaded = tables()
    keys: set[str] = set()
    prefixes: set[str] = set()
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        keys.update(re.findall(r"""message_key\s*=\s*['"]([a-z_]+(?:\.[a-z_0-9]+)+)['"]""", text))
        prefixes.update(re.findall(r"""message_key\s*=\s*f['"]([a-z_]+(?:\.[a-z_0-9]+)*\.)\{""", text))
    assert {"notice.exception_unknown_rule", "notice.evidence_unused"} <= keys  # the pattern still finds them
    assert "notice.evidence_document." in prefixes
    for lang in LANGUAGES:
        assert not sorted(k for k in keys if k not in loaded[lang]), lang
        assert not sorted(p for p in prefixes if not any(k.startswith(p) for k in loaded[lang])), lang


def test_every_registered_check_has_a_title_in_every_language() -> None:
    """C7: findings carry message_key check.<check id> (kernel/engine.py); every registry check needs it."""
    from neurogrid.checks.registry import REGISTRY

    for lang in LANGUAGES:
        missing = sorted(check_id for check_id in REGISTRY if f"check.{check_id}" not in tables()[lang])
        assert not missing, f"{lang}: {missing}"


def _families() -> list[tuple[str, list[str]]]:
    """Key families built at runtime from enum values (C7): prefix -> values that must all have a text."""
    from neurogrid.kernel.evidence import DocumentCheck, EvidenceState
    from neurogrid.kernel.findings import Light, Phase, Severity, SourceStatus, Status, Verification

    not_ok = [check.value for check in DocumentCheck if check is not DocumentCheck.OK]
    open_states = [state.value for state in EvidenceState if state is not EvidenceState.PROVIDED]
    return [
        ("status", [s.value for s in Status]),
        ("phase", [p.value for p in Phase]),
        ("light", [light.value for light in Light]),
        ("severity", [s.value for s in Severity]),
        ("source_status", [s.value for s in SourceStatus]),  # report cover
        ("verification", [v.value for v in Verification]),  # report section 5
        ("report.document_check", [c.value for c in DocumentCheck]),  # report section 5
        ("reason.evidence", [*not_ok, *open_states, "missing"]),  # engine: f"evidence.{...}"
        ("notice.evidence_document", not_ok),  # engine: manual 'provided' with a document problem
    ]


@pytest.mark.parametrize(("prefix", "values"), _families(), ids=[prefix for prefix, _ in _families()])
def test_key_families_built_at_runtime_are_complete(prefix: str, values: list[str]) -> None:
    for lang in LANGUAGES:
        missing = sorted(value for value in values if f"{prefix}.{value}" not in tables()[lang])
        assert not missing, f"{lang} {prefix}: {missing}"


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


# --- ARC-05: no statement about patients; A-57: findings name no law articles (P5) -------------------------

USER_DOC_SUFFIXES = {".md", ".txt", ".ps1", ".sh", ".yml", ".yaml", ".html"}


def _statements() -> dict[str, object]:
    data = load_yaml((SRC / "report" / "wording" / "statements.yaml").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _statement_patterns(group: str) -> list[re.Pattern[str]]:
    languages = _statements()[group]
    assert isinstance(languages, dict) and set(languages) == set(LANGUAGES)
    return [re.compile(pattern) for patterns in languages.values() for pattern in patterns]


def _without_allowed(text: str) -> str:
    allowed = _statements()["allowed"]
    assert isinstance(allowed, list)
    for phrase in allowed:
        text = re.sub(re.escape(phrase), "", text, flags=re.IGNORECASE)
    return text


def _own_texts() -> list[tuple[str, str]]:
    """NeuroGrid's own texts of the report and the console: language tables, rule packs (titles, sources),
    validator texts and the report templates (A-57 scope; never dataset-derived strings)."""
    from neurogrid.report.texts import validator_codes

    texts = [(f"{lang}:{key}", value) for lang, table in tables().items() for key, value in table.items()]
    for entry in resources.files("neurogrid.rulepacks").iterdir():
        if entry.name.endswith(".yaml"):
            pack = load_yaml(entry.read_text(encoding="utf-8"))
            assert isinstance(pack, dict)
            texts.append((f"{entry.name}:source", str(pack.get("source", ""))))
            for rule in pack["rules"]:
                texts += [(f"{entry.name}:{rule['id']}", str(rule[f"title_{lang}"])) for lang in ("zh", "en")]
    for code, entry in validator_codes().items():
        texts += [(f"validator:{code}:{lang}", entry[lang]) for lang in LANGUAGES]
    for path in sorted((SRC / "report" / "templates").iterdir()):
        texts.append((str(path.relative_to(ROOT)), path.read_text(encoding="utf-8")))
    return texts


def _user_texts() -> list[tuple[str, str]]:
    """Every user-facing text (B1 wording test): NeuroGrid's own texts plus the user documentation (docs/
    without the internal docs/umsetzung, which is not part of the site, A-28), the site configuration, the
    README files and the messages of the install scripts, where they exist."""
    internal = ROOT / "docs" / "umsetzung"
    paths = [p for p in (ROOT / "README.md", ROOT / "mkdocs.yml") if p.is_file()]
    for folder in (ROOT / "docs", ROOT / "packaging"):
        paths += sorted(
            p
            for p in folder.rglob("*")
            if p.is_file() and p.suffix in USER_DOC_SUFFIXES and not p.is_relative_to(internal)
        )
    paths += [p for p in (ROOT / "tools" / "install_pdf_browser.py",) if p.is_file()]
    return _own_texts() + [(str(p.relative_to(ROOT)), p.read_text(encoding="utf-8")) for p in paths]


def test_report_texts_make_no_patient_statements() -> None:
    """ARC-05: no statement about patients, diagnoses or clinical matters in any user-facing text; the scope
    note's negation is the only allowed phrase, header field names are excluded by the patterns."""
    patterns = _statement_patterns("patient")
    texts = [(name, _without_allowed(text)) for name, text in _user_texts()]
    hits = [(name, p.pattern) for name, text in texts for p in patterns if p.search(text)]
    assert not hits, hits


def test_findings_name_no_law_articles() -> None:
    """A-57: findings (rule titles, reasons, issue texts, validator texts, report texts) name no law
    articles."""
    patterns = _statement_patterns("law_article")
    hits = [(name, p.pattern) for name, text in _own_texts() for p in patterns if p.search(text)]
    assert not hits, hits


@pytest.mark.parametrize(
    ("group", "text", "caught"),
    [
        ("patient", "The patient shows artefacts.", True),
        ("patient", "Patients with epilepsy", True),
        ("patient", "the diagnosis of the subject", True),
        ("patient", "clinical relevance", True),
        ("patient", "患者的诊断", True),
        ("patient", "临床意义", True),
        ("patient", "Die Patientin", True),
        ("patient", "Diagnose der Probanden", True),
        ("patient", "klinisch relevant", True),
        ("patient", "the EDF patient field", False),
        ("patient", "Patientenfeld", False),
        ("patient", "Patientendaten werden gelesen", True),
        ("patient", "Patient 12", True),
        ("patient", "diagnosis_code (never in output)", False),
        ("patient", "diagnose_code", False),
        ("patient", "This report makes no statement about patients.", False),
        ("patient", "本报告不对患者作任何陈述。", False),
        ("patient", "Der Bericht trifft keine Aussage über Patienten.", False),
        ("law_article", "violates Art. 28 PIPL", True),
        ("law_article", "see article 5", True),
        ("law_article", "违反第二十八条", True),
        ("law_article", "nach Artikel 28", True),
        ("law_article", "BIDS 1.11.1", False),
        ("law_article", "M07 line-noise ratio", False),
    ],
)
def test_statement_lists_catch_examples(group: str, text: str, caught: bool) -> None:
    patterns = _statement_patterns(group)
    assert any(p.search(_without_allowed(text)) for p in patterns) is caught


def test_scope_note_is_the_allowed_negation_in_every_language() -> None:
    """The allowed phrases are exactly the negations in the scope note (ARC-05), so nothing else is exempt."""
    allowed = _statements()["allowed"]
    assert isinstance(allowed, list)
    for lang in LANGUAGES:
        note = tables()[lang]["report.text.scope_note"]
        assert sum(phrase in note for phrase in allowed) == 1, lang
        assert not any(p.search(_without_allowed(note)) for p in _statement_patterns("patient")), lang
