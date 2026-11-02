"""The hash-chained access log (NV-F03, DM-09, A-30, A-90; p6 decisions 3): the hash rule with its test
vector, appending under the lock, the content-based reader and the verifier with its honest limits."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
import time
import tracemalloc
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from vault_processes import lock_held  # type: ignore[import-not-found]

from conftest import dir_link  # type: ignore[import-not-found]
from neurogrid.kernel import canonical
from neurogrid.kernel.errors import InputError, NeuroGridError, UnsafePathError
from neurogrid.kernel.provenance import VAULT_LOG
from neurogrid.model.access import AccessEvent
from neurogrid.vault import _os, ledger
from neurogrid.vault.ledger import (
    GENESIS,
    MAX_LINE_BYTES,
    AppendOutcome,
    Deviation,
    append,
    append_locked,
    event_hash,
    verify,
)
from neurogrid.vault.lock import VaultLocked, exclusive
from neurogrid.vault.store import VaultLocation, init_vault, locate

# The test vector of the hash rule (also in docs/<lang>/vault.md): a fixed event and its hash.
VECTOR = {
    "format_version": 1,
    "seq": 1,
    "time": "2026-10-29T12:00:00Z",
    "role": "data_steward",
    "action": "check",
    "objects": ["**"],
    "purpose": "pre-check before registration",
    "approval_ref": "EC-2026-17",
    "tool_version": "0.2.0",
    "previous_hash": GENESIS,
}
VECTOR_HASH = "d4eddd3715aa9f571840e293fb40e696bc3dbbf4964dcf267b39b9fa27ec2670"
FIXED = datetime(2026, 10, 29, 12, 0, 0, tzinfo=UTC)


def now() -> datetime:
    return FIXED


def body(seq: int, previous: str, **changes: Any) -> dict[str, Any]:
    data = {**VECTOR, "seq": seq, "previous_hash": previous, **changes}
    data["hash"] = event_hash(data)
    return data


def chain(count: int, **changes: Any) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    previous = GENESIS
    for seq in range(1, count + 1):
        events.append(body(seq, previous, **changes))
        previous = events[-1]["hash"]
    return events


def line(event: dict[str, Any]) -> bytes:
    return ledger.compact_event(event) + b"\n"


def vault(
    tmp_path: Path, events: list[dict[str, Any]] | None = None, raw: bytes | None = None
) -> VaultLocation:
    tmp_path.mkdir(parents=True, exist_ok=True)
    location = locate(tmp_path, ".neurogrid/vault")
    init_vault(location)
    if raw is not None:
        location.log.write_bytes(raw)
    elif events is not None:
        location.log.write_bytes(b"".join(map(line, events)))
    return location.refreshed()


def deviations(location: VaultLocation, heads: tuple[str, ...] = ()) -> list[tuple[Any, ...]]:
    return [(d.line, d.kind, d.likely, d.problem) for d in verify(location, heads).deviations]


def append_check(location: VaultLocation, **changes: Any) -> AppendOutcome:
    fields: dict[str, Any] = {
        "role": "data_steward",
        "action": "check",
        "objects": ["**"],
        "purpose": None,
        "approval_ref": None,
        "now": now,
        **changes,
    }
    return append(location, **fields)


# --- hash rule ---------------------------------------------------------------------------------------------


def test_hash_test_vector() -> None:
    """The fixed event has a fixed hash; the snippet in docs/<lang>/vault.md recomputes it with the
    standard library alone (sorted keys, no white space, UTF-8, the event without 'hash')."""
    stdlib = hashlib.sha256(
        json.dumps(VECTOR, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    assert event_hash(VECTOR) == stdlib == VECTOR_HASH


def test_hash_excludes_hash_field_and_is_key_order_independent() -> None:
    reordered = dict(reversed(list(VECTOR.items())))
    assert event_hash(reordered) == event_hash(VECTOR) == event_hash({**VECTOR, "hash": "f" * 64})
    assert event_hash({**VECTOR, "seq": 2}) != event_hash(VECTOR)


@pytest.mark.parametrize(
    "changes",
    [{}, {"objects": ["数据/记录.edf", "a b,c"], "purpose": "预检查 – ü"}, {"role": None, "purpose": None}],
)
def test_compact_event_equals_kernel_canonical_compact(changes: dict[str, Any]) -> None:
    event = body(7, "b" * 64, **changes)
    assert ledger.compact_event(event) == canonical.compact(event)
    parsed = AccessEvent.model_validate(event, strict=True)
    assert ledger.compact_event(parsed) == canonical.compact(parsed)
    assert event_hash(parsed) == event["hash"]


# --- appending ---------------------------------------------------------------------------------------------


def test_first_event_links_genesis_seq1(tmp_path: Path) -> None:
    location = vault(tmp_path)
    outcome = append_check(location)
    assert outcome.status == "written" and outcome.event is not None
    assert (outcome.event.seq, outcome.event.previous_hash) == (1, GENESIS)
    assert outcome.event.time == "2026-10-29T12:00:00Z"
    assert outcome.event.tool_version == __import__("neurogrid").__version__
    assert outcome.event.hash == event_hash(outcome.event)


def test_append_links_previous_and_increments_seq(tmp_path: Path) -> None:
    location = vault(tmp_path)
    first = append_check(location).event
    second = append_check(location, action="read", purpose="audit", approval_ref="EC-1").event
    assert first is not None and second is not None
    assert (second.seq, second.previous_hash) == (2, first.hash)
    assert (second.action, second.purpose, second.approval_ref) == ("read", "audit", "EC-1")
    assert verify(location).intact


def test_line_is_canonical_compact_json_lf_terminated(tmp_path: Path) -> None:
    location = vault(tmp_path)
    event = append_check(location, objects=["数据/记录.edf"]).event
    assert event is not None
    data = location.log.read_bytes()
    assert data == canonical.compact(event) + b"\n"
    assert b" " not in data.split(b'"objects"')[0] and data.count(b"\n") == 1
    assert "数据".encode() in data  # UTF-8, not \\u escapes


def test_append_converts_the_time_to_utc(tmp_path: Path) -> None:
    from datetime import timedelta, timezone

    beijing = datetime(2026, 10, 29, 20, 0, 0, tzinfo=timezone(timedelta(hours=8)))
    event = append_check(vault(tmp_path), now=lambda: beijing).event
    assert event is not None and event.time == "2026-10-29T12:00:00Z"


def test_fsync_called(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    location = vault(tmp_path)
    synced: list[int] = []
    real = os.fsync

    def spy(fd: int) -> None:
        synced.append(os.fstat(fd).st_size)
        real(fd)

    with monkeypatch.context() as patched:
        patched.setattr(os, "fsync", spy)
        append_check(location)
    assert synced == [location.log.stat().st_size]  # after the whole line was written


def test_append_after_torn_tail_terminates_line_and_links_past_it(tmp_path: Path) -> None:
    events = chain(2)
    location = vault(tmp_path, raw=b"".join(map(line, events)) + line(body(3, events[1]["hash"]))[:40])
    outcome = append_check(location)
    assert outcome.event is not None and (outcome.event.seq, outcome.event.previous_hash) == (
        3,
        events[1]["hash"],
    )
    assert deviations(location) == [(3, "malformed", None, "not_json")]  # exactly the torn line
    assert location.log.read_bytes().count(b"\n") == 4


def test_append_terminates_a_complete_last_line_without_lf(tmp_path: Path) -> None:
    events = chain(2)
    location = vault(tmp_path, raw=b"\r\n".join(ledger.compact_event(e) for e in events))
    outcome = append_check(location)
    assert outcome.event is not None and (outcome.event.seq, outcome.event.previous_hash) == (
        3,
        events[1]["hash"],
    )
    assert verify(location).intact and verify(location).events == 3


def test_append_to_a_log_with_only_a_bom(tmp_path: Path) -> None:
    location = vault(tmp_path, raw=b"\xef\xbb\xbf")
    outcome = append_check(location)
    assert outcome.event is not None and outcome.event.seq == 1
    verification = verify(location)
    assert verification.intact and verification.events == 1


def test_append_looks_back_through_malformed_lines(tmp_path: Path) -> None:
    events = chain(1)
    location = vault(tmp_path, raw=line(events[0]) + b"garbage\n\n" + b"x" * (MAX_LINE_BYTES + 10) + b"\n")
    outcome = append_check(location)
    assert outcome.event is not None and outcome.event.previous_hash == events[0]["hash"]
    assert [d[1:] for d in deviations(location)] == [
        ("malformed", None, "not_json"),
        ("malformed", None, "blank"),
        ("malformed", None, "too_long"),
    ]


def test_append_only_reads_the_tail(tmp_path: Path) -> None:
    """The writer looks back at most TAIL_BYTES: a good entry before a megabyte of damage is not found."""
    events = chain(1)
    damage = (b"y" * 1000 + b"\n") * (ledger.TAIL_BYTES // 1000 + 2)
    location = vault(tmp_path, raw=line(events[0]) + damage)
    before = location.log.read_bytes()
    assert append_check(location).status == "log_damaged"
    assert location.log.read_bytes() == before


def test_append_log_missing_not_recreated(tmp_path: Path) -> None:
    location = vault(tmp_path)
    location.log.unlink()
    outcome = append_check(location)
    assert (outcome.status, outcome.event) == ("log_missing", None)
    assert not location.log.exists()
    assert outcome.error().message_key == "vault.log_missing"


def test_append_log_damaged_without_wellformed_tail(tmp_path: Path) -> None:
    location = vault(tmp_path, raw=b'{"not": "an event"}\n')
    assert append_check(location).status == "log_damaged"
    assert location.log.read_bytes() == b'{"not": "an event"}\n'


def test_append_without_vault(tmp_path: Path) -> None:
    outcome = append_check(locate(tmp_path, ".neurogrid/vault"))
    assert outcome.status == "no_vault"
    assert outcome.error().message_key == "vault.not_found"
    (tmp_path / "file").write_bytes(b"")
    assert append_check(locate(tmp_path, "file")).status == "no_vault"


def test_append_link(tmp_path: Path) -> None:
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / ".neurogrid").mkdir()
    dir_link(tmp_path / ".neurogrid" / "vault", tmp_path / "elsewhere")
    outcome = append_check(locate(tmp_path, ".neurogrid/vault"))
    assert (outcome.status, outcome.link_part) == ("link", "vault")
    error = outcome.error()
    assert isinstance(error, UnsafePathError) and error.params == {"part": "vault"}
    assert list((tmp_path / "elsewhere").iterdir()) == []


def test_append_lock_link(tmp_path: Path) -> None:
    location = vault(tmp_path)
    location.lock.unlink()
    (tmp_path / "elsewhere").mkdir()
    dir_link(location.lock, tmp_path / "elsewhere")
    assert append_check(location).status == "link"


@pytest.mark.skipif(sys.platform != "win32" and os.geteuid() == 0, reason="root ignores file modes")
def test_append_read_only_log_not_writable(tmp_path: Path) -> None:
    """A read-only vault is a warning and a finding, never exit 2 (A-30): append reports not_writable."""
    location = vault(tmp_path, chain(1))
    before = location.log.read_bytes()
    location.log.chmod(stat.S_IREAD)
    try:
        assert append_check(location).status == "not_writable"
    finally:
        location.log.chmod(stat.S_IREAD | stat.S_IWRITE)
    assert location.log.read_bytes() == before


def test_append_lock_not_creatable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    location = vault(tmp_path)

    def refuse(_path: Path) -> int:
        raise PermissionError(13, "read-only folder")

    monkeypatch.setattr(_os, "open_lock", refuse)
    assert append_check(location).status == "not_writable"


def test_append_write_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    location = vault(tmp_path)

    def full(_fd: int, _data: Any) -> int:
        raise OSError(28, "No space left on device")

    with monkeypatch.context() as patched:
        patched.setattr(os, "write", full)
        status = append_check(location).status
    assert status == "not_writable"


def test_append_locked_vault(tmp_path: Path) -> None:
    location = vault(tmp_path)
    with lock_held(location.lock):
        outcome = append_check(location, timeout_s=0.2)
    assert (outcome.status, outcome.event) == ("locked", None)
    assert isinstance(outcome.error(), VaultLocked)
    assert location.log.read_bytes() == b""


@pytest.mark.parametrize("violations", [1, 2])
def test_append_retries_a_sharing_violation_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, violations: int
) -> None:
    location = vault(tmp_path)
    real = _os.open_log
    calls: list[float] = []

    def busy(path: Path) -> int:
        calls.append(time.monotonic())
        if len(calls) <= violations:
            raise PermissionError(13, "in use")
        return real(path)

    monkeypatch.setattr(_os, "open_log", busy)
    monkeypatch.setattr(_os, "is_sharing_violation", lambda exc: True)
    status = append_check(location).status
    assert status == ("written" if violations == 1 else "not_writable")
    assert len(calls) == 2 and calls[1] - calls[0] >= ledger.RETRY_DELAY_S * 0.9


def test_sharing_violation_codes() -> None:
    assert _os.is_sharing_violation(OSError(13, "x", None, 32)) is (sys.platform == "win32")
    assert not _os.is_sharing_violation(PermissionError(13, "read-only"))


def test_append_locked_requires_the_held_lock(tmp_path: Path) -> None:
    location = vault(tmp_path)
    other = vault(tmp_path / "other")
    fields: dict[str, Any] = {
        "role": None,
        "action": "check",
        "objects": ["**"],
        "purpose": None,
        "approval_ref": None,
    }
    with exclusive(other.lock) as held, pytest.raises(ValueError, match="held lock"):
        append_locked(location, held, **fields)
    with exclusive(location.lock) as held:
        assert append_locked(location, held, now=now, **fields).status == "written"
        with pytest.raises(ValueError, match="append_locked"):
            append(location, **fields)  # would wait for itself until the timeout
    with pytest.raises(ValueError, match="held lock"):
        append_locked(location, held, **fields)  # released
    assert verify(location).events == 1


def test_append_locked_consent_manage_event(tmp_path: Path) -> None:
    """The consent area's path: lock, append the consent_manage event naming consents.yaml relative to the
    project root (p6 decisions 3), then write the file."""
    location = vault(tmp_path)
    with exclusive(location.lock) as held:
        outcome = append_locked(
            location,
            held,
            role="QA.lead",
            action="consent_manage",
            objects=[location.object_name("consents.yaml")],
            purpose=None,
            approval_ref="EC-2026-17",
            now=now,
        )
    assert outcome.event is not None and outcome.event.objects == [".neurogrid/vault/consents.yaml"]
    assert outcome.event.action == "consent_manage" and outcome.event.role == "QA.lead"


@pytest.mark.parametrize(
    ("changes", "key", "params"),
    [
        ({"role": "QA lead"}, "vault.role_invalid", {}),
        (
            {"action": "delete"},
            "vault.action_invalid",
            {"allowed": "read, check, convert, report, export, consent_manage"},
        ),
        ({"objects": ["**"] * 1001}, "vault.too_many_objects", {"limit": 1000}),
        ({"objects": ["x" * 1000] * 70}, "vault.too_many_objects", {"limit": 1000}),
        ({"objects": ["**", "/abs.edf"]}, "vault.object_invalid", {"index": 2}),
        ({"objects": ["a\\b"]}, "vault.object_invalid", {"index": 1}),
        ({"purpose": ""}, "vault.text_invalid", {"field": "purpose"}),
        ({"purpose": "p" * 201}, "vault.text_invalid", {"field": "purpose"}),
        ({"purpose": "a\nb"}, "vault.text_invalid", {"field": "purpose"}),
        ({"approval_ref": "x\ud800"}, "vault.text_invalid", {"field": "approval_ref"}),
        ({"approval_ref": "r" * 121}, "vault.text_invalid", {"field": "approval_ref"}),
    ],
)
def test_invalid_fields_are_tool_errors_before_anything_is_written(
    tmp_path: Path, changes: dict[str, Any], key: str, params: dict[str, Any]
) -> None:
    location = vault(tmp_path)
    with pytest.raises(InputError) as info:
        append_check(location, **changes)
    assert (info.value.message_key, info.value.params) == (key, params)
    assert location.log.read_bytes() == b""


def test_largest_valid_entry_fits_one_line(tmp_path: Path) -> None:
    location = vault(tmp_path)
    objects = ["x" * 1000] * 60  # about 60 KB: still one entry
    ledger.check_fields(role="r", action="read", objects=objects, purpose="p" * 200, approval_ref="a" * 120)
    outcome = append_check(location, objects=objects)
    assert outcome.status == "written" and len(location.log.read_bytes()) <= MAX_LINE_BYTES + 1
    assert verify(location).intact


def test_empty_objects_are_a_programming_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least one object"):
        append_check(vault(tmp_path), objects=[])


def test_outcome_errors() -> None:
    expected = {
        "no_vault": "vault.not_found",
        "link": "vault.link",
        "log_missing": "vault.log_missing",
        "locked": "vault.locked",
        "not_writable": "vault.not_writable",
        "log_damaged": "vault.log_damaged",
    }
    assert set(expected) | {"written"} == set(ledger.APPEND_STATUSES)
    for status, key in expected.items():
        error = AppendOutcome(status, link_part=VAULT_LOG).error()  # type: ignore[arg-type]
        assert isinstance(error, NeuroGridError) and error.message_key == key, status
    with pytest.raises(ValueError):
        AppendOutcome("written").error()


# --- reading and verifying ---------------------------------------------------------------------------------


def test_verify_intact_chain_exit0(tmp_path: Path) -> None:
    events = chain(5)
    verification = verify(vault(tmp_path, events))
    assert verification.intact and verification.deviations == ()
    assert (verification.events, verification.lines, verification.head) == (5, 5, events[-1]["hash"])


def test_verify_empty_log_intact_head_none(tmp_path: Path) -> None:
    verification = verify(vault(tmp_path))
    assert verification.intact and (verification.events, verification.lines, verification.head) == (
        0,
        0,
        None,
    )


def test_verify_log_missing_is_deviation_exit1(tmp_path: Path) -> None:
    location = vault(tmp_path)
    location.log.unlink()
    verification = verify(location, ["a" * 64])
    assert verification.deviations == (Deviation(None, "log_missing"),)
    assert not verification.intact and verification.expected[0].found is False


def test_verify_refuses_a_vault_that_is_not_present(tmp_path: Path) -> None:
    with pytest.raises(InputError) as info:
        verify(locate(tmp_path, ".neurogrid/vault"))
    assert info.value.message_key == "vault.not_found"
    location = vault(tmp_path)
    location.log.unlink()
    (tmp_path / "elsewhere").mkdir()
    dir_link(location.log, tmp_path / "elsewhere")
    with pytest.raises(UnsafePathError):
        verify(location)


def test_verify_detects_change(tmp_path: Path) -> None:
    """A field edited, its hash not recomputed: hash_mismatch on that line, likely change."""
    events = chain(5)
    events[2] = {**events[2], "role": "someone_else"}
    assert deviations(vault(tmp_path, events)) == [(3, "hash_mismatch", "change", None)]


def test_verify_detects_change_with_recomputed_own_hash(tmp_path: Path) -> None:
    """The edited entry carries a fresh own hash: the next entry no longer links to it."""
    events = chain(5)
    events[2] = body(3, events[1]["hash"], role="someone_else")
    assert deviations(vault(tmp_path, events)) == [(4, "link_mismatch", "change", None)]


def test_verify_detects_insert_forged(tmp_path: Path) -> None:
    events = chain(4)
    forged = body(3, events[1]["hash"], action="export")
    assert deviations(vault(tmp_path, [*events[:2], forged, *events[2:]])) == [
        (4, "link_mismatch", "insert", None)
    ]


def test_verify_detects_insert_duplicate(tmp_path: Path) -> None:
    events = chain(4)
    assert deviations(vault(tmp_path, [*events[:2], events[1], *events[2:]])) == [
        (3, "link_mismatch", "insert", None)
    ]


def test_verify_detects_delete_middle(tmp_path: Path) -> None:
    events = chain(5)
    assert deviations(vault(tmp_path, [*events[:2], *events[3:]])) == [(3, "link_mismatch", "delete", None)]


def test_verify_detects_delete_first(tmp_path: Path) -> None:
    events = chain(4)
    assert deviations(vault(tmp_path, events[1:])) == [(1, "start_mismatch", "delete", None)]


def test_verify_detects_reorder(tmp_path: Path) -> None:
    events = chain(5)
    swapped = [events[0], events[2], events[1], events[3], events[4]]
    found = deviations(vault(tmp_path, swapped))
    assert found == [
        (2, "link_mismatch", "reorder", None),
        (3, "link_mismatch", "reorder", None),
        (4, "link_mismatch", "reorder", None),
    ]


def test_verify_detects_reorder_of_the_first_entry(tmp_path: Path) -> None:
    events = chain(3)
    found = deviations(vault(tmp_path, [events[1], events[0], events[2]]))
    assert [d[1:3] for d in found] == [
        ("start_mismatch", "reorder"),
        ("link_mismatch", "reorder"),
        ("link_mismatch", "reorder"),
    ]


def test_reorder_needs_an_intact_chain_in_another_order(tmp_path: Path) -> None:
    """A swap plus a deletion is no permutation of an intact chain: the likely causes come from seq."""
    events = chain(6)
    found = deviations(vault(tmp_path, [events[0], events[2], events[1], events[3], events[5]]))
    assert "reorder" not in {d[2] for d in found} and found


def test_truncation_undetected_without_expect_head_detected_with(tmp_path: Path) -> None:
    """The documented limit (A-30): cutting entries off the end leaves an intact chain; only an externally
    recorded head shows it."""
    events = chain(5)
    location = vault(tmp_path, events[:3])
    assert verify(location).intact
    verification = verify(location, [events[-1]["hash"]])
    assert not verification.intact and verification.deviations == (Deviation(None, "head_missing"),)
    assert verification.expected[0].hash == events[-1]["hash"] and not verification.expected[0].found


def test_rewrite_undetected_without_expect_head_detected_with(tmp_path: Path) -> None:
    original = chain(4)
    location = vault(tmp_path, chain(4, role="rewritten"))
    assert verify(location).intact
    assert deviations(location, (original[-1]["hash"],)) == [(None, "head_missing", None, None)]


def test_edit_with_all_following_hashes_recomputed_is_a_rewrite(tmp_path: Path) -> None:
    original = chain(4)
    rewritten = original[:1]
    for seq in range(2, 5):
        rewritten.append(
            body(seq, rewritten[-1]["hash"], purpose="changed" if seq == 2 else VECTOR["purpose"])
        )
    location = vault(tmp_path, rewritten)
    assert verify(location).intact
    assert not verify(location, [original[-1]["hash"]]).intact


def test_expect_head_of_earlier_state_passes_after_appends(tmp_path: Path) -> None:
    events = chain(3)
    location = vault(tmp_path, events)
    recorded = verify(location).head
    assert recorded == events[-1]["hash"]
    append_check(location)
    append_check(location)
    verification = verify(location, [recorded.upper()])  # case does not matter
    assert verification.intact
    assert (verification.expected[0].line, verification.expected[0].events_after) == (3, 2)


def test_expect_head_repeatable(tmp_path: Path) -> None:
    events = chain(4)
    location = vault(tmp_path, events)
    verification = verify(location, [events[1]["hash"], events[3]["hash"], events[1]["hash"]])
    assert verification.intact
    assert [(e.line, e.events_after) for e in verification.expected] == [(2, 2), (4, 0)]
    missing = verify(location, [events[1]["hash"], "c" * 64, "d" * 64])
    assert [e.found for e in missing.expected] == [True, False, False]
    assert missing.deviations == (Deviation(None, "head_missing"), Deviation(None, "head_missing"))


def test_expect_head_counts_only_behind_an_intact_chain(tmp_path: Path) -> None:
    """A head is found only if the chain up to its line has no deviation."""
    events = chain(4)
    events[1] = {**events[1], "role": "edited"}
    verification = verify(vault(tmp_path, events), [events[3]["hash"]])
    assert not verification.expected[0].found
    assert [d.kind for d in verification.deviations] == ["hash_mismatch", "head_missing"]


@pytest.mark.parametrize("head", ["xyz", "a" * 63, "a" * 65, "g" * 64, " " + "a" * 63])
def test_expect_head_bad_format_exit2(tmp_path: Path, head: str) -> None:
    """errors.vault.bad_head (exit 2), before anything else is looked at."""
    with pytest.raises(InputError) as info:
        verify(locate(tmp_path, ".neurogrid/vault"), [head])
    assert info.value.message_key == "vault.bad_head"


MALFORMED = [
    (b"not json", "not_json"),
    (b'{"a": 1', "not_json"),
    (b"[1, 2]", "schema"),
    (b'{"seq": NaN}', "not_json"),
    (b"   ", "blank"),
    (b"", "blank"),
    (b"\xff\xfe", "encoding"),
    (b"\xef\xbb\xbf{}", "not_json"),  # a BOM only counts at the start of the file
]


@pytest.mark.parametrize(("raw", "problem"), MALFORMED, ids=[problem for _, problem in MALFORMED])
def test_malformed_kinds(tmp_path: Path, raw: bytes, problem: str) -> None:
    """A malformed line between two entries: one deviation naming the problem, never the content; the next
    entry links past it to the nearest well-formed line."""
    events = chain(2)
    location = vault(tmp_path, raw=line(events[0]) + raw + b"\n" + line(events[1]))
    assert deviations(location) == [(2, "malformed", None, problem)]


def _variant(changes: dict[str, Any] | None = None, drop: str | None = None) -> bytes:
    data = {**body(2, chain(1)[0]["hash"]), **(changes or {})}
    if drop:
        del data[drop]
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


@pytest.mark.parametrize(
    ("raw", "problem"),
    [
        (_variant({"user": "x"}), "schema"),
        (_variant(drop="role"), "schema"),
        (_variant({"hash": "ABC"}), "schema"),
        (_variant({"seq": "2"}), "schema"),
        (_variant({"time": "2026-10-29T12:00:00+08:00"}), "time"),
        (_variant({"time": "2026-02-30T12:00:00Z"}), "time"),
        (_variant({"time": "x", "seq": 0}), "schema"),
        (b'{"seq":1,"seq":1}', "duplicate_key"),
        (b"x" * (MAX_LINE_BYTES + 1), "too_long"),
    ],
    ids=["extra", "missing", "hash", "seq_text", "time_offset", "time_date", "time_and_seq", "dup", "long"],
)
def test_malformed_schema_and_limits(tmp_path: Path, raw: bytes, problem: str) -> None:
    events = chain(2)
    location = vault(tmp_path, raw=line(events[0]) + raw + b"\n" + line(events[1]))
    assert deviations(location) == [(2, "malformed", None, problem)]


def test_line_limit_is_exact(tmp_path: Path) -> None:
    padded = b" " * (MAX_LINE_BYTES - len(ledger.compact_event(chain(1)[0]))) + ledger.compact_event(
        chain(1)[0]
    )
    assert len(padded) == MAX_LINE_BYTES
    location = vault(tmp_path, raw=padded + b"\r\n")  # the CR does not count
    assert verify(location).intact
    location.log.write_bytes(b" " + padded + b"\n")
    assert deviations(location) == [(1, "malformed", None, "too_long")]


def test_bom_crlf_and_missing_final_lf_tolerated(tmp_path: Path) -> None:
    events = chain(3)
    text = b"\xef\xbb\xbf" + b"\r\n".join(ledger.compact_event(e) for e in events)
    verification = verify(vault(tmp_path, raw=text))
    assert verification.intact and verification.events == 3


def test_content_based_reading_key_order_and_white_space(tmp_path: Path) -> None:
    events = chain(3)
    pretty = [
        json.dumps(dict(reversed(list(e.items()))), ensure_ascii=True, indent=None).encode() for e in events
    ]
    assert verify(vault(tmp_path, raw=b"\n".join(pretty) + b"\n")).intact


def test_entry_content_never_in_deviations(tmp_path: Path) -> None:
    events = chain(3, objects=["secret-name.edf"], purpose="secret purpose")
    events[1] = {**events[1], "role": "edited"}
    verification = verify(vault(tmp_path, events))
    assert "secret" not in repr(verification.deviations)


def test_iter_entries_reads_up_to_the_snapshot(tmp_path: Path) -> None:
    """Readers stream [0, S) of the size noted under the lock; later appends do not change their verdict."""
    location = vault(tmp_path, chain(3))
    size = ledger.snapshot(location)
    append_check(location)
    entries = list(ledger.iter_entries(location.log, size))
    assert [entry.event.seq for entry in entries if entry.event] == [1, 2, 3]
    assert all(entry.hash_ok for entry in entries)


def test_snapshot_waits_for_the_lock(tmp_path: Path) -> None:
    location = vault(tmp_path, chain(1))
    with lock_held(location.lock):
        with pytest.raises(VaultLocked):
            ledger.snapshot(location, timeout_s=0.2)
        with pytest.raises(VaultLocked):
            verify(location, timeout_s=0.2)
    assert verify(location).intact


def test_snapshot_of_a_missing_log(tmp_path: Path) -> None:
    location = vault(tmp_path)
    location.log.unlink()
    with pytest.raises(FileNotFoundError):
        ledger.snapshot(location)
    location.log.mkdir()
    with pytest.raises(IsADirectoryError):
        ledger.snapshot(location)


def _long_log(location: VaultLocation, count: int) -> str:
    """Write an intact log of ``count`` entries; returns its head."""
    previous = GENESIS
    with location.log.open("wb") as handle:
        for seq in range(1, count + 1):
            event = body(seq, previous)
            handle.write(line(event))
            previous = event["hash"]
    return previous


def _peak_of_verify(location: VaultLocation) -> int:
    tracemalloc.start()
    try:
        assert verify(location).intact
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def test_verify_streams_100k_entries(tmp_path: Path) -> None:
    """Streaming: the memory of a verification does not grow with the log (measured with 5,000 and 25,000
    entries, both larger than one read chunk), and 100,000 entries are verified in bounded time (the
    1,000,000-entry time is a measurement in the build guide, not a gate)."""
    small, large = vault(tmp_path / "small"), vault(tmp_path / "large")
    _long_log(small, 5_000)
    _long_log(large, 25_000)
    assert small.log.stat().st_size > ledger.READ_CHUNK
    peaks = (_peak_of_verify(small), _peak_of_verify(large))
    assert peaks[1] < peaks[0] + 500_000 and peaks[1] < 8_000_000, f"peaks {peaks} bytes for 5,000/25,000"
    count = 100_000
    location = vault(tmp_path / "long")
    head = _long_log(location, count)
    started = time.perf_counter()
    verification = verify(location)
    seconds = time.perf_counter() - started
    assert verification.intact and verification.events == count and verification.head == head
    assert seconds < 300, f"{seconds:.1f} s for {count} entries ({location.log.stat().st_size} bytes)"
