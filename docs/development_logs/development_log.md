# 开发日志

按时间追加，最新记录在最上方。每条记录对应一次开发任务。

---

## 模板

```markdown
## [YYYY-MM-DD] 任务 NNN - 任务标题

- **日期**：YYYY-MM-DD
- **开发阶段**：环境搭建 / 数据层 / RAG / Agent 编排 / API 层 / 测试
- **对应 Prompt 归档**：`docs/prompts/<模块>/YYYY-MM-DD_NNN_任务名称.md`

### 本次完成的功能

- 功能点 1
- 功能点 2

### 主要技术决策

| 决策 | 选择 | 理由 |
|---|---|---|

### 修改的文件

| 文件 | 变更 |
|---|---|

### 测试和验证结果

| 验证项 | 命令 / 方式 | 结果 |
|---|---|---|

### 当前项目状态

一句话说明当前可运行到什么程度、有哪些已知缺口。

### 下一步开发计划

- [ ] 计划 1
- [ ] 计划 2
```

---

## [2026-11-06] 任务 007 返修 - Prompt 2-R1（F1/F2，待 Codex 复验）

- **日期**：2026-11-06
- **开发阶段**：Agent 编排 / Runtime（返修）
- **执行者**：DeepSeek（DeepSeek Harness 会话）
- **返修依据**：`docs/reviews/2026-11-06_task007_review.md` 的 Prompt 2-R1
- **对应归档**：`docs/prompts/04_agents/2026-11-06_007_agent_runtime_controlled_tools.md` §16

### 本次完成的功能

- **F1 账单租约隔离**：`FixtureRepository.statement()` 先用当前 `lease_id` 算出 invoice ID 集合，allocations 必须落在这些账单上；payments 只返回被这些 allocations 引用的已确认收款。同项目其他租约的付款不再减少本租约已收额。
- **F2 单次运行 Trace 隔离**：`ToolTrace` 增加 `run_id`（执行器从 `AgentContext.run_id` 写入）；`AgentRuntime.run()` 每次生成新 `run_id`，结果只截取本 run 的 Trace；共享 `TraceLog` 保持 append-only，不清空（并发 run 不会互相丢数据）。
- **回归测试**：新增 F1 2 个、F2 2 个，共 4 个；测试套件 47 → 51。

### 主要技术决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 付款归属 | 以"本租约账单 ID"为唯一桥梁（invoice → allocation → payment） | 只按项目过滤会把同项目他租约的付款算进来 |
| 无核销付款 | 不计入已收 | 未核销到本租约的收款不能减少本租约未收 |
| Trace 隔离 | 按 `run_id` 过滤，不清空共享日志 | 清空会让并发 run 丢 Trace；过滤保留全局可观测能力 |
| run_id 传递 | `AgentContext.run_id`（可空）→ `ToolTrace.run_id` | 不新建并行上下文类型，向后兼容 |

### 修改的文件

| 文件 | 变更 |
|---|---|
| `backend/app/fixtures/repository.py` | F1：statement 的 allocations/payments 按本租约账单过滤 |
| `backend/app/runtime/agent_runtime.py` | F2：run_id 生成、`_traces_for_run()`、结果只含本 run Trace |
| `backend/app/runtime/types.py` | F2：`ToolTrace.run_id`、`to_agent_context(run_id=...)` |
| `backend/app/agents/base/contracts.py` | F2：`AgentContext.run_id`（可空） |
| `backend/app/tools/executor.py` | F2：Trace 写入 `run_id` |
| `backend/tests/test_runtime.py` | 新增 F1/F2 回归；日志改走 stdout 避免 PowerShell 误判 stderr |

**未改**：业务工具查询范围、三个 Agent YAML、数据库设计、历史 Prompt 原文；未安装依赖、未调用模型、未建库、未提交/推送。

### 测试和验证结果

| 验证项 | 命令 | 结果 |
|---|---|---|
| 既有骨架自检 | `python tests/smoke_agent_contracts.py` | ✅ 57 项通过，退出码 0 |
| 自动化测试 | `python -m unittest discover -s tests` | ✅ `Ran 51 tests ... OK`，退出码 0 |
| CLI `--help` / `tools` / `check` / `demo` | `python -m app.cli ...` | ✅ 退出码均 0 |
| 数据变体 | `python -m app.cli demo --variant v_oct_rent_corrected` | ✅ 未收 `17280.00` |
| 预算耗尽 | `python -m app.cli demo --budget-tool-calls 1` | ✅ 退出码 2，`BUDGET_EXHAUSTED` 可见 |

### 当前项目状态

Task 007 **R1 已修复，待 Codex 复验**；未提交、未推送；Task 008 未开始。

### 下一步开发计划

- [ ] Codex 复验 F1/F2 与新增回归测试。
- [ ] 通过后再评估阶段性基线提交（由用户确认）。

---

## [2026-11-06] 任务 007 - Agent Runtime 与受控工具执行（待 Codex 验收）

- **日期**：2026-11-06
- **开发阶段**：Agent 编排 / Runtime
- **执行者**：DeepSeek（DeepSeek Harness 会话）
- **对应 Prompt 归档**：`docs/prompts/04_agents/2026-11-06_007_agent_runtime_controlled_tools.md`（Prompt 2）
- **前置验收**：Task 006 R2 复验通过（`docs/reviews/2026-11-06_task006_r2_review.md`）

### 本次完成的功能

- **K1–K5 修复**：Registry 替换改为副本计算+原子发布；工厂启动期校验配置 `version`/`capabilities` 与实现类一致；单次执行 `timeout=min(配置超时, 剩余 deadline)` 且重试不越过 deadline；`PARTIAL`/`SKIPPED` 聚合语义穷尽化（全 SKIPPED → FAILED）。
- **Agent Runtime**：`TrustedContext` 只由可信主体构造，payload 出现 `permissions`/`project_ids`/`principal_id` 等保留键直接判 `INVALID_REQUEST`；按 capability 解析 Agent；汇总证据、Trace 与预算。
- **Tool Registry / Executor**：静态白名单（拒绝重名/非 `BaseTool`）、`allowed_tools` + 权限双授权、严格输入/输出 Schema、项目范围、超时、可配置有限重试、并发安全预算（原子预留/结算，按 `call_id` 幂等）、结构化 Trace（不含原始参数）。
- **fixture 只读仓库 + 4 个只读工具**：`lease.lookup`、`billing.statement.read`、`billing.arrears.calculate`、`property.work_orders.read`；金额全 `Decimal`，证据带 dataset version / as_of / project / synthetic / 记录 ID 与调用 ID。
- **离线 CLI 与演示**：`python -m app.cli --help|tools|check|demo`；`demo` 用 Fake `ScriptedToolAgent` 跑通 Runtime→Agent→Executor→Repository，未调用模型。
- **工程入口**：`backend/pyproject.toml`（仅 pydantic/PyYAML + pytest 配置 + `app.cli:main`）、`backend/README.md`。

### 主要技术决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 预算记账 | 两阶段 `reserve`/`settle`，`call_id` 幂等 | 并发不超发；重试与重放不重复扣费 |
| 项目范围 | 只来自 `TrustedContext`，payload 保留键直接拒绝 | 防止用户/模型自报权限；工具参数无法猜出别家数据 |
| 证据来源 | 工具产出 `EvidenceDraft`，执行器补齐来源字段 | 工具无法伪造 `source_tool`/`tool_call_id` |
| 重试归属 | 仅工具层，`max_attempts` 可配置且 ≤5 | 避免图/节点/工具重试相乘 |
| Trace | 只存 16 位参数摘要与状态 | 满足可追溯，同时不落原始参数（可能含敏感值） |
| 测试框架 | `unittest.TestCase`（pytest 可收集） | 环境无 pytest 且本任务禁止安装 |
| 演示 Agent | Fake `ScriptedToolAgent`，配置在代码中构造 | 不改 3 个正式 Agent YAML，也不冒充真实模型调用 |

### 修改的文件

- 新增：`backend/pyproject.toml`、`backend/README.md`、`backend/app/fixtures/{__init__,repository}.py`、`backend/app/runtime/{__init__,types,budget,agent_runtime}.py`、`backend/app/tools/{registry,executor,fixture_tools}.py`、`backend/app/demo.py`、`backend/app/cli.py`、`backend/tests/test_runtime.py`。
- 修改：`backend/app/agents/base/{errors,contracts,base_agent,registry}.py`、`backend/app/agents/factory.py`、`backend/app/orchestration/coordinator.py`、`backend/app/paths.py`、`backend/app/tools/base.py`。
- 文档：本日志、007 归档、Docs README、Issue、Git 检查点、路线状态。

**未修改**：`docs/architecture/database_design.md`、三个 Agent 业务实现与 YAML、历史 Prompt 原文。

### 测试和验证结果

Python 3.11.18（`D:\anacada\envs\commercial-agent\python.exe`），未安装任何依赖。

