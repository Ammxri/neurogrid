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

## Entscheidungen zu STOPP 2 (11.10.2026)

Der Projektverantwortliche hat das Konzept freigegeben und E1–E5 nach Empfehlung entschieden.

**D-08 (E1) Binärteile.**
- D-05 gilt für Python-Pakete.
- Native Bibliotheken in Wheels (z. B. libquadmath, libgfortran) sind mit Hinweis in den Notices erlaubt.
- Die Chrome Headless Shell kommt nicht ins Offline-Bündel. `tools/install_pdf_browser.py` lädt sie online oder spielt eine vom Kunden bereitgestellte zip mit Prüfsumme ein.

**D-09 (E2) CI und Linux.**
- Der Projektverantwortliche legt das GitHub-Repo `neurogrid` an. Nach jeder Phase darf auf `dev` gepusht werden, nicht auf `main`.
- Docker Desktop ist derzeit nicht verfügbar, weil der Projektverantwortliche remote arbeitet. Lokale Linux- und Offline-Tests entfallen deshalb vorerst.
- Linux wird über die GitHub-CI geprüft, sobald das Repo angelegt und die URL genannt ist. Bis dahin bleiben TECH-05, TECH-11 und der Linux-Teil von NG-N04 offen bzw. „nicht verifiziert“.

**D-10 (E3) Zusätze.** a–h ja (`--jobs`, `consent add --from`, `log --show`, `manifest --out`,
`--strip-identifying-headers`, `--show-paths`, Release-Signatur, GitLab-CI-Vorlage); i (Bericht auf Deutsch) und
j (`--list-checks`) nein.

**D-11 (E4) Testkorpus ohne EEGDash.** Freigegebene Abweichung von §9 (LIB-09); geladen wird über OpenNeuro-API und PhysioNet.

**D-12 (E5) NG-N02.** Gemessen wird an einer 1-GB-EDF-Datei:
- hier mit 4 Kernen: < 150 s (für 256 Kanäle angepasst durch D-14)
- auf einem Runner mit 4 vCPU/16 GB: < 300 s
- jeweils mit 64, 128 und 256 Kanälen

**D-13 Konzeptfreigabe.** KONZEPT.md ist freigegeben, einschließlich der Regel für fehlende Normtexte (normunabhängige
Phasen vorziehen; Stopp, wenn nur normabhängige Phasen übrig sind) und der STOPPs nach v0.1 und v0.2.

## Entscheidung zu STOPP R4 (21.10.2026)

**D-14 (STOPP R4) NG-N02 und Parallelisierung einer Aufnahme.** Freigegeben sind die Optionen 1 und 2 aus der
Phasenmeldung zu P3:
- **Parallelisierung (Option 1):** `--jobs N` verteilt auch die Arbeitsschritte einer Aufnahme auf N Prozesse.
  - Der Stream läuft neben der Stichprobe, autoreject neben der ICA.
  - Bei einer einzelnen Aufnahme nutzt autoreject für seine Schwellensuche zusätzlich die freien Prozesse.
  - Die Methodik bleibt unverändert, das Ergebnis ist byte-gleich zu `--jobs 1`.
- **Grenzen (Option 2, ändert D-12 und A-50):**
  - Hier mit 4 Kernen (`--jobs 4`): < 150 s für 64 und 128 Kanäle; für 256 Kanäle gilt die PRD-Grenze von < 300 s.
  - Auf dem Runner mit 4 vCPU/16 GB bleibt es bei < 300 s.

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
- **Erfasste Dateien:** alles im Datensatz einschließlich `.neurogrid/` (splits.tsv, neurogrid.toml, consents.yaml, roles.yaml, risks.yaml, evidence.yaml, retention.yaml). Ausgenommen sind `manifest.json` selbst und das eigenständig hashverkettete `vault/access.jsonl` mit seiner Sperrdatei (präzisiert durch A-82).
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
- **Audit-Hook** im Python-Prozess: blockiert und protokolliert Socket-Verbindungen, Datagramme (sendto, sendmsg) und alle Namensauflösungen (getaddrinfo, gethostbyname[_ex], gethostbyaddr, getnameinfo) zu Nicht-Loopback-Zielen. Ausdrücklich gilt das **nur für den Python-Prozess**.
- **Grenze des Hooks:** Der Windows-Proactor von asyncio baut Verbindungen ohne Audit-Ereignis auf. NeuroGrid nutzt kein asyncio; ein Quelltext-Test verbietet Netzwerkmodule (asyncio, socket außerhalb des Hooks, ssl, http, urllib.request u. a.) per AST, auch als Attributzugriff.
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
- **Grenzen:** hier mit 4 Kernen (`--jobs 4`) < 150 s für 64 und 128 Kanäle, < 300 s für 256 Kanäle (D-14); auf einem Runner mit 4 vCPU/16 GB < 300 s, sobald CI verfügbar.
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

**A-60 Vorbedingungen der Metriken.** Jede Metrik hat Vorbedingungen; ist eine nicht erfüllt, ist das Ergebnis not_checkable mit Grund-Schlüssel, nie Exit 2. Präzisiert durch A-79 (P3).
- **Montage-Quelle:** `electrodes.tsv` > Abbildung aus M04 auf die Standardmontage > keine.
- **Ohne Positionen:** M06 läuft ohne RANSAC, M09a ohne Interpolation, M09b ist not_checkable.
- **Mindestwerte:** ≥ 60 s nutzbare Daten für M06/M09; ≥ 16 EEG-Kanäle für M09b (konfigurierbar). Sie stehen in results.json.

**A-61 Kanonisches JSON.**
- **Nicht-endliche Werte:** werden null mit not_checkable; `allow_nan=False`.
- **-0.0:** wird 0.0.
- **Sortierung:** feste Reihenfolge error > warning > info; danach Regel-ID, Objekt, Unterschlüssel.
- **Regel-Metadaten:** results.json enthält einen Block `rules` (ID, Klausel, Titel, Phase, Schweregrad, Nachweisart, `source_status`) und den SHA-256 je Paket; `report` liest nur results.json.
- **Wirksame Konfiguration:** steht kanonisch und bereinigt in results.json und im Anhang.

## Annahmen aus der Umsetzung

**A-62 Regelpaket-Feld `norm` (P1).** Das Regelpaket-Format erhält das optionale Feld `norm` (Standard
`false`). Nur Pakete mit `norm: true` und `source_status` inventory/final bekommen ein Abdeckungsmaß (A-16);
`core` und `bids` sind keine Normpakete. Kleine, rückwärtsverträgliche Erweiterung des Formats aus §11.

**A-63 Konfigurationsabschnitte (P1).** `neurogrid.toml` hat zusätzlich den Abschnitt `[dataset]` (id, name,
version, source, license – die Felder von DM-01, soweit nicht aus `dataset_description.json` lesbar). Die
Begründung für gemischte Abtastraten (M03, A-18) steht in `[metadata] mixed_sampling_rates_reason`.
Ohne Datensatz-ID steht im Ergebnis „unnamed“; der Ordnername wird nicht verwendet (könnte identifizierend sein).

**A-64 Heuristik für identifizierende Kopfzeilen (CORE-M01-05).** Überarbeitet nach dem Review von P1.
- **EDF+, Patientenfeld:** identifizierend, wenn Code, Geburtsdatum, Name oder weiterer Text nicht „X“ ist. Platzhalter ist in EDF+ nur „X“. Das Geschlecht zählt nur, wenn dort etwas anderes als M, F oder X steht.
- **EDF+, Aufnahmefeld:**
  - Krankenhaus-Code oder Techniker nicht „X“ → `recording`. Zusätzliche Unterfelder nach der Gerätebezeichnung werden wie Freitext geprüft (Name, sechs und mehr Ziffern, Nicht-ASCII → `recording`; Datum → `date`).
  - Datum im Startdate-Unterfeld nicht „X“ und nicht „01-JAN-JJJJ“ → `date`. Die Gerätebezeichnung zählt nicht.
  - Fehlt das Schlüsselwort „Startdate“, wird das Feld als Freitext geprüft.
- **Einfaches EDF:** Das Patientenfeld ist Freitext und gilt als identifizierend, sobald es etwas anderes als Platzhalter enthält (X, -, _, 0, anonymous, anon, unknown, n/a, none). Im Aufnahmefeld führt ein Datum zu `date` (auch ISO-Form JJJJ-MM-TT; Platzhalter wie 01-JAN-JJJJ oder JJJJ-01-01 ausgenommen), sechs und mehr Ziffern oder Nicht-ASCII-Bytes zu `recording`.
- **Unterstriche** gelten bei der Namenssuche als Leerzeichen (EDF+ schreibt Leerzeichen in Unterfeldern als `_`).
- **Startdatum (festes Feld):** Nur ein im Kalender gültiges TT.MM.JJ außer 01.01.JJ gilt als echtes Datum. Ein leeres, fehlerhaftes oder unmögliches Datum (00.00.00, 31.02.21) ist ein Kopfzeilenfehler (CORE-M01-02), kein Datum.
- **Ausgabe:** Nur die Feldnamen werden ausgegeben, nie die Werte. Schweregrad info. Auch pseudonyme Codes (z. B. `sub-01` aus MNE-Exporten) gelten als Kennung; bei info ist ein Hinweis zu viel gewollt.

**A-65 Übersprungene Ordner und Lesbarkeit.**
- **Übersprungen:** In BIDS-Datensätzen die Ordner `derivatives`, `sourcedata`, `code` und `stimuli` (keine Rohdaten); in allen Datensätzen versteckte Einträge (`.neurogrid`, Punktdateien).
- **Lesbarkeit (M01-01):** MNE liest den ersten und den letzten Sekundenblock. Eine abgeschnittene EDF liest MNE ohne Fehler; erkannt wird sie über die Kopfprüfung (CORE-M01-02, Dateigröße gegen Kopf).

## Annahmen aus dem Review von P1

Ein Review mit drei Prüfrichtungen (Korrektheit, Sicherheit/Datenschutz, DoD-Treue) und Gegenprüfung der
wesentlichen Befunde hat 29 kleine und 21 gegengeprüfte Befunde geliefert. Behoben sind alle bestätigten. Diese
Annahmen halten fest, wie dabei Lücken der Spezifikation gefüllt wurden.

**A-66 Projektwurzel und Pfade in `neurogrid.toml` (A-52).**
- Die Projektwurzel ist:
  - für eine toml in einem Ordner `.neurogrid` der Ordner darüber (auch bei `--config`);
  - für eine andere toml im Datensatz die Datensatzwurzel;
  - sonst der Ordner der toml.
