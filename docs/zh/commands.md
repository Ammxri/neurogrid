# 命令 {#commands}

`neurogrid [全局选项] <命令> [参数和选项]`。不带参数运行 `neurogrid` 会显示帮助并以退出码 2 结束。
`neurogrid <命令> --help` 以所选语言显示该命令的帮助。

命令行中的路径相对于当前文件夹。只有 `report --lang` 和 `report --format` 接受逗号分隔的列表；在 PowerShell 中
请加引号（`--lang "zh,en"`）或重复该选项。

## 全局选项 {#global}

| 选项 | 含义 |
|---|---|
| `--lang zh` / `--lang en` | 所有消息（包括 `--help`）的语言。未指定时依次使用环境变量 `NEUROGRID_LANG`、系统语言，否则为英文。未知或空的取值以退出码 2 结束。 |
| `--debug` | 发生内部错误时，另外显示不含控制字符、用户主文件夹和数据集路径的回溯信息。 |
| `--help` | 显示帮助并退出。 |

## scan {#scan}

`neurogrid scan PATH [--out FILE] [--show-paths]`

清点数据集文件夹或单个数据文件：BIDS 或原始文件夹、格式、受试者、记录、大小、不支持和无法读取的文件、未跟随的
链接；如果文件名看起来可识别身份，则给出提示。

