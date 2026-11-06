# 2026-11-06_007_Agent Runtime 与受控工具执行

## 1. 任务信息

- **任务编号**：007（正式 Prompt 2）
- **状态**：**R1 已修复，待 Codex 复验**（2026-11-06；F1/F2 见 §16）
- **唯一需求基线**：[Agent-first V1.0](../../handoffs/PROJECT_REFOCUS_AGENT_FIRST_V1.0.md)
- **实现规格**：[Runtime contracts](../../architecture/agent_runtime_contracts.md)、[MVP scope](../../product/mvp_scope_v2.md)、[Evaluation plan](../../evaluation/evaluation_plan.md)
- **前置验收**：[Task 006 R2 Review](../../reviews/2026-11-06_task006_r2_review.md)
- **Codex Review**：[Task 007 Review R1](../../reviews/2026-11-06_task007_review.md)

## 2. 目标

在保留现有 Agent 契约和 57 项 smoke 自检兼容性的前提下，完成**可测试、离线、确定性的 Agent Runtime 与 Tool Executor 最小实现**。用户能通过命令行对固定合成数据发起受控只读工具任务，获得结构化结果、证据和调用 Trace。

本任务证明 Runtime 边界、权限、预算、可靠性和工具调用机制，不实现真实模型调用或多 Agent 图。

## 3. 开始前必须执行

1. 先检查 `git status --short`、HEAD、`git diff --check`、现有测试与目录结构；不得重置、暂存、提交或清理工作区。
2. 当前工作区有任务 007 之前的广泛未提交内容。只修改本 Prompt 授权的文件；不覆盖、认领或删除既有改动。
3. 读取本 Prompt §1 全部基线和 `agent_runtime_contracts.md` §13 K1–K5。
4. 记录执行前 Git 状态及授权文件清单。若发现会改变既有用户数据、需要外部服务/凭据或无法判断的冲突，先停止并报告。

## 4. 实施范围

### 4.1 可运行工程入口

- 在 `backend/` 建立最小 `pyproject.toml`，声明当前源码必需依赖、pytest 测试配置和 CLI 入口；版本范围需兼容现有 Pydantic v2 / PyYAML 用法。
- 只添加当前任务真实使用的依赖：不得引入 LangChain、LangGraph、数据库、向量库、Web/API 或真实模型 SDK。
- 增加可复现的 CLI，例如 `python -m app.cli ...`，加载 Agent 配置并调用 Runtime。提供 `--help` 和一条 fixture 只读演示命令。
- 不要求联网，不读取或打印 API key，不修改当前 Conda 环境；仅声明依赖，不安装。

### 4.2 契约增量与 Agent Runtime

- 按 Runtime contracts §1–§5 增量实现：可信执行上下文（权限/项目范围不可来自用户 payload）、Evidence/ Finding 或本阶段必要的结构化证据类型、稳定结构化结果和错误语义。
- 保持 `AgentProtocol.handle()`、既有 `AgentRequest` / `AgentContext` / `AgentResult` 既有字段及 capability 命名兼容；新增字段必须有默认值或可空，不引入并行 V1/V2 生命周期。
- 不要一次性把 `AgentResult.output` 从 dict 替换成另一类型；无需为尚未实现的 Task 008+ 模型、Task 009 图或审批恢复预留抽象层。
- 修复 contracts §13 中 K1–K5：Registry 替换原子性、配置与类描述符一致校验、deadline 限制单次执行及重试、`allow_partial=False` 对所有 PARTIAL 的一致处理、SKIPPED 聚合语义。若选择与规格建议不同的 SKIPPED 聚合结果，必须给出一致且可观察的理由，并更新对应规格。

### 4.3 Tool Registry / Executor

