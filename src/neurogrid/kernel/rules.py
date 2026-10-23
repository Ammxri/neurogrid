"""Rule packs, the check registry contract and measurements (PRD §11, A-13).

Rule pack keys (PRD German → English, D-03): rulepack, version, quelle→source, regeln→rules;
per rule: id, klausel→clause, titel_zh→title_zh, titel_en→title_en, phase, pruefung→check,
parameter→params, schweregrad→severity, nachweis→verification.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from neurogrid.kernel.errors import RulepackError
from neurogrid.kernel.findings import ParamValue as ParamValue  # re-exported for checks and config
from neurogrid.kernel.findings import Phase, Severity, SourceStatus, TimeRange, Verification
from neurogrid.kernel.safety import load_yaml

RULE_ID_PATTERN = r"^[A-Z0-9]+(-[A-Z0-9]+)+$"
MAX_INTEGER_PARAM = 2**53  # exactly representable as a JSON number everywhere
EVIDENCE_CHECK = "evidence.document"


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: str = Field(pattern=RULE_ID_PATTERN, max_length=64)
    clause: str = Field(min_length=1, max_length=64)
    title_zh: str = Field(min_length=1, max_length=200)
    title_en: str = Field(min_length=1, max_length=200)
    phase: Phase
    check: str = Field(pattern=r"^[a-z0-9_]+(\.[a-z0-9_]+)+$", max_length=80)
    params: dict[str, ParamValue] = Field(default_factory=dict)
    severity: Severity
    # Optional severity in strict mode (--strict or [check] strict), applied by the engine, never by a check
    # (ARC-02). RP-01 extension like ``norm`` (A-62, A-82): CORE-M13-01 is a warning, with --strict an error.
    strict_severity: Severity | None = None
    verification: Verification

    def effective_severity(self, strict: bool) -> Severity:
        return self.strict_severity if strict and self.strict_severity is not None else self.severity


class Rulepack(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    rulepack: str = Field(pattern=r"^[a-z0-9_]+$", max_length=40)
    version: str = Field(min_length=1, max_length=40)
    source: str = Field(min_length=1, max_length=200)
    source_status: SourceStatus
    norm: bool = False  # True for packs that map a norm; only those get a coverage measure (A-16)
    rules: list[Rule] = Field(min_length=1)


@dataclass(frozen=True)
class LoadedRulepack:
    pack: Rulepack
    sha256: str
    origin: str  # "builtin" or "path"


def load_rulepack(source: bytes | str, origin: str) -> LoadedRulepack:
    """Parse a rule pack. The SHA-256 is taken over the raw file bytes so that it matches ``sha256sum``."""
    raw = source.encode("utf-8") if isinstance(source, str) else source
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise RulepackError("rulepack.encoding") from None
    data = load_yaml(text)
    if not isinstance(data, dict):
        raise RulepackError("rulepack.not_mapping")
    try:
        pack = Rulepack.model_validate(_enums_to_values(data))
    except ValidationError as exc:
        first = exc.errors()[0]
        location = ".".join(str(part) for part in first["loc"])
        raise RulepackError("rulepack.invalid", field=location, problem=first["type"]) from None
    seen: set[str] = set()
    for rule in pack.rules:
        if rule.id in seen:
            raise RulepackError("rulepack.duplicate_rule", rule=rule.id)
        seen.add(rule.id)
    digest = hashlib.sha256(raw).hexdigest()
    return LoadedRulepack(pack=pack, sha256=digest, origin=origin)


def _enums_to_values(data: dict[str, Any]) -> dict[str, Any]:
    """Strict models accept enum members only; convert known enum fields from strings."""
    converted = dict(data)
    if isinstance(converted.get("source_status"), str):
        converted["source_status"] = _to_enum(SourceStatus, converted["source_status"], "source_status")
    rules = converted.get("rules")
    if isinstance(rules, list):
        new_rules = []
        for rule in rules:
            if isinstance(rule, dict):
                rule = dict(rule)
                for key, enum in (
                    ("phase", Phase),
                    ("severity", Severity),
                    ("strict_severity", Severity),
                    ("verification", Verification),
                ):
                    if isinstance(rule.get(key), str):
                        rule[key] = _to_enum(enum, rule[key], key)
            new_rules.append(rule)
        converted["rules"] = new_rules
    return converted


def _to_enum(enum: type[Any], value: str, field_name: str) -> Any:
    try:
        return enum(value)
    except ValueError:
        raise RulepackError("rulepack.invalid", field=field_name, problem="enum") from None


# --- Check registry contract -------------------------------------------------------------------


@dataclass(frozen=True)
class ParamSpec:
    kind: Literal["number", "integer", "boolean", "string"]
    default: ParamValue


@dataclass(frozen=True)
class Measurement:
    """What a check measured for one object. Values must be JSON-compatible.

    ``object`` is the displayed ID (pseudonymous in raw folders unless --show-paths). ``identity`` lists the
    object's stable names – relative POSIX path first, then the pseudonymous ID. Exception patterns are
    matched against all of them and the finding key uses the first one, so neither depends on the display
    option (A-09, A-14). ``identity`` never appears in any output.
    """

    check_id: str
    object: str
    value: Any = None
    subkey: str | None = None
    file: str | None = None
    channel: str | None = None
    state: Literal["measured", "not_checkable", "not_applicable"] = "measured"
    reason: str | None = None
    time_ranges: tuple[TimeRange, ...] = ()
    time_ranges_total: int = 0
    time_ranges_duration_s: float | None = None
    details: Mapping[str, Any] = field(default_factory=dict)
    identity: tuple[str, ...] = ()


@dataclass(frozen=True)
class Evaluation:
    """The verdict of an evaluator. ``not_checkable`` (a reason key) says the measurement cannot be judged
    under the rule's parameters, e.g. when the verdict would reveal a withheld small cell (A-51); the engine
    then gives not_checkable and ignores ``passed``."""

    passed: bool
    threshold: Any = None
    not_checkable: str | None = None


Evaluator = Callable[[Measurement, Mapping[str, ParamValue]], Evaluation]


@dataclass(frozen=True)
class CheckSpec:
    id: str
    evaluate: Evaluator
    params: Mapping[str, ParamSpec] = field(default_factory=dict)


@dataclass(frozen=True)
class Bound:
    """A threshold comparison a check declares (A-13): the measured value must be ``op`` the parameter
    ``param``. The registry documentation is generated from it (tools/gen_docs.py)."""

    param: str
    op: Literal["<=", ">="]

    def __call__(self, measurement: Measurement, params: Mapping[str, ParamValue]) -> Evaluation:
        limit = params[self.param]
        passed = measurement.value <= limit if self.op == "<=" else measurement.value >= limit
        return Evaluation(passed=passed, threshold=limit)


def at_most(param: str) -> Bound:
    return Bound(param, "<=")


def at_least(param: str) -> Bound:
    return Bound(param, ">=")


def is_true(measurement: Measurement, params: Mapping[str, ParamValue]) -> Evaluation:
    return Evaluation(passed=measurement.value is True)


def evidence_spec() -> CheckSpec:
    """Manual rules are evaluated from evidence.yaml by the engine, not by a measurement."""
    return CheckSpec(id=EVIDENCE_CHECK, evaluate=is_true)


def check_param_value(spec: ParamSpec, value: object) -> bool:
    if spec.kind == "boolean":
        return isinstance(value, bool)
    if spec.kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool) and abs(value) <= MAX_INTEGER_PARAM
    if spec.kind == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return False
        try:
            return math.isfinite(value)
        except OverflowError:  # an integer beyond the float range is no usable threshold
            return False
    return isinstance(value, str)


def validate_against_registry(packs: Sequence[LoadedRulepack], registry: Mapping[str, CheckSpec]) -> None:
    """Every rule must name a registered check and only use its declared parameters."""
    seen: dict[str, str] = {}
    for loaded in packs:
        for rule in loaded.pack.rules:
            if rule.id in seen:
                raise RulepackError("rulepack.duplicate_rule", rule=rule.id)
            seen[rule.id] = loaded.pack.rulepack
            spec = registry.get(rule.check)
            if spec is None:
                raise RulepackError("rulepack.unknown_check", rule=rule.id, check=rule.check)
            if rule.verification is Verification.MANUAL and rule.check != EVIDENCE_CHECK:
                raise RulepackError("rulepack.manual_needs_evidence", rule=rule.id)
            for name, value in rule.params.items():
                param = spec.params.get(name)
                if param is None:
                    raise RulepackError("rulepack.unknown_param", rule=rule.id, param=name)
                if not check_param_value(param, value):
                    raise RulepackError("rulepack.param_type", rule=rule.id, param=name)
