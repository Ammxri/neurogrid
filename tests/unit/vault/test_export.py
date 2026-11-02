"""The export package of NeuroVault (NV-F07, CON-02; A-30, A-96): archive layout and entry modes, byte
identity with a fixed clock, the export event before packing (the archived log ends with it and index.json
names its hash as head), a write failure that keeps the event, and the refusals that write nothing."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

import pytest
from vault_processes import lock_held  # type: ignore[import-not-found]

from conftest import dir_link  # type: ignore[import-not-found]
from neurogrid.io.provenance import show
from neurogrid.kernel import canonical
from neurogrid.kernel.errors import ConfigError, InputError, NeuroGridError, UnsafePathError
from neurogrid.kernel.provenance import Manifest, ManifestError, manifest_bytes, manifest_hash, parse_manifest
from neurogrid.model.export import PARTS, ExportIndex
from neurogrid.model.results import Disclaimer, ToolInfo
from neurogrid.vault import export, ledger, store
from neurogrid.vault.export import ExportManifestSource, ExportReport, archived_manifest, export_vault
from neurogrid.vault.lock import VaultLocked

NOW = dt.datetime(2026, 11, 2, 9, 30, tzinfo=dt.UTC)
DISCLAIMER = Disclaimer(zh="固定声明", en="Fixed sentence")
TOOL = ToolInfo(version="9.9.9")
SIGNAL = b"EDF signal bytes of a recording (synthetic)\n"
ROLES = (
    b"format_version: 1\nroles:\n  - role: QA.lead\n    description: Reviews\n"
    b"    actions: [read, export]\n    objects: ['**']\n"
)
MISSING_FORMAT = {"field": "format_version", "problem": "missing"}
NAMES = [
    "manifest.json",
    "access.jsonl",
    "roles.yaml",
    "pia/pia.zh.md",
    "pia/pia.en.md",
    "report/report.zh.pdf",
    "report/report.en.html",
    "report/dossier.pdf",
    "index.json",
]


def _manifest(files: dict[str, bytes]) -> bytes:
    content: dict[str, Any] = {
        "format_version": "1",
        "files": [
            {"path": path, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
            for path, data in sorted(files.items())
        ],
        "skipped": [{"path": "Zhang San/linked.edf", "kind": "link"}],
        "excluded": [".neurogrid/vault/access.jsonl", ".neurogrid/vault/access.jsonl.lock"],
        "processing_steps": [],
        "software": [{"name": "neurogrid", "version": "9.9.9", "source": "manifest"}],
    }
    content["manifest_hash"] = manifest_hash(content)
    return manifest_bytes(Manifest.model_validate(content))


MANIFEST = _manifest({"Zhang San/rec_01.edf": SIGNAL, ".neurogrid/vault/roles.yaml": ROLES})
REPORTS = (  # given in another order than the archive's
    ExportReport("dossier.pdf", None, "dossier", b"%PDF-dossier"),
    ExportReport("report.en.html", "en", "html", b"<html>en</html>"),
    ExportReport("report.zh.pdf", "zh", "pdf", b"%PDF-zh"),
)


def _vault(root: Path) -> store.VaultLocation:
    """A vault with an edited PIA in both languages, a role register and two events in the log."""
    root.mkdir(parents=True)
    location = store.locate(root, store.DEFAULT_VAULT_PATH)
    store.init_vault(location)
    location.roles.write_bytes(ROLES)
    for path in location.pia_files:
        path.write_bytes(
            path.read_bytes().replace("【待填写】".encode(), b"done").replace(b"[to be completed]", b"done")
        )
    (root / "Zhang San").mkdir()
    (root / "Zhang San" / "rec_01.edf").write_bytes(SIGNAL)
    location.consents.write_bytes(store.CONSENTS_TEMPLATE + b"# planted Wang_Wei_1987\n")
    for _ in range(2):
        outcome = ledger.append(
            location,
            role="QA.lead",
            action="check",
            objects=["**"],
            purpose=None,
            approval_ref=None,
            now=lambda: NOW,
        )
        assert outcome.status == "written"
    return location.refreshed()


def _export(
    location: store.VaultLocation,
    out: Path,
    *,
    manifest: bytes = MANIFEST,
    plain: bool = False,
    reports: tuple[ExportReport, ...] = REPORTS,
    **kwargs: Any,
) -> export.ExportResult:
    return export_vault(
        location,
        out,
        manifest=ExportManifestSource(manifest, ".neurogrid/manifest.json", plain),
        reports=reports,
        role="QA.lead",
        purpose="inspection",
        approval_ref=None,
        disclaimer=DISCLAIMER,
        tool=TOOL,
        now=lambda: NOW,
        **kwargs,
    )


def _members(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        return {info.filename: archive.read(info) for info in archive.infolist()}


def test_archive_layout_and_entries(tmp_path: Path) -> None:
    """A-96: fixed names in fixed order, index.json last; every entry a regular file with the fixed time,
    Unix attributes 0o100644, deflated, no folder entry, no extra field, no data descriptor."""
    location = _vault(tmp_path / "data")
    out = tmp_path / "out" / "检查包.zip"
    result = _export(location, out)
    with zipfile.ZipFile(out) as archive:
        infos = archive.infolist()
        assert archive.testzip() is None
    assert [info.filename for info in infos] == NAMES
    for info in infos:
        assert info.date_time == (1980, 1, 1, 0, 0, 0) and info.create_system == 3, info.filename
        assert info.external_attr == 0o100644 << 16 and not info.is_dir(), info.filename
        assert info.compress_type == zipfile.ZIP_DEFLATED and info.extra == b"", info.filename
        assert not info.flag_bits & 0x08, info.filename  # sizes in the local header, no data descriptor
    members = _members(out)
    index = ExportIndex.model_validate_json(members["index.json"])
    assert index == result.index and members["index.json"] == canonical.dumps(index)
    assert [part.file for part in index.parts] == NAMES[:-1]
    assert [part.part for part in index.parts] == [
        "manifest",
        "access_log",
        "roles",
        "pia",
        "pia",
        "report",
        "report",
        "report",
    ]
    assert {part.part for part in index.parts} == set(PARTS)
    for part in index.parts:
        assert part.sha256 == hashlib.sha256(members[part.file]).hexdigest() and part.size == len(
            members[part.file]
        )
    assert [(p.lang, p.format) for p in index.parts[3:]] == [
        ("zh", None),
        ("en", None),
        ("zh", "pdf"),
        ("en", "html"),
        (None, "dossier"),
    ]
    assert index.disclaimer == DISCLAIMER and index.tool == TOOL and index.format_version == 1
    assert members["roles.yaml"] == ROLES and members["pia/pia.zh.md"] == location.pia_files[0].read_bytes()
    assert members["report/dossier.pdf"] == b"%PDF-dossier"
    # never consents, risks, retention, results.json or a data file (A-30, CON-02)
    assert not any(
        name.endswith((".edf", "consents.yaml", "risks.yaml", "retention.yaml", "results.json"))
        for name in members
    )
    assert all(SIGNAL not in data and b"Wang_Wei_1987" not in data for data in members.values())
    assert result.warnings == ()
    text = members["index.json"].decode("utf-8")
    assert str(tmp_path) not in text and "2026-11-02" not in text  # no path, no time (A-51)


def test_the_event_comes_before_packing(tmp_path: Path) -> None:
    """A-30 'Ereignis vor dem Packen': the archived log ends with the export event, its hash is the head of
    index.json; the vault's log holds exactly the archived bytes afterwards."""
    location = _vault(tmp_path / "data")
    out = tmp_path / "pkg.zip"
    result = _export(location, out)
    members = _members(out)
    lines = members["access.jsonl"].splitlines()
    last = json.loads(lines[-1])
    assert last["action"] == "export" and last["hash"] == result.event.hash == result.index.access_log.head
    assert last["objects"] == [
        ".neurogrid/manifest.json",
        ".neurogrid/vault/access.jsonl",
        ".neurogrid/vault/roles.yaml",
        ".neurogrid/vault/pia/pia.zh.md",
        ".neurogrid/vault/pia/pia.en.md",
    ]
    assert (last["role"], last["purpose"], last["seq"]) == ("QA.lead", "inspection", 3)
    assert members["access.jsonl"] == location.log.read_bytes()
    log = result.index.access_log
    assert (log.events, log.intact, log.deviations) == (3, True, 0)


