# 2026-11-06_013_三基线与 40 题正式评测

## 1. 基本信息

- **日期**：2026-11-06
- **任务编号**：013（正式 Prompt 8）
- **模块**：06_testing
- **状态**：**DeepSeek 自检通过**（离线三基线；真实模型测量受凭据限制，未执行）
- **前置任务**：007–012
- **Git Commit**：见 §8

## 2. 任务目标和背景

此前的验证都是"功能对不对"，没有回答"值不值得用多 Agent"。本任务建立可复查的评测：

- **数据**：8 道开发题（Task 006 冻结）+ 32 道保留题（本任务新增，冻结后只跑不改）；
- **三基线**：`A_deterministic`、`B_single_agent`、`C_multi_agent`，共用同一 fixture、同一套只读工具、同一份全任务预算；
- **分离指标**：自动断言（correctness）/ 路由（efficiency）/ 人工量表（rubric）三者不混算；
- **报告绑定**：代码提交、用例校验和、fixture 校验和、评分规则版本、模型与配置。

## 3. 原始用户 Prompt

本轮（2026-11-06）用户取消 Codex 逐任务审查，要求连续推进 Task 007 自检 → 015。与本任务相关的原文摘录：

````
- Task 013：确定性、多 Agent 与失败场景的 Evaluation 数据集和运行器

## 每个任务的执行要求

4. 为关键行为补充自动化验证；运行本任务相关测试和适当的现有回归测试，记录真实命令与结果。
5. 每个任务结束后更新：Prompt 归档、development_log、路线图、issue_log/knowledge_notes（必要时）、
   git_history 检查点。
6. 只有真实实现和验证完成后，才可把任务标记为"DeepSeek 自检通过"。不得编造测试、提交、推送或模型调用结果。
8. 没有外部凭据时，完成可验证的接口、Fake/离线测试和配置说明；准确标出真实服务验证受凭据限制。
````

范围以 `docs/product/PROJECT_DEVELOPMENT_ROADMAP.md` 的 **Prompt 8 / Task 013** 为准（40 题、三基线、指标分离、冻结规则）。

## 4. AI 实际执行的主要步骤

1. 先写 `docs/evaluation/scoring_v1.md`（**评分规则先冻结**），再生成保留集。
2. `backend/scripts/generate_heldout_cases.py`：从 fixture **计算**期望事实（金额/租期/工单数），避免手抄；产出 `heldout_v*.jsonl` 并打印校验和。v1 因嵌套取值缺陷作废（见 issue_log），当前使用 v2。
3. `backend/app/evaluation/cases.py`：JSONL 装载、必填校验、重复 ID 拒绝、兼容开发集旧结构（`trusted_context` / `expected_facts.lease_id`）。
4. `backend/app/evaluation/baselines.py`：三基线实现，共用工具白名单与 `max_tool_calls`；基线也走工具六道闸（构造显式 `AgentConfig`，不传 `None` 绕权限）。
5. `backend/app/evaluation/scoring.py`：确定性断言（facts / evidence / approval）+ 路由只作效率 + rubric 进人工队列；评分器不认识的期望键一律转人工（不静默判胜/判败）。
6. `backend/app/evaluation/runner.py`：逐题运行、汇总、绑定版本、输出 Markdown；报告按时间戳命名，不覆盖历史。
7. CLI `evaluate --baseline all --split dev|heldout`。
8. 新增 `backend/tests/test_evaluation.py`（23 项）。

## 5. 新增和修改的文件

| 文件 | 类型 | 说明 |
|---|---|---|
| `docs/evaluation/scoring_v1.md` | 新增 | 冻结的评分规则 |
| `docs/evaluation/cases/heldout_v2.jsonl` | 新增 | 32 道保留题（当前版本） |
| `docs/evaluation/cases/heldout_v1.jsonl` | 新增（作废存档） | 生成脚本缺陷版本，保留追溯 |
| `docs/evaluation/reports/*.json`、`*_summary.md` | 新增 | 实验记录（dev / heldout v2 两批，各含三基线） |
| `backend/scripts/generate_heldout_cases.py` | 新增 | 数据集生成与 `--check` 校验 |
| `backend/app/evaluation/{__init__,cases,baselines,scoring,runner}.py` | 新增 | 评测层 |
| `backend/tests/test_evaluation.py` | 新增 | 23 项 |
| `backend/app/cli.py` | 修改 | `evaluate` 命令 |
| `backend/app/paths.py` | 修改 | `CASES_DIR` / `REPORT_DIR` |

## 6. 执行结果和验证方式

