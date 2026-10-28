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
- Die Linux-Wheels von numpy und scipy bündeln libgfortran (GPL mit GCC-Laufzeitausnahme) und libquadmath (LGPL); die Windows-Wheels nicht. Das gilt für jede Installation mit MNE. (Berichtigt durch A-86: Die Windows-Wheels linken die GCC-Laufzeit statisch in `libscipy_openblas*.dll`.)

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

## Vorabentscheidungen zu STOPP G1 (26.10.2026)

**D-15 G1-Vorabentscheidungen.** Der Projektverantwortliche hat vor STOPP G1 nach Empfehlung entschieden:
- **Downloads außerhalb von D-06 freigegeben** (nur Lizenztexte):
  - Rechtstext CC BY 4.0 nach `LICENSES/CC-BY-4.0.txt`, mit SHA-256 abgelegt.
  - Lizenzdateien der im bids-validator 3.0.2 gebündelten npm/jsr-Pakete (genaue Versionen aus der Source-Map), geprüft abgelegt.
- **Repository:** beim ersten Push öffentlich. Die Bündel-Tests laufen dann bei jedem Push auf `dev` und `main`.
- **PyPI:** Trusted Publishing (OIDC, kein gespeichertes Token); zuerst TestPyPI, dann PyPI; jede Veröffentlichung startet der Projektverantwortliche.
- **Gitee:** Spiegel über die vorbereitete GitHub Action per SSH (Secret `GITEE_SSH_KEY`, gepinnter Host-Schlüssel); Gitee-Release mit Wheel, sdist, `SHA256SUMS`, Signatur und Verweis auf das GitHub-Release.
- **Dokumentation:** für v0.1 im Offline-Bündel und als Release-Artefakt; das Hosting wird nach v0.1 entschieden.
- **Signatur (Lesart von D-10 g):** Das Installationsskript prüft immer `SHA256SUMS`; die Sigstore-Signatur prüft es, wenn cosign vorhanden ist, sonst bricht es ab, außer mit dem ausdrücklichen Schalter `-SkipSignatureCheck`/`--skip-signature-check`. Die Dokumentation beschreibt die Prüfung vor der Übertragung auf einem vernetzten Rechner.
- **Kleine Zellen (A-81):** Die Tabellenregel und ihr Preis sind angenommen (Datenschutz vor Vollständigkeit).
- **DM-02:** Diagnoseähnliche Spalten dürfen Labelquelle von M11 sein, nur aggregiert nach der Tabellenregel.
- **Arbeitsweise ab sofort (Tempo):** volle Testsuite nur nach dem Merge; Agenten auf Stufe high, xhigh nur für Prüfungen zu Datenschutz und Regulatorik; ein Review je Phase mit vier Prüfrichtungen; das Nachbau-Dokument entsteht parallel; P6 wird vor G1 spezifiziert (ohne Commit).
- **Bei G1 offen:** muttersprachliche zh-Prüfung, Push-Freigabe mit Repo-URL und die Bestätigung der übrigen vorgemerkten Annahmen.
- **Repository-URL** (26.10.2026): `https://github.com/Ammxri/neurogrid`; seither wird nach D-09 nur `dev` gepusht.

**D-16 Lizenzen im mitgelieferten BIDS-Validator (26.10.2026).** Befund: bids-validator-deno 3.0.2 enthält in
`isomorphic-git` 1.41.9 eine aus `@zenfs/core/path` kopierte Funktion `path.join` (rund 90 Zeilen) unter
LGPL-3.0-or-later. Jede Version ohne diesen Abschnitt (bis 2.2.1) erfüllt die Pins nicht (BIDS 1.11.1, Schema 1.2.7,
Aufruf nach A-06). Entscheidung nach Empfehlung:
- **Versionsgebundene Ausnahme zu D-05** nur für diesen Abschnitt in bids-validator-deno 3.0.2 (Muster D-08): Die Texte
  LGPL-3.0 und GPL-3.0 werden einmalig geladen (Download freigegeben) und mitgeliefert; die Notices nennen Bauteil,
  Lizenz, Urheber und Fundstelle; der Quelltext liegt lesbar im Wheel und im Bündel. Jede andere Version des
  Validators braucht eine neue Prüfung.
- **Anfrage an die Entwickler** des Validators, den Abschnitt zu ersetzen: NeuroGrid entwirft den Text, der
  Projektverantwortliche sendet ihn.
- **Lizenzpolitik für gebündelte Teile:** Public Domain gilt als freizügig; bei einer Wahl-Lizenz mit mindestens einer
  freizügigen Option (z. B. „CC0-1.0 oder OpenSSL oder Apache-2.0“) gilt die freizügige Wahl, und NeuroGrid nennt sie.

## Entscheidungen zu STOPP G1 (27.10.2026)

**D-17 G1-Entscheidungen zu Lizenztexten, P6 und zh-Prüfung.** Der Projektverantwortliche hat nach Empfehlung
entschieden:
- **Lizenztexte der acht G1-Lücken (Release-Sperre):** Den Download aus den offiziellen Projektquellen hat der
  Projektverantwortliche erst nach Vorlage einer URL-Liste freigegeben; die Liste (acht Einträge von
  `license-gate/known_missing.toml`, 70 URLs) wurde vorgelegt und freigegeben. Im Einzelnen:
  - **Downloads außerhalb von D-06 freigegeben** (nur Lizenztexte): genau die Dateien der Liste, dazu das npm-Tarball von
    `@jspm/core` 2.1.0 für die byte-gleiche LICENSE mit CRLF. Jede Datei einmal, mit URL, Größe, SHA-256 und Abrufdatum in
    den Manifesten von `license-gate/third_party/`; Standardtexte zusätzlich in `license-gate/licence_texts.toml`.
  - **Wahlen:**
    1. python-build-standalone: die eigenen `LICENSE.*.txt` am Tag 20261009, dazu die Projektdateien für das, was sie
       nicht abdecken (itcl 4.3.8, Tcl thread 3.0.6, HACL\*, unter Windows expat 2.8.5 und libmpdec 2.5.1 aus
       `Doc/license.rst` von CPython v3.12.15); nicht die versionsgenauen Upstream-Alternativen der Liste.
    2. focus-visible: Volltext der W3C Software and Document License; keine erfundene Copyright-Zeile. Die Notices sagen
       wörtlich, dass das Projekt keine nennt, und verweisen auf sein Repository als Herkunft.
    3. `@jspm/core`: die Versionen der gebündelten Pakete aus dem Lockfile von jspm-core, im Manifest offen als „nur
       über Lockfile belegt“ gekennzeichnet. Die Zusammenfassung der Liste nennt 34 Pakete, ihre Tabelle 33 neben
       `@jspm/core` selbst (dessen Version aus `deno.lock` folgt); abgelegt sind die Texte aller 33.
    4. Brumme (hash-wasm): der Lizenzabschnitt der HTML-Seite als Auszug, mit Abrufdatum sowie Größe und SHA-256 der
       Seite.
    5. unicode-name: zusätzlich die Unicode License V3 (`unicode.org/license.txt`).
  - **Auszüge:** Ein Text, der aus einer nicht abgelegten Datei geschnitten ist (Art `document excerpt` oder
    `source header`), nennt diese Datei mit `source_size` und `source_sha256`. `tools/notices.py --check` prüft Art und
    Felder; `tools/notices.py --sources DIR` prüft die Quellen gegen eine lokale Kopie (Größe, SHA-256, Herkunft des
    Textes).
  - **Ergebnis:** 70 Downloads, 70 abgelegte Texte (bids-validator 3.0.2: 45, h5py 3.16.0: 1, mkdocs-material 9.7.7: 3,
    python-build-standalone 3.12.15+20261009: 21); zwei davon (Unicode-3.0, W3C-20150513) stehen auch in
    `licence_texts.toml`. Nicht abgelegt: das Tarball (nur seine LICENSE), die LF-LICENSE von jspm-core auf GitHub
    (nur zum Vergleich), die Brumme-Seite, `Doc/license.rst` und `Hacl_Hash_SHA2.c` (nur ihre Auszüge). Alle Lizenzen
    sind freizügig nach D-05/D-16; `known_missing.toml` ist leer, `tools/notices.py --check` endet mit 0.
  - **Bei G1 offen:** die muttersprachliche zh-Prüfung (A-07) schließt den geänderten Satz in `docs/zh/license.md` ein.
- **M14 (P6), Befunde pro Person:** Option B. Pro Person nur in results.json (bleibt beim Team; nötig für Ausnahmen und
  die Korrektur der Splits); Bericht, Export (P9) und Dossier zeigen M14 nur zusammengefasst je Nutzung und Grund,
  ohne Personen-IDs und ohne Versionsnummern der Einwilligung, nach der Tabellenregel von A-81.
- **zh-Texte von P6:** Option C. Bei G1 werden nur die Kernbegriffe geprüft (die fünf Nutzungsarten, Einwilligung und
  Widerruf, Zugriffsprotokoll, Hash-Kette, Platzhalter-Regelpaket, der Grenzsatz und die V-06-Aussage); die
  vollständigen P6-Texte bekommen eine eigene Runde vor dem v0.2-Release.
- **zh-Prüfpaket v0.1:** wird nach dem Merge der zweiten CI-Fix-Runde erstellt; die Prüfperson stellt der
  Projektverantwortliche.

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

**A-26 Installation ohne Internet und PDF.** Präzisiert durch A-85 und A-87 (P5).
- **Offline-Bündel je Plattform:** uv-Binary, python-build-standalone 3.12, cp312-Wheelhouse aus `uv.lock`, Dokumentation, Notices, `SHA256SUMS`. Das Installationsskript legt eine venv an (Bytecode vorkompiliert) und setzt beschreibbare Orte für `DENO_DIR` und den Browser.
- **Headless Shell:** gemäß E1 (Empfehlung: nicht im Bündel; `neurogrid` liefert ein Installationsskript, das online von Playwright lädt oder offline eine vom Kunden bereitgestellte zip mit geprüfter Prüfsumme einspielt). Kein Edge-Rückfall. Ohne Headless Shell endet `--format pdf` mit Exit 2 und Hinweis; HTML geht immer.
- **Vor dem PDF-Druck:** Startprüfung; fehlen Linux-Bibliotheken, folgt Exit 2 mit Paketliste.
- **Plattformen:** Windows 10 und andere Linux-Distributionen als Debian 12/Ubuntu 22.04+: „nicht verifiziert“.
- **Verteilung:** GitHub Releases (bis 2 GiB je Datei); Gitee nach dessen Größengrenzen.

**A-27 Schrift.** Präzisiert durch A-85 (P5); den matplotlib-Punkt ersetzt das eigene SVG aus A-84.
- **Herstellung:** Die statischen Schnitte Noto Sans SC 400/700 erzeugt ein tools-Skript einmalig aus der Google-Fonts-VF. Radikal- und Kompatibilitäts-Codepunkte werden entfernt. Die Schnitte sind mit SHA-256 eingecheckt (≈ 2 × 10,6 MB); `OFL.txt` liegt daneben.
- **Laufzeit:** Subsetting per fontTools mit `recalcTimestamp=False`; die name-IDs 0, 13 und 14 bleiben erhalten.
- **matplotlib:** bindet die Schrift per `addfont` ein, nutzt `svg.fonttype='path'` und ein eigenes MPLCONFIGDIR.
- **Lizenzangaben:** Wheel-Metadaten `license = "Apache-2.0 AND OFL-1.1"`; die Lizenz je Pfad steht in `REUSE.toml`.

**A-28 Dokumentation.** Präzisiert durch A-86 (P5).
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

**A-49 Netzwerkschutz.** Ergänzt durch A-85 (asyncio-Schleife von Playwright, Loopback) und A-87 (Paketscan, Nachweis auf Betriebssystemebene) in P5.
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

**A-51 Datenschutz in allen Ausgaben (NG-N05).** Gilt für Konsole, Bericht, results.json, scan-JSON, diff, Nachweismappe, ZIP, Logs und PDF-Metadaten. Ergänzt in P5 („Übergreifend“: `<user>`, `<host>`, unbekannter Benutzerordner, Laufwerkswurzel; A-87: Installer; A-89: Hilfsprozesse von `--jobs` ohne Konsole).
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

**A-54 Temporäre Dateien.** Präzisiert in P5 („Übergreifend“: Lage, Sperrdatei, Reste, Modus der Ausgaben) und durch A-85: Der Arbeitsordner des PDF-Browsers mit dem Chromium-Profil liegt im temporären Ordner des Rechners, nicht unter `--out`.
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

**A-56 Lizenz-Hinweise.** Die Notices erzeugt seit P5 ein eigener statischer Leser statt pip-licenses (A-86).
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

