# 2026-11-07_017_release_candidate_recheck

## 1. 基本信息

- 日期：2026-11-07（Asia/Shanghai）
- 任务编号：017
- 模块：06_testing
- 关联任务：016 及 008–015
- 执行者：Codex，按用户本次临时请求复查
- 审查基线：`main` / `bf30dd5`
- 本轮 Commit：`Pending`

## 2. 任务目标和背景

DeepSeek 已声明完成 Task 016 两批修复并记录第三批离线验证。独立检查原问题修复情况，查找遗漏或新引入的边界问题，保留真实进度与证据。

## 3. 原始用户 Prompt

```text
deepseek 说他修复完了 你找找毛病
```

## 4. AI 实际执行的主要步骤

1. 核对 Git 状态与 `041b2c5..bf30dd5` 的差异，读取修复、测试、路线图和归档记录。
2. 运行 238 项 unittest、57 项契约检查、SQLite CLI 调查入口和三基线保留集评测。
3. 独立核对金额互换、预期拒绝、单次补查成功、审批 ID/版本/意见、只读闸门和非法模型调用。
4. 用临时目录/合成数据复现旧记录迁移、跨项目报告标签、thread_id 复用、草案版本混用、工具后空答案、冲突下未补查和证据关联问题。
5. 新建复查报告，登记 Prompt、开发日志、问题入口、检查点和路线图提示。本轮不修改业务代码。

## 5. 新增和修改的文件

| 文件 | 变更 |
|---|---|
| docs/reviews/2026-11-07_release_candidate_recheck.md | 新增完整复查证据和 R1–R7 验收条件 |
| 本文件 | 新增 017 Prompt 归档 |
| docs/README.md | 登记 017 |
| docs/product/PROJECT_DEVELOPMENT_ROADMAP.md | 新增当前复查结论提示，保留历史记录 |
| docs/development_logs/development_log.md | 新增本轮日志 |
| docs/issues/issue_log.md | 新增 R1–R7 未解决入口 |
| docs/checkpoints/git_history.md | 记录基线与本轮未提交状态 |

## 6. 执行结果和验证方式

- `python -m unittest discover -s tests -p 'test_*.py'`：238 tests，OK。
- `python tests/smoke_agent_contracts.py`：57 项通过。
- `python -m app.cli investigate --backend sqlite`：exit 0。
- 当前保留集独立重跑：A 20/30、B 21/30、C 23/30，均零模型调用，未覆盖历史报告。
- 独立确认上轮主要反例改善；额外反例仍发现 4 项 P1、3 项 P2。
- 详细证据与验收要求见 [复查报告](../../reviews/2026-11-07_release_candidate_recheck.md)。

## 7. 遇到的问题及解决方法

现有回归覆盖了基础修复，但没有覆盖旧 schema 默认拒绝、多项目报告范围、持久线程复用、合同签署状态、多版本引用、前序工具后空回答及冲突与超时同时发生。问题已定位并归档，业务修复尚未实施。

## 8. 对应 Git Commit Hash

- 审查基线：`bf30dd5`。
- 本轮文档：`Pending`，没有提交或推送。

## 9. 后续待办事项

- [ ] 优先修复 R1–R4（持久状态、授权、证据适用性）。
- [ ] 修复 R5–R7（完成条件、恢复、引用关联）。
- [ ] 完成真实模型装配与调用、PostgreSQL 验证及最终 MVP 验收。

---

## 10. 实施记录（本文件 §1–§9 为复查原文，未改动）

用户要求按本报告逐项修复。执行原则：先复现，再改代码，每项加能复现原缺陷的回归测试；不改业务范围，不引入新依赖。

### 10.1 复现（改代码之前）

| 项 | 复现方式 | 修复前实测 |
|---|---|---|
| R1 | 同一 `thread_id` 先用星汇主体跑 `v_oct_rent_corrected`，再用 `principal_finance_jinlan` 的新 bundle 复用该线索 | 返回 `supported`，报告含星汇 `52596.00`；新 trace 却是 `project_scope_denied` |
| R2 | 按修复前 schema 建 runs 库 → 当前 `RunIndex` 迁移 → 金鹭主体查该 run | `get_run` 返回星汇报告，`project_ids=[]` |
| R3 | 创建者授权 `{xinghui, jinlan}` 提交星汇报告 → 金鹭主体读取 | 可读（`record_scope` 被写成两个项目） |
| R4 | v1 signed（5%）+ v2 draft（20%）同文档 | 默认检索命中 draft，finding 未标草案 |
| R5 | 第一轮正常调 `billing.statement.read`，第二轮 `text=""` | `stop_reason=final_answer`、`completed=True`、answer 为空 |
| R6 | 默认 A-301 变体（有差额）+ Property 首次 `tool_timeout` | `revision=0`，第二次未发生 |
| R7 | 同条号两版本同时存在 | 两条 finding 都绑定两个 chunk_id |

