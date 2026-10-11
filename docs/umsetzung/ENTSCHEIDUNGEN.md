# NeuroGrid – Entscheidungen und Annahmen

Rangfolge bei Konflikten: Antworten und Freigaben des Projektverantwortlichen > PRD > bestehender Code > Annahmen.
Offene Entscheidungsfragen stehen bis zur Antwort offen; Annahmen (A-xx) gelten, solange der
Projektverantwortliche nicht widerspricht. Verweise auf Anforderungen: IDs aus [ANFORDERUNGEN.md](ANFORDERUNGEN.md).
NeuroGrid ist bis auf Weiteres ein unbezahltes Open-Source- und Studienprojekt (PRD §22).

## Geprüfte Fakten (Stand 11.10.2026)

**Bibliotheken**
- Die Versionen und Lizenzen der elf Bibliotheken aus §9 stimmen mit PyPI überein: mne 1.13.2, mne-bids 0.20.0, bids-validator-deno 3.0.2, pyprep 0.9.0, eegprep 0.4.0, autoreject 0.5.1, mne-icalabel 0.10.0, edfio 0.4.18, pyEDFlib 0.1.42, eegdash 0.9.1, nwbinspector 0.7.2.
- eegprep 0.4.0 verlangt Python ≥ 3.12. Es zieht pyEDFlib, oct2py und pybids mit den LGPL-Paketen frozendict und num2words nach.
- pyEDFlib 0.1.42 hat für Python 3.13 keine Wheels für Windows/Linux x86_64.
- certifi (MPL-2.0) und tqdm (MPL-2.0 AND MIT) sind harte transitive Abhängigkeiten von MNE.
- Die Linux-Wheels von numpy und scipy bündeln libgfortran (GPL mit GCC-Laufzeitausnahme) und libquadmath (LGPL); die Windows-Wheels nicht. Das gilt für jede Installation mit MNE.

**BIDS und Validator**
- Der BIDS-Validator 3.0.2 kommt als universelles Wheel `bids-validator-deno` plus PyPI-Paket `deno` (MIT). Er bringt Schema 1.2.7 = BIDS 1.11.1 mit; die aktuelle Spezifikation ist BIDS 1.11.2.
- Der mitgelieferte Starter setzt fest `--allow-net`. Deno fragt ohne `DENO_NO_UPDATE_CHECK=1` bei dl.deno.land an, auch mit `--deny-net`.
- Der Validator liest keine Datendateien (gekürzte EDF, fehlende `.eeg` → keine Meldung).
- MNE-BIDS 0.20 schreibt `BIDSVersion: 1.9.0`, `n/a` für EEGReference und Platzhalter für Name und Autoren.

**Formate**
- edfio erkennt diskontinuierliche EDF+-Dateien (EDF+D) über die Zeitstempel-Annotationen (`is_continuous`).
- EEGLAB-.set mit eingebetteten Daten ist nicht blockweise lesbar.

**PDF und Schrift**
- Playwright 1.63 lädt Browser per `playwright install`. Die „Chrome Headless Shell“ ist ein Google-Chrome-Build: Laut ABOUT „All rights reserved“ mit Nutzungsbedingungen, laut LICENSE.headless_shell enthält sie FFmpeg (LGPL-2.1+).
- Edge baut bei jedem Lauf Verbindungen zu Microsoft auf.
- Playwright unterstützt offiziell nur Windows 11 und Debian/Ubuntu.
- Noto Sans SC steht unter OFL 1.1; reserviert ist nur der Name „Source“.
- MkDocs 1.6.1 ist seit 2024 ohne Release; Material for MkDocs ist im Wartungsmodus.

**Normtexte**
- GB/T 47127-2026 ist kostenlos auf openstd.samr.gov.cn lesbar (Bildseiten, Captcha, nur von Hand).
- YY/T 2029-2026 ist von hier aus nicht beschaffbar.
- ISO/IEC TS 27571:2026 kostet CHF 100.
- T/GXDSL 008-2025 ist derzeit nicht abrufbar.

**Sonstiges**
- Testdaten: Der Korpus ist geladen, siehe A-29. openneuro-py ist GPL-3.0 und wird nicht verwendet.
- Lokal gibt es kein Linux; WSL enthält nur die gestoppte Docker-Desktop-Distribution.
- Die PyPI-Namen `neurogrid` und `neurogrid-eeg` sind frei.

## Entscheidungen des Projektverantwortlichen

Am 11.10.2026 hat der Projektverantwortliche alle Empfehlungen zu F1–F7 freigegeben.

**D-01 (F1) Umfang.**
- v0.1, v0.2 und v1.0 werden vollständig umgesetzt, soweit das ohne Normtexte möglich ist.
- Normabhängige Teile folgen, sobald der jeweilige Text vorliegt (Go/No-Go).
- NG-F17 entsteht als Forschungsteil in `research/` außerhalb des Pakets.
- V-04 (NWB/invasiv, laut PRD bedingt) und V-05 (Server-Variante, nicht spezifiziert) bleiben offen.

**D-02 (F2) Normtexte.**
- GB/T 47127-2026: Der Projektverantwortliche lädt das PDF und legt es in `.local/normen/`.
- YY/T 2029-2026: Der Projektverantwortliche beschafft den Text.
- ISO/IEC TS 27571: Kauf durch den Projektverantwortlichen vor der Phase P10.
- T/GXDSL 008: `gxdsl008` entsteht aus den fünf PRD-Startwerten (A-40).

**D-03 (F3) Sprache öffentlicher Bezeichner.** Englisch in Code und allen öffentlichen Formaten
(YAML, JSON, TOML, Pydantic). Eine 1:1-Abbildung der PRD-Begriffe steht in der Dokumentation.

**D-04 (F4) Laufzeit.** Streamingfähige Metriken laufen blockweise über die volle Länge. M06 und M09 laufen
auf einer deterministischen Stichprobe; sie wird ausgewiesen und ist bis „volle Länge“ konfigurierbar.

**D-05 (F5) Abhängigkeiten und Lizenzen.**
- eegprep entfällt; das ist eine freigegebene Abweichung von §9 (LIB-05).
- NG-N07 gilt so: permissive Lizenzen plus MPL-2.0 für unverändert genutzte Laufzeitabhängigkeiten. GPL, LGPL und AGPL sind verboten (Auslegung für mitgelieferte Binärteile: siehe E1).
- Entwicklungswerkzeuge werden getrennt geprüft.
- Python 3.11–3.13.

**D-06 (F6) Downloads.** Freigegeben:
- uv, Python 3.11/3.12, PyPI-Pakete
- Chromium für Playwright, Noto Sans SC
- Testkorpus OpenNeuro (CC0) und PhysioNet PSG-IPA
- für NG-F17: torch, braindecode, moabb und MOABB-Daten

