# NeuroGrid – Fortschritt

Bei jedem Sitzungsneustart zuerst lesen: diese Datei, [ANFORDERUNGEN.md](ANFORDERUNGEN.md),
[ENTSCHEIDUNGEN.md](ENTSCHEIDUNGEN.md). PRD: `.local/prd/PRD-1-NeuroGrid.pdf` (Text: `*.layout.txt`, `*.raw.txt`;
Tabellen §12/§13 sind in `*.raw.txt` besser lesbar; Architekturbild: `architektur-s8.png`).

## Aktueller Stand

**Phase P5 abgeschlossen (`dev` 27c3e90: zweite und dritte CI-Fix-Runde, D-17 und die Behebung des G1-Befunds gemergt, CI ganz grün); nächster Schritt STOPP G1.**
Freigabemodus A bis STOPP G1. Git: `main` (Doku-Commit), Arbeitszweig `dev`, gepusht nach `https://github.com/Ammxri/neurogrid`
(D-15; nur `dev`, D-09; zuletzt gepusht: 27c3e90). Version 0.1.0rc1; 0.1.0 und Tag erst nach G1.
CI auf 27c3e90 ganz grün (`ci` 40680346160, `offline` 40680346176); auf 18da12f waren die sechs Testjobs rot (`ci`
40609866806), behoben in der dritten CI-Fix-Runde. Die volle Testsuite läuft nur in der CI (Prüfvorgehen ab dem Ende von
P5, ENTSCHEIDUNGEN A-87): je Testjob 0 Fehler, windows-latest 3681–3682 von 3697 bestanden, ubuntu-24.04 3605 von 3702;
Abdeckung Kern 93,3–93,5 %, Prüfer 97,3 %. G1-Lauf auf 18da12f: 6 von 6 Datensätzen bestanden, alle Kriterien erfüllt
(151 min); Endlauf auf 27c3e90: 6 von 6 Datensätzen in 5 Formaten bestanden, alle Kriterien erfüllt, 0 Probleme, V-01 erfüllt, V-06 ja (149 min 28 s; `.local/p5/ci3/g1_summary_27c3e90.md`) (Einzelheiten in den Einträgen unten).
Offen beim Nutzer: die Liste „Für STOPP G1 vorgemerkt“, GB/T-47127-PDF vor P7, YY/T-2029-Text vor P8,
ISO-TS vor P10, Docker Desktop bei Gelegenheit.

## Für STOPP G1 vorgemerkt

Vollständige Liste nach P5 (Stand 27c3e90); sie ersetzt die Listen der früheren Einträge. Jeder Punkt braucht den
Projektverantwortlichen.
- **Muttersprachliche zh-Prüfung** (A-07, A-86, D-15, D-17): Das Paket erzeugt `tools/zh_review_package.py` nach dem
  letzten G1-Lauf (27c3e90, mit dessen Beispiel-PDFs); die Prüfperson stellt der Projektverantwortliche. Seit dem ersten
  Paket (Stand Abnahme: 2530 Texte aus 34 Dateien) neu oder geändert:
  - die Überschriften der Schweregrade (`report.text.severity_heading`, `report.text.severity_heading_none`,
    `report.text.severity_heading_info`), der feste Satz und die Zeile `cli.check.recomputed` (A-89);
  - der Installationshinweis `errors.pdf.install.command_windows` (neu) und `errors.pdf.install.docs` (geändert), die
    Meldungen zum Arbeitsordner des Browsers (`errors.pdf.work_path_too_long`, `errors.pdf.temp_hint`,
    `errors.pdf.temp_unusable`, `errors.pdf.temp_unusable_hint`) und die geänderten Meldungen von `install.ps1` und
    `install.sh`;
  - die Sätze der Fix-Runden in docs/zh (installation.md, limitations.md, privacy.md, configuration.md, report.md), der
    seit D-17 geänderte Satz in `docs/zh/license.md`, der Plattformabsatz von README.bundle.txt und release-notes.md
    sowie gitee-release.md;
  - darunter neu aus der dritten CI-Fix-Runde (U1, 17e0d3f): in `docs/zh/installation.md` die Zelle der
    Windows-Server-Zeile, die neuen Zeilen für Debian 12 und Ubuntu 22.04 und für Ubuntu 24.04 und die Definitionen
    „测试套件已在 CI 中验证“ und „测试套件未在 CI 中运行“; der Plattformsatz in `docs/zh/limitations.md` (wörtlich auch in
    README.bundle.txt und release-notes.md); die Zelle der Audit-Hook-Tests in `docs/zh/privacy.md`;
  - von P6 nach D-17 nur die Kernbegriffe (die fünf Nutzungsarten, Einwilligung und Widerruf, Zugriffsprotokoll,
    Hash-Kette, Platzhalter-Regelpaket, der Grenzsatz und die V-06-Aussage).
- **Sichtprüfung der PDFs** zh/en (KONZEPT 4; NG-F13, REP-00, UF-01). Bis dahin bleiben NG-F13, REP-00 und UF-01
  `nicht verifiziert`, auch nach bestandenem G1-Lauf.
- **Annahmen A-78 bis A-89 zur Freigabe**, darunter:
  - A-84: höchstens 50 Befundzeilen je Regel plus Sammelzeile als Lesart von „jeder Befund“ (NG-F13); Abschnitt 4
    mit den datensatzweiten Werten von M11/M12, Anhang 6.1 (geprüfte Regeln) und 6.6 (Umgebung) als Lesart von
    REP-04/REP-06; Wortlaut der Überschriften in Abschnitt 3 (R05); eigenes SVG statt matplotlib.
  - A-85 (PDF-Weg, Schrift, QA-Gate mit `glyph_missing`, Startflags, Kernel-Importe fontTools/Playwright/pypdf), A-86
    (eigener Notices-Leser statt pip-licenses, Seitensatz der Doku, Offline-Suche, Plattformstand der Nutzerdoku nach
    U1), A-87 (Bündel, Pfadgrenzen, Signatur, Workflows, Release-Entwurf nur mit grüner Testsuite am Tag-Commit,
    Prüfvorgehen ab dem Ende von P5), A-88 (G1-Werkzeug, Skalierungsgrenzen), A-89 (Hilfsprozesse ohne Konsole,
    `platform` ohne WMI, eine Zeile auf stdout bei einem toten Prozess, Bibliothekswarnungen der Worker nicht gezeigt;
    aus der dritten CI-Fix-Runde `quiet_pool`, `on_null_device` und das Umbinden der Ströme im fork-Kind).
  - Aus P4: Alterspalten mit anderen Einheiten als Monate, Wochen, Tage gelten als Jahre; `report --out` nennt seinen
    Pfad auf der Konsole nicht pseudonym. Aus früheren Phasen: Restpunkte A-78, Zeitangaben ab 27,8 h nur auf 1 s
    genau (A-61, A-79), loky „resource tracker“ ohne Netzwerkschutz (A-79), Herkunft und Lizenz der ICLabel-Gewichte
    (A-56).
