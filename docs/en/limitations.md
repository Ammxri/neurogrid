# Limitations {#limitations}

!!! note "Fixed sentence"
    Pre-check with NeuroGrid. Not a conformity assessment within the meaning of NMPA regulations.

## What a result means {#meaning}

NeuroGrid is a pre-check. A result says whether a dataset passes the checks of the loaded rule packs, nothing
more; conformity is assessed by test institutes and the NMPA. NeuroGrid evaluates datasets only, never people,
and it is not a medical device. It gives no legal advice.

## Rule packs and thresholds {#thresholds}

- **gxdsl008** takes its five start values second-hand: the norm text of T/GXDSL 008-2025 was not accessible,
  every clause is "unknown", and no coverage measure is computed. All its rules are warnings.
- **Calibrated thresholds** (M06, M07, M09) are the 95th percentile over five public OpenNeuro data sets
  (22 recordings, 1050 channels). They may not fit other devices, montages or populations; check and override
  them with a justification.
- Version 0.1 contains no content from YY/T 2029-2026. A yyt2029 rule pack follows once the norm text has been read.

## Methods {#methods}

- M06 and M09 run on a sample (10 × 60 s by default); local disturbances outside the sample are not seen by them.
  M07 and M08 always use the full recording. `[sampling] mode = "full"` uses the whole recording.
- M09: autoreject often rejects 0 % on clean data, and the ICLabel share depends on the number of components;
  both are hard to compare between devices.
- M12 finds exact duplicates only, no partial ones.
- EEGLAB data sets with the data embedded in the `.set` file cannot be read in blocks; their memory use is about
  the size of the file.
- The BIDS validator 3.0.2 validates against its bundled schema (BIDS 1.11.1), while the current specification
  is BIDS 1.11.2. HED schemas newer than 8.4.0 are not available offline and give a finding of their own.
- Mapping patterns in `[convert] pattern` with adjacent overlapping repetitions are not detected and can make a
  run very slow (Ctrl+C ends it).

## Platforms {#platforms}

Windows 11 is verified locally. In the CI the offline bundle is verified on Windows Server (Windows PowerShell 5.1
and PowerShell 7), Debian 12, Ubuntu 22.04 and Ubuntu 24.04, and the test suite with Python 3.11–3.13 on Windows
Server and Ubuntu 24.04; the CI does not run the test suite on Debian 12 and Ubuntu 22.04. Windows 10, PowerShell 7
on Windows 11 and Ubuntu releases after 24.04 are not verified; other Linux distributions and ARM64 are not
supported ([Installation](installation.md#platforms)).

## Not part of version 0.1 {#not-in-v01}

- `diff` (comparison of two results), NeuroVault (consent, roles, access log, M14) and the evidence dossier
  follow in later versions.
- GB/T 47127 as an input and output format follows with version 0.2.
- The documentation is published inside the offline bundle and as a build artefact; a website for it is decided
  with the publication.
