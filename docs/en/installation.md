# Installation {#installation}

NeuroGrid runs locally. There are three ways to install it: the offline bundle (for computers without internet
access), from PyPI, or from the source code. For PDF reports a separate browser, the Chrome Headless Shell, is
installed once; HTML reports work without it.

## Supported platforms {#platforms}

| Platform | Status |
|---|---|
| Windows 11 x64, Windows PowerShell 5.1 | verified locally |
| Windows 11 x64, PowerShell 7 | not verified until the first CI run |
| Windows 10 x64 | not verified |
| Linux x86_64 with glibc 2.28 or newer: Debian 12, Ubuntu 22.04 and newer | not verified until the first CI run |
| Linux ARM64, macOS | not supported |

"Not verified" means: NeuroGrid is built for these systems, but no test run on them has been recorded yet.
Python 3.11–3.13 is supported; the offline bundle brings its own Python 3.12.

## Offline bundle {#offline-bundle}

Each release has one bundle per platform:

- `neurogrid-<version>-offline-win_amd64.zip`
- `neurogrid-<version>-offline-linux_x86_64.tar.gz`

The archive contains one folder `neurogrid-<version>-offline-<platform>/` with:

| Part | Content |
|---|---|
| `python/` | Python 3.12 (python-build-standalone) |
| `uv/` | the uv binary and its licences |
| `wheels/`, `requirements.lock.txt` | every runtime package as a wheel, pinned with SHA-256 |
| `docs/` | this documentation (zh/en) |
| `tools/install_pdf_browser.py` | installer of the PDF browser (see below) |
| `src/neurogrid-<version>.tar.gz` | the source code of this release |
| `install.cmd`, `install.ps1` / `install.sh` | installation scripts (Windows / Linux) |
| `README.txt`, `LICENSE`, `NOTICE`, `THIRD_PARTY_NOTICES.txt` | short guide and licences |
| `BUNDLE.json`, `SHA256SUMS`, `SHA256SUMS.sigstore.json` | contents, checksums, release signature |

