"""Install the PDF browser of NeuroGrid: Chrome Headless Shell revision 1243 (Playwright 1.63.0), the only
browser NeuroGrid prints PDF reports with (TECH-07, A-26, D-08).

The shell is not part of NeuroGrid or of its offline bundle. This script fetches the pinned zip online, or
installs a zip that was downloaded elsewhere, after checking its size and SHA-256 against the pinned values.
It installs into NeuroGrid's own folder, never into Playwright's (ms-playwright) and never through
`playwright install` (which would also fetch FFmpeg):

    Windows: %LOCALAPPDATA%\\NeuroGrid\\pdf-browser
    Linux:   ${XDG_DATA_HOME:-~/.local/share}/neurogrid/pdf-browser
    or the absolute local folder in NEUROGRID_PDF_BROWSER_DIR (or --dir)

Usage:
    python install_pdf_browser.py                                   # online, for this computer
    python install_pdf_browser.py --from-zip FILE --sha256 HEX      # offline, zip from another computer
    python install_pdf_browser.py --download-only --platform win64|linux64 --out DIR
    python install_pdf_browser.py --check                           # verify the installed shell
    python install_pdf_browser.py --print-info                      # addresses, sizes, checksums, folder

Only the Python standard library is used, so the script runs with the interpreter of the offline bundle
before NeuroGrid is installed. Messages are printed in Chinese and English.
Exit codes: 0 installed, already installed or verified; 1 checksum, size, unsafe zip or failed check;
2 usage, file, folder or network error.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import sys
import urllib.error
import urllib.request
import zipfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

REVISION = "1243"
BROWSER_VERSION = "153.0.8010.12"
PLAYWRIGHT = "1.63.0"
_CFT = "https://storage.googleapis.com/chrome-for-testing-public"
SHELL: dict[str, dict[str, Any]] = {
    "win64": {
        "urls": (
            f"https://cdn.playwright.dev/builds/cft/{BROWSER_VERSION}/win64/chrome-headless-shell-win64.zip",
            f"{_CFT}/{BROWSER_VERSION}/win64/chrome-headless-shell-win64.zip",
        ),
        "bytes": 120_200_717,
        "sha256": "7aec872f3090e639c4237467624ea863c20fe2878914c93a6556bdbb52aa6c4c",
        "files": 290,
        "unpacked": 283_217_434,
        "tree_sha256": "5d1d96b91285a66273d179c70c28de33531d84a193df942a79f539d6a76bcb74",
        "executable": "chrome-headless-shell-win64/chrome-headless-shell.exe",
    },
    "linux64": {
        "urls": (
            f"https://cdn.playwright.dev/builds/cft/{BROWSER_VERSION}/linux64/chrome-headless-shell-linux64.zip",
            f"{_CFT}/{BROWSER_VERSION}/linux64/chrome-headless-shell-linux64.zip",
        ),
        "bytes": 119_809_080,
        "sha256": "a9da028861a0cf789ff25c2fed45f5f1aaf969ed9247835b6a7821a4f7af9d1d",
        "files": 287,
        "unpacked": 272_533_063,
        "tree_sha256": "c0179e089634a013f8f121d451b071b657b4ee14f541d46fae0446f4160fb5db",
        "executable": "chrome-headless-shell-linux64/chrome-headless-shell",
    },
}
SHELL_DIRNAME = f"chrome-headless-shell-{REVISION}"
RECORD_NAME = "neurogrid-install.json"
RECORD_VERSION = 1
ENV_DIR = "NEUROGRID_PDF_BROWSER_DIR"
MAX_ENTRIES = 400
MAX_UNPACKED = 400_000_000
MAX_RATIO = 20.0
CHUNK = 1 << 20
TIMEOUT_S = 60
USER_AGENT = f"neurogrid-install-pdf-browser/{REVISION}"
_DRIVE_REMOTE = 4

MESSAGES: dict[str, tuple[str, str]] = {
    "notice": (
        "Chrome Headless Shell 是 Google Chrome 的一个构建版本（版权归 Google LLC 所有，"
        "适用 Google 的服务条款；其中包含 FFmpeg（LGPL-2.1+）等开源组件）。"
        "该程序由您自行下载；NeuroGrid 不分发该程序。",
        "The Chrome Headless Shell is a build of Google Chrome (copyright Google LLC, Google's terms of "
        "service apply; it contains open-source components such as FFmpeg under LGPL-2.1+). You download it "
        "yourself; NeuroGrid does not distribute it.",
    ),
    "target": ("安装目录：{folder}", "Installation folder: {folder}"),
    "already": (
        "PDF 浏览器（修订版 {revision}）已安装且完整：{folder}",
        "The PDF browser (revision {revision}) is already installed and complete: {folder}",
    ),
    "downloading": ("正在下载 {url}（{size} 字节）……", "Downloading {url} ({size} bytes) ..."),
    "download_failed": ("下载失败：{url}（{problem}）", "Download failed: {url} ({problem})"),
    "no_download": (
        "无法从任何固定地址下载该 zip。请在可联网的计算机上运行 --download-only，然后使用 --from-zip。",
        "The zip could not be downloaded from any pinned address. Run --download-only on a computer with "
        "internet access, then use --from-zip.",
    ),
    "checksum": (
        "{file} 的大小或 SHA-256 与固定值不符（应为 {size} 字节，SHA-256 {sha256}）。未安装任何内容。",
        "Size or SHA-256 of {file} differ from the pinned values ({size} bytes, SHA-256 {sha256}). "
        "Nothing was installed.",
    ),
    "sha256_mismatch": (
        "--sha256 给出的值不是修订版 {revision}（{platform}）的固定 SHA-256：{sha256}。只接受该固定的 zip。",
        "The value given with --sha256 is not the pinned SHA-256 of revision {revision} ({platform}): "
        "{sha256}. Only this pinned zip is accepted.",
    ),
    "unsafe": (
        "zip 不安全或不是预期的文件（{problem}）。未安装任何内容。",
        "The zip is unsafe or not the expected file ({problem}). Nothing was installed.",
    ),
    "installed": ("PDF 浏览器已安装：{folder}", "The PDF browser was installed: {folder}"),
    "downloaded": (
        "已下载并校验：{file}。请将其复制到目标计算机并运行：{command}",
        "Downloaded and verified: {file}. Copy it to the target computer and run: {command}",
    ),
    "check_ok": (
        "已安装的 PDF 浏览器完整（修订版 {revision}，{files} 个文件）。",
        "The installed PDF browser is complete (revision {revision}, {files} files).",
    ),
    "check_failed": (
        "已安装的 PDF 浏览器不完整或已被更改（{problem}）。请使用 --force 重新安装。",
        "The installed PDF browser is incomplete or was changed ({problem}). Reinstall it with --force.",
    ),
    "not_installed": ("{folder} 中未安装 PDF 浏览器。", "The PDF browser is not installed in {folder}."),
    "folder_invalid": (
        "{variable} 必须是本机上的绝对文件夹路径（不得为网络路径或设备路径）。",
        "{variable} must be an absolute folder on this computer (no network or device path).",
    ),
    "platform": (
        "不支持此平台（{platform}）；只支持 Windows x86_64 和 Linux x86_64。",
        "This platform is not supported ({platform}); only Windows x86_64 and Linux x86_64 are.",
    ),
    "io": ("无法写入 {folder}（{problem}）。", "Cannot write to {folder} ({problem})."),
    "zip_missing": ("未找到 zip 文件：{file}", "The zip file was not found: {file}"),
    "usage_from_zip": ("--from-zip 需要同时给出 --sha256。", "--from-zip needs --sha256 as well."),
    "usage_download": (
        "--download-only 需要 --platform 和 --out。",
        "--download-only needs --platform and --out.",
    ),
    "info_platform": (
        "平台 {platform}：{size} 字节，SHA-256 {sha256}，解压后 {files} 个文件、{unpacked} 字节",
        "Platform {platform}: {size} bytes, SHA-256 {sha256}, unpacked {files} files, {unpacked} bytes",
    ),
    "info_url": ("  地址：{url}", "  Address: {url}"),
    "info_packages": (
        "Linux（{distribution}）所需系统软件包：apt-get install --no-install-recommends {packages}",
        "Linux ({distribution}) system packages: apt-get install --no-install-recommends {packages}",
    ),
    "info_packages_missing": (
        "未找到 Linux 软件包列表；请参阅文档“安装”中的“PDF 浏览器”一节。",
        "The Linux package list was not found; see the section 'PDF browser' of the installation page "
        "in the documentation.",
    ),
}


class InstallError(Exception):
    """A failure with a message key, its parameters and the exit code (1 checksum/unsafe, 2 other)."""

    def __init__(self, key: str, code: int, **params: object) -> None:
        super().__init__(key)
        self.key = key
        self.code = code
        self.params = params


def shown(value: object) -> str:
    """A message parameter as the console shows it (A-51): the home folder, which holds the user name, as
    '~', like the neurogrid command line does (neurogrid.kernel.safety.redact_paths: native, POSIX and
    doubled-backslash spellings, case-insensitively on Windows, only up to a separator or the end)."""
    text = str(value)
    try:
        home = str(Path.home())
    except (RuntimeError, KeyError, OSError):  # no home folder known: nothing to hide
        return text
    if len(home.rstrip("\\/")) < 2:  # a root folder as home: replacing it would garble every path
        return text
    flags = re.IGNORECASE if os.name == "nt" else 0
    spellings = {home, home.replace("\\", "/"), home.replace("\\", "\\\\")}
    for spelling in sorted(spellings, key=len, reverse=True):
        pattern = re.escape(spelling) + r"(?=$|[\\/'\"\s:,;)\]])"
        text = re.sub(pattern, lambda _match: "~", text, flags=flags)
    return text


def say(key: str, **params: object) -> None:
    """One message in Chinese, then in English; every parameter with the home folder shown as '~'."""
    zh, en = MESSAGES[key]
    values = {name: shown(value) for name, value in params.items()}
    print(zh.format(**values))
    print(en.format(**values))


def current_platform() -> str:
    machine = platform.machine().lower()
    if sys.platform == "win32" and machine in ("amd64", "x86_64"):
        return "win64"
    if sys.platform.startswith("linux") and machine in ("x86_64", "amd64"):
        return "linux64"
    raise InstallError("platform", 2, platform=f"{sys.platform}/{platform.machine()}")


def default_browser_dir(environ: Mapping[str, str], *, windows: bool | None = None) -> Path:
    """NeuroGrid's default folder for the shell (the same rule as neurogrid.kernel.pdf)."""
    if windows if windows is not None else os.name == "nt":
        base = environ.get("LOCALAPPDATA", "")
        root = Path(base) if base and Path(base).is_absolute() else Path.home() / "AppData" / "Local"
        return root / "NeuroGrid" / "pdf-browser"
    data = environ.get("XDG_DATA_HOME", "")
    root = Path(data) if data and Path(data).is_absolute() else Path.home() / ".local" / "share"
    return root / "neurogrid" / "pdf-browser"


