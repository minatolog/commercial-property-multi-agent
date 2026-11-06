# Agent-First 版本候选：进度与缺陷审查

- 日期：2026-11-06（Asia/Shanghai）
- 审查者：Codex，按项目所有者本次请求进行独立检查；不恢复逐任务 Codex 审查流程。
- 对应任务：016；关联 Task 007–015。
- 被审查代码：`main` / `041b2c5`，检查开始时与 `origin/main` 一致，工作区干净。
- 结论：**离线功能模块和演示材料已搭齐，但存在集成故障、错误评分和状态/证据隔离问题，尚不满足完整 MVP 验收条件。**
- 操作范围：阅读代码与文档、运行现有测试及临时复现脚本、归档结果。未修复业务代码，未调用外部模型，未连接 PostgreSQL，未提交或推送。

## 1. 实际进度

从 `fe95ba5` 到当前 HEAD 共新增 8 个提交，包含 LangChain/LangGraph、数据库、RAG、审批、评测、API 和交付文档。

| 任务 | 代码实际情况 | 本次判断 |
|---|---|---|
| 007 Runtime / Tool Executor | 运行时、预算、权限、Trace 与租约核销金额口径已有实现 | 基础可用；现有测试通过 |
| 008 模型 Tool Calling | LangChain/DeepSeek 适配器、有限轮工具循环和独立 `ask` 命令已实现 | 真实调用未验证；异常模型响应会误报成功，见 F6 |
| 009 LangGraph 调查 | 规则规划、条件分支、Send 扇出、领域工具代理、核验、限次补查已实现 | 离线路径可运行；成功补查仍残留失败结论，见 F4 |
| 010 数据库 | SQLAlchemy 模型、Alembic、种子与查询层已实现 | PostgreSQL 未验证；文档所列 SQLite 调查命令实际崩溃，见 F3；只读装配有缺口，见 S2 |
| 011 合同 RAG | 两份合成 PDF、真实文本/页码、分块、BM25、启发式引用校验已实现 | 检索存在；Lease Agent 未限定本租约文档，见 F7 |
| 012 持久化/审批 | SQLite checkpoint、独立审批台账、两级审批、恢复和草案输出已实现 | 正常流程可运行；恢复请求 ID 错误、版本重放缺口，见 F5/S1 |
| 013 Evaluation | 8 道开发题、32 道保留题、三个离线执行路径、JSON/Markdown 报告已实现 | 评分器有实质错误；当前比较结果不能作为质量提升证据，见 F1/F2 |
| 014 API / 演示页 | FastAPI、运行索引、详情、Trace、审批入口及静态页面已实现 | 进程内正常流程测试通过；主体隔离和输入校验有问题，见 F8/S3 |
| 015 交付 | README、环境模板、演示脚本、里程碑已归档 | 可供继续修正的版本候选；不能据任务编号全部自检就宣称项目完成 |

### 真实模型接入仍有工程工作

`build_investigation_bundle()` 装配的是 `RuleBasedPlanner` 和 `ToolBackedAgent`，没有模型客户端注入；`SingleAgentBaseline.run()` 是关键词识别后的固定工具循环，没有复用 `SingleToolAgent`。`evaluate()` 将模型绑定固定写为 `offline_deterministic`。因此，**仅提供 API Key 不会让现有调查图或三基线评测自动变成真实模型工作流**。

真实模型工具闭环的代码入口目前是独立的 `ask --provider deepseek`。后续需要明确模型在调查工作流中的作用，以及真实 B/C 基线的装配和测量入口。这不要求所有节点都使用 LLM；确定性计算、权限和验证节点应继续保持确定性。

## 2. 本次实际验证

解释器：`D:\anacada\envs\commercial-agent\python.exe`。命令在 `backend/` 执行。

| 验证 | 实际结果 |
|---|---|
| `python -m unittest discover -s tests -p 'test_*.py'` | 192 tests，约 10 秒，OK |
| `python tests/smoke_agent_contracts.py` | 57 项通过 |
| 在内存调用 `evaluate(..., split='heldout')`，三个基线分别重跑 | 重现 A 15/27、B 16/27、C 23/27；未写入或覆盖旧报告 |
| `python -m app.cli investigate --backend sqlite` | exit 1，`AttributeError: 'DatabaseRepository' object has no attribute 'snapshot'` |
| 临时反例：交换三个金额字段 | 三项事实全部错误仍被评分为 3/3 |
| 临时故障注入：一次失败、第二次成功 | 两个子任务均已成功返回，最终仍 `insufficient` / `partial` |
| 临时控制面：调查→经理批准→财务批准 | 批准成功；返回的审批请求 ID 与持久台账 ID 不同，且返回 ID 无台账记录 |
| 临时 LangChain 非法工具响应 | 非法调用被丢弃，空答案被标记 `success` / `final_answer` |
| 临时索引加入同项目 A-302 合同 | A-301 调查报告引用了 A-302 条款 |
| 临时共享 RunIndex，不同真实 fixture 主体访问 | 金鹭主体读到了星汇主体的报告 |
| 临时内存 SQLite 检查/写入 | `PRAGMA query_only=0`；UPDATE 可执行，随后 rollback 并关闭内存库 |
| API 错误输入 | `max_tool_calls='abc'/null/-1` 均 500；`question=null` 被当作字符串 `None` 创建任务 |

