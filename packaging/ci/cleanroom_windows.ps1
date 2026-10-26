# Clean-room test of the Windows offline bundle (UF-08, NG-N01, NG-N04, CON-04, ARC-06, A-26, A-49).
# A fresh folder, no Python or uv on PATH, dead proxies, PDF browser folder and TEMP inside the room: the bundle is
# installed with its own installer and every v0.1 command runs from the installation (launcher neurogrid.cmd) on
# synthetic fixtures under a Chinese folder name with a space. Dataset data never gives exit 2.
# CI (elevated, ephemeral runner, without -NoOsAudit): Windows Filtering Platform audit of every connection plus an
# outbound block rule for every .exe of the bundle and of the installation; any connection or attempt of those
# programs to a non-loopback address fails the run. Locally use -NoOsAudit: no security setting is changed.
# Evidence (UTF-8): exit-codes.txt, <step>.out.log / <step>.err.log, summary.txt, wfp-*.txt (CI).
param(
    [Parameter(Mandatory = $true)][string]$Archive,
    [string]$Evidence = 'evidence',
    [string]$Root = '',
    [ValidateSet('cmd', 'pwsh')][string]$Installer = 'cmd',
    [string]$PdfBrowserZip = '',
    [string]$PdfBrowserSha256 = '',
    [switch]$NoOsAudit,
    [switch]$Keep
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
$started = Get-Date
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).ProviderPath
$Archive = (Resolve-Path -LiteralPath $Archive).ProviderPath
New-Item -ItemType Directory -Force -Path $Evidence | Out-Null
$Evidence = (Resolve-Path -LiteralPath $Evidence).ProviderPath
if (-not $Root) { $Root = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { [System.IO.Path]::GetTempPath() } }
$tag = 'ngcr' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$room = Join-Path $Root $tag
$wfpConnection = '{0CCE9226-69AE-11D9-BED3-505054503030}'  # audit subcategory "Filtering Platform Connection"
$utf8 = New-Object System.Text.UTF8Encoding $false
$codes = Join-Path $Evidence 'exit-codes.txt'
[System.IO.File]::WriteAllText($codes, '', $utf8)

function Note([string]$line) { [System.IO.File]::AppendAllText($codes, "$line`n", $utf8); Write-Host $line }

function Block-Executables([string]$dir) {
    if ($NoOsAudit) { return }
    Get-ChildItem -LiteralPath $dir -Recurse -File -Filter *.exe | ForEach-Object {
        New-NetFirewallRule -DisplayName "$tag-block" -Direction Outbound -Action Block -Program $_.FullName | Out-Null
    }
}

function Quote([string]$text) {
    if ($text -match '[\s,;&|<>^"()]' -or $text -eq '') { return '"' + ($text -replace '"', '\"') + '"' }
    return $text
}

