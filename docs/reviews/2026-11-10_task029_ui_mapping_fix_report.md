# Task 029 修复报告：协作工作台 U1–U3 展示映射

- 日期：2026-11-10（Asia/Shanghai）。
- 依据：[Task 028 独立复查](2026-11-10_task027_ui_acceptance_review.md)、[Task 029 返修 Prompt](../handoffs/DEEPSEEK_TASK029_UI_MAPPING_FIX_PROMPT.md)、[029 归档](../prompts/05_frontend/2026-11-10_029_ui_mapping_fixes.md)。
- 起点：`main` / `8569cc2`；Task 027 的实现与 Task 028 文档均在未提交工作区，本轮保留原样。
- 结论：**U1 已修复、U2 已修复、U3 已修复**，并新增可重复的浏览器级 JavaScript 回归（17 个用例 / 84 个断言，含 2 个真实 API 用例）。本轮未提交、未推送。

本轮只改展示层（`app/api/static/js/*` 与一处 CSS）与新增测试，未改 Agent、工具、预算、权限、审批、数据库或评分逻辑；`app/api/app.py` 未再改动。

## 1. 修复前复现（真实 JS 执行，非文本推断）

使用隔离控制面真实调用 `POST /api/runs`，把返回体注入浏览器，由浏览器执行当时的 `js/view-model.js`：

| 项 | 复现输入 | 修复前实际输出 |
|---|---|---|
| U1 | A-301 跨领域问题，`max_tool_calls=1`、`with_approval=false`（真实运行：`status=failed`、`verdict=insufficient`、`st_2_billing`/`st_3_property` 均 `budget_exhausted`） | `agent:billing` / `agent:property` = `not_called`「本次未调用」，`subtaskId` 为空；6 条 Trace 中 4 条的 agent 为空；规划只显示 1 个子任务 |
| U2 | 同一复杂调查（真实运行：6 条 finding，其中 3 条合同条款、1 条工单） | 节点发现数 `lease=1 / billing=1 / property=0`，`total=6` → 条款与工单发现未进入节点 |
| U3 | `{"status":"failed","report":{"error":{"code":"internal_error","message":"injected test error"}}}`（`WorkflowService.submit` 的 AgentError 持久化形状） | `plan=success（规划已完成）/ verify=success（未发现冲突）/ report=success（报告已生成）` |

修复后同一批输入的输出见第 2–4 节与第 5 节回归结果。

## 2. U1 [P1]：失败 Agent 被显示成「未调用」——已修复

### 根因

`agentParticipation` / `traceRows` / 规划计数只读 `report.agent_results`。后端 `run_subtask` 把失败写入 `report.failures`（带 `subtask_id`、`capability`、`error_code`、`message`，**没有** `agent` 字段），失败子任务不会留在 `agent_results`，于是前端既判「未参与」，又丢掉错误、工具记录与计数。

### 修改

集中在 `view-model.js` 一个入口，协作图、节点详情、调用记录与筛选共用同一份索引：

- 新增 `buildSubtaskIndex(run)`：合并 `report.agent_results`（终态结果）、`report.failures`（当前未解决失败）、`report.resolved_failures`（已恢复的历史失败）与 `run.traces`，**按 `subtask_id` 去重**，不依赖数组顺序。
- Agent 归属：结果记录自带 `agent` 名字段优先；否则用 `capability` 查静态能力表（`AGENT_DEFS[].capabilities`，来自各 Agent 的 YAML：`lease.query` / `lease.renewal_evaluation` / `billing.statement` / `billing.arrears_check` / `property.work_orders`）。两者都没有时保持「Agent 未确定」，不按子任务 ID 字符串猜。
- 终态：有结果按结果状态；否则当前失败即失败；只有 Trace 或只有历史失败时判 `unknown`（不猜成功/失败）；什么都没有才是 `not_called`。
- 领域聚合：一个领域多个子任务时取最严重终态并**保留全部子任务**，不再 `find` 第一条；`resolved_failures` 只作为审计信息，不覆盖当前成功。
- 失败标签直接带错误码（如「失败 · budget_exhausted」），节点详情展示错误码、后端 `message`、该子任务的全部工具尝试与 `来源 result / failure / trace`。
- `traceRows(run)` 改由索引解析 Agent；索引里没有的 Trace 标「未关联」并保留原始记录（新增「N 条记录无法关联到子任务」提示与「未关联子任务」筛选项）。
- 规划节点：报告没有原始计划数组，因此改为「已记录 N 个子任务（有终态结果 M · 当前未解决失败 K）」，按真实 `subtask_id` 去重；不再把结果数当规划总数。

