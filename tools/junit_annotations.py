"""GitHub annotations for the failed tests of a pytest JUnit XML report (TECH-05).

The CI jobs that run pytest write the report with ``--junitxml``. When the test step fails, this tool turns
the failed tests into workflow commands, ``::error title=<node ID>::<first line of the failure message>``.
GitHub shows them as annotations of the job's check run, which the public REST API serves without a login
(``GET /repos/<owner>/<repo>/check-runs/<id>/annotations``), unlike the job log. GitHub keeps at most 10 error
annotations per step, so the workflows run the tool twice, in two steps: once for at most 10 failed tests,
once with ``--summary`` for the counts.

Usage:
    python tools/junit_annotations.py pytest-junit.xml [--root .] [--limit 10]
    python tools/junit_annotations.py pytest-junit.xml --summary

The node ID is rebuilt from the report's class name (``tests.unit.test_x.TestY``) against the files below
--root. The tool always exits 0, because the job has already failed: a missing or unreadable report gives one
annotation that says so.
"""

from __future__ import annotations

import argparse
import io
import sys
import xml.etree.ElementTree as ElementTree
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

LIMIT = 10  # error annotations GitHub keeps per step
MESSAGE_LENGTH = 500
OUTCOMES = ("failure", "error")


@dataclass(frozen=True)
class Failed:
    node_id: str
    outcome: str  # "failure" (the test failed) or "error" (its setup, teardown or collection failed)
    message: str


@dataclass(frozen=True)
class Counts:
    tests: int
    failed: int
    errors: int
    skipped: int

    @property
    def passed(self) -> int:
        return self.tests - self.failed - self.errors - self.skipped


def escape_data(text: str) -> str:
    """The message of a workflow command."""
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def escape_property(text: str) -> str:
    """A property such as title=: also ':' and ',' (a node ID holds '::')."""
    return escape_data(text).replace(":", "%3A").replace(",", "%2C")


def node_id(classname: str, name: str, root: Path) -> str:
    """pytest's node ID: the longest leading part of the dotted class name that names a test file below
    ``root`` becomes its path, the rest are classes. A test outside such a file (a collection error has no
    class name) keeps the report's names."""
    parts = [part for part in classname.split(".") if part]
    for end in range(len(parts), 0, -1):
        path = "/".join(parts[:end]) + ".py"
        if (root / path).is_file():
            return "::".join([path, *parts[end:], name])
    return f"{classname}::{name}" if classname else name


def first_line(element: ElementTree.Element) -> str:
    """The first non-empty line of the failure's message attribute, else of its text."""
    for text in (element.get("message") or "", element.text or ""):
        for line in text.splitlines():
            if line.strip():
                line = line.strip()
                return line if len(line) <= MESSAGE_LENGTH else line[: MESSAGE_LENGTH - 1] + "…"
    return element.tag


def read(report: Path, root: Path) -> tuple[list[Failed], Counts]:
    """The failed test cases in report order, and the counts over all test cases."""
    tree = ElementTree.parse(report)  # written by pytest in the same job, not by a third party
    failed: list[Failed] = []
    tests = errors = failures = skipped = 0
    for case in tree.getroot().iter("testcase"):
        tests += 1
        outcome = next((child for child in case if child.tag in OUTCOMES), None)
        if outcome is not None:
            failures += outcome.tag == "failure"
            errors += outcome.tag == "error"
            identifier = node_id(case.get("classname", ""), case.get("name", ""), root)
            failed.append(Failed(identifier, outcome.tag, first_line(outcome)))
        elif case.find("skipped") is not None:
            skipped += 1
    return failed, Counts(tests, failures, errors, skipped)


def failure_commands(failed: Sequence[Failed], limit: int) -> list[str]:
    return [
        f"::error title={escape_property(item.node_id)}::{escape_data(item.message)}"
        for item in failed[:limit]
    ]


def summary_command(counts: Counts, shown: int, report: str) -> str:
    text = (
        f"{counts.failed} failed, {counts.errors} errors, {counts.passed} passed, {counts.skipped} skipped"
        f" ({counts.tests} tests); {shown} of {counts.failed + counts.errors} annotated, the full list is in"
        f" the job log and in {report}"
    )
    return f"::error title={escape_property('pytest summary')}::{escape_data(text)}"


def main(argv: Sequence[str] | None = None) -> int:
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("report", type=Path, help="JUnit XML file written by pytest --junitxml")
    parser.add_argument("--root", type=Path, default=Path(), help="folder the node IDs are relative to")
    parser.add_argument("--limit", type=int, default=LIMIT, help="failed tests to annotate (default 10)")
    parser.add_argument("--summary", action="store_true", help="print only the annotation with the counts")
    args = parser.parse_args(argv)
    try:
        failed, counts = read(args.report, args.root)
    except (OSError, ElementTree.ParseError) as exc:
        reason = f"no readable JUnit report {args.report}: {type(exc).__name__}: {exc}"
        print(f"::error title={escape_property('pytest summary')}::{escape_data(reason)}")
        return 0
    shown = min(len(failed), max(args.limit, 0))
    if args.summary:
        print(summary_command(counts, shown, args.report.as_posix()))
    else:
        for line in failure_commands(failed, shown):
            print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