function Shown([string]$path) {
    # A path as NeuroGrid's messages show it: quoted when it holds a space (kernel/pdf.py _quoted), then the home
    # folder as ~ (A-51, cli.py _redact). Without USERPROFILE the path stays as it is ([string] of $null is '',
    # so no method is called on a null value under ErrorActionPreference Stop).
    if ($path.Contains(' ')) { $path = '"' + $path + '"' }
    $userHome = ([string]$env:USERPROFILE).TrimEnd('\')
    if (-not $userHome) { return $path }
    return [regex]::Replace($path, [regex]::Escape($userHome) + '(?=[\\/])', '~', 'IgnoreCase')
}

function Invoke-Step([string]$name, [int[]]$allowed, [string]$exe, [string[]]$arguments, [string]$cwd) {
    # Start-Process instead of "& ... *> log": under ErrorActionPreference Stop, Windows PowerShell 5.1 turns
    # redirected native stderr into a terminating error before the exit code can be read.
    $line = ($arguments | ForEach-Object { Quote $_ }) -join ' '
    $file = $exe
    if ($exe.EndsWith('.cmd')) { $file = Join-Path $env:SystemRoot 'System32\cmd.exe'; $line = '/s /c "' + (Quote $exe) + ' ' + $line + '"' }
    $t = Get-Date
    $p = Start-Process -FilePath $file -ArgumentList $line -WorkingDirectory $cwd -NoNewWindow -Wait -PassThru `
        -RedirectStandardOutput (Join-Path $Evidence "$name.out.log") -RedirectStandardError (Join-Path $Evidence "$name.err.log")
    $code = $p.ExitCode
    Note ("{0} {1} ({2:N1} s)" -f $name, $code, ((Get-Date) - $t).TotalSeconds)
    if ($allowed -notcontains $code) { throw "$name exited with $code (allowed: $($allowed -join ','))" }
}

$rulesAdded = $false
try {
    if (-not $NoOsAudit) {
        auditpol /set /subcategory:$wfpConnection /success:enable /failure:enable | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'auditpol failed: the OS-level evidence needs an elevated runner' }
        $rulesAdded = $true
    }
    $auditStart = Get-Date

    # 1. Fresh folder, extraction with the tar.exe of Windows, nothing of the build machine on PATH.
    New-Item -ItemType Directory -Path $room, "$room\tmp", "$room\pdf-browser", "$room\pdf-browser-empty" | Out-Null
    & "$env:SystemRoot\System32\tar.exe" -xf $Archive -C $room
    if ($LASTEXITCODE -ne 0) { throw "tar.exe failed with $LASTEXITCODE" }
    $bundle = @(Get-ChildItem -LiteralPath $room -Directory -Filter 'neurogrid-*-offline-win_amd64')
    if ($bundle.Count -ne 1) { throw 'the archive must hold exactly one bundle folder' }
    $bundle = $bundle[0].FullName
    foreach ($name in @(Get-ChildItem Env: | Where-Object { $_.Name -match '^(PYTHON|UV_|VIRTUAL_ENV|CONDA|PIP_)' } | ForEach-Object { $_.Name })) {
        Remove-Item -LiteralPath "Env:$name"
    }
    $shell = (Get-Process -Id $PID).Path
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot;$env:SystemRoot\System32\WindowsPowerShell\v1.0"
    $env:HTTP_PROXY = 'http://127.0.0.1:9'; $env:HTTPS_PROXY = 'http://127.0.0.1:9'; $env:ALL_PROXY = 'http://127.0.0.1:9'
    $env:NO_PROXY = ''
    $env:TEMP = "$room\tmp"; $env:TMP = "$room\tmp"
    $env:NEUROGRID_PDF_BROWSER_DIR = "$room\pdf-browser"
    if (Get-Command python.exe, python3.exe, uv.exe -CommandType Application -ErrorAction SilentlyContinue) {
        throw 'python or uv is reachable on PATH: not a clean room'
    }
    Block-Executables $bundle

    # 2. Install with the shipped installer: install.cmd (Windows PowerShell 5.1) or install.ps1 under PowerShell 7.
    # The default prefix lies below %LOCALAPPDATA%, which holds the user name: a Chinese folder name with a
    # space is tested here. The prefix has exactly the length limit of install.ps1 (249 minus BUNDLE.json's
    # longest relative path), so every command below runs from the deepest folder the installer accepts; one
    # character more is refused with exit 2 before anything is created.
    $info = [System.IO.File]::ReadAllText((Join-Path $bundle 'BUNDLE.json'), $utf8) | ConvertFrom-Json
    $limit = 249 - [int]$info.max_relative_install_path
    $parent = Join-Path $room '安装 目录'
    $pad = $limit - $parent.Length - 1 - 'NeuroGrid'.Length
    if ($pad -lt 0) { throw "the room $room is too deep for an install prefix of $limit characters" }
    $prefix = Join-Path $parent ('NeuroGrid' + ('_' * $pad))
    $over = $prefix + '_'
    Invoke-Step 'install-over-limit' @(2) (Join-Path $bundle 'install.cmd') @('-Prefix', $over, '-SkipSignatureCheck') $room
    if (Test-Path -LiteralPath $parent) { throw 'the refused installation created a folder' }
    $refusal = [System.IO.File]::ReadAllText((Join-Path $Evidence 'install-over-limit.err.log'))
    if (-not $refusal.Contains("($($over.Length) characters, limit $limit)")) { throw 'the refusal does not name the length and the limit' }
    # The signature of a release bundle is verified on the connected host before (release.yml); cosign could not
    # reach Sigstore's trust root from inside the room, exactly as on an offline customer machine.
    $options = @('-Prefix', $prefix, '-SkipSignatureCheck')
    if ($PdfBrowserZip) { $options += @('-PdfBrowserZip', $PdfBrowserZip, '-PdfBrowserSha256', $PdfBrowserSha256) }
    if ($Installer -eq 'cmd') {
        Invoke-Step 'install' @(0) (Join-Path $bundle 'install.cmd') $options $room
    } else {
        if ($PSVersionTable.PSEdition -ne 'Core') { throw '-Installer pwsh needs this script to run under PowerShell 7' }
        Invoke-Step 'install' @(0) $shell (@('-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $bundle 'install.ps1')) + $options) $room
    }
    Invoke-Step 'install-verify-only' @(0) (Join-Path $bundle 'install.cmd') @('-VerifyOnly', '-SkipSignatureCheck') $room
    Block-Executables $prefix
    Block-Executables "$room\pdf-browser"
    # What the PDF part relies on: the bundled interpreter and installer next to BUNDLE.json (kernel/pdf.py names
    # this command when the PDF browser is missing). The installer removes its uv cache.
    foreach ($rel in 'neurogrid.cmd', 'BUNDLE.json', 'python\python.exe', 'tools\install_pdf_browser.py', 'venv\Scripts\neurogrid.exe') {
        if (-not (Test-Path -LiteralPath (Join-Path $prefix $rel) -PathType Leaf)) { throw "the installation lacks $rel" }
    }
    if (Test-Path -LiteralPath (Join-Path $prefix '.uv-cache')) { throw 'the installer left its uv cache behind' }
    # The MAX_PATH guard of install.ps1 relies on BUNDLE.json's prediction of the longest path below the prefix.
    $installed = @(Get-ChildItem -LiteralPath $prefix -Recurse -File -Force)
    $longest = ($installed | ForEach-Object { $_.FullName.Length - $prefix.Length - 1 } | Measure-Object -Maximum).Maximum
    $predicted = [int]([System.IO.File]::ReadAllText((Join-Path $prefix 'BUNDLE.json'), $utf8) | ConvertFrom-Json).max_relative_install_path
    $installedMiB = [math]::Round((($installed | Measure-Object -Property Length -Sum).Sum) / 1MB, 1)
    if ($longest -gt $predicted) { throw "longest path below the prefix: $longest characters, BUNDLE.json predicts $predicted" }
    # A-48: bytecode compiled at install, for every module of the venv (a Chinese prefix once made it silently fail).
    $site = Join-Path $prefix 'venv\Lib\site-packages'
    $modules = @(Get-ChildItem -LiteralPath $site -Recurse -File -Filter *.py | Where-Object { $_.Extension -eq '.py' })
    $uncompiled = @($modules | Where-Object { -not (Test-Path -LiteralPath (Join-Path $_.DirectoryName "__pycache__\$($_.BaseName).cpython-312.pyc")) })
    if ($modules.Count -eq 0 -or $uncompiled.Count -gt 0) {
        throw "modules without compiled bytecode: $($uncompiled.Count) of $($modules.Count), e.g. $(@($uncompiled | Select-Object -First 3 | ForEach-Object { $_.FullName }) -join ', ')"
    }
    $ng = Join-Path $prefix 'neurogrid.cmd'

    # 3. Every v0.1 command on synthetic fixtures (EDF, EDF+D, BDF, BrainVision, EEGLAB, BIDS) in a folder with a
    #    Chinese name and a space. FIF has no synthetic fixture; it is covered by the corpus run (ds000248).
    $work = Join-Path $room 'work\数据 集'
    New-Item -ItemType Directory -Force -Path $work | Out-Null
    foreach ($f in 'edf_ok', 'edf_plus_d', 'bdf_ok', 'brainvision_ok', 'eeglab_ok', 'bids_ok') {
        Copy-Item -Recurse -LiteralPath (Join-Path $repo "tests\fixtures\synthetic\$f") -Destination (Join-Path $work $f)
    }
    $documented = [System.IO.File]::ReadAllText((Join-Path $repo 'tests\fixtures\documented.toml'), $utf8)
    [System.IO.File]::WriteAllText((Join-Path $work 'documented.toml'), $documented, $utf8)
    $convert = $documented.Substring(0, $documented.IndexOf('[convert]')) + "[[convert.files]]`npath = `"rec_a.edf`"`nsubject = `"01`"`ntask = `"rest`"`n`n[[convert.files]]`npath = `"rec_b.edf`"`nsubject = `"02`"`ntask = `"rest`"`n"
    [System.IO.File]::WriteAllText((Join-Path $work 'convert.toml'), $convert, $utf8)
    $asOf = @('--as-of', '2026-10-11')
    Invoke-Step 'scan' @(0) $ng @('scan', (Join-Path $work 'edf_ok'), '--out', (Join-Path $work 'scan.json')) $work
    Invoke-Step 'check-edf' @(0) $ng (@('check', 'edf_ok', '--config', 'documented.toml', '--out', 'r-edf.json') + $asOf) $work
    Invoke-Step 'check-edf-plus-d' @(0, 1) $ng (@('check', 'edf_plus_d', '--config', 'documented.toml', '--out', 'r-edfd.json') + $asOf) $work
    Invoke-Step 'check-bdf' @(0, 1) $ng (@('check', 'bdf_ok', '--config', 'documented.toml', '--out', 'r-bdf.json') + $asOf) $work
    Invoke-Step 'check-brainvision' @(0, 1) $ng (@('check', 'brainvision_ok', '--config', 'documented.toml', '--out', 'r-bv.json') + $asOf) $work
    Invoke-Step 'check-eeglab' @(0, 1) $ng (@('check', 'eeglab_ok', '--config', 'documented.toml', '--out', 'r-set.json') + $asOf) $work
    Invoke-Step 'check-bids' @(0, 1) $ng (@('check', (Join-Path $work 'bids_ok'), '--rulepack', 'bids', '--rulepack', 'gxdsl008', '--out', (Join-Path $work 'r-bids.json')) + $asOf) $work
    Invoke-Step 'convert' @(0) $ng @('convert', 'edf_ok', '--to', 'bids', '--out', 'converted', '--config', 'convert.toml') $work
    Invoke-Step 'check-converted' @(0, 1) $ng (@('check', 'converted', '--rulepack', 'bids', '--out', 'r-conv.json') + $asOf) $work
    Invoke-Step 'manifest' @(0) $ng @('manifest', 'bids_ok', '--out', 'manifest.json') $work
    Invoke-Step 'verify' @(0) $ng @('verify', 'bids_ok', '--manifest', 'manifest.json') $work
    Invoke-Step 'report-html' @(0) $ng @('report', 'r-edf.json', '--lang', 'zh,en', '--format', 'html', '--out', 'report') $work
    foreach ($lang in 'zh', 'en') {
        if (-not (Test-Path -LiteralPath (Join-Path $work "report\report.$lang.html"))) { throw "report.$lang.html missing" }
    }
    if ($PdfBrowserZip) {
        Invoke-Step 'report-pdf' @(0) $ng @('report', 'r-edf.json', '--lang', 'zh,en', '--format', 'html,pdf', '--out', 'report-pdf') $work
        foreach ($lang in 'zh', 'en') {
            if (-not (Test-Path -LiteralPath (Join-Path $work "report-pdf\report.$lang.pdf"))) { throw "report.$lang.pdf missing" }
        }
    }
    # Without a PDF browser (an empty browser folder): exit 2, nothing written, and the hint names this
    # installation's own interpreter and PDF browser installer (kernel/pdf.py install_hint, B2).
    $env:NEUROGRID_PDF_BROWSER_DIR = "$room\pdf-browser-empty"
    Invoke-Step 'report-pdf-without-shell' @(2) $ng @('report', 'r-edf.json', '--lang', 'en', '--format', 'pdf', '--out', 'report-no-shell') $work
    $env:NEUROGRID_PDF_BROWSER_DIR = "$room\pdf-browser"
    if (Test-Path -LiteralPath (Join-Path $work 'report-no-shell')) { throw 'the report without PDF browser wrote output' }
    $hint = 'Install it with: ' + (Shown (Join-Path $prefix 'python\python.exe')) + ' ' + (Shown (Join-Path $prefix 'tools\install_pdf_browser.py'))
    if (-not ([System.IO.File]::ReadAllText((Join-Path $Evidence 'report-pdf-without-shell.err.log'), $utf8)).Contains($hint)) {
        throw "the hint does not name the installation's PDF browser installer: $hint"
    }
    Invoke-Step 'usage-error' @(2) $ng @('check') $work

    # 4. OS-level evidence: no connection or attempt of any program of the bundle or the installation (CI only).
    $summary = New-Object System.Collections.Generic.List[string]
    if (-not $NoOsAudit) {
        $events = @(Get-WinEvent -FilterHashtable @{ LogName = 'Security'; Id = 5156, 5157; StartTime = $auditStart } -ErrorAction SilentlyContinue)
        $ours = New-Object System.Collections.Generic.List[string]
        $loopback = 0
        foreach ($e in $events) {
            $data = @{}
            foreach ($d in ([xml]$e.ToXml()).Event.EventData.Data) { $data[$d.Name] = $d.'#text' }
            if ($data['Application'] -notlike "*\$tag\*") { continue }
            if ($data['DestAddress'] -in @('127.0.0.1', '::1')) { $loopback++; continue }
            $ours.Add(('{0} {1} {2} -> {3}:{4}' -f $e.Id, $data['Application'], $data['Direction'], $data['DestAddress'], $data['DestPort']))
        }
        [System.IO.File]::WriteAllText((Join-Path $Evidence 'wfp-connections.txt'), (($ours -join "`n") + "`n"), $utf8)
        $line = "WFP audit: $($ours.Count) non-loopback connections or attempts by programs under $tag; $loopback loopback events; $($events.Count) events in total"
        [System.IO.File]::WriteAllText((Join-Path $Evidence 'wfp-summary.txt'), "$line`n", $utf8)
        $summary.Add($line)
        if ($ours.Count -gt 0) { throw "network connections by NeuroGrid programs:`n$($ours -join "`n")" }
    }
    $left = @(Get-ChildItem -LiteralPath "$room\tmp" -Force -ErrorAction SilentlyContinue)
    $names = @($left | ForEach-Object { $_.Name }) -join "`n"
    [System.IO.File]::WriteAllText((Join-Path $Evidence 'temp-left.txt'), "$names`n", $utf8)
    # A-54: neither the installer nor a NeuroGrid run leaves anything in TEMP.
    if ($left.Count -gt 0) { throw "entries left in TEMP (temp-left.txt): $($left.Count)" }
    $summary.Add("archive: $(Split-Path -Leaf $Archive) sha256 $((Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLowerInvariant())")
    $summary.Add("shell: PowerShell $($PSVersionTable.PSVersion) ($($PSVersionTable.PSEdition)); installer: $Installer; OS: $([System.Environment]::OSVersion.VersionString)")
    $summary.Add("offline switches: PATH = System32 only, HTTP(S)_PROXY/ALL_PROXY = http://127.0.0.1:9, UV_OFFLINE=1 (installer), OS audit: $(-not $NoOsAudit)")
    $summary.Add("install prefix: $($prefix.Length) characters = the limit $limit (249 - $predicted); $($over.Length) characters refused with exit 2, nothing created")
    $summary.Add("installed: $($installed.Count) files, $installedMiB MiB; longest path below the prefix $longest characters (BUNDLE.json: $predicted); $($modules.Count) modules, all with compiled bytecode")
    $summary.Add("PDF report: $(if ($PdfBrowserZip) { 'exit 0 with the browser from -PdfBrowserZip; ' } else { '' })exit 2 with an empty browser folder, nothing written, hint: $hint")
    $summary.Add("entries left in the room's TEMP: $($left.Count) (temp-left.txt)")
    $summary.Add(("total {0:N0} s; all steps passed" -f ((Get-Date) - $started).TotalSeconds))
    [System.IO.File]::WriteAllText((Join-Path $Evidence 'summary.txt'), (($summary -join "`n") + "`n"), $utf8)
    $summary | ForEach-Object { Write-Host $_ }
} finally {
    if ($rulesAdded) {
        Get-NetFirewallRule -DisplayName "$tag-block" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
        auditpol /set /subcategory:$wfpConnection /success:disable /failure:disable | Out-Null
    }
    if (-not $Keep) { Remove-Item -LiteralPath $room -Recurse -Force -ErrorAction SilentlyContinue }
}
