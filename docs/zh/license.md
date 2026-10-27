# 许可证 {#licences}

| 部分 | 许可证 |
|---|---|
| 源代码、工具、配置 | Apache License 2.0（`LICENSE`、`NOTICE`） |
| 文档文本（本网站页面的文字、README、DATA_SOURCES）和合成示例数据 | 知识共享署名 4.0 国际许可协议（CC BY 4.0），https://creativecommons.org/licenses/by/4.0/ |
| 报告字体（Noto Sans SC 静态字重） | SIL 开放字体许可证 1.1（`src/neurogrid/report/fonts/OFL.txt`） |
| 本文档网站的主题、脚本、图标和字体 | 各自的许可证，见[下文](#docs-site) |
| `THIRD_PARTY_NOTICES.txt` | NeuroGrid 自己的文字为 CC BY 4.0；其中转载的许可证文本和声明保留各自的条款 |

仓库中的 `REUSE.toml` 列出每个文件的许可证；许可证文本位于 `LICENSES/`。由于 wheel 包含报告字体，其声明的许可证为
`Apache-2.0 AND OFL-1.1`。

## 第三方组件 {#third-party}

`THIRD_PARTY_NOTICES.txt` 列出 NeuroGrid 在 Windows 和 Linux 上依赖的每个软件包，以及这些软件包中的本机库和其他组件
（例如 numpy 和 scipy 中的 OpenBLAS 和 GCC 运行时库、deno 运行时和 BIDS 验证器包），附其许可证和许可证文本。它由
`tools/notices.py` 根据锁定的软件包生成，随每个发布版本和离线安装包提供。已知的缺漏在文件中写明，并在正式发布前补齐。

公开测试语料库中的数据集及其许可证列于 `DATA_SOURCES.md`。

## 本文档网站 {#docs-site}

CC BY 4.0 适用于本网站页面中 NeuroGrid 自己的文字。网站使用主题 mkdocs-material（MIT）构建，其文件保留各自的
许可证：

| 部分 | 许可证 |
|---|---|
| mkdocs-material：页面模板、样式表、脚本、网站图标 | MIT |
| 其脚本包中的 rxjs、tslib、clipboard、escape-html、focus-visible | Apache-2.0、0BSD、MIT、MIT、W3C 软件和文档许可证（W3C Software and Document License） |
| 其搜索中的 lunr | MIT |
| 其样式表中的配色 material-design-color | MIT |
| 图标：Material Design Icons、Octicons、Font Awesome Free | Apache-2.0、MIT、CC BY 4.0 |
| 中文字符：Noto Sans SC 的子集 | SIL 开放字体许可证 1.1 |

`THIRD_PARTY_NOTICES.txt` 列出每个部分的版权声明和许可证文本。随附文件未写明许可证的两个部分 focus-visible 和
material-design-color，其许可证文本取自各自的项目；focus-visible 未写明版权人，因此该文件改为注明其代码仓库。
搜索的语言文件（lunr-languages，采用 Mozilla 公共许可证）不属于本网站：本文档的搜索不使用它们。

## 不分发的组件 {#not-distributed}

用于打印 PDF 报告的 Chrome Headless Shell 不属于 NeuroGrid，也不包含在离线安装包中。您需要按 Google 的条款，用
`tools/install_pdf_browser.py` 自行安装（[安装](installation.md#pdf-browser)）。
