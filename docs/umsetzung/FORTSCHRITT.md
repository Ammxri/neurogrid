# NeuroGrid – Fortschritt

Bei jedem Sitzungsneustart zuerst lesen: diese Datei, [ANFORDERUNGEN.md](ANFORDERUNGEN.md),
[ENTSCHEIDUNGEN.md](ENTSCHEIDUNGEN.md). PRD: `.local/prd/PRD-1-NeuroGrid.pdf` (Text: `*.layout.txt`, `*.raw.txt`;
Tabellen §12/§13 sind in `*.raw.txt` besser lesbar; Architekturbild: `architektur-s8.png`).

## Aktueller Stand

**Phase P5 umgesetzt und gemergt (`dev` 55335ca, Doku-Korrektur 181654e); eine zweite CI-Fix-Runde (p5-ci2) läuft, danach STOPP G1.**
Freigabemodus A bis STOPP G1. Git: `main` (Doku-Commit), Arbeitszweig `dev`, gepusht nach `https://github.com/Ammxri/neurogrid`
(D-15; nur `dev`, D-09; zuletzt gepusht: 55335ca). Version 0.1.0rc1; 0.1.0 und Tag erst nach G1.
CI auf 55335ca: `offline` ganz grün, in `ci` die Testjobs rot (Einzelheiten im P5-Eintrag).
Offen beim Nutzer: Entscheidungen der Liste „Für STOPP G1 vorgemerkt“, GB/T-47127-PDF vor P7, YY/T-2029-Text vor P8,
ISO-TS vor P10, muttersprachliche zh-Prüfung vor v0.1, Docker Desktop bei Gelegenheit.

## Für STOPP G1 vorgemerkt

Vollständige Liste nach P5; sie ersetzt die Listen der früheren Einträge.
- **Freigaben:** Push und Merge nach `main`; Veröffentlichung (Version 0.1.0, Tag `v0.1.0`, `release.yml`), PyPI über
  `publish-pypi.yml` (Trusted Publishing bei TestPyPI und PyPI eintragen), Gitee-Spiegel (`mirror-gitee.yml`, Secret
  `GITEE_SSH_KEY`, Variable `GITEE_MIRROR`; das Gitee-Release legt der Projektverantwortliche von Hand an, R15).
- **Release-Sperre:** `tools/notices.py --check` meldet 8 Lücken aus `license-gate/known_missing.toml`; das Release
  bleibt gesperrt, bis der Projektverantwortliche je Lücke entscheidet (Download der Texte außerhalb von D-06/D-15
  oder anderer Umgang):
  - `bids-validator-deno:hed-validator@4.2.0/node_modules` (acht Pakete im vorgebauten hed-validator ohne Version in der Source-Map)
  - `bids-validator-deno:hash-wasm@4.12.0/src` (C-Quellen mit Verweis auf einen Haftungsausschluss bzw. ohne Lizenztext)
  - `bids-validator-deno:node-modules-polyfills/@jspm/core` (Node-Polyfills ohne Version)
  - `h5py:h5py.libs/libaec-*.so*` und `h5py:h5py.libs/libsz-*.so*` (Linux-Wheel ohne Lizenz und Text)
  - `python-build-standalone:3.12.15+20261009` (Texte der eingebauten Bibliotheken außer CPython)
  - `docs-site:focus-visible` und `docs-site:material-design-color` (Teile des Doku-Themes ohne angegebene Lizenz:
    Download der Lizenztexte freigeben oder die Website ohne sie bauen)
- **D-16:** Die LGPL-Ausnahme für den Abschnitt in bids-validator-deno 3.0.2 ist entschieden und umgesetzt (Texte
  neben isomorphic-git in `license-gate/third_party/bids-validator-3.0.2/`, Nennung in den Notices). Offen: Den Entwurf
  der Anfrage an die Entwickler des Validators (lokal, nicht versioniert) prüft und sendet der Projektverantwortliche.
