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
- **改动范围**：运行前用 `git stash create` 给工作区拍快照（不改工作区、不进 stash 列表），并记录所有脏文件的哈希；每轮把“相对快照新增或变化的文件”清单交给审查方，审查方用 `git diff <快照> -- <文件>` 只看本次改动。

## 准备

1. **claude 命令行**：PATH 里有 `claude` 就用它；没有时自动使用 Claude 桌面 App 自带的 `claude.exe`；也可以用 `-ClaudeExe` 指定路径。审查方使用你的 Claude 登录。
2. **DeepSeek key**：读环境变量 `DEEPSEEK_API_KEY`，没有时读仓库根目录 `.env` 里的同名项。

### 认证隔离（重要）

在 Claude 桌面 App 或另一个 Claude Code 会话里运行时，子进程会继承宿主的登录认证，其优先级高于 `ANTHROPIC_AUTH_TOKEN`，**会把 Claude 登录令牌发给 DeepSeek**。脚本因此在启动编码方前清空所有 `CLAUDE*` / `ANTHROPIC*` 环境变量，并使用独立配置目录 `tmp/dev_loop/.coder-config`。修改这部分代码后，可以把 `DEV_LOOP_CODER_BASE_URL` 指向本地假服务器，检查实际发出的认证头。

## 用法

先按以往的格式写好任务单（例如 `docs/handoffs/DEEPSEEK_TASK035_XXX_PROMPT.md`），然后在仓库根目录运行：

```powershell
.\scripts\dev_loop\dev_loop.ps1 -TaskFile docs\handoffs\DEEPSEEK_TASK035_XXX_PROMPT.md
```

常用参数：

| 参数 | 默认值 | 说明 |
|---|---|---|
| `-MaxRounds` | 5 | 最多循环几轮 |
| `-CoderModel` | `deepseek-chat` | DeepSeek 模型名 |
| `-ReviewerModel` | 空（Claude 默认模型） | 例如 `opus`、`sonnet` |
| `-CoderMaxTurns` / `-ReviewerMaxTurns` | 80 / 40 | 单次调用的最大工具轮数 |
| `-TestCommand` | conda 环境的 unittest | 在 `-TestWorkDir`（默认 `backend`）下执行 |
| `-SkipTests` | 关 | 不运行测试（例如纯文档任务） |
| `-CoderSkipPermissions` | 关 | 编码方跳过所有权限检查；默认只放行读写文件、git 只读命令和 conda Python |

## 日志

每次运行写到 `tmp/dev_loop/<时间戳>/`（已加入 `.gitignore`）：

- `round-N-coder.md` / `round-N-review.md`：编码方总结、审查意见
- `round-N-tests.txt`：完整测试输出
- `round-N-*.json`：命令行原始输出（含 session_id、费用估计）
- `summary.md`：每轮结论汇总

注意：编码方 JSON 里的 `total_cost_usd` 是按 Claude 价格估算的，对 DeepSeek 不准，实际费用以 DeepSeek 后台为准。

## 调整提示词

- 编码方：[`coder_prompt.md`](coder_prompt.md)
- 审查方：[`reviewer_prompt.md`](reviewer_prompt.md)

模板里的 `{{...}}` 占位符由脚本填充。项目约束（不碰 `data/`、不调付费接口、conda Python 路径等）写在模板里，按需修改即可。