| 验证项 | 命令 | 结果 |
|---|---|---|
| 既有骨架自检 | `python tests/smoke_agent_contracts.py` | ✅ 57 项通过，退出码 0 |
| 新增自动化测试 | `python -m unittest discover -s tests -v` | ✅ 47 个测试通过，退出码 0 |
| CLI 帮助 | `python -m app.cli --help` | ✅ 退出码 0 |
| CLI 工具清单 | `python -m app.cli tools` | ✅ 4 个工具 |
| CLI 配置检查 | `python -m app.cli check` | ✅ 3 Agent / 4 能力 / 4 工具 |
| fixture 演示 | `python -m app.cli demo` | ✅ `success`；3 调用、3 Trace、24 证据；未收 `18036.00` |
| 数据变体 | `python -m app.cli demo --variant v_oct_rent_corrected` | ✅ 未收 `17280.00` |
| 预算耗尽 | `python -m app.cli demo --budget-tool-calls 1` | ✅ 退出码 2，`BUDGET_EXHAUSTED` 可见 |
| pytest | `python -m pytest --version` | ⚠️ 未安装（本任务禁止安装），已记入 Issue |

### 当前项目状态

Task 007 的 Runtime、Tool Executor、fixture 只读工具与 CLI 已可离线运行并自检通过；**待 Codex 独立验收**。真实模型、LangGraph、数据库、RAG、审批与 FastAPI 尚未实现（按任务范围）。未提交、未推送。

### 下一步开发计划

- [ ] Codex 验收 Task 007；通过后编写 Prompt 3 / 任务 008（LangChain + DeepSeek 真实工具调用）。
- [ ] Task 008 需要模型依赖与密钥时，由项目所有者确认安装与预算。

---

## [2026-11-06] Task 006 / Prompt 1-R2 — Codex 复验通过

- **执行者**：Codex（独立复验）
- **复验报告**：[`docs/reviews/2026-11-06_task006_r2_review.md`](../reviews/2026-11-06_task006_r2_review.md)
- **结论**：Task 006 规格基线验收通过；路线图为 Prompt 1/10 已验收，Prompt 2/10（Task 007）待实施。

### 验证结果

| 项目 | 命令 / 方式 | 结果 |
|---|---|---|
| 场景选择器 | 运行 DeepSeek 临时 `verify_r2.py` | PASS=62 / FAIL=0；真实 JSON 展开 14 项 |
| 审批回归 | 运行 DeepSeek 临时 `regress_approval.py` | PASS=30 / FAIL=0 |
| 文件范围 | 运行 hash 比对脚本并检查真实文件 | 94 文件中授权范围内 8 个变化；backend 62 文件与 database_design 未变 |
| Git 检查 | `git diff --check` | 仅既有 `database_design.md:1661` EOF 告警 |

复验对象是规格、样例和参考选择器，不是 Runtime、模型 API 或数据库。未修改业务代码/数据库，未暂存、提交或推送。

### 下一步

- [ ] 按路线图起草 Prompt 2 / Task 007：Agent Runtime 与受控工具执行。
- [ ] 沿用 Codex Prompt → DeepSeek 落地 → Codex 独立验收 → 里程碑 Git 检查点流程。

---

## [2026-11-06] 任务 006 返修 - Prompt 1-R2（返修完成，待 Codex 复验）

- **执行者**：DeepSeek（DeepSeek Harness 会话）
- **对应归档**：`docs/prompts/04_agents/2026-11-03_006_agent_first_baseline.md`（§15）
- **返修依据**：`docs/reviews/2026-11-06_task006_r1_review.md` 第 4 节 Prompt 1-R2（窄范围两项）
- **执行前状态**：分支 `main`，HEAD `7ed2665bb9201568a8d74a12af37bf0a502378f1`；94 个文件（排除 `.git`）逐文件 SHA-256 记为基线

### 本次完成的功能

- **场景选择协议对齐实际 JSON 结构**：JSONL 的 `scenarios` 是数组、case 没有顶层 `scenario_id`。新增 `run_items(case)` 语义：有 `scenarios` 的 case 展开为 `(case_id, scenario_id)` 独立运行项，每个只跑一次；无 `scenarios` 的 case 恰好跑一次。运行项用同一个 `scenario_id` 在 case 数组中匹配断言、在 `variant.scenarios` 映射中取事件与证据要求。
- **错误行为可判定**：缺失 / 重复 / 未知 `scenario_id`、空数组、非数组、默认场景缺失或未知、case 与 fixture 场景不一致，共 8 类错误码，一律 fail fast，不静默回退。
- **审批重放改为重复投递**：`approval_replay` 中第二次 `evt_apr_fin_grant_003` 删除 `replayed` 字段，与第一次逐字段相同；重复次数由 `delivery.duplicates` 表达。
- **幂等 / 冲突双向验证**：同 ID 同内容 → 幂等忽略 1 次、预算增量 0；同 ID 异内容（改 `decision` 或 `occurred_at`）→ `EVENT_ID_CONFLICT`。
- **同步四处**：`evaluation_plan.md` §2.3（运行项展开/双端匹配/错误行为）、fixture `scenario_protocol`、C06/C08 JSONL、只读选择器验证脚本。

### 主要技术决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 场景连接方式 | 用 `scenario_id` 连接数组与映射，不用数组下标 | 下标会随用例编辑漂移；ID 是稳定键 |
| 运行项语义 | 有场景展开、无场景单跑 | 让 runner 的循环单位明确，评测可按运行项出明细 |
| 错误处理 | 8 类错误码 + fail fast | 静默回退会把 C06 主路径与 probe 混淆 |
| 一致性 | case 场景必须与 fixture 场景逐项一致 | 防止"评测断言"和"注入事件"各说各话 |
| 重放表达 | 重复投递（次数在场景配置），事件内容不变 | 契约规定同 ID 同内容才幂等；加标记等于制造冲突 |

### 修改的文件

| 文件 | 变更 |
|---|---|
| `docs/evaluation/fixtures/agent_first_v1.json` | `scenario_protocol` 重写为 r2；`approval_replay` 删除 `replayed`、新增 `delivery`；`spec_revision` → r2 |
| `docs/evaluation/cases/smoke_v1.jsonl` | C06/C08 协议版本 r2 + `scenario_expansion`；`scenario_resolution` 改写；probe `evidence_policy` 统一为 `required_on_success` |
| `docs/evaluation/evaluation_plan.md` | §2.3 重写；§5.1/§5.2 改为运行项；§7；§9 新增 S7–S9 |
| `docs/architecture/agent_runtime_contracts.md` | §9.2、§12.6：重复投递表达重放，禁止 `replayed` 字段 |
| `docs/prompts/04_agents/2026-11-03_006_agent_first_baseline.md` | 追加 §15 与 §5/§6/§7/§9 记录 |
| `docs/README.md` | 006 状态更新为 R1/R2 返修完成、待复验 |
| `docs/development_logs/development_log.md` | 本记录 |
| `docs/checkpoints/git_history.md` | R1-R2 检查点 |

**未修改**：`backend/`（62 个文件 hash 一致）、`docs/architecture/database_design.md`、ADR-005、Review、总路线、历史 Prompt 原文、审批角色规则与业务事实。

### 测试和验证结果

命令：`D:\anacada\envs\commercial-agent\python.exe -X utf8 <verify_r2.py>`（Python 3.11.18，仅标准库）

| 验证项 | 结果 |
|---|---|
| JSON / JSONL 解析 | ✅ 8 行、C01–C08 唯一有序；fixture 与 JSONL 协议版本均为 r2 |
| 运行项展开（真实 JSON 求值） | ✅ 14 项：C06=2、C08=6、其余各 1 |
| C06 选择器 | ✅ main → `evt_tool_fault_main_001`（2 次失败）；probe → `evt_tool_fault_probe_001`（1 次失败后成功）；证据 `[]` / 3 张发票 |
| C08 选择器 | ✅ 6 场景事件与 expected 终态/审批状态全部匹配 |
| 普通 case | ✅ `scenario_id=null`，事件取 `variant.events`，只跑一次 |
| 错误注入 10 例 | ✅ 8 类错误码全部按预期抛出 |
| 同 ID 同内容幂等 | ✅ 逐字段相同、无 `replayed`；ignored=1、唯一事件 3、预算增量 0 |
| 同 ID 异内容冲突 | ✅ 改 `decision` / `occurred_at` 均抛 `EVENT_ID_CONFLICT` |
| 证据 / Decimal / 链接 / 编码 | ✅ 证据全命中；`18036.00`、`756.00`、更正后 `17280.00`；0 断链；0 U+FFFD |
| 文件级 hash | ✅ 94 → 94，0 新增/删除；8 个变化（授权范围）、86 个不变 |
| C08 审批状态机回归 | ✅ 30/30（删除 `replayed` 后，六场景终态/角色/版本/过期行为不变） |
| `git diff --check` | ⚠️ 仅 `database_design.md:1661` 任务 005 遗留告警 |

程序化检查合计 **PASS=62 / FAIL=0**（会话内一次性只读校验，不属于仓库交付物）。

### 当前项目状态

Task 006 **返修完成，待 Codex 复验**；未提交、未推送；Prompt 2 / 任务 007 尚未开始。

### 下一步开发计划

- [ ] Codex 复验 R1-R2 两项与选择器/事件哈希断言。
- [ ] 通过后才发送 Prompt 2 / 任务 007。

---

## [2026-11-06] 任务 006 返修 - Prompt 1-R1（返修完成，待 Codex 复验）

- **执行者**：DeepSeek（DeepSeek Harness 会话）
- **对应归档**：`docs/prompts/04_agents/2026-11-03_006_agent_first_baseline.md`（§14 记录）
- **返修依据**：`docs/reviews/2026-11-03_task006_review.md` 第 7 节 Prompt 1-R1 原文
- **执行前状态**：分支 `main`，HEAD `7ed2665bb9201568a8d74a12af37bf0a502378f1`，工作区含接手前未提交变更（全部保留）

