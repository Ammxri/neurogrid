# NeuroGrid – Nachbau-Anleitung (technisch)

Diese Anleitung beschreibt, wie NeuroGrid von null auf einem eigenen Windows-11-Rechner wieder aufgebaut wird:
Werkzeuge, Umgebungen, Repository, Arbeitsweise, Phasen P0–P5, Prüfwerkzeuge, Testkorpus und Downloads. Sie ist
technisch; Geschäftsinhalte der PRD stehen hier nicht (A-01). Verweise auf die PRD nennen nur Abschnittsnummern.

**Stand:** Zweig `dev`, Merge-Commit `584b7d2` (P5-Bereiche zusammengeführt) plus Doku-Commit `19bd93c` (D-15).
**P5 ist noch nicht abgeschlossen.** Alle mit „Stand 584b7d2, P5 noch nicht abgeschlossen“ markierten Abschnitte
beschreiben den gemergten Zwischenstand; Integration, Abnahme (A-88), Review, Matrix und FORTSCHRITT von P5 folgen
und werden vom Lead nachgetragen.

---

## 0 Zweck und Lesehinweis

### 0.1 Zweck

- Jeder Schritt steht als Befehl in der Reihenfolge, in der er ausgeführt wird. Jeder Befehlsblock nennt seine
  Shell: **PowerShell** (Windows PowerShell 5.1) oder **Git Bash** (aus Git for Windows).
- Zu jedem Schritt stehen, soweit protokolliert, das erwartete Ergebnis (Testzahlen, Exitcodes, Größen, Zeiten)
  und die Prüfung, die den Schritt belegt.
- Entscheidungen (D-xx), Annahmen (A-xx) und Matrix-IDs (z. B. TECH-02, NG-N02) stehen dort, wo ein Schritt sie
  umsetzt. Die Texte stehen in [ENTSCHEIDUNGEN.md](ENTSCHEIDUNGEN.md), die Matrix in
  [ANFORDERUNGEN.md](ANFORDERUNGEN.md), Architektur und Phasenplan in [KONZEPT.md](KONZEPT.md), die Phasenberichte
  in [FORTSCHRITT.md](FORTSCHRITT.md).

### 0.2 Was reproduzierbar ist und was der Projektverantwortliche beisteuert

**Mit dieser Anleitung allein reproduzierbar:**
- die Werkzeugkette (Git, Python, uv) und die drei Python-Umgebungen 3.11/3.12/3.13
- die Installation aus `uv.lock` (exakte Pins, nur Wheels)
- alle Generatoren mit `--check` (Fixtures, Schemas, Montage-Namen, Doku-Seiten, Schriften, Kalibrierprotokoll)
- die Testsuite, Abdeckungs- und Lizenz-Gate, Rückverfolgbarkeit
- der öffentliche Testkorpus (gepinnt per SHA-256), Kalibrierung und Laufzeitmessung NG-N02
- PDF-Browser, Dokumentationsseite, Notices, Offline-Bündel und Windows-Reinraumtest

**Braucht den Projektverantwortlichen:**

| Was | Wofür | Stand |
|---|---|---|
| Repository-URL `<REPO_URL>` (GitHub) und Push-Freigabe | erster CI-Lauf, Linux (D-07, D-09, D-15) | offen bis STOPP G1 |
| die PRD selbst (PDF, privat) | nur für die Planung; liegt in `.local/prd/`, nie versioniert (A-01) | beim Projektverantwortlichen |
| Normtexte GB/T 47127, YY/T 2029, ISO/IEC TS 27571 | P7, P8, P10 (D-02, A-55) | nicht vorhanden |
| Konten: GitHub, Gitee, PyPI/TestPyPI (Trusted Publishing) | Release, Spiegel, Veröffentlichung (D-07, D-15) | nicht bekannt; weder Projektdokumente noch Faktenbasis belegen ein angelegtes Konto [NV] |
| Freigabe von Downloads außerhalb D-06 | CC-BY-4.0-Rechtstext, npm/jsr-Lizenzdateien des Validators | freigegeben (D-15); Ablage in `LICENSES/` und `license-gate/known_missing.toml` noch offen |
| Entscheidung zu den übrigen fehlenden Lizenztexten | BIDS-Schema-Lizenz im Validator, libaec/libsz im Linux-h5py-Wheel, Bibliothekstexte von python-build-standalone (D-15 gibt nur zwei der sechs Einträge in `known_missing.toml` frei) | offen bis STOPP G1 |
| muttersprachliche zh-Prüfung | alle zh-Texte (A-07, STOPP G1) | offen |

### 0.3 Platzhalter

| Platzhalter | Bedeutung |
|---|---|
| `<Projektordner>` | Wurzel des Repositorys (enthält `pyproject.toml`) |
| `<Benutzerordner>` | Profilordner des Windows-Benutzers (`%USERPROFILE%`) |
| `%APPDATA%`, `%LOCALAPPDATA%`, `%TEMP%` | Windows-Standardordner (PowerShell: `$env:APPDATA` usw.; Git Bash: `$APPDATA` usw.) |
| `<uv>` | Pfad zu `uv.exe`, siehe 1.3 Schritt 3 |
| `<Ziel>` | ein beliebiger, leerer Ausgabeordner |
| `<REPO_URL>`, `<owner>/<repo>` | öffentliches Repository, sobald angelegt |
| `<v>` | Paketversion, heute `0.1.0rc1` |

Alle Befehle laufen im `<Projektordner>`, wenn nichts anderes dasteht.

### 0.4 Belegstufen

Wichtige Angaben tragen eine Belegstufe:

| Kürzel | Bedeutung |
|---|---|
| **[G]** | geprüft: Befehl ausgeführt bzw. Datei oder Quelltext gelesen (für den heutigen Stand am 26.10.2026 auf `19bd93c`) |
| **[D]** | belegt in den Projektdokumenten, Commit-Nachrichten oder Messprotokollen, nicht neu ausgeführt |
| **[R]** | rekonstruiert: nirgends protokolliert, folgt aber eindeutig aus den Artefakten |
| **[NV]** | nicht verifiziert oder nicht mehr vorhanden |

---

## 1 Voraussetzungen

### 1.1 Rechner

| Merkmal | Wert des Entwicklungsrechners | Mindestens nötig |
|---|---|---|
| Betriebssystem | Windows 11 Home 10.0.26200 (x64) [G] | Windows 11 x64 (Windows 10 nicht verifiziert) |
| Kerne / RAM | 8 physische / 16 logische Kerne, 33,6 GB RAM [D] | 4 Kerne, 16 GB für NG-N02 (D-12, D-14) |
| Freier Platz | 323 GB zu Beginn [D] | ≈ 15 GB: Korpus 1,06 GB, 3 × 1 GB Laufzeitdateien, venvs, Caches, Bündel |
| Lange Pfade | `LongPathsEnabled = 1` [G] | empfohlen; Bündel prüft selbst (A-87) |
| Linux / WSL / Docker | kein Linux; Docker Desktop installiert, Engine nicht genutzt [D] | nicht nötig (D-09: Linux nur über CI) |

### 1.2 Werkzeuge und genaue Versionen

| Werkzeug | Version | Herkunft | Rolle |
|---|---|---|---|
| Git for Windows (mit Git Bash) | 2.51.1.windows.1 [G] | git-scm.com, war vorhanden | Versionsverwaltung, Git Bash |
| pdftotext (Xpdf) | 4.00 [G] | Teil von Git for Windows (`/mingw64/bin`) | nur Phase 0: PRD als Text |
| Python 3.13 (System) | 3.13.7 [G] | python.org-Installer, war vorhanden | trägt `uv` (pip) und die venv 3.13 |
| uv | 0.13.0 (`4ecd0eff2 2026-10-09`) [G] | PyPI, per pip ins Benutzerverzeichnis von Python 3.13 [R] | Umgebungen, Lock, Build |
| CPython 3.12.15 | 3.12.15 [G] | python-build-standalone über `uv python install` | Hauptumgebung `.venv`, Bündel-Interpreter |
| CPython 3.11.17 | 3.11.17 [G] | python-build-standalone über `uv python install` | Prüfumgebung 3.11 |
| Windows PowerShell | 5.1.26100.9711 [G] | Systembestandteil | Rauchtests, Installer, Reinraum |
| deno | 2.9.7 | PyPI-Paket `deno`, kommt mit `uv sync` | BIDS-Validator (A-06) |
| BIDS-Validator | bids-validator-deno 3.0.2 (Schema 1.2.7 = BIDS 1.11.1) | PyPI, kommt mit `uv sync` | Paket `bids` |
| Playwright | 1.63.0 (mit Node.js 24.21.0 im Wheel) | PyPI, kommt mit `uv sync` | PDF-Druck (A-85) |
| Chrome Headless Shell | Revision 1243 = 153.0.8010.12 | `tools/install_pdf_browser.py` (Download freigegeben durch D-06 „Chromium für Playwright“; D-08: nie im Bündel) | PDF, Doku-Browsertests |
| PowerShell 7, gh, actionlint | – | **nicht** installiert / nicht verwendet | – |

Nicht nötig: Node.js aus dem System (NeuroGrid nutzt es nicht), Microsoft Edge (verboten, A-26), Docker (D-09).

### 1.3 Installationsreihenfolge

**Schritt 1 – Git for Windows 2.51.1** installieren (Standardoptionen; Git Bash mit installieren). Installer
`Git-2.51.1-64-bit.exe` von der Release-Seite
`https://github.com/git-for-windows/git/releases/tag/v2.51.1.windows.1` (Größe und SHA-256 nicht festgehalten, die
Release-Seite nennt die Prüfsummen [NV]; auf dem Entwicklungsrechner war Git schon vorhanden). Prüfung (Git Bash):
```bash
git --version          # git version 2.51.1.windows.1
pdftotext -v 2>&1 | head -1   # pdftotext version 4.00
git config --show-origin core.autocrlf   # systemweit true (<Git-Installationsordner>/etc/gitconfig)
```
`core.autocrlf=true` bleibt; `.gitattributes` erzwingt LF im Arbeitsbaum (siehe 1.6). Eigene Identität setzen:
```bash
git config --global user.name "<Name>"
git config --global user.email "<E-Mail>"
```

**Schritt 2 – Python 3.13.7** vom python.org-Installer `python-3.13.7-amd64.exe`
(`https://www.python.org/ftp/python/3.13.7/python-3.13.7-amd64.exe`, Seite `https://www.python.org/downloads/release/python-3137/`;
Größe und Prüfsumme nicht festgehalten [NV]; war vorhanden) installieren: 64 Bit, „py launcher“ an. Prüfung (PowerShell):
```powershell
py -0p        # listet 3.13 (Python313); ein vorhandenes 3.14 stört nicht, ist aber nicht nutzbar (requires-python <3.14)
```

**Schritt 3 – uv 0.13.0** (D-06) [R: Beleg ist das dist-info mit `INSTALLER=pip` im Benutzer-site-packages von
Python 3.13]. PowerShell:
```powershell
py -3.13 -m pip install --user uv==0.13.0
$env:Path = "$env:APPDATA\Python\Python313\Scripts;$env:Path"   # uv ist sonst nicht im PATH
$env:UV   = "$env:APPDATA\Python\Python313\Scripts\uv.exe"      # für tools/licenses.py und einige Tests
uv --version   # uv 0.13.0 (4ecd0eff2 2026-10-09 x86_64-pc-windows-msvc)
```
pip lädt dabei die Datei `uv-0.13.0-py3-none-win_amd64.whl` (15 819 247 B, SHA-256
`0367b4e0ae4dcef32da4aa2ad2f3853b6ad81d50c187abe50d343d892b8fea21`), dieselbe, die `packaging/bundle_lock.json` für
das Bündel pinnt (Abschnitt 7). Hash-gebunden (empfohlen, PowerShell):
```powershell
Set-Content -Path "$env:TEMP\uv-req.txt" -Encoding ascii -Value "uv==0.13.0 --hash=sha256:0367b4e0ae4dcef32da4aa2ad2f3853b6ad81d50c187abe50d343d892b8fea21"
py -3.13 -m pip install --user --require-hashes --only-binary :all: -r "$env:TEMP\uv-req.txt"
```
Git Bash:
```bash
export PATH="$APPDATA/Python/Python313/Scripts:$PATH"
export UV="$APPDATA/Python/Python313/Scripts/uv.exe"
uv --version
```
Auf dem Entwicklungsrechner liegt uv **nicht** im PATH; alle Läufe nutzten den vollen Pfad `<uv>` [G]. Den PATH
dauerhaft zu setzen ist erlaubt, aber nicht nötig.

**Schritt 4 – Python 3.11 und 3.12 über uv** (D-06) [R]:
```powershell
uv python install 3.11.17 3.12.15
uv python list --only-installed   # mindestens cpython-3.12.15 und cpython-3.11.17 unter %APPDATA%\uv\python
```
Die Liste zeigt auch die System-Pythons (cpython-3.13.7, gegebenenfalls 3.14.x unter
`%LOCALAPPDATA%\Programs\Python`); erwartet werden mindestens 3.11.17 und 3.12.15 unter `%APPDATA%\uv\python` [G].
Ablage: `%APPDATA%\uv\python\cpython-3.1x.y-windows-x86_64-none`. Python 3.13 kommt nicht über uv, sondern vom
System (Schritt 2). Eine Warnung „Failed to inspect Python interpreter“ zu einer kaputten Verknüpfung
`cpython-3.12-windows-x86_64-none` ist bekannt und harmlos [G].

**Schritt 5 – Repository holen** (siehe 2.1), dann **Schritt 6 – Umgebungen** (1.4), **Schritt 7 – PDF-Browser**
(4.7.3), **Schritt 8 – Testkorpus** (Abschnitt 6). Schriften (`tools/build_fonts.py`) sind eingecheckt und müssen
nur zur Prüfung neu gebaut werden.

### 1.4 Die drei Python-Umgebungen

| Umgebung | Python | Rolle | Anlage |
|---|---|---|---|
| `.venv` | 3.12.15 (uv) | Hauptumgebung: Entwicklung, Generatoren, Bündelbau (A-42) | `uv sync --locked --no-build` |
| `.local/venv3.11` | 3.11.17 (uv) | Testlauf und Plattformvergleich 3.11 (D-05) | `UV_PROJECT_ENVIRONMENT` + `uv sync` [R] |
| `.local/venv3.13` | 3.13.7 (System) | Testlauf und Plattformvergleich 3.13 | `UV_PROJECT_ENVIRONMENT` + `uv sync` [R] |

`.python-version` enthält `3.12`, deshalb wählt `uv sync` ohne `--python` die 3.12. Git Bash:
```bash
uv sync --locked --no-build
UV_PROJECT_ENVIRONMENT=.local/venv3.11 uv sync --locked --no-build --python 3.11
UV_PROJECT_ENVIRONMENT=.local/venv3.13 uv sync --locked --no-build --python 3.13
```
PowerShell:
```powershell
uv sync --locked --no-build
$env:UV_PROJECT_ENVIRONMENT = ".local\venv3.11"; uv sync --locked --no-build --python 3.11
$env:UV_PROJECT_ENVIRONMENT = ".local\venv3.13"; uv sync --locked --no-build --python 3.13
Remove-Item Env:UV_PROJECT_ENVIRONMENT
```
Beleg für die Rekonstruktion: beide `pyvenv.cfg` tragen `prompt = neurogrid` und `uv = 0.13.0`; `uv venv` schreibt
keinen `prompt`, `uv sync` mit `UV_PROJECT_ENVIRONMENT` schon [G].

Erwartung und Prüfung:
- `uv sync` installiert Laufzeit + Gruppen `dev` und `docs` (`[tool.uv] default-groups`), `neurogrid` editierbar
  (`direct_url.json`: `"editable": true`) über hatchling 1.32.4.
