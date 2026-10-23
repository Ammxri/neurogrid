# NeuroGrid – Umsetzungskonzept (Phase 2)

Grundlage:
- PRD 1 (10.10.2026)
- [ANFORDERUNGEN.md](ANFORDERUNGEN.md)
- Entscheidungen D-01–D-07, offene Fragen E1–E5 und Annahmen A-00–A-61 in [ENTSCHEIDUNGEN.md](ENTSCHEIDUNGEN.md)

Stand 11.10.2026, überarbeitet nach einer Prüfung aus drei Blickwinkeln (Abschnitt 10).

---

## 1. Architektur und Tech-Stack

### 1.1 Überblick

Der Aufbau folgt den fünf Stufen des Architekturbilds der PRD (ARC-01). Prüfer messen, nur der Regelmotor bewertet (ARC-02).

```
Datensatz (EDF/EDF+[C|D], BDF, BrainVision, EEGLAB, FIF; ab v0.2 GB/T 47127)
   │  io/            Adapter → Datenmodell (nur gelistete Felder, A-51)   ← neurogrid.toml, BIDS-Sidecars
   ▼
Prüfer  checks/      Messwerte je Objekt (Datensatz, Aufnahme, Kanal, Datei)
   │                 ← BIDS-Validator 3.0.2 (deno-Unterprozess, --deny-net)
   │                 ← NeuroVault (Einwilligung, Rollen, Zugriffsprotokoll)
   ▼
kernel/  Regelmotor  ein Befund je Regel × Objekt × Unterschlüssel, mit Klausel und Details   ← Regelpakete (YAML)
   ▼
kernel/  Ausgabe     results.json (kanonisch) · Bericht HTML/PDF zh/en · Exitcode 0/1/2
```

- **Ein Prozess:** Alles läuft lokal in einem Python-Prozess, dazu je ein Unterprozess für deno und die Headless Shell.
- **Kein Netzwerkcode:** NeuroGrid enthält keinen Netzwerkcode.
- **Schutz:** Ein Audit-Hook sperrt Verbindungen aus dem Python-Prozess. Die Unterprozesse sind eigens abgesichert (A-49).

### 1.2 Paketstruktur

Der Aufbau folgt §13 (TECH-01). Ergänzungen sind mit „+“ markiert.

```
neurogrid/
  pyproject.toml  uv.lock  LICENSE (Apache-2.0)  NOTICE  THIRD_PARTY_NOTICES.md  DATA_SOURCES.md (+)  REUSE.toml (+)
  .gitattributes (+, eol=lf; Fixtures binär)   .github/workflows/ ci.yml, offline.yml (+), corpus.yml (+), docs.yml (+), release.yml (+)
  src/neurogrid/
    cli.py                Typer-App (pretty_exceptions_show_locals=False)
    + config.py           neurogrid.toml → Pydantic (strict)
    + convert.py          BIDS-Konvertierung; ab v0.2 GB/T 47127
    + diff.py  + dossier.py   v1.0
    + safety.py           Pfadprüfung (A-52), Ausgabefilter (A-51), sicherer YAML-Lader (A-53), Arbeitsordner (A-54), Audit-Hook (A-49)
    kernel/               nur Standardbibliothek, Pydantic, Jinja2, PyYAML, fontTools, Playwright; mypy --strict;
                          importiert nichts aus neurogrid.* außerhalb von kernel (A-23)
      rules.py  engine.py  findings.py  provenance.py  canonical.py  i18n.py  report.py  glob.py (+, A-14)
    io/                   edf.py bdf.py brainvision.py eeglab.py fif.py gbt47127.py (v0.2)  + base.py  + discover.py
    model/                dataset.py consent.py results.py
    checks/               structure.py metadata.py signal.py annotation.py ai_dataset.py provenance.py consent.py
                          + registry.py  + access.py (v1.0)  + evidence.py (P4)
    rulepacks/            core.yaml (+) bids.yaml gxdsl008.yaml yyt2029.yaml gbt47127.yaml   + rulepack.schema.json
    vault/                ledger.py roles.py pia.py  + store.py + risks.py + retention.py + export.py
    report/               templates/  i18n/zh.yaml en.yaml de.yaml  + charts.py  + fonts/ (Noto Sans SC 400/700 + OFL.txt)
                          + wording/forbidden.yaml (Sperrliste, A-57)
    + schemas/            results, rulepack, config, evidence, manifest, scan, diff (*.schema.json, aus Pydantic erzeugt)
  tests/                  fixtures/synthetic/ (CC BY 4.0) fixtures/derived/ (mit DATA_SOURCES-Eintrag)  rules/  …
  tools/   (+)            check_matrix_coverage.py gen_fixtures.py gen_large_edf.py corpus.py calibrate.py build_fonts.py
                          bundle.py notices.py licenses.py coverage_gates.py install_pdf_browser.py
  docs/                   zh/ en/ (MkDocs; metrics.md je Metrik = Quelle der core-Regeln), umsetzung/ (nicht Teil der Website)
  research/neuroarena/ (+)  eigenes uv-Projekt mit eigenem Lock (A-36)
  action.yml, ci-templates/gitlab-ci.yml (+, v1.0, A-34)
```

### 1.3 Tech-Stack

| Baustein | Version | Zweck | Grundlage |
|---|---|---|---|
| Python | 3.11–3.13 (`>=3.11,<3.14`), Entwicklung 3.12 | Laufzeit | NG-N04, A-42 |
| uv | 0.13 | Lock, Umgebungen, Bündel | TECH-02 |
| Build-Backend | hatchling, Version aus `src/neurogrid/__init__.py` | Wheel/sdist | A-27 |
| Typer, Pydantic v2, Jinja2, PyYAML, tomllib | gepinnt | CLI, Modelle, Vorlagen, Formate | TECH-03, TECH-07 |
| MNE-Python | 1.13.2 | Einlesen, Filter, ICA | LIB-01 |
| MNE-BIDS + pybv | 0.20.0 | BIDS; FIF → BrainVision | LIB-02, A-05 |
| bids-validator-deno + deno | 3.0.2 + 2.9.7 | Strukturprüfung, mitgeliefert | LIB-03, A-06 |
| edfio | 0.4.18 | EDF-Kopf, EDF+D-Zeitstruktur | LIB-08, A-24 |
| pyprep | 0.9.0 | M06 | LIB-04 |
| autoreject | 0.5.1 | M09a | LIB-06 |
| mne-icalabel[onnx], onnxruntime, python-picard | 0.10.0 / 1.31.0 / 0.8.2 | M09b | LIB-07, A-19 |
| numpy, scipy, scikit-learn, threadpoolctl | exakt gepinnt (gemeinsame Linie für 3.11–3.13) | Rechnen, feste Threads | A-11, A-48 |
| pymatreader, h5py | gepinnt | EEGLAB .set inkl. v7.3 | NG-F01 |
| matplotlib | 3.11 | SVG-Verteilungsgrafiken | REP-04 |
| Playwright + Chrome Headless Shell 1243 | 1.63.0 | PDF; Shell laut E1 nicht im Bündel | TECH-07, A-26 |
| Noto Sans SC (statisch 400/700, OFL), fontTools, pypdf | – | Schrift, Subsetting, PDF-Prüfung und Datumsfelder | A-27 |
| pytest, pytest-cov, ruff (inkl. PTH, PLW1514), mypy, pip-licenses | gepinnt (dev) | Qualität | TECH-04, NG-N07, NG-N08 |
| MkDocs 1.6.1 + Material 9.7 + mkdocs-static-i18n | eingefroren (dev) | Doku zh/en | TECH-06, A-28 |
| **nicht verwendet** | eegprep (D-05), pyEDFlib (A-24), EEGDash (E4), torch im Paket (A-19), openneuro-py (GPL), Edge, variable Schriften, MNE-Infomax | | |

### 1.4 Ablauf `check`

1. **Start:** Audit-Hook setzen; Ausgabe auf UTF-8 stellen; Arbeitsordner anlegen (A-54).
2. **Konfiguration:** `neurogrid.toml` (Standard `.neurogrid/neurogrid.toml`) mit dem sicheren Lader lesen und strikt validieren. Bei Fehler Exit 2 mit Feldangabe. Stichtag `as_of` festlegen.
3. **Erfassen** (`discover`):
   - Datensatz scannen (BIDS oder Rohordner); jeder Pfad läuft durch die Pfadprüfung.
   - Begleitdateien gruppieren; Metadaten nach A-04 zusammenführen.
   - Bei Rohordnern pseudonyme Aufnahme-IDs vergeben.
   - Nicht unterstützte Datendateien ergeben M01-Befunde.
