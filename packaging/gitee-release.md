# NeuroGrid {{version}}

使用 NeuroGrid 进行的预检。不构成国家药品监督管理局（NMPA）法规意义上的符合性评价。

Pre-check with NeuroGrid. Not a conformity assessment within the meaning of NMPA regulations.

本发布与 GitHub 发布相同 / This release is the same as the GitHub release: {{github_release}}

## Files / 文件

| File | Content |
|---|---|
| `neurogrid-{{version}}-py3-none-any.whl`, `neurogrid-{{version}}.tar.gz` | Wheel and source distribution |
| `SHA256SUMS`, `SHA256SUMS.sigstore.json` | Checksums of all release files and their keyless Sigstore signature |

离线安装包、说明文档和 PDF 浏览器安装程序见 GitHub 发布 / The offline bundles, the documentation and the PDF browser
installer are on the GitHub release.

## Verify before use / 使用前核验

```
cosign verify-blob SHA256SUMS --bundle SHA256SUMS.sigstore.json --certificate-identity {{identity}} --certificate-oidc-issuer https://token.actions.githubusercontent.com
sha256sum --check --ignore-missing SHA256SUMS
```

签名者身份必须与 GitHub 发布说明中的身份一致 / The signer identity must equal the one in the GitHub release notes:
`{{identity}}`