### 本次完成的功能

- **R1**：C06 拆成"主失败路径 + 恢复 probe"两个子场景，失败路径 `required_evidence_ids=[]`、probe 成功后才要求 3 张 invoice；fixture 增加 `scenario_protocol` 并写死解析优先级（case > variant.scenarios > variant.events，事件替换不合并、未知场景校验失败）。
- **R2**：三基线的**事实/引用/权限/审批**改为同一套共通质量断言；编排约束按 `baseline_mode` 单独判定；`route_class` 降为效率指标；C03/C04/C05/C08 放开三条路由，C04 明确"单 Lease Agent + Verifier 即可"；评测计划新增 A/B/C 对同一假想正确结果的评分示例。
- **R3**：新增物业/财务审批主体、跨项目审批人与只读主体；`approval_role_rules`（`all_of` + 串行 + 两名不同主体 + 禁止自批 + 72h 过期）与 v1/v2 草案；`v_approval_flow` 拆成 6 个可解析场景（拒绝/正确版本批准/同版本重放/无权限/换版/过期）。
- **R4**：契约补 State 唯一写入者、`tool_call_id`/`model_call_id`/`event_id` 稳定 ID、`reserve/settle/release` 原子记账；Evidence 改为按 `content_hash` 幂等合并、不同内容报 `EVIDENCE_CONFLICT`；墙钟改用单调时钟且不与并发节点求和；给出正/逆序到达、重复投递与冲突的具体输入与预期。
- **R5**：补 12 行穷尽转移表（supported/conflicting/insufficient × 补查上限 × 有无草案）；`revise` 只发 `RevisionRequest` 回 `planner`；`awaiting_human_input` 与 `awaiting_approval` 分离且无草案不得审批；`WorkflowResult` 纳入审批状态与拒绝理由；补齐 `Evidence` 数据版本、`ToolResult.evidence`、`Computation`、`WorkflowStatus` 枚举；resume 明确可能重放并给出幂等手段。
- **R6**：保留集（22–42 题）纳入 P0；指标改由 Trace 记录、`agent_runs` 存储方案单独决定；允许预先固定重复次数并冻结配置、禁止看结果调参；K6 改记为未来数据库映射注意事项 N1；更正 006 §8 旧状态与"大小相等"措辞；兼容策略改为单一路径增量迁移。

### 主要技术决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 场景解析 | 显式 `scenario_protocol`，优先级 case > variant.scenarios > variant.events，事件**替换**不合并 | 主失败路径与 probe 复用同一工具不同 `fail_attempts`，靠自然语言假设必然出错 |
| 失败路径证据 | `mode: none` + 空 required | 工具没有成功返回时要求 invoice 证据等于强迫读取隐藏数据 |
| 三基线评分 | 质量断言共用、架构约束分基线、路由只作效率 | 路由是产品选择，不是答案对错；避免"复杂题必须多 Agent"的预设 |
| 审批模型 | `all_of` + 串行 + 两名不同主体 + 72h 过期 + 事件 `event_id` 幂等 | 用最小机制覆盖拒绝/越权/换版/过期/重放，不建复杂审批平台 |
| 归并键 | `(subtask_id, attempt)` + 调用/事件稳定 ID + `content_hash` | 保证重放与到达顺序不影响结果与预算 |
| 兼容策略 | 单一路径增量迁移，一次一个边界 | 不为占位类型预建三套生命周期 |
| 基线验证 | 执行前后逐文件 SHA-256 比对 | 文件大小相等不能证明内容一致 |

### 修改的文件

| 文件 | 变更 |
|---|---|
| `docs/evaluation/fixtures/agent_first_v1.json` | 修改（场景协议、审批主体/规则/草案、C06 与 C08 子场景） |
| `docs/evaluation/cases/smoke_v1.jsonl` | 修改（8 行路由口径、C06 双场景、C08 六场景） |
| `docs/evaluation/evaluation_plan.md` | 修改（解析优先级、三基线分离、保留集入 P0、重复测量、6 项语义检查） |
| `docs/architecture/agent_runtime_contracts.md` | 修改（迁移、证据/工具/计算/状态类型、State 与转移、预算与墙钟、审批状态机、K6→N1） |
| `docs/architecture/agent_architecture.md` | 修改（K1–K6 → K1–K5 + N1 的交叉引用更正） |
| `docs/product/mvp_scope_v2.md` | 修改（Trace、保留集、审批规则、重复测量） |
| `docs/prompts/04_agents/2026-11-03_006_agent_first_baseline.md` | 修改（§1/§4/§5–§9 与新增 §14；§3、§10 原文未改） |
| `docs/README.md` | 修改（006 状态） |
| `docs/development_logs/development_log.md` | 修改（本记录） |
| `docs/checkpoints/git_history.md` | 修改（R1 检查点） |

**未修改**：`backend/` 全部文件（逐文件 SHA-256 一致）、`docs/architecture/database_design.md`（hash 不变）、ADR-005、Review、总路线、历史 Prompt 原文。

### 测试和验证结果

命令：`D:\anacada\envs\commercial-agent\python.exe -B -X utf8`（Python 3.11.18，仅标准库）。

| 验证项 | 方式 | 结果 |
|---|---|---|
| JSON/JSONL 解析 | `json.loads` | ✅ fixture 可解析；JSONL 8 行、case_id 唯一有序 |
| 变体与场景 | 对照 `variant_registry` | ✅ 8 case 变体齐全；C06 2 场景、C08 6 场景全部可解析 |
| 证据 ID | 应用 overlay 后重建 ID 索引 | ✅ 顶层与场景级 required 全部命中；负例语义正确 |
| Decimal 金额 | 逐项与汇总复核 | ✅ 账单 `17280/17280/18036`；有效付款 `34560`；未收 `18036`；超额 `756.00`；更正后未收 `17280` |
| S1 失败 C06 不强制证据 | 读取场景 | ✅ `required_evidence_ids=[]`、`evidence_policy=none` |
| S2 probe 成功才要求证据 | 读取场景 + 尝试模拟 | ✅ `fail_attempts=1 < 2`，第 2 次成功，成功后要求 3 张 invoice |
| S3 同一答案通过 A/B/C | 评测计划 §3.4 假想结果 | ✅ 三基线共同质量项全通过，仅效率不同 |
| S4 审批只认可信授权事件 | 6 场景状态机模拟 | ✅ 仅 granted/replay 达到 approved；越权/换版/过期被拒 |
| S5 重放不重复计账、顺序无关 | 归并/账本参考算法 | ✅ 正逆序 map 与 seen 一致；重复事件预算增量 0 |
| S6 verify 组合均有出口 | 3×2×2 枚举 + 契约 12 行表 | ✅ 12 组全部有明确去向 |
| Markdown 链接 | `docs/**/*.md` 相对链接解析 | ✅ 0 断链 |
| 编码 | UTF-8 解码检查 | ✅ 0 处替换字符（U+FFFD） |
| `git diff --check` | — | ⚠️ 唯一告警仍是 `database_design.md:1661` 任务 005 遗留，本轮未改该文件 |
| 文件级 hash 比对 | 执行前后 93 个文件 SHA-256 | ✅ 0 新增/0 删除；10 个文件内容变化（均为本任务授权范围），其余 83 个逐字节不变 |
| `backend/` 与数据库设计 | 逐文件 SHA-256 | ✅ `backend/` 全部一致；`database_design.md` `1b7e3735…6db7` 未变 |

程序化检查合计 **PASS=178 / FAIL=0**。

**未执行**：模型调用、Runtime 运行、数据库连接；不产出成功率/成本/延迟指标。

### 当前项目状态

Task 006 返修完成，**待 Codex 复验**；Prompt 2 / 任务 007 尚未开始；无提交、无推送。

### 下一步开发计划

- [ ] Codex 复验 R1–R6 与本次语义检查，更新路线状态。
- [ ] 通过后再发送 Prompt 2 / 任务 007（Runtime 与受控 Tool Calling）。

---

## [2026-11-04] 任务 006 派生交付 - Notability 路线图文 PDF

- **执行者**：Codex；本次为总路线格式导出，不推进开发任务验收。
- **原始请求**：已追加至 006 归档第 13 节。
- **源文档**：`docs/product/PROJECT_DEVELOPMENT_ROADMAP.md`。
- **产物**：`output/pdf/commercial_property_agent_first_roadmap_notability.pdf`（16 页 A4 竖版，约 414 KB）。
- **内容**：项目架构、协作流程、10 步可点击路线、逐步验收、手写留白、进度表与最终完成清单。
- **核验**：ReportLab 生成，Poppler 全页渲染，联系表和重点页视觉检查；pypdf 验证页数、书签和文本。使用 Codex 附带依赖，未修改项目环境。
- **状态口径**：2026-11-04 导出、2026-11-03 路线快照；006 仍待修正，不把导出当作新验收。未提交 Git。

---

## [2026-11-03] 任务 006 - Codex 首轮验收与总开发路线

- **执行者**：Codex（验收与规划，不实施 Runtime）
- **对应归档**：`docs/prompts/04_agents/2026-11-03_006_agent_first_baseline.md`
- **验收结论**：待修正 R1–R6；完整报告 `docs/reviews/2026-11-03_task006_review.md`。

### 实际完成