4. **Regelpakete laden:** `core` plus `--rulepack` (Name oder Pfad). Pakete mit `source_status` placeholder nur mit `--allow-draft-rulepacks`. Die Pakete werden gegen das Schema und die Prüf-Registry geprüft.
5. **Messen** – nur Prüfungen, die eine geladene Regel braucht:
   - ein Streaming-Durchlauf je Aufnahme (M01, M07, M08, Signal-Hash, Dauer)
   - Stichprobe (M06, M09)
   - datensatzweite Prüfungen (M03, M04, M11, M12, Validator, Manifest, Nachweise, Vault)
   - `--jobs` (E3) als Prozesspool; Ergebnisse in fester Reihenfolge
6. **Bewerten:** Regelmotor mit wirksamen Parametern samt Herkunft. Danach Ausnahmen, Nachweise und placeholder-Regeln anwenden; Ampel und Abdeckung bilden.
7. **Ausgeben:** `results.json` kanonisch schreiben (A-61, mit `disclaimer`), Kurzfassung auf der Konsole, Exitcode.
8. **Protokollieren:** Ist ein Vault vorhanden, Zugriffsereignis anhängen (mit Dateisperre). Es fließt nicht in results.json ein.

### 1.5 Laufzeitkonzept (NG-N02, D-04, A-50)

**Blockweise über die volle Länge.** Gelesen wird mit MNE `preload=False` in 60-s-Blöcken. Der Speicher liegt bei etwa 210 MB, unabhängig von der Dateigröße. Die Kennwerte rechnen festgeschriebene eigene Kernel, verteilt auf min(4, Kerne) Threads über Kanalgruppen:
- **M07:** rfft-Welch mit 2-s-Fenster, periodischem Hann-Fenster, ohne Überlappung. Je Block und Kanal wird P(f₀±1 Hz)/P(1–40 Hz) gebildet; der Kanalwert ist der Median über die Blöcke. Zusätzlich wird bei der anderen Netzfrequenz gemessen (A-47).
- **M08:** Flatline und Übersteuerung je 1-s-Fenster, je Format nach A-18.
- **Signal-Hash `NG-SIGHASH-v1`** (A-21).
- **Dauer und Lesbarkeit.**

**Stichprobe für M06/M09** (D-04, A-19, A-60):
- **Auswahl:** 10 × 60 s mittig in 10 gleichen Teilen; Aufnahmen bis 10 min ganz.
- **Vorverarbeitung:** Notch-Filter, Bandpass 1–100 Hz, 250 Hz, Montage, Durchschnittsreferenz.
- **M06:** pyprep mit RANSAC.
- **M09a:** lokales autoreject.
- **M09b:** picard (20 Komponenten, decim 4) plus ICLabel per ONNX.
- **Threads:** feste BLAS-Threads (threadpoolctl).
- **Ausweis:** Parameter, Startzeiten und Seed stehen in results.json und im Bericht.
- **Umschalten:** `[sampling] mode = "full"`. Die MNE-Standardwerte für die ICA sind ausgeschlossen (gemessen 115 s allein für die ICA).

**Gemessen (8.2).** 1-GB-EDF mit 64 Kanälen: 89 s mit 4 Kernen, höchstens 850 MB. Die Abnahme folgt A-50: < 150 s hier mit 4 Kernen; < 300 s auf einem Runner mit 4 vCPU/16 GB (sobald CI verfügbar); gemessen mit 64/128/256 Kanälen.

**Sonderfälle:**
- **EEGLAB** mit eingebetteten Daten: im Bericht als „nicht blockweise lesbar“ ausgewiesen.
- **EDF mit gemischten Raten:** Signalkennwerte nur auf EEG-Kanälen mit nativer Rate.
- **EDF+D:** Zeitbereiche in Aufnahmezeit über die Datensatz-Onsets von edfio.

### 1.6 Offline-Betrieb und Auslieferung (NG-N01, A-25, A-26, A-49)

**Validator** (A-06):
- Aufruf: `deno run --no-prompt --no-config --no-lock --no-remote --no-npm --cached-only --deny-net --allow-read=<datensatz> --allow-write=<ausgabe> --allow-env=<liste> <bundle> <datensatz> --format json -o <ausgabe> --max-rows -1`
- Umgebung bereinigt: `DENO_NO_UPDATE_CHECK=1`, eigenes `DENO_DIR` im Arbeitsordner, `NO_COLOR=1`, kein `BIDS_SCHEMA`.
- Validiert wird gegen das mitgelieferte Schema 1.2.7 (BIDS 1.11.1).

**PDF** (A-26):
- Playwright mit der Chrome Headless Shell aus einem NeuroGrid-eigenen Ordner.
- Netzwerk: Chromium-Flags fest im Code; `context.route` erlaubt nur die Berichtsdatei und `data:`; Anfragezähler im Lauf. CSP im HTML.
- Seitenlayout: Kopf-/Fußzeilen über CSS `@page`; der feste Satz steht in jeder Fußzeile.
- Datumsfelder: `CreationDate`/`ModDate` = Stichtag.
- **Kein Edge-Rückfall.** Fehlt die Shell oder fehlen Linux-Bibliotheken, endet der Lauf mit Exit 2 und Hinweis.
- Ob die Shell im Bündel liegt, hängt an **E1** (Empfehlung: nein; `tools/install_pdf_browser.py` lädt online oder spielt eine bereitgestellte zip mit geprüfter Prüfsumme ein).

**Schrift** (A-27): statische Noto-Sans-SC-Schnitte, eingecheckt; Subsetting zur Laufzeit; name-IDs 0/13/14 bleiben erhalten.

**QA-Gate je PDF:**
- nur eingebettete Type0/CIDFontType2-Subsets
- keine Systemschrift, kein Type3
- kein Radikal-Codepunkt im extrahierten Text
- Pflichtphrasen inkl. fester Satz auffindbar
- 0 abgebrochene Anfragen im Normalfall

**Offline-Bündel je Plattform** (`tools/bundle.py`):
- Inhalt: uv-Binary, python-build-standalone 3.12, cp312-Wheelhouse aus `uv.lock`, Dokumentation, Notices, `SHA256SUMS`, Installationsskripte (PowerShell 5.1 und Bash).
- Signatur nach E3.
- Verteilung über GitHub Releases.

**Nachweis „ohne Netz“** (A-49):
- Linux-Lauf aller Befehle in einem Container mit `--network none` bzw. `unshare -rn`, zusätzlich unter `strace -f -e trace=connect`.
- Windows per Firewall-Runner oder „nicht verifiziert“.

---

## 2. Datenmodell, Schnittstellen, Rollen und Rechte

### 2.1 Datenmodell (DM-01–DM-10, D-03)

Die zehn PRD-Objekte behalten ihren Inhalt; Namen und Felder sind englisch. Die Abbildungstabelle steht in der Doku.

| PRD (§10) | Englisch | Felder (PRD → Englisch) | Ergänzungen |
|---|---|---|---|
| Dataset | `Dataset` | id, name, version, quelle→source, lizenz→license, regelpakete→rulepacks, manifest_hash | is_bids |
| Subject | `Subject` | pseudo_id, alter_gruppe→age_group, geschlecht→sex, diagnose_code→diagnosis_code, consent_ref | – (Rohalter nur intern, nie serialisiert; diagnosis_code nie in Ausgaben) |
| Recording | `Recording` | id (pseudonym), subject, session, task, format, pfad→path (relativ, intern), abtastrate_hz→sampling_rate_hz, dauer_s→duration_s, geraet→device, elektrodentyp→electrode_type (wet/dry), referenz→reference, netzfrequenz_hz→line_frequency_hz | run, streamable, metadata_sources |
| Channel | `Channel` | name, typ→type, einheit→unit, position, impedanz_kohm→impedance_kohm, status (good/bad) | recording_id, resolution, physical_range |
| Annotation | `Annotation` | onset_s, dauer_s→duration_s, code, label, annotator_id, quelle→source | recording_id |
| Split | `Split` | name (train/val/test), recording_ids | – |
| ProcessingStep | `ProcessingStep` | schritt→step, werkzeug→tool, version, parameter→parameters, eingabe_hash→input_hash, ausgabe_hash→output_hash | – |
| ConsentScope | `ConsentScope` | subject, version, datum→date, erlaubte_nutzungen→permitted_uses{training, validation, publication, sharing, commercial}, widerruf→withdrawn, ethikvotum_ref→ethics_approval_ref | – |
| AccessEvent | `AccessEvent` | zeit→time (UTC), rolle→role, aktion→action, objekte→objects, zweck→purpose, genehmigung_ref→approval_ref, vorheriger_hash→previous_hash, hash | – (kein OS-Benutzer, kein Rechner) |
| Finding | `Finding` | regel_id→rule_id, klausel→clause, schweregrad→severity (error/warning/info), status, messwert→measured_value, schwelle→threshold, objekt→object, belege→**details** | rulepack, rulepack_version, source_status, phase, subkey, file, channel, time_ranges, message_key, params, key |

