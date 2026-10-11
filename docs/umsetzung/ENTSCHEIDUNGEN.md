# NeuroGrid – Entscheidungen und Annahmen

Rangfolge bei Konflikten: Antworten und Freigaben des Auftraggebers > PRD > bestehender Code > Annahmen.
Blocker-Fragen (F1–F7) stehen offen bis zur Antwort; Annahmen (A-xx) gelten, solange der Auftraggeber
nicht widerspricht. Verweise auf Anforderungen: IDs aus [ANFORDERUNGEN.md](ANFORDERUNGEN.md).

## Geprüfte Fakten (Stand 11.10.2026, Quellen im Phase-1-Bericht)

- Alle zehn Bibliotheksversionen und Lizenzen aus §9 stimmen mit PyPI überein (mne 1.13.2, mne-bids 0.20.0,
  bids-validator-deno 3.0.2, pyprep 0.9.0, eegprep 0.4.0, autoreject 0.5.1, mne-icalabel 0.10.0, edfio 0.4.18,
  pyEDFlib 0.1.42, eegdash 0.9.1, nwbinspector 0.7.2).
- eegprep 0.4.0 verlangt Python ≥ 3.12 und zieht pyEDFlib, oct2py (Jupyter/Octave-Kernel-Stack) und pybids
  mit den LGPL-Paketen frozendict und num2words nach. pyEDFlib 0.1.42 hat für Python 3.13 keine Wheels für
  Windows und Linux x86_64. Aktuelle numpy/scipy unterstützen 3.11 nicht mehr; ältere Versionen schon.
- certifi (MPL-2.0) und tqdm (MPL-2.0 AND MIT) sind harte transitive Abhängigkeiten von MNE.
- Der BIDS-Validator 3.0.2 ist auf PyPI als universelles Wheel `bids-validator-deno` erhältlich und hängt vom
  PyPI-Paket `deno` (MIT, ~42 MB je Plattform) ab; mitgeliefertes Schema = BIDS 1.11.1. Aktuelle Spezifikation:
  BIDS 1.11.2 (29.9.2026). MNE-BIDS 0.20 schreibt `BIDSVersion: 1.9.0` und `n/a` für EEGReference.
- Playwright 1.63 (Apache-2.0) lädt Chromium bei `playwright install` nach; offiziell unterstützt sind Windows 11
  und Debian/Ubuntu, nicht Windows 10. Noto Sans SC steht unter OFL 1.1.
- MkDocs 1.6.1 ist seit 2024 ohne Release; Material for MkDocs ist im Wartungsmodus.
- Normtexte: GB/T 47127-2026 ist kostenlos auf openstd.samr.gov.cn lesbar (Bildseiten mit Captcha, nur manuell).
  YY/T 2029-2026 ist von hier aus nicht beschaffbar. ISO/IEC TS 27571:2026 kostet CHF 100 (15 Seiten).
  Der Text von T/GXDSL 008-2025 ist derzeit nicht abrufbar (404 bzw. Captcha).
- Testdaten: OpenNeuro-Datensätze unter CC0 decken alle fünf Formate ab; PSG-IPA (PhysioNet, CC BY 4.0) hat
  12 Scorer je Aufnahme. openneuro-py ist GPL-3.0 und wird nicht verwendet. Einige Kandidaten haben 60 Hz Netzfrequenz.
- PyPI-Namen `neurogrid` und `neurogrid-eeg` sind frei.

## Entscheidungen des Auftraggebers

Am 11.10.2026 hat der Auftraggeber alle Empfehlungen zu F1–F7 freigegeben („Wir folgen deinen Ratschlag
und setzen deine Recommendations um“).

**D-01 (F1) Umfang.** Umgesetzt werden v0.1, v0.2 und v1.0 vollständig, soweit ohne Normtexte möglich.
Normabhängige Teile folgen, sobald der jeweilige Text vorliegt (Go/No-Go). NG-F17 entsteht als
Forschungsteil in `research/` außerhalb des Pakets. V-04 (NWB/invasiv, laut PRD bedingt) und V-05
(Server-Variante, nicht spezifiziert) bleiben offen.