- **Muttersprachliche zh-Prüfung** (A-07): Paket mit `tools/zh_review_package.py` (Stand Abnahme: 2530 Texte aus
  34 Dateien), dazu die neuen zh-Texte der Fix-Runde `report.text.severity_heading`, `report.text.severity_heading_none`,
  `report.text.severity_heading_info`, `errors.pdf.install.command_windows`, die geänderten Installer-Meldungen,
  README.bundle.txt, release-notes.md, gitee-release.md, die Sätze in docs/zh (installation.md, privacy.md) und der
  feste Satz.
- **Signatur, Lesart von D-10 g nach D-15 bestätigen:** Mit cosign (auf PATH oder `-Cosign`/`--cosign`) wird die
  Signatur immer geprüft, `-SkipSignatureCheck`/`--skip-signature-check` übergeht keine Ablehnung und lässt nur eine
  Installation ohne cosign weiterlaufen; die Meldung nennt für einen Rechner ohne Sigstore-Vertrauensanker den Weg
  „nach der Prüfung auf einem vernetzten Rechner ohne cosign auf PATH und mit dem Schalter“ (R16). R12: Die Prüfung im
  Archiv belegt nur Integrität (dokumentierte Grenze); die Installer nennen die geprüfte Identität zum Vergleich mit
  den Release-Notes.
- **Annahmen A-78 bis A-88 zur Freigabe**, darunter:
  - A-84: höchstens 50 Befundzeilen je Regel plus Sammelzeile als Lesart von „jeder Befund“ (NG-F13); Abschnitt 4
    mit den datensatzweiten Werten von M11/M12, Anhang 6.1 (geprüfte Regeln) und 6.6 (Umgebung) als Lesart von
    REP-04/REP-06; Wortlaut der Überschriften in Abschnitt 3 (R05); eigenes SVG statt matplotlib.
  - A-85 (PDF-Weg, Schrift, QA-Gate, Kernel-Importe fontTools/Playwright/pypdf), A-86 (eigener Notices-Leser statt
    pip-licenses, Seitensatz der Doku, Offline-Suche), A-87 (Bündel, Pfadgrenzen, Signatur, Workflows), A-88
    (G1-Werkzeug, Skalierungsgrenzen).
  - Aus P4: Alterspalten mit anderen Einheiten als Monate, Wochen, Tage gelten als Jahre; `report --out` nennt seinen
    Pfad auf der Konsole nicht pseudonym. Aus früheren Phasen: Restpunkte A-78, Zeitangaben ab 27,8 h nur auf 1 s
    genau (A-61, A-79), loky „resource tracker“ ohne Netzwerkschutz (A-79).
- **CI-Testjobs grün (Nachweis ausstehend):** Auf 55335ca sind die Testjobs von `ci` rot: Linux ein P2-Formattest,
  zwei Codepage-Umwandlungen von `convert` und zwei PDF-Tests; windows-latest drei Tests in `test_install_ps1.py`,
  `test_pdf_tests_pass_with_a_long_basetemp` (Chrome schreibt eine `debug.log` in seinen Programmordner) und einmal
  eine Zeitüberschreitung der Doku-Suche; der strace-Test der Doku ist mit 181654e behoben (Einzelheiten im
  P5-Eintrag). Ergebnis der zweiten Fix-Runde: <ERGEBNIS NACH P5-CI2>.
- **Nutzerdoku nachziehen:** R08 und R09 sind in Arbeit (p5-ci2-userdocs); auf 181654e nennen privacy.md und
  report.md nicht, dass `document`, `reviewer`, `comment` und `justification` aus evidence.yaml im Klartext erscheinen
  (A-83), und configuration.md dreht den Vorrang von `[dataset]` um. installation.md, limitations.md und privacy.md (en, zh) nennen Linux, PowerShell 7 und
  den Lauf unter strace noch „bis zum ersten CI-Lauf nicht verifiziert“, privacy.md den Firewall-Test „nicht
  verifiziert“; der Workflow `offline` auf 55335ca hat diese Punkte grün geprüft.
