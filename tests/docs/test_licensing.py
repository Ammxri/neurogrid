"""Licence information of every file and of the packages (TECH-10, CON-05, A-27, A-86).

REUSE.toml is checked with an own implementation of its rules (``*`` within a path segment, ``**`` across
segments, the last matching table wins): the REUSE tool itself is GPL-3.0 and has no Windows wheel for the
no-build lock (A-48), so this test is the REUSE gate. The licence texts are in LICENSES/; a text whose
download D-06 does not cover is listed in license-gate/known_missing.toml (STOPP G1) and blocks the
release."""

from __future__ import annotations

import re
import subprocess
import tomllib
import warnings
from functools import cache
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
LICENSES = ROOT / "LICENSES"
KNOWN_MISSING = ROOT / "license-gate" / "known_missing.toml"
# An SPDX header is a comment line of its own (code that merely names the tag is no header).
SPDX_HEADER = re.compile(
    r"^[ \t]*(?:#|//|/?\*|<!--|--|;)[ \t]*SPDX-License-Identifier:[ \t]*(\S[^\r\n]*?)[ \t]*(?:\*/|-->)?$",
    re.M,
)
SPDX_TOKEN = re.compile(r"[A-Za-z0-9.+-]+")
OPERATORS = {"AND", "OR", "WITH"}
# Files REUSE treats as licence files themselves.
LICENCE_FILE = re.compile(r"^(LICENSE|COPYING)(\..*)?$|^LICENSES/")


@cache
def _annotations() -> list[dict[str, Any]]:
    data = tomllib.loads((ROOT / "REUSE.toml").read_text(encoding="utf-8"))
    assert data["version"] == 1
    tables: list[dict[str, Any]] = data["annotations"]
    return tables


def glob_regex(pattern: str) -> re.Pattern[str]:
    """REUSE.toml path glob: '**' any characters, '*' any characters except '/', '\\' escapes."""
    out, index = "", 0
    while index < len(pattern):
        if pattern.startswith("**", index):
            out, index = out + ".*", index + 2
        elif pattern[index] == "*":
            out, index = out + "[^/]*", index + 1
        elif pattern[index] == "\\" and index + 1 < len(pattern):
            out, index = out + re.escape(pattern[index + 1]), index + 2
        else:
            out, index = out + re.escape(pattern[index]), index + 1
    return re.compile(out)


def licence_of(path: str) -> str | None:
    """The licence REUSE.toml gives a path: the last table one of whose globs matches."""
    found = None
    for table in _annotations():
        patterns = table["path"] if isinstance(table["path"], list) else [table["path"]]
        if any(glob_regex(p).fullmatch(path) for p in patterns):
            found = str(table["SPDX-License-Identifier"])
    return found


def _files() -> list[str]:
    """Tracked files plus new ones that are not ignored (what the next commit can contain)."""
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8")
    return sorted(name for name in listed.split("\0") if name and (ROOT / name).is_file())


def _header_licence(path: str) -> str | None:
    with (ROOT / path).open("rb") as stream:
        head = stream.read(4096)
    match = SPDX_HEADER.search(head.decode("utf-8", errors="replace"))
    return match.group(1).strip() if match else None


def _ids(expression: str) -> set[str]:
    return {token for token in SPDX_TOKEN.findall(expression) if token not in OPERATORS}


def known_missing() -> set[str]:
    data = tomllib.loads(KNOWN_MISSING.read_text(encoding="utf-8"))
    return {str(item["component"]) for item in data.get("missing", [])}


def test_every_file_has_licence_information() -> None:
    files = _files()
    assert len(files) > 200
    missing = [
        name
        for name in files
        if not LICENCE_FILE.search(name) and licence_of(name) is None and _header_licence(name) is None
    ]
    assert not missing, missing


def test_used_licences_have_texts_and_texts_are_used() -> None:
    used: set[str] = set()
    for table in _annotations():
        used |= _ids(str(table["SPDX-License-Identifier"]))
    for name in _files():
        header = _header_licence(name) if not name.startswith("LICENSES/") else None
        if header:
            used |= _ids(header)
    texts = {path.stem for path in LICENSES.glob("*.txt")}
    absent = used - texts
    assert absent <= known_missing(), sorted(absent - known_missing())  # only reviewed gaps (G1)
    assert not texts - used, sorted(texts - used)  # no unused licence text
    if absent:
        warnings.warn(f"licence texts pending owner approval (G1): {sorted(absent)}", stacklevel=1)
    assert (LICENSES / "Apache-2.0.txt").read_bytes() == (ROOT / "LICENSE").read_bytes()


