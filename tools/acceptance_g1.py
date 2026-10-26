"""G1 acceptance on the public test corpus (KONZEPT §6 G1, V-01, NG-F13, NG-F14, NG-N03, NG-N05, REP-00).

For every data set of the corpus (tools/corpus_spec.json: six data sets in five formats) the commands run as
real processes, the way a customer runs them (the ``neurogrid`` entry script next to this interpreter, the
environment without PYTHON* variables): ``scan``, ``check`` with core + bids + gxdsl008 (``--jobs 4``),
``report --lang zh,en --format html,pdf``, ``manifest`` and ``verify``, twice (run 1 with English console
messages, run 2 with Chinese ones); ``check --jobs 1`` once more on ds004148. Then, with this module's own
reading of the files (not the product's code that wrote them):

- exit codes: no exit 2; ``check`` exits with ``summary.exit_code`` (0 or 1), the others with 0;
- readability: no failed CORE-M01 finding; a data set with one does not count towards the G1 minimum, nor do
  its formats (NG-F01);
- console: strict UTF-8, the fixed sentence (A-08) as a line of stdout, stderr only translated library
  warnings, no traceback, no path of the data set, no home folder;
- files: exactly the expected files, no work folder or temporary file left (A-54);
- results.json, scan.json and manifest.json valid against the shipped schemas (Draft 2020-12 with formats),
  results.json canonical (NG-F14);
- every finding row of both HTML reports: the ten cells of report/render.py (FINDING_CELLS), every empty
  value one of the explained texts (EXPLAINED_EMPTY), the threshold with the origin of every parameter, at
  most MAX_ROWS_PER_RULE rows per rule with the exact remainder named (NG-F13, A-09, A-13, A-59);
- both HTML reports: the fixed sentence as visible text of the cover and of the appendix and as the meta
  description; its copy in the print CSS does not count (REP-07, A-08);
- every PDF: the runtime QA gate and an independent pypdf reading - only embedded Type0/CIDFontType2 subsets
  of the report fonts, the fixed sentence, running head and page counter on every page, A4 pages, no radical
  or compatibility code point, every section heading and rule ID, /Info exactly Title Creator Producer
  CreationDate ModDate with the neutral title and the reference date, no XMP, no /ID (REP-00, A-08, A-27);
- determinism: every file byte-identical over the two runs, ``--jobs 1`` equal to ``--jobs 4`` (NG-N03); the
  content checks are not repeated on a later run whose files are byte-identical to run 1 (its exit codes,
  console and file list are checked);
- privacy (NG-N05, A-51): no path of the corpus or the output folder, no home folder, user or host name, no
  identifying EDF/BDF header value, recording date or time, no raw age, no digest other than those
  results.json declares (finding keys, manifest, rule pack, configuration and evidence SHA-256: so no signal
  hash) in the console, results.json, scan.json, HTML, PDF text, PDF bytes (ASCII and UTF-16BE) and /Info.
  The manifest names the data set's own files by design (A-82); it is scanned for paths, user and host only;
- V-06: the loaded packs are exactly core, bids, gxdsl008; no rule, source or clause number of the norm
  (NORM, D-02);
- the corpus is unchanged afterwards (tools/corpus.py verify and no file added or touched).

The summary goes to <out>/summary.json (machine-readable: numbers, exit codes, durations, problem texts that
quote no value from the data) and <out>/summary.md (German table for the phase report, with the V-01
checklist). Raw data never enter the summary; the outputs of the runs stay below <out>. "Criteria met" means
the criteria of this run: the scaling test, the Linux offline run under strace, the clean room and the
coverage gates belong to the G1 criterion as well but have evidence of their own (OUTSIDE_THIS_RUN, named in
both summary files).

Usage:
    python tools/acceptance_g1.py --corpus .local/corpus --out .local/acceptance/g1
        [--datasets NAME ...] [--runs 2] [--jobs 4] [--as-of 2026-10-11] [--replace]

Exit code: 0 every criterion met, 1 a criterion not met, 2 tool error (corpus missing or changed, PDF browser
missing, output folder not usable).
"""

from __future__ import annotations

import argparse
import hashlib
import html as html_lib
import io
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser
from importlib import resources
from pathlib import Path
from typing import Any

import jsonschema
import pypdf
from pypdf.generic import ArrayObject, DictionaryObject

import neurogrid
from neurogrid.kernel import canonical
from neurogrid.kernel.findings import Finding, SourceStatus
from neurogrid.kernel.pdf import PLAYWRIGHT_VERSION, SHELL_REVISION, qa_gate
from neurogrid.model.results import Results
from neurogrid.report.output import REQUIRED_ONCE, pdf_expectation
from neurogrid.report.render import EXPLAINED_EMPTY, FINDING_CELLS, MAX_ROWS_PER_RULE
from neurogrid.report.texts import disclaimer, translator

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "tools" / "corpus_spec.json"
MATRIX = ROOT / "docs" / "umsetzung" / "ANFORDERUNGEN.md"
SUMMARY_SCHEMA = "neurogrid-acceptance-g1/1"
AS_OF = date(2026, 10, 11)
REPORT_LANGS = ("zh", "en")
CONSOLE_LANGS = ("en", "zh")  # run 1, run 2, ...
RULEPACKS = ("bids", "gxdsl008")  # core is always loaded (A-02)
BUILTIN_PACKS = ("core", "bids", "gxdsl008")
JOBS1_DATASET = "ds004148-1.0.1"
FORMATS = ("EDF", "BDF", "BrainVision", "EEGLAB", "FIF")  # the five formats of V-01
MIN_DATASETS, MIN_FORMATS = 3, 2  # PRD §19 G1: at least 3 data sets in at least 2 formats
# Parts of the G1 criterion (KONZEPT §6, P5 row) that this run does not check: each has evidence of its own.
OUTSIDE_THIS_RUN = (
    "Skalierungstest 1000 × 64 (tests/perf/test_report_scaling.py)",
    "Linux-Lauf ohne Netz + strace ohne connect (offline.yml)",
    "Bündel-Installation in debian:12-slim --network none ohne vorinstalliertes Python (offline.yml)",
    "Abdeckung Kern ≥ 90 %, Prüfer ≥ 80 % (tools/coverage_gates.py)",
)
COMMANDS = ("scan", "check", "report", "manifest", "verify")
PRODUCT_FILES = (
    "results.json",
    "scan.json",
    "manifest.json",
    "report.zh.html",
    "report.zh.pdf",
    "report.en.html",
    "report.en.pdf",
)
SCHEMAS = {"results.json": "results", "scan.json": "scan", "manifest.json": "manifest"}
READ_RULES = ("CORE-M01-01", "CORE-M01-02", "CORE-M01-03", "CORE-M01-04")  # readability (NG-F01)
A4 = (595.28, 841.89)  # points
A4_TOLERANCE = 1.5
REPORT_FONT = re.compile(r"^/?[A-Z]{6}\+NotoSansSC-(Regular|Bold)$")
RADICALS = ((0x2E80, 0x2FDF), (0xF900, 0xFAFF), (0x2F800, 0x2FA1F))
DRIVE_PATH = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]")
HEX_RUN = re.compile(r"[0-9a-fA-F]{16,}")
FONT_URI = re.compile(r"data:font/[A-Za-z0-9.+-]*;base64,[A-Za-z0-9+/=]*")
NORM = "YY/T 2029"  # the norm of V-06 and D-02; the one place this tool names it (reviewed mention)
YYT_CLAUSE = re.compile(r"(?i)(?:YY\s*/?\s*T\s*2029|yyt\s*2029)[^\n]{0,40}?\b\d+(?:\.\d+)+")
YYT_RULE = re.compile(r"(?i)^yyt")
AGE_KEY = re.compile(r"(?i)(?:.*_)?ages?(?:_.*)?")
AGE_GROUP = re.compile(r"\d+-\d+|90\+")
MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
DASH = "–"


class ToolError(Exception):
    """A condition the acceptance cannot run under (exit 2)."""


# --- running the commands ----------------------------------------------------------------------------------


@dataclass
class CommandRun:
    """One finished command: exit code, the raw console streams and the wall time."""

    name: str
    code: int
    stdout: bytes
    stderr: bytes
    seconds: float


def neurogrid_executable() -> Path:
    """The ``neurogrid`` entry script of this environment (Scripts/neurogrid.exe or bin/neurogrid)."""
    name = "neurogrid.exe" if os.name == "nt" else "neurogrid"
    path = Path(sys.executable).parent / name
    if not path.is_file():
        raise ToolError(f"the neurogrid entry script is missing next to the interpreter ({name})")
    return path


