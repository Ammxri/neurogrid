"""M13 provenance units (NG-F10, A-22, A-82): inventory, streaming hashes, manifest build, hash, reader and
comparison in the kernel; documentation sources, exclusions and display on the NeuroGrid side."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path, PurePosixPath

import pytest

from conftest import dir_link  # type: ignore[import-not-found]
from neurogrid.io import provenance as io_provenance
from neurogrid.io.discover import pseudonym
from neurogrid.io.provenance import (
    KNOWN_CONTROL_FILES,
    ProvenanceState,
    Sources,
    comparison_exclusions,
    generated_by,
    inside,
    load_processing_steps,
    load_provenance_file,
    load_sources,
    show,
    vault_exclusions,
)
from neurogrid.kernel import canonical
from neurogrid.kernel import provenance as kp
from neurogrid.kernel.errors import ConfigError, UnsafePathError
from neurogrid.kernel.provenance import (
    DEFAULT_MANIFEST,
    Exclusions,
    ManifestError,
    ManifestStatus,
    ProcessingStep,
    SoftwareEntry,
    build_manifest,
    compare,
    escape_name,
    inventory,
    manifest_bytes,
    manifest_hash,
    name_bytes,
    parse_manifest,
    read_manifest,
    safe_relative,
)

WINDOWS = sys.platform == "win32"


def _tree(root: Path) -> dict[str, bytes]:
    files = {
        "sub-01/rec.edf": b"\x00" * 300,
        "sub-01/rec.json": b"{}\n",
        "README": b"readme\n",
        ".bidsignore": b"*.tmp\n",
        ".DS_Store": b"os file",
        "derivatives/x/out.txt": b"derived",
        "code/run.py": b"print(1)\n",
        "sourcedata/raw.bin": b"raw",
        ".neurogrid/neurogrid.toml": b"[check]\n",
        ".neurogrid/splits.tsv": b"recording\tsplit\n",
        ".neurogrid/evidence.yaml": b"format_version: 1\n",
        ".neurogrid/processing_steps.json": b"[]\n",
        ".neurogrid/vault/access.jsonl": b'{"x": 1}\n',
        ".neurogrid/vault/access.jsonl.lock": b"",
        ".neurogrid/manifest.json": b"old manifest",  # the default location (A-82): left out
        "manifest.json": b"a file of the dataset",  # at the root it is an ordinary file: covered
        "张三/记录.edf": b"chinese name",
    }
    for relative, data in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return files


def _exclusions(*extra: str) -> Exclusions:
    return Exclusions.of([DEFAULT_MANIFEST.as_posix(), *extra])


VAULT = [".neurogrid/vault/access.jsonl", ".neurogrid/vault/access.jsonl.lock"]


# --- inventory and build -------------------------------------------------------------------------------


def test_build_covers_everything_but_the_manifest_and_the_vault_log(tmp_path: Path) -> None:
    """KONZEPT 2.5: everything in .neurogrid/ is covered except manifest.json and vault/access.jsonl."""
    files = _tree(tmp_path)
    assert DEFAULT_MANIFEST == PurePosixPath(".neurogrid", "manifest.json")
    built = build_manifest(tmp_path, _exclusions(*VAULT), excluded=VAULT)
    assert built.manifest is not None and not built.unreadable
    listed = {item.path: item for item in built.manifest.files}
    expected = sorted(set(files) - {".neurogrid/manifest.json", *VAULT})
    assert [item.path for item in built.manifest.files] == expected  # code-point order of POSIX paths
    for path in expected:
        assert listed[path].sha256 == hashlib.sha256(files[path]).hexdigest()
        assert listed[path].size == len(files[path])
    assert built.manifest.excluded == VAULT
    assert built.total_bytes == sum(len(files[path]) for path in expected)
    for name in (
        ".neurogrid/neurogrid.toml",
        ".neurogrid/splits.tsv",
        ".neurogrid/evidence.yaml",
        ".neurogrid/processing_steps.json",
        ".bidsignore",
        "derivatives/x/out.txt",
        "manifest.json",
    ):
        assert name in listed


def test_custom_vault_path_and_output_inside_the_dataset_are_excluded(tmp_path: Path) -> None:
    _tree(tmp_path)
    (tmp_path / "secure").mkdir()
    (tmp_path / "secure" / "access.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "m.json").write_text("{}", encoding="utf-8")
    recorded = vault_exclusions(tmp_path, tmp_path, "secure")
    assert recorded == ["secure/access.jsonl", "secure/access.jsonl.lock"]
    own = inside(tmp_path, tmp_path / "out" / "m.json")
    assert own == "out/m.json"
    built = build_manifest(tmp_path, _exclusions(*recorded, own), excluded=recorded)
    assert built.manifest is not None
    paths = {item.path for item in built.manifest.files}
    assert "secure/access.jsonl" not in paths and "out/m.json" not in paths
    assert ".neurogrid/vault/access.jsonl" in paths  # not the vault of this configuration
    assert vault_exclusions(tmp_path / "ds", tmp_path, "vault") == []  # vault outside the dataset
    assert vault_exclusions(tmp_path, tmp_path, ".neurogrid/vault") == VAULT


def test_manifest_hash_is_over_the_canonical_content(tmp_path: Path) -> None:
    _tree(tmp_path)
    step = ProcessingStep(step="filter", tool="ExampleTool", version="1.0", parameters={"low": 0.1})
    software = [SoftwareEntry(name="ExampleTool", version="1.0", source="processing_steps")]
    built = build_manifest(tmp_path, _exclusions(), processing_steps=[step], software=software)
    assert built.manifest is not None
    data = json.loads(manifest_bytes(built.manifest))
    without = {key: value for key, value in data.items() if key != "manifest_hash"}
    assert data["manifest_hash"] == canonical.sha256_of(without) == manifest_hash(data)
    # every field enters the hash
    for mutate in (
        lambda d: d["files"][0].update(path="other"),
        lambda d: d["files"][0].update(size=d["files"][0]["size"] + 1),
        lambda d: d["files"][0].update(sha256="0" * 64),
        lambda d: d["processing_steps"][0]["parameters"].update(low=0.2),
        lambda d: d["software"][0].update(version="2.0"),
        lambda d: d["excluded"].append("x/access.jsonl"),
    ):
        changed = json.loads(manifest_bytes(built.manifest))
        mutate(changed)
        assert manifest_hash(changed) != data["manifest_hash"]
    # indentation and key order of the file do not matter
    reordered = json.dumps(dict(reversed(list(data.items()))), indent=7).encode("utf-8")
    assert parse_manifest(reordered).hash_ok


def test_two_builds_are_byte_identical_and_hold_no_host_data(tmp_path: Path) -> None:
    _tree(tmp_path)
    first = build_manifest(tmp_path, _exclusions()).manifest
    second = build_manifest(tmp_path, _exclusions(), threads=1).manifest
    assert first is not None and second is not None
    text = manifest_bytes(first)
    assert text == manifest_bytes(second) and text.endswith(b"\n") and b"\r\n" not in text
    decoded = text.decode("utf-8")
    assert str(tmp_path) not in decoded and str(Path.home()) not in decoded
    assert (
        os.environ.get("USERNAME", "\x00") not in decoded
        and os.environ.get("COMPUTERNAME", "\x00") not in decoded
    )
    assert "张三/记录.edf" in decoded  # manifest.json holds the real relative paths by design (A-51)


def test_links_are_reported_and_never_followed(tmp_path: Path) -> None:
    root = tmp_path / "ds"
    root.mkdir()
    (root / "a.txt").write_text("a", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("distinctive outside content", encoding="utf-8")
    dir_link(root / "linked", outside)
    (root / ".neurogrid").mkdir()
    dir_link(root / ".neurogrid" / "vault", outside)
    found = inventory(root)
    assert [entry.relative for entry in found.files] == ["a.txt"]
    assert [(entry.path, entry.kind) for entry in found.skipped] == [
        (".neurogrid/vault", "link"),
        ("linked", "link"),
    ]
    try:
        (root / "file_link.txt").symlink_to(outside / "secret.txt")
    except OSError:
        return  # file symlinks need extra rights on Windows; the junctions above cover links
    assert ("file_link.txt", "link") in [(entry.path, entry.kind) for entry in inventory(root).skipped]


@pytest.mark.skipif(WINDOWS, reason="FIFOs are POSIX special files")
def test_special_files_are_skipped_without_blocking(tmp_path: Path) -> None:
    os.mkfifo(tmp_path / "pipe")
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    built = build_manifest(tmp_path, _exclusions())
    assert built.manifest is not None
    assert [(entry.path, entry.kind) for entry in built.manifest.skipped] == [("pipe", "special")]


def test_a_file_swapped_after_listing_is_not_hashed(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("first", encoding="utf-8")
    entry = inventory(tmp_path).files[0]
    (tmp_path / "a.txt").rename(tmp_path / "kept.txt")  # the listed file lives on under another name
    (tmp_path / "a.txt").write_text("other file", encoding="utf-8")  # a new file under the listed name
    assert kp.hash_file(entry) is None
    unknown = kp.FileEntry(entry.relative, entry.path, 99, 0, 0)  # no inode to compare: hashed as it is now
    assert kp.hash_file(unknown) == (hashlib.sha256(b"other file").hexdigest(), 10)


def test_unreadable_files_stop_the_manifest(tmp_path: Path) -> None:
    (tmp_path / "a.bin").write_bytes(b"x" * 100)
    (tmp_path / "b.bin").write_bytes(b"y")
    if WINDOWS:
        import msvcrt

        descriptor = os.open(tmp_path / "a.bin", os.O_RDWR | os.O_BINARY)
        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 100)
        try:
            built = build_manifest(tmp_path, _exclusions())
        finally:
            os.lseek(descriptor, 0, 0)
            msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 100)
            os.close(descriptor)
    else:
        if os.geteuid() == 0:
            pytest.skip("root can read every file")
        (tmp_path / "a.bin").chmod(0)
        try:
            built = build_manifest(tmp_path, _exclusions())
        finally:
            (tmp_path / "a.bin").chmod(0o644)
    assert built.manifest is None and built.unreadable == ("a.bin",)


def test_names_the_path_check_refuses_are_skipped_and_compared(tmp_path: Path) -> None:
    if WINDOWS:
        prefix = "\\\\?\\"
        (tmp_path / "ok.txt").write_text("ok", encoding="utf-8")
        with Path(prefix + str(tmp_path / "trail.")).open("wb") as handle:
            handle.write(b"z")
        Path(prefix + str(tmp_path / "aux")).mkdir()
        expected = {"aux", "trail."}
    else:
        (tmp_path / "ok.txt").write_text("ok", encoding="utf-8")
        (tmp_path / "a:b.edf").write_bytes(b"1")
        (tmp_path / "aux.txt").write_bytes(b"2")
        (tmp_path / "back\\slash").write_bytes(b"3")
        (Path(os.fsdecode(bytes(tmp_path) + b"/\xff\xfe.edf"))).write_bytes(b"4")
        expected = {"a%3Ab.edf", "aux.txt", "back%5Cslash", "%FF%FE.edf"}
    try:
        built = build_manifest(tmp_path, _exclusions())
        assert built.manifest is not None
        assert [item.path for item in built.manifest.files] == ["ok.txt"]
        assert {entry.path for entry in built.manifest.skipped if entry.kind == "unsafe_name"} == expected
        parsed = parse_manifest(manifest_bytes(built.manifest))  # the reader accepts what the builder wrote
        assert parsed.hash_ok
        assert compare(tmp_path, parsed.manifest, _exclusions()).deviations == ()
    finally:
        if WINDOWS:
            Path("\\\\?\\" + str(tmp_path / "trail.")).unlink()
            Path("\\\\?\\" + str(tmp_path / "aux")).rmdir()


def test_escaped_names_round_trip() -> None:
    for name in ("a:b.edf", "名字.txt", "100%.txt", "x\\y"):
        escaped = escape_name(name)
        assert all(ord(char) < 128 for char in escaped) and "\\" not in escaped
        assert name_bytes(escaped, "unsafe_name") == os.fsencode(name)
    assert name_bytes("plain/path.edf") == b"plain/path.edf"
    assert safe_relative("a/b.edf") and not safe_relative("a\\b") and not safe_relative("aux.txt")
    assert not safe_relative("\udcff.edf") and not safe_relative("x" * 1100)


def test_streaming_reads_chunks_and_threads_do_not_change_the_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for index in range(6):
        (tmp_path / f"f{index}.bin").write_bytes(os.urandom(3000 + index))
    monkeypatch.setattr(kp, "CHUNK_BYTES", 512)
    sizes: list[int] = []
    real_read = os.read

    def spy(descriptor: int, size: int) -> bytes:
        sizes.append(size)
        return real_read(descriptor, size)

    monkeypatch.setattr(kp.os, "read", spy)
    entries = inventory(tmp_path).files
    sequential = kp.hash_files(entries, threads=1)
    parallel = kp.hash_files(entries, threads=4)
    assert sequential == parallel
    assert sizes and max(sizes) == 512
    for entry, digest in zip(entries, sequential, strict=True):
        assert digest == (hashlib.sha256(entry.path.read_bytes()).hexdigest(), entry.size)


def test_exclusions_ignore_case_on_windows_only() -> None:
    exclusions = Exclusions.of(["Manifest.json"], ["Results/run-1"])
    assert exclusions.covers("Manifest.json") and exclusions.covers("Results/run-1/x/y")
    assert not exclusions.covers("Results/run-10")
    assert exclusions.covers("manifest.json") is WINDOWS


# --- compare -------------------------------------------------------------------------------------------


def _manifest(root: Path) -> kp.Manifest:
    built = build_manifest(root, _exclusions())
    assert built.manifest is not None
    return built.manifest


def test_compare_finds_every_kind_of_deviation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "ds"
    root.mkdir()
    for name in ("same.txt", "content.txt", "size.txt", "gone.txt", "to_link"):
        (root / name).write_text(name, encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    dir_link(root / "old_link", outside)
    manifest = _manifest(root)
    assert compare(root, manifest, _exclusions()).deviations == ()
    (root / "content.txt").write_text("CONTENT.TXT"[: len("content.txt")], encoding="utf-8")
    (root / "size.txt").write_text("longer content", encoding="utf-8")
    (root / "gone.txt").unlink()
    (root / "new.txt").write_text("new", encoding="utf-8")
    (root / "to_link").unlink()
    dir_link(root / "to_link", outside)
    if WINDOWS:
        Path(root / "old_link").rmdir()  # removes a junction or directory link, not its target
    else:
        (root / "old_link").unlink()
    dir_link(root / "new_link", outside)
    hashed: list[str] = []
    real = kp.hash_file

    def counting(entry: kp.FileEntry) -> tuple[str, int] | None:
        hashed.append(entry.relative)
        return real(entry)

    monkeypatch.setattr(kp, "hash_file", counting)
    result = compare(root, manifest, _exclusions(), threads=1)
    kinds = {deviation.path: deviation.kind for deviation in result.deviations}
    assert kinds == {
        "content.txt": "changed",
        "size.txt": "changed",
        "gone.txt": "missing",
        "new.txt": "new",
        "to_link": "skipped_changed",
        "old_link": "missing",
        "new_link": "new",
    }
    assert "size.txt" not in hashed and sorted(hashed) == ["content.txt", "same.txt"]  # sizes first
    by_path = {deviation.path: deviation for deviation in result.deviations}
    assert (by_path["size.txt"].size_manifest, by_path["size.txt"].size_now) == (8, 14)
    assert (by_path["to_link"].before, by_path["to_link"].now) == ("file", "link")
    assert by_path["new_link"].now == "link" and by_path["old_link"].before == "link"
    assert result.files == 5 and result.count("changed") == 2


def test_compare_reports_files_it_cannot_read(tmp_path: Path) -> None:
    (tmp_path / "a.bin").write_bytes(b"x" * 100)
    manifest = _manifest(tmp_path)
    if not WINDOWS:
        if os.geteuid() == 0:
            pytest.skip("root can read every file")
        (tmp_path / "a.bin").chmod(0)
        try:
            result = compare(tmp_path, manifest, _exclusions())
        finally:
            (tmp_path / "a.bin").chmod(0o644)
    else:
        import msvcrt

        descriptor = os.open(tmp_path / "a.bin", os.O_RDWR | os.O_BINARY)
        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 100)
        try:
            result = compare(tmp_path, manifest, _exclusions())
        finally:
            os.lseek(descriptor, 0, 0)
            msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 100)
            os.close(descriptor)
    assert [(d.path, d.kind) for d in result.deviations] == [("a.bin", "unreadable")]


def test_compare_marks_files_below_an_unlistable_folder_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "a.txt").write_text("a", encoding="utf-8")
    manifest = _manifest(tmp_path)
    real_walk = os.walk

    def walk(top: str | os.PathLike[str], **kwargs: object):  # type: ignore[no-untyped-def]
        for dirpath, dirnames, filenames in real_walk(top, **kwargs):  # type: ignore[call-overload]
            if Path(dirpath).name == "sub":
                kwargs["onerror"](PermissionError(13, "denied", dirpath))  # type: ignore[operator]
                continue
            yield dirpath, dirnames, filenames

    monkeypatch.setattr(kp.os, "walk", walk)
    result = compare(tmp_path, manifest, _exclusions())
    assert [(d.path, d.kind) for d in result.deviations] == [("sub/a.txt", "unreadable")]
    built = build_manifest(tmp_path, _exclusions())
    assert built.manifest is None and built.unreadable == ("sub",)


def test_excluded_paths_are_not_compared(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    manifest = _manifest(tmp_path)
    (tmp_path / ".neurogrid").mkdir()
    (tmp_path / ".neurogrid" / "manifest.json").write_text("{}", encoding="utf-8")  # the default location
    (tmp_path / "run-x").mkdir()
    (tmp_path / "run-x" / "tmp.json").write_text("{}", encoding="utf-8")
    exclusions = comparison_exclusions(tmp_path, manifest, None, tmp_path / "run-x")
    assert compare(tmp_path, manifest, exclusions).deviations == ()
    assert [d.path for d in compare(tmp_path, manifest, _exclusions()).deviations] == ["run-x/tmp.json"]
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")  # at the root: a file like any other
    (tmp_path / ".neurogrid" / "splits.tsv").write_text("recording\tsplit\n", encoding="utf-8")
    found = [(d.path, d.kind) for d in compare(tmp_path, manifest, exclusions).deviations]
    assert found == [(".neurogrid/splits.tsv", "new"), ("manifest.json", "new")]
    # a manifest read with --manifest from inside the dataset is left out as well
    exclusions = comparison_exclusions(tmp_path, manifest, tmp_path / "manifest.json")
    assert [d.path for d in compare(tmp_path, manifest, exclusions).deviations] == [
        ".neurogrid/splits.tsv",
        "run-x/tmp.json",
    ]


# --- read ----------------------------------------------------------------------------------------------


def _valid(tmp_path: Path) -> dict[str, object]:
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    data: dict[str, object] = json.loads(manifest_bytes(_manifest(tmp_path)))
    return data


def _rehashed(data: dict[str, object]) -> bytes:
    data = dict(data)
    data["manifest_hash"] = manifest_hash(data)
    return json.dumps(data).encode("utf-8")


@pytest.mark.parametrize(
    ("change", "key"),
    [
        (lambda d: d.update(format_version="2"), "manifest.unsupported_version"),
        (lambda d: d.pop("files"), "manifest.invalid"),
        (lambda d: d.update(extra=1), "manifest.invalid"),
        (lambda d: d["files"][0].update(sha256="ABC"), "manifest.invalid"),
        (lambda d: d["files"][0].update(size=-1), "manifest.invalid"),
        (lambda d: d["files"][0].update(size=True), "manifest.invalid"),
        (lambda d: d["files"][0].update(size="1"), "manifest.invalid"),
        (lambda d: d["files"].append(dict(d["files"][0])), "manifest.duplicate_path"),
        (lambda d: d["skipped"].append({"path": "a.txt", "kind": "link"}), "manifest.duplicate_path"),
        (lambda d: d["skipped"].append({"path": "x\\y", "kind": "unsafe_name"}), "manifest.unsafe_path"),
        (lambda d: d["skipped"].append({"path": "x%zz", "kind": "unsafe_name"}), "manifest.unsafe_path"),
        (lambda d: d["skipped"].append({"path": "x", "kind": "socket"}), "manifest.invalid"),
        (lambda d: d["excluded"].append("sub-01/rec.edf"), "manifest.excluded_invalid"),
        (lambda d: d["excluded"].append("../access.jsonl"), "manifest.unsafe_path"),
    ],
)
def test_invalid_manifest_content_is_refused(tmp_path: Path, change: object, key: str) -> None:
    data = _valid(tmp_path)
    change(data)  # type: ignore[operator]
    with pytest.raises(ManifestError) as info:
        parse_manifest(_rehashed(data))
    assert info.value.message_key == key


@pytest.mark.parametrize(
    "unsafe",
    ["../a", "/a", "C:/a", "//srv/share/a", "a:stream", "CON.txt", "a\x01b", "a\\b", "./a", "a/", "a."],
)
def test_unsafe_paths_in_the_manifest_are_refused(tmp_path: Path, unsafe: str) -> None:
    data = _valid(tmp_path)
    data["files"][0]["path"] = unsafe  # type: ignore[index]
    with pytest.raises(ManifestError) as info:
        parse_manifest(_rehashed(data))
    assert info.value.message_key == "manifest.unsafe_path"
    assert unsafe not in str(info.value.params)  # the error names the field, never the path


@pytest.mark.parametrize(
    "raw",
    [
        b"{not json",
        b'{"a": NaN}',
        b'{"a": Infinity}',
        b'{"a": 1e999}',
        b'{"a": 1, "a": 2}',
        b"[]",
        b"[" * 100_000 + b"]" * 100_000,
    ],
    ids=["syntax", "nan", "infinity", "overflow", "duplicate_key", "not_an_object", "deep"],
)
def test_manifest_that_is_no_clean_json_is_refused(raw: bytes) -> None:
    with pytest.raises(ManifestError) as info:
        parse_manifest(raw)
    assert info.value.message_key == "manifest.invalid"


def test_encoding_size_limit_and_byte_order_mark(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = _rehashed(_valid(tmp_path))
    assert parse_manifest(b"\xef\xbb\xbf" + data).hash_ok
    with pytest.raises(ManifestError) as info:
        parse_manifest(b"\xff\xfe\x00")
    assert info.value.message_key == "manifest.encoding"
    path = tmp_path / "m.json"
    path.write_bytes(data)
    assert read_manifest(path).hash_ok
    monkeypatch.setattr(kp, "MAX_MANIFEST_BYTES", 10)
    with pytest.raises(ManifestError) as info:
        read_manifest(path)
    assert info.value.message_key == "manifest.too_large"
    with pytest.raises(ManifestError) as info:
        read_manifest(tmp_path)  # a folder cannot be read as a manifest
    assert info.value.message_key == "manifest.unreadable"


def test_a_changed_hash_is_reported_not_refused(tmp_path: Path) -> None:
    data = _valid(tmp_path)
    data["files"][0]["size"] = 99  # type: ignore[index]
    parsed = parse_manifest(json.dumps(data).encode("utf-8"))
    assert not parsed.hash_ok


# --- documentation sources -----------------------------------------------------------------------------

PROVENANCE = """processing_steps:
  - step: filter
    tool: ExampleTool
    version: "1.2"
    parameters: {low: 0.5, notch: [50, 100], label: band}
