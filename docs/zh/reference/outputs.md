# 输出文件 {#outputs}

NeuroGrid 写出的所有文件均为 UTF-8 编码、LF 换行。JSON 文件是规范化的：键已排序，数字格式固定，不含时刻、计算机名
或用户名，也不含绝对路径。使用相同的数据、配置（包括 `as_of`）、规则包版本和运行环境，两次运行得到逐字节相同的文件。

## results.json {#results-json}

由 `check` 写入（`--out`，默认 `results.json`）；`report` 只读取该文件。JSON 模式：
[`results.schema.json`](../../schemas/results.schema.json)。

| 字段 | 内容 |
|---|---|
| `schema_version` | 格式版本。 |
| `disclaimer` | 中英文固定声明。 |
| `tool` | NeuroGrid 的名称和版本。 |
| `environment` | Python、平台、参与计算的依赖库及其版本、BLAS 线程数。 |
| `dataset` | 数据集字段，不含路径。 |
| `rulepacks` | 已加载的规则包：名称、版本、来源、来源状态、是否对应标准、文件的 SHA-256。 |
| `rules` | 每条已加载的规则，含条款、名称、阶段、检查项、生效的严重程度、严格模式下的严重程度、核验方式。 |
| `config` | 规范化配置的哈希值、`as_of`、随机种子、严格模式、抽样、生效阈值和设置（已清理）、`evidence.yaml` 的哈希值、知情同意记录的哈希值（`consents_sha256`）。 |
| `recordings` | 每条记录：假名 ID、格式、能否分块读取、指标以及 M06/M09 的抽样。 |
| `findings` | 每条未通过的检查结果，每个“规则 × 对象 × 子键”一条，带稳定的键。 |
| `passed` | 通过的检查，按规则和对象计数。 |
| `notices` | 本次运行的提示（级别、消息键、参数）。 |
| `evidence` | 来自 `evidence.yaml` 的证明材料记录，含计算出的和记录的 SHA-256。 |
| `exceptions` | 配置的例外及其是否被使用。 |
| `duplicates` | 信号相同的记录组（假名 ID），或 `null`。 |
| `ai` | 汇总的标签、人口学信息和数据划分计数（每个单元格少于 5 名受试者时扣留），或 `null`。 |
| `summary` | 每个阶段的信号灯、错误、警告、待补的证明材料；每个规则包的覆盖率；合计和退出码。 |
| `manifest` | 清单比对的结果，或 `null`。 |
| `consent` | M14：每种用途需要知情同意覆盖的受试者人数（报告中知情同意表格的合计），或 `null`。 |

不包含：时刻、计算机名或用户名、绝对路径、信号哈希值、原始年龄；关于 vault 访问日志，除 CORE-NV03-01/02 的发现外不含任何
内容：没有链头哈希值，也没有事件的数量或时间。本次运行自身的访问事件在写入 `results.json` 之后才追加。

## 清点 JSON {#scan-json}

由 `scan --out` 写入（模式 [`scan.schema.json`](../../schemas/scan.schema.json)）：`schema_version`、`disclaimer`、
`tool`、`is_bids`、`formats`、`subjects`、`recordings`、`unsupported`、`orphans`、`unreadable`、`other_files`、
`links_skipped`、`total_bytes`、`suspicious_names`（只有数量，从不列出名称）。

## 报告 {#reports}