def child_environment(lang: str, environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """The customer's environment: no PYTHON* variables, console messages in ``lang``."""
    base = os.environ if environ is None else environ
    env = {key: value for key, value in base.items() if not key.upper().startswith("PYTHON")}
    env["NEUROGRID_LANG"] = lang
    return env


def command_arguments(name: str, dataset: Path, folder: Path, *, jobs: int, as_of: date) -> list[str]:
    """The command line of one command; every output goes into ``folder`` (never into the data set)."""
    results = folder / "results.json"
    if name == "scan":
        return ["scan", str(dataset), "--out", str(folder / "scan.json")]
    if name == "check":
        packs = [arg for pack in RULEPACKS for arg in ("--rulepack", pack)]
        return ["check", str(dataset), *packs, "--as-of", as_of.isoformat(), "--jobs", str(jobs)] + [
            "--out",
            str(results),
        ]
    if name == "report":
        langs = ",".join(REPORT_LANGS)
        return ["report", str(results), "--lang", langs, "--format", "html,pdf", "--out", str(folder)]
    if name == "manifest":
        return ["manifest", str(dataset), "--out", str(folder / "manifest.json")]
    if name == "verify":
        return ["verify", str(dataset), "--manifest", str(folder / "manifest.json")]
    raise ValueError(name)


def run_command(executable: Path, arguments: Sequence[str], env: Mapping[str, str], cwd: Path) -> CommandRun:
    start = time.perf_counter()
    done = subprocess.run(
        [str(executable), *arguments], cwd=cwd, env=dict(env), capture_output=True, check=False
    )
    return CommandRun(
        name=arguments[0],
        code=done.returncode,
        stdout=done.stdout,
        stderr=done.stderr,
        seconds=round(time.perf_counter() - start, 1),
    )


def run_dataset(
    dataset: Path,
    folder: Path,
    *,
    lang: str,
    jobs: int = 4,
    as_of: date = AS_OF,
    commands: Sequence[str] = COMMANDS,
    executable: Path | None = None,
) -> dict[str, CommandRun]:
    """Run ``commands`` on ``dataset`` with their outputs in ``folder`` and the console in ``lang``; the
    console streams are kept next to it (``folder``.console/<command>.stdout|stderr). A ``check`` that ends
    with exit 2 leaves nothing to report on: the later commands that need results.json are not run."""
    exe = executable or neurogrid_executable()
    folder.mkdir(parents=True, exist_ok=True)
    console = folder.parent / f"{folder.name}.console"
    console.mkdir(exist_ok=True)
    env = child_environment(lang)
    runs: dict[str, CommandRun] = {}
    for name in commands:
        if name == "report" and runs.get("check", CommandRun("check", 0, b"", b"", 0.0)).code == 2:
            continue
        if name == "verify" and runs.get("manifest", CommandRun("manifest", 0, b"", b"", 0.0)).code == 2:
            continue
        arguments = command_arguments(name, dataset, folder, jobs=jobs, as_of=as_of)
        run = run_command(exe, arguments, env, folder.parent)
        (console / f"{name}.stdout").write_bytes(run.stdout)
        (console / f"{name}.stderr").write_bytes(run.stderr)
        runs[name] = run
    return runs


# --- checks (each returns problem texts; empty = passed) ---------------------------------------------------


def check_exit_codes(runs: Mapping[str, CommandRun], results: Results | None) -> list[str]:
    """NG-F14: no exit 2 for data set data; ``check`` exits with summary.exit_code (0 or 1), the other
    commands with 0 (verify compares with the manifest written just before)."""
    problems = []
    for name, run in runs.items():
        if run.code == 2:
            problems.append(f"{name}: exit 2 (tool error)")
        elif name == "check":
            if run.code not in (0, 1):
                problems.append(f"check: exit {run.code} is not 0 or 1")
            elif results is not None and run.code != results.summary.exit_code:
                problems.append(f"check: exit {run.code} != summary.exit_code {results.summary.exit_code}")
        elif run.code != 0:
            problems.append(f"{name}: exit {run.code}, expected 0")
    return problems


def _library_warning(lang: str) -> re.Pattern[str]:
    """The one stderr line NeuroGrid prints at exit 0/1: a library warning reduced to its category (A-07)."""
    marker = "\x00"
    template = translator(lang).t("cli.warning.library", type=marker)
    return re.compile(re.escape(template).replace(re.escape(marker), r"[A-Za-z_][A-Za-z0-9_.]*"))


def _decode(data: bytes, stream: str, problems: list[str]) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        problems.append(f"{stream} is not valid UTF-8")
        return data.decode("utf-8", "replace")


def check_console(
    stdout: bytes, stderr: bytes, lang: str, code: int, *, allowed_paths: Sequence[Path] = ()
) -> list[str]:
    """Strict UTF-8, the fixed sentence of ``lang`` as a line of stdout (A-08), at exit 0/1 only translated
    library warnings on stderr; never a traceback, a source location, a drive path or the home folder.
    ``allowed_paths`` are output paths the operator chose (--out): the console names them (A-82), so they
    are taken out before the path tests."""
    problems: list[str] = []
    out = _decode(stdout, "stdout", problems)
    err = _decode(stderr, "stderr", problems)
    if code in (0, 1):
        if disclaimer(lang) not in [line.strip() for line in out.splitlines()]:
            problems.append(f"stdout lacks the fixed sentence ({lang})")
        warning = _library_warning(lang)
        if any(line.strip() and not warning.fullmatch(line.strip()) for line in err.splitlines()):
            problems.append("stderr holds a line that is no translated NeuroGrid message")
    home = str(Path.home())
    for stream, text in (("stdout", out), ("stderr", err)):
        for path in allowed_paths:
            text = _remove_forms(text, path)
        if "Traceback" in text:
            problems.append(f"{stream} holds a traceback")
        if 'File "' in text:
            problems.append(f"{stream} holds a source location")
        if DRIVE_PATH.search(text):
            problems.append(f"{stream} holds a drive path")
        if len(home) > 1 and home.lower() in text.lower():
            problems.append(f"{stream} holds the home folder")
    return problems


def check_files(folder: Path, expected: Iterable[str] = PRODUCT_FILES) -> list[str]:
    """Exactly the expected files; no work folder (run-*) or temporary file left behind (A-54)."""
    wanted = set(expected)
    present = {entry.name: entry for entry in folder.iterdir()} if folder.is_dir() else {}
    problems = [f"missing {name}" for name in sorted(wanted - set(present))]
    for name in sorted(set(present) - wanted):
        kind = "folder" if present[name].is_dir() else "file"
        problems.append(f"unexpected {kind} {name}")
    return problems


@dataclass
class SchemaCheck:
    problems: list[str]
    results: Results | None = None


def _schema(name: str) -> dict[str, Any]:
    text = resources.files("neurogrid").joinpath("schemas", f"{name}.schema.json").read_text(encoding="utf-8")
    loaded: dict[str, Any] = json.loads(text)
    return loaded


def validate_schema_file(path: Path, schema: str) -> list[str]:
    """``path`` against the schema the wheel ships (src/neurogrid/schemas), Draft 2020-12 with formats."""
    try:
        instance = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"{path.name}: not readable as UTF-8 JSON ({type(exc).__name__})"]
    validator = jsonschema.Draft202012Validator(
        _schema(schema), format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER
    )
    errors = sorted(validator.iter_errors(instance), key=lambda error: list(error.absolute_path))
    return [f"{path.name}: schema error at /{'/'.join(map(str, e.absolute_path))}" for e in errors[:20]]


def validate_results_file(path: Path) -> SchemaCheck:
    """NG-F14: results.json is valid against results.schema.json, loads as Results and is canonical
    (canonical.dumps of the loaded results gives the file's bytes)."""
    problems = validate_schema_file(path, "results")
    try:
        data = path.read_bytes()
        results = Results.model_validate_json(data)
    except (OSError, ValueError) as exc:
        return SchemaCheck([*problems, f"results.json does not load ({type(exc).__name__})"])
    if canonical.dumps(results) != data:
        problems.append("results.json is not canonical")
    return SchemaCheck(problems, results)


