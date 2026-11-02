"""The consent records consents.yaml (DM-08, NV-F01, A-30, A-91): parser and validation, the canonical form,
the schema and the effective consent at a reference date."""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import jsonschema
import pytest
import yaml

from neurogrid.kernel.errors import ConfigError
from neurogrid.model import consent as consent_model
from neurogrid.model.consent import (
    CONSENT_USES,
    MAX_ENTRIES,
    MAX_FILE_BYTES,
    ConsentFile,
    ConsentScope,
    ConsentUse,
    dump_consents,
    effective,
    ethics_ref_valid,
    parse_consents,
    subject_id,
)
from neurogrid.vault.store import CONSENTS_TEMPLATE

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "src" / "neurogrid" / "schemas" / "consents.schema.json").read_text("utf-8"))
HEAD = "format_version: 1\nconsents:\n"
ENTRY = "  - subject: sub-01\n    version: 1\n    date: 2026-03-01\n"
USES = "    permitted_uses: [training]\n"


def doc(entry: str = ENTRY, extra: str = USES) -> str:
    """A file with one record: ``entry`` and the lines ``extra``."""
    return HEAD + entry + extra


def changed(old: str, new: str, extra: str = USES) -> str:
    """A file with one record, ENTRY with ``old`` replaced by ``new``."""
    return doc(ENTRY.replace(old, new), extra)


def _entry(**fields: object) -> ConsentScope:
    values: dict[str, object] = {"subject": "sub-01", "version": 1, "date": dt.date(2026, 3, 1)}
    values.update(fields)
    if "permitted_uses" not in values and not values.get("withdrawn"):
        values["permitted_uses"] = ("training",)
    return ConsentScope(**values)  # type: ignore[arg-type]


def _refusal(text: str | bytes) -> ConfigError:
    data = text.encode("utf-8") if isinstance(text, str) else text
    with pytest.raises(ConfigError) as info:
        parse_consents(data)
    return info.value


# --- valid files --------------------------------------------------------------------------------------------


def test_a_valid_file_with_yaml_dates_and_date_text() -> None:
    second = "  - subject: '02'\n    version: 3\n    date: '2026-04-02'\n    withdrawn: true\n"
    extra = "    permitted_uses: [validation, training]\n    ethics_approval_ref: EC-2026-17\n" + second
    first, other = parse_consents(doc(extra=extra).encode("utf-8")).consents
    assert first.subject == "sub-01" and first.date == dt.date(2026, 3, 1)
    assert first.permitted_uses == (ConsentUse.TRAINING, ConsentUse.VALIDATION)  # ConsentUse order
    assert first.ethics_approval_ref == "EC-2026-17" and first.withdrawn is False
    assert other.subject == "sub-02" and other.date == dt.date(2026, 4, 2)  # quoted text, label without sub-
    assert other.withdrawn and other.permitted_uses == ()


def test_a_bom_and_the_empty_template_are_accepted() -> None:
    assert parse_consents(b"\xef\xbb\xbf" + CONSENTS_TEMPLATE).consents == []
    assert parse_consents(CONSENTS_TEMPLATE) == ConsentFile(consents=[])


@pytest.mark.parametrize(("given", "stored"), [("01", "sub-01"), ("sub-01", "sub-01"), ("A1b", "sub-A1b")])
def test_subjects_are_stored_with_sub(given: str, stored: str) -> None:
    assert subject_id(given) == stored
    assert _entry(subject=given).subject == stored


@pytest.mark.parametrize(
    "given", ["Zhang San", "sub-01/..", "..", "张三", "sub-", "", "sub-01\n", "x" * 65, "sub_01", "sub-0-1"]
)
def test_subjects_that_are_no_pseudonymous_label_are_refused(given: str) -> None:
    assert subject_id(given) is None
    with pytest.raises(ValueError):
        _entry(subject=given)


def test_the_label_may_be_64_characters_long() -> None:
    assert subject_id("a" * 64) == "sub-" + "a" * 64


# --- refusals: the field, never the value (C2, A-51) --------------------------------------------------------

