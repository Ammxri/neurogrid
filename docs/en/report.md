# Reading the report {#report}

`neurogrid report` renders the report from `results.json` alone, as `report.zh.html` / `report.en.html` and,
with `--format pdf`, `report.zh.pdf` / `report.en.pdf`. Both formats hold the same content. The HTML file is
self-contained (fonts embedded, no links to files, a content security policy that loads nothing); the PDF is
A4, the cover and the summary upright, the sections 3–6 in landscape. Every PDF page carries the fixed sentence in
its footer, the page number "x / y" and a running head.

!!! note "Fixed sentence"
    Pre-check with NeuroGrid. Not a conformity assessment within the meaning of NMPA regulations.

## 1 Cover {#cover}

Dataset and version, the loaded rule packs with version, source status and SHA-256, the date (the reference
date `as_of` of the check, not the time of printing), the tool version and the manifest hash. If a placeholder
rule pack was loaded, a banner says that its rules are not based on a norm text and are not counted.

## 2 Summary {#summary}

Per phase (acquisition, processing, annotation, storage, access) a traffic light, the number of errors and
warnings (open evidence included) and the coverage measure.

| Light | Meaning |
|---|---|
| red | at least one failed error rule or open evidence for an error rule |
| yellow | the same for warning rules |
| green | no failed error rule in the loaded rule packs (and none of the cases above for warnings) |
| grey | no rule of the phase gave a passed, not passed, exception or evidence-open result |

Green means only that no rule of the loaded rule packs failed; it is no statement beyond these packs. The
coverage measure (share of the must-clauses that are checked automatically or semi-automatically) exists only
for packs that map a norm with source status `inventory` or `final`; for `core`, `bids`, `gxdsl008` and
placeholder packs it shows "n/a".

## 3 Findings by severity {#findings}

Errors, warnings and notes, each with rule ID, clause, title, status, file, channel, measured value, threshold
(with its origin: check default, rule pack or `neurogrid.toml`), time range and reason. An empty cell shows "–"
with its reason, for example when a manual rule has no measured value. Time ranges are given relative to the
start of the recording; whole-recording values say "whole recording", dataset-level values have no time range; at
most 20 ranges are listed with their number and total duration.

Statuses: passed, not passed, exception (justified), not applicable, not checkable (with reason), evidence open.
The report shows at most 50 rows per rule; a closing line names the exact number of further findings and that
the complete list is in `results.json` (`findings`, selected by `rule_id`). Passed checks are counted per rule.
Findings of placeholder packs are in a section of their own, "not evaluated".

## 4 Metrics per recording {#metrics}

A table of the metrics per recording (format, sampling rate, duration, EEG channels, passed checks and the values
of M06–M09) and small distribution charts, one value per recording (the worst channel) per metric. The sample of
M06/M09 is documented: segments in recording time, seed, channels analysed, electrode positions, filters. The
section also shows the dataset-level results: class shares and demography (withheld below 5 subjects per cell),
splits and the number of duplicate groups.

## 5 Manual evidence {#evidence}

Every rule evaluated from `evidence.yaml`, with kind, status, document, document check, reviewer, date and
comment. "Evidence filed" is the user's statement and is not assessed by NeuroGrid; NeuroGrid only checks that the
document exists, is not a link and matches its recorded hash.

## 6 Appendix {#appendix}

An overview of the loaded rules, the effective configuration (cleaned of paths that could identify a person),
the overridden thresholds, the justified exceptions with justification, approver role and validity, the notices
of the run, the environment (Python, platform, libraries) and the fixed sentence.

## Pseudonymity {#pseudonymity}

In raw folders recordings are shown under pseudonymous IDs (`rec-<8 hex digits>` or the mapping in
`neurogrid.toml`); `check --show-paths` shows real names. NeuroGrid does not pseudonymize data: IDs and file
names come from the input. The report contains no raw signals, no signal hashes, no raw ages and no values of
identifying header fields.
