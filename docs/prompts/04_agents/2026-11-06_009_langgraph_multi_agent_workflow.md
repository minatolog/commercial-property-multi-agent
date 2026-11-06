# 2026-11-06_009_LangGraph 多 Agent 工作流与条件路由

## 1. 基本信息

- **日期**：2026-11-06
- **任务编号**：009（正式 Prompt 4）
- **模块**：04_agents
- **状态**：**DeepSeek 自检通过**
- **前置任务**：007（Runtime）、008（LangChain / 单 Agent）
- **Git Commit**：见 §8

## 2. 任务目标和背景

Task 008 打通了"单 Agent + 工具"闭环，但系统仍无法把**一个跨系统问题**拆成多个领域子任务并并发调查。

本任务交付真正的 LangGraph 图：条件路由（简单问题不走扇出）、并发扇出与合流、按 `subtask_id` 归并、限次补查、以及"能力被禁用时不静默降级"。

## 3. 原始用户 Prompt

````
Task 009：LangGraph 多 Agent 工作流、共享状态和条件路由
...
- 实现 Lease、Billing、Property 独立 Agent；Coordinator 按能力规划；
- LangGraph 条件分支、动态选择子任务、并发执行、合流、有限补查；
- 每个 Agent 可独立配置/替换/禁用；
- 关键行为要有自动化验证；更新归档、日志、路线图与检查点。
````

完整原文见 2026-11-06 用户消息（"后续任务"列表 + "每个任务的执行要求"）。范围以路线图 `Prompt 4 / Task 009` 为准。

## 4. AI 实际执行的主要步骤

1. 安装 `langgraph>=1.0`（1.2.20），确认可编译 `StateGraph`。
2. 新增 `app/agents/base/tool_backed.py`：领域 Agent 的"工具调用 + 证据"统一入口。
3. 实现 `LeaseAgent`（租约事实/续租事实）、`BillingAgent`（账单/欠费）、新增 `PropertyAgent`（工单事实），并把 YAML `version` 同步到类属性（K2 一致性校验）。
4. 新增 `app/orchestration/investigation.py`：状态定义、规则规划器、确定性核验器、图与 `Investigator` 门面。
5. 扩展 `AgentContext.subtask_id` 与 `ToolTrace.subtask_id`，让并发子任务的 Trace 可归因。
6. `factory.build_registry` 支持依赖注入（按实现签名过滤），Coordinator 与图不 import 具体 Agent。
7. 新增 `app/investigation_demo.py` 装配层与 CLI `investigate`。
8. 新增 `tests/test_graph_workflow.py`（17 项）；更新既有 smoke / 安全扫描断言以反映新依赖与新增 Agent。

## 5. 新增和修改的文件

| 文件 | 类型 | 说明 |
|---|---|---|
| `backend/app/orchestration/investigation.py` | 新增 | 图、规划器、核验器、`Investigator` |
| `backend/app/agents/base/tool_backed.py` | 新增 | 领域 Agent 基类 |
| `backend/app/agents/property/{__init__,agent.py,prompts/system.md}` | 新增 | Property Agent |
| `backend/app/config/agents/property.yaml` | 新增 | 独立配置 |
| `backend/app/investigation_demo.py` | 新增 | 装配 |
| `backend/app/agents/lease/agent.py`、`billing/agent.py` | 重写 | 由骨架改为工具驱动实现 |
| `backend/app/agents/base/contracts.py` | 修改 | `AgentContext.subtask_id` |
| `backend/app/runtime/types.py`、`tools/executor.py` | 修改 | `ToolTrace.subtask_id` |
| `backend/app/agents/factory.py` | 修改 | 依赖注入按签名过滤；注册 `property` |
| `backend/app/cli.py` | 修改 | 新增 `investigate` |
| `backend/pyproject.toml` | 修改 | 声明 `langgraph` |
| `backend/tests/test_graph_workflow.py` | 新增 | 17 项 |
| `backend/tests/smoke_agent_contracts.py` | 修改 | 契约检查改用 stub；Agent 数量 5 |
| `backend/tests/test_runtime.py` | 修改 | 依赖声明检查更新（允许 langchain/langgraph，仍禁止 DB/Web） |