CONTROL_REF = '    ethics_approval_ref: "EC\\u0007"\n'  # YAML escape: the reader sees a control character
REFUSALS = {
    "timestamp": (changed("2026-03-01", "2026-03-01 10:00:00"), "consents.0.date"),
    "impossible date as text": (changed("2026-03-01", "'2026-02-30'"), "consents.0.date"),
    "basic date format": (changed("2026-03-01", "'20260301'"), "consents.0.date"),
    "unknown key": (doc(extra=USES + "    Zhang San: 1\n"), "consents.0.?"),
    "unknown top-level key": ("format_version: 1\nconsents: []\nZhang San: x\n", "?"),
    "format_version missing": ("consents: []\n", "format_version"),
    "format_version 2": ("format_version: 2\nconsents: []\n", "format_version"),
    "format_version true": ("format_version: true\nconsents: []\n", "format_version"),
    "consents missing": ("format_version: 1\n", "consents"),
    "version 0": (changed("version: 1", "version: 0"), "consents.0.version"),
    "version true": (changed("version: 1", "version: true"), "consents.0.version"),
    "version as text": (changed("version: 1", "version: '2'"), "consents.0.version"),
    "version too high": (changed("version: 1", "version: 1000001"), "consents.0.version"),
    "withdrawn with uses": (doc(extra=USES + "    withdrawn: true\n"), "consents.0"),
    "no uses without withdrawal": (doc(extra=""), "consents.0"),
    "unknown use": (doc(extra="    permitted_uses: [research]\n"), "consents.0.permitted_uses.0"),
    "duplicate use": (doc(extra="    permitted_uses: [training, training]\n"), "consents.0.permitted_uses"),
    "subject with a space": (changed("sub-01", "'Zhang San'"), "consents.0.subject"),
    "non-ASCII subject": (changed("sub-01", "张三"), "consents.0.subject"),
    "ethics ref too long": (
        doc(extra=USES + f"    ethics_approval_ref: {'E' * 121}\n"),
        "consents.0.ethics_approval_ref",
    ),
    "ethics ref with a control character": (doc(extra=USES + CONTROL_REF), "consents.0.ethics_approval_ref"),
    "blank ethics ref": (
        doc(extra=USES + "    ethics_approval_ref: '   '\n"),
        "consents.0.ethics_approval_ref",
    ),
    "a list instead of a mapping": ("- 1\n", "consents.yaml"),
}


@pytest.mark.parametrize(("text", "field"), REFUSALS.values(), ids=list(REFUSALS))
def test_invalid_content_names_the_field(text: str, field: str) -> None:
    error = _refusal(text)
    assert error.message_key == "consents.invalid"
    assert error.params["field"] == field
    assert "Zhang" not in str(error.params) and "张三" not in str(error.params)


def test_records_contradicting_each_other_are_refused_at_the_later_record() -> None:
    two = "  - subject: sub-01\n    version: {v}\n    date: {d}\n    permitted_uses: [training]\n"
    duplicate = HEAD + two.format(v=1, d="2026-01-01") + two.format(v=1, d="2026-02-01")
    error = _refusal(duplicate)
    assert error.params == {"field": "consents.1.version", "problem": "duplicate_version"}
    decreasing = HEAD + two.format(v=2, d="2026-01-01") + two.format(v=1, d="2026-02-01")
    error = _refusal(decreasing)
    assert error.params == {"field": "consents.0.date", "problem": "date_order"}  # version 2 dated earlier
    same_day = HEAD + two.format(v=1, d="2026-01-01") + two.format(v=2, d="2026-01-01")
    assert len(parse_consents(same_day.encode("utf-8")).consents) == 2  # equal dates do not decrease


def test_yaml_aliases_and_duplicate_keys_are_refused_without_value_text() -> None:
    assert _refusal(HEAD + "  - &a {subject: sub-01}\n  - *a\n").message_key == "yaml.alias"
    duplicate = _refusal(doc(extra="    version: 2\n" + USES))
    assert duplicate.message_key == "yaml.duplicate_key" and duplicate.params["name"] == "version"
    unknown = _refusal(doc(extra="    Zhang San: 1\n    Zhang San: 2\n"))
    assert unknown.message_key == "yaml.duplicate_key" and unknown.params["name"] == "?"


