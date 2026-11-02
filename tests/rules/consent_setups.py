"""Setups for the M14 rule cases (CORE-M14-01 consent.covered; A-30, A-91). Each builds a copy of the fixture
with a vault (vault.store.init_vault, what ``vault init`` does) and consent records in the canonical form
(model.consent.dump_consents, what ``vault consent add`` writes); vaults are never committed as fixtures.

bids_ai_ok has six subjects: sub-01..04 in train (training), sub-05 in val and sub-06 in test (validation by
default). Every setup runs at the reference date AS_OF.

- ``consent_all``: every subject permits training and validation;
- ``consent_no_training``: sub-02 (train) permits validation only;
- ``consent_withdrawn``: sub-03 withdrew with version 2 on 2026-06-01; ``consent_before_withdrawal`` checks
  the same records on 2026-05-31;
- ``consent_missing_subject``: no record of sub-04;
- ``consent_future``: the only record of sub-05 is dated after AS_OF;
- ``consent_empty``: a vault with ``consents: []`` (no consent data);
- ``consent_excepted``: consent_no_training with an exception for sub-02 and training (A-14);
- ``consent_sharing_missing`` / ``consent_sharing``: bids_ok without splits, [consent] dataset_uses = sharing
  in .neurogrid/neurogrid.toml, records without and with sharing;
- ``consent_subject_unknown``: edf_ok (a raw folder without mapping) with rec_a.edf in train and consent
  records, so the subject of a recording that needs a use is unknown;
- ``consent_single_file``: a single data file as the target.

The neurogrid.toml of a setup lies in the copy's .neurogrid folder: its project root is the copy, where the
vault is (A-66).
"""

from __future__ import annotations

import shutil
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path

from neurogrid.model.consent import ConsentFile, ConsentScope, dump_consents
from neurogrid.vault import store

AS_OF = date(2026, 11, 20)
BOTH = ("training", "validation")
Setup = Callable[[Path, Path], tuple[Path, dict[str, object]]]


def record(subject: str, uses: Sequence[str] = BOTH, **fields: object) -> ConsentScope:
    values: dict[str, object] = {"subject": subject, "version": 1, "date": date(2026, 1, 1)}
    values.update(fields)
    return ConsentScope(permitted_uses=tuple(uses), **values)  # type: ignore[arg-type]


def write_vault(folder: Path, records: Sequence[ConsentScope]) -> store.VaultLocation:
    """A vault at the default location of ``folder`` with these records."""
    location = store.locate(folder, store.DEFAULT_VAULT_PATH)
    store.init_vault(location)
    location.consents.write_bytes(dump_consents(ConsentFile(consents=list(records))))
    return location


def _setup(
    records: Sequence[ConsentScope],
    *,
    toml: str | None = None,
    as_of: date = AS_OF,
    change: Callable[[Path], None] | None = None,
) -> Setup:
    def setup(fixture: Path, tmp: Path) -> tuple[Path, dict[str, object]]:
        folder = tmp / fixture.name
        shutil.copytree(fixture, folder)
        write_vault(folder, records)
        if toml is not None:
            (folder / ".neurogrid" / "neurogrid.toml").write_text(toml, encoding="utf-8")
        if change is not None:
            change(folder)
        return folder, {"as_of": as_of}

    return setup


ALL = [record(f"sub-0{n}") for n in range(1, 7)]
NO_TRAINING = [r if r.subject != "sub-02" else record("sub-02", ("validation",)) for r in ALL]
WITHDRAWN = [*ALL, record("sub-03", (), version=2, date=date(2026, 6, 1), withdrawn=True)]
EXCEPTION = (
    '[[exceptions]]\nrule = "CORE-M14-01"\nobject = "sub-02"\nsubkey = "training"\n'
    'reason = "re-consent requested"\napproved_by = "QA"\n'
)
SHARING = '[consent]\ndataset_uses = ["sharing"]\n'


def _train_split(folder: Path) -> None:
    (folder / ".neurogrid" / "splits.tsv").write_text(
        "recording\tsplit\nrec_a.edf\ttrain\n", encoding="utf-8"
    )


def _single_file(fixture: Path, tmp: Path) -> tuple[Path, dict[str, object]]:
    return fixture / "rec_a.edf", {"as_of": AS_OF}


CONSENT_SETUPS: dict[str, Setup] = {
    "consent_all": _setup(ALL),
    "consent_no_training": _setup(NO_TRAINING),
    "consent_withdrawn": _setup(WITHDRAWN),
    "consent_before_withdrawal": _setup(WITHDRAWN, as_of=date(2026, 5, 31)),
    "consent_missing_subject": _setup([r for r in ALL if r.subject != "sub-04"]),
    "consent_future": _setup(
        [r if r.subject != "sub-05" else record("sub-05", date=date(2027, 1, 1)) for r in ALL]
    ),
    "consent_empty": _setup([]),
    "consent_excepted": _setup(NO_TRAINING, toml=EXCEPTION),
    "consent_sharing_missing": _setup([record("sub-01"), record("sub-02")], toml=SHARING),
    "consent_sharing": _setup([record("sub-01", ("sharing",)), record("sub-02", ("sharing",))], toml=SHARING),
    "consent_subject_unknown": _setup([record("sub-01")], change=_train_split),
    "consent_single_file": _single_file,
}
