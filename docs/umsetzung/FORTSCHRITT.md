# NeuroGrid – Fortschritt

Bei jedem Sitzungsneustart zuerst lesen: diese Datei, [ANFORDERUNGEN.md](ANFORDERUNGEN.md),
[ENTSCHEIDUNGEN.md](ENTSCHEIDUNGEN.md). PRD: `.local/prd/PRD-1-NeuroGrid.pdf` (Text: `*.layout.txt`, `*.raw.txt`;
Tabellen §12/§13 sind in `*.raw.txt` besser lesbar; Architekturbild: `architektur-s8.png`).

## Aktueller Stand

**Phase 2 – STOPP 2.** Umsetzungskonzept in [KONZEPT.md](KONZEPT.md); wartet auf Freigabe. Kein Produktivcode.
Git: `main` (Doku-Commit), Arbeitszweig `dev`.

## Verlauf

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

Nach Freigabe des Konzepts: Phase P1 (Gerüst und Durchstich), danach autonom bis zum STOPP nach P5 (v0.1, Gate G1).
