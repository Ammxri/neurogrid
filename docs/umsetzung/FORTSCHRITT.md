# NeuroGrid – Fortschritt

Bei jedem Sitzungsneustart zuerst lesen: diese Datei, [ANFORDERUNGEN.md](ANFORDERUNGEN.md),
[ENTSCHEIDUNGEN.md](ENTSCHEIDUNGEN.md). PRD: `.local/prd/PRD-1-NeuroGrid.pdf` (Text: `*.layout.txt`, `*.raw.txt`;
Tabellen §12/§13 sind in `*.raw.txt` besser lesbar; Architekturbild: `architektur-s8.png`).

## Aktueller Stand

**Phase P9 abgeschlossen (`dev` 5596a8d: Bereiche Register, Neueinwilligung, Paket und Vergleich, Merge-Entscheidungen des Leads, Querschnittstests; vor P7 und P8 vorgezogen nach D-13 und D-19, weil G-A und G-B nicht erfüllt sind); CI auf 5596a8d grün (`ci` 41447040471, `offline` 41447040492, `ci-integration` 41447040527); nächster Schritt P11 (NeuroArena) vor P10, weil G-C fehlt.**
Freigabemodus A. Git: `main` (Doku-Commit), Arbeitszweig `dev`, gepusht nach `https://github.com/Ammxri/neurogrid`
(D-15; nur `dev`, D-09; zuletzt gepusht: 5596a8d). Version auf `dev` 1.0.0.dev0 seit 8e9575f (D-19); v0.1.0 wird
später aus dem P5-Stand c4f240a plus den Korrekturen der Prüfungen auf einem Release-Zweig geschnitten, ein v0.2.0
ebenso aus dem Endstand von P6 (0ffdd90), jeweils mit Freigabe.
Stand P6: `dev` 0ffdd90, CI ganz grün (`ci` 41422859481, `offline` 41422859830); davor auf d50158b `ci` 41402168683
rot nur an fünf Tests außerhalb der Bereiche, behoben in 2f2a5a5. Die volle Testsuite läuft nur in der CI (A-87);
lokal liefen nur die betroffenen Tests (Zahlen in den Einträgen von P9 und P6). Stand P5: CI auf 27c3e90 ganz grün (`ci` 40680346160, `offline` 40680346176); G1-Endlauf
auf 27c3e90: 6 von 6 Datensätzen in 5 Formaten bestanden, alle Kriterien erfüllt, 0 Probleme, V-01 erfüllt, V-06 ja (149 min 28 s; `.local/p5/ci3/g1_summary_27c3e90.md`).
STOPP G1 (29.10.2026, D-18): Annahmen A-78 bis A-89, R16 und die D-15-Lesart zu core-js-pure freigegeben; P6 lief parallel zur zh-Prüfung und zur Sichtprüfung; das Release v0.1.0 erst danach.
Offen beim Nutzer: die übrigen Punkte von „Für STOPP G1 vorgemerkt“ (darunter die Kernbegriffe von P6 für die
zh-Prüfung), die Punkte von „Für STOPP G2 vorgemerkt“ (darunter A-90 bis A-99, die Kernbegriffe von P9, die
Sichtprüfung einer Nachweismappe, vor v1.0 ein eigener Runner für den echten Lauf der CI-Integration, D-19),
GB/T-47127-PDF vor P7, YY/T-2029-Text vor P8, ISO-TS vor P10, Docker Desktop bei Gelegenheit.

## Für STOPP G1 vorgemerkt

Stand 29.10.2026 (D-18): erledigt sind die Freigabe der Annahmen A-78 bis A-89 und die Bestätigung der Lesarten R16 und D-15 (core-js-pure); offen sind zh-Prüfung, Sichtprüfung, die Anfrage an die Entwickler des BIDS-Validators, die Kenntnisnahme der Grenzen sowie Merge und Veröffentlichung (nach den beiden Prüfungen).
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
  - von P6 nach D-17 Option C nur die Kernbegriffe. Sie stehen nicht im Paket von 27c3e90 (seit 2f2a5a5 nimmt
    `tools/zh_review_package.py` jedes eingebaute Regelpaket auf, auch `yyt2029.yaml`). Liste für die Prüfperson, aus
    den Sprachtabellen und der zh-Doku auf 0ffdd90; mit * die Texte, die der Bereich vault (Freeze) bzw. yyt2029 als
    Kernbegriff markiert hat (die Bau-Agenten von vault und consent endeten vor ihrem Bericht, die übrigen Fundstellen
    sind aus dem Code gesucht):
    - die fünf Nutzungsarten `terms.consent_use.*`: 训练 (training), 验证 (validation), 发表 (publication), 共享
      (sharing), 商业用途 (commercial);
    - Einwilligung und Widerruf: 知情同意 (u. a. `check.consent.covered` 用途在知情同意范围内, Titel von CORE-M14-01
      数据划分中的用途在知情同意范围内, `cli.help.vault.consent.about`*), 撤回 (`reason.consent.withdrawn`);
    - Zugriffsprotokoll und Hash-Kette: 访问日志, 哈希链 (`cli.help.vault.about`*, `check.access.log_intact`
      访问日志哈希链完整, `check.access.log_writable` 访问日志可写入, `errors.vault.log_missing`*,
      `errors.vault.log_damaged`*, `errors.vault.too_many_objects`*, `cli.vault.role_looks_identifying`*, der Abschnitt
      `vault` in `docs/zh/commands.md`*);
    - Platzhalter-Regelpaket: 占位规则包* (in `cli.check.none_evaluated`, `report.text.overall_none_evaluated`, in
      `docs/zh/rulepacks.md` und `commands.md`);
    - der Grenzsatz ohne 防篡改: `cli.vault.verify.limits` und `docs/zh/vault.md#limits` (防篡改 steht in
      `report/wording/forbidden.yaml`);
    - die V-06-Aussage* in `docs/zh/index.md`, `limitations.md` und `rulepacks.md`.
    Die vollständigen P6-Texte (u. a. die übrigen Meldungen von Vault und Einwilligung, `docs/zh/vault.md`, die neuen
    Schlüssel der Fix-Runde `report.consent.*` und `errors.vault.object_link`) bekommen eine eigene Runde vor dem
    Release von v0.2 (D-17).
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
- **Merge und Veröffentlichung** (je Schritt durch den Projektverantwortlichen; Release-Linie nach D-19: v0.1.0 aus dem
  P5-Stand c4f240a plus den Korrekturen aus zh- und Sichtprüfung auf einem Release-Zweig, nicht aus `dev`, das seit
  8391420 0.2.0.dev0 trägt; `tools/release_check.py` verlangt den Tag-Commit in `origin/main`, A-87): Merge nach `main` und Push;
  Version 0.1.0, Tag `v0.1.0` und `release.yml` (vorher die Platzhalter `<REPO_URL>` und `<PYPI_RELEASE>` in docs/en und
  docs/zh mit der freigegebenen Adresse füllen; `tools/release_check.py` sperrt das Release, solange sie stehen, und der
  Release-Entwurf entsteht nur, wenn `ci.yml` auf dem getaggten Commit besteht); PyPI über `publish-pypi.yml` (Trusted
  Publishing bei TestPyPI und PyPI eintragen, erst TestPyPI); Gitee-Spiegel (`mirror-gitee.yml`, Secret
  `GITEE_SSH_KEY`, Variable `GITEE_MIRROR`) und das Gitee-Release von Hand am gespiegelten Tag (R15).

