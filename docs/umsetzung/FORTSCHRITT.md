# NeuroGrid – Fortschritt

Bei jedem Sitzungsneustart zuerst lesen: diese Datei, [ANFORDERUNGEN.md](ANFORDERUNGEN.md),
[ENTSCHEIDUNGEN.md](ENTSCHEIDUNGEN.md). PRD: `.local/prd/PRD-1-NeuroGrid.pdf` (Text: `*.layout.txt`, `*.raw.txt`;
Tabellen §12/§13 sind in `*.raw.txt` besser lesbar; Architekturbild: `architektur-s8.png`).

## Aktueller Stand

**Phase P3 umgesetzt; STOPP R4 (NG-N02).** Die 1-GB-Messung verfehlt die Grenze aus A-50 für 128 und 256
Kanäle; die Entscheidung des Projektverantwortlichen steht aus (Optionen im Eintrag unten). Konzept freigegeben
(D-08 bis D-13), Freigabemodus A bis zum STOPP nach P5. Git: `main` (Doku-Commit), Arbeitszweig `dev` (lokal;
Push erst mit Repo-URL, D-09).
Offen beim Nutzer: GitHub-Repo-URL (TECH-05/TECH-11, Linux-Lauf), GB/T-47127-PDF vor P7, YY/T-2029-Text vor P8,
ISO-TS vor P10, muttersprachliche zh-Prüfung vor v0.1, Docker Desktop bei Gelegenheit.

## Verlauf

### 2026-10-21 – P3 Signalqualität
- **Abgeschlossen:** M06, M07, M08, M09, MET-01, LIB-01, LIB-04, LIB-06, LIB-07.
- **Teilweise:** NG-F07 (alle Werte im JSON; Laufzeit siehe NG-N02), NG-N02 (STOPP R4, siehe unten).
- **Beigetragen zu:** NG-N01, NG-N03, NG-N07, NG-N08, MET-02, REP-04.
- **Gebaut:**
  - Paket `neurogrid.quality`:
    - Signalquellen: eigener EDF/BDF-Leser über ein Speicherabbild, MNE für BrainVision/EEGLAB/FIF.
    - Stream über die volle Länge: M07, M08, Signal-Hash; in 4 Threads, Ergebnis davon unabhängig.
    - Deterministische Stichprobe für M06 (pyprep), M09a (autoreject) und M09b (picard + ICLabel über onnxruntime).
    - Montage-Quellen `electrodes.tsv` > Datei > Standardmontage, auch für einen Teil der Kanäle.
    - Prozesspool für `--jobs`; ein sterbender Prozess kostet nur seine Aufnahme.
  - Sieben Regeln im Paket `core`:
    - CORE-M06-01, CORE-M07-01, CORE-M07-02, CORE-M08-01, CORE-M08-02, CORE-M09-01, CORE-M09-02.
    - Schwellen von M06, M07 und M09 kalibriert: 0,30625, 0,407669, 0,305083 und 0,6.
    - Herkunft im Paket, Protokoll `rulepacks/calibration/core.json`.
  - Konfiguration `[quality]`, Option `check --jobs`; results.json mit `metrics` und `sample` je Aufnahme.
  - Der Bericht zeigt den Ausweis der Stichprobe; Texte zh/en/de.
  - Werkzeuge:
    - `tools/calibrate.py` (Kalibrierung und `--check`)
    - `tools/gen_large_edf.py` (EEG-ähnliche 1-GB-EDF)
    - `tools/benchmark.py` (NG-N02)
  - Drei Fixtures `edf_quality_*` (Dipolquellen); `neurogrid/quality/` zählt zur Abdeckungsgruppe „Prüfer“.
- **Tests und Review:**
  - Fünf Agenten haben je einen Testbereich geschrieben, zwei weitere Tests und Produktivcode gegengeprüft.
  - Erkennungstests gegen feste Sollwerte, alle erreicht:
    - M07: 8 von 8 Brumm-Kanälen erkannt, kein Fehlalarm.
    - M08: Zählung fenstergenau.
    - M06: 4 von 4 schlechten Kanälen bei 32 Kanälen gefunden.
    - M09a: 0 / 0,2 / 0,5 bei 0 / 20 / 50 % Artefakt-Epochen.
    - M09b steigt mit Augen- und Muskelquellen.
  - Gefunden und behoben, jeweils mit Test:
    - Ein konstanter Kanal erhielt einen M07-Wert aus Rundungsrauschen.
    - Eine Aufnahme ohne Signal bekam M09-Werte aus dem Filterrauschen.
    - M06 brach unter 14 Kanälen ab (pyprep-RANSAC).
    - Die Vorlagepositionen lagen im MRI- statt im Kopfkoordinatensystem; danach neu kalibriert.
    - Folgende Fälle führten zu Exit 2: Überlauf zu NaN, unendliche Netzfrequenz im FIF-Kopf, `--jobs` > 61 unter Windows.
    - Doppelte Kanalnamen verwarfen alle Stream-Werte.
    - Ein Seed ≥ 2³² ließ M06 und M09 scheitern.
    - Die Wahl unter mehreren `electrodes.tsv` war falsch.
    - Der Bericht brach bei abweichender `sample`-Form ab.
    - Ein Fenster mit einem einzigen Wert galt als flach.
    - Die Stichprobe las Kanal für Kanal.
    - Fehlende Telemetrie-Sperre für onnxruntime.
  - Annahme A-79 neu: präzisiert A-18, A-19, A-21 und A-60.
