"""Dataset objects (PRD §10 DM-01 to DM-07).

PRD → English: Dataset{quelle→source, lizenz→license, regelpakete→rulepacks}; Subject{alter_gruppe→age_group,
geschlecht→sex, diagnose_code→diagnosis_code}; Recording{pfad→path, abtastrate_hz→sampling_rate_hz,
dauer_s→duration_s, geraet→device, elektrodentyp→electrode_type, referenz→reference,
netzfrequenz_hz→line_frequency_hz}; Channel{typ→type, einheit→unit, impedanz_kohm→impedance_kohm};
Annotation{dauer_s→duration_s, quelle→source}; ProcessingStep{schritt→step, werkzeug→tool,
parameter→parameters, eingabe_hash→input_hash, ausgabe_hash→output_hash}.

Fields marked ``exclude=True`` never leave the process (A-51): raw paths, raw age, diagnosis codes.
ProcessingStep lives in the kernel because the manifest repeats the steps (M13, A-82); it is re-exported here.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from neurogrid.kernel.provenance import ProcessingStep


class Dataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str | None = None
    version: str | None = None
    source: str | None = None
    license: str | None = None
    rulepacks: list[str] = Field(default_factory=list)
    manifest_hash: str | None = None
    is_bids: bool = False


class Subject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pseudo_id: str
    age_group: str | None = None
    sex: str | None = None
    diagnosis_code: str | None = Field(default=None, exclude=True)
    consent_ref: str | None = None
    age: float | None = Field(default=None, exclude=True)


class Channel(BaseModel):
    """PRD fields plus recording_id, resolution, physical_range (KONZEPT 2.1) and the channel's own
    sampling_rate_hz (EDF/BDF allow one rate per signal, M03)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    type: str
    unit: str | None = None
    position: str | None = None
    impedance_kohm: float | None = None
    status: Literal["good", "bad"] | None = None
    recording_id: str | None = None
    sampling_rate_hz: float | None = None
    resolution: float | None = None  # physical units per digital step
    physical_range: tuple[float, float] | None = None


class Recording(BaseModel):
    """PRD fields plus run, streamable and metadata_sources (KONZEPT 2.1).

    ``sampling_rate_hz`` is the lowest EEG channel rate (EEGLAB: ``srate``, one rate for all channels, A-77);
    the channels carry their own rates.
    ``metadata_sources`` names where each documented value came from (A-04: toml, sidecar, header).
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    subject: str | None = None
    session: str | None = None
    task: str | None = None
    run: str | None = None
    format: str
    path: str = Field(exclude=True)
    sampling_rate_hz: float | None = None
    duration_s: float | None = None
    device: str | None = None
    electrode_type: Literal["wet", "dry"] | None = None
    reference: str | None = None
    line_frequency_hz: float | None = None
    streamable: bool = True
    discontinuous: bool = False
    metadata_sources: dict[str, str] = Field(default_factory=dict)
    channels: list[Channel] = Field(default_factory=list)

    @property
    def eeg_channels(self) -> list[Channel]:
        return [ch for ch in self.channels if ch.type == "EEG"]


class Annotation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    onset_s: float
    duration_s: float
    code: str
    label: str | None = None
    annotator_id: str | None = None
    source: str | None = None
    recording_id: str | None = None


class Split(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal["train", "val", "test"]
    recording_ids: list[str] = Field(default_factory=list)


__all__ = ["Annotation", "Channel", "Dataset", "ProcessingStep", "Recording", "Split", "Subject"]
