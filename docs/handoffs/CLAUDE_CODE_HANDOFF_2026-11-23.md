# 会话交接：2026-11-23（Task 032–035 收尾、dev_loop / dev_review、正式真实评测）

- 生成时间：2026-11-23 23:50（Asia/Shanghai），Claude Code。
- 分支：`main`；HEAD：`e486ea3`（`eval: 正式真实评测原始结果——heldout 四组 × 5 次（scoring-v3.3）`）。
- 远端：`origin/main` = `9817bd6`；**本地领先 3 个提交未推送**（`e90544d`、`c6037fe`、`e486ea3`，均为正式评测）。
- 工作区：只有未跟踪的 `.claude/`（本地预览配置，含会话临时路径，**不要提交**）；无其它未提交改动。
- 上一份交接：[CLAUDE_CODE_HANDOFF_2026-11-21.md](CLAUDE_CODE_HANDOFF_2026-11-21.md)（Task 031，已过时）。

---

## 1. 已验证事实（本文生成时实际运行 / 查看过）

### 1.1 测试（HEAD `e486ea3`，2026-11-23 23:49 实测）

| 项 | 结果 |
|---|---|
| 全量回归，默认环境 | `Ran 717 tests … OK (skipped=45)`（44 个 PG 测试 + 1 个既有 skip） |
| 全量回归，设置 `COMMERCIAL_PG_TEST_URL` | `Ran 717 tests … OK (skipped=1)` |
| 契约自检 `tests/smoke_agent_contracts.py` | 全部通过：70 项 |
| `python -m app.cli check` | exit 0 |

命令（在 `backend/` 下，Git Bash）：`PYTHONUTF8=1 D:/anacada/envs/commercial-agent/python.exe -m unittest discover -s tests -p "test_*.py"`。Git Bash 里的 `python` 是占位程序，必须写完整路径。

### 1.2 本会话完成并提交的任务（`3be785e..e486ea3`，共 34 个提交）

| 任务 | 状态 | 关键提交 | 归档 / 复查 |
|---|---|---|---|
| Task 032 业务流程工作台 | 独立复查有条件通过 → 返修 → 确认复查条件已满足 | `e1d0d2e` | [032 归档](../prompts/05_frontend/2026-11-22_032_business_workbench_ui.md)、`docs/reviews/2026-11-22_task032_*` |
| Task 034 LLM Supervisor 混合规划 | 同上 | `e1d0d2e` | [034 归档](../prompts/04_agents/2026-11-22_034_llm_supervisor_planner.md)、[ADR-006](../decisions/ADR-006-hybrid-planner.md) |
| Task 033 MCP 工具网关（stdio 第一版） | 独立复查有条件通过 → 返修 → 确认复查条件已满足 | `083335a`、`4422a74`、`57a0921`、`1f8ce86` | [033 归档](../prompts/04_agents/2026-11-23_033_mcp_gateway.md)、`docs/reviews/2026-11-23_task033_*` |
| Task 035 PostgreSQL 实机验证 | 独立复查**不通过**（单价读路径）→ 返修 → 确认复查有条件通过 → 条件再修（**未再复查**） | `af03655`、`f901ac5`、`5586ef3`、`127e503`、`a1b9d4c` | [035 归档](../prompts/02_database/2026-11-23_035_postgresql_verification.md)（§12 / §12.1）、`docs/reviews/2026-11-23_task035_*` |
| dev_loop 自动编码 / 审查循环 | 可用，已多次实跑 | `129c26b` … `e4bc85e` | [scripts/dev_loop/README.md](../../scripts/dev_loop/README.md) |
| dev_review 自动独立复查 | 可用，已实跑 2 次（035） | `34a51a2` | 同上 |
| 正式真实评测工具 | 可用，已实跑 | `e90544d`、`c6037fe` | `backend/app/evaluation/formal.py`、`backend/tests/test_formal_eval.py` |
| 正式真实评测：heldout 四组 × 5 次 | **已跑完，原始结果已提交；结论待评分审计** | `e486ea3` | [formal_20261123/summary.md](../evaluation/reports/formal_20261123/summary.md)（**未写入开发日志 / 基线 / 路线图**，见 §3.1） |

