# NeuroGrid offline installer for Windows 10/11 x64 (Windows PowerShell 5.1 and PowerShell 7; UF-08, A-26, D-08,
# D-10 g). It runs before any Python exists, so its messages are bilingual inline (zh / en). Nothing is downloaded:
# uv runs with UV_OFFLINE=1, --no-index and --require-hashes. No PATH, registry or profile change; uninstall =
# delete the install folder (and the PDF browser folder, if one was installed).
# Exit codes: 0 installed (or verified with -VerifyOnly), 2 usage or environment error, 3 integrity error
# (SHA256SUMS), 4 signature error.
[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$Prefix = '',
    [string]$Cosign = '',
    [switch]$SkipSignatureCheck,
    [switch]$VerifyOnly,
    [string]$PdfBrowserZip = '',
    [string]$PdfBrowserSha256 = '',
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$Unknown
)
$ErrorActionPreference = 'Stop'
$consoleEncoding = [Console]::OutputEncoding
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false } catch { }
# The variables set for uv below are restored at the end, also when the script runs inside an open session.
$savedEnvironment = @{}
foreach ($name in 'UV_OFFLINE', 'UV_NO_CONFIG', 'UV_PYTHON_DOWNLOADS', 'UV_NO_PROGRESS', 'UV_CACHE_DIR', 'PYTHONIOENCODING') {
    $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
$Bundle = $PSScriptRoot
$Issuer = 'https://token.actions.githubusercontent.com'

function Say([string]$zh, [string]$en) { [Console]::Out.WriteLine("$zh / $en") }
function Fail([int]$code, [string]$zh, [string]$en) {
    [Console]::Error.WriteLine("错误 / Error: $zh / $en")
    exit $code
}
function Invoke-Native([string]$exe, [string[]]$arguments, [switch]$Quiet) {
    # Native stderr reaches the console as it is; under 'Stop' Windows PowerShell 5.1 could turn it into an error.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        if ($Quiet) { & $exe @arguments | Out-Null } else { & $exe @arguments | Out-Host }
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
}

try {
    if ($Unknown) { Fail 2 "未知参数：$($Unknown -join ' ')" "unknown option: $($Unknown -join ' ')" }
    $infoPath = Join-Path $Bundle 'BUNDLE.json'
    if (-not (Test-Path -LiteralPath $infoPath -PathType Leaf)) { Fail 3 '缺少 BUNDLE.json' 'BUNDLE.json missing' }
    $info = [System.IO.File]::ReadAllText($infoPath, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
    $version = [string]$info.version
    if ($info.platform -ne 'win_amd64' -or $version -notmatch '^[A-Za-z0-9.+-]+$') {
        Fail 2 '此安装包不适用于 Windows x64' 'this bundle is not for Windows x64'
    }
    if ($PdfBrowserZip -or $PdfBrowserSha256) {
        if (-not $PdfBrowserZip -or $PdfBrowserSha256 -notmatch '^[0-9a-fA-F]{64}$') {
            Fail 2 '-PdfBrowserZip 须与 -PdfBrowserSha256（64 位十六进制）同时使用' '-PdfBrowserZip needs -PdfBrowserSha256 (64 hex digits)'
        }
        if (-not (Test-Path -LiteralPath $PdfBrowserZip -PathType Leaf)) { Fail 2 "找不到文件：$PdfBrowserZip" "file not found: $PdfBrowserZip" }
        $PdfBrowserZip = (Resolve-Path -LiteralPath $PdfBrowserZip).ProviderPath
    }

    # 1. Integrity: every listed file present with its SHA-256, no unlisted file (SHA256SUMS, GNU coreutils format).
    $sumsPath = Join-Path $Bundle 'SHA256SUMS'
    if (-not (Test-Path -LiteralPath $sumsPath -PathType Leaf)) { Fail 3 '缺少 SHA256SUMS' 'SHA256SUMS missing' }
    $listed = @{}
    foreach ($line in [System.IO.File]::ReadAllLines($sumsPath, [System.Text.Encoding]::UTF8)) {
        if ($line -cnotmatch '^([0-9a-f]{64})  ([A-Za-z0-9._+/-]+)$') { Fail 3 "SHA256SUMS 格式错误：$line" "malformed SHA256SUMS line: $line" }
        $digest = $Matches[1]
        $rel = $Matches[2]
        if ($rel -match '(^|/)\.\.?(/|$)') { Fail 3 "SHA256SUMS 格式错误：$line" "malformed SHA256SUMS line: $line" }
        if ($listed.ContainsKey($rel)) { Fail 3 "SHA256SUMS 中重复：$rel" "listed twice in SHA256SUMS: $rel" }
        $listed[$rel] = $digest
    }
    $bad = New-Object System.Collections.Generic.List[string]
    # SHA-256 through .NET, not Get-FileHash: under Windows PowerShell 5.1 that command comes from a script module,
    # and started from PowerShell 7 (Windows Terminal, GitHub's default shell) Windows PowerShell inherits a module
    # path where PowerShell 7's own Microsoft.PowerShell.Utility comes first and cannot load, so Get-FileHash
    # is "not recognized" (measured in CI). Only commands built into the engine are used here.
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        foreach ($rel in $listed.Keys) {
            $path = Join-Path $Bundle ($rel -replace '/', '\')
            if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { $bad.Add("missing / 缺少：$rel"); continue }
            $stream = [System.IO.File]::OpenRead($path)
            try { $hashBytes = $hasher.ComputeHash($stream) } finally { $stream.Dispose() }
            $actual = [System.BitConverter]::ToString($hashBytes).Replace('-', '').ToLowerInvariant()
            if ($actual -cne $listed[$rel]) { $bad.Add("changed / 已更改：$rel") }
        }
    } finally {
        $hasher.Dispose()
    }
    $root = (Resolve-Path -LiteralPath $Bundle).ProviderPath.TrimEnd('\') + '\'
    foreach ($item in Get-ChildItem -LiteralPath $Bundle -Recurse -Force) {
        $rel = $item.FullName.Substring($root.Length) -replace '\\', '/'
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) { $bad.Add("link / 链接：$rel"); continue }
        if ($item.PSIsContainer -or $rel -in @('SHA256SUMS', 'SHA256SUMS.sigstore.json')) { continue }
        if (-not $listed.ContainsKey($rel)) { $bad.Add("unexpected / 多余：$rel") }
    }
    if ($bad.Count -gt 0) {
        foreach ($problem in $bad) { [Console]::Error.WriteLine("  $problem") }
        Fail 3 "$($bad.Count) 个文件与 SHA256SUMS 不符，未安装" "$($bad.Count) files do not match SHA256SUMS; nothing installed"
    }
    Say "完整性已核对（$($listed.Count) 个文件）" "integrity verified ($($listed.Count) files)"

    # 2. Signature (Sigstore keyless, D-10 g). A check inside the archive proves integrity; authenticity comes from
    #    the check on a connected machine before the transfer (README.txt, docs/installation.html). cosign needs
    #    Sigstore's trust root (network or a prepared cache), so an explicit -SkipSignatureCheck wins over a cosign
    #    found on PATH; -Cosign always verifies.
    if ($Cosign -and $SkipSignatureCheck) { Fail 2 '-Cosign 与 -SkipSignatureCheck 不能同时使用' '-Cosign and -SkipSignatureCheck exclude each other' }
    $signature = Join-Path $Bundle 'SHA256SUMS.sigstore.json'
    $identity = [string]$info.release_identity
    if (Test-Path -LiteralPath $signature -PathType Leaf) {
        if (-not $identity) { Fail 4 'BUNDLE.json 未写明签名者身份' 'BUNDLE.json names no signer identity' }
        if (-not $Cosign -and -not $SkipSignatureCheck) {
            $found = Get-Command cosign -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($found) { $Cosign = $found.Path }
        }
        if ($Cosign) {
            if (-not (Test-Path -LiteralPath $Cosign -PathType Leaf)) { Fail 2 "找不到 cosign：$Cosign" "cosign not found: $Cosign" }
            $code = Invoke-Native $Cosign @('verify-blob', $sumsPath, '--bundle', $signature, '--certificate-identity', $identity, '--certificate-oidc-issuer', $Issuer)
            if ($code -ne 0) {
                Fail 4 '签名核验失败，未安装（cosign 需要 Sigstore 信任根：联网或已准备的缓存）' 'signature check failed; nothing installed (cosign needs the Sigstore trust root: network or a prepared cache)'
            }
            Say "签名已核验：$identity" "signature verified: $identity"
        } elseif ($SkipSignatureCheck) {
            Say '按要求未在本机核验签名；请确认已在联网电脑上核验' 'signature not verified here, as requested; make sure it was verified on a connected machine'
        } else {
            Fail 4 '未找到 cosign：请先在联网电脑上核验签名（见 README.txt），然后加 -SkipSignatureCheck，或用 -Cosign 指定 cosign.exe' 'cosign not found: verify the signature on a connected machine first (see README.txt), then pass -SkipSignatureCheck, or name cosign.exe with -Cosign'
        }
    } elseif ($SkipSignatureCheck) {
        Say '未签名的开发版本，签名未核验' 'unsigned development bundle, signature not verified'
    } else {
        Fail 4 '未签名的开发版本；如需继续请加 -SkipSignatureCheck' 'unsigned development bundle; pass -SkipSignatureCheck to continue'
    }
    if ($VerifyOnly) { Say '仅核验，未安装' 'verified only, nothing installed'; exit 0 }

    # 3. Target folder: local, absolute, new or empty, and short enough whatever LongPathsEnabled says. Measured
    #    on Windows 11 (build 26200) with LongPathsEnabled = 1: an extension module with an embedded manifest
    #    (fontTools' bezierTools.pyd) loads from a path of 250 characters but not from 251, and a program starts
    #    from a path of 259 characters but not from 260 (both ERROR_FILENAME_EXCED_RANGE). So every file of the
    #    installation stays within 250 characters: the prefix may have at most 249 minus the longest relative
    #    path below it, which BUNDLE.json predicts (tools/bundle.py).
    if (-not $Prefix) {
        if (-not $env:LOCALAPPDATA) { Fail 2 '未设置 LOCALAPPDATA，请用 -Prefix 指定安装文件夹' 'LOCALAPPDATA is not set; choose the install folder with -Prefix' }
        $Prefix = Join-Path $env:LOCALAPPDATA "NeuroGrid\$version"
    }
    if ($Prefix -match '^(\\\\|//)' -or -not [System.IO.Path]::IsPathRooted($Prefix) -or $Prefix -notmatch '^[A-Za-z]:') {
        Fail 2 "安装文件夹须为本机绝对路径：$Prefix" "the install folder must be an absolute local path: $Prefix"
    }
    $Prefix = [System.IO.Path]::GetFullPath($Prefix).TrimEnd('\')
    # ConvertFrom-Json gives Int32 under Windows PowerShell 5.1 and Int64 under PowerShell 7; null if missing.
    $longest = $info.max_relative_install_path
    if (-not ($longest -is [int] -or $longest -is [long]) -or $longest -lt 0) { Fail 3 'BUNDLE.json 不完整' 'BUNDLE.json incomplete' }
    $limit = 250 - 1 - [long]$longest
    if ($Prefix.Length -gt $limit) {
        Fail 2 "安装文件夹路径过长（$($Prefix.Length) 个字符，上限 $limit）：Windows 无法从更深的路径启动程序或加载部分模块，即使已启用长路径；请用 -Prefix 选择更短的文件夹" "install folder path too long ($($Prefix.Length) characters, limit $limit): Windows cannot start programs or load some modules from deeper paths, even with long paths enabled; choose a shorter folder with -Prefix"
    }
    $created = -not (Test-Path -LiteralPath $Prefix)
    if (-not $created) {
        if (-not (Test-Path -LiteralPath $Prefix -PathType Container) -or (Get-ChildItem -LiteralPath $Prefix -Force | Select-Object -First 1)) {
            Fail 2 "目标已存在且不为空：$Prefix（新版本请装入新文件夹）" "target exists and is not empty: $Prefix (install a new version into a new folder)"
        }
    }

    # 4. Install offline: interpreter, venv, wheelhouse with hashes, bytecode compiled at install (A-48).
    $done = $false
    try {
        New-Item -ItemType Directory -Force -Path $Prefix | Out-Null
        Copy-Item -LiteralPath (Join-Path $Bundle 'python') -Destination (Join-Path $Prefix 'python') -Recurse
        $env:UV_OFFLINE = '1'
        $env:UV_NO_CONFIG = '1'
        $env:UV_PYTHON_DOWNLOADS = 'never'
        $env:UV_NO_PROGRESS = '1'
        $env:UV_CACHE_DIR = Join-Path $Prefix '.uv-cache'
        # uv hands the files to compile to the interpreter through a pipe; without UTF-8 the interpreter reads a
        # prefix with Chinese characters in the ANSI code page and silently compiles nothing (measured, A-48).
        $env:PYTHONIOENCODING = 'utf-8'
        $uv = Join-Path $Bundle 'uv\uv.exe'
        $venv = Join-Path $Prefix 'venv'
        $code = Invoke-Native $uv @('venv', '--quiet', '--python', (Join-Path $Prefix 'python\python.exe'), $venv)
        if ($code -ne 0) { Fail 2 "创建虚拟环境失败（uv 退出码 $code）" "creating the virtual environment failed (uv exit code $code)" }
        $code = Invoke-Native $uv @('pip', 'sync', '--quiet', '--python', (Join-Path $venv 'Scripts\python.exe'), '--no-index', '--find-links', (Join-Path $Bundle 'wheels'), '--require-hashes', '--no-build', '--compile-bytecode', '--link-mode', 'copy', (Join-Path $Bundle 'requirements.lock.txt'))
        if ($code -ne 0) { Fail 2 "离线安装失败（uv 退出码 $code）" "offline installation failed (uv exit code $code)" }
        Remove-Item -LiteralPath $env:UV_CACHE_DIR -Recurse -Force -ErrorAction SilentlyContinue

        # 5. Launcher (exit codes pass through; nothing is set for DENO_DIR, which NeuroGrid sets per run, A-06/A-54),
        #    the PDF browser installer and the bundle's BUNDLE.json: next to python\ and tools\ it marks this folder
        #    as an offline-bundle installation, so a missing PDF browser is reported with the bundled command (D-08).
        $launcher = Join-Path $Prefix 'neurogrid.cmd'
        $text = "@echo off`r`nsetlocal`r`nset `"PYTHONPATH=`"`r`nset `"PYTHONHOME=`"`r`n`"%~dp0venv\Scripts\neurogrid.exe`" %*`r`nexit /b %ERRORLEVEL%`r`n"
        [System.IO.File]::WriteAllText($launcher, $text, [System.Text.Encoding]::ASCII)
        New-Item -ItemType Directory -Force -Path (Join-Path $Prefix 'tools') | Out-Null
        Copy-Item -LiteralPath (Join-Path $Bundle 'tools\install_pdf_browser.py') -Destination (Join-Path $Prefix 'tools\install_pdf_browser.py')
        Copy-Item -LiteralPath $infoPath -Destination (Join-Path $Prefix 'BUNDLE.json')

        # 6. Self-test.
        $code = Invoke-Native $launcher @('--help') -Quiet
        if ($code -ne 0) { Fail 2 "安装后自检失败（退出码 $code）" "self-test after installation failed (exit code $code)" }
        $done = $true
    } finally {
        if (-not $done -and $created) { Remove-Item -LiteralPath $Prefix -Recurse -Force -ErrorAction SilentlyContinue }
    }

    # 7. Optional: PDF browser from a zip the customer provides, into NeuroGrid's own browser folder (D-08).
    if ($PdfBrowserZip) {
        $python = Join-Path $Prefix 'python\python.exe'
        $code = Invoke-Native $python @('-I', (Join-Path $Prefix 'tools\install_pdf_browser.py'), '--from-zip', $PdfBrowserZip, '--sha256', $PdfBrowserSha256.ToLowerInvariant())
        if ($code -ne 0) { Fail 2 "NeuroGrid 已安装，但 PDF 浏览器未安装（退出码 $code）" "NeuroGrid is installed, but the PDF browser is not (exit code $code)" }
        Say 'PDF 浏览器已安装' 'PDF browser installed'
    }

    Say "已安装：$launcher" "installed: $launcher"
    # Where results go (UF-08, CON-04): --out, or the defaults of check, report and manifest (cli.py).
    Say '结果只保存在本机：写入 --out 指定的位置；未指定 --out 时，check 写入当前文件夹中的 results.json，report 写入 results.json 所在的文件夹，manifest 写入数据集中的 .neurogrid\manifest.json；不会上传任何数据' 'results stay on this computer: where --out points; without --out, check writes results.json in the current folder, report writes next to results.json and manifest writes .neurogrid\manifest.json inside the dataset; nothing is uploaded'
    # The PDF browser lies outside the prefix: NEUROGRID_PDF_BROWSER_DIR or NeuroGrid's default folder (D-08).
    $pdfFolder = '%LOCALAPPDATA%\NeuroGrid\pdf-browser'
    if ($env:NEUROGRID_PDF_BROWSER_DIR) { $pdfFolder = $env:NEUROGRID_PDF_BROWSER_DIR }
    Say "卸载：删除文件夹 $Prefix（若装过 PDF 浏览器，另删 $pdfFolder）" "uninstall: delete the folder $Prefix (and $pdfFolder if the PDF browser was installed)"
    [Console]::Out.WriteLine('使用 NeuroGrid 进行的预检。不构成国家药品监督管理局（NMPA）法规意义上的符合性评价。')
    [Console]::Out.WriteLine('Pre-check with NeuroGrid. Not a conformity assessment within the meaning of NMPA regulations.')
    exit 0
} catch {
    # Any unexpected failure (copying, file system) is an environment error, never a crash with another code.
    [Console]::Error.WriteLine("错误 / Error: 安装失败 / installation failed: $($_.Exception.Message)")
    exit 2
} finally {
    foreach ($name in $savedEnvironment.Keys) { [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], 'Process') }
    try { [Console]::OutputEncoding = $consoleEncoding } catch { }
}