- 实现独立 Tool Registry 和 Executor；工具按静态白名单注册，拒绝重名/替换冲突和未注册工具，不允许配置字符串动态导入 Python 类。
- 每个工具有版本/名称、严格参数 Schema、输出校验、所需权限及项目范围检查。授权同时满足 Agent config `allowed_tools` 与可信 `AgentContext.permissions`；不得从 `AgentRequest.payload` 推导权限或扩大范围。
- 实现有限超时、可配置有限重试、共享并发安全的调用预算和结构化 Tool Trace（call id、trace id、工具名、参数摘要、状态、错误码、attempt、耗时；不得记录密钥）。重试不得重复扣除成功调用预算或重复写入；本任务工具均为只读。
- 不提供任意 SQL、Python、Shell、文件系统或网络工具。
- 对未经允许、权限不足、非法参数、非法结果、超时、重试耗尽、预算耗尽等返回稳定错误码，不吞异常。

### 4.4 合成 fixture 与只读工具

- 读取 `docs/evaluation/fixtures/agent_first_v1.json`，通过明确的 FixtureRepository / 数据边界只读查询；不可把 fixture 复制成第二份事实源。
- 提供最小的 Lease、Billing、Property 域只读工具，覆盖租约/合同事实、账单/付款事实、维修工单事实中的代表性查询。真实具体字段以 fixture 为准。
- 每条返回事实附稳定 evidence id、工具来源、fixture dataset version、project_id、合成数据标记及可追溯记录 ID；越权项目不得通过猜参数读取。
- 金额只用 `Decimal`，不得由 float 进行财务计算。保留 Task 006 fixture 中的关键金额结果（如适用）：未收 `18036.00`、超额 `756.00`、更正后未收 `17280.00`。
- 注入 Fake Model / Fake Agent 仅用于证明 Runtime 调用边界；不得声称连接 DeepSeek 或真实 Tool Calling。

## 5. 测试与验收标准

运行并记录真实命令、Python 版本、退出码和结果：

1. 原有 `backend/tests/smoke_agent_contracts.py` 57 项全部通过；
2. 新增 pytest 自动化覆盖，至少包括：K1 原子替换失败保留旧注册；K2 配置描述符不一致被拒；K3 既有 deadline 可在单次执行中中止并限制重试总时长；K4/K5 聚合边界；
3. Tool 白名单、权限、可信项目范围、输入/输出 schema、未知工具拒绝；
4. timeout / retry / budget 并发竞争 / 调用 trace / 重试与预算幂等语义；
5. Lease/Billing/Property 至少各一条 fixture 查询；跨项目访问拒绝；无真实数据库/模型/网络；
6. Decimal 金额与证据来源关联正确；
7. CLI `--help` 和 fixture 演示可运行；
8. 相对链接、配置与敏感键扫描；`git diff --check`。将本轮告警与原有 `database_design.md:1661` EOF 空行明确区分；不要修改该文件。

只报告实际执行结果；不得以静态检查、手工伪造输出、DeepSeek 自报或未运行的测试宣称通过。任何失败均应修复后重跑。

## 6. 明确不做

- 不安装依赖、不修改 Conda 环境、不调用模型 API、不需要密钥或网络；
- 不实现 LangChain、Tool Calling 模型循环、LangGraph、多 Agent 并行图；
- 不建数据库、不创建 ORM/Alembic/SQL，不改 `database_design.md`；
- 不实现 RAG、PDF、审批/checkpoint、FastAPI/UI；
- 不实现业务写入、调账、退款、派单；
- 不提交、不推送、不打 Tag、不通过 GitHub Desktop 发布。

## 7. 修改范围与归档

可修改 `backend/` 下实现、测试、配置与最小运行文档；`docs/` 仅同步本 Prompt 归档、Docs README、开发日志、问题记录（若有真实问题）、Git 检查点和路线状态。若确需改动其他文件，先在完成报告说明理由，保持最小范围。

实现必须按独立模块组织：契约 / Registry / Runtime / Tool Registry 与 Executor / Fixture Repository / CLI 分层；Agent 通过接口依赖工具，不反向依赖具体业务工具；新增 Agent 或工具不得要求修改无关 Agent；配置独立且不含秘密。

