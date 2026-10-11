# NeuroGrid – Anforderungsmatrix

Quelle: „PRD 1 – NeuroGrid: Prüfstand für EEG-Datensätze“ (Stand 10.10.2026, 22 Seiten).
Lokale Kopie: `.local/prd/` (nicht versioniert). Fundstellen: `§Abschnitt S.Seite`.

Diese Datei ist die Checkliste für alle Phasen. Eine Zeile wird erst auf `erfüllt` gesetzt, wenn sie
ausgeführt und geprüft ist; der Beleg steht in „Nachweis“. Spalte „Klärung“ verweist auf die
Blocker-Fragen (F1–F7, siehe unten) und die Annahmen (A-xx) in [ENTSCHEIDUNGEN.md](ENTSCHEIDUNGEN.md).

**Priorität laut PRD.** Die PRD vergibt keine Prioritätsstufen, sondern Versionen mit Termin (§6):
**P1** = v0.1 (22.11.2026) · **P2** = v0.2 (3.1.2027) · **P3** = v1.0 (30.6.2027) · **P4** = v1.x (ab Q3 2027) ·
**Q** = querschnittlich, gilt ab v0.1 für alles.

**Status:** `offen` · `in Arbeit` · `erfüllt` · `teilweise` · `nicht verifiziert` · `blockiert (extern)` ·
`bewusst abgewichen` · `außerhalb Umfang`.

*Stand: Phase 1 (STOPP 1), noch kein Produktivcode. Zeilen gesamt: 166 (davon 9 Nicht-Ziele, 6 Geschäftsaufgaben).*

### Offene Blocker-Fragen (STOPP 1)

| Nr. | Thema | betrifft |
|---|---|---|
| F1 | Umfang dieser Umsetzung (v0.1 / v0.2 / v1.0 / v1.x) | alle P2–P4-Zeilen |
| F2 | Normtexte beschaffen (YY/T 2029, GB/T 47127, ISO/IEC TS 27571, T/GXDSL 008) | NG-F03, NG-F04, RP-02/03/06/08/10/12, GX-xx |
| F3 | Sprache der Bezeichner in öffentlichen Formaten (YAML, JSON, TOML, Pydantic) | DM-xx, RP-01, NG-F14, NG-F18 |
| F4 | NG-N02 (1 GB < 5 min) gegen M06/M09 auf voller Länge | NG-N02, NG-F07, M06, M09 |
| F5 | eegprep, Python 3.11 und Lizenzpolitik (MPL-2.0) | LIB-05, NG-N04, NG-N07 |
| F6 | Downloads, Installationen, Testkorpus | NG-F01, MET-01, NG-N02, TECH-xx |
| F7 | Repository, CI, Veröffentlichung, Urheber | TECH-08, TECH-11, BIZ-04 |

---

## A. Funktionale Anforderungen (§7)

| ID | Anforderung | Abnahmekriterium (PRD) | Fundstelle | Prio | Status | Klärung | Nachweis |
|---|---|---|---|---|---|---|---|
| NG-F01 | Einlesen von EDF/EDF+, BDF, BrainVision (.vhdr), EEGLAB (.set), FIF | Drei öffentliche Datensätze in mindestens zwei Formaten werden ohne Fehler eingelesen; unbekannte Formate erzeugen eine klare Fehlermeldung mit Dateiname | §7 S.6 | P1 | offen | F6, A-24, A-29 | |
| NG-F02 | Konvertierung nach EEG-BIDS (Spezifikation 1.11.x) über MNE-BIDS | Ausgabe besteht den BIDS-Validator v3 ohne Fehler | §7 S.6 | P1 | offen | A-05, A-06 | |
| NG-F03 | Prüfung und Konvertierung gegen GB/T 47127-2026 | Regelpaket `gbt47127` deckt alle Pflichtelemente des Normtexts ab | §7 S.6 | P2 | blockiert (extern): Normtext (kostenlos auf openstd.samr.gov.cn, nur manuell ladbar) | F1, F2, A-32 | |
| NG-F04 | Abbildungstabelle ISO/IEC TS 27571 ↔ BIDS ↔ GB/T 47127 | Jedes Pflichtfeld der TS ist einem Feld in BIDS oder GB/T zugeordnet oder als Lücke markiert | §7 S.6 | P3 | blockiert (extern): TS 27571 kostenpflichtig (CHF 100), GB/T 47127 | F1, F2 | |
| NG-F05 | Strukturprüfung über BIDS-Validator v3 (Deno, als Unterprozess) | Validator-Meldungen erscheinen als normale Befunde mit Schweregrad | §7 S.6 | P1 | offen | A-06 | |
| NG-F06 | Metadaten-Vollständigkeit (M02) | Fehlende Pflichtfelder werden je Datei gelistet | §7 S.6 | P1 | offen | A-03, A-04 | |
| NG-F07 | Signalqualitätsmetriken M03–M09 | Für jede Aufnahme liegen alle Werte im JSON vor; Laufzeit nach NG-N02 | §7 S.6 | P1 | offen | F4, A-18, A-19 | |
| NG-F08 | Annotationsprüfung M10 | Uneinheitliche Ereigniscodes, Lücken, Überlappungen und Cohens κ zwischen Annotatoren werden berichtet | §7 S.6 | P1 | offen | A-17 | |
| NG-F09 | KI-Datensatzstruktur M11–M12: Klassenbalance, Demografie, Split-Integrität, Duplikate | Ein Proband in Training und Test zugleich führt zu einem Fehler; doppelte Aufnahmen werden über Signal-Hash gefunden | §7 S.6 | P1 | offen | A-04, A-21 | |
| NG-F10 | Provenienz-Manifest M13 | `neurogrid verify` erkennt jede geänderte Datei | §7 S.6 | P1 | offen | A-22 | |
| NG-F11 | Regelpakete laden: `bids`, `gxdsl008`, `yyt2029`, eigene | Ein neues Regelpaket ist ohne Codeänderung einbindbar | §7 S.6 | P1 (Lader, bids, gxdsl008) / P2 (yyt2029) | offen | A-02, A-13 | |
| NG-F12 | Nachweis-Checkliste für nicht messbare Anforderungen (z. B. SOPs, Qualifikation der Annotatoren) | Jede manuelle Regel hat Status und Verweis auf ein Nachweisdokument in `evidence.yaml` | §7 S.7 | P2 | offen | A-15 | |
| NG-F13 | Bericht HTML und PDF in zh und en | Jeder Befund nennt Regel-ID, Klausel, Messwert, Schwelle, Datei, Zeitbereich | §7 S.7 | P1 | offen | A-08, A-09, A-10, A-26 | |
| NG-F14 | Maschinenlesbare Ausgabe und Exitcodes | JSON nach `results.schema.json`; Exitcode 0 = keine Fehler, 1 = Fehler, 2 = Werkzeugfehler | §7 S.7 | P1 | offen | F3, A-09, A-11, A-12 | |
| NG-F15 | Versionsvergleich zweier Prüfläufe | Neue, behobene und veränderte Befunde werden getrennt gelistet | §7 S.7 | P3 | offen | F1, A-33 | |
| NG-F16 | NeuroVault (§15) | siehe NV-F01 bis NV-F07 | §7 S.7 | P2 / P3 | offen | F1, A-30 | |
| NG-F17 | Qualitätsabhängige Decoder-Auswertung (§16) | Technischer Bericht mit Kurve „Genauigkeit über Qualitätsstufe“ | §7 S.7 | P4 | offen | F1, A-36 | |
| NG-F18 | Projektkonfiguration `neurogrid.toml` mit Schwellen und Ausnahmen | Jede Ausnahme braucht eine Begründung, und der Bericht zeigt sie an | §7 S.7 | P1 | offen | A-13, A-14 | |