- **Ergebnisse (lokal, Windows 11):**
  - pytest Python 3.12: 1722 bestanden, 7 übersprungen (Datei-Symlinks, POSIX).
  - pytest Python 3.11: 1722 bestanden, 7 übersprungen; Ergebnis gleich 3.12 bis auf `environment`.
  - pytest Python 3.13: 1722 bestanden, 7 übersprungen; Ergebnis gleich 3.12 bis auf `environment`.
  - Korpus: 28 bestanden (6 Datensätze, 5 Formate). Dazu: alle Werte auf den 22 OpenNeuro-Aufnahmen gemessen, Montage-Quellen nach A-60/A-79, PSG mit 3 Kanälen not_checkable, die Kalibrierung aus dem Korpus nachgerechnet.
  - Byte-Gleichheit bei `--jobs 1/4` und BLAS 1/4 Threads (Test, echter Prozess).
  - ruff und mypy (src, tools) sauber.
  - Abdeckung Kern 97,3 %, Prüfer 97,4 %; `neurogrid/quality/` 97–100 %.
  - Lizenz-Gate grün; Schemas, Fixtures und Matrix reproduzierbar bzw. vollständig.
  - `calibrate.py --check` grün.
- **NG-N02 (A-50):** `tools/benchmark.py`, 1-GB-EDF+C mit 512 Hz, Rechner ohne Last (8/16 Kerne), `--jobs 1`:

  | Kanäle | Laufzeit | Spitzenspeicher | A-50 (< 150 s) |
  |---|---|---|---|
  | 64 | 94,2 s | 1,7 GB | erfüllt |
  | 128 | 159,5 s | 2,3 GB | verfehlt |
  | 256 | 294,6 s | 3,4 GB | verfehlt |

  - Aufschlüsselung bei 256 Kanälen: Stream 25 s, Vorbereitung 12 s, pyprep 101 s, autoreject 131 s, ICA+ICLabel 16 s.
  - Die PRD-Grenze von 5 min hält dieser Rechner ein, bei 256 Kanälen nur knapp.
  - autoreject mit 4 Prozessen ist byte-gleich, spart aber nur 18 %, weil die lokale Kreuzvalidierung seriell läuft.
  - **STOPP R4:** Entscheidung beim Projektverantwortlichen. Optionen:
    1. Parallelisierung innerhalb einer Aufnahme mit `--jobs`: Stream parallel zur Stichprobe, autoreject mit mehreren Prozessen und parallel zur ICA. Die Methodik bleibt unverändert. Schätzung aus den Schrittzeiten: 128 Kanäle etwa 120 s, 256 Kanäle etwa 220–230 s.
    2. A-50 anpassen: 150 s für 64 und 128 Kanäle, für 256 Kanäle die PRD-Grenze von 5 min.
    3. Die Methodik für viele Kanäle ändern, z. B. RANSAC und autoreject nur auf einer festen Kanalauswahl. Das weicht von A-19 ab und wird nicht empfohlen.
    4. Die seriellen Schleifen von pyprep-RANSAC und autoreject selbst parallelisieren. Hoher Aufwand, bindet an Bibliotheksinterna.
    - Empfehlung: 1 und 2 zusammen.
- **Nicht verifiziert:**
  - Linux- und CI-Lauf (TECH-05, TECH-11, D-09).
  - NG-N02 auf einem Runner mit 4 vCPU/16 GB.
- **Offen zur Entscheidung:**
  - STOPP R4 (NG-N02).
  - Zeitangaben ab 27,8 h sind nur auf 1 s genau (6 signifikante Stellen, A-61, A-79).
  - Restpunkte aus A-78.

