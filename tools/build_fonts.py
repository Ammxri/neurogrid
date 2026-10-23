"""Static Noto Sans SC cuts for the report (A-27, D-06): Regular (400) and Bold (700), instanced from the
Google Fonts variable font with fontTools, radical and compatibility code points removed from the cmap.

The cuts are checked in under src/neurogrid/report/fonts/ together with OFL.txt and fonts.json (source URL,
commit, SHA-256 of the source and of every output). Variable fonts are never embedded: Chromium turns them
into Type3 fonts in a PDF (KONZEPT 8.3).

Usage:
    python tools/build_fonts.py                 # fetch the pinned sources (cache .local/build_fonts), build
    python tools/build_fonts.py --source DIR    # sources already in DIR (NotoSansSC[wght].ttf, OFL.txt)
    python tools/build_fonts.py --check         # rebuild in a temporary folder and compare

The sources are verified by size and SHA-256 before use; two builds give identical bytes (the head table's
modification time is not recalculated). Exit codes: 0 fine, 1 a checked-in file differs (--check),
2 usage, network or checksum error. This tool is not part of the NeuroGrid package, which never uses the
network.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import urllib.error
import urllib.request
from importlib.metadata import version
from pathlib import Path
from typing import Any, cast

from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

from neurogrid.kernel.fonts import RADICAL_AND_COMPAT, is_radical_or_compat

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "src" / "neurogrid" / "report" / "fonts"
CACHE = ROOT / ".local" / "build_fonts"
COMMIT = "a85815a42757630ce188fdad368c2dfc444d4773"
BASE = f"https://raw.githubusercontent.com/google/fonts/{COMMIT}/ofl/notosanssc/"
SOURCE_FONT = {
    "name": "NotoSansSC[wght].ttf",
    "url": BASE + "NotoSansSC%5Bwght%5D.ttf",
    "bytes": 17_772_300,
    "sha256": "a3041811a78c361b1de50f953c805e0244951c21c5bd412f7232ef0d899af0da",
}
SOURCE_LICENSE = {
    "name": "OFL.txt",
    "url": BASE + "OFL.txt",
    "bytes": 4_388,
    "sha256": "1c05c68c34f9708415aada51f17e1b0092d2cea709bf4a94cd38114f9e73d7d9",
}
# where Google Fonts took the variable font from (google/fonts METADATA.pb at the commit above)
UPSTREAM = {
    "repository": "https://github.com/notofonts/noto-cjk",
    "commit": "523d033d6cb47f4a80c58a35753646f5c3608a78",
}
CUTS = ((400, "Regular"), (700, "Bold"))
FONTTOOLS = "4.66.1"
USER_AGENT = "neurogrid-build-fonts/1 (report fonts of the NeuroGrid project)"


class BuildError(Exception):
    """A source is missing, cannot be fetched or does not match its pinned checksum (exit 2)."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _matches(path: Path, item: dict[str, Any]) -> bool:
    return path.is_file() and path.stat().st_size == item["bytes"] and sha256_file(path) == item["sha256"]