- `uv lock --check --offline` → „Resolved 103 packages“, Exit 0 [G, Stand 19bd93c]. (Bis P4 waren es 84 Pakete.)
- `.venv\Scripts\neurogrid.exe --help` zeigt die sechs Befehle (Anhang A).
- Nach jeder Änderung an `uv.lock` (z. B. P5-Merge) alle drei Umgebungen neu synchronisieren.

**Hilfsumgebungen**, die Werkzeuge selbst anlegen (nie von Hand):
- `.local/licenses/venv-runtime`, `venv-dev`, `venv-docs` – `tools/licenses.py` (aus `uv export`, A-86)
- Worktree-Umgebungen `<worktree>\.venv` – je Worktree `uv sync --locked --no-build` (3.5)

### 1.5 Umgebungsvariablen

Es gibt **keine Geheimnisse** im Repository. `.env.example` listet alle Variablen von NeuroGrid, seinen Werkzeugen
und Workflows mit leerem Wert; Hilfsvariablen der Shell (`UV_PROJECT_ENVIRONMENT`, `PYTHONIOENCODING`,
`PYTHONWARNDEFAULTENCODING`) stehen nicht darin [G]. `.env` ist
git-ignoriert, und nichts liest eine `.env` selbst (Variablen in der Shell setzen).

| Variable | Wer liest sie | Zweck |
|---|---|---|
| `NEUROGRID_LANG` | CLI | Sprache der Meldungen (`--lang` > `NEUROGRID_LANG` > Systemsprache > en; ungültig → Exit 2; A-07) |
| `NEUROGRID_PDF_BROWSER_DIR` | CLI, `install_pdf_browser.py`, Tests | Ordner der Headless Shell; nur absoluter lokaler Pfad (A-85) |
| `NEUROGRID_REQUIRE_PDF=1` | Tests | PDF-/Browser-Tests schlagen fehl statt übersprungen zu werden (CI, Schlusslauf) |
| `UV` | `tools/licenses.py` (nur die venv-Stufen; `--components` braucht kein uv), `tools/bundle.py`, Tests | Pfad zu uv, nur nötig, wenn uv nicht im PATH liegt (`shutil.which("uv")` hat Vorrang); ohne `UV` überspringen einige uv-Tests |
| `UV_PROJECT_ENVIRONMENT` | uv | Ziel-venv für 3.11/3.13 |
| `NEUROGRID_BUNDLE_CACHE` | `tools/bundle.py`, `tools/notices.py` | Download-Cache (Standard `.local/bundle-cache`, Dateien nach SHA-256 benannt) |
| `NEUROGRID_RELEASE_REPOSITORY` | `tools/bundle.py` (Sigstore-Identität im Bündel; GitHub Actions setzt stattdessen `GITHUB_REPOSITORY`) | `owner/repo` des signierenden Release-Workflows (nicht geheim). `tools/release_check.py` liest sie nicht: `--repository` hat als Standard `GITHUB_REPOSITORY` |
| `SOURCE_DATE_EPOCH` | `tools/build_docs.py`, `tools/bundle.py` | feste Zeitstempel (Standard: Commit-Zeit von HEAD) |
| `PYTHONWARNDEFAULTENCODING=1` | Python | macht fehlende `encoding=` sichtbar; pytest wandelt `EncodingWarning` aus `neurogrid` in Fehler |
| `PYTHONIOENCODING=utf-8` | Python | lokal empfohlen in Git Bash: sonst bricht die Ausgabe nicht-ASCII-Zeichen auf cp1252 ab [G] |
| `GITEE_MIRROR`, `GITEE_REPOSITORY`, `GITEE_KNOWN_HOSTS`, `GITEE_SSH_KEY`, `PYPI_API_TOKEN` | nur GitHub Actions | Spiegel und PyPI; `GITEE_SSH_KEY` ist ein Actions-Secret, nie in einer Datei |

NeuroGrid setzt intern selbst (nicht von Hand setzen): `MNE_TQDM=off`; für den Validator `DENO_NO_UPDATE_CHECK=1`,
`DENO_NO_PROMPT=1`, `DENO_DIR`, `NO_COLOR=1`, `TMP/TEMP/TMPDIR` im Arbeitsordner (A-06, A-49); für Browser und
Treiber ein minimales Umfeld ohne `NODE_OPTIONS`, `PLAYWRIGHT_*`, `PW_*` (A-85).

### 1.6 Bekannte Fallen unter Windows

1. **Worktree-Junctions.** Worktrees bekommen den Korpus als Junction (`.local\corpus` → Hauptordner). Vor
   `git worktree remove` die Junction **immer zuerst** lösen, sonst löscht git den Inhalt des Ziels:
   ```powershell
   cmd /c rmdir "<worktree>\.local\corpus"     # löst nur die Verknüpfung
   git worktree remove "<worktree>"
   ```
   In Git Bash wird `/c` umgedeutet; dort `cmd //c "rmdir <worktree>\.local\corpus"` oder PowerShell verwenden.
2. **CRLF.** `Path.write_text` erzeugt unter Windows CRLF. Werkzeuge schreiben mit `newline="\n"` oder
   `write_bytes`. `.gitattributes`: `* text=auto eol=lf`; Testdaten und Binärformate `-text`/`binary`;
   `*.cmd` CRLF, `*.sh` und `*.ps1` LF; `install.ps1` behält sein UTF-8-BOM (Windows PowerShell 5.1 liest
   BOM-lose Skripte in der ANSI-Codepage).
3. **Heredocs.** Git-Bash-Heredocs verschlucken Backslashes und brechen bei langen Skripten ab. Skripte und
   Commit-Nachrichten als Datei schreiben (`git commit -F <datei>`).
4. **Lange Pfade.** Gemessen auf Build 26200 mit `LongPathsEnabled=1`: eine `.pyd` mit eingebettetem Manifest lädt bis
   250 Zeichen Gesamtpfad, `CreateProcess` startet bis 259 [D]. Deshalb begrenzt `install.ps1` das Präfix auf
   `249 − max_relative_install_path` (heute 101 Zeichen; A-87). Worktree-Pfade unter `.claude\worktrees\wf_…`
   verlängern alles um ≈ 40 Zeichen. `git config core.longpaths` ist nicht gesetzt [G]; bisher ohne Folgen.
5. **Komma-Listen in PowerShell quoten:** `--lang "zh,en"`, `--format "html,pdf"`.
6. **Datei-Symlinks** brauchen den Entwicklermodus; die betroffenen Tests werden übersprungen (11 bis P4).
7. **`ProcessPoolExecutor`** erlaubt unter Windows höchstens 61 Prozesse; `--jobs` bis 64 wird begrenzt (A-79).
8. **uv nicht im PATH** (1.3 Schritt 3); dann brauchen `tools/licenses.py` (venv-Stufen, nicht `--components`) und
   die uv-Tests `UV`.
9. **Konsolen-Kodierung** in Git Bash: `export PYTHONIOENCODING=utf-8` vor Werkzeugläufen mit Chinesisch.
10. **Docker Desktop** ist nicht nutzbar (D-09); Linux-, Container- und strace-Prüfungen laufen nur in der CI.
11. **Debug-Log der Headless Shell:** Kindprozesse schreiben unter Windows ab Stufe INFO in `debug.log` neben
    `chrome-headless-shell.exe` (kein Schalter und keine Variable ändert das). NeuroGrid startet mit
    `--in-process-gpu` (die GPU läuft im Browserprozess) und unter Windows zusätzlich mit
    `--enable-features=CDPScreenshotNewSurface,NetworkServiceInProcess2` (auch der Netzwerkdienst läuft dort im
    Browserprozess; als Kindprozess schrieb er beim Schließen kurz nach dem Start die Warnung
    `Failed to post task ... sqlite_persistent_shared_dictionary_store.cc`). Der Wert wiederholt Playwrights
    eigenes `--enable-features` (Chromium behält nur den letzten Wert); ein `--disable-features` wird nie
    übergeben. Ein `debug.log` der Renderer stellt NeuroGrid nach dem Lauf wieder her (A-85). Unter Linux loggen
    Kindprozesse nach stderr; der Netzwerkdienst bleibt dort ein eigener Prozess. Nach Testläufen
    `install_pdf_browser.py --check` ausführen.

---

## 2 Repository von null

### 2.1 Herkunft

- **Weg A (empfohlen): vorhandenes Repository.** Sobald `<REPO_URL>` existiert: `git clone <REPO_URL> neurogrid`,
  dann `git checkout dev`. Bis dahin eine Kopie des lokalen Repositorys:
  `git clone --no-hardlinks <Projektordner> <Ziel>` (Git Bash). Die Historie enthält alles außer `.local/`.
- **Weg B: neu aufbauen.** Abschnitt 3 und 4 beschreiben, in welcher Reihenfolge was gebaut wurde und welche
  Entscheidungen es formten. Der Code selbst ist die Referenz; Weg B ist nur mit dem Repository als Vorlage
  realistisch.

`.local/` wird nie versioniert (A-01). Sie enthält: PRD (`.local/prd/`), Korpus, venvs 3.11/3.13, Lizenz-venvs,
Logs und Messungen (`.local/perf/`), Review-Material. Nach einem Klon fehlt sie und wird mit den Schritten in 1.4,
4.7.3 und 6 neu befüllt; PRD und Normtexte legt der Projektverantwortliche selbst ab.

### 2.2 Zweige und Ablauf in git

- `main`: nur der erste Doku-Commit `75e05a6`; Releases kommen später von `main` (Release-Gate).
- `dev`: Arbeitszweig (D-07, D-09). Es gibt **keinen Remote** [G]; gepusht wird erst nach Freigabe.
- Bereichszweige je Phase (`p4-*`, `p5-*`) in eigenen Worktrees, nach dem Merge gelöscht (3.5).
- Anlage aus dem Nichts [D: Reflog „checkout: moving from main to dev“]:
  ```bash
  git init -b main neurogrid && cd neurogrid
  # Phase-0/1-Dokumente anlegen, committen
  git checkout -b dev
  ```

### 2.3 Oberste Ebene

| Eintrag | Rolle |
|---|---|
| `pyproject.toml`, `uv.lock` | Projekt, exakte Pins, Lock (2.5, 2.6) |
| `.python-version` | `3.12` |
| `.gitattributes`, `.gitignore` | Zeilenenden (1.6), ignorierte Pfade (`.local/`, `.venv/`, Caches, `.coverage*`, `site/`, `dist/`, `.env`) |
| `.env.example` | alle Umgebungsvariablen, leer (1.5); ein Test vergleicht Code und Workflows damit |
| `LICENSE`, `NOTICE`, `LICENSES/` | Apache-2.0, Lizenzhinweis, Lizenztexte (Apache-2.0, OFL-1.1; CC-BY-4.0 fehlt noch) |
| `REUSE.toml` | Lizenz je Pfad (2.7) |
| `THIRD_PARTY_NOTICES.txt` | erzeugt von `tools/notices.py` (A-86) |
| `README.md`, `DATA_SOURCES.md` | Kurzbeschreibung zh/en; Herkunft von Fixtures und Korpus |
| `mkdocs.yml`, `docs/en`, `docs/zh`, `docs/_data`, `docs/assets` | Nutzerdoku (A-86) |
| `docs/umsetzung/` | Matrix, Konzept, Entscheidungen, Fortschritt, diese Anleitung (Deutsch, nicht Teil der Website) |
| `license-gate/` | `allowlist.txt`, `exceptions.txt`, `components.toml`, `known_missing.toml`, `network_baseline.json` |
| `packaging/` | Installer (`install.cmd`, `install.ps1`, `install.sh`), `README.bundle.txt`, `release-notes.md`, `bundle_lock.json`, `ci/*` (Reinraum, strace) |
| `.github/workflows/` | `ci.yml`, `offline.yml`, `corpus.yml`, `docs.yml`, `release.yml`, `publish-pypi.yml`, `mirror-gitee.yml` |
| `src/neurogrid/` | Paket (2.4) |
| `tests/` | Tests und Fixtures |
| `tools/` | Werkzeuge außerhalb des Pakets (Abschnitt 5) |

Umfang heute [G]: 413 versionierte Dateien; 19 738 Zeilen Python in `src`, 38 199 in `tests`; 32 Fixture-Ordner.

### 2.4 Paketstruktur `src/neurogrid`

| Teil | Inhalt | Phase |
|---|---|---|
| `cli.py`, `__main__.py` | Typer-App: `scan`, `convert`, `check`, `report`, `manifest`, `verify`; `--lang`, `--debug`; eigene Hilfe zh/en (NG-N06, A-86); Netzwerkschutz | P1, P2, P4, P5 |
| `config.py`, `pipeline.py`, `metadata.py`, `convert.py`, `validator.py` | Konfiguration (strikt), Abläufe, Metadaten mit Herkunft (A-04), BIDS-Konvertierung (A-05), Validator als abgeschotteter deno-Prozess (A-06) | P1, P2 |
| `kernel/` | Regelmotor, Befunde, kanonisches JSON (A-61), Matcher (A-14), i18n, Netzwerkschutz (A-49), Provenienz, Nachweise, Sicherheit (A-52..A-54), HTML-Rendering; ab P5 `fonts.py`, `pdf.py`, `pdf_linux_packages.json`. Importgrenze: nur Standardbibliothek, Pydantic, Jinja2, PyYAML, fontTools, Playwright, pypdf; `mypy --strict` (A-23, A-85) | P1, P4, P5 |
| `model/` | Pydantic-Datenmodell (DM-01..DM-10) und `results.json` | P1 ff. |
| `io/` | Adapter EDF/BDF, BrainVision, EEGLAB, FIF, BIDS; Discovery; Annotationen, participants, splits, Provenienz | P1, P2, P4 |
| `checks/` | Prüfer M01–M13, BIDS, Nachweise („Prüfer messen, sie entscheiden nie“, ARC-02) | P1–P4 |
| `quality/` | Signalmetriken M06–M09, Streaming, Stichprobe, Prozesspool | P3, D-14 |
| `report/` | `render.py`, `tables.py`, `charts.py`, `glyphs.py`, `output.py`, `texts.py`, Vorlage, i18n zh/en/de, Validator-Texte, Wortlisten, Schriften | P1, P5 |
| `rulepacks/` | `core.yaml` (0.1.1), `bids.yaml`, `gxdsl008.yaml`, `calibration/core.json` | P1–P5 |
| `schemas/` | JSON-Schemas (erzeugt): results, scan, config, rulepack, evidence, manifest | P1, P4 |

### 2.5 `pyproject.toml` (Stand 584b7d2)

- `[build-system]`: `hatchling==1.32.4`. Version dynamisch aus `src/neurogrid/__init__.py` (`0.1.0rc1`).
- `[project]`: `requires-python = ">=3.11,<3.14"` (A-42), `license = "Apache-2.0 AND OFL-1.1"`,
  `license-files = ["LICENSE", "NOTICE", "src/neurogrid/report/fonts/OFL.txt"]`, Autor laut A-38.
- **Laufzeit, alle exakt gepinnt (A-48):** autoreject 0.5.1, bids-validator-deno 3.0.2, deno 2.9.7, edfio 0.4.18,
  fonttools 4.66.1, h5py 3.16.0, jinja2 3.1.6, matplotlib 3.11.2, mne 1.13.2, mne-bids 0.20.0,
  mne-icalabel[onnx] 0.10.0, numpy 2.4.6, onnxruntime 1.31.0, playwright 1.63.0, pybv 0.8.1, pydantic 2.14.0,
  pymatreader 1.3.2, pypdf 6.21.2, pyprep 0.9.0, python-picard 0.8.2, pyyaml 6.0.3, scikit-learn 1.9.1,
  scipy 1.17.1, threadpoolctl 3.7.0, typer 0.27.3.
