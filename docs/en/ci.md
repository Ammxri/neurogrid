# CI integration {#ci}

NeuroGrid can run in a CI pipeline on your own runner: a GitHub Action and a GitLab CI template run `check`,
`report` and, with a baseline, `diff`. NeuroGrid runs on the runner and uploads nothing: `results.json`, the
reports and `diff.json` stay there as files of the job. Neither the action nor the template has an upload or
artifact step, and the last step of the action says so in zh and en.

## Your own runner only {#self-hosted}

- Both are meant for runners in your own network (self-hosted runners). Data of real persons must not reach a
  runner of GitHub or a shared runner of a GitLab service.
- The GitHub Action stops before NeuroGrid runs when the runner is not self-hosted: when GitHub's
  `runner.environment` is anything but `self-hosted`, an empty value included. `allow-hosted-runner: true` lets it
  run on a GitHub-hosted runner; use it for public or synthetic data only.
- The GitLab template runs only on a runner with the tag in `NEUROGRID_RUNNER_TAG`: register your own runner with
  that tag and give the tag to no shared runner. The template has no further guard; its script stops when the
  tag or the dataset is not set.
- Install NeuroGrid on the runner first ([Installation](installation.md)). The action and the template install
  nothing and need no network; they call the installed launcher (`neurogrid` on the `PATH`, or the path you give).
- Linux runners run the scripts in bash (GitLab: sh), Windows runners in Windows PowerShell 5.1.

## GitHub Action {#github-action}

The action is `action.yml` at the root of the repository. Refer to it with a release tag:

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

!!! warning "Placeholder"
    `<owner>/neurogrid` is the public repository at `<REPO_URL>`; it is filled in when the repository is
    published. `v<version>` is a NeuroGrid release from version 1.0 on.

Every input reaches the scripts of the action through environment variables, never as an expression inside a
script.

| Input | Default | Meaning |
|---|---|---|
| `path` | – | Dataset folder or single data file (required). |
| `rulepacks` | – | Rule packs for `check --rulepack`, one name or path per line; a comma is part of a path. Empty: the packs of the configuration. |
| `config` | – | `neurogrid.toml` for `check --config`; empty: `.neurogrid/neurogrid.toml` in the dataset. |
| `out` | `neurogrid-results/results.json` | The `results.json` that `check` writes; the reports and `diff.json` go next to it. |
| `strict` | `false` | `true` runs `check --strict`. |
| `role` | – | Role of the access event of `check` in the vault (`check --role`); empty: `[vault] role`. |
| `report-formats` | `html` | Formats for `report --format` (`html`, `pdf`, `html,pdf`; PDF needs the [PDF browser](installation.md#pdf-browser) on the runner); `none` skips the report. |
| `report-lang` | `zh,en` | Languages for `report --lang`. |
| `baseline` | – | `results.json` of an earlier run; given, `diff` compares it with this run and writes `diff.json`. |
| `fail-on` | `errors` | When the step fails, see below. |
| `neurogrid` | `neurogrid` | Name or path of the installed launcher. |
| `allow-hosted-runner` | `false` | `true` lets the action run on a GitHub-hosted runner, for public or synthetic data only. |

| Output | Meaning |
|---|---|
| `exit-code` | Exit code of `check` (0 or 1). |
| `diff-exit-code` | Exit code of `diff` (0 or 1); empty without `baseline`. |
| `results` | Path of the `results.json` written. |

The action runs five steps: the guard for the runner and the inputs (an invalid input fails the step), `check`
(exit code 2 fails at once), `report` unless `report-formats` is `none`, `diff` when `baseline` is given (exit
code 2 fails at once) and the verdict:

| `fail-on` | The step fails when |
|---|---|
| `errors` | `check` ends with exit code 1. |
| `new-errors` | `diff` ends with exit code 1 ([new error findings](commands.md#diff)); needs `baseline`. |
| `never` | never by the findings; a tool error (exit code 2) still fails. |

## GitLab CI template {#gitlab}

The template is `ci-templates/gitlab-ci.yml` in the repository and is shown here in full, so that the offline
bundle carries it with this documentation. Copy it into your repository, include it and extend `.neurogrid`
(sh) or, on a Windows runner with PowerShell, `.neurogrid-powershell`; the variables have the defaults of the
action's inputs. It has not run on GitLab yet: not verified.

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

## What has been verified {#status}

- The workflow `ci-integration.yml` of the repository runs the action on GitHub-hosted Ubuntu 24.04 and Windows
  runners with synthetic data only: without `allow-hosted-runner` the action must stop before anything is
  checked; with it, `check`, `report` and `diff` must give the expected exit codes and files.
- Not verified yet: a run of the action on a self-hosted runner, and the GitLab template on GitLab
  ([Limitations](limitations.md#ci)).