### 2026-10-20 – P2 Formate und BIDS
- **Abgeschlossen:** NG-F01, NG-F02, NG-F05, NG-F06, M01 bis M05, CLI-01, CLI-02, RP-09, LIB-02, LIB-03, LIB-08, CON-03. LIB-09 bleibt bewusst abgewichen (D-11); der Ersatz ist umgesetzt.
- **Beigetragen zu:** LIB-01 (Filter und ICA folgen in P3, A-78), ARC-04, NG-N01, NG-N05, UF-02, UF-04, DM-07, MET-02, NG-N08.
- **Gebaut:**
  - Adapter für BDF, BrainVision, EEGLAB (MAT v5/v7.3) und FIF; EDF+D wird gelesen.
  - Discovery mit Begleitdateien, verwaisten Dateien und weiteren bekannten, nicht unterstützten Formaten.
  - BIDS-Metadaten nach dem Vererbungsprinzip, mit Herkunft je Feld (A-04). Entitäten liest MNE-BIDS. Zuordnung im Rohordner über Tabelle oder Muster.
  - Prüfungen:
    - Paket `core`: M02-01/02, M03-03, M04-01 bis -05, M05-01/02; zusammen 17 Regeln.
    - Paket `bids`: BIDS-STO-001 bis -003 mit dem gebündelten Validator; eigene Texte für 200 Validator-Codes in zh/en/de.
  - `convert --to bids` über MNE-BIDS: mit Zuordnungsvorlage, `--strip-identifying-headers`, Verarbeitungsschritten und Validatorlauf auf der Ausgabe.
  - Korpus-Werkzeug `tools/corpus.py` mit Sperrdatei (297 Dateien, SHA-256), `DATA_SOURCES.md` und Korpus-Tests (`-m corpus`).
  - Fixtures für alle Formate und zwei BIDS-Datensätze: einer vollständig, einer mit je einem Fehler pro Regel.
- **Review von P2:**
  - Ein Agent je Testmodul, jedes Modul gegengeprüft. Dabei rund 20 Fehler gefunden und behoben, u. a.:
    - Die Leseprüfung folgte Verweisen außerhalb des Ordners.
    - Beschädigte Dateien wurden umgewandelt.
    - Eingebettete und epochierte EEGLAB-Daten brachen `convert` ab.
    - Das New-Segment-Datum blieb beim Entfernen der Kennungen stehen.
  - Review in fünf Richtungen mit Gegenprüfung: 48 Befunde bestätigt, 9 verworfen. Behoben in fünf getrennten Gruppen, jede mit eigener Gegenprüfung. Schwerpunkte:
    - Pfadsicherheit: BrainVision-Kopf wie MNE gelesen, FIF-Split-Ketten, HDF5-Links in EEGLAB, Links im Validator-Lauf.
    - Robuste Umwandlung: Ein Fehler bei einer Aufnahme bricht den Lauf nicht mehr ab, und die Ausgabe wird zurückgesetzt.
    - Kanaltypen nach Label und aus `channels.tsv`.
    - Ein Validator-Befund je Code.
  - In der Gegenprüfung zusätzlich gefunden und behoben: quadratische Laufzeiten bei manipulierten Köpfen und Kommentaren, mehrdeutige EEGLAB-Strukturen.
  - Neue bzw. überarbeitete Annahmen: A-77, A-78. Phasenplan: LIB-01 schließt in P3 ab.
  - Praxistest auf dem Korpus: Golden-Liste echter Metadatenfehler bestätigt (ds000248, ds002778, ds004148, ds004504); ds003775 ohne Fehler.
- **Ergebnisse (lokal, Windows 11):**
  - pytest 1449 bestanden unter Python 3.11, 3.12 und 3.13; 7 übersprungen (Datei-Symlinks brauchen den Entwicklermodus, POSIX-Fälle).
  - Korpus: 20 bestanden (6 Datensätze, 5 Formate); je eine Aufnahme pro Format mit und ohne `--strip-identifying-headers` umgewandelt, jeweils 0 Validator-Fehler.
  - ruff, `mypy --strict` (Kern) und mypy über `src` und `tools` sauber.
  - Abdeckung: Kern 97,3 %, Prüfer 97,0 %.
  - Lizenz-Gate grün; Fixtures, Schemas, Montage-Namen und Matrix reproduzierbar bzw. vollständig.
  - Zwei `check`-Läufe byte-gleich, zwei `convert`-Läufe dateigleich; 3.11 und 3.12 gleich bis auf `environment`.
  - Rauchtest unter Windows PowerShell 5.1: Exitcodes 0/1/1/0/0/0/2/0, Berichte zh/en.