def test_two_exports_with_the_same_clock_are_byte_identical(tmp_path: Path) -> None:
    """A-96: the same inputs and clock give the same archive (one environment)."""
    first = _vault(tmp_path / "a" / "data")
    shutil.copytree(tmp_path / "a" / "data", tmp_path / "b" / "data")
    second = store.locate(tmp_path / "b" / "data", store.DEFAULT_VAULT_PATH)
    _export(first, tmp_path / "a.zip")
    _export(second, tmp_path / "b.zip")
    assert (tmp_path / "a.zip").read_bytes() == (tmp_path / "b.zip").read_bytes()


def test_the_raw_manifest_copy_shows_pseudonymous_names(tmp_path: Path) -> None:
    """A-51: in a raw folder the archived manifest names files as verify shows them; fixed names of
    .neurogrid in clear; the stored manifest_hash is kept; plain keeps the bytes."""
    parsed = parse_manifest(MANIFEST)
    copy, pseudonymized = archived_manifest(parsed, MANIFEST, plain=False)
    assert pseudonymized and b"Zhang" not in copy
    shown = json.loads(copy)
    assert [item["path"] for item in shown["files"]] == [
        ".neurogrid/vault/roles.yaml",
        show("Zhang San/rec_01.edf", plain=False).file,
    ]
    assert shown["files"][1]["path"].startswith("rec-") and shown["files"][1]["path"].endswith(".edf")
    assert shown["skipped"] == [{"kind": "link", "path": show("Zhang San/linked.edf", plain=False).file}]
    assert shown["excluded"] == parsed.manifest.excluded
    assert shown["manifest_hash"] == parsed.manifest.manifest_hash
    assert archived_manifest(parsed, MANIFEST, plain=True) == (MANIFEST, False)
    location = _vault(tmp_path / "data")
    result = _export(location, tmp_path / "pkg.zip")
    manifest = result.index.manifest
    assert manifest.pseudonymized and manifest.manifest_hash == parsed.manifest.manifest_hash
    assert manifest.source_sha256 == hashlib.sha256(MANIFEST).hexdigest()
    assert _members(tmp_path / "pkg.zip")["manifest.json"] == copy
    plain = _export(location, tmp_path / "plain.zip", plain=True)
    assert (
        not plain.index.manifest.pseudonymized
        and _members(tmp_path / "plain.zip")["manifest.json"] == MANIFEST
    )


