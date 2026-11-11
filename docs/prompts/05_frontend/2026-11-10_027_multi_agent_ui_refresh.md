# 2026-11-10_027_multi_agent_ui_refresh

## 1. 基本信息

- 日期：2026-11-10（Asia/Shanghai）。
- 任务编号：027；模块：05_frontend。
- 关联：014（演示页）、025（未关闭缺陷）、026（当前指导关系）。
- Codex 调研起点：main / 8569cc2，工作区干净。
- 本轮 Commit：Pending，未提交/推送。
- 状态：**已实施并通过自检（2026-11-10 DeepSeek 实施，见第 10 节）；未提交、未推送。**

## 2. 任务目标和背景

用户认为页面简陋，希望体现多 Agent 合作，并明确要求先参考 GitHub 模板，由 Codex 写 Prompt、DeepSeek 实施。保留当前 FastAPI/Agent 骨架，使用开源 UI 基础改善展示，不为套模板迁移业务系统。

## 3. 原始用户 Prompt

```text
这个前端也太丑了 帮我美化一下 要提现出那种多agent的合作的感觉 帮我写一份prompt 然后我让deepseek 完成 你从github上看看 有没有这种的 最好有模板可以套用或者借鉴 不要自己从头开始
```

## 4. AI 实际执行的主要步骤

1. 检查 Git、docs 编号、实际前端与 API 返回结构、当前架构边界。
2. 搜索 GitHub，使用 GitHub 连接器读取候选仓库元数据、README、LICENSE、模板 HTML、固定 tag 的 package.json 与布局。
3. 核实 Tabler/starter 可复用、Langflow 适合视觉参考、Agent Chat UI 已归档且协议不直接匹配。
4. 编写模板选型记录与可直接执行的 DeepSeek Prompt，明确真实状态映射、静态资源本地化、模块边界、截图/功能验收。
5. 登记任务、更新日志与检查点；校验本轮 Markdown、原始 Prompt、链接和 Git 范围。实际检查结果在交付时记录。

## 5. 新增和修改的文件

| 文件 | 类型与用途 |
|---|---|
| docs/handoffs/DEEPSEEK_TASK027_MULTI_AGENT_UI_PROMPT.md | 新增；给 DeepSeek 执行的完整 Prompt |
| docs/reviews/2026-11-10_multi_agent_ui_template_review.md | 新增；实际调研、来源、许可与选择理由 |
| 本文件 | 新增；原始 Prompt、Codex 调研与后续实施归档 |
| docs/README.md | 修改；登记 027 |
| docs/development_logs/development_log.md | 修改；记录调研与待实施状态 |
| docs/checkpoints/git_history.md | 修改；本轮 Pending 与 026 提交回填说明 |
| docs/product/PROJECT_DEVELOPMENT_ROADMAP.md | 修改；记录用户优先安排的展示任务，仍为待实施 |

## 6. 执行结果和验证方式

已选定 Tabler starter/core 1.7.4 为复用基础，Langflow 只作协作画布参考。实施方案保持现有 API、规则演示、审批与证据语义；不伪造实时 Agent 状态，不实现新的经营决策层。

**Codex 本轮没有修改前端代码、安装模板或跑 UI 验收。** 静态文档核验以本轮真实结果为准；DeepSeek 完成后在下方追加实际实现、测试与截图，不覆盖本段调研边界。

本轮实际静态核验：7 份 Markdown（4 份修改、3 份新增）；58 个本地链接目标存在；33 个代码围栏块闭合；001–027 唯一且连续；027 原始用户 Prompt 精确匹配、归档九节齐全；UTF-8 与 git diff --check 通过。无 backend/ 或评测数据变更。

## 7. 遇到的问题及解决方案

| 问题 | 原因 | 解决 |
|---|---|---|
| 不能直接套 Agent Chat UI | Next.js + LangGraph Server 协议与本项目 FastAPI 不同，仓库已归档 | 不采用为基础，选 Tabler 静态组件 |
| 无逐节点实时进度 | 当前接口等待结果后返回 | 等待状态 + 真实结果回顾，不假造思考/进度 |
| GitHub tags ref 请求失败 | 连接器 URL 校验拒绝该路径 | 读取固定 tag 的实际文件核实版本；未声称已解析完整 commit SHA |