### 修复后（真实运行）

```text
plan=success(多领域分流)
agent:lease=partial(部分完成)
agent:billing=failed(失败 · budget_exhausted)
agent:property=failed(失败 · budget_exhausted)
verify=failed(存在失败子任务 · 2 个)
report=partial(报告已生成 · 证据不足)
approval=not_called(本次无审批请求)
```

节点详情：`st_2_billing 失败 · budget_exhausted`、后端消息「预算不足：工具调用数 已用 1、预留 0、上限 1」、工具尝试 2 次（`billing.statement.read` ×2，`budget_exhausted`），Agent 归属显示「由 capability 对照 Agent 定义表」。

## 3. U2 [P2]：条款与工单发现丢失——已修复

### 根因

`evidenceDomain()` 输出的是**证据展示分组**（`documents` / `work_orders` / `billing` / `lease`），而 `findingsForAgent` 直接与 Agent key（`lease` / `billing` / `property`）比较，`documents`、`work_orders` 永远比不上。

### 修改

- 明确分开两件事：`evidenceDomain()` 仍负责证据页分组（新增 `unknown` 分组，未知前缀不再默认归 `lease`）；新增 `attributeFinding()` / `findingsAttribution()` 负责 finding 的 Agent 归属。
- 归属顺序（全部集中在 `view-model.js` 一处）：
  1. 报告自带 `source.document_id` → 合同条款 → `lease`（basis=`source`）；
  2. 证据分组里**唯一**的领域指向（`documents` → lease、`billing` → billing、`work_orders` → property）→ 对应 Agent（basis=`evidence`）；
  3. 多个领域指向 → `cross_domain`，列出涉及的 Agent，**不归任何节点、也不复制**；
  4. 只有租约核心实体（`lease_` / `unit_` / `ten_` / `rule_`）→ `lease`；
  5. 含无法归类前缀、无 `evidence_ids` 或其它 → 未关联。
- 采用「领域指向优先」而不是多数票：账单 finding 同时引用 `lease_xh_a301_2025` 与 `inv_/itm_/pay_/alloc_`，按多数票或按「含租约即租约」都会归错，现在稳定归 `billing`。
- 摘要页新增「跨领域 / 未关联发现」区域；节点详情的「归属依据」改为按实际算法生成（如「报告提供的条款来源字段（doc_xh_a301_contract）」），不再笼统写「按证据 ID 前缀归属」。

### 修复后（真实复杂调查）

| 节点 | 修复前 | 修复后 |
|---|---|---|
| 合同 Agent | 1 条 | **4 条**（租期 1 + 条款 3，条款带页码与条款号） |
| 账单 Agent | 1 条 | 1 条 |
| 物业 Agent | 0 条 | **1 条**（相关工单 3 条，未关闭 1 条） |
| 跨领域 / 未关联 | 无此概念 | 0 条（该 fixture 全部可归属） |
| 总数 | 6 | 6（未丢失、未复制） |

## 4. U3 [P2]：异常/缺字段报告被画成绿色成功——已修复

### 根因

`planNode` / `verifyNode` / `reportNode` 只要 `run.report` 为真就判成功；`asArray()` 把缺失字段变成空数组，`requires_human_review !== true` 视为「不需要复核」，`report.error` 也被当成正常报告。

### 修改

- 新增字段三态判定 `fieldInfo()` / `textField()`：区分「未提供」「类型异常」「明确的空数组」。
- `report.error` 存在时：规划与核验 → `unknown`（信息未提供），报告 → `failed`（未生成），审批 → `unknown`；顶部状态与概况条也改用 `runStatusMeta(status, { reportError })`，避免 `completed` 掩盖异常。
- 核验节点联合判定：失败子任务 → `failed`；叙述与字段不一致 → `partial`；`conflicting` → `partial`；`insufficient` → `partial`；资料缺口 → `partial`；只有 `supported` + `completeness=complete` + 无缺口 + `requires_human_review === false` 才 `success`。缺 `verdict` / `conflicts` / `missing_information` 或类型不对 → `unknown`，文案明确「不能据此宣称未发现冲突」。
- 报告节点区分「报告文档已生成」与「结论成立」：`insufficient` → 「报告已生成 · 证据不足」，`conflicting` → 「报告已生成 · 存在冲突」，需复核 → 「报告已生成 · 需人工复核」。
- 新增 `unknown` 状态：灰色虚线徽章 `?`，画布连线对 `unknown` 保持虚线，不假装已执行。
- 摘要页：`report.error` 时只展示错误与该运行的基本信息；冲突/缺失区区分「报告未提供该字段」与「明确为空数组」。
- 未把 `run.status=failed` 机械传播到所有节点：每个节点按自身可观测字段判定（例如预算耗尽运行里 `plan` 仍据 `route` 显示成功，`report` 因 `insufficient` 显示「证据不足」而不是失败）。

