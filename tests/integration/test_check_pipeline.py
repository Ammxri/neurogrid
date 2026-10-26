"""End-to-end check: determinism, schema validity, single files, custom rule packs, config, privacy."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path, PurePosixPath

import jsonschema
import pytest

from conftest import DOCUMENTED_TOML, documented_config  # type: ignore[import-not-found]
from neurogrid import pipeline
from neurogrid.kernel import canonical
from neurogrid.kernel.errors import ConfigError, InputError, RulepackError, UnsafePathError
from neurogrid.kernel.findings import Status

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"
SCHEMAS = Path(__file__).parent.parent.parent / "src" / "neurogrid" / "schemas"
OPTIONS = pipeline.CheckOptions(as_of=date(2026, 10, 11))


def test_two_runs_are_byte_identical() -> None:
    first = canonical.dumps(pipeline.run_check(FIX / "edf_mixed", OPTIONS))
    second = canonical.dumps(pipeline.run_check(FIX / "edf_mixed", OPTIONS))
    assert first == second


def test_results_match_schema_and_contain_no_forbidden_content() -> None:
    results = pipeline.run_check(FIX / "edf_identifying", OPTIONS)
    data = json.loads(canonical.dumps(results))
    jsonschema.validate(data, json.loads((SCHEMAS / "results.schema.json").read_text(encoding="utf-8")))
    text = json.dumps(data, ensure_ascii=False)
    assert "Zhang" not in text and "24.08.21" not in text and "rec_named" not in text
    assert str(Path.home()) not in text and str(FIX) not in text
    assert data["disclaimer"]["zh"] and data["disclaimer"]["en"]
    assert "T" not in data["config"]["as_of"]


def test_scan_result_schema() -> None:
    data = json.loads(canonical.dumps(pipeline.run_scan(FIX / "unsupported")))
    jsonschema.validate(data, json.loads((SCHEMAS / "scan.schema.json").read_text(encoding="utf-8")))
    assert data["formats"] == {"EDF": 1} and data["unsupported"][0]["format"] == "CNT"


def test_single_file_target() -> None:
    results = pipeline.run_check(FIX / "edf_mixed" / "rec_256.edf", OPTIONS)
    assert len(results.recordings) == 1
    with pytest.raises(InputError) as info:
        pipeline.run_check(FIX / "unsupported" / "legacy.cnt", OPTIONS)
    assert info.value.message_key == "input.unknown_format"
    with pytest.raises(InputError):
        pipeline.run_check(FIX / "does-not-exist", OPTIONS)
    with pytest.raises(UnsafePathError):
        pipeline.run_check("\\\\server\\share\\data", OPTIONS)


CUSTOM = """rulepack: lab
version: "1.0"
source: Lab SOP 7
source_status: final
rules:
  - id: LAB-ACQ-001
    clause: "SOP-7 3.2"
    title_zh: 采样率至少 1000 Hz
    title_en: Sampling rate at least 1000 Hz
    phase: acquisition
    check: signal.sampling_rate_min
    params: {min_hz: 1000}
    severity: error
    verification: automatic
