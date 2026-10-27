"""Third-party notices and the licence gate's package sets (D-08, A-56, NG-N07, A-86).

tools/notices.py reads the locked wheels of both targets statically; these tests check its parts on synthetic
wheels and archives (no network), the committed THIRD_PARTY_NOTICES.txt against uv.lock, the reviewed
component list, and that the runtime export of the licence gate holds no package of the dev or docs group."""

from __future__ import annotations

import dataclasses
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import tomllib
import zipfile
from pathlib import Path
from typing import Any

import pytest
from packaging.markers import Marker
from packaging.utils import canonicalize_name

import licenses  # type: ignore[import-not-found]
import notices  # type: ignore[import-not-found]

ROOT = Path(__file__).resolve().parents[2]
ELF = b"\x7fELF" + b"\0" * 60
GROUP_ONLY_EXAMPLES = {
    "mkdocs",
    "mkdocs-material",
    "mkdocs-static-i18n",
    "pytest",
    "ruff",
    "mypy",
    "pip-licenses",
}


# --- the committed notices and the lock ---------------------------------------------------------------------


def _committed() -> str:
    return notices.NOTICES.read_text(encoding="utf-8")


def test_notices_list_exactly_the_locked_runtime_packages() -> None:
    assert notices.notice_packages(_committed()) == notices.locked_packages()


def test_notices_were_generated_from_the_current_lock() -> None:
    digest = hashlib.sha256(notices.LOCK.read_bytes()).hexdigest()
    assert f"uv.lock SHA-256: {digest}" in _committed(), "run tools/notices.py --out THIRD_PARTY_NOTICES.txt"


def test_notices_name_every_known_gap_and_the_validator_packages() -> None:
    text = _committed()
    gaps = text.split("5. Known gaps", 1)[1].split("\n6. ", 1)[0]
    known = notices.load_known_missing()
    for item in known:
        assert f"- {item['component']}: " in gaps, item["component"]
    assert "Packages compiled into the BIDS validator bundle" in text
    # D-17 closed the gaps of STOPP G1: section 5 says so instead of listing pending texts
    assert (notices.PENDING in gaps) is bool(known) and (notices.NO_GAPS in gaps) is not bool(known)
    assert "Chrome Headless Shell" in text and "not_distributed" in text  # D-08: named, never shipped
    texts = list(notices.iter_texts(text))
    assert len(texts) == len(set(texts)) > 50  # every licence text once


# Tables whose rows come from the contents of the wheels and bundle files; their rows are tied to uv.lock and
# packaging/bundle_lock.json by the tests above and below, the frame test compares only their column names.
WHEEL_TABLES = {
    ("Package", "Version", "Licence (metadata)", "Targets"),
    ("Target", "Package", "File", "Licence"),
    ("Registry", "Package", "Version", "Licence", "Licence texts"),
    ("Target", "Component", "Version", "File", "Licence"),
}
TABLE_RULE = re.compile(r"-+(?:  -+)*")
BUNDLE_HEADING = "Offline bundle parts as pinned in packaging/bundle_lock.json:"


def _frame(text: str) -> list[str]:
    """A notices text without what the wheel contents contribute: the header, every heading and paragraph,
    the review notes, the components outside the wheels, the removals and the gaps; of the tables built from
    the wheel contents only the column names. Section 6 (the licence texts) is compared separately."""
    lines = text.split("\n" + "=" * 78 + "\n", 1)[0].splitlines()
    frame: list[str] = []
    skipping = False
    for index, line in enumerate(lines):
        if index + 1 < len(lines) and TABLE_RULE.fullmatch(lines[index + 1]):
            columns = tuple(re.split(r"\s{2,}", line.strip()))
            frame.append("| " + " | ".join(columns))
            skipping = columns in WHEEL_TABLES
        elif TABLE_RULE.fullmatch(line):
            continue  # the rule under a header: its widths follow the rows
        elif skipping and line.strip() and not line.startswith("- "):
            continue  # a row of a wheel table (a list item after a table is no row)
        else:
            skipping = False
            frame.append(line)
    return frame


def _without_wheel_contents() -> str:
    """The generator's output for the current repository with wheels and bundle files that carry nothing:
    one validator wheel with one bundled package (so that section 3 is written) and, when
    packaging/bundle_lock.json exists, its pinned parts with their recorded removals."""
    locked = next(
        p for p in notices.runtime_packages("linux_x86_64") if canonicalize_name(p.name) == notices.VALIDATOR
    )
    validator = notices.WheelInfo(
        name=locked.name,
        version=locked.version,
        target="linux_x86_64",
        filename="validator.whl",
        sha256="0" * 64,
        license_expression="MIT",
        license_texts={},
        native=[],
        paths=[],
        sources=[("npm", "example", "1.0.0")],
    )
    pins, removed = notices.bundle_pins()
    parts = []
    for pin in pins:
        removals = removed.get(pin.target, []) if pin.name == notices.PBS else []
        parts.append(notices.BundleInfo(pin.name, pin.version, pin.target, pin.filename, "X", {}, removals))
    components, _allowed = notices.load_components()
    return notices.render([validator], components, notices.load_known_missing(), parts)


def test_committed_notices_have_the_generators_frame() -> None:
    """The committed file is what tools/notices.py writes today: its prose, section structure, review notes,
    components outside the wheels and gaps equal a fresh generation (a re-wrapped source string, an edited
    components.toml or known_missing.toml without a new generation fails here, not first in the release)."""
    committed, fresh = _committed(), _without_wheel_contents()
    assert _frame(committed) == _frame(fresh), "run tools/notices.py --out THIRD_PARTY_NOTICES.txt"
    kept_here = set(notices.iter_texts(fresh))  # the licence texts kept in this repository (OFL.txt)
    assert kept_here and kept_here <= set(notices.iter_texts(committed))


def test_frame_finds_changed_prose_and_component_lists() -> None:
    committed = _committed()
    assert any(line.startswith("NeuroGrid itself is licensed") for line in _frame(committed))
    assert "| Kind | Component | Part | Platform | Licence | Text" in _frame(committed)
    rewrapped = committed.replace("sample data are\nlicensed under", "sample data\nare licensed under")
    assert rewrapped != committed and _frame(rewrapped) != _frame(committed)
    for item in notices.load_known_missing():
        gap = committed.replace(f"- {item['component']}: ", f"- {item['component']} (changed): ")
        assert gap != committed and _frame(gap) != _frame(committed)
    note = "- bids-validator-deno bids_validator_deno/bids-validator.js: "
    reviewed = committed.replace(note, note + "changed ")
    assert reviewed != committed and _frame(reviewed) != _frame(committed)
    # a different wheel content does not change the frame
    row = next(line for line in committed.splitlines() if line.startswith("annotated-doc "))
    assert _frame(committed.replace(row, row.replace("MIT", "BSD-3-Clause", 1))) == _frame(committed)


def test_committed_notices_list_exactly_the_pinned_bundle_parts() -> None:
    """packaging/bundle_lock.json (bundle area) adds the offline bundle parts to the notices: the committed
    file names exactly the pinned parts and removals, or none while the bundle data is absent."""
    committed = _committed()
    pins, removed = notices.bundle_pins()
    if not pins:
        assert BUNDLE_HEADING not in committed and "removed from the bundle" not in committed
        return
    section = committed.split(BUNDLE_HEADING, 1)[1].split("\n5. ", 1)[0].split("\nLibraries that ", 1)[0]
    rows = {tuple(line.split()[:4]) for line in section.strip().splitlines()[2:] if not line.startswith("- ")}
    assert rows == {(p.target, p.name, p.version, p.filename) for p in pins}
    for target, items in removed.items():
        for path, reason in items:
            assert f"- removed from the bundle ({target}): {path} - {reason}" in section


def test_committed_notices_list_the_libraries_of_the_bundled_python() -> None:
    """D-17: the libraries python-build-standalone builds into the pinned Python are reviewed with their texts
    (license-gate/third_party/python-build-standalone-<version>/manifest.toml) and listed in section 4, each
    text in section 6; the texts are python-build-standalone's own licence files at the release tag plus the
    project files for what that set lacks."""
    pins, _removed = notices.bundle_pins()
    versions = {p.version for p in pins if p.name == notices.PBS}
    if not versions:
        pytest.skip("no packaging/bundle_lock.json")
    (version,) = versions
    review = notices.load_library_review(notices.PBS, version)
    assert review is not None
    assert notices.check_library_review(notices.PBS, version, review, []) == []
    names = {p.name for p in review.packages}
    assert {"OpenSSL", "libffi", "SQLite", "XZ Utils (liblzma)", "zlib", "Tcl/Tk", "itcl", "HACL*"} <= names
    tag = "python-build-standalone@" + version.split("+", 1)[1] + "/"
    for package in review.packages:
        for text in package.texts:
            assert text.url.startswith("https://raw.githubusercontent.com/"), text.label
            if text.label.startswith(tag):  # the PBS files at the tag, not the upstream alternatives
                assert text.url.endswith(
                    f"/astral-sh/python-build-standalone/{tag.split('@')[1]}{text.path.name}"
                )
    committed = _committed()
    heading = notices.LIBRARIES_HEADING.format(name=notices.PBS, version=version)
    section = committed.split(heading, 1)[1].split("\n5. ", 1)[0]
    rows = [line for line in section.splitlines() if line.startswith(notices.LIBRARY_PLATFORMS)]
    assert len(rows) == len(review.packages)
    users = [
        line for line in committed.splitlines() if line.startswith(f"Used by: {notices.PBS} {version}: ")
    ]
    assert len(users) == sum(len(p.texts) for p in review.packages)
    missing = notices.check_library_review(notices.PBS, version, None, [])
    assert missing and "no licence texts of the libraries" in missing[0]
    assert (
        notices.check_library_review(notices.PBS, version, None, [{"component": f"{notices.PBS}:{version}"}])
        == []
    )