## 8. 完成报告格式

完成后停止，不启动 Task 008。报告：

1. 实际修改文件清单及每个模块职责；
2. 真实运行的命令、结果、退出码；
3. K1–K5 的修复证据；
4. 工具权限、预算、重试、证据的演示结果；
5. 变更前后 Git 状态、HEAD，是否提交（应为否）；
6. 未完成项、风险与需要 Codex 复验的内容。

---

## 9. 执行记录（2026-11-06）

- **执行者**：DeepSeek（DeepSeek Harness 会话）
- **执行前状态**：分支 `main`，HEAD `7ed2665bb9201568a8d74a12af37bf0a502378f1`；96 个文件（排除 `.git`）逐文件 SHA-256 记入基线；工作区含此前未提交内容，全部保留。
- **运行环境**：`D:\anacada\envs\commercial-agent\python.exe`，Python 3.11.18；pydantic 2.14.2、PyYAML 6.0.3；**未安装任何新依赖**（`pytest` 在本环境不可用，且本任务禁止安装）。

真实步骤：

1. 读取本 Prompt、[Runtime contracts](../../architecture/agent_runtime_contracts.md) §13、[MVP scope](../../product/mvp_scope_v2.md)、[Evaluation plan](../../evaluation/evaluation_plan.md) 与 [Task 006 R2 复验](../../reviews/2026-11-06_task006_r2_review.md)。
2. 记录 `git status`、HEAD 与 96 个文件的 SHA-256 基线；先跑既有 57 项自检确认起点。
3. 修复 K1–K5（详见 §12）。
4. 新增 `app/fixtures/`、`app/runtime/`、`app/tools/registry.py`、`app/tools/executor.py`、`app/tools/fixture_tools.py`、`app/demo.py`、`app/cli.py`，以及 `backend/pyproject.toml`、`backend/README.md`。
5. 新增 `backend/tests/test_runtime.py`：`unittest.TestCase` 编写（当前环境无 pytest），同时可被 pytest 原生收集。
6. 运行验收命令并记录真实输出；更新本归档、Docs README、开发日志、Issue、Git 检查点与路线状态。

## 10. 文件清单与模块职责

### 10.1 新增

| 文件 | 职责 |
|---|---|
| `backend/pyproject.toml` | 最小工程入口：`pydantic`/`PyYAML` 依赖声明、pytest 配置、`app.cli:main` 控制台入口；**未引入** LangChain/LangGraph/DB/向量库/Web/模型 SDK |
| `backend/README.md` | 运行命令、模块地图、安全边界与未实现范围 |
| `backend/app/fixtures/__init__.py` / `repository.py` | fixture 只读仓库：唯一事实源、项目范围校验、`Decimal`、变体 overlay |
| `backend/app/runtime/__init__.py` / `types.py` | `TrustedContext`、`Evidence`/`EvidenceDraft`、`ToolTrace`、`ToolExecution`、`RuntimeResult`、`TraceLog` |
| `backend/app/runtime/budget.py` | 共享预算：原子 `reserve` / `settle` / `release`，按 `call_id` 幂等 |
| `backend/app/runtime/agent_runtime.py` | Runtime 边界：拒绝 payload 授能给、按 capability 解析 Agent、汇总证据/Trace/预算 |
| `backend/app/tools/registry.py` | 工具静态白名单：拒绝重名、拒绝非 `BaseTool`、拒绝非法元数据 |
| `backend/app/tools/executor.py` | 统一执行器：白名单 → 权限 → 参数 Schema → 预算预留 → 超时/有限重试 → 输出/范围校验 → Trace |
| `backend/app/tools/fixture_tools.py` | `lease.lookup`、`billing.statement.read`、`billing.arrears.calculate`、`property.work_orders.read` |
| `backend/app/demo.py` | `ScriptedToolAgent`（Fake Agent）与端到端接线，**不调用模型** |
| `backend/app/cli.py` | `python -m app.cli`：`--help` / `tools` / `check` / `demo` |
| `backend/tests/test_runtime.py` | 51 个自动化测试（初版 47 + R1 回归 4：F1 租约隔离 2、F2 Trace 隔离 2） |

