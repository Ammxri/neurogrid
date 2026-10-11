"""PRD §10 data model: every PRD field exists under its English name (DM-01 to DM-10, D-03)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import BaseModel

from neurogrid.kernel.findings import Finding
from neurogrid.model.dataset import (
    Annotation,
    Channel,
    Dataset,
    ProcessingStep,
    Recording,
    Split,
    Subject,
)

# PRD field (German) -> English field, per object. ConsentScope and AccessEvent follow in P6 (DM-08, DM-09).
MAPPING: dict[type[BaseModel], dict[str, str]] = {
    Dataset: {
        "id": "id",
        "name": "name",
        "version": "version",
        "quelle": "source",
        "lizenz": "license",
        "regelpakete": "rulepacks",
        "manifest_hash": "manifest_hash",
    },
    Subject: {
        "pseudo_id": "pseudo_id",
        "alter_gruppe": "age_group",
        "geschlecht": "sex",
        "diagnose_code": "diagnosis_code",
        "consent_ref": "consent_ref",
    },
    Recording: {
        "id": "id",
        "subject": "subject",
        "session": "session",
        "task": "task",
        "format": "format",
        "pfad": "path",
        "abtastrate_hz": "sampling_rate_hz",
        "dauer_s": "duration_s",
        "geraet": "device",
        "elektrodentyp": "electrode_type",
        "referenz": "reference",
        "netzfrequenz_hz": "line_frequency_hz",
    },
    Channel: {
        "name": "name",
        "typ": "type",
        "einheit": "unit",
        "position": "position",
        "impedanz_kohm": "impedance_kohm",
        "status": "status",
    },
    Annotation: {
        "onset_s": "onset_s",
        "dauer_s": "duration_s",
        "code": "code",
        "label": "label",
        "annotator_id": "annotator_id",
        "quelle": "source",
    },
    Split: {"name": "name", "recording_ids": "recording_ids"},
    ProcessingStep: {
        "schritt": "step",
        "werkzeug": "tool",
        "version": "version",
        "parameter": "parameters",
        "eingabe_hash": "input_hash",
        "ausgabe_hash": "output_hash",
    },
    Finding: {
        "regel_id": "rule_id",
        "klausel": "clause",
        "schweregrad": "severity",
        "status": "status",
        "messwert": "measured_value",
        "schwelle": "threshold",
        "objekt": "object",
        "belege": "details",
    },
}


@pytest.mark.parametrize("model", list(MAPPING), ids=lambda m: m.__name__)
def test_prd_fields_present(model: type[BaseModel]) -> None:
    missing = [english for english in MAPPING[model].values() if english not in model.model_fields]
    assert not missing, missing


def test_sensitive_fields_never_serialised() -> None:
    subject = Subject(pseudo_id="sub-01", age=34.5, diagnosis_code="G40", age_group="30-39")
    dumped = subject.model_dump(mode="json")
    assert "age" not in dumped and "diagnosis_code" not in dumped and dumped["age_group"] == "30-39"
    recording = Recording(id="rec-1", format="EDF", path="Zhang_San/rest.edf")
    assert "path" not in recording.model_dump(mode="json")


def test_enumerated_values() -> None:
    assert Recording(id="r", format="EDF", path="x", electrode_type="wet").electrode_type == "wet"
    assert Channel(name="Cz", type="EEG", status="bad").status == "bad"
    assert Split(name="test").recording_ids == []
    with pytest.raises(ValueError):
        Split(name="holdout")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        Recording(id="r", format="EDF", path="x", electrode_type="gel")  # type: ignore[arg-type]


def test_concept_supplement_fields() -> None:
    """KONZEPT 2.1: Ergänzungen per object."""
    supplements = {
        Dataset: {"is_bids"},
        Recording: {"run", "streamable", "metadata_sources"},
        Channel: {"recording_id", "resolution", "physical_range"},
        Annotation: {"recording_id"},
        Finding: {
            "rulepack",
            "rulepack_version",
            "source_status",
            "phase",
            "subkey",
            "file",
            "channel",
            "time_ranges",
            "message_key",
            "params",
            "key",
        },
    }
    for model, names in supplements.items():
        assert names <= set(model.model_fields), (model.__name__, names - set(model.model_fields))


@pytest.mark.parametrize("lang", ["en", "zh"])
def test_mapping_table_is_documented(lang: str) -> None:
    """D-03: the PRD → English mapping is published in the documentation, for every field of every object."""
    doc = (Path(__file__).parent.parent.parent / "docs" / lang / "data-model.md").read_text(encoding="utf-8")
    sections = {
        match.group(1): body
        for match, body in zip(
            re.finditer(r"^## (\w+)", doc, flags=re.M),
            re.split(r"^## \w+.*$", doc, flags=re.M)[1:],
            strict=True,
        )
    }
    for model, fields in MAPPING.items():
        assert model.__name__ in sections, (lang, model.__name__)
        rows = set(re.findall(r"^\| (\w+) \| (\w+)", sections[model.__name__], flags=re.M | re.ASCII))
        for prd, english in fields.items():
            assert (prd, english) in rows, (lang, model.__name__, prd)
