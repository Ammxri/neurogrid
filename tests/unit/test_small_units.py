"""Focused tests for helpers that the end-to-end tests reach only partially."""

from __future__ import annotations

import hashlib
import socket
from datetime import date
from pathlib import Path

import pytest

from neurogrid import pipeline
from neurogrid.kernel import netguard
from neurogrid.kernel.errors import NetworkBlockedError
from neurogrid.kernel.findings import Finding, Phase, Severity, SourceStatus, Status, TimeRange
from neurogrid.kernel.provenance import sha256_file, sha256_text
from neurogrid.report.render import _Formatter

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"


class _Sock:
    def __init__(self, family: int) -> None:
        self.family = family


def test_netguard_hook_directly() -> None:
    netguard._hook("open", ("file",))
    netguard._hook("socket.sendmsg", (_Sock(socket.AF_INET), None))  # connected socket, checked at connect
    netguard._hook("socket.gethostbyname", ("localhost",))
    netguard._hook("socket.getnameinfo", (("127.0.0.1", 80), 0))
    netguard._hook("socket.connect", (_Sock(socket.AF_INET), ("127.0.0.1", 80)))
    netguard._hook("socket.sendto", (_Sock(socket.AF_INET6), ("::1", 53, 0, 0)))
    netguard._hook("socket.getaddrinfo", ("localhost", 80, 0, 0, 0))
    if hasattr(socket, "AF_UNIX"):
        netguard._hook("socket.connect", (_Sock(socket.AF_UNIX), "/tmp/x.sock"))
    for event, args in (
        ("socket.connect", (_Sock(socket.AF_INET), ("8.8.8.8", 53))),
        ("socket.sendto", (_Sock(socket.AF_INET), ("example.org", 53))),
        ("socket.getaddrinfo", (b"example.org", 80, 0, 0, 0)),
        ("socket.connect", (_Sock(socket.AF_INET6), ("2001:db8::1", 443, 0, 0))),
        ("socket.sendmsg", (_Sock(socket.AF_INET), ("192.0.2.1", 53))),
        ("socket.gethostbyname", ("example.org",)),
        ("socket.gethostbyaddr", ("8.8.8.8",)),
        ("socket.getnameinfo", (("8.8.8.8", 53), 0)),
    ):
        with pytest.raises(NetworkBlockedError):
            netguard._hook(event, args)
    assert (
        netguard._is_local("::ffff:127.0.0.1")
        and netguard._is_local("[::1]")
        and not netguard._is_local("10.0.0.1")
    )
    assert netguard._host_of("name") == "name" and netguard._host_of(42) is None


def test_hashes(tmp_path: Path) -> None:
    path = tmp_path / "f.bin"
    path.write_bytes(b"neurogrid" * 1000)
    assert sha256_file(path) == hashlib.sha256(b"neurogrid" * 1000).hexdigest()
    assert sha256_text("ä") == hashlib.sha256("ä".encode()).hexdigest()


def test_combined_sampling_rate_check_from_prd_example(tmp_path: Path) -> None:
    pack = tmp_path / "example.yaml"
    pack.write_text(
        """rulepack: example
version: "0.2.0-draft"
source: "PRD example"
source_status: final
rules:
  - id: EXAMPLE-ACQ-001
    clause: "TBD"
    title_zh: 采样频率记录且一致
    title_en: Sampling rate documented and consistent
    phase: acquisition
    check: signal.sampling_rate_consistency
    params: {min_hz: 500}
    severity: error
    verification: automatic
""",
        encoding="utf-8",
    )
    options = pipeline.CheckOptions(rulepacks=(str(pack),), as_of=date(2026, 10, 11))
    ok = pipeline.run_check(FIX / "edf_ok", options)
    assert not [f for f in ok.findings if f.rule_id == "EXAMPLE-ACQ-001"]
    mixed = pipeline.run_check(FIX / "edf_mixed", options)
    assert {f.status for f in mixed.findings if f.rule_id == "EXAMPLE-ACQ-001"} == {Status.FAILED}
    empty = pipeline.run_check(FIX / "empty", options)
    assert not [f for f in empty.findings if f.rule_id == "EXAMPLE-ACQ-001"]


def test_rate_checks_not_checkable_without_eeg(tmp_path: Path) -> None:
    import gen_fixtures  # type: ignore[import-not-found]

    folder = tmp_path / "ecg_only"
    gen_fixtures.write_edf(folder / "ecg.edf", labels=("ECG",), label_prefix="")
    results = pipeline.run_check(folder, pipeline.CheckOptions(as_of=date(2026, 10, 11)))
    reasons = {(f.rule_id, f.status, f.reason) for f in results.findings}
    assert ("CORE-M03-01", Status.NOT_CHECKABLE, "signal.no_eeg_channels") in reasons


