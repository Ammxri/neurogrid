# NeuroGrid – Nachbau-Anleitung (technisch)

Diese Anleitung beschreibt, wie NeuroGrid von null auf einem eigenen Windows-11-Rechner wieder aufgebaut wird:
Werkzeuge, Umgebungen, Repository, Arbeitsweise, Phasen P0–P5, Prüfwerkzeuge, Testkorpus und Downloads. Sie ist
technisch; Geschäftsinhalte der PRD stehen hier nicht (A-01). Verweise auf die PRD nennen nur Abschnittsnummern.

**Stand:** Zweig `dev`, Commit `181654e` (27.10.2026): P5 nach Bau, Integration, Abnahme, Review, Fix-Runde, Merge
`55335ca` und Doku-Fix `181654e`. P5 ist gebaut und lokal geprüft; der Workflow `offline` ist auf GitHub grün, die
Testjobs von `ci` sind noch rot (Lauf auf `55335ca`, 4.7.12). Eine zweite Fix-Runde (Zweige `p5-ci2-*`) läuft; ihre
Ergebnisse trägt der Lead nach (Platzhalter `<ERGEBNIS NACH P5-CI2>`). Danach folgt **STOPP G1** (4.7.14).

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
- die G1-Abnahme auf dem Korpus (`tools/acceptance_g1.py`), der Skalierungstest und das zh-Prüfpaket (4.7.8)

**Nur in der CI (GitHub Actions) reproduzierbar:** Linux-Testläufe, Linux-Reinräume, glibc-Ablehnung, strace,
PDF unter Debian 12, Windows-Reinraum mit WFP-Audit (D-09; lokal kein Linux und keine Änderung an
Sicherheitseinstellungen).

**Braucht den Projektverantwortlichen:**

| Was | Wofür | Stand |
|---|---|---|
| Repository `https://github.com/Ammxri/neurogrid` (D-15, 26.10.2026) | CI, Linux (D-07, D-09, D-15) | angelegt und öffentlich; `dev` wird gepusht, CI läuft (4.7.9, 4.7.12) [G]; Push auf `main`, Tag und Release erst nach G1 |
| die PRD selbst (PDF, privat) | nur für die Planung; liegt in `.local/prd/`, nie versioniert (A-01) | beim Projektverantwortlichen |
| Normtexte GB/T 47127, YY/T 2029, ISO/IEC TS 27571 | P7, P8, P10 (D-02, A-55) | nicht vorhanden |
| Konten: Gitee, PyPI/TestPyPI (Trusted Publishing) | Spiegel, Veröffentlichung (D-07, D-15) | nicht bekannt; weder Projektdokumente noch Faktenbasis belegen ein angelegtes Konto [NV] |
| Freigabe von Downloads außerhalb D-06 | CC-BY-4.0-Rechtstext, npm/jsr-Lizenzdateien des Validators (D-15), LGPL-3.0/GPL-3.0-Texte (D-16) | freigegeben und abgelegt (4.7.7) [G] |
| Entscheidung zu den übrigen fehlenden Lizenztexten | 8 Einträge in `license-gate/known_missing.toml` (Abschnitt 8): Teile des Validator-Bündels ohne Version oder Text, libaec/libsz im Linux-h5py-Wheel, Bibliothekstexte von python-build-standalone, zwei Teile der Doku-Seite | offen bis STOPP G1; sperrt das Release |
| Versand der Anfrage an die Validator-Entwickler (D-16) | Ersatz des LGPL-Abschnitts in isomorphic-git | Entwurf liegt privat in `.local/p5/upstream_issue_bids_validator.md`; Versand durch den Projektverantwortlichen [NV] |
| muttersprachliche zh-Prüfung | alle zh-Texte (A-07, STOPP G1); Prüfpaket aus `tools/zh_review_package.py` (4.7.8) | offen |

### 0.3 Platzhalter

| Platzhalter | Bedeutung |
|---|---|
| `<Projektordner>` | Wurzel des Repositorys (enthält `pyproject.toml`) |
| `<Benutzerordner>` | Profilordner des Windows-Benutzers (`%USERPROFILE%`) |
| `%APPDATA%`, `%LOCALAPPDATA%`, `%TEMP%` | Windows-Standardordner (PowerShell: `$env:APPDATA` usw.; Git Bash: `$APPDATA` usw.) |
| `<uv>` | Pfad zu `uv.exe`, siehe 1.3 Schritt 3 |
| `<Ziel>` | ein beliebiger, leerer Ausgabeordner |
| `<REPO_URL>`, `<owner>/<repo>` | öffentliches Repository; für dieses Projekt `https://github.com/Ammxri/neurogrid` bzw. `Ammxri/neurogrid` (D-15). In der Nutzerdoku bleibt `<REPO_URL>` bis zum Release stehen (`tools/release_check.py` sperrt es außerhalb von `docs/umsetzung`) |
| `<v>` | Paketversion, heute `0.1.0rc1` |
| `<ERGEBNIS NACH P5-CI2>` | **vom Lead auszufüllen:** Ergebnis der zweiten CI-Fix-Runde (Testzahlen, CI-Läufe) |

Alle Befehle laufen im `<Projektordner>`, wenn nichts anderes dasteht.

### 0.4 Belegstufen

Wichtige Angaben tragen eine Belegstufe:

| Kürzel | Bedeutung |
|---|---|
| **[G]** | geprüft: Befehl ausgeführt bzw. Datei oder Quelltext gelesen. Ohne Zusatz gilt für die Abschnitte bis P4 der Stand `19bd93c` (26.10.2026), für P5 der Stand `181654e` (27.10.2026). „[G, CI 55335ca]“ heißt: in den öffentlichen Annotationen bzw. Job-Ergebnissen eines GitHub-Actions-Laufs auf `55335ca` gesehen |
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
| Linux / WSL / Docker | kein Linux; Docker Desktop installiert, Engine nicht genutzt [D] | nicht nötig (D-09: Linux nur über CI; GitHub Actions seit 26.10.2026) |

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
| PowerShell 7, gh, actionlint | – | lokal **nicht** installiert / nicht verwendet; PowerShell 7 läuft nur in der CI (`windows-latest`) | – |

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
- `uv lock --check --offline` → „Resolved 103 packages“, Exit 0 [G, Stand 19bd93c und 181654e; `pyproject.toml` und
  `uv.lock` sind seit `584b7d2` unverändert]. (Bis P4 waren es 84 Pakete.)
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
| `NEUROGRID_NOTICES_WHEELS` | `tests/docs/test_notices.py` | zweiter Ordner mit den gelockten Wheels (befüllt von `tools/notices.py --download`) für einen Worktree ohne eigenes `.local/notices-wheels`; nur absoluter lokaler Pfad (seit `051fafb`) |
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
11. **Debug-Log der Headless Shell:** Kindprozesse schreiben Fehler in `debug.log` neben
    `chrome-headless-shell.exe`; NeuroGrid startet mit `--in-process-gpu`, entfernt beim Start einen vorgefundenen
    `debug.log` (Rest eines abgebrochenen Laufs) und nach dem Lauf einen, den der Lauf angelegt hat; hält ein
    laufender Browser die Datei offen, schneidet der Lauf nur ab, was er angehängt hat (`kernel.pdf._ChildLog`;
    A-85, 4.7.6). Nach Testläufen
    `install_pdf_browser.py --check` ausführen; es schlägt fehl, solange ein `debug.log` neben der exe liegt.
12. **Lange Pfade der Headless Shell:** Revision 1243 ist nicht langpfadfähig; ihr Profil reicht 96 Zeichen unter
    den Arbeitsordner. Der Arbeitsordner liegt deshalb im Temp-Ordner (`ng-pdf-XXXXXXXX`); unter Windows darf der
    Temp-Ordner höchstens 84 Zeichen lang sein (`TEMP_PATH_LIMIT`), sonst Exit 2 vor dem Rendern (4.7.6).
13. **PowerShell 7 als Elternprozess:** Ein aus PowerShell 7 gestartetes Windows PowerShell 5.1 (GitHub-Standardshell,
    Windows Terminal) erbt den Modulpfad von PowerShell 7; dann fehlt `Get-FileHash`. Installer, Reinraumskript und
    `offline.yml` hashen deshalb über .NET `System.Security.Cryptography.SHA256` (4.7.11). Lokal nachstellen ohne
    pwsh: siehe 4.7.11 (Bündel).
14. **Kein Commit während `pytest -m bundle`:** Ohne `SOURCE_DATE_EPOCH` gilt die Commit-Zeit von HEAD; ein Commit
    während des Laufs macht die beiden Linux-Bauten ungleich (tar-mtimes) [D].
15. **Energiesparen bei Messungen:** Modern Standby hält die Prozesse an, `time.perf_counter` läuft weiter. Messläufe
    (`-m perf`, Benchmark) nur auf einem wach gehaltenen Rechner (4.7.8).
16. **`tools/notices.py --check` ohne `--wheelhouse` oder `--download`** sucht keine Wheels und endet mit Exit 2
    („files missing“); immer `--wheelhouse .local/notices-wheels` angeben oder `--download` (4.7.4).
17. **Negative Beispiele von Werkzeugaufrufen in Testdateien** aufteilen (`"tools/" + "licenses.py --release"`), sonst
    hält `tests/docs/test_notices.py::test_every_named_option_of_the_gate_tools_exists` sie für echte Aufrufe.
18. **Ordnergröße unter NTFS:** `os.stat` meldet für einen Ordner, über den der NTFS-Cache nichts weiß, Größe 0 und
    nach einem Auflisten die Indexgröße. Schnappschüsse von Ordnerbäumen daher erst auflisten, dann `stat` (4.7.6).
19. **`taskkill /F /T` kehrt zurück, bevor die Prozesse beendet sind;** vor dem Aufräumen auf jede genannte PID
    warten (4.7.6).

---

## 2 Repository von null

### 2.1 Herkunft

- **Weg A (empfohlen): vorhandenes Repository.** `git clone https://github.com/Ammxri/neurogrid.git neurogrid`,
  dann `git checkout dev` (öffentlich seit 26.10.2026, D-15; dort liegt bis G1 nur `dev`). Ohne Netz eine Kopie des
  lokalen Repositorys: `git clone --no-hardlinks <Projektordner> <Ziel>` (Git Bash). Die Historie enthält alles außer
  `.local/`.
- **Weg B: neu aufbauen.** Abschnitt 3 und 4 beschreiben, in welcher Reihenfolge was gebaut wurde und welche
  Entscheidungen es formten. Der Code selbst ist die Referenz; Weg B ist nur mit dem Repository als Vorlage
  realistisch.

`.local/` wird nie versioniert (A-01). Sie enthält: PRD (`.local/prd/`), Korpus, venvs 3.11/3.13, Lizenz-venvs,
Logs und Messungen (`.local/perf/`), Review-Material. Nach einem Klon fehlt sie und wird mit den Schritten in 1.4,
4.7.3 und 6 neu befüllt; PRD und Normtexte legt der Projektverantwortliche selbst ab.

### 2.2 Zweige und Ablauf in git

- `main`: nur der erste Doku-Commit `75e05a6`; Releases kommen später von `main` (Release-Gate).
- `dev`: Arbeitszweig (D-07, D-09). Remote `origin` = `https://github.com/Ammxri/neurogrid.git` [G]; seit dem
  26.10.2026 wird nur `dev` gepusht (D-15), `main`, Tags und Releases erst nach G1. Jeder Push auf `dev` startet
  `ci.yml` und `offline.yml` (4.7.12).
- Bereichszweige je Phase (`p4-*`, `p5-*`) in eigenen Worktrees, nach dem Merge gelöscht (3.5); in P5 zusätzlich
  Integrations- (`p5-int-*`), Abnahme- (`p5-acceptance`), Lizenztext- (`p5-licence-texts`) und Fix-Zweige
  (`p5-fix-*`, `p5-ci2-*`).
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
| `LICENSE`, `NOTICE`, `LICENSES/` | Apache-2.0, Lizenzhinweis, Lizenztexte der eigenen Dateien: `Apache-2.0.txt`, `CC-BY-4.0.txt` (D-15), `OFL-1.1.txt`, `LicenseRef-NeuroGrid-Reproduced-Notices.txt` (R26) [G] |
| `REUSE.toml` | Lizenz je Pfad (2.7) |
| `THIRD_PARTY_NOTICES.txt` | erzeugt von `tools/notices.py` (A-86) |
| `README.md`, `DATA_SOURCES.md` | Kurzbeschreibung zh/en; Herkunft von Fixtures und Korpus |
| `mkdocs.yml`, `docs/en`, `docs/zh`, `docs/_data`, `docs/assets` | Nutzerdoku (A-86) |
| `docs/umsetzung/` | Matrix, Konzept, Entscheidungen, Fortschritt, diese Anleitung (Deutsch, nicht Teil der Website) |
| `license-gate/` | `allowlist.txt`, `exceptions.txt`, `components.toml`, `known_missing.toml`, `network_baseline.json`, `licence_texts.toml` (Herkunft geladener Texte), `third_party/bids-validator-3.0.2/` (Manifest und Lizenztexte der gebündelten npm/jsr-Pakete, D-15/D-16), `third_party/mkdocs-material-9.7.7/manifest.toml` (Prüfung der Doku-Seite, R19) |
| `packaging/` | Installer (`install.cmd`, `install.ps1`, `install.sh`), `README.bundle.txt`, `release-notes.md`, `gitee-release.md` (R15), `bundle_lock.json`, `ci/*` (Reinraum, strace) |
| `.github/workflows/` | `ci.yml`, `offline.yml`, `corpus.yml`, `docs.yml`, `release.yml`, `publish-pypi.yml`, `mirror-gitee.yml` |
| `src/neurogrid/` | Paket (2.4) |
| `tests/` | Tests und Fixtures |
| `tools/` | Werkzeuge außerhalb des Pakets (Abschnitt 5) |

Umfang [G, 181654e]: 540 versionierte Dateien (davon 111 unter `license-gate/third_party/`); 20 764 Zeilen Python
in `src`, 45 738 in `tests` (`wc -l`); 32 Fixture-Ordner. (Stand `19bd93c`: 413 Dateien, 19 738 / 38 199 Zeilen.)

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

### 2.5 `pyproject.toml` (Stand 181654e, seit `584b7d2` unverändert)

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

