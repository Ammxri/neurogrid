# 术语对照 {#terms}

NeuroGrid 的代码和公开格式（YAML、JSON、TOML）使用英文标识符；其产品规格书使用德文术语。本页逐一列出成为公开
标识符的规格书术语（决定 D-03）。数据模型的十个对象见[数据模型](data-model.md)。

## 规则包格式 {#rulepack-format}

| 规格书术语 | 标识符 | 中文 | 含义 |
|---|---|---|---|
| rulepack | rulepack | 规则包 | 规则包名称 |
| version | version | 版本 | 规则包版本 |
| quelle | source | 来源 | 规则所依据的内容 |
| regeln | rules | 规则 | 规则列表 |
| id | id | 规则 ID | 规则标识 |
| klausel | clause | 条款 | 来源中的条款或章节 |
| titel_zh | title_zh | 中文名称 | 中文名称 |
| titel_en | title_en | 英文名称 | 英文名称 |
| phase | phase | 阶段 | 数据生命周期中的阶段 |
| pruefung | check | 检查项 | 已注册的检查项 |
| parameter | params | 参数 | 检查项的参数 |
| schweregrad | severity | 严重程度 | 严重程度 |
| nachweis | verification | 核验方式 | 规则的核验方式 |

没有对应规格书术语的补充键：`source_status`、`norm`、`strict_severity`（[规则包](rulepacks.md)）。

## 取值 {#values}

| 规格书术语 | 标识符 | 中文 | 含义 |
|---|---|---|---|
| erfassung | acquisition | 采集 | 阶段 |
| verarbeitung | processing | 处理 | 阶段 |
| annotation | annotation | 标注 | 阶段 |
| speicherung | storage | 存储 | 阶段 |
| zugriff | access | 访问 | 阶段 |
| fehler | error | 错误 | 严重程度 |
| warnung | warning | 警告 | 严重程度 |
| hinweis | info | 提示 | 严重程度 |
| automatisch | automatic | 自动 | 可从数据或元数据测量 |
| halbautomatisch | semi_automatic | 半自动 | 可检查配置或文件是否存在 |
| manuell | manual | 人工 | 需要证明文件 |
| nass | wet | 湿电极 | 电极类型（`[metadata.defaults] electrode_type`） |
| trocken | dry | 干电极 | 电极类型 |
| gut | good | 良好 | 通道状态 |
| schlecht | bad | 不良 | 通道状态 |
| training | training | 训练 | 知情同意中的用途（自 0.2 版起） |
| validierung | validation | 验证 | 知情同意中的用途（自 0.2 版起） |
| veroeffentlichung | publication | 发表 | 知情同意中的用途（自 0.2 版起） |
| weitergabe | sharing | 共享 | 知情同意中的用途（自 0.2 版起） |
| kommerziell | commercial | 商业用途 | 知情同意中的用途（自 0.2 版起） |

## 报告与检查结果 {#report-terms}

| 规格书术语 | 标识符 | 中文 | 含义 |
|---|---|---|---|
| Befund | finding | 检查结果 | 一条规则对一个对象的结果（results.json 中的 `findings`） |
| Belege | details | 详情 | 检查结果的支持信息（`details`） |
| Nachweis | evidence | 证明材料 | 人工或半自动规则的证明材料（`evidence.yaml`，results.json 中的 `evidence`） |
| Ausnahme | exception | 例外 | 有理由的例外（`[[exceptions]]`，results.json 中的 `exceptions`） |
| Ampel | light | 信号灯 | 每个阶段的信号灯（`summary.phases.*.light`） |
| Abdeckungsmass | coverage | 覆盖率 | 每个规则包的覆盖率（`summary.coverage`） |
| Stichtag | as_of | 基准日期 | 检查的基准日期（`--as-of`、`config.as_of`） |

检查结果的状态（`status`）：`passed`、`failed`、`excepted`、`not_applicable`、`not_checkable`、`evidence_open`
（[阅读报告](report.md#findings)）。