**D-02 (F2) Normtexte.**
- GB/T 47127-2026: Der Auftraggeber lädt das PDF auf openstd.samr.gov.cn und legt es in `.local/normen/`.
- YY/T 2029-2026: Der Auftraggeber beschafft den Text.
- ISO/IEC TS 27571: Kauf (CHF 100) durch den Auftraggeber vor der v1.0-Phase.
- T/GXDSL 008: `gxdsl008` entsteht aus den fünf PRD-Startwerten (A-40).

**D-03 (F3) Sprache öffentlicher Bezeichner.** Englisch in Code und allen öffentlichen Formaten
(YAML, JSON, TOML, Pydantic). Eine 1:1-Abbildung der PRD-Begriffe steht in der Dokumentation.

**D-04 (F4) Laufzeit.** Streamingfähige Metriken laufen blockweise über die volle Länge. M06 und M09 laufen
auf einer deterministischen Stichprobe. Sie wird in JSON und Bericht ausgewiesen und ist bis „volle Länge“
konfigurierbar.

**D-05 (F5) Abhängigkeiten und Lizenzen.**
- eegprep entfällt; das ist eine freigegebene Abweichung von §9 (LIB-05).
- NG-N07 bedeutet: permissive Lizenzen, dazu MPL-2.0 für unverändert genutzte Laufzeitabhängigkeiten.
  GPL, LGPL und AGPL sind verboten.
- Entwicklungswerkzeuge werden getrennt geprüft.
- Python 3.11–3.13.

**D-06 (F6) Downloads.** Freigegeben:
- uv und Python 3.11/3.12
- PyPI-Pakete, Chromium für Playwright, Noto Sans SC
- Testkorpus: OpenNeuro CC0-Teilmengen und PhysioNet PSG-IPA
- für NG-F17: torch, braindecode, moabb und MOABB-Daten

**D-07 (F7) Repository.**
- Lokales Git, Arbeit auf einem Arbeitszweig.
- Der Auftraggeber legt das öffentliche GitHub-Repository `neurogrid` an und nennt die URL.
- Gepusht wird nur nach Freigabe.
- Gitee-Spiegel und PyPI-Veröffentlichung führt der Auftraggeber mit eigenen Konten aus; ich bereite sie vor.
- Urheber: „Ammar Ahad“.
- `docs/umsetzung/` ist öffentlich; die PRD bleibt unversioniert.

## Annahmen (Nicht-Blocker)

**A-00 Nicht ausgefüllte Eingaben des Auftrags.** Ausgangslage: neues Projekt unter
`Projekte/neurogrid`. Technische Vorgaben: laut PRD §13. Zugänge: keine bekannt (uv, Deno, gh fehlen
lokal). Regulatorik: laut PRD (PIPL, MOST-Leitlinie, Positionierung als Vorprüfung, Apache-2.0).
Nicht anfassen: alle anderen Ordner unter `Projekte/`. Freigabemodus: A (Standard).

**A-01 PRD und Geschäftsinhalte.** Die PRD liegt in `.local/prd/` und wird nie versioniert
(`.gitignore`). `docs/umsetzung/` enthält nur technische Inhalte; Abschnitte zu Markt, Preisen,
Rechtsstatus und Gates werden nur über BIZ-IDs referenziert.

**A-02 Kernregelpaket für die Metriken.** Zusätzlich zu `bids`, `gxdsl008`, `yyt2029`, `gbt47127` gibt es
ein eingebautes Paket `core` mit je einer Regel pro Metrik-Prüfung (M01–M13, ab v0.2 M14) und den
Startschwellen aus §12. Es ist standardmäßig geladen und in `neurogrid.toml` abwählbar. Klausel = Metrik-ID
(z. B. „M07“), Quelle = „NeuroGrid §12“. Phasen: M01 speicherung; M02–M09 erfassung; M10 annotation;
M11–M12 verarbeitung; M13 speicherung; M14 zugriff.
*Begründung:* Laut §9 messen Prüfer und bewertet nur der Regelmotor; v0.1 hat sonst keine Regel für
M02, M04, M06–M13, also weder Befund noch Klausel noch Ampel. *Betrifft:* ARC-02, NG-F07–F10, NG-F13.