临时文件和审批库均使用临时目录；数据库写入反例只操作新建内存测试库。现有 192 项测试未因上述反例新增或修改。

## 3. 优先修复项

P1 表示应在完整 MVP 验收/正式展示质量结论前修复，不表示已发生生产事故。

### F1 [P1] 金额评分没有绑定字段，三个金额互换仍满分

- 位置：`backend/app/evaluation/scoring.py:167`。
- 原因：将 answer 与所有 facts 拼成字符串，使用 `text in haystack` 判断某字段是否正确；没有比较当前 key 对应的值。
- 反例：真值为 `invoiced_total=52596.00, paid_total=34560.00, outstanding_total=18036.00`；将输出改为 `34560.00, 18036.00, 52596.00`，答案留空，仍得到 `passed=true, correctness_passed=3, correctness_total=3`。
- 影响：金额口径错误、字段错置、在其他位置出现同一数字都会被误判；README 的自动断言通过率不能据此证明财务准确性。
- 修复验收：按字段做类型化比较，金额用 Decimal 且明确精度；增加字段交换、错误数值包含正确子串、正确值只出现在无关字段等反例；升级评分版本，生成新报告，保留历史。

### F2 [P1] 权限题正确拒绝被判失败，导致基线比较偏差

- 位置：`backend/app/evaluation/scoring.py:196`；`backend/app/evaluation/baselines.py` 的 A/B/C 状态转换。
- 原因：评分器对任何 `status='denied'` 无条件增加一项失败断言。C 在全部子任务拒绝时使用 `failed`，没有受到相同惩罚。
- 复现：H06 缺 billing.read，H11 跨项目访问。A 确实没有输出禁止的业务值，禁用内容断言通过；随后仍因 `H06-P` / `H11-P` 被判失败。
- 影响：A/B 正确守住权限边界也被扣分，C 的相同行为使用不同状态绕过这条扣分。当前 C 领先不能直接归因于架构收益。
- 修复验收：用例显式声明预期 outcome/拒绝原因；在同一状态和权限规则下评三基线；预期拒绝且无泄露应通过，未授权返回数据必须失败。增加跨基线一致性反例并重跑报告。

### F3 [P1] 数据库与 RAG 接线不兼容，公开的 SQLite 演示命令直接崩溃

- 位置：`backend/app/investigation_demo.py:80` → `backend/app/rag/library.py:37`、`:88`。
- 复现：`python -m app.cli investigate --backend sqlite`。
- 实际：`DatabaseRepository` 没有 `snapshot()`，但知识库装配无条件调用它，进程 exit 1。
- 影响：Task 010 的仓库测试通过没有覆盖后来接入 RAG 后的完整工作流；JSON/数据库数据源替换目前在公开入口失效。
- 修复验收：定义文档元数据/片段访问契约或注入独立知识源，消除对 fixture 全量快照的依赖；真实运行上述 CLI，并覆盖 SQLite + RAG（以及需要时审批）的集成路径。不能只关掉 RAG 来声称完整替换成功。

### F4 [P1] 补查成功不能消除当前失败，恢复后仍判调查不完整

- 位置：`backend/app/orchestration/investigation.py:82`、`:262`、`:429`、`:439`。
- 原因：failures/missing 使用追加 reducer；verify 与 report 把历史失败持续视为当前失败。revise 还会把 plan 缩成待补任务，原始完整计划与当前执行批次混用。
- 复现：使用 `v_oct_rent_corrected`，问题“核对账单和工单”；令 Property 第一次返回 tool_timeout、第二次成功。实际 `calls=2, results=2, revision=1`，最终仍为 `insufficient`、`completeness='partial'`，缺失列表仍写“未获得子任务结果”。
- 修复验收：分离历史尝试与当前子任务状态，保留原始预期子任务集合；恢复成功后当前 failures/missing 清除，历史错误仍可从 trace 审计；增加首次失败后恢复成功、持续失败和并发归并测试。

