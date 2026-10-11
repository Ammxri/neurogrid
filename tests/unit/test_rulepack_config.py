from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from neurogrid import config as config_module
from neurogrid.kernel.errors import ConfigError, RulepackError
from neurogrid.kernel.findings import SourceStatus
from neurogrid.kernel.rules import load_rulepack

VALID = """rulepack: mine
version: "0.1"
source: Own rules
source_status: final
rules:
  - id: MINE-ACQ-001
    clause: "1.1"
    title_zh: 测试
    title_en: Test
    phase: acquisition
    check: signal.sampling_rate_min
    params: {min_hz: 250}
    severity: warning
    verification: automatic
"""


def test_load_valid_pack() -> None:
    loaded = load_rulepack(VALID, origin="path")
    assert loaded.pack.rulepack == "mine" and loaded.pack.source_status is SourceStatus.FINAL
    assert len(loaded.sha256) == 64 and loaded.pack.norm is False


@pytest.mark.parametrize(
    ("text", "key"),
    [
        ("- just\n- a list\n", "rulepack.not_mapping"),
        (VALID.replace('clause: "1.1"', "clause: 1.1"), "rulepack.invalid"),
        (VALID.replace('version: "0.1"', "version: 0.1"), "rulepack.invalid"),
        (VALID.replace("phase: acquisition", "phase: someday"), "rulepack.invalid"),
        (VALID.replace("source_status: final", "source_status: maybe"), "rulepack.invalid"),
        (VALID.replace("id: MINE-ACQ-001", "id: lower-case"), "rulepack.invalid"),
        (VALID + "    extra: field\n", "rulepack.invalid"),
        (VALID + VALID.split("rules:\n")[1], "rulepack.duplicate_rule"),
    ],
)
def test_invalid_packs(text: str, key: str) -> None:
    with pytest.raises(RulepackError) as info:
        load_rulepack(text, origin="path")
    assert info.value.message_key == key


def test_config_parse_full() -> None:
    text = """
[dataset]
id = "ds-1"
name = "Demo"
[check]
rulepacks = ["core"]
as_of = 2026-11-20
[rules."CORE-M03-01".params]
min_hz = 256
[[exceptions]]
rule = "CORE-M03-01"
object = "rec-*"
reason = "Device limited to 256 Hz (SOP-3)."
valid_until = 2027-06-30
[metadata]
mixed_sampling_rates_reason = "two device generations"
[metadata.defaults]
electrode_type = "wet"
line_frequency_hz = 50
"""
    cfg = config_module.parse(text)
    assert cfg.check.as_of == date(2026, 11, 20)
    assert cfg.overrides() == {"CORE-M03-01": {"min_hz": 256}}
    assert cfg.exceptions[0].valid_until == date(2027, 6, 30)
    assert len(cfg.canonical_sha256()) == 64


def test_config_hash_ignores_formatting() -> None:
    a = config_module.parse("[check]\nseed = 1\n")
    b = config_module.parse("# comment\r\n[check]\r\nseed    =    1\r\n")
    assert a.canonical_sha256() == b.canonical_sha256()


@pytest.mark.parametrize(
    ("text", "key"),
    [
        ("[check]\nunknown = 1\n", "config.invalid"),
        ("[[exceptions]]\nrule = 'X-1'\nreason = ''\n", "config.invalid"),
        ("[check\n", "config.syntax"),
        ("[metadata.defaults]\nelectrode_type = 'gel'\n", "config.invalid"),
    ],
)
def test_config_errors(text: str, key: str) -> None:
    with pytest.raises(ConfigError) as info:
        config_module.parse(text)
    assert info.value.message_key == key