- **Signatur, Lesart von D-10 g nach D-15 bestätigen** (Installer-Hinweis R16): Mit cosign (auf PATH oder
  `-Cosign`/`--cosign`) wird die Signatur immer geprüft, `-SkipSignatureCheck`/`--skip-signature-check` übergeht keine
  Ablehnung und lässt nur eine Installation ohne cosign weiterlaufen; die Meldung nennt für einen Rechner ohne
  Sigstore-Vertrauensanker den Weg „nach der Prüfung auf einem vernetzten Rechner ohne cosign auf PATH und mit dem
  Schalter“. R12: Die Prüfung im Archiv belegt nur Integrität (dokumentierte Grenze); die Installer nennen die geprüfte
  Identität zum Vergleich mit den Release-Notes.
- **Lesart von D-15 bei core-js-pure 3.49.0 bestätigen:** Die Version stammt aus dem Quelltext der Source-Map, nicht aus
  einem Pfad (NACHBAU 8).
- **Bekannte Grenzen zur Kenntnis:**
  - Die Ausgabe von `convert` ist zwischen den Betriebssystemen nicht bytegleich: MNE-BIDS und pybv schreiben Textdateien
    mit `os.linesep` („Übergreifend“, BrainVision unter Linux).
  - Die Codepage-Werte `mbcs`, `dbcs` und `oem` bleiben plattformabhängig (unter Linux LookupError).
  - `avoid_wmi()` ersetzt eine private Funktion von CPython (`platform._wmi_query`); `quiet_pool` stützt sich auf private
    Teile von `concurrent.futures` und `multiprocessing` (`_SafeQueue`, `_CallItem`, `_on_queue_feeder_error`,
    `_call_queue`, `Queue._buffer`; gleich in 3.11.17, 3.12.15 und 3.13.7). Eine neue CPython-Version ist erneut zu
    prüfen (A-89).
  - Was eine Bibliothek direkt auf das Konsolengerät schreibt, bleibt ein Restrisiko; die Hilfsprozesse bleiben an der
    Konsole, damit Strg+C sie beendet (A-89). Hinter `on_null_device` (onnxruntime in ICLabel) verhielte sich eine
    Bibliothek falsch, die den alten Std-Handle-Wert zwischenspeichert oder im Block einen `logging.StreamHandler`
    anlegt; in onnxruntime, mne_icalabel und picard gibt es keines (A-89).
  - Ein forkserver oder resource tracker, den anderer Code desselben Prozesses vor NeuroGrids erstem Pool startete,
    behält seine Konsolen-Deskriptoren; in der CLI unter Linux kommt das nicht vor (A-89).
  - Mit `--jobs` > 1 erscheinen Bibliothekswarnungen der Worker nicht; die Konsole unterscheidet sich darin von
    `--jobs 1`, results.json nicht (A-89). Die Zeile `cli.check.recomputed` erscheint auch, wenn ein Teil nicht
    zustellbar war oder nicht gesendet werden konnte; ihr Text spricht von einem unerwartet beendeten Hilfsprozess.
  - Nur in der CI belegt (D-09): alle POSIX-Teile von A-89 und die Behebung unter Python 3.11 auf windows-latest (CI auf
    27c3e90 grün); der Aufruf von `ci.yml` aus `release.yml` läuft erst am ersten Release-Tag (A-87). Windows 10 ist
    nicht verifiziert (NG-N04 `teilweise`).
- **Anfrage an die Entwickler des BIDS-Validators** (D-16): den Entwurf
  (`.local/p5/upstream_issue_bids_validator.md`, nicht versioniert) prüft und sendet der Projektverantwortliche.
- **Merge und Veröffentlichung** (je Schritt durch den Projektverantwortlichen): Merge von `dev` nach `main` und Push;
  Version 0.1.0, Tag `v0.1.0` und `release.yml` (vorher die Platzhalter `<REPO_URL>` und `<PYPI_RELEASE>` in docs/en und
  docs/zh mit der freigegebenen Adresse füllen; `tools/release_check.py` sperrt das Release, solange sie stehen, und der
  Release-Entwurf entsteht nur, wenn `ci.yml` auf dem getaggten Commit besteht); PyPI über `publish-pypi.yml` (Trusted
  Publishing bei TestPyPI und PyPI eintragen, erst TestPyPI); Gitee-Spiegel (`mirror-gitee.yml`, Secret
  `GITEE_SSH_KEY`, Variable `GITEE_MIRROR`) und das Gitee-Release von Hand am gespiegelten Tag (R15).

## Verlauf

### 2026-10-28 – Dritte CI-Fix-Runde (p5-ci3; NG-N05, NG-N03, TECH-05, NG-F07, NG-N04, TECH-06, V-06, NG-N08)
- **Anlass:** CI auf 18da12f (`.local/ci_18da12f.txt`): `offline` (40609866836) grün, `ci` (40609866806) rot in allen
  sechs Testjobs: windows-latest mit Python 3.12 und 3.13 je 1 Fehler, mit Python 3.11 3 Fehler, ubuntu-24.04 mit Python
  3.11/3.12/3.13 je 5 Fehler. Überall `test_env_example.py` (`__PYVENV_LAUNCHER__`), unter Linux dazu der tracker-Test
  mit spawn und forkserver, der fork-Starttest und der CLI-Konsolentest (`AssertionError: 1`), auf windows-latest mit
  Python 3.11 derselbe CLI-Test (`AssertionError: 2`) und der Semaphor-Test (Traceback aus `queues.py`). Ursachen und
  Behebungen in ENTSCHEIDUNGEN A-89 „Dritte CI-Fix-Runde“.
