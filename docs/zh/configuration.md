# 配置 {#configuration}

数据集通过 `neurogrid.toml` 描述。其默认位置是数据集中的 `.neurogrid/neurogrid.toml`；`--config` 可指定其他文件。
该文件按 UTF-8（带或不带字节顺序标记）读取并严格校验：未知的键、错误的类型或无效的值都会使运行以退出码 2 结束，
并指出相应字段。

**项目根目录。** 文件中的路径相对于项目根目录：对于位于 `.neurogrid` 文件夹中的文件，为其上一级文件夹；对于数据集中的
其他文件，为数据集根目录；否则为该文件所在的文件夹。路径必须是普通的相对路径（不得含 `..`、盘符、网络或设备路径）。
从不跟随链接。

**优先顺序。** 元数据：`neurogrid.toml` > BIDS 附带文件 > 文件头 > 未记录（作为检查结果，不中止运行）。阈值：
`neurogrid.toml`（`[rules."ID".params]`）> 规则包 > 检查项默认值。每条检查结果都会写明生效的阈值及其来源。

## [dataset] {#dataset}

`id`、`name`、`version`、`source`、`license`：用于报告和 `results.json` 的数据集字段。此处设置的 `name` 和 `license`
优先于 `dataset_description.json` 中的 `Name` 和 `License`；只有此处未设置时才使用该文件中的值。`id`、`version` 和
`source` 只来自本节。没有 `id` 时数据集显示为“unnamed”；从不使用文件夹名称，因为它可能可识别身份。

## [check] {#check}

| 键 | 含义 |
|---|---|
| `rulepacks` | 要加载的规则包（名称或相对路径）；它会取代默认的 `core`，因此请同时列出 `core`。`--rulepack` 可再添加规则包。空列表无效。 |
| `strict` | 严格模式，与 `--strict` 相同（默认 `false`）。 |
| `seed` | 抽样指标的随机种子（默认 20261011，取值 0 至 2^63−1）。 |
| `as_of` | 基准日期 `YYYY-MM-DD`（默认：今天）；`--as-of` 优先。 |

## [sampling] {#sampling}

