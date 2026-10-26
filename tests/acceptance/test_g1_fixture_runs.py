"""The G1 path end to end on fixtures (NG-F13, NG-F14, NG-N03, NG-N05, REP-00): tools/acceptance_g1.py runs
scan, check (core + bids + gxdsl008, --jobs 4), report (zh + en, HTML + PDF), manifest and verify as real
processes of the ``neurogrid`` entry script, once with English and once with Chinese console messages, and
its checks find nothing; both runs are byte-identical and the data set is untouched. A leak or a change
planted afterwards is found. The same code runs on the corpus (test_g1_corpus.py). Marker ``pdf``."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

import acceptance_g1 as g1  # type: ignore[import-not-found]

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"
FIXTURES = ("edf_identifying", "bids_issues")


def _problems(evaluation: g1.DatasetEval) -> dict[str, list[str]]:
    return {category: items for category, items in evaluation.problems.items() if items}


@pytest.fixture(scope="module", params=FIXTURES)
def two_runs(
    request: pytest.FixtureRequest, pdf_shell: object, tmp_path_factory: pytest.TempPathFactory
) -> tuple[Path, Path, list[g1.DatasetEval]]:
    """Both runs of one fixture: (data set, output folder, the evaluation of each run)."""
    dataset = FIX / request.param
    before = g1.tree_state(dataset)
    out = tmp_path_factory.mktemp(f"g1-{request.param}")
    evaluations = []
    for number, lang in enumerate(g1.CONSOLE_LANGS, start=1):
        folder = out / f"run{number}" / dataset.name
        runs = g1.run_dataset(dataset, folder, lang=lang)
        assert list(runs) == list(g1.COMMANDS)
        evaluations.append(g1.evaluate_run(dataset, folder, runs, lang, out))
    assert g1.tree_state(dataset) == before  # nothing written into the data set
    return dataset, out, evaluations


@pytest.mark.pdf
def test_every_check_passes_on_the_products_outputs(
    two_runs: tuple[Path, Path, list[g1.DatasetEval]],
) -> None:
    dataset, out, evaluations = two_runs
    for evaluation in evaluations:
        assert _problems(evaluation) == {}
    stats = evaluations[0].stats
    assert stats["packs"] == ["core", "bids", "gxdsl008"]
    assert stats["rows_checked"]["zh"] == stats["rows_checked"]["en"] > 0
    assert stats["pdf_pages"]["zh"] > 0 and stats["pdf_pages"]["en"] > 0
    assert stats["forbidden_checked"] > 0
    first, second = out / "run1" / dataset.name, out / "run2" / dataset.name
    assert g1.compare_runs(first, second) == dict.fromkeys(g1.PRODUCT_FILES, True)  # NG-N03


@pytest.mark.pdf
def test_planted_header_values_are_searched(two_runs: tuple[Path, Path, list[g1.DatasetEval]]) -> None:
    """NG-N05: the identifying EDF header of edf_identifying is among the searched values, and the reports
    really are searched: the name written into a copy of the HTML report is found."""
    dataset, out, _evaluations = two_runs
    if dataset.name != "edf_identifying":
        pytest.skip("the planted header belongs to edf_identifying")
    forbidden = g1.forbidden_values(dataset, out)
    assert g1.Forbidden("EDF/BDF header value", "Zhang San 01-JAN-1980", "literal") in forbidden
    assert g1.Forbidden("recording date", "2021-08-24", "literal") in forbidden
    leaked = out / "leak" / dataset.name
    shutil.copytree(out / "run1" / dataset.name, leaked)
    html = leaked / "report.en.html"
    document = html.read_text(encoding="utf-8")
    assert document.count("</body>") == 1
    html.write_text(document.replace("</body>", "<p>Zhang San 01-JAN-1980</p></body>"), encoding="utf-8")
    runs = {name: g1.CommandRun(name, 0, b"", b"", 0.0) for name in ("report",)}
    runs["check"] = g1.CommandRun("check", 1, b"", b"", 0.0)
    evaluation = g1.evaluate_run(dataset, leaked, runs, "en", out)
    assert "report.en.html: contains a EDF/BDF header value" in evaluation.problems["privacy"]
    assert not g1.compare_runs(out / "run1" / dataset.name, leaked)["report.en.html"]