- `[project.scripts]`: `neurogrid = "neurogrid.cli:main"`.
- `[dependency-groups]`:
  - `dev`: jsonschema 4.26.0, mypy 2.4.0, pip-licenses 5.5.5, psutil 7.2.2, pytest 9.1.1, pytest-cov 7.1.0,
    ruff 0.17.0, types-PyYAML 6.0.12.20260906
  - `docs`: mkdocs 1.6.1, mkdocs-material 9.7.7, mkdocs-static-i18n 1.3.1, pymdown-extensions 12.3
- Wheel `packages = ["src/neurogrid"]`; sdist mit `src/neurogrid`, `pyproject.toml`, LICENSE, NOTICE, README.md,
  LICENSES, REUSE.toml, THIRD_PARTY_NOTICES.txt, DATA_SOURCES.md (TECH-10, CON-05).
- `[tool.uv]`: `no-build = true` (nur Wheels), `default-groups = ["dev", "docs"]`, `required-environments` Windows
  AMD64 und Linux x86_64.
- `[tool.ruff]`: Zeilenlänge 110, `py311`, Regeln `E F W I UP B PTH PLW1514 S506 S602 S604 S605` (Preview nur
  explizit), `tests/**` ohne `S`.
- `[tool.mypy]`: `python_version = "3.11"`, Plugin `pydantic.mypy`; `--strict` nur für den Kern auf der
  Kommandozeile.
- `[tool.pytest.ini_options]`: `addopts = --strict-markers -m "not corpus and not perf and not bundle" -p no:cacheprovider`;
  Marker `bundle`, `corpus`, `perf`, `browser`, `pdf`; `filterwarnings = error::EncodingWarning:neurogrid`.
- `[tool.coverage.run]`: `branch`, `patch = ["subprocess"]`, `concurrency = ["thread", "greenlet"]` (Playwright).

### 2.6 Abhängigkeitsgruppen und `uv.lock`

- `uv.lock`: `version = 1`, `revision = 5`, 103 Pakete (Stand 584b7d2) [G]. Einzige Versionsgabelung bis P4:
  contourpy 1.3.3 (3.11) / 1.4.0 (≥ 3.12).
- Laufzeitmenge für Lizenz-Gate, Notices, Bündel und Netzwerk-Scan **immer**:
  `uv export --frozen --no-default-groups --no-emit-project` (A-86). Stand 584b7d2: Laufzeitexport 66 Pakete; ein
  bloßes `--no-dev` ergibt 82 Pakete (mit den Doku-Werkzeugen) [G]. Die Werte 62/78 wurden im docs-Bereich gemessen,
  vor dem pdf-Merge (playwright, pypdf, greenlet, pyee) [D]. Ein Test vergleicht den echten Export. Nachzählen
  (Git Bash):
  ```bash
  uv export --frozen --no-default-groups --no-emit-project --no-hashes --offline | grep -c '^[a-z0-9]'   # 66
  uv export --frozen --no-dev --no-emit-project --no-hashes --offline | grep -c '^[a-z0-9]'                # 82
  ```
- Neue Abhängigkeit hinzufügen: Version prüfen (PyPI, Lizenz in der Allowlist), in `pyproject.toml` exakt pinnen,
  dann
  ```bash
  uv lock
  uv sync --locked --no-build
  uv run --no-sync python tools/licenses.py
  ```
  Vor P3 wurde eine Sicherung von `pyproject.toml`/`uv.lock` unter `.local/` angelegt; das ist empfehlenswert.

### 2.7 Lizenzen, REUSE und Lizenz-Gate

- **Lizenzen (D-05, D-08, A-38):** Code Apache-2.0; Doku, `README.md`, `DATA_SOURCES.md`, `THIRD_PARTY_NOTICES.txt`
  und `tests/fixtures/synthetic/**` CC-BY-4.0; `src/neurogrid/report/fonts/*.ttf` und `OFL.txt` OFL-1.1;
  `fonts.json` Apache-2.0.
- **`REUSE.toml`:** Tabellen mit `precedence = "aggregate"`, die letzte passende gewinnt; Schriften mit
  `override`. Geprüft vom eigenen Test `tests/docs/test_licensing.py` (das REUSE-Werkzeug selbst ist GPL-3.0 und
  keine Abhängigkeit). `LICENSES/CC-BY-4.0.txt` fehlt noch (D-15: Download freigegeben).
- **Lizenz-Gate (`tools/licenses.py`, NG-N07):** Stufe 1 `pip-licenses --allow-only` gegen
  `license-gate/allowlist.txt` mit versionsgebundenen Ausnahmen (`pybv:0.8.1`, `pyprep:0.9.0` in `exceptions.txt`);
  Stufe 2 sperrt jede Lizenz mit „GPL“ (`--partial-match`). Getrennt für `runtime`, `dev`, `docs`. Dazu
  `--components`: statische Prüfung jeder nativen Datei der gelockten Wheels beider Zielplattformen und der
  Bündelteile gegen `license-gate/components.toml` (D-08).
- Der Ordner hieß bis P4 `licenses/`; er wurde in P5 wegen der Kollision mit `LICENSES/` auf
  groß-/kleinschreibungsunabhängigen Windows-Laufwerken in `license-gate/` umbenannt (A-86).

### 2.8 Konfigurations- und Datendateien mit Rolle

| Datei | Rolle | Erzeugt von / gepflegt |
|---|---|---|
| `tests/fixtures/documented.toml` | dokumentiert BIDS-Pflichtfelder für Roh-Fixtures (`[metadata.defaults]`, `[convert] pattern`) | von Hand |
| `tools/corpus_spec.json` | welche Dateien je Korpus-Datensatz | von Hand |
| `tools/corpus_lock.json` | 297 Dateien mit URL, Größe, SHA-256, Herkunft des Hashes | einmalig (6.4) |
| `src/neurogrid/rulepacks/calibration/core.json` | Kalibrierprotokoll | `tools/calibrate.py` |
| `src/neurogrid/io/montage_names.py` | eingefrorene Elektrodennamen | `tools/gen_montage_names.py` |
| `src/neurogrid/schemas/*.schema.json` | öffentliche Schemas | `tools/gen_schemas.py` |
| `tests/fixtures/synthetic/**` | 32 Fixture-Ordner | `tools/gen_fixtures.py` |
| `src/neurogrid/report/fonts/*` + `fonts.json` | statische Noto-Sans-SC-Schnitte und Herkunft | `tools/build_fonts.py` |
| `src/neurogrid/kernel/pdf_linux_packages.json` | apt-Pakete der Headless Shell (Debian 12, Ubuntu 22.04/24.04) | `tools/linux_pdf_packages.py --write` |
| `docs/{en,zh}/reference/*.md`, generierte Blöcke in `metrics.md` | Registry, Regeln, Schwellen | `tools/gen_docs.py` |
| `docs/_data/*.yaml` | Bezeichnungen und Beschreibungen der Doku | von Hand |
| `mkdocs.yml`, `tools/mkdocs_hooks.py` | Seitenstruktur, Suche, Hooks | von Hand |
| `THIRD_PARTY_NOTICES.txt` | Drittanbieter-Hinweise | `tools/notices.py` |
| `license-gate/components.toml` | geprüfte native/nicht-Python-Komponenten | von Hand, geprüft |
| `license-gate/known_missing.toml` | fehlende Lizenztexte (6 Einträge, sperren das Release) | von Hand |
| `license-gate/network_baseline.json` | geprüfte Netzwerk-Fundstellen der Laufzeitpakete | `tools/scan_runtime_network.py --draft`, dann von Hand |
| `packaging/bundle_lock.json` | Interpreter und uv des Bündels (URL, Größe, SHA-256), Entfernung `_dbm` | `tools/bundle.py lock` |

---

## 3 Arbeitsweise

### 3.1 Grundsätze

- Rangfolge bei Konflikten: Antworten des Projektverantwortlichen > PRD > bestehender Code > Annahmen.
- Die PRD liegt nur lokal; öffentliche Dateien zitieren sie nicht und sagen „Projektverantwortlicher“ (A-01).
- Nachweise statt Behauptungen: eine Matrixzeile wird erst „erfüllt“, wenn ausgeführt und geprüft. Was lokal nicht
  geht, steht als „nicht verifiziert“ in Matrix und FORTSCHRITT.
- Bei jedem Sitzungsneustart zuerst FORTSCHRITT, ANFORDERUNGEN, ENTSCHEIDUNGEN lesen.

### 3.2 Anforderungsmatrix → Konzept → Phasen mit STOPPs

1. **PRD als Text** (Phase 0):
   ```bash
   pdftotext -layout -enc UTF-8 .local/prd/PRD-1-NeuroGrid.pdf .local/prd/PRD-1-NeuroGrid.layout.txt
   pdftotext -enc UTF-8 .local/prd/PRD-1-NeuroGrid.pdf .local/prd/PRD-1-NeuroGrid.raw.txt
   ```
   Beide Ausgaben sind byte-gleich mit den vorhandenen Dateien [G]. `.raw.txt` ist der Standardmodus, nicht `-raw`.
   Die Tabellen der Abschnitte 12/13 sind in `.raw.txt` besser lesbar. Wie das Architekturbild
   `architektur-s8.png` entstand, ist nicht protokolliert [NV].
2. **Matrix** `ANFORDERUNGEN.md`: je Anforderung ID, Abnahmekriterium, Fundstelle (`§Abschnitt S.Seite`),
   Zielversion, Status, Klärung (D-/A-), Nachweis. 166 Zeilen. Gegenprüfung durch eine zweite, unabhängige
   Extraktion.
3. **Lückenanalyse**: Blocker als Fragen (F1–F7, später E1–E5, STOPP R4) an den Projektverantwortlichen; der Rest
   als nummerierte Annahmen A-xx, die gelten, bis er widerspricht.
4. **Machbarkeits-Prototypen** S1–S5 vor dem Konzept (Wegwerfcode; Ergebnisse in KONZEPT 8).
5. **Konzept** `KONZEPT.md` mit Phasenplan P1–P12: je Phase „schließt ab“ / „trägt bei zu“ und DoD.
   `tools/check_matrix_coverage.py` erzwingt genau eine abschließende Phase je Zeile.
6. **STOPPs:** STOPP 2 (Konzeptfreigabe, D-08..D-13), technische STOPPs bei verfehlter Abnahme (R4 → D-14),
   STOPP G1 nach P5, STOPP G2 nach v0.2, Go/No-Go G-A/G-B/G-C vor normabhängigen Phasen. Bis G1 gilt
   **Freigabemodus A**: selbstständig bis zum STOPP, Lücken als Annahmen, für G1 vorgemerkt.

### 3.3 Entscheidungslog

- `ENTSCHEIDUNGEN.md`: geprüfte Fakten, D-01..D-15 (Entscheidungen des Projektverantwortlichen), A-00..A-83
  (Annahmen; je Phase ein Block „Annahmen aus der Umsetzung von Px“).
- P5 bringt A-84 (Bericht), A-85 (PDF), A-86 (Doku, Meldungen, Notices, Lizenzen), A-87 (Bündel, Signatur,
  Workflows), A-88 (Abnahme). **Stand 584b7d2: noch nicht eingetragen**; der Inhalt steht in den verbindlichen
  Vorgaben des Leads und wird vor G1 eingetragen.

### 3.4 Orchestrierungsmuster (ab P4, voll ausgebildet in P5)

| Schritt | Was geschieht | Ergebnis |
|---|---|---|
| 1 Bereichsspezifikationen | je Bereich eine Spezifikation (Anforderungen, Entwurf, Dateien, neue Abhängigkeiten, Downloads, Tests, offene Fragen, Risiken, Schnittstellen, i18n-Schlüssel, Proben) | P4: 4 Bereiche; P5: report, pdf, docs, bundle, acceptance |
| 2 Kritiker | ein unabhängiger Prüfer liest alle Spezifikationen: Korrekturen, Fehlendes, Widersprüche, Fragen an den Projektverantwortlichen | P4: Lücken G1–G16, Widersprüche X1–X18 |
| 3 Lead-Entscheidungen | verbindliche Vorgaben im Freigabemodus A; „wo diese Datei und eine Spezifikation abweichen, gilt diese Datei“ | P4: C1–C11 → A-80..A-83; P5: B1–B6 → A-84..A-88 |
| 4 Gemeinsamer Unterbau | was alle Bereiche brauchen, vorab auf `dev` | P4: `CheckContext` (`4253a65`) |
| 5 Paralleler Bau | je Bereich ein Zweig in eigenem Worktree; jeder liefert Code, Tests, `decisions_for_docs`, `facts_for_build_guide`, Lücken | P4: `p4-*`; P5: `p5-report`, `p5-pdf`, `p5-docs`, `p5-bundle` |
| 6 Unabhängige Verifikation | ein anderer Prüfer prüft jeden Bereich gegen Spezifikation und Vorgaben, findet neue Probleme | P5: report 15/7, pdf 4/8, docs 7/5, bundle 9/13 (Prüfpunkte/neue Probleme) [D] |
| 7 Reparatur | Reparatur-Commit je Bereich | P5: `133bb94`, `7c99a82`, `9331600`, `2d41f44` |
| 8 Merge | in fester Reihenfolge auf `dev`, danach `uv lock`, Generatoren neu | P5: report, docs, pdf, bundle |
| 9 Adversariales Review | mehrere Prüfrichtungen; jeder Befund wird von einem zweiten Prüfer zu widerlegen versucht (bestätigt / strittig / beabsichtigt / widerlegt), schwere doppelt | P4: 57 Befunde |
| 10 Fixes | Fix-Zweige je Bereich, je Befund ein Regressionstest, Nachprüfung, Reparaturrunde | P4: `p4-fix-*` |
| 11 Gegenprüfung | gemergter Stand auf Rückfälle und neue Fehler aus dem Zusammenspiel | P4: `p4-fix2-*` |
| 12 Doku und Commit | Matrix, ENTSCHEIDUNGEN, KONZEPT, FORTSCHRITT; Commit mit Anforderungs-IDs | P4: `e68e33e` |

Seit D-15 (Tempo): volle Testsuite nur nach dem Merge; ein Review je Phase mit vier Prüfrichtungen; diese Anleitung
entsteht parallel.

### 3.5 Git-Worktrees konkret

PowerShell, je Bereich:
```powershell
git worktree add ".claude\worktrees\<name>" -b p5-<bereich> dev
cd ".claude\worktrees\<name>"
uv sync --locked --no-build
# nur wenn Korpus-Tests laufen sollen: .local/ ist git-ignoriert und fehlt im neuen Worktree, also zuerst anlegen
New-Item -ItemType Directory -Force ".local" | Out-Null
cmd /c mklink /J ".local\corpus" "<Projektordner>\.local\corpus"
# ... bauen, testen, committen ...
cd "<Projektordner>"
git merge --no-ff p5-<bereich>          # Merge-Commits heißen "Merge branch 'p5-<bereich>' into dev"
cmd /c rmdir ".claude\worktrees\<name>\.local\corpus"   # Junction lösen (1.6 Punkt 1)
git worktree remove ".claude\worktrees\<name>"
git branch -d p5-<bereich>
```
`.claude/worktrees/` ist nicht in `.gitignore`, bleibt aber ungetrackt. Probe-Merges ohne Risiko: in einem
Wegwerf-Klon (`git clone --no-hardlinks --no-checkout <Projektordner> trial`).

### 3.6 Was davon von Hand geht

- **Vollständig von Hand:** Matrix, Konzept, Entscheidungslog, jede Bauphase, alle Prüfbefehle, Commit-Form. Die
  Werkzeuge sind gewöhnliche Python-Skripte.
