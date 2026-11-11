# 2026-11-10_029_ui_mapping_fixes

## 1. 基本信息

- 日期：2026-11-10；模块：05_frontend；关联任务：027、028。
- 阶段：Codex 编写返修 Prompt（第 1–9 节）；DeepSeek 已实施并自检（第 10 节）。
- 起点：main / 8569cc2，保留现有未提交变更；未提交/推送。

## 2. 任务目标和背景

依据 Task 028 审查，为 U1–U3 编写小范围返修指令、行为回归与归档要求，保留已完成版式和业务边界。

## 3. 原始用户 Prompt

```text
好帮我再写一个prompt 我发给deepseek
```

## 4. AI 实际执行的主要步骤

- 核对独立审查、实际 view-model 与节点详情代码、文档归档规范和 Git 状态。
- 编写 [DeepSeek 实施 Prompt](../../handoffs/DEEPSEEK_TASK029_UI_MAPPING_FIX_PROMPT.md)，明确集中映射、当前/历史失败、未知归属、错误状态和实际 JS 回归要求。
- 登记 029，更新日志与 Pending 检查点；仅文档检查，无业务测试或实现。

## 5. 新增和修改的文件

- 新增：本文件、`docs/handoffs/DEEPSEEK_TASK029_UI_MAPPING_FIX_PROMPT.md`。
- 更新：`docs/README.md`、`docs/development_logs/development_log.md`、`docs/checkpoints/git_history.md`。
- 未修改实现、测试、第三方资源、旧报告或截图。

## 6. 执行结果和验证方式

- 交付可直接引用的返修 Prompt，尚未执行修复，U1–U3 仍开放。
- 文档 UTF-8、围栏、新增链接、原始 Prompt、编号和 git diff 格式检查；具体结果在本阶段完成后追加。
- 阶段完成核验：上述检查全部通过，9 节归档完整、全局编号 001–029 连续无重复；git diff --check 通过（仅既有 LF/CRLF 提示），HEAD 保持 8569cc2。
- 403 tests / 57 项契约为 Task 028 证据，本阶段没有重新运行。

## 7. 遇到的问题及解决方法

未遇新增实施问题。Prompt 特别区分当前失败与历史失败、报告生成与结论可信、构造 fixture 与真实 API，防止返修仅替换文案或过度推断。

## 8. 对应 Git Commit Hash

Pending；HEAD 8569cc2，本阶段未提交/推送，不声明远端同步状态。

## 9. 后续待办事项

DeepSeek 按实施 Prompt 完成 U1–U3、真实 JS 行为回归与新报告；在本文件后追加实际执行记录，不覆盖本阶段记录或原始用户 Prompt。当前项目仍为版本候选，其他待办不变。

---

## 10. DeepSeek 实施记录（2026-11-10 追加）

> 第 1–9 节是 Codex 编写返修 Prompt 的阶段记录，未改写；第 3 节原始用户 Prompt 保持不变。
> 本轮未提交、未推送，HEAD 仍为 8569cc2。

### 10.1 实际执行步骤

1. 复现：用隔离控制面真实调用 `POST /api/runs`（A-301 复杂调查、`max_tool_calls=1` 预算耗尽、简单账单），把返回体注入浏览器执行**修复前**的 `view-model.js`，确认 U1（billing/property 显示「本次未调用」、4/6 条 Trace 无归属、规划只算 1 个子任务）、U2（节点发现 1/1/0，总数 6）、U3（error 形状下 plan/verify/report 全部 success）。
2. 在展示模型层集中重做映射（`view-model.js`）：`buildSubtaskIndex()` 合并结果/当前失败/历史失败/Trace 并按 `subtask_id` 去重；`capability`/`agent` 对照静态能力表归属 Agent；终态区分成功、部分、失败、`unknown`、未参与。
3. `findingsAttribution()` / `attributeFinding()`：优先 `source.document_id`，其次唯一的领域指向分组（documents→lease、billing→billing、work_orders→property），多领域或无证据时单列「跨领域 / 未关联」。
4. 节点判定改为基于字段三态与联合条件：`report.error` → 规划/核验 `unknown`、报告 `failed`；核验联合 verdict / completeness / conflicts / missing / failures / narrative_discrepancies / requires_human_review；区分「报告已生成」与「结论成立」。
5. 组件层同步：节点详情展示子任务终态、错误码、后端消息、工具尝试与归属依据；摘要页新增「跨领域 / 未关联发现」；调用记录新增 Agent 列、未关联提示与按 Agent 筛选；新增 `unknown` 状态样式。
6. 新增浏览器级 JS 回归与真实 API 复验，采集 10 张新截图（1 张来自注入 fixture，其余来自真实 API 输出），并归档。

