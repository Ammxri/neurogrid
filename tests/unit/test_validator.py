"""BIDS validator integration: sandboxed deno call, result parsing, BIDS measurements and NeuroGrid texts
per validator code (NG-F05, RP-09, LIB-03, A-03, A-06, A-07, A-12, A-49, A-54).

Covers neurogrid.validator (command, environment, parse, run), neurogrid.checks.bids (issues as measurements
per recording, file or dataset and validator code, sub-codes in the details; exceptions per code; issues
behind skipped links; HED schema issues; raw folders and single files), the validator code table
report/validator_codes.yaml with texts.validator_codes/validator_text, _Formatter.details for validator
findings, and the error path of kernel.safety.work_directory.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import types
from collections import Counter
from datetime import date
from importlib import metadata
from pathlib import Path, PurePosixPath
from typing import Any

import pytest
from markupsafe import escape

import gen_fixtures  # type: ignore[import-not-found,unused-ignore]
from conftest import dir_link  # type: ignore[import-not-found,unused-ignore]
from neurogrid import pipeline, validator
from neurogrid.checks import bids
from neurogrid.checks import context as context_module
from neurogrid.checks.context import CheckContext
from neurogrid.config import Config
from neurogrid.io.discover import pseudonym, scan
from neurogrid.kernel.errors import InputError
from neurogrid.kernel.findings import Finding, Phase, Severity, SourceStatus, Status
from neurogrid.kernel.rules import Measurement
from neurogrid.kernel.safety import load_yaml, work_directory
from neurogrid.model.results import Results
from neurogrid.report import texts
from neurogrid.report.render import _Formatter, render_report
from neurogrid.report.texts import translator, validator_codes, validator_text
from neurogrid.validator import ValidatorError, ValidatorIssue, ValidatorResult

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"
AS_OF = date(2026, 10, 11)
CATEGORIES = {"general", "eeg", "meg", "ieeg", "other_modality"}
DYNAMIC_CODES = {
    "JSON_KEY_REQUIRED",
    "JSON_KEY_RECOMMENDED",
    "SIDECAR_KEY_REQUIRED",
    "SIDECAR_KEY_RECOMMENDED",
}
FIXED_ENV = {"DENO_NO_UPDATE_CHECK", "DENO_NO_PROMPT", "DENO_DIR", "NO_COLOR", "TMP", "TEMP", "TMPDIR"}

# A validator 3.0.2 result document as written with --format json (shape taken from a real run).
DOCUMENT: dict[str, Any] = {
    "issues": {
        "issues": [
            {
                "code": "SIDECAR_KEY_REQUIRED",
                "subCode": "EEGReference",
                "severity": "error",
                "location": "/sub-01/eeg/sub-01_task-rest_eeg.edf",
                "issueMessage": "Field description: General description of the reference scheme used.",
                "rule": "rules.sidecars.eeg.EEGReference",
            },
            {
                "code": "HED_ERROR",
                "subCode": "SCHEMA_LOAD_FAILED",
                "severity": "error",
                "issueMessage": "ERROR: [SCHEMA_LOAD_FAILED] Could not load HED schema.",
            },
            {
                "code": "README_FILE_MISSING",
                "severity": "warning",
                "location": "/dataset_description.json",
                "rule": "rules.checks.hints.ReadmeFileMissing",
            },
        ],
        "codeMessages": {"README_FILE_MISSING": "A README file is recommended."},
    },
    "summary": {"subjects": ["01"], "schemaVersion": "1.2.7"},
}
PARSED = (
    ValidatorIssue("SIDECAR_KEY_REQUIRED", "EEGReference", "error", "sub-01/eeg/sub-01_task-rest_eeg.edf"),
    ValidatorIssue("HED_ERROR", "SCHEMA_LOAD_FAILED", "error", None),
    ValidatorIssue("README_FILE_MISSING", None, "warning", "dataset_description.json"),
)


# --- helpers ----------------------------------------------------------------------------------------------


class _FakeRun:
    """Stands in for subprocess.run: records each call and writes ``payload`` to the file after ``-o``."""

    def __init__(self, exit_code: int = 0, payload: bytes | None = None, error: BaseException | None = None):
        self.exit_code = exit_code
        self.payload = payload
        self.error = error
        self.calls: list[tuple[Any, dict[str, Any]]] = []

    def __call__(self, args: Any, **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        self.calls.append((args, kwargs))
        if self.error is not None:
            raise self.error
        if self.payload is not None:
            Path(args[args.index("-o") + 1]).write_bytes(self.payload)
        return subprocess.CompletedProcess(args, self.exit_code, b"", b"")


def _fake(monkeypatch: pytest.MonkeyPatch, fake: _FakeRun) -> _FakeRun:
    monkeypatch.setattr(subprocess, "run", fake)
    return fake


def _dataset(tmp_path: Path) -> Path:
    folder = tmp_path / "ds"
    folder.mkdir(parents=True)
    return folder


def _files(folder: Path) -> dict[str, str]:
    """Relative path -> SHA-256 of the content for every file below ``folder`` (detects any write)."""
    return {
        p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in folder.rglob("*")
        if p.is_file()
    }


@pytest.fixture(scope="module")
def bundle_text() -> str:
    bundle, _binary = validator._tools()
    return bundle.read_text(encoding="utf-8")


def _issue_list(bundle: str) -> str:
    """The object literal ``var bidsIssues = { ... };`` of the bundle (the validator's own issue list)."""
    start = bundle.index("var bidsIssues = {")
    return bundle[start : bundle.index("\n};", start)]


def _issue_list_codes(bundle: str) -> set[str]:
    return set(re.findall(r"^  ([A-Z][A-Z0-9_]*): \{", _issue_list(bundle), flags=re.MULTILINE))


def _schema_codes(bundle: str) -> set[str]:
    return set(re.findall(r'issue: \{ code: "([A-Z][A-Z0-9_]*)"', bundle))


def _plain(text: str) -> str:
    """A message as a reader sees it: JS escapes (``\\n``) and white space runs as one space, lower case."""
    return " ".join(text.replace("\\n", " ").replace("\\t", " ").split()).lower()


def _bundle_messages(bundle: str) -> list[tuple[str, str]]:
    """Every English text of the validator with its code: ``reason`` in the issue list, ``message`` in the
    schema. A list, because some schema codes have several messages."""
    reasons = re.findall(
        r'^  ([A-Z][A-Z0-9_]*): \{\n    severity: "\w+",\n    reason: "([^"\n]+)"',
        _issue_list(bundle),
        flags=re.MULTILINE,
    )
    messages = re.findall(r'issue: \{ code: "([A-Z][A-Z0-9_]*)", message: "([^"\n]+)"', bundle)
    return [(code, _plain(text)) for code, text in messages + reasons]


# --- command and environment (A-06, A-49, A-54) ---------------------------------------------------------


def test_command_grants_only_the_dataset_and_the_result_file(tmp_path: Path) -> None:
    dataset = tmp_path / "data set"
    result = tmp_path / "work" / "validator.json"
    binary = tmp_path / "bin" / "deno.exe"
    bundle = tmp_path / "pkg" / "bids-validator.js"
    cmd = validator.command(dataset, result, binary, bundle)
    assert cmd[:2] == [str(binary), "run"]
    script = cmd.index(str(bundle))
    flags, script_args = cmd[2:script], cmd[script:]
    # deno options must come before the script, otherwise deno would pass them to the bundle
    assert {"--no-prompt", "--no-remote", "--no-npm", "--cached-only", "--deny-net"} <= set(flags)
    assert {"--no-config", "--no-lock"} <= set(flags)
    assert [f for f in flags if f.startswith("--allow-read")] == [f"--allow-read={dataset}"]
    assert [f for f in flags if f.startswith("--allow-write")] == [f"--allow-write={result}"]
    assert [f for f in flags if f.startswith("--allow-env")] == [
        f"--allow-env={','.join(validator.ENV_ALLOW)}"
    ]
    # nothing beyond read, write, env and the OS release: no net, run, ffi, import or blanket permission
    assert {f.split("=", 1)[0] for f in flags if f.startswith("--allow")} == {
        "--allow-read",
        "--allow-write",
        "--allow-env",
        "--allow-sys",
    }
    assert "--allow-sys=osRelease" in flags and "-A" not in cmd
    assert not any(arg.startswith("--schema") for arg in cmd)  # the bundled schema is used (A-06)
    assert script_args == [
        str(bundle),
        str(dataset),
        "--format",
        "json",
        "-o",
        str(result),
        "--max-rows",
        "-1",
    ]


def test_allowed_environment_names_are_plain_and_hold_no_secrets() -> None:
    names = set(validator.ENV_ALLOW)
    assert len(names) == len(validator.ENV_ALLOW)
    assert all(re.fullmatch(r"[A-Z0-9_]+", name) for name in names)  # no comma can widen the list
    for secret in ("PATH", "HOME", "USERPROFILE", "APPDATA", "HTTPS_PROXY", "HTTP_PROXY", "DENO_AUTH_TOKENS"):
        assert secret not in names


@pytest.mark.parametrize("which", ["dataset", "result"])
def test_path_with_comma_is_refused(tmp_path: Path, which: str) -> None:
    dataset = tmp_path / ("a,b" if which == "dataset" else "ds")
    result = tmp_path / ("w,x" if which == "result" else "w") / "validator.json"
    with pytest.raises(ValidatorError) as info:
        validator.command(dataset, result, tmp_path / "deno", tmp_path / "bundle.js")
    assert info.value.message_key == "validator.comma_path"
    for lang in ("zh", "en"):
        assert translator(lang, strict=True).t("errors.validator.comma_path")


def test_comma_in_the_bundle_or_binary_path_is_harmless(tmp_path: Path) -> None:
    """Only the permission lists are split at commas; the binary and the script path are plain arguments."""
    cmd = validator.command(
        tmp_path / "ds", tmp_path / "v.json", tmp_path / "a,b" / "deno", tmp_path / "c,d.js"
    )
    assert cmd[0] == str(tmp_path / "a,b" / "deno") and str(tmp_path / "c,d.js") in cmd


def test_run_refuses_comma_paths_before_starting_deno(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _fake(monkeypatch, _FakeRun(0, json.dumps(DOCUMENT).encode()))
    dataset = tmp_path / "x,y"
    dataset.mkdir()
    with pytest.raises(ValidatorError) as info:
        validator.run(dataset, tmp_path / "work")
    assert info.value.message_key == "validator.comma_path" and fake.calls == []


def test_environment_is_reduced_and_points_into_the_work_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = tmp_path / "work"
    monkeypatch.setenv("BIDS_SCHEMA", "https://example.invalid/schema.json")
    monkeypatch.setenv("DENO_DIR", str(tmp_path / "foreign-deno-dir"))
    monkeypatch.setenv("DENO_AUTH_TOKENS", "secret@example.invalid")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:3128")
    monkeypatch.setenv("NEUROGRID_TEST_SECRET", "do-not-pass")
    monkeypatch.setenv("TERM", "xterm")  # readable by the bundle, but not passed on either
    monkeypatch.setenv("SYSTEMROOT", "C:\\Windows")
    monkeypatch.delenv("WINDIR", raising=False)
    assert validator.environment(work) == {
        "DENO_NO_UPDATE_CHECK": "1",
        "DENO_NO_PROMPT": "1",
        "DENO_DIR": str(work / "deno"),
        "NO_COLOR": "1",
        "TMP": str(work),
        "TEMP": str(work),
        "TMPDIR": str(work),
        "SYSTEMROOT": "C:\\Windows",
    }


def test_environment_passes_windir_only_when_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SYSTEMROOT", raising=False)
    monkeypatch.setenv("WINDIR", "C:\\Windows")
    env = validator.environment(tmp_path)
    assert set(env) == FIXED_ENV | {"WINDIR"} and env["WINDIR"] == "C:\\Windows"
    monkeypatch.delenv("WINDIR")
    assert set(validator.environment(tmp_path)) == FIXED_ENV


# --- parse ------------------------------------------------------------------------------------------------


def test_parse_reads_code_subcode_severity_location_and_schema_version() -> None:
    assert validator.parse(DOCUMENT) == ("1.2.7", PARSED)


def test_parse_skips_malformed_entries_and_normalizes_fields() -> None:
    document: dict[str, Any] = {
        "issues": {
            "issues": [
                "not an object",
                {"subCode": "no code"},
                {"code": 12, "severity": "error"},
                {"code": "EMPTY_FILE", "subCode": 3, "location": 7},
                {"code": "NOT_INCLUDED", "severity": "ignore", "location": "/"},
                {"code": "SUBJECT_FOLDERS", "severity": "warning", "location": "/sub-01/"},
                {"code": "HED_WARNING", "subCode": "", "severity": "warning", "location": ""},
            ]
        },
        "summary": {"schemaVersion": 127},
    }
    assert validator.parse(document) == (
        None,
        (
            ValidatorIssue("EMPTY_FILE", None, "error", None),  # missing severity counts as error
            ValidatorIssue("NOT_INCLUDED", None, "ignore", None),  # the dataset root is no file location
            ValidatorIssue("SUBJECT_FOLDERS", None, "warning", "sub-01"),
            ValidatorIssue("HED_WARNING", "", "warning", None),
        ),
    )


@pytest.mark.parametrize(
    "document",
    [
        {},
        {"issues": [], "summary": []},
        {"issues": {"issues": {"code": "EMPTY_FILE"}}, "summary": "1.2.7"},
        {"issues": {"codeMessages": {}}, "summary": {"schemaVersion": None}},
    ],
)
def test_parse_tolerates_unexpected_shapes(document: dict[str, Any]) -> None:
    assert validator.parse(document) == (None, ())


# --- run with a stand-in for deno (A-06, A-12) ------------------------------------------------------------


def test_run_starts_deno_with_an_argument_list_and_the_reduced_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _fake(monkeypatch, _FakeRun(16, json.dumps(DOCUMENT).encode()))
    dataset = _dataset(tmp_path)
    work = tmp_path / "out" / "run-1" / "validator"  # not there yet
    result = validator.run(tmp_path / "ds" / ".." / "ds", work)
    assert result == ValidatorResult(exit_code=16, schema_version="1.2.7", issues=PARSED)
    assert work.is_dir() and (work / "validator.json").is_file()
    ((args, kwargs),) = fake.calls
    bundle, binary = validator._tools()
    assert isinstance(args, list)
    assert args == validator.command(dataset.resolve(), work / "validator.json", binary, bundle)
    assert kwargs == {
        "capture_output": True,
        "env": validator.environment(work),
        "timeout": validator.TIMEOUT_S,
        "stdin": subprocess.DEVNULL,
        "check": False,
    }  # in particular no shell


def test_exit_zero_is_a_result_without_issues(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    empty = {"issues": {"issues": [], "codeMessages": {}}, "summary": {"schemaVersion": "1.2.7"}}
    _fake(monkeypatch, _FakeRun(0, json.dumps(empty).encode()))
    assert validator.run(_dataset(tmp_path), tmp_path / "w") == ValidatorResult(0, "1.2.7", ())


def test_timeout_is_forwarded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _fake(monkeypatch, _FakeRun(0, json.dumps(DOCUMENT).encode()))
    validator.run(_dataset(tmp_path), tmp_path / "w", timeout=7.5)
    assert fake.calls[0][1]["timeout"] == 7.5


@pytest.mark.parametrize(
    ("exit_code", "payload"),
    [
        (1, json.dumps(DOCUMENT).encode()),  # deno's own error exit, even with a result file
        (2, None),
        (-9, None),  # killed
        (0, None),  # success claimed, but no result file
        (16, None),
        (16, b"{not json"),
        (16, b"[]"),  # JSON, but no document
        (16, b'"text"'),
        (0, b"\xff\xfe\x00{"),  # not UTF-8
    ],
)
def test_other_outcomes_are_tool_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exit_code: int, payload: bytes | None
) -> None:
    _fake(monkeypatch, _FakeRun(exit_code, payload))
    with pytest.raises(ValidatorError) as info:
        validator.run(_dataset(tmp_path), tmp_path / "w")
    assert info.value.message_key == "validator.failed"
    assert info.value.params == {"code": exit_code}


def test_oversized_result_is_a_tool_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.dumps(DOCUMENT).encode()
    monkeypatch.setattr(validator, "MAX_RESULT_BYTES", len(payload) - 1)
    _fake(monkeypatch, _FakeRun(16, payload))
    with pytest.raises(ValidatorError) as info:
        validator.run(_dataset(tmp_path), tmp_path / "w")
    assert (info.value.message_key, info.value.params) == ("validator.failed", {"code": 16})
    monkeypatch.setattr(validator, "MAX_RESULT_BYTES", len(payload))
    assert validator.run(_dataset(tmp_path / "again"), tmp_path / "w2").issues == PARSED


def test_timeout_is_a_tool_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake(monkeypatch, _FakeRun(error=subprocess.TimeoutExpired(cmd="deno", timeout=1)))
    with pytest.raises(ValidatorError) as info:
        validator.run(_dataset(tmp_path), tmp_path / "w", timeout=1)
    assert info.value.message_key == "validator.timeout"
    assert info.value.__suppress_context__  # no foreign traceback text in the message chain (A-07)


@pytest.mark.parametrize("error", [FileNotFoundError(2, "missing"), PermissionError(13, "denied")])
def test_unstartable_binary_is_reported_as_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: OSError
) -> None:
    _fake(monkeypatch, _FakeRun(error=error))
    with pytest.raises(ValidatorError) as info:
        validator.run(_dataset(tmp_path), tmp_path / "w")
    assert info.value.message_key == "validator.missing"


@pytest.mark.parametrize("module", ["bids_validator_deno", "deno"])
def test_missing_package_is_a_tool_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, module: str
) -> None:
    monkeypatch.setitem(sys.modules, module, None)  # makes "import <module>" fail
    fake = _fake(monkeypatch, _FakeRun(0, json.dumps(DOCUMENT).encode()))
    with pytest.raises(ValidatorError) as info:
        validator.run(_dataset(tmp_path), tmp_path / "w")
    assert info.value.message_key == "validator.missing" and fake.calls == []


