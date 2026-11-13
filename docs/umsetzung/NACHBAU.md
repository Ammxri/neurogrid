# NeuroGrid – Nachbau-Anleitung (technisch)

Diese Anleitung beschreibt, wie NeuroGrid von null auf einem eigenen Windows-11-Rechner wieder aufgebaut wird:
Werkzeuge, Umgebungen, Repository, Arbeitsweise, Phasen P0–P6 und P9, Prüfwerkzeuge, Testkorpus und Downloads. Sie ist
technisch; Geschäftsinhalte der PRD stehen hier nicht (A-01). Verweise auf die PRD nennen nur Abschnittsnummern.

**Stand P9:** Zweig `dev`, Commit `5596a8d` (02.11.2026): P9 vor P7 und P8 (D-13, D-19) nach den Bereichen Register,
Neueinwilligung, Paket und Vergleich (Freeze `159539d`), den Merges `c00475b`, `cd08106`, `74db563`, `cc7bc9c` mit
den Entscheidungen des Leads (`851031c`, `9597441`) und den Querschnittstests `5596a8d` (4.9). CI auf `5596a8d` grün
(`ci` 41447040471, `offline` 41447040492, `ci-integration` 41447040527) [D: `.local/p9/docs_brief.md`]. Version auf `dev` `1.0.0.dev0` seit `8e9575f`.

**Stand P6:** Zweig `dev`, Commit `0ffdd90` (02.11.2026): P6 nach den Bereichen vault, consent und yyt2029, den
Merges `9272cd9`, `3646997`, `c516598`, den Querschnittstests `40d6d16`, den Merge-Korrekturen `d50158b`, den
CI-Korrekturen `2f2a5a5` und der Fix-Runde nach dem Review (Zweig `p6-fix`, Merge `0ffdd90`; 4.8). CI auf `d50158b`:
`ci` 41402168683 rot nur an fünf Tests außerhalb der Bereiche, `offline` 41402168572 grün [G, CI d50158b]; CI auf
`0ffdd90`: ganz grün (`ci` 41422859481, `offline` 41422859830). Version auf `dev` `0.2.0.dev0`; v0.1.0 entsteht später aus `c4f240a` auf einem
Release-Zweig (D-19). STOPP G1 ist nach D-18 teilweise entschieden; offen sind zh- und Sichtprüfung (4.7.21).

**Stand P5:** Zweig `dev`, Commit `27c3e90` (28.10.2026): P5 nach Bau, Integration, Abnahme, Review, Fix-Runde, Merge
`55335ca`, Doku-Fix `181654e`, zweiter CI-Fix-Runde (Zweige `p5-ci2-*`, 4.7.14), Lizenztexten nach D-17 (4.7.15),
Doku-Merge `dcec9bd`, der Behebung des G1-Befunds an der Konsole (Zweig `p5-g1-console`, Merge `18da12f`; 4.7.17) und
der dritten CI-Fix-Runde (Zweige `p5-ci3-*`, Merges `ce87432`, `f3fe478`, `1dd0eac`; 4.7.18). Auf `18da12f` waren
alle sechs Testjobs von `ci` rot (Lauf 40609866806; `offline` 40609866836 grün) [G, CI 18da12f]; auf `27c3e90` sind
beide Workflows ganz grün (`ci` 40680346160, `offline` 40680346176; 4.7.19) [G, CI 27c3e90]. Die volle Testsuite läuft
seit dem 28.10.2026 nur in der CI, lokal nur die betroffenen Tests (4.0). G1 auf `18da12f`: 6 von 6 Datensätzen
bestanden, alle Kriterien erfüllt (151 min); G1 auf dem Endstand `27c3e90`: 6 von 6 Datensätzen in 5 Formaten bestanden, alle Kriterien erfüllt, 0 Probleme, V-01 erfüllt, V-06 ja (149 min 28 s; `.local/p5/ci3/g1_summary_27c3e90.md`) (4.7.20). **STOPP G1** ist
offen (4.7.21).

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

**Nur in der CI (GitHub Actions) reproduzierbar:** Linux-Testläufe (darunter die POSIX-Zweige von A-89),
Linux-Reinräume, glibc-Ablehnung, strace, PDF unter Debian 12, Windows-Reinraum mit WFP-Audit, PowerShell 7 (D-09;
lokal kein Linux und keine Änderung an Sicherheitseinstellungen). Lokal lassen sich die Runner-Bedingungen nur
nachstellen (1.6 Punkt 20–22).

**Braucht den Projektverantwortlichen:**

| Was | Wofür | Stand |
|---|---|---|
| Repository `https://github.com/Ammxri/neurogrid` (D-15, 26.10.2026) | CI, Linux (D-07, D-09, D-15) | angelegt und öffentlich; `dev` wird gepusht, CI läuft (4.7.9, 4.7.12, 4.7.16, 4.7.19) [G]; Merge auf `main`, Tag und Release erst nach G1 |
| die PRD selbst (PDF, privat) | nur für die Planung; liegt in `.local/prd/`, nie versioniert (A-01) | beim Projektverantwortlichen |
| Normtexte GB/T 47127, YY/T 2029, ISO/IEC TS 27571 | P7, P8, P10 (D-02, A-55) | nicht vorhanden |
| Konten: Gitee, PyPI/TestPyPI (Trusted Publishing) | Spiegel, Veröffentlichung (D-07, D-15) | nicht bekannt; weder Projektdokumente noch Faktenbasis belegen ein angelegtes Konto [NV] |
| Freigabe von Downloads außerhalb D-06 | CC-BY-4.0-Rechtstext, npm/jsr-Lizenzdateien des Validators (D-15); LGPL-3.0/GPL-3.0-Texte für isomorphic-git (D-16); URL-Liste der acht übrigen Lücken (D-17) | freigegeben und abgelegt (`LICENSES/`, `license-gate/third_party/`, `license-gate/licence_texts.toml`; D-15/D-16 in 4.7.7) [G] |
| Entscheidung zu den übrigen fehlenden Lizenztexten | Pakete im dist von hed-validator, hash-wasm (Brumme, argon2), `@jspm/core`, libaec/libsz im Linux-h5py-Wheel, Bibliotheken von python-build-standalone, focus-visible und material-design-color der Doku | entschieden (D-17, 27.10.2026); `license-gate/known_missing.toml` ist leer |
| Versand der Anfrage an die Validator-Entwickler (D-16) | Ersatz des LGPL-Abschnitts in isomorphic-git | Entwurf liegt privat in `.local/p5/upstream_issue_bids_validator.md`; Versand durch den Projektverantwortlichen [NV] |
| muttersprachliche zh-Prüfung | alle zh-Texte (A-07, STOPP G1); Prüfpaket aus `tools/zh_review_package.py` (4.7.8), nach dem letzten G1-Lauf neu erzeugt | offen |
| Bestätigung der Annahmen A-78..A-89, der R16-Lesart und der bekannten Grenzen; Freigabe von Merge und Release | STOPP G1 (4.7.21) | Annahmen und Lesarten bestätigt (D-18, 29.10.2026); offen: Kenntnisnahme der Grenzen, Release v0.1.0 aus `c4f240a` auf einem Release-Zweig (D-19) |
| Kernbegriffe von P6 in der zh-Prüfung, vollständige P6-Texte vor v0.2 | D-17 Option C (Liste in FORTSCHRITT „Für STOPP G1 vorgemerkt“) | offen |
| Bestätigung der Annahmen A-90..A-92 | STOPP G2 (4.8.11) | offen |
| vorübergehender eigener Runner für den echten Lauf der CI-Integration | V-03, vor dem Release von v1.0 (D-19) | offen; `ci-integration.yml` hat den Job `self-hosted` (nur von Hand, 4.9.6) |
| Bestätigung der Annahmen A-93..A-99 (darunter die Abweichung von A-95 vom Entwurf) | Freigabe nach P9, STOPP G2 (4.9.9) | offen |
| Kernbegriffe von P9 in der zh-Prüfung, vollständige P9-Texte vor v1.0 | D-19 wie D-17 Option C (Liste in FORTSCHRITT „Für STOPP G2 vorgemerkt“) | offen |
| Sichtprüfung einer Nachweismappe (`dossier.pdf`) | REP-08 (Muster D-18) | offen |
| juristische Prüfung der PIA-Vorlage durch eine in der VR China zugelassene Rechtsberatung | NV-F05, vor der ersten echten Verwendung, kein Release-Gate (D-19) | offen |
| ein echter Lauf der GitLab-Vorlage | V-03 (A-98) | offen, nie auf GitLab gelaufen |

### 0.3 Platzhalter

| Platzhalter | Bedeutung |
|---|---|
| `<Projektordner>` | Wurzel des Repositorys (enthält `pyproject.toml`) |
| `<Benutzerordner>` | Profilordner des Windows-Benutzers (`%USERPROFILE%`) |
| `%APPDATA%`, `%LOCALAPPDATA%`, `%TEMP%` | Windows-Standardordner (PowerShell: `$env:APPDATA` usw.; Git Bash: `$APPDATA` usw.) |
| `<uv>` | Pfad zu `uv.exe`, siehe 1.3 Schritt 3 |
| `<Ziel>` | ein beliebiger, leerer Ausgabeordner |
| `<REPO_URL>`, `<owner>/<repo>` | öffentliches Repository; für dieses Projekt `https://github.com/Ammxri/neurogrid` bzw. `Ammxri/neurogrid` (D-15). In der Nutzerdoku bleibt `<REPO_URL>` bis zum Release stehen (`tools/release_check.py` sperrt es außerhalb von `docs/umsetzung`) |
| `<v>` | Paketversion, heute `1.0.0.dev0` auf `dev` (seit `8e9575f`; von `8391420` bis `0ffdd90` `0.2.0.dev0`; bis `c4f240a` `0.1.0rc1`, die Zahlen von P5 gelten für diese Version) |

Alle Befehle laufen im `<Projektordner>`, wenn nichts anderes dasteht.

### 0.4 Belegstufen

Wichtige Angaben tragen eine Belegstufe:

| Kürzel | Bedeutung |
|---|---|
| **[G]** | geprüft: Befehl ausgeführt bzw. Datei oder Quelltext gelesen. Ohne Zusatz gilt für die Abschnitte bis P4 der Stand `19bd93c` (26.10.2026), für P5 der Stand `181654e` (27.10.2026), für die Abschnitte 4.7.14–4.7.17 und die dort genannten Zählungen der Stand `18da12f` (28.10.2026), für 4.7.18–4.7.21 der Stand `27c3e90` (28.10.2026), für 4.8 und die dort genannten Zählungen der Stand `0ffdd90` (02.11.2026), für 4.9 der Stand `5596a8d` (02.11.2026). „[G, CI 55335ca]“ heißt: in den öffentlichen Annotationen bzw. Job-Ergebnissen eines GitHub-Actions-Laufs auf `55335ca` gesehen, „[G, CI dcec9bd]“, „[G, CI 18da12f]“, „[G, CI 27c3e90]“ und „[G, CI d50158b]“ entsprechend auf diesen Commits |
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
| .NET SDK | 10.0.103 [D] | war vorhanden | nur eine Probe der zweiten CI-Fix-Runde (`GetFullPath` unter .NET 10 wie in PowerShell 7, `dotnet run`); für den Nachbau nicht nötig |

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
- `uv lock --check --offline` → „Resolved 103 packages“, Exit 0 [G, Stand 19bd93c, 181654e und 18da12f;
  `pyproject.toml` und `uv.lock` sind seit `584b7d2` unverändert, auch bis `27c3e90` (`git diff --stat 18da12f
  27c3e90`) und bis `0ffdd90` (`git diff --stat 27c3e90 0ffdd90 -- uv.lock pyproject.toml` leer; P6 brachte keine
  Abhängigkeit)]. (Bis P4 waren es 84 Pakete.)
- `.venv\Scripts\neurogrid.exe --help` zeigt die sechs Befehle und seit P6 die Gruppe `vault` (Anhang A) [G, 0ffdd90].
- Nach jeder Änderung an `uv.lock` (z. B. P5-Merge) alle drei Umgebungen neu synchronisieren.

**Forschungsumgebung (seit P11, A-100):** `research/neuroarena/.venv` mit Python 3.12 aus dem eigenen Lock des
Forschungsprojekts (142 Pakete, torch und torchaudio aus dem CPU-Index von PyTorch); unabhängig von den drei
Umgebungen oben, NeuroGrid läuft daraus nur als Kommandozeile der Hauptumgebung (A-101):
```powershell
uv sync --locked --no-build --project research/neuroarena
uv lock --check --project research/neuroarena
```

**Hilfsumgebungen**, die Werkzeuge selbst anlegen (nie von Hand):
- `.local/licenses/venv-runtime`, `venv-dev`, `venv-docs` – `tools/licenses.py` (aus `uv export`, A-86)
- Worktree-Umgebungen `<worktree>\.venv` – je Worktree `uv sync --locked --no-build` (3.5)

### 1.5 Umgebungsvariablen

Es gibt **keine Geheimnisse** im Repository. `.env.example` listet alle Variablen von NeuroGrid, seinen Werkzeugen
und Workflows mit leerem Wert; Hilfsvariablen der Shell (`UV_PROJECT_ENVIRONMENT`, `PYTHONIOENCODING`,
`PYTHONWARNDEFAULTENCODING`) stehen nicht darin [G], ebenso wenig Variablen, die Tests nur für ihre eigenen
Kindprozesse setzen (u. a. `NEUROGRID_TEST_CLOSE_QUEUE_SEMAPHORE`, `NEUROGRID_TEST_WMI_SEEN`, `NEUROGRID_TEST_MARKS`
der A-89-Tests; nie von Hand setzen) [G: `tests/`]. `.env` ist
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
11. **Debug-Log der Headless Shell:** Kindprozesse schreiben unter Windows ab Stufe INFO in `debug.log` neben
    `chrome-headless-shell.exe` (kein Schalter und keine Variable ändert das). NeuroGrid startet mit
    `--in-process-gpu` (die GPU läuft im Browserprozess) und unter Windows zusätzlich mit
    `--enable-features=CDPScreenshotNewSurface,NetworkServiceInProcess2` (auch der Netzwerkdienst läuft dort im
    Browserprozess; als Kindprozess schrieb er beim Schließen kurz nach dem Start die Warnung
    `Failed to post task ... sqlite_persistent_shared_dictionary_store.cc`). Der Wert wiederholt Playwrights
    eigenes `--enable-features` (Chromium behält nur den letzten Wert); ein `--disable-features` wird nie
    übergeben. Den `debug.log` der Renderer räumt NeuroGrid auf: beim Start entfernt es einen vorgefundenen
    `debug.log` (Rest eines abgebrochenen Laufs) und nach dem Lauf einen, den der Lauf angelegt hat; hält ein
    laufender Browser die Datei offen, schneidet der Lauf nur ab, was er angehängt hat (`kernel.pdf._ChildLog`;
    A-85, 4.7.6). Unter Linux loggen Kindprozesse nach stderr; der Netzwerkdienst bleibt dort ein eigener Prozess.
    Nach Testläufen `install_pdf_browser.py --check` ausführen; es schlägt fehl, solange ein `debug.log` neben der
    exe liegt.
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
20. **8.3-Pfade der GitHub-Runner:** Auf `windows-latest` heißt `TEMP` `C:\Users\RUNNER~1\AppData\Local\Temp`; .NET
    `GetFullPath` liefert die lange Schreibweise (`runneradmin`), Windows PowerShell 5.1 bei teilweise fehlenden
    Ordnern je nach Namen nur teilweise. Lokal nachstellen: `TEMP` und `TMP` auf die 8.3-Schreibweise eines Ordners mit
    langem Namen setzen (der Datenträger muss 8.3-Namen anlegen, Prüfung mit `dir /x`), dann pytest (4.7.14).
21. **Locale beim Lesen im Textmodus:** `open()` ohne `encoding` nimmt die Locale (Runner: UTF-8, Windows: ANSI-Codepage,
    cp1252 bzw. cp936); MNE 1.13.2 liest die BrainVision-Markerdatei ein zweites Mal so. Python bestimmt die Locale in C,
    sie lässt sich zur Laufzeit nicht umstellen. Nachstellen: `PYTHONUTF8=1` (am nächsten am Runner) oder die Hilfen
    `locale_encoding`, `linux_codecs`, `linux_text_system` aus `tests/conftest.py` (4.7.14).
22. **Codec-Aliase nur unter Windows:** `ansi` und `dbcs` zeigen auf `mbcs`, das nur unter Windows existiert;
    `codecs.lookup("ANSI")` endet unter Linux mit `LookupError`. Ein Kopierweg, der den Codepage-Wert als Codec-Namen
    nimmt, verhält sich deshalb je Plattform anders (4.7.14).
23. **WSL-Stub statt Git Bash:** Aus PowerShell findet `shutil.which("bash")` `C:\Windows\system32\bash.exe` (WSL ohne
    Distribution, D-09); dann scheitert `tests/cli/test_report_pdf_cli.py::test_report_html_pdf_zh_en_writes_four_files`.
    Diesen Test aus Git Bash laufen lassen [D].
24. **Ein Stash-Stapel für alle Worktrees:** `git stash` legt Einträge im gemeinsamen Repository ab; jeder Worktree
    sieht und verschiebt denselben Stapel (`stash@{0}` ist je nach Zeitpunkt ein anderer Eintrag). Einträge nur per
    SHA anwenden, nie per Index löschen, in parallelen Worktrees möglichst gar nicht stashen; nach dem Merge den Stapel
    leeren (heute leer [G]).
25. **CPython 3.12 und WMI:** `platform.uname()`/`platform.machine()` fragen unter 3.12 WMI; bricht die Abfrage ab,
    schließt ihr weiterlaufender Thread einen fremden Handle (A-89, 4.7.17). Eigene Mess- oder Prüfskripte mit
    Prozesspools unter Windows deshalb wie NeuroGrid mit `neurogrid.kernel.processes.avoid_wmi()` starten.
26. **Agenten brechen ab:** Verbindungsabbrüche (`ECONNRESET`) und Anmeldefehler (`403`) beendeten in P5 mehrere
    Agenten mitten in Bau, Verifikation oder Reparatur. Ein abgebrochener Lauf hinterlässt gestagte, gestashte oder
    ungespeicherte Änderungen im Worktree. Vor der Wiederaufnahme `git status`, `git diff`, `git stash list` lesen und
    die Reste bewusst übernehmen oder verwerfen (in P5 beides vorgekommen, 4.7.14).
27. **pytest `capfd` und geforkte Kinder:** `capfd` setzt `sys.stdout`/`sys.stderr` auf Objekte, die auf einen
    Deskriptor über 2 schreiben (eine Temp-Datei; 1 und 2 zeigen per `dup2` ebenfalls dorthin). Ein unter `capfd`
    geforktes Kind schreibt über die geerbten Objekte dorthin; 0–2 auf das Nullgerät zu legen reicht dann nicht
    (4.7.18, P2) [D].
28. **`subprocess.run(capture_output=True)` wartet auf jeden Halter der Pipes.** Der resource tracker von
    `multiprocessing` erbt 0–2 und `sys.stderr.fileno()` (`util.spawnv_passfds`) und schließt in `main()` nur stdin und
    stdout; ein mit der Konsole gestarteter tracker verzögert `run()` also bis zu seinem Aufräumen, ein stummer nicht.
    Tests, die danach nach seinen Spuren suchen, müssen auf sein Ende warten (4.7.18, P1) [D].
29. **onnxruntime unter Linux schreibt nach Deskriptor 2:** Das Linux-Wheel 1.31.0 meldet beim Anlegen seiner Umgebung
    Fehler der Geräteerkennung („GPU device discovery failed: …“, `/sys/class/drm`) über seinen Standard-Logger nach
    stderr; das Windows-Build hat eine eigene Geräteerkennung und schreibt seine Zeilen über `std::wclog`. Eine
    Umgebungsvariable für die Standardstufe gibt es nicht, `set_default_logger_severity` legt die Umgebung erst an
    (4.7.18, P3) [D].
30. **Quelltexte vergleichen:** Die Standardbibliothek des System-Python 3.13 liegt mit CRLF vor; beim Vergleich mit
    der von uv verwalteten 3.11- oder 3.12-`Lib` `diff --strip-trailing-cr` verwenden [D].
31. **mypy unter win32 und POSIX-Zweige:** Nach `if sys.platform == "win32": yield; return` meldet mypy unter win32
    Namen aus dem folgenden POSIX-Code; stattdessen `if sys.platform != "win32": … else: …` schreiben [D].
32. **Schwere Testläufe nicht parallel:** Zwei gleichzeitige pytest-Läufe auf diesem Rechner ließen
    `test_quality_review_p3.py::test_one_recording_with_jobs_4_equals_jobs_1` (Grenze 120 s) mit 138 s, 155 s bzw. 199 s
    scheitern; allein dauert er 75–90 s. Python-Versionen nacheinander prüfen (4.7.18) [D].

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

- `main`: nur der erste Doku-Commit `75e05a6`; Releases kommen später von `main` (Release-Gate). Nach D-19 wird
  v0.1.0 aus dem P5-Stand `c4f240a` plus den Korrekturen der Prüfungen auf einem Release-Zweig geschnitten, nicht aus
  `dev`; ein v0.2.0 ebenso aus dem Endstand von P6. Einen solchen Release-Zweig gibt es noch nicht [G: `git branch -a`].
- `dev`: Arbeitszweig (D-07, D-09). Remote `origin` = `https://github.com/Ammxri/neurogrid.git` [G]; seit dem
  26.10.2026 wird nur `dev` gepusht (D-15), `main`, Tags und Releases erst nach G1. Jeder Push auf `dev` startet
  `ci.yml` und `offline.yml` (4.7.12).
- Bereichszweige je Phase (`p4-*`, `p5-*`) in eigenen Worktrees, nach dem Merge gelöscht (3.5); in P5 zusätzlich
  Integrations- (`p5-int-*`), Abnahme- (`p5-acceptance`), Lizenztext- (`p5-licence-texts`, `p5-licence-texts-2`),
  Doku- (`p5-docs`, `p5-final-docs`) und Fix-Zweige (`p5-fix-*`, `p5-ci2-*`, `p5-g1-console`, `p5-ci3-*`); in P6
  `p6-vault`, `p6-consent`, `p6-yyt2029` (dazu die Sicherung `backup-p6-yyt2029-518964e`), `p6-fix` und `p6-docs`
  (4.8.1). Die von der
  Orchestrierung angelegten Worktrees tragen zusätzlich Zweige `worktree-wf_*`; sie bleiben nach dem Merge stehen
  und lassen sich mit `git branch -D` entfernen, sobald ihr Worktree gelöst ist [G: `git branch`].
- Pushes auf `origin/dev` [G: Reflog von `origin/dev`]: `42e129d` (26.10. 12:57), `c3be509` (17:05), `55335ca`
  (22:22), `dcec9bd` (27.10. 09:52), `18da12f` (28.10. 01:36), `27c3e90` (28.10. 12:29); `181654e` und die Merges
  der dritten CI-Fix-Runde wurden nie allein gepusht. Danach `7426dee` und `2159e89` (28.10. 20:38), `c4f240a`
  (29.10. 01:54), `d50158b` (02.11. 07:47) und `0ffdd90` (02.11. 10:42); die P6-Commits vor `d50158b` und `2f2a5a5`
  wurden nicht allein gepusht.
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
| `LICENSE`, `NOTICE`, `LICENSES/` | Apache-2.0, Lizenzhinweis, Lizenztexte der eigenen Dateien: `Apache-2.0.txt`, `CC-BY-4.0.txt` (seit D-15), `OFL-1.1.txt`, `LicenseRef-NeuroGrid-Reproduced-Notices.txt` (R26) [G] |
| `REUSE.toml` | Lizenz je Pfad (2.7) |
| `THIRD_PARTY_NOTICES.txt` | erzeugt von `tools/notices.py` (A-86) |
| `README.md`, `DATA_SOURCES.md` | Kurzbeschreibung zh/en; Herkunft von Fixtures und Korpus |
| `mkdocs.yml`, `docs/en`, `docs/zh`, `docs/_data`, `docs/assets` | Nutzerdoku (A-86) |
| `docs/umsetzung/` | Matrix, Konzept, Entscheidungen, Fortschritt, diese Anleitung (Deutsch, nicht Teil der Website) |
| `license-gate/` | `allowlist.txt`, `exceptions.txt`, `components.toml`, `known_missing.toml`, `network_baseline.json`, `licence_texts.toml` (Herkunft geladener Texte), `third_party/` (Lizenztexte gebündelter Teile mit `manifest.toml`): `bids-validator-3.0.2/` (gebündelte npm/jsr-Pakete, D-15/D-16/D-17), `h5py-3.16.0/` (libaec/libsz, D-17), `mkdocs-material-9.7.7/` (Prüfung der Doku-Seite, R19; Texte von focus-visible und material-design-color D-17), `python-build-standalone-3.12.15+20261009/` (D-17) |
| `packaging/` | Installer (`install.cmd`, `install.ps1`, `install.sh`), `README.bundle.txt`, `release-notes.md`, `gitee-release.md` (R15), `bundle_lock.json`, `ci/*` (Reinraum, strace) |
| `.github/workflows/` | `ci.yml`, `offline.yml`, `corpus.yml`, `docs.yml`, `release.yml`, `publish-pypi.yml`, `mirror-gitee.yml`, seit P9 `ci-integration.yml` (4.9.6) |
| `action.yml`, `ci-templates/gitlab-ci.yml` | seit P9: GitHub Action (zusammengesetzt) und GitLab-Vorlage der CI-Integration beim Kunden (A-98, 4.9.6) |
| `src/neurogrid/` | Paket (2.4) |
| `tests/` | Tests und Fixtures |
| `tools/` | Werkzeuge außerhalb des Pakets (Abschnitt 5) |

Umfang [G, 0ffdd90]: 652 versionierte Dateien (davon 183 unter `license-gate/third_party/`); 25 513 Zeilen Python
in `src`, 56 313 in `tests` (`git ls-files 'src/*.py' | xargs cat | wc -l`, ebenso für `tests`; dieselbe Zählung
ergibt auf `18da12f` die 21 553 Zeilen unten); 32 Fixture-Ordner. (Stand `18da12f`: 615 Dateien, 21 553 / 48 179
Zeilen; Stand `181654e`: 540 Dateien, davon 111 unter `third_party`, 20 764 / 45 738 Zeilen; Stand `19bd93c`:
413 Dateien, 19 738 / 38 199 Zeilen.)

### 2.4 Paketstruktur `src/neurogrid`

| Teil | Inhalt | Phase |
|---|---|---|
| `cli.py`, `__main__.py` | Typer-App: `scan`, `convert`, `check`, `report`, `manifest`, `verify`; seit P6 die Gruppen `vault` (`init`, `log`, `verify`) und `vault consent` (`add`) mit verschachtelten Hilfebereichen, `check --role`, `report --config` (A-90); seit P9 `diff`, `vault export` und `report --format dossier` (A-96, A-97, A-99); `--lang`, `--debug`; eigene Hilfe zh/en (NG-N06, A-86); Netzwerkschutz | P1, P2, P4, P5, P6, P9 |
| `config.py`, `pipeline.py`, `metadata.py`, `convert.py`, `validator.py` | Konfiguration (strikt), Abläufe, Metadaten mit Herkunft (A-04), BIDS-Konvertierung (A-05), Validator als abgeschotteter deno-Prozess (A-06) | P1, P2 |
| `diff.py`, `dossier.py` | Versionsvergleich zweier results.json (A-97; importiert nur kernel, model, `report.texts`); Nachweismappe (A-99; darf report und kernel importieren) | P9 |
| `kernel/` | Regelmotor, Befunde, kanonisches JSON (A-61), Matcher (A-14), i18n, Netzwerkschutz (A-49), Provenienz, Nachweise, Sicherheit (A-52..A-54), HTML-Rendering; ab P5 `fonts.py`, `pdf.py`, `pdf_linux_packages.json`, seit dem G1-Befund `processes.py` (Hilfsprozesse ohne Konsole, `avoid_wmi`; A-89). Importgrenze: nur Standardbibliothek, Pydantic, Jinja2, PyYAML, fontTools, Playwright, pypdf; `mypy --strict` (A-23, A-85) | P1, P4, P5 |
| `model/` | Pydantic-Datenmodell (DM-01..DM-10) und `results.json`; seit P6 `access.py` (AccessEvent, DM-09) und `consent.py` (ConsentScope, DM-08), beide nur mit Kernimporten; seit P9 `_registers.py`, `roles.py`, `retention.py`, `risks.py` (nur Kern und Modelle), `export.py` (ExportIndex), `diff.py` (DiffResult) | P1 ff., P6, P9 |
| `io/` | Adapter EDF/BDF, BrainVision, EEGLAB, FIF, BIDS; Discovery; Annotationen, participants, splits, Provenienz (seit P6 ohne die Protokolle des Vaults im Manifest) | P1, P2, P4, P6 |
| `checks/` | Prüfer M01–M14, BIDS, Nachweise, seit P6 `consent.py` (M14) und `access.py` (NV03), seit P9 dort auch CORE-M14-02 und CORE-NV04-01 und neu `retention.py` (NV05) („Prüfer messen, sie entscheiden nie“, ARC-02) | P1–P4, P6, P9 |
| `vault/` | NeuroVault (A-90, A-91): `store.py` (Ort, Zustände, `vault init`, Ersetzen in einem Schritt), `lock.py` (Sperre `access.jsonl.lock`), `ledger.py` (Hash-Kette, Anhängen, Prüfung), `roles.py`, `consents.py` (`consents.yaml`, `consents.tsv`, `vault consent add`), `_os.py` (aller Plattformcode mit Markierungen); seit P9 `roles.py` mit Erlaubnisregel, `retention.py`, `pia.py`, `risks.py`, `export.py` und `templates/pia.zh.md`, `pia.en.md` (A-93 bis A-96); importiert nur kernel, model, io, config und vault | P6, P9 |
| `quality/` | Signalmetriken M06–M09, Streaming, Stichprobe, Prozesspool | P3, D-14 |
| `report/` | `render.py`, `tables.py`, `charts.py`, `glyphs.py`, `output.py`, `texts.py`, Vorlage, i18n zh/en/de, Validator-Texte, Wortlisten, Schriften; seit P6 der zusammengefasste M14-Block (`tables.consent_table`, A-91), die Zeile des Zugriffsprotokolls auf dem Deckblatt und `report.text.os_access` im Anhang (A-90); seit P9 der Abschnitt Neueinwilligung (A-95), `identify.py` (erkennt Berichte und Mappe für den Export) und `templates/dossier.html.j2` (A-99) | P1, P5, P6, P9 |
| `rulepacks/` | `core.yaml` (1.0.0 seit P9, 0.2.0 seit P6, vorher 0.1.1), `bids.yaml`, `gxdsl008.yaml`, `yyt2029.yaml` (Platzhalter, P6), `calibration/core.json` | P1–P6 |
| `schemas/` | JSON-Schemas (erzeugt): results, scan, config, rulepack, evidence, manifest, seit P6 access_event und consents, seit P9 roles, risks, retention, export_index und diff (13) | P1, P4, P6, P9 |

### 2.5 `pyproject.toml` (Stand 0ffdd90, seit `584b7d2` unverändert)

- `[build-system]`: `hatchling==1.32.4`. Version dynamisch aus `src/neurogrid/__init__.py` (`0.2.0.dev0` seit
  `8391420`, vorher `0.1.0rc1`).
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

- `uv.lock`: `version = 1`, `revision = 5`, 103 Pakete (Stand 584b7d2, unverändert bis 0ffdd90) [G]. Einzige
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
  (D-15, 4.7.7); Herkunft, Größe und SHA-256 jedes geladenen Lizenztextes stehen in `license-gate/licence_texts.toml`
  (Standardtexte) bzw. in den Manifesten von `license-gate/third_party/` (D-15, D-16, D-17).
- **Lizenz-Gate (`tools/licenses.py`, NG-N07):** Stufe 1 `pip-licenses --allow-only` gegen
  `license-gate/allowlist.txt` mit versionsgebundenen Ausnahmen (`pybv:0.8.1`, `pyprep:0.9.0` in `exceptions.txt`);
  Stufe 2 sperrt jede Lizenz mit „GPL“ (`--partial-match`). Getrennt für `runtime`, `dev`, `docs`. Dazu
  `--components`: statische Prüfung jeder nativen Datei der gelockten Wheels beider Zielplattformen und der
  Bündelteile gegen `license-gate/components.toml` (D-08).