**A-59 Skalierung der Befunde.** Präzisiert durch A-84 (kein CSV-Anhang) und A-88 (Grenzen des Skalierungstests).
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
version, source, license – die Felder von DM-01, soweit nicht aus `dataset_description.json` lesbar). Der Vorrang
folgt A-04 (präzisiert in P5, Review R09): name und license aus der toml gehen vor `Name`/`License` aus
`dataset_description.json`, die nur ein dort nicht gesetztes Feld füllen; id, version und source kommen nur aus dem
Abschnitt. Die Begründung für gemischte Abtastraten (M03, A-18) steht in `[metadata] mixed_sampling_rates_reason`.
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
Ebenso erlaubt sind dort reservierte Gerätenamen, Backslashes im Namen (`\x.edf`, `a\b.edf`) und
`/\…` (ein absoluter POSIX-Pfad). Abgelehnt wird aber ein eingetippter oder eingefügter Windows-Netz- oder
Gerätepfad, mit demselben Schlüssel wie unter Windows (`kernel.safety.operator_path_problem`): `//…` sowie ein
Backslash gefolgt von einem zweiten Trennzeichen (`\\server\share`, `\/server/share`) als `path.unc`, die Präfixe
`\\?\`, `\\.\` und `\??\` (auch mit Schrägstrichen gemischt) als `path.device`. Sonst würde ein solcher Pfad als
relativer Name gelesen (Eingabe nicht gefunden; mit `--out` eine Datei dieses Namens im Arbeitsordner).

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

**A-77 Formate, Metadaten, Validator und Konvertierung (Stand nach dem Review von P2; ergänzt in P5: „Übergreifend“, BrainVision unter Linux).**
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
- **Offline-Nachweis des Validators (NG-N01, A-49):** Der CI-Job `offline-strace` (Linux) führt `check` mit dem Paket `bids` und `convert` unter `strace -e trace=connect` aus und schlägt bei jedem `connect` mit AF_INET/AF_INET6 fehl. Er läuft erst nach einem Push (D-09). Geändert in P5 (A-87): Der Job steht in `offline.yml`; Loopback ist erlaubt, außer Port 9.
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

## Annahmen aus der Umsetzung von P5

Die folgenden Annahmen schließen Lücken, die PRD, Konzept und frühere Annahmen offenlassen (Freigabemodus A,
Vorgaben B1–B6). Eingearbeitet sind die Integration, das Review von P5, die Fix-Runde, die zweite CI-Fix-Runde
(p5-ci2) und der G1-Befund auf dcec9bd (A-89). Sie sind für STOPP G1 vorgemerkt (A-84 bis A-89). Der Entwurf der
P6-Vorgaben hatte A-89 bis A-91 vorläufig vergeben (Code, Tests und Texte von P6 sollen dafür die Token `A-P6V`,
`A-P6C`, `A-P6Y` tragen; im Repository steht noch keiner); A-89 ist jetzt der G1-Befund, die Annahmen von P6 beginnen
bei A-90.

**Übergreifend (gilt für A-84 bis A-88).**
- **Version:** `0.1.0rc1`; `0.1.0` und der Tag `v0.1.0` erst nach STOPP G1.
- **Review von P5:** vier Prüfrichtungen, 30 Befunde (R00–R29), 29 bestätigt, R12 strittig und als dokumentierte Grenze entschieden (A-87). Behoben sind alle; R08 und R09, zwei Abweichungen der Nutzerdoku, in der zweiten CI-Fix-Runde (p5-ci2-userdocs, Merge d4f3214; A-86). Auf 181654e nannten die Datenschutz- und Berichtsseiten nicht, dass `document`, `reviewer`, `comment` und `justification` aus evidence.yaml im Klartext erscheinen (A-83), und `configuration.md` drehte den Vorrang von `[dataset]` um (es gilt die toml vor `dataset_description.json`, A-04; A-63 begründet nur, warum es den Abschnitt gibt).
- **Zweite CI-Fix-Runde (p5-ci2):** behebt die roten Testjobs von `ci` auf 55335ca in fünf Bereichen (Merges b2b5246 chrome-log, 18d1750 win-runner, a4196e2 linux-p2, d4f3214 userdocs, df1c790 linux-pdf; dazu D-17 mit 9d8afcb und die Doku mit dcec9bd). Die Verhaltensänderungen stehen in den Bereichen: Regel-IDs im Bericht (A-84), Startflags, debug.log und QA-Gate des PDF (A-85), Nutzerdoku (A-86), Installer (A-87), BrainVision unter Linux (nächster Punkt). Ergebnis: CI auf dcec9bd ganz grün (A-87).
- **BrainVision unter Linux** (zweite CI-Fix-Runde, ergänzt A-77; TECH-05):
  - MNE 1.13.2 liest die Markerdatei ein zweites Mal im Textmodus ohne Kodierung, um das Aufnahmedatum zu finden (`_get_hdr_info`); Python nimmt dafür die Kodierung des Locale (Linux UTF-8, Windows die ANSI-Codepage). NeuroGrid lässt genau diesen Lesevorgang als Latin-1 dekodieren (`io.brainvision.mne_reading_without_locale`, `MNE_MARKER_DATE_CODEC`); jeder Aufruf von MNE für BrainVision geht über `io.brainvision.mne_read_raw_brainvision` (`read_check`, `convert`, Qualitätssignale; ein AST-Test erzwingt das), `convert` hält den Kontext auch, während MNE-BIDS schreibt (es liest eine kopierte Aufnahme noch einmal). MNEs eigene Dekodierung der Marker nach Codepage bleibt. Vorher waren Markerdateien in Latin-1/ANSI unter Linux, mit chinesischem Text in UTF-8 oder GBK unter einem westlichen Windows und in Latin-1 unter einem chinesischen Windows nicht lesbar bzw. nicht konvertierbar.
  - MNE-BIDS nimmt die Codepage des Kopfs als Python-Codec, um Kopf und Markerdatei zu kopieren; `ANSI` (jede Schreibweise) kennt Python nur unter Windows (`mbcs`). `convert._copy_codec` gibt MNE-BIDS dafür überall Latin-1, das jedes Byte auf sich abbildet: ANSI-Aufnahmen werden auch unter Linux kopiert (vorher aus den geladenen Daten als float32 mit `Codepage=UTF-8` neu geschrieben), unter Windows unabhängig von der Systemcodepage.
  - Beide Ersetzungen halten `io.base.ModulePatch` (Sperre plus Zähler der Halter): Der erste Halter in einem beliebigen Thread setzt sie, der letzte stellt das Modul wieder her; Blöcke dürfen sich verschachteln und in mehreren Threads in beliebiger Reihenfolge enden. Andere Aufrufer desselben Moduls sehen die Ersetzung, solange sie gehalten wird; ein Modul, das nicht mehr wie erwartet aussieht, ergibt RuntimeError.
  - Ein Backslash in einem Verweis aus einer Datendatei trennt auf jedem System Ordner (`kernel.safety.check_relative`, unverändert seit A-52): Unter POSIX öffnete MNE einen Dateinamen mit Backslash im Datensatz, NeuroGrid meldet überall `companion.unsafe_reference`. Der Test, der MNE dem Ordnerlink folgen lässt, läuft nur unter Windows; ein POSIX-Gegenstück hält das Linux-Verhalten fest.
  - Bekannte Grenzen: Die Ausgabe von `convert` ist zwischen den Betriebssystemen nicht bytegleich, weil MNE-BIDS und pybv Textdateien (participants.*, channels.tsv, events.*, scans.tsv, kopierter oder geschriebener .vhdr/.vmrk) mit `os.linesep` schreiben (unter Windows CRLF); damit unterscheidet sich auch `output_hash` in `.neurogrid/processing_steps.json`. Codepage-Werte, die Python nur unter Windows auflöst (`mbcs`, `dbcs`, `oem`; keine BrainVision-Standardwerte, diese sind UTF-8 und ANSI), bleiben plattformabhängig: unter Windows die Systemcodepage, unter Linux LookupError. Der Linux-Teil ist in der CI geprüft (dcec9bd grün), lokal nur nachgestellt (Locale und Codec-Register im Prozess, `PYTHONUTF8=1`).
- **Ausgaben** (präzisiert A-54, KONZEPT 2.8): Jede Ausgabe (results.json, scan-Inventar, Manifest, Berichte, Zuordnungsvorlage) entsteht als temporäre Datei mit Modus `0666` abzüglich umask (`kernel.safety.create_temporary`; vorher wie `mkstemp` immer `0600`) und wird dann umbenannt. Unter Linux folgen die Dateien der umask des Bedieners; unter Windows ändert sich nichts.
- **Arbeitsordner** (präzisiert A-54):
  - `check` legt `run-XXXXXXXX` neben results.json an, `convert` neben dem Ausgabeordner, der PDF-Druck `ng-pdf-XXXXXXXX` im temporären Ordner des Rechners (A-85).
  - Bibliotheksaufrufe ohne Ausgabeordner (`run_check`, `run_convert`, `convert_to_bids` ohne Arbeitsordner; die CLI arbeitet immer neben ihrer Ausgabe): Windows `<temp>/neurogrid`, Linux `<temp>/neurogrid-<uid>` mit `0700` (`kernel.safety.temp_work_base`). Ist der Linux-Ordner ein Link, gehört er einem anderen Benutzer oder dürfen Gruppe oder andere schreiben: `output.not_writable` (Exit 2).
  - Jeder Arbeitsordner enthält `neurogrid-work.lock` mit der Marke „NeuroGrid work folder“; der Lauf hält die Datei gesperrt (msvcrt bzw. `fcntl.flock`). Gelöscht wird im `finally` (Inhalt zuerst, Sperrdatei zuletzt) und beim nächsten Start in derselben Basis (`run-*` beim nächsten Lauf dort, `ng-pdf-*` beim nächsten PDF-Druck), aber nur ein Ordner mit Marke und ohne Sperre. Ordner laufender Läufe, Ordner ohne Sperrdatei (auch Reste älterer Versionen), Links und die eigenen Ordner bleiben stehen. Die Sperrdatei liegt im Ordner, weil A-82 nur den Arbeitsordner vom Manifestvergleich ausnimmt.
- **Konsole** (ergänzt A-51):
  - Neben `<dataset>` und `~` erscheinen Anmelde- und Rechnername als `<user>` und `<host>`. Quellen: `USERNAME`, getpass und der POSIX-passwd-Eintrag; `COMPUTERNAME` und `os.uname().nodename` mit und ohne Domäne (keine Socket-API außerhalb von netguard). Ersetzt wird als ganzes Wort (kein ASCII-Buchstabe oder -Ziffer daneben), ohne Groß-/Kleinschreibung und nur in Pfaden des Rechners (absolut oder mit `~`, bis Anführungszeichen, Zeilenende oder Kennzeichnung), nie in einer Kennzeichnung und nie in Namen relativ zum Datensatz. Namen unter 3 Zeichen und „neurogrid“ bleiben stehen (dieselbe Grenze wie die G1-Prüfung). Grund: Unter Linux liegt `/tmp` außerhalb des Benutzerordners (CI: `/tmp/pytest-of-<user>/…`), ebenso USB-Sticks (`/media/<user>/…`).
  - Ist der Benutzerordner nicht bestimmbar (Linux ohne `HOME` und ohne passwd-Eintrag) oder die Wurzel des Dateisystems (`HOME=/` in Containern), wird nichts als `~` gezeigt und der Lauf geht weiter (`kernel.safety.home_folder`). Vorher folgte auf die geschriebene Ausgabe „Internal error (RuntimeError)“ mit Exit 2.
  - Eine Laufwerkswurzel als Datensatzwurzel (`E:\`) wird zu `<dataset>\…`, aber nur als eigenes Wort mit folgendem Trennzeichen („Size: 3 MB“ bleibt). Vorher wurde sie nie ersetzt, auch nicht im `--debug`-Traceback.
  - Der Hinweis zur PDF-Installation behält Anmelde- und Rechnernamen, weil er ein Befehl ist, der so läuft, wie er gedruckt ist (A-85).
- **Pfade unter Linux:** A-67 nennt seit der Fix-Runde die POSIX-Regeln (`kernel.safety.operator_path_problem`). Zu A-66: Unter Linux nennt `.\.neurogrid\lab.yaml` eine andere Datei (der Backslash ist ein Namenszeichen) und ergibt `rulepack.not_found`; der Lader ist unverändert. Nicht dekodierbare Dateinamen (Byte 0x80) nehmen unter Linux denselben Weg über das Surrogat-Escape wie unter Windows.
- **Unterprozesse:** Jeder Aufruf im Textmodus in `src/neurogrid` nennt seine Kodierung (statischer Test; ruff PLW1514 deckt nur `open()` ab). Anlass: `ldd` ohne Kodierung löste unter `PYTHONWARNDEFAULTENCODING=1` eine EncodingWarning aus, die `filterwarnings = ["error::EncodingWarning:neurogrid"]` zum Fehler macht.
- **Wortwahl ARC-05** (ergänzt A-57): `report/wording/statements.yaml` mit den Gruppen `patient` (keine Aussage über Patienten, Diagnosen oder Klinik; Kopffeldnamen sind in den Mustern ausgenommen, z. B. de `(?i)\bPatient(?!enfeld|\s+field)`) und `law_article`. Jedes Muster gilt für jeden Text, gleich welcher Sprache; erlaubt sind genau die drei Verneinungen des Geltungshinweises. Die Patientenprüfung durchsucht Sprachtabellen zh/en/de, Regeltitel, Validator-Texte, Vorlagen, `docs/` ohne `docs/umsetzung`, `mkdocs.yml`, README, `packaging/` und `tools/install_pdf_browser.py`; Gesetzesartikel werden nur in NeuroGrids eigenen Texten gesucht (A-57).
- **Fester Satz:** Jede Kopie (`README.bundle.txt`, `release-notes.md`, `gitee-release.md`, `install.ps1`, `install.sh`) muss `disclaimer` der Sprachtabellen gleichen (Test).
- **`.env.example`** nennt jede Variable ohne Wert: `NEUROGRID_LANG`, `NEUROGRID_PDF_BROWSER_DIR`, `NEUROGRID_REQUIRE_PDF`, `NEUROGRID_NOTICES_WHEELS`, `UV`, `NEUROGRID_BUNDLE_CACHE`, `NEUROGRID_RELEASE_REPOSITORY`, `SOURCE_DATE_EPOCH`, `GITEE_MIRROR`, `GITEE_REPOSITORY`, `GITEE_KNOWN_HOSTS`, `GITEE_SSH_KEY` (nur als Secret), `PYPI_API_TOKEN` (nur, falls Trusted Publishing abgelehnt wird). `tests/packaging/test_env_example.py` vergleicht sie mit den Namen aus Code, Werkzeugen, Tests, Workflows und Paketskripten (auch Zuweisungen vor einem Befehl); System-, CI- und Fremdvariablen stehen dort in geprüften Listen.
- **Systemsprache unter Linux** (bekannte Grenze, zu A-07): `detect_language` nutzt `locale.getlocale()`, also LC_CTYPE (LC_ALL > LC_CTYPE > LANG); `LC_MESSAGES` und GNU `LANGUAGE` zählen nicht.
- **Abweichungen von KONZEPT 1.2, 1.3 und 1.6:** `license-gate/` statt `licenses/`; `THIRD_PARTY_NOTICES.txt` statt `.md`; Workflows `ci.yml`, `offline.yml`, `corpus.yml`, `docs.yml`, `release.yml`, `publish-pypi.yml`, `mirror-gitee.yml` (kein `bundle-test.yml`); `tools/` zusätzlich `gen_docs.py`, `build_docs.py`, `mkdocs_hooks.py`, `docs_templates/`; `mkdocs.yml` im Wurzelordner; `safety.py` und der Audit-Hook `netguard.py` liegen unter `kernel/` (KONZEPT 1.2 nannte `src/neurogrid/safety.py`); Kernimport pypdf, die Datumsfelder setzt NeuroGrid ohne pypdf (A-85); kein matplotlib im Bericht (A-84); MkDocs-Werkzeuge in einer eigenen Gruppe `docs` (A-86). KONZEPT 1.2, 1.3 und 1.6 sind entsprechend nachgetragen.

**A-84 Bericht** (präzisiert A-08, A-09, A-10, A-13, A-59; weicht bei den Diagrammen von KONZEPT 1.3 und A-27 ab).
- **Seiten:** A4; Deckblatt und Zusammenfassung hoch, Abschnitte 3–6 quer (benannte Seite `wide`); Ränder 16/13/20/13 mm. Das Deckblatt steht allein, die Abschnitte 4, 5 und 6 beginnen auf einer neuen Seite.
  - Kopfzeile links „NeuroGrid 预检报告 · 基准日期 <as_of>“ bzw. „NeuroGrid pre-check report · reference date <as_of>“; fester Satz unten links (80 % Breite) auf jeder Seite; unten rechts „第 x 页 / 共 y 页“ bzw. „Page x / y“.
  - Tabellenköpfe wiederholen sich, Zeilen werden nie geteilt.
  - Eine Schriftfamilie „NG Sans“ für alles (auch jede Randbox, `pre` und Code), `font-synthesis: none`, keine Kursive; die Festbreiten-Optik kommt nur aus dem Zeichenabstand. Die wirksamen Einstellungen (JSON) stehen dreispaltig.
  - Die Randboxen sind Chromium-spezifisch: Maßgebliche Seitenausgabe ist das PDF.
- **Kopf des HTML:** `<title>` = `report.title` (zh „NeuroGrid 预检报告“, en „NeuroGrid pre-check report“, unverändert seit P1; der Gedankenstrich im Beispiel von B2 entfällt), ohne Datensatznamen und Pfad; `<meta name="description">` = fester Satz.
- **Breite** (Review R01, R04): Nichts darf breiter sein als die Seite, sonst verkleinert Chromium jede Seite des Drucks (gemessen: auf 2/3, Werte abgeschnitten).
  - `overflow-wrap: anywhere` am body, von jeder Zelle geerbt.
  - In Tabellen mit automatischem Layout bleiben jeder Kopf, die Beschriftungen der Schlüssel/Wert-Tabellen und die eigenen Wörter der Klasse `td.own` (Quellstatus, Phase, Ampel, Abdeckung, Herkunft, Ausnahme verwendet/abgelaufen) auf einer Zeile. Wie Text umbrechen nur Köpfe mit Datensatzwerten (`th.value`, KI-Bereiche) und die Köpfe der fünf Tabellen mit festem Layout.
  - Feste Spaltenanteile, je Tabelle 100 %; Befunde: Regel 12, Klausel 6,5, Titel 12, Status 7, Datei 11, Kanal 6, Messwert 8, Schwelle 10, Zeit 11,5, Grund 16. Jedes eigene Wort passt in zh und en in seine Spalte; umbrechen dürfen nur Datensatzwerte und BIDS-Feldnamen als Beschriftung (`EEGChannelCount`).
  - Das QA-Gate prüft die Verkleinerung nicht, denn ein Datensatzwert darf nie Exit 2 auslösen; Tests lesen die Skalierung der Seiteninhalte (3,125 auf jeder Seite).
  - Regel-IDs brechen nie um (zweite CI-Fix-Runde): außer in der Regelspalte (`td.c-rule`) steht jede Regel-ID in einem Element, das nicht umbricht (`<span class="nowrap">`, in der Parametertabelle `td.mono.nowrap`), auch im Fließtext: Gruppenüberschriften, Querverweise in Titelzellen, Restsatz, Schwellennotizen der Diagramme, Nachweistabelle, Ausnahmen und Hinweise geladener Regeln. Gemessen unter Windows: Der zh-Querverweis „CORE-M05-“ | „02“ einer Titelzelle brach vorher am Bindestrich. In übersetzte Sätze kommt eine Regel-ID über einen Steuerzeichen-Platzhalter (`render.RULE_SLOT`); der Text daneben wird vorher glyphensicher gemacht, so kann Datensatztext keinen Platzhalter fälschen. Eine Regel-ID, die kein geladenes Paket kennt (Text des Nutzers), bricht weiter um und kann die Seite nicht verbreitern.
- **Befunde** (Abschnitt 3; A-59 gelesen als „vollständig nur im JSON“, ändert A-59):
  - Gruppen nach Schweregrad, dann Regel (ID aufsteigend); Zeilen nach Status (failed > evidence_open > not_checkable > excepted > not_applicable > passed), Objekt, Unterschlüssel.
  - Je Regel eine Sammelzeile („N Befund(e) an K Objekt(en); gemessen MIN bis MAX; Status: Anzahl“).
  - Höchstens 50 Zeilen je Regel (`MAX_ROWS_PER_RULE`); darüber nennt `report.text.rule_more` den genauen Rest und die vollständige Liste in results.json (`findings` mit `rule_id`). Kein CSV-Anhang, kein neues Ausgabeformat. Für G1 vorgemerkt: diese Lesart von „Jeder Befund“ (NG-F13).
  - Überschriften der Schweregrade (Review R05, REP-03): Anzahl der Befunde und davon die in der Zusammenfassung gezählten (nicht bestanden plus Nachweis offen), z. B. en „Error: N finding(s), C of them counted in the summary (F not passed, O evidence open)“; ohne Gezählte „…, none of them counted in the summary“ ohne Statuswörter; Hinweise „not counted in the summary“ (`report.text.severity_heading*`). Für G1 vorgemerkt (Wortlaut).
- **Leere Zellen** (B1, präzisiert A-09):
  - `render.EXPLAINED_EMPTY` nennt die zwölf Schlüssel `report.value.*` für leere Zellen; Tests und `tools/acceptance_g1.py` importieren das Tupel. `render.FINDING_CELLS` = rule, clause, title, status, file, channel, measured, threshold, time, reason (Klasse `c-<name>`, die Kanalspalte ist neu); jede Zeile trägt `data-key` = Befundschlüssel.
  - Messwert None (auch leere Liste oder leerer Text): bei evidence/evidence_open/passed `not_applicable_value`, bei not_checkable/not_applicable `measured_see_reason`, sonst `measured_presence`.
  - Schwelle: die wirksamen Parameter als „Name = Wert (Herkunft)“, auch ohne Messwert (A-13); der Schwellwert steht eigens nur, wenn er von jedem Parameterwert abweicht; `no_threshold` nur, wenn die Regel keins von beiden hat.
  - Datei None: „Datensatz (datensatzweite Prüfung)“. Zeit: höchstens 20 Bereiche, dann Anzahl und Gesamtdauer (A-10); datensatzweit `time_dataset`.
- **Glyphen:** C0/C1-Steuerzeichen und DEL außer Tab, LF und CR, einzelne Surrogate und Zeichen, die eine der beiden Berichtsschriften nicht hat, erscheinen als sichtbarer Text `[U+XXXX]`. Es gibt einen Ersetzungsweg (`report.glyphs.glyph_safe`): für jeden Vorlagenausdruck über den neuen Parameter `finalize` von `kernel.report.render_html` und noch einmal über das ganze Dokument (A-85); beide Durchgänge sind idempotent.
- **Diagramme** (REP-04; Abweichung vom matplotlib-Eintrag in KONZEPT 1.3 und A-27): eigenes, deterministisches Inline-SVG (`report/charts.py`, nur Standardbibliothek); matplotlib bleibt nur Abhängigkeit von MNE.
  - Gemessene Gründe: matplotlib-Import 5,8 s kalt und 1,8 s warm, Schriftcache in MPLCONFIGDIR, 18 KB je Diagramm, Text nur als Pfade (nicht durchsuchbar, nicht im PDF-Text), gleiche Bytes nur mit `svg.hashsalt` und `metadata Date None`. Das eigene SVG: etwa 2–3 KB, bytegleich, Text in der eingebetteten Schrift; nur `rect`, `line` und `text`.
  - Histogramm 300 × 150, 20 gleiche Klassen, Werte außerhalb in der ersten bzw. letzten Klasse. Bereiche: [0, 1] für Anteile, [−1, 1] für κ, für M07 [0, m · 10^k] mit m ∈ {1; 2; 2,5; 5}, mindestens max(2 · Schwelle, größter Wert). Je Regel der Prüfung (ohne Platzhalter-Pakete) eine gestrichelte Linie aus `config.effective_params`.
  - Ein Wert je Aufnahme: M06, M09a, M09b; M07 größtes Verhältnis und M08 größter Flach- bzw. Übersteuerungsanteil über die Kanäle; M10 κ-Mittel. Das κ-Diagramm erscheint nur, wenn eine Aufnahme κ hat; jede andere Metrik ohne Werte ergibt die Zeile „TITEL: keine Messwerte“. Die Bildunterschrift ist HTML-Text: n Aufnahmen, nicht gemessen, nicht bestanden, Schwelle mit Herkunft.
  - Überlauf (Review R03): Der Bereich nutzt nur endliche Grenzen (eine verdoppelte Schwelle, die nach unendlich überläuft, zählt nicht); `nice_ceiling` liefert nie unendlich; eine nicht darstellbare Position fällt in die letzte Klasse. Vorher brach `report` mit `OverflowError` ab (Exit 2, auch für `--format html`).
- **Zusammenfassung und Deckblatt:** Summenzeile (`summary.errors`, `warnings`, `open_evidence`) und ein Hinweis, was „n/a“ beim Abdeckungsmaß heißt; drei Gesamtsätze (besteht / besteht die Fehlerprüfungen, N Warnungen bleiben / besteht nicht alle Prüfungen: N Fehler, M Warnungen). Deckblatt „Datum (Stichtag)“; fehlen Name, Version, Lizenz oder Manifest-Hash, steht „– (Grund)“. Geltungshinweis (ARC-05) auf Deckblatt und im Anhang; Hinweis zu den core-Klauseln auf `docs/<lang>/metrics.md` (A-02; de verweist auf docs/en).
- **Metriktabelle** (Abschnitt 4): Aufnahme, Format (+ „nicht blockweise lesbar“), Rate, Dauer, Kanäle „alle (EEG)“, Netzfrequenz „50 (Sidecar)“, M06, M07 max, M07 nicht bestandene Kanäle „k / n“, M08 „flach / übersteuert“ max, M09a, M09b, M10 κ-Mittel, M10 Abdeckung min; Anteile mit drei Nachkommastellen. „ *“ markiert einen Wert, wenn eine Regel derselben Prüfung (ohne Platzhalter; für die Netzfrequenz `quality.line_frequency`, für die Abdeckung `annotation.gaps`) auf dieser Aufnahme nicht bestanden ist (ARC-02). Fehlt ein Wert: „–“ bzw. „– (Grund)“; eine Legende erklärt beides.
- **Lesarten für G1:** Abschnitt 4 zeigt zusätzlich die datensatzweiten Werte aus `results.ai` (Klassen je Split, Demografie, Splits; eine zurückgehaltene Tabelle mit `report.ai.withheld`, A-51, A-81) und die Zahl der Duplikatgruppen; Anhang 6.1 „Geprüfte Regeln“ (Anzahl je Status) als Lesart von „diese Prüfungen“ (REP-06); Anhang 6.6 Umgebung (Python, Plattform, Bibliotheken, BLAS-Threads).

**A-85 PDF** (präzisiert A-08, A-26, A-27, A-49, A-54).
- **Ablauf** (`report.output.write_reports`, B1):
  - Ein unbekanntes Format endet mit Exit 2 (`errors.report.format_unavailable`). Mit `pdf` laufen `locate_shell` und `preflight` vor jedem Rendern; danach prüft `check_output_folder` vor dem Browserstart, ob ein Ziel ein Ordner ist (`output.is_directory`) oder der Ordner nicht beschreibbar (`output.not_writable`); beides Exit 2, nichts geschrieben. `--format html` braucht den Browser nie (A-26).
  - Je Sprache wird zweimal gerendert: Der erste Durchgang liefert die Zeichen des Entwurfs, dazu `page_text(lang)` (die Texte, die nur im CSS der Randboxen stehen); daraus entstehen die Teilschriften (`kernel.fonts.subset_font_css`, Familie „NG Sans“), der zweite Durchgang bettet sie ein. `report.<lang>.html` ist bytegleich zur gedruckten Datei, die Schriften stecken also auch im HTML.
  - Ein `PdfPrinter` druckt alle Sprachen; das QA-Gate läuft auf jedem PDF.
  - Schreiben, alles oder nichts (`write_all`, Review R00): Jede Datei wird neben ihrem Ziel bereitgestellt, vorhandene Berichte werden nach `.<Name>.<Zufall>.bak` daneben verschoben, dann die neuen hineingeschoben. Scheitert ein Schritt (volle Platte, fehlendes Recht, ein Bericht, den ein Betrachter sperrt), werden die schon platzierten neuen Dateien entfernt und die alten in umgekehrter Reihenfolge zurückgeschoben (bestmöglich; eine nicht wiederherstellbare Sicherung bleibt stehen), dann `output.not_writable` (Exit 2). Die Sicherungen werden erst nach vollem Erfolg gelöscht; scheitert das, scheitert der Lauf nicht. Ein Ordner, den der Lauf umsonst angelegt hat, wird wieder entfernt.
- **Browser:** nur Chrome Headless Shell Revision 1243 (Playwright 1.63.0) aus NeuroGrids Ordner.
  - `NEUROGRID_PDF_BROWSER_DIR` muss ein absoluter lokaler Ordner sein (leer, relativ, UNC, Gerätepfad oder Netzlaufwerk: Exit 2 `pdf.browser_dir_invalid`). Standard: `%LOCALAPPDATA%\NeuroGrid\pdf-browser` bzw. `${XDG_DATA_HOME:-~/.local/share}/neurogrid/pdf-browser` (ein relatives `XDG_DATA_HOME` gilt nicht).
  - Aufbau `<dir>/chrome-headless-shell-1243/{neurogrid-install.json, chrome-headless-shell-<win64|linux64>/…}`. `locate_shell` prüft den Ordner (`pdf.shell_missing`), dann Eintrag und Programm (`pdf.shell_incomplete`), dann Revision, Plattform und Programmpfad im Eintrag (`pdf.shell_revision`); andere Plattform `pdf.platform_unsupported`.
  - Nie `ms-playwright`, `PLAYWRIGHT_BROWSERS_PATH`, ein Kanal, Edge oder eine PATH-Suche. Ein Test verlangt für jeden Chromium-Start unter `src`, `tools` und `tests` ein `executable_path` aus `locate_shell` und keinen Kanal.
- **`tools/install_pdf_browser.py`** (nur Standardbibliothek, Meldungen zh und en): lädt die gepinnte zip (URL, Größe, SHA-256); `--from-zip ZIP --sha256 HEX` (nur die gepinnte zip), `--download-only --platform P --out DIR`, `--print-info`, `--check` (prüft eine Installation), `--dir`, `--force`. Es liegt im Bündel (`tools/`) und am Release; PyPI- und Quellnutzer holen es vom Release (Adresse und SHA-256 auf der Installationsseite, A-86). Der Benutzerordner erscheint in jeder Meldung als `~` (Review R06, Regel wie `redact_paths`).
- **Hinweis bei Exit 2:** `PdfError` trägt einen übersetzten Zusatzhinweis in einer zweiten Zeile; seine Parameter sind bereinigt, Datensatz- und Benutzerpfad ersetzt, nicht gekürzt, Anmelde- und Rechnername nicht ersetzt. Ein Pfad aus Playwrights Fehlertext erscheint nie, nur der Ausnahmetyp.
  - Bündelinstallation (`BUNDLE.json` im Präfix, dem Ordner über der venv, dazu `python/python.exe` bzw. `python/bin/python3.12` und `tools/install_pdf_browser.py`): ein Befehl, der so läuft, wie er gedruckt ist, ohne Benutzernamen (Review R07). Windows (`errors.pdf.install.command_windows`): für die Eingabeaufforderung mit `"%LOCALAPPDATA%\…"` (sonst `%USERPROFILE%`), für PowerShell mit `& "$env:LOCALAPPDATA\…"` (`$` und Backtick maskiert); ein Präfix anderswo steht wörtlich, in PowerShell in einfachen Anführungszeichen. Linux: `"$HOME/…"` mit maskiertem `\`, `"`, `$` und Backtick. Vorher stand dort `~`, das weder cmd.exe noch PowerShell im Skriptargument auflöst.
  - Jede andere Installation (PyPI, Quelle): Dokumentation, Installationsseite, Abschnitt „PDF-Browser“ (`errors.pdf.install.docs`).