def _is_network_drive(path: Path) -> bool:
    if os.name != "nt" or not re.fullmatch(r"[A-Za-z]:\\", path.anchor):
        return False
    get_drive_type = ctypes.windll.kernel32.GetDriveTypeW  # type: ignore[attr-defined,unused-ignore]
    return int(get_drive_type(path.anchor)) == _DRIVE_REMOTE


def checked_folder(raw: str, variable: str) -> Path:
    """An absolute local folder: no UNC, device or namespace path, no mapped network drive."""
    text = raw.strip()
    native = text.replace("/", "\\") if os.name == "nt" else text
    if (
        not text
        or any(ord(ch) < 32 for ch in text)
        or native.startswith(("\\\\", "//"))
        or not Path(text).is_absolute()
    ):
        raise InstallError("folder_invalid", 2, variable=variable)
    path = Path(text)
    if _is_network_drive(path):
        raise InstallError("folder_invalid", 2, variable=variable)
    return path


def browser_dir(environ: Mapping[str, str], explicit: str | None = None) -> Path:
    if explicit is not None:
        return checked_folder(explicit, "--dir")
    value = environ.get(ENV_DIR)
    if value is not None:
        return checked_folder(value, ENV_DIR)
    return default_browser_dir(environ)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def matches_pin(path: Path, pin: Mapping[str, Any]) -> bool:
    return path.is_file() and path.stat().st_size == pin["bytes"] and sha256_file(path) == pin["sha256"]


