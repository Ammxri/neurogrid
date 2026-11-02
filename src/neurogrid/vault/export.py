"""The export package of NeuroVault: ``vault export`` (NV-F07, CON-02, UF-03, UF-06; A-30, A-96).

One ZIP for an inspection with exactly the five parts plus ``index.json`` (model.export.ExportIndex):

- ``manifest.json``: the dataset's manifest (``<dataset>/.neurogrid/manifest.json`` or ``--manifest``), parsed
  with kernel.provenance.parse_manifest. In a raw folder without --show-paths the archive holds a copy whose
  ``files[].path``, ``skipped[].path`` and ``excluded`` are the names io.provenance.show displays
  (``rec-<sha8>.<ext>``, NeuroGrid's fixed names in .neurogrid/ in clear, A-51); its manifest_hash stays the
  stored one (index.json: pseudonymized). BIDS datasets and --show-paths keep the file byte for byte.
- ``access.jsonl``: the access log up to and including the export event (bytes [0, S), the snapshot rule).
- ``roles.yaml``: the role register, as it is (it must parse, errors.roles.*).
- ``pia/pia.zh.md``, ``pia/pia.en.md``: every present impact assessment file, at least one.
- ``report/report.<lang>.<html|pdf>`` and ``report/dossier.pdf``: 1 to 5 NeuroGrid reports, identified by the
  pipeline (report.identify; this module never imports the report, ARC-01), each name at most once.

Never in the archive: consents.yaml, risks.yaml, retention.yaml, results.json, any data file (no signals, no
consent data, A-30, CON-02). Only regular files: every part is checked with lstat and read through a handle
opened without following links (O_NOFOLLOW on POSIX, a link check before on Windows); a link in the vault is
errors.vault.link {part} as in P6 (never followed), a folder or another special file errors.export.not_regular
{part}, a missing part errors.export.part_missing {part}.

Order of work (A-30 "Ereignis vor dem Packen"), all or nothing: everything is read and validated first and
the temporary file next to --out is created (a refusal writes nothing, not even an access event); then, under
the vault lock, the export event is appended (``append_locked``, objects: the manifest when it lies in the
dataset, the log, roles.yaml and the PIA files relative to the project root) and the size S of the log taken
through a handle opened there; after the lock is released the bytes [0, S) of that handle are streamed into
the archive and the log is verified up to S as every reader of P6 does it (ledger.iter_entries reads it by
its name; only NeuroGrid appends after S, so both see the same entries). index.json records the head (the
export event's hash), the entries and the state of the chain; a broken chain is exported and named (a
warning, never exit 1). The temporary file then replaces --out. A failure after the event is
errors.export.write_failed: the event stays (the log shows the attempt, as for ``vault consent add``), the
temporary file is removed and --out is unchanged.

Archive (A-96): fixed names and order (model.export.PARTS, then index.json), every entry with date_time
1980-01-01 00:00:00, create_system 3 (Unix), external_attr 0o100644 << 16 (a regular file, rw-r--r--),
ZIP_DEFLATED at zlib's default level (Z_DEFAULT_COMPRESSION, level 6), no folder entries and no extra fields;
ZIP64 only where zipfile needs it (from the known size of each member). The same inputs and clock give the
same bytes in one environment (zlib's output may differ between platforms).
"""

from __future__ import annotations

import hashlib
import os
import stat
import zipfile
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

from neurogrid.io.provenance import show
from neurogrid.kernel import canonical
from neurogrid.kernel.errors import InputError, NeuroGridError, UnsafePathError
from neurogrid.kernel.provenance import ParsedManifest, manifest_bytes, parse_manifest
from neurogrid.kernel.safety import create_temporary, is_link
from neurogrid.model.access import AccessEvent
from neurogrid.model.export import (
    ExportAccessLog,
    ExportIndex,
    ExportManifest,
    ExportPart,
    ReportFormat,
)
from neurogrid.model.results import Disclaimer, ToolInfo
from neurogrid.model.roles import MAX_FILE_BYTES as MAX_ROLES_BYTES
from neurogrid.model.roles import RoleRegister, parse_roles
from neurogrid.vault import _os, ledger, roles
from neurogrid.vault.lock import LOCK_TIMEOUT_S, exclusive
from neurogrid.vault.store import (
    PIA_FILES,
    PIA_FOLDER,
    ROLES_FILE,
    VaultLocation,
    pia_template,
    require_present,
)

