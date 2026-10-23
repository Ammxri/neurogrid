# Metrics {#metrics}

The rule pack `core` evaluates the metrics M01–M13; this page is its source (the clause of a core rule is the
metric). For each metric it says what is measured, how, on which object, when a value cannot be judged, which
rules use it with which threshold and where that threshold comes from. Every threshold can be overridden in
`neurogrid.toml` (`[rules."ID".params]`).

**States.** A value that cannot be judged is *not checkable* with a reason (for example too little data); a rule
that does not apply to the recording is *not applicable*. Neither is a tool error: data never cause exit code 2.

**Origins.** *Start value of the product specification*: the value NeuroGrid's product specification sets.
*Calibrated*: the 95th percentile over the public test corpus, see [Calibration](#calibration). *Assumption*: a
reading recorded in the decision log `docs/umsetzung/ENTSCHEIDUNGEN.md` of the repository.

**Libraries.** MNE-Python 1.13.2, edfio 0.4.18, MNE-BIDS 0.20.0, BIDS validator 3.0.2 (deno 2.9.7), pyprep
0.9.0, autoreject 0.5.1, python-picard 0.8.2, mne-icalabel 0.10.0 with onnxruntime 1.31.0, numpy 2.4.6, scipy
1.17.1 – all pinned exactly.

## M01 Readability and header {#M01}

**Measured.** Each data file is opened: MNE reads the first and the last 1-s block. EDF headers are checked with
edfio, BDF, BrainVision and EEGLAB headers with own parsers: file size against the header, fields, number formats,
start date. Companion files (`.eeg`, `.vmrk`, `.fdt`, FIF parts) must be plain file names next to the file that
refers to them; other references are not opened. Files in formats NeuroGrid cannot read (for example `.cnt`,
`.mff`, `.xdf`) are findings with their (pseudonymous) file name.

**Identifying header fields** (CORE-M01-05, info): the EDF/EDF+ patient field and recording field, real start dates,
FIF `subject_info` and `experimenter`, EEGLAB `subject` and comment fields. Only the field names are reported,
never the values.

<!-- BEGIN GENERATED thresholds M01 -->
| Rule | Severity | Parameter | Origin |
|---|---|---|---|
| [CORE-M01-01](reference/rules.md#CORE-M01-01) Data file can be read | Error | – | start value of the product specification (A-65) |
| [CORE-M01-02](reference/rules.md#CORE-M01-02) File header is consistent | Error | – | start value of the product specification (A-46) |
| [CORE-M01-03](reference/rules.md#CORE-M01-03) Companion files and references are present | Error | – | assumption A-46 (decision log) |
| [CORE-M01-04](reference/rules.md#CORE-M01-04) Data file format is supported | Error | – | assumption A-12 (decision log) |
| [CORE-M01-05](reference/rules.md#CORE-M01-05) Header contains no person identifier or real date | Note | – | assumption A-64 (decision log) |
<!-- END GENERATED -->

**Limits.** A truncated EDF file is still readable by MNE; it is found by the header check (size against the
header). An EEGLAB data set with embedded data is not readable in blocks; the report says so.

## M02 Metadata completeness {#M02}

**Measured.** The EEG-BIDS required fields `EEGReference`, `SamplingFrequency`, `PowerLineFrequency`,
`SoftwareFilters` and `TaskName`, and the columns `name`, `type`, `units` of `channels.tsv`, one finding per
missing field (sub-key = field name). `n/a` counts as missing for `EEGReference` and `PowerLineFrequency`, as a
valid value for `SoftwareFilters`. Sources in this order: `neurogrid.toml` > BIDS sidecar > file header.
CORE-M02-02 compares `TaskName` with the task label, the form of `BIDSVersion` and an empty `Name`.

<!-- BEGIN GENERATED thresholds M02 -->
| Rule | Severity | Parameter | Origin |
|---|---|---|---|
| [CORE-M02-01](reference/rules.md#CORE-M02-01) Required EEG-BIDS field is documented | Error | – | start value of the product specification (A-03) |
| [CORE-M02-02](reference/rules.md#CORE-M02-02) Metadata are consistent (TaskName, BIDSVersion, Name) | Warning | – | assumption A-46 (decision log) |
<!-- END GENERATED -->

## M03 Sampling rate {#M03}

**Measured.** The sampling rate of each recording (the lowest EEG rate), computed exactly from the ASCII fields of
the header (for example 550 samples per 1.1 s = 500 Hz). Recordings with different rates need a justification in
`[metadata] mixed_sampling_rates_reason`. The rate in a BIDS sidecar must equal the rate of the data.

<!-- BEGIN GENERATED thresholds M03 -->
| Rule | Severity | Parameter | Origin |
|---|---|---|---|
| [CORE-M03-01](reference/rules.md#CORE-M03-01) Sampling rate at or above the minimum | Warning | `min_hz` = 500 (rule pack) | start value of the product specification, which quotes T/GXDSL 008-2025 (second-hand) (A-40) |
| [CORE-M03-02](reference/rules.md#CORE-M03-02) Sampling rates are uniform or the difference is documented | Warning | – | start value of the product specification (A-18) |
| [CORE-M03-03](reference/rules.md#CORE-M03-03) Sampling rate in the sidecar matches the data | Warning | – | assumption A-46 (decision log) |
<!-- END GENERATED -->

## M04 Channel set and montage {#M04}

**Measured.** Channel names against the 10-20/10-10 name lists of the MNE montages `standard_1020` and
`standard_1005` (without a leading "EEG" and without reference endings such as REF, AVG; bipolar derivations
count when both parts are standard names). `[metadata] channel_map` maps own labels. A name that exists only in
10-05 gives a note. Further: electrode positions present, the same channel set for every task, the channel count
in sidecar, `channels.tsv` and data file.

<!-- BEGIN GENERATED thresholds M04 -->
| Rule | Severity | Parameter | Origin |
|---|---|---|---|
| [CORE-M04-01](reference/rules.md#CORE-M04-01) Channel names follow 10-20/10-10 or are mapped | Error | – | start value of the product specification (A-18) |
| [CORE-M04-02](reference/rules.md#CORE-M04-02) Electrode positions are documented | Warning | – | assumption A-18 (decision log) |
| [CORE-M04-03](reference/rules.md#CORE-M04-03) Same channel set for each task | Warning | – | assumption A-18 (decision log) |
| [CORE-M04-04](reference/rules.md#CORE-M04-04) Channel count is consistent | Warning | – | assumption A-46 (decision log) |
| [CORE-M04-05](reference/rules.md#CORE-M04-05) Channel name is within 10-20/10-10 | Note | – | assumption A-18 (decision log) |
<!-- END GENERATED -->

## M05 Impedance {#M05}

**Measured.** Whether each EEG channel has an impedance (BIDS `electrodes.tsv` or the BrainVision header) and,
for wet electrodes, whether it is at most the limit. Whether electrodes are wet or dry is documented only in
`neurogrid.toml` (`[metadata.defaults] electrode_type`); without it the limit is not checkable, for dry electrodes
it is not applicable, because the start value applies to wet electrodes.

<!-- BEGIN GENERATED thresholds M05 -->
| Rule | Severity | Parameter | Origin |
|---|---|---|---|
| [CORE-M05-01](reference/rules.md#CORE-M05-01) Impedance is documented | Warning | – | start value of the product specification (A-83) |
| [CORE-M05-02](reference/rules.md#CORE-M05-02) Impedance below the limit (wet electrodes) | Warning | `max_kohm` = 5 (rule pack) | start value of the product specification, which quotes T/GXDSL 008-2025 (second-hand) (A-40) |
<!-- END GENERATED -->

## M06 Bad channels {#M06}

**Measured.** The share of bad EEG channels found by pyprep `NoisyChannels` (the criteria of `find_all_bads`,
RANSAC last and only with electrode positions) on the sample: 10 segments of 60 s in the middle of 10 equal parts,
recordings up to 10 minutes whole. Each segment is first resampled to 250 Hz; the segments are joined at
boundaries that the filters respect, then filtered with a notch at the line frequency and its harmonic below
125 Hz and a 1–100 Hz band-pass. M06 measures on this data; M09 afterwards uses the average reference without the
bad channels of M06. The sample is documented in `results.json` and in the report.

**Preconditions.** At least 60 s of data, at least 200 Hz and at least 16 EEG channels (`[quality]`
`min_seconds`, `min_channels`); otherwise not checkable.

<!-- BEGIN GENERATED thresholds M06 -->
| Rule | Severity | Parameter | Origin |
|---|---|---|---|
| [CORE-M06-01](reference/rules.md#CORE-M06-01) Share of bad channels within the limit | Warning | `max_fraction` = 0.30625 (rule pack) | calibrated: 95th percentile over 22 recordings of the public corpus (A-20, A-44) |
<!-- END GENERATED -->

## M07 Line noise {#M07}

**Measured.** Per channel over the full length, in 60-s blocks: Welch spectrum with 2-s periodic Hann windows
without overlap; ratio P(f₀ ± 1 Hz) / P(1–40 Hz); the channel value is the median over the blocks. f₀ is the
documented line frequency, otherwise 50 Hz. Not applicable when the sampling rate is below 2·(f₀ + 1).
CORE-M07-02 also measures at the other line frequency (50/60 Hz) and gives a note when it fits better by the
factor `min_factor`.

<!-- BEGIN GENERATED thresholds M07 -->
| Rule | Severity | Parameter | Origin |
|---|---|---|---|
| [CORE-M07-01](reference/rules.md#CORE-M07-01) Line-noise ratio within the limit | Warning | `max_ratio` = 0.407669 (rule pack) | calibrated: 95th percentile over 1050 channels of the public corpus (A-20, A-44) |
| [CORE-M07-02](reference/rules.md#CORE-M07-02) Documented line frequency fits the data | Note | `min_factor` = 2.0 (rule pack) | assumption A-47, A-79 (decision log) |
<!-- END GENERATED -->

## M08 Flat lines and clipping {#M08}

**Measured.** Per channel over the full length, in 1-s windows. Flat: no variance beyond the least significant bit
(from the digital and physical range in EDF/BDF, from the resolution in BrainVision); in floating-point formats
(EEGLAB, FIF) peak-to-peak below `[quality] flat_tolerance_uv` (0.1 µV). Clipping: values at the limits of the
measuring range where it is known (EDF/BDF), otherwise plateaus of at least `[quality] plateau_samples` (10)
equal samples at the extreme. Clipped windows do not count as flat as well. The value is the share of the
duration. Neighbouring windows are joined into time ranges: `results.json` keeps at most 100 per channel with
their number, the report shows at most 20 with their number and total duration.

<!-- BEGIN GENERATED thresholds M08 -->
| Rule | Severity | Parameter | Origin |
|---|---|---|---|
| [CORE-M08-01](reference/rules.md#CORE-M08-01) Flat line within 5 % of the duration | Error | `max_fraction` = 0.05 (rule pack) | start value of the product specification (A-18) |
| [CORE-M08-02](reference/rules.md#CORE-M08-02) Clipping within 5 % of the duration | Error | `max_fraction` = 0.05 (rule pack) | start value of the product specification (A-18) |
<!-- END GENERATED -->

## M09 Artefact share {#M09}

**Measured on the sample of M06.** M09a: the share of rejected 2-s epochs of local autoreject (`cv=10`,
`n_interpolate=[1, 4, 32]`). M09b: the share of ICA components (picard, extended, 20 components, `decim=4`) whose
most likely ICLabel class is not "brain"; ICLabel runs with onnxruntime, its telemetry switched off.

**Preconditions.** As M06, plus: autoreject needs electrode positions; M09a and M09b need the bad channels of M06.
Otherwise not checkable.

<!-- BEGIN GENERATED thresholds M09 -->
| Rule | Severity | Parameter | Origin |
|---|---|---|---|
| [CORE-M09-01](reference/rules.md#CORE-M09-01) autoreject rejection rate within the limit | Warning | `max_fraction` = 0.305083 (rule pack) | calibrated: 95th percentile over 22 recordings of the public corpus (A-20, A-44) |
| [CORE-M09-02](reference/rules.md#CORE-M09-02) Share of non-brain ICA components within the limit | Warning | `max_fraction` = 0.6 (rule pack) | calibrated: 95th percentile over 22 recordings of the public corpus (A-20, A-44) |
<!-- END GENERATED -->

**Limits.** autoreject often rejects 0 % on clean data, and the ICLabel share depends on the number of
components; both values are hard to compare between devices. The thresholds are calibrated on the public corpus
and can be overridden.

## M10 Annotation {#M10}

**Measured.** Annotations from EDF+/BDF+ annotation channels, BrainVision markers, EEGLAB events, FIF annotations
and BIDS `events.tsv`. κ: pairwise unweighted Cohen's κ on a grid (30 s continuous, 1 s events; `[annotation]`
`mode`, `epoch_s`), "no event" is a class of its own; the mean over the pairs is compared with `min_kappa`, the
minimum and the weakest pair are in the details. Codes: within the vocabulary and one code per label. Gaps
(continuous mode only) and overlaps per annotator. With one annotator κ is not applicable.

<!-- BEGIN GENERATED thresholds M10 -->
| Rule | Severity | Parameter | Origin |
|---|---|---|---|
| [CORE-M10-01](reference/rules.md#CORE-M10-01) Agreement between annotators (Cohen's kappa) at least 0.6 | Warning | `min_kappa` = 0.6 (rule pack) | start value of the product specification (A-80) |
| [CORE-M10-02](reference/rules.md#CORE-M10-02) Annotation codes uniform and in the vocabulary | Warning | – | assumption A-17 (decision log) |
| [CORE-M10-03](reference/rules.md#CORE-M10-03) No gaps in continuous annotation | Warning | – | assumption A-17 (decision log) |
| [CORE-M10-04](reference/rules.md#CORE-M10-04) No overlapping annotations per annotator | Warning | – | assumption A-17 (decision log) |
<!-- END GENERATED -->

## M11 Classes and demography {#M11}

**Measured.** The share of each class per scope (all, train, val, test) from the label source in `[ai] labels`
(`events:<column>`, `participants:<column>` or `annotations`), and whether age and sex are documented for every
subject (`participants.tsv`). Ages appear only in 10-year groups, the raw age never. Small cells: a table on
subject level appears only when every filled cell counts at least 5 subjects, otherwise it is withheld and only
its sum is shown.

<!-- BEGIN GENERATED thresholds M11 -->
| Rule | Severity | Parameter | Origin |
|---|---|---|---|
| [CORE-M11-01](reference/rules.md#CORE-M11-01) Every class at least the minimum share | Warning | `min_share` = 0.05 (rule pack) | start value of the product specification (A-81) |
| [CORE-M11-02](reference/rules.md#CORE-M11-02) Age and sex documented | Warning | – | start value of the product specification (A-81) |
<!-- END GENERATED -->

## M12 Split integrity {#M12}

**Measured.** Each subject in at most one split (`.neurogrid/splits.tsv` or a column `split` in
`participants.tsv`), and no duplicate recordings: the signal hash NG-SIGHASH-v1 (SHA-256 per EEG channel over the
rounded values in 0.1 µV, with the sampling rate) finds exact duplicates. Hashes are never output; findings name
the group and its (pseudonymous) recordings.

<!-- BEGIN GENERATED thresholds M12 -->
| Rule | Severity | Parameter | Origin |
|---|---|---|---|
| [CORE-M12-01](reference/rules.md#CORE-M12-01) Each subject in exactly one split | Error | – | start value of the product specification (A-81) |
| [CORE-M12-02](reference/rules.md#CORE-M12-02) No duplicate recordings (signal hash) | Error | – | start value of the product specification (A-21) |
<!-- END GENERATED -->

**Limits.** Only exact duplicates are found; partial duplicates (a cut recording) are not.

## M13 Provenance {#M13}

**Measured.** A manifest (`.neurogrid/manifest.json`, written by `neurogrid manifest`) is present; the files match
it (changed, new, missing, kind changed, unreadable); processing steps and software versions are documented
(`.neurogrid/provenance.yaml`, the steps of `convert`, `GeneratedBy` of `dataset_description.json`).

<!-- BEGIN GENERATED thresholds M13 -->
| Rule | Severity | Parameter | Origin |
|---|---|---|---|
| [CORE-M13-01](reference/rules.md#CORE-M13-01) Provenance manifest present | Warning (--strict: Error) | – | start value of the product specification (A-22, A-82) |
| [CORE-M13-02](reference/rules.md#CORE-M13-02) Files match the manifest | Error | – | start value of the product specification (A-82) |
| [CORE-M13-03](reference/rules.md#CORE-M13-03) Processing steps and software versions documented | Warning | – | assumption A-22 (decision log) |
<!-- END GENERATED -->

## M14 Consent scope (from v0.2) {#M14}

Whether the use of each recording in a split is covered by the consent of its subject. M14 needs NeuroVault and
follows with version 0.2; version 0.1 has no M14 rule.

## Calibration {#calibration}

The calibrated thresholds are the 95th percentile (numpy, linear interpolation) of the values measured on the
public test corpus: 22 recordings and 1050 channels of five OpenNeuro data sets in five formats. The protocol is
`src/neurogrid/rulepacks/calibration/core.json`; a test checks that protocol, rule pack and check defaults agree.

<!-- BEGIN GENERATED calibration -->
| Data set | Version | DOI | Format | Recordings | Channels (M07) |
|---|---|---|---|---|---|
| ds000248 | 1.2.4 | 10.18112/openneuro.ds000248.v1.2.4 | FIF | 1 | 60 |
| ds002778 | 1.0.5 | 10.18112/openneuro.ds002778.v1.0.5 | BDF | 5 | 200 |
| ds003775 | 1.2.1 | 10.18112/openneuro.ds003775.v1.2.1 | EDF | 8 | 512 |
| ds004148 | 1.0.1 | 10.18112/openneuro.ds004148.v1.0.1 | BrainVision | 3 | 183 |
| ds004504 | 1.0.9 | 10.18112/openneuro.ds004504.v1.0.9 | EEGLAB | 5 | 95 |
<!-- END GENERATED -->

These values describe the corpus. They may not fit other devices, montages or populations; check them on own
data and override them in `neurogrid.toml` with a justification.

## Literature {#literature}

The methods are those of the pinned libraries; their authors ask to cite:

- PREP pipeline (pyprep): Bigdely-Shamlo et al., Frontiers in Neuroinformatics 9:16, 2015,
  doi:10.3389/fninf.2015.00016.
- autoreject: Jas et al., NeuroImage 159, 417–429, 2017.
- ICLabel: Pion-Tonachini et al., NeuroImage, 2019, doi:10.1016/j.neuroimage.2019.05.026; mne-icalabel: Li et al.,
  Journal of Open Source Software, 2022, doi:10.21105/joss.04484.
- picard: Ablin, Cardoso, Gramfort, IEEE Transactions on Signal Processing, 2018.
- MNE-BIDS: Appelhoff et al., Journal of Open Source Software 4:1896, 2019, doi:10.21105/joss.01896.
- MNE-Python: doi:10.5281/zenodo.592483.
