# 命令 {#commands}

`neurogrid [全局选项] <命令> [参数和选项]`。不带参数运行 `neurogrid` 会显示帮助并以退出码 2 结束。
`neurogrid <命令> --help` 以所选语言显示该命令的帮助。

命令行中的路径相对于当前文件夹。只有 `report --lang`、`report --format` 和 `diff --format` 接受逗号分隔的列表；在 PowerShell 中
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
| `--rulepack NAME_OR_PATH` | 内置规则包（`core`、`bids`、`gxdsl008`、`yyt2029`）或 YAML 文件；可重复指定。`yyt2029` 是占位规则包，在基于条款的版本提供之前只有使用 `--allow-draft-rulepacks` 时才会加载（[占位规则包](rulepacks.md#placeholder)）。 |
| `--config FILE` | `neurogrid.toml`（默认：数据集中的 `.neurogrid/neurogrid.toml`）。 |
| `--out FILE` | 结果文件（默认 `results.json`）。 |
| `--strict` | 严格模式：缺少清单即为错误（CORE-M13-01）。 |
| `--as-of YYYY-MM-DD` | 判断例外和日期所用的基准日期（默认：今天）；它是结果的一部分。 |
| `--allow-draft-rulepacks` | 允许加载占位规则包；其规则会显示，但从不计入统计。`neurogrid.toml` 中没有相应的设置：每次运行单独决定。 |
| `--show-paths` | 显示真实路径，而非假名 ID（原始文件夹）。 |
| `--jobs N` | 计算信号指标所用的进程数，1–64；结果与 `--jobs 1` 逐字节相同。 |
| `--evidence FILE` | `evidence.yaml`（默认：数据集中的 `.neurogrid/evidence.yaml`）。 |
| `--manifest FILE` | 用于比对的清单（默认：数据集中的 `.neurogrid/manifest.json`）。 |
| `--role ROLE` | 本次运行在 vault 中记录的访问事件的角色：角色名称或姓名缩写（以字母开头，其后为字母、数字、`_`、`.` 或 `-`，最多 80 个字符），优先于 `[vault] role`。角色无效时以退出码 2 结束，没有 vault 时也是如此；没有 vault 时该选项不起作用，并有提示说明。 |

有 vault 时（`[vault] path`，默认为 `.neurogrid/vault`），`check` 在写入 `results.json` 之后追加一个访问事件（操作
`check`，对象 `**`）；该事件从不进入 `results.json`。访问事件无法写入时（vault 被锁定或为只读、缺少访问日志）只给出
警告，退出码不变。

| 退出码 | 含义 |
|---|---|
| 0 | 没有未通过的错误级规则，错误级规则也没有待补的证明材料（占位规则包不计） |
| 1 | 至少有一项上述情况；或有无法读取、不受支持的数据文件，或数据集中没有可读取的记录 |
| 2 | 工具错误：配置、规则包（包括未使用 `--allow-draft-rulepacks` 的占位规则包）、验证器、不允许的路径、vault 路径中有链接、`--role` 无效、内部错误 |

控制台的结论句只列出已评价的规则包，从不列出占位规则包。如果只加载了占位规则包，结论句会说明未评价任何规则包，退出码为 0。

## report {#report}

`neurogrid report RESULTS [--lang zh,en] [--format html,pdf,dossier] [--out FOLDER] [--config FILE]`

只根据 `results.json` 按语言和格式生成报告：`report.<lang>.html` 和 `report.<lang>.pdf`（[阅读报告](report.md)）。
命令最后会输出固定声明。
使用 `--format dossier` 时还会写出 `dossier.pdf`，即[证明材料汇编](report.md#dossier)：目录部分与中文报告和英文报告
合为一个 PDF，始终包含两种语言，不受 `--lang` 影响。

| 参数 / 选项 | 含义 |
|---|---|
| `RESULTS_FILE` | 由 `check` 写入的 `results.json`。 |
| `--lang` | 报告语言 `zh`、`en`（默认 `zh,en`）。 |
| `--format` | `html`、`pdf`、`dossier`（默认 `html`）；PDF 和证明材料汇编需要 [PDF 浏览器](installation.md#pdf-browser)。多种格式要么全部写出，要么都不写出。 |
| `--out FOLDER` | 输出文件夹（默认：`results.json` 所在的文件夹）。 |
| `--config FILE` | 报告显示其 vault 的 `neurogrid.toml`：封面增加访问日志一行（条目数、链头哈希值、哈希链状态，在生成报告前读取），报告在写出文件之后追加其访问事件（操作 `report`）。不指定 `--config` 时，报告不读取也不写入任何 vault。 |

| 退出码 | 含义 |
|---|---|
| 0 | 已写出所有要求的报告 |
| 2 | 工具错误：结果无法读取、未知的语言或格式、缺少 PDF 浏览器或 Linux 系统库（此时不写出任何文件）、`--config` 无效、vault 路径中有链接 |

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

## diff {#diff}

`neurogrid diff OLD NEW [--format text|json|text,json] [--out FILE]`

版本比较：按每项检查结果的稳定键（规则 × 对象 × 子键）比较同一数据集的两个 `results.json` 文件。它只读取这两个
文件，不读取数据集和 vault，也不记录访问事件。

| 类别 | 含义 |
|---|---|
| 新增 | 该键只在 `NEW` 中 |
| 已消除 | 该键只在 `OLD` 中，且其规则在 `NEW` 中对同一对象计有通过结果 |
| 已移除 | 该键只在 `OLD` 中的其他情况：规则不再加载或对象已不存在 |
| 已变化 | 该键在两者中都有，但状态、有效严重程度或测量值不同（数值四舍五入到 6 位有效数字） |

占位规则包的检查结果不参与比较，只计数。针对知情同意记录的规则（`consent.*` 检查，例如 CORE-M14-01）的检查结果
按规则和类别计数，从不逐项列出，因此版本比较中不会出现任何受试者。文本显示两次运行（NeuroGrid 版本、基准日期、
规则包）、配置是否变化，数据集 ID 或名称不同时给出警告，然后每个类别最多 200 行（JSON 列出全部）、计数的知情同意
规则、汇总和退出码的原因。对象与 `results.json` 中一致：在原始数据文件夹中为假名，除非检查时使用了 `--show-paths`。

| 参数 / 选项 | 含义 |
|---|---|
| `OLD` | 较早运行的 `results.json`。 |
| `NEW` | 较晚运行的 `results.json`。 |
| `--format` | `text`（默认）、`json` 或 `text,json`。仅有 `json` 且没有 `--out` 时，控制台输出 JSON 而不输出文本（固定声明是其字段 `disclaimer`）；`text,json` 需要 `--out`。 |
| `--out FILE` | JSON 文件（[输出文件](reference/outputs.md#diff-json)）；仅在 `--format` 含 `json` 时使用。 |

| 退出码 | 含义 |
|---|---|
| 0 | 没有新的错误级结果 |
| 1 | 至少有一个键在 `NEW` 中是计入的错误级结果（未通过或证明材料待补，严重程度为错误），而在 `OLD` 中不是：新增结果或变为错误，知情同意规则也包括在内 |
| 2 | 工具错误：某个文件不是可读取的 `results.json`（消息指明 `OLD` 或 `NEW`）、未知格式、`text,json` 未给出 `--out`、`--out` 未配合 `json` |

## vault {#vault}

`neurogrid vault <命令> [参数和选项]`

NeuroVault 命令作用于 vault 文件夹：`neurogrid.toml` 中的 `[vault] path`，相对于项目根目录，默认为
`.neurogrid/vault`。其中包含知情同意记录 `consents.yaml`、哈希链访问日志 `access.jsonl` 及其锁文件
`access.jsonl.lock`。vault 路径中的链接从不跟随。`neurogrid vault consent` 汇集用于知情同意记录的命令。不带命令时，
`neurogrid vault` 和 `neurogrid vault consent` 显示帮助并以退出码 2 结束。

文件格式、哈希链及其局限见 [NeuroVault](vault.md)。每个 vault 命令都接受 `PATH`，即数据集文件夹（默认：当前文件夹；不接受文件），以及 `--config FILE`，即其
`[vault] path` 指定 vault 的 `neurogrid.toml`（默认：数据集中的 `.neurogrid/neurogrid.toml`）。每个命令最后都输出
固定声明。

| 退出码 | 含义 |
|---|---|
| 0 | 命令已完成；对 `vault verify`：访问日志完整 |
| 1 | `vault verify`：访问日志中至少有一处不一致，包括缺少访问日志或未找到预期的链头哈希值 |
| 2 | 工具错误：没有 vault、vault 路径中有链接、vault 路径不是文件夹、vault 被另一个 NeuroGrid 进程锁定或无法写入、输入无效（角色、目的、操作、对象、链头哈希值） |

### vault init {#vault-init}

`neurogrid vault init [PATH] [--config FILE]`

创建 vault 中缺少的部分：vault 路径中的文件夹、`consents.yaml`（尚无知情同意记录）、空的访问日志 `access.jsonl`
及其锁文件 `access.jsonl.lock`、角色登记册 `roles.yaml`、风险登记册 `risks.yaml` 和保存期限 `retention.yaml`（均为空，
附带注释示例），以及个人信息保护影响评估的草稿 `pia/pia.zh.md` 和 `pia/pia.en.md`（[NeuroVault](vault.md#folder)）。
已有部分逐字节保留，因此该命令可随时重复运行，也可用于 0.2 版的 vault（只补充新增部分）；它不记录访问事件（哈希链从
创世哈希值开始）。之后请重新运行 `neurogrid manifest`：`consents.yaml`、各登记册和 PIA 文件属于清单，访问日志及其
锁文件不属于清单。

| 参数 / 选项 | 含义 |
|---|---|
| `PATH` | 数据集文件夹（默认：当前文件夹）。 |
| `--config FILE` | `neurogrid.toml`；其 `[vault] path` 指定 vault。 |

### vault log {#vault-log}

`neurogrid vault log [PATH] [--config FILE] --action ACTION --objects OBJECT [--objects OBJECT ...] --purpose TEXT [--approval-ref REF] [--role ROLE]`

`neurogrid vault log [PATH] [--config FILE] --show`

手动记录一次访问，例如 NeuroGrid 无法看到的、交给审阅人员的副本。角色和目的为必填：`--role` 优先于
`[vault] role`，`--purpose` 优先于 `[vault] purpose`；`--approval-ref` 优先于 `[vault] approval_ref`，可选。
在原始文件夹中，指向现有文件的对象以其假名文件名记录（与 `verify` 的显示相同）；在对象被视为模式之前，先按操作系统
读取文件名的方式查找该名称，因此含 `[`、`*` 或 `?` 的文件名，以及在 Windows 下大小写不同或末尾带点或空格的名称，也算
作现有文件。指向数据集中的链接或目录联接（或经过链接的路径）的对象以退出码 2 结束（从不跟随链接）。模式、文件夹和 BIDS
路径按原样记录。
看起来像人名或身份编号的对象、目的或角色会给出提示，并按原样记录。命令输出新条目的序号和哈希值。

`--show` 显示最新的 200 个条目（行、序号、UTC 时间、角色、操作、对象、目的、批准编号；无法读取的行只显示其行号）、
未显示的较早行数、条目数、链头哈希值和哈希链状态。它不能与条目的选项同时使用，也不作任何记录。

| 参数 / 选项 | 含义 |
|---|---|
| `PATH` | 数据集文件夹（默认：当前文件夹）。 |
| `--config FILE` | `neurogrid.toml`；其 `[vault] path` 指定 vault。 |
| `--action ACTION` | `read`、`check`、`convert`、`report`、`export` 或 `consent_manage`。 |
| `--objects OBJECT` | 相对于数据集的路径或模式（`**` = 整个数据集）；多个对象时重复该选项，逗号属于路径的一部分（最多 1000 个对象，每个最多 1024 个字符）。 |
| `--purpose TEXT` | 访问目的，最多 200 个字符（默认：`[vault] purpose`）。 |
| `--approval-ref REF` | 批准编号，例如伦理委员会的批件编号，最多 120 个字符（默认：`[vault] approval_ref`）。 |
| `--role ROLE` | 角色名称或姓名缩写（默认：`[vault] role`）。 |
| `--show` | 显示日志，而不记录条目。 |

### vault verify {#vault-verify}

`neurogrid vault verify [PATH] [--config FILE] [--expect-head HASH ...]`

校验访问日志的哈希链。输出条目数、链头哈希值（最后一个条目的哈希值）、每处不一致的行、类型和可能的原因（修改、
插入、删除、重新排序），从不输出条目内容；还输出每个预期链头的结果、在别处记录链头哈希值的提示以及哈希链的局限。
它不记录访问事件。

| 参数 / 选项 | 含义 |
|---|---|
| `PATH` | 数据集文件夹（默认：当前文件夹）。 |
| `--config FILE` | `neurogrid.toml`；其 `[vault] path` 指定 vault。 |
| `--expect-head HASH` | 先前在 vault 之外记录的链头哈希值（64 位十六进制数字）；即使之后又追加了条目，它也必须仍是完整哈希链的一部分。可重复。只有这样才能发现末尾截断和整体重写。 |

### vault export {#vault-export}

`neurogrid vault export [PATH] --report FILE [--report FILE ...] --out FILE.zip [--manifest FILE] [--show-paths]
[--config FILE] [--role ROLE] [--purpose TEXT] [--approval-ref REF]`

为检查写出检查包（[NeuroVault](vault.md#export)）：一个 ZIP，恰好包含五个组成部分和 `index.json`，先写入 `--out`
旁的临时文件，再移到目标位置，要么全部写出，要么什么都不写。所有内容先读取并检查；随后在 vault 锁下追加访问事件
`export`，访问日志打包到该事件为止（含该事件）。`index.json` 列出每个组成部分及其 SHA-256 和大小，以及导出日志的
链头哈希值，即导出事件的哈希值：请在 vault 之外记下它，以后用 `neurogrid vault verify --expect-head` 检查。角色、
目的和批准编号与 `vault log` 相同；必须有角色。控制台输出每个组成部分的大小和 SHA-256、链头哈希值和归档的路径，
并对未经编辑的个人信息保护影响评估、空的角色登记册、断裂的哈希链（日志按原样导出）以及位于数据集内的归档给出警告。

| 参数 / 选项 | 含义 |
|---|---|
| `PATH` | 数据集文件夹（默认：当前文件夹）。 |
| `--report FILE` | 要纳入的 NeuroGrid 报告，须为 `neurogrid report` 写出且未经修改：`report.<lang>.html`、`report.<lang>.pdf` 或 `dossier.pdf`。重复该选项可给出 1 至 5 份报告，每种一次；其他文件一律拒绝。 |
| `--out FILE.zip` | 要写出的 ZIP 文件；不得位于 vault 文件夹内。已有文件会被替换。 |
| `--manifest FILE` | 要纳入的清单（默认：数据集中的 `.neurogrid/manifest.json`）；必须有效。 |
| `--show-paths` | 在导出的清单中保留真实文件名；否则在原始数据文件夹中以假名 ID 命名文件，与 `verify` 的显示相同。 |
| `--config FILE` | `neurogrid.toml`；其 `[vault] path` 指定 vault。 |
| `--role ROLE` | 访问事件中的角色（默认：`[vault] role`；没有角色时退出码为 2）。 |
| `--purpose TEXT`、`--approval-ref REF` | 访问事件的目的和批准编号（默认：`[vault] purpose` 和 `approval_ref`，否则为空）。 |

| 退出码 | 含义 |
|---|---|
| 0 | 已写出检查包，哈希链断裂时也是如此（`index.json` 记录其状态） |
| 2 | 拒绝，不写出任何内容，也不记录访问事件：缺少组成部分或不是普通文件、链接、清单或角色登记册无效、文件不是 NeuroGrid 报告或同一报告给出两次、`--out` 位于 vault 内或是文件夹、没有角色；事件之后只会因写入失败而结束（事件保留，`--out` 不变） |

### 其他命令的访问事件 {#access-events}

`check`（操作 `check`）、`convert`（操作 `convert`，源文件夹 `neurogrid.toml` 的 vault）和 `report --config`
（操作 `report`）向其 `neurogrid.toml` 的 vault 追加一个事件，角色、目的和批准编号取自 `[vault]`（`check --role`
优先于 `[vault] role`；没有角色时事件不记录角色，并有提示说明）。`scan`、`manifest` 和 `verify` 只向默认位置
`.neurogrid/vault` 的 vault 追加操作为 `read` 的事件，不含角色、目的和批准编号。每个事件都在本次运行的输出写入之后
追加，并以整个数据集（`**`）为对象。不作记录的有：以退出码 2 结束的运行、不带 `--config` 的 `report`、`vault init`、
`vault log --show` 和 `vault verify`。事件无法写入时只给出警告，从不改变退出码；对 `convert`、`scan`、`manifest` 和
`verify`，vault 路径中的链接属于这种警告，对 `check`、`report --config` 和各 vault 命令则为退出码 2。

`check`、`convert`、`report --config`、`vault log` 和 `vault consent add` 在开始时将自身的访问与角色登记册
`roles.yaml` 比较（[NeuroVault](vault.md#roles)）：登记册不允许该访问（未知角色，或该角色没有的操作或对象），或无法
读取 `roles.yaml` 时，它们给出警告，但仍记录该事件；退出码不变。只有 `check` 会因无效的 `roles.yaml`（CORE-NV04-01
读取该文件）以退出码 2 结束。没有登记册、为 `roles: []`，以及不记录角色的 `scan`、`manifest` 和 `verify`，均不作比较。

### vault consent add {#vault-consent-add}

`neurogrid vault consent add PATH --subject S --version N --date YYYY-MM-DD (--uses U[,U] | --withdrawn)
[--ethics-ref R]` 记录一条知情同意；`neurogrid vault consent add PATH --from consents.tsv` 导入一张表格
（[consents.tsv](reference/outputs.md#consents)）。`PATH` 是数据集文件夹；vault 为 `neurogrid.toml` 中的 `[vault] path`
（`--config`，默认为数据集中的 `.neurogrid/neurogrid.toml`）。请先使用 `neurogrid vault init` 创建 vault。

| 选项 | 含义 |
|---|---|
| `--subject` | 假名受试者，可带或不带 `sub-`。 |
| `--version` | 知情同意的版本，1 到 1000000 之间的整数；更改记录为一个更高的新版本。 |
| `--date` | 知情同意或撤回的日期，`YYYY-MM-DD`。 |
| `--uses` | 允许的用途（可重复指定或用逗号分隔）：`training`、`validation`、`publication`、`sharing`、`commercial`。部分撤回是用途更少的新版本。 |
| `--withdrawn` | 自该日期起完全撤回；不带 `--uses`。 |
| `--ethics-ref` | 可选的伦理审批编号（不得含人名）。 |
| `--from` | 用导入表代替单项字段；要么记录所有行，要么一行也不记录。 |
| `--config` | 含 `[vault] path` 和访问事件字段默认值的 `neurogrid.toml`。 |
| `--role` | 访问事件中的角色（角色或姓名缩写）；默认 `[vault] role`；没有角色时退出码为 2。 |
| `--purpose`、`--approval-ref` | 访问事件的目的和批准编号；默认 `[vault] purpose` 和 `approval_ref`，否则为空。 |

命令在 vault 锁下读取现有记录，检查新的完整文件（同一受试者和版本记录两次、较高版本的日期早于较低版本、字段无效：
退出码 2，不写入任何内容），为 `consents.yaml` 追加访问事件 `consent_manage`，然后一步替换该文件。若在写入事件之后
无法写入文件，命令以退出码 2 结束，文件保持不变，日志保留这次尝试。控制台显示受试者和版本或导入记录的数量，从不显示
用途或伦理审批编号。记录成功时退出码为 0，任何拒绝时为 2。

## 退出码总览 {#exit-codes}

- **0** – 没有未通过的错误级规则，错误级规则也没有待补的证明材料；仅有警告从不改变退出码。
- **1** – 检查结果：未通过的错误级规则、错误级规则待补的证明材料、无法读取或不受支持的数据文件、没有可读取的记录；
  对 `verify` 和 `vault verify` 为存在不一致，对 `convert` 为有文件未转换，对 `diff` 为有新的错误级结果。
- **2** – 仅限工具错误：配置、规则包、验证器、PDF 浏览器、不允许的路径、内部错误、明确指定的未知格式的单个文件。
  数据集中的数据从不导致退出码 2。
