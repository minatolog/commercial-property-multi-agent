<#
.SYNOPSIS
  自动“编码 → 审查”循环：DeepSeek（经 Claude Code）编码，Claude 审查，直到通过或达到轮数上限。

.EXAMPLE
  .\scripts\dev_loop\dev_loop.ps1 -TaskFile docs\handoffs\DEEPSEEK_TASK035_XXX_PROMPT.md

.NOTES
  - 需要已安装 Claude Code 命令行（claude），并已登录过一次（审查方用你的 Claude 账号）。
  - 需要环境变量 DEEPSEEK_API_KEY（编码方用）。
  - 脚本不会提交代码；通过后由你自己检查 diff 再 commit。
  - 每轮日志写到 tmp\dev_loop\<时间戳>\。
  - 退出码：0 审查通过；1 达到轮数上限仍未通过；2 中途出错或护栏触发（见 summary.md）。
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$TaskFile,
    [int]$MaxRounds = 5,
    [string]$CoderModel = "deepseek-chat",
    [string]$ReviewerModel = "",
    [int]$CoderMaxTurns = 80,
    [int]$ReviewerMaxTurns = 40,
    [string]$TestCommand = '"D:\anacada\envs\commercial-agent\python.exe" -m unittest discover -s tests -p "test_*.py"',
    [string]$TestWorkDir = "backend",
    [int]$TestTailLines = 150,
    [switch]$SkipTests,
    [switch]$CoderSkipPermissions,
    [string]$ClaudeExe = ""
)

$ErrorActionPreference = "Stop"
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
# 不设这一项时，PowerShell 5.1 经管道传给 claude 的提示词开头会多一个 BOM（﻿）
[Console]::InputEncoding = $utf8
$OutputEncoding = $utf8

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

# ---------------------------------------------------------------- 前置检查
if (-not $ClaudeExe) {
    $cmd = Get-Command claude -ErrorAction SilentlyContinue
    if ($cmd) {
        $ClaudeExe = $cmd.Source
    }
    else {
        # 退而使用 Claude 桌面 App 自带的命令行（取最新版本）
        $bundled = Get-ChildItem (Join-Path $env:LOCALAPPDATA "Claude-Data") -Recurse -Filter "claude.exe" -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match '\\claude-code\\' } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($bundled) { $ClaudeExe = $bundled.FullName }
    }
}
if (-not $ClaudeExe -or -not (Test-Path $ClaudeExe)) {
    throw "找不到 claude 命令行。请安装 Claude Code 命令行，或用 -ClaudeExe 指定 claude.exe 路径。"
}
Write-Host "claude 命令行：$ClaudeExe"