### 10.2 修改

| 文件 | 改动 |
|---|---|
| `backend/app/agents/base/errors.py` | 新增工具/预算/范围错误码与异常；`TOOL_TIMEOUT` 归入可重试码 |
| `backend/app/agents/base/contracts.py` | `AgentContext` 增量新增 `principal_id`、`project_ids`（有默认值，向后兼容） |
| `backend/app/agents/base/base_agent.py` | K3：`timeout = min(配置超时, 剩余 deadline)`，重试不越过 deadline |
| `backend/app/agents/base/registry.py` | K1：副本上计算 + 一次性发布，失败保留旧注册 |
| `backend/app/agents/factory.py` | K2：启动期校验配置 `version`/`capabilities` 与实现类一致 |
| `backend/app/orchestration/coordinator.py` | K4/K5：`PARTIAL`/`SKIPPED` 聚合语义穷尽化 |
| `backend/app/paths.py` | 新增 `REPO_ROOT`、`DEFAULT_FIXTURE_PATH` |
| `backend/app/tools/base.py` | 新增 `BaseTool`、`ToolInvocation`；保留原有 `ToolProtocol` 与 `assert_*` 辅助函数 |

**未修改**：`docs/architecture/database_design.md`、`backend/app/agents/{lease,billing,compliance}` 业务逻辑（仍为 `NOT_IMPLEMENTED` 骨架）、三个 Agent YAML、历史 Prompt 原文。

## 11. 验证命令与真实结果

均在 `backend/` 下执行（PowerShell）：

| # | 命令 | 退出码 | 真实结果 |
|---|---|---|---|
| 1 | `python tests/smoke_agent_contracts.py` | 0 | `全部通过：57 项检查` |
| 2 | `python -m unittest discover -s tests -v` | 0 | 初版 `Ran 47 tests ... OK`；R1 后 `Ran 51 tests ... OK` |
| 3 | `python -m app.cli --help` | 0 | 列出 `tools` / `check` / `demo` 三个子命令 |
| 4 | `python -m app.cli tools` | 0 | 4 个工具，含权限/超时/重试上限 |
| 5 | `python -m app.cli check` | 0 | 3 个 Agent、4 个能力、4 个工具；如实列出未实现的 `lease.term_extract`、`compliance.checklist.read` |
| 6 | `python -m app.cli demo` | 0 | `status=success`；3 次工具调用、3 条 Trace、24 条证据；未收 `18036.00` |
| 7 | `python -m app.cli demo --variant v_oct_rent_corrected` | 0 | 未收 `17280.00`（数据更正后结论随之变化） |
| 8 | `python -m app.cli demo --budget-tool-calls 1` | 2 | 第二次调用返回 `BUDGET_EXHAUSTED`，命令以 2 退出（失败可见，不静默成功） |
| 9 | `python -m pytest --version` | 1 | `No module named pytest`（本环境未安装；未尝试安装） |

`demo` 的关键金额与证据：应收 `52596.00`、有效付款 `34560.00`、未收 `18036.00`、10 月租金超额 `756.00`；全部以十进制字符串传输，证据为 `db_fact` 且带 `dataset_version=agent-first-v1`、`as_of_date=2026-11-03`、`project_id=prj_xinghui`、`synthetic=true`、`tool_call_id`。

## 12. K1–K5 修复证据

