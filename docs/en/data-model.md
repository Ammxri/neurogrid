# Data model

NeuroGrid's public formats (results.json, rule packs, neurogrid.toml) use English identifiers. The data model
follows the ten objects of the product specification (§10); this page maps each original field name to its
English name (decision D-03). Fields marked *never in output* stay inside the process.

## Dataset

| Specification field | Field |
|---|---|
| id | id |
| name | name |
| version | version |
| quelle | source |
| lizenz | license |
| regelpakete | rulepacks |
| manifest_hash | manifest_hash |

Supplement: `is_bids`.

## Subject

| Specification field | Field |
|---|---|
| pseudo_id | pseudo_id |
| alter_gruppe | age_group |
| geschlecht | sex |
| diagnose_code | diagnosis_code (never in output) |
| consent_ref | consent_ref |

The raw age is used only to form age groups and is never written.

## Recording

| Specification field | Field |
|---|---|
| id | id |
| subject | subject |
| session | session |
| task | task |
| format | format |
| pfad | path (relative, never in output) |
| abtastrate_hz | sampling_rate_hz |
| dauer_s | duration_s |
| geraet | device |
| elektrodentyp | electrode_type (wet/dry) |
| referenz | reference |
| netzfrequenz_hz | line_frequency_hz |

Supplements: `run`, `streamable`, `discontinuous`, `metadata_sources` (where each value came from), `channels`.

## Channel

| Specification field | Field |
|---|---|
| name | name |
| typ | type |
| einheit | unit |
| position | position |
| impedanz_kohm | impedance_kohm |
| status | status (good/bad) |

Supplements: `recording_id`, `sampling_rate_hz`, `resolution`, `physical_range`.

## Annotation

| Specification field | Field |
|---|---|
| onset_s | onset_s |
| dauer_s | duration_s |
| code | code |
| label | label |
| annotator_id | annotator_id |
| quelle | source |

Supplement: `recording_id`.

## Split

| Specification field | Field |
|---|---|
| name | name (train/val/test) |
| recording_ids | recording_ids |

## ProcessingStep

| Specification field | Field |
|---|---|
| schritt | step |
| werkzeug | tool |
| version | version |
| parameter | parameters |
| eingabe_hash | input_hash |
| ausgabe_hash | output_hash |

## Finding

| Specification field | Field |
|---|---|
| regel_id | rule_id |
| klausel | clause |
| schweregrad | severity |
| status | status |
| messwert | measured_value |
| schwelle | threshold |
| objekt | object |
| belege | details |

Supplements: `key`, `rulepack`, `rulepack_version`, `source_status`, `phase`, `subkey`, `file`, `channel`,
`params` (effective thresholds with their origin), `time_ranges`, `message_key`, `reason`.

## ConsentScope and AccessEvent

Both objects belong to NeuroVault and are added in version 0.2.
