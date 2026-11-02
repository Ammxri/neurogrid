# NeuroVault {#vault}

NeuroVault 在数据旁的 vault 文件夹中保存数据集的知情同意记录、对数据集访问情况的哈希链日志、角色登记册、保存期限、
风险登记册和个人信息保护影响评估。NeuroGrid 对其进行检查并给出警告，但不强制执行任何内容（[局限](limitations.md#neurovault)）。

NeuroGrid 不设用户账户。文件的访问权限由操作系统管理：能写入 vault 文件夹的人就能修改它。访问日志记录通过
NeuroGrid 发生的访问，并使之后对日志的修改可见；它不能阻止这些修改。

## 概览 {#overview}

| 命令 | 作用 |
|---|---|
| `neurogrid vault init [PATH]` | 创建 vault 中缺少的部分；已有部分保持不变。 |
| `neurogrid vault consent add PATH …` | 在 `consents.yaml` 中记录受试者的知情同意，并追加一个访问事件。 |
| `neurogrid vault log [PATH] --action … --objects … --purpose …` | 手动记录一次访问。 |
| `neurogrid vault log [PATH] --show` | 显示最新的条目、链头哈希值和哈希链状态。 |
| `neurogrid vault verify [PATH] [--expect-head HASH]` | 校验哈希链（完整时退出码 0，有不一致时为 1）。 |

选项和退出码：[命令](commands.md#vault)。

## vault 文件夹 {#folder}

vault 是 `neurogrid.toml` 中 `[vault] path` 指定的文件夹，相对于项目根目录（默认为数据集中的
`.neurogrid/vault`；[配置](configuration.md#consent-vault)）。其中包含：

| 文件 | 内容 |
|---|---|
| `consents.yaml` | 知情同意记录（只含受试者的假名 ID）。属于清单：`neurogrid verify` 会报告其更改。 |
| `access.jsonl` | 访问日志，每行一个事件。不属于清单：它随每次访问而增长。 |
| `access.jsonl.lock` | 所有读取或写入 vault 的 NeuroGrid 进程共用的锁文件。不属于清单。 |
| `roles.yaml` | 角色登记册（[角色](#roles)）。属于清单。 |
| `retention.yaml` | vault 中各文件的保存期限（[保存期限](#retention)）。属于清单。 |
| `risks.yaml` | 风险登记册（[风险登记册](#risks)）。属于清单。 |
| `pia/pia.zh.md`、`pia/pia.en.md` | 个人信息保护影响评估，待填写的草稿（[个人信息保护影响评估](#pia)）。属于清单。 |

缺少登记册和 PIA 文件时，`vault init` 根据模板写入它们，已有文件逐字节保持不变；由 NeuroGrid 0.2 创建的 vault 只需
再运行一次 `vault init` 即可获得这些文件。vault 路径中任何位置的链接或目录联接，以及访问日志、其锁文件、`consents.yaml`、
各登记册、`pia` 文件夹或 PIA 文件处的链接，都从不跟随：`check`、
`report --config` 和各 vault 命令以退出码 2 结束；`convert`、`scan`、`manifest` 和 `verify` 不写入事件并给出警告。
在 Linux 下，新建的 vault 文件夹权限为 0700，新建的 vault 文件为 0600；在 Windows 下沿用其所在文件夹的权限。

`neurogrid manifest` 不收录默认位置的 vault（`scan`、`manifest` 和 `verify` 在此记录）以及 `[vault] path` 处的 vault
（`check`、`convert` 和 `report` 在此记录）的访问日志及其锁文件，因此日志增长时 `verify` 和 CORE-M13-02 仍保持一致；
若较早的清单列出了默认位置的日志和锁文件，二者在比对时同样不予考虑，CORE-M13-02 还不考虑本次运行自身 vault 的日志和锁文件。

## 访问事件 {#events}

| 命令 | 事件 | vault |
|---|---|---|
| `check` | 操作 `check` | 其 `neurogrid.toml` 的 vault |
| `convert` | 操作 `convert` | 源文件夹 `neurogrid.toml` 的 vault |
| `report --config FILE` | 操作 `report` | 该 `neurogrid.toml` 的 vault，位于 `check` 对该文件使用的项目根目录下（[配置](configuration.md#configuration)） |
| `scan`、`manifest`、`verify` | 操作 `read`，不含角色、目的和批准编号 | 只用默认位置 `.neurogrid/vault` 的 vault |
| `vault consent add` | 操作 `consent_manage`，对象 `.neurogrid/vault/consents.yaml` | 其 `neurogrid.toml` 的 vault |
| `vault log` | 给定的操作 | 其 `neurogrid.toml` 的 vault |

每次运行的事件在其输出写入之后追加；它从不进入 `results.json`，因此对相同数据的两次 `check` 运行结果逐字节相同。
角色、目的和批准编号取自 `[vault]`；`check --role` 和 `vault log` 的选项优先。没有角色的自动事件不记录角色，并有
提示说明；`vault log` 必须有角色和目的。事件无法写入时（vault 被锁定或为只读、日志缺失或损坏）只给出警告，从不改变
退出码。

不作记录的有：以退出码 2 结束的运行、不带 `--config` 的 `report`、`vault init`、`vault log --show` 和
`vault verify`，以及所有不经过 NeuroGrid 的访问。

### 字段 {#fields}

| 字段 | 内容 |
|---|---|
| `format_version` | 1 |
| `seq` | 在哈希链中的位置，1、2、3…… |
| `time` | UTC，精确到秒，`YYYY-MM-DDTHH:MM:SSZ`，取自本地时钟 |
| `role` | 角色名称或姓名缩写（以字母开头，其后为字母、数字、`_`、`.` 或 `-`，最多 80 个字符），或 `null` |
| `action` | `read`、`check`、`convert`、`report`、`export` 或 `consent_manage` |
| `objects` | 1 至 1000 个相对 POSIX 路径或模式（每个最多 1024 个字符） |
| `purpose` | 最多 200 个字符，或 `null` |
| `approval_ref` | 最多 120 个字符，或 `null` |
| `tool_version` | 写入该条目的 NeuroGrid 版本 |
| `previous_hash` | 前一个条目的 `hash`；第一个条目为 64 个零 |
| `hash` | 不含 `hash` 字段的条目的 SHA-256（见下文） |

事件中不含用户名、计算机名、进程 ID 和绝对路径。对象分属两个命名空间：数据事件指向数据集——`**` 表示整个数据集，
或者是交给 `vault log` 的、相对于数据集的路径和模式；涉及 vault 文件的事件以相对于项目根目录的路径指明该文件，例如
`.neurogrid/vault/consents.yaml`。在原始文件夹中，`vault log` 的对象若指向现有文件，则以其假名文件名记录
（`rec-<8 位十六进制数字>.<扩展名>`，与 `verify` 的显示相同），文件名含通配符，或在 Windows 下仅大小写或末尾的点和
空格不同时也是如此；指向链接的对象会被拒绝。JSON 模式为
[`access_event.schema.json`](../schemas/access_event.schema.json)；与产品规格书术语的对应关系见
[数据模型](data-model.md)。

## 哈希链 {#chain}

`access.jsonl` 的每一行是一个事件，格式为按键排序的紧凑 JSON、UTF-8 文本，以 LF 结尾。事件的 `hash` 是该事件去掉
`hash` 字段后的上述 JSON 的 SHA-256（小写十六进制）。第一个事件的 `previous_hash` 为 64 个零；之后每个事件都携带
其前面最近一个格式正确的行所存储的 `hash`，因此损坏的行会被跳过，并始终作为一处不一致保留。对于编辑器和 Git 会
改变文件但不改变内容的情况，读取是宽容的：行内键的顺序和空白、文件开头的字节顺序标记、CRLF 行尾以及最后一行之后
缺少的 LF。一行最多 64 KiB。

**测试向量。** 事件

<!-- example: vault-vector -->
```json
{"action":"check","approval_ref":"EC-2026-17","format_version":1,"objects":["**"],"previous_hash":"0000000000000000000000000000000000000000000000000000000000000000","purpose":"pre-check before registration","role":"data_steward","seq":1,"time":"2026-10-29T12:00:00Z","tool_version":"0.2.0"}
```

的哈希值为 `d4eddd3715aa9f571840e293fb40e696bc3dbbf4964dcf267b39b9fa27ec2670`。

**不借助 NeuroGrid 检查。** 下面几行 Python（只用标准库）会重新计算日志中每个哈希值和每个链接，并输出链头；它们
检查哈希链，而不检查字段规则：

<!-- example: vault-check -->
```python
import hashlib
import json
import sys
from pathlib import Path

previous = "0" * 64
lines = Path(sys.argv[1]).read_bytes().removeprefix(b"\xef\xbb\xbf").split(b"\n")
for number, raw in enumerate(lines[:-1] if lines[-1] == b"" else lines, start=1):
    try:
        event = json.loads(raw.removesuffix(b"\r"))
        stored = event.pop("hash")
    except (ValueError, KeyError, AttributeError, TypeError):
        print(f"line {number}: unreadable")
        continue
    text = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != stored:
        print(f"line {number}: changed")
    if event.get("previous_hash") != previous:
        print(f"line {number}: link broken")
    previous = stored
print("head", previous)
```

## 校验日志 {#verify}

`neurogrid vault verify` 读取日志，按行、类型和可能的原因报告每处不一致，从不输出条目内容：

| 类型 | 可能的原因 |
|---|---|
| 无法读取的条目 | 该行已损坏，或由其他程序写入 |
| 条目已更改 | 条目被编辑过（其哈希值已不相符） |
| 链接断开 | 条目被删除（`seq` 跳跃）、被插入（`seq` 重复或倒退）、在重新计算哈希值后被修改，或被重新排序 |
| 哈希链未从开头开始 | 开头的条目被删除 |
| 缺少访问日志 | `access.jsonl` 被删除（退出码 1；NeuroGrid 不会自动重建它） |
| 未找到预期的链头哈希值 | 日志在末尾被截断或被整体重写（使用 `--expect-head` 时） |

**记下链头。** 请将 `vault verify`、`vault log --show` 或报告（使用 `--config` 时）输出的链头哈希值记在 vault 之外，
例如实验记录本或工单中，并在以后使用 `neurogrid vault verify --expect-head <hash>` 检查。当时记下的链头必须仍是
完整哈希链的一部分，即使之后又追加了条目也是如此。只有这样才能发现末尾截断和整体重写。

## 局限 {#limits}

- 可以发现：哈希链内条目的修改、插入、删除和重新排序。重新计算其后所有哈希值的修改属于整体重写。
- 末尾截断和整体重写只能通过 `--expect-head` 对照在别处记录的链头哈希值发现。
- 只记录通过 NeuroGrid 进行的访问：以退出码 2 结束的运行不作记录；`scan`、`manifest` 和 `verify` 只使用默认位置
  的 vault；`report` 只有在指定 `--config` 时才记录。
- 时间取自本地时钟，未经核实。
- 锁（`access.jsonl.lock`）只是协调性的：它使 NeuroGrid 进程彼此错开，但不能阻止编辑器等其他程序；它们所作的
  修改由哈希链显示出来。NeuroGrid 进程最多等待 10 秒获得锁：需要 vault 的命令此时以退出码 2 结束，只追加自身事件的
  运行给出警告，CORE-NV03-01 为无法检查。只要没有其他进程更长时间地占用锁，两次 `check` 运行就逐字节相同。
- 因断电而写到一半的行始终作为一处不一致保留；下一个条目会越过它进行链接。

## 角色 {#roles}

角色是您为访问数据的职能所取的名称（`data_steward`、`QA.lead`），或姓名缩写——绝不是人名或登录名。NeuroGrid 只
检查其格式；当角色、对象或目的看起来像人名或身份编号时会给出警告，但仍会记录。角色只作参考，不强制执行。

角色登记册 `roles.yaml` 规定哪个角色可以对哪些对象执行哪些操作。`vault init` 写入的文件包含 `roles: []`，并以注释形式
附上以下示例：

<!-- example: roles-yaml -->
```yaml
format_version: 1
roles:
  - role: data_steward
    description: Prepares, checks and converts the dataset
    actions: [read, check, convert, report, export, consent_manage]
    objects: ["**", ".neurogrid/vault/consents.yaml"]
    ethics_approval_ref: "EC-2026-17"
  - role: QA.lead
    description: Reviews the check results and the reports
    actions: [read, report]
    objects: ["**"]
```

| 字段 | 内容 |
|---|---|
| `role` | 角色名称或姓名缩写：以字母开头，后跟字母、数字、`_`、`.` 或 `-`，最多 80 个字符；每个角色只能出现一次。 |
| `description` | 1 至 200 个可打印字符。只保存在该文件中：从不出现在 `results.json`、报告或控制台中。 |
| `actions` | `read`、`check`、`convert`、`report`、`export` 和 `consent_manage` 中的 1 至 6 项，每项只能出现一次。 |
| `objects` | 1 至 100 个路径或模式（`**` 表示任意层文件夹，`*` 和 `?` 只在一个名称内匹配）：数据相对于数据集，vault 中的文件相对于项目根目录。 |
| `ethics_approval_ref` | 可选：伦理审批编号，1 至 120 个可打印字符；从不出现在输出中。 |

角色登记册最多包含 200 个角色、1,000,000 字节。事件的角色在登记册中、该角色可以执行其操作，且该角色的某个对象模式
覆盖事件的每个对象时，访问即为允许。本身就是模式的对象只被能覆盖其所有可能路径的模式覆盖：每个自动事件的对象 `**`
只被 `**` 覆盖。在原始文件夹中，访问日志以假名文件名（`rec-<sha8>.<ext>`）记录文件，因此按真实文件名编写的模式在
那里不会匹配。

CORE-NV04-01 将访问日志与登记册比较（[指标](metrics.md#NV04)）。`check`、`convert`、`report --config`、`vault log`
和 `vault consent add` 在开始时比较自身的访问；登记册不允许时给出警告，但仍记录该访问，退出码不变。没有登记册或为
`roles: []` 时不作比较。`roles.yaml` 无效时，`check` 在读取数据之前以退出码 2 结束（错误信息指出条目和字段，从不显示
值）；其他命令只给出警告。

## 保存期限 {#retention}

`retention.yaml` 为 vault 中的每个文件记录其创建日期、最低保存期限，以及可选的复核日期。`vault init` 写入的文件包含
`objects: []`，并以注释形式附上以下示例：

<!-- example: retention-yaml -->
```yaml
format_version: 1
objects:
  - object: pia
    created: 2026-11-02
    min_until: 2029-11-02
    review_at: 2029-08-01
  - object: access_log
    created: 2026-11-02
    min_until: 2029-11-02
```

| 字段 | 内容 |
|---|---|
| `object` | `pia`（个人信息保护影响评估）、`access_log`、`roles`、`risks` 或 `consents`；每个对象只能出现一次。 |
| `created` | 对象的创建日期（YYYY-MM-DD）。 |
| `min_until` | 最低保存期限：不早于 `created` 之后三年；自 2 月 29 日起算时最早为三年后的 3 月 1 日。日期更早时 `check` 以退出码 2 结束。 |
| `review_at` | 可选：介于 `created` 和 `min_until` 之间的复核日期。 |

该文件最多 100,000 字节。CORE-NV05-01 要求 `pia` 和 `access_log` 各有一个条目：NeuroGrid 将 PIPL 中关于个人信息
保护影响评估的规定理解为要求影响评估报告和处理情况记录（此处即访问日志）至少保存三年。这是 NeuroGrid 的理解，
不构成法律意见。CORE-NV05-01 还会报告文件缺失的已列出对象，以及开头条目被删除的访问日志。CORE-NV05-03 从
`min_until` 之前 90 天起（参数 `days`）以及自 `review_at` 起给出提醒。提醒措辞中立：请在自行开展法律审查后，决定
继续保存或删除。NeuroGrid 不删除任何内容，也不为 EEG 数据设定保存期限（[指标](metrics.md#NV05)）。

## 个人信息保护影响评估 {#pia}

`vault init` 以两份草稿写入个人信息保护影响评估：`pia/pia.zh.md` 和 `pia/pia.en.md`。每份的第一行都注明它是占位
文本，不构成法律意见。草稿包含 PIPL 要求开展个人信息保护影响评估的情形的检查清单、作为标题的评估要点以及待填写的
字段，每个字段都带有占位标记（中文文件为【待填写】，英文文件为 `[to be completed]`）。模板以 NeuroGrid 自己的语言转述
相关规定并注明条文；其中不含任何法律依据，也不含任何评估结论。模板在首次实际使用前，由在中华人民共和国获准执业的
法律顾问审核；该审核不是 NeuroGrid 发布的前提条件。

CORE-NV05-02 报告以下情况：vault 中没有 PIA 文件；PIA 文件仍是未经编辑的模板（字节顺序标记和 CRLF 换行符除外）；
已编辑的文件中仍留有占位标记。只要有一个已编辑且不含占位标记的文件即可。NeuroGrid 不评判其内容，也从不将其写入任何
输出。

## 风险登记册 {#risks}

风险登记册 `risks.yaml` 列出在取得知情同意之后发现的风险：受影响的用途，以及从哪个知情同意版本起该风险被覆盖。
`vault init` 写入的文件包含 `risks: []`，并以注释形式附上以下示例：

<!-- example: risks-yaml -->
```yaml
format_version: 1
risks:
  - id: R-2026-01
    date: 2026-09-01
    description: The recordings are also used to train a second model
    affected_uses: [training, sharing]
    min_consent_version: 2
```

| 字段 | 内容 |
|---|---|
| `id` | 以字母开头，后跟字母、数字、`_`、`.` 或 `-`，最多 40 个字符；每个 ID 只能出现一次。 |
| `date` | 记录该风险的日期（YYYY-MM-DD）。 |
| `description` | 1 至 500 个可打印字符。只保存在该文件中：从不出现在 `results.json`、报告、导出或控制台中。 |
| `affected_uses` | `training`、`validation`、`publication`、`sharing` 和 `commercial` 中的 1 至 5 项，每项只能出现一次。 |
| `min_consent_version` | 从该知情同意版本起，知情同意覆盖该风险（1 至 1,000,000）。 |

风险登记册最多包含 1,000 项风险、1,000,000 字节；当有规则读取它时，无效的文件会使 `check` 以退出码 2 结束。读取它的
重新取得知情同意检查在 M14 中说明（[指标](metrics.md#M14)）。

## 检查 {#checks}

规则包 `core` 用 CORE-NV03-01（哈希链完整，错误）和 CORE-NV03-02（访问日志可写入，警告）检查日志：
[指标](metrics.md#NV03)。CORE-NV04-01 将日志与角色登记册比较（警告），CORE-NV05-01 和 CORE-NV05-02 检查保存期限和
个人信息保护影响评估（警告），CORE-NV05-03 提醒最低保存期限即将结束（信息）：[指标](metrics.md#NV04)、
[指标](metrics.md#NV05)。