## Für STOPP G2 vorgemerkt

Stand 03.11.2026 (nach P6, P9 und P11). STOPP G2 folgt nach Abschluss von v0.2 (A-37, KONZEPT 6); P7 und P8 warten auf
die Normtexte (G-A, G-B). Jeder Punkt braucht den Projektverantwortlichen.
- **Annahmen A-90 bis A-92 zur Freigabe** (ENTSCHEIDUNGEN „Annahmen aus der Umsetzung von P6“), darunter die Lesarten:
  - A-90: Zugriffsereignisse von `scan`, `manifest` und `verify` nur im Vault am Standardort, von `report` nur mit
    `--config`, keine Ereignisse bei Exit 2; das Ereignis erst nach allen Ausgaben; Leser halten die Sperre nur für die
    Größe des Protokolls (Lesart von „Dateisperre um Lesen und Anhängen“); die wahrscheinliche Ursache einer Abweichung
    nicht in results.json; `vault log --show` ohne `--last`; Projektwurzel von `report --config` wie bei `check`, mit der
    benannten Einengung für eine toml außerhalb des Datensatzes.
  - A-91: Sobald Einwilligungsdaten vorliegen, ist jede nicht gedeckte Nutzung ein Fehler, mit oder ohne `[consent]`;
    ohne benötigte Nutzung ist M14 not_applicable, auch mit `--strict`; der Preis der Tabellenregel im M14-Block (in
    kleinen oder gemischten Datensätzen fast immer nur Summen je Nutzung).
  - A-92: `title_zh` des Gerüsts aus der veröffentlichten Prüfung statt aus dem Beispiel; der Gesamtsatz mit core und
    `yyt2029` bleibt „besteht die Prüfungen der geladenen Regelpakete“ (Banner und Abschnitt grenzen ab).
- **Annahmen A-93 bis A-99 zur Freigabe** (ENTSCHEIDUNGEN „Annahmen aus der Umsetzung von P9“; vorgemerkt für die
  Freigabe nach P9), darunter die Lesarten:
  - A-93: Rollenregister beratend; CORE-NV04-01 beurteilt nur Ereignisse vor dem Vortag des Stichtags (UTC), damit
    zwei `check` bytegleich bleiben, Ereignisse ohne Rolle sind not_checkable; die Befehle warnen und schreiben ihr
    Ereignis trotzdem; eine ungültige `roles.yaml` ist nur für `check` Exit 2.
  - A-94: Pflichtobjekte `pia` und `access_log` als Lesart von PIPL Art. 56; der 29. Februar plus drei Jahre ist der
    1. März; die Erinnerung ohne „muss löschen“; die beiden PIA-Vorlagen als einzige Ausnahme des Worttests für
    Gesetzesartikel (D-19).
  - A-95: CORE-M14-02 je Proband mit gültiger Einwilligung, Probanden ohne gültige Einwilligung bleiben CORE-M14-01;
    **Abweichung vom Entwurf, braucht die Freigabe mit A-95:** der neue optionale Block `reconsent` in results.json und
    die Lesart der kleinen Zellen (ein zurückgehaltenes Risiko zeigt nur `subjects`, Anhang 6.1 ohne Zahl für ein
    zurückgehaltenes CORE-M14-02); der Preis: Summen, Ampel und Überschrift zählen verletzte Ergebnisse, mit einem
    beurteilten Risiko ist die Zahl unter der Version ablesbar (wie bei M14-01 hingenommen).
  - A-96: fünf Pflichtteile, Ereignis vor dem Packen, Kopie des Manifests mit pseudonymen Namen in Rohordnern,
    `roles.yaml` und die PIA-Dateien so im ZIP, wie sie geschrieben sind („Rollen ohne personenbezogene Daten
    beschreiben“), kein Hash von `consents.yaml` im Ereignis.
  - A-97: Kategorie „entfallen“ neben „behoben“, der Schweregrad als Änderung, Rundung auf 6 signifikante Stellen,
    Regeln der Einwilligungsprüfungen nur gezählt (D-19).
  - A-98: Schutz der Action über `runner.environment` (Wert nicht verifiziert), GitLab nur über den Runner-Tag, kein
    Upload, fail-on errors als Standard.
  - A-99: Aufbau der Nachweismappe, immer zh und en, Zusammenführen mit pypdf, Metadaten und QA-Gate.
