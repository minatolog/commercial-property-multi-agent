# 2026-11-06_012_持久检查点、人工审批与暂停恢复

## 1. 基本信息

- **日期**：2026-11-06
- **任务编号**：012（正式 Prompt 7）
- **模块**：04_agents
- **状态**：**DeepSeek 自检通过**（本地 SQLite 控制面；不宣称分布式恰好一次）
- **前置任务**：007（Runtime）、009（LangGraph 图）、011（证据链）
- **Git Commit**：见 §8

## 2. 任务目标和背景

Task 009 的图跑完即丢：进程退出无法恢复，也没有"人工点头"的位置。
本任务把三点补齐：

1. **持久化**：LangGraph checkpoint 落到本地 SQLite，按 `thread_id` 恢复同一条任务线；
2. **人工审批**：审批是独立节点，草案先暂停、由两名审批人串行签署，批准只产出 `approved_draft`；
3. **故障与并发**：权限撤销、版本不匹配、过期、重复恢复、预算耗尽都必须有确定性行为。

硬约束：审批台账与业务数据、与 checkpoint 三方**物理分离**；不宣称外部副作用恰好一次。

## 3. 原始用户 Prompt

本轮（2026-11-06）用户取消 Codex 逐任务审查，要求连续推进 Task 007 自检 → 015，并给出统一执行要求。与本任务相关的原文摘录：

````
## 后续任务

按照路线图中既定顺序完成 Task 008–015。先读对应范围和验收标准，再实现当前任务；
每个任务完成并自检后，自动继续下一个，不要每完成一步就等待用户或 Codex 确认。

- Task 012：持久化 checkpoint、人工审批和暂停恢复

## 每个任务的执行要求

1. 一次只推进一个任务，保持模块边界清晰、低耦合、Agent 可插拔、配置独立。
2. 按 docs/README.md 的编号规则分配下一个全局唯一 Prompt 编号，并将完整 Prompt 归档到正确目录。
3. 实现当前任务的最小完整垂直切片，不顺手扩张到无关功能。
4. 为关键行为补充自动化验证；运行本任务相关测试和适当的现有回归测试，记录真实命令与结果。
5. 每个任务结束后更新：Prompt 归档、development_log、路线图、issue_log/knowledge_notes（必要时）、
   git_history 检查点。
6. 只有真实实现和验证完成后，才可把任务标记为"DeepSeek 自检通过"。不得编造测试、提交、推送或模型调用结果。
7. API Key 等只从环境变量或本地忽略文件读取，绝不写入代码、文档、日志、测试输出或 Git。
8. 没有外部凭据时，完成可验证的接口、Fake/离线测试和配置说明；准确标出真实服务验证受凭据限制。
9. 不重建或删除现有数据库设计，不擅自变更业务范围，不引入未论证的大型依赖。
10. 不执行破坏性 Git 操作。
````

范围以 `docs/product/PROJECT_DEVELOPMENT_ROADMAP.md` 的 **Prompt 7 / Task 012** 为准：

> 接持久 checkpointer；明确 thread/run/request/trace 标识；审批独立节点暂停；重新授权后恢复；绑定草案版本；处理拒绝、过期、重复恢复与并发恢复。补齐超时、权限撤销、预算耗尽等故障注入。
>
> 验收：进程退出后能恢复指定任务；权限撤销或版本不匹配拒绝恢复；未经批准不继续审批路径；重复恢复不重复产出动作；批准也只形成"已批准草案"，不真实调账或派单。
>
> 检查点：checkpoint 与真实业务数据分开管理，不宣称外部副作用恰好一次。

## 4. AI 实际执行的主要步骤

1. 安装 `langgraph-checkpoint-sqlite`（3.1.3，含 `aiosqlite`）。
2. `app/orchestration/checkpointing.py`：`AsyncSqliteSaver` 异步上下文管理器；显式声明 `allowed_msgpack_modules`（仅放行本项目 `AgentContext` / `AgentOutput`）。
3. `app/orchestration/approval.py`：审批控制面
   - 模型：`ApprovalRule` / `ApprovalStage` / `ApprovalRequest` / `ApprovalDecisionOutcome`；
   - 存储：`ApprovalStore`（`approval_requests` / `approval_decisions` / `resume_ledger`）；
   - 校验链：存在 → 终态 → 过期 → 版本 → 身份/权限/项目 → 自批 → 重复签署 → 阶段顺序；
   - 幂等：`(request_id, role)` 唯一 + 同人同结论重放返回既有状态；
   - 并发：`BEGIN IMMEDIATE` + 唯一约束把并发插入变为 `ApprovalConflictError`。
