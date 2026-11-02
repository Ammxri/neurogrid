"""The consent records in the vault (NV-F01, NV-F02, CLI-08, D-10 b; A-30, A-91; p6 decisions 2, 3): reading
for check, the consents.tsv import and ``vault consent add`` under the vault lock."""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import pytest
from vault_processes import lock_held  # type: ignore[import-not-found]

from conftest import dir_link  # type: ignore[import-not-found]
from neurogrid.kernel.errors import ConfigError, InputError, UnsafePathError
from neurogrid.model.consent import ConsentFile, ConsentScope, dump_consents, parse_consents
from neurogrid.vault import consents, ledger, store
from neurogrid.vault.consents import (
    ImportedRecord,
    add_consents,
    load_for_check,
    parse_consents_tsv,
    read_consents_tsv,
)
from neurogrid.vault.lock import VaultLocked

TODAY = dt.datetime(2026, 11, 20, 9, 30, tzinfo=dt.UTC)
HEADER = "subject\tversion\tdate\tpermitted_uses\twithdrawn\tethics_approval_ref\n"


def _record(subject: str = "sub-01", version: int = 1, **fields: object) -> ConsentScope:
    values: dict[str, object] = {"date": dt.date(2026, 3, 1), "permitted_uses": ("training",)}
    values.update(fields)
    return ConsentScope(subject=subject, version=version, **values)  # type: ignore[arg-type]


def _vault(root: Path, records: list[ConsentScope] | None = None) -> store.VaultLocation:
    location = store.locate(root, store.DEFAULT_VAULT_PATH)
    store.init_vault(location)
    if records is not None:
        location.consents.write_bytes(dump_consents(ConsentFile(consents=records)))
    return location.refreshed()


def _add(location: store.VaultLocation, *records: ConsentScope | ImportedRecord) -> consents.AddResult:
    return add_consents(
        location, list(records), role="data_steward", purpose=None, approval_ref=None, now=lambda: TODAY
    )


def _state(location: store.VaultLocation) -> tuple[bytes, bytes]:
    return location.consents.read_bytes(), location.log.read_bytes()


# --- reading for check ----------------------------------------------------------------------------------


def test_load_for_check_states(tmp_path: Path) -> None:
    assert load_for_check(tmp_path, tmp_path, ".neurogrid/vault").state == "no_vault"
    (tmp_path / ".neurogrid" / "vault").mkdir(parents=True)
    missing = load_for_check(tmp_path, tmp_path, ".neurogrid/vault")
    assert (missing.state, missing.has_data, missing.sha256) == ("no_file", False, None)
    location = _vault(tmp_path)
    empty = load_for_check(tmp_path, tmp_path, ".neurogrid/vault")
    assert empty.state == "loaded" and not empty.has_data and empty.sha256 is not None  # consents: []
    location.consents.write_bytes(dump_consents(ConsentFile(consents=[_record()])))
    loaded = load_for_check(tmp_path, tmp_path, ".neurogrid/vault")
    assert loaded.has_data and loaded.file is not None and loaded.file.consents == [_record()]
    assert not loaded.outside_dataset and loaded.sha256 == loaded.file.canonical_sha256()