- **zh-Prüfung der P9-Texte** (D-19 wie D-17 Option C): jetzt die Kernbegriffe, die vollständigen Texte in einer Runde
  vor dem Release von v1.0. Kernbegriffe aus den Berichten der Bereiche: 角色登记册 (Rollenregister), 保存期限 und
  最低保存期限 (Aufbewahrungsfrist, Mindestaufbewahrung), 个人信息保护影响评估 (Folgenabschätzung), 风险登记册
  (Risikoregister), 重新取得知情同意 (Neueinwilligung), 检查包 (Export-ZIP), 版本比较 (Versionsvergleich), 证明材料汇编
  (Nachweismappe); die Sätze von A-30 请在自行开展法律审查后，决定继续保存或删除。 (Erinnerung der Aufbewahrung) und
  根据风险登记册，可能需要重新取得知情同意——由伦理委员会决定。 (Neueinwilligung); der Kopf der PIA-Vorlage und die
  Markierung 【待填写】; als neue Begriffe vorgeschlagen 自托管运行器 (eigener Runner), GitHub 托管的运行器
  (GitHub-gehosteter Runner), 制品 (Artefakt), 基线 (Baseline). Fundstellen: `cli.vault.role_not_permitted`,
  `cli.vault.role_reason.*`, `cli.vault.roles_invalid`, `cli.vault.init.templates_hint`, die Hinweise
  `notice.roles_without_ethics_ref`, `notice.registers_look_identifying`, `notice.retention_reminder`,
  `notice.risks_future`, `reason.roles.*`, `reason.retention.*`, `reason.pia.*`, `reason.reconsent.*`, die Titel der fünf
  Prüfungen und `title_zh` der fünf neuen Regeln in `core.yaml`, `report.roles.*`, `report.retention.*`, `report.pia.*`,
  `report.reconsent.*`, `report.dossier.*`, `terms.access_action.*`, `terms.retention_object.*`,
  `terms.diff_category.*`, `cli.check.reconsent`, `cli.vault.export.*`, `cli.diff.*`, `errors.export.*`,
  `errors.diff.*`, `cli.help.vault.export.*`, `cli.help.diff.*`, `cli.help.report.format`, die Texte der Action und der
  GitLab-Vorlage, `pia.zh.md` und die zh-Doku (`vault.md`, `metrics.md`, `commands.md`, `report.md`,
  `reference/outputs.md`, `data-model.md`, `privacy.md`, `limitations.md`, `index.md`, `ci.md`).
- **Eigener Runner vor v1.0** (D-19): ein vorübergehend registrierter Runner mit dem Label `neurogrid`, nur per Dispatch
  und nie für Pull Requests, für den echten Lauf von `ci-integration.yml` (Job `self-hosted`); bis dahin bleibt V-03
  `teilweise`.
- **Juristische Prüfung der PIA-Vorlage** durch eine in der VR China zugelassene Rechtsberatung vor der ersten echten
  Verwendung (D-19; kein Release-Gate).
- **Sichtprüfung einer Nachweismappe** (`dossier.pdf`); bis dahin bleibt REP-08 `nicht verifiziert` (Muster D-18).
- **Echter Lauf der GitLab-Vorlage:** nicht verifiziert sind die GitLab-Variable in `tags`, ein leerer Tag und die
  Kodierung unter PowerShell auf GitLab.
- **zh-Runde der vollständigen P6-Texte** vor dem Release von v0.2 (D-17 Option C).
- **Release v0.2.0**, falls gewünscht, aus dem Endstand von P6 auf einem Release-Zweig (D-19).
- **Bekannte Grenzen zur Kenntnis:** Kürzen am Ende und Neuschreiben des Zugriffsprotokolls nur mit
  `vault verify --expect-head`; nur Zugriffe über NeuroGrid; Zeiten aus der lokalen Uhr; Sperre beratend; die Gültigkeit
  einer Einwilligung beurteilt NeuroGrid nicht; das Ziel „10⁶ Einträge in < 30 s“ für `vault verify` ist nicht gemessen.
  Aus P9: Rollen bleiben beratend, und mit einem Stichtag mehr als einen Tag in der Zukunft kann das eigene Ereignis
  eines Laufs in CORE-NV04-01 des nächsten Laufs eingehen; `vault export` prüft das Protokoll nach dem Streamen über
  den Namen (ein fremdes Programm, das es dazwischen ersetzt, bleibt unbemerkt) und hält die Berichte bis zu 5 × 256 MB
  im Speicher; Risiko-IDs erscheinen im Bericht wie geschrieben; Differenzen zweier veröffentlichter, sich
  überschneidender Risiken können Zahlen von 1 bis 4 ergeben (A-81 gilt je Tabelle); das Export-ZIP ist nur in einer
  Umgebung bytegleich (zlib); die Leistung mit etwa 1 000 Risiken ist nicht gemessen.
- **Annahmen A-100 bis A-110 zur Freigabe** (ENTSCHEIDUNGEN „Annahmen aus der Umsetzung von P11“; vorgemerkt für die
  Freigabe nach P11), darunter die Lesarten:
  - A-100: torchaudio als direkte Abhängigkeit aus dem CPU-Index von PyTorch (das Linux-Wheel von PyPI linkt CUDA);
    ein Lauf startet aus dem Checkout, in dem die Daten liegen.
  - A-101 und A-102: NeuroGrid über die CLI auf temporären FIF-Dateien, die toml setzt nur `min_channels` und die
    Netzfrequenz; die Stufe aus dem größten Verhältnis zu den wirksamen Schwellen von M06, M07, M08 und M09, die Stufe
    einer Sitzung ist die schlechteste ihrer Läufe.
  - A-103: Stufenwerte vor dem ersten Lauf festgelegt; die Artefaktformen stammen von Bereich B und sind nicht an
    NeuroGrid angepasst.
  - A-104: Kreuzvalidierung innerhalb jeder Sitzung, Zufallsniveau als Anteil der häufigsten Klasse, gepaartes Design.
  - A-105: die SSVEP-Filterbank mit CSP ist eine eigene Konstruktion (MOABB hat keine); **Abweichung vom
    Referenzbeispiel von EEGNet:** Eingabe ×1e6 statt ×1000, dazu 20 % Validierung und Geduld 50 als Wahl des Leads.
  - A-106: Gleichheit zweier Läufe nur je Maschine und Lock.
  - A-107: die zh-Abgrenzung ist ein Entwurf für die zh-Prüfrunde.
  - A-108: Ausnahmen des Forschungs-Gates (pycountry, libsndfile, libquadmath, pybv, debugpy, Intel OpenMP),
    versionsgebunden.
  - A-109: Pilotbefund Q4 oder schlechter bei Zhou2016 (88 %) und Cho2017 (87 %) der sauberen Aufnahmen, nach D-20 als
    Befund berichtet.
  - A-110: `research.yml` nur auf Ubuntu 24.04, ohne Datensatz-Download.