- **Startprüfung** (`kernel.pdf.preflight`): `playwright == 1.63.0` (`pdf.playwright_version`); der temporäre Ordner (siehe Arbeitsordner); unter Linux `ldd <shell>` mit `LC_ALL=C`, Kodierung UTF-8, Fehler ersetzt.
  - Meldet ldd Bibliotheken als „not found“, nennt `pdf.linux_libraries` die apt-Pakete aus `kernel/pdf_linux_packages.json` für die Distribution laut `/etc/os-release` (debian12, ubuntu22.04, ubuntu24.04; jede andere: die Namen für Debian 12 mit dem Hinweis „nicht verifiziert“). Ein fehlendes `GLIBC_x` ergibt `pdf.glibc_too_old`; ohne ldd entfällt die Prüfung, ein scheiternder Start bleibt Exit 2.
  - Dieselbe Datei nutzen `tools/linux_pdf_packages.py` (CI, Doku; liest die `nativeDeps` von Playwright 1.63.0 als Daten, ohne node) und ein Test gegen Playwright. Von dessen Distributionen bleiben nur die drei aus A-58. Die ldd-Testdaten sind synthetisch und so gekennzeichnet.
- **Arbeitsordner des Browsers** (ändert A-54): ein privater Ordner `ng-pdf-XXXXXXXX` im temporären Ordner des Rechners (`tempfile.gettempdir()`: TMPDIR, TEMP, TMP), nie unter `--out`, im `finally` gelöscht (Sperrdatei siehe „Übergreifend“). Er enthält die temporären Dateien des Treibers, das Chromium-Profil (mit dem Log des Browserprozesses; `chromium.log` aus `--log-file` entsteht nicht, siehe debug.log) und die gedruckten HTML-Kopien.
  - Grund (gemessen): Die Shell kann keine langen Pfade, ihr Profil reicht 96 Zeichen unter den Arbeitsordner. Mit dem Arbeitsordner unter `--out` hinterließ ein `--out` von 195 Zeichen eine debug.log mit lokalen Pfaden im aktuellen Ordner, 210 Zeichen endeten in `pdf.launch_failed`.
  - Windows-Grenzen: Arbeitsordner höchstens 100 Zeichen (`WORK_PATH_LIMIT`), temporärer Ordner höchstens 84 (`TEMP_PATH_LIMIT` = 100 − Trenner − `ng-pdf-` − 8 Zeichen); gemessen sauber bis 160, Fehler in debug.log ab 170, also 60 Zeichen Reserve. Darüber Exit 2 `pdf.work_path_too_long` (Länge, Grenze) mit dem Hinweis `pdf.temp_hint` (TEMP und TMP, ggf. TMPDIR, auf einen Ordner von höchstens 84 Zeichen setzen); ohne brauchbaren temporären Ordner `pdf.temp_unusable` mit Hinweis; beides vor dem Rendern. Unter Linux gilt keine Grenze.
  - Treiber, Browser und dessen Kindprozesse laufen mit dem Arbeitsordner als aktuellem Ordner (`kernel.pdf.driver_environment`; danach zurück in den vorigen Ordner oder, wenn er fehlt, in den Elternordner). Kann ein Prozess seine Logdatei nicht öffnen, schreibt Chromium `debug.log` in seinen aktuellen Ordner (gemessen: ab 197 Zeichen Arbeitsordner überschreiten die Profilpfade 260 Zeichen); so landet sie im Arbeitsordner und wird mit ihm gelöscht, nie im Ordner des Aufrufers.
  - Pfade für Treiber und Browser sind immer absolut (`PdfPrinter`).
- **Browserstart:** nur `executable_path`, headless, `chromium_sandbox=False`, ohne Signal-Handler; Start-Timeout 60 s.
  - Flags `CHROMIUM_FLAGS`: `--disable-background-networking`, `--disable-component-update`, `--disable-breakpad`, `--no-pings`, `--disable-domain-reliability`, `--disable-sync`, `--proxy-server=direct://`, `--host-resolver-rules=MAP * ~NOTFOUND` und als letztes `--font-render-hinting=none` (`TEXT_LAYOUT_FLAG`); dazu `--in-process-gpu`, nur unter Windows `--enable-features=CDPScreenshotNewSurface,NetworkServiceInProcess2` (siehe debug.log) und `--log-file=<work>/chromium.log` (`kernel.pdf.launch_arguments`). Playwright 1.63.0 setzt eigene Standardflags dazu.
  - Textsatz (zweite CI-Fix-Runde): Die Shell setzt `--font-render-hinting` standardmäßig auf `full`, was nur der Linux-Renderer anwendet: Jede Glyphe stand auf einer gehinteten ganzen Pixelposition, die Vorschübe `/W` des PDF blieben ungehintet, und pypdf las Leerzeichen in Regel-IDs (CI auf 55335ca: BIDS-STO-001/002/003 und GXDSL008-STO-002 in keiner Zeile des zh-PDF-Texts, obwohl die Zellen nicht umbrechen). `none` gibt ungehintete Vorschübe an Subpixel-Positionen wie DirectWrite unter Windows; dort ändert der Schalter nichts (gemessen: bytegleicher zh-Bericht). Ein unbekannter Wert verhindert den Start (`pdf.launch_failed`), der letzte Wert auf der Kommandozeile gilt.
  - `--enable-features` wiederholt Playwrights eigenen Wert (`PLAYWRIGHT_FEATURES`), weil Chromium von einem wiederholten Schalter nur den letzten Wert behält; NeuroGrid übergibt kein `--disable-features`, das Playwrights Liste ersetzen würde. Nach einem Update von Playwright ist `PLAYWRIGHT_FEATURES` neu zu prüfen; ein Test liest den Wert aus dem Treiberbündel.
  - Umgebung des Browsers vollständig und minimal: Windows TMP/TEMP/TMPDIR = Arbeitsordner und SystemRoot; Linux dazu HOME und XDG_CONFIG/CACHE/DATA_HOME im Arbeitsordner, `LANG=C.UTF-8`.
  - Beim Start des Treibers (node): TMP/TEMP/TMPDIR = Arbeitsordner; entfernt sind `NODE_OPTIONS`, `NODE_PATH`, `DEBUG`, `DEBUG_FILE`, `DEBUGP`, `PWDEBUG` und jede Variable `PLAYWRIGHT_*` und `PW_*` (darunter `PLAYWRIGHT_NODEJS_PATH`, das einen anderen node starten würde).
- **debug.log** (Windows, gemessen): Kindprozesse der Shell nutzen `--log-file` nicht und hängen Fehler an `debug.log` neben dem Programm an, also in NeuroGrids Browserordner (einmal gesehen: zwei Zeilen des GPU-Prozesses; danach scheiterte `install_pdf_browser.py --check`). Deshalb läuft die GPU im Browserprozess (`--in-process-gpu`; die PDFs sind mit und ohne Flag bytegleich).
  - Grund laut Quelltext von Chromium 153.0.8010.12 (Revision 1243; zweite CI-Fix-Runde): Unter Windows richtet ein Kindprozess der Shell kein Logging ein und behält die Voreinstellung „in debug.log neben dem Programm, ab INFO“; kein Schalter und keine Variable ändern das. Auf dem windows-latest-Runner (55335ca) schrieb der Netzwerkdienst als Kindprozess beim Schließen eines eben gestarteten Browsers die Warnung `sqlite_persistent_store_backend_base.cc:181 … sqlite_persistent_shared_dictionary_store.cc:259` dorthin (lokal nachgestellt: 6 von 6 und 20 von 20 Läufen). Deshalb läuft unter Windows auch der Netzwerkdienst im Browserprozess (`NetworkServiceInProcess2`; danach 10 von 10 Läufe ohne debug.log und ohne Netzwerkdienst-Prozess). Unter Linux schreiben Kindprozesse auf stderr, das Prozessmodell bleibt dort unverändert.
  - `--log-file` wirkt in der Shell nicht (gemessen: keine solche Datei); der Browserprozess schreibt in `<Profil>\Default\chrome_debug.log` im Arbeitsordner, das Flag bleibt und ist so dokumentiert. Renderer bleiben Kindprozesse; eine debug.log, die einer anhängt, macht der Drucker rückgängig (nächster Satz).
  - Eine beim Start vorgefundene debug.log (Rest eines abgebrochenen Laufs, mit lokalen Pfaden) wird entfernt; hält ein laufender Browser sie offen, schneidet der Lauf am Ende nur ab, was er angehängt hat, und eine von ihm angelegte entfernt er.
- **Seite und Druck:**
  - Kontext: JavaScript aus, `offline`, Service Worker blockiert, keine Downloads, Zeitzone UTC, helles Farbschema; Locale zh-CN für den zh-Bericht und en-US für den en-Bericht (andere werden abgelehnt; jeder Bericht ergibt in beiden Locales dieselben Bytes, getestet).
  - Standard-Timeout 300 s nur für Öffnen und Laden der Seite; Playwright 1.63.0 sendet `Page.pdf` ohne Timeout, ein großer Bericht endet also nie beim Drucken in `pdf.timeout` (Quelltext-Test).
  - Ein Router mit einem Parameter lässt nur die exakte Datei-URL durch und bricht alles andere ab; gezählt wird über die Ereignisse `request` und `requestfailed`.
  - Die CSP aus A-08 muss im `<head>` stehen, geprüft mit einem HTML-Parser vor dem Druck (sonst `pdf.qa_failed` `html_csp_missing`).
  - `page.pdf`: A4, CSS-Seitengröße, Hintergründe, `tagged=False` (getaggte PDFs tragen DOM-Knoten-IDs), `outline=False`, keine Kopf-/Fußzeile von Chromium.
- **Datum und Metadaten:** `/CreationDate` und `/ModDate` (Skia-Form `D:JJJJMMTThhmmss±hh'mm'`) werden gleich lang durch `D:<as_of>000000+00'00'` ersetzt; Exit 2 (`pdf.qa_failed` `metadata_dates`), wenn nicht jedes Feld genau einmal vorkommt. Kein Umschreiben mit pypdf. `/Info` enthält genau Title (= HTML-`<title>`), Creator „Chromium“, Producer „Skia/PDF …“ (gemessen: m153), CreationDate und ModDate; kein `/Subject`, kein XMP; Skias Trailer hat kein `/ID` (gemessen: nur /Size /Root /Info).
- **QA-Gate** (`kernel.pdf.qa_gate`, zur Laufzeit auf jedem PDF; Tests haben zusätzlich ein eigenes pypdf-Orakel und prüfen, dass das Gate ihm folgt):
  - Codes (sortiert, in Meldungen nur die Codes): `unreadable`, `no_pages`, `font_type3`, `font_not_cid_truetype`, `font_not_report_font`, `font_no_tounicode`, `glyph_missing`, `radical_codepoint`, `phrase_missing_on_page`, `phrase_missing`, `metadata_keys`, `metadata_title`, `metadata_dates`, `metadata_xmp`, `requests_unexpected`, `requests_aborted`, `requests_failed`.
  - Schriften: nur Type0 mit CIDFontType2, FontFile2 und ToUnicode, auch in Form-XObjects; BaseFont `ABCDEF+<Name>`, wobei das Produkt die PostScript-Namen aus den Schriftdateien übergibt (`PdfExpect.fonts`, `kernel.fonts.postscript_names`); der Kern nennt keine Schrift (A-23); im Code steht „NotoSansSC-“ nur in `report/texts.py`.
  - Phrasen (Leerraum zählt nicht): der feste Satz auf jeder Seite; einmal je PDF `report.title`, `report.section.{cover,summary,findings,metrics,evidence,appendix}` und bei geladenem Platzhalter-Paket `report.placeholder_banner`.
  - Fehlende Glyphe (`glyph_missing`, zweite CI-Fix-Runde): Hat keine installierte Schrift ein Zeichen, zeichnet Chromium das leere Kästchen (.notdef, Glyphe 0) der ersten Kandidatenschrift, also der Berichtsschrift; das PDF bettet dann nur Berichtsschriften ein und sein Text enthält nichts vom Zeichen, Schrift- und Radikalprüfung sahen es nicht (CI auf 55335ca: die Radikal-Gegenprobe U+2F63 ergab auf ubuntu-24.04 kein Urteil; unter Windows nachgestellt mit U+0378). Das Gate folgt deshalb beim Textauszug von pypdf der aktuellen Schrift (Tf, q/Q, Form-XObjects) und meldet jede gezeigte Glyphe 0 einer Type0-Schrift mit Identity-Kodierung (CID 0 unter `CIDToGIDMap /Identity` oder ohne Map, eine CID, die eine Map auf 0 schickt oder die über sie hinausgeht). Eine Type0-Schrift ohne Identity-CMap als `/Encoding` ergibt `font_not_cid_truetype`. Gemessen: etwa 10 % mehr Zeit für das Gate (19-seitiger zh-Bericht 1,75–1,90 s statt 1,57–1,62 s).
  - Gegenproben in den Tests ohne Systemschriften: ein Berichtsschnitt, dessen cmap U+2F63 auf die Glyphe von 生 legt (`radical_codepoint`), ein umbenannter Schnitt (`font_not_report_font`) und U+0378 (`glyph_missing`), je mit genauem Urteil und den eingebetteten Schnitten; die Gegenproben mit Systemschriften (Emoji, U+2717, U+2F63) nehmen auf einem System ohne Schrift für das Zeichen auch genau `glyph_missing` an. Keine neuen i18n-Schlüssel (die Codes stehen in `pdf.qa_failed`).
- **Schriften** (präzisiert A-27):
  - Statische Schnitte Noto Sans SC 400/700 aus `tools/build_fonts.py` (google/fonts@a85815a4, `NotoSansSC[wght].ttf`, URL und SHA-256 gepinnt, OFL-1.1); je Schnitt 453 Radikal- und Kompatibilitäts-Codepunkte entfernt; eingecheckt unter `src/neurogrid/report/fonts/` mit `fonts.json` (SHA-256, Quelle) und `OFL.txt`.
  - Teilschriften zur Laufzeit: name-IDs 0–6, 13 und 14, Sprache 0x409, `recalc_timestamp` aus, `notdef_outline`, ohne Hinting, Standard-Layout-Features, immer mit „0123456789 /“; eingebettet als `@font-face` „NG Sans“ 400/700 (`data:font/ttf;base64`).
  - Glyphenzwillinge (`kernel.fonts.separate_shared_glyphs`): Jeder Codepunkt bekommt in der Teilschrift eine eigene Glyphe. Grund (gemessen): Die Schnitte bilden 95 Glyphen auf 2–4 Codepunkte ab (z. B. U+2012/U+2013, U+002D/U+00AD/U+2011), und Skia schreibt je Glyphe einen ToUnicode-Eintrag mit dem kleinsten Codepunkt. Ein Datensatzname mit U+2012 machte so jeden „–“ des Berichts zu U+2012, und eine Gate-Phrase mit dem höheren Zwilling konnte fehlen (Exit 2 durch Datensatzdaten). Der kleinste Codepunkt behält die Glyphe; jeder andere erhält eine Kopie `<Glyphe>.uXXXX` (Umriss, Breite, vmtx, GDEF-Klasse), in Codepunktfolge angehängt.
  - Die Kopien nehmen an jedem GSUB-, GPOS- und GDEF-Eintrag ihres Originals teil (Unterschneidung, Markenpositionen, lokale Formen bleiben gleich). Ein von einer Kopie erreichtes Ersatzzeichen ist selbst eine Kopie (`<Ersatz><Suffix>`), Ligaturen heißen `<Ligatur>.L<Länge><Suffix>`. Schriften mit Glyphentabellen, die nicht kopiert werden (`GLYPH_TABLES_NOT_COPIED`), werden abgelehnt. Die Schnitte nutzen nur GSUB 1/3/4 und GPOS 1/2/4.
  - Zwillinge durch Ersetzung (Review R02, `kernel.fonts.substituted_glyphs`): Eine cmap-Glyphe, die eine GSUB-Ersetzung der Typen 1, 2, 3, 4 oder 8 auch aus anderen Glyphen erzeugt (z. B. `uniFB01` aus f + i, `uni2E3A` über ccmp, `uni2015` über zh-locl), gilt als Zwilling; jeder ihrer Codepunkte erhält eine Kopie. Damit bleibt der PDF-Text von NeuroGrids eigenen Wörtern gleich dem HTML-Text, auch wenn ein Datensatz U+FB01 enthält.
  - Verworfen: Zwillinge beim Glyphenschutz vereinheitlichen (ändert Datensatztext) und eine Gleichsetzung im Gate (der PDF-Text bliebe falsch).
