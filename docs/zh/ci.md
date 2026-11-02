# CI 集成 {#ci}

NeuroGrid 可以在您自有运行器上的 CI 流水线中运行：GitHub Action 和 GitLab CI 模板运行 `check`、`report`，给出基线时
还运行 `diff`（版本比较）。NeuroGrid 在运行器上运行，不上传任何内容：`results.json`、报告和 `diff.json` 作为作业的文件
保留在运行器上。Action 和模板都没有上传或制品（artifact）步骤，Action 的最后一步会用中英文说明这一点。

## 只用于自有运行器 {#self-hosted}

- 两者都用于您自有网络中的运行器（自托管运行器，self-hosted runner）。真实人员的数据不得进入 GitHub 的运行器或
  GitLab 服务的共享运行器。
- 当运行器不是自托管运行器时，即 GitHub 的 `runner.environment` 不是 `self-hosted`（包括值为空）时，GitHub Action
  会在 NeuroGrid 运行之前停止。设置 `allow-hosted-runner: true` 后，它可以在 GitHub 托管的运行器上运行；只可用于公开
  数据或合成数据。
- GitLab 模板只在带有 `NEUROGRID_RUNNER_TAG` 中标签的运行器上运行：请用该标签注册您自有的运行器，并且不要把该标签
  分配给任何共享运行器。模板没有其他防护；未设置标签或数据集时，其脚本会停止。
- 请先在运行器上安装 NeuroGrid（[安装](installation.md)）。Action 和模板不安装任何内容，也不需要网络；它们调用已安装
  的启动程序（`PATH` 中的 `neurogrid`，或您给出的路径）。
- Linux 运行器用 bash（GitLab：sh）运行脚本，Windows 运行器用 Windows PowerShell 5.1 运行脚本。

## GitHub Action {#github-action}

Action 是仓库根目录下的 `action.yml`。请用发布标签引用它：

<!-- example: workflow -->
```yaml
jobs:
  neurogrid:
    runs-on: [self-hosted, neurogrid]
    steps:
      - uses: actions/checkout@v4
      - uses: <owner>/neurogrid@v<version>
        with:
          path: data
          rulepacks: |
            core
            bids
          baseline: previous/results.json
          fail-on: new-errors
```

!!! warning "占位"
    `<owner>/neurogrid` 是位于 `<REPO_URL>` 的公开仓库，将在仓库发布时填写。`v<version>` 是 1.0 版起的 NeuroGrid
    发布版本。

每个输入项都通过环境变量传给 Action 的脚本，从不作为表达式写进脚本。