- **Lizenz-Gate des Forschungsprojekts (seit P11, A-108, D-20):** `tools/licenses.py --target research` prüft
  Laufzeit und Dev des Forschungs-Locks gegen `license-gate/research/allowlist.txt`, Ausnahmen nur
  versionsgebunden mit ihrer Entscheidung in `license-gate/research/exceptions.toml` (GPL und AGPL verboten);
  `--target research --components --download` prüft die nativen und gebündelten Teile der Wheels beider Ziele gegen
  `license-gate/research/components.toml` (Wheels in `.local/research-wheels/`).
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
| `src/neurogrid/vault/templates/pia.zh.md`, `pia.en.md` | Vorlagen der Folgenabschätzung (Platzhalter, A-94); die Vorlagen `roles.yaml`, `risks.yaml`, `retention.yaml` stehen in `vault/store.py` | von Hand; juristische Prüfung vor erster echter Verwendung (D-19) |
| `tests/fixtures/synthetic/**` | 32 Fixture-Ordner | `tools/gen_fixtures.py` |
| `src/neurogrid/report/fonts/*` + `fonts.json` | statische Noto-Sans-SC-Schnitte und Herkunft | `tools/build_fonts.py` |
| `src/neurogrid/kernel/pdf_linux_packages.json` | apt-Pakete der Headless Shell (Debian 12, Ubuntu 22.04/24.04) | `tools/linux_pdf_packages.py --write` |
| `docs/{en,zh}/reference/*.md`, generierte Blöcke in `metrics.md` | Registry, Regeln, Schwellen | `tools/gen_docs.py` |
| `docs/_data/*.yaml` | Bezeichnungen und Beschreibungen der Doku | von Hand |
| `mkdocs.yml`, `tools/mkdocs_hooks.py` | Seitenstruktur, Suche, Hooks | von Hand |
| `THIRD_PARTY_NOTICES.txt` | Drittanbieter-Hinweise | `tools/notices.py` |
| `license-gate/components.toml` | geprüfte native/nicht-Python-Komponenten | von Hand, geprüft |
| `license-gate/known_missing.toml` | fehlende Lizenztexte (seit D-17 leer; jeder Eintrag sperrt das Release; Abschnitt 8) | von Hand |
| `license-gate/licence_texts.toml` | Herkunft (URL, Größe, SHA-256, Abrufdatum, Entscheidung) jedes geladenen Standard-Lizenztexts | von Hand, von `tests/docs/test_licensing.py` geprüft |
| `license-gate/third_party/*/manifest.toml` | geprüfte Drittanbieter-Teile mit Texten (Validator-Bündel, Doku-Theme, seit D-17 auch h5py und python-build-standalone) mit URL, Größe, SHA-256, Abrufdatum und Entscheidung | einmalig erstellt, mit D-17 ergänzt (Skripte nur im Scratchpad [NV]), von `notices.py --check`, `build_docs.py` und `tests/docs/test_licensing.py` geprüft |
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

- `ENTSCHEIDUNGEN.md`: geprüfte Fakten, D-01..D-19 (Entscheidungen des Projektverantwortlichen; D-18 vom 29.10.,
  D-19 vom 02.11.2026), A-00..A-92 (Annahmen; je Phase ein Block „Annahmen aus der Umsetzung von Px“).
- P5 bringt A-84 Bericht, A-85 PDF, A-86 Dokumentation/Meldungen/Notices/Lizenzen, A-87
  Bündel/Signatur/Installation/Workflows, A-88 Abnahme und, aus dem G1-Befund auf `dcec9bd`, A-89 (Hilfsprozesse ohne
  Konsole, `platform` ohne WMI; am Ende des P5-Blocks nach A-88 angehängt). Grundlage sind die verbindlichen Vorgaben
  B1–B6 des Leads sowie die `decisions_for_docs` der Bereiche, der Integration, der Fix-Runden und der Behebung des
  G1-Befunds; sie stehen in ENTSCHEIDUNGEN („Annahmen aus der Umsetzung von P5“), zusammen mit den Hinweisen an älteren
  Annahmen (u. a. A-51 Konsole, A-54 Arbeitsordner, A-67 Pfade unter Linux).
- **Nummern ab P6:** Der P6-Entwurf (privat, `.local/p6/`) hatte A-89..A-91 nur vorläufig vergeben und sah für Code,
  Tests und Texte von P6 die Token `A-P6V`, `A-P6C`, `A-P6Y` vor. Da A-89 zu P5 gehört, vergeben die endgültigen
  Vorgaben vom 29.10.2026 (`.local/p6/p6_final.md`) A-90 (NeuroVault v0.2), A-91 (Einwilligung M14) und A-92
  (Gerüst yyt2029, Auslegungsfragen) direkt; die Token entfielen und stehen außerhalb von `docs/umsetzung` nirgends
  [G: `grep -rn "A-P6" src tests tools docs`].
- P6 bringt A-90..A-92 (Block „Annahmen aus der Umsetzung von P6“, für STOPP G2 vorgemerkt) und die Hinweise an A-30,
  A-41, A-82 und A-83. Grundlage sind die Vorgaben des Leads, die Berichte des Freeze und des Bereichs yyt2029
  (`.local/p6/workflow_result.json`), für vault und consent Code, Commit-Meldungen, Tests und Nutzerdoku (die
  Bau-Agenten endeten vor ihrem Bericht, 4.8.4) und die Festlegungen der Fix-Runde (`.local/p6/fix_decisions.md`).

### 3.4 Orchestrierungsmuster (ab P4, voll ausgebildet in P5)

| Schritt | Was geschieht | Ergebnis |
|---|---|---|
| 1 Bereichsspezifikationen | je Bereich eine Spezifikation (Anforderungen, Entwurf, Dateien, neue Abhängigkeiten, Downloads, Tests, offene Fragen, Risiken, Schnittstellen, i18n-Schlüssel, Proben) | P4: 4 Bereiche; P5: report, pdf, docs, bundle, acceptance; P6: vault, consent, yyt2029 (`.local/p6/spec/*.json`) |
| 2 Kritiker | ein unabhängiger Prüfer liest alle Spezifikationen: Korrekturen, Fehlendes, Widersprüche, Fragen an den Projektverantwortlichen | P4: Lücken G1–G16, Widersprüche X1–X18; P6: Korrekturen, Fehlendes und 13 Konflikte, aufgelöst im Entwurf der Vorgaben |
| 3 Lead-Entscheidungen | verbindliche Vorgaben im Freigabemodus A; „wo diese Datei und eine Spezifikation abweichen, gilt diese Datei“ | P4: C1–C11 → A-80..A-83; P5: B1–B6 → A-84..A-88; P6: Entwurf und endgültige Vorgaben (29.10.2026) → A-90..A-92 |
| 4 Gemeinsamer Unterbau | was alle Bereiche brauchen, vorab auf `dev` | P4: `CheckContext` (`4253a65`); P6: Schnittstellen-Freeze `f023146` als erster Commit des Bereichs vault |
| 5 Paralleler Bau | je Bereich ein Zweig in eigenem Worktree; jeder liefert Code, Tests, `decisions_for_docs`, `facts_for_build_guide`, Lücken | P4: `p4-*`; P5: `p5-report`, `p5-pdf`, `p5-docs`, `p5-bundle`; P6: `p6-vault`, `p6-consent`, `p6-yyt2029` |
| 6 Unabhängige Verifikation | ein anderer Prüfer prüft jeden Bereich gegen Spezifikation und Vorgaben, findet neue Probleme | P5: report 15/7, pdf 4/8, docs 7/5, bundle 9/13 (Prüfpunkte/neue Probleme) [D]; P6: nur yyt2029 19/7; vault und consent ohne eigene Verifikation (Bau-Agenten am Sitzungslimit beendet), an ihre Stelle trat das Review in Schritt 9 (4.8) |
| 7 Reparatur | Reparatur-Commit je Bereich | P5: `133bb94`, `7c99a82`, `9331600`, `2d41f44`; P6: `9a9433e` (yyt2029) |
| 8 Merge | in fester Reihenfolge auf `dev`, danach `uv lock`, Generatoren neu | P5: report, docs, pdf, bundle; P6: consent, vault, yyt2029 (`9272cd9`, `3646997`, `c516598`) |
| 8a Integration und Abnahme | Integrationsaufgaben am gemergten Stand, Abnahmeskript, Lizenztexte; je Zweig Bau → unabhängige Verifikation → Reparatur | P5: `p5-int-pdf`, `p5-int-pack`, `p5-acceptance`, `p5-licence-texts` (4.7.6–4.7.8); P6: Querschnittstests `40d6d16`, Merge-Korrekturen `d50158b`; keine G1-Abnahme (4.8.6) |
| 9 Adversariales Review | mehrere Prüfrichtungen; jeder Befund wird von einem zweiten Prüfer zu widerlegen versucht (bestätigt / strittig / beabsichtigt / widerlegt), schwere doppelt | P4: 57 Befunde; P5: 30 Befunde R00–R29 (4.7.10); P6: ein unabhängiges Review nur mit Lesezugriff auf vault und consent, 7 Befunde (4.8.8) |
| 10 Fixes | Fix-Zweige je Bereich, je Befund ein Regressionstest, Nachprüfung, Reparaturrunde | P4: `p4-fix-*`; P5: `p5-fix-report`, `-linux`, `-bundle`, `-docs`, dazu die CI-Fehler (4.7.11); P6: `p6-fix`, ein Commit je Befund, Merge `0ffdd90` (4.8.8) |
| 11 Gegenprüfung | gemergter Stand auf Rückfälle und neue Fehler aus dem Zusammenspiel | P4: `p4-fix2-*`; P5: die CI auf dem gemergten Stand (`55335ca`), danach `p5-ci2-*`; die CI auf `18da12f`, danach `p5-ci3-*` (4.7.12, 4.7.14, 4.7.18); P6: die CI auf `d50158b`, danach `2f2a5a5` (4.8.7) |
| 11a Abnahme am Endstand | voller G1-Lauf auf dem gemergten, CI-grünen Stand; jeder Befund wie in Schritt 10 behoben | P5: Befund an der Konsole auf `dcec9bd` → `p5-g1-console` (4.7.17); auf `18da12f` bestanden, einmal auf dem Endstand `27c3e90` (4.7.20) |
| 12 Doku und Commit | Matrix, ENTSCHEIDUNGEN, KONZEPT, FORTSCHRITT; Commit mit Anforderungs-IDs | P4: `e68e33e`; P5: Zweig `p5-docs` (Merge `dcec9bd`), Schlussfassung `p5-final-docs` (diese Fassung); P6: Zweig `p6-docs` (4.8) |

Seit D-15 (Tempo): volle Testsuite nur nach dem Merge; ein Review je Phase mit vier Prüfrichtungen; diese Anleitung
entsteht parallel. Seit dem 28.10.2026 läuft die volle Testsuite nur noch in der CI, und die Doku entsteht einmal je
Phase nach grüner CI (Prozessentscheidung, 4.0).

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

Weitere Python-Versionen in einem Worktree (dritte CI-Fix-Runde, je ≈ 1 min) [D]:
```powershell
$env:UV_PROJECT_ENVIRONMENT = ".venv312"   # bzw. ".venv313"
& <uv> sync --locked --no-build --python 3.12   # bzw. 3.13 (System-Python 3.13.7)
```
uv legt in jede dieser Umgebungen eine `.gitignore` mit `*`; `git status` bleibt sauber.

### 3.6 Was davon von Hand geht

- **Vollständig von Hand:** Matrix, Konzept, Entscheidungslog, jede Bauphase, alle Prüfbefehle, Commit-Form. Die
  Werkzeuge sind gewöhnliche Python-Skripte.
- **Nur mit Ersatz:** Parallelität (stattdessen Bereiche nacheinander in eigenen Zweigen bauen) und
  Unabhängigkeit von Verifikation und Review. Ersatz: Spezifikation und Vorgaben schriftlich festhalten, jeden
  Bereich zeitversetzt gegen eine Prüfliste je Prüfrichtung durchgehen, jeden Befund mit einem eigenen
  Reproduktionsskript belegen, bevor er behoben wird, und nach dem Merge die Gegenprüfung (Schritt 11) wiederholen.
- Zeitbedarf ist nicht protokolliert [NV]; die volle Suite dauert je Lauf 13–18 min (bis P4), in P5 mit
  `NEUROGRID_REQUIRE_PDF=1` 26–33 min [D]; auf `dcec9bd` bei überlastetem Rechner 4 h 07 min
  [G: `.local/logs/full_dcec9bd.log`]. Zeitgrenzen einzelner Tests reißen dann (4.7.17).
- Die Orchestrierung ist nicht ausfallsicher: In der zweiten CI-Fix-Runde brachen sechs Agenten durch
  Verbindungsabbrüche oder Anmeldefehler ab, einer hing 6455 s ohne Fortschritt; zwei weitere Läufe nahmen die Arbeit
  aus den Worktrees wieder auf (4.7.14, 1.6 Punkt 26) [D].

### 3.7 Commit-Form und Rückverfolgbarkeit (TECH-12, A-43)

- Präfix `feat:` / `fix:` / `docs:` / `chore:`, Anforderungs-IDs in Klammern im Betreff, Text als Stichpunktliste,
  Schlusszeile `Co-Authored-By: …` (wo ein Werkzeug mitgeschrieben hat).
- Vor jedem Commit (PowerShell):
  ```powershell
  .\.venv\Scripts\python.exe tools\check_commit_ids.py --message-file <datei>
  git commit -F <datei>
  ```