def test_a_write_failure_after_the_event_keeps_the_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """As consent add: the log shows the attempt, --out is unchanged and no temporary file is left."""
    location = _vault(tmp_path / "data")
    out = tmp_path / "out" / "pkg.zip"
    out.parent.mkdir()
    out.write_bytes(b"earlier package")

    def broken(*_args: Any, **_kwargs: Any) -> Any:
        raise OSError("disk full")

    monkeypatch.setattr(export, "_stream_log", broken)
    with pytest.raises(InputError) as info:
        _export(location, out)
    assert info.value.message_key == "export.write_failed"
    last = json.loads(location.log.read_bytes().splitlines()[-1])
    assert last["action"] == "export" and last["seq"] == 3
    assert out.read_bytes() == b"earlier package" and sorted(p.name for p in out.parent.iterdir()) == [
        "pkg.zip"
    ]


def _unchanged(location: store.VaultLocation, out: Path, call: Any) -> NeuroGridError:
    before = location.log.read_bytes()
    with pytest.raises(NeuroGridError) as info:
        call()
    assert location.log.read_bytes() == before, "a refusal writes no event"
    assert not out.exists() and not any(out.parent.glob(f".{out.name}.*")), "a refusal writes nothing"
    return info.value


def test_refusals_write_nothing(tmp_path: Path) -> None:
    root = tmp_path / "data"
    location = _vault(root)
    out = tmp_path / "pkg.zip"
    in_vault = location.path / "pkg.zip"
    cases: list[tuple[Any, Path, str, dict[str, object]]] = [
        (lambda: _export(location, out, manifest=b"{}"), out, "manifest.invalid", MISSING_FORMAT),
        (lambda: _export(location, in_vault), in_vault, "export.out_in_vault", {}),
        (lambda: _export(location, tmp_path), out, "output.is_directory", {}),
    ]
    for call, target, key, params in cases:
        error = _unchanged(location, target, call)
        assert (error.message_key, error.params) == (key, params)
    blocker = tmp_path / "blocker"
    blocker.write_bytes(b"")
    error = _unchanged(location, out, lambda: _export(location, blocker / "pkg.zip"))
    assert error.message_key == "output.not_writable"
    roles = location.roles.read_bytes()
    location.roles.write_bytes(b"format_version: 1\nroles: [1]\n")
    error = _unchanged(location, out, lambda: _export(location, out))
    assert isinstance(error, ConfigError) and error.message_key == "roles.invalid"
    location.roles.unlink()
    error = _unchanged(location, out, lambda: _export(location, out))
    assert (error.message_key, error.params) == ("export.part_missing", {"part": "roles.yaml"})
    location.roles.mkdir()
    error = _unchanged(location, out, lambda: _export(location, out))
    assert (error.message_key, error.params) == ("export.not_regular", {"part": "roles.yaml"})
    location.roles.rmdir()
    location.roles.write_bytes(roles)
    for path in location.pia_files:
        path.unlink()
    error = _unchanged(location, out, lambda: _export(location, out))
    assert (error.message_key, error.params) == ("export.part_missing", {"part": "pia"})
    store.init_vault(location)  # the templates again: exported with a warning
    log = location.log.read_bytes()
    location.log.unlink()
    with pytest.raises(InputError) as missing:
        _export(location, out)
    assert (missing.value.message_key, missing.value.params) == (
        "export.part_missing",
        {"part": "access.jsonl"},
    )
    assert not out.exists()
    location.log.write_bytes(log)
    result = _export(location, out)
    assert result.warnings == ("pia_unedited",)
    with pytest.raises(InputError) as absent:
        _export(store.locate(tmp_path / "nothing", store.DEFAULT_VAULT_PATH), tmp_path / "x.zip")
    assert absent.value.message_key == "vault.not_found"


