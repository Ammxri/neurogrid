"""The hash-chained access log ``<vault>/access.jsonl`` (NV-F03, DM-09, A-30, A-90): appending, reading and
verifying.

Format: one access event per line, canonical compact JSON (kernel.canonical.compact: sorted keys, no white
space, UTF-8) and LF. ``hash`` = SHA-256 over the canonical compact JSON of the event without ``hash``;
``previous_hash`` of the first entry is GENESIS (64 zeros), every later one carries the stored ``hash`` of the
nearest preceding well-formed line (parseable and schema-valid; malformed lines are skipped for linking, by
the writer and by the verifier alike); ``seq`` counts 1..n. Reading is content-based, as for the manifest
(A-61): key order and white space inside a line do not matter, a UTF-8 BOM at the start of the file, CRLF
line ends and a missing LF after the last line are tolerated; JSON is strict (no duplicate keys, NaN or
Infinity) and a line holds at most MAX_LINE_BYTES.

Locking (neurogrid.vault.lock): ``append`` takes the vault lock for reading the tail and appending;
``append_locked`` does both under a lock the caller holds. Readers (``verify``, ``vault log --show``, the
CORE-NV03-01 measurement) take the lock only to note the size S of the log (``snapshot``) and read the bytes
[0, S) without it: NeuroGrid only ever adds bytes after S, so the verdict on [0, S) cannot change while they
read, and a long verification never blocks a writer (p6 decisions 3, the P6 reading of A-30 "Dateisperre um
Lesen und Anhängen").

Limits of the chain (A-30, stated by ``vault verify`` and the documentation): changing, inserting, deleting
and reordering entries inside the chain are detected; an edit that recomputes every following hash is a
rewrite; truncation at the end and rewriting are detected only against a head hash recorded elsewhere
(``--expect-head``); only accesses through NeuroGrid are recorded; times come from the local clock.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import stat
import time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, get_args

from pydantic import ValidationError

from neurogrid import __version__
from neurogrid.kernel.errors import InputError, NeuroGridError, UnsafePathError
from neurogrid.kernel.provenance import VAULT_LOCK, VAULT_LOG
from neurogrid.kernel.safety import is_link
from neurogrid.model.access import (
    ACTIONS,
    FORMAT_VERSION,
    MAX_APPROVAL_REF_CHARS,
    MAX_OBJECTS,
    MAX_PURPOSE_CHARS,
    AccessEvent,
    format_time,
    object_problem,
    role_valid,
    text_problem,
)
from neurogrid.vault import _os
from neurogrid.vault.lock import LOCK_TIMEOUT_S, HeldLock, VaultLocked, exclusive
from neurogrid.vault.store import VaultLocation, require_present

GENESIS = "0" * 64
MAX_LINE_BYTES = 65_536  # one entry without its line end (A-53)
TAIL_BYTES = 1_048_576  # the writer looks this far back for the previous well-formed entry
READ_CHUNK = 1_048_576
RETRY_DELAY_S = 0.1  # one retry of a Windows sharing violation (antivirus, indexer)
_BOM = b"\xef\xbb\xbf"
_HEAD = re.compile(r"[0-9A-Fa-f]{64}")
_LARGEST_SEQ = 10**15  # for the size check of a new entry: a seq longer than any real chain

AppendStatus = Literal["written", "no_vault", "link", "log_missing", "locked", "not_writable", "log_damaged"]
APPEND_STATUSES: tuple[str, ...] = get_args(AppendStatus)
Problem = Literal["not_json", "duplicate_key", "schema", "too_long", "blank", "encoding", "time"]
DeviationKind = Literal[
    "malformed", "hash_mismatch", "link_mismatch", "start_mismatch", "log_missing", "head_missing"
]
DEVIATION_KINDS: tuple[str, ...] = get_args(DeviationKind)
Likely = Literal["change", "insert", "delete", "reorder"]
LIKELY: tuple[str, ...] = get_args(Likely)


def utc_now() -> datetime:
    return datetime.now(UTC)


def compact_event(data: AccessEvent | Mapping[str, Any]) -> bytes:
    """kernel.canonical.compact of an event: the same bytes for its value types (text, integers, null, lists
    of text; tests/unit/vault/test_ledger.py compares both) without the generic normalisation, which a log of
    a million lines would pay for on every entry. Only for validated values (no lone surrogates)."""
    if isinstance(data, AccessEvent):
        data = data.model_dump(mode="json")
    text = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return text.encode("utf-8")


def event_hash(event: AccessEvent | Mapping[str, Any]) -> str:
    """SHA-256 (hex) over the canonical compact JSON of the event without its ``hash`` field."""
    data = event.model_dump(mode="json") if isinstance(event, AccessEvent) else dict(event)
    data.pop("hash", None)
    return hashlib.sha256(compact_event(data)).hexdigest()


def normalize_head(text: str) -> str:
    """A head hash given on the command line (``--expect-head``): 64 hex digits in any case, stored lower
    case; anything else is errors.vault.bad_head (exit 2)."""
    if not _HEAD.fullmatch(text):
        raise InputError("vault.bad_head")
    return text.lower()


def check_fields(
    *,
    role: str | None,
    action: str,
    objects: Sequence[str],
    purpose: str | None,
    approval_ref: str | None,
) -> None:
    """Validate the fields a caller gives for a new event, before anything is locked or written. Raises the
    tool errors (exit 2) errors.vault.role_invalid, .action_invalid {allowed}, .too_many_objects {limit} (more
    than MAX_OBJECTS objects, or together more than one entry of MAX_LINE_BYTES holds), .object_invalid
    {index} (1-based; no value is shown, A-51) and .text_invalid {field} (purpose, approval_ref: empty, too
    long, a control character or a lone surrogate). ValueError for an empty object list."""
    if role is not None and not role_valid(role):
        raise InputError("vault.role_invalid")
    if action not in ACTIONS:
        raise InputError("vault.action_invalid", allowed=", ".join(ACTIONS))
    if not objects:
        raise ValueError("an access event names at least one object")
    if len(objects) > MAX_OBJECTS:
        raise InputError("vault.too_many_objects", limit=MAX_OBJECTS)
    for index, item in enumerate(objects, start=1):
        if not isinstance(item, str) or object_problem(item) is not None:
            raise InputError("vault.object_invalid", index=index)
    for name, value, limit in (
        ("purpose", purpose, MAX_PURPOSE_CHARS),
        ("approval_ref", approval_ref, MAX_APPROVAL_REF_CHARS),
    ):
        if value is not None and (not value or len(value) > limit or text_problem(value) is not None):
            raise InputError("vault.text_invalid", field=name)
    sample = _body(
        _LARGEST_SEQ, "2000-01-01T00:00:00Z", role, action, objects, purpose, approval_ref, GENESIS
    )
    if len(compact_event({**sample, "hash": GENESIS})) > MAX_LINE_BYTES:
        raise InputError("vault.too_many_objects", limit=MAX_OBJECTS)


def _body(
    seq: int,
    moment: str,
    role: str | None,
    action: str,
    objects: Sequence[str],
    purpose: str | None,
    approval_ref: str | None,
    previous_hash: str,
) -> dict[str, Any]:
    return {
        "format_version": FORMAT_VERSION,
        "seq": seq,
        "time": moment,
        "role": role,
        "action": action,
        "objects": list(objects),
        "purpose": purpose,
        "approval_ref": approval_ref,
        "tool_version": __version__,
        "previous_hash": previous_hash,
    }


# --- reading ----------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Entry:
    """One line of the log: the event if the line is well-formed (else ``problem`` says why not) and whether
    its stored hash equals the recomputed one."""

    line: int
    event: AccessEvent | None
    problem: Problem | None = None
    hash_ok: bool = False


class _DuplicateKey(ValueError):
    pass


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(key)
        result[key] = value
    return result


def _no_constant(_name: str) -> Any:
    raise ValueError("NaN or Infinity")


def parse_line(content: bytes, line: int = 0) -> Entry:
    """One line without its line end (LF, and CR before it, already removed)."""
    if len(content) > MAX_LINE_BYTES:
        return Entry(line, None, "too_long")
    if not content.strip():
        return Entry(line, None, "blank")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return Entry(line, None, "encoding")
    try:
        raw = json.loads(text, object_pairs_hook=_unique_keys, parse_constant=_no_constant)
    except _DuplicateKey:
        return Entry(line, None, "duplicate_key")
    except (ValueError, RecursionError):
        return Entry(line, None, "not_json")
    if not isinstance(raw, dict):
        return Entry(line, None, "schema")
    try:
        event = AccessEvent.model_validate(raw, strict=True)
    except ValidationError as exc:
        only_time = all(tuple(error["loc"]) == ("time",) for error in exc.errors())
        return Entry(line, None, "time" if only_time else "schema")
    return Entry(line, event, None, event_hash(raw) == event.hash)


def _lines(fd: int, size: int | None) -> Iterator[bytes | None]:
    """The lines of an open log up to ``size`` bytes (all without it), streamed: each without LF and a CR
    before it, or None for a line longer than MAX_LINE_BYTES (skipped up to its LF, never held in memory).
    A UTF-8 BOM at the start is dropped; a last line without LF counts."""
    remaining = size
    buffer = bytearray()
    overflow = False
    first = True
    while remaining is None or remaining > 0:
        chunk = os.read(fd, READ_CHUNK if remaining is None else min(READ_CHUNK, remaining))
        if not chunk:
            break
        if remaining is not None:
            remaining -= len(chunk)
        if first:
            first = False
            if chunk.startswith(_BOM):
                chunk = chunk[len(_BOM) :]
        start = 0
        while True:
            end = chunk.find(b"\n", start)
            piece = chunk[start:] if end < 0 else chunk[start:end]
            if not overflow:
                buffer += piece
                overflow = len(buffer) > MAX_LINE_BYTES + 1  # + 1: a CR before the LF
                if overflow:
                    buffer.clear()
            if end < 0:
                break
            yield None if overflow else _without_cr(buffer)
            buffer.clear()
            overflow = False
            start = end + 1
    if overflow:
        yield None
    elif buffer:
        yield _without_cr(buffer)


def _without_cr(buffer: bytearray) -> bytes:
    return bytes(buffer[:-1] if buffer.endswith(b"\r") else buffer)


def iter_entries(path: Path, size: int | None = None) -> Iterator[Entry]:
    """The entries of the log at ``path``, read up to ``size`` bytes (from ``snapshot``), streamed. Raises
    UnsafePathError errors.vault.link for a link, OSError (FileNotFoundError if the log is missing)."""
    if is_link(path):
        raise UnsafePathError("vault.link", part=VAULT_LOG)
    try:
        fd = _os.open_for_reading(path)
    except OSError as exc:
        if _os.is_link_error(exc):
            raise UnsafePathError("vault.link", part=VAULT_LOG) from None
        raise
    try:
        for number, content in enumerate(_lines(fd, size), start=1):
            yield Entry(number, None, "too_long") if content is None else parse_line(content, number)
    finally:
        os.close(fd)


def snapshot(location: VaultLocation, timeout_s: float = LOCK_TIMEOUT_S) -> int:
    """The size of the log, taken under the vault lock (released before it returns). Raises the errors of
    store.require_present, VaultLocked, UnsafePathError for a linked log, FileNotFoundError for a missing log
    and OSError."""
    current = location.refreshed()
    require_present(current)
    with exclusive(current.lock, timeout_s):
        if is_link(current.log):
            raise UnsafePathError("vault.link", part=VAULT_LOG)
        info = os.lstat(current.log)
        if not stat.S_ISREG(info.st_mode):
            raise IsADirectoryError(errno.EISDIR, "the access log is no regular file")
        return info.st_size


# --- verifying --------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Deviation:
    """A deviation of the log: its line (None for log_missing and head_missing), its kind, the likely cause
    for chain breaks (from seq: a later seq than expected = entries deleted, an earlier one = inserted, the
    expected one = the entry before was changed with a recomputed hash; ``reorder`` when the whole log is a
    permutation of an intact chain) and the problem of a malformed line. Never any content of the entry."""

    line: int | None
    kind: DeviationKind
    likely: Likely | None = None
    problem: Problem | None = None


@dataclass(frozen=True)
class ExpectedHead:
    """An externally recorded head hash (``--expect-head``): found on ``line`` with ``events_after`` entries
    after it if a line whose own hash verifies carries it and the chain up to that line has no deviation."""

    hash: str
    line: int | None = None
    events_after: int | None = None

    @property
    def found(self) -> bool:
        return self.line is not None


@dataclass(frozen=True)
class LogVerification:
    events: int  # well-formed entries
    lines: int
    head: str | None  # the stored hash of the last well-formed entry; None for an empty log
    deviations: tuple[Deviation, ...]  # all, in line order; log_missing and head_missing last
    expected: tuple[ExpectedHead, ...] = ()

    @property
    def intact(self) -> bool:
        return not self.deviations


_MODULUS = 1 << 256


def _fingerprint(tag: bytes, number: int, digest: str = "") -> int:
    return int.from_bytes(hashlib.sha256(b"%s:%d:%s" % (tag, number, digest.encode("ascii"))).digest(), "big")


class _Verifier:
    """Checks entries one by one in constant memory (apart from the deviations): own hash, start, links,
    expected heads, and multiset fingerprints of the seq values and the links for the reorder rule."""

    def __init__(self, heads: Sequence[str]) -> None:
        self.heads = dict.fromkeys(heads)
        self.found: dict[str, tuple[int, int]] = {}
        self.deviations: list[Deviation] = []
        self.lines = 0
        self.events = 0
        self.previous: tuple[str, int] | None = None  # stored hash and seq of the last well-formed entry
        # reorder: possible while every line is well-formed with a verified own hash
        self.permutation_only = True
        self.out_of_order = False
        self.seqs = 0
        self.links_claimed = 0
        self.links_offered = 0
        self.last: tuple[int, str] = (0, GENESIS)  # the largest seq and its hash

    def feed(self, entry: Entry) -> None:
        self.lines = entry.line
        event = entry.event
        if event is None:
            self.deviations.append(Deviation(entry.line, "malformed", problem=entry.problem))
            self.permutation_only = False
            return
        self.events += 1
        if not entry.hash_ok:
            self.deviations.append(Deviation(entry.line, "hash_mismatch", "change"))
            self.permutation_only = False
        if self.previous is None:
            if event.previous_hash != GENESIS or event.seq != 1:
                self.deviations.append(Deviation(entry.line, "start_mismatch", "delete"))
        elif event.previous_hash != self.previous[0]:
            expected = self.previous[1] + 1
            likely: Likely = (
                "delete" if event.seq > expected else "insert" if event.seq < expected else "change"
            )
            self.deviations.append(Deviation(entry.line, "link_mismatch", likely))
        if (
            entry.hash_ok
            and not self.deviations
            and event.hash in self.heads
            and event.hash not in self.found
        ):
            self.found[event.hash] = (entry.line, self.events)
        if self.permutation_only:
            self.out_of_order = self.out_of_order or event.seq != self.events
            self.seqs = (self.seqs + _fingerprint(b"s", event.seq)) % _MODULUS
            self.links_claimed = (
                self.links_claimed + _fingerprint(b"l", event.seq, event.previous_hash)
            ) % _MODULUS
            self.links_offered = (
                self.links_offered + _fingerprint(b"l", event.seq + 1, event.hash)
            ) % _MODULUS
            if event.seq > self.last[0]:
                self.last = (event.seq, event.hash)
        self.previous = (event.hash, event.seq)

    def _reordered(self) -> bool:
        """True if the entries are an intact chain in another order: their seq values are 1..n and the links
        they claim (seq, previous_hash) are exactly the links the sorted chain offers (genesis for 1,
        hash(s) for s + 1)."""
        n = self.events
        if not (self.permutation_only and self.out_of_order and n >= 2 and self.last[0] == n):
            return False
        expected_seqs = sum(_fingerprint(b"s", seq) for seq in range(1, n + 1)) % _MODULUS
        offered = (
            self.links_offered - _fingerprint(b"l", n + 1, self.last[1]) + _fingerprint(b"l", 1, GENESIS)
        )
        return self.seqs == expected_seqs and self.links_claimed == offered % _MODULUS

    def result(self) -> LogVerification:
        deviations = self.deviations
        if any(d.kind in ("link_mismatch", "start_mismatch") for d in deviations) and self._reordered():
            deviations = [
                Deviation(d.line, d.kind, "reorder") if d.kind in ("link_mismatch", "start_mismatch") else d
                for d in deviations
            ]
        expected = []
        for head in self.heads:
            if head in self.found:
                line, index = self.found[head]
                expected.append(ExpectedHead(head, line, self.events - index))
            else:
                expected.append(ExpectedHead(head))
                deviations = [*deviations, Deviation(None, "head_missing")]
        return LogVerification(
            self.events,
            self.lines,
            self.previous[0] if self.previous is not None else None,
            tuple(deviations),
            tuple(expected),
        )


def verify_entries(entries: Iterable[Entry], expect_heads: Sequence[str] = ()) -> LogVerification:
    """Verify a stream of entries (``iter_entries``); ``vault log --show`` feeds the same stream it shows."""
    verifier = _Verifier([normalize_head(head) for head in expect_heads])
    for entry in entries:
        verifier.feed(entry)
    return verifier.result()


def verify(
    location: VaultLocation, expect_heads: Sequence[str] = (), timeout_s: float = LOCK_TIMEOUT_S
) -> LogVerification:
    """Verify the log of a present vault (``vault verify``, CLI-09). A missing log is the single deviation
    log_missing. Raises errors.vault.bad_head before anything is read, the errors of store.require_present,
    VaultLocked and OSError."""
    heads = list(dict.fromkeys(normalize_head(head) for head in expect_heads))
    current = location.refreshed()
    require_present(current)
    try:
        size = snapshot(current, timeout_s)
        return verify_entries(iter_entries(current.log, size), heads)
    except FileNotFoundError:
        return LogVerification(0, 0, None, (Deviation(None, "log_missing"),), tuple(map(ExpectedHead, heads)))


# --- appending --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class AppendOutcome:
    """The result of an append: ``written`` with the new event, or why nothing was written. Callers that need
    the vault turn it into a tool error with ``error()``; automatic events only warn (p6 decisions 4)."""

    status: AppendStatus
    event: AccessEvent | None = None
    link_part: str | None = None

    def error(self) -> NeuroGridError:
        """The tool error of a status other than written: errors.vault.not_found (no_vault), .link {part},
        .locked, .log_missing, .not_writable, .log_damaged."""
        if self.status == "written":
            raise ValueError("the event was written")
        if self.status == "link":
            return UnsafePathError("vault.link", part=self.link_part)
        if self.status == "locked":
            return VaultLocked()
        if self.status == "no_vault":
            return InputError("vault.not_found")
        return InputError(f"vault.{self.status}")


def append(
    location: VaultLocation,
    *,
    role: str | None,
    action: str,
    objects: Sequence[str],
    purpose: str | None,
    approval_ref: str | None,
    now: Callable[[], datetime] = utc_now,
    timeout_s: float = LOCK_TIMEOUT_S,
) -> AppendOutcome:
    """Append one event under the vault lock. Never raises for the statuses of AppendOutcome; raises the
    tool errors of check_fields for invalid fields."""
    objects = list(objects)
    check_fields(role=role, action=action, objects=objects, purpose=purpose, approval_ref=approval_ref)
    current = location.refreshed()
    if current.state == "link":
        return AppendOutcome("link", link_part=current.link_part)
    if current.state != "present":
        return AppendOutcome("no_vault")
    try:
        with exclusive(current.lock, timeout_s) as held:
            return append_locked(
                current,
                held,
                role=role,
                action=action,
                objects=objects,
                purpose=purpose,
                approval_ref=approval_ref,
                now=now,
            )
    except VaultLocked:
        return AppendOutcome("locked")
    except UnsafePathError:
        return AppendOutcome("link", link_part=VAULT_LOCK)
    except OSError:
        return AppendOutcome("not_writable")


def append_locked(
    location: VaultLocation,
    held: HeldLock,
    *,
    role: str | None,
    action: str,
    objects: Sequence[str],
    purpose: str | None,
    approval_ref: str | None,
    now: Callable[[], datetime] = utc_now,
) -> AppendOutcome:
    """Append one event while the caller holds the vault lock of ``location`` (ValueError otherwise); never
    locks. The tail of the log (at most TAIL_BYTES) gives the previous entry: an empty log starts at GENESIS
    with seq 1, a log without a well-formed line in the tail is log_damaged. A last line without LF (torn by
    a crash) is terminated first; it stays a malformed line, the new entry links past it. One write of the
    whole line on the O_APPEND handle, then fsync. Never raises for the statuses of AppendOutcome."""
    if not held.covers(location.lock):
        raise ValueError("append_locked needs the held lock of this vault")
    objects = list(objects)
    check_fields(role=role, action=action, objects=objects, purpose=purpose, approval_ref=approval_ref)
    current = location.refreshed()
    if current.state == "link":
        return AppendOutcome("link", link_part=current.link_part)
    if current.state != "present":
        return AppendOutcome("no_vault")
    try:
        fd = _open_log(current.log)
    except FileNotFoundError:
        return AppendOutcome("log_missing")
    except OSError as exc:
        if _os.is_link_error(exc):
            return AppendOutcome("link", link_part=VAULT_LOG)
        return AppendOutcome("not_writable")
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            return AppendOutcome("not_writable")
        tail = _tail(fd, info.st_size)
        if tail is None:
            return AppendOutcome("log_damaged")
        previous, terminate = tail
        seq, previous_hash = (1, GENESIS) if previous is None else (previous.seq + 1, previous.hash)
        body = _body(seq, format_time(now()), role, action, objects, purpose, approval_ref, previous_hash)
        event = AccessEvent.model_validate({**body, "hash": event_hash(body)}, strict=True)
        data = (b"\n" if terminate else b"") + compact_event(event) + b"\n"
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view) :]
        os.fsync(fd)
    except OSError:
        return AppendOutcome("not_writable")
    finally:
        with suppress(OSError):  # after fsync the entry is on disk
            os.close(fd)
    return AppendOutcome("written", event)


Writability = Literal["writable", "log_missing", "not_writable"]


def probe_writable(location: VaultLocation) -> Writability:
    """Whether an event could be appended now (CORE-NV03-02, A-30 "Warnung und Befund" for a read-only
    vault), without writing a byte to the log: the log is opened for appending as ``append_locked`` opens it
    (not created when it is missing: log_missing), and the lock file as ``exclusive`` opens it (created empty
    when it is missing, as every append does; it is never part of the manifest). Raises the errors of
    store.require_present and UnsafePathError errors.vault.link for a linked log or lock file."""
    current = location.refreshed()
    require_present(current)
    try:
        fd = _open_log(current.log)
    except FileNotFoundError:
        return "log_missing"
    except OSError as exc:
        if _os.is_link_error(exc):
            raise UnsafePathError("vault.link", part=VAULT_LOG) from None
        return "not_writable"
    try:
        regular = stat.S_ISREG(os.fstat(fd).st_mode)
    finally:
        os.close(fd)
    if not regular:
        return "not_writable"
    if is_link(current.lock):
        raise UnsafePathError("vault.link", part=VAULT_LOCK)
    try:
        fd = _os.open_lock(current.lock)
    except OSError as exc:
        if _os.is_link_error(exc):
            raise UnsafePathError("vault.link", part=VAULT_LOCK) from None
        return "not_writable"
    os.close(fd)
    return "writable"


def _open_log(path: Path) -> int:
    """The log for appending; one retry after RETRY_DELAY_S on a Windows sharing violation."""
    try:
        return _os.open_log(path)
    except OSError as exc:
        if not _os.is_sharing_violation(exc):
            raise
    time.sleep(RETRY_DELAY_S)
    return _os.open_log(path)


def _tail(fd: int, size: int) -> tuple[AccessEvent | None, bool] | None:
    """(the last well-formed entry in the last TAIL_BYTES of the log or None for an empty log, whether the
    log needs an LF before the next entry); None if the tail holds no well-formed line (log_damaged)."""
    start = max(0, size - TAIL_BYTES - 1)  # one byte more: was the window's first line cut?
    os.lseek(fd, start, os.SEEK_SET)
    data = bytearray()
    while len(data) < size - start:
        chunk = os.read(fd, size - start - len(data))
        if not chunk:
            break
        data += chunk
    if start == 0:
        content = bytes(data[len(_BOM) :]) if data.startswith(_BOM) else bytes(data)
        if not content:  # empty, or only a BOM: the chain starts at GENESIS
            return None, False
    else:
        cut = data.find(b"\n")
        if cut < 0:
            return None
        content = bytes(data[cut + 1 :])
    lines = content.split(b"\n")
    terminate = lines[-1] != b""
    if not terminate:
        lines.pop()
    for line in reversed(lines):
        entry = parse_line(line[:-1] if line.endswith(b"\r") else line)
        if entry.event is not None:
            return entry.event, terminate
    return None
