"""tools/bundle.py verify (UF-08, CON-02, CON-04, D-08, A-48, A-58): every way a bundle can be incomplete,
changed or carry something it must not carry is reported (exit 1); a good bundle passes (exit 0)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from bundle_fakes import VERSION, extract, inputs, resum, rewrite, wheel

import bundle

Members = dict[str, tuple[bytes | None, str | None, int]]


def _bundle(tmp_path: Path, platform: str) -> tuple[Path, str]:
    archive = bundle.build(inputs(tmp_path, platform))
    return archive, f"neurogrid-{VERSION}-offline-{platform}"


def _problems(archive: Path, change: Callable[[Members], None]) -> list[str]:
    return bundle.verify(rewrite(archive, change))


@pytest.mark.parametrize("platform", ["win_amd64", "linux_x86_64"])
def test_changed_missing_and_extra_files_are_reported(tmp_path: Path, platform: str) -> None:
    archive, root = _bundle(tmp_path, platform)
    good = archive.read_bytes()

    def changed(found: Members) -> None:
        found[f"{root}/LICENSE"] = (b"changed", None, 0o100644)

    def missing(found: Members) -> None:
        del found[f"{root}/NOTICE"]

    def extra(found: Members) -> None:
        found[f"{root}/docs/extra.html"] = (b"x", None, 0o100644)

    for change, expected in (
        (changed, "changed (SHA-256 differs): LICENSE"),
        (missing, "listed but missing: NOTICE"),
        (extra, "not listed in SHA256SUMS: docs/extra.html"),
    ):
        archive.write_bytes(good)
        problems = _problems(archive, change)
        assert expected in problems, problems


def test_disallowed_content_is_reported_even_with_consistent_checksums(tmp_path: Path) -> None:
    archive, root = _bundle(tmp_path, "win_amd64")
    good = archive.read_bytes()
    cases = {
        "chrome-headless-shell-win64/chrome-headless-shell.exe": "browser files must not be in the bundle",
        "ms-playwright/x.txt": "browser files must not be in the bundle",
        "data/rec.edf": "not allowed at the top level: data/",
        "tools/other.py": "not allowed in tools/: tools/other.py",
        "wheels/notes.txt": "not a wheel: wheels/notes.txt",
        "docs/x.pyc": "bytecode outside the interpreter",
    }
    for path, expected in cases.items():
        archive.write_bytes(good)

        def plant(found: Members, path: str = path) -> None:
            found[f"{root}/{path}"] = (b"x", None, 0o100644)
            resum(found, root)

        problems = _problems(archive, plant)
        assert any(expected in p for p in problems), (path, problems)


def test_names_that_differ_only_in_case_are_reported_for_windows(tmp_path: Path) -> None:
    archive, root = _bundle(tmp_path, "win_amd64")

    def twin(found: Members) -> None:
        found[f"{root}/docs/INDEX.html"] = (b"x", None, 0o100644)
        resum(found, root)

    assert "paths differ only in case: docs/INDEX.html, docs/index.html" in _problems(archive, twin)


def test_wheel_checks(tmp_path: Path) -> None:
    archive, root = _bundle(tmp_path, "linux_x86_64")
    good = archive.read_bytes()
    too_new = wheel(tmp_path / "w", "delta", "1.0", "cp312-cp312-manylinux_2_34_x86_64")
    with_pyc = wheel(
        tmp_path / "w", "eps", "1.0", "py3-none-any", {"eps/__pycache__/x.cpython-312.pyc": b"x"}
    )
    for planted, expected in ((too_new, "manylinux <= 2_28"), (with_pyc, "wheel contains bytecode")):
        archive.write_bytes(good)

        def plant(found: Members, planted: Path = planted) -> None:
            found[f"{root}/wheels/{planted.name}"] = (planted.read_bytes(), None, 0o100644)
            resum(found, root)

        problems = _problems(archive, plant)
        assert any(expected in p for p in problems), problems
        assert any("not pinned in requirements.lock.txt" in p for p in problems)
        assert any("BUNDLE.json: wheel list differs" in p for p in problems)


def test_linux_checks_berkeley_db_and_links(tmp_path: Path) -> None:
    archive, root = _bundle(tmp_path, "linux_x86_64")
    good = archive.read_bytes()

    def dbm(found: Members) -> None:
        found[f"{root}/python/lib/python3.12/lib-dynload/_dbm.cpython-312-x86_64-linux-gnu.so"] = (
            b"x",
            None,
            0o100755,
        )
        resum(found, root)

    def outside(found: Members) -> None:
        found[f"{root}/python/bin/escape"] = (None, "../../../etc/passwd", 0o777)

    def unrecorded(found: Members) -> None:
        found[f"{root}/python/bin/another"] = (None, "python3.12", 0o777)

    expectations = (
        (dbm, "Berkeley DB module must be removed"),
        (dbm, "records python/lib/python3.12/lib-dynload"),
        (outside, "link points outside the bundle"),
        (unrecorded, "SYMLINKS does not match"),
    )
    for change, expected in expectations:
        archive.write_bytes(good)
        problems = _problems(archive, change)
        assert any(expected in p for p in problems), (expected, problems)


def test_readme_without_the_fixed_sentence_is_reported(tmp_path: Path) -> None:
    archive, root = _bundle(tmp_path, "win_amd64")

    def strip(found: Members) -> None:
        found[f"{root}/README.txt"] = (b"NeuroGrid offline bundle\n", None, 0o100644)
        resum(found, root)

    problems = _problems(archive, strip)
    assert "README.txt lacks the fixed sentence (zh)" in problems
    assert "README.txt lacks the fixed sentence (en)" in problems


def test_signature_and_identity_must_come_together(tmp_path: Path) -> None:
    archive, root = _bundle(tmp_path, "win_amd64")

    def signature_only(found: Members) -> None:
        found[f"{root}/SHA256SUMS.sigstore.json"] = (b"{}", None, 0o100644)

    problems = _problems(archive, signature_only)
    assert "BUNDLE.json: release_identity and SHA256SUMS.sigstore.json must come together" in problems


def test_bundle_json_must_match_the_root_name(tmp_path: Path) -> None:
    archive, root = _bundle(tmp_path, "win_amd64")

    def other_version(found: Members) -> None:
        info = json.loads(found[f"{root}/BUNDLE.json"][0] or b"")
        info["version"] = "0.0.1"
        found[f"{root}/BUNDLE.json"] = (json.dumps(info).encode(), None, 0o100644)
        resum(found, root)

    assert "BUNDLE.json: version or platform differ from the root folder name" in _problems(
        archive, other_version
    )


def test_unsorted_or_malformed_checksum_lines_are_reported(tmp_path: Path) -> None:
    archive, root = _bundle(tmp_path, "win_amd64")
    good = archive.read_bytes()

    def unsorted(found: Members) -> None:
        lines = (found[f"{root}/SHA256SUMS"][0] or b"").decode().splitlines(keepends=True)
        found[f"{root}/SHA256SUMS"] = ("".join(reversed(lines)).encode(), None, 0o100644)

    def malformed(found: Members) -> None:
        data = found[f"{root}/SHA256SUMS"][0] or b""
        found[f"{root}/SHA256SUMS"] = (data.replace(b"  ", b" *", 1), None, 0o100644)

    assert "SHA256SUMS is not sorted" in _problems(archive, unsorted)
    archive.write_bytes(good)
    assert any(p.startswith("malformed SHA256SUMS line") for p in _problems(archive, malformed))


def test_an_extracted_windows_bundle_folder_is_verified_too(tmp_path: Path) -> None:
    archive, _ = _bundle(tmp_path, "win_amd64")
    folder = extract(archive, tmp_path / "extracted")
    assert bundle.verify(folder) == []
    (folder / "README.txt").write_text("changed", encoding="utf-8")
    assert "changed (SHA-256 differs): README.txt" in bundle.verify(folder)


def test_two_root_folders_or_a_wrong_name_are_reported(tmp_path: Path) -> None:
    archive, root = _bundle(tmp_path, "win_amd64")

    def second_root(found: Members) -> None:
        found["other/x.txt"] = (b"x", None, 0o100644)

    problems = _problems(archive, second_root)
    assert any("exactly one root folder" in p for p in problems)


def test_verify_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    archive, root = _bundle(tmp_path, "win_amd64")
    assert bundle.main(["verify", str(archive)]) == 0
    assert capsys.readouterr().out.strip().endswith(": ok")
    rewrite(archive, lambda found: found.__setitem__(f"{root}/NOTICE", (b"x", None, 0o100644)))
    assert bundle.main(["verify", str(archive)]) == 1
    other = tmp_path / "x.7z"
    other.write_bytes(b"x")
    assert bundle.main(["verify", str(other)]) == 2