- **Kernimporte:** `KERNEL_ALLOWED_THIRD_PARTY` um fontTools, playwright und pypdf erweitert (KONZEPT 1.2 nennt nur fontTools und Playwright). Playwright wird erst beim Browserstart importiert; HTML-Läufe laden es nie.
- **Netzwerkschutz** (ergänzt A-49): Die synchrone API von Playwright betreibt eine asyncio-Schleife im NeuroGrid-Prozess und spricht über Pipes mit dem Treiber; unter Windows legt der Proactor dafür ein Socket-Paar über 127.0.0.1 an (mit Audit-Ereignissen; gemessen genau ein connect). Loopback ist erlaubt, jede andere Verbindung, jedes Datagramm und jede Namensauflösung bleiben gesperrt (getestet); netguard ist unverändert. NeuroGrids eigener Code nutzt weiter kein asyncio.
- **Bekannte Grenzen:** Unter Linux ohne `HOME`, ohne passwd-Eintrag, ohne `XDG_DATA_HOME` und ohne `NEUROGRID_PDF_BROWSER_DIR` endet `report --format pdf` mit „Internal error (RuntimeError)“ (Exit 2) statt einer eigenen Meldung, weil `kernel.pdf.default_browser_dir` `Path.home()` ungeschützt aufruft (ebenso der Standardordner von `tools/install_pdf_browser.py`). Ein Arbeitsordner, dessen Lauf zwischen `mkdtemp` und dem Anlegen der Sperrdatei abbricht, bleibt leer stehen. Die Kopien der Glyphenzwillinge sind für GSUB 2/5/6/8 und GPOS 3/5/6/7/8 nur an einer synthetischen Testschrift geprüft. Die visuelle Prüfung der PDFs von Hand ist ein Punkt für G1 (KONZEPT 4).

**A-86 Dokumentation, Meldungen, Notices, Lizenzen** (präzisiert A-07, A-28, A-56, A-57; NG-N06; D-15 und D-16 siehe dort).
- **Werkzeuge** (präzisiert A-28): mkdocs 1.6.1, mkdocs-material 9.7.7, mkdocs-static-i18n 1.3.1 und pymdown-extensions 12.3 in der Gruppe `docs`; `[tool.uv] default-groups = ["dev", "docs"]`. Jeder Laufzeitexport ist `uv export --frozen --no-default-groups --no-emit-project` (ein Export mit `--no-dev` trüge mkdocs mit); ein Test vergleicht den echten Export mit der statischen Hülle von `tools/notices.py` für CPython 3.12.
- **Seiten:** genau 16 je Sprache: index, installation (Offline-Bündel, Download prüfen, PDF-Browser, PyPI, Quelle, Doku öffnen), quickstart, commands, configuration, rulepacks, metrics, report, privacy, limitations, terms, data-model, license, reference/checks und reference/rules (beide erzeugt), reference/outputs (mit results.json).
- **Bau** nur über `tools/build_docs.py`: `gen_docs.py --check`; `SOURCE_DATE_EPOCH` aus der Umgebung oder die Commit-Zeit von HEAD; `mkdocs build --strict` unter einem Audit-Hook, der `socket.connect`, `getaddrinfo`, `gethostbyname`, `gethostbyaddr`, `sendto`, `sendmsg` und `urllib.Request` ablehnt; danach Prüfungen des gebauten Auftritts. Exit 0 gebaut und geprüft, 1 eine Prüfung gescheitert, 2 der Bau gescheitert (auch: keine Lizenzprüfung für die installierte Theme-Version).
- **Fremdteile des Auftritts** (Review R19; TECH-10, D-05):
  - Geprüft in `license-gate/third_party/mkdocs-material-9.7.7/manifest.toml`: mkdocs-material MIT, rxjs Apache-2.0, tslib 0BSD, clipboard 2.0.11, escape-html und lunr 2.3.9 MIT, Material Design Icons Apache-2.0, Octicons MIT, Font Awesome Free 7.1.0 CC-BY-4.0, die Noto-Sans-SC-Teilschrift OFL-1.1; Texte aus dem installierten Wheel und den Dateiköpfen, nichts geladen.
  - `build_docs.py` entfernt nach dem Bau `assets/javascripts/lunr/**` (lunr-languages unter MPL, tinyseg, wordcut; die Suche mit `lang: en` lädt sie nie) und `**/*.map`.
  - Der Bau scheitert (Exit 1) bei einer Datei, die weder NeuroGrids eigene ist (Suchindex, Sitemaps, Schemas, `neurogrid.css`, `file-search-hint.js`) noch geprüft; bei einer entfernten Datei, die noch da ist; bei einem Copyleft-Kopf in einer .js- oder .css-Datei; bei einer Lizenz außerhalb der freizügigen und OFL-1.1 (MPL-2.0 nur mit `unmodified = true`, D-05) ohne Eintrag in `known_missing.toml`; bei einer Prüfung, die nicht zur installierten und gesperrten Theme-Version passt; bei einer kopierten Lizenzdatei, die nicht mehr der installierten gleicht.
  - focus-visible und material-design-color nennen in den gelieferten Dateien keine Lizenz; bis D-17 waren sie Lücken `docs-site:*`, die jeder Bau als „licence pending (blocks the release, STOPP G1)“ nannte. Seit D-17 liegen ihre Texte im Manifest (focus-visible: W3C-20150513 ohne erfundene Copyright-Zeile; material-design-color 2.3.2: MIT, Version nur aus dem Lockfile von mkdocs-material belegt).
  - THIRD_PARTY_NOTICES nennt den Auftritt in Abschnitt 4, seine Texte in Abschnitt 6. CC BY 4.0 gilt nur für NeuroGrids eigenen Text; Fußzeile und Lizenzseite sagen das.
- **Offline-Suche** (Option a): kein Offline-Plugin von Material. Die Suche geht, wenn der Ordner über 127.0.0.1 ausgeliefert wird (Installationsseite: `.\python\python.exe` bzw. `python/bin/python3.12 -m http.server 8000 --bind 127.0.0.1 --directory docs`); unter `file://` sperrt ein Skript das Feld mit übersetztem Hinweis. Suchsprache nur en mit eigenem Trenner, `reconfigure_search: false`. Chinesisch ohne Wörterbuch: `tools/mkdocs_hooks.py` ersetzt jieba und zerlegt jede Folge von Han-Zeichen in einzelne Zeichen (im Index durch U+200B getrennt). Kein jieba, kein Bau aus Quellen.
- **Chinesische Schrift der Doku** (Lesart von „lokale Schrift“ in A-28): `build_docs.py` schneidet die Han-Zeichen aller gebauten Seiten aus den statischen Berichtsschriften (WOFF, ohne Zeitstempel, name-IDs 0–6, 13, 14); CSS-Familie „NeuroGrid Docs SC“ mit CJK-`unicode-range`, lateinischer Text bleibt in der Systemschrift des Themes.
- **Meldungen** (NG-N06, Umfang a):
  - Hilfetexte, Usage-Überschriften, Metavariablen (`值`/`VALUE`, `N`), Standard- und Pflicht-Hinweise und Usage-Fehler kommen aus `cli.help.*` und `cli.error.*`; die englischen `help=`-Texte stehen nicht mehr in den Optionen.
  - Mechanismus: der öffentliche `cls`-Haken von Typer (Unterklassen von TyperCommand und TyperGroup überschreiben `format_help`, `parse_args` und `resolve_command`); `typer._click` wird nie importiert. click-Ausnahmen werden nach Klassennamen abgebildet (MissingParameter, BadParameter, NoSuchOption, BadOptionUsage), dazu eigene Fehler für unbekannte Befehle und überzählige Argumente.
  - Die Hilfe ist in Terminalspalten gesetzt (ostasiatische Zeichenbreite), ohne Umbruch vor schließenden oder nach öffnenden chinesischen Satzzeichen.
  - Die Sprache entsteht vor dem Parsen aus argv: globales `--lang` > `NEUROGRID_LANG` > Systemsprache; ein ungültiges `--lang` fällt zurück und wird dann mit Exit 2 gemeldet.
- **Notices** (ändert A-56):
  - `tools/notices.py` liest die gesperrten Wheels beider Ziele (win_amd64, manylinux x86_64; CPython 3.12) statisch mit zipfile, nichts wird installiert. Eigener Leser statt pip-licenses, weil pip-licenses nur die installierten Pakete einer Plattform sieht. Ausgabe `THIRD_PARTY_NOTICES.txt`.
  - Abschnitte: 1 Python-Pakete je Ziel; 2 native und Nicht-Python-Teile der Wheels, jeder mit geprüftem Eintrag in `components.toml` (D-08); 3 die in den BIDS-Validator kompilierten npm- und jsr-Pakete laut Source-Map (Texte nach D-15, LGPL-Teil nach D-16); 4 Teile außerhalb der Wheels (Noto Sans SC mit OFL.txt, python-build-standalone und uv laut `packaging/bundle_lock.json` mit der Entfernung von `_dbm`, der Doku-Auftritt, Chrome Headless Shell als nicht verteilt); 5 bekannte Lücken; 6 Lizenztexte, nach SHA-256 entdoppelt.
  - Lizenz der Datei (Review R26): `CC-BY-4.0 AND LicenseRef-NeuroGrid-Reproduced-Notices`, als Urheber auch die genannten Dritten; `LICENSES/LicenseRef-NeuroGrid-Reproduced-Notices.txt` sagt, dass wiedergegebene Texte wörtlich kopiert sind, ihre eigenen Bedingungen behalten, NeuroGrid an ihnen keine Rechte beansprucht und GPL/LGPL nur unverändert kopiert werden dürfen.
  - `notices.py --check` endet mit Exit 1, solange `license-gate/known_missing.toml` eine Lücke nennt; `release.yml` führt `tools/notices.py --download --check` vor jedem Bau und jeder Signatur aus. Seit D-17 ist `known_missing.toml` leer und `--check` endet mit 0 (Abschnitt 5 der Notices: „None: every licence text is in this file.“); neue Prüfungen: jeder Ordner unter `license-gate/third_party/` enthält genau die Texte seines Manifests mit SHA-256 und Größe, die eingebauten Bibliotheken von python-build-standalone haben ein eigenes Manifest (`LIBRARY_ALLOWED`), Art und Felder eines Auszugs werden geprüft (D-17). Bis dahin blieb die Freigabe für diese acht Lücken gesperrt: `bids-validator-deno:hed-validator@4.2.0/node_modules` (acht Pakete ohne Version in der Source-Map; D-15 deckt nur genaue Versionen), `bids-validator-deno:hash-wasm@4.12.0/src` (C-Teile ohne Lizenztext), `bids-validator-deno:node-modules-polyfills/@jspm/core` (Polyfills ohne Version), `h5py:h5py.libs/libaec-*.so*` und `h5py:h5py.libs/libsz-*.so*` (das Linux-Wheel nennt weder Lizenz noch Text), `python-build-standalone:3.12.15+20261009` (die Texte der eingebauten Bibliotheken wie OpenSSL, libffi, SQLite, XZ und zlib fehlen im Archiv), `docs-site:focus-visible` und `docs-site:material-design-color`.
- **Lizenz-Gate:**
  - Ordner `license-gate/` statt `licenses/` (Kollision mit REUSE `LICENSES/` auf Windows ohne Unterscheidung der Groß-/Kleinschreibung) mit `allowlist.txt`, `exceptions.txt`, `components.toml` (Felder dist, pattern, platform, spdx, kind ∈ native|bundled|notice|external|bundle|not_distributed, notice, note), `known_missing.toml`, `licence_texts.toml`, `network_baseline.json` und `third_party/`.
  - `tools/licenses.py` prüft die Gruppen runtime, dev und docs in zwei Stufen und mit `--components` statisch jede native Datei der gesperrten Wheels beider Ziele und die Bündelteile; die Linux-Prüfung läuft damit auch unter Windows. Native Allowlist (D-08) mit `GPL-3.0-or-later WITH GCC-exception-3.1` (nur GCC-Laufzeit) und `LGPL-2.1-or-later` (libquadmath).
  - CON-01: Importsperre für metabci, openvibe und eegprep über `src/neurogrid/**/*.py` und `tools/*.py` (Test).
- **Berichtigung der Geprüften Fakten:** Die Windows-Wheels von numpy und scipy nennen in ihrer LICENSE.txt die GCC-Laufzeit (`GPL-3.0-or-later WITH GCC-exception-3.1`) als statisch in `libscipy_openblas*.dll` gelinkt. Die Linux-Wheels liefern libgfortran und libquadmath als eigene .so-Dateien; scikit-learn liefert unter Linux libgomp.
- **REUSE** (die letzte passende Tabelle gilt; `tests/docs/test_licensing.py` wendet dieselbe Regel auf jede versionierte und neue Datei an):
  - CC-BY-4.0: `docs/**`, README.md, DATA_SOURCES.md, `tests/fixtures/synthetic/**`. Apache-2.0: Code und Konfiguration (`src/**`, Tests, `tools/**`, `.github/**`, `packaging/**`, `license-gate/**`, `.env.example`, pyproject.toml, uv.lock, mkdocs.yml, `docs/assets/**` u. a.). OFL-1.1 mit Vorrang: `src/neurogrid/report/fonts/*.ttf` und `OFL.txt` (Urheberzeile aus OFL.txt); `fonts.json` Apache-2.0. THIRD_PARTY_NOTICES.txt mit eigener Angabe (siehe Notices).
  - `LICENSES/` enthält nur Lizenzen eigener Dateien, wie `reuse lint` es verlangt (Review R27): Apache-2.0, CC-BY-4.0 (Download nach D-15), OFL-1.1, LicenseRef-NeuroGrid-Reproduced-Notices. Die Texte LGPL-3.0 und GPL-3.0 aus D-16 liegen neben isomorphic-git 1.41.9 unter `license-gate/third_party/bids-validator-3.0.2/npm/isomorphic-git@1.41.9/`.
  - Das eigene REUSE-Gate folgt `reuse lint` bei unbenutzten Lizenzen und übergeht SPDX-Zeilen in Lizenzdateien; das REUSE-Werkzeug selbst ist keine Abhängigkeit (GPL-3.0, kein Windows-Wheel).
- **core 0.1.1:** Die Quelle von core lautet „NeuroGrid core metrics (docs/<lang>/metrics.md)“; damit ändern sich Paketbytes und SHA-256.
- **Wortwahl und V-06:** `tests/docs/test_docs_wording.py` wendet `report/wording/forbidden.yaml` auf alle Seiten, `docs/_data`, `mkdocs.yml` und `docs/assets` an; erlaubte Sätze stehen auf einer Zeile. Der V-06-Test liegt nur in `tests/unit/test_norm_independence.py`; geprüfte Nennungen stehen dort in `KNOWN`.
- **Installationsseite** (Review R28, Lesart von B2): Ein von `tools/gen_docs.py` erzeugter Block „pdf installer“ nennt `<REPO_URL>/releases/download/v<version>/install_pdf_browser.py` und den SHA-256 des Skripts dieser Version; `gen_docs.py --check` scheitert nach jeder Änderung des Skripts. Alle Exit-2-Hinweise (zh, en, de) verweisen auf diesen Abschnitt. Die Platzhalter `<REPO_URL>` und `<PYPI_RELEASE>` stehen nur in Kästen „Placeholder“/„占位“; `release_check.py` scheitert, solange einer bleibt.
- **Datenschutzseite** (Review R25): nennt die Regel von `tools/strace_check.py` (kein AF_INET/AF_INET6-Aufruf an eine Adresse außer Loopback; Loopback erlaubt außer Port 9, A-87), dazu `<user>`/`<host>` in Konsolenpfaden und den Arbeitsordner des PDF-Browsers im temporären Ordner.
- **Nutzerdoku nach der zweiten CI-Fix-Runde** (en und zh, je mit Test in `tests/docs/test_docs_sync.py`, der auf dem alten Text scheitert):
  - R09: `configuration.md#dataset` sagt jetzt wie der Code (`pipeline._dataset_info`) und A-04: name und license aus `neurogrid.toml` gehen vor `dataset_description.json`, die nur ein nicht gesetztes Feld füllt; id, version und source kommen nur aus dem Abschnitt (A-63).
  - R08: `privacy.md#outputs`, `report.md` (Abschnitt 5 und Pseudonymität) und die Zeile zu evidence.yaml in `configuration.md` nennen die Ausnahme von A-83: `document`, `reviewer`, `comment` und `justification` stehen im Klartext in results.json und in Abschnitt 5, auch in Rohordnern ohne `--show-paths`, nie auf der Konsole; als reviewer eine Rolle oder Initialen (A-15), neutrale Dokumentnamen, keine Personen in comment und justification, dazu der Hinweis `notice.evidence_looks_identifying`.
  - Plattformstand (zweite CI-Fix-Runde; die Testsuite-Zellen sind seit der dritten überholt, nächster Punkt): Die Sätze „bis zum ersten CI-Lauf nicht verifiziert“ sind ersetzt. installation.md und limitations.md (und dieselbe Passage in README.bundle.txt und den Release-Notes) unterscheiden „lokal verifiziert“ (Windows 11 mit Windows PowerShell 5.1), „Offline-Bündel in der CI verifiziert; Testsuite noch nicht verifiziert“ (Windows Server des Runners mit PowerShell 5.1 und 7; Debian 12, Ubuntu 22.04, Ubuntu 24.04), „nicht verifiziert“ (Windows 11 mit PowerShell 7, Windows 10, Ubuntu nach 24.04) und „abgelehnt“ (glibc < 2.28, in der CI verifiziert); der Reinraum ist je Plattform beschrieben (Linux ohne Netz und Python, Windows mit Netz, Sperrregel und WFP-Audit). Der Test liest Images und Shells aus `offline.yml`.
  - Plattformstand nach der dritten CI-Fix-Runde (U1, 17e0d3f und 341beb1; V-06, NG-N04, TECH-06, NG-N01): Die Zellen „Testsuite noch nicht verifiziert“ (Stand 55335ca) sind ersetzt. „Testsuite in der CI verifiziert (Python 3.11–3.13)“ gilt für Windows Server (Runner `windows-latest`) und Ubuntu 24.04 (Reinraum `ubuntu:24.04` und Runner `ubuntu-24.04`); „Testsuite nicht in der CI ausgeführt“ für Debian 12 und Ubuntu 22.04, die nur die Offline- und PDF-Jobs sehen (die frühere gemeinsame Linux-Zeile ist geteilt); Windows 10 und PowerShell 7 unter Windows 11 bleiben „nicht verifiziert“. Dasselbe sagen limitations.md (en/zh), wörtlich auch README.bundle.txt und die Release-Notes; die Zeile der Audit-Hook-Tests in privacy.md heißt „lokal und in der CI auf den Runnern `windows-latest` und `ubuntu-24.04` mit Python 3.11–3.13 verifiziert“ (`tests/conftest.py` installiert netguard für jeden Test, ohne Plattformausnahme). `tests/docs/test_docs_sync.py` liest Runner und Python-Versionen aus der Testmatrix von `ci.yml` und die Distributionen aus `offline.yml` (`SUITE_IN_CI`, `SUITE_NOT_IN_CI`, `SUITE_DEFINITION`, `SUITE_LIMITS`, `AUDIT_HOOK_IN_CI`, `NOT_VERIFIED`, `RUNNERS`) und verbietet die alten Sätze von 18da12f in docs/en, docs/zh und beiden Liefertexten als ganze Sätze, nicht jedes „do not pass yet“/„尚未通过“ (341beb1). Gedeckt ist die Aussage durch die grüne CI auf 27c3e90 (A-87) und für jede Version durch das Release-Gate (dd9ab93, A-87).
  - Firewall-Prüfung auf der Datenschutzseite: dieselbe Sperrregel wie der Windows-Reinraum (jede .exe unter Installation bzw. venv und unter `%LOCALAPPDATA%\NeuroGrid\pdf-browser`, dazu `sys._base_executable` bei venv-Installationen) und wie man sie entfernt; eine Regel deckt den PDF-Browser ab, weil alle seine Prozesse `chrome-headless-shell.exe` sind. Behauptet eine Seite, ein Teil laufe „im Browserprozess“, prüft der Test das gegen die echten Windows-Startflags.