def test_package_without_bundle_is_a_tool_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = types.ModuleType("bids_validator_deno")
    package.__file__ = str(tmp_path / "bids_validator_deno" / "__init__.py")
    monkeypatch.setitem(sys.modules, "bids_validator_deno", package)
    with pytest.raises(ValidatorError) as info:
        validator._tools()
    assert info.value.message_key == "validator.missing"


def test_missing_deno_binary_is_a_tool_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import deno  # type: ignore[import-untyped,unused-ignore]

    monkeypatch.setattr(deno, "find_deno_bin", lambda: str(tmp_path / "deno.exe"))
    with pytest.raises(ValidatorError) as info:
        validator._tools()
    assert info.value.message_key == "validator.missing"


def test_installed_tools_match_the_pins() -> None:
    bundle, binary = validator._tools()
    assert bundle.name == "bids-validator.js" and bundle.is_file() and binary.is_file()
    assert metadata.version("bids-validator-deno") == validator.VALIDATOR_VERSION == "3.0.2"
    assert metadata.version("deno") == "2.9.7"  # the runtime the permission flags were probed with (KONZEPT)


@pytest.mark.parametrize("key", ["missing", "failed", "timeout", "comma_path"])
def test_validator_errors_have_texts(key: str) -> None:
    for lang in ("zh", "en"):
        text = translator(lang, strict=True).t(f"errors.validator.{key}", code=16)
        assert text and "{" not in text