Hilfsmodelle (A-09): `Rule`, `Rulepack`, `CheckSpec`, `Measurement`, `MetricValue`, `Manifest`, `EvidenceItem`,
`ExceptionEntry`, `Role`, `Risk`, `RetentionItem`, `RunInfo`, `Environment`, `Results`, `ScanResult`, `DiffResult`.

### 2.2 Regelpakete (RP-01, D-03, A-41)

```yaml
rulepack: yyt2029
version: 0.2.0-draft
source: "YY/T 2029-2026"
source_status: placeholder          # placeholder | secondary | inventory | final
rules:
  - id: YYT2029-ACQ-001
    clause: "TBD"                   # clause number from the norm text once it has been read
    title_zh: "采样频率记录且一致"
    title_en: "Sampling rate documented and consistent"
    phase: acquisition              # acquisition|processing|annotation|storage|access
    check: signal.sampling_rate_consistency
    params: {min_hz: 500}           # placeholder until the norm text is read
    severity: error                 # error|warning|info
    verification: automatic         # automatic|semi_automatic|manual
```

- **Regel-IDs:** `PAKET-PHASE-NNN` (PHASE ∈ ACQ, PROC, ANN, STO, ACC); in `core` gilt die Ausnahme `CORE-Mxx-NN` (A-02).
- **Prüfungen:** `check` verweist auf die Prüf-Registry, die als generierte Doku-Seite veröffentlicht wird. Manuelle Regeln nutzen `evidence.document`.
- **Titel:** `title_de` ist nicht vorgesehen; de gibt es nur in der Kern-Sprachtabelle (A-07).

**Regeln des Pakets `core`.** Quelle ist die Metrik-Doku `docs/<lang>/metrics.md#Mxx`. Bei „Annahme“ nennt die PRD keine Schwelle bzw. keinen Schweregrad.

| ID | Prüfung | Phase | Schweregrad | Startschwelle | Herkunft |
|---|---|---|---|---|---|
| CORE-M01-01 | Datei lesbar | storage | error | – | PRD |
| CORE-M01-02 | Kopfzeile konsistent (Größe, Felder; EDF via edfio) | storage | error | – | PRD (M01), A-46 |
| CORE-M01-03 | Begleitdateien und Verweise vorhanden | storage | error | – | A-46 |
| CORE-M01-04 | Datendatei in unterstütztem Format | storage | error | – | A-12 |
| CORE-M01-05 | Kopfzeile enthält Personen-/Aufnahmekennung oder echtes Datum (ohne Wert) | storage | info | – | A-05 |
| CORE-M02-01 | Pflichtfeld vorhanden (je Feld; `n/a` nach A-03) | acquisition | error | – | PRD |
| CORE-M02-02 | Metadaten konsistent (TaskName, BIDSVersion, Name) | acquisition | warning | – | A-46 |
| CORE-M03-01 | Abtastrate ≥ Mindestwert | acquisition | warning | 500 Hz | PRD (T/GXDSL 008) |
| CORE-M03-02 | gemischte Raten nur dokumentiert | acquisition | warning | – | PRD |
| CORE-M03-03 | Sidecar-Rate = Daten | acquisition | warning | – | A-46 |
| CORE-M04-01 | Kanalnamen 10-20/10-10 oder abgebildet | acquisition | error | – | PRD |
| CORE-M04-02 | Positionen vorhanden | acquisition | warning | – | A-18 |
| CORE-M04-03 | gleicher Kanalsatz je Aufgabe | acquisition | warning | – | A-18 |
| CORE-M04-04 | Kanalzahl konsistent | acquisition | warning | – | A-46 |
| CORE-M04-05 | Name nur in 10-05 | acquisition | info | – | A-18 |
| CORE-M05-01 | Impedanz dokumentiert | acquisition | warning | – | PRD |
| CORE-M05-02 | Impedanz unter Schwelle (nass) | acquisition | warning | 5 kΩ | PRD (T/GXDSL 008) |
| CORE-M06-01 | Anteil schlechter Kanäle | acquisition | warning | kalibriert | PRD, A-44 |
| CORE-M07-01 | Netzbrumm-Verhältnis je Kanal | acquisition | warning | kalibriert | PRD, A-44 |
| CORE-M07-02 | dokumentierte Netzfrequenz plausibel | acquisition | info | – | A-47 |
| CORE-M08-01 | Flatline-Anteil je Kanal | acquisition | error | 5 % der Dauer | PRD |
| CORE-M08-02 | Übersteuerungs-Anteil je Kanal | acquisition | error | 5 % der Dauer | PRD |
| CORE-M09-01 | autoreject-Verwerfungsrate | acquisition | warning | kalibriert | PRD, A-44 |
| CORE-M09-02 | ICLabel-Anteil nicht Gehirn | acquisition | warning | kalibriert | PRD, A-44 |
| CORE-M10-01 | Cohens κ zwischen Annotatoren | annotation | warning | 0,6 | PRD |
| CORE-M10-02 | Codes einheitlich und im Vokabular | annotation | warning | – | A-17 |
| CORE-M10-03 | keine Lücken (kontinuierlich) | annotation | warning | – | A-17 |
| CORE-M10-04 | keine Überlappungen je Annotator | annotation | warning | – | A-17 |
| CORE-M11-01 | jede Klasse ≥ Mindestanteil | processing | warning | 5 % | PRD |
| CORE-M11-02 | Alter und Geschlecht vollständig | processing | warning | – | PRD |
| CORE-M12-01 | Proband in genau einem Split | processing | error | – | PRD |
| CORE-M12-02 | keine doppelten Aufnahmen (Signal-Hash) | processing | error | – | PRD |
| CORE-M13-01 | Manifest vorhanden | storage | error (`--strict`) / warning | – | PRD, A-22 |
| CORE-M13-02 | Dateien entsprechen dem Manifest | storage | error | – | NG-F10 |
| CORE-M13-03 | Verarbeitungsschritte und Softwareversionen dokumentiert | storage | warning | – | A-22 |
| CORE-M14-01 | Nutzung im Split durch Einwilligung gedeckt (v0.2) | access | error | – | PRD, A-30 |
| CORE-M14-02 | möglicherweise Neueinwilligung erforderlich (v1.0) | access | warning | – | NV-F06, A-30 |
| CORE-NV03-01 | Zugriffsprotokoll intakt (v0.2) | access | error | – | NV-F03 |
| CORE-NV04-01 | Zugriffe im Rollenregister erlaubt (v1.0) | access | warning | – | NV-F04 |
| CORE-NV05-01 | Aufbewahrungsobjekte vollständig, Frist ≥ 3 Jahre (v1.0) | access | warning | – | NV-F05, A-30 |
| CORE-NV05-02 | Folgenabschätzung bearbeitet (keine Rohvorlage) (v1.0) | access | warning | – | A-30 |
| CORE-NV05-03 | Mindestaufbewahrung endet in ≤ 90 Tagen (v1.0) | access | info | 90 Tage | NV-F05 |

**Paket `bids`:** `BIDS-STO-001` (Validator-Fehler, error), `BIDS-STO-002` (Validator-Warnungen, warning), `BIDS-STO-003` (HED-Schema offline nicht verfügbar, warning). Der Unterschlüssel ist der Validator-Code.

**Paket `gxdsl008`** (`source_status: secondary`, A-40):

| ID | Prüfung | Schweregrad | Nachweis |
|---|---|---|---|
| GXDSL008-ACQ-001 | Impedanz < 5 kΩ (nass) | warning | automatisch |
| GXDSL008-ACQ-002 | Abtastrate ≥ 500 Hz | warning | automatisch |
| GXDSL008-STO-001 | Speicherformat EDF oder HDF5 | warning | automatisch |
| GXDSL008-ACC-001 | AES-256 und rollenbasierter Zugriff | warning | manuell |
| GXDSL008-STO-002 | Prüfsummen für Dateien | warning | halbautomatisch (Manifest) |

### 2.3 `results.json` (NG-F14, A-09, A-11, A-61)