### 1.3 正式真实评测结果（scoring-v3.3，原样）

冻结提交 `c6037fe`；32 道 heldout（30 道计分）；A 离线，B / C 用 `deepseek-flash`（服务端实际应答一致，无 mismatch）；合计约 **259 万 token**；项目无价格表，不报金额。

| 组 | 通过率 均值（5 次区间） |
|---|---|
| A 确定性规则 | 66.7%（5 次完全一致） |
| B 单 Agent | 35.3%（30.0–36.7%） |
| C 多 Agent · 规则规划 | 56.0%（50.0–63.3%） |
| C 多 Agent · 混合规划 | 52.0%（43.3–56.7%） |

**已核实的现象（不是结论）**：
- 真实模型组工具事实断言 ~92%（A 85%）、答案金额接地 ~99%，但**资金结论断言只有 38–50%**；其中 mismatch 的答案 92–100% 完整写出了全部可信金额。抽查 H02 / H03 / H04 均为**评分器误判**：v3.3 的字段绑定把 Markdown 表格里单张账单的“已收 15876 / 未收 0.00”当成总结论。
- B 组 outcome 断言 0/48：应拒绝的题（H06、H11、H12、H16、H27）B 返回 `failed` 而非 `denied`。
- 两个 C 组 H11、H16（跨主体查租约 / 工单）**每次都不通过**，A 全部通过。**原因未核实**（可能是真实行为问题，也可能是评分口径），与安全相关，审计时优先看。
- 合同条款检索 H17 / H19、工单 H14 上，真实模型 C 组明显好于 A。
- H07、H15、H18、H20、H24 四组全不通过（含 A）。

### 1.4 已解决的重要问题（详见各归档与 `docs/issues/issue_log.md`）

- 035：seed 外键顺序、PG 只读闸门只管单个事务、`timestamptz` 读回 UTC、单价被截成 2 位（存储层与**仓库读路径**两处）、`arrears()` 与工具契约不符、只读角色密码泄露面。
- 033：跨项目文档检索返回 ok + 0 条（改为范围拒绝；根因之一是锦澜合同缺 PDF）、未知工具名无测试守护。
- dev_loop：未跟踪文件快照、git 护栏、审查方继承桌面 App 宿主变量、PowerShell 管道 BOM、默认模型名（key 只有 `deepseek-flash` / `deepseek-v4-pro`）。

---

## 2. 尚未验证 / 有保留的内容

- **正式评测的质量结论**：v3.3 对真实模型答案大量误判，通过率被低估，**目前不能下“真实模型好 / 不好”的结论**；只有“C 比 B 高约 20 个点、5 次方向一致”相对可靠（具体幅度待重算）。混合规划与规则规划的 4 个点差距在 σ≈5.5 内，看不出优势。
- **Task 035 最后一轮再修**（`a1b9d4c`：arrears 字段、SQL 日志检查、文档）没有再做独立复查（用户选择直接推送）。
- heldout 题在开发中被反复查看，结果只能算回归 / 探索性，不是盲测。
- 人工评分表 `formal_20261123/manual_scoring.csv`（24 条）**尚未评分**，需用户本人完成。
- MCP 网关未在 Flowise 中实连；HTTP + OAuth、RLS、多实例并发、生产部署均未做。

---

## 3. 下一步（按优先级）

### 3.1 先补归档缺口（文档工作）

正式真实评测（`e90544d` / `c6037fe` / `e486ea3`）**还没有**：开发日志条目、问题日志条目、任务归档（建议 `docs/prompts/06_testing/2026-11-23_036_formal_real_evaluation.md`，编号是否用 036 由用户定）、`CURRENT_BASELINE.md` 与路线图工作包 4 的状态更新、`docs/README.md` 任务表登记。现状文档仍写“正式真实 heldout 对照未做”。