- **Nur mit Ersatz:** Parallelität (stattdessen Bereiche nacheinander in eigenen Zweigen bauen) und
  Unabhängigkeit von Verifikation und Review. Ersatz: Spezifikation und Vorgaben schriftlich festhalten, jeden
  Bereich zeitversetzt gegen eine Prüfliste je Prüfrichtung durchgehen, jeden Befund mit einem eigenen
  Reproduktionsskript belegen, bevor er behoben wird, und nach dem Merge die Gegenprüfung (Schritt 11) wiederholen.
- Zeitbedarf ist nicht protokolliert [NV]; die volle Suite dauert je Lauf 13–18 min.

### 3.7 Commit-Form und Rückverfolgbarkeit (TECH-12, A-43)

- Präfix `feat:` / `fix:` / `docs:` / `chore:`, Anforderungs-IDs in Klammern im Betreff, Text als Stichpunktliste,
  Schlusszeile `Co-Authored-By: …` (wo ein Werkzeug mitgeschrieben hat).
- Vor jedem Commit (PowerShell):
  ```powershell
  .\.venv\Scripts\python.exe tools\check_commit_ids.py --message-file <datei>
  git commit -F <datei>
  ```
- Jeder datierte FORTSCHRITT-Eintrag nennt IDs. Prüfung des ganzen Stands: `tools/check_commit_ids.py` →
  „33 commit(s) and 5 phase entr(y/ies) checked, 0 problem(s)“ [G, 19bd93c].
- Phasenbericht in FORTSCHRITT: Abgeschlossen, Beigetragen zu, Gebaut, Review, Ergebnisse, Nicht verifiziert,
  Für STOPP G1 vorgemerkt.

---

## 4 Phase für Phase

### 4.0 Prüfbefehle jeder Phase (DoD, KONZEPT 6)

**Interpreter-Variable.** Jeder PowerShell-Block dieser Anleitung, der `& $PY …` enthält, setzt zuerst
```powershell
$PY = ".\.venv\Scripts\python.exe"            # 3.12; für 3.11: ".\.local\venv3.11\Scripts\python.exe", für 3.13: ".\.local\venv3.13\Scripts\python.exe"
```
und jeder Git-Bash-Block, der `"$PY" …` enthält,
```bash
PY=.venv/Scripts/python.exe                   # bzw. .local/venv3.11/Scripts/python.exe, .local/venv3.13/Scripts/python.exe
```
Ohne diese Zuweisung ist `$PY` leer und der Aufruf bricht ab. Die Zuweisung gilt nur in der laufenden Shell; in
einer neuen Shell erneut setzen.

PowerShell:

```powershell
$PY = ".\.venv\Scripts\python.exe"
uv lock --check --offline                                 # Lock aktuell (TECH-02)
.\.venv\Scripts\ruff.exe check .                          # Lint
.\.venv\Scripts\ruff.exe format --check .                 # Format
.\.venv\Scripts\mypy.exe --strict src\neurogrid\kernel    # Kern streng (A-23)
.\.venv\Scripts\mypy.exe src\neurogrid tools              # alles
& $PY -m pytest -q                                        # Standardlauf (ohne corpus, perf, bundle)
& $PY -m pytest -q --cov=neurogrid --cov-report=json:.local/coverage.json
& $PY tools\coverage_gates.py .local\coverage.json        # Kern >= 90 %, Prüfer >= 80 % (NG-N08)
& $PY tools\licenses.py                                   # braucht $env:UV
& $PY tools\gen_fixtures.py --check
& $PY tools\gen_schemas.py --check
& $PY tools\gen_montage_names.py --check
& $PY tools\calibrate.py --check
& $PY tools\gen_docs.py --check                           # ab P5
& $PY tools\check_matrix_coverage.py
& $PY tools\check_commit_ids.py
```

**Durchstich und Determinismus** (A-11, NG-N03), Git Bash:
```bash
cp -r tests/fixtures/synthetic/edf_ok /tmp/edf_ok
.venv/Scripts/neurogrid.exe check /tmp/edf_ok --config tests/fixtures/documented.toml --as-of 2026-10-11 --out /tmp/a.json
.venv/Scripts/neurogrid.exe check /tmp/edf_ok --config tests/fixtures/documented.toml --as-of 2026-10-11 --out /tmp/b.json
cmp /tmp/a.json /tmp/b.json && echo identisch
.venv/Scripts/neurogrid.exe report /tmp/a.json --lang zh,en --format html,pdf --out /tmp/rep
```
PowerShell-Vergleich: `fc.exe /b a.json b.json`. Ergebnis heute [G, 19bd93c]: `check` Exit 0, „0 error(s),
11 warning(s)“, 4,2 s; zwei Läufe byte-gleich; `report` Exit 0 in 17,6 s mit `report.zh.html` 339 846 B,
`report.en.html` 110 080 B, `report.zh.pdf` 167 350 B, `report.en.pdf` 93 829 B; nicht vorhandener Pfad → Exit 2.

**Plattformvergleich:** derselbe `check` mit allen drei venvs; die `results.json` sind gleich bis auf den Block
`environment` (und `tool.python`). Das Vergleichsskript lag nur im Scratchpad [NV]; die CI bildet es im Job
`compare` nach.

### 4.1 Phasen 0–2: Planung (2026-10-11)

**Phase 0/1** (Commit `75e05a6` auf `main`) [D]:
- PRD lesen (3.2 Schritt 1); Matrix 166 Zeilen (151 Anforderungen, 9 Nicht-Ziele, 6 Geschäftsaufgaben),
  gegengeprüft (272 Einzelpunkte).
- Lückenanalyse: 50 Punkte, 7 Blocker-Fragen F1–F7, 44 Annahmen A-00..A-43.
- Externe Fakten geprüft (Abschnitt „Geprüfte Fakten“ in ENTSCHEIDUNGEN).

**Phase 2** (`git checkout -b dev` direkt nach `75e05a6`, dann Commit `d81ad0c` auf `dev`) [G: Reflog]:
- F1–F7 → D-01..D-07 (Umfang, Normtexte, englische Bezeichner, Laufzeit, Lizenzen und Python 3.11–3.13,
  Downloads, Repository).
- Umgebung nach 1.3 Schritt 3/4; Prototyp-venv mit dem geplanten Stack.
- Prototypen: S1 Validator/BIDS, S2 Laufzeit 1 GB (89 s), S3 PDF/CJK, S4 Abhängigkeiten/Lizenzen, S5 Testkorpus
  (1,06 GB). **Skripte nicht erhalten** [NV]; Ergebnisse in KONZEPT 8. Für den Nachbau nicht nötig.
- `KONZEPT.md`; drei unabhängige Prüfer (PRD-Treue, Technik/Phasen, Regulatorik/Datenschutz/Lizenzen): 82 Befunde
  (0 Blocker, 43 wesentlich, 39 klein), eingearbeitet.
- `tools/check_matrix_coverage.py` → 166/166.
- **STOPP 2**: Freigabe; E1–E5 → D-08 (Binärteile, Headless Shell nicht im Bündel), D-09 (CI/Linux erst mit
  Repo-URL), D-10 (Zusätze a–h), D-11 (Korpus ohne EEGDash), D-12 (NG-N02-Messung), D-13 (Konzeptfreigabe).

Prüfung heute [G]: `check_matrix_coverage.py` → „Matrix-IDs: 166 Phasen: 12 mit genau einer abschließenden
Phase: 166“ (P5 schließt 36 ab, trägt zu 3 bei).

### 4.2 P1 – Gerüst und Durchstich (Commit `a44d592`, 2026-10-11)

Matrix: schließt TECH-02, TECH-03, TECH-04, TECH-09, TECH-12, ARC-02, ARC-03, LIB-10, DM-01..DM-07, DM-10, RP-01,
RP-04, RP-12, V-08 ab (TECH-11 wartet auf CI).

**Gebaut** (Reihenfolge innerhalb der Phase nicht protokolliert [NV]; sinnvolle Reihenfolge):
1. Repository nach PRD §13: `.gitattributes`, `.python-version`, LICENSE, NOTICE, README, REUSE.toml,
   `pyproject.toml` (exakte Pins, `no-build`), `uv lock`, Lizenz-Allowlist und -Ausnahmen, `ci.yml`.
2. Kern `kernel/`: `rules.py`, `engine.py` (Schwellen mit Herkunft, Ausnahmen über stabile Pfad-Identitäten,
   Ampel, Abdeckung, Exitcodes), `findings.py`, `canonical.py`, `glob.py`, `i18n.py`, `safety.py`, `netguard.py`,
   `provenance.py` (Hashing), `evidence.py` (Modell), `report.py`, `errors.py`.
3. `config.py`, `io/base.py`, `io/edf.py`, `io/channels.py`, `io/discover.py`, `model/`, `pipeline.py`,
   `checks/context.py`, `checks/registry.py`, `checks/structure.py` (M01), `checks/signal.py` (M03).
4. Paket `core` mit M01/M03; `scan`, `check`, `report` (HTML zh/en); Schemas.
5. Werkzeuge `check_commit_ids.py`, `coverage_gates.py`, `gen_fixtures.py`, `gen_schemas.py`, `licenses.py`.
6. Tests: CLI, Pipeline, Bericht, eingebaute Regeln (Positiv/Negativ je Regel), Überschreibbarkeit der Schwellen
   (MET-02), Unit-Tests; 8 Fixture-Ordner.

Generator-Befehle (Git Bash):
```bash
PY=.venv/Scripts/python.exe
"$PY" tools/gen_fixtures.py
"$PY" tools/gen_schemas.py
uv lock
uv sync --locked --no-build
```

**Prägende Entscheidungen:** D-03, D-05, D-07/D-09, A-02, A-07..A-16, A-23, A-38, A-42, A-48, A-49, A-51..A-54, A-57,
A-61; aus Umsetzung und Review A-62..A-76.

**Review:** drei Durchgänge mit Gegenprüfung (Korrektheit, Sicherheit/Datenschutz, DoD-Treue); alle bestätigten
Befunde behoben; Praxistest auf PSG-IPA und ds003775 [D].

**Ergebnis [D]:** pytest 347 bestanden, 4 übersprungen unter 3.11/3.12/3.13; ruff, format, `mypy --strict` Kern
sauber; Abdeckung Kern 97,4 %, Prüfer 95,2 %; Lizenz-Gate grün; Fixtures und Schemas reproduzierbar; zwei `check`
byte-gleich; Rauchtest PowerShell 5.1 Exit 0/1/2/0 (genaue Befehle nicht protokolliert [NV]; der CI-Job
`powershell51` bildet ihn nach).

### 4.3 P2 – Formate und BIDS (Commit `fbcdc51`, 2026-10-20)

Matrix: schließt NG-F01, NG-F02, NG-F05, NG-F06, M01–M05, CLI-01, CLI-02, RP-09, LIB-02, LIB-03, LIB-08, LIB-09,
CON-03 ab.

**Gebaut:**
- Adapter BrainVision, EEGLAB (MAT v5/v7.3), FIF (inkl. Split), BDF; EDF+D lesbar; Discovery mit Begleitdateien,
  verwaisten und nicht unterstützten Dateien (A-77).
- `io/bids.py`, `metadata.py` (Vererbungsprinzip, Herkunft je Feld, A-04), `io/identifying.py`,
  `io/montage_names.py`.
- Prüfungen M02, M04, M05, M03-03 → `core` 17 Regeln; Paket `bids` (BIDS-STO-001..003) mit `validator.py`; eigene
  Texte zh/en/de für 200 Validator-Codes.
- `convert --to bids` über MNE-BIDS, `--strip-identifying-headers`, Validatorlauf auf der Ausgabe.
- Korpus: `tools/corpus.py`, `corpus_spec.json`, `corpus_lock.json`, `DATA_SOURCES.md`, `tests/corpus`.
- 13 neue Fixture-Ordner, `tests/fixtures/documented.toml`.

Befehle (Git Bash):
```bash
PY=.venv/Scripts/python.exe
"$PY" tools/gen_montage_names.py   # aus MNE 1.13.2, colin27_1020/colin27_1005
"$PY" tools/gen_fixtures.py
"$PY" tools/corpus.py fetch        # Abschnitt 6
```

**Prägende Entscheidungen:** A-03..A-06, A-12, A-18, A-24, A-29, A-46, A-52, A-53, D-11; neu A-77, A-78.

**Review:** je Testmodul ein Prüfer mit Gegenprüfung (≈ 20 Fehler), dann fünf Prüfrichtungen (48 bestätigt,
9 verworfen), behoben in fünf Gruppen; Golden-Liste echter Metadatenfehler auf dem Korpus bestätigt [D].

**Ergebnis [D]:** pytest 1449 bestanden, 7 übersprungen (3 Pythons); Korpus 20 bestanden; je Format eine Aufnahme mit
und ohne `--strip-identifying-headers` ohne Validator-Fehler; Abdeckung Kern 97,3 %, Prüfer 97,0 %; zwei `convert`
dateigleich; Rauchtest PowerShell 5.1 Exit 0/1/1/0/0/0/2/0 (Befehle [NV]).

### 4.4 P3 – Signalqualität (Commit `6445b62`, 2026-10-21)

Matrix: schließt NG-F07, M06–M09, MET-01, NG-N02 (nach D-14), LIB-01, LIB-04, LIB-06, LIB-07 ab.

**Gebaut:** Paket `quality/` (eigener EDF/BDF-Blockleser über Speicherabbild; MNE `preload=False` in 60-s-Blöcken
für die übrigen Formate; Stream M07/M08 und Signal-Hash `NG-SIGHASH-v1`; Stichprobe 10 × 60 s mit pyprep (M06),
autoreject (M09a), picard + ICLabel über onnxruntime (M09b)); `checks/quality.py` mit sieben Regeln; `[quality]` in
der Konfiguration; `check --jobs`; Werkzeuge `calibrate.py`, `gen_large_edf.py`, `benchmark.py`; drei Fixtures
`edf_quality_*`. Neue Abhängigkeiten: pyprep, autoreject, mne-icalabel[onnx], onnxruntime, python-picard,
scikit-learn, threadpoolctl.

**Reihenfolge** [R aus Dateizeiten]: Sicherung von pyproject/Lock → Probeläufe → kleine 64-Kanal-Probedatei →
Kalibrierung v2/v3 → erste Tests → Korpuslauf → Testbereiche (fünf Schreiber, zwei Gegenprüfer) → Profil →
1-GB-Dateien → Stream auf Threads → Benchmark → Review → Kalibrierung v4 → Schlussläufe 3.12/3.11/3.13 → Korpus →
Commit.

**Kalibrierung (MET-01, A-20, A-79):**
```powershell
$PY = ".\.venv\Scripts\python.exe"
& $PY tools\calibrate.py --root .local\corpus --jobs 4   # misst, schreibt rulepacks/calibration/core.json (lang)
& $PY tools\calibrate.py --check                        # "calibration protocol and rule pack agree" [G]
```
95. Perzentil (numpy, linear), Seed 20261011, 22 Aufnahmen, 1050 Kanäle, 5 Formate. Ergebnis: CORE-M06-01
`max_fraction` 0,30625; CORE-M07-01 `max_ratio` 0,407669; CORE-M09-01 0,305083; CORE-M09-02 0,6 [G].

**Laufzeit NG-N02 (A-50):**
```powershell
$PY = ".\.venv\Scripts\python.exe"
& $PY tools\gen_large_edf.py .local\perf\ng_n02_64ch.edf --channels 64   # optional; benchmark erzeugt selbst
& $PY tools\benchmark.py --jobs 1 --out .local\perf\benchmark.json
```
Ergebnis mit `--jobs 1` [D]: 64 Kanäle 94,2 s / 1,7 GB, 128 Kanäle 159,5 s / 2,3 GB, 256 Kanäle 294,6 s / 3,4 GB
→ Grenze 150 s nur bei 64 Kanälen → **STOPP R4**.

