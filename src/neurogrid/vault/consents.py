"""The consent records in the vault (NV-F01, NV-F02, CLI-08, D-10 b; A-30, A-91): ``<vault>/consents.yaml``
read for M14, the import table ``consents.tsv`` and the rewrite by ``vault consent add``.

consents.yaml is a control file (C2): a link at its place or anywhere in the vault path is never followed
(errors.vault.link, p6 decisions 2), and a file that is no regular file, cannot be read, is too large, is no
UTF-8 text or holds invalid records ends the run with exit 2 (errors.consents.*). A missing vault and a vault
without consents.yaml are no error: M14 has no consent data then (not checkable, A-30).

``vault consent add`` (p6 decisions 3) holds the vault lock while it reads the existing records (missing =
none), validates the new complete file, appends the access event ``consent_manage`` (objects: consents.yaml
relative to the project root, never subject IDs, A-30 "keine Einwilligungsdaten") and only then replaces the
file in one step (store.replace_file). The event comes first: a change is never missing from the log; a write
that fails after it leaves the logged attempt (errors.consent.write_failed, documented).

consents.tsv (``--from``): UTF-8 with or without BOM, tab-separated, a header matched without surrounding
space and case (as splits.tsv), the columns subject, version, date, permitted_uses (alias uses;
comma-separated in the cell), withdrawn (optional: true/false/1/0/yes/no, empty = false) and
ethics_approval_ref (optional; alias ethics_ref). Unknown or repeated columns are an error, blank lines are
skipped. Errors name the line and the column, never the text of a cell (A-51). The import is all or nothing:
one event, or nothing at all.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from neurogrid.io.identifying import LONG_NUMBER, looks_identifying
from neurogrid.io.participants import canonical
from neurogrid.kernel.errors import ConfigError, InputError, UnsafePathError
from neurogrid.kernel.safety import is_link, read_limited
from neurogrid.model.access import AccessEvent
from neurogrid.model.consent import (
    CONSENT_USES,
    MAX_ENTRIES,
    MAX_FILE_BYTES,
    ConsentFile,
    ConsentScope,
    ConsentUse,
    consistency_problem,
    date_from_text,
    dump_consents,
    ethics_ref_valid,
    parse_consents,
    subject_id,
    version_from_text,
)
from neurogrid.vault import ledger, store
from neurogrid.vault.lock import LOCK_TIMEOUT_S, exclusive
from neurogrid.vault.store import CONSENTS_FILE, VaultLocation, require_present

CONSENT_ACTION = "consent_manage"
MAX_TSV_BYTES = 10_000_000
MAX_TSV_ROWS = 20_000
TSV_COLUMNS = {  # header (canonical) -> field
    "subject": "subject",
    "version": "version",
    "date": "date",
    "permitted_uses": "permitted_uses",
    "uses": "permitted_uses",
    "withdrawn": "withdrawn",
    "ethics_approval_ref": "ethics_approval_ref",
    "ethics_ref": "ethics_approval_ref",
}
TSV_REQUIRED = ("subject", "version", "date", "permitted_uses")
_TRUE = frozenset({"true", "1", "yes"})
_FALSE = frozenset({"false", "0", "no", ""})


# --- reading for check (M14) -------------------------------------------------------------------------------


@dataclass(frozen=True)
class LoadedConsents:
    """The consent records a check run found: ``no_vault`` (no vault folder), ``no_file`` (a vault without
    consents.yaml) or ``loaded``. ``outside_dataset``: the vault lies outside the dataset, so a manifest of
    the dataset does not cover consents.yaml."""

    state: Literal["no_vault", "no_file", "loaded"]
    file: ConsentFile | None = None
    outside_dataset: bool = False

    @property
    def has_data(self) -> bool:
        """At least one record (``consents: []`` holds no consent data, A-30)."""
        return self.file is not None and bool(self.file.consents)

    @property
    def sha256(self) -> str | None:
        """results.json config.consents_sha256: the canonical hash of the parsed records, None without a
        file."""
        return self.file.canonical_sha256() if self.file is not None else None


def read_consents(path: Path) -> ConsentFile:
    """consents.yaml at ``path``. Raises FileNotFoundError for a missing file, UnsafePathError
    errors.vault.link for a link and ConfigError errors.consents.not_a_file, .unreadable, .too_large and the
    errors of model.consent.parse_consents."""
    if is_link(path):
        raise UnsafePathError("vault.link", part=CONSENTS_FILE)
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        raise
    except OSError:
        raise ConfigError("consents.unreadable") from None
    if not stat.S_ISREG(info.st_mode):
        raise ConfigError("consents.not_a_file")
    try:
        data = read_limited(path, MAX_FILE_BYTES)
    except InputError:
        raise ConfigError("consents.too_large", limit=MAX_FILE_BYTES) from None
    except FileNotFoundError:
        raise
    except OSError:
        raise ConfigError("consents.unreadable") from None
    return parse_consents(data)


def load_for_check(dataset_root: Path, project_root: Path, vault_path: str) -> LoadedConsents:
    """The consent records for M14 (KONZEPT 1.4: before the signal pass, so an invalid file ends the run with
    exit 2 before the data are read, C2). The vault is ``project_root / vault_path`` (A-66). Raises
    errors.vault.link {part} (UnsafePathError) and errors.vault.not_folder (InputError) like every command
    that reads the vault (p6 decisions 2), and the errors of read_consents."""
    location = store.locate(project_root, vault_path)
    if location.state in ("link", "not_folder"):
        require_present(location)
    if location.state == "absent":
        return LoadedConsents("no_vault")
    outside = not location.path.is_relative_to(Path(dataset_root).resolve())
    try:
        parsed = read_consents(location.consents)
    except FileNotFoundError:
        return LoadedConsents("no_file", outside_dataset=outside)
    return LoadedConsents("loaded", parsed, outside_dataset=outside)


def identifying_refs(consents: ConsentFile) -> int:
    """How many ethics references read like a name, a long number or non-ASCII text (A-51 heuristic of
    io.identifying; notice.consent_refs_look_identifying shows the count, never a value)."""
    return sum(
        1
        for entry in consents.consents
        if entry.ethics_approval_ref is not None and looks_identifying(entry.ethics_approval_ref)
    )


def subjects_with_long_numbers(entries: Sequence[ConsentScope]) -> int:
    """Subjects whose label holds six or more digits in a row (A-51 heuristic: possibly a patient or study
    number, cli.vault.consent.subject_hint)."""
    return len({entry.subject for entry in entries if LONG_NUMBER.search(entry.subject)})


# --- the import table consents.tsv (D-10 b) ----------------------------------------------------------------


@dataclass(frozen=True)
class ImportedRecord:
    """One record of consents.tsv with its line (1 = header)."""

    line: int
    record: ConsentScope


def _invalid(line: int, column: str) -> InputError:
    return InputError("consent_tsv.invalid_row", line=line, field=column)


def _uses_cell(text: str, line: int) -> tuple[ConsentUse, ...]:
    items = [item.strip().lower() for item in text.split(",")]
    items = [item for item in items if item]
    if any(item not in CONSENT_USES for item in items) or len(set(items)) != len(items):
        raise _invalid(line, "permitted_uses")
    return tuple(ConsentUse(item) for item in items)


def _record(cells: dict[str, str], line: int) -> ConsentScope:
    subject = subject_id(cells["subject"])
    if subject is None:
        raise _invalid(line, "subject")
    version = version_from_text(cells["version"])
    if version is None:
        raise _invalid(line, "version")
    moment = date_from_text(cells["date"])
    if moment is None:
        raise _invalid(line, "date")
    uses = _uses_cell(cells["permitted_uses"], line)
    flag = cells.get("withdrawn", "").lower()
    if flag not in _TRUE | _FALSE:
        raise _invalid(line, "withdrawn")
    ethics = cells.get("ethics_approval_ref", "") or None
    if ethics is not None and not ethics_ref_valid(ethics):
        raise _invalid(line, "ethics_approval_ref")
    try:
        return ConsentScope(
            subject=subject,
            version=version,
            date=moment,
            permitted_uses=uses,
            withdrawn=flag in _TRUE,
            ethics_approval_ref=ethics,
        )
    except ValidationError:  # uses together with a withdrawal, or neither
        raise _invalid(line, "permitted_uses") from None


def parse_consents_tsv(data: bytes) -> list[ImportedRecord]:
    """Parse consents.tsv bytes (at most MAX_TSV_BYTES and MAX_TSV_ROWS records). Raises InputError
    errors.consent_tsv.too_large, .encoding, .columns, .too_many_rows, .invalid_row {line, field} and
    .duplicate {line} (the same subject and version twice in the table)."""
    if len(data) > MAX_TSV_BYTES:
        raise InputError("consent_tsv.too_large", limit=MAX_TSV_BYTES)
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise InputError("consent_tsv.encoding") from None
    lines = text.splitlines()
    header_line = next((index for index, line in enumerate(lines) if line.strip()), None)
    if header_line is None:
        raise InputError("consent_tsv.columns")
    names = [canonical(name) for name in lines[header_line].split("\t")]
    fields = [TSV_COLUMNS.get(name) for name in names]
    if None in fields or len(set(fields)) != len(fields) or not set(TSV_REQUIRED) <= set(fields):
        raise InputError("consent_tsv.columns")  # unknown, repeated or missing columns (as splits.tsv)
    records: list[ImportedRecord] = []
    seen: set[tuple[str, int]] = set()
    for index in range(header_line + 1, len(lines)):
        if not lines[index].strip():
            continue
        number = index + 1
        if len(records) >= MAX_TSV_ROWS:
            raise InputError("consent_tsv.too_many_rows", limit=MAX_TSV_ROWS)
        cells = lines[index].split("\t")
        if len(cells) > len(fields):
            raise _invalid(number, str(fields[-1]))  # a cell beyond the last column
        values = {str(name): (cells[at].strip() if at < len(cells) else "") for at, name in enumerate(fields)}
        record = _record(values, number)
        key = (record.subject, record.version)
        if key in seen:
            raise InputError("consent_tsv.duplicate", line=number)
        seen.add(key)
        records.append(ImportedRecord(number, record))
    return records


def read_consents_tsv(path: Path) -> list[ImportedRecord]:
    """The import table at an operator path (--from, A-66). The file itself must not be a link (folders on
    the way may be). Raises errors.path.link, errors.consent.from_not_found, errors.consent_tsv.not_a_file,
    .unreadable, .too_large and the errors of parse_consents_tsv."""
    if is_link(path):
        raise UnsafePathError("path.link")
    if not os.path.lexists(path):
        raise InputError("consent.from_not_found")
    if not path.is_file():
        raise InputError("consent_tsv.not_a_file")
    try:
        data = read_limited(path, MAX_TSV_BYTES)
    except InputError:
        raise InputError("consent_tsv.too_large", limit=MAX_TSV_BYTES) from None
    except OSError:
        raise InputError("consent_tsv.unreadable") from None
    return parse_consents_tsv(data)


# --- vault consent add (p6 decisions 3) --------------------------------------------------------------------


@dataclass(frozen=True)
class AddResult:
    """What ``vault consent add`` recorded: the access event and the new records."""

    event: AccessEvent
    records: tuple[ConsentScope, ...]


def _existing(location: VaultLocation) -> ConsentFile:
    try:
        return read_consents(location.consents)
    except FileNotFoundError:
        return ConsentFile(consents=[])


def _new_file(existing: ConsentFile, added: Sequence[ImportedRecord | ConsentScope]) -> bytes:
    """The complete new file in its canonical form. A record that repeats a subject and version or breaks the
    date order (dates do not decrease with the version) is refused: errors.consent.duplicate_version /
    .date_order for a single record, errors.consent_tsv.duplicate / .invalid_row (column date) with the line
    for an import."""
    entries = list(existing.consents)
    lines: list[int | None] = [None] * len(entries)
    for item in added:
        record = item.record if isinstance(item, ImportedRecord) else item
        entries.append(record)
        lines.append(item.line if isinstance(item, ImportedRecord) else None)
    found = consistency_problem(entries)
    if found is not None:
        index, _field, problem = found
        line = lines[index]
        if line is None:  # an existing record: the conflict is with the first new record of its subject
            subject = entries[index].subject
            line = next((n for n, e in zip(lines, entries, strict=True) if n and e.subject == subject), None)
        if line is None:  # a single record (the existing file is consistent on its own)
            raise InputError(f"consent.{problem}")
        if problem == "duplicate_version":
            raise InputError("consent_tsv.duplicate", line=line)
        raise _invalid(line, "date")
    # what is written must read back (parse_consents): at most MAX_ENTRIES records and MAX_FILE_BYTES; the
    # records are valid already and the canonical form reads back exactly (tests/unit/test_consent_model.py),
    # so the limits are checked here instead of parsing the new file again (PyYAML is slow, A-53)
    if len(entries) > MAX_ENTRIES:
        raise ConfigError("consents.invalid", field="consents", problem="too_long")
    data = dump_consents(ConsentFile(consents=entries))
    if len(data) > MAX_FILE_BYTES:
        raise ConfigError("consents.too_large", limit=MAX_FILE_BYTES)
    return data


def add_consents(
    location: VaultLocation,
    added: Sequence[ImportedRecord | ConsentScope],
    *,
    role: str | None,
    purpose: str | None,
    approval_ref: str | None,
    now: Callable[[], datetime] = ledger.utc_now,
    timeout_s: float = LOCK_TIMEOUT_S,
) -> AddResult:
    """Record consents under the vault lock (p6 decisions 3): read the existing consents.yaml (missing =
    none), validate the new complete file, append the access event, replace the file. Nothing is written
    when a step before the event fails; the event stays when the write after it fails (errors.consent.
    write_failed: the log shows the attempt, the file is unchanged, the temporary file is removed).

    Raises the tool errors (exit 2) of ledger.check_fields, store.require_present (errors.vault.not_found,
    .link, .not_folder), errors.vault.locked (VaultLocked), .not_writable, the event statuses
    (errors.vault.log_missing, .log_damaged, ...), errors.consents.* for an invalid existing file, the errors
    of _new_file and errors.consent.write_failed."""
    objects = [location.object_name(CONSENTS_FILE)]
    ledger.check_fields(
        role=role, action=CONSENT_ACTION, objects=objects, purpose=purpose, approval_ref=approval_ref
    )
    require_present(location.refreshed())
    try:
        with exclusive(location.lock, timeout_s) as held:
            current = location.refreshed()  # a link may have appeared while we waited
            require_present(current)
            data = _new_file(_existing(current), added)
            outcome = ledger.append_locked(
                current,
                held,
                role=role,
                action=CONSENT_ACTION,
                objects=objects,
                purpose=purpose,
                approval_ref=approval_ref,
                now=now,
            )
            if outcome.status != "written" or outcome.event is None:
                raise outcome.error()
            try:
                store.replace_file(current.consents, data)
            except OSError:
                raise InputError("consent.write_failed") from None
    except OSError:  # the lock file cannot be opened or created (a read-only vault without one)
        raise InputError("vault.not_writable") from None
    records = tuple(item.record if isinstance(item, ImportedRecord) else item for item in added)
    return AddResult(outcome.event, records)
