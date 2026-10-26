"""Third-party notices and the licence gate's package sets (D-08, A-56, NG-N07, A-86).

tools/notices.py reads the locked wheels of both targets statically; these tests check its parts on synthetic
wheels and archives (no network), the committed THIRD_PARTY_NOTICES.txt against uv.lock, the reviewed
component list, and that the runtime export of the licence gate holds no package of the dev or docs group."""

from __future__ import annotations

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
    for item in notices.load_known_missing():
        assert f"- {item['component']}: " in gaps, item["component"]
    assert "Packages compiled into the BIDS validator bundle" in text and notices.PENDING in text
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
    section = committed.split(BUNDLE_HEADING, 1)[1].split("\n5. ", 1)[0]
    rows = {tuple(line.split()[:4]) for line in section.strip().splitlines()[2:] if not line.startswith("- ")}
    assert rows == {(p.target, p.name, p.version, p.filename) for p in pins}
    for target, items in removed.items():
        for path, reason in items:
            assert f"- removed from the bundle ({target}): {path} - {reason}" in section


def test_committed_notices_equal_a_generation_from_the_cached_wheels() -> None:
    """With every pinned file in .local/notices-wheels (filled by `tools/notices.py --download`) the whole
    file is compared with a fresh generation; without them the frame test above still runs."""
    folders = [notices.DEFAULT_CACHE]
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
        found, licences = notices.validator_sources(archive)
    assert found == [  # by name, casefolded; never attributed to the package whose dist carries them
        ("npm", "@nodable/entities", "in x@1.0.0"),
        ("jsr", "@std/path", "1.1.2"),
        ("npm", "ajv", "8.20.0"),
        ("npm", "lodash", "in hed-validator@4.2.0"),
    ]
    assert licences == {("ajv", "8.20.0"): "MIT", ("lodash", "in hed-validator@4.2.0"): "ISC"}


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
        for key in ("registry", "name", "version", "found", "spdx", "note", "pending"):
            if key in package:
                lines.append(f"{key} = {json.dumps(package[key])}")
        for text in package.get("texts", []):
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
    known = {item["component"] for item in notices.load_known_missing()}
    listed = set()
    for package in packages:
        assert notices.spdx_units(package.spdx) <= notices.BUNDLED_ALLOWED, package
        assert package.texts or package.pending in known, package
        assert not package.pending or package.pending in known, package
        for text in package.texts:
            data = text.path.read_bytes()
            assert hashlib.sha256(data).hexdigest() == text.sha256 and len(data) == text.size, text.label
            assert b"\r" not in data, text.label  # LF only: git (eol=lf) keeps the bytes and the hash
            assert text.kind in {"licence file", "source header", "standard text"}, text.label
            if text.kind == "licence file":
                assert text.url.startswith(("https://registry.npmjs.org/", "https://jsr.io/")), text.label
            listed.add(text.path.resolve())
    stored = {p.resolve() for p in base.rglob("*") if p.is_file() and p.name != "manifest.toml"}
    assert stored <= listed, sorted(str(p) for p in stored - listed)
    assert len({p.key for p in packages}) == len(packages) > 70
    schema = next(p for p in packages if p.name == "@bids/schema")
    assert schema.spdx == "CC-BY-4.0" and schema.texts[0].label.endswith("@bids/schema@1.2.7/LICENSE")


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
