# 隐私与离线运行 {#privacy}

NeuroGrid 在本地运行。它不含网络代码，不上传、不传输任何内容；它只把您要求的文件（结果、报告、清单、转换后的
数据集）写到您指定的位置。

## 不使用网络 {#offline}

| 部分 | 保护措施 |
|---|---|
| NeuroGrid 的 Python 进程 | 审计钩子阻止并记录所有指向非回环地址的套接字连接、数据报和名称解析。它只作用于该 Python 进程。 |
| BIDS 验证器（deno） | 以 `--deny-net` 和 `DENO_NO_UPDATE_CHECK=1` 启动，只能读取数据集、只能写入其输出文件。 |
| PDF 浏览器（Chrome Headless Shell） | 固定参数关闭后台联网、组件更新、崩溃报告和 ping；除报告文件和 `data:` 外的所有请求都被中止；HTML 带有不加载任何资源的内容安全策略。 |
| ICLabel（onnxruntime） | 在第一次会话之前关闭其遥测。 |

PDF 打印使用 Playwright，其同步接口会在 NeuroGrid 进程内运行一个 asyncio 循环；在 Windows 上，该循环通过一对回环
套接字与自身通信。审计钩子只允许这一回环连接，其余一律阻止。

**NeuroGrid 无法控制的部分。** 操作系统的服务——检查文件的杀毒软件、文件夹的云同步、系统更新——不在 NeuroGrid 的
控制范围内。如有需要，请将数据集放在不进行同步的文件夹中。

## 输出中包含什么 {#outputs}

- 只读取列出的文件头字段；对于可识别身份的文件头字段（EDF 的受试者字段和记录字段、真实日期、FIF 的受试者信息、
  EEGLAB 注释），只报告字段名，从不报告字段值。
- 在原始数据文件夹中，记录获得假名 ID（`rec-<8 位十六进制数>` 或 `neurogrid.toml` 中的映射）；数据集根目录显示为
  `<dataset>`，用户主文件夹显示为 `~`。`--show-paths` 显示真实名称——只在允许出现真实名称的场合使用。
- 控制台显示本机路径时，用户主文件夹显示为 `~`，登录名和计算机名显示为 `<user>` 和 `<host>`，在用户主文件夹之外也是如此
  （例如 U 盘上的输出：`/media/<user>/…`）。
- NeuroGrid 不对数据做假名化处理：ID 和文件名来自输入。`convert --strip-identifying-headers` 会在转换后的副本中把
  可识别身份的文件头字段替换为占位值。
- 人口学信息和类别标签只以汇总形式出现；受试者层面的表格中若有非空单元格少于 5 名受试者，则扣留该表格。
- 任何输出中都没有原始信号、信号哈希值和原始年龄。
- 没有用户账户，也没有日志文件。文件的访问权限由操作系统的权限管理。
- 每次运行在其输出旁边使用独立的工作文件夹，并在结束时删除。PDF 浏览器的工作文件夹则位于本机的临时文件夹中
  （Windows 限制其路径长度），同样在结束时删除。某次运行被强行终止而未能删除的工作文件夹，会由下一次在同一位置
  工作的运行删除。

## 自行验证 {#check-yourself}

您不必只相信这些说明：源代码是公开的，离线行为可以在您自己的计算机上验证。

- **从源代码构建。** `uv sync --locked --no-build` 只安装锁定的 wheel 文件；`uv build` 构建 NeuroGrid 的 wheel 和
  源代码压缩包。每个发布版本也附带其源代码压缩包。
- **下载的文件。** 用 `SHA256SUMS` 比对发布文件，并校验其签名（[安装](installation.md#verify)）。
- **Linux，无网络。** 在没有网络的容器中运行，例如对已安装的安装包使用
  `docker run --rm --network none -v "$PWD:/data:ro" <image>`，或以 root 权限执行 `sudo unshare -n`，再以自己的用户
  身份运行命令。
- **Linux，系统调用。**
  `strace -f -e trace=connect,sendto,sendmsg -o strace-check.txt neurogrid check <dataset>` 记录 NeuroGrid
  及其子进程的每次连接尝试。记录中不得出现指向回环地址（127.0.0.0/8、`::1`）以外地址的 `AF_INET` 或 `AF_INET6`
  调用；回环调用是允许的（PDF 步骤通过回环与其自己的浏览器进程通信），但回环地址的端口 9 除外：失效的代理（例如
  `http://127.0.0.1:9`）指向该端口，向其发送请求的程序实际上是在尝试访问网络。源代码仓库中的
  `python3 tools/strace_check.py <folder>` 对该文件夹中的每个 `strace-*.txt` 文件应用完全相同的规则，并列出其统计的
  回环调用。
- **Windows。** 为每个程序设置出站防火墙规则，例如
  `New-NetFirewallRule -Direction Outbound -Action Block -Program <path of neurogrid.exe>`，并对 `python.exe`、
  `deno.exe`、Playwright 的 `node.exe` 和 PDF 浏览器做同样设置。
- **决策。** 决策记录和需求矩阵是仓库的一部分（`docs/umsetzung/`）。

| 证据 | 状态 |
|---|---|
| 源代码中的审计钩子和网络禁令（测试） | 已在本地验证 |
| 无网络和 `strace` 下的 Linux 运行 | 首次 CI 运行前未验证 |
| Windows 防火墙测试 | 未验证（它会更改计算机的安全设置） |