## 6. 执行结果和验证方式

| # | 命令 | 退出码 | 结果 |
|---|---|---|---|
| 1 | `python tests/smoke_agent_contracts.py` | 0 | 57 项通过 |
| 2 | `python -m unittest discover -s tests` | 0 | `Ran 94 tests ... OK`（52 + 24 + 17 + 1 依赖一致性） |
| 3 | `python -m app.cli investigate` | 0 | C03 场景：3 个子任务并发完成、`verdict=conflicting`、差额 `756.00`、缺失 `doc_xh_a301_annex_b`、3 条 Trace 分属 3 个 `subtask_id` |
| 4 | `python -m app.cli ask "A-301 欠多少？"` | 0 | 单 Agent 路径未受影响 |
| 5 | 其余 CLI（`--help` / `tools` / `check` / `demo`） | 0 | 全部正常 |

关键图行为（均有断言）：

| 行为 | 证据 |
|---|---|
| 条件路由 | 纯欠费问题 → `route=deterministic`、1 条 Trace；争议问题 → `route=fanout`、3 条 Trace |
| 并发扇出与合流 | 3 个子任务同一 `run_id`、`subtask_id` 互不相同、结果无缺失 |
| 归并按 `subtask_id` | 补查重跑不产生重复结果 |
| 冲突可见 | `rent_variance` = `756.00`，并附 `evidence_ids` |
| 缺失资料可见 | `doc_xh_a301_annex_b` 进入 `missing_information` |
| 能力禁用不静默 | `capability_unavailable` 失败被记录，其余两个能力仍完成，`completeness=partial` |
| 补查有界 | 仅在"子任务失败"时补查，上限 1；文档缺失不触发补查 |
| 跨项目拒绝 | 锦澜租约在星汇上下文下全部 `project_scope_denied`，`results=()` |

## 7. 遇到的问题及解决方法

| 问题 | 原因 | 解决 |
|---|---|---|
| `Send` 传递的 `context` 丢失，`run_subtask` 报 `KeyError: 'context'` | LangGraph 只保留 State 中声明的 channel | 在 `InvestigationState` 显式声明 `context: AgentContext` |
| 租约结论显示 `租期 None 至 None` | `LeaseLookupOutput` 是**扁平**结构，Agent 按嵌套 `lease` 读取 | LeaseAgent 改为按扁平的 `document_ids` / `missing_document_ids` 读取 |
| `PropertyAgent` 报 `KeyError: 'id'` | 工具输出字段名是 `work_order_id` | 改用 `work_order_id` |
| 补查后 `conflicts` 重复两条 | `conflicts`/`missing` 是 `operator.add` 追加通道，多轮会累积 | 报告节点统一去重；`InvestigationResult.conflicts` 以报告为准 |
| 冲突与"资料缺失"只有一个 verdict 槽位，语义打架 | 单一字段承载两个维度 | 新增 `completeness`（complete/partial），`verdict` 只回答证据是否矛盾 |
| 文档缺失触发了无意义的补查 | 补查条件只看 `insufficient` | 补查条件改为"确实有子任务失败"，永久性缺失不重试 |
| smoke 中 `NOT_IMPLEMENTED` 检查随业务 Agent 实现而失效 | 用真实 `LeaseAgent` 做契约检查 | 改用 `_VoidAgent` 契约替身，检查项仍 57 项 |

## 8. 对应 Git Commit Hash

- **状态**：见 `docs/checkpoints/git_history.md`（由本轮里程碑提交回填）。

## 9. 后续待办事项

- [ ] Task 010：PostgreSQL 只读业务工具与数据访问边界（本机无 PostgreSQL，需说明验证边界）
- [ ] Planner 目前是确定性规则；接入真实模型后可在 Task 013 对比"规则规划 vs 模型规划"的代价
- [ ] 图当前没有持久 checkpointer（Task 012）
- [ ] 审批节点未实现（Task 012）