**Ergebnis [D]:** pytest 1722 bestanden, 7 übersprungen (3 Pythons); Korpus 28; Byte-Gleichheit `--jobs 1/4` und BLAS
1/4; Abdeckung Kern 97,3 %, Prüfer 97,4 %; Lizenz-Gate grün (pyprep als geprüfte Ausnahme).

### 4.5 D-14 – Parallelisierung einer Aufnahme (Commit `cfa6273`, 2026-10-21)

Entscheidung D-14 (STOPP R4): Optionen 1 und 2; Grenzen mit `--jobs 4`: < 150 s bis 128 Kanäle, < 300 s für 256.

**Gebaut:** eine Aufnahme zerfällt in Stream, Stichprobenvorbereitung mit M06, autoreject, ICA/ICLabel; Teile als
Aufgaben eines Prozesspools; autoreject ab 64 Kanälen mit `--jobs − 1` loky-Prozessen (Netzwerkschutz, ein
BLAS-Thread); feste Zusammensetzung → byte-gleich zu `--jobs 1`. Neues Modul `quality/workers.py`.

**Prüfung:**
```powershell
$PY = ".\.venv\Scripts\python.exe"
& $PY tools\benchmark.py --jobs 4 --out .local\perf\benchmark_final.json
```
Ergebnis [D]: 64 Kanäle 75,6 s / 1,8 GB, 128 Kanäle 126,2 s / 2,5 GB, 256 Kanäle 248,2 s / 3,7 GB; pytest 3.12:
1729 bestanden, 7 übersprungen; Abdeckung 97,3 % / 97,3 %; `--jobs 1` und `--jobs 4` byte-gleich auf der
64-Kanal-Datei [G an den gespeicherten Ergebnissen]. Review: drei Richtungen, 12 Befunde bestätigt und behoben.

### 4.6 P4 – Annotation, KI-Struktur, Provenienz, Nachweise, gxdsl008 (2026-10-21 bis 10-23)

Matrix: schließt NG-F08, NG-F09, NG-F10, NG-F12, M10–M13, MET-02, CLI-03, CLI-04, CLI-06, GX-00..GX-05, UF-04, UF-05,
RP-05 ab.

**Reihenfolge (belegt, Muster aus 3.4):**
1. Unterbau `4253a65`: `CheckContext` mit Projektwurzel, `--show-paths`, `--strict`, `as_of`, Manifest- und
   Evidence-Pfaden.
2. Spezifikationen je Bereich → Kritiker (G1–G16, X1–X18) → offene Fragen → Vorgaben C1–C11 (später A-80..A-83 und
   „Übergreifend“).
3. Paralleler Bau: `p4-evidence` (`f488b39`), `p4-ai` (`7c31804`), `p4-provenance` (`484873e`), `p4-annotation`
   (`cf3a1a9`); Merge in dieser Reihenfolge.
4. Integration `p4-int-ai` (`58510e5`: Labelquelle `annotations`, Verdeckung von `ai.splits`) und
   `p4-int-provenance` (`5d499d9`: Manifest unter `.neurogrid/`).
5. Review in sechs Richtungen: 57 Befunde (46 bestätigt, 2 strittig, 8 beabsichtigt, 1 widerlegt); Fixes in
   `p4-fix-*` mit Regressionstests, Reparaturrunde.
6. Gegenprüfung des gemergten Stands: 0 Rückfälle; 6 neue kleine Fehler + 2 Restpunkte in `p4-fix2-display`,
   `p4-fix2-readers`.
7. Abschluss-Doku `e68e33e`.

**Gebaut:** M10 (`io/annotations.py`, `checks/annotation.py`; Cohens κ, Codes, Lücken, Überlappungen), M11/M12
(`checks/ai_dataset.py`, `io/participants.py`, `io/splits.py`, `io/events.py`; Tabellenregel für kleine Zellen,
A-81), M13 (`manifest`/`verify`, `.neurogrid/manifest.json`, `--strict` über `strict_severity`), Nachweise
(`.neurogrid/evidence.yaml` mit Dokument-Hash), Paket `gxdsl008` (A-40, Klausel „unknown“), neue Schemas
`evidence`, `manifest`; 8 Fixture-Ordner.

**Ergebnis [D]:** pytest 3.11 / 3.12 / 3.13 je 2705 bestanden, 11 übersprungen, 65 abgewählt (13:34 / 16:23 mit
Abdeckung / 13:59 min); Korpus 62 bestanden in 11:42 (κ auf PSG-IPA ±0,001); Abdeckung Kern 97,1 %, Prüfer 97,2 %;
acht Fixtures mit core+bids+gxdsl008 unter drei Pythons gleich bis auf `environment`. NG-N02 mit `--jobs 4`:

| Kanäle | Laufzeit | Spitzenspeicher | Grenze (D-14) |
|---|---|---|---|
| 64 | 69,6 s | 1,8 GB | 150 s |
| 128 | 118,6 s | 2,6 GB | 150 s |
| 256 | 241,7 s | 3,6 GB | 300 s |
| 256 mit Manifest | 239,1 s | 3,7 GB | 300 s (Skript nicht erhalten [NV]) |

Exit jeweils 1, weil die synthetische EDF ohne Konfiguration CORE-M02-01 verletzt – zulässig (Kriterium: Exit 0 oder 1
unter der Grenze).

### 4.7 P5 – Bericht, PDF, Doku, Bündel (Stand 584b7d2, P5 noch nicht abgeschlossen)

#### 4.7.1 Vorgehen bis heute

| Datum | Commit | Schritt |
|---|---|---|
| bis 23.10. | – | Spezifikationen report, pdf, docs, bundle, acceptance; Kritiker; Vorgaben B1–B6 (Bericht↔PDF-Vertrag, PDF, Doku/Notices/Lizenzen, Bündel/Signatur/CI, G1-Liste, gemeinsame Dateien) |
| 23.10. 23:47 – 24.10. 00:40 | `8b9c949`, `d3f07ba`, `1dbb23e`, `73bb04b` | paralleler Bau in vier Worktrees |
| 24.10. 01:28 – 05:10 | `133bb94`, `7c99a82`, `9331600`, `2d41f44` | Reparatur nach unabhängiger Verifikation |
| 24.10. 04:03 – 16:51 | `f10e05b`, `e7e2352`, `23880d2`, `584b7d2` | Merge report → docs → pdf → bundle. `uv.lock` mit 103 Paketen entstand beim pdf-Merge `23880d2` (nach dem docs-Merge `e7e2352` waren es 99); im bundle-Merge `584b7d2` wurden nur `THIRD_PARTY_NOTICES.txt` neu erzeugt und in `pyproject.toml` der Marker `bundle` samt `addopts` ergänzt [G] |
| 26.10. | `19bd93c` | D-15 Vorabentscheidungen zu G1 |
| laufend | Zweige `p5-int-pdf`, `p5-int-pack`, `p5-acceptance` | Integration und Abnahme (nicht Teil dieses Stands) |

Gemeinsame Merge-Konfliktstellen [D]: Pytest-Marker und `addopts` in `pyproject.toml` (Vereinigung: `pdf`,
`browser`, `bundle`), `REUSE.toml`, `uv.lock` (neu erzeugen), `report/render.py` und Vorlage (Bericht-Bereich gewinnt),
Docstring von `kernel/report.py`, i18n-Tabellen (Vereinigung der Schlüsselblöcke).

#### 4.7.2 Bericht (Bereich report; A-84; NG-F13, REP-00..REP-07, POS-01, ARC-05, UF-01, UF-07)

- Eigene deterministische Inline-SVG-Grafiken in `report/charts.py` (nur Standardbibliothek; matplotlib nicht im
  Bericht – Abweichung von KONZEPT 1.3 mit Messgründen), Tabellen `report/tables.py`, Glyph-Sicherheit
  `report/glyphs.py` (`[U+XXXX]` für nicht darstellbare Zeichen).
- Leerzellen-Vertrag `render.EXPLAINED_EMPTY`, zehn Zellklassen `c-rule … c-reason`, Zeilenattribut `data-key`.
- Höchstens 50 Zeilen je Regel plus Sammelzeile mit exaktem Rest; vollständige Liste in `results.json` (A-59).
- Layout A4: Deckblatt/Zusammenfassung hoch, Abschnitte 3–6 quer; fester Satz auf jeder Seite; eine Schrift „NG Sans“.
- Wortprüfung ARC-05 über alle nutzersichtbaren Texte (`report/wording/statements.yaml`).
- Skalierungsdaten und -test:
  ```powershell
  $PY = ".\.venv\Scripts\python.exe"
  & $PY tools\gen_fixtures.py --scale-results .local\perf\scale_worst.json                 # 1000 × 64, schlimmster Fall
  & $PY tools\gen_fixtures.py --scale-results .local\perf\scale_typical.json --typical
  & $PY -m pytest tests\perf\test_report_scaling.py -m perf -s -p no:cacheprovider          # schreibt .local/perf/report_scaling.json
  ```
  Gemessen (vor dem PDF-Merge, HTML zh+en) [D]: schlimmster Fall 128 742 Befunde, `results.json` 149 113 681 B,
  Erzeugung 37,6 s, `report` 13,4 s, Spitze 1675 MB; typischer Fall 6 110 Befunde, `results.json` 27 435 327 B, Erzeugung 9,7 s, `report` 6,1 s, Spitze 349 MB.
  Grenzen legt A-88 nach Messung auf dem gemergten Stand fest [offen].
- Suite im Bereich nach Reparatur: 2831 bestanden, 14 übersprungen, 69 abgewählt in 895,85 s [D].

#### 4.7.3 PDF (Bereich pdf; A-85; TECH-07, CLI-05, NG-F13, NG-N01, NG-N03)

- Neue Laufzeitabhängigkeiten: playwright 1.63.0, pypdf 6.21.2, fonttools 4.66.1 (direkt), transitiv greenlet 3.5.6,
  pyee 13.0.1.
- `kernel/fonts.py` (Subsetting, eigene Glyphen je Codepunkt), `kernel/pdf.py` (`locate_shell`, Start-Check,
  `PdfPrinter`, QA-Gate, Datumsfelder = Stichtag), `report/output.py` (`write_reports`: alles oder nichts),
  `kernel/pdf_linux_packages.json`.
- **Schriften** (D-06, A-27), eingecheckt; Neubau und Prüfung:
  ```powershell
  $PY = ".\.venv\Scripts\python.exe"
  & $PY tools\build_fonts.py            # lädt die gepinnte Quelle nach .local\build_fonts, baut Regular/Bold
  & $PY tools\build_fonts.py --check    # "fonts are reproducible", ≈ 71 s [D]
  ```
  Quelle und Ausgaben siehe Abschnitt 7; je Schnitt 453 Radikal-/Kompatibilitäts-Codepunkte entfernt.
- **PDF-Browser** (D-06, D-08), PowerShell:
  ```powershell
  $PY = ".\.venv\Scripts\python.exe"
  & $PY tools\install_pdf_browser.py --print-info   # URLs, Größen, SHA-256, Zielordner, apt-Listen
  & $PY tools\install_pdf_browser.py                # online, nach %LOCALAPPDATA%\NeuroGrid\pdf-browser
  & $PY tools\install_pdf_browser.py --check        # "complete (revision 1243, 290 files)" [G], ≈ 1,5 s
  ```
  Offline: `--download-only --platform win64 --out <Ziel>` auf einem vernetzten Rechner, dann
  `--from-zip <zip> --sha256 7aec872f3090e639c4237467624ea863c20fe2878914c93a6556bdbb52aa6c4c`. Nie
  `playwright install`, nie `ms-playwright`, nie Edge (A-26). Ein älteres `%LOCALAPPDATA%\ms-playwright` wird nie
  benutzt (getestet).
- **PDF-Tests:**
  ```powershell
  $PY = ".\.venv\Scripts\python.exe"
  $env:NEUROGRID_REQUIRE_PDF = "1"
  & $PY -m pytest -q -p no:cacheprovider tests\integration\test_report_pdf.py tests\cli\test_report_pdf_cli.py tests\unit\test_pdf_unit.py tests\unit\test_fonts.py tests\unit\test_install_pdf_browser.py
  ```
  Volle Suite nach Reparatur: 2818 bestanden, 12 übersprungen, 65 abgewählt in 1085,73 s [D].
- Messungen [D]: Fixture `bids_issues` (core+bids+gxdsl008): zh-PDF 14 Seiten 143 490 B, en 9 Seiten 63 587 B; gleiche
  SHA-256 in drei Läufen; 3.11/3.12/3.13 drucken byte-gleiche PDFs; Korpus-Rauchtest auf ds002778, ds004148, ds000248
  ohne Exit 2, QA-Gate grün, 0 blockierte Verbindungen; Wheel `neurogrid-0.1.0.dev1-py3-none-any.whl` 13 060 889 B.
- Linux-Pakete (Git Bash): `PY=.venv/Scripts/python.exe; "$PY" tools/linux_pdf_packages.py debian12` (21 Pakete);
  `"$PY" tools/linux_pdf_packages.py --check` → „pdf_linux_packages.json matches Playwright“ [G].

#### 4.7.4 Doku, Meldungen, Notices, Lizenzen (Bereich docs; A-86; TECH-06, TECH-10, POS-02, CON-05, NG-N06, V-06, D-03)

- 16 Seiten je Sprache (`index`, `installation`, `quickstart`, `commands`, `configuration`, `rulepacks`, `metrics`,
  `report`, `privacy`, `limitations`, `terms`, `data-model`, `license`, `reference/checks`, `reference/rules`,
  `reference/outputs`).
- Erzeugen und Bauen:
  ```powershell
  $PY = ".\.venv\Scripts\python.exe"
  & $PY tools\gen_docs.py --check                    # "documentation up to date" [G]
  uv run python tools\build_docs.py --site-dir site  # ≈ 32–38 s; endet mit "network events during the build: 0" und "documentation built and checked" [D]
  ```
  Mit `SOURCE_DATE_EPOCH=1792800000` sind zwei Bauten byte-gleich (Test). Suche offline nur über
  `python -m http.server 8000 --bind 127.0.0.1 --directory <site>`; auf `file://` ist das Suchfeld abgeschaltet.
  Chinesisch ohne jieba (ein Token je Han-Zeichen, `tools/mkdocs_hooks.py`).
- CLI-Hilfe und Bedienfehler zh/en über `cli.help.*`/`cli.error.*` (NG-N06).
- Notices:
  ```powershell
  $PY = ".\.venv\Scripts\python.exe"
  & $PY tools\notices.py --download --out THIRD_PARTY_NOTICES.txt   # lädt gepinnte Wheels nach .local\notices-wheels
  & $PY tools\notices.py --download --check                         # erwartet: "up to date" + 6 "incomplete: …", Exit 1
  ```
  Exit 1 ist bis G1 gewollt: `license-gate/known_missing.toml` hat 6 Einträge (Abschnitt 8). Heutige Datei
  1 398 869 B [G]; in der Merge-Simulation „129 wheels, 4 bundle parts“ [D].
- Lizenz-Gate mit Doku-Gruppe (PowerShell):
  ```powershell
  $PY = ".\.venv\Scripts\python.exe"
  $env:UV = "<uv>"                                   # nur, wenn uv nicht im PATH liegt
  & $PY tools\licenses.py                            # runtime/dev/docs × allowlist/copyleft: je "ok"
  & $PY tools\licenses.py --components --download    # oder --wheelhouse <dir> je Ziel; braucht kein uv
  ```
  Im Bereich (Lock vor dem Merge) runtime/dev/docs × allowlist/copyleft ok [D]; `--components` mit „129 wheels,
  4 bundle parts“ nur in der Merge-Simulation [D]. **Auf dem gemergten Stand (103-Paket-Lock) ist keiner der beiden
  Läufe protokolliert – nach dem Merge zu wiederholen** (Stand 584b7d2, P5 noch nicht abgeschlossen).
