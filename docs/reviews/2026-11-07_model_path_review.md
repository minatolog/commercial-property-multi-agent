# 本次修复与模型驱动链路审查（Task 021）

- 日期：2026-11-07（Asia/Shanghai）。
- 代码基线：`main` / `45af0cb`，检查开始时工作区干净，与本地 `origin/main` 一致。
- 差异范围：`bf30dd5..45af0cb`，涉及 R1–R7 修复、领域 LLM Agent、模型 B/C 入口、环境加载、真实 provider 适配与首跑归档。
- 结论：**上轮主要问题已修复，模型装配有实际进展；新增模型路径仍复现 5 项 P1 和 1 项 P2 问题。**
- 本轮未修改业务代码，未安装依赖，未新增付费模型请求，未连接 PostgreSQL，未提交或推送；只读取已入库的真实调用归档，并用 Fake/scripted 做独立验证。
- 本次为用户临时要求的审查，不恢复逐任务 Codex 审查流程。

## 1. 已完成工作与独立核实

| 项目 | 本次核实 |
|---|---|
| 全量回归 | `python -m unittest discover -s tests -p 'test_*.py'`：301 tests，18.536 秒，OK（skipped=1） |
| 契约检查 | `python tests/smoke_agent_contracts.py`：57 项通过 |
| 模型调查装配 | `python -m app.cli investigate --model-provider scripted`：exit 0，conflicting，failures=[]，6 次模型调用、4 次工具调用 |
| 上轮 R1 持久线程复用 | 星汇运行后换金鹭主体复用 thread，本次抛 ThreadIdentityConflictError，不再带出旧账单 |
| 上轮 R2 旧 schema 升级 | 当前 RunIndex/WorkflowService 处理旧库后，金鹭访问星汇记录返回 404 |
| 上轮 R3 多项目报告标签 | 在内存 fixture 中给创建者两个项目；A-301 报告标签仅有 prj_xinghui，金鹭访问返回 404 |
| 上轮 R4–R7 | 签署状态、空答案、冲突下补查、精确证据关联有实现和相关回归，通过本次全量测试；不能因此推断新增 LLM 引擎也已继承所有约束 |

代码中已存在 `LLMToolAgent`、领域 LLM 实现、工厂引擎选择、模型工具名映射、`.env` 加载、B/C 的模型注入入口。这些不再只是规划。

仓库中也有真实 DeepSeek 首跑产物，读取结果如下（本轮没有重新请求服务）：

| 归档 | 记录的实际内容 |
|---|---|
| `20261107T0232_real_model_investigate_deepseek.json` | conflicting、failures=[]，账本记录 8 次模型调用、12 次工具调用、14421 tokens |
| `real_model_dev/*B_single_agent.json` | 8 道开发题，1/7 自动计分通过，账本记录 18 次模型调用、35060 tokens |
| `real_model_dev/*C_multi_agent.json` | 8 道开发题，0/6 自动计分通过，账本记录 26 次模型调用、42217 tokens |

这证明仓库有真实调用及失败情况的归档，不代表本轮重新验证了 provider，也不代表上述账本在发生重试时一定等于物理调用消耗（见 N1）。开发集分母不同，且含未自动评分内容，不能拿来宣称 B/C 的质量优劣。

## 2. 需要修正的问题

本报告使用 N1–N6，避免与前两轮 F/S/R 编号混淆。

### N1 [P1] 模型重试复用预算 ID，实际调用超限且 token 少记

- 位置：`backend/app/runtime/tool_loop.py:92`、`:141`；`backend/app/agents/base/base_agent.py:122`；`backend/app/runtime/budget.py` 的幂等预留/结算。
- 原因：model_call_id 只有 run/subtask/round。BaseAgent 重试 `_execute()` 或图重跑同一子任务时，轮次重新从 1 开始，预算把新的物理请求当成已结算请求；实际客户端仍被再次调用。
- 本次复现：Billing 使用 `max_model_calls=1`，Fake 首轮返回非法调用并消耗 10 tokens，触发配置允许的 MODEL_ERROR 重试；第二次返回文本并消耗 20 tokens。**客户端实际调用 2 次，预算仍显示 used_model_calls=1、used_total_tokens=10；两次响应合计实际为 30 tokens。**
- 影响：调用上限不能按物理请求生效；失败重试时成本与 token 统计可能被低估。不能断言历史真实归档一定触发此问题，但当前账本不能作为所有失败路径下准确消耗的证明。
- 修复验收：区分物理请求 attempt 与幂等重放；每次真实发送使用唯一请求标识并完整记账，只有实际复用既有结果时才复用结算 ID。覆盖 BaseAgent 重试、图补查、并发子任务、首次失败、token 超限后的真实消耗记录。max_model_calls=1 时不得发出第二个物理请求。

