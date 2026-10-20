from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

from neurogrid.kernel import netguard

FIXTURES = Path(__file__).parent / "fixtures" / "synthetic"
TOOLS = Path(__file__).parent.parent / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))  # lets tests reuse the fixture writer in tools/gen_fixtures.py
AS_OF = date(2026, 10, 11)
# Raw folders must document the EEG-BIDS required fields in neurogrid.toml (M02-01, A-03, A-05). Tests whose
# subject is something else use this configuration (also used by CI) so that only their subject decides the
# exit code.
DOCUMENTED_TOML = (FIXTURES.parent / "documented.toml").read_text(encoding="utf-8")


def documented_config(folder: Path, extra: str = "", name: str = "documented.toml") -> Path:
    """A neurogrid.toml in ``folder`` that documents the required metadata, plus ``extra`` lines."""
    path = folder / name
    path.write_text(DOCUMENTED_TOML + extra, encoding="utf-8")
    return path


@pytest.fixture(scope="session", autouse=True)
def _offline() -> None:
    """Every test runs with the network guard that NeuroGrid installs at start-up (A-49)."""
    netguard.install()


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


def dir_link(link: Path, target: Path) -> None:
    """A directory link: a symlink where permitted, else a Windows junction (needs no extra rights)."""
    try:
        link.symlink_to(target, target_is_directory=True)
        return
    except OSError:
        pass
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
        return
    pytest.skip("directory links not permitted on this system")