def test_kept_texts_and_library_reviews_are_checked(tmp_path: Path) -> None:
    """Every folder of license-gate/third_party holds exactly the texts its manifest lists, with their SHA-256
    and size; a library of a bundle part needs a text and a permissive licence (D-17)."""
    base = notices.library_review_folder(notices.PBS, "1.0+1", tmp_path)
    (base / "lib@1").mkdir(parents=True)
    data = b"MIT licence of lib\n"
    (base / "lib@1" / "LICENSE").write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()

    def manifest(spdx: str, sha256: str = digest, platform: str = "any") -> None:
        lines = [
            "version = 1",
            f'component = "{notices.PBS}"',
            'component_version = "1.0+1"',
            "[[package]]",
            'registry = "library"',
            'name = "lib"',
            'version = "1"',
            f'platform = "{platform}"',
            f'spdx = "{spdx}"',
            "[[package.text]]",
            'file = "lib@1/LICENSE"',
            'origin = "LICENSE"',
            'kind = "licence file"',
            f"size = {len(data)}",
            f'sha256 = "{sha256}"',
        ]
        (base / "manifest.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def problems() -> list[str]:
        review = notices.load_library_review(notices.PBS, "1.0+1", tmp_path)
        return notices.check_library_review(notices.PBS, "1.0+1", review, [])

    manifest("MIT")
    assert problems() == [] and notices.check_kept_texts(tmp_path) == []
    manifest("MIT AND LGPL-2.1-or-later")
    assert problems() == [
        "bundle part python-build-standalone 1.0+1: lib 1: licence MIT AND LGPL-2.1-or-later is not "
        "permissive"
    ]
    manifest("TCL", platform="macos")
    assert problems() == ["bundle part python-build-standalone 1.0+1: lib 1: unknown platform macos"]
    manifest("MIT", sha256="0" * 64)
    found = [*problems(), *notices.check_kept_texts(tmp_path)]
    assert len(found) == 2 and all("SHA-256 or size of lib@1/LICENSE differs" in p for p in found)
    manifest("MIT")
    (base / "lib@1" / "LICENSE.extra.txt").write_text("not listed\n", encoding="utf-8")
    assert notices.check_kept_texts(tmp_path) == [
        "python-build-standalone-1.0+1: file not listed in manifest.toml: lib@1/LICENSE.extra.txt"
    ]
    assert notices.load_library_review(notices.PBS, "9", tmp_path) is None
    other = notices.library_review_folder(notices.PBS, "2.0+2", tmp_path / "other")
    other.mkdir(parents=True)
    shutil.copy(base / "manifest.toml", other / "manifest.toml")  # names version 1.0+1
    with pytest.raises(notices.NoticeError):
        notices.load_library_review(notices.PBS, "2.0+2", tmp_path / "other")


def test_excerpts_record_their_source_and_sources_are_checked(tmp_path: Path) -> None:
    """A text cut from a file that is not kept (D-17) records that file (url, retrieved, source_size,
    source_sha256); --sources finds a copy by size and SHA-256 and checks that the text comes from it:
    verbatim from a text file, as the words of the plain text from an HTML page."""
    base = tmp_path / "pkg-1"
    base.mkdir()
    rst = b"Intro\n\nlib\n---\n\nPermission is hereby granted.\n\nOther\n"
    page = (
        b"<html><body><h2>License</h2><p>Licensed like the <a href='http://z.example/l.html'>zlib "
        b"license</a>:</p><ol><li>Do no harm.</li></ol></body></html>"
    )
    excerpts = {
        "a.txt": (b"lib\n---\n\nPermission is hereby granted.\n", rst, "https://x.example/license.rst"),
        "b.txt": (
            b"License\n\nLicensed like the zlib license (http://z.example/l.html):\n\n1. Do no harm.\n",
            page,
            "https://x.example/disclaimer.html",
        ),
    }
    sources = tmp_path / "sources"
    sources.mkdir()

    def write_manifest(texts: dict[str, bytes]) -> str:
        lines = ["version = 1", "[[package]]", 'registry = "library"', 'name = "lib"', 'version = "1"']
        for name, (_, source, url) in excerpts.items():
            text = texts[name]
            (base / name).write_bytes(text)
            lines += [
                "[[package.text]]",
                f'file = "{name}"',
                'origin = "a section"',
                f'kind = "{notices.EXCERPT}"',
                f'url = "{url}"',
                f"size = {len(text)}",
                f'sha256 = "{hashlib.sha256(text).hexdigest()}"',
                'retrieved = "2026-10-27"',
                f"source_size = {len(source)}",
                f'source_sha256 = "{hashlib.sha256(source).hexdigest()}"',
            ]
        content = "\n".join(lines) + "\n"
        (base / "manifest.toml").write_text(content, encoding="utf-8")
        return content

    def put_sources(a: bytes, b: bytes) -> None:
        (sources / "copy-a.txt").write_bytes(a)
        (sources / "copy-b.txt").write_bytes(b)

    texts = {name: text for name, (text, _, _) in excerpts.items()}
    plain = write_manifest(texts)
    put_sources(rst, page)
    assert notices.check_kept_texts(tmp_path) == []
    assert notices.check_text_sources([sources], tmp_path) == ([], 2)
    empty = tmp_path / "no-copies"
    empty.mkdir()
    assert notices.main(["--sources", str(empty)]) == 1  # the committed reviews: no copy of any source

    put_sources(rst.replace(b"hereby", b"not"), page.replace(b"no harm", b"what you like"))
    found, checked = notices.check_text_sources([sources], tmp_path)
    assert checked == 2 and [p.split(" (")[0] for p in found] == [
        "pkg-1: a.txt: no copy of its source",
        "pkg-1: b.txt: no copy of its source",
    ]
    put_sources(rst, page)
    write_manifest({**texts, "b.txt": b"License\n\nAnything goes.\n"})  # not from the page
    assert notices.check_kept_texts(tmp_path) == []
    found, _ = notices.check_text_sources([sources], tmp_path)
    assert len(found) == 1 and found[0].startswith("pkg-1: b.txt: does not come from its source")

    # the kind is known and an excerpt names the file it was cut from
    write_manifest(texts)
    (base / "manifest.toml").write_text(plain.replace("source_size = ", "page_size = ", 1), encoding="utf-8")
    assert notices.check_kept_texts(tmp_path) == [
        "pkg-1: library lib 1: a.txt needs url, retrieved, source_size (larger than the text) and "
        "source_sha256 of the file it was cut from"
    ]
    (base / "manifest.toml").write_text(plain.replace(notices.EXCERPT, "page excerpt", 1), encoding="utf-8")
    assert notices.check_kept_texts(tmp_path) == [
        "pkg-1: library lib 1: unknown kind 'page excerpt' of a.txt"
    ]


def _wheel_folders() -> list[Path]:
    """.local/notices-wheels and, for a worktree without its own cache, NEUROGRID_NOTICES_WHEELS."""
    folders = [notices.DEFAULT_CACHE]
    if os.environ.get("NEUROGRID_NOTICES_WHEELS"):
        folders.append(Path(os.environ["NEUROGRID_NOTICES_WHEELS"]))
    return folders


def test_committed_notices_equal_a_generation_from_the_cached_wheels() -> None:
    """With every pinned file in .local/notices-wheels or NEUROGRID_NOTICES_WHEELS (filled by
    `tools/notices.py --download`) the whole file is compared with a fresh generation; without them the
    frame test above still runs."""
    folders = _wheel_folders()
    wheels, missing = notices.collect(folders, fetch=False, cache=notices.DEFAULT_CACHE)
    bundle, missing_parts = notices.collect_bundle(folders, fetch=False, cache=notices.DEFAULT_CACHE)
    if missing or missing_parts:
        pytest.skip(
            f"{len(missing) + len(missing_parts)} pinned files are not in .local/notices-wheels "
            "(python tools/notices.py --download --check fills it)"
        )
    components, _allowed = notices.load_components()
    fresh = notices.render(wheels, components, notices.load_known_missing(), bundle)
    committed = _committed()
    assert committed == fresh, f"first difference in line {notices.first_difference(committed, fresh)}"


def test_first_difference_names_the_line() -> None:
    assert notices.first_difference("a\nb\nc\n", "a\nx\nc\n") == 2
    assert notices.first_difference("a\nb\n", "a\nb\nc\n") == 3
    assert notices.first_difference("a\n", "a\n") == 2


def test_paragraphs_do_not_depend_on_how_the_source_is_broken() -> None:
    one = notices.paragraph("NeuroGrid itself is licensed under Apache-2.0.   Its documentation\n  follows.")
    assert one == notices.paragraph(
        "NeuroGrid itself is licensed under Apache-2.0. Its documentation follows."
    )
    lines = notices.paragraph(notices.INTRO + " " + notices.VALIDATOR_INTRO)
    assert len(lines) > 1 and all(len(line) <= notices.WIDTH for line in lines)


def test_runtime_closure_excludes_the_dependency_groups() -> None:
    lock = tomllib.loads(notices.LOCK.read_text(encoding="utf-8"))
    locked = {canonicalize_name(p["name"]) for p in lock["package"]}
    assert GROUP_ONLY_EXAMPLES <= locked  # the groups are in the lock (default-groups = dev, docs) ...
    for target in notices.TARGETS:
        names = {canonicalize_name(p.name) for p in notices.runtime_packages(target)}
        assert not GROUP_ONLY_EXAMPLES & names, target  # ... but never in the runtime set
        assert {"mne", "numpy", "typer", "bids-validator-deno"} <= names


def _uv() -> str:
    found = os.environ.get("UV") or shutil.which("uv")
    if not found:
        pytest.skip("uv is neither on PATH nor in UV (CI and `uv run` provide it)")
    return found


def _export(command: list[str]) -> dict[str, str]:
    """name -> marker ('' without) of a `uv export` in requirements format."""
    out = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True
    ).stdout
    found = {}
    for line in out.splitlines():
        match = re.match(r"^([A-Za-z0-9_.\-]+)==\S+(?:\s*;\s*(.+))?$", line.strip())
        if match:
            found[canonicalize_name(match.group(1))] = (match.group(2) or "").strip()
    return found


def test_runtime_export_holds_no_dev_or_docs_package(monkeypatch: pytest.MonkeyPatch) -> None:
    """B3: every runtime export is `uv export --frozen --no-default-groups --no-emit-project`; with
    default-groups = [dev, docs] a --no-dev export would carry the documentation tools (measured 78 vs 62)."""
    monkeypatch.setattr(licenses, "UV", _uv())
    command = licenses.export_command("runtime")
    assert {"--frozen", "--no-default-groups", "--no-emit-project"} <= set(
        command
    ) and "--no-dev" not in command
    runtime = _export(command)
    groups = {**_export(licenses.export_command("dev")), **_export(licenses.export_command("docs"))}
    static = {canonicalize_name(p.name) for t in notices.TARGETS for p in notices.runtime_packages(t)}
    group_only = set(groups) - static
    assert GROUP_ONLY_EXAMPLES <= group_only
    assert not group_only & set(runtime), sorted(group_only & set(runtime))
    # the export is universal (3.11-3.13); for CPython 3.12 on both targets it equals tools/notices.py's set
    env = {target: notices.environment(target) for target in notices.TARGETS}
    applicable = {
        name
        for name, marker in runtime.items()
        if not marker or any(Marker(marker).evaluate(e) for e in env.values())
    }
    assert applicable == static


# --- reading wheels -----------------------------------------------------------------------------------------


def _wheel(folder: Path, name: str, version: str, files: dict[str, bytes], metadata: str) -> Path:
    path = folder / f"{name}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"{name}-{version}.dist-info/METADATA", metadata)
        for inner, data in files.items():
            archive.writestr(inner, data)
    return path


def _locked(name: str, version: str) -> Any:
    return notices.Locked(name, version, (), (), {})


