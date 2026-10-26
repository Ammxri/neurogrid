# 安装 {#installation}

NeuroGrid 在本地运行，有三种安装方式：离线安装包（用于无法访问互联网的计算机）、从 PyPI 安装或从源代码安装。生成
PDF 报告需要另外安装一次浏览器 Chrome Headless Shell；HTML 报告不需要它。

## 支持的平台 {#platforms}

| 平台 | 状态 |
|---|---|
| Windows 11 x64，Windows PowerShell 5.1 | 已在本地验证 |
| Windows 11 x64，PowerShell 7 | 首次 CI 运行前未验证 |
| Windows 10 x64 | 未验证 |
| glibc 2.28 及以上的 Linux x86_64：Debian 12、Ubuntu 22.04 及以上 | 首次 CI 运行前未验证 |
| Linux ARM64、macOS | 不支持 |

“未验证”表示：NeuroGrid 面向这些系统构建，但尚未记录在其上的测试运行。支持 Python 3.11–3.13；离线安装包自带
Python 3.12。

## 离线安装包 {#offline-bundle}

每个发布版本为每个平台提供一个安装包：

- `neurogrid-<version>-offline-win_amd64.zip`
- `neurogrid-<version>-offline-linux_x86_64.tar.gz`

压缩包中有一个文件夹 `neurogrid-<version>-offline-<platform>/`，内容如下：

| 部分 | 内容 |
|---|---|
| `python/` | Python 3.12（python-build-standalone） |
| `uv/` | uv 程序及其许可证 |
| `wheels/`、`requirements.lock.txt` | 全部运行时依赖包的 wheel 文件，以 SHA-256 锁定 |
| `docs/` | 本文档（中/英） |
| `tools/install_pdf_browser.py` | PDF 浏览器的安装程序（见下文） |
| `src/neurogrid-<version>.tar.gz` | 本版本的源代码 |
| `install.cmd`、`install.ps1` / `install.sh` | 安装脚本（Windows / Linux） |
| `README.txt`、`LICENSE`、`NOTICE`、`THIRD_PARTY_NOTICES.txt` | 简要说明和许可证 |
| `BUNDLE.json`、`SHA256SUMS`、`SHA256SUMS.sigstore.json` | 内容清单、校验和、发布签名 |