```
{ "schema_version", "disclaimer": {zh, en}, "tool": {name, version}, "environment": {python, platform, libraries, blas_threads},
  "dataset": {Dataset ohne Pfade}, "rulepacks": [{name, version, source, source_status, norm, sha256}],
  "rules": [{id, rulepack, clause, title_zh, title_en, phase, check, severity (wirksam), strict_severity,
             verification, source_status}],
  "config": {canonical_sha256, as_of, seed, strict, sampling, effective_params, effective_settings (bereinigt),
             evidence_sha256},
  "recordings": [{id (pseudonym), format, streamable, metrics (P4: metrics.annotation), sample}],
  "findings": [Finding …] (verletzte und Sonderstatus einzeln),
  "passed": [{rule_id, object, count} …] (bestandene gezählt je Regel × Objekt),
  "notices": [{level, message_key, params} …],
  "evidence": [EvidenceRecord {rule_id, rulepack, phase, severity, verification, status, outcome, document,
               document_check, sha256 (berechnet), sha256_recorded (eingetragen), reviewer, date, comment,
               justification} …],
  "exceptions": [ExceptionEntry … mit used],
  "duplicates": [[recording_id …] …] | null,
  "ai": {labels: {source, column, unit, scopes: {scope: {total, classes | null}}} | null,
         demographics: {subjects, age_documented, sex_documented, age_groups | null, sex | null} | null,
         splits: {source, recordings, subjects, unassigned} | null} | null,
         (ai null: keine der Prüfungen von CORE-M11-01, CORE-M11-02, CORE-M12-01 geladen;
          classes, age_groups, sex null: zurückgehalten, A-81)
  "summary": {phases: {phase: {light, errors, warnings, open_evidence}}, coverage: {pack: value|"n/a"},
              errors, warnings, open_evidence, exit_code},
  "manifest": {sha256, status, files, changed, new, missing, skipped_changed, unreadable} | null }
```

Die Felder aus P4 (`evidence`, `duplicates`, `ai`, `manifest`, `strict_severity`, `evidence_sha256`, `summary.open_evidence`) sind optional;
results.json früherer Stände bleibt lesbar (A-80 ff., Übergreifend).

Nicht enthalten: Uhrzeit, Rechner- oder Benutzername, absolute Pfade, Vault-Kopf-Hash, Signal-Hashes, Rohalter, diagnosis_code.

### 2.4 `neurogrid.toml` (NG-F18, MET-02)

```toml
[check]
rulepacks = ["core", "bids", "gxdsl008"]
strict = false
seed = 20261011
as_of = 2026-11-20               # optional; default: today

[sampling]
mode = "sample"                  # sample | full
segments = 10
segment_s = 60

[rules."CORE-M07-01".params]
max_ratio = 0.35

[[exceptions]]
rule = "CORE-M04-01"
object = "sub-07/**"
subkey = "X1"
reason = "Electrode 'X1' is a documented auxiliary sensor (SOP-12)."
approved_by = "QA lead"
valid_until = 2027-06-30

[metadata.defaults]
electrode_type = "wet"
line_frequency_hz = 50
device = "ExampleAmp 64"

[convert]
pattern = '(?P<subject>[A-Za-z0-9]+)_(?P<task>rest|task)\.edf'

[annotation]
mode = "continuous"
epoch_s = 30
vocabulary = ["W", "N1", "N2", "N3", "R"]   # Beispiel; die Codes hängen vom Datensatz ab
annotators = ["scorer*"]                    # optional, Muster (A-80)

[[annotation.files]]                        # reine Annotationsdatei zuordnen (A-80)
path = "raw/night1_scorer2.edf"
recording = "raw/night1.edf"
annotator = "scorer2"

[ai]
labels = "events:trial_type"     # oder "participants:<Spalte>" oder "annotations" (A-81)
splits = ".neurogrid/splits.tsv"

[consent]
split_use = { train = "training", val = "validation", test = "validation" }
dataset_uses = ["sharing"]

[vault]
path = ".neurogrid/vault"
role = "data_steward"
purpose = "pre-check before registration"
approval_ref = "EC-2026-17"
```

### 2.5 Weitere Dateien

- **Ablageort** `.neurogrid/` im Datensatz (A-22, A-30, A-47). Der Validator betritt ihn nicht; außer `manifest.json`, `vault/access.jsonl` und dessen Sperrdatei `vault/access.jsonl.lock` wird alles darin ins Manifest aufgenommen (A-82; `check` lässt zusätzlich seinen Arbeitsordner `run-*` außen vor).
- **`evidence.yaml`** (A-15, A-83): Standardort `.neurogrid/evidence.yaml`; `format_version: 1`, `evidence: {Regel-ID: {…}}` mit `status` open|provided|partial|not_applicable, `document`, `sha256`, `reviewer` (Rolle/Kürzel), `date`, `comment`, `justification`.
- **`manifest.json`** (A-22, A-82): Standardort `.neurogrid/manifest.json`; `format_version`, `files` [{path, sha256, size}], `skipped`, `excluded`, `processing_steps`, `software`, `manifest_hash`.
- **`provenance.yaml`** (A-82): `.neurogrid/provenance.yaml` mit `processing_steps` und `software` (CORE-M13-03).
- **Vault** (A-30): `consents.yaml`, `roles.yaml`, `risks.yaml` ({id, date, description, affected_uses, min_consent_version}), `retention.yaml`, `access.jsonl`, `pia/pia.zh.md`, `pia/pia.en.md`.
- **`splits.tsv`:** `recording`, `split`. Alternativ eine Spalte `split` in `participants.tsv`.
- **`index.json` im Export-ZIP:** SHA-256 je Bestandteil, Kopf-Hash, Werkzeugversion, fester Satz.

### 2.6 Befehle (§13, A-31; Zusätze nach E3 gekennzeichnet)

| Befehl | Optionen | Ausgabe | IDs |
|---|---|---|---|
| `neurogrid scan PFAD` | `--out scan.json`, [E3] `--show-paths` | Formate, Probanden, Aufnahmen, Größen, nicht unterstützte Dateien | CLI-01 |
| `neurogrid convert PFAD --to bids --out ZIEL` | `--config`, `--to gbt47127` (v0.2), [E3] `--strip-identifying-headers` | BIDS-Datensatz + ProcessingSteps + Validatorlauf | CLI-02, NG-F02, NG-F03 |
| `neurogrid check PFAD` | `--rulepack` (mehrfach), `--config`, `--out`, `--strict`, `--manifest`, `--evidence`, `--as-of`, `--role`, `--allow-draft-rulepacks`, [E3] `--jobs`, [E3] `--show-paths` | results.json, Kurzfassung, Exit 0/1/2 | CLI-03, CLI-04 |
| `neurogrid report results.json` | `--lang zh,en`, `--format html,pdf`, `--out`; v1.0 `--format dossier` | `report.<lang>.<html,pdf>` | CLI-05, REP-08 |
| `neurogrid manifest PFAD` | [E3] `--out` (Standard `.neurogrid/manifest.json`), [E3] `--show-paths` | manifest.json | CLI-06 |
| `neurogrid verify PFAD --manifest manifest.json` | [E3] `--show-paths` | geändert/neu/fehlend/Art geändert/unlesbar; Exit 0/1, 2 bei ungültigem Manifest (A-82) | CLI-06 |
| `neurogrid diff alt.json neu.json` | `--format text,json` | neu/behoben/verändert; Exit 1 bei neuen Fehlern | CLI-07 |
| `neurogrid vault init / consent add / log / verify / export` | `consent add --subject --version --date --uses --withdrawn --ethics-ref`, [E3] `--from consents.tsv`; `log --action --objects --purpose --approval-ref`, [E3] `--show`; `verify --expect-head`; `export --report --out` | Vault-Dateien, ZIP | CLI-08, CLI-09 |
| global | `--lang`, `--debug` | – | NG-N06, A-51 |

### 2.7 Exitcodes (A-12)

| Code | Bedeutung |
|---|---|
| 0 | kein nicht ausgenommener error-Befund verletzt, kein offener Nachweis zu einer error-Regel (placeholder-Pakete zählen nicht) |
| 1 | mindestens ein solcher Befund; unlesbare oder nicht unterstützte Datendatei; Datensatz ohne lesbare Aufnahme. Bei `verify`/`vault verify`: Abweichung. Bei `diff`: neue Fehlerbefunde |
| 2 | Werkzeugfehler: Konfiguration, Regelpaket, Validator, Headless Shell für PDF, unzulässiger Pfad, interne Ausnahme, unbekanntes Format einer ausdrücklich übergebenen Datei |

### 2.8 Rollen und Rechte