**A-03 Eingang von `check`.** `check` akzeptiert BIDS-Datensätze (erkannt an `dataset_description.json`)
und Rohordner. Der Validator läuft nur auf BIDS; bei Rohordnern entsteht ein Hinweis „BIDS-Struktur nicht
geprüft“. M02 bewertet in beiden Fällen dasselbe interne Metadatenmodell. `n/a` gilt bei EEGReference und
PowerLineFrequency als fehlend, bei SoftwareFilters als gültig (BIDS: keine Softwarefilter).

**A-04 Herkunft von Metadaten, die im Format fehlen.** Vorrang: `neurogrid.toml` > BIDS-Sidecars
(`participants.tsv`, `*_eeg.json`, `*_channels.tsv`, `*_electrodes.tsv`, `*_events.tsv`) > Formatkopf
(z. B. BrainVision-Impedanzblock, FIF `line_freq`) > undokumentiert. Undokumentiert erzeugt den Befund
„nicht dokumentiert“, keinen Abbruch. Elektrodentyp, Gerät und Netzfrequenz für Rohdaten kommen aus der
toml; Splits aus einer `splits.tsv`; Annotator aus einer Spalte `annotator` in `events.tsv` oder aus
getrennten Annotationsdateien je Annotator. Demografie-Spalten werden ohne Groß-/Kleinschreibung
abgebildet (age; sex/gender; m/f/M/F).

**A-05 Konvertierung.** `convert` braucht für Rohordner eine Zuordnung zu sub/ses/task/run: Regex mit
benannten Gruppen oder Zuordnungstabelle in der toml. Fehlt sie oder fehlt `task`, endet der Lauf mit
Exit 2 und einer ausgefüllten Vorlage. Labels nur alphanumerisch. EDF, BDF, BrainVision und EEGLAB werden
von MNE-BIDS übernommen; FIF wird nach BrainVision geschrieben (pybv, BSD-3). Pflichtfelder der Sidecars
werden aus den Metadatenquellen (A-04) befüllt, nicht mit `n/a`. `BIDSVersion` wird auf die Schema-Version
des mitgelieferten Validators gesetzt. EDF+D (diskontinuierlich) wird als M01-Befund „nicht unterstützt“
gemeldet. Kopfzeilen-Felder (Patient, Aufnahme) werden nie in JSON oder Bericht übernommen.

**A-06 BIDS-Validator.** `bids-validator-deno==3.0.2` und `deno` exakt gepinnt als Python-Abhängigkeit;
Aufruf als Unterprozess mit `--format json -o <datei>` und `--max-rows -1`, ohne Netzrecht. Geprüft wird
gegen das mitgelieferte Schema (BIDS 1.11.1). Exit 16 = Validierungsbefunde, anderer Exit ≠ 0 = Werkzeugfehler.
Validator-Fehler → Regel `BIDS-STR-001` (fehler), Warnungen → `BIDS-STR-002` (warnung); Code und Ort stehen
in den Belegen, Klausel = Validator-Code. Getestet wird die Abbildung, nicht jeder einzelne Code.

**A-07 Sprachen.** Eigene Meldungen nur über Sprachschlüssel. Tabellen für zh, en und de vollständig
(de laut §1 im Kern). CLI-Sprache über `--lang`, `NEUROGRID_LANG` oder Systemsprache, Standard en;
Ausgabe immer UTF-8. Fremdmeldungen (MNE, Validator) erscheinen im Original, eingerahmt von einer
übersetzten Meldung. Die chinesischen Texte schreibe ich; ein Muttersprachler muss sie prüfen
(Abschlussbericht: manueller Schritt).