Chrome Headless Shell 不包含在安装包中，需要单独安装（见 [PDF 浏览器](#pdf-browser)）。

### 校验下载的文件 {#verify}

在将压缩包拷贝到目标计算机之前，先在可联网的计算机上校验签名，然后在目标计算机上校验校验和。

```bash
# 在可联网的计算机上：校验发布校验和的签名（Sigstore，cosign）
cosign verify-blob SHA256SUMS --bundle SHA256SUMS.sigstore.json \
  --certificate-identity "<REPO_URL>/.github/workflows/release.yml@refs/tags/v<version>" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
sha256sum --check --ignore-missing SHA256SUMS
```

!!! warning "占位"
    `<REPO_URL>` 是公开仓库的地址，将在仓库发布时填写。

在 Windows 上，将 `Get-FileHash -Algorithm SHA256 <file>` 的结果与 `SHA256SUMS` 中该文件的那一行进行比较。安装脚本
会再次按 `SHA256SUMS` 检查安装包中的每个文件。由同一压缩包内的脚本进行的检查只能证明文件完整，不能证明文件来自何
人；这一点由拷贝前的签名校验来证明。

### 安装 {#install}

=== "Windows"

    ```powershell
    # 解压 zip 文件，然后在解压后的文件夹中运行：
    .\install.cmd -Prefix "$env:LOCALAPPDATA\NeuroGrid\<version>"
    ```

    `install.cmd` 只为这一个进程用 Windows PowerShell 5.1 启动 `install.ps1`，不更改任何系统设置。选项：
    `-Prefix <folder>`、`-Cosign <path to cosign.exe>`、`-SkipSignatureCheck`、`-VerifyOnly`、
    `-PdfBrowserZip <zip> -PdfBrowserSha256 <hex>`。

=== "Linux"

    ```bash
    tar -xzf neurogrid-<version>-offline-linux_x86_64.tar.gz
    cd neurogrid-<version>-offline-linux_x86_64
    bash install.sh --prefix "$HOME/.local/share/neurogrid/<version>"
    ```

    选项：`--prefix <folder>`、`--cosign <path>`、`--skip-signature-check`、`--verify-only`、
    `--pdf-browser-zip <zip> --pdf-browser-sha256 <hex>`。不需要 root 权限。

如果没有 `cosign`，脚本会停止，除非在完成上文所述的联网校验后明确跳过签名校验（`-SkipSignatureCheck` /
`--skip-signature-check`）。如果有 `cosign`（用 `-Cosign` / `--cosign` 指定或在 `PATH` 中找到），脚本总会校验签名，
上述开关不能覆盖 `cosign` 的否定结果。脚本在安装目录中创建虚拟环境（预编译字节码），离线并按哈希值安装 wheel 文件，然后写入
启动程序。退出码：0 已安装，2 用法或环境问题，3 完整性问题，4 签名问题。

在 Windows 上，安装文件夹的路径必须较短：即使已启用长路径（`LongPathsEnabled`），
Windows 也无法从更长的路径启动程序或加载部分模块，因此每个已安装文件的路径都不超过 250 个字符。
安装程序接受的安装目录最多为 249 个字符减去其下最长的相对路径（`BUNDLE.json` 中记录为
`max_relative_install_path`）；安装目录更长时，安装程序在创建任何内容之前以退出码 2 停止。
NeuroGrid 0.1.0rc1 的最长相对路径为 148 个字符，因此上限为 101 个字符。默认安装目录
`%LOCALAPPDATA%\NeuroGrid\<version>` 远短于此。

Linux 安装包内置的 Python 不含 `dbm.ndbm` 模块（`_dbm`）：该模块链接 Berkeley DB（Sleepycat 许可），
因此安装包不包含它，并在 `BUNDLE.json`（`python.removed`）中记录。NeuroGrid 不使用它。

启动程序不会加入 `PATH`，请使用完整路径调用：

=== "Windows"

    ```powershell
    & "$env:LOCALAPPDATA\NeuroGrid\<version>\neurogrid.cmd" --help
    ```

=== "Linux"

    ```bash
    "$HOME/.local/share/neurogrid/<version>/bin/neurogrid" --help
    ```

卸载即删除安装目录；如已安装 PDF 浏览器，再删除其文件夹。

## PDF 浏览器 {#pdf-browser}

PDF 报告由 Chrome Headless Shell 修订版 1243（Playwright 1.63.0 使用的版本）打印。它是 Google 的构建版本，
有其自身的使用条款，因此不随 NeuroGrid 分发（D-08）。`tools/install_pdf_browser.py` 将其安装到 NeuroGrid 的文件夹中：

| | 文件夹 |
|---|---|
| Windows | `%LOCALAPPDATA%\NeuroGrid\pdf-browser` |
| Linux | `${XDG_DATA_HOME:-~/.local/share}/neurogrid/pdf-browser` |
| 任意平台 | 若设置了环境变量 `NEUROGRID_PDF_BROWSER_DIR`，则为其中的文件夹 |

NeuroGrid 只使用这个文件夹，从不使用系统中的 Chrome、Edge 或 Playwright 的浏览器缓存。

```bash
# 联网：下载锁定的压缩包（URL、大小和 SHA-256 固定写在脚本中）
python tools/install_pdf_browser.py
# 离线：先在可联网的计算机上
python tools/install_pdf_browser.py --download-only --platform win64 --out <folder>
# 再在目标计算机上，使用脚本输出的 SHA-256
python tools/install_pdf_browser.py --from-zip <zip> --sha256 <hex>
# 显示锁定的数据，或检查已安装的浏览器
python tools/install_pdf_browser.py --print-info
python tools/install_pdf_browser.py --check
```

`--platform` 为 `win64` 或 `linux64`。只接受锁定的压缩包。在离线安装包中，该脚本位于 `tools/`，用随附的 Python
运行（Windows 上为 `python\python.exe`，Linux 上为 `python/bin/python3.12`）；安装脚本也可以代为运行
（`-PdfBrowserZip`、`--pdf-browser-zip`）。从 PyPI 或源代码安装时，请从仓库的发布页面获取该脚本，其 SHA-256 列在
发布版本的 `SHA256SUMS` 中。

没有浏览器时，`neurogrid report --format pdf` 以退出码 2 结束并给出提示；`--format html` 始终可用。在 Linux 上，浏览器
需要系统库；NeuroGrid 在打印前检查这些库，并列出缺少的软件包。Debian 12、Ubuntu 22.04 和 Ubuntu 24.04 的软件包列表
见 `src/neurogrid/kernel/pdf_linux_packages.json`。

## 从 PyPI 安装 {#pypi}

!!! warning "占位"
    NeuroGrid 将由项目负责人发布到 PyPI；在此之前，发布版本记为 `<PYPI_RELEASE>`。

```bash
python -m pip install neurogrid
```

## 从源代码安装 {#source}

```bash
uv sync --locked --no-build
uv run neurogrid --help
```

`uv.lock` 以哈希值锁定每个依赖包；`--no-build` 只安装 wheel 文件，从不从源代码构建依赖包。`uv build` 构建
NeuroGrid 本身的 wheel 和源代码压缩包。

## 打开本文档 {#docs}

本文档是安装包文件夹 `docs/` 中的静态网站。在浏览器中打开 `docs/index.html` 即可阅读。搜索功能需要通过网页服务器
访问页面；请启动一个只在本机监听的本地网页服务器：

=== "Windows"

    ```powershell
    .\python\python.exe -m http.server 8000 --bind 127.0.0.1 --directory docs
    ```

=== "Linux"

    ```bash
    python/bin/python3.12 -m http.server 8000 --bind 127.0.0.1 --directory docs
    ```

然后打开 `http://127.0.0.1:8000/`。直接从磁盘打开时，搜索框处于禁用状态并显示相应提示。

这些页面不从其他计算机加载任何内容；文档构建时会对每个页面、样式表和脚本进行这项检查。只有一种情况不取决于本文档：
如果浏览器不支持 ResizeObserver 接口，主题脚本会尝试从 `unpkg.com` 加载替代脚本。
