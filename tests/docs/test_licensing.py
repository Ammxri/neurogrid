"""Licence information of every file and of the packages (TECH-10, CON-05, A-27, A-86).

REUSE.toml is checked with an own implementation of its rules (``*`` within a path segment, ``**`` across
segments, the last matching table wins): the REUSE tool itself is GPL-3.0 and has no Windows wheel for the
no-build lock (A-48), so this test is the REUSE gate. Like ``reuse lint`` it fails for a licence without its
text in LICENSES/ and for a text in LICENSES/ that no file of the repository uses; a text whose download
no decision covers (D-06, D-15, D-16, D-17) is listed in license-gate/known_missing.toml (STOPP G1) and blocks
the release. Licence texts of bundled third-party packages and libraries (D-15, D-16, D-17) are kept next to
the package in license-gate/third_party/, not in LICENSES/."""

from __future__ import annotations

import hashlib
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
# Files REUSE treats as licence files themselves: LICENSES/ and, by file name anywhere, LICENSE/LICENCE and
# COPYING with an optional '.' or '-' suffix (the REUSE tool's ignore patterns, case-sensitive).
LICENCE_FILE = re.compile(r"(?:^|/)(?:LICEN[CS]E|COPYING)(?:[-.][^/]*)?$|^LICENSES/")
THIRD_PARTY = "license-gate/third_party/"


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


def test_licence_files_outside_licenses_are_reviewed_third_party_texts() -> None:
    """A file that counts as a licence file by its name alone is the project's LICENSE or a third-party text
    of license-gate/third_party that a manifest lists (D-15); nothing else escapes the licence check by its
    name."""
    named = [name for name in _files() if LICENCE_FILE.search(name) and not name.startswith("LICENSES/")]
    assert "LICENSE" in named
    listed: set[str] = set()
    for manifest in (ROOT / THIRD_PARTY).glob("*/manifest.toml"):
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))
        base = manifest.parent.relative_to(ROOT).as_posix()
        listed |= {
            f"{base}/{text['file']}" for p in data["package"] for text in p.get("text", []) if "file" in text
        }
    assert listed, "no third-party licence texts"
    outside = [name for name in named if name != "LICENSE" and name not in listed]
    assert not outside, outside
    assert listed <= set(named), sorted(listed - set(named))


@pytest.mark.parametrize(
    ("path", "hit"),
    [
        ("LICENSE", True),
        ("COPYING.txt", True),
        ("license-gate/third_party/v/npm/a@1/LICENSE", True),
        ("license-gate/third_party/v/npm/a@1/LICENSE-MIT", True),
        ("license-gate/third_party/v/npm/a@1/LICENSE.src-x.c.txt", True),
        ("docs/en/license.md", False),  # a page about the licence is documentation (CC-BY-4.0)
        ("tools/licenses.py", False),
        ("LICENSEX", False),
    ],
)
def test_licence_file_names(path: str, hit: bool) -> None:
    assert bool(LICENCE_FILE.search(path)) is hit


STANDARD_TEXT = re.compile(r"(?:^|/)LICENSE\.([A-Za-z0-9.+-]+)\.txt$")


def third_party_texts() -> dict[str, str]:
    """SPDX ID -> repository path of the standard licence texts that a manifest of license-gate/third_party
    keeps next to a bundled package (file LICENSE.<SPDX-ID>.txt of kind 'standard text'), for example the
    LGPL-3.0 and GPL-3.0 texts of the D-16 exception."""
    found: dict[str, str] = {}
    for manifest in (ROOT / THIRD_PARTY).glob("*/manifest.toml"):
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))
        base = manifest.parent.relative_to(ROOT).as_posix()
        for package in data["package"]:
            for text in package.get("text", []):
                match = STANDARD_TEXT.search(str(text.get("file", "")))
                if match and text.get("kind") == "standard text":
                    found[match.group(1)] = f"{base}/{text['file']}"
    return found


