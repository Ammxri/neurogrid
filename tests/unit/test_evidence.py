"""evidence.yaml parsing and the document checker (NG-F12, RP-05, A-15, A-52, A-53, A-83)."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import date, datetime
from importlib import resources
from pathlib import Path

import jsonschema
import pytest
import yaml

from conftest import dir_link  # type: ignore[import-not-found]
from neurogrid.kernel.errors import ConfigError
from neurogrid.kernel.evidence import (
    DocumentCheck,
    EvidenceFile,
    EvidenceItem,
    EvidenceState,
    file_document_checker,
    no_document_checker,
    parse_evidence,
)

EXAMPLE = """\
format_version: 1
evidence:
  GXDSL008-ACC-001:
    status: provided
    document: .neurogrid/evidence/it-security-sop-12.pdf
    sha256: 3F0A6C9D2B1E4F5A6B7C8D9E0F1A2B3C4D5E6F708192A3B4C5D6E7F8091A2B3C
    reviewer: QA lead
    date: 2026-11-02
    comment: AES-256 at rest, role concept v2
  SITE-ACC-002:
    status: not_applicable
    justification: no data at rest on this site
  SITE-ACC-003:
    status: partial
"""


def _parse(text: str) -> dict[str, EvidenceItem]:
    return dict(parse_evidence(text.encode("utf-8")).evidence)


def test_example_is_parsed_and_the_hash_normalised() -> None:
    entries = _parse(EXAMPLE)
    item = entries["GXDSL008-ACC-001"]
    assert item.status is EvidenceState.PROVIDED
    assert item.document == ".neurogrid/evidence/it-security-sop-12.pdf"
    assert item.sha256 == "3f0a6c9d2b1e4f5a6b7c8d9e0f1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c"
    assert item.date == date(2026, 11, 2) and item.reviewer == "QA lead"
    assert entries["SITE-ACC-002"].status is EvidenceState.NOT_APPLICABLE
    assert entries["SITE-ACC-003"].document is None  # partial may lack a document


def test_bom_backslashes_and_empty_section_are_accepted() -> None:
    """PowerShell 5.1 writes a BOM; Windows users write backslashes. Both give the same entry."""
    parsed = parse_evidence(
        b"\xef\xbb\xbfformat_version: 1\nevidence:\n  X-1:\n"
        b'    status: provided\n    document: "a\\\\b.pdf"\n'
    )
    assert parsed.evidence["X-1"].document == "a/b.pdf"  # POSIX form on every platform
    assert parse_evidence(b"format_version: 1\nevidence:\n").evidence == {}
    assert parse_evidence(b"format_version: 1\n").evidence == {}


@pytest.mark.parametrize(
    ("text", "key", "field"),
    [
        (
            "format_version: 1\nevidence:\n  X-1: {status: open}\n  X-1: {status: open}\n",
            "yaml.duplicate_key",
            None,
        ),
        ("a: &x 1\nformat_version: *x\n", "yaml.alias", None),
        (
            "format_version: 1\nevidence:\n  X-1: {status: open, owner: me}\n",
            "evidence.invalid",
            "evidence.X-1.owner",
        ),
        ("format_version: 1\nevidence:\n  X-1: {status: done}\n", "evidence.invalid", "evidence.X-1.status"),
        (
            "format_version: 1\nevidence:\n  X-1: {status: not_applicable}\n",
            "evidence.invalid",
            "evidence.X-1",
        ),
        (
            "format_version: 1\nevidence:\n  X-1: {status: not_applicable, justification: '  '}\n",
            "evidence.invalid",
            "evidence.X-1",
        ),
        ("format_version: 1\nevidence:\n  X-1: {status: provided}\n", "evidence.invalid", "evidence.X-1"),
        ("format_version: 1\nevidence:\n  Zhang San: {status: open}\n", "evidence.invalid", "evidence.#1"),
        (
            "format_version: 1\nevidence:\n  X-1: {status: open, date: '02.11.2026'}\n",
            "evidence.invalid",
            "evidence.X-1.date",
        ),
        ("format_version: true\nevidence: {}\n", "evidence.invalid", "format_version"),
        ("format_version: 2\nevidence: {}\n", "evidence.invalid", "format_version"),
        ("evidence: {}\n", "evidence.invalid", "format_version"),
        ("format_version: 1\nevidence: []\n", "evidence.invalid", "evidence"),
        ("format_version: 1\nevidence:\n  X-1: {status: open, sha256: abc}\n", "evidence.invalid", None),
        ("format_version: 1\nevidence:\n  X-1: {status: open, reviewer: 7}\n", "evidence.invalid", None),
        ("- format_version\n", "evidence.not_mapping", None),
        ("", "evidence.not_mapping", None),
    ],
)
def test_invalid_files_name_the_field(text: str, key: str, field: str | None) -> None:
    with pytest.raises(ConfigError) as info:
        parse_evidence(text.encode("utf-8"))
    assert info.value.message_key == key
    if field is not None:
        assert info.value.params["field"] == field


def test_problem_names_the_missing_document_and_justification() -> None:
    with pytest.raises(ConfigError) as info:
        parse_evidence(b"format_version: 1\nevidence:\n  X-1: {status: provided}\n")
    assert info.value.params["problem"] == "document_required"
    with pytest.raises(ConfigError) as info:
        parse_evidence(b"format_version: 1\nevidence:\n  X-1: {status: not_applicable}\n")
    assert info.value.params["problem"] == "justification_required"


def test_value_text_is_never_echoed() -> None:
    """C2: a malformed key or an unknown field made of free text is named by position or '?', not by its
    text."""
    with pytest.raises(ConfigError) as info:
        parse_evidence(b"format_version: 1\nevidence:\n  X-1: {status: open, 'Zhang San': 1}\n")
    assert "Zhang" not in str(info.value.params)
    with pytest.raises(ConfigError) as info:
        parse_evidence("format_version: 1\nevidence:\n  张三: {status: open}\n".encode())
    assert "张三" not in str(info.value.params)


@pytest.mark.parametrize(
    "document", ["../outside.pdf", "C:/x.pdf", "\\\\\\\\srv\\\\x.pdf", "a:b.pdf", "https://x/y"]
)
def test_unsafe_document_paths_are_refused(document: str) -> None:
    text = f'format_version: 1\nevidence:\n  X-1:\n    status: provided\n    document: "{document}"\n'
    with pytest.raises(ConfigError) as info:
        parse_evidence(text.encode("utf-8"))
    assert info.value.message_key == "evidence.unsafe_path" and info.value.params == {"rule": "X-1"}


def test_size_and_encoding_limits() -> None:
    with pytest.raises(ConfigError) as info:
        parse_evidence(b"format_version: 1\ncomment: \xff\xfe\n")
    assert info.value.message_key == "evidence.encoding"
    with pytest.raises(ConfigError) as info:
        parse_evidence(b"format_version: 1\n#" + b"x" * 2_100_000 + b"\n")
    assert info.value.message_key == "yaml.too_large"
    many = "".join(f"  R-{n}: {{status: open}}\n" for n in range(10_001))
    with pytest.raises(ConfigError) as info:
        parse_evidence(f"format_version: 1\nevidence:\n{many}".encode())
    assert info.value.message_key == "evidence.invalid" and info.value.params["problem"] == "too_long"


def test_item_model_is_strict() -> None:
    """Strict like neurogrid.toml (A-53); a date may be a YAML date or the text 'YYYY-MM-DD', which the
    schema's format 'date' describes (A-83, review P4 EVI35); other text, numbers and times are refused."""
    assert EvidenceItem.model_validate({"status": "open", "date": "2026-11-02"}).date == date(2026, 11, 2)
    assert EvidenceItem.model_validate({"status": "open", "date": date(2026, 11, 2)}).date == date(
        2026, 11, 2
    )
    for value in ("02.11.2026", "20261102", "2026-11-02T10:00:00", "2026-02-30", "２０２６-11-02", 20261102):
        with pytest.raises(ValueError):
            EvidenceItem.model_validate({"status": "open", "date": value})
    with pytest.raises(ValueError):
        EvidenceItem.model_validate({"status": "open", "date": datetime(2026, 11, 2, 10, 0)})
    with pytest.raises(ValueError):
        EvidenceItem.model_validate({"status": "open", "reviewer": 7})
    assert EvidenceItem.model_validate({"status": "open"}).status is EvidenceState.OPEN
    with pytest.raises(ValueError):
        EvidenceFile.model_validate({"format_version": True})
    assert EvidenceFile.model_validate({"format_version": 1, "evidence": None}).evidence == {}