- **zh-Prüfung des NeuroArena-Berichts** (F9 B, D-20; die Prüfung ist kein Gate für P11):
  `research/neuroarena/report/zh/report.md` und die zh-Texte in `research/neuroarena/src/neuroarena/report.py`, beide
  im zh-Prüfpaket (`tools/zh_review_package.py`). Unsichere Begriffe aus Bereich D: 劣化 und 劣化阶梯
  (Verschlechterung, Leiter), 会话 (Sitzung), 运行 (Lauf), 组合 (Paar aus Sitzung und Bedingung), 随机水平
  (Zufallsniveau), 自助法区间 (Bootstrap-Intervall), 平直通道 (flacher Kanal), 电极跳变 (Elektrodensprung), 肌电爆发
  (Muskelartefakt), 早停 (Early Stopping), 耐心值 (Geduld), 比值最大 (größtes Verhältnis), 适用范围声明
  (Abgrenzung) und der Satz der Abgrenzung; Artikelverweise der Form „第…条“ kommen nicht vor.

## Verlauf

### 2026-11-02 – P9 v1.0 normunabhängig: Register, Neueinwilligung, Export und Nachweismappe, diff und CI-Integration (NV-F04, NV-F05, NV-F06, NV-F07, NG-F15, NG-F16, CLI-07, CLI-08, CON-02, UF-02, UF-03, UF-06, REP-08, V-03)
- **Abgeschlossen:** NV-F04, NV-F05 (Software; PIA-Vorlage = Platzhalter nach A-30, juristische Prüfung vor erster
  echter Verwendung, D-19), NV-F06, NV-F07, NG-F15, CLI-07, CLI-08, CON-02, UF-02, UF-03, UF-06 (lokal mit den
  betroffenen Tests belegt, A-87; volle Suite in der CI auf 5596a8d grün: `ci` 41447040471, `offline` 41447040492,
  `ci-integration` 41447040527).
- **Nicht verifiziert:** REP-08 (Nachweismappe gebaut und getestet, `tests/integration/test_dossier.py::test_dossier_complete`;
  offen bis zur Sichtprüfung eines Dossier-PDFs durch den Projektverantwortlichen, Muster D-18).
- **Teilweise:** NG-F16 (NV-F01, NV-F02, NV-F04 bis NV-F07 erfüllt; NV-F03 bleibt `teilweise` bis zu den Details aus dem
  Normtext, P8), V-03 (NeuroVault, `diff` und Nachweismappe gebaut; die CI-Integration gilt erst nach dem echten Lauf
  auf eigenem Runner, D-19; die Abbildung ISO/IEC TS 27571 bleibt blockiert, P10).
- **Beigetragen zu:** ARC-01 (fünf Stufen mit jedem Zulieferer von P9, `tests/integration/test_p9_cross.py::test_five_stages_v1`),
  NG-F13 (Abschnitt Neueinwilligung des Berichts), DM-09 (Aktionen des Rollenregisters), NG-N03 (zwei `check` mit
  vollem Vault bytegleich), NG-N05 (eingepflanzte Kennungen in jeder Ausgabe von P9), NG-N06 (neue Schlüssel in zh, en
  und de).
- **Gebaut** (vier Bereiche nach den verbindlichen Vorgaben des Leads vom 02.11.2026, ENTSCHEIDUNGEN A-93 bis A-99):
  - Register (A-93, A-94): `model/_registers.py` (strenger Leser der drei Register), `model/roles.py`,
    `model/retention.py`, `model/risks.py`; `vault/roles.py` (Erlaubnisregel, Warnungen), `vault/retention.py`,
    `vault/pia.py`, `vault/risks.py` (Leser), `vault/templates/pia.zh.md` und `pia.en.md`; `vault init` legt die
    Register und die PIA-Dateien an; CORE-NV04-01 (`checks/access.py`) und CORE-NV05-01 bis -03
    (`checks/retention.py`); Warnungen von check, convert, report `--config`, vault log und vault consent add; core 1.0.0;
    Schemas `roles`, `retention`, `risks`.
  - Neueinwilligung (A-95): `vault.risks.judged`/`future`, CORE-M14-02 (`checks/consent.py`), der Block `reconsent` in
    results.json, der Abschnitt Neueinwilligung am Ende von Abschnitt 3 des Berichts mit der Tabellenregel, die
    Konsolenzeile `cli.check.reconsent`.
  - Paket (A-96, A-99): `vault/export.py`, `model/export.py` (ExportIndex) mit Schema, `report/identify.py`,
    `dossier.py` mit `report/templates/dossier.html.j2`, `kernel/pdf.py` (`PdfExpect.every_page_any`, `merge_pdfs`,
    `page_count`); Befehle `vault export` und `report --format dossier`.
  - Vergleich (A-97, A-98): `diff.py`, `model/diff.py` (DiffResult) mit Schema, Befehl `diff`; `action.yml`,
    `ci-templates/gitlab-ci.yml`, `.github/workflows/ci-integration.yml`, Nutzerseite `ci.md`.
- **Vorgehen:** Start mit 8e9575f (`1.0.0.dev0`, 02.11. 10:55) auf `p9-registers`, Schnittstellen-Freeze 159539d
  (11:46); Neueinwilligung und Paket ab dem Freeze, Vergleich ab 0ffdd90. Merges c00475b (Register), cd08106
  (Vergleich), 74db563 (Paket), cc7bc9c (Neueinwilligung); vom Lead dazwischen 851031c (`.env.example` deckt Action und
  Vorlage ab) und 9597441 (Rollenwarnung von `vault export`); Querschnittstests 5596a8d (13:39). Die Worktrees von P6
  und der vier Bereiche von P9 (`p6-*`, `p9-*`) wurden nach einer Prüfung auf Reparse-Punkte (keine gefunden) entfernt,
  ihre Zweige mit `git branch -d` gelöscht.