### 修复后

```text
report.error 运行：plan=unknown(规划信息未提供) verify=unknown(核验信息未提供)
                 report=failed(报告未生成) approval=unknown(审批状态未提供)
                 三个领域=not_called，全部连线虚线，概况条「失败 / 未产出结论」
```

## 5. 测试与证据

### 5.1 新增可运行的 JavaScript 回归

`backend/tests/test_ui_view_model.py` + `app/api/static/tests/ui-model-harness.html` + `ui-model-cases.js`：

- Python 侧用隔离控制面真实调用 API（复杂调查、预算耗尽、简单账单），把返回体注入静态服务；
- 用**真实浏览器**（Chrome/Edge，`--headless=new --dump-dom`）加载 harness，由浏览器执行真实的 `view-model.js`；
- 解析浏览器写回的 JSON 并断言。找不到浏览器时整类 `SkipTest` 并说明原因，不静默通过。

实际结果：**17 个用例 / 84 个断言 / 0 失败**，其中 15 个为结构化 fixture、**2 个为真实 API 输出**。

| 场景 | 来源 | 断言数 |
|---|---|---|
| 正常单领域：只标记真实参与的能力 | fixture | 3 |
| 正常多领域：Agent / 计数 / 发现 / Trace 归属一致 | fixture | 7 |
| 工具预算耗尽：失败可见，保留错误码与工具尝试 | fixture | 9 |
| 权限拒绝 / 超时：不显示未调用，失败历史保留 | fixture | 6 |
| 补查成功 + 多子任务：当前终态准确、旧失败可审计 | fixture | 5 |
| 发现归属：租约 / 条款 / 账单 / 工单全覆盖 | fixture | 6 |
| 跨领域 / 未知前缀 / 无证据：不误归且可见 | fixture | 6 |
| report.error：规划 / 核验 / 报告均不给绿灯 | fixture | 5 |
| 旧记录缺字段：显示未知而不是成功 | fixture | 2 |
| 字段类型异常：不崩溃、不宣称无冲突 | fixture | 4 |
| insufficient：报告已生成但证据不足 | fixture | 4 |
| conflicting：冲突并列、需复核 | fixture | 3 |
| 叙述与字段不一致：核验降级 | fixture | 2 |
| supported 且字段完整：可以显示成功 | fixture | 5 |
| Trace 归属：子任务缺失或未知时不猜 | fixture | 4 |
| 真实 API：A-301 复杂调查 | **real** | 7 |
| 真实 API：工具预算耗尽 | **real** | 6 |

其中「权限拒绝 / 超时」与 `report.error` 是**按后端真实输出契约构造的结构化 fixture**，不是宣称本轮真实服务发生过内部崩溃；真实 API 用例用的是本轮实际 `POST /api/runs` 的返回体。

### 5.2 既有回归

| 命令（在 `backend/`） | 实际输出 |
|---|---|
| `python -m unittest discover -s tests -p "test_*.py"` | `Ran 409 tests in 22.255s` → `OK (skipped=1)`（Task 028 基线 403，本轮 +6） |
| `python tests/smoke_agent_contracts.py` | 全部通过，57 项 |
| `python -m unittest tests.test_ui_view_model -v` | `Ran 6 tests in 1.346s` → `OK` |

### 5.3 浏览器验收（真实服务，隔离数据）

隔离服务 `127.0.0.1:8021`，临时控制面（不触碰用户既有运行，不审批用户既有草案）：