software:
  - name: Other
    version: "3"
"""


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_provenance_file_is_read_strictly(tmp_path: Path) -> None:
    assert load_provenance_file(tmp_path) is None
    _write(tmp_path, ".neurogrid/provenance.yaml", PROVENANCE)
    parsed = load_provenance_file(tmp_path)
    assert parsed is not None and parsed.processing_steps is not None
    assert parsed.processing_steps[0].parameters == {"low": 0.5, "notch": [50, 100], "label": "band"}
    _write(tmp_path, ".neurogrid/provenance.yaml", "processing_steps: []\n")
    sources = load_sources(tmp_path, is_bids=False)
    assert sources.no_processing_declared and sources.steps == []


@pytest.mark.parametrize(
    ("text", "key"),
    [
        ("a: &x 1\nb: *x\n", "provenance.yaml_alias"),
        ("software: []\nsoftware: []\n", "provenance.yaml_duplicate_key"),
        ("software: [\n", "provenance.yaml_syntax"),
        ("software:" + " [" * 40 + " ]" * 40 + "\n", "provenance.yaml_too_deep"),
        ("unknown: 1\n", "provenance.invalid"),
        ("- a\n", "provenance.invalid"),
        ("processing_steps:\n  - {step: a, tool: b, version: 1.2}\n", "provenance.invalid"),
        (
            "processing_steps:\n  - {step: a, tool: b, version: '1', parameters: {d: 2026-01-01}}\n",
            "provenance.invalid",
        ),
        (
            "processing_steps:\n  - {step: a, tool: b, version: '1', parameters: {d: .nan}}\n",
            "provenance.invalid",
        ),
        ("processing_steps:\n  - {step: a, tool: b, version: '1', input_hash: abc}\n", "provenance.invalid"),
        ("software:\n  - {name: a}\n", "provenance.invalid"),
    ],
)
def test_invalid_provenance_file_is_a_tool_error(tmp_path: Path, text: str, key: str) -> None:
    _write(tmp_path, ".neurogrid/provenance.yaml", text)
    with pytest.raises(ConfigError) as info:
        load_provenance_file(tmp_path)
    assert info.value.message_key == key


def test_provenance_file_limits_encoding_and_links(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = _write(tmp_path, ".neurogrid/provenance.yaml", "software: []\n")
    path.write_bytes(b"\xff\xfe")
    with pytest.raises(ConfigError) as info:
        load_provenance_file(tmp_path)
    assert info.value.message_key == "provenance.encoding"
    monkeypatch.setattr(io_provenance, "MAX_YAML_BYTES", 4)
    path.write_text("software: []\n", encoding="utf-8")
    with pytest.raises(ConfigError) as info:
        load_provenance_file(tmp_path)
    assert info.value.message_key == "provenance.yaml_too_large"
    path.unlink()
    path.mkdir()
    with pytest.raises(ConfigError) as info:
        load_provenance_file(tmp_path)
    assert info.value.message_key == "provenance.invalid"
    other = tmp_path / "other"
    other.mkdir()
    _write(other, "x/provenance.yaml", "software: []\n")
    ds = tmp_path / "ds"
    ds.mkdir()
    dir_link(ds / ".neurogrid", other / "x")
    with pytest.raises(UnsafePathError):  # a linked .neurogrid is not followed (A-66): exit 2
        load_provenance_file(ds)


def test_processing_steps_json_problems_are_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert load_processing_steps(tmp_path) == ([], None)
    steps = [ProcessingStep(step="convert_to_bids", tool="neurogrid", version="0.1", input_hash="a" * 64)]
    path = tmp_path / ".neurogrid" / "processing_steps.json"
    path.parent.mkdir()
    path.write_bytes(canonical.dumps(steps))
    assert load_processing_steps(tmp_path) == (steps, None)
    for content, problem in (
        (b"{", "json"),
        (b'{"a": 1}', "schema"),
        (b'[{"step": 1}]', "schema"),
        (b'[{"step": "a", "tool": "b", "version": "1", "x": 1}]', "schema"),
        (b"[NaN]", "json"),
        (b"\xff", "json"),
    ):
        path.write_bytes(content)
        assert load_processing_steps(tmp_path) == ([], problem)
    path.write_bytes(b"[]")
    monkeypatch.setattr(io_provenance, "MAX_STEPS_BYTES", 1)
    assert load_processing_steps(tmp_path) == ([], "too_large")
    path.unlink()
    path.mkdir()
    assert load_processing_steps(tmp_path) == ([], "not_a_file")
    ds = tmp_path / "ds"
    ds.mkdir()
    dir_link(ds / ".neurogrid", tmp_path / ".neurogrid")
    assert load_processing_steps(ds) == ([], "link")


def test_generated_by_needs_name_and_version(tmp_path: Path) -> None:
    description = {
        "Name": "x",
        "GeneratedBy": [
            {"Name": "Pipeline", "Version": "2.0"},
            {"Name": "NoVersion"},
            {"Name": "Ctrl\x07Name", "Version": "1"},
            {"Name": "x" * 300, "Version": "1"},
            "text",
        ],
    }
    _write(tmp_path, "dataset_description.json", json.dumps(description))
    assert generated_by(tmp_path, is_bids=True) == [("CtrlName", "1"), ("Pipeline", "2.0")]
    assert generated_by(tmp_path, is_bids=False) == []
    _write(tmp_path, "dataset_description.json", "{broken")
    assert generated_by(tmp_path, is_bids=True) == []
    _write(tmp_path, "dataset_description.json", json.dumps({"GeneratedBy": {"Name": "a", "Version": "1"}}))
    assert generated_by(tmp_path, is_bids=True) == []


def test_software_versions_are_collected_and_sorted() -> None:
    steps = (
        ProcessingStep(step="a", tool="Zeta", version="1"),
        ProcessingStep(step="b", tool="Alpha", version=" 2 "),
        ProcessingStep(step="c", tool="", version="3"),
    )
    sources = Sources(None, steps, None, (("Pipeline", "9"),))
    software = sources.software("0.1.0")
    assert [(s.name, s.version, s.source) for s in software] == [
        ("Alpha", "2", "processing_steps"),
        ("Pipeline", "9", "bids"),
        ("Zeta", "1", "processing_steps"),
        ("neurogrid", "0.1.0", "manifest"),
    ]
    assert len(sources.documented_software) == 3 and sources.incomplete_steps == 1
    assert sources.source_names() == ["processing_steps", "bids"]


# --- display and state -------------------------------------------------------------------------------


def test_display_follows_a51_and_x14() -> None:
    raw = show("Zhang_San/rec 1.EDF", plain=False)
    assert raw.object.startswith("rec-") and raw.file == raw.object + ".edf"
    assert raw.identity == ("Zhang_San/rec 1.EDF", raw.object, raw.file)
    assert show("Zhang_San/rec 1.EDF", plain=True).object == "Zhang_San/rec 1.EDF"
    for name in KNOWN_CONTROL_FILES:
        assert show(name, plain=False).object == name
    assert (
        show("notes.张三", plain=False).file == show("notes.张三", plain=False).object
    )  # odd suffix left out
    assert raw.object == pseudonym(PurePosixPath("Zhang_San/rec 1.EDF"))  # the same ID as in M01 findings


def test_state_reports_status_without_comparing(tmp_path: Path) -> None:
    def state(**kwargs: object) -> ProvenanceState:
        options = {
            "single_file": False,
            "is_bids": False,
            "show_paths": False,
            "manifest_path": None,
            "work": None,
        }
        options.update(kwargs)
        return ProvenanceState(tmp_path, **options)  # type: ignore[arg-type]

    assert state(single_file=True).info().status is ManifestStatus.NOT_APPLICABLE
    assert state().info().status is ManifestStatus.MISSING
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    built = build_manifest(tmp_path, _exclusions())
    assert built.manifest is not None
    (tmp_path / "manifest.json").write_bytes(manifest_bytes(built.manifest))
    root_only = state()  # a manifest.json at the root is not the default location (A-82)
    assert root_only.info().status is ManifestStatus.MISSING and root_only.read().problem == "missing"
    (tmp_path / "manifest.json").unlink()
    location = tmp_path / ".neurogrid" / "manifest.json"
    location.parent.mkdir()
    location.write_bytes(manifest_bytes(built.manifest))
    fresh = state()
    assert fresh.read().location == location.resolve()
    info = fresh.info()
    assert info.status is ManifestStatus.NOT_VERIFIED and info.sha256 == built.manifest.manifest_hash
    assert fresh.comparison() is not None and fresh.info().status is ManifestStatus.MATCHES
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    later = state()
    later.comparison()
    assert later.info().status is ManifestStatus.DIFFERS and later.info().new == 1
    location.write_text("[]", encoding="utf-8")
    broken = state()
    assert broken.info().status is ManifestStatus.INVALID and broken.read().problem == "manifest.invalid"
    data = json.loads(manifest_bytes(built.manifest))
    data["files"][0]["size"] = 5
    location.write_text(json.dumps(data), encoding="utf-8")
    assert state().info().status is ManifestStatus.HASH_MISMATCH


@pytest.mark.parametrize("linked", [".neurogrid", ".neurogrid/manifest.json"])
def test_state_never_follows_a_link_at_the_default_location(tmp_path: Path, linked: str) -> None:
    """A linked .neurogrid, or a link at .neurogrid/manifest.json, is not read (A-52, A-66): problem "link"
    (CORE-M13-01 manifest_invalid), and nothing is compared."""
    root = tmp_path / "ds"
    (root / ".neurogrid").mkdir(parents=True)
    (root / "a.txt").write_text("a", encoding="utf-8")
    built = build_manifest(root, _exclusions())
    assert built.manifest is not None
    target = tmp_path / "elsewhere" / "manifest.json"  # a folder: links to folders are junctions on Windows
    target.mkdir(parents=True)
    (target / "manifest.json").write_bytes(manifest_bytes(built.manifest))
    if linked == ".neurogrid":
        (root / ".neurogrid").rmdir()
    dir_link(root.joinpath(*PurePosixPath(linked).parts), target)
    state = ProvenanceState(
        root, single_file=False, is_bids=False, show_paths=False, manifest_path=None, work=None
    )
    assert state.read() == io_provenance.ManifestRead(None, "link", None)
    assert state.info().status is ManifestStatus.INVALID and state.comparison() is None


# --- texts ---------------------------------------------------------------------------------------------


def test_every_provenance_key_exists_in_every_language() -> None:
    """Keys built at run time (critic G3): reasons per deviation kind, check titles, verify lines, report
    statuses, the re-keyed YAML errors of provenance.yaml and the manifest errors."""
    from neurogrid.checks import provenance as checks
    from neurogrid.kernel.i18n import LANGUAGES
    from neurogrid.report.texts import tables

    keys = {f"reason.{key}" for key in checks._REASONS.values()}
    keys |= {f"check.{spec.id}" for spec in checks.SPECS}
    keys |= {f"cli.verify.{kind}" for kind in kp.DEVIATION_KINDS}
    keys |= {f"report.manifest_status.{status.value}" for status in ManifestStatus}
    keys |= {
        f"errors.provenance.yaml_{name}"
        for name in ("alias", "duplicate_key", "syntax", "too_large", "too_deep")
    }
    keys |= {
        f"errors.manifest.{name}"
        for name in (
            "not_found",
            "unreadable",
            "too_large",
            "encoding",
            "invalid",
            "unsupported_version",
            "unsafe_path",
            "duplicate_path",
            "excluded_invalid",
            "needs_folder",
            "steps_invalid",
        )
    }
    keys |= {
        "notice.output_inside_dataset",
        "report.label.manifest_status",
        "reason.provenance.single_file",
        "reason.provenance.files_differ",
        "cli.verify.matches",
        "cli.verify.differs",
        "cli.verify.hash_ok",
        "cli.verify.hash_mismatch",
        "cli.verify.checked",
    }
    loaded = tables()
    for lang in LANGUAGES:
        missing = sorted(key for key in keys if key not in loaded[lang])
        assert not missing, (lang, missing)