class _Rows(HTMLParser):
    """Every <tr data-key=...> with the text of its <td class="c-..."> cells (entities resolved)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[tuple[str, dict[str, str]]] = []
        self.repeated: list[str] = []
        self._row: dict[str, str] | None = None
        self._key = ""
        self._cell: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "tr" and values.get("data-key"):
            self._row, self._key = {}, values.get("data-key") or ""
        elif tag == "td" and self._row is not None:
            classes = (values.get("class") or "").split()
            self._cell = next((name[2:] for name in classes if name.startswith("c-")), None)
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._row is not None and self._cell is not None:
            if self._cell in self._row:
                self.repeated.append(self._key)
            self._row[self._cell] = "".join(self._text)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append((self._key, self._row))
            self._row = None


def finding_rows(document: str) -> tuple[list[tuple[str, dict[str, str]]], list[str]]:
    """(data-key, {cell class: text}) of every finding row, and the keys of rows with a repeated cell."""
    parser = _Rows()
    parser.feed(document)
    parser.close()
    return parser.rows, parser.repeated


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(_has_value(item) for item in value)
    if isinstance(value, dict):
        return any(_has_value(item) for item in value.values())
    return True


def _plain(text: str) -> bool:
    """Text the report shows as it is (printable ASCII): only then is a cell compared with it literally."""
    return all(" " <= char <= "~" for char in text)


def _row_sections(findings: Iterable[Finding]) -> Counter[tuple[bool, str, str]]:
    """Findings per table of the findings section: placeholder or by severity, then by rule (A-59)."""
    counts: Counter[tuple[bool, str, str]] = Counter()
    for finding in findings:
        placeholder = finding.source_status is SourceStatus.PLACEHOLDER
        counts[(placeholder, "" if placeholder else finding.severity.value, finding.rule_id)] += 1
    return counts


def _row_problems(
    key: str, row: Mapping[str, str], finding: Finding, lang: str, explained: set[str]
) -> list[str]:
    tr = translator(lang).t
    problems: list[str] = []
    missing = [cell for cell in FINDING_CELLS if cell not in row]
    if missing:
        problems.append(f"row {key}: cells missing: {', '.join(missing)}")
    for cell in FINDING_CELLS:
        value = row.get(cell, "").strip()
        if not value:
            problems.append(f"row {key}: cell {cell} is empty")
        elif value.startswith(DASH) and value not in explained:
            problems.append(f"row {key}: cell {cell} is a dash without an explained reason")
    if not missing:
        problems.extend(_cell_problems(key, row, finding, tr, explained))
    return problems


def _cell_problems(key: str, row: Mapping[str, str], f: Finding, tr: Any, explained: set[str]) -> list[str]:
    """The contents of the cells against the finding (NG-F13: rule, clause, measured value, threshold, file,
    time range; A-09 empty values, A-10 time ranges, A-13 parameters with origin)."""
    problems = []
    if row["rule"].strip() != f.rule_id:
        problems.append(f"row {key}: rule cell differs from the finding's rule")
    if f.source_status is SourceStatus.PLACEHOLDER:
        status = tr("report.value.placeholder_status")
    else:
        status = tr(f"status.{f.status.value}")
    if row["status"].strip() != status:
        problems.append(f"row {key}: status cell differs from the finding's status")
    measured = row["measured"].strip()
    if _has_value(f.measured_value) == measured.startswith(DASH):
        problems.append(f"row {key}: measured cell does not match the measured value")
    threshold = row["threshold"]
    if f.params:
        for name in sorted(f.params):
            origin = tr(f"report.text.origin_{f.params[name].origin}")
            if f"{name} = " not in threshold or f"({origin})" not in threshold:
                problems.append(f"row {key}: threshold cell lacks parameter {name} with its origin")
    elif f.threshold is None and threshold.strip() != tr("report.value.no_threshold"):
        problems.append(f"row {key}: threshold cell does not say that the rule has no threshold")
    elif f.threshold is not None and threshold.strip().startswith(DASH):
        problems.append(f"row {key}: threshold cell hides the threshold")
    file_cell = row["file"].strip()
    if f.file is None:
        if file_cell != tr("report.value.dataset_level"):
            problems.append(f"row {key}: file cell does not say dataset level")
    elif _plain(f.file) and file_cell != f.file:
        problems.append(f"row {key}: file cell differs from the finding's file")
    channel = row["channel"].strip()
    if f.channel is None:
        if channel != tr("report.value.no_channel"):
            problems.append(f"row {key}: channel cell does not say not channel-specific")
    elif _plain(f.channel) and channel != f.channel:
        problems.append(f"row {key}: channel cell differs from the finding's channel")
    time_cell = row["time"].strip()
    if f.time_ranges:
        first = f.time_ranges[0]
        if not time_cell.startswith(f"{first.start_s:.3f}{DASH}{first.end_s:.3f} s"):
            problems.append(f"row {key}: time cell does not start with the first time range")
    elif f.file is None:
        if time_cell != tr("report.value.time_dataset"):
            problems.append(f"row {key}: time cell does not say dataset level")
    elif time_cell not in (tr("report.value.whole_recording"), tr("report.value.whole_file")):
        problems.append(f"row {key}: time cell names neither a range nor the whole recording or file")
    return problems


@dataclass
class RowCheck:
    problems: list[str]
    rows: int


def check_finding_rows(document: str, results: Results, lang: str) -> RowCheck:
    """NG-F13 / A-59 on one HTML report: one row per shown finding with all ten cells, no bare '–', and per
    rule table min(total, MAX_ROWS_PER_RULE) rows plus the sentence naming the exact remainder."""
    tr = translator(lang).t
    explained = {tr(key) for key in EXPLAINED_EMPTY}
    by_key = {finding.key: finding for finding in results.findings}
    rows, repeated = finding_rows(document)
    problems = [f"row {key}: a cell class appears twice" for key in sorted(set(repeated))]
    seen: Counter[str] = Counter()
    shown: Counter[tuple[bool, str, str]] = Counter()
    for key, row in rows:
        seen[key] += 1
        finding = by_key.get(key)
        if finding is None:
            problems.append(f"row {key}: no finding with this key in results.json")
            continue
        placeholder = finding.source_status is SourceStatus.PLACEHOLDER
        shown[(placeholder, "" if placeholder else finding.severity.value, finding.rule_id)] += 1
        problems.extend(_row_problems(key, row, finding, lang, explained))
    problems.extend(f"row {key}: shown {count} times" for key, count in sorted(seen.items()) if count > 1)
    text = html_lib.unescape(document)
    for section, total in sorted(_row_sections(results.findings).items()):
        rule = section[2]
        expected = min(total, MAX_ROWS_PER_RULE)
        if shown[section] != expected:
            problems.append(f"{rule}: {shown[section]} rows shown, expected {expected} of {total}")
        if total > expected and tr("report.text.rule_more", count=total - expected, rule=rule) not in text:
            problems.append(
                f"{rule}: the sentence naming the remaining {total - expected} findings is missing"
            )
    return RowCheck(problems, len(rows))


class _Sentence(HTMLParser):
    """The visible text of every <section id=...> (style, script and head left out) and the content of
    <meta name="description">."""

    SKIPPED = ("style", "script", "head")

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.sections: dict[str, list[str]] = defaultdict(list)
        self.description: str | None = None
        self._section: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "meta" and (values.get("name") or "").lower() == "description":
            self.description = values.get("content") or ""
        if tag in self.SKIPPED:
            self._skip += 1
        elif tag == "section":
            self._section.append(values.get("id") or "")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "meta":
            self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIPPED and self._skip:
            self._skip -= 1
        elif tag == "section" and self._section:
            self._section.pop()

    def handle_data(self, data: str) -> None:
        if not self._skip and self._section:
            self.sections[self._section[-1]].append(data)


HTML_SENTENCE_PLACES = (("cover", "on the cover"), ("appendix", "in the appendix"))


def check_html(document: str, lang: str) -> list[str]:
    """REP-07/A-08 on one HTML report: the fixed sentence of ``lang`` is visible text of the cover and of the
    appendix and is the meta description. Its copy in the print CSS (@page margin boxes) does not count:
    the HTML read on screen has to carry it itself."""
    parser = _Sentence()
    parser.feed(document)
    parser.close()
    sentence = _squeeze(disclaimer(lang))
    problems = [
        f"the fixed sentence is missing {where}"
        for section, where in HTML_SENTENCE_PLACES
        if sentence not in _squeeze("".join(parser.sections.get(section, [])))
    ]
    if parser.description is None or _squeeze(parser.description) != sentence:
        problems.append("the meta description is not the fixed sentence")
    return problems


# --- PDF ---------------------------------------------------------------------------------------------------


def _object(value: Any) -> Any:
    return value.get_object() if hasattr(value, "get_object") else value


def _fonts(resources_: Any, seen: set[int]) -> Iterator[DictionaryObject]:
    """Fonts of a resource dictionary and, recursively, of its form XObjects (own walk, not the QA gate's)."""
    resources_ = _object(resources_)
    if not isinstance(resources_, DictionaryObject) or id(resources_) in seen:
        return
    seen.add(id(resources_))
    fonts = _object(resources_.get("/Font"))
    if isinstance(fonts, DictionaryObject):
        for ref in fonts.values():
            font = _object(ref)
            if isinstance(font, DictionaryObject):
                yield font
    xobjects = _object(resources_.get("/XObject"))
    if isinstance(xobjects, DictionaryObject):
        for ref in xobjects.values():
            xobject = _object(ref)
            if isinstance(xobject, DictionaryObject) and xobject.get("/Subtype") == "/Form":
                yield from _fonts(xobject.get("/Resources"), seen)


def _font_problem(font: DictionaryObject) -> str | None:
    subtype = _object(font.get("/Subtype"))
    if subtype != "/Type0":
        return f"font of subtype {subtype} (only embedded Type0 subsets are allowed)"
    if not REPORT_FONT.match(str(_object(font.get("/BaseFont")))):
        return "a font that is no subset of the report fonts"
    if "/ToUnicode" not in font:
        return "a font without ToUnicode"
    descendants = _object(font.get("/DescendantFonts"))
    descendant = _object(descendants[0]) if isinstance(descendants, ArrayObject) and descendants else None
    if not isinstance(descendant, DictionaryObject) or _object(descendant.get("/Subtype")) != "/CIDFontType2":
        return "a Type0 font without a CIDFontType2 descendant"
    descriptor = _object(descendant.get("/FontDescriptor"))
    files = sorted(k for k in descriptor if str(k).startswith("/FontFile")) if descriptor is not None else []
    if files != ["/FontFile2"]:
        return "a font that is not embedded as FontFile2"
    return None


def _squeeze(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _page_counter(number: int, total: int) -> re.Pattern[str]:
    """'x / y' in the squeezed page text with up to three characters of words around the slash."""
    return re.compile(rf"(?<!\d){number}\D{{0,3}}/\D{{0,3}}(?<!\d){total}(?!\d)")


def pdf_date(as_of: date) -> str:
    return f"D:{as_of:%Y%m%d}000000+00'00'"


@dataclass
class PdfCheck:
    problems: list[str]
    pages: int = 0
    text: str = ""
    info: dict[str, str] = field(default_factory=dict)


def check_pdf(data: bytes, lang: str, results: Results, document: str) -> PdfCheck:
    """The PDF of ``document`` (the delivered HTML): the runtime QA gate and an independent reading."""
    tr = translator(lang).t
    problems = [f"QA gate: {code}" for code in qa_gate(data, pdf_expectation(results, lang, document))]
    try:
        reader = pypdf.PdfReader(io.BytesIO(data))
        pages = list(reader.pages)
        texts = [page.extract_text() or "" for page in pages]
        info = {str(k): str(v) for k, v in (reader.metadata or {}).items()}
        root = _object(reader.trailer.get("/Root"))
        trailer_keys = set(reader.trailer.keys())
    except Exception as exc:  # any reading failure is a defect of the PDF
        return PdfCheck([*problems, f"not readable ({type(exc).__name__})"])
    if not pages:
        return PdfCheck([*problems, "no pages"])
    seen: set[int] = set()
    font_problems: set[str] = set()
    for page in pages:
        for font in _fonts(page.get("/Resources"), seen):
            problem = _font_problem(font)
            if problem is not None:
                font_problems.add(problem)
    problems.extend(sorted(font_problems))
    if not seen:
        problems.append("no font resources")
    squeezed = [_squeeze(text) for text in texts]
    sentence = _squeeze(disclaimer(lang))
    head = _squeeze(tr("report.page.running_head", as_of=results.config.as_of.isoformat()))
    for number, (page, text) in enumerate(zip(pages, squeezed, strict=True), start=1):
        if sentence not in text:
            problems.append(f"page {number}: the fixed sentence is missing")
        if head not in text:
            problems.append(f"page {number}: the running head is missing")
        if not _page_counter(number, len(pages)).search(text):
            problems.append(f"page {number}: the page counter is missing")
        width, height = sorted((float(page.mediabox.width), float(page.mediabox.height)))
        if abs(width - A4[0]) > A4_TOLERANCE or abs(height - A4[1]) > A4_TOLERANCE:
            problems.append(f"page {number}: not A4")
    if float(pages[0].mediabox.width) > float(pages[0].mediabox.height):
        problems.append("the cover page is not portrait")
    if len(pages) > 1 and float(pages[-1].mediabox.width) < float(pages[-1].mediabox.height):
        problems.append("the appendix page is not landscape")
    whole = "".join(squeezed)
    if any(low <= ord(char) <= high for text in texts for char in text for low, high in RADICALS):
        problems.append("radical or compatibility code point in the text")
    for key in REQUIRED_ONCE:
        if _squeeze(tr(key)) not in whole:
            problems.append(f"{key} not found")
    rules = sorted({finding.rule_id for finding in results.findings})
    absent = [rule for rule in rules if rule not in whole]
    if absent:
        problems.append(f"rule IDs not in the text: {', '.join(absent)}")
    if sorted(info) != ["/CreationDate", "/Creator", "/ModDate", "/Producer", "/Title"]:
        problems.append("/Info keys are not exactly Title Creator Producer CreationDate ModDate")
    if info.get("/Title") != tr("report.title"):
        problems.append("/Title is not the neutral report title")
    stamp = pdf_date(results.config.as_of)
    if info.get("/CreationDate") != stamp or info.get("/ModDate") != stamp:
        problems.append("/CreationDate or /ModDate is not the reference date")
    if isinstance(root, DictionaryObject) and "/Metadata" in root:
        problems.append("XMP metadata present")
    if "/ID" in trailer_keys:
        problems.append("trailer holds /ID")
    return PdfCheck(problems, len(pages), "\n".join(texts), info)


# --- privacy -----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Forbidden:
    """A value that must not leave the process. ``kind``: path (any spelling, case-insensitive), word (whole
    word, case-insensitive) or literal (exact). ``label`` names it in problems; the value is never shown."""

    label: str
    value: str
    kind: str


def _path_forms(path: Path) -> set[str]:
    """``path`` absolute, resolved (through links and junctions), with the home folder written '~' as the
    console does, each with both separators and JSON-escaped."""
    home = str(Path.home())
    forms: set[str] = set()
    for base in {str(path.absolute()), str(path.resolve())}:
        candidates = {base}
        if len(home) > 1 and base.lower().startswith(home.lower()):
            candidates.add("~" + base[len(home) :])
        for item in candidates:
            for spelled in (item, item.replace("\\", "/"), item.replace("/", "\\")):
                forms.add(spelled)
                forms.add(spelled.replace("\\", "\\\\"))
    return {form for form in forms if len(form) > 2}


def _remove_forms(text: str, path: Path) -> str:
    for form in sorted(_path_forms(path), key=len, reverse=True):
        text = re.sub(re.escape(form), "<out>", text, flags=re.IGNORECASE)
    return text


def _informative(value: str) -> bool:
    """A header value worth searching: three or more characters with a letter or digit other than the EDF+
    placeholder X."""
    return len(value) >= 3 and any(char.isalnum() and char not in "Xx" for char in value)


def _year(two: str) -> int:
    """EDF start date year: 85-99 are 1985-1999, else 2000-2084 (EDF specification)."""
    number = int(two)
    return 1900 + number if number >= 85 else 2000 + number


def header_values(path: Path, as_of: date = AS_OF) -> list[Forbidden]:
    """Identifying values of one EDF/BDF header: the patient and recording fields (whole and, in EDF+, every
    informative subfield), the start date in the forms dd.mm.yy, yyyy-mm-dd and dd-MMM-yyyy and the start
    time in the forms hh.mm.ss and hh:mm:ss. A start date equal to the reference date is not searched (the
    report shows the reference date). A subfield is searched as a whole word: a short name part such as
    'San' is no leak inside the font family 'NG Sans'. An EDF+ recording field whose subfields are all
    placeholders ('Startdate X X X X') and the start time 00.00.00 hold nothing to search."""
    with path.open("rb") as stream:
        head = stream.read(184)
    if len(head) < 184:
        return []
    found: list[Forbidden] = []
    patient = head[8:88].decode("latin-1").strip()
    recording = head[88:168].decode("latin-1").strip()
    plus = recording.startswith("Startdate")  # EDF+: subfields separated by spaces
    subfields = [*patient.split(" "), *recording.split(" ")[1:]] if plus else []
    whole = (patient, recording if not plus or any(map(_informative, recording.split(" ")[1:])) else "")
    for value in whole:
        if _informative(value):
            found.append(Forbidden("EDF/BDF header value", value, "literal"))
    for value in subfields:
        if _informative(value):
            found.append(Forbidden("EDF/BDF header subfield", value, "word"))
    start = head[168:176].decode("latin-1")
    if re.fullmatch(r"\d\d\.\d\d\.\d\d", start):
        day, month, year = start.split(".")
        full = _year(year)
        if 1 <= int(month) <= 12 and f"{full}-{month}-{day}" != as_of.isoformat():
            for form in (start, f"{full}-{month}-{day}", f"{day}-{MONTHS[int(month) - 1]}-{full}"):
                found.append(Forbidden("recording date", form, "literal"))
    clock = head[176:184].decode("latin-1")
    if re.fullmatch(r"\d\d\.\d\d\.\d\d", clock) and clock != "00.00.00":
        found.append(Forbidden("recording time", clock, "literal"))
        found.append(Forbidden("recording time", clock.replace(".", ":"), "literal"))
    return found


def raw_ages(dataset: Path) -> list[str]:
    """The raw values of the age column(s) of participants.tsv (n/a and empty cells left out)."""
    table = dataset / "participants.tsv"
    if not table.is_file():
        return []
    lines = table.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    if not lines:
        return []
    header = [name.strip() for name in lines[0].split("\t")]
    columns = [i for i, name in enumerate(header) if AGE_KEY.fullmatch(name.lower())]
    values = []
    for line in lines[1:]:
        cells = line.split("\t")
        for i in columns:
            if i < len(cells) and cells[i].strip() and cells[i].strip().lower() != "n/a":
                values.append(cells[i].strip())
    return values


def forbidden_values(dataset: Path, out: Path, *, as_of: date = AS_OF) -> list[Forbidden]:
    """Everything that must not appear in the outputs of ``dataset`` (A-51, NG-N05)."""
    found = [Forbidden("data set path", form, "path") for form in _path_forms(dataset)]
    found += [Forbidden("output path", form, "path") for form in _path_forms(out)]
    found += [Forbidden("home folder", form, "path") for form in _path_forms(Path.home())]
    for label, names in (
        ("user name", ("USERNAME", "USER", "LOGNAME")),
        ("host name", ("COMPUTERNAME", "HOSTNAME")),
    ):
        values = {os.environ.get(name, "") for name in names}
        if label == "host name":
            values.add(socket.gethostname())
        found += [Forbidden(label, value, "word") for value in sorted(values) if len(value) >= 3]
    for path in sorted(dataset.rglob("*")):
        if path.suffix.lower() in (".edf", ".bdf") and path.is_file():
            found += header_values(path, as_of)
    for age in raw_ages(dataset):
        if not age.isdigit():  # a plain integer is no searchable token (counts); see age_problems
            found.append(Forbidden("raw age", age, "number"))
    return sorted(set(found), key=lambda item: (item.label, item.value))


def _matches(text: str, item: Forbidden) -> bool:
    if item.kind == "path":
        return item.value.lower() in text.lower()
    if item.kind == "word":
        return re.search(rf"(?i)(?<![A-Za-z0-9]){re.escape(item.value)}(?![A-Za-z0-9])", text) is not None
    if item.kind == "number":
        return re.search(rf"(?<![\d.,]){re.escape(item.value)}(?![\d.,])", text) is not None
    return item.value in text


def age_problems(data: Any, where: str = "") -> list[str]:
    """Raw ages never leave the process (A-21, A-51): every value under a key that names an age is a count,
    a mapping of 10-year groups to counts, or None."""
    problems: list[str] = []
    if isinstance(data, dict):
        for key, value in data.items():
            path = f"{where}/{key}"
            if isinstance(key, str) and AGE_KEY.fullmatch(key):
                if isinstance(value, dict):
                    if not all(AGE_GROUP.fullmatch(str(k)) and type(v) is int for k, v in value.items()):
                        problems.append(f"{path} holds more than 10-year groups with counts")
                elif value is not None and type(value) is not int:
                    problems.append(f"{path} holds a value that is no count")
            problems.extend(age_problems(value, path))
    elif isinstance(data, list):
        for index, item in enumerate(data):
            problems.extend(age_problems(item, f"{where}/{index}"))
    return problems


def declared_digests(results: Results) -> set[str]:
    """The SHA-256 values results.json declares: manifest, rule packs, configuration, evidence."""
    values = {results.dataset.manifest_hash, results.config.canonical_sha256, results.config.evidence_sha256}
    values |= {pack.sha256 for pack in results.rulepacks}
    if results.manifest is not None:
        values.add(results.manifest.sha256)
    for record in results.evidence or []:
        values |= {record.sha256, record.sha256_recorded}
    return {value.lower() for value in values if value}


def unexpected_digests(text: str, keys: set[str], digests: set[str]) -> int:
    """Hex runs of 16 or more characters that are neither a finding key nor part of a declared SHA-256 (a
    signal hash would be one). The embedded fonts (data:font URIs) are left out."""
    count = 0
    for match in HEX_RUN.finditer(FONT_URI.sub(" ", text)):
        run = match.group(0).lower()
        if run not in keys and not any(run in digest for digest in digests):
            count += 1
    return count


MANIFEST_LABELS = ("data set path", "output path", "home folder", "user name", "host name")


@dataclass
class Output:
    """One output to scan: its name, the text, for a PDF also the raw bytes and /Info."""

    name: str
    text: str
    raw: bytes = b""
    info: dict[str, str] = field(default_factory=dict)
    manifest: bool = False


def console_output(name: str, run: CommandRun, out: Path) -> Output:
    """Both console streams of one command, with the operator's own --out folder (named on the console by
    design, A-82) taken out, so the rest is searched for everything else."""
    text = "\n".join(data.decode("utf-8", "replace") for data in (run.stdout, run.stderr))
    return Output(f"{name} console", _remove_forms(text, out))


def check_privacy(
    outputs: Sequence[Output],
    forbidden: Sequence[Forbidden],
    results: Results | None,
    *,
    extra: Iterable[str] = (),
) -> list[str]:
    """NG-N05/A-51 over every output. Problems name the output and the kind of value, never the value. The
    manifest names the data set's own files by design (A-82): it is searched for paths, user and host only.
    Console text is passed with the operator's own --out folder taken out (A-82, see console_output)."""
    problems: list[str] = []
    keys = {finding.key for finding in results.findings} if results is not None else set()
    digests = (declared_digests(results) if results is not None else set()) | {d.lower() for d in extra}
    for output in outputs:
        for item in forbidden:
            if output.manifest and item.label not in MANIFEST_LABELS:
                continue
            texts = [output.text, *output.info.values()]
            hit = any(_matches(text, item) for text in texts)
            if not hit and output.raw and item.kind != "word":
                for encoding in ("latin-1", "utf-16-be"):
                    try:
                        needle = item.value.encode(encoding)
                    except UnicodeEncodeError:
                        continue
                    if needle in output.raw:
                        hit = True
                        break
            if hit:
                problems.append(f"{output.name}: contains a {item.label}")
        if not output.manifest:
            count = unexpected_digests(output.text, keys, digests)
            if count:
                problems.append(f"{output.name}: {count} hex digest(s) results.json does not declare")
    return sorted(set(problems))


# --- V-06 --------------------------------------------------------------------------------------------------


def v06_problems(results: Results, documents: Iterable[str]) -> list[str]:
    """V-06: the loaded packs are exactly core, bids, gxdsl008; no rule, source or clause of NORM."""
    problems = []
    names = [pack.name for pack in results.rulepacks]
    if sorted(names) != sorted(BUILTIN_PACKS):
        problems.append(f"loaded packs are {', '.join(names)}, not core, bids, gxdsl008")
    if any(YYT_RULE.match(rule.id) for rule in results.rules):
        problems.append(f"a {NORM} rule is loaded")
    if any(YYT_CLAUSE.search(f"{pack.name} {pack.source}") for pack in results.rulepacks):
        problems.append(f"a rule pack cites a {NORM} clause")
    if any(YYT_CLAUSE.search(text) for text in documents):
        problems.append(f"an output cites a {NORM} clause")
    return problems


# --- comparing runs and the corpus -------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def compare_runs(first: Path, second: Path, names: Iterable[str] = PRODUCT_FILES) -> dict[str, bool]:
    """NG-N03: per file whether both runs wrote the same bytes (False when one is missing)."""
    same = {}
    for name in names:
        a, b = first / name, second / name
        same[name] = a.is_file() and b.is_file() and sha256_file(a) == sha256_file(b)
    return same


def tree_state(folder: Path) -> dict[str, tuple[int, int]]:
    """Relative path -> (size, modification time in ns) of every file below ``folder``."""
    state = {}
    for path in sorted(folder.rglob("*")):
        if path.is_file():
            stat = path.stat()
            state[path.relative_to(folder).as_posix()] = (stat.st_size, stat.st_mtime_ns)
    return state


# --- V-01 checklist ----------------------------------------------------------------------------------------


def matrix_status(text: str) -> dict[str, str]:
    """ID -> status of every row of the requirements matrix (the column named 'Status' of its table)."""
    statuses: dict[str, str] = {}
    column: int | None = None
    for line in text.splitlines():
        if not line.startswith("|"):
            column = None
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells and cells[0] == "ID":
            column = cells.index("Status") if "Status" in cells else None
        elif column is not None and len(cells) > column and not set(cells[0]) <= {"-", ":", " "}:
            statuses[cells[0]] = cells[column]
    return statuses


METRIC_ROWS = tuple(f"M{n:02d}" for n in range(1, 14))
GX_ROWS = tuple(f"GX-0{n}" for n in range(6))
# (item, matrix rows, evidence: tests and run criteria). Items 1-5 rest on the matrix rows and, where the run
# shows them, on the run; items 6-7 rest on the run (the lead sets NG-F13/NG-F14 after G1). The run has no
# criterion for items 2 and 4: it never converts, and the metrics are checked by the tests of their rules.
V01_ITEMS: tuple[tuple[str, str, tuple[str, ...], str], ...] = (
    (
        "five_formats",
        "5 Formate (EDF/EDF+, BDF, BrainVision, EEGLAB, FIF)",
        ("NG-F01",),
        "tests/corpus/test_corpus.py::test_every_dataset_is_read_without_m01_errors; "
        "G1-Lauf: alle Formate ohne Lesefehler (CORE-M01-01..04)",
    ),
    (
        "bids_conversion",
        "Konvertierung nach BIDS",
        ("NG-F02",),
        "tests/integration/test_convert.py::test_check_of_the_output_finds_no_validator_error; "
        "tests/corpus/test_corpus.py::test_one_recording_per_format_converts_without_validator_errors",
    ),
    (
        "structure_check",
        "Strukturprüfung (BIDS-Validator)",
        ("NG-F05",),
        "tests/unit/test_validator.py::test_command_grants_only_the_dataset_and_the_result_file; "
        "G1-Lauf: BIDS-STO-001 auf jedem BIDS-Datensatz ausgewertet",
    ),
    (
        "metrics",
        "Metriken M01–M13",
        METRIC_ROWS,
        "tests/rules/test_builtin_rules.py::test_every_builtin_rule_has_positive_and_negative_case",
    ),
    (
        "rulepacks",
        "Regelpakete bids und gxdsl008",
        ("RP-09", *GX_ROWS),
        "tests/rules/test_builtin_rules.py::test_every_builtin_rule_has_positive_and_negative_case; "
        "G1-Lauf: core, bids und gxdsl008 geladen",
    ),
    (
        "report",
        "Bericht zh/en (HTML und PDF)",
        ("NG-F13",),
        "tests/integration/test_report_p5.py; tests/integration/test_report_pdf.py; "
        "G1-Lauf: Befundzeilen, PDF-QA-Gate und unabhängige PDF-Prüfung zh/en",
    ),
    (
        "json",
        "JSON-Ausgabe (results.json, Exitcodes)",
        ("NG-F14",),
        "tests/unit/test_architecture.py::test_schemas_are_up_to_date; "
        "G1-Lauf: results.json schemagültig und kanonisch, Exitcodes",
    ),
)


def v01_checklist(
    statuses: Mapping[str, str], datasets: Sequence[Mapping[str, Any]], g1_met: bool
) -> list[dict[str, Any]]:
    """The seven V-01 items with status and evidence (matrix rows; run criteria from ``datasets``). ``run_ok``
    is None for an item without a run criterion (2 and 4): it rests on its matrix rows and their tests."""
    ran = [entry for entry in datasets if entry.get("check_exit") in (0, 1)]
    formats = {fmt for entry in ran if entry.get("read_errors") == 0 for fmt in entry.get("formats", [])}
    bids = [entry for entry in datasets if entry.get("is_bids")]
    run_ok: dict[str, bool | None] = {
        "five_formats": set(FORMATS) <= formats,
        "bids_conversion": None,
        "structure_check": bool(bids) and all(entry.get("validator_evaluated") for entry in bids),
        "metrics": None,
        "rulepacks": bool(datasets) and all(not entry.get("v06") for entry in datasets),
        "report": bool(datasets) and all(not entry.get("report_problems") for entry in datasets) and g1_met,
        "json": bool(datasets) and all(not entry.get("json_problems") for entry in datasets),
    }
    items = []
    for number, (item, title, rows, evidence) in enumerate(V01_ITEMS, start=1):
        matrix = {row: statuses.get(row, "fehlt") for row in rows}
        matrix_ok = all(status == "erfüllt" for status in matrix.values())
        fulfilled = run_ok[item] is not False and (matrix_ok or item in ("report", "json"))
        items.append(
            {
                "number": number,
                "item": item,
                "title": title,
                "status": "fulfilled" if fulfilled else "not_fulfilled",
                "matrix": matrix,
                "run_ok": run_ok[item],
                "evidence": evidence,
            }
        )
    return items


# --- one data set ------------------------------------------------------------------------------------------


@dataclass
class DatasetEval:
    """The evaluation of one run of one data set."""

    problems: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    stats: dict[str, Any] = field(default_factory=dict)

    def add(self, category: str, items: Iterable[str]) -> None:
        self.problems[category].extend(items)


def evaluate_run(
    dataset: Path,
    folder: Path,
    runs: Mapping[str, CommandRun],
    lang: str,
    out: Path,
    *,
    as_of: date = AS_OF,
    contents: bool = True,
) -> DatasetEval:
    """Every check on the outputs of one run of one data set. With ``contents=False`` only what differs
    between runs by design is checked - exit codes, console streams (their language) and the file list - for
    a run whose files are byte-identical to a run checked in full (the content checks would repeat
    themselves on the same bytes; compare_runs proves the identity)."""
    result = DatasetEval()
    checked = validate_results_file(folder / "results.json") if (folder / "results.json").is_file() else None
    results = checked.results if checked else None
    result.add("exit", check_exit_codes(runs, results))
    for name, run in runs.items():
        problems = check_console(run.stdout, run.stderr, lang, run.code, allowed_paths=(out,))
        result.add("console", (f"{name}: {problem}" for problem in problems))
    result.add("files", check_files(folder))
    if checked is None:
        result.add("json", ["results.json missing"])
        return result
    result.add("json", checked.problems)
    if results is None:
        return result
    forbidden = forbidden_values(dataset, out, as_of=as_of)
    consoles = [console_output(name, run, out) for name, run in runs.items()]
    manifest_text = ""
    if (folder / "manifest.json").is_file():
        manifest_text = (folder / "manifest.json").read_text(encoding="utf-8")
    # the file digests and the manifest hash the manifest declares (manifest and verify print the hash)
    manifest_digests = {match.group(0) for match in re.finditer(r"[0-9a-f]{64}", manifest_text)}
    if not contents:
        result.add("privacy", check_privacy(consoles, forbidden, results, extra=manifest_digests))
        return result
    for name in ("scan.json", "manifest.json"):
        if (folder / name).is_file():
            result.add("json", validate_schema_file(folder / name, SCHEMAS[name]))
    documents: dict[str, str] = {}
    outputs: list[Output] = []
    for lang_report in REPORT_LANGS:
        html_path = folder / f"report.{lang_report}.html"
        pdf_path = folder / f"report.{lang_report}.pdf"
        if not html_path.is_file() or not pdf_path.is_file():
            continue
        document = html_path.read_text(encoding="utf-8")
        documents[lang_report] = document
        rows = check_finding_rows(document, results, lang_report)
        result.add("rows", (f"{lang_report}: {problem}" for problem in rows.problems))
        result.add("html", (f"{lang_report}: {problem}" for problem in check_html(document, lang_report)))
        result.stats.setdefault("rows_checked", {})[lang_report] = rows.rows
        raw = pdf_path.read_bytes()
        pdf = check_pdf(raw, lang_report, results, document)
        result.add("pdf", (f"{lang_report}: {problem}" for problem in pdf.problems))
        result.stats.setdefault("pdf_pages", {})[lang_report] = pdf.pages
        outputs.append(Output(html_path.name, FONT_URI.sub(" ", document)))
        outputs.append(Output(pdf_path.name, pdf.text, raw=raw, info=pdf.info))
    for name in ("results.json", "scan.json"):
        if (folder / name).is_file():
            outputs.append(Output(name, (folder / name).read_text(encoding="utf-8")))
    if manifest_text:
        outputs.append(Output("manifest.json", manifest_text, manifest=True))
    outputs += consoles
    result.add("privacy", check_privacy(outputs, forbidden, results, extra=manifest_digests))
    result.add("privacy", age_problems(json.loads((folder / "results.json").read_text(encoding="utf-8"))))
    result.add("v06", v06_problems(results, [o.text for o in outputs if not o.manifest]))
    summary = results.summary
    failed_reads = [f for f in results.findings if f.rule_id in READ_RULES and f.status.value == "failed"]
    evaluated = {p.rule_id for p in results.passed} | {
        f.rule_id for f in results.findings if f.status.value in ("passed", "failed")
    }
    result.stats.update(
        formats=sorted({rec.format for rec in results.recordings}),
        recordings=len(results.recordings),
        is_bids=results.dataset.is_bids,
        errors=summary.errors,
        warnings=summary.warnings,
        findings=len(results.findings),
        read_errors=len(failed_reads),
        validator_evaluated="BIDS-STO-001" in evaluated,
        packs=[pack.name for pack in results.rulepacks],
        forbidden_checked=len(forbidden),
    )
    return result


# --- the whole run -----------------------------------------------------------------------------------------


def corpus_datasets() -> list[dict[str, Any]]:
    spec: dict[str, Any] = json.loads(SPEC.read_text(encoding="utf-8"))
    datasets: list[dict[str, Any]] = spec["datasets"]
    return datasets


def _start_checks(corpus: Path, names: Sequence[str], out: Path) -> None:
    if not corpus.is_dir():
        raise ToolError("the corpus folder does not exist (python tools/corpus.py fetch)")
    known = {entry["local_dir"]: entry["dataset"] for entry in corpus_datasets()}
    unknown = [name for name in names if name not in known]
    if unknown:
        raise ToolError(f"unknown data set(s): {', '.join(unknown)}; known: {', '.join(known)}")
    try:
        inside = out.resolve().is_relative_to(corpus.resolve())
    except OSError:
        inside = False
    if inside:
        raise ToolError("the output folder lies inside the corpus")
    verify = [sys.executable, str(ROOT / "tools" / "corpus.py"), "verify", "--root", str(corpus)]
    for name in names:
        verify += ["--dataset", known[name]]
    if subprocess.run(verify, capture_output=True, check=False).returncode != 0:
        raise ToolError("the corpus is incomplete or changed (python tools/corpus.py verify)")
    browser = [sys.executable, str(ROOT / "tools" / "install_pdf_browser.py"), "--check"]
    if subprocess.run(browser, capture_output=True, check=False).returncode != 0:
        raise ToolError("the PDF browser is not installed (python tools/install_pdf_browser.py)")


OWN_ENTRIES = ("summary.json", "summary.md", "jobs1")


def _prepare_out(out: Path, runs: int, replace: bool) -> None:
    """The output folder must be empty; with --replace the entries of an earlier run of this tool (and only
    those) are removed first."""
    out.mkdir(parents=True, exist_ok=True)
    own = {*OWN_ENTRIES, *(f"run{r}" for r in range(1, runs + 1))}
    present = {entry.name for entry in out.iterdir()}
    if not present:
        return
    if not replace:
        raise ToolError("the output folder is not empty (use --replace to repeat a run)")
    foreign = present - own
    if foreign:
        raise ToolError("the output folder holds files of something else; choose an empty folder")
    for name in sorted(present):
        target = out / name
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        else:
            target.unlink()


def run_acceptance(
    corpus: Path,
    out: Path,
    *,
    names: Sequence[str],
    runs: int = 2,
    jobs: int = 4,
    as_of: date = AS_OF,
    replace: bool = False,
) -> dict[str, Any]:
    """The whole G1 run; returns the summary (also written to <out>/summary.json and summary.md)."""
    # the commands run inside the output folder: relative arguments would point elsewhere there
    corpus, out = corpus.absolute(), out.absolute()
    _start_checks(corpus, names, out)
    _prepare_out(out, runs, replace)
    executable = neurogrid_executable()
    before = {name: tree_state(corpus / name) for name in names}
    entries: list[dict[str, Any]] = []
    for name in names:
        dataset = corpus / name
        evaluations: list[DatasetEval] = []
        seconds: dict[str, dict[str, float]] = {}
        exits: dict[str, int] = {}
        compared = {file: True for file in PRODUCT_FILES}  # file -> equal in every run so far
        for number in range(1, runs + 1):
            lang = CONSOLE_LANGS[(number - 1) % len(CONSOLE_LANGS)]
            folder = out / f"run{number}" / name
            print(f"{name}: run {number} (console {lang})", flush=True)
            commands = run_dataset(dataset, folder, lang=lang, jobs=jobs, as_of=as_of, executable=executable)
            seconds[f"run{number}"] = {cmd: run.seconds for cmd, run in commands.items()}
            contents = True
            if number == 1:
                exits = {cmd: run.code for cmd, run in commands.items()}
            else:
                same = compare_runs(out / "run1" / name, folder)
                compared = {file: equal and same[file] for file, equal in compared.items()}
                # a later run byte-identical to run 1 needs no second content check of the same bytes
                contents = not all(same.values())
            evaluations.append(
                evaluate_run(dataset, folder, commands, lang, out, as_of=as_of, contents=contents)
            )
        entries.append(_entry(name, out, evaluations, seconds, exits, compared))
    jobs1 = None
    if JOBS1_DATASET in names:
        folder = out / "jobs1" / JOBS1_DATASET
        print(f"{JOBS1_DATASET}: check --jobs 1", flush=True)
        single = run_dataset(
            corpus / JOBS1_DATASET,
            folder,
            lang="en",
            jobs=1,
            as_of=as_of,
            commands=("check",),
            executable=executable,
        )
        equal = compare_runs(out / "run1" / JOBS1_DATASET, folder, ("results.json",))["results.json"]
        run = single["check"]
        checked = (
            validate_results_file(folder / "results.json") if (folder / "results.json").is_file() else None
        )
        problems = check_exit_codes(single, checked.results if checked else None)
        problems += check_console(run.stdout, run.stderr, "en", run.code, allowed_paths=(out,))
        jobs1 = {
            "dataset": JOBS1_DATASET,
            "exit": run.code,
            "identical": equal,
            "check_s": run.seconds,
            "problems": problems,
            "ok": equal and not problems,
        }
    after = {name: tree_state(corpus / name) for name in names}
    unchanged = before == after
    _start_checks_after(corpus, names)
    summary = _summary(entries, jobs1, unchanged, runs=runs, jobs=jobs, as_of=as_of)
    write_summary(out, summary)
    return summary


def _start_checks_after(corpus: Path, names: Sequence[str]) -> None:
    known = {entry["local_dir"]: entry["dataset"] for entry in corpus_datasets()}
    verify = [sys.executable, str(ROOT / "tools" / "corpus.py"), "verify", "--root", str(corpus)]
    for name in names:
        verify += ["--dataset", known[name]]
    if subprocess.run(verify, capture_output=True, check=False).returncode != 0:
        raise ToolError("the corpus changed during the run (python tools/corpus.py verify)")


def _entry(
    name: str,
    out: Path,
    evaluations: Sequence[DatasetEval],
    seconds: Mapping[str, Mapping[str, float]],
    exits: Mapping[str, int],
    compared: Mapping[str, bool],
) -> dict[str, Any]:
    problems: dict[str, list[str]] = defaultdict(list)
    for number, evaluation in enumerate(evaluations, start=1):
        for category, items in evaluation.problems.items():
            problems[category].extend(f"run {number}: {item}" for item in items)
    different = [file for file, same in compared.items() if not same]
    if different:
        problems["determinism"].append(f"differs between the runs: {', '.join(different)}")
    stats = evaluations[0].stats
    unread = stats.get("read_errors") or 0
    if unread:  # a recording that cannot be read has not been checked (NG-F01, KONZEPT §6 G1)
        rules = f"{READ_RULES[0]}..{READ_RULES[-1][-2:]}"
        problems["read"].append(f"{unread} failed readability findings ({rules})")
    folder = out / "run1" / name
    sizes = {file: (folder / file).stat().st_size for file in PRODUCT_FILES if (folder / file).is_file()}
    flat = sorted(f"{category}: {item}" for category, items in problems.items() for item in items)
    return {
        "name": name,
        "formats": stats.get("formats", []),
        "recordings": stats.get("recordings"),
        "is_bids": stats.get("is_bids"),
        "exit": dict(exits),
        "check_exit": exits.get("check"),
        "report_exit": exits.get("report"),
        "errors": stats.get("errors"),
        "warnings": stats.get("warnings"),
        "findings": stats.get("findings"),
        "read_errors": stats.get("read_errors"),
        "validator_evaluated": stats.get("validator_evaluated"),
        "packs": stats.get("packs", []),
        "rows_checked": stats.get("rows_checked", {}),
        "pdf_pages": stats.get("pdf_pages", {}),
        "bytes": sizes,
        "seconds": {run: dict(values) for run, values in seconds.items()},
        "identical": not different and len(compared) == len(PRODUCT_FILES),
        "forbidden_values_checked": stats.get("forbidden_checked", 0),
        "report_problems": sorted(
            problems.get("rows", []) + problems.get("html", []) + problems.get("pdf", [])
        ),
        "json_problems": sorted(problems.get("json", []) + problems.get("exit", [])),
        "v06": sorted(problems.get("v06", [])),
        "problems": flat,
        "ok": not flat,
    }


def _summary(
    entries: Sequence[dict[str, Any]],
    jobs1: dict[str, Any] | None,
    unchanged: bool,
    *,
    runs: int,
    jobs: int,
    as_of: date,
) -> dict[str, Any]:
    # a data set and its formats count only when every recording was read (no failed CORE-M01 finding),
    # as for item 1 of the V-01 checklist: a format that could not be read has not been checked
    passed = [entry for entry in entries if entry["ok"] and entry.get("read_errors") == 0]
    formats = sorted({fmt for entry in passed for fmt in entry["formats"]})
    minimum = len(passed) >= MIN_DATASETS and len(formats) >= MIN_FORMATS
    all_met = bool(entries) and len(passed) == len(entries)
    statuses = matrix_status(MATRIX.read_text(encoding="utf-8")) if MATRIX.is_file() else {}
    criteria = minimum and all_met and unchanged and (jobs1 is None or jobs1["ok"])
    checklist = v01_checklist(statuses, entries, criteria)
    return {
        "schema": SUMMARY_SCHEMA,
        "as_of": as_of.isoformat(),
        "tool_version": neurogrid.__version__,
        "python": platform.python_version(),
        "platform": f"{sys.platform}-{platform.machine().lower()}",
        "playwright": PLAYWRIGHT_VERSION,
        "shell_revision": SHELL_REVISION,
        "runs": runs,
        "jobs": jobs,
        "datasets": list(entries),
        "jobs1": jobs1,
        "corpus_unchanged": unchanged,
        "g1": {
            "datasets_ok": len(passed),
            "datasets": len(entries),
            "formats_ok": formats,
            "minimum_met": minimum,
            "all_met": all_met,
            "criteria_met": criteria,  # the criteria of this run, not the whole G1 criterion
            "outside_this_run": list(OUTSIDE_THIS_RUN),
        },
        "v01_checklist": checklist,
        "v01_fulfilled": criteria and all(item["status"] == "fulfilled" for item in checklist),
        "v06_ok": all(not entry["v06"] for entry in entries),
    }


# --- summary files -----------------------------------------------------------------------------------------


def _yes(value: Any) -> str:
    return "ja" if value else "nein"


NO_RUN_CRITERION = "– (kein Laufkriterium)"  # the run column of a V-01 item the G1 run does not show


def _run_cell(value: bool | None) -> str:
    return NO_RUN_CRITERION if value is None else _yes(value)


def _pair(values: Mapping[str, Any], keys: Sequence[str] = REPORT_LANGS) -> str:
    return " / ".join(str(values.get(key, "–")) for key in keys)


def summary_markdown(summary: Mapping[str, Any]) -> str:
    """The German table of the G1 run for the phase report (no paths, no data from the data sets)."""
    g1 = summary["g1"]
    lines = [
        "# G1-Abnahme auf dem Testkorpus",
        "",
        f"Stichtag {summary['as_of']} · NeuroGrid {summary['tool_version']} · Python {summary['python']} · "
        f"{summary['platform']} · Playwright {summary['playwright']} · "
        f"Headless Shell {summary['shell_revision']} · {summary['runs']} Läufe · "
        f"check --jobs {summary['jobs']}",
        "",
        "| Datensatz | Format | Aufnahmen | Exit check / report | Fehler / Warnungen | Befunde | "
        "geprüfte Zeilen zh / en | PDF-Seiten zh / en | check s (Läufe) | report s (Läufe) | "
        "HTML kB zh / en | PDF kB zh / en | byte-gleich | Probleme |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for entry in summary["datasets"]:
        runs = sorted(entry["seconds"])
        check_s = " / ".join(str(entry["seconds"][run].get("check", "–")) for run in runs)
        report_s = " / ".join(str(entry["seconds"][run].get("report", "–")) for run in runs)
        size = entry["bytes"]
        html_kb = " / ".join(str(round(size.get(f"report.{lang}.html", 0) / 1000)) for lang in REPORT_LANGS)
        pdf_kb = " / ".join(str(round(size.get(f"report.{lang}.pdf", 0) / 1000)) for lang in REPORT_LANGS)
        lines.append(
            f"| {entry['name']} | {', '.join(entry['formats'])} | {entry['recordings']} | "
            f"{entry['check_exit']} / {entry['report_exit']} | {entry['errors']} / {entry['warnings']} | "
            f"{entry['findings']} | {_pair(entry['rows_checked'])} | {_pair(entry['pdf_pages'])} | "
            f"{check_s} | {report_s} | {html_kb} | {pdf_kb} | {_yes(entry['identical'])} | "
            f"{len(entry['problems'])} |"
        )
    jobs1 = summary["jobs1"]
    lines += [
        "",
        f"- Bestanden: {g1['datasets_ok']} von {g1['datasets']} Datensätzen; "
        f"Formate: {', '.join(g1['formats_ok'])}",
        f"- Mindestbedingung G1 (≥ {MIN_DATASETS} Datensätze in ≥ {MIN_FORMATS} Formaten): "
        f"{_yes(g1['minimum_met'])}",
        f"- Alle Datensätze bestanden: {_yes(g1['all_met'])}",
        f"- `--jobs 1` = `--jobs {summary['jobs']}` ({JOBS1_DATASET}): "
        + (_yes(jobs1["identical"]) if jobs1 else "nicht gelaufen"),
        f"- Korpus unverändert: {_yes(summary['corpus_unchanged'])}",
        f"- Alle Kriterien dieses Laufs erfüllt: {_yes(g1['criteria_met'])}",
        f"- Nicht Teil dieses Laufs (eigene Nachweise): {'; '.join(g1['outside_this_run'])}",
        "",
        "## V-01-Checkliste",
        "",
        "| Nr. | Punkt | Status | Matrix | Lauf | Nachweis |",
        "|---|---|---|---|---|---|",
    ]
    for item in summary["v01_checklist"]:
        matrix = ", ".join(f"{row} {status}" for row, status in item["matrix"].items())
        status = "erfüllt" if item["status"] == "fulfilled" else "nicht erfüllt"
        lines.append(
            f"| {item['number']} | {item['title']} | {status} | {matrix} | {_run_cell(item['run_ok'])} | "
            f"{item['evidence']} |"
        )
    lines += [
        "",
        f"V-01 insgesamt: {'erfüllt' if summary['v01_fulfilled'] else 'nicht erfüllt'}",
        "",
        "## V-06",
        "",
        f"Geladene Pakete je Datensatz genau core, bids, gxdsl008; keine {NORM}-Regel, -Quelle oder "
        f"-Klauselnummer in den Ausgaben: {_yes(summary['v06_ok'])} "
        "(dazu tests/unit/test_norm_independence.py).",
        "",
        "## Probleme",
        "",
    ]
    problems = [(entry["name"], problem) for entry in summary["datasets"] for problem in entry["problems"]]
    if jobs1:
        problems += [(f"{jobs1['dataset']} (--jobs 1)", problem) for problem in jobs1["problems"]]
    lines += [f"- {name}: {problem}" for name, problem in problems] or ["- keine"]
    return "\n".join(lines) + "\n"


def write_summary(out: Path, summary: Mapping[str, Any]) -> None:
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (out / "summary.md").write_text(summary_markdown(summary), encoding="utf-8", newline="\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("--corpus", type=Path, required=True, help="the corpus folder (tools/corpus.py)")
    parser.add_argument("--out", type=Path, required=True, help="output folder of the runs and the summary")
    parser.add_argument("--datasets", nargs="+", help="local folder names (default: all of corpus_spec.json)")
    parser.add_argument("--runs", type=int, default=2, help="runs to compare byte by byte (at least 2)")
    parser.add_argument("--jobs", type=int, default=4, help="--jobs of check (the extra run uses 1)")
    parser.add_argument("--as-of", type=date.fromisoformat, default=AS_OF, help="reference date (A-08)")
    parser.add_argument("--replace", action="store_true", help="replace an earlier run of this tool in --out")
    args = parser.parse_args(argv)
    if args.runs < 2:
        parser.error("--runs must be at least 2")
    names = args.datasets or [entry["local_dir"] for entry in corpus_datasets()]
    try:
        summary = run_acceptance(
            args.corpus,
            args.out,
            names=names,
            runs=args.runs,
            jobs=args.jobs,
            as_of=args.as_of,
            replace=args.replace,
        )
    except ToolError as exc:
        print(f"acceptance: {exc}", file=sys.stderr)
        return 2
    g1 = summary["g1"]
    print(
        f"G1: {g1['datasets_ok']}/{g1['datasets']} data sets passed, formats {', '.join(g1['formats_ok'])}; "
        f"minimum {'met' if g1['minimum_met'] else 'NOT met'}; "
        f"all criteria of this run {'met' if g1['criteria_met'] else 'NOT met'}"
    )
    print(f"  outside this run: {'; '.join(g1['outside_this_run'])}")
    for entry in summary["datasets"]:
        for problem in entry["problems"]:
            print(f"  {entry['name']}: {problem}")
    for problem in (summary["jobs1"] or {}).get("problems", []):
        print(f"  {JOBS1_DATASET} (--jobs 1): {problem}")
    return 0 if g1["criteria_met"] else 1


if __name__ == "__main__":
    sys.exit(main())