- **Platzhalter `<REPO_URL>`** in docs/en und docs/zh (und `<PYPI_RELEASE>` auf der Installationsseite) mit der
  freigegebenen Adresse füllen; `tools/release_check.py` sperrt das Release, solange sie stehen.
- **Sichtprüfung der PDFs** zh/en (KONZEPT 4).
- **Fragen zu P6** (Entwurf der P6-Vorgaben, ohne Commit, D-15):
  1. M14 je Proband: Option A (Befunde je Proband überall), B (je Proband nur in results.json; Bericht, Export und
     Mappe zusammengefasst je Nutzung und Grund) oder C (überall zusammengefasst). Empfehlung: B.
  2. zh-Texte von P6: Option A (alle P6-Entwürfe in die G1-Prüfung), B (eigene Runde vor v0.2) oder C (bei G1 nur die
     Begriffe, die vollen Texte vor v0.2). Empfehlung: C.

## Verlauf

### 2026-10-27 – P5 Bericht, PDF, Dokumentation, Bündel, Abnahme
- **Abgeschlossen:** NG-F14, NG-F18, CLI-05, REP-01, REP-02, REP-03, REP-04, REP-05, REP-06, REP-07, POS-01, ARC-05, ARC-06, TECH-06, TECH-10, NG-N01, NG-N03, NG-N05, NG-N06, CON-01, CON-04, V-06, UF-07, UF-08; aus P1 nachgetragen: TECH-11 (CI aktiv).
- **Umgesetzt, Nachweis offen (`nicht verifiziert`):** NG-F13, REP-00, TECH-05, TECH-07, NG-N04, NG-N08, UF-01 (CI-Testjobs noch rot, Lauf auf 55335ca, zweite Fix-Runde läuft; REP-00 und UF-01 zusätzlich Sichtprüfung bei G1).
- **Teilweise:** V-01, NG-N07 (8 Lizenzlücken, G1), POS-02 und CON-05 (Platzhalter `<REPO_URL>`, Release nach G1). **Blockiert (extern):** TECH-08 (Gitee-Konto und Secret).
- **Beigetragen zu:** UF-02, CON-02, TECH-01, RP-07.
- **Gebaut** (vier Bereiche parallel nach den verbindlichen Vorgaben B1–B6, ENTSCHEIDUNGEN A-84 bis A-87):
  - Bericht (A-84): sechs Abschnitte zh/en; Deckblatt nach REP-01; Zusammenfassung mit Ampel, Summen und Abdeckungsmaß; Befunde mit zehn Zellen und erklärten leeren Zellen, höchstens 50 Zeilen je Regel plus Sammelzeile; Metriktabelle je Aufnahme und Verteilungsgrafiken als eigenes SVG (`report/charts.py`); Nachweise; Anhang 6.1–6.6; Abgrenzung (ARC-05) und Worttest `report/wording/statements.yaml`; Glyphensicherheit; Generator für den Skalierungsfall 1000 × 64 (`tools/gen_fixtures.py`).
  - PDF (A-85): `report/output.py` `write_reports` (zwei Durchgänge, alles oder nichts), `kernel/fonts.py` (Subsets, Glyph-Zwillinge), `kernel/pdf.py` (Shell aus dem NeuroGrid-Ordner, Startprüfung mit `ldd` und `pdf_linux_packages.json`, Druck, Datumsfelder, QA-Gate); statische Schriften aus `tools/build_fonts.py`; `tools/install_pdf_browser.py`; `report --format pdf`; netguard-Lesart für die asyncio-Schleife (A-49).
  - Doku, Meldungen, Notices, Lizenzen (A-86): MkDocs-Website zh/en mit je 16 Seiten (`tools/gen_docs.py`, `tools/build_docs.py`, `tools/mkdocs_hooks.py`), Offline-Suche; Hilfe und Bedienfehler der Kommandozeile übersetzt (`cli.help.*`, `cli.error.*`); `tools/notices.py` → `THIRD_PARTY_NOTICES.txt`; `license-gate/` mit `components.toml` und `known_missing.toml`; REUSE mit OFL-1.1 für die Schriften; V-06-Test; core 0.1.1 (Quellenangabe der Doku).
  - Bündel, Signatur, Workflows (A-87): `tools/bundle.py` (build, verify; byte-gleich), `packaging/` (install.ps1/install.cmd, install.sh, README, Release-Notes), Signatur nach D-15, `tools/release_check.py`, `tools/scan_runtime_network.py`, `tools/strace_check.py`, Reinraum-Skripte, sieben Workflows, `.env.example`.