def test_header_without_valid_rate_is_not_checkable_and_never_exit_2(tmp_path: Path) -> None:
    """A-12, A-60, A-61: a broken header is a finding, the run still writes results."""
    folder = tmp_path / "broken"
    folder.mkdir()
    for name, value in (("nan.edf", b"nan     "), ("inf.edf", b"1e400   ")):
        data = bytearray((FIX / "edf_ok" / "rec_a.edf").read_bytes())
        data[244:252] = value
        (folder / name).write_bytes(bytes(data))
    (folder / "good.edf").write_bytes((FIX / "edf_ok" / "rec_a.edf").read_bytes())
    results = pipeline.run_check(folder, pipeline.CheckOptions(as_of=date(2026, 10, 11)))
    rate = [f for f in results.findings if f.rule_id == "CORE-M03-01"]
    assert {(f.status, f.reason) for f in rate} == {(Status.NOT_CHECKABLE, "signal.rate_unknown")}
    header = [f for f in results.findings if f.rule_id == "CORE-M01-02"]
    assert len(header) == 2 and all("header.record_duration" in f.details["issues"] for f in header)
    assert results.summary.exit_code == 1


def test_engine_treats_non_finite_values_as_not_checkable() -> None:
    from neurogrid.checks.registry import REGISTRY
    from neurogrid.kernel import engine
    from neurogrid.kernel.rules import Measurement

    pack = pipeline.load_rulepack_ref("core")
    measurements = {
        "signal.sampling_rate_min": [
            Measurement(check_id="signal.sampling_rate_min", object="r", value=float("nan"))
        ]
    }
    result = engine.run(
        engine.EngineInput(
            packs=[pack], registry=REGISTRY, measurements=measurements, as_of=date(2026, 10, 11)
        )
    )
    finding = next(f for f in result.findings if f.rule_id == "CORE-M03-01")
    assert finding.status is Status.NOT_CHECKABLE and finding.reason == "value.non_finite"
    assert finding.measured_value is None


def _finding(**overrides: object) -> Finding:
    data: dict[str, object] = {
        "key": "k",
        "rule_id": "R-1",
        "rulepack": "p",
        "rulepack_version": "1",
        "source_status": SourceStatus.FINAL,
        "clause": "4.1",
        "phase": Phase.ACQUISITION,
        "severity": Severity.ERROR,
        "status": Status.FAILED,
        "object": "rec-1",
        "file": "rec-1.edf",
        "message_key": "check.signal.sampling_rate_min",
    }
    data.update(overrides)
    return Finding(**data)  # type: ignore[arg-type]


def test_report_formatter() -> None:
    fmt = _Formatter("en", recordings=frozenset({"rec-1"}))
    assert fmt.value(None) == "–" and fmt.value(True) == "yes" and fmt.value(False) == "no"
    assert fmt.value(0.123456789) == "0.123457" and fmt.value({"b": 1, "a": [1]}) == "a: 1; b: 1"
    measured = fmt.value({"rates_hz": [256.0, 512.0], "documented": False})
    assert measured == "documented: no; rates (Hz): 256, 512"  # translated labels, no raw JSON
    assert fmt.measured(_finding(status=Status.EVIDENCE_OPEN)) == "– (not measured for this rule)"
    placeholder = _finding(source_status=SourceStatus.PLACEHOLDER)
    assert fmt.clause(placeholder) == "placeholder – not from the norm text"  # A-41
    assert fmt.status(placeholder) == "not evaluated (placeholder rule)"  # no verdict (KONZEPT §3)
    assert fmt.status(_finding()) == "not passed"
    ranges = [TimeRange(start_s=float(i), end_s=i + 0.5) for i in range(22)]
    text = fmt.time_range(_finding(time_ranges=ranges[:21], time_ranges_total=25))
    # P5 (A-10): at most 20 ranges, then their number (and the total duration when results.json has it)
    assert text.endswith("(20 of 25 ranges)") and "0.000–0.500 s" in text and "19.000–19.500 s" in text
    assert "20.000–20.500 s" not in text
    timed = fmt.time_range(
        _finding(time_ranges=ranges[:21], time_ranges_total=25, time_ranges_duration_s=12.5)
    )
    assert timed.endswith("(20 of 25 ranges; total 12.5 s)")
    both = fmt.time_range(_finding(time_ranges=ranges[:2], time_ranges_total=2, time_ranges_duration_s=1.0))
    assert both == "0.000–0.500 s, 1.000–1.500 s (total 1 s)"
    assert fmt.time_range(_finding(file=None)) == "– (dataset-wide check, no time range)"  # A-10
    assert fmt.time_range(_finding()) == "whole recording"  # rec-1 is a recording of the results
    # a file that is no recording: a control file or a new file in the manifest comparison (A-10, A-82)
    control = _finding(object=".neurogrid/neurogrid.toml", file=".neurogrid/neurogrid.toml")
    assert fmt.time_range(control) == "whole file"
    assert fmt.time_range(_finding(object="rec-2", file="rec-2.txt")) == "whole file"
    assert _Formatter("zh").time_range(control) == "整个文件"
    assert _Formatter("de").time_range(control) == "gesamte Datei"
    detail = fmt.details(
        _finding(
            reason="read.failed",
            details={
                "issues": ["header.size_field"],
                "fields": ["patient"],
                "error_type": "ValueError",
                "exception_reason": "SOP-1",
            },
        )
    )
    assert (
        "could not be read" in detail
        and "patient field" in detail
        and "ValueError" in detail
        and "SOP-1" in detail
    )
    assert fmt.details(_finding()) == "–"
    translated = fmt.details(_finding(reason="read.failed", details={"issue": "header.bad_signal_count"}))
    assert "Invalid number of signals." in translated and "header.bad_signal_count" not in translated