### A2. Versionsinhalte ohne eigene NG-F-ID (§6) und Produktprofil (§2)

| ID | Anforderung | Abnahme / Prüfung | Fundstelle | Prio | Status | Klärung | Nachweis |
|---|---|---|---|---|---|---|---|
| V-01 | v0.1 umfasst: 5 Formate, Konvertierung nach BIDS, Strukturprüfung, Metriken M01–M13, Regelpakete `bids` und `gxdsl008`, Bericht zh/en, JSON-Ausgabe | alle Teile erfüllt | §6 S.5 | P1 | offen | | |
| V-02 | v0.2 umfasst: `yyt2029` erste Fassung nach Klausel-Inventar, Nachweis-Checkliste, GB/T-47127-Prüfung, NeuroVault-Grundfunktionen | alle Teile erfüllt | §6 S.5 | P2 | teilweise blockiert (Normtexte) | F1, F2 | |
| V-03 | v1.0 umfasst: vollständiges NeuroVault, Versionsvergleich, **CI-Integration**, Abbildung ISO/IEC TS 27571, **PDF-Nachweismappe für Registrierungsunterlagen** | alle Teile erfüllt | §6 S.5 | P3 | offen | F1, A-34, A-35 | |
| V-04 | v1.x: NWB und invasive Daten, falls im Geltungsbereich (zunächst nur nicht-invasiv, §20) | – (bedingt; Geltungsbereich erst nach Normtext klar, §21) | §6 S.5, §20, §21 | P4 | offen (PRD bedingt) | F1 | |
| V-05 | v1.x: Server-Variante für Teams | – (PRD nicht spezifiziert; Spannung zu NZ-03) | §6 S.5 | P4 | offen (PRD nicht spezifiziert) | F1 | |
| V-06 | Version 0.1 ist unabhängig vom Normtext YY/T 2029 | v0.1 nutzt keinen Inhalt aus YY/T 2029 | §6 S.5 | P1 | offen | | |
| V-07 | Werkzeug prüft, konvertiert und erzeugt einen zweisprachigen Prüfbericht; prüft gegen YY/T 2029-2026, GB/T 47127-2026, ISO/IEC TS 27571:2026, EEG-BIDS | Gesamtabnahme | §2 S.2 | Q | offen | F2, A-08 | |
| V-08 | Fünf Prüfphasen Erfassung, Verarbeitung, Annotation, Speicherung, Zugriff (Ziel: 合规、可用、可追溯) | jede Regel hat eine Phase | §3 S.3, §11 | Q | offen | A-02 | |

## B. Modul NeuroVault (§15)

„NeuroVault macht Einwilligung, Zugriffsrechte und Zugriffe prüfbar, wie PIPL und die BCI-Ethikleitlinie des MOST (2.2.2024) es verlangen.“