- Jeder datierte FORTSCHRITT-Eintrag nennt IDs. Prüfung des ganzen Stands: `tools/check_commit_ids.py` →
  „33 commit(s) and 5 phase entr(y/ies) checked, 0 problem(s)“ [G, 19bd93c]; „146 commit(s) and 5 phase entr(y/ies) checked, 0 problem(s)“ [G, 181654e];
  „181 commit(s) and 7 phase entr(y/ies) checked, 0 problem(s)“ [G, 18da12f];
  „226 commit(s) and 9 phase entr(y/ies) checked, 0 problem(s)“ [G, 0ffdd90 mit der Doku von P6 im Arbeitsbaum].
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
& $PY tools\notices.py --wheelhouse .local\notices-wheels --check   # ab P5; seit D-17 Exit 0, kein "incomplete"
& $PY tools\check_matrix_coverage.py
& $PY tools\check_commit_ids.py
```
Volle Suite ab P5: `$env:NEUROGRID_REQUIRE_PDF = "1"; $env:PYTHONWARNDEFAULTENCODING = "1"; & $PY -m pytest -q -p
no:cacheprovider` (mit `UV` gesetzt oder über `uv run --no-sync`, sonst überspringen die uv-Tests).

**Woher die Testzahlen kommen (Prozessentscheidung des Leads vom 28.10.2026 nach der Kritik des
Projektverantwortlichen; A-87):**
- Die volle Testsuite läuft nur in der CI, in den sechs Testjobs von `ci.yml` (windows-latest und ubuntu-24.04 ×
  Python 3.11/3.12/3.13). Lokal laufen nur die Tests, die eine Änderung betrifft, z. B.
  `& $PY -m pytest -q -p no:cacheprovider <betroffene Testdateien>`.
- Testzahlen und Abdeckung werden aus den Notice-Annotationen der CI gelesen, die ein grüner Testjob seit `2a49a0c`
  schreibt (ohne Anmeldung lesbar, 4.7.19), nicht aus einem lokalen Lauf.
- Die Doku (Matrix, ENTSCHEIDUNGEN, FORTSCHRITT, diese Anleitung) entsteht einmal je Phase, nach grüner CI.
- Lange Läufe (G1, Korpustests `-m corpus`) laufen nur einmal, auf dem Endstand.
- Die lokalen vollen Läufe früherer Runden bleiben als Geschichte stehen, z. B. `dcec9bd`: 3647 bestanden,
  21 übersprungen, 127 abgewählt, 1 fehlgeschlagen (A-88; 4.7.20).

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

### 4.7 P5 – Bericht, PDF, Doku, Bündel (2026-10-23 bis 10-28; Stand 27c3e90)

Matrix: schließt NG-F13, NG-F14, NG-F18, CLI-05, REP-00..REP-07, POS-01, POS-02, ARC-05, ARC-06, TECH-05..TECH-08,
TECH-10, NG-N01, NG-N03..NG-N08, CON-01, CON-04, CON-05, V-01, V-06, UF-01, UF-07, UF-08 ab (36), trägt zu UF-02,
CON-02, TECH-01 bei (KONZEPT 6) [G]. Den Stand je Zeile führt die Matrix. Auf `181654e` standen die Zeilen, deren
Nachweis die CI-Testjobs sind, auf `nicht verifiziert` („umgesetzt, Nachweis ausstehend“: NG-F13, REP-00, TECH-05,
TECH-07, NG-N04, NG-N08, UF-01; 4.7.12); mit dem grünen Lauf auf `dcec9bd` liegt dieser Nachweis ausgeführt vor
(4.7.16). Seitdem stehen TECH-05, TECH-07 und NG-N08 auf `erfüllt`, NG-N04 auf `teilweise` (Windows 10 nicht
verifiziert); NG-F13, REP-00 und UF-01 bleiben bis zur Sichtprüfung der PDFs und zum G1-Lauf auf dem Endstand
`nicht verifiziert`, NG-N07 ist seit D-17 `erfüllt`. Auf `18da12f` mit der Behebung des G1-Befunds (A-89) waren
alle sechs Testjobs rot: überall `test_env_example`, dazu Konsolentests von A-89 unter Linux und unter Windows mit
Python 3.11 (4.7.18); nach der dritten CI-Fix-Runde sind auf `27c3e90` alle Jobs grün (4.7.19) [G, CI 27c3e90].

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
| 27.10. 02:22 – 08:32 | Zweige `p5-ci2-chrome-log` (`88b15a4`, `c5c6ff6`), `p5-ci2-win-runner` (`5d7af87`, `1d07ad9`, `5c40d24`), `p5-ci2-linux-p2` (`ad902d8`, `bf81d92`, `d8f8be9`, `18bb4ef`, `96e5986`, `c5f41c4`), `p5-ci2-userdocs` (`c73038c`, `c5f6d9e`, `83fe365`, `901bda6`, `a4f8f68`, `65965f1`, `379172c`), `p5-ci2-linux-pdf` (`24df1e3`, `73ba07b`, `df329f5`); Merges `b2b5246`, `18d1750`, `a4196e2`, `d4f3214`, `df1c790` | zweite CI-Fix-Runde mit R08/R09 und Nutzerdoku; drei Workflow-Läufe wegen abgebrochener Agenten (4.7.14) |
| 27.10. 07:34 – 08:25 | Zweig `p5-licence-texts-2` (`b1db39a`, `8a13999`, `4e05926`, `534733d`; Merge `9d8afcb`) | D-17 Lizenztexte der acht G1-Lücken; `known_missing.toml` leer (4.7.15) |
| 27.10. 06:51 – 09:52 | Zweig `p5-docs` (`3ba5665`), Merge `dcec9bd`, Push 09:52 | Doku auf dem Stand `181654e`; CI-Läufe 40476578603 (`ci`) und 40476578452 (`offline`) ganz grün (4.7.16) |
| 27.10. bis 16:19 | – | volle Suite auf `dcec9bd` (bis 13:59) und G1-Lauf (134 min, bis 16:19) [R: Dateizeiten und Dauer in `.local/logs`]; G1-Befund an der Konsole (4.7.17) |
| 27.10. 19:01 – 28.10. 01:36 | Zweig `p5-g1-console` (`36b0924`, `17178a5`, `acfbe02`, `ff9b88c`, `d478250`, `ac155be`, `01e0676`, `6786f4e`, `178818c`), Merge `18da12f`, Push 01:36 | Behebung des G1-Befunds, A-89 (4.7.17); CI-Läufe 40609866806 (`ci`, alle sechs Testjobs rot) und 40609866836 (`offline`, grün) (4.7.18) |
| 28.10. bis 04:08 | – | G1-Lauf auf `18da12f`: 6 von 6 Datensätzen bestanden, alle Kriterien erfüllt, 151 min (4.7.20) [R: Dateizeit und Dauer in `.local/logs/g1_18da12f.log`] |
| 28.10. 04:19 – 12:20 | Zweige `p5-ci3-posix` (`919bd11`, `3d212b5`, `223206b`, `5aa8749`, `9b9a98b`, `1ebe89b`, `7f5b3b0`), `p5-ci3-win311` (`9b355bd`, `aa03735`, `a25fc54`, `2c82a5f`, `25ead0d`, `95f6c50`), `p5-ci3-docs` (`29ff4af`, `d269cb9`, `17e0d3f`, `dd9ab93`, `341beb1`); Merges `ce87432`, `f3fe478`, `1dd0eac` | dritte CI-Fix-Runde: die roten Testjobs von `18da12f`, Release-Gate (4.7.18) |
| 28.10. 12:20 – 12:29 | `2a49a0c`, `27c3e90`, Push 12:29 | Testzahlen und Abdeckung grüner Testjobs als Notice-Annotationen; CI-Läufe 40680346160 (`ci`) und 40680346176 (`offline`) ganz grün (4.7.19) |
| 28.10. | Zweig `p5-final-docs` | Schlussfassung der Doku auf `27c3e90`; lokal nur die betroffenen Tests unter Python 3.12 und 3.11, keine lokale volle Suite; G1-Lauf auf `27c3e90`: 6 von 6 Datensätzen in 5 Formaten bestanden, alle Kriterien erfüllt, 0 Probleme, V-01 erfüllt, V-06 ja (149 min 28 s; `.local/p5/ci3/g1_summary_27c3e90.md`) (4.7.20) |

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
  & $PY tools\notices.py --download --check                         # erwartet: "up to date", Exit 0
  & $PY tools\notices.py --wheelhouse .local\notices-wheels --check # dasselbe offline aus dem Cache
  & $PY tools\notices.py --sources <Ordner mit den D-17-Downloads>  # optional: Quellen der Auszüge, Exit 0
  ```
  Seit D-17 ist `license-gate/known_missing.toml` leer; jeder neue Eintrag ließe `--check` mit Exit 1 enden
  („incomplete: …“). Bis D-17 endete `--check` hier gewollt mit Exit 1 (beim Bau sechs, auf `181654e` acht Lücken
  [G, 181654e]). Die Quellen der Auszüge (`source_size`, `source_sha256`) liegen nicht im Repository; `--sources`
  prüft sie gegen eine lokale Kopie. Ohne `--wheelhouse` und ohne `--download` endet `--check` mit Exit 2 („files
  missing“), weil der Cache nur mit `--download` gelesen wird [D]. Datei seit D-17 1 850 317 B [G] (auf `181654e`
  1 664 921 B [G, 181654e], beim Bau 1 398 869 B); „129 wheels, 4 bundle parts“ [D]. **Neu erzeugen nach jeder
  Änderung** an `uv.lock`, `license-gate/components.toml`, `known_missing.toml`, `licence_texts.toml`, einem
  `third_party/*/manifest.toml` oder `packaging/bundle_lock.json`:
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
  ds004148-1.0.1 psg-ipa-1.0.0`): Exit 0; psg-ipa ergibt 556 gesuchte Rohnamen, keiner gefunden [D]. Auf
  `55335ca`/`181654e` ist kein voller G1-Lauf protokolliert [NV]; bei einem Lauf traten ein `MemoryError` (autoreject
  auf ds002778) und ein `read.failed` auf, beides aus dem Arbeitsspeicher des Rechners: auf einem Rechner mit genug
  freiem RAM laufen lassen oder je Datensatz einzeln. Der volle Lauf auf `dcec9bd` ergab 5/6 und den Befund an der
  Konsole (4.7.17); auf `18da12f` „G1: 6/6 data sets passed, formats BDF, BrainVision, EDF, EEGLAB, FIF; minimum
  met; all criteria of this run met“, Exit 0, 151 min (4.7.20); auf dem Endstand `27c3e90`: 6 von 6 Datensätzen in 5 Formaten bestanden, alle Kriterien erfüllt, 0 Probleme, V-01 erfüllt, V-06 ja (149 min 28 s; `.local/p5/ci3/g1_summary_27c3e90.md`).

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
`fa96a58115dc6547e385c1b01344e3cd84a1719abaf34ef8c36b2f3b9a760d1f`). Nicht versioniert. Die Fix-Runden und die Behebung des
G1-Befunds haben zh-Texte geändert und ergänzt; das Paket nach dem letzten G1-Lauf neu erzeugen (die Beispiel-PDFs
kommen aus dessen Lauf 1), mit `--g1` auf diesen Lauf. Neu oder geändert gegenüber dem ersten Paket (`6a4f737`) [G:
Vergleich von `report/i18n/zh.yaml`]: `report.text.severity_heading`, `severity_heading_info`,
`severity_heading_none` (R05), `errors.pdf.install.command_windows` (neu) und `errors.pdf.install.docs` (geändert;
R07, R28), `errors.pdf.work_path_too_long`, `errors.pdf.temp_hint`, `errors.pdf.temp_unusable`,
`errors.pdf.temp_unusable_hint` (4.7.6), `cli.check.recomputed` (A-89); dazu die zh-Sätze in `docs/zh/installation.md`,
`privacy.md`, `limitations.md`, `license.md`, `configuration.md`, `report.md` und in `packaging/install.ps1`,
`install.sh`, `README.bundle.txt`, `release-notes.md`, `gitee-release.md`.

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
`docs/en/privacy.md`]; behoben in `p5-ci2-userdocs` (R09 `c73038c`, R08 `c5f6d9e`; 4.7.14).

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
  mit einer Warnung des Netzwerkdiensts (`sqlite_persistent_shared_dictionary_store`) [G, CI 55335ca] – behoben in
  der zweiten Fix-Runde (`88b15a4`, 4.7.14).

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
  `known_missing`-Eintrag oder abweichender Theme-Version; ohne Prüfung der installierten Version Exit 2. Bis D-17
  meldete jeder Bau „licence pending (blocks the release, STOPP G1): …“ für focus-visible und material-design-color
  (`cce23d2`, `c8c3f6e`); seit ihre Texte abgelegt sind (D-17), entfällt die Zeile. Gebaute Seite danach: 33 HTML-Seiten plus Skripte, Stile, 2 woff-Teilmengen, 6 Schemas, Suchindex,
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
der CI deshalb nicht gelaufen [NV]. Ergebnis nach der zweiten Fix-Runde: auf `dcec9bd` alle Jobs beider Workflows
grün, Abdeckungs-Gates eingeschlossen (4.7.16) [G, CI dcec9bd].

D-15 verlangt die Bündel-Tests bei jedem Push auf `dev` und `main`: Seit Review R10 läuft der Workflow `offline` bei
jedem Push auf `dev` und `main` sowie per Dispatch oder Aufruf aus `release.yml`; ein neuerer Push auf denselben Zweig
bricht den älteren Lauf ab, ein Release-Lauf (Tag-Ref) wird nie abgebrochen [G: `on:`- und `concurrency:`-Block,
`tests/packaging/test_workflows.py`]. `ci.yml` hat weiterhin keinen Bündel-Job. Auf `dev` lief `offline` auf `55335ca`
ganz grün [G, CI 55335ca]; gepusht wurden `42e129d`, `c3be509` und `55335ca` [G: Reflog von `origin/dev`].

#### 4.7.13 Stand auf `181654e` (vor der zweiten CI-Fix-Runde)

Geprüft [G, 181654e]:
- `uv lock --check --offline` → 103 Pakete; `ruff check .` „All checks passed!“; `ruff format --check .` „224 files
  already formatted“.
- `gen_fixtures`, `gen_schemas`, `gen_montage_names`, `gen_docs`, `calibrate` jeweils `--check` grün;
  `linux_pdf_packages.py --check` grün; `install_pdf_browser.py --check` „complete (revision 1243, 290 files)“;
  `check_matrix_coverage.py` 166/166; `check_commit_ids.py` 146 Commits, 0 Probleme.
- `notices.py --wheelhouse <.local/notices-wheels> --check` → auf `181654e` „up to date“, wegen der acht Lücken in
  `known_missing.toml` Exit 1; seit D-17 (`9d8afcb`) „up to date“ ohne „incomplete“, Exit 0 [G].
- Testsammlung: 3749 Tests, Standardlauf 3622, abgewählt 127 (114 `corpus`, 9 `perf`, 4 `bundle`); Marker `pdf` 98,
  `browser` 2.

Lokale volle Suiten [D]: Fix-Runde report `c9a536a` 3502 bestanden / 23 übersprungen; linux `191a62a` 3510 / 25 (mit
`PYTHONWARNDEFAULTENCODING=1`); bundle `d42bbf4` 3498 / 23; gemergter Stand `55335ca` 3597 bestanden, 24
übersprungen, 127 abgewählt, 1 fehlgeschlagen (behoben in `181654e`). Nach der zweiten Fix-Runde und dem G1-Befund:
4.7.17 und 4.7.20.

Auf `181654e` noch offen waren: CI-Testjobs grün auf Linux und Windows; volle Suite unter 3.11/3.12/3.13 auf dem
Endstand; Abdeckungs-Gate auf dem Endstand; Korpustests (`-m corpus`, 114) und voller G1-Lauf auf dem Endstand;
`bundle.py sizes`; zh-Prüfpaket neu erzeugen; R08 und R09 (4.7.10); überholte Plattformangaben der Nutzerdoku
(`installation.md`, `limitations.md`, `privacy.md` en/zh: Linux, PowerShell 7 und strace „bis zum ersten CI-Lauf nicht
verifiziert“, Firewall-Test „nicht verifiziert“, obwohl `offline` auf `55335ca` sie grün prüfte) [G, 181654e];
Phasenbericht an den Projektverantwortlichen. Erledigt sind seitdem die CI-Testjobs mit Abdeckungs-Gates (4.7.16),
R08/R09 und die Plattformangaben (4.7.14) und ein voller G1-Lauf (auf `dcec9bd`, 4.7.17); was bleibt, steht in 4.7.20.

#### 4.7.14 Zweite CI-Fix-Runde (Zweige `p5-ci2-*`, 27.10.2026)

Alle Zweige gingen von `181654e` aus, je mit eigenem Worktree und `uv sync --locked --no-build`; je Fehler aus 4.7.12
ein Bereich, dazu die Nutzerdoku (R08, R09, überholte Plattformangaben). Ablauf je Bereich wie in 4.7.11: Bau →
unabhängige Verifikation → Reparatur, Prüfbefehle wie dort, keine volle Suite im Zweig (die läuft nach dem Merge) [D].

**Drei Workflow-Läufe statt einem** (1.6 Punkt 26) [D]:
1. Lauf 1: chrome-log vollständig (Bau `88b15a4`, Verifikation, Reparatur `c5c6ff6`); win-runner Bau und Verifikation
   (die Reparatur brach mit `ECONNRESET` ab); linux-p2 Bau (die Verifikation brach ab); linux-pdf brach im Bau ab, mit
   Teil A gestagt und Teil B im Stash.
2. Lauf 2: Verifikation von linux-p2; win-runner nur Kommentare (`5c40d24`; ein unfertiger Rest des abgebrochenen
   Agenten wurde verworfen und als Diff im Scratchpad gesichert); userdocs Bau und Verifikation; die URL-Liste der acht
   Lizenzlücken (Grundlage von D-17, 4.7.15); eine Gegenprüfung der Projektdokumente. linux-pdf hing 6455 s ohne
   Fortschritt und brach beim Neustart wie die Reparaturen von linux-p2 und userdocs mit `403` ab; die Reparatur von
   userdocs hatte vorher noch `a4f8f68` und `65965f1` committet, die von linux-p2 unfertige Arbeit im Worktree
   hinterlassen [R: Commit-Zeiten und Befund von Lauf 3].
3. Lauf 3: linux-pdf fertig (Teil A als `24df1e3`, Teil B als `73ba07b`, der Stash-Eintrag per SHA angewendet),
   Verifikation, Reparatur `df329f5`; Reparaturen von linux-p2 (`96e5986`, `c5f41c4`, unfertige Arbeit des
   abgebrochenen Agenten geprüft und übernommen) und userdocs (`379172c`).

Merge am 27.10. 08:24–08:32 in der Reihenfolge chrome-log (`b2b5246`), win-runner (`18d1750`), linux-p2 (`a4196e2`),
userdocs (`d4f3214`), Lizenztexte (`9d8afcb`, 4.7.15), linux-pdf (`df1c790`), alle ohne Konflikt; Konflikte hatte nur
der Doku-Merge `dcec9bd` (ENTSCHEIDUNGEN, NACHBAU) [G: `git show --remerge-diff`]. Vorab prüfte `git merge-tree` jeden
Zweig gegen die anderen (3.5) [D].

**chrome-log** (`test_pdf_tests_pass_with_a_long_basetemp`, alle Windows-Testjobs seit `c3be509`; TECH-07, NG-N03):
- Ursache (Chromium-Quelltext am Tag 153.0.8010.12): `headless/lib/headless_content_main_delegate.cc` richtet unter
  Windows für Kindprozesse kein Logging ein, sie behalten `LOG_TO_FILE` und schreiben ab INFO in `debug.log` neben der
  exe; kein Schalter und keine Variable ändern das. Der Netzwerkdienst ist ein eigener Kindprozess; schließt der Browser
  kurz nach dem Start, meldet der Speicher für gemeinsame Wörterbücher genau die Zeile aus der CI-Annotation.
  `_ChildLog` entfernte die Datei, übrig blieb die geänderte mtime des Ordners.
- Behebung `88b15a4`: unter Windows `--enable-features=CDPScreenshotNewSurface,NetworkServiceInProcess2`
  (`PLAYWRIGHT_FEATURES` + `IN_PROCESS_NETWORK` in `kernel/pdf.py`), der Wert wiederholt Playwrights eigenes, weil
  Chromium nur den letzten behält; kein `--disable-features`; Linux unverändert (1.6 Punkt 11).
- Nachweis [D]: vorher schrieb ein Start/Schluss ohne Druck auf einer frischen Kopie der Shell die CI-Zeile in 6 von 6
  und 20 von 20 Läufen, danach weder in 10 solchen Läufen noch in 5 Druckläufen; kein Netzwerkdienst-Prozess mehr.
  Neuer Test `test_a_browser_closed_right_after_its_start_leaves_the_browser_folder_untouched`; ein Unit-Test liest
  `chromiumSwitches` aus dem gepinnten Treiber und scheitert, wenn ein Playwright-Update die Liste ändert. Der CI-Test
  selbst war lokal auch vorher grün (Zeitabhängigkeit nur auf dem Runner); grün auf `dcec9bd` [G, CI dcec9bd].
- Falle: Den Netzwerkdienst als Ursache zeigte erst eine Prozessliste während Start und Schluss
  (`--utility-sub-type=network.mojom.NetworkService`); `--log-file` wirkt in der Headless Shell nicht.

**win-runner** (drei Tests in `test_install_ps1.py`, ein Such-Timeout in `test_docs_browser.py`; UF-08, NG-N05, V-01):
- Ursache Installer (1.6 Punkt 20): Die Testordner lagen unter dem 8.3-`TEMP` des Runners, der Installer gab das
  Präfix nach `GetFullPath` lang aus, `Show` verbarg nur die eigene und die ganz kurze Schreibweise. So kam
  `C:\Users\runneradmin\…` in die Ausgabe von uv – ein echter A-51-Fehler für jeden Nutzer mit 8.3-Variablen. Die
  Längenprüfung zählte im Test die kurze, im Installer die lange Schreibweise, und Windows PowerShell 5.1 erweitert
  8.3-Namen eines nur teilweise vorhandenen Pfads je nach Namen nicht durchgehend (.NET 10 in PowerShell 7 schon).
- Behebung `5d7af87`: `Get-LongPath` in `packaging/install.ps1` (`GetFullPath` des tiefsten vorhandenen Ordners plus
  Rest); `Show` verbirgt `LOCALAPPDATA` und `USERPROFILE` in eigener, langer und kurzer Schreibweise; die 250-Zeichen-
  Grenze zählt den Pfad, den die Dateien bekommen. Tests mit Parametern „as created“ und „8.3“ (übersprungen mit Grund
  auf einem Datenträger ohne 8.3-Namen), Varianten für pwsh nur in der CI.
- Ursache Suche: mkdocs-material 9.7.7 liest das Suchfeld nur bei keyup, focus oder der ersten Bereit-Meldung des
  Workers, nie bei input; `insert_text` sendet nur input. War der Worker vor dem Text bereit, kam die Anfrage nie an.
  Behebung `1d07ad9`: warten, bis die Ergebniszeile den übersetzten Platzhalter zeigt, dann Text einfügen und `End`
  drücken. Nachweis [D]: Rennprobe je 5 Versuche, alter Ablauf nach Bereit 0/5, neuer 5/5.
- Falle: Der Verifizierer fand, dass die Variante „8.3-powershell-5.1“ allein den fehlenden `Get-LongPath` nicht sicher
  erkennt (abhängig von den Ordnernamen); direkter Regressionstest ist `test_get_long_path_expands_whatever_exists`
  (Kommentare richtiggestellt in `5c40d24`).

**linux-p2** (`test_review_p2_formats.py`, zwei Fälle in `test_review_p2_convert.py`; NG-F02, CLI-02, NG-N04):
- Rückwärtsstrich: MNE setzt den Datendateinamen mit `os.path.join` zusammen; nur unter Windows trennt `\` Ordner. Das
  Produkt war richtig (`kernel.safety.check_relative` behandelt `\` überall als Trenner); der Test gilt jetzt nur unter
  Windows (mit Grund), ein POSIX-Gegenstück prüft das Linux-Verhalten (`ad902d8`, `96e5986`).
- Locale (1.6 Punkt 21): MNE 1.13.2 `_get_hdr_info` (`brainvision.py:727`) öffnet die Markerdatei im Textmodus ohne
  Kodierung; unter Linux scheiterte ein cp1252-Marker mit `UnicodeDecodeError`, die Aufnahme wurde `read.failed`. Das
  traf auch Windows-Systeme mit anderer Codepage (UTF-8- oder GBK-Marker auf westlichem, Latin-1 auf chinesischem
  Windows). Behebung `bf81d92`: jeder MNE-Aufruf für BrainVision über `io.brainvision.mne_read_raw_brainvision`;
  `mne_reading_without_locale` gibt diesem einen Lesen Latin-1 (`MNE_MARKER_DATE_CODEC`); ein AST-Test erzwingt den Weg.
  `d8f8be9`: `convert._write` hält den Kontext auch, während MNE-BIDS schreibt (MNE-BIDS 0.20 `write.py:2210` liest eine
  kopierte Aufnahme erneut mit MNE).
- Codec (1.6 Punkt 22): MNE-BIDS kopiert Kopf und Marker mit dem Codepage-Wert als Codec-Namen; `ANSI` gibt es nur unter
  Windows. Unter Linux wurde die Aufnahme deshalb aus den geladenen Daten neu geschrieben (float32, `Codepage=UTF-8`),
  unter Windows kopiert. Behebung `18bb4ef`: `convert._copy_codec` macht aus `ANSI` (jede Schreibweise) Latin-1.
- Reparatur `c5f41c4`: `io.base.ModulePatch` (Sperre und Zähler der Halter) für beide prozessweiten Ersetzungen, damit
  sie auch bei Threads halten, die in anderer Reihenfolge austreten (vorher latent, NeuroGrid liest heute nicht aus
  mehreren Threads über MNE).
- Nachweis lokal nur simuliert [D]: `PYTHONUTF8=1` und die conftest-Hilfen gaben ohne die Behebung genau die
  CI-Meldungen (`(0, 0, 1) == (1, 0, 0)`), danach byte-gleiche Ausgaben unter drei Locales; unter Linux grün auf
  `dcec9bd` [G, CI dcec9bd].
- Falle: Erst das Abschalten je einer Behebung (pytest-Plugins im Scratchpad) zeigte, dass Ursache B (Codec) hinter
  Ursache A (Locale) verdeckt lag; nach A allein scheiterte der alte Test weiter.

**linux-pdf** (`test_rule_ids_do_not_break_inside_in_the_pdf`, `test_qa_gate_negative_controls`; REP-00, NG-F13,
TECH-07):
- Regel-IDs: Die Zellen waren schon `nowrap`, die Teilung entstand erst beim Auslesen. Die Headless Shell setzt
  `--font-render-hinting` standardmäßig auf `full`, das nur der Linux-Renderer anwendet; dann stehen die Glyphen auf
  ganzen Pixeln, die `/W`-Breiten des PDF bleiben ungehintet, und pypdf liest Leerzeichen in die Lücken. Behebung
  `24df1e3`: `TEXT_LAYOUT_FLAG = "--font-render-hinting=none"` als letzter Eintrag von `CHROMIUM_FLAGS` (unter Windows
  byte-gleiches PDF); dazu steht jede Regel-ID im Fließtext in einem `<span class=nowrap>` und kommt über
  `render.RULE_SLOT` in übersetzte Sätze (auf jeder Plattform brach `CORE-M05-02` vorher nach dem Bindestrich).
  Nachstellen unter Windows: `WIDER_GLYPHS` (zusätzlicher Buchstabenabstand im Druck; ab ≈ 1,2 px teilt pypdf
  `BIDS-STO-001`). Unter Linux prüft `test_font_render_hinting_is_read_by_the_shell`, dass `full` die IDs weiter teilt
  (Gegenprobe der Ursache).
- QA-Gate: Hat keine installierte Schrift ein Zeichen, zeichnet Blink das `.notdef`-Kästchen der Berichtsschrift; das PDF
  bettet dann nur Berichtsschriften ein und sein Text enthält nichts von dem Zeichen, also bestanden Schrift- und
  Radikalprüfung ein PDF mit Kästchen (unter Linux fehlt eine Schrift für U+2F63, unter Windows zeichnete eine
  Systemschrift es). Behebung `73ba07b`: `_MissingGlyphs` meldet Glyphe 0 als `glyph_missing`; ein Type0-Font ohne
  Identity-CMap scheitert an `font_not_cid_truetype`; die Gegenproben brauchen keine Systemschrift mehr (eigene
  Teilmengen mit Radikal-Alias und umbenanntem Schnitt, U+0378 für das Kästchen). Gate auf einem 19-Seiten-Bericht
  ≈ 10 % langsamer, innerhalb der Reserve aus A-88 [D].
- Reparatur `df329f5`: Ein Docstring in `render.py` zitierte den zh-Querverweis auf Chinesisch; damit scheiterte
  `test_zh_review_package.py::test_every_file_with_chinese_text_is_in_the_package` in jedem Testjob. Das Beispiel steht
  jetzt auf Englisch (Falle: kein chinesischer Text außerhalb der Quellen des zh-Pakets).

**userdocs** (R08, R09, überholte Plattformangaben; TECH-06, NG-N05, V-06):
- R09 `c73038c`: `configuration.md` (en/zh) sagt wie der Code (`pipeline._dataset_info`), dass `name`/`license` aus
  `neurogrid.toml` gewinnen und `id`/`version`/`source` nur aus dem Abschnitt kommen.
- R08 `c5f6d9e`: `privacy.md`, `report.md`, `configuration.md` nennen, dass `document`, `reviewer`, `comment`,
  `justification` aus `evidence.yaml` im Klartext in `results.json` und Abschnitt 5 stehen, nie auf der Konsole.
- Plattformen `83fe365`, `a4f8f68`, `65965f1`: Plattformtabelle und Nachweistabelle folgen `offline.yml`; die
  Reinräume sind je Plattform beschrieben; `README.bundle.txt` und `release-notes.md` tragen denselben Absatz wie
  `limitations.md`. Die Zellen „test suite not yet verified“ (en/zh, `SUITE_PENDING` in `tests/docs/test_docs_sync.py`)
  waren von Hand umzustellen, wenn die Testjobs grün sind; umgestellt mit `17e0d3f` und `341beb1` (4.7.18).
- Firewall `901bda6`, `379172c`: Der Prüfvorschlag der Datenschutzseite ist die Regel des Windows-Reinraums (jede `.exe`
  unter Installation und `pdf-browser`, dazu `sys._base_executable` für venv-Installationen); ein Test prüft
  Aussagen über die Prozessaufteilung gegen `launch_arguments(windows=True)`.
- Falle: `privacy.md` von userdocs war nur zusammen mit chrome-log wahr; die Reparatur machte den Satz unabhängig davon
  und den Test laut statt still übersprungen.

**Fallen der Runde** (zusätzlich zu 1.6 Punkt 20–26): Der gemeinsame Stash-Stapel (1.6 Punkt 24) trug Einträge zweier
Zweige (`7f04f52…` mit Teil B von linux-pdf, `7864c47` mit Resten von userdocs und chrome-log); die Agenten lasen bzw.
wendeten sie nur per SHA an und ließen sie für den Lead stehen [D]; heute ist der Stapel leer [G]. Jede
Linux-Behebung war lokal nur simuliert; jede Testmeldung nennt deshalb die gemessene Ursache (Locale, Codec, `os.sep`,
Glyphenlücke, eingebettete Schnitte), damit die nächste Annotation sie zeigt. Bestätigt hat sie erst der grüne
Linux-Testjob auf `dcec9bd` (4.7.16).

#### 4.7.15 Lizenztexte nach D-17 (Zweig `p5-licence-texts-2`)

- **Liste:** In der zweiten CI-Fix-Runde entstand `.local/p5/licence_url_list.md` (privat): je Eintrag von
  `known_missing.toml` die Herkunft der Version und die URLs der Texte, 70 Zeilen, jede URL per HEAD geprüft (HTTP 200;
  nur ein GitLab-Server antwortete mit 429); nichts geladen [D]. Der Projektverantwortliche gab sie mit D-17 frei
  (Wahlen 1–5 in ENTSCHEIDUNGEN).
- **Download und Ablage** (`b1db39a`, `8a13999`): 70 Downloads (68 eindeutige URLs der Liste, das npm-Tarball von
  `@jspm/core` 2.1.0 mit 1 521 183 B als größte Datei, `Modules/_hacl/Hacl_Hash_SHA2.c` von CPython v3.12.15), zusammen
  ≈ 1,85 MB; drei Abrufe von raw.githubusercontent.com brachen mit WinError 10054 ab und gelangen beim zweiten Versuch.
  Nicht geladen: die Zeile „PBS full-Archive“ (98 MB, nicht empfohlen). 70 Texte abgelegt [G: Ordner und `git ls-files`]:
  `license-gate/third_party/bids-validator-3.0.2/npm/<paket>@<version>/` (45: acht hed-validator-Pakete, Unicode
  License V3 für unicode-name, Brumme-Auszug und argon2-Text für hash-wasm, `@jspm/core` mit seiner LICENSE und 33
  `LICENSE.<paket>@<version>.txt`), `h5py-3.16.0/libaec@1.1.4/` (1, neues Manifest), `mkdocs-material-9.7.7/npm/`
  (`focus-visible@5.2.1`, `material-design-color@2.3.2`; 3), `python-build-standalone-3.12.15+20261009/` (21:
  `python-build-standalone@20261009/` mit 16 `LICENSE.*.txt`, `itcl@4.3.8`, `thread@3.0.6`, `cpython@3.12.15` mit drei
  Auszügen; neues Manifest). Unicode-3.0 und W3C-20150513 stehen zusätzlich in `license-gate/licence_texts.toml`. Jeder
  Text mit `url`, `size`, `sha256`, `retrieved = 2026-10-27`, `decision = D-17`. Die Lade- und Ablageskripte lagen nur
  im Scratchpad [NV]; die Manifeste halten jede URL, Größe und SHA-256 fest.
- **CRLF:** `npm/@jspm/core@2.1.0/LICENSE` ist die byte-gleiche Datei aus dem Tarball (42 179 B, CRLF) und in
  `.gitattributes` als `-text` markiert; sonst machte `* text=auto eol=lf` daraus LF und der SHA-256 bräche.
  `git ls-files --eol` zeigt `i/crlf w/crlf attr/-text` [G]; ein Test verlangt, dass es die einzige CRLF-Datei ist.
- **Neue Prüfungen in `tools/notices.py`** [G: Quelltext]: `BUNDLED_ALLOWED` um Unicode-3.0, Unlicense, W3C-20150513 und
  `LicenseRef-Brumme-Disclaimer`; `LIBRARY_ALLOWED` (zusätzlich TCL, X11, bzip2-1.0.6, `LicenseRef-itcl`) für die in
  python-build-standalone gebauten Bibliotheken; ein Manifest je gebündeltem Interpreter (`--check` scheitert ohne);
  `check_kept_texts` (jeder Ordner hält genau die Texte seines Manifests); `TEXT_KINDS` (Reparatur `4e05926`: eine Art
  `document excerpt` mit `source_size`/`source_sha256` für alle Auszüge). Abschnitt 5 der Notices lautet „None: every
  licence text is in this file.“
- **Befehle:**
  ```powershell
  $PY = ".\.venv\Scripts\python.exe"
  & $PY tools\notices.py --wheelhouse .local\notices-wheels --out THIRD_PARTY_NOTICES.txt
  & $PY tools\notices.py --wheelhouse .local\notices-wheels --check   # "THIRD_PARTY_NOTICES.txt up to date", Exit 0 [G, 18da12f]
  & $PY -I tools\notices.py --sources <Ordner mit den D-17-Downloads> # Quellen der 4 Auszüge, Exit 0 [D]
  & $PY tools\licenses.py --components --wheelhouse .local\notices-wheels   # "components (129 wheels, 4 bundle parts, …): ok" [D]
  ```
  `THIRD_PARTY_NOTICES.txt` 1 850 317 B [G, 18da12f]. Vor D-17 endete `--check` mit Exit 1 und acht Einträgen als
  „incomplete“ [D].
- **Verifikation** [D]: alle 70 Dateien erneut in einen leeren Ordner geladen (`python -I`, nichts ausgeführt), Größe und
  SHA-256 gleich; Auszüge von Hand gegen ihre Quellen verglichen.
- **Fallen:** Die Liste nannte „34 weitere Pakete“ in `@jspm/core`, ihre Tabelle 33 (fs-monkey im Generator doppelt
  gezählt); ein Agentenbericht nannte 74 statt 70 abgelegte Texte (Reparatur `534733d` korrigierte die Zahlen und
  bringt `test_rebuild_guide_states_the_current_licence_gaps`). Die Brumme-Seite ist dynamisch; nur Auszug und
  Seiten-Hash werden aufbewahrt. `--sources` braucht lokale Kopien der Quellen, die nicht im Repository liegen.

#### 4.7.16 CI-Stand auf `dcec9bd`

Gepusht am 27.10. 09:52; gelesen über die öffentliche Jobs-API (4.7.9) [G, CI dcec9bd; Liste in
`.local/ci_dcec9bd.txt`]:

| Workflow / Lauf | Job | Ergebnis |
|---|---|---|
| `offline`, 40476578452 | beide Offline-Bündel aus `uv.lock` (unsignierte Entwicklungsbündel), mit `pytest -m bundle` | grün |
| | PDF in `debian:12-slim` mit der dokumentierten Paketliste (`--network none`, strace) | grün |
| | glibc 2.27 mit Exit 2 abgelehnt (`ubuntu:18.04`, A-58) | grün |
| | Reinraum Windows (PowerShell 5.1 und pwsh, WFP-Audit, PDF) – erstmals mit `NetworkServiceInProcess2` | grün |
| | Reinräume `debian:12-slim`, `ubuntu:24.04`, `ubuntu:22.04` (`--network none`, ohne Python, uid 1000) | grün |
| | jeder v0.1-Befehl unter strace, `--network none` (Linux) | grün |
| `ci`, 40476578603 | Test ubuntu-24.04 × 3.11/3.12/3.13 (Lint, Typen, Tests mit Abdeckung, Abdeckungs-Gates, Determinismusprobe) | grün |
| | Test windows-latest × 3.11/3.12/3.13 (ebenso) | grün |
| | plattformübergreifender Vergleich (berichtet, nicht erzwungen) | grün |
| | Lizenz-Gate und Netz-Scan der Laufzeitpakete; Windows PowerShell 5.1; PowerShell 7; Anforderungs-IDs | grün |

Auf `dcec9bd` standen Testzahlen und Abdeckungswerte nur im Job-Log (Anmeldung nötig); Annotationen gab es nur bei
Fehlern, weil die Annotationsschritte nur bei `failure()` liefen [G: `ci.yml`, leere Annotationsliste]. Die
Abdeckungs-Gates bestanden dort, ihre Werte sind ohne Log nicht belegt [NV]; seit `2a49a0c` schreibt jeder grüne
Testjob Testzahlen und Abdeckung als Notice-Annotation (Werte auf `27c3e90` in 4.7.19). Die Testsuite läuft in der CI
nur auf ubuntu-24.04 und windows-latest; Debian 12 und Ubuntu 22.04 sehen nur die Reinräume. `dcec9bd` enthält die
Behebung des G1-Befunds noch nicht; ihr CI-Lauf auf `18da12f` war rot (4.7.18), grün ist erst `27c3e90` (4.7.19).

#### 4.7.17 G1-Lauf auf `dcec9bd` und Befund an der Konsole (A-89; Zweig `p5-g1-console`)

**Lauf** [G: `.local/p5/ci2/g1_summary_dcec9bd.md`, `.local/logs/g1_dcec9bd.log`]: `tools/acceptance_g1.py` wie in 4.7.8,
134 min, Exit 1: „G1: 5/6 data sets passed, formats BDF, BrainVision, EDF, FIF; minimum met; all criteria of this run
NOT met“. Beide Läufe je Datensatz byte-gleich, `--jobs 1` = `--jobs 4` auf ds004148, Korpus unverändert. ds004504-1.0.9
(EEGLAB) scheiterte nur an Lauf 1 von `check`: acht Probleme (stderr mit Laufwerkspfad, Traceback, Quellstelle,
Benutzerordner, Benutzername, keine übersetzte Meldung, kein UTF-8); `check` brauchte 935,6 s statt 299,4 s in Lauf 2.

**Warum G1 es fand und Tests und CI nicht:** Das G1-Werkzeug startet echte `neurogrid`-Prozesse mit `--jobs 4` auf
echten Daten und prüft jede Konsolenausgabe strikt (UTF-8, fester Satz, keine Pfade, keine Namen; A-51, NG-N05). Kein
Test verlangte eine stumme Konsole der Pool-Prozesse. Die volle Suite auf `dcec9bd` zeigte denselben Traceback
(`SpawnProcess-18`, WinError 6) nur im mitgeschnittenen stderr von
`test_quality_review_p3.py::test_one_recording_with_jobs_4_equals_jobs_1`, der an seiner Zeitgrenze scheiterte
(122,5 s > 120 s; Suite 4 h 07 min auf einem überlasteten Rechner) [G: `.local/logs/full_dcec9bd.log`]. Die CI war grün;
ob WMI-Abfragen auf den Runnern abbrechen, ist nicht gemessen [NV], und der G1-Lauf läuft in keinem Workflow auf `dev`
(`corpus.yml` nur `main`/Dispatch).

**Ursache** (CPython 3.12, nicht NeuroGrid und kein Rennen beim Herunterfahren) [D; Quelltext G]: `platform.uname()` bzw.
`platform.machine()` fragt unter 3.12 WMI über `_wmi.exec_query` (`PC/_wmimodule.cpp`). Die Funktion wartet 1000 ms auf
COM und 100 ms auf die Verbindung (gh-112278) und kehrt mit WAIT_TIMEOUT zurück, während ihr Thread weiterläuft; er
hält einen Zeiger auf `struct _query_data` im Stackrahmen der beendeten Funktion und schließt am Ende mit
`CloseHandle(data->writePipe)` den Wert, der dort inzwischen steht. Im Worker kommt der Aufruf über
`import scipy.signal` → array_api_compat → `numpy.testing` → `platform.machine()`. Auf dem Messrechner bricht jede
WMI-Abfrage ab (WinError 258 nach ≈ 0,3 s, auch ohne Last), und der späte Thread schloss immer den Handle-Wert 24; lag
dort das Semaphor der Aufrufwarteschlange, scheiterte das nächste `call_queue.get()` an `self._sem.release()` mit
WinError 6, `multiprocessing` schrieb `Process SpawnProcess-N:` und den Traceback auf die geerbte Konsole, der Pool brach
(`BrokenProcessPool`), und `compute_all` rechnete jede offene Aufnahme allein nach (daher 935,6 s). CPython 3.13 kopiert
die Struktur in den Thread; 3.12 bekommt nur Sicherheitskorrekturen.

**Interventionsmessungen** [D] (Handle-Monitor als `sitecustomize` auf `PYTHONPATH`: Typ jedes Warteschlangen-Handles im
1-ms-Takt über `NtQueryObject`, bei einer Änderung die Stacks aller Threads, dazu das Audit-Ereignis
`_wmi.exec_query`; `compute_all` auf der 19-Kanal-EDF `cap19` mit `workers=4`, 3 Pools je Lauf):

| Aufbau | Ergebnis |
|---|---|
| `dcec9bd` mit WMI, 9 Läufe | 7 mit totem Worker (10 Tode); 14 der 22 Worker mit dem Semaphor auf Wert 24 verloren es, jedes Mal in `platform.uname()` nach der abgebrochenen Abfrage; keiner der 39 mit anderem Wert |
| `dcec9bd` mit gesperrtem `_wmi`, 9 Läufe | 0 Tode, keine Schließung (23 Worker mit dem Semaphor auf 24) |
| Behebung, gleicher Monitor, 6 Läufe | 0 Tode (36 Worker, 10 mit dem Semaphor auf 24) |
| ohne NeuroGrid: frische spawn-Kinder, `platform.machine()`, 3 s warten | mit WMI 2 von 24 verloren Handle 24, mit `avoid_wmi()` 0 von 16; Nachprüfung: 3 von 40 gegen 0 von 40, Handle-Schnappschuss 2 von 32 gegen 0 von 20 |
| NeuroGrid-Ebene ohne Monitor, `dcec9bd` | 1 von 10 Läufen mit genau dem G1-Traceback (849 B, kein UTF-8); 0 von 3 echten `check`-Läufen auf ds004504 |

Herunterfahren oder Abbruch des Pools scheiden aus: Der Worker scheiterte nach erfolgreichem `_recv_bytes()` an
`_sem.release()`, und Handles gehören der Handle-Tabelle des eigenen Prozesses.

**Behebung in zwei Schichten plus Ursache** (Commits in 4.7.1; A-89 in ENTSCHEIDUNGEN) [G: Quelltext]:
- Ursache: `kernel/processes.py` `avoid_wmi()` ersetzt `platform._wmi_query` durch eine Funktion, die `OSError` wirft;
  `platform` antwortet aus `ver` und der Umgebung wie vor 3.12 (`platform.machine()` weiter `AMD64`). Aufgerufen in
  `cli.main()` direkt nach `netguard.install()`, in `quality.workers.worker_start()` (damit auch in
  `loky_worker_start()`) und in der Testsitzung (`tests/conftest.py`).
- Schicht 1, Start: Jeder Pool entsteht über `quality._pool(size)` mit `mp_context=processes.pool_context()`. Windows:
  `NullStdioPopen` wie `popen_spawn_win32.Popen` (CPython 3.11–3.13) mit STARTUPINFO, stdin/stdout/stderr = ein
  vererbbarer NUL-Handle als einziger vererbter Handle, `STARTF_FORCEOFFFEEDBACK` wo definiert (`d478250`), venv ohne
  private Konstante gefunden (`ff9b88c`). POSIX (fork, spawn, forkserver): Deskriptoren 0–2 nur während des Starts auf
  `/dev/null`; bei spawn/forkserver startet `pool_context()` in diesem Fenster auch den resource tracker (`01e0676`).
- Schicht 2, Initializer: `to_null_device()` als erster Schritt von `worker_start()` legt 0–2 und
  `sys.stdin/stdout/stderr` erneut auf das Nullgerät; loky-Prozesse und ihr tracker erben es.
- Dazu: `driver_environment()` legt `sys.stderr` während des Starts des Playwright-Treibers auf das Nullgerät
  (`17178a5`); ein toter Pool- oder loky-Prozess erscheint einmal als übersetzte Zeile `cli.check.recomputed` auf stdout
  (`6786f4e`); `results.json` bleibt unberührt.
- Nachweis [D]: `tests/unit/test_processes.py` (jede Startmethode, jede Schicht allein, Gegenprobe ohne beide);
  `tests/integration/test_worker_console.py` (Semaphor deterministisch geschlossen; kein Prozess fragt WMI; echter
  `check --jobs 2` mit störendem `sitecustomize`); alle drei scheitern auf `dcec9bd`. Echte Läufe auf ds004504 mit der
  Behebung: stderr 0 B, `results.json` SHA-256 `0a183ea9…` byte-gleich zu `dcec9bd`; `acceptance_g1.py --datasets
  ds004504-1.0.9`: Datensatz bestanden, Berichte byte-gleich zum G1-Lauf auf `dcec9bd` (Exit 1 nur, weil das Minimum
  von drei Datensätzen mit einem Datensatz nicht erreichbar ist). Unter Linux prüfte erst die CI auf `18da12f` die
  POSIX-Zweige; sie war dort rot, ebenso die Konsolentests unter Windows mit Python 3.11 (dritte CI-Fix-Runde, 4.7.18).
- Grenzen (A-89; Abschnitt 8): `avoid_wmi` ersetzt eine private CPython-Funktion; direktes Schreiben auf das
  Konsolengerät bleibt ein Restrisiko; Warnungen der Worker entfallen bei `--jobs` > 1.

#### 4.7.18 Dritte CI-Fix-Runde (Zweige `p5-ci3-*`, 28.10.2026)

**CI auf `18da12f`** (Push 28.10. 01:36) [G, CI 18da12f; `.local/ci_18da12f.txt`, `.local/p5/ci3/annotations_18da12f.json`]:

| Workflow / Lauf | Job | Ergebnis |
|---|---|---|
| `offline`, 40609866836 | alle neun Jobs (beide Bündel, strace, PDF in `debian:12-slim`, glibc-Ablehnung, Reinräume Windows unter PowerShell 5.1 und pwsh, `debian:12-slim`, `ubuntu:22.04`, `ubuntu:24.04`) | grün |
| `ci`, 40609866806 | Lizenz-Gate und Netz-Scan; Windows PowerShell 5.1; PowerShell 7; Anforderungs-IDs | grün |
| | Test windows-latest × 3.12 und × 3.13 | rot: je 1 fehlgeschlagen, 3668 bestanden, 14 übersprungen (3683 Tests) |
| | Test windows-latest × 3.11 | rot: 3 fehlgeschlagen, 3665 bestanden, 15 übersprungen (3683 Tests) |
| | Test ubuntu-24.04 × 3.11/3.12/3.13 | rot: je 5 fehlgeschlagen, 3587 bestanden, 96 übersprungen (3688 Tests) |
| | plattformübergreifender Vergleich (berichtet, nicht erzwungen) | übersprungen (hängt an den Testjobs) |

Fehlgeschlagen (Annotationen; Titel = Knoten-ID, Text = erste Zeile):
- alle sechs Testjobs: `tests/packaging/test_env_example.py::test_example_lists_every_variable_of_code_and_workflows`
  („list these in .env.example or review them into PROVIDED/THIRD_PARTY/INTERNAL“);
- ubuntu-24.04 (alle drei Versionen): `test_processes.py::test_the_resource_tracker_of_a_pool_has_no_console[spawn]` und
  `[forkserver]` („assert not True“), `test_pool_processes_start_on_the_null_device[fork]` (ein Traceback statt
  `('', '')`), `test_worker_console.py::test_check_with_jobs_keeps_the_console_clean_when_workers_write_and_die`
  („AssertionError: 1“);
- windows-latest × 3.11: derselbe CLI-Test („AssertionError: 2“) und
  `test_a_worker_whose_call_queue_semaphore_is_closed_leaves_the_console_clean` (`['Traceback', 'File "', 'queues.py']`).

**Aufbau der Runde** [D: `.local/p5/ci3/facts_for_docs.md`, `workflow_result.json`]: drei Bereiche, je von `18da12f`
aus in eigenem Worktree, Ablauf wie in 4.7.11 (Bau → unabhängige Verifikation → Reparatur): `posix` (die Linux-Fehler),
`win311` (die Fehler unter Windows mit Python 3.11), `docs` (`test_env_example`, Nutzerdoku, Release-Gate). Keine volle
Suite im Zweig. Linux lief lokal nie (D-09); jeder Linux-Beleg kam erst aus der CI auf `27c3e90` (4.7.19).

**docs: `__PYVENV_LAUNCHER__`** (E1; TECH-05, CON-02):
- Ursache: `NullStdioPopen` (A-89) setzt in der Umgebung eines spawn-Workers aus einer venv
  `env["__PYVENV_LAUNCHER__"] = sys.executable`, wie CPythons `popen_spawn_win32` (bpo-35797). Der Scan in
  `tests/packaging/test_env_example.py` hält jeden Schreibzugriff auf eine Zuordnung namens `env` für eine
  Umgebungsvariable von NeuroGrid. Er ist statisch, deshalb scheiterte er in allen sechs Jobs gleich und lokal auf
  `18da12f` ebenso (1 fehlgeschlagen, 6 bestanden).
- Behebung `29ff4af`: der Name in `THIRD_PARTY` (Variablen anderer Programme, die NeuroGrid für sie setzt), nicht in
  `.env.example`. Dazu `9b9a98b` (posix): `USER` und `LOGNAME` in `PROVIDED` (vom Betriebssystem gesetzt, wie
  `USERNAME` unter Windows; gelesen von `_measured` im Konsolentest). Entfällt die Zeile in `kernel/processes.py`, muss
  der Eintrag mit, sonst scheitert `test_reviewed_names_are_in_use_and_in_one_set_only`.

**posix P1: resource tracker** (`[spawn]`, `[forkserver]`; NG-N05, TECH-05):
- Ursache (ein Rennen im Test, kein Produktfehler), gefunden in den Quelltexten von CPython 3.11.17, 3.12.15 und 3.13:
  `util.spawnv_passfds` lässt 0–2 vererben und reicht zusätzlich `sys.stderr.fileno()` weiter, `resource_tracker.main`
  schließt nur stdin und stdout und entfernt die Semaphore erst im `finally` nach EOF. Der gewöhnliche tracker hält
  daher die stderr-Pipe von `subprocess.run`, und `run()` kehrt erst nach seinem Aufräumen zurück (1.6 Punkt 28). Der
  stumme tracker von NeuroGrid hält keine Pipe; `run()` kehrt beim SIGKILL zurück, während der tracker noch startet,
  und der Test sah das Semaphor zu früh.
- Behebung `919bd11` (nur Test): Das getötete Skript druckt die PID des trackers; `_wait_for_end` wartet auf dessen
  Ende (unter Linux pidfd plus `select`, höchstens 60 s; sonst `os.kill`-Abfrage); eine neue Zusicherung verlangt das
  Ende, die Meldung nennt PID und Wartezeit.

**posix P2: geforkter Worker unter `capfd`** (`[fork]`; NG-N05, TECH-05):
- Ursache (Produktfehler gegen den Docstring): `null_descriptors` legte nur 0–2 auf das Nullgerät. Ein geforktes Kind
  erbt die Stream-Objekte des Elternprozesses; unter `capfd` schreiben sie auf einen Deskriptor über 2 (1.6 Punkt 27).
  Im CLI liegen die Streams auf 0–2, aber ein einbettendes Programm oder ein `sitecustomize` erzeugt dieselbe Lage.
- Behebung `3d212b5`: `null_descriptors` legt unter POSIX auch die Deskriptoren hinter `sys.stdout`, `sys.stderr`,
  `sys.__stdout__`, `sys.__stderr__` auf das Nullgerät (`_stream_descriptors`) und stellt jeden mit seinem
  Vererbungs-Flag wieder her; `_after_fork_in_child` (über den Stapel `_SAVED`) schließt in einem im Fenster geforkten
  Kind die Kopien der Konsolendeskriptoren und bindet `sys.stdin/stdout/stderr` vor dem Bootstrap an das Nullgerät;
  `_START_LOCK` ist ein `RLock`, die Kopien ein Stapel (verschachtelte Fenster). `1ebe89b`: Ein Fenster, das einen
  Deskriptor nicht kopieren oder das Nullgerät nicht öffnen kann (EMFILE, ENFILE), wirft vor seinem Block und ändert
  nichts (`_on_null`; als geschlossen gilt ein Deskriptor nur bei EBADF). `5aa8749`: Docstrings nennen die Grenze
  (ein fremder forkserver oder tracker behält seine Deskriptoren).
- Nachweis lokal nur simuliert: `1ebe89b` wurde mit dem POSIX-Zweig unter Windows und einem nachgebauten `fcntl`
  geprüft (Skript im Scratchpad; auf `5aa8749` lief der Block mit geschlossenem Deskriptor 1 bzw. blieben Kopien
  offen, danach keiner der beiden Fälle) [D].

**posix P3: `AssertionError: 1`** (CLI-Test unter Linux; NG-N05, NG-N03):
- Ursache: Die nackte `1` ist die Meldung `jobs` der Konsolenzusicherung, also der Lauf mit `--jobs 1`. Dort läuft die
  ganze Stichprobe (pyprep, autoreject, ICA, ICLabel) im CLI-Prozess, unter Linux zum ersten Mal in einem Test. Im
  gepinnten Linux-Wheel (aus `.local/notices-wheels`, SHA-256 wie in `uv.lock`, kein Download) stehen die Zeichenketten
  der Geräteerkennung (1.6 Punkt 29) [G]:
  ```powershell
  & $PY -I -c "import zipfile,sys; z=zipfile.ZipFile(sys.argv[1]); [print(n) for n in z.namelist() if '.so' in n and b'GPU device discovery failed: ' in z.read(n)]" .local\notices-wheels\onnxruntime-1.31.0-cp312-cp312-manylinux_2_28_x86_64.whl
  # onnxruntime/capi/libonnxruntime.so.1.31.0 und onnxruntime_pybind11_state.cpython-312-x86_64-linux-gnu.so
  ```
  Neben „GPU device discovery failed: “ stehen dort „NPU device discovery failed: “, `/sys/class/drm` und
  `core/platform/linux/device_discovery.cc`. Die genaue Zeile hat keine CI-Annotation gezeigt; belegt sind die Strings
  und der grüne Linux-Testjob nach der Behebung.
- Behebung `223206b`: `kernel/processes.on_null_device()`; `quality.sample._iclabel` importiert onnxruntime, schaltet
  die Telemetrie ab und rechnet ICA und `label_components` darin (Werte unverändert, NG-N03). Der Konsolentest meldet
  seither `_measured(...)`: `--jobs`, Exitcode, Probleme und bis zu vier auffällige Konsolenzeilen (Benutzerordner,
  Benutzer, Rechner und Testordner ersetzt).
- Reparatur `7f5b3b0`: Die Annahme in `223206b`, das Windows-Build habe keine solche Erkennung, war falsch. Die
  Windows-DLL hat `core/platform/windows/device_discovery.cc` („Failed to load dxcore.dll …“, „Failed to create DXGI
  factory.“), importiert wie `python312.dll` die gemeinsame UCRT (`api-ms-win-crt-*`), dazu `MSVCP140` (PE-Importe
  gelesen), und schreibt über
  `WOStreamSink(std::wclog)`; mit dem Logger auf VERBOSE schreibt eine Sitzung UTF-16-Zeilen nach stderr, mit 1/2 auf
  NUL nichts. Ein echter Konsolen-Stream (`_WindowsConsoleIO`) wirft auf NUL `OSError` (WinError 1); in ICLabels `try`
  würde M09b dann `failed`, der Wert hinge von der Konsole ab. Deshalb unter Windows `_console_on_null` (1/2 über
  `_on_null` auf das Nullgerät, `sys.stdout`/`sys.stderr` für den Block auf eine Senke an Deskriptor 1).
- Neue Tests [G: Quelltext]: in `tests/unit/test_processes.py`
  `test_null_descriptors_cover_a_stream_on_another_descriptor_and_a_forked_child`,
  `test_on_null_device_keeps_native_output_of_library_code_off_the_console`,
  `test_onnxruntime_logs_nothing_to_the_console_inside_on_null_device` (echtes onnxruntime auf VERBOSE),
  `test_on_null_device_on_a_windows_console_writes_nothing_there_and_raises_nothing` (nur Windows: Konsole mit
  `CREATE_NO_WINDOW`, liest den Bildschirmpuffer), `test_a_window_that_runs_out_of_descriptors_changes_nothing[copy|null]`;
  in `tests/unit/test_quality_sample.py` `test_onnxruntime_runs_inside_on_null_device`; in
  `tests/integration/test_worker_console.py` `test_the_failure_message_shows_the_offending_console_lines`.

**win311 W1/W2: Traceback der Warteschlange unter Python 3.11** (NG-N05, NG-N03, NG-F07):
- Ursache, lokal unter Python 3.11.17 im ersten Versuch nachgestellt (`'queues.py', line 246, in _feed` →
  `connection.py` `send_bytes` → `_check_closed` → `OSError: handle is closed`): Der Traceback kommt nicht aus einem
  Worker, sondern aus dem Feeder-Thread der Aufrufwarteschlange im Prozess von NeuroGrid, dessen stderr die Konsole
  ist. In CPython 3.11 `concurrent/futures/process.py` schließt `terminate_broken` nach dem Tod eines Workers unter
  Windows den Schreiber der Warteschlange (gh-107219), danach legt `shutdown_workers` für jeden Worker, der noch als
  lebend gilt, ein `None` hinein (`put_nowait`, nur solange ein Platz frei ist). Das Senden scheitert ohne errno, also
  greift `_ignore_epipe` nicht, und `Queue._on_queue_feeder_error` druckt den Traceback mit dem Installationspfad von
  Python (Benutzername). 3.12 und 3.13 überspringen `shutdown_workers` bei kaputtem Pool
  (`_join_executor_internals(broken=True)`). Probe mit einem gewöhnlichen `ProcessPoolExecutor` und `os._exit` im
  Task: Traceback in 5 von 5 Läufen unter 3.11, 0 unter 3.12 und 3.13.
- `AssertionError: 2` ist die Konsolenzusicherung des Laufs mit `--jobs 2`, dieselbe Ursache als Rennen (ob der
  beendete Worker noch lebt, wenn 3.11 prüft). Gezeigt hat es ein instrumentierter Manager-Thread des CLI-Prozesses:
  eine Testdatei im Scratchpad importiert `test_worker_console`, hängt Code an `twc.HOOK` (läuft als `sitecustomize`;
  Schutz `if MARKS and "--multiprocessing-fork" not in sys.argv`) und ruft die Testfunktion; außerhalb von `tests/`
  braucht sie `tests/` und `tools/` auf `sys.path` und wie `tests/conftest.py` `netguard.install()` und
  `processes.avoid_wmi()`. Ausgabe: `terminate_broken n=2 alive=[False, True]` → `shutdown_workers alive=[False, True]`
  → Feeder-Fehler `OSError: handle is closed`, danach genau `AssertionError: 2`. Lokal lief der Test auf `18da12f` grün,
  weil die Warteschlange voll war; der Semaphor-Test (2 Tasks in 3 Plätzen) scheiterte unter 3.11.17 ohne
  `quiet_pool` in 3 von 3 Läufen.
- Behebung `9b355bd`: `kernel/processes.quiet_pool(pool)` ersetzt auf jeder Plattform den Fehlerhandler der
  Aufrufwarteschlange; ein nicht picklebarer Task scheitert weiter an seinem eigenen Future (CPythons Handler über
  `weakref.WeakMethod`), jedes andere gescheiterte Senden geht nur ins Debug-Log von `multiprocessing`;
  `quality._pool` gibt `quiet_pool(ProcessPoolExecutor(...))` zurück. `a25fc54`: die Warteschlange bleibt
  einsammelbar (`test_quiet_pool_leaves_the_call_queue_collectable`). `aa03735`: die Konsolenzusicherungen drucken
  `(jobs, problems, shown)`, `shown` aus `_traces()` (Datei:Zeile, Funktion und Ausnahmetyp, ohne Pfade und Texte).
  `25ead0d`: Docstrings nennen die genaue Bedingung von 3.11. Reparatur `95f6c50`: `_FeedBuffer` hält das zuletzt
  entnommene Objekt, bis es gesendet ist; ein Task, der nicht gesendet werden konnte, scheitert jetzt an seinem Future
  (statt ohne Zeichen offen zu bleiben), `compute_all` rechnet die Aufnahme allein nach
  (`test_a_task_that_could_not_be_sent_fails_its_future`). Deterministischer Regressionstest:
  `test_the_queue_thread_of_a_pool_prints_no_failed_send`. `quiet_pool` stützt sich auf private Teile von CPython,
  die in 3.11.17, 3.12.15 und 3.13.7 gleich sind (Abschnitt 8).

**docs: Nutzerdoku und Release-Gate** (U1, NP5, C1; V-06, NG-N04, TECH-06, V-01):
- `17e0d3f`: `installation.md`, `limitations.md`, `privacy.md` (en/zh), `README.bundle.txt`, `release-notes.md`
  sagen „test suite verified in CI (Python 3.11–3.13)“ für Windows Server (`windows-latest`) und Ubuntu 24.04
  (`ubuntu-24.04`) und „test suite not run in CI“ für Debian 12 und Ubuntu 22.04 (dort nur Reinräume); Windows 10
  bleibt „not verified“. `tests/docs/test_docs_sync.py` liest Runner und Versionen aus der Testmatrix von `ci.yml`
  (`SUITE_IN_CI`, `SUITE_NOT_IN_CI`, `RUNNERS` u. a.). `341beb1`: gesperrt sind nur noch die ganzen Sätze von
  `18da12f`, nicht jedes „do not pass yet“ / „尚未通过“. `d269cb9`: Kommentar an `V01_ITEMS` (NG-F14 seit P5 erfüllt,
  nur NG-F13 wartet auf G1).
- **Release-Gate** `dd9ab93`: `ci.yml` bekommt `on.workflow_call`; `release.yml` ruft es als Job `suite` (`uses:
  ./.github/workflows/ci.yml`, gleiche Tag-Bedingung wie `build`), der Entwurf braucht `needs: [build, suite, test]`.
  Damit entsteht kein Release-Entwurf, wenn Lint, Typen, die Testmatrix, beide PowerShell-Jobs, Lizenz- oder
  Rückverfolgbarkeits-Gate auf dem getaggten Commit selbst scheitern; die Doku-Aussage „test suite verified in CI“
  hängt so am ausgelieferten Commit. Der Vergleichsjob lädt nur noch die Artefakte `results-*`. Gelaufen ist der
  Aufruf noch nie (erst mit dem ersten Tag) [NV].

**Merge** am 28.10. [G: `git log --first-parent`, `git show --remerge-diff f3fe478`]: `p5-ci3-posix` (`ce87432`, 12:17)
ohne Konflikt; `p5-ci3-win311` (`f3fe478`, 12:20) mit Konflikten in drei Dateien, alle als Vereinigung gelöst (von
beiden Bereichen vorab angekündigt [D]):
- `src/neurogrid/kernel/processes.py`: beide Importmengen (`collections`, `errno`, `weakref`, `from collections.abc
  import Callable, Iterator`); beide Zeilen `_P = TypeVar("_P")` und `_START_LOCK = threading.RLock()` (`RLock` von
  posix, nicht `Lock`); `__all__` mit `on_null_device` und `quiet_pool`.
- `tests/unit/test_processes.py`: beide Importmengen (`gc`, `importlib.util`, `json`, `time`, `weakref`).
- `tests/integration/test_worker_console.py`: Docstring des CLI-Tests aus beiden Fassungen; eine Meldung, die beides
  trägt: `assert problems == [], f"{_measured(jobs, run, problems, tmp_path)} frames {shown}"`, ebenso für `leaks`.

Danach `2a49a0c` (Lead, 4.7.19), `p5-ci3-docs` (`1dd0eac`, ohne Konflikt), `27c3e90` (Lead), Push 12:29.

**Fallen der Runde** (1.6 Punkt 27–32): Eine Meldung, die nur einen Schleifenwert zeigt („1“, „2“), sagt nicht, was
geschrieben wurde; jede Konsolenzusicherung druckt seither, was sie gemessen hat. Ein Docstring, der eine Plattform
für unberührt erklärt, braucht dieselbe Messung wie die andere (`7f5b3b0`). Lokal grüne Zeittests sagen über ein Rennen
auf dem Runner nichts.

#### 4.7.19 CI-Stand auf `27c3e90` und Notice-Annotationen

Gepusht am 28.10. 12:29; gelesen über die öffentliche API ohne Anmeldung [G, CI 27c3e90; Liste in
`.local/ci_27c3e90.txt`]:

| Workflow / Lauf | Job | Ergebnis |
|---|---|---|
| `offline`, 40680346176 | alle neun Jobs wie in 4.7.18 | grün |
| `ci`, 40680346160 | Lizenz-Gate und Netz-Scan; Windows PowerShell 5.1; PowerShell 7; Anforderungs-IDs | grün |
| | Test windows-latest × 3.11 | grün: 0 fehlgeschlagen, 3681 bestanden, 16 übersprungen (3697 Tests); Kern 93,4 %, Prüfer 97,3 % |
| | Test windows-latest × 3.12 und × 3.13 | grün: je 0 fehlgeschlagen, 3682 bestanden, 15 übersprungen (3697 Tests); Kern 93,5 %, Prüfer 97,3 % |
| | Test ubuntu-24.04 × 3.11/3.12/3.13 | grün: je 0 fehlgeschlagen, 3605 bestanden, 97 übersprungen (3702 Tests); Kern 93,3 %, Prüfer 97,3 % |
| | plattformübergreifender Vergleich (berichtet, nicht erzwungen) | grün |

Abdeckungsgrenzen: Kern ≥ 90 %, Prüfer ≥ 80 % (NG-N08), in jedem Testjob „ok“. Welche Tests ein Runner übersprang,
nennt die Annotation nicht (nur Job-Log und `pytest-junit.xml`) [NV].

**Notice-Annotationen** (`2a49a0c`, `27c3e90`; TECH-05, NG-N08) [G: Quelltext]:
- `tools/junit_annotations.py`: Die Zählzeile `pytest summary` ist bei Fehlern `::error`, sonst `::notice`; `ci.yml`
  ruft sie nach den Abdeckungs-Gates im Schritt „Test counts of a green run as an annotation“ (`if: success()`) noch
  einmal auf.
- `tools/coverage_gates.py` druckt die Werte zeilenweise und dazu eine Annotation
  `::notice title=coverage::Kern: … % (limit 90 %) ok; Prüfer: … % (limit 80 %) ok` (bei Unterschreitung `::error`);
  Test `tests/unit/test_coverage_gates.py::test_the_gates_print_their_values_as_one_annotation`.

**Lesen ohne Anmeldung** (Skript des Leads, nur im Scratchpad; hier sein Ablauf) [G: Skript gelesen und ausgeführt]:
1. `GET https://api.github.com/repos/Ammxri/neurogrid/actions/runs?head_sha=<sha>&per_page=50` → `workflow_runs`
   (je Workflow ein Lauf: `id`, `name`, `status`, `conclusion`). `<sha>` ist der volle 40-stellige Hash
   (`git rev-parse 27c3e90` → `27c3e903efae52032556aac023218caedb5b88af`); mit dem Kurz-Hash kommen keine Läufe.