4. `app/control_plane.py`：`control_plane()` 异步上下文，一起开关 checkpointer 与审批台账（路径固定在 `data/`，已加 `.gitignore`）。
5. 图改造：`report → approval → END`；`approval` 节点用 `interrupt()` 暂停，恢复后只写 `approved_draft`；无审批通道时标 `unavailable`，预算耗尽标 `blocked_budget`。
6. `Investigator`：新增 `resume()`、`thread_id`、`checkpointer`、审批钩子；`resume` 先校验再恢复，`resume_ledger` 保证重复恢复不重放。
7. CLI：新增 `approve`（含 `--dry-run`）、`pending`；`investigate` 增加 `--with-approval` / `--thread-id` / `--control-dir`。
8. 新增 `backend/tests/test_approval.py`（21 项）。

## 5. 新增和修改的文件

| 文件 | 类型 | 说明 |
|---|---|---|
| `backend/app/orchestration/approval.py` | 新增 | 审批规则、台账、校验链、幂等与并发 |
| `backend/app/orchestration/checkpointing.py` | 新增 | `AsyncSqliteSaver` 装配与 serde 白名单 |
| `backend/app/control_plane.py` | 新增 | checkpointer + 审批台账的生命周期 |
| `backend/tests/test_approval.py` | 新增 | 21 项 |
| `backend/app/orchestration/investigation.py` | 修改 | `approval` 节点、`resume()`、`thread_id`、草案解析 |
| `backend/app/investigation_demo.py` | 修改 | 控制面注入、`resume_investigation` |
| `backend/app/cli.py` | 修改 | `approve` / `pending` / `--with-approval` |
| `backend/app/paths.py` | 修改 | `DATA_DIR` / `CHECKPOINT_DB` / `CONTROL_DB` / `SQLITE_DB_PATH` |
| `backend/app/db/bootstrap.py` | 修改 | 落盘 SQLite 路径改为 `data/business/`，不再在 cwd 生成游离文件 |
| `backend/pyproject.toml` | 修改 | 声明 `langgraph-checkpoint-sqlite` |
| `.gitignore` | 修改 | 忽略 `data/`、`*.sqlite*` |

## 6. 执行结果和验证方式

| # | 命令 | 退出码 | 结果 |
|---|---|---|---|
| 1 | `python -m unittest tests.test_approval` | 0 | `Ran 21 tests ... OK` |
| 2 | `python -m unittest discover -s tests -p "test_*.py"` | 0 | `Ran 156 tests ... OK`（原 135 + 21） |
| 3 | `python tests/smoke_agent_contracts.py` | 0 | 57 项通过 |
| 4 | `python -m app.cli investigate --with-approval --thread-id thread_e2e --control-dir <tmp>` | 0 | `approval_status=pending_approval`，生成 `apr_...`（v2，700.00） |
| 5 | `python -m app.cli approve <id> --principal principal_property_manager_xinghui --draft-version 2` | 0 | `pending_next_stage`（图仍暂停） |
| 6 | `python -m app.cli approve <id> --principal principal_finance_xinghui --draft-version 2` | 0 | `approved` + `approved_draft.status=approved_draft_only`、`executed_side_effects=[]` |
| 7 | 重复执行步骤 6 | 0 | 返回首次结果 + "重复恢复"警告，不再重放节点 |
| 8 | `approve ... --draft-version 1` | 3 | `invalid_request`：审批版本不匹配：请求为 v2，提交为 v1 |
| 9 | `python -m app.cli pending` | 0 | 列出待审批请求与已记录决定 |
| 10 | 其余 CLI（`tools`/`check`/`demo`/`search`/`investigate`） | 0 | 全部正常 |

关键行为（均有断言）：

