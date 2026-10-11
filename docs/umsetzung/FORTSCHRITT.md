# NeuroGrid – Fortschritt

Bei jedem Sitzungsneustart zuerst lesen: diese Datei, [ANFORDERUNGEN.md](ANFORDERUNGEN.md),
[ENTSCHEIDUNGEN.md](ENTSCHEIDUNGEN.md). PRD: `.local/prd/PRD-1-NeuroGrid.pdf` (Text: `*.layout.txt`, `*.raw.txt`;
Tabellen §12/§13 sind in `*.raw.txt` besser lesbar; Architekturbild: `architektur-s8.png`).

## Aktueller Stand

**Phase P1 abgeschlossen, P2 als Nächstes.** Konzept freigegeben (D-08 bis D-13), Freigabemodus A bis zum
STOPP nach P5. Git: `main` (Doku-Commit), Arbeitszweig `dev` (lokal; Push erst mit Repo-URL, D-09).
Offen beim Nutzer: GitHub-Repo-URL (TECH-05/TECH-11, Linux-Lauf), GB/T-47127-PDF vor P7, YY/T-2029-Text vor P8,
ISO-TS vor P10, muttersprachliche zh-Prüfung vor v0.1, Docker Desktop bei Gelegenheit.

## Verlauf

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
