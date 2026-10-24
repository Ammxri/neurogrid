# 规则包 {#rulepacks}

规则包是一个 YAML 文件，它把测量结果变成检查结果：每条规则引用一个已注册的检查项，并给出其参数、阶段、严重程度
和核验方式。NeuroGrid 内置 `core`、`bids` 和 `gxdsl008`（[内置规则](reference/rules.md)）；检验机构、制造商或
标准起草人无需修改代码即可编写自己的规则包，并通过 `--rulepack <file>` 或 `[check] rulepacks` 加载。

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
| `title_zh`、`title_en` | 自拟的简短名称；从不引用标准原文。 |
| `phase` | `acquisition`、`processing`、`annotation`、`storage` 或 `access`。 |
| `check` | [检查项注册表](reference/checks.md)中的检查项；未知的检查项以退出码 2 结束。 |
| `params` | 该检查项声明的参数，例如 `{min_hz: 500}`；其他参数会报错。 |
| `severity` | `error`、`warning` 或 `info`。 |
| `strict_severity` | 可选，严格模式（`--strict`）下的严重程度。 |
| `verification` | `automatic`、`semi_automatic` 或 `manual`。人工规则使用检查项 `evidence.document`。 |

该格式的模式以 [`rulepack.schema.json`](../schemas/rulepack.schema.json) 发布。规则包按 UTF-8 读取，并使用安全的
YAML 读取器（不允许别名和重复键，有大小限制）。

## 从标准条款到规则 {#mapping}

推荐的对应方式遵循中国标准的用语：含“应”或“不应”的条款对应严重程度为 `error` 的规则，含“宜”的对应 `warning`，
含“可”的对应 `info`。每条规则归入五个阶段之一，并划分为 `automatic`（可从数据或元数据测量）、`semi_automatic`
（可检查配置或文件是否存在）或 `manual`（需要证明文件）。

规则包只包含条款号和自拟的简短说明，从不包含标准的原文、表格或图。

## 人工规则与证明材料 {#evidence}

人工规则依据 `.neurogrid/evidence.yaml`（或 `--evidence`）评价。没有条目时，其状态为“证明材料待补”，并按其严重
程度计入。“已提供”表示：证明材料已提交——这是用户的陈述，NeuroGrid 不对其作评价；NeuroGrid 只检查所指明的文件
存在、不是链接且与记录的哈希值一致。半自动规则在文件缺失或已更改时不通过。

## 占位规则包 {#placeholder}

`source_status: placeholder` 的规则包只有在使用 `--allow-draft-rulepacks` 时才会加载。其检查结果显示在报告中单独的
“未评价”部分，条款标记为占位，从不计入退出码、信号灯或覆盖率。

0.1 版不包含 YY/T 2029-2026 的任何内容。yyt2029 规则包将在研读标准文本后提供。

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
提交到公开仓库的问题跟踪系统；解读问题清单将在 0.2 版中随 yyt2029 规则包提供。

!!! warning "占位"
    公开仓库的地址为 `<REPO_URL>`，将在仓库发布时填写。