- **Integration:** PDF-Weg mit allen Bereichen (u. a. privater Arbeitsordner `ng-pdf-*` des Browsers im temporären Ordner, nie unter `--out`), Bündel mit Präfix an der Längengrenze im Windows-Reinraum, Lizenztexte nach D-15 (CC BY 4.0, Lizenzdateien der Validator-Pakete) und D-16 (LGPL-Abschnitt im Validator); Abnahme (A-88): `tools/acceptance_g1.py`, Skalierungstest, zh-Prüfpaket, fester Satz auf der Konsole jedes Befehls.
- **Review:** vier Prüfrichtungen (Bericht/PDF, Datenschutz, Bündel/CI, Doku/Lizenzen/Abnahme), jeder Befund gegengeprüft.
  - 30 Befunde R00–R29: 29 bestätigt, R12 strittig (Entscheidung: dokumentierte Grenze, die Installer nennen die geprüfte Identität). Behoben sind alle außer R08 und R09 (Nutzerdoku, in der Fix-Runde keinem Bereich zugeordnet; in Arbeit (p5-ci2-userdocs)), je mit Test, nachgeprüft und in einer Reparaturrunde nachgebessert.
  - Wichtigste Befunde:
    - R19: Die Doku-Website im Bündel enthielt fremdes JavaScript ohne Nennung, darunter lunr-languages (MPL); jetzt entfernt bzw. geprüft (`license-gate/third_party/mkdocs-material-9.7.7/`).
    - R00: Berichte wurden beim Ersetzen nicht alles oder nichts geschrieben; R01: ein langer Wert verkleinerte jede PDF-Seite auf 2/3.
    - R10: Die Bündel-Tests liefen nicht auf jedem Push auf `dev` (gegen D-15); R11: tote Loopback-Proxies ließen Netzversuche im strace- und WFP-Nachweis als erlaubt erscheinen.
    - R07, R13, R06: Installationshinweis, Installer und Browser-Installer zeigten Benutzerordner bzw. einen nicht ausführbaren Befehl.
    - R20–R24, R29: Das G1-Werkzeug verglich Klausel, Messwert, Schwelle und Titel nicht, suchte weder rohe Datei- und Ordnernamen noch ganzzahlige Rohalter, zählte unlesbare Datensätze mit und prüfte den festen Satz im HTML nicht.
  - Fix-Runde in vier Bereichen (report, linux, bundle, docs). Sie behob auch die Fehler des GitHub-Laufs auf c3be509 (Lauf 40355705974; annotiert: windows-latest 3.12/3.13 je 18 Fehler, ubuntu-24.04 3.11/3.12 je 18 Fehler und 10 Setup-Fehler): `Get-FileHash` fehlt in Windows PowerShell 5.1 unter dem Modulpfad von PowerShell 7, EncodingWarning aus `ldd` in der PDF-Startprüfung, Benutzername in `/tmp`-Pfaden, UNC- und Gerätepfade unter POSIX, ein nur unter Windows gültiger Test; dazu Annotationen für bis zu 40 Fehler je Job. Offen: `test_pdf_tests_pass_with_a_long_basetemp` (windows-latest).
  - Merges 28de466, 2e1e24e, e204c7b, 862de1d; Merge-Fix 55335ca (die Sicherungsdatei aus R00 entsteht über `create_temporary`, das die Linux-Fix-Runde an die Stelle von `mkstemp` setzte). Ein semantischer Konflikt zwischen R11 (Bündel) und R25 (Doku) ließ den strace-Test der Doku scheitern, behoben in 181654e.
