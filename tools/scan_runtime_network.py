"""Scan of the installed runtime packages for network and telemetry code (A-49; NG-N01, CON-04, ARC-06).

A-49 asks for a scan of the installed runtime packages for telemetry and update mechanisms. For every
distribution of the runtime set (`uv export --frozen --no-default-groups`, the same set the offline bundle
ships) that is installed in the scanned environment, every .py file is parsed: imports of network modules
(NETWORK_MODULES) and markers of telemetry or update checks (MARKERS) are hits. Each hit must be listed in the
reviewed baseline license-gate/network_baseline.json with the version it was reviewed for, the reason why it
does not reach the network when NeuroGrid runs, and the control that keeps it so. A hit missing from the
baseline, a changed hit, an entry reviewed for another installed version and an entry whose hit disappeared
fail the scan. Entries for distributions or files that are not installed on this platform are skipped (the
baseline covers Windows and Linux).

Not covered, stated openly: dynamic imports and native code (compiled extensions, deno, the Playwright driver,
the PDF browser). The subprocesses are restricted by their own flags and checked at the operating-system level
(strace, WFP audit; offline.yml); the NeuroGrid process itself runs under the audit hook (kernel/netguard.py).

Usage: python tools/scan_runtime_network.py [--site-packages DIR] [--baseline FILE] [--distribution NAME ...]
                                            [--draft OUT]
  --distribution  scan these distributions instead of the runtime set (no uv needed)
  --draft         write a baseline draft: reviewed entries kept, new hits with empty reason/control to review
Exit codes: 0 every hit reviewed, 1 unreviewed, changed, outdated or stale entries, 2 usage or environment
error.
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import json
import re
import sys
import sysconfig
from collections.abc import Iterable, Mapping
from importlib import metadata
from pathlib import Path
from typing import Any

from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "license-gate" / "network_baseline.json"
NETWORK_MODULES = (
    "aiohttp",
    "ftplib",
    "http.client",
    "http.server",
    "httpx",
    "imaplib",
    "nntplib",
    "poplib",
    "pooch",
    "requests",
    "smtplib",
    "socket",
    "socketserver",
    "ssl",
    "telnetlib",
    "urllib.request",
    "urllib3",
    "webbrowser",
    "websocket",
    "websockets",
    "xmlrpc",
)
# "telemetry" also inside identifiers (disable_telemetry_events); the generic words only as whole words.
MARKERS = re.compile(
    r"(?i)(telemetry|\banalytics\b|\bsentry_sdk\b|sentry\.io|\bposthog\b|\bmixpanel\b|segment\.io"
    r"|update_check|check_for_updates?|pypi\.org/pypi|api\.github\.com)"
)


@dataclasses.dataclass(frozen=True)
class Found:
    distribution: str
    version: str
    file: str
    hits: tuple[str, ...]


def file_hits(source: str) -> set[str]:
    """Network imports (absolute, also ``from x import y``) and telemetry/update markers of one module."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return {"unparsable"}
    kinds: set[str] = set()
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names = [node.module, *(f"{node.module}.{alias.name}" for alias in node.names)]
        for name in names:
            kinds.update(f"import:{m}" for m in NETWORK_MODULES if name == m or name.startswith(m + "."))
    kinds.update(f"marker:{match.group(1).lower()}" for match in MARKERS.finditer(source))
    return kinds


def installed(site_packages: Path, names: Iterable[str]) -> dict[str, metadata.Distribution]:
    wanted = {canonicalize_name(n) for n in names}
    found: dict[str, metadata.Distribution] = {}
    for dist in metadata.distributions(path=[str(site_packages)]):
        name = canonicalize_name(dist.metadata["Name"] or "")
        if name in wanted:
            found.setdefault(name, dist)
    return found


def files_of(dist: metadata.Distribution) -> dict[str, Path]:
    return {
        f.as_posix(): Path(str(dist.locate_file(f)))
        for f in dist.files or []
        if f.suffix == ".py" and Path(str(dist.locate_file(f))).is_file()
    }


def scan(dists: Mapping[str, metadata.Distribution]) -> list[Found]:
    found: list[Found] = []
    for name, dist in sorted(dists.items()):
        for rel, path in sorted(files_of(dist).items()):
            kinds = file_hits(path.read_text(encoding="utf-8", errors="replace"))
            if kinds:
                found.append(Found(name, dist.version, rel, tuple(sorted(kinds))))
    return found


