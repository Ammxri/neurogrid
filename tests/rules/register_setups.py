"""Setups for the rule cases of the vault registers (CORE-NV04-01, CORE-NV05-01/02/03; NV-F04, NV-F05; A-30,
A-93, A-94). Each makes a copy of the fixture with a vault made by ``vault init`` (its registers and PIA files
from the templates) and two check events of ``data_steward`` at FIXED (vault_setups.vault_copy), changes what
the case is about and checks at AS_OF, so that the events lie before the day before the reference date:

- roles: ``reg_roles_permitted`` (the role may check everything), ``reg_roles_action`` (the role may only
  read), ``reg_roles_unknown`` (the register names another role), ``reg_roles_object`` (an event names an
  object no pattern of the role covers), ``reg_roles_star`` (the role's pattern ``*`` does not cover the
  object ``**``), ``reg_roles_no_file`` (roles.yaml removed), ``reg_roles_empty`` (the template,
  ``roles: []``), ``reg_roles_no_role`` (a read event without a role, as scan records it),
  ``reg_roles_late`` (every event on the reference date: none before the cut), ``reg_roles_excepted`` (an
  exception for the pair);
- retention and PIA: ``reg_complete`` (entries for pia and access_log, one PIA file edited without
  placeholders), ``reg_template`` (the templates only), ``reg_no_retention`` (retention.yaml removed),
  ``reg_object_missing`` (an entry for roles, roles.yaml removed), ``reg_log_truncated`` (the first log line
  removed), ``reg_pia_missing`` (both PIA files removed), ``reg_pia_open`` (an edited PIA file with
  placeholders left), ``reg_ending``, ``reg_ended``, ``reg_review_due`` (the reminder of CORE-NV05-03).
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

from vault_setups import FIXED, vault_copy  # type: ignore[import-not-found]

from neurogrid.vault import ledger
from neurogrid.vault.store import VaultLocation, pia_template

AS_OF = date(2026, 11, 20)  # FIXED (2026-10-29) lies before the cut 2026-11-19T00:00:00Z
Setup = Callable[[Path, Path], tuple[Path, dict[str, object]]]
STEWARD = "  - {role: data_steward, description: Prepares the dataset, actions: [%s], objects: [%s]}\n"
PERMITTED = "format_version: 1\nroles:\n" + STEWARD % ("read, check", "'**'")
RETENTION = (
    "format_version: 1\nobjects:\n"
    "  - {object: pia, created: 2026-10-01, min_until: 2029-10-01}\n"
    "  - {object: access_log, created: 2026-10-01, min_until: 2029-10-01%s}\n"
)
ACCESS_LOG_ONLY = "format_version: 1\nobjects:\n  - {object: access_log, created: %s, min_until: %s}\n"
EDITED_PIA = (
    b"# Personal information protection impact assessment\n\nAssessed on 2026-10-20 by the QA role.\n"
)


def _event(
    location: VaultLocation, *, role: str | None, action: str, objects: list[str], when: datetime
) -> None:
    outcome = ledger.append(
        location, role=role, action=action, objects=objects, purpose=None, approval_ref=None, now=lambda: when
    )
    assert outcome.status == "written", outcome


def _setup(change: Callable[[Path, VaultLocation], None], *, events: int = 2) -> Setup:
    def setup(fixture: Path, tmp: Path) -> tuple[Path, dict[str, object]]:
        folder, location = vault_copy(fixture, tmp, events=events)
        change(folder, location)
        return folder, {"as_of": AS_OF}

    return setup


def _roles(text: str) -> Callable[[Path, VaultLocation], None]:
    def change(_folder: Path, location: VaultLocation) -> None:
        location.roles.write_text(text, encoding="utf-8")

    return change


def _object_event(_folder: Path, location: VaultLocation) -> None:
    location.roles.write_text(
        PERMITTED + STEWARD.replace("data_steward", "QA") % ("read", "'sub-02/**'"), encoding="utf-8"
    )
    _event(location, role="QA", action="read", objects=["sub-01/eeg/x.edf"], when=FIXED)


def _no_role(_folder: Path, location: VaultLocation) -> None:
    location.roles.write_text(PERMITTED, encoding="utf-8")
    _event(location, role=None, action="read", objects=["**"], when=FIXED)


def _late(_folder: Path, location: VaultLocation) -> None:
    location.roles.write_text(PERMITTED, encoding="utf-8")
    for _ in range(2):
        _event(
            location,
            role="data_steward",
            action="check",
            objects=["**"],
            when=datetime(2026, 11, 20, 8, tzinfo=UTC),
        )


def _excepted(folder: Path, location: VaultLocation) -> None:
    location.roles.write_text("format_version: 1\nroles:\n" + STEWARD % ("read", "'**'"), encoding="utf-8")
    (folder / ".neurogrid" / "neurogrid.toml").write_text(
        '[[exceptions]]\nrule = "CORE-NV04-01"\nsubkey = "data_steward/check"\n'
        'reason = "checks were agreed with the ethics committee"\n',
        encoding="utf-8",
    )


def _retention(review: str = "", *, edit_pia: bool = True) -> Callable[[Path, VaultLocation], None]:
    def change(_folder: Path, location: VaultLocation) -> None:
        location.retention.write_text(RETENTION % review, encoding="utf-8")
        if edit_pia:
            location.pia_files[1].write_bytes(EDITED_PIA)

    return change


def _retention_text(text: str) -> Callable[[Path, VaultLocation], None]:
    def change(_folder: Path, location: VaultLocation) -> None:
        location.retention.write_text(text, encoding="utf-8")
        location.pia_files[1].write_bytes(EDITED_PIA)

    return change


def _no_retention(_folder: Path, location: VaultLocation) -> None:
    location.retention.unlink()


def _object_missing(folder: Path, location: VaultLocation) -> None:
    _retention_text(RETENTION % "" + "  - {object: roles, created: 2026-10-01, min_until: 2029-10-01}\n")(
        folder, location
    )
    location.roles.unlink()


def _log_truncated(folder: Path, location: VaultLocation) -> None:
    _retention()(folder, location)
    lines = location.log.read_bytes().splitlines(keepends=True)
    location.log.write_bytes(b"".join(lines[1:]))


def _pia_missing(folder: Path, location: VaultLocation) -> None:
    _retention(edit_pia=False)(folder, location)
    shutil.rmtree(location.pia_folder)


def _pia_open(folder: Path, location: VaultLocation) -> None:
    _retention(edit_pia=False)(folder, location)
    location.pia_files[1].write_bytes(pia_template("pia.en.md") + b"\nPurpose described below.\n")


def _nothing(_folder: Path, _location: VaultLocation) -> None:
    pass


REGISTER_SETUPS: dict[str, Setup] = {
    "reg_roles_permitted": _setup(_roles(PERMITTED)),
    "reg_roles_action": _setup(_roles("format_version: 1\nroles:\n" + STEWARD % ("read", "'**'"))),
    "reg_roles_unknown": _setup(
        _roles("format_version: 1\nroles:\n" + STEWARD.replace("data_steward", "QA") % ("check", "'**'"))
    ),
    "reg_roles_object": _setup(_object_event),
    "reg_roles_star": _setup(_roles("format_version: 1\nroles:\n" + STEWARD % ("check", "'*'"))),
    "reg_roles_no_file": _setup(lambda _folder, location: location.roles.unlink()),
    "reg_roles_empty": _setup(_nothing),
    "reg_roles_no_role": _setup(_no_role, events=0),
    "reg_roles_late": _setup(_late, events=0),
    "reg_roles_excepted": _setup(_excepted),
    "reg_complete": _setup(_retention()),
    "reg_template": _setup(_nothing),
    "reg_no_retention": _setup(_no_retention),
    "reg_object_missing": _setup(_object_missing),
    "reg_log_truncated": _setup(_log_truncated),
    "reg_pia_missing": _setup(_pia_missing),
    "reg_pia_open": _setup(_pia_open),
    "reg_ending": _setup(_retention_text(ACCESS_LOG_ONLY % ("2023-12-01", "2026-12-31"))),  # 41 days left
    "reg_ended": _setup(_retention_text(ACCESS_LOG_ONLY % ("2023-01-01", "2026-01-01"))),
    "reg_review_due": _setup(_retention(", review_at: 2026-11-01")),
}