- `uv.lock`: `version = 1`, `revision = 5`, 103 Pakete (Stand 584b7d2, unverändert bis 181654e) [G]. Einzige
  Versionsgabelung bis P4: contourpy 1.3.3 (3.11) / 1.4.0 (≥ 3.12).
- Laufzeitmenge für Lizenz-Gate, Notices, Bündel und Netzwerk-Scan **immer**:
  `uv export --frozen --no-default-groups --no-emit-project` (A-86). Stand 181654e: Laufzeitexport 66 Pakete; ein
  bloßes `--no-dev` ergibt 82 Pakete (mit den Doku-Werkzeugen) [G]. Die Werte 62/78 wurden im docs-Bereich gemessen,
  vor dem pdf-Merge (playwright, pypdf, greenlet, pyee) [D]. Der Test
  `tests/packaging/test_bundle_wheels.py::test_runtime_export_holds_no_dev_or_docs_only_package` verlangt seit der
  Integration (`4e0f39a`), dass der Export genau dem Abschluss der Laufzeitabhängigkeiten in `uv.lock` entspricht:
  psutil steht in der Gruppe `dev`, ist aber auch Laufzeitabhängigkeit von pyprep und mne-icalabel und gehört deshalb
  ins Bündel (4.7.6). Nachzählen (Git Bash):
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
  keine Abhängigkeit). Seit der Fix-Runde verhält sich der eigene Test wie `reuse lint`: jeder Text in `LICENSES/`
  muss benutzt sein, Kopfzeilen in Lizenzdateien zählen nicht (R27). `THIRD_PARTY_NOTICES.txt` steht unter
  `CC-BY-4.0 AND LicenseRef-NeuroGrid-Reproduced-Notices` (R26). `LICENSES/CC-BY-4.0.txt` ist seit `ce1ab9c` abgelegt
  (D-15, 4.7.7).
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
| `license-gate/known_missing.toml` | fehlende Lizenztexte (8 Einträge, sperren das Release; Abschnitt 8) | von Hand |
| `license-gate/licence_texts.toml` | Herkunft (URL, Größe, SHA-256, Entscheidung) jedes geladenen Lizenztexts | von Hand, von `tests/docs/test_licensing.py` geprüft |
| `license-gate/third_party/*/manifest.toml` | geprüfte Drittanbieter-Teile mit Texten (Validator-Bündel, Doku-Theme) | einmalig erstellt (Skripte nur im Scratchpad [NV]), von `notices.py --check` und `build_docs.py` geprüft |
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

- `ENTSCHEIDUNGEN.md`: geprüfte Fakten, D-01..D-16 (Entscheidungen des Projektverantwortlichen), A-00..A-88
  (Annahmen; je Phase ein Block „Annahmen aus der Umsetzung von Px“).
- P5 bringt A-84 Bericht, A-85 PDF, A-86 Dokumentation/Meldungen/Notices/Lizenzen, A-87
  Bündel/Signatur/Installation/Workflows und A-88 Abnahme. Grundlage sind die verbindlichen Vorgaben B1–B6 des Leads
  sowie die `decisions_for_docs` der Bereiche, der Integration und der Fix-Runde; sie stehen in ENTSCHEIDUNGEN
  („Annahmen aus der Umsetzung von P5“), zusammen mit den Hinweisen an älteren Annahmen (u. a. A-51 Konsole,
  A-54 Arbeitsordner, A-67 Pfade unter Linux).

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
| 8a Integration und Abnahme | Integrationsaufgaben am gemergten Stand, Abnahmeskript, Lizenztexte; je Zweig Bau → unabhängige Verifikation → Reparatur | P5: `p5-int-pdf`, `p5-int-pack`, `p5-acceptance`, `p5-licence-texts` (4.7.6–4.7.8) |
| 9 Adversariales Review | mehrere Prüfrichtungen; jeder Befund wird von einem zweiten Prüfer zu widerlegen versucht (bestätigt / strittig / beabsichtigt / widerlegt), schwere doppelt | P4: 57 Befunde; P5: 30 Befunde R00–R29 (4.7.10) |
| 10 Fixes | Fix-Zweige je Bereich, je Befund ein Regressionstest, Nachprüfung, Reparaturrunde | P4: `p4-fix-*`; P5: `p5-fix-report`, `-linux`, `-bundle`, `-docs`, dazu die CI-Fehler (4.7.11) |
| 11 Gegenprüfung | gemergter Stand auf Rückfälle und neue Fehler aus dem Zusammenspiel | P4: `p4-fix2-*`; P5: die CI auf dem gemergten Stand (`55335ca`), danach `p5-ci2-*` (4.7.12) |
| 12 Doku und Commit | Matrix, ENTSCHEIDUNGEN, KONZEPT, FORTSCHRITT; Commit mit Anforderungs-IDs | P4: `e68e33e`; P5: Zweig `p5-docs` (diese Fassung) |

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
Wegwerf-Klon (`git clone --no-hardlinks --no-checkout <Projektordner> trial`) oder ohne Arbeitsbaum mit
`git merge-tree --write-tree --name-only <zweig-a> <zweig-b>` (listet die Konfliktdateien; so in P5 vor jedem
Integrations-Merge geprüft [D]). Ein Merge ohne Textkonflikt kann trotzdem semantisch brechen (P5: 4.7.11, Merge-
Kopplungen); nach jedem Merge daher die Generatoren mit `--check` und die betroffenen Tests laufen lassen.

### 3.6 Was davon von Hand geht

- **Vollständig von Hand:** Matrix, Konzept, Entscheidungslog, jede Bauphase, alle Prüfbefehle, Commit-Form. Die
  Werkzeuge sind gewöhnliche Python-Skripte.
- **Nur mit Ersatz:** Parallelität (stattdessen Bereiche nacheinander in eigenen Zweigen bauen) und
  Unabhängigkeit von Verifikation und Review. Ersatz: Spezifikation und Vorgaben schriftlich festhalten, jeden
  Bereich zeitversetzt gegen eine Prüfliste je Prüfrichtung durchgehen, jeden Befund mit einem eigenen
  Reproduktionsskript belegen, bevor er behoben wird, und nach dem Merge die Gegenprüfung (Schritt 11) wiederholen.
- Zeitbedarf ist nicht protokolliert [NV]; die volle Suite dauert je Lauf 13–18 min (bis P4), in P5 mit
  `NEUROGRID_REQUIRE_PDF=1` 26–33 min [D].

### 3.7 Commit-Form und Rückverfolgbarkeit (TECH-12, A-43)

- Präfix `feat:` / `fix:` / `docs:` / `chore:`, Anforderungs-IDs in Klammern im Betreff, Text als Stichpunktliste,
  Schlusszeile `Co-Authored-By: …` (wo ein Werkzeug mitgeschrieben hat).
- Vor jedem Commit (PowerShell):
  ```powershell
  .\.venv\Scripts\python.exe tools\check_commit_ids.py --message-file <datei>
  git commit -F <datei>
  ```
- Jeder datierte FORTSCHRITT-Eintrag nennt IDs. Prüfung des ganzen Stands: `tools/check_commit_ids.py` →
  „33 commit(s) and 5 phase entr(y/ies) checked, 0 problem(s)“ [G, 19bd93c]; „146 commit(s) and 5 phase entr(y/ies) checked, 0 problem(s)“ [G, 181654e].
  Eine Annahmenummer (A-xx) allein gilt nicht als Anforderungs-ID; jeder Betreff braucht eine Matrix-ID wie
  TECH-07 [D]. Für einen Zweig: `tools/check_commit_ids.py --since <basis>`.
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
& $PY tools\linux_pdf_packages.py --check                 # ab P5
& $PY tools\install_pdf_browser.py --check                # ab P5, nach jedem Testlauf
& $PY tools\notices.py --wheelhouse .local\notices-wheels --check   # ab P5; Exit 1 bis G1 (8 "incomplete", Abschnitt 8)
& $PY tools\check_matrix_coverage.py
& $PY tools\check_commit_ids.py
```
Volle Suite ab P5: `$env:NEUROGRID_REQUIRE_PDF = "1"; $env:PYTHONWARNDEFAULTENCODING = "1"; & $PY -m pytest -q -p
no:cacheprovider` (mit `UV` gesetzt oder über `uv run --no-sync`, sonst überspringen die uv-Tests).

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

### 4.7 P5 – Bericht, PDF, Doku, Bündel (2026-10-23 bis 10-27; Stand 181654e)

Matrix: schließt NG-F13, NG-F14, NG-F18, CLI-05, REP-00..REP-07, POS-01, POS-02, ARC-05, ARC-06, TECH-05..TECH-08,
TECH-10, NG-N01, NG-N03..NG-N08, CON-01, CON-04, CON-05, V-01, V-06, UF-01, UF-07, UF-08 ab (36), trägt zu UF-02,
CON-02, TECH-01 bei (KONZEPT 6) [G]. Den Stand je Zeile führt die Matrix: jede Zeile, deren Nachweis die
CI-Testjobs sind, steht bis zur zweiten Fix-Runde auf `nicht verifiziert` („umgesetzt, Nachweis ausstehend“: NG-F13,
REP-00, TECH-05, TECH-07, NG-N04, NG-N08, UF-01; 4.7.12); V-01, NG-N07, POS-02 und CON-05 sind `teilweise`, TECH-08
ist `blockiert (extern)`.

#### 4.7.1 Vorgehen

| Datum | Commit | Schritt |
|---|---|---|
| bis 23.10. | – | Spezifikationen report, pdf, docs, bundle, acceptance; Kritiker; Vorgaben B1–B6 (Bericht↔PDF-Vertrag, PDF, Doku/Notices/Lizenzen, Bündel/Signatur/CI, G1-Liste, gemeinsame Dateien) |
| 23.10. 23:47 – 24.10. 00:40 | `8b9c949`, `d3f07ba`, `1dbb23e`, `73bb04b` | paralleler Bau in vier Worktrees (4.7.2–4.7.5) |
| 24.10. 01:28 – 05:10 | `133bb94`, `7c99a82`, `9331600`, `2d41f44` | Reparatur nach unabhängiger Verifikation |
| 24.10. 04:03 – 16:51 | `f10e05b`, `e7e2352`, `23880d2`, `584b7d2` | Merge report → docs → pdf → bundle. `uv.lock` mit 103 Paketen entstand beim pdf-Merge `23880d2` (nach dem docs-Merge `e7e2352` waren es 99); im bundle-Merge `584b7d2` wurden nur `THIRD_PARTY_NOTICES.txt` neu erzeugt und in `pyproject.toml` der Marker `bundle` samt `addopts` ergänzt [G] |
| 26.10. 10:44 – 13:30 | `19bd93c`, `42e129d`, `261cbe4` | D-15 Vorabentscheidungen zu G1; erste Fassung dieser Anleitung; erster Push von `dev` (`42e129d`, 12:57) [G: Reflog von `origin/dev`]; D-16 (LGPL-Abschnitt im Validator) und Repository-URL |
| 25.–26.10. | Zweige `p5-int-pdf` (`3c3813d`), `p5-int-pack` (`6986940`), `p5-acceptance` (`1ed26e2`), `p5-licence-texts` (`9625233`) | Integration, Lizenztexte, G1-Abnahme; je Zweig Bau, unabhängige Verifikation, Reparatur (4.7.6–4.7.8) |
| 26.10. 15:30 – 15:50 | `a702660`, `8394c5e`, `2ad5710`, `ce1ab9c`, `051fafb`, `c3be509` | Merge in dieser Reihenfolge, Merge-Fix `.env.example`, GitHub-Annotationen; Push (17:05) und CI-Lauf auf `c3be509` (4.7.9) |
| 26.10. | – | Review mit vier Prüfrichtungen: 30 Befunde R00–R29 (4.7.10) |
| 26.10. bis 22:17 | Zweige `p5-fix-report` (`c9a536a`), `p5-fix-linux` (`191a62a`), `p5-fix-bundle` (`d42bbf4`), `p5-fix-docs`; Merges `28de466`, `2e1e24e`, `e204c7b`, `862de1d` | Fix-Runde: Review-Befunde und CI-Fehler von `c3be509` (4.7.11) |
| 26.10. 22:21 – 27.10. 01:57 | `55335ca`, `181654e` | zwei Merge-Fixes (semantische Konflikte); CI-Lauf auf `55335ca` (4.7.12) |
| ab 27.10. | Zweige `p5-ci2-chrome-log`, `p5-ci2-linux-p2`, `p5-ci2-linux-pdf`, `p5-ci2-win-runner` | zweite CI-Fix-Runde: `<ERGEBNIS NACH P5-CI2>` |

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
  Die Grenzen hat A-88 auf dem gemergten Stand mit echten Schriften und PDF festgelegt (4.7.8).
- Suite im Bereich nach Reparatur: 2831 bestanden, 14 übersprungen, 69 abgewählt in 895,85 s [D].
- Spätere Änderungen: Schreiben alles oder nichts auch beim Umbenennen, Seitenbreite, Spaltenanteile,
  Überschriften von Abschnitt 3, Diagrammgrenzen (Fix-Runde R00, R01, R03–R05; 4.7.11).

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
  `"$PY" tools/linux_pdf_packages.py --check` → „pdf_linux_packages.json matches Playwright“ [G]. Die CI installiert
  auf `ubuntu-24.04` die Liste `linux_pdf_packages.py ubuntu24.04` per apt; der Job `pdf-debian12` nutzt die
  Debian-12-Liste und war auf `55335ca` grün [G, CI 55335ca].
- Spätere Änderungen: Arbeitsordner des Browsers im Temp-Ordner, Längengrenzen, Aufräumen abgebrochener Läufe,
  `--out` vor dem Browserstart geprüft, Glyph-Kopien in GSUB/GPOS/GDEF (Integration, 4.7.6); Ligatur-Zwillinge,
  ausführbarer Installationshinweis, `~` im Installer, Kodierung des ldd-Laufs (Fix-Runde R02, R06, R07, CI; 4.7.11).

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
  & $PY tools\notices.py --download --check                         # erwartet: "up to date" + 8 "incomplete: …", Exit 1
  & $PY tools\notices.py --wheelhouse .local\notices-wheels --check # dasselbe offline aus dem Cache
  ```
  Exit 1 ist bis G1 gewollt: `license-gate/known_missing.toml` hat heute 8 Einträge (Abschnitt 8) [G, 181654e]; beim
  Bau waren es 6. Ohne `--wheelhouse` und ohne `--download` endet `--check` mit Exit 2 („files missing“), weil der
  Cache nur mit `--download` gelesen wird [D]. Datei heute 1 664 921 B [G, 181654e] (beim Bau 1 398 869 B); „129
  wheels, 4 bundle parts“ [D]. **Neu erzeugen nach jeder Änderung** an `uv.lock`, `license-gate/components.toml`,
  `known_missing.toml`, `licence_texts.toml`, einem `third_party/*/manifest.toml` oder `packaging/bundle_lock.json`:
  `& $PY tools\notices.py --wheelhouse .local\notices-wheels --out THIRD_PARTY_NOTICES.txt`; die Tests in
  `tests/docs/test_notices.py` erzwingen das.