EXPORT_ACTION = "export"
MAX_PIA_BYTES = 4_000_000  # as CORE-NV05-02 reads a PIA file (A-94)
MAX_REPORT_BYTES = 256_000_000  # as results.json (A-53)
MAX_REPORTS = 5  # report.zh/en.html/pdf and dossier.pdf, each at most once
READ_CHUNK = 1_048_576
MANIFEST_MEMBER = "manifest.json"
LOG_MEMBER = "access.jsonl"
ROLES_MEMBER = ROLES_FILE
INDEX_MEMBER = "index.json"
REPORT_FOLDER = "report"
# The reports in archive order (A-96): the languages in report order, html before pdf, the dossier last
REPORT_ORDER = ("report.zh.html", "report.zh.pdf", "report.en.html", "report.en.pdf", "dossier.pdf")
ZIP_DATE = (1980, 1, 1, 0, 0, 0)
ZIP_SYSTEM_UNIX = 3
ZIP_FILE_MODE = 0o100644 << 16  # S_IFREG | rw-r--r-- in the high 16 bits (Unix attributes)
_BOM = b"\xef\xbb\xbf"
# Warnings of a written export (cli.vault.export.<key>): the export is written anyway (A-96)
PIA_UNEDITED = "pia_unedited"
ROLES_EMPTY = "roles_empty"
CHAIN_BROKEN = "chain_broken"


@dataclass(frozen=True)
class ExportReport:
    """A report the pipeline identified (report.identify): its fixed name in REPORT_ORDER, its language (None:
    the dossier, both languages), its format and its bytes."""

    name: str
    lang: str | None
    format: ReportFormat
    data: bytes


@dataclass(frozen=True)
class ExportManifestSource:
    """The manifest as read: its bytes, its path relative to the dataset when it lies there (the event
    object, already in the form the log stores), and whether the archive keeps its names in clear (a BIDS
    dataset or --show-paths)."""

    data: bytes
    object: str | None
    plain: bool


@dataclass(frozen=True)
class ExportResult:
    """What ``vault export`` wrote: the access event, index.json as written, the warnings (PIA_UNEDITED,
    ROLES_EMPTY, CHAIN_BROKEN) and the role warning of its event (vault.roles.role_warning: the register it
    packs does not permit the export; A-93)."""

    event: AccessEvent
    index: ExportIndex
    warnings: tuple[str, ...]
    role_warning: str | None = None


def read_regular(
    path: Path,
    *,
    part: str,
    max_bytes: int,
    link: Callable[[], NeuroGridError],
    too_large: Callable[[], NeuroGridError],
) -> bytes:
    """The bytes of one part, never through a link: ``link()`` for a link at the file itself (also ELOOP of
    O_NOFOLLOW), errors.export.part_missing {part} for a missing file, errors.export.not_regular {part} for a
    folder or a special file, ``too_large()`` beyond ``max_bytes`` (nothing beyond is read, A-53)."""
    if is_link(path):
        raise link()
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        raise InputError("export.part_missing", part=part) from None
    except OSError:
        raise InputError("export.not_regular", part=part) from None
    if not stat.S_ISREG(info.st_mode):
        raise InputError("export.not_regular", part=part)
    try:
        fd = _os.open_for_reading(path)
    except FileNotFoundError:
        raise InputError("export.part_missing", part=part) from None
    except OSError as exc:
        if _os.is_link_error(exc):
            raise link() from None
        raise InputError("export.not_regular", part=part) from None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):  # replaced while we looked
            raise InputError("export.not_regular", part=part)
        data = _read_up_to(fd, max_bytes + 1)
    except OSError:
        raise InputError("export.not_regular", part=part) from None
    finally:
        os.close(fd)
    if len(data) > max_bytes:
        raise too_large()
    return data