**D-07 (F7) Repository.**
- Lokales Git, Arbeitszweig `dev`.
- Der Projektverantwortliche legt das öffentliche GitHub-Repository `neurogrid` an; gepusht wird nur nach Freigabe.
- Gitee-Spiegel und PyPI führt der Projektverantwortliche mit eigenen Konten aus.
- Urheber „Ammar Ahad“.
- `docs/umsetzung/` ist öffentlich, die PRD nicht.

## Offene Entscheidungsfragen (STOPP 2)

Wortlaut und Empfehlung stehen im STOPP-2-Bericht und in KONZEPT.md Abschnitt 9.

| Nr. | Thema | Empfehlung |
|---|---|---|
| E1 | Auslegung von D-05 für mitgelieferte Binärteile (libquadmath in numpy/scipy unter Linux; Chrome Headless Shell mit FFmpeg/LGPL und Google-Nutzungsbedingungen) | Python-Pakete wie D-05; native Bibliotheken in Wheels mit Hinweis zulassen; Headless Shell **nicht** ins Bündel, sondern Installationsskript |
| E2 | CI und Linux vor v0.1 | GitHub-Repo jetzt anlegen, Push auf `dev` ab P1 freigeben; zusätzlich Docker Desktop für lokale Linux- und Offline-Tests |
| E3 | Zusätze über die PRD hinaus | siehe Liste in KONZEPT 9 (empfohlen: behalten bzw. streichen je Punkt) |
| E4 | Testkorpus über die OpenNeuro-API statt EEGDash (LIB-09) | Abweichung freigeben (EEGDash zieht torch und NVIDIA-Pakete nach) |
| E5 | Lesart und Referenzmessung von NG-N02 (A-50) | eine 1-GB-EDF-Datei; Messung mit 4 Kernen hier und auf einem 4-vCPU/16-GB-Runner |

## Annahmen (Nicht-Blocker)

**A-00 Nicht ausgefüllte Eingaben des Auftrags.** Ausgangslage: neues Projekt unter `Projekte/neurogrid`.
- Technische Vorgaben: laut PRD §13.
- Zugänge: keine (uv inzwischen installiert; Deno kommt über PyPI; gh fehlt).
- Regulatorik: laut PRD.
- Nicht anfassen: alle anderen Ordner unter `Projekte/`.
- Freigabemodus: A.

**A-01 PRD und Geschäftsinhalte.** Die PRD liegt in `.local/prd/` und wird nie versioniert. `docs/umsetzung/` enthält nur
technische Inhalte. Markt, Preise, Rechtsstatus, Gates und Zielkunden werden nur über BIZ-IDs referenziert. Beispiele
verwenden neutrale Namen (z. B. Gerät „ExampleAmp 64“).

**A-02 Kernregelpaket `core`.** Ein eingebautes Paket `core` bewertet die Metriken M01–M13 (ab v0.2 M14), mit den
Startschwellen aus §12. Es ist standardmäßig geladen und in `neurogrid.toml` abwählbar.
- Die vollständige Regelliste (ID, Teilprüfung, Phase, Schweregrad, Schwelle, Quelle) steht in KONZEPT 2.2.
- Regel-IDs nach dem Muster `CORE-Mxx-NN`. Das ist eine bewusste, dokumentierte Ausnahme vom Schema `PAKET-PHASE-NNN`, weil die Klausel hier die Metrik ist.
- Als Quelle nennt der Bericht die öffentliche, versionierte Metrik-Dokumentation (`docs/<lang>/metrics.md#Mxx`), nicht die unveröffentlichte PRD.
- Phasen: M01 storage; M02–M09 acquisition; M10 annotation; M11–M12 processing; M13 storage; M14 access.

**A-03 Eingang von `check`.**
- `check` nimmt BIDS-Datensätze (erkannt an `dataset_description.json`) und Rohordner. Der Validator läuft nur auf BIDS; bei Rohordnern entsteht ein Hinweis „BIDS-Struktur nicht geprüft“.
- M02 bewertet je fehlendem Feld einen eigenen Befund (Unterschlüssel = Feldname).
- `n/a` zählt bei EEGReference und PowerLineFrequency als fehlend, bei SoftwareFilters als gültig.

**A-04 Herkunft fehlender Metadaten.** Vorrang: `neurogrid.toml` > BIDS-Sidecars > Formatkopf > undokumentiert
(Befund „nicht dokumentiert“, kein Abbruch). Weitere Quellen:
- Splits: `.neurogrid/splits.tsv` oder Spalte `split` in `participants.tsv`.
- Annotatoren: Spalte `annotator` in `events.tsv` oder eine Datei je Annotator.
- Demografie-Spalten werden ohne Groß-/Kleinschreibung abgebildet (age; sex/gender).

**A-05 Konvertierung.**
- **Zuordnung:** Rohordner brauchen eine Zuordnung zu sub/ses/task/run, als Regex mit benannten Gruppen oder Zuordnungstabelle in der toml. Fehlt sie, endet der Lauf mit Exit 2 und schreibt eine Vorlage. Labels sind nur alphanumerisch.
- **Formate:** EDF, BDF, BrainVision und EEGLAB übernimmt MNE-BIDS. FIF wird nach BrainVision geschrieben (pybv). EDF+D wird gelesen (edfio für die Zeitstruktur), nicht abgelehnt.
- **Sidecars:** Pflichtfelder werden aus A-04 befüllt. MNE-BIDS-Platzhalter (Name, Autoren) werden ersetzt bzw. weggelassen. Typisierte Empfehlungsfelder bekommen nie `n/a`. Template-Positionen werden nicht als `space-CapTrak` geschrieben. `BIDSVersion` = Schema-Version des Validators.
- **Kopfzeilen:** Identifizierende Kopfzeilenfelder bleiben in den Datendateien unverändert, sofern E3 nicht `--strip-identifying-headers` freigibt. NeuroGrid meldet ihr Vorhandensein als Hinweis, ohne Werte auszugeben (M01).
- **Doku-Hinweis:** „NeuroGrid pseudonymisiert nicht; IDs und Dateinamen stammen aus der Eingabe.“