2. je Lauf `GET …/actions/runs/<run-id>/jobs?per_page=100` → `jobs` mit `id`, `name`, `conclusion`, `steps`.
3. je Job `GET …/check-runs/<job-id>/annotations?per_page=100` (die Job-ID ist die Check-Run-ID) → `annotation_level`
   (`failure`, `warning`, `notice`), `title`, `message`.

```python
import json, sys, urllib.request

API = "https://api.github.com/repos/Ammxri/neurogrid"


def get(url):
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request) as response:
        return json.load(response)


for run in get(f"{API}/actions/runs?head_sha={sys.argv[1]}&per_page=50")["workflow_runs"]:
    print("RUN", run["id"], run["name"], run["status"], run["conclusion"])
    for job in get(f"{API}/actions/runs/{run['id']}/jobs?per_page=100")["jobs"]:
        print("  JOB", job["id"], job["name"], job["status"], job["conclusion"])
        for note in get(f"{API}/check-runs/{job['id']}/annotations?per_page=100"):
            print("    ", note["annotation_level"], note["title"], "::", note["message"])
```
Aufruf aus Git Bash mit `PYTHONIOENCODING=utf-8` (1.6 Punkt 9; sonst erscheint „Prüfer“ verstümmelt). Das Skript des
Leads zeigt Annotationen nur bei gescheiterten Jobs oder mit `--all-annotations`. Solange ein Job läuft, steht
`in_progress` da (so der Vergleichsjob beim ersten Lesen von `27c3e90`); erneut lesen, bis jeder Lauf `completed` ist.

**Wie die Zahlen in die Doku kommen** (Prozessentscheidung, 4.0): nach grüner CI die beiden Annotationen jedes
Testjobs lesen und unverändert übernehmen; lokal laufen nur die betroffenen Tests (4.7.20).

#### 4.7.20 Stand heute (`27c3e90`) und was zu P5 noch fehlt

Geprüft auf `18da12f` [G, 18da12f, im Worktree `p5-final-docs`]; `pyproject.toml` und `uv.lock` sind bis `27c3e90`
unverändert:
- `uv lock --check --offline` → 103 Pakete; `ruff check .` „All checks passed!“; `ruff format --check .` „227 files
  already formatted“.
- `gen_fixtures`, `gen_schemas`, `gen_montage_names`, `gen_docs`, `calibrate`, `linux_pdf_packages` je `--check` grün;
  `install_pdf_browser.py --check` „complete (revision 1243, 290 files)“; `notices.py --wheelhouse … --check` „up to
  date“; `check_matrix_coverage.py` 166/166; `check_commit_ids.py` 181 Commits, 7 Phaseneinträge, 0 Probleme.
- Testsammlung: 3810 Tests, Standardlauf 3683, abgewählt 127 (114 `corpus`, 9 `perf`, 4 `bundle`); Marker `pdf` 101,
  `browser` 2. Auf `27c3e90` zählt die CI im Standardlauf 3697 Tests unter Windows und 3702 unter Linux (4.7.19).

**Testsuite auf dem Endstand:** Die volle Suite lief nur in den sechs Testjobs der CI, alle grün (4.7.19); eine lokale
volle Suite auf `27c3e90` lief nicht (Prozessentscheidung, 4.0). Lokal liefen nur die von der dritten Runde
betroffenen Tests [G: Logs]:
- Python 3.12 (`.venv`): 184 bestanden, 5 übersprungen, 52 abgewählt in 2472,62 s (41 min)
  (`.local/logs/targeted_27c3e90_py312.log`, Exit 0);
- Python 3.11: 18 bestanden, 4 übersprungen in 263,59 s (`.local/logs/targeted_27c3e90_py311.log`, Exit 0).

Lokale volle Suiten früherer Runden (Geschichte): `dcec9bd` (Windows 11, Python 3.12, `NEUROGRID_REQUIRE_PDF=1`)
3647 bestanden, 21 übersprungen, 127 abgewählt, 1 fehlgeschlagen (`test_one_recording_with_jobs_4_equals_jobs_1`,
4.7.17; allein grün, in der CI grün; A-88) [G: Log]; ältere Stände in 4.7.8 und 4.7.13.

**G1** [G: `.local/p5/ci3/g1_summary_18da12f.md`, `.local/logs/g1_18da12f.log`]: auf `18da12f` „G1: 6/6 data sets
passed, formats BDF, BrainVision, EDF, EEGLAB, FIF; minimum met; all criteria of this run met“, Exit 0, 151 min
(`real 151m40.587s`): je Datensatz beide Läufe byte-gleich, 0 Probleme; `--jobs 1` = `--jobs 4` auf ds004148-1.0.1;
Korpus unverändert; V-01-Checkliste erfüllt; V-06-Zeile „ja“. Weil die dritte Runde den Windows-Pfad geändert hat
(`quiet_pool` in jedem Pool, `on_null_device` um ICLabel), läuft G1 einmal auf dem Endstand `27c3e90`:
6 von 6 Datensätzen in 5 Formaten bestanden, alle Kriterien erfüllt, 0 Probleme, V-01 erfüllt, V-06 ja (149 min 28 s; `.local/p5/ci3/g1_summary_27c3e90.md`).

Korpustests (`-m corpus`, 114) auf dem Endstand [G]: `tests/corpus/test_corpus.py` 62 von 62 bestanden (12 im ersten Lauf, dessen 3-h-Grenze im Test `…converts_without_validator_errors[keep-headers-BrainVision]` ablief – allein 242 s, bestanden –, die übrigen 50 in 74 min; `.local/logs/corpus_27c3e90.log`, `.local/logs/corpus_27c3e90_rest.log`); `tests/acceptance/test_g1_corpus.py` (52 Tests, ruft die Abnahme selbst auf, ≈ 2 h): auf 27c3e90 48 bestanden, 4 gescheitert – `test_no_host_path_or_header_data_in_outputs[psg-ipa-1.0.0]` und die drei Tests über den ganzen Lauf, die daraus folgen. Ursache im Prüfwerkzeug, nicht im Produkt: pytests Ausgabeordner liegt unter `pytest-of-<Login>`, die Konsole druckt ihn geschwärzt (`pytest-of-<user>`, A-51), die Prüfung nahm diese Form nicht als den eigenen `--out`-Ordner heraus, und der Rohordner `PSG` traf `psg-ipa-1.0.0` im Ausgabepfad; behoben in 7426dee (`_path_forms` kennt die geschwärzte Form; Regressionstest `test_a_redacted_output_path_on_the_console_is_no_raw_name_leak`, vor dem Fix rot, danach grün). Wiederholung des Moduls auf 7426dee: 52 von 52 bestanden (1 h 57 min; `.local/logs/g1corpus_7426dee.log`). Noch offen vor G1: `bundle.py sizes` [NV];
Phasenbericht an den Projektverantwortlichen. Erzeugt nach dem letzten G1-Lauf: das zh-Prüfpaket (`zh_review_package.py --g1 .local/acceptance/g1 --since 6a4f737 --out .local/acceptance/zh_review.md`: 2626 zh-Texte aus 35 Dateien, 145 neu und 1 geändert gegenüber dem ersten Paket auf `6a4f737`, zwei Beispiel-PDFs; 4.7.8). Erledigt seit
`18da12f`: CI grün auf ubuntu-24.04 und windows-latest (4.7.19), die Plattformzellen der Nutzerdoku (`17e0d3f`).

#### 4.7.21 STOPP G1 (teilweise entschieden, D-18)

Stand 02.11.2026: Am 29.10.2026 hat der Projektverantwortliche mit D-18 die Annahmen A-78..A-89, die Lesarten R16/R12
und die Lesart von D-15 zu core-js-pure freigegeben und P6 parallel zur zh- und Sichtprüfung gestartet (4.8); offen
sind zh-Prüfung, Sichtprüfung, die Anfrage an die Validator-Entwickler, die Kenntnisnahme der Grenzen und das Release.
Nach D-19 (02.11.2026) wird v0.1.0 aus dem P5-Stand `c4f240a` plus den Korrekturen der Prüfungen auf einem
Release-Zweig geschnitten, nicht aus `dev`. Die folgende Liste ist der Stand der Vorlage von STOPP G1:

STOPP G1 war **offen**; er folgte mit dem Phasenbericht des Leads (G1 auf `27c3e90`: 6 von 6 Datensätzen in 5 Formaten bestanden, alle Kriterien erfüllt, 0 Probleme, V-01 erfüllt, V-06 ja (149 min 28 s; `.local/p5/ci3/g1_summary_27c3e90.md`); CI auf
`27c3e90` grün, 4.7.19; G1 auf `18da12f` bestanden, 4.7.20). Die vollständige Liste führt FORTSCHRITT („Für STOPP G1
vorgemerkt“). STOPP G1 enthält, jeweils durch den Projektverantwortlichen:
- muttersprachliche zh-Prüfung mit dem Paket aus `tools/zh_review_package.py`, erzeugt nach dem letzten G1-Lauf
  (D-17), einschließlich der neuen Schlüssel und Sätze aus 4.7.8 und der zh-Sätze von `17e0d3f` in
  `docs/zh/installation.md`, `limitations.md`, `privacy.md`; Sichtprüfung der Beispiel-PDFs (kein PDF-Renderer
  lokal).
- Bestätigung der Annahmen A-78..A-89 und der Lesarten der PRD daraus (u. a. Abschnitt 4 mit Aggregaten von
  `results.ai`, Anhang 6.1/6.6, nur 50 Zeilen je Regel plus `results.json`, Überschriften von Abschnitt 3), dazu die
  geänderten A-51, A-54, A-67; die Lesart der Signatur (R12 Grenze).
- Bestätigung des Installationshinweises nach R16 (cosign im PATH prüft immer, der Schalter überspringt nur eine
  Installation ohne cosign).
- Kenntnisnahme der bekannten Grenzen: `convert`-Ausgabe zwischen Betriebssystemen nicht byte-gleich (MNE-BIDS und pybv
  schreiben Textdateien mit `os.linesep`); Codepage-Aliase `mbcs`/`dbcs`/`oem` bleiben plattformabhängig; `avoid_wmi`
  und `quiet_pool` stützen sich auf private CPython-Teile; direktes Schreiben auf das Konsolengerät bleibt ein
  Restrisiko; ein fremder forkserver oder resource tracker behält seine Deskriptoren; Warnungen der Worker entfallen
  bei `--jobs` > 1 (Abschnitt 8).
- Versand der Anfrage an die Validator-Entwickler (D-16; Entwurf `.local/p5/upstream_issue_bids_validator.md`).
- Freigabe des Merge von `dev` nach `main` und der Schritte zu v0.1.0: Version `0.1.0`, Tag `v0.1.0`, `release.yml`
  (mit dem Job `suite` als Release-Gate, 4.7.18), TestPyPI/PyPI über Trusted Publishing, Gitee-Spiegel und
  Gitee-Release von Hand (R15).
- Bereits entschieden (D-17): Lizenztexte der acht Lücken (abgelegt, 4.7.15); M14 Option B; zh-Prüfung der P6-Texte
  Option C (bei G1 nur die Kernbegriffe, die vollen Texte vor v0.2); zh-Paket nach dem Merge der zweiten
  CI-Fix-Runde. Geplant war, P6 erst nach G1 zu beginnen; nach D-18 lief P6 parallel (4.8), mit Annahmen ab A-90
  (3.3). Die Kernbegriffe von P6 für die zh-Prüfung nennt FORTSCHRITT („Für STOPP G1 vorgemerkt“).

### 4.8 P6 – NeuroVault, Einwilligung M14, Gerüst yyt2029 (2026-10-29 bis 11-02; Stand 0ffdd90)

Matrix: schließt NG-F11, NV-F01, NV-F02, NV-F03, M14, DM-08, DM-09, CLI-09, RP-10, ARC-01 ab (10), trägt zu NG-F16,
CLI-08, UF-03, UF-06, V-02 bei (5; KONZEPT 6, `check_matrix_coverage.py`) [G]. NV-F03 steht auf `teilweise`, bis P8 die
Details aus dem Normtext bringt; den Stand je Zeile führt die Matrix. Grundlage: die Vorgaben des Leads (privat:
`.local/p6/p6_decisions_draft.md`, `.local/p6/p6_final.md`, die Bereichsspezifikationen `.local/p6/spec/vault.json`,
`consent.json`, `yyt2029.json`), D-17 (M14 Option B, zh Option C), D-18 (P6 parallel zu den G1-Prüfungen); Annahmen
A-90 (NeuroVault), A-91 (Einwilligung M14), A-92 (Gerüst yyt2029). Keine neue Abhängigkeit, kein Download.

#### 4.8.1 Vorgehen

| Datum | Commit | Schritt |
|---|---|---|
| 29.10. 02:34 | `8391420` | Start auf `dev`: Version `0.2.0.dev0` (4.8.2) |
| 29.10. 02:40 – 05:58 | Zweig `p6-yyt2029`: `3bd764f`, `e84b8ef`, `85f382d` | Gerüst, DoD-Tests, Vorlage der Auslegungsfragen (4.8.3); der Zweig wurde so neu geschrieben, dass jeder Commit die Prüfungen besteht (`85f382d` hat den Baum von `518964e`, Sicherung `backup-p6-yyt2029-518964e`) [G: `git diff --quiet 518964e 85f382d`] |
| 29.10. 04:18 | Zweig `p6-vault`: `f023146` | Schnittstellen-Freeze (4.8.4) |
| bis 02.11. 07:24 | `57fb4a0` (`p6-vault`), `0c81561` (`p6-consent`, auf `f023146`) | Bau vault und consent; beide Bau-Agenten endeten am Sitzungslimit vor ihrem Bericht, der Stand ist als `wip:`-Commit festgehalten (4.8.4, 4.8.5) |
| 02.11. 07:28 – 07:30 | `9a9433e` (`p6-yyt2029`), `ed81152` (`p6-vault`) | Befunde der Nachprüfung von yyt2029; Zeilenlänge eines CLI-Tests |
| 02.11. 07:30 – 07:35 | Merges `9272cd9` (consent), `3646997` (vault), `c516598` (yyt2029) | Merge in dieser Reihenfolge (4.8.6) |
| 02.11. 07:39 – 07:47 | `40d6d16`, `d50158b`, Push 07:47 | Querschnittstests, semantische Merge-Korrekturen; CI auf `d50158b` (4.8.7) |
| 02.11. 08:22 | `2f2a5a5` | die fünf Fehler der CI auf `d50158b` behoben (4.8.7) |
| 02.11. 09:14 – 10:37 | Zweig `p6-fix`: `754aef6`, `09cd05a`, `eabdef6`, `8b36697`, `f307754`, `16fd7c9`, `9e44134`; Merge `0ffdd90`, Push 10:42 | Review und Fix-Runde (4.8.8); CI auf `0ffdd90` (4.8.9) |
| 02.11. | Zweig `p6-docs` | diese Doku |