| ID | Anforderung | Grundlage (PRD) | Fundstelle | Prio | Status | Klärung | Nachweis |
|---|---|---|---|---|---|---|---|
| NV-F01 | Einwilligungsumfang je Proband: Version, Datum, erlaubte Nutzungen, Widerruf, Ethikvotum | PIPL Art. 29; MOST-Leitlinie 4.3 | §15 S.15 | P2 | offen | A-30 | |
| NV-F02 | Prüfung: Nutzung jeder Aufnahme in einem Split ist von der Einwilligung gedeckt (Metrik M14) | PIPL Art. 28 (Zweckbindung) | §15 S.15 | P2 | offen | A-30 | |
| NV-F03 | Zugriffsprotokoll als JSONL, jeder Eintrag enthält den SHA-256 des vorigen; `vault verify` erkennt Manipulation | YY/T 2029 „Zugriff“ und „rückverfolgbar“ (Details nach Normtext) | §15 S.15 | P2 | offen (Normdetails später) | A-30 | |
| NV-F04 | Rollenregister: wer darf was sehen, mit Verweis auf das Ethikvotum | MOST-Leitlinie 4.4 | §15 S.15 | P3 | offen | F1, A-30 | |
| NV-F05 | Vorlage für die Datenschutz-Folgenabschätzung und Aufbewahrungsfrist von mindestens 3 Jahren mit Erinnerung | PIPL Art. 55, 56 | §15 S.15 | P3 | offen | F1, A-30 | |
| NV-F06 | Neue Risiken im Risikoregister erzeugen eine Liste der Probanden, die neu einwilligen müssen | MOST-Leitlinie 4.3 | §15 S.15 | P3 | offen | F1, A-30 | |
| NV-F07 | Prüfpaket als ZIP: Manifest, Protokoll, Rollen, Folgenabschätzung, Bericht | Inspektionen | §15 S.15 | P3 | offen | F1, A-30 | |

Die Aufteilung „Grundfunktionen“ (v0.2) / „vollständig“ (v1.0) nennt die PRD nicht; Annahme A-30.

## C. Nicht-funktionale Anforderungen (§8)

| ID | Anforderung | Prüfung | Fundstelle | Prio | Status | Klärung | Nachweis |
|---|---|---|---|---|---|---|---|
| NG-N01 | Läuft lokal und offline. Keine Telemetrie. Der BIDS-Validator wird mitgeliefert, nicht nachgeladen | Lauf ohne Netz; Socket-Sperre in Tests; Code-Scan | §8 S.7 | Q | offen | A-06, A-25, A-26 | |
| NG-N02 | 1 GB EDF wird auf einem Laptop mit 16 GB RAM in unter 5 Minuten geprüft; Daten werden blockweise gelesen | Laufzeit- und Spitzenspeicher-Messung mit synthetischer 1-GB-EDF | §8 S.7 | Q | offen | F4 | |
| NG-N03 | Reproduzierbar: gleiche Daten, Konfiguration und Regelpaketversion ergeben identisches JSON; Zufallsverfahren wie ICA mit festem Seed | zwei Läufe, Byte-Vergleich | §8 S.7 | Q | offen | A-11 | |
| NG-N04 | Windows 10/11 (PowerShell) und Linux; Python 3.11–3.13 | CI-Matrix | §8 S.8 | Q | offen | F5, A-26 | |
| NG-N05 | Berichte enthalten standardmäßig keine Rohsignale und nur pseudonyme IDs | Test auf Berichtsinhalt | §8 S.8 | Q | offen | A-05, A-09 | |
| NG-N06 | Alle Meldungen in zh und en | Vollständigkeitstest der Sprachtabellen | §8 S.8 | Q | offen | A-07 | |
| NG-N07 | Abhängigkeiten nur mit permissiven Lizenzen; die CI prüft das mit pip-licenses | CI-Schritt | §8 S.8 | Q | offen | F5 | |
| NG-N08 | Testabdeckung: Kern 90 %, Prüfer 80 %; jede Regel hat mindestens einen Test mit Positiv- und Negativfall | Coverage-Bericht, Regel-Test-Abgleich | §8 S.8 | Q | offen | A-23 | |

## D. Qualitätsmetriken (§12)

„Vierzehn Metriken bilden den normunabhängigen Kern.“

