# Commands {#commands}

`neurogrid [global options] <command> [arguments and options]`. Without arguments `neurogrid` shows the help
and ends with exit code 2. `neurogrid <command> --help` shows the help of one command in the selected language.

Paths on the command line refer to the current folder. Comma lists are accepted only by `report --lang` and
`report --format`; quote them in PowerShell (`--lang "zh,en"`) or repeat the option.

## Global options {#global}

| Option | Meaning |
|---|---|
| `--lang zh` / `--lang en` | Language of all messages, `--help` included. Without it: the environment variable `NEUROGRID_LANG`, then the system language, else English. An unknown or empty value ends with exit code 2. |
| `--debug` | On an internal error, also show a traceback without control characters, home folder or dataset paths. |
| `--help` | Show the help and exit. |

## scan {#scan}

`neurogrid scan PATH [--out FILE] [--show-paths]`

Inventory of a dataset folder or a single data file: BIDS or raw folder, formats, subjects, recordings, sizes,
unsupported and unreadable files, links that are not followed, and a hint if file names look identifying.

| Argument / option | Meaning |
|---|---|
| `PATH` | Dataset folder or single data file. |
| `--out FILE` | Also write the inventory as JSON ([Output files](reference/outputs.md#scan-json)). |
| `--show-paths` | Show real paths instead of pseudonymous IDs (raw folders). |

| Code | Meaning |
|---|---|
| 0 | inventory written |
| 2 | tool error (path not allowed, output not writable, internal error) |

## convert {#convert}

`neurogrid convert PATH --to bids --out FOLDER [--config FILE] [--strip-identifying-headers]`

Converts a raw folder to EEG-BIDS (MNE-BIDS 0.20.0) and runs the BIDS validator on the result. Required metadata
that is documented nowhere is written as `n/a` and listed; names and authors are never invented.

| Argument / option | Meaning |
|---|---|
| `PATH` | Raw data folder or single data file (a BIDS dataset as input ends with exit code 2). |
| `--to bids` | Target structure; v0.1 knows `bids`. |
| `--out FOLDER` | Output folder; must be empty or new and outside the input. |
| `--config FILE` | `neurogrid.toml` (default: `.neurogrid/neurogrid.toml` in the raw folder) with the mapping of files to subject, session, task and run. |
| `--strip-identifying-headers` | Replace identifying header fields (EDF/BDF patient field and recording field, start date, BrainVision comment) by placeholders in the copies. |

| Code | Meaning |
|---|---|
| 0 | every recording converted and the validator reports no error |
| 1 | a file was not converted or the validator reports errors |
| 2 | tool error: mapping missing (a template is written), output folder not usable, validator not runnable |

## check {#check}

`neurogrid check PATH [options]`

Checks a dataset against the loaded rule packs and writes `results.json`. The pack `core` is loaded unless
`neurogrid.toml` lists packs in `[check] rulepacks`.

| Argument / option | Meaning |
|---|---|
| `PATH` | Dataset folder or single data file. |
| `--rulepack NAME_OR_PATH` | Built-in pack (`core`, `bids`, `gxdsl008`) or a YAML file; repeatable. |
| `--config FILE` | `neurogrid.toml` (default: `.neurogrid/neurogrid.toml` in the dataset). |
| `--out FILE` | Results file (default `results.json`). |
| `--strict` | Strict mode: a missing manifest is an error (CORE-M13-01). |
| `--as-of YYYY-MM-DD` | Reference date for exceptions and dates (default: today); it is part of the result. |
| `--allow-draft-rulepacks` | Allow placeholder rule packs; their rules are shown but never counted. |
| `--show-paths` | Show real paths instead of pseudonymous IDs (raw folders). |
| `--jobs N` | Processes for the signal metrics, 1–64; the result is byte-identical to `--jobs 1`. |
| `--evidence FILE` | `evidence.yaml` (default: `.neurogrid/evidence.yaml` in the dataset). |
| `--manifest FILE` | Manifest to compare with (default: `.neurogrid/manifest.json` in the dataset). |

| Code | Meaning |
|---|---|
| 0 | no failed error rule and no open evidence for an error rule (placeholder packs do not count) |
| 1 | at least one; also an unreadable or unsupported data file, or a dataset without a readable recording |
| 2 | tool error: configuration, rule pack, validator, path not allowed, internal error |

## report {#report}

`neurogrid report RESULTS [--lang zh,en] [--format html,pdf] [--out FOLDER]`

Renders the report from `results.json` alone, per language and format: `report.<lang>.html` and
`report.<lang>.pdf` ([Reading the report](report.md)). The command prints the fixed sentence at the end.

| Argument / option | Meaning |
|---|---|
| `RESULTS_FILE` | `results.json` written by `check`. |
| `--lang` | Report languages `zh`, `en` (default `zh,en`). |
| `--format` | `html`, `pdf` (default `html`); PDF needs the [PDF browser](installation.md#pdf-browser). |
| `--out FOLDER` | Output folder (default: the folder of `results.json`). |

| Code | Meaning |
|---|---|
| 0 | every requested report written |
| 2 | tool error: unreadable results, unknown language or format, PDF browser or Linux libraries missing (then nothing is written) |

## manifest {#manifest}

`neurogrid manifest PATH [--out FILE] [--show-paths]`

Writes the provenance manifest: SHA-256 and size of every file, the processing steps and the software versions
(M13). Links and special files are listed, never followed.

| Argument / option | Meaning |
|---|---|
| `PATH` | Dataset folder. |
| `--out FILE` | Manifest file (default: `.neurogrid/manifest.json` in the dataset). |
| `--show-paths` | Show real paths instead of pseudonymous IDs (raw folders). |

| Code | Meaning |
|---|---|
| 0 | manifest written |
| 1 | files could not be read, or the dataset has more entries than a manifest lists; nothing written |
| 2 | tool error (for example invalid `.neurogrid/processing_steps.json`) |

## verify {#verify}

`neurogrid verify PATH --manifest FILE [--show-paths]`

Compares a dataset with its manifest: changed, new and missing files, links or special files that changed, and
files that cannot be read.

| Argument / option | Meaning |
|---|---|
| `PATH` | Dataset folder. |
| `--manifest FILE` | `manifest.json` written by `manifest` (required). |
| `--show-paths` | Show real paths instead of pseudonymous IDs (raw folders). |

| Code | Meaning |
|---|---|
| 0 | the dataset matches the manifest |
| 1 | at least one deviation |
| 2 | tool error: the manifest is invalid |

## Exit codes in general {#exit-codes}

- **0** – no failed error rule and no open evidence for an error rule; warnings alone never change it.
- **1** – findings: a failed error rule, open evidence for an error rule, an unreadable or unsupported data
  file, no readable recording; for `verify` a deviation, for `convert` a file not converted.
- **2** – tool errors only: configuration, rule pack, validator, PDF browser, path not allowed, internal error,
  an explicitly given single file of unknown format. Data in the dataset never cause exit code 2.
