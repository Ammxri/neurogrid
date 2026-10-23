"""Linux system packages the PDF browser needs (A-26, A-58), from the one data file
src/neurogrid/kernel/pdf_linux_packages.json that NeuroGrid's start check (kernel/pdf.py), CI, the
Dockerfiles and the documentation share.

The file is taken from Playwright 1.63.0's own list of Chromium dependencies (nativeDeps in
playwright/driver/package/lib/coreBundle.js, read as data, never run): the 'chromium' packages and the
libraries that map to them. Playwright 1.63.0 also lists Debian 13 and Ubuntu 26.04; NeuroGrid's file keeps
the three distributions of A-58 (Debian 12, Ubuntu 22.04 and 24.04).

Usage:
    python tools/linux_pdf_packages.py [DISTRIBUTION]   # packages on one line (default: from /etc/os-release)
    python tools/linux_pdf_packages.py --list           # the distributions in the file
    python tools/linux_pdf_packages.py --check          # compare the file with the installed Playwright
    python tools/linux_pdf_packages.py --write          # maintainers: rewrite the file from Playwright

Exit codes: 0 fine, 1 the file differs from Playwright (--check), 2 usage or unknown distribution.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from importlib.metadata import version
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "src" / "neurogrid" / "kernel" / "pdf_linux_packages.json"
PLAYWRIGHT = "1.63.0"
# NeuroGrid name -> Playwright host platform and the /etc/os-release fields that identify it (A-58)
DISTRIBUTIONS = {
    "debian12": ("debian12-x64", {"ID": "debian", "VERSION_ID": "12"}),
    "ubuntu22.04": ("ubuntu22.04-x64", {"ID": "ubuntu", "VERSION_ID": "22.04"}),
    "ubuntu24.04": ("ubuntu24.04-x64", {"ID": "ubuntu", "VERSION_ID": "24.04"}),
}
FALLBACK = "debian12"
_BARE_KEY = re.compile(r"(?m)^(\s*)([A-Za-z_$][\w$]*)\s*:")
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")


def _bundle() -> Path:
    import playwright

    return Path(playwright.__file__).parent / "driver" / "package" / "lib" / "coreBundle.js"


def _deps_literal(source: str) -> str:
    """The object literal 'deps = { "ubuntu22.04-x64": {...}, ... }' of Playwright's nativeDeps."""
    marker = source.find('"ubuntu22.04-x64": {')
    start = source.rfind("deps = {", 0, marker)
    if marker < 0 or start < 0:
        raise ValueError("nativeDeps not found in the Playwright driver")
    start = source.index("{", start)
    depth = 0
    for index in range(start, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise ValueError("unbalanced nativeDeps literal")


def parse_deps(literal: str) -> dict[str, Any]:
    """The nativeDeps object literal as data: it holds only string keys (some bare), string arrays and
    nested objects, so quoting the bare keys and dropping trailing commas gives JSON."""
    text = _TRAILING_COMMA.sub(r"\1", _BARE_KEY.sub(r'\1"\2":', literal))
    try:
        deps = json.loads(text)
    except ValueError as exc:
        raise ValueError(f"nativeDeps is not plain data ({exc})") from None
    if not isinstance(deps, dict):
        raise ValueError("nativeDeps is not an object")
    return deps


def from_playwright() -> dict[str, Any]:
    """The data file's content as Playwright's installed driver defines it."""
    deps = parse_deps(_deps_literal(_bundle().read_text(encoding="utf-8")))
    distributions = {}
    for name, (host, os_release) in DISTRIBUTIONS.items():
        entry = deps[host]
        packages = list(entry["chromium"])
        libraries = {lib: pkg for lib, pkg in sorted(entry["lib2package"].items()) if pkg in packages}
        distributions[name] = {"os_release": os_release, "packages": packages, "libraries": libraries}
    return {
        "format_version": 1,
        "playwright": version("playwright"),
        "source": "Playwright nativeDeps (playwright/driver/package/lib/coreBundle.js), browser 'chromium'",
        "fallback": FALLBACK,
        "distributions": distributions,
    }


def load() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(DATA.read_text(encoding="utf-8"))
    return data


def render(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def detect(os_release: Path = Path("/etc/os-release")) -> str | None:
    """The distribution name for /etc/os-release, or None."""
    try:
        text = os_release.read_text(encoding="utf-8")
    except OSError:
        return None
    fields = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            fields[key.strip()] = value.strip().strip('"').strip("'")
    for name, (_host, wanted) in DISTRIBUTIONS.items():
        if all(fields.get(key) == value for key, value in wanted.items()):
            return name
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("distribution", nargs="?", help="debian12, ubuntu22.04 or ubuntu24.04")
    parser.add_argument("--list", action="store_true", help="print the distributions in the file")
    parser.add_argument("--check", action="store_true", help="compare the file with the installed Playwright")
    parser.add_argument("--write", action="store_true", help="rewrite the file from the installed Playwright")
    args = parser.parse_args(argv)
    if args.check or args.write:
        if version("playwright") != PLAYWRIGHT:
            print(f"Playwright {PLAYWRIGHT} is required (found {version('playwright')})", file=sys.stderr)
            return 2
        expected = render(from_playwright())
        if args.write:
            DATA.write_text(expected, encoding="utf-8", newline="\n")
            return 0
        same = DATA.read_text(encoding="utf-8") == expected
        print("pdf_linux_packages.json matches Playwright" if same else "pdf_linux_packages.json differs")
        return 0 if same else 1
    data = load()
    if args.list:
        print("\n".join(sorted(data["distributions"])))
        return 0
    name = args.distribution or detect()
    if name not in data["distributions"]:
        print(
            f"unknown distribution {name!r}; known: {', '.join(sorted(data['distributions']))}",
            file=sys.stderr,
        )
        return 2
    print(" ".join(data["distributions"][name]["packages"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