- **Keine Benutzerkonten** (NZ-08). Zugriffsrechte regelt das Betriebssystem; Bericht und Doku sagen das ausdrücklich.
- **Rollenregister** `roles.yaml` (NV-F04): Rolle, Beschreibung, erlaubte Aktionen (read, check, convert, report, export, consent_manage), Objektbereich (Muster nach A-14), `ethics_approval_ref`. Die Vorlage enthält neutrale Beispielrollen.
- **Beratende Durchsetzung:** Ereignisse werden gegen das Register geprüft (CORE-NV04-01). Ein Befehl warnt, wenn seine Rolle die Aktion nicht darf.
- **Personenfelder** enthalten Rollen oder Kürzel, keine Klarnamen (NZ-09, A-51).

---

## 3. Sicherheit und Regulatorik

| Vorgabe | Umsetzung | Prüfung |
|---|---|---|
| Lokal, offline, keine Telemetrie (NG-N01, CON-04, ARC-06) | kein Netzwerkcode; Audit-Hook (nur Python-Prozess); deno `--deny-net` + `DENO_NO_UPDATE_CHECK`; Chromium-Flags + route + CSP; `onnxruntime.disable_telemetry_events()` | Linux-Lauf ohne Netz + strace (OS-Ebene); Socket-Sperre in Tests; Quelltext- und Paket-Scan |
| Daten nie selbst exportieren (CON-02) | keine Upload-Funktion; Export-ZIP nur fünf Teile + index.json; GitHub Action nur auf eigenen Runnern | ZIP-Test; Action-Test |
| Pseudonymität (NG-N05, NZ-09) | Allowlist der Kopffelder, Ausgabefilter für alle Ausgaben, pseudonyme Aufnahme-IDs bei Rohordnern, Annotationscodes gefiltert, Aggregation mit Zellen < 5, keine Signal-Hashes, kein Rohalter, kein diagnosis_code (A-51) | Fixtures mit eingepflanzten Kennungen je Format; alle Ausgaben inkl. PDF-Text durchsucht |
| Keine Rohsignale (NG-N05) | nur Kennzahlen und aggregierte Grafiken | Test auf Berichtsinhalt |
| Zweckbindung, Einwilligung (PIPL Art. 28/29, MOST 4.3) | M14 mit Versionen und Stichtag; ohne Daten not_checkable; Neueinwilligung als Hinweis an die Ethikkommission | Regel-Tests |
| Rückverfolgbarkeit (NV-F03) | Hashkette mit Sperre; `--expect-head`; Grenzen offen benannt | Tests für Ändern/Einfügen/Löschen/Umsortieren, Kürzen nur mit Kopf-Hash, Neuschreiben nur mit Kopf-Hash |
| Folgenabschätzung, Aufbewahrung (PIPL Art. 55/56) | Gliederungsvorlage mit Platzhalter-Kopf; Aufbewahrung je Objekt ≥ 3 Jahre; neutrale Erinnerung | Fristlogik-Tests; juristische Prüfung vor Verwendung |
| Vorprüfung, keine Konformität (POS-01, NZ-05) | fester Satz überall (A-08); Sperrliste (A-57); placeholder-Pakete gekennzeichnet und ohne Wertung (A-41) | Wort-Test über Vorlagen, Tabellen, Doku, README; Platzhalter-Banner-Test |
| Keine klinischen Aussagen (NZ-01, ARC-05) | keine Patientenbewertung; NG-F17 mit Abgrenzungstext | Wort-Test |
| Normtexte urheberrechtlich geschützt | nur Klauselnummern und eigene Kurztexte (A-55) | DoD P7, P8, P10 |
| Lizenzen (NG-N07, CON-01, D-05, E1) | zweistufiges Gate getrennt für Laufzeit, Dev und research; Komponentenliste für Nicht-Python-Teile; Notices automatisch; DATA_SOURCES; REUSE | CI-Schritte |
| Eingaben (A-52, A-53) | zentrale Pfadprüfung (UNC, `..`, ADS, Junctions); sicherer YAML-Lader; Größen- und Längengrenzen; Escape | Angriffs-Fixtures in der Windows- und Linux-CI |
| Temporäre Dateien (A-54) | Arbeitsordner je Lauf, Aufräumen | Test ohne Reste in %TEMP% |
| Lieferkette | `uv.lock` mit Hashes, exakte Pins, `no-build`; Release-Signatur nach E3 | `uv lock --check`; Signaturprüfung im Installationsskript |
| Rechtstexte | fester Satz zh/en, PIA-Vorlage = Platzhalter bis zur muttersprachlichen bzw. juristischen Prüfung | zh-Prüfung ist Bedingung für die Veröffentlichung von v0.1 |

---

## 4. Teststrategie

**Automatisch** (pytest; lokal ab P1, in der CI ab dem ersten Push laut E2):

| Ebene | Inhalt |
|---|---|
| Unit | kernel (Regelmotor, Vorrang, Ausnahmen inkl. Matcher, Ampel, Abdeckung, Kanonisierung, Hashkette), Adapter, jede Prüfung |
| Regel-Tests | je Regel jedes eingebauten Pakets ein Positiv- und ein Negativfall; ein Meta-Test findet Regeln ohne Fall (NG-N08) |
| Parameter-Meta-Test | jeder Parameter der Registry lässt sich per toml überschreiben und wirkt (MET-02) |
| Erkennung | Generator mit Sollwerten (wie S2): M07 trifft alle Brumm-Kanäle ohne Fehlalarm, M08 auf ±1 Fenster genau, M06-Trefferquote, M09a/b steigen mit dem Artefaktanteil |
| Integration | synthetische Fixtures aller Formate inkl. EDF+D, GBK-kodierter .vhdr, Gleitkomma-.set, Randfälle (kurz, wenige Kanäle, ohne Positionen) |
| Determinismus | zwei Läufe byte-gleich, auch mit Vault, Ausnahmen mit `valid_until`, `--jobs 1/4` und BLAS 1/4; Golden-Vergleich strukturell exakt, Gleitkomma mit Toleranz; Plattformvergleich gemessen |
| CLI | Typer-Runner und echte Unterprozesse unter Bash, PowerShell 7 und Windows PowerShell 5.1; chinesische Pfade; `--lang "zh,en"` |
| Datenschutz | eingepflanzte Kennungen je Format → keine in Konsole, JSON, HTML, PDF-Text, ZIP, Mappe; Fehlerpfade mit `--debug` bereinigt |
| Sicherheit | UNC/`..`/Junction/ADS/Komma-Pfade; YAML-Aliase, doppelte Schlüssel, Übergröße; bösartige Dateinamen |
| Offline | Socket-Sperre in allen Tests; Linux-Job ohne Netz + strace für den ganzen Ablauf |
| Bericht | alle Abschnitte, Pflichtfelder je Befund, fester Satz auf jeder Seite, Platzhalter-Banner, PDF-QA-Gate, Skalierung 1000 × 64 |
| Wortwahl, i18n, Schemas | Sperrliste; jeder Schlüssel in zh/en/de; erzeugte Schemas = eingecheckte |
| Lizenzen | pip-licenses zweistufig (Laufzeit, Dev, research); Komponentenliste Nicht-Python |
| Abdeckung | `tools/coverage_gates.py`: combine über alle Läufe inkl. Unterprozesse; Kern ≥ 90 %, Prüfer ≥ 80 % (A-23) |
| Korpus (`corpus`) | `check` und `report` auf allen 6 Datensätzen; Golden-Liste echter Metadatenfehler; κ auf PSG-IPA |
| Laufzeit (`perf`) | 1-GB-EDF mit 64/128/256 Kanälen (A-50) |

**Manuell:**
- PDF-Sichtprüfung (zh/en)
- muttersprachliche Prüfung der zh-Texte und des festen Satzes (vor v0.1)
- juristische Prüfung der PIA-Vorlage (vor erster echter Verwendung)
- Windows 10 und weitere Linux-Distributionen: „nicht verifiziert“, solange kein Testsystem vorhanden ist

---

## 5. Risiken und Go/No-Go-Punkte

