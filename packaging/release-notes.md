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

Each offline bundle also carries its own signed `SHA256SUMS`. Its installer checks every file and stops unless the
signature was verified with cosign or `-SkipSignatureCheck` / `--skip-signature-check` confirms the check above.
每个离线安装包都带有自己的已签名 `SHA256SUMS`；安装脚本逐一核对文件，未核验签名时需明确加上跳过参数。

## Install / 安装

- Offline / 离线：`README.txt` in the bundle and `docs/installation.html`.
- Source / 源代码：https://github.com/{{repository}}/tree/v{{version}}

## Known limits / 已知限制

- Not verified / 未经验证：Windows 10; Linux distributions other than Debian 12 and Ubuntu 22.04+.
- PDF reports need the separate Chrome Headless Shell (`install_pdf_browser.py`) and, on Linux, system libraries.
- Operating system services such as virus scanners or cloud sync are not controlled by NeuroGrid.