### N2 [P1] 模型取回其他租约的数据，仍当成目标租约的调查结果

- 位置：`backend/app/agents/base/llm_agent.py:107`、`:140`、`:144`、`:194`；`backend/app/agents/base/facts.py`。
- 原因：目标 lease_id 只写在模型消息里，没有在工具执行前后强制校验；成功工具输出按工具名合并，下游不核对其实体是否对应当前请求。
- 本次复现：在内存 fixture 给可信主体星汇与金鹭两个项目权限；用户请求 A-301，Fake 却调用 `billing.statement.read(lease_jl_b101_2025)`。输出被完整接受，报告 `lease_id=lease_xh_a301_2025`，工具输出 lease_id 却为 `lease_jl_b101_2025`，最终 supported，finding 写“应收 0.00、已收 0.00、未收 0.00”。
- 边界：工具未越过主体项目权限；这里是**有权读取的错误实体**被绑定到当前报告，属于结果正确性错误，不能用项目权限检查替代目标校验。
- 修复验收：从可信计划生成本次任务允许的租约/商铺目标集合，在执行与结果归并处校验；比较任务可以显式声明多目标，普通单租约任务不得悄悄换目标。同一工具多次调用时，不能仅按工具名覆盖不同实体的结果。

### N3 [P1] LLM 检索路径绕过租约文档范围，其他租约合同再次进入报告

- 位置：`backend/app/agents/base/llm_agent.py:202`；`backend/app/tools/knowledge_tools.py:90`、`:108`。
- 原因：确定性 LeaseAgent 会解析本租约文档并传 document_ids；新 LLM 路径把这些参数交给模型自由决定。模型省略 document_ids 时工具使用 allowed=None，检索扩大到整个已授权项目，返回条款也没有与当前 lease 的适用集合核对。
- 本次复现：临时索引加入星汇 A-302 的已签署合同（明确登记 lease_id 为 A-302）。调查 A-301 时模型正常调用 A-301 lease.lookup，随后无范围调用 document.search。最终 A-301 报告的合同 finding 引用了 `doc_xh_a302_contract#v1#p1#5.2`，内容为只适用于 A-302 的 20% 递增。
- 影响：上轮文档归属修复在确定性路径成立，模型引擎下仍可绕过。签署状态和真实页码不能保证合同适用对象正确。
- 修复验收：文档适用范围由可信计划/目录解析后注入或与模型参数取交集；不能依赖模型主动填写 document_ids。LLM 和 deterministic 共用同一范围策略，测试模型省略范围、显式指定其他租约文档及公共制度例外。

### N4 [P1] 模型完全不取证，图仍判 supported / complete

- 位置：`backend/app/agents/base/llm_agent.py:140`–`:144`；`backend/app/orchestration/investigation.py:307`、`:348`、`:456`、`:580`。
- 原因：非空模型文本就可以结束工具循环；领域视图允许空输出；图将“Agent 返回成功”当作“子任务证据充分”，没有按能力验证必需字段/证据。
- 本次复现：用户问 A-301 还欠多少，Fake 第一轮只返回“已经核对，账单没有问题”，没有任何工具调用。实际 verdict=supported、completeness=complete、results_status=[success]、findings=[]、traces=0、failures=[]。
- 影响：无证据的任务被认定证据充分。仅检查模型回答非空不够，也不能靠 Prompt 要求模型必须取数。
- 修复验收：按 capability 定义最低结果契约及证据需求。账单能力没有有效账单工具结果、租约能力没有目标租约事实等情况应明确失败或证据不足。区分允许纯说明的问题与必须取证的业务查询；覆盖不调用工具、只调用无关工具、工具全失败后给出非空文本。