### 10.2 新增和修改的文件

| 文件 | 类型 | 说明 |
|---|---|---|
| `backend/app/api/static/js/view-model.js` | 修改 | 子任务索引 / 终态 / 归属 / 字段三态 / 节点判定 |
| `backend/app/api/static/js/components/report.js` | 修改 | 节点详情、跨领域区域、调用记录 Agent 列与未关联提示、错误分支 |
| `backend/app/api/static/js/components/graph.js` | 修改 | `unknown` 不视为已走到，连线保持虚线 |
| `backend/app/api/static/js/app.js` | 修改 | 顶部状态尊重 `report.error` |
| `backend/app/api/static/css/workbench.css` | 修改 | `unknown` 徽章、节点徽章换行、子任务终态配色 |
| `backend/app/api/static/tests/ui-model-harness.html`、`ui-model-cases.js` | 新增 | 浏览器内执行 view-model 的回归入口与 17 个用例 |
| `backend/tests/test_ui_view_model.py` | 新增 | 无头浏览器驱动 + 真实 API 数据注入（6 项） |
| `docs/reviews/2026-11-10_task029_ui_mapping_fix_report.md` | 新增 | U1/U2/U3 复现、根因、修改、前后对比、证据与限制 |
| `docs/reviews/task029_screenshots/*.png` | 新增 | 10 张本轮截图 |
| `docs/README.md`、`docs/development_logs/development_log.md`、`docs/issues/issue_log.md`、`docs/checkpoints/git_history.md`、`docs/architecture/CURRENT_BASELINE.md`、`docs/product/PROJECT_DEVELOPMENT_ROADMAP.md` | 修改 | 索引、日志、问题、检查点、基线与进度同步 |

### 10.3 验证结果（实际输出）

| 验证项 | 结果 |
|---|---|
| `python -m unittest discover -s tests -p "test_*.py"` | `Ran 409 tests in 22.255s` → OK (skipped=1) |
| `python tests/smoke_agent_contracts.py` | 57 项通过 |
| `python -m unittest tests.test_ui_view_model -v` | `Ran 6 tests in 1.346s` → OK |
| 浏览器 JS 回归（harness） | 17 用例 / 84 断言 / 0 失败，含 2 个真实 API 用例 |
| 浏览器实测 | 控制台无错误、无失败请求；1440/1280 无横向溢出；390px 单列无溢出；两级审批与驳回、筛选、节点详情均正常 |
| 静态资源 | `/`、`/static/css/workbench.css`、`/static/js/*.js`、Tabler CSS/JS 均 200 且 MIME 正确 |

详细前后对比与截图清单见 [Task 029 修复报告](../../reviews/2026-11-10_task029_ui_mapping_fix_report.md)。

### 10.4 未完成 / 已知限制

- 报告不提供原始计划数组与「finding 来源子任务」字段，规划计数只能标「已记录子任务」，证据分组与 finding 归属仍属展示推断（已在页面说明）。
- `subtask_id` 在报告中完全不存在的 Trace 只能显示「未关联」。
- `report.error` 的界面证据来自注入 fixture（结构取自服务端 AgentError 分支），本轮未让真实服务发生内部崩溃。
- 前端回归依赖本机 Chrome/Edge，缺浏览器时跳过并说明。
- 未调整窄屏区块顺序（Task 027 遗留的体验项）。

### 10.5 建议的 Git Summary / Description（待确认后执行）

- Summary：`fix(ui): map failed subtasks and findings from real report fields`
- Description：

```text
Fix U1-U3 from the Task 028 review without changing layout or backend behaviour.

- U1: build one subtask index from agent_results + failures + resolved_failures + traces,
  so budget/permission/timeout failures show as failed with error code, tool attempts and
  trace ownership instead of "not called"; plan counts use real subtask ids
- U2: separate evidence display groups from finding ownership; prefer report source fields,
  map documents->lease and work_orders->property once, list cross-domain/unassociated
  findings explicitly instead of hiding or duplicating them
- U3: report.error and missing/invalid fields no longer render as success; verify/report
  nodes combine verdict, completeness, conflicts, missing info, failures and review flags;
  new "unknown" state keeps the canvas honest
- tests: headless-browser regression that executes the real view-model modules
  (17 cases / 84 assertions, 2 driven by real POST /api/runs output); 409 backend tests OK
  (skipped=1), 57 contract checks
```
