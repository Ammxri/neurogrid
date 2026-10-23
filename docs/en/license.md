# Licences {#licences}

| Part | Licence |
|---|---|
| Source code, tools, configuration | Apache License 2.0 (`LICENSE`, `NOTICE`) |
| Documentation (these pages, README, DATA_SOURCES) and synthetic sample data | Creative Commons Attribution 4.0 International (CC BY 4.0), https://creativecommons.org/licenses/by/4.0/ |
| Report fonts (Noto Sans SC, static cuts) | SIL Open Font License 1.1 (`src/neurogrid/report/fonts/OFL.txt`) |

The licence of every file is listed in `REUSE.toml` of the repository; the licence texts are in `LICENSES/`.
The wheel declares `Apache-2.0 AND OFL-1.1`, because it carries the report fonts.

## Third-party components {#third-party}

`THIRD_PARTY_NOTICES.txt` lists every package NeuroGrid depends on for Windows and Linux, the native libraries
and other components inside those packages (for example the OpenBLAS and GCC runtime libraries of numpy and
scipy, the deno runtime and the BIDS validator bundle) with their licences and licence texts. It is generated from
the locked packages by `tools/notices.py` and ships with every release and in the offline bundle. Known gaps are
named in the file and are closed before the publication.

The test data sets of the public corpus and their licences are listed in `DATA_SOURCES.md`.

## Not distributed {#not-distributed}

The Chrome Headless Shell that prints the PDF reports is not part of NeuroGrid or of the offline bundle. You
install it yourself with `tools/install_pdf_browser.py`, under Google's terms
([Installation](installation.md#pdf-browser)).