- **Nicht verifiziert:**
  - „Validator unter strace ohne connect“: Der CI-Job `offline-strace` ist angelegt, läuft aber erst nach einem Push (D-09); lokal gibt es kein Linux und kein Docker.
  - Linux- und CI-Lauf allgemein (TECH-05, TECH-11).
- **Offen zur Entscheidung (A-78):**
  - Muster mit überlappenden Wiederholungen.
  - Speicherbedarf bei großen MAT-v5-Dimensionen.
  - Sonderdateien (FIFO).
  - Kanaltyp-Tabelle für Rohordner.

### 2026-10-11 – P1 Gerüst und Durchstich
- **Abgeschlossen:** TECH-02, TECH-03, TECH-04, TECH-09, TECH-12, ARC-02, ARC-03, LIB-10, DM-01 bis DM-07, DM-10,
  RP-01, RP-04, RP-12, V-08. **Teilweise:** TECH-11 (CI wartet auf die Repo-URL, D-09).
- **Beigetragen zu:** TECH-01, TECH-05, TECH-10, NG-F11, NG-F12, NG-F13, NG-F14, NG-F18, M01, M03, MET-02, CLI-01,
  CLI-03, CLI-05, REP-03, NG-N03, NG-N05, NG-N07, NG-N08, CON-01, ARC-01, RP-05.
- **Gebaut:**
  - Repository nach §13 mit LICENSE/NOTICE/REUSE, pyproject/uv.lock (exakte Pins, `no-build`), CI-Workflow.
  - Kern `neurogrid.kernel`: Regelmotor, Befunde, Kanonisierung, Matcher, i18n, Hashing, Nachweis-Modell, Abdeckung, Netzwerkschutz, Pfad- und Eingabesicherheit.
  - Konfiguration `neurogrid.toml` (strikt), EDF-Adapter → Datenmodell, discover.
  - Paket `core` mit M01/M03, Befehle `scan`, `check`, `report` (HTML zh/en), Schemas, Werkzeuge (Matrix, Fixtures, Schemas, Abdeckung, Lizenzen, Commit-IDs).