**A-08 Bericht.** Je Sprache und Format eine Datei (`report.zh.html`, `report.en.pdf` …) im Ordner aus
`--out` (Standard: neben `results.json`). `--lang` und `--format` nehmen Komma-Listen (in PowerShell in
Anführungszeichen) und wiederholte Optionen an. Das Deckblatt-Datum ist das Erzeugungsdatum des Berichts.
HTML ist eigenständig (kein CDN), Grafiken als Inline-SVG aus matplotlib. Den festen Satz aus §14 übersetze
ich nach zh/en; der Auftraggeber gibt die Übersetzung frei.

**A-09 Befundmodell.** Ein Befund je Regel × Objekt (Datensatz, Aufnahme, Kanal oder Datei). Die
PRD-Felder bleiben; ergänzt werden Regelpaket und -version, Phase, Datei, Kanal, Zeitbereiche,
Meldungsschlüssel und ein stabiler Schlüssel. Statuswerte: bestanden, verletzt, ausgenommen,
nicht anwendbar, nicht prüfbar, Nachweis offen. Bestandene Prüfungen werden kompakt mit ausgegeben.
Zusätzlich zu den zehn PRD-Objekten entstehen Hilfsmodelle (Regel, Regelpaket, Messwert, Manifest,
Nachweis, Ausnahme, Rolle, Risiko, Laufinfo); die zehn Objekte bleiben inhaltlich wie in §10.

**A-10 Zeitbereich.** Liste von [start_s, ende_s] relativ zum Aufnahmebeginn; bei aufnahmeweiten
Werten „gesamte Aufnahme“, bei datensatzweiten Werten leer. Höchstens 20 Intervalle plus Anzahl und
Gesamtdauer.

**A-11 Reproduzierbarkeit.** `results.json` enthält keine Uhrzeit, keinen Rechnernamen und keine absoluten
Pfade; Pfade relativ und mit `/`; Schlüssel und Listen sortiert; Gleitkommawerte auf 6 signifikante
Stellen gerundet; ein Seed aus der Konfiguration geht an ICA, autoreject und pyprep-RANSAC.
Byte-Gleichheit wird auf demselben Rechner zugesichert und plattformübergreifend in der CI gemessen.

**A-12 Exitcodes.** Datendefekte (auch unlesbare Dateien, M01) sind Befunde → Exit 1, wenn mindestens ein
nicht ausgenommener Befund mit Schweregrad fehler verletzt ist. Exit 2 nur bei ungültiger Konfiguration,
nicht ladbarem Regelpaket, fehlendem Validator oder internem Fehler; eine ausdrücklich übergebene
Einzeldatei unbekannten Formats ergibt Exit 2 mit Dateiname. Warnungen → Exit 0. Gleiches Schema für
`verify`, `vault verify` und `diff` (Exit 1 bei neuen Fehlerbefunden).

**A-13 Schwellen und eigene Regelpakete.** Vorrang: toml > Regelpaket > Standardwert der Prüfung.
Adressiert wird über die Regel-ID. Jede Prüfung deklariert ihre Parameter samt Vergleichsrichtung in
einer dokumentierten Registry; eigene Pakete (per Pfad) dürfen nur registrierte Prüfungen verwenden.
YAML nur per `safe_load`, kein ausführbarer Code in Paketen, doppelte IDs = Exit 2. Wirksame Schwellen und
ihre Herkunft stehen im Befund; überschriebene Schwellen listet der Anhang.

**A-14 Ausnahmen.** `[[exceptions]]` mit Regel, optionalem Objekt-Muster, Pflichtbegründung (nicht leer),
optional genehmigt_von und gueltig_bis. Ausgenommene Befunde zählen weder für Exit 1 noch für die Ampel und
stehen im Anhang. Fehlende Begründung = Exit 2; abgelaufene Ausnahme = Warnung.

**A-15 Nachweise (`evidence.yaml`).** Je Regel: Status (offen, erfüllt, teilweise, nicht anwendbar),
Dokumentpfad, SHA-256 (automatisch), Prüfer, Datum, Kommentar; „nicht anwendbar“ braucht eine Begründung.
Halbautomatisch = Dokument vorhanden und Hash stimmt. Manuelle Regeln ohne Eintrag sind „Nachweis offen“
und zählen mit ihrem Schweregrad (sonst ließe sich „besteht diese Prüfungen“ nicht ehrlich sagen).