- Pfade in der toml (`check.rulepacks`, `ai.splits`, `vault.path`) sind nur relativ zulässig: kein `..`, keine Laufwerks-, UNC- oder Gerätepfade. Verstöße enden beim Laden mit Exit 2 und Feldangabe.
- Regelpakete aus der toml werden innerhalb der Projektwurzel aufgelöst, ohne Links zu folgen. Pfade auf der Kommandozeile (`--rulepack`, `--config`, `--out`) sind Bedienerpfade und beziehen sich auf das Arbeitsverzeichnis.
- Ein Link als `.neurogrid` oder als toml am Standardort wird nicht verfolgt (Exit 2).
- Bedienerpfade dürfen über Links führen (der Bediener hat den Pfad gewählt). Innerhalb des Datensatzes werden Links nie verfolgt, ebenso wenig eine verlinkte Einzeldatei als Ziel.
- Eine einzelne Datei als Ziel wird wie ein Rohordner mit genau dieser Datei geprüft. Die ID folgt der gespeicherten Schreibweise des Namens, nicht der getippten.
- Dasselbe Regelpaket, auf mehreren Wegen genannt (toml und Kommandozeile, andere Schreibweise), wird einmal geladen. Zwei verschiedene Dateien mit gleichem Paketnamen sind ein Fehler (Exit 2).