- **Review von P1:** drei Durchgänge, jeweils mit Gegenprüfung aller wesentlichen Befunde.
  - Erster Durchgang: drei Prüfrichtungen (Korrektheit, Sicherheit/Datenschutz, DoD-Treue).
  - Zweiter und dritter Durchgang prüften die Korrekturen und suchten Regressionen.
  - Weitere Funde dieser Durchgänge, alle behoben: Überläufe im EDF-Kopf, Hypnogramme als „unlesbar“, MNE-Warnungen mit Benutzerpfad, stille Links und gesperrte Ordner in `check`, Gerätepfade (`\??\`), exponentieller Ausnahme-Matcher, Ausnahme über den Dateinamen abhängig von `--show-paths`.
  - Alle bestätigten Befunde des ersten Durchgangs behoben, u. a.:
    - Absturz bei doppeltem YAML-Schlüssel (Exit 1 mit Traceback)
    - NaN-/Inf-Kopfwerte (Exit 2 ohne results.json)
    - Regelpaketpfade aus der toml relativ zum Arbeitsverzeichnis
    - `--show-paths` änderte Ausnahmen und Exitcode
    - Ordnerformate .mff/.mefd blieben unbemerkt
    - `--rulepack` wurde kleingeschrieben
    - DNS-Lücken im Netzwerkschutz
    - Klarnamen aus Ausnahme-Mustern in den Ausgaben
    - laxe Konfiguration
  - Neue bzw. überarbeitete Annahmen: A-49, A-64, A-66 bis A-76.
  - Praxistest auf echten Korpusdaten (PSG-IPA, ds003775): Exit 0, alle 75 Hypnogramme lesbar, echtes Aufnahmedatum in ds003775 als Hinweis erkannt.
  - Phasenplan korrigiert: RP-05 → P4, ARC-01 → P6, TECH-01 → P12.
- **Ergebnisse (lokal, Windows 11):**
  - pytest 347 bestanden unter Python 3.11, 3.12 und 3.13; 4 übersprungen (Datei-Symlinks brauchen den Entwicklermodus, POSIX-Fälle).
  - ruff und `mypy --strict` (Kern) sauber.
  - Abdeckung Kern 97,4 %, Prüfer 95,2 %.
  - Lizenz-Gate grün (Laufzeit, Dev); Fixtures und Schemas reproduzierbar.
  - Zwei Läufe byte-gleich; 3.11/3.12/3.13 gleich bis auf `environment`.
  - Rauchtest unter Windows PowerShell 5.1: Exit 0/1/2/0, Berichte zh/en.
- **Nicht verifiziert:** Linux und CI-Lauf (TECH-05, TECH-11, NG-N04), weil die Repo-URL fehlt (D-09). Docker steht nicht zur Verfügung.

### 2026-10-11 – Phase 2
- Antworten auf F1–F7: alle Empfehlungen freigegeben → D-01 bis D-07 in ENTSCHEIDUNGEN.md.
- Umgebung: uv 0.13.0 (per pip), Python 3.11.17 und 3.12.15 (uv), Prototyp-venv mit dem geplanten Stack.
- Lokales Git-Repository angelegt (D-07).
- Fünf Machbarkeits-Prototypen (Wegwerfcode im Scratchpad):
  - S1 Validator/BIDS
  - S2 Laufzeit 1 GB: 89 s gemessen
  - S3 PDF/CJK
  - S4 Abhängigkeiten/Lizenzen
  - S5 Testkorpus: 1,06 GB nach `.local/corpus/`
  Ergebnisse in KONZEPT Abschnitt 8. Daraus folgen neue oder geänderte Annahmen: A-06, A-18, A-19, A-22, A-26, A-27, A-29, A-46 bis A-49.
- Nebenwirkung des Prototyps S4: Er hatte ungefragt CPython 3.15 in uv installiert; wieder entfernt.
- Konzept: Architektur, Datenmodell, Schnittstellen, Rollen, Sicherheit/Regulatorik, Teststrategie, Risiken, Phasenplan P1–P12.
- Prüfung des Konzepts durch drei unabhängige Prüfer (PRD-Treue, Technik/Phasen, Regulatorik/Datenschutz/Lizenzen):
  82 Befunde (0 Blocker, 43 wesentlich, 39 klein).
  - Eingearbeitet in KONZEPT.md und ENTSCHEIDUNGEN.md: A-00 bis A-61 überarbeitet bzw. neu.
  - Fünf Punkte brauchen eine Entscheidung (E1–E5).
  - Wichtigste Änderungen: Reihenfolge v0.2 vor v1.0; Determinismus (Stichtag, kein Vault-Hash in results.json); Datenschutz-Ausgabefilter; Pfad- und Eingabesicherheit; Offline-Nachweis auf OS-Ebene; Lizenzumfang inkl. Binärteile; Umgang mit Normtexten.
- Selbst nachgeprüft:
  - Linux-Wheels von numpy/scipy bündeln libquadmath (LGPL) und libgfortran.
  - Die Chrome Headless Shell ist ein Google-Chrome-Build mit FFmpeg (LGPL).
  - edfio erkennt EDF+D.
  - Lokal gibt es kein Linux (WSL nur docker-desktop, gestoppt).
- `tools/check_matrix_coverage.py`: 166/166 Zeilen mit genau einer abschließenden Phase, keine unbekannte ID.
- In öffentlichen Dokumenten heißt es „Projektverantwortlicher“ statt „Auftraggeber“ (unbezahltes Studienprojekt, PRD §22).
- Prioritäten in der Matrix heißen jetzt v0.1/v0.2/v1.0/v1.x, damit sie nicht mit den Phasen P1–P12 kollidieren.

### 2026-10-11 – Phase 0 und 1
- PRD vollständig gelesen (22 Seiten, Text und Architekturbild extrahiert).
- Anforderungsmatrix erstellt: 166 Zeilen (151 Anforderungen, 9 Nicht-Ziele, 6 Geschäftsaufgaben).
  Gegengeprüft durch eine unabhängige zweite Extraktion (272 Einzelpunkte) – keine fehlende Anforderung mehr.
- Lückenanalyse: 50 Punkte, davon 7 Blocker-Fragen (F1–F7) und 44 dokumentierte Annahmen (A-00 bis A-43).
- Externe Fakten geprüft: Bibliotheksversionen und Lizenzen (PyPI), BIDS-Validator-Auslieferung, BIDS 1.11.x,
  Playwright/Chromium, Noto-CJK, MkDocs-Status, Verfügbarkeit der Normtexte, öffentliche Testdatensätze.
- Umgebung: Python 3.13 und 3.14 vorhanden; uv, Deno, gh fehlen; 323 GB frei.

## Nächster Schritt

P2 (Formate und BIDS): Adapter BDF, BrainVision, EEGLAB, FIF, EDF+D; Korpus-Werkzeug und DATA_SOURCES.md;
`convert --to bids`; Validator-Integration und Paket `bids`; M01–M05 vollständig (A-46). Danach P3–P5 und STOPP G1.