### 3.2 评分审计 → scoring-v3.4（不再调用模型）

1. 逐条审计 v3.3 的资金结论 mismatch 与 outcome 失败，分“评分误判 / 真错误”。重点先看 C 组 H11 / H16（安全相关）、B 组拒绝行为。
2. 如需改评分：按评测计划**新建 scoring-v3.4**，对 `formal_20261123/rep*/` 里已保存的答案离线重算，v3.3 报告原样保留，不跨版本比较通过率。改评分规则要有测试，且不能为了提分放宽真错误。
3. 把 `manual_scoring.csv` 整理给用户评分；人工结果与自动结果分母分开报告。
4. 之后才能写工作包 4 的结论。

### 3.3 其余待用户决定

- 推送本地 3 个提交（用户开口再推）。
- 网页工作台接真实模型；`mcp-serve` 是否不再从 `.env` 读 `DEMO_PRINCIPAL_ID`（当前 P3，已文档化）；CLI 注入 PG 仓库的临时替换做法是否重构；`fixed_amount` 租金规则未实现。
- 工作包 5：最终复现与交付（在评测结论之后）。

---

## 4. 关键位置

| 内容 | 路径 |
|---|---|
| 当前基线 / 路线图 | `docs/architecture/CURRENT_BASELINE.md`、`docs/product/PROJECT_DEVELOPMENT_ROADMAP.md` |
| 评测计划 / 评分规则 | `docs/evaluation/evaluation_plan.md`、`docs/evaluation/scoring_v3.md`；代码 `backend/app/evaluation/scoring.py`、`runner.py` |
| 正式评测工具与结果 | `backend/app/evaluation/formal.py`（`run` / `summarize`）；`docs/evaluation/reports/formal_20261123/`（`freeze.json`、`summary.md/json`、`manual_scoring.csv`、`rep1..5/{a,main,hybrid}/`） |
| 数据层 / PG | `backend/app/db/`（`session.py` 只读闸门与时区、`repository.py`、`roles.py`）、`backend/migrations/versions/0001–0003`、`backend/tests/test_postgres_layer.py` |
| MCP 网关 | `backend/app/mcp_gateway/`、`backend/app/config/mcp_clients/`、`backend/tests/test_mcp_gateway.py` |
| 规划层 | `backend/app/orchestration/supervisor.py`、`backend/app/config/planner.yaml` |
| 自动化脚本 | `scripts/dev_loop/dev_loop.ps1`（编码↔审查）、`dev_review.ps1`（独立复查） |
| 开发记录 | `docs/development_logs/development_log.md`、`docs/issues/issue_log.md`、`docs/checkpoints/git_history.md`、`docs/prompts/` 任务归档 |

---

## 5. 新会话必须遵守的约束

1. **全部用中文回复**（用户明确要求）。
2. **不调用付费模型接口**（DeepSeek 等），除非用户在当次对话里明确授权；评分审计与重算必须离线。
3. 不提交 / 推送 / reset / clean，除非用户开口；不提交 `.claude/`；不碰 `data/`、`tools/flowise/`、`.gitignore` 里的 Flowise 三行。
4. 评分变更另升版本、另建报告，不改写历史测量（评测计划 §3）。
5. 文档换行用 LF；状态措辞如实，不把“有条件通过 / 待复查”写成“已验收”。
6. 工作流：给 DeepSeek 的编码任务写成 dev_loop 任务单（只改哪些文件、验收标准），先提交再跑；Claude 改完后的独立复查由 Claude **直接运行 `dev_review.ps1`**，不要让用户在两个模型间转交。跑完都要自己看 diff、做变异测试。
7. PG 测试：本机 Docker 容器 `cpma-pg-dev`（`postgres:16`，只绑定 `127.0.0.1:55432`，一次性测试库）当前在运行；设置 `COMMERCIAL_PG_TEST_URL` 才会跑 PG 测试。不要把 `COMMERCIAL_DB_URL` 设成全局变量（`backend/migrations/env.py` 会优先读它）。连接串与密码不得写进任何文件。
