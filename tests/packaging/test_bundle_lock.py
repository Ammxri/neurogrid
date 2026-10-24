"""packaging/bundle_lock.json (KONZEPT 1.6, A-11, A-26, D-06): the pinned interpreter and uv of the offline
bundle.

The values were taken from the release SHA256SUMS of python-build-standalone 20261009 and the PyPI data of uv
0.13.0 with `tools/bundle.py lock` (23.10.2026); here their shape and their agreement with the workflows are
checked.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

import bundle

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))


def test_lock_loads_and_pins_both_platforms() -> None:
    lock = bundle.load_bundle_lock()
    assert lock["python"]["version"] == "3.12.15" and lock["python"]["build"] == "20261009"
    assert lock["python"]["flavor"] == "install_only_stripped"
    for platform in bundle.PLATFORMS:
        python_pin = lock["python"]["platforms"][platform]
        release = "https://github.com/astral-sh/python-build-standalone/releases/download/20261009/"
        assert python_pin["url"].startswith(release + "cpython-3.12.15%2B20261009-")
        assert python_pin["url"].endswith("-install_only_stripped.tar.gz")
        uv_pin = lock["uv"]["platforms"][platform]
        assert uv_pin["url"].startswith("https://files.pythonhosted.org/packages/")
        tag = "win_amd64" if platform == "win_amd64" else "manylinux_2_17_x86_64.manylinux2014_x86_64"
        assert uv_pin["url"].endswith(f"/uv-{lock['uv']['version']}-py3-none-{tag}.whl")
    assert lock["python"]["platforms"]["win_amd64"]["url"].count("x86_64-pc-windows-msvc") == 1
    assert lock["python"]["platforms"]["linux_x86_64"]["url"].count("x86_64-unknown-linux-gnu") == 1


def test_only_the_berkeley_db_module_is_removed_and_the_reason_is_recorded() -> None:
    lock = bundle.load_bundle_lock()
    assert set(lock["remove"]) == {"linux_x86_64"}
    (removal,) = lock["remove"]["linux_x86_64"]
    assert removal["path"] == "python/lib/python3.12/lib-dynload/_dbm.cpython-312-x86_64-linux-gnu.so"
    assert "Sleepycat" in removal["reason"]


def test_uv_version_of_the_bundle_is_the_uv_version_of_every_workflow() -> None:
    version = bundle.load_bundle_lock()["uv"]["version"]
    assert WORKFLOWS
    for path in WORKFLOWS:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        uses_uv = "astral-sh/setup-uv@" in path.read_text(encoding="utf-8")
        if uses_uv:
            assert data["env"]["UV_VERSION"] == version, path.name
    assert re.fullmatch(r"\d+\.\d+\.\d+", version)


@pytest.mark.parametrize(
    "change, message",
    [
        (lambda d: d.update(format_version=2), "format_version"),
        (lambda d: d["python"]["platforms"].pop("linux_x86_64"), "no pin for linux_x86_64"),
        (
            lambda d: d["uv"]["platforms"]["win_amd64"].update(url="http://example.org/uv.whl"),
            "must be https",
        ),
        (lambda d: d["python"]["platforms"]["win_amd64"].update(sha256="ABC"), "64 lowercase hex"),
        (lambda d: d["python"]["platforms"]["win_amd64"].update(size=0), "positive integer"),
        (lambda d: d["python"].update(version="3.13.1"), "CPython 3.12"),
        (lambda d: d["remove"]["linux_x86_64"][0].update(reason=""), "needs a reason"),
    ],
)
def test_broken_locks_are_refused(tmp_path: Path, change: object, message: str) -> None:
    import json

    data = json.loads((ROOT / "packaging" / "bundle_lock.json").read_text(encoding="utf-8"))
    change(data)  # type: ignore[operator]
    path = tmp_path / "bundle_lock.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(bundle.BundleError, match=message):
        bundle.load_bundle_lock(path)