def test_a_damaged_log_is_refused_and_new_folders_are_removed(tmp_path: Path) -> None:
    """The event cannot be appended (no readable entry at the end of the log): errors.vault.log_damaged, and
    the folders created for --out are removed again; a log that is a folder is no regular file."""
    location = _vault(tmp_path / "data")
    location.log.write_bytes(b"not an entry\n")
    out = tmp_path / "new" / "deeper" / "pkg.zip"
    with pytest.raises(InputError) as info:
        _export(location, out)
    assert info.value.message_key == "vault.log_damaged" and not (tmp_path / "new").exists()
    assert location.log.read_bytes() == b"not an entry\n"
    location.log.unlink()
    location.log.mkdir()
    with pytest.raises(InputError) as folder:
        _export(location, out)
    assert (folder.value.message_key, folder.value.params) == ("export.not_regular", {"part": "access.jsonl"})


def test_a_log_shorter_than_its_snapshot_is_a_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only NeuroGrid appends after S; a log another program cut after the event cannot be packed: the export
    fails after the event (errors.export.write_failed), the new folders go, the event stays."""
    location = _vault(tmp_path / "data")
    real = export._append_event

    def longer(*args: Any) -> tuple[Any, int, int]:
        event, fd, size = real(*args)
        return event, fd, size + 10

    monkeypatch.setattr(export, "_append_event", longer)
    out = tmp_path / "new" / "pkg.zip"
    with pytest.raises(InputError) as info:
        _export(location, out)
    assert info.value.message_key == "export.write_failed" and not (tmp_path / "new").exists()
    assert json.loads(location.log.read_bytes().splitlines()[-1])["action"] == "export"


def test_the_reports_come_from_the_pipeline_identified_and_each_once(tmp_path: Path) -> None:
    location = _vault(tmp_path / "data")
    for reports in ((), (*REPORTS, REPORTS[0]), (ExportReport("notes.html", "en", "html", b""),)):
        with pytest.raises(ValueError):
            _export(location, tmp_path / "pkg.zip", reports=reports)
    assert not (tmp_path / "pkg.zip").exists()


def test_only_one_pia_language_is_enough(tmp_path: Path) -> None:
    location = _vault(tmp_path / "data")
    location.pia_files[0].unlink()
    result = _export(location, tmp_path / "pkg.zip")
    assert [part.file for part in result.index.parts if part.part == "pia"] == ["pia/pia.en.md"]


def test_an_empty_role_register_and_a_broken_chain_are_exported_and_named(tmp_path: Path) -> None:
    """A-96: a broken chain is exported (index.json records it) and warned, never refused."""
    location = _vault(tmp_path / "data")
    location.roles.write_bytes(store.ROLES_TEMPLATE)
    lines = location.log.read_bytes().splitlines(keepends=True)
    lines[0] = lines[0].replace(b'"check"', b'"read"')  # the first entry changed: its hash no longer fits
    location.log.write_bytes(b"".join(lines))
    result = _export(location, tmp_path / "pkg.zip")
    assert result.warnings == ("roles_empty", "chain_broken")
    log = result.index.access_log
    assert not log.intact and log.deviations == 1 and log.events == 3 and log.head == result.event.hash


def test_links_in_the_vault_are_never_followed(tmp_path: Path) -> None:
    """P6 link rule: a link at the pia folder or the vault folder is errors.vault.link {part}; nothing is
    written, no event."""
    location = _vault(tmp_path / "data")
    elsewhere = tmp_path / "elsewhere"
    shutil.move(str(location.pia_folder), str(elsewhere))
    dir_link(location.pia_folder, elsewhere)
    before = location.log.read_bytes()
    with pytest.raises(UnsafePathError) as info:
        _export(location, tmp_path / "pkg.zip")
    assert (info.value.message_key, info.value.params) == ("vault.link", {"part": "pia"})
    assert location.log.read_bytes() == before and not (tmp_path / "pkg.zip").exists()


def test_a_file_link_at_a_part_is_refused(tmp_path: Path) -> None:
    location = _vault(tmp_path / "data")
    real = tmp_path / "roles-elsewhere.yaml"
    real.write_bytes(ROLES)
    location.roles.unlink()
    try:
        location.roles.symlink_to(real)
    except OSError:
        pytest.skip("file symlinks not permitted on this system")
    with pytest.raises(UnsafePathError) as info:
        _export(location, tmp_path / "pkg.zip")
    assert info.value.params == {"part": "roles.yaml"}


def test_a_locked_vault_is_exit_2_without_event(tmp_path: Path) -> None:
    location = _vault(tmp_path / "data")
    before = location.log.read_bytes()
    with lock_held(location.lock), pytest.raises(VaultLocked):
        _export(location, tmp_path / "pkg.zip", timeout_s=0.2)
    assert location.log.read_bytes() == before and not (tmp_path / "pkg.zip").exists()


def test_read_regular_never_reads_beyond_the_limit(tmp_path: Path) -> None:
    path = tmp_path / "big.html"
    path.write_bytes(b"x" * 11)
    assert (
        export.read_regular(
            path, part="report", max_bytes=11, link=lambda: InputError("x"), too_large=lambda: InputError("y")
        )
        == b"x" * 11
    )
    with pytest.raises(InputError) as info:
        export.read_regular(
            path,
            part="report",
            max_bytes=10,
            link=lambda: InputError("x"),
            too_large=lambda: ManifestError("manifest.too_large", limit=10),
        )
    assert info.value.message_key == "manifest.too_large"
    with pytest.raises(InputError) as missing:
        export.read_regular(
            tmp_path / "none",
            part="report",
            max_bytes=10,
            link=lambda: InputError("x"),
            too_large=lambda: InputError("y"),
        )
    assert missing.value.params == {"part": "report"}


def test_the_index_schema_is_the_model(tmp_path: Path) -> None:
    location = _vault(tmp_path / "data")
    _export(location, tmp_path / "pkg.zip")
    schema = json.loads(
        (Path(store.__file__).parent.parent / "schemas" / "export_index.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert schema["title"] == "ExportIndex" and set(schema["required"]) >= {
        "disclaimer",
        "tool",
        "parts",
        "manifest",
        "access_log",
    }
    index = json.loads(_members(tmp_path / "pkg.zip")["index.json"])
    assert set(index) == set(schema["properties"]) and export.INDEX_MEMBER == "index.json"