def load_baseline(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("format_version") != 1 or not isinstance(data.get("entries"), list):
        raise ValueError(f"{path.name}: unsupported format")
    entries: list[dict[str, Any]] = data["entries"]
    return entries


def compare(
    found: list[Found], entries: list[dict[str, Any]], dists: Mapping[str, metadata.Distribution]
) -> list[str]:
    """Every problem: unreviewed, changed, outdated, stale or incomplete baseline entries."""
    problems: list[str] = []
    reviewed = _keyed(entries)
    for entry in entries:
        if not str(entry.get("reason", "")).strip() or not str(entry.get("control", "")).strip():
            problems.append(
                f"not reviewed (reason or control empty): {entry['distribution']} {entry['file']}"
            )
    hit_keys = set()
    for item in found:
        key = (item.distribution, item.file)
        hit_keys.add(key)
        known = reviewed.get(key)
        if known is None:
            problems.append(f"unreviewed: {item.distribution} {item.version} {item.file} {list(item.hits)}")
        elif known.get("version") != item.version:
            problems.append(f"reviewed for {known.get('version')}, installed {item.version}: {item.file}")
        elif sorted(known.get("hits", [])) != list(item.hits):
            problems.append(
                f"hits changed in {item.file}: reviewed {known.get('hits')}, found {list(item.hits)}"
            )
    for key, entry in sorted(reviewed.items()):
        dist = dists.get(key[0])
        if key in hit_keys or dist is None or dist.version != entry.get("version"):
            continue
        if key[1] in files_of(dist):
            problems.append(f"stale baseline entry (hit no longer found): {key[0]} {key[1]}")
    return problems


def _keyed(entries: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    return {(str(canonicalize_name(e["distribution"])), str(e["file"])): e for e in entries}


def draft(found: list[Found], entries: list[dict[str, Any]]) -> dict[str, Any]:
    reviewed = _keyed(entries)
    current = {(item.distribution, item.file): item for item in found}
    out = []
    for key in sorted(set(reviewed) | set(current)):
        item = current.get(key)
        old = reviewed.get(key)
        if item is None and old is not None:
            out.append(old)  # not installed here (other platform) or stale: kept for review
            continue
        assert item is not None
        same = (
            old is not None
            and old.get("version") == item.version
            and sorted(old.get("hits", [])) == list(item.hits)
        )
        out.append(
            {
                "distribution": item.distribution,
                "version": item.version,
                "file": item.file,
                "hits": list(item.hits),
                "reason": old["reason"] if same and old else "",
                "control": old["control"] if same and old else "",
            }
        )
    return {"format_version": 1, "entries": out}


def runtime_names() -> set[str]:
    sys.path.insert(0, str(ROOT / "tools"))
    from bundle import export_requirements, parse_requirements

    return {pin.name for pin in parse_requirements(export_requirements(ROOT))}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--site-packages", default=sysconfig.get_paths()["purelib"])
    parser.add_argument("--baseline", default=str(BASELINE))
    parser.add_argument("--distribution", action="append")
    parser.add_argument("--draft")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 2
    try:
        names = set(args.distribution) if args.distribution else runtime_names()
        entries = load_baseline(Path(args.baseline)) if Path(args.baseline).is_file() else []
    except Exception as exc:  # uv missing, export failed, unreadable baseline: an environment error
        print(f"error: {exc}", file=sys.stderr)
        return 2
    dists = installed(Path(args.site_packages), names)
    found = scan(dists)
    if args.draft:
        text = json.dumps(draft(found, entries), indent=1, ensure_ascii=False) + "\n"
        Path(args.draft).write_text(text, encoding="utf-8", newline="\n")
        print(f"draft written: {args.draft} ({len(found)} files with hits)")
        return 0
    problems = compare(found, entries, dists)
    for problem in problems:
        print(problem)
    missing = sorted(canonicalize_name(n) for n in names if canonicalize_name(n) not in dists)
    print(
        f"{len(dists)} distributions scanned ({len(missing)} not installed here), "
        f"{len(found)} files with hits, "
        f"{len(problems)} problem(s)"
    )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