The Chrome Headless Shell is not part of the bundle; it is installed separately (see [PDF browser](#pdf-browser)).

### Verify the download {#verify}

Check the signature on a computer with internet access before you move the archive, then the checksums on the
target computer.

```bash
# on a connected computer: signature of the release checksums (Sigstore, cosign)
cosign verify-blob SHA256SUMS --bundle SHA256SUMS.sigstore.json \
  --certificate-identity "<REPO_URL>/.github/workflows/release.yml@refs/tags/v<version>" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
sha256sum --check --ignore-missing SHA256SUMS
```

!!! warning "Placeholder"
    `<REPO_URL>` is the address of the public repository; it is filled in when the repository is published.

On Windows, compare the value of `Get-FileHash -Algorithm SHA256 <file>` with the line of the file in
`SHA256SUMS`. The installation script checks every file of the bundle against its `SHA256SUMS` again. A check by
a script inside the same archive proves that the files are intact, not who made them; the signature check
before the transfer does that. The installer prints the signer identity it verified (`signature verified: …`),
and `README.txt` in the bundle names it: compare it with the identity in the release notes on the project's
release page, because an identity read from the archive can be changed together with the archive.

### Install {#install}

=== "Windows"

    ```powershell
    # unpack the zip, then in the unpacked folder:
    .\install.cmd -Prefix "$env:LOCALAPPDATA\NeuroGrid\<version>"
    ```

    `install.cmd` starts `install.ps1` with Windows PowerShell 5.1 for this one process; no system setting is
    changed. Options: `-Prefix <folder>`, `-Cosign <path to cosign.exe>`, `-SkipSignatureCheck`,
    `-VerifyOnly`, `-PdfBrowserZip <zip> -PdfBrowserSha256 <hex>`.

=== "Linux"

    ```bash
    tar -xzf neurogrid-<version>-offline-linux_x86_64.tar.gz
    cd neurogrid-<version>-offline-linux_x86_64
    bash install.sh --prefix "$HOME/.local/share/neurogrid/<version>"
    ```

    Options: `--prefix <folder>`, `--cosign <path>`, `--skip-signature-check`, `--verify-only`,
    `--pdf-browser-zip <zip> --pdf-browser-sha256 <hex>`. No root rights are needed.

Without `cosign` the script stops unless the signature check is skipped explicitly
(`-SkipSignatureCheck` / `--skip-signature-check`) after the check on a connected computer described above.
When `cosign` is there (named with `-Cosign` / `--cosign` or found on `PATH`), the script always checks the
signature, and the switch does not override a `cosign` that rejects it. The script creates a virtual environment in the prefix (bytecode compiled), installs the wheels offline with
their hashes and writes a launcher. Exit codes: 0 installed, 2 usage or environment, 3 integrity, 4 signature.

On Windows the install folder needs a short path: Windows cannot start programs or load some modules from
longer paths, even with long paths enabled (`LongPathsEnabled`), so every installed file stays within 250
characters. The installer accepts a prefix of at most 249 characters minus the longest relative path below it,
which `BUNDLE.json` records as `max_relative_install_path`; a longer prefix stops it with exit code 2 before it
creates anything. For NeuroGrid 0.1.0rc1 that path has 148 characters, so the limit is 101 characters. The
default prefix `%LOCALAPPDATA%\NeuroGrid\<version>` is much shorter.

The Python of the Linux bundle lacks the module `dbm.ndbm` (`_dbm`): it links Berkeley DB, which is under the
Sleepycat licence, so the bundle leaves it out and records this in `BUNDLE.json` (`python.removed`). NeuroGrid
does not use it.

The launcher is not added to `PATH`. Call it with its full path:

=== "Windows"

    ```powershell
    & "$env:LOCALAPPDATA\NeuroGrid\<version>\neurogrid.cmd" --help
    ```

=== "Linux"

    ```bash
    "$HOME/.local/share/neurogrid/<version>/bin/neurogrid" --help
    ```

Uninstalling means deleting the prefix folder and, if installed, the folder of the PDF browser.

## PDF browser {#pdf-browser}

PDF reports are printed by the Chrome Headless Shell, revision 1243 (the build that Playwright 1.63.0 uses).
It is a Google build with its own terms and is therefore not distributed with NeuroGrid (D-08).
`tools/install_pdf_browser.py` installs it into a NeuroGrid folder:

| | Folder |
|---|---|
| Windows | `%LOCALAPPDATA%\NeuroGrid\pdf-browser` |
| Linux | `${XDG_DATA_HOME:-~/.local/share}/neurogrid/pdf-browser` |
| any | the folder in the environment variable `NEUROGRID_PDF_BROWSER_DIR`, if set |

NeuroGrid uses only this folder; it never uses a system Chrome, Edge or the Playwright browser cache.

```bash
# online: download the pinned archive (URL, size and SHA-256 are fixed in the script)
python tools/install_pdf_browser.py
# offline: on a connected computer
python tools/install_pdf_browser.py --download-only --platform win64 --out <folder>
# then on the target computer, with the SHA-256 the script printed
python tools/install_pdf_browser.py --from-zip <zip> --sha256 <hex>
# show the pinned data, or check an installed browser
python tools/install_pdf_browser.py --print-info
python tools/install_pdf_browser.py --check
```

`--platform` is `win64` or `linux64`. Only the pinned archive is accepted. In the offline bundle the script lies in
`tools/` and runs with the bundled Python (`python\python.exe` on Windows, `python/bin/python3.12` on Linux);
the installation scripts can run it for you (`-PdfBrowserZip`, `--pdf-browser-zip`).

With an installation from PyPI or from source, download the script from the release of your NeuroGrid version.
Address and SHA-256 of the script of this version:

<!-- BEGIN GENERATED pdf installer -->
```text
<REPO_URL>/releases/download/v<version>/install_pdf_browser.py
SHA-256: 3e713e1400cde83a93782d1dacd0e8201fcb74693c787987e7e5ca51cfd6b149
```
<!-- END GENERATED -->

The same value is the `install_pdf_browser.py` line of the release's `SHA256SUMS`, whose signature you check as
in [Verify the download](#verify). Compare it before you run the script with Python 3.11 or later:

```bash
sha256sum install_pdf_browser.py                         # Linux
Get-FileHash -Algorithm SHA256 install_pdf_browser.py    # Windows PowerShell
```

Without the browser, `neurogrid report --format pdf` stops with exit code 2 and a hint; `--format html` always
works. On Linux the browser needs system libraries; NeuroGrid checks them before printing and names the missing
packages. The package lists for Debian 12, Ubuntu 22.04 and Ubuntu 24.04 are in
`src/neurogrid/kernel/pdf_linux_packages.json`.

## From PyPI {#pypi}

!!! warning "Placeholder"
    NeuroGrid is published on PyPI by the project owner; until then the release is `<PYPI_RELEASE>`.

```bash
python -m pip install neurogrid
```

## From the source code {#source}

```bash
uv sync --locked --no-build
uv run neurogrid --help
```

`uv.lock` pins every package with its hash; `--no-build` installs only wheels, never builds a package from
source. `uv build` creates the wheel and the source archive of NeuroGrid itself.

## Opening this documentation {#docs}

The documentation is a static website in the bundle folder `docs/`. Open `docs/index.html` in a browser to
read it. The search needs the pages to be served; start a local web server that listens on this computer only:

=== "Windows"

    ```powershell
    .\python\python.exe -m http.server 8000 --bind 127.0.0.1 --directory docs
    ```

=== "Linux"

    ```bash
    python/bin/python3.12 -m http.server 8000 --bind 127.0.0.1 --directory docs
    ```

Then open `http://127.0.0.1:8000/`. Opened directly from the disk, the search field is disabled and says so.

The pages load nothing from other computers; the documentation build checks every page, stylesheet and script
for that. One case lies outside the documentation: in a browser without the ResizeObserver interface, the
theme's script tries to load a replacement from `unpkg.com`.
