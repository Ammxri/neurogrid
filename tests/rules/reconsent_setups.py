"""Setups for the CORE-M14-02 rule cases (consent.reconsent; NV-F06, A-30, A-95). Each builds a copy of the
fixture with a vault (vault.store.init_vault), consent records in the canonical form (consent_setups) and a
risk register risks.yaml written here; vaults are never committed as fixtures.

bids_ai_ok has six subjects: sub-01..04 in train (training), sub-05 in val and sub-06 in test (validation by
default). Every setup runs at the reference date consent_setups.AS_OF (2026-11-20).

- ``reconsent_reached``: every subject consented with version 2; R-train (training, version 2) and R-val
  (validation, version 1), both dated before AS_OF;
- ``reconsent_version_below``: every subject consented with version 1; R-train asks for version 2;
- ``reconsent_excepted``: reconsent_version_below with exceptions for sub-01..04 and R-train (A-14);
- ``reconsent_no_candidates``: a risk on commercial use, which no recording needs: passed for the dataset;
- ``reconsent_future``: R-train dated after AS_OF only (no risk judged yet);
- ``reconsent_no_consents``: R-train with ``consents: []`` (no consent data: not checkable, never failed).

A vault without risks (the empty template), no vault and a single file are the cases of consent_setups and of
the fixture itself.
"""

from __future__ import annotations

import shutil
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from consent_setups import AS_OF, Setup, record, write_vault  # type: ignore[import-not-found]

from neurogrid.model.consent import ConsentScope

ENTRY = (
    "  - {{id: {id}, date: {date}, description: {text}, affected_uses: [{uses}], min_consent_version: {v}}}\n"
)
TRAIN = ENTRY.format(id="R-train", date="2026-09-01", text="second model", uses="training", v=2)
VAL = ENTRY.format(id="R-val", date="2026-02-01", text="new partner", uses="validation", v=1)
COMMERCIAL = ENTRY.format(id="R-com", date="2026-02-01", text="licence", uses="commercial", v=1)
LATER = ENTRY.format(id="R-train", date="2026-12-01", text="second model", uses="training", v=2)
V1 = [record(f"sub-0{n}") for n in range(1, 7)]
V2 = [record(f"sub-0{n}", version=2) for n in range(1, 7)]
EXCEPTIONS = "".join(
    f'[[exceptions]]\nrule = "CORE-M14-02"\nobject = "sub-0{n}"\nsubkey = "R-train"\n'
    'reason = "ethics committee decided"\napproved_by = "QA"\n'
    for n in range(1, 5)
)


def register(*entries: str) -> bytes:
    return ("format_version: 1\nrisks:\n" + "".join(entries)).encode("utf-8")


def _setup(records: Sequence[ConsentScope], risks: bytes, *, toml: str | None = None) -> Setup:
    def setup(fixture: Path, tmp: Path) -> tuple[Path, dict[str, object]]:
        folder = tmp / fixture.name
        shutil.copytree(fixture, folder)
        location = write_vault(folder, records)
        location.risks.write_bytes(risks)
        if toml is not None:
            (folder / ".neurogrid" / "neurogrid.toml").write_text(toml, encoding="utf-8")
        return folder, {"as_of": AS_OF}

    return setup


RECONSENT_SETUPS: dict[str, Setup] = {
    "reconsent_reached": _setup(V2, register(TRAIN, VAL)),
    "reconsent_version_below": _setup(V1, register(TRAIN)),
    "reconsent_excepted": _setup(V1, register(TRAIN), toml=EXCEPTIONS),
    "reconsent_no_candidates": _setup(V1, register(COMMERCIAL)),
    "reconsent_future": _setup(V1, register(LATER)),
    "reconsent_no_consents": _setup([], register(TRAIN)),
}
assert date(2026, 9, 1) <= AS_OF < date(2026, 12, 1)  # TRAIN is judged, LATER is not
