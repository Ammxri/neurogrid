# Licences {#licences}

| Part | Licence |
|---|---|
| Source code, tools, configuration | Apache License 2.0 (`LICENSE`, `NOTICE`) |
| Documentation text (the text of these pages, README, DATA_SOURCES) and synthetic sample data | Creative Commons Attribution 4.0 International (CC BY 4.0), https://creativecommons.org/licenses/by/4.0/ |
| Report fonts (Noto Sans SC, static cuts) | SIL Open Font License 1.1 (`src/neurogrid/report/fonts/OFL.txt`) |
| Theme, scripts, icons and font of this documentation site | their own licences, see [below](#docs-site) |
| `THIRD_PARTY_NOTICES.txt` | NeuroGrid's own text CC BY 4.0; the licence texts and notices it reproduces keep their own terms |

The licence of every file is listed in `REUSE.toml` of the repository; the licence texts are in `LICENSES/`.
The wheel declares `Apache-2.0 AND OFL-1.1`, because it carries the report fonts.

## Third-party components {#third-party}

`THIRD_PARTY_NOTICES.txt` lists every package NeuroGrid depends on for Windows and Linux, the native libraries
and other components inside those packages (for example the OpenBLAS and GCC runtime libraries of numpy and
scipy, the deno runtime and the BIDS validator bundle) with their licences and licence texts. It is generated from
the locked packages by `tools/notices.py` and ships with every release and in the offline bundle. Known gaps are
named in the file and are closed before the publication.

The test data sets of the public corpus and their licences are listed in `DATA_SOURCES.md`.

## This documentation site {#docs-site}

CC BY 4.0 covers NeuroGrid's own text of these pages. The site is built with the theme mkdocs-material
(MIT), whose files keep their own licences:

| Part | Licence |
|---|---|
| mkdocs-material: page templates, style sheets, scripts, favicon | MIT |
| in its script bundle: rxjs, tslib, clipboard, escape-html, focus-visible | Apache-2.0, 0BSD, MIT, MIT, W3C Software and Document License |
| in its search: lunr | MIT |
| in its style sheet: the colour palette material-design-color | MIT |
| icons: Material Design Icons, Octicons, Font Awesome Free | Apache-2.0, MIT, CC BY 4.0 |
| the Chinese characters: a subset of Noto Sans SC | SIL Open Font License 1.1 |

`THIRD_PARTY_NOTICES.txt` lists each part with its copyright and licence text. For the two parts whose
licence the shipped files do not state, focus-visible and material-design-color, the texts come from the
projects themselves; focus-visible names no copyright holder, so the file names its repository instead.
The language files of the search (lunr-languages, under the Mozilla Public License) are not part of the
site: the search of this documentation does not use them.

## Not distributed {#not-distributed}

The Chrome Headless Shell that prints the PDF reports is not part of NeuroGrid or of the offline bundle. You
install it yourself with `tools/install_pdf_browser.py`, under Google's terms
([Installation](installation.md#pdf-browser)).