# --- real runs of the bundled validator ------------------------------------------------------------------


@pytest.fixture(scope="module")
def real_runs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, tuple[ValidatorResult, Path]]:
    """One real validator run per BIDS fixture; work folders with a space and non-ASCII letters (A-54)."""
    base = tmp_path_factory.mktemp("validator")
    runs: dict[str, tuple[ValidatorResult, Path]] = {}
    with pytest.MonkeyPatch.context() as patch:
        # a schema URL in the caller's environment must not reach the validator (A-06): it would be fetched
        patch.setenv("BIDS_SCHEMA", "https://example.invalid/schema.json")
        for name in ("bids_ok", "bids_issues"):
            before = _files(FIX / name)
            work = base / f"工作 {name}" / "validator"
            runs[name] = (validator.run(FIX / name, work), work)
            assert _files(FIX / name) == before  # only read access to the dataset
    return runs


def test_real_run_on_a_valid_dataset_reports_nothing(
    real_runs: dict[str, tuple[ValidatorResult, Path]],
) -> None:
    result, work = real_runs["bids_ok"]
    assert result == ValidatorResult(exit_code=0, schema_version="1.2.7", issues=())
    assert (work / "validator.json").is_file()
    assert {p.name for p in work.iterdir()} <= {"validator.json", "deno"}  # writes stay in the work folder


EDF_01 = "sub-01/eeg/sub-01_task-rest_eeg.edf"
EDF_02 = "sub-02/eeg/sub-02_task-rest_eeg.edf"
EVENTS_01 = "sub-01/eeg/sub-01_task-rest_events.tsv"
DESCRIPTION = "dataset_description.json"


def test_real_run_on_a_dataset_with_issues(real_runs: dict[str, tuple[ValidatorResult, Path]]) -> None:
    result, _work = real_runs["bids_issues"]
    assert result.exit_code == 16 and result.schema_version == "1.2.7"
    # exactly the planted errors: EEGReference missing in sub-01, HED schema 8.99.0 not bundled (offline)
    assert Counter(i for i in result.issues if i.severity == "error") == Counter(
        [
            ValidatorIssue("SIDECAR_KEY_REQUIRED", "EEGReference", "error", EDF_01),
            ValidatorIssue("HED_ERROR", "SCHEMA_LOAD_FAILED", "error", None),
        ]
    )
    # warnings: the incomplete dataset_description.json (BIDSVersion "v1.2.1", no README, no authors) and
    # missing recommended sidecar fields; the channel count mismatch only where it was planted (sub-01)
    assert {(i.code, i.location) for i in result.issues if i.severity == "warning"} == {
        ("UNKNOWN_BIDS_VERSION", DESCRIPTION),
        ("README_FILE_MISSING", DESCRIPTION),
        ("TOO_FEW_AUTHORS", DESCRIPTION),
        ("NO_AUTHORS", DESCRIPTION),
        ("JSON_KEY_RECOMMENDED", DESCRIPTION),
        ("EEG_CHANNEL_COUNT_MISMATCH", EDF_01),
        ("SIDECAR_KEY_RECOMMENDED", EDF_01),
        ("SIDECAR_KEY_RECOMMENDED", EDF_02),
        ("SIDECAR_KEY_RECOMMENDED", EVENTS_01),
    }
    assert {i.sub_code for i in result.issues if i.code == "JSON_KEY_RECOMMENDED"} == {
        "License",
        "GeneratedBy",
        "SourceDatasets",
    }
    assert {i.severity for i in result.issues} == {"error", "warning"}
    codes = validator_codes()
    assert all(i.code in codes for i in result.issues)  # every code of the real run has a NeuroGrid text


