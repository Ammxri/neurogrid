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
