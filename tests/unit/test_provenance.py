"""M13 provenance units (NG-F10, A-22, A-82): inventory, streaming hashes, manifest build, hash, reader and
comparison in the kernel; documentation sources, exclusions and display on the NeuroGrid side."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path, PurePosixPath

import pytest
from pydantic import ValidationError

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
    shown_target,
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


def _native(path: Path) -> Path:
    """A path the file system takes literally: Windows would change names with a trailing dot or space and
    reserved names, and long paths need the extended form."""
    return Path("\\\\?\\" + str(path)) if WINDOWS else path


def _put(path: Path, data: bytes | None = None) -> None:
    """Create a folder (data None) or a file under a name the path check refuses."""
    if data is None:
        _native(path).mkdir()
    else:
        _native(path).write_bytes(data)


def _remove(path: Path) -> None:
    shutil.rmtree(_native(path))


def _unsafe(manifest: kp.Manifest) -> set[str]:
    return {entry.path for entry in manifest.skipped if entry.kind == "unsafe_name"}


def test_long_escaped_refused_names_are_recorded(tmp_path: Path) -> None:
    """PRO19: a refused name whose percent-encoded form is longer than 3 * MAX_PATH_CHARS is a skipped entry,
    never a ValidationError: CJK folders (9 characters per character) above a name with a trailing space, and
    a path the length rule alone refuses (over MAX_PATH_CHARS characters, no special character)."""
    root = tmp_path / "ds"
    root.mkdir()
    (root / "ok.txt").write_text("ok", encoding="utf-8")
    folder = root
    for _ in range(5):  # 80 characters per folder: 240 bytes, within the 255-byte limit of POSIX file systems
        folder = folder / ("患者资料" * 20)
        _put(folder)
    trailing = folder / "x "
    _put(trailing)
    _put(trailing / "rec.edf", b"1")
    deep = root
    for _ in range(13):
        deep = deep / ("脑电" * 40)
        _put(deep)
    _put(deep / "x.edf", b"2")
    try:
        long_name = (trailing / "rec.edf").relative_to(root).as_posix()
        length_only = (deep / "x.edf").relative_to(root).as_posix()
        assert len(escape_name(long_name)) > 3 * kp.MAX_PATH_CHARS and len(length_only) > kp.MAX_PATH_CHARS
        built = build_manifest(root, _exclusions())
        assert built.manifest is not None
        assert [item.path for item in built.manifest.files] == ["ok.txt"]
        unsafe = _unsafe(built.manifest)
        assert {escape_name(long_name), escape_name(length_only)} <= unsafe
        parsed = parse_manifest(manifest_bytes(built.manifest))  # the reader takes the same bound
        assert parsed.hash_ok and compare(root, parsed.manifest, _exclusions()).deviations == ()
        _put(trailing / "new.edf", b"3")
        assert [(d.path, d.kind) for d in compare(root, parsed.manifest, _exclusions()).deviations] == [
            (escape_name((trailing / "new.edf").relative_to(root).as_posix()), "new")
        ]
    finally:
        _remove(root)


def test_escaped_names_are_bounded_alike_for_writer_and_reader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PRO19: SkippedEntry holds every name a walk can return (MAX_ESCAPED_CHARS, writer and reader); longer
    is refused by the reader, and a validation error never shows the name (--debug, A-51)."""
    assert kp.MAX_ESCAPED_CHARS == 3 * 3 * 32_767
    data = _valid(tmp_path)
    data["skipped"] = [{"kind": "unsafe_name", "path": "%E8" * (kp.MAX_ESCAPED_CHARS // 3)}]
    assert parse_manifest(_rehashed(data)).hash_ok  # at the bound: accepted
    data["skipped"] = [{"kind": "unsafe_name", "path": "%E8" * (kp.MAX_ESCAPED_CHARS // 3) + "x"}]
    with pytest.raises(ManifestError) as info:
        parse_manifest(_rehashed(data))
    assert info.value.message_key == "manifest.invalid" and info.value.params["field"] == "skipped.0.path"
    secret = "Zhang" + "San"
    with pytest.raises(ValidationError) as error:
        kp.SkippedEntry(path=secret * kp.MAX_ESCAPED_CHARS, kind="unsafe_name")
    assert secret not in str(error.value)
    # defensive: a name longer than the bound cannot be recorded; it is reported, never raised
    monkeypatch.setattr(kp, "MAX_ESCAPED_CHARS", 8)
    _put(tmp_path / "long name.")
    try:
        found = inventory(tmp_path)
        assert "long name." in found.unreadable and all(e.path != "long name." for e in found.skipped)
    finally:
        _remove(tmp_path / "long name.")


def test_names_below_a_refused_folder_are_compared_by_presence(tmp_path: Path) -> None:
    """PRO20 (A-82, critic X8): a folder the path check refuses is walked; every name below it is a skipped
    unsafe_name entry, so new and missing files there are deviations. Their content is never hashed, and a
    link below such a folder is recorded, not followed."""
    root = tmp_path / "ds"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.edf").write_bytes(b"outside")
    (root / "pat").mkdir()
    (root / "pat" / "sub01.edf").write_bytes(b"p" * 10)
    _put(root / "aux")
    _put(root / "aux" / "sub01.edf", b"a" * 10)
    _put(root / "aux" / "keep.edf", b"k")
    _put(root / "aux" / "nested")
    _put(root / "aux" / "nested" / "deep.edf", b"d")
    _put(root / "sub-01.")
    _put(root / "sub-01." / "rec.edf", b"r")
    linked = root / "aux" / "linked"
    if WINDOWS:
        import _winapi

        _winapi.CreateJunction(str(outside), str(_native(linked)))
    else:
        dir_link(linked, outside)
    try:
        built = build_manifest(root, _exclusions())
        assert built.manifest is not None
        assert [item.path for item in built.manifest.files] == ["pat/sub01.edf"]
        assert _unsafe(built.manifest) == {
            "aux",
            "aux/keep.edf",
            "aux/linked",
            "aux/nested",
            "aux/nested/deep.edf",
            "aux/sub01.edf",
            "sub-01.",
            "sub-01./rec.edf",
        }  # nothing from behind the link
        manifest = parse_manifest(manifest_bytes(built.manifest)).manifest
        assert compare(root, manifest, _exclusions()).deviations == ()
        _put(root / "aux" / "sub01.edf", b"b" * 10)  # same size, other content: not hashed (X8)
        assert compare(root, manifest, _exclusions()).deviations == ()
        _put(root / "aux" / "sub02.edf", b"n")
        _native(root / "aux" / "keep.edf").unlink()
        _native(root / "sub-01." / "rec.edf").unlink()
        found = {(d.path, d.kind, d.before, d.now) for d in compare(root, manifest, _exclusions()).deviations}
        assert found == {
            ("aux/sub02.edf", "new", None, "unsafe_name"),
            ("aux/keep.edf", "missing", "unsafe_name", None),
            ("sub-01./rec.edf", "missing", "unsafe_name", None),
        }
    finally:
        if WINDOWS:
            _native(linked).rmdir()  # the junction, not its target
        else:
            linked.unlink()
        _remove(root)


def test_files_below_an_unlistable_refused_folder_are_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PRO20: a refused folder that cannot be listed stops the manifest (exit 1) and makes the entries below
    it unreadable in a comparison, also when their stored names are percent-encoded."""
    folder = tmp_path / "张三 "
    _put(folder)
    _put(folder / "a.edf", b"a")
    try:
        manifest = _manifest(tmp_path)
        assert _unsafe(manifest) == {escape_name("张三 "), escape_name("张三 /a.edf")}
        real_walk = os.walk

        def walk(top: str | os.PathLike[str], **kwargs: object):  # type: ignore[no-untyped-def]
            for dirpath, dirnames, filenames in real_walk(top, **kwargs):  # type: ignore[call-overload]
                if Path(dirpath).name == "张三 ":
                    kwargs["onerror"](PermissionError(13, "denied", dirpath))  # type: ignore[operator]
                    continue
                yield dirpath, dirnames, filenames

        monkeypatch.setattr(kp.os, "walk", walk)
        found = [(d.path, d.kind, d.before) for d in compare(tmp_path, manifest, _exclusions()).deviations]
        assert found == [(escape_name("张三 /a.edf"), "unreadable", "unsafe_name")]
        built = build_manifest(tmp_path, _exclusions())
        assert built.manifest is None and built.unreadable == ("张三 ",)
    finally:
        monkeypatch.undo()
        _remove(folder)


def test_refused_and_plain_names_that_read_alike_stay_apart(tmp_path: Path) -> None:
    """PRO27: 'COM¹.txt' is refused and stored as 'COM%C2%B9.txt', which is also a plain, allowed name. The
    reader accepts the manifest the builder wrote, the comparison keeps both entries, and their findings have
    different keys."""
    root = tmp_path / "ds"
    root.mkdir()
    (root / "README").write_text("x", encoding="utf-8")
    _put(root / "COM¹.txt", b"refused name")
    (root / "COM%C2%B9.txt").write_bytes(b"plain name")
    try:
        built = build_manifest(root, _exclusions())
        assert built.manifest is not None
        assert [item.path for item in built.manifest.files] == ["COM%C2%B9.txt", "README"]
        assert _unsafe(built.manifest) == {"COM%C2%B9.txt"}
        manifest = parse_manifest(manifest_bytes(built.manifest)).manifest
        assert compare(root, manifest, _exclusions()).deviations == ()
        _native(root / "COM¹.txt").unlink()
        gone = compare(root, manifest, _exclusions()).deviations
        assert [(d.path, d.kind, d.before) for d in gone] == [("COM%C2%B9.txt", "missing", "unsafe_name")]
        _put(root / "COM¹.txt", b"refused name")
        (root / "COM%C2%B9.txt").unlink()
        gone = compare(root, manifest, _exclusions()).deviations
        assert [(d.path, d.kind, d.before) for d in gone] == [("COM%C2%B9.txt", "missing", "file")]
        _native(root / "COM¹.txt").unlink()
        both = compare(root, manifest, _exclusions()).deviations
        assert [(d.kind, d.unsafe) for d in both] == [("missing", False), ("missing", True)]
        shown = [show(d.path, plain=True, kind="unsafe_name" if d.unsafe else None) for d in both]
        assert shown[0].identity[0] != shown[1].identity[0]  # distinct finding keys (A-68)
        assert shown[1].identity[0] == io_provenance.UNSAFE_IDENTITY + "COM%C2%B9.txt"
        assert {"COM%C2%B9.txt"} <= set(shown[1].identity)  # exception patterns still match the stored path
    finally:
        _remove(root)
    # the same name listed twice, in any spelling, is still refused
    data = _valid(tmp_path)
    data["skipped"] = [{"kind": "unsafe_name", "path": "a%2Etxt"}]
    with pytest.raises(ManifestError) as info:
        parse_manifest(_rehashed(data))
    assert info.value.message_key == "manifest.duplicate_path"


def test_more_entries_than_a_manifest_holds_give_no_manifest_but_no_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dataset data (C2): more files or more skipped entries than MAX_MANIFEST_ENTRIES are a result without a
    manifest (``too_many``, the limit; exit 1 in ``manifest``), never a ManifestError; nothing is hashed then.
    Up to the limit the manifest is built."""
    root = tmp_path / "ds"
    root.mkdir()
    (root / "a.txt").write_text("a", encoding="utf-8")
    (root / "b.txt").write_text("b", encoding="utf-8")
    monkeypatch.setattr(kp, "MAX_MANIFEST_ENTRIES", 2)
    at_limit = build_manifest(root, _exclusions())
    assert at_limit.manifest is not None and at_limit.too_many is None
    monkeypatch.setattr(kp, "MAX_MANIFEST_ENTRIES", 1)

    def no_hashing(*_args: object) -> None:
        raise AssertionError("hashed although no manifest can be written")

    monkeypatch.setattr(kp, "hash_files", no_hashing)
    assert build_manifest(root, _exclusions()) == kp.BuildResult(None, (), (), 0, too_many=1)
    (root / "b.txt").unlink()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    dir_link(root / "one", elsewhere)
    dir_link(root / "two", elsewhere)  # one file, two skipped links
    assert build_manifest(root, _exclusions()) == kp.BuildResult(None, (), (), 0, too_many=1)
    monkeypatch.undo()  # hashing again
    monkeypatch.setattr(kp, "MAX_MANIFEST_ENTRIES", 2)
    with_links = build_manifest(root, _exclusions())
    assert with_links.manifest is not None and len(with_links.manifest.skipped) == 2


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


def _nested_json(levels: int, kind: str = "dict") -> str:
    """JSON text nested ``levels`` levels deep, written as text: json.dumps itself recurses."""
    if kind == "dict":
        return '{"a":' * (levels - 1) + '{"a":1' + "}" * levels
    return "[" * levels + "]" * levels


def _nested(levels: int) -> dict[str, object]:
    value: dict[str, object] = {"a": 1}
    for _ in range(levels - 1):
        value = {"a": value}
    return value


def _with_parameters(tmp_path: Path, parameters: str) -> bytes:
    data = _valid(tmp_path)
    data["processing_steps"] = [{"step": "s", "tool": "t", "version": "1", "parameters": "PARAMETERS"}]
    return json.dumps(data).replace('"PARAMETERS"', parameters).encode("utf-8")


@pytest.mark.parametrize(
    ("levels", "kind"),
    [(kp.MAX_PARAMETER_DEPTH + 1, "dict"), (990, "dict"), (1200, "list"), (2900, "dict")],
)
def test_deeply_nested_manifests_are_invalid_not_a_crash(tmp_path: Path, levels: int, kind: str) -> None:
    """PRO21 (A-53, C2): a manifest nested deeper than the builder ever writes is manifest.invalid (too_deep),
    before the schema, canonical JSON or the hash recurse (RecursionError at about 1000 levels before)."""
    parameters = '{"p":' + _nested_json(levels - 1, kind) + "}"
    with pytest.raises(ManifestError) as info:
        parse_manifest(_with_parameters(tmp_path, parameters))
    assert info.value.message_key == "manifest.invalid"
    assert info.value.params == {"field": "-", "problem": "too_deep"}


def test_the_reader_accepts_the_deepest_parameters_the_builder_writes(tmp_path: Path) -> None:
    """PRO21/PRO25: parameters nest at most MAX_PARAMETER_DEPTH levels; such a step is written and read
    again, one level more is refused where a step is made."""
    assert kp.nesting_within(_nested(kp.MAX_PARAMETER_DEPTH), kp.MAX_PARAMETER_DEPTH)
    assert not kp.nesting_within(_nested(kp.MAX_PARAMETER_DEPTH + 1), kp.MAX_PARAMETER_DEPTH)
    assert kp.nesting_within(1, 0) and not kp.nesting_within([], 0) and kp.nesting_within([[1], (2,)], 2)
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    step = ProcessingStep(step="s", tool="t", version="1", parameters=_nested(kp.MAX_PARAMETER_DEPTH))
    built = build_manifest(tmp_path, _exclusions(), processing_steps=[step])
    assert built.manifest is not None
    assert parse_manifest(manifest_bytes(built.manifest)).hash_ok
    with pytest.raises(ValidationError):
        ProcessingStep(step="s", tool="t", version="1", parameters=_nested(kp.MAX_PARAMETER_DEPTH + 1))
    parameters = '{"p":' + _nested_json(kp.MAX_PARAMETER_DEPTH - 1) + "}"
    assert not parse_manifest(_with_parameters(tmp_path, parameters)).hash_ok  # read, hash not recomputed


def test_steps_that_canonical_json_cannot_hold_are_a_clean_error(tmp_path: Path) -> None:
    """PRO25 backstop: the step readers refuse such values; a step made in code gives steps_invalid, never a
    bare ValueError."""
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    step = ProcessingStep(step="s", tool="t", version="1", parameters={"x": object()})  # no JSON value
    with pytest.raises(ManifestError) as info:
        build_manifest(tmp_path, _exclusions(), processing_steps=[step])
    assert info.value.message_key == "manifest.steps_invalid" and info.value.params == {"problem": "value"}


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


@pytest.mark.parametrize("levels", [kp.MAX_PARAMETER_DEPTH + 1, 120, 990, 1100])
def test_deeply_nested_processing_steps_are_too_deep(tmp_path: Path, levels: int) -> None:
    """PRO25: parameters deeper than a manifest can hold make processing_steps.json unusable ("too_deep"):
    manifest ends with steps_invalid naming the file, check reports it, the two agree."""
    path = tmp_path / ".neurogrid" / "processing_steps.json"
    path.parent.mkdir()
    step = '[{"step":"convert","tool":"neurogrid","version":"0.1.0","parameters":PARAMETERS}]'
    path.write_text(step.replace("PARAMETERS", _nested_json(levels)), encoding="utf-8")
    assert load_processing_steps(tmp_path) == ([], "too_deep")
    path.write_text(step.replace("PARAMETERS", _nested_json(kp.MAX_PARAMETER_DEPTH)), encoding="utf-8")
    steps, problem = load_processing_steps(tmp_path)
    assert problem is None and len(steps) == 1
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    built = build_manifest(tmp_path, _exclusions(), processing_steps=steps)  # written and read again
    assert built.manifest is not None and parse_manifest(manifest_bytes(built.manifest)).hash_ok


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


def test_the_written_manifest_is_named_as_a51_allows() -> None:
    """INT45: inside a raw folder the console names the manifest file by the pseudonymous file name verify
    shows, except the default location and NeuroGrid's fixed names; in clear in BIDS or with --show-paths."""
    assert shown_target(".neurogrid/manifest.json", plain=False) == ".neurogrid/manifest.json"
    assert shown_target(".neurogrid/provenance.yaml", plain=False) == ".neurogrid/provenance.yaml"
    named = "Zh" + "ang_San/m.json"
    hidden = shown_target(named, plain=False)
    assert hidden == "…/" + show(named, plain=False).file and "ang_San" not in hidden
    assert hidden.startswith("…/rec-") and hidden.endswith(".json")
    at_root = "Zh" + "ang_San.json"
    assert shown_target(at_root, plain=False) == show(at_root, plain=False).file
    assert shown_target(".neurogrid/copy.json", plain=False).startswith("…/rec-")
    assert shown_target(named, plain=True) == named


@pytest.mark.parametrize(
    ("own", "bidsignore", "expected"),
    [
        ("manifest.json", None, "listed"),
        ("sub-01/manifest.json", None, "listed"),
        ("sub-01/derivatives/manifest.json", None, "listed"),  # only top-level folders are ignored
        (".neurogrid/copy.json", None, None),
        ("sub-01/.cache/m.json", None, None),
        ("sourcedata/manifest.json", None, None),
        ("derivatives/manifest.json", None, None),
        ("code/manifest.json", None, None),
        ("stimuli/manifest.json", None, None),
        ("log/manifest.json", None, None),
        ("doc/manifest.json", None, None),
        ("Code/manifest.json", None, None),  # without case
        ("SourceData/manifest.json", None, None),
        ("manifest.json", "manifest.json\n", None),
        ("sub-01/manifest.json", "manifest.json\n", None),  # no slash: a name anywhere
        ("sub-01/manifest.json", "sub-01\n", None),  # also a folder name
        ("manifest.json", "/manifest.json\n", None),
        ("sub-01/manifest.json", "/manifest.json\n", "listed"),  # a slash anchors at the root
        ("sub-01/manifest.json", "sub-01/manifest.json\n", None),
        ("a/b/manifest.json", "b/manifest.json\n", "listed"),  # a slash in the middle anchors as well
        ("extra/manifest.json", "extra/\n", None),
        ("extra/manifest.json", "Extra/\n", None),
        ("sub-01/eeg/manifest.json", "eeg/\n", None),
        ("sub-01/eeg/manifest.json", "sub-01/eeg/\n", None),
        ("manifest.json", "manifest.json/\n", "listed"),  # a trailing slash names folders only
        ("manifest.json", "MANIFEST.json\r\n", None),  # without case, CR and trailing spaces dropped
        ("manifest.json", "\ufeffmanifest.json   \n", None),
        ("manifest.json", "# manifest.json\n", "listed"),
        ("manifest.json", "  manifest.json\n", "listed"),  # leading spaces are part of the pattern
        ("manifest.json", "*.json\n", "maybe"),
        ("manifest.json", "manifest.json\n!manifest.json\n", "maybe"),
        ("manifest.json", "other.txt\n!x\n", "listed"),
        # only CRs, then spaces are dropped at the end of a line: other whitespace stays part of the name
        ("manifest.json", "manifest.json\t\n", "listed"),
        ("manifest.json", "manifest.json　\n", "listed"),  # ideographic space (Chinese input methods)
        ("manifest.json", "manifest.json \n", "listed"),
        ("manifest.json", "manifest.json\x0b\n", "listed"),
        ("manifest.json", "manifest.json\x0c\n", "listed"),
        ("manifest.json", "manifest.json \t \n", "listed"),
        ("sub-01/manifest.json", "sub-01\t\n", "listed"),
        ("manifest.json", "manifest.json   \r\n", None),
        ("manifest.json", "manifest.json\r\r\n", None),
        ("manifest.json", "manifest.json\r   \n", "listed"),  # spaces after a CR: the CR stays
        ("manifest.json", "manifest.json  \r  \n", "listed"),
        # a line that is empty only after that matches every path; one of spaces only is skipped
        ("manifest.json", "other.txt\r\n\r\nzzz\r\n", None),  # an empty line of a CRLF file
        ("manifest.json", " \r\n", None),
        ("manifest.json", "other.txt\n﻿\n", None),
        ("manifest.json", "   \n", "listed"),
        ("manifest.json", "\t\n", "listed"),
        ("manifest.json", "manifest.json\n!\r\n", "maybe"),
        # the reader drops the file's byte order mark; a later one hides '!' and '#' and is then dropped
        ("manifest.json", "﻿\nother.txt\n", "listed"),
        ("manifest.json", "﻿!manifest.json\n", "listed"),
        ("manifest.json", "manifest.json\n﻿!manifest.json\n", None),
        ("manifest.json", "﻿﻿manifest.json\n", None),
        ("manifest.json", "﻿#x\nmanifest.json\n", None),
        ("#manifest.json", "﻿#manifest.json\n", "listed"),
        ("#manifest.json", "x\n﻿#manifest.json\n", None),
        ("manifest.json", "!﻿manifest.json\nmanifest.json\n", "maybe"),
        # text starting with a replacement character is taken for UTF-16: the whole file is not used
        ("manifest.json", b"\xff\nmanifest.json\n", "listed"),
        ("manifest.json", b"\xef\xbb\xbf\xff\nmanifest.json\n", "listed"),
        ("manifest.json", "�\nmanifest.json\n", "listed"),
        ("manifest.json", b"x\n\xff\nmanifest.json\n", None),
        # case as a JavaScript regular expression without the u flag compares it
        ("k.json", "K.json\n", "listed"),  # Kelvin sign
        ("K.json", "k.json\n", "listed"),
        ("K.json", "K.json\n", None),
        ("σ.json", "ς.json\n", None),  # sigma and final sigma
        ("\U00010428.json", "\U00010400.json\n", "listed"),  # outside the BMP: no case
        ("\U00010428.json", "\U00010428.json\n", None),
        ("é.json", "É.JSON\n", None),
        ("i.json", "İ.json\n", "listed"),
        ("straße.json", "STRASSE.json\n", "listed"),
    ],
)
def test_validator_listing_follows_the_bundled_validator(
    tmp_path: Path, own: str, bidsignore: str | bytes | None, expected: str | None
) -> None:
    """PRO23: where the bundled validator 3.0.2 lists a file (each case measured with validator.run: hidden
    entries, the top-level folders of VALIDATOR_IGNORED_FOLDERS and .bidsignore with the gitignore rules of
    its ignore package, without case); patterns NeuroGrid does not evaluate give "maybe" (conditional
    hint)."""
    if bidsignore is not None:
        data = bidsignore if isinstance(bidsignore, bytes) else bidsignore.encode("utf-8")
        (tmp_path / ".bidsignore").write_bytes(data)
    assert io_provenance.validator_listing(tmp_path, own) == expected


def test_validator_listing_with_an_unusable_bidsignore(tmp_path: Path) -> None:
    (tmp_path / ".bidsignore").mkdir()
    assert io_provenance.validator_listing(tmp_path, "manifest.json") == "maybe"
    assert io_provenance.validator_listing(tmp_path, "code/manifest.json") is None


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
        "cli.manifest.too_many_entries",
        "cli.manifest.bids_hint",
        "cli.manifest.bids_hint_bidsignore",
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