# --- checks/bids.py: issues as measurements (RP-09, A-06, A-09) -------------------------------------------

VHDR = "sub-01/eeg/sub-01_task-rest_eeg.vhdr"
SET = "sub-02/eeg/sub-02_task-rest_eeg.set"


def _bids_dataset(tmp_path: Path) -> Path:
    """A BIDS folder with a BrainVision triple (sub-01) and an EEGLAB .set/.fdt pair (sub-02)."""
    root = tmp_path / "bids"
    root.mkdir()
    (root / "dataset_description.json").write_text(
        json.dumps({"Name": "t", "BIDSVersion": "1.11.1"}), encoding="utf-8"
    )
    gen_fixtures.write_brainvision(root / VHDR, seconds=1)
    gen_fixtures.write_eeglab(root / SET, seconds=1)
    (root / "sub-01/eeg/sub-01_task-rest_channels.tsv").write_text("name\ttype\tunits\n", encoding="utf-8")
    (root / "notes.txt").write_text("not part of BIDS\n", encoding="utf-8")
    return root


def _context(root: Path, issues: tuple[ValidatorIssue, ...]) -> CheckContext:
    ctx = CheckContext.build(scan(root), Config(), work=None)
    return CheckContext(
        root=ctx.root,
        scan=ctx.scan,
        config=ctx.config,
        recordings=ctx.recordings,
        _validator=ValidatorResult(exit_code=16 if issues else 0, schema_version="1.2.7", issues=issues),
    )


def _identity(relative: str, suffix: str) -> tuple[str, ...]:
    """Relative path, pseudonymous ID and pseudonymous file name of a recording (A-09, A-14)."""
    pseudo = pseudonym(PurePosixPath(relative))
    return (relative, pseudo, f"{pseudo}{suffix}")


def _failed(
    check_id: str,
    obj: str,
    code: str,
    file: str | None,
    identity: tuple[str, ...],
    count: int,
    sub_codes: dict[str, int] | None = None,
) -> Measurement:
    """One measurement per object and validator code: subkey = the code (A-06, A-77, KONZEPT)."""
    details: dict[str, Any] = {"validator_code": code, "count": count}
    if sub_codes is not None:
        details["sub_codes"] = sub_codes
    return Measurement(
        check_id=check_id,
        object=obj,
        subkey=code,
        file=file,
        value=False,
        details=details,
        identity=identity,
    )


ISSUES = (
    ValidatorIssue("SIDECAR_KEY_REQUIRED", "EEGReference", "error", VHDR),
    ValidatorIssue("SIDECAR_KEY_REQUIRED", "EEGReference", "error", "sub-01/eeg/sub-01_task-rest_eeg.vmrk"),
    ValidatorIssue("BRAINVISION_LINKS_BROKEN", None, "error", "sub-01/eeg/sub-01_task-rest_eeg.eeg"),
    ValidatorIssue("EMPTY_FILE", None, "error", "sub-02/eeg/sub-02_task-rest_eeg.fdt"),
    ValidatorIssue("NOT_INCLUDED", None, "error", "notes.txt"),
    ValidatorIssue("SUBJECT_FOLDERS", None, "error", None),
    ValidatorIssue("SUBJECT_FOLDERS", None, "error", None),
    ValidatorIssue("HED_ERROR", "SCHEMA_LOAD_FAILED", "error", None),
    ValidatorIssue("HED_ERROR", "TAG_INVALID", "error", "sub-01/eeg/sub-01_task-rest_events.tsv"),
    ValidatorIssue("HED_WARNING", "SCHEMA_LOAD_FAILED", "warning", "dataset_description.json"),
    ValidatorIssue("JSON_KEY_RECOMMENDED", "License", "warning", "dataset_description.json"),
    ValidatorIssue(
        "TSV_ADDITIONAL_COLUMNS_UNDEFINED", None, "warning", "sub-01/eeg/sub-01_task-rest_channels.tsv"
    ),
    ValidatorIssue("EEG_CHANNEL_COUNT_MISMATCH", None, "warning", VHDR),
    ValidatorIssue("README_FILE_MISSING", None, "ignore", "dataset_description.json"),
    ValidatorIssue("HED_ERROR", "SCHEMA_LOAD_FAILED", "ignore", None),
)


def test_errors_are_grouped_per_recording_file_and_dataset(tmp_path: Path) -> None:
    ctx = _context(_bids_dataset(tmp_path), ISSUES)
    vhdr_identity = _identity(VHDR, ".vhdr")
    set_identity = _identity(SET, ".set")
    events = "sub-01/eeg/sub-01_task-rest_events.tsv"
    assert bids.measure_errors(ctx) == [
        _failed(bids.ERRORS, "dataset", "SUBJECT_FOLDERS", None, (), 2),
        _failed(bids.ERRORS, "notes.txt", "NOT_INCLUDED", "notes.txt", ("notes.txt",), 1),
        # .vmrk and .eeg belong to the .vhdr recording: same object, one per code, sub-codes in the details
        _failed(bids.ERRORS, VHDR, "BRAINVISION_LINKS_BROKEN", VHDR, vhdr_identity, 1),
        _failed(bids.ERRORS, VHDR, "SIDECAR_KEY_REQUIRED", VHDR, vhdr_identity, 2, {"EEGReference": 2}),
        _failed(bids.ERRORS, events, "HED_ERROR", events, (events,), 1, {"TAG_INVALID": 1}),
        _failed(bids.ERRORS, SET, "EMPTY_FILE", SET, set_identity, 1),  # .fdt counts for the .set
    ]


