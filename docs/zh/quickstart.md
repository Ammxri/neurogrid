# 快速开始 {#quickstart}

四条命令即可从一个原始脑电文件夹得到报告。示例中调用的是 `neurogrid`；离线安装时请使用启动程序的完整路径
（[安装](installation.md#install)）。

## 1. 数据清点：`scan` {#scan}

```bash
neurogrid scan raw/
```

`scan` 列出格式、受试者、记录、大小以及 NeuroGrid 无法读取的文件，不做任何修改。

## 2. 转换为 EEG-BIDS：`convert` {#convert}

原始数据文件夹需要将每个文件映射到受试者、任务以及（可选的）会话和运行编号。请将映射写入
`raw/.neurogrid/neurogrid.toml`，例如用匹配文件名的正则表达式：

```toml
[convert]
pattern = '(?P<subject>[A-Za-z0-9]+)_(?P<task>rest|task)\.edf'

[metadata.defaults]
reference = "Cz"
line_frequency_hz = 50
```

```bash
neurogrid convert raw/ --to bids --out bids/
```

没有映射时，`convert` 会写出模板 `raw/.neurogrid/mapping-template.toml`（每个文件一行），并以退出码 2 结束；请将
其中的行复制到 `neurogrid.toml` 并填写标签。输出文件夹必须为空或尚不存在。BIDS 验证器会离线检查转换结果。

## 3. 检查：`check` {#check}

```bash
neurogrid check bids/ --rulepack bids --rulepack gxdsl008 --out results.json
```

除非 `neurogrid.toml` 列出了其他规则包，否则总会加载 `core` 规则包。控制台会显示结果、错误和警告的数量以及固定声明。
`results.json` 包含全部检查结果。

## 4. 报告：`report` {#report}

=== "Bash"

    ```bash
    neurogrid report results.json --lang zh,en --format html,pdf
    ```

=== "PowerShell"

    ```powershell
    neurogrid report results.json --lang "zh,en" --format "html,pdf"
    ```

PowerShell 会把未加引号的逗号拆分为多个参数：请给列表加引号，或重复该选项（`--lang zh --lang en`）。报告写在
`results.json` 旁边，文件名为 `report.zh.html`、`report.en.html`、`report.zh.pdf` 和 `report.en.pdf`
（[阅读报告](report.md)）。生成 PDF 需要 [PDF 浏览器](installation.md#pdf-browser)。

## 退出码 {#exit-codes}

| 退出码 | 含义 |
|---|---|
| 0 | 已加载规则包中没有未通过的错误级规则，错误级规则也没有待补的证明材料 |
| 1 | 至少有一项上述情况；或有无法读取、不受支持的数据文件，或没有可读取的记录 |
| 2 | 工具错误：配置、规则包、验证器、PDF 浏览器、不允许的路径、内部错误 |

数据问题是检查结果（退出码 1），从不是工具错误。各命令的详细说明见[命令](commands.md)。

## 中文消息 {#language}

```bash
neurogrid --lang zh check bids/
```

在命令之前使用 `--lang`，或设置环境变量 `NEUROGRID_LANG`，即可为所有消息选择 zh 或 en，包括 `--help` 和命令行错误。
