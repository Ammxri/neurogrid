"""The built site in the Chrome Headless Shell: search works offline over 127.0.0.1, file:// pages need no
network (TECH-06, A-28). The browser is located and started like for the PDF (kernel.pdf: locate_shell, the
launch arguments with the GPU inside the browser process, the browser and driver environments, D-08, A-54);
a debug.log that a child process of the shell appends next to its executable is undone afterwards (A-51).
Without the shell the tests are skipped with the reason, unless NEUROGRID_REQUIRE_PDF=1 (CI), then they
fail."""

from __future__ import annotations

import functools
import http.server
import os
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import docs_site  # type: ignore[import-not-found]
import pytest

QUERIES = (
    ("zh/index.html", "采样率"),
    ("zh/index.html", "工频"),
    ("zh/index.html", "阈值"),
    ("index.html", "line noise"),
)
HINTS = {"en": "Search needs a local server (see Installation)", "zh": "搜索需通过本地服务器打开（见“安装”）"}


@pytest.fixture(scope="session")
def built_site(tmp_path_factory: pytest.TempPathFactory) -> docs_site.Build:
    return docs_site.built(tmp_path_factory.getbasetemp())


def _unavailable(reason: str) -> None:
    if os.environ.get("NEUROGRID_REQUIRE_PDF") == "1":
        pytest.fail(f"browser required (NEUROGRID_REQUIRE_PDF=1): {reason}")
    pytest.skip(reason)


def _pdf_module() -> Any:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401

        from neurogrid.kernel import pdf
    except ImportError as exc:
        _unavailable(f"PDF browser support not importable ({type(exc).__name__}: {exc.name})")
        raise
    return pdf


def _shell(pdf: Any) -> Any:
    from neurogrid.kernel.errors import NeuroGridError

    try:
        return pdf.locate_shell(os.environ)
    except NeuroGridError as exc:
        _unavailable(f"PDF browser not installed ({exc.message_key}); see tools/install_pdf_browser.py")
        raise


def launch_flags(arguments: list[str]) -> list[str]:
    """The PDF printer's launch arguments with one change: they map every host name to "not found", the docs
    server on 127.0.0.1 must stay reachable."""
    return [
        f"{flag}, EXCLUDE 127.0.0.1" if flag.startswith("--host-resolver-rules=") else flag
        for flag in arguments
    ]


class ChildLog:
    """debug.log next to the shell's executable as the tests found it: absent or with its size. On Windows a
    child process of the shell appends to it instead of the --log-file; restore() removes a file the tests
    created or cuts what they appended (A-51, A-54: nothing of a run stays in NeuroGrid's browser folder)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.size = path.stat().st_size if path.is_file() else None

    def restore(self) -> None:
        if self.size is None:
            self.path.unlink(missing_ok=True)
        elif self.path.stat().st_size > self.size:
            with self.path.open("r+b") as handle:
                handle.truncate(self.size)

    def unchanged(self) -> bool:
        return (self.path.stat().st_size if self.path.is_file() else None) == self.size


@pytest.fixture(scope="module")
def browser(built_site: Any) -> Iterator[Any]:
    """The shell with its profile in a kernel.pdf.browser_work folder: short and independent of pytest's
    basetemp (the shell cannot use long paths on Windows, P2)."""
    assert built_site.returncode == 0, built_site.output[-2000:]
    pdf = _pdf_module()
    shell = _shell(pdf)
    from playwright.sync_api import sync_playwright

    child_log = ChildLog(shell.executable.parent / pdf.CHILD_LOG)
    with pdf.browser_work() as work:
        try:
            with pdf.driver_environment(work):
                playwright = sync_playwright().start()
            try:
                flags = launch_flags(pdf.launch_arguments(work))
                assert pdf.IN_PROCESS_GPU in flags and f"--log-file={work / 'chromium.log'}" in flags
                instance = playwright.chromium.launch(
                    executable_path=str(shell.executable),
                    headless=True,
                    args=flags,
                    env=pdf.browser_environment(work),
                )
                try:
                    yield instance
                finally:
                    instance.close()
            finally:
                playwright.stop()
        finally:
            child_log.restore()  # after the last browser process has ended
    assert child_log.unchanged(), child_log.path


@pytest.fixture(scope="module")
def server(built_site: Any) -> Iterator[str]:
    handler = functools.partial(_QuietHandler, directory=str(built_site.site))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass


@pytest.mark.browser
def test_search_finds_zh_and_en_offline(browser: Any, server: str) -> None:
    context = browser.new_context()
    blocked: list[str] = []

    def guard(route: Any) -> None:
        if route.request.url.startswith(server + "/"):
            route.continue_()
        else:
            blocked.append(route.request.url)
            route.abort()

    context.route("**/*", guard)
    page = context.new_page()
    hits = {}
    for start, query in QUERIES:
        page.goto(f"{server}/{start}", wait_until="load")
        page.wait_for_selector("input.md-search__input")
        page.focus("input.md-search__input")
        page.keyboard.insert_text(query)
        page.wait_for_selector(".md-search-result__item", timeout=15_000)
        hits[query] = page.locator(".md-search-result__item").count()
        page.fill("input.md-search__input", "")
    context.close()
    assert all(count >= 1 for count in hits.values()), hits
    assert blocked == []


@pytest.mark.browser
def test_file_url_pages_work_without_network(browser: Any, built_site: Any) -> None:
    context = browser.new_context(offline=True)
    page = context.new_page()
    requests: list[str] = []
    page.on("request", lambda request: requests.append(request.url))
    for start, lang in (("index.html", "en"), ("zh/index.html", "zh"), ("zh/metrics.html", "zh")):
        page.goto((built_site.site / start).as_uri(), wait_until="load")
        field = page.locator("input.md-search__input")
        assert page.evaluate("document.documentElement.lang") == lang
        assert field.is_disabled()
        assert field.get_attribute("placeholder") == HINTS[lang]
    links = page.locator("a[hreflang]").evaluate_all("els => els.map(e => e.getAttribute('href'))")
    assert links and all(not link.startswith(("/", "http")) for link in links), links
    context.close()
    assert [url for url in requests if not url.startswith(("file:", "data:"))] == []


# --- the launch helpers (no browser needed) -----------------------------------------------------------------


def test_launch_flags_keep_the_pdf_arguments_and_reach_the_local_server() -> None:
    arguments = [
        "--disable-sync",
        "--host-resolver-rules=MAP * ~NOTFOUND",
        "--in-process-gpu",
        "--log-file=x",
    ]
    assert launch_flags(arguments) == [
        "--disable-sync",
        "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
        "--in-process-gpu",
        "--log-file=x",
    ]


def test_child_log_is_removed_or_cut_back(tmp_path: Path) -> None:
    log = tmp_path / "debug.log"
    absent = ChildLog(log)
    log.write_bytes(b"[1024/120000.000:ERROR:gpu] message\n")
    assert not absent.unchanged()
    absent.restore()
    assert not log.exists() and absent.unchanged()
    log.write_bytes(b"older lines\n")
    present = ChildLog(log)
    present.restore()  # nothing appended: left alone
    with log.open("ab") as handle:
        handle.write(b"appended by a run\n")
    assert not present.unchanged()
    present.restore()
    assert log.read_bytes() == b"older lines\n" and present.unchanged()