- 控制台：无 `pageerror`、无 `console.error`；无 4xx/5xx 资源请求；资源 200 且 MIME 正确。
- 1440×900、1280×800：首屏可见任务输入、协作图与概况条，`scrollWidth ≤ innerWidth` 无横向溢出。
- 390×844：`scrollWidth = 390`、画布单列、SVG 隐藏、`overflow` 元素为空。
- 两级审批通过（`approved_draft_only`、`executed_side_effects=[]`）、驳回（`stages=[rejected,pending]`）、调用记录按 Agent 筛选、节点详情均实测。

截图（`docs/reviews/task029_screenshots/`）：

| 文件 | 内容 | 数据来源 |
|---|---|---|
| `01-report-error-fixture-1440x900.png` | `report.error` 运行：失败 / 未产出结论 / 节点 `unknown` 与 `failed` | **注入 fixture**（临时库，明确标记） |
| `02-overview-complex-1440x900.png` | 复杂调查总览（三领域参与、待审批） | 真实 API |
| `03-node-detail-lease-findings-1440x900.png` | 合同节点详情：4 条发现（租约 + 3 条款） | 真实 API |
| `04-budget-failure-overview-1440x900.png` | 预算耗尽：两个领域「失败 · budget_exhausted」 | 真实 API |
| `05-budget-failure-node-detail-1440x900.png` | 失败节点详情：错误码、后端消息、工具尝试 | 真实 API |
| `06-calls-filtered-billing-1440x900.png` | 调用记录按 Agent 筛选，含 Agent 列 | 真实 API |
| `07-approval-approved-1440x900.png` | 两级批准完成、草案与差额分栏 | 真实 API |
| `08-approval-rejected-1440x900.png` | 第一阶段驳回 | 真实 API |
| `09-narrow-390-budget-failure.png` | 390px 窄屏纵向布局 | 真实 API |
| `10-overview-1280x800.png` | 1280×800 总览 | 真实 API |

## 6. 修改文件

| 文件 | 类型 | 说明 |
|---|---|---|
| `backend/app/api/static/js/view-model.js` | 修改 | 子任务索引与终态聚合、finding 归属、字段三态与节点判定、Trace 归属、运行状态覆盖 |
| `backend/app/api/static/js/components/report.js` | 修改 | 节点详情（失败/多子任务/归属依据）、跨领域与未关联区域、调用记录 Agent 列与未关联提示、`report.error` 分支 |
| `backend/app/api/static/js/components/graph.js` | 修改 | `unknown` 不算「已走到」，连线保持虚线 |
| `backend/app/api/static/js/app.js` | 修改 | 顶部状态使用 `reportErrorOf(run)` |
| `backend/app/api/static/css/workbench.css` | 修改 | `unknown` 状态徽章、节点徽章换行、子任务终态配色 |
| `backend/app/api/static/tests/ui-model-harness.html` | 新增 | 浏览器内执行 view-model 的测试入口 |
| `backend/app/api/static/tests/ui-model-cases.js` | 新增 | 15 个 fixture 用例 + 2 个真实 API 用例 |
| `backend/tests/test_ui_view_model.py` | 新增 | 起静态服务、注入真实返回体、无头浏览器执行与断言 |
| 文档 | 新增/修改 | 本报告、029 归档追加、索引、开发日志、问题记录、检查点、基线、路线图 |

页面版式、Tabler 1.7.4 本地资源与许可、模块拆分、`/static` 挂载均未改动。

## 7. 剩余限制与未完成项

1. 规划节点仍无原始计划数组可读（后端报告不提供），所以只能显示「已记录子任务」，无法证明「计划了几个、执行了几个」。
2. 证据分组和 finding 归属都是**展示推断**：后端没有「证据所属领域」和「finding 来源子任务」字段。当前规则已在页面与本文说明；若后端将来补字段，应改为读取显式来源。
3. 一条 Trace 若其 `subtask_id` 在报告里完全不存在（例如任务在写结果前崩溃），只能显示「未关联」，无法自动归属。
4. `report.error` 的浏览器截图来自注入 fixture（结构取自 `WorkflowService.submit` 的 AgentError 分支）；本轮没有让真实服务产生内部崩溃。
5. 前端回归依赖本机 Chrome/Edge；无浏览器环境会跳过并显式说明，不算通过。
6. 窄屏下协作视图仍排在表单与历史之后（Task 027 遗留的体验项，本轮按要求未调整版式）。
7. Z1–Z3、独立模型配置、完整处置建议、PostgreSQL 与正式真实评测仍属其他待办，本轮未声称解决。