- 审阅 DeepSeek 的 ADR、MVP、Runtime 规格、评测计划、JSON fixture 与 8 道用例。
- 独立解析 JSON/JSONL、应用变体、校验来源 ID、Decimal 金额与文档相对路径；现有骨架自检 57 项通过。
- 核实基线应收 `52596.00`、有效付款 `34560.00`、未收 `18036.00`、10 月差异 `756.00`；更正后未收 `17280.00`。
- 发现超时证据要求、基线路由偏置、审批授权、重放预算/证据归并、Graph 契约闭合、P0/记录口径 6 组问题；准备 Prompt 1-R1。
- 按用户要求新增 `docs/product/PROJECT_DEVELOPMENT_ROADMAP.md`：10 次正式 Prompt（含已发送的第 1 次）；当前计一次必要返修后预计实际 11 次，后续若继续返修则额外计数。

### 修改与边界

- 新增 Review 与总路线；更新 006 归档、Docs 索引、本日志、Issue 和 Git 检查点。
- 不修改 backend、原数据库设计、DeepSeek 的 fixture/规格交付或历史 Prompt 原文；无安装、模型调用、建库、提交或推送。
- DeepSeek 执行前未有 Codex 持有的完整 hash 快照；不宣称已独立证明所有旧未跟踪源码字节未变。

### 当前状态与下一步

任务 006 处于待修正；DeepSeek 按 Review 第 7 节返修后由 Codex 复验。007 尚未开始，Commit `Pending`。

---

## [2026-11-03] 任务 006 - Prompt 1 准备（待执行、待验收）

- **开发阶段**：Agent-first 基线准备
- **执行者**：Codex（仅提示词准备）
- **对应 Prompt 归档**：`docs/prompts/04_agents/2026-11-03_006_agent_first_baseline.md`
- **协作流程**：Codex 编写 Prompt → DeepSeek 执行 → Codex 审查 → 通过后下一项。

### 本次完成的功能

- 已编写 Prompt 1 / 全局任务 006：方向 ADR、MVP 范围、Runtime 契约规格、8 个合成评测样例及验收要求。
- 归档用户原文并登记编号；执行 Prompt 保存在归档第 10 节。
- DeepSeek 尚未执行，不能把预期文档、样例或 Runtime 标记为已实现。

### 主要技术决策

- 先交付可编码、可验收的基线和固定事实，不以完成旧 14 表财务引擎为 Runtime 开发前提。
- 本任务执行范围限 Markdown 和 docs/evaluation/ 的 JSON/JSONL；不改 backend/，不安装依赖、建库或提交。

### 修改的文件

- 新增 006 Prompt 归档；更新 Docs 编号表、本日志和 Git 检查点。

### 测试和验证结果

- 准备前核实 `main` / `7ed2665bb9201568a8d74a12af37bf0a502378f1`，工作区有既有未提交变更。
- 本阶段未执行模型评测；DeepSeek 交付及 Codex 验收结果待追加。

### 当前项目状态

Prompt 1 已准备；任务 006 待 DeepSeek 执行、待 Codex 验收。Commit 为 `Pending`。

### 下一步开发计划

- [ ] DeepSeek 执行任务 006。
- [ ] Codex 审查文件、数据一致性及实际验证结果，问题修正后再进入任务 007。

---

## [2026-11-06] 任务 009 - LangGraph 多 Agent 工作流与条件路由

- **日期**：2026-11-06
- **开发阶段**：阶段 1' - 多 Agent 图编排
- **对应 Prompt 归档**：`docs/prompts/04_agents/2026-11-06_009_langgraph_multi_agent_workflow.md`（正式 Prompt 4）
- **状态**：**DeepSeek 自检通过**

### 本次完成的功能

- `LeaseAgent` / `BillingAgent` 由骨架改为工具驱动实现；新增 `PropertyAgent`（工单事实）。
- 新增 LangGraph 调查图：条件路由（简单问题不扇出）、`Send` 并发扇出、合流、限次补查、确定性核验。
- 新增 `completeness` 维度，把"证据是否矛盾"与"调查是否跑全"分开表达。
- Trace 增加 `subtask_id`，并发子任务可归因；`factory` 支持依赖注入且按签名过滤。
- CLI 新增 `investigate`（默认跑 C03 争议调查场景）。
- 新增 17 项图测试，覆盖路由、并发、冲突、缺失、越权、能力禁用、补查有界。

### 主要技术决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 规划器 | 确定性规则（关键词 + 复杂度判定） | 无模型凭据也能复现；"简单问题不拆多 Agent"必须可被程序断言 |
| 补查条件 | 仅"子任务失败"才补查 | 文档缺失重跑也拿不到，纯浪费预算 |
| 结果归并 | 按 `subtask_id` 取最后一次 | 补查重跑不重复计数 |
| 冲突 vs 完整性 | `verdict` + `completeness` 双字段 | 单一 verdict 会丢掉另一半信息 |
| 依赖注入 | 按构造函数签名过滤 | Agent 只声明自己需要的依赖，图不被迫了解实现 |

### 修改的文件

| 文件 | 变更 |
|---|---|
| `backend/app/orchestration/investigation.py` | 新增（图/规划器/核验器/门面） |
| `backend/app/agents/base/tool_backed.py`、`agents/property/*`、`config/agents/property.yaml` | 新增 |
| `backend/app/investigation_demo.py` | 新增 |
| `backend/app/agents/{lease,billing}/agent.py` | 重写为工具驱动 |
| `backend/app/agents/base/contracts.py`、`runtime/types.py`、`tools/executor.py` | `subtask_id` 维度 |
| `backend/app/agents/factory.py`、`cli.py`、`pyproject.toml` | 注入、`investigate`、依赖 |
| `backend/tests/test_graph_workflow.py` | 新增（17 项） |
| `backend/tests/{smoke_agent_contracts,test_runtime}.py` | 断言同步 |

### 测试和验证结果

| 验证项 | 结果 |
|---|---|
| 骨架自检 | ✅ 57 项 |
| 单元测试 | ✅ `Ran 94 tests ... OK` |
| CLI（6 条命令） | ✅ 全部退出码 0 |
| C03 图执行 | ✅ 3 子任务并发、`conflicting`、差额 756.00、缺失 annex_b、Trace 按 subtask 归因 |

### 当前项目状态

多 Agent 图可运行且可解释：简单问题走确定性路径，复杂问题并发扇出并核验。尚无数据库、RAG、审批与持久 checkpoint、评测 runner 与 API。

### 下一步开发计划

- [ ] Task 010：PostgreSQL 只读工具与数据访问边界
- [ ] Task 012：持久 checkpoint 与审批暂停/恢复

---

## [2026-11-06] 任务 008 - LangChain、DeepSeek 适配与真实工具调用闭环

- **日期**：2026-11-06
- **开发阶段**：阶段 1' - 模型接入与单 Agent 基线
- **对应 Prompt 归档**：`docs/prompts/04_agents/2026-11-06_008_langchain_deepseek_tool_calling.md`（正式 Prompt 3）
- **状态**：**DeepSeek 自检通过**（离线闭环已验证；真实 DeepSeek 调用受凭据限制，未验证）

### 本次完成的功能

- 新增厂商无关模型客户端层：`ChatMessage` / `ToolSpec` / `ModelTurn` / `ChatModelClient`，含 `FakeChatModelClient`。
- 新增 LangChain ↔ DeepSeek（OpenAI 兼容）适配器，复用既有参数裁剪与密钥来源，`max_retries=0` 关闭隐式重试。
- 新增有限轮次工具调用循环：轮次上限、模型/工具/token 预算、deadline 三重约束，停止原因可见。
- 新增单 Agent + Tools 基线（`single.investigate`）与独立 YAML（`max_tool_rounds=3`）。
- CLI 新增 `ask` 子命令（默认 fake 离线，`--provider deepseek` 走真实调用）。
- 新增 24 项测试，覆盖工具清单裁剪、结果回传、非法参数、越权、轮次上限、预算耗尽、模型异常、用量累加、密钥缺失。

### 主要技术决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 模型抽象 | 自有窄接口 `ChatModelClient`，而非直接暴露 LangChain 类型 | Agent/图不依赖 LangChain 具体类，替换 Provider 不影响业务代码 |
| 隐式重试 | `max_retries=0` | 重试归属只能有一层（工具层），否则多层相乘放大成本 |
| 非法工具参数 | 作为工具调用结果回传给模型，不抛异常 | 模型可自我纠正；抛异常会让整轮失败 |
| 工具可见范围 | `allowed_tools ∩ 实现存在 ∩ 调用方权限` | 模型根本看不到越权工具，越权在第一道闸就被挡住 |
| Trace 共享 | Agent 注入与 Runtime 同一个 `TraceLog` | 否则出现"调用了工具但 `tool_traces` 为空"的假象 |

### 修改的文件

| 文件 | 变更 |
|---|---|
| `backend/app/llm/model_client.py` / `langchain_client.py` | 新增 |
| `backend/app/runtime/tool_loop.py` | 新增 |
| `backend/app/agents/single/{agent.py,__init__.py,prompts/system.md}` | 新增 |
| `backend/app/single_demo.py` | 新增 |
| `backend/app/config/agents/single.yaml` | 新增 |
| `backend/app/config/schema.py` | 新增 `max_tool_rounds` |
| `backend/app/agents/factory.py` | 注册 `single` |
| `backend/app/cli.py` | 新增 `ask` |
| `backend/pyproject.toml` / `backend/README.md` | 依赖与文档 |
| `backend/tests/test_llm_tool_loop.py` | 新增（24 项） |
| `backend/tests/smoke_agent_contracts.py` | Agent 数量断言 3 → 4（仍 57 项） |

