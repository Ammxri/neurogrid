"""Area D (notebook, report en/zh, figures): ``report.publish`` and ``report.render`` on complete run folders
of all three datasets built without any computation (tests/_runs.py), and the stored notebook (NA-01, NA-05,
DoD 1, DoD 2; A-107, F5f, F8 A, F9 B). The end-to-end path with real smoke runs and the executed notebook is
tests/test_report_smoke.py."""

from __future__ import annotations

import csv
import dataclasses
import json
import re
import shutil
import statistics
from pathlib import Path
from types import SimpleNamespace

import pytest

import _runs
import _wording
from neuroarena import compare, paths, records, report
from neuroarena.datasets import DATASETS

NOTEBOOK = paths.NOTEBOOKS / "neuroarena.ipynb"
HEADINGS = {
    "en": ["## Goal", "## Data", "## Method", "## Results", "## Limitations", "## Scope statement"],
    "zh": ["## 目标", "## 数据", "## 方法", "## 结果", "## 局限性", "## 适用范围声明"],
}


@pytest.fixture(scope="module")
def published(tmp_path_factory: pytest.TempPathFactory) -> SimpleNamespace:
    """Two equal fake runs, published and rendered once for the module."""
    base = tmp_path_factory.mktemp("report")
    a = _runs.make_run(base / "runs", "fake-a")
    b = _runs.make_run(base / "runs", "fake-b")
    results = base / "results"
    publication = report.publish([a, b], results)
    en, zh = report.render(results, base / "report" / "en", base / "report" / "zh")
    return SimpleNamespace(
        base=base,
        a=a,
        b=b,
        results=results,
        publication=publication,
        en=en,
        zh=zh,
        texts={"en": en.read_text(encoding="utf-8"), "zh": zh.read_text(encoding="utf-8")},
    )


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_publish_writes_every_file_of_the_results_folder(published: SimpleNamespace) -> None:
    """The files of the module docstring, in its order; curve.csv and sessions.csv are the reported run's
    files with the frozen columns (records)."""
    assert published.publication.files == tuple(published.results / name for name in report.PUBLISHED)
    assert sorted(p.name for p in published.results.iterdir()) == sorted(report.PUBLISHED)
    for name in (paths.CURVE_FILE, paths.SESSIONS_FILE):
        assert (published.results / name).read_bytes() == (published.a / name).read_bytes(), name
    assert records.read_curve(published.results / paths.CURVE_FILE)
    for name in report.PUBLISHED:
        data = (published.results / name).read_bytes()
        if not name.endswith(".png"):
            assert b"\r\n" not in data and not data.startswith(b"\xef\xbb\xbf"), name
            data.decode("utf-8")


def test_publishing_twice_gives_the_same_bytes(published: SimpleNamespace) -> None:
    """Byte-stable outputs: the figures with fixed metadata and hash salt, the rest sorted, without times."""
    again = published.base / "results-again"
    report.publish([published.a, published.b], again)
    for name in report.PUBLISHED:
        assert (again / name).read_bytes() == (published.results / name).read_bytes(), name


def test_figures_carry_no_date_and_no_time(published: SimpleNamespace) -> None:
    svg = (published.results / f"{report.QUALITY_FIGURE}.svg").read_text(encoding="utf-8")
    assert svg.startswith("<?xml") and "<dc:date>" not in svg
    png = (published.results / f"{report.DEGRADATION_FIGURE}.png").read_bytes()
    assert png.startswith(b"\x89PNG") and b"tIME" not in png


