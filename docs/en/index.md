# NeuroGrid {#neurogrid}

!!! note "Fixed sentence"
    Pre-check with NeuroGrid. Not a conformity assessment within the meaning of NMPA regulations.

NeuroGrid is an open, local and offline tool that pre-checks EEG datasets for AI-based brain–computer interface
(BCI) devices. It reads EDF/EDF+, BDF, BrainVision, EEGLAB and FIF recordings, converts raw folders to EEG-BIDS,
measures the quality metrics M01–M13, evaluates them with rule packs and writes `results.json` plus a report in
Chinese and English (HTML and PDF).

A result says whether a dataset *passes the checks of the loaded rule packs*.
NeuroGrid performs no conformity assessment: conformity is assessed by test institutes and the NMPA.
NeuroGrid evaluates datasets only, never people, and it is not a medical device.

## What version 0.1 contains {#v01}

- Commands `scan`, `convert --to bids`, `check`, `report`, `manifest` and `verify` ([Commands](commands.md)).
- The rule packs `core` (metrics M01–M13, [Metrics](metrics.md)), `bids` (BIDS validator 3.0.2) and `gxdsl008`
  (start values that the product specification quotes from T/GXDSL 008-2025, second-hand)
  ([Built-in rules](reference/rules.md)).
- Own rule packs in YAML that use the registered checks ([Rule packs](rulepacks.md)).
- `results.json` as the canonical result and the report in Chinese and English ([Reading the report](report.md),
  [Output files](reference/outputs.md)).
- Local operation without any network connection ([Privacy and offline operation](privacy.md)).

Version 0.1 contains no content from YY/T 2029-2026. A yyt2029 rule pack follows once the norm text has been read.
`diff`, NeuroVault and the evidence dossier are not part of version 0.1 ([Limitations](limitations.md)).

## Where to start {#start}

1. [Installation](installation.md): offline bundle, PDF browser, installation from source.
2. [Quick start](quickstart.md): from a raw folder to the report in four commands.
3. [Configuration](configuration.md): `neurogrid.toml` with metadata, thresholds and justified exceptions.

## Open reference and feedback {#feedback}

NeuroGrid is an open reference: test institutes, authors of standards and manufacturers can run it themselves,
read every rule with its method, threshold and origin, and write their own rule packs. The source code, the
decision log (`docs/umsetzung/` in the repository) and these pages are public.

Questions about how a clause or a threshold is read, and any other feedback, go to the issue tracker of the
public repository.

!!! warning "Placeholder"
    The address of the public repository is `<REPO_URL>`; it is filled in when the repository is published.

## Licences {#licence}

Code: Apache-2.0. Documentation and sample data: CC BY 4.0. Report fonts: SIL Open Font License 1.1.
See [Licences](license.md).
