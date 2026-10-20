"""Channel type assignment by label and standard electrode names (A-18, A-77, M04).

MNE's ``infer_types`` mislabels e.g. ECG and SaO2 in polysomnography files, so NeuroGrid keeps its own list.
Labels are matched against the standard names without regard to case, after removing a leading type word
("EEG Fp1") and a trailing reference ("Fp1-REF", "C3-A2"); a bipolar label ("Fp1-F7") is standard if both
parts are.

The type of a label is decided on the label without a leading "EEG" type word, so that TUH labels such as
"EEG EKG1-REF" or "EEG PHOTIC-REF" are no EEG channels while "EEG Fp1-REF" or "EEG Fpz-Cz" stay EEG.
EOG, ECG/EKG and EMG count wherever they appear in the label ("VEOG", "HEOG-L", "EOG horizontal"); other
types are recognised by the first word ("LOC-A2", TUH "LUC", the orbital "LO1"/"IO1", "H.R.") or the start
of the label (Neuroscan "HEO"/"VEO", "GSR1", "Event marker", "Photo", "AccX"). The AASM EOG derivations
"E1-M2"/"E2-M1" are EOG, while "E1" alone stays EEG (an EGI net electrode). Everything else is treated as
EEG; no 10-20/10-10/10-05 name matches any of these rules.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from neurogrid.io.montage_names import ONLY_1005, SYSTEM_1020

ANNOTATION_LABELS = ("EDF ANNOTATIONS", "BDF ANNOTATIONS")

# Type words that count anywhere in the label; the first match wins.
_CONTAINED: tuple[tuple[str, str], ...] = (
    ("EOG", "EOG"),
    ("ECG", "ECG"),
    ("EKG", "ECG"),
    ("EMG", "EMG"),
)

# Short names that are a type only as the first word of the label (dots removed, "H.R." is "HR"): the
# canthus EOG of sleep and TUH recordings ("LOC-A2", "ROC-A1", "EEG LUC-REF", "EEG RLC-REF"), the orbital
# EOG electrodes of Neuroscan/BESA caps (lateral, infra- and supraorbital), heart rate, and the derived TUH
# channels.
_WORDS: dict[str, str] = {
    "LOC": "EOG",
    "ROC": "EOG",
    "LUC": "EOG",
    "RUC": "EOG",
    "LLC": "EOG",
    "RLC": "EOG",
    "LO1": "EOG",
    "LO2": "EOG",
    "IO1": "EOG",
    "IO2": "EOG",
    "SO1": "EOG",
    "SO2": "EOG",
    "HR": "MISC",
    "IBI": "MISC",
    "BURSTS": "MISC",
    "SUPPR": "MISC",
}

# Ordered prefixes; the first match wins.
_PREFIXES: tuple[tuple[str, str], ...] = (
    ("HEO", "EOG"),  # Neuroscan "HEO", "VEO", "HEOL", "VEOU"
    ("VEO", "EOG"),
    ("RESP", "RESP"),
    ("THOR", "RESP"),  # respiratory effort belts
    ("ABDO", "RESP"),
    ("EFFORT", "RESP"),
    ("AIRFLOW", "RESP"),
    ("FLOW", "RESP"),
    ("THERM", "RESP"),  # thermistor airflow
    ("NASAL", "RESP"),  # nasal pressure
    ("SAO2", "MISC"),  # oxygen saturation
    ("SPO2", "MISC"),
    ("OSAT", "MISC"),
    ("SAT", "MISC"),
    ("OX", "MISC"),  # oximeter status (SHHS "OX stat")
    ("PLET", "MISC"),  # plethysmogram ("Pleth", BioSemi "Plet")
    ("PPG", "MISC"),
    ("PULSE", "MISC"),
    ("GSR", "MISC"),  # skin conductance
    ("EDA", "MISC"),
    ("ERG", "MISC"),  # BioSemi "Erg1", electroretinogram
    ("TEMP", "MISC"),
    ("SNORE", "MISC"),
    ("SOUND", "MISC"),
    ("LIGHT", "MISC"),
    ("PHOTIC", "MISC"),  # photic stimulator
    ("PHOTO", "MISC"),  # photodiode or photo sensor of ERP setups
    ("ACC", "MISC"),  # accelerometer ("ACC_X", "AccX") of mobile and consumer devices
    ("GYRO", "MISC"),
    ("POS", "MISC"),
    ("EVENT", "MISC"),  # Sleep-EDF "Event marker" (a 1 Hz marker signal, misc in MNE's Sleep-EDF reader)
    ("MARKER", "MISC"),
    ("ANNOT", "MISC"),  # an annotation-like signal that is no EDF+/BDF+ annotation channel
    ("LEG", "EMG"),
    ("CHIN", "EMG"),
    ("STATUS", "TRIG"),
    ("TRIG", "TRIG"),
    ("STI", "TRIG"),
)

_BY_UPPER_1020 = {name.upper(): name for name in SYSTEM_1020}
_BY_UPPER_1005 = {name.upper(): name for name in ONLY_1005}
_TYPE_WORD = re.compile(r"^(?:EEG)[\s_:-]+", re.IGNORECASE)
_REFERENCE_SUFFIX = re.compile(r"[-_ ]+(?:REF|AVG|AR|LE|RE|CZ)$", re.IGNORECASE)
_WORD_SPLIT = re.compile(r"[^A-Z0-9]+")
_AASM_EOG = re.compile(r"^E[12]\s*-\s*[AM][12]$")  # "E1-M2", "E2-M1": EOG of the AASM sleep montage


def classify(label: str) -> str:
    """The channel type of a label: EEG, EOG, ECG, EMG, RESP, TRIG, MISC or ANNOT (A-18, A-77)."""
    text = label.strip().upper()
    if text in ANNOTATION_LABELS:
        return "ANNOT"
    rest = _TYPE_WORD.sub("", text)  # "EEG EKG1-REF" is an ECG channel, "EEG Fp1-REF" an EEG channel
    for word, kind in _CONTAINED:
        if word in rest:
            return kind
    if _AASM_EOG.match(rest):
        return "EOG"
    first = _WORD_SPLIT.split(rest.replace(".", ""), maxsplit=1)[0]
    if first in _WORDS:
        return _WORDS[first]
    for prefix, kind in _PREFIXES:
        if rest.startswith(prefix):
            return kind
    return "EEG"


def _lookup(name: str) -> tuple[str, str] | None:
    key = name.strip().upper()
    if key in _BY_UPPER_1020:
        return _BY_UPPER_1020[key], "1020"
    if key in _BY_UPPER_1005:
        return _BY_UPPER_1005[key], "1005"
    return None


def standard_name(label: str, channel_map: Mapping[str, str] | None = None) -> tuple[str, str] | None:
    """The standard name of a channel label and its system ("1020" for 10-20/10-10, "1005" for 10-05 only).

    ``channel_map`` (from neurogrid.toml) maps labels that differ from the standard to a standard name.
    None if the label is no standard name.
    """
    if channel_map and label in channel_map:
        return _lookup(channel_map[label])
    text = _TYPE_WORD.sub("", label.strip())
    text = _REFERENCE_SUFFIX.sub("", text)
    found = _lookup(text)
    if found is not None:
        return found
    parts = re.split(r"\s*-\s*", text)
    if len(parts) == 2:
        first, second = _lookup(parts[0]), _lookup(parts[1])
        if first is not None and second is not None:
            # a referential or bipolar derivation; the system is the wider one of the two
            system = "1005" if "1005" in (first[1], second[1]) else "1020"
            return f"{first[0]}-{second[0]}", system
    return None
