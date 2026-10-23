# 指标 {#metrics}

规则包 `core` 评价指标 M01–M13；本页是它的来源（core 规则的条款即为指标）。对每个指标，本页说明测量什么、如何测量、
在什么对象上测量、何时无法判断、哪些规则使用它及其阈值，以及该阈值的来源。所有阈值都可以在 `neurogrid.toml`
（`[rules."ID".params]`）中覆盖。

**状态。** 无法判断的值为*无法检查*并附原因（例如数据太少）；不适用于该记录的规则为*不适用*。两者都不是工具错误：
数据从不导致退出码 2。

**来源。** *产品规格书中的起始值*：NeuroGrid 的产品规格书规定的数值。*已校准*：公开测试语料库上的第 95 百分位数，见
[校准](#calibration)。*假设*：记录在仓库决策记录 `docs/umsetzung/ENTSCHEIDUNGEN.md` 中的解读。

**依赖库。** MNE-Python 1.13.2、edfio 0.4.18、MNE-BIDS 0.20.0、BIDS 验证器 3.0.2（deno 2.9.7）、pyprep 0.9.0、
autoreject 0.5.1、python-picard 0.8.2、mne-icalabel 0.10.0 及 onnxruntime 1.31.0、numpy 2.4.6、scipy 1.17.1——全部
精确锁定版本。

## M01 可读性与文件头 {#M01}

**测量内容。** 打开每个数据文件：MNE 读取第一个和最后一个 1 秒的数据块。EDF 文件头用 edfio 检查，BDF、BrainVision
和 EEGLAB 文件头用自有解析器检查：文件大小与文件头是否一致、字段、数字格式、开始日期。伴随文件（`.eeg`、`.vmrk`、
`.fdt`、FIF 分段文件）必须是引用它的文件旁边的普通文件名；其他引用不会被打开。NeuroGrid 无法读取的格式（例如
`.cnt`、`.mff`、`.xdf`）的文件会以其（假名）文件名作为检查结果列出。

**可识别身份的文件头字段**（CORE-M01-05，提示）：EDF/EDF+ 的受试者字段和记录字段、真实的开始日期、FIF 的
`subject_info` 和 `experimenter`、EEGLAB 的 `subject` 和注释字段。只报告字段名，从不报告字段值。

<!-- BEGIN GENERATED thresholds M01 -->
| 规则 | 严重程度 | 参数 | 来源 |
|---|---|---|---|
| [CORE-M01-01](reference/rules.md#CORE-M01-01) 数据文件可读取 | 错误 | – | 产品规格书中的起始值（A-65） |
| [CORE-M01-02](reference/rules.md#CORE-M01-02) 文件头一致 | 错误 | – | 产品规格书中的起始值（A-46） |
| [CORE-M01-03](reference/rules.md#CORE-M01-03) 伴随文件和引用存在 | 错误 | – | 假设 A-46（决策记录） |
| [CORE-M01-04](reference/rules.md#CORE-M01-04) 数据文件格式受支持 | 错误 | – | 假设 A-12（决策记录） |
| [CORE-M01-05](reference/rules.md#CORE-M01-05) 文件头不含个人标识或真实日期 | 提示 | – | 假设 A-64（决策记录） |
<!-- END GENERATED -->

**局限。** 被截断的 EDF 文件仍可被 MNE 读取；它由文件头检查（文件大小与文件头比较）发现。数据嵌入 `.set` 文件中的
EEGLAB 数据集无法分块读取；报告会注明这一点。

## M02 元数据完整性 {#M02}

**测量内容。** EEG-BIDS 必填字段 `EEGReference`、`SamplingFrequency`、`PowerLineFrequency`、`SoftwareFilters` 和
`TaskName`，以及 `channels.tsv` 的 `name`、`type`、`units` 列；每个缺失字段一条检查结果（子键 = 字段名）。对
`EEGReference` 和 `PowerLineFrequency`，`n/a` 视为缺失；对 `SoftwareFilters`，`n/a` 是有效值。来源顺序：
`neurogrid.toml` > BIDS 附带文件 > 文件头。CORE-M02-02 将 `TaskName` 与任务标签比较，并检查 `BIDSVersion` 的格式和
`Name` 是否为空。

<!-- BEGIN GENERATED thresholds M02 -->
| 规则 | 严重程度 | 参数 | 来源 |
|---|---|---|---|
| [CORE-M02-01](reference/rules.md#CORE-M02-01) EEG-BIDS 必填字段已记录 | 错误 | – | 产品规格书中的起始值（A-03） |
| [CORE-M02-02](reference/rules.md#CORE-M02-02) 元数据一致（TaskName、BIDSVersion、名称） | 警告 | – | 假设 A-46（决策记录） |
<!-- END GENERATED -->

## M03 采样率 {#M03}

**测量内容。** 每条记录的采样率（最低的 EEG 采样率），按文件头中的 ASCII 字段精确计算（例如每 1.1 秒 550 个样本
= 500 Hz）。采样率不同的记录需要在 `[metadata] mixed_sampling_rates_reason` 中说明理由。BIDS 附带文件中的采样率
必须与数据的采样率相同。

<!-- BEGIN GENERATED thresholds M03 -->
| 规则 | 严重程度 | 参数 | 来源 |
|---|---|---|---|
| [CORE-M03-01](reference/rules.md#CORE-M03-01) 采样率不低于最低值 | 警告 | `min_hz` = 500（规则包） | 产品规格书中的起始值，转引自 T/GXDSL 008-2025（二手来源）（A-40） |
| [CORE-M03-02](reference/rules.md#CORE-M03-02) 采样率统一或已说明原因 | 警告 | – | 产品规格书中的起始值（A-18） |
| [CORE-M03-03](reference/rules.md#CORE-M03-03) 附带文件中的采样率与数据一致 | 警告 | – | 假设 A-46（决策记录） |
<!-- END GENERATED -->

## M04 通道组与导联 {#M04}

**测量内容。** 将通道名与 MNE 导联 `standard_1020` 和 `standard_1005` 的 10-20/10-10 名称列表比较（去掉前缀
“EEG”和 REF、AVG 等参考后缀；双极导联的两部分都是标准名称时视为标准）。`[metadata] channel_map` 可映射自定义标签。
只存在于 10-05 中的名称给出提示。另外检查：是否有电极位置、每个任务的通道组是否相同、附带文件、`channels.tsv`
和数据文件中的通道数。

<!-- BEGIN GENERATED thresholds M04 -->
| 规则 | 严重程度 | 参数 | 来源 |
|---|---|---|---|
| [CORE-M04-01](reference/rules.md#CORE-M04-01) 通道名符合 10-20/10-10 或已映射 | 错误 | – | 产品规格书中的起始值（A-18） |
| [CORE-M04-02](reference/rules.md#CORE-M04-02) 电极位置已记录 | 警告 | – | 假设 A-18（决策记录） |
| [CORE-M04-03](reference/rules.md#CORE-M04-03) 同一任务的通道组相同 | 警告 | – | 假设 A-18（决策记录） |
| [CORE-M04-04](reference/rules.md#CORE-M04-04) 通道数一致 | 警告 | – | 假设 A-46（决策记录） |
| [CORE-M04-05](reference/rules.md#CORE-M04-05) 通道名在 10-20/10-10 范围内 | 提示 | – | 假设 A-18（决策记录） |
<!-- END GENERATED -->

## M05 阻抗 {#M05}

**测量内容。** 每个 EEG 通道是否有阻抗值（BIDS `electrodes.tsv` 或 BrainVision 文件头），以及在湿电极时是否不超过
限值。电极是湿电极还是干电极只在 `neurogrid.toml`（`[metadata.defaults] electrode_type`）中记录；未记录时该限值
无法检查，干电极时不适用，因为该起始值适用于湿电极。

<!-- BEGIN GENERATED thresholds M05 -->
| 规则 | 严重程度 | 参数 | 来源 |
|---|---|---|---|
| [CORE-M05-01](reference/rules.md#CORE-M05-01) 阻抗已记录 | 警告 | – | 产品规格书中的起始值（A-83） |
| [CORE-M05-02](reference/rules.md#CORE-M05-02) 阻抗低于阈值（湿电极） | 警告 | `max_kohm` = 5（规则包） | 产品规格书中的起始值，转引自 T/GXDSL 008-2025（二手来源）（A-40） |
<!-- END GENERATED -->

## M06 坏通道 {#M06}

**测量内容。** pyprep `NoisyChannels`（`find_all_bads` 的各项判据，RANSAC 最后进行且只在有电极位置时进行）在抽样上
发现的坏 EEG 通道所占比例。抽样：在 10 个等分段的中间各取 60 秒，共 10 段；不超过 10 分钟的记录整体使用。每段先
重采样到 250 Hz，再将各段拼接（滤波不跨越拼接边界），然后在工频及其低于 125 Hz 的谐波处陷波滤波，并进行 1–100 Hz
带通滤波。M06 在这些数据上测量；随后 M09 使用去除 M06 坏通道后的平均参考。抽样情况记录在 `results.json` 和报告中。

**前提条件。** 至少 60 秒数据、至少 200 Hz、至少 16 个 EEG 通道（`[quality]` 的 `min_seconds`、`min_channels`）；
否则无法检查。

<!-- BEGIN GENERATED thresholds M06 -->
| 规则 | 严重程度 | 参数 | 来源 |
|---|---|---|---|
| [CORE-M06-01](reference/rules.md#CORE-M06-01) 坏通道比例不超过阈值 | 警告 | `max_fraction` = 0.30625（规则包） | 已校准：公开语料库中 22 个记录的第 95 百分位数（A-20, A-44） |
<!-- END GENERATED -->

## M07 工频干扰 {#M07}

**测量内容。** 对每个通道全长按 60 秒数据块计算：采用 2 秒周期汉宁窗、无重叠的 Welch 频谱；比值
P(f₀ ± 1 Hz) / P(1–40 Hz)；通道值为各数据块的中位数。f₀ 为记录的工频，否则为 50 Hz。采样率低于 2·(f₀ + 1) 时
不适用。CORE-M07-02 还会在另一工频（50/60 Hz）处测量，若后者按因子 `min_factor` 更为吻合，则给出提示。

<!-- BEGIN GENERATED thresholds M07 -->
| 规则 | 严重程度 | 参数 | 来源 |
|---|---|---|---|
| [CORE-M07-01](reference/rules.md#CORE-M07-01) 工频干扰比不超过阈值 | 警告 | `max_ratio` = 0.407669（规则包） | 已校准：公开语料库中 1050 个通道的第 95 百分位数（A-20, A-44） |
| [CORE-M07-02](reference/rules.md#CORE-M07-02) 记录的工频与数据相符 | 提示 | `min_factor` = 2.0（规则包） | 假设 A-47, A-79（决策记录） |
<!-- END GENERATED -->

## M08 平直段与削波 {#M08}

**测量内容。** 对每个通道全长按 1 秒窗口计算。平直：方差不超过最低有效位（EDF/BDF 由数字量程和物理量程得出，
BrainVision 由分辨率得出）；浮点格式（EEGLAB、FIF）中峰峰值低于 `[quality] flat_tolerance_uv`（0.1 µV）。削波：在
已知量程（EDF/BDF）时为位于量程边界的值，否则为极值处至少 `[quality] plateau_samples`（10）个相同样本的平台。
削波窗口不再同时计为平直。数值为所占时长的比例。相邻窗口合并为时间段：`results.json` 中每个通道最多保留 100 个
时间段及其数量，报告最多显示 20 个，并给出数量和总时长。

<!-- BEGIN GENERATED thresholds M08 -->
| 规则 | 严重程度 | 参数 | 来源 |
|---|---|---|---|
| [CORE-M08-01](reference/rules.md#CORE-M08-01) 平直段不超过时长的 5% | 错误 | `max_fraction` = 0.05（规则包） | 产品规格书中的起始值（A-18） |
| [CORE-M08-02](reference/rules.md#CORE-M08-02) 削波不超过时长的 5% | 错误 | `max_fraction` = 0.05（规则包） | 产品规格书中的起始值（A-18） |
<!-- END GENERATED -->

## M09 伪迹比例 {#M09}

**在 M06 的抽样上测量。** M09a：局部 autoreject（`cv=10`、`n_interpolate=[1, 4, 32]`）拒绝的 2 秒分段所占比例。
M09b：ICA 成分（picard，extended，20 个成分，`decim=4`）中最可能的 ICLabel 类别不是“brain”的比例；ICLabel 通过
onnxruntime 运行，其遥测已关闭。

**前提条件。** 与 M06 相同，另外：autoreject 需要电极位置；M09a 和 M09b 需要 M06 得出的坏通道。否则无法检查。

<!-- BEGIN GENERATED thresholds M09 -->
| 规则 | 严重程度 | 参数 | 来源 |
|---|---|---|---|
| [CORE-M09-01](reference/rules.md#CORE-M09-01) autoreject 拒绝率不超过阈值 | 警告 | `max_fraction` = 0.305083（规则包） | 已校准：公开语料库中 22 个记录的第 95 百分位数（A-20, A-44） |
| [CORE-M09-02](reference/rules.md#CORE-M09-02) 非脑源 ICA 成分比例不超过阈值 | 警告 | `max_fraction` = 0.6（规则包） | 已校准：公开语料库中 22 个记录的第 95 百分位数（A-20, A-44） |
<!-- END GENERATED -->

**局限。** 对干净数据，autoreject 常常拒绝 0 %，ICLabel 比例则取决于成分数量；两个数值都难以在不同设备之间比较。
阈值在公开语料库上校准，可以覆盖。

## M10 标注 {#M10}

**测量内容。** 标注来自 EDF+/BDF+ 标注通道、BrainVision 标记、EEGLAB 事件、FIF 标注和 BIDS `events.tsv`。κ：在网格上
（连续模式 30 秒，事件模式 1 秒；`[annotation]` 的 `mode`、`epoch_s`）计算两两之间不加权的 Cohen's κ，“无事件”是单独
的一类；将各对的平均值与 `min_kappa` 比较，最小值和最弱的一对写在详情中。代码：在词表范围内，且每个标签只对应一个
代码。空隙（仅连续模式）和每名标注者内部的重叠。只有一名标注者时 κ 不适用。

<!-- BEGIN GENERATED thresholds M10 -->
| 规则 | 严重程度 | 参数 | 来源 |
|---|---|---|---|
| [CORE-M10-01](reference/rules.md#CORE-M10-01) 标注者间一致性（Cohen κ）不低于 0.6 | 警告 | `min_kappa` = 0.6（规则包） | 产品规格书中的起始值（A-80） |
| [CORE-M10-02](reference/rules.md#CORE-M10-02) 标注代码统一且在词表内 | 警告 | – | 假设 A-17（决策记录） |
| [CORE-M10-03](reference/rules.md#CORE-M10-03) 连续标注无间隙 | 警告 | – | 假设 A-17（决策记录） |
| [CORE-M10-04](reference/rules.md#CORE-M10-04) 同一标注者的标注无重叠 | 警告 | – | 假设 A-17（决策记录） |
<!-- END GENERATED -->

## M11 类别与人口学信息 {#M11}

**测量内容。** 按 `[ai] labels` 中的标签来源（`events:<column>`、`participants:<column>` 或 `annotations`）计算各范围
（all、train、val、test）中每个类别的占比，以及每名受试者的年龄和性别是否已记录（`participants.tsv`）。年龄只以
10 岁分组出现，从不出现原始年龄。小单元格：受试者层面的表格只有在每个非空单元格至少有 5 名受试者时才显示，否则
扣留该表格，只显示其总数。

<!-- BEGIN GENERATED thresholds M11 -->
| 规则 | 严重程度 | 参数 | 来源 |
|---|---|---|---|
| [CORE-M11-01](reference/rules.md#CORE-M11-01) 每个类别不低于最小占比 | 警告 | `min_share` = 0.05（规则包） | 产品规格书中的起始值（A-81） |
| [CORE-M11-02](reference/rules.md#CORE-M11-02) 年龄和性别已记录 | 警告 | – | 产品规格书中的起始值（A-81） |
<!-- END GENERATED -->

## M12 数据划分完整性 {#M12}

**测量内容。** 每名受试者至多属于一个数据划分（`.neurogrid/splits.tsv` 或 `participants.tsv` 中的 `split` 列），
且没有重复的记录：信号哈希 NG-SIGHASH-v1（对每个 EEG 通道按 0.1 µV 取整的数值连同采样率计算 SHA-256）可发现完全
相同的记录。哈希值从不输出；检查结果只列出重复组及其（假名）记录。

<!-- BEGIN GENERATED thresholds M12 -->
| 规则 | 严重程度 | 参数 | 来源 |
|---|---|---|---|
| [CORE-M12-01](reference/rules.md#CORE-M12-01) 每名受试者只属于一个数据划分 | 错误 | – | 产品规格书中的起始值（A-81） |
| [CORE-M12-02](reference/rules.md#CORE-M12-02) 无重复记录（信号哈希） | 错误 | – | 产品规格书中的起始值（A-21） |
<!-- END GENERATED -->

**局限。** 只能发现完全相同的重复，不能发现部分重复（例如截取的记录）。

## M13 溯源 {#M13}

**测量内容。** 存在清单（`.neurogrid/manifest.json`，由 `neurogrid manifest` 写入）；文件与清单一致（已更改、新增、
缺失、类型改变、无法读取）；处理步骤和软件版本已记录（`.neurogrid/provenance.yaml`、`convert` 的处理步骤、
`dataset_description.json` 中的 `GeneratedBy`）。

<!-- BEGIN GENERATED thresholds M13 -->
| 规则 | 严重程度 | 参数 | 来源 |
|---|---|---|---|
| [CORE-M13-01](reference/rules.md#CORE-M13-01) 来源清单存在 | 警告 (--strict: 错误) | – | 产品规格书中的起始值（A-22, A-82） |
| [CORE-M13-02](reference/rules.md#CORE-M13-02) 文件与清单一致 | 错误 | – | 产品规格书中的起始值（A-82） |
| [CORE-M13-03](reference/rules.md#CORE-M13-03) 已记录处理步骤和软件版本 | 警告 | – | 假设 A-22（决策记录） |
<!-- END GENERATED -->

## M14 知情同意范围（自 0.2 版起） {#M14}

每条记录在数据划分中的用途是否在其受试者的知情同意范围内。M14 需要 NeuroVault，将随 0.2 版提供；0.1 版没有 M14
规则。

## 校准 {#calibration}

已校准的阈值是在公开测试语料库上测得数值的第 95 百分位数（numpy，线性插值）：五个格式各异的 OpenNeuro 数据集，共
22 条记录、1050 个通道。校准记录见 `src/neurogrid/rulepacks/calibration/core.json`；有测试检查该记录、规则包和检查项
默认值三者一致。

<!-- BEGIN GENERATED calibration -->
| 数据集 | 版本 | DOI | 格式 | 记录数 | 通道数（M07） |
|---|---|---|---|---|---|
| ds000248 | 1.2.4 | 10.18112/openneuro.ds000248.v1.2.4 | FIF | 1 | 60 |
| ds002778 | 1.0.5 | 10.18112/openneuro.ds002778.v1.0.5 | BDF | 5 | 200 |
| ds003775 | 1.2.1 | 10.18112/openneuro.ds003775.v1.2.1 | EDF | 8 | 512 |
| ds004148 | 1.0.1 | 10.18112/openneuro.ds004148.v1.0.1 | BrainVision | 3 | 183 |
| ds004504 | 1.0.9 | 10.18112/openneuro.ds004504.v1.0.9 | EEGLAB | 5 | 95 |
<!-- END GENERATED -->

这些数值描述的是该语料库，可能不适用于其他设备、导联或人群；请在自己的数据上检验，并在 `neurogrid.toml` 中附理由
覆盖。

## 文献 {#literature}

各方法均来自锁定版本的依赖库；其作者请求引用：

- PREP 流程（pyprep）：Bigdely-Shamlo 等，Frontiers in Neuroinformatics 9:16，2015，doi:10.3389/fninf.2015.00016。
- autoreject：Jas 等，NeuroImage 159，417–429，2017。
- ICLabel：Pion-Tonachini 等，NeuroImage，2019，doi:10.1016/j.neuroimage.2019.05.026；mne-icalabel：Li 等，
  Journal of Open Source Software，2022，doi:10.21105/joss.04484。
- picard：Ablin、Cardoso、Gramfort，IEEE Transactions on Signal Processing，2018。
- MNE-BIDS：Appelhoff 等，Journal of Open Source Software 4:1896，2019，doi:10.21105/joss.01896。
- MNE-Python：doi:10.5281/zenodo.592483。