**A-67 Netzwerkpfade auf der Kommandozeile (A-52, NG-N01).** Unter Windows gilt jede Wurzel aus zwei Trennzeichen
(Schrägstrich und Backslash in beliebiger Mischung) als UNC- oder Gerätepfad. Die Prüfung wird auf dem aufgelösten
Pfad wiederholt (Links auf Netzfreigaben). Verbundene Netzlaufwerke werden ebenfalls abgelehnt. Geräte- und
Namensraumpfade (`\\?\`, `\\.\`, `\??\`, GLOBALROOT) werden schon vor jedem Dateizugriff abgelehnt, ebenso
reservierte Gerätenamen (CON, PRN, AUX, NUL, CONIN$, CONOUT$, COM/LPT mit 1–9 und ¹²³) in jedem Pfadteil. Dieselbe
Liste gilt für Pfade aus Dateien (A-52). Doppelpunkte nach dem Laufwerk (Datenströme)
sind nur unter Windows verboten; unter Linux sind sie gültige Zeichen.

**A-68 Stabile Befundschlüssel und Ausnahme-Abgleich (A-09, A-14).**
- Intern hat jede Aufnahme drei stabile Namen: den relativen POSIX-Pfad, die pseudonyme ID und den pseudonymen Dateinamen (ID plus Endung, wie er in Rohordnern angezeigt wird).
- Ausnahme-Muster werden gegen alle drei und gegen die angezeigte ID geprüft. Der Befundschlüssel wird über den relativen Pfad gebildet.
- `--show-paths` ändert damit nur die Anzeige, nie Status, Exitcode oder Schlüssel.

**A-69 Ausnahme-Muster in Ausgaben (A-51).** Bei Rohordnern ohne `--show-paths` erscheinen Muster, die mehr als
Platzhalter (`*`, `**`, `*.ext`) oder pseudonyme IDs enthalten, in results.json und im Bericht nur als
`pattern-<sha256[:8]>`. Der Konfigurations-Hash wird weiter über die echte Konfiguration gebildet.

**A-70 Dateiname in M01-Befunden (A-12 und A-51).** „Mit Dateinamen“ heißt bei Rohordnern: pseudonyme ID plus
Endung (z. B. `rec-2c710f52.cnt`). Den Klarnamen zeigt `--show-paths`. In BIDS-Datensätzen steht immer der relative Pfad.

**A-71 Hinweis auf identifizierende Dateinamen (A-51).**
- Enthält ein Pfadsegment einer Datendatei Nicht-ASCII-Buchstaben oder sechs und mehr Ziffern in Folge, gibt es einen Hinweis.
- Er erscheint in `check` als Notice und in `scan` auf der Konsole sowie als `suspicious_names`.
- Er nennt nur die Anzahl, keine Namen.

**A-72 Probanden in `scan` (CLI-01).** Bei BIDS-Datensätzen zählt `scan` die `sub`-Labels der Datendateien. Bei
Rohordnern steht „unbekannt“, bis die Zuordnung aus der toml (A-05, P2) vorliegt. Aus BIDS-Dateinamen werden
`subject`, `session`, `task` und `run` in das Datenmodell übernommen (Herkunft `bids_filename`).

**A-73 Kommandozeile.**
- `--rulepack` ist wiederholbar und wird nicht an Kommas getrennt. Groß-/Kleinschreibung bleibt erhalten. Kommalisten gibt es nur für `--lang` und `--format` (A-08).
- `rulepacks = []` in der toml ist ungültig.
- Sprachangaben in Locale-Form werden normalisiert (`zh_CN.UTF-8` → `zh`). Eine nicht verfügbare oder leere Sprache in `--lang` oder `NEUROGRID_LANG` endet mit Exit 2 statt mit stillem Rückfall.
- `--out` darf kein Ordner sein (auch kein Pfad mit Trennzeichen am Ende). Geschrieben wird über eine temporäre Datei im Zielordner, die bei Fehlern gelöscht wird (A-54). Ist der Zielort nicht beschreibbar, gibt es eine eigene Meldung (Exit 2).
- Warnungen von Bibliotheken erscheinen nur als übersetzter Hinweis mit ihrer Kategorie, ohne Fremdtext und Pfade (A-07, A-51). Beim Lesen der Daten werden sie ganz unterdrückt; das Ergebnis zählt.
- Mit `--debug` ist der Traceback frei von Steuerzeichen; Benutzerverzeichnis und Datensatzwurzel sind ersetzt, und Pfade unterhalb der Datensatzwurzel werden nach `<dataset>/` abgeschnitten.
- Ohne Argumente zeigt `neurogrid` die Hilfe (Exit 2).

**A-74 Eingaben.**
- **Ordnerformate:** EGI-MFF (`.mff`) und MEF3 (`.mefd`) sind Ordner. Jeder solche Ordner zählt als eine nicht unterstützte Aufnahme (M01-04) und wird nicht betreten.
- **Kodierung:** `neurogrid.toml` und Regelpakete werden als UTF-8 mit oder ohne BOM gelesen. Andere Kodierungen enden mit Exit 2 und klarer Meldung. Der SHA-256 eines Regelpakets wird über die Dateibytes gebildet (prüfbar mit `sha256sum`).
- **Größe und Tiefe:** Größengrenzen gelten vor dem Lesen; die YAML-Tiefe wird schon beim Einlesen begrenzt. Dateinamen, die kein gültiges Unicode sind, werden mit Escape-Folgen angezeigt und brechen den Lauf nicht ab.
- **Nicht lesbare Einträge:** Ordner, die nicht aufgelistet werden können, und Datendateien, die sich nicht öffnen lassen (z. B. Namen mit Punkt am Ende unter Windows), sind CORE-M01-01-Fehler mit pseudonymer ID. Sie werden nicht still übersprungen. `scan` listet sie als „nicht lesbare Einträge“.
- **Links im Datensatz:** Nicht verfolgte Links und Junctions meldet auch `check`, als Notice mit Anzahl (Stufe warning) und auf der Konsole.
- **Reine Annotationsdateien** (EDF+ nur mit „EDF Annotations“, z. B. Hypnogramme) sind lesbar. Sie zählen aber nicht als Aufnahme für „Datensatz ohne lesbare Aufnahme“.
- **`dataset_description.json`:** Übernommen werden nur Name (200 Zeichen), License (80), BIDSVersion und DatasetType (je 40), ohne Steuerzeichen. Eine unlesbare oder zu tief verschachtelte Datei gilt als leer.
- **BrainVision-Begleitdatei:** Ob eine `.eeg` zu einer `.vhdr` gehört, wird auf allen Plattformen ohne Rücksicht auf Groß-/Kleinschreibung entschieden.
- **Ausnahme-Muster:** Ausnahme-Muster laufen mit einem linearen Matcher, auch bei vielen `**`.
- **Übersetzung:** Unbekannte Schlüssel (etwa aus einer fremden results.json) werden nie als Formatvorlage benutzt.

**A-75 Nicht-endliche Werte (A-61, A-60).**
- Zahlenfelder im EDF-Kopf müssen schlichte Dezimalzahlen sein (Spezifikation). Ein Exponent mit höchstens zwei Ziffern wird geduldet. Alles andere, etwa `nan`, `inf`, `1e-320`, `0x10` oder `1_000`, ist ein Kopfzeilenfehler. Damit bleiben alle abgeleiteten Werte endlich.
- Eine Datensatzdauer von 0 ist nur bei reinen Annotationsdateien zulässig.
- `nan`/`inf` in toml und Regelpaketen sind Fehler mit Feldangabe (Exit 2), ebenso Ganzzahlen außerhalb des darstellbaren Bereichs: Zahlen-Parameter müssen als Gleitkommazahl endlich sein, Ganzzahl-Parameter höchstens 2^53 betragen, `seed` liegt zwischen 0 und 2^63−1.
- Abtastraten werden exakt aus den ASCII-Feldern berechnet (550 Samples je 1,1 s = 500 Hz).
- Fehlt die Rate trotz EEG-Kanälen, lautet der Grund `signal.rate_unknown`.
- Erreicht trotzdem ein nicht-endlicher Messwert den Regelmotor, wird der Befund not_checkable (`value.non_finite`) mit Messwert null.

**A-76 Datenmodell und Phasenplan.**
- **Datenmodell:** Die Adapter liefern das Datenmodell `Recording` mit `Channel` (ARC-01, A-24). Kanäle tragen zusätzlich ihre eigene Abtastrate (EDF erlaubt eine Rate je Signal). `Recording.sampling_rate_hz` ist die niedrigste EEG-Rate. Die Abbildungstabelle PRD → Englisch steht in `docs/en|zh/data-model.md` (D-03).
- **Phasenplan, korrigierte Zuordnungen:**
  - RP-05 schließt in P4 ab (Auswertung halbautomatischer Nachweise nach A-15).
  - ARC-01 schließt in P6 ab (Zulieferer NeuroVault).
  - TECH-01 schließt in P12 ab (§13-Struktur vollständig erst nach P7/P9).
- **Befunde:** Jeder Befund trägt die wirksamen Schwellen mit Herkunft (`params`, A-13). In results.json heißen die Einstellungen `config.effective_settings`; dazu kommt `config.sampling` (KONZEPT 2.3).
- **Bericht:**
  - Befunde aus Platzhalter-Paketen stehen in einem eigenen Abschnitt „nicht bewertet“, mit dem Klauseltext aus A-41. Auch ihre bestandenen Prüfungen zählen nicht mit.
  - Ein hinterlegter Nachweis erscheint mit dem Wortlaut aus A-15. Der Dokumentverweis folgt mit dem Nachweisblock in P4.
  - Strukturierte Messwerte erscheinen mit übersetzten Beschriftungen statt als JSON.
- **Ausnahmen:** Ausnahmen greifen auch über den angezeigten Dateinamen (z. B. `rec-2c710f52.cnt`, A-70).
- **Rückverfolgbarkeit (TECH-12):** `tools/check_commit_ids.py` prüft jeden datierten Fortschrittseintrag außer denen der Planungsphasen 0–2 und kann eine Commit-Nachricht vor dem Commit prüfen (`--message-file`).

## Annahmen aus der Umsetzung von P2

**A-77 Formate, Metadaten, Validator und Konvertierung (Stand nach dem Review von P2).**
- **Verweise in Dateien (A-52):** NeuroGrid öffnet nur Dateien, deren Verweis ein einfacher Dateiname neben der verweisenden Datei ist, kein Link. Verweise mit Ordnern, absolute, UNC- oder `..`-Pfade gelten als unsicher (M01-03 `companion.unsafe_reference`). Sie werden nie geöffnet, auch nicht über MNE: Die Leseprüfung meldet dann `UnsafePathError` (M01-01), und `convert` wandelt die Aufnahme nicht um.
  - BrainVision:
    - Der Kopf wird mit der Grammatik von MNE gelesen: configparser ohne Interpolation auf dem Text vor `[Comment]`, Schlüssel ohne Groß-/Kleinschreibung, `=` und `:` als Trenner, der Abschnitt „Common Infos“ mit Rückfall auf „Common infos“. Doppelte Schlüssel behalten den letzten Wert; bis zu 100 Zeilen ohne Schlüssel werden übersprungen.
    - `DataFile` und `MarkerFile` werden zusätzlich genau so gelesen, wie MNE sie liest (Kodierung nach `Codepage`). Beide Lesarten gehen durch die Pfadprüfung.
    - MNE wird für die Leseprüfung nur aufgerufen, wenn beide Verweise eine vorhandene Datei neben dem Kopf nennen. Sonst lautet das Ergebnis `UnsafePathError`, `FileNotFoundError` oder `HeaderUnreadable`. Fehlt die Markerdatei, schlägt M01-01 also fehl.
  - FIF: Die Kette der Split-Teile wird vor jedem Lesen mit den Funktionen von MNE verfolgt. Jeder Teil muss ein einfacher Dateiname im selben Ordner sein, ohne Link. Eine Kette, die zu einem früheren Teil zurückführt, oder eine mit mehr als 1000 Teilen gilt als unsicher. Dann liest `read()` nur die Messinformation der Datei selbst, und die Dauer bleibt unbekannt.
  - EEGLAB:
    - `EEG.data` muss ein einfacher Dateiname sein.
    - Jede `.set`, die HDF5 öffnen kann (MAT v7.3), wird vor dem Lesen vollständig durchgegangen; dabei werden nur harte Links aufgelöst. Externe Links, externe Speicherung und virtuelle Datensätze ergeben `header.external_reference`. Weiche Links, Zyklen und unbekannte Objekte ergeben `header.unreadable_container`. In beiden Fällen gilt M01-01/M01-02, und MNE wird nicht aufgerufen.
    - Strukturen, bei denen MNE oder MNE-BIDS eine andere Struktur lesen würde als die geprüfte, werden ebenfalls als `header.unreadable_container` abgelehnt: verschachteltes `EEG.EEG`, `EEG` neben einer Variablen `data` auf oberster Ebene und in v7.3 `EEG` oder `EEG.data` in einer Zelle. EEGLAB schreibt keine davon.
  - Discovery: Links und versteckte Dateien werden aussortiert, bevor nach Begleitdateien gesucht wird; nur reguläre Dateien werden geöffnet. Ein Kopf kann nur Dateien als Begleitdatei beanspruchen, die weder Aufnahme noch Datendatei eines anderen Formats sind (`.eeg` und `.fdt` immer).
  - Die Zuordnungsvorlage wird nie über einen Link geschrieben. Geschrieben wird über eine temporäre Datei, die dann die Vorlage ersetzt. Ist das nicht möglich, endet der Lauf mit `errors.convert.mapping_missing_unwritable` (Exit 2). Dateinamen stehen TOML-sicher darin: Steuerzeichen und DEL als `\uXXXX`.
- **Größen und Eingaben (A-53):**
  - EEGLAB:
    - Die Grenze von 4 GB gilt für die Datei, für die deklarierten Größen der HDF5-Datensätze und für die entpackte Größe komprimierter MAT-v5-Variablen; mehr ergibt `header.too_large`.
    - Geladen werden nur die Kopffelder, die NeuroGrid nutzt; eingebettete Messwerte liest NeuroGrid selbst nicht.
    - Höchstens 4096 Standardkanäle.
  - BrainVision: Mehr als 100 Zeilen ohne Schlüssel vor `[Comment]`, ein Schlüssel mit mehr als 64 Leerraumzeichen in Folge (in der Lesart von NeuroGrid oder von MNE) und `Codepage=punycode` machen den Kopf unlesbar (`header.unreadable`); MNE wird dann nicht aufgerufen. Grund: configparser, ältere CPython-Versionen und punycode brauchen dafür quadratische Zeit. Impedanzzeilen werden am ersten Doppelpunkt geteilt. Der Kopf darf höchstens 2 MB groß sein.
  - Die Suche nach Namen in Freitext (A-51) begrenzt jeden Namensteil auf 40 und die Trennzeichen auf 8 Zeichen; die Laufzeit ist damit linear.
  - Ein Zahlenwert im Sidecar, der nicht in eine Gleitkommazahl passt, gilt als keine Zahl und führt nie zum Absturz.
  - Muster in `[convert] pattern`:
    - Abgelehnt werden mit `config.unsafe_pattern` (Exit 2) Rückverweise, bedingte Gruppen sowie Wiederholungen oder Alternativen in einem Teil, der sich selbst wiederholt.
    - Nicht erkannt werden nebeneinanderliegende, überlappende Wiederholungen. Sie können einen Lauf sehr lange dauern lassen; das betrifft nur die Verfügbarkeit, und Strg+C beendet den Lauf. Die Entscheidung darüber ist offen (A-78).
- **Adapter:**
  - BrainVision:
    - Kodierung des Kopfes für die eigenen Angaben: UTF-8, wenn gültig; sonst GBK, wenn der Kopf Folgen von Nicht-ASCII-Bytes enthält, wie chinesischer Text sie hat; sonst Latin-1 (westlicher ANSI-Kopf, z. B. „µV“).
    - Die Größe der Datendatei wird gegen Kanalzahl × Bytes je Wert geprüft.
    - Impedanzen kommen aus dem letzten Impedanzblock im Kommentar (kΩ). Der Block endet an der ersten Zeile, die nicht „Kanal: Wert“ für einen Kanal des Kopfes oder für Ref/Gnd ist; „Out of Range“ zählt als nicht dokumentiert. Alles andere im Kommentar wird nur auf Kennungen geprüft (A-51).
  - EEGLAB:
    - Gelesen mit pymatreader (MAT v5 und v7.3).
    - nbchan, pnts und trials müssen positive ganze Zahlen sein; sonst gibt es nur `header.number_field` und keine Größen- oder Formprüfung.
    - Die Form eingebetteter Daten wird ohne Achsen der Länge 1 verglichen, damit ein Datensatz mit einem Kanal, einer Epoche oder einem Wert gültig ist.
    - Fehlen Kanalorte ganz oder teilweise, heißen die fehlenden Kanäle wie bei MNE „EEG 000“, „EEG 001“ usw. (Typ EEG, µV).
    - Die Abtastrate der Aufnahme ist `srate`. Eingebettete Daten gelten als nicht streambar; der Bericht weist das aus (R14).
    - `subject`, `filepath`, `comments`, `history` und `setname` sind nur Hinweise; leere MATLAB-Texte zählen nicht als Kennung. Epochierte Datensätze liest MNE als Epochen.
  - FIF:
    - Kanaltypen einschließlich MEG, Positionen aus `loc`, Netzfrequenz aus `line_freq`.
    - `subject_info`, `experimenter` und `meas_date` sind Hinweise. Nach `raw.anonymize()` gelten die Platzhalter von MNE („mne_anonymize“, his_id „0“, verschobenes Geburts- und Messdatum) nicht als Kennung.
  - EDF+D wird wie eine fortlaufende Datei gelesen und als diskontinuierlich markiert (A-12); die Zeitstruktur zählt erst ab P3.
  - Nicht unterstützte Formate (M01-04 `format.unsupported`, verglichen ohne Groß-/Kleinschreibung):
    - `.cnt`, `.mff`, `.xdf`, `.xdfz`, `.fif.gz`, `.gdf`, `.nwb`, `.cdt`, `.dap`, `.mefd`, `.nxe`, `.ahdr`, `.lay`, `.nedf`, `.easy`, `.trc`, `.e`, `.ns1`–`.ns6`, `.nev` und `.ncs`.
    - Allgemeine Endungen wie `.dat`, `.txt`, `.bin`, `.mat` und `.gz` sowie Begleitdateien zählen als sonstige Dateien.
    - Eine FieldTrip-Layoutdatei `.lay` wird wie ein Persyst-Kopf gemeldet.
  - Begleitdateien ohne Hauptdatei (`.eeg`, `.fdt`) ergeben M01-04 mit dem Grund „verwaiste Begleitdatei“; `convert` nennt denselben Grund. `scan` führt sie in einer eigenen Liste (`orphans`, Konsole „nicht zuordenbare Datendateien“) und zählt sie nicht als nicht unterstützte Formate.
  - Dateien nur mit Annotationskanälen (z. B. Hypnogramme) sind lesbar, zählen aber nicht als Aufnahme; M02–M05 sind dort nicht anwendbar.
- **Kanaltypen (A-18, A-04):**
  - Der Typ wird am Label ohne vorangestelltes „EEG“ bestimmt. EOG, ECG/EKG und EMG zählen an beliebiger Stelle (VEOG, HEOG, „EEG EKG1-REF“).
  - Als erstes Wort gelten LOC, ROC, LUC, RUC, LLC und RLC sowie die AASM-Ableitungen E1/E2 gegen M1/M2/A1/A2 als EOG. HEO und VEO (Neuroscan) gelten als EOG.
  - Atemkanäle gelten als RESP. Sättigung, Puls, Pleth/PPG, GSR/EDA, ERG, Temperatur, Schnarchen, Licht, Photic, Lage sowie Ereignis- und Markersignale gelten als MISC. LEG und CHIN gelten als EMG, STATUS/TRIG/STI als TRIG.
  - Alles andere bleibt EEG (die Liste ist nicht vollständig, z. B. BioSemi EXG1–8). Kein 10-20/10-10/10-05-Name ist betroffen.
  - In BIDS gewinnt jeder angegebene Typ in `channels.tsv` gegen das Label. Bekannte Typen werden übernommen; MEG-Typen werden zu MEG, alle übrigen (GSR, PPG, TEMP, …) zu MISC. Annotationskanäle werden nie umgetypt.
- **Metadaten (A-03, A-04):**
  - Die Entitäten in BIDS-Dateinamen liest MNE-BIDS (LIB-02); Namen mit Entitäten, die BIDS nicht kennt, mit doppelten Entitäten oder mit Werten, die nicht nur aus Buchstaben und Ziffern bestehen, gelten nicht als BIDS-Namen.
  - Der Sidecar hat dasselbe Suffix wie die Datendatei und folgt dem Vererbungsprinzip. `channels.tsv` und `electrodes.tsv` werden in der nächstgelegenen Datei gesucht; bei `electrodes.tsv` spielt `space` keine Rolle. Eine `channels.tsv` ohne Zeilen ist keine Quelle (auch nicht für M04-04).
  - Die Spalten name/type/units:
    - `channels.tsv` ist die Quelle, wenn jeder Kanal außer den Annotationskanälen dort eine Zeile mit Wert hat; `n/a` zählt als Wert.
    - Sonst ist eine Spalte dokumentiert, wenn jeder Kanal den Wert in seiner Zeile oder im Kopf hat.
  - Prüfungen in M02-02:
    - TaskName wird mit dem task-Label nur über Buchstaben und Ziffern und ohne Groß-/Kleinschreibung verglichen.
    - BIDSVersion muss die Form `x.y.z` haben.
    - Name gilt als leer, wenn er leer ist oder `n/a` lautet.
  - `ManufacturersModelName` mit `n/a` dokumentiert kein Gerät.
  - Rohordner:
    - Die Zuordnung kommt aus `[[convert.files]]` (hat Vorrang) oder `[convert] pattern` (benannte Gruppen subject, session, task, run; subject und task Pflicht).
    - Nennt eine Gruppe einen Wert, der nicht nur aus Buchstaben und Ziffern besteht, oder ist run keine Zahl, gilt die Datei als nicht zugeordnet. Abgeglichen wird mit dem relativen Pfad oder dem Dateinamen.
    - `scan` zählt die Probanden aus der Zuordnung in `.neurogrid/neurogrid.toml`, wenn jede Aufnahme außer reinen Annotationsdateien zugeordnet ist (A-72); sonst bleibt „unbekannt“.
  - Ob Elektroden nass oder trocken sind, steht nur in `neurogrid.toml` (`metadata.defaults.electrode_type`). Ohne Angabe ist M05-02 nicht prüfbar. Bei trockenen Elektroden ist M05-02 nicht anwendbar, weil die Schwelle der PRD für nasse gilt.
- **M04:**
  - Kanalnamen werden ohne vorangestelltes „EEG“ und ohne Referenz-Endung (REF, AVG, AR, LE, RE, Cz) verglichen. Bipolare oder referenzielle Ableitungen gelten als Standard, wenn beide Teile Standardnamen sind.
  - Die Namenslisten stammen aus den MNE-Montagen standard_1020 und standard_1005 (`tools/gen_montage_names.py --check`). `[metadata.channel_map]` bildet eigene Namen ab.
  - M04-04 vergleicht die EEG-Kanalzahl in Sidecar, `channels.tsv` und Datei sowie die Gesamtzahl in `channels.tsv` und Datei (ohne Annotationskanäle).
  - Der Titel von M04-05 nennt die geprüfte Eigenschaft („Kanalname innerhalb 10-20/10-10“), damit „nicht bestanden“ richtig gelesen wird.
- **Validator (A-06, A-09, A-14):**
  - **Befunde:**
    - Je Regel, Objekt und Validator-Code entsteht ein Befund; der Unterschlüssel ist der Code.
    - Die Details nennen die Gesamtzahl und die Anzahl je Unter-Code (z. B. Feldname); der Bericht nennt die Unter-Codes nach dem Text („Betrifft: …“, höchstens 100).
    - Eine Ausnahme auf einen Code deckt alle Unter-Codes ab.
  - **Zuordnung:**
    - Eine Meldung gehört zur Aufnahme, deren Datei sie nennt, oder zu deren Begleitdatei (`.eeg`/`.vmrk`, `.fdt`). Andere Dateien, etwa Sidecars, behalten ihren Ort.
    - Meldungen an oder unter einem Link, dem Discovery nicht gefolgt ist, werden verworfen; der Hinweis auf nicht verfolgte Links deckt sie ab.
    - Eine einzelne Datei als Ziel wird nicht validiert (BIDS-STO-001 bis -003 nicht anwendbar).
  - **Texte und HED:**
    - Die eigenen Texte stehen in `report/validator_codes.yaml`, ein Satz je Code in zh/en/de, für alle Codes des gebündelten Validators.
    - HED-Schemas, die der Validator nicht mitbringt, ergeben offline `HED_ERROR` mit Unter-Code `SCHEMA_LOAD_FAILED` und damit BIDS-STO-003.
  - **Warnungen:** Synthetische BIDS-Testdaten brauchen alle empfohlenen Felder, um ohne Warnung zu bleiben. Echte Datensätze haben fast immer Warnungen (BIDS-STO-002); das gibt den Validator wieder.
  - **Arbeitsordner:** Lässt er sich neben der Ausgabe nicht anlegen, endet der Lauf wie bei einer nicht schreibbaren Ausgabe (Exit 2, A-54).
- **Konvertierung (A-05):**
  - **Eingang und Ausgabe:**
    - Eingang ist nur ein Rohordner (ein BIDS-Eingang ergibt Exit 2).
    - Die Ausgabe muss ein leerer oder neuer Ordner außerhalb des Eingangs sein; eine Datei an ihrer Stelle und Pfade mit Komma werden abgelehnt, bevor etwas geschrieben wird.
    - Fehlt eine Zuordnung, wird die Vorlage geschrieben (Exit 2).
    - Ziele werden ohne Groß-/Kleinschreibung verglichen (`duplicate_target`). Subjekt- oder Sitzungs-Labels, die sich nur darin unterscheiden, werden abgelehnt (`label_case`, Exit 2), weil sie unter Windows und macOS im selben Ordner landen.
  - **Was umgewandelt wird:**
    - Nur Aufnahmen ohne Begleitdatei-Problem (M01-03) und ohne Kopfproblem, das die Daten betrifft (M01-02). Kopfprobleme nur in Textfeldern (Nicht-ASCII, Startdatum, Ablehnung durch edfio) halten nicht auf.
    - Nicht umgewandelt werden: epochierte EEGLAB-Datensätze, weil EEG-BIDS fortlaufende Daten erwartet; Aufnahmen ohne EEG-Kanal (`convert.no_eeg_channels`); reine Annotationsdateien, die gelesen, aber nicht zugeordnet werden müssen.
    - Jede nicht umgewandelte Datei steht mit Grund auf der Konsole.
  - **Fehler bei einer Aufnahme:** Er bricht den Lauf nie ab. Die Ausgabe wird auf den Stand vor dieser Aufnahme zurückgesetzt: neue Dateien entfernt, geänderte TSV- und JSON-Dateien auf Datensatz- und Probandenebene wiederhergestellt. Die Aufnahme steht als `convert.failed` (Exit 1) auf der Konsole.
  - **Formate:**
    - EDF/BDF (einschließlich EDF+D) übernimmt MNE-BIDS als Dateikopie. Kann MNE-BIDS die Datei unter ihrem Namen oder Pfad nicht finden (mehrere Punkte, Großbuchstaben in der Endung, `.eeg`/`.fdt`/`.dat` im Pfad, `.ds` im Ordnernamen), wird sie zuerst als `recording.<ext>` in den Arbeitsordner verlinkt oder kopiert.
    - Hat erst der Pfad des Arbeitsordners selbst ein solches Merkmal, wird eine fortlaufende EDF/BDF als BrainVision geschrieben. Ein EDF+D wird dann als `convert.failed` gelistet.
    - BrainVision und EEGLAB werden kopiert, wenn MNE-BIDS sie finden kann. Sonst, und bei MAT v7.3 und eingebetteten Daten, werden sie aus den gelesenen Daten als BrainVision geschrieben.
    - FIF wird nur mit EEG- und Begleitkanälen nach BrainVision geschrieben.
    - Elektrodenpositionen aus EEGLAB und aus BrainVision-`[Coordinates]` werden nicht übernommen (möglicherweise Vorlagepositionen).
  - **Sidecars und `channels.tsv`:**
    - Nicht dokumentierte Pflichtfelder werden als `n/a` geschrieben und gelistet. Für EEGReference und PowerLineFrequency meldet `check` sie danach (M02-01). Für SoftwareFilters ist `n/a` nach BIDS gültig; die Konsole sagt, dass `check` es nicht meldet.
    - Ohne `[dataset] name` ist auch der Name `n/a` (M02-02). Autoren werden nicht erfunden. `Manufacturer`, das MNE-BIDS nur aus dem Dateiformat ableitet, wird weggelassen.
    - In `channels.tsv` einer kopierten EDF/BDF bekommt jeder Kanal die Abtastrate und Einheit seines eigenen Signals; Einheiten werden bis zum ersten NUL-Byte gelesen, als UTF-8 oder sonst Latin-1. Filtergrenzen stehen dort nur, wenn das Vorfilterfeld des Kanals sie nennt, sonst `n/a`.
  - **`--strip-identifying-headers`:**
    - EDF/BDF: Patienten- und Aufnahmefeld werden durch die Platzhalter der EDF+-Spezifikation ersetzt, das Startdatum durch 01.01.85.
    - BrainVision: Bearbeitet werden die Bytes. Aus dem Kommentar bleibt nur der Impedanzblock, die Ziffern des Datums im Marker „New Segment“ werden genullt, sonst wird nichts umkodiert.
    - Vor dem Schreiben entfernt MNE Messdatum, `subject_info`, `experimenter` und `description`; EEGLAB-Eingang wird dann als BrainVision geschrieben.
  - **Verarbeitungsschritte (DM-07):** `input_hash` und `output_hash` sind SHA-256 über die sortierten Zeilen „Dateiname, Tab, SHA-256“ aller Dateien der Aufnahme (Kopf, Daten-, Markerdatei, `.fdt`, FIF-Teile).
  - **Exitcodes:** 0, wenn mindestens eine und jede Aufnahme umgewandelt ist und der Validator keinen Fehler meldet. 1 bei nicht umgewandelten Dateien oder Validator-Fehlern; ist gar nichts umgewandelt, bleibt keine Ausgabe stehen. 2 bei Werkzeugfehlern.
  - **Abbruch** (Werkzeugfehler, Validator-Fehler, Strg+C mit Exit 130): Eine neu angelegte Ausgabe wird entfernt; ein Ausgabeordner, der vorher leer war, wird wieder geleert.
- **Umgebung in results.json (A-11, A-48):** Neben den bisherigen Bibliotheken stehen dort bids-validator-deno, deno, h5py und pymatreader.
- **Offline-Nachweis des Validators (NG-N01, A-49):** Der CI-Job `offline-strace` (Linux) führt `check` mit dem Paket `bids` und `convert` unter `strace -e trace=connect` aus und schlägt bei jedem `connect` mit AF_INET/AF_INET6 fehl. Er läuft erst nach einem Push (D-09).
- **Testkorpus (E4, LIB-09):** `tools/corpus.py` lädt die sechs Datensätze über die OpenNeuro-API und PhysioNet und prüft sie offline gegen `tools/corpus_lock.json`. Für OpenNeuro gibt es keine veröffentlichten Prüfsummen; sie wurden beim ersten Laden zusammen mit dem Snapshot-Commit festgehalten. Lizenzen und Zitate stehen in `DATA_SOURCES.md`.


**A-78 Phasenplan, Bibliotheken und offene Restpunkte aus P2.**
- **Phasenplan:** LIB-01 (MNE: Einlesen, Filter, ICA) schließt in P3 ab, weil Filter und ICA erst mit M06/M09 genutzt werden; P2 trägt das Einlesen bei.
- **LIB-02 (MNE-BIDS lesen und schreiben):**
  - Geschrieben wird mit `write_raw_bids`.
  - Gelesen werden die Entitäten der Dateinamen mit `get_entities_from_fname`.
  - Die Werte der Sidecars liest NeuroGrid selbst, weil jede Angabe ihre Herkunft behalten muss (A-04) und weil `read_raw_bids` bei inkonsistenten Datensätzen abbricht, die M04-04 gerade melden soll (z. B. abweichende Kanalzahl).
- **Offene Restpunkte** (bekannte Grenzen, keine Datendefekte; Entscheidung des Projektverantwortlichen bei STOPP G1):
  1. Muster in `[convert] pattern` mit nebeneinanderliegenden, überlappenden Wiederholungen werden nicht erkannt und können einen Lauf sehr lange dauern lassen (nur Verfügbarkeit; Strg+C beendet den Lauf).
     Möglichkeiten:
     - eine Engine mit linearer Laufzeit (neue Abhängigkeit, z. B. google-re2),
     - eine eingeschränkte Mustersyntax,
     - die Grenze akzeptieren.
  2. MAT-v5-Zellen und -Strukturen mit sehr großen deklarierten Dimensionen belegen beim Laden viel Speicher (gemessen: 2 kB Datei → rund 470 MB). Die Grenze von 4 GB zählt dort nur entpackte Bytes, keine Elemente. Schließen würde das ein eigener Elementlauf über MAT v5.
  3. Sonderdateien wie FIFOs (Linux, z. B. aus Archiven) werden von Discovery und beim Verfolgen von FIF-Teilen nicht ausgeschlossen; Lesen kann dann blockieren.
  4. Kanaltypen nach Label sind nicht vollständig (z. B. BioSemi EXG1–8 bleiben EEG). Eine Tabelle `[metadata.channel_types]` in `neurogrid.toml` für Rohordner wäre möglich, geht aber über die PRD hinaus und ist deshalb nicht umgesetzt.

## Annahmen aus der Umsetzung von P3

**A-79 Signalqualität M06–M09 (P3; präzisiert A-18, A-19, A-21, A-60).**
- **Lesen:**
  - EDF/BDF: eigener Leser über ein Speicherabbild der Datensätze. Er liefert Digitalwerte (für M08 an den Grenzen des Messbereichs) und jeden Kanal in seiner nativen Rate. Gelesen werden nur vollständige Datensätze.
  - EDF+D/BDF+D: Die Zeiten kommen aus dem ersten TAL jedes Datensatzes. KONZEPT 1.5 nannte dafür edfio; edfio liest aber kein BDF.
  - BrainVision, EEGLAB und FIF: über MNE mit `preload=False`, in 60-s-Blöcken.
  - Mehrfach vergebene Kanalnamen werden wie bei MNE eindeutig gemacht (`Fp1-0`, `Fp1-1`). Die Werte stehen unter diesen Namen.
- **Stream:** Die Kanäle eines Blocks werden in min(4, Kerne) Threads gerechnet (KONZEPT 1.5). Jeder Kanal bleibt in einem Thread, die Werte hängen nicht von der Thread-Zahl ab.
- **M07** (A-18, A-47): Rechenweg wie in KONZEPT 1.5. Der Kanalwert ist der Median der Blockwerte.
  - not_applicable bei fs < 2·(f₀+1).
  - not_checkable, wenn die Aufnahme kürzer als ein 2-s-Segment ist (`quality.too_short`) oder der Kanal zwischen 1 und 40 Hz keine Leistung hat (`quality.no_signal_power`). Ein konstanter Abschnitt zählt als leistungslos, denn sein Mittelwert ist in Gleitkomma nicht immer exakt.
  - Liegt das Band der anderen Netzfrequenz über Nyquist, wird es nicht gemessen.
  - **CORE-M07-02** (info, Annahme) prüft die Plausibilität der dokumentierten Netzfrequenz. Der Hinweis erscheint, wenn der Median der Kanalverhältnisse bei der anderen Netzfrequenz mehr als `min_factor` = 2,0 mal so hoch ist.
    - Ist das andere Band nicht messbar: not_checkable (`quality.rate_below_other_band`).
    - Ist kein Kanal messbar: der gemeinsame Grund der Kanäle.
- **M08** (A-18):
  - Toleranzen stehen in `[quality]`: `flat_tolerance_uv` 0,1 µV, `plateau_samples` 10.
  - Ein 1-s-Fenster braucht mindestens 2 Werte. Darunter ist M08 not_checkable (`quality.window_too_few_samples`): Ein einzelner Wert ergäbe immer „flach“.
  - Zeitbereiche benachbarter Fenster werden zusammengefasst. Je Kanal stehen höchstens 100 Bereiche im Befund, dazu die Gesamtzahl.
  - Bekannte Grenze: Das kanonische JSON rundet Zahlen auf 6 signifikante Stellen (A-61). Zeitangaben sind deshalb ab 10⁵ s (27,8 h) nur noch auf 1 s genau.
- **Unbrauchbare Werte** (A-75): Fenster und Welch-Segmente mit nicht endlichen Werten oder Werten jenseits von ±10¹⁰⁰ µV (beschädigte Datei) werden nicht beurteilt, sondern als `unusable_windows` gezählt. Ein Kanal ohne beurteilbare Werte ergibt not_checkable `quality.unusable_samples`. Eine nicht endliche Netzfrequenz im Dateikopf gilt als nicht dokumentiert; es gilt dann 50 Hz.
- **Signal-Hash `NG-SIGHASH-v1`** (A-21):
  - Je Kanal SHA-256 über die int64-Werte von rint(µV·10), kombiniert mit der Rate.
  - Werte jenseits von ±2⁶² werden begrenzt; nicht endliche Werte gehen als int64-Minimum ein.
  - Der Hash dient M12 (P4) und wird nicht ausgegeben.
- **Stichprobe** (A-19): Der Ausweis steht in results.json (`recordings[].sample`) und im Bericht (Abschnitt 4). Er nennt Modus, Abschnitte in Aufnahmezeit, Seed, ausgewertete Kanäle, Positionsquelle, ausgelassene Kanäle, Notch, Band, 250 Hz und die Epochenlänge. Die Bibliotheken (pyprep, autoreject, picard) erhalten `seed mod 2³²`, denn NumPy nimmt keine größeren Seeds; A-75 lässt Seeds bis 2⁶³−1 zu.
- **Montage-Quelle** (präzisiert A-60): Je Aufnahme gilt die erste Quelle, die Positionen für alle EEG-Kanäle oder für mindestens `min_channels` liefert. Alle Quellen stehen im Kopfkoordinatensystem von MNE.
  1. `electrodes.tsv`, nur zusammen mit der `coordsystem.json` desselben `space`:
     - Die Einheit muss m, cm oder mm sein.
     - Das System muss eine bekannte Ausrichtung haben. RAS-Systeme (CapTrak, ElektaNeuromag, ChietiItab) werden direkt übernommen. ALS-Systeme (CTF, 4DBti, KitYokogawa, EEGLAB, EEGLAB-HJ) werden nach RAS gedreht.
     - Vorlage-Räume und „Other“ werden nicht verwendet.
     - Von mehreren Dateien gilt die erste brauchbare der tiefsten Ebene. Ist keine brauchbar, steht der Grund im Ausweis (`positions_unused`).
  2. Positionen aus der Datei, wie MNE sie im Kopfkoordinatensystem liest (FIF, EEGLAB, BrainVision).
  3. Standardmontage colin27 (10-05) über die Standardnamen aus M04 und `channel_map`. Die Vorlage ist im MRI-System gespeichert und wird wie bei `raw.set_montage` ins Kopfkoordinatensystem überführt.
  4. Keine Positionen.
  - Haben nur einige Kanäle Positionen, aber mindestens `min_channels`, werden nur diese Kanäle ausgewertet. Die übrigen stehen im Ausweis (z. B. BioSemi EXG1–8).
- **M06** (A-19):
  - Die Kriterien laufen in der Reihenfolge von pyprep `find_all_bads`, RANSAC zuletzt.
  - RANSAC läuft nur mit Positionen und nur, wenn die Vorbedingungen von pyprep erfüllt sind: mindestens 14 nutzbare Kanäle und genug gute Kanäle nach den übrigen Kriterien. Sonst wird RANSAC übersprungen (`ransac_skipped`). Vorher brach M06 in diesem Fall ganz ab.
  - Bricht M06 ab, sind die schlechten Kanäle unbekannt. M09a und M09b brauchen die Durchschnittsreferenz ohne sie und sind dann not_checkable (`quality.bad_channels_unknown`).
- **Vorbedingungen** (präzisiert A-60):
  - Für M06, M09a und M09b gelten ≥ 60 s Daten, ≥ 200 Hz (für das Band 1–100 Hz) und ≥ `min_channels` EEG-Kanäle (16, `[quality]`). A-60 sah die Kanalzahl nur für M09b vor. Gemessen: Bei 3 bipolaren PSG-Kanälen markierte pyprep alle als schlecht (M06 = 1,0).
  - autoreject braucht Positionen auch ohne Interpolation. Ohne Positionen ist M09a deshalb not_checkable (`quality.no_positions`); A-60 sah „ohne Interpolation“ vor.
  - Bricht ein Verfahren oder die Vorbereitung der Stichprobe ab, ergibt das not_checkable `quality.method_failed` mit dem Typ der Ausnahme. Die Stream-Werte bleiben erhalten.
- **ICLabel** läuft über onnxruntime. Vorher wird `onnxruntime.disable_telemetry_events()` aufgerufen (KONZEPT 3, NG-N01, CON-04).
- **Determinismus** (A-11, NG-N03):
  - Gerechnet wird stets mit einem BLAS-Thread (threadpoolctl); `environment.blas_threads` ist 1.
  - `--jobs N` verteilt die Aufnahmen und ihre Arbeitsschritte auf N Prozesse (D-14), jeder mit Netzwerkschutz:
    - Je Aufnahme laufen Stream und Vorbereitung der Stichprobe mit M06 nebeneinander, danach autoreject und ICA.
    - Höchstens N Aufnahmen sind gleichzeitig in Arbeit, also höchstens N vorbereitete Stichproben im Speicher (bei 256 Kanälen je etwa 0,3 GB).
    - autoreject verteilt seine Schwellensuche bei einer einzelnen Aufnahme ab 64 Kanälen auf `--jobs − 1` loky-Prozesse; darunter kostet ihr Start mehr, als er spart.
      - Diese Prozesse starten wie die übrigen: Netzwerkschutz, ein BLAS-Thread, keine Bibliothekswarnungen, Daten ohne Zwischendateien.
      - Stirbt einer, rechnet autoreject im eigenen Prozess neu; das Ergebnis ist dasselbe.
      - Bekannte Grenze: Der Hilfsprozess „resource tracker“ von loky führt keinen NeuroGrid-Code aus und hat keinen Netzwerkschutz. Stirbt ein Pool-Prozess, kann er Warnungen ausgeben und bis etwa 35 s weiterlaufen.
    - Die Teile werden nach festen Regeln zusammengesetzt; das Ergebnis ist byte-gleich zu `--jobs 1`.
    - autoreject und ICA geben keine Ausnahme weiter. Ein Fehler außerhalb ihrer eigenen Schritte ergibt `quality.method_failed`; die Stream-Werte und M06 bleiben erhalten.
    - Kommt das Ergebnis eines Teils nicht an (z. B. `MemoryError` beim Übertragen der Stichprobe), wird die Aufnahme einzeln wiederholt.
  - Unter Windows nutzt der Pool höchstens 61 Prozesse (Grenze von ProcessPoolExecutor), auch wenn `--jobs` bis 64 erlaubt.
  - Stirbt ein Prozess, nimmt der Pool keine Arbeit mehr an. Aufnahmen ohne Ergebnis laufen dann einzeln in einem eigenen Prozess. Stirbt auch der, ergibt das not_checkable `quality.worker_failed`.
- **Kalibrierung** (A-20, MET-01):
  - Grundlage ist das 95. Perzentil der gemessenen Werte über die fünf OpenNeuro-Datensätze des Korpus (22 Aufnahmen, 1050 Kanäle, 5 Formate).
  - PSG-IPA ist nicht dabei: Der Datensatz stammt von PhysioNet, A-20 legt OpenNeuro-Snapshots fest.
  - Das Protokoll liegt in `src/neurogrid/rulepacks/calibration/core.json`. `tools/calibrate.py --check` und ein Test prüfen, dass Protokoll, Regelpaket und die Standardwerte der Prüfungen übereinstimmen. Ein Korpus-Test rechnet die Perzentile nach.
- **Benchmark NG-N02** (A-50): `tools/gen_large_edf.py` erzeugt EEG-ähnliche Daten aus Dipolquellen, damit pyprep, autoreject und ICA realistisch viel Arbeit haben. Mit unstrukturierter Mischung galten 56–89 % der Kanäle als schlecht, und die Laufzeit wurde unterschätzt.
- **Abdeckung** (A-23): `neurogrid/quality/` gehört zur Gruppe „Prüfer“.
- **Lizenz-Gate** (A-56): pyprep 0.9.0 trägt im Metadatenfeld den vollen MIT-Text. Es steht deshalb als versionsgebundene, von Hand geprüfte Ausnahme in `licenses/exceptions.txt`.


## Annahmen aus der Umsetzung von P4

Die folgenden Annahmen schließen Lücken, die PRD, Konzept und frühere Annahmen offenlassen (Freigabemodus A). Sie
sind für STOPP G1 vorgemerkt.

**Übergreifend (gilt für A-80 bis A-83).**
- **results.json:** `schema_version` bleibt bis zur ersten Veröffentlichung „1.0“. Alle neuen Felder sind optional; results.json früherer Stände wird weiter gelesen und dargestellt.
- **Steuerdateien:**
  - Vom Nutzer geschriebene Konfiguration (`neurogrid.toml`, `.neurogrid/evidence.yaml`, `.neurogrid/splits.tsv`, `.neurogrid/provenance.yaml`) ergibt bei Fehlern Exit 2, mit Feld oder Zeile (ein Syntaxfehler der neurogrid.toml nur mit der Fehlerart, ohne Zeile) und ohne Zellinhalt.
  - Integritätsdateien (`manifest.json`, `.neurogrid/processing_steps.json`) ergeben in `check` einen Befund und erst in `verify`/`manifest` Exit 2.
  - Datensatzdaten (events.tsv, participants.tsv) ergeben nie Exit 2.
- **Freitext in Ausgaben** (präzisiert A-17, A-51): Codes, Klassenbezeichnungen und Annotator-IDs erscheinen nur, wenn sie im Vokabular stehen oder dem Muster aus A-17 folgen und nicht nach Personendaten aussehen (Name, lange Zahl, absoluter Pfad, Datum auch mit Monatsnamen oder Unterstrichen, freistehende Jahreszahl 1900–2099, Uhrzeit wie „22.31“, „22h31“ oder „10 pm“; eine Zahl mit einstelliger Vorkommastelle wie „0.25“ bleibt lesbar); sonst „Freitext (n Zeichen)“ mit dem Unterschlüssel `text-<sha8>`. Annotatoren heißen in Unterschlüsseln immer `ann-<sha8>`. Unterschlüssel hängen nicht von `--show-paths` ab (A-68).
- **Ampel** (präzisiert A-16):
  - Eine Phase ist grau, wenn keine ihrer Regeln ein Ergebnis „bestanden“, „verletzt“, „ausgenommen“ oder „Nachweis offen“ liefert.
  - Jedes Ergebnis einer Nachweisregel zählt als bewertet, auch ein begründetes not_applicable.
- **Wirksame Konfiguration:** In Rohordnern erscheinen Pfadwerte (`convert.files`, `convert.pattern`, `annotation.files`, `annotation.annotators`, `ai.splits`) ohne `--show-paths` nur pseudonym (A-51). Ausnahme: `ai.splits` bleibt lesbar, wenn es einer der festen Steuerdateinamen in `.neurogrid/` ist (z. B. `.neurogrid/splits.tsv`); ein selbst gewählter Name in `.neurogrid/` wird ebenfalls pseudonym. Eine Dateiendung erscheint neben einem Pseudonym nur, wenn NeuroGrid sie als Format- oder Steuerdateiendung kennt oder jeder Teil mit einem Buchstaben beginnt, kurz ist und nach der Freitextregel lesbar ist; Ziffernteile, Daten, Jahre und Uhrzeiten nie (eine Regel für Manifest, `verify`, Befunde, Bericht, Konsole und wirksame Konfiguration). In BIDS ohne `--show-paths` folgen `annotation.annotators` und `annotation.files[].annotator` der Freitextregel: Ein Muster bleibt lesbar, wenn jeder Wert lesbar wäre, den es mit einzeln gefüllten Platzhaltern ergibt (Füllungen: Leerzeichen, Buchstabe, Ziffer, die Datums- und Zeittrenner `.` `:` `-` `/` `h`, bei `*` auch nichts); sonst `pattern-<sha8>` bzw. `ann-<sha8>` (mehr als 3 Platzhalter oder andere Glob-Zeichen: immer pseudonym). Muster wie `*.<Endung>` und `rec-<sha8>.<Endung>` folgen der Endungsregel; sonst `pattern-<sha8>`. Der Konfigurations-Hash bleibt über die echte Konfiguration.
- **Konsole:** Jeder Hinweis der Stufe Warnung wird ausgegeben, mit bereinigten und gekürzten Parametern.
- **Reine Annotationsdateien** sind für M11/M12 keine Aufnahmen; ein zugeordnetes Hypnogramm gehört zu Proband und Split seiner Signalaufnahme.
- **Ohne Annotationen, Labels oder Splits:** je Regel ein datensatzweiter Befund not_applicable statt einer Zeile je Aufnahme (A-59). Ausnahme: Im kontinuierlichen Modus bewertet CORE-M10-03 jede Signalaufnahme einzeln, auch wenn der Datensatz keine Annotation enthält (Abdeckung 0).

**A-80 Annotation M10** (präzisiert A-17).
- **Quellen:** EDF+/BDF+-TAL (auch reine Annotationsdateien; MNE-Kanalverweise `@@Kanal` werden abgeschnitten), BrainVision `.vmrk`, EEGLAB-Ereignisse (MAT v5 und v7.3), FIF-Annotationen und BIDS `events.tsv` (UTF-8 mit oder ohne BOM).
  - In BIDS ersetzt eine zutreffende `events.tsv` die Annotationen der Datei.
  - Strukturmarken bleiben außen vor, je Format: EDF+-Zeitstempel, in vmrk jede Marke vom Typ „New Segment“, in EEGLAB „boundary“, in FIF „BAD_ACQ_SKIP“ und „EDGE boundary“; in events.tsv wird keine Zeile als Strukturmarke ausgelassen.
  - Zeitgrenzen (A-53): Beginn ≥ −10⁹ s, Ende ≤ 10⁹ s (rund 31,7 Jahre), alle Werte endlich. In events.tsv zählt eine Zeile außerhalb als ungültig (`notice.events_rows_invalid`); in EDF-TAL, vmrk, EEGLAB und FIF macht sie die Quelle unlesbar (`annotation.unreadable`). In EEGLAB wird ein Ereignis mit leerer oder NaN-Latenz nicht still verworfen, sondern als ungültig gezählt und im selben Hinweis gemeldet wie ungültige events.tsv-Zeilen (`notice.events_rows_invalid`, Stufe Info; ebenso FIF-Annotationen, die MNE verwirft, weil sie ganz außerhalb der Daten liegen); eine leere oder NaN-Dauer gilt als 0 (EEGLAB-Konvention für fehlende Dauer). Kein Leser verwirft eine Annotation ohne Spur: vmrk liest Markernummern beliebiger Länge und jeden Abschnitt „[Marker Infos]“ unabhängig von der Schreibweise.
  - „n/a“ gilt in events.tsv ohne Groß-/Kleinschreibung und nach Entfernen äußerer Leerzeichen als kein Wert, für M10 und M11 gleich (wie in participants.tsv).
  - Eine EDF-Kopfgröße unter 256 · (Signale + 1) macht Annotationen und Signal unlesbar (not_checkable), nie Exit 2; CORE-M01-02 meldet das Kopffeld.
- **Annotatoren:** Spalte `annotator` in events.tsv oder je Annotator eine Datei.
  - Reine Annotationsdateien werden über `[[annotation.files]]` (path und recording relativ zum Datensatz, annotator optional) oder über den gemeinsamen Dateinamensanfang zugeordnet.
  - `[annotation] annotators` grenzt mit Mustern (`*`, `?`, Groß-/Kleinschreibung beachtet) ein, welche Annotatoren zählen. Verglichen wird mit der Annotator-ID, nicht mit dem Dateinamen: Spalte `annotator`, `[[annotation.files]].annotator` oder der Rest des Dateinamens nach „<Aufnahmename>_“ (z. B. `night_scorer2.edf` → `scorer2`). Schließen die Muster alle aus, nennen die Befunde den Grund `annotation.all_excluded`.
  - Ein Pfad darf in `[[annotation.files]]` nur einmal stehen, nach Vereinheitlichung (`\` → `/`, `./` entfällt), auch bei gleichen Angaben (sonst Exit 2 mit dem Feld `annotation.files.<n>.path`, n = Position des Eintrags ab 0, nie mit dem Pfad).
  - Nicht zuordenbare oder mehrdeutige Dateien werden eigene Objekte und erhalten einen Hinweis.
- **Codes:** code = Spalte trial_type, falls vorhanden, sonst value; Bezeichnung aus den `Levels` der events.json.
  - Vokabular: toml vor `Levels`; exakter Vergleich; HED wird nicht genutzt.
  - Eine Bezeichnung mit verschiedenen Codes ist uneinheitlich.
- **κ (CORE-M10-01):** paarweises, ungewichtetes Cohens κ auf einem Raster ab t = 0 bis zum Aufnahmeende (Standard 30 s kontinuierlich, 1 s ereignisbasiert).
  - Belegung nach Epochenmitte, nur Annotationen mit Dauer > 0; „kein Ereignis“ ist eine Klasse.
  - Verglichen wird der **Mittelwert** mit `min_kappa` = 0,6; Minimum, Paare und das schwächste Paar stehen in den Details.
  - Ein Objekt mit einer unlesbaren Quelle ist ganz not_checkable (kein κ über eine Teilmenge).
  - Grenzen (A-53): höchstens 5 Mio. Epochen und höchstens 100 Annotatoren mit bewerteter Annotation (4950 Paare) je Objekt; darüber not_checkable (`annotation.too_many_epochs` bzw. `annotation.too_many_annotators`). κ wird je Objekt einmal berechnet, über Klassenabschnitte statt Epoche für Epoche, mit höchstens 25 Mio. gleichzeitig gehaltenen Klassenwerten; die Details nennen die schwächsten Paare und die Zahl aller Paare.
  - An κ, Lücken und Überlappungen nimmt ein Annotator nur teil, wenn er mindestens eine Annotation mit Dauer > 0 hat. Eine Spur nur aus Marken zählt für das Vokabular und für `[ai] labels = "annotations"`; gibt es nur Marken, nennen CORE-M10-01/04 den Grund `annotation.markers_only`, und CORE-M10-03 verletzt mit Abdeckung 0.
  - Eine zugeordnete reine Annotationsdatei ohne Annotation bleibt ein Annotator: Abdeckung 0, CORE-M10-03 verletzt.
- **Referenz PSG-IPA** (präzisiert die DoD von P4): die nachgerechneten Werte mit vier Stellen, Toleranz ±0,001. KONZEPT 8.5 nennt deren Rundung.
  - Scorer 1 gegen 2: 0,7902 / 0,6905 / 0,8104.
  - Mittel über die 66 Paare der 12 manuellen Scorer: 0,7253 / 0,6598 / 0,7656.
- **Lücken (CORE-M10-03)** nur im kontinuierlichen Modus. Abdeckung = belegter Anteil der ganzen Aufnahme; eine Signalaufnahme ohne Annotation hat dort Abdeckung 0.
- **Überlappungen (CORE-M10-04):** kontinuierlich jede Überlappung je Annotator, ereignisbasiert nur gleiche Codes. Marken der Dauer 0 zählen nur für das Vokabular. 1 ms ist ein numerisches Epsilon, keine Schwelle.
- **Ausweis:** κ (Mittel, Minimum, Paare), Abdeckung, Modus, Raster und Quellen stehen in `recordings[].metrics["annotation"]`.

**A-81 KI-Struktur M11/M12** (präzisiert A-21).
- **Labels:** `[ai] labels` = `events:<Spalte>`, `participants:<Spalte>` oder `annotations` (Codes der M10-Annotationen).
  - Ohne Angabe ist CORE-M11-01 not_applicable.
  - Zähleinheit: Ereignisse bzw. Probanden. Parameter `min_share` = 0,05 (Startwert der PRD, nicht kalibriert).
  - `annotations`: Jede Annotation jedes beteiligten Annotators (`[annotation] annotators`) zählt als ein Ereignis, auch Marken der Dauer 0. Zugeordnete Hypnogramme zählen im Split ihrer Signalaufnahme; nicht zuordenbare reine Annotationsdateien zählen nicht.
  - `events:<Spalte>` liest events.tsv mit demselben Leser und derselben Kopfregel wie M10 (erste von doppelten Spalten; kein Label sind nur „“ und „n/a“).
  - Aufnahmen, deren Annotationen oder events.tsv nicht lesbar sind, bleiben ganz außen vor und werden in einem Warnhinweis gezählt; ist keine lesbar, ist CORE-M11-01 not_checkable (`ai.labels_unreadable`), für beide Quellen.
  - Jede Spalte, deren Name ein Alter bezeichnet (`age`, `age_years`, `AgeAtScan` …), zählt in den 10-Jahres-Stufen der Demografie; nennt der Name eine Einheit (Monate, Wochen, Tage; als eigenes Wort oder zusammengeschrieben wie `AgeMonths`, `AgeInDays`, `GestationalAgeWeeks`), wird vorher in Jahre umgerechnet; andere Einheiten (z. B. Stunden) gelten als Jahre und ergeben dann eine falsche Stufe, aber nie einen Rohwert (für G1 vorgemerkt); ein Wert, der kein Alter ist, ist kein Label; das Rohalter erscheint nie. Erkannt wird am Spaltennamen.
  - In einer Spalte `sex` oder `gender` sind die Platzhalter der Demografie kein Label.
  - Die Labels werden nur gezählt, wenn CORE-M11-01 (bzw. dessen Prüfung) geladen ist; nur dann enthält results.json den Block `ai.labels`.
- **Demografie (CORE-M11-02):** `participants.tsv` im Datensatz, auch für Rohordner (participant_id = Proband der Zuordnung, mit oder ohne `sub-`).
  - Spalte `sex` vor `gender`. Platzhalter (unknown, unk, u, nan, na, n/a, none, null, missing, not reported, not available, ?, -; ohne Groß-/Kleinschreibung) gelten als nicht dokumentiert.
  - Alter in 10-Jahres-Stufen, „90+“ als oberste. „N+“ zählt zur Stufe von N; ein Bereich „a-b“ zur Stufe von a; Nicht-Zahlen gelten als fehlend.
  - Das Rohalter wird nie ausgegeben.
- **Kleine Zellen** (A-51; Tabellenregel nach dem Review von P4):
  - Eine Tabelle auf Probandenebene ist eine Verteilung von Probanden auf Kategorien: jeder Bereich (all, train, val, test) einer Labelquelle aus participants.tsv sowie die Demografie-Tabellen Altersstufen und Geschlecht.
  - Als öffentlich gilt jede Probandenzahl, die NeuroGrid an anderer Stelle ausgibt: Probanden je Bereich und Split, Probanden mit dokumentiertem Wert, die Einzelergebnisse von CORE-M11-02. Diese Zahlen schützen nichts und werden deshalb nicht verdeckt.
  - Kategorien und Zahlen einer Tabelle erscheinen nur, wenn **jede** besetzte Zelle mindestens 5 zählt; Nullzellen erscheinen dann auch. Sonst wird die Tabelle **zurückgehalten**: keine Kategorien, keine Zahlen, nur ihre Summe. Die frühere Mitunterdrückung einzelner Zellen entfällt; sie war über Summen, Split-Zahlen, Nullzellen und Statusangaben zurückzurechnen.
  - Die Bereiche einer Labelquelle hängen über Summen zusammen: Wird einer zurückgehalten, werden alle zurückgehalten.
  - CORE-M11-01 bei zurückgehaltener Labelquelle: ein Ergebnis je Bereich ohne Klasse, Bezeichnung, Anteil und Zahl (Details: Bereich, Einheit, Summe, `withheld`; zusätzlich `small_cell`, wenn die Probandenzahlen allein zeigen, dass der Bereich eine Zelle 1–4 enthält). Der Status folgt nur aus den Probandenzahlen und `min_share`: bestanden, wenn 1/N ≥ `min_share`; verletzt, wenn die Zahlen allein zeigen, dass der Bereich die Zelle 1–4 enthält (N ≤ 4, oder alle Bereiche mit Probanden haben dieselbe Summe, z. B. ohne Splits), und 4/N < `min_share`; sonst not_checkable (`ai.small_cell`). Darüber hinaus wird nicht ausgegeben, ob ein Bereich eine Zelle 1–4 hat oder einem Split eine Klasse fehlt. Die erste Fassung (genaues Ergebnis für nur mitgehaltene Bereiche, Kennzeichen je Bereich) war nachweislich zurückzurechnen; eine Auszählung über alle Belegungen zeigt mit dieser Fassung keine herleitbare Zelle mehr.
  - Preis der Regel (für G1 vorgemerkt): Bei zurückgehaltener Labelquelle mit Splits meldet CORE-M11-01 eine in einem Split fehlende Klasse oder ein deutliches Ungleichgewicht nicht als verletzt, sondern als bestanden (1/N ≥ `min_share`) oder not_checkable.
  - Ereigniszahlen (Quellen `events:` und `annotations`) und Split-Zahlen werden nicht zurückgehalten.
  - Diagnoseähnliche Spalten dürfen Labelquelle sein, nur aggregiert und unterdrückt. Für G1 vorgemerkt: Lesart von DM-02.
- **Splits:** `.neurogrid/splits.tsv` (recording, split) hat Vorrang vor einer Spalte `split` in participants.tsv; sind beide vorhanden, gibt es einen Hinweis.
  - Erlaubte Werte: train, val, test.
  - `recording` ist der relative Pfad oder die pseudonyme ID.
  - Ein Proband in mehr als einem Split ist in jeder Kombination ein Fehler.
  - `[ai] splits` außerhalb des Datensatzes ist erlaubt, mit Hinweis.
  - Ordnet die Split-Quelle keine Aufnahme zu, ist CORE-M12-01 datensatzweit not_applicable (`ai.splits_unassigned`).
- **Duplikate (CORE-M12-02):** über den Signal-Hash `NG-SIGHASH-v1` (die Prüfung gehört zum Stream).
  - Jedes Mitglied einer Duplikatgruppe erhält einen Fehler; Unterschlüssel ist die Gruppennummer, die Details nennen die angezeigten Aufnahme-IDs (in Rohordnern ohne `--show-paths` pseudonym).
  - Hashes werden nie ausgegeben. Identische flache Aufnahmen sind Duplikate.
- **Modul:** `checks/ai_dataset.py` (Name aus TECH-01/KONZEPT 1.2).

**A-82 Provenienz M13, `manifest`/`verify`** (präzisiert A-22).
- **Manifest:**
  - Standardort `<Datensatz>/.neurogrid/manifest.json` (KONZEPT 2.5); der BIDS-Validator betritt `.neurogrid/` nicht. Eine `manifest.json` in der Datensatzwurzel ist eine gewöhnliche Datei. Liegt `--out` in einem BIDS-Datensatz außerhalb versteckter Ordner, gibt `manifest` einen Hinweis auf den Validator.
  - Ein Link an `.neurogrid` oder an der Manifestdatei wird nicht verfolgt (A-52, A-66).
  - Der Hinweis auf den Validator erscheint nur an einer Stelle, die der gebündelte Validator 3.0.2 prüft: nicht in versteckten Teilen, nicht in den obersten Ordnern sourcedata, derivatives, code, stimuli, log und doc (ohne Groß-/Kleinschreibung) und nicht unter einer wörtlichen Zeile der `.bidsignore` (nachgemessene Regeln des Validators). Bei Platzhaltern oder Maskierungen (wenn keine wörtliche Zeile die Datei erfasst), bei einer Verneinung (wenn eine wörtliche Zeile sie erfasst) oder bei unlesbarer `.bidsignore` lautet der Hinweis, die Manifest-Datei „kann daher gemeldet werden“.
  - Format nach A-22, zusätzlich `skipped` und `excluded`:
    - `skipped`: Links, Junctions, Sonderdateien und Namen, die die Pfadprüfung ablehnt, prozentkodiert. Damit bemerkt `verify` auch neue Links. Unter einem abgelehnten Ordnernamen wird weiter aufgelistet (Windows über das Präfix `\\?\`, Links nie): Was darunter liegt, steht ebenfalls in `skipped` und wird nur auf Vorhandensein verglichen, nie auf Inhalt. Ist ein solcher Ordner nicht auflistbar, schreibt `manifest` nichts (Exit 1); `verify` und `check` melden ihn als unlesbar. Kodierte und gewöhnliche Namen bilden getrennte Namensräume (Vergleich über die ursprünglichen Namensbytes).
    - `excluded`: Vault-Protokoll `access.jsonl` und dessen Sperrdatei `access.jsonl.lock` (der Name der Sperrdatei wird mit dem Vault in P6 bestätigt). `check` lässt zusätzlich seinen Arbeitsordner `run-*` außen vor.
  - Grenzen (A-53): Verschachtelungstiefe von manifest.json höchstens 35, von `processing_steps.json` höchstens 34 (Parameter eines Schritts höchstens 32 Ebenen); tiefer ist ungültig (`too_deep`; Befund in `check`, Exit 2 in `verify` bei manifest.json bzw. in `manifest` bei `processing_steps.json`). Höchstens 2 Mio. Dateien und übersprungene Einträge; darüber schreibt `manifest` nichts und endet mit Exit 1 (Datensatzdaten ergeben nie Exit 2, C2). Kodierte Pfade dürfen bis 294 903 Zeichen lang sein (Schreiber und Leser gleich).
  - Betriebssystemdateien (.DS_Store, Thumbs.db) gehören dazu.
  - Ist beim Erstellen eine Datei unlesbar, wird nichts geschrieben (Exit 1).
  - Gehasht wird in min(4, Kerne) Threads.
- **`verify`:**
  - `--manifest` ist Pflicht; Exit 0 bei Gleichheit, 1 bei Abweichung, 2 bei ungültigem Manifest.
  - Abweichungsarten: geändert, neu, fehlend, Art geändert, unlesbar.
  - Bekannte Steuerdateien in `.neurogrid/` werden im Klartext genannt, andere Dateien in Rohordnern pseudonym, außer mit `--show-paths` (D-10 f).
- **CORE-M13-01:** Warnung, mit `--strict` oder `[check] strict` ein Fehler. Dafür erhält das Regelpaketformat das optionale Feld `strict_severity` (wie A-62):
  - Das Feld kann den Schweregrad auch senken.
  - Das Abdeckungsmaß nutzt weiter den Grundschweregrad.
  - Die Bedingung „[consent] konfiguriert“ von M14 folgt in P6.
- **CORE-M13-02:**
  - Fehler je abweichender Datei, auch ohne `--strict`.
  - Ohne Manifest not_applicable (CORE-M13-01 meldet das Fehlen); mit unbrauchbarem Manifest not_checkable.
- **CORE-M13-03:** Quellen sind `.neurogrid/provenance.yaml`, die Verarbeitungsschritte von `convert` und `GeneratedBy` der dataset_description.json.
  - `provenance.yaml` enthält `processing_steps` und `software`. Eine leere Liste `processing_steps: []` dokumentiert „keine Verarbeitung“, aber keine Software.
  - `GeneratedBy` (Name und Version) zählt nur als Software.
- **Ausgaben im Datensatz:** Liegt `--out` im Datensatz, gibt es einen Hinweis; ein späterer Lauf meldet die frühere results.json als neue Datei. Bei einer einzelnen Datei als Ziel gibt es keinen Datensatz und keinen Hinweis. Die Konsole nennt ein Ziel in einem Rohordner nur pseudonym (außer BIDS, `--show-paths` oder ein fester Steuerdateiname); das gilt für `manifest --out`, `check --out` und `scan --out`. `report --out` kennt den Datensatz nicht; dort wird nur der Benutzerordner verdeckt (bekannte Grenze).
- **Leere Optionswerte** (`--manifest ""`, `--evidence ""`, `--config ""`, `--out ""`) ergeben in check, convert, manifest, scan und report Exit 2 statt des Standardorts.
- **`.neurogrid/provenance.yaml`** wird als Steuerdatei vor der Signalqualität geprüft (Exit 2 vor der langen Rechnung).

**A-83 Nachweise, Ausnahmen, gxdsl008** (präzisiert A-14, A-15, A-40).
- **evidence.yaml:**
  - `--evidence DATEI`; ohne die Option der Standardort `<Datensatz>/.neurogrid/evidence.yaml`.
  - Format `format_version: 1` mit `evidence: {Regel-ID: {…}}`. `sha256` darf groß geschrieben sein (gespeichert klein); `date` als YAML-Datum oder als Text `JJJJ-MM-TT` (anderer Text, unmögliche Daten und Zeitstempel werden abgelehnt); `format_version: true` wird abgelehnt. Schema und Leser stimmen überein, bis auf die Pfadprüfung von `document`, die nur der Leser vornimmt. Ein Regel-ID-Schlüssel mit Zeilenumbruch wird wie jeder ungültige Schlüssel nur mit seiner Position genannt (`evidence.#<n>`), ein Feldname mit Zeilenumbruch als `?`.
  - Status „provided“ ohne Dokument ist ein Werkzeugfehler.
  - NeuroGrid berechnet den Hash jedes genannten Dokuments und vergleicht ihn, wenn einer eingetragen ist.
  - Bei einer manuellen Regel bleibt „provided“ bei fehlendem, verlinktem oder geändertem Dokument die Angabe des Nutzers und erhält einen Warnhinweis; eine halbautomatische Nachweisregel ist dann verletzt (Grund `evidence.<Dokumentprüfung>`, z. B. `evidence.document_missing`).
  - Weitere Hinweise: Prüfdatum nach dem Stichtag, Einträge für nicht geladene Regeln, Einträge zu Regeln, die keine Nachweisregeln sind.
  - Anzeige: `document` (relativer Pfad), `reviewer`, `comment` und `justification` stehen in results.json und im Berichtsabschnitt 5 im Klartext, auch in Rohordnern ohne `--show-paths` (der Bericht braucht einen lesbaren Dokumentverweis, REP-05); die Konsole gibt sie nie aus. Der Info-Hinweis `notice.evidence_looks_identifying` zählt Einträge, deren `reviewer` oder `document` nach Personendaten aussieht. `comment` und `justification` verantwortet der Nutzer (Rolle oder Kürzel nach A-15).
  - In results.json stehen je Nachweis der von NeuroGrid berechnete Hash (`sha256`) und der eingetragene (`sha256_recorded`).
  - `summary.open_evidence` zählt nur offene Nachweise von Fehler- und Warnregeln (wirksamer Schweregrad, A-16).
- **Ausnahmen:** Jeder passende aktive Eintrag gilt als verwendet. Einträge für Regeln, die in keinem geladenen Paket stehen, erhalten einen eigenen Warnhinweis. Das Format der Regel-ID wird nur beim Lesen der neurogrid.toml geprüft; results.json früherer Stände bleibt lesbar.
- **gxdsl008:**
  - Klausel „unknown“ im Paket, im Bericht übersetzt (D-03).
  - GX-03 prüft das Speicherformat:
    - EDF, EDF+C und EDF+D bestehen, ebenso HDF5-Container (EEGLAB MAT v7.3).
    - BDF, BrainVision, EEGLAB MAT v5 und FIF ergeben die Warnung, auch für BrainVision-Umwandlungen durch NeuroGrid.
    - Auch nicht unterstützte Aufnahmeformate und verwaiste Begleitdateien (z. B. `.cnt`, `.mff`, `.eeg` ohne Kopf) werden bewertet; der Wert ist das Format aus der Endung, nie der Dateiname. NWB gilt als HDF5, wenn die Datei HDF5 ist, sonst als NWB (Warnung). Das Paket wird für sich bewertet, auch ohne core.
- **Bericht:** Ein Befund mit Datei, aber ohne Zeitbereich, auf einer Datei, die keine Aufnahme ist (Steuerdatei, geänderte oder neue Datei des Manifestvergleichs, nicht unterstützte Datei), zeigt „gesamte Datei“ statt „gesamte Aufnahme“. Die Legende der Ampel folgt der Regel aus „Übergreifend“.
  - GX-05 besteht, wenn das Manifest vorhanden ist und stimmt.
- **Impedanz:** Aufnahmen ohne dokumentierte Impedanzen ergeben für die Impedanzschwelle not_checkable (`impedance.not_documented`) statt keinen Befund.
- **CLI-03** schließt in P4 für die Kommandozeile der PRD; `--role` folgt mit dem Vault in P6.