def test_quality_summary_and_unmeasured_count_what_quality_json_holds(published: SimpleNamespace) -> None:
    """quality_summary.csv: per dataset and condition the recordings and sessions per level, the share at Q4
    or worse, the worst-rule and not-measurable counts and the median ratios; unmeasured.csv: NeuroGrid's
    reasons."""
    rows = {(r["dataset"], r["condition"]): r for r in _rows(published.results / report.QUALITY_SUMMARY_FILE)}
    assert list(_rows(published.results / report.QUALITY_SUMMARY_FILE)[0]) == list(
        report.QUALITY_SUMMARY_COLUMNS
    )
    assert len(rows) == len(_runs.DATASET_NAMES) * len(_runs.CONDITION_IDS)
    zhou = rows["Zhou2016", "clean"]  # M06 0.35 / 0.30625: Q4 in all 4 recordings; M09b not measurable
    assert (zhou["n_recordings"], zhou["recordings_q4"], zhou["q4_or_worse_share"]) == ("4", "4", "1.0")
    assert (zhou["worst_CORE-M06-01"], zhou["unmeasured_CORE-M09-02"], zhou["median_ratio_CORE-M09-02"]) == (
        "4",
        "4",
        "",
    )
    assert float(zhou["median_ratio_CORE-M06-01"]) == pytest.approx(0.35 / 0.30625)
    cho = rows["Cho2017", "clean"]  # M09a 0.5 / 0.305083: Q5
    assert (cho["recordings_q5"], cho["worst_CORE-M09-01"]) == ("2", "2")
    flat = rows["Kalunga2016", "channels-1"]  # one flat channel: ratio 20, Q5 everywhere
    assert (flat["recordings_q5"], flat["worst_CORE-M08-01"], flat["sessions_q5"]) == ("4", "4", "2")
    gap = rows["Kalunga2016", "artifacts-5"]  # subject 2 has no measurable rule: its session has no level
    assert (gap["recordings_without_level"], gap["sessions_without_level"], gap["q4_or_worse_share"]) == (
        "2",
        "1",
        "0.5",
    )
    reasons = _rows(published.results / report.UNMEASURED_FILE)
    assert list(reasons[0]) == list(report.UNMEASURED_COLUMNS)
    found = {(r["dataset"], r["condition"], r["rule_id"], r["reason"]): r["recordings"] for r in reasons}
    assert found["Zhou2016", "clean", "CORE-M09-02", "quality.too_few_channels"] == "4"
    assert found["Kalunga2016", "artifacts-5", "CORE-M06-01", "quality.too_short"] == "2"
    assert not any(key[0] == "Cho2017" for key in found)


def test_method_json_states_the_method_without_machine_details(published: SimpleNamespace) -> None:
    method = json.loads((published.results / report.METHOD_FILE).read_text(encoding="utf-8"))
    assert method["runs"] == ["fake-a", "fake-b"] and method["mode"] == "full"
    assert method["neurogrid"]["version"] == f"neurogrid {_runs.NEUROGRID_VERSION}"
    assert method["neurogrid"]["call"] == report.NEUROGRID_CALL
    assert method["neurogrid"]["configuration"]["Zhou2016"]["quality"]["min_channels"] == 14
    assert method["neurogrid"]["thresholds"]["CORE-M09-01"] == 0.305083
    assert method["quality"]["boundaries"] == [0.5, 0.75, 1.0, 1.5]
    assert method["degradation"]["line_noise_db"] == [-15.0, -10.0, -5.0, 0.0, 10.0]
    assert "levels" not in method["degradation"] and "round_half_up" not in method["degradation"]
    assert method["datasets"]["Cho2017"]["flattened_channels"] == [3, 6, 13, 22, 32]
    assert method["decoders"]["eegnet_input_scale"] == 1e6
    assert method["machine"] == {
        "system": method["machine"]["system"],
        "machine": method["machine"]["machine"],
    }
    assert set(method["datasets"]) == set(_runs.DATASET_NAMES)


def test_run_compare_names_both_runs(published: SimpleNamespace) -> None:
    """DoD 1: run_compare.json is compare.write_comparison of the two runs, with their run ids."""
    document = json.loads((published.results / paths.RUN_COMPARE_FILE).read_text(encoding="utf-8"))
    assert document["runs"] == ["fake-a", "fake-b"] and document["ok"] and document["exact"]
    assert document["compared"] == dict(published.publication.comparison.compared)
    plain = compare.compare_runs(published.a, published.b)
    assert plain.runs == () and published.publication.comparison == dataclasses.replace(
        plain, runs=("fake-a", "fake-b")
    )


def test_report_has_attribution_for_every_dataset(published: SimpleNamespace) -> None:
    """NA-01 (A-36): every dataset with citation, DOI of the paper, source, download source and the licence
    at the download source, and the note that the data were degraded in memory and not redistributed."""
    notes = {"en": "does not redistribute the data", "zh": "不对这些数据进行再分发"}
    for language, text in published.texts.items():
        assert notes[language] in text, language
        data = text[text.index(HEADINGS[language][1]) : text.index(HEADINGS[language][2])]
        for spec in DATASETS.values():
            for value in (spec.citation, spec.paper_doi, spec.source, spec.download, spec.licence):
                assert value in data, (language, spec.name, value)
            assert f"**{spec.name}**" in data, (language, spec.name)