def test_no_case_collision_with_licenses_folder() -> None:
    """Windows treats licenses/ and LICENSES/ as one folder; the gate configuration lives in license-gate/."""
    files = _files()
    folded: dict[str, str] = {}
    for name in files:
        assert folded.setdefault(name.casefold(), name) == name, (name, folded[name.casefold()])
    tops = {name.split("/", 1)[0] for name in files if "/" in name}
    assert not [top for top in tops if top.casefold() == "licenses" and top != "LICENSES"]
    assert (ROOT / "license-gate" / "allowlist.txt").is_file() and (
        ROOT / "license-gate" / "components.toml"
    ).is_file()


@pytest.mark.parametrize(
    ("path", "licence"),
    [
        ("src/neurogrid/cli.py", "Apache-2.0"),
        ("src/neurogrid/report/i18n/zh.yaml", "Apache-2.0"),
        ("tools/notices.py", "Apache-2.0"),
        ("tests/unit/test_norm_independence.py", "Apache-2.0"),
        ("mkdocs.yml", "Apache-2.0"),
        (".python-version", "Apache-2.0"),
        ("license-gate/components.toml", "Apache-2.0"),
        ("docs/assets/javascripts/file-search-hint.js", "Apache-2.0"),
        ("docs/assets/stylesheets/neurogrid.css", "Apache-2.0"),
        ("docs/en/index.md", "CC-BY-4.0"),
        ("docs/zh/reference/rules.md", "CC-BY-4.0"),
        ("docs/_data/labels.zh.yaml", "CC-BY-4.0"),
        ("README.md", "CC-BY-4.0"),
        ("DATA_SOURCES.md", "CC-BY-4.0"),
        ("THIRD_PARTY_NOTICES.txt", "CC-BY-4.0"),
        ("tests/fixtures/synthetic/edf_ok/sub-01_task-rest_eeg.edf", "CC-BY-4.0"),
        ("src/neurogrid/report/fonts/NotoSansSC-Regular.ttf", "OFL-1.1"),
        ("src/neurogrid/report/fonts/NotoSansSC-Bold.ttf", "OFL-1.1"),
        ("src/neurogrid/report/fonts/OFL.txt", "OFL-1.1"),
        ("src/neurogrid/report/fonts/fonts.json", "Apache-2.0"),
    ],
)
def test_licence_split_code_docs_data_fonts(path: str, licence: str) -> None:
    assert licence_of(path) == licence


def test_every_documentation_page_and_source_file_has_its_licence() -> None:
    for name in _files():
        if name.startswith(("docs/en/", "docs/zh/")):
            assert licence_of(name) == "CC-BY-4.0", name
        elif name.startswith("src/") and not name.startswith("src/neurogrid/report/fonts/"):
            assert licence_of(name) == "Apache-2.0", name


def _pyproject() -> dict[str, Any]:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_wheel_licence_expression_covers_packaged_files() -> None:
    """The wheel packs src/neurogrid (hatch); its licence expression names every licence of those files."""
    project = _pyproject()["project"]
    declared = _ids(project["license"])
    packaged = {licence_of(name) for name in _files() if name.startswith("src/neurogrid/")}
    assert packaged == {"Apache-2.0", "OFL-1.1"}
    assert {str(item) for item in packaged} <= declared
    for name in project["license-files"]:
        assert (ROOT / name).is_file(), name
    assert "src/neurogrid/report/fonts/OFL.txt" in project["license-files"]


def test_sdist_contains_licence_and_notice_files() -> None:
    """CON-05: the source release carries its complete licence information."""
    include = set(_pyproject()["tool"]["hatch"]["build"]["targets"]["sdist"]["include"])
    needed = {"src/neurogrid", "LICENSE", "NOTICE", "LICENSES", "REUSE.toml", "THIRD_PARTY_NOTICES.txt"}
    needed |= {"DATA_SOURCES.md", "README.md", "pyproject.toml"}
    assert needed <= include, sorted(needed - include)
    assert all((ROOT / name).exists() for name in include)


@pytest.mark.parametrize(
    ("pattern", "path", "hit"),
    [
        ("src/**", "src/neurogrid/cli.py", True),
        ("tests/fixtures/*.toml", "tests/fixtures/documented.toml", True),
        ("tests/fixtures/*.toml", "tests/fixtures/synthetic/x.toml", False),
        ("tests/**/*.py", "tests/unit/a.py", True),
        ("src/neurogrid/report/fonts/*.ttf", "src/neurogrid/report/fonts/NotoSansSC-Bold.ttf", True),
        ("docs/**", "docsx/a.md", False),
        ("a\\*b", "a*b", True),
        ("a\\*b", "axb", False),
    ],
)
def test_glob_semantics(pattern: str, path: str, hit: bool) -> None:
    assert bool(glob_regex(pattern).fullmatch(path)) is hit