- Lizenz-Gate mit Doku-Gruppe (PowerShell):
  ```powershell
  $PY = ".\.venv\Scripts\python.exe"
  $env:UV = "<uv>"                                   # nur, wenn uv nicht im PATH liegt
  & $PY tools\licenses.py                            # runtime/dev/docs × allowlist/copyleft: je "ok"
  & $PY tools\licenses.py --components --download    # oder --wheelhouse <dir> je Ziel; braucht kein uv
  ```
  Im Bereich (Lock vor dem Merge) runtime/dev/docs × allowlist/copyleft ok [D]. Auf dem 103-Paket-Lock (Zweig
  `p5-acceptance`, `228ec49`): runtime/dev/docs × allowlist/copyleft ok, `--components --wheelhouse
  .local/notices-wheels` → „components (129 wheels, 4 bundle parts, win_amd64, linux_x86_64): ok“ [D]. Der CI-Job
  „licence gate and scan of the installed runtime packages“ (`tools/licenses.py` für runtime/dev/docs und
  `tools/scan_runtime_network.py`) war auf `55335ca` grün [G, CI 55335ca]; `--components` läuft in keinem Workflow.
  `licenses.py` ist seit der Abnahme in `stage_commands()`/`run_stages()` geteilt, damit
  `tests/acceptance/test_license_gate.py` beide Stufen an synthetischen Distributionen prüfen kann (dazu der CON-01-Test
  der Sperrliste `metabci`, `openvibe`, `eegprep`).
- `core.yaml` 0.1.0 → 0.1.1 (Quellenangabe verweist auf `metrics.md`).
- Suite nach Reparatur (mit `UV` gesetzt): 2908 bestanden, 13 übersprungen, 65 abgewählt in 957,69 s [D]. Browser-Tests
  (`-m browser`) liefen vor dem Merge nur in einem Ersatzaufbau; nach dem Merge laufen sie in der vollen Suite
  (Integration: 4 bestanden in 42 s [D]).
- Spätere Änderungen: geprüfte Teile der Doku-Seite (R19), Notices-Lizenz (R26), Ort der D-16-Texte (R27),
  Adresse und SHA-256 von `install_pdf_browser.py` in `installation.md` (R28), strace-Regel auf der
  Datenschutzseite (R25, `181654e`) (4.7.11).

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
  die Spezifikationsprobe mit den PDF-Paketen 65 bzw. 64 Wheels, 233,1 bzw. 261,9 MiB [D]. `bundle.py sizes` ist auf
  dem gemergten Stand nicht protokolliert [NV].
- Gemessen [D]: vor dem PDF-Merge Windows-zip 246 087 316 B (3510 Einträge), Linux-tar.gz 275 211 566 B, zwei Bauten je
  Plattform byte-gleich, Bau 14–19 s (Windows, warmer Cache) bzw. ≈ 55 s (Linux); gemergtes `0.1.0rc1`-Windows-Bündel
  in einer Probe 309 696 896 B, `max_relative_install_path` 148, Präfixgrenze 101.
- Gemessen auf dem Integrationszweig `p5-int-pack` (`cb19b17`, Bau wie in `offline.yml`,
  `SOURCE_DATE_EPOCH=1793008170` = Commit-Zeit) [D]: `uv build` 9 s, `build_docs.py` 33 s, `bundle.py build --platform
  win_amd64 … --cache .local/bundle-cache` 15 s (warmer Cache), `verify` 3 s; `neurogrid-0.1.0rc1-offline-win_amd64.zip`
  311 242 440 B (296,8 MiB), SHA-256 `2aede1125ca640e80b2b05255b7375327ccbb118403ed037618b757c7af9a3d4`, 3514 Einträge.
  Ein unabhängiger Nachbau aus einem `git archive` ergab dasselbe Wheel und sdist und ein zip, das sich nur in
  `BUNDLE.json` (`git_commit` = null ohne git) und der daraus folgenden `SHA256SUMS` unterscheidet. Ohne `UV` endet
  `bundle.py` mit Exit 2 („uv not found: put uv on PATH or set UV“).
- **Windows-Reinraum lokal:**
  ```powershell
  powershell -NoProfile -ExecutionPolicy Bypass -File packaging\ci\cleanroom_windows.ps1 -Archive <zip> -Evidence <Ziel> -NoOsAudit
  ```
  Optionen: `-Root`, `-Installer cmd|pwsh`, `-PdfBrowserZip <zip> -PdfBrowserSha256 <hex>`, `-Keep`. Gemessen [D]:
  Installation 116–135 s, ganzer Lauf 198–219 s, 16 257 Dateien / 641,9 MiB, 0 Reste in TEMP; Exitcodes: install 0,
  verify-only 0, scan 0, check-edf 0, check-edf-plus-d 0, check-bdf 0, check-brainvision 1, check-eeglab 1,
  check-bids 0, convert 0, check-converted 0, manifest 0, verify 0, report-html 0, report-pdf-ohne-Browser 2,
  Bedienfehler 2. (Gemessen vor dem PDF-Merge.)
  **Nach der Integration** (`234dd1a`/`2b70ea5`) installiert das Skript in ein Präfix von genau der Grenze
  (249 − `max_relative_install_path`, aufgefüllt als `<Raum>\安装 目录\NeuroGrid___…`), nachdem ein Präfix von Grenze + 1
  mit Exit 2 abgelehnt wurde (Meldung nennt Länge und Grenze, kein Ordner angelegt). In beiden Zweigen (mit und ohne
  `-PdfBrowserZip`) muss `report --format pdf` mit leerem `NEUROGRID_PDF_BROWSER_DIR` Exit 2 liefern, nichts schreiben
  und den Installationshinweis des Bündels ausgeben. Lauf mit Browser-zip (PowerShell, kein Eingriff in
  Sicherheitseinstellungen) [D]:
  ```powershell
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File packaging\ci\cleanroom_windows.ps1 -Archive <zip> -Evidence <Ziel> -NoOsAudit -PdfBrowserZip <chrome-headless-shell-win64.zip> -PdfBrowserSha256 7aec872f3090e639c4237467624ea863c20fe2878914c93a6556bdbb52aa6c4c
  ```
  Ergebnis auf `cb19b17` [D]: install-over-limit 2 (81,7 s, davon die `SHA256SUMS`-Prüfung von 3513 Dateien),
  install 0 (81,9 s, mit PDF-Browser aus dem zip), install-verify-only 0, scan 0, check-edf 0, check-edf-plus-d 0,
  check-bdf 0, check-brainvision 1, check-eeglab 1, check-bids 0, convert 0, check-converted 0, manifest 0, verify 0,
  report-html 0, report-pdf 0 (20,2 s), report-pdf-without-shell 2 (3,1 s), usage-error 2; installiert 16 826 Dateien,
  774,9 MiB, 5171 Module mit Bytecode, längster Pfad unter dem Präfix 148; 0 Reste in TEMP; Skript 275 s (mit
  Aufruf 293 s). Den erwarteten Hinweistext baut das Skript seit der Fix-Runde wie NeuroGrid (R07, 4.7.11).
  In der CI lief der Windows-Reinraum auf `55335ca` grün unter Windows PowerShell 5.1 und PowerShell 7, jeweils mit
  WFP-Audit und PDF [G, CI 55335ca].
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
- **Linux und CI** (nur auf CI-Runnern mit Docker, D-09; lokal nie gelaufen; im Workflow `offline` auf `55335ca` alle
  Jobs grün [G, CI 55335ca], 4.7.12), Git Bash bzw. bash:
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
  PATH, Registry oder Profil. Unsignierte Entwicklungsbündel brauchen `-SkipSignatureCheck`. Stand nach der
  Fix-Runde [G: Quelltext `install.ps1`, `install.sh`; Verhalten D: Tests der Fix-Runde]:
  - Ein cosign im PATH oder über `-Cosign`/`--cosign` prüft immer; lehnt es ab, endet die Installation mit Exit 4, auch
    mit dem Schalter. Der Schalter lässt nur eine Installation **ohne** cosign weiterlaufen (R16, wörtliche Lesart von
    D-15; Bestätigung bei G1).
  - Nach „signature verified: <Identität>“ fordern beide Installer auf, die Identität mit der in den Release-Notes
    auf `https://github.com/Ammxri/neurogrid/releases` zu vergleichen (R12, Entscheidung des Leads: die Prüfung im
    Archiv bleibt eine Integritätsprüfung, dokumentierte Grenze).
  - Windows-Präfix nur als Laufwerk + `:` + Trenner auf einem lokalen Laufwerk (kein Netzlaufwerk); `-Cosign` wird
    zum vollen Pfad der genannten Datei aufgelöst, nie über PATH (R17).
  - Eine gescheiterte Installation hinterlässt das Ziel wie vorgefunden (R14).
  - Konsolenausgabe und Ausgabe der aufgerufenen Programme zeigen `%LOCALAPPDATA%` und `~` (Windows, auch 8.3-Namen)
    bzw. `${XDG_DATA_HOME}` und `~` (Linux) statt Benutzerordnern (R13, Nachprüfung V2).
  - Hashes unter Windows über .NET `SHA256`, nicht `Get-FileHash` (CI-Fehler, 1.6 Punkt 13).
- **Signatur (D-10 g, D-15):** Sigstore keyless nur in `release.yml`; Prüfung vor der Übertragung auf einem vernetzten
  Rechner:
  ```bash
  cosign verify-blob SHA256SUMS --bundle SHA256SUMS.sigstore.json \
    --certificate-identity https://github.com/<owner>/<repo>/.github/workflows/release.yml@refs/tags/v<v> \
    --certificate-oidc-issuer https://token.actions.githubusercontent.com
  sha256sum --check --ignore-missing SHA256SUMS
  ```
  Windows: `(Get-FileHash <datei> -Algorithm SHA256).Hash.ToLower()` mit der Zeile in `SHA256SUMS` vergleichen (in
  einem eigenen PowerShell-Fenster; ein aus PowerShell 7 gestartetes 5.1 findet `Get-FileHash` nicht, 1.6 Punkt 13).
- **Weitere Werkzeuge:** `tools/release_check.py`, `tools/scan_runtime_network.py` (gemessen **vor dem PDF-Merge**,
  ohne playwright, pypdf, greenlet, pyee: 61 Distributionen, 79 Dateien mit Fundstellen, 0 Probleme [D]; auf dem
  gemergten Stand im CI-Job „licence gate and scan of the installed runtime packages“ grün [G, CI 55335ca], Zahlen dort
  nicht festgehalten), `tools/strace_check.py` (Abschnitt 5).
- **Workflows** (alle Actions per Commit-SHA gepinnt, Abschnitt 7) [G: `on:`-Blöcke]: `ci.yml` (Push dev/main, PRs;
  Jobs `test`, `compare`, `traceability`, `licenses`, `powershell51`, `pwsh`, **kein Bündel-Job**), `offline.yml`
  (Push dev/main, Dispatch, Aufruf aus `release.yml`; Jobs `build`, `offline-strace`, `cleanroom-linux`, `glibc-refusal`,
  `pdf-debian12`, `cleanroom-windows`), `docs.yml` (Push main, PRs, Dispatch), `corpus.yml` (Push main, Dispatch; ruft
  `tools/acceptance_g1.py --corpus .local/corpus --out .local/acceptance/g1` auf), `release.yml` (Tag `v*` und
  Dispatch, nur Entwurf), `publish-pypi.yml` (Dispatch, Trusted Publishing), `mirror-gitee.yml` (Dispatch/Release,
  `vars.GITEE_MIRROR`; seit R15 mit dem Job `gitee-release`). **Gelaufen** sind seit dem ersten Push am 26.10.2026
  `ci.yml` auf `dev` (unter anderem auf `c3be509` und `55335ca`) und – nachdem R10 den Auslöser auf `dev` erweitert
  hatte – der Workflow `offline` auf `55335ca` (Lauf 40403791782; 4.7.9, 4.7.12); `docs.yml`,
  `corpus.yml`, `release.yml`, `publish-pypi.yml` und `mirror-gitee.yml` sind noch nie gelaufen (nur `main`, Tag
  oder Dispatch) [NV]. Seit `c3be509` folgen jedem pytest-Schritt in `ci.yml`, `docs.yml` und `offline.yml`
  Annotationsschritte mit `tools/junit_annotations.py` (dort zwei: 10 Fehler, Zählung), seit der Fix-Runde (`98f0d92`)
  fünf (Fehler 1–10, 11–20, 21–30, 31–40, Zählung) [G: `git show c3be509`, Workflows].
- Langsamer Test: `uv run pytest -m bundle tests/packaging/test_bundle_real.py` (braucht `site/`, Notices,
  `tools/install_pdf_browser.py`; im Bereich 3 bestanden in 392,6 s; nach der Integration 4 Tests, 4 bestanden in
  437,87 s auf `2b70ea5` [D]). Seit `8d93c19` ist er der letzte Schritt des Jobs `build` in `offline.yml`
  (`NEUROGRID_BUNDLE_CACHE="$RUNNER_TEMP/bundle-cache" uv run --no-sync python -m pytest -m bundle -p no:cacheprovider
  tests/packaging/test_bundle_real.py`; unter Linux wird der Windows-Reinraumtest übersprungen); auf `55335ca` grün
  [G, CI 55335ca].
- Suite im Bereich (Bau-Commit `73bb04b`, vor der Reparatur `2d41f44`): 2864 bestanden, 13 übersprungen, 68 abgewählt
  in 1118,97 s [D]; für den Reparaturstand ist keine volle Suite protokolliert [NV]. `tests/packaging` unter
  3.11/3.12/3.13 je 157 bestanden [D].
