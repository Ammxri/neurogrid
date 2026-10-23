"""One offline build of the documentation site per test session, shared by the documentation tests
(TECH-06). A helper module, not a conftest.py: the tests import tests/conftest.py as ``conftest``, so a second
conftest in this folder would shadow it."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EPOCH = "1792800000"
_BUILDS: dict[str, Build] = {}


@dataclass(frozen=True)
class Build:
    site: Path
    returncode: int
    output: str


def build(site: Path, epoch: str = EPOCH) -> Build:
    """tools/build_docs.py in its own process (its audit hook must not stay in the test process)."""
    env = {**os.environ, "SOURCE_DATE_EPOCH": epoch, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "build_docs.py"), "--site-dir", str(site)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=600,
    )
    return Build(site=site, returncode=proc.returncode, output=proc.stdout + proc.stderr)


def built(base: Path) -> Build:
    """The session's site, built once below ``base`` (a session temporary folder) and then reused."""
    if "site" not in _BUILDS:
        _BUILDS["site"] = build(Path(tempfile.mkdtemp(prefix="docs-", dir=base)) / "site")
    return _BUILDS["site"]