- **Vorgehen:** drei Bereiche parallel auf eigenen Zweigen, je mit Nachprüfung und Reparaturrunde; gemergt in ce87432
  (posix), f3fe478 (win311) und 1dd0eac (docs).
  - posix (p5-ci3-posix): Der tracker-Test war ein Wettlauf im Test, er wartet jetzt auf das Ende des stillen trackers
    (919bd11). Ein geforktes Kind erreichte über Ströme auf einem Deskriptor über 2 die Konsole: `null_descriptors` deckt
    auch die Deskriptoren hinter den sys-Strömen, ein im Fenster geforktes Kind bindet seine Ströme vor dem Bootstrap an
    das Nullgerät (3d212b5). Mit `--jobs 1` schrieb onnxruntime unter Linux eigene Zeilen auf Deskriptor 2: neu
    `kernel/processes.on_null_device()` für ICLabel (223206b), unter Windows mit Deskriptoren 1 und 2 und den sys-Strömen
    auf einer Senke (7f5b3b0, berichtigt die Annahme von 223206b über den Windows-Build). Ein Fenster ohne freie
    Deskriptoren ändert nichts mehr (1ebe89b). `USER` und `LOGNAME` sind im Scan geprüft (9b9a98b); die Docstrings
    nennen die Grenze fremder forkserver und tracker (5aa8749).
  - win311 (p5-ci3-win311): Der Traceback kam vom Feeder-Thread der Aufrufwarteschlange im eigenen Prozess (CPython 3.11
    legt nach dem Tod eines Workers noch Stoppsignale in die geschlossene Warteschlange). Neu `kernel/processes.quiet_pool`
    in `quality._pool` (9b355bd, a25fc54, 2c82a5f); eine Aufgabe, die nicht gesendet werden konnte, scheitert an ihrer
    eigenen Future und wird allein nachgerechnet (95f6c50); die genaue Bedingung unter 3.11 steht in 25ead0d; die
    Meldungen der Konsolentests nennen, was sie gemessen haben (aa03735).
  - docs (p5-ci3-docs): `__PYVENV_LAUNCHER__` in `THIRD_PARTY` des Scans (29ff4af). Plattformzellen der Nutzerdoku
    (U1, 17e0d3f): Windows Server und Ubuntu 24.04 „Testsuite in der CI verifiziert (Python 3.11–3.13)“, Debian 12 und
    Ubuntu 22.04 „Testsuite nicht in der CI ausgeführt“, Windows 10 „nicht verifiziert“; dasselbe in limitations.md,
    privacy.md (Audit-Hook-Tests), README.bundle.txt und den Release-Notes, en und zh; die alten Sätze sind als ganze
    Sätze verboten (341beb1). `release.yml` ruft `ci.yml` auf dem getaggten Commit auf, ohne grüne Testsuite kein
    Release-Entwurf (dd9ab93). Der Kommentar über `V01_ITEMS` sagt, dass nur NG-F13 auf G1 wartet (d269cb9).
  - Danach: Ein grüner Testjob schreibt Testzahlen und Abdeckung als Hinweis-Annotation, ohne Anmeldung lesbar
    (2a49a0c, 27c3e90).
- **Prüfvorgehen ab dem Ende von P5** (ENTSCHEIDUNGEN A-87; nach der Kritik des Projektverantwortlichen vom
  28.10.2026): Die volle Testsuite läuft nur in der CI (sechs Testjobs); lokal laufen nur die betroffenen Tests;
  Testzahlen und Abdeckung kommen aus den Hinweis-Annotationen der CI; die Umsetzungsdoku wird je Phase einmal nach
  grüner CI geschrieben; lange Läufe (G1-Abnahme, Korpustests) laufen nur einmal auf dem Endstand. Die lokalen vollen
  Läufe früherer Runden (zuletzt dcec9bd: 3647 bestanden, 21 übersprungen, 127 abgewählt, 1 fehlgeschlagen) bleiben als
  Verlauf im P5-Eintrag.
- **Ergebnisse:**
  - CI auf 27c3e90 (`.local/ci_27c3e90.txt`) ganz grün: `ci` (Lauf 40680346160) mit allen sechs Testjobs ohne Fehler,
    Abdeckungs-Gates, Lizenz-Gate mit Paketscan, Windows PowerShell 5.1, PowerShell 7, Anforderungs-IDs und
    Plattformvergleich (berichtet, nicht erzwungen); `offline` (Lauf 40680346176) mit allen neun Jobs.

    | Testjob | bestanden | übersprungen | Tests | Kern | Prüfer |
    |---|---|---|---|---|---|
    | windows-latest, Python 3.11 | 3681 | 16 | 3697 | 93,4 % | 97,3 % |
    | windows-latest, Python 3.12 | 3682 | 15 | 3697 | 93,5 % | 97,3 % |
    | windows-latest, Python 3.13 | 3682 | 15 | 3697 | 93,5 % | 97,3 % |
    | ubuntu-24.04, Python 3.11 | 3605 | 97 | 3702 | 93,3 % | 97,3 % |
    | ubuntu-24.04, Python 3.12 | 3605 | 97 | 3702 | 93,3 % | 97,3 % |
    | ubuntu-24.04, Python 3.13 | 3605 | 97 | 3702 | 93,3 % | 97,3 % |

  - Lokal auf 27c3e90 (Windows 11, nur die von der Runde betroffenen Tests; keine volle lokale Suite): Python 3.12 184
    bestanden, 5 übersprungen, 52 abgewählt in 41 min; Python 3.11 18 bestanden, 4 übersprungen.
  - G1-Lauf auf 18da12f (vor der Runde, `.local/p5/ci3/g1_summary_18da12f.md`): 6 von 6 Datensätzen in 5 Formaten
    bestanden, alle Kriterien des Laufs erfüllt, beide Läufe bytegleich, `--jobs 1` = `--jobs 4`, Korpus unverändert,
    V-01-Checkliste des Laufs erfüllt, V-06 ja, 151 min. Weil die Runde den Windows-Weg von `check --jobs` änderte
    (`quiet_pool`, `on_null_device`), läuft die Abnahme einmal auf dem Endstand 27c3e90: 6 von 6 Datensätzen in 5 Formaten bestanden, alle Kriterien erfüllt, 0 Probleme, V-01 erfüllt, V-06 ja (149 min 28 s; `.local/p5/ci3/g1_summary_27c3e90.md`).
