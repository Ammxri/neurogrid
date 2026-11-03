# NeuroArena

Research part of NeuroGrid (NG-F17): how the accuracy of two standard decoders (CSP+LDA and EEGNet) changes
with NeuroGrid's quality level on three public MOABB datasets (Zhou2016, Cho2017, Kalunga2016), under
controlled degradation in five levels per kind (line noise, flat channels, artefacts).

The results apply only to the public datasets and decoders studied; they make no statement about the
performance or safety of a medical device.

**Status:** scaffold (P11). The interfaces are fixed; data loading, degradation, quality levels, decoders,
runner, notebook and report follow.

## Layout

- `src/neuroarena/`: the package. It never imports `neurogrid`; NeuroGrid runs as the command line of the main
  project (`uv run --project <repo> --locked neurogrid check ...`) and NeuroArena reads its `results.json`.
- `tests/`: unit tests and, marked `smoke`, short runs on synthetic data without any download.
- `notebooks/`, `report/en/`, `report/zh/`, `results/`: reserved for the notebook, the report in English and
  Chinese, figures, aggregated CSV and the comparison of two runs.
- Data, working files and runs are kept in `.local/arena/` of the repository only, never in the repository
  or a CI cache.

## Setup and checks

```bash
cd research/neuroarena
uv sync --locked --no-build          # own lock; torch from the PyTorch CPU index
uv run --no-sync pytest -m "not smoke"
uv run --no-sync ruff check . && uv run --no-sync ruff format --check .
```

The research licence gate runs from the repository root with the main project's environment:
`python tools/licenses.py --target research` and `python tools/licenses.py --target research --components
--download` (lists in `license-gate/research/`).

## License

Code: Apache-2.0. This README, the report, figures and aggregated results: CC BY 4.0 (see `REUSE.toml` of the
repository). The datasets keep their own licences; the report carries their attribution.
