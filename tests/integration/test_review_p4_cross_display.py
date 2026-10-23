"""Cross-check of P4, display and privacy (A-51, A-70, C5): a date, a year or a clock time written as the
"extension" of a file name never appears next to its pseudonym (X-interactions-0: one suffix rule,
io.provenance.shown_suffix, for verify, M13 findings, reports, the manifest target and the effective
configuration), annotator patterns whose wildcard stands for a date or time separator are hidden like the
dates and clock times they spell (X-evidence-0), and an output file inside a raw folder is named on the
console like the manifest target (L3)."""

from __future__ import annotations

import re
import shutil
from datetime import date
from pathlib import Path, PurePosixPath

import pytest

from conftest import documented_config  # type: ignore[import-not-found]
from neurogrid import pipeline
from neurogrid.cli import main
from neurogrid.io.discover import pseudonym, scan
from neurogrid.io.provenance import show, shown_suffix, shown_target
from neurogrid.kernel import canonical
from neurogrid.model.results import Results
from neurogrid.report.render import render_report

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"
AS_OF = date(2026, 10, 11)
LANGUAGES = ("zh", "en", "de")
# File names without a format extension whose last dot-part is a compact date of birth, a birth year or the
# minutes of a clock time: the extension rule of A-70 must not show these parts next to the pseudonym.
DATED_NAMES = ("x born.19610312", "Zhang San born 12.03.1961", "Wang Wu lights off 22.31")
# A pseudonym followed by a part that starts with a digit (the old rule showed rec-<sha8>.19610312, .31).
DATED_PSEUDONYM = re.compile(r"rec-[0-9a-f]{8}\.\d")
# Names whose extension stays: one NeuroGrid classifies, and a short ASCII word that the display rule shows.
SHOWN_NAMES = {"Li Si notes.TSV": ".tsv", "Zhao Liu.scoring": ".scoring"}


def run(args: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    with pytest.raises(SystemExit) as info:
        main(args)
    out, err = capsys.readouterr()
    return int(info.value.code or 0), out, err


def _raw(tmp_path: Path) -> Path:
    folder = tmp_path / "ds"
    shutil.copytree(FIX / "edf_ok", folder)
    return folder


def _pseudonymous(name: str) -> str:
    return pseudonym(PurePosixPath(name)) + SHOWN_NAMES.get(name, "")


# --- X-interactions-0: one suffix rule --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "suffix"),
    [
        ("rec 1.EDF", ".edf"),  # a format NeuroGrid reads
        ("a.fif.gz", ".fif.gz"),  # a two-part one it knows (A-74)
        ("legacy.cnt", ".cnt"),
        ("lonely.fdt", ".fdt"),  # an orphan companion
        ("events.tsv", ".tsv"),
        ("events.tsv.gz", ".gz"),
        ("results.json", ".json"),
        ("hyp.scoring", ".scoring"),  # a short ASCII word the display rule shows
        ("scores.v2", ".v2"),
        ("x born.19610312", ""),  # a compact date of birth
        ("Zhang San born 12.03.1961", ""),  # a birth year
        ("Li Si born 03.04.1972", ""),
        ("Wang Wu lights off 22.31", ""),  # the minutes of a clock time
        ("visit.2019", ""),
        ("trace.001", ""),  # digits only
        ("night.10pm", ""),  # a clock time
        ("notes.mar12", ""),  # a date with a month name
        ("id.a123456", ""),  # a long number
        ("a.王伟", ""),  # letters outside ASCII
        ("a.extensionlong", ""),  # longer than ten characters
        ("x", ""),
    ],
)
def test_one_suffix_rule_for_every_pseudonymous_file_name(name: str, suffix: str) -> None:
    """A-51, A-70: the extension next to a pseudonym is one NeuroGrid classifies, or one whose every part is
    a short ASCII word (a letter, then letters or digits) that display_text shows (C5). show() (verify, M13
    findings) and shown_target (the manifest target) use this one rule."""
    assert shown_suffix(name) == suffix
    shown = show(name, plain=False)
    assert shown.object == pseudonym(PurePosixPath(name)) and shown.file == shown.object + suffix
    assert shown_target(name, plain=False) == shown.file
    assert show(name, plain=True).file == name  # in clear in BIDS and with --show-paths


def test_found_files_follow_the_same_rule(tmp_path: Path) -> None:
    """The file names of M01/M10 findings (FoundFile.display_file) and the names exceptions match
    (identity, A-68) agree with show() for the same file."""
    names = (*DATED_NAMES, *SHOWN_NAMES)
    for name in names:
        (tmp_path / name).write_text("planted\n", encoding="utf-8")
    found = {item.relative.as_posix(): item for item in scan(tmp_path).other}
    for name in names:
        assert found[name].display_file == show(name, plain=False).file == _pseudonymous(name)
        assert found[name].identity == show(name, plain=False).identity


