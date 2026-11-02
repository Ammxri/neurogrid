# NeuroVault {#vault}

NeuroVault 在数据旁的 vault 文件夹中保存数据集的知情同意记录，以及对数据集访问情况的哈希链日志。0.2 版包含 vault
文件夹、知情同意记录、访问日志及其检查；角色登记册、保存期限、影响评估和导出将在以后的版本中提供
（[局限](limitations.md#neurovault)）。

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
| `neurogrid vault export [PATH] --report FILE --out FILE.zip` | 为检查写出检查包：一个包含五个组成部分和 `index.json` 的 ZIP（[检查包](#export)）。 |

选项和退出码：[命令](commands.md#vault)。

## vault 文件夹 {#folder}

vault 是 `neurogrid.toml` 中 `[vault] path` 指定的文件夹，相对于项目根目录（默认为数据集中的
`.neurogrid/vault`；[配置](configuration.md#consent-vault)）。其中包含：

| 文件 | 内容 |
|---|---|
| `consents.yaml` | 知情同意记录（只含受试者的假名 ID）。属于清单：`neurogrid verify` 会报告其更改。 |
| `access.jsonl` | 访问日志，每行一个事件。不属于清单：它随每次访问而增长。 |
| `access.jsonl.lock` | 所有读取或写入 vault 的 NeuroGrid 进程共用的锁文件。不属于清单。 |

vault 路径中任何位置的链接或目录联接，以及访问日志、其锁文件或 `consents.yaml` 处的链接，都从不跟随：`check`、
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
| `vault export` | 操作 `export`；对象：位于数据集内时的清单、`access.jsonl`、`roles.yaml` 和个人信息保护影响评估文件 | 其 `neurogrid.toml` 的 vault |

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

## 检查包 {#export}

`neurogrid vault export` 为检查写出一个 ZIP（[命令](commands.md#vault-export)）。它按以下顺序恰好包含这些文件，
别无其他：

| 成员 | 内容 |
|---|---|
| `manifest.json` | 数据集的清单（或 `--manifest`）。在原始数据文件夹中且不使用 `--show-paths` 时，为一份以假名 ID 命名数据文件的副本（`rec-<sha8>.<ext>`，与 `verify` 的显示相同；NeuroGrid 自己在 `.neurogrid/` 中的文件以明文显示）；其 `manifest_hash` 保持原存储值，即报告显示的值，因此与副本不再一致。BIDS 数据集和 `--show-paths` 保持文件原样。 |
| `access.jsonl` | 到导出事件为止（含该事件）的访问日志。 |
| `roles.yaml` | 原样的角色登记册。 |
| `pia/pia.zh.md`、`pia/pia.en.md` | 存在的个人信息保护影响评估文件（至少一份）。 |
| `report/report.<lang>.html`、`report/report.<lang>.pdf`、`report/dossier.pdf` | 用 `--report` 给出的报告（1 至 5 份，每种一次）。 |
| `index.json` | 其他每个成员及其 SHA-256 和大小、清单哈希值、导出日志的链头哈希值、条目数和哈希链状态、固定声明以及 NeuroGrid 版本（[输出文件](reference/outputs.md#export-zip)）。 |

检查包中从不包含：知情同意记录 `consents.yaml`、风险登记册 `risks.yaml`、保存期限 `retention.yaml`、`results.json`
以及任何数据文件——不含信号，也不含知情同意数据。只打包普通文件；vault 中的链接从不跟随（退出码 2），缺失的组成部分、
不是普通文件或不是 NeuroGrid 报告的文件在写出任何内容之前即被拒绝。

导出事件先于打包：所有内容先读取并检查，然后在 vault 锁下追加事件 `export`，日志打包到该事件为止（含该事件），因此
`index.json` 中的链头哈希值就是该事件的哈希值。请在 vault 之外记下它；以后用 `neurogrid vault verify --expect-head <hash>`
可以确认日志仍含有导出的条目。断裂的哈希链按原样导出并予以指明：`index.json` 记录其状态，控制台给出警告。事件之后
若无法写出检查包，日志保留这次尝试，`--out` 不变。ZIP 中每个条目都有固定时间（1980-01-01）和普通文件的模式；在同一台
计算机上，相同的文件和相同的时钟得到相同的归档。

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
检查其格式；当角色、对象或目的看起来像人名或身份编号时会给出警告，但仍会记录。角色只作参考，不强制执行；角色登记册
将在以后的版本中提供。

## 检查 {#checks}

规则包 `core` 用 CORE-NV03-01（哈希链完整，错误）和 CORE-NV03-02（访问日志可写入，警告）检查日志：
[指标](metrics.md#NV03)。
