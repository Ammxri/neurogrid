# NeuroGrid

> **Pre-check with NeuroGrid. Not a conformity assessment within the meaning of NMPA regulations.**
> **使用 NeuroGrid 进行的预检。不构成国家药品监督管理局（NMPA）法规意义上的符合性评价。**

NeuroGrid is an open, local and offline tool that checks EEG datasets for AI-based brain–computer
interface (BCI) devices, converts them to EEG-BIDS and writes a report in Chinese and English.
It reports whether a dataset *passes the checks of the loaded rule packs*.
NeuroGrid itself performs no conformity assessment: conformity is assessed by test institutes and the NMPA.
NeuroGrid makes no statement about patients.

NeuroGrid 是一个开源、本地、离线运行的工具，用于检查面向人工智能脑机接口产品的脑电数据集，
将其转换为 EEG-BIDS，并生成中英文报告。它只说明数据集是否通过已加载规则包的各项检查。

**Status:** under development (v0.1 in progress). Not yet released.

## Usage (development version)

```bash
uv sync --locked --no-build
uv run neurogrid scan path/to/dataset
uv run neurogrid check path/to/dataset --out results.json
uv run neurogrid report results.json --lang zh,en --format html
```

In PowerShell, quote comma lists: `--lang "zh,en"` (or repeat the option: `--lang zh --lang en`).

Exit codes of `check`: `0` no failed error rule, `1` at least one, `2` tool error.

NeuroGrid never sends data anywhere; it works fully offline.

## Documentation

User documentation in Chinese and English: `docs/zh/` and `docs/en/` (installation, quick start, commands,
configuration, rule packs, metrics, reading the report, privacy, limitations). The website is built offline with
`uv run python tools/build_docs.py --site-dir site`; the offline bundle carries it in `docs/`.

## License

Code: Apache-2.0 (see `LICENSE`, `NOTICE`). Documentation and sample data: CC BY 4.0. Report fonts: SIL Open
Font License 1.1. The licence of every file is listed in `REUSE.toml`, the texts are in `LICENSES/`; third-party
components are listed in `THIRD_PARTY_NOTICES.txt`.