Zeiten sind Autorzeiten der Commits (`git log --format='%h %ad' --date=format:'%d.%m. %H:%M' c4f240a..0ffdd90`) [G].
Die Bereiche arbeiteten in Worktrees wie in 3.5 (`git worktree add ".claude\worktrees\p6-<bereich>" -b p6-<bereich>
<basis>`), vault und yyt2029 ab `8391420` bzw. `c4f240a`, consent ab `f023146`.

#### 4.8.2 Start und Version (`8391420`; V-02)

- `src/neurogrid/__init__.py`: `__version__ = "0.2.0.dev0"`; `docs/en/installation.md` und `docs/zh/installation.md`
  nennen diese Version mit unveränderter Präfixgrenze (längster Installationspfad 148 Zeichen, Präfix höchstens 101).
  Tests, die `0.1.0rc1` als Testdatum pinnen, bleiben (A-90 „Übergreifend“).
- Nach D-19 entsteht v0.1.0 später aus `c4f240a` auf einem Release-Zweig, nicht aus `dev`; `tools/release_check.py`
  lehnt Entwicklungsversionen ohnehin ab (A-87).
- Prüfung (PowerShell) [D: Bericht des Freeze, 49 bestanden]:
  ```powershell
  $PY = ".\.venv\Scripts\python.exe"
  & $PY -m pytest -q -p no:cacheprovider tests\packaging\test_packaging_texts.py tests\unit\test_norm_independence.py tests\packaging\test_release_check.py tests\acceptance\test_zh_review_package.py
  ```
- Die Metadaten der editierbaren Installation nennen bis zum nächsten `uv sync --locked --no-build` noch `0.1.0rc1`
  (`importlib.metadata`); NeuroGrid und die Tests lesen `neurogrid.__version__` [D].

#### 4.8.3 Bereich yyt2029 (A-92; RP-10, NG-F11, V-06, POS-01, RP-08)

**Gebaut** (`3bd764f`, `e84b8ef`, `85f382d`, `9a9433e`):
1. `src/neurogrid/rulepacks/yyt2029.yaml` (Platzhalter, `0.2.0-draft` auf eigener Zeile, `norm: true`, nur
   YYT2029-ACQ-001 mit Klausel `TBD`, `signal.sampling_rate_consistency`, `{min_hz: 500}`, error). SHA-256 der Datei mit
   LF: `31bcab4eee2b3d81d2402a589ffd86a879093825a2718d33bf62a8859f6209f1` (steht in `docs/<lang>/reference/rules.md`;
   nach jeder Änderung `gen_docs.py` laufen lassen) [D].
2. `tools/gen_docs.py`: `PACKS` mit vier Paketen; Klausel des Platzhalters = `report.value.placeholder_clause`, Regel-IDs
   mit `labels.rules.placeholder_suffix`; Prüfung und Block der Auslegungsfragen (Modelle `Reading`, `Asked`,
   `Question`, `QuestionsFile`; `validate_questions`, `load_questions`, `questions_block`, gemeinsame `environment()`);
   Vorlage `tools/docs_templates/questions.md.j2`; `docs/_data/interpretation_questions.yaml` leer.
3. `cli.py`: `{packs}` von `cli.check.passes`/`fails` ohne Platzhalter-Pakete, sonst `cli.check.none_evaluated`;
   `report/render.py` `_Formatter.overall(summary, rulepacks)` mit `report.text.overall_none_evaluated`.
4. `tests/unit/test_norm_independence.py` neu gefasst (ohne Versionsschranke, Gerüst bis P8 festgehalten, `KNOWN` als
   genaue Zeilen); V-06-Satz in `index.md`, `limitations.md`, `rulepacks.md` (en/zh); Nutzerdoku `rulepacks.md`,
   `commands.md`, `report.md`, seit `9a9433e` auch `configuration.md`.
5. Nach der unabhängigen Nachprüfung (19 Prüfpunkte erfüllt, 7 neue Probleme [D: `.local/p6/workflow_result.json`])
   `9a9433e`: Texte der Auslegungsfragen ohne Nennung der Norm und ohne Zeile mit Name und Punktzahl, erweiterter
   Bereich chinesischer Zeichen, keine Regel doppelt; Paket und Version auf getrennten Zeilen in `_cover.html.j2`.

**Erzeugen und prüfen** (PowerShell):
```powershell
$PY = ".\.venv\Scripts\python.exe"
& $PY tools\gen_docs.py            # 10 Dateien: je Sprache reference/checks.md, reference/rules.md, metrics.md, installation.md, rulepacks.md
& $PY tools\gen_docs.py --check    # "documentation up to date" [G, 0ffdd90]
$env:NEUROGRID_REQUIRE_PDF = "1"; $env:PYTHONWARNDEFAULTENCODING = "1"
& $PY -m pytest -q -p no:cacheprovider tests\integration\test_yyt2029_scaffold.py tests\rules\test_builtin_rules.py tests\unit\test_engine.py tests\unit\test_message_tables.py tests\unit\test_language_and_wording.py tests\unit\test_norm_independence.py tests\docs\test_docs_build.py
```
Ergebnis [D]: auf `518964e` 508 bestanden in 35:43 min (mit `test_check_pipeline.py`, `test_report.py`,
`test_report_p5.py`, `test_report_pdf.py::test_placeholder_banner_required_once`, `tests/cli/test_cli.py`,
`test_cli_help_i18n.py`, `tests/acceptance/test_console_sentence.py`); die Nachprüfung 815 bestanden, 3 übersprungen
(die drei Skips sind ältere Umgebungs-Skips von `tests/docs/test_notices.py`). Laufzeiten: `test_yyt2029_scaffold.py`
(23 Tests mit dem PDF-Test) etwa 4:50 min, `test_norm_independence.py` 17–25 s (Scan von `git ls-files`), die
Doku-Tests zusammen (mit dem MkDocs-Bau) 130 Tests in 16:38 min [D].

**Regelfälle:** YYT2029-ACQ-001 besteht auf `edf_ok` (512 Hz) und scheitert auf `edf_lowrate` (256 Hz) und `edf_mixed`;
mit `tests/fixtures/documented.toml` enden `edf_lowrate` und `edf_mixed` mit und ohne `yyt2029` mit Exit 0 – der Beleg,
dass die verletzte Fehlerregel des Platzhalters Exit 1 nie setzt [D].

**Fallen:** Jede neue Zeile in einer versionierten Datei, die das Paket oder die Norm nennt, muss genau in `KNOWN` von
`tests/unit/test_norm_independence.py` stehen, und keine Zeile darf Name und Version näher als 40 Zeichen bringen (so
scheiterte die CI auf `d50158b` an zwei Zeilen des Querschnittstests, 4.8.7). Eine HTML-Ausgabe mit `yyt2029` würde
vor `9a9433e` diese Regel auf dem Deckblatt verletzen; ein Bericht mit diesem Paket gehört nie als Golden ins
Repository.

#### 4.8.4 Bereich vault (A-90; NV-F03, NV-F01, DM-09, CLI-08, CLI-09, ARC-01)

**Freeze `f023146`** (erster Commit des Bereichs, die Schnittstelle für consent) [G: Quelltext, Commit-Meldung]:
`model/access.py` (AccessEvent, `ACTIONS`, `ROLE_PATTERN`, Grenzen, Prüfungen von Text, Objekt und Zeit),
`vault/store.py` (`locate`, `locate_default`, `VaultLocation`, `require_present`, `init_vault`, `replace_file`,
`CONSENTS_TEMPLATE`), `vault/lock.py` (`exclusive`, `HeldLock`, `VaultLocked`, `LOCK_TIMEOUT_S` 10.0, `POLL_S` 0.05),
`vault/ledger.py` (Hash-Regel mit Testvektor, `append`/`append_locked` mit `AppendOutcome`, `check_fields`, `snapshot`,
`iter_entries`, `verify`), `vault/roles.py`, `vault/_os.py` (Plattformcode mit `# platform-only`-Markierungen),
`cli.py` (`_help_scope`, verschachtelte `_HelpGroup`, `vault_app`, `consent_app`), Schlüssel `cli.help.vault.*`,
`errors.vault.*`, core 0.2.0, `schemas/access_event.schema.json`, die Importgrenze in `tests/unit/test_architecture.py`.
Typer 0.27.3/click 8.5.0: Eine Unter-Typer-Gruppe ohne Befehl braucht `no_args_is_help=True` ausdrücklich; Pydantic 2.14
nimmt im strikten Modus `True` und `1.0` für `Literal[1]` an, deshalb ist `format_version` ein int mit `ge=1, le=1` [D].

**Nach dem Freeze** (`57fb4a0`, `ed81152`; die Inhalte stehen nur in Code, Tests und Doku, weil der Bau-Agent vor
seinem Bericht endete) [G: `git show --stat 57fb4a0`]: `checks/access.py` (CORE-NV03-01/02), `pipeline.py`
(Ereignisse von check, convert, report, scan, manifest und verify; `PendingAccess`; `vault init`, `vault log`,
`vault log --show`, `vault verify`), `cli.py` (die drei Befehle, `check --role`, `report --config`),
`config.py` (`[vault] role` nach `ROLE_PATTERN`), `io/provenance.py` und `kernel/provenance.py` (Sperrdatei),
`report/render.py`, `report/output.py` und Vorlagen (Zeile des Zugriffsprotokolls, `report.text.os_access`),
`tools/coverage_gates.py` (Plattformblöcke, `--platform`), `docs/<lang>/vault.md` (neu) und Teile von `commands.md`,
`configuration.md`, `data-model.md`, `limitations.md`, `metrics.md`, `privacy.md`, `reference/outputs.md`, `report.md`;
Tests `tests/cli/test_cli_vault.py`, `tests/integration/test_vault_pipeline.py`, `tests/docs/test_docs_vault.py`,
`tests/rules/vault_setups.py`, Regelfälle in `tests/rules/test_builtin_rules.py`, `tests/unit/test_coverage_gates.py`.

**Erzeugen und prüfen** (PowerShell):
```powershell
$PY = ".\.venv\Scripts\python.exe"
& $PY tools\gen_schemas.py --check   # "schemas up to date": acht Schemas, neu access_event und consents [G, 0ffdd90]
& $PY -m pytest -q -p no:cacheprovider tests\unit\vault tests\unit\test_access_event.py tests\cli\test_cli_vault.py tests\integration\test_vault_pipeline.py tests\docs\test_docs_vault.py tests\unit\test_architecture.py tests\unit\test_coverage_gates.py
.\.venv\Scripts\mypy.exe --strict src\neurogrid\vault src\neurogrid\model\access.py
.\.venv\Scripts\mypy.exe --strict src\neurogrid\vault --platform linux   # die POSIX-Zweige von _os.py statisch
```
Ergebnis [D]: im Freeze die neuen Tests ohne den 10⁵-Test 257 bestanden, 4 übersprungen (POSIX: dreimal
`test_init_posix_permissions`, `test_flock_branch`), `test_verify_streams_100k_entries` allein in 190 s unter starker
Last (Grenze 300 s; unbelastet nicht gemessen); `tests/unit/vault/test_lock.py` dauert etwa 80 s, weil jeder Kindprozess
`neurogrid` importiert (`test_concurrent_appends_8_processes_x_25`: 8 Prozesse, Start über eine stdin-Schranke). Lauf der
betroffenen Tests des Bereichs am 02.11.: 702 bestanden, 6 übersprungen in 288,36 s (`.local/logs/vault_tests_1.log`).
Das Ziel „`vault verify` mit 10⁶ Einträgen in < 30 s“ ist nicht gemessen [NV].

**Fallen** [D]: Kindprozesse der Tests schreiben unter Windows CRLF auf stdout (Vergleich mit `readline().strip()`);
eine sehr lange `parametrize`-ID sprengt `PYTEST_CURRENT_TEST` (über 32 767 Zeichen), deshalb ausdrückliche IDs. Unter
Windows werden `test_init_posix_permissions` und `test_flock_branch` übersprungen; sie nennen die gemessenen Modi in ihrer
Meldung für die Linux-CI.

#### 4.8.5 Bereich consent (A-91; NV-F01, NV-F02, M14, DM-08)

Gebaut auf `f023146` (`0c81561`; Inhalte nur in Code, Tests und Doku, der Bau-Agent endete vor seinem Bericht)
[G: `git show --stat 0c81561`]: `model/consent.py` (ConsentScope, ConsentFile, kanonisches Schreiben, Hash),
`vault/consents.py` (Lesen für `check`, `consents.tsv`, `vault consent add`), `checks/consent.py` (CORE-M14-01),
`config.py` (`[consent]` mit `DEFAULT_SPLIT_USE` und `configured`), `model/results.py` (`consents_sha256`),
`report/render.py`, `report/tables.py` und `_findings.html.j2` (M14-Block), `cli.py` (`vault consent add`),
`schemas/consents.schema.json`, `tools/gen_schemas.py`, `tools/gen_docs.py` (Schweregrad-Hinweis von M14),
`tools/acceptance_g1.py` (M14-Block statt Befundzeilen); Doku `metrics.md#M14`, `configuration.md`,
`data-model.md`, `reference/outputs.md`, `privacy.md`, `limitations.md`, `terms.md`; Tests
`tests/unit/test_consent_model.py`, `test_config_consent.py`, `tests/unit/vault/test_consents.py`,
`tests/cli/test_cli_consent.py`, `tests/integration/test_consent_pipeline.py`, `tests/rules/consent_setups.py`.

**Prüfen** (PowerShell):
```powershell
$PY = ".\.venv\Scripts\python.exe"
& $PY -m pytest -q -p no:cacheprovider tests\unit\test_consent_model.py tests\unit\test_config_consent.py tests\unit\vault\test_consents.py tests\cli\test_cli_consent.py tests\integration\test_consent_pipeline.py tests\unit\test_data_model.py tests\rules\test_builtin_rules.py
```
Lauf der betroffenen Tests des Bereichs am 02.11.: 485 bestanden in 163,55 s (`.local/logs/consent_tests_1.log`) [G:
Protokoll]. Darin u. a. `test_consent_add_while_a_check_appends` (zwei echte Prozesse, Kette intakt, beide Ereignisse
da) und `test_a_write_failure_after_the_event` (`os.replace` scheitert zweimal: Exit 2, Ereignis bleibt, Datei
unverändert).

#### 4.8.6 Merge, Querschnittstests, Merge-Korrekturen

```powershell
$PY = ".\.venv\Scripts\python.exe"
git merge --no-ff p6-consent      # 9272cd9; bringt den Freeze f023146 mit
git merge --no-ff p6-vault        # 3646997
git merge --no-ff p6-yyt2029      # c516598
& $PY tools\gen_schemas.py --check
& $PY tools\gen_docs.py --check
uv lock --check --offline         # unverändert, 103 Pakete
```
- Querschnittstests `40d6d16`, `tests/integration/test_p6_cross.py`: `test_uf06_init_consent_add_log_show_verify`,
  `test_uf03_consent_documented_and_checked`, `test_dod_two_checks_vault_consents_yyt2029_byte_identical` (`--jobs 1`
  und `4`), `test_linked_vault_and_linked_consents_exit2` (ohne erlaubte Datei-Links wird der zweite Teil
  übersprungen), `test_vault_without_access_log`, `test_five_stages_with_suppliers`, `test_five_stages_print` (Marker
  `pdf`). Lauf: 7 bestanden, 1 übersprungen in 41,10 s (`.local/logs/p6_cross_1.log`) [G: Protokoll]. Die Startseite
  nennt NeuroVault teilweise verfügbar.
- Gemergter Stand, betroffene Tests: 1096 bestanden, 9 fehlgeschlagen, 6 übersprungen in 434,56 s
  (`.local/logs/p6_merged_1.log`) [G: Protokoll]: `test_language_and_wording.py::test_all_languages_have_the_same_keys`
  und `::test_placeholders_match_across_languages` (`report.access` lag in zh und de nicht unter `report`), sechs Tests
  in `test_report_p5.py` (Berichte mit M14 und NV03 zugleich), `test_docs_build.py::test_docs_pages_exist_in_both_languages`
  (17 statt 16 Seiten mit `vault.md`). Behoben in `d50158b`.
- Merge-Konfliktstellen laut Bereichsbericht yyt2029 [D]: die i18n-Tabellen (Vereinigung), der `check`-Block in
  `cli.py`, `tests/rules/test_builtin_rules.py` und `tests/docs/test_docs_build.py`.

#### 4.8.7 CI auf `d50158b` und `2f2a5a5`

Gelesen wie in 4.7.19 [G, CI d50158b; `.local/ci_d50158b.txt`, mitgeschrieben, als drei Testjobs noch liefen]:

| Workflow / Lauf | Job | Ergebnis |
|---|---|---|
| `offline`, 41402168572 | alle neun Jobs wie in 4.7.18 | grün |
| `ci`, 41402168683 | Lizenz-Gate und Netz-Scan; Windows PowerShell 5.1; PowerShell 7; Anforderungs-IDs | grün |
| | Test windows-latest × 3.13 | rot: 5 fehlgeschlagen, 4319 bestanden, 19 übersprungen (4343 Tests) |
| | Test ubuntu-24.04 × 3.12 und × 3.13 | rot: je 5 fehlgeschlagen, 4243 bestanden, 100 übersprungen (4348 Tests) |
| | Test windows-latest × 3.11 und × 3.12, ubuntu-24.04 × 3.11 | beim Mitschreiben noch laufend; nach dem Lead rot an denselben fünf Tests |

Die fünf Tests (auf allen Plattformen dieselben): `tests/unit/test_norm_independence.py::test_yyt2029_mentions_are_known`
(zwei ungeprüfte Zeilen in `test_p6_cross.py`), `tests/rules/test_thresholds_overridable.py::test_builtin_parameter_override_takes_effect[yyt2029-YYT2029-ACQ-001-min_hz:number]`
(`rulepack.placeholder_needs_flag`), `tests/integration/test_report.py::test_placeholder_findings_are_listed_without_verdict`
und `::test_each_finding_row_has_required_fields` (`assert 43 == 44`: Befundzeilen neben dem M14-Block) und
`tests/acceptance/test_zh_review_package.py::test_every_file_with_chinese_text_is_in_the_package` (`yyt2029.yaml` fehlte
im Paket). Alle fünf liegen außerhalb der Dateien der Bereiche: Die Bereiche hatten nur ihre eigenen Tests laufen
lassen. Behoben in `2f2a5a5` (Zeilen in `KNOWN`, der Test lädt den Platzhalter mit dem Schalter, die Befundzeilen ohne
M14, `tools/zh_review_package.py` nimmt jedes Paket unter `src/neurogrid/rulepacks/` auf). Die Linux-Jobs zeigten nur
diese fünf Fehler: Der POSIX-Code des Vaults lief dort grün (Stand vor der Fix-Runde). Die Vorgaben von P9 verlangen
zusätzlich zu den eigenen Tests jeden Test, der eine geänderte Datei liest (u. a. `test_norm_independence`,
`test_docs_*`, `test_zh_review_package`, `test_report*`, `test_thresholds_overridable`,
`test_language_and_wording`) [D: `.local/p9/p9_final.md`].

#### 4.8.8 Review und Fix-Runde (Zweig `p6-fix`)

Ein unabhängiges Review nur mit Lesezugriff auf vault und consent auf `d50158b` (Skripte nur im Scratchpad [NV]) fand
sieben Befunde; `p6-fix` behob alle, je mit Regressionstests, die vorher scheitern und danach bestehen
[D: `.local/p6/fix_decisions.md`]; Einzelheiten in ENTSCHEIDUNGEN A-90 und A-91:

| Nr. | Befund | Commit | Tests |
|---|---|---|---|
| 1 | M14: Der Bericht druckte die genaue kleine Zelle dreimal (Summe des Blocks, Regelzeile, Anhang 6.1; 6.3 zählte ausgenommene Probanden) | `754aef6` | `test_no_m14_cell_of_one_to_four_subjects_can_be_read_from_the_report`, `test_results_consent_only_when_m14_measured_per_subject`, `test_a_published_m14_table_shows_the_passed_subjects_of_each_use`, `test_exceptions_of_m14_rules_are_counted_only`, `test_the_withheld_m14_counts_in_the_pdf` |
| 2 | Ausnahmen einer nicht geladenen M14-Regel zeigten Proband und Begründung in 6.3/6.5 | `09cd05a` | `test_exceptions_of_an_unloaded_m14_rule_are_withheld`, `…_never_reach_the_pdf`, `test_the_built_in_consent_rules_are_known` |
| 3 | `vault log --objects` speicherte Rohdateien mit Glob-Zeichen, nachgestelltem Punkt oder Link im Klartext | `eabdef6` | `test_vault_log_looks_up_the_literal_name_first`, `test_vault_log_refuses_an_object_that_names_a_link` |
| 4 | Das Manifest nannte bei abweichendem `[vault] path` das Protokoll am Standardort; `verify` scheiterte nach jedem read-Ereignis | `8b36697` | `test_the_manifest_leaves_out_the_log_of_every_vault`, `test_check_compares_without_the_log_of_its_vault` |
| 5 | `mkdir(mode=0o700)` gab unter Windows eine eigene, geschützte DACL | `f307754` | `test_init_windows_folders_inherit_the_acls_of_their_parent` |
| 6 | `[vault] purpose`/`approval_ref` leer oder mit Tab: Exit 2 erst nach der Datenarbeit | `16fd7c9` | `test_vault_texts_of_the_toml_are_config_errors_for_every_command` |
| 7 | `report --config` mit toml in einem Unterordner suchte einen anderen Vault als `check` | `9e44134` | `test_report_config_finds_the_vault_of_check` (drei Fälle) |

Zwei vorhandene Erwartungen wurden dabei geändert, weil sie das alte Verhalten festhielten: eine in
`tests/unit/test_provenance.py` (Befund 4) und `errors.vault.text_invalid` → `config.invalid` (Befund 6). Lauf der
betroffenen Dateien: 1037 bestanden, 8 übersprungen (POSIX-Zweige; Datei-Links sind auf diesem Rechner nicht
erlaubt); nach dem Merge `0ffdd90` die Überschneidung der Zweige 168 bestanden, 1 übersprungen [D]. Offen: die neuen
zh-Texte (sechs Schlüssel `report.consent.*`, `errors.vault.object_link`) und zh-Absätze der Doku gehören zur vollen
zh-Runde von P6 vor v0.2.

#### 4.8.9 CI-Stand auf `0ffdd90`

Gepusht am 02.11. 10:42 [G: Reflog von `origin/dev`]; gelesen wie in 4.7.19: ganz grün, `ci` 41422859481 und `offline` 41422859830 (neun Jobs); Testjobs laut Notice-Annotationen: windows-latest Python 3.11 4347 bestanden / 20 übersprungen, 3.12 und 3.13 je 4348 / 19 (von 4367); ubuntu-24.04 Python 3.11, 3.12 und 3.13 je 4271 / 101 (von 4372); 0 Fehler; Abdeckung Kern 93,9–94,0 %, Prüfer 97,1–97,2 % (Grenzen 90 % und 80 %)

#### 4.8.10 Durchlauf von Hand (UF-06, UF-03, NV-F03)

Auf `0ffdd90` ausgeführt [G, 0ffdd90] (Git Bash, im `<Projektordner>`; Fixture `bids_ai_ok` mit Splits: sub-01 bis
sub-04 in train, sub-05 in val, sub-06 in test):
```bash
export PYTHONIOENCODING=utf-8
NG=.venv/Scripts/neurogrid.exe
rm -rf /tmp/p6demo && mkdir -p /tmp/p6demo && cp -r tests/fixtures/synthetic/bids_ai_ok /tmp/p6demo/data
$NG --lang en vault init /tmp/p6demo/data       # Created: .neurogrid/vault, consents.yaml, access.jsonl, access.jsonl.lock; Exit 0
for s in 01 02 03 04 05 06; do
  $NG --lang en vault consent add /tmp/p6demo/data --subject $s --version 1 --date 2026-03-01 \
      --uses training,validation --role data_steward      # je Exit 0, je ein Ereignis consent_manage
done
$NG --lang en vault log /tmp/p6demo/data --action read --objects '**' --purpose "review of the split" --role QA.lead
                                                # "Access event 7 recorded, hash …"; Exit 0
$NG --lang en check /tmp/p6demo/data --as-of 2026-10-11 --out /tmp/p6demo/r1.json   # Exit 1 (CORE-M02-01 ohne dokumentierte Metadaten)
$NG --lang en check /tmp/p6demo/data --as-of 2026-10-11 --out /tmp/p6demo/r2.json
cmp /tmp/p6demo/r1.json /tmp/p6demo/r2.json && echo identisch                       # identisch
$NG --lang en vault log /tmp/p6demo/data --show   # 9 Einträge (6 consent_manage, read, 2 check), Kopf-Hash, "Hash chain: intact."
$NG --lang en vault verify /tmp/p6demo/data       # "The access log is intact.", Kopf-Hinweis, Grenzsatz; Exit 0
```
Beobachtet: Beide `check` geben „Note: no role is set …“ aus (ohne neurogrid.toml keine Rolle; das Ereignis schreibt
`null`); in `r1.json` besteht CORE-M14-01 für 6 Ergebnisse (je Proband die Nutzung seines Splits), CORE-NV03-01 und -02
bestehen, `consent` = `{"subjects": {"training": 4, "validation": 2}}`, `config.consents_sha256` gesetzt; der Kopf-Hash
steht nicht in `r1.json`. `vault verify --expect-head <Kopf-Hash von --show>` endet mit Exit 0.

Weiter mit Konfiguration und Bericht, dann eine geänderte Zeile:
```bash
printf '[vault]\nrole = "data_steward"\npurpose = "pre-check before registration"\n' > /tmp/p6demo/data/.neurogrid/neurogrid.toml
$NG --lang en check /tmp/p6demo/data --as-of 2026-10-11 --out /tmp/p6demo/r3.json        # Exit 1, Ereignis mit Rolle
$NG --lang en report /tmp/p6demo/r3.json --lang en --format html --out /tmp/p6demo/rep \
    --config /tmp/p6demo/data/.neurogrid/neurogrid.toml                                   # Exit 0, Ereignis "report"
sed -i 's/review of the split/review of the plits/' /tmp/p6demo/data/.neurogrid/vault/access.jsonl
$NG --lang en vault verify /tmp/p6demo/data   # "Line 7: entry changed (its hash does not match its content) (likely changed)"; Exit 1
$NG --lang en check /tmp/p6demo/data --as-of 2026-10-11 --out /tmp/p6demo/r4.json
# r4.json: CORE-NV03-01 failed, reason vault.chain_broken, details {"deviations": 1, "first_line": 7, "kind": "hash_mismatch"}
```
`report --config` verlangt eine vorhandene toml (sonst „Configuration file not found.“, Exit 2). Ohne `--config`
schreibt `report` kein Ereignis und das Deckblatt hat keine Zeile des Zugriffsprotokolls. Jeder `vault consent add`
startet einen eigenen Prozess (auf dem Entwicklungsrechner etwa 3 s je Aufruf); für viele Einträge `--from
consents.tsv` nehmen (ein Ereignis für den ganzen Import).

#### 4.8.11 Stand heute (`0ffdd90`) und was zu P6 noch fehlt

Geprüft im Worktree `p6-docs` auf `0ffdd90` mit dieser Doku [G]: `gen_schemas.py --check` „schemas up to date“,
`gen_docs.py --check` „documentation up to date“, `check_matrix_coverage.py` 166/166 („P6: schließt 10 ab, trägt zu 5
bei“), `check_commit_ids.py` „226 commit(s) and 9 phase entr(y/ies) checked, 0 problem(s)“, `ruff format --check .`
„259 files already formatted“; die Prüfbefehle der Doku in 4.8.12.

Offen:
- CI auf `0ffdd90`: ganz grün (`ci` 41422859481, `offline` 41422859830); damit die POSIX-Zweige des Vaults nach der Fix-Runde (flock, Modi 0700/0600 mit
  fchmod, fsync des Ordners) und die Abdeckung je Testjob.
- NV-F03 bleibt `teilweise` bis P8 (Details aus dem Normtext; der Punkt ist kein Eintrag der Auslegungsfragen, A-92).
- zh-Texte: die Kernbegriffe von P6 in der zh-Prüfung von STOPP G1 (FORTSCHRITT), die vollständigen Texte vor v0.2.
- Für STOPP G2 vorgemerkt: A-90..A-92 mit ihren Lesarten (FORTSCHRITT „Für STOPP G2 vorgemerkt“).
- Nicht gemessen: `vault verify` mit 10⁶ Einträgen; keine G1-Abnahme und keine Korpustests auf dem Endstand von P6
  (P6 ändert die Abnahme von G1 nur im M14-Block, `tools/acceptance_g1.py`).
- Nächste Phase: P9 vor P7 und P8 (D-19, D-13); mit dem ersten Commit von P9 geht `dev` auf `1.0.0.dev0`.

#### 4.8.12 Prüfbefehle der Doku von P6

Nach dem Schreiben der fünf Dateien in `docs/umsetzung` (PowerShell, im Worktree):
```powershell
$PY = ".\.venv\Scripts\python.exe"
$env:NEUROGRID_NOTICES_WHEELS = "<Projektordner>\.local\notices-wheels"
& $PY -m pytest -q -p no:cacheprovider tests\docs\test_docs_sync.py tests\docs\test_licensing.py tests\packaging\test_workflows.py
& $PY tools\check_matrix_coverage.py
& $PY tools\check_commit_ids.py
.\.venv\Scripts\ruff.exe format --check .    # formatiert auch Python-Blöcke in Markdown
```

### 4.9 P9 – Register, Neueinwilligung, Export und Nachweismappe, diff und CI-Integration (2026-11-02; Stand 5596a8d)

Matrix: schließt NV-F04, NV-F05, NV-F06, NV-F07, NG-F15, CLI-07, CLI-08, CON-02, UF-02, UF-03, UF-06 ab; REP-08 bleibt
`nicht verifiziert` bis zur Sichtprüfung einer Nachweismappe, NG-F16 und V-03 bleiben `teilweise` (NV-F03 bis P8; der
echte Lauf auf eigenem Runner vor v1.0, ISO-Abbildung in P10). Im Phasenplan führt P9 13 abschließende Zeilen und
einen Beitrag (`check_matrix_coverage.py` „P9: schließt 13 ab, trägt zu 1 bei“) [G]. P9 lief vor P7 und P8, weil G-A
und G-B nicht erfüllt sind (D-13, D-19). Grundlage: die Vorgaben des Leads (privat: `.local/p9/p9_decisions_draft.md`,
`.local/p9/p9_final.md`, die Schnittstelle des Freeze `.local/p9/freeze_api.md`, die Berichte der Bereiche
`.local/p9/area_{a,b,c,d}_report.md`, die Vorgaben dieser Doku `.local/p9/docs_brief.md`), D-17, D-19; Annahmen A-93
bis A-99. Keine neue Abhängigkeit, kein Download: `pyproject.toml`, `uv.lock` und `license-gate/` sind seit `0ffdd90`
unverändert [G: `git diff --stat 0ffdd90 5596a8d -- pyproject.toml uv.lock license-gate`].

#### 4.9.1 Vorgehen