**A-16 Ampel und Abdeckungsmaß.** Je Phase: rot bei mindestens einem verletzten Fehler, gelb bei Warnung
oder offenem Nachweis, sonst grün; grau ohne Regeln. Abdeckungsmaß je Normpaket = Muss-Klauseln (mit
mindestens einer fehler-Regel), die automatisch oder halbautomatisch geprüft werden, geteilt durch alle
Muss-Klauseln; für `core` und `bids` „n/a“ (keine Normklauseln).

**A-17 Annotation (M10).** Modus kontinuierlich (z. B. Schlafstadien) oder ereignisbasiert, in der toml.
κ = Cohens κ paarweise auf einem Epochenraster (Standard 30 s kontinuierlich, 1 s ereignisbasiert), „kein
Ereignis“ als eigene Klasse; bei mehr als zwei Annotatoren Mittelwert und Minimum. Lücken und Abdeckung nur
im kontinuierlichen Modus; Überlappungen je Annotator. Uneinheitliche Codes = Codes außerhalb des
Vokabulars (toml oder `events.json`) oder gleiche Bezeichnung mit verschiedenen Codes. Mit einem Annotator
ist κ „nicht anwendbar“.

**A-18 Technische Parameter M03, M04, M07, M08.** M03: gemischte Raten gelten als dokumentiert, wenn die toml
sie begründet. M04: Namen gegen die 10-05-Montage von MNE (umfasst 10-20/10-10), Abbildungstabelle in der toml,
Nicht-EEG-Kanäle ausgenommen. M07: dokumentierte Netzfrequenz (Standard 50 Hz laut PRD; manche öffentliche
Daten haben 60 Hz), Welch-Spektrum, Median über EEG-Kanäle, nicht anwendbar bei zu niedriger Abtastrate.
M08: 1-s-Fenster, Varianz unter Toleranz oder Werte an den Grenzen des Messbereichs (EDF/BDF-Kopf),
Anteil je Kanal. Alle Werte konfigurierbar.

**A-19 M06 und M09.** M06 = Anteil schlechter EEG-Kanäle laut pyprep NoisyChannels (RANSAC nur mit
Elektrodenpositionen, sonst ohne und mit Hinweis). M09 erzeugt zwei Werte: Verwerfungsrate von autoreject
und Anteil der ICA-Komponenten, deren wahrscheinlichste ICLabel-Klasse nicht „brain“ ist. ICLabel läuft mit
onnxruntime (MIT) statt torch.

**A-20 Kalibrierung.** Skript unter `tools/` mit fest gepinnten OpenNeuro-Snapshots (mindestens drei);
95. Perzentil über Aufnahmen; Ergebnis wird Standardwert im Paket `core` mit Herkunftsangabe.

**A-21 KI-Struktur (M11, M12).** Labelquelle konfigurierbar (`trial_type` oder eine participants-Spalte);
Klassenanteil je Split und gesamt; Altersgruppen in 10-Jahres-Stufen (konfigurierbar). Ein Proband in mehr
als einem Split ist in jeder Kombination ein Fehler; ohne Splits ist der Split-Teil „nicht anwendbar“.
Signal-Hash: SHA-256 über die nach Namen sortierten Kanäle, Werte in µV auf 0,1 µV gerundet, plus
Abtastrate, blockweise berechnet. Teilduplikate sind nicht abgedeckt.

**A-22 Manifest.** Format mit Versionsnummer und sortierter Dateiliste (Pfad, SHA-256, Größe),
Verarbeitungsschritten und Softwareversionen; Manifest-Hash = SHA-256 der kanonischen JSON-Bytes.
`verify` meldet geänderte, neue und fehlende Dateien. `convert` protokolliert eigene Schritte; fremde
Schritte aus `dataset_description.json` (GeneratedBy) oder einer optionalen `provenance.yaml`.
Ohne `--strict` ist ein fehlendes Manifest eine Warnung. Ablageort wird in Phase 2 festgelegt (Ziel:
im Datensatz, ohne BIDS-Validatorbefund).