def test_config_load_locations(tmp_path: Path) -> None:
    cfg, path, root = config_module.load(None, tmp_path)
    assert path is None and cfg.check.seed == 20261011 and root == tmp_path.resolve()
    (tmp_path / ".neurogrid").mkdir()
    (tmp_path / ".neurogrid" / "neurogrid.toml").write_text("[check]\nseed = 7\n", encoding="utf-8")
    cfg, path, root = config_module.load(None, tmp_path)
    assert cfg.check.seed == 7 and path is not None
    assert root == tmp_path.resolve()  # inside the dataset: the project root is the dataset root (A-52)
    outside = tmp_path.parent / f"{tmp_path.name}-shared"
    outside.mkdir()
    (outside / "lab.toml").write_text("[check]\nseed = 8\n", encoding="utf-8")
    _cfg, _path, root = config_module.load(outside / "lab.toml", tmp_path)
    assert root == outside.resolve()  # outside: the folder of the toml
    with pytest.raises(ConfigError):
        config_module.load(tmp_path / "missing.toml", tmp_path)
    with pytest.raises(ConfigError):
        config_module.parse("x" * (config_module.MAX_CONFIG_BYTES + 1))
    big = tmp_path / "big.toml"
    big.write_bytes(b"#" * (config_module.MAX_CONFIG_BYTES + 1))
    with pytest.raises(ConfigError) as info:
        config_module.load(big, tmp_path)
    assert info.value.message_key == "config.too_large"


def test_config_encodings(tmp_path: Path) -> None:
    """PowerShell 5.1 writes UTF-8 with BOM; other encodings end with a clear message (A-53)."""
    assert config_module.parse_bytes(b"\xef\xbb\xbf[check]\nseed = 3\n").check.seed == 3
    with pytest.raises(ConfigError) as info:
        config_module.parse_bytes("# 注释\n[check]\nseed = 3\n".encode("gbk"))
    assert info.value.message_key == "config.encoding"


@pytest.mark.parametrize(
    ("text", "field"),
    [
        ('[check]\nrulepacks = ["core", "../outside.yaml"]\n', "check.rulepacks.1"),
        ('[check]\nrulepacks = ["C:/Users/x/pack.yaml"]\n', "check.rulepacks.0"),
        ('[check]\nrulepacks = ["/etc/pack.yaml"]\n', "check.rulepacks.0"),
        ('[ai]\nsplits = "/home/x/splits.tsv"\n', "ai.splits"),
        ('[vault]\npath = "\\\\\\\\server\\\\share"\n', "vault.path"),
    ],
)
def test_config_paths_must_be_relative(text: str, field: str) -> None:
    with pytest.raises(ConfigError) as info:
        config_module.parse(text)
    assert info.value.message_key == "config.unsafe_path" and info.value.params["field"] == field


@pytest.mark.parametrize(
    "text",
    [
        '[check]\nstrict = "yes"\n',
        '[check]\nseed = "7"\n',
        '[check]\nas_of = "2026-10-11"\n',
        '[metadata.defaults]\nline_frequency_hz = "50"\n',
        '[[exceptions]]\nrule = "X-1"\nreason = "r"\nvalid_until = "2027-01-01"\n',
        "[check]\nrulepacks = []\n",
    ],
)
def test_config_is_strict(text: str) -> None:
    """No silent type conversion (KONZEPT 1.2, A-53); an empty rule pack list is no configuration."""
    with pytest.raises(ConfigError) as info:
        config_module.parse(text)
    assert info.value.message_key == "config.invalid"


def test_config_accepts_typed_values() -> None:
    cfg = config_module.parse("[sampling]\nsegment_s = 30\n[metadata.defaults]\nline_frequency_hz = 50\n")
    assert cfg.sampling.segment_s == 30.0 and cfg.metadata.defaults.line_frequency_hz == 50.0


def test_rulepack_hash_is_over_file_bytes() -> None:
    import hashlib

    crlf = VALID.replace("\n", "\r\n").encode("utf-8")
    loaded = load_rulepack(crlf, origin="path")
    assert loaded.sha256 == hashlib.sha256(crlf).hexdigest()
    assert load_rulepack(b"\xef\xbb\xbf" + VALID.encode("utf-8"), origin="path").pack.rulepack == "mine"
    with pytest.raises(RulepackError) as info:
        load_rulepack(VALID.replace("测试", "x").encode("utf-16"), origin="path")
    assert info.value.message_key == "rulepack.encoding"