**A-06 BIDS-Validator.**
- **Aufruf:** deno wird direkt gestartet, mit `--deny-net`, nur Leserecht auf den Datensatz und nur Schreibrecht auf die Ausgabedatei. Die Umgebung ist bereinigt: `DENO_NO_UPDATE_CHECK=1`, eigenes `DENO_DIR`, kein `BIDS_SCHEMA`; `--schema` wird nie übergeben. Ausgabe mit `--format json -o … --max-rows -1`.
- **Sicherer Start:** Das Binary wird über den Paketpfad aufgelöst (`shell=False`). Pfade mit Komma werden abgelehnt (Exit 2), weil Deno Rechte-Listen an Kommas trennt.
- **Ergebnis:** Exit 16 = Befunde, jeder andere Exit ≠ 0 = Werkzeugfehler. Validator-Fehler → `BIDS-STO-001` (error), Warnungen → `BIDS-STO-002` (warning), mit Unterschlüssel = Validator-Code (A-09); je BrainVision-Tripel zusammengefasst.
- **Texte:** Die zh/en-Meldungen pflegt NeuroGrid je Code; der englische Originaltext erscheint nicht im Bericht.
- **HED:** Versionen über 8.4.0 sind offline nicht verfügbar und erscheinen als eigener Befund.

**A-07 Sprachen.**
- Eigene Meldungen gibt es nur über Sprachschlüssel.
- Sprachtabellen zh, en und de laut §1 im Kern. Bericht und CLI sind offiziell zh/en (NG-F13, NG-N06); de ist nur als Tabelle für Proof/RegOps vorhanden, sofern E3 nichts anderes ergibt.
- CLI-Sprache über `--lang`, `NEUROGRID_LANG` oder die Systemsprache; Ausgabe immer UTF-8.
- Fremdmeldungen erscheinen nur als Code bzw. Ausnahmetyp plus übersetzter, bereinigter Text.
- Die chinesischen Texte prüft vor der Veröffentlichung von v0.1 ein Muttersprachler; das ist Bedingung für STOPP G1.

**A-08 Bericht.**
- **Dateien:** Je Sprache und Format eine Datei im Ordner `--out`. `--lang`/`--format` nehmen Komma-Listen und wiederholte Optionen.
- **Datum:** Das Deckblatt-Datum ist der Stichtag (`as_of`, A-11).
- **HTML:** eigenständig, mit Content-Security-Policy (`default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:`) und ohne Links auf Dateipfade. Der PDF-Titel ist neutral.
- **Fester Satz** zh/en: steht im Anhang und auf dem Deckblatt, in der Fußzeile jeder PDF-Seite, als Pflichtfeld `disclaimer` in results.json, scan- und diff-JSON, in der Konsolen-Kurzfassung, auf der Nachweismappe und im Export-Index.

**A-09 Befundmodell.**
- **Schlüssel:** Ein Befund je Regel × Objekt × Unterschlüssel (z. B. Feldname bei M02, Validator-Code, Kanal). Der stabile Schlüssel ist SHA-256 über (rule_id, object, subkey).
- **Felder:** Die PRD-Felder bleiben, mit einer Umbenennung: Die „Belege“ eines Befunds heißen `details` (D-03), damit `evidence` eindeutig die Nachweise aus `evidence.yaml` bezeichnet. Ergänzt werden Paket und -version, `source_status` des Pakets, Phase, Datei, Kanal, Zeitbereiche und Meldungsschlüssel.
- **Status:** passed, failed, excepted, not_applicable, not_checkable (mit Grund-Schlüssel), evidence_open.
- **Bestandene Befunde** werden je Regel und Aufnahme gezählt (A-59).
- **Leere Felder:** Felder ohne Wert (z. B. Messwert bei manuellen Regeln) erscheinen als „–“ mit Grund.

**A-10 Zeitbereich.** Liste von [start_s, end_s] relativ zum Aufnahmebeginn (bei EDF+D in Aufnahmezeit).
Aufnahmeweite Werte zeigen „gesamte Aufnahme“, datensatzweite keinen Zeitbereich. Höchstens 20 Intervalle,
dazu Anzahl und Gesamtdauer.

**A-11 Reproduzierbarkeit (NG-N03).** Gleiche Eingabe heißt: gleiche Daten, gleiche Konfiguration (inkl. Stichtag
`as_of`), gleiche Regelpaketversionen und gleiche Umgebung.
- **Stichtag:** `check --as-of JJJJ-MM-TT` bzw. `[check] as_of`, Standard heute. Alle Datumslogik nutzt ihn (Ausnahmen, Fristen, Einwilligungen); er steht in results.json.
- **Umgebung:** Ein Block `environment` nennt die rechnenden Bibliotheken, die Plattform und die BLAS-Threads.
- **Inhalt von results.json:** keine Uhrzeit, kein Rechner- oder Benutzername, keine absoluten Pfade und kein Vault-Kopf-Hash. Der Hash der Konfiguration wird über den kanonisch serialisierten Inhalt gebildet, nicht über Rohbytes.
- **Rechnen:** feste BLAS-/OpenMP-Threads (threadpoolctl); `--jobs` als Prozesspool mit 1 BLAS-Thread je Worker; fester Seed.
- **Abhängigkeiten:** Alle ergebnisrelevanten Bibliotheken sind exakt gepinnt (A-48).
- **Tests:** Byte-Gleichheit zweier Läufe in derselben Umgebung. Der Golden-Vergleich ist strukturell exakt, Gleitkommawerte haben dokumentierte Toleranzen. Die Gleichheit über Plattformen wird gemessen und berichtet, ist aber keine Testbedingung.

**A-12 Exitcodes.**
- **Exit 1:** Datendefekte sind Befunde. Exit 1, wenn mindestens ein nicht ausgenommener error-Befund verletzt ist oder ein Nachweis zu einer error-Regel offen ist. Jede nicht unterstützte oder nicht zuordenbare Datendatei in einem Ordner ist ein M01-Fehler mit Dateinamen. Ein Datensatz ohne lesbare Aufnahme ist ein Fehler.
- **Exit 2** nur bei:
  - ungültiger Konfiguration
  - nicht ladbarem Regelpaket
  - fehlendem Validator bzw. fehlender Headless Shell für PDF
  - unzulässigem Pfad
  - internem Fehler
  - ausdrücklich übergebener Einzeldatei unbekannten Formats
- **Exit 0:** nur Warnungen.
- **Andere Befehle:** `verify` und `vault verify` → 1 bei Abweichung; `diff` → 1 bei neuen error-Befunden.

**A-13 Schwellen und eigene Regelpakete.**
- **Vorrang:** toml > Regelpaket > Standardwert der Prüfung, adressiert über die Regel-ID.
- **Prüf-Registry:** Jede Prüfung deklariert Parameter und Vergleichsrichtung; die Registry steht als generierte Doku-Seite bereit. Eigene Pakete nutzen nur registrierte Prüfungen.
- **Herkunft:** Wirksame Schwellen samt Herkunft stehen im Befund; überschriebene listet der Anhang.