| ID | Metrik | Methode (PRD) | Startschwelle (PRD) | Fundstelle | Prio | Status | Klärung | Nachweis |
|---|---|---|---|---|---|---|---|---|
| M01 | Lesbarkeit und Kopfzeile | Einlesen mit MNE; EDF-Kopfzeile mit edfio prüfen | Fehler bei Lesefehler | §12 S.12 | P1 | offen | A-24 | |
| M02 | Metadaten-Vollständigkeit | Pflichtfelder EEG-BIDS: EEGReference, SamplingFrequency, PowerLineFrequency, SoftwareFilters, TaskName; channels.tsv name/type/units | Fehler je fehlendem Feld | §12 S.12 | P1 | offen | A-03 | |
| M03 | Abtastrate | Wert je Aufnahme; Einheitlichkeit im Datensatz | Warnung unter 500 Hz (T/GXDSL 008); Warnung bei gemischten Raten ohne Dokumentation | §12 S.12 | P1 | offen | A-18 | |
| M04 | Kanalsatz und Montage | Kanalnamen gegen 10-20/10-10; Positionen vorhanden; gleicher Kanalsatz je Aufgabe | Fehler bei unbekannten Namen ohne Abbildung | §12 S.12 | P1 | offen | A-18 | |
| M05 | Impedanz | Werte vorhanden? Unter Schwelle? | Warnung über 5 kΩ nass (T/GXDSL 008); Warnung, wenn nicht dokumentiert | §12 S.12 | P1 | offen | A-04 | |
| M06 | Schlechte Kanäle | pyprep NoisyChannels | kalibrieren | §12 S.12 | P1 | offen | F4, A-19, A-20 | |
| M07 | Netzbrummen | Leistung 50 Hz ± 1 Hz im Verhältnis zu 1–40 Hz | kalibrieren | §12 S.12 | P1 | offen | A-18, A-20 | |
| M08 | Flatline und Übersteuerung | Abschnitte ohne Varianz oder an der Messbereichsgrenze | Fehler über 5 % der Dauer (Startwert) | §12 S.12 | P1 | offen | A-18 | |
| M09 | Artefaktanteil | Verwerfungsrate mit autoreject; Anteil nicht-hirnbedingter ICA-Komponenten mit mne-icalabel | kalibrieren | §12 S.12 | P1 | offen | F4, A-19, A-20 | |
| M10 | Annotation | Code-Vokabular, Abdeckung, Lücken, Überlappungen, Cohens κ bei mehreren Annotatoren | Warnung bei κ unter 0,6 (übliche Konvention) | §12 S.13 | P1 | offen | A-17 | |
| M11 | Klassen und Demografie | Verteilung der Labels; Alter und Geschlecht vollständig | Warnung, wenn eine Klasse unter 5 % liegt oder Demografie fehlt | §12 S.13 | P1 | offen | A-04, A-21 | |
| M12 | Split-Integrität | Proband in mehreren Splits; Duplikate über Signal-Hash | Fehler | §12 S.13 | P1 | offen | A-21 | |
| M13 | Provenienz | SHA-256 je Datei, Verarbeitungsschritte, Softwareversionen | Fehler bei fehlendem Manifest im Modus `--strict` | §12 S.13 | P1 | offen | A-22 | |
| M14 | Einwilligungsumfang | Nutzung im Split durch Einwilligung gedeckt? | Fehler (ab v0.2) | §12 S.13 | P2 | offen | A-30 | |
| MET-01 | Schwellen ohne Quelle (M06, M07, M09) werden kalibriert: Startwert = 95. Perzentil über mindestens drei öffentliche Datensätze | Kalibrierlauf dokumentiert, Werte mit Herkunft im Regelpaket | §12 S.12 | P1 | offen | F6, A-20 | |
| MET-02 | Alle Schwellen sind in `neurogrid.toml` überschreibbar | Test je Schwelle | §12 S.12 | P1 | offen | A-13 | |

## E. Datenmodell (§10)

„Zehn Pydantic-Objekte (Pydantic v2) tragen alles, was NeuroGrid prüft und berichtet.“ Feldnamen: siehe F3.

| ID | Objekt | Wichtigste Felder (PRD) | Fundstelle | Prio | Status | Klärung | Nachweis |
|---|---|---|---|---|---|---|---|
| DM-01 | Dataset | id, name, version, quelle, lizenz, regelpakete[], manifest_hash | §10 S.9 | P1 | offen | F3 | |
| DM-02 | Subject | pseudo_id, alter_gruppe, geschlecht, diagnose_code (optional), consent_ref | §10 S.9 | P1 | offen | F3, A-21 | |
| DM-03 | Recording | id, subject, session, task, format, pfad, abtastrate_hz, dauer_s, geraet, elektrodentyp (nass/trocken), referenz, netzfrequenz_hz | §10 S.10 | P1 | offen | F3, A-04 | |
| DM-04 | Channel | name, typ (EEG/EOG/EMG/…), einheit, position (10-20/10-10), impedanz_kohm, status (gut/schlecht) | §10 S.10 | P1 | offen | F3 | |
| DM-05 | Annotation | onset_s, dauer_s, code, label, annotator_id, quelle | §10 S.10 | P1 | offen | F3, A-17 | |
| DM-06 | Split | name (train/val/test), recording_ids[] | §10 S.10 | P1 | offen | F3 | |
| DM-07 | ProcessingStep | schritt, werkzeug, version, parameter, eingabe_hash, ausgabe_hash | §10 S.10 | P1 | offen | F3, A-22 | |
| DM-08 | ConsentScope | subject, version, datum, erlaubte_nutzungen{training, validierung, veroeffentlichung, weitergabe, kommerziell}, widerruf, ethikvotum_ref | §10 S.10 | P2 | offen | F3 | |
| DM-09 | AccessEvent | zeit, rolle, aktion, objekte[], zweck, genehmigung_ref, vorheriger_hash, hash | §10 S.10 | P2 | offen | F3 | |
| DM-10 | Finding | regel_id, klausel, schweregrad, status, messwert, schwelle, objekt, belege[] | §10 S.10 | P1 | offen | F3, A-09 | |

## F. Regelpakete und Klausel-Inventar (§11)