- **Entscheidungen des Leads beim Merge** (in ENTSCHEIDUNGEN „Übergreifend“, A-95, A-96 und A-98):
  1. Konflikte als Vereinigung (Sprachtabellen, Doku, `tools/gen_schemas.py`, Regel-Setups), erzeugte Dateien neu
     erzeugt (`gen_docs.py --check`, `gen_schemas.py --check` sauber).
  2. Ein Abschnitt `#risks` in `vault.md`: der Text des Bereichs Neueinwilligung mit dem markierten Beispiel
     `risks-yaml` des Bereichs Register (gleich dem Beispiel der Vorlage, in beiden Sprachen); die Grenze „1,000 risks
     and 1,000,000 bytes“.
  3. `vault export` warnt über das Rollenregister wie die anderen Befehle (9597441,
     `tests/cli/test_cli_export.py::test_export_warns_when_the_register_does_not_permit_it`); `roles_invalid` kommt
     dort nicht vor, eine ungültige `roles.yaml` lehnt den Export schon mit Exit 2 ab.
  4. Die Warnung „PIA unbearbeitet“ des Exports bleibt eine örtliche Prüfung der gepackten Bytes nach der Regel von
     CORE-NV05-02.
  5. Datenschutz: `roles.yaml` und die PIA-Dateien sind Pflichtteile und werden so gepackt, wie sie geschrieben sind;
     die Nutzerdoku sagt „Rollen ohne personenbezogene Daten beschreiben“.
  6. Veraltete Sätze in `docs/{en,zh}/limitations.md` und `index.md` aktualisiert; Nennungen der Norm in `KNOWN` von
     `test_norm_independence` geprüft.
  7. `.env.example` mit den zwölf Job-Variablen der GitLab-Vorlage; `test_env_example` liest `action.yml` und
     `ci-templates/*.yml` (851031c); schließt die Lücke des Bereichs Vergleich.
  8. Abweichung des Bereichs Neueinwilligung vom Entwurf (Block `reconsent`, kleine Zellen): braucht die Freigabe mit
     A-95 bei G2.
  9. „Wert von `runner.environment` nicht verifiziert“ bleibt in den Lücken (der echte Lauf belegt den Schutz, nicht den
     Wert); der eigene Runner ist vor v1.0 offen.
- **Integration:** Querschnittstests 5596a8d, `tests/integration/test_p9_cross.py` (neun Tests):
  `test_uf02_scan_convert_check_diff`, `test_uf06_init_consent_add_log_verify_export`,
  `test_uf03_build_check_consent_export`, `test_dod_two_checks_full_vault_byte_identical[1]` und `[4]`,
  `test_privacy_planted_identifiers_in_p9_outputs`, `test_consent_namespace_agrees_in_report_and_diff`,
  `test_dossier_as_export_report_part` (Marker `pdf`), `test_five_stages_v1`. Festgestellt: `vault log` und `manifest`
  schreiben im Vault am Standardort Ereignisse `read`; `bids_ai_ok` hat keine `neurogrid.toml` (die Tests schreiben
  `documented.toml` wie in P6); `report` hat keine Option `--role`.
- **Ergebnisse (lokal, Windows 11; nur betroffene Tests, A-87; die Bereiche mit `NEUROGRID_REQUIRE_PDF=1` und
  `PYTHONWARNDEFAULTENCODING=1`, Vergleich ohne Angabe):**
  - Register: unit, rules, acceptance und packaging_texts 3240 bestanden, 23 übersprungen, 1 fehlgeschlagen
    (Markierung der zh-Vorlage, behoben mit `\u`-Escape); Integration von Vault, Einwilligung, check und Bericht
    (9 Dateien) 300 bestanden, 3 übersprungen, 3 fehlgeschlagen (behoben: Datei der not_checkable-Befunde von
    CORE-NV04-01 ohne Register; geänderte Erwartung in `test_report_p5`, vier Regeln mehr in der Phase access;
    geänderter Aufbau in `test_consent_pipeline` mit gefüllter `retention.yaml` und einer PIA-Datei); übrige Integration
    450 bestanden, 1 übersprungen; cli, docs und workflows 462 bestanden, 3 übersprungen; Wiederholungen grün (298/3,
    415/4, 24, 151/2).
  - Neueinwilligung (66 Dateien, die geänderte Dateien lesen): acceptance 64 bestanden, 2 übersprungen; cli, docs,
    packaging und rules 761/3; integration 690/3; unit 1469/6; 0 Fehler.
  - Paket: pdf_unit und architecture 89; report_pdf mit cli 65; dossier 6; identify, Wortwahl, Tabellen, Norm,
    Architektur, Texte, Hilfe, cli, zh-Paket und Berichte 327; Export im Vault 15/1; export_pipeline 7; cli_export 6/1
    (kein pwsh lokal); Doku 142; docs_browser, licensing und notices 103/3; Vault, Einwilligung, Querschnitt P6,
    Register und packaging 565/13; coverage_gates 5.
  - Vergleich: tests/cli und tests/unit 2860 bestanden, 22 übersprungen; `test_ci_integration.py` 51; workflows,
    env_example und bundle_lock 56; Doku, Wortwahl, Lizenzen, Notices, Vault, zh-Paket, Sprache, Norm, Texte und
    Datenmodell 356/3; `test_docs_build.py` 53 (MkDocs strikt mit `ci.md`); `test_docs_browser.py` 4.
  - Nach allen vier Merges (Lead): Integration 243 bestanden, 1 übersprungen; unit, docs, cli und rules 1315 bestanden,
    8 übersprungen; Querschnittstests 9 bestanden; `ruff check`, `ruff format --check`, `mypy src/neurogrid tools`,
    `mypy --strict` für den Kern, `gen_schemas.py --check` und `gen_docs.py --check` sauber. Volle Suite: nur in der CI.