### N5 [P2] Billing/Property 模型收不到原问题和关键筛选条件

- 位置：`backend/app/orchestration/investigation.py:162`–`:164`；`backend/app/agents/base/llm_agent.py:104`–`:107`。
- 原因：Planner 仅为 Lease 子任务写 query；Property 的 category 虽然写在 payload，LLMToolAgent 构造消息时只取 question/query/lease_id，没有传 category、unit_id 等业务约束。Billing/Property 的 question 实际为空。
- 本次复现：请求“只查询 A-301 空调维修工单”，模型收到 `question=""` 且没有 category。在合成 fixture 副本增加一条电梯工单后，确定性路径返回 3 条空调工单；模型不传类别查询时返回 5 条全部工单，仍 supported。原 fixture 已有非空调工单，新增记录仅用于强化区分。
- 修复验收：将原问题或明确的领域子问题和 schema 化筛选条件完整传递；对可信计划确定的硬条件在工具边界执行，不能只补到提示词后任由模型丢弃。测试同租约多种工单、unit_id、类别及未来日期过滤条件。

### N6 [P1] 用户答案金额错误，自动评测仍可能满分

- 位置：`backend/app/evaluation/baselines.py:405`–`:406`；`backend/app/evaluation/scoring.py:282`；单 Agent 输出 answer 的路径。
- 原因：facts 从工具提取，answer 来自模型；金额评分只校验内部 facts，不校验用户看到的最终答案是否与 facts 一致。
- 本次复现：模型正确调用 A-301 账单工具，得到 outstanding_total=18036.00；最终却回答“A301 未收金额为 0.00 元，账单已经全部结清”。B 基线保留这段错误 answer，评测 expected_facts.outstanding_total=18036.00 仍 passed=true、correctness_rate=1.0。
- 边界：当前指标确实可以解释为“内部工具事实提取正确”，但不能据此声称“用户回答金额正确”。Prompt 中要求金额来自工具，并未构成程序约束。
- 修复验收：将结构化业务结论与模型叙述分离，并保证展示给用户的金额由可信字段渲染或经过明确一致性校验；评测分别记录工具事实准确性、最终答案准确性及未评内容。加入“facts 正确但 answer 写错/否认欠费”的反例。评分逻辑变更需升版并保留旧报告。

## 3. 架构与完成范围

本次模型客户端注入是真实代码，不再属于“只缺模型装配”的旧状态。不过独立配置还需明确策略：`app/llm/factory.py:43` 的 DeepSeek 工厂读取 single.yaml，随后同一客户端被注入各领域 Agent。修改领域 YAML 的模型名/采样/输出长度不会自动重建相应客户端。可以规定全局模型覆盖，也可以按 AgentConfig 构造客户端，但不应让独立配置中的模型参数无声失效。

当前主要风险集中在“确定性引擎的约束没有完整迁移到 LLM 引擎”，不需要推倒现有模块。建议共用请求目标/筛选/文档范围策略与结果校验契约，保留模型选工具的能力；金额计算、权限与事实核验继续由确定性模块负责。

真实 DeepSeek 首跑与 dev 归档可以保留为历史证据；修复 N1/N6 后如要做质量/成本结论，应另建冻结实验，而不是回写历史测量。PostgreSQL、真实 heldout、多次稳定性测量、人工量表、部署/真实鉴权仍未在本轮完成。

## 4. 建议实施顺序

1. N1：先修物理调用与 token 记账，避免后续真实评测的预算和测量口径失真。
2. N2/N3/N5：统一可信目标与筛选约束，堵住换租约和扩大文档范围的入口。
3. N4/N6：定义“完成了什么”及“用户答案是否正确”，补充结果契约与最终输出测试。
4. 再运行原有 301 项回归与新反例，并在明确预算下重新测量真实模型；相关结果归档需绑定代码、数据、模型参数和评分版本。

本轮反例全部使用 Fake/scripted、临时合成数据和临时目录。没有查看或输出本地密钥值，没有修改 fixture 或业务源码，也没有产生新的 provider 费用。