- **Nicht verifiziert:** Die genaue Zeile von onnxruntime unter Linux hat die CI nie gezeigt (die Ursache stützt sich
  auf die Zeichenketten des Wheels; seit 27c3e90 besteht der Test). Der Aufruf von `ci.yml` aus `release.yml` lief noch
  nie (erst am ersten Release-Tag). Grenzen der Runde: ENTSCHEIDUNGEN A-89 und die Liste „Für STOPP G1 vorgemerkt“.

### 2026-10-27 – G1-Befund: Worker auf der Konsole (p5-g1-console; NG-N05, NG-N03, TECH-05, NG-F07)
- **Befund** (G1-Lauf auf dcec9bd, ds004504-1.0.9, `check --jobs 4`, Lauf 1): Konsole mit Laufwerkspfad, Traceback, Benutzerordner, Benutzername und Nicht-UTF-8 (NG-N05, A-51), Laufzeit 935,6 s statt 299,4 s. Ein Pool-Prozess starb in `call_queue.get` an `self._sem.release()` mit `OSError: [WinError 6]`; derselbe Traceback im vollen Testlauf (`test_one_recording_with_jobs_4_equals_jobs_1`).
- **Ursache** (A-89): CPython 3.12s WMI-Abfrage hinter `platform.uname()` (im Worker über `import scipy.signal`) bricht nach 1000/100 ms ab; ihr Thread läuft mit einem Zeiger in den beendeten Stackrahmen weiter und schließt einen fremden Handle-Wert, hier das Semaphor der Aufrufwarteschlange. Handle-Monitor je Prozess: mit WMI 7 von 9 Läufen mit totem Worker, jede Schließung während `platform.uname()` nach der abgebrochenen Abfrage; ohne `_wmi` 0 von 9, mit der Behebung 0 von 6 (kein Semaphor verloren). Herunterfahren und Abbruch des Pools waren nicht beteiligt.
- **Behoben:** `kernel/processes.py`: `avoid_wmi()` in `cli.main()`, in jedem Worker-Initializer und in der Testsitzung; die Pool-Prozesse starten auf dem Nullgerät (Windows: STARTUPINFO, POSIX: Deskriptoren 0–2 beim Start), der Initializer legt Deskriptoren und sys-Ströme zuerst auf das Nullgerät (auch loky); der PDF-Treiber startet mit stderr auf dem Nullgerät. Tests: `tests/unit/test_processes.py`, `tests/integration/test_worker_console.py` (auf dcec9bd scheitern alle drei Integrationstests).
- **Ergebnisse (Windows 11, Python 3.12.15, `NEUROGRID_REQUIRE_PDF=1`, `PYTHONWARNDEFAULTENCODING=1`):** Neue Tests: `tests/unit/test_processes.py` 6 bestanden, 1 übersprungen (POSIX); `tests/integration/test_worker_console.py` 3 bestanden, auf dcec9bd 3 gescheitert. Nachbarn: `test_quality_review_p3.py` 26 bestanden (u. a. `--jobs 1` = `--jobs 4`, sterbender Worker, loky-Rückfall); `test_quality_pipeline.py` und `test_quality_sample.py` 76 bestanden (NG-N03 über Jobs und BLAS-Threads); `test_architecture.py` und `test_validator.py` bestanden; `test_processes.py`, `test_worker_console.py`, `test_pdf_unit.py`, `test_cli.py`, `test_report_pdf_cli.py`, `test_docs_browser.py` und `test_console_sentence.py` zusammen 116 bestanden, 1 übersprungen (POSIX). `test_report_pdf.py` 49 bestanden; danach `tools/install_pdf_browser.py --check`: PDF-Browser vollständig (Revision 1243, 290 Dateien). ruff, `mypy src/neurogrid tools` und `mypy --strict src/neurogrid/kernel` (auch `--platform linux`) sauber. Korpus ds004504-1.0.9 (`check --jobs 4` wie `tools/acceptance_g1.py`): auf dcec9bd 0 von 3 Läufen mit Konsolenproblem (398,3 / 320,9 / 313,0 s; die Rate ohne Monitor ist niedrig), mit der Behebung 0 von 3 (327,5 / 317,7 / 319,6 s), results.json in allen sechs Läufen bytegleich. `tools/acceptance_g1.py --datasets ds004504-1.0.9` auf der Behebung: 1 von 1 Datensätzen bestanden, keine Probleme (Konsole, Datenschutz, Dateien, Berichte), beide Läufe bytegleich, Korpus unverändert, `check` 314,8 / 319,2 s statt 935,6 / 299,4 s; results.json und die vier Berichte bytegleich zum G1-Lauf auf dcec9bd (Minimum und Gesamtkriterien sind mit nur einem Datensatz nicht erfüllt).
- **Nachprüfung, drei Punkte behoben** (A-89): (1) POSIX mit spawn oder forkserver: Der resource tracker von multiprocessing startete beim ersten Semaphor eines Pools mit der Konsole; endete der CLI-Prozess ohne Finalizer (SIGKILL, OOM-Killer), schrieb er `resource_tracker: … leaked semaphore objects` mit Installationspfad. `pool_context()` startet ihn jetzt auf dem Nullgerät (Test: Prozess mit NeuroGrid-Pool, SIGKILL, stderr leer, Semaphor trotzdem entfernt; Gegenprobe mit einfachem Pool zeigt die Warnung). (2) Direktes Schreiben auf das Konsolengerät (`CONOUT$`, `msvcrt.putwch`, `/dev/tty`) umgeht beide Schichten; die Prozesse bleiben an der Konsole, damit Strg+C sie beendet (A-77); als Grenze in A-89 mit dem Suchergebnis über die Umgebung. (3) Ein toter Pool- oder loky-Prozess (oder ein nicht zustellbarer Teil) erscheint jetzt einmal als übersetzte Zeile `cli.check.recomputed` (zh/en/de) auf stdout, bevor die Wiederholungen beginnen; results.json bleibt unberührt.
- **Ergebnisse der Nachprüfung (Windows 11, Python 3.12.15, `NEUROGRID_REQUIRE_PDF=1`, `PYTHONWARNDEFAULTENCODING=1`):** `test_quality_review_p3.py` und `test_worker_console.py` 30 bestanden (u. a. `--jobs 1` = `--jobs 4`, sterbender Worker, loky-Rückfall, die Zeile genau einmal bei `--jobs 2`); `test_quality_pipeline.py`, `test_quality_sample.py`, `test_language_and_wording.py` und `test_processes.py` 128 bestanden, 2 übersprungen (POSIX, darunter der tracker-Test); `test_cli.py`, `test_architecture.py`, `test_console_sentence.py`, `test_g1_checks.py`, `test_zh_review_package.py`, `test_provenance_pipeline.py` und `test_packaging_texts.py` 182 bestanden. ruff, `mypy src/neurogrid tools` und `mypy --strict src/neurogrid/kernel` (auch `--platform linux`) sauber. Korpus ds004504-1.0.9 (`check --jobs 4` wie `tools/acceptance_g1.py`): Exit 0 in 311,4 s, stderr leer, Konsolen- und Datenschutzprüfung ohne Befund, keine Zeile `cli.check.recomputed` (kein Worker starb), results.json bytegleich zum G1-Lauf auf dcec9bd, Korpus unverändert.
- **Gemergt:** 18da12f (gepusht). CI auf 18da12f: `offline` (40609866836) grün, `ci` (40609866806) rot in allen sechs Testjobs, behoben in der dritten CI-Fix-Runde (Eintrag oben); CI auf 27c3e90 ganz grün (`ci` 40680346160, `offline` 40680346176). Keine volle lokale Suite auf dem Endstand (Prüfvorgehen ab dem Ende von P5, A-87). Voller G1-Lauf auf 18da12f: 6 von 6 Datensätzen bestanden, alle Kriterien erfüllt (151 min); Endlauf auf 27c3e90: 6 von 6 Datensätzen in 5 Formaten bestanden, alle Kriterien erfüllt, 0 Probleme, V-01 erfüllt, V-06 ja (149 min 28 s; `.local/p5/ci3/g1_summary_27c3e90.md`).
- **Nur in der CI verifiziert:** die POSIX-Zweige (fork, spawn, forkserver, resource tracker; lokal kein Linux): auf 18da12f rot, auf 27c3e90 grün.

