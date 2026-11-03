"""The three approved MOABB datasets and the degraded views of them (NA-01, NA-03; area B "data and quality").

Approved (F1 B, owner's answer of 2026-11-02): Zhou2016 (motor imagery), Cho2017 (motor imagery, instead of
PhysionetMI) and Kalunga2016 (SSVEP). No other dataset (draft section 7). The numbers of the loader count,
not the MOABB documentation (draft 2.1, R-P11-9); the values below were read from moabb 1.7.2 as locked
(METADATA and the dataset objects, 2026-11-02).

Licences and sizes, checked at the sources by the lead on 2026-11-02 (owner: check size and licence of
Cho2017 at the source before loading it, ask above 25 GB; about 10.2 GB in all, so no question is needed):
- Zhou2016: moabb 1.7.2 downloads the BIDS conversion by MOABB in Zenodo record 16534752, CC-BY-4.0 (Zenodo
  API; 8 files, 0.126 GB). The original figshare item 2061654 is CC0-1.0 (figshare API).
- Cho2017: GigaDB doi:10.5524/100295, CC0-1.0 (DataCite rightsIdentifier cc0-1.0; 9.97 GB per DataCite, about
  0.2 GB per subject file). moabb 1.7.2 downloads the .mat files from the GigaDB mirror on Wasabi S3; MOABB's
  own metadata says CC-BY-4.0, which is not what the source states.
- Kalunga2016: CC-BY-4.0 at Zenodo record 2392979 (Zenodo API; 36 FIF files, 0.110 GB); moabb 1.7.2 downloads
  the FIF files there.

Storage (A-100): the data go to ``paths.MNE_DATA`` only. ``configure_storage`` sets the MNE variables in the
environment of this process, never in MNE's configuration file in the home folder. It also pins MOABB's
download provider to ``upstream``: moabb 1.7.2 would otherwise fetch (and, inside ``get_data``, prefetch) the
files from NEMAR mirrors, not from the sources above whose licences were checked.
"""

from __future__ import annotations

import os
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
    licence: str  # SPDX identifier of the data as downloaded (the licence at the download source)
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
        licence="CC-BY-4.0",
        licence_verified=True,
        licence_note=(
            "CC-BY-4.0 at the download source of moabb 1.7.2, the BIDS conversion by MOABB in Zenodo record "
            "16534752 (Zenodo API, checked 2026-11-02; 8 files, 0.126 GB). The original figshare item "
            "doi:10.6084/m9.figshare.2061654 is CC0-1.0 (figshare API)."
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
        licence="CC0-1.0",
        licence_verified=True,
        licence_note=(
            "CC0-1.0 at GigaDB doi:10.5524/100295 (DataCite rightsIdentifier cc0-1.0, checked "
            "2026-11-02; 9.97 GB per DataCite, about 0.2 GB per subject file). MOABB's own metadata says "
            "CC-BY-4.0, which is not what the source states."
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
        licence_note=(
            "CC-BY-4.0 at Zenodo record 2392979 (Zenodo API, checked 2026-11-02; 36 FIF files, 0.110 GB)."
        ),
        source="https://zenodo.org/record/2392979",
        download="https://zenodo.org/record/2392979/files/",
        paper_doi="10.1016/j.neucom.2016.01.007",
        citation=(
            'Emmanuel K. Kalunga, Sylvain Chevallier, Quentin Barthelemy. "Online SSVEP-based BCI using '
            'Riemannian Geometry". Neurocomputing, 2016. arXiv report: https://arxiv.org/abs/1501.03227'
        ),
    ),
}


# MOABB's download provider (moabb.utils.get_download_provider reads the environment first): only the
# dataset's own downloader, i.e. the sources in DatasetSpec.download whose licences were checked, never a
# NEMAR mirror.
DOWNLOAD_PROVIDER = "upstream"


def configure_storage(mne_data: Path = paths.MNE_DATA) -> None:
    """Point MNE and MOABB at ``mne_data`` for this process: ``MNE_DATA`` and ``MNE_DATASETS_<sign>_PATH``
    of every approved dataset in ``os.environ`` (MOABB's ``get_dataset_path`` reads them before it would
    write ``~/.mne/mne-python.json``). Creates the folder. Writes no configuration file.

    Also sets ``MOABB_DOWNLOAD_PROVIDER`` to ``DOWNLOAD_PROVIDER`` (see the module docstring): without it,
    moabb 1.7.2 loads and prefetches from NEMAR inside ``get_data``."""
    folder = Path(mne_data).absolute()
    folder.mkdir(parents=True, exist_ok=True)
    os.environ["MNE_DATA"] = str(folder)
    for spec in DATASETS.values():
        os.environ[f"MNE_DATASETS_{spec.mne_sign}_PATH"] = str(folder)
    os.environ["MOABB_DOWNLOAD_PROVIDER"] = DOWNLOAD_PROVIDER


def moabb_dataset(spec: DatasetSpec) -> BaseDataset:
    """The MOABB loader object of ``spec`` (``moabb.datasets.<spec.name>()``), unchanged."""
    import moabb.datasets

    return getattr(moabb.datasets, spec.name)()


def fetch(spec: DatasetSpec, subjects: tuple[int, ...] | None = None) -> None:
    """Download the data of ``spec`` (all subjects by default, F2 A) into the configured storage. The only
    function that is meant to download; never called by tests or CI (F11 B). Before the first call for
    Cho2017 and Zhou2016 the licence at the download source is checked (see the module docstring).

    Refuses a dataset whose licence is not verified at the source. Storage and provider as
    ``configure_storage`` (called here); MOABB never writes its path into MNE's configuration file."""
    if not spec.licence_verified:
        raise RuntimeError(f"{spec.name}: the licence at the download source is not verified")
    configure_storage()
    dataset = moabb_dataset(spec)
    chosen = list(dataset.subject_list if subjects is None else subjects)
    unknown = sorted(set(chosen) - set(dataset.subject_list))
    if unknown:
        raise ValueError(f"{spec.name}: unknown subjects {unknown}")
    dataset.download(subject_list=chosen, update_path=False, verbose="error")


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
    The FIF export (``export.write_fifs``) and the decoders read exactly this view.

    The view loads the raws of ``base`` per subject as ``base.get_data`` would before any processing step
    (MOABB's raw stage without the disk cache) and degrades every run with the key ``RecordingKey(spec.name,
    subject, session, run)``. ``code`` is ``Degraded-<base code>-<condition id>`` in MOABB's code form; the
    object can be pickled when ``base`` can."""
    from neuroarena import _views

    return _views.Degraded(spec, condition, moabb_dataset(spec) if base is None else base)
