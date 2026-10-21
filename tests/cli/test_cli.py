"""Command line: exit codes 0/1/2 (NG-F14), messages, list options, sanitized errors."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import documented_config  # type: ignore[import-not-found]
from neurogrid.cli import main

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"


def run(args: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    with pytest.raises(SystemExit) as info:
        main(args)
    out, err = capsys.readouterr()
    return int(info.value.code or 0), out, err


def test_check_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    documented = str(documented_config(tmp_path))
    code, out, _ = run(
        [
            "check",
            str(FIX / "edf_ok"),
            "--out",
            str(tmp_path / "ok.json"),
            "--as-of",
            "2026-10-11",
            "--config",
            documented,
        ],
        capsys,
    )
    assert code == 0 and "passes the checks" in out and "Not a conformity assessment" in out
    code, out, _ = run(["check", str(FIX / "edf_ok"), "--out", str(tmp_path / "raw.json")], capsys)
    assert code == 1 and "does not pass" in out  # raw folder without documented metadata (M02-01)
    code, out, _ = run(["check", str(FIX / "edf_truncated"), "--out", str(tmp_path / "bad.json")], capsys)
    assert code == 1 and "does not pass" in out
    code, _, err = run(["check", str(FIX / "edf_ok"), "--rulepack", "nosuch"], capsys)
    assert code == 2 and "nosuch" in err
    code, _, err = run(["check", str(FIX / "edf_ok"), "--as-of", "11.10.2026"], capsys)
    assert code == 2 and "YYYY-MM-DD" in err
    code, _, err = run(["check"], capsys)
    assert code == 2
    code, _, err = run(["check", str(FIX / "unsupported" / "legacy.cnt")], capsys)
    assert code == 2 and "legacy.cnt" in err


def test_chinese_messages(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = str(documented_config(tmp_path))
    code, out, _ = run(
        [
            "--lang",
            "zh",
            "check",
            str(FIX / "edf_lowrate"),
            "--out",
            str(tmp_path / "r.json"),
            "--config",
            config,
        ],
        capsys,
    )
    assert code == 0 and "通过了已加载规则包" in out and "符合性评价" in out


def test_scan_and_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(["scan", str(FIX / "unsupported"), "--out", str(tmp_path / "scan.json")], capsys)
    assert code == 0 and "CNT" in out
    assert json.loads((tmp_path / "scan.json").read_text(encoding="utf-8"))["formats"] == {"EDF": 1}
    results = tmp_path / "results.json"
    run(["check", str(FIX / "edf_mixed"), "--out", str(results)], capsys)
    code, out, _ = run(
        ["report", str(results), "--lang", "zh", "--lang", "en", "--out", str(tmp_path / "rep")], capsys
    )
    assert (
        code == 0
        and (tmp_path / "rep" / "report.zh.html").is_file()
        and (tmp_path / "rep" / "report.en.html").is_file()
    )
    code, _, _ = run(["report", str(results), "--lang", "zh,en"], capsys)
    assert code == 0 and (tmp_path / "report.en.html").is_file()
    code, _, err = run(["report", str(results), "--format", "pdf"], capsys)
    assert code == 2 and "pdf" in err
    code, _, err = run(["report", str(results), "--lang", "fr"], capsys)
    assert code == 2
    (tmp_path / "broken.json").write_text("{}", encoding="utf-8")
    code, _, err = run(["report", str(tmp_path / "broken.json")], capsys)
    assert code == 2


def test_home_directory_is_not_printed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out_file = Path.home() / ".neurogrid-test-results.json"
    try:
        config = str(documented_config(tmp_path))
        code, out, _ = run(["check", str(FIX / "edf_ok"), "--out", str(out_file), "--config", config], capsys)
        assert code == 0 and str(Path.home()) not in out and "~" in out
    finally:
        out_file.unlink(missing_ok=True)


def test_internal_error_is_exit_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from neurogrid import pipeline

    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError(f"secret {Path.home()}")

    monkeypatch.setattr(pipeline, "run_check", boom)
    code, _, err = run(["check", str(FIX / "edf_ok")], capsys)
    assert code == 2 and "RuntimeError" in err and "secret" not in err
    code, _, err = run(["--debug", "check", str(FIX / "edf_ok")], capsys)
    assert code == 2 and str(Path.home()) not in err and "Traceback" in err


def test_real_subprocess_exit_codes(tmp_path: Path) -> None:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    base = [sys.executable, "-m", "neurogrid"]
    config = str(documented_config(tmp_path))
    ok = subprocess.run(
        [*base, "check", str(FIX / "edf_ok"), "--out", str(tmp_path / "a.json"), "--config", config],
        capture_output=True,
        env=env,
        check=False,
    )
    bad = subprocess.run(
        [*base, "check", str(FIX / "empty"), "--out", str(tmp_path / "b.json")],
        capture_output=True,
        env=env,
        check=False,
    )
    tool = subprocess.run(
        [*base, "check", str(FIX / "edf_ok"), "--rulepack", "nosuch"],
        capture_output=True,
        env=env,
        check=False,
    )
    assert (ok.returncode, bad.returncode, tool.returncode) == (0, 1, 2)


DUP_PACK = (FIX.parent.parent.parent / "src" / "neurogrid" / "rulepacks" / "core.yaml").read_text(
    encoding="utf-8"
)


def test_duplicate_key_in_rule_pack_is_exit_2_without_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pack = tmp_path / "dup.yaml"
    pack.write_text(DUP_PACK.replace("rulepack: core", "rulepack: dup\nversion: '9'", 1), encoding="utf-8")
    for lang in ("en", "zh"):
        code, _, err = run(["--lang", lang, "check", str(FIX / "edf_ok"), "--rulepack", str(pack)], capsys)
        assert code == 2 and "Traceback" not in err and str(Path.home()) not in err
        assert "version" in err


def test_rulepack_paths_keep_case_and_commas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from neurogrid import pipeline

    seen: list[tuple[str, ...]] = []

    def spy(target: object, options: pipeline.CheckOptions) -> None:
        seen.append(options.rulepacks)
        raise SystemExit(0)

    monkeypatch.setattr(pipeline, "run_check", spy)
    with pytest.raises(SystemExit):
        main(["check", str(FIX / "edf_ok"), "--rulepack", "Packs/My Lab,v2.yaml", "--rulepack", "core"])
    assert seen == [("Packs/My Lab,v2.yaml", "core")]


def test_custom_rulepack_path_with_capitals_and_comma(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "My Packs"
    folder.mkdir()
    pack = folder / "Lab_QA,v2.yaml"
    pack.write_text(
        DUP_PACK.replace("rulepack: core", "rulepack: labqa", 1).replace("CORE-", "LABQA-"), encoding="utf-8"
    )
    code, _, err = run(
        [
            "check",
            str(FIX / "edf_ok"),
            "--rulepack",
            str(pack),
            "--out",
            str(tmp_path / "r.json"),
            "--config",
            str(documented_config(tmp_path)),
        ],
        capsys,
    )
    assert code == 0, err
    assert [
        p["name"] for p in json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))["rulepacks"]
    ] == [
        "core",
        "labqa",
    ]


@pytest.mark.parametrize("value", ["zh_CN", "zh-CN", "zh_CN.UTF-8", "ZH"])
def test_language_locale_forms(
    value: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = run(["--lang", value, "scan", str(FIX / "edf_ok")], capsys)
    assert code == 0 and "数据清点" in out
    monkeypatch.setenv("NEUROGRID_LANG", value)
    code, out, _ = run(["scan", str(FIX / "edf_ok")], capsys)
    assert code == 0 and "数据清点" in out


def test_unknown_language_is_an_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _, err = run(["--lang", "de", "scan", str(FIX / "edf_ok")], capsys)
    assert code == 2 and "Unknown language" in err
    monkeypatch.setenv("NEUROGRID_LANG", "fr")
    code, _, err = run(["scan", str(FIX / "edf_ok")], capsys)
    assert code == 2 and "'fr'" in err


def test_control_characters_from_files_are_removed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pack = tmp_path / "evil.yaml"
    pack.write_text(
        DUP_PACK.replace("rulepack: core", "rulepack: evil", 1)
        .replace("CORE-", "EVIL-")
        .replace("min_hz: 500", '"min_hz\\e]0;owned\\a\\rdataset passes": 500'),
        encoding="utf-8",
    )
    code, _, err = run(["check", str(FIX / "edf_ok"), "--rulepack", str(pack)], capsys)
    assert code == 2 and "\x1b" not in err and "\x07" not in err and "\r" not in err


def test_output_folder_is_refused_and_nothing_is_left(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "out"
    target.mkdir()
    code, _, err = run(["check", str(FIX / "edf_ok"), "--out", str(target)], capsys)
    assert code == 2 and "folder" in err
    assert list(tmp_path.iterdir()) == [target] and list(target.iterdir()) == []


def test_written_path_hides_the_dataset_root(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dataset = tmp_path / "Mustermann_Max_1957"
    dataset.mkdir()
    (dataset / "rec.edf").write_bytes((FIX / "edf_ok" / "rec_a.edf").read_bytes())
    config = str(documented_config(tmp_path))
    code, out, _ = run(
        ["check", str(dataset), "--out", str(dataset / "results.json"), "--config", config], capsys
    )
    assert code == 0 and "Mustermann" not in out and "<dataset>" in out


def test_debug_traceback_hides_dataset_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from neurogrid import pipeline

    dataset = tmp_path / "Mustermann_Max_1957"
    dataset.mkdir()

    def boom(*args: object, **kwargs: object) -> None:
        raise OSError(2, "No such file", str(dataset / "x.edf"))

    monkeypatch.setattr(pipeline, "run_check", boom)
    code, _, err = run(["--debug", "check", str(dataset)], capsys)
    assert code == 2 and "Traceback" in err and "Mustermann" not in err and str(Path.home()) not in err


def test_scan_shows_subjects_and_name_hint(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "Zhang_4711234.edf").write_bytes((FIX / "edf_ok" / "rec_a.edf").read_bytes())
    code, out, _ = run(["scan", str(tmp_path)], capsys)
    assert code == 0 and "Subjects: unknown" in out and "1 data file path" in out and "4711234" not in out


def test_mixed_rate_edf_prints_no_library_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "unit"))  # also when run on its own
    from test_io import _mixed_rate_edf  # type: ignore[import-not-found]

    folder = tmp_path / "mixed"
    folder.mkdir()
    _mixed_rate_edf(folder / "psg.edf")
    config = str(documented_config(tmp_path))
    code, _, err = run(["check", str(folder), "--out", str(tmp_path / "r.json"), "--config", config], capsys)
    assert "RuntimeWarning" not in err and str(Path.home()) not in err
    # the samples are all zero: the only error is the flat line of the EEG channel (M08, since P3)
    results = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    errors = {(f["rule_id"], f["subkey"]) for f in results["findings"] if f["severity"] == "error"}
    assert code == 1 and errors == {("CORE-M08-01", "EEG Fz")}


def test_library_warnings_are_reduced_to_their_category(capsys: pytest.CaptureFixture[str]) -> None:
    import warnings

    from neurogrid import cli

    cli._show_warning(RuntimeWarning("secret C:\\Users\\x"), RuntimeWarning, "C:\\Users\\x\\lib.py", 9)
    err = capsys.readouterr().err
    assert "RuntimeWarning" in err and "secret" not in err and "Users" not in err
    assert warnings.showwarning is not None


def test_empty_language_is_an_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = run(["--lang", "", "scan", str(FIX / "edf_ok")], capsys)
    assert code == 2 and "No language given" in err
    results = tmp_path / "r.json"
    run(["check", str(FIX / "edf_ok"), "--out", str(results)], capsys)
    code, _, err = run(["report", str(results), "--lang", " , "], capsys)
    assert code == 2 and "No language given" in err


def test_help_without_arguments_keeps_its_lines(capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = run([], capsys)
    assert code == 2 and "Invalid command line" not in err and err.count("\n") > 5 and "check" in err


def test_output_edge_cases(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = run(["check", str(FIX / "edf_ok"), "--out", str(tmp_path / "newdir") + "\\"], capsys)
    assert code == 2 and "folder" in err and not (tmp_path / "newdir").exists()
    blocker = tmp_path / "afile"
    blocker.write_text("x", encoding="utf-8")
    code, _, err = run(["check", str(FIX / "edf_ok"), "--out", str(blocker / "r.json")], capsys)
    assert code == 2 and "cannot be written" in err and "Internal error" not in err
    results = tmp_path / "r.json"
    run(["check", str(FIX / "edf_ok"), "--out", str(results)], capsys)
    code, _, err = run(["report", str(results), "--out", str(blocker)], capsys)
    assert code == 2 and "cannot be written" in err


def test_debug_traceback_is_cleaned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from neurogrid import pipeline

    dataset = tmp_path / "ds"
    dataset.mkdir()

    secret = "Zh" + "ang_19800101"  # built at run time so that the source line shown carries no name

    def boom(*args: object, **kwargs: object) -> None:
        raise OSError(2, "gone \x1b]0;pwned\x07", str(dataset / secret / "rec.edf"))

    monkeypatch.setattr(pipeline, "run_check", boom)
    code, _, err = run(["--debug", "check", str(dataset)], capsys)
    assert code == 2 and "Traceback" in err
    assert "\x1b" not in err and "\x07" not in err and "Zhang" not in err and "<dataset>/…" in err


def test_check_prints_skipped_links(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from conftest import dir_link

    outside = tmp_path / "outside"
    outside.mkdir()
    dataset = tmp_path / "ds"
    dataset.mkdir()
    (dataset / "rec.edf").write_bytes((FIX / "edf_ok" / "rec_a.edf").read_bytes())
    dir_link(dataset / "linked", outside)
    config = str(documented_config(tmp_path))
    code, out, _ = run(["check", str(dataset), "--out", str(tmp_path / "r.json"), "--config", config], capsys)
    assert code == 0 and "were not followed" in out


def test_device_path_message(capsys: pytest.CaptureFixture[str]) -> None:
    if sys.platform != "win32":
        pytest.skip("Windows path forms")
    code, _, err = run(["scan", "\\??\\GLOBALROOT\\Device\\HarddiskVolume3\\x"], capsys)
    assert code == 2 and "namespace paths" in err


def test_empty_language_variable_is_an_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for value in ("", "  "):
        monkeypatch.setenv("NEUROGRID_LANG", value)
        code, _, err = run(["scan", str(FIX / "edf_ok")], capsys)
        assert code == 2 and "No language given" in err


def test_debug_traceback_cuts_names_with_quotes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from neurogrid import pipeline

    dataset = tmp_path / "ds"
    dataset.mkdir()
    secret = "O'Bri" + "en Max"

    def boom(*args: object, **kwargs: object) -> None:
        raise FileNotFoundError(2, "gone", str(dataset / secret / "a.edf"))

    monkeypatch.setattr(pipeline, "run_check", boom)
    code, _, err = run(["--debug", "check", str(dataset)], capsys)
    assert code == 2 and "Brien" not in err and "<dataset>/…" in err


def test_reserved_device_names_on_the_command_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    if sys.platform != "win32":
        pytest.skip("Windows device names")
    for name in ("COM\u00b9", "CONOUT$", "lpt3.json"):
        code, _, err = run(["check", str(FIX / "edf_ok"), "--out", name], capsys)
        assert code == 2 and "Reserved device names" in err


def test_directory_with_globalroot_in_its_name_is_allowed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "GLOBALROOT-study"
    folder.mkdir()
    (folder / "r.edf").write_bytes((FIX / "edf_ok" / "rec_a.edf").read_bytes())
    code, _, _ = run(["scan", str(folder)], capsys)
    assert code == 0