def test_one_measurement_per_object_and_code_with_counts_per_sub_code(tmp_path: Path) -> None:
    """A-06, A-77, KONZEPT: subkey = validator code; the sub-codes (e.g. field names) and their counts go to
    the details, sorted by sub-code; occurrences without a sub-code count only in the total."""
    edf = "sub-01/eeg/sub-01_task-rest_eeg.edf"
    issues = (
        ValidatorIssue("SIDECAR_KEY_RECOMMENDED", "Manufacturer", "warning", edf),
        ValidatorIssue("SIDECAR_KEY_RECOMMENDED", "CapManufacturer", "warning", edf),
        ValidatorIssue("SIDECAR_KEY_RECOMMENDED", "EEGGround", "warning", edf),
        ValidatorIssue("SIDECAR_KEY_RECOMMENDED", "EEGGround", "warning", edf),
        ValidatorIssue("SIDECAR_KEY_RECOMMENDED", None, "warning", edf),
        ValidatorIssue("SIDECAR_KEY_RECOMMENDED", "", "warning", edf),  # an empty sub-code is none
        ValidatorIssue("SIDECAR_KEY_RECOMMENDED", "TaskName", "warning", None),
    )
    ctx = _context(_bids_dataset(tmp_path), issues)
    measurements = bids.measure_warnings(ctx)
    assert measurements == [
        _failed(bids.WARNINGS, "dataset", "SIDECAR_KEY_RECOMMENDED", None, (), 1, {"TaskName": 1}),
        _failed(
            bids.WARNINGS,
            edf,
            "SIDECAR_KEY_RECOMMENDED",
            edf,
            (edf,),
            6,
            {"CapManufacturer": 1, "EEGGround": 2, "Manufacturer": 1},
        ),
    ]
    assert list(measurements[1].details["sub_codes"]) == ["CapManufacturer", "EEGGround", "Manufacturer"]
    without = bids.measure_warnings(_context(tmp_path / "bids", (issues[4],)))
    assert without == [_failed(bids.WARNINGS, edf, "SIDECAR_KEY_RECOMMENDED", edf, (edf,), 1)]
    assert "sub_codes" not in without[0].details


def test_warnings_are_measured_separately(tmp_path: Path) -> None:
    ctx = _context(_bids_dataset(tmp_path), ISSUES)
    channels = "sub-01/eeg/sub-01_task-rest_channels.tsv"
    description = "dataset_description.json"
    assert bids.measure_warnings(ctx) == [
        _failed(
            bids.WARNINGS, description, "JSON_KEY_RECOMMENDED", description, (description,), 1, {"License": 1}
        ),
        _failed(bids.WARNINGS, channels, "TSV_ADDITIONAL_COLUMNS_UNDEFINED", channels, (channels,), 1),
        _failed(bids.WARNINGS, VHDR, "EEG_CHANNEL_COUNT_MISMATCH", VHDR, _identity(VHDR, ".vhdr"), 1),
    ]


def test_hed_schema_issues_go_only_to_their_own_check(tmp_path: Path) -> None:
    ctx = _context(_bids_dataset(tmp_path), ISSUES)
    description = "dataset_description.json"
    schema = {"SCHEMA_LOAD_FAILED": 1}
    assert bids.measure_hed_schema(ctx) == [
        _failed(bids.HED_SCHEMA, "dataset", "HED_ERROR", None, (), 1, schema),
        _failed(bids.HED_SCHEMA, description, "HED_WARNING", description, (description,), 1, schema),
    ]
    others = bids.measure_errors(ctx) + bids.measure_warnings(ctx)
    assert not [m for m in others if "SCHEMA_LOAD_FAILED" in m.details.get("sub_codes", {})]
    assert not [m for m in others + bids.measure_hed_schema(ctx) if m.subkey == "README_FILE_MISSING"]


@pytest.mark.parametrize(
    ("issue", "check_id"),
    [
        (ValidatorIssue("HED_ERROR", "SCHEMA_LOAD_FAILED", "error", None), bids.HED_SCHEMA),
        (ValidatorIssue("HED_WARNING", "SCHEMA_LOAD_FAILED", "warning", None), bids.HED_SCHEMA),
        (ValidatorIssue("HED_ERROR", None, "error", None), bids.ERRORS),  # HED, but not about the schema
        (ValidatorIssue("HED_WARNING", "TAG_EXTENDED", "warning", None), bids.WARNINGS),
        # a malformed HEDVersion is reported by the JSON schema check as well: it stays a validator error
        (ValidatorIssue("JSON_SCHEMA_VALIDATION_ERROR", "HEDVersion", "error", None), bids.ERRORS),
        (ValidatorIssue("JSON_SCHEMA_VALIDATION_ERROR", "SchemaVersion", "error", None), bids.ERRORS),
    ],
)
def test_issue_goes_to_exactly_one_check(tmp_path: Path, issue: ValidatorIssue, check_id: str) -> None:
    ctx = _context(_bids_dataset(tmp_path), (issue,))
    sub_codes = {issue.sub_code: 1} if issue.sub_code else None
    for other, measure in bids.MEASURERS.items():
        expected = (
            [_failed(other, "dataset", issue.code, None, (), 1, sub_codes)]
            if other == check_id
            else [Measurement(check_id=other, object="dataset", value=True)]
        )
        assert measure(ctx) == expected, other


def test_no_issues_is_one_passing_dataset_measurement(tmp_path: Path) -> None:
    ctx = _context(_bids_dataset(tmp_path), (ValidatorIssue("README_FILE_MISSING", None, "ignore", None),))
    for check_id, measure in bids.MEASURERS.items():
        assert measure(ctx) == [Measurement(check_id=check_id, object="dataset", value=True)]


def test_raw_folders_are_not_validated() -> None:
    ctx = CheckContext.build(scan(FIX / "brainvision_ok"), Config(), work=None)  # no work folder: no run
    assert not ctx.scan.is_bids
    for check_id, measure in bids.MEASURERS.items():
        assert measure(ctx) == [
            Measurement(check_id=check_id, object="dataset", state="not_applicable", reason="bids.not_bids")
        ]
    for lang in ("zh", "en"):
        assert translator(lang, strict=True).t("reason.bids.not_bids")


