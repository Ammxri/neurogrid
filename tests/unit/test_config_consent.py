"""[consent] in neurogrid.toml (NG-F18, M14; A-30, A-82 note "[consent] konfiguriert", A-91): the uses per
split and for the whole dataset, their canonical form and when the section counts as configured."""

from __future__ import annotations

import pytest

from neurogrid import config
from neurogrid.kernel.errors import ConfigError
from neurogrid.model.consent import ConsentUse

TRAINING, VALIDATION = ConsentUse.TRAINING, ConsentUse.VALIDATION


def test_without_a_section_the_defaults_apply_and_nothing_is_configured() -> None:
    for text in ("", "[consent]\n"):
        section = config.parse(text).consent
        assert not section.configured
        assert section.effective_split_use() == {
            "train": (TRAINING,),
            "val": (VALIDATION,),
            "test": (VALIDATION,),
        }
        assert section.dataset_uses == []


def test_configured_only_with_content() -> None:
    assert config.parse('[consent]\nsplit_use = { test = "publication" }\n').consent.configured
    assert config.parse('[consent]\ndataset_uses = ["sharing"]\n').consent.configured
    assert not config.parse("[consent]\ndataset_uses = []\nsplit_use = {}\n").consent.configured


def test_string_and_list_values_and_the_per_split_default() -> None:
    text = '[consent]\nsplit_use = { train = ["validation", "training"], test = "publication" }\n'
    section = config.parse(text).consent
    assert section.effective_split_use() == {
        "train": (TRAINING, VALIDATION),  # ConsentUse order, whatever the order in the file
        "val": (VALIDATION,),  # not named: its own default
        "test": (ConsentUse.PUBLICATION,),
    }


def test_effective_settings_are_canonical_lists() -> None:
    one = config.parse(
        '[consent]\nsplit_use = { train = "training" }\ndataset_uses = ["sharing", "commercial"]\n'
    )
    other = config.parse(
        '[consent]\ndataset_uses = ["commercial", "sharing"]\nsplit_use = { train = ["training"] }\n'
    )
    assert one.consent.model_dump(mode="json") == {
        "split_use": {"train": ["training"]},
        "dataset_uses": ["sharing", "commercial"],
    }
    assert one.canonical_sha256() == other.canonical_sha256()


@pytest.mark.parametrize(
    ("text", "field", "problem"),
    [
        ('split_use = { holdout = "training" }', "consent.split_use.holdout.[key]", "literal_error"),
        ('split_use = { train = "research" }', "consent.split_use.train.0", "enum"),
        ("split_use = { train = [] }", "consent.split_use.train", "too_short"),
        ('split_use = { train = ["training", "training"] }', "consent.split_use.train", "value_error"),
        ("split_use = { train = 5 }", "consent.split_use.train", "list_type"),
        ('dataset_uses = ["sharing", "sharing"]', "consent.dataset_uses", "value_error"),
        ('dataset_uses = ["research"]', "consent.dataset_uses.0", "enum"),
        ('dataset_uses = "sharing"', "consent.dataset_uses", "list_type"),
        ('uses = ["sharing"]', "consent.uses", "extra_forbidden"),
    ],
)
def test_invalid_sections_are_configuration_errors(text: str, field: str, problem: str) -> None:
    with pytest.raises(ConfigError) as info:
        config.parse("[consent]\n" + text + "\n")
    assert info.value.message_key == "config.invalid"
    assert info.value.params == {"field": field, "problem": problem}
