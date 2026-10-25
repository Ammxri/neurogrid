"""The real offline bundles (marker ``bundle``, not part of the default run; UF-08, NG-N04, V-01, A-26, A-48).

tools/bundle.py builds both platforms from uv.lock exactly as offline.yml does, twice and byte-identically;
verify passes on each archive; on Windows the clean room (packaging/ci/cleanroom_windows.ps1 -NoOsAudit: fresh
folder, PATH = System32 only, dead proxies, no security setting changed) installs the Windows bundle with its
own installer and runs every v0.1 command from the installation.

Inputs as in offline.yml: wheel and sdist from `uv build`, the documentation site built beforehand into site/
(`python tools/build_docs.py --site-dir site`), THIRD_PARTY_NOTICES.txt and tools/install_pdf_browser.py. The
build runs as its own process: it downloads the pinned interpreter, uv and the locked wheels into the bundle
cache (NEUROGRID_BUNDLE_CACHE or .local/bundle-cache; D-06), while the network guard of this test process
stays active. Run with: uv run pytest -m bundle tests/packaging/test_bundle_real.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from test_packaging_texts import documented_prefix_limit

ROOT = Path(__file__).resolve().parents[2]
UV = os.environ.get("UV") or shutil.which("uv")
INPUTS = {
    "documentation site (python tools/build_docs.py --site-dir site)": ROOT / "site" / "index.html",
    "THIRD_PARTY_NOTICES.txt (python tools/notices.py)": ROOT / "THIRD_PARTY_NOTICES.txt",
    "tools/install_pdf_browser.py": ROOT / "tools" / "install_pdf_browser.py",
}
pytestmark = pytest.mark.bundle


def _missing_inputs() -> list[str]:
    missing = [name for name, path in INPUTS.items() if not path.is_file()]
    return missing + ([] if UV else ["uv (run through `uv run` or set UV)"])


def _run(command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=timeout, check=False
    )


@pytest.fixture(scope="module")
def dist(tmp_path_factory: pytest.TempPathFactory) -> Path:
    missing = _missing_inputs()
    if missing:
        pytest.skip("inputs of the real bundle missing: " + "; ".join(missing))
    assert UV is not None
    out = tmp_path_factory.mktemp("dist")
    result = _run([UV, "build", "--out-dir", str(out)], timeout=900)
    assert result.returncode == 0, result.stderr[-2000:]
    return out


@pytest.fixture(scope="module")
def bundles(dist: Path, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    (wheel,) = dist.glob("neurogrid-*-py3-none-any.whl")
    built: dict[str, Path] = {}
    for platform in ("win_amd64", "linux_x86_64"):
        archives = []
        for attempt in ("a", "b"):
            out = tmp_path_factory.mktemp(f"{platform}-{attempt}")
            command = [sys.executable, str(ROOT / "tools" / "bundle.py"), "build", "--platform", platform]
            command += ["--wheel", str(wheel), "--docs", str(ROOT / "site"), "--out", str(out)]
            command += ["--notices", str(INPUTS["THIRD_PARTY_NOTICES.txt (python tools/notices.py)"])]
            result = _run(command, timeout=3600)
            assert result.returncode == 0, result.stdout[-1000:] + result.stderr[-3000:]
            (archive,) = out.glob("neurogrid-*-offline-*")
            archives.append(archive)
        assert archives[0].read_bytes() == archives[1].read_bytes(), platform  # reproducible build
        built[platform] = archives[0]
    return built


@pytest.mark.parametrize("platform", ["win_amd64", "linux_x86_64"])
def test_real_bundle_builds_reproducibly_and_passes_verify(bundles: dict[str, Path], platform: str) -> None:
    archive = bundles[platform]
    assert archive.name.endswith(".zip" if platform == "win_amd64" else ".tar.gz")
    assert archive.stat().st_size < 2 * 1024**3
    result = _run([sys.executable, str(ROOT / "tools" / "bundle.py"), "verify", str(archive)], timeout=900)
    assert result.returncode == 0, result.stdout[-3000:]


def test_documented_windows_prefix_limit_is_the_one_of_the_built_bundle(bundles: dict[str, Path]) -> None:
    """The longest relative path the installation pages name (test_packaging_texts.py) is the one the built
    Windows bundle's BUNDLE.json gives install.ps1, for this version."""
    with zipfile.ZipFile(bundles["win_amd64"]) as archive:
        (name,) = [n for n in archive.namelist() if n.count("/") == 1 and n.endswith("/BUNDLE.json")]
        info = json.loads(archive.read(name))
    for lang in ("en", "zh"):
        assert documented_prefix_limit(lang)[:2] == (info["version"], info["max_relative_install_path"]), lang


@pytest.mark.skipif(sys.platform != "win32", reason="the Windows clean room needs Windows")
def test_windows_clean_room(bundles: dict[str, Path], tmp_path: Path) -> None:
    powershell = shutil.which("powershell")
    assert powershell is not None
    evidence = tmp_path / "evidence"
    script = ROOT / "packaging" / "ci" / "cleanroom_windows.ps1"
    command = [powershell, "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]
    command += ["-Archive", str(bundles["win_amd64"]), "-Evidence", str(evidence), "-NoOsAudit"]
    result = subprocess.run(command, capture_output=True, timeout=3600, check=False)
    codes = (evidence / "exit-codes.txt").read_text(encoding="utf-8")
    assert result.returncode == 0, codes + result.stderr.decode("utf-8", "replace")[-3000:]
    steps = dict(line.split(" ", 2)[:2] for line in codes.splitlines())
    assert steps["install"] == "0" and steps["report-html"] == "0" and steps["usage-error"] == "2"
    assert "all steps passed" in (evidence / "summary.txt").read_text(encoding="utf-8")
