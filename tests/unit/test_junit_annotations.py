"""tools/junit_annotations.py (TECH-05): the GitHub annotations that CI prints for failed tests, read from a
JUnit XML report that a real pytest run wrote."""

from __future__ import annotations

import subprocess
import sys
import xml.etree.ElementTree as ElementTree
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[2] / "tools" / "junit_annotations.py"

SAMPLE = """
import pytest


@pytest.fixture
def broken():
    raise RuntimeError("setup went wrong")


def test_passes():
    assert True


def test_fails():
    assert 1 + 1 == 3, "first line of the reason\\nsecond line"


@pytest.mark.parametrize("value", ["a,b", "c:d"])
def test_parametrized(value):
    assert value == "x"


def test_setup_error(broken):
    pass


@pytest.mark.skip(reason="not here")
def test_skipped():
    pass


class TestGroup:
    def test_in_class(self):
        raise ValueError("100% wrong")
"""


def _run(*args: str, cwd: Path) -> list[str]:
    done = subprocess.run(
        [sys.executable, str(TOOL), *args], capture_output=True, cwd=cwd, check=False, encoding="utf-8"
    )
    assert done.returncode == 0, done.stderr
    assert done.stderr == ""
    return done.stdout.splitlines()


@pytest.fixture(scope="module")
def report(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("junit")
    (root / "pkg").mkdir()
    (root / "pkg" / "test_sample.py").write_text(SAMPLE, encoding="utf-8")
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--rootdir", str(root)]
        + ["--junitxml=pytest-junit.xml", "pkg"],
        capture_output=True,
        cwd=root,
        check=False,
    )
    assert done.returncode == 1, done.stdout.decode("utf-8", "replace")
    return root / "pytest-junit.xml"


def test_every_failed_test_gets_one_error_annotation_with_its_node_id(report: Path) -> None:
    lines = _run(report.name, cwd=report.parent)
    assert lines == [
        "::error title=pkg/test_sample.py%3A%3Atest_fails::AssertionError: first line of the reason",
        "::error title=pkg/test_sample.py%3A%3Atest_parametrized[a%2Cb]::AssertionError: assert 'a,b' == 'x'",
        "::error title=pkg/test_sample.py%3A%3Atest_parametrized[c%3Ad]::AssertionError: assert 'c:d' == 'x'",
        "::error title=pkg/test_sample.py%3A%3Atest_setup_error::"
        'failed on setup with "RuntimeError: setup went wrong"',
        "::error title=pkg/test_sample.py%3A%3ATestGroup%3A%3Atest_in_class::ValueError: 100%25 wrong",
    ]


def test_the_summary_names_the_counts(report: Path) -> None:
    assert _run(report.name, "--summary", cwd=report.parent) == [
        "::error title=pytest summary::4 failed, 1 errors, 1 passed, 1 skipped (7 tests); 5 of 5 annotated,"
        " the full list is in the job log and in pytest-junit.xml"
    ]


def test_at_most_the_limit_is_annotated(report: Path) -> None:
    lines = _run(report.name, "--limit", "2", cwd=report.parent)
    assert [line.split("::")[1] for line in lines] == [
        "error title=pkg/test_sample.py%3A%3Atest_fails",
        "error title=pkg/test_sample.py%3A%3Atest_parametrized[a%2Cb]",
    ]
    summary = _run(report.name, "--limit", "2", "--summary", cwd=report.parent)
    assert len(summary) == 1 and "; 2 of 5 annotated," in summary[0]


def test_node_ids_without_a_test_file_keep_the_reported_names(report: Path) -> None:
    lines = _run(report.name, "--root", str(report.parent / "pkg"), cwd=report.parent)
    assert lines[0].startswith("::error title=pkg.test_sample%3A%3Atest_fails::")


def test_a_passing_run_gives_no_test_annotation(tmp_path: Path) -> None:
    (tmp_path / "pytest-junit.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest" tests="1">'
        '<testcase classname="tests.test_a" name="test_ok" time="0.1"/></testsuite></testsuites>',
        encoding="utf-8",
    )
    assert _run("pytest-junit.xml", cwd=tmp_path) == []
    assert _run("pytest-junit.xml", "--summary", cwd=tmp_path) == [
        "::error title=pytest summary::0 failed, 0 errors, 1 passed, 0 skipped (1 tests); 0 of 0 annotated,"
        " the full list is in the job log and in pytest-junit.xml"
    ]


def test_a_missing_or_broken_report_is_said_in_one_annotation(tmp_path: Path) -> None:
    (missing,) = _run("absent.xml", cwd=tmp_path)
    assert missing.startswith("::error title=pytest summary::no readable JUnit report absent.xml: ")
    (tmp_path / "broken.xml").write_text("<testsuites>", encoding="utf-8")
    (broken,) = _run("broken.xml", "--summary", cwd=tmp_path)
    assert broken.startswith("::error title=pytest summary::no readable JUnit report broken.xml: ParseError")


def test_messages_and_titles_are_escaped_for_workflow_commands() -> None:
    sys.path.insert(0, str(TOOL.parent))
    try:
        import junit_annotations as tool  # type: ignore[import-not-found]
    finally:
        sys.path.remove(str(TOOL.parent))
    assert tool.escape_data("50% a\r\nb") == "50%25 a%0D%0Ab"
    assert tool.escape_property("t.py::x[a,b]") == "t.py%3A%3Ax[a%2Cb]"
    long = tool.first_line(ElementTree.Element("failure", message="x" * 600))
    assert len(long) == tool.MESSAGE_LENGTH and long.endswith("x…")
    text_only = ElementTree.Element("error", message="")
    text_only.text = "\n  Traceback line one\nline two\n"
    assert tool.first_line(text_only) == "Traceback line one"
    assert tool.first_line(ElementTree.Element("failure")) == "failure"
