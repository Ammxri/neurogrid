# Rule packs {#rulepacks}

A rule pack is a YAML file that turns measurements into findings: each rule names a registered check, its
parameters, a phase, a severity and how it is verified. NeuroGrid ships `core`, `bids` and `gxdsl008`
([Built-in rules](reference/rules.md)); a test institute, a manufacturer or the author of a standard can write
their own pack without changing code and load it with `--rulepack <file>` or `[check] rulepacks`.

## Format {#format}

| Key | Meaning |
|---|---|
| `rulepack` | Name of the pack (lower case letters, digits, `_`). Two packs with the same name are an error. |
| `version` | Version of the pack; it appears in `results.json` and in the report next to the SHA-256 of the file. |
| `source` | What the rules are based on (for example a standard and its edition). |
| `source_status` | `final`, `inventory`, `secondary` (values second-hand) or `placeholder` (not based on a norm text). |
| `norm` | `true` if the pack maps a norm: only such packs with `inventory` or `final` get a coverage measure. Default `false`. |
| `rules` | List of rules (at least one). |

Each rule:

| Key | Meaning |
|---|---|
| `id` | Rule ID `PACK-PHASE-NNN`, phase ACQ, PROC, ANN, STO or ACC (e.g. `LABSOP-ACQ-001`). The `core` pack uses `CORE-Mxx-NN` on purpose: its clause is the metric. |
| `clause` | Clause or section of the source; `TBD` while it is not known. |
| `title_zh`, `title_en` | Own short titles; never quote a norm text. |
| `phase` | `acquisition`, `processing`, `annotation`, `storage` or `access`. |
| `check` | A check of the [check registry](reference/checks.md); unknown checks end with exit code 2. |
| `params` | Parameters the check declares, e.g. `{min_hz: 500}`; others are an error. |
| `severity` | `error`, `warning` or `info`. |
| `strict_severity` | Optional severity in strict mode (`--strict`). |
| `verification` | `automatic`, `semi_automatic` or `manual`. Manual rules use the check `evidence.document`. |

The schema of the format is published as [`rulepack.schema.json`](../schemas/rulepack.schema.json). The packs
are read with a safe YAML loader (no aliases, no duplicate keys, size limits) as UTF-8.

## From a norm to rules {#mapping}

The recommended mapping follows the language of Chinese standards: a clause with 应 or 不应 (shall, shall not)
becomes a rule with severity `error`, one with 宜 (should) a `warning`, one with 可 (may) an `info`. Every rule is
assigned to one of the five phases and classified as `automatic` (measurable from data or metadata),
`semi_automatic` (a configuration or a document can be checked) or `manual` (needs an evidence document).

Rule packs contain clause numbers and own short descriptions only, never the wording, tables or figures of a
norm.

## Manual rules and evidence {#evidence}

A manual rule is evaluated from `.neurogrid/evidence.yaml` (or `--evidence`). Without an entry its status is
"evidence open" and it counts with its severity. "Provided" means: evidence filed – the user's statement, not
assessed by NeuroGrid; NeuroGrid only checks that the named document exists, is not a link and matches its
recorded hash. A semi-automatic rule fails when the document is missing or has changed.

## Placeholder packs {#placeholder}

A pack with `source_status: placeholder` loads only with `--allow-draft-rulepacks`. Its findings appear in a
separate report section "not evaluated", with the clause marked as a placeholder, and never count for the exit
code, the traffic light or the coverage.

Version 0.1 contains no content from YY/T 2029-2026. A yyt2029 rule pack follows once the norm text has been read.

## Example {#example}

The following pack is executed by NeuroGrid's tests exactly as printed here: on the synthetic fixture `edf_ok`
with `tests/fixtures/documented.toml` the check ends with exit code 0, and the three rule IDs appear in
`results.json`. The manual rule has no evidence, so its status is "evidence open"; as a warning it does not
change the exit code.

<!-- example: rulepack -->
```yaml
rulepack: lab_sop
version: "1.0.0"
source: "SOP EEG-07 of an example laboratory"
source_status: final
rules:
  - id: LABSOP-ACQ-001
    clause: "4.2"
    title_zh: 采样率不低于 250 Hz
    title_en: Sampling rate at least 250 Hz
    phase: acquisition
    check: signal.sampling_rate_min
    params: {min_hz: 250}
    severity: error
    verification: automatic
  - id: LABSOP-ACQ-002
    clause: "4.3"
    title_zh: 每个通道的平直段不超过 1%
    title_en: Flat segments at most 1 % per channel
    phase: acquisition
    check: quality.flatline
    params: {max_fraction: 0.01}
    severity: warning
    verification: automatic
  - id: LABSOP-ACC-001
    clause: "7.1"
    title_zh: 访问权限已记录
    title_en: Access rights documented
    phase: access
    check: evidence.document
    severity: warning
    verification: manual
```

```bash
neurogrid check tests/fixtures/synthetic/edf_ok --config tests/fixtures/documented.toml \
  --rulepack lab_sop.yaml --as-of 2026-10-11
```

## Feedback on clause interpretations {#feedback}

When a clause can be read in more than one way, NeuroGrid records the reading in the decision log and in the
rule's title or parameters. Questions and proposals for another reading go to the issue tracker of the public
repository; the list of interpretation questions follows in version 0.2 with the yyt2029 pack.

!!! warning "Placeholder"
    The address of the public repository is `<REPO_URL>`; it is filled in when the repository is published.