def test_used_licences_have_texts_and_texts_are_used() -> None:
    used: set[str] = set()
    own: set[str] = set()  # licences of this repository's own files (no third-party licence file)
    for table in _annotations():
        used |= _ids(str(table["SPDX-License-Identifier"]))
    own |= used
    for name in _files():
        # licence files themselves are no licensed files (reuse lint skips them): a third-party header
        # extract such as the LGPL path.join header of isomorphic-git states its own licence
        header = _header_licence(name) if not LICENCE_FILE.search(name) else None
        if header:
            used |= _ids(header)
            own |= _ids(header)
    texts = {path.stem for path in LICENSES.glob("*.txt")}
    absent = used - texts
    assert absent <= known_missing(), sorted(absent - known_missing())  # only reviewed gaps (G1)
    # as reuse lint: every text in LICENSES/ licenses a file of this repository (no unused licence)
    unused = texts - used
    assert not unused, sorted(unused)
    # the copyleft texts serve the bundled LGPL part only (D-16): kept next to that package in
    # license-gate/third_party, never in LICENSES/ and never the licence of a file of this repository
    copyleft = {"LGPL-3.0-or-later", "GPL-3.0-or-later"}
    kept = third_party_texts()
    assert copyleft <= set(kept), sorted(copyleft - set(kept))
    assert not copyleft & (texts | own | used)
    assert all((ROOT / path).is_file() and LICENCE_FILE.search(path) for path in kept.values()), kept
    if absent:
        warnings.warn(f"licence texts pending owner approval (G1): {sorted(absent)}", stacklevel=1)
    assert (LICENSES / "Apache-2.0.txt").read_bytes() == (ROOT / "LICENSE").read_bytes()


LICENCE_TEXTS = ROOT / "license-gate" / "licence_texts.toml"
SHA256 = re.compile(r"[0-9a-f]{64}")
SPDX_DATA = "https://raw.githubusercontent.com/spdx/license-list-data/v3.27.0"
# Every standard licence text downloaded into LICENSES/ or next to a bundled package, with the decision that
# approved exactly that download and its URL: SPDX license-list-data at one pinned tag, and the Unicode
# License V3 as unicode.org publishes it (D-17).
COPYLEFT_DIR = "license-gate/third_party/bids-validator-3.0.2/npm/isomorphic-git@1.41.9"
UNICODE_TEXT = "license-gate/third_party/bids-validator-3.0.2/npm/unicode-name@1.1.0/LICENSE.Unicode-3.0.txt"
W3C_TEXT = "license-gate/third_party/mkdocs-material-9.7.7/npm/focus-visible@5.2.1/LICENSE.W3C-20150513.txt"
APPROVED_DOWNLOADS = {
    "LICENSES/CC-BY-4.0.txt": ("D-15", f"{SPDX_DATA}/text/CC-BY-4.0.txt"),
    f"{COPYLEFT_DIR}/LICENSE.LGPL-3.0-or-later.txt": ("D-16", f"{SPDX_DATA}/text/LGPL-3.0-or-later.txt"),
    f"{COPYLEFT_DIR}/LICENSE.GPL-3.0-or-later.txt": ("D-16", f"{SPDX_DATA}/text/GPL-3.0-or-later.txt"),
    UNICODE_TEXT: ("D-17", "https://www.unicode.org/license.txt"),
    W3C_TEXT: ("D-17", f"{SPDX_DATA}/text/W3C-20150513.txt"),
}