| 参数 / 选项 | 含义 |
|---|---|
| `PATH` | 数据集文件夹或单个数据文件。 |
| `--out FILE` | 另将清点结果写为 JSON（[输出文件](reference/outputs.md#scan-json)）。 |
| `--show-paths` | 显示真实路径，而非假名 ID（原始文件夹）。 |

| 退出码 | 含义 |
|---|---|
| 0 | 已完成清点 |
| 2 | 工具错误（不允许的路径、输出无法写入、内部错误） |

## convert {#convert}

`neurogrid convert PATH --to bids --out FOLDER [--config FILE] [--strip-identifying-headers]`

将原始数据文件夹转换为 EEG-BIDS（MNE-BIDS 0.20.0），并对结果运行 BIDS 验证器。任何地方都没有记录的必填元数据
写为 `n/a` 并列出；名称和作者从不编造。

| 参数 / 选项 | 含义 |
|---|---|
| `PATH` | 原始数据文件夹或单个数据文件（以 BIDS 数据集作为输入时以退出码 2 结束）。 |
| `--to bids` | 目标结构；0.1 版支持 `bids`。 |
| `--out FOLDER` | 输出文件夹；必须为空或尚不存在，且位于输入之外。 |
| `--config FILE` | `neurogrid.toml`（默认：原始数据文件夹中的 `.neurogrid/neurogrid.toml`），其中记录文件到受试者、会话、任务和运行编号的映射。 |
| `--strip-identifying-headers` | 在转换后的副本中，将可识别身份的文件头字段（EDF/BDF 的受试者字段和记录字段、开始日期、BrainVision 注释）替换为占位值。 |

| 退出码 | 含义 |
|---|---|
| 0 | 所有记录均已转换，验证器未报告错误 |
| 1 | 有文件未转换，或验证器报告了错误 |
| 2 | 工具错误：缺少映射（会写出模板）、输出文件夹不可用、验证器无法运行 |

## check {#check}

`neurogrid check PATH [选项]`

按已加载的规则包检查数据集，并写入 `results.json`。除非 `neurogrid.toml` 在 `[check] rulepacks` 中列出了规则包，
否则加载 `core`。

| 参数 / 选项 | 含义 |
|---|---|
| `PATH` | 数据集文件夹或单个数据文件。 |
| `--rulepack NAME_OR_PATH` | 内置规则包（`core`、`bids`、`gxdsl008`）或 YAML 文件；可重复指定。 |
| `--config FILE` | `neurogrid.toml`（默认：数据集中的 `.neurogrid/neurogrid.toml`）。 |
| `--out FILE` | 结果文件（默认 `results.json`）。 |
| `--strict` | 严格模式：缺少清单即为错误（CORE-M13-01）。 |
| `--as-of YYYY-MM-DD` | 判断例外和日期所用的基准日期（默认：今天）；它是结果的一部分。 |
| `--allow-draft-rulepacks` | 允许加载占位规则包；其规则会显示，但从不计入统计。 |
| `--show-paths` | 显示真实路径，而非假名 ID（原始文件夹）。 |
| `--jobs N` | 计算信号指标所用的进程数，1–64；结果与 `--jobs 1` 逐字节相同。 |
| `--evidence FILE` | `evidence.yaml`（默认：数据集中的 `.neurogrid/evidence.yaml`）。 |
| `--manifest FILE` | 用于比对的清单（默认：数据集中的 `.neurogrid/manifest.json`）。 |

| 退出码 | 含义 |
|---|---|
| 0 | 没有未通过的错误级规则，错误级规则也没有待补的证明材料（占位规则包不计） |
| 1 | 至少有一项上述情况；或有无法读取、不受支持的数据文件，或数据集中没有可读取的记录 |
| 2 | 工具错误：配置、规则包、验证器、不允许的路径、内部错误 |

## report {#report}

`neurogrid report RESULTS [--lang zh,en] [--format html,pdf] [--out FOLDER]`

只根据 `results.json` 按语言和格式生成报告：`report.<lang>.html` 和 `report.<lang>.pdf`（[阅读报告](report.md)）。
命令最后会输出固定声明。

| 参数 / 选项 | 含义 |
|---|---|
| `RESULTS_FILE` | 由 `check` 写入的 `results.json`。 |
| `--lang` | 报告语言 `zh`、`en`（默认 `zh,en`）。 |
| `--format` | `html`、`pdf`（默认 `html`）；PDF 需要 [PDF 浏览器](installation.md#pdf-browser)。 |
| `--out FOLDER` | 输出文件夹（默认：`results.json` 所在的文件夹）。 |

| 退出码 | 含义 |
|---|---|
| 0 | 已写出所有要求的报告 |
| 2 | 工具错误：结果无法读取、未知的语言或格式、缺少 PDF 浏览器或 Linux 系统库（此时不写出任何文件） |

## manifest {#manifest}

`neurogrid manifest PATH [--out FILE] [--show-paths]`

写入溯源清单：每个文件的 SHA-256 和大小、处理步骤和软件版本（M13）。链接和特殊文件只列出，从不跟随。

| 参数 / 选项 | 含义 |
|---|---|
| `PATH` | 数据集文件夹。 |
| `--out FILE` | 清单文件（默认：数据集中的 `.neurogrid/manifest.json`）。 |
| `--show-paths` | 显示真实路径，而非假名 ID（原始文件夹）。 |

| 退出码 | 含义 |
|---|---|
| 0 | 已写入清单 |
| 1 | 有文件无法读取，或数据集的条目多于清单可列出的数量；未写入任何内容 |
| 2 | 工具错误（例如 `.neurogrid/processing_steps.json` 无效） |

## verify {#verify}

`neurogrid verify PATH --manifest FILE [--show-paths]`

将数据集与其清单比对：已更改、新增和缺失的文件，发生变化的链接或特殊文件，以及无法读取的文件。

| 参数 / 选项 | 含义 |
|---|---|
| `PATH` | 数据集文件夹。 |
| `--manifest FILE` | 由 `manifest` 写入的 `manifest.json`（必填）。 |
| `--show-paths` | 显示真实路径，而非假名 ID（原始文件夹）。 |

| 退出码 | 含义 |
|---|---|
| 0 | 数据集与清单一致 |
| 1 | 至少有一处不一致 |
| 2 | 工具错误：清单无效 |

## 退出码总览 {#exit-codes}

- **0** – 没有未通过的错误级规则，错误级规则也没有待补的证明材料；仅有警告从不改变退出码。
- **1** – 检查结果：未通过的错误级规则、错误级规则待补的证明材料、无法读取或不受支持的数据文件、没有可读取的记录；
  对 `verify` 为存在不一致，对 `convert` 为有文件未转换。
- **2** – 仅限工具错误：配置、规则包、验证器、PDF 浏览器、不允许的路径、内部错误、明确指定的未知格式的单个文件。
  数据集中的数据从不导致退出码 2。