- `core.yaml` 0.1.0 → 0.1.1 (Quellenangabe verweist auf `metrics.md`).
- Suite nach Reparatur (mit `UV` gesetzt): 2908 bestanden, 13 übersprungen, 65 abgewählt in 957,69 s [D]. Browser-Tests
  (`-m browser`) liefen vor dem Merge nur in einem Ersatzaufbau.

#### 4.7.5 Bündel, Signatur, Workflows (Bereich bundle; A-87; UF-08, ARC-06, CON-04, CON-02, NG-N01, NG-N04, TECH-05, TECH-08, V-01)

- Version `0.1.0rc1`; `0.1.0` und Tag `v0.1.0` erst nach G1.
- **Bündel bauen** (in einer synchronisierten Umgebung; Git Bash):
  ```bash
  export SOURCE_DATE_EPOCH="$(git log -1 --format=%ct)"
  uv sync --locked --no-build --python 3.12
  uv build --out-dir dist
  uv run --no-sync python tools/build_docs.py --site-dir site
  v="$(uv run --no-sync python -c 'import neurogrid; print(neurogrid.__version__)')"
  for p in win_amd64 linux_x86_64; do
    uv run --no-sync python tools/bundle.py build --platform "$p" \
      --wheel "dist/neurogrid-$v-py3-none-any.whl" --sdist "dist/neurogrid-$v.tar.gz" \
      --docs site --notices THIRD_PARTY_NOTICES.txt --out dist
  done
  uv run --no-sync python tools/bundle.py verify "dist/neurogrid-$v-offline-win_amd64.zip"
  uv run --no-sync python tools/bundle.py verify "dist/neurogrid-$v-offline-linux_x86_64.tar.gz"
  ```
  Downloads landen in `NEUROGRID_BUNDLE_CACHE` bzw. `.local/bundle-cache` (Dateien nach SHA-256 benannt, bei jeder
  Nutzung geprüft). Weitere Befehle: `tools/bundle.py sizes`, `tools/bundle.py lock --python 3.12.15 --pbs-build
  20261009 --uv 0.13.0` (nur Pflege, Netz). `bundle.py sizes` maß **vor dem PDF-Merge** (ohne playwright, pypdf,
  greenlet, pyee) win_amd64 61 Wheels / 195,5 MiB, linux_x86_64 60 Wheels / 214,9 MiB, höchste manylinux-glibc 2.28;
  die Spezifikationsprobe mit den PDF-Paketen 65 bzw. 64 Wheels, 233,1 bzw. 261,9 MiB [D]. Auf dem gemergten Stand
  nicht gemessen [NV].
- Gemessen [D]: vor dem PDF-Merge Windows-zip 246 087 316 B (3510 Einträge), Linux-tar.gz 275 211 566 B, zwei Bauten je
  Plattform byte-gleich, Bau 14–19 s (Windows, warmer Cache) bzw. ≈ 55 s (Linux); gemergtes `0.1.0rc1`-Windows-Bündel
  in einer Probe 309 696 896 B, `max_relative_install_path` 148, Präfixgrenze 101.
- **Windows-Reinraum lokal:**
  ```powershell
  powershell -NoProfile -ExecutionPolicy Bypass -File packaging\ci\cleanroom_windows.ps1 -Archive <zip> -Evidence <Ziel> -NoOsAudit
  ```
  Optionen: `-Root`, `-Installer cmd|pwsh`, `-PdfBrowserZip <zip> -PdfBrowserSha256 <hex>`, `-Keep`. Gemessen [D]:
  Installation 116–135 s, ganzer Lauf 198–219 s, 16 257 Dateien / 641,9 MiB, 0 Reste in TEMP; Exitcodes: install 0,
  verify-only 0, scan 0, check-edf 0, check-edf-plus-d 0, check-bdf 0, check-brainvision 1, check-eeglab 1,
  check-bids 0, convert 0, check-converted 0, manifest 0, verify 0, report-html 0, report-pdf-ohne-Browser 2,
  Bedienfehler 2. (Gemessen vor dem PDF-Merge; nach dem Merge zu wiederholen.)
  **Prüfbares Ergebnis** im `-Evidence`-Ordner [D]: `exit-codes.txt` (je Schritt der Exitcode, Vergleich mit der
  Liste oben), `<schritt>.out.log` und `<schritt>.err.log` je Schritt, `summary.txt` (Dateien, Größe, Zeiten),
  `temp-left.txt` (Reste in TEMP, erwartet leer).
- **Präfixgrenze am echten Bündel (A-87)** [D]: das gemergte Windows-zip mit `System32\tar.exe` entpacken, dann
  `install.cmd -SkipSignatureCheck -Prefix <Pfad mit 102 Zeichen>` → Exit 2, nichts angelegt;
  `-Prefix <Pfad mit 101 Zeichen>` → Exit 0 in ≈ 72 s, längster installierter Pfad 250 Zeichen; danach
  `<Präfix>\neurogrid.cmd check tests\fixtures\synthetic\edf_ok --as-of 2026-10-24 --out r.json` → Exit 1 (Befunde,
  ohne `documented.toml`) und `report r.json --lang "zh,en" --format html` → Exit 0 mit `report.zh.html`,
  `report.en.html`. Ein Präfix unter 102 Zeichen geht nur unter einem kurzen Ordner (z. B. `%TEMP%\ngp5lp`), nicht
  unter einem tiefen Worktree. Das Skript lag nur im Scratchpad [NV]; geprüft wurde mit dem reparierten `install.ps1`
  (Zeile in `SHA256SUMS` angepasst). Standardpräfix `%LOCALAPPDATA%\NeuroGrid\0.1.0rc1` = 41 Zeichen + Länge des
  Benutzernamens, also weit unter 101.
- **Linux und CI** (nur auf CI-Runnern mit Docker, D-09; lokal nie gelaufen), Git Bash bzw. bash:
  ```bash
  # Reinraum: docker run --rm --network none --user 1000:1000, tests/fixtures schreibgeschützt eingebunden
  bash packaging/ci/cleanroom_linux.sh --image debian:12-slim [--trace] [--pdf-zip ZIP --pdf-sha256 HEX] [--evidence DIR] ARCHIVE
  bash packaging/ci/cleanroom_linux.sh --image ubuntu:22.04 ARCHIVE
  bash packaging/ci/cleanroom_linux.sh --image ubuntu:24.04 ARCHIVE
  bash packaging/ci/cleanroom_linux.sh --image ubuntu:18.04 --expect-refusal ARCHIVE   # glibc < 2.28: Installer muss mit Exit 2 ablehnen
  # strace: Image debian:12-slim + strace, --cap-add SYS_PTRACE, seccomp=unconfined; danach python3 tools/strace_check.py DIR
  bash packaging/ci/offline_strace_linux.sh ARCHIVE [DIR]
  # PDF unter Debian 12: Shell auf dem Host laden, apt-Liste aus tools/linux_pdf_packages.py debian12
  python3 tools/install_pdf_browser.py --download-only --platform linux64 --out shell
  bash packaging/ci/pdf_debian12.sh ARCHIVE shell/*.zip [DIR]
  ```
  `packaging/ci/cleanroom_inside.sh` läuft nur im Container (von `cleanroom_linux.sh` aufgerufen), nie direkt.
  Unbekannte Option oder fehlendes Archiv → Exit 2.
- **Installer:** Windows `install.cmd [-Prefix DIR] [-Cosign PATH | -SkipSignatureCheck] [-VerifyOnly]
  [-PdfBrowserZip ZIP -PdfBrowserSha256 HEX]`; Linux `./install.sh [--prefix DIR] [--cosign PATH |
  --skip-signature-check] [--verify-only] [--pdf-browser-zip ZIP --pdf-browser-sha256 HEX]`. Exit 0 installiert,
  2 Bedienung/Umgebung, 3 Integrität, 4 Signatur. Standardpräfix `%LOCALAPPDATA%\NeuroGrid\<v>`; keine Änderung an
  PATH, Registry oder Profil. Unsignierte Entwicklungsbündel brauchen `-SkipSignatureCheck`.
- **Signatur (D-10 g, D-15):** Sigstore keyless nur in `release.yml`; Prüfung vor der Übertragung auf einem vernetzten
  Rechner:
  ```bash
  cosign verify-blob SHA256SUMS --bundle SHA256SUMS.sigstore.json \
    --certificate-identity https://github.com/<owner>/<repo>/.github/workflows/release.yml@refs/tags/v<v> \
    --certificate-oidc-issuer https://token.actions.githubusercontent.com
  sha256sum --check --ignore-missing SHA256SUMS
  ```
  Windows: `(Get-FileHash <datei> -Algorithm SHA256).Hash.ToLower()` mit der Zeile in `SHA256SUMS` vergleichen.
- **Weitere Werkzeuge:** `tools/release_check.py`, `tools/scan_runtime_network.py` (gemessen **vor dem PDF-Merge**,
  ohne playwright, pypdf, greenlet, pyee: 61 Distributionen, 79 Dateien mit Fundstellen, 0 Probleme [D]; auf dem
  gemergten Stand nicht wiederholt [NV]), `tools/strace_check.py` (Abschnitt 5).
- **Workflows** (alle Actions per Commit-SHA gepinnt, Abschnitt 7) [G: `on:`-Blöcke]: `ci.yml` (Push dev/main, PRs;
  Jobs `test`, `compare`, `traceability`, `licenses`, `powershell51`, `pwsh`, **kein Bündel-Job**), `offline.yml`
  (Push dev/main, Dispatch, Aufruf aus `release.yml`; Jobs `build`, `offline-strace`, `cleanroom-linux`, `glibc-refusal`,
  `pdf-debian12`, `cleanroom-windows`), `docs.yml` (Push main, PRs, Dispatch), `corpus.yml` (Push main, Dispatch; ruft
  `tools/acceptance_g1.py --corpus .local/corpus --out .local/acceptance/g1` auf), `release.yml` (Tag `v*` und
  Dispatch, nur Entwurf), `publish-pypi.yml` (Dispatch, Trusted Publishing), `mirror-gitee.yml` (Dispatch/Release,
  `vars.GITEE_MIRROR`). **Noch nie gelaufen** (kein Remote, D-09).
- Langsamer Test: `uv run pytest -m bundle tests/packaging/test_bundle_real.py` (braucht `site/`, Notices,
  `tools/install_pdf_browser.py`; 3 bestanden in 392,6 s [D]).
- Suite im Bereich (Bau-Commit `73bb04b`, vor der Reparatur `2d41f44`): 2864 bestanden, 13 übersprungen, 68 abgewählt
  in 1118,97 s [D]; für den Reparaturstand ist keine volle Suite protokolliert [NV]. `tests/packaging` unter
  3.11/3.12/3.13 je 157 bestanden [D].
- **Optionaler Flugmodus-Test (für den Projektverantwortlichen, nicht durchgeführt):** Bündel bauen und mit
  `tools/bundle.py verify` prüfen; Netz trennen (Flugmodus); `install.cmd -SkipSignatureCheck -Prefix <kurzer Pfad>`;
  dann `<Präfix>\neurogrid.cmd check tests\fixtures\synthetic\edf_ok --config tests\fixtures\documented.toml --out r.json`
  und `report r.json --lang "zh,en" --format html`; erwartet Exit 0 und beide Berichte. Den OS-Nachweis mit WFP-Audit
  macht nur die CI (keine Änderung an Sicherheitseinstellungen des eigenen Rechners).

#### 4.7.6 Stand heute und was zu P5 noch fehlt

Heute geprüft [G, 19bd93c]:
- `uv lock --check --offline` → 103 Pakete; `ruff check` „All checks passed!“; `ruff format --check` „211 files
  already formatted“ auf dem sauberen Stand `19bd93c`; sobald `docs/umsetzung/NACHBAU.md` versioniert ist, sind es
  212 (ruff 0.17.0 zählt auch diese Markdown-Datei).
- `gen_fixtures`, `gen_schemas`, `gen_montage_names`, `gen_docs`, `calibrate` jeweils `--check` grün;
  `linux_pdf_packages.py --check` grün; `install_pdf_browser.py --check` grün; `corpus.py verify` „corpus verified“
  in ≈ 2,5–4 s.
- Testsammlung: 3414 Tests, Standardlauf 3342, abgewählt 72 (62 `corpus`, 7 `perf`, 3 `bundle`); Marker `pdf` 22,
  `browser` 2.
- Durchstich `check` + `report --format html,pdf` (4.0).

Noch offen (Lead): volle Suite auf dem gemergten Stand unter 3.11/3.12/3.13 mit `NEUROGRID_REQUIRE_PDF=1` und `UV`,
Abdeckungs- und Lizenz-Gate, Korpus- und Skalierungstest, `tools/acceptance_g1.py` (von `corpus.yml` aufgerufen,
existiert noch nicht), A-84..A-88, Review mit vier Prüfrichtungen, Matrix/KONZEPT/FORTSCHRITT, Phasenbericht, STOPP G1.
Dazu nach dem Merge zu wiederholen: Lizenz-Gate runtime/dev/docs und `--components` auf dem 103-Paket-Lock (4.7.4),
Windows-Reinraum, `bundle.py sizes`, `scan_runtime_network.py` (4.7.5).

D-15 verlangt, dass die Bündel-Tests nach dem ersten Push bei jedem Push auf `dev` und `main` laufen. Seit Review R10
läuft `offline.yml` bei jedem Push auf `dev` und `main` sowie per Dispatch oder Aufruf aus `release.yml`; ein neuerer
Push auf denselben Zweig bricht den älteren Lauf ab, ein Release-Lauf (Tag-Ref) wird nie abgebrochen [G: `on:`- und
`concurrency:`-Block, `tests/packaging/test_workflows.py`]. `ci.yml` (Push `dev`/`main`) hat weiterhin keinen
Bündel-Job; die Bündel-Tests liegen in `offline.yml`. Ein grüner Lauf von `offline.yml` auf `dev` steht noch aus [NV].

---

## 5 Prüfwerkzeuge (`tools/`)

Alle Werkzeuge laufen im `<Projektordner>` mit `& $PY tools\<name>.py` (PowerShell) bzw. `"$PY" tools/<name>.py`
(Git Bash), nachdem `PY` wie in 4.0 gesetzt ist. Exit 0 heißt immer „in Ordnung“.

