# Task 031 前后证据目录

本目录保存 Task 031（2026-11-21）的**前后对照证据**，配套归档见
[Task 031 归档](../../prompts/06_testing/2026-11-21_031_core_correctness_fixes.md)。

## 目录

| 路径 | 内容 |
|---|---|
| `before/` | 改动前证据：干净 HEAD（`e3b3594`）代码上运行的结果 |
| `before/reports/` | 改动前离线 heldout 报告（A 20/30、B 21/30、C 23/30） |
| `before/unittest.txt` / `before/smoke.txt` / `before/check.json` | 改动前 409 tests / 57 项契约 / `check` |
| `before/counterexamples.json` | Z1/Z2/Z3 改动前真实反例输出 |
| `after/` | 改动后证据：当前工作区（未提交） |
| `after/reports/` | 无（改动后报告按项目规范写入 `docs/evaluation/reports/20261121T085431_*`） |
| `after/unittest.txt` / `after/smoke.txt` / `after/check.json` | 改动后 529 tests / 70 项契约 / `check` |
| `after/counterexamples.json` | Z1/Z2/Z3 改动后真实输出 |
| `after/cli_ask_scripted.json`、`after/cli_investigate_scripted.json`、`after/cli_investigate_clarification.json` | 脚本化 `ask` / `investigate` 默认输出；未命中领域时的澄清输出 |
| `after/cli_contract_evidence.json` | 退出码、`approve --dry-run` 前后台账逐字节不变、身份来源 |
| `after/check_invalid_config.*` | 在配置里写入 `vector_store: chroma` 后 `check` 的真实报错（随后按字节恢复） |
| `after/evaluate_heldout.txt` | 改动后离线 heldout 运行输出 |
| `after/evaluation_compare.txt` | 改动前后逐题对比（用例/fixture/评分校验和一致） |

## 复现脚本

| 脚本 | 用途 |
|---|---|
| `counterexamples.py` | 同一脚本分别在改动前/后代码上运行 Z1/Z2/Z3 反例，输出 JSON |
| `capture_cli_contract.py` | 采集退出码、dry-run 不写数据、身份来源证据 |
| `compare_evaluation.py` | 对比 `before/reports` 与 `docs/evaluation/reports` 的逐题结果 |
| `normalize_utf8.py` | 把 PowerShell 重定向产生的 UTF-16 证据统一转回 UTF-8 |
| `verify_docs.py` | 文档静态核验：UTF-8、围栏配对、相对链接、归档 9 节、Prompt 逐字 |

运行方式（仓库根）：

```powershell
$env:PYTHONIOENCODING="utf-8"; $env:PYTHONUTF8="1"
$py = "D:\anacada\envs\commercial-agent\python.exe"
& $py docs/reviews/task031_evidence/compare_evaluation.py
& $py docs/reviews/task031_evidence/verify_docs.py
```

`counterexamples.py` / `capture_cli_contract.py` 需要 `PYTHONPATH=<repo>/backend`，并在 `backend/` 或任意目录下用同一解释器运行。

## 边界

- 改动前证据来自 `git worktree add --detach <临时目录> HEAD` 的干净工作树（用后已 `git worktree remove` 清理），不是用 `git stash` 改当前工作区得到的。
- 所有证据都**未调用付费模型接口**；`.env` 中的密钥只被 `api_key_env_present` 读取到"存在"，未发起请求。
- 改动前/后报告都绑定同一未提交 commit（`e3b3594`），区分依据是生成时间与工作区状态；这是项目现有报告绑定的已知局限。