- **zh-Prüfung (A-07, G1):** alle 16 zh-Seiten, `docs/_data/labels.zh.yaml` und `checks.zh.yaml`, der Hinweis für `file://`, die zh-Werte von `cli.help.*`, `cli.error.*` und `errors.pdf.*`, die Meldungen von `install_pdf_browser.py`, beide Installer, README.bundle.txt, die Release-Notes und `gitee-release.md`; das Prüfpaket erzeugt `tools/zh_review_package.py` (A-88). Seit der ersten Fassung des Pakets (6a4f737) neu oder geändert: die Überschriften der Schweregrade (`report.text.severity_heading`, `_none`, `_info`), der Installationshinweis `errors.pdf.install.command_windows` (neu) und `errors.pdf.install.docs` (geändert), die Meldungen zum Arbeitsordner des Browsers (`errors.pdf.work_path_too_long`, `errors.pdf.temp_hint`, `errors.pdf.temp_unusable`, `errors.pdf.temp_unusable_hint`), die Meldungen von `install.ps1` und `install.sh`, die Sätze der Fix-Runden in docs/zh (installation, limitations, privacy, configuration, report) und im Plattformabsatz von README.bundle.txt und den Release-Notes, `gitee-release.md`, der geänderte Satz in `docs/zh/license.md` (D-17) und die Zeile `cli.check.recomputed` (A-89). Aus der dritten CI-Fix-Runde (U1): in `docs/zh/installation.md` die Zelle der Windows-Server-Zeile, die beiden neuen Linux-Zeilen (Debian 12 und Ubuntu 22.04; Ubuntu 24.04) und die Definitionen „测试套件已在 CI 中验证“ und „测试套件未在 CI 中运行“; der Plattformsatz in `docs/zh/limitations.md` (wörtlich auch in README.bundle.txt und den Release-Notes); die Zelle der Audit-Hook-Tests in `docs/zh/privacy.md`.

**A-87 Bündel, Signatur, Installation, Workflows** (präzisiert A-26, A-48, A-49, A-58; Lesart von D-10 g und D-15).
- **Bündel** (`tools/bundle.py build|verify|sizes|lock`):
  - `neurogrid-<v>-offline-win_amd64.zip` und `neurogrid-<v>-offline-linux_x86_64.tar.gz`, je mit genau einem Wurzelordner `neurogrid-<v>-offline-<platform>/`. Oberste Ebene: BUNDLE.json, LICENSE, NOTICE, README.txt (aus `packaging/README.bundle.txt`), SHA256SUMS, THIRD_PARTY_NOTICES.txt, `docs/`, `python/`, requirements.lock.txt, `src/` (nur das sdist, CON-05), `tools/` (nur install_pdf_browser.py), `uv/` (uv bzw. uv.exe, Lizenzen, CycloneDX-SBOM), `wheels/`; Windows dazu install.cmd und install.ps1, Linux install.sh und SYMLINKS; `SHA256SUMS.sigstore.json` nur in Release-Bauten.
  - `verify` lehnt u. a. ab: Browserdateien (chrome*, chromium*, headless_shell, ms-playwright), .pyc außerhalb von `python/`, Pfade außerhalb `[A-Za-z0-9._+/-]`, Namen, die sich nur in der Groß-/Kleinschreibung unterscheiden, `_dbm` (Linux), Links aus dem Bündel heraus, Wheels, die nicht zu cp312 und win_amd64 bzw. manylinux ≤ 2_28 passen, Archive ab 2 GiB und eine README.txt ohne den festen Satz zh und en.
  - Interpreter (präzisiert KONZEPT 1.6): python-build-standalone 3.12.15+20261009 `install_only_stripped`, unverändert bis auf eine Entfernung unter Linux: `python/lib/python3.12/lib-dynload/_dbm.cpython-312-x86_64-linux-gnu.so` (Berkeley DB 6.0.19, Sleepycat), vermerkt in `BUNDLE.json` `python.removed`, in den Notices, README.txt und den Release-Notes; ein Test zeigt, dass kein Laufzeitpaket dbm oder shelve braucht. uv 0.13.0 aus seinem PyPI-Wheel mit Lizenzen und SBOM.
  - Reproduzierbar: `SOURCE_DATE_EPOCH` (Standard: Commit-Zeit von HEAD), sortierte Einträge; zip mit `create_system` 3 und Modi 0644/0755; tar.gz im PAX-Format, uid/gid 0, mtime = Epoche, gzip ohne Zeit und Namen; SHA256SUMS im GNU-Format, bytewise sortiert. Zwei Bauten je Plattform sind bytegleich (lokal gemessen und im Job `build` von offline.yml).
- **Installation:**
  - Laufzeitsatz = `uv export --frozen --no-default-groups --no-emit-project`; `requirements.lock.txt` mit Pin und Hash je Wheel, auch für das NeuroGrid-Wheel. Installiert wird mit `uv pip sync --no-index --find-links wheels --require-hashes --no-build --compile-bytecode --link-mode copy` und `UV_OFFLINE=1`, `UV_NO_CONFIG=1`, `UV_PYTHON_DOWNLOADS=never`, `UV_CACHE_DIR` im Präfix (danach entfernt), `PYTHONIOENCODING=utf-8` (gemessen: ohne es kompilierte uv unter einem Präfix mit chinesischen Zeichen 0 von 5003 Modulen). Das Windows-Skript stellt jede gesetzte Variable wieder her.
  - Lesart von A-26 („setzt beschreibbare Orte“): Standardpräfix `%LOCALAPPDATA%\NeuroGrid\<v>` bzw. `${XDG_DATA_HOME:-~/.local/share}/neurogrid/<v>`; keine Änderung an PATH, Registry oder Profil; ein vorhandenes, nicht leeres Ziel wird abgelehnt (Exit 2). Die Starter `neurogrid.cmd` und `bin/neurogrid` leeren PYTHONPATH und PYTHONHOME und setzen nichts für `DENO_DIR` (je Lauf, A-06, A-54) oder den Browser (Standardordner aus A-85 oder `NEUROGRID_PDF_BROWSER_DIR`).
  - `-PdfBrowserZip`/`--pdf-browser-zip` mit `-PdfBrowserSha256`/`--pdf-browser-sha256` ruft `install_pdf_browser.py --from-zip … --sha256 …` mit dem Bündel-Python. Ins Präfix kommen BUNDLE.json, `python/` und `tools/install_pdf_browser.py` (die Marke für den Hinweis aus A-85).
  - Exitcodes: 0 installiert bzw. geprüft (`-VerifyOnly`/`--verify-only`), 2 Bedienung oder Umgebung, 3 Integrität, 4 Signatur. `install.sh` lehnt außerdem alles außer Linux x86_64 sowie glibc < 2.28 ab (A-58).
  - Präfix (Review R17): unter Windows nur Laufwerksbuchstabe, Doppelpunkt und Trennzeichen (`C:Ordner` abgelehnt), kein Netzlaufwerk (DriveType Network), kein UNC; unter Linux absolut. `-Cosign`/`--cosign` wird auf den vollen Pfad der genannten Datei aufgelöst, ein bloßer Name nie über PATH gesucht.
  - Längengrenze unabhängig von LongPathsEnabled: unter Windows Präfix ≤ 249 − `max_relative_install_path` aus BUNDLE.json, damit jede Datei ≤ 250 Zeichen bleibt. Gemessen unter Windows 11 Build 26200 mit LongPathsEnabled = 1: Eine .pyd mit eingebettetem Manifest (fontTools `bezierTools`) lädt bei 250 Zeichen und scheitert bei 251, CreateProcess startet ein Programm bei 259 und scheitert bei 260. 0.1.0rc1: 148, also Grenze 101 (bei 101 installiert, 102 abgelehnt). Unter Linux Präfix ≤ 4094 − `max_relative_install_path` Bytes (PATH_MAX 4096 mit NUL; chinesische Namen zählen nach UTF-8-Bytes). Darüber Exit 2 mit Länge und Grenze, nichts angelegt; fehlende oder nicht ganzzahlige Vorhersage Exit 3. Die alte Prüfung (MAX_PATH 259, übersprungen bei LongPathsEnabled = 1) ließ 181 Zeichen durch, und `report` scheiterte danach mit ImportError.
  - Lange Schreibweise (zweite CI-Fix-Runde): `install.ps1` schreibt das Präfix lang (`Get-LongPath`: `GetFullPath` des tiefsten vorhandenen Ordners, der fehlende Rest wie angegeben), und die Grenze zählt diese Schreibweise, also den Pfad, den die Dateien bekommen, unter Windows PowerShell 5.1 und PowerShell 7 gleich, wie viel vom Präfix es auch schon gibt. Anlass: Auf dem windows-latest-Runner ist TEMP `C:\Users\RUNNER~1\…`; .NET erweitert 8.3-Namen, Windows PowerShell 5.1 (.NET Framework) bei einem nur teilweise vorhandenen Pfad je nach Namen nur unvollständig.
  - SHA-256 unter Windows über .NET (`System.Security.Cryptography.SHA256`), nicht `Get-FileHash`: Aus PowerShell 7 gestartet (Windows Terminal, Standard-Shell von GitHub) erbt Windows PowerShell 5.1 einen Modulpfad, auf dem Get-FileHash fehlt (gemessen in CI). Der Installer nutzt nur Befehle der Engine; ebenso `cleanroom_windows.ps1` und offline.yml.
  - Konsole (Review R13, A-51): `%LOCALAPPDATA%` und `~` (Windows: lange und 8.3-Schreibweise, jede Groß-/Kleinschreibung, nur ganze Ordnernamen) bzw. `${XDG_DATA_HOME}` und `~` (Linux) statt absoluter Benutzerordner, auch in Ausnahmetexten, wiedergegebenen Argumenten und der Ausgabe von uv, cosign und Python (zeilenweise gefiltert, Fehler bleiben auf stderr). Unter Windows verdeckt `Show` LOCALAPPDATA und USERPROFILE in drei Schreibweisen: der eigenen der Variable, der langen (`Get-LongPath`, seit der zweiten CI-Fix-Runde: auf dem Runner sind die Variablen 8.3 geschrieben, das Präfix und der uv-Cache darunter aber lang, so stand `C:\Users\runneradmin\…` in der Ausgabe von uv) und der kurzen (FileSystemObject `ShortPath`). Grenze: andere gemischte Schreibweisen sind nicht abgedeckt; die Programme geben die übergebenen oder kanonisch langen Pfade aus.
  - Fehlgeschlagene Installation (Review R14): Das Ziel bleibt, wie es war. Ein vom Installer angelegtes Präfix wird entfernt, ein vorher leeres wieder geleert, angelegte Elternordner werden entfernt, solange sie leer sind.
  - Meldungen zweisprachig in einer Zeile zh / en (Ausnahme von A-07, weil die Installer vor Python laufen; Test: jede Meldung ein Paar, Chinesisch zuerst, Englisch ohne Han); install.ps1 UTF-8 mit BOM, install.cmd CRLF. Sie gehören zur Wortprüfung (A-57, ARC-05) und zur zh-Prüfung.
- **Signatur** (Lesart von D-10 g und D-15; für G1 vorgemerkt):
  - Sigstore keyless nur in `release.yml` (`id-token: write`, cosign aus sigstore/cosign-installer v4.1.2): signiert werden die innere SHA256SUMS jedes Bündels (`SHA256SUMS.sigstore.json`) und eine SHA256SUMS über alle Release-Dateien. Identität `https://github.com/<owner>/<repo>/.github/workflows/release.yml@refs/tags/v<version>`, Aussteller `https://token.actions.githubusercontent.com`. Kein cosign im Bündel, kein gespeicherter Schlüssel, kein Secret.
  - Die Installer prüfen immer SHA256SUMS (jede gelistete Datei, keine ungelistete, Links gleich SYMLINKS). Ist cosign da (`-Cosign`/`--cosign` oder auf PATH), wird die Signatur immer geprüft; eine Ablehnung endet mit Exit 4, auch mit `-SkipSignatureCheck`/`--skip-signature-check` (Review R16; ersetzt die frühere Fassung, nach der der Schalter einen cosign auf PATH übergeht). Der Schalter lässt nur eine Installation ohne cosign weiterlaufen; die Meldungen nennen beide Ursachen (Ablehnung, fehlende Sigstore-Vertrauensbasis) und den Weg ohne Vertrauensbasis: auf einem vernetzten Rechner prüfen, dann ohne cosign auf PATH mit dem Schalter. `-Cosign` zusammen mit dem Schalter: Exit 2. Unsignierte Entwicklungsbündel brauchen immer den Schalter.
  - Dokumentierte Grenze (Review R12, Entscheidung: Grenze bleibt): Die Identität für cosign stammt aus BUNDLE.json (`release_identity`), die ein verändertes Bündel ebenso mitbringen kann; die Prüfung im Archiv belegt die Integrität, nicht die Herkunft. Die Herkunft belegen die Prüfung mit `cosign verify-blob` auf einem vernetzten Rechner vor der Übertragung und der Vergleich der Identität: Nach „signature verified: <Identität>“ fordern beide Installer auf, sie mit der Identität in den Release-Notes auf `https://github.com/Ammxri/neurogrid/releases` zu vergleichen (Konstante `$Releases`/`RELEASES`, D-15). README.txt Schritt 1 und die Installationsseiten sagen dasselbe; die Release-Notes veröffentlichen „Signer identity / 签名者身份“.
- **README.txt** (Review R18): Windows-Befehle in PowerShell-Syntax (`.\install.cmd`, `& "$env:LOCALAPPDATA\NeuroGrid\<v>\neurogrid.cmd" …`, `"zh,en"` in Anführungszeichen) mit einer Zeile dazu, was in cmd.exe anders ist; der cosign-Befehl auf einer Zeile; ein Test führt die Zeilen so aus, wie sie gedruckt sind. Ergebnisse bleiben auf dem Rechner (UF-08, CON-04): dort, wohin `--out` zeigt; ohne `--out` schreibt `check` results.json in den aktuellen Ordner, `report` neben results.json, `manifest` `.neurogrid/manifest.json` im Datensatz; nichts wird hochgeladen.
- **Workflows** (eine Definition je Workflow; jede Action per Commit-SHA gepinnt; oben `contents: read`, Schreibrechte nur in `release.build` (id-token), `release.draft` (contents) und `publish-pypi.publish` (id-token)):
  - `ci.yml` (Push auf dev und main, PRs; seit dd9ab93 auch `workflow_call`, einziger Aufrufer `release.yml`): Lint, Typen, Tests Windows und Linux × Python 3.11–3.13 mit PDF-Tests (`NEUROGRID_REQUIRE_PDF=1`, apt-Liste aus `pdf_linux_packages.json`, `PYTHONWARNDEFAULTENCODING=1`), Abdeckungsgrenzen (`tools/coverage_gates.py` im Testjob), Plattformvergleich einer Prüfung (berichtet, nicht erzwungen), Kommandozeile unter Windows PowerShell 5.1 und PowerShell 7, Lizenz-Gate mit Paketscan, Anforderungs-IDs.
  - `offline.yml` (Review R10, D-15): Push auf dev und main, von Hand und als `workflow_call` aus `release.yml` mit den signierten Bündeln (ein Tag läuft nur so). Jobs: `build` (Wheel, sdist, Doku und beide Bündel; danach `pytest -m bundle tests/packaging/test_bundle_real.py`: zwei Bauten bytegleich, verify, die dokumentierte Windows-Präfixgrenze), `offline-strace`, `cleanroom-linux` × 3, `glibc-refusal` (ubuntu:18.04), `pdf-debian12`, `cleanroom-windows` × {powershell, pwsh}. Gleichzeitigkeit je Ref: ein Push bricht ältere Läufe ab, Release-Läufe nie. Vorher lief offline.yml nur auf main.
  - `docs.yml` (Push auf main, PRs, von Hand; Bau und Browsertests); `corpus.yml` (von Hand und Push auf main; Cache-Schlüssel `hashFiles('tools/corpus_lock.json')`; hochgeladen werden nur summary.json und summary.md); `release.yml` (Tag `v*` oder von Hand, nur für Tags; nur ein Release-Entwurf); `publish-pypi.yml` (nur von Hand; Trusted Publishing, erst testpypi, dann pypi); `mirror-gitee.yml` (von Hand oder bei veröffentlichtem Release, nur mit `vars.GITEE_MIRROR == 'true'`).
  - Gitee-Release (Review R15, D-15): Der Job `gitee-release` nach `mirror` (Auslöser: veröffentlichtes Release oder von Hand mit der Eingabe `tag`) lädt Wheel, sdist, SHA256SUMS und SHA256SUMS.sigstore.json des GitHub-Release, prüft cosign (Identität von release.yml am Tag) und beide Prüfsummen erneut und stellt die Dateien mit dem Text aus `packaging/gitee-release.md` (fester Satz, Dateien, Prüfung, Identität, Link zum GitHub-Release) als Artefakt bereit. Das Gitee-Release legt der Projektverantwortliche von Hand am gespiegelten Tag an (Schritte in der Job-Zusammenfassung). Kein Gitee-API-Token, denn D-15 gibt nur `GITEE_SSH_KEY` frei; ein automatischer Upload bräuchte eine neue Entscheidung (`GITEE_TOKEN`, G1). Die Offline-Bündel bleiben nur auf GitHub.
  - Fehlerannotationen (TECH-05): Nach jedem pytest-Schritt in ci.yml, docs.yml und offline.yml annotieren vier Schritte je 10 fehlgeschlagene Tests (`tools/junit_annotations.py --offset 0/10/20/30 --limit 10`) und ein fünfter die Zahlen (`--summary --limit 40`); GitHub hält 10 Fehlerannotationen je Schritt, so sind bis zu 40 Fehler je Job ohne Anmeldung über die öffentliche API lesbar.
  - Zahlen als Hinweis-Annotation (2a49a0c, 27c3e90; TECH-05, NG-N08): Ein grüner Testjob schreibt seine Testzahlen („pytest summary :: 0 failed, 0 errors, … passed, … skipped“) und `tools/coverage_gates.py` die Abdeckungswerte als eine Annotation („coverage :: Kern: … % (limit 90 %) ok; Prüfer: … % (limit 80 %) ok“, bei einer gerissenen Grenze als Fehlerannotation). Damit sind Testzahlen und Abdeckung jedes Jobs ohne Anmeldung lesbar; vorher standen die Abdeckungswerte nur im Protokoll des Laufs, das eine Anmeldung braucht.
  - Test: Jede `--option`, die Workflows, CI-Skripte und Installer an `tools/<name>.py` übergeben, muss eine argparse-Option dieses Werkzeugs sein (gelesen aus dessen Parser).
- **Freigabe-Gate** (`tools/release_check.py`, nur Standardbibliothek): Tag = `v` + `__version__`, keine Entwicklungsversion; Checkout = Tag-Commit, enthalten in `origin/main`; sauberer Arbeitsbaum; kein `<REPO_URL>`/`<PYPI_RELEASE>` in `docs/` (außer `docs/umsetzung`) oder README.md; jede Lizenz aus REUSE.toml mit Text in `LICENSES/`. `release.yml` zusätzlich: `uv lock --check`, `uv sync --locked --no-build --python 3.12` mit `tools/licenses.py` und `tools/notices.py --download --check` (A-86), alles vor Bau und Signatur.
  - Testsuite am Tag-Commit (dd9ab93, dritte CI-Fix-Runde; V-06, NG-N04, TECH-05, V-01): `release.yml` ruft `ci.yml` als Job `suite` mit derselben Tag-Bedingung wie `build` auf, und der Entwurf braucht `build`, `suite` und `test`. Ein Release-Entwurf entsteht also nur, wenn Lint, Typen, die ganze Testmatrix (windows-latest und ubuntu-24.04 × Python 3.11–3.13), beide PowerShell-Jobs, das Lizenz-Gate und die Anforderungs-IDs auf dem getaggten Commit selbst bestehen; ein grüner Lauf eines früheren Commits zählt nicht. Anlass: Die Nutzerdoku sagt „Testsuite in der CI verifiziert“; auf dcec9bd stimmte das, auf 18da12f waren alle sechs Testjobs rot. Der Vergleichsjob von `ci.yml` lädt nur die Artefakte `results-*`. `tests/docs/test_docs_sync.py` scheitert, wenn kein Job von `release.yml`, der `ci.yml` nutzt, unter den `needs` des Entwurfs steht; `tests/packaging/test_workflows.py` prüft Auslöser und Jobs. Der Aufruf über `workflow_call` (eigene Gleichzeitigkeitsgruppe, eigener `env`-Block) lief auf GitHub noch nie; erst der erste Lauf an einem Release-Tag belegt ihn.