| Werkzeug | Zweck | Aufruf | Exitcodes |
|---|---|---|---|
| `check_matrix_coverage.py` | jede Matrixzeile genau eine abschließende Phase, keine unbekannte ID | `check_matrix_coverage.py` | 0 / 1 |
| `check_commit_ids.py` | Anforderungs-IDs in Commits seit `d81ad0c` (Merges übersprungen) und datierten FORTSCHRITT-Einträgen | `[--since REV] [--message-file F] [--no-history]` | 0 / 1 |
| `coverage_gates.py` | Abdeckung je Gruppe aus `coverage json`: Kern ≥ 90 %, Prüfer ≥ 80 % | `coverage_gates.py <coverage.json>` (kein `--help`) | 0 / 1 |
| `gen_fixtures.py` | synthetische Fixtures; Skalierungs-`results.json` (A-59) | `[--check]`, `--scale-results OUT [--recordings 1000] [--channels 64] [--typical]` | 0 / 1 |
| `gen_schemas.py` | JSON-Schemas aus Pydantic | `[--check]` | 0 / 1 |
| `gen_montage_names.py` | Elektrodennamen aus MNE 1.13.2 einfrieren | `[--check]` | 0 / 1 |
| `licenses.py` | Lizenz-Gate in eigenen venvs aus `uv.lock`; statische Komponentenprüfung | `[--groups runtime dev docs]`, `--components (--wheelhouse DIR … \| --download)`; `UV` nur für die venv-Stufen und nur, wenn uv nicht im PATH liegt; `--components` braucht kein uv | 0 / 1 / 2 (2 bei `--components`, wenn Dateien fehlen oder `notices.NoticeError` auftritt) |
| `corpus.py` | Korpus laden und offline prüfen (nur Standardbibliothek) | `verify\|fetch\|lock [--root .local/corpus] [--lock F] [--spec F] [--dataset X]… [--workers 4] [--prefer-mirror]` | 0 / 1 / 2 |
| `calibrate.py` | Schwellen M06/M07/M09 (95. Perzentil) | `[--root .local/corpus] [--jobs 4]`, `--check` | 0 / 1 |
| `gen_large_edf.py` | 1-GB-EDF+C für NG-N02 (fester Seed) | `OUT.edf [--channels 64] [--size-gb 1.0]` | 0 |
| `benchmark.py` | Wandzeit und Spitzen-RSS von `neurogrid check` | `[--channels 64 128 256] [--jobs 4] [--size-gb 1.0] [--out .local/perf/benchmark.json]` | 0 / 1 |
| `build_fonts.py` | statische Noto-Sans-SC-Schnitte | `[--source DIR]`, `--check` | 0 / 1 / 2 |
| `install_pdf_browser.py` | Headless Shell 1243 in NeuroGrids Ordner (nur Standardbibliothek, Meldungen zh+en) | `[--dir D] [--from-zip ZIP --sha256 HEX] [--download-only --platform win64\|linux64 --out DIR] [--force] [--check] [--print-info]` | 0 / 1 / 2 |
| `linux_pdf_packages.py` | apt-Liste der Shell aus Playwright 1.63.0 | `[DISTRIBUTION]`, `--list`, `--check`, `--write` | 0 / 1 / 2 |
| `gen_docs.py` | Referenzseiten und generierte Blöcke | `[--check]` | 0 / 1 / 2 |
| `build_docs.py` | Website bauen und prüfen (Netz-Audit-Hook, `SOURCE_DATE_EPOCH`) | `[--site-dir site]` | 0 / 1 / 2 |
| `mkdocs_hooks.py` | MkDocs-Hooks (Suche zh, Schemas, 404) – kein eigener Aufruf | über `mkdocs.yml` | – |
| `notices.py` | `THIRD_PARTY_NOTICES.txt` statisch aus den Wheels beider Ziele | `--list`; `--wheelhouse DIR … --out F`; `--download [--cache DIR] --out F`; `--check`; `--components`; `[--bundle-lock F]` | 0 / 1 / 2 |
| `bundle.py` | Offline-Bündel | `build --platform P --wheel W --docs D --notices N [--sdist S] [--pdf-installer F] [--out dist] [--cache DIR] [--sign none\|sigstore]`; `verify PATH`; `sizes [--platform P]`; `lock --python V --pbs-build B --uv V [--cache DIR]` | 0 / 1 / 2 |
| `release_check.py` | Release-Gate (Tag = Version, auf main, sauberer Baum, keine Platzhalter, Lizenztexte) | `--tag v<v> [--root DIR] [--notes OUT] [--repository owner/repo]` | 0 / 1 / 2 |
| `scan_runtime_network.py` | Netzwerk-/Telemetrie-Fundstellen der Laufzeitpakete gegen die Baseline | `[--site-packages DIR] [--baseline F] [--distribution NAME]… [--draft OUT]` | 0 / 1 / 2 |
| `strace_check.py` | strace-Ausgaben auswerten (nicht-Loopback = Fehler) | `strace_check.py EVIDENCE_DIR` (kein `--help`) | 0 / 1 / 2 |

Datendateien in `tools/`: `corpus_spec.json`, `corpus_lock.json`, `docs_templates/*.md.j2` (Vorlagen für
`gen_docs.py`).

Prüfskripte unter `packaging/ci/` (genaue Aufrufe in 4.7.5):

| Skript | Zweck | Aufruf | Exitcodes |
|---|---|---|---|
| `cleanroom_windows.ps1` | Windows-Reinraum: Installer und jeder v0.1-Befehl, Belegdateien | `powershell -NoProfile -ExecutionPolicy Bypass -File packaging\ci\cleanroom_windows.ps1 -Archive ZIP -Evidence DIR [-NoOsAudit] [-Root DIR] [-Installer cmd\|pwsh] [-PdfBrowserZip ZIP -PdfBrowserSha256 HEX] [-Keep]` | 0 = alle Schritte wie erwartet; sonst Abbruch mit ≠ 0 (z. B. Reste in TEMP); mit OS-Audit (CI) zusätzlich `wfp-*.txt` |
| `cleanroom_linux.sh` | Linux-Reinraum im Container ohne Netz, ohne Python, uid 1000 (nur CI) | `bash packaging/ci/cleanroom_linux.sh --image IMAGE [--expect-refusal] [--trace] [--pdf-zip ZIP --pdf-sha256 HEX] [--evidence DIR] ARCHIVE` | 0; 2 Bedienung; sonst Exitcode des Containers |
| `cleanroom_inside.sh` | läuft im Container, von `cleanroom_linux.sh` gestartet | nie direkt | – |
| `offline_strace_linux.sh` | `cleanroom_linux.sh --trace` in einem Debian-12-Image mit strace, danach `strace_check.py` | `bash packaging/ci/offline_strace_linux.sh ARCHIVE [EVIDENCE_DIR]` | 0 / ≠ 0 |
| `pdf_debian12.sh` | Bündel mit PDF-Browser unter Debian 12, `report --format pdf` | `bash packaging/ci/pdf_debian12.sh ARCHIVE SHELL_ZIP [EVIDENCE_DIR]` | 0 / ≠ 0 |

---

## 6 Testkorpus

### 6.1 Zweck und Freigabe

Öffentlicher Korpus für Korpus-Tests, Kalibrierung (MET-01) und Praxistests; freigegeben durch D-06 und D-11 (ohne
EEGDash, LIB-09). Ablage `.local/corpus/`, nie versioniert.

### 6.2 Quellen und Pins

| Datensatz | Quelle | Version | Format | Lizenz | Auszug (`corpus_spec.json`) | Dateien / MB | Snapshot (hexsha) |
|---|---|---|---|---|---|---|---|
| ds003775 | OpenNeuro | 1.2.1 | EDF | CC0 | Wurzeldateien, sub-001..005 | 37 / 251,8 | `cb354b249827d17fa0575b2b42521ba25982c16b` |
| ds002778 | OpenNeuro | 1.0.5 | BDF | CC0 | Wurzeldateien, erste 5 Probanden | 41 / 59,9 | `2890cbd8da62179735aae536a520008154630dd6` |
| ds004148 | OpenNeuro | 1.0.1 | BrainVision | CC0 | Wurzeldateien, sub-01..03, ses-session1, task eyesclosed (+ electrodes, coordsystem, scans, sessions) | 26 / 109,9 | `f3ce98fa8e907b2498ebd359a1ea12f911a0964c` |
| ds004504 | OpenNeuro | 1.0.9 | EEGLAB | CC0 | Wurzeldateien, sub-001..005 | 20 / 128,7 | `63b2ec152bc3cd4487d131124f10f767ebe543bc` |
| ds000248 | OpenNeuro | 1.2.4 | FIF (MEG mit EEG) | CC0 | Wurzeldateien, sub-01 task audiovisual run-01, coordsystem, scans, Kalibrier-/Crosstalk-Dateien (ohne sub-emptyroom) | 14 / 128,6 | `0a357f1276dbf7fcc3c3fc35f74cb24ffe4a68a8` |
| psg-ipa | PhysioNet | 1.0.0 | EDF+ | CC BY 4.0 | 3 kleinste Schlafaufnahmen mit allen Annotationen + Doku-Dateien | 159 / 377,5 | – (`SHA256SUMS.txt`) |

Summe: 297 Dateien, 1,056 GB. Prüfsummen: 158 „published“ (PhysioNet `SHA256SUMS.txt`), 139 „first_download“
(OpenNeuro veröffentlicht keine Hashes; beim ersten Laden zusammen mit dem Snapshot festgehalten). Zitate und DOIs
stehen in `DATA_SOURCES.md`.

### 6.3 Laden und Prüfen

PowerShell:
```powershell
$PY = ".\.venv\Scripts\python.exe"
& $PY tools\corpus.py fetch                    # nur URLs aus tools/corpus_lock.json; 4 parallele Downloads
& $PY tools\corpus.py fetch --prefer-mirror    # PhysioNet über den AWS-Spiegel (so wurde PSG-IPA geladen)
& $PY tools\corpus.py fetch --dataset ds003775 # nur ein Datensatz (wiederholbar)
& $PY tools\corpus.py verify                   # offline: "corpus verified" in ≈ 2,5–4 s [G]
& $PY -m pytest -m corpus                      # 62 Tests, ≈ 12 min [D]
```
`fetch` lädt nur die URLs aus `tools/corpus_lock.json` (OpenNeuro: S3 mit `versionId`, für 36 Dateien von ds002778
der Objekt-Endpunkt `https://openneuro.org/crn/datasets/ds002778/objects/<id>`; PhysioNet bzw. mit
`--prefer-mirror` den AWS-Spiegel), prüft Größe und SHA-256, überspringt vorhandene gleiche Dateien und meldet
„N/N files present and verified“ (Exit 0; 1 bei Fehlern). Die GraphQL-API `https://openneuro.org/crn/graphql` nutzt nur
`corpus.py lock` (Pflege, 6.4) [G: `cmd_fetch`].
Dauer von `fetch` nicht protokolliert [NV]. Wiederholte Abbrüche sind normal; `fetch` erneut starten, bis `verify`
grün ist. In der CI: Cache-Schlüssel `corpus-<hashFiles(tools/corpus_lock.json)>`, nur eine Zusammenfassung verlässt
den Runner.

### 6.4 Herkunft der Sperrdatei

`tools/corpus_lock.json` wurde **nicht** mit `corpus.py lock` erstellt, sondern einmalig aus der `registry.json` des
Prototyps S5 abgeleitet (Skript nur im Scratchpad) [G]. Für den Nachbau: `fetch` gegen die eingecheckte Sperrdatei
(gleiches Ergebnis). `corpus.py lock` löst die Spezifikation neu auf (Netz; neue Hashes für OpenNeuro) und ist nur für
Pflege gedacht.

### 6.5 Spiegel und Worktrees

Worktrees bekommen den Korpus als Junction (3.5); vor dem Entfernen lösen (1.6). Eine Kopie ist ebenfalls möglich
(1 GB). Synthetische Fixtures und die 1-GB-Dateien (`.local/perf/ng_n02_{64,128,256}ch.edf`, von
`gen_large_edf.py`/`benchmark.py`) gehören nicht zum Korpus.

---

## 7 Externe Downloads

| Was | Quelle (URL) | Größe | SHA-256 | Freigabe | Wofür |
|---|---|---|---|---|---|
| Git for Windows 2.51.1 | `Git-2.51.1-64-bit.exe` von `https://github.com/git-for-windows/git/releases/tag/v2.51.1.windows.1` | [NV] | [NV] (auf der Release-Seite) | war vorhanden | Werkzeug |
| Python 3.13.7 | `https://www.python.org/ftp/python/3.13.7/python-3.13.7-amd64.exe` | [NV] | [NV] | war vorhanden | uv-Träger, venv 3.13 |
| uv 0.13.0 (pip, 1.3 Schritt 3) | PyPI, dieselbe Datei `uv-0.13.0-py3-none-win_amd64.whl` wie die nächste Zeile | 15 819 247 B | `0367b4e0ae4dcef32da4aa2ad2f3853b6ad81d50c187abe50d343d892b8fea21` (gepinnt in `packaging/bundle_lock.json`; mit `pip install --require-hashes` erzwingbar) | D-06 | Werkzeug |
| uv 0.13.0 Wheel win_amd64 | `https://files.pythonhosted.org/packages/b2/00/73abae6cafcdb868d42b2c71bf12c9c2eb06a8d229a09569760c41b7948d/uv-0.13.0-py3-none-win_amd64.whl` | 15 819 247 B | `0367b4e0ae4dcef32da4aa2ad2f3853b6ad81d50c187abe50d343d892b8fea21` | D-06 | Bündel |
| uv 0.13.0 Wheel Linux | `https://files.pythonhosted.org/packages/c3/75/1901383808ba0d421f32060ba0e9884169b685a722e1af5d87fdd4225ba6/uv-0.13.0-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl` | 17 941 073 B | `52c7da0fd9056d9551124777ec77de53f0df7017daf8f98a19e947b7837416ed` | D-06 | Bündel, Notices |
| CPython 3.11.17, 3.12.15 | python-build-standalone über `uv python install` | [NV] | von uv geprüft | D-06 | Entwicklung |
| PBS 3.12.15+20261009 Windows | `https://github.com/astral-sh/python-build-standalone/releases/download/20261009/cpython-3.12.15%2B20261009-x86_64-pc-windows-msvc-install_only_stripped.tar.gz` | 22 011 208 B | `11ed9f8a6ac64fb1b5a55e40e305a6744a3f77a70863c8f8197a6e4349abc64a` | D-06 | Bündel-Interpreter |
| PBS 3.12.15+20261009 Linux | `…/20261009/cpython-3.12.15%2B20261009-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz` | 34 304 557 B | `ffa8f85f1b56e88b687f08d743d817015524b86a9365fd921243132b80f1a36d` | D-06 | Bündel (ohne `_dbm`, A-87) |
| Python-Pakete (103 im Lock) | PyPI (`pypi.org/simple`, `files.pythonhosted.org`) | je Wheel in `uv.lock` | je Wheel in `uv.lock` | D-06; nur Wheels (A-48) | Laufzeit, dev, docs |
| hatchling 1.32.4 | PyPI | – | – | D-06 | Build-Backend |
| Noto Sans SC Variable | `https://raw.githubusercontent.com/google/fonts/a85815a42757630ce188fdad368c2dfc444d4773/ofl/notosanssc/NotoSansSC%5Bwght%5D.ttf` | 17 772 300 B | `a3041811a78c361b1de50f953c805e0244951c21c5bd412f7232ef0d899af0da` | D-06 | `build_fonts.py` (Version 2.004, upstream noto-cjk `523d033d`) |
| OFL.txt der Schrift | `…/a85815a42757630ce188fdad368c2dfc444d4773/ofl/notosanssc/OFL.txt` | 4 388 B | `1c05c68c34f9708415aada51f17e1b0092d2cea709bf4a94cd38114f9e73d7d9` | D-06 | Lizenz |
| → erzeugt: NotoSansSC-Regular.ttf | `tools/build_fonts.py` | 10 589 344 B | `df909d5171e793a8f49bfb01b6a853bff79e5b6415ef41372f85ba3e189e66c9` | – | eingecheckt |
| → erzeugt: NotoSansSC-Bold.ttf | `tools/build_fonts.py` | 10 578 868 B | `2dc3346b660b6740b9c2832f430f0cdc061bc7fc6637498ac82cde49deb7105f` | – | eingecheckt |
| Chrome Headless Shell 1243 win64 | `https://cdn.playwright.dev/builds/cft/153.0.8010.12/win64/chrome-headless-shell-win64.zip` (Spiegel `https://storage.googleapis.com/chrome-for-testing-public/153.0.8010.12/win64/chrome-headless-shell-win64.zip`) | 120 200 717 B (entpackt 290 Dateien, 283 217 434 B) | `7aec872f3090e639c4237467624ea863c20fe2878914c93a6556bdbb52aa6c4c` | D-06, D-08 (nie im Bündel) | PDF, Browsertests |
| Chrome Headless Shell 1243 linux64 | gleiche Pfade mit `linux64` | 119 809 080 B (287 Dateien, 272 533 063 B) | `a9da028861a0cf789ff25c2fed45f5f1aaf969ed9247835b6a7821a4f7af9d1d` | D-06, D-08 | CI, Linux-Kunden |
| Testkorpus OpenNeuro (5 Datensätze), `corpus.py fetch` | Dateien `https://s3.amazonaws.com/openneuro.org/<ds>/…?versionId=…`, für 36 Dateien von ds002778 `https://openneuro.org/crn/datasets/ds002778/objects/<id>` (alle URLs aus `tools/corpus_lock.json`) | 6.2 | `tools/corpus_lock.json` | D-06, D-11 | Korpus, Kalibrierung |
| OpenNeuro-Metadaten, nur `corpus.py lock` (Pflege) | GraphQL-API `https://openneuro.org/crn/graphql` | – | – (liefert keine Hashes) | D-06, D-11 | Sperrdatei neu auflösen (6.4) |
| PSG-IPA 1.0.0, `corpus.py fetch` | `https://physionet.org/files/psg-ipa/1.0.0/`, mit `--prefer-mirror` Spiegel `https://physionet-open.s3.amazonaws.com/psg-ipa/1.0.0/` | 377,5 MB | `SHA256SUMS.txt` | D-06 | Korpus, κ |
| ICLabel-Netzgewichte | im Wheel mne-icalabel 0.10.0 | – | – | Herkunft/Lizenz offen (A-56) | M09b |
| Standardmontagen colin27 | im Wheel mne 1.13.2 (`mne.datasets` verboten) | – | – | A-49, A-79 | M04, Positionen |
| apt-Pakete, Container-Images (`debian:12-slim`, `ubuntu:22.04/24.04/18.04`), strace | Debian/Ubuntu, Docker Hub, nur auf CI-Runnern | – | Digest nur zur Laufzeit festgehalten | D-09, A-58 | Linux-Reinraum, strace, PDF-Linux |
| GitHub Actions | `actions/checkout` v7.0.1 `3d3c42e5…`, `astral-sh/setup-uv` v10.3.2 `07a047e6…`, `actions/upload-artifact` v7.0.2 `cf430e03…`, `actions/download-artifact` v8.0.2 `9000827c…`, `actions/cache` v6.1.0 `55cc8345…`, `sigstore/cosign-installer` v4.1.2 `6f9f1778…`, `pypa/gh-action-pypi-publish` v1.14.3 `7245906f…` | – | Commit-SHA (aufgelöst 23.10. mit `git ls-remote`) | D-07, D-09 | CI |
| cosign | über `sigstore/cosign-installer` (Standardversion dieses Commits) | – | – | D-10 g | Signatur in der CI |
| CC-BY-4.0-Rechtstext, npm/jsr-Lizenzdateien des Validators | creativecommons.org bzw. npm/jsr | – | beim Ablegen festhalten | **D-15** (freigegeben; Ablage in `LICENSES/` und `known_missing.toml` noch offen) | `LICENSES/`, Notices |
| BIDS-Schema-Lizenz, libaec/libsz-Texte, Bibliothekstexte von python-build-standalone | – | – | – | **keine Freigabe** (Entscheidung zu G1) | `known_missing.toml` leeren |
| torch, braindecode, moabb, MOABB-Daten | – | – | – | D-06 | P11, noch nicht geladen |