def test_a_vault_outside_the_dataset_is_marked(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    _vault(tmp_path, [_record()])
    loaded = load_for_check(dataset, tmp_path, ".neurogrid/vault")  # a toml outside the dataset (A-66)
    assert loaded.state == "loaded" and loaded.outside_dataset


@pytest.mark.parametrize("part", [".neurogrid", "vault", "consents.yaml"])
def test_links_in_the_vault_are_never_followed(tmp_path: Path, part: str) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    root = tmp_path / "dataset"
    if part == ".neurogrid":
        root.mkdir()
        dir_link(root / ".neurogrid", elsewhere)
    elif part == "vault":
        (root / ".neurogrid").mkdir(parents=True)
        dir_link(root / ".neurogrid" / "vault", elsewhere)
    else:
        (root / ".neurogrid" / "vault").mkdir(parents=True)
        dir_link(root / ".neurogrid" / "vault" / "consents.yaml", elsewhere)
    with pytest.raises(UnsafePathError) as info:
        load_for_check(root, root, ".neurogrid/vault")
    assert info.value.message_key == "vault.link" and info.value.params == {"part": part}


def test_unusable_consent_files_end_the_run(tmp_path: Path) -> None:
    (tmp_path / "file").write_bytes(b"x")
    with pytest.raises(InputError) as not_folder:
        load_for_check(tmp_path, tmp_path, "file/vault")
    assert not_folder.value.message_key == "vault.not_folder"
    location = _vault(tmp_path)
    location.consents.unlink()
    location.consents.mkdir()
    with pytest.raises(ConfigError) as folder:
        load_for_check(tmp_path, tmp_path, ".neurogrid/vault")
    assert folder.value.message_key == "consents.not_a_file"
    location.consents.rmdir()
    location.consents.write_bytes(b"format_version: 1\nconsents:\n  - subject: Zhang San\n")
    with pytest.raises(ConfigError) as invalid:
        load_for_check(tmp_path, tmp_path, ".neurogrid/vault")
    assert invalid.value.message_key == "consents.invalid" and "Zhang" not in str(invalid.value.params)


def test_identifying_references_and_long_numbers_are_counted() -> None:
    records = [
        _record("sub-01", ethics_approval_ref="EC-2026-17"),
        _record("sub-02", ethics_approval_ref="Zhang San approval"),
        _record("sub-1234567", ethics_approval_ref="伦理 17"),
        _record("sub-1234567", version=2),
    ]
    assert consents.identifying_refs(ConsentFile(consents=records)) == 2
    assert consents.subjects_with_long_numbers(records) == 1


# --- consents.tsv (D-10 b) -------------------------------------------------------------------------------


def _tsv(text: str) -> list[ImportedRecord]:
    return parse_consents_tsv(text.encode("utf-8"))


def _tsv_refusal(text: str | bytes) -> InputError:
    with pytest.raises(InputError) as info:
        parse_consents_tsv(text.encode("utf-8") if isinstance(text, str) else text)
    return info.value


def test_a_table_with_bom_aliases_and_blank_lines() -> None:
    text = (
        "﻿ Subject \tVERSION\tDate\tUses\tEthics_Ref\tWithdrawn\n"
        "01\t1\t2026-01-05\ttraining, Validation\tEC-1\t\n"
        "\n"
        "sub-02\t2\t2026-02-01\t\t\tyes\n"
    )
    first, second = _tsv(text)
    assert first.line == 2 and second.line == 4  # the header is line 1; the blank line is skipped
    assert first.record == _record(
        "sub-01",
        date=dt.date(2026, 1, 5),
        permitted_uses=("training", "validation"),
        ethics_approval_ref="EC-1",
    )
    assert second.record.withdrawn and second.record.permitted_uses == () and second.record.version == 2


@pytest.mark.parametrize("flag", ["true", "True", "1", "yes", "false", "0", "no", ""])
def test_withdrawn_values(flag: str) -> None:
    withdrawn = flag.lower() in ("true", "1", "yes")
    uses = "" if withdrawn else "training"
    (item,) = _tsv(HEADER + f"sub-01\t1\t2026-01-05\t{uses}\t{flag}\t\n")
    assert item.record.withdrawn is withdrawn


@pytest.mark.parametrize(
    "header",
    [
        "subject\tversion\tdate\n",  # permitted_uses missing
        "subject\tversion\tdate\tpermitted_uses\tnotes\n",  # unknown column
        "subject\tversion\tdate\tpermitted_uses\tuses\n",  # the same column twice (alias)
        "\n\n",  # no header
    ],
)
def test_columns_are_strict(header: str) -> None:
    assert _tsv_refusal(header + "sub-01\t1\t2026-01-05\ttraining\n").message_key == "consent_tsv.columns"


ROW = {
    "subject": "Zhang San\t1\t2026-01-05\ttraining\t\t",
    "version": "sub-01\t0\t2026-01-05\ttraining\t\t",
    "date": "sub-01\t1\t20260105\ttraining\t\t",
    "permitted_uses": "sub-01\t1\t2026-01-05\tresearch\t\t",
    "withdrawn": "sub-01\t1\t2026-01-05\ttraining\tmaybe\t",
    "ethics_approval_ref": "sub-01\t1\t2026-01-05\ttraining\t\t" + "E" * 121,
}


@pytest.mark.parametrize("column", list(ROW))
def test_invalid_rows_name_the_line_and_column_never_the_cell(column: str) -> None:
    error = _tsv_refusal(HEADER + "sub-09\t1\t2026-01-05\ttraining\t\t\n" + ROW[column] + "\n")
    assert error.message_key == "consent_tsv.invalid_row"
    assert error.params == {"line": 3, "field": column}


@pytest.mark.parametrize(
    "row",
    [
        "sub-01\t1\t2026-01-05\ttraining\ttrue\t",  # uses with a withdrawal
        "sub-01\t1\t2026-01-05\t\t\t",  # neither
        "sub-01\t1\t2026-01-05\ttraining,training\t\t",  # a use twice
        "sub-01\t1\t2026-02-30\ttraining\t\t",  # no real day
        "sub-01\t1.5\t2026-01-05\ttraining\t\t",
        "sub-01\t1\t2026-01-05\ttraining\t\tEC\tx",  # a cell beyond the last column
    ],
)
def test_more_invalid_rows(row: str) -> None:
    error = _tsv_refusal(HEADER + row + "\n")
    assert error.message_key == "consent_tsv.invalid_row" and error.params["line"] == 2


def test_duplicates_limits_and_encoding(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = "sub-01\t1\t2026-01-05\ttraining\t\t\nsub-02\t1\t2026-01-05\ttraining\t\t\n"
    duplicate = _tsv_refusal(HEADER + rows + "01\t1\t2026-02-05\ttraining\t\t\n")
    assert duplicate.message_key == "consent_tsv.duplicate" and duplicate.params == {"line": 4}
    assert (
        _tsv_refusal("subject\n".encode("cp1252") + "é\n".encode("cp1252")).message_key
        == "consent_tsv.encoding"
    )
    monkeypatch.setattr(consents, "MAX_TSV_ROWS", 1)
    assert _tsv_refusal(HEADER + rows).message_key == "consent_tsv.too_many_rows"
    monkeypatch.setattr(consents, "MAX_TSV_BYTES", 10)
    assert _tsv_refusal(HEADER).message_key == "consent_tsv.too_large"


def test_reading_the_table_file(tmp_path: Path) -> None:
    with pytest.raises(InputError) as missing:
        read_consents_tsv(tmp_path / "consents.tsv")
    assert missing.value.message_key == "consent.from_not_found"
    (tmp_path / "folder.tsv").mkdir()
    with pytest.raises(InputError) as folder:
        read_consents_tsv(tmp_path / "folder.tsv")
    assert folder.value.message_key == "consent_tsv.not_a_file"
    dir_link(tmp_path / "linked.tsv", tmp_path / "folder.tsv")
    with pytest.raises(UnsafePathError) as linked:
        read_consents_tsv(tmp_path / "linked.tsv")
    assert linked.value.message_key == "path.link"
    (tmp_path / "ok.tsv").write_text(HEADER + "sub-01\t1\t2026-01-05\ttraining\t\t\n", encoding="utf-8")
    assert [item.record.subject for item in read_consents_tsv(tmp_path / "ok.tsv")] == ["sub-01"]


# --- vault consent add (p6 decisions 3) ------------------------------------------------------------------


def test_add_writes_the_canonical_file_after_one_consent_manage_event(tmp_path: Path) -> None:
    location = _vault(tmp_path)
    result = _add(location, _record("sub-02"))
    assert location.consents.read_bytes() == dump_consents(ConsentFile(consents=[_record("sub-02")]))
    event = result.event
    assert (event.seq, event.action, event.role) == (1, "consent_manage", "data_steward")
    assert event.objects == [".neurogrid/vault/consents.yaml"]  # the file, never a subject (A-30)
    assert event.time == "2026-11-20T09:30:00Z" and event.purpose is None and event.approval_ref is None
    second = _add(
        location,
        _record("sub-01", 1),
        _record("sub-02", 2, date=dt.date(2026, 6, 1), withdrawn=True, permitted_uses=()),
    )
    assert second.event.seq == 2
    parsed = parse_consents(location.consents.read_bytes())
    assert [(r.subject, r.version) for r in parsed.consents] == [("sub-01", 1), ("sub-02", 1), ("sub-02", 2)]
    verification = ledger.verify(location)
    assert verification.intact and verification.events == 2
    assert not list(location.path.glob(".consents.yaml.*.tmp"))


def test_a_missing_consents_file_counts_as_empty(tmp_path: Path) -> None:
    location = _vault(tmp_path)
    location.consents.unlink()
    _add(location, _record())
    assert parse_consents(location.consents.read_bytes()).consents == [_record()]


def test_contradicting_records_are_refused_and_nothing_is_written(tmp_path: Path) -> None:
    location = _vault(tmp_path, [_record("sub-01", 2, date=dt.date(2026, 5, 1))])
    before = _state(location)
    for record, key in (
        (_record("sub-01", 2), "consent.duplicate_version"),
        (_record("sub-01", 3, date=dt.date(2026, 4, 1)), "consent.date_order"),  # dated before version 2
        (_record("sub-01", 1, date=dt.date(2026, 6, 1)), "consent.date_order"),  # dated after version 2
    ):
        with pytest.raises(InputError) as info:
            _add(location, record)
        assert info.value.message_key == key and info.value.params == {}
        assert _state(location) == before


def test_an_import_names_the_line_of_the_conflict(tmp_path: Path) -> None:
    location = _vault(tmp_path, [_record("sub-01", 2, date=dt.date(2026, 5, 1))])
    before = _state(location)
    table = _tsv(HEADER + "sub-02\t1\t2026-01-05\ttraining\t\t\nsub-01\t2\t2026-06-05\ttraining\t\t\n")
    with pytest.raises(InputError) as duplicate:
        _add(location, *table)
    assert duplicate.value.message_key == "consent_tsv.duplicate" and duplicate.value.params == {"line": 3}
    table = _tsv(HEADER + "sub-02\t1\t2026-01-05\ttraining\t\t\nsub-01\t1\t2026-06-05\ttraining\t\t\n")
    with pytest.raises(InputError) as order:
        _add(location, *table)
    assert order.value.message_key == "consent_tsv.invalid_row"
    assert order.value.params == {"line": 3, "field": "date"}
    assert _state(location) == before


def test_the_file_limits_hold_for_the_new_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    location = _vault(tmp_path, [_record("sub-01")])
    before = _state(location)
    monkeypatch.setattr(consents, "MAX_ENTRIES", 1)
    with pytest.raises(ConfigError) as many:
        _add(location, _record("sub-02"))
    assert many.value.params == {"field": "consents", "problem": "too_long"}
    monkeypatch.setattr(consents, "MAX_ENTRIES", 10)
    monkeypatch.setattr(consents, "MAX_FILE_BYTES", len(before[0]) + 10)
    with pytest.raises(ConfigError) as large:
        _add(location, _record("sub-02"))
    assert large.value.message_key == "consents.too_large"
    assert _state(location) == before


def test_without_a_vault_or_its_log_nothing_is_written(tmp_path: Path) -> None:
    absent = store.locate(tmp_path, store.DEFAULT_VAULT_PATH)
    with pytest.raises(InputError) as not_found:
        _add(absent, _record())
    assert not_found.value.message_key == "vault.not_found"
    location = _vault(tmp_path)
    location.log.unlink()  # a present vault without access.jsonl is never repaired silently
    before = location.consents.read_bytes()
    with pytest.raises(InputError) as log_missing:
        _add(location, _record())
    assert log_missing.value.message_key == "vault.log_missing"
    assert location.consents.read_bytes() == before and not location.log.exists()


def test_an_invalid_existing_file_is_refused(tmp_path: Path) -> None:
    location = _vault(tmp_path)
    location.consents.write_bytes(b"format_version: 2\nconsents: []\n")
    with pytest.raises(ConfigError) as info:
        _add(location, _record())
    assert info.value.message_key == "consents.invalid" and location.log.read_bytes() == b""


def test_invalid_event_fields_are_refused_before_the_lock(tmp_path: Path) -> None:
    location = _vault(tmp_path)
    with pytest.raises(InputError) as info:
        add_consents(location, [_record()], role="Zhang San", purpose=None, approval_ref=None)
    assert info.value.message_key == "vault.role_invalid" and location.log.read_bytes() == b""


def test_a_write_failure_after_the_event_keeps_the_logged_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    location = _vault(tmp_path, [_record("sub-01")])
    before = location.consents.read_bytes()
    calls: list[str] = []

    def refuse(source: object, target: object) -> None:
        calls.append(str(target))
        raise PermissionError(13, "in use")

    monkeypatch.setattr(os, "replace", refuse)
    with pytest.raises(InputError) as info:
        _add(location, _record("sub-02"))
    assert info.value.message_key == "consent.write_failed"
    assert len(calls) == 2  # one retry after store.REPLACE_RETRY_S (Windows: a reader holds the file)
    assert location.consents.read_bytes() == before  # unchanged
    assert not list(location.path.glob(".consents.yaml.*.tmp"))  # the temporary file is removed
    verification = ledger.verify(location)
    assert verification.intact and verification.events == 1  # the attempt is in the log


def test_a_held_lock_ends_with_vault_locked(tmp_path: Path) -> None:
    location = _vault(tmp_path)
    before = _state(location)
    with lock_held(location.lock), pytest.raises(VaultLocked):
        add_consents(location, [_record()], role="QA", purpose=None, approval_ref=None, timeout_s=0.3)
    assert _state(location) == before