| Nr. | Risiko / Punkt | Folge | Gegenmaßnahme | vor Phase |
|---|---|---|---|---|
| R1 | GB/T 47127-PDF fehlt (D-02) | NG-F03, RP-11, ARC-04 offen | **Go/No-Go G-A** | P7 |
| R2 | YY/T 2029-Text fehlt (D-02) | RP-02/03/06/07/08, V-02 offen | **Go/No-Go G-B** | P8 |
| R3 | ISO/IEC TS 27571 nicht gekauft | NG-F04, V-03 offen | **Go/No-Go G-C** | P10 |
| R4 | NG-N02 verfehlt | Abnahme offen | gemessen 89 s; DoD P3 mit 64/128/256 Kanälen, sonst STOPP | P3 |
| R5 | Validator-JSON ändert sich | Abbildung bricht | exakte Pins, Vertragstest | P2 |
| R6 | Headless Shell: Lizenz (E1), Windows 10 | PDF-Auslieferung | E1; Installationsskript; Win10 = „nicht verifiziert“ | P5 |
| R7 | Kalibrierte Schwellen untypisch | falsche Warnungen | Netzfrequenz je Aufnahme; Herkunft dokumentiert; überschreibbar | P3 |
| R8 | Determinismus über Plattformen | nur je Umgebung zugesichert (A-11) | gemeinsame numpy/scipy-Linie; Messung in der CI | P1–P5 |
| R9 | MkDocs/Material ohne Weiterentwicklung | Doku-Build altert | eingefroren; nur Build betroffen | P5 |
| R10 | Kein GitHub-/Linux-Lauf vor v0.1 | NG-N04, TECH-05/11 spät geprüft | E2 | P1 |
| R11 | zh-Texte, Rechtstexte | Qualität | Platzhalter, Prüfung vor Veröffentlichung | P5, P9 |
| R12 | Gate G1 (BIZ-05) | – | **STOPP nach P5** | nach P5 |
| R13 | Gate G2 (BIZ-05) | – | **STOPP nach Abschluss von v0.2** (nach P8, oder früher, wenn nur normabhängige Phasen übrig sind) | nach P8 |
| R14 | EEGLAB eingebettet nicht blockweise | Speicher ≈ Dateigröße | Bericht weist es aus | P2 |
| R15 | Stichprobe übersieht örtliche Störungen | M06/M09 unvollständig | M08 über volle Länge; Stichprobe ausgewiesen | P3 |
| R16 | M09-Methodik (autoreject 0 %, ICLabel hängt an n) | schwer vergleichbar | Parameter fest; Kalibrierung auf echten Daten; Erkennungstests | P3 |
| R17 | Linux erst ab glibc 2.28; Shell braucht Systembibliotheken | Kundensysteme | Plattformmatrix (A-58); Startprüfung mit Paketliste | P5 |
| R18 | Unterprozesse außerhalb des Audit-Hooks | Offline-Versprechen | Flags je Unterprozess; Nachweis auf OS-Ebene (A-49) | P2, P5 |
| R19 | Klarnamen in Dateinamen/Kopfzeilen | NG-N05 | A-51, A-05; Doku-Hinweis | P1–P5 |
| R20 | Normtext-Zitate im öffentlichen Repo | Urheberrecht | A-55 | P7, P8, P10 |

**Fehlende Normtexte:** Fehlt ein Text an G-A, G-B oder G-C, ziehe ich die nächste normunabhängige Phase vor
(P9, P11) und melde das im Phasenbericht. Ich stoppe, wenn nur noch normabhängige Phasen übrig sind, und an den
STOPPs nach P5 und nach Abschluss von v0.2. Diese Abweichung von „Stopp bei fehlendem Zugang“ gilt nur mit Freigabe von STOPP 2.

---

## 6. Phasenplan

**Reihenfolge:** P1 → P2 → P3 → P4 → P5 (**STOPP G1**) → P6 → [G-A] P7 → [G-B] P8 (**STOPP G2**) → P9 → [G-C] P10 → P11 → P12.

**Jede Phase endet mit:**
- lauffähigem Stand, Tests grün (lokal; ab E2 auch in der CI)
- Abdeckungs-Gates und Lizenz-Gate
- geprüften Akzeptanzkriterien
- aktualisierter Matrix und FORTSCHRITT
- Commit auf `dev` und Phasenbericht

„Schließt ab“ heißt, die Phase liefert den Nachweis für die Zeile. „Trägt bei“ heißt, die Zeile wird dort teilweise gebaut.