Bewusst **nicht** verwendet: eegprep (D-05), pyEDFlib (A-24), EEGDash (D-11), openneuro-py (GPL-3.0), Microsoft Edge,
jieba (nur sdist), iframe-worker, `playwright install`, actionlint (Nebenwirkung einer Probe, nicht übernommen, aus dem
Cache entfernt).

---

## 8 Bekannte Grenzen und nicht Verifiziertes

**Plattformen (D-09):**
- Linux, CI, strace, Container und alle sieben Workflows sind **nie gelaufen** (kein Remote, kein Docker). Betroffen:
  TECH-05, TECH-11, Linux-Teil von NG-N04, offline-strace (NG-N01), Linux-Reinräume, glibc-Ablehnung, `pdf-debian12`,
  Windows-WFP-Audit, POSIX-Zweige der Provenienz, Linux-Start-Check des PDF-Browsers (ldd-Testdaten sind synthetisch).
- PowerShell 7 ist nicht installiert; Windows 10 und die Windows-Server-Images von GitHub sind nicht verifiziert.
- NG-N02 auf einem Runner mit 4 vCPU/16 GB ist nicht gemessen.
- Neuere Action-Hauptversionen, WFP-Audit und strace im Container können beim ersten Lauf Anpassungen brauchen.

**Nicht protokolliert / nicht erhalten:**
- genaue Befehle für uv-Installation, `uv python install`, Anlage von venv3.11/3.13 (hier [R]), lokale pytest-Aufrufe,
  Probe-Wheel, Rauchtests PowerShell 5.1 in P1/P2, Zusatzmessung „256 Kanäle mit Manifest“
- Prototypen S1–S5 (Skripte gelöscht); Bau-Reihenfolge innerhalb P1–P3; Herstellung von `architektur-s8.png`
- Plattformvergleichsskript (nur Scratchpad)

**Inhaltlich offen (für G1 vorgemerkt):**
- `license-gate/known_missing.toml`, 6 Einträge: CC-BY-4.0-Rechtstext; Lizenzdateien der npm/jsr-Pakete im Validator;
  Lizenz des BIDS-Schemas 1.2.7 im Validator; libaec 1.1.4 und libsz im Linux-h5py-Wheel; Texte der Bibliotheken in
  python-build-standalone. Solange die Liste nicht leer ist, sperren `notices.py --check` und `release_check.py` das
  Release.
- Herkunft/Lizenz der ICLabel-Gewichte (A-56); Restpunkte A-78; Zeitangaben ab 27,8 h nur auf 1 s genau (A-61,
  A-79); loky „resource tracker“ ohne Netzwerkschutz (A-79); vorgemerkte Punkte aus A-80..A-83.
- Container-Images per Tag, nicht per Digest gepinnt; cosign-Version = Standard des Installers; Windows-OS-Nachweis
  ordnet DNS-Anfragen des DNS-Client-Dienstes nicht zu.
- PDF: kein Warten auf Web-Schriften vor dem Druck (Fehlfall wäre Exit 2 durch das Gate, nie beobachtet); Umbenennung
  der Ausgaben nicht transaktional; kopierte Glyph-Zwillinge nehmen nicht an GSUB/GPOS teil; Sichtprüfung der PDFs
  nicht gemacht (kein PDF-Renderer lokal).
- Pfadgrenzen 250/260 nur auf Windows 11 Build 26200 gemessen; Linux-PATH_MAX-Grenze beruht auf der dokumentierten
  Konstante.
- zh-Prüfung durch Muttersprachler (A-07) für alle zh-Texte, Doku, Installer- und Browser-Meldungen.

**P5 (Stand 584b7d2, P5 noch nicht abgeschlossen):** volle Suite, Abdeckung, Lizenz-Gate (alle Gruppen und
`--components`), Korpus, Skalierungsgrenzen (A-88), `bundle.py sizes`, `scan_runtime_network.py` und Reinraum auf dem
gemergten Stand sind noch nicht gelaufen; `tools/acceptance_g1.py` fehlt; A-84..A-88, Matrix, KONZEPT 1.2/1.3/1.6 und
FORTSCHRITT sind für P5 noch nicht nachgetragen. Die Bündel-Tests laufen seit Review R10 wie in D-15 verlangt bei jedem
Push auf `dev` und `main` (`offline.yml`) [G]; ein grüner Lauf auf `dev` steht aus [NV].

---

## Anhang A – Befehlsreferenz `neurogrid`

Aufruf: `neurogrid [--lang zh|en] [--debug] <Befehl> …` (auch `python -m neurogrid`, `uv run neurogrid`). Globale
Optionen: `--lang` (Sprache der Meldungen; sonst `NEUROGRID_LANG`, dann Systemsprache), `--debug` (bereinigter
Traceback bei internen Fehlern), `--help`.

- `neurogrid <Befehl> --help` zeigt die Hilfe in der gewählten Sprache (`--lang zh` bzw. `--lang en` vor dem Befehl,
  sonst `NEUROGRID_LANG`/Systemsprache; NG-N06) [G].
- `--lang` und `NEUROGRID_LANG` nehmen nur `zh` oder `en` an (beim Bericht auch die Liste `zh,en`); alles andere,
  auch `de`, endet mit „Unknown language … Available: zh, en.“ und Exit 2 [G]. Deutsch gibt es nur als Textspalte
  in den Kern-Tabellen (`report/i18n/de.yaml`, `validator_codes.yaml`), nicht als Sprache von CLI oder Bericht
  (`report/texts.py`: `REPORT_LANGUAGES = ("zh", "en")`; A-07, D-10 i).

| Befehl | Argument | Optionen |
|---|---|---|
| `scan` | `PATH` (Ordner oder Datei) | `--out VALUE` (Inventar als JSON), `--show-paths` |
| `check` | `PATH` | `--rulepack VALUE` (Name oder Pfad, wiederholbar), `--config VALUE` (Standard `.neurogrid/neurogrid.toml`), `--out VALUE` (Standard `results.json`), `--strict`, `--as-of YYYY-MM-DD` (Standard heute), `--allow-draft-rulepacks`, `--show-paths`, `--jobs N` (1–64, Standard 1), `--evidence VALUE` (Standard `.neurogrid/evidence.yaml`), `--manifest VALUE` (Standard `.neurogrid/manifest.json`) |
| `convert` | `PATH` | `--to bids` (Pflicht), `--out VALUE` (Pflicht, leer oder fehlend), `--config VALUE`, `--strip-identifying-headers` |
| `report` | `RESULTS_FILE` | `--lang VALUE` (Standard `zh,en`), `--format VALUE` (`html`, `pdf`, `html,pdf`; Standard `html`), `--out VALUE` (Standard neben `results.json`) |
| `manifest` | `PATH` (Ordner) | `--out VALUE` (Standard `.neurogrid/manifest.json`), `--show-paths` |
| `verify` | `PATH` (Ordner) | `--manifest VALUE` (Pflicht), `--show-paths` |

**Exitcodes (A-12):** `check`: 0 keine fehlgeschlagene error-Regel, 1 mindestens eine (auch: Ordner ohne lesbare
Aufnahme), 2 Werkzeugfehler (Bedienfehler, Eingabe nicht gefunden, ungültige Konfiguration). `verify`: 0 gleich,
1 Abweichung, 2 bei ungültigem oder fehlendem Manifest (A-82). `report`: 0; 2 bei fehlender oder ungültiger
`results.json`, unbekannter Sprache oder unbekanntem Format oder PDF-Fehler (z. B. fehlender PDF-Browser, mit Hinweis
auf `install_pdf_browser.py`). `scan`, `convert`, `manifest`: 2 bei Bedien- und Werkzeugfehlern (z. B. Pfad nicht
gefunden). Jeder Befehl endet mit dem festen Satz (A-08).

Werkzeug-Befehle: Abschnitt 5. Prüfbefehle je Phase: 4.0.

---

## Anhang B – Checkliste „Nachbau prüfen“

**Umgebung**
- [ ] `git --version` = 2.51.1; `.gitattributes` greift (Dateien im Arbeitsbaum mit LF)
- [ ] `uv --version` = 0.13.0; `UV` gesetzt
- [ ] `uv python list --only-installed` zeigt 3.11.17 und 3.12.15; System-Python 3.13.7
- [ ] `uv lock --check --offline` → 103 Pakete, Exit 0
- [ ] `.venv`, `.local/venv3.11`, `.local/venv3.13` mit `uv sync --locked --no-build` angelegt; `neurogrid --help` in allen drei

**Generatoren und Statik**
- [ ] `gen_fixtures`, `gen_schemas`, `gen_montage_names`, `gen_docs`, `calibrate` mit `--check` → Exit 0
- [ ] `build_fonts.py --check` → „fonts are reproducible“
- [ ] `linux_pdf_packages.py --check` → Exit 0
- [ ] `ruff check .`, `ruff format --check .`, `mypy --strict src/neurogrid/kernel`, `mypy src/neurogrid tools` sauber
- [ ] `check_matrix_coverage.py` → 166 mit genau einer abschließenden Phase
- [ ] `check_commit_ids.py` → 0 Probleme

**Tests**
- [ ] PDF-Browser installiert, `install_pdf_browser.py --check` → vollständig (290 Dateien)
- [ ] `pytest -q` mit `NEUROGRID_REQUIRE_PDF=1` und `UV` unter 3.11, 3.12, 3.13 grün; Sammlung 3414, Standardlauf 3342
- [ ] Abdeckung: `coverage_gates.py` → Kern ≥ 90 %, Prüfer ≥ 80 % (zuletzt 97,1 % / 97,2 % in P4)
- [ ] `licenses.py` → runtime/dev/docs × allowlist/copyleft ok; `licenses.py --components --download` ok (auf dem
      gemergten 103-Paket-Lock noch nicht protokolliert, 4.7.4)
- [ ] Korpus: `corpus.py fetch` + `verify` → „corpus verified“ (297 Dateien); `pytest -m corpus` → 62 bestanden
- [ ] `pytest -m perf` (NG-N02, Skalierung) unter den Grenzen aus D-14 bzw. A-88

**Ende-zu-Ende**
- [ ] `check` auf `edf_ok` mit `documented.toml` → Exit 0; zwei Läufe byte-gleich; 3.11/3.12/3.13 gleich bis auf `environment`
- [ ] `check` auf `empty` → Exit 1; fehlender Pfad → Exit 2
- [ ] `report --lang "zh,en" --format "html,pdf"` → Exit 0, vier Dateien; ohne PDF-Browser → Exit 2 mit Hinweis
- [ ] `convert --to bids` je Format ohne Validator-Fehler; `manifest` + `verify` → Exit 0

**Auslieferung**
- [ ] `build_docs.py --site-dir site` → „documentation built and checked“, 0 Netzereignisse
- [ ] `notices.py --download --check` → aktuell, 6 „incomplete“ (Exit 1 bis G1)
- [ ] `bundle.py build` beider Plattformen + `bundle.py verify` → Exit 0; zwei Bauten byte-gleich
- [ ] Windows-Reinraum `cleanroom_windows.ps1 … -NoOsAudit` → Exitcodes wie in 4.7.5; im `-Evidence`-Ordner
      `exit-codes.txt`, `<schritt>.out.log`/`.err.log`, `summary.txt`, `temp-left.txt` (leer)
- [ ] Präfixgrenze (A-87): `install.cmd -SkipSignatureCheck -Prefix <102 Zeichen>` → Exit 2, nichts angelegt;
      `<101 Zeichen>` → Exit 0
- [ ] optional: Flugmodus-Test (4.7.5)

**Nur mit dem Projektverantwortlichen / CI (offen)**
- [ ] Push auf `<REPO_URL>`, erster Lauf von `ci.yml`, `offline.yml`, `docs.yml`, `corpus.yml`
- [ ] Bündel-Tests laufen bei jedem Push auf `dev` und `main` grün (D-15; seit Review R10 so konfiguriert,
      `offline.yml` Push `dev`/`main`; erster grüner Lauf auf `dev` steht aus, 4.7.6)
- [ ] Linux-Reinräume (`cleanroom_linux.sh` je Image, Ablehnung `ubuntu:18.04`), `offline_strace_linux.sh`,
      `pdf_debian12.sh` grün (4.7.5)
- [ ] fehlende Lizenztexte abgelegt (D-15), `known_missing.toml` leer
- [ ] zh-Prüfung, STOPP G1, dann `0.1.0`, Tag, `release.yml`, `publish-pypi.yml`, `mirror-gitee.yml`