- **CI:**
  - 851031c: `ci-integration` 41442891483 lehnte auf den GitHub-gehosteten Runnern ubuntu-24.04 und windows-latest ab
    und lief mit allow-hosted-runner auf beiden (check, report, diff); der Job auf eigenem Runner wurde übersprungen.
  - 5596a8d (02.11.2026): alle drei Läufe abgeschlossen mit Ergebnis success. `ci` 41447040471; `offline` 41447040492
    (beide Bündel, Reinräume ubuntu 22.04/24.04 und debian:12-slim, Windows unter powershell und pwsh, glibc 2.27 mit
    Exit 2 abgelehnt, strace-Lauf, PDF in debian:12-slim); `ci-integration` 41447040527 (abgelehnt auf ubuntu-24.04 und
    windows-latest; check, report und diff mit allow-hosted-runner auf beiden, der Schritt mit fail-on errors scheiterte
    wie vorgesehen; Job auf eigenem Runner übersprungen). Testjobs laut Notice-Annotationen: windows-latest Python 3.11 4821 bestanden / 20 übersprungen, 3.12 und 3.13 je 4822 / 19 (von 4841); ubuntu-24.04 Python 3.11, 3.12 und 3.13 je 4721 / 125 (von 4846); 0 Fehler; Abdeckung Kern 94,3–94,4 %, Prüfer 97,0–97,1 % (Grenzen 90 % und 80 %)
- **Annahmen:** A-93 (Rollenregister), A-94 (Aufbewahrung und Folgenabschätzung), A-95 (Risikoregister und
  Neueinwilligung), A-96 (Export-ZIP), A-97 (Versionsvergleich), A-98 (CI-Integration), A-99 (Nachweismappe);
  vorgemerkt für die Freigabe nach P9 (STOPP G2). Angewandt: D-19; keine neue Entscheidung.
- **Nicht verifiziert:**
  - REP-08: Sichtprüfung einer Nachweismappe; für `table.reconsent` gibt es kein CSS, ein gedrucktes PDF mit vielen
    Risiken hat niemand angesehen.
  - CI-Integration: der Wert von `runner.environment` in einem zusammengesetzten Schritt, der Lauf auf eigenem Runner
    (vor v1.0, D-19), die GitLab-Vorlage auf GitLab (Variable in `tags`, leerer Tag, Kodierung unter PowerShell).
  - Die Laufzeit mit etwa 1 000 Risiken; PowerShell 7 für `diff` nur in der CI; lokal übersprungen sind u. a. die Tests
    mit Datei-Links (auf diesem Rechner nicht erlaubt) und mit pwsh.
  - zh-Texte von P9: die Kernbegriffe jetzt, die vollständigen Texte vor dem Release von v1.0 (Liste unter „Für STOPP
    G2 vorgemerkt“).
- **Für STOPP G2 vorgemerkt:** übernommen in die Liste „Für STOPP G2 vorgemerkt“ oben.

### 2026-11-02 – P6 v0.2 normunabhängig: NeuroVault, Einwilligung M14, Gerüst yyt2029 (NG-F11, NV-F01, NV-F02, NV-F03, M14, DM-08, DM-09, CLI-09, RP-10, ARC-01)
- **Abgeschlossen:** NG-F11, NV-F01, NV-F02, M14, DM-08, DM-09, CLI-09, RP-10, ARC-01 (lokal mit den betroffenen Tests
  belegt, A-87; volle Suite in der CI auf 0ffdd90: ganz grün (`ci` 41422859481, `offline` 41422859830)).
- **Teilweise:** NV-F03 (Hash-Kette, `vault verify`, `--expect-head` und die Grenzen mit Tests; offen sind die Details
  aus dem Normtext, P8).
- **Beigetragen zu:** NG-F16, CLI-08, UF-03, UF-06 (Export und Prüfpaket in P9), V-02 (bleibt teilweise blockiert);
  dazu CLI-03 (`check --role`), CLI-05 (`report --config`), NG-F10 (Manifest ohne die Protokolle des Vaults), POS-01,
  V-06, NG-N03, NG-N05, NG-N06, NG-N08, TECH-01, TECH-06. RP-08 bleibt blockiert (nur die Vorlage).
- **Gebaut** (drei Bereiche nach den verbindlichen Vorgaben des Leads vom 29.10.2026, ENTSCHEIDUNGEN A-90 bis A-92):
  - NeuroVault (A-90): `src/neurogrid/vault/` mit `store.py` (Ort und Zustände, `vault init`, Ersetzen in einem
    Schritt), `lock.py` (beratende Sperre `access.jsonl.lock`, höchstens 10 s), `ledger.py` (Hash-Kette, Anhängen,
    Prüfung mit `--expect-head`, Probe der Beschreibbarkeit), `roles.py`, `_os.py` (aller Plattformcode mit
    Markierungen); `model/access.py` (AccessEvent, DM-09) mit Schema; Befehle `vault init`, `vault log` (auch
    `--show`), `vault verify`, `check --role`, `report --config`; automatische Ereignisse von check, convert, report,
    scan, manifest und verify; CORE-NV03-01/02 (`checks/access.py`, core 0.2.0); Zeile des Zugriffsprotokolls auf dem
    Deckblatt und der Satz zu den Zugriffsrechten im Anhang jedes Berichts; Gate der Abdeckung mit Plattformblöcken;
    Nutzerdoku `vault.md` (zh/en) mit Testvektor und Nachprüfskript.
  - Einwilligung M14 (A-91): `model/consent.py` (ConsentScope, DM-08) mit Schema, `vault/consents.py` (Lesen für
    `check`, Import `consents.tsv`, `vault consent add` mit Ereignis vor dem Schreiben), `[consent]` in der
    Konfiguration, CORE-M14-01 (`checks/consent.py`) je Proband und Nutzung; im Bericht ein zusammengefasster Block nach
    D-17 Option B mit der Tabellenregel; `results.json` mit `config.consents_sha256` und `consent.subjects`.
  - Gerüst yyt2029 (A-92): Platzhalter-Paket `yyt2029` (0.2.0-draft, eine Regel ohne Klausel), Konsole und Bericht
    nennen kein Platzhalter-Paket als bestanden; Vorlage der Auslegungsfragen (leer, geprüft, erzeugter Block);
    Norm-Unabhängigkeitstest ohne Versionsschranke mit genau geprüften Zeilen; V-06-Satz der aktuellen Version.