- **Ergebnisse (lokal, Windows 11):**
  - Volle Suiten der Fix-Runde: report c9a536a 3502 bestanden, 23 übersprungen; linux 191a62a 3510 bestanden, 25 übersprungen (mit `PYTHONWARNDEFAULTENCODING=1`); bundle d42bbf4 3498 bestanden, 23 übersprungen.
  - Gemergter Stand 55335ca (Python 3.12, `NEUROGRID_REQUIRE_PDF=1`, `PYTHONWARNDEFAULTENCODING=1`): 3597 bestanden, 24 übersprungen, 127 abgewählt, 1 fehlgeschlagen (strace-Test der Doku, behoben in 181654e). Endstand nach der zweiten Fix-Runde: <ERGEBNIS NACH P5-CI2>.
  - G1-Lauf (`tools/acceptance_g1.py`, 4587546): 6 von 6 Datensätzen in 5 Formaten (BDF, BrainVision, EDF, EEGLAB, FIF), alle Kriterien des Laufs erfüllt, zwei Läufe byte-gleich, `--jobs 1` = `--jobs 4`, Korpus unverändert, V-01-Checkliste des Laufs erfüllt (nur die Kriterien dieses Laufs; Matrix V-01 teilweise), V-06 ok; unabhängig nachgeprüft (alle 42 Ausgabedateien byte-gleich). Nach den Korrekturen R20–R24 mit verschärften Prüfungen auf 3 Datensätzen erneut bestanden; ein voller Lauf aller sechs Datensätze auf dem Endstand steht aus.
  - Skalierung (A-88, 1000 Aufnahmen × 64 Kanäle):

    | Fall | Befunde | `report` HTML | `report` HTML+PDF | PDF-Seiten zh/en |
    |---|---|---|---|---|
    | ungünstigster | 128 742 | 21,4 s / 1703 MB | 108,8 s / 1929 MB | 99 / 106 |
    | typisch | 6 110 | 13,0 s / 364 MB | 92,1 s / 1284 MB | 136 / 142 |

    Grenze im Test: größter Wert der Läufe vom 26.10.2026 plus 50 %, aufgerundet (z. B. 164 s / 2894 MB für HTML+PDF im ungünstigsten Fall).
  - Lizenz-Gate (Laufzeit, Dev, Doku) und Komponentenprüfung (129 Wheels beider Ziele, 4 Bündelteile) grün auf dem 103-Paket-Lock (Zweig p5-acceptance, 228ec49); `notices.py --check` meldet die 8 Lücken (Exit 1 bis G1).
  - Windows-Reinraum lokal (`-NoOsAudit`, Integrationszweig cb19b17): Präfix an der Grenze (101 Zeichen) installiert, 102 abgelehnt; `report` mit PDF im installierten Bündel 20,2 s.