def fetch(item: dict[str, Any], folder: Path) -> Path:
    """The pinned file in ``folder``; downloaded only when it is not there with the right checksum."""
    target = folder / str(item["name"])
    if _matches(target, item):
        return target
    folder.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    request = urllib.request.Request(str(item["url"]), headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as out:
            while chunk := response.read(1 << 20):
                out.write(chunk)
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
        partial.unlink(missing_ok=True)
        raise BuildError(f"download failed: {item['url']} ({exc})") from None
    if not _matches(partial, item):
        partial.unlink(missing_ok=True)
        raise BuildError(f"size or SHA-256 differs from the pinned value: {item['url']}")
    partial.replace(target)
    return target


def source_file(item: dict[str, Any], folder: Path) -> Path:
    """A source given with --source: it must exist and match the pinned size and SHA-256."""
    path = folder / str(item["name"])
    if not _matches(path, item):
        raise BuildError(f"{path.name} in {folder} is missing or differs from the pinned SHA-256")
    return path


def remove_codepoints(font: Any) -> int:
    """Remove radical and compatibility code points from every Unicode cmap subtable; returns how many
    distinct code points were removed."""
    removed: set[int] = set()
    for table in font["cmap"].tables:
        if table.isUnicode():
            for codepoint in [cp for cp in table.cmap if is_radical_or_compat(cp)]:
                del table.cmap[codepoint]
                removed.add(codepoint)
    return len(removed)


def build_cut(source: Path, weight: int, target: Path) -> dict[str, Any]:
    font = TTFont(source, recalcTimestamp=False)
    static = instancer.instantiateVariableFont(font, {"wght": weight}, updateFontNames=True)
    removed = remove_codepoints(static)
    static.save(target)
    return {
        "weight": weight,
        "bytes": target.stat().st_size,
        "sha256": sha256_file(target),
        "removed_codepoints": removed,
    }


def font_version(source: Path) -> str:
    font = TTFont(source, recalcTimestamp=False, lazy=True)
    try:
        return f"{cast(float, font['head'].fontRevision):.3f}"
    finally:
        font.close()


def build(source_font: Path, source_license: Path, out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    files: dict[str, Any] = {}
    for weight, style in CUTS:
        name = f"NotoSansSC-{style}.ttf"
        print(f"building {name} (wght {weight}) ...", flush=True)
        files[name] = build_cut(source_font, weight, out / name)
    (out / "OFL.txt").write_bytes(source_license.read_bytes())
    record = {
        "format_version": 1,
        "family": "Noto Sans SC",
        "license": "OFL-1.1",
        "license_file": {"name": "OFL.txt", "url": SOURCE_LICENSE["url"], "sha256": SOURCE_LICENSE["sha256"]},
        "source": {
            "url": SOURCE_FONT["url"],
            "commit": COMMIT,
            "bytes": SOURCE_FONT["bytes"],
            "sha256": SOURCE_FONT["sha256"],
            "font_version": font_version(source_font),
            "upstream": UPSTREAM,
        },
        "tool": {"fonttools": version("fonttools"), "script": "tools/build_fonts.py"},
        "removed_ranges": [[f"U+{low:04X}", f"U+{high:04X}"] for low, high in RADICAL_AND_COMPAT],
        "files": files,
    }
    (out / "fonts.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return record


OUTPUTS = ("NotoSansSC-Regular.ttf", "NotoSansSC-Bold.ttf", "OFL.txt", "fonts.json")


def compare(built: Path, checked_in: Path) -> list[str]:
    return [
        name
        for name in OUTPUTS
        if not (checked_in / name).is_file()
        or (built / name).read_bytes() != (checked_in / name).read_bytes()
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--source", type=Path, help="folder with NotoSansSC[wght].ttf and OFL.txt (no download)"
    )
    parser.add_argument("--check", action="store_true", help="rebuild and compare with the checked-in files")
    parser.add_argument("--out", type=Path, default=FONTS, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if version("fonttools") != FONTTOOLS:
        print(f"fontTools {FONTTOOLS} is required (found {version('fonttools')})", file=sys.stderr)
        return 2
    try:
        if args.source is not None:
            font, license_text = (
                source_file(SOURCE_FONT, args.source),
                source_file(SOURCE_LICENSE, args.source),
            )
        else:
            font, license_text = fetch(SOURCE_FONT, CACHE), fetch(SOURCE_LICENSE, CACHE)
    except BuildError as exc:
        print(exc, file=sys.stderr)
        return 2
    if not args.check:
        record = build(font, license_text, args.out)
        for name, item in record["files"].items():
            removed = item["removed_codepoints"]
            print(f"{name}: {item['bytes']} bytes, sha256 {item['sha256']}, {removed} removed")
        return 0
    with tempfile.TemporaryDirectory(prefix="neurogrid-fonts-") as temporary:
        build(font, license_text, Path(temporary))
        differing = compare(Path(temporary), args.out)
    for name in differing:
        print(f"differs from a fresh build: {name}")
    print("fonts are reproducible" if not differing else "fonts differ")
    return 1 if differing else 0


if __name__ == "__main__":
    sys.exit(main())