| Phase | Inhalt | Schließt ab | Trägt bei zu | Definition of Done |
|---|---|---|---|---|
| P1 Gerüst und Durchstich | Repo nach §13 + `.gitattributes`, REUSE, pyproject/uv.lock (exakte Pins, `no-build`); CI-Workflows; Lizenz-Gate; ruff (PTH, PLW1514)/mypy; `safety.py`; kernel (Regelmotor, Befunde, Kanonisierung, Matcher, i18n, Hashing, Nachweis-Modell, Abdeckung); config; EDF-Adapter + discover; `core` mit M01/M03; `scan`, `check`; minimaler HTML-Bericht (en); Schemas | TECH-02, TECH-03, TECH-04, TECH-09, TECH-11, TECH-12, ARC-02, ARC-03, LIB-10, DM-01, DM-02, DM-03, DM-04, DM-05, DM-06, DM-07, DM-10, RP-01, RP-04, RP-12, V-08 | TECH-01, TECH-05, TECH-10, NG-F11, NG-F12, NG-F13, NG-F14, NG-F18, M01, M03, MET-02, CLI-01, CLI-03, CLI-05, REP-03, NG-N03, NG-N05, NG-N07, NG-N08, CON-01, ARC-01, RP-05 | `check` → results.json → `report` (HTML en) läuft auf EDF-Fixture; JSON schema-gültig und zweimal byte-gleich; Exit 0/1/2 je Testfall; eigenes Regelpaket per Pfad wirkt; kernel-Importgrenze und mypy --strict grün; Lizenz-Gate grün; Coverage-Gates aktiv; TECH-11 erst erfüllt, wenn E2 (Push) den ersten CI-Lauf ermöglicht |
| P2 Formate und BIDS | Adapter BDF, BrainVision, EEGLAB, FIF, EDF+D; nicht unterstützte Formate → M01; Korpus-Werkzeug + DATA_SOURCES; `convert --to bids`; Validator-Integration + `bids`; M01–M05 vollständig inkl. A-46 | NG-F01, NG-F02, NG-F05, NG-F06, M01, M02, M03, M04, M05, CLI-01, CLI-02, RP-09, LIB-02, LIB-03, LIB-08, LIB-09, CON-03 | LIB-01, ARC-04, NG-N01, NG-N05, UF-02, UF-04 | alle 6 Korpus-Datensätze (5 Formate) fehlerfrei eingelesen; Ordner mit `.cnt`/`.xdf` → M01-Fehler mit Dateiname, Ordner ohne lesbare Aufnahme → Exit 1; konvertierte Fixtures und Korpus-Daten bestehen den Validator ohne Fehler; Validator-Meldungen als Befunde mit Unterschlüssel; fehlendes Pflichtfeld je Feld gelistet; Validator unter strace ohne connect; gekürzte Datei, fehlende Begleitdatei, falsche Kanalzahl erkannt |
| P3 Signalqualität | Streaming (M07, M08 je Format, Signal-Hash); Stichprobe mit Vorbedingungen; M06, M09; Kalibrierung; 1-GB-Benchmark | NG-F07, M06, M07, M08, M09, MET-01, NG-N02, LIB-01, LIB-04, LIB-06, LIB-07 | NG-N03 | alle Metrikwerte je Aufnahme im JSON; Erkennungstests gegen Sollwerte bestanden; Randfälle → not_checkable, nie Exit 2; Kalibrierprotokoll im Paket; NG-N02 nach A-50 gemessen (64/128/256 Kanäle); Byte-Gleichheit bei `--jobs 1/4` und BLAS 1/4 |
| P4 Annotation, KI-Struktur, Provenienz, Nachweise, gxdsl008 | M10–M13; `manifest`/`verify`/`--strict`; `evidence.yaml`-Auswertung; Ausnahmen vollständig (Unterschlüssel, Matcher); `gxdsl008` | NG-F08, NG-F09, NG-F10, NG-F12, M10, M11, M12, M13, MET-02, CLI-03, CLI-04, CLI-06, GX-00, GX-01, GX-02, GX-03, GX-04, GX-05, UF-04, UF-05, RP-05 | NG-F11, NG-F18, RP-07, REP-05, UF-01 | κ auf PSG-IPA wie gemessen (±0,001); je Test positiv/negativ für Codes, Lücken, Überlappungen, Klassenanteil, Demografie; Proband in train+test → Fehler; Duplikat gefunden; `verify` erkennt Ändern/Neu/Fehlend auch in splits.tsv und neurogrid.toml; Ausnahme ohne Begründung → Exit 2; GX-04 über evidence.yaml auf „provided“ und „open“ geprüft; Parameter-Meta-Test grün |
| P5 Bericht, Doku, Bündel, v0.1 | Bericht HTML/PDF zh/en (6 Abschnitte, Ampel, Abdeckung, Grafiken, fester Satz überall, Platzhalter-Banner, Skalierung); PDF-QA-Gate; Wortwahl/i18n; Datenschutz-Tests; MkDocs zh/en (inkl. metrics.md, Registry-Seite); Notices; Offline-Bündel + Reinraumtest; Offline-Nachweis OS-Ebene; Release-Workflows (Gitee, PyPI) vorbereitet | NG-F13, NG-F14, NG-F18, CLI-05, REP-00, REP-01, REP-02, REP-03, REP-04, REP-05, REP-06, REP-07, POS-01, POS-02, ARC-05, ARC-06, TECH-05, TECH-06, TECH-07, TECH-08, TECH-10, NG-N01, NG-N03, NG-N04, NG-N05, NG-N06, NG-N07, NG-N08, CON-01, CON-04, CON-05, V-01, V-06, UF-01, UF-07, UF-08 | UF-02, CON-02, TECH-01 | **G1-Kriterium:** `check` (core+bids+gxdsl008) und `report` zh/en laufen auf ≥ 3 Korpus-Datensätzen in ≥ 2 Formaten ohne Exit 2; jeder Befund mit Regel-ID, Klausel, Messwert, Schwelle, Datei, Zeitbereich (bzw. „–“ mit Grund); PDF-QA-Gate grün; Skalierungstest 1000 × 64; Linux-Lauf ohne Netz + strace ohne connect; Bündel installiert in `debian:12-slim --network none` ohne vorinstalliertes Python; Abdeckung Kern ≥ 90 %, Prüfer ≥ 80 %; **STOPP (G1)**: zh-Prüfung, Push-/Veröffentlichungsfreigabe |
| P6 v0.2 normunabhängig | Gerüst `yyt2029` (placeholder, `--allow-draft-rulepacks`, Banner, ohne Wertung); Vorlage Auslegungsfragen; `vault init/consent add/log/verify`; M14; Zugriffsereignisse mit Sperre | NG-F11, NV-F01, NV-F02, NV-F03, M14, DM-08, DM-09, CLI-09, RP-10, ARC-01 | NG-F16, CLI-08, UF-03, UF-06, V-02 | placeholder-Paket ohne Schalter → Exit 2; mit Schalter: Banner, keine Prozentzahl, kein Einfluss auf Exit/Ampel; `vault verify` erkennt Ändern/Einfügen/Löschen/Umsortieren, Kürzen und Neuschreiben nur mit `--expect-head` (getestet, NV-F03 ggf. „teilweise“); zwei `check`-Läufe mit Vault byte-gleich; M14 ohne Daten not_checkable |
| **G-A** | GB/T 47127-PDF liegt in `.local/normen/` | – | – | sonst P9 vorziehen |
| P7 GB/T 47127 | Norm lesen; Inventar der Pflichtelemente (Volltext nur lokal); `io/gbt47127.py` lesen/schreiben; `convert --to gbt47127`; Paket `gbt47127` | NG-F03, RP-11, ARC-04 | V-02 | Inventar ↔ Regeln vollständig; Rundreise BIDS → GB/T → `check` ohne Fehler; keine Normtext-Zitate im Repo |
| **G-B** | YY/T 2029-Text liegt vor | – | – | sonst P9 vorziehen |
| P8 yyt2029 Klausel-Inventar | Inventar (Klausel, 应/宜/可, Phase, Einstufung; Volltext lokal); Regeln; Prüfmethoden genau nach Norm mit Klauselverweis; `source_status: inventory`; Abdeckungsmaß; Auslegungsfragen; NV-F03-Details nach Norm | RP-02, RP-03, RP-06, RP-07, RP-08, V-02 | – | jede Muss-Klausel als Regel; Abdeckung ≥ 60 % (darunter STOPP mit Begründung); keine Normtext-Zitate; **STOPP (G2)** |
| P9 v1.0 normunabhängig | Rollenregister; Aufbewahrung und PIA-Vorlage; Risikoregister + Neueinwilligung; Export-ZIP + index.json; `diff`; GitHub Action + GitLab-Vorlage; Nachweismappe | NV-F04, NV-F05, NV-F06, NV-F07, NG-F15, NG-F16, CLI-07, CLI-08, REP-08, CON-02, UF-02, UF-03, UF-06 | V-03 | ZIP: fünf Teile + index.json, keine Signale/Einwilligungen, nur reguläre Dateien; `min_until` < 3 Jahre → Exit 2; Neueinwilligungsliste als Befunde + Berichtsabschnitt; `diff` trennt neu/behoben/verändert; Action bricht auf GitHub-Runnern ab und läuft auf eigenem Runner (echter Lauf nach Push); Mappe vollständig |
| **G-C** | ISO/IEC TS 27571 gekauft (und GB/T vorhanden) | – | – | sonst P11 vorziehen |
| P10 ISO/IEC TS 27571-Abbildung | Abbildungstabelle TS ↔ BIDS ↔ GB/T (Feldbezeichner + eigene Beschreibung) | NG-F04, V-03 | – | jedes TS-Pflichtfeld zugeordnet oder als Lücke markiert; ISO-Lizenzbedingungen vor Veröffentlichung geprüft |
| P11 NeuroArena | `research/neuroarena` (eigenes Lock): MOABB-Daten, Qualitätsstufen (A-45), 5 Verschlechterungsstufen, EEGNet + CSP+LDA, Notebook, technischer Bericht mit Attribution und Abgrenzung | NG-F17, NA-01, NA-02, NA-03, NA-04, NA-05 | – | Notebook läuft zweimal mit gleichen Zahlen (Toleranz dokumentiert); Kurve für beide Decoder; eigenes Lizenz-Gate grün |
| P12 Abnahme | frische Installation (online, offline), ganze Suite, alle User Flows Ende zu Ende, Matrix Zeile für Zeile | V-04, V-05, V-07, LIB-05, NZ-01, NZ-02, NZ-03, NZ-04, NZ-05, NZ-06, NZ-07, NZ-08, NZ-09, BIZ-01, BIZ-02, BIZ-03, BIZ-04, BIZ-05, BIZ-06, TECH-01 | – | Abnahmetabelle mit Nachweis je Zeile |

---

## 7. Vollständigkeitsprüfung Matrix ↔ Phasenplan

`tools/check_matrix_coverage.py` prüft:
- jede Matrixzeile hat **genau eine** abschließende Phase
- jede ID im Plan existiert in der Matrix

Ergebnis vom 11.10.2026: 166 von 166 Zeilen mit genau einer abschließenden Phase, keine unbekannte ID
(Ausgabe im Phasenbericht). Über mehrere Phasen verteilt (Spalte „trägt bei zu“) sind u. a. NG-F11–F14, NG-F18,
NG-N01/N03/N05, ARC-04, UF-01–UF-06 und V-02/V-03.

---

## 8. Ergebnisse der Machbarkeits-Prototypen (11.10.2026)

Die Prototypen sind Wegwerfcode. Skripte und Protokolle liegen im Sitzungs-Scratchpad.

### 8.1 BIDS-Konvertierung und Validator (S1)
- **Konvertierung:** Alle fünf Formate wurden konvertiert. Mit echten Werten: Validator 0 Fehler, 0 Warnungen. Nur mit Pflichtfeldern: 162 Empfehlungs-Warnungen.
- **MNE-BIDS:** schreibt BIDSVersion 1.9.0, Platzhalter für Name und Autoren, `n/a` und Template-Positionen als `space-CapTrak`. Korrektur nach A-05.
- **`n/a` in typisierten Feldern** erzeugt Fehler.
- **Direktaufruf** mit `--deny-net`: gleiche Befunde wie der offizielle Starter.
- **Laufzeit:** 0,85 s + 2,5 ms je Datei.
- **Exitcodes:** 0/16/1.
- **`.neurogrid/`** bleibt unbeachtet; Dateien in der Wurzel ergeben NOT_INCLUDED.
- **Lücken:** gekürzte EDF, fehlende `.eeg` und falscher `DataFile` bleiben unerkannt (A-46).

### 8.2 Laufzeit 1 GB (S2)
- **Testdatei:** synthetische EDF+C, 1,008 GB, 64 Kanäle, 512 Hz, 4,27 h.
- **Streaming:** 12,2 s, 208 MB. Der Signal-Hash ist in 9 Läufen identisch.

  | Schritt (10 × 60 s, 250 Hz) | Zeit |
  |---|---|
  | pyprep | 23 s |
  | autoreject lokal | 22 s |
  | picard n=20, decim 4 | 13 s |
  | ICLabel | 2,6 s |

  Zum Vergleich: picard mit Standardwerten 115 s; Infomax > 1134 s.
- **Gesamt:** 89 s, ≤ 850 MB, determiniert.
- **Erkennung:** alle 8 Brumm-Kanäle ohne Fehlalarm; pyprep ohne Notch markiert Brumm-Kanäle als schlecht.
- **Offen (R16):** autoreject lokal 0 %; globale Rate 19–40 % je nach Stichprobe; ICLabel-Anteil 27/45/56 % bei 15/20/27 Komponenten.