def _sample(tmp_path: Path, name: str = "demo", licence_text: bytes = b"MIT text\r\n") -> Any:
    files = {
        f"{name}-1.0.dist-info/licenses/LICENSE": licence_text,
        f"{name}.libs/libfoo-123.so.1": ELF,
        f"{name}/_ext.cpython-312-x86_64-linux-gnu.so": ELF,  # an extension module, not a native library
        f"{name}/NOTICE.extra": b"extra notice",
        f"{name}/code.py": b"x = 1\n",
    }
    path = _wheel(
        tmp_path, name, "1.0", files, "Metadata-Version: 2.4\nName: demo\nLicense-Expression: MIT\n"
    )
    return notices.read_wheel(path, _locked(name, "1.0"), "linux_x86_64", [f"{name}/NOTICE.*"])


def test_read_wheel_finds_licences_notices_and_native_libraries(tmp_path: Path) -> None:
    info = _sample(tmp_path)
    assert info.license_expression == "MIT"
    assert info.license_texts == {
        "demo-1.0.dist-info/licenses/LICENSE": "MIT text\n",
        "demo/NOTICE.extra": "extra notice\n",
    }
    assert info.native == ["demo.libs/libfoo-123.so.1"]


@pytest.mark.parametrize(
    ("metadata", "expected"),
    [
        ("License-Expression: Apache-2.0\nLicense: whatever\n", "Apache-2.0"),
        ("License: BSD-3-Clause\n", "BSD-3-Clause"),
        ("Classifier: License :: OSI Approved :: MIT License\n", "MIT License"),
        ("Name: x\n", "NOASSERTION"),
    ],
)
def test_license_expression_order(metadata: str, expected: str) -> None:
    assert notices.license_expression(metadata) == expected


def test_spdx_clauses_split_and_or() -> None:
    clauses = notices.spdx_clauses(
        "MIT AND (CC0-1.0 OR OpenSSL OR Apache-2.0) AND GPL-3.0-or-later WITH GCC-exception-3.1 AND MIT"
    )
    assert clauses == [
        frozenset({"MIT"}),
        frozenset({"CC0-1.0", "OpenSSL", "Apache-2.0"}),
        frozenset({"GPL-3.0-or-later WITH GCC-exception-3.1"}),
    ]
    # a choice between a licence and two that must both hold: each clause keeps its choice
    assert notices.spdx_clauses("A OR (B AND C)") == [frozenset({"A", "B"}), frozenset({"A", "C"})]
    assert notices.spdx_clauses("MIT OR Apache-2.0") == [frozenset({"MIT", "Apache-2.0"})]
    assert notices.spdx_clauses("") == []
    for broken in ("(MIT", "MIT AND", "MIT OR OR BSD-3-Clause", "MIT WITH", "MIT BSD-3-Clause", ")"):
        with pytest.raises(ValueError):
            notices.spdx_clauses(broken)


def test_spdx_units_keep_exceptions() -> None:
    units = notices.spdx_units("BSD-3-Clause AND (MIT OR GPL-3.0-or-later WITH GCC-exception-3.1)")
    assert units == {"BSD-3-Clause", "MIT", "GPL-3.0-or-later WITH GCC-exception-3.1"}


def _component(**fields: str) -> Any:
    base = {"dist": "demo", "pattern": "demo.libs/libfoo-*.so*", "platform": "any", "spdx": "MIT"}
    base |= {"kind": "native", "notice": "", "note": ""}
    return notices.Component(**(base | fields))


def test_component_check(tmp_path: Path) -> None:
    info = _sample(tmp_path)
    allowed = {"MIT", "BSD-3-Clause"}
    assert notices.check_components([info], [_component()], allowed, []) == []
    unreviewed = notices.check_components([info], [], allowed, [])
    assert unreviewed == ["linux_x86_64: demo 1.0: native file without review: demo.libs/libfoo-123.so.1"]
    stale = notices.check_components(
        [info], [_component(), _component(pattern="demo.libs/gone*")], allowed, []
    )
    assert stale == ["linux_x86_64: demo: components.toml entry matches nothing: demo.libs/gone*"]
    unknown = [_component(spdx="NOASSERTION")]
    assert len(notices.check_components([info], unknown, allowed, [])) == 1
    gap = [{"component": "demo:demo.libs/libfoo-*.so*", "what": "text pending"}]
    assert notices.check_components([info], unknown, allowed, gap) == []  # listed for STOPP G1
    gpl = [_component(spdx="GPL-3.0-only")]
    assert "not on the native allowlist" in notices.check_components([info], gpl, allowed, [])[0]
    other_platform = [_component(platform="win_amd64")]
    assert notices.check_components([info], other_platform, allowed, [])[0].endswith("libfoo-123.so.1")


def test_render_is_deterministic_and_deduplicates_texts(tmp_path: Path) -> None:
    first = _sample(tmp_path)
    second = _sample(tmp_path, name="other")  # same licence text as the first wheel
    components = [_component(), _component(dist="other", pattern="other.libs/libfoo-*.so*")]
    text = notices.render([second, first], components, [{"component": "X", "what": "missing."}])
    assert text == notices.render([first, second], components, [{"component": "X", "what": "missing."}])
    assert notices.notice_packages(text) == {("demo", "1.0"), ("other", "1.0")}
    assert (
        text.count("MIT text") == 1
        and "Used by: demo 1.0 (linux_x86_64)" in text
        and "Used by: other 1.0" in text
    )
    assert "- X: missing. Text pending owner approval (G1)." in text
    assert "date" not in text.lower().split("6. licence texts")[0]


def test_validator_sources_from_the_source_map(tmp_path: Path) -> None:
    source_map = {
        "sources": [
            "file:///x/node_modules/.deno/ajv@8.20.0/node_modules/ajv/dist/core.js",
            "https://jsr.io/@std/path/1.1.2/mod.ts",
            "file:///x/src/own.ts",
            # packages that the prebuilt dist of a bundled package carries: no version in the map
            "../../node_modules/.deno/hed-validator@4.2.0/node_modules/hed-validator/node_modules/lodash/a.js",
            "../../node_modules/.deno/x@1.0.0/node_modules/x/node_modules/@nodable/entities/src/e.js",
        ],
        "sourcesContent": [
            "/* SPDX-License-Identifier: MIT */\nexport {}",
            "",
            "x",
            "/** @license ISC */",
            "",
        ],
    }
    path = tmp_path / "v.whl"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(notices.VALIDATOR_MAP, json.dumps(source_map))
    with zipfile.ZipFile(path) as archive:
        found, licences, unattributed = notices.validator_sources(archive)
    assert found == [  # by name, casefolded; never attributed to the package whose dist carries them
        ("npm", "@nodable/entities", "in x@1.0.0"),
        ("jsr", "@std/path", "1.1.2"),
        ("npm", "ajv", "8.20.0"),
        ("npm", "lodash", "in hed-validator@4.2.0"),
    ]
    assert licences == {("ajv", "8.20.0"): "MIT", ("lodash", "in hed-validator@4.2.0"): "ISC"}
    assert unattributed == ["file:///x/src/own.ts"]  # no package and not the validator's own build path


def _source_map_wheel(tmp_path: Path, entries: list[tuple[str, str]]) -> Path:
    path = tmp_path / "map.whl"
    source_map = {"sources": [s for s, _c in entries], "sourcesContent": [c for _s, c in entries]}
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(notices.VALIDATOR_MAP, json.dumps(source_map))
    return path


def test_every_licence_a_bundled_source_states_is_found(tmp_path: Path) -> None:
    """The isomorphic-git case: an SPDX-License-Identifier far past the head of a bundled file (a copied
    LGPL path.join) is found, and so is an SPDX line that is no plain expression."""
    copied = "/*!\n * copied from @zenfs/core/path\n * SPDX-License-Identifier: LGPL-3.0-or-later\n */"
    content = (
        "/* MIT package */\n" + "x = 1;\n" * 2000 + copied + "\n// SPDX-License-Identifier: GPL-2.0, see X\n"
    )
    assert len(content) > 4000
    path = _source_map_wheel(
        tmp_path,
        [("./node_modules/.deno/isomorphic-git@1.41.9/node_modules/isomorphic-git/index.cjs", content)],
    )
    with zipfile.ZipFile(path) as archive:
        _found, licences, _unattributed = notices.validator_sources(archive)
    assert licences == {("isomorphic-git", "1.41.9"): "GPL-2.0, see X / LGPL-3.0-or-later"}
    assert notices.stated_licences("/* SPDX-License-Identifier: */") == {"(empty SPDX-License-Identifier)"}
    assert notices.stated_licences("/** @license MIT */ /* SPDX-License-Identifier: 0BSD */") == {
        "MIT",
        "0BSD",
    }


def test_polyfills_and_own_sources_are_attributed(tmp_path: Path) -> None:
    """Every entry of the source map belongs to a package, to a polyfill's package or to the validator's own
    code; anything else is reported (the @jspm/core polyfills were once missed)."""
    polyfill = "// node_modules/@jspm/core/nodelibs/browser/chunk-A.js\n/** @license MIT */\n"
    polyfill += "// node_modules/@jspm/core/nodelibs/browser/fs.js\nexport {}\n"
    path = _source_map_wheel(
        tmp_path,
        [
            ("node-modules-polyfills:node:fs/promises", polyfill),
            ("node-modules-polyfills:node:path", "// node_modules/@jspm/core/nodelibs/browser/path.js\n"),
            ("node-modules-polyfills:node:os", "no marker"),
            ("../../src/main.ts", "// SPDX-License-Identifier: MIT\n"),
            ("../../deno.json", "{}"),
            ("../../vendor/thing.js", ""),
        ],
    )
    with zipfile.ZipFile(path) as archive:
        found, licences, unattributed = notices.validator_sources(archive)
    assert found == [("npm", "@jspm/core", notices.POLYFILL_FOUND)]
    assert licences == {("@jspm/core", notices.POLYFILL_FOUND): "MIT", notices.OWN: "MIT"}
    assert unattributed == ["node-modules-polyfills:node:os", "../../vendor/thing.js"]


def test_unattributed_entries_and_own_licences_are_problems(tmp_path: Path) -> None:
    folder = _third_party(tmp_path, [_mit("a")])
    packages = notices.load_validator_texts("9.9.9", folder)
    wheel = _validator_wheel([("npm", "a", "1.0.0")], {notices.OWN: "MIT"})
    assert notices.check_validator_texts(wheel, packages, []) == []
    wheel.unattributed = ["../../vendor/thing.js"]
    assert notices.check_validator_texts(wheel, packages, []) == [
        "linux_x86_64: bids-validator-deno 9.9.9: source-map entry of no package and not the validator's "
        "own: ../../vendor/thing.js"
    ]
    listed = [{"component": "bids-validator-deno:../../vendor/thing.js", "what": "gap"}]
    assert notices.check_validator_texts(wheel, packages, listed) == []  # an explicitly listed gap
    wheel.unattributed = []
    wheel.source_licenses = {notices.OWN: "LGPL-3.0-or-later"}
    assert "an own source states LGPL-3.0-or-later" in notices.check_validator_texts(wheel, packages, [])[0]