def test_a_single_file_as_target_is_not_validated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A-66: a single file is checked like a raw folder with exactly this file. Verifier, review P2: a file at
    the root of a BIDS dataset made the validator check the whole folder, and through a junction there that
    discovery never listed ('extra/Mueller_Hans_1975' reached the results)."""
    root = _bids_dataset(tmp_path)
    gen_fixtures.write_edf(root / "single.edf", seconds=1)
    (tmp_path / "outside" / "Mueller_Hans_1975").mkdir(parents=True)
    dir_link(root / "extra", tmp_path / "outside")
    calls: list[Path] = []

    def fake_run(dataset: Path, work: Path) -> ValidatorResult:
        calls.append(dataset)
        return ValidatorResult(16, "1.2.7", (ValidatorIssue("NOT_INCLUDED", None, "error", "extra"),))

    monkeypatch.setattr(context_module, "run_validator", fake_run)
    found = scan(root, only=PurePosixPath("single.edf"))
    assert found.is_bids and found.single_file and not scan(root).single_file
    ctx = CheckContext.build(found, Config(), work=tmp_path / "work")
    for check_id, measure in bids.MEASURERS.items():
        assert measure(ctx) == [
            Measurement(check_id=check_id, object="dataset", state="not_applicable", reason="bids.not_bids")
        ]
    assert calls == []
    monkeypatch.undo()  # the whole pipeline with the real validator installed: it is not started either
    options = pipeline.CheckOptions(rulepacks=("core", "bids"), as_of=AS_OF, work_base=tmp_path / "base")
    results = pipeline.run_check(root / "single.edf", options)
    assert "Mueller" not in results.model_dump_json() and "extra" not in results.model_dump_json()
    bids_findings = [f for f in results.findings if f.rule_id.startswith("BIDS-")]
    assert len(bids_findings) == 3 and {f.status for f in bids_findings} == {Status.NOT_APPLICABLE}
    assert [r.id for r in results.recordings] == ["single.edf"]


def test_check_ids_and_evaluation() -> None:
    assert (
        set(bids.MEASURERS)
        == {spec.id for spec in bids.SPECS}
        == {
            "bids.validator_errors",
            "bids.validator_warnings",
            "bids.hed_schema_available",
        }
    )
    passing = Measurement(check_id=bids.ERRORS, object="dataset", value=True)
    failing = _failed(bids.ERRORS, "dataset", "SUBJECT_FOLDERS", None, (), 1)
    for spec in bids.SPECS:
        assert spec.evaluate(passing, {}).passed and not spec.evaluate(failing, {}).passed


def test_one_validator_run_per_check_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _bids_dataset(tmp_path)
    calls: list[tuple[Path, Path]] = []

    def fake_run(dataset: Path, work: Path) -> ValidatorResult:
        calls.append((dataset, work))
        return ValidatorResult(16, "1.2.7", ISSUES)

    monkeypatch.setattr(context_module, "run_validator", fake_run)
    ctx = CheckContext.build(scan(root), Config(), work=tmp_path / "work")
    for measure in bids.MEASURERS.values():
        measure(ctx)
    assert calls == [(ctx.root, tmp_path / "work" / "validator")]


def test_validator_needs_a_work_folder(tmp_path: Path) -> None:
    ctx = CheckContext.build(scan(_bids_dataset(tmp_path)), Config(), work=None)
    with pytest.raises(RuntimeError, match="needs a work folder"):
        bids.measure_errors(ctx)


def test_issue_on_a_recording_stays_with_that_recording(tmp_path: Path) -> None:
    root = _bids_dataset(tmp_path)
    edf = "sub-01/eeg/sub-01_task-rest_eeg.edf"
    gen_fixtures.write_edf(root / edf, seconds=1)
    ctx = _context(root, (ValidatorIssue("EMPTY_FILE", None, "error", edf),))
    assert {rec.object_id for rec in ctx.recordings} >= {edf, VHDR}
    (measurement,) = bids.measure_errors(ctx)
    assert (measurement.object, measurement.file) == (edf, edf)


def test_issue_on_the_sidecar_of_a_recording_stays_with_the_sidecar(tmp_path: Path) -> None:
    """The real validator reports a malformed sidecar as JSON_INVALID at the sidecar's own location; the
    finding must point there, not to the BrainVision header the user would then search in vain."""
    root = _bids_dataset(tmp_path)
    sidecar = "sub-01/eeg/sub-01_task-rest_eeg.json"
    (root / sidecar).write_text(json.dumps({"TaskName": "rest"}), encoding="utf-8")
    ctx = _context(root, (ValidatorIssue("JSON_INVALID", None, "error", sidecar),))
    assert bids.measure_errors(ctx) == [_failed(bids.ERRORS, sidecar, "JSON_INVALID", sidecar, (sidecar,), 1)]


def test_issues_at_or_behind_a_skipped_link_are_dropped(tmp_path: Path) -> None:
    """A-66, review P2: the validator lists what lies behind a junction; those issues (and the outside names
    in their locations) are dropped, the links_skipped notice covers them. Other issues stay."""
    root = _bids_dataset(tmp_path)
    outside = tmp_path / "outside"
    (outside / "Mueller_Hans_1975").mkdir(parents=True)
    dir_link(root / "extra", outside)
    dir_link(root / "sub-01" / "eeg" / "linked", outside)
    issues = (
        ValidatorIssue("NOT_INCLUDED", None, "error", "extra"),
        ValidatorIssue("NOT_INCLUDED", None, "error", "extra/Mueller_Hans_1975"),
        ValidatorIssue("INVALID_LOCATION", None, "error", "sub-01/eeg/linked/sub-07_task-rest_eeg.edf"),
        ValidatorIssue("SIDECAR_KEY_RECOMMENDED", "TaskName", "warning", "sub-01/eeg/linked/x_eeg.edf"),
        ValidatorIssue("NOT_INCLUDED", None, "error", "extra2"),  # starts like the link, but is no part of it
        ValidatorIssue("NOT_INCLUDED", None, "error", "notes.txt"),
        ValidatorIssue("SUBJECT_FOLDERS", None, "error", None),
    )
    ctx = _context(root, issues)
    assert ctx.scan.skipped_links == [PurePosixPath("extra"), PurePosixPath("sub-01/eeg/linked")]
    assert bids.measure_errors(ctx) == [
        _failed(bids.ERRORS, "dataset", "SUBJECT_FOLDERS", None, (), 1),
        _failed(bids.ERRORS, "extra2", "NOT_INCLUDED", "extra2", ("extra2",), 1),
        _failed(bids.ERRORS, "notes.txt", "NOT_INCLUDED", "notes.txt", ("notes.txt",), 1),
    ]
    assert bids.measure_warnings(ctx) == [Measurement(check_id=bids.WARNINGS, object="dataset", value=True)]


def test_link_names_that_are_not_unicode_match_the_validator_spelling(tmp_path: Path) -> None:
    """A link name with undecodable bytes is a surrogate escape here and U+FFFD in the validator's output."""
    ctx = _context(
        _bids_dataset(tmp_path),
        (
            ValidatorIssue("NOT_INCLUDED", None, "error", "M\ufffdller/secret.txt"),
            ValidatorIssue("NOT_INCLUDED", None, "error", "M\ufffd\ufffdller"),
            ValidatorIssue("NOT_INCLUDED", None, "error", "Muller"),
        ),
    )
    ctx.scan.skipped_links.append(PurePosixPath("M\udcfcller"))  # os.walk on Linux for the Latin-1 byte 0xFC
    assert bids.measure_errors(ctx) == [
        _failed(bids.ERRORS, "Muller", "NOT_INCLUDED", "Muller", ("Muller",), 1)
    ]


# --- the check pipeline and the report on a real run (A-06, A-07, A-54) -----------------------------------


@pytest.fixture(scope="module")
def issues_results(tmp_path_factory: pytest.TempPathFactory) -> tuple[Results, Path]:
    base = tmp_path_factory.mktemp("work-base")
    options = pipeline.CheckOptions(rulepacks=("bids",), as_of=AS_OF, work_base=base)
    return pipeline.run_check(FIX / "bids_issues", options), base


def _validator_texts(work: Path) -> list[str]:
    """Lines of the validator's own English messages from a real result file (long enough to be specific)."""
    data = json.loads((work / "validator.json").read_text(encoding="utf-8"))
    messages = [item.get("issueMessage", "") for item in data["issues"]["issues"]]
    messages += [str(text) for text in data["issues"].get("codeMessages", {}).values()]
    return sorted(
        {line.strip() for text in messages for line in text.splitlines() if len(line.strip()) >= 25}
    )


