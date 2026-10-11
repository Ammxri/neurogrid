"""Channel type assignment by label (A-18).

MNE's ``infer_types`` mislabels e.g. ECG and SaO2 in polysomnography files, so NeuroGrid keeps its own list.
"""

from __future__ import annotations

ANNOTATION_LABELS = ("EDF ANNOTATIONS", "BDF ANNOTATIONS")

# Ordered prefixes; the first match wins. Everything else is treated as EEG.
_PREFIXES: tuple[tuple[str, str], ...] = (
    ("EEG", "EEG"),
    ("EOG", "EOG"),
    ("EMG", "EMG"),
    ("ECG", "ECG"),
    ("EKG", "ECG"),
    ("RESP", "RESP"),
    ("SAO2", "MISC"),
    ("SPO2", "MISC"),
    ("PLETH", "MISC"),
    ("PULSE", "MISC"),
    ("TEMP", "MISC"),
    ("SNORE", "MISC"),
    ("LIGHT", "MISC"),
    ("POS", "MISC"),
    ("LEG", "EMG"),
    ("CHIN", "EMG"),
    ("STATUS", "TRIG"),
    ("TRIG", "TRIG"),
    ("STI", "TRIG"),
)


def classify(label: str) -> str:
    text = label.strip().upper()
    if text in ANNOTATION_LABELS:
        return "ANNOT"
    for prefix, kind in _PREFIXES:
        if text.startswith(prefix):
            return kind
    return "EEG"