| Datum | Commit | Schritt |
|---|---|---|
| 02.11. 10:55 | `8e9575f` (Zweig `p9-registers`, auf `0ffdd90`) | Start: Version `1.0.0.dev0` (4.9.2) |
| 02.11. 11:36 | `c1f5129` (`dev`) | Doku von P6 (`7e6e6aa`) auf `dev` |
| 02.11. 11:39 – 11:56 | Zweig `p9-compare` (auf `0ffdd90`): `affd0a8`, `49dd657` | Vergleich und CI-Integration (4.9.6) |
| 02.11. 11:46 | `159539d` (`p9-registers`) | Schnittstellen-Freeze (4.9.3) |
| 02.11. 12:12 – 13:16 | Zweig `p9-package` (auf `159539d`): `fc9ecbd`, `364e2f1`, `eba51e5`, `9e427dd` | Kern-PDF, Nachweismappe, `vault export` (4.9.5) |
| 02.11. 12:14 – 13:18 | Zweig `p9-reconsent` (auf `159539d`): `5ea36be`, `495412d`, `6148d96` | Neueinwilligung (4.9.4) |
| 02.11. 12:58 | `952dfe6` (`p9-registers`) | Regeln, Warnungen und Doku der Register (4.9.3) |
| 02.11. 13:00 – 13:28 | Merges `c00475b` (Register), `cd08106` (Vergleich), dazu `851031c`, Merge `74db563` (Paket), dazu `9597441`, Merge `cc7bc9c` (Neueinwilligung) | Merge mit den Entscheidungen des Leads (4.9.7) |
| 02.11. 13:39 | `5596a8d` | Querschnittstests (4.9.7); CI auf `5596a8d` (4.9.8) |
| 02.11. | Zweig `p9-docs` | diese Doku |

Zeiten sind Autorzeiten der Commits (`git log --format='%h %ad' --date=format:'%d.%m. %H:%M' 0ffdd90..5596a8d`) [G].
Die Bereiche arbeiteten in Worktrees wie in 3.5 (`git worktree add ".claude\worktrees\p9-<bereich>" -b
p9-<bereich> <basis>`) [R]; nach den Merges wurden die Worktrees von P6 und P9 nach einer Prüfung auf Reparse-Punkte
(keine gefunden) entfernt und ihre Zweige mit `git branch -d` gelöscht [D: `.local/p9/docs_brief.md`].

#### 4.9.2 Start und Version (`8e9575f`; V-02, V-03)

- `src/neurogrid/__init__.py`: `__version__ = "1.0.0.dev0"`; die Installationsseiten nennen diese Version mit der
  unveränderten Präfixgrenze 148/101 [D: Commit-Meldung `8e9575f`]. `core.yaml` geht im Freeze auf `1.0.0`.
- Nach D-19 entstehen v0.1.0 aus `c4f240a` und ein v0.2.0, falls gewünscht, aus dem Endstand von P6 (`0ffdd90`), je
  auf einem Release-Zweig; `tools/release_check.py` lehnt Entwicklungsversionen ab (A-87).

#### 4.9.3 Bereich Register (A-93, A-94; NV-F04, NV-F05, CLI-08, DM-09, ARC-01)

**Freeze `159539d`** (erster Commit des Bereichs, die Schnittstelle für Neueinwilligung und Paket, ohne Platzhalter)
[D: `.local/p9/freeze_api.md`]: `model/_registers.py` (`parse_register` mit Bytegrenze, BOM, `load_yaml` des Kerns
ohne Aliase und doppelte Schlüssel, `RegisterSpec`, `RegisterDate`, `FormatVersion`), `model/roles.py`,
`model/retention.py` (`plus_three_years`, `RETENTION_OBJECTS`, `REQUIRED`), `model/risks.py`; `vault/store.py`
(`ROLES_FILE`, `RISKS_FILE`, `RETENTION_FILE`, `PIA_FOLDER`, `PIA_FILES`, die Vorlagen, Zustand `link` für die neuen
Teile, `init_vault` mit den neuen Teilen, `LoadedRegister`, `read_vault_file`), die Leser `vault/roles.py`,
`vault/retention.py`, `vault/risks.py` (`load_for_check`), `vault/templates/pia.zh.md` und `pia.en.md`; Felder
`roles`, `retention`, `risks` von CheckContext und `config.*_sha256`; `pipeline._load_vault_files`; core `1.0.0`;
Schemas `roles`, `retention`, `risks`; Tests `tests/unit/test_registers_model.py`, `tests/unit/vault/test_registers.py`,
`tests/integration/test_registers_pipeline.py`, Hunks in `test_store`, `test_architecture`,
`test_language_and_wording` (die PIA-Dateien als einzige Ausnahme von `law_article`), `test_cli_vault` und
`test_p6_cross` (Vault-Dateien rekursiv verglichen, `pia/` ist ein Ordner); `tools/zh_review_package.py` nimmt
`pia.zh.md` auf.

**Nach dem Freeze `952dfe6`** [D: Bericht des Bereichs]: `vault/roles.py` (`Permission`, `covers`, `permission`,
`role_warning`, `permission_at`, `identifying_count`), `vault/pia.py` (`read_pia`), `vault/ledger.py` (`first_entry`),
`checks/access.py` (CORE-NV04-01, `event_cut`, Hinweise), `checks/retention.py` (neu: CORE-NV05-01 bis -03, Hinweis
der Erinnerung), `core.yaml` (vier Regeln), Pipeline und CLI (`PendingAccess.permission`/`.role_warning`,
`VaultLogRun.role_warning`, Warnungen von check, convert, report `--config`, vault log und vault consent add,
`cli.vault.init.templates_hint`), Bericht (`roles_details`, `retention_details`), Doku en/zh (`vault.md` mit
`#roles`, `#retention`, `#pia`, `#risks` nur Format, `#checks`; `metrics.md` `#NV04`, `#NV05`; `commands.md`;
`reference/outputs.md`; `data-model.md` Role und RetentionItem; `configuration.md#files`; `limitations.md`;
`privacy.md`; `docs/_data` mit Prüfungen und Herkunft der Regeln).

**Prüfen** (PowerShell):
```powershell
$PY = ".\.venv\Scripts\python.exe"
$env:NEUROGRID_REQUIRE_PDF = "1"; $env:PYTHONWARNDEFAULTENCODING = "1"
& $PY tools\gen_schemas.py --check   # "schemas up to date": 13 Schemas seit P9
& $PY -m pytest -q -p no:cacheprovider tests\unit\test_registers_model.py tests\unit\vault tests\integration\test_registers_pipeline.py tests\rules\test_builtin_rules.py tests\rules\test_thresholds_overridable.py tests\cli\test_cli_vault.py tests\docs\test_docs_vault.py tests\unit\test_architecture.py tests\unit\test_language_and_wording.py
```
Ergebnis [D: Bericht des Bereichs]: Stapel unit, rules, acceptance und packaging_texts 3240 bestanden, 23 übersprungen,
1 fehlgeschlagen (die Markierung der zh-Vorlage in `vault/pia.py`, behoben: als `\u`-Escape, weil das zh-Prüfpaket
jede Datei mit chinesischem Text verlangt); Integration von Vault, Einwilligung, check und Bericht (9 Dateien)
300 bestanden, 3 übersprungen, 3 fehlgeschlagen (behoben: Datei der not_checkable-Befunde von CORE-NV04-01 ohne
Register ist `.neurogrid/vault/roles.yaml`; geänderte Erwartung in `test_report_p5`, vier Regeln mehr in der Phase
access; geänderter Aufbau in `test_consent_pipeline` mit gefüllter `retention.yaml` und einer PIA-Datei); übrige
Integration 450/1; cli, docs und workflows 462/3; Wiederholungen grün (298/3, 415/4, 24, 151/2). `check_commit_ids.py
--since 0ffdd90`: 0 Probleme.

**Nachbaufakten** [D]: Ein Vault aus P6 bekommt Register und PIA-Dateien mit einem `vault init`. Jeder `check` auf
einem frischen `vault init` zeigt drei Warnungen von NV05 und NV04 grau, bis die Register gefüllt sind. CORE-NV05-03
ist mit `[rules."CORE-NV05-03".params] days` überschreibbar. `glob.match("*", "**")` ist wahr; deshalb deckt
`vault.roles.covers` ein Objekt `**` nur mit dem Muster `**`.

**Fallen** [D]: Der Bereich Neueinwilligung schrieb ebenfalls `vault.md#risks` und Risk in `data-model.md`; beim
Merge bleibt je eines (4.9.7). `tests/docs/test_docs_vault.py::test_register_examples_are_the_templates_examples_and_parse`
verlangt, dass jedes Beispiel in `vault.md` dem auskommentierten Beispiel seiner Vorlage gleicht.

#### 4.9.4 Bereich Neueinwilligung (A-95; NV-F06, NG-F16, NG-F13)

**Gebaut** (`5ea36be`, `495412d`, `6148d96`, auf dem Freeze) [D: Bericht des Bereichs]: `vault.risks.judged` und
`future` (`LoadedRisks.judged`/`.future`); CORE-M14-02 `consent.reconsent` in `checks/consent.py` und `core.yaml`;
`model/results.py` (`ReconsentRisk`, `ReconsentSummary`, Feld `reconsent`) mit `results.schema.json`;
`report/tables.py` (`consent_rules` nach dem Präfix, Zeilen je Risiko), `report/render.py` und `_findings.html.j2`
(Verweiszeile, Abschnitt am Ende von Abschnitt 3); `cli.check.reconsent`; Sprachtabellen zh/en/de; erzeugte Doku;
Regelfälle (`tests/rules/reconsent_setups.py`); Doku en/zh (`vault.md#risks` mit markiertem Beispiel, `metrics.md#M14`,
Abschnitt in `report.md`, Risk in `data-model.md`, je eine Zeile in `privacy.md` und `limitations.md`). Geändert, ohne
eine Prüfung zu streichen: `tools/acceptance_g1.py` (`_consent_block_problems` kennt Zeile und Abschnitt von M14-02 und
lehnt einen genannten Probanden weiter ab), `test_report_p5` (`test_findings_grouped…` mit der Verweiszeile,
`test_access_phase_is_grey_without_rules` mit CORE-M14-02), `tests/acceptance/test_g1_checks.py::test_finding_rows_accept_the_report`
(zusammengefasst = Prüfungen `consent.*`).

**Prüfen** (PowerShell):
```powershell
$PY = ".\.venv\Scripts\python.exe"
$env:NEUROGRID_REQUIRE_PDF = "1"; $env:PYTHONWARNDEFAULTENCODING = "1"
& $PY -m pytest -q -p no:cacheprovider tests\unit\vault\test_risks.py tests\integration\test_reconsent_pipeline.py tests\rules\test_builtin_rules.py tests\integration\test_report_p5.py tests\acceptance\test_g1_checks.py tests\docs\test_docs_vault.py
```
Ergebnis [D: Bericht des Bereichs; 66 Dateien, die geänderte Dateien lesen]: acceptance 64 bestanden, 2 übersprungen;
cli, docs, packaging und rules 761/3; integration 690/3; unit 1469/6; 0 Fehler.

**Nachbaufakten** [D]: `REASONS` in `checks/consent.py` bleiben die Literale `consent.*` (ein Test vergleicht sie), die
Gründe von M14-02 stehen in `RECONSENT_REASONS`; `SPECS[0]` bleibt `consent.covered`. Im Renderer bekommen die Regeln
von `consent.covered` die Blöcke von M14-01, die von `consent.reconsent` die Verweiszeile; jedes Gruppen-Dict trägt den
Schlüssel `reconsent` (Jinja2 mit StrictUndefined). Der Regelteil des neuen Abschnitts nutzt keine Klasse
`rule-group` und kein verschachteltes `div` (Regex des G1-Orakels). `cli.py` importiert
`report.tables.reconsent_subjects`.

#### 4.9.5 Bereich Paket (A-96, A-99; NV-F07, REP-08, CON-02, CLI-08, V-03)

**Gebaut** (`fc9ecbd`, `364e2f1`, `eba51e5`, `9e427dd`, auf dem Freeze) [D: Bericht des Bereichs]: `kernel/pdf.py`
(`PdfExpect.every_page_any`, `merge_pdfs`, `page_count`, `document_info`, `reference_date`); `dossier.py` und
`report/templates/dossier.html.j2` (mit Ergänzung des CSS); `report/identify.py`; `report/output.py` (`FORMATS` mit
dossier, `write_reports`); `vault/export.py`, `model/export.py` (ExportIndex), `schemas/export_index.schema.json`,
`pipeline.run_vault_export`, CLI `vault export` und der Hunk `report --format`; `errors.export.*`,
`cli.vault.export.*`, `cli.help.vault.export.*`, `report.dossier.*`; Doku en/zh (`commands.md` mit `report --format
dossier` und `#vault-export`, `vault.md` mit Zeile der Übersicht, Zeile der Ereignisse und `#export` vor `#limits`,
`report.md#dossier`, `reference/outputs.md` mit `#export-zip`, `privacy.md`, `limitations.md`). `9e427dd` lässt den
Shell-Test des Exports auch unter PowerShell 7 laufen.

**Prüfen** (PowerShell):
```powershell
$PY = ".\.venv\Scripts\python.exe"
$env:NEUROGRID_REQUIRE_PDF = "1"; $env:PYTHONWARNDEFAULTENCODING = "1"
& $PY tools\install_pdf_browser.py --check
& $PY -m pytest -q -p no:cacheprovider tests\unit\test_pdf_unit.py tests\unit\test_report_identify.py tests\unit\vault\test_export.py tests\integration\test_export_pipeline.py tests\integration\test_dossier.py tests\cli\test_cli_export.py
```
Ergebnis [D: Bericht des Bereichs]: pdf_unit und architecture 89; report_pdf mit cli 65; dossier 6; identify, Wortwahl,
Tabellen, Norm, Architektur, Texte von P2, Hilfe, cli, zh-Paket, Berichte und Nachweise 327; Export im Vault 15/1;
export_pipeline 7; cli_export 6/1 (kein pwsh lokal); Doku (sync, Wortwahl, Vault, Bau) 142; docs_browser, licensing und
notices 103/3; Vault, Einwilligung, Querschnitt P6, Register und packaging 565/13; coverage_gates 5. Abdeckung lokal:
`vault/export.py` 85 % (Zweige für Wettläufe des Betriebssystems), `report/identify.py` 98 %, `model/export.py` 100 %.

**Gemessen** [D]: pypdf 6.21.2 `add_page` mit echten Chromium-PDFs: zh 18 Seiten 201 274 B und en 20 Seiten 123 321 B
ergeben 38 Seiten 324 173 B in 0,06–0,08 s; bytegleich in einem Prozess und mit `PYTHONHASHSEED` 1 und 2; Trailer
`/Info /Root /Size`, keine `/ID`, `%PDF-1.4`. Nachweismappe von `bids_ai_ok` mit core: 40 Seiten (2 + 19 + 19),
373 229 B, etwa 21 s je Bau, bytegleich in zwei frischen Prozessen und im Test (`--lang zh` gegen `en` mit html); mit
`--config` unterscheiden sich zwei Bauten mit Absicht (das eigene Ereignis des Berichts rückt den Kopf weiter). Das
Erkennen einer Mappe von 40 Seiten (QA-Gate) dauert etwa 4 s.

**Fallen** [D]: pypdf `append` legt ein leeres `/Outlines` an, deshalb `add_page`. Python 3.11/3.12 haben keine
öffentliche Kompressionsstufe je ZIP-Eintrag; der Export nutzt die Standardstufe von zlib (6). Lokal übersprungen:
die Tests mit pwsh und mit Datei-Links (auf diesem Rechner nicht erlaubt). Die Prüfung des Exports liest das
Protokoll nach dem Streamen über den Namen (Grenze in `limitations.md`).

#### 4.9.6 Bereich Vergleich (A-97, A-98; NG-F15, CLI-07, UF-02, V-03, CON-02)

**Gebaut** (`affd0a8`, `49dd657`, auf `0ffdd90`; `__version__` unberührt) [D: Bericht des Bereichs]: `diff.py`,
`model/diff.py` (DiffResult), `schemas/diff.schema.json`, CLI `diff`; `action.yml`, `ci-templates/gitlab-ci.yml`,
`.github/workflows/ci-integration.yml`, Nutzerseite `docs/<lang>/ci.md` (Navigation „CI integration: CI 集成“).
Gemeinsame Hunks: `tests/packaging/test_workflows.py` (`NAMES` und `ci-integration`; `uses: ./` nur dort und nur mit
`action.yml`), `tests/docs/test_docs_sync.py` (`EXIT_CODES` von `diff` {0, 1, 2}, Anker `diff-json` gegen
`diff.schema.json`), `tests/cli/test_cli_help_i18n.py`, `tests/docs/test_docs_build.py` (17 → 18 Seiten),
`tools/gen_schemas.py`, `tools/zh_review_package.py` (`action.yml`, `ci-templates/gitlab-ci.yml`, `docs/en/ci.md`),
`REUSE.toml` (`action.yml` und `ci-templates/**` unter Apache-2.0), `mkdocs.yml`, Sprachtabellen, Doku en/zh
(`commands.md#diff`, `reference/outputs.md#diff-json`, `data-model.md#diff-result`, `privacy.md`,
`limitations.md#ci`, `ci.md`).

**Prüfen** (PowerShell):
```powershell
$PY = ".\.venv\Scripts\python.exe"
& $PY -m pytest -q -p no:cacheprovider tests\unit\test_diff.py tests\cli\test_cli_diff.py tests\packaging\test_ci_integration.py tests\packaging\test_workflows.py tests\packaging\test_env_example.py tests\docs\test_docs_sync.py tests\cli\test_cli_help_i18n.py
```
Ergebnis [D: Bericht des Bereichs]: tests/cli und tests/unit 2860 bestanden, 22 übersprungen; `test_ci_integration.py`
51; workflows, env_example und bundle_lock 56; Doku, Wortwahl, Lizenzen, Notices, Vault, zh-Paket, Sprache, Norm, Texte
von P2 und Datenmodell 356/3; `test_docs_build.py` 53 (MkDocs strikt mit `ci.md`); `test_docs_browser.py` 4.

**Nachbaufakten** [D]: `test_ci_integration.py` bildet die Runner-Befehle von GitHub nach: `bash --noprofile --norc
-eo pipefail <datei>`; `powershell -command ". '<datei>'"` mit `$ErrorActionPreference='stop'` und angehängtem Exit
von `LASTEXITCODE`; die Formen `inputs.X`, `runner.environment`, `steps.ID.outputs.X` verbunden mit `||`; Ausgaben aus
`GITHUB_OUTPUT`. Die GitLab-Skripte laufen mit `sh -e` (unter Windows `sh.exe` von Git Bash, mit `C:/`-Pfaden);
PowerShell führt eine Datei mit BOM über `-File` aus. `ci-integration.yml` pinnt actions/checkout `3d3c42e5` (v7.0.1)
und astral-sh/setup-uv `07a047e6` (v10.3.2), uv 0.13.0, Python 3.12; Starter `.venv/bin/neurogrid` bzw.
`.venv/Scripts/neurogrid.exe`.

**Fallen** [D]: Windows PowerShell 5.1 liest UTF-8 ohne BOM als ANSI; deshalb sind die Skripte der Action ASCII und
alle zh/en-Texte kommen über env. Unter `powershell -command` des Runners wird jeder Exit ungleich 0 zu 1 (gemessen).
`test_ci_integration.py` verlängert jeden Windows-Testjob um etwa 3,5 min. Die PowerShell-7-Variante von
`test_cli_diff.py` läuft nur in der CI.

#### 4.9.7 Merge, Entscheidungen des Leads, Querschnittstests

```powershell
$PY = ".\.venv\Scripts\python.exe"
git merge --no-ff p9-registers     # c00475b; bringt 8e9575f und den Freeze 159539d mit
git merge --no-ff p9-compare       # cd08106
# 851031c: .env.example und test_env_example decken action.yml und ci-templates/ ab
git merge --no-ff p9-package       # 74db563
# 9597441: vault export warnt über das Rollenregister
git merge --no-ff p9-reconsent     # cc7bc9c
& $PY tools\gen_schemas.py --check
& $PY tools\gen_docs.py --check
```
[R: Reihenfolge und Commits aus `git log --graph 0ffdd90..5596a8d`; die Befehle selbst sind nicht protokolliert.]

Entscheidungen des Leads beim Merge [D: `.local/p9/docs_brief.md`; Einzelheiten in ENTSCHEIDUNGEN „Übergreifend“,
A-95, A-96, A-98]: Konflikte als Vereinigung (Sprachtabellen, Doku, `gen_schemas.py`, Regel-Setups), erzeugte
Dateien neu erzeugt; ein Abschnitt `vault.md#risks` (Text der Neueinwilligung, markiertes Beispiel `risks-yaml` der
Register, Grenze „1,000 risks and 1,000,000 bytes“; `tests/unit/vault/test_risks.py` liest die Markierung); `vault
export` warnt über das Rollenregister (`9597441`); die Warnung „PIA unbearbeitet“ bleibt örtlich; `roles.yaml` und
die PIA-Dateien werden gepackt, wie sie geschrieben sind; veraltete Sätze in `limitations.md` und `index.md`; Nennungen
der Norm in `KNOWN` von `test_norm_independence`; `.env.example` mit den zwölf Job-Variablen der GitLab-Vorlage
(`851031c`); die Abweichung der Neueinwilligung vom Entwurf zur Freigabe mit A-95; „Wert von `runner.environment`
nicht verifiziert“ bleibt in den Lücken.

Querschnittstests `5596a8d`, `tests/integration/test_p9_cross.py` (neun Tests) [G: Quelltext]:
`test_uf02_scan_convert_check_diff` (Rohordner → `scan` → `convert --to bids` → `check` → `manifest` → geänderte Datei →
`check` Exit 1 → `diff --format json` Exit 1 mit genau dem neuen Befund CORE-M13-02 `README.md`, behoben CORE-M13-01,
entfallen CORE-M13-02 `dataset`; umgekehrt Exit 0), `test_uf06_init_consent_add_log_verify_export` (Ereignisse
consent_manage, read, read, check, export; das archivierte Protokoll gleicht dem Protokoll bis zum Ereignis `export`,
`index.json` nennt dessen Hash als Kopf, `vault verify --expect-head` Exit 0), `test_uf03_build_check_consent_export`
(Risiko R-1 verlangt Version 2: CORE-M14-02 verletzt für sub-01 bis sub-04, der Bericht hält die Zahlen zurück, das ZIP
ohne `consents.yaml`, `risks.yaml`, `retention.yaml` und results.json), `test_dod_two_checks_full_vault_byte_identical[1]`
und `[4]` (Einwilligungen, Rollen, Risiken, Aufbewahrung, Folgenabschätzung und Protokoll; zwei Ereignisse mehr,
results.json bytegleich, alle vier `*_sha256` gesetzt), `test_privacy_planted_identifiers_in_p9_outputs`,
`test_consent_namespace_agrees_in_report_and_diff`, `test_dossier_as_export_report_part` (Marker `pdf`),
`test_five_stages_v1`. Festgestellt [D]: `vault log` und `manifest` schreiben im Vault am Standardort Ereignisse
`read`; `bids_ai_ok` hat keine `neurogrid.toml` (die Tests schreiben `documented.toml` wie in P6); `report` hat keine
Option `--role`.

Lokale Läufe nach allen vier Merges [D: `.local/p9/docs_brief.md`]: Integration 243 bestanden, 1 übersprungen; unit,
docs, cli und rules 1315 bestanden, 8 übersprungen; Querschnittstests 9 bestanden; `ruff check .`, `ruff format
--check .`, `mypy src/neurogrid tools`, `mypy --strict src/neurogrid/kernel`, `gen_schemas.py --check` und
`gen_docs.py --check` sauber. Volle Suite: nur in der CI.

#### 4.9.8 CI-Stand auf `5596a8d`

Alle drei Läufe abgeschlossen, Ergebnis success (02.11.2026) [D: `.local/p9/docs_brief.md`]:

| Workflow / Lauf | Ergebnis |
|---|---|
| `ci`, 41447040471 | grün; Testjobs laut Notice-Annotationen: windows-latest Python 3.11 4821 bestanden / 20 übersprungen, 3.12 und 3.13 je 4822 / 19 (von 4841); ubuntu-24.04 Python 3.11, 3.12 und 3.13 je 4721 / 125 (von 4846); 0 Fehler; Abdeckung Kern 94,3–94,4 %, Prüfer 97,0–97,1 % (Grenzen 90 % und 80 %) |
| `offline`, 41447040492 | grün: beide Bündel, Reinräume ubuntu 22.04/24.04 und debian:12-slim, Windows unter powershell und pwsh, glibc 2.27 mit Exit 2 abgelehnt, strace-Lauf, PDF in debian:12-slim |
| `ci-integration`, 41447040527 | grün: abgelehnt auf den GitHub-gehosteten Runnern ubuntu-24.04 und windows-latest; check, report und diff mit allow-hosted-runner auf beiden, der Schritt mit fail-on errors scheiterte wie vorgesehen; Job auf eigenem Runner übersprungen |

Schon auf `851031c` lief `ci-integration` 41442891483 so (abgelehnt auf beiden gehosteten Runnern, mit dem Schalter
check, report und diff, eigener Runner übersprungen). Die Ablehnung belegt den Schutz, nicht den Wert von
`runner.environment` (auch ein leerer Wert lehnt ab).

#### 4.9.9 Stand heute (`5596a8d`) und was zu P9 noch fehlt

Geprüft im Worktree `p9-docs` auf `5596a8d` mit dieser Doku, vor ihrem Commit [G]: `gen_schemas.py --check` „schemas
up to date“, `gen_docs.py --check` „documentation up to date“, `check_matrix_coverage.py` 166/166 („P9: schließt 13
ab, trägt zu 1 bei“), `check_commit_ids.py --since c1f5129` „15 commit(s) and 10 phase entr(y/ies) checked, 0
problem(s)“, `ruff check .` „All checks passed!“, `ruff format --check .` „296 files already formatted“; die
Prüfbefehle der Doku in 4.9.10: 146 bestanden; die übrigen Testdateien, die „umsetzung“ nennen und den Ordner auslassen
(`test_zh_review_package.py`, `test_docs_build.py`, `test_docs_wording.py`, `test_release_check.py`,
`test_language_and_wording.py`, `test_norm_independence.py`): 177 bestanden in 3:03 min (`PYTHONWARNDEFAULTENCODING=1`).

Offen:
- REP-08: Sichtprüfung einer Nachweismappe durch den Projektverantwortlichen.
- V-03: der echte Lauf von `ci-integration.yml` auf einem eigenen Runner vor v1.0 (D-19); der Wert von
  `runner.environment`; die GitLab-Vorlage auf GitLab; die Abbildung ISO/IEC TS 27571 (P10, G-C).
- NV-F03 und damit NG-F16 bleiben `teilweise` bis P8 (Details aus dem Normtext).
- zh-Texte von P9: die Kernbegriffe jetzt, die vollständigen Texte vor dem Release von v1.0 (FORTSCHRITT „Für STOPP G2
  vorgemerkt“).
- Juristische Prüfung der PIA-Vorlage vor der ersten echten Verwendung (D-19).
- Für STOPP G2 vorgemerkt: A-93 bis A-99, darunter die Abweichung der Neueinwilligung vom Entwurf (A-95).
- Nicht gemessen: die Laufzeit mit etwa 1 000 Risiken; kein Durchlauf von Hand wie in 4.8.10 (die Abläufe belegen die
  Querschnittstests 4.9.7); keine G1-Abnahme und keine Korpustests auf dem Endstand von P9.
- Nächste Phase: P11 vor P10 (G-C fehlt); P7, P8 und P10 warten auf die Normtexte.

#### 4.9.10 Prüfbefehle der Doku von P9

Nach dem Schreiben der fünf Dateien in `docs/umsetzung` (PowerShell, im Worktree; die Testdateien, die
`docs/umsetzung` lesen, dazu die beiden Tests, die die Werkzeuge über die Matrix und FORTSCHRITT laufen lassen):
```powershell
$PY = ".\.venv\Scripts\python.exe"
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .    # formatiert auch Python-Blöcke in Markdown
& $PY tools\check_matrix_coverage.py
& $PY tools\check_commit_ids.py --since c1f5129
& $PY -m pytest -q -p no:cacheprovider tests\docs\test_docs_sync.py tests\docs\test_licensing.py tests\packaging\test_packaging_texts.py tests\packaging\test_workflows.py tests\unit\test_architecture.py::test_matrix_coverage tests\unit\test_small_units.py::test_commit_message_cleanup
```

### 4.10 P11 – NeuroArena (2026-11-02 bis 11-09)

Matrix: NG-F17 und NA-01 bis NA-05 (DoD in KONZEPT 6: zwei volle Läufe mit gleichen Zahlen, Kurve für beide Decoder,
eigenes Lizenz-Gate grün). P11 lief vor P10, weil G-C fehlt. Grundlage: die Vorlage des Leads (privat:
`.local/p11/p11_decisions_draft.md`), die Antworten des Projektverantwortlichen (D-20, `.local/p11/p11_final.md`),
der Vertrag der Bereiche (`.local/p11/freeze_api.md`); Annahmen A-100 bis A-110. Das Paket `src/neurogrid/`, sein
`pyproject.toml` und sein `uv.lock` bleiben unverändert [G: `git diff --stat 5596a8d b5e4472 -- src pyproject.toml
uv.lock`].

#### 4.10.1 Vorgehen

| Schritt | Commits | Inhalt |
|---|---|---|
| Gerüst | `74ce4aa`, `9c0556f`, `80a3c5b` (Zweig `p11-scaffold`) | Forschungsprojekt mit Lock, eingefrorene Schnittstellen, Gate `--target research`, `research.yml` |
| Gate-Ausnahmen | `99a8c06` | debugpy und Intel OpenMP nach der Antwort von D-20 |
| Bereich B | Zweig `p11-data`: `c6d6bad`, `ac62bff`; Merge `519be71` | Datensätze, Verschlechterung, FIF-Export, Aufruf von NeuroGrid, Qualitätsstufe, Synthetik |
| Bereich C | Zweig `p11-eval`: `433e21b`, `38ad106`, `83ca05e`; Merge `3146cc0` | Determinismus, Decoder, Auswertung, CSV, Runner, `compare_runs` |
| Eingabeskala | `29cfc47` | EEGNet ×1e6 statt ×1000 (A-105) |
| auf `dev` | `a8451e0` | Gerüst, B und C für die CI |
| Bereich D | Zweig `p11-report`: `942651c`, dazu `7fed448` (torchaudio aus dem CPU-Index), `720980a` (Wortlaut der Grenzen); Merge `b5e4472` | Bericht en/zh, Abbildungen, `results/`, Notebook |

Die Bereiche arbeiteten in Worktrees wie in 3.5, jeweils mit eigener Forschungsumgebung (1.4). Nach den Merges wurden
die Worktrees nach einer Prüfung auf Reparse-Punkte (keine gefunden) entfernt; der Rest des Gerüst-Worktrees (Pfade
über 260 Zeichen) mit `cmd /c 'rmdir /s /q "\\?\<voller Pfad>"'` [R].

#### 4.10.2 Daten

Lizenz und Größe jedes Datensatzes wurden vor dem Laden an der Download-Quelle geprüft (D-20). Laden einmal und
nacheinander in `.local/arena/mne_data` (etwa 10,2 GB; 255 Dateien nach dem Laden [G]):
```powershell
uv run --no-sync --project research/neuroarena python -c "from neuroarena import datasets; datasets.configure_storage(); [datasets.fetch(spec) for spec in datasets.DATASETS.values()]"
```
`configure_storage` setzt `MOABB_DOWNLOAD_PROVIDER=upstream`; ohne das lädt moabb 1.7.2 von Spiegeln (A-100). Cho2017
kommt von GigaDB (Webseite für automatischen Abruf nicht lesbar, die Dateien selbst schon).

#### 4.10.3 Läufe

Aus dem Checkout, in dem `.local/arena/` liegt (die Pfade hängen an der editierbaren Installation), mit uv auf PATH
oder in `UV` (A-101):
```powershell
uv run --project research/neuroarena --locked python -m neuroarena.runner --run-id pilot-1 --mode pilot --processes 10 --neurogrid-jobs 6
uv run --project research/neuroarena --locked python -m neuroarena.runner --run-id full-1 --mode full --processes 12 --neurogrid-jobs 6
uv run --project research/neuroarena --locked python -m neuroarena.runner --run-id full-2 --mode full --processes 12 --neurogrid-jobs 6
uv run --no-sync --project research/neuroarena python -m neuroarena.report publish full-1 full-2
uv run --no-sync --project research/neuroarena python -m neuroarena.report render
```
Der Runner ist fortsetzbar: Ein abgebrochener Lauf wird mit derselben Run-ID und derselben Konfiguration neu
gestartet und überspringt fertige Einheiten. `publish` gibt Exit 1, wenn die Läufe verschieden sind; die Dateien sind
dann trotzdem geschrieben und `run_compare.json` nennt die Unterschiede.

