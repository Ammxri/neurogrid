"""tools/scan_runtime_network.py (A-49 scan of the installed runtime packages; NG-N01): planted network
imports and telemetry markers in a stand-in distribution are found, reviewed baseline entries suppress them,
and unreviewed, changed, outdated or stale entries fail. The real environment is checked against the reviewed
baseline too."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

import scan_runtime_network as scan

ROOT = Path(__file__).resolve().parents[2]


def _site(tmp_path: Path, version: str = "1.0", net: str | None = None) -> Path:
    site = tmp_path / "site"
    files = {
        "fakepkg/__init__.py": "VALUE = 1\n",
        "fakepkg/net.py": net if net is not None else "import socket\nfrom urllib import request\n",
        "fakepkg/telemetry.py": "DSN = 'https://key@sentry.io/1'\n\ndef disable_telemetry_events():\n"
        "    pass\n",
        "fakepkg/clean.py": "import json\nfrom . import net\n",
        "fakepkg/broken.py": "def (:\n",
    }
    for rel, text in files.items():
        (site / rel).parent.mkdir(parents=True, exist_ok=True)
        (site / rel).write_text(text, encoding="utf-8")
    info = site / f"fakepkg-{version}.dist-info"
    info.mkdir()
    (info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: fakepkg\nVersion: {version}\n", encoding="utf-8"
    )
    (info / "RECORD").write_text(
        "".join(f"{rel},,\n" for rel in files) + f"{info.name}/RECORD,,\n", encoding="utf-8"
    )
    return site


def _entry(file: str, hits: list[str], version: str = "1.0") -> dict[str, object]:
    return {
        "distribution": "fakepkg",
        "version": version,
        "file": file,
        "hits": hits,
        "reason": "r",
        "control": "c",
    }


REVIEWED = [
    _entry("fakepkg/broken.py", ["unparsable"]),
    _entry("fakepkg/net.py", ["import:socket", "import:urllib.request"]),
    _entry("fakepkg/telemetry.py", ["marker:sentry.io", "marker:telemetry"]),
]


def _run(site: Path, baseline: list[dict[str, object]], tmp_path: Path, *extra: str) -> int:
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps({"format_version": 1, "entries": baseline}), encoding="utf-8")
    args = ["--site-packages", str(site), "--baseline", str(path), "--distribution", "fakepkg", *extra]
    return scan.main(args)


def test_planted_hits_are_found() -> None:
    assert scan.file_hits("import socket\nimport ssl as s\nfrom http.client import HTTPConnection\n") == {
        "import:socket",
        "import:ssl",
        "import:http.client",
    }
    assert scan.file_hits("from urllib import request\n") == {"import:urllib.request"}
    assert scan.file_hits("from urllib import parse\nimport json\n") == set()
    assert scan.file_hits("x = 'https://pypi.org/pypi/mne/json'\n") == {"marker:pypi.org/pypi"}
    assert scan.file_hits("import requests.adapters\n") == {"import:requests"}
    assert scan.file_hits("# the word ArgsEntry is not sentry\n") == set()


def test_reviewed_hits_pass(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    site = _site(tmp_path)
    assert _run(site, REVIEWED, tmp_path) == 0
    assert "3 files with hits, 0 problem(s)" in capsys.readouterr().out


def test_unreviewed_hit_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    site = _site(tmp_path)
    assert _run(site, REVIEWED[1:], tmp_path) == 1
    assert "unreviewed: fakepkg 1.0 fakepkg/broken.py ['unparsable']" in capsys.readouterr().out


def test_changed_hits_fail(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    site = _site(tmp_path, net="import socket\nimport ftplib\n")
    assert _run(site, REVIEWED, tmp_path) == 1
    assert "hits changed in fakepkg/net.py" in capsys.readouterr().out


def test_an_upgrade_needs_a_new_review(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    site = _site(tmp_path, version="1.1")
    assert _run(site, REVIEWED, tmp_path) == 1
    assert "reviewed for 1.0, installed 1.1: fakepkg/net.py" in capsys.readouterr().out


def test_stale_and_incomplete_entries_fail(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    site = _site(tmp_path)
    stale = [*REVIEWED, _entry("fakepkg/clean.py", ["import:socket"])]
    assert _run(site, stale, tmp_path) == 1
    assert "stale baseline entry (hit no longer found): fakepkg fakepkg/clean.py" in capsys.readouterr().out
    empty_reason = [{**REVIEWED[0], "reason": ""}, *REVIEWED[1:]]
    assert _run(site, empty_reason, tmp_path) == 1
    assert "not reviewed (reason or control empty)" in capsys.readouterr().out


def test_entries_of_other_platforms_are_kept(tmp_path: Path) -> None:
    site = _site(tmp_path)
    other = [
        *REVIEWED,
        _entry("fakepkg/_windows_only.py", ["import:socket"]),
        {**_entry("x/y.py", []), "distribution": "absent"},
    ]
    assert _run(site, other, tmp_path) == 0


def test_draft_keeps_reviews_and_lists_new_hits_for_review(tmp_path: Path) -> None:
    site = _site(tmp_path)
    out = tmp_path / "draft.json"
    assert _run(site, REVIEWED[1:], tmp_path, "--draft", str(out)) == 0
    entries = json.loads(out.read_text(encoding="utf-8"))["entries"]
    by_file = {e["file"]: e for e in entries}
    assert by_file["fakepkg/net.py"]["reason"] == "r"
    assert by_file["fakepkg/broken.py"]["reason"] == "" and by_file["fakepkg/broken.py"]["hits"] == [
        "unparsable"
    ]


def test_usage_error_exits_2(tmp_path: Path) -> None:
    assert scan.main(["--unknown"]) == 2
    broken = tmp_path / "baseline.json"
    broken.write_text('{"format_version": 9}', encoding="utf-8")
    assert scan.main(["--baseline", str(broken), "--distribution", "x"]) == 2


@pytest.mark.skipif(
    not (os.environ.get("UV") or shutil.which("uv")), reason="uv not found: run through `uv run`"
)
def test_installed_runtime_packages_match_the_reviewed_baseline(capsys: pytest.CaptureFixture[str]) -> None:
    code = scan.main([])
    out = capsys.readouterr().out
    assert code == 0, out
    baseline = json.loads((ROOT / "license-gate" / "network_baseline.json").read_text(encoding="utf-8"))
    assert all(e["reason"].strip() and e["control"].strip() for e in baseline["entries"])