- **CI (GitHub Actions, 55335ca):**
  - `offline` (Lauf 40403791782) ganz grün: beide Offline-Bündel aus `uv.lock` (unsignierte Entwicklungsbündel), PDF in debian:12-slim mit der dokumentierten Paketliste (`--network none`, strace), glibc 2.27 mit Exit 2 abgelehnt (ubuntu:18.04), Reinraum Windows (powershell 5.1 und pwsh, WFP-Audit, PDF), Reinräume debian:12-slim, ubuntu:24.04, ubuntu:22.04 (`--network none`, ohne Python, uid 1000), jeder v0.1-Befehl unter strace mit `--network none`.
  - `ci` (Lauf 40403791901): grün Lizenz-Gate mit Paketscan, Kommandozeile unter Windows PowerShell 5.1 und PowerShell 7, Anforderungs-IDs; rot die Testjobs: ubuntu-24.04 Python 3.11/3.12/3.13 je 6 Fehler (`test_review_p2_formats.py::test_mne_alone_follows_the_differently_decoded_reference`, zwei Codepage-Umwandlungen in `test_review_p2_convert.py`, `test_report_pdf.py::test_qa_gate_negative_controls`, `::test_rule_ids_do_not_break_inside_in_the_pdf`, der strace-Test der Doku), windows-latest je 5–6 Fehler (drei Tests in `test_install_ps1.py` auf dem Runner, `test_pdf_tests_pass_with_a_long_basetemp`, der strace-Test der Doku, einmal eine Zeitüberschreitung der Suche in `test_docs_browser.py`). Die zweite Fix-Runde (p5-ci2) läuft.
- **Annahmen:** A-84 (Bericht), A-85 (PDF), A-86 (Doku, Meldungen, Notices, Lizenzen), A-87 (Bündel, Signatur, Installation, Workflows), A-88 (Abnahme); für STOPP G1 vorgemerkt.
- **Nicht verifiziert:**
  - Volle Testsuite unter Linux und auf dem Windows-Runner (siehe CI), damit auch die Abdeckungs-Gates im CI.
  - Auf dem Endstand: voller G1-Lauf aller sechs Datensätze, Korpustests (`-m corpus`) und `bundle.py sizes`.
  - Windows 10; NG-N02 auf einem Runner mit 4 vCPU/16 GB; Signaturprüfung an einem echten Release; Sichtprüfung der PDFs.
  - Der Windows-Nachweis auf OS-Ebene ordnet DNS-Anfragen über den DNS-Client-Dienst nicht zu (A-87); Container-Images per Tag, nicht per Digest gepinnt.

### 2026-10-23 – P4 Annotation, KI-Struktur, Provenienz, Nachweise, gxdsl008
- **Abgeschlossen:** NG-F08, NG-F09, NG-F10, NG-F12, M10, M11, M12, M13, MET-02, CLI-03, CLI-04, CLI-06, GX-00, GX-01, GX-02, GX-03, GX-04, GX-05, UF-04, UF-05, RP-05.
- **Beigetragen zu:** NG-F11, NG-F18, RP-07, REP-05, UF-01, UF-07, REP-01, DM-05, DM-06, NG-N02, NG-N03, NG-N05, NG-N08.
- **Gebaut:**
  - M10 Annotation (`io/annotations.py`, `checks/annotation.py`): Leser für EDF+/BDF+-TAL (auch reine Annotationsdateien), BrainVision `.vmrk`, EEGLAB (MAT v5/v7.3), FIF und BIDS `events.tsv`; Zuordnung von Hypnogrammen; Cohens κ, Codes, Lücken, Überlappungen (CORE-M10-01..04).
  - M11/M12 KI-Struktur (`checks/ai_dataset.py`, `io/participants.py`, `io/splits.py`, `io/events.py`): Klassenanteile aus events, participants oder Annotationen; Demografie; Split-Integrität; Duplikate über den Signal-Hash.
  - M13 Provenienz: `neurogrid manifest` und `neurogrid verify` (`kernel/provenance.py`, `io/provenance.py`), Standardort `.neurogrid/manifest.json`; CORE-M13-01..03; `--strict` über das neue Regelfeld `strict_severity`.
  - Nachweise: Auswertung von `.neurogrid/evidence.yaml` mit Dokument-Hash (`kernel/evidence.py`, `checks/evidence.py`); halbautomatische Regeln; Ausnahmen vollständig; Ampel nach A-16, präzisiert unter „Übergreifend“ in A-80 ff.
  - Paket `gxdsl008` mit GX-01 bis GX-05 (Klausel „unknown“ bis zum Normtext, D-02).
  - results.json: optionale Blöcke `evidence`, `duplicates`, `ai`, `manifest`; Bericht mit den neuen Abschnitten; alle Texte zh/en/de.
  - Annahmen A-80 (Annotation), A-81 (KI-Struktur), A-82 (Provenienz), A-83 (Nachweise, Ausnahmen, gxdsl008) und übergreifende Regeln.