"""


def test_custom_rulepack_without_code_change(tmp_path: Path) -> None:
    path = tmp_path / "lab.yaml"
    path.write_text(CUSTOM, encoding="utf-8")
    results = pipeline.run_check(
        FIX / "edf_ok", pipeline.CheckOptions(rulepacks=(str(path),), as_of=OPTIONS.as_of)
    )
    assert [p.name for p in results.rulepacks] == ["core", "lab"]
    assert results.summary.exit_code == 1
    finding = next(f for f in results.findings if f.rule_id == "LAB-ACQ-001")
    assert finding.status is Status.FAILED and finding.threshold == 1000 and finding.clause == "SOP-7 3.2"


def test_rulepack_errors(tmp_path: Path) -> None:
    with pytest.raises(RulepackError) as info:
        pipeline.run_check(FIX / "edf_ok", pipeline.CheckOptions(rulepacks=("nosuchpack",)))
    assert info.value.message_key == "rulepack.not_found"
    with pytest.raises(RulepackError):
        pipeline.run_check(FIX / "edf_ok", pipeline.CheckOptions(rulepacks=(str(tmp_path / "missing.yaml"),)))
    draft = tmp_path / "draft.yaml"
    draft.write_text(CUSTOM.replace("source_status: final", "source_status: placeholder"), encoding="utf-8")
    with pytest.raises(RulepackError) as info:
        pipeline.run_check(FIX / "edf_ok", pipeline.CheckOptions(rulepacks=(str(draft),)))
    assert info.value.message_key == "rulepack.placeholder_needs_flag"
    allowed = pipeline.run_check(
        FIX / "edf_ok",
        pipeline.CheckOptions(
            rulepacks=(str(draft),), allow_draft_rulepacks=True, config_path=documented_config(tmp_path)
        ),
    )
    assert allowed.summary.exit_code == 0
    assert any(f.rule_id == "LAB-ACQ-001" and f.status is Status.FAILED for f in allowed.findings)
    dup = tmp_path / "dup.yaml"
    dup.write_text(CUSTOM.replace("rulepack: lab", "rulepack: core"), encoding="utf-8")
    with pytest.raises(RulepackError) as info:
        pipeline.run_check(FIX / "edf_ok", pipeline.CheckOptions(rulepacks=(str(dup),)))
    assert info.value.message_key == "rulepack.duplicate_pack"


def test_config_overrides_exceptions_and_dates(tmp_path: Path) -> None:
    config = tmp_path / "neurogrid.toml"
    config.write_text(
        """[dataset]