- **Vorgehen:** Start auf `dev` mit 8391420 (0.2.0.dev0, 29.10.); Bereich vault mit dem Schnittstellen-Freeze f023146,
  consent darauf aufbauend, yyt2029 parallel (3bd764f, e84b8ef, 85f382d). Die Bau-Agenten von vault und consent endeten
  am Sitzungslimit vor ihrem Bericht; ihr Stand ist als `wip:`-Commit festgehalten (57fb4a0, 0c81561, 02.11.), dazu
  ed81152 (Zeilenlänge eines CLI-Tests). yyt2029 wurde unabhängig nachgeprüft (19 Prüfpunkte erfüllt, 7 neue Probleme),
  die Befunde behoben in 9a9433e (Prüfung der Fragentexte, Paket und Version auf getrennten Zeilen des Deckblatts,
  `[check] rulepacks` nennt den Schalter). Merges 9272cd9 (consent), 3646997 (vault), c516598 (yyt2029).
- **Integration:** Querschnittstests 40d6d16 (`tests/integration/test_p6_cross.py`: UF-06, UF-03, Bytegleichheit der
  DoD mit Vault, Einwilligungen und `yyt2029` bei `--jobs 1` und `4`, verlinkter Vault und verlinkte `consents.yaml`,
  Vault ohne Protokoll, die fünf Stufen mit Zulieferern); die Startseite nennt NeuroVault teilweise verfügbar.
  Semantische Merge-Korrekturen d50158b: `report.access` in zh und de unter `report`, Berichtstests mit M14 und NV03
  zugleich, die Seitenzahl mit `vault.md`.
- **CI-Korrekturen (2f2a5a5)** nach der CI auf d50158b, die nur an fünf Tests außerhalb der Bereiche scheiterte:
  `test_norm_independence.py::test_yyt2029_mentions_are_known` (zwei ungeprüfte Zeilen des Querschnittstests, jetzt
  in `KNOWN`), `test_thresholds_overridable.py::test_builtin_parameter_override_takes_effect[yyt2029-YYT2029-ACQ-001-min_hz:number]`
  (lädt das Platzhalter-Paket jetzt mit dem Schalter), `test_report.py::test_placeholder_findings_are_listed_without_verdict`
  und `::test_each_finding_row_has_required_fields` (Befundzeilen neben dem M14-Block) und
  `test_zh_review_package.py::test_every_file_with_chinese_text_is_in_the_package` (`yyt2029.yaml` fehlte im Paket).
- **Review:** unabhängiges Review nur mit Lesezugriff auf vault und consent auf d50158b, sieben Befunde, alle behoben
  auf `p6-fix` (Merge 0ffdd90), je mit Regressionstest, der vorher scheitert und danach besteht:
  1. M14 kleine Zellen (Datenschutz, hoch): Der Bericht druckte die genaue kleine Zelle dreimal (754aef6).
  2. Ausnahmen einer nicht geladenen M14-Regel zeigten Proband und Begründung (Datenschutz, mittel; 09cd05a).
  3. `vault log --objects` speicherte Rohdateien mit Glob-Zeichen, nachgestelltem Punkt oder als Link im Klartext
     (Datenschutz, mittel; eabdef6, neu `errors.vault.object_link`).
  4. Das Manifest nannte bei abweichendem `[vault] path` das Protokoll am Standardort, jedes `verify` nach einem
     read-Ereignis scheiterte (Datenintegrität; 8b36697).
  5. Neue Vault-Ordner bekamen unter Windows eine eigene, geschützte DACL statt der ACLs des Elternordners (f307754).
  6. Ein leeres oder ein Tab in `[vault] purpose`/`approval_ref` beendete `check`, `convert` und `report --config` erst
     nach der Datenarbeit mit `errors.vault.text_invalid`; jetzt `config.invalid` beim Lesen der toml (16fd7c9).
  7. `report --config` mit einer toml in einem Unterordner des Datensatzes suchte einen anderen Vault als `check`
     (9e44134).
- **Ergebnisse (lokal, Windows 11, Python 3.12.15; nur betroffene Tests, A-87):**
  - Bereich yyt2029 auf 518964e (Baum gleich 85f382d): 508 bestanden in 35:43 min (mit `NEUROGRID_REQUIRE_PDF=1`); die
    unabhängige Nachprüfung: 815 bestanden, 3 übersprungen in 1:39:46 h; dazu ein Lauf der betroffenen Tests des Bereichs
    mit 110 bestanden (Zahl des Leads; Zeitpunkt und Protokoll nicht festgehalten).
  - Bereich vault (02.11., vor den Merges): 702 bestanden, 6 übersprungen in 288,36 s
    (`.local/logs/vault_tests_1.log`); im Freeze `test_verify_streams_100k_entries` in 190 s unter starker Last
    (Grenze 300 s).
  - Bereich consent (02.11., vor den Merges): 485 bestanden in 163,55 s (`.local/logs/consent_tests_1.log`).
  - Gemergter Stand, betroffene Tests: 1096 bestanden, 9 fehlgeschlagen, 6 übersprungen in 434,56 s (zwei Sprachtests,
    sechs Tests in `test_report_p5.py`, die Seitenzahl in `test_docs_build.py`; `.local/logs/p6_merged_1.log`), behoben
    in d50158b.
  - Querschnittstests: 7 bestanden, 1 übersprungen in 41,10 s (`.local/logs/p6_cross_1.log`).
  - Fix-Runde `p6-fix`: 1037 bestanden, 8 übersprungen (POSIX-Zweige; Datei-Links sind auf diesem Rechner nicht
    erlaubt); nach dem Merge 0ffdd90 die Überschneidung der Zweige 168 bestanden, 1 übersprungen.
  - Durchlauf von Hand auf 0ffdd90 (NACHBAU 4.8): `vault init`, sechs `vault consent add`, `vault log`, zwei `check`
    bytegleich mit 9 Ereignissen danach, `vault verify` Exit 0; nach einer geänderten Zeile Exit 1 und CORE-NV03-01
    verletzt.