- **Vorgehen:** vier Bereiche parallel nach verbindlichen Vorgaben (ENTSCHEIDUNGEN: „Übergreifend“ und A-80 bis A-83), zusammengeführt und integriert (Manifest unter `.neurogrid/`, Labelquelle `annotations`, Verdeckung von `ai.splits`).
- **Review:** sechs Prüfrichtungen (Annotation, KI-Struktur, Provenienz, Nachweise/gxdsl008, Integration/Datenschutz, Abgleich mit PRD und DoD), jeder Befund unabhängig gegengeprüft, schwere doppelt.
  - 57 Befunde: 46 bestätigt, 2 strittig, 8 beabsichtigt, 1 widerlegt. Alle bestätigten und die strittigen behoben, je mit Regressionstest, unabhängig nachgeprüft und in einer Reparaturrunde nachgebessert.
  - Wichtigste Befunde:
    - Die Mitunterdrückung kleiner Zellen war über Summen, Split-Zahlen, Nullzellen und Statusangaben zurückzurechnen. Ersetzt durch die Tabellenregel (A-81); eine Auszählung über alle Belegungen findet keine herleitbare Zelle mehr.
    - `participants:age` gab Rohalter aus; Datum und Uhrzeit in Annotationstexten erschienen im Klartext.
    - Exit 2 durch Datensatzdaten: Überlauf bei großen Annotationszeiten, negatives Kopfgrößenfeld in EDF+, lange kodierte Dateinamen, tief verschachteltes Manifest.
    - `verify` übersah Änderungen unter abgelehnten Ordnernamen; GX-03 bewertete nicht unterstützte Formate nicht.
    - κ wuchs quadratisch mit der Zahl der Annotatoren; jetzt auf 100 Annotatoren begrenzt und über Klassenabschnitte berechnet (Beispiel: rund 290 s → 4 s für den ganzen Lauf, gleiche Ergebnisse).
  - Gegenprüfung des gemergten Stands: keiner der 44 behobenen Code-Befunde tritt mehr auf (die übrigen 4 betrafen nur die Dokumentation). Sechs neue kleinere Fehler aus dem Zusammenspiel der Fixes und zwei eigene Restpunkte in einer zweiten Runde behoben und nachgeprüft (u. a. Datumsteile als Dateiendung, Uhrzeit-Muster, „N/A“ als Klasse, Konsolenpfad von `check --out`).
- **Ergebnisse (lokal, Windows 11):**
  - pytest Python 3.11, 3.12 und 3.13: je 2705 bestanden, 11 übersprungen (Datei-Symlinks und POSIX-Zweige unter Windows).
  - Acht Fixtures mit core+bids+gxdsl008 und allen P4-Funktionen unter 3.11/3.12/3.13 gleich bis auf `environment`.
  - Korpus: 62 bestanden, darunter κ auf PSG-IPA wie nachgerechnet (±0,001).
  - Abdeckung Kern 97,1 %, Prüfer 97,2 %; ruff und mypy (src, tools) sauber.
  - Lizenz-Gate grün (keine neuen Abhängigkeiten); Schemas, Fixtures, Matrix und `calibrate.py --check` grün.
  - NG-N02 mit allen Regeln von `core` und `--jobs 4`:

    | Kanäle | Laufzeit | Spitzenspeicher | Grenze (D-14) |
    |---|---|---|---|
    | 64 | 69,6 s | 1,8 GB | 150 s |
    | 128 | 118,6 s | 2,6 GB | 150 s |
    | 256 | 241,7 s | 3,6 GB | 300 s |
    | 256, Datensatz mit Manifest | 239,1 s | 3,7 GB | 300 s |