# --- the published schema accepts what the reader accepts (A-83, review P4 EVI35) ------------------------


class _Yaml12Loader(yaml.SafeLoader):
    """How an editor's YAML 1.2 language server reads evidence.yaml before checking it against the schema:
    without the YAML 1.1 timestamps, an unquoted date stays text."""


_Yaml12Loader.yaml_implicit_resolvers = {
    first: [(tag, regexp) for tag, regexp in resolvers if tag != "tag:yaml.org,2002:timestamp"]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
SCHEMA = json.loads(  # the schema published with the code under test (gen_schemas --check pins the copy)
    resources.files("neurogrid").joinpath("schemas", "evidence.schema.json").read_text(encoding="utf-8")
)
SHA = "3f0a6c9d2b1e4f5a6b7c8d9e0f1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c"
ENTRY = "format_version: 1\nevidence:\n  GXDSL008-ACC-001:\n"
AGREEMENT = {
    "provided": (ENTRY + "    status: provided\n    document: sop.pdf\n", True),
    "upper-case sha256": (
        ENTRY + f"    status: provided\n    document: a.pdf\n    sha256: {SHA.upper()}\n",
        True,
    ),
    "short sha256": (ENTRY + "    status: open\n    sha256: abc\n", False),
    "unquoted date": (ENTRY + "    status: open\n    date: 2026-10-01\n", True),
    "quoted date": (ENTRY + '    status: open\n    date: "2026-10-01"\n', True),
    "date with a time": (ENTRY + "    status: open\n    date: 2026-10-01 10:00:00\n", False),
    "date as other text": (ENTRY + '    status: open\n    date: "01.10.2026"\n', False),
    "impossible date": (ENTRY + '    status: open\n    date: "2026-02-30"\n', False),
    "format_version true": ("format_version: true\nevidence: {}\n", False),
    "format_version 1.0": ("format_version: 1.0\nevidence: {}\n", True),
    "format_version 2": ("format_version: 2\nevidence: {}\n", False),
    "format_version missing": ("evidence: {}\n", False),
    "empty section": ("format_version: 1\nevidence:\n", True),
    "no section": ("format_version: 1\n", True),
    "section as a list": ("format_version: 1\nevidence: []\n", False),
    "key that is no rule ID": ("format_version: 1\nevidence:\n  lowercase-key: {status: open}\n", False),
    "key too long": (f"format_version: 1\nevidence:\n  A-{'1' * 63}: {{status: open}}\n", False),
    "provided without document": (ENTRY + "    status: provided\n", False),
    "not_applicable without justification": (ENTRY + "    status: not_applicable\n", False),
    "not_applicable with a blank justification": (
        ENTRY + "    status: not_applicable\n    justification: '   '\n",
        False,
    ),
    "not_applicable with a justification": (
        ENTRY + "    status: not_applicable\n    justification: no data at rest\n",
        True,
    ),
    "partial without document": (ENTRY + "    status: partial\n", True),
    "unknown status": (ENTRY + "    status: done\n", False),
    "unknown field": (ENTRY + "    status: open\n    owner: QA\n", False),
    "reviewer as a number": (ENTRY + "    status: open\n    reviewer: 7\n", False),
    "unknown top-level key": ("format_version: 1\nnotes: x\n", False),
}


def _reader_accepts(text: str) -> bool:
    try:
        parse_evidence(text.encode("utf-8"))
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


# --- document checker ---------------------------------------------------------------------------


def _item(document: str | None, sha256: str | None = None) -> EvidenceItem:
    if document is None:
        return EvidenceItem(status=EvidenceState.PARTIAL)
    return EvidenceItem(status=EvidenceState.PROVIDED, document=document, sha256=sha256)


def test_document_checks(tmp_path: Path) -> None:
    folder = tmp_path / ".neurogrid" / "evidence"
    folder.mkdir(parents=True)
    content = b"standard operating procedure, version 12\n"
    (folder / "sop.pdf").write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    check = file_document_checker(tmp_path)
    assert check(_item(None)).check is DocumentCheck.NO_DOCUMENT
    ok = check(_item(".neurogrid/evidence/sop.pdf"))
    assert ok.check is DocumentCheck.OK and ok.sha256 == digest  # same as sha256sum
    assert check(_item(".neurogrid/evidence/sop.pdf", digest.upper())).check is DocumentCheck.OK
    changed = check(_item(".neurogrid/evidence/sop.pdf", "0" * 64))
    assert changed.check is DocumentCheck.HASH_MISMATCH and changed.sha256 == digest
    assert check(_item(".neurogrid/evidence/missing.pdf")).check is DocumentCheck.DOCUMENT_MISSING
    assert check(_item(".neurogrid/evidence")).check is DocumentCheck.DOCUMENT_MISSING  # a folder


def test_document_case_must_match_on_every_platform(tmp_path: Path) -> None:
    (tmp_path / "SOP.pdf").write_bytes(b"x")
    (tmp_path / "Docs").mkdir()
    (tmp_path / "Docs" / "a.pdf").write_bytes(b"y")
    check = file_document_checker(tmp_path)
    assert check(_item("sop.pdf")).check is DocumentCheck.DOCUMENT_MISSING
    assert check(_item("docs/a.pdf")).check is DocumentCheck.DOCUMENT_MISSING
    assert check(_item("Docs/a.pdf")).check is DocumentCheck.OK


def test_document_behind_a_link_is_not_followed(tmp_path: Path) -> None:
    target = tmp_path / "elsewhere"
    target.mkdir()
    (target / "sop.pdf").write_bytes(b"secret")
    root = tmp_path / "dataset"
    root.mkdir()
    dir_link(root / "evidence", target)
    assert file_document_checker(root)(_item("evidence/sop.pdf")).check is DocumentCheck.DOCUMENT_LINK


@pytest.mark.skipif(sys.platform == "win32", reason="file symlinks need extra rights on Windows")
def test_linked_document_file_is_not_followed(tmp_path: Path) -> None:
    (tmp_path / "real.pdf").write_bytes(b"x")
    (tmp_path / "link.pdf").symlink_to(tmp_path / "real.pdf")
    assert file_document_checker(tmp_path)(_item("link.pdf")).check is DocumentCheck.DOCUMENT_LINK


def test_missing_root_and_default_checker(tmp_path: Path) -> None:
    assert file_document_checker(tmp_path / "gone")(_item("a.pdf")).check is DocumentCheck.DOCUMENT_MISSING
    assert no_document_checker(_item(None)).check is DocumentCheck.NO_DOCUMENT
    assert no_document_checker(_item("a.pdf")).check is DocumentCheck.DOCUMENT_MISSING


def test_documents_are_hashed_once_per_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from neurogrid.kernel import evidence

    (tmp_path / "a.pdf").write_bytes(b"x")
    calls: list[Path] = []
    original = evidence.sha256_file
    monkeypatch.setattr(evidence, "sha256_file", lambda path: calls.append(path) or original(path))
    check = file_document_checker(tmp_path)
    for _ in range(3):
        assert check(_item("a.pdf")).check is DocumentCheck.OK
    assert len(calls) == 1
