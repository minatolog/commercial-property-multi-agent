# dev_loop：自动编码 / 审查循环

把“DeepSeek 写代码 → Claude 审查 → DeepSeek 按意见修改 → 再审查”的来回粘贴交给脚本完成。

## 工作方式

每一轮：

1. **编码**：用 Claude Code 命令行、以 DeepSeek 为后端（`https://api.deepseek.com/anthropic`）运行，按任务单实施；从第 2 轮起接着同一个会话（`--resume`），读取上一轮审查意见逐条修复。
2. **测试**：脚本自己运行测试（默认 `backend/` 下的 unittest），结果原样交给审查方，不依赖编码方的自述。
3. **审查**：用 Claude Code 命令行、以 Claude 模型运行，只读（禁用 Edit / Write），最后一行输出 `VERDICT: APPROVED` 或 `VERDICT: CHANGES_REQUESTED`。
4. 审查通过 **且** 测试退出码为 0，循环结束；否则进入下一轮，最多 `-MaxRounds` 轮（默认 5）。

两边都禁止 `git commit / push / checkout / switch / stash / reset / rebase / clean`。脚本结束时改动留在工作区，由你检查后自己提交。

两个保证由脚本自己完成，不依赖模型的自述：

- **测试**：每轮由脚本运行，退出码不为 0 就不算通过。
- **改动范围**：运行前用临时索引把整个工作区（含未跟踪文件，遵守 `.gitignore`）写成一个悬空提交作为基线快照，每轮审查前再拍一个；不改工作区、不改真实索引、不动分支和 stash。同时记录所有脏文件的哈希，每轮把“相对基线新增或变化的文件”清单交给审查方，审查方用 `git diff <基线快照> <本轮快照> -- <文件>` 只看本次改动。快照哈希记录在日志目录的 `snapshots.txt`。
- **git 护栏**：每次编码方、审查方运行后，检查 HEAD、当前分支、stash 列表是否与开始时一致；任何一项变了就立即停止（退出码 2）。

### 这些限制是“建议”，不是沙箱

两边都放行了 conda 的 `python.exe`（编码方要跑测试、审查方要复核），而 python 能执行任意代码。因此：

- `--disallowedTools` 里禁止的 git 命令只能挡住模型直接敲命令，挡不住 `python -c "import subprocess; ..."`。提交、切分支、stash 由上面的 git 护栏在事后发现；改工作区以外的东西（例如 `data/`、用户目录）脚本发现不了。
- “不调付费接口”只靠提示词约束：脚本已不把 `DEEPSEEK_API_KEY` 传给两边的子进程，但项目代码会自己读仓库根目录的 `.env`；编码方进程里的 `ANTHROPIC_AUTH_TOKEN` 本身也是 DeepSeek key。
- 认证隔离只保证编码方的请求头里不会误带 Claude 登录令牌；编码方用 python 仍然读得到本机文件。
- 审查方的“只读”同理，只是禁用了 Edit / Write。

只在你信任两边模型、且工作区可随时恢复的前提下使用。

## 准备

1. **claude 命令行**：PATH 里有 `claude` 就用它；没有时自动使用 Claude 桌面 App 自带的 `claude.exe`；也可以用 `-ClaudeExe` 指定路径。
   审查方使用**本机 claude 命令行自己的登录**（`~/.claude`），不借用桌面 App 的会话。运行前在终端里确认：`claude auth status` 应显示 `"loggedIn": true`；没登录先运行一次 `claude` 按提示登录。审查用量计入你的 Claude 订阅额度。
2. **DeepSeek key**：读环境变量 `DEEPSEEK_API_KEY`，没有时读仓库根目录 `.env` 里的同名项。

### 认证隔离（重要）

在 Claude 桌面 App 或另一个 Claude Code 会话里运行时，子进程会继承宿主的登录认证，其优先级高于 `ANTHROPIC_AUTH_TOKEN`，**会把 Claude 登录令牌发给 DeepSeek**。脚本因此在启动编码方前清空所有 `CLAUDE*` / `ANTHROPIC*` 环境变量，并使用独立配置目录 `tmp/dev_loop/.coder-config`。修改这部分代码后，可以把 `DEV_LOOP_CODER_BASE_URL` 指向本地假服务器，检查实际发出的认证头。

审查方同样清空宿主注入的 `CLAUDE*` / `ANTHROPIC*` 变量（桌面 App 会注入宿主会话 ID、消息管道、宿主认证刷新等），只保留你自己设的 `CLAUDE_CONFIG_DIR` 与 `ANTHROPIC_API_KEY`。

### 已验证的部分（2026-11-23）

在临时仓库里用真实 `claude.exe`（2.1.330）跑编码方，`DEV_LOOP_CODER_BASE_URL` 指向本地假 Anthropic 服务器，审查方用假脚本代替（未调用任何真实模型）：

- 编码方每个请求只带 `Authorization: Bearer <DeepSeek key>`，没有 `x-api-key`、没有 Claude 令牌；子进程里没有 `DEEPSEEK_API_KEY`；也没有标题生成之类的额外请求。
- 权限规则：`Bash(D:/anacada/envs/commercial-agent/python.exe:*)` 能放行；`git commit` 被拒绝；`acceptEdits` 下 Write 可用。
- 第 2 轮 `--resume` 能接上第 1 轮的会话；提示词开头没有 BOM。
- 用完工具轮数时 CLI 输出 `subtype: "error_max_turns"`、`is_error: true`、带 `session_id`，脚本按预期继续测试与审查。
- 清空宿主变量后，`claude auth status` 仍显示已登录，审查方可以独立认证。

