# 数据模型

NeuroGrid 的公开格式（results.json、规则包、neurogrid.toml）使用英文标识符。数据模型沿用产品规格（§10）中的
十个对象；本页列出每个原始字段名对应的英文字段名（决定 D-03）。标注为“从不输出”的字段只在进程内使用。

## Dataset（数据集）

| 规格字段 | 字段 |
|---|---|
| id | id |
| name | name |
| version | version |
| quelle | source |
| lizenz | license |
| regelpakete | rulepacks |
| manifest_hash | manifest_hash |

补充字段：`is_bids`。

## Subject（受试者）

| 规格字段 | 字段 |
|---|---|
| pseudo_id | pseudo_id |
| alter_gruppe | age_group |
| geschlecht | sex |
| diagnose_code | diagnosis_code（从不输出） |
| consent_ref | consent_ref |

原始年龄仅用于划分年龄组，从不写出。

## Recording（记录）

| 规格字段 | 字段 |
|---|---|
| id | id |
| subject | subject |
| session | session |
| task | task |
| format | format |
| pfad | path（相对路径，从不输出） |
| abtastrate_hz | sampling_rate_hz |
| dauer_s | duration_s |
| geraet | device |
| elektrodentyp | electrode_type（wet/dry） |
| referenz | reference |
| netzfrequenz_hz | line_frequency_hz |

补充字段：`run`、`streamable`、`discontinuous`、`metadata_sources`（各取值的来源）、`channels`。

## Channel（通道）

| 规格字段 | 字段 |
|---|---|
| name | name |
| typ | type |
| einheit | unit |
| position | position |
| impedanz_kohm | impedance_kohm |
| status | status（good/bad） |

补充字段：`recording_id`、`sampling_rate_hz`、`resolution`、`physical_range`。

## Annotation（标注）

| 规格字段 | 字段 |
|---|---|
| onset_s | onset_s |
| dauer_s | duration_s |
| code | code |
| label | label |
| annotator_id | annotator_id |
| quelle | source |

补充字段：`recording_id`。

## Split（数据划分）

| 规格字段 | 字段 |
|---|---|
| name | name（train/val/test） |
| recording_ids | recording_ids |

## ProcessingStep（处理步骤）

| 规格字段 | 字段 |
|---|---|
| schritt | step |
| werkzeug | tool |
| version | version |
| parameter | parameters |
| eingabe_hash | input_hash |
| ausgabe_hash | output_hash |

## Finding（检查结果）

| 规格字段 | 字段 |
|---|---|
| regel_id | rule_id |
| klausel | clause |
| schweregrad | severity |
| status | status |
| messwert | measured_value |
| schwelle | threshold |
| objekt | object |
| belege | details |

补充字段：`key`、`rulepack`、`rulepack_version`、`source_status`、`phase`、`subkey`、`file`、`channel`、
`params`（生效阈值及其来源）、`time_ranges`、`time_ranges_total`、`time_ranges_duration_s`、`message_key`、
`reason`。

## ConsentScope 与 AccessEvent

这两个对象属于 NeuroVault，将在 0.2 版中加入。

## Results（结果）

`results.json` 包含上述对象以及本次运行的上下文：规则包和规则、生效配置、各记录及其指标和抽样、检查结果
及按次数统计的通过项、提示、证明材料记录、例外、重复组、汇总的 AI 结构（`ai`）和清单比对结果。字段列于
[输出文件](reference/outputs.md#results-json)；JSON 模式为 [`results.schema.json`](../schemas/results.schema.json)。
