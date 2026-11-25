<#
.SYNOPSIS
  让 DeepSeek（经 Claude Code 命令行）按一份复查 Prompt 做一次只读独立复查，报告由脚本写盘。

.DESCRIPTION
  dev_loop.ps1 是“DeepSeek 编码 → Claude 审查”；本脚本补上反方向：Claude（或人）改完之后，
  由 DeepSeek 独立复查。这样复查 Prompt 写好后，可以由 Claude Code 会话直接调用本脚本，
  不需要用户在两个模型之间转交。

  - 复查方只读：禁用 Edit / Write；最终回复就是完整报告，由脚本保存到 -ReportFile。
  - 实验（复制代码做变异等）只能在仓库外的临时目录做（脚本创建并通过 --add-dir 放行）。
  - 运行前后各拍一次工作区快照，并核对 HEAD / 分支 / stash：只要仓库被改动，就以退出码 2
    结束，并列出被改的文件（报告仍会保存，供排查）。

.EXAMPLE
  .\scripts\dev_loop\dev_review.ps1 -PromptFile docs\handoffs\REVIEW_TASK035_PROMPT.md -ReportFile docs\reviews\2026-11-24_task035_independent_review.md

.NOTES
  退出码：0 复查完成且仓库未被改动；1 参数或前置检查失败（例如报告已存在、找不到 key）；
  2 复查出错、用完轮数、没有报告正文或仓库被改动。
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$PromptFile,
    [Parameter(Mandatory = $true)][string]$ReportFile,
    [string]$Model = "deepseek-flash",
    [int]$MaxTurns = 150,
    [string[]]$AddDirs = @(),
    [switch]$Overwrite,
    # 上一次复查用完工具调用、没给出报告时：接着同一会话（保留已做的调查），只要求它写出报告
    [string]$ResumeSession = "",
    [string]$ClaudeExe = ""
)

$ErrorActionPreference = "Stop"
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
[Console]::InputEncoding = $utf8
$OutputEncoding = $utf8

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

# ---------------------------------------------------------------- 前置检查
if (-not $ClaudeExe) {
    $cmd = Get-Command claude -ErrorAction SilentlyContinue
    if ($cmd) { $ClaudeExe = $cmd.Source }
    else {
        $bundled = Get-ChildItem (Join-Path $env:LOCALAPPDATA "Claude-Data") -Recurse -Filter "claude.exe" -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match '\\claude-code\\' } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($bundled) { $ClaudeExe = $bundled.FullName }
    }
}
if (-not $ClaudeExe -or -not (Test-Path $ClaudeExe)) { throw "找不到 claude 命令行，用 -ClaudeExe 指定。" }

$DeepseekKey = $env:DEEPSEEK_API_KEY
if (-not $DeepseekKey) {
    $dotenv = Join-Path $RepoRoot ".env"
    if (Test-Path $dotenv) {
        $line = Get-Content $dotenv -Encoding UTF8 | Where-Object { $_ -match '^\s*DEEPSEEK_API_KEY\s*=' } | Select-Object -First 1
        if ($line) { $DeepseekKey = ($line -replace '^\s*DEEPSEEK_API_KEY\s*=\s*', '').Trim().Trim('"').Trim("'") }
    }
}
if (-not $DeepseekKey) { throw "未找到 DEEPSEEK_API_KEY（环境变量和仓库 .env 中都没有）。" }