- **Optionaler Flugmodus-Test (für den Projektverantwortlichen, nicht durchgeführt):** Bündel bauen und mit
  `tools/bundle.py verify` prüfen; Netz trennen (Flugmodus); `install.cmd -SkipSignatureCheck -Prefix <kurzer Pfad>`;
  dann `<Präfix>\neurogrid.cmd check tests\fixtures\synthetic\edf_ok --config tests\fixtures\documented.toml --out r.json`
  und `report r.json --lang "zh,en" --format html`; erwartet Exit 0 und beide Berichte. Den OS-Nachweis mit WFP-Audit
  macht nur die CI (keine Änderung an Sicherheitseinstellungen des eigenen Rechners).

#### 4.7.6 Integration (Zweige `p5-int-pdf` und `p5-int-pack`)

Beide Zweige gingen von `584b7d2` aus, je mit eigenem Worktree und `uv sync --locked --no-build`; keine Downloads
(Headless Shell 1243 schon in `%LOCALAPPDATA%\NeuroGrid\pdf-browser`, Bündel-Cache vorhanden) [D]. Ablauf je Zweig:
Bau → unabhängige Verifikation → Reparatur (Commits in 4.7.1).

**`p5-int-pdf` (A-85, A-54, A-27; TECH-07, CLI-05, NG-N03, NG-N05)** [D, Quelltext G]:
- **P1 Prüfung des Browser-Ordners:** Ein Test meldete einmal einen geänderten Ordner `hyphen-data` (0 → 12 288 B),
  ohne dass Chromium schrieb. Ursache gemessen: unter Python 3.12/Windows 11 meldet `os.stat` für einen Ordner ohne
  NTFS-Cache-Eintrag Größe 0, nach dem Auflisten die Indexgröße (Doppelschnappschuss kalter Systemordner: 30–75
  Abweichungen; „erst auflisten, dann stat“: 0). Keine Produktänderung. Neue Hilfen in `tests/conftest.py`:
  `folder_content()` (Einträge, Größe nach dem Auflisten, mtime, SHA-256), `fresh_shell()` (Kopie der installierten
  Shell in einen neuen kurzen Ordner), `short_folder()`. Messmethode: Änderungsbeobachter mit `ReadDirectoryChangesW`
  (ctypes) auf einer `shutil.copytree`-Kopie; Kopieren der Shell (291 Dateien, 283 MB) 0,5 s, Hashen 3,9 s.
- **P2 Arbeitsordner des Browsers:** Reproduziert auf `584b7d2`: `report --format pdf --out <195 Zeichen>` aus einem
  leeren Ordner ergab Exit 0, aber ein `debug.log` (23 091 B, lokale Pfade) im aktuellen Ordner; bei 210 Zeichen
  Exit 2 mit dem irreführenden Hinweis auf den Installer. Lösung: `kernel.pdf.browser_work()` legt einen privaten
  Ordner `ng-pdf-XXXXXXXX` in `tempfile.gettempdir()` an (nie unter `--out`, nie `ms-playwright`), entfernt ihn im
  `finally`; Treiber, Browser und Kindprozesse laufen mit ihm als aktuellem Ordner (`driver_environment` wechselt mit
  `os.chdir` und stellt zurück). Grenzen unter Windows: Arbeitsordner ≤ 100 Zeichen (`WORK_PATH_LIMIT`), Temp-Ordner
  ≤ 84 (`TEMP_PATH_LIMIT = 100 − 1 − len("ng-pdf-") − 8`); sonst Exit 2 mit `errors.pdf.work_path_too_long` und
  `errors.pdf.temp_hint`, ohne Temp-Ordner `errors.pdf.temp_unusable`; geprüft in `preflight` vor dem Rendern.
  Gemessene Längen des Arbeitsordners: bis 160 sauber, 170–200 Cache-Fehler im `debug.log` neben der exe, ab 210
  Startfehler; tiefster Profilpfad 96 Zeichen. Danach: `--out` mit 195, 210, 240 Zeichen → Exit 0, aktueller Ordner
  leer. `check` und `convert` behalten ihren Arbeitsordner neben der Ausgabe.
- **P3 Glyph-Kopien:** `kernel.fonts.GlyphCopies` trägt jede Kopie überall ein, wo ihr Original in GSUB, GPOS und
  GDEF steht (Coverage, Klassen, Paarsätze, Ersetzungen, Ligaturen, Kontextregeln Format 1–3, Extensions); eine
  Ersetzung einer Kopie liefert eine eigene Kopie (Suffix), Ligaturausgaben `.L<len><suffix>`. Schriften mit nicht
  kopierten Tabellen (CFF, COLR, SVG, `kern`, `morx` …) werden abgelehnt. Gemessen bei 100 px: „T–T L–L“ Regular
  337,8125 px mit und ohne Kopie (vorher 358). Die ausgelieferten Schnitte nutzen nur GSUB 1/3/4 und GPOS 1/2/4.
- **Reparatur** (`3c3813d`): Jeder Arbeitsordner (`run-*` und `ng-pdf-*`) enthält `neurogrid-work.lock` (Inhalt
  `NeuroGrid work folder\n`, gesperrt mit `msvcrt.locking` bzw. `fcntl.flock`); `kernel.safety.remove_leftovers`
  entfernt beim nächsten Start im selben Basisordner Ordner abgebrochener Läufe (Inhalt zuerst, Sperrdatei zuletzt).
  Ein beim Start vorgefundener `debug.log` neben der Shell wird entfernt. `report.output.check_output_folder` prüft
  `--out` vor dem Browserstart (`output.is_directory`, `output.not_writable`, Exit 2, nichts geschrieben). Gemessen:
  `taskkill /F /T` kehrt vor dem Ende der Chromium-Prozesse zurück; der Hard-Kill-Test wartet je PID
  (`OpenProcess(SYNCHRONIZE)` + `WaitForSingleObject`).
- Volle Suite nach Reparatur (`NEUROGRID_REQUIRE_PDF=1`): 3349 bestanden, 21 übersprungen, 72 abgewählt in 1570 s.

**`p5-int-pack` (A-87; TECH-05, CON-02, UF-08, V-01)** [D]:
- **K1** `tests/packaging/test_workflows.py` prüft jeden Aufruf `tools/<name>.py` in Workflows, `packaging/ci/*`,
  `install.sh` und `install.ps1` gegen den echten argparse-Parser des Werkzeugs (aus seinem `main()`). Die
  Verifikation fand eine Lücke (Optionen zwischen zwei gequoteten Argumenten verschwanden); Reparatur `cf01d2c` mit
  Sicherheitsnetz und Mutationstest.
- **K2** `installation.md` (en/zh) nennt die Windows-Präfixgrenze (148 → 101) und das fehlende `dbm.ndbm` unter Linux.
- **K3** `tests/packaging/test_install_ps1.py` arbeitet in einem kurzen Ordner unter dem System-Temp (≤ 120
  Zeichen), unabhängig von `--basetemp`.
- **K4** `tests/packaging/test_env_example.py` findet jede Variable in Paket, Werkzeugen, Tests, Workflows und
  Skripten; Reparatur `ef27745`: Zuweisung vor einem Befehl zählt als Umgebung, Präfix-Auffangregel für
  `NEUROGRID_`/`GITEE_`/`PYPI_` wieder da.
- **K5** Bündelbau, Reinraum an der Präfixgrenze und ohne Browser, Bündel-Markertests, Notices (Zahlen in 4.7.5, 4.7.4).
- Laufzeitexport gegen den Abschluss in `uv.lock` geprüft (psutil, 2.6).
- Reparatur (`6986940`): Rückfälle K1/K4, PDF-Tests unabhängig von der Länge von `--basetemp`, `offline.yml` führt
  `pytest -m bundle` aus (N3), `Shown` ohne `USERPROFILE` im Reinraum (N4). Gemessen: bis 196 Zeichen Arbeitsordner
  schreibt der Browser `<profile>\Default\chrome_debug.log`, 197–209 fällt das Log in den aktuellen Ordner, ab 210
  Startfehler; `--enable-logging=stderr`, `--log-level=3`, `--disable-logging` und
  `--enable-features=NetworkServiceInProcess` verhindern das `debug.log` des Netzwerkdiensts neben der exe nicht.
- Volle Suite nach Reparatur: 3352 bestanden, 13 übersprungen, 73 abgewählt in 1545 s.

**Merge-Konflikte** (`8394c5e`): `kernel/pdf.py` und die PDF-Tests von `p5-int-pdf` (Arbeitsordner im Temp-Ordner)
gewinnen; aus `p5-int-pack` bleiben der gemessene Kommentar zum Fallback-Log, der Test
`test_fallback_log_of_a_long_work_folder_stays_in_the_work_folder` und `browser_root` für die als `file://`
geöffnete Doku-Seite; `test_workflows.py` von `p5-int-pack` [G: Commit-Nachricht].

#### 4.7.7 Lizenztexte (D-15, D-16; Zweig `p5-licence-texts`)

- **CC BY 4.0** (D-15): `LICENSES/CC-BY-4.0.txt` byte-gleich aus SPDX license-list-data v3.27.0
  (`https://raw.githubusercontent.com/spdx/license-list-data/v3.27.0/text/CC-BY-4.0.txt`, 17 023 B, SHA-256
  `d557539df68e771cc1eedcc91d13f70fca930e508d11eedcafa4b15db49e3744`, geladen 26.10.2026), festgehalten in
  `license-gate/licence_texts.toml` [G]. Die Verifikation merkte an: SPDX-Fassung, nicht wortgleich mit dem CC-Rechtstext
  (Abschnitt 6 anders gegliedert, Haftungsausschluss nicht in Großbuchstaben) – für REUSE ausreichend [D].
- **Validator-Bündel** (D-15): Die Source-Map von bids-validator 3.0.2 hat 790 Quellen: 18 jsr-, 53 npm-Pakete, dazu 9 in
  der Distribution von hed-validator 4.2.0 eingebettete [D]. Lizenzdateien: npm aus dem Versions-Tarball (sha512 des
  Versionsdokuments geprüft, nur LICENSE/LICENCE/COPYING/NOTICE der obersten Ebene, im Speicher gelesen), jsr aus
  `https://jsr.io/<paket>/<version>/<datei>` (gegen `<version>_meta.json` geprüft). 146 Downloads, 9 381 740 B (größte
  Datei: hed-validator-4.2.0-Tarball, 5,4 MB) [D]. Ablage `license-gate/third_party/bids-validator-3.0.2/` (Dateien
  `LICENSE` bzw. `LICENSE.<herkunft>.txt`, nur LF) mit `manifest.toml` (je Paket Registry, Name, Version, Lizenz,
  URLs, SHA-256, Texte, offene Punkte). Die Download- und Zusammenstellungsskripte wurden nicht versioniert (nur
  Scratchpad) [NV]; das Manifest hält jede URL, Größe und SHA-256 zur Nachprüfung fest.
- **D-16:** Die Verifikation fand in `isomorphic-git` 1.41.9 einen aus `@zenfs/core/path` kopierten Abschnitt unter
  LGPL-3.0-or-later, den `notices.py` übersehen hatte (geprüft wurden nur die ersten 4000 Zeichen je Quelle); dazu
  fehlten `@jspm/core` (Node-Polyfills) und die vollständigen Lizenzen von hash-wasm 4.12.0. Der
  Projektverantwortliche entschied D-16; umgesetzt in `d74f413`…`9625233`: LGPL-3.0-or-later (42 098 B,
  `996af0513df21f7496288951c41428a03c174e9e4a9d63665c57d670f845ccb1`) und GPL-3.0-or-later (34 674 B,
  `fb981668c18a279e285fc4d83fba1e836cc84dd4daa73c9697d3cfd2d8aca6e0`), beide SPDX v3.27.0, seit R27 neben
  isomorphic-git unter `license-gate/third_party/bids-validator-3.0.2/npm/isomorphic-git@1.41.9/` [G:
  `licence_texts.toml`]. `notices.py --check` scheitert, wenn das Manifest nicht zur Source-Map passt, ein Text in
  Größe oder SHA-256 abweicht, eine Lizenz nicht in `BUNDLED_ALLOWED` steht oder ein Paket ohne Text keinen Eintrag in
  `known_missing.toml` hat.
- Aufgelöst und aus `known_missing.toml` entfernt: CC-BY-4.0, Lizenzdateien der Validator-Pakete, BIDS-Schema 1.2.7
  (laut jsr-LICENSE CC-BY-4.0). Neu eingetragen: hed-validator-Unterpakete ohne Version, hash-wasm-C-Quellen ohne
  Text, `@jspm/core`. Abschnitt 3 der Notices listet 80 Pakete.
- Prüfung: `notices.py --wheelhouse .local/notices-wheels --check` „up to date“; `--components` 0 Probleme in 129
  Wheels und 4 Bündelteilen; `tests/docs/test_licensing.py`, `test_notices.py` grün [D].

#### 4.7.8 Abnahme G1, Skalierung, zh-Prüfpaket (A-88; Zweig `p5-acceptance`)

**G1-Werkzeug** `tools/acceptance_g1.py` [G: Optionen; Verhalten D]:
```powershell
$PY = ".\.venv\Scripts\python.exe"
& $PY tools\acceptance_g1.py --corpus .local\corpus --out .local\acceptance\g1 [--datasets <ordner> …] [--runs 2] [--jobs 4] [--as-of 2026-10-11] [--replace]
```
- Je Datensatz als echte Prozesse des `neurogrid`-Skripts neben dem Interpreter (PYTHON*-Variablen entfernt):
  `scan`, `check` (core+bids+gxdsl008, `--jobs 4`), `report --lang zh,en --format html,pdf`, `manifest`, `verify`,
  zweimal (Lauf 1 Konsole en, Lauf 2 zh), dazu einmal `check --jobs 1` auf ds004148-1.0.1.
- Prüft mit eigenem Code: kein Exit 2; Konsole strikt UTF-8 mit festem Satz; genau 7 Produktdateien; Schemas
  (Draft 2020-12) und kanonisches `results.json`; jede Befundzeile mit den 10 Zellklassen, jede Leerzelle aus
  `EXPLAINED_EMPTY`, höchstens 50 Zeilen je Regel plus genaue Sammelzeile; jedes PDF über das QA-Gate und eine
  unabhängige pypdf-Lesung (Schriften, fester Satz/Kopf/Seitenzahl auf jeder Seite, A4, `/Info`, Datumsfelder, kein
  XMP, keine `/ID`); Byte-Gleichheit beider Läufe; Datenschutzsuche über alle Ausgaben; Korpus vor und nach dem Lauf
  unverändert (`corpus.py verify`). Schreibt `summary.json` (Schema `neurogrid-acceptance-g1/1`, nur Zahlen und
  relative Namen) und `summary.md` (deutsche Tabelle, V-01-Checkliste, V-06-Zeile).