**A-14 Ausnahmen.**
- **Form:** `[[exceptions]]` mit `rule`, optional `object` (Pfadmuster), optional `subkey` (z. B. Validator-Code oder Feld), Pflichtfeld `reason` (nicht leer) sowie optional `approved_by` (Rolle oder Kürzel, kein Klarname) und `valid_until`.
- **Muster:** Ein eigener Matcher arbeitet auf relativen POSIX-Pfaden (`**` = beliebig viele Segmente, `*` = ein Segment, Groß-/Kleinschreibung zählt), auf allen Plattformen gleich.
- **Wirkung:** Ausgenommene Befunde zählen weder für den Exit noch für die Ampel und stehen im Anhang.
- **Fehlerfälle:** fehlende Begründung → Exit 2; abgelaufene Ausnahme (gegen `as_of`) → Warnung.

**A-15 Nachweise (`evidence.yaml`).**
- **Felder je Regel:** `status` (open | provided | partial | not_applicable), `document`, `sha256` (automatisch), `reviewer` (Rolle oder Kürzel), `date`, `comment`; `justification` ist Pflicht bei not_applicable.
- **Wortwahl:** „provided“ heißt im Bericht „Nachweis hinterlegt (Angabe des Nutzers, nicht von NeuroGrid bewertet)“, nie „erfüllt“.
- **Halbautomatisch** = Dokument vorhanden und Hash stimmt.
- **Ohne Eintrag:** Eine manuelle Regel ohne Eintrag hat den Status evidence_open und zählt mit ihrem Schweregrad.
- **Zeitpunkt:** Nachweismodell und -auswertung entstehen in P4, also schon für gxdsl008 in v0.1.

**A-16 Ampel und Abdeckungsmaß.**
- **Ampel je Phase:**
  - rot: mindestens ein verletzter error-Befund oder offener Nachweis zu einer error-Regel
  - gelb: dasselbe bei warning
  - sonst grün
  - grau: keine Regeln oder nur Regeln aus Paketen mit `source_status` placeholder
- **Legende:** „grün = keine verletzte Fehler-Regel in den geladenen Regelpaketen“.
- **Zählung:** `errors` und `warnings` enthalten offene Nachweise; `open_evidence` ist nur eine Aufschlüsselung.
- **Abdeckungsmaß** je Paket mit `source_status` inventory oder final: Muss-Klauseln mit automatischer oder halbautomatischer Prüfung geteilt durch alle Muss-Klauseln. Für core, bids, Pakete ohne Muss-Klausel sowie placeholder- und secondary-Pakete steht „n/a“.

**A-17 Annotation (M10).**
- **Modus** in der toml: kontinuierlich oder ereignisbasiert.
- **κ:** paarweises Cohens κ auf einem Epochenraster (30 s bzw. 1 s); „kein Ereignis“ ist eine eigene Klasse. Ausgewiesen werden Mittelwert und Minimum. Mit nur einem Annotator ist κ not_applicable.
- **Lücken und Abdeckung** nur im kontinuierlichen Modus; Überlappungen je Annotator.
- **Uneinheitliche Codes:** außerhalb des Vokabulars oder gleiche Bezeichnung mit verschiedenen Codes.
- **Anzeige:** Annotationscodes erscheinen nur, wenn sie dem Muster `[A-Za-z0-9_.\-/ ]{1,32}` folgen, sonst als „Freitext (n Zeichen)“.
- **Schweregrade der Teilprüfungen:** κ < 0,6 = warning (PRD); uneinheitliche Codes, Lücken und Überlappungen = warning (Annahme, PRD nennt keine).

**A-18 Technische Parameter M03, M04, M07, M08.**
- **M03:** Gemischte Raten gelten als dokumentiert, wenn die toml sie begründet; die Sidecar-Rate muss den Daten entsprechen.
- **M04:** Kanalnamen gegen eine 10-20/10-10-Namensliste. Namen, die nur in 10-05 vorkommen, ergeben einen Hinweis „außerhalb 10-10“. Unbekannte Namen ohne Abbildung sind ein Fehler (PRD). Zu „Positionen vorhanden“ und „gleicher Kanalsatz je Aufgabe“ nennt die PRD keinen Schweregrad; Annahme: warning. Kanaltypen ordnet eine eigene Bezeichnungsliste zu.
- **M07:** Netzfrequenz laut Dokumentation, Standard 50 Hz. Rechenweg wie in KONZEPT 1.5; bewertet wird je Kanal; nicht anwendbar, wenn fs < 2·(f₀+1).
- **M08** je Format:
  - LSB aus Digital-/Physikalbereich (EDF/BDF) bzw. Resolution (BrainVision); für Gleitkommaformate (EEGLAB, FIF) gilt eine absolute Toleranz (Spitze-Spitze < 0,1 µV, konfigurierbar).
  - Übersteuerung: an den Grenzen des Messbereichs, wo er bekannt ist (EDF/BDF); sonst über Plateaus (≥ 10 gleiche Samples am Extremwert). Ohne beides: not_checkable.
  - Übersteuerte Fenster zählen nicht zusätzlich als flach.

**A-19 M06 und M09.**
- **Stichprobe:** 10 × 60 s mittig in 10 gleichen Teilen; Aufnahmen bis 10 min ganz.
- **Vorverarbeitung:** Notch-Filter bei f₀ und Harmonischen, Bandpass 1–100 Hz, 250 Hz, Montage und Durchschnittsreferenz ohne schlechte Kanäle.
- **M06:** Anteil schlechter EEG-Kanäle (pyprep NoisyChannels, RANSAC nur mit Positionen).
- **M09a:** Anteil verworfener 2-s-Epochen aus lokalem autoreject (`cv=10`, `n_interpolate=[1,4,32]`).
- **M09b:** Anteil der ICA-Komponenten (picard extended, 20 Komponenten, decim 4), deren wahrscheinlichste ICLabel-Klasse nicht „brain“ ist; zusätzlich ohne „other“.
- **Backend:** onnxruntime.
- **Vorbedingungen:** siehe A-60.

**A-20 Kalibrierung.**
- `tools/calibrate.py` mit fest gepinnten OpenNeuro-Snapshots (mindestens drei).
- 95. Perzentil über Aufnahmen (M06, M09) bzw. Kanäle (M07); Ergebnis mit Herkunft im Paket `core`.
- Kalibriert werden nur die Metriken mit „kalibrieren“ (M06, M07, M09). M08 (5 %) und M11 (5 %) behalten die PRD-Startwerte.

**A-21 KI-Struktur (M11, M12).**
- **M11:** Labelquelle konfigurierbar; Klassenanteile je Split und gesamt; Altersgruppen in 10-Jahres-Stufen; das Rohalter wird nie serialisiert.
- **M12 Splits:** Ein Proband in mehr als einem Split ist in jeder Kombination ein Fehler. Ohne Splits ist der Split-Teil not_applicable.
- **M12 Signal-Hash:** `NG-SIGHASH-v1`, nur über EEG-Kanäle, int64 von round(µV·10). Die Abtastrate geht als Dezimalstring mit festem Format ein. Hashes werden nicht ausgegeben, nur Duplikatgruppen (pseudonyme Aufnahme-IDs). Teilduplikate sind nicht abgedeckt.