### 2026-10-27 – P5 Bericht, PDF, Dokumentation, Bündel, Abnahme
- **Abgeschlossen:** NG-F14, NG-F18, CLI-05, REP-01, REP-02, REP-03, REP-04, REP-05, REP-06, REP-07, POS-01, ARC-05, ARC-06, TECH-06, TECH-10, NG-N01, NG-N03, NG-N05, NG-N06, CON-01, CON-04, V-06, UF-07, UF-08; aus P1 nachgetragen: TECH-11 (CI aktiv); nach der zweiten CI-Fix-Runde (CI auf dcec9bd grün): TECH-05, TECH-07, NG-N08; nach D-17: NG-N07; TECH-05 und NG-N08 nach dem roten Lauf auf 18da12f mit der dritten CI-Fix-Runde auf 27c3e90 erneut grün.
- **Umgesetzt, Nachweis offen (`nicht verifiziert`):** NG-F13, REP-00, UF-01 (G1-Lauf auf 18da12f bestanden, Endlauf auf 27c3e90: 6 von 6 Datensätzen in 5 Formaten bestanden, alle Kriterien erfüllt, 0 Probleme, V-01 erfüllt, V-06 ja (149 min 28 s; `.local/p5/ci3/g1_summary_27c3e90.md`); offen bis G1 die Sichtprüfung der PDFs, für NG-F13 dazu die Freigabe der Lesart von „jeder Befund“).
- **Teilweise:** V-01 (G1-Lauf, Release nach G1), NG-N04 (Windows 10 nicht verifiziert), POS-02 und CON-05 (Platzhalter `<REPO_URL>`, Release nach G1). **Blockiert (extern):** TECH-08 (Gitee-Konto und Secret).
- **Beigetragen zu:** UF-02, CON-02, TECH-01, RP-07.
- **Gebaut** (vier Bereiche parallel nach den verbindlichen Vorgaben B1–B6, ENTSCHEIDUNGEN A-84 bis A-87):
  - Bericht (A-84): sechs Abschnitte zh/en; Deckblatt nach REP-01; Zusammenfassung mit Ampel, Summen und Abdeckungsmaß; Befunde mit zehn Zellen und erklärten leeren Zellen, höchstens 50 Zeilen je Regel plus Sammelzeile; Metriktabelle je Aufnahme und Verteilungsgrafiken als eigenes SVG (`report/charts.py`); Nachweise; Anhang 6.1–6.6; Abgrenzung (ARC-05) und Worttest `report/wording/statements.yaml`; Glyphensicherheit; Generator für den Skalierungsfall 1000 × 64 (`tools/gen_fixtures.py`).
  - PDF (A-85): `report/output.py` `write_reports` (zwei Durchgänge, alles oder nichts), `kernel/fonts.py` (Subsets, Glyph-Zwillinge), `kernel/pdf.py` (Shell aus dem NeuroGrid-Ordner, Startprüfung mit `ldd` und `pdf_linux_packages.json`, Druck, Datumsfelder, QA-Gate); statische Schriften aus `tools/build_fonts.py`; `tools/install_pdf_browser.py`; `report --format pdf`; netguard-Lesart für die asyncio-Schleife (A-49).
  - Doku, Meldungen, Notices, Lizenzen (A-86): MkDocs-Website zh/en mit je 16 Seiten (`tools/gen_docs.py`, `tools/build_docs.py`, `tools/mkdocs_hooks.py`), Offline-Suche; Hilfe und Bedienfehler der Kommandozeile übersetzt (`cli.help.*`, `cli.error.*`); `tools/notices.py` → `THIRD_PARTY_NOTICES.txt`; `license-gate/` mit `components.toml` und `known_missing.toml`; REUSE mit OFL-1.1 für die Schriften; V-06-Test; core 0.1.1 (Quellenangabe der Doku).
  - Bündel, Signatur, Workflows (A-87): `tools/bundle.py` (build, verify; byte-gleich), `packaging/` (install.ps1/install.cmd, install.sh, README, Release-Notes), Signatur nach D-15, `tools/release_check.py`, `tools/scan_runtime_network.py`, `tools/strace_check.py`, Reinraum-Skripte, sieben Workflows, `.env.example`.