- Exitcodes: 0 alle Kriterien dieses Laufs erfüllt, 1 ein Kriterium verfehlt, 2 Werkzeugfehler (Korpus fehlt oder
  verändert, PDF-Browser fehlt, `--out` nicht leer ohne `--replace` oder im Korpus).
- Ergebnis auf `4587546` [D]: „G1: 6/6 data sets passed, formats BDF, BrainVision, EDF, EEGLAB, FIF; minimum met; all
  criteria met“, Exit 0, ≈ 20 min. Je Datensatz (check/report-Exit; Befunde; PDF-Seiten zh/en; check s Lauf 1/2;
  report s Lauf 1/2): ds003775-1.2.1 EDF 0/0, 92, 26/28, 73,3/74,7, 29,8/17,3 · ds002778-1.0.5 BDF 1/0, 134,
  30/32, 32,1/31,8, 19,5/20,9 · ds004148-1.0.1 BrainVision 1/0, 49, 22/25, 43,6/44,0, 15,8/15,1 · ds004504-1.0.9
  EEGLAB 0/0, 50, 18/21, 44,5/43,5, 14,5/14,2 · ds000248-1.2.4 FIF 1/0, 87, 21/23, 30,1/29,8, 15,6/15,4 ·
  psg-ipa-1.0.0 EDF+ (Rohordner) 1/0, 1721, 92/123, 15,1/15,1, 52,6/50,9. Alle Dateien beider Läufe byte-gleich.
  Erneut auf `6a4f737` (≈ 17 min): 6/6, V-01 erfüllt. Ein unabhängiger Nachlauf ergab dieselben 42 Produktdateien
  (SHA-256) bei anderem Ausgabepfad und anderer Uhrzeit.
- pytest-Hülle: `$env:NEUROGRID_REQUIRE_PDF = "1"; & $PY -m pytest tests\acceptance\test_g1_corpus.py -m corpus [-k
  <datensatz>]` → 52 bestanden in 1124 s auf `944037c` [D]. Korpus im Worktree als Junction (3.5).
- Nach der Fix-Runde (R20–R24, R29; 4.7.11) lief das Werkzeug auf drei Datensätzen (`--datasets ds002778-1.0.5
  ds004148-1.0.1 psg-ipa-1.0.0`): Exit 0; psg-ipa ergibt 556 gesuchte Rohnamen, keiner gefunden [D]. Ein voller
  G1-Lauf auf dem gemergten Stand (`55335ca`/`181654e`) ist nicht protokolliert [NV] – vor G1 zu wiederholen; bei
  einem Lauf traten ein `MemoryError` (autoreject auf ds002778) und ein `read.failed` auf, beides aus dem
  Arbeitsspeicher des Rechners: auf einem Rechner mit genug freiem RAM laufen lassen oder je Datensatz einzeln.

**Skalierung** (A-59, A-88) [G: `tests/perf/test_report_scaling.py`; Messwerte D]:
```powershell
$env:NEUROGRID_REQUIRE_PDF = "1"
& $PY -m pytest tests\perf\test_report_scaling.py -m perf -s -p no:cacheprovider   # ≈ 8,5 min, schreibt .local\perf\report_scaling.json
```
Nur diese Datei angeben: `pytest tests/perf -m perf` startet auch NG-N02 mit 1-GB-Dateien. Grenze = ⌈1,5 × größter
Wert wiederholter Läufe vom 26.10.2026⌉ (`MEASURED`, `RESERVE = 1.5`; Ryzen 9 6900HX, Windows 11 26200, Python
3.12.15, Shell 1243). Ein einzelner Lauf ließ zu wenig Luft (QA-Gate schlimmster Fall 29,9 / 29,2 / 44,6 s).

| Fall | Messung (größter Wert) | Grenze |
|---|---|---|
| schlimmster (128 742 Befunde, 149 MB `results.json`) | html 21,4 s / 1703 MB; html,pdf 108,8 s / 1929 MB; parse 4,3, render 7,8, print 5,0, QA-Gate 44,6 s; 99/106 Seiten zh/en; PDF 730 131 / 728 364 B; HTML 1 252 705 / 1 026 261 B | html 33 s / 2555 MB; html,pdf 164 s / 2894 MB; parse 7, render 12, print 8, Gate 67 s; 149/159 Seiten; PDF 1 095 197 / 1 092 546 B; HTML 1 879 058 / 1 539 392 B |
| typischer (6 110 Befunde) | html 13,0 s / 364 MB; html,pdf 92,1 s / 1284 MB; parse 0,6, render 4,4, print 4,7, Gate 36,2 s; 136/142 Seiten | html 20 s / 546 MB; html,pdf 139 s / 1926 MB; parse 1, render 7, print 8, Gate 55 s; 204/213 Seiten |

Zwei Nachtwerte (8 370,2 s Berichtsprozess, 14 936,9 s zh-Gate) sind ausgeschlossen: der Rechner schlief (Modern
Standby). Beleg ohne Adminrechte (PowerShell):
```powershell
Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-Kernel-Power'; Id=506,507} |
  ForEach-Object { ([xml]$_.ToXml()).Event.EventData.Data }
```
Ereignis 507 trägt `SleepEntered`, `SleepDurationInUs`, `DripsResidencyInUs`: Schlaf 8 282,0 s ab 02:31:45 und
14 907,0 s ab 04:55:17 (UTC+1) lagen in den beiden Messungen; ohne sie bleiben 88,2 s bzw. 29,9 s. Die Grenzen gelten
für einen wach gehaltenen Rechner dieser Art (1.6 Punkt 15).

**zh-Prüfpaket** (A-07, STOPP G1):
```powershell
& $PY tools\zh_review_package.py [--g1 .local\acceptance\g1] [--examples ds002778-1.0.5 psg-ipa-1.0.0] [--out .local\acceptance\zh_review\zh_review.md] [--since a44d592]
```
Listet jede zh-Zeichenkette mit Quelle und Schlüssel, markiert neu/geändert gegenüber dem P1-Commit `a44d592`, legt
die beiden Beispiel-PDFs aus dem G1-Lauf daneben (Exit 2 und nichts geschrieben, wenn die Basis oder ein Beispiel
fehlt). Ergebnis auf `6a4f737` [D]: 2530 zh-Zeichenketten aus 34 Dateien (2268 neu, 6 geändert), dazu
`ds002778-1.0.5.report.zh.pdf` (30 Seiten, 245 816 B, `9b8eb078d73d6bf6861ed7f91eaa1ef2c0672ae94e3167731b5c738959dcdf83`)
und `psg-ipa-1.0.0.report.zh.pdf` (92 Seiten, 546 640 B,
`fa96a58115dc6547e385c1b01344e3cd84a1719abaf34ef8c36b2f3b9a760d1f`). Nicht versioniert. Die Fix-Runde hat zh-Texte
geändert und ergänzt; das Paket vor G1 neu erzeugen [NV].

**Weitere Tests:** `tests/acceptance/test_g1_checks.py` (jede Prüfung erkennt einen eingepflanzten Fehler),
`test_g1_fixture_runs.py`, `test_console_sentence.py` (fester Satz jedes Befehls in zh/en), `test_license_gate.py`,
`test_zh_review_package.py`. V-06: das Werkzeug nennt die Norm genau einmal (`NORM` in `tools/acceptance_g1.py`,
geprüfter Eintrag in `tests/unit/test_norm_independence.py`). Volle Suite nach Reparatur (`6a4f737`): 3381
bestanden, 22 übersprungen, 126 abgewählt in 1588 s [D].

#### 4.7.9 Merge der Integration und CI-Lauf auf `c3be509`

- Merge-Reihenfolge am 26.10.: `p5-int-pdf` (`a702660`), `p5-int-pack` (`8394c5e`), `p5-acceptance` (`2ad5710`;
  `test_workflows.py`: die Prüfung gegen die echten Parser bleibt, der PENDING-Eintrag für `acceptance_g1.py` entfällt),
  `p5-licence-texts` (`ce1ab9c`; Notices ohne Konflikt, `--check` aktuell) [G: Commit-Nachrichten].
- Merge-Fix `051fafb`: `tests/docs/test_notices.py` liest `NEUROGRID_NOTICES_WHEELS`, `test_env_example.py` verlangt
  jede Variable in `.env.example` → eingetragen (1.5).
- `c3be509`: `tools/junit_annotations.py` (nur Standardbibliothek, Exit immer 0) macht aus `pytest-junit.xml`
  Fehler-Annotationen `::error title=<node ID>::<erste Zeile>`. Die Job-Logs von GitHub Actions brauchen eine
  Anmeldung, die Annotationen der Check-Runs liefert die öffentliche REST-API ohne Anmeldung:
  ```bash
  curl -s https://api.github.com/repos/Ammxri/neurogrid/actions/runs/<run-id>/jobs          # Jobs und Ergebnis
  curl -s https://api.github.com/repos/Ammxri/neurogrid/check-runs/<job-id>/annotations     # Fehler-Annotationen
  ```
  GitHub behält höchstens 10 Fehler-Annotationen je Schritt; seit der Fix-Runde fünf Schritte (40 Fehler + Zählung).
- Lauf 40355705974 auf `c3be509` (Workflow `ci`) [G, CI-Annotationen]: grün Lizenz-Gate, PowerShell 5.1,
  PowerShell 7, Rückverfolgbarkeit; rot alle sechs Testjobs. Windows: 18 fehlgeschlagen, 3466 bestanden,
  8 übersprungen (3492 Tests) – 17 davon `test_install_ps1.py` mit „The term 'Get-FileHash' is not recognized“ (annotiert
  sind 9; die Zahl 17 stammt aus der Nachstellung der Fix-Runde [D]), dazu `test_pdf_tests_pass_with_a_long_basetemp`.
  Linux: 18 fehlgeschlagen, 10 Fehler, 3401 bestanden, 63 übersprungen; nur die ersten 10 annotiert. Diese Fehler
  gingen in die Fix-Runde (4.7.11).

#### 4.7.10 Review (30 Befunde R00–R29)

Vier Prüfrichtungen (Bericht/PDF, Datenschutz, Bündel/CI, Doku/Lizenzen/Abnahme), jeder Befund reproduziert und von
einem zweiten Prüfer gegengeprüft: 29 bestätigt, 1 strittig (R12) [D]. Schwere nach Gegenprüfung: 1 kritisch → major
(R19), sonst major/minor.

| Bereich | Befunde |
|---|---|
| Bericht/PDF | R00 Schreiben nicht alles-oder-nichts, wenn ein Ziel nicht ersetzbar ist (PDF im Betrachter offen); R01 ein langer Wert schrumpft das ganze PDF auf 2/3; R02 Ligatur-Zwillinge (ﬁ); R03 Diagrammbereich bei riesiger Schwelle (2·t → inf); R04 Wörter mitten getrennt; R05 Überschriften von Abschnitt 3 widersprechen der Zusammenfassung; R06 Installer zeigt den Benutzerordner |
| Datenschutz | R07 Installationshinweis des Bündels mit `~` nicht ausführbar; R08 Doku verschweigt, dass `document`, `reviewer`, `comment` aus `evidence.yaml` im Klartext in `results.json` und Bericht stehen (Verhalten nach A-83 gewollt, Doku-Lücke); R09 Doku zu `[dataset]` dreht den Vorrang um (Code: `neurogrid.toml` gewinnt) |
| Bündel/CI | R10 Bündel-Tests nicht bei Push auf `dev` (gegen D-15); R11 tote Loopback-Proxys tarnen Netzversuche als erlaubtes Loopback; R12 Signaturidentität stammt aus dem Bündel selbst (strittig); R13 Installer zeigt Benutzerpfade; R14 gescheiterte Installation hinterlässt Reste; R15 kein Workflow für das Gitee-Release; R16 Schalter übergeht ein ablehnendes cosign; R17 laufwerksrelatives `-Prefix`, relatives `-Cosign`; R18 README-Befehle nicht lauffähig |
| Doku/Lizenzen/Abnahme | R19 Doku-Seite liefert ungeprüftes Drittanbieter-JS (lunr-languages MPL, wordcut); R20 G1-Zeilenprüfung vergleicht Zellen nicht mit dem Befund; R21 keine Suche nach echten Rohnamen; R22 keine Suche nach ganzzahligen Rohaltern; R23 unlesbare Aufnahmen zählen zum Minimum; R24 fester Satz im HTML nicht geprüft; R25 strace-Regel auf der Datenschutzseite falsch; R26 Lizenz der Notices; R27 LGPL/GPL-Texte ungenutzt in `LICENSES/`; R28 Adresse und SHA-256 von `install_pdf_browser.py` fehlen; R29 „Alle Kriterien erfüllt“ bei Teilabdeckung |

R12, Entscheidung des Leads: dokumentierte Grenze; die Installer geben die geprüfte Identität aus und fordern den
Vergleich mit den Release-Notes (4.7.5). **R08 und R09 waren keinem Fix-Bereich zugeordnet und sind auf `181654e`
unverändert** [G: `docs/en/configuration.md` Abschnitt `[dataset]`, `src/neurogrid/pipeline.py` Zeilen 642/645,
`docs/en/privacy.md`]; beide sind in Arbeit (`p5-ci2-userdocs`).

#### 4.7.11 Fix-Runde (Zweige `p5-fix-report`, `p5-fix-linux`, `p5-fix-bundle`, `p5-fix-docs`)

Alle vier Zweige von `c3be509`, je Befund ein Regressionstest, danach unabhängige Nachprüfung und Reparatur.
Prüfbefehle wie in der CI: `ruff check .`, `ruff format --check .`, `mypy src/neurogrid tools --no-incremental`,
`mypy --strict src/neurogrid/kernel --no-incremental`, `tools/check_commit_ids.py --since c3be509` [D].

