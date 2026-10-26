from __future__ import annotations

import os
import shutil
import sys
import tempfile
from collections.abc import Iterator
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
# On Windows the PDF browser starts only while the paths of its profile, inside the run's work folder next to
# the output (A-54), stay within 260 characters: measured with revision 1243, a work folder of 210 characters
# no longer starts, and from 197 characters on Chromium's logging falls back to the current folder
# (kernel/pdf.py). pytest's folder (--basetemp) can be of any length, so the tests that start the browser
# write below one short folder of the system's temporary folder instead (browser_root, browser_tmp).
BROWSER_ROOT_LIMIT = 120


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


@pytest.fixture(scope="session")
def pdf_shell() -> object:
    """The installed PDF browser (kernel.pdf.locate_shell, the only way the project starts a browser),
    located once per session from the environment the tests start with.

    Without it, tests marked ``pdf`` (and fixtures that request this one) are skipped with the reason,
    unless NEUROGRID_REQUIRE_PDF=1 (CI and the final local run): then a missing browser fails them."""
    from neurogrid.kernel.errors import PdfError
    from neurogrid.kernel.pdf import locate_shell

    try:
        return locate_shell(os.environ)
    except PdfError as exc:
        reason = (
            f"PDF browser not available ({exc.message_key}); install it with tools/install_pdf_browser.py"
        )
        if os.environ.get("NEUROGRID_REQUIRE_PDF") == "1":
            pytest.fail(reason)
        pytest.skip(reason)


@pytest.fixture(scope="session")
def browser_root() -> Iterator[Path]:
    """The session's folder directly below the system's temporary folder for the tests that start the PDF
    browser (independent of --basetemp, BROWSER_ROOT_LIMIT), removed at the end."""
    root = Path(tempfile.mkdtemp(prefix="ngpdf-"))
    try:
        assert len(str(root)) <= BROWSER_ROOT_LIMIT, f"temporary folder too long for the PDF tests: {root}"
        yield root
    finally:
        shutil.rmtree(root)


@pytest.fixture
def browser_tmp(browser_root: Path) -> Path:
    """A new folder of one test below browser_root."""
    return Path(tempfile.mkdtemp(prefix="t", dir=browser_root))


@pytest.fixture(autouse=True)
def _pdf_marker(request: pytest.FixtureRequest) -> None:
    if request.node.get_closest_marker("pdf") is not None:
        request.getfixturevalue("pdf_shell")


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
