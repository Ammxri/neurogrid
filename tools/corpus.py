"""Public test corpus (LIB-09, decision E4): six data sets from OpenNeuro and PhysioNet, pinned by SHA-256.

The corpus is not part of the repository (size, licences). This tool loads it into .local/corpus and checks it
offline. tools/corpus_spec.json says which files are taken from each data set; tools/corpus_lock.json pins
every file (URL, size, SHA-256). PhysioNet publishes SHA256SUMS.txt, which the lock repeats. OpenNeuro
publishes no file hashes, so their hashes were recorded at the first download ("first_download") together
with the commit (hexsha) of the snapshot. DATA_SOURCES.md lists licences and citations.

Usage:
    python tools/corpus.py verify [--root .local/corpus]       # offline: each file present, size and hash
    python tools/corpus.py fetch  [--root .local/corpus] [--dataset ds003775] [--workers 4] [--prefer-mirror]
    python tools/corpus.py lock   [--root .local/corpus]       # maintainers: resolve the spec anew (network)

Exit codes: 0 fine, 1 files missing or different, 2 usage, network or data source error.
Only the standard library is used. This tool is not part of the NeuroGrid package, which never uses the
network.
"""

from __future__ import annotations

import argparse
import concurrent.futures as futures
import fnmatch
import hashlib
import html
import io
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "tools" / "corpus_spec.json"
LOCK = ROOT / "tools" / "corpus_lock.json"
DEFAULT_ROOT = ROOT / ".local" / "corpus"
GRAPHQL = "https://openneuro.org/crn/graphql"
USER_AGENT = "neurogrid-corpus-tool/1 (test corpus of the NeuroGrid project)"
CHUNK = 1 << 20
LOCK_VERSION = 1


class CorpusError(Exception):
    """A data source answered differently than expected (exit 2)."""


# --- HTTP (only used by fetch and lock) ------------------------------------------------------------


def _request(
    url: str, data: bytes | None = None, headers: dict[str, str] | None = None
) -> urllib.request.Request:
    return urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT, **(headers or {})})


def _with_retries(action: Any, what: str, retries: int = 5) -> Any:
    for attempt in range(retries):
        try:
            return action()
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            if attempt == retries - 1:
                raise CorpusError(f"{what}: {exc}") from None
            print(f"  retry {what} ({exc})", file=sys.stderr)
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")

    def action() -> dict[str, Any]:
        with urllib.request.urlopen(
            _request(url, body, {"Content-Type": "application/json"}), timeout=60
        ) as r:
            result: dict[str, Any] = json.loads(r.read().decode("utf-8"))
            return result

    return _with_retries(action, f"POST {url}")


def _get_text(url: str) -> str:
    def action() -> str:
        with urllib.request.urlopen(_request(url), timeout=60) as r:
            return r.read().decode("utf-8", "replace")

    return _with_retries(action, f"GET {url}")


# --- selection of files ----------------------------------------------------------------------------


def match_parts(path: list[str], pattern: list[str]) -> bool:
    """Glob per path segment: '*' never crosses '/', '**' matches zero or more segments."""
    if not pattern:
        return not path
    if pattern[0] == "**":
        return any(match_parts(path[i:], pattern[1:]) for i in range(len(path) + 1))
    if not path:
        return False
    return fnmatch.fnmatchcase(path[0], pattern[0]) and match_parts(path[1:], pattern[1:])


def could_descend(folder: list[str], pattern: list[str]) -> bool:
    """True if a file below ``folder`` could still match ``pattern``."""
    for index, segment in enumerate(folder):
        if index >= len(pattern):
            return False
        if pattern[index] == "**":
            return True
        if not fnmatch.fnmatchcase(segment, pattern[index]):
            return False
    return len(pattern) > len(folder)


def wanted(relative: str, includes: list[str], excludes: list[str]) -> bool:
    parts = relative.split("/")
    if any(match_parts(parts, e.split("/")) for e in excludes):
        return False
    return any(match_parts(parts, i.split("/")) for i in includes)


def _natural(text: str) -> list[Any]:
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", text)]