**report** (R00–R07, CI-Linux; Endstand `c9a536a`, volle Suite 3502 bestanden / 23 übersprungen [D]):
- **CI Linux, eine Ursache für die meisten nicht annotierten Linux-Fehler:** `kernel/pdf.py` `preflight` startete
  `ldd` mit `text=True` ohne `encoding`; mit `PYTHONWARNDEFAULTENCODING=1` und `filterwarnings =
  error::EncodingWarning:neurogrid` wurde daraus ein Fehler (Fixture-Fehler in `test_report_pdf.py` und
  `test_g1_checks.py`, Exit 2 in CLI-Tests). Jetzt `encoding="utf-8", errors="replace"` (`a5e527a`) [G: Quelltext];
  ein statischer Test verlangt für jeden Unterprozess im Textmodus unter `src/neurogrid` eine Kodierung (ruff
  `PLW1514` deckt nur `open()` ab).
- R00 `write_all` transaktional: alle Dateien vorbereiten, vorhandene Ziele als `.<name>.<zufall>.bak` daneben
  verschieben, neue einsetzen; bei Fehler zurück und Exit 2 (`output.not_writable`); Sicherungen erst nach Erfolg
  löschen (`295ccc6`).
- R01 `overflow-wrap: anywhere` am `body`, Beschriftungen der Schlüssel/Wert-Tabellen `nowrap`; kein Gate auf
  „Schrumpfen“ (ein Datensatzwert darf nie Exit 2 auslösen). Testmethode: In Chromium-153-PDFs beginnt jeder
  Seiteninhalt mit `.23999999 0 0 -.23999999 0 H cm`, dann `S 0 0 S x y cm` mit S = 3,125 bei 100 %; kleiner =
  geschrumpft (gemessen: Basisbericht auf `c3be509` 99,5 %, langer Deckblattwert 2/3). Reparatur `7dc4b40`: eigene
  Wörter in Tabellen mit automatischem Layout brechen nie (Klasse `td.own`).
- R02 `kernel.fonts.substituted_glyphs`: eine cmap-Glyphe, die eine GSUB-Ersetzung aus anderen Glyphen erzeugt
  (liga/ccmp/locl), gilt als Zwilling und bekommt Kopien (`06ddf20`).
- R03 Diagrammbereich nur aus endlichen Grenzen, `nice_ceiling` nie unendlich (`c4dc7b1`).
- R04 neue feste Spaltenanteile, je Tabelle 100 % (Befunde: Regel 12, Klausel 6,5, Titel 12, Status 7, Datei 11,
  Kanal 6, Messwert 8, Schwelle 10, Zeit 11,5, Grund 16) (`2b1b2cd`).
- R05 Überschriften „{Schwere}: N Befunde, davon C in der Zusammenfassung gezählt (F nicht bestanden, O Nachweis
  offen)“; neue Schlüssel `report.text.severity_heading*` (zh/en/de) (`deb282e`).
- R06 `tools/install_pdf_browser.py` zeigt den Benutzerordner als `~` (`2744ca2`).
- R07 `kernel.pdf.install_hint` schreibt einen lauffähigen Befehl ohne Benutzernamen: Windows zwei Formen
  (Eingabeaufforderung mit `%LOCALAPPDATA%\…`, PowerShell mit `& "$env:LOCALAPPDATA\…"`; neuer Schlüssel
  `errors.pdf.install.command_windows`), Linux `"$HOME/…"` (`f214b44`); das Reinraumskript erwartet seit `5c6242e`
  genau diesen Text.
- Nicht behoben: `test_pdf_tests_pass_with_a_long_basetemp` auf `windows-latest` (lokal grün); `4ee617d` meldet seither,
  welche Einträge während des Laufs entstanden. Auf `55335ca` zeigte die Annotation einen `debug.log` neben der exe
  mit einer Warnung des Netzwerkdiensts (`sqlite_persistent_shared_dictionary_store`) [G, CI 55335ca] – Gegenstand der
  zweiten Fix-Runde.

**linux** (CI-Linux, Prüfung der POSIX-Zweige; Endstand `191a62a`, volle Suite mit `PYTHONWARNDEFAULTENCODING=1`
3510 bestanden / 25 übersprungen [D]):
- A-51: Unter Linux liegt `/tmp` außerhalb des Benutzerordners (CI: `/tmp/pytest-of-runner/…`). Die Konsole zeigt jetzt
  Login- und Rechnernamen in Pfaden des Rechners als `<user>` und `<host>` (ganze Wörter, ab 3 Zeichen, nicht
  `neurogrid`; Quellen `USERNAME`, `getpass`, passwd, `COMPUTERNAME`, `os.uname().nodename` – keine Socket-API außerhalb
  von `netguard`) (`53188c4`, `84da9db`, `26b752c`). Unbekannter oder `/` als Benutzerordner ist kein Absturz mehr;
  Laufwerkswurzel als Datensatzwurzel; Reparatur `c49a966` (Wörter wie „Size:“ blieben sonst nicht unverändert).
- A-67: Unter Linux werden `//…`, `\\server\share`, `\\?\…`, `\\.\…`, `\??\…` wie unter Windows abgelehnt
  (`kernel.safety.operator_path_problem(text, windows=…)`, `a2f8430`); A-67 in ENTSCHEIDUNGEN nachgetragen (`191a62a`).
- A-54: Ausgaben mit 0666 abzüglich umask statt 0600 (`kernel.safety.create_temporary`, `4b25569`); Arbeitsbasis ohne
  Ausgabeordner unter Linux `<temp>/neurogrid-<uid>` mit 0700, fremde oder für andere schreibbare Basis abgelehnt
  (`temp_work_base`, `334ca4f`).
- Tests mit nicht dekodierbaren Dateinamen laufen auch unter Linux (`76bcb99`).
- Nicht behoben: `Path.home()` ungeschützt in `kernel/pdf.default_browser_dir` und `install_pdf_browser.py` (Linux ohne
  `HOME` und passwd → „Internal error“, Exit 2); Sprache unter Linux aus `LC_CTYPE`, nicht `LC_MESSAGES` (A-07).

**bundle** (R10–R18, CI-Windows; Endstand `d42bbf4`, volle Suite 3498 bestanden / 23 übersprungen [D]):
- CI Windows: `Get-FileHash` fehlt in einem aus PowerShell 7 gestarteten 5.1 (1.6 Punkt 13); Hash über .NET in
  `install.ps1`, `cleanroom_windows.ps1` und `offline.yml` (`4a5140d`). Lokal nachstellen ohne pwsh: Ordner `<dir>`
  mit `Microsoft.PowerShell.Utility\Microsoft.PowerShell.Utility.psd1` (GUID `1DA87E53-152B-403E-98DC-74D7B4D63D59`,
  ModuleVersion 7.0.0.0, CompatiblePSEditions Core, CmdletsToExport `Get-FileHash`, `Format-Hex` und alle Cmdlets der
  5.1-Datei, NestedModules `Microsoft.PowerShell.Commands.Utility.dll`) vorn in `PSModulePath`; dann läuft
  `ConvertFrom-Json`, aber nicht `Get-FileHash` [D]. Alle `test_install_ps1.py`-Tests laufen mit diesem Ersatz.
- Annotationen in vier Schritten zu 10 plus Zählung (`98f0d92`).
- R10 der Workflow `offline` auf `dev` und `main`, Concurrency je Ref (`a4a07bf`, `260b1f8`); R11 keine toten Proxys
  mehr in den Linux-Reinräumen, unter Windows nur mit `-NoOsAudit`; `strace_check.py` und die WFP-Auswertung zählen
  einen Loopback-Aufruf auf Port 9 als Netzversuch (`d3a7bfd`); R12 Identitätsvergleich (`a83297b`); R13 Pfade als
  `%LOCALAPPDATA%`/`~` (`2c4605b`, `6c43ca1`); R14 Ziel bleibt wie vorgefunden (`6f7ee43`, `b0015d5`); R15 Job
  `gitee-release` in `mirror-gitee.yml`: lädt Wheel, sdist, `SHA256SUMS` und Signatur des GitHub-Release, prüft
  sie erneut und legt sie mit dem Text aus `packaging/gitee-release.md` als Artefakt ab; das Gitee-Release legt der
  Projektverantwortliche von Hand an (kein Gitee-Token, D-15 gibt nur `GITEE_SSH_KEY` frei) (`213cc70`); R16
  (`d0a2edc`); R17 (`56967bc`, `d42bbf4`); R18 README-Befehle in PowerShell-Form, als gedruckt geprüft (`871dbc7`).

**docs** (R19–R29):
- R19 `license-gate/third_party/mkdocs-material-9.7.7/manifest.toml` prüft jeden Drittanbieter-Teil der Seite
  (mkdocs-material MIT, rxjs Apache-2.0, tslib 0BSD, clipboard/escape-html/lunr MIT, Material Design Icons
  Apache-2.0, Octicons MIT, Font Awesome Free 7.1.0 CC-BY-4.0, Noto-Sans-SC-Teilmenge OFL-1.1); Texte aus dem
  installierten Wheel, ohne Download. `tools/build_docs.py` entfernt `assets/javascripts/lunr/**` und alle `*.map` und
  bricht mit Exit 1 ab bei ungeprüfter Datei, Copyleft-Kopf in `.js`/`.css`, nicht freizügiger Lizenz ohne
  `known_missing`-Eintrag oder abweichender Theme-Version; ohne Prüfung der installierten Version Exit 2. Jeder Bau
  meldet „licence pending (blocks the release, STOPP G1): …“ für focus-visible und material-design-color (`cce23d2`,
  `c8c3f6e`). Gebaute Seite danach: 33 HTML-Seiten plus Skripte, Stile, 2 woff-Teilmengen, 6 Schemas, Suchindex,
  Sitemaps [D].
- R20–R24, R29 im G1-Werkzeug: Zellvergleich mit `results.json` (`006836f`), Suche nach Rohnamen (`45c2e23`,
  `8fefaab`) und ganzzahligen Altern im Kontext (`0293662`, Reparatur `0854df6`: chinesische Muster als Escapes),
  unlesbare Aufnahmen zählen nicht (`cbeff1b`), fester Satz im HTML (`2394f00`), „Kriterien dieses Laufs“ und
  `g1.outside_this_run` (Skalierung, Linux-strace, Reinraum debian:12-slim, Abdeckung) (`794deaa`).
- R25 Datenschutzseite nennt die strace-Regel (`b962a30`); R26 (`0e2cefa`); R27 (`33b8e82`, `938acaf`: Prüfung auf
  verschobene Pfade in den Notices); R28 `gen_docs.py` erzeugt den Block „pdf installer“ in `installation.md`
  (`<REPO_URL>/releases/download/v<v>/install_pdf_browser.py` und SHA-256 des Skripts; `8f1aa89`). Heute:
  `3e713e1400cde83a93782d1dacd0e8201fcb74693c787987e7e5ca51cfd6b149` [G, 181654e: Datei und Seite stimmen überein].
- Volle Suite der docs-Fix-Runde: in den Quellen nicht protokolliert [NV].

**Merge der Fix-Runde und Merge-Kopplungen** (26.10. 22:14–22:17, Reihenfolge report → linux → bundle → docs):
- **Semantischer Konflikt `tempfile` gegen `create_temporary`:** `p5-fix-linux` ersetzte `tempfile.mkstemp` durch
  `kernel.safety.create_temporary` und entfernte den Import, `p5-fix-report` fügte `_move_aside` mit `tempfile.mkstemp`
  hinzu; der Merge hinterließ einen undefinierten Namen. Fix `55335ca`: auch die Sicherungsdatei kommt aus
  `create_temporary` [G: Quelltext `report/output.py`].
- **Semantischer Konflikt Port 9:** R11 (bundle) zählt Loopback auf Port 9 als Netzversuch, R25 (docs) schrieb
  „Loopback erlaubt“ und testete mit Port 9. Lokal auf `55335ca` (Windows 11, Python 3.12,
  `NEUROGRID_REQUIRE_PDF=1`, `PYTHONWARNDEFAULTENCODING=1`): 3597 bestanden, 24 übersprungen, 127 abgewählt,
  1 fehlgeschlagen (`test_privacy_pages_state_the_strace_rule_of_the_offline_gate`) [D]; in der CI scheiterte derselbe
  Test in jedem Testjob. Fix `181654e`: die Seiten (en/zh) nennen die Port-9-Ausnahme, der Test prüft gewöhnliche
  Ports als erlaubt und Port 9 als abgelehnt.
- **`gen_docs` nach Änderungen an `install_pdf_browser.py`:** `p5-fix-report` änderte das Skript, `p5-fix-docs` die
  Seite mit seinem SHA-256; nach dem Merge `tools/gen_docs.py` laufen lassen und die beiden `installation.md`
  committen, dann `gen_docs.py --check`, `tests/docs/test_docs_build.py`, `build_docs.py` [D]. Heute „documentation up
  to date“ [G].
- **Notices neu erzeugen** nach Änderungen an `uv.lock`, `components.toml`, `known_missing.toml`, Manifesten oder
  `bundle_lock.json` (4.7.4); heute „up to date“ [G].
- **`.env.example`** nach neuen Variablen in Tests oder Skripten (`051fafb`; `HOMEDRIVE`/`HOMEPATH` als Systemvariablen
  in `c9a536a`).

#### 4.7.12 CI-Stand auf `55335ca`

Gelesen über die öffentliche Check-Run-API (4.7.9) [G, CI 55335ca]:

| Workflow / Lauf | Job | Ergebnis |
|---|---|---|
| `offline`, 40403791782 | beide Offline-Bündel aus `uv.lock` (unsignierte Entwicklungsbündel), mit `pytest -m bundle` | grün |
| | PDF in `debian:12-slim` mit der dokumentierten Paketliste (`--network none`, strace) | grün |
| | glibc 2.27 mit Exit 2 abgelehnt (`ubuntu:18.04`, A-58) | grün |
| | Reinraum Windows (PowerShell 5.1 und pwsh, WFP-Audit, PDF) | grün |
| | Reinräume `debian:12-slim`, `ubuntu:24.04`, `ubuntu:22.04` (`--network none`, ohne Python, uid 1000) | grün |
| | jeder v0.1-Befehl unter strace, `--network none` (Linux) | grün |
| `ci`, 40403791901 | Lizenz-Gate und Netz-Scan der Laufzeitpakete; Windows PowerShell 5.1; PowerShell 7; Anforderungs-IDs | grün |
| | Test ubuntu-24.04 × 3.11/3.12/3.13 | rot: je 6 fehlgeschlagen, 3531 bestanden, 85 übersprungen (3622) |
| | Test windows-latest × 3.11/3.13 bzw. 3.12 | rot: 5 bzw. 6 fehlgeschlagen, 3606 bzw. 3605 bestanden, 11 übersprungen |
| | plattformübergreifender Vergleich | übersprungen (hängt an den Testjobs) |