#### 4.10.4 Lizenz-Gate und CI

```powershell
& $PY tools\licenses.py --target research
& $PY tools\licenses.py --target research --components --download
```
In `research.yml` brach der erste Lauf auf `a8451e0` in den Unit-Tests ab: Das Linux-Wheel von torchaudio auf PyPI
linkt gegen CUDA (`libcudart.so.13`, `libtorch_cuda.so`; gelesen aus den Bibliotheken des Wheels [G]) und lädt neben
`torch 2.15.0+cpu` nicht, braindecode importiert torchaudio. Behoben in `7fed448`: torchaudio 2.11.1 als direkte
Abhängigkeit aus dem CPU-Index.

#### 4.10.5 Tests

```powershell
cd research\neuroarena
uv run --no-sync pytest -q -m "not smoke"
uv run --no-sync pytest -q -m smoke     # braucht uv für die Kommandozeile von NeuroGrid
```

#### 4.10.6 Verlauf der vollen Läufe

Ein voller Lauf rechnet auf dem Rechner aus 1.1 mehr als 40 h. Er muss deshalb unabhängig von der Sitzung laufen, aus
der er gestartet wird: Prozesse, die als Kinder einer Sitzung der Claude-App laufen, enden mit deren Neustart (so am
04.11. 08:05). Die Claude-App für Windows ist ein MSIX-Paket; uv und die von uv verwaltete Python-Installation liegen
unter `AppData\Roaming` nur in dessen virtueller Sicht. Abgekoppelt gestartet wurde deshalb eine PowerShell-Datei mit
den beiden Runner-Aufrufen aus 4.10.3 und einer Statusdatei je Start und Ende [R]:
```powershell
Invoke-CommandInDesktopPackage -PackageFamilyName "<Paketfamilie der App>" -AppId "Claude" -Command "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" -Args "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"<Skript>`"" -PreventBreakaway
```
Außerhalb der App reicht jede Shell, die nicht an einer Sitzung hängt. Weitere Fallen: Windows PowerShell 5.1
schreibt `*>`-Umleitungen als UTF-16 LE mit BOM, und `$ErrorActionPreference = "Stop"` macht aus den
Fortschrittszeilen des Runners auf stderr Fehler. Den Energiesparmodus nicht zulassen: Nach dem modernen Standby lief die
CPU unter Last mit etwa 12 % der Nennleistung (Zähler `\Prozessorinformationen(_Total)\% Prozessorleistung`, sonst
etwa 75 % im Energieschema des Herstellers) bis zum nächsten Neustart.

| Lauf | Start | Ende | Anläufe | Einheiten | Summe der Einheiten |
|---|---|---|---|---|---|
| `full-1` | 03.11. 04:20 | 07.11. 19:52 | 4 (Neustart durch Windows-Update 04.11. 03:55, Neustart der App 04.11. 08:05, Absturz 05.11. 02:25) | 2224, keine fehlgeschlagen | 2 098 073 s |
| `full-2` | 07.11. 19:52 | 09.11. 08:19 | 2 (Neustart des Rechners über das Startmenü 09.11. 05:30, fortgesetzt 06:44) | 2224, keine fehlgeschlagen | 1 509 553 s |

Beim zweiten Start des Skripts bekommt `full-1` einen leeren Anlauf in `run.json` (nichts offen, Exit 0), danach
setzt `full-2` fort. Die Summe von `full-2` geteilt durch 12 Prozesse sind 34,9 h und liegen in der Hochrechnung aus
dem Pilotlauf. Bei `full-1` sind die gedrosselten Stunden eingerechnet.

Der Absturz am 05.11. (Kernel-Power 41 ohne Bugcheck) blieb bis zum 07.11. 15:20 unbemerkt, weil die Wächter mit der
Sitzung endeten. Danach waren alle 1576 fertigen Einheiten und alle Ergebnisdateien von NeuroGrid lesbar [G]; der Lauf
wurde mit derselben Run-ID fortgesetzt. Bei einem langen Lauf deshalb nach jedem Neustart zuerst die Statusdatei und
die Python-Prozesse prüfen.

#### 4.10.7 Ergebnisse

Aus dem Hauptcheckout, nachdem beide Läufe fertig sind [R]:
```powershell
uv run --no-sync --project research/neuroarena python -m neuroarena.report publish full-1 full-2
uv run --no-sync --project research/neuroarena python -m neuroarena.report render
uv run --no-sync --project research/neuroarena pytest -q research/neuroarena/tests/test_published_results.py
```
`publish` schreibt die zehn Dateien von `results/` und endet mit Exit 1, wenn sich die Läufe unterscheiden. `render`
schreibt `report/en/report.md` und `report/zh/report.md` allein aus `results/`. Ergebnis am 09.11.2026 [G]:
- Vergleich: exakt gleich, ohne Toleranz – 12 160 Folds, die NeuroGrid-Werte von 1696 Aufnahmen und 48 quality.json,
  0 Unterschiede.
- Genauigkeit sauber (CSP+LDA / EEGNet, Zufallsniveau):

  | Datensatz | CSP+LDA | EEGNet | Zufallsniveau |
  |---|---|---|---|
  | Zhou2016 | 82,6 % | 78,7 % | 33,4 % |
  | Cho2017 | 65,9 % | 66,2 % | 50,0 % |
  | Kalunga2016 | 56,5 % | 37,4 % | 25,0 % |

- Qualitätsstufen der Hauptkurve: Zhou2016 nur Q3 bis Q5, Cho2017 zu 87 % bei Q5, Kalunga2016 über alle fünf Stufen.
  Keine Kombination ist ohne Stufe.
- Befund A-111: Unter Netzbrummen steigt EEGNet bei Cho2017 von 66,2 % auf 96,8 %, CSP+LDA bleibt. Der MOABB-Loader
  legt die Versuche je Klasse als Block an. Ein Versuch beginnt alle 3584 Abtastwerte, das sind 420 Perioden von
  60 Hz. Zwischen den Blöcken liegen 500 Nullwerte. Die Sinusschwingung hat daher je Klasse eine eigene Phase am
  Versuchsbeginn. Prüfen lässt sich das so: `neuroarena.datasets.configure_storage()` aufrufen, dann für jeden
  Probanden `mne.events_from_annotations` auf den Rohdaten von `Cho2017().get_data()` anwenden und
  `(Beginn · 60 / 512) mod 1` je Klasse bilden. Am 09.11. ergab das bei allen 52 Probanden 0,8828 (linke Hand)
  gegen 0,4766 (rechte Hand).
- Vorsicht beim Nachprüfen: Ohne `configure_storage()` lädt moabb 1.7.2 vom NEMAR-Spiegel und nicht von der geprüften
  Quelle. Außerdem schreibt `mne.set_config` eine Konfigurationsdatei unter `~/.mne`.

#### 4.10.8 Stand heute und was zu P11 noch fehlt

P11 ist abgeschlossen (Ergebnisse 00f63a5, Phasencommit danach). Offen sind nur Punkte beim Projektverantwortlichen:
- die Entscheidung zu A-111;
- die zh-Prüfung des Berichts;
- die Sichtprüfung der beiden Abbildungen.

`.local/arena/` (Daten 10,2 GB, Läufe, Logs) bleibt unversioniert liegen. Ein Nachbau braucht die Läufe nicht: Die
Tests von `results/` laufen ohne Laufordner.

#### 4.10.9 Prüfbefehle der Doku von P11

Wie in 4.9.10, dazu der Ergebnistest im Forschungsprojekt:
```powershell
$PY = ".\.venv\Scripts\python.exe"
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
& $PY tools\check_matrix_coverage.py
& $PY tools\check_commit_ids.py --since c1f5129
& $PY -m pytest -q -p no:cacheprovider tests\docs\test_docs_sync.py tests\docs\test_licensing.py tests\packaging\test_packaging_texts.py tests\packaging\test_workflows.py tests\unit\test_architecture.py::test_matrix_coverage tests\unit\test_small_units.py::test_commit_message_cleanup
uv run --no-sync --project research/neuroarena pytest -q research/neuroarena/tests/test_published_results.py
```

### 4.11 P7 – GB/T 47127 (2026-11-09)

#### 4.11.1 Normtext und Inventar

Den Normtext GB/T 47127—2026 übergibt der Projektverantwortliche (D-22). Er liegt unversioniert als
`.local/normen/GBT-47127-2026.pdf` (23 Seiten, Text auslesbar). Der Text wird mit pypdf ausgelesen, im
Layout-Modus nach `GBT-47127-2026.layout.txt` und kompakt ohne Leerzeilen [R].

Beim Auslesen fehlen in manchen Bezeichnern der Tabellen Buchstaben, etwa „SamlinFreuenc“ für
SamplingFrequency. Maßgeblich ist die Tabelle (A-113).

Das Inventar steht in `.local/p7/inventory.md`: Pflichtelemente G-01 bis G-27 mit Klausel und Verbindlichkeit (应
heißt „muss“, 宜 „soll“, 可 „kann“) sowie die Auslegungsfragen AF-1 bis AF-10. Ins Repository kommen nur
Klauselnummern, Bezeichner und eigene Kurztexte (A-55).

#### 4.11.2 Aufbau

| Teil | Datei | Inhalt |
|---|---|---|
| Leser | `src/neurogrid/io/gbt47127.py` | `read_dataset` (Layout nach 6.1/6.2, Dateinamen nach 7.5.7/7.6, JSON/XML und TSV/CSV, Leseprobleme als Schlüssel statt Ausnahmen), `looks_like_gbt47127` (Erkennung, A-115) |
| Schreiber | ebenda | `from_bids` (BIDS → GB/T, Feldabbildung, BrainVision mit umbenannter Daten- und Markerdatei, Lücken statt erfundener Werte, A-114) |
| Prüfungen | `src/neurogrid/checks/gbt47127.py` | 18 Prüfungen; Feldtabellen je Modalität (Tabellen 1–19); `structure_counts` für `convert` |
| Regelpaket | `src/neurogrid/rulepacks/gbt47127.yaml` | 18 Regeln, `source_status: final`, `norm: true` |
| Konvertierung | `src/neurogrid/pipeline.py` | `_run_convert_gbt47127` (über BIDS, Verarbeitungsschritte, Strukturprüfung) |
| Kern | `io/discover.py`, `metadata.py`, `io/participants.py` | Feld `is_gbt47127`, Metadaten aus GB/T, ParticipantId als `participant_id` |
| Texte | `report/i18n/{en,zh,de}.yaml`, `docs/_data/checks.{en,zh}.yaml`, `interpretation_questions.yaml` | Prüftitel und Gründe, Referenzseiten, IQ-001 bis IQ-005 |
| Tests | `tests/integration/test_gbt47127.py` | 35 Tests (siehe 4.11.4) |

#### 4.11.3 Benutzung

Aus dem Projektordner [R]:
```powershell
$PY = ".\.venv\Scripts\python.exe"
& .\.venv\Scripts\neurogrid.exe convert tests\fixtures\synthetic\bids_ok --to gbt47127 --out <Arbeitsordner>\gbt
& .\.venv\Scripts\neurogrid.exe check <Arbeitsordner>\gbt --rulepack gbt47127 --out <Arbeitsordner>\results.json
& .\.venv\Scripts\neurogrid.exe convert tests\fixtures\synthetic\edf_ok --to gbt47127 --config tests\fixtures\documented.toml --out <Arbeitsordner>\gbt_raw
```

Erwartet [G]:
- **BIDS-Fixture:** `Converted recordings: 2` und die Strukturprüfung mit 0 Fehlern. `check` ergibt 0 Fehler und
  7 Warnungen, so viele wie die BIDS-Quelle, bei Abdeckung `gbt47127` 1.0. Die einzige GB/T-Meldung ist der
  Hinweis STO-002: Der Name der Fixture enthält Leerzeichen.
- **Rohordner `edf_ok`:**
  - Name und Elektrodenpositionen werden als Lücken gemeldet; sie sind nirgends belegt.
  - Die Strukturprüfung zeigt 3 Fehler, Exit 1.
  - `processing_steps.json` enthält `convert_to_bids` und `convert_to_gbt47127`.

Fallen: Ohne `[[convert.files]]` oder ein passendes Muster schreibt `convert` die Vorlage
`.neurogrid/mapping-template.toml` in den Eingabeordner, auch in eine Test-Fixture. Deshalb immer eine Kopie
konvertieren.

#### 4.11.4 Tests

`tests/integration/test_gbt47127.py` (35):
- der vollständige Datensatz aus `bids_ok` besteht jede Regel;
- 19 Störungen, je eine Regel mit ihrem Grund;
- XML und CSV werden gelesen;
- DOCTYPE wird abgelehnt;
- Teile der Dateinamen;
- Pseudonyme in fremden Ordnern (A-117);
- Rundreise BIDS → GB/T → `check` ohne Fehler;
- Rohordner mit Lücken;
- BrainVision mit Begleitdateien;
- Runs ohne Zeitstempel;
- volle Ausgabe wird abgelehnt;
- jede der sechs Modalitäten vollständig und mit fehlendem Pflichtfeld.

Angepasst an den neuen Stand, nicht abgeschwächt:
- die Paketlisten in `test_message_tables.py`, `test_norm_independence.py` (KNOWN) und `tools/gen_docs.py`;
- die ausgelieferten Auslegungsfragen in `test_docs_build.py` (vorher leer, jetzt IQ-001 bis IQ-005);
- `--to` im Konvertierungstest, `gbt47127` nicht mehr „nicht verfügbar“.

Das zh-Prüfpaket nimmt `interpretation_questions.yaml` auf.

CI auf 2358e45: `ci` war rot am Typcheck (`mypy src/neurogrid tools`; 9 Stellen in `checks/gbt47127.py`, an
denen `None` nicht eingegrenzt war). Behoben in f842fc0 mit der Hilfsfunktion `_as_float` und ausdrücklichen Prüfungen. Vor dem
Push also auch `mypy` laufen lassen: `uv run --no-sync mypy src/neurogrid tools` [R].

CI auf f842fc0: `ci` rot an `tests/rules/test_builtin_rules.py::test_every_builtin_rule_has_positive_and_negative_case`:
jede Regel eines eingebauten Pakets braucht einen positiven und einen negativen Fall (NG-N08). Ergänzt in 36b9ddf mit
`tests/rules/gbt47127_setups.py` (der GB/T-Datensatz entsteht zur Laufzeit aus `bids_ok`). Lokal vor dem Push also auch
`tests/rules` laufen lassen.

#### 4.11.5 Stand heute und was offen ist

- Die Annahmen A-113 bis A-117 sind freigegeben mit D-23 (13.11.2026).
- Echte GB/T-Datensätze von Geräten gibt es nicht öffentlich: Die Tests nutzen synthetische Daten.
- Die XML-Struktur ist eine Lesart (IQ-004).
- Für NG-F04 (Abbildung ISO/IEC TS 27571 ↔ BIDS ↔ GB/T, P10) liegt die GB/T-Seite jetzt vor.

#### 4.11.6 Lauf auf eigenem Runner (2026-11-13, V-03, D-19)

Einmal vor v1.0 läuft `ci-integration.yml` mit dem Job `self-hosted` auf einem eigenen Runner, nur per Dispatch:

1. Runner herunterladen (hier 2.338.2, Windows x64), die Prüfsumme mit der Release-Seite von `actions/runner`
   vergleichen, nach `%USERPROFILE%\actions-runner` entpacken.
2. Registrieren mit dem Token von Settings → Actions → Runners → New self-hosted runner (gilt eine Stunde; das macht der
   Projektverantwortliche): `.\config.cmd --url https://github.com/<owner>/<repo> --token <TOKEN> --labels neurogrid
   --name neurogrid-temp --unattended`. Ohne `--labels neurogrid` nimmt der Runner den Job nie an; im Protokoll
   `_diag/Runner_*.log` steht dann `Arg 'labels': ''`.
3. `run.cmd` starten (kein Dienst) und auf „Listening for Jobs“ warten.
4. Erst dann `ci-integration` von Hand starten: Branch `dev`, Eingabe `self_hosted` an. Einen Job, der eingereiht wurde,
   als noch kein Runner das Label hatte, teilt GitHub nicht neu zu, auch nicht nach dem Nachtragen des Labels und einem
   Neustart des Runners: den Lauf abbrechen und neu starten.
5. Erwartet: alle fünf Jobs grün; der Job `self-hosted` in etwa 2 min; der Schritt „Exit code and files as expected“
   wird übersprungen (er läuft nur, wenn etwas fehlt).
6. Danach `Runner.Listener` beenden, den Ordner löschen (er enthält `.credentials`) und den Runner unter Settings →
   Actions → Runners entfernen.

Ein neu gestarteter Runner meldet einige Minuten „A session for this runner already exists“ (Conflict), bis GitHub die
alte Sitzung verwirft; er versucht es selbst weiter.

Ergebnis am 13.11.2026: `ci-integration` 43405451313 auf 024c737 grün (FORTSCHRITT, Verlauf 2026-11-13).

---

## 5 Prüfwerkzeuge (`tools/`)

Alle Werkzeuge laufen im `<Projektordner>` mit `& $PY tools\<name>.py` (PowerShell) bzw. `"$PY" tools/<name>.py`
(Git Bash), nachdem `PY` wie in 4.0 gesetzt ist. Exit 0 heißt immer „in Ordnung“.

| Werkzeug | Zweck | Aufruf | Exitcodes |
|---|---|---|---|
| `check_matrix_coverage.py` | jede Matrixzeile genau eine abschließende Phase, keine unbekannte ID | `check_matrix_coverage.py` | 0 / 1 |
| `check_commit_ids.py` | Anforderungs-IDs in Commits seit `d81ad0c` (Merges übersprungen) und datierten FORTSCHRITT-Einträgen | `[--since REV] [--message-file F] [--no-history]` | 0 / 1 |
| `coverage_gates.py` | Abdeckung je Gruppe aus `coverage json`: Kern ≥ 90 % (seit P6 mit `vault/`), Prüfer ≥ 80 %; seit P6 ohne die markierten Blöcke der anderen Plattform in `vault/_os.py`, eine Markierung anderswo lässt das Gate scheitern (A-90) | `coverage_gates.py <coverage.json> [--platform windows\|posix]` (Standard: die laufende Plattform; `--help` seit P6) | 0 / 1 |
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
| `gen_docs.py` | Referenzseiten und generierte Blöcke (10 Dateien); seit P6 Platzhalter-Kennzeichen und der Block der Auslegungsfragen aus `docs/_data/interpretation_questions.yaml`, ungültige Fragen sind Exit 2 (A-92) | `[--check]` | 0 / 1 / 2 |
| `build_docs.py` | Website bauen und prüfen (Netz-Audit-Hook, `SOURCE_DATE_EPOCH`; seit R19 Entfernen von `lunr/**` und `*.map`, Prüfung jedes Drittanbieter-Teils gegen `license-gate/third_party/mkdocs-material-<v>/manifest.toml`, Zeile „licence pending …“ je offenem Teil) | `[--site-dir site]` | 0 / 1 / 2 |
| `mkdocs_hooks.py` | MkDocs-Hooks (Suche zh, Schemas, 404) – kein eigener Aufruf | über `mkdocs.yml` | – |
| `notices.py` | `THIRD_PARTY_NOTICES.txt` statisch aus den Wheels beider Ziele; `--check` prüft auch die Manifeste unter `license-gate/third_party/` und meldet jeden `known_missing`-Eintrag als „incomplete“ | `--list`; `--wheelhouse DIR … --out F`; `--download [--cache DIR] --out F`; `--check` (nur mit `--wheelhouse` oder `--download`); `--components`; `--sources DIR …` (Quellen der Auszüge, D-17); `[--bundle-lock F]` | 0 / 1 (auch: Einträge in `known_missing.toml`) / 2 (u. a. Dateien fehlen) |
| `bundle.py` | Offline-Bündel | `build --platform P --wheel W --docs D --notices N [--sdist S] [--pdf-installer F] [--out dist] [--cache DIR] [--sign none\|sigstore]`; `verify PATH`; `sizes [--platform P]`; `lock --python V --pbs-build B --uv V [--cache DIR]` | 0 / 1 / 2 |
| `release_check.py` | Release-Gate (Tag = Version, auf main, sauberer Baum, keine Platzhalter, Lizenztexte) | `--tag v<v> [--root DIR] [--notes OUT] [--repository owner/repo]` | 0 / 1 / 2 |
| `scan_runtime_network.py` | Netzwerk-/Telemetrie-Fundstellen der Laufzeitpakete gegen die Baseline | `[--site-packages DIR] [--baseline F] [--distribution NAME]… [--draft OUT]` | 0 / 1 / 2 |
| `strace_check.py` | strace-Ausgaben auswerten (nicht-Loopback = Fehler; seit R11 auch Loopback auf Port 9, den Port eines toten Proxys; liest seine eigene `strace-summary.txt` nicht zurück) | `strace_check.py EVIDENCE_DIR` (kein `--help`) | 0 / 1 / 2 |
| `acceptance_g1.py` | G1-Abnahme auf dem Korpus (A-88, 4.7.8); seit P6 erwartet sie für M14 den zusammengefassten Block statt Befundzeilen und prüft, dass er keinen Probanden nennt (A-91) | `--corpus DIR --out DIR [--datasets X …] [--runs 2] [--jobs 4] [--as-of 2026-10-11] [--replace]` | 0 / 1 / 2 |
| `zh_review_package.py` | zh-Prüfpaket mit Beispiel-PDFs (A-07, 4.7.8); seit `2f2a5a5` mit jedem Regelpaket unter `src/neurogrid/rulepacks/` | `[--out F] [--since a44d592] [--g1 DIR] [--examples DS …]` | 0 / 2 |
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
| CC-BY-4.0-Rechtstext | `https://raw.githubusercontent.com/spdx/license-list-data/v3.27.0/text/CC-BY-4.0.txt` | 17 023 B | `d557539df68e771cc1eedcc91d13f70fca930e508d11eedcafa4b15db49e3744` (`license-gate/licence_texts.toml`) | **D-15** (abgelegt) | `LICENSES/CC-BY-4.0.txt` (4.7.7) |
| LGPL-3.0-or-later, GPL-3.0-or-later für isomorphic-git 1.41.9 | `…/license-list-data/v3.27.0/text/LGPL-3.0-or-later.txt` bzw. `…/GPL-3.0-or-later.txt` | 42 098 B / 34 674 B | `996af0513df21f7496288951c41428a03c174e9e4a9d63665c57d670f845ccb1` / `fb981668c18a279e285fc4d83fba1e836cc84dd4daa73c9697d3cfd2d8aca6e0` (`license-gate/licence_texts.toml`) | **D-16** (abgelegt) | neben isomorphic-git 1.41.9 unter `license-gate/third_party/bids-validator-3.0.2/npm/`, Notices |
| Lizenzdateien der npm/jsr-Pakete im Validator 3.0.2 | npm-Versionsdokumente und -Tarballs von registry.npmjs.org (URLs je Paket im Manifest), jsr `https://jsr.io/<paket>/<version>/<datei>` und `<version>_meta.json` | 146 Downloads des Zweigs `p5-licence-texts` (einschließlich CC-BY-Text), zusammen 9 381 740 B [D] | je Datei in `license-gate/third_party/bids-validator-3.0.2/manifest.toml` | **D-15** (nur genaue Versionen; abgelegt) | Notices Abschnitt 3 |
| Lizenztexte der acht G1-Lücken (70 Downloads: Einzeldateien von raw.githubusercontent.com, unicode.org/license.txt, die Brumme-Seite, das npm-Tarball von `@jspm/core` 2.1.0) | URL-Liste des Projektverantwortlichen | je Datei im Manifest | Manifeste in `license-gate/third_party/` (bids-validator 45, h5py 1, mkdocs-material 3, python-build-standalone 21 Texte) | **D-17** (abgelegt; `known_missing.toml` leer) | Notices |
| Texte der Doku-Seite (mkdocs-material 9.7.7) | kein Download: aus dem installierten Wheel (die Texte von focus-visible und material-design-color: D-17-Zeile) | – | in `license-gate/third_party/mkdocs-material-9.7.7/manifest.toml` | – | R19 |
| Quelltexte zur Ursachensuche der zweiten Fix-Runde und des G1-Befunds (nur gelesen, nichts abgelegt) | Chromium am Tag 153.0.8010.12: `https://chromium.googlesource.com/chromium/src/+/refs/tags/153.0.8010.12/<pfad>?format=TEXT` (base64); CPython `PC/_wmimodule.cpp` der Zweige 3.12 und 3.13; mkdocs-material 9.7.7 aus der Source-Map im `.venv` (kein Download) | – | – | nicht protokolliert [NV] | 4.7.14, 4.7.17 |
| `install_pdf_browser.py` als Release-Asset | `<REPO_URL>/releases/download/v<v>/install_pdf_browser.py` (erst ab dem ersten Release) | – | heute `3e713e1400cde83a93782d1dacd0e8201fcb74693c787987e7e5ca51cfd6b149`, erzeugt in `installation.md` von `gen_docs.py` | – | PyPI-/Quell-Nutzer (R28) |
| torch, braindecode, moabb, MOABB-Daten | – | – | – | D-06 | P11, noch nicht geladen |

Bewusst **nicht** verwendet: eegprep (D-05), pyEDFlib (A-24), EEGDash (D-11), openneuro-py (GPL-3.0), Microsoft Edge,
jieba (nur sdist), iframe-worker, `playwright install`, actionlint (Nebenwirkung einer Probe, nicht übernommen, aus dem
Cache entfernt).

---

## 8 Bekannte Grenzen und nicht Verifiziertes

**Plattformen (D-09):**
- **In der CI gelaufen** (GitHub Actions, seit 26.10.2026): Auf dem Endstand `27c3e90` sind alle Jobs beider
  Workflows grün (4.7.19) [G, CI 27c3e90], ebenso schon auf `dcec9bd` (4.7.16) [G, CI dcec9bd] – im Workflow
  `offline` Bau beider Bündel mit `pytest -m bundle`, offline-strace aller v0.1-Befehle (NG-N01), Linux-Reinräume `debian:12-slim`, `ubuntu:22.04`, `ubuntu:24.04`, glibc-Ablehnung
  `ubuntu:18.04`, `pdf-debian12`, Windows-Reinraum unter PowerShell 5.1 und PowerShell 7 mit WFP-Audit (so schon auf
  `55335ca` [G, CI 55335ca]); in `ci` die sechs Testjobs ubuntu-24.04 und windows-latest × 3.11–3.13 mit Abdeckungs-Gates,
  der plattformübergreifende Vergleich (berichtet, nicht erzwungen), Lizenz-Gate und Netz-Scan, Kommandozeile unter
  PowerShell 5.1 und 7, Rückverfolgbarkeit. Auf `55335ca` und `18da12f` waren die Testjobs rot (4.7.12, 4.7.18).
  TECH-11 („CI aktiv“) steht auf `erfüllt`: Nach der DoD von P1 (KONZEPT 6) gilt die Zeile, sobald nach dem Push der
  erste CI-Lauf möglich ist; `ci.yml` und `offline.yml` laufen auf jedem Push auf `dev` (Läufe 40403791901 und
  40403791782 auf `55335ca`, 40476578603 und 40476578452 auf `dcec9bd`, 40609866806 und 40609866836 auf `18da12f`,
  40680346160 und 40680346176 auf `27c3e90`).
- **Belegt seit `27c3e90`:** die Behebung des G1-Befunds unter Linux (POSIX-Zweige von `kernel/processes.py`,
  resource tracker bei spawn/forkserver, `on_null_device`) und unter Windows mit Python 3.11–3.13 (`quiet_pool`),
  nur über die grünen CI-Testjobs (lokal kein Linux). Testzahlen und Abdeckung je Job stehen seit `2a49a0c` als
  Notice-Annotationen in der öffentlichen API (4.7.19); welche Tests ein Runner übersprang (unter Linux 97, unter
  Windows 15–16), steht nur im Job-Log und in `pytest-junit.xml` [NV]. Die Testsuite läuft in der CI nur auf
  ubuntu-24.04 und windows-latest, nie auf Debian 12 oder Ubuntu 22.04 (dort nur die Reinräume); so sagt es seit
  `17e0d3f` auch die Nutzerdoku.
- **Nachweis ausstehend:** Der Aufruf von `ci.yml` aus `release.yml` (Job `suite`, Release-Gate `dd9ab93`) lief noch
  nie; erst der erste Tag-Lauf prüft ihn [NV]. Die genaue Linux-Zeile von onnxruntime im CLI-Prozess hat keine CI
  gedruckt (belegt sind die Zeichenketten des Wheels und der grüne Testjob, 4.7.18).
- Nie gelaufen: `docs.yml`, `corpus.yml`, `release.yml`, `publish-pypi.yml`, `mirror-gitee.yml` (nur `main`, Tag
  oder Dispatch) [NV].
- PowerShell 7 lokal nicht installiert (nur CI); Windows 10 nicht verifiziert; NG-N02 auf einem Runner mit
  4 vCPU/16 GB nicht gemessen.

**Nicht protokolliert / nicht erhalten:**
- genaue Befehle für uv-Installation, `uv python install`, Anlage von venv3.11/3.13 (hier [R]), lokale pytest-Aufrufe,
  Probe-Wheel, Rauchtests PowerShell 5.1 in P1/P2, Zusatzmessung „256 Kanäle mit Manifest“
- Prototypen S1–S5 (Skripte gelöscht); Bau-Reihenfolge innerhalb P1–P3; Herstellung von `architektur-s8.png`
- Plattformvergleichsskript (nur Scratchpad)
- P5: einmalige Lade- und Zusammenstellungsskripte der Validator-Lizenztexte und der D-17-Texte, Prüf- und
  Messskripte der Verifikationen, die Simulations-Plugins der Linux-Fehler und der Handle-Monitor des G1-Befunds (nur
  Scratchpad); das Skript der Präfixprobe; die volle Suite der docs-Fix-Runde; `bundle.py sizes` und Korpustests
  (`-m corpus`) auf dem gemergten Stand; volle Suiten in den Zweigen der zweiten CI-Fix-Runde (nur nach dem Merge)
- P5, dritte CI-Fix-Runde: der nachgebaute `fcntl` für den POSIX-Zweig, der instrumentierte Manager-Thread und das
  pytest-Plugin für `shutdown_workers` (nur Scratchpad); das API-Leseskript des Leads (nur Scratchpad, Ablauf und
  Kurzfassung in 4.7.19); eine lokale volle Suite auf `27c3e90` (bewusst nicht, 4.0)

**Inhaltlich offen (für G1 vorgemerkt):**
- Lizenztexte: geschlossen. `license-gate/known_missing.toml` ist seit D-17 leer (CC-BY-4.0-Rechtstext und
  npm/jsr-Lizenzdateien nach D-15, LGPL-/GPL-Text nach D-16, die acht übrigen Lücken nach D-17). Ein neuer Eintrag
  sperrte das Release wieder über `notices.py --download --check` in `release.yml`. Die Versionen der 33 Pakete in
  `@jspm/core` 2.1.0 sind nur über das Lockfile von jspm-core belegt (D-17); die Quellen der Auszüge liegen nicht im
  Repository (`notices.py --sources`). Geschlossen hat D-17 die acht Einträge, die auf `181654e` noch offen waren
  [G, 181654e]:
  `bids-validator-deno:hed-validator@4.2.0/node_modules` (acht in hed-validator 4.2.0 eingebettete Pakete ohne
  Version in der Source-Map: @nodable/entities, fast-xml-parser, lodash, path-expression-matcher, semver, strnum,
  unicode-name, xml-naming), `bids-validator-deno:hash-wasm@4.12.0/src` (C-Quellen ohne Lizenztext: crc32, crc64,
  xxhash32, xxhash64; argon2), `bids-validator-deno:node-modules-polyfills/@jspm/core` (Node-Polyfills ohne Version),
  `h5py:h5py.libs/libaec-*.so*` und `h5py:h5py.libs/libsz-*.so*` (im Linux-h5py-Wheel weder Lizenz noch Text),
  `python-build-standalone:3.12.15+20261009` (Texte der Bibliotheken außer CPython), `docs-site:focus-visible` und
  `docs-site:material-design-color` (im Doku-Theme ohne Lizenzangabe).
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
- R08 und R09: behoben in `p5-ci2-userdocs` (4.7.14).
- `convert`: Die Ausgabe ist zwischen Betriebssystemen nicht byte-gleich. MNE-BIDS und pybv schreiben
  `participants.*`, `*_channels.tsv`, `*_events.*`, `*_scans.tsv`, kopierte BrainVision-Köpfe und -Marker und die
  `.vhdr`/`.vmrk` von pybv im Textmodus mit `os.linesep` (unter Windows CRLF gemessen, unter Linux folgt LF);
  damit unterscheidet sich auch `output_hash` in `.neurogrid/processing_steps.json` [D]. Zwei `convert` auf derselben
  Plattform bleiben dateigleich (4.3).
- BrainVision: Nur `Codepage=ANSI` (jede Schreibweise) wird plattformgleich behandelt; `mbcs`, `dbcs`, `oem` und `cpNNNN`
  (Python-Aliase, keine Standardwerte von BrainVision) decodieren unter Windows mit der Systemcodepage und scheitern
  unter Linux. Eine Markerdatei mit `Codepage=punycode` ist in der Laufzeit nicht begrenzt (A-53 begrenzt nur den Kopf;
  im Code gesehen, nicht gemessen). Seit `18bb4ef` kopiert auch Linux ANSI-Aufnahmen byte-gleich; reines MNE 1.13 unter
  Linux liest deren nicht-ASCII-Marker nicht (MNE-Fehler, NeuroGrid liest über `mne_read_raw_brainvision`). Die
  Ersetzungen von `io.base.ModulePatch` gelten, solange sie gehalten werden, für den ganzen Prozess.
- PDF unter Linux: Die Gegenprobe in `test_font_render_hinting_is_read_by_the_shell` (mit `full` geteilte Regel-IDs)
  und die Radikal-Gegenprobe (Skia wählt den kleinsten Codepunkt einer geteilten Glyphe) beruhen auf dem Verhalten von
  Chromium 153/FreeType; ändert es sich, scheitern die Tests mit der genannten Ursache. Die Glyph-0-Prüfung liest nur
  Type0-Schriften mit Identity-Kodierung. Renderer bleiben unter Windows Kindprozesse; schrieben sie je ein `debug.log`,
  räumte `_ChildLog` es weg.
- Installer: `Show` verbirgt Benutzerordner in eigener, langer und kurzer Schreibweise, nicht in gemischten.
- Hilfsprozesse (A-89): `avoid_wmi()` ersetzt die private Funktion `platform._wmi_query` (CPython 3.12/3.13); benennt
  eine spätere Version sie um, wirkt der Schutz nicht mehr (die Audit-Tests unter Windows würden das zeigen). Direktes
  Schreiben auf das Konsolengerät (`CONOUT$`, `msvcrt.putwch`, `/dev/tty`) umgeht beide Schichten (Restrisiko, in keinem
  Lauf beobachtet). Bibliothekswarnungen der Worker entfallen bei `--jobs` > 1, mit `--jobs 1` erscheinen sie übersetzt.
  Unter POSIX gehen Ausgaben anderer Threads während eines Prozessstarts nach `/dev/null`; den resource tracker deckt der
  Schutz nur, wenn NeuroGrid ihn zuerst startet. Ein kaputter Pool rechnet weiter jede offene Aufnahme allein nach (D-14).
  Seit der dritten CI-Fix-Runde (4.7.18): Ein forkserver oder resource tracker, den anderer Code desselben Prozesses vor
  dem ersten Pool von NeuroGrid startete, behält seine Deskriptoren (im CLI unter Linux nicht möglich: fork ist bis 3.13
  Standard, das CLI wählt nie forkserver). Nicht gedeckt sind auch stdin des Elternprozesses auf einem Deskriptor über 2
  und Stream-Objekte ohne Deskriptor, über die vorher registrierte at-fork-Handler schreiben. `quiet_pool` stützt sich
  auf private Teile von CPython (`concurrent.futures.process._SafeQueue`, `_CallItem`, `_on_queue_feeder_error`,
  `ProcessPoolExecutor._call_queue`, `multiprocessing.queues.Queue._buffer`), gleich in 3.11.17, 3.12.15 und 3.13.7;
  eine neue CPython-Version ist neu zu prüfen (`tests/integration/test_worker_console.py` scheitert, wenn sich ihr
  Verhalten ändert). Ein verlorenes Stoppsignal in einem arbeitenden Pool ließe den Lauf am Ende auf seinen Worker
  warten (nicht beobachtet, nicht behandelt). Während eines `on_null_device`-Blocks gehen Konsolenausgaben anderer
  Threads auf das Nullgerät (mit `--jobs 1` hat das CLI keinen solchen Thread); unter Windows würde eine Bibliothek,
  die den alten Standard-Handle zwischenspeichert oder im Block einen `logging.StreamHandler` anlegt, danach falsch
  schreiben (in onnxruntime, mne_icalabel und picard keiner gefunden).
- Lizenztexte: Die Brumme-Seite ist dynamisch (aufbewahrt sind Auszug und Seiten-Hash); die Version von
  material-design-color 2.3.2 belegt nur das Lockfile von mkdocs-material; `notices.py --sources` braucht lokale Kopien.
- Signatur: die Prüfung im Archiv ist eine Integritätsprüfung, die Identität vergleicht der Nutzer (R12); cosign im
  PATH prüft immer (R16); Gitee-Release von Hand (R15).
- Pfadgrenzen 250/260 nur auf Windows 11 Build 26200 gemessen; Linux-PATH_MAX-Grenze beruht auf der dokumentierten
  Konstante. Die Messgrenzen der Skalierung gelten für einen Rechner wie den Entwicklungsrechner, wach gehalten.
- zh-Prüfung durch Muttersprachler (A-07) für alle zh-Texte, Doku, Installer- und Browser-Meldungen (4.7.8), auch für
  den seit D-17 geänderten Satz zu focus-visible und material-design-color in `docs/zh/license.md`.

**Aus P6 (A-90 bis A-92; für STOPP G2 vorgemerkt):**
- Zugriffsprotokoll: Ändern, Einfügen, Löschen und Umsortieren innerhalb der Kette werden erkannt; Kürzen am Ende und
  vollständiges Neuschreiben nur mit `vault verify --expect-head` gegen einen anderswo festgehaltenen Kopf-Hash. Erfasst
  sind nur Zugriffe über NeuroGrid: Läufe mit Exit 2 schreiben nichts, `scan`, `manifest` und `verify` nur in den Vault
  am Standardort, `report` nur mit `--config`. Zeiten aus der lokalen Uhr, nicht geprüft. Die Sperre ist beratend
  (andere Programme hält sie nicht auf) und wartet höchstens 10 s; zwei `check` sind bytegleich, solange niemand die
  Sperre länger hält. Rollen sind beratend.
- Einwilligung: NeuroGrid beurteilt nicht, ob eine Einwilligung rechtlich wirksam ist; `vault consent add` schreibt
  `consents.yaml` kanonisch neu (Kommentare gehen verloren); results.json nennt pseudonyme Probanden mit dem Grund
  (wie die Daten behandeln). Im Bericht ist die Aufschlüsselung je Nutzung in kleinen oder gemischten Datensätzen fast
  immer zurückgehalten (Tabellenregel, A-81).
- `report --config` mit einer toml außerhalb des Datensatzes unter einem Ordner, der selbst `.neurogrid`, eine
  `dataset_description.json` oder den `[vault] path` enthält, nimmt diesen Ordner als Projektwurzel (9e44134).
- Platzhalter-Gerüst: Mit core und `yyt2029` bleibt der Gesamtsatz „besteht die Prüfungen der geladenen Regelpakete“,
  die Konsole nennt nur `core`; Banner und eigener Abschnitt grenzen das ab.
- Nicht verifiziert [NV]: die POSIX-Zweige des Vaults nach der Fix-Runde (CI auf `0ffdd90`: ganz grün (`ci` 41422859481, `offline` 41422859830)), das Ziel
  „`vault verify` mit 10⁶ Einträgen in < 30 s“, die Inhalte der beiden `wip:`-Commits gegen einen Bericht ihrer
  Bau-Agenten (es gibt keinen; belegt sind sie nur durch Code, Tests, Doku und das Review), die Skripte des Reviews
  (nur Scratchpad).

**Aus P9 (A-93 bis A-99; für die Freigabe nach P9 vorgemerkt):**
- Rollenregister: beratend, nichts wird abgelehnt; CORE-NV04-01 beurteilt nur Ereignisse vor dem Vortag des
  Stichtags (UTC); mit einem Stichtag mehr als einen Tag in der Zukunft kann das eigene Ereignis eines Laufs in
  CORE-NV04-01 des nächsten Laufs eingehen; Ereignisse ohne Rolle (`scan`, `manifest`, `verify`) bleiben grau.
- Folgenabschätzung: die Vorlagen sind Platzhalter (A-30); juristische Prüfung durch eine in der VR China
  zugelassene Rechtsberatung vor der ersten echten Verwendung (D-19); Fristlogik nur für die Vault-Objekte, nicht für
  die EEG-Daten.
- Neueinwilligung: die Liste je Proband steht nur in results.json; der Preis der Tabellenregel (mit einem beurteilten
  Risiko ist die Zahl unter der Version über Summen und Ampel ablesbar; A-81 gilt je Tabelle, Differenzen zweier
  veröffentlichter, sich überschneidender Risiken können Zahlen von 1 bis 4 ergeben); Risiko-IDs erscheinen im Bericht
  wie geschrieben; kein CSS für `table.reconsent`, kein gedrucktes PDF mit vielen Risiken angesehen; die Laufzeit mit
  etwa 1 000 Risiken ist nicht gemessen. Die erzeugte Schwellenzeile von CORE-M14-02 in `metrics.md#M14` nennt nur
  „Warning“, ohne den Hinweis auf not_checkable (Lücke des Bereichs, offen).
- Export-ZIP: bytegleich nur in einer Umgebung (zlib); die Prüfung liest das Protokoll nach dem Streamen über den
  Namen, ein fremdes Programm, das es dazwischen ersetzt, bleibt unbemerkt; die Berichte liegen bis zu 5 × 256 MB im
  Speicher; `roles.yaml` und die PIA-Dateien kommen so ins ZIP, wie sie geschrieben sind (Rollen ohne personenbezogene
  Daten beschreiben).
- CI-Integration [NV]: der Wert von `runner.environment` auf einem eigenen Linux- oder macOS-Runner (auf einem
  eigenen Windows-Runner belegt, 4.11.6), die GitLab-Vorlage auf GitLab (Variable in
  `tags`, leerer Tag, Kodierung unter PowerShell); die PowerShell-7-Variante von `test_cli_diff.py` läuft nur in der CI.
- Nachweismappe [NV]: Sichtprüfung durch den Projektverantwortlichen (REP-08); mit `--config` sind zwei Bauten mit
  Absicht verschieden (das eigene Ereignis des Berichts).
- `src/neurogrid/cli.py`: Der Docstring nannte die Exitcodes von `diff` (0, 1, 2) nicht und sagte noch „Further
  commands follow in later phases“; behoben vom Lead mit der Doku (Docstring, kein Verhalten).
- Nicht verifiziert [NV]: lokal übersprungene Tests (Datei-Links, pwsh); die Testzahlen und die Abdeckung der CI auf
  `5596a8d` stehen in 4.9.8.

**P9 (Stand 5596a8d):** Bereiche Register, Neueinwilligung, Paket und Vergleich, Merge mit den Entscheidungen des
Leads und Querschnittstests sind gemacht (4.9); CI auf `5596a8d` grün (`ci` 41447040471, `offline` 41447040492, `ci-integration` 41447040527). Eine lokale volle Suite gibt es nicht
(A-87). Offen: REP-08 bis zur Sichtprüfung, V-03 bis zum Lauf auf eigenem Runner, NV-F03 bis P8, die zh-Runde der
P9-Texte vor v1.0, die Freigabe von A-93 bis A-99.

**P6 (Stand 0ffdd90):** Bereiche vault, consent und yyt2029, Querschnittstests, Merge- und CI-Korrekturen, Review und
Fix-Runde sind gemacht (4.8); CI auf `d50158b` rot nur an fünf Tests außerhalb der Bereiche (behoben in `2f2a5a5`),
`offline` grün; CI auf `0ffdd90`: ganz grün (`ci` 41422859481, `offline` 41422859830). Eine lokale volle Suite gibt es nicht (A-87). Offen: NV-F03 bis P8,
die zh-Runde der P6-Texte vor v0.2, STOPP G2.

**P5 (Stand 27c3e90):** Bau, Integration, Lizenztexte (D-15, D-16, D-17), G1-Abnahme, Skalierungsgrenzen (A-88),
Review, Fix-Runde, zweite CI-Fix-Runde, die Behebung des G1-Befunds und die dritte CI-Fix-Runde sind gemacht
(4.7.6–4.7.18); auf `27c3e90` sind alle CI-Jobs grün, Abdeckung je Testjob Kern 93,3–93,5 %, Prüfer 97,3 % (4.7.19);
G1 auf `18da12f` 6 von 6 Datensätzen bestanden (4.7.20). G1 auf `27c3e90`: 6 von 6 Datensätzen in 5 Formaten bestanden, alle Kriterien erfüllt, 0 Probleme, V-01 erfüllt, V-06 ja (149 min 28 s; `.local/p5/ci3/g1_summary_27c3e90.md`); das zh-Prüfpaket ist erzeugt (4.7.20). Korpustests auf dem Endstand: `test_corpus.py` 62 von 62, `test_g1_corpus.py` nach dem Werkzeug-Fix 7426dee: 52 von 52 bestanden (1 h 57 min; `.local/logs/g1corpus_7426dee.log`) (4.7.20). Offen: `bundle.py sizes` auf dem Endstand, dann STOPP G1 (4.7.21). Eine lokale volle Suite auf dem
Endstand gibt es nicht; die volle Suite läuft nur in der CI (4.0). Die Bündel-Tests laufen seit Review R10 wie in D-15
verlangt bei jedem Push auf `dev` und `main`; grün auf `dev` mit `55335ca` [G, CI 55335ca], `dcec9bd` [G, CI dcec9bd],
`18da12f` [G, CI 18da12f] und `27c3e90` [G, CI 27c3e90].

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
| `check` | `PATH` | `--rulepack VALUE` (Name oder Pfad, wiederholbar), `--config VALUE` (Standard `.neurogrid/neurogrid.toml`), `--out VALUE` (Standard `results.json`), `--strict`, `--as-of YYYY-MM-DD` (Standard heute), `--allow-draft-rulepacks`, `--show-paths`, `--jobs N` (1–64, Standard 1), `--evidence VALUE` (Standard `.neurogrid/evidence.yaml`), `--manifest VALUE` (Standard `.neurogrid/manifest.json`), seit P6 `--role VALUE` (Rolle des Zugriffsereignisses vor `[vault] role`) |
| `convert` | `PATH` | `--to bids` (Pflicht), `--out VALUE` (Pflicht, leer oder fehlend), `--config VALUE`, `--strip-identifying-headers` |
| `report` | `RESULTS_FILE` | `--lang VALUE` (Standard `zh,en`), `--format VALUE` (`html`, `pdf`, `html,pdf`; seit P9 auch `dossier`, kombinierbar, immer zh und en; Standard `html`), `--out VALUE` (Standard neben `results.json`), seit P6 `--config VALUE` (neurogrid.toml, deren Vault das Deckblatt zeigt; dann ein Ereignis `report`) |
| `manifest` | `PATH` (Ordner) | `--out VALUE` (Standard `.neurogrid/manifest.json`), `--show-paths` |
| `verify` | `PATH` (Ordner) | `--manifest VALUE` (Pflicht), `--show-paths` |
| `vault init` (P6) | `PATH` (Datensatz; Standard der aktuelle Ordner) | `--config VALUE` (Standard `.neurogrid/neurogrid.toml`; `[vault] path` nennt den Vault); seit P9 legt es auch `roles.yaml`, `risks.yaml`, `retention.yaml` und `pia/pia.zh.md`, `pia/pia.en.md` an, wenn sie fehlen |
| `vault log` (P6) | `PATH` (wie oben) | `--config VALUE`, `--action VALUE` (read, check, convert, report, export, consent_manage), `--objects VALUE` (wiederholbar), `--purpose VALUE`, `--approval-ref VALUE`, `--role VALUE`; oder allein `--show` |
| `vault verify` (P6) | `PATH` (wie oben) | `--config VALUE`, `--expect-head VALUE` (wiederholbar) |
| `vault consent add` (P6) | `PATH` (Pflicht) | `--subject VALUE`, `--version VALUE`, `--date VALUE`, `--uses VALUE` (wiederholbar oder kommagetrennt) oder `--withdrawn`, `--ethics-ref VALUE`; oder `--from VALUE` (consents.tsv); dazu `--config VALUE`, `--role VALUE`, `--purpose VALUE`, `--approval-ref VALUE` |
| `vault export` (P9) | `PATH` (Datensatz; Standard der aktuelle Ordner) | `--report VALUE` (Pflicht, wiederholbar, 1 bis 5: `report.<lang>.html`, `report.<lang>.pdf` oder `dossier.pdf`, je Art einmal), `--out VALUE` (Pflicht, ZIP außerhalb des Vaults), `--manifest VALUE` (Standard `.neurogrid/manifest.json`), `--show-paths`, `--config VALUE`, `--role VALUE`, `--purpose VALUE`, `--approval-ref VALUE` |
| `diff` (P9) | `OLD` `NEW` (zwei results.json, Pflicht) | `--format VALUE` (`text`, `json`, `text,json`; Standard `text`; `json` ohne `--out` allein auf stdout), `--out VALUE` (JSON; Pflicht bei `text,json`) |

**Exitcodes (A-12):** `check`: 0 keine fehlgeschlagene error-Regel, 1 mindestens eine (auch: Ordner ohne lesbare
Aufnahme), 2 Werkzeugfehler (Bedienfehler, Eingabe nicht gefunden, ungültige Konfiguration). `verify`: 0 gleich,
1 Abweichung, 2 bei ungültigem oder fehlendem Manifest (A-82). `report`: 0; 2 bei fehlender oder ungültiger
`results.json`, unbekannter Sprache oder unbekanntem Format oder PDF-Fehler (z. B. fehlender PDF-Browser, mit Hinweis
auf `install_pdf_browser.py`). `scan`, `convert`, `manifest`: 2 bei Bedien- und Werkzeugfehlern (z. B. Pfad nicht
gefunden). Seit P6 (A-90, A-91): `vault verify` 0 intakt, 1 Abweichung (auch fehlendes Protokoll oder nicht
gefundener erwarteter Kopf), 2 Werkzeugfehler (kein Vault, Link, kein Ordner, gesperrt, ungültiger Kopf-Hash);
`vault init`, `vault log`, `vault consent add` 0 oder 2; `vault` und `vault consent` ohne Befehl zeigen die Hilfe
und enden mit 2; `check` endet zusätzlich mit 2 bei ungültiger Rolle, einem Link oder Nicht-Ordner im Vault-Pfad,
ungültiger `consents.yaml` oder ungültigem `[consent]`. Seit P9 (A-93 bis A-99): `check` endet zusätzlich mit 2 bei
ungültiger `roles.yaml`, `risks.yaml` oder `retention.yaml` (auch `min_until` vor `created` plus drei Jahren), wenn
eine geladene Regel sie braucht, und bei einem Link an einer neuen Vault-Datei; `vault export` 0 geschrieben, 2 bei
jeder Ablehnung, nie 1; `diff` 0 kein neuer Fehlerbefund, 1 neue Fehlerbefunde, 2 Werkzeugfehler; `report --format
dossier` 0 oder 2. Eine Rollenwarnung (`cli.vault.role_not_permitted`) ändert keinen Exitcode. Ein Zugriffsereignis,
das nicht geschrieben werden kann, ändert keinen Exitcode. Jeder Befehl endet mit dem festen Satz (A-08).

**CI-Integration (P9, A-98):** GitHub Action `uses: Ammxri/neurogrid@<tag>` (Datei `action.yml`) mit den Eingaben
`path` (Pflicht), `rulepacks` (je Zeile eines), `config`, `out` (Standard `neurogrid-results/results.json`), `strict`,
`role`, `report-formats` (Standard `html`, `none` überspringt), `report-lang` (Standard `zh,en`), `baseline` (schaltet
`diff` ein), `fail-on` (`errors`, `new-errors`, `never`; Standard `errors`), `neurogrid` (Pfad des installierten
Starters, Standard `neurogrid`), `allow-hosted-runner` (Standard `false`) und den Ausgaben `exit-code`,
`diff-exit-code`, `results`; auf einem Runner, dessen `runner.environment` nicht `self-hosted` ist, Abbruch mit Exit 1,
außer mit `allow-hosted-runner: true`. GitLab: `include` von `ci-templates/gitlab-ci.yml`, ein Job mit `extends:
.neurogrid` (POSIX sh) oder `.neurogrid-powershell` (Windows mit PowerShell), Variable `NEUROGRID_RUNNER_TAG` (Pflicht, Tag des eigenen
Runners), die Variablen `NEUROGRID_*` wie die Eingaben der Action, der Starter in `NEUROGRID_COMMAND`. Beides lädt
nichts hoch; `docs/<lang>/ci.md` zeigt die Vorlage und die Eingaben.

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
- [ ] volle Suite nur in der CI (4.0): die sechs Testjobs von `ci.yml` grün, Zahlen aus den Notice-Annotationen
      (4.7.19); auf `27c3e90` windows-latest 3681 bzw. 3682 bestanden, 16 bzw. 15 übersprungen (3697 Tests),
      ubuntu-24.04 je 3605 bestanden, 97 übersprungen (3702 Tests), 0 fehlgeschlagen; lokal nur die betroffenen
      Tests mit `NEUROGRID_REQUIRE_PDF=1`, `PYTHONWARNDEFAULTENCODING=1` und `UV`, aus Git Bash (1.6 Punkt 23), auf
      `27c3e90` unter 3.12 184 bestanden, 5 übersprungen, 52 abgewählt und unter 3.11 18 bestanden, 4 übersprungen
      (4.7.20); lokale volle Läufe früherer Runden als Geschichte (`dcec9bd` 3647 bestanden, 21 übersprungen,
      127 abgewählt, 1 fehlgeschlagen; A-88)
- [ ] Abdeckung: `coverage_gates.py` → Kern ≥ 90 %, Prüfer ≥ 80 % (zuletzt 97,1 % / 97,2 % lokal in P4; in der CI auf
      `27c3e90` je Testjob Kern 93,3 % (ubuntu-24.04), 93,4 % (windows-latest × 3.11) bzw. 93,5 % (windows-latest ×
      3.12/3.13), Prüfer 97,3 %; 4.7.19)
- [ ] Runner-Bedingungen lokal nachgestellt (4.7.14): `tests/packaging/test_install_ps1.py` mit `TEMP`/`TMP` in
      8.3-Schreibweise grün; die BrainVision-Tests aus `test_review_p2_convert.py` und `test_review_p2_formats.py` mit
      `PYTHONUTF8=1` grün; `tests/docs/test_docs_browser.py` mehrfach grün
- [ ] Hilfsprozesse (A-89): `tests/unit/test_processes.py`, `tests/unit/test_quality_sample.py` und
      `tests/integration/test_worker_console.py` grün, unter Windows mit Python 3.11 und 3.12 (die POSIX-Zweige nur in
      der CI, 4.7.18); `check --jobs 4` auf einem Korpus-Datensatz mit leerem stderr
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
      all criteria of this run met“; `summary.md` mit V-01-Checkliste und V-06-Zeile (4.7.8); auf `dcec9bd` 5/6 wegen
      des Konsolenbefunds (4.7.17), auf `18da12f` 6/6, alle Kriterien erfüllt (151 min), auf dem Endstand `27c3e90`
      6 von 6 Datensätzen in 5 Formaten bestanden, alle Kriterien erfüllt, 0 Probleme, V-01 erfüllt, V-06 ja (149 min 28 s; `.local/p5/ci3/g1_summary_27c3e90.md`) (4.7.20)
- [ ] zh-Prüfpaket: `zh_review_package.py --g1 <letzter G1-Lauf>` → Exit 0, Markdown plus zwei Beispiel-PDFs (4.7.8),
      erzeugt nach dem letzten G1-Lauf

**Auslieferung**
- [ ] `build_docs.py --site-dir site` → „documentation built and checked“, 0 Netzereignisse, keine Zeile „licence
      pending …“ (seit D-17; vorher je eine für focus-visible und material-design-color)
- [ ] `notices.py --wheelhouse .local/notices-wheels --check` (oder `--download --check`) → aktuell, kein
      „incomplete“, Exit 0 (seit D-17)
- [ ] `bundle.py build` beider Plattformen + `bundle.py verify` → Exit 0; zwei Bauten byte-gleich
      (`pytest -m bundle tests/packaging/test_bundle_real.py` → 4 bestanden; während des Laufs nicht committen)
- [ ] Windows-Reinraum `cleanroom_windows.ps1 … -NoOsAudit [-PdfBrowserZip … -PdfBrowserSha256 …]` → Exitcodes wie in
      4.7.5 (mit install-over-limit 2, report-pdf-without-shell 2); im `-Evidence`-Ordner `exit-codes.txt`,
      `<schritt>.out.log`/`.err.log`, `summary.txt`, `temp-left.txt` (leer)
- [ ] Präfixgrenze (A-87): `install.cmd -SkipSignatureCheck -Prefix <102 Zeichen>` → Exit 2, nichts angelegt;
      `<101 Zeichen>` → Exit 0
- [ ] optional: Flugmodus-Test (4.7.5)

**CI (GitHub Actions, `https://github.com/Ammxri/neurogrid`)**
- [x] Push auf `dev`, Läufe von `ci.yml` und `offline.yml` (erledigt, 4.7.9, 4.7.12, 4.7.16, 4.7.18, 4.7.19)
- [x] Bündel-Tests bei jedem Push auf `dev` und `main` (D-15; seit Review R10, `offline.yml` Push `dev`/`main`);
      grün auf `55335ca` (Lauf 40403791782), `dcec9bd` (Lauf 40476578452), `18da12f` (Lauf 40609866836) und
      `27c3e90` (Lauf 40680346176), Linux-Reinräume, glibc-Ablehnung
      `ubuntu:18.04`, offline-strace, `pdf-debian12`, Windows-Reinraum mit WFP-Audit unter PowerShell 5.1 und 7
- [x] Testjobs von `ci.yml` (Windows und Linux × 3.11–3.13) mit Abdeckungs-Gates und Vergleich grün – auf `55335ca`
      rot, auf `dcec9bd` grün (Lauf 40476578603, 4.7.16)
- [x] dasselbe auf dem Endstand mit den POSIX-Zweigen von A-89: auf `18da12f` rot (Lauf 40609866806, 4.7.18), nach
      der dritten CI-Fix-Runde auf `27c3e90` grün (Lauf 40680346160, 4.7.19)
- [ ] Annotationen ohne Anmeldung lesen (4.7.19): Läufe über `actions/runs?head_sha=<voller SHA>`, Jobs je Lauf,
      Annotationen je Job über die Check-Run-API; bei rotem Lauf die Fehler, seit `2a49a0c` bei grünem Testjob
      Testzahlen und Abdeckung als Notice
- [ ] Release-Gate (`dd9ab93`): `release.yml` ruft `ci.yml` als Job `suite`, der Entwurf braucht `[build, suite,
      test]`; erst der erste Tag-Lauf prüft das auf GitHub [NV]

**P6 (4.8)**
- [ ] `neurogrid.__version__` = `0.2.0.dev0`; `--help` zeigt die Gruppe `vault`
- [ ] `gen_schemas.py --check` (acht Schemas, mit access_event und consents) und `gen_docs.py --check` → Exit 0
- [ ] `check_matrix_coverage.py` → „P6: schließt 10 ab, trägt zu 5 bei“
- [ ] betroffene Tests der drei Bereiche (4.8.3–4.8.5) und `tests/integration/test_p6_cross.py` grün; unter Windows
      übersprungen: die POSIX-Zweige, ohne erlaubte Datei-Links auch die Tests mit verlinkter Datei
- [ ] Durchlauf von Hand 4.8.10: `vault init`, sechs `vault consent add`, `vault log`, zwei `check` bytegleich,
      `vault verify` Exit 0; nach einer geänderten Zeile Exit 1 und CORE-NV03-01 verletzt
- [ ] CI auf dem Endstand von P6 (`0ffdd90`): ganz grün (`ci` 41422859481, `offline` 41422859830)
- [ ] `tests/unit/test_norm_independence.py` grün: jede Zeile, die `yyt2029` nennt, steht genau in `KNOWN`

**P9 (4.9)**
- [ ] `neurogrid.__version__` = `1.0.0.dev0`; `--help` zeigt `diff` und `vault export`; `report --help` nennt `dossier`
- [ ] `gen_schemas.py --check` (13 Schemas, mit roles, risks, retention, export_index und diff) und `gen_docs.py --check`
      → Exit 0
- [ ] `check_matrix_coverage.py` → „P9: schließt 13 ab, trägt zu 1 bei“
- [ ] betroffene Tests der vier Bereiche (4.9.3–4.9.6) und `tests/integration/test_p9_cross.py` (neun Tests) grün; unter
      Windows übersprungen: die POSIX-Zweige, ohne erlaubte Datei-Links die Tests mit verlinkter Datei, ohne pwsh die
      Tests mit PowerShell 7
- [ ] `vault init` auf einem Vault aus P6 legt Register und PIA-Dateien an; der nächste `check` zeigt drei Warnungen
      von NV05 und NV04 grau
- [ ] `retention.yaml` mit `min_until` vor `created` plus drei Jahren → `check` Exit 2, keine results.json, kein Ereignis
- [ ] `vault export` → ZIP mit genau den Teilen und `index.json`; das archivierte Protokoll endet mit dem Ereignis
      `export`, `vault verify --expect-head <Kopf aus index.json>` Exit 0
- [ ] `diff` → Exit 1 für einen neuen Fehlerbefund, 0 in der Gegenrichtung; `--format json` allein auf stdout
- [ ] `report --format dossier` (PDF-Browser nötig) → `dossier.pdf`, zwei Bauten ohne `--config` bytegleich
- [ ] CI auf dem Endstand von P9 (`5596a8d`): grün (`ci` 41447040471, `offline` 41447040492, `ci-integration` 41447040527)
- [ ] `tests/unit/test_norm_independence.py` grün (neue Nennungen der Norm in `KNOWN`)

**Nur mit dem Projektverantwortlichen (offen, STOPP G1)**
- [x] Entscheidung zu den acht Lücken in `known_missing.toml` (D-17); fehlende Lizenztexte abgelegt (D-15, D-16,
      D-17), `known_missing.toml` leer und Notices neu
- [x] M14 Option B, zh-Prüfung der P6-Texte Option C, zh-Paket nach der zweiten CI-Fix-Runde (D-17)
- [ ] Anfrage an die Validator-Entwickler versendet (D-16)
- [ ] zh-Prüfung mit dem Paket nach dem letzten G1-Lauf (neue Schlüssel und Sätze in 4.7.8), Sichtprüfung der
      Beispiel-PDFs
- [x] Bestätigung A-78..A-89 und R16-Installationshinweis (D-18, 29.10.2026)
- [ ] Kenntnisnahme der bekannten Grenzen (4.7.21, Abschnitt 8); zh-Prüfung mit den Kernbegriffen von P6 (FORTSCHRITT)
- [ ] für STOPP G2 und v1.0: Bestätigung A-90..A-99, Kernbegriffe von P9 in der zh-Prüfung (vollständige Texte vor
      v1.0), Sichtprüfung einer Nachweismappe (REP-08), eigener Runner für den echten Lauf von `ci-integration.yml`
      (D-19), juristische Prüfung der PIA-Vorlage vor der ersten echten Verwendung, echter Lauf der GitLab-Vorlage
- [ ] danach Release-Zweig aus `c4f240a` (D-19), Merge nach `main`, `0.1.0`, Tag `v0.1.0`, `release.yml`, `publish-pypi.yml` (TestPyPI/PyPI, Trusted
      Publishing), `mirror-gitee.yml` (Spiegel) und das Gitee-Release von Hand aus dem Artefakt des Jobs
      `gitee-release` (R15); `docs.yml` und `corpus.yml` laufen erst mit `main`
