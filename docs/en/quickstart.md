# Quick start {#quickstart}

Four commands lead from a folder of raw EEG files to the report. The examples call `neurogrid`; in an offline
installation use the full path of the launcher ([Installation](installation.md#install)).

## 1. Inventory: `scan` {#scan}

```bash
neurogrid scan raw/
```

`scan` lists formats, subjects, recordings, sizes and files NeuroGrid cannot read. It changes nothing.

## 2. Conversion to EEG-BIDS: `convert` {#convert}

A raw folder needs a mapping of each file to subject, task and (optionally) session and run. Write it into
`raw/.neurogrid/neurogrid.toml`, for example as a pattern over the file names:

```toml
[convert]
pattern = '(?P<subject>[A-Za-z0-9]+)_(?P<task>rest|task)\.edf'

[metadata.defaults]
reference = "Cz"
line_frequency_hz = 50
```

```bash
neurogrid convert raw/ --to bids --out bids/
```

Without a mapping, `convert` writes the template `raw/.neurogrid/mapping-template.toml` with one row per
file and ends with exit code 2; copy the rows into `neurogrid.toml` and fill in the labels.
The output folder must be empty or new. The BIDS validator checks the result offline.

## 3. Check: `check` {#check}

```bash
neurogrid check bids/ --rulepack bids --rulepack gxdsl008 --out results.json
```

The pack `core` is always loaded unless `neurogrid.toml` lists other packs. The console names the result, the
number of errors and warnings, and the fixed sentence. `results.json` holds every finding.

## 4. Report: `report` {#report}

=== "Bash"

    ```bash
    neurogrid report results.json --lang zh,en --format html,pdf
    ```

=== "PowerShell"

    ```powershell
    neurogrid report results.json --lang "zh,en" --format "html,pdf"
    ```

PowerShell splits unquoted commas into separate arguments: quote the list, or repeat the option
(`--lang zh --lang en`). The reports are written next to `results.json` as `report.zh.html`, `report.en.html`,
`report.zh.pdf` and `report.en.pdf` ([Reading the report](report.md)). PDF needs the
[PDF browser](installation.md#pdf-browser).

## Exit codes {#exit-codes}

| Code | Meaning |
|---|---|
| 0 | no failed error rule and no open evidence for an error rule in the loaded rule packs |
| 1 | at least one of them; also an unreadable or unsupported data file, or no readable recording |
| 2 | tool error: configuration, rule pack, validator, PDF browser, path not allowed, internal error |

Data problems are findings (exit code 1), never tool errors. Details per command: [Commands](commands.md).

## Messages in Chinese {#language}

```bash
neurogrid --lang zh check bids/
```

`--lang` before the command, or the environment variable `NEUROGRID_LANG`, selects zh or en for every message,
including `--help` and errors on the command line.
