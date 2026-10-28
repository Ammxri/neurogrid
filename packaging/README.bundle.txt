NeuroGrid {{version}} - 离线安装包 / offline bundle ({{platform}})

使用 NeuroGrid 进行的预检。不构成国家药品监督管理局（NMPA）法规意义上的符合性评价。
Pre-check with NeuroGrid. Not a conformity assessment within the meaning of NMPA regulations.

本安装包无需联网，也无需预装 Python。结果只保存在本机，写入 --out 指定的位置；未指定 --out 时，check 写入当前
文件夹中的 results.json，report 写入 results.json 所在的文件夹，manifest 写入数据集中的 .neurogrid/manifest.json。
不会上传任何数据。
This bundle needs neither network nor a preinstalled Python. Results stay on this computer: they are written
where --out points; without --out, check writes results.json in the current folder, report writes next to
results.json and manifest writes .neurogrid/manifest.json inside the dataset. Nothing is uploaded.

1. 传输前在联网电脑上核验签名（一行命令）/ Before the transfer, verify the signature on a connected machine (one
   command line):
     cosign verify-blob SHA256SUMS --bundle SHA256SUMS.sigstore.json --certificate-identity {{identity}} --certificate-oidc-issuer https://token.actions.githubusercontent.com
   签名者身份为 "-" 表示未签名的开发版本 / a signer identity "-" means an unsigned development build.
   请先将此签名者身份与项目发布页面（https://github.com/Ammxri/neurogrid/releases）发布说明中的身份核对：本文件和
   安装包中写明的身份可能随安装包一起被改动，单独不能证明来源。安装程序核验后也会显示该身份。
   First compare this signer identity with the one in the release notes on the project's release page
   (https://github.com/Ammxri/neurogrid/releases): the identity written here and in the bundle can be changed
   together with the bundle, so on its own it proves nothing. The installer shows it again after verifying.

2. Windows 10/11 x64，在 PowerShell 中、于解压后的文件夹内 / in PowerShell, in the unpacked folder:
     .\install.cmd -SkipSignatureCheck          签名已在联网电脑上核验 / signature verified on a connected machine
     .\install.cmd -Cosign C:\path\cosign.exe   在本机核验 / verify on this machine
     & "$env:LOCALAPPDATA\NeuroGrid\{{version}}\neurogrid.cmd" check <数据集 / dataset> --out results.json
     & "$env:LOCALAPPDATA\NeuroGrid\{{version}}\neurogrid.cmd" report results.json --lang "zh,en" --format html
   在 cmd.exe 中去掉 ".\" 和 "& "，并写 %LOCALAPPDATA% / in cmd.exe drop ".\" and "& " and write %LOCALAPPDATA%.
   安装程序本身用 Windows PowerShell 5.1 运行 / the installer itself runs with Windows PowerShell 5.1.
   安装文件夹路径须较短，安装程序会给出上限 / the install folder path must be short; the installer names the limit.

3. Linux x86_64, glibc >= 2.28 (Debian 12, Ubuntu 22.04+):
     ./install.sh --skip-signature-check
     ~/.local/share/neurogrid/{{version}}/bin/neurogrid check <数据集 / dataset> --out results.json
   内置 Python 不含 dbm.ndbm 模块（_dbm，Berkeley DB 许可，见 BUNDLE.json）；NeuroGrid 不使用它。
   The bundled Python lacks the dbm.ndbm module (_dbm, Berkeley DB licence, see BUNDLE.json); NeuroGrid does
   not use it.

4. PDF 报告（可选）需要单独的 PDF 浏览器，它不在本安装包内 / PDF reports (optional) need a separate PDF browser,
   which is not part of this bundle:
     .\install.cmd -PdfBrowserZip <zip> -PdfBrowserSha256 <hex>
     ./install.sh --pdf-browser-zip <zip> --pdf-browser-sha256 <hex>

5. 卸载：删除安装文件夹；若装过 PDF 浏览器，另删其文件夹（%LOCALAPPDATA%\NeuroGrid\pdf-browser 或
   ~/.local/share/neurogrid/pdf-browser）。移动文件夹会使安装失效，请重新安装。
   Uninstall: delete the install folder and, if the PDF browser was installed, its folder
   (%LOCALAPPDATA%\NeuroGrid\pdf-browser or ~/.local/share/neurogrid/pdf-browser). Moving the install folder
   breaks the installation; reinstall instead.

文档 / Documentation: docs/index.html (中文: docs/zh/index.html)
许可 / Licences: LICENSE, NOTICE, THIRD_PARTY_NOTICES.txt - 源代码 / source code: src/neurogrid-{{version}}.tar.gz
平台 / Platforms: Windows 11 已在本地验证。离线安装包已在 CI 中于 Windows Server（Windows PowerShell 5.1 和
PowerShell 7）、Debian 12、Ubuntu 22.04 和 Ubuntu 24.04 上验证，测试套件已在 CI 中用 Python 3.11–3.13 于
Windows Server 和 Ubuntu 24.04 上验证；CI 不在 Debian 12 和 Ubuntu 22.04 上运行测试套件。Windows 10、Windows 11
上的 PowerShell 7 以及 24.04 之后的 Ubuntu 版本未验证；其他 Linux 发行版和 ARM64 不受支持。
Windows 11 is verified locally. In the CI the offline bundle is verified on Windows Server (Windows PowerShell 5.1
and PowerShell 7), Debian 12, Ubuntu 22.04 and Ubuntu 24.04, and the test suite with Python 3.11–3.13 on Windows
Server and Ubuntu 24.04; the CI does not run the test suite on Debian 12 and Ubuntu 22.04. Windows 10, PowerShell 7
on Windows 11 and Ubuntu releases after 24.04 are not verified; other Linux distributions and ARM64 are not
supported.
签名者身份 / Signer identity: {{identity}}