**仍未验证**：真实 DeepSeek 接口（模型名与长时间工具调用的兼容性）与真实 Claude 审查。CLI 会在 stderr 提示 `unrecognized_model`，可以忽略；JSON 里的费用估计不准（见“日志”）。

## 用法

先按以往的格式写好任务单（例如 `docs/handoffs/DEEPSEEK_TASK035_XXX_PROMPT.md`），然后在仓库根目录运行：

```powershell
.\scripts\dev_loop\dev_loop.ps1 -TaskFile docs\handoffs\DEEPSEEK_TASK035_XXX_PROMPT.md
```

常用参数：

| 参数 | 默认值 | 说明 |
|---|---|---|
| `-MaxRounds` | 5 | 最多循环几轮 |
| `-CoderModel` | `deepseek-flash` | DeepSeek 模型名（可用名称以 `https://api.deepseek.com/models` 为准；2026-11-23 该 key 只有 `deepseek-flash`、`deepseek-v4-pro`） |
| `-ReviewerModel` | 空（Claude 默认模型） | 例如 `opus`、`sonnet` |
| `-CoderMaxTurns` / `-ReviewerMaxTurns` | 80 / 40 | 单次调用的最大工具轮数 |
| `-TestCommand` | conda 环境的 unittest | 在 `-TestWorkDir`（默认 `backend`）下执行 |
| `-SkipTests` | 关 | 不运行测试（例如纯文档任务） |
| `-AddDirs` | 空 | 仓库外需要读取的目录（例如 `D:nacada\envs\commercial-agent\Lib\site-packages\mcp`），逗号分隔；编码方与审查方都可访问 |
| `-CoderSkipPermissions` | 关 | 编码方跳过所有权限检查；默认只放行读写文件、git 只读命令和 conda Python |

## 日志

每次运行写到 `tmp/dev_loop/<时间戳>/`（已加入 `.gitignore`）：

- `round-N-coder.md` / `round-N-review.md`：编码方总结、审查意见
- `round-N-tests.txt`：完整测试输出
- `round-N-*.json`：命令行原始输出（含 session_id、费用估计）
- `round-N-git.txt`：本轮相对基线的变化清单与 git 状态
- `snapshots.txt`：基线与每轮快照的提交哈希
- `summary.md`：每轮结论汇总、编码方 / 审查方会话 ID；中途出错或护栏触发时也会写出

退出码：0 审查通过；1 达到轮数上限仍未通过；2 中途出错（例如审查方用完工具轮数）或 git 护栏触发。编码方用完工具轮数不会中止，会照常测试并交给审查方，由审查方判断是否做完。

注意：编码方 JSON 里的 `total_cost_usd` 是按 Claude 价格估算的，对 DeepSeek 不准，实际费用以 DeepSeek 后台为准。

## dev_review：DeepSeek 独立复查（反方向）

`dev_loop.ps1` 是“DeepSeek 编码 → Claude 审查”。Claude（或人）改完代码后的**独立复查**由 `dev_review.ps1` 完成：DeepSeek 按一份复查 Prompt 做一次只读复查，报告由脚本保存。复查 Prompt 写好后，Claude Code 会话可以直接调用它，不需要用户在两个模型之间转交。

```powershell
.\scripts\dev_loop\dev_review.ps1 -PromptFile docs\handoffs\REVIEW_TASK035_PROMPT.md -ReportFile docseviews6-11-24_task035_independent_review.md
```

| 参数 | 默认值 | 说明 |
|---|---|---|
| `-Model` | `deepseek-flash` | 复查方模型 |
| `-MaxTurns` | 150 | 工具调用上限 |
| `-AddDirs` | 空 | 仓库外需要读取的目录，逗号分隔 |
| `-Overwrite` | 关 | 报告已存在时覆盖（默认拒绝） |

- **只读**：禁用 Edit / Write / `git add` / `pip`；复查方的最终回复就是报告正文，脚本只保留从第一个 `# ` 标题开始的部分，统一为 LF。
- **实验目录**：脚本在 `%TEMP%\dev_review\<时间戳>` 建一个仓库外目录并用 `--add-dir` 放行，变异测试、临时脚本、评测输出都写在那里。
- **核对**：运行前后各拍一次工作区快照，并核对 HEAD / 分支 / stash；仓库有任何改动 → 退出码 2 并列出文件（报告仍保存，供排查）。与 dev_loop 一样，放行了 python 就只是“事后发现”，不是沙箱。
- **认证隔离**与 dev_loop 编码方相同（清空宿主 `CLAUDE*` / `ANTHROPIC*`，独立配置目录，只给 DeepSeek key）。
- 退出码：0 完成且仓库未改；1 参数或前置检查失败；2 出错 / 用完轮数 / 无报告 / 仓库被改动。日志在 `tmp/dev_loop/review-<时间戳>/`。
- 复查方模板：[`independent_review_prompt.md`](independent_review_prompt.md)。

## 调整提示词

- 编码方：[`coder_prompt.md`](coder_prompt.md)
- 审查方：[`reviewer_prompt.md`](reviewer_prompt.md)

模板里的 `{{...}}` 占位符由脚本填充。项目约束（不碰 `data/`、不调付费接口、conda Python 路径等）写在模板里，按需修改即可。
