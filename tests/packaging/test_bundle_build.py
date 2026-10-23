"""tools/bundle.py build on stand-in inputs (UF-08, A-26, A-48, D-08, KONZEPT 1.6): content, formats,
removals, reproducibility and every refusal. Nothing is downloaded; the inputs come through file:// URLs."""

from __future__ import annotations

import dataclasses
import gzip
import hashlib
import io
import json
import re
import stat
import tarfile
import zipfile
from pathlib import Path

import pytest
from bundle_fakes import EPOCH, VERSION, inputs, members, pin

import bundle
from neurogrid.report.texts import disclaimer

PLATFORMS = ("win_amd64", "linux_x86_64")


def _build(tmp_path: Path, platform: str, **changes: object) -> Path:
    built = inputs(tmp_path, platform)
    return bundle.build(dataclasses.replace(built, **changes) if changes else built)


@pytest.mark.parametrize("platform", PLATFORMS)
def test_bundle_has_the_allowed_layout_and_passes_verify(tmp_path: Path, platform: str) -> None:
    archive = _build(tmp_path, platform)
    root = f"neurogrid-{VERSION}-offline-{platform}"
    assert archive.name == root + (".zip" if platform == "win_amd64" else ".tar.gz")
    names = {name.removeprefix(root + "/") for name in members(archive)}
    tops = {name.split("/")[0] + ("/" if "/" in name else "") for name in names}
    expected = {
        "BUNDLE.json", "LICENSE", "NOTICE", "README.txt", "SHA256SUMS", "THIRD_PARTY_NOTICES.txt",
        "docs/", "python/", "requirements.lock.txt", "src/", "tools/", "uv/", "wheels/",
    }  # fmt: skip
    expected |= {"install.cmd", "install.ps1"} if platform == "win_amd64" else {"install.sh", "SYMLINKS"}
    assert tops == expected
    assert f"src/neurogrid-{VERSION}.tar.gz" in names and "tools/install_pdf_browser.py" in names
    assert {n for n in names if n.startswith("uv/")} == {
        "uv/" + ("uv.exe" if platform == "win_amd64" else "uv"),
        "uv/LICENSE-APACHE",
        "uv/LICENSE-MIT",
        "uv/uv.cyclonedx.json",
    }
    assert "SHA256SUMS.sigstore.json" not in names  # unsigned development bundle
    assert bundle.verify(archive) == []


@pytest.mark.parametrize("platform", PLATFORMS)
def test_wheelhouse_has_exactly_the_fitting_wheels(tmp_path: Path, platform: str) -> None:
    archive = _build(tmp_path, platform)
    wheels = sorted(n.rsplit("/", 1)[1] for n in members(archive) if "/wheels/" in n)
    if platform == "win_amd64":
        assert wheels == [
            "alpha-1.0-py3-none-any.whl",
            "beta-2.0-cp312-cp312-win_amd64.whl",
            "gamma-3.0-py3-none-any.whl",  # the marker sys_platform == 'win32' holds
            f"neurogrid-{VERSION}-py3-none-any.whl",
        ]
    else:
        assert wheels == [
            "alpha-1.0-py3-none-any.whl",
            "beta-2.0-cp312-cp312-manylinux_2_28_x86_64.whl",  # never the manylinux_2_34 one (A-58)
            f"neurogrid-{VERSION}-py3-none-any.whl",
        ]


@pytest.mark.parametrize("platform", PLATFORMS)
def test_requirements_pin_every_bundled_wheel_by_hash(tmp_path: Path, platform: str) -> None:
    archive = _build(tmp_path, platform)
    found = members(archive)
    root = f"neurogrid-{VERSION}-offline-{platform}"
    text = (found[f"{root}/requirements.lock.txt"][0] or b"").decode()
    pins = bundle.parse_requirements(text)
    hashes = {h for p in pins for h in p.hashes}
    wheel_hashes = {hashlib.sha256(d or b"").hexdigest() for n, (d, _, _) in found.items() if "/wheels/" in n}
    assert hashes == wheel_hashes
    assert all(len(p.hashes) == 1 and p.marker is None for p in pins)
    assert f"neurogrid=={VERSION} \\\n    --hash=sha256:" in text


