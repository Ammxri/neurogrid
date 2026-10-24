"""Small, offline stand-ins for the inputs of tools/bundle.py (interpreter archive, uv wheel, wheels, lock
data).

Everything is generated in a temporary folder and served through file:// URLs, so builds in tests download
nothing (the network guard of tests/conftest.py stays active). The real installer scripts and README template
of packaging/ are used unchanged.
"""

from __future__ import annotations

import hashlib
import io
import tarfile
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import bundle  # tools/bundle.py (tests/conftest.py puts tools/ on sys.path)

ROOT = Path(__file__).resolve().parents[2]
VERSION = "9.8.7"  # obviously not a real NeuroGrid version
EPOCH = 1_700_000_000
WHEEL_DATE = (1980, 1, 1, 0, 0, 0)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_zip(path: Path, members: dict[str, bytes]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name in sorted(members):
            archive.writestr(zipfile.ZipInfo(name, WHEEL_DATE), members[name])
    return path


def wheel(folder: Path, name: str, version: str, tag: str, files: dict[str, bytes] | None = None) -> Path:
    dist = f"{name}-{version}"
    members = dict(files or {f"{name}/__init__.py": b"VALUE = 1\n"})
    members[f"{dist}.dist-info/METADATA"] = (
        f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n".encode()
    )
    members[f"{dist}.dist-info/WHEEL"] = f"Wheel-Version: 1.0\nTag: {tag}\n".encode()
    members[f"{dist}.dist-info/RECORD"] = b""
    return write_zip(folder / f"{dist}-{tag}.whl", members)


def pbs(folder: Path, platform: str, *, links: bool = True, case_pair: bool = True, dbm: bool = True) -> Path:
    """A python-build-standalone-like archive: python/ with an interpreter stand-in (and on Linux links, a
    terminfo pair that differs only in case, and the _dbm module that the bundle must leave out)."""
    path = folder / f"pbs-{platform}.tar.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    files: dict[str, tuple[bytes, int]] = {}
    symlinks: dict[str, str] = {}
    if platform == "win_amd64":
        files["python/python.exe"] = (b"MZ stand-in interpreter", 0o644)
        files["python/Lib/os.py"] = (b"# stand-in\n", 0o644)
        files["python/Lib/__pycache__/os.cpython-312.pyc"] = (b"\x00stand-in", 0o644)
    else:
        files["python/bin/python3.12"] = (b"\x7fELF stand-in interpreter", 0o775)
        files["python/lib/python3.12/os.py"] = (b"# stand-in\n", 0o664)
        if dbm:
            files["python/lib/python3.12/lib-dynload/_dbm.cpython-312-x86_64-linux-gnu.so"] = (
                b"\x7fELF bdb",
                0o775,
            )
        if case_pair:
            files["python/share/terminfo/E/Eterm"] = (b"upper", 0o664)
            files["python/share/terminfo/e/eterm"] = (b"lower", 0o664)
        if links:
            symlinks["python/bin/python3"] = "python3.12"
            symlinks["python/bin/python"] = "python3.12"
    with tarfile.open(path, "w:gz") as tar:
        for name, (data, mode) in sorted(files.items()):
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), mode
            tar.addfile(info, io.BytesIO(data))
        for name, target in sorted(symlinks.items()):
            info = tarfile.TarInfo(name)
            info.type, info.linkname = tarfile.SYMTYPE, target
            tar.addfile(info)
    return path


def uv_wheel(folder: Path, platform: str) -> Path:
    binary = "uv.exe" if platform == "win_amd64" else "uv"
    magic = b"MZ stand-in uv" if platform == "win_amd64" else b"\x7fELF stand-in uv"
    tag = "py3-none-win_amd64" if platform == "win_amd64" else "py3-none-manylinux_2_17_x86_64"
    return wheel(
        folder,
        "uv",
        "0.13.0",
        tag,
        {
            f"uv-0.13.0.data/scripts/{binary}": magic,
            "uv-0.13.0.data/scripts/uvx" + (".exe" if platform == "win_amd64" else ""): magic,
            "uv-0.13.0.dist-info/licenses/LICENSE-APACHE": b"Apache stand-in\n",
            "uv-0.13.0.dist-info/licenses/LICENSE-MIT": b"MIT stand-in\n",
            "uv-0.13.0.dist-info/sboms/uv.cyclonedx.json": b"{}\n",
        },
    )


def pin(path: Path) -> dict[str, Any]:
    return {"url": path.as_uri(), "size": path.stat().st_size, "sha256": sha256(path)}


def lock_entry(name: str, version: str, wheels: list[Path]) -> str:
    rows = ",\n".join(
        f'    {{ url = "{w.as_uri()}", hash = "sha256:{sha256(w)}", size = {w.stat().st_size} }}'
        for w in wheels
    )
    return f'[[package]]\nname = "{name}"\nversion = "{version}"\nwheels = [\n{rows},\n]\n'


def requirement(name: str, version: str, wheels: list[Path], marker: str = "") -> str:
    hashes = " \\\n".join(f"    --hash=sha256:{sha256(w)}" for w in wheels)
    head = f"{name}=={version}" + (f" ; {marker}" if marker else "")
    return f"{head} \\\n{hashes}\n    # via neurogrid\n"