| ID | Anforderung | Abnahme / Prüfung | Fundstelle | Prio | Status | Klärung | Nachweis |
|---|---|---|---|---|---|---|---|
| RP-01 | Regelpaket-Format YAML: `rulepack`, `version`, `quelle`, `regeln[]` mit `id`, `klausel`, `titel_zh`, `titel_en`, `phase` (erfassung\|verarbeitung\|annotation\|speicherung\|zugriff), `pruefung`, `parameter`, `schweregrad` (fehler\|warnung\|hinweis), `nachweis` (automatisch\|halbautomatisch\|manuell) | Schema-Validierung aller Pakete | §11 S.10–11 | P1 | offen | F3, A-13 | |
| RP-02 | Jede Klausel der Norm wird eine YAML-Regel mit Klauselnummer, Phase, Prüfung und Schweregrad (Klausel-Inventar) | Inventar ↔ Regelpaket vollständig | §11 S.10–11 | P2 | blockiert (extern): Normtext YY/T 2029 | F2 | |
| RP-03 | Schweregrad aus Normsprache nach GB/T 1.1: 应/不应 → fehler, 宜 → warnung, 可 → hinweis | Inventar-Prüfung | §11 S.11 | P2 | blockiert (extern): Normtext | F2 | |
| RP-04 | Jede Regel einer der fünf Phasen zugeordnet | Schema-Pflichtfeld | §11 S.11 | P1 | offen | | |
| RP-05 | Einstufung automatisch / halbautomatisch (Konfiguration oder Existenz eines Dokuments) / manuell (Nachweisdokument) | Schema-Pflichtfeld; Prüfer für halbautomatisch | §11 S.11 | P1 | offen | A-15 | |
| RP-06 | Nennt die Norm eine Prüfmethode (检验方法), wird sie genau so implementiert, und der Code verweist auf die Klausel | Code-Review | §11 S.11 | P2 | blockiert (extern): Normtext | F2 | |
| RP-07 | Abdeckungsmaß = Anteil der Muss-Klauseln, die automatisch oder halbautomatisch prüfbar sind; Ziel v0.2 ≥ 60 % | berechnet, im Bericht | §11 S.11 | P2 (Berechnung P1) | offen | A-16 | |
| RP-08 | Liste „Auslegungsfragen“ für unsichere Auslegungen | Datei im Repo | §11 S.11 | P2 | blockiert (extern): Normtext | F2 | |
| RP-09 | Regelpaket `bids` | Paket lädt, Validator-Befunde | §6, §7 | P1 | offen | A-06 | |
| RP-10 | Regelpaket `yyt2029` Version `0.2.0-draft`; Parameter sind Platzhalter, bis der Normtext gelesen ist (Beispielregel YYT2029-ACQ-001, Klausel 5.1.2, `signal.sampling_rate_consistency`, `min_hz: 500`) | Paket lädt; Platzhalter markiert | §11 S.10–11 | P2 | offen (Inhalt blockiert) | F2, A-41 | |
| RP-11 | Regelpaket `gbt47127` | siehe NG-F03 | §9 Abb., §13 | P2 | blockiert (extern): Normtext | F2 | |
| RP-12 | Regelpakete werden versioniert (Gegenmaßnahme „neue Normen“) | Version in jedem Paket und im JSON | §20 S.21 | Q | offen | | |
| GX-00 | Regelpaket `gxdsl008`: Startwerte aus T/GXDSL 008-2025 (Guangxi, 18.3.2025), bis der YY/T-Normtext vorliegt | Paket lädt, je Regel Positiv-/Negativtest | §11 S.11 | P1 | offen (Normtext T/GXDSL nicht zugänglich) | F2, A-40 | |
| GX-01 | gxdsl008: Impedanz unter 5 kΩ bei nassen Elektroden | Regel + Tests | §11 S.11 | P1 | offen | A-40 | |
| GX-02 | gxdsl008: Abtastrate mindestens 500 Hz empfohlen | Regel + Tests | §11 S.11 | P1 | offen | A-40 | |
| GX-03 | gxdsl008: EDF oder HDF5 als Format | Regel + Tests | §11 S.11 | P1 | offen | A-40 | |
| GX-04 | gxdsl008: AES-256 und rollenbasierter Zugriff | manuelle Regel (Nachweis) | §11 S.11 | P1 | offen | A-15, A-40 | |
| GX-05 | gxdsl008: Prüfsummen für Dateien | halbautomatische Regel (Manifest) | §11 S.11 | P1 | offen | A-40 | |

## G. Kommandozeile (§13)

„Ein Repository, sieben Befehle; alles läuft in PowerShell und unter Linux.“

| ID | Befehl | Zweck | Fundstelle | Prio | Status | Klärung | Nachweis |
|---|---|---|---|---|---|---|---|
| CLI-01 | `neurogrid scan PFAD` | Bestandsaufnahme: Formate, Probanden, Aufnahmen, Größen | §13 S.14 | P1 | offen | A-31 | |
| CLI-02 | `neurogrid convert PFAD --to bids --out ZIEL` | Konvertierung | §13 S.14 | P1 | offen | A-05 | |
| CLI-03 | `neurogrid check PFAD --rulepack yyt2029 --rulepack bids --config neurogrid.toml --out results.json` | Prüfung | §13 S.14 | P1 | offen | A-03, A-31 | |
| CLI-04 | Modus `--strict` (fehlendes Manifest = Fehler) | M13 | §12 S.13 | P1 | offen | A-22 | |
| CLI-05 | `neurogrid report results.json --lang zh,en --format html,pdf` | Bericht | §13 S.14 | P1 | offen | A-08 | |
| CLI-06 | `neurogrid manifest PFAD` / `neurogrid verify PFAD --manifest manifest.json` | Provenienz | §13 S.14 | P1 | offen | A-22 | |
| CLI-07 | `neurogrid diff alt.json neu.json` | Versionsvergleich | §13 S.14 | P3 | offen | F1, A-33 | |
| CLI-08 | `neurogrid vault init` / `consent add` / `log` / `export` | NeuroVault | §13 S.14 | P2/P3 | offen | A-30 | |
| CLI-09 | `neurogrid vault verify` (in NV-F03 genannt, fehlt in der Befehlstabelle) | Manipulationserkennung | §15 S.15 | P2 | offen | A-30 | |