**A-23 Paket `kernel`.** Unterpaket `neurogrid.kernel` (Regelmotor, Befunde/Belege, Berichtsgrundlage,
Provenienz, Sprachtabellen) ohne Importe aus EEG-Modulen, durch einen Test erzwungen; `mypy --strict` auf
`kernel`. Abdeckung „Kern“ = `kernel/` + `model/`, „Prüfer“ = `checks/` + `io/`. Herauslösen als eigene
Distribution erst, wenn Proof startet.

**A-24 Adapter.** Einlesen über MNE; EDF-Kopf (M01) über edfio; BDF-Kopf über einen eigenen, kleinen
Parser, weil pyEDFlib unter Python 3.13 keine Wheels hat. Adapter-API `read(pfad) → Recording` ist stabil
(RehabLoop).

**A-25 Offline, keine Telemetrie.** Kein Netzwerkcode zur Laufzeit; Tests sperren Sockets; Playwright lädt
nur `file://` und bricht alle anderen Anfragen ab. „Daten nie selbst exportieren“ heißt: kein Upload, keine
Übertragung; lokales Schreiben (convert, Bericht, Export-ZIP) ist erlaubt.

**A-26 Installation ohne Internet und PDF.** Ein Skript baut je Plattform ein Offline-Bündel (Wheelhouse
aus `uv.lock`, Chromium, Schrift, Dokumentation, Prüfsummen). Unter Windows nutzt die PDF-Erzeugung,
falls Chromium fehlt, den vorinstallierten Edge. Windows 10 wird von Playwright offiziell nicht
unterstützt; dort gilt PDF als „nicht verifiziert“.

**A-27 Schrift.** Noto Sans SC (OFL 1.1) wird mitgeliefert, mit Lizenztext und `THIRD_PARTY_NOTICES`.

**A-28 Dokumentation.** MkDocs 1.6.1 + Material 9.7 + mkdocs-static-i18n, exakt gepinnt (eingefrorener
Stack, Wartungsrisiko dokumentiert); `docs/zh`, `docs/en`; `docs/umsetzung` gehört nicht zur Website;
Dokumentation unter CC BY 4.0.

**A-29 Testkorpus.** OpenNeuro (CC0): ds003775 (EDF), ds002778 (BDF), ds004148 (BrainVision), ds004504
(EEGLAB), ds000248 (FIF mit EEG); PhysioNet PSG-IPA (CC BY 4.0, 12 Scorer, Nicht-BIDS) für κ und
Konvertierung. Download über versionierte URLs mit SHA-256, nicht im Repository. Die CI nutzt synthetische
Fixtures; öffentliche Daten in einem eigenen, gecachten Job; die 1-GB-EDF wird erzeugt. EEGDash nur als
Entwicklungswerkzeug (zieht torch nach).

**A-30 NeuroVault.** Ablage im Datensatz unter einem versteckten NeuroGrid-Ordner (Pfad in der toml
änderbar): Einwilligungen, `roles.yaml`, `risks.yaml`, `access.jsonl`, Folgenabschätzung. v0.2 = NV-F01–F03
inkl. `vault verify`; v1.0 = NV-F04–F07. Ist ein Vault vorhanden, schreiben check, convert, report und export
automatisch Zugriffsereignisse; die Rolle kommt aus `--role` oder der toml. Rollen werden nicht technisch
erzwungen (keine Identitätsverwaltung), Verstöße gegen das Rollenregister werden Befunde. Keine eigene
Verschlüsselung; Datenträgerverschlüsselung ist manueller Nachweis. Hashkette über kanonisches JSON,
Startwert 64 × „0“, Zeit in UTC; der letzte Hash steht in Bericht und Export (ein abgeschnittenes Ende ist
ohne externen Anker nicht erkennbar – dokumentiert). Fristerinnerung: Warnung bei jedem Befehl, wenn die
Aufbewahrungsfrist in höchstens 90 Tagen endet. Folgenabschätzung als Vorlage zh/en entlang PIPL Art. 55/56,
gekennzeichnet „keine Rechtsberatung, juristisch prüfen“. Neueinwilligung: Probanden mit Einwilligung vor
dem Risikodatum, deren erlaubte Nutzungen das Risiko betrifft, ohne Widerruf. M14: Split → Nutzung
konfigurierbar (train → training, val/test → validierung), weitere Zwecke auf Datensatzebene; Widerruf oder
fehlende Einwilligung = Fehler. Das Export-ZIP enthält nur die fünf Bestandteile aus NV-F07, nie Signale.