def test_committed_validator_wheel_is_fully_attributed() -> None:
    """With the locked validator wheel in .local/notices-wheels (or NEUROGRID_NOTICES_WHEELS): no entry of its
    source map is unattributed, the polyfills belong to @jspm/core, and the LGPL header that isomorphic-git
    copied from @zenfs/core is found in exactly the source-map entry that the version-bound exception names
    (D-16), which then holds."""
    locked = next(
        p for p in notices.runtime_packages("linux_x86_64") if canonicalize_name(p.name) == notices.VALIDATOR
    )
    wheel = notices.select_wheel(locked, "linux_x86_64")
    path = notices.find_wheel(wheel, _wheel_folders())
    if path is None:
        pytest.skip(f"{wheel.filename} is not in .local/notices-wheels")
    with zipfile.ZipFile(path) as archive:
        found, licences, unattributed = notices.validator_sources(archive)
    assert unattributed == []
    assert ("npm", "@jspm/core", notices.POLYFILL_FOUND) in found
    assert "LGPL-3.0-or-later" in licences[("isomorphic-git", "1.41.9")]
    packages = notices.load_validator_texts(locked.version) or []
    iso = next(p for p in packages if p.name == "isomorphic-git")
    assert "LGPL-3.0-or-later" in notices.spdx_units(iso.spdx) and not iso.owner_decision
    exceptions = notices.load_bundled_exceptions()
    (exception,) = [e for e in exceptions if e.package == "isomorphic-git"]
    info = notices.read_wheel(path, locked, "linux_x86_64", [])
    stating = [s for s, hints in info.source_statements.items() if "LGPL-3.0-or-later" in hints]
    assert stating == [exception.source]
    problems, excused = notices.check_exceptions(info, packages, exceptions)
    assert problems == [] and excused == {iso.key: {"LGPL-3.0-or-later"}}
    known = notices.load_known_missing()
    assert notices.check_validator_texts(info, packages, known, exceptions=exceptions) == []
    assert "is not permissive" in "\n".join(notices.check_validator_texts(info, packages, known))


# --- licence texts of the packages inside the validator bundle (D-15) ---------------------------------------


def _validator_wheel(sources: list[tuple[str, str, str]], stated: dict[tuple[str, str], str]) -> Any:
    return notices.WheelInfo(
        name="bids-validator-deno",
        version="9.9.9",
        target="linux_x86_64",
        filename="v.whl",
        sha256="0" * 64,
        license_expression="MIT",
        license_texts={},
        native=[],
        paths=["bids_validator_deno/bids-validator.js"],
        sources=sources,
        source_licenses=stated,
    )