def test_pipeline_turns_issues_into_findings_with_subkeys(
    issues_results: tuple[Results, Path], real_runs: dict[str, tuple[ValidatorResult, Path]]
) -> None:
    results, base = issues_results
    assert list(base.iterdir()) == []  # the run's work folder with the validator output is removed (A-54)
    bids_findings = [f for f in results.findings if f.rule_id.startswith("BIDS-")]
    assert {f.status for f in bids_findings} == {Status.FAILED}
    failed: dict[str, dict[tuple[str, str | None], Finding]] = {}
    for f in bids_findings:
        failed.setdefault(f.rule_id, {})[(f.object, f.subkey)] = f
    # validator errors -> BIDS-STO-001 (error); the unavailable HED schema only -> BIDS-STO-003 (A-06, A-77)
    assert set(failed["BIDS-STO-001"]) == {(EDF_01, "SIDECAR_KEY_REQUIRED")}
    assert set(failed["BIDS-STO-003"]) == {("dataset", "HED_ERROR")}
    error = failed["BIDS-STO-001"][(EDF_01, "SIDECAR_KEY_REQUIRED")]
    assert (error.severity, error.file) == (Severity.ERROR, EDF_01)
    assert error.details == {
        "validator_code": "SIDECAR_KEY_REQUIRED",
        "count": 1,
        "sub_codes": {"EEGReference": 1},
    }
    hed = failed["BIDS-STO-003"][("dataset", "HED_ERROR")]
    assert (hed.severity, hed.file) == (Severity.WARNING, None)
    assert hed.details == {"validator_code": "HED_ERROR", "count": 1, "sub_codes": {"SCHEMA_LOAD_FAILED": 1}}
    # validator warnings -> BIDS-STO-002 (warning): one finding per object and code (A-06, A-77) with the
    # total count and the count per sub-code
    warnings: dict[tuple[str, str], Counter[str | None]] = {}
    for i in real_runs["bids_issues"][0].issues:
        if i.severity == "warning":
            warnings.setdefault((i.location or "dataset", i.code), Counter())[i.sub_code or None] += 1
    assert len(warnings) == 9  # the nine (code, location) pairs of test_real_run_on_a_dataset_with_issues
    assert sum(sum(c.values()) for c in warnings.values()) >= 50  # many issues, few findings
    assert set(failed["BIDS-STO-002"]) == set(warnings)
    for (obj, code), per_sub_code in warnings.items():
        finding = failed["BIDS-STO-002"][(obj, code)]
        assert finding.severity is Severity.WARNING
        assert finding.file == (None if obj == "dataset" else obj)
        expected: dict[str, Any] = {"validator_code": code, "count": sum(per_sub_code.values())}
        named = {sub: n for sub, n in per_sub_code.items() if sub is not None}
        if named:
            expected["sub_codes"] = dict(sorted(named.items()))
        assert finding.details == expected
    recommended = failed["BIDS-STO-002"][(EDF_01, "SIDECAR_KEY_RECOMMENDED")]
    assert recommended.details["count"] >= 2 and set(recommended.details["sub_codes"]) >= {"Manufacturer"}


def test_exception_for_a_validator_code_covers_every_sub_code(tmp_path: Path) -> None:
    """Review P2: an exception with subkey = validator code (A-06, A-14) must take effect. Before the fix the
    subkeys were CODE/subCode, so this exception stayed unused and three findings remained."""
    root = tmp_path / "ds"
    shutil.copytree(FIX / "bids_ok", root)
    sidecar = root / "sub-01" / "eeg" / "sub-01_task-rest_eeg.json"
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    for key in ("CapManufacturer", "EEGGround", "Manufacturer"):
        assert data.pop(key, None) is not None, key
    sidecar.write_text(json.dumps(data), encoding="utf-8")
    toml = tmp_path / "neurogrid.toml"
    toml.write_text(
        '[[exceptions]]\nrule = "BIDS-STO-002"\nsubkey = "SIDECAR_KEY_RECOMMENDED"\n'
        'reason = "Recommended keys are not collected in this project."\n',
        encoding="utf-8",
    )
    options = pipeline.CheckOptions(rulepacks=("bids",), config_path=toml, as_of=AS_OF, work_base=tmp_path)
    results = pipeline.run_check(root, options)
    (finding,) = [f for f in results.findings if f.rule_id == "BIDS-STO-002"]
    assert (finding.object, finding.subkey, finding.status) == (
        EDF_01,
        "SIDECAR_KEY_RECOMMENDED",
        Status.EXCEPTED,
    )
    assert finding.details == {
        "validator_code": "SIDECAR_KEY_RECOMMENDED",
        "count": 3,
        "sub_codes": {"CapManufacturer": 1, "EEGGround": 1, "Manufacturer": 1},
        "exception_reason": "Recommended keys are not collected in this project.",
    }
    assert [(use.entry.subkey, use.used) for use in results.exceptions] == [("SIDECAR_KEY_RECOMMENDED", True)]


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_report_shows_neurogrid_texts_never_the_validator_messages(
    issues_results: tuple[Results, Path], real_runs: dict[str, tuple[ValidatorResult, Path]], lang: str
) -> None:
    results, _base = issues_results
    html = render_report(results, lang)
    for code in ("SIDECAR_KEY_REQUIRED", "HED_ERROR", "README_FILE_MISSING"):
        own = validator_text(code, lang)
        assert own is not None, code
        assert str(escape(own)) in html, code
    serialized = results.model_dump_json()
    foreign = _validator_texts(real_runs["bids_issues"][1])
    assert len(foreign) >= 5
    for line in foreign:
        assert line not in html and str(escape(line)) not in html, line
        assert line not in serialized, line


# --- validator_codes.yaml (A-06) -------------------------------------------------------------------------


def test_code_table_covers_every_code_of_the_installed_validator(bundle_text: str) -> None:
    listed = _issue_list_codes(bundle_text)
    schema = _schema_codes(bundle_text)
    # exact counts for the pinned bundle 3.0.2: a parser that silently found fewer codes would fail here
    assert len(listed) == 52 and {"HED_ERROR", "HED_WARNING", "SIDECAR_KEY_REQUIRED"} <= listed
    assert len(schema) == 130 and "EEG_CHANNEL_COUNT_MISMATCH" in schema
    assert DYNAMIC_CODES <= listed
    missing = sorted((listed | schema | DYNAMIC_CODES) - set(validator_codes()))
    assert missing == []


def test_every_code_in_the_table_exists_in_the_bundle(bundle_text: str) -> None:
    emitted = set(re.findall(r'\bcode(?:: | = )"([A-Z][A-Z0-9_]*)"', bundle_text))
    known = _issue_list_codes(bundle_text) | _schema_codes(bundle_text) | emitted
    unknown = sorted(set(validator_codes()) - known)
    assert unknown == []


def test_code_table_entries_have_exactly_four_one_line_fields() -> None:
    raw_text = texts.VALIDATOR_CODES.read_text(encoding="utf-8")
    data = load_yaml(raw_text)
    assert isinstance(data, dict) and len(data) >= 180
    for code, entry in data.items():
        assert re.fullmatch(r"[A-Z][A-Z0-9_]*", code), code
        assert isinstance(entry, dict) and set(entry) == {"category", "en", "zh", "de"}, code
        assert entry["category"] in CATEGORIES, code
        for lang in ("en", "zh", "de"):
            text = entry[lang]
            assert isinstance(text, str) and text.strip() == text and len(text) >= 10, (code, lang)
            assert not re.search(r"[\r\n{}<>]", text), (code, lang)
        assert re.search(r"[\u4e00-\u9fff]", entry["zh"]), code  # the zh text is Chinese
        assert entry["zh"] != entry["en"] and entry["de"] != entry["en"], code
    # one physical line per field: a quoted scalar that closes on the same line
    fields = re.findall(r'^  (category|en|zh|de): "[^"\n]*"$', raw_text, flags=re.MULTILINE)
    assert len(fields) == 4 * len(data)
    assert "\r" not in raw_text


def test_english_texts_are_not_the_validator_messages(bundle_text: str) -> None:
    """A-06: the validator's English text never appears; NeuroGrid's text neither repeats nor contains it,
    and is not a fragment of it either. Every message of a code is compared, not only the last one."""
    messages = _bundle_messages(bundle_text)
    assert len(messages) == 176 and len({code for code, _ in messages}) == 169
    table = validator_codes()
    assert {code for code, _ in messages} <= set(table)
    copied = sorted(
        code
        for code, message in messages
        if message.strip(" .") in _plain(table[code]["en"])
        or _plain(table[code]["en"]).strip(" .") in message
    )
    assert copied == []