| 编号 | 修复 | 自动化证据（`test_runtime.py`） |
|---|---|---|
| **K1** | Registry 替换改为"副本计算 + 原子发布"；任何失败都在发布前发生 | `TestK1RegistryAtomicReplace::test_failed_replace_keeps_old_registration`（替换抛错后名称/能力/解析不变）、`test_replace_success_swaps_capabilities_atomically` |
| **K2** | 工厂在启动期校验配置 `version` 与 `capabilities` 和实现类一致，不一致即 `AgentConfigMismatchError` | `TestK2ConfigDescriptorConsistency::test_version_mismatch_rejected`、`test_capability_mismatch_rejected`、`test_matching_config_builds` |
| **K3** | 单次执行 `timeout = min(配置超时, 剩余 deadline)`；重试循环每次先检查剩余 deadline；deadline 命中返回 `DEADLINE_EXCEEDED` | `TestK3DeadlineBoundsSingleExecution` 三项：单次中止 < 1.5s、重试总时长 < 1.2s、过期 deadline 直接失败且 `attempt=0` |
| **K4** | `allow_partial=False` 时，任何非全成功（含 PARTIAL）都聚合为 `FAILED` | `TestK4K5Aggregation::test_partial_visible_only_when_allowed`、`test_mixed_skipped_is_partial_only_when_allowed` |
| **K5** | 全 `SKIPPED` → `FAILED`；混合 SKIPPED 按"未全部成功"处理 | `test_all_skipped_is_failed` |

K5 的取舍：规格建议"全 SKIPPED → FAILED（或 partial + 理由）"，本次选 **FAILED**——没有任何成功产出时把它报成"部分成功"会掩盖"什么都没做成"，下游会按失败处理缺口。该语义写在 `summarize_results` docstring 的穷尽表中，且 `allow_partial=False` 时混合 SKIPPED 同样降级为 FAILED。

## 13. 工具权限、预算、重试与证据演示结果

| 场景 | 结果（均有自动化断言） |
|---|---|
| Agent `allowed_tools` 未包含工具 | `TOOL_NOT_ALLOWED`，状态 `denied`，不执行工具 |
| 可信上下文缺少权限 | `PERMISSION_DENIED` |
| 未注册工具 | `TOOL_NOT_FOUND` |
| 参数不合法（互斥字段、未知字段、保留键） | `INVALID_TOOL_ARGUMENTS`；payload 里写 `permissions` 被直接拒绝 |
| 输出 Schema 不合法 | `INVALID_TOOL_RESULT` |
| 工具返回越权项目证据 | `PERMISSION_DENIED`，不返回数据 |
| 跨项目查询（星汇上下文读锦澜租约，或反之） | `PROJECT_SCOPE_DENIED`，`data` 为空 |
| 超时后有限重试 | 第 1 次 `timeout`、第 2 次成功；`attempts=2`、2 条 Trace、预算只计 1 |
| 重试耗尽 | `TOOL_TIMEOUT`、`attempts=2`、预算只计 1 |
| 预算耗尽 | `BUDGET_EXHAUSTED`，不再执行 |
| 10 并发 / 预算 3 | 恰好 3 成功、7 `BUDGET_EXHAUSTED`，`used_tool_calls=3`（无超发） |
| Trace | 含 `call_id`、`trace_id`、工具名、16 位参数摘要、状态、错误码、attempt、耗时；**不含原始参数** |
| 证据来源 | `source_tool`/`tool_call_id` 由执行器写入；`synthetic=true`、`dataset_version`/`as_of_date`/`project_id` 齐全；`record_id` 可在 fixture 中反查 |

## 14. 变更前后 Git 状态