### F5 [P1] 审批恢复生成新请求 ID，报告引用不存在的审批记录

- 位置：`backend/app/orchestration/investigation.py:521`、`:553`、`:688`。
- 原因：LangGraph 恢复时重新执行审批节点，重新构造随机 request_id；`ApprovalStore.create()` 能返回已存在请求，但 hook 丢弃这个返回值，节点继续使用新构造的请求。
- 复现：两级批准后，台账是 `apr_0dcc34996663`，返回结果是 `apr_759f2c211b2a`；`store.get(returned_id)` 为 None。
- 影响：已批准结果中的请求身份和审计链断开；返回的 approval_request 还可能保留新建时的 pending stages，与 approved 状态矛盾。
- 修复验收：审批节点重放复用持久请求的同一 ID；恢复结果回读权威台账状态。首次暂停、两级决定、重新启动、重复恢复后的 ID、version、status、stages 均一致。

### F6 [P1] LangChain 非法工具调用被静默丢弃，空答案被当作成功

- 位置：`backend/app/llm/langchain_client.py:152`；`backend/app/runtime/tool_loop.py:154`。
- 原因：转换只处理 response.tool_calls，不处理 LangChain 的 invalid_tool_calls；循环把“没有有效 tool_calls”直接当最终答案，也未以 finish_reason 区分异常结束。
- 复现：本地构造 `AIMessage(content='', invalid_tool_calls=[...], response_metadata={'finish_reason':'tool_calls'})`，经真实转换函数产生零工具调用。交给单 Agent 循环后返回 `status='success'`、`stop_reason='final_answer'`、空 answer、零 evidence。
- 修复验收：保留并反馈非法调用或明确 MODEL_ERROR；空输出、截断结束、非法 JSON、正常最终回答分别有可检查的结果。测试应经过 LangChain 响应转换，不能只验证 Fake 的通用 parse_tool_call。

### F7 [P1] 租约条款检索只有项目范围，没有目标租约/文档范围

- 位置：`backend/app/agents/lease/agent.py:101`。
- 原因：取得 lease.lookup 的 document_ids 后，检索只传 query/top_k，没有传目标 document_id 或允许文档集合。项目权限相同不代表合同适用于当前租约。
- 复现：在临时索引加入 `prj_xinghui` 的 A-302 合同，条款为“A302 租金递增百分之二十，仅适用于 A302”。查询 A-301 的“合同租金递增百分之二十”，返回文档列表首项为 `doc_xh_a302_contract`，并将其写入 A-301 报告 finding。
- 影响：证据确实存在，但属于错误合同；真实页码不能保证结论适用于目标租约。
- 修复验收：合同检索按当前租约关联的文档及版本限定；公共制度文件作为单独有适用范围的证据类型处理。测试同项目两租约、不同文档版本和公共制度的归属。

### F8 [P1] 运行索引查询没有主体/项目过滤，数据层隔离未延伸到 API

- 位置：`backend/app/api/service.py:248`、`:254`；RunIndex 的 get/list。
- 原因：查询仅依据 run_id 或全局列表，没有核对记录的 principal_id 或项目范围。
- 复现：星汇主体通过 WorkflowService 创建运行；使用同一个临时 RunIndex，另建 `principal_finance_jinlan` 服务（fixture 中仅有 `prj_jinlan` 授权），仍能 list/get 星汇租约 `lease_xh_a301_2025` 的报告与 findings。
- 边界：当前 HTTP 身份固定，未证明请求体可切换主体。本项复现的是共用索引、服务身份切换/多实例时的授权缺失，独立于 README 已披露的“演示鉴权不是真认证”。
- 修复验收：list/detail/traces/decide 都从可信主体检查所有权或明确项目 ACL；配置身份切换后也不能读旧主体数据；禁止依赖随机 run_id 保密。

## 4. 其他确认的问题

### S1 [P2] 已终态审批的幂等分支绕过版本校验和重新授权

`backend/app/orchestration/approval.py:435` 的 approved/rejected 分支早于 `:462` 版本校验与后续授权。批准 v2 后，同一个财务主体用 `draft_version=999` 重放仍返回 approved。应先验证身份、权限、范围及请求版本，再判定是否为可接受的幂等重放；幂等不能让错误版本看起来获批。

### S2 [P2] 实际数据库装配没有启用声明的只读连接闸门