def _third_party(folder: Path, packages: list[dict[str, Any]]) -> Path:
    """A license-gate/third_party folder with one manifest for validator 9.9.9; a text given as bytes
    ("data") is stored and recorded with its SHA-256."""
    base = notices.validator_texts_folder("9.9.9", folder)
    lines = ["version = 1", 'validator_version = "9.9.9"']
    for package in packages:
        lines.append("[[package]]")
        for key in ("registry", "name", "version", "found", "spdx", "note", "pending", "owner_decision"):
            if key in package:
                lines.append(f"{key} = {json.dumps(package[key])}")
        if "pending_licences" in package:
            lines.append(f"pending_licences = {json.dumps(package['pending_licences'])}")
        for expression, chosen in package.get("choices", []):
            lines += [
                "[[package.choice]]",
                f"expression = {json.dumps(expression)}",
                f"chosen = {json.dumps(chosen)}",
                'parts = "x.c"',
            ]
        for text in package.get("texts", []):
            if "repository_file" in text:  # a text of this repository (LICENSES/), recorded as it is
                kept = (ROOT / text["repository_file"]).read_bytes()
                lines += [
                    "[[package.text]]",
                    f"repository_file = {json.dumps(text['repository_file'])}",
                    'origin = "standard text"',
                    'kind = "standard text"',
                    f"size = {len(kept)}",
                    f"sha256 = {json.dumps(hashlib.sha256(kept).hexdigest())}",
                ]
                continue
            data: bytes = text["data"]
            (base / text["file"]).parent.mkdir(parents=True, exist_ok=True)
            (base / text["file"]).write_bytes(data)
            digest = text.get("sha256", hashlib.sha256(data).hexdigest())
            lines += [
                "[[package.text]]",
                f"file = {json.dumps(text['file'])}",
                'origin = "LICENSE"',
                'kind = "licence file"',
                f"size = {len(data)}",
                f"sha256 = {json.dumps(digest)}",
            ]
    base.mkdir(parents=True, exist_ok=True)
    (base / "manifest.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return folder


def _mit(name: str, **fields: Any) -> dict[str, Any]:
    text = {"file": f"npm/{name}@1.0.0/LICENSE", "data": f"MIT licence of {name}\n".encode()}
    return {"registry": "npm", "name": name, "version": "1.0.0", "spdx": "MIT", "texts": [text]} | fields


def test_validator_texts_cover_exactly_the_bundled_packages(tmp_path: Path) -> None:
    sources = [("npm", "a", "1.0.0"), ("npm", "b", "in a@1.0.0")]
    nested = {"registry": "npm", "name": "b", "found": "in a@1.0.0", "pending": "gap:b"}
    folder = _third_party(tmp_path, [_mit("a"), nested])
    packages = notices.load_validator_texts("9.9.9", folder)
    assert packages is not None and [p.key for p in packages] == sources
    wheel = _validator_wheel(sources, {("a", "1.0.0"): "MIT"})
    known = [{"component": "gap:b", "what": "no version"}]
    assert notices.check_validator_texts(wheel, packages, known) == []
    # a nested package without texts needs its known_missing.toml entry
    assert "'gap:b' is not listed" in notices.check_validator_texts(wheel, packages, [])[0]
    # the source map and the review must name the same packages
    extra = _validator_wheel([*sources, ("jsr", "@std/x", "1.0.0")], {})
    assert notices.check_validator_texts(extra, packages, known) == [
        "linux_x86_64: bids-validator-deno 9.9.9: bundled package without review: jsr @std/x 1.0.0"
    ]
    fewer = _validator_wheel(sources[:1], {})
    assert "stale review" in notices.check_validator_texts(fewer, packages, known)[0]
    assert "no reviewed licence texts" in notices.check_validator_texts(wheel, None, known)[0]
    assert notices.load_validator_texts("1.2.3", folder) is None


def test_validator_texts_are_checked_byte_for_byte_and_must_be_permissive(tmp_path: Path) -> None:
    sources = [("npm", "a", "1.0.0")]
    known: list[dict[str, str]] = []

    def problems(package: dict[str, Any], stated: dict[tuple[str, str], str] | None = None) -> list[str]:
        folder = _third_party(tmp_path / str(len(list(tmp_path.iterdir()))), [package])
        wheel = _validator_wheel(sources, stated or {})
        return notices.check_validator_texts(wheel, notices.load_validator_texts("9.9.9", folder), known)

    assert problems(_mit("a")) == []
    changed = _mit("a")
    changed["texts"][0]["sha256"] = "0" * 64
    assert "SHA-256 or size of npm/a@1.0.0/LICENSE differs" in problems(changed)[0]
    assert "is not permissive" in problems(_mit("a", spdx="GPL-3.0-only"))[0]
    assert "is not permissive" in problems(_mit("a", spdx="MIT AND LGPL-2.1-or-later"))[0]
    assert problems(_mit("a", spdx="MIT AND Zlib")) == []
    assert "states BSD-3-Clause" in problems(_mit("a"), {("a", "1.0.0"): "BSD-3-Clause"})[0]
    assert (
        "no licence text" in problems({"registry": "npm", "name": "a", "version": "1.0.0", "spdx": "MIT"})[0]
    )
    assert "without a reviewed licence" in problems(_mit("a", spdx=""))[0]
    folder = _third_party(tmp_path / "gone", [_mit("a")])
    (notices.validator_texts_folder("9.9.9", folder) / "npm" / "a@1.0.0" / "LICENSE").unlink()
    wheel = _validator_wheel(sources, {})
    found = notices.check_validator_texts(wheel, notices.load_validator_texts("9.9.9", folder), known)
    assert found == [
        "linux_x86_64: bids-validator-deno 9.9.9: npm a 1.0.0: licence text missing: npm/a@1.0.0/LICENSE"
    ]


def test_a_licence_outside_the_permissive_ones_needs_an_owner_decision(tmp_path: Path) -> None:
    """A truthful non-permissive licence (isomorphic-git: MIT AND LGPL-3.0-or-later) passes the component
    check only with a known_missing.toml entry that carries a decision; that entry keeps --check failing."""
    sources = [("npm", "a", "1.0.0")]
    lgpl = _mit("a", spdx="MIT AND LGPL-3.0-or-later", owner_decision="gap:a")
    folder = _third_party(tmp_path, [lgpl])
    packages = notices.load_validator_texts("9.9.9", folder)
    wheel = _validator_wheel(sources, {("a", "1.0.0"): "LGPL-3.0-or-later / MIT"})
    decided = [
        {"component": "gap:a", "what": "LGPL", "decision": "owner decision required (D-05 forbids LGPL)"}
    ]
    assert notices.check_validator_texts(wheel, packages, decided) == []
    no_decision = [{"component": "gap:a", "what": "LGPL"}]
    assert "is not listed with a decision" in notices.check_validator_texts(wheel, packages, no_decision)[0]
    assert "is not listed with a decision" in notices.check_validator_texts(wheel, packages, [])[0]
    # the review that once said MIT only: the LGPL header the source states is a problem
    mit = notices.load_validator_texts("9.9.9", _third_party(tmp_path / "mit", [_mit("a")]))
    assert "a bundled source states LGPL-3.0-or-later, the review says MIT" in "\n".join(
        notices.check_validator_texts(wheel, mit, [])
    )


COPYLEFT_DIR = "license-gate/third_party/bids-validator-3.0.2/npm/isomorphic-git@1.41.9"
COPYLEFT_TEXTS = (
    f"{COPYLEFT_DIR}/LICENSE.LGPL-3.0-or-later.txt",
    f"{COPYLEFT_DIR}/LICENSE.GPL-3.0-or-later.txt",
)
LGPL_SOURCE = "../../node_modules/.deno/a@1.0.0/node_modules/a/index.cjs"


def _exception(**fields: Any) -> Any:
    base: dict[str, Any] = {
        "decision": "D-16",
        "dist": "bids-validator-deno",
        "dist_version": "9.9.9",
        "registry": "npm",
        "package": "a",
        "version": "1.0.0",
        "source": LGPL_SOURCE,
        "spdx": "LGPL-3.0-or-later",
        "component": "path.join copied from elsewhere",
        "copyright": "Copyright (c) Example contributors",
        "location": "bids_validator_deno/bids-validator.js, lines 1 to 9",
        "source_code": "bids_validator_deno/bids-validator.js.map",
        "texts": COPYLEFT_TEXTS,
        "note": "",
    }
    return notices.BundledException(**(base | fields))


def _lgpl_package(version: str = "1.0.0", texts: tuple[str, ...] = COPYLEFT_TEXTS) -> dict[str, Any]:
    package = _mit("a", version=version, spdx="MIT AND LGPL-3.0-or-later")
    package["texts"] = [{"file": f"npm/a@{version}/LICENSE", "data": b"MIT licence of a\n"}]
    package["texts"] += [{"repository_file": name} for name in texts]
    return package


def _lgpl_wheel(version: str = "1.0.0", elsewhere: bool = False) -> Any:
    wheel = _validator_wheel([("npm", "a", version)], {("a", version): "LGPL-3.0-or-later / MIT"})
    source = LGPL_SOURCE.replace("1.0.0", version)
    wheel.source_statements = {source: ("LGPL-3.0-or-later", "MIT")}
    if elsewhere:
        wheel.source_statements["../../node_modules/.deno/a@1.0.0/node_modules/a/other.js"] = (
            "LGPL-3.0-or-later",
        )
    return wheel


def test_a_version_bound_exception_admits_exactly_its_part(tmp_path: Path) -> None:
    """D-16: an LGPL part passes only through an exception for exactly this validator version, package
    version and source-map entry, with the LGPL and GPL texts attached to the package."""
    packages = notices.load_validator_texts("9.9.9", _third_party(tmp_path, [_lgpl_package()]))
    assert packages is not None
    wheel = _lgpl_wheel()
    assert notices.check_validator_texts(wheel, packages, [], exceptions=[_exception()]) == []
    assert "is not permissive" in notices.check_validator_texts(wheel, packages, [])[0]
    # an exception for another wheel is not this one's
    other_dist = [_exception(dist="other-validator")]
    assert "is not permissive" in notices.check_validator_texts(wheel, packages, [], exceptions=other_dist)[0]
    # the review must name the licence, and the licence must be stated in exactly the named entry
    found = notices.check_validator_texts(wheel, packages, [], exceptions=[_exception(spdx="LGPL-2.1-only")])
    assert "the review of the package says MIT AND LGPL-3.0-or-later" in "\n".join(found)
    moved = notices.check_validator_texts(wheel, packages, [], exceptions=[_exception(source="x.js")])
    assert "the exception names x.js" in "\n".join(moved) and "is not permissive" in "\n".join(moved)
    twice = notices.check_validator_texts(
        _lgpl_wheel(elsewhere=True), packages, [], exceptions=[_exception()]
    )
    assert "a/other.js" in "\n".join(twice) and "is not permissive" in "\n".join(twice)
    # both texts must be attached to the package
    only_lgpl = _third_party(tmp_path / "lgpl", [_lgpl_package(texts=COPYLEFT_TEXTS[:1])])
    found = notices.check_validator_texts(
        wheel, notices.load_validator_texts("9.9.9", only_lgpl), [], exceptions=[_exception()]
    )
    assert f"{COPYLEFT_TEXTS[1]} is not attached" in "\n".join(found)
    assert "names no licence text" in "\n".join(
        notices.check_validator_texts(wheel, packages, [], exceptions=[_exception(texts=())])
    )


def test_a_version_bound_exception_fails_for_any_other_version(tmp_path: Path) -> None:
    """Another validator version or another version of the package fails the gate again (D-16)."""
    packages = notices.load_validator_texts("9.9.9", _third_party(tmp_path, [_lgpl_package()]))
    assert packages is not None
    wheel = _lgpl_wheel()
    older = notices.check_validator_texts(wheel, packages, [], exceptions=[_exception(dist_version="9.9.8")])
    assert any("does not hold for bids-validator-deno 9.9.9: review it again" in p for p in older)
    assert any("is not permissive" in p for p in older)
    upgraded = notices.load_validator_texts("9.9.9", _third_party(tmp_path / "up", [_lgpl_package("1.1.0")]))
    found = notices.check_validator_texts(_lgpl_wheel("1.1.0"), upgraded, [], exceptions=[_exception()])
    assert any("the bundle carries no a 1.0.0" in p for p in found)
    assert any(
        p.endswith(
            "npm a 1.1.0: licence MIT AND LGPL-3.0-or-later is not permissive (not in BUNDLED_ALLOWED)"
        )
        for p in found
    )


def test_the_committed_exception_is_bound_to_the_locked_versions() -> None:
    """The one exception of components.toml (D-16) names the locked validator 3.0.2 and isomorphic-git
    1.41.9, its texts are downloads approved by D-16, and the same review fails for any other validator
    version."""
    locked = next(
        p for p in notices.runtime_packages("linux_x86_64") if canonicalize_name(p.name) == notices.VALIDATOR
    )
    (exception,) = notices.load_bundled_exceptions()
    assert (exception.decision, exception.dist, exception.dist_version) == (
        "D-16",
        notices.VALIDATOR,
        "3.0.2",
    )
    assert locked.version == exception.dist_version
    assert (exception.registry, exception.package, exception.version) == ("npm", "isomorphic-git", "1.41.9")
    assert exception.spdx == "LGPL-3.0-or-later" and exception.texts == COPYLEFT_TEXTS
    assert "James Prevett and other ZenFS contributors" in exception.copyright
    assert "bids-validator.js" in exception.location and "bids-validator.js.map" in exception.source_code
    recorded = tomllib.loads((ROOT / "license-gate" / "licence_texts.toml").read_text(encoding="utf-8"))
    decisions = {item["path"]: item["decision"] for item in recorded["text"]}
    assert all(decisions[name] == "D-16" for name in exception.texts)
    packages = notices.load_validator_texts(locked.version) or []
    iso = next(p for p in packages if p.name == exception.package)
    wheel = _validator_wheel([iso.key], {(iso.name, iso.found): "LGPL-3.0-or-later / MIT"})
    wheel.version = locked.version
    wheel.source_statements = {exception.source: ("LGPL-3.0-or-later", "MIT")}
    assert notices.check_exceptions(wheel, packages, [exception]) == ([], {iso.key: {"LGPL-3.0-or-later"}})
    wheel.version = "3.0.3"
    problems, excused = notices.check_exceptions(wheel, packages, [exception])
    assert excused == {} and "does not hold for bids-validator-deno 3.0.3" in problems[0]
    gaps = {item["component"] for item in notices.load_known_missing()}
    assert not {g for g in gaps if "isomorphic-git" in g or g == "LGPL-3.0-or-later"}


def test_the_notices_name_the_exception_with_its_texts(tmp_path: Path) -> None:
    folder = _third_party(tmp_path, [_lgpl_package()])
    wheel = _lgpl_wheel()
    text = notices.render([wheel], [], [], third_party=folder, exceptions=[_exception()])
    section = " ".join(text.split("\n3. ", 1)[1].split("\n6. ", 1)[0].split())
    assert "MIT AND LGPL-3.0-or-later (exception D-16: below)" in section
    assert notices.EXCEPTIONS_HEADING in section
    for value in ("Copyright (c) Example contributors", "lines 1 to 9", LGPL_SOURCE, "bids-validator.js.map"):
        assert value in section, value
    assert f"Licence texts: {COPYLEFT_TEXTS[0]}, {COPYLEFT_TEXTS[1]} (section 6)" in section
    texts = list(notices.iter_texts(text))
    assert any(t.startswith("GNU LESSER GENERAL PUBLIC LICENSE") for t in texts)
    assert any(t.startswith("GNU GENERAL PUBLIC LICENSE") for t in texts)
    other = notices.render([wheel], [], [], third_party=folder, exceptions=[_exception(dist_version="1")])
    assert notices.EXCEPTIONS_HEADING not in other and "exception D-16" not in other


def test_the_committed_notices_name_the_exception() -> None:
    text = " ".join(_committed().split())
    (exception,) = notices.load_bundled_exceptions()
    for value in (exception.copyright, exception.location, exception.source, exception.source_code):
        assert " ".join(value.split()) in text, value
    assert "MIT AND LGPL-3.0-or-later (exception D-16: below)" in text


def test_a_package_without_review_may_state_permissive_licences_only(tmp_path: Path) -> None:
    sources = [("npm", "@jspm/core", notices.POLYFILL_FOUND)]
    gap = {"registry": "npm", "name": "@jspm/core", "found": notices.POLYFILL_FOUND, "pending": "gap:jspm"}
    packages = notices.load_validator_texts("9.9.9", _third_party(tmp_path, [gap]))
    known = [{"component": "gap:jspm", "what": "no version"}]
    permissive = _validator_wheel(sources, {("@jspm/core", notices.POLYFILL_FOUND): "MIT"})
    assert notices.check_validator_texts(permissive, packages, known) == []
    lgpl = _validator_wheel(sources, {("@jspm/core", notices.POLYFILL_FOUND): "LGPL-3.0-only"})
    assert (
        "states LGPL-3.0-only, there is no reviewed licence"
        in notices.check_validator_texts(lgpl, packages, known)[0]
    )


def _policy_problems(tmp_path: Path, package: dict[str, Any], known: list[dict[str, str]]) -> list[str]:
    folder = _third_party(tmp_path / str(len(list(tmp_path.iterdir()))), [package])
    wheel = _validator_wheel([("npm", "a", "1.0.0")], {})
    return notices.check_validator_texts(wheel, notices.load_validator_texts("9.9.9", folder), known)


def test_public_domain_counts_as_permissive(tmp_path: Path) -> None:
    """D-16: a public-domain dedication (LicenseRef-Public-Domain) is permissive, another LicenseRef only once
    reviewed (D-17: the zlib-like terms of Stephan Brumme's code)."""
    assert "LicenseRef-Public-Domain" in notices.BUNDLED_ALLOWED
    assert _policy_problems(tmp_path, _mit("a", spdx="MIT AND LicenseRef-Public-Domain"), []) == []
    other = _policy_problems(tmp_path, _mit("a", spdx="MIT AND LicenseRef-Not-Stated"), [])
    assert len(other) == 1 and "is not permissive" in other[0]
    d17 = {"LicenseRef-Brumme-Disclaimer", "Unicode-3.0", "Unlicense", "W3C-20150513"}
    assert d17 <= notices.BUNDLED_ALLOWED and d17 <= notices.SITE_ALLOWED
    assert _policy_problems(tmp_path, _mit("a", spdx="MIT AND LicenseRef-Brumme-Disclaimer"), []) == []
    # the libraries of the bundled Python add the Tcl, X11 and bzip2 terms, never a copyleft licence
    assert {"TCL", "X11", "bzip2-1.0.6", "LicenseRef-itcl"} <= notices.LIBRARY_ALLOWED
    assert not {unit for unit in notices.LIBRARY_ALLOWED if "GPL" in unit or "MPL" in unit}


def test_a_choice_with_a_permissive_option_is_permissive(tmp_path: Path) -> None:
    """D-16: 'CC0-1.0 OR OpenSSL OR Apache-2.0' is permissive once the manifest names the permissive option
    NeuroGrid uses; a choice without a permissive option is not, and a recorded choice must be in the
    licence."""
    spdx = "MIT AND (CC0-1.0 OR OpenSSL OR Apache-2.0)"
    choice = ("CC0-1.0 OR OpenSSL OR Apache-2.0", "Apache-2.0")
    assert _policy_problems(tmp_path, _mit("a", spdx=spdx, choices=[choice]), []) == []
    reordered = ("Apache-2.0 OR CC0-1.0 OR OpenSSL", "Apache-2.0")  # the same choice in another order
    assert _policy_problems(tmp_path, _mit("a", spdx=spdx, choices=[reordered]), []) == []
    unnamed = _policy_problems(tmp_path, _mit("a", spdx=spdx), [])
    assert unnamed == [
        "linux_x86_64: bids-validator-deno 9.9.9: npm a 1.0.0: the choice Apache-2.0 OR CC0-1.0 OR OpenSSL "
        "names no chosen permissive option (D-16)"
    ]
    openssl = _policy_problems(tmp_path, _mit("a", spdx=spdx, choices=[(choice[0], "OpenSSL")]), [])
    assert len(openssl) == 1 and "OpenSSL is no permissive option of the choice" in openssl[0]
    no_permissive = _mit(
        "a", spdx="MIT AND (GPL-2.0-only OR OpenSSL)", choices=[("GPL-2.0-only OR OpenSSL", "OpenSSL")]
    )
    assert any("is not permissive" in p for p in _policy_problems(tmp_path, no_permissive, []))
    stale = _policy_problems(tmp_path, _mit("a", choices=[choice]), [])
    assert len(stale) == 1 and "is not part of the licence MIT" in stale[0]
    single = _policy_problems(tmp_path, _mit("a", choices=[("MIT", "MIT")]), [])
    assert len(single) == 1 and "is no choice of licences" in single[0]
    broken = _policy_problems(tmp_path, _mit("a", spdx="MIT AND (Zlib"), [])
    assert any("is no SPDX expression" in p for p in broken)


def test_licences_of_parts_without_texts_wait_with_their_gap(tmp_path: Path) -> None:
    """A licence of parts whose texts are missing (pending_licences) passes only together with the text
    gap (pending), which keeps --check failing; it is no decision of its own."""
    spdx = "MIT AND LicenseRef-Not-Stated"
    waiting = _mit("a", spdx=spdx, pending="gap:a", pending_licences=["LicenseRef-Not-Stated"])
    known = [{"component": "gap:a", "what": "texts of LicenseRef-Not-Stated"}]
    assert _policy_problems(tmp_path, waiting, known) == []
    without_gap = _mit("a", spdx=spdx, pending_licences=["LicenseRef-Not-Stated"])
    found = _policy_problems(tmp_path, without_gap, [])
    assert any("pending_licences without a gap" in p for p in found)
    assert any("is not permissive" in p for p in found)
    stale = _mit("a", pending="gap:a", pending_licences=["LicenseRef-Not-Stated"])
    assert any(
        "pending licence LicenseRef-Not-Stated is not part" in p
        for p in _policy_problems(tmp_path, stale, known)
    )
    # a pending licence never excuses one that is outside the policy and not listed as pending
    other = _mit(
        "a",
        spdx=spdx + " AND GPL-3.0-only",
        pending="gap:a",
        pending_licences=["LicenseRef-Not-Stated"],
    )
    assert any("is not permissive" in p for p in _policy_problems(tmp_path, other, known))


def test_the_notices_name_the_chosen_option(tmp_path: Path) -> None:
    spdx = "MIT AND (CC0-1.0 OR OpenSSL OR Apache-2.0)"
    package = _mit("a", spdx=spdx, choices=[("CC0-1.0 OR OpenSSL OR Apache-2.0", "Apache-2.0")])
    folder = _third_party(tmp_path, [package])
    text = notices.render([_validator_wheel([("npm", "a", "1.0.0")], {})], [], [], third_party=folder)
    section = text.split("\n3. ", 1)[1].split("\n6. ", 1)[0]
    assert f"{spdx} (choice: below)" in section
    assert notices.CHOICES_HEADING in section
    assert "- npm a 1.0.0: CC0-1.0 OR OpenSSL OR Apache-2.0 (x.c) - chosen: Apache-2.0" in section
    assert "LicenseRef-Public-Domain" in " ".join(section.split())  # the policy names it


def test_committed_hash_wasm_follows_the_licence_policy() -> None:
    """D-16 applied to hash-wasm 4.12.0: no owner decision is pending any more and both choices name
    Apache-2.0 (whose text is attached). D-17 closed its text gap: the Brumme parts carry the excerpt of the
    licence section of Stephan Brumme's page (with the page's SHA-256), argon2 the BSD-3-Clause LICENSE of
    the Go code it is based on."""
    locked = next(
        p for p in notices.runtime_packages("linux_x86_64") if canonicalize_name(p.name) == notices.VALIDATOR
    )
    packages = {p.name: p for p in notices.load_validator_texts(locked.version) or []}
    hash_wasm = packages["hash-wasm"]
    assert not hash_wasm.owner_decision
    assert {(c.expression, c.chosen) for c in hash_wasm.choices} == {
        ("CC0-1.0 OR OpenSSL OR Apache-2.0", "Apache-2.0"),
        ("CC0-1.0 OR Apache-2.0", "Apache-2.0"),
    }
    assert "LICENSES/Apache-2.0.txt" in {t.label for t in hash_wasm.texts}
    assert not hash_wasm.pending_licences and not hash_wasm.pending
    units = notices.spdx_units(hash_wasm.spdx)
    assert {"LicenseRef-Brumme-Disclaimer", "BSD-3-Clause"} <= units and "LicenseRef-Not-Stated" not in units
    by_kind = {t.kind: t for t in hash_wasm.texts if "brumme" in t.label or "argon2-golang" in t.label}
    assert set(by_kind) == {notices.EXCERPT, "licence file"}
    excerpt = by_kind[notices.EXCERPT]
    assert excerpt.url == "https://create.stephan-brumme.com/disclaimer.html"
    page = "5f715c9dbeb48101fe36b28ceeb7af56325d20534bfdd791eebad8a622189ef1"
    assert page in excerpt.origin and (excerpt.source_size, excerpt.source_sha256) == (23966, page)
    assert excerpt.path.read_text(encoding="utf-8").startswith("License\n\nUnless otherwise noted,")
    assert by_kind["licence file"].url.startswith("https://raw.githubusercontent.com/golang/crypto/948cd5f3")
    outside, problems = notices.licence_policy(hash_wasm, notices.BUNDLED_ALLOWED)
    assert outside == set() and problems == []
    gaps = {item["component"]: item for item in notices.load_known_missing()}
    assert not [c for c in gaps if "hash-wasm" in c]
    committed = _committed()
    assert (
        "- npm hash-wasm 4.12.0: CC0-1.0 OR OpenSSL OR Apache-2.0 (blake2b, blake2s) - chosen: Apache-2.0"
        in (committed)
    )
    assert "- npm hash-wasm 4.12.0: CC0-1.0 OR Apache-2.0 (blake3) - chosen: Apache-2.0" in committed


def test_gaps_name_what_they_wait_for() -> None:
    assert notices.gap_status({"component": "x", "what": "y"}) == notices.PENDING
    decided = {"component": "x", "what": "y", "decision": "owner decision required (D-05 forbids LGPL)"}
    assert notices.gap_status(decided) == "Owner decision required (D-05 forbids LGPL) (G1)"
    text = notices.render([], [], [decided])
    assert "- x: y Owner decision required (D-05 forbids LGPL) (G1)." in text


def test_render_names_the_reviewed_licences_and_copies_their_texts(tmp_path: Path) -> None:
    sources = [("npm", "a", "1.0.0"), ("npm", "b", "in a@1.0.0")]
    nested = {"registry": "npm", "name": "b", "found": "in a@1.0.0", "pending": "gap:b", "note": "no version"}
    folder = _third_party(tmp_path, [_mit("a"), nested])
    wheel = _validator_wheel(sources, {})
    text = notices.render([wheel], [], [{"component": "gap:b", "what": "no version."}], third_party=folder)
    section = text.split("\n3. ", 1)[1].split("\n5. ", 1)[0]
    assert "license-gate/third_party/bids-validator-9.9.9/manifest.toml" in " ".join(section.split())
    rows = [line.split() for line in section.splitlines() if line.startswith("npm ")]
    assert rows == [
        ["npm", "a", "1.0.0", "MIT", "licence", "file"],
        ["npm", "b", "in", "a@1.0.0", "pending", "missing", "(section", "5)"],
    ]
    assert "- npm b in a@1.0.0: no version" in section
    assert "Used by: bids-validator-deno 9.9.9 bundle: npm a 1.0.0: LICENSE" in text
    assert "MIT licence of a" in list(notices.iter_texts(text))[0]


def test_committed_validator_texts_match_their_manifest() -> None:
    """Every stored text of license-gate/third_party has its recorded SHA-256 and size, every file there is in
    a manifest, each licence is permissive and each pending package names a listed gap (D-15)."""
    locked = next(
        p for p in notices.runtime_packages("linux_x86_64") if canonicalize_name(p.name) == notices.VALIDATOR
    )
    packages = notices.load_validator_texts(locked.version)
    assert packages is not None, "license-gate/third_party has no manifest for the locked validator"
    base = notices.validator_texts_folder(locked.version)
    gaps = notices.load_known_missing()
    known = {item["component"] for item in gaps}
    decisions = {item["component"]: item for item in gaps if item.get("decision")}
    listed = set()
    crlf = []
    excepted = {
        (e.registry, e.package, e.version): notices.spdx_units(e.spdx)
        for e in notices.load_bundled_exceptions()
        if e.dist_version == locked.version
    }
    for package in packages:
        outside, policy = notices.licence_policy(package, notices.BUNDLED_ALLOWED)  # D-16 choices
        assert policy == [], (package.name, policy)
        outside -= excepted.get((package.registry, package.name, package.version), set())  # D-16
        if outside:  # only with the owner's decision pending: the gap names each licence, the release fails
            assert package.owner_decision in decisions, package
            what = decisions[package.owner_decision]["what"]
            assert all(unit.split()[-1] in what for unit in outside), (package.name, outside)
        if package.pending_licences:  # licences of parts without texts: the text gap names each of them
            assert package.pending in known and not package.owner_decision, package
            what = next(item["what"] for item in gaps if item["component"] == package.pending)
            assert all(unit in what for unit in package.pending_licences), package.name
        assert not package.owner_decision or package.owner_decision in decisions, package
        assert package.texts or package.pending in known, package
        assert not package.pending or package.pending in known, package
        for text in package.texts:
            data = text.path.read_bytes()
            assert hashlib.sha256(data).hexdigest() == text.sha256 and len(data) == text.size, text.label
            if b"\r" in data:
                crlf.append(text.label)
            assert text.kind in notices.TEXT_KINDS, text.label
            if text.kind == "licence file":  # D-15: npm and jsr; D-17: the repositories on GitHub
                assert text.url.startswith(
                    ("https://registry.npmjs.org/", "https://jsr.io/", "https://raw.githubusercontent.com/")
                ), text.label
            listed.add(text.path.resolve())
    stored = {p.resolve() for p in base.rglob("*") if p.is_file() and p.name != "manifest.toml"}
    assert stored <= listed, sorted(str(p) for p in stored - listed)
    # LF only, so that git (eol=lf) keeps the bytes and the hash; the one exception is the LICENSE of
    # @jspm/core 2.1.0, kept with the CRLF endings of its npm tarball (D-17), which .gitattributes marks -text
    assert crlf == ["npm/@jspm/core@2.1.0/LICENSE"], crlf
    path = (base / crlf[0]).relative_to(ROOT).as_posix()
    attributes = subprocess.run(
        ["git", "check-attr", "text", "--", path], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    assert attributes.strip() == f"{path}: text: unset", attributes
    assert len({p.key for p in packages}) == len(packages) > 70
    schema = next(p for p in packages if p.name == "@bids/schema")
    assert schema.spdx == "CC-BY-4.0" and schema.texts[0].label.endswith("@bids/schema@1.2.7/LICENSE")
    by_name = {p.name: p for p in packages}
    # a licence named in the expression has its text attached (the Apache 'Used by' line names the package)
    s3 = by_name["@bradenmacdonald/s3-lite-client"]
    assert "Apache-2.0" in notices.spdx_units(s3.spdx)
    assert "LICENSES/Apache-2.0.txt" in {t.label for t in s3.texts}
    # hash-wasm: the expression of all its stored headers, not only the MIT of its LICENSE
    hash_wasm = notices.spdx_units(by_name["hash-wasm"].spdx)
    assert {"MIT", "0BSD", "Zlib", "BSD-2-Clause", "Apache-2.0", "CC0-1.0", "OpenSSL"} <= hash_wasm
    # D-17: a package without a version in the source map has the version of its lockfile, openly marked
    # where only the lockfile proves it (the 33 packages inside @jspm/core)
    jspm = by_name["@jspm/core"]
    assert jspm.version == "2.1.0" and len(jspm.texts) == 34 and "nur über Lockfile belegt" in jspm.note
    inside = [t for t in jspm.texts if t.label != "npm/@jspm/core@2.1.0/LICENSE"]
    assert all("version only proven by the jspm-core lockfile" in t.origin for t in inside)
    nested = [p for p in packages if p.found == "in hed-validator@4.2.0"]
    assert len(nested) == 9 and all(p.version and p.texts and p.spdx for p in nested)
    assert "Unicode-3.0" in notices.spdx_units(by_name["unicode-name"].spdx)
    manifest = tomllib.loads((base / "manifest.toml").read_text(encoding="utf-8"))
    assert "only to extract" in manifest["downloads"] and "no tarball is kept" in manifest["downloads"]


def test_repository_notices_must_exist(tmp_path: Path) -> None:
    info = _sample(tmp_path)
    allowed = {"MIT"}
    kept = _component(notice="LICENSES/CC-BY-4.0.txt")
    assert notices.check_components([info], [kept], allowed, []) == []
    absent = _component(notice="LICENSES/absent.txt")
    assert notices.check_components([info], [absent], allowed, []) == [
        "linux_x86_64: demo: notice not in the repository: LICENSES/absent.txt"
    ]
    text = notices.render([info], [kept], [])
    assert "Used by: demo 1.0: demo.libs/libfoo-*.so* (MIT)" in text
    assert "Creative Commons Attribution 4.0 International" in text


def test_a_note_naming_a_moved_text_is_found(tmp_path: Path) -> None:
    """R27: the notes of the manifests are prose; a text moved away from LICENSES/ must not stay named."""
    (tmp_path / "LICENSES").mkdir()
    (tmp_path / "LICENSES" / "MIT.txt").write_text("MIT\n", encoding="utf-8")
    kept = tmp_path / "license-gate" / "third_party" / "a@1.0.0"
    kept.mkdir(parents=True)
    (kept / "LICENSE.LGPL-3.0-or-later.txt").write_text("LGPL\n", encoding="utf-8")
    text = (
        "The texts are LICENSES/MIT.txt and LICENSES/LGPL-3.0-or-later.txt (moved). Kept next to it: "
        "license-gate/third_party/a@1.0.0/LICENSE.LGPL-3.0-or-later.txt. A bundled source names src/md5.c, "
        "tools/gyp and vendor/LICENSES/X.txt, which are no files of the repository."
    )
    assert notices.missing_repository_paths(text, tmp_path) == ["LICENSES/LGPL-3.0-or-later.txt"]
    fixed = text.replace(" and LICENSES/LGPL-3.0-or-later.txt", "")
    assert notices.missing_repository_paths(fixed, tmp_path) == []


def test_committed_notices_and_notes_name_only_existing_repository_files() -> None:
    """R27: neither the committed notices nor a note of license-gate names a repository file that is gone,
    e.g. the copyleft texts of the D-16 exception after they moved next to isomorphic-git."""
    assert notices.missing_repository_paths(_committed()) == []
    for path in sorted((ROOT / "license-gate").rglob("*.toml")):
        named = path.read_text(encoding="utf-8")
        assert notices.missing_repository_paths(named) == [], path.relative_to(ROOT)


# --- files and downloads ------------------------------------------------------------------------------------


def test_find_file_checks_the_hash(tmp_path: Path) -> None:
    (tmp_path / "a.whl").write_bytes(b"abc")
    good = hashlib.sha256(b"abc").hexdigest()
    assert notices.find_file("a.whl", good, [tmp_path]) == tmp_path / "a.whl"
    (tmp_path / good).write_bytes(b"abc")  # the bundle cache names files by their SHA-256
    assert notices.find_file("missing.whl", good, [tmp_path]) == tmp_path / good
    with pytest.raises(notices.NoticeError):
        notices.find_file("a.whl", "0" * 64, [tmp_path])
    assert notices.find_file("b.whl", good, [tmp_path / "none"]) is None


class _Response(io.BytesIO):
    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def test_download_only_pinned_sources_and_only_matching_bytes(tmp_path: Path, monkeypatch: Any) -> None:
    calls: list[str] = []

    def fake_urlopen(url: str, timeout: int) -> _Response:
        calls.append(url)
        return _Response(b"payload")

    monkeypatch.setattr(notices.urllib.request, "urlopen", fake_urlopen)
    good = hashlib.sha256(b"payload").hexdigest()
    with pytest.raises(notices.NoticeError):
        notices.download_file("https://example.org/x.whl", "x.whl", good, 7, tmp_path)
    assert calls == []  # refused before any connection
    url = "https://files.pythonhosted.org/packages/x.whl"
    with pytest.raises(notices.NoticeError):
        notices.download_file(url, "x.whl", "0" * 64, 7, tmp_path)
    assert not list(tmp_path.iterdir())  # nothing left behind
    assert notices.download_file(url, "x.whl", good, 7, tmp_path).read_bytes() == b"payload"


# --- parts of the offline bundle ----------------------------------------------------------------------------


def _bundle_lock(folder: Path, pbs: bytes, uv: bytes) -> Path:
    def entry(name: str, data: bytes) -> dict[str, Any]:
        return {
            "url": f"https://example.org/{name}",
            "sha256": hashlib.sha256(data).hexdigest(),
            "size": len(data),
        }

    data = {
        "format_version": 1,
        "python": {
            "version": "3.12.15",
            "build": "20261009",
            "platforms": {t: entry(f"cpython-3.12.15%2B20261009-{t}.tar.gz", pbs) for t in notices.TARGETS},
        },
        "uv": {
            "version": "0.13.0",
            "platforms": {t: entry(f"uv-0.13.0-{t}.whl", uv) for t in notices.TARGETS},
        },
        "remove": {
            "linux_x86_64": [{"path": "python/lib/python3.12/lib-dynload/_dbm.so", "reason": "Sleepycat"}]
        },
    }
    path = folder / "bundle_lock.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _tar(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def test_bundle_parts_are_read_from_the_pinned_files(tmp_path: Path, monkeypatch: Any) -> None:
    pbs = _tar(
        {
            "python/LICENSE.txt": b"PSF licence",
            "python/Lib/site-packages/pip-26.2.1.dist-info/licenses/LICENSE.txt": b"pip MIT",
            "python/python.exe": b"MZ",
        }
    )
    uv_buffer = io.BytesIO()
    with zipfile.ZipFile(uv_buffer, "w") as archive:
        archive.writestr("uv-0.13.0.dist-info/METADATA", "License-Expression: MIT OR Apache-2.0\n")
        archive.writestr("uv-0.13.0.dist-info/licenses/LICENSE-MIT", "uv MIT")
    uv = uv_buffer.getvalue()
    lock = _bundle_lock(tmp_path, pbs, uv)
    folder = tmp_path / "files"
    folder.mkdir()
    for target in notices.TARGETS:
        (folder / f"cpython-3.12.15+20261009-{target}.tar.gz").write_bytes(pbs)
        (folder / f"uv-0.13.0-{target}.whl").write_bytes(uv)
    monkeypatch.setenv("NEUROGRID_BUNDLE_CACHE", str(tmp_path / "cache"))
    parts, missing = notices.collect_bundle([folder], fetch=False, cache=tmp_path / "dl", bundle_lock=lock)
    assert missing == [] and len(parts) == 4
    python = next(p for p in parts if p.name == notices.PBS and p.target == "linux_x86_64")
    assert python.version == "3.12.15+20261009" and python.license_expression == "Python-2.0"
    assert set(python.license_texts) == {
        "python/LICENSE.txt",
        "python/Lib/site-packages/pip-26.2.1.dist-info/licenses/LICENSE.txt",
    }
    assert python.removed == [("python/lib/python3.12/lib-dynload/_dbm.so", "Sleepycat")]
    uv_part = next(p for p in parts if p.name == notices.UV)
    assert uv_part.license_expression == "MIT OR Apache-2.0"
    components, allowed = notices.load_components()
    assert notices.check_components([], components, allowed, [], parts) == []
    text = notices.render([], components, [], parts)
    assert (
        "Offline bundle parts as pinned in packaging/bundle_lock.json" in text
        and "_dbm.so - Sleepycat" in text
    )
    assert "Used by: python-build-standalone 3.12.15+20261009 (win_amd64): python/LICENSE.txt" in text
    newer = [p for p in parts if p.name == notices.UV]
    newer[0].version = "0.14.0"
    assert "no reviewed entry" in notices.check_components([], components, allowed, [], newer)[0]
    without_licence = tmp_path / "plain.tar.gz"
    without_licence.write_bytes(_tar({"python/python.exe": b"MZ"}))
    with pytest.raises(notices.NoticeError):
        notices.read_pbs(without_licence, notices.Pinned(notices.PBS, "1", "win_amd64", "u", "s", 1), "x", [])
    assert notices.bundle_pins(tmp_path / "absent.json") == ([], {})


# --- the reviewed component list and the --check gate -------------------------------------------------------


def test_component_list_is_reviewed_and_consistent() -> None:
    components, allowed = notices.load_components()
    kinds = {"native", "bundled", "notice", "external", "bundle", "not_distributed"}
    for component in components:
        assert component.kind in kinds and component.platform in {"any", *notices.TARGETS}, component
        assert component.spdx and component.dist and component.pattern, component
        if component.kind in ("native", "bundled") and component.spdx != "NOASSERTION":
            assert notices.spdx_units(component.spdx) <= allowed, component
    keys = {f"{c.dist}:{c.pattern}" for c in components}
    texts = {path.stem for path in (ROOT / "LICENSES").glob("*.txt")}
    for item in notices.load_known_missing():
        assert item["component"] in keys or item["component"] not in texts, item  # a component or a licence
        assert item["what"].strip(), item
    unknown = [f"{c.dist}:{c.pattern}" for c in components if c.spdx == "NOASSERTION"]
    assert set(unknown) <= {item["component"] for item in notices.load_known_missing()}
    assert "GPL-3.0-or-later WITH GCC-exception-3.1" in allowed and "GPL-3.0-or-later" not in allowed


TOOL_CALL = re.compile(r"tools/(notices|licenses|build_docs|gen_docs)\.py([^`'\"\n]*)")
OPTION = re.compile(r"(?<![\w-])--[a-z][a-z0-9-]*")


def _tool_calls() -> list[tuple[str, str, str]]:
    """(file, tool, option) for every option named after one of the documentation area's tools in the gate
    files, the workflows, the documentation, the README, the tools and the tests."""
    files = [
        *(ROOT / "license-gate").glob("*.toml"),
        *(ROOT / ".github" / "workflows").glob("*.yml"),
        ROOT / "README.md",
        ROOT / "mkdocs.yml",
        *(ROOT / "docs" / "en").rglob("*.md"),
        *(ROOT / "docs" / "zh").rglob("*.md"),
        *(ROOT / "tools").glob("*.py"),
        *(ROOT / "tests").rglob("*.py"),
    ]
    calls = []
    for path in files:
        for match in TOOL_CALL.finditer(path.read_text(encoding="utf-8")):
            for option in OPTION.findall(match.group(2)):
                calls.append((path.relative_to(ROOT).as_posix(), match.group(1), option))
    return calls


def _unknown_options(calls: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    sources = {tool: (ROOT / "tools" / f"{tool}.py").read_text(encoding="utf-8") for _p, tool, _o in calls}
    return [(path, tool, option) for path, tool, option in calls if f'"{option}"' not in sources[tool]]


def test_every_named_option_of_the_gate_tools_exists() -> None:
    """A command line named in a gate file, workflow or page runs; the gate for missing texts is
    `tools/notices.py --check` (the release runs it with --download), not an option of tools/licenses.py."""
    calls = _tool_calls()
    assert ("license-gate/known_missing.toml", "notices", "--check") in calls
    assert _unknown_options(calls) == []
    line = "list is not empty (tools/" + "licenses.py --release). The notices and the REUSE test name it."
    found = [("x", m.group(1), o) for m in TOOL_CALL.finditer(line) for o in OPTION.findall(m.group(2))]
    assert _unknown_options(found) == [("x", "licenses", "--release")]  # the comment this test replaced


def test_check_fails_while_texts_are_missing(tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
    """The release runs `tools/notices.py --download --check`: it fails on outdated notices and while
    license-gate/known_missing.toml lists a gap (B3, STOPP G1)."""
    info = _sample(tmp_path)
    monkeypatch.setattr(notices, "collect", lambda *a, **k: ([info], []))
    monkeypatch.setattr(notices, "collect_bundle", lambda *a, **k: ([], []))
    monkeypatch.setattr(notices, "load_components", lambda: ([_component()], {"MIT"}))
    target = tmp_path / "NOTICES.txt"
    monkeypatch.setattr(notices, "NOTICES", target)
    monkeypatch.setattr(notices, "load_known_missing", lambda: [])
    # the documentation site has its own test (its pending parts refer to the real known_missing.toml)
    monkeypatch.setattr(notices, "check_site_review", lambda site, known: [])
    assert notices.main(["--check"]) == 1  # no file yet: outdated
    assert notices.main(["--out", str(target)]) == 0
    assert notices.main(["--check"]) == 0
    gap = [{"component": "CC-BY-4.0", "what": "legal code"}]
    monkeypatch.setattr(notices, "load_known_missing", lambda: gap)
    assert notices.main(["--out", str(target)]) == 0
    capsys.readouterr()
    assert notices.main(["--check"]) == 1
    assert "incomplete: CC-BY-4.0" in capsys.readouterr().out
    monkeypatch.setattr(notices, "collect", lambda *a, **k: ([], ["x.whl"]))
    assert notices.main(["--check"]) == 2


SITE_PARTS = (
    "mkdocs-material",
    "rxjs",
    "tslib",
    "clipboard",
    "escape-html",
    "focus-visible",
    "lunr",
    "material-design-color",
    "Material Design Icons",
    "Octicons",
    "Font Awesome Free",
    "Noto Sans SC",
)


def test_the_documentation_site_is_reviewed_and_listed_in_the_notices() -> None:
    """R19, TECH-10, NG-N07: every third-party part of the documentation site that the bundle and the release
    ship is in THIRD_PARTY_NOTICES.txt with its licence and texts; parts whose licence or text the shipped
    files do not state are known gaps (the release fails while they remain)."""
    version = notices.locked_version(notices.SITE_THEME)
    review = notices.load_site_review(version)
    assert version == "9.7.7" and review is not None
    assert tuple(p.name for p in review.packages) == SITE_PARTS
    known = notices.load_known_missing()
    assert notices.check_site_review(review, known) == []
    text = (ROOT / "THIRD_PARTY_NOTICES.txt").read_text(encoding="utf-8")
    section = text.split("\n4. Components outside the wheels", 1)[1].split("\n5. ", 1)[0]
    assert (
        "Documentation site (docs/ of the offline bundle and of the release, mkdocs-material 9.7.7):"
        in section
    )
    for name in SITE_PARTS:
        assert name in section, name
    assert "assets/javascripts/lunr/**, **/*.map" in section
    gaps = text.split("\n5. ", 1)[1].split("\n6. ", 1)[0]
    assert "docs-site:" not in gaps  # D-17: focus-visible and material-design-color have their texts
    by_name = {p.name: p for p in review.packages}
    focus, colours = by_name["focus-visible"], by_name["material-design-color"]
    assert (focus.version, focus.spdx, colours.version, colours.spdx) == (
        "5.2.1",
        "W3C-20150513",
        "2.3.2",
        "MIT",
    )
    assert {t.kind for t in focus.texts} == {"licence file", "standard text"} and not focus.pending
    # D-17: the project names no copyright line, and the notices invent none; they name the repository
    assert "none is made up" in focus.note and "https://github.com/WICG/focus-visible" in focus.note
    assert "only the one the package-lock.json" in colours.note
    users = [line for line in text.splitlines() if line.startswith("Used by: documentation site")]
    for part in (
        "pypi mkdocs-material 9.7.7",
        "npm lunr 2.3.9",
        "npm tslib",
        "icons Font Awesome Free 7.1.0",
    ):
        assert any(part in line for line in users), part
    texts = list(notices.iter_texts(text))
    assert any("Licensed MIT © Zeno Rocha" in t for t in texts)
    assert any(t.startswith("Pictogrammers Free License") for t in texts)
    assert any("W3C Software and Document" in t for t in texts)
    assert any(t.startswith("The MIT License (MIT)\n\nCopyright (c) Denis Malinochkin") for t in texts)


def test_a_documentation_site_review_names_each_gap(tmp_path: Path) -> None:
    review = notices.load_site_review(notices.locked_version(notices.SITE_THEME))
    assert review is not None
    known = notices.load_known_missing()
    assert notices.check_site_review(None, known) == [
        "documentation site: no licence review of mkdocs-material (license-gate/third_party)"
    ]
    where = "documentation site (mkdocs-material 9.7.7)"
    lunr = next(p for p in review.packages if p.name == "lunr")

    def with_lunr(**changes: Any) -> Any:
        changed = dataclasses.replace(lunr, **changes)
        return dataclasses.replace(
            review, packages=tuple(changed if p is lunr else p for p in review.packages)
        )

    assert notices.check_site_review(with_lunr(spdx="MPL-2.0"), known) == [
        f"{where}: npm lunr 2.3.9: licence MPL-2.0 is not permissive (MPL-2.0 needs unmodified = true)"
    ]
    unmodified = dataclasses.replace(with_lunr(spdx="MPL-2.0"), unmodified=frozenset({"lunr"}))
    assert notices.check_site_review(unmodified, known) == []  # D-05: MPL-2.0 passed on unmodified
    assert notices.check_site_review(with_lunr(spdx="LGPL-3.0-or-later"), known) == [
        f"{where}: npm lunr 2.3.9: licence LGPL-3.0-or-later is not permissive"
    ]
    assert notices.check_site_review(with_lunr(spdx="", texts=()), known) == [
        f"{where}: npm lunr 2.3.9: no licence text and no known_missing.toml entry",
        f"{where}: npm lunr 2.3.9: no reviewed licence and no known_missing.toml entry",
    ]
    assert notices.check_site_review(with_lunr(pending="docs-site:lunr"), known) == [
        f"{where}: npm lunr 2.3.9: 'docs-site:lunr' is not listed in known_missing.toml"
    ]
    copy = tmp_path / "review"
    shutil.copytree(review.folder, copy)
    header = copy / "npm" / "lunr@2.3.9" / "LICENSE.source-header.txt"
    header.write_text(header.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")
    moved = [
        dataclasses.replace(t, path=copy / t.label) if t.label.startswith("npm/lunr") else t
        for t in lunr.texts
    ]
    assert notices.check_site_review(with_lunr(texts=tuple(moved)), known) == [
        f"{where}: npm lunr 2.3.9: SHA-256 or size of npm/lunr@2.3.9/LICENSE.source-header.txt differs from "
        "manifest.toml"
    ]
    orphan = dataclasses.replace(review, files=tuple(f for f in review.files if "search" not in f.pattern))
    assert f"{where}: npm lunr 2.3.9: part of no site file (stale review)" in notices.check_site_review(
        orphan, known
    )
    assert notices.site_glob("**/*.html").fullmatch("index.html")
    assert notices.site_glob("**/*.html").fullmatch("zh/reference/rules.html")
    assert not notices.site_glob("assets/javascripts/bundle.*.min.js").fullmatch(
        "assets/javascripts/x/bundle.a.min.js"
    )