- **Integration:** PDF-Weg mit allen Bereichen (u. a. privater Arbeitsordner `ng-pdf-*` des Browsers im temporären Ordner, nie unter `--out`), Bündel mit Präfix an der Längengrenze im Windows-Reinraum, Lizenztexte nach D-15 (CC BY 4.0, Lizenzdateien der Validator-Pakete) und D-16 (LGPL-Abschnitt im Validator); Abnahme (A-88): `tools/acceptance_g1.py`, Skalierungstest, zh-Prüfpaket, fester Satz auf der Konsole jedes Befehls.
- **Review:** vier Prüfrichtungen (Bericht/PDF, Datenschutz, Bündel/CI, Doku/Lizenzen/Abnahme), jeder Befund gegengeprüft.
  - 30 Befunde R00–R29: 29 bestätigt, R12 strittig (Entscheidung: dokumentierte Grenze, die Installer nennen die geprüfte Identität). Behoben sind alle, je mit Test, nachgeprüft und in einer Reparaturrunde nachgebessert; R08 und R09 (Nutzerdoku, in der Fix-Runde keinem Bereich zugeordnet) erst in der zweiten CI-Fix-Runde (p5-ci2-userdocs).
  - Wichtigste Befunde:
    - R19: Die Doku-Website im Bündel enthielt fremdes JavaScript ohne Nennung, darunter lunr-languages (MPL); jetzt entfernt bzw. geprüft (`license-gate/third_party/mkdocs-material-9.7.7/`).
    - R00: Berichte wurden beim Ersetzen nicht alles oder nichts geschrieben; R01: ein langer Wert verkleinerte jede PDF-Seite auf 2/3.
    - R10: Die Bündel-Tests liefen nicht auf jedem Push auf `dev` (gegen D-15); R11: tote Loopback-Proxies ließen Netzversuche im strace- und WFP-Nachweis als erlaubt erscheinen.
    - R07, R13, R06: Installationshinweis, Installer und Browser-Installer zeigten Benutzerordner bzw. einen nicht ausführbaren Befehl.
    - R20–R24, R29: Das G1-Werkzeug verglich Klausel, Messwert, Schwelle und Titel nicht, suchte weder rohe Datei- und Ordnernamen noch ganzzahlige Rohalter, zählte unlesbare Datensätze mit und prüfte den festen Satz im HTML nicht.
  - Fix-Runde in vier Bereichen (report, linux, bundle, docs). Sie behob auch die Fehler des GitHub-Laufs auf c3be509 (Lauf 40355705974; annotiert: windows-latest 3.12/3.13 je 18 Fehler, ubuntu-24.04 3.11/3.12 je 18 Fehler und 10 Setup-Fehler): `Get-FileHash` fehlt in Windows PowerShell 5.1 unter dem Modulpfad von PowerShell 7, EncodingWarning aus `ldd` in der PDF-Startprüfung, Benutzername in `/tmp`-Pfaden, UNC- und Gerätepfade unter POSIX, ein nur unter Windows gültiger Test; dazu Annotationen für bis zu 40 Fehler je Job. Offen blieb `test_pdf_tests_pass_with_a_long_basetemp` (windows-latest), behoben in der zweiten CI-Fix-Runde.
  - Merges 28de466, 2e1e24e, e204c7b, 862de1d; Merge-Fix 55335ca (die Sicherungsdatei aus R00 entsteht über `create_temporary`, das die Linux-Fix-Runde an die Stelle von `mkstemp` setzte). Ein semantischer Konflikt zwischen R11 (Bündel) und R25 (Doku) ließ den strace-Test der Doku scheitern, behoben in 181654e.
- **Zweite CI-Fix-Runde (p5-ci2)** gegen die roten Testjobs von `ci` auf 55335ca, je Bereich mit Test, der vorher scheitert, Nachprüfung und Reparaturrunde (ENTSCHEIDUNGEN „Übergreifend“, A-84 bis A-87):
  - chrome-log (b2b5246): Unter Windows schreibt jeder Kindprozess der Shell in `debug.log` neben dem Programm (Quelltext von Chromium 153); der Netzwerkdienst tat das beim Schließen eines eben gestarteten Browsers. Er läuft dort jetzt im Browserprozess (`--enable-features=CDPScreenshotNewSurface,NetworkServiceInProcess2`, Playwrights eigenes Feature wiederholt); neuer Test „Browser gleich nach dem Start geschlossen, Ordner unberührt“ (vorher in jedem Lauf mit der CI-Zeile gescheitert).
  - win-runner (18d1750): Auf dem Runner sind TEMP und die Benutzervariablen 8.3 geschrieben (`RUNNER~1`); `install.ps1` schreibt und zählt das Präfix lang (`Get-LongPath`) und verdeckt auch die lange Schreibweise von LOCALAPPDATA und USERPROFILE (ein echter A-51-Fehler: `C:\Users\runneradmin\…` in der Ausgabe von uv). Die Zeitüberschreitung der Doku-Suche war ein Wettlauf im Test (mkdocs-material liest die Suche nur bei keyup, focus oder bereitem Worker).
  - linux-p2 (a4196e2): MNE liest die Markerdatei für das Datum mit der Kodierung des Locale, MNE-BIDS kopiert mit der Codepage als Codec (`ANSI` nur unter Windows). NeuroGrid liest diesen Schritt als Latin-1 und kopiert ANSI als Latin-1 auf jedem System, gehalten über das threadsichere `io.base.ModulePatch`; der Test „MNE folgt dem Backslash-Verweis“ läuft nur unter Windows, ein POSIX-Gegenstück hält das Linux-Verhalten fest.
  - userdocs (d4f3214): R08 und R09 behoben; Plattform- und Nachweisstand der Nutzerdoku nach dem grünen `offline`-Lauf, auch in README.bundle.txt und den Release-Notes; Firewall-Prüfung wie im Windows-Reinraum (A-86).
  - linux-pdf (df1c790): `--font-render-hinting=none` (unter Linux setzte die Shell gehintete Ganzpixel-Positionen, pypdf las Leerzeichen in Regel-IDs; unter Windows bytegleich); jede Regel-ID in einem Element, das nicht umbricht, auch im Fließtext (gemessen: „CORE-M05-“ | „02“ brach vorher auch unter Windows); QA-Gate `glyph_missing` für das .notdef-Kästchen und Gegenproben ohne Systemschriften (auf ubuntu-24.04 ergab die Radikal-Gegenprobe vorher kein Urteil).
  - Doku der Runde mit dcec9bd; ein Querabgleich berichtigte u. a. die Python-Version der Suite auf 55335ca (3.12, nicht 3.13) und die Reihenfolge der ersten CI-Läufe (NACHBAU).