def download(pin: Mapping[str, Any], target: Path) -> Path:
    """Fetch the pinned zip into ``target`` (primary address, then the mirror); verified before use."""
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    for url in pin["urls"]:
        say("downloading", url=url, size=pin["bytes"])
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response, partial.open("wb") as out:
                received = 0
                while chunk := response.read(CHUNK):
                    received += len(chunk)
                    if received > pin["bytes"]:
                        raise ValueError("more data than the pinned size")
                    out.write(chunk)
        except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError, OSError) as exc:
            partial.unlink(missing_ok=True)
            say("download_failed", url=url, problem=type(exc).__name__)
            continue
        if matches_pin(partial, pin):
            partial.replace(target)
            return target
        partial.unlink(missing_ok=True)
        say("checksum", file=url, size=pin["bytes"], sha256=pin["sha256"])
    raise InstallError("no_download", 2)


def _entry_problem(info: zipfile.ZipInfo, prefix: str) -> str | None:
    name = info.filename
    raw = info.orig_filename  # on Windows zipfile turns '\' into '/' in filename
    if any("\\" in n or ":" in n or n.startswith("/") or any(ord(ch) < 32 for ch in n) for n in (name, raw)):
        return f"entry name {name!r}"
    folder = name.endswith("/")
    segments = name[:-1].split("/") if folder else name.split("/")
    if (
        len(segments) < (1 if folder else 2)
        or segments[0] != prefix
        or any(s in ("", ".", "..") for s in segments)
    ):
        return f"entry name {name!r}"
    kind = stat.S_IFMT(info.external_attr >> 16)
    if kind not in (0, stat.S_IFREG, stat.S_IFDIR):
        return f"entry type of {name!r}"
    if info.flag_bits & 0x1:
        return f"encrypted entry {name!r}"
    if info.file_size and info.compress_size and info.file_size / info.compress_size > MAX_RATIO:
        return f"compression ratio of {name!r}"
    return None