@pytest.mark.parametrize("platform", PLATFORMS)
def test_two_builds_are_byte_identical(tmp_path: Path, platform: str) -> None:
    built = inputs(tmp_path, platform)
    first = bundle.build(dataclasses.replace(built, out=tmp_path / "a"))
    second = bundle.build(dataclasses.replace(built, out=tmp_path / "b", cache=tmp_path / "other-cache"))
    assert first.read_bytes() == second.read_bytes()
    third = bundle.build(dataclasses.replace(built, out=tmp_path / "c", source_date_epoch=EPOCH + 86400))
    assert third.read_bytes() != first.read_bytes()  # the epoch is really the only time source


def test_sha256sums_format(tmp_path: Path) -> None:
    archive = _build(tmp_path, "win_amd64")
    found = members(archive)
    root = f"neurogrid-{VERSION}-offline-win_amd64"
    lines = (found[f"{root}/SHA256SUMS"][0] or b"").decode().split("\n")
    assert lines[-1] == ""
    paths = []
    for line in lines[:-1]:
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9._+/-]+)", line)
        assert match, line
        digest, rel = match.groups()
        assert hashlib.sha256(found[f"{root}/{rel}"][0] or b"").hexdigest() == digest
        paths.append(rel)
    assert paths == sorted(paths)
    regular = {n.removeprefix(root + "/") for n in found} - {"SHA256SUMS"}
    assert set(paths) == regular


def test_zip_entries_are_normalised(tmp_path: Path) -> None:
    archive = _build(tmp_path, "win_amd64")
    with zipfile.ZipFile(archive) as z:
        infos = z.infolist()
    assert [i.filename for i in infos] == sorted(i.filename for i in infos)
    for info in infos:
        assert info.create_system == 3
        assert info.date_time == (2023, 11, 14, 22, 13, 20)  # SOURCE_DATE_EPOCH 1700000000 in UTC
        mode = info.external_attr >> 16
        assert stat.S_ISREG(mode) and stat.S_IMODE(mode) in (0o644, 0o755)
        expected = zipfile.ZIP_STORED if info.filename.endswith((".whl", ".gz")) else zipfile.ZIP_DEFLATED
        assert info.compress_type == expected
    modes = {i.filename.rsplit("/", 1)[1]: stat.S_IMODE(i.external_attr >> 16) for i in infos}
    assert modes["python.exe"] == 0o755 and modes["uv.exe"] == 0o755 and modes["BUNDLE.json"] == 0o644
    assert (members(archive)[f"neurogrid-{VERSION}-offline-win_amd64/install.cmd"][0] or b"").count(
        b"\r\n"
    ) >= 3


def test_tar_entries_are_normalised_and_links_recorded(tmp_path: Path) -> None:
    archive = _build(tmp_path, "linux_x86_64")
    raw = archive.read_bytes()
    assert raw[:2] == b"\x1f\x8b" and raw[4:8] == b"\x00\x00\x00\x00"  # gzip header mtime 0
    assert raw[3] & 0x08 == 0  # no file name in the gzip header
    root = f"neurogrid-{VERSION}-offline-linux_x86_64"
    with tarfile.open(archive, "r:gz") as tar:
        infos = tar.getmembers()
    assert [i.name for i in infos] == sorted(i.name for i in infos)
    by_name = {i.name: i for i in infos}
    for info in infos:
        assert (info.uid, info.gid, info.uname, info.gname, info.mtime) == (0, 0, "", "", EPOCH)
    assert by_name[root].isdir() and by_name[root].mode == 0o755
    assert by_name[f"{root}/install.sh"].mode == 0o755
    assert by_name[f"{root}/uv/uv"].mode == 0o755
    assert by_name[f"{root}/python/bin/python3.12"].mode == 0o755
    assert by_name[f"{root}/BUNDLE.json"].mode == 0o644
    assert (
        by_name[f"{root}/python/bin/python3"].issym()
        and by_name[f"{root}/python/bin/python3"].linkname == "python3.12"
    )
    links = (members(archive)[f"{root}/SYMLINKS"][0] or b"").decode()
    assert links == "python/bin/python -> python3.12\npython/bin/python3 -> python3.12\n"
    # names that differ only in case stay apart (nothing is staged on a case-insensitive disk)
    assert {f"{root}/python/share/terminfo/E/Eterm", f"{root}/python/share/terminfo/e/eterm"} <= set(by_name)