每种语言 `zh`、`en` 的 `report.<lang>.html` 和 `report.<lang>.pdf`，位于 `--out` 指定的文件夹（默认：`results.json`
旁边），见[阅读报告](../report.md)。使用 `--format dossier` 时另有 `dossier.pdf`，即包含两种语言的
[证明材料汇编](../report.md#dossier)。

## manifest.json {#manifest}

由 `manifest` 写入（默认 `.neurogrid/manifest.json`；模式 [`manifest.schema.json`](../../schemas/manifest.schema.json)）：
`format_version`、`files`（路径、SHA-256、大小）、`skipped`（链接、特殊文件、被路径检查拒绝的名称）、`excluded`
（默认位置的 vault 和 `[vault] path` 处的 vault 的访问日志及其锁文件）、`processing_steps`、`software`、`manifest_hash`（基于规范化 JSON 字节计算）。

## consents.yaml 和 consents.tsv {#consents}

vault 中的 `consents.yaml` 保存知情同意记录（模式 [`consents.schema.json`](../../schemas/consents.schema.json)）；
`neurogrid vault init` 创建空文件，`neurogrid vault consent add` 以规范格式重写它（记录按受试者和版本排序，手工添加的
注释不保留）：

<!-- example: consents.yaml -->
```yaml
format_version: 1
consents:
  - subject: sub-01
    version: 1
    date: 2026-03-01
    permitted_uses: [training, validation]
    withdrawn: false
    ethics_approval_ref: "EC-2026-17"
```

| 字段 | 内容 |
|---|---|
| `subject` | 假名受试者：`sub-<标签>`，标签由字母和数字组成（最多 64 个字符）；输入时可带或不带 `sub-`。 |
| `version` | 1 到 1000000 之间的整数；较高版本取代较低版本，日期不得随版本升高而提前。 |
| `date` | 知情同意或撤回的日期，`YYYY-MM-DD`。 |
| `permitted_uses` | `training`、`validation`、`publication`、`sharing`、`commercial` 的子集；只有 `withdrawn: true` 时可为空。 |
| `withdrawn` | 自 `date` 起完全撤回时为 `true`（默认 `false`）。 |
| `ethics_approval_ref` | 可选的伦理审批编号，1 到 120 个可打印字符；不得为人名。 |

最多 20 000 条记录、4 000 000 字节。文件无效时，`check` 和 `vault consent add` 以退出码 2 结束，并指出记录和字段，从不
显示值。`consents.yaml` 属于清单，因此 `verify` 会报告在 NeuroGrid 之外所做的更改。

`consents.tsv` 是 `vault consent add --from` 的导入表：UTF-8（带或不带 BOM），制表符分隔，标题行（名称不区分大小写）含
`subject`、`version`、`date`、`permitted_uses`（或 `uses`，单元格内以逗号分隔），可选 `withdrawn`（`true`/`false`、
`yes`/`no`、`1`/`0`，空 = false）和 `ethics_approval_ref`（或 `ethics_ref`）。最多 10 000 000 字节、20 000 行；错误信息
指出行和列，从不显示单元格内容。

`results.json` 中的 `config.consents_sha256` 是解析后规范化记录的 SHA-256（同一组记录无论如何书写都相同）；没有
`consents.yaml` 或未加载 M14 时为 `null`；记录本身从不进入 `results.json`。

## 访问日志 {#access-log}

vault（`[vault] path`，默认 `.neurogrid/vault`）中的 `access.jsonl`，由 `vault init` 创建为空文件，由各命令追加
（[NeuroVault](../vault.md#events)）：每行一个访问事件，格式为按键排序的紧凑 JSON，以 LF 结尾（模式
[`access_event.schema.json`](../../schemas/access_event.schema.json)）。字段：`format_version`、`seq`、`time`、
`role`、`action`、`objects`、`purpose`、`approval_ref`、`tool_version`、`previous_hash`、`hash`
（[哈希链](../vault.md#chain)）。其锁文件 `access.jsonl.lock` 为空文件。两者都不纳入清单。

## 检查包（ZIP） {#export-zip}

由 `vault export` 写入 `--out`（[NeuroVault](../vault.md#export)）：成员依次为 `manifest.json`、`access.jsonl`、
`roles.yaml`、`pia/pia.zh.md` 和 `pia/pia.en.md`（存在的）、`report/report.<lang>.html`、`report/report.<lang>.pdf`
和 `report/dossier.pdf`（给出的），最后是 `index.json`（模式 [`export_index.schema.json`](../../schemas/export_index.schema.json)；
键已排序、以 LF 换行的规范化 JSON）：`format_version`（1）、`disclaimer`（`zh`、`en`）、`tool`（`name`、`version`）、
`parts`（每个成员：`part` 为 `manifest`、`access_log`、`roles`、`pia` 或 `report`；`file` 为归档中的名称；`sha256`；
`size`；个人信息保护影响评估文件或报告的 `lang`；报告的 `format`：`html`、`pdf` 或 `dossier`）、`manifest`
（原存储的 `manifest_hash`、所读文件的 `source_sha256`、`pseudonymized`：归档的副本以假名 ID 命名数据文件）以及
`access_log`（`head` 为导出事件的哈希值；`events`；`intact`；`deviations`）。不含时间、归档以外的路径以及用户名或
计算机名。

## 其他模式 {#schemas}

[`config.schema.json`](../../schemas/config.schema.json)（`neurogrid.toml`）、
[`rulepack.schema.json`](../../schemas/rulepack.schema.json)、
[`evidence.schema.json`](../../schemas/evidence.schema.json)（`evidence.yaml`）、
[`consents.schema.json`](../../schemas/consents.schema.json)（`consents.yaml`）和
[`access_event.schema.json`](../../schemas/access_event.schema.json)（`access.jsonl` 的一行）。

## 退出码 {#exit-codes}

| 退出码 | 含义 |
|---|---|
| 0 | 没有未通过的错误级规则，错误级规则也没有待补的证明材料 |
| 1 | 有检查结果，或存在不一致（`verify`），或有文件未转换（`convert`） |
| 2 | 工具错误 |

各命令的详细说明见[命令](../commands.md)。
