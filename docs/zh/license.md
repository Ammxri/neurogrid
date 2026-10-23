# 许可证 {#licences}

| 部分 | 许可证 |
|---|---|
| 源代码、工具、配置 | Apache License 2.0（`LICENSE`、`NOTICE`） |
| 文档（本网站、README、DATA_SOURCES）和合成示例数据 | 知识共享署名 4.0 国际许可协议（CC BY 4.0），https://creativecommons.org/licenses/by/4.0/ |
| 报告字体（Noto Sans SC 静态字重） | SIL 开放字体许可证 1.1（`src/neurogrid/report/fonts/OFL.txt`） |

仓库中的 `REUSE.toml` 列出每个文件的许可证；许可证文本位于 `LICENSES/`。由于 wheel 包含报告字体，其声明的许可证为
`Apache-2.0 AND OFL-1.1`。

## 第三方组件 {#third-party}

`THIRD_PARTY_NOTICES.txt` 列出 NeuroGrid 在 Windows 和 Linux 上依赖的每个软件包，以及这些软件包中的本机库和其他组件
（例如 numpy 和 scipy 中的 OpenBLAS 和 GCC 运行时库、deno 运行时和 BIDS 验证器包），附其许可证和许可证文本。它由
`tools/notices.py` 根据锁定的软件包生成，随每个发布版本和离线安装包提供。已知的缺漏在文件中写明，并在正式发布前补齐。

公开测试语料库中的数据集及其许可证列于 `DATA_SOURCES.md`。

## 不分发的组件 {#not-distributed}

用于打印 PDF 报告的 Chrome Headless Shell 不属于 NeuroGrid，也不包含在离线安装包中。您需要按 Google 的条款，用
`tools/install_pdf_browser.py` 自行安装（[安装](installation.md#pdf-browser)）。
