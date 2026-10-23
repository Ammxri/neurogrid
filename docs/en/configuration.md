# Configuration {#configuration}

A dataset is described by `neurogrid.toml`. Its default location is `.neurogrid/neurogrid.toml` inside the
dataset; `--config` names another file. The file is read as UTF-8 (with or without byte order mark) and
validated strictly: an unknown key, a wrong type or an invalid value ends the run with exit code 2 and names the
field.

**Project root.** Paths inside the file are relative to the project root: for a file in a `.neurogrid` folder
the folder above it, for another file inside the dataset the dataset root, otherwise the folder of the file.
Paths must be plain relative paths (no `..`, no drive, network or device path). Links are never followed.

**Precedence.** Metadata: `neurogrid.toml` > BIDS sidecars > file header > not documented (a finding, no stop).
Thresholds: `neurogrid.toml` (`[rules."ID".params]`) > rule pack > default of the check. Every finding names the
effective threshold and where it came from.

## [dataset] {#dataset}

`id`, `name`, `version`, `source`, `license`: the dataset fields of the report and of `results.json` when
`dataset_description.json` does not provide them. Without `id` the dataset is shown as "unnamed"; the folder
name is never used, it could be identifying.

## [check] {#check}

| Key | Meaning |
|---|---|
| `rulepacks` | Rule packs to load (names or relative paths); replaces the default `core`, so list `core` as well. `--rulepack` adds more. An empty list is invalid. |
| `strict` | Strict mode like `--strict` (default `false`). |
| `seed` | Seed of the sampled metrics (default 20261011, 0 to 2^63−1). |
| `as_of` | Reference date `YYYY-MM-DD` (default: today); `--as-of` wins. |

## [sampling] {#sampling}

