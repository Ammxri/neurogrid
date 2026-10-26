"""`neurogrid report --format pdf` (CLI-05, A-08, A-26): four files for zh,en × html,pdf; without the PDF
browser exit 2 with the install hint and nothing written; HTML works without it; the fixed sentence ends
the output (REP-07)."""

from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import pypdf
import pytest

from conftest import long_path, short_folder  # type: ignore[import-not-found]
from neurogrid import pipeline
from neurogrid.cli import main
from neurogrid.kernel import canonical, fonts
from neurogrid.kernel.errors import PdfError
from neurogrid.kernel.pdf import ENV_BROWSER_DIR
from neurogrid.model.results import Results
from neurogrid.report.texts import disclaimer

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"
FILES = ["report.en.html", "report.en.pdf", "report.zh.html", "report.zh.pdf"]


@pytest.fixture(scope="module")
def results_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    results = pipeline.run_check(FIX / "edf_mixed", pipeline.CheckOptions(as_of=date(2026, 10, 11)))
    path = tmp_path_factory.mktemp("cli-pdf") / "results.json"
    path.write_bytes(canonical.dumps(results))
    return path


def run(args: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    with pytest.raises(SystemExit) as info:
        main(args)
    out, err = capsys.readouterr()
    return int(info.value.code or 0), out, err


def _env(**extra: str) -> dict[str, str]:
    return {**os.environ, "PYTHONIOENCODING": "utf-8", **extra}


@pytest.mark.pdf
def test_report_html_pdf_zh_en_writes_four_files(results_file: Path, tmp_path: Path) -> None:
    """Real subprocesses under Bash and Windows PowerShell 5.1, output folder with a Chinese name."""
    python = Path(sys.executable).as_posix()

    def quoted(path: Path | str) -> str:  # a PowerShell string literal
        return "'" + str(path).replace("'", "''") + "'"

    runs: list[tuple[list[str], Path]] = []
    bash, powershell = shutil.which("bash"), shutil.which("powershell")
    if bash:
        out = tmp_path / "报告 bash"
        script = f'"{python}" -m neurogrid report "$0" --lang zh,en --format html,pdf --out "$1"'
        runs.append(([bash, "-c", script, str(results_file), str(out)], out))
    if powershell:
        out = tmp_path / "报告 powershell"
        script = (
            f"& {quoted(sys.executable)} -m neurogrid report {quoted(results_file)} --lang 'zh,en' "
            f"--format 'html,pdf' --out {quoted(out)}; exit $LASTEXITCODE"
        )
        runs.append(([powershell, "-NoProfile", "-NonInteractive", "-Command", script], out))
    if not runs:
        pytest.skip("neither bash nor powershell found")
    for command, out in runs:
        done = subprocess.run(command, capture_output=True, env=_env(), check=False)
        stdout = done.stdout.decode("utf-8", "replace")
        assert done.returncode == 0, (command[0], done.stderr.decode("utf-8", "replace"))
        assert sorted(p.name for p in out.iterdir()) == FILES
        assert stdout.count("Report written to") == 4 or stdout.count("报告已写入") == 4
        assert stdout.strip().splitlines()[-1] in (disclaimer("en"), disclaimer("zh"))
        assert (out / "report.zh.pdf").read_bytes().startswith(b"%PDF-")


# The characters of the repair note (U+2013, U+00AD, U+2011, U+00B7), each next to a code point of lower
# value that shares its glyph in the static cuts: U+2012 (with U+2013), U+002D (with U+00AD and U+2011);
# U+2027 shares the glyph of U+00B7.
TWIN_NAME = "EEG \u2012\u2013 -\u00ad\u2011 \u00b7\u2027"


def _plain(text: str) -> str:
    """``text`` without white space and soft hyphens (U+00AD is not drawn)."""
    return re.sub("[\\s\u00ad]", "", text)


def _pdf_text(path: Path) -> str:
    return "".join(page.extract_text() or "" for page in pypdf.PdfReader(io.BytesIO(path.read_bytes())).pages)


@pytest.mark.pdf
def test_glyph_twins_in_the_dataset_name_exit_0_with_the_name_as_written(
    results_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dataset data never ends with exit 2 (B2, A-27): a dataset name whose characters share a glyph with
    another code point of the report font gives exit 0 and four reports; the PDF text holds the name as
    written (the soft hyphen is not drawn). Negative control with the glyphs shared as in the font (the
    subsets before the repair): the PDF text reads every character as the lowest code point of its glyph."""
    results = Results.model_validate_json(results_file.read_bytes())
    results.dataset.name = TWIN_NAME
    source = tmp_path / "results.json"
    source.write_bytes(canonical.dumps(results))
    out = tmp_path / "out"
    args = ["report", str(source), "--lang", "zh,en", "--format", "html,pdf", "--out"]
    code, _, err = run([*args, str(out)], capsys)
    assert code == 0, err
    assert sorted(p.name for p in out.iterdir()) == FILES
    for lang in ("zh", "en"):
        assert TWIN_NAME in (out / f"report.{lang}.html").read_text(encoding="utf-8")
        assert _plain(TWIN_NAME) in _plain(_pdf_text(out / f"report.{lang}.pdf")), lang
    kept = tmp_path / "kept"
    fonts._subset.cache_clear()
    try:
        with monkeypatch.context() as patch:
            patch.setattr(fonts, "separate_shared_glyphs", lambda font: {})
            code, _, err = run([*args, str(kept)], capsys)
    finally:
        fonts._subset.cache_clear()  # no other test sees a subset with shared glyphs
    assert code == 0, err  # no phrase the gate requires has a glyph twin of lower code point
    lowest = "EEG\u2012\u2012--\u00b7\u00b7"
    assert all(lowest in _plain(_pdf_text(kept / f"report.{lang}.pdf")) for lang in ("zh", "en"))


def _child_log_state(executable: Path) -> int | None:
    log = executable.parent / "debug.log"
    return log.stat().st_size if log.is_file() else None


@pytest.mark.pdf
def test_long_out_path_writes_the_reports_and_leaves_nothing_behind(
    results_file: Path, pdf_shell: object, tmp_path: Path
) -> None:
    """P2: an --out of 240 characters (measured with the merged state: at 195 characters a debug.log with
    local paths stayed in the current folder, at 210 the run ended in pdf.launch_failed with the install
    check as hint): exit 0, the four files; nothing in the current folder, in the temporary folder (the
    browser's work folder lies there, removed) or next to the shell's executable."""
    out = long_path(tmp_path / "o", 240)
    assert len(str(out)) >= 240
    executable = pdf_shell.executable  # type: ignore[attr-defined]
    log_before = _child_log_state(executable)
    with short_folder("ng-env-") as root:
        temp, cwd = root / "temp", root / "cwd"
        temp.mkdir()
        cwd.mkdir()
        done = subprocess.run(
            [sys.executable, "-m", "neurogrid", "report", str(results_file), "--lang", "zh,en"]
            + ["--format", "html,pdf", "--out", str(out)],
            capture_output=True,
            env=_env(TEMP=str(temp), TMP=str(temp), TMPDIR=str(temp)),
            cwd=cwd,
            check=False,
        )
        assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
        assert sorted(p.name for p in out.iterdir()) == FILES
        assert list(cwd.iterdir()) == [] and list(temp.iterdir()) == []
    assert _child_log_state(executable) == log_before


@pytest.mark.pdf
@pytest.mark.skipif(os.name != "nt", reason="the path limit is Windows' (MAX_PATH); Linux has none")
def test_temporary_folder_too_long_for_the_browser_exits_2_with_its_own_hint(
    results_file: Path, tmp_path: Path
) -> None:
    """P2: a temporary folder (TEMP, TMP, TMPDIR) whose path is too long for the shell's profile ends with
    exit 2 before anything is rendered: the message names the length and the limit, the hint the
    environment variables and the length they may have; nothing is written, also not into the temporary
    folder or the current folder."""
    from neurogrid.kernel import pdf

    out = tmp_path / "out"
    with short_folder("ng-env-") as root:
        temp = root / ("t" * max(1, pdf.TEMP_PATH_LIMIT - len(str(root))))  # one character too many
        cwd = root / "cwd"
        temp.mkdir()
        cwd.mkdir()
        length = len(str(temp))
        assert length > pdf.TEMP_PATH_LIMIT
        done = subprocess.run(
            [sys.executable, "-m", "neurogrid", "report", str(results_file), "--lang", "en"]
            + ["--format", "html,pdf", "--out", str(out)],
            capture_output=True,
            env=_env(TEMP=str(temp), TMP=str(temp), TMPDIR=str(temp)),
            cwd=cwd,
            check=False,
        )
        err = done.stderr.decode("utf-8", "replace")
        assert done.returncode == 2, err
        assert f"has a path of {length} characters" in err
        assert f"on Windows the browser can use at most {pdf.TEMP_PATH_LIMIT}" in err
        assert f"with a path of at most {pdf.TEMP_PATH_LIMIT} characters" in err and "TEMP and TMP" in err
        assert "installer" not in err  # not the misleading hint of a launch failure
        assert not out.exists() and list(temp.iterdir()) == [] and list(cwd.iterdir()) == []


def test_pdf_without_shell_exits_2_with_hint_and_writes_nothing(
    results_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    empty = tmp_path / "no-browser"
    empty.mkdir()
    monkeypatch.setenv(ENV_BROWSER_DIR, str(empty))
    out = tmp_path / "out"
    code, stdout, err = run(["report", str(results_file), "--format", "html,pdf", "--out", str(out)], capsys)
    assert code == 2 and not out.exists() and "Report written" not in stdout
    assert "The PDF browser (Chrome Headless Shell, revision 1243) is not installed" in err
    assert "HTML reports work without it" in err and "install_pdf_browser.py" in err
    # not an offline bundle (this source checkout): the hint is the documentation page (B2)
    assert "documentation, installation page, section 'PDF browser'" in err
    assert str(Path.home()) not in err  # the folder is shown with ~ (A-51)
    code, _, err = run(
        ["--lang", "zh", "report", str(results_file), "--format", "pdf", "--out", str(out)], capsys
    )
    assert code == 2 and "未安装 PDF 浏览器" in err and "“PDF 浏览器”一节" in err and not out.exists()


def test_bundle_installation_hint_names_its_own_installer_command(
    results_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """B2: in an offline-bundle installation (marker file in the prefix) the hint is the command with the
    bundled interpreter and script, the home folder shown as ~ (A-51)."""
    from neurogrid.kernel import pdf

    prefix = tmp_path / "NeuroGrid 0.1"
    python = prefix / "python" / ("python.exe" if os.name == "nt" else "bin/python3.12")
    script = prefix / "tools" / "install_pdf_browser.py"
    for path in (prefix / pdf.BUNDLE_MARKER, python, script):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
    monkeypatch.setattr(pdf.sys, "prefix", str(prefix / "venv"))
    monkeypatch.setenv(ENV_BROWSER_DIR, str(tmp_path / "no-browser"))
    out = tmp_path / "out"
    code, _, err = run(["report", str(results_file), "--format", "pdf", "--out", str(out)], capsys)
    assert code == 2 and not out.exists()
    assert "Install it with: " in err and "--from-zip <zip file> --sha256 <SHA-256>" in err
    home = str(Path.home())
    command = f'"{str(python).replace(home, "~")}" "{str(script).replace(home, "~")}"'
    assert command in err and home not in err


def test_html_only_works_without_shell(results_file: Path, tmp_path: Path) -> None:
    """A-26 'HTML geht immer': no browser, and Playwright is not even imported."""
    probe = (
        "import sys\nfrom neurogrid.cli import main\n"
        "try:\n    main(sys.argv[1:])\nexcept SystemExit as exc:\n    code = exc.code\n"
        "print('playwright' in sys.modules, code)\n"
    )
    out = tmp_path / "out"
    done = subprocess.run(
        [sys.executable, "-c", probe, "report", str(results_file), "--lang", "zh,en", "--out", str(out)],
        capture_output=True,
        env=_env(**{ENV_BROWSER_DIR: str(tmp_path / "nothing")}),
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    assert done.stdout.decode("utf-8").strip().splitlines()[-1] == "False 0"
    assert sorted(p.name for p in out.iterdir()) == ["report.en.html", "report.zh.html"]


def test_ms_playwright_shell_is_never_used(
    results_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Playwright's own browser folder (here: an ms-playwright install of this machine, or a stand-in) is
    never used, also not through PLAYWRIGHT_BROWSERS_PATH."""
    ms_playwright = Path(os.environ.get("LOCALAPPDATA", tmp_path)) / "ms-playwright"
    if not (ms_playwright / "chromium_headless_shell-1243").is_dir():
        ms_playwright = tmp_path / "ms-playwright"
        (ms_playwright / "chromium_headless_shell-1243" / "chrome-headless-shell-win64").mkdir(parents=True)
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(ms_playwright))
    monkeypatch.setenv(ENV_BROWSER_DIR, str(tmp_path / "empty"))
    code, _, err = run(["report", str(results_file), "--format", "pdf", "--out", str(tmp_path / "o")], capsys)
    assert code == 2 and "is not installed" in err and not (tmp_path / "o").exists()


@pytest.mark.pdf
def test_repeated_and_comma_options(
    results_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "a"
    args = [
        "report",
        str(results_file),
        "--lang",
        "zh",
        "--lang",
        "en",
        "--format",
        "html",
        "--format",
        "pdf",
    ]
    code, stdout, _ = run([*args, "--out", str(out)], capsys)
    assert code == 0 and sorted(p.name for p in out.iterdir()) == FILES
    assert stdout.strip().splitlines()[-1] == disclaimer("en")
    out = tmp_path / "b"
    code, _, _ = run(
        ["report", str(results_file), "--lang", " en, zh ", "--format", "PDF, html", "--out", str(out)],
        capsys,
    )
    assert code == 0 and sorted(p.name for p in out.iterdir()) == FILES


def test_unknown_format_and_invalid_browser_folder_exit_2(
    results_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _, err = run(["report", str(results_file), "--format", "html,docx", "--out", str(tmp_path)], capsys)
    assert code == 2 and "Output format 'docx' is not available" in err
    assert not list(tmp_path.glob("report.*"))
    monkeypatch.setenv(ENV_BROWSER_DIR, "relative/folder")
    code, _, err = run(["report", str(results_file), "--format", "pdf", "--out", str(tmp_path)], capsys)
    assert code == 2 and f"{ENV_BROWSER_DIR} must be an absolute folder" in err


def test_report_prints_the_fixed_sentence_last(
    results_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, stdout, _ = run(["report", str(results_file), "--lang", "en", "--out", str(tmp_path)], capsys)
    lines = stdout.strip().splitlines()
    assert code == 0 and lines[-1] == disclaimer("en") and lines[0].startswith("Report written to")
    code, stdout, _ = run(["--lang", "zh", "report", str(results_file), "--out", str(tmp_path)], capsys)
    assert code == 0 and stdout.strip().splitlines()[-1] == disclaimer("zh")


def test_pdf_error_hint_is_redacted_but_not_shortened(
    results_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The hint (here the apt list of a Linux start check) is NeuroGrid's own text: shown in full, the home
    folder as ~ (A-51)."""
    from neurogrid.report import output

    packages = " ".join(f"libpackage{i}" for i in range(40))
    command = str(Path.home() / "neurogrid" / "python.exe")

    def fail(environ: object) -> None:
        raise PdfError(
            "pdf.linux_libraries",
            libraries="libnss3.so",
            hint=("pdf.install.apt", {"distribution": "debian12", "packages": f"{packages} {command}"}),
        )

    monkeypatch.setattr(output, "locate_shell", fail)
    code, _, err = run(["report", str(results_file), "--format", "pdf", "--out", str(tmp_path / "x")], capsys)
    assert code == 2 and "libnss3.so" in err and packages in err
    assert str(Path.home()) not in err and "~" in err
    assert len(err.splitlines()) == 2