**A-22 Manifest.**
- **Inhalt:** Versionsnummer, sortierte Dateiliste (Pfad, SHA-256, Größe), Verarbeitungsschritte, Softwareversionen; Manifest-Hash über die kanonischen JSON-Bytes.
- **Erfasste Dateien:** alles im Datensatz einschließlich `.neurogrid/` (splits.tsv, neurogrid.toml, consents.yaml, roles.yaml, risks.yaml, evidence.yaml, retention.yaml). Ausgenommen sind nur `manifest.json` selbst und das eigenständig hashverkettete `vault/access.jsonl`.
- **Symlinks und Junctions** werden nicht verfolgt, sondern gemeldet.
- **`verify`** meldet geänderte, neue und fehlende Dateien.
- **Fehlendes Manifest:** ohne `--strict` eine Warnung (Annahme; die PRD regelt nur den strict-Fall).

**A-23 Paket `kernel` und Testabdeckung.**
- **Grenze:** `neurogrid.kernel` importiert nichts aus `neurogrid.*` außerhalb von kernel und keine EEG-Bibliotheken (AST-Test ab P1). Vorlagenpfade und Sprachtabellen werden übergeben. `mypy --strict` auf kernel.
- **Abdeckungsgrenzen:** „Kern“ (≥ 90 %) = kernel, model, vault, config. „Prüfer“ (≥ 80 %) = checks, io, convert, diff, dossier, report, cli.
- **Messung:** `coverage combine` über alle Läufe inkl. Unterprozessen; `coverage report --include=… --fail-under=…` je Gruppe; lokal ab P1 Gate jeder Phase, in der CI ab dem ersten Push.

**A-24 Adapter.**
- Einlesen über MNE; EDF-Kopf über edfio; BDF-Kopf über einen eigenen Parser.
- **Adapter-API:** `read(path) → Recording`, `iter_blocks()`, `read_segments()`, je Kanal `unit`, `resolution`, `physical_range` (optional, mit Herkunft). Sie ist stabil (RehabLoop).
- **Feldauswahl:** Adapter übernehmen nur ausdrücklich gelistete Kopffelder (A-51).

**A-25 Offline.**
- Kein Netzwerkcode.
- „Daten nie selbst exportieren“ = kein Upload, keine Übertragung; lokales Schreiben ist erlaubt.

**A-26 Installation ohne Internet und PDF.**
- **Offline-Bündel je Plattform:** uv-Binary, python-build-standalone 3.12, cp312-Wheelhouse aus `uv.lock`, Dokumentation, Notices, `SHA256SUMS`. Das Installationsskript legt eine venv an (Bytecode vorkompiliert) und setzt beschreibbare Orte für `DENO_DIR` und den Browser.
- **Headless Shell:** gemäß E1 (Empfehlung: nicht im Bündel; `neurogrid` liefert ein Installationsskript, das online von Playwright lädt oder offline eine vom Kunden bereitgestellte zip mit geprüfter Prüfsumme einspielt). Kein Edge-Rückfall. Ohne Headless Shell endet `--format pdf` mit Exit 2 und Hinweis; HTML geht immer.
- **Vor dem PDF-Druck:** Startprüfung; fehlen Linux-Bibliotheken, folgt Exit 2 mit Paketliste.
- **Plattformen:** Windows 10 und andere Linux-Distributionen als Debian 12/Ubuntu 22.04+: „nicht verifiziert“.
- **Verteilung:** GitHub Releases (bis 2 GiB je Datei); Gitee nach dessen Größengrenzen.

**A-27 Schrift.**
- **Herstellung:** Die statischen Schnitte Noto Sans SC 400/700 erzeugt ein tools-Skript einmalig aus der Google-Fonts-VF. Radikal- und Kompatibilitäts-Codepunkte werden entfernt. Die Schnitte sind mit SHA-256 eingecheckt (≈ 2 × 10,6 MB); `OFL.txt` liegt daneben.
- **Laufzeit:** Subsetting per fontTools mit `recalcTimestamp=False`; die name-IDs 0, 13 und 14 bleiben erhalten.
- **matplotlib:** bindet die Schrift per `addfont` ein, nutzt `svg.fonttype='path'` und ein eigenes MPLCONFIGDIR.
- **Lizenzangaben:** Wheel-Metadaten `license = "Apache-2.0 AND OFL-1.1"`; die Lizenz je Pfad steht in `REUSE.toml`.

**A-28 Dokumentation.**
- MkDocs 1.6.1 + Material 9.7 + mkdocs-static-i18n, gepinnt; ohne externe Ressourcen (`theme.font: false`, lokale Schrift, Build-Test).
- `docs/umsetzung` gehört nicht zur Website. Lizenz: CC BY 4.0.

**A-29 Testkorpus.**
- **Bestand:** in `.local/corpus/` mit `registry.json` (297 Dateien, 1,06 GB). OpenNeuro (CC0): ds003775 (EDF), ds002778 (BDF), ds004148 (BrainVision), ds004504 (EEGLAB), ds000248 (FIF). PhysioNet PSG-IPA (CC BY 4.0), geladen vom offiziellen AWS-Spiegel und gegen die Prüfsummen von physionet.org geprüft.
- **Zugriff:** Geladen wird über die OpenNeuro-API statt über EEGDash (E4).
- **Kalibrierung:** lädt bis zu 20 Probanden je Datensatz nach (≈ 2,6 GB, nur lokal, nicht im CI-Cache).
- **Herkunft:** `DATA_SOURCES.md` nennt je Datensatz Version/DOI, Urheber, Lizenz, Zitierhinweis und Art der Änderung. Korpusauszüge kommen nur mit Eintrag dort ins Repository; synthetische und abgeleitete Fixtures liegen getrennt.
- **Golden-Liste:** Echte Metadatenfehler im Korpus dienen als Positiv-Testfälle.

**A-30 NeuroVault.**
- **Ablage:** `.neurogrid/vault/`; der Pfad ist änderbar. v0.2 = NV-F01–F03; v1.0 = NV-F04–F07.
- **Zugriffsereignisse:**
  - Befehle schreiben automatisch Ereignisse, wenn ein Vault vorhanden ist. Rolle, `purpose` und `approval_ref` kommen aus `--role` bzw. der toml. Kein OS-Benutzer, kein Rechnername.
  - Dateisperre um Lesen und Anhängen, fsync danach.
  - Ist der Vault schreibgeschützt: Warnung und Befund, kein Exit 2.
  - `report` findet den Vault über `--config`; ohne Angabe schreibt es kein Ereignis.