def test_report_sections_and_disclaimer(published: SimpleNamespace) -> None:
    """A-107: the sections in order in both languages, the scope statement (A-36) last; the en text exactly,
    zh its translation; the figures linked relative to the report and present."""
    for language, text in published.texts.items():
        positions = [text.find(f"\n{heading}\n") for heading in HEADINGS[language]]
        assert -1 not in positions and positions == sorted(positions), (language, positions)
        scope = text[positions[-1] :]
        assert _wording.SCOPE[language] in scope, language
        assert text.endswith("\n") and "\r" not in text
        links = re.findall(r"\]\(([^)]+\.(?:svg|png))\)", text)
        assert len(links) == 4, (language, links)
        folder = published.en.parent if language == "en" else published.zh.parent
        for link in links:
            assert not Path(link).is_absolute() and (folder / link).resolve().is_file(), link
    assert set(report.TEXTS["en"]) == set(report.TEXTS["zh"])
    assert [report.TEXTS[language][key] for language in ("en", "zh") for key in report.SECTIONS] == [
        *HEADINGS["en"],
        *HEADINGS["zh"],
    ]


def test_report_wording(published: SimpleNamespace) -> None:
    """A-57 (and ARC-05) on both reports, every text template of both languages and the notebook's text
    (Markdown cells and code comments); the lists catch what they are meant to catch."""
    for language, text in published.texts.items():
        assert not _wording.hits(text), (language, _wording.hits(text))
    for language, texts in report.TEXTS.items():
        assert not _wording.hits(json.dumps(texts, ensure_ascii=False)), language
    for text in _wording.notebook_texts(NOTEBOOK):
        assert not _wording.hits(text), (text[:80], _wording.hits(text))
    assert _wording.hits("The dataset is compliant.") and _wording.hits("数据集符合标准要求")
    assert _wording.hits("no clinical statement") and not _wording.hits("no statement about a medical device")


def test_published_files_hold_no_paths_user_or_host_names(published: SimpleNamespace) -> None:
    names = _wording.private_names(published.base, paths.REPO, paths.PROJECT)
    for path in [*(published.results / name for name in report.PUBLISHED), published.en, published.zh]:
        assert not _wording.private_hits(path.read_bytes(), names), (
            path.name,
            _wording.private_hits(path.read_bytes(), names),
        )


def test_missing_levels_are_not_invented(published: SimpleNamespace) -> None:
    """DoD 2: a level without pairs has no curve row and a dash in the report; pairs without a level are
    counted from sessions.csv."""
    curve = records.read_curve(published.results / paths.CURVE_FILE)
    zhou = {p.x for p in curve if p.dataset == "Zhou2016" and p.axis == "quality"}
    assert zhou == {4, 5}
    row = next(
        line for line in published.texts["en"].splitlines() if line.startswith("| Zhou2016 | CSP+LDA | –")
    )
    assert row.count("| – |") >= 1 and row.endswith("| 0 |")
    kalunga = [
        line for line in published.texts["en"].splitlines() if line.startswith("| Kalunga2016 | EEGNet | –")
    ]
    assert kalunga and kalunga[0].endswith("| 1 |")


