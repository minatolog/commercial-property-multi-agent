# Task 027 实施与视觉自检报告：多 Agent 协作工作台

- 日期：2026-11-10（Asia/Shanghai）。
- 实施者：DeepSeek（按 [实施 Prompt](../handoffs/DEEPSEEK_TASK027_MULTI_AGENT_UI_PROMPT.md) 执行）。
- 代码基线：`main` / `8569cc2` 之上的工作区变更；本轮**未提交、未推送**。
- 相关记录：[Codex 模板调研](2026-11-10_multi_agent_ui_template_review.md)、[Task 027 归档](../prompts/05_frontend/2026-11-10_027_multi_agent_ui_refresh.md)。

## 1. 结论

现有 FastAPI 同源页面已改造为 **商业地产 · Agent 协作工作台**：版式、卡片、表单、徽章、列表、标签页来自本地固定的
Tabler `@tabler/core@1.7.4`；中央「Agent 协作视图」用节点 + 端口 + 有向连线表达任务规划 → 三个领域 Agent →
证据核验 → 调查报告 → 人工审批的固定职责关系（视觉组织参考 Langflow，代码为本项目自写）。

Agent/工具/审批/评测逻辑、权限模型、数据库与评分均未改动；`app/api/app.py` 只新增一个受限的 `/static` 挂载。
页面不伪造逐节点实时进度，全部状态来自 `/api/runs` 返回的 `report`、`traces` 与 `approval_request`。

## 2. 复用的模板与固定版本资产

