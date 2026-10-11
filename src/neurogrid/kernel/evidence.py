"""Evidence for rules that cannot be measured (NG-F12, A-15).

``provided`` means the user has filed a document; NeuroGrid does not judge its content.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvidenceState(StrEnum):
    OPEN = "open"
    PROVIDED = "provided"
    PARTIAL = "partial"
    NOT_APPLICABLE = "not_applicable"


class DocumentCheck(StrEnum):
    OK = "ok"
    NO_DOCUMENT = "no_document"
    DOCUMENT_MISSING = "document_missing"
    HASH_MISMATCH = "hash_mismatch"


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: EvidenceState
    document: str | None = Field(default=None, max_length=1024)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    reviewer: str | None = Field(default=None, max_length=80)
    date: dt.date | None = None
    comment: str | None = Field(default=None, max_length=500)
    justification: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _justified(self) -> EvidenceItem:
        if self.status is EvidenceState.NOT_APPLICABLE and not (self.justification or "").strip():
            raise ValueError("not_applicable needs a justification")
        return self


DocumentChecker = Callable[[EvidenceItem], DocumentCheck]


def no_document_checker(item: EvidenceItem) -> DocumentCheck:
    return DocumentCheck.NO_DOCUMENT if item.document is None else DocumentCheck.DOCUMENT_MISSING