### 8.3 PDF mit chinesischer Schrift (S3)
- **Durchsatz:** 10 Seiten mit 200 Befunden in 0,7–0,8 s; 91 KB (zh); alle 141 Hanzi extrahierbar.
- **Variable Schriften:** werden zu Type3.
- **Voller statischer Font ohne Subsetting:** Radikal-Codepunkte (生 → U+2F63).
- **Kopf-/Fußzeilen:** Playwright-Templates nutzen Systemschriften, daher CSS `@page`.
- **Netz:** Headless Shell ohne Socket in > 25 Läufen; Edge mit 8–14 Verbindungen (ausgeschlossen).
- **Größe:** Shell 283 MB entpackt / 120 MB zip; Playwright-Paket 105 MB.
- **Determinismus:** HTML byte-gleich; PDF nach festen Datumsfeldern byte-gleich.

### 8.4 Abhängigkeiten und Lizenzen (S4)
- **Lock:** 98 Pakete; nur numpy/scipy/contourpy verzweigen bei 3.12; Wheels für cp311–cp313 vorhanden.
- **Linux:** glibc ≥ 2.28.
- **Venvs:** 3.11/3.13 mit je 64 Paketen; Smoke-Test grün; etwa 580 MiB.
- **Lizenzen der Laufzeit:** 60 permissiv; certifi/tqdm MPL-2.0; pyprep/pybv von Hand geprüft. Kein GPL/LGPL/AGPL auf Ebene der Python-Pakete.
- **Nachträglich gefunden:** Linux-Wheels von numpy/scipy bündeln libquadmath (LGPL) und libgfortran (GPL mit Laufzeitausnahme) → E1.
- **Lizenz-Gate:** zweistufig, positiv und negativ getestet.
- **Netzwerk:** Pipeline unter Audit-Hook ohne Netzwerkversuch.

### 8.5 Testkorpus (S5)
- **Umfang:** 297 Dateien, 1,06 GB, alle 25 Aufnahmen lazy lesbar.
- **Quellen:** OpenNeuro ds003775, ds002778, ds004148, ds004504, ds000248 (CC0) und PhysioNet PSG-IPA v1.0.0 (CC BY 4.0, DOI 10.13026/esx0-nw71; Zitierhinweis in DATA_SOURCES.md).
- **κ auf PSG-IPA:** Scorer 1 gegen 2: 0,79 / 0,69 / 0,81. Mittel der 66 Paare der 12 manuellen Scorer: 0,73 / 0,66 / 0,77.
- **Echte Metadatenfehler** (Golden-Liste):
  - ds002778 sub-hc8: 50 Hz dokumentiert, 60 Hz gemessen.
  - ds004148 sub-01: EEGChannelCount 64 statt 61.
  - `gender` statt `sex`; Spaltenköpfe mit Leerzeichen; BIDSVersion „v1.2.1“; leerer Name.
  - ds003775: echtes Aufnahmedatum (Positivfall für CORE-M01-05).

---

## 9. Offene Entscheidungen (STOPP 2)

**E1 – Mitgelieferte Binärteile und D-05.**
- **Befund (a):** Die Linux-Wheels von numpy/scipy bündeln libquadmath (LGPL) und libgfortran. Das ist mit MNE unvermeidbar.
- **Befund (b):** Die Chrome Headless Shell ist ein Google-Chrome-Build mit Nutzungsbedingungen und enthält FFmpeg (LGPL).
- **Empfehlung:**
  - D-05 gilt für Python-Pakete.
  - Native Bibliotheken in Wheels (dynamisch gelinkt, austauschbar, Quellcode verfügbar) sind mit Hinweis in den Notices erlaubt.
  - Die Headless Shell kommt **nicht** ins Bündel. `tools/install_pdf_browser.py` lädt sie online oder spielt eine vom Kunden bereitgestellte zip mit Prüfsumme ein; HTML geht immer.
- **Alternative:** Shell im Bündel als ausdrückliche Ausnahme. Nicht empfohlen, weil die Weitergabebedingungen ungeklärt sind.

**E2 – CI und Linux vor v0.1.**
- **Empfehlung:**
  - Sie legen das GitHub-Repo `neurogrid` jetzt an (privat ist bis v0.1 möglich).
  - Ich pushe nach jeder Phase auf `dev` (nicht auf `main`); damit läuft die CI ab P1.
  - Zusätzlich starten Sie einmal Docker Desktop (der Fehlerdialog muss weggeklickt werden), damit ich Linux- und Offline-Tests lokal fahren kann.
- **Ohne E2:** TECH-05/TECH-11 und NG-N04 (Linux) bleiben bis P5 „nicht verifiziert“.

**E3 – Zusätze über die PRD hinaus** (je Punkt ja/nein; meine Empfehlung in Klammern):

| Nr. | Zusatz | Nutzen | Empfehlung |
|---|---|---|---|
| a | `check --jobs N` | große Datensätze parallel, Ergebnis bitgleich | ja |
| b | `vault consent add --from consents.tsv` | Massenimport von Einwilligungen | ja |
| c | `vault log --show` | Protokoll lesbar ohne Editor | ja |
| d | `manifest --out` | Manifest außerhalb des Datensatzes | ja |
| e | `convert --strip-identifying-headers` | Kennungen aus Kopfzeilen entfernen vor Weitergabe | ja |
| f | `check --show-paths` | Klarpfade statt pseudonymer IDs für lokale Fehlersuche | ja |
| g | Release-Signatur (Sigstore) + Prüfung im Installationsskript | Vertrauen (PRD §20) | ja |
| h | GitLab-CI-Vorlage zusätzlich zur GitHub Action | chinesische Kunden nutzen oft GitLab | ja |
| i | Bericht auch auf Deutsch | – (PRD: zh/en) | nein |
| j | `check --list-checks` | – (stattdessen generierte Doku-Seite) | nein |

**E4 – Testkorpus ohne EEGDash** (LIB-09). Der Korpus wird über die OpenNeuro-API und PhysioNet geladen. EEGDash
zieht torch und NVIDIA-Pakete nach. **Empfehlung:** Abweichung freigeben.

**E5 – NG-N02.** Lesart „eine 1-GB-EDF-Datei“. Messung: hier mit 4 Kernen < 150 s, auf einem Runner mit
4 vCPU/16 GB < 300 s, mit 64/128/256 Kanälen. **Empfehlung:** freigeben.

**Aufgaben des Projektverantwortlichen** (außerhalb der Software):
- GB/T 47127-PDF nach `.local/normen/` (vor P7)
- YY/T 2029-Text (vor P8)
- ISO/IEC TS 27571 (vor P10)
- GitHub-Repo (E2)
- Docker Desktop starten (E2)
- muttersprachliche Prüfung zh (vor Veröffentlichung v0.1)
- juristische Prüfung der PIA-Vorlage (vor erster Verwendung)
- Gitee- und PyPI-Konten (Veröffentlichung)

---

## 10. Prüfung des Konzepts (11.10.2026)

Drei unabhängige Prüfer haben das Konzept vor der Vorlage gelesen:
- Treue zur PRD
- Technik und Phasen
- Regulatorik, Datenschutz und Lizenzen

Ergebnis: 82 Befunde (0 Blocker, 43 wesentlich, 39 klein). Die wesentlichen sind eingearbeitet; nur dort, wo eine Entscheidung nötig ist, stehen sie als E1–E5 offen. Die wichtigsten Änderungen:
- **Reihenfolge:** v0.2 vor v1.0.
- **Determinismus:** expliziter Stichtag, Vault-Kopf-Hash aus results.json, Umgebungsblock, exakte Pins.
- **Befundschlüssel** mit Unterschlüssel; Umbenennung `belege` → `details`.
- **Platzhalter-Pakete:** nur mit Schalter, mit Banner, ohne Wertung.
- **Ampel:** offene Nachweise zählen als Fehler bzw. Warnung.
- **Manifest** umfasst `.neurogrid/`.
- **Datenschutz:** Allowlist, Ausgabefilter, pseudonyme Aufnahme-IDs.
- **Eingaben:** Pfad- und Eingabesicherheit.
- **Offline-Nachweis** auf Betriebssystemebene; Unterprozesse eigens geschützt.
- **Lizenz-Gate** über Nicht-Python-Bestandteile; Datenquellen-Attribution; Umgang mit Normtexten.
- **Vault:** ehrliche Grenzen der Hashkette; Aufbewahrung je Objekt; PIA nur als Gliederung.
- **M08** je Format; Vorbedingungen der Metriken.
- **Phasenplan** mit „schließt ab“ und „trägt bei“.
