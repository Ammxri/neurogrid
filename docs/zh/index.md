# NeuroGrid {#neurogrid}

!!! note "固定声明"
    使用 NeuroGrid 进行的预检。不构成国家药品监督管理局（NMPA）法规意义上的符合性评价。

NeuroGrid 是一个开源、本地、离线运行的工具，用于对面向人工智能脑机接口（BCI）产品的脑电（EEG）数据集进行预检。
它读取 EDF/EDF+、BDF、BrainVision、EEGLAB 和 FIF 格式的记录，将原始数据文件夹转换为 EEG-BIDS，测量质量指标
M01–M13，用规则包对其进行评价，并写出 `results.json` 以及中英文报告（HTML 和 PDF）。

结果只说明数据集是否*通过已加载规则包的各项检查*。NeuroGrid 不进行符合性评价：符合性评价由检验机构和国家药品
监督管理局（NMPA）进行。NeuroGrid 只评价数据集，从不评价任何个人；它不是医疗器械。

## 0.1 版包含的内容 {#v01}

- 命令 `scan`、`convert --to bids`、`check`、`report`、`manifest` 和 `verify`（[命令](commands.md)）。
- 规则包 `core`（指标 M01–M13，[指标](metrics.md)）、`bids`（BIDS 验证器 3.0.2）和 `gxdsl008`（产品规格书转引的
  T/GXDSL 008-2025 起始值，二手来源）（[内置规则](reference/rules.md)）。
- 使用已注册检查项编写的自定义 YAML 规则包（[规则包](rulepacks.md)）。
- 作为规范结果的 `results.json` 以及中英文报告（[阅读报告](report.md)、[输出文件](reference/outputs.md)）。
- 完全在本地运行，不建立任何网络连接（[隐私与离线运行](privacy.md)）。

0.1 版不包含 YY/T 2029-2026 的任何内容。yyt2029 规则包将在研读标准文本后提供。
`diff`、NeuroVault 和证明材料汇编不属于 0.1 版（[局限](limitations.md)）。

## 从哪里开始 {#start}

1. [安装](installation.md)：离线安装包、PDF 浏览器、从源代码安装。
2. [快速开始](quickstart.md)：四条命令，从原始数据文件夹到报告。
3. [配置](configuration.md)：在 `neurogrid.toml` 中记录元数据、阈值和有理由的例外。

## 开放的参考实现与反馈 {#feedback}

NeuroGrid 是一个开放的参考实现：检验机构、标准起草人和制造商都可以自行运行它，查看每条规则的方法、阈值及其来源，
并编写自己的规则包。源代码、决策记录（仓库中的 `docs/umsetzung/`）和本文档均公开。

关于条款或阈值如何解读的问题以及其他反馈，请提交到公开仓库的问题跟踪系统。

!!! warning "占位"
    公开仓库的地址为 `<REPO_URL>`，将在仓库发布时填写。

## 许可证 {#licence}

代码：Apache-2.0。文档和示例数据：CC BY 4.0。报告字体：SIL 开放字体许可证 1.1。见[许可证](license.md)。