| 用途 | 来源 | 版本 / 提交 | 许可 |
|---|---|---|---|
| 页面骨架（page / page-header / container-xl / row-cards / card / btn / form / list / nav-tabs） | [tabler/tabler-starter](https://github.com/tabler/tabler-starter) `index.html` | 提交 `cc48a519c3684879761e1a49a1d1017bb47a68cd` | MIT |
| 预编译 CSS/JS | [`@tabler/core`](https://www.npmjs.com/package/@tabler/core) `dist/css/tabler.min.css`、`dist/js/tabler.min.js` | 1.7.4 | MIT |
| 协作画布（节点、母线、箭头、详情面板） | 本项目自写（`css/workbench.css` + `js/components/graph.js`） | — | 本项目 |

获取与落地证据（详见 [`static/THIRD_PARTY_NOTICES.md`](../../backend/app/api/static/THIRD_PARTY_NOTICES.md)）：

- 下载地址 `https://registry.npmjs.org/@tabler/core/-/core-1.7.4.tgz`，npm `dist.integrity`
  `sha512-fHAPnsKl9JnJJkLxE5UbPkLUBlgn/G1b0urLh5LMGt2DnebpK2tZNEKD/8YiwGz67EoNahGretSsHovDOvJGWA==`；
  tarball SHA-256 `ccb1631d26cec2589d357556c8fe86bbba75ef0bcf672a4939a7ed5d4ab7319c`（4,627,544 字节）。
- `vendor/tabler/css/tabler.min.css`：686,694 字节，SHA-256 `d75139f3ec33bff19063eca16f8628dbd3d9e43066878ade0b9ccc9780fd1de1`。
- `vendor/tabler/js/tabler.min.js`：149,338 字节，SHA-256 `962d5921689cc277fcb7dda8449204f0029d9971b5aee1a3a0775756e53a2dca`。
- `vendor/tabler/LICENSE`：1,090 字节，SHA-256 `4f88a82d13be3c5c63a12c5631eae914aa4381b6dc17641bf1ab85f3f8f6c8a5`。

**本项目对上游文件的唯一改动**：删除两个 `<sourceMappingURL>` 尾注释（未附带 `.map`，避免浏览器请求缺失资源）；
其余字节未改。starter 里两处 `cdn.jsdelivr.net/npm/@tabler/core@latest/...` 引用已替换成上述本地固定文件，
运行期不访问 CDN / Google Fonts / 远程图片 / Node 服务。

## 3. 实际使用的 Tabler 组件

| Tabler 类 | 页面位置 |
|---|---|
| `page` / `page-wrapper` / `page-header` / `page-body` / `container-xl` | 整页骨架与两级容器 |
| `row row-cards` + `col-12 col-lg-4 col-xxl-3` | 左侧任务 / 历史栏与右侧工作区栅格 |
| `navbar` / `navbar-brand` / `navbar-nav` | 顶栏（项目名、规则演示标识、刷新） |
| `card` / `card-header` / `card-body` / `card-footer` / `card-title` / `card-actions` | 新建调查、最近运行、协作视图、报告卡片 |
| `form-label` / `form-control` / `form-hint` / `form-select` / `form-check form-switch` | 问题、租约、审批开关、列表筛选、审批人/意见 |
| `btn` / `btn-primary` / `btn-outline-secondary` / `btn-ghost-secondary` / `btn-sm` / `btn-list` / `spinner-border` | 提交、刷新、示例问题、复制、审批、加载态 |
| `nav nav-tabs` / `nav-link` / `tab-content` / `tab-pane` + `data-bs-toggle="tab"` | 摘要 / 证据 / 调用记录 / 审批 / 原始数据（切换由本地 `tabler.min.js` 提供） |
| `badge` / `bg-azure-lt` / `text-secondary` / `small` | 状态徽章与辅助文字 |
| `list-group` / `list-group-item` | 最近运行列表 |
| `table table-sm table-vcenter` | 工具调用记录表 |
| `alert alert-danger/warning/success/secondary` | 错误、待审批、已批准、无审批请求 |
| `empty` / `empty-title` / `empty-subtitle` | 空态 |

状态语义（颜色 + 文字 + 符号，不只靠颜色）：`wb-status` 的 `data-status` 取 `idle / pending / success / partial /
failed / not_called / warning / info`，分别带 `○ ◌ ✓ ! ✕ – ! i` 前缀符号。

## 4. 页面结构

```text
navbar（项目名 + 规则演示·合成数据 + 刷新数据）
page-header（租约/运行 ID、问题、状态说明、运行状态徽章、新建调查）
├─ 左栏 col-lg-4：新建调查（问题 / 租约 / 审批开关 / 示例问题 / 提交）
│               最近运行（本地筛选 + 状态徽章列表）
└─ 右栏 col-lg-8：Agent 协作视图
    ├─ 概况条：执行状态 / 证据结论 / 冲突与缺口 / 审批
    ├─ 画布：任务规划 → 合同·账单·物业 Agent → 各领域结果合并 → 证据核验 → 调查报告 → 人工审批
    └─ 节点详情（点击节点后展开：状态、工具调用、冲突、发现）
    调查报告与证据（5 个标签页）
```

1440×900 与 1280×800 首屏可见任务输入、协作视图与概况条；≤991.98px 画布改为纵向卡片 + 左侧流程导轨，
隐藏 SVG 连线；≤767.98px 压缩标题字号并限 3 行，避免把协作视图挤出首屏。

## 5. 真实 API 映射

| 页面元素 | 后端字段（实际返回） |
|---|---|
| 顶部租约/运行/状态 | `GET /api/runs/{id}` 的 `lease_id`、`run_id`、`status`；`report.verdict`、`created_at` |
| 领域节点状态 | `report.agent_results[]` 的 `capability` / `agent` / `subtask_id` / `status`；无匹配记录 → 「本次未调用」 |
| 规划节点 | `report.route`（`deterministic` / `fanout`）、`report.revision`、`agent_results` 数量 |
| 核验节点 | `report.verdict`、`completeness`、`conflicts`、`missing_information`、`failures`、`requires_human_review` |
| 报告节点 | `report.findings` / `warnings` / `disclaimer` / `proposed_draft` |
| 审批节点 | `report.approval_status`、`report.approval_request.status` 与 `stages[]`（`role` / `seq` / `status` / `decided_by` / `decided_at` / `reason`） |
| 节点详情的工具调用 | `run.traces[]` 的 `tool`、`subtask_id`、`status`、`attempt`、`duration_ms`（按 `subtask_id` 关联） |
| 调用记录表的 Agent 列 | `report.agent_results` 按 `subtask_id` 反查 `agent`，不按行号猜 |
| 证据分组 | `findings[].evidence_ids`、`conflicts[].evidence_ids`、`proposed_draft.evidence_ids`、`approval_request.evidence_ids`；条款出处取 `findings[].source`（`document_id` / `document_version` / `page` / `clause_id` / 摘录） |
| 金额区 | `report.authoritative_amounts[]`（`rendered` / `conclusion` / `check_status`）；为空时退到 `derivation="computed"` 的 finding 文本，并明确说明 |
| 审批金额对照 | `report.proposed_draft.amount`（草案）与 `proposed_draft.computed_variance` / `conflicts[].amount`（差额）**分栏展示**，明确草案金额不是差额的计算结论 |
| 已批准结果 | `report.approved_draft.status` 与 `executed_side_effects`（空数组） |
| 调用计数 | `report.budget.used_tool_calls` / `max_tool_calls` |
| 审批人下拉 | `GET /api/meta` 的 `approver_allowlist`，按当前待办阶段的 `role` 预选；权限仍由服务端判定 |
| 上报字段 | `POST /api/runs`：`question` / `lease_id` / `with_approval`；审批：`decision` / `draft_version` / `reason` + `X-Actor-Id` |

**不发送**任何自报身份字段（`principal_id` / `permissions` / `roles` / `approval_roles`）；页面只使用
`approval_status` 与 `approval_request.status` 判断是否展示审批操作，不把 `completed` 解释为「争议已解决」。

## 6. 状态真实性规则

1. 提交期间（请求未返回）只显示整体「调查执行中，等待结果」，七个节点统一「状态待返回」，不按定时器推进、不造进度百分比。
2. 只有出现在 `report.agent_results` 里的能力才算参与；其余节点为「本次未调用」，虚线连通、`data-state="not_called"`。
3. 规划 / 核验 / 报告节点标注「结果回顾」，并在图下说明「接口一次性返回完整结果，不提供逐节点实时事件」。
4. 连线只有在起点与终点都「真的走到」时才高亮，未参与领域保持虚线支路（合并母线只连接实际参与的领域）。
5. 调用记录中的 `duration_ms` 明确标注为单次工具耗时，不求和当作任务总耗时；Trace 无开始时间，顺序不作为因果时间线。
6. 「处置建议」固定显示「暂未生成处置建议」——后端没有该字段，页面不编造。

## 7. 证据分组是展示映射（非后端分类）

后端没有「证据所属领域」字段，页面按 ID 前缀映射到四个分组：
`doc_` / `snip_` → 合同文书与条款；`inv_` / `itm_` / `pay_` / `alloc_` → 账单与付款；`wo_` → 物业工单；其余 → 合同与租约。
单条 finding 的领域归属按它引用的证据 ID 前缀多数票决定。该规则在「证据」标签页与节点详情处都有文字说明，
不声称是后端分类结果。

## 8. 前端文件组织

```text
backend/app/api/static/
  index.html                     Tabler 骨架 + 固定职责图节点（数据钩子）
  css/workbench.css              领域配色、状态语义、画布、响应式、reduced-motion
  js/api.js                      fetch 封装：网络错误 / 非 JSON / 4xx5xx / trace_id / AbortSignal
  js/view-model.js               只读展示映射（纯函数，无 DOM、无请求）
  js/dom.js                      textContent 建 DOM + 复制按钮
  js/components/graph.js         节点状态与 SVG 连线（扇出 + 合并母线 + 链式箭头）
  js/components/report.js        摘要 / 证据 / 调用记录 / 审批 / 原始数据 / 节点详情
  js/app.js                      状态协调、事件绑定、并发防护
  vendor/tabler/                 固定版本 CSS/JS + MIT 许可证
  THIRD_PARTY_NOTICES.md         来源、版本、哈希、许可、修改说明
```

安全：全部渲染走 `document.createElement` + `textContent`，不拼 `innerHTML`；长 ID / JSON 用
`overflow-wrap:anywhere` 与独立滚动容器。

## 9. 验证（本轮实际执行）

### 9.1 自动化测试

| 命令（在 `backend/`） | 实际输出 |
|---|---|
| `python -m unittest discover -s tests -p "test_api.py"` | `Ran 33 tests in 4.493s` → `OK`（含 4 项新增静态资源用例） |
| `python -m unittest discover -s tests -p "test_*.py"` | `Ran 403 tests in 22.534s` → `OK (skipped=1)` |
| `python tests/smoke_agent_contracts.py` | `全部通过，57 项` |

新增测试（`backend/tests/test_api.py::TestWorkbenchStaticAssets`）覆盖行为而非样式：
9 个静态资源的 HTTP 200 与 MIME；首页只引用本地资源且无 CDN 主机；
`/static/../app.py`、`/static/%2e%2e/app.py`、`/static/..%2fapp.py`、`/static/css/../../app.py` 均 404；
`/static/`、`/static/css/` 不返回目录列表（404）。
同时把原有 `test_index_page_renders` 的页面标题断言更新为新页面标题（页面改名属本次改动，不是绕过测试）。

### 9.2 静态资源 HTTP 实测

在隔离服务（临时数据目录，端口 8017）上实测：

| 路径 | 状态 | Content-Type |
|---|---|---|
| `/` | 200 | `text/html; charset=utf-8` |
| `/static/css/workbench.css` | 200 | `text/css; charset=utf-8` |
| `/static/js/app.js` | 200 | `application/javascript` |
| `/static/vendor/tabler/css/tabler.min.css` | 200 | `text/css; charset=utf-8` |
| `/static/vendor/tabler/js/tabler.min.js` | 200 | `application/javascript` |
| `/static/THIRD_PARTY_NOTICES.md` | 200 | `text/markdown; charset=utf-8` |
| `/static/%2e%2e/app.py` | 404 | — |

文档命令 `python -m uvicorn app.api.app:app --host 127.0.0.1 --port 8018` 也单独验证过：`/`、`/static/css/workbench.css`、
`/static/vendor/tabler/js/tabler.min.js`、`/api/meta` 均为 200。

### 9.3 浏览器实测（真实 Chrome，非示意图）

- 控制台：无 `pageerror`、无 `console.error`；网络面板无 4xx/5xx 资源请求（模拟故障的用例除外）。
- 1440×900：`document.documentElement.scrollWidth = 1425 ≤ 1440`，无横向溢出；三列画布 + 概况条可见。
- 1280×800：审批节点底边 766 < 800，协作图与概况条在首屏内完整可见。
- 390×844：`scrollWidth = 390`，无横向溢出；画布单列、SVG 隐藏、节点全宽 299px。
- A-301 复杂调查：三领域 `success/partial/partial`，冲突 1 条、资料缺失 1 条，节点详情中的工具与 Trace 一一对应。
- 简单账单问题：只有账单 Agent 高亮，合同/物业为「本次未调用」，合并母线只连接账单支路。
- 两阶段审批：物业（含意见）→ 财务（含意见），`request.status=approved`、`approved_draft.status=approved_draft_only`、
  `executed_side_effects=[]`；驳回路径为 `stages=[rejected,pending]`、`request.status=rejected`、操作区收起。
- 故障注入：500 非 JSON 响应显示「服务端返回了非 JSON 响应（HTTP 500）」+ `trace_id`；
  网络中断显示启动提示（`python -m uvicorn app.api.app:app ...`）；两种情况下已输入内容保留。
- 竞态：首个运行的详情请求被人为延迟 1.5s 后快速切换到第二个运行，旧请求被 abort，界面保持第二个运行（未回退）。

### 9.4 截图（`docs/reviews/task027_screenshots/`）

| 文件 | 内容 | 视口 |
|---|---|---|
| `01-overview-1440x900.png` | 协作总览：概况条 + 三领域 + 核验/报告/审批，已批准运行 | 1440×900 |
| `02-node-detail-and-calls-1440x900.png` | 账单 Agent 节点详情 + 调用记录表 | 1440×900 |
| `03-approval-approved-1440x900.png` | 两级审批均已批准、草案金额与差额分栏、副作用为空 | 1440×900 |
| `04-pending-1440x900.png` | 请求未返回时的等待态（节点全部「状态待返回」） | 1440×900 |
| `05-narrow-390x844.png` | 窄屏纵向布局 | 390×844 |
| `06-overview-1280x800.png` | 协作总览（较小桌面） | 1280×800 |
| `07-approval-rejected-1440x900.png` | 第一阶段驳回：状态、审批人、时间、意见 | 1440×900 |

截图取自隔离服务（临时 `runs.sqlite` / `graph.sqlite` / `approval.sqlite`），未触碰用户既有运行记录，
也未批准用户已有草案。

## 10. 布局偏差与取舍

| 上游参考 | 本项目做法 | 原因 |
|---|---|---|
| Tabler 默认带 Navbar + Sidebar 的后台布局 | 只保留 Navbar；无侧边栏与下拉/通知/搜索 | 单页工作台按钮必须有真实行为，不放装饰入口 |
| starter 的 CDN `@latest` | 固定 1.7.4 本地文件 | 运行期离线、可复现 |
| Langflow 可拖拽节点编辑器 | 固定职责图 + 结果回顾 | 本项目编排在 LangGraph 内部，不做通用编排器 |
| Tabler 图表/地图/插件 | 未引入 | 本任务不需要，避免无关依赖与许可混淆 |

## 11. 已知限制与未完成项

1. 浏览器可视高度低于 720px 时，图下方的说明文字需要滚动才能看全（首屏仍可见任务输入、协作图与概况条）。
2. 窄屏中「Agent 协作视图」排在表单和最近运行之后（保持单栏阅读顺序），需要向下滚动才能看到；
   本轮未重排移动端区块顺序。
3. 页面没有逐节点 SSE/WebSocket，仍是一次性返回 + 结果回顾；这不改变后端能力，也不假装有实时进度。
4. `report.authoritative_amounts` 在当前离线路径为空，金额区退化为展示工具计算的 finding 文本；未新增金额计算。
5. 证据分组依赖 ID 前缀（见第 7 节），后端若改变 ID 命名需要同步更新 `view-model.js`。
6. 旧「商业地产多 Agent 工作流演示」页面只保留在 Git 历史中，未在仓库内留副本。
7. 本轮未提交、未推送；`docs/` 下他人未提交的文档改动保持原样。
8. 变更后需要重启正在运行的 uvicorn 进程才能加载新的 `/static` 挂载（本机 8000 端口上的既有进程启动于改动前）。