Fehlgeschlagene Tests: Linux `test_review_p2_formats.py::test_mne_alone_follows_the_differently_decoded_reference`,
zwei Codepage-/Marker-Fälle in `test_review_p2_convert.py`, `test_report_pdf.py::test_qa_gate_negative_controls`,
`test_report_pdf.py::test_rule_ids_do_not_break_inside_in_the_pdf` und der strace-Doku-Test; Windows drei Tests in
`test_install_ps1.py` (auf dem Runner), `test_pdf_tests_pass_with_a_long_basetemp` (Chrome schreibt `debug.log` in
den Ordner der exe), der strace-Doku-Test und einmal ein Such-Timeout in `test_docs_browser.py`. Der strace-Doku-Test
ist mit `181654e` behoben; die übrigen bearbeitet die zweite Fix-Runde `p5-ci2-*`. In den Testjobs liefen Lint und
Typen grün (fehlgeschlagen war nur der Schritt „Tests with coverage“); die Abdeckungs-Gates (Schritt danach) sind in
der CI deshalb nicht gelaufen [NV]. Ergebnis nach der zweiten Fix-Runde: `<ERGEBNIS NACH P5-CI2>`.

D-15 verlangt die Bündel-Tests bei jedem Push auf `dev` und `main`: Seit Review R10 läuft der Workflow `offline` bei
jedem Push auf `dev` und `main` sowie per Dispatch oder Aufruf aus `release.yml`; ein neuerer Push auf denselben Zweig
bricht den älteren Lauf ab, ein Release-Lauf (Tag-Ref) wird nie abgebrochen [G: `on:`- und `concurrency:`-Block,
`tests/packaging/test_workflows.py`]. `ci.yml` hat weiterhin keinen Bündel-Job. Auf `dev` lief `offline` auf `55335ca`
ganz grün [G, CI 55335ca]; gepusht wurden `42e129d`, `c3be509` und `55335ca` [G: Reflog von `origin/dev`].

#### 4.7.13 Stand heute und was zu P5 noch fehlt

Geprüft [G, 181654e]:
- `uv lock --check --offline` → 103 Pakete; `ruff check .` „All checks passed!“; `ruff format --check .` „224 files
  already formatted“.
- `gen_fixtures`, `gen_schemas`, `gen_montage_names`, `gen_docs`, `calibrate` jeweils `--check` grün;
  `linux_pdf_packages.py --check` grün; `install_pdf_browser.py --check` „complete (revision 1243, 290 files)“;
  `check_matrix_coverage.py` 166/166; `check_commit_ids.py` 146 Commits, 0 Probleme.
- `notices.py --wheelhouse <.local/notices-wheels> --check` → „up to date“ und 8 „incomplete“, Exit 1.
- Testsammlung: 3749 Tests, Standardlauf 3622, abgewählt 127 (114 `corpus`, 9 `perf`, 4 `bundle`); Marker `pdf` 98,
  `browser` 2.

Lokale volle Suiten [D]: Fix-Runde report `c9a536a` 3502 bestanden / 23 übersprungen; linux `191a62a` 3510 / 25 (mit
`PYTHONWARNDEFAULTENCODING=1`); bundle `d42bbf4` 3498 / 23; gemergter Stand `55335ca` 3597 bestanden, 24
übersprungen, 127 abgewählt, 1 fehlgeschlagen (behoben in `181654e`). Nach der zweiten Fix-Runde:
`<ERGEBNIS NACH P5-CI2>`.

Noch offen vor G1: CI-Testjobs grün auf Linux und Windows (zweite Fix-Runde); volle Suite unter 3.11/3.12/3.13 auf dem
Endstand; Abdeckungs-Gate auf dem Endstand [NV]; Korpustests (`-m corpus`, 114) und voller G1-Lauf auf dem Endstand
[NV]; `bundle.py sizes` [NV]; zh-Prüfpaket neu erzeugen; R08 und R09 (in Arbeit, `p5-ci2-userdocs`; 4.7.10); überholte Plattformangaben der
Nutzerdoku (`installation.md`, `limitations.md`, `privacy.md` en/zh: Linux, PowerShell 7 und strace „bis zum ersten
CI-Lauf nicht verifiziert“, Firewall-Test „nicht verifiziert“, obwohl `offline` auf `55335ca` sie grün prüfte) [G];
Phasenbericht an den Projektverantwortlichen. Matrix, KONZEPT (1.1–1.3, 1.6, 2.6, 2.8, 3, 4, Risiko R10 in 5), FORTSCHRITT und
A-84..A-88 in ENTSCHEIDUNGEN sind mit diesem Doku-Stand nachgetragen.

#### 4.7.14 STOPP G1 (folgt)

STOPP G1 ist noch **offen**; er folgt, sobald die CI-Testjobs grün sind und der Lead den Phasenbericht vorgelegt hat.
Die vollständige Liste führt FORTSCHRITT („Für STOPP G1 vorgemerkt“); für den Nachbau wichtig sind:
- Bestätigung der Annahmen A-84..A-88 und der Lesarten der PRD daraus (u. a. Abschnitt 4 mit Aggregaten von
  `results.ai`, Anhang 6.1/6.6, nur 50 Zeilen je Regel plus `results.json`, Überschriften von Abschnitt 3), dazu die
  geänderten A-51, A-54, A-67; die Lesart der Signatur (R12 Grenze, R16 cosign im PATH prüft immer).
- Entscheidung über die 8 Einträge in `known_missing.toml` (Abschnitt 8); bis dahin sperren `notices.py --check` und
  `release_check.py` das Release.
- Versand der Anfrage an die Validator-Entwickler (D-16).
- muttersprachliche zh-Prüfung mit dem Paket aus 4.7.8, einschließlich der in der Fix-Runde neuen zh-Texte
  (Installer, README.txt, Release-Notes, `packaging/gitee-release.md`, `installation.md`, `privacy.md`).
- Sichtprüfung der Beispiel-PDFs (kein PDF-Renderer lokal).
- Freigabe von Push auf `main`, Version `0.1.0`, Tag `v0.1.0`, `release.yml`, TestPyPI/PyPI, Gitee-Spiegel und
  Gitee-Release von Hand (R15).
- Zwei Fragen aus dem P6-Entwurf: (1) Befunde von M14 je Proband gegen A-30/A-35 (Optionen A/B/C, Empfehlung B:
  je Proband nur in `results.json`, im Bericht aggregiert); (2) zh-Prüfung der P6-Texte (Empfehlung C: bei G1 nur die
  Begriffe, die vollen Texte vor v0.2). P6 beginnt erst nach G1.

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
| `build_docs.py` | Website bauen und prüfen (Netz-Audit-Hook, `SOURCE_DATE_EPOCH`; seit R19 Entfernen von `lunr/**` und `*.map`, Prüfung jedes Drittanbieter-Teils gegen `license-gate/third_party/mkdocs-material-<v>/manifest.toml`, Zeile „licence pending …“ je offenem Teil) | `[--site-dir site]` | 0 / 1 / 2 |
| `mkdocs_hooks.py` | MkDocs-Hooks (Suche zh, Schemas, 404) – kein eigener Aufruf | über `mkdocs.yml` | – |
| `notices.py` | `THIRD_PARTY_NOTICES.txt` statisch aus den Wheels beider Ziele; `--check` prüft auch die Manifeste unter `license-gate/third_party/` und meldet jeden `known_missing`-Eintrag als „incomplete“ | `--list`; `--wheelhouse DIR … --out F`; `--download [--cache DIR] --out F`; `--check` (nur mit `--wheelhouse` oder `--download`); `--components`; `[--bundle-lock F]` | 0 / 1 (auch: Einträge in `known_missing.toml`) / 2 (u. a. Dateien fehlen) |
| `bundle.py` | Offline-Bündel | `build --platform P --wheel W --docs D --notices N [--sdist S] [--pdf-installer F] [--out dist] [--cache DIR] [--sign none\|sigstore]`; `verify PATH`; `sizes [--platform P]`; `lock --python V --pbs-build B --uv V [--cache DIR]` | 0 / 1 / 2 |
| `release_check.py` | Release-Gate (Tag = Version, auf main, sauberer Baum, keine Platzhalter, Lizenztexte) | `--tag v<v> [--root DIR] [--notes OUT] [--repository owner/repo]` | 0 / 1 / 2 |
| `scan_runtime_network.py` | Netzwerk-/Telemetrie-Fundstellen der Laufzeitpakete gegen die Baseline | `[--site-packages DIR] [--baseline F] [--distribution NAME]… [--draft OUT]` | 0 / 1 / 2 |
| `strace_check.py` | strace-Ausgaben auswerten (nicht-Loopback = Fehler; seit R11 auch Loopback auf Port 9, den Port eines toten Proxys; liest seine eigene `strace-summary.txt` nicht zurück) | `strace_check.py EVIDENCE_DIR` (kein `--help`) | 0 / 1 / 2 |
| `acceptance_g1.py` | G1-Abnahme auf dem Korpus (A-88, 4.7.8) | `--corpus DIR --out DIR [--datasets X …] [--runs 2] [--jobs 4] [--as-of 2026-10-11] [--replace]` | 0 / 1 / 2 |
| `zh_review_package.py` | zh-Prüfpaket mit Beispiel-PDFs (A-07, 4.7.8) | `[--out F] [--since a44d592] [--g1 DIR] [--examples DS …]` | 0 / 2 |
| `junit_annotations.py` | fehlgeschlagene Tests aus `pytest-junit.xml` als GitHub-Annotationen (4.7.9) | `REPORT [--root .] [--offset 0] [--limit 10]`; `REPORT --summary [--limit 40]` | immer 0 |

Datendateien in `tools/`: `corpus_spec.json`, `corpus_lock.json`, `docs_templates/*.md.j2` (Vorlagen für
`gen_docs.py`).

Prüfskripte unter `packaging/ci/` (genaue Aufrufe in 4.7.5):

| Skript | Zweck | Aufruf | Exitcodes |
|---|---|---|---|
| `cleanroom_windows.ps1` | Windows-Reinraum: Ablehnung bei Präfixgrenze + 1, Installation an der Grenze, jeder v0.1-Befehl, PDF ohne Browser, Belegdateien | `powershell -NoProfile -ExecutionPolicy Bypass -File packaging\ci\cleanroom_windows.ps1 -Archive ZIP -Evidence DIR [-NoOsAudit] [-Root DIR] [-Installer cmd\|pwsh] [-PdfBrowserZip ZIP -PdfBrowserSha256 HEX] [-Keep]` | 0 = alle Schritte wie erwartet; sonst Abbruch mit ≠ 0 (z. B. Reste in TEMP); mit OS-Audit (CI) zusätzlich `wfp-*.txt` |
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
| apt-Pakete, Container-Images (`debian:12-slim`, `ubuntu:22.04/24.04/18.04`), strace | Debian/Ubuntu, Docker Hub, nur auf CI-Runnern (seit 26.10.2026 in Gebrauch) | – | Digest nur zur Laufzeit festgehalten | D-09, A-58 | Linux-Reinraum, strace, PDF-Linux, apt-Liste der Testjobs |
| GitHub Actions | `actions/checkout` v7.0.1 `3d3c42e5…`, `astral-sh/setup-uv` v10.3.2 `07a047e6…`, `actions/upload-artifact` v7.0.2 `cf430e03…`, `actions/download-artifact` v8.0.2 `9000827c…`, `actions/cache` v6.1.0 `55cc8345…`, `sigstore/cosign-installer` v4.1.2 `6f9f1778…`, `pypa/gh-action-pypi-publish` v1.14.3 `7245906f…` | – | Commit-SHA (aufgelöst 23.10. mit `git ls-remote`) | D-07, D-09 | CI |
| cosign | über `sigstore/cosign-installer` (Standardversion dieses Commits) | – | – | D-10 g | Signatur in der CI |
| CC-BY-4.0-Rechtstext | `https://raw.githubusercontent.com/spdx/license-list-data/v3.27.0/text/CC-BY-4.0.txt` | 17 023 B | `d557539df68e771cc1eedcc91d13f70fca930e508d11eedcafa4b15db49e3744` | **D-15** | `LICENSES/CC-BY-4.0.txt` (4.7.7) |
| LGPL-3.0-or-later, GPL-3.0-or-later | `…/license-list-data/v3.27.0/text/LGPL-3.0-or-later.txt` bzw. `…/GPL-3.0-or-later.txt` | 42 098 B / 34 674 B | `996af0513df21f7496288951c41428a03c174e9e4a9d63665c57d670f845ccb1` / `fb981668c18a279e285fc4d83fba1e836cc84dd4daa73c9697d3cfd2d8aca6e0` | **D-16** | neben isomorphic-git 1.41.9 unter `license-gate/third_party/bids-validator-3.0.2/npm/` |
| Lizenzdateien der npm/jsr-Pakete im Validator 3.0.2 | npm-Versionsdokumente und -Tarballs (URLs je Paket im Manifest), jsr `https://jsr.io/<paket>/<version>/<datei>` und `<version>_meta.json` | 146 Downloads des Zweigs `p5-licence-texts` (einschließlich CC-BY-Text), zusammen 9 381 740 B [D] | je Datei in `license-gate/third_party/bids-validator-3.0.2/manifest.toml` | **D-15** (nur genaue Versionen) | Notices Abschnitt 3 |
| Texte der Doku-Seite (mkdocs-material 9.7.7) | kein Download: aus dem installierten Wheel | – | in `license-gate/third_party/mkdocs-material-9.7.7/manifest.toml` | – | R19 |
| `install_pdf_browser.py` als Release-Asset | `<REPO_URL>/releases/download/v<v>/install_pdf_browser.py` (erst ab dem ersten Release) | – | heute `3e713e1400cde83a93782d1dacd0e8201fcb74693c787987e7e5ca51cfd6b149`, erzeugt in `installation.md` von `gen_docs.py` | – | PyPI-/Quell-Nutzer (R28) |
| 8 fehlende Texte bzw. Lizenzen (`known_missing.toml`, Abschnitt 8) | – | – | – | **keine Freigabe** (Entscheidung zu G1) | `known_missing.toml` leeren |
| torch, braindecode, moabb, MOABB-Daten | – | – | – | D-06 | P11, noch nicht geladen |