| 输入项 | 默认值 | 含义 |
|---|---|---|
| `path` | – | 数据集文件夹或单个数据文件（必填）。 |
| `rulepacks` | – | 用于 `check --rulepack` 的规则包，每行一个名称或路径；逗号属于路径的一部分。为空时：使用配置中的规则包。 |
| `config` | – | 用于 `check --config` 的 `neurogrid.toml`；为空时：数据集中的 `.neurogrid/neurogrid.toml`。 |
| `out` | `neurogrid-results/results.json` | `check` 写入的 `results.json`；报告和 `diff.json` 写在它旁边。 |
| `strict` | `false` | 为 `true` 时运行 `check --strict`。 |
| `role` | – | `check` 在 vault 中记录的访问事件的角色（`check --role`）；为空时：`[vault] role`。 |
| `report-formats` | `html` | 用于 `report --format` 的格式（`html`、`pdf`、`html,pdf`；PDF 需要运行器上的 [PDF 浏览器](installation.md#pdf-browser)）；为 `none` 时不生成报告。 |
| `report-lang` | `zh,en` | 用于 `report --lang` 的语言。 |
| `baseline` | – | 较早运行的 `results.json`；给出时，`diff` 将其与本次运行比较并写入 `diff.json`。 |
| `fail-on` | `errors` | 步骤何时失败，见下文。 |
| `neurogrid` | `neurogrid` | 已安装的启动程序的名称或路径。 |
| `allow-hosted-runner` | `false` | 为 `true` 时允许 Action 在 GitHub 托管的运行器上运行，只可用于公开数据或合成数据。 |

| 输出项 | 含义 |
|---|---|
| `exit-code` | `check` 的退出码（0 或 1）。 |
| `diff-exit-code` | `diff` 的退出码（0 或 1）；没有 `baseline` 时为空。 |
| `results` | 写入的 `results.json` 的路径。 |

Action 运行五个步骤：检查运行器和输入项的防护步骤（输入项无效时步骤失败）、`check`（退出码 2 立即失败）、`report`
（`report-formats` 为 `none` 时跳过）、给出 `baseline` 时的 `diff`（退出码 2 立即失败）以及判定步骤：

| `fail-on` | 步骤在以下情况失败 |
|---|---|
| `errors` | `check` 以退出码 1 结束。 |
| `new-errors` | `diff` 以退出码 1 结束（[新的错误级结果](commands.md#diff)）；需要 `baseline`。 |
| `never` | 从不因检查结果失败；工具错误（退出码 2）仍会失败。 |

## GitLab CI 模板 {#gitlab}

模板是仓库中的 `ci-templates/gitlab-ci.yml`，此处完整列出，以便离线安装包随本文档一起提供它。请将其复制到您的仓库中，
用 include 引入，并扩展 `.neurogrid`（sh），或在使用 PowerShell 的 Windows 运行器上扩展 `.neurogrid-powershell`；
各变量的默认值与 Action 输入项的默认值相同。模板尚未在 GitLab 上运行过：未验证。

<!-- example: gitlab-ci.yml -->
```yaml
# NeuroGrid GitLab CI template (A-34, A-98, D-10 h): runs `neurogrid check`, `neurogrid report` and, with a
# baseline, `neurogrid diff` on your own GitLab runner. Not run on GitLab yet: not verified.
#
# Install NeuroGrid on the runner, copy this file into your repository (for example as
# ci-templates/neurogrid.yml) and extend one of the two hidden jobs:
#
#   include:
#     - local: ci-templates/neurogrid.yml
#
#   neurogrid:
#     extends: .neurogrid               # .neurogrid-powershell on a Windows runner with PowerShell
#     variables:
#       NEUROGRID_RUNNER_TAG: neurogrid  # tag of your own runner (required)
#       NEUROGRID_PATH: data/            # dataset folder or single data file (required)
#
# Only a runner with that tag takes the job: register your own runner with the tag and give it to no shared
# runner. The template has no guard against shared runners (A-34 asks for it in the GitHub Action only); its
# script stops when the tag or the dataset is not set. The NEUROGRID_TEXT_* variables are the messages of the
# script in zh and en (variables keep the scripts ASCII for Windows PowerShell 5.1); leave them as they are.
#
# Nothing is uploaded: there is no artifacts section, so results.json, the reports and diff.json stay on the
# runner. GitLab uploads artifacts to the GitLab server: add the commented example only for results without
# data of real persons.
# 不上传任何内容：本模板没有 artifacts 部分，results.json、报告和 diff.json 保留在运行器上。GitLab 会把制品
# （artifacts）上传到 GitLab 服务器：只有在结果不含真实人员数据时，才添加注释中的示例。

.neurogrid:
  tags:
    - $NEUROGRID_RUNNER_TAG
  variables:
    NEUROGRID_PATH: ""
    NEUROGRID_RULEPACKS: ""  # one rule pack name or path per line, never split at commas
    NEUROGRID_CONFIG: ""
    NEUROGRID_OUT: neurogrid-results/results.json
    NEUROGRID_STRICT: "false"
    NEUROGRID_ROLE: ""
    NEUROGRID_REPORT_FORMATS: html  # none skips the report
    NEUROGRID_REPORT_LANG: zh,en
    NEUROGRID_BASELINE: ""  # results.json of an earlier run: diff compares it with this run
    NEUROGRID_FAIL_ON: errors  # errors, new-errors (needs NEUROGRID_BASELINE) or never
    NEUROGRID_COMMAND: neurogrid  # name or path of the installed launcher
    NEUROGRID_TEXT_UNSET_ZH: "NeuroGrid：请设置 NEUROGRID_RUNNER_TAG（您自有运行器的标签）和 NEUROGRID_PATH（数据集）。"
    NEUROGRID_TEXT_UNSET_EN: "NeuroGrid: set NEUROGRID_RUNNER_TAG (the tag of your own runner) and NEUROGRID_PATH (the dataset)."
    NEUROGRID_TEXT_INVALID_ZH: "NeuroGrid：NEUROGRID_STRICT 须为 true 或 false，NEUROGRID_FAIL_ON 须为 errors、new-errors（需要 NEUROGRID_BASELINE）或 never。"
    NEUROGRID_TEXT_INVALID_EN: "NeuroGrid: NEUROGRID_STRICT must be true or false, NEUROGRID_FAIL_ON errors, new-errors (needs NEUROGRID_BASELINE) or never."
    NEUROGRID_TEXT_NOTE_ZH: "NeuroGrid 不上传任何内容：results.json、报告和版本比较结果作为文件保留在此运行器上。只有在其中不含真实人员数据时，才可将其作为制品（artifacts）上传。"
    NEUROGRID_TEXT_NOTE_EN: "NeuroGrid uploads nothing: results.json, the reports and the comparison stay on this runner as files. Upload them as artifacts only if they hold no data of real persons."
    NEUROGRID_TEXT_FAILED_ZH: "NeuroGrid：按 NEUROGRID_FAIL_ON，作业失败（check 或 diff 的退出码为 1）。"
    NEUROGRID_TEXT_FAILED_EN: "NeuroGrid: the job fails by NEUROGRID_FAIL_ON (exit code 1 of check or diff)."
  # artifacts:  # uploads to the GitLab server: only for results without data of real persons
  #   paths:
  #     - neurogrid-results/
  #   expire_in: 7 days
  script:
    - |
      set -eu
      say() { printf '%s\n' "$@" >&2; }
      if [ -z "${NEUROGRID_RUNNER_TAG:-}" ] || [ -z "$NEUROGRID_PATH" ]; then
        say "$NEUROGRID_TEXT_UNSET_ZH" "$NEUROGRID_TEXT_UNSET_EN"
        exit 2
      fi
      case "$NEUROGRID_STRICT:$NEUROGRID_FAIL_ON" in
        true:errors | true:new-errors | true:never | false:errors | false:new-errors | false:never) ;;
        *) say "$NEUROGRID_TEXT_INVALID_ZH" "$NEUROGRID_TEXT_INVALID_EN"; exit 2 ;;
      esac
      if [ "$NEUROGRID_FAIL_ON" = new-errors ] && [ -z "$NEUROGRID_BASELINE" ]; then
        say "$NEUROGRID_TEXT_INVALID_ZH" "$NEUROGRID_TEXT_INVALID_EN"
        exit 2
      fi
      set -- check "$NEUROGRID_PATH" --out "$NEUROGRID_OUT"
      fields=$IFS
      IFS='
      '
      set -f
      for pack in $NEUROGRID_RULEPACKS; do
        pack=$(printf '%s' "$pack" | tr -d '\r')
        if [ -n "$pack" ]; then set -- "$@" --rulepack "$pack"; fi
      done
      set +f
      IFS=$fields
      if [ -n "$NEUROGRID_CONFIG" ]; then set -- "$@" --config "$NEUROGRID_CONFIG"; fi
      if [ "$NEUROGRID_STRICT" = true ]; then set -- "$@" --strict; fi
      if [ -n "$NEUROGRID_ROLE" ]; then set -- "$@" --role "$NEUROGRID_ROLE"; fi
      checked=0
      "$NEUROGRID_COMMAND" "$@" || checked=$?
      if [ "$checked" -ne 0 ] && [ "$checked" -ne 1 ]; then exit "$checked"; fi
      if [ "$NEUROGRID_REPORT_FORMATS" != none ]; then
        "$NEUROGRID_COMMAND" report "$NEUROGRID_OUT" --lang "$NEUROGRID_REPORT_LANG" --format "$NEUROGRID_REPORT_FORMATS"
      fi
      compared=0
      if [ -n "$NEUROGRID_BASELINE" ]; then
        target="$(dirname "$NEUROGRID_OUT")/diff.json"
        "$NEUROGRID_COMMAND" diff "$NEUROGRID_BASELINE" "$NEUROGRID_OUT" --format text,json --out "$target" || compared=$?
        if [ "$compared" -ne 0 ] && [ "$compared" -ne 1 ]; then exit "$compared"; fi
      fi
      say "$NEUROGRID_TEXT_NOTE_ZH" "$NEUROGRID_TEXT_NOTE_EN"
      if { [ "$NEUROGRID_FAIL_ON" = errors ] && [ "$checked" -eq 1 ]; } || { [ "$NEUROGRID_FAIL_ON" = new-errors ] && [ "$compared" -eq 1 ]; }; then
        say "$NEUROGRID_TEXT_FAILED_ZH" "$NEUROGRID_TEXT_FAILED_EN"
        exit 1
      fi

.neurogrid-powershell:
  extends: .neurogrid
  script:
    - |
      $ErrorActionPreference = 'Continue'
      function Say([string[]] $Lines) {
        $stream = [Console]::OpenStandardError()
        foreach ($line in $Lines) {
          $bytes = [System.Text.Encoding]::UTF8.GetBytes($line + "`n")
          $stream.Write($bytes, 0, $bytes.Length)
        }
        $stream.Flush()
      }
      if (-not $env:NEUROGRID_RUNNER_TAG -or -not $env:NEUROGRID_PATH) {
        Say @($env:NEUROGRID_TEXT_UNSET_ZH, $env:NEUROGRID_TEXT_UNSET_EN)
        exit 2
      }
      $strictValid = @('true', 'false') -ccontains $env:NEUROGRID_STRICT
      $failOnValid = @('errors', 'new-errors', 'never') -ccontains $env:NEUROGRID_FAIL_ON
      if (-not $strictValid -or -not $failOnValid -or ($env:NEUROGRID_FAIL_ON -ceq 'new-errors' -and -not $env:NEUROGRID_BASELINE)) {
        Say @($env:NEUROGRID_TEXT_INVALID_ZH, $env:NEUROGRID_TEXT_INVALID_EN)
        exit 2
      }
      $arguments = @('check', $env:NEUROGRID_PATH, '--out', $env:NEUROGRID_OUT)
      foreach ($pack in ("$env:NEUROGRID_RULEPACKS" -split '\r?\n')) {
        if ($pack) { $arguments += @('--rulepack', $pack) }
      }
      if ($env:NEUROGRID_CONFIG) { $arguments += @('--config', $env:NEUROGRID_CONFIG) }
      if ($env:NEUROGRID_STRICT -ceq 'true') { $arguments += '--strict' }
      if ($env:NEUROGRID_ROLE) { $arguments += @('--role', $env:NEUROGRID_ROLE) }
      & $env:NEUROGRID_COMMAND @arguments
      $checked = $LASTEXITCODE
      if ($null -eq $checked) { $checked = 2 }
      if ($checked -ne 0 -and $checked -ne 1) { exit $checked }
      if ($env:NEUROGRID_REPORT_FORMATS -cne 'none') {
        & $env:NEUROGRID_COMMAND report $env:NEUROGRID_OUT --lang $env:NEUROGRID_REPORT_LANG --format $env:NEUROGRID_REPORT_FORMATS
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
      }
      $compared = 0
      if ($env:NEUROGRID_BASELINE) {
        $folder = Split-Path -Parent $env:NEUROGRID_OUT
        if ($folder) { $target = Join-Path $folder 'diff.json' } else { $target = 'diff.json' }
        & $env:NEUROGRID_COMMAND diff $env:NEUROGRID_BASELINE $env:NEUROGRID_OUT --format 'text,json' --out $target
        $compared = $LASTEXITCODE
        if ($null -eq $compared) { $compared = 2 }
        if ($compared -ne 0 -and $compared -ne 1) { exit $compared }
      }
      Say @($env:NEUROGRID_TEXT_NOTE_ZH, $env:NEUROGRID_TEXT_NOTE_EN)
      if (($env:NEUROGRID_FAIL_ON -ceq 'errors' -and $checked -eq 1) -or ($env:NEUROGRID_FAIL_ON -ceq 'new-errors' -and $compared -eq 1)) {
        Say @($env:NEUROGRID_TEXT_FAILED_ZH, $env:NEUROGRID_TEXT_FAILED_EN)
        exit 1
      }
      exit 0
```

## 已验证的内容 {#status}

- 仓库中的工作流 `ci-integration.yml` 只用合成数据在 GitHub 托管的 Ubuntu 24.04 和 Windows 运行器上运行 Action：
  未设置 `allow-hosted-runner` 时，Action 必须在检查任何内容之前停止；设置后，`check`、`report` 和 `diff` 必须给出预期
  的退出码和文件。
- 尚未验证：Action 在自托管运行器上的运行，以及 GitLab 模板在 GitLab 上的运行（[局限](limitations.md#ci)）。
