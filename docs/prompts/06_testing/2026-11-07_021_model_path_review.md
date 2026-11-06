# 2026-11-07_021_model_path_review

## 1. 基本信息

- 日期：2026-11-07（Asia/Shanghai）
- 任务编号：021
- 模块：06_testing
- 关联任务：017–020
- 执行者：Codex（用户本次临时请求）
- 审查基线：`main` / `45af0cb`
- 本轮 Commit：`Pending`

## 2. 任务目标和背景

检查 DeepSeek 新完成的 R1–R7 修复、模型驱动领域 Agent、环境加载与真实调用首跑变更，核对进度并定位可复现的缺陷。

## 3. 原始用户 Prompt

```text
检查一下deepseel的 本次修改
```

## 4. AI 实际执行的主要步骤

1. 检查 Git 状态与 `bf30dd5..45af0cb` 差异、任务归档和代码。
2. 运行 301 项 unittest、57 项契约检查以及 scripted 调查 CLI。
3. 在临时控制面/旧 schema/内存 fixture 中核对线程复用、旧数据隔离、多项目报告标签。
4. 使用 Fake 复现预算重试、错误实体、不取证成功、LLM 文档范围、问题/筛选丢失以及答案金额与内部 facts 不一致。
5. 读取已入库真实调查与 dev 评测的结构化统计，未重新调用 provider。
6. 归档本报告与日志，不修改业务源码。

## 5. 新增和修改的文件

| 文件 | 变更 |
|---|---|
| docs/reviews/2026-11-07_model_path_review.md | 新增修复核实与 N1–N6 报告 |
| 本文件 | 新增 021 归档 |
| docs/README.md | 登记 021 |
| docs/product/PROJECT_DEVELOPMENT_ROADMAP.md | 新增当前独立审查提示 |
| docs/development_logs/development_log.md | 新增本轮日志 |
| docs/issues/issue_log.md | 新增 N1–N6 未解决入口 |
| docs/checkpoints/git_history.md | 登记审查基线与未提交状态 |

## 6. 执行结果和验证方式

- 301 tests，OK（skipped=1）；57 项契约检查通过。
- scripted CLI：exit 0、conflicting、无失败、6 次模型调用、4 次工具调用。
- 线程复用被拒绝；旧记录与多项目报告的跨项目访问返回 404。
- 额外复现 5 项 P1、1 项 P2：模型重试记账、目标租约、文档范围、证据完成条件、问题/筛选条件、最终回答准确性。
- 详细证据和验收标准见 [模型链路审查报告](../../reviews/2026-11-07_model_path_review.md)。
- 尝试向 A_deterministic 注入模型时，工厂按设计明确拒绝；未将该预期拒绝记为缺陷。

## 7. 遇到的问题及解决方法

新 LLM 路径未完整继承确定性路径的目标、范围和结果约束；回归测试通过仍可构造错误成功。已定位并给出验收反例，本轮没有执行修复。

## 8. 对应 Git Commit Hash

- 被审查基线：`45af0cb`。
- 本轮文档：`Pending`；没有提交或推送。

## 9. 后续待办事项

- [ ] 优先修 N1 物理请求预算与用量记账。
- [ ] 修 N2/N3/N5 的目标及筛选边界。
- [ ] 修 N4/N6 的结果契约和最终回答验证。
- [ ] 明确独立模型配置策略，完成真实 heldout 与 PostgreSQL 等剩余验收。


---

## 10. DeepSeek 实施记录（接续本节，原始 Prompt 与审查结论不改动）

- 执行者：DeepSeek（用户要求按 021 报告逐项修复 N1–N6，分批自检并继续推进）
- 代码基线：`main` / `45af0cb`（未提交变更保留）
- 本轮 Commit：`Pending`（完成后按里程碑提交，见 git_history）

### 10.1 N1 模型调用预算按物理请求记账