### 测试和验证结果

| 验证项 | 命令 | 结果 |
|---|---|---|
| 骨架自检 | `python tests/smoke_agent_contracts.py` | ✅ 57 项，退出码 0 |
| 单元测试 | `python -m unittest discover -s tests` | ✅ `Ran 76 tests ... OK` |
| 单 Agent 闭环 | `python -m app.cli ask "A-301 现在还有多少钱没交？"` | ✅ success / final_answer / 2 轮 / 1 次工具 / 13 条证据 / 1 条 Trace |
| 缺密钥 | `... --provider deepseek` | ✅ 退出码 2 + `MissingApiKeyError`，未伪造成功 |
| 回归 | `python -m app.cli demo` | ✅ 未收 `18036.00` 不变 |

### 当前项目状态

单 Agent 可以真正"选择工具 → 受控执行 → 读取结果 → 作答"（离线 Fake 已验证）。尚无 LangGraph 图、数据库、RAG、审批与评测 runner。

### 下一步开发计划

- [ ] Task 009：LangGraph 多 Agent 图与条件路由（含子任务 `run_id`/Trace 维度复核）
- [ ] 真实 DeepSeek 调用需 `DEEPSEEK_API_KEY` 与预算确认

---

## [2026-11-06] Task 007 独立自检（DeepSeek）— 通过

- **任务**：007（正式 Prompt 2）Runtime 与受控工具执行
- **状态**：**DeepSeek 自检通过**（未经 Codex 验收；项目已取消 Codex 逐任务复核）
- **自检报告**：`docs/reviews/2026-11-06_task007_deepseek_selfcheck.md`

### 本次完成的功能

- 独立核对 Task 007 R1 的实际代码与测试，不依赖既有报告。
- **发现并修复 R1 的 F1 遗留缺陷**：`statement()` 的 `paid_total` 仍按整笔付款金额累计，一笔付款拆分核销到同项目不同租约时，他租约部分会被算进本租约已收（复现：`35060.00` / 应 `34760.00`）。
- 新增跨租约拆分付款回归测试，同时断言两个租约各自的已收与未收。
- 独立验证 F2：连续两次与并发两次运行各 3 条 Trace，`call_id` 不相交，共享 append-only 日志保留并集。

### 主要技术决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 已收额口径 | `Σ(核销到本租约的 allocation.amount)` | 付款是资金实体，跨租约拆分时整笔金额不都属于本租约 |
| 未收额口径 | 逐账单 `outstanding` 求合 | 与账单级余额定义保持一致，避免总额与明细口径分叉 |
| 付款列表 | 仍返回参与核销的完整付款记录 | 保留可追溯性；金额口径与记录展示分开 |

### 修改的文件

| 文件 | 变更 |
|---|---|
| `backend/app/fixtures/repository.py` | 已收/未收按本租约核销金额计算 |
| `backend/tests/test_runtime.py` | 新增拆分付款回归测试（1 项） |
| `docs/reviews/2026-11-06_task007_deepseek_selfcheck.md` | 新增自检报告 |
| `docs/prompts/04_agents/2026-11-06_007_agent_runtime_controlled_tools.md` | 状态更新 + §17 自检记录 |
| `docs/product/PROJECT_DEVELOPMENT_ROADMAP.md` | 进度表与流程说明更新 |
| `docs/development_logs/development_log.md` | 本条 |
| `docs/checkpoints/git_history.md` | 检查点记录 |

### 测试和验证结果

| 验证项 | 命令 | 结果 |
|---|---|---|
| 既有骨架自检 | `python tests/smoke_agent_contracts.py` | ✅ 57 项通过，退出码 0 |
| 单元测试 | `python -m unittest discover -s tests` | ✅ `Ran 52 tests ... OK` |
| CLI | `--help` / `tools` / `check` / `demo` / `demo --variant` | ✅ 全部退出码 0；未收 `18036.00` / `17280.00` |
| 预算耗尽 | `demo --budget-tool-calls 1` | ✅ 退出码 2、`budget_exhausted`、`tool_trace_count=2` |
| 租约隔离（独立脚本） | 13 项断言 | ✅ 修复后 `PASS=13 FAIL=0`（修复前 11/2） |
| Trace 隔离（独立脚本） | 12 项断言 | ✅ `PASS=12 FAIL=0` |

### 当前项目状态

离线 Runtime、受控 Tool Executor、4 个只读 fixture 工具、CLI 均可用且有回归覆盖。尚无真实模型、LangGraph、数据库、RAG、审批与评测 runner。

### 下一步开发计划

- [ ] Task 008：LangChain + DeepSeek 适配与真实 Tool Calling 闭环（`DEEPSEEK_API_KEY` 未设置，真实调用预计受凭据限制）
- [ ] Task 009 起：LangGraph 多 Agent 图（需复核子任务 run_id / Trace 维度）

---

## [2026-11-03] 任务 006 - Agent-first 基线、契约与首批评测样例

- **日期**：2026-11-03
- **开发阶段**：阶段 0' - 方向重定与规格化（Agent-first）
- **对应 Prompt 归档**：`docs/prompts/04_agents/2026-11-03_006_agent_first_baseline.md`（用户侧称 Prompt 1）
- **状态**：执行完成，**待 Codex 审查**（未验收）

### 本次完成的功能

- 记录方向调整决策 ADR-005，明确区分「用户已确认 C1–C7」与「本 ADR 建议 S1–S10」，并确立"与历史文档冲突时以新基线为准"。
- 定义 P0 范围、唯一主演示场景（A-301 争议调查）、P0 九项覆盖项的**可验证完成标准映射表**，以及 P1 与暂停清单。
- 编写编码级运行时契约（12 项）：契约兼容三阶段、证据/结论结构、金额与时间语义、权限与租户拆分、Tool Executor、Model Adapter、Registry/GraphBuilder、State 与图语义、预算与重试归属、四类 ID 与恢复、审批节点。
- 建立合成评测数据：2 个项目、3 商户、3 租约、4 条计费规则、3 张账单、3 笔收款、4 条工单、4 份文档 + 4 段片段，金额自洽。
- 产出 8 条评测用例 C01–C08，覆盖确定性查询、单 Agent 检索、完整争议调查、冲突证据、缺失资料、工具超时、越权访问、减免审批四条分支。
- 固件内置 5 个变体（含 1 个数据回归变体、1 个故障注入、1 个审批流含 3 个子变体），并规定 overlay → events 的解析顺序。
- 通过源码核对复现 4 项已知骨架问题，并额外发现 2 项，形成任务 007 修复清单 K1–K6。
- 同步修正 `system_design.md` 与现状矛盾的表述（Pydantic 实际已引入、已有骨架代码），并链接 ADR-005。

### 主要技术决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 契约升级方式 | 三阶段（新增可空字段 → 超集类型 → 收敛），不做一次性破坏 | 现有 3 个 Agent + 57 项自检依赖旧结构 |
| 金额表示 | `{"amount": "15120.00", "currency": "CNY"}` 十进制字符串 | JSON 浮点在解析阶段即失真；`Decimal` 才有真值 |
| 引用验证 | 拆成 L1「引用存在」与 L2「引用支持结论」两级 | 只做 L1 会出现"页码对但话说的是别的意思"的伪引用 |
| State 归并 | 键为 `(subtask_id, attempt)`，禁止裸列表追加 | 重放会把一次执行记成两条，污染预算与补查轮次 |
| 补查上限 | `max_revisions = 1` | 防止验证器无限自我循环 |
| 预算归属 | 只有工具层重试（上限 2），Runtime/节点/模型不重试 | 多层重试会相乘放大成本 |
| 审批 | 独立 Graph 节点 + 绑定 `draft_version` | 草案一改，旧审批自动失效；避免"批准的是 A、执行的是 B" |
| 文档 page 语义 | 明确为"约定的测试来源定位"，不声称 PDF 已校验 | 未实现真实 RAG 前不得虚假声明 |
| 评测顺序 | 先 8 题开发样例，保留测试集后置并隔离 | 8 题可见，直接当结论会过拟合 |
| 数据库 | P0 表数待评审反推，不锁定 10/14 表 | 避免把待定方案写成既成事实 |

### 修改的文件

| 文件 | 变更 |
|---|---|
| `docs/decisions/ADR-005-agent-first-refocus.md` | 新增 |
| `docs/product/mvp_scope_v2.md` | 新增 |
| `docs/architecture/agent_runtime_contracts.md` | 新增 |
| `docs/architecture/agent_architecture.md` | 修改（增量说明与链接） |
| `docs/architecture/system_design.md` | 修改（修正矛盾表述 + 链接 ADR-005） |
| `docs/evaluation/evaluation_plan.md` | 新增 |
| `docs/evaluation/fixtures/agent_first_v1.json` | 新增 |
| `docs/evaluation/cases/smoke_v1.jsonl` | 新增 |
| `docs/README.md` | 修改（目录索引 + 006 状态） |
| `docs/prompts/04_agents/2026-11-03_006_agent_first_baseline.md` | 修改（追加执行阶段与验证结果，未改写 §3/§10） |
| `docs/development_logs/development_log.md` | 修改（本条） |
| `docs/checkpoints/git_history.md` | 修改（Pending 检查点） |