| 行为 | 证据 |
|---|---|
| 暂停后可跨连接恢复 | 三个独立 `control_plane` 上下文依次完成 investigate → 阶段1 → 阶段2 |
| 串行双人审批 | 财务先批被 `StageOrderViolationError` 拒绝；阶段1后请求仍 `pending` |
| 请求人不得自批 | `SelfApprovalForbiddenError` |
| 同一人不得签两段 | `DuplicatePrincipalError`（即便伪造双角色主体） |
| 无审批权限/跨项目 | `PermissionDeniedForApprovalError` / `ProjectScopeDeniedForApprovalError` |
| 版本不匹配 | `DraftVersionMismatchError`，且图仍停在 `('approval',)` |
| 过期 | `ApprovalExpiredError`，请求落为 `expired`，审计表无记录 |
| 拒绝终局 | `rejected` 后下一阶段 `ApprovalConflictError`；`approved_draft` 为 `null` |
| 重复恢复 | 返回首次结果 + 警告，`approval_decisions` 保持 2 条 |
| 批准不等于执行 | `approved_draft.status=approved_draft_only`、`executed_side_effects=[]` |
| 无审批通道/预算耗尽 | `unavailable` / `blocked_budget`，都显式写进 `warnings` |
| 存储分离 | 单元测试断言 `CHECKPOINT_DB != CONTROL_DB` 且均被 `.gitignore` 忽略 |

## 7. 遇到的问题及解决方法

| 问题 | 原因 | 解决 |
|---|---|---|
| `NotImplementedError: The SqliteSaver does not support async methods` | 图用 `ainvoke`，LangGraph 调用 `aget_tuple` | 改用 `AsyncSqliteSaver`（`aiosqlite` 连接） |
| 恢复时 `KeyError: 'question'`，图从 START 重跑 | `investigate()` 调 `_ainvoke(payload)` 时没传 `thread_id`，checkpoint 写到了 `thread_unknown`，恢复时读不到 | `_ainvoke(payload, thread_id=effective_thread)`；这类"标识拼错"必须靠跨进程用例暴露 |
| 暂停后 `approval_status` 仍是 `ready`、`approval_request` 为空 | `interrupt()` 会丢弃该节点本次的写入，返回值里只有 `__interrupt__` | 从 checkpoint 的 `aget_state().next` + 审批台账推出待审批请求 |
| `graph.compile()` 后 `get_state` 报 `No checkpointer set` | 编译时没传 checkpointer | `compile(checkpointer=...)`，由 `Investigator` 统一注入 |
| `Deserializing unregistered type AgentContext` 告警 | LangGraph 对未知类型反序列化会逐步收紧 | `JsonPlusSerializer(allowed_msgpack_modules=[...])` 只放行本项目两个类型 |
| Windows 下临时目录清理失败 `WinError 32` | `with sqlite3.connect(...)` 只提交事务、**不关闭连接** | `ApprovalStore._session()` 用 `contextmanager` + `finally: close()` |
| `DatabaseRepository` 没有 `snapshot()`，图构造直接崩 | 审批规则与草案来自 fixture 元数据，数据库仓库没有 | `_safe_snapshot()`：取不到就返回 `{}`，表现为"无可审批草案"而不是报错 |
| 静态 `expires_at` 让所有审批一创建就过期 | fixture 草案有效期是固定时间点 | 审批窗口从**请求创建时刻**起算（72h），草案自带有效期降级为审计字段 `draft_expires_at` |

## 8. 对应 Git Commit Hash

- **状态**：见 `docs/checkpoints/git_history.md`（里程碑提交后回填）。

## 9. 后续待办事项

- [ ] 审批目前只到"已批准草案"。真实调账/派单（含幂等键与外部对账）不在本阶段范围，接之前必须先定义外部副作用的幂等与补偿策略。
- [ ] 并发恢复只保证单机 SQLite 语义；多进程同时恢复同一 `request_id` 依赖 `resume_ledger` 唯一约束，未做跨机测试。
- [ ] 超时注入目前用"预算耗尽"与"过期"覆盖；节点级 `deadline_at` 尚未在审批门强制。
- [ ] `pending` 命令没有分页与按项目过滤，数据量上来后需要补充。