# --- OpenNeuro --------------------------------------------------------------------------------------

_FILES_QUERY = (
    "query($ds: ID!, $tag: String!, $tree: String) { snapshot(datasetId: $ds, tag: $tag) "
    "{ files(tree: $tree) { id filename size directory urls } } }"
)
_SNAPSHOT_QUERY = "query($ds: ID!, $tag: String!) { snapshot(datasetId: $ds, tag: $tag) { hexsha } }"


def _openneuro(query: str, variables: dict[str, Any]) -> dict[str, Any]:
    answer = _post_json(GRAPHQL, {"query": query, "variables": variables})
    if answer.get("errors") or not answer.get("data", {}).get("snapshot"):
        raise CorpusError(f"OpenNeuro: {json.dumps(answer.get('errors'))[:300]}")
    snapshot: dict[str, Any] = answer["data"]["snapshot"]
    return snapshot


def plan_openneuro(spec: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    dataset, tag = spec["dataset"], spec["version"]
    includes, excludes = list(spec.get("include", [])), list(spec.get("exclude", []))

    def listing(tree: str | None) -> list[dict[str, Any]]:
        files: list[dict[str, Any]] = _openneuro(_FILES_QUERY, {"ds": dataset, "tag": tag, "tree": tree})[
            "files"
        ]
        return files

    top = listing(None)
    if spec.get("first_n_subjects"):
        subjects = sorted(
            (f["filename"] for f in top if f["directory"] and f["filename"].startswith("sub-")), key=_natural
        )
        includes += [f"{s}/**" for s in subjects[: spec["first_n_subjects"]]]
    planned: list[dict[str, Any]] = []

    def walk(entries: list[dict[str, Any]], prefix: list[str]) -> None:
        for entry in entries:
            parts = [*prefix, entry["filename"]]
            if entry["directory"]:
                if any(match_parts(parts, e.split("/")) for e in excludes):
                    continue
                if any(could_descend(parts, i.split("/")) for i in includes):
                    walk(listing(entry["id"]), parts)
            elif wanted("/".join(parts), includes, excludes):
                urls = entry.get("urls") or []
                if not urls:
                    raise CorpusError(f"OpenNeuro gives no URL for {dataset}/{'/'.join(parts)}")
                planned.append(
                    {
                        "path": "/".join(parts),
                        "url": urls[0],
                        "mirror_url": None,
                        "size": int(entry["size"]),
                        "sha256_published": None,
                    }
                )

    walk(top, [])
    return planned, {"snapshot_hexsha": _openneuro(_SNAPSHOT_QUERY, {"ds": dataset, "tag": tag})["hexsha"]}


# --- PhysioNet --------------------------------------------------------------------------------------

_LISTING_ROW = re.compile(r'<a href="([^"?]+)">[^<]*</a>[ \t]+\S+[ \t]+\S+[ \t]+(-|\d+)')


def _physionet_listing(base: str, sub: str) -> list[tuple[str, int | None, bool]]:
    rows = []
    for line in _get_text(base + sub).splitlines():
        match = _LISTING_ROW.search(line)
        if not match:
            continue
        href, size = html.unescape(match.group(1)), match.group(2)
        if href.startswith("../"):
            continue
        rows.append((sub + href, None if size == "-" else int(size), href.endswith("/")))
    return rows


def plan_physionet(spec: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    base = spec["base_url"].rstrip("/") + "/"
    includes, excludes = list(spec.get("include", [])), list(spec.get("exclude", []))
    published: dict[str, str] = {}
    for line in _get_text(base + spec["sha256sums"]).splitlines():
        if line.strip():
            digest, name = line.split(None, 1)
            published[name.strip()] = digest.lower()
    found: list[tuple[str, int | None]] = []

    def walk(sub: str) -> None:
        for relative, size, is_dir in _physionet_listing(base, sub):
            parts = relative.rstrip("/").split("/")
            if is_dir:
                if any(could_descend(parts, i.split("/")) for i in includes):
                    walk(relative)
            elif wanted(relative, includes, excludes):
                found.append((relative, size))

    walk("")
    smallest = spec.get("smallest_recordings")
    if smallest:  # only the n smallest recordings and the files that belong to them
        recording = re.compile(smallest["recording_regex"])
        ranked = sorted((size or 0, rel) for rel, size in found if recording.fullmatch(rel))
        keep = {m.group("rid") for _s, rel in ranked[: smallest["n"]] if (m := recording.fullmatch(rel))}
        owner = re.compile(smallest["id_regex"])

        def kept(relative: str) -> bool:
            match = owner.search(relative.rsplit("/", 1)[-1])
            return match is None or match.group("rid") in keep

        found = [(rel, size) for rel, size in found if kept(rel)]
    mirror = spec.get("mirror_base_url")
    planned = []
    for relative, size in found:
        if size is None:
            raise CorpusError(f"PhysioNet gives no size for {relative}")
        planned.append(
            {
                "path": relative,
                "url": base + relative,
                "mirror_url": mirror.rstrip("/") + "/" + relative if mirror else None,
                "size": size,
                "sha256_published": published.get(relative),
            }
        )
    return planned, {}


# --- files ------------------------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def _target(root: Path, local_dir: str, relative: str) -> Path:
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise CorpusError(f"unsafe path in the lock file: {relative!r}")
    return root.joinpath(local_dir, *path.parts)


def download(url: str, dest: Path, size: int, retries: int = 6) -> None:
    """Resumable download into ``dest`` (via ``dest.part``); the size must match."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    for attempt in range(retries):
        have = part.stat().st_size if part.exists() else 0
        if have > size:
            part.unlink()
            have = 0
        if have == size:
            break
        headers = {"Range": f"bytes={have}-"} if have else {}
        try:
            with urllib.request.urlopen(_request(url, headers=headers), timeout=120) as response:
                mode = "ab" if have and response.status == 206 else "wb"
                with part.open(mode) as stream:
                    for block in iter(lambda: response.read(CHUNK), b""):
                        stream.write(block)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            print(f"  retry {attempt + 1} {dest.name}: {exc}", file=sys.stderr)
            time.sleep(min(30, 2**attempt))
    got = part.stat().st_size if part.exists() else -1
    if got != size:
        raise CorpusError(f"{dest.name}: {got} bytes received, {size} expected")
    part.replace(dest)


def load_lock(path: Path) -> dict[str, Any]:
    lock: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if lock.get("lock_version") != LOCK_VERSION:
        raise CorpusError(f"unknown lock version in {path.name}")
    return lock


def _datasets(lock: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {d["dataset"]: d for d in lock["datasets"]}


def _selected(lock: dict[str, Any], only: list[str] | None) -> list[dict[str, Any]]:
    known = _datasets(lock)
    for name in only or []:
        if name not in known:
            raise CorpusError(f"unknown data set {name!r}; known: {', '.join(sorted(known))}")
    return [f for f in lock["files"] if not only or f["dataset"] in only]


# --- commands ---------------------------------------------------------------------------------------


def cmd_verify(root: Path, lock: dict[str, Any], only: list[str] | None) -> int:
    """Offline: each file of the lock exists below ``root`` with its size and SHA-256."""
    datasets = _datasets(lock)
    problems: list[str] = []
    counted: dict[str, int] = {}
    for item in _selected(lock, only):
        path = _target(root, datasets[item["dataset"]]["local_dir"], item["path"])
        name = f"{datasets[item['dataset']]['local_dir']}/{item['path']}"
        if not path.is_file():
            problems.append(f"missing  {name}")
        elif path.stat().st_size != item["size"]:
            problems.append(f"size     {name}")
        elif sha256_file(path) != item["sha256"]:
            problems.append(f"sha256   {name}")
        else:
            counted[item["dataset"]] = counted.get(item["dataset"], 0) + 1
    for name, dataset in sorted(datasets.items()):
        if not only or name in only:
            expected = sum(1 for f in lock["files"] if f["dataset"] == name)
            print(f"{dataset['local_dir']}: {counted.get(name, 0)}/{expected} files verified")
    for line in problems:
        print(line)
    print("corpus verified" if not problems else f"{len(problems)} file(s) missing or different")
    return 1 if problems else 0


def cmd_fetch(root: Path, lock: dict[str, Any], only: list[str] | None, workers: int, mirror: bool) -> int:
    datasets = _datasets(lock)

    def one(item: dict[str, Any]) -> str:
        path = _target(root, datasets[item["dataset"]]["local_dir"], item["path"])
        if path.is_file() and path.stat().st_size == item["size"] and sha256_file(path) == item["sha256"]:
            return "present"
        url = item["mirror_url"] if mirror and item.get("mirror_url") else item["url"]
        download(url, path, item["size"])
        if sha256_file(path) != item["sha256"]:
            path.unlink()
            raise CorpusError(f"{item['path']}: SHA-256 differs from the lock file")
        return "downloaded"

    errors = 0
    selected = _selected(lock, only)
    with futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        jobs = {pool.submit(one, item): item for item in selected}
        for done in futures.as_completed(jobs):
            item = jobs[done]
            try:
                status = done.result()
            except CorpusError as exc:
                errors += 1
                print(f"  error {item['dataset']}/{item['path']}: {exc}", file=sys.stderr)
                continue
            if status == "downloaded":
                print(f"  downloaded {item['dataset']}/{item['path']} ({item['size']:,} bytes)")
    print(f"{len(selected) - errors}/{len(selected)} files present and verified")
    return 1 if errors else 0


def cmd_lock(root: Path, spec_path: Path, lock_path: Path, workers: int) -> int:
    """Resolve the spec at the data sources, download what is missing and write the lock file."""
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    datasets: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    for entry in spec["datasets"]:
        planned, extra = plan_openneuro(entry) if entry["source"] == "openneuro" else plan_physionet(entry)
        keys = ("source", "dataset", "version", "license", "local_dir", "format", "doi")
        datasets.append({**{k: entry[k] for k in keys}, **extra})
        for item in planned:
            files.append({"dataset": entry["dataset"], **item})
        print(f"{entry['dataset']} {entry['version']}: {len(planned)} files")

    def pin(item: dict[str, Any]) -> dict[str, Any]:
        local_dir = next(d["local_dir"] for d in datasets if d["dataset"] == item["dataset"])
        path = _target(root, local_dir, item["path"])
        if not (path.is_file() and path.stat().st_size == item["size"]):
            download(item["url"], path, item["size"])
        digest = sha256_file(path)
        published = item.pop("sha256_published")
        if published is not None and digest != published:
            raise CorpusError(f"{item['path']}: SHA-256 differs from the published checksum")
        return {**item, "sha256": digest, "sha256_source": "published" if published else "first_download"}

    with futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        pinned = list(pool.map(pin, files))
    write_lock(lock_path, datasets, pinned)
    print(f"wrote {lock_path.name}: {len(pinned)} files")
    return 0


def write_lock(path: Path, datasets: list[dict[str, Any]], files: list[dict[str, Any]]) -> None:
    lock = {
        "lock_version": LOCK_VERSION,
        "datasets": sorted(datasets, key=lambda d: d["dataset"]),
        "files": sorted(files, key=lambda f: (f["dataset"], f["path"])),
    }
    path.write_bytes((json.dumps(lock, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("verify", "fetch", "lock"))
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--lock", type=Path, default=LOCK)
    parser.add_argument("--spec", type=Path, default=SPEC)
    parser.add_argument("--dataset", action="append", help="limit to these data sets (repeatable)")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--prefer-mirror", action="store_true", help="PhysioNet: use the AWS mirror")
    args = parser.parse_args(argv)
    try:
        if args.command == "lock":
            return cmd_lock(args.root, args.spec, args.lock, args.workers)
        lock = load_lock(args.lock)
        if args.command == "verify":
            return cmd_verify(args.root, lock, args.dataset)
        return cmd_fetch(args.root, lock, args.dataset, args.workers, args.prefer_mirror)
    except (CorpusError, OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