def test_downloaded_licence_texts_match_their_record() -> None:
    """D-15, D-16, D-17: a licence text downloaded into LICENSES/ or next to a bundled package (the standard
    texts of license-gate/third_party) is recorded with its URL, size and SHA-256 and stored byte for byte;
    Apache-2.0 (a copy of LICENSE) and OFL-1.1 (the font's OFL.txt) are no downloads. Each download is the
    one its decision approved, from the pinned tag of SPDX license-list-data or, for the Unicode License V3,
    from unicode.org."""
    data = tomllib.loads(LICENCE_TEXTS.read_text(encoding="utf-8"))
    assert data["version"] == 1
    recorded = {str(item["path"]): item for item in data["text"]}
    texts = {f"LICENSES/{path.name}" for path in LICENSES.glob("*.txt")}
    texts -= {"LICENSES/Apache-2.0.txt", "LICENSES/OFL-1.1.txt", f"LICENSES/{REPRODUCED}.txt"}
    assert set(recorded) == texts | set(third_party_texts().values())
    assert {path: (item["decision"], item["url"]) for path, item in recorded.items()} == APPROVED_DOWNLOADS
    assert not {Path(path).stem for path in recorded} & known_missing()
    for path, item in recorded.items():
        content = (ROOT / path).read_bytes()
        assert SHA256.fullmatch(str(item["sha256"])), path
        assert hashlib.sha256(content).hexdigest() == item["sha256"], path
        assert len(content) == item["size"], path
        named = STANDARD_TEXT.search(path)
        assert item["spdx"] == (named.group(1) if named else Path(path).stem), path
        assert b"\r" not in content, path
    unicode = (ROOT / UNICODE_TEXT).read_text(encoding="utf-8")
    assert unicode.startswith("UNICODE LICENSE V3\n") and "Permission is hereby granted" in unicode
    assert "W3C Software and Document Short Notice" in (ROOT / W3C_TEXT).read_text(encoding="utf-8")
    font_licence = ROOT / "src" / "neurogrid" / "report" / "fonts" / "OFL.txt"
    assert font_licence.read_bytes() == (LICENSES / "OFL-1.1.txt").read_bytes()
    cc_by = (LICENSES / "CC-BY-4.0.txt").read_text(encoding="utf-8")
    assert cc_by.startswith("Creative Commons Attribution 4.0 International")
    assert "Section 1 – Definitions." in cc_by and "Section 8 – Interpretation." in cc_by
    lgpl = (ROOT / COPYLEFT_DIR / "LICENSE.LGPL-3.0-or-later.txt").read_text(encoding="utf-8")
    assert lgpl.startswith("GNU LESSER GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007")
    assert "4. Combined Works." in lgpl
    gpl = (ROOT / COPYLEFT_DIR / "LICENSE.GPL-3.0-or-later.txt").read_text(encoding="utf-8")
    assert gpl.startswith("GNU GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007")
    assert "END OF TERMS AND CONDITIONS" in gpl


REPRODUCED = "LicenseRef-NeuroGrid-Reproduced-Notices"


def _table_of(path: str) -> dict[str, Any]:
    found: dict[str, Any] = {}
    for table in _annotations():
        patterns = table["path"] if isinstance(table["path"], list) else [table["path"]]
        if any(glob_regex(p).fullmatch(path) for p in patterns):
            found = table
    return found


def test_notices_file_keeps_the_terms_of_the_texts_it_reproduces() -> None:
    """TECH-10, D-05, D-16: THIRD_PARTY_NOTICES.txt reproduces third-party licence texts and notices word for
    word (the GPL and LGPL texts may not be changed). Its annotation therefore licenses only NeuroGrid's own
    prose under CC BY 4.0, keeps the reproduced texts under their own terms (an own LicenseRef with its text
    in LICENSES/) and does not claim the third parties' copyright."""
    table = _table_of("THIRD_PARTY_NOTICES.txt")
    assert table["SPDX-License-Identifier"] == f"CC-BY-4.0 AND {REPRODUCED}"
    holders = table["SPDX-FileCopyrightText"]
    assert isinstance(holders, list) and "2026 Ammar Ahad" in holders
    assert any("third-party copyright holders" in holder for holder in holders), holders
    assert table.get("precedence") == "override"
    assert "THIRD_PARTY_NOTICES.txt" not in next(
        tab["path"] for tab in _annotations() if "docs/**" in tab["path"]
    )
    text = " ".join((LICENSES / f"{REPRODUCED}.txt").read_text(encoding="utf-8").split())
    assert text.startswith(REPRODUCED)
    for part in ("word for word", "own terms", "claims no copyright", "only unchanged", "CC BY 4.0"):
        assert part in text, part
    notices_text = (ROOT / "THIRD_PARTY_NOTICES.txt").read_text(encoding="utf-8")
    assert "GNU LESSER GENERAL PUBLIC LICENSE" in notices_text  # it does reproduce such a text
    assert REPRODUCED in " ".join(notices_text.split("\n1. ", 1)[0].split())


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
        ("THIRD_PARTY_NOTICES.txt", f"CC-BY-4.0 AND {REPRODUCED}"),
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
