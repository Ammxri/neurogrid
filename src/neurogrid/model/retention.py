"""The retention periods of NeuroVault: ``<vault>/retention.yaml`` (NV-F05; A-30, A-94). For each object of
the vault, when it was created, the date until which it is kept at least and an optional review date. The
schema is generated from RetentionRegister (tools/gen_schemas.py: schemas/retention.schema.json).

Format (format_version 1)::

    format_version: 1
    objects:
      - object: pia                    # one of RETENTION_OBJECTS, each once
        created: 2026-11-02            # a YAML date or the text "2026-11-02"
        min_until: 2029-11-02          # at least plus_three_years(created)
        review_at: 2029-08-01          # optional; created <= review_at <= min_until

The objects are the vault's own files: ``pia`` (the impact assessment pia/pia.zh.md, pia/pia.en.md),
``access_log`` (access.jsonl), ``roles``, ``risks`` and ``consents`` (the YAML files of the same names).
REQUIRED names pia and access_log: NeuroGrid reads the PIPL provision on the impact assessment as asking that
its report and the record of the processing be kept for at least three years (A-30, A-94; an interpretation,
marked as such in the documentation). There is no retention period for EEG data and no deletion logic: the
reminder of CORE-NV05-03 is neutral (A-30).

The file is a control file (C2): invalid content ends a run with exit 2 and names the place (entry index and
field name), never the text of a value (model._registers). A minimum retention of less than three years is
errors.retention.too_short {object} (exit 2, the DoD of P9 in KONZEPT 6); a review date outside created ..
min_until is errors.retention.invalid {field, problem review_order}. NeuroGrid never rewrites the file.

Only kernel and model imports (ARC-01).
"""

from __future__ import annotations

import datetime as dt
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field

from neurogrid.kernel import canonical
from neurogrid.kernel.errors import ConfigError
from neurogrid.model._registers import (
    FILE_KEY,
    FormatVersion,
    RegisterDate,
    RegisterSpec,
    invalid,
    parse_register,
)

MAX_FILE_BYTES = 100_000
MIN_YEARS = 3  # the minimum retention (A-30)
RetentionObject = Literal["pia", "access_log", "roles", "risks", "consents"]
RETENTION_OBJECTS: tuple[str, ...] = get_args(RetentionObject)
REQUIRED: tuple[str, ...] = ("pia", "access_log")  # CORE-NV05-01: an entry is expected for each (A-94)
LIST_KEY = "objects"
ENTRY_KEYS = ("object", "created", "min_until", "review_at")
# Problems of the checks across fields and entries (a fixed key shown in errors.retention.invalid).
DUPLICATE_OBJECT = "duplicate_object"
REVIEW_ORDER = "review_order"
SPEC = RegisterSpec(
    name="retention",
    list_key=LIST_KEY,
    max_bytes=MAX_FILE_BYTES,
    keys=frozenset((FILE_KEY, LIST_KEY, *ENTRY_KEYS)),
    problems=frozenset(),
)
_OBJECT_ORDER = {name: index for index, name in enumerate(RETENTION_OBJECTS)}


def plus_three_years(created: dt.date) -> dt.date | None:
    """The earliest permitted min_until: the same month and day MIN_YEARS later; 29 February gives 1 March
    when that year has no 29 February (the stricter reading of "three years", A-94). None when that day lies
    beyond the last date Python knows (9999-12-31): no min_until is late enough then."""
    year = created.year + MIN_YEARS
    if year > dt.MAXYEAR:
        return None
    try:
        return created.replace(year=year)
    except ValueError:  # 29 February in a year without it
        return dt.date(year, 3, 1)


class RetentionItem(BaseModel):
    """The retention of one object of the vault (A-94)."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    object: RetentionObject
    created: RegisterDate
    min_until: RegisterDate
    review_at: RegisterDate | None = None

    @property
    def too_short(self) -> bool:
        """min_until lies before plus_three_years(created)."""
        earliest = plus_three_years(self.created)
        return earliest is None or self.min_until < earliest

    @property
    def review_in_order(self) -> bool:
        """No review date, or one in created .. min_until (both included)."""
        return self.review_at is None or self.created <= self.review_at <= self.min_until


class RetentionRegister(BaseModel):
    """The whole retention.yaml. ``format_version`` and ``objects`` are required in a file (parse_retention,
    and the schema); the defaults only serve NeuroGrid's own construction. Each object is listed at most once,
    min_until lies at least three years after created and a review date between both (parse_retention; the
    schema cannot compare fields)."""

    model_config = ConfigDict(
        strict=True, extra="forbid", json_schema_extra={"required": [FILE_KEY, LIST_KEY]}
    )

    format_version: FormatVersion = 1
    objects: list[RetentionItem] = Field(default_factory=list, max_length=len(RETENTION_OBJECTS))

    @property
    def entries(self) -> list[RetentionItem]:
        return self.objects

    def canonical_sha256(self) -> str:
        """Hash over the parsed content (results.json config.retention_sha256): the same for every spelling of
        the same register (order of entries, quoting, comments, line ends)."""
        items = sorted(self.objects, key=lambda entry: _OBJECT_ORDER[entry.object])
        return canonical.sha256_of(
            {
                "format_version": self.format_version,
                "objects": [item.model_dump(mode="json") for item in items],
            }
        )

    def by_object(self) -> dict[str, RetentionItem]:
        """object -> its entry."""
        return {entry.object: entry for entry in self.objects}


def parse_retention(data: bytes) -> RetentionRegister:
    """Parse retention.yaml bytes (model._registers.parse_register), then each entry in file order: an
    object listed before (errors.retention.invalid, objects.<i>.object, duplicate_object), a minimum
    retention of less than three years (errors.retention.too_short {object}) and a review date outside
    created .. min_until (errors.retention.invalid, objects.<i>.review_at, review_order). The first problem
    found is raised (exit 2)."""
    parsed = parse_register(data, SPEC, RetentionRegister)
    seen: set[str] = set()
    for index, item in enumerate(parsed.objects):
        if item.object in seen:
            raise invalid(SPEC, f"{LIST_KEY}.{index}.object", DUPLICATE_OBJECT)
        seen.add(item.object)
        if item.too_short:
            raise ConfigError("retention.too_short", object=item.object)
        if not item.review_in_order:
            raise invalid(SPEC, f"{LIST_KEY}.{index}.review_at", REVIEW_ORDER)
    return parsed