# DeepSeek key 只放进局部变量，不写进本进程环境，避免被编码方 / 审查方的子进程继承。
$DeepseekKey = $env:DEEPSEEK_API_KEY
if (-not $DeepseekKey) {
    $dotenv = Join-Path $RepoRoot ".env"
    if (Test-Path $dotenv) {
        $line = Get-Content $dotenv -Encoding UTF8 | Where-Object { $_ -match '^\s*DEEPSEEK_API_KEY\s*=' } | Select-Object -First 1
        if ($line) { $DeepseekKey = ($line -replace '^\s*DEEPSEEK_API_KEY\s*=\s*', '').Trim().Trim('"').Trim("'") }
    }
}
if (-not $DeepseekKey) {
    throw "未找到 DEEPSEEK_API_KEY（环境变量和仓库 .env 中都没有）。"
}
$taskFull = (Resolve-Path $TaskFile).Path
if (-not $taskFull.StartsWith($RepoRoot + '\')) { throw "任务单必须在仓库内：$TaskFile" }
$taskRel = $taskFull.Substring($RepoRoot.Length).TrimStart('\').Replace('\', '/')

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$RunDir = Join-Path $RepoRoot "tmp\dev_loop\$stamp"
New-Item -ItemType Directory -Force $RunDir | Out-Null
$RunRel = "tmp/dev_loop/$stamp"

$coderTpl = [IO.File]::ReadAllText((Join-Path $PSScriptRoot "coder_prompt.md"), $utf8)
$reviewerTpl = [IO.File]::ReadAllText((Join-Path $PSScriptRoot "reviewer_prompt.md"), $utf8)

function Write-Utf8([string]$Path, [string]$Text) {
    [IO.File]::WriteAllText($Path, $Text, $utf8)
}

function Fill-Template([string]$Tpl, [hashtable]$Vars) {
    foreach ($k in $Vars.Keys) { $Tpl = $Tpl.Replace("{{$k}}", [string]$Vars[$k]) }
    return $Tpl
}

# 运行 git 并返回 stdout 行；git 往 stderr 写的提示（如换行符警告）不当作错误。
function Invoke-Git {
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { $out = & git -c core.quotepath=false @args 2>$null }
    finally { $ErrorActionPreference = $prevEap }
    return $out
}

# 临时设置环境变量调用 claude，结束后恢复原值。$null 表示删除该变量。
# 返回解析后的 JSON；用完工具轮数（error_max_turns）时不抛错，而是在返回对象上标记 dl_max_turns。
function Invoke-Claude([string]$Prompt, [string[]]$CliArgs, [hashtable]$EnvOverrides, [string]$LogFile) {
    $saved = @{}
    foreach ($k in $EnvOverrides.Keys) {
        $saved[$k] = [Environment]::GetEnvironmentVariable($k, "Process")
        [Environment]::SetEnvironmentVariable($k, $EnvOverrides[$k], "Process")
    }
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $raw = ($Prompt | & $ClaudeExe @CliArgs) -join "`n"
        $code = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $prevEap
        foreach ($k in $saved.Keys) { [Environment]::SetEnvironmentVariable($k, $saved[$k], "Process") }
    }
    Write-Utf8 $LogFile $raw
    if (-not $raw -or -not $raw.Trim()) { throw "claude 没有任何输出（退出码 $code），见 $LogFile" }
    try { $obj = $raw | ConvertFrom-Json } catch { $obj = $null }
    if (-not $obj) { throw "claude 输出不是 JSON（退出码 $code），见 $LogFile" }
    $maxTurns = ($obj.subtype -eq "error_max_turns")
    if (-not $maxTurns -and ($obj.is_error -or ($obj.subtype -and $obj.subtype -ne "success"))) {
        throw "claude 调用出错（$($obj.subtype)）：$($obj.result)（见 $LogFile）"
    }
    $obj | Add-Member -NotePropertyName dl_max_turns -NotePropertyValue $maxTurns -Force
    return $obj
}

# 编码方：先清掉所有 CLAUDE* / ANTHROPIC* 变量（在 Claude 桌面 App 或另一个 Claude Code
# 会话里运行时，子进程会继承宿主的登录认证，其优先级高于 ANTHROPIC_AUTH_TOKEN，
# 会把 Claude 的登录令牌发给 DeepSeek），再用独立的空配置目录，确保只有 DeepSeek key 可用。
$coderEnv = @{}
Get-ChildItem env: | Where-Object { $_.Name -match '^(CLAUDE|ANTHROPIC)' } | ForEach-Object { $coderEnv[$_.Name] = $null }
$CoderConfigDir = Join-Path $RepoRoot "tmp\dev_loop\.coder-config"
New-Item -ItemType Directory -Force $CoderConfigDir | Out-Null
$coderEnv["CLAUDE_CONFIG_DIR"] = $CoderConfigDir
$coderEnv["ANTHROPIC_BASE_URL"] = $(if ($env:DEV_LOOP_CODER_BASE_URL) { $env:DEV_LOOP_CODER_BASE_URL } else { "https://api.deepseek.com/anthropic" })
$coderEnv["ANTHROPIC_AUTH_TOKEN"] = $DeepseekKey
$coderEnv["ANTHROPIC_MODEL"] = $CoderModel
$coderEnv["ANTHROPIC_SMALL_FAST_MODEL"] = $CoderModel
$coderEnv["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = $CoderModel
$coderEnv["API_TIMEOUT_MS"] = "600000"
$coderEnv["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
$coderEnv["DEEPSEEK_API_KEY"] = $null
$coderEnv["PYTHONUTF8"] = "1"
$coderEnv["PYTHONIOENCODING"] = "utf-8"
$reviewerEnv = @{
    ANTHROPIC_BASE_URL            = $null
    ANTHROPIC_AUTH_TOKEN          = $null
    ANTHROPIC_MODEL               = $null
    ANTHROPIC_SMALL_FAST_MODEL    = $null
    ANTHROPIC_DEFAULT_HAIKU_MODEL = $null
    CLAUDECODE                    = $null
    DEEPSEEK_API_KEY              = $null
    PYTHONUTF8                    = "1"
    PYTHONIOENCODING              = "utf-8"
}

# 注意：两边都放行了 conda 的 python.exe，它能执行任意代码，所以下面的禁止规则只能防止
# 模型“直接敲 git 命令”，挡不住它用 python 绕过。真正的兜底是每轮结束后的 Assert-GitUnchanged。
$denyGit = @(
    "Bash(git commit:*)", "Bash(git push:*)", "Bash(git checkout:*)", "Bash(git switch:*)",
    "Bash(git stash:*)", "Bash(git reset:*)", "Bash(git rebase:*)", "Bash(git clean:*)", "Bash(rm -rf:*)"
)
$coderAllow = @(
    "Read", "Edit", "Write", "Glob", "Grep",
    "Bash(git status:*)", "Bash(git diff:*)", "Bash(git log:*)", "Bash(git show:*)",
    "Bash(ls:*)", "Bash(cat:*)", "Bash(head:*)", "Bash(tail:*)", "Bash(grep:*)", "Bash(find:*)",
    "Bash(D:/anacada/envs/commercial-agent/python.exe:*)",
    "Bash(echo:*)", "Bash(wc:*)", "Bash(file:*)", "Bash(diff:*)", "Bash(sort:*)"
)
$reviewerAllow = @(
    "Read", "Glob", "Grep",
    "Bash(git status:*)", "Bash(git diff:*)", "Bash(git log:*)", "Bash(git show:*)",
    "Bash(ls:*)", "Bash(cat:*)", "Bash(head:*)", "Bash(tail:*)", "Bash(grep:*)", "Bash(find:*)",
    "Bash(echo:*)", "Bash(wc:*)", "Bash(file:*)", "Bash(diff:*)", "Bash(sort:*)",
    "Bash(D:/anacada/envs/commercial-agent/python.exe:*)"
)

function Get-GitSnapshot {
    $st = (Invoke-Git status --porcelain -uall) -join "`n"
    $ds = (Invoke-Git diff --stat) -join "`n"
    return "## git status --porcelain -uall`n$st`n`n## git diff --stat`n$ds"
}

# 把整个工作区（含未跟踪文件，遵守 .gitignore）写成一个悬空提交：用临时索引，
# 不改工作区、不改真实索引、不动任何分支或 stash。审查方用 `git diff <前> <后> -- 文件` 看改动。
function New-WorktreeSnapshot([string]$Label) {
    $index = Join-Path $RunDir "snapshot-$Label.index"
    $savedIndex = $env:GIT_INDEX_FILE
    $env:GIT_INDEX_FILE = $index
    try {
        Invoke-Git read-tree HEAD | Out-Null
        Invoke-Git add -A -- . ":(exclude)tmp/dev_loop" | Out-Null
        $tree = (Invoke-Git write-tree) | Select-Object -First 1
    }
    finally {
        if ($savedIndex) { $env:GIT_INDEX_FILE = $savedIndex } else { Remove-Item Env:GIT_INDEX_FILE -ErrorAction SilentlyContinue }
        Remove-Item $index -Force -ErrorAction SilentlyContinue
    }
    if (-not $tree) { throw "生成工作区快照失败（$Label）" }
    $commit = (Invoke-Git -c user.name=dev_loop -c user.email=dev_loop@localhost commit-tree $tree -p HEAD -m "dev_loop snapshot $Label") |
        Select-Object -First 1
    if (-not $commit) { throw "生成快照提交失败（$Label）" }
    Add-Content -Path (Join-Path $RunDir "snapshots.txt") -Encoding UTF8 -Value "$Label $commit"
    return $commit
}

# 工作区里所有“脏”文件 -> 内容哈希，用来算出相对基线真正新增或变化的文件
function Get-DirtyMap {
    $lines = Invoke-Git status --porcelain -uall
    $map = @{}
    foreach ($l in $lines) {
        if ($l.Length -lt 4) { continue }
        $path = $l.Substring(3)
        if ($path -match ' -> ') { $path = ($path -split ' -> ')[-1] }
        $path = $path.Trim('"')
        if ($path -like 'tmp/dev_loop/*') { continue }
        $full = Join-Path $RepoRoot $path
        if (Test-Path $full -PathType Leaf) { $map[$path] = (Get-FileHash $full -Algorithm SHA256).Hash }
        else { $map[$path] = "<deleted>" }
    }
    return $map
}

function Get-DeltaText([hashtable]$Base, [hashtable]$Now) {
    $out = New-Object System.Collections.Generic.List[string]
    foreach ($p in ($Now.Keys | Sort-Object)) {
        if (-not $Base.ContainsKey($p)) { $out.Add("新增改动  $p") }
        elseif ($Base[$p] -ne $Now[$p]) { $out.Add("再次修改  $p") }
    }
    foreach ($p in ($Base.Keys | Sort-Object)) {
        if (-not $Now.ContainsKey($p)) { $out.Add("被还原    $p") }
    }
    if ($out.Count -eq 0) { return "（相对循环开始前没有任何文件变化）" }
    return ($out -join "`n")
}

# 提交、切分支、stash 都会改动这三样；任何一样变了就停止循环。
function Get-GitGuardState {
    return [ordered]@{
        HEAD   = ((Invoke-Git rev-parse HEAD) | Select-Object -First 1)
        Branch = ((Invoke-Git symbolic-ref -q HEAD) | Select-Object -First 1)
        Stash  = ((Invoke-Git stash list) -join "`n")
    }
}

function Assert-GitUnchanged([string]$Who) {
    $now = Get-GitGuardState
    $bad = @()
    foreach ($k in $GuardBaseline.Keys) {
        if ([string]$now[$k] -ne [string]$GuardBaseline[$k]) { $bad += "$k：$($GuardBaseline[$k]) -> $($now[$k])" }
    }
    if ($bad.Count -gt 0) {
        throw "护栏触发：$Who 运行后 git 状态被改动（$($bad -join '；')）。请人工检查，必要时恢复。"
    }
}

function Invoke-Tests([int]$Round) {
    if ($SkipTests) { return @{ Code = 0; Tail = "（已用 -SkipTests 跳过测试）" } }
    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"
    Push-Location (Join-Path $RepoRoot $TestWorkDir)
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $out = cmd /c "$TestCommand 2>&1"
        $code = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $prevEap
        Pop-Location
    }
    $all = ($out -join "`n")
    Write-Utf8 (Join-Path $RunDir "round-$Round-tests.txt") $all
    $tail = (($out | Select-Object -Last $TestTailLines) -join "`n")
    return @{ Code = $code; Tail = $tail }
}

# ---------------------------------------------------------------- 基线
# 运行前的工作区状态，供审查方区分“本次改动”和“之前就有的未提交改动”
$BaselineRel = "$RunRel/baseline-git.txt"
Write-Utf8 (Join-Path $RunDir "baseline-git.txt") (Get-GitSnapshot)
$BaselineMap = Get-DirtyMap
$BaselineCommit = New-WorktreeSnapshot "baseline"
$GuardBaseline = Get-GitGuardState
Write-Host "基线快照：$BaselineCommit"

# ---------------------------------------------------------------- 主循环
Write-Host "任务单：$taskRel"
Write-Host "日志目录：$RunRel"
$coderSession = $null
$reviewerSession = $null
$prevReviewRel = $null
$approved = $false
$failure = $null
$round = 0
$summary = New-Object System.Collections.Generic.List[string]
$summary.Add("# dev_loop $stamp")
$summary.Add("")
$summary.Add("- 任务单：``$taskRel``")
$summary.Add("- 编码方：$CoderModel；审查方：$(if ($ReviewerModel) { $ReviewerModel } else { 'Claude 默认模型' })")
$summary.Add("- 基线快照：``$BaselineCommit``")
$summary.Add("")

try {
    for ($round = 1; $round -le $MaxRounds; $round++) {
        Write-Host ""
        Write-Host "========== 第 $round 轮：编码（$CoderModel） ==========" -ForegroundColor Cyan

        if ($prevReviewRel) {
            $reviewSection = "- 上一轮审查意见：``$prevReviewRel``。请先阅读，逐条处理其中「必须修」的条目。"
        }
        else {
            $reviewSection = "- 这是第一轮，没有审查意见。"
        }
        $coderPrompt = Fill-Template $coderTpl @{ TASK_FILE = $taskRel; ROUND = $round; REVIEW_SECTION = $reviewSection }

        $cArgs = @("-p", "--output-format", "json", "--max-turns", "$CoderMaxTurns")
        if ($CoderSkipPermissions) {
            $cArgs += "--dangerously-skip-permissions"
        }
        else {
            $cArgs += @("--permission-mode", "acceptEdits", "--allowedTools") + $coderAllow
        }
        $cArgs += @("--disallowedTools") + $denyGit
        if ($coderSession) { $cArgs += @("--resume", $coderSession) }

        $coder = Invoke-Claude $coderPrompt $cArgs $coderEnv (Join-Path $RunDir "round-$round-coder.json")
        if ($coder.session_id) { $coderSession = $coder.session_id }
        $coderText = [string]$coder.result
        if ($coder.dl_max_turns) {
            $coderText = "（调度脚本补充：编码方用完了 $CoderMaxTurns 次工具调用，本轮可能没做完。以下是它最后的输出，可能为空。）`n`n$coderText"
            Write-Host "编码方用完工具轮数，继续测试与审查。" -ForegroundColor Yellow
        }
        Write-Utf8 (Join-Path $RunDir "round-$round-coder.md") $coderText
        Write-Host $coderText
        Assert-GitUnchanged "第 $round 轮编码方"

        Write-Host "---------- 运行测试 ----------" -ForegroundColor Cyan
        $t = Invoke-Tests $round
        Write-Host "测试退出码：$($t.Code)"

        Write-Host "========== 第 $round 轮：审查（Claude） ==========" -ForegroundColor Magenta
        if ($prevReviewRel) {
            $prevSection = "`n- 上一轮你给出的审查意见：``$prevReviewRel``（检查是否都已处理）。"
        }
        else {
            $prevSection = ""
        }
        $roundCommit = New-WorktreeSnapshot "round-$round"
        $delta = Get-DeltaText $BaselineMap (Get-DirtyMap)
        Write-Utf8 (Join-Path $RunDir "round-$round-git.txt") ("## 相对基线的变化（快照 $BaselineCommit -> $roundCommit）`n$delta`n`n" + (Get-GitSnapshot))
        $reviewerPrompt = Fill-Template $reviewerTpl @{
            GIT_SNAPSHOT        = $delta
            BASELINE_STATUS     = $BaselineRel
            BASELINE_COMMIT     = $BaselineCommit
            ROUND_COMMIT        = $roundCommit
            TASK_FILE           = $taskRel
            ROUND               = $round
            CODER_SUMMARY       = $coderText
            TEST_EXIT           = $t.Code
            TEST_OUTPUT         = $t.Tail
            PREV_REVIEW_SECTION = $prevSection
        }
        $rArgs = @("-p", "--output-format", "json", "--max-turns", "$ReviewerMaxTurns",
            "--allowedTools") + $reviewerAllow + @("--disallowedTools", "Edit", "Write", "NotebookEdit") + $denyGit
        if ($ReviewerModel) { $rArgs += @("--model", $ReviewerModel) }

        $reviewer = Invoke-Claude $reviewerPrompt $rArgs $reviewerEnv (Join-Path $RunDir "round-$round-reviewer.json")
        $reviewerSession = $reviewer.session_id
        Assert-GitUnchanged "第 $round 轮审查方"
        $reviewFile = Join-Path $RunDir "round-$round-review.md"
        if ($reviewer.dl_max_turns) {
            Write-Utf8 $reviewFile ([string]$reviewer.result)
            throw "审查方用完了 $ReviewerMaxTurns 次工具调用，没有给出结论。可加大 -ReviewerMaxTurns 后重跑，或用 claude --resume $reviewerSession 接着审查。"
        }
        Write-Utf8 $reviewFile $reviewer.result
        $prevReviewRel = "$RunRel/round-$round-review.md"
        Write-Host $reviewer.result

        $lastLine = [string](([string]$reviewer.result -split "`n") | Where-Object { $_.Trim() } | Select-Object -Last 1)
        $verdictApproved = ($lastLine -match "VERDICT:\s*APPROVED")
        $ok = $verdictApproved -and ($t.Code -eq 0)
        $summary.Add("- 第 $round 轮：测试退出码 $($t.Code)；审查结论 ``$($lastLine.Trim())``；快照 ``$roundCommit``")

        if ($ok) { $approved = $true; break }
        if ($verdictApproved -and ($t.Code -ne 0)) {
            Add-Content -Path $reviewFile -Encoding UTF8 -Value "`n`n> 调度脚本补充：审查方给了 APPROVED，但测试退出码为 $($t.Code)，视为不通过。请先让测试通过。"
        }
    }
}
catch {
    $failure = $_.Exception.Message
}
finally {
    $summary.Add("")
    $summary.Add("- 编码方会话：``$coderSession``（配置目录 ``tmp/dev_loop/.coder-config``）")
    $summary.Add("- 最后一次审查会话：``$reviewerSession``")
    $summary.Add("")
    if ($failure) {
        $summary.Add("**结果：第 $round 轮中途停止。** $failure")
    }
    elseif ($approved) {
        $summary.Add("**结果：审查通过。** 请自行检查 ``git diff`` 后再提交。")
    }
    else {
        $summary.Add("**结果：$MaxRounds 轮内未通过。** 最新审查意见：``$prevReviewRel``。")
    }
    Write-Utf8 (Join-Path $RunDir "summary.md") ($summary -join "`n")
}

Write-Host ""
if ($failure) {
    Write-Host "第 $round 轮中途停止：$failure" -ForegroundColor Red
    Write-Host "日志：$RunRel/summary.md" -ForegroundColor Red
    exit 2
}
if ($approved) {
    Write-Host "审查通过（第 $round 轮）。改动未提交，请检查 git diff 后自行 commit。" -ForegroundColor Green
    exit 0
}
Write-Host "达到 $MaxRounds 轮上限仍未通过，需要你介入。日志：$RunRel" -ForegroundColor Yellow
exit 1
