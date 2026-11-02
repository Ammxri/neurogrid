"""The three approved MOABB datasets and the degraded views of them (NA-01, NA-03; area B "data and quality").

Approved (F1 B, owner's answer of 2026-11-02): Zhou2016 (motor imagery), Cho2017 (motor imagery, instead of
PhysionetMI) and Kalunga2016 (SSVEP). No other dataset (draft section 7). The numbers of the loader count,
not the MOABB documentation (draft 2.1, R-P11-9); the values below were read from moabb 1.7.2 as locked
(METADATA and the dataset objects, 2026-11-02).

Licences (owner: check size and licence of Cho2017 at the source before loading it, ask above 25 GB):
- Zhou2016: CC0-1.0 at the original source (figshare 2061654, API checked for the draft). moabb 1.7.2 does
  not download from there but from the BIDS conversion in Zenodo record 16534752, whose licence is not
  verified (the MOABB metadata says CC-BY-4.0): to be checked before the download.
- Cho2017: CC-BY-4.0 per the MOABB metadata only; not verified at GigaDB (draft 2.1). moabb 1.7.2 downloads
  the .mat files from the GigaDB mirror on Wasabi S3.
- Kalunga2016: CC-BY-4.0 at Zenodo record 2392979 (draft 2.1); moabb 1.7.2 downloads the FIF files there.

Storage (A-100): the data go to ``paths.MNE_DATA`` only. ``configure_storage`` sets the MNE variables in the
environment of this process, never in MNE's configuration file in the home folder.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from neuroarena import paths
from neuroarena.keys import Condition

if TYPE_CHECKING:
    from moabb.datasets.base import BaseDataset


@dataclass(frozen=True)
class DatasetSpec:
    """One approved dataset as NeuroArena uses it."""

    name: str  # MOABB class name in moabb.datasets (also the dataset part of every key and path)
    paradigm: str  # MOABB paradigm: "imagery" | "ssvep"
    events: tuple[str, ...]  # class labels as the MOABB loader names them; all of them are used
    n_subjects: int  # len(subject_list) of the loader
    n_eeg_channels: int  # [quality] min_channels of the research configuration (F5d)
    sampling_rate_hz: float
    line_frequency_hz: float  # [metadata.defaults] line_frequency_hz of the research configuration (A-101)
    mne_sign: str  # MOABB's signifier: the variable MNE_DATASETS_<sign>_PATH names the data folder
    licence: str  # SPDX identifier of the data at the original source
    licence_verified: bool  # False: taken from the MOABB metadata only, to be checked at the source
    licence_note: str
    source: str  # the original data: DOI or record
    download: str  # where moabb 1.7.2 downloads from
    paper_doi: str
    citation: str  # the reference of the MOABB loader's docstring (attribution, A-36; report: area D)


DATASETS: dict[str, DatasetSpec] = {
    "Zhou2016": DatasetSpec(
        name="Zhou2016",
        paradigm="imagery",
        events=("left_hand", "right_hand", "feet"),
        n_subjects=4,
        n_eeg_channels=14,
        sampling_rate_hz=250.0,
        line_frequency_hz=50.0,
        mne_sign="ZHOU2016",
        licence="CC0-1.0",
        licence_verified=True,
        licence_note=(
            "CC0-1.0 at the original source (figshare API, draft 2.1; the MOABB page and metadata say "
            "CC-BY-4.0). moabb 1.7.2 downloads the BIDS conversion of Zenodo record 16534752 instead, whose "
            "licence is not verified: check it before the download."
        ),
        source="doi:10.6084/m9.figshare.2061654",
        download="https://zenodo.org/api/records/16534752",
        paper_doi="10.1371/journal.pone.0162657",
        citation=(
            "Zhou B, Wu X, Lv Z, Zhang L, Guo X (2016) A Fully Automated Trial Selection Method for "
            "Optimization of Motor Imagery Based Brain-Computer Interface. PLoS ONE 11(9). "
            "https://doi.org/10.1371/journal.pone.0162657"
        ),
    ),
    "Cho2017": DatasetSpec(
        name="Cho2017",
        paradigm="imagery",
        events=("left_hand", "right_hand"),
        n_subjects=52,
        n_eeg_channels=64,
        sampling_rate_hz=512.0,
        line_frequency_hz=60.0,
        mne_sign="GIGADB",
        licence="CC-BY-4.0",
        licence_verified=False,
        licence_note=(
            "CC-BY-4.0 per the MOABB metadata only; not verified at GigaDB (draft 2.1). The owner's answer "
            "(F1 B): check size and licence at the source before loading, ask above 25 GB."
        ),
        source="doi:10.5524/100295",
        download="https://s3.ap-northeast-1.wasabisys.com/gigadb-datasets/live/pub/10.5524/100001_101000/100295/mat_data/",
        paper_doi="10.1093/gigascience/gix034",
        citation=(
            "Cho, H., Ahn, M., Ahn, S., Kwon, M. and Jun, S.C., 2017. EEG datasets for motor imagery brain "
            "computer interface. GigaScience. https://doi.org/10.1093/gigascience/gix034"
        ),
    ),
    "Kalunga2016": DatasetSpec(
        name="Kalunga2016",
        paradigm="ssvep",
        events=("13", "17", "21", "rest"),
        n_subjects=12,
        n_eeg_channels=8,
        sampling_rate_hz=256.0,
        line_frequency_hz=50.0,
        mne_sign="SSVEPEXO",
        licence="CC-BY-4.0",
        licence_verified=True,
        licence_note="CC-BY-4.0 at Zenodo record 2392979 (draft 2.1).",
        source="https://zenodo.org/record/2392979",
        download="https://zenodo.org/record/2392979/files/",
        paper_doi="10.1016/j.neucom.2016.01.007",
        citation=(
            'Emmanuel K. Kalunga, Sylvain Chevallier, Quentin Barthelemy. "Online SSVEP-based BCI using '
            'Riemannian Geometry". Neurocomputing, 2016. arXiv report: https://arxiv.org/abs/1501.03227'
        ),
    ),
}


def configure_storage(mne_data: Path = paths.MNE_DATA) -> None:
    """Point MNE and MOABB at ``mne_data`` for this process: ``MNE_DATA`` and ``MNE_DATASETS_<sign>_PATH``
    of every approved dataset in ``os.environ`` (MOABB's ``get_dataset_path`` reads them before it would
    write ``~/.mne/mne-python.json``). Creates the folder. Writes no configuration file."""
    raise NotImplementedError("area B")


def moabb_dataset(spec: DatasetSpec) -> BaseDataset:
    """The MOABB loader object of ``spec`` (``moabb.datasets.<spec.name>()``), unchanged."""
    raise NotImplementedError("area B")


def fetch(spec: DatasetSpec, subjects: tuple[int, ...] | None = None) -> None:
    """Download the data of ``spec`` (all subjects by default, F2 A) into the configured storage. The only
    function that is meant to download; never called by tests or CI (F11 B). Before the first call for
    Cho2017 and Zhou2016 the licence at the download source is checked (see the module docstring)."""
    raise NotImplementedError("area B")


def degraded_dataset(spec: DatasetSpec, condition: Condition, base: BaseDataset | None = None) -> BaseDataset:
    """A MOABB dataset whose raw data are those of ``base`` (default ``moabb_dataset(spec)``) after
    ``degradation.degrade`` for ``condition`` (A-103: on the raw signal, before filter and epoching).

    Contract (C relies on it):
    - ``get_data(subjects)`` returns ``{subject: {session: {run: raw}}}`` with the same subjects, sessions,
      runs, channels, montage, annotations and events as ``base``; only the EEG samples differ.
    - ``subject_list``, ``event_id``, ``interval``, ``paradigm`` and ``n_sessions`` are those of ``base``, so
      every MOABB paradigm that accepts ``base`` accepts it; ``code`` differs per condition.
    - For ``condition == CLEAN`` the raws equal those of ``base`` sample for sample.
    - Deterministic: the same (key, condition) gives byte-identical data in every call and process (seeds of
      ``degradation.seed_sequence``); nothing is cached on disk.
    The FIF export (``export.write_fifs``) and the decoders read exactly this view."""
    raise NotImplementedError("area B")