- **Nicht verifiziert:**
  - Linux- und CI-Lauf (TECH-05, TECH-11, D-09), damit auch die POSIX-Zweige der Provenienz.
  - NG-N02 auf einem Runner mit 4 vCPU/16 GB.
- **Für STOPP G1 vorgemerkt:** übernommen in die vollständige Liste „Für STOPP G1 vorgemerkt“ oben; die Tabellenregel für kleine Zellen mit ihrem Preis und die Lesart von DM-02 sind mit D-15 entschieden.

### 2026-10-21 – D-14 (STOPP R4) umgesetzt
- **Entscheidung D-14:** Optionen 1 und 2 der P3-Meldung (Parallelisierung einer Aufnahme mit `--jobs`; A-50: 150 s bis 128 Kanäle, 300 s darüber).
- **Gebaut:**
  - Eine Aufnahme zerfällt in vier Teile: Stream, Vorbereitung der Stichprobe mit M06, autoreject und ICA/ICLabel.
  - Mit `--jobs N` laufen die Teile als Aufgaben eines Prozesspools, höchstens N Aufnahmen gleichzeitig.
  - autoreject nutzt bei einer einzelnen Aufnahme ab 64 Kanälen `--jobs − 1` loky-Prozesse. Sie haben Netzwerkschutz, einen BLAS-Thread, keine Warnungen auf der Konsole und keine Zwischendateien. Stirbt einer, rechnet autoreject im eigenen Prozess neu.
  - Feste Regeln setzen die Teile zusammen; das Ergebnis ist byte-gleich zu `--jobs 1`.
  - autoreject und ICA geben keine Ausnahme weiter. Kommt das Ergebnis eines Teils nicht an, läuft die Aufnahme einzeln.
  - `tools/benchmark.py` misst mit `--jobs 4` und den Grenzen aus D-14.
- **Review:** drei Prüfrichtungen (Planer, Determinismus, Robustheit), jeder Befund gegengeprüft. Alle 12 Befunde bestätigt und behoben, darunter Exit 2 bei einem `MemoryError` beim Übertragen der Stichprobe und eine fehlende Wiederholung nach einem sterbenden loky-Prozess. Bekannte Grenze: Der Hilfsprozess „resource tracker“ von loky hat keinen Netzwerkschutz (A-79).
- **Ergebnisse:**
  - pytest Python 3.12: 1729 bestanden, 7 übersprungen; Abdeckung Kern 97,3 %, Prüfer 97,3 %.
  - NG-N02 mit `--jobs 4`: 64 Kanäle 75,6 s / 1,8 GB, 128 Kanäle 126,2 s / 2,5 GB, 256 Kanäle 248,2 s / 3,7 GB, alle unter der Grenze.
  - `--jobs 1` und `--jobs 4` byte-gleich auf der 64-Kanal-1-GB-Datei.
- **Nicht verifiziert:** NG-N02 auf dem Runner (CI, D-09).

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

Zweite CI-Fix-Runde (p5-ci2) abschließen und ihr Ergebnis nachtragen (<ERGEBNIS NACH P5-CI2>), dann **STOPP G1**
mit der Liste „Für STOPP G1 vorgemerkt“ (KONZEPT 6: zh-Prüfung, Push- und Veröffentlichungsfreigabe). Nach der
Freigabe: Version 0.1.0, Tag `v0.1.0`, `release.yml`; danach P6 nach dem Entwurf der P6-Vorgaben und den Antworten
auf die beiden P6-Fragen.
