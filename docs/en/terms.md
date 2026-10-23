# Terms {#terms}

NeuroGrid's code and public formats (YAML, JSON, TOML) use English identifiers; its product specification uses
German terms. This page maps each specification term that became a public identifier 1:1 (decision D-03). The
ten objects of the data model are on [Data model](data-model.md).

## Rule pack format {#rulepack-format}

| Specification term | Identifier | Meaning |
|---|---|---|
| rulepack | rulepack | name of the rule pack |
| version | version | version of the rule pack |
| quelle | source | what the rules are based on |
| regeln | rules | list of rules |
| id | id | rule ID |
| klausel | clause | clause or section of the source |
| titel_zh | title_zh | Chinese title |
| titel_en | title_en | English title |
| phase | phase | phase of the data life cycle |
| pruefung | check | registered check |
| parameter | params | parameters of the check |
| schweregrad | severity | severity |
| nachweis | verification | how the rule is verified |

Additions without a specification term: `source_status`, `norm`, `strict_severity` ([Rule packs](rulepacks.md)).

## Values {#values}

| Specification term | Identifier | Meaning |
|---|---|---|
| erfassung | acquisition | phase: acquisition |
| verarbeitung | processing | phase: processing |
| annotation | annotation | phase: annotation |
| speicherung | storage | phase: storage |
| zugriff | access | phase: access |
| fehler | error | severity: error |
| warnung | warning | severity: warning |
| hinweis | info | severity: note |
| automatisch | automatic | measurable from data or metadata |
| halbautomatisch | semi_automatic | a configuration or a document can be checked |
| manuell | manual | needs an evidence document |
| nass | wet | electrode type (`[metadata.defaults] electrode_type`) |
| trocken | dry | electrode type |
| gut | good | channel status |
| schlecht | bad | channel status |
| training | training | consent use (from version 0.2) |
| validierung | validation | consent use (from version 0.2) |
| veroeffentlichung | publication | consent use (from version 0.2) |
| weitergabe | sharing | consent use (from version 0.2) |
| kommerziell | commercial | consent use (from version 0.2) |

## Report and findings {#report-terms}

| Specification term | Identifier | Meaning |
|---|---|---|
| Befund | finding | result of one rule for one object (`findings` in results.json) |
| Belege | details | supporting details of a finding (`details`) |
| Nachweis | evidence | evidence for a manual or semi-automatic rule (`evidence.yaml`, `evidence` in results.json) |
| Ausnahme | exception | justified exception (`[[exceptions]]`, `exceptions` in results.json) |
| Ampel | light | traffic light per phase (`summary.phases.*.light`) |
| Abdeckungsmass | coverage | coverage measure per rule pack (`summary.coverage`) |
| Stichtag | as_of | reference date of a check (`--as-of`, `config.as_of`) |

Statuses of a finding (`status`): `passed`, `failed`, `excepted`, `not_applicable`, `not_checkable`,
`evidence_open` ([Reading the report](report.md#findings)).