def test_cho2017_line_noise_finding_follows_the_line_noise_item(
    published: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A-111: the line-noise item points to the next item, which states the finding for Cho2017 with the
    ladder's mean accuracies from curve.csv and the EEGNet pairs at the top level with and without the
    ladder from sessions.csv; without Cho2017 among the phase-locked datasets neither appears."""
    curve = records.read_curve(published.results / paths.CURVE_FILE)
    ladder = {
        (p.decoder, p.x): p.mean_accuracy
        for p in curve
        if p.dataset == "Cho2017" and p.axis == "degradation" and p.kind == "line_noise"
    }
    sessions = records.read_sessions(published.results / paths.SESSIONS_FILE)
    top = [s for s in sessions if s.dataset == "Cho2017" and s.decoder == "eegnet" and s.quality_level == 5]
    line, rest = [s for s in top if s.kind == "line_noise"], [s for s in top if s.kind != "line_noise"]
    assert line and rest
    starts = {
        "en": ("- **Band-pass filters", "- **Cho2017: the added line noise"),
        "zh": ("- **带通滤波", "- **Cho2017："),
    }
    for language, text in published.texts.items():
        t = report.TEXTS[language]
        lines = text.splitlines()
        index = next(i for i, x in enumerate(lines) if x.startswith(starts[language][0]))
        assert lines[index].endswith(t["lim_line_except"].format(name="Cho2017"))
        item = lines[index + 1]
        assert item.startswith(starts[language][1]) and "A-111" in item and "F4c" in item
        eegnet = " \N{RIGHTWARDS ARROW} ".join(report._percent(ladder["eegnet", x]) for x in (0, 5))
        assert t["named"].format(name="EEGNet", items=eegnet) in item
        assert report._percent(statistics.fmean(s.accuracy for s in rest)) in item
        assert f"{len(top)}" in item and f"{len(line)}" in item and f"{len(rest)}" in item
    monkeypatch.setattr(report, "PHASE_LOCKED_LINE_NOISE", "Nowhere2000")
    copy = published.base / "no-phase"
    shutil.copytree(published.results, copy / "results")
    en, zh = report.render(copy / "results", copy / "report" / "en", copy / "report" / "zh")
    assert "A-111" not in en.read_text(encoding="utf-8") and "A-111" not in zh.read_text(encoding="utf-8")


def test_report_is_rendered_from_the_results_folder_only(published: SimpleNamespace) -> None:
    """render reads results/ and nothing else (the run folders may be gone); a number changed in results/
    changes the report."""
    copy = published.base / "copy"
    shutil.copytree(published.results, copy / "results")
    en, zh = report.render(copy / "results", copy / "report" / "en", copy / "report" / "zh")
    assert en.read_text(encoding="utf-8") == published.texts["en"]
    assert zh.read_text(encoding="utf-8") == published.texts["zh"]
    method_path = copy / "results" / report.METHOD_FILE
    method = json.loads(method_path.read_text(encoding="utf-8"))
    method["neurogrid"]["version"] = "neurogrid 0.0.42"
    method_path.write_text(json.dumps(method), encoding="utf-8", newline="\n")
    en, _ = report.render(copy / "results", copy / "report" / "en", copy / "report" / "zh")
    assert "neurogrid 0.0.42 checked" in en.read_text(encoding="utf-8")


def test_publish_refuses_wrong_or_incomplete_runs(published: SimpleNamespace, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="exactly two"):
        report.publish([published.a], tmp_path / "results")
    broken = shutil.copytree(published.b, tmp_path / "runs" / "fake-c")
    (broken / paths.SESSIONS_FILE).unlink()
    with pytest.raises(ValueError, match="sessions.csv"):
        report.publish([broken, published.a], tmp_path / "results")
    (published.a.parent / "missing").mkdir(exist_ok=True)
    with pytest.raises(ValueError, match="run.json"):
        report.publish([published.a, published.a.parent / "missing"], tmp_path / "results")
    other = shutil.copytree(published.b, tmp_path / "runs" / "fake-d")
    (other / "folds" / "Cho2017" / "clean" / "eegnet.csv").unlink()
    with pytest.raises(ValueError, match="incomplete"):
        report.publish([published.a, other], tmp_path / "results")
    with pytest.raises(ValueError, match="missing"):
        report.render(tmp_path / "nothing", tmp_path / "en", tmp_path / "zh")


def test_command_line_exit_codes(published: SimpleNamespace, tmp_path: Path) -> None:
    """publish: 0 written and equal, 1 written but different, 2 usage error; render: 0, 1 when
    run_compare.json records different runs, 2 without results."""
    different = _runs.make_run(tmp_path / "runs", "fake-x", eegnet_offset=2)
    out = tmp_path / "results"
    assert report.main(["publish", str(published.a), str(different), "--results", str(out)]) == 1
    assert not json.loads((out / paths.RUN_COMPARE_FILE).read_text(encoding="utf-8"))["ok"]
    assert (
        report.main(
            [
                "render",
                "--results",
                str(out),
                "--report-en",
                str(tmp_path / "en"),
                "--report-zh",
                str(tmp_path / "zh"),
            ]
        )
        == 1
    )
    assert "**different**" in (tmp_path / "en" / report.REPORT_FILE).read_text(encoding="utf-8")
    assert report.main(["publish", str(published.a), str(published.b), "--results", str(out)]) == 0
    assert (
        report.main(
            [
                "render",
                "--results",
                str(out),
                "--report-en",
                str(tmp_path / "en"),
                "--report-zh",
                str(tmp_path / "zh"),
            ]
        )
        == 0
    )
    assert report.main(["publish", str(published.a)]) == 2
    assert report.main(["publish", str(published.a), str(tmp_path / "none"), "--results", str(out)]) == 2
    assert report.main(["render", "--results", str(tmp_path / "none")]) == 2
    assert report.main(["--help"]) == 0


def test_notebook_is_stored_without_outputs_and_reads_published_files() -> None:
    """NA-05: the notebook is committed without outputs (it is executed headless in the smoke step) and reads
    only files that publish writes."""
    import nbformat

    notebook = nbformat.read(NOTEBOOK, as_version=4)
    nbformat.validate(notebook)
    assert notebook.metadata["kernelspec"]["name"] == "python3"
    code = [cell for cell in notebook.cells if cell.cell_type == "code"]
    assert code and all(cell.outputs == [] and cell.execution_count is None for cell in code)
    read = set(re.findall(r'RESULTS / "([^"]+)"', "\n".join(cell.source for cell in code)))
    assert read and read <= set(report.PUBLISHED), read - set(report.PUBLISHED)
    assert "NEUROARENA_RESULTS" in code[0].source
    raw = NOTEBOOK.read_bytes()
    assert b"\r\n" not in raw and raw.endswith(b"}\n")