def test_validator_text_lookup() -> None:
    entry = validator_codes()["SIDECAR_KEY_REQUIRED"]
    assert validator_text("SIDECAR_KEY_REQUIRED", "en") == entry["en"]
    assert validator_text("SIDECAR_KEY_REQUIRED", "zh") == entry["zh"]
    assert validator_text("SIDECAR_KEY_REQUIRED", "de") == entry["de"]
    assert validator_text("NOT_A_VALIDATOR_CODE", "en") is None
    assert validator_text("SIDECAR_KEY_REQUIRED", "fr") is None


def test_code_table_must_be_a_mapping(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    broken = tmp_path / "validator_codes.yaml"
    broken.write_text("- SIDECAR_KEY_REQUIRED\n", encoding="utf-8")
    monkeypatch.setattr(texts, "VALIDATOR_CODES", broken)
    texts.validator_codes.cache_clear()
    try:
        with pytest.raises(TypeError):
            texts.validator_codes()
    finally:
        monkeypatch.undo()
        texts.validator_codes.cache_clear()
    assert "SIDECAR_KEY_REQUIRED" in texts.validator_codes()


# --- _Formatter.details for validator findings (A-06, A-07) ---------------------------------------------


def _finding(details: dict[str, Any]) -> Finding:
    return Finding(
        key="0123456789abcdef",
        rule_id="BIDS-STO-001",
        rulepack="bids",
        rulepack_version="0.1.0",
        source_status=SourceStatus.SECONDARY,
        clause="BIDS 1.11.1",
        phase=Phase.STORAGE,
        severity=Severity.ERROR,
        status=Status.FAILED,
        object="sub-01/eeg/sub-01_task-rest_eeg.edf",
        subkey="SIDECAR_KEY_REQUIRED",
        file="sub-01/eeg/sub-01_task-rest_eeg.edf",
        details=details,
        message_key="check.bids.validator_errors",
    )


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_details_show_the_neurogrid_text_for_a_known_code(lang: str, bundle_text: str) -> None:
    text = _Formatter(lang).details(_finding({"validator_code": "SIDECAR_KEY_REQUIRED", "count": 1}))
    assert text == validator_codes()["SIDECAR_KEY_REQUIRED"][lang]
    foreign = [message for code, message in _bundle_messages(bundle_text) if code == "SIDECAR_KEY_REQUIRED"]
    assert len(foreign) == 1 and foreign[0] not in _plain(text)


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_details_add_the_count_when_an_issue_occurs_more_than_once(lang: str) -> None:
    tr = translator(lang, strict=True).t
    own = validator_codes()["SIDECAR_KEY_REQUIRED"][lang]
    count_text = tr("report.validator.count", count=3)
    assert "3" in count_text and "{" not in count_text
    text = _Formatter(lang).details(_finding({"validator_code": "SIDECAR_KEY_REQUIRED", "count": 3}))
    assert text == f"{own} {count_text}"


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_details_use_the_generic_text_for_an_unknown_code(lang: str) -> None:
    tr = translator(lang, strict=True).t
    generic = tr("report.validator.generic", code="FUTURE_CODE")
    assert "FUTURE_CODE" in generic
    assert _Formatter(lang).details(_finding({"validator_code": "FUTURE_CODE", "count": 1})) == generic
    many = _Formatter(lang).details(_finding({"validator_code": "FUTURE_CODE", "count": 2}))
    assert many == f"{generic} {tr('report.validator.count', count=2)}"


def test_generic_texts_differ_per_language() -> None:
    zh = translator("zh", strict=True).t("report.validator.generic", code="X")
    en = translator("en", strict=True).t("report.validator.generic", code="X")
    assert zh != en and re.search(r"[\u4e00-\u9fff]", zh)


@pytest.mark.parametrize("count", [None, 0, 1, "5", 2.0, True])
def test_details_omit_the_count_unless_it_is_an_integer_above_one(count: object) -> None:
    details: dict[str, Any] = {"validator_code": "SIDECAR_KEY_REQUIRED"}
    if count is not None:
        details["count"] = count
    assert _Formatter("en").details(_finding(details)) == validator_codes()["SIDECAR_KEY_REQUIRED"]["en"]


def test_details_without_validator_code_show_no_validator_text() -> None:
    assert _Formatter("en").details(_finding({})) == translator("en").t("report.value.none")


# --- kernel.safety.work_directory (A-54) -----------------------------------------------------------------


def test_work_directory_where_a_file_is_in_the_way(tmp_path: Path) -> None:
    blocker = tmp_path / "out"
    blocker.write_text("a file, not a folder", encoding="utf-8")
    for base in (blocker, blocker / "nested"):
        with pytest.raises(InputError) as info, work_directory(base):
            pytest.fail("the block must not run")
        assert info.value.message_key == "output.not_writable"
        assert info.value.__suppress_context__
    assert blocker.read_text(encoding="utf-8") == "a file, not a folder"


def test_work_folder_that_cannot_be_created_in_an_existing_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The base exists, but the run folder cannot be made in it (e.g. no permission)."""

    def refuse(*args: object, **kwargs: object) -> str:
        raise PermissionError(13, "denied")

    monkeypatch.setattr(tempfile, "mkdtemp", refuse)
    with pytest.raises(InputError) as info, work_directory(tmp_path):
        pytest.fail("the block must not run")
    assert info.value.message_key == "output.not_writable" and info.value.__suppress_context__
    assert list(tmp_path.iterdir()) == []


def test_check_ends_like_an_unwritable_output_when_the_work_folder_is_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A-77/A-54: no work folder next to the output -> output.not_writable (exit 2); deno is never started."""
    calls: list[tuple[Path, Path]] = []

    def fake_run(dataset: Path, work: Path) -> ValidatorResult:
        calls.append((dataset, work))
        return ValidatorResult(0, "1.2.7", ())

    monkeypatch.setattr(context_module, "run_validator", fake_run)
    blocker = tmp_path / "out"
    blocker.write_text("a file, not a folder", encoding="utf-8")
    options = pipeline.CheckOptions(rulepacks=("bids",), as_of=AS_OF, work_base=blocker / "work")
    with pytest.raises(InputError) as info:
        pipeline.run_check(FIX / "bids_ok", options)
    assert info.value.message_key == "output.not_writable" and calls == []
    for lang in ("zh", "en"):
        assert translator(lang, strict=True).t("errors.output.not_writable")


def test_work_directory_is_private_and_removed_after_an_error(tmp_path: Path) -> None:
    base = tmp_path / "out" / ".work"  # created with its parents
    with pytest.raises(RuntimeError, match="boom"), work_directory(base) as path:
        kept = path
        (path / "deno").mkdir()
        (path / "deno" / "cache").write_bytes(b"x")
        (path / "validator.json").write_text("{}", encoding="utf-8")
        raise RuntimeError("boom")
    assert kept.parent == base and kept.name.startswith("run-")
    assert not kept.exists() and base.is_dir()


def test_errors_inside_the_block_are_not_turned_into_output_errors(tmp_path: Path) -> None:
    with pytest.raises(PermissionError), work_directory(tmp_path / "w") as path:
        kept = path
        raise PermissionError(13, "denied inside the run")
    assert not kept.exists()


def test_each_run_gets_its_own_work_folder(tmp_path: Path) -> None:
    with work_directory(tmp_path) as first, work_directory(tmp_path) as second:
        assert first != second and first.is_dir() and second.is_dir()
    assert not first.exists() and not second.exists()
    assert list(tmp_path.iterdir()) == []