**未修改**：`backend/` 任何文件、`docs/architecture/database_design.md`、历史 Prompt 原文。

### 测试和验证结果

| 验证项 | 结果 |
|---|---|
| fixture JSON 可解析 | ✅ 44 个基线实体，`synthetic=true` |
| JSONL 行数 / case_id | ✅ 恰好 8 行，C01–C08 唯一有序 |
| 变体与证据 ID 存在性 | ✅ 8/8 变体已注册；required 全命中；负例语义正确 |
| Decimal 金额核对 | ✅ 账单 17280/17280/18036；有效核销 17280/17280/0；未收合计 18036.00 |
| 冲销排除对照 | ✅ 若计入冲销分配，08 月将超额，证明断言有效 |
| 合同递增自洽 | ✅ 120→126.00→132.30；超额 756.00 |
| 数据变体（overlay） | ✅ 更正后 10 月合计 17280.00，且基线未被就地修改 |
| Markdown 相对链接 | ✅ 21 文件 / 55 链接，新增文档 0 断链 |
| `backend/` 一致性 | ✅ 与本任务开始前一致 |
| `git diff --check` | ⚠️ 仅 1 条**任务 005 遗留**告警（`database_design.md` EOF 空行），本轮不改该文件，未处理 |
| 程序化断言总数 | ✅ **164 项全部通过** |

**未执行**：模型调用、Runtime 运行、数据库连接 → 因此不产出成功率/成本/延迟数值。

### 当前项目状态

方向与规格已就绪：可编码的契约、可机器读取的数据与 8 条用例已具备。**Runtime、真实 Tool、Service/Repository、图实现、评测 runner、三基线均未开始。** 代码侧仍只有阶段 0 骨架（`backend/` 未变）。

### 下一步开发计划

- [ ] Codex 审查本次交付（实际文件 + 数据一致性），给出通过/待修正结论
- [ ] 任务 007：Agent Runtime 与受控 Tool Calling，并修复 K1–K5
- [ ] 任务 007 起接入 fixture loader 与 Deterministic 基线
- [ ] 后续补 22–42 题保留测试集并做隔离

---

## [2026-11-03] 任务 005 - 数据库设计复核与 MVP 决策补充

- **日期**：2026-11-03
- **开发阶段**：阶段 2 - 数据层设计复核
- **对应 Prompt 归档**：`docs/prompts/02_database/2026-11-03_005_database_design_review.md`
- **说明**：用户称其为「Task 003 Review」，项目内部编号顺延为 005（对任务 004 的复核修订）

### 本次完成的功能

- 精确盘点约束与索引：发现 §8.2 实为 **18 条**唯一约束（文档原写 17，因一行含两条）。
- 技术复核发现 **12 项缺陷**，其中 **2 项严重**：
  - **D1**：`occupied_to` 允许 NULL 且被 `COALESCE('infinity')`，会**永久锁死商铺**。
  - **D4**：`blocks_occupancy` 缺初始化触发器，先建活跃租约再插占用行时**约束完全不生效**。
- 落地三项业务决策 DEC-001~003（押金不入应收 / 不做表计 / 待签不占位），并同步修改枚举与触发条件。
- 给出 `lease_units` 排他约束的**完整可执行 DDL**：生成列 + 两个触发器 + 11 个场景逐条验证 + Alembic 注意项。
- 给出收款核销的**并发一致性方案**：`FOR UPDATE` 行锁 + 固定加锁顺序 + `ON CONFLICT` 累加，附 5 种被否决方案理由、6 个错误码、10 个测试用例。
- 补齐免租期与阶梯租金的**确定性金额算法**（逐月舍入、免租显式归零、`period_unit` 收窄建议）。
- 清理冗余：删除 3 条唯一约束 + 3 个索引，附"约束已自动建索引"完整盘点表。
- 剩余 5 项待确认问题逐条给出建议默认方案（均不阻塞建表）。
- 同步更新 ER 图与 `v_invoice_outstanding` 视图（补 `reversed_at IS NULL`）。

### 主要技术决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 排他约束如何表达区间 | `GENERATED ALWAYS AS (daterange(...)) STORED` 生成列 | 表达式索引在约束场景行为不确定；生成列是普通列，`\d` 输出与报错更可读，且区间转换只写一处 |
| 区间端点 | 一律 `NOT NULL`，由触发器物化 | 用 NULL 表示开放区间会被约束解释为无限期，语义与实现直接冲突（D1） |
| 合同时间 vs 占用时间 | 双触发器强制"占用区间恒等于租期" | 让不一致**无法表达**，而不是事后校验（D3/D4 的正解） |
| 待签是否占位 | 不占位，仅 `active` | 待签作废率高，占位会让商铺被僵尸合同锁死；代价是重复签约后一单失败 |
| 核销并发 | `SELECT ... FOR UPDATE` + 固定加锁顺序 | `CHECK`/`EXCLUDE` 无法表达跨行聚合；行锁消除 check-then-write 窗口，排序加锁避免死锁 |
| 核销冲销 | 新增 `reversed_at`，唯一索引改部分索引 | 否则冲销后要么丢审计、要么余额算错（D5） |
| 冗余索引 | 删除 3 条约束 + 3 个索引 | 被蕴含或被其他索引覆盖，纯写放大且制造"已覆盖"错觉 |

### 修改的文件

| 文件 | 变更 |
|---|---|
| `docs/architecture/database_design.md` | v1 → v2（46,000 → 65,839 字符）；新增 §14 决策、§15 复核；重写 §6.3/6.6/6.7/6.9/6.11/6.13/8.x/9.1/13；ER 图与视图同步 |
| `docs/prompts/02_database/2026-11-03_005_database_design_review.md` | 新增 |
| `docs/README.md` | 编号登记表补 005 |
| `docs/checkpoints/git_history.md` | 新增阶段 2 复核记录 |
| `docs/lessons_learned/knowledge_notes.md` | 新增 1 篇 |

**未创建**：`.sql`、SQLAlchemy 模型、Alembic 迁移。**未安装 PostgreSQL。**

### 测试和验证结果

| 验证项 | 结果 |
|---|---|
| 唯一约束计数纠错 | ✅ 18 → 15（删除 3 条冗余） |
| 索引重复检测 | ✅ 18 条（v1 21 条，删 3 条完全重复/被覆盖） |
| Mermaid 结构 | ✅ 14 实体 / 14 闭合 / 属性行 0 处非法 |
| 代码围栏 | ✅ 54 个，偶数闭合 |
| 章节编号 | ✅ 1–16 连续 |
| 视图一致性 | ✅ 已补 `reversed_at IS NULL` |
| 未建库 / 未迁移 / 未提交 | ✅ 确认 |

### 当前项目状态

数据库设计 v2 完成，待评审。14 张表结论不变。项目仍无任何 SQLAlchemy 模型、迁移脚本或数据库连接代码。

### 下一步开发计划

- [ ] 评审 §13.3 剩余 5 项（均有默认方案，不阻塞建表）
- [ ] 评审通过后提交
- [ ] 建库后先验证 §15.2.3 的 11 个约束场景，再写上层代码
- [ ] 按 §15.3.5 编写核销测试（含 2 个并发用例）

---

## [2026-11-03] 任务 004 - PostgreSQL 数据库架构设计

- **日期**：2026-11-03
- **开发阶段**：阶段 2 - 数据层设计
- **对应 Prompt 归档**：`docs/prompts/02_database/2026-11-03_004_postgresql_database_design.md`
- **说明**：用户本条 Prompt 自标为「Task 003」，因项目内部编号已用至 003，归档顺延为 004

### 本次完成的功能

- 评估初始 13 张表方案：确认**无删除、无合并**，判定需新增 `lease_units`，最终 **14 张表**。
- 识别并处理 9 项设计缺口（排他约束、约束跨表限制、明细追溯链、文档版本、隔离键、Agent 调用树、软删除唯一约束、公共区域工单等）。
- 补齐 14 张表的完整字段定义（类型 / Nullable / 默认值 / 说明）与全部状态机。
- 建立 2 条排他约束（租期不重叠、计费规则不重叠）与 17 条唯一约束、21 条索引。
- 定义出账（租金计算）与核销（收款分配）两条数据流的完整步骤与幂等/校验要求。
- 定义 Agent → Tool → Service → Repository → Model 的四层数据访问边界与 5 条硬规则。
- 给出 `v_invoice_outstanding` 视图定义（含"双明细表 JOIN 会翻倍"的陷阱说明）。
- 原骨架中的 6 项待决策问题全部给出结论；新增 8 项待业务确认问题。
- 补充「未来扩展建议」与「已知限制」各 1 节。