M06 和 M09 在抽样上运行：`mode = "sample"` 在等分的各段中间各取 `segments`（默认 10）个长为 `segment_s`
（默认 60）秒的片段；不超过 10 分钟的记录整体使用。`mode = "full"` 使用整条记录（[指标](metrics.md#M06)）。

## [quality] {#quality}

| 键 | 默认值 | 含义 |
|---|---|---|
| `flat_tolerance_uv` | 0.1 | 浮点格式中峰峰值低于该值（µV）即视为平直（M08）。 |
| `plateau_samples` | 10 | 量程未知时，在极值处连续相同的样本数达到该值即视为削波（M08）。 |
| `min_seconds` | 60 | M06/M09 所需的数据时长。 |
| `min_channels` | 16 | M06/M09 所需的 EEG 通道数。 |

## [rules."ID".params] {#rules}

按规则 ID 覆盖某条规则的参数，例如在 `[rules."CORE-M07-01".params]` 中写 `max_ratio = 0.35`。只接受该检查项声明的
参数（[检查项注册表](reference/checks.md)）。

## [[exceptions]] {#exceptions}

有理由的例外会使匹配的检查结果不计入退出码和信号灯；这些结果仍在报告附录中显示。

| 键 | 含义 |
|---|---|
| `rule` | 规则 ID（必填）。 |
| `object` | 对象的匹配模式：相对 POSIX 路径或假名 ID；`**` 匹配任意多个路径段，`*` 匹配一个路径段，区分大小写。 |
| `subkey` | 子键，例如字段名、通道或验证器代码。 |
| `reason` | 理由（必填，不得为空；缺少时退出码为 2）。 |
| `approved_by` | 角色或姓名缩写，从不填写全名。 |
| `valid_until` | 有效期的最后一天；晚于 `as_of` 后该例外不再生效，并给出警告。 |

## [metadata] {#metadata}

| 键 | 含义 |
|---|---|
| `defaults.electrode_type` | `wet` 或 `dry`；只能在此处记录。未记录时阻抗阈值无法检查；为 `dry` 时不适用。 |
| `defaults.line_frequency_hz` | 记录的工频（否则 M07 使用 50 Hz）。 |
| `defaults.device` | 设备名称。 |
| `defaults.reference` | EEG 参考（EEG-BIDS 的 `EEGReference`）。 |
| `defaults.software_filters` | 软件滤波（EEG-BIDS 的 `SoftwareFilters`，`n/a` 有效）。 |
| `mixed_sampling_rates_reason` | 记录采样率不一致时的理由（M03）。 |
| `channel_map` | 通道标签 → 标准位置名称，用于与 10-20/10-10/10-05 不同的标签（M04）。 |

## [convert] {#convert}

供 `convert`（以及 `scan` 统计受试者）使用的原始文件到受试者、会话、任务和运行编号的映射：

- `pattern`：带命名分组 `subject` 和 `task`（必填）以及 `session`、`run`（可选）的正则表达式，与相对路径或文件名
  匹配。标签必须由字母和数字组成，`run` 必须是数字。含反向引用或嵌套重复的表达式会被拒绝（退出码 2）。
- `[[convert.files]]`，含 `path`、`subject`、`session`、`task`、`run`：映射表，优先于正则表达式。

## [annotation] {#annotation}

| 键 | 含义 |
|---|---|
| `mode` | `events`（默认）或 `continuous`（睡眠分期等无间隙的评分）。 |
| `epoch_s` | κ 的网格；默认连续模式 30 秒，事件模式 1 秒。 |
| `vocabulary` | 允许的代码（精确匹配）；未设置时使用 `events.json` 中的 `Levels`。 |
| `annotators` | 参与计算的标注者 ID 的匹配模式（`*`、`?`）。 |
| `files` | `[[annotation.files]]`，含 `path`、`recording` 和可选的 `annotator`：仅含标注的文件（例如睡眠分期图）及其所属的记录。 |

## [ai] {#ai}

| 键 | 含义 |
|---|---|
| `labels` | M11 类别标签的来源：`events:<column>`、`participants:<column>` 或 `annotations`。未设置时 CORE-M11-01 不适用。 |
| `splits` | 数据划分文件（列 `recording`、`split`，取值 train、val、test）；默认 `.neurogrid/splits.tsv`，否则为 `participants.tsv` 中的 `split` 列。 |

## [consent] 和 [vault] {#consent-vault}

这两节会被接受并校验；从 0.2 版（NeuroVault）起才进行评价。在 0.1 版中，`[vault] path`（默认 `.neurogrid/vault`）
已用于将 vault 访问日志排除在清单之外。键：`[consent]` 的 `split_use`、`dataset_uses`；`[vault]` 的 `path`、`role`、
`purpose`、`approval_ref`。

## 示例 {#example}

<!-- example: neurogrid.toml -->
```toml
[dataset]
id = "example-eeg"
name = "Example EEG study"
license = "CC0"

[check]
rulepacks = ["core", "bids", "gxdsl008"]
strict = false
as_of = 2026-11-20

[sampling]
mode = "sample"
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
reference = "Cz"

[annotation]
mode = "continuous"
epoch_s = 30
vocabulary = ["W", "N1", "N2", "N3", "R"]

[ai]
labels = "events:trial_type"
splits = ".neurogrid/splits.tsv"
```

## .neurogrid/ 中的其他文件 {#files}

| 文件 | 内容 |
|---|---|
| `evidence.yaml` | 人工和半自动规则的证明材料：`format_version: 1`，`evidence: {规则 ID: {status, document, sha256, reviewer, date, comment, justification}}`；status 为 `open`、`provided`、`partial` 或 `not_applicable`（须写明理由）。NeuroGrid 计算每份文件的 SHA-256，并与记录的值比较。 |
| `splits.tsv` | 列 `recording`（相对路径或假名 ID）和 `split`（train、val、test）。 |
| `provenance.yaml` | `processing_steps` 和 `software`（CORE-M13-03）；`processing_steps: []` 表示“未经处理”。 |
| `manifest.json` | 由 `manifest` 写入（[输出文件](reference/outputs.md#manifest)）。 |