- **D-17 Lizenztexte** (9d8afcb): 70 Downloads aus der freigegebenen URL-Liste, 70 abgelegte Texte (bids-validator 3.0.2: 45, h5py 3.16.0: 1, mkdocs-material 9.7.7: 3, python-build-standalone 3.12.15+20261009: 21), alle freizügig; `known_missing.toml` leer, `tools/notices.py --check` endet mit 0; neue Prüfungen für abgelegte Texte, Auszüge und die Bibliotheken von python-build-standalone (`notices.py --sources` gegen lokale Kopien: 4 Texte, 0 Probleme). Unabhängig nachgeprüft: jede Datei mit Größe und SHA-256 der Liste, die ganzen Texte bytegleich zu einem zweiten Download, die vier Auszüge gegen ihre Quelle.
- **G1-Befund auf dcec9bd** (eigener Eintrag oben, A-89): ein sterbender Pool-Prozess schrieb auf die Konsole; behoben mit `avoid_wmi()` und Hilfsprozessen auf dem Nullgerät, gemergt in 18da12f.
- **Dritte CI-Fix-Runde** (eigener Eintrag oben, A-89): die roten Testjobs von 18da12f behoben (`quiet_pool`, `on_null_device`, Ströme im fork-Kind, Variablen des Scans, Plattformzellen der Nutzerdoku, Release nur mit grüner Testsuite am Tag-Commit), gemergt bis 1dd0eac, CI auf 27c3e90 ganz grün; dazu das Prüfvorgehen ab dem Ende von P5 (A-87).
- **Ergebnisse (lokal, Windows 11):**
  - Volle Suiten der Fix-Runde: report c9a536a 3502 bestanden, 23 übersprungen; linux 191a62a 3510 bestanden, 25 übersprungen (mit `PYTHONWARNDEFAULTENCODING=1`); bundle d42bbf4 3498 bestanden, 23 übersprungen.
  - Gemergter Stand 55335ca (Python 3.12, `NEUROGRID_REQUIRE_PDF=1`, `PYTHONWARNDEFAULTENCODING=1`): 3597 bestanden, 24 übersprungen, 127 abgewählt, 1 fehlgeschlagen (strace-Test der Doku, behoben in 181654e).
  - Nach der zweiten CI-Fix-Runde auf dcec9bd (gleiche Umgebung): 3647 bestanden, 21 übersprungen, 127 abgewählt, 1 fehlgeschlagen, nur an seiner Zeitgrenze (`test_quality_review_p3.py::test_one_recording_with_jobs_4_equals_jobs_1`, 122,5 s statt höchstens 120 s; die Suite lief auf dem ausgelasteten Rechner 4 h 07 min statt etwa 30 min; im mitgeschnittenen stderr derselbe tote Pool-Prozess wie im G1-Befund, `SpawnProcess-18`, A-89; allein bestanden, in der CI grün). Auf dem Endstand 27c3e90 lief keine volle lokale Suite (Prüfvorgehen ab dem Ende von P5, A-87); die volle Suite belegt die CI (`ci` 40680346160, alle sechs Testjobs ohne Fehler; Zahlen im Eintrag der dritten CI-Fix-Runde), lokal liefen nur die betroffenen Tests (Python 3.12: 184 bestanden, 5 übersprungen, 52 abgewählt; Python 3.11: 18 bestanden, 4 übersprungen).
  - G1-Lauf (`tools/acceptance_g1.py`, 4587546): 6 von 6 Datensätzen in 5 Formaten (BDF, BrainVision, EDF, EEGLAB, FIF), alle Kriterien des Laufs erfüllt, zwei Läufe byte-gleich, `--jobs 1` = `--jobs 4`, Korpus unverändert, V-01-Checkliste des Laufs erfüllt (nur die Kriterien dieses Laufs; Matrix V-01 teilweise), V-06 ok; unabhängig nachgeprüft (alle 42 Ausgabedateien byte-gleich). Nach den Korrekturen R20–R24 mit verschärften Prüfungen auf 3 Datensätzen erneut bestanden.
  - G1-Lauf auf dcec9bd (alle sechs Datensätze): 5 von 6 bestanden (BDF, BrainVision, EDF, FIF), Minimum erfüllt, beide Läufe bytegleich, `--jobs 1` = `--jobs 4`, Korpus unverändert, V-06 ja; ds004504-1.0.9 (EEGLAB) nur am Konsolenbefund von Lauf 1 gescheitert (A-89), Befundzeilen, Berichte und Dateien aller sechs ohne Problem; damit „alle Kriterien dieses Laufs“ und V-01 des Laufs nicht erfüllt. Voller Lauf auf 18da12f: 6 von 6 Datensätzen in 5 Formaten (BDF, BrainVision, EDF, EEGLAB, FIF) bestanden, Minimum erfüllt, alle Kriterien des Laufs erfüllt, beide Läufe bytegleich, `--jobs 1` = `--jobs 4`, Korpus unverändert, V-01-Checkliste des Laufs erfüllt, V-06 ja, keine Probleme, 151 min; ds004504-1.0.9 `check` 333,0 / 324,6 s. Endlauf auf 27c3e90: 6 von 6 Datensätzen in 5 Formaten bestanden, alle Kriterien erfüllt, 0 Probleme, V-01 erfüllt, V-06 ja (149 min 28 s; `.local/p5/ci3/g1_summary_27c3e90.md`).
  - Skalierung (A-88, 1000 Aufnahmen × 64 Kanäle):

    | Fall | Befunde | `report` HTML | `report` HTML+PDF | PDF-Seiten zh/en |
    |---|---|---|---|---|
    | ungünstigster | 128 742 | 21,4 s / 1703 MB | 108,8 s / 1929 MB | 99 / 106 |
    | typisch | 6 110 | 13,0 s / 364 MB | 92,1 s / 1284 MB | 136 / 142 |

    Grenze im Test: größter Wert der Läufe vom 26.10.2026 plus 50 %, aufgerundet (z. B. 164 s / 2894 MB für HTML+PDF im ungünstigsten Fall).
  - Lizenz-Gate (Laufzeit, Dev, Doku) und Komponentenprüfung (129 Wheels beider Ziele, 4 Bündelteile) grün auf dem 103-Paket-Lock (Zweig p5-acceptance, 228ec49); `notices.py --check` meldete damals die 8 Lücken (Exit 1), seit D-17 Exit 0.
  - Windows-Reinraum lokal (`-NoOsAudit`, Integrationszweig cb19b17): Präfix an der Grenze (101 Zeichen) installiert, 102 abgelehnt; `report` mit PDF im installierten Bündel 20,2 s.