def test_new_files_with_a_dated_name_never_show_the_date(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """X-interactions-0 (A-51): files that appear after the manifest are listed by verify and reported by
    CORE-M13-02 (results.json, reports in zh, en and de) without the date part of their name; --show-paths
    shows the names as stored, on request only (D-10 f)."""
    folder = _raw(tmp_path)
    code, _, _ = run(["manifest", str(folder)], capsys)
    assert code == 0
    names = (*DATED_NAMES, *SHOWN_NAMES)
    for name in names:
        (folder / name).write_text("planted\n", encoding="utf-8")
    expected = {_pseudonymous(name) for name in names}
    manifest = str(folder / ".neurogrid" / "manifest.json")
    code, out, err = run(["verify", str(folder), "--manifest", manifest], capsys)
    listed = {line.strip()[2:] for line in out.splitlines() if line.strip().startswith("- ")}
    assert code == 1 and listed == expected and not DATED_PSEUDONYM.search(out + err)
    results_file = tmp_path / "results.json"
    config = str(documented_config(tmp_path))
    code, out, err = run(
        ["check", str(folder), "--out", str(results_file), "--config", config, "--as-of", "2026-10-11"],
        capsys,
    )
    results = Results.model_validate_json(results_file.read_bytes())
    new = {f.file for f in results.findings if f.rule_id == "CORE-M13-02" and f.subkey == "new"}
    assert code == 1 and new == expected
    texts = [out + err, results_file.read_text(encoding="utf-8")]
    texts += [render_report(results, lang) for lang in LANGUAGES]
    for text in texts:
        assert not DATED_PSEUDONYM.search(text) and "Zhang" not in text and "Wang" not in text
    code, out, _ = run(["verify", str(folder), "--manifest", manifest, "--show-paths"], capsys)
    assert code == 1 and all(f"- {name}\n" in out for name in names)


def test_a_manifest_written_under_a_dated_name_is_named_without_the_date(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """X-interactions-0, INT45: the console names a manifest written inside a raw folder by the pseudonymous
    file name verify shows, here without an extension; in clear with --show-paths."""
    folder = _raw(tmp_path)
    for name in DATED_NAMES:
        code, out, _ = run(["manifest", str(folder), "--out", str(folder / name)], capsys)
        assert (
            code == 0 and f"Manifest written to {Path('<dataset>', pseudonym(PurePosixPath(name)))}\n" in out
        )
        assert not DATED_PSEUDONYM.search(out) and "Zhang" not in out and "Wang" not in out
    code, out, _ = run(["manifest", str(folder), "--out", str(folder / "Li Si notes.json")], capsys)
    shown = pseudonym(PurePosixPath("Li Si notes.json")) + ".json"
    assert code == 0 and f"Manifest written to {Path('<dataset>', shown)}\n" in out
    name = DATED_NAMES[1]
    code, out, _ = run(["manifest", str(folder), "--out", str(folder / name), "--show-paths"], capsys)
    assert code == 0 and f"Manifest written to {Path('<dataset>', name)}\n" in out


def test_settings_never_show_a_date_written_as_an_extension(tmp_path: Path) -> None:
    """X-interactions-0, C4: [[annotation.files]] paths of the effective configuration appear in raw folders
    as the pseudonymous file names, without a date, year or clock time as extension; a real one stays."""
    folder = _raw(tmp_path)
    config = documented_config(
        tmp_path,
        '[[annotation.files]]\npath = "x born.19610312"\nrecording = "Wang Wu lights off 22.31"\n'
        '[[annotation.files]]\npath = "hyp/Zhang San born 12.03.1961"\nrecording = "rec_a.edf"\n',
    )
    results = pipeline.run_check(folder, pipeline.CheckOptions(config_path=config, as_of=AS_OF))
    rows = results.config.effective_settings["annotation"]["files"]
    assert [(row["path"], row["recording"]) for row in rows] == [
        (pseudonym(PurePosixPath("x born.19610312")), pseudonym(PurePosixPath("Wang Wu lights off 22.31"))),
        (
            pseudonym(PurePosixPath("hyp/Zhang San born 12.03.1961")),
            pseudonym(PurePosixPath("rec_a.edf")) + ".edf",
        ),
    ]
    texts = [canonical.dumps(results).decode("utf-8"), *(render_report(results, lang) for lang in LANGUAGES)]
    for text in texts:
        assert not DATED_PSEUDONYM.search(text) and "Zhang" not in text and "Wang" not in text
    shown = pipeline.run_check(
        folder, pipeline.CheckOptions(config_path=config, as_of=AS_OF, show_paths=True)
    )
    assert shown.config.effective_settings["annotation"]["files"][0]["path"] == "x born.19610312"


# --- X-evidence-0: wildcards that stand for a date or time separator --------------------------------------


@pytest.mark.parametrize(
    "pattern",
    [
        "night 22?31",  # night 22.31, night 22h31
        "22?31",
        "night 22*31",
        "10?30pm",  # 10.30pm
        "8?30 pm",
        "rater 22?31?00",  # 22.31.00
        "born 12?03?1961",  # 12.03.1961, 12/03/1961, 12-03-1961
        "born 12?03?61",
        "1961?03?12",
    ],
)
def test_patterns_that_spell_a_clock_time_or_a_date_are_hidden(pattern: str) -> None:
    """X-evidence-0 (R10, R13): a wildcard is also filled with '.', ':', '-', '/' and 'h'; a pattern that then
    spells a date, a year or a clock time is not displayable, like the annotator IDs it matches."""
    assert not pipeline._pattern_displayable(pattern)


@pytest.mark.parametrize("pattern", ["scorer*", "*scorer*", "rater-??", "site?-rater-??", "A?", "*", "S?1"])
def test_patterns_over_codes_stay_displayable(pattern: str) -> None:
    """The separators of dates and times do not hide patterns over codes: '/' on both sides of a word is no
    folder path here, and ':' (no A-17 character) is judged as the '.' of the clock-time rule."""
    assert pipeline._pattern_displayable(pattern)


# --- L3: output files inside a raw folder on the console ---------------------------------------------------

SECRET = "Zhang San 1961"


def test_results_inside_a_raw_folder_are_named_like_the_manifest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """L3 (A-51): 'Results written to' names a results file inside a raw folder by the pseudonymous file name
    (after '…' for its folder), like the manifest target; in clear with --show-paths, in BIDS datasets and
    outside the dataset."""
    folder = _raw(tmp_path)
    (folder / SECRET).mkdir()
    options = ["--config", str(documented_config(tmp_path)), "--as-of", "2026-10-11"]
    own = f"{SECRET}/results.json"
    code, out, err = run(
        ["check", str(folder), "--out", str(folder / SECRET / "results.json"), *options], capsys
    )
    shown = show(own, plain=False).file
    assert shown == pseudonym(PurePosixPath(own)) + ".json"
    assert f"Results written to {Path('<dataset>', '…', shown)}\n" in out and "Zhang" not in out + err
    code, out, err = run(["check", str(folder), "--out", str(folder / f"{SECRET}.json"), *options], capsys)
    at_root = pseudonym(PurePosixPath(f"{SECRET}.json")) + ".json"
    assert f"Results written to {Path('<dataset>', at_root)}\n" in out and "Zhang" not in out + err
    target = folder / SECRET / "results.json"
    code, out, _ = run(["check", str(folder), "--out", str(target), "--show-paths", *options], capsys)
    assert f"Results written to {Path('<dataset>', SECRET, 'results.json')}\n" in out
    outside = tmp_path / "out" / "r.json"
    code, out, _ = run(["check", str(folder), "--out", str(outside), *options], capsys)
    written = [line for line in out.splitlines() if line.startswith("Results written to ")]
    assert (
        len(written) == 1
        and written[0].endswith(str(Path("out", "r.json")))
        and "<dataset>" not in written[0]
    )
    bids = tmp_path / "bids"
    shutil.copytree(FIX / "bids_ok", bids)
    code, out, _ = run(["check", str(bids), "--out", str(bids / "sub-01" / "r.json"), *options], capsys)
    assert f"Results written to {Path('<dataset>', 'sub-01', 'r.json')}\n" in out


def test_an_inventory_inside_a_raw_folder_is_named_like_the_manifest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """L3: the same for 'Inventory written to' (scan --out)."""
    folder = _raw(tmp_path)
    (folder / SECRET).mkdir()
    code, out, err = run(["scan", str(folder), "--out", str(folder / SECRET / "inventory.json")], capsys)
    shown = show(f"{SECRET}/inventory.json", plain=False).file
    assert code == 0 and f"Inventory written to {Path('<dataset>', '…', shown)}\n" in out
    assert "Zhang" not in out + err
    target = folder / SECRET / "inventory.json"
    code, out, _ = run(["scan", str(folder), "--out", str(target), "--show-paths"], capsys)
    assert code == 0 and f"Inventory written to {Path('<dataset>', SECRET, 'inventory.json')}\n" in out