## H. Prüfbericht (§14) und Positionierung (§5)

| ID | Anforderung | Fundstelle | Prio | Status | Klärung | Nachweis |
|---|---|---|---|---|---|---|
| REP-00 | Bericht so gebaut, dass eine RA-Leiterin ihn ohne Nacharbeit in die Registrierungsunterlagen legen kann | §14 S.14 | P1 | offen | A-08 | |
| REP-01 | Deckblatt: Datensatz und Version, Regelpakete mit Versionen, Datum, Werkzeugversion, Manifest-Hash | §14 S.14 | P1 | offen | A-08, A-11 | |
| REP-02 | Zusammenfassung: je Phase (Erfassung, Verarbeitung, Annotation, Speicherung, Zugriff) eine Ampel, Zahl der Fehler und Warnungen, Abdeckungsmaß | §14 S.14 | P1 | offen | A-16 | |
| REP-03 | Befunde nach Schweregrad, jeweils mit Klausel, Messwert, Schwelle, Datei und Zeitbereich | §14 S.14 | P1 | offen | A-09, A-10 | |
| REP-04 | Metriken je Aufnahme als Tabelle und kleine Verteilungsgrafiken | §14 S.14 | P1 | offen | A-08 | |
| REP-05 | Manuelle Nachweise mit Status und Dokumentverweis | §14 S.14 | P2 (Abschnitt ab P1) | offen | A-15 | |
| REP-06 | Anhang: Konfiguration und begründete Ausnahmen | §14 S.14 | P1 | offen | A-14 | |
| REP-07 | Fester Satz im Bericht: „Vorprüfung mit NeuroGrid. Keine Konformitätsbewertung im Sinne der NMPA-Vorschriften.“ (zh und en) | §14 S.14 | P1 | offen | A-08 | |
| REP-08 | PDF-Nachweismappe für Registrierungsunterlagen | §6 S.5 | P3 | offen (Inhalt in PRD nicht spezifiziert) | F1, A-35 | |
| POS-01 | Vorprüfung, keine Zertifizierung: Ausgaben sagen „Ihre Daten bestehen diese Prüfungen“, nie „Ihre Daten sind konform“; Konformität stellen Prüfinstitute und NMPA fest | §5 S.4 | Q | offen | | |
| POS-02 | Gegenüber Verfassern und Prüfinstituten: offene Referenz, die sie mitprägen und selbst verwenden können | §5 S.4 | Q | offen | | |

## I. Architektur, gemeinsamer Kern und Bausteine (§1, §9)

| ID | Anforderung | Fundstelle | Prio | Status | Klärung | Nachweis |
|---|---|---|---|---|---|---|
| ARC-01 | Fünf Stufen: Datensatz → Adapter/Datenmodell → Prüfer (Struktur, Metadaten, Signal, Annotation, KI-Struktur, Provenienz, Einwilligung) → Regelmotor → Ausgabe (JSON, Bericht HTML/PDF zh/en, Exitcode); Zulieferer BIDS-Validator, NeuroVault, Regelpakete | §9 S.8 Abb. | P1 | offen | | |
| ARC-02 | Prüfer liefern Messwerte, der Regelmotor bewertet sie gegen die Regelpakete; ein Befund je Regel, mit Klausel und Beleg | §9 S.9 Abb. | P1 | offen | A-02, A-09 | |
| ARC-03 | Internes Paket `kernel`: Regelmotor, Belege, Bericht, Provenienz, Sprachtabellen zh/en/de; geteilt mit Proof und RegOps; „was ein zweites Produkt braucht, wandert in den Kern“ | §1 S.1, §9 | P1 | offen | A-07, A-23 | |
| ARC-04 | Adapter wiederverwendbar (RehabLoop nutzt die NeuroGrid-Adapter für Gerätelogs im Format GB/T 47127-2026) | §1 S.1 | P1 (GB/T-Adapter P2) | offen | A-24 | |
| ARC-05 | Entwickler- und Compliance-Werkzeug, kein Medizinprodukt: keine Aussage über Patienten | §2 S.2 | Q | offen | | |
| ARC-06 | Läuft beim Kunden, offline: keine Daten verlassen den Rechner | §9 Abb., §22 | Q | offen | A-25 | |
| LIB-01 | MNE-Python 1.13.2 (BSD-3): Einlesen, Filter, ICA | §9 S.9 | P1 | offen | | |
| LIB-02 | MNE-BIDS 0.20.0 (BSD-3): BIDS lesen und schreiben | §9 S.9 | P1 | offen | A-05 | |
| LIB-03 | BIDS-Validator v3 (Deno) 3.0.2 (MIT): Strukturprüfung | §9 S.9 | P1 | offen | A-06 | |
| LIB-04 | pyprep 0.9.0 (MIT): schlechte Kanäle (PREP) | §9 S.9 | P1 | offen | A-19 | |
| LIB-05 | eegprep 0.4.0 (BSD-2): ASR-Artefaktmetriken | §9 S.9 | P1 | offen | **F5** | |
| LIB-06 | autoreject 0.5.1 (BSD-3): Verwerfungsrate je Epoche | §9 S.9 | P1 | offen | A-19 | |
| LIB-07 | mne-icalabel 0.10.0 (BSD-3): Anteil nicht-hirnbedingter ICA-Komponenten | §9 S.9 | P1 | offen | A-19 | |
| LIB-08 | edfio 0.4.18 (Apache-2.0) / pyEDFlib 0.1.42 (BSD): EDF-Kopfzeilen prüfen | §9 S.9 | P1 | offen | A-24 | |
| LIB-09 | EEGDash 0.9.1 (BSD-3): Katalog öffentlicher BIDS-Datensätze als Testkorpus | §9 S.9 | P1 | offen | A-29 | |
| LIB-10 | NWB Inspector 0.7.2 (BSD): Vorbild für Schweregrade und Prüfer-Aufbau (keine Abhängigkeit) | §9 S.9 | P1 | offen | A-09 | |