id = "lab-ds"
[check]
as_of = 2026-12-01
[rules."CORE-M03-01".params]
min_hz = 200
[[exceptions]]
rule = "CORE-M03-02"
reason = "Two amplifier generations, see SOP-3."
""",
        encoding="utf-8",
    )
    results = pipeline.run_check(FIX / "edf_mixed", pipeline.CheckOptions(config_path=config))
    assert results.config.as_of == date(2026, 12, 1)
    assert results.dataset.id == "lab-ds"
    assert results.config.effective_params["CORE-M03-01"]["min_hz"].origin == "config"
    assert not [f for f in results.findings if f.rule_id == "CORE-M03-01"]
    excepted = [f for f in results.findings if f.rule_id == "CORE-M03-02"]
    assert excepted[0].status is Status.EXCEPTED and results.exceptions[0].used
    bad = tmp_path / "bad.toml"
    bad.write_text('[rules."CORE-M03-01".params]\nmin_hz = "x"\n', encoding="utf-8")
    with pytest.raises(ConfigError):
        pipeline.run_check(FIX / "edf_ok", pipeline.CheckOptions(config_path=bad))


def test_show_paths_reveals_names_only_on_request() -> None:
    hidden = pipeline.run_check(FIX / "edf_ok", OPTIONS)
    assert all(r.id.startswith("rec-") for r in hidden.recordings)
    shown = pipeline.run_check(FIX / "edf_ok", pipeline.CheckOptions(show_paths=True, as_of=OPTIONS.as_of))
    assert sorted(r.id for r in shown.recordings) == ["rec_a.edf", "rec_b.edf"]


def test_environment_block() -> None:
    env = pipeline.run_check(FIX / "edf_ok", OPTIONS).environment
    assert env.libraries["mne"] != "missing" and env.python.count(".") == 1
    # The BIDS validator, its runtime and the EEGLAB readers change results as well (A-11, A-48).
    for name in ("bids-validator-deno", "deno", "pymatreader", "h5py"):
        assert env.libraries[name] != "missing", name


LAB_PACK = CUSTOM.replace("rulepack: lab", "rulepack: lab")


def _dataset_with_config(tmp_path: Path, toml: str) -> Path:
    dataset = tmp_path / "ds"
    dataset.mkdir()
    for name in ("rec_a.edf", "rec_b.edf"):
        (dataset / name).write_bytes((FIX / "edf_ok" / name).read_bytes())
    (dataset / ".neurogrid").mkdir()
    (dataset / ".neurogrid" / "neurogrid.toml").write_text(toml, encoding="utf-8")
    (dataset / ".neurogrid" / "lab.yaml").write_text(LAB_PACK, encoding="utf-8")
    return dataset


def test_toml_rule_pack_paths_are_relative_to_the_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dataset = _dataset_with_config(tmp_path, '[check]\nrulepacks = ["core", ".neurogrid/lab.yaml"]\n')
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    for cwd in (dataset, elsewhere):
        monkeypatch.chdir(cwd)
        results = pipeline.run_check(dataset, OPTIONS)
        assert [p.name for p in results.rulepacks] == ["core", "lab"]


@pytest.mark.parametrize("ref", ["../outside.yaml", "C:/outside.yaml", "/outside.yaml"])
def test_toml_rule_pack_paths_may_not_leave_the_project(tmp_path: Path, ref: str) -> None:
    (tmp_path / "outside.yaml").write_text(CUSTOM, encoding="utf-8")
    dataset = _dataset_with_config(tmp_path, f'[check]\nrulepacks = ["core", "{ref}"]\n')
    with pytest.raises(ConfigError) as info:
        pipeline.run_check(dataset, OPTIONS)
    assert info.value.message_key == "config.unsafe_path"


def test_linked_config_folder_is_refused(tmp_path: Path) -> None:
    from conftest import dir_link

    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (foreign / "neurogrid.toml").write_text(
        '[[exceptions]]\nrule = "CORE-M01-04"\nreason = "hide"\n', encoding="utf-8"
    )
    dataset = tmp_path / "ds"
    dataset.mkdir()
    (dataset / "rec.edf").write_bytes((FIX / "edf_ok" / "rec_a.edf").read_bytes())
    dir_link(dataset / ".neurogrid", foreign)
    with pytest.raises(UnsafePathError) as info:
        pipeline.run_check(dataset, OPTIONS)
    assert info.value.message_key == "path.link"


def _raw_with_exception(tmp_path: Path, pattern: str) -> tuple[Path, Path]:
    dataset = tmp_path / "raw"
    site = dataset / "Mustermann_Max_1985"
    site.mkdir(parents=True)
    (site / "rec.edf").write_bytes((FIX / "edf_ok" / "rec_a.edf").read_bytes())
    (site / "legacy.cnt").write_bytes(b"x")
    config = tmp_path / "neurogrid.toml"
    config.write_text(
        DOCUMENTED_TOML + f'[[exceptions]]\nrule = "CORE-M01-04"\nobject = "{pattern}"\n'
        'reason = "Legacy export kept (SOP-9)."\n',
        encoding="utf-8",
    )
    return dataset, config


def test_exception_patterns_use_relative_paths_and_ignore_show_paths(tmp_path: Path) -> None:
    dataset, config = _raw_with_exception(tmp_path, "Mustermann_Max_1985/*.cnt")
    hidden = pipeline.run_check(dataset, pipeline.CheckOptions(config_path=config, as_of=OPTIONS.as_of))
    shown = pipeline.run_check(
        dataset, pipeline.CheckOptions(config_path=config, as_of=OPTIONS.as_of, show_paths=True)
    )
    for results in (hidden, shown):
        assert results.summary.exit_code == 0 and results.exceptions[0].used
        assert [f.status for f in results.findings if f.rule_id == "CORE-M01-04"] == [Status.EXCEPTED]
    assert [f.key for f in hidden.findings] == [f.key for f in shown.findings]
    text = canonical.dumps(hidden).decode("utf-8")
    assert "Mustermann" not in text and "pattern-" in text
    assert "Mustermann" in canonical.dumps(shown).decode("utf-8")


def test_pseudonymous_exception_pattern_works_in_both_modes(tmp_path: Path) -> None:
    from neurogrid.io.discover import pseudonym

    dataset, _ = _raw_with_exception(tmp_path, "x")
    rec_id = pseudonym(PurePosixPath("Mustermann_Max_1985/legacy.cnt"))
    config = tmp_path / "pseudo.toml"
    config.write_text(
        DOCUMENTED_TOML + f'[[exceptions]]\nrule = "CORE-M01-04"\nobject = "{rec_id}"\nreason = "SOP-9"\n',
        encoding="utf-8",
    )
    for show in (False, True):
        results = pipeline.run_check(
            dataset, pipeline.CheckOptions(config_path=config, as_of=OPTIONS.as_of, show_paths=show)
        )
        assert results.summary.exit_code == 0 and results.exceptions[0].entry.object == rec_id


def test_folder_formats_fail_m01(tmp_path: Path) -> None:
    (tmp_path / "rec.edf").write_bytes((FIX / "edf_ok" / "rec_a.edf").read_bytes())
    (tmp_path / "sub01_rest.mff").mkdir()
    (tmp_path / "sub01_rest.mff" / "signal1.bin").write_bytes(b"\x00" * 16)
    results = pipeline.run_check(tmp_path, OPTIONS)
    unsupported = [f for f in results.findings if f.rule_id == "CORE-M01-04"]
    assert results.summary.exit_code == 1 and len(unsupported) == 1
    assert unsupported[0].file and unsupported[0].file.endswith(".mff")


def test_findings_carry_effective_thresholds() -> None:
    results = pipeline.run_check(FIX / "edf_lowrate", OPTIONS)
    finding = next(f for f in results.findings if f.rule_id == "CORE-M03-01")
    assert finding.params["min_hz"].value == 500 and finding.params["min_hz"].origin == "rulepack"


def test_recording_summary_from_the_data_model(tmp_path: Path) -> None:
    eeg = tmp_path / "sub-07" / "eeg"
    eeg.mkdir(parents=True)
    (tmp_path / "dataset_description.json").write_text(
        '{"Name": "D", "BIDSVersion": "1.11.1"}', encoding="utf-8"
    )
    (eeg / "sub-07_task-rest_eeg.edf").write_bytes((FIX / "edf_ok" / "rec_a.edf").read_bytes())
    summary = pipeline.run_check(tmp_path, OPTIONS).recordings[0]
    assert (summary.subject, summary.task, summary.sampling_rate_hz) == ("07", "rest", 512.0)
    assert summary.metadata_sources["subject"] == "bids_filename"
    assert summary.metadata_sources["sampling_rate_hz"] == "header"


def test_effective_settings_and_sampling_in_results() -> None:
    results = pipeline.run_check(FIX / "edf_ok", OPTIONS)
    assert results.config.sampling == {"mode": "sample", "segment_s": 60.0, "segments": 10}
    assert results.config.effective_settings["vault"]["path"] == ".neurogrid/vault"


def test_name_hint_notice(tmp_path: Path) -> None:
    (tmp_path / "Zhang_4711234.edf").write_bytes((FIX / "edf_ok" / "rec_a.edf").read_bytes())
    results = pipeline.run_check(tmp_path, OPTIONS)
    assert any(
        n.message_key == "notice.names_look_identifying" and n.params == {"count": 1} for n in results.notices
    )
    assert "4711234" not in canonical.dumps(results).decode("utf-8")


@pytest.mark.skipif(sys.platform != "win32", reason="lone surrogates in names are a Windows case here")
def test_undecodable_name_does_not_crash_check(tmp_path: Path) -> None:
    (tmp_path / "rec.edf").write_bytes((FIX / "edf_ok" / "rec_a.edf").read_bytes())
    try:
        (tmp_path / "notiz_\udc80.txt").write_bytes(b"x")
    except (OSError, UnicodeError):
        pytest.skip("file system refuses the name")
    for show in (False, True):
        results = pipeline.run_check(tmp_path, pipeline.CheckOptions(as_of=OPTIONS.as_of, show_paths=show))
        canonical.dumps(results)


def test_annotation_only_files_are_readable_but_no_recording(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "unit"))  # also when run on its own
    from test_io import _annotation_only_edf  # type: ignore[import-not-found]

    psg = tmp_path / "psg"
    psg.mkdir()
    (psg / "night.edf").write_bytes((FIX / "edf_ok" / "rec_a.edf").read_bytes())
    _annotation_only_edf(psg / "night_hypnogram.edf")
    documented = pipeline.CheckOptions(config_path=documented_config(tmp_path), as_of=OPTIONS.as_of)
    results = pipeline.run_check(psg, documented)
    assert results.summary.exit_code == 0
    assert not [f for f in results.findings if f.rule_id == "CORE-M01-01"]
    only = tmp_path / "only"
    only.mkdir()
    _annotation_only_edf(only / "h.edf")
    alone = pipeline.run_check(only, documented)
    reasons = {f.reason for f in alone.findings if f.rule_id == "CORE-M01-01"}
    assert alone.summary.exit_code == 1 and reasons == {"dataset.no_readable_recording"}


@pytest.mark.parametrize(
    ("offset", "value", "exit_code"),
    [
        (244, b"1e-320  ", 1),  # out of range: header issue (A-75)
        (236, b"99999999", 1),  # far more records than the file holds: truncated
        (244, b"1e99    ", 0),  # a legal (absurd) duration; the rate is low, which is only a warning
    ],
)
def test_extreme_header_values_never_stop_the_run(
    tmp_path: Path, offset: int, value: bytes, exit_code: int
) -> None:
    folder = tmp_path / "ds"
    folder.mkdir()
    (folder / "good.edf").write_bytes((FIX / "edf_ok" / "rec_a.edf").read_bytes())
    data = bytearray((FIX / "edf_ok" / "rec_a.edf").read_bytes())
    data[offset : offset + 8] = value
    (folder / "bad.edf").write_bytes(bytes(data))
    options = pipeline.CheckOptions(config_path=documented_config(tmp_path), as_of=OPTIONS.as_of)
    results = pipeline.run_check(folder, options)
    canonical.dumps(results)
    assert results.summary.exit_code == exit_code


def test_links_are_reported_by_check(tmp_path: Path) -> None:
    from conftest import dir_link

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "legacy.cnt").write_bytes(b"x")
    dataset = tmp_path / "ds"
    dataset.mkdir()
    (dataset / "rec.edf").write_bytes((FIX / "edf_ok" / "rec_a.edf").read_bytes())
    dir_link(dataset / "linked", outside)
    results = pipeline.run_check(dataset, OPTIONS)
    notice = next(n for n in results.notices if n.message_key == "notice.links_skipped")
    assert notice.params == {"count": 1} and notice.level.value == "warning"


def test_unlistable_folder_fails_m01(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    (tmp_path / "good.edf").write_bytes((FIX / "edf_ok" / "rec_a.edf").read_bytes())
    locked = tmp_path / "Mustermann_locked"
    locked.mkdir()
    real_scandir = os.scandir

    def scandir(path: object = ".") -> object:
        if Path(str(path)).resolve() == locked.resolve():
            raise PermissionError(13, "denied", str(path))
        return real_scandir(path)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "scandir", scandir)
    results = pipeline.run_check(tmp_path, OPTIONS)
    failed = [f for f in results.findings if f.rule_id == "CORE-M01-01" and f.reason == "read.unlistable"]
    assert results.summary.exit_code == 1 and len(failed) == 1
    assert "Mustermann" not in canonical.dumps(results).decode("utf-8")


def test_folder_format_as_target_is_unknown_format(tmp_path: Path) -> None:
    target = tmp_path / "sub01.mff"
    target.mkdir()
    with pytest.raises(InputError) as info:
        pipeline.run_check(target, OPTIONS)
    assert info.value.message_key == "input.unknown_format"


def test_single_file_ids_do_not_depend_on_typed_case() -> None:
    typed = str(FIX / "edf_ok" / "REC_A.EDF")
    if not Path(typed).exists():
        pytest.skip("case-sensitive file system")
    shown = pipeline.run_check(typed, pipeline.CheckOptions(as_of=OPTIONS.as_of, show_paths=True))
    assert shown.recordings[0].id == "rec_a.edf"


def _other_spellings(dataset: Path) -> list[str]:
    """Command-line spellings of <dataset>/.neurogrid/lab.yaml from inside the dataset (A-66): a doubled
    separator, a detour through '..', the absolute path; on Windows also backslashes and another case. On
    POSIX a backslash is an ordinary character of a name, so '.\\.neurogrid\\lab.yaml' names another
    (missing) file there: the Linux CI failure 'rulepack.not_found' was the test's, not the loader's."""
    spellings = [
        "./.neurogrid//lab.yaml",
        ".neurogrid/../.neurogrid/lab.yaml",
        str(dataset / ".neurogrid" / "lab.yaml"),
    ]
    if sys.platform == "win32":
        spellings.append(".\\.neurogrid\\lab.yaml")
        if Path(".NeuroGrid", "LAB.yaml").is_file():  # a case-insensitive folder (the usual one on Windows)
            spellings.append(".NeuroGrid\\LAB.yaml")
    return spellings


def test_rule_packs_are_deduplicated_by_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dataset = _dataset_with_config(tmp_path, '[check]\nrulepacks = ["core", ".neurogrid/lab.yaml"]\n')
    monkeypatch.chdir(dataset)
    for spelling in _other_spellings(dataset):
        same = pipeline.run_check(dataset, pipeline.CheckOptions(rulepacks=(spelling,), as_of=OPTIONS.as_of))
        assert [p.name for p in same.rulepacks] == ["core", "lab"], spelling
    if sys.platform != "win32":  # the backslash spelling is another file on POSIX, not the same pack again
        with pytest.raises(RulepackError) as info:
            pipeline.run_check(
                dataset, pipeline.CheckOptions(rulepacks=(".\\.neurogrid\\lab.yaml",), as_of=OPTIONS.as_of)
            )
        assert info.value.message_key == "rulepack.not_found"
    elsewhere = tmp_path / "cwd"
    (elsewhere / ".neurogrid").mkdir(parents=True)
    (elsewhere / ".neurogrid" / "lab.yaml").write_text(
        CUSTOM.replace("rulepack: lab", "rulepack: other").replace("LAB-", "OTHER-"), encoding="utf-8"
    )
    monkeypatch.chdir(elsewhere)
    both = pipeline.run_check(
        dataset, pipeline.CheckOptions(rulepacks=(".neurogrid/lab.yaml",), as_of=OPTIONS.as_of)
    )
    assert [p.name for p in both.rulepacks] == ["core", "lab", "other"]


def test_explicit_config_in_dot_neurogrid_uses_its_dataset_as_project_root(tmp_path: Path) -> None:
    dataset = _dataset_with_config(tmp_path, '[check]\nrulepacks = ["core", ".neurogrid/lab.yaml"]\n')
    sub = dataset / "sub"
    sub.mkdir()
    (sub / "r.edf").write_bytes((FIX / "edf_ok" / "rec_a.edf").read_bytes())
    config = dataset / ".neurogrid" / "neurogrid.toml"
    results = pipeline.run_check(
        sub / "r.edf", pipeline.CheckOptions(config_path=config, as_of=OPTIONS.as_of)
    )
    assert [p.name for p in results.rulepacks] == ["core", "lab"]


def test_exception_by_displayed_file_name(tmp_path: Path) -> None:
    from neurogrid.io.discover import pseudonym

    dataset, _ = _raw_with_exception(tmp_path, "x")
    shown_name = pseudonym(PurePosixPath("Mustermann_Max_1985/legacy.cnt")) + ".cnt"
    config = tmp_path / "file.toml"
    config.write_text(
        DOCUMENTED_TOML
        + f'[[exceptions]]\nrule = "CORE-M01-04"\nobject = "{shown_name}"\nreason = "SOP-9"\n',
        encoding="utf-8",
    )
    results = pipeline.run_check(dataset, pipeline.CheckOptions(config_path=config, as_of=OPTIONS.as_of))
    assert results.summary.exit_code == 0 and results.exceptions[0].used


@pytest.mark.parametrize(
    ("toml", "key"),
    [
        ('[rules."CORE-M03-01".params]\nmin_hz = inf\n', "config.invalid"),
        ('[rules."CORE-M03-01".params]\nmin_hz = nan\n', "config.invalid"),
        ("[metadata.defaults]\nline_frequency_hz = inf\n", "config.invalid"),
        ("[check]\nseed = " + "9" * 5000 + "\n", "config.syntax"),
    ],
)
def test_non_finite_and_oversized_config_values(tmp_path: Path, toml: str, key: str) -> None:
    config = tmp_path / "n.toml"
    config.write_text(toml, encoding="utf-8")
    with pytest.raises(ConfigError) as info:
        pipeline.run_check(FIX / "edf_ok", pipeline.CheckOptions(config_path=config, as_of=OPTIONS.as_of))
    assert info.value.message_key == key


def test_non_finite_rule_pack_parameter(tmp_path: Path) -> None:
    pack = tmp_path / "nan.yaml"
    pack.write_text(CUSTOM.replace("min_hz: 1000", "min_hz: .nan"), encoding="utf-8")
    with pytest.raises(RulepackError) as info:
        pipeline.run_check(FIX / "edf_ok", pipeline.CheckOptions(rulepacks=(str(pack),), as_of=OPTIONS.as_of))
    assert info.value.message_key == "rulepack.param_type"


def test_entities_survive_an_unreadable_header(tmp_path: Path) -> None:
    eeg = tmp_path / "sub-03" / "eeg"
    eeg.mkdir(parents=True)
    (tmp_path / "dataset_description.json").write_text('{"Name": "D"}', encoding="utf-8")
    (eeg / "sub-03_task-rest_eeg.edf").write_bytes(b"0" * 100)
    summary = pipeline.run_check(tmp_path, OPTIONS).recordings[0]
    assert (summary.subject, summary.task) == ("03", "rest")
    assert summary.metadata_sources == {"subject": "bids_filename", "task": "bids_filename"}


def test_exception_by_displayed_file_name_ignores_show_paths(tmp_path: Path) -> None:
    """A-68: the pseudonymous file name shown in raw folders keeps working with --show-paths."""
    from neurogrid.io.discover import pseudonym

    dataset, _ = _raw_with_exception(tmp_path, "x")
    shown_name = pseudonym(PurePosixPath("Mustermann_Max_1985/legacy.cnt")) + ".cnt"
    config = tmp_path / "file.toml"
    config.write_text(
        DOCUMENTED_TOML
        + f'[[exceptions]]\nrule = "CORE-M01-04"\nobject = "{shown_name}"\nreason = "SOP-9"\n',
        encoding="utf-8",
    )
    keys = []
    for show in (False, True):
        results = pipeline.run_check(
            dataset, pipeline.CheckOptions(config_path=config, as_of=OPTIONS.as_of, show_paths=show)
        )
        assert results.summary.exit_code == 0 and results.exceptions[0].used
        keys.append([f.key for f in results.findings])
    assert keys[0] == keys[1]


@pytest.mark.parametrize(
    ("toml", "key"),
    [
        ('[rules."CORE-M03-01".params]\nmin_hz = 1' + "0" * 400 + "\n", "config.param_type"),
        ("[check]\nseed = -1\n", "config.invalid"),
        ("[check]\nseed = 1" + "0" * 30 + "\n", "config.invalid"),
        ('[check]\nrulepacks = ["core", "CONIN$"]\n', "config.unsafe_path"),
        ('[check]\nrulepacks = ["core", "packs/COM\u00b9.yaml"]\n', "config.unsafe_path"),
    ],
)
def test_out_of_range_and_reserved_config_values(tmp_path: Path, toml: str, key: str) -> None:
    config = tmp_path / "r.toml"
    config.write_text(toml, encoding="utf-8")
    with pytest.raises(ConfigError) as info:
        pipeline.run_check(FIX / "edf_ok", pipeline.CheckOptions(config_path=config, as_of=OPTIONS.as_of))
    assert info.value.message_key == key


def test_huge_integer_in_rule_pack(tmp_path: Path) -> None:
    for value in ("1" + "0" * 400, "1" + "0" * 5000):
        pack = tmp_path / "big.yaml"
        pack.write_text(CUSTOM.replace("min_hz: 1000", f"min_hz: {value}"), encoding="utf-8")
        with pytest.raises((RulepackError, ConfigError)) as info:
            pipeline.run_check(
                FIX / "edf_ok", pipeline.CheckOptions(rulepacks=(str(pack),), as_of=OPTIONS.as_of)
            )
        assert info.value.message_key in ("rulepack.param_type", "yaml.syntax")


def test_config_folder_name_is_case_insensitive_on_windows(tmp_path: Path) -> None:
    if sys.platform != "win32":
        pytest.skip("case-insensitive file system")
    project = tmp_path / "proj"
    (project / ".NeuroGrid").mkdir(parents=True)
    (project / "packs").mkdir()
    (project / "packs" / "lab.yaml").write_text(CUSTOM, encoding="utf-8")
    config = project / ".NeuroGrid" / "neurogrid.toml"
    config.write_text('[check]\nrulepacks = ["core", "packs/lab.yaml"]\n', encoding="utf-8")
    results = pipeline.run_check(
        FIX / "edf_ok", pipeline.CheckOptions(config_path=config, as_of=OPTIONS.as_of)
    )
    assert [p.name for p in results.rulepacks] == ["core", "lab"]


def test_edf_plus_d_with_annotation_channel_documents_all_channel_columns(tmp_path: Path) -> None:
    """An EDF+ annotation signal has no unit; it is no channel and does not undo the header columns (A-77)."""
    results = pipeline.run_check(
        FIX / "edf_plus_d",
        pipeline.CheckOptions(config_path=documented_config(tmp_path), as_of=OPTIONS.as_of),
    )
    failed = {(f.rule_id, f.subkey) for f in results.findings if f.status is Status.FAILED}
    assert not {rule for rule, _subkey in failed} & {"CORE-M01-01", "CORE-M01-02", "CORE-M01-03"}
    assert not [subkey for rule, subkey in failed if rule == "CORE-M02-01"]
    assert results.summary.exit_code == 0


@pytest.mark.parametrize("show_paths", [False, True])
def test_cnt_and_xdf_files_are_m01_errors_with_their_file_name(tmp_path: Path, show_paths: bool) -> None:
    """KONZEPT P2: a folder with .cnt/.xdf gives an M01 error that names the file (A-12, A-70)."""
    from neurogrid.io.discover import pseudonym

    dataset = tmp_path / "ds"
    dataset.mkdir()
    (dataset / "rec.edf").write_bytes((FIX / "edf_ok" / "rec_a.edf").read_bytes())
    for name in ("session.xdf", "legacy.cnt"):
        (dataset / name).write_bytes(b"\x00" * 32)
    options = pipeline.CheckOptions(
        config_path=documented_config(tmp_path), as_of=OPTIONS.as_of, show_paths=show_paths
    )
    results = pipeline.run_check(dataset, options)
    unsupported = sorted((f.file, f.status, f.reason) for f in results.findings if f.rule_id == "CORE-M01-04")
    names = ("legacy.cnt", "session.xdf")
    shown = (
        list(names)
        if show_paths
        else [f"{pseudonym(PurePosixPath(n))}{PurePosixPath(n).suffix}" for n in names]
    )
    assert unsupported == sorted((name, Status.FAILED, "format.unsupported") for name in shown)
    assert results.summary.exit_code == 1
