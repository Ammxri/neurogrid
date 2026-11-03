"""Smoke step of area D (F11 B, marker smoke; NA-05, DoD 2): the smoke runs shared with area C (conftest
``smoke_runs``) published, rendered in en and zh, and the notebook executed headless with nbclient on the
``python3`` kernel of the research environment, reading the published folder through NEUROARENA_RESULTS."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import _wording
from _smoke import SMOKE_CONFIG, SmokeRuns
from neuroarena import paths, records, report

pytestmark = pytest.mark.smoke

NOTEBOOK = paths.NOTEBOOKS / "neuroarena.ipynb"


@pytest.fixture(scope="module")
def smoke_published(smoke_runs: SmokeRuns, tmp_path_factory: pytest.TempPathFactory) -> SimpleNamespace:
    base = tmp_path_factory.mktemp("smoke-report")
    results = base / "results"
    publication = report.publish([smoke_runs.first, smoke_runs.second], results)
    en, zh = report.render(results, base / "report" / "en", base / "report" / "zh")
    return SimpleNamespace(base=base, results=results, publication=publication, en=en, zh=zh)


def test_curve_data_has_both_decoders_every_dataset(smoke_published: SimpleNamespace) -> None:
    """DoD 2 on the published curve: for every dataset of the run, both decoders on the degradation axis at
    every degradation level of the run (clean at 0) and on the quality axis, unless sessions.csv shows that no
    pair of that dataset and decoder has a level (then the report counts them, nothing is invented)."""
    method = json.loads((smoke_published.results / report.METHOD_FILE).read_text(encoding="utf-8"))
    curve = records.read_curve(smoke_published.results / paths.CURVE_FILE)
    sessions = records.read_sessions(smoke_published.results / paths.SESSIONS_FILE)
    assert method["config"]["datasets"] == list(SMOKE_CONFIG.datasets)
    assert smoke_published.publication.comparison.ok and smoke_published.publication.comparison.exact
    for dataset in method["config"]["datasets"]:
        for decoder in method["config"]["decoders"]:
            assert {
                p.x for p in curve if (p.dataset, p.decoder, p.axis) == (dataset, decoder, "degradation")
            } == {
                0,
                5,
            }, (dataset, decoder)
            quality = [p for p in curve if (p.dataset, p.decoder, p.axis) == (dataset, decoder, "quality")]
            pairs = [s for s in sessions if (s.dataset, s.decoder) == (dataset, decoder)]
            with_level = [s for s in pairs if s.quality_level is not None]
            assert sum(p.n_sessions for p in quality) == len(with_level), (dataset, decoder)
            assert quality or not with_level, (dataset, decoder)
            assert all(p.n_without_level == len(pairs) - len(with_level) for p in quality)


def test_smoke_publication_is_byte_stable(smoke_runs: SmokeRuns, smoke_published: SimpleNamespace) -> None:
    again = smoke_published.base / "again"
    report.publish([smoke_runs.first, smoke_runs.second], again)
    for name in report.PUBLISHED:
        assert (again / name).read_bytes() == (smoke_published.results / name).read_bytes(), name


def test_smoke_report_sections_wording_and_paths(smoke_published: SimpleNamespace) -> None:
    """NA-05 on the report of a real smoke run: the mode is stated, the sections and the scope statement are
    there, no word of the lists and no path, user or host name in any published file."""
    names = _wording.private_names(smoke_published.base, paths.REPO, paths.PROJECT)
    banners = {"en": "**Mode smoke:**", "zh": "**smoke 模式：**"}
    for language, path in (("en", smoke_published.en), ("zh", smoke_published.zh)):
        text = path.read_text(encoding="utf-8")
        assert banners[language] in text and _wording.SCOPE[language] in text, language
        headings = [report.TEXTS[language][key] for key in report.SECTIONS]
        positions = [text.find(f"\n{heading}\n") for heading in headings]
        assert -1 not in positions and positions == sorted(positions), language
        assert not _wording.hits(text), (language, _wording.hits(text))
    for path in [
        *(smoke_published.results / name for name in report.PUBLISHED),
        smoke_published.en,
        smoke_published.zh,
    ]:
        found = _wording.private_hits(path.read_bytes(), names)
        assert not found, (path.name, found)


def test_notebook_runs_headless_smoke(
    smoke_published: SimpleNamespace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NA-05: the stored notebook runs without a user interface (nbclient, kernel python3 of the research
    environment) on the published smoke results and shows the tables and both figures. Jupyter's and IPython's
    own files go to tmp_path, not to the home folder."""
    import nbformat
    from nbclient import NotebookClient

    monkeypatch.setenv("NEUROARENA_RESULTS", str(smoke_published.results))
    monkeypatch.setenv("JUPYTER_RUNTIME_DIR", str(tmp_path / "jupyter-runtime"))
    monkeypatch.setenv("IPYTHONDIR", str(tmp_path / "ipython"))
    notebook = nbformat.read(NOTEBOOK, as_version=4)
    client = NotebookClient(
        notebook, timeout=600, kernel_name="python3", resources={"metadata": {"path": str(NOTEBOOK.parent)}}
    )
    client.execute()
    outputs = [output for cell in notebook.cells if cell.cell_type == "code" for output in cell.outputs]
    assert not [o for o in outputs if o.output_type == "error"]
    svgs = [o for o in outputs if "image/svg+xml" in o.get("data", {})]
    assert len(svgs) == 2
    text = "\n".join(str(o.get("text", "")) + str(o.get("data", {}).get("text/plain", "")) for o in outputs)
    for expected in ("csp_lda", "eegnet", *SMOKE_CONFIG.datasets, "smoke"):
        assert expected in text, expected
    stored = nbformat.read(NOTEBOOK, as_version=4)
    assert all(
        cell.get("outputs", []) == [] for cell in stored.cells
    )  # the stored file stays without outputs