def _read_up_to(fd: int, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while total < limit:
        chunk = os.read(fd, min(READ_CHUNK, limit - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    return b"".join(chunks)


def _vault_link(part: str) -> Callable[[], NeuroGridError]:
    return lambda: UnsafePathError("vault.link", part=part)


def archived_manifest(parsed: ParsedManifest, data: bytes, *, plain: bool) -> tuple[bytes, bool]:
    """The manifest.json of the archive and whether it is the pseudonymous copy (A-51): BIDS datasets and
    --show-paths (``plain``) keep the file as it is; in a raw folder every path of ``files``, ``skipped`` and
    ``excluded`` becomes the name io.provenance.show displays (verify and the findings show the same names),
    written canonically (kernel.provenance.manifest_bytes). The stored manifest_hash is kept."""
    if plain:
        return data, False
    manifest = parsed.manifest
    copy = manifest.model_copy(
        update={
            "files": [
                item.model_copy(update={"path": show(item.path, plain=False).file}) for item in manifest.files
            ],
            "skipped": [
                entry.model_copy(update={"path": show(entry.path, plain=False, kind=entry.kind).file})
                for entry in manifest.skipped
            ],
            "excluded": [show(name, plain=False).file for name in manifest.excluded],
        }
    )
    return manifest_bytes(copy), True


def _pia_unedited(name: str, data: bytes) -> bool:
    """The PIA file equals its template after removing a BOM and CRLF line ends (the rule of CORE-NV05-02)."""
    text = data.removeprefix(_BOM).replace(b"\r\n", b"\n")
    return text == pia_template(name)


@dataclass(frozen=True)
class _Member:
    """A member of the archive before writing: its part, name, language and format and its bytes."""

    part: str
    name: str
    data: bytes
    lang: str | None = None
    format: ReportFormat | None = None


def _vault_members(
    current: VaultLocation,
) -> tuple[list[_Member], list[str], list[str], RoleRegister]:
    """roles.yaml and the PIA files of the vault (read and checked), their event objects, the warnings and
    the role register as packed."""
    warnings: list[str] = []
    data = read_regular(
        current.roles,
        part=ROLES_FILE,
        max_bytes=MAX_ROLES_BYTES,
        link=_vault_link(ROLES_FILE),
        too_large=lambda: InputError("roles.too_large", limit=MAX_ROLES_BYTES),
    )
    register = parse_roles(data)
    if not register.entries:
        warnings.append(ROLES_EMPTY)
    members = [_Member("roles", ROLES_MEMBER, data)]
    objects = [current.object_name(ROLES_FILE)]
    if is_link(current.pia_folder):
        raise UnsafePathError("vault.link", part=PIA_FOLDER)
    unedited = []
    for name, path in zip(PIA_FILES, current.pia_files, strict=True):
        part = f"{PIA_FOLDER}/{name}"
        if not os.path.lexists(path):
            continue
        data = read_regular(
            path,
            part=part,
            max_bytes=MAX_PIA_BYTES,
            link=_vault_link(part),
            too_large=lambda: InputError("file.too_large", limit=MAX_PIA_BYTES),
        )
        members.append(_Member("pia", part, data, lang=name.split(".")[1]))
        objects.append(current.object_name(part))
        unedited.append(_pia_unedited(name, data))
    if len(members) == 1:
        raise InputError("export.part_missing", part=PIA_FOLDER)
    if all(unedited):
        warnings.append(PIA_UNEDITED)
    return members, objects, warnings, register


def _report_members(reports: Sequence[ExportReport]) -> list[_Member]:
    if not reports or len(reports) > MAX_REPORTS:
        raise ValueError("an export holds 1 to 5 reports")
    names = [report.name for report in reports]
    if len(set(names)) != len(names) or not set(names) <= set(REPORT_ORDER):
        raise ValueError("each report name of REPORT_ORDER at most once")
    ordered = sorted(reports, key=lambda report: REPORT_ORDER.index(report.name))
    return [
        _Member("report", f"{REPORT_FOLDER}/{report.name}", report.data, report.lang, report.format)
        for report in ordered
    ]


def _entry(name: str, size: int) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, ZIP_DATE)
    info.create_system = ZIP_SYSTEM_UNIX
    info.external_attr = ZIP_FILE_MODE
    info.compress_type = zipfile.ZIP_DEFLATED
    info.file_size = size  # zipfile decides ZIP64 from it
    return info


def _write(archive: zipfile.ZipFile, member: _Member) -> ExportPart:
    with archive.open(_entry(member.name, len(member.data)), "w") as stream:
        stream.write(member.data)
    return ExportPart(
        part=member.part,
        file=member.name,
        sha256=hashlib.sha256(member.data).hexdigest(),
        size=len(member.data),
        lang=member.lang,
        format=member.format,
    )


def _stream_log(archive: zipfile.ZipFile, fd: int, size: int) -> ExportPart:
    """The bytes [0, size) of the log handle as the member access.jsonl."""
    digest = hashlib.sha256()
    os.lseek(fd, 0, os.SEEK_SET)
    remaining = size
    with archive.open(_entry(LOG_MEMBER, size), "w") as stream:
        while remaining > 0:
            chunk = os.read(fd, min(READ_CHUNK, remaining))
            if not chunk:  # the log became shorter than the snapshot: it was not NeuroGrid
                raise OSError("the access log is shorter than its snapshot")
            stream.write(chunk)
            digest.update(chunk)
            remaining -= len(chunk)
    return ExportPart(part="access_log", file=LOG_MEMBER, sha256=digest.hexdigest(), size=size)


def _new_folders(folder: Path) -> Path | None:
    """Create the missing folders above --out; the topmost one created (to remove after a refusal) or None."""
    missing = [parent for parent in (folder, *folder.parents) if not parent.exists()]
    folder.mkdir(parents=True, exist_ok=True)
    return missing[-1] if missing else None


def _remove_folders(top: Path | None, folder: Path) -> None:
    """Remove the empty folders this export created for nothing (best effort)."""
    if top is None:
        return
    for current in (folder, *folder.parents):
        with suppress(OSError):
            current.rmdir()
        if current == top:
            break


def export_vault(
    location: VaultLocation,
    out: Path,
    *,
    manifest: ExportManifestSource,
    reports: Sequence[ExportReport],
    role: str,
    purpose: str | None,
    approval_ref: str | None,
    disclaimer: Disclaimer,
    tool: ToolInfo,
    now: Callable[[], datetime] = ledger.utc_now,
    timeout_s: float = LOCK_TIMEOUT_S,
) -> ExportResult:
    """Write the export package of the vault at ``location`` to ``out`` (see the module docstring for the
    order of work). Raises (exit 2, nothing written and no event): the errors of ledger.check_fields and
    store.require_present, errors.output.is_directory, errors.export.out_in_vault, the manifest errors
    (errors.manifest.*), errors.export.part_missing / .not_regular {part}, errors.vault.link {part},
    errors.roles.*, errors.output.not_writable (the folder of --out takes no file), errors.vault.locked and
    the event statuses (errors.vault.log_missing, .log_damaged, .not_writable, ...); after the event
    errors.export.write_failed (the event stays)."""
    parsed = parse_manifest(manifest.data)
    current = location.refreshed()
    require_present(current)
    out = Path(out)
    if out.is_dir():
        raise InputError("output.is_directory")
    vault_folder = current.path.resolve()
    target = out.resolve(strict=False)
    if target == vault_folder or target.is_relative_to(vault_folder):
        raise InputError("export.out_in_vault")
    archived, pseudonymized = archived_manifest(parsed, manifest.data, plain=manifest.plain)
    if is_link(current.log):
        raise UnsafePathError("vault.link", part=LOG_MEMBER)
    try:
        log_info = os.lstat(current.log)
    except FileNotFoundError:
        raise InputError("export.part_missing", part=LOG_MEMBER) from None
    if not stat.S_ISREG(log_info.st_mode):
        raise InputError("export.not_regular", part=LOG_MEMBER)
    vault_members, vault_objects, warnings, register = _vault_members(current)
    report_members = _report_members(reports)
    objects = [
        *([manifest.object] if manifest.object is not None else []),
        current.object_name(LOG_MEMBER),
        *vault_objects,
    ]
    ledger.check_fields(
        role=role, action=EXPORT_ACTION, objects=objects, purpose=purpose, approval_ref=approval_ref
    )
    # compared before the event, with the register as packed (an invalid one already refused the export)
    role_warning = roles.role_warning(roles.permission(register, role, EXPORT_ACTION, objects))
    created = None
    try:
        created = _new_folders(out.parent)
        handle, name = create_temporary(out.parent, f".{out.name}.")
    except OSError:
        _remove_folders(created, out.parent)
        raise InputError("output.not_writable") from None
    temporary = Path(name)
    stream: BinaryIO = os.fdopen(handle, "w+b")
    written = False
    try:
        event, fd, size = _append_event(current, objects, role, purpose, approval_ref, now, timeout_s)
        try:
            index, chain_intact = _write_archive(
                stream,
                fd,
                size,
                current,
                manifest_member=_Member("manifest", MANIFEST_MEMBER, archived),
                members=[*vault_members, *report_members],
                manifest_index=ExportManifest(
                    manifest_hash=parsed.manifest.manifest_hash,
                    source_sha256=hashlib.sha256(manifest.data).hexdigest(),
                    pseudonymized=pseudonymized,
                ),
                disclaimer=disclaimer,
                tool=tool,
            )
            stream.close()
            temporary.replace(out)  # one step; an earlier file of that name is replaced
        except (OSError, ValueError, zipfile.LargeZipFile):
            raise InputError("export.write_failed") from None
        finally:
            os.close(fd)
        written = True
    finally:
        stream.close()
        if not written:
            temporary.unlink(missing_ok=True)
            if created is not None and not out.exists():
                _remove_folders(created, out.parent)
    if not chain_intact:
        warnings.append(CHAIN_BROKEN)
    return ExportResult(event, index, tuple(warnings), role_warning)


def _append_event(
    current: VaultLocation,
    objects: Sequence[str],
    role: str,
    purpose: str | None,
    approval_ref: str | None,
    now: Callable[[], datetime],
    timeout_s: float,
) -> tuple[AccessEvent, int, int]:
    """Under the vault lock: the export event, then a handle on the log (no link followed) and its size S.
    The handle stays open for streaming after the lock is released; NeuroGrid only appends after S."""
    try:
        with exclusive(current.lock, timeout_s) as held:
            located = current.refreshed()  # a link may have appeared while we waited
            require_present(located)
            outcome = ledger.append_locked(
                located,
                held,
                role=role,
                action=EXPORT_ACTION,
                objects=objects,
                purpose=purpose,
                approval_ref=approval_ref,
                now=now,
            )
            if outcome.status != "written" or outcome.event is None:
                raise outcome.error()
            try:
                fd = _os.open_for_reading(located.log)
            except OSError:  # the event is written: what follows is a failed write of the export
                raise InputError("export.write_failed") from None
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode):
                    raise InputError("export.write_failed")
            except BaseException:
                os.close(fd)
                raise
            return outcome.event, fd, info.st_size
    except OSError:  # the lock file cannot be opened or created (a read-only vault without one)
        raise InputError("vault.not_writable") from None


def _write_archive(
    stream: BinaryIO,
    fd: int,
    size: int,
    current: VaultLocation,
    *,
    manifest_member: _Member,
    members: Sequence[_Member],
    manifest_index: ExportManifest,
    disclaimer: Disclaimer,
    tool: ToolInfo,
) -> tuple[ExportIndex, bool]:
    """The archive in member order with index.json last; the log verified up to ``size`` (snapshot rule)."""
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        parts = [_write(archive, manifest_member), _stream_log(archive, fd, size)]
        parts += [_write(archive, member) for member in members]
        verification = ledger.verify_entries(ledger.iter_entries(current.log, size))
        if verification.head is None:  # the export event is in [0, S)
            raise OSError("no readable entry in the exported log")
        index = ExportIndex(
            disclaimer=disclaimer,
            tool=tool,
            parts=parts,
            manifest=manifest_index,
            access_log=ExportAccessLog(
                head=verification.head,
                events=verification.events,
                intact=verification.intact,
                deviations=len(verification.deviations),
            ),
        )
        data = canonical.dumps(index)
        with archive.open(_entry(INDEX_MEMBER, len(data)), "w") as member:
            member.write(data)
    return index, verification.intact