### 主要技术决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 多商铺租约扩展 | 新增 `lease_units`，MVP 用 `UNIQUE(lease_id)` 限制一租约一商铺 | 若把 `unit_id` 放 `leases`，未来放开需破坏性迁移 + 全量查询改写；用关联表则只需 `DROP INDEX` |
| 租期冲突 | `EXCLUDE USING gist` 排他约束 | 应用层校验在并发下失效；这是数据库唯一能真正保证的机制 |
| 排他约束排除草稿 | `lease_units.blocks_occupancy` 本地列 + 触发器 | PG 排他约束的谓词不能引用其他表，只能物化 |
| 阶梯租金 | 物化多条 `effective_from/to` 规则 | 存递增率的话，规则中途变更后历史账单无法复现 |
| 账单总额 | 不落库，由明细 `SUM` 派生 | 满足"不存可算出的数据"，避免双写不一致 |
| 行级金额 | 存储 `invoice_items.amount` | 唯一"看似冗余"的存储：行级四舍五入后乘法无法还原，属财务凭证性质 |
| 枚举 | `TEXT + CHECK`，不用 PG 原生 `ENUM` | 原生 enum 删改值需重建类型，早期状态机变动频繁 |
| 项目隔离 | 叶子表冗余 `project_id` + 复合外键强制一致 | RLS 策略无法做 4 层 JOIN；复合外键让冗余不可能不一致 |
| 文档版本 | 不可变行 + `supersedes_id` 链，无 `updated_at` | 版本链本身即审计证据，无需额外历史表 |
| Agent 输出落库 | `agent_runs` 用 `jsonb` | 为每个 Agent 建结构化列会导致频繁改表 |

### 修改的文件

| 文件 | 变更 |
|---|---|
| `docs/architecture/database_design.md` | 骨架 → 完整设计（约 46000 字符），保留原原则与变更历史 |
| `docs/prompts/02_database/2026-11-03_004_postgresql_database_design.md` | 新增 |
| `docs/prompts/02_database/.gitkeep` | 删除（目录已有实际文件） |
| `docs/README.md` | 编号登记表补 004 |
| `docs/checkpoints/git_history.md` | 新增阶段 2 待提交记录 |
| `docs/lessons_learned/knowledge_notes.md` | 新增 2 篇数据库建模笔记 |
| `docs/architecture/system_design.md` | 待定问题 #9 标记已决策 |
| `docs/architecture/agent_development_guide.md` | 新增「数据访问规则」章节 |

**未创建**：`.sql` 文件、SQLAlchemy 模型、Alembic 迁移、数据库连接配置。**未安装 PostgreSQL。**

### 测试和验证结果

| 验证项 | 方式 | 结果 |
|---|---|---|
| 章节完整 | 提取 `^## ` 标题 | 14 个章节，覆盖用户要求全部 10 项内容 |
| 逐表字段设计 | 提取 `^### 6\.\d+` | 6.1~6.14 共 14 张表，每表五列字段说明 |
| Mermaid ER | 结构校验 | 14 实体块 / 14 闭合括号 / 25 条关系，属性行 0 处非法 |
| 代码围栏 | 统计围栏行数 | 40（偶数，闭合） |
| 约束与索引汇总 | 第 8 章 | 17 唯一 / 2 排他 / 21 索引，均注明所服务查询 |
| 状态机 | 第 9 章 | 租约 / 账单 / 收款 / 工单 / Agent 运行 5 组全部定义 |
| 业务日期 vs 系统时间 | 2.1 + 字段类型 | `date` 用于业务日历，`timestamptz` 用于事件时刻 |
| 未建真实表 / 未安装 PG | 未执行任何安装或连接命令 | 确认 |
| 未提交 Git | 未执行 `git add` / `commit` | 确认 |

### 当前项目状态

数据库设计完成，待评审。项目仍无任何 SQLAlchemy 模型、迁移脚本或数据库连接代码。基础设施（Conda 环境、Agent 架构骨架、文档体系）已就绪，Agent 业务逻辑仍为空实现。

### 下一步开发计划

- [ ] 评审 `database_design.md` 第 13.2 节 8 项待确认问题
- [ ] 评审通过后提交（建议与任务 003 改动分开提交）
- [ ] 安装 PostgreSQL，创建 UTF8 数据库，执行 `CREATE EXTENSION btree_gist`
- [ ] 编写 SQLAlchemy 2.0 模型与 Alembic 初始迁移（手动补 `EXCLUDE` / 部分唯一索引 / 复合外键）
- [ ] 创建 `v_invoice_outstanding` 视图与两个触发器
- [ ] 建立 Repository / Service / DTO 骨架

---

## [2026-11-03] 任务 003 - 模块化多 Agent 架构约束

- **日期**：2026-11-03
- **开发阶段**：阶段 0 - 架构约束与骨架
- **对应 Prompt 归档**：`docs/prompts/04_agents/2026-11-03_003_modular_multi_agent_architecture.md`

### 本次完成的功能

- 确立 **Modular Monolith + Agent Registry + LangGraph Orchestration + Configuration-Driven Design** 四层架构并写入强制约束。
- 实现统一 Agent 契约：`AgentProtocol`、`BaseAgent`、`AgentRequest` / `AgentContext` / `AgentResult` / `AgentDescriptor` / `AgentOutput`（全部 Pydantic，`frozen` + `extra=forbid`）。
- 实现 `AgentRegistry`：注册、按能力发现、启用状态判定、拒绝重名/能力冲突/接口不兼容。
- 实现静态白名单工厂 `AGENT_IMPLEMENTATIONS`，杜绝配置字符串触发的任意导入。
- 实现 Agent 配置 Schema 与加载器：7 类非法配置被拒，敏感字段（`api_key`/`password`/`token` 等）结构性拒绝。
- 实现模型适配层：参数裁剪（`temperature` 为 `null` 时不下发）、provider 白名单、密钥仅从环境变量读取。
- 实现工具契约与双重授权：`allowed_tools` 白名单 + `context.permissions` 业务权限。
- 定义 LangGraph 共享 State 与合并策略（追加式 reducer / 单点写入），**不导入 langgraph**。
- 实现编排契约：`CoordinatorPolicy` 三级降级策略、`check_plan_feasibility()` 区分 available / disabled / missing、`summarize_results()` 保留部分成功语义。
- 建立 3 个 Agent 骨架（lease / billing / compliance）与独立 YAML 配置、独立 Prompt，覆盖「启用」「temperature 为 null」「禁用」三种状态。
- 编写 57 项自检脚本并全部通过。
- 新增架构文档与 Agent 开发指南。

### 主要技术决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 架构形态 | Modular Monolith | 单人/小团队，Agent 间高频共享上下文；用接口边界而非网络边界保证解耦，未来可沿边界抽服务 |
| Agent 返回值 | 子类只返回 `AgentOutput`，`AgentResult` 由基类构造 | 元数据（延迟/模型/trace/重试次数）在所有 Agent 上天然一致，避免遗漏可观测性 |
| 能力命名 | `<domain>.<action>` 字符串，**不设全局枚举** | 全局枚举会让新增 Agent 必须改公共文件，违背「新增不修改已有文件」 |
| 配置→实例映射 | `factory.py` 内静态字典白名单 | 从结构上消除 `importlib` 任意导入风险；配置被篡改也只能命中已登记实现 |
| 敏感字段防护 | Schema `extra="forbid"` + 显式拒绝键名 + 运行时读环境变量 | 三层防线，且报错信息引导改用 `api_key_env` |
| 能力冲突策略 | 宁可启动失败 | 两个 Agent 声明同一能力会破坏「按能力选 Agent」的确定性 |
| 禁用 vs 缺失 | `AgentDisabledError` 与 `CapabilityUnavailableError` 分开 | 便于上层给出明确原因并选择降级或转人工，而不是笼统报「能力不存在」 |
| State 字段 | 并发字段一律配 reducer，单点写入字段不配 | 无 reducer 的并发写入在 LangGraph 下会直接冲突报错，属于有意保护 |
| 依赖安装 | 只装 `pydantic` + `pyyaml` | 没有它们，配置 Schema 校验与类型契约无法被真实验证；不装任何 AI 框架 |
| `.gitignore` | `env/` 锚定为 `/env/` | 原规则会忽略任意层级的 `env/` 目录，威胁未来的 `app/env/` 包 |

### 修改的文件

| 文件 | 变更 |
|---|---|
| `backend/app/paths.py` | 新增 |
| `backend/app/agents/base/{contracts,protocol,base_agent,registry,errors,__init__}.py` | 新增 |
| `backend/app/agents/factory.py` | 新增 |
| `backend/app/agents/{lease,billing,compliance}/{agent.py,prompts/system.md}` | 新增（骨架） |
| `backend/app/config/{schema,loader}.py`、`config/agents/{lease,billing,compliance}.yaml` | 新增 |
| `backend/app/llm/adapter.py`、`backend/app/tools/base.py` | 新增 |
| `backend/app/orchestration/{state,coordinator}.py` | 新增 |
| `backend/tests/smoke_agent_contracts.py` | 新增（57 项自检） |
| `docs/architecture/agent_architecture.md` | 新增 |
| `docs/architecture/agent_development_guide.md` | 新增 |
| `docs/prompts/04_agents/2026-11-03_003_modular_multi_agent_architecture.md` | 新增 |
| `.gitignore` | `env/` → `/env/` |
| `docs/README.md` | 编号登记表补 003 |
| `docs/architecture/system_design.md` | 引用新文档 + ADR |
| `docs/lessons_learned/knowledge_notes.md` | 新增笔记 |
| `docs/prompts/04_agents/.gitkeep` | 删除（目录已有实际文件） |

### 测试和验证结果

