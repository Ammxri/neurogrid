"""The built site in the Chrome Headless Shell: search works offline over 127.0.0.1, file:// pages need no
network (TECH-06, A-28). The browser is located like for the PDF (kernel.pdf.locate_shell, D-08): without it
the tests are skipped with the reason, unless NEUROGRID_REQUIRE_PDF=1 (CI), then they fail."""

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

pytestmark = pytest.mark.browser

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


def _browser_args(work: Path) -> tuple[str, list[str]]:
    """The executable of the NeuroGrid PDF browser and the fixed Chromium flags of kernel.pdf; the shell's log
    goes to the work folder, not next to the executable (A-54)."""
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401

        from neurogrid.kernel import pdf
        from neurogrid.kernel.errors import NeuroGridError
    except ImportError as exc:
        _unavailable(f"PDF browser support not importable ({type(exc).__name__}: {exc.name})")
        raise
    try:
        shell = pdf.locate_shell(os.environ)
    except NeuroGridError as exc:
        _unavailable(f"PDF browser not installed ({exc.message_key}); see tools/install_pdf_browser.py")
        raise
    # the PDF flags map every host name to "not found"; the docs server on 127.0.0.1 must stay reachable
    flags = [
        f"{flag}, EXCLUDE 127.0.0.1" if flag.startswith("--host-resolver-rules=") else flag
        for flag in pdf.CHROMIUM_FLAGS
    ]
    return str(shell.executable), [*flags, f"--log-file={work / 'chromium.log'}"]


@pytest.fixture(scope="module")
def browser(built_site: Any, tmp_path_factory: pytest.TempPathFactory) -> Iterator[Any]:
    assert built_site.returncode == 0, built_site.output[-2000:]
    executable, flags = _browser_args(tmp_path_factory.mktemp("browser"))
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        instance = playwright.chromium.launch(executable_path=executable, headless=True, args=flags)
        try:
            yield instance
        finally:
            instance.close()


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