- **Paketscan** (A-49 „Scan der installierten Laufzeitpakete“): `tools/scan_runtime_network.py` durchsucht jede .py des Laufzeitsatzes per AST nach Netzwerkmodulen und Telemetrie- oder Update-Merkmalen; jeder Treffer braucht einen Eintrag in `license-gate/network_baseline.json` (Version der Distribution, Grund, Steuerung). Ungeprüfte, geänderte, veraltete und verwaiste Einträge lassen den Scan scheitern; Einträge für Distributionen, die auf der Plattform fehlen, werden übersprungen. Nicht abgedeckt: dynamische Importe und nativer Code (dafür die Flags und der Nachweis auf Betriebssystemebene).
- **Nachweis auf Betriebssystemebene** (präzisiert A-49, ändert den offline-strace-Punkt in A-77; Review R11):
  - Linux: das installierte Bündel im Container mit `--network none` unter `strace -f -qq -e trace=connect,sendto,sendmsg`. `tools/strace_check.py` wertet jeden AF_INET/AF_INET6-Aufruf an eine Adresse außer Loopback oder mit unlesbarer Adresse als Netzwerkversuch (Exit 1). Loopback ist erlaubt, gezählt und in `strace-summary.txt` gelistet, außer Port 9: Dorthin zeigt ein toter Proxy wie `http://127.0.0.1:9`, und ein Programm, das Proxy-Variablen folgt, sendet seinen Versuch dorthin. Die Linux-Reinräume entfernen alle Proxy-Variablen; `strace_check.py` liest seine eigene Zusammenfassung nie als Trace.
  - Windows (CI): WFP-Audit (Unterkategorie `{0CCE9226-69AE-11D9-BED3-505054503030}`) und ausgehende Sperrregeln für jedes .exe von Bündel, Installation und PDF-Browser; Ereignisse 5156/5157 dieser Programme an eine Adresse außer Loopback und an Port 9 müssen 0 sein; Regeln und Auditrichtlinie werden danach zurückgesetzt. Die Läufe setzen keine Proxy-Variablen; den toten Proxy setzt nur der lokale Reinraum (`-NoOsAudit`).
  - Auf dem Rechner des Projektverantwortlichen läuft nur der Reinraum auf Anwendungsebene (`-NoOsAudit`), ohne Änderung an Sicherheitseinstellungen; ein optionaler Test im Flugmodus steht in NACHBAU.md.
- **Reinräume** (neu in P5): Präfix und Arbeitsordner mit chinesischem Namen und Leerzeichen; jede .py der venv hat ihre `.cpython-312.pyc` (A-48); der längste Pfad unter dem Präfix ≤ `max_relative_install_path`; nichts bleibt in TEMP/TMPDIR (A-54); im Präfix BUNDLE.json, Interpreter und `tools/install_pdf_browser.py`; kein uv-Cache.
  - Windows: Installation bei genau der Präfixgrenze; ein Zeichen mehr muss mit Exit 2 abgelehnt werden (Länge und Grenze auf stderr, Elternordner nicht angelegt); alle v0.1-Befehle laufen aus dem tiefsten zulässigen Präfix. Ohne Browser endet `report --format pdf` mit Exit 2, legt `--out` nicht an und druckt den ausführbaren Hinweis aus A-85; mit `-PdfBrowserZip` Exit 0 und beide PDFs.
  - Linux: debian:12-slim, ubuntu:22.04 und ubuntu:24.04 mit `--network none`, ohne Python, uid 1000, Fixtures nur lesbar eingebunden; ohne Browser prüft der Linux-Reinraum nur Exit 2.
- **Stand der CI:**
  - 55335ca, offline (Lauf 40403791782): alle Jobs grün: beide Offline-Bündel aus uv.lock (unsignierte Entwicklungsbündel) mit den Bündeltests, PDF in debian:12-slim mit der dokumentierten Paketliste (`--network none`, strace), glibc 2.27 mit Exit 2 abgelehnt (ubuntu:18.04, A-58), Reinräume Windows (powershell 5.1 und pwsh, WFP-Audit, PDF), debian:12-slim, ubuntu:24.04 und ubuntu:22.04 (`--network none`, ohne Python, uid 1000), jeder v0.1-Befehl unter strace mit `--network none` (Linux).
  - 55335ca, ci (Lauf 40403791901): grün sind Lizenz-Gate mit Paketscan, Kommandozeile unter Windows PowerShell 5.1 und unter PowerShell 7 sowie die Anforderungs-IDs. Rot waren die Testjobs (ubuntu-24.04 mit Python 3.11/3.12/3.13 je 6 Fehler, windows-latest je 5–6); sie sind Gegenstand der zweiten CI-Fix-Runde („Übergreifend“).
  - dcec9bd (nach der zweiten CI-Fix-Runde), alles grün: ci (Lauf 40476578603) mit den Testjobs ubuntu-24.04 und windows-latest × Python 3.11/3.12/3.13 samt Abdeckungsgrenzen (die Zahlen stehen nur im Protokoll des Laufs, das eine Anmeldung braucht), Lizenz-Gate mit Paketscan, Kommandozeile unter Windows PowerShell 5.1 und PowerShell 7, Anforderungs-IDs und Plattformvergleich; offline (Lauf 40476578452) mit denselben neun Jobs wie auf 55335ca.
  - 18da12f (Behebung des G1-Befunds, A-89; gepusht): `offline` (Lauf 40609866836) ganz grün; `ci` (Lauf 40609866806) rot in allen sechs Testjobs: windows-latest mit Python 3.12 und 3.13 je 1 Fehler (3668 bestanden, 14 übersprungen), mit Python 3.11 3 Fehler (3665 / 15), ubuntu-24.04 mit Python 3.11/3.12/3.13 je 5 Fehler (3587 / 96); gemeinsam `tests/packaging/test_env_example.py`, dazu die Konsolentests von A-89 (Einzelheiten, Ursachen und Behebung: A-89 „Dritte CI-Fix-Runde“). Grün waren Lizenz-Gate, beide PowerShell-Jobs und die Anforderungs-IDs; der Plattformvergleich wurde übersprungen.
  - 27c3e90 (nach der dritten CI-Fix-Runde, Endstand P5), alles grün: `ci` (Lauf 40680346160) mit allen sechs Testjobs samt Abdeckungs-Gates, Lizenz-Gate mit Paketscan, Windows PowerShell 5.1, PowerShell 7, Anforderungs-IDs und Plattformvergleich (berichtet, nicht erzwungen); `offline` (Lauf 40680346176) mit allen neun Jobs. Testzahlen und Abdeckung laut den Hinweis-Annotationen (jeweils 0 Fehler):

    | Testjob | bestanden | übersprungen | Tests | Kern | Prüfer |
    |---|---|---|---|---|---|
    | windows-latest, Python 3.11 | 3681 | 16 | 3697 | 93,4 % | 97,3 % |
    | windows-latest, Python 3.12 | 3682 | 15 | 3697 | 93,5 % | 97,3 % |
    | windows-latest, Python 3.13 | 3682 | 15 | 3697 | 93,5 % | 97,3 % |
    | ubuntu-24.04, Python 3.11 | 3605 | 97 | 3702 | 93,3 % | 97,3 % |
    | ubuntu-24.04, Python 3.12 | 3605 | 97 | 3702 | 93,3 % | 97,3 % |
    | ubuntu-24.04, Python 3.13 | 3605 | 97 | 3702 | 93,3 % | 97,3 % |

    Grenzen der Gates: Kern ≥ 90 %, Prüfer ≥ 80 %. Welche Tests übersprungen wurden, steht nur im Protokoll und in `pytest-junit.xml` des Laufs.
- **Prüfvorgehen ab dem Ende von P5** (Entscheidung der Umsetzung nach der Kritik des Projektverantwortlichen vom 28.10.2026; gilt ab P6): Die volle Testsuite läuft nur in der CI (sechs Testjobs); lokal laufen nur die von einer Änderung betroffenen Tests. Testzahlen und Abdeckung werden aus den Hinweis-Annotationen der CI gelesen (2a49a0c, 27c3e90), nicht lokal gemessen. Die Umsetzungsdoku wird je Phase einmal geschrieben, nach grüner CI. Lange Läufe (G1-Abnahme, Korpustests) laufen nur einmal, auf dem Endstand. Die lokalen vollen Läufe früherer Runden (zuletzt dcec9bd: 3647 bestanden, 21 übersprungen, 127 abgewählt, 1 gescheitert; A-88) bleiben als Verlauf dokumentiert. Auf dem Endstand 27c3e90 lief deshalb keine volle lokale Suite, sondern nur die betroffenen Tests (A-88 „Lokaler Stand“).
- **Bekannte Grenzen:** Container-Images per Tag (der Digest wird zur Laufzeit in `images.txt` festgehalten, nicht gepinnt); die cosign-Version ist der Standard von cosign-installer v4.1.2; der Importtest mit gekürztem Interpreter ist lokal nur simuliert (echt sind die CLI-Befehle im Linux-Reinraum); Zuordnungslücke WFP/DNS-Client im Windows-Nachweis (auch A-49).

**A-88 Abnahme** (präzisiert A-59 und KONZEPT §6 G1; V-01, NG-F13, NG-F14, NG-N03, NG-N05, REP-00).
- **`tools/acceptance_g1.py`:**
  - Je Datensatz des Korpus (`tools/corpus_spec.json`: sechs Datensätze, fünf Formate) laufen `scan`, `check` (core + bids + gxdsl008, `--as-of 2026-10-11`, `--jobs 4`), `report --lang zh,en --format html,pdf`, `manifest` und `verify` als echte Prozesse des Startskripts `neurogrid` neben dem Interpreter, ohne PYTHON*-Variablen und im Ausgabeordner (Pfade vorher absolut); das zweimal (Lauf 1 mit englischer, Lauf 2 mit chinesischer Konsole), dazu einmal `check --jobs 1` auf ds004148. Geprüft wird mit eigener Lesart der Dateien, nicht mit dem Code des Produkts. Gegenüber der Spezifikation sind `scan`, `manifest` und `verify` hinzugekommen.
  - Exitcodes: 0 jedes Kriterium erfüllt, 1 ein Kriterium nicht erfüllt, 2 Werkzeugfehler (Korpus fehlt oder ist laut `tools/corpus.py verify` vorher oder nachher geändert, PDF-Browser fehlt laut `install_pdf_browser.py --check`, Ausgabeordner nicht leer ohne `--replace` oder im Korpus). „Fehlerfrei geprüft“ heißt: kein Exit 2 (D-13); Exit 1 von `check` ist auf ds002778, ds004148, ds000248 und psg-ipa erwartet.
  - Kriterien: kein Exit 2; `check` endet mit `summary.exit_code`, die anderen mit 0. Ein Datensatz mit verletztem CORE-M01-Befund zählt nicht zum Minimum, seine Formate auch nicht (Review R23). Konsole strikt UTF-8, der feste Satz als Zeile auf stdout, auf stderr nur übersetzte Bibliothekswarnungen, kein Traceback, kein Pfad von Datensatz oder Benutzerordner. Genau die erwarteten Dateien, kein Arbeitsordner und keine temporäre Datei übrig (A-54). results.json, scan.json und manifest.json gegen die mitgelieferten Schemas (Draft 2020-12 mit Formaten), results.json kanonisch.
  - Befundzeilen (ohne CSV, B1; Review R20): Zeilen über `data-key` und die zehn Zellen von `FINDING_CELLS`; ein leerer Wert nur als Text aus `EXPLAINED_EMPTY`; jede Zelle wird mit dem Befund verglichen: Klausel exakt (oder die erklärten Texte für Platzhalter, unbekannt, fehlend), Titel der Sprache mit Unterschlüssel, Messwert, jeder Parameter als „Name = Wert (Herkunft)“ und ein eigener Schwellwert, Datei, Kanal, Zeitbereich, übersetzter Grund; `[U+XXXX]` gilt als Zeichen. Je Regel min(Gesamt, 50) Zeilen, darüber genau der Satz `report.text.rule_more`.
  - HTML (Review R24): der feste Satz als sichtbarer Text von Deckblatt und Anhang und als meta description; seine Kopie im Druck-CSS zählt nicht.
  - PDF: das QA-Gate und ein unabhängiges pypdf-Orakel mit eigenem Schriftenlauf (auch durch Form-XObjects): nur Type0 mit CIDFontType2, FontFile2 und ToUnicode, BaseFont `^[A-Z]{6}\+NotoSansSC-(Regular|Bold)$`; fester Satz, Kopfzeile und Seitenzähler „x / y“ auf jeder Seite; A4 auf ±1,5 pt, Deckblatt hoch, letzte Seite quer; kein Codepunkt in U+2E80–2FDF, U+F900–FAFF oder U+2F800–2FA1F; jede Abschnittsüberschrift und die Regel-ID jedes Befunds im Text; `/Info` genau Title, Creator, Producer, CreationDate und ModDate mit Title = `report.title` und beiden Daten `D:<as_of>000000+00'00'`, kein XMP, kein `/ID`.
  - Determinismus: jede Datei über beide Läufe bytegleich, `--jobs 1` = `--jobs 4`. Ein späterer Lauf mit bytegleichen Dateien wird nur auf Exitcodes, Konsole, Dateiliste und Datenschutz der Konsole geprüft.
  - Datenschutz (NG-N05, A-51): Gesucht werden die Pfade von Datensatz, Ausgabe und Benutzerordner (absolut und aufgelöst, beide Trenner, JSON-maskiert, als `~`-Form, ohne Groß-/Kleinschreibung); Benutzer- und Rechnername (`USERNAME`/`USER`/`LOGNAME`, `COMPUTERNAME`/`HOSTNAME`, gethostname; ab 3 Zeichen, als ganzes Wort); Patienten- und Aufnahmefeld aus EDF/BDF-Köpfen ganz, EDF+-Unterfelder als ganze Wörter (Platzhalter ausgenommen); Startdatum als dd.mm.yy, yyyy-mm-dd und dd-MMM-yyyy (außer = `as_of`) und Startzeit (außer 00.00.00); in Rohordnern ohne `--show-paths` jeder echte relative Pfad, Dateiname, Dateistamm und Ordnername (Review R21; nicht im Manifest, ohne NeuroGrids eigenes Vokabular und reine Zahlen; die Ausgabepfade unter `--out` sind vorher entfernt); nicht ganzzahlige Rohalter als eigene Zahl; ganzzahlige Rohalter im Zusammenhang (Review R22): als eigene Zahl bis 40 Zeichen hinter der Probanden-ID (nie über `<tr` oder einen Zeilenumbruch), nach einer Altersbeschriftung mit Trenner (age, Alter, 年龄, aged) oder vor einer Alterseinheit (years, 岁, Jahre), nicht in den PDF-Bytes; in results.json und scan.json unter Altersschlüsseln nur Zahlen oder 10-Jahres-Stufen; Hex-Folgen ab 16 Zeichen außer Befundschlüsseln und den deklarierten SHA-256 (also kein Signal-Hash). Durchsucht werden Konsole, results.json, scan.json, HTML (ohne die data-URIs der Schriften), PDF-Text, PDF-Bytes (latin-1 und UTF-16BE) und `/Info`; manifest.json nennt die Dateien des Datensatzes mit Absicht (A-82) und wird nur nach Pfaden, Benutzer und Rechner durchsucht. Die Konsole nennt das `--out` des Bedieners mit Absicht; es wird vor der Suche entfernt.
  - V-06: geladen sind genau core, bids und gxdsl008; keine Regel, Quelle oder Klauselnummer der Norm (die Norm steht im Werkzeug einmal als `NORM`, geprüfte Nennung in `tests/unit/test_norm_independence.py`, Tests bauen ihre Beispiele daraus).
  - Ausgabe: `summary.json` (Schema „neurogrid-acceptance-g1/1“; nur Zahlen, Exitcodes, Dauern, Größen, Seiten und Problemtexte ohne Werte aus den Daten, Namen nur relativ zu `--out`) und `summary.md` (deutsche Tabelle mit V-01-Checkliste und V-06-Zeile). „Kriterien erfüllt“ heißt: die Kriterien dieses Laufs (Review R29); `g1.outside_this_run` und summary.md nennen, was der Lauf nicht abdeckt (Skalierungstest 1000 × 64, Linux offline unter strace, Reinraum debian:12-slim, Abdeckungsgrenzen). Die Läufe bleiben unter `--out`; `corpus.yml` lädt nur die beiden Zusammenfassungen hoch. Die Konsolenzeile des Ergebnisses ist ASCII (ein cp1252-stdout brach vorher an „≥“ ab).
  - V-01-Checkliste: Punkte 1–5 gelten als erfüllt, wenn ihre Matrixzeilen (NG-F01, NG-F02, NG-F05, M01–M13, RP-09/GX-00–GX-05) „erfüllt“ sind und kein Laufkriterium dagegen spricht; Punkt 2 (Konvertierung nach BIDS) und Punkt 4 (Metriken) haben kein Laufkriterium (`run_ok` null, in summary.md „– (kein Laufkriterium)“). Punkte 6 (Bericht) und 7 (JSON) stützen sich nur auf den Lauf, nicht auf die Matrix; Punkt 6 verlangt dazu alle G1-Kriterien des Laufs. Der Kommentar über `V01_ITEMS` im Werkzeug sagt seit d269cb9 dasselbe: Die Matrixzeilen der Punkte 6 und 7 werden gezeigt, aber nicht verlangt; NG-F14 steht seit P5 auf `erfüllt`, nur NG-F13 bleibt bis G1 `nicht verifiziert` und wird dort gesetzt (vorher hieß es, NG-F13 und NG-F14 würden erst nach G1 gesetzt). V-01 insgesamt braucht alle sieben Punkte und alle G1-Kriterien.
- **Ergebnis auf dem Korpus:**
  - Abnahme vor dem Review (4587546, 6a4f737): je 6 von 6 Datensätzen, Formate BDF, BrainVision, EDF, EEGLAB und FIF, Minimum erfüllt, alle Kriterien dieses Laufs erfüllt, `--jobs 1` = `--jobs 4`, Korpus unverändert, summary.md „V-01 insgesamt: erfüllt“ (nur die Kriterien dieses Laufs), V-06 ja. Ein Gegenlauf auf 944037c mit anderem Ausgabepfad und anderer Uhrzeit ergab dieselben 42 Produktdateien (je Datensatz results/scan/manifest-JSON und HTML/PDF zh/en, SHA-256) wie der Lauf auf 4587546.
  - Nach der Fix-Runde (strengere Prüfungen R20–R24, R29): drei Datensätze (ds002778-1.0.5, ds004148-1.0.1, psg-ipa-1.0.0), alle bestanden, Exit 0; für psg-ipa entstehen 556 verbotene Rohnamen, keiner steht in den Ausgaben.
  - Voller Lauf aller sechs Datensätze auf dcec9bd (Stand nach der zweiten CI-Fix-Runde; `.local/p5/ci2/g1_summary_dcec9bd.md`): 5 von 6 bestanden, Formate BDF, BrainVision, EDF und FIF, Minimum (≥ 3 Datensätze in ≥ 2 Formaten) erfüllt, beide Läufe bytegleich, `--jobs 1` = `--jobs 4` (ds004148), Korpus unverändert. ds004504-1.0.9 (EEGLAB) scheiterte nur am Konsolenbefund von Lauf 1 (Traceback mit Laufwerkspfad, Benutzerordner und Benutzername, kein UTF-8; `check` 935,6 s statt 299,4 s; Ursache und Behebung A-89); Befundzeilen, HTML, PDF und Dateien aller sechs Datensätze ohne Problem. Damit waren „alle Kriterien dieses Laufs“ und V-01 Punkt 6 (er verlangt alle G1-Kriterien) nicht erfüllt, V-06 ja. Ein Lauf mit `tools/acceptance_g1.py --datasets ds004504-1.0.9` auf der Behebung bestand ohne Problem, results.json und die vier Berichte bytegleich zum Lauf auf dcec9bd.
  - Voller Lauf auf 18da12f (`.local/p5/ci3/g1_summary_18da12f.md`, Protokoll `.local/logs/g1_18da12f.log`; Python 3.12.15, Windows 11, `check --jobs 4`, zwei Läufe): 6 von 6 Datensätzen bestanden, Formate BDF, BrainVision, EDF, EEGLAB und FIF, Minimum erfüllt, alle Kriterien dieses Laufs erfüllt, beide Läufe bytegleich, `--jobs 1` = `--jobs 4` (ds004148-1.0.1), Korpus unverändert, V-01-Checkliste des Laufs „V-01 insgesamt: erfüllt“, V-06 ja, keine Probleme; Dauer 151 min 40 s. ds004504-1.0.9 lief mit `check` in 333,0 / 324,6 s (auf dcec9bd 935,6 / 299,4 s).
  - Weil die dritte CI-Fix-Runde den Windows-Weg von `check --jobs` änderte (`quiet_pool`, `on_null_device`; A-89), läuft die Abnahme einmal auf dem Endstand 27c3e90: <G1 27c3e90>.