| # | 命令 | 退出码 | 结果 |
|---|---|---|---|
| 1 | `python scripts/generate_heldout_cases.py` | 0 | 32 题，sha256 `acc384b4…`（v2） |
| 2 | `python -m unittest tests.test_evaluation` | 0 | `Ran 23 tests ... OK` |
| 3 | `python -m unittest discover -s tests -p "test_*.py"` | 0 | `Ran 179 tests ... OK` |
| 4 | `python tests/smoke_agent_contracts.py` | 0 | 57 项通过 |
| 5 | `python -m app.cli evaluate --split dev` | 0 | 生成 3 份 JSON + 汇总 Markdown |
| 6 | `python -m app.cli evaluate --split heldout` | 0 | 生成 3 份 JSON + 汇总 Markdown（当前引用 v2） |

> 说明：v1 保留集跑过一次用于确认缺陷（未留存报告，属中间调试实验）；
> 正式报告全部基于 v2，且按时间戳命名，不会覆盖历史。

### 保留集 v2 结果（离线，`scoring-v1`）

| 基线 | 计分题通过 | 通过率 | 自动断言通过率 | 路由命中（效率） | 工具调用 | token | 成本 |
|---|---|---|---|---|---|---|---|
| `A_deterministic` | 15/27 | 0.5556 | 0.6481 | 24/32 | 27 | 0 | n/a（离线） |
| `B_single_agent` | 16/27 | 0.5926 | 0.6975 | 0/32 | 38 | 0 | n/a（离线） |
| `C_multi_agent` | 23/27 | 0.8519 | 0.8704 | 28/32 | 47 | 0 | n/a（离线） |

**如实说明**：

- 32 题中 5 题不含可自动判定的断言（`cases_not_scored`），未计入通过率——属数据集缺陷，见 §9；
- `C` 领先主要来自"跨领域扇出 + 审批/权限边界"这类 A/B 结构上做不到的题，**不代表通用质量优势**；
- 本例 token=0、成本 `null`：**没有调用真实模型**，这些数字只能说明架构行为，不能当作模型质量或成本；
- `B` 的路由命中 0/32 是定义使然（单 Agent 架构不拆任务），只作效率参考。

## 7. 遇到的问题及解决方法

| 问题 | 原因 | 解决 |
|---|---|---|
| 保留集 v1 的 `lease_period` 期望为 `None 至 None` | 生成脚本把 `lease_facts()` 的返回当成 lease 本身（实际在 `facts["lease"]`） | 修脚本 → 产出 **v2**；v1 保留存档并在 issue_log 记录，不就地改 v1 |
| 开发集用例缺 `principal_id` / `lease_id` | Task 006 的结构是 `trusted_context` + `expected_facts.lease_id` | 装载器兼容两种结构；开发集文件不改 |
| 开发集问题只给 "A-301"，没有 lease_id | 原设计面向人类可读问题 | `resolve_lease()` 按单元编号从 fixture 反查，越权则返回空让流程明确失败 |
| 基线传 `agent_config=None` 时 `ToolExecutor` 崩溃 | 六道闸要求显式工具白名单 | 为基线构造 `AgentConfig`（`allowed_tools` = 注册表全部工具），**不绕过**授权检查 |
| 评分器不认识的期望键会静默判败 | `expected_facts` 里混有 schema 字段（如 `reversed_allocation_excluded`） | 引入 `SCORABLE_FACT_KEYS`，不认识的键进人工队列 |
| "无可判定断言的题"被算成失败 | `passed` 只有 True/False | 增加 `applicable`，`passed=None`，汇总单列 `cases_not_scored` |

## 8. 对应 Git Commit Hash

- **状态**：见 `docs/checkpoints/git_history.md`（里程碑提交后回填）。

## 9. 后续待办事项

- [ ] **数据集缺陷**：5 题（H22/H25/H26/H27/H30）没有可机械判定的断言，应在新版数据集中补 `forbidden_substrings` / `required_evidence_ids`，并在新的实验里跑，不改 v2。
- [ ] **真实模型测量**：需要 `DEEPSEEK_API_KEY`。计划按冻结配置（provider/model/temperature/max_tokens/重复次数）重复 3 次，记录 token 与费用口径；离线结果不得替代。
- [ ] **检索短板**：H18–H20（条款检索）在 C 上失败，根因是 BM25 用整段问题检索、top-3 召回不足；属 Task 011 的 P1 范围（混合检索/rerank），不应通过改题解决。
- [ ] 人工量表 32 题尚未实际人工评分，报告只列出待评项。
- [ ] 评测尚未覆盖"进程中断/恢复"场景（Task 012 能力），可作为下一批数据集的专项。