def check_zip(archive: zipfile.ZipFile, platform_name: str) -> list[zipfile.ZipInfo]:
    """Every entry is a regular file or folder below chrome-headless-shell-<platform>/ (A-53)."""
    infos = archive.infolist()
    prefix = f"chrome-headless-shell-{platform_name}"
    if len(infos) > MAX_ENTRIES:
        raise InstallError("unsafe", 1, problem=f"{len(infos)} entries")
    if sum(info.file_size for info in infos) > MAX_UNPACKED:
        raise InstallError("unsafe", 1, problem="unpacked size")
    seen: set[str] = set()
    for info in infos:
        problem = _entry_problem(info, prefix)
        if problem:
            raise InstallError("unsafe", 1, problem=problem)
        key = info.filename.rstrip("/").lower()
        if key in seen:
            raise InstallError("unsafe", 1, problem=f"duplicate entry {info.filename!r}")
        seen.add(key)
    return infos


def tree_digest(folder: Path, root: Path) -> tuple[int, int, str]:
    """Files, bytes and the SHA-256 over 'path<TAB>size<TAB>sha256' lines of every file below ``folder``."""
    lines = []
    total = 0
    for path in sorted(p for p in folder.rglob("*") if p.is_file() or p.is_symlink()):
        if path.is_symlink():
            raise InstallError("check_failed", 1, problem="link inside the folder")
        size = path.stat().st_size
        total += size
        lines.append(f"{path.relative_to(root).as_posix()}\t{size}\t{sha256_file(path)}\n")
    lines.sort()
    return len(lines), total, hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()


