"""Retention and the impact assessment of the vault (NV-F05; A-30, A-94, p9 decisions 4): CORE-NV05-01 the
retention periods are complete (retention.complete, warning), CORE-NV05-02 the impact assessment was edited
(pia.edited, warning) and CORE-NV05-03 the reminder before a minimum retention ends (retention.ending, info,
parameter ``days``).

The vault of the run is ctx.vault, as for the access log (checks.access): a single file as target has no vault
(not applicable, vault.single_file), a dataset without a vault folder is not checkable (vault.not_found), a
link ends check with exit 2 before the data are read. retention.yaml is read before the signal pass
(ctx.retention; an invalid file, a minimum retention below three years included, is exit 2 there); the PIA
files and the presence of the other vault files are looked at when the checks measure. Nothing here depends on
the access log beyond its first well-formed entry under the snapshot rule, and nothing on the run's own event,
so two runs on the same data stay byte-identical (NG-N03).

- retention.complete: a vault without retention.yaml is one failed dataset-level measurement
  (retention.no_file); otherwise one measurement per object in REQUIRED and per listed object (subkey: the
  object): failed for a required object without an entry (retention.entry_missing), an object whose file is
  missing (retention.object_missing; pia: neither PIA file) or an access log whose first well-formed entry
  does not link to the genesis hash (retention.log_truncated: entries at the start were removed), else
  passed.
- pia.edited: one dataset-level measurement: failed without a PIA file (pia.missing), when every PIA file
  equals its template apart from a BOM and CRLF line ends (pia.template_unedited) or when every edited file
  still holds a placeholder marker (pia.fields_open); not checkable when a PIA file is too large or cannot be
  read (pia.unreadable); else passed (one edited file without a marker suffices). Details: counts only.
- retention.ending: one measurement per entry (subkey: the object), the value the days from the reference date
  to min_until; failed when the value is at most ``days`` (default 90) or the review date is reached. The
  reason is neutral (A-30: retention.ended for a past min_until, retention.review_due for a reached review
  date, else retention.ending): NeuroGrid reminds, the user decides on further retention or deletion after
  their own legal review; EEG data have no retention period here. No entries: not applicable.

Details never hold texts of the files, only the object, dates of retention.yaml and counts (A-51).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date
from pathlib import PurePosixPath
from typing import Any

from neurogrid.checks.access import measurement_at, present_vault
from neurogrid.checks.context import CheckContext
from neurogrid.kernel.findings import Finding, Notice, Severity, Status
from neurogrid.kernel.rules import CheckSpec, Evaluation, Measurement, ParamSpec, ParamValue, is_true
from neurogrid.model.retention import REQUIRED, RETENTION_OBJECTS, RetentionItem
from neurogrid.vault import ledger
from neurogrid.vault import lock as vault_lock
from neurogrid.vault import retention as vault_retention
from neurogrid.vault.lock import VaultLocked
from neurogrid.vault.pia import read_pia
from neurogrid.vault.store import DEFAULT_VAULT_PATH, RETENTION_FILE, VaultLocation

RETENTION_COMPLETE = "retention.complete"
PIA_EDITED = "pia.edited"
RETENTION_ENDING = "retention.ending"
CHECKS = frozenset({RETENTION_COMPLETE, PIA_EDITED, RETENTION_ENDING})
DEFAULT_DAYS = 90  # A-30: the reminder starts at most 90 days before min_until
# Every reason and notice key of this module (some are passed through variables), for the language tables
REASONS = (
    "retention.no_file",
    "retention.entry_missing",
    "retention.object_missing",
    "retention.log_truncated",
    "retention.ending",
    "retention.ended",
    "retention.review_due",
    "retention.no_entries",
    "pia.missing",
    "pia.template_unedited",
    "pia.fields_open",
    "pia.unreadable",
)
NOTICES = ("notice.retention_reminder",)
# retention.yaml as a finding names it: only in the dataset's default vault (a fixed name in .neurogrid/,
# KNOWN_CONTROL_FILES, shown in clear, A-51), as the access log of checks.access
DEFAULT_RETENTION = (PurePosixPath(DEFAULT_VAULT_PATH) / RETENTION_FILE).as_posix()


def _ending(measurement: Measurement, params: Mapping[str, ParamValue]) -> Evaluation:
    """Failed when the days to min_until are at most ``days`` or the review date is reached
    (details.review_due); the threshold is ``days``."""
    days = params["days"]
    review_due = measurement.details.get("review_due") is True
    return Evaluation(passed=not (measurement.value <= days or review_due), threshold=days)


SPECS = (
    CheckSpec(id=RETENTION_COMPLETE, evaluate=is_true),
    CheckSpec(id=PIA_EDITED, evaluate=is_true),
    CheckSpec(id=RETENTION_ENDING, evaluate=_ending, params={"days": ParamSpec("integer", DEFAULT_DAYS)}),
)


def _as_of(ctx: CheckContext) -> date:
    return ctx.as_of or date.today()  # the pipeline always sets the reference date


def _retention_file(ctx: CheckContext, location: VaultLocation) -> str | None:
    default = ctx.root.joinpath(*PurePosixPath(DEFAULT_VAULT_PATH).parts)
    return DEFAULT_RETENTION if location.path == default else None


def _loaded(ctx: CheckContext, location: VaultLocation) -> vault_retention.LoadedRetention:
    """retention.yaml as the pipeline read it before the signal pass (read now only for a caller that did
    not)."""
    return ctx.retention if ctx.retention is not None else vault_retention.load_for_check(location)


def _object_present(location: VaultLocation, name: str) -> bool:
    if name == "pia":
        return any(path.is_file() for path in location.pia_files)
    paths = {
        "access_log": location.log,
        "roles": location.roles,
        "risks": location.risks,
        "consents": location.consents,
    }
    return paths[name].is_file()


def _log_problem(location: VaultLocation) -> tuple[str, str] | None:
    """(state, reason) when the start of the access log is not as NeuroGrid wrote it: retention.log_truncated
    (the first well-formed entry does not link to GENESIS or is not entry 1), or not checkable when the log
    cannot be read now; None for an intact start or a log without a well-formed entry."""
    try:
        first = ledger.first_entry(location, vault_lock.LOCK_TIMEOUT_S)
    except VaultLocked:
        return "not_checkable", "vault.locked"
    except FileNotFoundError:
        return "measured", "retention.object_missing"
    except OSError:
        return "not_checkable", "vault.log_unreadable"
    if first is not None and (first.previous_hash != ledger.GENESIS or first.seq != 1):
        return "measured", "retention.log_truncated"
    return None


def _object_measurement(
    location: VaultLocation, file: str | None, name: str, entries: Mapping[str, RetentionItem]
) -> Measurement:
    details = {"object": name}
    common: dict[str, Any] = {
        "check_id": RETENTION_COMPLETE,
        "object": "dataset",
        "subkey": name,
        "file": file,
    }
    if name not in entries:
        return Measurement(**common, value=False, reason="retention.entry_missing", details=details)
    if not _object_present(location, name):
        return Measurement(**common, value=False, reason="retention.object_missing", details=details)
    if name == "access_log":
        problem = _log_problem(location)
        if problem is not None:
            state, reason = problem
            if state == "not_checkable":
                return Measurement(**common, state="not_checkable", reason=reason, details=details)
            return Measurement(**common, value=False, reason=reason, details=details)
    return Measurement(**common, value=True, details=details)


def measure_complete(ctx: CheckContext) -> list[Measurement]:
    found = present_vault(ctx, RETENTION_COMPLETE)
    if isinstance(found, list):
        return found
    file = _retention_file(ctx, found)
    loaded = _loaded(ctx, found)
    if loaded.file is None:
        return measurement_at(RETENTION_COMPLETE, file, value=False, reason="retention.no_file")
    entries = loaded.file.by_object()
    names = [name for name in RETENTION_OBJECTS if name in REQUIRED or name in entries]
    return [_object_measurement(found, file, name, entries) for name in names]


def measure_pia(ctx: CheckContext) -> list[Measurement]:
    found = present_vault(ctx, PIA_EDITED)
    if isinstance(found, list):
        return found
    reading = read_pia(found)
    details = {"files": reading.files, "open_fields": reading.open_fields}
    if reading.state == "unreadable":
        return measurement_at(
            PIA_EDITED, None, state="not_checkable", reason="pia.unreadable", details=details
        )
    passed = reading.state == "edited"
    reason = None if passed else f"pia.{reading.state}"
    return measurement_at(PIA_EDITED, None, value=passed, reason=reason, details=details)


def measure_ending(ctx: CheckContext) -> list[Measurement]:
    found = present_vault(ctx, RETENTION_ENDING)
    if isinstance(found, list):
        return found
    file = _retention_file(ctx, found)
    loaded = _loaded(ctx, found)
    if loaded.file is None or not loaded.file.objects:
        return measurement_at(RETENTION_ENDING, file, state="not_applicable", reason="retention.no_entries")
    as_of = _as_of(ctx)
    out: list[Measurement] = []
    order = {name: index for index, name in enumerate(RETENTION_OBJECTS)}
    for item in sorted(loaded.file.objects, key=lambda entry: order[entry.object]):
        days = (item.min_until - as_of).days
        review_due = item.review_at is not None and item.review_at <= as_of
        if days < 0:
            reason = "retention.ended"
        elif review_due:
            reason = "retention.review_due"
        else:
            reason = "retention.ending"
        details = {
            "object": item.object,
            "min_until": item.min_until.isoformat(),
            "review_at": item.review_at.isoformat() if item.review_at is not None else None,
            "review_due": review_due,
        }
        out.append(
            Measurement(
                check_id=RETENTION_ENDING,
                object="dataset",
                subkey=item.object,
                file=file,
                value=days,
                reason=reason,
                details=details,
            )
        )
    return out


MEASURERS = {
    RETENTION_COMPLETE: measure_complete,
    PIA_EDITED: measure_pia,
    RETENTION_ENDING: measure_ending,
}


def notices(findings: Iterable[Finding]) -> list[Notice]:
    """notice.retention_reminder {count} (warning level, so check prints it on the console): the entries of
    retention.yaml for which a CORE-NV05-03 rule reminds (failed findings; an excepted one does not count).
    The count only: no object, date or subject (A-51)."""
    count = sum(
        1
        for finding in findings
        if finding.message_key == f"check.{RETENTION_ENDING}" and finding.status is Status.FAILED
    )
    if not count:
        return []
    return [Notice(level=Severity.WARNING, message_key="notice.retention_reminder", params={"count": count})]