Bewusst **nicht** verwendet: eegprep (D-05), pyEDFlib (A-24), EEGDash (D-11), openneuro-py (GPL-3.0), Microsoft Edge,
jieba (nur sdist), iframe-worker, `playwright install`, actionlint (Nebenwirkung einer Probe, nicht übernommen, aus dem
Cache entfernt).

---

## 8 Bekannte Grenzen und nicht Verifiziertes

**Plattformen (D-09):**
- **In der CI gelaufen** (GitHub Actions, seit 26.10.2026): Im Workflow `offline` auf `55335ca` sind alle Jobs grün –
  Bau beider Bündel mit `pytest -m bundle`, offline-strace aller v0.1-Befehle (NG-N01), Linux-Reinräume
  `debian:12-slim`, `ubuntu:22.04`, `ubuntu:24.04`, glibc-Ablehnung `ubuntu:18.04`, `pdf-debian12`, Windows-Reinraum
  unter PowerShell 5.1 und PowerShell 7 mit WFP-Audit [G, CI 55335ca]. In `ci` grün: Lizenz-Gate und Netz-Scan,
  Kommandozeile unter PowerShell 5.1 und 7, Rückverfolgbarkeit, Lint und Typen in allen sechs Testjobs.
- **Nachweis ausstehend:** Die Testjobs von `ci` (Windows und Linux × 3.11–3.13) sind auf `55335ca` rot (4.7.12);
  alles, dessen Nachweis diese Testjobs sind (in der Matrix `nicht verifiziert`: NG-F13, REP-00, TECH-05, TECH-07,
  NG-N04, NG-N08, UF-01; dazu POSIX-Zweige der Provenienz und des Datenschutzfilters, Linux-Start-Check des
  PDF-Browsers), bleibt „umgesetzt, Nachweis ausstehend“: CI-Testjobs noch rot (Lauf auf 55335ca), zweite Fix-Runde
  läuft (`<ERGEBNIS NACH P5-CI2>`). TECH-11 („CI aktiv“) steht auf `erfüllt`: Nach der DoD von P1 (KONZEPT 6) gilt
  die Zeile, sobald nach dem Push der erste CI-Lauf möglich ist; `ci.yml` und `offline.yml` laufen auf jedem Push auf
  `dev` (Läufe 40403791901 und 40403791782 auf `55335ca`).
  Abdeckungs-Gates und plattformübergreifender Vergleich sind in der CI noch nicht gelaufen.
- Nie gelaufen: `docs.yml`, `corpus.yml`, `release.yml`, `publish-pypi.yml`, `mirror-gitee.yml` (nur `main`, Tag
  oder Dispatch) [NV].
- PowerShell 7 lokal nicht installiert (nur CI); Windows 10 nicht verifiziert; NG-N02 auf einem Runner mit
  4 vCPU/16 GB nicht gemessen.

**Nicht protokolliert / nicht erhalten:**
- genaue Befehle für uv-Installation, `uv python install`, Anlage von venv3.11/3.13 (hier [R]), lokale pytest-Aufrufe,
  Probe-Wheel, Rauchtests PowerShell 5.1 in P1/P2, Zusatzmessung „256 Kanäle mit Manifest“
- Prototypen S1–S5 (Skripte gelöscht); Bau-Reihenfolge innerhalb P1–P3; Herstellung von `architektur-s8.png`
- Plattformvergleichsskript (nur Scratchpad)
- P5: einmalige Lade- und Zusammenstellungsskripte der Validator-Lizenztexte, Prüf- und Messskripte der
  Verifikationen (nur Scratchpad); das Skript der Präfixprobe; die volle Suite der docs-Fix-Runde; `bundle.py sizes`,
  Korpustests (`-m corpus`) und ein voller G1-Lauf auf dem gemergten Stand

**Inhaltlich offen (für G1 vorgemerkt):**
- `license-gate/known_missing.toml`, 8 Einträge [G, 181654e]:
  1. `bids-validator-deno:hed-validator@4.2.0/node_modules` – acht in hed-validator 4.2.0 eingebettete Pakete ohne
     Version in der Source-Map (@nodable/entities, fast-xml-parser, lodash, path-expression-matcher, semver, strnum,
     unicode-name, xml-naming);
  2. `bids-validator-deno:hash-wasm@4.12.0/src` – C-Quellen ohne Lizenztext (crc32, crc64, xxhash32, xxhash64;
     argon2);
  3. `bids-validator-deno:node-modules-polyfills/@jspm/core` – Node-Polyfills ohne Version;
  4. `h5py:h5py.libs/libaec-*.so*` und 5. `h5py:h5py.libs/libsz-*.so*` – im Linux-h5py-Wheel weder Lizenz noch Text;
  6. `python-build-standalone:3.12.15+20261009` – Texte der Bibliotheken außer CPython;
  7. `docs-site:focus-visible` und 8. `docs-site:material-design-color` – im Doku-Theme ohne Lizenzangabe.
  Solange die Liste nicht leer ist, sperren `notices.py --check` (8 „incomplete“) und `release_check.py` das Release.
  Ein Download dafür deckt weder D-06 noch D-15 ab.
- Lesart von D-15 bei core-js-pure 3.49.0 (Version aus dem Quelltext der Source-Map, nicht aus einem Pfad) bestätigen.
- Herkunft/Lizenz der ICLabel-Gewichte (A-56); Restpunkte A-78; Zeitangaben ab 27,8 h nur auf 1 s genau (A-61,
  A-79); loky „resource tracker“ ohne Netzwerkschutz (A-79); vorgemerkte Punkte aus A-80..A-83.
- Container-Images per Tag, nicht per Digest gepinnt; cosign-Version = Standard des Installers; Windows-OS-Nachweis
  ordnet DNS-Anfragen des DNS-Client-Dienstes nicht zu.
- PDF: kein Warten auf Web-Schriften vor dem Druck (Fehlfall wäre Exit 2 durch das Gate, nie beobachtet); die Code-Pfade
  für GSUB 2/5/6/8 und GPOS 3/5–8 der Glyph-Kopien prüft nur eine synthetische Testschrift; Sichtprüfung der PDFs nicht
  gemacht (kein PDF-Renderer lokal). (Erledigt: Umbenennung transaktional seit R00; Glyph-Kopien in GSUB/GPOS seit
  der Integration.)
- Ein hart beendeter Lauf, der zwischen `mkdtemp` und dem Anlegen seiner Sperrdatei endet, hinterlässt einen leeren
  Ordner; Reste älterer Versionen ohne Sperrdatei werden nie automatisch entfernt; `ng-pdf-*`-Reste entfernt erst der
  nächste PDF-Druck.
- Linux: `Path.home()` ungeschützt im PDF-Teil (ohne `HOME` und passwd „Internal error“, Exit 2); Sprache aus `LC_CTYPE`
  statt `LC_MESSAGES` (A-07); der Linux-Reinraum prüft den Hinweistext des fehlenden Browsers nicht.
- R08 und R09 (Doku-Befunde zu `evidence.yaml` im Klartext und zum Vorrang von `[dataset]`): auf `181654e` nicht
  behoben, in Arbeit (`p5-ci2-userdocs`; 4.7.10).
- Signatur: die Prüfung im Archiv ist eine Integritätsprüfung, die Identität vergleicht der Nutzer (R12); cosign im
  PATH prüft immer (R16); Gitee-Release von Hand (R15).
- Pfadgrenzen 250/260 nur auf Windows 11 Build 26200 gemessen; Linux-PATH_MAX-Grenze beruht auf der dokumentierten
  Konstante. Die Messgrenzen der Skalierung gelten für einen Rechner wie den Entwicklungsrechner, wach gehalten.
- zh-Prüfung durch Muttersprachler (A-07) für alle zh-Texte, Doku, Installer- und Browser-Meldungen (4.7.8).

**P5 (Stand 181654e):** Bau, Integration, Lizenztexte, G1-Abnahme, Skalierungsgrenzen (A-88), Review und Fix-Runde
sind gemacht (4.7.6–4.7.11). Offen: CI-Testjobs grün und volle Suiten auf dem Endstand (`<ERGEBNIS NACH P5-CI2>`),
Abdeckung, Korpus und voller G1-Lauf auf dem Endstand, `bundle.py sizes`, R08/R09 (in Arbeit, `p5-ci2-userdocs`) und die überholten
Plattformangaben der Nutzerdoku (4.7.13), dann STOPP G1 (4.7.14). A-84..A-88, Matrix, KONZEPT und FORTSCHRITT sind
nachgetragen. Die Bündel-Tests laufen seit Review R10 wie in
D-15 verlangt bei jedem Push auf `dev` und `main`; grün auf `dev` mit `55335ca` [G, CI 55335ca].

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
- [ ] PDF-Browser installiert, `install_pdf_browser.py --check` → vollständig (290 Dateien), auch nach jedem Testlauf
- [ ] `pytest -q` mit `NEUROGRID_REQUIRE_PDF=1`, `PYTHONWARNDEFAULTENCODING=1` und `UV` unter 3.11, 3.12, 3.13 grün;
      Sammlung 3749, Standardlauf 3622, abgewählt 127 (Stand 181654e; Ergebnis: `<ERGEBNIS NACH P5-CI2>`)
- [ ] Abdeckung: `coverage_gates.py` → Kern ≥ 90 %, Prüfer ≥ 80 % (zuletzt 97,1 % / 97,2 % in P4; P5 nicht protokolliert)
- [ ] `licenses.py` → runtime/dev/docs × allowlist/copyleft ok; `licenses.py --components --wheelhouse
      .local/notices-wheels` → „components (129 wheels, 4 bundle parts, win_amd64, linux_x86_64): ok“ (4.7.4)
- [ ] Korpus: `corpus.py fetch` + `verify` → „corpus verified“ (297 Dateien); `pytest -m corpus` → 114 Tests
      (62 Korpus + 52 G1-Hülle) bestanden
- [ ] `pytest tests/perf/test_report_scaling.py -m perf` → 6 bestanden unter den Grenzen aus A-88 (4.7.8), Rechner wach
      gehalten; NG-N02 (`tests/perf/test_ng_n02.py`, `benchmark.py --jobs 4`) unter den Grenzen aus D-14

**Ende-zu-Ende**
- [ ] `check` auf `edf_ok` mit `documented.toml` → Exit 0; zwei Läufe byte-gleich; 3.11/3.12/3.13 gleich bis auf `environment`
- [ ] `check` auf `empty` → Exit 1; fehlender Pfad → Exit 2
- [ ] `report --lang "zh,en" --format "html,pdf"` → Exit 0, vier Dateien; ohne PDF-Browser → Exit 2 mit Hinweis
- [ ] `convert --to bids` je Format ohne Validator-Fehler; `manifest` + `verify` → Exit 0
- [ ] G1: `acceptance_g1.py --corpus .local/corpus --out .local/acceptance/g1` → Exit 0, „6/6 data sets passed …
      all criteria of this run met“; `summary.md` mit V-01-Checkliste und V-06-Zeile (4.7.8)
- [ ] zh-Prüfpaket: `zh_review_package.py` → Exit 0, Markdown plus zwei Beispiel-PDFs (4.7.8)

**Auslieferung**
- [ ] `build_docs.py --site-dir site` → „documentation built and checked“, 0 Netzereignisse, zwei Zeilen „licence
      pending …“ (focus-visible, material-design-color)
- [ ] `notices.py --wheelhouse .local/notices-wheels --check` (oder `--download --check`) → aktuell, 8 „incomplete“
      (Exit 1 bis G1)
- [ ] `bundle.py build` beider Plattformen + `bundle.py verify` → Exit 0; zwei Bauten byte-gleich
      (`pytest -m bundle tests/packaging/test_bundle_real.py` → 4 bestanden; während des Laufs nicht committen)
- [ ] Windows-Reinraum `cleanroom_windows.ps1 … -NoOsAudit [-PdfBrowserZip … -PdfBrowserSha256 …]` → Exitcodes wie in
      4.7.5 (mit install-over-limit 2, report-pdf-without-shell 2); im `-Evidence`-Ordner `exit-codes.txt`,
      `<schritt>.out.log`/`.err.log`, `summary.txt`, `temp-left.txt` (leer)
- [ ] Präfixgrenze (A-87): `install.cmd -SkipSignatureCheck -Prefix <102 Zeichen>` → Exit 2, nichts angelegt;
      `<101 Zeichen>` → Exit 0
- [ ] optional: Flugmodus-Test (4.7.5)

**CI (GitHub Actions, `https://github.com/Ammxri/neurogrid`)**
- [x] Push auf `dev`, Läufe von `ci.yml` und `offline.yml` (erledigt, 4.7.9, 4.7.12)
- [x] Bündel-Tests bei jedem Push auf `dev` und `main` (D-15; seit Review R10, `offline.yml` Push `dev`/`main`);
      grün auf `55335ca` (Lauf 40403791782), Linux-Reinräume, glibc-Ablehnung `ubuntu:18.04`, offline-strace,
      `pdf-debian12`, Windows-Reinraum mit WFP-Audit unter PowerShell 5.1 und 7
- [ ] Testjobs von `ci.yml` (Windows und Linux × 3.11–3.13) grün – auf `55335ca` rot, zweite Fix-Runde:
      `<ERGEBNIS NACH P5-CI2>`; danach Abdeckungs-Gates und Vergleich in der CI
- [ ] Fehler eines Laufs ohne Anmeldung lesen: Annotationen über die Check-Run-API (4.7.9)

**Nur mit dem Projektverantwortlichen (offen, STOPP G1)**
- [ ] Entscheidung zu den 8 Einträgen in `known_missing.toml`, danach `known_missing.toml` leer und Notices neu
- [ ] Anfrage an die Validator-Entwickler versendet (D-16)
- [ ] zh-Prüfung, Sichtprüfung der Beispiel-PDFs, Bestätigung A-84..A-88, STOPP G1
- [ ] danach `0.1.0`, Push auf `main`, Tag, `release.yml`, `publish-pypi.yml`, `mirror-gitee.yml` (Spiegel) und das
      Gitee-Release von Hand aus dem Artefakt des Jobs `gitee-release` (R15); `docs.yml` und `corpus.yml` laufen erst
      mit `main`