- **原问题复现**：`max_model_calls=10`，Fake 首轮返回非法工具调用（10 tokens）触发 `MODEL_ERROR` 重试，第二轮成功（20 tokens）。实测 `client.calls=2` 但 `budget.used_model_calls=1`、`used_total_tokens=10`。
- **根因**：`model_call_id = f"mc_{run}_{subtask}_{round}"`，`BaseAgent` 重试后 `round` 重新从 1 开始，新请求复用了已结算 ID，`Budget._reserve` 幂等去重把它吞掉。
- **修改**：`runtime/tool_loop.py` 增加 `itertools.count` 全局 `request_seq` 并拼进 `model_call_id`；`runtime/budget.py` 新增 `record_unbudgeted_tokens()`，`runtime/types.py` 的 `BudgetUsage` 增加 `exceeded_tokens`（token 只能事后得知，超限时如实记账 + 标注超出量，而不是丢弃）。
- **修复后**：`limit=10` → 2 次物理请求 / 2 次记账 / 30 tokens；`limit=1` → **只发出 1 次物理请求**、账本 1 次、任务明确失败。
- **测试**：`backend/tests/test_model_budget.py`（6 项）：重试逐次记账、失败尝试 token 入账、`max_model_calls=1` 拦截第二个请求、token 溢出如实记录、成功路径逐次记账、图补查逐次记账。
- **未覆盖**：真实 provider 下的 token 统计仍以返回值为准；并发压测下 `request_seq` 只保证唯一性，不保证严格顺序。

### 10.2 N2 / N3 / N5 可信目标、文档范围与筛选条件

- **N5 复现**：`RuleBasedPlanner().plan("只查询 A-301 空调维修工单")` 的子任务 payload 只有 `lease_id`/`category`，**没有 question**，模型收到的 `question=""`。
- **N2 复现**：主体同时有星汇+金鹭权限、目标 A-301 时，Fake 让模型调用 `billing.statement.read(lease_jl_b101_2025)`，旧实现照单全收并返回 `status=success`（facts 为金鹭数据）。
- **N3 复现**：目录中有 A-301 与 A-302 两份合同，模型省略 `document_ids` 时检索返回 **A-302 的 20% 递增条款**；点名 A-302 也照给。
- **修改**（新增统一约束层，确定性/LLM 共用）：
  - `agents/base/scope.py`（新增）：`TaskScope.apply_arguments()`（模型给错→拒绝并回传原因；省略→注入可信值）与 `accepts_output()`（结果实体校验）。
  - `runtime/tool_loop.py`：新增 `prepare_arguments` 钩子，拒绝的调用不执行，原因作为 `INVALID_TOOL_ARGUMENTS` 回传给模型。
  - `agents/base/llm_agent.py`：从可信 payload 构造 `TaskScope`，按 scope 注入/拒绝工具参数，执行后过滤越界输出，输出 `task_scope` / `rejected_outputs`。
  - `tools/knowledge_tools.py`：`DocumentSearchInput.lease_id` + `_resolve_allowed()`：以可信租约解析适用文档集并与模型给的 `document_ids` 取交集；两者都没有时受控调用返回**空集合（默认拒绝）**，`require_scope=False`（CLI 人工检索）保持全库搜索。
  - `orchestration/investigation.py`：每个子任务 payload 带上原问题 `question`。
  - `evaluation/baselines.py`：离线 B 基线的条款检索改为带 `lease_id`（否则受新默认拒绝影响，H17 会丢证据）。
- **测试**：`backend/tests/test_task_scope.py`（15 项）：省略注入、错租约拒绝、输出归属校验、无 scope 不约束、双权限错实体、省略租约、受控/交互式文档范围、公共制度文档例外、planner 传 question 与 category。
- **未覆盖**：跨项目汇总类报告仍是"同一租约"口径，多项目聚合报表未实现。

### 10.3 N4 零取证不再算完成

- **原问题复现**：Fake 从不调用工具，只回"已经核对，账单没有问题" → `verdict=supported`、`completeness=complete`、`tool_calls=0`。
- **修改**：
  - `agents/base/evidence.py`（新增）：按 capability 定义**最低结果契约**（billing 需 `lease_id`/`invoiced_total`/`paid_total`/`outstanding_total`；property 需 `work_order_count`/`open_count`；lease 需非空 `lease`）；未登记的 capability 视为允许纯说明，不加门槛。
  - `agents/base/llm_agent.py`：契约不满足 → `INSUFFICIENT_EVIDENCE` 失败（不可重试），details 记录违规项、工具调用数、拒绝原因。
  - `orchestration/investigation.py`：`verify_results` 独立复核能力契约（不轻信"Agent 说自己成功"），缺字段计入 `missing` → `insufficient`。
  - `agents/base/errors.py`：新增 `INSUFFICIENT_EVIDENCE` 与 `InsufficientEvidenceError`。