- **CI:**
  - d50158b (Push 02.11. 07:47): `ci` 41402168683 rot nur an den fünf Tests oben, auf allen Plattformen; laut den
    Annotationen der beim Mitschreiben abgeschlossenen Testjobs windows-latest × 3.13 5 fehlgeschlagen, 4319 bestanden,
    19 übersprungen (4343 Tests), ubuntu-24.04 × 3.12 und × 3.13 je 5 fehlgeschlagen, 4243 bestanden, 100 übersprungen
    (4348 Tests); Lizenz-Gate, beide PowerShell-Jobs und Anforderungs-IDs grün (`.local/ci_d50158b.txt`). `offline`
    41402168572 grün mit allen neun Jobs. Die Linux-Jobs zeigten nur diese fünf Fehler, der POSIX-Code des Vaults lief
    dort grün (vor der Fix-Runde).
  - 0ffdd90 (Push 02.11. 10:42): ganz grün, `ci` 41422859481 und `offline` 41422859830 (neun Jobs); Testjobs laut Notice-Annotationen: windows-latest Python 3.11 4347 bestanden / 20 übersprungen, 3.12 und 3.13 je 4348 / 19 (von 4367); ubuntu-24.04 Python 3.11, 3.12 und 3.13 je 4271 / 101 (von 4372); 0 Fehler; Abdeckung Kern 93,9–94,0 %, Prüfer 97,1–97,2 % (Grenzen 90 % und 80 %)
- **Annahmen:** A-90 (NeuroVault v0.2), A-91 (Einwilligung M14), A-92 (Gerüst yyt2029, Auslegungsfragen); für STOPP G2
  vorgemerkt. Neu: D-19 (Antworten vom 02.11.2026).
- **Nicht verifiziert:**
  - Die POSIX-Zweige des Vaults nach der Fix-Runde (flock, Modi 0700/0600 mit fchmod, fsync des Ordners): nur in der CI
    (D-09), ganz grün (`ci` 41422859481, `offline` 41422859830).
  - Das Ziel der Vorgaben „`vault verify` mit 10⁶ Einträgen in < 30 s“ ist nicht gemessen.
  - Welche Tests die lokalen Läufe übersprangen, steht nur in den Protokollen; die Läufe von vault und consent sind
    nur als Zahlen erhalten (`.local/logs/vault_tests_1.log`, `consent_tests_1.log`).
  - zh-Texte von P6: Kernbegriffe bei der zh-Prüfung (Liste unter „Für STOPP G1 vorgemerkt“), die vollständigen Texte
    vor dem Release von v0.2.
- **Für STOPP G2 vorgemerkt:** übernommen in die Liste „Für STOPP G2 vorgemerkt“ oben.

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
  - Auf dem Endstand 27c3e90: `bundle.py sizes` (das Bündel baut und prüft die CI, `offline` 40680346176; die Größen stehen nur im Job-Protokoll); keine volle lokale Suite (die volle Suite belegt die grüne CI).
- **Korpustests auf dem Endstand** (einmal, nach dem Prüfvorgehen, A-87): `tests/corpus/test_corpus.py` 62 von 62 bestanden (12 im ersten Lauf, dessen 3-h-Grenze im Test `…converts_without_validator_errors[keep-headers-BrainVision]` ablief – allein 242 s, bestanden –, die übrigen 50 in 74 min; `.local/logs/corpus_27c3e90.log`, `.local/logs/corpus_27c3e90_rest.log`); `tests/acceptance/test_g1_corpus.py` (52 Tests, ruft die Abnahme selbst auf, ≈ 2 h): auf 27c3e90 48 bestanden, 4 gescheitert – `test_no_host_path_or_header_data_in_outputs[psg-ipa-1.0.0]` und die drei Tests über den ganzen Lauf, die daraus folgen. Ursache im Prüfwerkzeug, nicht im Produkt: pytests Ausgabeordner liegt unter `pytest-of-<Login>`, die Konsole druckt ihn geschwärzt (`pytest-of-<user>`, A-51), die Prüfung nahm diese Form nicht als den eigenen `--out`-Ordner heraus, und der Rohordner `PSG` traf `psg-ipa-1.0.0` im Ausgabepfad; behoben in 7426dee (`_path_forms` kennt die geschwärzte Form; Regressionstest `test_a_redacted_output_path_on_the_console_is_no_raw_name_leak`, vor dem Fix rot, danach grün). Wiederholung des Moduls auf 7426dee: 52 von 52 bestanden (1 h 57 min; `.local/logs/g1corpus_7426dee.log`).
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

P9 ist abgeschlossen (`dev` 5596a8d; CI auf 5596a8d grün: `ci` 41447040471, `offline` 41447040492, `ci-integration`
41447040527). Weil weder das GB/T-47127-PDF (G-A) noch der YY/T-2029-Text (G-B) noch ISO/IEC TS 27571 (G-C) vorliegt
(`.local/normen/` gibt es nicht), folgt nach D-13 und KONZEPT 5 als nächste normunabhängige Phase **P11 NeuroArena**
(`research/neuroarena` mit eigenem Lock; KONZEPT 6) vor P10; P7, P8 und P10 warten auf die Normtexte.
Parallel beim Projektverantwortlichen: zh-Prüfung (Kernbegriffe von P6 und P9) und Sichtprüfung (die Berichte für STOPP
G1, eine Nachweismappe für REP-08), die übrigen Punkte von „Für STOPP G2 vorgemerkt“ (A-90 bis A-99, eigener Runner vor
v1.0, juristische Prüfung der PIA-Vorlage vor der ersten echten Verwendung, echter Lauf der GitLab-Vorlage); danach die
Release-Zweige für v0.1.0 aus dem P5-Stand c4f240a und, falls gewünscht, für v0.2.0 aus dem P6-Endstand 0ffdd90,
jeweils nach den Prüfungen und mit Freigabe.