def test_linux_bundle_leaves_out_and_records_the_berkeley_db_module(tmp_path: Path) -> None:
    archive = _build(tmp_path, "linux_x86_64")
    root = f"neurogrid-{VERSION}-offline-linux_x86_64"
    found = members(archive)
    assert not [n for n in found if "/_dbm." in n]
    info = json.loads(found[f"{root}/BUNDLE.json"][0] or b"")
    assert info["python"]["removed"] == [
        "python/lib/python3.12/lib-dynload/_dbm.cpython-312-x86_64-linux-gnu.so"
    ]


def test_bundle_json_fields(tmp_path: Path) -> None:
    built = inputs(tmp_path, "win_amd64")
    archive = bundle.build(built)
    found = members(archive)
    root = f"neurogrid-{VERSION}-offline-win_amd64"
    raw = found[f"{root}/BUNDLE.json"][0] or b""
    info = json.loads(raw)
    assert raw.decode() == json.dumps(info, indent=1, sort_keys=True) + "\n"
    assert info["format_version"] == 1 and info["name"] == "neurogrid"
    assert (info["version"], info["platform"]) == (VERSION, "win_amd64")
    assert info["git_commit"] == "0" * 40 and info["source_date_epoch"] == EPOCH
    assert info["uv_lock_sha256"] == hashlib.sha256(built.uv_lock_text.encode()).hexdigest()
    assert info["python"]["version"] == "3.12.15" and info["python"]["removed"] == []
    assert info["uv"]["version"] == "0.13.0" and info["uv"]["wheel"].startswith("uv-0.13.0-")
    assert [w["file"] for w in info["wheels"]] == sorted(w["file"] for w in info["wheels"])
    assert info["sdist"]["file"] == f"neurogrid-{VERSION}.tar.gz"
    assert info["release_identity"] is None
    venv = "venv/Lib/site-packages/"
    assert info["max_relative_install_path"] >= len(venv + "alpha/__pycache__/__init__.cpython-312.pyc")


def test_readme_carries_the_fixed_sentence_and_no_placeholder(tmp_path: Path) -> None:
    archive = _build(tmp_path, "linux_x86_64")
    text = (members(archive)[f"neurogrid-{VERSION}-offline-linux_x86_64/README.txt"][0] or b"").decode()
    assert disclaimer("zh") in text and disclaimer("en") in text
    assert "{{" not in text and VERSION in text and "linux_x86_64" in text
    assert "Signer identity: -" in text  # unsigned development bundle


def test_a_pin_without_a_fitting_wheel_is_refused(tmp_path: Path) -> None:
    built = inputs(tmp_path, "linux_x86_64")
    fitting = r'    \{ url = "[^"]*beta-2\.0-cp312-cp312-(win_amd64|manylinux_2_28_x86_64)\.whl"[^\n]*\n'
    only_new = re.sub(fitting, "",
                      built.uv_lock_text)  # fmt: skip
    with pytest.raises(bundle.BundleError, match="no cp312 wheel for linux_x86_64: beta==2.0"):
        bundle.build(dataclasses.replace(built, uv_lock_text=only_new))


