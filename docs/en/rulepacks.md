# Rule packs {#rulepacks}

A rule pack is a YAML file that turns measurements into findings: each rule names a registered check, its
parameters, a phase, a severity and how it is verified. NeuroGrid ships five packs: `core`, `bids`,
`gbt47127` (the GB/T 47127 multi-modal data format), `gxdsl008` and the placeholder pack `yyt2029`
([Built-in rules](reference/rules.md), [Placeholder packs](#placeholder)); a
test institute, a manufacturer or the author of a standard can write their own pack without changing code and
load it with `--rulepack <file>` or `[check] rulepacks`.

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

This version contains no content from YY/T 2029-2026. The placeholder pack yyt2029 (one example rule without clause, loaded only with `--allow-draft-rulepacks`, never counted) is not based on the norm text either; the clause-based pack follows once the norm text has been read.

```bash
neurogrid check DATA --rulepack yyt2029 --allow-draft-rulepacks
```

Without `--allow-draft-rulepacks` the command ends with exit code 2 before any data are read, whether the pack
is named with `--rulepack`, by its file path or in `[check] rulepacks`; there is no switch in `neurogrid.toml`.
With it, the result sentence on the console names only the packs that were evaluated, and when only placeholder
packs are loaded, the console and the report say that no rule pack was evaluated (exit code 0).

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
repository; the list of interpretation questions below records each such clause.

!!! warning "Placeholder"
    The address of the public repository is `<REPO_URL>`; it is filled in when the repository is published.

<!-- BEGIN GENERATED interpretation questions -->
### Interpretation questions {#questions}

Clauses that can be read in more than one way, with the possible readings, the reading NeuroGrid implements and whom the question was put to (by role, never by name). The list is generated from `docs/_data/interpretation_questions.yaml`; it names no pack of its own, so every rule pack that maps a norm uses it.

#### IQ-001 {#IQ-001}

| | |
|---|---|
| ID | IQ-001 |
| Topic | Spelling of the modality folders |
| Rule pack | gbt47127 |
| Clause | 6.2 |
| Rules | [GBT47127-STO-007](reference/rules.md#GBT47127-STO-007) |
| Question | Clause 6.2 says the modality folders use English lower-case abbreviations, but its list writes EEG, fNIRS, MEG, fMRI, iEEG and uEphys, and the file name suffixes of 7.5.7.1 use the same mixed spelling. Which spelling is required? |
| Possible readings | (a) Only the spelling of the list (EEG, fNIRS …).; (b) Only lower case (eeg, fnirs …).; (c) Both: the spelling of the list or lower case. |
| Reading implemented | (c) The sentence and the list disagree; NeuroGrid accepts both and reports any other spelling. convert writes the spelling of the list, the same as the file name suffix. |
| Status | open |
| Asked (role, date) | – |
| Answer | – |
| Effect on the rules | no change |

#### IQ-002 {#IQ-002}

| | |
|---|---|
| ID | IQ-002 |
| Topic | Special characters in the data set name |
| Rule pack | gbt47127 |
| Clause | 7.2, Table 1 |
| Rules | [GBT47127-STO-002](reference/rules.md#GBT47127-STO-002) |
| Question | Table 1 asks the data set name to avoid special characters and spaces but does not define special characters. Which characters may a name contain? |
| Possible readings | (a) Letters, digits, '.', '_' and '-'.; (b) Letters and digits only.; (c) Any printable character except spaces. |
| Reading implemented | (a) The characters that are safe in file and folder names on every system; the rule is an info only. |
| Status | open |
| Asked (role, date) | – |
| Answer | – |
| Effect on the rules | no change |

#### IQ-003 {#IQ-003}

| | |
|---|---|
| ID | IQ-003 |
| Topic | <matches> of the event table |
| Rule pack | gbt47127 |
| Clause | 7.6 |
| Rules | [GBT47127-ANN-002](reference/rules.md#GBT47127-ANN-002), [GBT47127-STO-008](reference/rules.md#GBT47127-STO-008) |
| Question | Clause 7.6 names an event table <matches>_events.<extension>, where <matches> is the file name of the signal file. Does <matches> include the extension of the signal file? |
| Possible readings | (a) Without the extension (sub-01_task-rest_EEG_events.tsv).; (b) With the extension (sub-01_task-rest_EEG.edf_events.tsv). |
| Reading implemented | (a) The sidecar shares the name without its extension (7.5.7.2), and so do the channel and electrode tables; NeuroGrid reads both forms and reports the second as an info. |
| Status | open |
| Asked (role, date) | – |
| Answer | – |
| Effect on the rules | no change |

#### IQ-004 {#IQ-004}

| | |
|---|---|
| ID | IQ-004 |
| Topic | Structure of a key-value file in XML |
| Rule pack | gbt47127 |
| Clause | 7.1 |
| Rules | [GBT47127-STO-001](reference/rules.md#GBT47127-STO-001), [GBT47127-STO-010](reference/rules.md#GBT47127-STO-010), [GBT47127-ACQ-001](reference/rules.md#GBT47127-ACQ-001) |
| Question | Clause 7.1 allows key-value metadata in XML but gives no structure. How are fields, lists and types written in XML? |
| Possible readings | (a) One root element; each child element is a field named by its identifier; a repeated child is a list; numbers and Booleans are written as text.; (b) Fields as attributes of the root element. |
| Reading implemented | (a) The direct mapping of the JSON form; documents with a DOCTYPE or entity declaration are refused for safety. |
| Status | open |
| Asked (role, date) | – |
| Answer | – |
| Effect on the rules | no change |

#### IQ-005 {#IQ-005}

| | |
|---|---|
| ID | IQ-005 |
| Topic | Values of the optode type |
| Rule pack | gbt47127 |
| Clause | 7.5.2, Table 8 |
| Rules | [GBT47127-ACQ-003](reference/rules.md#GBT47127-ACQ-003) |
| Question | Table 8 says the optode type is a source or a detector. Which values does the column hold? |
| Possible readings | (a) The Chinese terms for source and detector or the English source and detector.; (b) Only the Chinese terms. |
| Reading implemented | (a) The identifiers of the format are English, the definitions Chinese; both forms are accepted, without regard to case. |
| Status | open |
| Asked (role, date) | – |
| Answer | – |
| Effect on the rules | no change |
<!-- END GENERATED -->