def extract(zip_path: Path, platform_name: str, staging: Path) -> tuple[int, int]:
    """Unpack the checked zip into ``staging``; sizes are enforced while writing, not only declared."""
    with zipfile.ZipFile(zip_path) as archive:
        infos = check_zip(archive, platform_name)
        files = written_total = 0
        for info in infos:
            target = staging.joinpath(*PurePosixPath(info.filename).parts)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            written = 0
            with archive.open(info) as source, target.open("xb") as out:
                while chunk := source.read(CHUNK):
                    written += len(chunk)
                    if written > info.file_size:
                        raise InstallError("unsafe", 1, problem=f"size of {info.filename!r}")
                    out.write(chunk)
            if written != info.file_size:
                raise InstallError("unsafe", 1, problem=f"size of {info.filename!r}")
            mode = (info.external_attr >> 16) & 0o777
            if os.name != "nt" and mode:
                target.chmod(mode | stat.S_IRUSR | stat.S_IWUSR)
            files += 1
            written_total += written
    return files, written_total


def read_record(shell_dir: Path) -> dict[str, Any] | None:
    try:
        data = json.loads((shell_dir / RECORD_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def verify_installed(shell_dir: Path, platform_name: str) -> tuple[bool, str, int]:
    """(complete, problem, files): the record, the executable and the pinned tree digest."""
    pin = SHELL[platform_name]
    record = read_record(shell_dir)
    if record is None:
        return False, "no installation record", 0
    if record.get("revision") != REVISION or record.get("platform") != platform_name:
        return False, "other revision or platform", 0
    if not (shell_dir / pin["executable"]).is_file():
        return False, "executable missing", 0
    files, total, digest = tree_digest(shell_dir / pin["executable"].split("/")[0], shell_dir)
    if (files, total, digest) != (pin["files"], pin["unpacked"], pin["tree_sha256"]):
        return False, f"{files} files, {total} bytes, content differs", files
    return True, "", files


def install(zip_path: Path, platform_name: str, folder: Path, *, source: str, force: bool) -> Path:
    pin = SHELL[platform_name]
    if not matches_pin(zip_path, pin):
        raise InstallError("checksum", 1, file=zip_path.name, size=pin["bytes"], sha256=pin["sha256"])
    shell_dir = folder / SHELL_DIRNAME
    staging = folder / f".staging-{REVISION}-{platform_name}"
    old = folder / f".old-{REVISION}-{platform_name}"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        for leftover in (staging, old):
            if leftover.exists():
                shutil.rmtree(leftover)
        staging.mkdir()
        files, total = extract(zip_path, platform_name, staging)
        counted, unpacked, digest = tree_digest(staging / pin["executable"].split("/")[0], staging)
        if (counted, unpacked, digest) != (pin["files"], pin["unpacked"], pin["tree_sha256"]):
            raise InstallError("unsafe", 1, problem="unpacked content differs from the pinned build")
        if shell_dir.exists():
            if not force and verify_installed(shell_dir, platform_name)[0]:
                shutil.rmtree(staging)
                return shell_dir
            shell_dir.replace(old)
        staging.replace(shell_dir)
        record = {
            "format_version": RECORD_VERSION,
            "revision": REVISION,
            "browser_version": BROWSER_VERSION,
            "playwright": PLAYWRIGHT,
            "platform": platform_name,
            "executable": pin["executable"],
            "zip_bytes": pin["bytes"],
            "zip_sha256": pin["sha256"],
            "files": files,
            "bytes": total,
            "tree_sha256": digest,
            "source": source,
        }
        partial = shell_dir / (RECORD_NAME + ".part")
        partial.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        partial.replace(shell_dir / RECORD_NAME)  # written last: without it the install is incomplete
        if old.exists():
            shutil.rmtree(old)
    except OSError as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise InstallError("io", 2, folder=folder, problem=type(exc).__name__) from None
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return shell_dir


def package_lists(script: Path) -> dict[str, Any] | None:
    """The Linux package lists (src/neurogrid/kernel/pdf_linux_packages.json) next to a source checkout or
    inside the venv of an offline-bundle installation."""
    base = script.resolve().parent.parent
    candidates = [base / "src" / "neurogrid" / "kernel" / "pdf_linux_packages.json"]
    candidates += sorted(base.glob("venv/[Ll]ib/*/neurogrid/kernel/pdf_linux_packages.json"))
    candidates += sorted(
        base.glob("venv/lib/python3*/site-packages/neurogrid/kernel/pdf_linux_packages.json")
    )
    for candidate in candidates:
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            return data
    return None


def print_info(folder: Path | None) -> None:
    for name, pin in SHELL.items():
        say(
            "info_platform",
            platform=name,
            size=pin["bytes"],
            sha256=pin["sha256"],
            files=pin["files"],
            unpacked=pin["unpacked"],
        )
        for url in pin["urls"]:
            say("info_url", url=url)
    if folder is not None:
        say("target", folder=folder)
    lists = package_lists(Path(__file__))
    distributions = lists.get("distributions") if lists else None
    if not isinstance(distributions, dict):
        say("info_packages_missing")
        return
    for distribution, entry in sorted(distributions.items()):
        say("info_packages", distribution=distribution, packages=" ".join(entry.get("packages", [])))


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dir", help="installation folder (default: NeuroGrid's folder, see above)")
    parser.add_argument("--from-zip", type=Path, help="install this zip (downloaded elsewhere)")
    parser.add_argument(
        "--sha256", help="SHA-256 of the zip given with --from-zip (must be the pinned value)"
    )
    parser.add_argument("--download-only", action="store_true", help="only fetch and verify the zip")
    parser.add_argument("--platform", choices=sorted(SHELL), help="platform of the zip for --download-only")
    parser.add_argument("--out", type=Path, help="folder for the zip of --download-only")
    parser.add_argument("--force", action="store_true", help="reinstall even if a complete shell is present")
    parser.add_argument("--check", action="store_true", help="verify the installed shell")
    parser.add_argument("--print-info", action="store_true", help="show addresses, sizes, checksums, folder")
    args = parser.parse_args(argv)
    try:
        if args.print_info:
            try:
                folder: Path | None = browser_dir(os.environ, args.dir)
            except InstallError:
                folder = None
            print_info(folder)
            return 0
        if args.download_only:
            if args.platform is None or args.out is None:
                raise InstallError("usage_download", 2)
            pin = SHELL[args.platform]
            target = args.out / pin["urls"][0].rsplit("/", 1)[-1]
            if not matches_pin(target, pin):
                download(pin, target)
            command = f"python install_pdf_browser.py --from-zip {target.name} --sha256 {pin['sha256']}"
            say("downloaded", file=target, command=command)
            return 0
        platform_name = current_platform()
        folder = browser_dir(os.environ, args.dir)
        shell_dir = folder / SHELL_DIRNAME
        if args.check:
            if not shell_dir.exists():
                say("not_installed", folder=folder)
                return 1
            complete, problem, files = verify_installed(shell_dir, platform_name)
            if complete:
                say("check_ok", revision=REVISION, files=files)
                return 0
            say("check_failed", problem=problem)
            return 1
        pin = SHELL[platform_name]
        say("notice")
        say("target", folder=folder)
        if not args.force and shell_dir.exists() and verify_installed(shell_dir, platform_name)[0]:
            say("already", revision=REVISION, folder=shell_dir)
            return 0
        if args.from_zip is not None:
            if args.sha256 is None:
                raise InstallError("usage_from_zip", 2)
            if args.sha256.strip().lower() != pin["sha256"]:
                raise InstallError(
                    "sha256_mismatch", 1, revision=REVISION, platform=platform_name, sha256=pin["sha256"]
                )
            if not args.from_zip.is_file():
                raise InstallError("zip_missing", 2, file=args.from_zip)
            install(args.from_zip, platform_name, folder, source="zip", force=True)
        else:
            folder.mkdir(parents=True, exist_ok=True)
            archive = folder / f".download-{REVISION}-{platform_name}.zip"
            try:
                if not matches_pin(archive, pin):
                    download(pin, archive)
                install(archive, platform_name, folder, source="download", force=True)
            finally:
                archive.unlink(missing_ok=True)
        say("installed", folder=shell_dir)
        return 0
    except InstallError as exc:
        say(exc.key, **exc.params)
        return exc.code
    except OSError as exc:
        say("io", folder=args.dir or args.out or "", problem=type(exc).__name__)
        return 2


if __name__ == "__main__":
    sys.exit(main())