- **Speicher:** Ein G1-Korpuslauf auf einem ausgelasteten Rechner (parallele Läufe) ergab einen `MemoryError` in CORE-M09 (autoreject) auf ds002778 und einen Lesefehler bei einer psg-ipa-Aufnahme; Zeilen-, HTML-, PDF- und Datenschutzprüfungen meldeten nichts, die Ursache war der freie Arbeitsspeicher. G1-Läufe deshalb auf einem Rechner mit genug freiem RAM oder Datensatz für Datensatz (`--datasets`). Ebenso kann `tests/unit/test_quality_sample.py` (5 Prozesse) unter Last beim Aufbau mit `MemoryError` scheitern; allein besteht er.
- **Skalierungsgrenzen** (A-59; `tests/perf/test_report_scaling.py`, Marker `perf`, Standard abgewählt):
  - Daten: `tools/gen_fixtures.py` `scale_results(recordings=1000, channels=64, worst_case=True)` (CLI `--scale-results OUT.json [--recordings N] [--channels C] [--typical]`), Seed 20261023, as_of 2026-10-23, Befunde aus dem echten core-Paket und Regelmotor. Schlimmster Fall: alle Kanäle verletzen CORE-M07-01 und CORE-M08-01 (128 742 Befunde, results.json 149 MB); typischer Fall 6 110 Befunde.
  - Gemessen wird der echte Prozess `report --lang zh,en` (Wandzeit, Spitzenspeicher des Prozessbaums), dazu je Stufe der größere Wert der beiden Sprachen; geprüft werden außerdem die Struktur nach A-59 (≤ 50 Zeilen je Regel, genauer Rest, 1000 Metrikzeilen), Bytegleichheit und das QA-Gate.
  - Grenze = ⌈1,5 × größter Wert wiederholter Läufe am 26.10.2026⌉ auf dem Messrechner (AMD Ryzen 9 6900HX, 8 Kerne/16 Threads, 31 GB RAM, Windows 11 Build 26200, Python 3.12.15, Playwright 1.63.0, Shell 1243). PRD und KONZEPT setzen keine Grenze; diese schützen vor Rückschritten und gelten für einen solchen Rechner, solange er wach bleibt.
  - Schlimmster Fall (Messwert → Grenze): `--format html` 21,4 s / 1703 MB → 33 s / 2555 MB; `--format html,pdf` 108,8 s / 1929 MB → 164 s / 2894 MB; je Sprache Parsen 4,3 → 7 s, Rendern 7,8 → 12 s, Drucken 5,0 → 8 s, QA-Gate 44,6 → 67 s; Seiten zh/en 99/106 → 149/159; PDF 730 131/728 364 B → 1 095 197/1 092 546 B; HTML 1 252 705/1 026 261 B → 1 879 058/1 539 392 B.
  - Typischer Fall: `html` 13,0 s / 364 MB → 20 s / 546 MB; `html,pdf` 92,1 s / 1284 MB → 139 s / 1926 MB; Parsen 0,6 → 1 s, Rendern 4,4 → 7 s, Drucken 4,7 → 8 s, QA-Gate 36,2 → 55 s; Seiten 136/142 → 204/213; PDF 835 710/854 455 B → 1 253 565/1 281 683 B; HTML 1 309 136/1 081 128 B → 1 963 704/1 621 692 B.
  - Ausgelassen sind zwei Nachtwerte des typischen Falls (8 370,2 s Berichtsprozess, 14 936,9 s zh-Gate): Der Rechner schlief in beiden Messungen (Modern Standby; Windows-Systemprotokoll, Kernel-Power 506/507: 8 282,0 s und 14 907,0 s Schlaf); ohne den Schlaf bleiben 88,2 s und 29,9 s wie in den anderen Läufen.
- **PDF-Testumgebung:**
  - Marker `pdf`; ohne Shell werden die Tests mit Grund übersprungen, mit `NEUROGRID_REQUIRE_PDF=1` (CI und der letzte lokale Lauf) scheitern sie. Die Fixture `pdf_shell` gilt für die Sitzung; Coverage mit `concurrency = ["thread", "greenlet"]` (Playwrights synchrone API wechselt Greenlets).
  - Die Shell (Revision 1243) liegt im Standardordner (`%LOCALAPPDATA%\NeuroGrid\pdf-browser`), installiert mit `tools/install_pdf_browser.py`; nach Testläufen `install_pdf_browser.py --check` (findet Dateien, die die Shell in ihren Ordner schrieb). Mit dieser Umgebung liefen die pdf-Tests und die Abnahmetests ohne PDF-Übersprung.
  - Pfadgrenzen: Jeder Test, der die Shell startet, nimmt seinen Arbeitsordner aus `kernel.pdf.browser_work`. Was Browsertests als `file://` öffnen, liegt in einem Sitzungsordner direkt unter dem temporären Ordner (`browser_root`, höchstens 120 Zeichen; gemessen: ab 260 Zeichen lädt Windows eine solche Seite nicht mehr). `tests/packaging/test_install_ps1.py` arbeitet in einem kurzen Ordner (höchstens 120 Zeichen), damit seine Ergebnisse nicht von `--basetemp` abhängen. `test_pdf_tests_pass_with_a_long_basetemp` lässt Browsertests in einem verschachtelten pytest mit 200 Zeichen `--basetemp` gegen eine frische Kopie der Shell laufen, die bytegleich bleiben muss.
- **Nur in der CI prüfbar** (D-09; lokal gibt es kein Linux und keine Änderung an Sicherheitseinstellungen): die Linux-Zweige von Sperrdateien (`fcntl.flock`), Arbeitsbasis und Treiberordner; die Startprüfung mit ldd; die Linux-Reinräume und der strace-Nachweis; der WFP-Nachweis unter Windows; PowerShell 7 (lokal nicht installiert); die Testjobs und Abdeckungsgrenzen auf Linux und auf windows-latest; `corpus.yml` und `docs.yml` (nur main); `release.yml`, `publish-pypi.yml` und `mirror-gitee.yml` (vom Projektverantwortlichen gestartet). Stand: auf dcec9bd `ci` und `offline` ganz grün (A-87), damit auch Testjobs und Abdeckungsgrenzen unter Linux und auf windows-latest; die POSIX-Zweige von A-89 kamen erst mit 18da12f, wo die Testjobs rot waren, und sind seit der dritten CI-Fix-Runde auf 27c3e90 in allen sechs Testjobs grün (`ci` 40680346160, `offline` 40680346176; A-87, A-89).
- **Lokaler Stand:** volle Suiten der Fix-Runde unter Windows 11: Bereich report (c9a536a) 3502 bestanden / 23 übersprungen; Bereich linux (191a62a) 3510 / 25 mit `PYTHONWARNDEFAULTENCODING=1`; Bereich bundle (d42bbf4) 3498 / 23. Zusammengeführt auf 55335ca (Windows 11, Python 3.12, `NEUROGRID_REQUIRE_PDF=1`, `PYTHONWARNDEFAULTENCODING=1`): 3597 bestanden, 24 übersprungen, 127 abgewählt, 1 gescheitert (der strace-Test der Datenschutzseite, ein inhaltlicher Konflikt zwischen R11 und R25 beim Zusammenführen, behoben in 181654e). Nach der zweiten CI-Fix-Runde auf dcec9bd (gleiche Umgebung): 3647 bestanden, 21 übersprungen, 127 abgewählt, 1 gescheitert, nur an seiner Zeitgrenze: `tests/integration/test_quality_review_p3.py::test_one_recording_with_jobs_4_equals_jobs_1` mit 122,5 s statt höchstens 120 s, während die ganze Suite auf dem ausgelasteten Rechner 4 h 07 min lief (sonst etwa 30 min). Sein mitgeschnittenes stderr zeigt denselben toten Pool-Prozess wie der G1-Befund (`SpawnProcess-18`, WinError 6 in `call_queue.get`, A-89); danach rechnete der Lauf die Teile allein, das Ergebnis war gleich. Allein besteht er, in der CI ist er grün. Endstand 27c3e90: Nach dem Prüfvorgehen ab dem Ende von P5 (A-87) lief keine volle lokale Suite. Die volle Suite belegt die CI (`ci` 40680346160, alle sechs Testjobs ohne Fehler: windows-latest 3681–3682 bestanden und 15–16 übersprungen von 3697, ubuntu-24.04 3605 bestanden und 97 übersprungen von 3702; Tabelle in A-87). Lokal (Windows 11, nur die von der dritten CI-Fix-Runde betroffenen Tests): Python 3.12 184 bestanden, 5 übersprungen, 52 abgewählt in 41 min; Python 3.11 18 bestanden, 4 übersprungen (`.local/logs/targeted_27c3e90_py312.log`, `targeted_27c3e90_py311.log`).
- **zh-Prüfpaket** (A-07, STOPP G1): `tools/zh_review_package.py` (Basis a44d592, das Gerüst aus P1) listet jeden ausgelieferten zh-Text mit Quelle und Schlüssel und markiert neu oder geändert; ein Vollständigkeitstest vergleicht mit `git ls-files` und einer geprüften Liste nicht angezeigter Stellen. Dazu kommen zwei Beispiel-PDFs (`report.zh.pdf` von ds002778-1.0.5 und psg-ipa-1.0.0 aus Lauf 1 eines G1-Laufs; nur bestandene Datensätze, deren PDF noch die vom Lauf notierte Größe hat). Ausgabe `.local/acceptance/zh_review/zh_review.md` (nicht versioniert); Exit 2 ohne lesbaren Basis-Commit oder Beispiel. Das Paket für G1 wird nach dem letzten G1-Lauf erzeugt, aus dessen Lauf 1 die Beispiel-PDFs stammen (D-17: nach dem Merge der zweiten CI-Fix-Runde; der letzte G1-Lauf ist der auf 27c3e90); welche zh-Texte seit der ersten Fassung neu sind, nennt A-86.
- **Für G1 vorgemerkt:** Die nicht als UTF-8 lesbare Ausgabe (Byte 0xFC bei `check` auf ds004148) aus der Spezifikationsphase kam in keinem Lauf von P5 wieder; wahrscheinlich war es derselbe Worker-Traceback wie im G1-Befund auf dcec9bd („ungültig“ in cp1252, A-89).

**A-89 Hilfsprozesse ohne Konsole, `platform` ohne WMI** (G1-Befund auf dcec9bd, behoben auf p5-g1-console, Merge 18da12f; dritte CI-Fix-Runde auf p5-ci3-posix, p5-ci3-win311 und p5-ci3-docs, Merges ce87432, f3fe478 und 1dd0eac, CI auf 27c3e90 grün; präzisiert A-51, A-79, A-85, D-14; NG-N05, NG-N03, TECH-05, NG-F07; für STOPP G1 vorgemerkt).
- **Befund:** G1-Lauf, ds004504-1.0.9, `check --jobs 4`, Lauf 1: Ein Pool-Prozess (`SpawnProcess-2`) starb in `call_queue.get` an `self._sem.release()` mit `OSError: [WinError 6] Das Handle ist ungültig`; multiprocessing schrieb `Process SpawnProcess-2:` mit Traceback auf stderr (Installationspfade mit Benutzername, Text in der Codepage der Konsole, kein UTF-8). Der Pool war damit kaputt, jede offene Aufnahme lief allein: 935,6 s statt 299,4 s. Ebenso im vollen Testlauf (`test_one_recording_with_jobs_4_equals_jobs_1`, `SpawnProcess-18`, Zeitgrenze 120 s gerissen).
- **Ursache:** CPython 3.12 fragt in `platform.uname()` zuerst WMI (`_wmi.exec_query`, `PC/_wmimodule.cpp`). Die Funktion wartet 1000 ms auf COM und 100 ms auf die Verbindung (gh-112278) und kehrt dann mit WAIT_TIMEOUT zurück, während ihr Abfrage-Thread weiterläuft: Er liest seine Handles über einen Zeiger auf `struct _query_data` im Stackrahmen der beendeten Funktion und schließt am Ende den Wert, der dort inzwischen steht (`CloseHandle(data->writePipe)`), also irgendein Handle des Prozesses (auf dem Messrechner jedes Mal den Wert 24; welcher Wert dort steht, hängt vom späteren Stackinhalt ab). Im Worker kommt `platform.uname()` mit der Stichprobe (`import scipy.signal` → array_api_compat → `numpy.testing` → `platform.machine()`); getroffen wurde das Semaphor der Aufrufwarteschlange, die nächste `get` scheiterte. Auf dem Messrechner läuft jede WMI-Abfrage in den Abbruch (WinError 258 nach etwa 0,3 s, auch ohne Last). Nur manchmal: Es trifft nur, wenn der gelesene Wert der des Semaphors ist; das hängt davon ab, welche Werte der Elternprozess beim Start in den Worker dupliziert. Das Herunterfahren des Pools war nicht beteiligt.
- **Nachweis:** Handle-Monitor in jedem Prozess (sitecustomize; Typ und Gültigkeit der Warteschlangen-Handles im 1-ms-Takt, bei einer Änderung die Stacks aller Threads), `compute_all` auf der 19-Kanal-EDF des Tests mit `--jobs 4`, je 9 Läufe mit 3 Pools auf dcec9bd. Mit WMI: 7 von 9 Läufen mit totem Worker (10 Tode); 14 der 22 Worker, deren Semaphor auf dem Handle-Wert 24 lag, verloren es, jedes Mal während `platform.uname()` nach der abgebrochenen WMI-Abfrage; keiner der 39 Worker mit anderem Wert. Mit gesperrtem `_wmi`: 0 von 9 Läufen, keine Schließung (23 Worker mit dem Semaphor auf 24). Mit der Behebung (gleicher Monitor, 6 Läufe mit 3 Pools): kein Worker verlor sein Semaphor oder starb (36 Worker, 10 mit dem Semaphor auf 24). Ohne NeuroGrid nachgestellt: frische spawn-Prozesse, `platform.machine()` und 3 s warten: 2 von 24 verloren ihr Handle 24 (ein Event), mit `avoid_wmi()` 0 von 16 (6 davon mit einem Semaphor auf 24). CPython 3.13 kopiert die Struktur in den Thread; 3.12 erhält nur noch Sicherheitskorrekturen.
- **Behebung:** `kernel/processes.py` `avoid_wmi()`: `platform` fragt WMI nicht und antwortet aus `ver` und der Umgebung wie vor 3.12. Aufgerufen in `cli.main()` und im Initializer jedes Pool- und loky-Prozesses, bevor eine Bibliothek `platform` fragt, ebenso in der Testsitzung (`tests/conftest.py`).
- **Kein Hilfsprozess schreibt auf die Konsole** (Verteidigung in der Tiefe):
  - Start: Die Pools nutzen `pool_context()` (die gesetzte Startmethode, sonst die der Plattform). Windows (spawn): eigener Popen wie `popen_spawn_win32` (CPython 3.11–3.13), aber mit STARTUPINFO: stdin, stdout und stderr sind das Nullgerät, nur dieses Handle wird vererbt. POSIX (fork, spawn, forkserver): Der Elternprozess leert seine Puffer und legt die Deskriptoren 0–2 (seit 3d212b5 auch die Deskriptoren hinter den sys-Strömen, siehe „Dritte CI-Fix-Runde“) nur für den Start auf /dev/null; Kind, forkserver und dessen Kinder erben es. Damit ist auch alles vor dem Initializer stumm: Interpreterstart, Entpicklung und der Bootstrap von multiprocessing mit seinem `Process …:`-Traceback. Mit spawn und forkserver startet `pool_context()` in diesem Fenster auch den resource tracker von multiprocessing (läuft er schon, wird er nur geprüft, ist er tot, neu gestartet). Sonst startete ihn das erste benannte Semaphor in `ProcessPoolExecutor.__init__` mit den Deskriptoren der Konsole und `sys.stderr.fileno()`, und endete der CLI-Prozess ohne Finalizer (SIGTERM, SIGKILL, OOM-Killer), schrieb er `resource_tracker: There appear to be N leaked semaphore objects` mit Installationspfad auf die Konsole. fork, unter Linux bis 3.13 die Voreinstellung, entfernt die Semaphoren sofort und braucht keinen tracker.
  - Initializer: `to_null_device()` als erster Schritt von `worker_start` und `loky_worker_start` legt 0–2 und sys.stdin/stdout/stderr erneut auf das Nullgerät; loky-Prozesse und ihr resource tracker erben es. In NeuroGrids eigenem Prozess wirkt es nicht.
  - PDF (A-85): Playwright startet den Treiber mit `sys.stderr.fileno()`; `driver_environment()` legt sys.stderr während des Starts auf das Nullgerät. Der Validator (A-06) läuft schon mit `capture_output` und `stdin=DEVNULL`, seine Ausgabe wird nie gezeigt.
  - Was der Elternprozess braucht, kommt weiter über den Pool: Werte, Ausnahmen als Daten und der Tod eines Workers (BrokenProcessPool, Wiederholung allein bzw. `quality.worker_failed`, D-14). Stirbt ein Pool- oder loky-Prozess oder kommt ein Teil nicht an, sagt `check` das über NeuroGrids eigenen Kanal: einmal, bevor die Wiederholungen beginnen, die übersetzte Zeile `cli.check.recomputed` auf stdout (zh/en/de, mit der Zahl der Aufnahmen, deren Arbeit ohne ihn weitergeht; `compute_all(on_recompute=…)` über `CheckOptions.on_recompute`). results.json bleibt davon unberührt (NG-N03). Ein loky-Prozess, der stirbt, wird im Pool-Prozess gezählt (`sample.refits()`, Aufgabe `autoreject_part`). `--debug` bleibt wie dokumentiert (bereinigter Traceback eines internen Fehlers im eigenen Prozess).
  - Bibliothekswarnungen eines Workers erscheinen nicht; mit `--jobs 1` erscheinen sie wie bisher als übersetzte Kategorie. Die Konsole unterscheidet sich darin zwischen `--jobs 1` und `--jobs N`, results.json nicht. Eine Weitergabe an den Elternprozess brächte keine Gleichheit: Die loky-Prozesse von autoreject ignorieren Warnungen (D-14), während dieselbe Anpassung mit `--jobs 1` im CLI-Prozess läuft, und Warnungen beim Import kommen je Prozess einmal. Die Zeile sagt nur, dass die Ergebnisse nicht betroffen sind; A-51 ist in beiden Fällen erfüllt.