## 8. 对应 Git Commit Hash

- Pending：本轮未提交或推送。
- 起点 8569cc2 是 Task 026 文档提交，不是本轮 hash。

## 9. 后续待办事项

- DeepSeek 完整阅读实施 Prompt，完成模板资源复用、协作视图、真实 API 适配、浏览器验收与归档。
- 实施完成后追加记录；Z1–Z3、独立模型配置、处置建议生成、PG/真实评测等仍独立管理。
- 实际提交操作发生后再回填 Git hash。

---

## 10. DeepSeek 实施记录（2026-11-10 追加）

> 第 1–9 节是 Codex 调研与原始 Prompt 的原文记录，未改写；本节记录实际实施、验证与归档。
> 原始用户 Prompt（第 3 节）保持不变，任务编号沿用 027。

### 10.1 实际做了什么

1. 核对真实返回：用隔离服务实测 `A-301` 复杂调查（fanout、conflicting、1 冲突、1 缺失、审批 pending）与
   简单账单问题（deterministic、仅 billing 参与），确认 `agent_results` / `conflicts` / `traces` / `approval_request`
   的实际字段名（`traces[].tool` 而非 `tool_name`），再据此设计展示映射。
2. 下载并固定 `@tabler/core@1.7.4` 预编译资源到 `backend/app/api/static/vendor/tabler/`，保留 MIT 许可证，
   记录 URL、npm integrity、tarball 与落地文件 SHA-256；删除两处 `sourceMappingURL` 注释并写入 `THIRD_PARTY_NOTICES.md`。
3. 按 tabler-starter 的 `page / page-wrapper / page-header / page-body / container-xl / row-cards / card / form / nav-tabs`
   结构重写 `index.html`，样式与脚本拆到 `css/` 与 `js/`；`app/api/app.py` 增加受限 `/static` 挂载（只挂 static 目录）。
4. 自写 Agent 协作画布：节点来自固定职责图，SVG 连线按实际布局计算（扇出曲线 + 合并母线 + 链式箭头）；
   点击节点在详情面板展示该 Agent 的实际状态、工具调用、冲突与发现。
5. 报告区 5 个标签页（摘要 / 证据 / 调用记录 / 审批 / 原始数据），全部按后端真实字段渲染，缺失值显示「未提供 / 待核实」。
6. 状态真实性：提交中只显示整体等待态；只有 `report.agent_results` 出现的能力才高亮；未参与领域为「本次未调用」；
   规划/核验/报告标为「结果回顾」；不显示百分比、思考链或逐节点耗时。
7. 审批：双角色串行、审批人只从 `/api/meta` 白名单选择并按当前阶段预选、意见写入 `reason`、
   草案金额与 `computed_variance` 分栏标注、批准后显示 `executed_side_effects` 为空。
8. 并发与错误处理：详情请求使用序号 + `AbortController` 防旧响应覆盖；网络/非 JSON/4xx5xx 统一显示可读错误与 `trace_id`。
9. 补充测试与浏览器验收，并把截图、报告与索引更新归档。

### 10.2 新增和修改的文件

| 文件 | 类型 | 说明 |
|---|---|---|
| `backend/app/api/app.py` | 修改 | 增加 `StaticFiles` 挂载（`/static` → `app/api/static`），不改任何路由语义 |
| `backend/app/api/static/index.html` | 重写 | Tabler 骨架 + 固定职责图节点；无外网资源引用 |
| `backend/app/api/static/css/workbench.css` | 新增 | 领域配色、状态语义、画布/连线、响应式、`prefers-reduced-motion` |
| `backend/app/api/static/js/api.js` | 新增 | fetch 封装、错误归一化、`X-Trace-Id`、AbortSignal |
| `backend/app/api/static/js/view-model.js` | 新增 | 只读展示映射与状态中文化（纯函数） |
| `backend/app/api/static/js/dom.js` | 新增 | `textContent` 建 DOM、复制按钮 |
| `backend/app/api/static/js/components/graph.js` | 新增 | 节点状态 + SVG 扇出/合并母线/链式箭头 |
| `backend/app/api/static/js/components/report.js` | 新增 | 摘要/证据/调用记录/审批/原始数据/节点详情 |
| `backend/app/api/static/js/app.js` | 新增 | 协调层：加载、提交、选择、并发防护、审批提交 |
| `backend/app/api/static/vendor/tabler/**` | 新增 | core 1.7.4 `tabler.min.css` / `tabler.min.js` + MIT LICENSE |
| `backend/app/api/static/THIRD_PARTY_NOTICES.md` | 新增 | 来源、版本、哈希、许可、复用组件与本项目修改 |
| `backend/tests/test_api.py` | 修改 | 新增 `TestWorkbenchStaticAssets`（4 项）；更新首页标题断言 |
| `docs/reviews/2026-11-10_multi_agent_ui_implementation_review.md` | 新增 | 实施与视觉自检报告 |
| `docs/reviews/task027_screenshots/*.png` | 新增 | 7 张真实浏览器截图 |
| 本文件 | 修改 | 追加本节；更新第 1 节状态 |
| `docs/README.md`、`docs/development_logs/development_log.md`、`docs/checkpoints/git_history.md`、`docs/product/PROJECT_DEVELOPMENT_ROADMAP.md`、`docs/demo/demo_script.md`、`docs/architecture/CURRENT_BASELINE.md` | 修改 | 索引、日志、检查点、进度、演示脚本与展示现状同步 |