`backend/app/db/bootstrap.py:56` 直接使用 `Session(engine)`，没有进入 `session_scope(read_only=True)`。新建内存库实测 `PRAGMA query_only=0`，UPDATE 被接受。当前没有暴露写工具，所以不代表普通 API 请求可任意执行 UPDATE；但“连接层强制只读”的实现承诺未在实际装配中兑现。应在工具仓库会话及每次新事务/连接上启用只读，并通过真实装配验证拒写。

### S3 [P2] API 使用字典与手动强转，非法参数触发 500

`backend/app/api/app.py:138`–`:141`：max_tool_calls 为 `abc`、null、-1 均返回 500；question 为 null 被转换成字符串 `None`，返回 201。应使用 Pydantic 请求模型校验非空文本、严格布尔和非负且有上限的预算，并统一验证错误与 trace 响应。

### S4 [P2] API 返回的 run_id 与工具 trace 中 run_id 不一致

`backend/app/api/service.py:207` 生成公开 run_id；`backend/app/investigation_demo.py:112` 又生成 context.run_id，未注入同一值。本次运行公开 ID 为 `run_bd96b480f938`，trace 归属为 `run_084f647c2d52`。应注入统一运行身份，测试公开 ID、checkpoint context、审批 run_id 和每条工具 trace 的关联关系。

另有静态检查发现：API 接收 reason，但 WorkflowService.decide 没有传到 Investigator/ApprovalStore；正常 CLI 恢复也未转发 args.reason。审批意见会丢失，修复 F5 时应一并验证其持久化。

## 5. 架构评价与未完成范围

值得保留：Agent Protocol/Registry、独立 YAML/Prompt、统一 ToolExecutor、确定性 Decimal 金额、独立 checkpoint/审批台账、同源轻量演示页。这些均已有代码和测试依据，保留当前结构逐项修正即可。

主要耦合：知识库与草案解析依赖 FixtureRepository.snapshot；仅凭“Coordinator 没有 import 具体 Agent”不能证明数据源可替换。建议按使用场景定义 Repository/DocumentCatalog/DraftRepository 的小接口，装配层注入，避免把完整 fixture 快照作为跨层公共协议。

仍需完成或单独验证：

1. 至少一次真实 DeepSeek 工具调用，以及调查工作流/评测的真实模型装配；不能仅补一个 Key 就把现有离线评测称为真实 Agent 对照。
2. 可连接的 PostgreSQL 驱动、配置、测试实例、迁移和 fixture 等价性验证；专用约束/RLS 是否纳入精简 MVP 需按现有需求明确，不将旧 14 表草案全部搬入。
3. 修正评分器后重新冻结评分规则；补齐 5 道无自动判定题（H22/H25/H26/H27/H30）。不要把 32 道保留题写成 32 道均已有效评分；本次仅 27 道进入分母。
4. 当前 B 是规则多工具循环，A 被限制成单工具；缺少同等任务能力的强确定性工作流对照。应说明实验在比较哪些因素，再补真实 B/C 和统一安全语义，不能据现有百分比宣称多 Agent 提升。
5. 独立环境复现未在本轮执行；未做浏览器视觉验收、真实服务鉴权、部署或外部副作用验证。现有说明明确披露其中多项限制，这一点应保留。
6. 路线图表格已写 Task 015 自检，但正文仍写“Prompt 2–5 自检通过”、底部保留旧的逐任务 Codex 流程；应统一现行状态与历史记录的区别。`backend/commercial_agent_migrate.db` 已被 Git 跟踪，与运行态应排除的规范不一致，先确认用途再处理。

## 6. 建议后续开发顺序与验收

| 顺序 | 范围 | 完成标准 |
|---|---|---|
| 第一批：正确性与隔离 | F1/F2/F7/F8 | 金额交换必败；预期拒绝能正确评分；A-301 不引用 A-302；主体切换不能看到旧报告；升版评分后保留旧报告并重跑 |
| 第二批：完整运行链路 | F3/F4/F5/F6 + S1–S4 | SQLite+RAG 调查成功；一次失败后恢复为正确最终状态；审批 ID/版本/阶段一致；异常模型响应明确失败；真实装配拒写；API 4xx 与 trace/run 身份一致 |
| 第三批：真实集成与交付 | 模型/PG/评测/复现 | 有真实模型工具闭环记录；可选择真实模型的 B/C 评测；PG 迁移/等价性验证；有模型、配置、数据、评分版本及成本口径；独立环境按 README 复现 |

本次不自动开始修复或创建 Git 提交。建议先把第一、二批交给 DeepSeek 修正，再进行第三批。任务自检历史可保留，但当前项目状态应显示“版本候选，审查发现待修正”，不写“项目已全部完成”。