- **Determinismus:** Der Kopf-Hash steht nur in Bericht und Export, nicht in results.json. Rollenbefunde entstehen nur aus Ereignissen vor dem aktuellen Lauf.
- **Grenzen der Hashkette** (ehrlich formuliert):
  - Erkannt werden Ändern, Einfügen, Löschen und Umsortieren innerhalb der Kette.
  - Kürzen am Ende und vollständiges Neuschreiben erkennt nur `vault verify --expect-head <hash>` gegen einen extern festgehaltenen Kopf-Hash.
  - Erfasst sind nur Zugriffe über NeuroGrid.
  - Begriffe wie „manipulationssicher“, „tamper-proof“ und „防篡改“ sind verboten.
- **Rollen:** Das Rollenregister wird beratend geprüft, nicht erzwungen.
- **Aufbewahrung** (`retention.yaml`):
  - je Objekt (PIA-Bericht, Zugriffsprotokoll, ggf. Register) `created`, `min_until` und optional `review_at`
  - `min_until` < created + 3 Jahre → Exit 2
  - fehlende Objekte oder gekürztes Protokoll → Befund
  - Erinnerung ≤ 90 Tage vor `min_until`, neutral formuliert („Mindestaufbewahrung endet – über Weiteraufbewahrung oder Löschung nach eigener Rechtsprüfung entscheiden“)
  - keine Fristlogik für EEG-Daten; die Zuordnung Art. 56 → PIA und Protokoll ist als Auslegung gekennzeichnet
- **Folgenabschätzung:** Vorlage zh/en, nur als Gliederung. Kopfzeile „ENTWURF/PLATZHALTER – keine Rechtsberatung – vor Verwendung durch eine in der VR China zugelassene Rechtsberatung prüfen“. Enthält die Auslöser nach Art. 55 als Checkliste, die Prüfpunkte nach Art. 56 Abs. 1 als Überschriften und Felder `【待填写】`; keine vorausgefüllten Rechtsgrundlagen oder Bewertungen. Eine unbearbeitete Vorlage ergibt einen Befund.
- **Einwilligung:**
  - Wirksam ist die höchste Version mit Datum ≤ `as_of`; ein Teilwiderruf ist eine neue Version.
  - Ohne Vault oder Einwilligungsdaten ist M14 not_checkable (grau); ein Fehler entsteht nur mit `--strict` oder bei konfiguriertem `[consent]`.
  - Widerruf oder fehlende Einwilligung bei konfiguriertem Einwilligungsmodell = Fehler.
  - Probanden werden nur über die pseudo_id geführt.
- **Neueinwilligung:**
  - Risiken führen `affected_uses` und `min_consent_version`.
  - Betroffene Probanden erscheinen als Befund je Proband (eigene core-Regel, warning) und in einem eigenen Berichtsabschnitt, mit dem Text „laut Risikoregister möglicherweise Neueinwilligung erforderlich – Entscheidung durch die Ethikkommission“.
- **Export-ZIP** (NV-F07):
  - Inhalt: genau die fünf Bestandteile plus `index.json` (SHA-256 je Teil, Kopf-Hash, Werkzeugversion, fester Satz).
  - Nur reguläre Dateien aus dem Vault; keine Signale, keine Einwilligungsdaten.
  - `--report` muss ein NeuroGrid-Bericht sein.
  - Das Export-Ereignis wird vor dem Packen angehängt; Archivnamen und Zeitstempel sind fest.

**A-31 Befehle und Optionen.** Die Befehle aus §13 bleiben. Notwendige Ergänzungen (von PRD oder Annahmen getragen):
`check --strict --manifest --evidence --as-of --role --allow-draft-rulepacks`, `convert --config --to gbt47127`,
`report --out --format dossier`, `vault verify [--expect-head]`, `vault consent add <Felder>`,
`vault log <Felder>`, `vault export --report --out`, `diff --format json`, globale `--lang`, `--debug`.
Reine Komfort- oder Zusatzfunktionen stehen in E3 zur Freigabe.

**A-32 GB/T 47127 in v0.2** (§6/NG-F03 statt §20).

**A-33 Versionsvergleich.**
- Schlüssel wie in A-09.
- „verändert“ heißt: gleicher Schlüssel, aber anderer Status oder anderer Messwert (nach Rundung).
- Exit 1 bei neuen error-Befunden.

**A-34 CI-Integration (v1.0).**
- Wiederverwendbare GitHub Action; dazu eine GitLab-CI-Vorlage als Teil der Auslegung von „CI-Integration“.
- Beide sind nur für selbst gehostete Runner im Kundennetz gedacht. Die Action bricht auf GitHub-gehosteten Runnern ab, außer bei `allow-hosted-runner: true` für öffentliche oder synthetische Daten.
- Kein Artefakt-Upload per Standard; Warnhinweis zh/en.
- Als erfüllt gilt sie erst nach einem echten GitHub-Lauf.

**A-35 PDF-Nachweismappe (v1.0).**
- Inhalt: ein PDF mit Deckblatt (fester Satz), Bericht zh und en, Nachweisliste mit SHA-256, Manifest- und NeuroVault-Zusammenfassung.
- Nie Signale, keine Einwilligungsdaten.

**A-36 NG-F17.**
- **Ort:** eigenes uv-Projekt `research/neuroarena/` mit eigenem Lock; torch aus dem CPU-Index, außer CUDA wird gebraucht. Gehört nicht zum Lizenz-Gate des Pakets; hat ein eigenes Lizenz-Gate.
- **Datensätze:** Zhou2016 (CC0), PhysionetMI (ODC-By), Kalunga2016 (CC BY 4.0), mit Attributionsblock.
- **Qualitätsstufe:** siehe A-45.
- **Abgrenzung im Bericht:** „gilt nur für die untersuchten öffentlichen Datensätze und Decoder; keine Aussage über Leistung oder Sicherheit eines Medizinprodukts“.
- **Reproduzierbarkeit:** Seeds, deterministische Algorithmen, CPU-Lauf, dokumentierte Toleranz.

**A-37 Gates.** G1–G4 sind Geschäftsentscheidungen des Projektverantwortlichen (BIZ-05). Software-Phasen stoppen
nach P5 (v0.1) und nach Abschluss von v0.2 sowie an den technischen Go/No-Go-Punkten (Normtexte).

**A-38 Urheber.** „Ammar Ahad“ in LICENSE/NOTICE/pyproject (D-07).

**A-39 Paketname.** PyPI `neurogrid`; Befehl `neurogrid`.

