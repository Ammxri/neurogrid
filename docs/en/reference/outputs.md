# Output files {#outputs}

All files NeuroGrid writes are UTF-8 with LF line ends. JSON files are canonical: sorted keys, fixed number
format, no time of day, no computer or user name, no absolute path. Two runs with the same data, configuration
(including `as_of`), rule pack versions and environment give byte-identical files.

## results.json {#results-json}

Written by `check` (`--out`, default `results.json`); `report` reads only this file. JSON schema:
[`results.schema.json`](../../schemas/results.schema.json).

| Field | Content |
|---|---|
| `schema_version` | Version of the format. |
| `disclaimer` | The fixed sentence in zh and en. |
| `tool` | Name and version of NeuroGrid. |
| `environment` | Python, platform, the computing libraries with versions, BLAS threads. |
| `dataset` | The dataset fields, without paths. |
| `rulepacks` | Loaded packs: name, version, source, source status, norm, SHA-256 of the file. |
| `rules` | Every loaded rule with clause, titles, phase, check, effective severity, strict severity, verification. |
| `config` | Hash of the canonical configuration, `as_of`, seed, strict mode, sampling, effective thresholds and settings (cleaned), hash of `evidence.yaml`, hash of the consent records (`consents_sha256`). |
| `recordings` | Per recording: pseudonymous ID, format, readable in blocks, metrics and the sample of M06/M09. |
| `findings` | Every finding that is not passed, one per rule × object × sub-key, with its stable key. |
| `passed` | Passed checks, counted per rule and object. |
| `notices` | Notices of the run (level, message key, parameters). |
| `evidence` | Evidence records from `evidence.yaml` with the computed and the recorded SHA-256. |
| `exceptions` | The configured exceptions and whether they were used. |
| `duplicates` | Groups of recordings with the same signal (pseudonymous IDs), or `null`. |
| `ai` | Aggregated label, demography and split counts (withheld below 5 subjects per cell), or `null`. |
| `summary` | Per phase light, errors, warnings, open evidence; coverage per pack; totals and the exit code. |
| `manifest` | Result of the manifest comparison, or `null`. |

Not contained: time of day, computer or user name, absolute paths, signal hashes, raw ages.

## Scan JSON {#scan-json}

Written by `scan --out` (schema [`scan.schema.json`](../../schemas/scan.schema.json)): `schema_version`,
`disclaimer`, `tool`, `is_bids`, `formats`, `subjects`, `recordings`, `unsupported`, `orphans`, `unreadable`,
`other_files`, `links_skipped`, `total_bytes`, `suspicious_names` (a count, never names).

## Reports {#reports}

`report.<lang>.html` and `report.<lang>.pdf` per language `zh`, `en` in the folder `--out` (default: next to
`results.json`), see [Reading the report](../report.md).

## manifest.json {#manifest}

Written by `manifest` (default `.neurogrid/manifest.json`; schema
[`manifest.schema.json`](../../schemas/manifest.schema.json)): `format_version`, `files` (path, SHA-256, size),
`skipped` (links, special files, names the path check refuses), `excluded` (the vault log), `processing_steps`,
`software`, `manifest_hash` (over the canonical JSON bytes).

## consents.yaml and consents.tsv {#consents}

`consents.yaml` in the vault holds the consent records (schema
[`consents.schema.json`](../../schemas/consents.schema.json)); `neurogrid vault init` creates it empty, and
`neurogrid vault consent add` rewrites it in a canonical form (records sorted by subject and version, comments
added by hand are not kept):

<!-- example: consents.yaml -->
```yaml
format_version: 1
consents:
  - subject: sub-01
    version: 1
    date: 2026-03-01
    permitted_uses: [training, validation]
    withdrawn: false
    ethics_approval_ref: "EC-2026-17"
```

| Field | Content |
|---|---|
| `subject` | Pseudonymous subject: `sub-<label>`, the label made of letters and digits (at most 64); given with or without `sub-`. |
| `version` | Whole number 1 to 1000000; a higher version replaces a lower one, the dates must not decrease with the version. |
| `date` | Date of the consent or the withdrawal, `YYYY-MM-DD`. |
| `permitted_uses` | Subset of `training`, `validation`, `publication`, `sharing`, `commercial`; empty only with `withdrawn: true`. |
| `withdrawn` | `true` for a full withdrawal from `date` on (default `false`). |
| `ethics_approval_ref` | Optional reference of the ethics approval, 1 to 120 printable characters; never a name. |

At most 20 000 records and 4 000 000 bytes. An invalid file ends `check` and `vault consent add` with exit code 2
and names the record and the field, never a value. `consents.yaml` is part of the manifest, so `verify` reports a
change made outside NeuroGrid.

`consents.tsv` is the import table of `vault consent add --from`: UTF-8 (with or without BOM), tab-separated, a
header row (names without regard to case) with `subject`, `version`, `date`, `permitted_uses` (or `uses`,
comma-separated in the cell) and optionally `withdrawn` (`true`/`false`, `yes`/`no`, `1`/`0`, empty = false) and
`ethics_approval_ref` (or `ethics_ref`). At most 10 000 000 bytes and 20 000 rows; errors name the line and the
column, never the content of a cell.

`config.consents_sha256` in `results.json` is the SHA-256 of the canonical parsed records (the same for every
spelling of the same records), `null` without `consents.yaml` or without M14; the records themselves never reach
`results.json`.

## Further schemas {#schemas}

[`config.schema.json`](../../schemas/config.schema.json) (`neurogrid.toml`),
[`rulepack.schema.json`](../../schemas/rulepack.schema.json) and
[`evidence.schema.json`](../../schemas/evidence.schema.json) (`evidence.yaml`),
[`consents.schema.json`](../../schemas/consents.schema.json) (`consents.yaml`).

## Exit codes {#exit-codes}

| Code | Meaning |
|---|---|
| 0 | no failed error rule and no open evidence for an error rule |
| 1 | findings, or a deviation (`verify`), or files not converted (`convert`) |
| 2 | tool error |

Details per command: [Commands](../commands.md).