- **修复后**：同一反例 → `verdict=insufficient`、`completeness=partial`、失败码 `insufficient_evidence`、findings 为空。
- **测试**：`backend/tests/test_evidence_and_answer.py`（N4 部分 7 项）：契约单元判定、零工具调用、只调无关/未注册工具、工具全失败后给文本、正常取证仍成功、`verify_results` 缺字段、租约只有条款无租约事实。
- **未覆盖**：契约只描述"必须有哪些字段"，不校验字段值本身的业务合理性（那属于工具与核验逻辑）。

### 10.4 N6 最终答案准确性

- **原问题复现**：模型正确调用 A-301 账单工具（facts `outstanding_total=18036.00`），最终回答"A301 未收金额为 0.00 元，账单已经全部结清"；旧评分只比对 facts，`C01-F:outstanding_total` 仍判通过。
- **修改**：
  - `agents/base/narrative.py`（新增）：`check_answer_consistency(answer, facts)`，机械规则——答案里"两位小数"的金额（或与事实完全相等的整数）必须来自 `facts` 金额集合；出现集合外金额 → `mismatch`；只在缺金额 → `not_mentioned`；无金额事实 → `not_checkable`。条款号 `5.2`、百分比 `20%`、日期不会被误判为金额。
  - `agents/base/llm_agent.py` / `agents/single/agent.py`：输出 `answer_check`；`mismatch` 时追加 warning（任务降为 `partial`）。
  - `orchestration/investigation.py`：报告新增 `narrative_discrepancies`，非空即 `requires_human_review=True`。
  - `evaluation/scoring.py`：升 `scoring-v3`，新增 `answer` 断言（`mismatch` 失败、`not_mentioned` 转人工、`consistent` 通过、`not_checkable` 不产生断言），`CaseScore.answer_check` 落盘。
  - `evaluation/runner.py`：汇总增加 `by_kind`（`tool_facts` / `final_answer` / `evidence` / `outcome` / `approval`），Markdown 报告新增"指标分解"表。
  - `docs/evaluation/scoring_v3.md`（新增），`scoring_v2.md` 标注已被取代；v2 报告与真实模型历史测量**未回写**。
- **测试**：`backend/tests/test_evidence_and_answer.py`（N6 部分 10 项）：金额来源不明、金额一致、条款号/百分比不误判、无金额不判、错误叙述可见且非 success、报告列出 `narrative_discrepancies`、正确叙述保持 success、评分侧"facts 全对但答案写错"判失败、正确答案通过、沉默答案转人工。
- **未覆盖**：只校验金额；"1.8 万"这类改写会被视为未提及；真实模型答案准确性尚未测量。

### 10.5 本轮验证命令与结果

| 命令 | 结果 |
|---|---|
| `python -m unittest discover -s tests -p "test_*.py"`（`backend/`） | **343 tests，OK（skipped=1）** |
| `python tests/smoke_agent_contracts.py` | **57 项检查通过** |
| `python -m app.cli investigate`（offline） | exit 0，`conflicting`，工具事实完整 |
| `python -m app.cli investigate --model-provider scripted` | exit 0，`conflicting`，4 次工具调用，无失败 |
| `python -m app.cli evaluate --split heldout --quiet` | A 20/30、B 21/30、C 23/30（`scoring-v3`） |
| `python -m app.cli evaluate --split dev --quiet` | A/B/C 均 0/7（开发集为人工量表题） |

### 10.6 仍未解决的问题

- 真实模型复测未做：N1 记账已修，但本轮没有消耗 provider 额度；真实答案准确性、真实 heldout 稳定性仍未测量。
- 独立模型配置策略（领域 YAML 的模型名/采样是否重建客户端）未处理，仍是审查报告第 3 节提出的待决项。
- PostgreSQL 实机验证、部署/真实鉴权、人工量表评分仍未完成。
- `not_mentioned` 口径偏宽（只说"已核对"不算错），需要真实模型数据后再定是否需要收紧。