**A-40 gxdsl008 ohne Normtext.**
- `source_status: secondary` (Werte aus zweiter Hand), Klausel „unbekannt (Normtext nicht zugänglich)“.
- Alle fünf Regeln warning; Abdeckungsmaß n/a.
- Format-Regel = Speicherformat der Aufnahmen (EDF/HDF5); AES-256/RBAC = manuelle Regel (Nachweis ab P4); Prüfsummen = halbautomatisch über das Manifest.
- Gleiche Schwellen wie in core (500 Hz, 5 kΩ) erzeugen bewusst je Paket einen eigenen Befund, denn jedes Paket wird unabhängig bewertet. Im Bericht sind sie miteinander verknüpft.

**A-41 Platzhalter-Regelpakete.**
- **Status:** `source_status` ∈ {placeholder, secondary, inventory, final}.
- **Gerüst yyt2029** `0.2.0-draft`: placeholder; die PRD-Beispielregel hat die Klausel „TBD“.
- **Laden:** placeholder-Pakete nur mit `--allow-draft-rulepacks`.
- **Kennzeichnung:** Banner auf dem Deckblatt; in der Klauselspalte steht „Platzhalter – nicht aus dem Normtext“.
- **Wirkung:** Befunde aus placeholder-Paketen zählen nicht für Exit, Ampel und Abdeckung. Keine erfundenen Regeln.

**A-42 Python-Versionen.** 3.11–3.13, `requires-python = ">=3.11,<3.14"`; Entwicklung mit 3.12.

**A-43 Board-ID.** Jeder Commit und jeder Fortschrittseintrag nennt die Anforderungs-IDs.

**A-44 Schweregrad der kalibrierten Metriken.** Für M06, M07 und M09 gilt warning.

**A-45 Qualitätsstufe für NG-F17.** Das ungünstigste Verhältnis aus Kernmetrik und Schwelle (M06, M07, M08, M09a, M09b)
ergibt Q1 (< 0,5) bis Q5 (≥ 1,5). Gilt nur für `research/`.

**A-46 Integritätsprüfungen jenseits des Validators** innerhalb von M01–M04:
- **M01:** Lesbarkeit, Größe gegen den Kopf, Begleitdateien.
- **M02:** TaskName = task-Label, BIDSVersion-Format, leerer Name.
- **M03:** Sidecar-Rate gegen die Daten.
- **M04:** Kanalzahl in Sidecar, `channels.tsv` und Datei.

**A-47 Netzfrequenz-Plausibilität und Ablageort der Konfiguration.**
- M07 misst zusätzlich bei der anderen Netzfrequenz; passt sie besser, entsteht ein Hinweis.
- Die Konfiguration liegt standardmäßig in `<datensatz>/.neurogrid/neurogrid.toml`.

**A-48 Python-, Plattform- und Versionsgrenzen.**
- **Auslieferung als Anwendung:** Alle ergebnisrelevanten Bibliotheken sind in `pyproject.toml` exakt gepinnt: numpy, scipy, scikit-learn, mne, mne-bids, pyprep, autoreject, python-picard, mne-icalabel, onnxruntime, edfio, Validator, deno, Playwright.
- **numpy/scipy:** für 3.11–3.13 auf eine gemeinsame Linie gepinnt (numpy 2.4.x, scipy 1.17.x; im Lock zu bestätigen).
- **Bauen:** `no-build` in uv.
- **Linux:** x86_64, glibc ≥ 2.28, verifiziert auf Debian 12/Ubuntu 22.04+. ARM64 ist nicht unterstützt.
- **Installation:** Bytecode wird vorkompiliert.

**A-49 Netzwerkschutz.**
- **Audit-Hook** im Python-Prozess: blockiert und protokolliert Socket-Verbindungen und DNS-Auflösungen zu Nicht-Loopback-Zielen. Ausdrücklich gilt das **nur für den Python-Prozess**.
- **Unterprozesse** sind eigens geschützt:
  - Deno mit `--deny-net` und `DENO_NO_UPDATE_CHECK=1`
  - Chromium mit fest gesetzten Flags (`--disable-background-networking`, `--disable-component-update`, `--disable-breakpad`, `--no-pings`)
  - `context.route` lässt nur die exakte Berichtsdatei und `data:` zu
- **onnxruntime:** `onnxruntime.disable_telemetry_events()` vor der ersten Session.
- **Codeverbote** (Quelltext-Test): `mne.datasets`-Fetcher, `mne_icalabel.datasets`, `mne.Report`, `mne.sys_info()` ohne `check_version=False`. Dazu ein Scan der installierten Laufzeitpakete nach Telemetrie- und Update-Mechanismen.
- **Nachweis auf Betriebssystemebene:** Linux-Lauf ohne Netz (`unshare -rn` bzw. Container mit `--network none`) und unter `strace -f -e trace=connect`. Unter Windows Firewall-Test auf einem Runner oder „nicht verifiziert“.
- **Nicht steuerbar:** Dienste des Betriebssystems (Virenscanner-Proben, Cloud-Sync) steuert NeuroGrid nicht; das steht in der Doku.

**A-50 Lesart und Messung von NG-N02.**
- **Lesart:** „1 GB EDF“ = eine EDF-Datei von 1 GB (E5).
- **Messung:** Wandzeit des echten Prozesses `neurogrid check` (Start, Importe, discover, alle core-Regeln, Schreiben von results.json) und Spitzen-RSS inkl. Kindprozessen.
- **Grenzen:** hier mit 4 Kernen < 150 s; auf einem Runner mit 4 vCPU/16 GB < 300 s, sobald CI verfügbar.
- **Kanalzahl:** gemessen werden 64, 128 und 256 Kanäle.
- **Zusatzmessung:** 1 GB verteilt auf viele kurze Aufnahmen. Sie wird berichtet, ist aber kein Abnahmekriterium von NG-N02.

**A-51 Datenschutz in allen Ausgaben (NG-N05).** Gilt für Konsole, Bericht, results.json, scan-JSON, diff, Nachweismappe, ZIP, Logs und PDF-Metadaten.
- **Allowlist statt Denylist:** Adapter übernehmen nur gelistete Felder. Nicht übernommen werden u. a. EDF-Patient-/Aufnahmefeld, FIF subject_info/experimenter/description/meas_id, EEGLAB subject/comments/filepath/history und der BrainVision-Kommentar.
- **Pfade:** Die Datensatzwurzel wird `<dataset>`, das Benutzerverzeichnis `~`. Keine Rechner- oder Benutzernamen.
- **Aufnahme-IDs bei Rohordnern:** pseudonym, aus der Zuordnung oder als `rec-<sha256(relpfad)[:8]>`. Die Zuordnung ID → Pfad liegt nur in `.neurogrid/`. Klarpfade gibt es nur mit ausdrücklicher Option (E3).
- **Hinweise:** wenn Labels oder Dateinamen wie Namen oder Kennnummern aussehen (Nicht-ASCII-Buchstaben, ≥ 6 Ziffern).
- **Demografie und Labels** nur aggregiert, Zellen < 5 unterdrückt.
- **Fehler:** Typer ohne lokale Variablen; Traceback nur mit `--debug` und bereinigt.
- **Logdateien:** keine standardmäßig.
- **Test:** Fixtures mit eingepflanzten Kennungen je Format; alle Ausgaben inkl. PDF-Text werden danach durchsucht.