### 10.3 验证结果（实际输出）

| 验证项 | 结果 |
|---|---|
| `python -m unittest discover -s tests -p "test_api.py"` | `Ran 33 tests in 4.493s` → OK |
| `python -m unittest discover -s tests -p "test_*.py"` | `Ran 403 tests in 22.534s` → OK (skipped=1) |
| `python tests/smoke_agent_contracts.py` | 57 项通过 |
| `python -m uvicorn app.api.app:app --host 127.0.0.1 --port 8018` | `/`、`/static/css/workbench.css`、`/static/vendor/tabler/js/tabler.min.js`、`/api/meta` 均 200 |
| 浏览器控制台 / 网络 | 无脚本错误，无缺失资源；静态资源 200 且 MIME 正确 |
| 1440×900 / 1280×800 / 390×844 | 无横向溢出；窄屏纵向步骤布局生效 |
| A-301 复杂调查 | 三领域参与、冲突与缺失显示、Trace 与节点详情一致 |
| 简单账单问题 | 仅账单 Agent 高亮，其余「本次未调用」 |
| 两级审批 | 物业→财务，`approved_draft_only`、`executed_side_effects=[]`；驳回路径正确 |
| 故障注入 / 竞态 | 500 与断网均有可读错误 + trace_id；旧响应被 abort 不覆盖新选择 |

细节、字段映射表与截图清单见[实施与视觉自检报告](../../reviews/2026-11-10_multi_agent_ui_implementation_review.md)。

### 10.4 未完成 / 已知限制

- 无逐节点实时事件流（沿用一次性返回 + 结果回顾），未新增 SSE/WebSocket。
- `authoritative_amounts` 在当前离线路径为空，金额区展示工具计算的 finding 文本；未新增金额运算。
- 窄屏区块顺序未调整（协作视图仍排在表单与历史之后）。
- 证据分组按 ID 前缀映射，属展示启发式，已在页面与报告中注明。
- 本轮未提交、未推送；Z1–Z3、独立模型配置、处置建议生成、PG/真实评测仍独立管理。

### 10.5 建议的 Git Summary / Description（待确认后执行）

- Summary：`feat(api,ui): rebuild multi-agent workbench on Tabler 1.7.4`
- Description：

```text
Reuse the official Tabler starter layout and @tabler/core 1.7.4 prebuilt assets
(vendored locally with license, version and SHA-256 records) and replace the single-file
demo page with a multi-agent collaboration workbench.

- mount /static for the existing static directory only
- fixed responsibility graph (plan -> lease/billing/property -> merge -> verify -> report -> approval)
  with node details, real tool traces and per-domain findings
- report tabs for summary, evidence, tool calls, approval and raw JSON
- truthful states: single waiting state while the request is in flight, "not called" for unused
  agents, result review instead of fabricated live progress
- two-stage approval UI (property -> finance) with draft amount and computed variance shown separately
- race protection via request sequence + AbortController, typed API errors with trace_id
- tests: 403 backend tests OK (skipped=1), 57 contract checks, new static-asset route tests
```

- 本轮未执行该提交；`docs/` 下他人未提交的改动保持原样。