### 10.2 实际修改

| 编号 | 位置 | 修法 |
|---|---|---|
| R1 | `orchestration/investigation.py` | 新增 `ThreadIdentityConflictError`；`investigate()` 在写入前校验既有 thread 的主体/租约/`run_id`，冲突即拒绝（恢复请用 `resume()`）；`results`/`failures` 带 `run_id`，`verify`/`route`/`revise`/`report`/`_to_result` 一律按当前 run 过滤（`_scoped_by_run`） |
| R2 | `api/service.py` | `RunIndex.get()` 对空/缺失范围**默认拒绝**；`_migrate` 补 `grant_project_ids_json`；`WorkflowService._backfill_legacy_scope()` 用可信主体 + 目标租约回填，回填不了就保持隔离 |
| R3 | `api/service.py` | 记录分两个字段：`project_ids`（按目标租约解析的**报告数据范围**，用于授权）与 `grant_project_ids`（创建者授权范围，仅审计）；失败记录同样口径 |
| R4 | `rag/service.py`、`rag/library.py`、`tools/knowledge_tools.py`、`tools/fixture_tools.py`、`agents/lease/agent.py` | 索引记录 `document_status`；`search(document_statuses=...)` 默认只 `signed`；`KnowledgeLibrary.documents` 改 `(document_id, version)` 复合键；`document_ids_for_lease` 只给 signed；工具新增 `include_drafts`（默认关）与 `document_status` 证据字段；`lease.lookup` 增 `signed_document_ids`/`draft_document_ids`；草案条款标 `derivation=document_draft` 并在文案前缀声明 |
| R5 | `runtime/tool_loop.py` | 最终回合空文本一律 `MODEL_ERROR`（不再要求"无工具且无证据"）；有证据也不再算完成 |
| R6 | `orchestration/investigation.py` | `route_after_verify` 只看**未解决且可重试**的子任务，不再要求 `verdict == insufficient`；冲突照旧保留在报告里 |
| R7 | `orchestration/investigation.py` | finding 证据按 `chunk_id` 精确绑定，缺失时按 `document_id#v{version}#p{page}#{clause_id}` 复合键重建；删除条款号子串匹配；同一子任务的多次失败在报告中按 subtask 去重 |

回归测试：`test_approval.py::TestThreadIdentityBoundary`(5)、`test_api.py::TestLegacyRunScope`(3) 与 `TestReportScopeIsNotCreatorGrant`(1)、`test_rag.py::TestDocumentStatusPolicy`(6) 与 `TestFindingEvidenceBinding`(3)、`test_llm_tool_loop.py`(3)、`test_graph_workflow.py`(2)。

### 10.3 验证命令与结果

```powershell
cd D:\commercial-property-multi-agent\backend
D:\anacada\envs\commercial-agent\python.exe -m unittest discover -s tests -p "test_*.py"
# Ran 261 tests ... OK

D:\anacada\envs\commercial-agent\python.exe tests\smoke_agent_contracts.py
# 全部通过：57 项检查
```

针对性实测：

| 项 | 修复后实测输出 |
|---|---|
| R1 | `RUN1 supported []` → `BLOCKED invalid_context principal_ops_xinghui` → 新线索 `FRESH insufficient 1 False`（报告不含 `52596.00`） |
| R1（CLI 真实入口） | 同 `--thread-id` 第二次：`SECOND_EXIT=2`，`[error] ThreadIdentityConflictError: [invalid_context] thread_id='thread_reuse_demo' 已被运行 run_... 占用` |
| R5 | `STOP model_error | completed = False | evidence = 17 | answer = ''`（修复前是 `final_answer` / `completed=True`） |

### 10.4 评分规则

本轮**未改动**评分规则：`scoring-v2` 保持不变，因此不生成新的评测报告版本，历史报告继续有效。

### 10.5 Git

- 本轮业务修复与文档：见 `docs/checkpoints/git_history.md`（提交后回填 hash）。

### 10.6 仍未完成

- [ ] 真实 DeepSeek 工具调用闭环与真实 B/C 评测装配（无 `DEEPSEEK_API_KEY`）。
- [ ] PostgreSQL 实机验证（无实例，5432 不可达）。
- [ ] 人工量表评分（H25/H26 与 rubric 队列）。
- [ ] 真实服务鉴权与部署验证。