- **Grenzen:** Unter POSIX gehen während des Starts eines Pool-Prozesses oder des resource trackers Ausgaben anderer Threads des Elternprozesses auf /dev/null (NeuroGrid schreibt dann nichts). Was eine Bibliothek direkt auf das Konsolengerät schreibt (Windows `CONOUT$`, `msvcrt.putwch`; POSIX `/dev/tty`), umgeht beide Schichten: Pool- und loky-Prozesse bleiben an der Konsole (kein CREATE_NO_WINDOW, DETACHED_PROCESS oder setsid), damit Strg+C auch sie beendet; abgetrennt würde der Lauf nach Strg+C auf ihre laufenden Aufgaben warten (A-77: Strg+C beendet den Lauf). Suche in der Umgebung von uv.lock (Windows): im Python-Code nur click/typer (CLI-Prozess: Pager, Tastatureingabe), in den Binärdateien nur die statisch gelinkte Fortran-Laufzeit von OpenBLAS und scipy (fitpack, odrpack); in keinem Lauf erreichte etwas auf diesem Weg die Konsole. `avoid_wmi()` ersetzt die private Funktion `platform._wmi_query` (CPython 3.12/3.13); benennt ein späteres CPython sie um, wirkt der Schutz still nicht mehr, die Audit-Tests (`test_no_pool_worker_asks_wmi`, `test_avoid_wmi_keeps_platform_answering_without_a_wmi_query`) bemerken das unter Windows. Ein kaputter Pool (etwa nach einem echten Speichermangel) rechnet weiter jede offene Aufnahme allein nach (D-14); behoben ist nur der Auslöser der G1-Tode. Den resource tracker deckt der Schutz nur, wenn NeuroGrid ihn zuerst startet (im CLI-Prozess startet ihn heute nichts vorher). Die POSIX-Zweige (fork, spawn, forkserver, resource tracker) prüft nur die CI (lokal kein Linux); unter Windows lief die Behebung lokal nur mit Python 3.12 (`NullStdioPopen` gegen den Quelltext von 3.11 und 3.13 gelesen). Auf 18da12f waren in der CI alle sechs Testjobs rot (`ci` 40609866806; dritte CI-Fix-Runde unten), auf 27c3e90 sind alle grün (`ci` 40680346160). Weitere Grenzen aus der dritten CI-Fix-Runde stehen dort.
- **Tests:** `tests/unit/test_processes.py` (jede Startmethode der Plattform, Start und Initializer je allein, Gegenprobe ohne beide, `avoid_wmi`; POSIX mit spawn und forkserver: ein Prozess mit NeuroGrid-Pool, mit SIGKILL beendet, lässt stderr leer, der tracker räumt das Semaphor trotzdem ab, Gegenprobe mit einfachem Pool zeigt die Warnung); `test_quality_pipeline.py` und `test_quality_review_p3.py`: `on_recompute` einmal vor den Wiederholungen mit der Zahl der Aufnahmen, auch für einen sterbenden loky-Prozess, nie ohne Tod; `tests/integration/test_worker_console.py`: das geschlossene Warteschlangen-Semaphor deterministisch (unter Windows das echte Handle), kein Worker fragt WMI (Audit-Ereignis `_wmi.exec_query`), echter Lauf `check --jobs 2`, dessen Worker bei Start, Bootstrap und Ende schreiben und von denen einer stirbt (Konsolen- und Datenschutzprüfung der G1-Abnahme, results.json = `--jobs 1`, auch der CLI-Prozess fragt kein WMI; die Zeile `cli.check.recomputed` genau einmal bei `--jobs 2`, nie bei `--jobs 1`). Auf dcec9bd scheitern alle drei. Die Tests der dritten CI-Fix-Runde stehen im nächsten Punkt.
- **Dritte CI-Fix-Runde** (p5-ci3; TECH-05, NG-N05, NG-N03, NG-F07; Befund der CI auf 18da12f, `ci` 40609866806; behoben auf drei Zweigen, gemergt in ce87432, f3fe478 und 1dd0eac; CI auf 27c3e90 ganz grün, `ci` 40680346160, `offline` 40680346176, Zahlen in A-87):
  - **Befund:** Rot waren alle sechs Testjobs. Auf allen scheiterte `tests/packaging/test_env_example.py::test_example_lists_every_variable_of_code_and_workflows`. Auf ubuntu-24.04 mit Python 3.11–3.13 dazu `tests/unit/test_processes.py::test_the_resource_tracker_of_a_pool_has_no_console[forkserver]` und `[spawn]` (`assert not True`), `test_pool_processes_start_on_the_null_device[fork]` (Traceback statt leerer Ausgabe) und `tests/integration/test_worker_console.py::test_check_with_jobs_keeps_the_console_clean_when_workers_write_and_die` (`AssertionError: 1`). Auf windows-latest mit Python 3.11 dazu derselbe CLI-Test (`AssertionError: 2`) und `test_a_worker_whose_call_queue_semaphore_is_closed_leaves_the_console_clean` (Traceback aus `queues.py`). Die Zahl in der Meldung des CLI-Tests war jeweils nur der Wert von `--jobs` des gescheiterten Laufs.
  - **resource tracker unter POSIX** (Wettlauf im Test, kein Produktfehler; 919bd11): Ein einfacher tracker erbt die Deskriptoren 0–2 und `sys.stderr.fileno()` (`util.spawnv_passfds`) und schließt nur stdin und stdout; `subprocess.run` mit `capture_output` kehrt deshalb erst zurück, wenn er aufgeräumt hat und endet. NeuroGrids stiller tracker hält keine Pipe: `run()` kehrt schon beim SIGKILL des Prozesses zurück, während der tracker womöglich noch startet, und er entfernt das Semaphor erst danach (nach EOF seines Deskriptors). Das Aufräumen selbst ist unverändert. Der Test gibt jetzt die PID des trackers aus und wartet auf dessen Ende (unter Linux pidfd mit select, höchstens 60 s; sonst Abfrage mit `os.kill`), bevor er das Semaphor sucht; eine neue Prüfung verlangt, dass der tracker endete.
  - **fork mit Strömen auf anderen Deskriptoren** (Produktfehler gegen den Modul-Docstring; 3d212b5): `null_descriptors` legte nur 0–2 auf /dev/null. Ein geforktes Kind erbt die Objekte `sys.stdout` und `sys.stderr` des Elternprozesses; schreiben sie auf einen Deskriptor über 2 (pytests capfd, ein einbettendes Programm, ein sitecustomize, ein Strom auf einer Kopie der Konsole), erreichte der Worker die Konsole vor `to_null_device`. Die Ströme der CLI liegen auf 0–2, die Lücke war nur so erreichbar; spawn und forkserver starten frische Interpreter auf 0–2 und waren nicht betroffen. Jetzt legt `null_descriptors` auch die Deskriptoren hinter `sys.stdout`, `sys.stderr`, `sys.__stdout__` und `sys.__stderr__` auf /dev/null und stellt jeden mit seinem Vererbungs-Flag wieder her; so bekommt auch der resource tracker über `sys.stderr.fileno()` das Nullgerät. Ein im Fenster geforktes Kind (`_after_fork_in_child`, scharf geschaltet über den Stapel `_SAVED`) schließt die gesicherten Kopien der Konsolen-Deskriptoren und bindet sys.stdin/stdout/stderr vor dem Bootstrap von multiprocessing an das Nullgerät: Es hält keinen Konsolen-Deskriptor und schreibt nie durch Stromobjekte, deren Pufferlock ein anderer Thread des Elternprozesses beim Fork halten konnte. `_START_LOCK` ist ein RLock und die Kopien liegen auf einem Stapel, verschachtelte Fenster stellen richtig wieder her. Nebenwirkung: Nach einem SIGKILL des CLI-Prozesses halten verwaiste fork-Worker keinen Leser der Konsolen-Pipe mehr offen.
  - **`--jobs 1` unter Linux: native Ausgabe von onnxruntime** (223206b, 7f5b3b0): Mit `--jobs 1` läuft die ganze Stichprobe (pyprep, autoreject, ICA, ICLabel) im CLI-Prozess; das war der erste Linux-CI-Test, der ICLabel dort ausführt. Das gesperrte Linux-Wheel onnxruntime 1.31.0 (cp312, manylinux_2_28) enthält `core/platform/linux/device_discovery.cc` mit „GPU device discovery failed: “, „/sys/class/drm“ und „NPU device discovery failed: “; sein Standard-Logger schreibt beim Anlegen der Umgebung auf Deskriptor 2. Eine Umgebungsvariable für die Standard-Schwere gibt es nicht, und `set_default_logger_severity` legt die Umgebung zuerst an. Neu ist `kernel/processes.on_null_device()`: Bibliothekscode, dessen native Ausgabe NeuroGrid nie zeigt, läuft mit der Konsole auf dem Nullgerät, im Worker und mit `--jobs 1` im eigenen Prozess; `quality.sample._iclabel` führt den Import von onnxruntime, das Abschalten der Telemetrie, ICA und `label_components` darin aus. Unter POSIX ist das `null_descriptors`. Unter Windows (7f5b3b0; 223206b nahm fälschlich an, der Windows-Build habe keine solche Geräteerkennung) hat onnxruntime eine eigene (`core/platform/windows/device_discovery.cc`: SetupDi, D3D12, DXCore), teilt die UCRT mit Python (`api-ms-win-crt-*`, MSVCP140) und schreibt über `WOStreamSink(std::wclog)` (gemessen: VERBOSE-Zeilen in UTF-16 auf stderr außerhalb des Fensters, nichts darin). `_console_on_null` legt die Deskriptoren 1 und 2 über das gemeinsame `_on_null` auf das Nullgerät (die UCRT ruft in Konsolenprogrammen auch SetStdHandle) und sys.stdout/sys.stderr für den Block auf eine Senke auf Deskriptor 1, die vor dem Zurücksetzen geleert wird: Ein echter Konsolenstrom (`_WindowsConsoleIO`) wirft auf dem Nullgerät `OSError` (WinError 1), was im try von ICLabel M09b scheitern ließe und den Wert von der Konsole abhängig machte (NG-N03). Python-Warnungen des Blocks ignorierte `_quiet` schon; die Regel oben (mit `--jobs 1` übersetzte Bibliothekswarnungen) bleibt, die Werte bleiben gleich. Beleg der Ursache: die Zeichenketten des Wheels und das bloße „1“ (der Lauf mit `--jobs 1`) in der Annotation; die genaue Zeile hat die CI nie gezeigt, auf 27c3e90 besteht der Test auf ubuntu-24.04.
  - **Fenster ohne freie Deskriptoren** (1ebe89b): Ein Fenster (`null_descriptors`, `on_null_device`), das einen Deskriptor nicht kopieren oder das Nullgerät nicht öffnen kann (EMFILE, ENFILE), wirft vor seinem Block und ändert nichts: Kopien geschlossen, `_SAVED` gekürzt, jeder Deskriptor dieselbe Datei mit demselben Flag. Als geschlossen gilt ein Deskriptor nur bei EBADF; vorher galt ein EMFILE beim Kopieren als geschlossener Deskriptor, der Block lief, und danach wurde der offene Konsolen-Deskriptor geschlossen. In ICLabel macht `run_iclabel` aus dem OSError ein gescheitertes M09b (A-60); ein Pool-Start scheitert wie ohnehin bei fehlenden Deskriptoren.
  - **Feeder-Thread der Aufrufwarteschlange unter Python 3.11** (9b355bd, 95f6c50, 25ead0d): eine dritte Quelle neben Start und Initializer der Worker, der Feeder-Thread im eigenen Prozess, dessen stderr die Konsole ist. In CPython 3.11 schließt `terminate_broken` nach dem Tod eines Workers den Schreiber der Warteschlange (gh-107219, nur win32), dann legt `shutdown_workers` noch ein Stoppsignal für jeden Worker hinein, der noch als lebend gilt, solange die Warteschlange einen freien Platz hat (`put_nowait`, bei `queue.Full` endet die Schleife). Der Versand scheitert mit `OSError('handle is closed')` ohne errno, `_ignore_epipe` greift nicht, und `_SafeQueue` reicht das schon gepickelte Objekt an `Queue._on_queue_feeder_error` → `traceback.print_exc()` mit dem Installationspfad von Python samt Benutzername. 3.12 und 3.13 überspringen `shutdown_workers` für einen kaputten Pool (`_join_executor_internals(broken=True)`); eine Probe mit einfachem `ProcessPoolExecutor` und `os._exit` druckte den Traceback unter 3.11 5 von 5 Mal, unter 3.12 und 3.13 nie. Ob ein Lauf den Weg erreicht, hängt vom Timing ab: Der CLI-Test startet mindestens 3 Aufgaben für 3 Plätze, er bestand lokal auf 18da12f und scheiterte in der CI; der Semaphor-Test legt 2 Aufgaben in 3 Plätze und scheiterte lokal unter 3.11.17 ohne `quiet_pool` 3 von 3 Mal. Behebung: `kernel/processes.quiet_pool(pool)`, auf jeder Plattform und Version, genutzt in `quality._pool`, setzt einen eigenen `_on_queue_feeder_error` an `pool._call_queue`. Eine Aufgabe, die sich nicht pickeln lässt, lässt weiter ihre eigene Future scheitern (der Handler von concurrent.futures, erreicht über `weakref.WeakMethod`, damit der Feeder-Thread die Warteschlange nicht festhält; a25fc54); jeder andere gescheiterte Versand geht nur in das Debug-Log von multiprocessing, denn der Pool meldet den Tod schon (BrokenProcessPool → `cli.check.recomputed`). Neues Verhalten (95f6c50): `_FeedBuffer` ersetzt `call_queue._buffer` und hält das zuletzt entnommene Objekt bis zum nächsten `popleft`; so scheitert eine Aufgabe, die der Feeder-Thread nicht senden konnte, an ihrer eigenen Future mit dem Fehler, statt ohne Zeichen offen zu bleiben (CPython druckt dann einen Traceback und lässt sie offen). `compute_all` rechnet die Aufnahme danach allein, `check` zeigt `cli.check.recomputed`, die Werte gleichen `--jobs 1`; gescheiterte Stoppsignale gehen nur ins Debug-Log. Aus dem Quelltext von 3.12 und 3.13 gefolgert, nicht gemessen: Schlösse `Queue._terminate_broken` den Schreiber, während der Feeder-Thread gerade sendet, entstünde derselbe Traceback; `quiet_pool` deckt auch das. Kein Plattform-Skip und keine Änderung der Testerwartung: Die Zusage von A-51 und NG-N05 war im eigenen Prozess verletzt. 25ead0d berichtigt die ungenaue Bedingung in den Commit-Meldungen 9b355bd und aa03735 (die Historie blieb).
  - **Variablen im Scan von `.env.example`** (29ff4af, 9b9a98b; TECH-05, CON-02): `NullStdioPopen` setzt für einen gespawnten Worker in einer venv `__PYVENV_LAUNCHER__` wie CPythons `popen_spawn_win32` (bpo-35797); der Scan in `tests/packaging/test_env_example.py` sah diese Schreibung, geprüft hatte sie niemand (Fehler in allen sechs Testjobs). Sie steht jetzt in `THIRD_PARTY`, nicht in `.env.example` (Variable eines anderen Programms); entfällt die Zeile in `kernel/processes.py`, muss der Eintrag mit weg, sonst scheitert `test_reviewed_names_are_in_use_and_in_one_set_only`. `USER` und `LOGNAME` (unter POSIX vom Betriebssystem gesetzt wie `USERNAME` unter Windows, gelesen von `_measured` im Konsolentest) stehen in `PROVIDED`. Nicht behoben: `tools/acceptance_g1.py::forbidden_values` liest `USER`, `LOGNAME` und `HOSTNAME` über eine verschachtelte Schleife, die der Scan nicht auflöst; `HOSTNAME` wird gelesen, aber nie geprüft.
  - **Meldungen der Konsolentests** (aa03735, 223206b): Die Konsolen- und Datenschutzprüfungen des CLI-Tests nennen `--jobs`, den Exitcode, die Probleme, bis zu 4 auffällige Konsolenzeilen (Benutzerordner, Benutzer, Rechner und `tmp_path` durch Platzhalter ersetzt) und die Traceback-Rahmen als Datei:Zeile Funktion mit den Ausnahmetypen, ohne Pfade und Texte, damit eine CI-Annotation die Ursache nennt statt „1“ oder „2“.
  - **Neue Tests:** in `tests/unit/test_processes.py` `test_null_descriptors_cover_a_stream_on_another_descriptor_and_a_forked_child`, `test_on_null_device_keeps_native_output_of_library_code_off_the_console`, `test_onnxruntime_logs_nothing_to_the_console_inside_on_null_device` (echtes onnxruntime mit VERBOSE, alle Plattformen), `test_on_null_device_on_a_windows_console_writes_nothing_there_and_raises_nothing` (nur Windows: Konsole mit CREATE_NO_WINDOW, liest den Bildschirmpuffer) und `test_a_window_that_runs_out_of_descriptors_changes_nothing[copy|null]` (alle Plattformen), der capfd-Test jetzt auch unter Windows; `tests/unit/test_quality_sample.py::test_onnxruntime_runs_inside_on_null_device`; in `tests/integration/test_worker_console.py` `test_the_failure_message_shows_the_offending_console_lines`, `test_the_queue_thread_of_a_pool_prints_no_failed_send` (deterministischer Regressionstest des Wegs unter 3.11) und `test_a_task_that_could_not_be_sent_fails_its_future` (vor 95f6c50 blieb die Future unter 3.11 offen, nach 60 s brach der Test den Pool ab).
  - **Grenzen aus der Runde:**
    - Ein forkserver oder resource tracker, den anderer Code desselben Prozesses vor NeuroGrids erstem Pool startete, behält seine Deskriptoren: CPython prüft nur einen laufenden, und einen fremden tracker zu beenden, entfernte die Ressourcen dieses Codes (Docstrings von `NullStdioForkServerPopen` und `_quiet_resource_tracker`, 5aa8749). In der CLI unter Linux kommt das nicht vor: fork ist bis 3.13 die Voreinstellung, die CLI wählt nie forkserver, fork-Semaphoren werden nicht registriert, und der CLI-Prozess nutzt keinen gemeinsamen Speicher.
    - Unter POSIX nicht gedeckt: stdin des Elternprozesses auf einem Deskriptor über 2 und Stromobjekte ohne Deskriptor, durch die vor NeuroGrids eigenem at-fork-Handler registrierte Handler schreiben.
    - `quiet_pool` stützt sich auf private Teile von CPython: `concurrent.futures.process._SafeQueue`, `_CallItem` und `_on_queue_feeder_error`, `ProcessPoolExecutor._call_queue` und `multiprocessing.queues.Queue._buffer` (von `_start_thread` übernommen, von `_feed` mit `popleft` geleert), gleich in 3.11.17, 3.12.15 und 3.13.7. Eine neue CPython-Version ist erneut zu prüfen; `tests/integration/test_worker_console.py` scheitert, wenn sich ihr Verhalten ändert.
    - Solange ein Pool arbeitet, ist kein gescheiterter Versand bekannt (der eigene Prozess hält einen Leser der Pipe). Ginge in einem arbeitenden Pool ein Stoppsignal verloren, wartete der Lauf am Ende auf seinen Worker, wie CPython nach seinem Traceback; nicht beobachtet, nicht behandelt.
    - `on_null_device` deckt unter Windows nicht, was direkt auf das Konsolengerät geht (`CONOUT$`, Grenze oben). Eine Bibliothek, die den alten Std-Handle-Wert zwischenspeichert, oder ein im Block angelegter `logging.StreamHandler` (er behielte die geschlossene Senke) verhielte sich nach dem Block falsch; in onnxruntime, mne_icalabel und picard gibt es keines (Suche). Auf beiden Plattformen gehen Konsolenausgaben anderer Threads während des Blocks auf das Nullgerät; mit `--jobs 1` hat die CLI keinen solchen Thread.
    - `cli.check.recomputed` spricht von einem unerwartet beendeten Hilfsprozess; die Zeile erscheint auch, wenn ein Teil nicht zustellbar war (seit D-14), und jetzt nach einem gescheiterten Versand. Wortlaut und Schlüssel blieben unverändert.
    - Nur in der CI belegt (D-09): alle POSIX-Teile der Runde (Warten auf den tracker, Deckung der Deskriptoren und Umbinden im fork-Kind, die Umleitung von `on_null_device`, der Linux-Lauf mit `--jobs 1`) und die Behebung des Wettlaufs auf windows-latest mit Python 3.11 (lokal liegt die Warteschlange des CLI-Tests voll). Die CI auf 27c3e90 ist in allen sechs Testjobs grün; welche Tests dort übersprungen wurden, nennt nur das Protokoll des Laufs. Der Aufruf von `ci.yml` aus `release.yml` lief noch nie (A-87).