**A-52 Pfadsicherheit.** Alle Pfade aus Dateien oder Optionen gehen durch eine zentrale Prüfung. Das gilt für Verweise in BrainVision/EEGLAB, splits.tsv, provenance.yaml, manifest.json, Nachweise, Vault, Regelpakete und Import-Tabellen.
- **Nur relative Pfade:**
  - kein `..`
  - keine Laufwerks-, UNC- oder Gerätepfade
  - keine Alternate Data Streams
  - keine reservierten Namen
- **Danach:** `resolve(strict=True)` und `is_relative_to(<Datensatz- bzw. Projektwurzel>)`.
- **Symlinks und Junctions:** werden nicht verfolgt, sondern gemeldet.
- **Projektwurzel:** Ordner der toml bzw. Datensatzwurzel.
- **Tests:** UNC, `..`, Junction, ADS in der Windows-CI.

**A-53 Eingabesicherheit.**
- **YAML:** eigener sicherer Lader ohne Aliase; doppelte Schlüssel = Fehler; Größen- und Tiefenbegrenzung.
- **Pydantic** im strict-Modus.
- **Längengrenzen:** für Regex und Dateinamen.
- **Konsole:** Fremdtext mit `rich.markup.escape`, Steuerzeichen werden entfernt.
- **Jinja2:** mit Autoescape.
- **Unterprozesse:** nur mit Argumentlisten.
- **Archive:** Entpacken nur mit Pfadprüfung je Eintrag.

**A-54 Temporäre Dateien.**
- Je Lauf ein Arbeitsordner (unter `--out` bzw. `.neurogrid/tmp`).
- `TMP`/`TMPDIR`, `JOBLIB_TEMP_FOLDER`, das Chromium-Profil und die Validator-Ausgabe zeigen dorthin.
- Gelöscht wird im `finally` und beim nächsten Start.
- Test: keine Reste in %TEMP%.

**A-55 Normtexte und Urheberrecht.**
- **Erlaubt im Repository:** Klauselnummer, eigene Kurzbeschreibung, Normsprachklasse (应/宜/可), Phase und Einstufung.
- **Nicht erlaubt:** wörtliche Klauseltexte, Tabellen, Abbildungen.
- **Ablage:** Das Volltext-Inventar und die Normtexte bleiben in `.local/`, nie in CI-Cache, Bündel oder Korpus.
- **ISO-Abbildungstabelle:** Vor ihrer Veröffentlichung werden die ISO-Lizenzbedingungen geprüft.
- **DoD:** Der Prüfpunkt „keine Normtext-Zitate“ gehört zu P7, P8 und P10.

**A-56 Lizenz-Hinweise.**
- **Erzeugung:** `THIRD_PARTY_NOTICES` entsteht automatisch aus pip-licenses (mit Lizenztexten), `*.libs`- und LICENSES_bundled-Dateien der Wheels, den Lizenzen von Deno, Node (Playwright-Treiber) und Validator-Bündel, der Attribution von BIDS- und HED-Schema sowie der OFL.
- **Gate:** Das Lizenz-Gate hat zwei Stufen (exakte Allowlist plus Copyleft-Sperre) und läuft getrennt für Laufzeit, Dev und research. Für Nicht-Python-Bestandteile gibt es eine Liste mit erwarteten Lizenzen; Abweichung = CI-Fehler.
- **Rückfrage:** Herkunft und Lizenz der ICLabel-Gewichte werden geklärt.

**A-57 Wortwahl.**
- **Sperrliste** zh/en/de als Datei, u. a.: konform, zertifiziert, compliant, certified, conformity, meets the requirements, 符合…要求, 合格, 认证, 达标, 通过 YY/T, „erfüllt die Norm“; dazu „合规“ als Phasen- oder Ampeltext.
- **Geltungsbereich:** Vorlagen, Sprachtabellen, Regeltitel, Doku, README und die pyproject-Beschreibung.
- **Ausnahme:** Einzige exakte Ausnahme ist der feste Satz.
- **Gesetzesartikel:** Befunde nennen keine Gesetzesartikel.

**A-58 Linux-Plattform.** Unterstützt sind x86_64, glibc ≥ 2.28, Debian 12 und Ubuntu 22.04+. In der CI erzeugt ein Job
das PDF in `debian:12-slim` mit `--network none` und einer dokumentierten apt-Liste.

**A-59 Skalierung der Befunde.**
- Bestandene Befunde werden je Regel und Aufnahme gezählt.
- Kanaldetails erscheinen nur bei Verletzung, mit Obergrenze (20) plus Anzahl.
- Der Bericht zeigt je Regel höchstens 50 Zeilen; die vollständige Liste steht in JSON bzw. einem CSV-Anhang.
- Skalierungstest: 1000 Aufnahmen × 64 Kanäle.

**A-60 Vorbedingungen der Metriken.** Jede Metrik hat Vorbedingungen; ist eine nicht erfüllt, ist das Ergebnis not_checkable mit Grund-Schlüssel, nie Exit 2.
- **Montage-Quelle:** `electrodes.tsv` > Abbildung aus M04 auf die Standardmontage > keine.
- **Ohne Positionen:** M06 läuft ohne RANSAC, M09a ohne Interpolation, M09b ist not_checkable.
- **Mindestwerte:** ≥ 60 s nutzbare Daten für M06/M09; ≥ 16 EEG-Kanäle für M09b (konfigurierbar). Sie stehen in results.json.

**A-61 Kanonisches JSON.**
- **Nicht-endliche Werte:** werden null mit not_checkable; `allow_nan=False`.
- **-0.0:** wird 0.0.
- **Sortierung:** feste Reihenfolge error > warning > info; danach Regel-ID, Objekt, Unterschlüssel.
- **Regel-Metadaten:** results.json enthält einen Block `rules` (ID, Klausel, Titel, Phase, Schweregrad, Nachweisart, `source_status`) und den SHA-256 je Paket; `report` liest nur results.json.
- **Wirksame Konfiguration:** steht kanonisch und bereinigt in results.json und im Anhang.