## J. Technischer Standard und Repository (§13, §22)

| ID | Anforderung | Fundstelle | Prio | Status | Klärung | Nachweis |
|---|---|---|---|---|---|---|
| TECH-01 | Repository-Aufbau nach §13: `pyproject.toml`; `src/neurogrid/` mit `cli.py`, `io/` (edf, bdf, brainvision, eeglab, fif, gbt47127), `model/` (dataset, consent, results), `checks/` (structure, metadata, signal, annotation, ai_dataset, provenance, consent), `rulepacks/` (bids, gxdsl008, yyt2029, gbt47127 .yaml), `vault/` (ledger, roles, pia), `report/` (templates/, i18n/zh.yaml, i18n/en.yaml); `tests/` (fixtures/ mit kleinen synthetischen EDFs, test_*.py); `docs/` (zh/, en/) | §13 S.13 | P1 | offen | A-23 | |
| TECH-02 | Python 3.12 als Entwicklungsstandard; uv | §13 S.14 | P1 | offen | F6 | |
| TECH-03 | Typer (CLI), Pydantic v2 (Modelle) | §13 S.14 | P1 | offen | | |
| TECH-04 | pytest, ruff, mypy streng für `kernel` | §13 S.14 | P1 | offen | A-23 | |
| TECH-05 | GitHub Actions: Windows und Linux, Python 3.11–3.13 | §13 S.14 | P1 | offen | F5, F7 | |
| TECH-06 | Dokumentation mit MkDocs, zh/en | §13 S.14 | P1 | offen | A-28 | |
| TECH-07 | Berichte über Jinja2 und Playwright mit Noto-CJK | §13 S.14 | P1 | offen | A-26, A-27 | |
| TECH-08 | Gitee-Spiegel für China | §13 S.14 | P1 | offen (Konto des Nutzers nötig) | F7 | |
| TECH-09 | Pfade nur über `pathlib` | §13 S.14 | Q | offen | | |
| TECH-10 | Lizenzen: Code Apache-2.0; Dokumentation und Beispieldaten CC BY 4.0 | §22 S.22, §2 | P1 | offen | A-38 | |
| TECH-11 | Repository `neurogrid` nach §13 angelegt, Apache-2.0, CI aktiv | §1 S.1 | P1 | offen (GitHub-Zugang fehlt) | F7 | |
| TECH-12 | Jede Arbeitskarte (Commit, Fortschrittseintrag) trägt die Anforderungs-ID | §7 S.5 | Q | offen | A-43 | |

## K. Rahmenbedingungen mit Software-Bezug (§20, §22)

| ID | Anforderung | Fundstelle | Prio | Status | Klärung | Nachweis |
|---|---|---|---|---|---|---|
| CON-01 | Keine GPL-Software im Kern (ausdrücklich nicht MetaBCI GPL-2.0, nicht OpenViBE AGPL) | §22 S.22 | Q | offen | F5 | |
| CON-02 | Das Werkzeug darf sensible Daten nie selbst exportieren (PIPL, grenzüberschreitende Übermittlung) | §22 S.22 | Q | offen | A-25, A-30 | |
| CON-03 | Entwicklung nur mit öffentlichen Datensätzen (OpenNeuro, EEGDash, MOABB); nie identifizierbare Patientendaten | §22 S.22 | Q | offen | F6, A-29 | |
| CON-04 | Beim Kunden läuft alles lokal; Daten verlassen das Haus nicht (auch Zusage der Kontaktnachricht §18) | §22 S.22, §18, §20 | Q | offen | A-25 | |
| CON-05 | Offener Code als Vertrauensmaßnahme | §20 S.20 | Q | offen | F7 | |

## L. User Flows (§4 Personas, §5, §13, §18)