- 执行前：`main` / `7ed2665bb9201568a8d74a12af37bf0a502378f1`；96 个文件（排除 `.git`）逐文件 SHA-256 基线。
- 执行后：HEAD **未变**；`git status --porcelain` 与执行前**逐行相同**（25 行）；**未暂存、未提交、未推送**。
- 文件级比对（含被 `.gitignore` 忽略的 `__pycache__` 缓存）：96 → 122 个文件，**0 删除**；新增 26 个（其中 14 个源码/工程文件、12 个 `.pyc` 缓存），变化 22 个（8 个源码 + 6 个文档 + 8 个重新生成的 `.pyc`），其余 74 个逐字节不变。
- 源码变化清单（8 个，均在授权范围）：`agents/base/{errors,contracts,base_agent,registry}.py`、`agents/factory.py`、`orchestration/coordinator.py`、`paths.py`、`tools/base.py`。
- `backend/` 下的 62 个原有文件中，46 个逐字节不变（含三个 Agent 实现、三个 YAML、`llm/adapter.py`、`config/*` 等）；变化的源码只有上面 8 个。
- `docs/architecture/database_design.md`：SHA-256 仍为 `1b7e37350a18ff4c17e7063558a1ab3b4be5beabbd6a94aa4efbe236a5f56db7`，未变。
- `__pycache__/` 被 `.gitignore` 忽略，`.pyc` 只是本地运行缓存，不是交付物。

## 15. 未完成项、风险与 Codex 复验建议

1. **pytest 未安装**：本环境没有 pytest，且 Prompt 明确"不安装依赖"。测试因此用标准库 `unittest` 编写并执行；`Test*`/`test_*` 命名与 `unittest.TestCase` 结构可被 pytest 原生收集。Codex 若在装有 pytest 的环境复验，可直接 `pytest backend/tests/test_runtime.py`。
2. **没有真实模型/图/数据库/RAG/审批/前端**：按 §6 明确不做；`ScriptedToolAgent` 是 Fake Agent，不能据此宣称已接入 DeepSeek 或真实 Tool Calling。
3. **CLI `check` 显示两个未实现的 allowed_tools**（`lease.term_extract`、`compliance.checklist.read`）：来自历史 YAML，本轮不实现也不删除（删除会改变既有配置语义）。执行器在真正调用时会返回 `TOOL_NOT_FOUND`。
4. **依赖只声明未安装**：`backend/pyproject.toml` 声明 `pydantic`/`PyYAML`（环境已有）；`dev` extras 里的 pytest 未安装。
5. **`git diff --check` 仍报告** `docs/architecture/database_design.md:1661` EOF 空行，属 Task 005 遗留，本任务禁止修改该文件。
6. **复验建议**：先跑 §11 的 1–2 条命令，再重点检查 K1 的"替换失败保留旧注册"、K3 的 deadline 中止耗时、预算并发与 Trace 不含原始参数；最后确认 `backend/` 历史 57 项与三个 YAML 未被语义性改动。

## 16. Prompt 2-R1 返修记录（F1 / F2，2026-11-06）

**依据**：[Task 007 Review R1](../../reviews/2026-11-06_task007_review.md) 的 Prompt 2-R1。只修两项隔离缺口，不扩大业务范围。
**当前状态**：**R1 已修复，待 Codex 复验**。

### 16.1 F1：账单查询误计同项目其他租约的付款

| 项 | 修正前 | 修正后 |
|---|---|---|
| allocations | 只按 `project_ids` + 付款状态过滤 | 必须 `alloc["invoice_id"] in 本租约 invoice_ids` |
| payments | 返回项目内**全部** confirmed 付款 | 只返回被上述 allocations 引用到的付款，避免把无核销/他租约付款算进已收 |
| 冲销 | 已排除 | 保持排除（`reversed_at is None` + 付款 `confirmed`） |

**证据**：新增 `TestStatementLeaseIsolation`（2 个测试）。测试在 fixture 内存副本中追加同项目 A-302 的账单、`100.00` 确认付款与核销 `alloc_test_a302`，然后断言：

- A-301 Statement 仍为应收 `52596.00`、已收 `34560.00`、未收 `18036.00`；
- A-301 的 `allocations` 恰为 `{alloc_001, alloc_002}`、`payments` 恰为 `{pay_2026_08_28, pay_2026_09_28}`，不含 `alloc_test_a302` / `pay_test_a302`；
- A-302 Statement 只用自己的 `100.00` 付款（已收 `100.00`、未收 `0.00`）。

