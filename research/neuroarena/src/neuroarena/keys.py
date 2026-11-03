"""Shared keys of NeuroArena (frozen by the P11 scaffold; used by every area).

A recording is one MOABB run of one session of one subject of one dataset; a session groups the runs whose
quality level is the worst of theirs and on which the decoders are evaluated (F5e, A-104). A condition is one
step of one degradation ladder: the clean data (level 0) or one of five levels of one kind (F4a A: one ladder
per kind, 16 conditions in all).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# The three degradation kinds of the PRD ("add line noise, remove channels, mix in artefacts"), F4.
KINDS = ("line_noise", "channels", "artifacts")
CLEAN_KIND = "clean"
LEVELS = (1, 2, 3, 4, 5)
# MOABB 1.x names sessions and runs with digits ("0", "1", ...); a key keeps the loader's name as it is.
NAME = re.compile(r"[A-Za-z0-9]+")


@dataclass(frozen=True, order=True)
class Condition:
    """One condition: ``Condition("clean", 0)`` or ``Condition(kind, level)``, kind in KINDS, level 1-5."""

    kind: str
    level: int

    def __post_init__(self) -> None:
        if self.kind == CLEAN_KIND:
            if self.level != 0:
                raise ValueError("the clean condition has level 0")
        elif self.kind not in KINDS or self.level not in LEVELS:
            raise ValueError(f"unknown condition {self.kind!r} {self.level!r}")

    @property
    def id(self) -> str:
        """``clean`` or ``<kind>-<level>`` (file and folder names, CSV column ``condition``)."""
        return CLEAN_KIND if self.kind == CLEAN_KIND else f"{self.kind}-{self.level}"

    @classmethod
    def from_id(cls, text: str) -> Condition:
        if text == CLEAN_KIND:
            return cls(CLEAN_KIND, 0)
        kind, _, level = text.rpartition("-")
        if not level.isdigit():
            raise ValueError(f"unknown condition {text!r}")
        return cls(kind, int(level))


CLEAN = Condition(CLEAN_KIND, 0)
# The 16 conditions in their fixed order: clean, then each ladder from level 1 to 5 (F4a A).
CONDITIONS = (CLEAN, *(Condition(kind, level) for kind in KINDS for level in LEVELS))


@dataclass(frozen=True, order=True)
class SessionKey:
    """One session of one subject of one dataset (DatasetSpec.name, MOABB subject number, session name)."""

    dataset: str
    subject: int
    session: str

    def __post_init__(self) -> None:
        if not NAME.fullmatch(self.session) or self.subject < 1:
            raise ValueError(f"invalid session key {self!r}")


@dataclass(frozen=True, order=True)
class RecordingKey:
    """One run of one session (the unit of the FIF export and of NeuroGrid's quality level, A-102)."""

    dataset: str
    subject: int
    session: str
    run: str

    def __post_init__(self) -> None:
        if not (NAME.fullmatch(self.session) and NAME.fullmatch(self.run)) or self.subject < 1:
            raise ValueError(f"invalid recording key {self!r}")

    @property
    def session_key(self) -> SessionKey:
        return SessionKey(self.dataset, self.subject, self.session)
