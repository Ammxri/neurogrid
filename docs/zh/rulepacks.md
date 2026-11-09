# 规则包 {#rulepacks}

规则包是一个 YAML 文件，它把测量结果变成检查结果：每条规则引用一个已注册的检查项，并给出其参数、阶段、严重程度
和核验方式。NeuroGrid 内置五个规则包：`core`、`bids`、`gbt47127`（GB/T 47127 多模态数据格式）、`gxdsl008` 和占位规则包 `yyt2029`
（[内置规则](reference/rules.md)、[占位规则包](#placeholder)）；检验机构、制造商或标准起草人无需修改代码即可编写
自己的规则包，并通过 `--rulepack <file>` 或 `[check] rulepacks` 加载。

## 格式 {#format}

| 键 | 含义 |
|---|---|
| `rulepack` | 规则包名称（小写字母、数字、`_`）。两个同名规则包会报错。 |
| `version` | 规则包版本；它与文件的 SHA-256 一起出现在 `results.json` 和报告中。 |
| `source` | 规则所依据的内容（例如某项标准及其版本）。 |
| `source_status` | `final`、`inventory`、`secondary`（数值转引）或 `placeholder`（并非依据标准原文）。 |
| `norm` | 规则包对应一项标准时为 `true`：只有这类状态为 `inventory` 或 `final` 的规则包才计算覆盖率。默认 `false`。 |
| `rules` | 规则列表（至少一条）。 |

每条规则：

| 键 | 含义 |
|---|---|
| `id` | 规则 ID `PACK-PHASE-NNN`，阶段为 ACQ、PROC、ANN、STO 或 ACC（例如 `LABSOP-ACQ-001`）。`core` 规则包特意使用 `CORE-Mxx-NN`：其条款就是指标。 |
| `clause` | 来源中的条款或章节；未知时写 `TBD`。 |
| `title_zh`、`title_en` | 自拟的简短名称；不得引用标准原文。 |
| `phase` | `acquisition`、`processing`、`annotation`、`storage` 或 `access`。 |
| `check` | [检查项注册表](reference/checks.md)中的检查项；检查项未知时，命令以退出码 2 结束。 |
| `params` | 该检查项声明的参数，例如 `{min_hz: 500}`；其他参数会报错。 |
| `severity` | `error`、`warning` 或 `info`。 |
| `strict_severity` | 可选，严格模式（`--strict`）下的严重程度。 |
| `verification` | `automatic`、`semi_automatic` 或 `manual`。人工规则使用检查项 `evidence.document`。 |

该格式的模式以 [`rulepack.schema.json`](../schemas/rulepack.schema.json) 发布。规则包按 UTF-8 读取，并使用安全的
YAML 读取器（不允许别名和重复键，有大小限制）。

## 从标准条款到规则 {#mapping}

推荐的对应方式遵循中国标准的用语：含“应”或“不应”的条款对应严重程度为 `error` 的规则，含“宜”的对应 `warning`，
含“可”的对应 `info`。每条规则归入五个阶段之一，并划分为 `automatic`（可从数据或元数据测量）、`semi_automatic`
（可对配置或文件进行检查）或 `manual`（需要证明文件）。

规则包只包含条款号和自拟的简短说明，从不包含标准的原文、表格或图。

## 人工规则与证明材料 {#evidence}

人工规则依据 `.neurogrid/evidence.yaml`（或 `--evidence`）评价。没有条目时，其状态为“证明材料待补”，并按其严重
程度计入。状态 `provided` 表示：已提交证明材料——这是用户的陈述，NeuroGrid 不对其作评价；NeuroGrid 只检查所指明的文件
存在、不是链接且与记录的哈希值一致。半自动规则在文件缺失或已更改时不通过。

## 占位规则包 {#placeholder}

`source_status: placeholder` 的规则包只有在使用 `--allow-draft-rulepacks` 时才会加载。其检查结果显示在报告中单独的
“未评价”部分，条款标记为占位，从不计入退出码、信号灯或覆盖率。

本版本不包含 YY/T 2029-2026 的任何内容。占位规则包 yyt2029（仅含一条无条款号的示例规则，须使用 `--allow-draft-rulepacks` 加载，不计入统计）同样并非依据标准原文；基于条款的规则包将在研读标准文本后提供。

```bash
neurogrid check DATA --rulepack yyt2029 --allow-draft-rulepacks
```

未使用 `--allow-draft-rulepacks` 时，无论该规则包是通过 `--rulepack`、文件路径还是 `[check] rulepacks` 指定，命令都会
在读取任何数据之前以退出码 2 结束；`neurogrid.toml` 中没有相应的开关。使用该选项时，控制台的结论句只列出已评价的
规则包；如果只加载了占位规则包，控制台和报告都会说明未评价任何规则包（退出码 0）。

## 示例 {#example}

NeuroGrid 的测试会原样执行下面的规则包：在合成测试数据 `edf_ok` 上配合 `tests/fixtures/documented.toml` 运行时，
检查以退出码 0 结束，三个规则 ID 都出现在 `results.json` 中。人工规则没有证明材料，因此状态为“证明材料待补”；作为
警告，它不改变退出码。

<!-- example: rulepack -->
```yaml
rulepack: lab_sop
version: "1.0.0"
source: "SOP EEG-07 of an example laboratory"
source_status: final
rules:
  - id: LABSOP-ACQ-001
    clause: "4.2"
    title_zh: 采样率不低于 250 Hz
    title_en: Sampling rate at least 250 Hz
    phase: acquisition
    check: signal.sampling_rate_min
    params: {min_hz: 250}
    severity: error
    verification: automatic
  - id: LABSOP-ACQ-002
    clause: "4.3"
    title_zh: 每个通道的平直段不超过 1%
    title_en: Flat segments at most 1 % per channel
    phase: acquisition
    check: quality.flatline
    params: {max_fraction: 0.01}
    severity: warning
    verification: automatic
  - id: LABSOP-ACC-001
    clause: "7.1"
    title_zh: 访问权限已记录
    title_en: Access rights documented
    phase: access
    check: evidence.document
    severity: warning
    verification: manual
```

```bash
neurogrid check tests/fixtures/synthetic/edf_ok --config tests/fixtures/documented.toml \
  --rulepack lab_sop.yaml --as-of 2026-10-11
```

## 关于条款解读的反馈 {#feedback}

当一个条款可以有多种解读时，NeuroGrid 会在决策记录以及规则的名称或参数中写明所采用的解读。问题和其他解读的建议请
提交到公开仓库的问题跟踪系统；下方的解读问题清单逐条记录这类条款。

!!! warning "占位符"
    公开仓库的地址为 `<REPO_URL>`，将在仓库发布时填写。

<!-- BEGIN GENERATED interpretation questions -->
### 解读问题 {#questions}

本页列出可有多种解读的条款，以及可能的解读、NeuroGrid 采用的解读和已向哪类角色提出（只写角色，从不写姓名）。本清单由 `docs/_data/interpretation_questions.yaml` 生成；它不专属于某个规则包，凡对应一项标准的规则包均使用它。

#### IQ-001 {#IQ-001}

| | |
|---|---|
| ID | IQ-001 |
| 主题 | 模态目录名的大小写 |
| 规则包 | gbt47127 |
| 条款 | 6.2 |
| 规则 | [GBT47127-STO-007](reference/rules.md#GBT47127-STO-007) |
| 问题 | 6.2 规定模态目录采用英文小写字母缩写，但其列表写作 EEG、fNIRS、MEG、fMRI、iEEG 和 uEphys，7.5.7.1 中的文件名后缀也采用同样的大小写混合写法。应采用哪种写法？ |
| 可能的解读 | (a) 只能采用列表中的写法（EEG、fNIRS 等）。; (b) 只能采用全小写（eeg、fnirs 等）。; (c) 两者均可：列表中的写法或全小写。 |
| 采用的解读 | (c) 条文与列表不一致；NeuroGrid 两种写法都接受，只报告其他写法。convert 采用列表中的写法，与文件名后缀一致。 |
| 状态 | 未决 |
| 已提出（角色、日期） | – |
| 答复 | – |
| 对规则的影响 | 无变更 |

#### IQ-002 {#IQ-002}

| | |
|---|---|
| ID | IQ-002 |
| 主题 | 数据集名称中的特殊字符 |
| 规则包 | gbt47127 |
| 条款 | 7.2, Table 1 |
| 规则 | [GBT47127-STO-002](reference/rules.md#GBT47127-STO-002) |
| 问题 | 表 1 要求数据集名称避免使用特殊字符和空格，但未定义何为特殊字符。名称可以包含哪些字符？ |
| 可能的解读 | (a) 字母、数字、'.'、'_' 和 '-'。; (b) 只能是字母和数字。; (c) 除空格外的任何可打印字符。 |
| 采用的解读 | (a) 这些字符在各操作系统的文件名和目录名中都安全可用；该规则仅为提示。 |
| 状态 | 未决 |
| 已提出（角色、日期） | – |
| 答复 | – |
| 对规则的影响 | 无变更 |

#### IQ-003 {#IQ-003}

| | |
|---|---|
| ID | IQ-003 |
| 主题 | 事件元数据文件中的 <matches> |
| 规则包 | gbt47127 |
| 条款 | 7.6 |
| 规则 | [GBT47127-ANN-002](reference/rules.md#GBT47127-ANN-002), [GBT47127-STO-008](reference/rules.md#GBT47127-STO-008) |
| 问题 | 7.6 规定事件元数据文件命名为 <matches>_events.<extension>，其中 <matches> 为对应信号记录数据文件的文件名。<matches> 是否包含信号记录数据文件的扩展名？ |
| 可能的解读 | (a) 不含扩展名（sub-01_task-rest_EEG_events.tsv）。; (b) 含扩展名（sub-01_task-rest_EEG.edf_events.tsv）。 |
| 采用的解读 | (a) 附属元数据文件与信号记录数据文件仅扩展名不同（7.5.7.2），通道和电极元数据文件的命名也不含扩展名；NeuroGrid 两种形式都能读取，对第二种给出提示。 |
| 状态 | 未决 |
| 已提出（角色、日期） | – |
| 答复 | – |
| 对规则的影响 | 无变更 |

#### IQ-004 {#IQ-004}

| | |
|---|---|
| ID | IQ-004 |
| 主题 | XML 格式的键值型元数据文件的结构 |
| 规则包 | gbt47127 |
| 条款 | 7.1 |
| 规则 | [GBT47127-STO-001](reference/rules.md#GBT47127-STO-001), [GBT47127-STO-010](reference/rules.md#GBT47127-STO-010), [GBT47127-ACQ-001](reference/rules.md#GBT47127-ACQ-001) |
| 问题 | 7.1 允许以 XML 保存键值型元数据，但未规定其结构。字段、数组和数据类型在 XML 中如何表示？ |
| 可能的解读 | (a) 一个根元素；每个子元素是一个以标识符命名的字段；重复出现的子元素为数组；数字和布尔值以文本表示。; (b) 字段作为根元素的属性。 |
| 采用的解读 | (a) 这是 JSON 形式的直接映射；出于安全考虑，含 DOCTYPE 或实体声明的文档不予读取。 |
| 状态 | 未决 |
| 已提出（角色、日期） | – |
| 答复 | – |
| 对规则的影响 | 无变更 |

#### IQ-005 {#IQ-005}

| | |
|---|---|
| ID | IQ-005 |
| 主题 | 光极类型的取值 |
| 规则包 | gbt47127 |
| 条款 | 7.5.2, Table 8 |
| 规则 | [GBT47127-ACQ-003](reference/rules.md#GBT47127-ACQ-003) |
| 问题 | 表 8 规定光极类型为光源或光探测器。该列应填写哪些取值？ |
| 可能的解读 | (a) 中文的“光源”和“光探测器”，或英文的 source 和 detector。; (b) 只能是中文术语。 |
| 采用的解读 | (a) 该格式的标识符为英文，定义为中文；两种形式均接受，不区分大小写。 |
| 状态 | 未决 |
| 已提出（角色、日期） | – |
| 答复 | – |
| 对规则的影响 | 无变更 |
<!-- END GENERATED -->