def test_wrong_inputs_are_refused(tmp_path: Path) -> None:
    built = inputs(tmp_path, "win_amd64")
    other = built.wheel.with_name(f"other-{VERSION}-py3-none-any.whl")
    other.write_bytes(built.wheel.read_bytes())
    cases = {
        "not the NeuroGrid wheel": dataclasses.replace(built, wheel=other),
        "sdist name does not match": dataclasses.replace(built, sdist=built.notices),
        "not a built documentation site": dataclasses.replace(built, docs=built.docs / "zh" / "missing"),
        "input file missing": dataclasses.replace(built, pdf_installer=tmp_path / "missing.py"),
        "unknown platform": dataclasses.replace(built, platform="macos_arm64"),
    }
    for message, case in cases.items():
        with pytest.raises(bundle.BundleError, match=message):
            bundle.build(case)


def test_signing_needs_the_release_workflow(tmp_path: Path) -> None:
    built = inputs(tmp_path, "win_amd64")
    with pytest.raises(bundle.BundleError, match="GITHUB_REPOSITORY or NEUROGRID_RELEASE_REPOSITORY"):
        bundle.build(dataclasses.replace(built, sign="sigstore"))
    with pytest.raises(bundle.BundleError, match="OIDC token of a GitHub Actions run"):
        bundle.build(
            dataclasses.replace(built, sign="sigstore", environ={"NEUROGRID_RELEASE_REPOSITORY": "o/r"})
        )
    assert bundle.release_identity("1.2.3", {"GITHUB_REPOSITORY": "owner/neurogrid"}) == (
        "https://github.com/owner/neurogrid/.github/workflows/release.yml@refs/tags/v1.2.3"
    )


def test_install_ps1_without_bom_is_refused(tmp_path: Path) -> None:
    built = inputs(tmp_path, "win_amd64")
    packaging = tmp_path / "packaging"
    packaging.mkdir()
    for name in ("README.bundle.txt", "install.cmd", "install.sh"):
        (packaging / name).write_bytes((built.packaging_dir / name).read_bytes())
    (packaging / "install.ps1").write_bytes((built.packaging_dir / "install.ps1").read_bytes()[3:])
    with pytest.raises(bundle.BundleError, match="UTF-8 with BOM"):
        bundle.build(dataclasses.replace(built, packaging_dir=packaging))


def test_a_removal_that_is_not_in_the_interpreter_is_refused(tmp_path: Path) -> None:
    built = inputs(tmp_path, "linux_x86_64")
    built.lock["remove"]["linux_x86_64"].append({"path": "python/lib/missing.so", "reason": "x"})
    with pytest.raises(bundle.BundleError, match="removal not found"):
        bundle.build(built)


def test_links_out_of_the_bundle_and_odd_paths_are_refused() -> None:
    stage = bundle.Stage("linux_x86_64")
    for bad in ("a b.txt", "../x", "/abs", "a//b", "ä.txt", "x/./y"):
        with pytest.raises(bundle.BundleError):
            stage.file(bad, b"")
    assert bundle._inside("python/bin/../lib/x") and not bundle._inside("python/../../etc/passwd")


def test_case_collisions_are_refused_for_windows(tmp_path: Path) -> None:
    """Two members whose names differ only in case cannot both exist on a Windows disk. The pair is planted in
    the interpreter archive (a tar keeps both names even on a case-insensitive build machine)."""
    built = inputs(tmp_path, "win_amd64")
    archive = tmp_path / "pbs-case.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for name, data in (
            ("python/python.exe", b"MZ stand-in interpreter"),
            ("python/Lib/Case.py", b"# upper\n"),
            ("python/Lib/case.py", b"# lower\n"),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    built.lock["python"]["platforms"]["win_amd64"] = pin(archive)
    with pytest.raises(bundle.BundleError, match="differ only in case.*Lib/Case.py, python/Lib/case.py"):
        bundle.build(built)
    linux = inputs(tmp_path / "linux", "linux_x86_64")  # the Linux stand-in has the pair E/Eterm, e/eterm
    assert bundle.verify(bundle.build(linux)) == []