| 验证项 | 命令 / 方式 | 结果 |
|---|---|---|
| 架构骨架自检 | `python backend/tests/smoke_agent_contracts.py` | **57 项全部通过，退出码 0** |
| 配置 Schema 拒绝非法输入 | 自检分组 1 | 7 类非法配置全部被拒（含 `api_key` 字面量、绝对路径、路径穿越、非法能力名、rerank>top_k、未知字段、非法环境变量名） |
| 能力禁用可区分 | 自检分组 2 | `AgentDisabledError` 与 `CapabilityUnavailableError` 均按预期抛出 |
| Prompt 隔离 | 自检分组 4 | lease 与 billing 的 Prompt 内容互不包含 |
| 模型参数裁剪 | 自检分组 5 | `temperature: null` 时该参数不下发 |
| 计划可行性 | 自检分组 6 | available / disabled / missing 三类正确区分 |
| 白名单安全性 | 自检分组 7 | 白名单外 `name` 抛 `AgentNotRegisteredError`，无动态导入 |
| 依赖范围 | `pip list` | 仅 pydantic / pydantic-core / pyyaml / typing-* / annotated-types，无 AI 框架 |
| `.gitignore` 修正有效 | `git check-ignore` | `backend/` 下 6 个代表路径均可跟踪 |

### 当前项目状态

架构骨架完整可运行（57 项自检全绿），三个 Agent 均为 `NOT_IMPLEMENTED` 占位，无任何业务逻辑。LangGraph / FastAPI / 数据库 / RAG 均未接入。仓库已有一次提交 `7ed2665`，本次变更尚未提交。

### 下一步开发计划

- [ ] 确认后提交本次架构骨架
- [ ] 阶段 1：`pyproject.toml`、FastAPI 入口、配置层（Pydantic Settings）、迁移自检脚本到 pytest
- [ ] 阶段 2：确定多租户字段并落地数据库 Schema
- [ ] 阶段 3：RAG 检索工具接入 `retrieval_settings`
- [ ] 阶段 4：LangGraph 集成，实现 Coordinator，补并发写入测试

---

## [2026-11-03] 任务 002 - 项目文档与 Prompt 归档系统

- **日期**：2026-11-03
- **开发阶段**：环境搭建 / 工程规范
- **对应 Prompt 归档**：`docs/prompts/01_environment/2026-11-03_002_docs_prompt_archive_system.md`

### 本次完成的功能

- 建立 `docs/` 完整目录结构（architecture / prompts / development_logs / issues / lessons_learned / checkpoints）。
- 建立 Prompt 归档机制，包含 9 段式归档模板与全局递增编号规则。
- 归档任务 001（Conda 环境配置）与任务 002（文档系统）两条历史 Prompt。
- 建立开发日志、问题记录、知识笔记、Git 检查点四类文档及各自模板。
- 编写 `docs/README.md` 作为统一规范入口，含目录说明、命名规范、更新流程、记录原则与 Git 约定。

### 主要技术决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 空目录占位 | `.gitkeep` | Git 不跟踪空文件夹，需要占位文件才能把目录结构提交进仓库 |
| 模板存放位置 | 嵌入各文档文件头部的「模板」小节 | 严格遵循用户指定的目录结构，不额外引入 `templates/` 目录，同时保证模板触手可及 |
| Prompt 原文保存方式 | 4 个反引号围栏的代码块 | 原始 Prompt 内部含 3 个反引号的代码块（如 `conda create ...`），用 4 反引号包裹可避免围栏提前闭合 |
| 编号规则 | 三位数全局递增，跨模块不重置 | 保证任一编号在项目内唯一，便于跨模块按序检索 |
| 归档范围 | 仅保存真实发生过的任务 | 遵守「不为没做过的工作编造记录」原则 |

### 修改的文件

| 文件 | 变更 |
|---|---|
| `.vscode/settings.json` | 新增（本地文件，已被 .gitignore 忽略） |
| `docs/README.md` | 新增 |
| `docs/architecture/system_design.md` | 新增（骨架） |
| `docs/architecture/database_design.md` | 新增（骨架） |
| `docs/prompts/01_environment/2026-11-03_001_conda_environment.md` | 新增 |
| `docs/prompts/01_environment/2026-11-03_002_docs_prompt_archive_system.md` | 新增 |
| `docs/prompts/02_database/.gitkeep` 等 5 个 | 新增（占位） |
| `docs/development_logs/development_log.md` | 新增 |
| `docs/issues/issue_log.md` | 新增 |
| `docs/lessons_learned/knowledge_notes.md` | 新增 |
| `docs/checkpoints/git_history.md` | 新增 |

### 测试和验证结果

| 验证项 | 命令 / 方式 | 结果 |
|---|---|---|
| 目录结构完整 | `Get-ChildItem docs -Recurse -Directory` | 12 个目录全部就位 |
| `docs/` 未被忽略 | `git check-ignore -v docs/...`（7 个代表路径） | 全部 `NOT IGN`，未被排除 |
| 空目录可入库 | 各空目录生成 `.gitkeep` | 5 个 `.gitkeep` 已生成 |
| Git 变更可见 | `git status --short --ignored` | `docs/` 与 `.gitignore` 为未跟踪状态，`.vscode/` 已忽略 |

### 当前项目状态

Conda 环境 `commercial-agent` 可用，文档与归档体系已建立，仓库尚无任何提交。项目代码为空，等待进入数据层与 Agent 骨架开发。

### 下一步开发计划

- [ ] 确认并执行首次 Git 提交（`.gitignore` + `docs/`）
- [ ] 建立 `pyproject.toml` 与项目最小目录骨架（`app/`、`agents/`、`tests/`）
- [ ] 设计 PostgreSQL 表结构，输出 `docs/architecture/database_design.md` 正式版本

---

## [2026-11-03] 任务 001 - Conda 独立环境配置

- **日期**：2026-11-03
- **开发阶段**：环境搭建
- **对应 Prompt 归档**：`docs/prompts/01_environment/2026-11-03_001_conda_environment.md`

### 本次完成的功能

- 确认项目根目录为 `D:\commercial-property-multi-agent`，Git 仓库已初始化且绑定远端 `minatolog/commercial-property-multi-agent`。
- 定位 Anaconda 安装位置 `D:\anacada`（Anaconda3 2025.12-2，conda 26.1.1），并确认其未加入系统 PATH。
- 盘点已有环境（`base` / `aiagent` / `z5581485`），确认 `commercial-agent` 无命名冲突。
- 创建独立环境 `commercial-agent`（Python 3.11.18 + pip 26.2.2），路径 `D:\anacada\envs\commercial-agent`。
- 将 VS Code Python Interpreter 指向该环境，并写入 `.vscode/settings.json` 兜底。
- 创建 `.gitignore`，覆盖密钥、Python 缓存、工具缓存、向量库数据与 VS Code 个人配置。
- 未安装任何项目依赖（仅 pip / setuptools / wheel / packaging）。

### 主要技术决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 环境管理方式 | Conda 独立命名环境，不使用 venv | 项目后续需要 BGE Embedding、向量检索等可能含原生扩展的依赖，Conda 在 Windows 上处理二进制依赖更稳 |
| Python 版本 | 3.11 | LangGraph / LangChain 生态与 3.11 兼容性最成熟，3.12+ 部分依赖轮子尚不齐全 |
| 环境存放位置 | 默认 `D:\anacada\envs\`，不放进项目目录 | 环境体积大且含绝对路径，放入项目会污染仓库并拖慢 Git 操作 |
| `.vscode` 忽略策略 | 忽略全部 + 白名单 `extensions.json` / `launch.json` / `tasks.json` | 个人机器配置（含解释器绝对路径、终端设置）不进仓库，团队可共享的调试配置保留 |
| 项目依赖 | 本次一律不装 | 遵循「仅完成环境准备」的要求，避免在架构未定时锁定版本 |

### 修改的文件

| 文件 | 变更 |
|---|---|
| `.gitignore` | 新增 |
| `.vscode/settings.json` | 新增（本地文件，已被 .gitignore 忽略） |

### 测试和验证结果

| 验证项 | 命令 / 方式 | 结果 |
|---|---|---|
| 环境创建成功 | `conda env list` | 列表中存在 `commercial-agent` → `D:\anacada\envs\commercial-agent` |
| Python 版本 | `python --version` | `Python 3.11.18` |
| Python 来源 | `sys.executable` | `D:\anacada\envs\commercial-agent\python.exe` |
| pip 来源 | `python -m pip --version` | pip 26.2.2 from `...\commercial-agent\Lib\site-packages` |
| 环境隔离 | 打印 `sys.path` | 仅含 `commercial-agent` 路径，无 base 环境泄漏 |
| 依赖干净 | `pip list` | 仅 packaging / pip / setuptools / wheel |
| 其他环境未受影响 | 对比 `envs` 目录时间戳 | `aiagent`、`z5581485` 时间戳不变 |
| `.gitignore` 生效 | `git check-ignore -v`（双向用例） | 该忽略的已忽略，源码路径均未被忽略 |
| VS Code 解释器 | Python 扩展环境信息 | Environment Type: conda，Version: 3.11.18 |
| 激活可用性 | `conda activate commercial-agent` | `CONDA_PREFIX` 正确，`where python` 首选该环境，`conda deactivate` 正常回退 |

### 当前项目状态

开发环境就绪，仓库无代码。`.gitignore` 与 `.vscode/settings.json` 已建立但尚未提交。

### 下一步开发计划

- [ ] 提交 `.gitignore`
- [ ] 建立 `pyproject.toml`
- [ ] 规划 PostgreSQL 表结构与 Agent 模块划分