def test_size_limits_and_encoding(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _refusal(b"#" * (MAX_FILE_BYTES + 1)).message_key == "consents.too_large"
    latin = "format_version: 1\nconsents: [] # é\n".encode("latin-1")
    assert _refusal(latin).message_key == "consents.encoding"
    record = {"subject": "sub-1", "version": 1, "date": dt.date(2026, 1, 1), "permitted_uses": ["training"]}
    many = [{**record, "subject": f"sub-{n}"} for n in range(MAX_ENTRIES + 1)]
    # the YAML of 20 001 records takes PyYAML half a minute: the parsed document is given directly
    monkeypatch.setattr(consent_model, "_yaml", lambda _text: {"format_version": 1, "consents": many})
    assert _refusal(b"format_version: 1\n").params == {"field": "consents", "problem": "too_long"}
    monkeypatch.setattr(consent_model, "_yaml", lambda _text: {"format_version": 1, "consents": many[:-1]})
    assert len(parse_consents(b"format_version: 1\n").consents) == MAX_ENTRIES


def test_ethics_references_must_be_printable_text() -> None:
    assert ethics_ref_valid("EC-2026-17") and ethics_ref_valid("伦理审批 2026 第 17 号")
    for text in ("", "   ", "E" * 121, "a b", "a​b", "a﻿b", "a\x85b", "ab"):
        assert not ethics_ref_valid(text), repr(text)


# --- the canonical form -------------------------------------------------------------------------------------


def test_the_empty_file_is_the_template_of_vault_init() -> None:
    assert dump_consents(ConsentFile(consents=[])) == CONSENTS_TEMPLATE


def test_the_canonical_dump() -> None:
    quoted = 'a "b" \\ 伦'
    records = [
        _entry(
            subject="sub-02", version=2, permitted_uses=("validation", "training"), ethics_approval_ref=quoted
        ),
        _entry(subject="sub-01", version=1, withdrawn=True, permitted_uses=()),
        _entry(subject="sub-02", version=1, permitted_uses=("sharing",)),
    ]
    data = dump_consents(ConsentFile(consents=records))
    text = data.decode("utf-8")
    assert not data.startswith(b"\xef\xbb\xbf") and b"\r" not in data and text.endswith("\n")
    assert text.startswith("# NeuroGrid consent records")
    body = text.split("format_version: 1\n", 1)[1]
    assert body == (
        "consents:\n"
        "  - subject: sub-01\n    version: 1\n    date: 2026-03-01\n"
        "    permitted_uses: []\n    withdrawn: true\n"
        "  - subject: sub-02\n    version: 1\n    date: 2026-03-01\n"
        "    permitted_uses: [sharing]\n    withdrawn: false\n"
        "  - subject: sub-02\n    version: 2\n    date: 2026-03-01\n"
        "    permitted_uses: [training, validation]\n"
        '    withdrawn: false\n    ethics_approval_ref: "a \\"b\\" \\\\ 伦"\n'
    )


@pytest.mark.parametrize(
    "ref",
    [None, "EC-2026-17", "12:30 # not a comment", "'quoted'", '"double"', "[1, 2]", "yes", "~", "伦理 1"],
)
def test_parse_of_the_dump_gives_the_records_back(ref: str | None) -> None:
    records = [
        _entry(subject="sub-01", version=1, ethics_approval_ref=ref),
        _entry(subject="sub-01", version=2, withdrawn=True, permitted_uses=(), date=dt.date(2026, 6, 1)),
        _entry(subject="sub-A7", version=1, permitted_uses=tuple(CONSENT_USES)),
    ]
    original = ConsentFile(consents=records)  # in canonical order already
    assert parse_consents(dump_consents(original)) == original
    assert dump_consents(parse_consents(dump_consents(original))) == dump_consents(original)


def test_the_hash_is_the_same_for_every_spelling_of_the_same_records() -> None:
    second = ENTRY.replace("version: 1", "version: 2") + "    withdrawn: true\n"
    canonical = parse_consents(
        doc(extra="    permitted_uses: [training, validation]\n" + second).encode("utf-8")
    )
    reformatted = parse_consents(
        b"# notes\r\nconsents:\r\n  - {withdrawn: true, date: '2026-03-01', version: 2, subject: '01'}\r\n"
        b"  - permitted_uses: [validation, training]\r\n    subject: sub-01\r\n    version: 1\r\n"
        b"    date: 2026-03-01\r\n    withdrawn: false\r\nformat_version: 1\r\n"
    )
    assert canonical.canonical_sha256() == reformatted.canonical_sha256()
    other = parse_consents(doc().encode("utf-8"))
    assert other.canonical_sha256() != canonical.canonical_sha256()


# --- the schema accepts what the reader accepts (apart from rules across records) --------------------------

AGREEMENT = {
    "valid": (doc(), True),
    "label without sub-": (changed("sub-01", "'01'"), True),
    "date as text": (changed("2026-03-01", "'2026-03-01'"), True),
    "withdrawal": (doc(extra="    withdrawn: true\n"), True),
    "withdrawal with an empty list": (doc(extra="    permitted_uses: []\n    withdrawn: true\n"), True),
    "empty": ("format_version: 1\nconsents: []\n", True),
    "withdrawn with uses": (doc(extra=USES + "    withdrawn: true\n"), False),
    "no uses": (doc(extra=""), False),
    "empty uses": (doc(extra="    permitted_uses: []\n"), False),
    "duplicate use": (doc(extra="    permitted_uses: [training, training]\n"), False),
    "unknown use": (doc(extra="    permitted_uses: [research]\n"), False),
    "bad subject": (changed("sub-01", "'a b'"), False),
    "version 0": (changed("version: 1", "version: 0"), False),
    "blank ethics ref": (doc(extra=USES + "    ethics_approval_ref: ' '\n"), False),
    "unknown key": (doc(extra=USES + "    note: x\n"), False),
    "format_version 2": ("format_version: 2\nconsents: []\n", False),
    "no format_version": ("consents: []\n", False),
    "no consents": ("format_version: 1\n", False),
}


class _Yaml12Loader(yaml.SafeLoader):
    """Dates stay text, as a YAML 1.2 tool reads them; the schema's format "date" checks them."""


_Yaml12Loader.yaml_implicit_resolvers = {
    key: [(tag, regexp) for tag, regexp in resolvers if tag != "tag:yaml.org,2002:timestamp"]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def _reader_accepts(text: str) -> bool:
    try:
        parse_consents(text.encode("utf-8"))
    except ConfigError:
        return False
    return True


def _schema_accepts(text: str) -> bool:
    data = json.loads(json.dumps(yaml.load(text, Loader=_Yaml12Loader)))  # noqa: S506 - the strict SafeLoader
    validator = jsonschema.Draft202012Validator(SCHEMA, format_checker=jsonschema.FormatChecker())
    return validator.is_valid(data)


@pytest.mark.parametrize(("text", "valid"), AGREEMENT.values(), ids=list(AGREEMENT))
def test_schema_and_reader_accept_the_same_documents(text: str, valid: bool) -> None:
    assert (_reader_accepts(text), _schema_accepts(text)) == (valid, valid)


# --- the effective consent (A-30) ---------------------------------------------------------------------------

AS_OF = dt.date(2026, 11, 20)


def test_the_highest_version_dated_on_or_before_the_reference_date_counts() -> None:
    records = [
        _entry(version=1, date=dt.date(2026, 1, 1), permitted_uses=("training", "sharing")),
        _entry(version=2, date=dt.date(2026, 5, 1), permitted_uses=("training",)),  # partial withdrawal
        _entry(version=3, date=dt.date(2027, 1, 1), permitted_uses=("training", "commercial")),  # future
    ]
    consent = effective(records, AS_OF)
    assert consent.state == "valid" and consent.version == 2
    assert consent.covers(ConsentUse.TRAINING) and not consent.covers(ConsentUse.SHARING)
    assert not consent.covers(ConsentUse.COMMERCIAL)
    assert effective(records, dt.date(2026, 4, 30)).covers(
        ConsentUse.SHARING
    )  # before the partial withdrawal
    assert effective(records, dt.date(2027, 1, 1)).version == 3  # a record dated on the reference date counts


def test_withdrawal_renewal_none_and_future_only() -> None:
    withdrawn = [
        _entry(version=1, date=dt.date(2026, 1, 1)),
        _entry(version=2, date=dt.date(2026, 6, 1), withdrawn=True, permitted_uses=()),
    ]
    assert effective(withdrawn, AS_OF).state == "withdrawn" and effective(withdrawn, AS_OF).version == 2
    assert not effective(withdrawn, AS_OF).covers(ConsentUse.TRAINING)
    assert effective(withdrawn, dt.date(2026, 5, 31)).covers(ConsentUse.TRAINING)
    renewed = [*withdrawn, _entry(version=3, date=dt.date(2026, 9, 1))]
    assert effective(renewed, AS_OF).state == "valid" and effective(renewed, AS_OF).version == 3
    assert effective([], AS_OF).state == "none" and effective([], AS_OF).version is None
    future = effective([_entry(version=1, date=dt.date(2027, 1, 1))], AS_OF)
    assert future.state == "future_only" and future.version is None


def test_consent_uses_are_the_five_uses_of_the_data_model() -> None:
    assert CONSENT_USES == ("training", "validation", "publication", "sharing", "commercial")
    assert re.fullmatch(SCHEMA["$defs"]["ConsentScope"]["properties"]["subject"]["pattern"], "01")