def test_parse_requirements_of_the_uv_export_format() -> None:
    text = (
        "alpha==1.0 \\\n    --hash=sha256:"
        + "a" * 64
        + " \\\n    --hash=sha256:"
        + "b" * 64
        + "\n    # via x\n"
        "Beta_Pkg==2.0 ; sys_platform == 'win32' \\\n    --hash=sha256:" + "c" * 64 + "\n"
    )
    pins = bundle.parse_requirements(text)
    assert pins[0] == bundle.Pin("alpha", "1.0", None, frozenset({"a" * 64, "b" * 64}))
    assert pins[1].name == "beta-pkg" and pins[1].marker == "sys_platform == 'win32'"
    for bad in ("alpha>=1.0 \\\n    --hash=sha256:" + "a" * 64 + "\n", "alpha==1.0\n", "-e .\n"):
        with pytest.raises(bundle.BundleError):
            bundle.parse_requirements(bad)


def test_fetch_checks_size_and_hash_and_uses_the_cache(tmp_path: Path) -> None:
    source = tmp_path / "file.bin"
    source.write_bytes(b"payload")
    digest = hashlib.sha256(b"payload").hexdigest()
    cache = tmp_path / "cache"
    got = bundle.fetch(source.as_uri(), digest, 7, cache)
    assert got == cache / digest and got.read_bytes() == b"payload"
    source.unlink()
    assert bundle.fetch(source.as_uri(), digest, 7, cache) == got  # served from the cache, no access
    other = tmp_path / "other.bin"
    other.write_bytes(b"payload!")
    with pytest.raises(bundle.BundleError, match="larger than the pinned"):
        bundle.fetch(other.as_uri(), "0" * 64, 7, cache)
    with pytest.raises(bundle.BundleError, match="pinned 8"):
        bundle.fetch(other.as_uri(), "0" * 64, 8, cache)
    assert not list(cache.glob("*.part"))


def test_installed_paths_cover_bytecode_scripts_and_data() -> None:
    names = ["pkg/__init__.py", "pkg/data.bin", "pkg-1.0.data/scripts/tool", "pkg-1.0.data/purelib/extra.py"]
    paths = set(bundle.installed_paths("pkg-1.0-py3-none-any.whl", names, "win_amd64"))
    assert paths == {
        "venv/Lib/site-packages/pkg/__init__.py",
        "venv/Lib/site-packages/pkg/__pycache__/__init__.cpython-312.pyc",
        "venv/Lib/site-packages/pkg/data.bin",
        "venv/Scripts/tool",
        "venv/Lib/site-packages/extra.py",
        "venv/Lib/site-packages/__pycache__/extra.cpython-312.pyc",
    }
    linux = set(bundle.installed_paths("pkg-1.0-py3-none-any.whl", names[:1], "linux_x86_64"))
    assert "venv/lib/python3.12/site-packages/pkg/__pycache__/__init__.cpython-312.pyc" in linux


def test_highest_manylinux() -> None:
    assert bundle.highest_manylinux(["a-1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl"]) == (
        2,
        17,
    )
    assert bundle.highest_manylinux(
        ["a-1-py3-none-any.whl", "b-1-cp312-cp312-manylinux_2_28_x86_64.whl"]
    ) == (2, 28)
    assert bundle.highest_manylinux(["a-1-py3-none-any.whl"]) is None


def test_command_line_usage_errors_exit_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert bundle.main(["build", "--platform", "win_amd64"]) == 2
    assert bundle.main(["unknown"]) == 2
    assert bundle.main(["verify", "does-not-exist.zip"]) == 2
    assert "not found" in capsys.readouterr().err


def test_gzip_of_the_tar_is_deterministic_without_name(tmp_path: Path) -> None:
    archive = _build(tmp_path, "linux_x86_64")
    with gzip.open(archive) as handle:
        assert handle.read(512)  # a readable tar header