| ID | Flow | Fundstelle | Prio | Status | Klärung | Nachweis |
|---|---|---|---|---|---|---|
| UF-01 | RA-Leiterin (Frau Li): `check` mit Regelpaketen → Bericht zh/en als PDF mit Klauselbezug → in Registrierungsunterlagen legen; manuelle Nachweise und Ausnahmen im Bericht | §4, §14 | P1 (Nachweise P2) | offen | | |
| UF-02 | Datenteam (Herr Wang): Daten mehrerer Kliniken `scan` → `convert --to bids` → `check` in der Pipeline (JSON, Exitcodes) → `diff` zweier Läufe | §4, §13 | P1 (diff/CI P3) | offen | | |
| UF-03 | Klinik-Forschungsgruppe (Dr. Zhao): Datensatz aufbauen → Nachweis, dass er die Prüfungen besteht → Einwilligung dokumentieren (`vault`) → Prüfpaket für Weitergabe | §4, §15 | P2/P3 | offen | | |
| UF-04 | Prüfinstitut/Verfasser: offene Referenzimplementierung; eigenes Regelpaket ohne Codeänderung; Massenprüfungen per Skript | §4, NG-F11 | P1 | offen | | |
| UF-05 | Provenienz: `manifest` → Weitergabe → `verify` erkennt jede Änderung | §12 M13, NG-F10 | P1 | offen | | |
| UF-06 | NeuroVault: `vault init` → `consent add` → `log` → `verify` → `export` (ZIP für Inspektionen) | §13, §15 | P2/P3 | offen | | |
| UF-07 | Ausnahmen in `neurogrid.toml` mit Begründung, Nachweise in `evidence.yaml` → beides im Bericht | §7, §14 | P1/P2 | offen | | |
| UF-08 | Vor-Ort-Lauf beim Kunden: Installation und Prüfung ohne Internet auf einem Kundenrechner; Ergebnis bleibt beim Kunden | §18 S.19, §22 | P1 | offen | A-26 | |

## M. Decoder-Auswertung aus NeuroArena (§16, NG-F17)

| ID | Schritt | Fundstelle | Prio | Status | Klärung | Nachweis |
|---|---|---|---|---|---|---|
| NA-01 | Drei MOABB-Datensätze wählen, etwa Motor-Imagery und SSVEP | §16 S.15 | P4 | offen | F1, A-36 | |
| NA-02 | Je Aufnahme die NeuroGrid-Qualitätsstufe berechnen | §16 S.15 | P4 | offen (Qualitätsstufe in PRD nicht definiert) | F1, A-36 | |
| NA-03 | Daten kontrolliert in fünf Stufen verschlechtern: Netzbrummen hinzufügen, Kanäle entfernen, Artefakte einmischen | §16 S.16 | P4 | offen | F1 | |
| NA-04 | Zwei Standard-Decoder trainieren: EEGNet über braindecode und CSP+LDA über MNE oder pyRiemann | §16 S.16 | P4 | offen | F1, F5 | |
| NA-05 | Kurve „Genauigkeit über Qualitätsstufe“ als technischen Bericht mit Notebook veröffentlichen | §16 S.16 | P4 | offen | F1, F7 | |

## N. Nicht-Ziele (bleiben draußen)

| ID | Nicht-Ziel | Fundstelle |
|---|---|---|
| NZ-01 | Keine klinischen Aussagen | §6 S.5 |
| NZ-02 | Keine Dekodier-Algorithmen als Produkt | §6 S.5 |
| NZ-03 | Kein Hosting von Kundendaten | §6 S.5 |
| NZ-04 | Keine Cloud-Pflicht | §6 S.5 |
| NZ-05 | Kein Anspruch auf Zertifizierung | §6 S.5 |
| NZ-06 | Keine Unterstützung proprietärer Rohformate ohne Herstellerdokumentation | §6 S.5 |
| NZ-07 | NeuroVault: keine Blockchain | §15 S.15 |
| NZ-08 | NeuroVault: keine Identitätsverwaltung | §15 S.15 |
| NZ-09 | NeuroVault: keine Klarnamen | §15 S.15 |

## O. Außerhalb des Software-Umfangs (Aufgaben des Nutzers)

Stehen in der PRD, sind aber keine Software-Anforderungen. Sie werden nicht umgesetzt, aber dort
vermerkt, wo Software-Phasen von ihnen abhängen.

| ID | Aufgabe | Fundstelle | Abhängige Anforderungen |
|---|---|---|---|
| BIZ-01 | Normtexte beschaffen: YY/T 2029-2026 (NIFDC/SPC), GB/T 47127-2026 (openstd.samr.gov.cn), ISO/IEC TS 27571 (ISO-Shop), T/GXDSL 008-2025 (ttbz.org.cn) | §1, §17 W1, §20 | NG-F03, NG-F04, RP-02/03/06/08/10/11, GX-xx, NV-F03 (Details) |
| BIZ-02 | Konferenzen, Kontakte, Gespräche, Gesprächsleitfaden, Kontaktnachricht, WeChat-Profil | §1, §17, §18 | – |
| BIZ-03 | International Office SSPU, Hochschule Trier, Gesellschaftsgründung, Rechtsstatus | §1, §22 | – |
| BIZ-04 | Veröffentlichung v0.1 auf GitHub, Gitee und PyPI; chinesischer Fachartikel | §17 W6 | TECH-08, TECH-11, NA-05 |
| BIZ-05 | Gates G1 (29.11.2026), G2 (15.1.2027, hartes Abbruchkriterium), G3 (30.6.2027), G4 (1.9.2027) | §19 | F1 |
| BIZ-06 | Preise und Angebote (Audit, Jahreslizenz, Integration) | §18 | – |