def inputs(tmp: Path, platform: str, **pbs_options: bool) -> bundle.BuildInputs:
    """BuildInputs of a complete, tiny bundle: three third-party packages (one Windows-only by marker, one
    with a too new manylinux wheel next to a fitting one), stand-in interpreter, uv, docs, notices, sdist."""
    src = tmp / "src"
    alpha = wheel(src, "alpha", "1.0", "py3-none-any")
    beta = [
        wheel(src, "beta", "2.0", "cp312-cp312-win_amd64"),
        wheel(src, "beta", "2.0", "cp312-cp312-manylinux_2_28_x86_64"),
        wheel(src, "beta", "2.0", "cp312-cp312-manylinux_2_34_x86_64"),
    ]
    gamma = wheel(src, "gamma", "3.0", "py3-none-any")
    uv_lock = "version = 1\n\n" + "\n".join(
        [
            lock_entry("alpha", "1.0", [alpha]),
            lock_entry("beta", "2.0", beta),
            lock_entry("gamma", "3.0", [gamma]),
        ]
    )
    requirements = (
        requirement("alpha", "1.0", [alpha])
        + requirement("beta", "2.0", beta)
        + requirement("gamma", "3.0", [gamma], "sys_platform == 'win32'")
    )
    ng_wheel = wheel(
        src / "dist", "neurogrid", VERSION, "py3-none-any", {"neurogrid/__init__.py": b"x = 1\n"}
    )
    sdist = src / "dist" / f"neurogrid-{VERSION}.tar.gz"
    sdist.write_bytes(b"stand-in sdist")
    docs = src / "site"
    (docs / "zh").mkdir(parents=True)
    (docs / "index.html").write_text("<html>docs</html>\n", encoding="utf-8")
    (docs / "zh" / "index.html").write_text("<html>文档</html>\n", encoding="utf-8")
    notices = src / "THIRD_PARTY_NOTICES.txt"
    notices.write_text("notices stand-in\n", encoding="utf-8")
    installer = src / "install_pdf_browser.py"
    installer.write_text("# stand-in of the PDF browser installer\n", encoding="utf-8")
    lock = {
        "format_version": 1,
        "python": {
            "version": "3.12.15",
            "build": "20261009",
            "platforms": {p: pin(pbs(src / "pbs", p, **pbs_options)) for p in bundle.PLATFORMS},
        },
        "uv": {
            "version": "0.13.0",
            "platforms": {p: pin(uv_wheel(src / "uv" / p, p)) for p in bundle.PLATFORMS},
        },
        "remove": {
            "linux_x86_64": (
                [
                    {
                        "path": "python/lib/python3.12/lib-dynload/_dbm.cpython-312-x86_64-linux-gnu.so",
                        "reason": "x",
                    }
                ]
                if pbs_options.get("dbm", True)
                else []
            )
        },
    }
    return bundle.BuildInputs(
        platform=platform,
        wheel=ng_wheel,
        sdist=sdist,
        docs=docs,
        notices=notices,
        pdf_installer=installer,
        out=tmp / "out",
        cache=tmp / "cache",
        sign="none",
        lock=lock,
        uv_lock_text=uv_lock,
        requirements=requirements,
        source_date_epoch=EPOCH,
        git_commit="0" * 40,
        environ={},
    )


def members(archive: Path) -> dict[str, tuple[bytes | None, str | None, int]]:
    """Name -> (data, link target, mode) of every member of a bundle archive (directories left out)."""
    found: dict[str, tuple[bytes | None, str | None, int]] = {}
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            for info in z.infolist():
                found[info.filename] = (z.read(info), None, info.external_attr >> 16)
    else:
        with tarfile.open(archive, "r:gz") as tar:
            for member in tar:
                if member.isdir():
                    continue
                handle = tar.extractfile(member) if member.isfile() else None
                found[member.name] = (handle.read() if handle else None, member.linkname or None, member.mode)
    return found


def rewrite(archive: Path, change: Callable[[dict[str, tuple[bytes | None, str | None, int]]], None]) -> Path:
    """The archive with its members changed in place by ``change`` (for tampering tests)."""
    found = members(archive)
    change(found)
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive, "w") as z:
            for name, (data, _, mode) in sorted(found.items()):
                info = zipfile.ZipInfo(name, WHEEL_DATE)
                info.create_system, info.external_attr = 3, mode << 16
                z.writestr(info, data or b"")
    else:
        with tarfile.open(archive, "w:gz") as tar:
            for name, (data, link, mode) in sorted(found.items()):
                info = tarfile.TarInfo(name)
                info.mode = mode & 0o7777
                if link is not None:
                    info.type, info.linkname = tarfile.SYMTYPE, link
                    tar.addfile(info)
                else:
                    info.size = len(data or b"")
                    tar.addfile(info, io.BytesIO(data or b""))
    return archive


def resum(found: dict[str, tuple[bytes | None, str | None, int]], root: str) -> None:
    """Recompute SHA256SUMS of a member dict (tampering that keeps the checksums consistent)."""
    lines = []
    for name in sorted(found):
        data, link, _ = found[name]
        rel = name.removeprefix(root + "/")
        if link is None and rel not in ("SHA256SUMS", "SHA256SUMS.sigstore.json"):
            lines.append(f"{hashlib.sha256(data or b'').hexdigest()}  {rel}\n")
    found[f"{root}/SHA256SUMS"] = ("".join(lines).encode(), None, 0o100644)


def extract(archive: Path, target: Path) -> Path:
    """Extract a bundle archive (zip, or tar.gz without links) and return the bundle folder."""
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            z.extractall(target)
    else:
        with tarfile.open(archive, "r:gz") as tar:
            tar.extractall(target, filter="data")
    (folder,) = list(target.iterdir())
    return folder