M06 and M09 run on a sample: `mode = "sample"` takes `segments` (default 10) segments of `segment_s` (default
60) seconds in the middle of equal parts; recordings up to 10 minutes are used whole. `mode = "full"` uses the
whole recording ([Metrics](metrics.md#M06)).

## [quality] {#quality}

| Key | Default | Meaning |
|---|---|---|
| `flat_tolerance_uv` | 0.1 | Peak-to-peak below this value (µV) counts as flat in floating-point formats (M08). |
| `plateau_samples` | 10 | Equal samples at the extreme that count as clipping where the range is unknown (M08). |
| `min_seconds` | 60 | Data needed for M06/M09. |
| `min_channels` | 16 | EEG channels needed for M06/M09. |

## [rules."ID".params] {#rules}

Overrides the parameters of one rule, addressed by its ID, for example `[rules."CORE-M07-01".params]` with
`max_ratio = 0.35`. Only the parameters the check declares are accepted ([Check registry](reference/checks.md)).

## [[exceptions]] {#exceptions}

A justified exception removes matching findings from the exit code and the traffic light; they stay visible in
the report appendix.

| Key | Meaning |
|---|---|
| `rule` | Rule ID (required). |
| `object` | Pattern over the object: relative POSIX path or pseudonymous ID; `**` any number of segments, `*` one segment, case-sensitive. |
| `subkey` | Sub-key, for example a field name, a channel or a validator code. |
| `reason` | Justification (required, not empty; missing → exit code 2). |
| `approved_by` | A role or initials, never a full name. |
| `valid_until` | Last day of validity; after `as_of` the exception no longer applies and a warning says so. |

## [metadata] {#metadata}

| Key | Meaning |
|---|---|
| `defaults.electrode_type` | `wet` or `dry`; only here. Without it the impedance threshold is not checkable; for `dry` it is not applicable. |
| `defaults.line_frequency_hz` | Line frequency of the recordings (M07 otherwise uses 50 Hz). |
| `defaults.device` | Device name. |
| `defaults.reference` | EEG reference (EEG-BIDS `EEGReference`). |
| `defaults.software_filters` | Software filters (EEG-BIDS `SoftwareFilters`, `n/a` is valid). |
| `mixed_sampling_rates_reason` | Justification for recordings with different sampling rates (M03). |
| `channel_map` | Channel label → standard position name for labels that differ from 10-20/10-10/10-05 (M04). |

## [convert] {#convert}

Mapping of raw files to subject, session, task and run for `convert` (and subjects for `scan`):

- `pattern`: a regular expression with the named groups `subject` and `task` (required) and `session`, `run`
  (optional), matched against the relative path or the file name. Labels must be letters and digits, `run` a
  number. Expressions with back-references or nested repetitions are refused (exit code 2).
- `[[convert.files]]` with `path`, `subject`, `session`, `task`, `run`: a table, which wins over the pattern.

## [annotation] {#annotation}

| Key | Meaning |
|---|---|
| `mode` | `events` (default) or `continuous` (sleep stages and other gap-free scoring). |
| `epoch_s` | Grid of κ; default 30 s continuous, 1 s events. |
| `vocabulary` | Allowed codes (exact match); without it the `Levels` of `events.json` apply. |
| `annotators` | Patterns (`*`, `?`) over annotator IDs that take part. |
| `files` | `[[annotation.files]]` with `path`, `recording` and optional `annotator`: annotation-only files (for example hypnograms) and the recording they belong to. |

## [ai] {#ai}

| Key | Meaning |
|---|---|
| `labels` | Source of the class labels of M11: `events:<column>`, `participants:<column>` or `annotations`. Without it CORE-M11-01 is not applicable. |
| `splits` | Split file (columns `recording`, `split` with train, val, test); default `.neurogrid/splits.tsv`, else a column `split` in `participants.tsv`. |

## [consent] and [vault] {#consent-vault}

Both sections are accepted and validated; they are evaluated from version 0.2 on (NeuroVault). Already in 0.1,
`[vault] path` (default `.neurogrid/vault`) keeps the vault's access log out of the manifest. Keys: `[consent]`
`split_use`, `dataset_uses`; `[vault]` `path`, `role`, `purpose`, `approval_ref`.

## Example {#example}

<!-- example: neurogrid.toml -->
```toml
[dataset]
id = "example-eeg"
name = "Example EEG study"
license = "CC0"

[check]
rulepacks = ["core", "bids", "gxdsl008"]
strict = false
as_of = 2026-11-20

[sampling]
mode = "sample"
segments = 10
segment_s = 60

[rules."CORE-M07-01".params]
max_ratio = 0.35

[[exceptions]]
rule = "CORE-M04-01"
object = "sub-07/**"
subkey = "X1"
reason = "Electrode 'X1' is a documented auxiliary sensor (SOP-12)."
approved_by = "QA lead"
valid_until = 2027-06-30

[metadata.defaults]
electrode_type = "wet"
line_frequency_hz = 50
device = "ExampleAmp 64"
reference = "Cz"

[annotation]
mode = "continuous"
epoch_s = 30
vocabulary = ["W", "N1", "N2", "N3", "R"]

[ai]
labels = "events:trial_type"
splits = ".neurogrid/splits.tsv"
```

## Further files in .neurogrid/ {#files}

| File | Content |
|---|---|
| `evidence.yaml` | Evidence for manual and semi-automatic rules: `format_version: 1`, `evidence: {rule ID: {status, document, sha256, reviewer, date, comment, justification}}`; status `open`, `provided`, `partial` or `not_applicable` (justification required). NeuroGrid computes the SHA-256 of each document and compares it with a recorded one. |
| `splits.tsv` | Columns `recording` (relative path or pseudonymous ID) and `split` (train, val, test). |
| `provenance.yaml` | `processing_steps` and `software` (CORE-M13-03); `processing_steps: []` documents "no processing". |
| `manifest.json` | Written by `manifest` ([Output files](reference/outputs.md#manifest)). |