def test_translator_never_formats_unknown_keys() -> None:
    from neurogrid.report.texts import translator

    tr = translator("en").t
    for key in ("issue.{", "issue.{0}", "issue.{a.__class__.__mro__}", "issue.{x:>500000000}"):
        assert tr(key, x=1) == key


def test_glob_matcher_stays_fast_on_hostile_patterns() -> None:
    import time

    from neurogrid.kernel.glob import match

    path = "/".join(["a"] * 40)
    start = time.perf_counter()
    assert not match("/".join(["**"] * 169) + "/nomatch", path)
    assert not match("**/*/" * 50 + "x", path)
    assert time.perf_counter() - start < 1.0
    assert match("sub-07/**", "sub-07/eeg/x.edf") and match("a/**/b", "a/b") and not match("a/*/b", "a/b")


def test_dataset_level_rate_reason_when_eeg_has_no_rate(tmp_path: Path) -> None:
    folder = tmp_path / "norate"
    folder.mkdir()
    data = bytearray((FIX / "edf_ok" / "rec_a.edf").read_bytes())
    data[244:252] = b"nan     "
    (folder / "r.edf").write_bytes(bytes(data))
    results = pipeline.run_check(folder, pipeline.CheckOptions(as_of=date(2026, 10, 11)))
    uniform = next(f for f in results.findings if f.rule_id == "CORE-M03-02")
    assert uniform.status is Status.NOT_CHECKABLE and uniform.reason == "signal.rate_unknown"


def test_commit_id_tool_entries_and_message_file(tmp_path: Path) -> None:
    import check_commit_ids  # type: ignore[import-not-found]

    text = (
        "### 2026-10-11 – Phase 2\n- planning, no IDs\n"
        "### 2026-10-12 – P1 Gerüst\n- closes TECH-02\n"
        "### 2026-10-13 – Wartung\n- nothing\n"
    )
    entries = check_commit_ids.phase_entries(text)
    assert [heading for heading, _body in entries] == [
        "### 2026-10-12 – P1 Gerüst",
        "### 2026-10-13 – Wartung",
    ]
    known = check_commit_ids.matrix_ids()
    assert (
        check_commit_ids.expand(entries[0][1]) & known and not check_commit_ids.expand(entries[1][1]) & known
    )


def test_commit_message_cleanup(tmp_path: Path) -> None:
    import subprocess
    import sys

    import check_commit_ids  # type: ignore[import-not-found]

    scissors = "# ------------------------ >8 ------------------------"
    message = f"# Please enter...\n# NG-F01 in a comment\n\n{scissors}\nTECH-02\n"
    assert check_commit_ids.clean_message(message) == ""
    assert check_commit_ids.first_line("") == "(empty message)"
    tool = Path(__file__).parent.parent.parent / "tools" / "check_commit_ids.py"
    for text, expected in (("", 1), (message, 1), ("feat: P1 (TECH-02)\n", 0)):
        path = tmp_path / "msg.txt"
        path.write_text(text, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(tool), "--no-history", "--message-file", str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        assert result.returncode == expected, result.stdout