function Get-RepoRelative([string]$Path, [switch]$MustExist) {
    $full = if ($MustExist) { (Resolve-Path $Path).Path } else { [IO.Path]::GetFullPath((Join-Path $RepoRoot $Path)) }
    if (-not $full.StartsWith($RepoRoot + '\')) { throw "路径必须在仓库内：$Path" }
    return $full.Substring($RepoRoot.Length).TrimStart('\').Replace('\', '/')
}
$promptRel = Get-RepoRelative $PromptFile -MustExist
$reportRel = Get-RepoRelative $ReportFile
$reportFull = Join-Path $RepoRoot $reportRel
if ((Test-Path $reportFull) -and -not $Overwrite) { throw "报告已存在：$reportRel（确需覆盖时加 -Overwrite）" }

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$RunDir = Join-Path $RepoRoot "tmp\dev_loop\review-$stamp"
New-Item -ItemType Directory -Force $RunDir | Out-Null
$RunRel = "tmp/dev_loop/review-$stamp"
# 仓库外的实验目录：复查方可以在这里复制代码、做变异
$ScratchDir = Join-Path $env:TEMP "dev_review\$stamp"
New-Item -ItemType Directory -Force $ScratchDir | Out-Null

function Write-Utf8([string]$Path, [string]$Text) {
    $dir = Split-Path $Path -Parent
    if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }
    [IO.File]::WriteAllText($Path, ($Text -replace "`r`n", "`n"), $utf8)
}

function Invoke-Git {
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { $out = & git -c core.quotepath=false @args 2>$null }
    finally { $ErrorActionPreference = $prevEap }
    return $out
}

# 与 dev_loop.ps1 相同：临时索引把整个工作区（含未跟踪文件，遵守 .gitignore）写成悬空提交
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
    return $tree
}

function Get-GitGuardState {
    return [ordered]@{
        HEAD   = ((Invoke-Git rev-parse HEAD) | Select-Object -First 1)
        Branch = ((Invoke-Git symbolic-ref -q HEAD) | Select-Object -First 1)
        Stash  = ((Invoke-Git stash list) -join "`n")
    }
}

# 与 dev_loop.ps1 的编码方相同的认证隔离：清掉宿主的 CLAUDE* / ANTHROPIC*，只给 DeepSeek key
$reviewEnv = @{}
Get-ChildItem env: | Where-Object { $_.Name -match '^(CLAUDE|ANTHROPIC)' } | ForEach-Object { $reviewEnv[$_.Name] = $null }
$ConfigDir = Join-Path $RepoRoot "tmp\dev_loop\.coder-config"
New-Item -ItemType Directory -Force $ConfigDir | Out-Null
$reviewEnv["CLAUDE_CONFIG_DIR"] = $ConfigDir
$reviewEnv["ANTHROPIC_BASE_URL"] = $(if ($env:DEV_LOOP_CODER_BASE_URL) { $env:DEV_LOOP_CODER_BASE_URL } else { "https://api.deepseek.com/anthropic" })
$reviewEnv["ANTHROPIC_AUTH_TOKEN"] = $DeepseekKey
$reviewEnv["ANTHROPIC_MODEL"] = $Model
$reviewEnv["ANTHROPIC_SMALL_FAST_MODEL"] = $Model
$reviewEnv["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = $Model
$reviewEnv["API_TIMEOUT_MS"] = "600000"
$reviewEnv["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
$reviewEnv["DEEPSEEK_API_KEY"] = $null
$reviewEnv["PYTHONUTF8"] = "1"
$reviewEnv["PYTHONIOENCODING"] = "utf-8"

$allow = @(
    "Read", "Glob", "Grep",
    "Bash(git status:*)", "Bash(git diff:*)", "Bash(git log:*)", "Bash(git show:*)", "Bash(git rev-parse:*)", "Bash(git ls-files:*)",
    "Bash(ls:*)", "Bash(cat:*)", "Bash(head:*)", "Bash(tail:*)", "Bash(grep:*)", "Bash(find:*)", "Bash(sha256sum:*)",
    "Bash(echo:*)", "Bash(wc:*)", "Bash(file:*)", "Bash(diff:*)", "Bash(sort:*)", "Bash(cp:*)", "Bash(mkdir:*)",
    "Bash(D:/anacada/envs/commercial-agent/python.exe:*)"
)
$deny = @(
    "Edit", "Write", "NotebookEdit",
    "Bash(git commit:*)", "Bash(git push:*)", "Bash(git checkout:*)", "Bash(git switch:*)", "Bash(git add:*)",
    "Bash(git stash:*)", "Bash(git reset:*)", "Bash(git rebase:*)", "Bash(git clean:*)", "Bash(rm -rf:*)", "Bash(pip:*)"
)

$addDirArgs = @("--add-dir", $ScratchDir)
$AddDirs = @($AddDirs | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })
foreach ($d in $AddDirs) {
    if (-not (Test-Path $d -PathType Container)) { throw "-AddDirs 目录不存在：$d" }
    $addDirArgs += @("--add-dir", (Resolve-Path $d).Path)
}

$tpl = [IO.File]::ReadAllText((Join-Path $PSScriptRoot "independent_review_prompt.md"), $utf8)
$prompt = $tpl.Replace("{{PROMPT_FILE}}", $promptRel).Replace("{{REPORT_FILE}}", $reportRel).Replace("{{SCRATCH_DIR}}", $ScratchDir.Replace('\', '/'))
if ($ResumeSession) {
    $prompt = "你在上一段已经用完了工具调用次数，还没有给出报告。现在不要再调用任何工具，" +
        "直接根据你已经做过的调查，按复查 Prompt（$promptRel）第 5 节的格式输出完整报告正文，第一行是一级标题。" +
        "没来得及验证的项目如实写进「本轮限制」并标明未验证，不要把推测写成结论。" +
        "另外如实说明实验是否在 PG 测试库留下了临时角色或数据（调度方观察到留下了 6 个 ro_log_* 角色，已清理）。"
}

# ---------------------------------------------------------------- 运行
$before = New-WorktreeSnapshot "before"
$guard = Get-GitGuardState
Write-Host "复查 Prompt：$promptRel"
Write-Host "报告：$reportRel"
Write-Host "实验目录（仓库外）：$ScratchDir"
Write-Host "日志：$RunRel"

$resumeArgs = if ($ResumeSession) { @("--resume", $ResumeSession) } else { @() }
$cliArgs = @("-p", "--output-format", "json", "--max-turns", "$MaxTurns") + $resumeArgs + $addDirArgs +
    @("--permission-mode", "default", "--allowedTools") + $allow + @("--disallowedTools") + $deny

$saved = @{}
foreach ($k in $reviewEnv.Keys) {
    $saved[$k] = [Environment]::GetEnvironmentVariable($k, "Process")
    [Environment]::SetEnvironmentVariable($k, $reviewEnv[$k], "Process")
}
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
try {
    $raw = ($prompt | & $ClaudeExe @cliArgs 2>$null) -join "`n"
    $code = $LASTEXITCODE
}
finally {
    $ErrorActionPreference = $prevEap
    foreach ($k in $saved.Keys) { [Environment]::SetEnvironmentVariable($k, $saved[$k], "Process") }
}
Write-Utf8 (Join-Path $RunDir "review.json") $raw

$problems = New-Object System.Collections.Generic.List[string]
$obj = $null
if ($raw -and $raw.Trim()) { try { $obj = $raw | ConvertFrom-Json } catch { $obj = $null } }
if (-not $obj) { $problems.Add("claude 输出不是 JSON（退出码 $code），见 $RunRel/review.json") }
elseif ($obj.subtype -eq "error_max_turns") { $problems.Add("复查方用完了 $MaxTurns 次工具调用，报告可能不完整；可用 claude --resume $($obj.session_id) 接着做（配置目录 tmp/dev_loop/.coder-config）") }
elseif ($obj.is_error -or ($obj.subtype -and $obj.subtype -ne "success")) { $problems.Add("claude 调用出错（$($obj.subtype)）：$($obj.result)") }

# 仓库必须原样：先核对，再写报告（报告本身不算改动）
$after = New-WorktreeSnapshot "after"
$changed = @(Invoke-Git diff --name-only $before $after)
if ($changed.Count -gt 0) { $problems.Add("复查方改动了仓库文件：" + ($changed -join "，")) }
$now = Get-GitGuardState
foreach ($k in $guard.Keys) {
    if ([string]$now[$k] -ne [string]$guard[$k]) { $problems.Add("git 状态被改动：$k $($guard[$k]) -> $($now[$k])") }
}

$report = if ($obj) { [string]$obj.result } else { "" }
# 只保留从第一个一级标题开始的正文（去掉模型可能加的开场白）
$lines = $report -split "`n"
$start = [Array]::FindIndex($lines, [Predicate[string]] { param($l) $l -match '^# ' })
if ($start -gt 0) { $report = ($lines[$start..($lines.Count - 1)] -join "`n") }
if ($report.Trim()) {
    Write-Utf8 $reportFull ($report.TrimEnd() + "`n")
    Write-Host "报告已保存：$reportRel"
}
else { $problems.Add("复查方没有给出报告正文") }

if ($obj) {
    $u = $obj.usage
    Write-Host ("用量：{0} 轮，{1:N0} 秒；输入 {2}，缓存命中 {3}，输出 {4} token" -f $obj.num_turns, ($obj.duration_ms / 1000), $u.input_tokens, $u.cache_read_input_tokens, $u.output_tokens)
    $denials = @($obj.permission_denials)
    if ($denials.Count -gt 0) { Write-Host "被拒绝的工具调用：$($denials.Count) 次（详见 $RunRel/review.json）" }
}

if ($problems.Count -gt 0) {
    Write-Utf8 (Join-Path $RunDir "problems.txt") ($problems -join "`n")
    foreach ($p in $problems) { Write-Host "问题：$p" -ForegroundColor Red }
    exit 2
}
Write-Host "复查完成，仓库未被改动。报告未提交，请阅读后再决定。" -ForegroundColor Green
exit 0