- **CI (GitHub Actions, 55335ca):**
  - `offline` (Lauf 40403791782) ganz grün: beide Offline-Bündel aus `uv.lock` (unsignierte Entwicklungsbündel), PDF in debian:12-slim mit der dokumentierten Paketliste (`--network none`, strace), glibc 2.27 mit Exit 2 abgelehnt (ubuntu:18.04), Reinraum Windows (powershell 5.1 und pwsh, WFP-Audit, PDF), Reinräume debian:12-slim, ubuntu:24.04, ubuntu:22.04 (`--network none`, ohne Python, uid 1000), jeder v0.1-Befehl unter strace mit `--network none`.
  - `ci` (Lauf 40403791901): grün Lizenz-Gate mit Paketscan, Kommandozeile unter Windows PowerShell 5.1 und PowerShell 7, Anforderungs-IDs; rot die Testjobs: ubuntu-24.04 Python 3.11/3.12/3.13 je 6 Fehler (`test_review_p2_formats.py::test_mne_alone_follows_the_differently_decoded_reference`, zwei Codepage-Umwandlungen in `test_review_p2_convert.py`, `test_report_pdf.py::test_qa_gate_negative_controls`, `::test_rule_ids_do_not_break_inside_in_the_pdf`, der strace-Test der Doku), windows-latest je 5–6 Fehler (drei Tests in `test_install_ps1.py` auf dem Runner, `test_pdf_tests_pass_with_a_long_basetemp`, der strace-Test der Doku, einmal eine Zeitüberschreitung der Suche in `test_docs_browser.py`).
- **CI (GitHub Actions, dcec9bd, nach der zweiten CI-Fix-Runde):** alles grün. `ci` (Lauf 40476578603): Testjobs ubuntu-24.04 und windows-latest × Python 3.11/3.12/3.13 mit Abdeckungs-Gates (die Abdeckungswerte standen damals nur im Protokoll des Laufs; seit 2a49a0c und 27c3e90 als Hinweis-Annotation, Werte des Endstands im Eintrag der dritten CI-Fix-Runde: Kern 93,3–93,5 %, Prüfer 97,3 %), Lizenz-Gate mit Paketscan, Kommandozeile unter Windows PowerShell 5.1 und PowerShell 7, Anforderungs-IDs, Plattformvergleich (berichtet, nicht erzwungen). `offline` (Lauf 40476578452): dieselben neun Jobs wie auf 55335ca.
- **CI (18da12f und 27c3e90):** auf 18da12f `offline` (40609866836) grün, `ci` (40609866806) rot in allen sechs Testjobs; nach der dritten CI-Fix-Runde auf 27c3e90 alles grün, `ci` (40680346160) und `offline` (40680346176); Zahlen und Abdeckung je Testjob im Eintrag der dritten CI-Fix-Runde.
- **Annahmen:** A-84 (Bericht), A-85 (PDF), A-86 (Doku, Meldungen, Notices, Lizenzen), A-87 (Bündel, Signatur, Installation, Workflows), A-88 (Abnahme), A-89 (Hilfsprozesse, G1-Befund); für STOPP G1 vorgemerkt. Der Entwurf der P6-Vorgaben hatte A-89 bis A-91 vorläufig vergeben; P6 beginnt jetzt bei A-90.
- **Nutzerdoku nachgezogen** (dritte CI-Fix-Runde, U1, 17e0d3f und 341beb1): Die Zellen „Testsuite noch nicht verifiziert“ sind ersetzt; Windows Server und Ubuntu 24.04 „Testsuite in der CI verifiziert (Python 3.11–3.13)“, Debian 12 und Ubuntu 22.04 „Testsuite nicht in der CI ausgeführt“ (die CI prüft dort nur das Offline-Bündel), auch in der Zeile der Audit-Hook-Tests in privacy.md, en und zh, in README.bundle.txt und den Release-Notes; `SUITE_PENDING`/`AUDIT_HOOK_PENDING` in `tests/docs/test_docs_sync.py` sind durch Prüfungen gegen die Matrix von `ci.yml` ersetzt (A-86). Belegt durch die grüne CI auf 27c3e90, für jedes Release durch `ci.yml` am Tag-Commit (dd9ab93, A-87). Das zh-Prüfpaket entsteht nach dem letzten G1-Lauf, dem auf 27c3e90 (A-88).
- **Nicht verifiziert:**
  - Auf dem Endstand 27c3e90: Korpustests (`-m corpus`) und `bundle.py sizes` (nach dem Prüfvorgehen einmal auf dem Endstand, A-87); keine volle lokale Suite (die volle Suite belegt die grüne CI).
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

G1-Endlauf auf 27c3e90: 6 von 6 Datensätzen in 5 Formaten bestanden, alle Kriterien erfüllt, 0 Probleme, V-01 erfüllt, V-06 ja (149 min 28 s; `.local/p5/ci3/g1_summary_27c3e90.md`); das zh-Prüfpaket mit dessen Beispiel-PDFs ist erzeugt. Jetzt **STOPP G1**
mit der Liste „Für STOPP G1 vorgemerkt“ (KONZEPT 6: zh-Prüfung, Sichtprüfung der PDFs, Freigabe der Annahmen A-78 bis
A-89, Merge nach `main` und Veröffentlichung). Nach der Freigabe: Version 0.1.0, Tag `v0.1.0`, `release.yml`, PyPI und
Gitee; danach P6 nach dem Entwurf der P6-Vorgaben und D-17 (M14 Option B, zh-Texte Option C), mit Annahmen ab A-90 und
nach dem Prüfvorgehen ab dem Ende von P5 (A-87).