### 16.2 F2：Runtime 复用后 Trace 混入先前执行

| 项 | 修正前 | 修正后 |
|---|---|---|
| Trace 归属 | `RuntimeResult.tool_traces = TraceLog.snapshot()`（进程级累计） | 只取 `trace.run_id == 本次 run_id` 的记录 |
| 共享日志 | 会被后续调用污染结果 | 保持 **append-only 全局日志**，并发 run 都往里追加，不清空 |
| 标记方式 | 无 | `ToolTrace.run_id` 由执行器从 `AgentContext.run_id` 写入；Runtime 每次执行生成新 `run_id` |

**证据**：新增 `TestTraceIsolation`（2 个测试）：

- 同一 `build_demo_bundle()` 连续两次 `run_demo`：每次结果各 3 条 Trace，`call_id` 集合不相交，且各自 `run_id` 全匹配；共享 `TraceLog` 仍保留 6 条历史；
- `asyncio.gather` 并发两个 run：结果各 3 条、互不交叉，共享日志恰好 6 条且等于两次结果并集——证明没有"清空共享日志"导致的丢数据。

### 16.3 本轮修改文件

| 文件 | 改动 |
|---|---|
| `backend/app/fixtures/repository.py` | F1：`statement()` 按本租约 invoice IDs 过滤 allocations，并据此回收 payments |
| `backend/app/runtime/agent_runtime.py` | F2：`run()` 生成 `run_id` 并过滤本次 Trace；新增 `_traces_for_run()` |
| `backend/app/runtime/types.py` | F2：`ToolTrace.run_id`；`to_agent_context(run_id=...)` |
| `backend/app/agents/base/contracts.py` | F2：`AgentContext.run_id`（可空，向后兼容） |
| `backend/app/tools/executor.py` | F2：Trace 写入 `context.run_id` |
| `backend/tests/test_runtime.py` | 新增 F1/F2 共 4 个回归测试；日志改走 stdout |

**未改**：业务工具查询范围、审批/数据库设计、三个 Agent YAML、历史 Prompt 原文；未安装依赖、未调用模型、未建库、未提交/推送。

### 16.4 R1 验证结果

| # | 命令 | 退出码 | 结果 |
|---|---|---|---|
| 1 | `python tests/smoke_agent_contracts.py` | 0 | 57 项通过 |
| 2 | `python -m unittest discover -s tests` | 0 | `Ran 51 tests ... OK`（初版 47 + R1 4） |
| 3 | `python -m app.cli --help` | 0 | 正常 |
| 4 | `python -m app.cli tools` | 0 | 4 个工具 |
| 5 | `python -m app.cli check` | 0 | 3 Agent / 4 能力 / 4 工具 |
| 6 | `python -m app.cli demo` | 0 | `success`；3 Trace、24 证据、未收 `18036.00` |
| 7 | `python -m app.cli demo --variant v_oct_rent_corrected` | 0 | 未收 `17280.00` |
| 8 | `python -m app.cli demo --budget-tool-calls 1` | 2 | `BUDGET_EXHAUSTED` 可见；本次 run 只有 2 条 Trace（3 条是错误累计时才会出现） |

链接、敏感键、文件级 hash 与 `git diff --check` 结果见本轮完成报告；`database_design.md` 未变，HEAD 未变，未提交。

**R1 文件级比对**：123 → 123 个文件，**0 新增 / 0 删除**；17 个变化（6 个源码文件 + 5 个文档 + 6 个重新生成的 `.pyc` 缓存），其余 106 个逐字节不变；`docs/architecture/database_design.md` 的 SHA-256 仍为 `1b7e37350a18ff4c17e7063558a1ab3b4be5beabbd6a94aa4efbe236a5f56db7`。`git status --porcelain` 与执行前逐行相同，HEAD 未变。

