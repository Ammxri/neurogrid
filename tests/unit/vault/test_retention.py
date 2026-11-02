"""The access log as the retention and role checks read it (NV-F04, NV-F05; A-93, A-94): ledger.first_entry
under the snapshot rule (CORE-NV05-01 retention.log_truncated) and the event cut of CORE-NV04-01."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from neurogrid.checks.access import event_cut
from neurogrid.vault import ledger
from neurogrid.vault.store import VaultLocation, init_vault, locate

WHEN = datetime(2026, 10, 29, 12, 0, 0, tzinfo=UTC)


def _vault(tmp_path: Path, events: int) -> VaultLocation:
    location = locate(tmp_path, ".neurogrid/vault")
    init_vault(location)
    for _ in range(events):
        outcome = ledger.append(
            location,
            role="QA",
            action="check",
            objects=["**"],
            purpose=None,
            approval_ref=None,
            now=lambda: WHEN,
        )
        assert outcome.status == "written"
    return location.refreshed()


def test_first_entry(tmp_path: Path) -> None:
    location = _vault(tmp_path, 3)
    first = ledger.first_entry(location)
    assert first is not None and (first.seq, first.previous_hash) == (1, ledger.GENESIS)
    lines = location.log.read_bytes().splitlines(keepends=True)
    location.log.write_bytes(b"garbage\n" + b"".join(lines[1:]))  # a damaged first line is skipped
    second = ledger.first_entry(location)
    assert second is not None and second.seq == 2 and second.previous_hash != ledger.GENESIS
    location.log.write_bytes(b"")
    assert ledger.first_entry(location) is None


def test_first_entry_reads_up_to_the_snapshot(tmp_path: Path) -> None:
    """The size is taken under the lock; an entry appended later is not read (the snapshot rule)."""
    location = _vault(tmp_path, 0)
    location.log.write_bytes(b"not json\n")
    assert ledger.first_entry(location) is None


def test_event_cut() -> None:
    """A-93: events before 00:00 UTC of the day before the reference date, in the time format of the log."""
    assert event_cut(date(2026, 11, 20)) == "2026-11-19T00:00:00Z"
    assert event_cut(date(2027, 3, 1)) == "2027-02-28T00:00:00Z"
    assert "2026-11-18T23:59:59Z" < event_cut(date(2026, 11, 20)) <= "2026-11-19T00:00:00Z"