**A-31 Befehle.** Die Befehle aus §13 bleiben; Zusätze nur, wo die PRD sie selbst nennt oder voraussetzt:
`check --strict`, `check --manifest`, `check --evidence`, `vault verify`, `report --out`, `scan --out`.

**A-32 GB/T 47127 in v0.2.** §20 zählt GB/T 47127 zur normunabhängigen v0.1, §6 und NG-F03 legen es auf
v0.2; es gilt das Spezifischere (v0.2).

**A-33 Versionsvergleich.** Schlüssel = Regel-ID + Objekt; „verändert“ = gleicher Schlüssel, anderer
Status oder Messwert.

**A-34 CI-Integration (v1.0).** Wiederverwendbare GitHub Action und GitLab-CI-Vorlage samt Doku; nutzen
Exitcodes, JSON und `diff` gegen einen Referenzlauf.

**A-35 PDF-Nachweismappe (v1.0).** Ein PDF mit Deckblatt, Bericht zh und en, Nachweisliste mit
SHA-256 der Dokumente, Manifest-Zusammenfassung und NeuroVault-Zusammenfassung; nie Signale.

**A-36 NG-F17 (falls im Umfang).** Ordner `research/` außerhalb des Pakets, eigene Abhängigkeitsgruppe
(moabb, braindecode, torch). Datensätze mit klarer Lizenz: Zhou2016 (CC0), PhysionetMI (ODC-By),
Kalunga2016 (CC BY 4.0). Die „Qualitätsstufe“ definiert die PRD nicht; Vorschlag kommt in Phase 2.

**A-37 Gates.** G1–G4 sind Geschäftsentscheidungen des Auftraggebers. Software-Phasen halten nur an
Go/No-Go-Punkten, von denen sie technisch abhängen (Normtexte).

**A-38 Urheber.** LICENSE/NOTICE und `pyproject.toml` nennen „Ammar Ahad“ (Absender laut PRD §18),
bis der Auftraggeber etwas anderes sagt (F7).

**A-39 Paketname.** PyPI-Distribution `neurogrid` (frei, Stand 11.10.2026); Befehl `neurogrid`.

**A-40 gxdsl008 ohne Normtext.** Regeln aus den fünf PRD-Startwerten; Klausel „unbekannt (Normtext nicht
zugänglich)“. Schweregrad warnung für alle fünf (die PRD nennt für Abtastrate und Impedanz ausdrücklich
Warnung, für die übrigen nichts). Format-Regel prüft das Speicherformat der Aufnahmen (EDF/HDF5);
AES-256/rollenbasierter Zugriff = manuelle Regel; Prüfsummen = halbautomatisch über das Manifest.

**A-41 yyt2029 ohne Normtext.** Nur Paketgerüst `0.2.0-draft` mit der PRD-Beispielregel, als Platzhalter
markiert. Keine erfundenen Regeln; das Inventar entsteht erst mit dem Normtext.

**A-42 Python-Versionen.** 3.11–3.13 laut NG-N04 (uv löst numpy/scipy je Version passend auf);
Entwicklung mit 3.12. Hängt an F5.

**A-43 Board-ID.** Jeder Commit und jeder Eintrag in FORTSCHRITT.md nennt die Anforderungs-IDs.
