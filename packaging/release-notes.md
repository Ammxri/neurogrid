# NeuroGrid {{version}}

使用 NeuroGrid 进行的预检。不构成国家药品监督管理局（NMPA）法规意义上的符合性评价。

Pre-check with NeuroGrid. Not a conformity assessment within the meaning of NMPA regulations.

> Draft written by the release workflow. The project owner reviews and edits it before publishing it.
> 本说明由发布流程生成草稿，由项目负责人审阅后发布。

## Files / 文件

| File | Content |
|---|---|
| `neurogrid-{{version}}-offline-win_amd64.zip` | Offline bundle for Windows 10/11 x64: interpreter, uv, wheels, documentation, notices, installer |
| `neurogrid-{{version}}-offline-linux_x86_64.tar.gz` | Offline bundle for Linux x86_64 with glibc 2.28 or newer |
| `neurogrid-{{version}}-py3-none-any.whl`, `neurogrid-{{version}}.tar.gz` | Wheel and source distribution |
| `THIRD_PARTY_NOTICES.txt` | Licences of every redistributed component |
| `install_pdf_browser.py` | Installer of the separate PDF browser (Chrome Headless Shell; not distributed by NeuroGrid) |
| `SHA256SUMS`, `SHA256SUMS.sigstore.json` | Checksums of all files and their keyless Sigstore signature |

## Verify before use / 使用前核验

On a connected machine / 在联网电脑上：

```
cosign verify-blob SHA256SUMS --bundle SHA256SUMS.sigstore.json \
  --certificate-identity {{identity}} \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
sha256sum --check --ignore-missing SHA256SUMS
```

Windows: `(Get-FileHash <file> -Algorithm SHA256).Hash.ToLower()` must equal the line in `SHA256SUMS`.

Signer identity / 签名者身份：`{{identity}}`. The installers print the identity they verified
(`signature verified: …`) and each bundle's `README.txt` names it; both must equal this one, which this release
page publishes outside the archive. 安装程序在核验后显示的身份以及安装包 `README.txt` 中写明的身份都必须与此处一致；
只有本发布页面上的身份在安装包之外公布。

Each offline bundle also carries its own signed `SHA256SUMS`. Its installer checks every file and stops unless the
signature was verified with cosign or `-SkipSignatureCheck` / `--skip-signature-check` confirms the check above.
每个离线安装包都带有自己的已签名 `SHA256SUMS`；安装脚本逐一核对文件，未核验签名时需明确加上跳过参数。

## Install / 安装

- Offline / 离线：`README.txt` in the bundle and `docs/installation.html`.
- Source / 源代码：https://github.com/{{repository}}/tree/v{{version}}

## Known limits / 已知限制

- Platforms: Windows 11 is verified locally. In the CI the offline bundle is verified on Windows Server (Windows
  PowerShell 5.1 and PowerShell 7), Debian 12, Ubuntu 22.04 and Ubuntu 24.04; the test suite on Linux and on the
  Windows runner is not yet verified. Windows 10, PowerShell 7 on Windows 11 and Ubuntu releases after 24.04 are
  not verified; other Linux distributions and ARM64 are not supported.
  / 平台：Windows 11 已在本地验证。离线安装包已在 CI 中于 Windows Server（Windows PowerShell 5.1 和 PowerShell 7）、
  Debian 12、Ubuntu 22.04 和 Ubuntu 24.04 上验证；Linux 和 Windows 运行器上的测试套件尚未验证。
  Windows 10、Windows 11 上的 PowerShell 7 以及 24.04 之后的 Ubuntu 版本未验证；其他 Linux 发行版和 ARM64 不受支持。
- PDF reports need the separate Chrome Headless Shell (`install_pdf_browser.py`) and, on Linux, system libraries.
- Linux bundle: the bundled Python lacks the `dbm.ndbm` module (`_dbm`, Berkeley DB licence; recorded in
  `BUNDLE.json`); NeuroGrid does not use it. / Linux 安装包内置的 Python 不含 `dbm.ndbm` 模块（`_dbm`）。
- Windows: the install folder path must be short (Windows limits paths of programs and of some modules even with
  long paths enabled); the installer names the limit. / Windows：安装文件夹路径须较短，安装程序会给出上限。
- Operating system services such as virus scanners or cloud sync are not controlled by NeuroGrid.
